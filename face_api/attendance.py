"""
Classroom Multi-Face Attendance Service & Face Registration Engine
Coordinates SCRFD detection, quality filtering, ArcFace & dlib embedding extraction,
class-scoped similarity search, deduplication, and database attendance logging.
"""
import time
import os
import cv2
import numpy as np
import face_recognition
from datetime import datetime
from typing import Dict, Any, List, Optional, Union, Tuple

from . import config
from .detector import DetectedFace
from .quality import QualityCheckResult
from .matcher import MatchResult
from .pipeline import get_pipeline, decode_image, draw_visual_annotations

def register_single_student_face(
    image_input: Union[str, bytes, np.ndarray],
    db_session,
    student_id: int,
    organization_id: int
) -> Dict[str, Any]:
    """
    Registers a student's facial biometric embedding using SCRFD + ArcFace and dlib.
    Enforces strict registration constraints:
    - Exactly 1 face must be detected
    - Face must pass biometric quality checks
    - Generates 512-d normalized ArcFace embedding
    - Stores into database and invalidates organization cache
    """
    pipeline = get_pipeline()
    img = decode_image(image_input)

    # 1. Detect faces with SCRFD
    faces = pipeline.detector.detect(img, threshold=config.FACE_DETECTION_THRESHOLD)

    if len(faces) == 0:
        return {
            "success": False,
            "error": "No usable face detected. Please upload a clearer image."
        }

    if len(faces) > 1:
        return {
            "success": False,
            "error": "Multiple faces detected. Please upload an image containing only this student."
        }

    face = faces[0]

    # 2. Quality evaluation
    q_result = pipeline.quality_filter.evaluate(img, face)
    if not q_result.is_valid:
        return {
            "success": False,
            "error": f"Face quality check failed: {q_result.reason}. Please upload a clearer image.",
            "rejection_reason": q_result.reason,
            "metrics": q_result.metrics
        }

    # 3. Extract 512-d ArcFace embedding and 128-d dlib encoding
    embedding_512 = pipeline.recognizer.extract_embedding(img, face.landmarks)

    # Extract 128-d dlib encoding for universal backward compatibility
    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB) if len(img.shape) == 3 and img.shape[2] == 3 else img
    top, right, bottom, left = int(face.bbox[1]), int(face.bbox[2]), int(face.bbox[3]), int(face.bbox[0])
    # Ensure non-negative bounds
    h, w = img.shape[:2]
    box = (max(0, top), min(w, right), min(h, bottom), max(0, left))
    dlib_encs = face_recognition.face_encodings(img_rgb, [box])
    enc_128_list = dlib_encs[0].tolist() if dlib_encs else None

    # 4. Save to Database
    from app import Student, FaceEncoding
    student = db_session.get(Student, int(student_id))
    if not student:
        return {"success": False, "error": "Student not found in database."}

    # Verify organization isolation
    if student.organization_id != int(organization_id):
        return {"success": False, "error": "Access denied: Student does not belong to this organization."}

    # Save 512-d ArcFace record
    new_record_512 = FaceEncoding(
        student_id=student.id,
        encoding_path="",
        encoding_data=embedding_512.tolist(),
        created_at=datetime.utcnow()
    )
    db_session.add(new_record_512)

    # Save 128-d dlib record if extracted
    if enc_128_list:
        new_record_128 = FaceEncoding(
            student_id=student.id,
            encoding_path="",
            encoding_data=enc_128_list,
            created_at=datetime.utcnow()
        )
        db_session.add(new_record_128)

    db_session.commit()

    # 5. Invalidate organization & class cache
    pipeline.embedding_store.invalidate_cache(organization_id=int(organization_id), class_id=student.class_id)

    return {
        "success": True,
        "message": f"Face successfully registered for {student.name}.",
        "student_name": student.name,
        "roll_number": student.roll_number,
        "embedding_dim": len(embedding_512),
        "quality_metrics": q_result.metrics
    }


def process_classroom_attendance(
    image_input: Union[str, bytes, np.ndarray],
    db_session,
    organization_id: int,
    class_id: int,
    subject_id: Optional[int] = None,
    detection_range: str = "50m",
    student_count: int = 0
) -> Dict[str, Any]:
    """
    Executes the full classroom attendance pipeline strictly scoped to (organization_id, class_id):
    Classroom Camera Image -> SCRFD Multi-face detection -> Face Quality filtering ->
    Class-Scoped Matching (512-d + 128-d) -> Deduplication -> Attendance records creation.
    """
    pipeline = get_pipeline()
    t_start = time.perf_counter()

    # Step 1: Decode Image
    img = decode_image(image_input)
    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB) if len(img.shape) == 3 and img.shape[2] == 3 else img

    # Step 2: Load Class-Scoped Matcher
    t_load_0 = time.perf_counter()
    matcher = pipeline.embedding_store.get_matcher(
        db_session=db_session,
        organization_id=int(organization_id),
        class_id=int(class_id)
    )
    load_time = time.perf_counter() - t_load_0

    # Distance-Adaptive Resolution Scaling
    range_str = str(detection_range or "").lower().strip()
    is_deep_scan = (
        "100" in range_str or
        range_str in ["crowd", "extended", "large"] or
        student_count > 15
    )
    det_input_size = config.DEEP_SCAN_INPUT_SIZE if is_deep_scan else config.DETECTION_INPUT_SIZE
    range_label = "100 Meters (Extended Crowd Mode)" if is_deep_scan else "50 Meters (Standard Room)"
    distance_meters = 100 if is_deep_scan else 50

    # Step 3: SCRFD Multi-Face Detection
    t_det_0 = time.perf_counter()
    all_detected_faces = pipeline.detector.detect(
        img,
        threshold=config.FACE_DETECTION_THRESHOLD,
        input_size=det_input_size
    )
    detection_time = time.perf_counter() - t_det_0

    total_detected = len(all_detected_faces)
    print(f"[CampusAI Biometrics] Detected faces in classroom photo: {total_detected}")

    if total_detected == 0:
        return {
            "success": "No faces detected in photo.",
            "faces_detected": 0,
            "recognized": [],
            "recognized_count": 0,
            "unknown_faces": 0,
            "rejected_faces": [],
            "rejected_count": 0,
            "duplicate_removed": 0,
            "attendance_marked": 0,
            "detection_range": range_label,
            "distance_meters": distance_meters,
            "annotated_image": None,
            "timings": {
                "detection_sec": round(detection_time, 3),
                "total_sec": round(time.perf_counter() - t_start, 3)
            }
        }

    # Step 4: Face Quality Filtering
    t_qual_0 = time.perf_counter()
    valid_faces: List[DetectedFace] = []
    rejected_faces: List[Tuple[DetectedFace, QualityCheckResult]] = []

    for face in all_detected_faces:
        q_res = pipeline.quality_filter.evaluate(img, face)
        if q_res.is_valid:
            valid_faces.append(face)
        else:
            rejected_faces.append((face, q_res))
    quality_time = time.perf_counter() - t_qual_0

    # Step 5: Feature Extraction & Class-Scoped Matching
    t_match_0 = time.perf_counter()
    match_results: List[MatchResult] = []
    h_img, w_img = img.shape[:2]

    for face in valid_faces:
        # Extract 512-d ArcFace embedding
        emb_512 = pipeline.recognizer.extract_embedding(img, face.landmarks)

        # Extract 128-d dlib encoding from SCRFD bounding box
        top, right, bottom, left = int(face.bbox[1]), int(face.bbox[2]), int(face.bbox[3]), int(face.bbox[0])
        box = (max(0, top), min(w_img, right), min(h_img, bottom), max(0, left))
        dlib_encs = face_recognition.face_encodings(img_rgb, [box])
        enc_128 = dlib_encs[0] if dlib_encs else None

        # Compare ONLY against the loaded class gallery
        match = matcher.match_face(emb_512=emb_512, enc_128=enc_128)
        match_results.append(match)

        if match.is_recognized:
            print(f"[CampusAI Biometrics] RECOGNIZED -> Student ID: {match.student_id}, Name: {match.student_name}, Class ID: {match.class_id}, Distance/Sim: {match.distance}/{match.similarity} (Confidence: {match.confidence_pct}%) via {match.model_type}")
        else:
            print(f"[CampusAI Biometrics] UNKNOWN face detected in Class {class_id} (Best score: distance={match.distance}, sim={match.similarity})")

    matching_time = time.perf_counter() - t_match_0

    # Step 6: Deduplication and Attendance Recording
    t_db_0 = time.perf_counter()
    from app import Attendance, india_now

    today = india_now().date()
    current_time = india_now().time()

    recognized_by_student_id: Dict[int, Dict[str, Any]] = {}
    duplicate_count = 0
    unknown_count = 0

    for idx, match in enumerate(match_results):
        if match.is_recognized:
            sid = match.student_id
            if sid in recognized_by_student_id:
                duplicate_count += 1
                if match.confidence_pct > recognized_by_student_id[sid]['confidence']:
                    recognized_by_student_id[sid]['confidence'] = match.confidence_pct
                    recognized_by_student_id[sid]['similarity'] = match.similarity
                    recognized_by_student_id[sid]['distance'] = match.distance
            else:
                recognized_by_student_id[sid] = {
                    'student_id': sid,
                    'name': match.student_name,
                    'roll_number': match.roll_number,
                    'confidence': match.confidence_pct,
                    'similarity': match.similarity,
                    'distance': match.distance,
                    'model_type': match.model_type
                }
        else:
            unknown_count += 1

    # Persist attendance records to database
    final_recognized_list = []
    new_marked_count = 0

    for sid, stud_data in recognized_by_student_id.items():
        # Check if already present today
        query = Attendance.query.filter_by(
            student_id=sid,
            date=today
        )
        if subject_id:
            query = query.filter_by(subject_id=subject_id)

        existing = query.first()
        if not existing:
            new_att = Attendance(
                student_id=sid,
                class_id=int(class_id),
                subject_id=subject_id,
                date=today,
                time=current_time,
                status='present'
            )
            db_session.add(new_att)
            status_str = 'present'
            new_marked_count += 1
        else:
            status_str = 'already present' if existing.status == 'present' else existing.status

        final_recognized_list.append({
            'student_id': sid,
            'name': stud_data['name'],
            'roll_number': stud_data['roll_number'],
            'status': status_str,
            'confidence': stud_data['confidence'],
            'similarity': stud_data['similarity'],
            'distance': stud_data['distance'],
            'model_type': stud_data['model_type']
        })

    if new_marked_count > 0:
        db_session.commit()

    db_time = time.perf_counter() - t_db_0

    # Print Attendance Summary Log
    print(f"\n[CampusAI Biometrics] Attendance Summary for Class ID: {class_id}")
    print(f"[CampusAI Biometrics] Total Detected: {total_detected}")
    print(f"[CampusAI Biometrics] Recognized: {len(final_recognized_list)}")
    print(f"[CampusAI Biometrics] Unknown: {unknown_count}")
    print(f"[CampusAI Biometrics] Low Quality Rejected: {len(rejected_faces)}")
    print(f"[CampusAI Biometrics] Duplicates Removed: {duplicate_count}")
    print(f"[CampusAI Biometrics] Attendance Marked in DB: {new_marked_count}\n")

    # Step 7: Annotated Visual Image
    annotated_b64 = draw_visual_annotations(img, valid_faces, match_results, rejected_faces)
    total_time = time.perf_counter() - t_start

    # Format rejected faces breakdown
    rejected_summary = [
        {
            "bbox": [int(b) for b in face.bbox],
            "reason": q_res.reason,
            "metrics": q_res.metrics
        }
        for face, q_res in rejected_faces
    ]

    return {
        "success": f"Attendance marked for {len(final_recognized_list)} students",
        "faces_detected": total_detected,
        "recognized": final_recognized_list,
        "recognized_count": len(final_recognized_list),
        "unknown_faces": unknown_count,
        "rejected_faces": rejected_summary,
        "rejected_count": len(rejected_faces),
        "duplicate_removed": duplicate_count,
        "attendance_marked": len(final_recognized_list),
        "detection_range": range_label,
        "distance_meters": distance_meters,
        "annotated_image": annotated_b64,
        "timings": {
            "load_sec": round(load_time, 3),
            "detection_sec": round(detection_time, 3),
            "quality_sec": round(quality_time, 3),
            "matching_sec": round(matching_time, 3),
            "db_sec": round(db_time, 3),
            "total_sec": round(total_time, 3)
        }
    }

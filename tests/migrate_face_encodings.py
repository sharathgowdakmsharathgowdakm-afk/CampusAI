"""
CampusAI Biometric Migration & Re-registration Engine
Converts existing student face images into new ArcFace 512-d embeddings using SCRFD.
Preserves all legacy data without deletion.
"""
import os
import glob
from datetime import datetime
from typing import Dict, Any, List

from face_api.pipeline import get_pipeline, decode_image
from face_api import config

def run_face_migration(app=None, organization_id: int = None) -> Dict[str, Any]:
    """
    Scans students and regenerates ArcFace embeddings for all available source images.
    Returns migration statistics breakdown.
    """
    if app is None:
        from app import app as flask_app
        app = flask_app

    pipeline = get_pipeline()
    stats = {
        "total_students": 0,
        "already_arcface": 0,
        "successfully_converted": 0,
        "missing_image": 0,
        "invalid_image": 0,
        "details": []
    }

    with app.app_context():
        from app import db, Student, FaceEncoding

        query = Student.query
        if organization_id:
            query = query.filter_by(organization_id=int(organization_id))
        students = query.all()

        stats["total_students"] = len(students)
        uploads_dir = os.path.join(config.BASE_DIR, "uploads")

        for student in students:
            # Check if student already has a 512-d ArcFace embedding
            existing_encs = FaceEncoding.query.filter_by(student_id=student.id).all()
            has_arcface = any(
                e.encoding_data and isinstance(e.encoding_data, list) and len(e.encoding_data) == config.EMBEDDING_DIM
                for e in existing_encs
            )

            if has_arcface:
                stats["already_arcface"] += 1
                stats["details"].append({
                    "student_id": student.id,
                    "name": student.name,
                    "roll_number": student.roll_number,
                    "status": "already_converted"
                })
                continue

            # Search for candidate face image for this student
            candidate_images = []
            # 1. Named patterns in uploads: student_<id>.*, <roll_number>.*
            for ext in ['jpg', 'jpeg', 'png', 'JPG', 'JPEG', 'PNG']:
                p1 = os.path.join(uploads_dir, f"student_{student.id}.{ext}")
                p2 = os.path.join(uploads_dir, f"{student.roll_number}.{ext}")
                p3 = os.path.join(uploads_dir, f"student_{student.id}_*.{ext}")
                if os.path.exists(p1): candidate_images.append(p1)
                if os.path.exists(p2): candidate_images.append(p2)
                candidate_images.extend(glob.glob(p3))

            # Only use images explicitly mapped to student ID or roll number

            if not candidate_images:
                stats["missing_image"] += 1
                stats["details"].append({
                    "student_id": student.id,
                    "name": student.name,
                    "roll_number": student.roll_number,
                    "status": "missing_image",
                    "note": "No source photo found. Student should register via webcam/upload."
                })
                continue

            # Process the first valid candidate image
            success_for_student = False
            for img_path in candidate_images:
                try:
                    img = decode_image(img_path)
                    faces = pipeline.detector.detect(img)
                    if not faces:
                        continue

                    # Filter quality
                    best_face = None
                    for f in faces:
                        q = pipeline.quality_filter.evaluate(img, f)
                        if q.is_valid:
                            best_face = f
                            break

                    if not best_face:
                        continue

                    # Extract ArcFace embedding
                    emb = pipeline.recognizer.extract_embedding(img, best_face.landmarks)
                    new_rec = FaceEncoding(
                        student_id=student.id,
                        encoding_path="",
                        encoding_data=emb.tolist(),
                        created_at=datetime.utcnow()
                    )
                    db.session.add(new_rec)
                    db.session.commit()
                    success_for_student = True
                    break
                except Exception as err:
                    continue

            if success_for_student:
                stats["successfully_converted"] += 1
                stats["details"].append({
                    "student_id": student.id,
                    "name": student.name,
                    "roll_number": student.roll_number,
                    "status": "successfully_converted"
                })
            else:
                stats["invalid_image"] += 1
                stats["details"].append({
                    "student_id": student.id,
                    "name": student.name,
                    "roll_number": student.roll_number,
                    "status": "invalid_image",
                    "note": "Face could not be clearly extracted or failed quality check."
                })

        # Invalidate cache so new embeddings are active immediately
        pipeline.embedding_store.invalidate_cache(organization_id=organization_id)

    return stats

def print_migration_report(stats: Dict[str, Any]):
    print("\n" + "=" * 50)
    print(" CampusAI Face Data Migration Report")
    print("=" * 50)
    print(f"Total students:         {stats['total_students']}")
    print(f"Already ArcFace:        {stats['already_arcface']}")
    print(f"Successfully converted: {stats['successfully_converted']}")
    print(f"Missing image:          {stats['missing_image']}")
    print(f"Invalid image:          {stats['invalid_image']}")
    print("=" * 50)

if __name__ == "__main__":
    import sys
    org_id = int(sys.argv[1]) if len(sys.argv) > 1 else None
    results = run_face_migration(organization_id=org_id)
    print_migration_report(results)

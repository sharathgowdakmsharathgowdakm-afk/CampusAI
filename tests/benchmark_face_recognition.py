"""
CampusAI Face Recognition Benchmark Utility
Tests SCRFD detection, ArcFace embedding, and similarity search across
classroom crowd sizes: 10, 25, 50, 75, and 100 faces.
Measures real processing times and recognition statistics.
"""
import os
import time
from typing import Tuple, List, Dict
import cv2
import numpy as np

from face_api.pipeline import get_pipeline
from face_api.matcher import NumPyCosineMatcher
from face_api import config

def build_composite_classroom(face_img: np.ndarray, count: int, canvas_size=(1920, 1080)) -> Tuple[np.ndarray, int]:
    """
    Constructs a synthetic classroom image by tiling face samples across rows and columns.
    Adds slight variations in scale, lighting, and placement to simulate real classroom conditions.
    """
    canvas = np.full((canvas_size[1], canvas_size[0], 3), 220, dtype=np.uint8)
    # Add subtle classroom background gradient
    for y in range(canvas_size[1]):
        v = int(210 + 35 * (y / canvas_size[1]))
        canvas[y, :] = (v, v, v)

    # Calculate grid dimensions
    cols = int(np.ceil(np.sqrt(count * 1.6)))
    rows = int(np.ceil(count / cols))

    cell_w = canvas_size[0] // (cols + 1)
    cell_h = canvas_size[1] // (rows + 1)

    placed = 0
    rng = np.random.RandomState(42)

    for r in range(rows):
        for c in range(cols):
            if placed >= count:
                break

            center_x = int((c + 1) * cell_w + rng.randint(-15, 15))
            center_y = int((r + 1) * cell_h + rng.randint(-15, 15))

            # Target face size (e.g., 65-110px simulating classroom distance)
            target_size = rng.randint(70, 115)
            scaled_face = cv2.resize(face_img, (target_size, target_size))

            # Slight lighting variation
            bright_factor = rng.uniform(0.85, 1.15)
            scaled_face = np.clip(scaled_face * bright_factor, 0, 255).astype(np.uint8)

            fh, fw = scaled_face.shape[:2]
            x1 = max(0, center_x - fw // 2)
            y1 = max(0, center_y - fh // 2)
            x2 = min(canvas_size[0], x1 + fw)
            y2 = min(canvas_size[1], y1 + fh)

            crop_w = x2 - x1
            crop_h = y2 - y1
            if crop_w > 0 and crop_h > 0:
                canvas[y1:y2, x1:x2] = scaled_face[:crop_h, :crop_w]
                placed += 1

    return canvas, placed

def run_benchmarks():
    print("=" * 65)
    print(" CampusAI SCRFD + ArcFace Real Benchmark Suite")
    print("=" * 65)

    pipeline = get_pipeline()
    diag = pipeline.get_diagnostics()
    print(f"Device: {diag['inference_device']} | Detector: {diag['face_detector']} | Recognizer: {diag['face_recognizer']}")
    print("-" * 65)

    # Load source face image
    sample_path = os.path.join(config.BASE_DIR, "uploads", "face.jpg")
    if not os.path.exists(sample_path):
        sample_path = os.path.join(config.BASE_DIR, "uploads", "face_0.jpg")

    source_face = cv2.imread(sample_path)
    if source_face is None:
        # Fallback to creating a test face pattern
        source_face = np.full((160, 160, 3), 180, dtype=np.uint8)

    # Crop to just the face region if full body/photo
    initial_dets = pipeline.detector.detect(source_face)
    if initial_dets:
        box = initial_dets[0].bbox
        face_crop = source_face[box[1]:box[3], box[0]:box[2]]
    else:
        face_crop = source_face

    # Warmup inference
    _ = pipeline.detector.detect(cv2.resize(source_face, (640, 640)))

    # Generate reference gallery of 100 students
    reference_embedding = pipeline.recognizer.extract_embedding(source_face, initial_dets[0].landmarks if initial_dets else np.zeros((5, 2)))
    
    gallery_size = 100
    rng = np.random.RandomState(1337)
    gallery_matrix = []
    gallery_metadata = []

    # Student 1 matches the source face
    gallery_matrix.append(reference_embedding)
    gallery_metadata.append({'student_id': 1, 'name': 'Primary Student', 'roll_number': 'CS-001', 'class_id': 1})

    # Other students have synthetic random unit vectors
    for i in range(2, gallery_size + 1):
        v = rng.randn(config.EMBEDDING_DIM).astype(np.float32)
        v /= np.linalg.norm(v)
        gallery_matrix.append(v)
        gallery_metadata.append({'student_id': i, 'name': f'Student {i}', 'roll_number': f'CS-{i:03d}', 'class_id': 1})

    gallery_matrix = np.vstack(gallery_matrix)
    matcher = NumPyCosineMatcher(gallery_matrix, gallery_metadata, threshold=config.FACE_RECOGNITION_THRESHOLD)

    target_face_counts = [10, 25, 50, 75, 100]

    for face_count in target_face_counts:
        # Construct classroom frame
        classroom_frame, actual_placed = build_composite_classroom(face_crop, face_count)

        # 1. Measure SCRFD Detection Time
        t0_det = time.perf_counter()
        detections = pipeline.detector.detect(classroom_frame, input_size=(1280, 1280) if face_count >= 50 else (640, 640))
        detection_time = time.perf_counter() - t0_det

        # Quality filter
        valid_faces = []
        rejected_count = 0
        for f in detections:
            q = pipeline.quality_filter.evaluate(classroom_frame, f)
            if q.is_valid:
                valid_faces.append(f)
            else:
                rejected_count += 1

        # 2. Measure ArcFace Batch Embedding Time
        t0_emb = time.perf_counter()
        if valid_faces:
            landmarks_list = [f.landmarks for f in valid_faces]
            embeddings = pipeline.recognizer.extract_embeddings_batch(classroom_frame, landmarks_list)
        else:
            embeddings = np.empty((0, config.EMBEDDING_DIM), dtype=np.float32)
        embedding_time = time.perf_counter() - t0_emb

        # 3. Measure Similarity Search Time
        t0_search = time.perf_counter()
        match_results = matcher.batch_search(embeddings)
        search_time = time.perf_counter() - t0_search

        total_time = detection_time + embedding_time + search_time

        detected_count = len(detections)
        recognized_count = sum(1 for m in match_results if m.is_recognized)
        unknown_count = len(valid_faces) - recognized_count

        print(f"Faces: {actual_placed}")
        print(f"Detection time: {detection_time:.2f} sec")
        print(f"Embedding time: {embedding_time:.2f} sec")
        print(f"Search time:    {search_time:.4f} sec")
        print(f"Total:          {total_time:.2f} sec")
        print(f"Detected:       {detected_count}")
        print(f"Recognized:     {recognized_count}")
        print(f"Unknown:        {unknown_count}")
        if rejected_count > 0:
            print(f"Low Quality:    {rejected_count}")
        print("-" * 65)

if __name__ == "__main__":
    run_benchmarks()

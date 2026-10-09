"""
Multi-Tenant & Class-Wise Embedding Store
Manages, caches, and retrieves face representations strictly scoped by:
    organization_id -> class_id -> student_id -> registered face encodings

Guarantees that:
1. Students from other classes are never included in the candidate gallery.
2. Both existing 128-d dlib encodings (.pkl files and JSON data) and 512-d ArcFace embeddings are loaded.
3. Informative server-side debug logs are printed for every load operation.
"""
import os
import pickle
import threading
import numpy as np
from typing import Dict, List, Optional, Tuple, Any
from . import config
from .matcher import NumPyCosineMatcher, ClassScopedGalleryMatcher

class CachedGallery:
    """Stores in-memory class gallery matcher and timestamp."""
    __slots__ = ('matcher', 'timestamp')

    def __init__(self, matcher: ClassScopedGalleryMatcher, timestamp: float):
        self.matcher = matcher
        self.timestamp = timestamp


class EmbeddingStore:
    """
    Organization & Class-Scoped Face Embedding Repository.
    Loads registered vectors from database and provides fast cached class matchers.
    """
    def __init__(self):
        self._cache: Dict[Tuple[int, Optional[int]], CachedGallery] = {}
        self._lock = threading.Lock()

    def invalidate_cache(self, organization_id: Optional[int] = None, class_id: Optional[int] = None):
        """Invalidate cached galleries for a specific class, organization, or all."""
        with self._lock:
            if organization_id is None:
                self._cache.clear()
            elif class_id is None:
                keys_to_delete = [k for k in self._cache.keys() if k[0] == organization_id]
                for k in keys_to_delete:
                    del self._cache[k]
            else:
                key = (int(organization_id), int(class_id))
                if key in self._cache:
                    del self._cache[key]

    def get_matcher(
        self,
        db_session,
        organization_id: int,
        class_id: Optional[int] = None,
        force_reload: bool = False
    ) -> ClassScopedGalleryMatcher:
        """
        Get an organization- and class-scoped matcher.
        Guarantees that face recognition only searches students belonging to organization_id AND class_id.
        """
        if not organization_id:
            raise ValueError("organization_id is strictly required for embedding lookup.")

        cache_key = (int(organization_id), int(class_id) if class_id is not None else None)

        with self._lock:
            if not force_reload and cache_key in self._cache:
                return self._cache[cache_key].matcher

        # Load from database outside lock
        matcher = self._load_class_gallery_from_db(db_session, organization_id, class_id)

        with self._lock:
            import time
            self._cache[cache_key] = CachedGallery(matcher, time.time())
            return matcher

    def _load_class_gallery_from_db(
        self,
        db_session,
        organization_id: int,
        class_id: Optional[int] = None
    ) -> ClassScopedGalleryMatcher:
        """
        Query DB for students belonging strictly to organization_id AND class_id.
        Loads all existing registered encodings:
        - 128-d dlib arrays stored in .pkl files on disk
        - 128-d dlib arrays stored in JSON columns
        - 512-d ArcFace arrays stored in JSON columns
        """
        from app import Student, FaceEncoding

        # Base query filtered by organization
        query = db_session.query(Student).filter(Student.organization_id == int(organization_id))

        if class_id is not None:
            query = query.filter(Student.class_id == int(class_id))

        students = query.all()

        print(f"\n[CampusAI Biometrics] ========================================")
        print(f"[CampusAI Biometrics] Selected Organization ID: {organization_id}")
        print(f"[CampusAI Biometrics] Selected Class ID: {class_id if class_id is not None else 'ALL'}")
        print(f"[CampusAI Biometrics] Students loaded: {len(students)}")

        # Per-student encoding collectors (keyed by student.id)
        # We collect ALL valid encodings per student, then compute a centroid (mean) for matching.
        # This dramatically improves recognition robustness: individual registrations may vary
        # due to pose/lighting, but the centroid is always closer to any new encoding.
        student_vecs_512: Dict[int, List[np.ndarray]] = {}
        student_vecs_128: Dict[int, List[np.ndarray]] = {}
        student_meta: Dict[int, Dict[str, Any]] = {}

        students_with_encodings = 0
        raw_128_count = 0
        raw_512_count = 0
        skipped_count = 0

        for student in students:
            enc_records = db_session.query(FaceEncoding).filter_by(student_id=student.id).all()
            student_has_encoding = False

            meta_info = {
                'student_id': student.id,
                'name': student.name,
                'roll_number': student.roll_number,
                'class_id': student.class_id,
                'organization_id': student.organization_id
            }

            for face_rec in enc_records:
                # 1. Check encoding_data (JSON list)
                if face_rec.encoding_data and isinstance(face_rec.encoding_data, list):
                    dim = len(face_rec.encoding_data)
                    if dim == config.EMBEDDING_DIM:  # 512-d ArcFace
                        vec = np.array(face_rec.encoding_data, dtype=np.float32)
                        norm = np.linalg.norm(vec)
                        if norm > 1e-6:
                            vec = vec / norm
                            student_vecs_512.setdefault(student.id, []).append(vec)
                            student_meta[student.id] = meta_info
                            student_has_encoding = True
                            raw_512_count += 1
                    elif dim == 128:  # 128-d dlib in JSON
                        vec = np.array(face_rec.encoding_data, dtype=np.float64)
                        student_vecs_128.setdefault(student.id, []).append(vec)
                        student_meta[student.id] = meta_info
                        student_has_encoding = True
                        raw_128_count += 1
                    else:
                        skipped_count += 1
                        print(f"[CampusAI Biometrics] Skipping EncID={face_rec.id} for Student {student.id}: unexpected dim={dim}")

                # 2. Check encoding_path (.pkl file on disk)
                elif face_rec.encoding_path and os.path.exists(face_rec.encoding_path):
                    try:
                        with open(face_rec.encoding_path, 'rb') as f:
                            arr = pickle.load(f)
                        if isinstance(arr, np.ndarray):
                            if arr.shape == (128,):
                                student_vecs_128.setdefault(student.id, []).append(arr.astype(np.float64))
                                student_meta[student.id] = meta_info
                                student_has_encoding = True
                                raw_128_count += 1
                            elif arr.shape == (config.EMBEDDING_DIM,):
                                vec = arr.astype(np.float32)
                                norm = np.linalg.norm(vec)
                                if norm > 1e-6:
                                    vec = vec / norm
                                    student_vecs_512.setdefault(student.id, []).append(vec)
                                    student_meta[student.id] = meta_info
                                    student_has_encoding = True
                                    raw_512_count += 1
                            else:
                                skipped_count += 1
                                print(f"[CampusAI Biometrics] Skipping EncID={face_rec.id} for Student {student.id}: wrong shape {arr.shape}")
                        else:
                            skipped_count += 1
                    except Exception as err:
                        print(f"[CampusAI Biometrics] Warning: Failed to read {face_rec.encoding_path}: {err}")

            if student_has_encoding:
                students_with_encodings += 1
            else:
                print(f"[CampusAI Biometrics] Student ID: {student.id}, Name: {student.name}, Class ID: {student.class_id} -> Face encoding: NOT FOUND")

        # Build centroid gallery: ONE vector per student (mean of all their registrations)
        vectors_512: List[np.ndarray] = []
        meta_512: List[Dict[str, Any]] = []
        vectors_128: List[np.ndarray] = []
        meta_128: List[Dict[str, Any]] = []

        for sid, vecs in student_vecs_512.items():
            centroid = np.mean(vecs, axis=0).astype(np.float32)
            norm = np.linalg.norm(centroid)
            if norm > 1e-6:
                centroid = centroid / norm
            vectors_512.append(centroid)
            meta_512.append(student_meta[sid])

        for sid, vecs in student_vecs_128.items():
            centroid = np.mean(vecs, axis=0).astype(np.float64)
            vectors_128.append(centroid)
            meta_128.append(student_meta[sid])
            n = len(vecs)
            print(f"[CampusAI Biometrics]   Student {sid} ({student_meta[sid]['name']}): {n} dlib encodings -> centroid (norm={np.linalg.norm(centroid):.4f})")

        total_gallery = len(vectors_512) + len(vectors_128)
        print(f"[CampusAI Biometrics] Raw encodings found: {raw_512_count + raw_128_count} (512-d: {raw_512_count}, 128-d: {raw_128_count}, skipped: {skipped_count})")
        print(f"[CampusAI Biometrics] Gallery centroids built: {total_gallery} (512-d: {len(vectors_512)}, 128-d: {len(vectors_128)})")
        print(f"[CampusAI Biometrics] Students with active encodings: {students_with_encodings} / {len(students)}")
        print(f"[CampusAI Biometrics] ========================================\n")

        matrix_512 = np.vstack(vectors_512).astype(np.float32) if vectors_512 else np.empty((0, config.EMBEDDING_DIM), dtype=np.float32)
        matrix_128 = np.vstack(vectors_128).astype(np.float64) if vectors_128 else np.empty((0, 128), dtype=np.float64)

        return ClassScopedGalleryMatcher(
            class_id=int(class_id) if class_id is not None else 0,
            organization_id=int(organization_id),
            matrix_512=matrix_512,
            metadata_512=meta_512,
            matrix_128=matrix_128,
            metadata_128=meta_128,
            threshold_512=config.FACE_RECOGNITION_THRESHOLD,
            tolerance_128=0.55
        )

# Global singleton store instance
embedding_store = EmbeddingStore()

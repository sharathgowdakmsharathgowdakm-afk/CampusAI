"""
Similarity Search and Student Identification
Vectorized similarity comparison against known student face embeddings.
Supports both ArcFace 512-d normalized cosine comparison and dlib 128-d Euclidean distance comparison.
Strictly scoped by organization_id and class_id.
"""
from abc import ABC, abstractmethod
import numpy as np
from typing import List, Dict, Any, Optional, Tuple
from . import config

class MatchResult:
    """Outcome of a similarity search query against the candidate gallery."""
    __slots__ = ('is_recognized', 'student_id', 'student_name', 'roll_number',
                 'class_id', 'similarity', 'confidence_pct', 'distance', 'model_type')

    def __init__(
        self,
        is_recognized: bool,
        student_id: Optional[int] = None,
        student_name: Optional[str] = None,
        roll_number: Optional[str] = None,
        class_id: Optional[int] = None,
        similarity: float = 0.0,
        confidence_pct: float = 0.0,
        distance: float = 1.0,
        model_type: str = "ArcFace"
    ):
        self.is_recognized = is_recognized
        self.student_id = student_id
        self.student_name = student_name
        self.roll_number = roll_number
        self.class_id = class_id
        self.similarity = round(float(similarity), 4)
        self.confidence_pct = round(float(confidence_pct), 1)
        self.distance = round(float(distance), 4)
        self.model_type = model_type

    def to_dict(self) -> dict:
        return {
            'is_recognized': self.is_recognized,
            'student_id': self.student_id,
            'name': self.student_name,
            'roll_number': self.roll_number,
            'class_id': self.class_id,
            'similarity': self.similarity,
            'confidence': self.confidence_pct,
            'distance': self.distance,
            'model_type': self.model_type
        }

class BaseSimilarityMatcher(ABC):
    """Abstract interface for face embedding search backends."""
    @abstractmethod
    def search(self, query_embedding: np.ndarray, threshold: Optional[float] = None) -> MatchResult:
        pass


class NumPyCosineMatcher(BaseSimilarityMatcher):
    """
    High-performance in-memory vectorized similarity matcher for 512-d embeddings.
    Computes dot products on L2-normalized embeddings (cosine similarity).
    """
    def __init__(
        self,
        embeddings_matrix: np.ndarray,
        candidates_metadata: List[Dict[str, Any]],
        threshold: Optional[float] = None
    ):
        self.threshold = threshold if threshold is not None else config.FACE_RECOGNITION_THRESHOLD
        if embeddings_matrix is not None and embeddings_matrix.size > 0 and len(embeddings_matrix.shape) == 2:
            self.matrix = embeddings_matrix.astype(np.float32)
            self.metadata = candidates_metadata
        else:
            self.matrix = np.empty((0, config.EMBEDDING_DIM), dtype=np.float32)
            self.metadata = []

    def is_empty(self) -> bool:
        return self.matrix.shape[0] == 0

    def search(self, query_embedding: np.ndarray, threshold: Optional[float] = None) -> MatchResult:
        thresh = threshold if threshold is not None else self.threshold
        if self.is_empty() or query_embedding is None:
            return MatchResult(is_recognized=False, similarity=0.0, confidence_pct=0.0, distance=1.0)

        sims = np.dot(self.matrix, query_embedding)
        best_idx = int(np.argmax(sims))
        best_sim = float(sims[best_idx])
        cosine_dist = max(0.0, 1.0 - best_sim)

        if best_sim >= thresh:
            cand = self.metadata[best_idx]
            conf = min(99.9, round(60.0 + (best_sim - thresh) / max(0.01, 1.0 - thresh) * 39.9, 1))
            return MatchResult(
                is_recognized=True,
                student_id=cand.get('student_id'),
                student_name=cand.get('name'),
                roll_number=cand.get('roll_number'),
                class_id=cand.get('class_id'),
                similarity=best_sim,
                confidence_pct=conf,
                distance=cosine_dist,
                model_type="ArcFace-512"
            )
        else:
            return MatchResult(
                is_recognized=False,
                similarity=best_sim,
                confidence_pct=0.0,
                distance=cosine_dist,
                model_type="ArcFace-512"
            )

    def batch_search(self, query_embeddings: np.ndarray, threshold: Optional[float] = None) -> List[MatchResult]:
        thresh = threshold if threshold is not None else self.threshold
        if self.is_empty() or query_embeddings.shape[0] == 0:
            return [MatchResult(is_recognized=False, similarity=0.0, confidence_pct=0.0) for _ in range(query_embeddings.shape[0])]

        sim_matrix = np.dot(query_embeddings, self.matrix.T)
        best_indices = np.argmax(sim_matrix, axis=1)
        best_scores = sim_matrix[np.arange(query_embeddings.shape[0]), best_indices]

        results: List[MatchResult] = []
        for i, sim_score in enumerate(best_scores):
            sim_val = float(sim_score)
            cosine_dist = max(0.0, 1.0 - sim_val)
            if sim_val >= thresh:
                idx = int(best_indices[i])
                cand = self.metadata[idx]
                conf = min(99.9, round(60.0 + (sim_val - thresh) / max(0.01, 1.0 - thresh) * 39.9, 1))
                results.append(MatchResult(
                    is_recognized=True,
                    student_id=cand.get('student_id'),
                    student_name=cand.get('name'),
                    roll_number=cand.get('roll_number'),
                    class_id=cand.get('class_id'),
                    similarity=sim_val,
                    confidence_pct=conf,
                    distance=cosine_dist,
                    model_type="ArcFace-512"
                ))
            else:
                results.append(MatchResult(
                    is_recognized=False,
                    similarity=sim_val,
                    confidence_pct=0.0,
                    distance=cosine_dist,
                    model_type="ArcFace-512"
                ))

        return results


class ClassScopedGalleryMatcher:
    """
    Class-specific Matcher.
    Holds both 512-d ArcFace and 128-d dlib registered encodings strictly for one class_id.
    Compares query faces ONLY against students in this class.
    """
    def __init__(
        self,
        class_id: int,
        organization_id: int,
        matrix_512: np.ndarray,
        metadata_512: List[Dict[str, Any]],
        matrix_128: np.ndarray,
        metadata_128: List[Dict[str, Any]],
        threshold_512: float = 0.42,
        tolerance_128: float = 0.48
    ):
        self.class_id = int(class_id)
        self.organization_id = int(organization_id)
        self.threshold_512 = threshold_512
        self.tolerance_128 = tolerance_128

        self.matcher_512 = NumPyCosineMatcher(matrix_512, metadata_512, threshold=threshold_512)
        self.matrix_128 = matrix_128.astype(np.float64) if (matrix_128 is not None and matrix_128.size > 0) else np.empty((0, 128), dtype=np.float64)
        self.metadata_128 = metadata_128 or []

        # For backwards compatibility attribute inspection
        self.matrix = self.matcher_512.matrix
        self.metadata = metadata_512 + metadata_128

    def is_empty(self) -> bool:
        return self.matcher_512.is_empty() and (self.matrix_128.shape[0] == 0)

    def count(self) -> int:
        return self.matcher_512.matrix.shape[0] + self.matrix_128.shape[0]

    def match_face(
        self,
        emb_512: Optional[np.ndarray] = None,
        enc_128: Optional[np.ndarray] = None
    ) -> MatchResult:
        """
        Compare query face representations against class gallery.
        Evaluates 512-d ArcFace and/or 128-d dlib representations.
        """
        if self.is_empty():
            return MatchResult(is_recognized=False, similarity=0.0, confidence_pct=0.0, distance=1.0)

        best_result: Optional[MatchResult] = None

        # 1. Evaluate 512-d ArcFace
        if emb_512 is not None and not self.matcher_512.is_empty():
            res_512 = self.matcher_512.search(emb_512)
            if res_512.is_recognized:
                best_result = res_512

        # 2. Evaluate 128-d dlib
        if enc_128 is not None and self.matrix_128.shape[0] > 0:
            dists = np.linalg.norm(self.matrix_128 - enc_128, axis=1)
            best_idx = int(np.argmin(dists))
            best_dist = float(dists[best_idx])
            sim_128 = max(0.0, 1.0 - best_dist)
            conf_128 = max(0.0, min(99.9, round((1.0 - best_dist / self.tolerance_128) * 40.0 + 60.0, 1))) if best_dist <= self.tolerance_128 else 0.0

            cand = self.metadata_128[best_idx]
            print(f"[CampusAI Biometrics] dlib-128 match: best={cand.get('name')} (S{cand.get('student_id')}), "
                  f"dist={best_dist:.4f}, tol={self.tolerance_128}, "
                  f"{'PASS' if best_dist <= self.tolerance_128 else 'FAIL'}")

            if best_dist <= self.tolerance_128:
                cand = self.metadata_128[best_idx]
                res_128 = MatchResult(
                    is_recognized=True,
                    student_id=cand.get('student_id'),
                    student_name=cand.get('name'),
                    roll_number=cand.get('roll_number'),
                    class_id=cand.get('class_id'),
                    similarity=round(sim_128, 4),
                    confidence_pct=conf_128,
                    distance=round(best_dist, 4),
                    model_type="dlib-128"
                )
                if best_result is None or res_128.confidence_pct > best_result.confidence_pct:
                    best_result = res_128
            elif best_result is None:
                best_result = MatchResult(
                    is_recognized=False,
                    similarity=round(sim_128, 4),
                    confidence_pct=0.0,
                    distance=round(best_dist, 4),
                    model_type="dlib-128"
                )

        if best_result is not None:
            return best_result

        return MatchResult(is_recognized=False, similarity=0.0, confidence_pct=0.0, distance=1.0)

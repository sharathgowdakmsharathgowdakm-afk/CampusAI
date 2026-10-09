"""
CampusAI Face Recognition Engine (SCRFD + ArcFace)
"""
from . import config
from .detector import SCRFDDetector, DetectedFace
from .quality import FaceQualityFilter, QualityCheckResult
from .recognizer import ArcFaceRecognizer
from .matcher import BaseSimilarityMatcher, NumPyCosineMatcher, MatchResult
from .embedding_store import EmbeddingStore, embedding_store
from .pipeline import FaceRecognitionPipeline, get_pipeline, decode_image, draw_visual_annotations
from .attendance import process_classroom_attendance, register_single_student_face

__all__ = [
    'config',
    'SCRFDDetector',
    'DetectedFace',
    'FaceQualityFilter',
    'QualityCheckResult',
    'ArcFaceRecognizer',
    'BaseSimilarityMatcher',
    'NumPyCosineMatcher',
    'MatchResult',
    'EmbeddingStore',
    'embedding_store',
    'FaceRecognitionPipeline',
    'get_pipeline',
    'decode_image',
    'draw_visual_annotations',
    'process_classroom_attendance',
    'register_single_student_face'
]

"""
Face Recognition Pipeline Singleton and Diagnostic Utilities
Coordinates SCRFD detection, quality filtering, ArcFace embedding extraction, and image visualization.
"""
import os
import base64
import time
import cv2
import numpy as np
import onnxruntime as ort
from typing import Dict, Any, List, Optional, Tuple, Union

from . import config
from .detector import SCRFDDetector, DetectedFace
from .quality import FaceQualityFilter, QualityCheckResult
from .recognizer import ArcFaceRecognizer
from .matcher import MatchResult
from .embedding_store import embedding_store

class FaceRecognitionPipeline:
    """
    Singleton service coordinator for CampusAI Biometrics.
    Loads models once at startup and reuses sessions across requests.
    """
    def __init__(self):
        self._detect_hardware()
        print(f"[CampusAI Biometrics] Initializing SCRFD on {self.active_device}...")
        self.detector = SCRFDDetector(providers=self.active_providers)
        print(f"[CampusAI Biometrics] Initializing ArcFace on {self.active_device}...")
        self.recognizer = ArcFaceRecognizer(providers=self.active_providers)
        self.quality_filter = FaceQualityFilter()
        self.embedding_store = embedding_store
        self.is_ready = True
        print("[CampusAI Biometrics] Pipeline initialized successfully.")

    def _detect_hardware(self):
        available = ort.get_available_providers()
        if 'CUDAExecutionProvider' in available:
            self.active_providers = ['CUDAExecutionProvider', 'CPUExecutionProvider']
            self.active_device = "GPU (CUDA)"
        else:
            self.active_providers = ['CPUExecutionProvider']
            self.active_device = "CPU"

    def get_diagnostics(self, db_session=None) -> Dict[str, Any]:
        """Return diagnostic metrics for admin dashboard."""
        registered_count = 0
        if db_session is not None:
            try:
                from app import FaceEncoding
                # Count total 512-d ArcFace embeddings
                encs = db_session.query(FaceEncoding.encoding_data).all()
                for (d,) in encs:
                    if d and isinstance(d, list) and len(d) == config.EMBEDDING_DIM:
                        registered_count += 1
            except Exception:
                pass

        return {
            "face_detector": "SCRFD (det_10g)",
            "face_recognizer": "ArcFace (w600k_r50)",
            "inference_device": self.active_device,
            "providers": self.active_providers,
            "models_loaded": self.is_ready,
            "registered_arcface_embeddings": registered_count,
            "detection_threshold": config.FACE_DETECTION_THRESHOLD,
            "recognition_threshold": config.FACE_RECOGNITION_THRESHOLD,
            "min_face_size": config.MIN_FACE_SIZE
        }

# Global Singleton Instance
_pipeline_instance: Optional[FaceRecognitionPipeline] = None

def get_pipeline() -> FaceRecognitionPipeline:
    global _pipeline_instance
    if _pipeline_instance is None:
        _pipeline_instance = FaceRecognitionPipeline()
    return _pipeline_instance

def decode_image(image_input: Union[str, bytes, np.ndarray]) -> np.ndarray:
    """
    Convert base64 string, file path, or bytes into an OpenCV BGR numpy array.
    """
    if isinstance(image_input, np.ndarray):
        return image_input

    if isinstance(image_input, bytes):
        nparr = np.frombuffer(image_input, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError("Failed to decode image from byte buffer.")
        return img

    if isinstance(image_input, str):
        # Base64 string check
        if image_input.startswith("data:image") or len(image_input) > 500:
            b64_data = image_input
            if "," in b64_data:
                b64_data = b64_data.split(",", 1)[1]
            raw_bytes = base64.b64decode(b64_data)
            nparr = np.frombuffer(raw_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if img is None:
                raise ValueError("Failed to decode image from base64 string.")
            return img
        elif os.path.exists(image_input):
            img = cv2.imread(image_input)
            if img is None:
                raise ValueError(f"Failed to read image from path: {image_input}")
            return img

    raise ValueError("Invalid image input format.")

def draw_visual_annotations(
    image: np.ndarray,
    valid_faces: List[DetectedFace],
    match_results: List[MatchResult],
    rejected_faces: List[Tuple[DetectedFace, QualityCheckResult]]
) -> str:
    """
    Draw color-coded bounding boxes and badges on detected faces:
    - Green: Recognized Student (Name & Match %)
    - Amber/Orange: Unknown Face
    - Red/Gray dashed: Rejected / Low Quality Face (Reason)
    Returns base64 JPEG data URL for display in UI.
    """
    annotated = image.copy()
    h, w = annotated.shape[:2]

    # Responsive font scale based on image dimensions
    base_dim = max(h, w)
    font_scale = max(0.4, min(0.85, base_dim / 1400.0))
    line_thick = max(1, int(round(base_dim / 600.0)))

    # 1. Draw Rejected / Low Quality Faces (Red / Gray)
    for face, qres in rejected_faces:
        x1, y1, x2, y2 = face.bbox
        # Red/Gray box
        cv2.rectangle(annotated, (x1, y1), (x2, y2), (80, 80, 220), line_thick)
        label = f"Low Quality: {qres.reason}"
        # Small background badge
        t_size = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, font_scale * 0.8, 1)[0]
        badge_y1 = max(0, y1 - t_size[1] - 6)
        cv2.rectangle(annotated, (x1, badge_y1), (x1 + t_size[0] + 8, y1), (40, 40, 180), -1)
        cv2.putText(annotated, label, (x1 + 4, y1 - 4), cv2.FONT_HERSHEY_SIMPLEX, font_scale * 0.8, (255, 255, 255), 1, cv2.LINE_AA)

    # 2. Draw Valid Faces (Recognized or Unknown)
    for face, match in zip(valid_faces, match_results):
        x1, y1, x2, y2 = face.bbox
        if match.is_recognized:
            # Green box for recognized students
            box_color = (46, 204, 113)  # Bright Green in BGR
            badge_color = (39, 174, 96)
            label = f"{match.student_name} ({match.confidence_pct}%)"
            icon_char = "[OK]"
        else:
            # Amber / Yellow box for unknown faces
            box_color = (0, 165, 255)  # Orange in BGR
            badge_color = (0, 140, 230)
            label = "? Unknown"
            icon_char = "[?]"

        cv2.rectangle(annotated, (x1, y1), (x2, y2), box_color, line_thick)

        # Label background
        t_size = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, font_scale, 1)[0]
        badge_y1 = max(0, y1 - t_size[1] - 8)
        cv2.rectangle(annotated, (x1, badge_y1), (x1 + t_size[0] + 10, y1), badge_color, -1)
        cv2.putText(annotated, label, (x1 + 5, y1 - 4), cv2.FONT_HERSHEY_SIMPLEX, font_scale, (255, 255, 255), 1, cv2.LINE_AA)

    # Encode as JPEG
    encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 88]
    _, buf = cv2.imencode('.jpg', annotated, encode_param)
    b64_str = base64.b64encode(buf).decode('utf-8')
    return f"data:image/jpeg;base64,{b64_str}"

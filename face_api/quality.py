"""
Face Quality Filtering Module
Validates detected faces against resolution, blur, lighting, visibility, and pose thresholds.
"""
import cv2
import numpy as np
from typing import Tuple, Optional, Dict, Any
from . import config
from .detector import DetectedFace

class QualityCheckResult:
    """Stores the outcome of face quality filtering."""
    __slots__ = ('is_valid', 'reason', 'metrics')

    def __init__(self, is_valid: bool, reason: Optional[str] = None, metrics: Optional[Dict[str, Any]] = None):
        self.is_valid = is_valid
        self.reason = reason
        self.metrics = metrics or {}

    def to_dict(self) -> dict:
        return {
            'is_valid': self.is_valid,
            'reason': self.reason,
            'metrics': self.metrics
        }

class FaceQualityFilter:
    """
    Evaluates face crops for biometric suitability before ArcFace embedding extraction.
    Ensures poor-quality or cropped detections do not pollute similarity search or skew attendance.
    """
    def __init__(
        self,
        min_size: Optional[int] = None,
        blur_threshold: Optional[float] = None,
        min_brightness: Optional[float] = None,
        max_brightness: Optional[float] = None,
        max_yaw_ratio: Optional[float] = None,
        max_roll_deg: Optional[float] = None
    ):
        self.min_size = min_size or config.MIN_FACE_SIZE
        self.blur_threshold = blur_threshold or config.QUALITY_BLUR_THRESHOLD
        self.min_brightness = min_brightness or config.QUALITY_MIN_BRIGHTNESS
        self.max_brightness = max_brightness or config.QUALITY_MAX_BRIGHTNESS
        self.max_yaw_ratio = max_yaw_ratio or config.MAX_YAW_RATIO
        self.max_roll_deg = max_roll_deg or config.MAX_ROLL_DEGREES

    def evaluate(self, image: np.ndarray, face: DetectedFace) -> QualityCheckResult:
        """
        Evaluate a detected face in the context of the full frame.
        Returns QualityCheckResult with boolean status, rejection reason (if rejected), and metrics.
        """
        metrics = {
            'width': face.width,
            'height': face.height,
            'confidence': round(face.score, 4)
        }

        # 1. Detection Confidence Check
        if face.score < config.FACE_DETECTION_THRESHOLD:
            return QualityCheckResult(False, "Low detection confidence", metrics)

        # 2. Bounding Box Size Check
        if face.width < self.min_size or face.height < self.min_size:
            return QualityCheckResult(False, "Face too small", metrics)

        # 3. Extract Face Crop
        h, w = image.shape[:2]
        x1, y1, x2, y2 = face.bbox
        x1_c, y1_c = max(0, x1), max(0, y1)
        x2_c, y2_c = min(w, x2), min(h, y2)

        crop_w = x2_c - x1_c
        crop_h = y2_c - y1_c
        if crop_w <= 4 or crop_h <= 4:
            return QualityCheckResult(False, "Low image quality", metrics)

        # Border / Visibility check: if face is severely cut off at frame edges
        visible_ratio = (crop_w * crop_h) / max(1, face.width * face.height)
        metrics['visible_ratio'] = round(visible_ratio, 3)
        if visible_ratio < 0.60:
            return QualityCheckResult(False, "Low image quality", metrics)

        face_crop = image[y1_c:y2_c, x1_c:x2_c]
        if face_crop.size == 0:
            return QualityCheckResult(False, "Low image quality", metrics)

        # Convert crop to grayscale
        if len(face_crop.shape) == 3 and face_crop.shape[2] == 3:
            gray = cv2.cvtColor(face_crop, cv2.COLOR_BGR2GRAY)
        else:
            gray = face_crop

        # 4. Blur / Sharpness Check (Laplacian Variance)
        # Note: scale by face size to avoid penalizing smaller clear faces unduly
        laplacian = cv2.Laplacian(gray, cv2.CV_64F)
        blur_score = float(laplacian.var())
        metrics['blur_score'] = round(blur_score, 2)

        # If face is larger, expected variance is higher; adaptive threshold
        size_scale = max(1.0, min(2.5, face.width / 60.0))
        adjusted_blur_thresh = self.blur_threshold * (1.0 / size_scale)

        if blur_score < adjusted_blur_thresh:
            return QualityCheckResult(False, "Too blurry", metrics)

        # 5. Brightness / Lighting Check (Mean Luminance)
        mean_brightness = float(np.mean(gray))
        metrics['brightness'] = round(mean_brightness, 2)

        if mean_brightness < self.min_brightness or mean_brightness > self.max_brightness:
            return QualityCheckResult(False, "Poor lighting", metrics)

        # 6. Pose / Angle Estimation from 5 Landmarks
        # Landmarks: [0]: left_eye, [1]: right_eye, [2]: nose, [3]: left_mouth, [4]: right_mouth
        kps = face.landmarks
        if kps is not None and kps.shape == (5, 2):
            left_eye = kps[0]
            right_eye = kps[1]
            nose = kps[2]

            # In-plane tilt (Roll)
            dx = right_eye[0] - left_eye[0]
            dy = right_eye[1] - left_eye[1]
            roll_angle = abs(float(np.degrees(np.arctan2(dy, dx))))
            metrics['roll_degrees'] = round(roll_angle, 2)

            if roll_angle > self.max_roll_deg:
                return QualityCheckResult(False, "Extreme face angle", metrics)

            # Yaw estimation: distance from left eye to nose vs right eye to nose
            dist_left = max(1.0, float(np.linalg.norm(nose - left_eye)))
            dist_right = max(1.0, float(np.linalg.norm(nose - right_eye)))
            yaw_ratio = dist_left / dist_right
            metrics['yaw_ratio'] = round(yaw_ratio, 2)

            if yaw_ratio > self.max_yaw_ratio or yaw_ratio < (1.0 / self.max_yaw_ratio):
                return QualityCheckResult(False, "Extreme face angle", metrics)

        # Overall composite quality score (0.0 to 1.0)
        q_conf = min(1.0, face.score)
        q_blur = min(1.0, blur_score / 100.0)
        q_bright = 1.0 - abs(mean_brightness - 128.0) / 128.0
        composite_quality = round(0.4 * q_conf + 0.3 * q_blur + 0.3 * q_bright, 3)
        metrics['quality_score'] = composite_quality

        return QualityCheckResult(True, None, metrics)

"""
CampusAI Face Recognition Configuration
SCRFD + ArcFace Pipeline Settings
"""
import os

# Base paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS_DIR = os.path.join(BASE_DIR, "face_models")

# ONNX Model Paths
DETECTOR_MODEL_PATH = os.environ.get(
    "SCRFD_MODEL_PATH",
    os.path.join(MODELS_DIR, "det_10g.onnx")
)

RECOGNIZER_MODEL_PATH = os.environ.get(
    "ARCFACE_MODEL_PATH",
    os.path.join(MODELS_DIR, "w600k_r50.onnx")
)

# Detection Thresholds
# Minimum confidence required for SCRFD face detection
FACE_DETECTION_THRESHOLD = float(os.environ.get("FACE_DETECTION_THRESHOLD", "0.50"))

# Non-Maximum Suppression (NMS) IoU overlap threshold
NMS_THRESHOLD = float(os.environ.get("NMS_THRESHOLD", "0.40"))

# Minimum face bounding box size (width or height in pixels)
MIN_FACE_SIZE = int(os.environ.get("MIN_FACE_SIZE", "28"))

# Standard detector input resolution (width, height)
DETECTION_INPUT_SIZE = (640, 640)

# High-resolution deep scan mode input size for distant classroom crowds
DEEP_SCAN_INPUT_SIZE = (1280, 1280)

# Maximum image dimension to prevent runaway memory usage
MAX_IMAGE_DIMENSION = 2560

# ArcFace Recognition Settings
# Cosine similarity threshold for ArcFace (embeddings are normalized to unit sphere)
# Values >= threshold indicate a verified match
FACE_RECOGNITION_THRESHOLD = float(os.environ.get("FACE_RECOGNITION_THRESHOLD", "0.48"))

# Embedding vector dimensionality
EMBEDDING_DIM = 512

# ArcFace standard input size
ARCFACE_INPUT_SIZE = (112, 112)

# Quality Filtering Thresholds
# Blur detection: minimum variance of Laplacian
QUALITY_BLUR_THRESHOLD = float(os.environ.get("QUALITY_BLUR_THRESHOLD", "22.0"))

# Lighting / Brightness thresholds (mean grayscale intensity)
QUALITY_MIN_BRIGHTNESS = float(os.environ.get("QUALITY_MIN_BRIGHTNESS", "35.0"))
QUALITY_MAX_BRIGHTNESS = float(os.environ.get("QUALITY_MAX_BRIGHTNESS", "230.0"))

# Pose / Rotation limits (landmark ratios and angles)
# Max eye-to-nose horizontal ratio (yaw estimate)
MAX_YAW_RATIO = float(os.environ.get("MAX_YAW_RATIO", "3.0"))
# Max face tilt angle (roll in degrees)
MAX_ROLL_DEGREES = float(os.environ.get("MAX_ROLL_DEGREES", "45.0"))

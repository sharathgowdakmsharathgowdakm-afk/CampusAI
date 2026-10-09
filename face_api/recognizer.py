"""
ArcFace Face Recognizer Implementation
Generates 512-dimensional normalized face embeddings from aligned crops using ONNX Runtime.
Supports single-face and batch-face inference for high-speed classroom recognition.
"""
import os
import cv2
import numpy as np
import onnxruntime as ort
from typing import List, Optional, Union
from . import config

# Canonical 5-point facial landmark reference coordinates for 112x112 ArcFace alignment
ARCFACE_REFERENCE_LANDMARKS = np.array([
    [38.2946, 51.6963],  # left eye
    [73.5318, 51.5014],  # right eye
    [56.0252, 71.7366],  # nose tip
    [41.5493, 92.3655],  # left mouth corner
    [70.7299, 92.2041]   # right mouth corner
], dtype=np.float32)

def align_face_to_template(img: np.ndarray, landmarks: np.ndarray) -> np.ndarray:
    """
    Align face crop to standard 112x112 ArcFace template using similarity transform.
    Landmarks shape must be (5, 2) in image coordinate space.
    """
    src_pts = landmarks.reshape(5, 2).astype(np.float32)
    M, _ = cv2.estimateAffinePartial2D(src_pts, ARCFACE_REFERENCE_LANDMARKS, method=cv2.LMEDS)

    if M is None:
        # Fallback to simple crop and resize if transform cannot be estimated
        x1 = max(0, int(round(np.min(src_pts[:, 0]))))
        y1 = max(0, int(round(np.min(src_pts[:, 1]))))
        x2 = min(img.shape[1], int(round(np.max(src_pts[:, 0]))))
        y2 = min(img.shape[0], int(round(np.max(src_pts[:, 1]))))
        crop = img[y1:y2, x1:x2]
        if crop.size == 0:
            return np.zeros((112, 112, 3), dtype=np.uint8)
        return cv2.resize(crop, (112, 112))

    aligned = cv2.warpAffine(img, M, (112, 112), flags=cv2.INTER_LINEAR, borderValue=0.0)
    return aligned

class ArcFaceRecognizer:
    """
    ArcFace Biometric Recognizer powered by ONNX Runtime.
    Converts 5-landmark face crops to 512-dimensional L2-normalized embeddings.
    """
    def __init__(self, model_path: Optional[str] = None, providers: Optional[List[str]] = None):
        self.model_path = model_path or config.RECOGNIZER_MODEL_PATH
        if not os.path.exists(self.model_path):
            raise FileNotFoundError(f"ArcFace model file not found at: {self.model_path}")

        available_providers = ort.get_available_providers()
        if providers is None:
            if 'CUDAExecutionProvider' in available_providers:
                providers = ['CUDAExecutionProvider', 'CPUExecutionProvider']
            else:
                providers = ['CPUExecutionProvider']

        opts = ort.SessionOptions()
        opts.log_severity_level = 3
        opts.intra_op_num_threads = max(1, os.cpu_count() or 4)
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

        self.session = ort.InferenceSession(self.model_path, sess_options=opts, providers=providers)
        self.input_name = self.session.get_inputs()[0].name
        self.output_name = self.session.get_outputs()[0].name
        self.providers = self.session.get_providers()
        self.active_provider = self.providers[0] if self.providers else "CPUExecutionProvider"

    def align(self, image: np.ndarray, landmarks: np.ndarray) -> np.ndarray:
        """Align face image using 5 landmarks."""
        return align_face_to_template(image, landmarks)

    def extract_embedding(self, image: np.ndarray, landmarks: np.ndarray) -> np.ndarray:
        """
        Extract a single normalized 512-d embedding vector.
        Returns 1D np.ndarray of shape (512,) float32.
        """
        aligned = self.align(image, landmarks)
        blob = cv2.dnn.blobFromImage(
            aligned,
            scalefactor=1.0 / 127.5,
            size=(112, 112),
            mean=(127.5, 127.5, 127.5),
            swapRB=True
        )
        outs = self.session.run([self.output_name], {self.input_name: blob})
        raw_emb = outs[0][0].astype(np.float32)

        # L2-normalize embedding vector
        norm = np.linalg.norm(raw_emb)
        if norm > 1e-6:
            normalized_emb = raw_emb / norm
        else:
            normalized_emb = raw_emb

        return normalized_emb

    def extract_embeddings_batch(self, image: np.ndarray, list_of_landmarks: List[np.ndarray]) -> np.ndarray:
        """
        Extract normalized 512-d embeddings for multiple faces in a single batched forward pass.
        Returns 2D np.ndarray of shape (N, 512) float32.
        """
        if not list_of_landmarks:
            return np.empty((0, config.EMBEDDING_DIM), dtype=np.float32)

        n = len(list_of_landmarks)
        batch_blob = np.empty((n, 3, 112, 112), dtype=np.float32)

        for i, lm in enumerate(list_of_landmarks):
            aligned = self.align(image, lm)
            # Normalize to [-1.0, 1.0] and convert HWC -> CHW (RGB)
            rgb = cv2.cvtColor(aligned, cv2.COLOR_BGR2RGB).astype(np.float32)
            rgb = (rgb - 127.5) / 127.5
            chw = np.transpose(rgb, (2, 0, 1))
            batch_blob[i] = chw

        outs = self.session.run([self.output_name], {self.input_name: batch_blob})
        embeddings = outs[0].astype(np.float32)  # shape (N, 512)

        # Vectorized row-wise L2 normalization
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        norms = np.maximum(norms, 1e-6)
        normalized_embeddings = embeddings / norms

        return normalized_embeddings

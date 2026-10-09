"""
SCRFD Face Detector Implementation
High-speed multi-face detection using ONNX Runtime with 5-point landmark regression.
"""
import os
import cv2
import numpy as np
import onnxruntime as ort
from typing import List, Dict, Tuple, Optional, Union
from . import config

def distance2bbox(points: np.ndarray, distance: np.ndarray, max_shape: Optional[Tuple[int, int]] = None) -> np.ndarray:
    """Decode distance offsets to bounding boxes [x1, y1, x2, y2]."""
    x1 = points[:, 0] - distance[:, 0]
    y1 = points[:, 1] - distance[:, 1]
    x2 = points[:, 0] + distance[:, 2]
    y2 = points[:, 1] + distance[:, 3]
    if max_shape is not None:
        x1 = np.clip(x1, 0, max_shape[1])
        y1 = np.clip(y1, 0, max_shape[0])
        x2 = np.clip(x2, 0, max_shape[1])
        y2 = np.clip(y2, 0, max_shape[0])
    return np.stack([x1, y1, x2, y2], axis=-1)

def distance2kps(points: np.ndarray, distance: np.ndarray, max_shape: Optional[Tuple[int, int]] = None) -> np.ndarray:
    """Decode distance offsets to 5-point facial landmarks (10 coordinates)."""
    preds = []
    for i in range(0, distance.shape[1], 2):
        px = points[:, i % 2] + distance[:, i]
        py = points[:, i % 2 + 1] + distance[:, i + 1]
        if max_shape is not None:
            px = np.clip(px, 0, max_shape[1])
            py = np.clip(py, 0, max_shape[0])
        preds.append(px)
        preds.append(py)
    return np.stack(preds, axis=-1)

def nms(dets: np.ndarray, thresh: float) -> List[int]:
    """Pure NumPy Non-Maximum Suppression (NMS)."""
    if dets.shape[0] == 0:
        return []
    x1 = dets[:, 0]
    y1 = dets[:, 1]
    x2 = dets[:, 2]
    y2 = dets[:, 3]
    scores = dets[:, 4]

    areas = (x2 - x1 + 1) * (y2 - y1 + 1)
    order = scores.argsort()[::-1]

    keep = []
    while order.size > 0:
        i = order[0]
        keep.append(int(i))
        xx1 = np.maximum(x1[i], x1[order[1:]])
        yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]])
        yy2 = np.minimum(y2[i], y2[order[1:]])

        w = np.maximum(0.0, xx2 - xx1 + 1)
        h = np.maximum(0.0, yy2 - yy1 + 1)
        inter = w * h
        ovr = inter / (areas[i] + areas[order[1:]] - inter)

        inds = np.where(ovr <= thresh)[0]
        order = order[inds + 1]

    return keep

class DetectedFace:
    """Data container for a detected face."""
    __slots__ = ('bbox', 'score', 'landmarks', 'width', 'height', 'area')

    def __init__(self, bbox: List[int], score: float, landmarks: np.ndarray):
        self.bbox = bbox  # [x1, y1, x2, y2]
        self.score = float(score)
        self.landmarks = landmarks  # shape (5, 2)
        self.width = max(0, bbox[2] - bbox[0])
        self.height = max(0, bbox[3] - bbox[1])
        self.area = self.width * self.height

    def to_dict(self) -> dict:
        return {
            'bbox': self.bbox,
            'score': round(self.score, 4),
            'landmarks': self.landmarks.tolist(),
            'width': self.width,
            'height': self.height
        }

class SCRFDDetector:
    """
    SCRFD Face Detector powered by ONNX Runtime.
    Handles single face to dense classroom crowd scenarios with multi-scale feature strides.
    """
    def __init__(self, model_path: Optional[str] = None, providers: Optional[List[str]] = None):
        self.model_path = model_path or config.DETECTOR_MODEL_PATH
        if not os.path.exists(self.model_path):
            raise FileNotFoundError(f"SCRFD model file not found at: {self.model_path}")

        # Hardware detection
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
        self.output_names = [o.name for o in self.session.get_outputs()]
        self.providers = self.session.get_providers()
        self.active_provider = self.providers[0] if self.providers else "CPUExecutionProvider"

        # Strides: 8, 16, 32
        self.strides = [8, 16, 32]
        self._anchor_cache = {}

    def _get_anchors(self, input_size: Tuple[int, int], stride: int, num_anchors: int) -> np.ndarray:
        key = (input_size[0], input_size[1], stride, num_anchors)
        if key in self._anchor_cache:
            return self._anchor_cache[key]

        feat_h = input_size[1] // stride
        feat_w = input_size[0] // stride
        anchor_centers = np.stack(np.mgrid[:feat_h, :feat_w][::-1], axis=-1).astype(np.float32)
        anchor_centers = (anchor_centers * stride).reshape((-1, 2))
        if num_anchors == 2:
            anchor_centers = np.stack([anchor_centers, anchor_centers], axis=1).reshape((-1, 2))

        self._anchor_cache[key] = anchor_centers
        return anchor_centers

    def detect(
        self,
        image: Union[np.ndarray, str],
        threshold: Optional[float] = None,
        input_size: Optional[Tuple[int, int]] = None,
        min_face_size: Optional[int] = None
    ) -> List[DetectedFace]:
        """
        Detect faces in image.
        Returns a list of DetectedFace objects sorted by area (largest to smallest).
        """
        thresh = threshold if threshold is not None else config.FACE_DETECTION_THRESHOLD
        min_size = min_face_size if min_face_size is not None else config.MIN_FACE_SIZE

        # Load image if file path
        if isinstance(image, str):
            img = cv2.imread(image)
            if img is None:
                raise ValueError(f"Could not read image from file path: {image}")
        else:
            img = image.copy()

        orig_h, orig_w = img.shape[:2]

        # Prevent runaway processing on gigantic images
        if max(orig_h, orig_w) > config.MAX_IMAGE_DIMENSION:
            scale_down = config.MAX_IMAGE_DIMENSION / max(orig_h, orig_w)
            img = cv2.resize(img, (int(orig_w * scale_down), int(orig_h * scale_down)), interpolation=cv2.INTER_AREA)
            orig_h, orig_w = img.shape[:2]

        # Determine target detection input resolution
        target_size = input_size or config.DETECTION_INPUT_SIZE
        im_ratio = float(orig_h) / orig_w
        model_ratio = float(target_size[1]) / target_size[0]

        if im_ratio > model_ratio:
            new_h = target_size[1]
            new_w = int(new_h / im_ratio)
        else:
            new_w = target_size[0]
            new_h = int(new_w * im_ratio)

        det_scale = float(new_h) / orig_h
        resized_img = cv2.resize(img, (new_w, new_h))
        det_img = np.zeros((target_size[1], target_size[0], 3), dtype=np.uint8)
        det_img[:new_h, :new_w, :] = resized_img

        # Normalize blob: (x - 127.5) / 128.0, swapRB=True (BGR to RGB)
        blob = cv2.dnn.blobFromImage(det_img, 1.0 / 128.0, target_size, (127.5, 127.5, 127.5), swapRB=True)
        net_outs = self.session.run(self.output_names, {self.input_name: blob})

        scores_list = []
        bboxes_list = []
        kpss_list = []

        # Outputs layout:
        # [0, 1, 2] -> scores for stride 8, 16, 32
        # [3, 4, 5] -> bbox distances for stride 8, 16, 32
        # [6, 7, 8] -> keypoint distances for stride 8, 16, 32
        for idx, stride in enumerate(self.strides):
            score = net_outs[idx]
            bbox = net_outs[idx + 3] * stride
            kps = net_outs[idx + 6] * stride

            feat_h = target_size[1] // stride
            feat_w = target_size[0] // stride
            num_anchors = 2 if score.shape[0] == feat_h * feat_w * 2 else 1
            anchor_centers = self._get_anchors(target_size, stride, num_anchors)

            pos_inds = np.where(score >= thresh)[0]
            if len(pos_inds) > 0:
                pos_scores = score[pos_inds]
                pos_bboxes = distance2bbox(anchor_centers[pos_inds], bbox[pos_inds])
                pos_kpss = distance2kps(anchor_centers[pos_inds], kps[pos_inds])

                scores_list.append(pos_scores)
                bboxes_list.append(pos_bboxes)
                kpss_list.append(pos_kpss)

        if not scores_list:
            return []

        scores = np.vstack(scores_list)
        bboxes = np.vstack(bboxes_list) / det_scale
        kpss = np.vstack(kpss_list) / det_scale

        dets = np.hstack([bboxes, scores])
        keep = nms(dets, config.NMS_THRESHOLD)

        results: List[DetectedFace] = []
        for k in keep:
            box = dets[k, :4]
            x1 = max(0, int(round(box[0])))
            y1 = max(0, int(round(box[1])))
            x2 = min(orig_w, int(round(box[2])))
            y2 = min(orig_h, int(round(box[3])))
            conf = float(dets[k, 4])

            bw = x2 - x1
            bh = y2 - y1
            if bw < min_size or bh < min_size:
                continue

            landmarks = kpss[k].reshape((5, 2))
            # Clip landmarks to image boundary
            landmarks[:, 0] = np.clip(landmarks[:, 0], 0, orig_w)
            landmarks[:, 1] = np.clip(landmarks[:, 1], 0, orig_h)

            results.append(DetectedFace(
                bbox=[x1, y1, x2, y2],
                score=conf,
                landmarks=landmarks
            ))

        # Sort by face bounding box area descending
        results.sort(key=lambda f: f.area, reverse=True)
        return results

"""Detector: ONNX inference when a model exists, deterministic mock otherwise.

Contract (same for both backends):
    detect(frame_bgr) -> list[Detection(label, confidence, bbox=(x1,y1,x2,y2))]
"""
from dataclasses import dataclass
from pathlib import Path

import numpy as np

# Must mirror backend/app/schemas.py LABELS
LABELS = [
    "pothole", "crack", "waterlogging", "garbage_dump", "illegal_parking",
    "broken_streetlight", "open_manhole", "roadside_debris", "faded_signage",
]


@dataclass
class Detection:
    label: str
    confidence: float
    bbox: tuple  # x1, y1, x2, y2 in pixels


class MockDetector:
    """Deterministic pseudo-detections keyed off frame stats — lets the entire
    pipeline run end-to-end before any model is trained."""

    def __init__(self, seed: int = 42):
        self._rng = np.random.default_rng(seed)
        self._counter = 0

    def detect(self, frame: np.ndarray) -> list[Detection]:
        self._counter += 1
        h, w = frame.shape[:2]
        # emit a plausible detection roughly every 3rd frame
        if self._counter % 3 != 0:
            return []
        label = LABELS[int(self._rng.integers(0, len(LABELS)))]
        conf = float(self._rng.uniform(0.5, 0.95))
        cx, cy = self._rng.uniform(0.2, 0.8, 2)
        bw, bh = self._rng.uniform(0.08, 0.25, 2)
        bbox = (
            int((cx - bw / 2) * w), int((cy - bh / 2) * h),
            int((cx + bw / 2) * w), int((cy + bh / 2) * h),
        )
        return [Detection(label, conf, bbox)]


class OnnxDetector:
    """YOLOv8-style detector exported to ONNX (input 1x3x640x640).

    Handles the standard ultralytics export output shape [1, 4+nc, N]:
    rows 0-3 = cx,cy,w,h (pixels in letterboxed space); rows 4.. = per-class
    scores. Reads class names from a sibling model_labels.json when present
    (written by ml/export_onnx.py), else falls back to the platform label list.
    """

    def __init__(self, model_path: str | Path, conf_thres: float = 0.45,
                 input_size: int = 640, labels: list[str] | None = None):
        import json
        import onnxruntime as ort
        self.session = ort.InferenceSession(
            str(model_path), providers=["CPUExecutionProvider"]
        )
        self.conf_thres = conf_thres
        self.input_size = input_size
        self.input_name = self.session.get_inputs()[0].name
        if labels is None:
            lab_file = Path(model_path).with_name("model_labels.json")
            labels = json.loads(lab_file.read_text()) if lab_file.exists() else LABELS
        self.names = labels

    def _preprocess(self, frame: np.ndarray):
        import cv2
        h, w = frame.shape[:2]
        scale = min(self.input_size / w, self.input_size / h)
        nw, nh = int(w * scale), int(h * scale)
        img = cv2.resize(frame, (nw, nh))
        canvas = np.full((self.input_size, self.input_size, 3), 114, dtype=np.uint8)
        canvas[(self.input_size - nh) // 2:(self.input_size - nh) // 2 + nh,
               (self.input_size - nw) // 2:(self.input_size - nw) // 2 + nw] = img
        img = cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        return np.transpose(img, (2, 0, 1))[None], scale, (self.input_size - nw) // 2, (self.input_size - nh) // 2

    def _nms(self, boxes: np.ndarray, scores: np.ndarray, iou_thres: float = 0.45):
        """boxes: [N,4] xyxy; greedy NMS returning kept indices."""
        x1, y1, x2, y2 = boxes[:, 0], boxes[:, 1], boxes[:, 2], boxes[:, 3]
        areas = (x2 - x1) * (y2 - y1)
        order = scores.argsort()[::-1]
        keep = []
        while order.size:
            i = order[0]
            keep.append(i)
            xx1 = np.maximum(x1[i], x1[order[1:]])
            yy1 = np.maximum(y1[i], y1[order[1:]])
            xx2 = np.minimum(x2[i], x2[order[1:]])
            yy2 = np.minimum(y2[i], y2[order[1:]])
            inter = np.maximum(0, xx2 - xx1) * np.maximum(0, yy2 - yy1)
            iou = inter / (areas[i] + areas[order[1:]] - inter + 1e-9)
            order = order[1:][iou <= iou_thres]
        return keep

    def detect(self, frame: np.ndarray) -> list[Detection]:
        inp, scale, pad_x, pad_y = self._preprocess(frame)
        out = np.asarray(self.session.run(None, {self.input_name: inp})[0])
        # out: [1, 4+nc, N] -> transpose to [N, 4+nc]
        preds = out[0].T if out.ndim == 3 else out
        if preds.shape[1] < 5:
            return []
        boxes_cxcywh = preds[:, :4]
        class_scores = preds[:, 4:]
        cls_ids = class_scores.argmax(axis=1)
        confs = class_scores.max(axis=1)
        mask = confs >= self.conf_thres
        if not mask.any():
            return []
        boxes_cxcywh, confs, cls_ids = boxes_cxcywh[mask], confs[mask], cls_ids[mask]
        # cxcywh -> xyxy (letterboxed space)
        cx, cy, bw, bh = boxes_cxcywh[:, 0], boxes_cxcywh[:, 1], boxes_cxcywh[:, 2], boxes_cxcywh[:, 3]
        boxes = np.stack([cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2], axis=1)
        keep = self._nms(boxes, confs)
        dets = []
        h, w = frame.shape[:2]
        for i in keep:
            x1, y1, x2, y2 = boxes[i]
            # undo letterbox padding + scaling, clip to frame
            x1 = float(np.clip((x1 - pad_x) / scale, 0, w))
            y1 = float(np.clip((y1 - pad_y) / scale, 0, h))
            x2 = float(np.clip((x2 - pad_x) / scale, 0, w))
            y2 = float(np.clip((y2 - pad_y) / scale, 0, h))
            cls = int(cls_ids[i])
            if cls < len(self.names):
                dets.append(Detection(self.names[cls], float(confs[i]),
                                      (int(x1), int(y1), int(x2), int(y2))))
        return dets


def load_detector(model_path: str | None, conf_thres: float = 0.45) -> OnnxDetector | MockDetector:
    if model_path and Path(model_path).exists():
        print(f"[detector] loading ONNX model: {model_path}")
        return OnnxDetector(model_path, conf_thres)
    print("[detector] no ONNX model found — using MockDetector (pipeline demo mode)")
    return MockDetector()

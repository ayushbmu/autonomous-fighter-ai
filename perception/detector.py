from __future__ import annotations

from dataclasses import dataclass
from typing import List

import numpy as np

try:
    from ultralytics import YOLO
except ImportError:  # pragma: no cover
    YOLO = None


@dataclass
class Detection:
    label: str
    confidence: float
    x1: float
    y1: float
    x2: float
    y2: float


class FighterDetector:
    """YOLOv8 wrapper that returns normalized fighter detections."""

    def __init__(self, model_path: str, conf_threshold: float = 0.4) -> None:
        self.conf_threshold = conf_threshold
        import torch
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model = YOLO(model_path) if YOLO is not None else None
        if self.model is not None:
            self.model.to(self.device)

    def detect(self, frame: np.ndarray) -> List[Detection]:
        if self.model is None:
            return []

        results = self.model.predict(
            source=frame,
            conf=self.conf_threshold,
            verbose=False,
            device=self.device,
            half=(self.device == "cuda"),
        )
        detections: List[Detection] = []

        if not results:
            return detections

        result = results[0]
        if result.boxes is None:
            return detections

        names = result.names
        boxes = result.boxes

        for box in boxes:
            cls_idx = int(box.cls.item())
            conf = float(box.conf.item())
            x1, y1, x2, y2 = [float(v) for v in box.xyxy[0].tolist()]
            detections.append(
                Detection(
                    label=str(names.get(cls_idx, cls_idx)),
                    confidence=conf,
                    x1=x1,
                    y1=y1,
                    x2=x2,
                    y2=y2,
                )
            )

        return detections

from __future__ import annotations

import base64
from dataclasses import asdict
from typing import List, Optional

import cv2
import numpy as np

from perception.detector import Detection


def draw_detections(frame: np.ndarray, detections: List[Detection]) -> np.ndarray:
    output = frame.copy()
    for det in detections:
        x1, y1, x2, y2 = int(det.x1), int(det.y1), int(det.x2), int(det.y2)
        color = (0, 190, 255) if det.label.lower() in {"player", "p1"} else (20, 110, 255)
        cv2.rectangle(output, (x1, y1), (x2, y2), color, 2)
        label = f"{det.label} {det.confidence:.2f}"
        cv2.putText(output, label, (x1, max(24, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2, cv2.LINE_AA)
    return output


def encode_jpeg_base64(frame: np.ndarray, quality: int = 60) -> Optional[str]:
    ok, buffer = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)])
    if not ok:
        return None
    return base64.b64encode(buffer.tobytes()).decode("ascii")

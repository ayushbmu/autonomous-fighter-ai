from __future__ import annotations

import base64
from dataclasses import asdict
from typing import Any, Dict, List, Optional

import cv2
import numpy as np

from perception.detector import Detection


def _draw_roi_rect(
    output: np.ndarray,
    roi: tuple[float, float, float, float],
    color: tuple[int, int, int],
    label: str,
) -> None:
    h, w = output.shape[:2]
    x0 = int(w * roi[0])
    y0 = int(h * roi[1])
    x1 = int(w * roi[2])
    y1 = int(h * roi[3])
    cv2.rectangle(output, (x0, y0), (x1, y1), color, 1)
    cv2.putText(output, label, (x0, max(14, y0 - 4)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA)


def draw_detections(frame: np.ndarray, detections: List[Detection], hud_debug: Optional[Dict[str, Any]] = None) -> np.ndarray:
    output = frame.copy()
    for det in detections:
        x1, y1, x2, y2 = int(det.x1), int(det.y1), int(det.x2), int(det.y2)
        color = (0, 190, 255) if det.label.lower() in {"player", "p1"} else (20, 110, 255)
        cv2.rectangle(output, (x1, y1), (x2, y2), color, 2)
        label = f"{det.label} {det.confidence:.2f}"
        cv2.putText(output, label, (x1, max(24, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2, cv2.LINE_AA)

    if hud_debug:
        _draw_roi_rect(output, tuple(hud_debug.get("health_left_roi", (0.05, 0.03, 0.46, 0.09))), (0, 255, 255), "P1 HP")
        _draw_roi_rect(output, tuple(hud_debug.get("health_right_roi", (0.54, 0.03, 0.95, 0.09))), (0, 255, 255), "EN HP")
        _draw_roi_rect(output, tuple(hud_debug.get("shadow_roi", (0.07, 0.09, 0.45, 0.14))), (255, 220, 40), "Shadow")

        p_hp = float(hud_debug.get("player_health", 0.0))
        e_hp = float(hud_debug.get("enemy_health", 0.0))
        s_fill = float(hud_debug.get("shadow_meter", 0.0))
        s_full = bool(hud_debug.get("shadow_full", False))
        text = f"HUD P1:{p_hp:.2f} EN:{e_hp:.2f} SH:{s_fill:.2f} FULL:{int(s_full)}"
        cv2.putText(output, text, (14, max(30, output.shape[0] - 14)), cv2.FONT_HERSHEY_SIMPLEX, 0.62, (255, 255, 255), 2, cv2.LINE_AA)
    return output


def encode_jpeg_base64(frame: np.ndarray, quality: int = 60) -> Optional[str]:
    ok, buffer = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)])
    if not ok:
        return None
    return base64.b64encode(buffer.tobytes()).decode("ascii")

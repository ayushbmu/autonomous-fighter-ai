from __future__ import annotations

from dataclasses import asdict
from typing import Any, Dict

import cv2
import numpy as np

from perception.capture import FpsCounter, ScreenCapture
from perception.detector import FighterDetector
from perception.state_extractor import extract_relative_state
from perception.visualize import draw_detections, encode_jpeg_base64


class HudEstimatorConfig:
    def __init__(
        self,
        health_left_roi: tuple[float, float, float, float] = (0.05, 0.03, 0.46, 0.09),
        health_right_roi: tuple[float, float, float, float] = (0.54, 0.03, 0.95, 0.09),
        shadow_roi: tuple[float, float, float, float] = (0.07, 0.09, 0.45, 0.14),
        shadow_h_min: int = 88,
        shadow_h_max: int = 135,
        shadow_s_min: int = 90,
        shadow_v_min: int = 70,
        debug_overlay: bool = True,
    ) -> None:
        self.health_left_roi = health_left_roi
        self.health_right_roi = health_right_roi
        self.shadow_roi = shadow_roi
        self.shadow_h_min = shadow_h_min
        self.shadow_h_max = shadow_h_max
        self.shadow_s_min = shadow_s_min
        self.shadow_v_min = shadow_v_min
        self.debug_overlay = debug_overlay


def _slice_roi(frame: np.ndarray, x0: float, y0: float, x1: float, y1: float) -> np.ndarray:
    h, w = frame.shape[:2]
    left = int(max(0, min(w - 1, w * x0)))
    right = int(max(left + 1, min(w, w * x1)))
    top = int(max(0, min(h - 1, h * y0)))
    bottom = int(max(top + 1, min(h, h * y1)))
    return frame[top:bottom, left:right]


def _estimate_fill_ratio(mask: np.ndarray, min_column_fill: float = 0.14) -> float:
    if mask.size == 0:
        return 0.0

    column_fill = mask.mean(axis=0)
    active_columns = float(np.mean(column_fill > min_column_fill))
    return float(np.clip(active_columns, 0.0, 1.0))


def _estimate_health_fill(frame: np.ndarray, roi_rect: tuple[float, float, float, float]) -> float:
    roi = _slice_roi(frame, *roi_rect)

    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    red_low = cv2.inRange(hsv, (0, 80, 70), (20, 255, 255))
    red_high = cv2.inRange(hsv, (160, 80, 70), (179, 255, 255))
    yellow = cv2.inRange(hsv, (20, 80, 70), (45, 255, 255))
    mask = ((red_low | red_high | yellow) > 0).astype(np.float32)
    return _estimate_fill_ratio(mask, min_column_fill=0.20)


def _estimate_shadow_fill(frame: np.ndarray, cfg: HudEstimatorConfig) -> float:
    roi = _slice_roi(frame, *cfg.shadow_roi)
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    blue = cv2.inRange(
        hsv,
        (cfg.shadow_h_min, cfg.shadow_s_min, cfg.shadow_v_min),
        (cfg.shadow_h_max, 255, 255),
    )
    mask = (blue > 0).astype(np.float32)
    return _estimate_fill_ratio(mask, min_column_fill=0.12)


class PerceptionPipeline:
    def __init__(self, capture: ScreenCapture, detector: FighterDetector, hud_config: HudEstimatorConfig | None = None) -> None:
        self.capture = capture
        self.detector = detector
        self.fps_counter = FpsCounter()
        self.hud_config = hud_config or HudEstimatorConfig()

    def step(self) -> Dict[str, Any]:
        frame = self.capture.grab_latest_bgr()
        fps = self.fps_counter.tick()
        detections = self.detector.detect(frame)
        relative_state = extract_relative_state(
            detections=detections,
            frame_width=frame.shape[1],
            frame_height=frame.shape[0],
        )

        player_health = _estimate_health_fill(frame, self.hud_config.health_left_roi)
        enemy_health = _estimate_health_fill(frame, self.hud_config.health_right_roi)
        shadow_meter = _estimate_shadow_fill(frame, self.hud_config)

        state = asdict(relative_state) if relative_state else None
        if state is not None:
            state["player_health"] = player_health
            state["enemy_health"] = enemy_health
            state["shadow_meter"] = shadow_meter
            state["shadow_full"] = shadow_meter >= 0.98

        hud_debug = {
            "player_health": player_health,
            "enemy_health": enemy_health,
            "shadow_meter": shadow_meter,
            "shadow_full": shadow_meter >= 0.98,
            "health_left_roi": self.hud_config.health_left_roi,
            "health_right_roi": self.hud_config.health_right_roi,
            "shadow_roi": self.hud_config.shadow_roi,
        }

        annotated = draw_detections(
            frame,
            detections,
            hud_debug=hud_debug if self.hud_config.debug_overlay else None,
        )
        encoded = encode_jpeg_base64(annotated)

        return {
            "fps": fps,
            "detections": [asdict(d) for d in detections],
            "state": state,
            "hud_debug": hud_debug,
            "frame_shape": list(frame.shape),
            "live_frame_jpeg": encoded,
        }

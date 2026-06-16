from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Tuple


def _as_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _as_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _as_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def _as_roi(name: str, default: Tuple[float, float, float, float]) -> Tuple[float, float, float, float]:
    value = os.getenv(name)
    if value is None:
        return default

    parts = [part.strip() for part in value.split(",") if part.strip()]
    if len(parts) != 4:
        return default

    try:
        x0, y0, x1, y1 = (float(part) for part in parts)
    except ValueError:
        return default

    if not (0.0 <= x0 < x1 <= 1.0 and 0.0 <= y0 < y1 <= 1.0):
        return default

    return (x0, y0, x1, y1)


@dataclass(frozen=True)
class RuntimeSettings:
    api_host: str = "127.0.0.1"
    api_port: int = 8001
    yolo_model: str = "yolov8n.pt"
    capture_left: int = 0
    capture_top: int = 0
    capture_width: int = 1280
    capture_height: int = 720
    target_fps: float = 30.0
    key_tap_min_delay_ms: int = 10
    key_tap_max_delay_ms: int = 30
    min_action_confidence: float = 0.3
    hud_debug_overlay: bool = True
    hud_health_left_roi: Tuple[float, float, float, float] = (0.05, 0.03, 0.46, 0.09)
    hud_health_right_roi: Tuple[float, float, float, float] = (0.54, 0.03, 0.95, 0.09)
    hud_shadow_roi: Tuple[float, float, float, float] = (0.07, 0.09, 0.45, 0.14)
    hud_shadow_h_min: int = 88
    hud_shadow_h_max: int = 135
    hud_shadow_sat_min: int = 90
    hud_shadow_val_min: int = 70


@dataclass(frozen=True)
class DesktopUISettings:
    """Settings for desktop UI (PyQt6)"""
    ws_url: str = "ws://127.0.0.1:8001/ws"
    telemetry_update_interval_ms: int = 100  # UI refresh rate


def load_runtime_settings() -> RuntimeSettings:
    return RuntimeSettings(
        api_host=os.getenv("AF_API_HOST", "127.0.0.1"),
        api_port=_as_int("AF_API_PORT", 8001),
        yolo_model=os.getenv("AF_YOLO_MODEL", "yolov8n.pt"),
        capture_left=_as_int("AF_CAPTURE_LEFT", 0),
        capture_top=_as_int("AF_CAPTURE_TOP", 0),
        capture_width=_as_int("AF_CAPTURE_WIDTH", 1280),
        capture_height=_as_int("AF_CAPTURE_HEIGHT", 720),
        target_fps=_as_float("AF_TARGET_FPS", 30.0),
        key_tap_min_delay_ms=_as_int("AF_KEY_TAP_MIN_MS", 10),
        key_tap_max_delay_ms=_as_int("AF_KEY_TAP_MAX_MS", 30),
        min_action_confidence=_as_float("AF_MIN_ACTION_CONFIDENCE", 0.55),
        hud_debug_overlay=_as_bool("AF_HUD_DEBUG_OVERLAY", True),
        hud_health_left_roi=_as_roi("AF_HUD_HEALTH_LEFT_ROI", (0.05, 0.03, 0.46, 0.09)),
        hud_health_right_roi=_as_roi("AF_HUD_HEALTH_RIGHT_ROI", (0.54, 0.03, 0.95, 0.09)),
        hud_shadow_roi=_as_roi("AF_HUD_SHADOW_ROI", (0.07, 0.09, 0.45, 0.14)),
        hud_shadow_h_min=_as_int("AF_HUD_SHADOW_H_MIN", 88),
        hud_shadow_h_max=_as_int("AF_HUD_SHADOW_H_MAX", 135),
        hud_shadow_sat_min=_as_int("AF_HUD_SHADOW_S_MIN", 90),
        hud_shadow_val_min=_as_int("AF_HUD_SHADOW_V_MIN", 70),
    )

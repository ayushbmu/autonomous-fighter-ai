from __future__ import annotations

import os
from dataclasses import dataclass


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
    )

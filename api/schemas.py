from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class TelemetryPacket(BaseModel):
    timestamp: float
    fps: float
    current_action: str
    confidence_score: float
    attack_streak: int
    frame_shape: Optional[List[int]] = None
    detections: List[Dict[str, Any]]
    state: Optional[Dict[str, Any]] = None
    live_frame_jpeg: Optional[str] = None
    fight_memory: Optional[Dict[str, Any]] = None

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from perception.detector import Detection

PLAYER_LABELS = {"player", "p1", "fighter_player", "1", "left", "blue"}
ENEMY_LABELS = {"enemy", "p2", "fighter_enemy", "opponent", "2", "3", "right", "red"}


@dataclass
class FighterState:
    cx: float
    cy: float
    width: float
    height: float
    airborne: float


@dataclass
class RelativeState:
    player: FighterState
    enemy: FighterState
    dx: float
    dy: float
    distance: float
    confidence: float


def _center(box: Detection) -> tuple[float, float]:
    return ((box.x1 + box.x2) * 0.5, (box.y1 + box.y2) * 0.5)


def _fighter_state(box: Detection, ground_line: float) -> FighterState:
    cx, cy = _center(box)
    h = max(1.0, box.y2 - box.y1)
    airborne = 1.0 if (box.y2 < ground_line - h * 0.05) else 0.0
    return FighterState(cx=cx, cy=cy, width=max(1.0, box.x2 - box.x1), height=h, airborne=airborne)


def assign_player_enemy(detections: List[Detection]) -> tuple[Optional[Detection], Optional[Detection]]:
    if len(detections) < 2:
        return None, None

    detections_sorted = sorted(detections, key=lambda d: (d.confidence, d.x1), reverse=True)
    player_candidates = [d for d in detections_sorted if d.label.lower() in PLAYER_LABELS]
    enemy_candidates = [d for d in detections_sorted if d.label.lower() in ENEMY_LABELS]

    player = max(player_candidates, key=lambda d: d.confidence) if player_candidates else detections_sorted[0]
    enemy = max(enemy_candidates, key=lambda d: d.confidence) if enemy_candidates else None

    if enemy is None:
        for candidate in detections_sorted:
            if candidate is not player:
                enemy = candidate
                break

    if enemy is None:
        return None, None

    if player is enemy:
        for candidate in detections_sorted:
            if candidate is not player:
                enemy = candidate
                break

    return player, enemy


def extract_relative_state(detections: List[Detection], frame_width: int, frame_height: int) -> Optional[RelativeState]:
    if len(detections) < 2:
        return None

    player, enemy = assign_player_enemy(detections)
    if player is None or enemy is None:
        return None

    ground_line = float(frame_height) * 0.9
    p_state = _fighter_state(player, ground_line)
    e_state = _fighter_state(enemy, ground_line)

    dx = (e_state.cx - p_state.cx) / max(1.0, frame_width)
    dy = (e_state.cy - p_state.cy) / max(1.0, frame_height)
    distance = (dx * dx + dy * dy) ** 0.5
    confidence = (player.confidence + enemy.confidence) * 0.5

    return RelativeState(
        player=p_state,
        enemy=e_state,
        dx=dx,
        dy=dy,
        distance=distance,
        confidence=confidence,
    )

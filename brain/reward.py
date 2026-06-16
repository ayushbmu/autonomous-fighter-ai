from __future__ import annotations

from typing import Literal


CurriculumPhase = Literal["attack", "position", "combos"]


def aggressive_reward(
    dealt_damage: float,
    received_damage: float,
    combo_hits: int,
    moved_forward: bool,
    moved_backward: bool,
    idle_frames: int,
    distance_to_enemy: float,
    blocked: bool = False,
    under_pressure: bool = False,
    phase: CurriculumPhase = "attack",
) -> float:
    """Reward shaping tuned for relentless offensive behavior."""

    dealt_scaled = max(0.0, dealt_damage) * 1000.0
    received_scaled = max(0.0, received_damage) * 1000.0

    if phase == "attack":
        damage_weight = 0.08
        damage_taken_weight = 0.05
        combo_weight = 0.8
        distance_weight = 0.6
    elif phase == "position":
        damage_weight = 0.06
        damage_taken_weight = 0.06
        combo_weight = 1.0
        distance_weight = 1.8
    else:
        damage_weight = 0.05
        damage_taken_weight = 0.06
        combo_weight = 2.6
        distance_weight = 0.9

    reward = 0.0
    reward += dealt_scaled * damage_weight
    reward -= received_scaled * damage_taken_weight
    reward += combo_hits * combo_weight

    if moved_forward:
        reward += 0.6
    if moved_backward:
        reward -= 1.4

    if blocked and under_pressure:
        reward += 2.4
    elif under_pressure and not blocked:
        reward -= 1.8

    reward -= min(idle_frames, 30) * 0.08
    reward += max(0.0, 0.35 - distance_to_enemy) * distance_weight

    return reward

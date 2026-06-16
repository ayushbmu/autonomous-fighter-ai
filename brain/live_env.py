from __future__ import annotations

from typing import Any, Callable, Dict

import numpy as np

from brain.action_space import FighterAction
from brain.env import AutonomousFighterEnv

PerceptionStep = Callable[[], Dict[str, Any]]
ActionRunner = Callable[[FighterAction], None]


def perception_to_env_state(packet: Dict[str, Any]) -> Dict[str, Any]:
    state = packet.get("state") or {}
    player = state.get("player") or {}
    enemy = state.get("enemy") or {}

    return {
        "dx": float(state.get("dx", 0.0)),
        "dy": float(state.get("dy", 0.0)),
        "distance": float(state.get("distance", 0.5)),
        "player_airborne": float(player.get("airborne", 0.0)),
        "enemy_airborne": float(enemy.get("airborne", 0.0)),
        "dealt_damage": float(state.get("dealt_damage", 0.0)),
        "received_damage": float(state.get("received_damage", 0.0)),
        "combo_hits": int(state.get("combo_hits", 0)),
        "forward_velocity": 1.0 if float(state.get("dx", 0.0)) > 0 else 0.0,
        "confidence": float(state.get("confidence", 0.0)),
        "player_health": float(state.get("player_health", 1.0)),
        "enemy_health": float(state.get("enemy_health", 1.0)),
        "shadow_meter": float(state.get("shadow_meter", 0.0)),
        "shadow_full": bool(state.get("shadow_full", False)),
    }


class LiveAutonomousFighterEnv(AutonomousFighterEnv):
    """Environment bridge for direct environmental interaction using live perception + inputs."""

    def __init__(self, perception_step: PerceptionStep, action_runner: ActionRunner, max_steps: int = 2000):
        self._perception_step = perception_step
        self._action_runner = action_runner
        self._prev_enemy_health = 1.0
        self._prev_player_health = 1.0
        self._combo_streak = 0
        super().__init__(state_provider=self._state_provider, action_executor=self._action_executor, max_steps=max_steps)

    def _state_provider(self) -> Dict[str, Any]:
        packet = self._perception_step()
        state = perception_to_env_state(packet)

        enemy_health = float(state.get("enemy_health", self._prev_enemy_health))
        player_health = float(state.get("player_health", self._prev_player_health))

        dealt_damage = max(0.0, self._prev_enemy_health - enemy_health)
        received_damage = max(0.0, self._prev_player_health - player_health)

        if dealt_damage > 0.002:
            self._combo_streak += 1
        else:
            self._combo_streak = 0

        self._prev_enemy_health = enemy_health
        self._prev_player_health = player_health

        state["dealt_damage"] = dealt_damage
        state["received_damage"] = received_damage
        state["combo_hits"] = self._combo_streak
        return state

    def _action_executor(self, action: FighterAction) -> None:
        self._action_runner(action)

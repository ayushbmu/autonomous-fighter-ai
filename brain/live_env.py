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
        "dealt_damage": 0.0,
        "received_damage": 0.0,
        "combo_hits": 0,
        "forward_velocity": 1.0 if float(state.get("dx", 0.0)) > 0 else 0.0,
        "confidence": float(state.get("confidence", 0.0)),
    }


class LiveAutonomousFighterEnv(AutonomousFighterEnv):
    """Environment bridge for direct environmental interaction using live perception + inputs."""

    def __init__(self, perception_step: PerceptionStep, action_runner: ActionRunner, max_steps: int = 2000):
        self._perception_step = perception_step
        self._action_runner = action_runner
        super().__init__(state_provider=self._state_provider, action_executor=self._action_executor, max_steps=max_steps)

    def _state_provider(self) -> Dict[str, Any]:
        packet = self._perception_step()
        return perception_to_env_state(packet)

    def _action_executor(self, action: FighterAction) -> None:
        self._action_runner(action)

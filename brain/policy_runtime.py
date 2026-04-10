from __future__ import annotations

from pathlib import Path

import numpy as np
from stable_baselines3 import PPO

from brain.action_space import FighterAction


class PolicyRuntime:
    def __init__(self, model_path: str, deterministic: bool = False) -> None:
        self.model = PPO.load(model_path)
        self.deterministic = deterministic

    def choose_action(self, observation: np.ndarray) -> FighterAction:
        action, _ = self.model.predict(observation, deterministic=self.deterministic)
        return FighterAction(int(action))


class HeuristicAggressiveRuntime:
    """Fallback policy used before PPO training completes."""

    def choose_action(self, observation: np.ndarray) -> FighterAction:
        distance = float(observation[2])
        enemy_airborne = float(observation[4]) > 0.5

        if distance > 0.25:
            return FighterAction.MOVE_FORWARD
        if enemy_airborne:
            return FighterAction.HEAVY_ATTACK
        return FighterAction.LIGHT_ATTACK


def build_runtime(model_path: str | None, deterministic: bool = False):
    if model_path:
        path = Path(model_path)
        if path.exists() or path.with_suffix(".zip").exists():
            return PolicyRuntime(str(path), deterministic=deterministic)
    return HeuristicAggressiveRuntime()

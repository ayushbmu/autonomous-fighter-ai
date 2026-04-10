from __future__ import annotations

from typing import Any, Callable, Dict, Optional

import gymnasium as gym
import numpy as np
from gymnasium import spaces

from brain.action_space import FighterAction
from brain.reward import aggressive_reward

StateProvider = Callable[[], Dict[str, Any]]
ActionExecutor = Callable[[FighterAction], None]


class AutonomousFighterEnv(gym.Env[np.ndarray, int]):
    metadata = {"render_modes": []}

    def __init__(
        self,
        state_provider: Optional[StateProvider] = None,
        action_executor: Optional[ActionExecutor] = None,
        max_steps: int = 2_000,
    ) -> None:
        super().__init__()
        self.state_provider = state_provider
        self.action_executor = action_executor
        self.max_steps = max_steps
        self.current_step = 0
        self.curriculum_phase = "attack"

        self.action_space = spaces.Discrete(len(FighterAction))
        self.observation_space = spaces.Box(
            low=-1.0,
            high=1.0,
            shape=(10,),
            dtype=np.float32,
        )

        self._idle_frames = 0

    def set_curriculum_phase(self, phase: str) -> None:
        if phase not in {"attack", "position", "combos"}:
            raise ValueError(f"Unsupported curriculum phase: {phase}")
        self.curriculum_phase = phase

    def _default_state(self) -> Dict[str, Any]:
        return {
            "dx": 0.0,
            "dy": 0.0,
            "distance": 0.5,
            "player_airborne": 0.0,
            "enemy_airborne": 0.0,
            "dealt_damage": 0.0,
            "received_damage": 0.0,
            "combo_hits": 0,
            "forward_velocity": 0.0,
            "confidence": 0.0,
        }

    def _get_state(self) -> Dict[str, Any]:
        if self.state_provider is None:
            return self._default_state()
        return self.state_provider()

    def _to_observation(self, state: Dict[str, Any]) -> np.ndarray:
        obs = np.array(
            [
                float(state.get("dx", 0.0)),
                float(state.get("dy", 0.0)),
                float(state.get("distance", 0.5)),
                float(state.get("player_airborne", 0.0)),
                float(state.get("enemy_airborne", 0.0)),
                float(state.get("dealt_damage", 0.0)),
                float(state.get("received_damage", 0.0)),
                float(state.get("combo_hits", 0.0)) / 10.0,
                float(state.get("forward_velocity", 0.0)),
                float(state.get("confidence", 0.0)),
            ],
            dtype=np.float32,
        )
        return np.clip(obs, -1.0, 1.0)

    def reset(self, *, seed: Optional[int] = None, options: Optional[dict] = None):
        super().reset(seed=seed)
        self.current_step = 0
        self._idle_frames = 0
        state = self._get_state()
        obs = self._to_observation(state)
        return obs, {}

    def step(self, action: int):
        self.current_step += 1
        action_enum = FighterAction(action)

        if self.action_executor is not None:
            self.action_executor(action_enum)

        state = self._get_state()

        moved_forward = action_enum == FighterAction.MOVE_FORWARD
        moved_backward = action_enum == FighterAction.MOVE_BACKWARD
        idle_like = action_enum in {FighterAction.IDLE, FighterAction.CROUCH}
        self._idle_frames = self._idle_frames + 1 if idle_like else 0

        reward = aggressive_reward(
            dealt_damage=float(state.get("dealt_damage", 0.0)),
            received_damage=float(state.get("received_damage", 0.0)),
            combo_hits=int(state.get("combo_hits", 0)),
            moved_forward=moved_forward,
            moved_backward=moved_backward,
            idle_frames=self._idle_frames,
            distance_to_enemy=float(state.get("distance", 0.5)),
            blocked=action_enum == FighterAction.MOVE_BACKWARD,
            under_pressure=(
                float(state.get("distance", 0.5)) < 0.2
                and float(state.get("enemy_airborne", 0.0)) < 0.5
            ),
            phase=self.curriculum_phase,
        )

        terminated = False
        truncated = self.current_step >= self.max_steps
        obs = self._to_observation(state)

        info = {
            "action": action_enum.name,
            "step": self.current_step,
            "reward": reward,
            "curriculum_phase": self.curriculum_phase,
        }

        return obs, reward, terminated, truncated, info

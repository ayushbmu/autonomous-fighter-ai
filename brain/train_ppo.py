from __future__ import annotations

import argparse
from pathlib import Path

from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import BaseCallback
from stable_baselines3.common.env_util import make_vec_env
from stable_baselines3.common.vec_env import VecMonitor, VecNormalize
import torch

from brain.env import AutonomousFighterEnv


class CurriculumCallback(BaseCallback):
    def __init__(self, total_timesteps: int, verbose: int = 0) -> None:
        super().__init__(verbose=verbose)
        self.total_timesteps = max(1, int(total_timesteps))
        self._last_phase: str | None = None

    def _phase_for_progress(self, progress: float) -> str:
        if progress < 0.40:
            return "attack"
        if progress < 0.75:
            return "position"
        return "combos"

    def _set_phase(self, phase: str) -> None:
        if self.training_env is None:
            return
        self.training_env.env_method("set_curriculum_phase", phase)
        if self.verbose > 0:
            print(f"[curriculum] switched to phase={phase} at step={self.num_timesteps}")
        self._last_phase = phase

    def _on_training_start(self) -> None:
        self._set_phase("attack")

    def _on_step(self) -> bool:
        progress = min(1.0, float(self.num_timesteps) / float(self.total_timesteps))
        phase = self._phase_for_progress(progress)
        if phase != self._last_phase:
            self._set_phase(phase)
        return True


def train(
    total_timesteps: int = 250_000,
    output_dir: str = "brain/models",
    n_envs: int = 4,
    device: str | None = None,
) -> Path:
    env = make_vec_env(lambda: AutonomousFighterEnv(), n_envs=n_envs)
    env = VecMonitor(env)
    env = VecNormalize(env, norm_obs=True, norm_reward=True, clip_obs=10.0, clip_reward=10.0, gamma=0.995)
    resolved_device = device or ("cuda" if torch.cuda.is_available() else "cpu")

    model = PPO(
        policy="MlpPolicy",
        env=env,
        device=resolved_device,
        verbose=1,
        learning_rate=3e-4,
        n_steps=2048,
        batch_size=256,
        gamma=0.995,
        gae_lambda=0.95,
        ent_coef=0.01,
        clip_range=0.2,
    )

    model.learn(
        total_timesteps=total_timesteps,
        progress_bar=True,
        callback=CurriculumCallback(total_timesteps=total_timesteps, verbose=1),
    )

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    model_path = output_path / "ppo_aggressive_fighter"
    model.save(model_path)
    env.save(str(output_path / "ppo_aggressive_fighter_vecnormalize.pkl"))
    return model_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train AutonomousFighter PPO policy")
    parser.add_argument("--timesteps", type=int, default=250_000)
    parser.add_argument("--output-dir", default="brain/models")
    parser.add_argument("--n-envs", type=int, default=4)
    parser.add_argument("--device", default=None)
    args = parser.parse_args()

    saved = train(
        total_timesteps=args.timesteps,
        output_dir=args.output_dir,
        n_envs=args.n_envs,
        device=args.device,
    )
    print(f"Saved model to: {saved}")

from __future__ import annotations

import argparse
from statistics import mean
from pathlib import Path

import numpy as np
from stable_baselines3 import PPO
from stable_baselines3.common.vec_env import DummyVecEnv, VecNormalize

from brain.env import AutonomousFighterEnv


def evaluate(model_path: str, episodes: int = 10, max_steps: int = 1000) -> float:
    base_env = DummyVecEnv([lambda: AutonomousFighterEnv(max_steps=max_steps)])
    model_file = Path(model_path)
    norm_path = model_file.with_name(f"{model_file.stem}_vecnormalize.pkl")
    if norm_path.exists():
        env = VecNormalize.load(str(norm_path), base_env)
        env.training = False
        env.norm_reward = False
    else:
        env = base_env

    model = PPO.load(model_path, env=env)

    returns = []
    for _ in range(episodes):
        obs = env.reset()
        done = np.array([False])
        total_reward = 0.0
        steps = 0

        while not bool(done[0]) and steps < max_steps:
            action, _ = model.predict(obs, deterministic=True)
            obs, reward, done, _ = env.step(action)
            total_reward += float(reward[0])
            steps += 1

        returns.append(total_reward)

    return float(mean(returns)) if returns else 0.0


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate trained AutonomousFighter PPO policy")
    parser.add_argument("--model", required=True, help="Path to PPO model zip")
    parser.add_argument("--episodes", type=int, default=10)
    parser.add_argument("--max-steps", type=int, default=1000)
    args = parser.parse_args()

    score = evaluate(args.model, episodes=args.episodes, max_steps=args.max_steps)
    print(f"Mean reward over {args.episodes} episodes: {score:.3f}")


if __name__ == "__main__":
    main()

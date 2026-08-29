"""評估訓練後的 PPO 策略：行走距離、速度、跌倒率。

用法：python eval_policy.py [model_path] [episodes]
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np


def main():
    model_path = sys.argv[1] if len(sys.argv) > 1 else str(Path(__file__).parent / "ppo_walk_final")
    n_ep = int(sys.argv[2]) if len(sys.argv) > 2 else 5

    from stable_baselines3 import PPO
    from rl.humanoid_env import HumanoidWalkEnv

    model = PPO.load(model_path, device="cpu")
    env = HumanoidWalkEnv()
    results = []
    for ep in range(n_ep):
        obs, _ = env.reset(seed=100 + ep)
        dist0 = None
        steps = 0
        vxs = []
        while True:
            action, _ = model.predict(obs, deterministic=True)
            obs, r, term, trunc, info = env.step(action)
            if dist0 is None:
                dist0 = info["x"]
            vxs.append(info["vx"])
            steps += 1
            if term or trunc:
                break
        fell = term
        results.append((info["x"] - dist0, steps * 0.02, fell, np.mean(vxs)))
        print(f"ep{ep}: 距離 {results[-1][0]:+.2f} m, 存活 {results[-1][1]:.1f} s, "
              f"跌倒 {fell}, 平均速度 {results[-1][3]:.2f} m/s")
    d = np.array([r[0] for r in results])
    fell_rate = np.mean([r[2] for r in results])
    print(f"\n平均距離 {d.mean():.2f} m ｜ 跌倒率 {fell_rate*100:.0f}% ｜ "
          f"平均速度 {np.mean([r[3] for r in results]):.2f} m/s")


if __name__ == "__main__":
    main()

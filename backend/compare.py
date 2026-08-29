"""三種行走控制器的 SIM-only nominal regression snapshot。

用法：python compare.py [--quick]
輸出：comparison_report.md（並列印摘要）

測試矩陣（皆關閉輔助平衡，速度目標 0.7 m/s）：
1. 平地行走 10 s × N 回合：存活時間、前進距離、平均速度、observed fall
   fraction、sampled absolute mechanical work proxy 與 CoT proxy
2. 行走中抗推撞：穩定行走 3 s 後，從 前/後/側 三方向施加 0.2 s 推力，
   二分搜尋此 deterministic protocol 下的 simulated recovery threshold
"""

import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))

from config_schema import default_robot, GaitParams
from live_sim import LiveSession

GAIT = dict(speed=0.7, step_length=0.35, duty=0.62, clearance=0.07)
CONTROLLERS = ["track", "raibert", "rl"]
LABELS = {"track": "軌跡追蹤（開環）", "raibert": "Raibert 閉環", "rl": "RL 學習策略（PPO）"}


def new_session(ctrl: str) -> LiveSession:
    s = LiveSession(default_robot(), GaitParams(**GAIT), [])
    s.assist_balance = False
    s._advance_sim(1.0)                       # 先站穩
    s.command({"type": "mode", "mode": "walk", "controller": ctrl})
    s.command({"type": "mode", "mode": "walk"})
    return s


def advance_measured(s: LiveSession, T: float) -> float:
    """推進 T 秒並回傳機械能耗（J）。分段呼叫避開單次步數上限。"""
    E = 0.0
    remain = T
    while remain > 1e-9 and s.controller.state != "FALLEN":
        step = min(remain, 0.05)
        # 能耗：取推進前後關節速度與扭矩的近似積分（粗略：用當前值）
        tau = s.data.actuator_force.copy()
        qd = s.data.qvel[6:].copy()
        s._advance_sim(step)
        E += float(np.sum(np.abs(tau * qd))) * step
        remain -= step
    if remain > 0:
        s._advance_sim(remain)                # 跌倒後繼續走完時間（能耗不計）
    return E


def flat_walk(ctrl: str, n_ep: int = 3) -> dict:
    res = {"dist": [], "alive": [], "vx": [], "energy": [], "fell": []}
    for ep in range(n_ep):
        s = new_session(ctrl)
        x0 = float(s.data.qpos[0])
        t0 = s.sim_t
        E = 0.0
        alive_t = 10.0
        for k in range(200):                  # 10 s，每段 0.05 s
            E += advance_measured(s, 0.05)
            if s.controller.state == "FALLEN":
                alive_t = s.sim_t - t0
                break
        dist = float(s.data.qpos[0]) - x0
        res["dist"].append(dist)
        res["alive"].append(alive_t)
        res["vx"].append(dist / max(alive_t, 1e-6))
        res["energy"].append(E)
        res["fell"].append(s.controller.state == "FALLEN")
    return res


def push_capacity(ctrl: str, direction: list[float]) -> float:
    """搜尋目前 simulated protocol 的 recovery threshold（N），不是硬體額定能力。"""
    lo, hi = 0.0, 400.0
    def survives(force: float) -> bool:
        s = new_session(ctrl)
        for _ in range(60):
            s._advance_sim(0.05)
            if s.controller.state == "FALLEN":
                return False                  # 還沒推就跌 → 不通過
        s.command({"type": "push", "dir": direction, "force": force, "duration": 0.2})
        for _ in range(60):
            s._advance_sim(0.05)
            if s.controller.state == "FALLEN":
                return False
        return True
    if not survives(0.0):
        return -1.0                           # 無推力也走不完 → 無法測
    for _ in range(5):
        mid = (lo + hi) / 2
        if survives(mid):
            lo = mid
        else:
            hi = mid
    return lo


def main():
    quick = "--quick" in sys.argv
    n_ep = 2 if quick else 3
    t0 = time.time()
    M = float(np.sum(new_session("track").model.body_mass))

    rows = []
    push_dirs = {"後方推(向前)": [1, 0, 0], "前方推(向後)": [-1, 0, 0], "側向推": [0, 1, 0]}
    for ctrl in CONTROLLERS:
        print(f"\n=== {LABELS[ctrl]} ===")
        fw = flat_walk(ctrl, n_ep)
        dist = np.mean(fw["dist"])
        alive = np.mean(fw["alive"])
        vx = np.mean(fw["vx"])
        fell = 100 * np.mean(fw["fell"])
        E = np.mean(fw["energy"])
        cot = E / (M * 9.81 * max(dist, 1e-3)) if dist > 0.05 else float("nan")
        print(f"平地: 距離 {dist:.2f} m, 存活 {alive:.1f}/10 s, 速度 {vx:.2f} m/s, "
              f"observed fall {fell:.0f}%, CoT proxy {cot:.2f}")
        pushes = {}
        for name, d in push_dirs.items():
            cap = push_capacity(ctrl, d)
            pushes[name] = cap
            print(f"抗推({name}): {'—（平地即跌倒）' if cap < 0 else f'{cap:.0f} N'}")
        rows.append((ctrl, dist, alive, vx, fell, cot, pushes))

    # --- 報告 ---
    lines = [
        "# 行走控制器 SIM-only nominal snapshot",
        "",
        "- Evidence scope：SOFTWARE_ONLY / deterministic nominal regression；非實機、非 HIL、非一般化性能證據",
        f"- 測試條件：速度目標 0.7 m/s、步長 0.35 m、總重 {M:.1f} kg、輔助平衡關閉",
        f"- 平地行走 {n_ep} 回合 × 10 s；push 指標為特定 simulated protocol 的 recovery threshold",
        f"- 產生時間：{time.strftime('%Y-%m-%d %H:%M')}",
        "",
        "| 控制器 | 前進距離 | 存活時間 | 平均速度 | observed fall | CoT proxy | push threshold:後方 | push threshold:前方 | push threshold:側向 |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for ctrl, dist, alive, vx, fell, cot, pushes in rows:
        pv = ["—" if pushes[k] < 0 else f"{pushes[k]:.0f} N" for k in push_dirs]
        cot_s = "—" if np.isnan(cot) else f"{cot:.2f}"
        lines.append(f"| {LABELS[ctrl]} | {dist:.2f} m | {alive:.1f}/10 s | {vx:.2f} m/s | "
                     f"{fell:.0f}% | {cot_s} | {pv[0]} | {pv[1]} | {pv[2]} |")
    lines += [
        "",
        "## 解讀",
        "",
        "- **軌跡追蹤（開環）**：時序開環、無落腳調整，為對照組 — 展示「為什麼需要閉環」。",
        "- **Raibert 閉環**：觸地相位重置 + 線上落腳法則 + 世界座標腿方位控制。",
        "  手調參數，姿態扭矩與支撐腿力耦合未解（需 QP/WBC 才能完全解耦）。",
        "- **RL（PPO）**：以分析模式的運動學步態為模仿參考（DeepMimic-lite）+",
        "  速度追蹤獎勵 + RSI 初始化，訓練環境使用目前模型的 constant torque saturation。",
        "",
        f"RL 模型：{__import__('controller_rl').find_model_path().name}",
    ]
    out = Path(__file__).parent.parent / "comparison_report.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n報告已寫入 {out}（{(time.time()-t0)/60:.1f} 分鐘）")


if __name__ == "__main__":
    main()

"""四個行走控制器的開發比較：凍結動作任務 + 行走中推力掃描 + 速度掃描，輸出圖與數據。

    python -X utf8 backend/compare_controllers_report.py [--out DIR]

比較的四個控制器：track（開環軌跡追蹤）、raibert（Raibert 啟發式落腳）、
rl（PPO 學習策略，registry 選定的 checkpoint）、cp（Capture-point／DCM 落腳，
Raibert 的單因子對照組，見 controller_cp.py）。

三個實驗：
  A. 凍結任務 ``stand_start_walk_stop_v1``（9 s、11 個判準），每個控制器各一次，
     與 run_motion_task.run_one 完全相同的路徑，Dynamic Run Trace 500 Hz。
  B. 行走中推力：任務同一組 gait，assist 全關，行走開始後 PUSH_AT_WALK_S 秒對軀幹
     施 0.2 s 的水平力（前向、側向各一組），量推力後仍站立的秒數。
  C. 速度掃描：三個 deterministic 控制器（RL policy 綁定固定訓練 gait，不參與）
     在固定步週期 0.5 s 下改目標速度，量 6 s 內站立秒數與前進距離。

所有數值都是 SOFTWARE_ONLY_MUJOCO_REALIZED_SIMULATION，性質是
DEVELOPMENT_COMPARISON_ONLY：不是控制器排名、不是實體能力、不是 V3 benchmark。
增益一律使用各控制器程式裡寫死的值，本 harness 不調任何參數。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

from config_schema import GaitParams, default_robot  # noqa: E402
from live_sim import LiveSession  # noqa: E402
from motion_tasks import TASK_ID, get_motion_task  # noqa: E402
from run_motion_task import switch_controller  # noqa: E402
from run_trace import DEFAULT_TRACE_ROOT  # noqa: E402

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
DEFAULT_OUT = REPO / "docs" / "assets" / "controller-compare-2026-09-22"

CONTROLLERS = ("track", "raibert", "rl", "cp")
LABELS = {
    "track": "track（開環軌跡追蹤）",
    "raibert": "raibert（Raibert 落腳）",
    "rl": "rl（PPO 學習策略）",
    "cp": "cp（Capture-point 落腳）",
}
COLORS = {"track": "#7f7f7f", "raibert": "#1f77b4", "rl": "#2ca02c", "cp": "#d62728"}
DETERMINISTIC = ("track", "raibert", "cp")

# 實驗 B：預先定死，未依結果調整
PUSH_AT_WALK_S = 0.8           # 行走開始後幾秒推（三個 deterministic 控制器在 ~2 s 內自行跌倒，故推得早）
PUSH_DURATION_S = 0.2
PUSH_OBSERVE_S = 3.0           # 推後觀察多久
PUSH_FORCES_N = (0.0, 40.0, 80.0, 120.0, 160.0)
PUSH_DIRECTIONS = {"forward": (1.0, 0.0, 0.0), "lateral": (0.0, 1.0, 0.0)}

# 實驗 C：固定步週期 T_step = step_length / speed = 0.5 s（與任務相同）
SPEED_SWEEP_MPS = (0.3, 0.5, 0.7, 0.9)
SPEED_T_STEP_S = 0.5
SPEED_OBSERVE_S = 6.0

ADVANCE_CHUNK_S = 0.1
CODE_FILES = ("controller.py", "controller_raibert.py", "controller_cp.py", "controller_rl.py",
              "live_sim.py", "motion_tasks.py", "run_motion_task.py", "compare_controllers_report.py")


# ---------------------------------------------------------------- 共用


def _cjk_font() -> None:
    logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)  # 字重回退訊息是雜訊
    names = {f.name for f in font_manager.fontManager.ttflist}
    for candidate in ("Noto Sans CJK TC", "Noto Sans CJK SC", "WenQuanYi Zen Hei", "Microsoft JhengHei"):
        if candidate in names:
            plt.rcParams["font.family"] = candidate
            break
    plt.rcParams["axes.unicode_minus"] = False


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _git_head() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=REPO, text=True).strip()
    except Exception:  # pragma: no cover - git 不存在時
        return "unknown"


def task_gait() -> GaitParams:
    contract = get_motion_task(TASK_ID)
    return GaitParams.model_validate({**GaitParams().model_dump(mode="json"), **contract["gait"]})


def new_session(controller: str, gait: GaitParams) -> LiveSession:
    session = LiveSession(default_robot(), gait, [])
    if controller != session.walk_controller:
        switched = switch_controller(session, controller)
        if isinstance(switched, dict) and switched.get("type") == "error":
            raise RuntimeError(f"{controller}: {switched['code']}")
    return session


def _walk_state(session: LiveSession) -> str:
    return session.controller.state


def _advance_until(session: LiveSession, t_end: float) -> None:
    while session.sim_t < t_end - 1e-9:
        session._advance_sim(min(ADVANCE_CHUNK_S, t_end - session.sim_t))


# ---------------------------------------------------------------- A. 凍結任務


def run_task(controller: str) -> dict:
    session = new_session(controller, GaitParams())
    started = session.command({"type": "task_start", "task_id": TASK_ID})
    if isinstance(started, dict) and started.get("type") == "error":
        raise RuntimeError(f"{controller}: {started['code']}")
    t0 = time.time()
    while session.motion_task.active:
        session._advance_sim(0.2)
    wall = time.time() - t0
    receipt = session.last_trace_receipt
    evaluation = session.last_task_result["evaluation"]
    run_id = receipt["run_id"]
    npz = np.load(DEFAULT_TRACE_ROOT / f"{run_id}.npz")
    arrays = {k: npz[k] for k in ("time", "com", "com_vel", "pitch_deg", "roll_deg", "state_code",
                                  "cop_xy", "saturation_pct")}
    return {
        "controller": controller,
        "run_id": run_id,
        "status": evaluation["status"],
        "passed_count": sum(1 for c in evaluation["criteria"] if c["passed"]),
        "criteria": evaluation["criteria"],
        "summary": receipt["summary"],
        "wall_s": round(wall, 2),
        "arrays": arrays,
    }


# ---------------------------------------------------------------- B. 行走中推力


def run_push(controller: str, direction: str, force_n: float, gait: GaitParams) -> dict:
    session = new_session(controller, gait)
    session.assist_balance = False
    session.startup_assist_enabled = False
    session.command({"type": "mode", "mode": "walk"})
    t_walk0 = session.sim_t
    _advance_until(session, t_walk0 + PUSH_AT_WALK_S)
    fell_before_push = _walk_state(session) == "FALLEN"
    pushed = False
    if not fell_before_push and force_n > 0.0:
        result = session.command({
            "type": "push", "dir": list(PUSH_DIRECTIONS[direction]),
            "force": float(force_n), "duration": PUSH_DURATION_S,
        })
        if isinstance(result, dict) and result.get("type") == "error":
            raise RuntimeError(f"push rejected: {result}")
        pushed = True
    t_push = session.sim_t
    fall_t = None
    max_pitch = max_roll = 0.0
    y0 = float(session.data.qpos[1])
    x0 = float(session.data.qpos[0])
    while session.sim_t < t_push + PUSH_OBSERVE_S - 1e-9:
        session._advance_sim(min(0.02, t_push + PUSH_OBSERVE_S - session.sim_t))
        tel = session.controller.telemetry(session.data)
        max_pitch = max(max_pitch, abs(float(tel["pitch_deg"])))
        max_roll = max(max_roll, abs(float(tel["roll_deg"])))
        if _walk_state(session) == "FALLEN" and fall_t is None:
            fall_t = session.sim_t
            break
    upright_after_push = (fall_t - t_push) if fall_t is not None else PUSH_OBSERVE_S
    return {
        "controller": controller,
        "direction": direction,
        "force_n": force_n,
        "fell_before_push": fell_before_push,
        "pushed": pushed,
        "push_at_walk_s": PUSH_AT_WALK_S,
        "fell_after_push": fall_t is not None,
        "upright_after_push_s": round(float(upright_after_push), 3),
        "max_abs_pitch_deg": round(max_pitch, 1),
        "max_abs_roll_deg": round(max_roll, 1),
        "displacement_m": [round(float(session.data.qpos[0]) - x0, 3), round(float(session.data.qpos[1]) - y0, 3)],
    }


# ---------------------------------------------------------------- C. 速度掃描


def run_speed(controller: str, speed: float) -> dict:
    base = task_gait().model_dump(mode="json")
    gait = GaitParams.model_validate({**base, "speed": speed, "step_length": round(speed * SPEED_T_STEP_S, 4)})
    session = new_session(controller, gait)
    session.assist_balance = False
    session.startup_assist_enabled = False
    session.command({"type": "mode", "mode": "walk"})
    t0 = session.sim_t
    x0 = float(session.data.qpos[0])
    fall_t = None
    while session.sim_t < t0 + SPEED_OBSERVE_S - 1e-9:
        session._advance_sim(min(0.02, t0 + SPEED_OBSERVE_S - session.sim_t))
        if _walk_state(session) == "FALLEN":
            fall_t = session.sim_t
            break
    return {
        "controller": controller,
        "speed_mps": speed,
        "step_length_m": gait.step_length,
        "upright_s": round(float((fall_t or (t0 + SPEED_OBSERVE_S)) - t0), 3),
        "fell": fall_t is not None,
        "distance_m": round(float(session.data.qpos[0]) - x0, 3),
        "steps": int(getattr(session.controller, "n_steps", 0)),
    }


# ---------------------------------------------------------------- 圖


def _phase_bands(ax, contract: dict) -> None:
    shades = ["#f7f7f7", "#e8f1fb", "#ddeedd", "#fbeee0", "#f7f7f7"]
    for phase, shade in zip(contract["phases"], shades):
        ax.axvspan(phase["start_s"], phase["end_s"], color=shade, zorder=0)
        ax.text((phase["start_s"] + phase["end_s"]) / 2, 0.98, phase["id"], transform=ax.get_xaxis_transform(),
                ha="center", va="top", fontsize=7, color="#555")


def _fall_marker(ax, t, y, color):
    ax.plot([t], [y], marker="x", color=color, ms=9, mew=2, ls="none", zorder=5)


def fig_task_vx(results: list[dict], contract: dict, out: Path) -> None:
    fig, ax = plt.subplots(figsize=(10, 4.2))
    _phase_bands(ax, contract)
    lim = contract["criteria"]
    ax.axhspan(lim["steady_speed_min_mps"], lim["steady_speed_max_mps"], xmin=2.5 / 9, xmax=6.5 / 9,
               color="#2ca02c", alpha=0.10, zorder=1)
    ax.axhline(contract["gait"]["speed"], color="#2ca02c", ls="--", lw=1, label=f"目標 {contract['gait']['speed']} m/s")
    for r in results:
        a = r["arrays"]
        vx = a["com_vel"][:, 0]
        ax.plot(a["time"], vx, color=COLORS[r["controller"]], lw=1.4, label=LABELS[r["controller"]])
        fall = r["summary"]["first_fall_time_s"]
        if fall is not None:
            i = int(np.searchsorted(a["time"], fall))
            _fall_marker(ax, fall, vx[min(i, len(vx) - 1)], COLORS[r["controller"]])
    ax.set_ylim(-1.6, 1.8)
    ax.set_xlim(0, 9)
    ax.set_xlabel("時間 (s)")
    ax.set_ylabel("質心前進速度 vx (m/s)")
    ax.set_title("A. 凍結任務 stand_start_walk_stop_v1：前進速度（× = 首次跌倒）")
    ax.legend(loc="lower left", fontsize=8, ncol=2)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(out, dpi=140)
    plt.close(fig)


def fig_task_posture(results: list[dict], contract: dict, out: Path) -> None:
    fig, axes = plt.subplots(2, 1, figsize=(10, 6), sharex=True)
    limit = contract["criteria"]["posture_limit_deg"]
    for ax, key, name in ((axes[0], "pitch_deg", "pitch"), (axes[1], "roll_deg", "roll")):
        _phase_bands(ax, contract)
        ax.axhline(limit, color="#999", ls=":", lw=1)
        ax.axhline(-limit, color="#999", ls=":", lw=1, label=f"站立姿態判準 ±{limit:.0f}°")
        for r in results:
            a = r["arrays"]
            ax.plot(a["time"], a[key], color=COLORS[r["controller"]], lw=1.2, label=LABELS[r["controller"]])
            fall = r["summary"]["first_fall_time_s"]
            if fall is not None:
                i = int(np.searchsorted(a["time"], fall))
                _fall_marker(ax, fall, a[key][min(i, len(a[key]) - 1)], COLORS[r["controller"]])
        ax.set_ylabel(f"軀幹 {name} (°)")
        ax.set_ylim(-100, 100)
        ax.grid(alpha=0.3)
    axes[0].set_title("A. 凍結任務：軀幹姿態（× = 首次跌倒）")
    axes[0].legend(loc="lower left", fontsize=8, ncol=3)
    axes[1].set_xlabel("時間 (s)")
    axes[1].set_xlim(0, 9)
    fig.tight_layout()
    fig.savefig(out, dpi=140)
    plt.close(fig)


def _fmt(value, unit) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return value
    if unit in ("s", "m", "m/s"):
        return f"{value:.3f}"
    return f"{value:.1f}"


def fig_task_criteria(results: list[dict], out: Path) -> None:
    ids = [c["id"] for c in results[0]["criteria"]]
    fig, ax = plt.subplots(figsize=(10, 0.42 * len(ids) + 1.6))
    grid = np.array([[1.0 if c["passed"] else 0.0 for c in r["criteria"]] for r in results]).T
    ax.imshow(grid, cmap=matplotlib.colors.ListedColormap(["#f4c7c3", "#c6e5c6"]), vmin=0, vmax=1, aspect="auto")
    for j, r in enumerate(results):
        for i, c in enumerate(r["criteria"]):
            ax.text(j, i, _fmt(c["value"], c["unit"]), ha="center", va="center", fontsize=8,
                    color="#222" if c["passed"] else "#8b0000")
    limits = []
    for c in results[0]["criteria"]:
        lim = c["limit"]
        lim_txt = f"[{lim[0]}, {lim[1]}]" if isinstance(lim, list) else str(lim)
        limits.append(f"{c['id']}  ({c['operator']} {lim_txt} {c['unit']})")
    ax.set_yticks(range(len(ids)))
    ax.set_yticklabels(limits, fontsize=8)
    ax.set_xticks(range(len(results)))
    ax.set_xticklabels([f"{LABELS[r['controller']]}\n{r['passed_count']}/{len(ids)} 通過" for r in results], fontsize=8)
    ax.set_title("A. 凍結任務 11 項判準（綠 = 通過、紅 = 未通過；格內為量測值）")
    ax.legend(handles=[Patch(color="#c6e5c6", label="通過"), Patch(color="#f4c7c3", label="未通過")],
              loc="upper left", bbox_to_anchor=(1.01, 1.0), fontsize=8)
    fig.tight_layout()
    fig.savefig(out, dpi=140)
    plt.close(fig)


def fig_task_path(results: list[dict], contract: dict, out: Path) -> None:
    fig, ax = plt.subplots(figsize=(10, 3.6))
    drift = contract["criteria"]["lateral_drift_max_m"]
    ax.axhspan(-drift, drift, color="#2ca02c", alpha=0.08, label=f"側向偏移判準 ±{drift} m")
    ax.axvline(contract["criteria"]["steady_progress_min_m"], color="#999", ls=":", lw=1,
               label=f"STEADY_PROGRESS ≥ {contract['criteria']['steady_progress_min_m']} m（相對起點）")
    for r in results:
        a = r["arrays"]
        fall = r["summary"]["first_fall_time_s"]
        n = int(np.searchsorted(a["time"], fall)) if fall is not None else len(a["time"])
        n = max(n, 2)
        x = a["com"][:n, 0] - a["com"][0, 0]
        y = a["com"][:n, 1] - a["com"][0, 1]
        ax.plot(x, y, color=COLORS[r["controller"]], lw=1.4, label=LABELS[r["controller"]])
        if fall is not None:
            _fall_marker(ax, x[-1], y[-1], COLORS[r["controller"]])
    ax.set_xlabel("質心前進位移 x (m)")
    ax.set_ylabel("質心側向位移 y (m)")
    ax.set_title("A. 凍結任務：質心俯視軌跡（畫到首次跌倒為止；× = 跌倒點）")
    y_all = np.concatenate([r["arrays"]["com"][:, 1] - r["arrays"]["com"][0, 1] for r in results])
    ax.set_ylim(min(-0.7, float(np.nanmin(y_all)) - 0.1), max(0.7, float(np.nanmax(y_all)) + 0.1))
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8, loc="upper right", ncol=2)
    fig.tight_layout()
    fig.savefig(out, dpi=140)
    plt.close(fig)


def fig_task_capture_point(results: list[dict], contract: dict, out: Path) -> None:
    """ξ_x − CoP_x：瞬時 capture point 相對壓力中心的超前量（LIPM 等速時 ≈ v/ω0 ≈ 0.2 m）。"""
    fig, ax = plt.subplots(figsize=(10, 4))
    _phase_bands(ax, contract)
    for r in results:
        if r["controller"] not in ("raibert", "cp"):
            continue
        a = r["arrays"]
        com, v = a["com"], a["com_vel"]
        omega0 = np.sqrt(9.81 / np.maximum(com[:, 2], 0.3))
        xi_x = com[:, 0] + v[:, 0] / omega0
        cop_x = a["cop_xy"][:, 0]
        lead = xi_x - cop_x
        lead[~np.isfinite(cop_x)] = np.nan
        fall = r["summary"]["first_fall_time_s"]
        n = int(np.searchsorted(a["time"], fall)) if fall is not None else len(lead)
        ax.plot(a["time"][:n], lead[:n], color=COLORS[r["controller"]], lw=1.2, label=LABELS[r["controller"]])
        if fall is not None:
            _fall_marker(ax, fall, np.nan_to_num(lead[max(n - 1, 0)]), COLORS[r["controller"]])
    v_des = contract["gait"]["speed"]
    ax.axhline(v_des / np.sqrt(9.81 / 0.85), color="#555", ls="--", lw=1,
               label=f"LIPM 等速參考 v_des/ω0 ≈ {v_des / np.sqrt(9.81 / 0.85):.2f} m")
    ax.axhline(0, color="#999", lw=0.8)
    ax.set_xlim(0, 9)
    ax.set_ylim(-0.6, 0.9)
    ax.set_xlabel("時間 (s)")
    ax.set_ylabel("ξ_x - CoP_x (m)")
    ax.set_title("A. 診斷：capture point 相對壓力中心的超前量（raibert vs cp，同一堆疊只換落腳與踝法則）")
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8, loc="lower left")
    fig.tight_layout()
    fig.savefig(out, dpi=140)
    plt.close(fig)


def fig_push(push_rows: list[dict], out: Path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(11, 3.6), sharey=True)
    for ax, direction in zip(axes, PUSH_DIRECTIONS):
        grid = np.full((len(CONTROLLERS), len(PUSH_FORCES_N)), np.nan)
        for row in push_rows:
            if row["direction"] != direction:
                continue
            i = CONTROLLERS.index(row["controller"])
            j = PUSH_FORCES_N.index(row["force_n"])
            grid[i, j] = row["upright_after_push_s"]
        im = ax.imshow(grid, cmap="RdYlGn", vmin=0, vmax=PUSH_OBSERVE_S, aspect="auto")
        for row in push_rows:
            if row["direction"] != direction:
                continue
            i = CONTROLLERS.index(row["controller"])
            j = PUSH_FORCES_N.index(row["force_n"])
            if row["fell_before_push"]:
                txt = "推前\n已跌"
            elif row["fell_after_push"]:
                txt = f"{row['upright_after_push_s']:.2f} s\n跌倒"
            else:
                txt = f"≥{PUSH_OBSERVE_S:.0f} s\n站立"
            ax.text(j, i, txt, ha="center", va="center", fontsize=7.5)
        ax.set_xticks(range(len(PUSH_FORCES_N)))
        ax.set_xticklabels(["0 N（無推）"] + [f"{f:.0f} N" for f in PUSH_FORCES_N[1:]])
    axes[0].set_yticks(range(len(CONTROLLERS)))
    axes[0].set_yticklabels([LABELS[c] for c in CONTROLLERS], fontsize=8)
    for ax, direction in zip(axes, PUSH_DIRECTIONS):
        ax.set_title(f"B. {'前向' if direction == 'forward' else '側向'}推力 {PUSH_DURATION_S} s，"
                     f"行走開始後 {PUSH_AT_WALK_S} s 施加", fontsize=10)
    fig.colorbar(im, ax=axes, fraction=0.02, pad=0.02, label="推後站立秒數 (s)")
    fig.suptitle("B. 行走中推力掃描：推後仍站立的秒數（觀察窗 3 s；assist 全關）", fontsize=11)
    fig.savefig(out, dpi=140, bbox_inches="tight")
    plt.close(fig)


def fig_speed(speed_rows: list[dict], out: Path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(11, 3.6))
    for c in DETERMINISTIC:
        rows = [r for r in speed_rows if r["controller"] == c]
        xs = [r["speed_mps"] for r in rows]
        axes[0].plot(xs, [r["upright_s"] for r in rows], marker="o", color=COLORS[c], label=LABELS[c])
        axes[1].plot(xs, [r["distance_m"] for r in rows], marker="o", color=COLORS[c], label=LABELS[c])
    axes[0].axhline(SPEED_OBSERVE_S, color="#999", ls=":", lw=1)
    axes[0].set_ylabel(f"站立秒數 (s，上限 {SPEED_OBSERVE_S:.0f})")
    axes[1].set_ylabel("前進距離 (m)")
    for ax in axes:
        ax.set_xlabel("目標速度 (m/s)；步週期固定 0.5 s")
        ax.grid(alpha=0.3)
        ax.set_xticks(SPEED_SWEEP_MPS)
    axes[0].legend(fontsize=8)
    fig.suptitle("C. 速度掃描（僅 deterministic 控制器；RL policy 綁定固定訓練 gait，不參與）", fontsize=11)
    fig.tight_layout()
    fig.savefig(out, dpi=140)
    plt.close(fig)


# ---------------------------------------------------------------- 主流程


def downsample_csv(results: list[dict], out: Path, every: int = 10) -> None:
    lines = ["controller,t_s,com_x_m,com_y_m,com_z_m,vx_mps,vy_mps,pitch_deg,roll_deg,state_code"]
    for r in results:
        a = r["arrays"]
        for i in range(0, len(a["time"]), every):
            lines.append(",".join([
                r["controller"], f"{a['time'][i]:.3f}",
                f"{a['com'][i, 0]:.4f}", f"{a['com'][i, 1]:.4f}", f"{a['com'][i, 2]:.4f}",
                f"{a['com_vel'][i, 0]:.4f}", f"{a['com_vel'][i, 1]:.4f}",
                f"{a['pitch_deg'][i]:.2f}", f"{a['roll_deg'][i]:.2f}", str(int(a["state_code"][i])),
            ]))
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--skip-push", action="store_true")
    parser.add_argument("--skip-speed", action="store_true")
    args = parser.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    _cjk_font()
    contract = get_motion_task(TASK_ID)
    t_start = time.time()

    print("== A. 凍結任務 ==", flush=True)
    task_results = []
    for c in CONTROLLERS:
        r = run_task(c)
        task_results.append(r)
        failed = ", ".join(f"{x['id']}={_fmt(x['value'], x['unit'])}" for x in r["criteria"] if not x["passed"])
        print(f"  {c:8s} {r['status']} {r['passed_count']}/11  fall={r['summary']['first_fall_time_s']}  "
              f"wall={r['wall_s']}s  failed: {failed}", flush=True)

    push_rows: list[dict] = []
    if not args.skip_push:
        print("== B. 行走中推力 ==", flush=True)
        gait = task_gait()
        for c in CONTROLLERS:
            for direction in PUSH_DIRECTIONS:
                for f in PUSH_FORCES_N:
                    row = run_push(c, direction, f, gait)
                    push_rows.append(row)
                    print(f"  {c:8s} {direction:8s} {f:5.0f} N  before={row['fell_before_push']}  "
                          f"upright_after={row['upright_after_push_s']}  fell={row['fell_after_push']}", flush=True)

    speed_rows: list[dict] = []
    if not args.skip_speed:
        print("== C. 速度掃描 ==", flush=True)
        for c in DETERMINISTIC:
            for s in SPEED_SWEEP_MPS:
                row = run_speed(c, s)
                speed_rows.append(row)
                print(f"  {c:8s} {s:.1f} m/s  upright={row['upright_s']}  dist={row['distance_m']}  steps={row['steps']}",
                      flush=True)

    print("== 圖 ==", flush=True)
    fig_task_vx(task_results, contract, out / "fig1_task_forward_speed.png")
    fig_task_posture(task_results, contract, out / "fig2_task_posture.png")
    fig_task_criteria(task_results, out / "fig3_task_criteria.png")
    fig_task_path(task_results, contract, out / "fig4_task_com_path.png")
    fig_task_capture_point(task_results, contract, out / "fig5_task_capture_point_lead.png")
    if push_rows:
        fig_push(push_rows, out / "fig6_push_sweep.png")
    if speed_rows:
        fig_speed(speed_rows, out / "fig7_speed_sweep.png")
    downsample_csv(task_results, out / "task_traces_50hz.csv")

    summary = {
        "schema": "CONTROLLER_COMPARISON_REPORT_V1",
        "nature": "DEVELOPMENT_COMPARISON_ONLY",
        "evidence_scope": "SOFTWARE_ONLY_MUJOCO_REALIZED_SIMULATION",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git_head": _git_head(),
        "python": platform.python_version(),
        "code_sha256": {name: _sha256(HERE / name) for name in CODE_FILES if (HERE / name).exists()},
        "task": {
            "task_id": TASK_ID,
            "gait": contract["gait"],
            "criteria_limits": contract["criteria"],
            "results": [
                {k: v for k, v in r.items() if k != "arrays"} for r in task_results
            ],
        },
        "push_sweep": {
            "push_at_walk_s": PUSH_AT_WALK_S, "duration_s": PUSH_DURATION_S, "observe_s": PUSH_OBSERVE_S,
            "forces_n": list(PUSH_FORCES_N), "directions": PUSH_DIRECTIONS,
            "gait": task_gait().model_dump(mode="json"), "assist": False,
            "rows": push_rows,
        },
        "speed_sweep": {
            "speeds_mps": list(SPEED_SWEEP_MPS), "t_step_s": SPEED_T_STEP_S, "observe_s": SPEED_OBSERVE_S,
            "controllers": list(DETERMINISTIC), "rows": speed_rows,
        },
        "wall_s_total": round(time.time() - t_start, 1),
    }
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"寫入 {out}（{summary['wall_s_total']} s）")
    return 0


if __name__ == "__main__":
    sys.exit(main())

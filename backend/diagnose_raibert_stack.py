"""定位 Raibert 堆疊那個「起步後約 2 s 必倒」的共用瓶頸：儀器化基準 + 單因子消融。

    python -X utf8 backend/diagnose_raibert_stack.py [--out DIR] [--skip-task]

背景（CONTROLLER_COMPARISON_2026-09-22 §4.2、§6）：raibert 與 cp 只差落腳與踝法則，
卻在同一時點倒下；速度掃描 0.3–0.9 m/s 的站立秒數全落在 1.8–2.5 s。
這支 harness 做兩件事：

  A. 儀器化基準：任務同一組 gait（0.7 m/s、0.35 m、clearance 0.07）、行走模式、assist 全關，
     每個 physics tick 記錄控制器內部狀態（相位、支撐腳、接觸、落點、骨盆目標、髖／踝修正、
     支撐腿各關節扭矩與其上限、腳掌高度），畫成時間線，直接看失敗機制。
  B. 單因子消融：RaibertController 的每個堆疊常數（2026-09-22 從 compute() 搬成 class attribute）
     各改一個值，其餘不動，量行走模式 6 s 內站立秒數、步數、距離。變體清單在看到 A 之前寫死。
     站滿 6 s 的變體再跑一次凍結任務，報 11 項判準。

性質：DEVELOPMENT 診斷，不是 protocol、不是 evidence。不改任何預設行為——所有變體都是
子類別上的屬性覆寫，controller_raibert.py 的預設值就是原本的行為（trace 逐位元相等已驢證）。
"""

from __future__ import annotations

import argparse
import contextlib
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

import live_sim  # noqa: E402
from config_schema import GaitParams, default_robot  # noqa: E402
from controller import G, JOINT_ORDER, quat_to_pitch_roll  # noqa: E402
from controller_raibert import RaibertController  # noqa: E402
from live_sim import LiveSession  # noqa: E402
from motion_tasks import TASK_ID, get_motion_task  # noqa: E402

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
DEFAULT_OUT = REPO / "docs" / "assets" / "raibert-diagnosis-2026-09-22"
OBSERVE_S = 6.0
TICK_S = 0.02
CODE_FILES = ("controller.py", "controller_raibert.py", "live_sim.py", "diagnose_raibert_stack.py")


# ---------------------------------------------------------------- 變體（在看到 A 的結果之前寫死）

def _scaled(name: str, factor: float):
    return {name: getattr(RaibertController, name) * factor}


VARIANTS: list[tuple[str, dict, dict]] = [
    # (名稱, 控制器屬性覆寫, gait 覆寫)
    ("baseline", {}, {}),
    ("hurry_off", {"HURRY_CP_AHEAD_M": 9.9}, {}),
    ("td_min_phase_0.70", {"TD_MIN_PHASE": 0.70}, {}),
    ("td_min_phase_0.25", {"TD_MIN_PHASE": 0.25}, {}),
    ("first_shift_0.4s", {"FIRST_SHIFT_S": 0.4}, {}),
    ("first_shift_1.2s", {"FIRST_SHIFT_S": 1.2}, {}),
    ("land_lock_off", {"LAND_LOCK_PHASE": 1.1}, {}),
    ("pushdown_off", {"PUSHDOWN_RATE": 0.0}, {}),
    ("pushdown_x2", {"PUSHDOWN_RATE": 0.70}, {}),
    ("v_servo_off", {"V_SERVO_GAIN": 0.0}, {}),
    ("v_servo_x2", {"V_SERVO_GAIN": 0.50}, {}),
    ("x_rel_center_0.3", {"X_REL_PHASE_CENTER": 0.3}, {}),
    ("x_rel_center_0.7", {"X_REL_PHASE_CENTER": 0.7}, {}),
    ("x_rel_lim_half", {"X_REL_LIM_M": 0.16}, {}),
    ("lateral_rate_first_x2", {"LATERAL_RATE_FIRST": 0.30}, {}),
    ("lean_v_off", {"LEAN_V_GAIN": 0.0}, {}),
    ("grav_ff_1.0", {"GRAV_FF_SCALE": 1.0}, {}),
    ("grav_ff_0.7", {"GRAV_FF_SCALE": 0.7}, {}),
    ("qfrc_bias_1.0", {"QFRC_BIAS_SCALE": 1.0}, {}),
    ("hip_pitch_gain_half", {**_scaled("HIP_PITCH_KP", 0.5), **_scaled("HIP_PITCH_KD", 0.5)}, {}),
    ("hip_pitch_gain_x2", {**_scaled("HIP_PITCH_KP", 2.0), **_scaled("HIP_PITCH_KD", 2.0)}, {}),
    ("hip_corr_lim_220", {"HIP_CORR_LIM_NM": 220.0}, {}),
    ("roll_gain_half", {**_scaled("ROLL_KP", 0.5), **_scaled("ROLL_KD", 0.5)}, {}),
    ("roll_gain_x2", {**_scaled("ROLL_KP", 2.0), **_scaled("ROLL_KD", 2.0)}, {}),
    ("ankle_x2", {"ANKLE_KV": 140.0, "ANKLE_LIM_NM": 70.0}, {}),
    ("ankle_off", {"ANKLE_KV": 0.0}, {}),
    ("kR_0.15", {"kR": 0.15}, {}),
    ("kR_0.60", {"kR": 0.60}, {}),
    ("DS_0.30", {"DS": 0.30}, {}),
    ("DS_0.05", {"DS": 0.05}, {}),
    ("land_back_lim_0.20", {"LAND_BACK_LIM_M": 0.20}, {}),
    ("land_reach_0.30", {"LAND_REACH_M": 0.30}, {}),
    ("pd_x1.5", {"_pd_scale": 1.5}, {}),
    ("pd_x0.7", {"_pd_scale": 0.7}, {}),
    ("gait_clearance_0.04", {}, {"clearance": 0.04}),
    ("gait_clearance_0.10", {}, {"clearance": 0.10}),
    ("gait_step_0.25", {}, {"step_length": 0.25}),
    ("gait_step_0.45", {}, {"step_length": 0.45}),
    ("gait_lean_0deg", {}, {"torso_lean_deg": 0.0}),
    ("gait_lean_6deg", {}, {"torso_lean_deg": 6.0}),
    ("gait_speed_0.5_step_0.25", {}, {"speed": 0.5, "step_length": 0.25}),
]

INSTANCE_ATTRS = {"kR", "DS"}


def make_variant_class(overrides: dict):
    class_attrs = {k: v for k, v in overrides.items() if k not in INSTANCE_ATTRS and not k.startswith("_")}
    inst_attrs = {k: v for k, v in overrides.items() if k in INSTANCE_ATTRS}
    pd_scale = overrides.get("_pd_scale")

    def __init__(self, model, cfg, gait, lean):
        RaibertController.__init__(self, model, cfg, gait, lean)
        for k, v in inst_attrs.items():
            setattr(self, k, v)
        if pd_scale is not None:
            self.kp = self.kp * pd_scale
            self.kd = self.kd * pd_scale

    return type("VariantRaibert", (RaibertController,), {**class_attrs, "__init__": __init__})


@contextlib.contextmanager
def raibert_factory(cls):
    """讓 LiveSession（含 motion-task candidate）以 cls 取代 RaibertController。"""
    original = live_sim.LiveSession._make_controller

    def patched(self, lean, kind=None):
        selected = kind or self.walk_controller
        if selected == "raibert":
            return cls(self.model, self.cfg, self.gait, lean)
        return original(self, lean, kind)

    live_sim.LiveSession._make_controller = patched
    try:
        yield
    finally:
        live_sim.LiveSession._make_controller = original


# ---------------------------------------------------------------- 共用

def _cjk_font() -> None:
    logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)
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
    except Exception:  # pragma: no cover
        return "unknown"


def task_gait(**overrides) -> GaitParams:
    contract = get_motion_task(TASK_ID)
    return GaitParams.model_validate({**GaitParams().model_dump(mode="json"), **contract["gait"], **overrides})


def walk_session(gait: GaitParams) -> LiveSession:
    session = LiveSession(default_robot(), gait, [])   # 預設 walk_controller 就是 raibert
    session.assist_balance = False
    session.startup_assist_enabled = False
    session.command({"type": "mode", "mode": "walk"})
    return session


# ---------------------------------------------------------------- A. 儀器化基準

class InstrumentedRaibert(RaibertController):
    """每個 tick 記一列內部狀態；不改任何行為。"""

    def __init__(self, model, cfg, gait, lean):
        super().__init__(model, cfg, gait, lean)
        self.rows: list[dict] = []
        self._idx = {
            side: {
                "hip_pitch": JOINT_ORDER.index(f"hip_pitch_{side}"),
                "knee": JOINT_ORDER.index(f"knee_{side}"),
                "ankle": JOINT_ORDER.index(f"ankle_{side}"),
            }
            for side in ("l", "r")
        }

    def compute(self, data, t_gait, dt):
        tau = super().compute(data, t_gait, dt)
        if self.state in ("WALK", "STOPPING", "FALLEN"):
            pitch, roll = quat_to_pitch_roll(data.qpos[3:7])
            cl, cr = self._foot_contacts(data)
            st = self.stance
            sw = "r" if st == "l" else "l"
            foot_l = data.xpos[self._body["l"]]
            foot_r = data.xpos[self._body["r"]]
            row = {
                "t": float(self.t),
                "state": self.state,
                "phase": float(self.phase),
                "stance": st,
                "n_steps": int(self.n_steps),
                "contact_l": bool(cl), "contact_r": bool(cr),
                "pelvis_x": float(data.qpos[0]), "pelvis_y": float(data.qpos[1]), "pelvis_z": float(data.qpos[2]),
                "vx": float(self._v_filt[0]), "vy": float(self._v_filt[1]),
                "pitch_deg": float(np.degrees(pitch)), "roll_deg": float(np.degrees(roll)),
                "hip_corr": float(self.hip_corr), "roll_corr": float(self.roll_corr), "ankle_corr": float(self.ankle_corr),
                "p_land_x_rel": float(self.p_land[0] - data.qpos[0]),
                "stance_ankle_x_rel": float(self.stance_ankle[0] - data.qpos[0]),
                "foot_l_z": float(foot_l[2]), "foot_r_z": float(foot_r[2]),
                "foot_l_x_rel": float(foot_l[0] - data.qpos[0]), "foot_r_x_rel": float(foot_r[0] - data.qpos[0]),
            }
            for joint in ("hip_pitch", "knee", "ankle"):
                j_st = self._idx[st][joint]
                row[f"tau_st_{joint}"] = float(tau[j_st])
                row[f"lim_st_{joint}"] = float(self.tau_lim[j_st])
                j_sw = self._idx[sw][joint]
                row[f"tau_sw_{joint}"] = float(tau[j_sw])
            self.rows.append(row)
        return tau


def run_instrumented(gait: GaitParams) -> tuple[dict, list[dict]]:
    with raibert_factory(InstrumentedRaibert):
        session = walk_session(gait)
        t0 = session.sim_t
        fall_t = None
        while session.sim_t < t0 + OBSERVE_S - 1e-9:
            session._advance_sim(min(TICK_S, t0 + OBSERVE_S - session.sim_t))
            if session.controller.state == "FALLEN":
                fall_t = session.sim_t
                # 再跑 0.3 s 看倒下的姿態，然後停
                session._advance_sim(0.3)
                break
        ctrl = session.controller
        events = [d for d in ctrl.decisions if d.get("kind") in ("first", "td", "hurry", "hip", "fall", "mode")]
        return {
            "fall_t_after_walk_s": None if fall_t is None else round(fall_t - t0, 3),
            "steps": int(ctrl.n_steps),
            "events": events,
        }, ctrl.rows


# ---------------------------------------------------------------- B. 消融

def run_variant(name: str, overrides: dict, gait_overrides: dict) -> dict:
    gait = task_gait(**gait_overrides)
    cls = make_variant_class(overrides)
    with raibert_factory(cls):
        session = walk_session(gait)
        t0 = session.sim_t
        x0 = float(session.data.qpos[0])
        fall_t = None
        knee_sat_ticks = 0
        max_abs_pitch = 0.0
        idx_knee = [JOINT_ORDER.index("knee_l"), JOINT_ORDER.index("knee_r")]
        while session.sim_t < t0 + OBSERVE_S - 1e-9:
            session._advance_sim(min(TICK_S, t0 + OBSERVE_S - session.sim_t))
            ctrl = session.controller
            pitch, _ = quat_to_pitch_roll(session.data.qpos[3:7])
            max_abs_pitch = max(max_abs_pitch, abs(float(np.degrees(pitch))))
            tau = session.data.ctrl
            if any(abs(tau[j]) >= 0.95 * ctrl.tau_lim[j] for j in idx_knee):
                knee_sat_ticks += 1
            if ctrl.state == "FALLEN":
                fall_t = session.sim_t
                break
        ctrl = session.controller
        td = [d for d in ctrl.decisions if d.get("kind") == "td"]
        return {
            "variant": name,
            "overrides": {k: v for k, v in overrides.items()},
            "gait_overrides": gait_overrides,
            "upright_s": round(float((fall_t or (t0 + OBSERVE_S)) - t0), 3),
            "fell": fall_t is not None,
            "steps": int(ctrl.n_steps),
            "distance_m": round(float(session.data.qpos[0]) - x0, 3),
            "max_abs_pitch_deg": round(max_abs_pitch, 1),
            "knee_sat_ticks_20ms": knee_sat_ticks,
            "touchdowns_logged": [d["text"] for d in td][:6],
        }


def run_task_with(overrides: dict, gait_overrides: dict) -> dict:
    """站滿 6 s 的變體再跑凍結任務（任務 gait 由契約決定，gait 覆寫在此無效）。"""
    cls = make_variant_class(overrides)
    with raibert_factory(cls):
        session = LiveSession(default_robot(), GaitParams(), [])
        started = session.command({"type": "task_start", "task_id": TASK_ID})
        if isinstance(started, dict) and started.get("type") == "error":
            return {"error": started["code"]}
        while session.motion_task.active:
            session._advance_sim(0.2)
        ev = session.last_task_result["evaluation"]
        return {
            "run_id": session.last_trace_receipt["run_id"],
            "status": ev["status"],
            "passed_count": sum(1 for c in ev["criteria"] if c["passed"]),
            "first_fall_time_s": session.last_trace_receipt["summary"]["first_fall_time_s"],
            "failed": [{"id": c["id"], "value": c["value"]} for c in ev["criteria"] if not c["passed"]],
        }


# ---------------------------------------------------------------- 圖

def fig_timeline(rows: list[dict], events: list[dict], out: Path, title: str) -> None:
    t = np.array([r["t"] for r in rows]) - rows[0]["t"]
    def col(k): return np.array([r[k] for r in rows], dtype=float)
    fig, axes = plt.subplots(6, 1, figsize=(11, 13), sharex=True)
    ev_td = [d["t"] - rows[0]["t"] + 0 for d in events if d["kind"] == "td"]
    ev_first = [d["t"] - rows[0]["t"] for d in events if d["kind"] == "first"]
    ev_fall = [d["t"] - rows[0]["t"] for d in events if d["kind"] == "fall"]
    ev_hurry = [d["t"] - rows[0]["t"] for d in events if d["kind"] == "hurry"]

    def marks(ax):
        for x in ev_first: ax.axvline(x, color="#2ca02c", ls="--", lw=1)
        for x in ev_td: ax.axvline(x, color="#1f77b4", ls=":", lw=1)
        for x in ev_hurry: ax.axvline(x, color="#ff7f0e", ls="-.", lw=1)
        for x in ev_fall: ax.axvline(x, color="#d62728", lw=1.5)

    ax = axes[0]
    ax.plot(t, col("pitch_deg"), color="#d62728", label="軀幹 pitch")
    ax.plot(t, col("roll_deg"), color="#9467bd", label="軀幹 roll")
    ax.axhline(15, color="#999", ls=":"); ax.axhline(-15, color="#999", ls=":")
    ax.set_ylabel("°"); ax.set_ylim(-60, 60); ax.legend(fontsize=8, loc="upper left"); marks(ax)
    ax.set_title(title)

    ax = axes[1]
    ax.plot(t, col("vx"), color="#1f77b4", label="vx（濾波）")
    ax.axhline(0.7, color="#2ca02c", ls="--", lw=1, label="v_des 0.7")
    ax.set_ylabel("m/s"); ax.legend(fontsize=8, loc="upper left"); marks(ax)

    ax = axes[2]
    ax.plot(t, col("foot_l_z"), color="#17becf", label="左腳 z")
    ax.plot(t, col("foot_r_z"), color="#bcbd22", label="右腳 z")
    cl = col("contact_l"); cr = col("contact_r")
    ax.fill_between(t, 0, 0.01, where=cl > 0.5, color="#17becf", alpha=0.35, step="mid")
    ax.fill_between(t, -0.012, -0.002, where=cr > 0.5, color="#bcbd22", alpha=0.35, step="mid")
    ax.set_ylabel("m（色帶 = 接觸）"); ax.legend(fontsize=8, loc="upper left"); marks(ax)

    ax = axes[3]
    ax.plot(t, col("phase"), color="#7f7f7f", label="相位")
    st = np.array([1.0 if r["stance"] == "l" else 0.0 for r in rows])
    ax.step(t, st * 0.2 + 1.05, color="#17becf", lw=1, label="支撐腳 = L（高）／R（低）")
    ax.plot(t, col("p_land_x_rel"), color="#8c564b", label="落點 x - 骨盆 x")
    ax.plot(t, col("stance_ankle_x_rel"), color="#e377c2", label="支撐踝 x - 骨盆 x")
    ax.set_ylabel("相位／m"); ax.legend(fontsize=8, loc="upper left", ncol=2); marks(ax)

    ax = axes[4]
    for joint, color in (("hip_pitch", "#d62728"), ("knee", "#1f77b4"), ("ankle", "#2ca02c")):
        ax.plot(t, col(f"tau_st_{joint}"), color=color, label=f"支撐 {joint} τ")
        ax.plot(t, col(f"lim_st_{joint}"), color=color, ls=":", lw=0.8)
        ax.plot(t, -col(f"lim_st_{joint}"), color=color, ls=":", lw=0.8)
    ax.set_ylabel("N·m（虛線 = 上限）"); ax.legend(fontsize=8, loc="upper left", ncol=3); marks(ax)

    ax = axes[5]
    ax.plot(t, col("hip_corr"), color="#d62728", label="髖 pitch 修正")
    ax.plot(t, col("roll_corr"), color="#9467bd", label="髖 roll 修正")
    ax.plot(t, col("ankle_corr"), color="#2ca02c", label="踝策略")
    ax.axhline(110, color="#d62728", ls=":", lw=0.8); ax.axhline(-110, color="#d62728", ls=":", lw=0.8)
    ax.set_ylabel("N·m"); ax.set_xlabel("行走開始後時間 (s)"); ax.legend(fontsize=8, loc="upper left", ncol=3); marks(ax)
    axes[-1].text(0.995, 0.02, "綠虛線 = 起步；藍點線 = 觸地；橘點劃線 = 加速換步；紅線 = 跌倒",
                  transform=axes[-1].transAxes, ha="right", va="bottom", fontsize=8, color="#555")
    fig.tight_layout()
    fig.savefig(out, dpi=130)
    plt.close(fig)


def fig_ablation(results: list[dict], out: Path) -> None:
    base = next(r for r in results if r["variant"] == "baseline")
    rows = sorted(results, key=lambda r: r["upright_s"])
    fig, ax = plt.subplots(figsize=(10, 0.28 * len(rows) + 1.6))
    y = np.arange(len(rows))
    colors = ["#2ca02c" if not r["fell"] else ("#1f77b4" if r["upright_s"] > base["upright_s"] + 0.3 else
              ("#d62728" if r["upright_s"] < base["upright_s"] - 0.3 else "#9e9e9e")) for r in rows]
    ax.barh(y, [r["upright_s"] for r in rows], color=colors)
    ax.axvline(base["upright_s"], color="#333", ls="--", lw=1, label=f"baseline {base['upright_s']:.2f} s")
    ax.set_yticks(y)
    ax.set_yticklabels([f"{r['variant']}  （{r['steps']} 步，{r['distance_m']:+.2f} m）" for r in rows], fontsize=8)
    ax.set_xlabel(f"行走模式站立秒數（上限 {OBSERVE_S:.0f} s；綠 = 站滿、藍 = 比 baseline 多 0.3 s 以上、紅 = 少 0.3 s 以上）")
    ax.set_xlim(0, OBSERVE_S + 0.3)
    ax.set_title("B. 單因子消融：每個變體只改一個常數（或一個 gait 參數）")
    ax.legend(fontsize=8, loc="lower right")
    ax.grid(axis="x", alpha=0.3)
    fig.tight_layout()
    fig.savefig(out, dpi=130)
    plt.close(fig)


# ---------------------------------------------------------------- 主流程

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--skip-task", action="store_true")
    args = parser.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    _cjk_font()
    t_start = time.time()

    print("== A. 儀器化基準 ==", flush=True)
    base_info, rows = run_instrumented(task_gait())
    print(f"  fall after walk start: {base_info['fall_t_after_walk_s']} s, steps {base_info['steps']}")
    for e in base_info["events"]:
        print(f"    {e['t']:.3f} {e['kind']:6s} {e['text'][:80]}")
    fig_timeline(rows, base_info["events"], out / "fig1_baseline_timeline.png",
                 "A. Raibert 基準（任務 gait、行走模式、assist 關）：從起步到跌倒的內部狀態")
    (out / "baseline_timeline.csv").write_text(
        ",".join(rows[0].keys()) + "\n" + "\n".join(",".join(str(r[k]) for k in rows[0]) for r in rows[::5]) + "\n",
        encoding="utf-8")

    print("== B. 單因子消融 ==", flush=True)
    results = []
    for name, ov, gov in VARIANTS:
        r = run_variant(name, ov, gov)
        results.append(r)
        print(f"  {name:26s} upright={r['upright_s']:5.2f}  steps={r['steps']:2d}  dist={r['distance_m']:+.2f}  "
              f"maxpitch={r['max_abs_pitch_deg']:5.1f}  knee_sat={r['knee_sat_ticks_20ms']}", flush=True)
    # 事後加的一段（規則在看到單因子結果後才定，據實揭露）：取站立秒數最高的三個
    # 控制器常數變體（排除 gait 變體），兩兩與三個一起組合，看效果是否可加。
    print("== B2. 前三名的兩兩／三者組合 ==", flush=True)
    singles = [r for r in results if r["variant"] != "baseline" and not r["gait_overrides"]]
    top3 = sorted(singles, key=lambda r: -r["upright_s"])[:3]
    by_name = {v[0]: v for v in VARIANTS}
    import itertools
    combos = [c for k in (2, 3) for c in itertools.combinations([t["variant"] for t in top3], k)]
    for combo in combos:
        ov = {}
        for name in combo:
            ov.update(by_name[name][1])
        name = "combo:" + "+".join(combo)
        r = run_variant(name, ov, {})
        results.append(r)
        VARIANTS.append((name, ov, {}))
        print(f"  {name:60s} upright={r['upright_s']:5.2f}  steps={r['steps']:2d}  dist={r['distance_m']:+.2f}", flush=True)
    fig_ablation(results, out / "fig2_ablation.png")

    survivors = [r for r in results if not r["fell"] and r["variant"] != "baseline"]
    task_rows = []
    if survivors and not args.skip_task:
        print("== C. 站滿 6 s 的變體跑凍結任務 ==", flush=True)
        for r in survivors:
            name = r["variant"]
            ov = next(v for v in VARIANTS if v[0] == name)[1]
            gov = next(v for v in VARIANTS if v[0] == name)[2]
            if gov:
                print(f"  {name}: gait 變體不能改凍結任務的 gait，略過任務")
                continue
            tr = run_task_with(ov, gov)
            tr["variant"] = name
            task_rows.append(tr)
            print(f"  {name:26s} {tr.get('status')} {tr.get('passed_count')}/11 fall={tr.get('first_fall_time_s')} "
                  f"failed={[f['id'] for f in tr.get('failed', [])]}", flush=True)
        # 站滿的第一個變體也畫一張時間線
        first = survivors[0]
        ov = next(v for v in VARIANTS if v[0] == first["variant"])[1]
        gov = next(v for v in VARIANTS if v[0] == first["variant"])[2]
        cls = make_variant_class(ov)
        class InstrumentedVariant(InstrumentedRaibert, cls):  # type: ignore[misc, valid-type]
            pass
        with raibert_factory(InstrumentedVariant):
            session = walk_session(task_gait(**gov))
            t0 = session.sim_t
            while session.sim_t < t0 + OBSERVE_S - 1e-9 and session.controller.state != "FALLEN":
                session._advance_sim(TICK_S)
            ev = [d for d in session.controller.decisions if d.get("kind") in ("first", "td", "hurry", "hip", "fall")]
            fig_timeline(session.controller.rows, ev, out / "fig3_survivor_timeline.png",
                         f"C. 站滿 6 s 的變體 {first['variant']} 的內部狀態")

    summary = {
        "schema": "RAIBERT_STACK_DIAGNOSIS_V1",
        "nature": "DEVELOPMENT_DIAGNOSIS_ONLY",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git_head": _git_head(),
        "python": platform.python_version(),
        "code_sha256": {n: _sha256(HERE / n) for n in CODE_FILES if (HERE / n).exists()},
        "gait": task_gait().model_dump(mode="json"),
        "observe_s": OBSERVE_S,
        "baseline": {k: v for k, v in base_info.items() if k != "events"},
        "baseline_events": [{"t": e["t"], "kind": e["kind"], "text": e["text"]} for e in base_info["events"]],
        "ablation": results,
        "task_on_survivors": task_rows,
        "wall_s_total": round(time.time() - t_start, 1),
    }
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"寫入 {out}（{summary['wall_s_total']} s）")
    return 0


if __name__ == "__main__":
    sys.exit(main())

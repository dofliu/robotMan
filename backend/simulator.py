"""模擬管線：運動學步態 → 有限差分速度/加速度 → MuJoCo 逆動力學
→ 解析地面反力分配 → 關節/馬達端扭矩與能耗 → 感測器 raycast。
"""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import uuid

import numpy as np
import mujoco
from config_schema import SimRequest
from model_builder import build_mjcf, geom_render_list, JOINT_ORDER, JOINT_GROUP
from gait import GaitEngine

DT = 1.0 / 120.0        # 內部計算頻率（有限差分用）
DECIM = 2               # 輸出降頻 → 60 fps
RAY_ANGLES_DEG = [5, -5, -15, -28, -42, -58, -75]   # 感測器射線俯仰角（相對水平）
RAY_MAX = 4.0           # 射線最大距離 m
G = 9.81
SIMULATION_CLASS = "KINEMATIC_INVERSE_DYNAMICS_ESTIMATE"
PROVENANCE_SCHEMA_VERSION = "1.0"
METRIC_SET_VERSION = "ANALYSIS_METRICS_V1"
PROVENANCE_CODE_FILES = (
    "simulator.py", "gait.py", "model_builder.py", "config_schema.py", "hardware_db.py",
)


def _r(arr, nd=4):
    """四捨五入後轉 list，縮小 JSON 體積。"""
    return np.round(np.asarray(arr), nd).tolist()


def _canonical_hash(value) -> str:
    """對 JSON-safe 結構產生跨執行穩定的 SHA-256。"""
    raw = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(raw).hexdigest()}"


def _code_hash() -> str | None:
    """雜湊實際參與此管線的本機原始碼；無法讀取時誠實回傳 null。"""
    try:
        base = Path(__file__).resolve().parent
        h = hashlib.sha256()
        for name in PROVENANCE_CODE_FILES:
            p = base / name
            h.update(name.encode("utf-8"))
            h.update(b"\0")
            h.update(p.read_bytes())
            h.update(b"\0")
        return f"sha256:{h.hexdigest()}"
    except OSError:
        return None


def _enum_name(enum_type, value) -> str:
    try:
        return enum_type(int(value)).name
    except (TypeError, ValueError):
        return str(int(value))


def _actual_motion_metrics(times: np.ndarray, qpos: np.ndarray,
                           power_elec: np.ndarray, total_mass: float) -> dict:
    """以實際 root 軌跡與實際 sampled elapsed time 計算運動/能耗指標。"""
    elapsed = float(times[-1] - times[0]) if len(times) >= 2 else 0.0
    net_x = float(qpos[-1, 0] - qpos[0, 0]) if len(qpos) >= 2 else 0.0
    # distance 定義為實際淨前進距離；倒退不冒充已完成的前進任務。
    distance = max(net_x, 0.0)
    p_total = np.sum(power_elec, axis=1)
    if len(times) >= 2:
        dt = np.diff(times)
        energy = float(np.sum(0.5 * (p_total[1:] + p_total[:-1]) * dt))
    else:
        energy = 0.0
    avg_speed = distance / elapsed if elapsed > 0.0 else 0.0
    avg_power = energy / elapsed if elapsed > 0.0 else 0.0
    cot = energy / (total_mass * G * distance) if distance > 1e-9 else None
    return {
        "elapsed_time_s": elapsed,
        "net_displacement_m": net_x,
        "distance_m": distance,
        "avg_speed_mps": avg_speed,
        "energy_J": energy,
        "avg_power_W": avg_power,
        "cot": cot,
    }


def _convex_hull(pts: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Andrew monotone chain，回傳逆時針凸包頂點。"""
    pts = sorted(set(pts))
    if len(pts) <= 2:
        return pts
    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def _signed_margin(hull: list[tuple[float, float]], p: tuple[float, float]) -> float | None:
    """點到凸多邊形邊界的有號距離：內部為正、外部為負。"""
    n = len(hull)
    if n < 3:
        return None
    m = np.inf
    for i in range(n):
        ax, ay = hull[i]
        bx, by = hull[(i + 1) % n]
        ex, ey = bx - ax, by - ay
        L = np.hypot(ex, ey)
        if L < 1e-9:
            continue
        # 逆時針多邊形：cross > 0 表示點在邊的內側
        d = (ex * (p[1] - ay) - ey * (p[0] - ax)) / L
        m = min(m, d)
    return float(m)


def run_simulation(req: SimRequest) -> dict:
    cfg, gait, obstacles = req.robot, req.gait, req.obstacles
    model_xml = build_mjcf(cfg, obstacles, dynamic=False)
    model = mujoco.MjModel.from_xml_string(model_xml)
    data = mujoco.MjData(model)
    engine = GaitEngine(cfg, gait, obstacles)

    config_hash = _canonical_hash(req.model_dump(mode="json"))
    model_hash = f"sha256:{hashlib.sha256(model_xml.encode('utf-8')).hexdigest()}"
    code_hash = _code_hash()

    nq, nv = model.nq, model.nv
    n_frames = int(gait.duration / DT)
    times = np.arange(n_frames) * DT

    # ---------- 質心目標軌跡：ZMP 參考 → cart-table 反解 ----------
    # 矢狀面採標準 ZMP 步態生成：ZMP 參考跟隨支撐腳 CoP（含腳跟→腳尖
    # 前移與雙支撐轉移），由 cart-table 模型 com - (z/g)·com̈ = zmp 的
    # 頻域轉移函數反解質心 x 微振盪。如此質心動力學與腳掌支撐一致，
    # 讓水平反力與 ZMP reference 在目前 cart-table screening model 內自洽；
    # 這不是 contact solver 或實體量測驗證。
    base = np.array([engine.base_x(t) for t in times])
    w_l = np.array([engine.contact_weight("l", t) for t in times])
    w_r = np.array([engine.contact_weight("r", t) for t in times])
    foot_cx = cfg.dims.foot_len / 2 - 0.06
    cop_back, cop_front = -0.25 * cfg.dims.foot_len, 0.35 * cfg.dims.foot_len

    zmp_ref = np.full(n_frames, np.nan)
    for i, t in enumerate(times):
        num, den = 0.0, 0.0
        for side, w in (("l", w_l[i]), ("r", w_r[i])):
            if w > 1e-6:
                tgt, _ = engine.foot_target(side, t)
                prog = engine.stance_progress(side, t)
                cop = cop_back + (cop_front - cop_back) * (prog if prog is not None else 0.5)
                num += w * (tgt[0] + foot_cx + cop)
                den += w
        if den > 1e-6:
            zmp_ref[i] = num / den
    # 騰空期無支撐：線性補間（cart-table 於騰空期本就不適用）
    nanmask = np.isnan(zmp_ref)
    if nanmask.any():
        zmp_ref[nanmask] = np.interp(times[nanmask], times[~nanmask], zmp_ref[~nanmask])

    kk_ref = np.exp(-0.5 * (np.arange(-5, 6) / 2.0) ** 2)
    kk_ref /= kk_ref.sum()

    # 頻域求解 c(t)：com = base + c 代入 com - (z/g)·com̈ = zmp_ref
    # → c - (z/g)·c̈ = zmp_ref - base + (z/g)·b̈ase
    # base 的加速度項不可省略：跨越/停止時骨盆減速會直接漂移 ZMP
    z_bar = engine.z_nom * 0.95               # 質心平均高度（略低於骨盆）
    base_acc = np.zeros_like(base)
    base_acc[1:-1] = (base[2:] - 2 * base[1:-1] + base[:-2]) / DT**2
    base_acc[0], base_acc[-1] = base_acc[1], base_acc[-2]
    base_acc = np.convolve(base_acc, kk_ref, mode="same")
    delta = zmp_ref - base + (z_bar / G) * base_acc
    pad = n_frames // 2
    dpad = np.concatenate([delta[pad:0:-1], delta, delta[-2:-pad - 2:-1]])
    freq = np.fft.rfftfreq(len(dpad), DT)
    H = 1.0 / (1.0 + (z_bar / G) * (2 * np.pi * freq) ** 2)
    cpad = np.fft.irfft(np.fft.rfft(dpad) * H, len(dpad))
    c_osc = cpad[pad:pad + n_frames]

    # ---------- 迭代：把全身質心 x 逼近目標軌跡 base + c(t) ----------
    qpos = np.zeros((n_frames, nq))
    com_x = np.zeros(n_frames)
    for it in range(8):
        for i, t in enumerate(times):
            qpos[i] = engine.qpos_at(t, nq)
        for i in range(n_frames):
            data.qpos[:] = qpos[i]
            mujoco.mj_kinematics(model, data)
            mujoco.mj_comPos(model, data)
            com_x[i] = data.subtree_com[0][0]
        trend = base + c_osc + np.mean(com_x - base - c_osc)
        dev = com_x - trend
        # 不可平滑 dev：cart-table 放大係數 ~(1+zω²/g)，高頻殘差
        # 會被放大 15 倍以上成為 ZMP 誤差；只用 tanh 平滑限幅
        prev = np.interp(times, engine._corr_t, engine._corr_x) if engine._corr_x is not None else 0.0
        total = prev + dev
        engine.set_x_correction(times, 0.12 * np.tanh(total / 0.12))
        if np.abs(dev).max() < 5e-4:
            break
    for i, t in enumerate(times):
        qpos[i] = engine.qpos_at(t, nq)

    # ---------- 有限差分：qvel / qacc（mj_differentiatePos 正確處理四元數） ----------
    qvel_fwd = np.zeros((n_frames, nv))
    for i in range(n_frames - 1):
        mujoco.mj_differentiatePos(model, qvel_fwd[i], DT, qpos[i], qpos[i + 1])
    qvel_fwd[-1] = qvel_fwd[-2]

    qvel = np.zeros((n_frames, nv))
    qvel[1:-1] = 0.5 * (qvel_fwd[1:-1] + qvel_fwd[0:-2])
    qvel[0], qvel[-1] = qvel_fwd[0], qvel_fwd[-1]

    qacc = np.zeros((n_frames, nv))
    qacc[1:-1] = (qvel_fwd[1:-1] - qvel_fwd[0:-2]) / DT
    qacc[0], qacc[-1] = qacc[1], qacc[-2]

    # ---------- Pass A：純運動學（質心、腳底、感測器原點） ----------
    site_l = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_SITE, "sole_l")
    site_r = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_SITE, "sole_r")
    site_lidar = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_SITE, "lidar")

    com = np.zeros((n_frames, 3))
    n_body = model.nbody - 1                 # 排除 world body
    xpos = np.zeros((n_frames, n_body, 3))
    xquat = np.zeros((n_frames, n_body, 4))
    lidar_pos = np.zeros((n_frames, 3))
    lidar_mat = np.zeros((n_frames, 9))
    sole_pos = {"l": np.zeros((n_frames, 3)), "r": np.zeros((n_frames, 3))}

    for i in range(n_frames):
        data.qpos[:] = qpos[i]
        mujoco.mj_kinematics(model, data)
        mujoco.mj_comPos(model, data)
        com[i] = data.subtree_com[0]
        xpos[i] = data.xpos[1:]
        xquat[i] = data.xquat[1:]
        lidar_pos[i] = data.site_xpos[site_lidar]
        lidar_mat[i] = data.site_xmat[site_lidar]
        sole_pos["l"][i] = data.site_xpos[site_l]
        sole_pos["r"][i] = data.site_xpos[site_r]

    # ---------- 地面反力（解析）：F = M·(a_com + g)，依接觸排程分配左右腳 ----------
    M_total = float(np.sum(model.body_mass))
    a_com = np.zeros_like(com)
    a_com[1:-1] = (com[2:] - 2 * com[1:-1] + com[:-2]) / DT**2
    a_com[0], a_com[-1] = a_com[1], a_com[-2]
    # 極小幅高斯平滑（σ≈8ms）：消除有限差分尖峰。σ 不能再大，
    # 否則重心轉移瞬間的 ZMP 會出現相位延遲、被誤判為超出支撐面
    kk = np.exp(-0.5 * (np.arange(-3, 4) / 1.0) ** 2)
    kk /= kk.sum()
    for ax in range(3):
        a_com[:, ax] = np.convolve(a_com[:, ax], kk, mode="same")

    wsum = w_l + w_r
    F_total = M_total * (a_com + np.array([0.0, 0.0, G]))
    F_total[:, 2] = np.maximum(F_total[:, 2], 0.0)   # 地面不能拉住腳
    with np.errstate(invalid="ignore", divide="ignore"):
        share_l = np.where(wsum > 1e-6, w_l / np.maximum(wsum, 1e-6), 0.0)
        share_r = np.where(wsum > 1e-6, w_r / np.maximum(wsum, 1e-6), 0.0)
    grf_l = F_total * share_l[:, None]
    grf_r = F_total * share_r[:, None]

    # ---------- ZMP（cart-table 模型） ----------
    # 只在「有支撐」且垂直加速度分母遠離零時定義：騰空期或分母趨零時
    # ZMP 無物理意義（數值上會發散）
    zmp = np.full((n_frames, 2), np.nan)
    denom = a_com[:, 2] + G
    ok = (denom > 3.0) & (wsum > 0.05)
    zmp[ok, 0] = com[ok, 0] - com[ok, 2] * a_com[ok, 0] / denom[ok]
    zmp[ok, 1] = com[ok, 1] - com[ok, 2] * a_com[ok, 1] / denom[ok]

    # ---------- 穩定性分析：ZMP / CoM 對支撐多邊形的裕度 ----------
    # 支撐多邊形 = 當下排程承重腳掌的凸包；ZMP 出界只代表目前 model
    # indicator 未通過，不能單獨推論實體機器人會傾倒。
    # CoM 投影裕度是「靜態穩定」指標（慢速步態適用）。
    hx = cfg.dims.foot_len / 2
    hy = 0.055                                # 腳掌半寬（geom 0.045 + 邊緣餘裕）
    zmp_margin = np.full(n_frames, np.nan)
    com_margin = np.full(n_frames, np.nan)
    hulls: list[list[tuple[float, float]]] = []
    for i in range(n_frames):
        pts: list[tuple[float, float]] = []
        for side, w in (("l", w_l[i]), ("r", w_r[i])):
            if w > 0.05:
                cx, cy = float(sole_pos[side][i][0]), float(sole_pos[side][i][1])
                pts += [(round(cx - hx, 4), round(cy - hy, 4)),
                        (round(cx + hx, 4), round(cy - hy, 4)),
                        (round(cx + hx, 4), round(cy + hy, 4)),
                        (round(cx - hx, 4), round(cy + hy, 4))]
        hull = _convex_hull(pts) if pts else []
        hulls.append(hull)
        if hull:
            if not np.isnan(zmp[i, 0]):
                m = _signed_margin(hull, (float(zmp[i, 0]), float(zmp[i, 1])))
                if m is not None:
                    zmp_margin[i] = m
            m = _signed_margin(hull, (float(com[i, 0]), float(com[i, 1])))
            if m is not None:
                com_margin[i] = m

    # ---------- Pass B：逆動力學 + 接觸力扣除 → 關節扭矩 ----------
    # GRF 作用點採腳跟→腳尖的 heuristic CoP 前移規則；尚未由 force-plate
    # 或 contact solver 校準，僅用於 current-model sensitivity screening。
    nj = len(JOINT_ORDER)
    tau = np.zeros((n_frames, nj))
    jacp = np.zeros((3, nv))
    body_foot = {
        "l": mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "foot_l"),
        "r": mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "foot_r"),
    }
    site_sole = {"l": site_l, "r": site_r}
    # CoP 偏移沿用 ZMP 參考所使用的同一組（隨腳掌長度縮放），保持一致

    for i in range(n_frames):
        data.qpos[:] = qpos[i]
        data.qvel[:] = qvel[i]
        data.qacc[:] = qacc[i]
        mujoco.mj_inverse(model, data)
        qfrc = data.qfrc_inverse.copy()
        t = times[i]
        for side, F in (("l", grf_l[i]), ("r", grf_r[i])):
            if abs(F[2]) < 1e-9:
                continue
            prog = engine.stance_progress(side, t)
            cop_x = cop_back + (cop_front - cop_back) * (prog if prog is not None else 0.5)
            point = data.site_xpos[site_sole[side]] + np.array([cop_x, 0.0, 0.0])
            mujoco.mj_jac(model, data, jacp, None, point, body_foot[side])
            qfrc -= jacp.T @ F
        tau[i] = qfrc[6:]

    qd_j = qvel[:, 6:]                        # 各關節角速度（rad/s）

    # ---------- 馬達端換算 ----------
    tau_motor = np.zeros_like(tau)
    util = np.zeros_like(tau)                 # 相對額定扭矩
    speed_rpm = np.zeros_like(tau)
    power_elec = np.zeros_like(tau)

    specs = []
    for j, name in enumerate(JOINT_ORDER):
        a = cfg.actuators[JOINT_GROUP[name]]
        specs.append(a)
        N, eg, em = a.gear.ratio, a.gear.efficiency, a.motor.efficiency
        P_mech = tau[:, j] * qd_j[:, j]
        driving = P_mech > 0
        # 驅動：馬達需克服減速機損耗；被動（背驅）：損耗反而幫忙制動
        tau_motor[:, j] = np.where(driving, tau[:, j] / (N * eg), tau[:, j] * eg / N)
        speed_rpm[:, j] = np.abs(qd_j[:, j]) * N * 60 / (2 * np.pi)
        util[:, j] = np.abs(tau_motor[:, j]) / a.motor.rated_torque
        power_elec[:, j] = np.where(driving, P_mech / (eg * em), 0.0)  # 不考慮能量回收

    # ---------- 感測器 raycast（僅偵測環境：geom group 2） ----------
    out_idx = np.arange(0, n_frames, DECIM)
    n_out = len(out_idx)
    angles = np.deg2rad(RAY_ANGLES_DEG)
    n_rays = len(angles)
    ray_hits = np.zeros((n_out, n_rays, 3))
    ray_dists = np.full((n_out, n_rays), RAY_MAX)
    n_obs = len(obstacles)
    detected = np.zeros((n_out, n_obs), dtype=int)
    geomgroup = np.array([0, 0, 1, 0, 0, 0], dtype=np.uint8)
    geomid_out = np.zeros(1, dtype=np.int32)

    obs_geom_ids = {}
    for oi in range(n_obs):
        gid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, f"obstacle_{oi}")
        obs_geom_ids[gid] = oi

    for k, i in enumerate(out_idx):
        data.qpos[:] = qpos[i]
        mujoco.mj_kinematics(model, data)
        R = lidar_mat[i].reshape(3, 3)
        origin = lidar_pos[i]
        for ri, ang in enumerate(angles):
            d_local = np.array([np.cos(ang), 0.0, np.sin(ang)])
            d_world = R @ d_local
            dist = mujoco.mj_ray(model, data, origin, d_world, geomgroup, 1, -1, geomid_out)
            if dist < 0 or dist > RAY_MAX:
                dist = RAY_MAX
                gid = -1
            else:
                gid = int(geomid_out[0])
            ray_dists[k, ri] = dist
            ray_hits[k, ri] = origin + d_world * dist
            if gid in obs_geom_ids and dist < 3.0:
                detected[k, obs_geom_ids[gid]] = 1

    # ---------- 統計 ----------
    # 能耗、距離、平均速度與 CoT 使用完整「實際軌跡／實際 elapsed time」。
    # 關節峰值/RMS 仍使用穩態窗，避免把起停暫態混入持續額定需求。
    t_steady = min(2 * engine.T, gait.duration * 0.5)
    # 尾端排除一個週期：FFT 鏡射填補與有限差分的邊界效應集中在結尾
    st = (times >= t_steady) & (times <= gait.duration - engine.T)
    warnings: list[str] = []
    if st.any():
        stats_window_mode = "steady_window"
    else:
        # 短時模擬或長週期可能沒有穩態窗。不可靜默回傳全零需求；P0 採
        # 完整 sampled window fallback，並在 warning/provenance 中明示。
        st = np.ones(n_frames, dtype=bool)
        stats_window_mode = "full_window_fallback"
        warnings.append(
            "⚠️ 致動器穩態統計窗不可用：模擬時長不足以排除起迄週期；"
            "已改用完整 sampled window，結果包含暫態且不得解讀為穩態額定需求"
        )
    motion = _actual_motion_metrics(times, qpos, power_elec, M_total)
    E_total = motion["energy_J"]
    cot = motion["cot"]

    if cot is None:
        warnings.append(
            "⚠️ CoT 無法計算：實際淨前進距離為 0 m；已回傳 null，未使用命令速度替代"
        )
    group_stats = {}
    for grp in cfg.actuators:
        idxs = [j for j, n in enumerate(JOINT_ORDER) if JOINT_GROUP[n] == grp]
        a = cfg.actuators[grp]
        tm = np.abs(tau_motor[st][:, idxs])
        tj = np.abs(tau[st][:, idxs])
        sp = speed_rpm[st][:, idxs]
        # peak_* 必須是真正 sampled maximum，供 fail-closed threshold 使用。
        # p99_5_* 另列為 descriptive statistic，不能冒充 feasibility peak。
        peak_tm = float(tm.max()) if tm.size else 0.0
        peak_tj = float(tj.max()) if tj.size else 0.0
        p99_5_tm = float(np.percentile(tm, 99.5)) if tm.size else 0.0
        p99_5_tj = float(np.percentile(tj, 99.5)) if tj.size else 0.0
        rms_tm = float(np.sqrt(np.mean(tm**2))) if tm.size else 0.0
        peak_sp = float(sp.max()) if sp.size else 0.0
        p99_5_sp = float(np.percentile(sp, 99.5)) if sp.size else 0.0
        group_stats[grp] = {
            "peak_tau_joint": round(peak_tj, 2),
            "peak_tau_motor": round(peak_tm, 3),
            "p99_5_tau_joint": round(p99_5_tj, 2),
            "p99_5_tau_motor": round(p99_5_tm, 3),
            "rms_tau_motor": round(rms_tm, 3),
            "peak_util_pct": round(100 * peak_tm / a.motor.rated_torque, 1),
            "p99_5_util_pct": round(100 * p99_5_tm / a.motor.rated_torque, 1),
            "rms_util_pct": round(100 * rms_tm / a.motor.rated_torque, 1),
            "peak_vs_peak_pct": round(100 * peak_tm / a.motor.peak_torque, 1),
            "p99_5_vs_peak_pct": round(100 * p99_5_tm / a.motor.peak_torque, 1),
            "peak_speed_rpm": round(peak_sp, 0),
            "p99_5_speed_rpm": round(p99_5_sp, 0),
            "speed_util_pct": round(100 * peak_sp / a.motor.rated_speed_rpm, 1),
            "p99_5_speed_util_pct": round(100 * p99_5_sp / a.motor.rated_speed_rpm, 1),
            "gearbox_util_pct": round(100 * peak_tj / a.gear.rated_torque_out, 1),
            "p99_5_gearbox_util_pct": round(100 * p99_5_tj / a.gear.rated_torque_out, 1),
        }
        gname = f"{grp}（{a.motor.name} + {a.gear.name}）"
        if peak_tm > a.motor.peak_torque:
            warnings.append(
                f"⛔ {gname}：目前估算扭矩為所填馬達峰值的 "
                f"{round(100*peak_tm/a.motor.peak_torque)}% — CURRENT_MODEL_ACTUATOR_SCREEN=INFEASIBLE"
            )
        elif rms_tm > a.motor.rated_torque:
            warnings.append(
                f"⚠️ {gname}：目前估算 RMS 扭矩為所填額定值的 "
                f"{round(100*rms_tm/a.motor.rated_torque)}%；thermal state/允許持續時間未建模，"
                "THERMAL_CAPABILITY=UNRESOLVED"
            )
        elif peak_tm > a.motor.rated_torque:
            warnings.append(
                f"🔶 {gname}：目前估算峰值扭矩為所填持續額定值的 "
                f"{round(100*peak_tm/a.motor.rated_torque)}%；未提供 peak-duration/thermal curve，"
                "允許持續時間不可判定"
            )
        if peak_sp > a.motor.rated_speed_rpm:
            warnings.append(
                f"⛔ {gname}：目前估算轉速 {round(peak_sp)} rpm 超過所填額定 "
                f"{round(a.motor.rated_speed_rpm)} rpm — CURRENT_MODEL_SPEED_SCREEN=INFEASIBLE"
            )
        if peak_tj > a.gear.rated_torque_out:
            warnings.append(
                f"⛔ {gname}：目前估算關節扭矩為所填減速機額定輸出的 "
                f"{round(100*peak_tj/a.gear.rated_torque_out)}% — CURRENT_MODEL_GEARBOX_SCREEN=INFEASIBLE"
            )

    if engine.ik_clamped:
        warnings.append(
            "⚠️ 目前解析 IK/幾何可及性 screen 未通過，軌跡已截斷；"
            "可縮短步長、降低下蹲量或調整連桿尺寸"
        )

    if engine.blocking_obstacle is not None:
        ob = engine.blocking_obstacle
        warnings.append(
            f"⛔ 障礙物（x={ob.x} m，高 {ob.height} m／深 {ob.depth} m）未通過目前 heuristic planner screen"
            f"（screening bounds：高 ≤ {engine.h_max:.2f} m、深 ≤ {max(engine.depth_max, 0):.2f} m）"
            "；規劃器已在障礙物前停止前進。此結果不是實體跨越能力上限"
        )

    # 穩定性統計（穩態窗）。支撐面拓撲切換（單腳↔雙腳）前 4 samples
    # 至後 10 samples 排除：多邊形瞬間縮放 + 量測鏈延遲使該窗口的裕度
    # 屬量測病態點（120 Hz 約 -33 ms 至 +83 ms），
    # 顯示保留原始曲線、統計不計入
    active = (w_l > 0.05).astype(int) * 2 + (w_r > 0.05).astype(int)
    topo_change = np.zeros(n_frames, dtype=bool)
    ch = np.where(np.diff(active) != 0)[0]
    for i in ch:
        # 切換後的窗口較長：量測鏈（FD + 平滑）延遲約 50-80ms
        topo_change[max(0, i - 4):i + 11] = True
    stat_mask = st & ~topo_change
    zm_w = zmp_margin[stat_mask]
    zm_valid = zm_w[np.isfinite(zm_w)]
    cm_w = com_margin[stat_mask]
    cm_valid = cm_w[np.isfinite(cm_w)]
    # candidate = 已進入 actuator 統計窗且排除支撐拓撲切換病態區的 samples；
    # valid = candidate 中具有 finite ZMP margin 的 samples。
    zmp_candidate_sample_count = int(np.count_nonzero(stat_mask))
    zmp_valid_sample_count = int(zm_valid.size)
    zmp_valid_coverage_pct = (
        100.0 * zmp_valid_sample_count / zmp_candidate_sample_count
        if zmp_candidate_sample_count > 0 else None
    )
    # 門檻 -2.5cm：本管線裕度量測鏈（FD+平滑+離散多邊形）的容差約 ±2cm，
    # 淺層擦邊不計入目前 model indicator 的不穩定比例；此 tolerance 尚未
    # 經實體或 higher-fidelity contact model 校準。
    zmp_unstable_pct = (
        float(100 * np.mean(zm_valid < -0.025)) if zmp_valid_sample_count > 0 else None
    )
    # min_* 是 true sampled minimum；P1 另列為 filtered descriptive diagnostic。
    min_zmp = float(zm_valid.min()) if zmp_valid_sample_count > 0 else None
    p01_zmp = float(np.percentile(zm_valid, 1)) if zmp_valid_sample_count > 0 else None
    min_com = float(cm_valid.min()) if cm_valid.size else np.nan
    if zmp_unstable_pct is None:
        warnings.append(
            "⚠️ ZMP_STABILITY=UNAVAILABLE：目前統計窗經支撐拓撲切換排除與 finite-value "
            "screen 後沒有有效 ZMP margin samples；zmp_stable_pct 已回傳 null，"
            "不得解讀為 100% stable"
        )
    elif gait.mode == "walk":
        if zmp_unstable_pct > 15:
            warnings.append(
                f"⚠️ 目前 cart-table ZMP screen 未通過：{zmp_unstable_pct:.0f}% 的時間明顯超出排程支撐多邊形"
                f"（P1 裕度 {p01_zmp*100:.1f} cm；sampled minimum {min_zmp*100:.1f} cm）"
                "— CURRENT_MODEL_ZMP_SCREEN=NOT_PASSED；"
                f"這不是實體跌倒判定。"
                f"可嘗試：降低速度、縮短步長、加寬/加長腳掌、調整骨盆側擺"
            )
        elif zmp_unstable_pct > 3:
            warnings.append(
                f"🔶 目前 cart-table ZMP screen 裕度偏低：{zmp_unstable_pct:.0f}% 的時間超出排程支撐面"
                f"（P1 裕度 {p01_zmp*100:.1f} cm；sampled minimum {min_zmp*100:.1f} cm）；"
                "尚不能據此判定實體抗擾動能力"
            )
    if gait.mode != "walk":
        warnings.append(
            "ℹ️ 跑步含騰空期，cart-table ZMP indicator 僅供 current-model screening；"
            "可再以 MuJoCo forward contact simulation 測試，但仍不等同實體穩定性驗證"
        )

    # 每個致動器群組左右各一顆
    act_mass = sum((a.motor.mass + a.gear.mass) * 2 for a in cfg.actuators.values())

    summary = {
        "total_mass": round(M_total, 2),
        "actuator_mass": round(act_mass, 2),
        "cycle_time": round(engine.T, 3),
        "cadence_spm": round(120 / engine.T, 1),          # 每分鐘步數（雙步/週期）
        "elapsed_time_s": round(motion["elapsed_time_s"], 4),
        "distance": round(motion["distance_m"], 4),
        "net_displacement": round(motion["net_displacement_m"], 4),
        "avg_speed": round(motion["avg_speed_mps"], 4),
        "energy_J": round(E_total, 1),
        "avg_power_W": round(motion["avg_power_W"], 1),
        "cot": round(cot, 3) if cot is not None else None,
        "actuator_stats_window": {
            "mode": stats_window_mode,
            "start_s": round(float(times[st][0]), 4),
            "end_s": round(float(times[st][-1]), 4),
            "n_samples": int(np.count_nonzero(st)),
        },
        "zmp_stable_pct": (
            round(100 - zmp_unstable_pct, 1) if zmp_unstable_pct is not None else None
        ),
        "zmp_valid_sample_count": zmp_valid_sample_count,
        "zmp_candidate_sample_count": zmp_candidate_sample_count,
        "zmp_valid_coverage_pct": (
            round(zmp_valid_coverage_pct, 1) if zmp_valid_coverage_pct is not None else None
        ),
        "min_zmp_margin_cm": round(min_zmp * 100, 1) if min_zmp is not None else None,
        "p01_zmp_margin_cm": round(p01_zmp * 100, 1) if p01_zmp is not None else None,
        "min_com_margin_cm": round(min_com * 100, 1) if np.isfinite(min_com) else None,
        "stopped_by_obstacle": engine.blocking_obstacle is not None,
        "groups": group_stats,
    }

    # ---------- 組裝輸出（60 fps） ----------
    o = out_idx
    result = {
        "meta": {
            "dt": DT * DECIM,
            "n_frames": n_out,
            "cycle_time": engine.T,
            "joint_names": JOINT_ORDER,
            "body_names": [mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, b) for b in range(1, model.nbody)],
            "warnings": warnings,
            "summary": summary,
        },
        "geoms": geom_render_list(model),
        "frames": {
            "time": _r(times[o], 3),
            "xpos": _r(xpos[o]),
            "xquat": _r(xquat[o]),
        },
        "telemetry": {
            "q": _r(qpos[o][:, 7:]),
            "qd": _r(qd_j[o], 3),
            "tau": _r(tau[o], 3),
            "tau_motor": _r(tau_motor[o], 4),
            "util": _r(util[o], 4),
            "speed_rpm": _r(speed_rpm[o], 1),
            "power": _r(power_elec[o], 2),
        },
        "gait": {
            "contact_l": _r(w_l[o], 3),
            "contact_r": _r(w_r[o], 3),
            "grf_l": _r(grf_l[o], 1),
            "grf_r": _r(grf_r[o], 1),
            "com": _r(com[o]),
            "zmp": np.where(np.isnan(zmp[o]), None, np.round(zmp[o], 4)).tolist(),
        },
        "sensor": {
            "origin": _r(lidar_pos[o]),
            "hits": _r(ray_hits),
            "dists": _r(ray_dists, 3),
            "detected": detected.tolist(),
        },
        "stability": {
            "zmp_margin": np.where(np.isnan(zmp_margin[o]), None,
                                   np.round(zmp_margin[o], 4)).tolist(),
            "com_margin": np.where(np.isnan(com_margin[o]), None,
                                   np.round(com_margin[o], 4)).tolist(),
            "polygons": [hulls[i] for i in out_idx],
        },
    }

    stable_payload = {
        "schema_version": PROVENANCE_SCHEMA_VERSION,
        "metric_set_version": METRIC_SET_VERSION,
        "deterministic": True,
        "simulation_class": SIMULATION_CLASS,
        "config_hash": config_hash,
        "model_hash": model_hash,
        "code_hash": code_hash,
        "engine": "MuJoCo",
        "engine_version": getattr(mujoco, "__version__", None),
        "result": result,
    }
    result_hash = _canonical_hash(stable_payload)
    result["meta"]["provenance"] = {
        "schema_version": PROVENANCE_SCHEMA_VERSION,
        "metric_set_version": METRIC_SET_VERSION,
        "deterministic": True,
        "run_id": str(uuid.uuid4()),
        "scenario_id": f"scenario-{config_hash.split(':', 1)[-1][:16]}",
        "config_hash": config_hash,
        "result_hash": result_hash,
        "deterministic_content_hash": result_hash,
        "content_hash_algorithm": "SHA-256",
        "content_hash_scope": (
            "canonical stable payload containing schema_version, metric_set_version, "
            "deterministic, simulation_class, config_hash, model_hash, code_hash, engine, "
            "engine_version, and response result before meta.provenance injection"
        ),
        "content_hash_canonicalization": (
            "UTF-8 JSON; sort_keys=true; separators=(',', ':'); "
            "ensure_ascii=false; allow_nan=false"
        ),
        "content_hash_excluded_fields": ["meta.provenance", "run_id", "created_at"],
        "random_seed": None,
        "engine": "MuJoCo",
        "engine_version": getattr(mujoco, "__version__", None),
        "model_version": model_hash,
        "model_hash": model_hash,
        "controller": "PRESCRIBED_KINEMATICS_ANALYTIC_GRF_INVERSE_DYNAMICS",
        "controller_version": None,
        "code_version": code_hash,
        "code_hash": code_hash,
        "integrator": _enum_name(mujoco.mjtIntegrator, model.opt.integrator),
        "integrator_applicable": False,
        "solver": _enum_name(mujoco.mjtSolver, model.opt.solver),
        "solver_applicable": False,
        "configured_model_timestep_s": float(model.opt.timestep),
        "simulation_class": SIMULATION_CLASS,
        "assist_enabled": False,
        "internal_dt_s": DT,
        "output_dt_s": DT * DECIM,
        "analysis_rate_hz": 1.0 / DT,
        "output_rate_hz": 1.0 / (DT * DECIM),
        "controller_rate_hz": None,
        "controller_rate_applicable": False,
        "evidence_scope": "SOFTWARE_ONLY_KINEMATIC_INVERSE_DYNAMICS_ESTIMATE",
        "calibration_status": "UNCALIBRATED_REPRESENTATIVE_PARAMETERS",
        "git_sha": None,
        "policy_version": None,
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    return result

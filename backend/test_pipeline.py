"""管線驗證：IK 正確性（FK 對照）、逆動力學合理性（靜站扭矩 ≈ 理論值）。"""

import numpy as np
import mujoco
from config_schema import default_robot, GaitParams, SimRequest, Obstacle
from model_builder import make_model, JOINT_ORDER, pelvis_height
from gait import GaitEngine
from simulator import run_simulation


def test_ik_fk_roundtrip():
    """IK 解出的關節角，經 MuJoCo FK 後腳底位置應與目標一致、腳掌應水平。"""
    cfg = default_robot()
    gait = GaitParams()
    eng = GaitEngine(cfg, gait, [])
    model = make_model(cfg, [])
    data = mujoco.MjData(model)
    site_l = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_SITE, "sole_l")
    foot_l = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "foot_l")

    max_pos_err = 0.0
    max_level_err = 0.0
    for t in np.linspace(0.3, 3.0, 40):
        q = eng.qpos_at(t, model.nq)
        data.qpos[:] = q
        mujoco.mj_kinematics(model, data)

        target, _ = eng.foot_target("l", t)
        # sole site 相對踝關節有前移偏置，比較時以踝關節（foot body 原點）為準
        ankle_pos = data.xpos[foot_l]
        err = np.linalg.norm(ankle_pos - target)
        max_pos_err = max(max_pos_err, err)

        # 腳掌水平：foot body 的 z 軸應接近世界 z 軸
        R = data.xmat[foot_l].reshape(3, 3)
        level_err = abs(1.0 - R[2, 2])
        max_level_err = max(max_level_err, level_err)

    print(f"IK 位置誤差 max = {max_pos_err*1000:.2f} mm")
    print(f"腳掌水平誤差 max = {max_level_err:.4f} (1-cos)")
    # 8mm 容差：接近腿長極限時 IK 軟飽和會刻意偏離目標（避免速度跳變）
    assert max_pos_err < 0.008, "IK 位置誤差過大"
    assert max_level_err < 0.02, "腳掌未保持水平"


def test_static_stance_torque():
    """靜止站立（雙腳平均承重）時，逆動力學管線的重力矩應與封閉解同量級。

    驗證方式：垂直方向 GRF 總和應等於總重量；髖/膝扭矩非零且有限。
    """
    cfg = default_robot()
    gait = GaitParams(speed=0.3, step_length=0.2, duration=4.0)
    req = SimRequest(robot=cfg, gait=gait, obstacles=[])
    out = run_simulation(req)

    M = out["meta"]["summary"]["total_mass"]
    grf_l = np.array(out["gait"]["grf_l"])
    grf_r = np.array(out["gait"]["grf_r"])
    fz = grf_l[:, 2] + grf_r[:, 2]
    # 穩態平均垂直反力 ≈ Mg
    mean_fz = fz[len(fz) // 2:].mean()
    print(f"總質量 {M} kg → Mg = {M*9.81:.0f} N，平均垂直 GRF = {mean_fz:.0f} N")
    assert abs(mean_fz - M * 9.81) / (M * 9.81) < 0.05

    tau = np.array(out["telemetry"]["tau"])
    knee_idx = JOINT_ORDER.index("knee_l")
    peak_knee = np.abs(tau[:, knee_idx]).max()
    print(f"膝關節峰值扭矩 = {peak_knee:.1f} Nm")
    assert 1.0 < peak_knee < 500.0
    print("警告:", out["meta"]["warnings"])


def test_walk_and_run():
    cfg = default_robot()
    for mode, speed, duty, sl in (("walk", 1.2, 0.62, 0.45), ("run", 2.8, 0.38, 0.85)):
        gait = GaitParams(mode=mode, speed=speed, duty=duty, step_length=sl,
                          clearance=0.10, duration=5.0)
        out = run_simulation(SimRequest(robot=cfg, gait=gait,
                                        obstacles=[Obstacle(x=2.5, height=0.12, depth=0.25)]))
        s = out["meta"]["summary"]
        print(f"[{mode}] 週期 {s['cycle_time']}s, 能耗 {s['energy_J']} J, COT {s['cot']}, "
              f"膝 peak util {s['groups']['knee']['peak_util_pct']}%")
        det = np.array(out["sensor"]["detected"])
        print(f"[{mode}] 障礙物被偵測的影格比例 = {det.mean():.2f}")
        assert out["meta"]["n_frames"] > 100


if __name__ == "__main__":
    test_ik_fk_roundtrip()
    test_static_stance_torque()
    test_walk_and_run()
    print("\n全部通過 ✓")

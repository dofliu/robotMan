"""V1 actuated energy suite (V1-ACTUATED-ENERGY-SUITE-V1): frozen contract, MuJoCo primary run,
NumPy recomputation of the actuated energy balance.

  A1. actuated_openloop_{4,2,1}ms  trunk fixed, no floor, 12 motors driven by prescribed sinusoidal
                                   torques: E - E0 = W_act - W_damp.
  A2. planted_squat_{4,2,1}ms      full humanoid on the plant floor, the plant's standing PD law
                                   tracking a slow squat: E - E0 = W_act - W_damp + W_contact.

Specification: docs/V1_ACTUATED_ENERGY_SUITE_SPEC.md.  Thresholds live in ACTUATED_SUITE_CONTRACT and
were frozen before the first execution; they must not be relaxed after seeing results.

    python backend/v1_actuated_energy_suite.py --raw-output backend/run_traces/v1-actuated-energy-<ts>.json
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys

import mujoco
import numpy as np

from config_schema import GaitParams, default_robot
from controller import BalanceController
from gait import GaitEngine
from model_builder import JOINT_ORDER, build_mjcf, pelvis_height
from v1_dynamic_reference_suite import compiled_model_receipt as _dynamic_receipt, replay_energies

PRIMARY_SCHEMA_VERSION = "V1_ACTUATED_ENERGY_SUITE_V1"
CLAIM_BOUNDARY = (
    "SIM_ONLY_MUJOCO / NOT_PHYSICALLY_VALIDATED. Energy balance of the project humanoid under "
    "actuation (open-loop sinusoidal torques with the trunk fixed; the plant's standing PD law "
    "tracking a slow squat on the plant floor), recomputed from serialized torques, velocities, "
    "damping, contact forces and contact-point velocities. The plant has no drive-loss model, so "
    "the balance has no drive-loss term. No walking, no physical validation; V1 stays PARTIAL."
)

GRAVITY = 9.81
FREQUENCIES_HZ = (0.55, 0.75, 0.95, 1.15, 0.65, 0.85, 1.05, 1.25, 0.60, 0.80, 1.00, 1.20)

CASE_SPECS = (
    {"case_id": "actuated_openloop_4ms", "family": "openloop", "physics_dt_s": 0.004, "energy_residual_relative_max": 0.02},
    {"case_id": "actuated_openloop_2ms", "family": "openloop", "physics_dt_s": 0.002, "energy_residual_relative_max": 0.01},
    {"case_id": "actuated_openloop_1ms", "family": "openloop", "physics_dt_s": 0.001, "energy_residual_relative_max": 0.005},
    {"case_id": "planted_squat_4ms", "family": "squat", "physics_dt_s": 0.004, "energy_residual_relative_max": 0.05},
    {"case_id": "planted_squat_2ms", "family": "squat", "physics_dt_s": 0.002, "energy_residual_relative_max": 0.025},
    {"case_id": "planted_squat_1ms", "family": "squat", "physics_dt_s": 0.001, "energy_residual_relative_max": 0.0125},
)

ACTUATED_SUITE_CONTRACT = {
    "contract_id": "v1_actuated_energy_suite_v1",
    "schema_version": PRIMARY_SCHEMA_VERSION,
    "claim_boundary": CLAIM_BOUNDARY,
    "gravity_mps2": GRAVITY,
    "integrator": "IMPLICITFAST",
    "joint_order": list(JOINT_ORDER),
    "openloop": {"trunk_z_m": 1.6, "duration_s": 3.0, "amplitude_fraction": 0.015,
                 "frequencies_hz": list(FREQUENCIES_HZ), "phase_step_rad": 0.4},
    "squat": {"duration_s": 5.0, "settle_s": 1.0, "depth_m": 0.05, "frequency_hz": 0.25, "crouch_m": 0.10,
              "shoulder_rad": 0.05, "elbow_rad": 0.35, "bias_feedforward": 0.8, "mu": 1.0,
              "planted_from_s": 0.5, "contact_count": 8, "fall_z_fraction_min": 0.75, "fall_angle_max_rad": 0.2},
    "tolerances": {
        "time_grid_error_max_s": 1.0e-12,
        "actuator_clip_abs_max": 1.0e-12,
        "gear_projection_abs_max": 1.0e-12,
        "engine_energy_agreement_relative_max": 1.0e-8,
        "actuator_work_scale_min_j": 1.0,
        "prescribed_ctrl_relative_max": 1.0e-12,
        "pd_law_abs_max": 1.0e-9,
        "qd_ref_abs_max": 1.0e-9,
        "unilateral_normal_force_min_n": -1.0e-12,
        "friction_cone_utilisation_max": 1.0 + 1.0e-9,
        "frame_axis_alignment_max": 1.0e-12,
        "contact_force_closure_max_n": 1.0e-9,
        "energy_scale_min_j": 1.0,
        "primary_replay_relative_max": 1.0e-10,
        "primary_replay_absolute_max": 1.0e-12,
    },
    "case_matrix": [deepcopy(s) for s in CASE_SPECS],
}

COMMON_CRITERION_IDS = (
    "FINITE_RAW_VALUES", "TRACE_STEP_COUNT", "TRACE_TIME_GRID", "COMPILED_TIMESTEP_IDENTITY",
    "COMPILED_MODEL_CONTRACT", "EXTERNAL_FORCE_ABSENT", "ACTUATOR_FORCE_IS_CLIPPED_CTRL",
    "QFRC_ACTUATOR_MATCHES_GEAR_FORCE", "ENGINE_KINETIC_ENERGY_AGREEMENT", "ENGINE_POTENTIAL_ENERGY_AGREEMENT",
    "ACTUATOR_WORK_SCALE_MIN", "ENERGY_BALANCE_RESIDUAL_RELATIVE_MAX",
)
OPENLOOP_CRITERION_IDS = COMMON_CRITERION_IDS + ("CTRL_MATCHES_PRESCRIBED", "NO_CONTACT")
SQUAT_CRITERION_IDS = COMMON_CRITERION_IDS + (
    "CTRL_MATCHES_PD_LAW", "QD_REF_IS_BACKWARD_DIFFERENCE", "NO_FALL", "CONTACT_COUNT_PLANTED",
    "UNILATERAL_NORMAL_FORCE", "FRICTION_CONE_RESPECTED", "CONTACT_FRAME_AXIS_ALIGNED",
    "CONTACT_FORCE_WORLD_SUM_MATCHES_QFRC_CONSTRAINT",
)
SUITE_CRITERION_IDS = ("OPENLOOP_RESIDUAL_TIMESTEP_MONOTONE", "SQUAT_RESIDUAL_TIMESTEP_MONOTONE")

SAMPLE_KEYS = ("time_s", "qpos", "qvel", "qacc", "ctrl", "actuator_force", "qfrc_actuator", "qfrc_bias",
               "qfrc_constraint", "energy_engine", "ncon", "contacts", "bodies",
               "qfrc_applied_abs_max", "xfrc_applied_abs_max")
CONTACT_KEYS = ("geom1", "geom2", "body1", "body2", "dim", "dist", "pos", "frame", "force_contact_frame")
BODY_KEYS = ("xpos", "xipos", "ximat", "angvel_world", "linvel_com_world")


# ---------------------------------------------------------------- 小工具

def _sha256_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _criterion(criterion_id: str, value, operator: str, limit, unit: str) -> dict:
    ops = {"<=": lambda a, b: a <= b, ">=": lambda a, b: a >= b, "==": lambda a, b: a == b, "<": lambda a, b: a < b}
    finite = value is not None and (not isinstance(value, float) or math.isfinite(value))
    passed = bool(finite and ops[operator](value, limit))
    return {"id": criterion_id, "value": value, "operator": operator, "limit": limit, "unit": unit, "passed": passed}


def _finite_tree(value) -> bool:
    if isinstance(value, bool) or value is None or isinstance(value, str) or isinstance(value, int):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, dict):
        return all(_finite_tree(v) for v in value.values())
    if isinstance(value, (list, tuple)):
        return all(_finite_tree(v) for v in value)
    return False


def quaternion_pitch_roll(quat) -> tuple[float, float]:
    w, x, y, z = [float(v) for v in quat]
    pitch = math.asin(max(-1.0, min(1.0, 2.0 * (w * y - z * x))))
    roll = math.atan2(2.0 * (w * x + y * z), 1.0 - 2.0 * (x * x + y * y))
    return pitch, roll


# ---------------------------------------------------------------- 參考訊號（與 replay 逐字對應）

def prescribed_ctrl(t: float, force_upper: list[float], contract: dict = ACTUATED_SUITE_CONTRACT) -> list[float]:
    o = contract["openloop"]
    return [o["amplitude_fraction"] * float(force_upper[j]) * math.sin(2.0 * math.pi * o["frequencies_hz"][j] * t + o["phase_step_rad"] * j)
            for j in range(len(force_upper))]


def squat_depth(t: float, contract: dict = ACTUATED_SUITE_CONTRACT) -> float:
    s = contract["squat"]
    if t < s["settle_s"]:
        return 0.0
    return s["depth_m"] * 0.5 * (1.0 - math.cos(2.0 * math.pi * s["frequency_hz"] * (t - s["settle_s"])))


class SquatReference:
    """Deterministic leg reference from the project's analytic IK; arms and hip roll fixed."""

    def __init__(self, cfg, controller: BalanceController, contract: dict = ACTUATED_SUITE_CONTRACT):
        s = contract["squat"]
        self.engine = GaitEngine(cfg, GaitParams(crouch=s["crouch_m"]), [])
        self.hw = float(self.engine.hw)
        self.ankle_h = float(self.engine.ankle_h)
        self.z_nom = float(controller.z_nom)
        self.stand_q = np.asarray(controller.stand_q, dtype=float).copy()
        self.contract = contract

    def q_ref(self, t: float) -> np.ndarray:
        s = self.contract["squat"]
        dz = squat_depth(t, self.contract)
        _roll, hp, kn, ap = self.engine.leg_ik(np.array([0.0, self.hw, self.z_nom - dz]), np.array([0.0, self.hw, self.ankle_h]), 0.0)
        q = self.stand_q.copy()
        for side in ("l", "r"):
            q[JOINT_ORDER.index(f"hip_roll_{side}")] = 0.0
            q[JOINT_ORDER.index(f"hip_pitch_{side}")] = hp
            q[JOINT_ORDER.index(f"knee_{side}")] = kn
            q[JOINT_ORDER.index(f"ankle_{side}")] = ap
            q[JOINT_ORDER.index(f"shoulder_{side}")] = s["shoulder_rad"]
            q[JOINT_ORDER.index(f"elbow_{side}")] = s["elbow_rad"]
        return q


# ---------------------------------------------------------------- MJCF

def _option_xml(dt: float, contract: dict) -> str:
    return (f'<option gravity="0 0 {-contract["gravity_mps2"]}" timestep="{dt}" integrator="implicitfast">'
            f'<flag energy="enable"/></option>')


def _apply_transforms(xml: str, transforms) -> str:
    for pattern, replacement, flags in transforms:
        hits = re.findall(pattern, xml, flags)
        if len(hits) != 1:
            raise RuntimeError(f"transform expects exactly one match for {pattern!r}, found {len(hits)}")
        xml = re.sub(pattern, replacement, xml, count=1, flags=flags)
    return xml


def build_openloop_mjcf(dt: float, contract: dict = ACTUATED_SUITE_CONTRACT) -> tuple[str, str]:
    original = build_mjcf(default_robot(), [], dynamic=True)
    variant = _apply_transforms(original, (
        (r'<freejoint name="root"/>', "", 0),
        (r'<geom name="floor"[^>]*/>', "", 0),
        (r'<body name="trunk" pos="[^"]*">', f'<body name="trunk" pos="0 0 {contract["openloop"]["trunk_z_m"]}">', 0),
        (r"<option[^>]*/>", _option_xml(dt, contract), 0),
    ))
    if "<actuator>" not in variant:
        raise RuntimeError("open-loop variant lost its actuators")
    return variant, original


def build_squat_mjcf(dt: float, contract: dict = ACTUATED_SUITE_CONTRACT) -> tuple[str, str]:
    original = build_mjcf(default_robot(), [], dynamic=True)
    variant = _apply_transforms(original, ((r"<option[^>]*/>", _option_xml(dt, contract), 0),))
    return variant, original


def compiled_model_receipt(model: mujoco.MjModel, xml: str, xml_original: str) -> dict:
    receipt = _dynamic_receipt(model, xml, xml_original)
    actuators = []
    for a in range(model.nu):
        actuators.append({
            "name": mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_ACTUATOR, a),
            "joint": mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_JOINT, int(model.actuator_trnid[a, 0])),
            "trntype": mujoco.mjtTrn(int(model.actuator_trntype[a])).name,
            "dyntype": mujoco.mjtDyn(int(model.actuator_dyntype[a])).name,
            "gaintype": mujoco.mjtGain(int(model.actuator_gaintype[a])).name,
            "biastype": mujoco.mjtBias(int(model.actuator_biastype[a])).name,
            "gear": [float(x) for x in model.actuator_gear[a]],
            "ctrlrange": [float(x) for x in model.actuator_ctrlrange[a]],
            "forcerange": [float(x) for x in model.actuator_forcerange[a]],
            "dof_adr": int(model.jnt_dofadr[int(model.actuator_trnid[a, 0])]),
        })
    receipt["actuators"] = actuators
    receipt["dof_damping"] = [float(x) for x in model.dof_damping]
    receipt["dof_armature"] = [float(x) for x in model.dof_armature]
    receipt["has_floor"] = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, "floor") >= 0
    receipt["has_freejoint"] = any(int(model.jnt_type[j]) == int(mujoco.mjtJoint.mjJNT_FREE) for j in range(model.njnt))
    receipt["body_names"] = [mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, b) for b in range(model.nbody)]
    return receipt


# ---------------------------------------------------------------- primary run

def _record_sample(model: mujoco.MjModel, data: mujoco.MjData) -> dict:
    mujoco.mj_forward(model, data)
    mujoco.mj_energyPos(model, data)
    mujoco.mj_energyVel(model, data)
    vel = np.zeros(6)
    force = np.zeros(6)
    bodies = []
    for b in range(1, model.nbody):
        mujoco.mj_objectVelocity(model, data, mujoco.mjtObj.mjOBJ_BODY, b, vel, 0)
        bodies.append({
            "xpos": [float(x) for x in data.xpos[b]],
            "xipos": [float(x) for x in data.xipos[b]],
            "ximat": [float(x) for x in data.ximat[b]],
            "angvel_world": [float(x) for x in vel[:3]],
            "linvel_com_world": [float(x) for x in vel[3:]],
        })
    contacts = []
    for i in range(data.ncon):
        c = data.contact[i]
        mujoco.mj_contactForce(model, data, i, force)
        contacts.append({
            "geom1": int(c.geom1), "geom2": int(c.geom2),
            "body1": int(model.geom_bodyid[c.geom1]), "body2": int(model.geom_bodyid[c.geom2]),
            "dim": int(c.dim), "dist": float(c.dist),
            "pos": [float(x) for x in c.pos], "frame": [float(x) for x in c.frame],
            "force_contact_frame": [float(x) for x in force],
        })
    return {
        "time_s": float(data.time),
        "qpos": [float(x) for x in data.qpos],
        "qvel": [float(x) for x in data.qvel],
        "qacc": [float(x) for x in data.qacc],
        "ctrl": [float(x) for x in data.ctrl],
        "actuator_force": [float(x) for x in data.actuator_force],
        "qfrc_actuator": [float(x) for x in data.qfrc_actuator],
        "qfrc_bias": [float(x) for x in data.qfrc_bias],
        "qfrc_constraint": [float(x) for x in data.qfrc_constraint],
        "energy_engine": [float(data.energy[0]), float(data.energy[1])],
        "ncon": int(data.ncon),
        "contacts": contacts,
        "bodies": bodies,
        "qfrc_applied_abs_max": float(np.max(np.abs(data.qfrc_applied))),
        "xfrc_applied_abs_max": float(np.max(np.abs(data.xfrc_applied))),
    }


def run_case(spec: dict, contract: dict = ACTUATED_SUITE_CONTRACT) -> dict:
    dt = float(spec["physics_dt_s"])
    cfg = default_robot()
    if spec["family"] == "openloop":
        xml, original = build_openloop_mjcf(dt, contract)
        duration = contract["openloop"]["duration_s"]
    else:
        xml, original = build_squat_mjcf(dt, contract)
        duration = contract["squat"]["duration_s"]
    model = mujoco.MjModel.from_xml_string(xml)
    data = mujoco.MjData(model)
    force_upper = [float(x) for x in model.actuator_forcerange[:, 1]]
    controller_receipt = None
    reference = None
    if spec["family"] == "openloop":
        data.qpos[:] = 0.0
        data.qvel[:] = 0.0
    else:
        controller = BalanceController(model, cfg, None, 0.0)
        reference = SquatReference(cfg, controller, contract)
        data.qpos[:] = 0.0
        data.qpos[2] = pelvis_height(cfg, contract["squat"]["crouch_m"])
        data.qpos[3] = 1.0
        data.qpos[7:] = reference.stand_q
        data.qvel[:] = 0.0
        controller_receipt = {
            "kp": [float(x) for x in controller.kp], "kd": [float(x) for x in controller.kd],
            "stand_q": [float(x) for x in reference.stand_q], "z_nom_m": reference.z_nom,
            "hw_m": reference.hw, "ankle_h_m": reference.ankle_h,
            "initial_pelvis_z_m": float(data.qpos[2]),
        }
    n_steps = int(round(duration / dt))
    samples = []
    q_ref_prev = None
    for n in range(n_steps + 1):
        mujoco.mj_forward(model, data)                       # 狀態相依量（qfrc_bias）對應此刻
        t = float(data.time)
        if spec["family"] == "openloop":
            data.ctrl[:] = prescribed_ctrl(t, force_upper, contract)
            extra = {}
        else:
            q_ref = reference.q_ref(t)
            qd_ref = np.zeros_like(q_ref) if q_ref_prev is None else (q_ref - q_ref_prev) / dt
            q_ref_prev = q_ref
            q = np.asarray(data.qpos[7:])
            qd = np.asarray(data.qvel[6:])
            bias = np.asarray(data.qfrc_bias[6:])
            data.ctrl[:] = controller.kp * (q_ref - q) + controller.kd * (qd_ref - qd) + contract["squat"]["bias_feedforward"] * bias
            extra = {"q_ref": [float(x) for x in q_ref], "qd_ref": [float(x) for x in qd_ref]}
        sample = _record_sample(model, data)                 # 含 mj_forward：actuator_force／qfrc_actuator／qacc 反映新 ctrl
        sample.update(extra)
        samples.append(sample)
        if n < n_steps:
            mujoco.mj_step(model, data)
    return {
        "case_id": spec["case_id"], "family": spec["family"], "physics_dt_s": dt, "duration_s": duration,
        "expected_sample_count": n_steps + 1, "spec": deepcopy(spec),
        "compiled_model": compiled_model_receipt(model, xml, original),
        "controller": controller_receipt,
        "mjcf": xml,
        "raw_trace": samples,
    }


# ---------------------------------------------------------------- 獨立可重算的量（NumPy）

def _trapezoid_cumulative(values: np.ndarray, dt: float) -> np.ndarray:
    out = np.zeros_like(values)
    if len(values) > 1:
        out[1:] = np.cumsum(0.5 * (values[1:] + values[:-1])) * dt
    return out


def _axis_alignment_error(frame_rows: np.ndarray) -> float:
    err = 0.0
    for row in frame_rows:
        best = min(np.max(np.abs(row - s * np.eye(3)[a])) for a in range(3) for s in (1.0, -1.0))
        err = max(err, float(best))
    return err


def contact_force_on_robot(contact: dict) -> np.ndarray:
    rows = np.asarray(contact["frame"], dtype=float).reshape(3, 3)
    f = rows.T @ np.asarray(contact["force_contact_frame"][:3], dtype=float)
    return f if contact["body1"] == 0 else -f


def contact_robot_body(contact: dict) -> int:
    return contact["body2"] if contact["body1"] == 0 else contact["body1"]


def contact_power(sample: dict) -> float:
    total = 0.0
    for c in sample["contacts"]:
        body = sample["bodies"][contact_robot_body(c) - 1]
        f = contact_force_on_robot(c)
        v = np.asarray(body["linvel_com_world"]) + np.cross(np.asarray(body["angvel_world"]), np.asarray(c["pos"]) - np.asarray(body["xipos"]))
        total += float(f @ v)
    return total


def energy_accounting(case: dict, contract: dict) -> dict:
    trace = case["raw_trace"]
    dt = case["physics_dt_s"]
    cm = case["compiled_model"]
    damping = np.asarray(cm["dof_damping"], dtype=float)
    qvel = np.array([s["qvel"] for s in trace])
    qfrc_act = np.array([s["qfrc_actuator"] for s in trace])
    # 致動力在步內保持常數（ctrl 語義）：力取步首、速度取梯形；阻尼功對 sample 取梯形
    held = np.einsum("ij,ij->i", qfrc_act[:-1], 0.5 * (qvel[:-1] + qvel[1:])) * dt
    w_act = np.concatenate([[0.0], np.cumsum(held)])
    p_damp = np.einsum("ij,ij->i", qvel * damping, qvel)
    w_damp = _trapezoid_cumulative(p_damp, dt)
    if case["family"] == "squat":
        p_con = np.array([contact_power(s) for s in trace])
        w_con = _trapezoid_cumulative(p_con, dt)
    else:
        w_con = np.zeros(len(trace))
    energy = np.array([s["energy_engine"][0] + s["energy_engine"][1] for s in trace])
    residual = energy - energy[0] - w_act + w_damp - w_con
    e_scale = max(float(np.max(np.abs(w_act))), float(np.max(energy) - np.min(energy)), contract["tolerances"]["energy_scale_min_j"])
    n_joint = len(contract["joint_order"])
    qpos = np.array([s["qpos"] for s in trace])
    dq = qpos[1:, -n_joint:] - qpos[:-1, -n_joint:]
    tau_joint = qfrc_act[:-1, -n_joint:]
    w_disc = np.concatenate([[0.0], np.cumsum(np.einsum("ij,ij->i", tau_joint, dq))])
    residual_disc = energy - energy[0] - w_disc + w_damp - w_con
    return {
        "actuator_work_abs_max_j": float(np.max(np.abs(w_act))),
        "actuator_work_final_j": float(w_act[-1]),
        "damping_work_final_j": float(w_damp[-1]),
        "contact_work_final_j": float(w_con[-1]),
        "energy_change_final_j": float(energy[-1] - energy[0]),
        "energy_range_j": float(np.max(energy) - np.min(energy)),
        "energy_scale_j": float(e_scale),
        "energy_residual_abs_max_j": float(np.max(np.abs(residual))),
        "energy_residual_relative_max": float(np.max(np.abs(residual)) / e_scale),
        "discrete_work_residual_relative_max": float(np.max(np.abs(residual_disc)) / e_scale),
    }


def common_metrics(case: dict, contract: dict) -> dict:
    trace = case["raw_trace"]
    dt = case["physics_dt_s"]
    cm = case["compiled_model"]
    g = contract["gravity_mps2"]
    times = np.array([s["time_s"] for s in trace])
    grid_err = float(np.max(np.abs(times - dt * np.arange(len(trace)))))
    ext = max(max(s["qfrc_applied_abs_max"], s["xfrc_applied_abs_max"]) for s in trace)
    lo = np.array([a["forcerange"][0] for a in cm["actuators"]])
    hi = np.array([a["forcerange"][1] for a in cm["actuators"]])
    gear = np.array([a["gear"][0] for a in cm["actuators"]])
    dof = np.array([a["dof_adr"] for a in cm["actuators"]])
    clip_err = gear_err = 0.0
    ke_err = pe_err = 0.0
    implicit = 0.0
    for n, s in enumerate(trace):
        ctrl = np.asarray(s["ctrl"]); af = np.asarray(s["actuator_force"]); qa = np.asarray(s["qfrc_actuator"])
        clip_err = max(clip_err, float(np.max(np.abs(af - np.clip(ctrl, lo, hi)))))
        projected = np.zeros_like(qa)
        np.add.at(projected, dof, gear * af)
        gear_err = max(gear_err, float(np.max(np.abs(qa - projected))))
        ke, pe = replay_energies(s, cm, g)
        ke_err = max(ke_err, abs(ke - s["energy_engine"][1]))
        pe_err = max(pe_err, abs(pe - s["energy_engine"][0]))
        if n + 1 < len(trace):
            v0 = np.asarray(s["qvel"]); v1 = np.asarray(trace[n + 1]["qvel"]); a0 = np.asarray(s["qacc"])
            implicit = max(implicit, float(np.max(np.abs(v1 - v0 - dt * a0))))
    ke_scale = max(max(abs(s["energy_engine"][1]) for s in trace), contract["tolerances"]["energy_scale_min_j"])
    pe_scale = max(max(abs(s["energy_engine"][0]) for s in trace), contract["tolerances"]["energy_scale_min_j"])
    metrics = {
        "time_grid_error_max_s": grid_err,
        "external_force_abs_max": float(ext),
        "actuator_clip_error_max": clip_err,
        "gear_projection_error_max": gear_err,
        "engine_kinetic_energy_agreement_relative_max": float(ke_err / ke_scale),
        "engine_potential_energy_agreement_relative_max": float(pe_err / pe_scale),
        "implicit_velocity_correction_max": implicit,
        "ncon_max": int(max(s["ncon"] for s in trace)),
        "sample_count": len(trace),
    }
    metrics.update(energy_accounting(case, contract))
    return metrics


def _model_contract_ok(case: dict, contract: dict) -> tuple[bool, list[str]]:
    cm = case["compiled_model"]
    problems = []
    if cm["integrator"] != contract["integrator"]:
        problems.append("integrator")
    if not cm["energy_flag_enabled"]:
        problems.append("energy flag")
    if [float(x) for x in cm["gravity_mps2"]] != [0.0, 0.0, -contract["gravity_mps2"]]:
        problems.append("gravity")
    if cm["nu"] != len(contract["joint_order"]) or [a["joint"] for a in cm["actuators"]] != contract["joint_order"]:
        problems.append("actuator inventory")
    for a in cm["actuators"]:
        if a["gear"][0] != 1.0 or a["ctrlrange"] != a["forcerange"] or a["forcerange"][1] <= 0.0 or a["trntype"] != "mjTRN_JOINT":
            problems.append(f"actuator {a['name']}")
    expect_floor = case["family"] == "squat"
    if cm["has_floor"] != expect_floor or cm["has_freejoint"] != expect_floor:
        problems.append("floor/freejoint layout")
    joints_by_name = {j["name"]: j for j in cm["joints"]}
    for name in contract["joint_order"]:
        j = joints_by_name.get(name)
        if j is None or j["type"] != "HINGE":
            problems.append(f"joint {name}")
            continue
        expected_damping = 0.3 if name.startswith(("shoulder", "elbow")) else 1.0
        if j["damping"] != expected_damping:
            problems.append(f"damping {name}")
    if case["family"] == "squat" and case["mjcf"].count('friction="1.0 0.005 0.0001"') < 3:
        problems.append("plant friction triple")
    return (not problems), problems


def _common_criteria(case: dict, contract: dict, metrics: dict) -> list[dict]:
    tol = contract["tolerances"]
    trace = case["raw_trace"]
    ok, problems = _model_contract_ok(case, contract)
    return [
        _criterion("FINITE_RAW_VALUES", 1 if _finite_tree(trace) else 0, "==", 1, "flag"),
        _criterion("TRACE_STEP_COUNT", len(trace), "==", case["expected_sample_count"], "samples"),
        _criterion("TRACE_TIME_GRID", metrics["time_grid_error_max_s"], "<=", tol["time_grid_error_max_s"], "s"),
        _criterion("COMPILED_TIMESTEP_IDENTITY", case["compiled_model"]["timestep_s"], "==", case["physics_dt_s"], "s"),
        _criterion("COMPILED_MODEL_CONTRACT", 1 if ok else 0, "==", 1, "flag; problems=" + ";".join(problems)),
        _criterion("EXTERNAL_FORCE_ABSENT", metrics["external_force_abs_max"], "<=", 0.0, "N or N·m"),
        _criterion("ACTUATOR_FORCE_IS_CLIPPED_CTRL", metrics["actuator_clip_error_max"], "<=", tol["actuator_clip_abs_max"], "N·m"),
        _criterion("QFRC_ACTUATOR_MATCHES_GEAR_FORCE", metrics["gear_projection_error_max"], "<=", tol["gear_projection_abs_max"], "N·m"),
        _criterion("ENGINE_KINETIC_ENERGY_AGREEMENT", metrics["engine_kinetic_energy_agreement_relative_max"], "<=", tol["engine_energy_agreement_relative_max"], "relative"),
        _criterion("ENGINE_POTENTIAL_ENERGY_AGREEMENT", metrics["engine_potential_energy_agreement_relative_max"], "<=", tol["engine_energy_agreement_relative_max"], "relative"),
        _criterion("ACTUATOR_WORK_SCALE_MIN", metrics["actuator_work_abs_max_j"], ">=", tol["actuator_work_scale_min_j"], "J"),
        _criterion("ENERGY_BALANCE_RESIDUAL_RELATIVE_MAX", metrics["energy_residual_relative_max"], "<=", case["spec"]["energy_residual_relative_max"], "relative to energy scale"),
    ]


def evaluate_openloop_case(case: dict, contract: dict = ACTUATED_SUITE_CONTRACT) -> dict:
    tol = contract["tolerances"]
    trace = case["raw_trace"]
    metrics = common_metrics(case, contract)
    hi = [a["forcerange"][1] for a in case["compiled_model"]["actuators"]]
    err = 0.0
    for s in trace:
        expected = prescribed_ctrl(float(s["time_s"]), hi, contract)
        err = max(err, max(abs(float(c) - e) / h for c, e, h in zip(s["ctrl"], expected, hi)))
    metrics["prescribed_ctrl_relative_error_max"] = float(err)
    criteria = _common_criteria(case, contract, metrics) + [
        _criterion("CTRL_MATCHES_PRESCRIBED", float(err), "<=", tol["prescribed_ctrl_relative_max"], "relative to forcerange"),
        _criterion("NO_CONTACT", metrics["ncon_max"], "==", 0, "contacts"),
    ]
    assert [c["id"] for c in criteria] == list(OPENLOOP_CRITERION_IDS)
    return {"case_id": case["case_id"], "family": "openloop", "physics_dt_s": case["physics_dt_s"],
            "status": "PASS" if all(c["passed"] for c in criteria) else "FAIL", "criteria": criteria, "metrics": metrics}


def evaluate_squat_case(case: dict, contract: dict = ACTUATED_SUITE_CONTRACT) -> dict:
    tol = contract["tolerances"]
    sq = contract["squat"]
    trace = case["raw_trace"]
    dt = case["physics_dt_s"]
    metrics = common_metrics(case, contract)
    ctl = case["controller"]
    kp = np.asarray(ctl["kp"]); kd = np.asarray(ctl["kd"])
    n_joint = len(contract["joint_order"])
    pd_err = qd_err = 0.0
    z_min_frac = math.inf
    angle_max = 0.0
    fn_min = math.inf
    util_max = 0.0
    axis_err = 0.0
    closure = 0.0
    planted_ok = True
    mu = float(sq["mu"])
    for n, s in enumerate(trace):
        q = np.asarray(s["qpos"][-n_joint:]); qd = np.asarray(s["qvel"][-n_joint:]); bias = np.asarray(s["qfrc_bias"][-n_joint:])
        q_ref = np.asarray(s["q_ref"]); qd_ref = np.asarray(s["qd_ref"])
        law = kp * (q_ref - q) + kd * (qd_ref - qd) + sq["bias_feedforward"] * bias
        pd_err = max(pd_err, float(np.max(np.abs(np.asarray(s["ctrl"]) - law))))
        expected_qd = np.zeros(n_joint) if n == 0 else (q_ref - np.asarray(trace[n - 1]["q_ref"])) / dt
        qd_err = max(qd_err, float(np.max(np.abs(qd_ref - expected_qd))))
        z_min_frac = min(z_min_frac, float(s["qpos"][2]) / ctl["z_nom_m"])
        pitch, roll = quaternion_pitch_roll(s["qpos"][3:7])
        angle_max = max(angle_max, abs(pitch), abs(roll))
        if s["time_s"] >= sq["planted_from_s"] - 1e-9 * dt and s["ncon"] != sq["contact_count"]:
            planted_ok = False
        world_sum = np.zeros(3)
        for c in s["contacts"]:
            rows = np.asarray(c["frame"]).reshape(3, 3)
            axis_err = max(axis_err, _axis_alignment_error(rows))
            f = c["force_contact_frame"]
            fn_min = min(fn_min, float(f[0]))
            tangential = math.hypot(float(f[1]), float(f[2]))
            if f[0] > 0.0:
                util_max = max(util_max, tangential / (mu * float(f[0])))
            elif tangential > 0.0:
                util_max = math.inf
            world_sum += contact_force_on_robot(c)
        closure = max(closure, float(np.max(np.abs(world_sum - np.asarray(s["qfrc_constraint"][:3])))))
    if not math.isfinite(fn_min):
        fn_min = 0.0
    metrics.update({
        "pd_law_error_max": float(pd_err), "qd_ref_error_max": float(qd_err),
        "pelvis_z_fraction_min": float(z_min_frac), "trunk_angle_abs_max_rad": float(angle_max),
        "planted_contact_count_constant": 1 if planted_ok else 0,
        "normal_force_min_n": float(fn_min), "friction_cone_utilisation_max": float(util_max),
        "frame_axis_alignment_error_max": float(axis_err), "contact_force_closure_error_max_n": float(closure),
    })
    criteria = _common_criteria(case, contract, metrics) + [
        _criterion("CTRL_MATCHES_PD_LAW", float(pd_err), "<=", tol["pd_law_abs_max"], "N·m"),
        _criterion("QD_REF_IS_BACKWARD_DIFFERENCE", float(qd_err), "<=", tol["qd_ref_abs_max"], "rad/s"),
        _criterion("NO_FALL", 1 if (z_min_frac >= sq["fall_z_fraction_min"] and angle_max <= sq["fall_angle_max_rad"]) else 0, "==", 1, "flag"),
        _criterion("CONTACT_COUNT_PLANTED", metrics["planted_contact_count_constant"], "==", 1, "flag"),
        _criterion("UNILATERAL_NORMAL_FORCE", float(fn_min), ">=", tol["unilateral_normal_force_min_n"], "N"),
        _criterion("FRICTION_CONE_RESPECTED", float(util_max), "<=", tol["friction_cone_utilisation_max"], "ratio"),
        _criterion("CONTACT_FRAME_AXIS_ALIGNED", float(axis_err), "<=", tol["frame_axis_alignment_max"], "unit vector"),
        _criterion("CONTACT_FORCE_WORLD_SUM_MATCHES_QFRC_CONSTRAINT", float(closure), "<=", tol["contact_force_closure_max_n"], "N"),
    ]
    assert [c["id"] for c in criteria] == list(SQUAT_CRITERION_IDS)
    return {"case_id": case["case_id"], "family": "squat", "physics_dt_s": dt,
            "status": "PASS" if all(c["passed"] for c in criteria) else "FAIL", "criteria": criteria, "metrics": metrics}


def evaluate_case(case: dict, contract: dict = ACTUATED_SUITE_CONTRACT) -> dict:
    return evaluate_openloop_case(case, contract) if case["family"] == "openloop" else evaluate_squat_case(case, contract)


def _orders(errors: list[float]) -> dict:
    if min(errors) <= 0.0:
        return {"coarse_medium": None, "medium_fine": None, "status": "ESTIMATED"}
    return {"coarse_medium": float(math.log2(errors[0] / errors[1])), "medium_fine": float(math.log2(errors[1] / errors[2])), "status": "ESTIMATED"}


def evaluate_suite(evaluations: list[dict], contract: dict = ACTUATED_SUITE_CONTRACT) -> dict:
    by_id = {e["case_id"]: e for e in evaluations}
    open_e = [by_id[f"actuated_openloop_{k}ms"]["metrics"]["energy_residual_relative_max"] for k in (4, 2, 1)]
    squat_e = [by_id[f"planted_squat_{k}ms"]["metrics"]["energy_residual_relative_max"] for k in (4, 2, 1)]
    criteria = [
        _criterion("OPENLOOP_RESIDUAL_TIMESTEP_MONOTONE", 1 if open_e[0] > open_e[1] > open_e[2] else 0, "==", 1, "flag"),
        _criterion("SQUAT_RESIDUAL_TIMESTEP_MONOTONE", 1 if squat_e[0] > squat_e[1] > squat_e[2] else 0, "==", 1, "flag"),
    ]
    assert [c["id"] for c in criteria] == list(SUITE_CRITERION_IDS)
    gate_ok = all(e["status"] == "PASS" for e in evaluations) and all(c["passed"] for c in criteria)
    return {
        "status": "PASS" if gate_ok else "FAIL",
        "criteria": criteria,
        "timestep_study": {
            "openloop_residual_relative": open_e, "openloop_observed_order": _orders(open_e),
            "squat_residual_relative": squat_e, "squat_observed_order": _orders(squat_e),
            "implicit_velocity_correction_max": [by_id[c]["metrics"]["implicit_velocity_correction_max"] for c in [s["case_id"] for s in contract["case_matrix"]]],
            "discrete_work_residual_relative": [by_id[c]["metrics"]["discrete_work_residual_relative_max"] for c in [s["case_id"] for s in contract["case_matrix"]]],
            "contact_work_final_j": [by_id[f"planted_squat_{k}ms"]["metrics"]["contact_work_final_j"] for k in (4, 2, 1)],
        },
    }


def run_actuated_suite(contract: dict = ACTUATED_SUITE_CONTRACT) -> dict:
    cases = [run_case(spec, contract) for spec in contract["case_matrix"]]
    evaluations = [evaluate_case(c, contract) for c in cases]
    suite = evaluate_suite(evaluations, contract)
    merged = []
    for case, ev in zip(cases, evaluations):
        entry = deepcopy(case)
        entry.update({"status": ev["status"], "criteria": ev["criteria"], "metrics": ev["metrics"]})
        merged.append(entry)
    return {
        "schema_version": PRIMARY_SCHEMA_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "claim_boundary": CLAIM_BOUNDARY,
        "contract": deepcopy(contract),
        "contract_sha256": _sha256_text(json.dumps(contract, sort_keys=True, separators=(",", ":"))),
        "mujoco_version": mujoco.__version__,
        "cases": merged,
        "suite": suite,
        "status": suite["status"],
    }


def summary_without_raw(result: dict) -> dict:
    compact = deepcopy(result)
    for case in compact["cases"]:
        case.pop("raw_trace", None)
        case.pop("mjcf", None)
    return compact


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="V1 actuated energy suite (frozen contract).")
    parser.add_argument("--raw-output", type=Path, default=None, help="write the full primary result here (exclusive create)")
    args = parser.parse_args(argv)
    result = run_actuated_suite()
    if args.raw_output is not None:
        args.raw_output.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(args.raw_output), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(result, fh, allow_nan=False)
        print(f"raw artifact: {args.raw_output}")
    compact = summary_without_raw(result)
    print(json.dumps({"status": compact["status"],
                      "cases": [{"case_id": c["case_id"], "status": c["status"],
                                 "failed": [k["id"] for k in c["criteria"] if not k["passed"]],
                                 "residual_relative": c["metrics"]["energy_residual_relative_max"],
                                 "actuator_work_j": c["metrics"]["actuator_work_final_j"],
                                 "damping_work_j": c["metrics"]["damping_work_final_j"],
                                 "contact_work_j": c["metrics"]["contact_work_final_j"]} for c in compact["cases"]],
                      "suite_failed": [k["id"] for k in compact["suite"]["criteria"] if not k["passed"]],
                      "timestep_study": compact["suite"]["timestep_study"]}, indent=2, allow_nan=False))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())

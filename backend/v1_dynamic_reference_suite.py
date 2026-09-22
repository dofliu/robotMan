"""Frozen V1 dynamic reference suite: known pendulum + articulated passive swing.

Two contact-free, controller-free, actuation-free case families on a 4/2/1 ms
grid (spec: docs/V1_DYNAMIC_REFERENCE_SUITE_SPEC.md, V1-DYNAMIC-REFERENCE-SUITE-V1):

  P. known_pendulum_{4,2,1}ms      one sphere on a hinge; closed-form period and energy
  A. articulated_passive_swing_*   the project humanoid with the trunk fixed to the world,
                                   no floor, no actuators; energy balance incl. damping work

Every threshold lives in DYNAMIC_SUITE_CONTRACT and was frozen before the first run.
Passing this suite does not promote V1 to PASS and is not physical validation.

    python -X utf8 backend/v1_dynamic_reference_suite.py [--raw-output PATH]
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

import mujoco
import numpy as np

from config_schema import default_robot
from model_builder import build_mjcf


PRIMARY_SCHEMA_VERSION = "V1_DYNAMIC_REFERENCE_SUITE_V1"
CLAIM_BOUNDARY = (
    "SIM_ONLY_MUJOCO / NOT_PHYSICALLY_VALIDATED. Contact-free, controller-free, "
    "actuation-free reference cases: a closed-form physical pendulum (period and "
    "energy) and the project's articulated humanoid swinging passively from a fixed "
    "trunk (energy balance including joint-damping work, closed-form inertia of "
    "sphere/box bodies). It does not verify contact physics, actuators, controllers, "
    "any physical capability, or the complete V1 gate."
)

ARTICULATED_INITIAL_POSE_RAD = {
    "hip_roll_l": 0.15, "hip_pitch_l": 0.6, "knee_l": -1.0, "ankle_l": 0.2,
    "hip_roll_r": -0.10, "hip_pitch_r": -0.4, "knee_r": -0.3, "ankle_r": -0.2,
    "shoulder_l": 1.0, "elbow_l": 0.8, "shoulder_r": -0.8, "elbow_r": 0.3,
}

CASE_SPECS = (
    {"case_id": "known_pendulum_4ms", "family": "pendulum", "physics_dt_s": 0.004,
     "roles": ["TIMESTEP_COARSE"], "energy_fluctuation_relative_max": 0.02},
    {"case_id": "known_pendulum_2ms", "family": "pendulum", "physics_dt_s": 0.002,
     "roles": ["TIMESTEP_MEDIUM"], "energy_fluctuation_relative_max": 0.01},
    {"case_id": "known_pendulum_1ms", "family": "pendulum", "physics_dt_s": 0.001,
     "roles": ["TIMESTEP_FINE"], "energy_fluctuation_relative_max": 0.005},
    {"case_id": "articulated_passive_swing_4ms", "family": "articulated", "physics_dt_s": 0.004,
     "roles": ["TIMESTEP_COARSE"], "energy_residual_relative_max": 0.05},
    {"case_id": "articulated_passive_swing_2ms", "family": "articulated", "physics_dt_s": 0.002,
     "roles": ["TIMESTEP_MEDIUM"], "energy_residual_relative_max": 0.025},
    {"case_id": "articulated_passive_swing_1ms", "family": "articulated", "physics_dt_s": 0.001,
     "roles": ["TIMESTEP_FINE"], "energy_residual_relative_max": 0.0125},
)

DYNAMIC_SUITE_CONTRACT = {
    "contract_id": "v1_dynamic_reference_suite_v1",
    "specification": "docs/V1_DYNAMIC_REFERENCE_SUITE_SPEC.md",
    "gravity_mps2": 9.81,
    "integrator": "IMPLICITFAST",
    "controller": None,
    "actuation": "NONE",
    "assist_enabled": False,
    "deterministic": True,
    "pendulum": {
        "mass_kg": 2.0,
        "radius_m": 0.05,
        "length_m": 0.5,
        "pivot_z_m": 1.5,
        "theta0_rad": math.pi / 3.0,
        "duration_s": 6.0,
        "min_period_count": 3,
        "hinge_axis": [0.0, 1.0, 0.0],
    },
    "articulated": {
        "trunk_z_m": 1.6,
        "duration_s": 3.0,
        "initial_pose_rad": dict(ARTICULATED_INITIAL_POSE_RAD),
        "analytic_inertia_bodies": ["trunk", "foot_l", "foot_r"],
        "expected_joint_count": 12,
        "expected_leg_damping": 1.0,
        "expected_arm_damping": 0.3,
    },
    "case_matrix": deepcopy(list(CASE_SPECS)),
    "tolerances": {
        "time_grid_error_max_s": 1.0e-12,
        "engine_energy_agreement_relative_max": 1.0e-8,
        "pendulum_period_relative_error_max": 1.0e-3,
        "pendulum_energy_secular_drift_relative_max": 1.0e-3,
        "pendulum_period_fine_delta_relative_max": 5.0e-4,
        "pendulum_period_roundoff_floor_s": 1.0e-7,
        "articulated_residual_roundoff_floor": 1.0e-6,
        "energy_scale_min_j": 1.0,
        "inertia_relative_error_max": 1.0e-9,
        "com_abs_error_max_m": 1.0e-12,
        "mass_abs_error_max_kg": 1.0e-12,
        "primary_replay_relative_max": 1.0e-10,
        "primary_replay_absolute_max": 1.0e-12,
    },
}

COMMON_CRITERION_IDS = (
    "FINITE_RAW_VALUES",
    "TRACE_STEP_COUNT",
    "TRACE_TIME_GRID",
    "COMPILED_TIMESTEP_IDENTITY",
    "COMPILED_MODEL_CONTRACT",
    "EXTERNAL_FORCE_ABSENT",
    "NO_CONTACT",
    "ENGINE_KINETIC_ENERGY_AGREEMENT",
    "ENGINE_POTENTIAL_ENERGY_AGREEMENT",
)
PENDULUM_CRITERION_IDS = COMMON_CRITERION_IDS + (
    "PENDULUM_PERIOD_COUNT",
    "PENDULUM_PERIOD_RELATIVE_ERROR",
    "PENDULUM_ENERGY_RELATIVE_FLUCTUATION",
    "PENDULUM_ENERGY_SECULAR_DRIFT",
    "PENDULUM_INERTIA_ANALYTIC_AGREEMENT",
)
ARTICULATED_CRITERION_IDS = COMMON_CRITERION_IDS + (
    "ENERGY_SCALE_POSITIVE",
    "ENERGY_BALANCE_RESIDUAL_RELATIVE_MAX",
    "BODY_MASS_ANALYTIC_AGREEMENT",
    "BODY_INERTIA_ANALYTIC_AGREEMENT",
)
SUITE_CRITERION_IDS = (
    "EXACT_CASE_INVENTORY",
    "ALL_CASES_PASS",
    "PENDULUM_PERIOD_TIMESTEP_FINE_DELTA",
    "PENDULUM_PERIOD_TIMESTEP_MONOTONE",
    "ARTICULATED_RESIDUAL_TIMESTEP_MONOTONE",
    "TIMESTEP_NON_DT_CONFIG_IDENTITY",
)


# ---------------------------------------------------------------- 小工具

def _sha256_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _criterion(criterion_id: str, value, operator: str, limit, unit: str) -> dict:
    if operator == "<=":
        passed = float(value) <= float(limit)
    elif operator == ">=":
        passed = float(value) >= float(limit)
    elif operator == "==":
        passed = value == limit
    else:
        raise ValueError(f"unsupported operator {operator}")
    return {"id": criterion_id, "passed": bool(passed), "value": value, "operator": operator,
            "limit": limit, "unit": unit}


def _finite_tree(value) -> bool:
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return True
    if isinstance(value, (int, float)):
        return math.isfinite(float(value))
    if isinstance(value, dict):
        return all(_finite_tree(v) for v in value.values())
    if isinstance(value, (list, tuple)):
        return all(_finite_tree(v) for v in value)
    return True


def complete_elliptic_integral_first_kind(k: float) -> float:
    """K(k) by the arithmetic-geometric mean: K = pi / (2 * AGM(1, sqrt(1 - k^2)))."""
    a, b = 1.0, math.sqrt(1.0 - k * k)
    for _ in range(64):
        if abs(a - b) <= 1e-17 * a:
            break
        a, b = 0.5 * (a + b), math.sqrt(a * b)
    return math.pi / (2.0 * a)


def pendulum_closed_form(contract: dict) -> dict:
    p = contract["pendulum"]
    m, r, length, g = p["mass_kg"], p["radius_m"], p["length_m"], contract["gravity_mps2"]
    inertia_pivot = 0.4 * m * r * r + m * length * length
    k = math.sin(0.5 * p["theta0_rad"])
    period = 4.0 * math.sqrt(inertia_pivot / (m * g * length)) * complete_elliptic_integral_first_kind(k)
    energy0 = m * g * length * (1.0 - math.cos(p["theta0_rad"]))
    return {"inertia_pivot_kgm2": inertia_pivot, "period_s": period, "energy0_j": energy0,
            "small_angle_period_s": 2.0 * math.pi * math.sqrt(inertia_pivot / (m * g * length))}


# ---------------------------------------------------------------- MJCF

def build_pendulum_mjcf(dt: float, contract: dict = DYNAMIC_SUITE_CONTRACT) -> str:
    p = contract["pendulum"]
    g = contract["gravity_mps2"]
    return (
        '<mujoco model="known_pendulum">\n'
        '  <compiler angle="radian"/>\n'
        f'  <option gravity="0 0 {-g}" timestep="{dt}" integrator="implicitfast"><flag energy="enable"/></option>\n'
        '  <worldbody>\n'
        f'    <body name="arm" pos="0 0 {p["pivot_z_m"]}">\n'
        '      <joint name="pivot" type="hinge" axis="0 1 0" damping="0" armature="0"/>\n'
        f'      <geom name="bob" type="sphere" size="{p["radius_m"]}" pos="0 0 {-p["length_m"]}" mass="{p["mass_kg"]}"/>\n'
        '    </body>\n'
        '  </worldbody>\n'
        '</mujoco>\n'
    )


def build_articulated_mjcf(dt: float, contract: dict = DYNAMIC_SUITE_CONTRACT) -> tuple[str, str]:
    """The project humanoid with exactly four declared transforms. Returns (variant, original)."""
    original = build_mjcf(default_robot(), [], dynamic=True)
    a = contract["articulated"]
    g = contract["gravity_mps2"]
    variant = original
    for pattern, replacement, flags in (
        (r'<freejoint name="root"/>', "", 0),
        (r'<geom name="floor"[^>]*/>', "", 0),
        (r"<actuator>.*?</actuator>", "", re.S),
        (r'<body name="trunk" pos="[^"]*">', f'<body name="trunk" pos="0 0 {a["trunk_z_m"]}">', 0),
        (r"<option[^>]*/>",
         f'<option gravity="0 0 {-g}" timestep="{dt}" integrator="implicitfast"><flag energy="enable"/></option>', 0),
    ):
        hits = re.findall(pattern, variant, flags)
        if len(hits) != 1:
            raise RuntimeError(f"articulated transform expects exactly one match for {pattern!r}, found {len(hits)}")
        variant = re.sub(pattern, replacement, variant, count=1, flags=flags)
    return variant, original


def geom_records_from_mjcf(xml: str) -> list[dict]:
    """Geom type/size/pos/fromto/mass as written in the MJCF text, with the owning body name."""
    root = ET.fromstring(xml)
    records: list[dict] = []

    def walk(node, body_name: str):
        for child in node:
            if child.tag == "body":
                walk(child, child.get("name"))
            elif child.tag == "geom":
                records.append({
                    "name": child.get("name"), "body": body_name, "type": child.get("type"),
                    "size": [float(x) for x in child.get("size").split()],
                    "pos": [float(x) for x in child.get("pos").split()] if child.get("pos") else None,
                    "fromto": [float(x) for x in child.get("fromto").split()] if child.get("fromto") else None,
                    "mass": float(child.get("mass")) if child.get("mass") is not None else None,
                })
    walk(root.find("worldbody"), "world")
    return records


def compiled_model_receipt(model: mujoco.MjModel, xml: str, xml_original: str | None = None) -> dict:
    integrator_name = mujoco.mjtIntegrator(model.opt.integrator).name.replace("mjINT_", "")
    joints = []
    for j in range(model.njnt):
        adr = int(model.jnt_dofadr[j])
        joints.append({
            "name": mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_JOINT, j),
            "type": mujoco.mjtJoint(model.jnt_type[j]).name.replace("mjJNT_", ""),
            "qpos_adr": int(model.jnt_qposadr[j]), "dof_adr": adr,
            "damping": float(model.dof_damping[adr]), "armature": float(model.dof_armature[adr]),
        })
    bodies = []
    for b in range(1, model.nbody):
        bodies.append({
            "name": mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, b),
            "mass_kg": float(model.body_mass[b]),
            "inertia_principal_kgm2": [float(x) for x in model.body_inertia[b]],
            "ipos_m": [float(x) for x in model.body_ipos[b]],
            "iquat": [float(x) for x in model.body_iquat[b]],
        })
    return {
        "mjcf_sha256": _sha256_text(xml),
        "mjcf_original_sha256": _sha256_text(xml_original) if xml_original is not None else None,
        "timestep_s": float(model.opt.timestep),
        "integrator": integrator_name,
        "gravity_mps2": [float(x) for x in model.opt.gravity],
        "energy_flag_enabled": bool(model.opt.enableflags & mujoco.mjtEnableBit.mjENBL_ENERGY),
        "nq": int(model.nq), "nv": int(model.nv), "nu": int(model.nu), "nbody": int(model.nbody), "ngeom": int(model.ngeom),
        "joints": joints,
        "bodies": bodies,
        "geoms_from_mjcf": geom_records_from_mjcf(xml),
    }


# ---------------------------------------------------------------- 執行

def _record_sample(model: mujoco.MjModel, data: mujoco.MjData) -> dict:
    mujoco.mj_forward(model, data)
    mujoco.mj_energyPos(model, data)
    mujoco.mj_energyVel(model, data)
    vel = np.zeros(6)
    bodies = []
    for b in range(1, model.nbody):
        # mjOBJ_BODY 的 6D 速度以 body 的慣性框（質心 xipos）為參考點、世界座標：
        # 線速度就是質心速度。第一次執行時誤當成 frame 原點速度再加 ω×r，被
        # ENGINE_KINETIC_ENERGY_AGREEMENT 判準抓到；欄位名改為 linvel_com_world 以免重演。
        mujoco.mj_objectVelocity(model, data, mujoco.mjtObj.mjOBJ_BODY, b, vel, 0)
        bodies.append({
            "xpos": [float(x) for x in data.xpos[b]],
            "xipos": [float(x) for x in data.xipos[b]],
            "ximat": [float(x) for x in data.ximat[b]],
            "angvel_world": [float(x) for x in vel[:3]],
            "linvel_com_world": [float(x) for x in vel[3:]],
        })
    return {
        "time_s": float(data.time),
        "qpos": [float(x) for x in data.qpos],
        "qvel": [float(x) for x in data.qvel],
        "energy_engine": [float(data.energy[0]), float(data.energy[1])],
        "ncon": int(data.ncon),
        "qfrc_applied_abs_max": float(np.max(np.abs(data.qfrc_applied))) if model.nv else 0.0,
        "xfrc_applied_abs_max": float(np.max(np.abs(data.xfrc_applied))),
        "bodies": bodies,
    }


def run_case(spec: dict, contract: dict = DYNAMIC_SUITE_CONTRACT) -> dict:
    dt = float(spec["physics_dt_s"])
    if spec["family"] == "pendulum":
        xml, xml_original = build_pendulum_mjcf(dt, contract), None
        duration = contract["pendulum"]["duration_s"]
    else:
        xml, xml_original = build_articulated_mjcf(dt, contract)
        duration = contract["articulated"]["duration_s"]
    model = mujoco.MjModel.from_xml_string(xml)
    data = mujoco.MjData(model)
    if spec["family"] == "pendulum":
        data.qpos[0] = contract["pendulum"]["theta0_rad"]
    else:
        for name, angle in contract["articulated"]["initial_pose_rad"].items():
            j = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
            if j < 0:
                raise RuntimeError(f"joint {name} missing from articulated variant")
            data.qpos[model.jnt_qposadr[j]] = angle
    data.qvel[:] = 0.0
    n_steps = int(round(duration / dt))
    samples = [_record_sample(model, data)]
    for _ in range(n_steps):
        mujoco.mj_step(model, data)
        samples.append(_record_sample(model, data))
    return {
        "case_id": spec["case_id"], "family": spec["family"], "physics_dt_s": dt,
        "roles": list(spec["roles"]), "duration_s": duration, "expected_sample_count": n_steps + 1,
        "spec": deepcopy(spec),
        "compiled_model": compiled_model_receipt(model, xml, xml_original),
        "mjcf": xml,
        "raw_trace": samples,
    }


# ---------------------------------------------------------------- 獨立可重算的量
# primary 用 NumPy（向量化、不同的加總順序）；v1_dynamic_replay.py 用純 Python 重做同樣的物理，
# 兩者在 1e-10 相對差內一致才算 primary/replay agreement——這使比對不是同一段程式跑兩次。

def body_kinetic_energy(sample_body: dict, body_receipt: dict) -> float:
    m = body_receipt["mass_kg"]
    inertia = np.asarray(body_receipt["inertia_principal_kgm2"])
    w = np.asarray(sample_body["angvel_world"])
    v_com = np.asarray(sample_body["linvel_com_world"])
    rot_mat = np.asarray(sample_body["ximat"]).reshape(3, 3)   # world_from_inertial
    w_local = rot_mat.T @ w
    return float(0.5 * m * v_com @ v_com + 0.5 * inertia @ (w_local * w_local))


def replay_energies(sample: dict, model_receipt: dict, gravity: float) -> tuple[float, float]:
    ke = float(sum(body_kinetic_energy(b, r) for b, r in zip(sample["bodies"], model_receipt["bodies"])))
    masses = np.asarray([r["mass_kg"] for r in model_receipt["bodies"]])
    z = np.asarray([b["xipos"][2] for b in sample["bodies"]])
    pe = float(gravity * masses @ z)
    hinge = [(j["dof_adr"], j["armature"]) for j in model_receipt["joints"] if j["type"] == "HINGE"]
    if hinge:
        qd = np.asarray([sample["qvel"][adr] for adr, _ in hinge])
        arm = np.asarray([a for _, a in hinge])
        ke += float(0.5 * arm @ (qd * qd))
    return ke, pe


def upward_zero_crossings(times: list[float], theta: list[float]) -> list[float]:
    out = []
    for i in range(1, len(theta)):
        if theta[i - 1] < 0.0 <= theta[i]:
            frac = -theta[i - 1] / (theta[i] - theta[i - 1])
            out.append(times[i - 1] + frac * (times[i] - times[i - 1]))
    return out


def _sym3_eigenvalues(matrix: list[list[float]]) -> list[float]:
    """Sorted eigenvalues of a symmetric 3x3 (NumPy here; the replay uses Jacobi rotations)."""
    return [float(x) for x in np.sort(np.linalg.eigvalsh(np.asarray(matrix)))]


def analytic_body_inertia(geoms: list[dict]) -> dict | None:
    """Composite mass, CoM and principal inertia of a body made only of spheres and boxes.

    Returns None when the body contains any other geom type (capsule bodies are out of scope).
    """
    if not geoms or any(g["type"] not in ("sphere", "box") for g in geoms):
        return None
    total = sum(g["mass"] for g in geoms)
    com = [sum(g["mass"] * g["pos"][i] for g in geoms) / total for i in range(3)]
    tensor = [[0.0] * 3 for _ in range(3)]
    for g in geoms:
        m = g["mass"]
        if g["type"] == "sphere":
            r = g["size"][0]
            own = [0.4 * m * r * r] * 3
        else:
            hx, hy, hz = g["size"]
            own = [m * (hy * hy + hz * hz) / 3.0, m * (hx * hx + hz * hz) / 3.0, m * (hx * hx + hy * hy) / 3.0]
        d = [g["pos"][i] - com[i] for i in range(3)]
        d2 = sum(x * x for x in d)
        for i in range(3):
            for j in range(3):
                tensor[i][j] += (own[i] if i == j else 0.0) + m * ((d2 if i == j else 0.0) - d[i] * d[j])
    return {"mass_kg": total, "com_m": com, "principal_kgm2": _sym3_eigenvalues(tensor)}


# ---------------------------------------------------------------- 判準

def _common_criteria(case: dict, contract: dict, ke_replay: list[float], pe_replay: list[float]) -> list[dict]:
    tol = contract["tolerances"]
    trace = case["raw_trace"]
    dt = case["physics_dt_s"]
    compiled = case["compiled_model"]
    times = [s["time_s"] for s in trace]
    grid_err = max(abs(t - k * dt) for k, t in enumerate(times))
    ke_engine = [s["energy_engine"][1] for s in trace]
    pe_engine = [s["energy_engine"][0] for s in trace]
    ke_scale = 1.0 + max(abs(x) for x in ke_engine)
    pe_scale = 1.0 + max(abs(x) for x in pe_engine)
    ke_diff = max(abs(a - b) for a, b in zip(ke_replay, ke_engine)) / ke_scale
    pe_diff = max(abs(a - b) for a, b in zip(pe_replay, pe_engine)) / pe_scale
    model_ok = (
        compiled["integrator"] == contract["integrator"]
        and compiled["gravity_mps2"] == [0.0, 0.0, -contract["gravity_mps2"]]
        and compiled["nu"] == 0
        and compiled["energy_flag_enabled"] is True
    )
    if case["family"] == "articulated":
        a = contract["articulated"]
        joints = compiled["joints"]
        model_ok = model_ok and len(joints) == a["expected_joint_count"] and all(
            (abs(j["damping"] - (a["expected_arm_damping"] if j["name"].startswith(("shoulder", "elbow"))
                                 else a["expected_leg_damping"])) <= 1e-12) for j in joints)
    else:
        joints = compiled["joints"]
        model_ok = model_ok and len(joints) == 1 and joints[0]["damping"] == 0.0 and joints[0]["armature"] == 0.0
    return [
        _criterion("FINITE_RAW_VALUES", _finite_tree(trace), "==", True, "bool"),
        _criterion("TRACE_STEP_COUNT", len(trace), "==", case["expected_sample_count"], "samples"),
        _criterion("TRACE_TIME_GRID", grid_err, "<=", tol["time_grid_error_max_s"], "s"),
        _criterion("COMPILED_TIMESTEP_IDENTITY", compiled["timestep_s"], "==", dt, "s"),
        _criterion("COMPILED_MODEL_CONTRACT", model_ok, "==", True, "bool"),
        _criterion("EXTERNAL_FORCE_ABSENT",
                   max(max(s["qfrc_applied_abs_max"], s["xfrc_applied_abs_max"]) for s in trace), "<=", 0.0, "N or N·m"),
        _criterion("NO_CONTACT", max(s["ncon"] for s in trace), "<=", 0, "contacts"),
        _criterion("ENGINE_KINETIC_ENERGY_AGREEMENT", ke_diff, "<=", tol["engine_energy_agreement_relative_max"], "relative"),
        _criterion("ENGINE_POTENTIAL_ENERGY_AGREEMENT", pe_diff, "<=", tol["engine_energy_agreement_relative_max"], "relative"),
    ]


def evaluate_pendulum_case(case: dict, contract: dict = DYNAMIC_SUITE_CONTRACT) -> dict:
    tol = contract["tolerances"]
    p = contract["pendulum"]
    closed = pendulum_closed_form(contract)
    g = contract["gravity_mps2"]
    trace = case["raw_trace"]
    times = [s["time_s"] for s in trace]
    theta = [s["qpos"][0] for s in trace]
    theta_dot = [s["qvel"][0] for s in trace]
    inertia = closed["inertia_pivot_kgm2"]
    energy = [0.5 * inertia * w * w + p["mass_kg"] * g * p["length_m"] * (1.0 - math.cos(q)) for q, w in zip(theta, theta_dot)]
    energy0 = closed["energy0_j"]
    # 引擎 PE 以絕對 z 計：m g (z_pivot − L cos θ)；KE = ½ I θ̇²
    ke_replay = [0.5 * inertia * w * w for w in theta_dot]
    pe_replay = [p["mass_kg"] * g * (p["pivot_z_m"] - p["length_m"] * math.cos(q)) for q in theta]
    crossings = upward_zero_crossings(times, theta)
    periods = [b - a for a, b in zip(crossings[:-1], crossings[1:])]
    period_count = len(periods)
    period_meas = sum(periods) / period_count if period_count else float("nan")
    period_rel_err = abs(period_meas - closed["period_s"]) / closed["period_s"] if period_count else float("inf")
    fluctuation = max(abs(e - energy0) for e in energy) / energy0
    if period_count >= 2:
        first = [e for t, e in zip(times, energy) if crossings[0] <= t < crossings[1]]
        last = [e for t, e in zip(times, energy) if crossings[-2] <= t < crossings[-1]]
        drift = abs(sum(last) / len(last) - sum(first) / len(first)) / energy0
    else:
        drift = float("inf")
    body = case["compiled_model"]["bodies"][0]
    sphere_inertia = 0.4 * p["mass_kg"] * p["radius_m"] ** 2
    inertia_rel = max(abs(x - sphere_inertia) for x in body["inertia_principal_kgm2"]) / sphere_inertia
    ipos_err = max(abs(a - b) for a, b in zip(body["ipos_m"], [0.0, 0.0, -p["length_m"]]))
    inertia_ok = inertia_rel <= tol["inertia_relative_error_max"] and ipos_err <= tol["com_abs_error_max_m"]
    criteria = _common_criteria(case, contract, ke_replay, pe_replay) + [
        _criterion("PENDULUM_PERIOD_COUNT", period_count, ">=", p["min_period_count"], "periods"),
        _criterion("PENDULUM_PERIOD_RELATIVE_ERROR", period_rel_err, "<=", tol["pendulum_period_relative_error_max"], "relative"),
        _criterion("PENDULUM_ENERGY_RELATIVE_FLUCTUATION", fluctuation, "<=", case["spec"]["energy_fluctuation_relative_max"], "relative"),
        _criterion("PENDULUM_ENERGY_SECULAR_DRIFT", drift, "<=", tol["pendulum_energy_secular_drift_relative_max"], "relative"),
        _criterion("PENDULUM_INERTIA_ANALYTIC_AGREEMENT", inertia_ok, "==", True, "bool"),
    ]
    metrics = {
        "closed_form": closed,
        "period_measured_s": period_meas,
        "period_count": period_count,
        "period_relative_error": period_rel_err,
        "energy_relative_fluctuation_max": fluctuation,
        "energy_secular_drift_relative": drift,
        "zero_crossings_s": crossings,
        "engine_ke_agreement_relative": criteria[7]["value"],
        "engine_pe_agreement_relative": criteria[8]["value"],
        "compiled_inertia_relative_error": inertia_rel,
        "compiled_ipos_abs_error_m": ipos_err,
    }
    return {"metrics": metrics, "criteria": criteria,
            "status": "PASS" if all(c["passed"] for c in criteria) else "FAIL"}


def evaluate_articulated_case(case: dict, contract: dict = DYNAMIC_SUITE_CONTRACT) -> dict:
    tol = contract["tolerances"]
    g = contract["gravity_mps2"]
    trace = case["raw_trace"]
    receipt = case["compiled_model"]
    times = [s["time_s"] for s in trace]
    ke_replay, pe_replay = [], []
    for s in trace:
        ke, pe = replay_energies(s, receipt, g)
        ke_replay.append(ke)
        pe_replay.append(pe)
    hinge_dofs = [(j["dof_adr"], j["damping"]) for j in receipt["joints"] if j["type"] == "HINGE"]
    damping = np.asarray([d for _, d in hinge_dofs])
    qd = np.asarray([[s["qvel"][adr] for adr, _ in hinge_dofs] for s in trace])
    power = (qd * qd) @ damping
    t = np.asarray(times)
    work = np.concatenate([[0.0], np.cumsum(0.5 * (power[1:] + power[:-1]) * np.diff(t))])
    ke_arr, pe_arr = np.asarray(ke_replay), np.asarray(pe_replay)
    e0 = float(ke_arr[0] + pe_arr[0])
    residual = ke_arr + pe_arr + work - e0
    e_scale = float(e0 - pe_arr.min())
    residual_rel = float(np.max(np.abs(residual)) / e_scale) if e_scale > 0 else float("inf")
    work = [float(x) for x in work]
    residual = [float(x) for x in residual]
    # 解析慣量（球＋盒 body）與質量總和（所有 body）
    geoms_by_body: dict[str, list[dict]] = {}
    for gm in receipt["geoms_from_mjcf"]:
        geoms_by_body.setdefault(gm["body"], []).append(gm)
    mass_err_max = 0.0
    inertia_rel_max = 0.0
    com_err_max = 0.0
    inertia_bodies_checked = []
    for body in receipt["bodies"]:
        geoms = geoms_by_body.get(body["name"], [])
        mass_err_max = max(mass_err_max, abs(body["mass_kg"] - sum(gm["mass"] for gm in geoms)))
        if body["name"] in contract["articulated"]["analytic_inertia_bodies"]:
            analytic = analytic_body_inertia(geoms)
            if analytic is None:
                inertia_rel_max = float("inf")
                continue
            compiled_sorted = sorted(body["inertia_principal_kgm2"])
            inertia_rel_max = max(inertia_rel_max, max(abs(a - b) / b for a, b in zip(analytic["principal_kgm2"], compiled_sorted)))
            com_err_max = max(com_err_max, max(abs(a - b) for a, b in zip(analytic["com_m"], body["ipos_m"])))
            inertia_bodies_checked.append(body["name"])
    inertia_ok = (inertia_rel_max <= tol["inertia_relative_error_max"] and com_err_max <= tol["com_abs_error_max_m"]
                  and sorted(inertia_bodies_checked) == sorted(contract["articulated"]["analytic_inertia_bodies"]))
    criteria = _common_criteria(case, contract, ke_replay, pe_replay) + [
        _criterion("ENERGY_SCALE_POSITIVE", e_scale, ">=", tol["energy_scale_min_j"], "J"),
        _criterion("ENERGY_BALANCE_RESIDUAL_RELATIVE_MAX", residual_rel, "<=", case["spec"]["energy_residual_relative_max"], "relative"),
        _criterion("BODY_MASS_ANALYTIC_AGREEMENT", mass_err_max, "<=", tol["mass_abs_error_max_kg"], "kg"),
        _criterion("BODY_INERTIA_ANALYTIC_AGREEMENT", inertia_ok, "==", True, "bool"),
    ]
    metrics = {
        "energy_initial_j": e0,
        "energy_scale_j": e_scale,
        "damping_work_final_j": work[-1],
        "kinetic_energy_max_j": max(ke_replay),
        "energy_balance_residual_abs_max_j": max(abs(r) for r in residual),
        "energy_balance_residual_relative_max": residual_rel,
        "engine_ke_agreement_relative": criteria[7]["value"],
        "engine_pe_agreement_relative": criteria[8]["value"],
        "body_mass_abs_error_max_kg": mass_err_max,
        "body_inertia_relative_error_max": inertia_rel_max,
        "body_com_abs_error_max_m": com_err_max,
        "inertia_bodies_checked": sorted(inertia_bodies_checked),
    }
    return {"metrics": metrics, "criteria": criteria,
            "status": "PASS" if all(c["passed"] for c in criteria) else "FAIL"}


def evaluate_case(case: dict, contract: dict = DYNAMIC_SUITE_CONTRACT) -> dict:
    return evaluate_pendulum_case(case, contract) if case["family"] == "pendulum" else evaluate_articulated_case(case, contract)


def _observed_order(q_coarse: float, q_medium: float, q_fine: float, floor: float) -> tuple[float | None, str]:
    d1, d2 = q_coarse - q_medium, q_medium - q_fine
    if abs(d1) <= floor or abs(d2) <= floor:
        return None, "ROUNDOFF_LIMITED"
    if (d1 > 0) != (d2 > 0):
        return None, "NON_MONOTONIC"
    return math.log(abs(d1) / abs(d2)) / math.log(2.0), "ESTIMATED"


def _non_dt_config(case: dict) -> dict:
    cfg = {k: v for k, v in case["compiled_model"].items() if k not in ("timestep_s", "mjcf_sha256")}
    cfg["spec"] = {k: v for k, v in case["spec"].items() if k not in ("physics_dt_s", "case_id", "roles",
                                                                      "energy_fluctuation_relative_max",
                                                                      "energy_residual_relative_max")}
    return cfg


def evaluate_suite(cases: list[dict], evaluations: list[dict], contract: dict = DYNAMIC_SUITE_CONTRACT) -> dict:
    tol = contract["tolerances"]
    expected = [(s["case_id"], s["family"], s["physics_dt_s"]) for s in contract["case_matrix"]]
    actual = [(c["case_id"], c["family"], c["physics_dt_s"]) for c in cases]
    by_id = {c["case_id"]: (c, e) for c, e in zip(cases, evaluations)}

    def metric(case_id: str, key: str) -> float:
        return by_id[case_id][1]["metrics"][key]

    closed = pendulum_closed_form(contract)
    t4, t2, t1 = (metric(f"known_pendulum_{n}ms", "period_measured_s") for n in (4, 2, 1))
    fine_delta_rel = abs(t2 - t1) / closed["period_s"]
    period_monotone = abs(t2 - t1) <= max(abs(t4 - t2), tol["pendulum_period_roundoff_floor_s"])
    r4, r2, r1 = (metric(f"articulated_passive_swing_{n}ms", "energy_balance_residual_relative_max") for n in (4, 2, 1))
    floor = tol["articulated_residual_roundoff_floor"]
    residual_monotone = (r1 <= max(r2, floor)) and (r2 <= max(r4, floor))
    non_dt_ok = all(
        _non_dt_config(by_id[f"{fam}_{n}ms"][0]) == _non_dt_config(by_id[f"{fam}_4ms"][0])
        for fam in ("known_pendulum", "articulated_passive_swing") for n in (2, 1)
    )
    period_order, period_order_status = _observed_order(t4, t2, t1, tol["pendulum_period_roundoff_floor_s"])
    residual_order, residual_order_status = _observed_order(r4, r2, r1, floor)
    criteria = [
        _criterion("EXACT_CASE_INVENTORY", actual == expected, "==", True, "bool"),
        _criterion("ALL_CASES_PASS", sum(1 for e in evaluations if e["status"] == "PASS"), "==", len(expected), "cases"),
        _criterion("PENDULUM_PERIOD_TIMESTEP_FINE_DELTA", fine_delta_rel, "<=", tol["pendulum_period_fine_delta_relative_max"], "relative"),
        _criterion("PENDULUM_PERIOD_TIMESTEP_MONOTONE", period_monotone, "==", True, "bool"),
        _criterion("ARTICULATED_RESIDUAL_TIMESTEP_MONOTONE", residual_monotone, "==", True, "bool"),
        _criterion("TIMESTEP_NON_DT_CONFIG_IDENTITY", non_dt_ok, "==", True, "bool"),
    ]
    return {
        "criteria": criteria,
        "status": "PASS" if all(c["passed"] for c in criteria) else "FAIL",
        "timestep_study": {
            "pendulum_period_s": {"4ms": t4, "2ms": t2, "1ms": t1, "closed_form": closed["period_s"]},
            "pendulum_period_observed_order": period_order, "pendulum_period_order_status": period_order_status,
            "articulated_residual_relative": {"4ms": r4, "2ms": r2, "1ms": r1},
            "articulated_residual_observed_order": residual_order, "articulated_residual_order_status": residual_order_status,
        },
    }


def run_dynamic_suite(contract: dict = DYNAMIC_SUITE_CONTRACT) -> dict:
    cases = [run_case(spec, contract) for spec in contract["case_matrix"]]
    evaluations = [evaluate_case(c, contract) for c in cases]
    suite = evaluate_suite(cases, evaluations, contract)
    for case, evaluation in zip(cases, evaluations):
        case.update(evaluation)
    return {
        "schema_version": PRIMARY_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "claim_boundary": CLAIM_BOUNDARY,
        "contract": deepcopy(contract),
        "contract_sha256": "sha256:" + hashlib.sha256(
            json.dumps(contract, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest(),
        "cases": cases,
        "suite": suite,
        "status": "PASS" if suite["status"] == "PASS" and all(c["status"] == "PASS" for c in cases) else "FAIL",
    }


def summary_without_raw(result: dict) -> dict:
    out = deepcopy(result)
    for case in out["cases"]:
        case.pop("raw_trace", None)
        case.pop("mjcf", None)
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--raw-output", type=Path, help="write the full result (with raw traces) as JSON; exclusive create")
    args = parser.parse_args(argv)
    result = run_dynamic_suite()
    if args.raw_output is not None:
        payload = json.dumps(result, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        args.raw_output.parent.mkdir(parents=True, exist_ok=True)
        with args.raw_output.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
        result["raw_artifact"] = {
            "path": str(args.raw_output),
            "sha256": "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest(),
            "size_bytes": len(payload.encode("utf-8")),
            "write_policy": "EXCLUSIVE_CREATE_NO_OVERWRITE",
        }
    print(json.dumps(summary_without_raw(result), ensure_ascii=False, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())

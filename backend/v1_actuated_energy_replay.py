"""Stdlib-only replay for the frozen V1 actuated energy suite.

No MuJoCo, no NumPy, no project imports.  The replay validates the primary result's schema and
frozen contract, then recomputes every metric from the serialized per-step samples and the
compiled-model receipts (kinetic and potential energy from body kinematics and principal inertias,
actuator, damping and contact work by trapezoid, the prescribed torque signal, the plant's PD law,
contact bookkeeping) and compares with the primary metrics.  Primary metrics are comparison
receipts, never replay inputs.

    python -I -S backend/v1_actuated_energy_replay.py PRIMARY_RESULT.json
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sys

PRIMARY_SCHEMA_VERSION = "V1_ACTUATED_ENERGY_SUITE_V1"
REPLAY_SCHEMA_VERSION = "V1_ACTUATED_ENERGY_REPLAY_RECEIPT_V1"
REPLAY_CLAIM_BOUNDARY = (
    "SIM_ONLY_MUJOCO / NOT_PHYSICALLY_VALIDATED. This stdlib-only process replay recomputes the "
    "actuated energy balance (actuator, damping and contact work against the engine energy) from "
    "serialized evidence and compares it with the primary. Torques, kinematics, contact forces and "
    "compiled parameters remain MuJoCo receipts; this is not physical validation and does not make V1 PASS."
)

# 與 primary 的 ACTUATED_SUITE_CONTRACT 逐字相同的凍結常數；漂移即 ReplayValidationError。
FROZEN_CONTRACT_ID = "v1_actuated_energy_suite_v1"
FROZEN_GRAVITY = 9.81
FROZEN_JOINT_ORDER = ["hip_roll_l", "hip_pitch_l", "knee_l", "ankle_l", "hip_roll_r", "hip_pitch_r", "knee_r", "ankle_r",
                      "shoulder_l", "elbow_l", "shoulder_r", "elbow_r"]
FROZEN_OPENLOOP = {"trunk_z_m": 1.6, "duration_s": 3.0, "amplitude_fraction": 0.015,
                   "frequencies_hz": [0.55, 0.75, 0.95, 1.15, 0.65, 0.85, 1.05, 1.25, 0.60, 0.80, 1.00, 1.20], "phase_step_rad": 0.4}
FROZEN_SQUAT = {"duration_s": 5.0, "settle_s": 1.0, "depth_m": 0.05, "frequency_hz": 0.25, "crouch_m": 0.10,
                "shoulder_rad": 0.05, "elbow_rad": 0.35, "bias_feedforward": 0.8, "mu": 1.0,
                "planted_from_s": 0.5, "contact_count": 8, "fall_z_fraction_min": 0.75, "fall_angle_max_rad": 0.2}
FROZEN_TOLERANCES = {
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
}
FROZEN_CASE_IDS = ("actuated_openloop_4ms", "actuated_openloop_2ms", "actuated_openloop_1ms",
                   "planted_squat_4ms", "planted_squat_2ms", "planted_squat_1ms")
FROZEN_CASE_DT = (0.004, 0.002, 0.001, 0.004, 0.002, 0.001)
FROZEN_RESIDUAL_MAX = (0.02, 0.01, 0.005, 0.05, 0.025, 0.0125)
SAMPLE_KEYS = ("time_s", "qpos", "qvel", "qacc", "ctrl", "actuator_force", "qfrc_actuator", "qfrc_bias",
               "qfrc_constraint", "energy_engine", "ncon", "contacts", "bodies", "qfrc_applied_abs_max", "xfrc_applied_abs_max")
CONTACT_KEYS = ("geom1", "geom2", "body1", "body2", "dim", "dist", "pos", "frame", "force_contact_frame")
BODY_KEYS = ("xpos", "xipos", "ximat", "angvel_world", "linvel_com_world")


class ReplayValidationError(RuntimeError):
    pass


# ---------------------------------------------------------------- 驗證

def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ReplayValidationError(message)


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


def _is_num_list(value, n: int | None = None) -> bool:
    if not isinstance(value, list) or (n is not None and len(value) != n):
        return False
    return all(isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(float(x)) for x in value)


def validate_primary(primary: dict) -> None:
    _require(isinstance(primary, dict), "primary must be an object")
    _require(primary.get("schema_version") == PRIMARY_SCHEMA_VERSION, "schema_version drift")
    contract = primary.get("contract")
    _require(isinstance(contract, dict), "contract missing")
    _require(contract.get("contract_id") == FROZEN_CONTRACT_ID, "contract_id drift")
    _require(contract.get("tolerances") == FROZEN_TOLERANCES, "tolerance drift")
    _require(contract.get("gravity_mps2") == FROZEN_GRAVITY, "gravity drift")
    _require(contract.get("joint_order") == FROZEN_JOINT_ORDER, "joint order drift")
    _require(contract.get("openloop") == FROZEN_OPENLOOP and contract.get("squat") == FROZEN_SQUAT, "case definition drift")
    matrix = contract.get("case_matrix")
    _require(isinstance(matrix, list) and [s.get("case_id") for s in matrix] == list(FROZEN_CASE_IDS), "case matrix drift")
    _require([s.get("physics_dt_s") for s in matrix] == list(FROZEN_CASE_DT), "case dt drift")
    _require([s.get("energy_residual_relative_max") for s in matrix] == list(FROZEN_RESIDUAL_MAX), "residual threshold drift")
    cases = primary.get("cases")
    _require(isinstance(cases, list) and [c.get("case_id") for c in cases] == list(FROZEN_CASE_IDS), "case inventory drift")
    n_joint = len(FROZEN_JOINT_ORDER)
    for case, dt, spec in zip(cases, FROZEN_CASE_DT, matrix):
        cid = case.get("case_id")
        _require(case.get("physics_dt_s") == dt, f"{cid}: dt drift")
        _require(case.get("spec") == spec, f"{cid}: spec drift")
        _require(isinstance(case.get("compiled_model"), dict) and isinstance(case.get("raw_trace"), list), f"{cid}: raw_trace or compiled_model missing")
        _require(isinstance(case.get("criteria"), list) and all(isinstance(k, dict) and "id" in k and "passed" in k for k in case["criteria"]), f"{cid}: criteria malformed")
        _require(isinstance(case.get("metrics"), dict) and isinstance(case.get("mjcf"), str), f"{cid}: metrics or mjcf missing")
        cm = case["compiled_model"]
        for key in ("timestep_s", "integrator", "gravity_mps2", "energy_flag_enabled", "nq", "nv", "nu", "nbody", "joints", "bodies",
                    "actuators", "dof_damping", "dof_armature", "has_floor", "has_freejoint"):
            _require(key in cm, f"{cid}: compiled_model.{key} missing")
        nq, nv, nu, nbody = int(cm["nq"]), int(cm["nv"]), int(cm["nu"]), int(cm["nbody"])
        _require(nu == n_joint and len(cm["actuators"]) == nu and len(cm["bodies"]) == nbody - 1, f"{cid}: actuator/body inventory")
        _require(len(case["raw_trace"]) == case.get("expected_sample_count"), f"{cid}: sample count mismatch")
        if case["family"] == "squat":
            ctl = case.get("controller")
            _require(isinstance(ctl, dict) and _is_num_list(ctl.get("kp"), n_joint) and _is_num_list(ctl.get("kd"), n_joint)
                     and isinstance(ctl.get("z_nom_m"), float) and ctl["z_nom_m"] > 0, f"{cid}: controller receipt")
        for i, sample in enumerate(case["raw_trace"]):
            _require(isinstance(sample, dict) and all(k in sample for k in SAMPLE_KEYS), f"{cid}[{i}]: sample keys")
            _require(isinstance(sample["time_s"], (int, float)) and math.isfinite(sample["time_s"]), f"{cid}[{i}]: time")
            _require(_is_num_list(sample["qpos"], nq) and _is_num_list(sample["qvel"], nv) and _is_num_list(sample["qacc"], nv)
                     and _is_num_list(sample["qfrc_actuator"], nv) and _is_num_list(sample["qfrc_bias"], nv)
                     and _is_num_list(sample["qfrc_constraint"], nv), f"{cid}[{i}]: state shape")
            _require(_is_num_list(sample["ctrl"], nu) and _is_num_list(sample["actuator_force"], nu), f"{cid}[{i}]: actuator shape")
            _require(_is_num_list(sample["energy_engine"], 2), f"{cid}[{i}]: energy")
            _require(isinstance(sample["ncon"], int) and sample["ncon"] == len(sample["contacts"]), f"{cid}[{i}]: ncon")
            _require(isinstance(sample["bodies"], list) and len(sample["bodies"]) == nbody - 1, f"{cid}[{i}]: bodies")
            for b in sample["bodies"]:
                _require(isinstance(b, dict) and all(k in b for k in BODY_KEYS) and _is_num_list(b["xpos"], 3) and _is_num_list(b["xipos"], 3)
                         and _is_num_list(b["ximat"], 9) and _is_num_list(b["angvel_world"], 3) and _is_num_list(b["linvel_com_world"], 3), f"{cid}[{i}]: body shape")
            for c in sample["contacts"]:
                _require(isinstance(c, dict) and all(k in c for k in CONTACT_KEYS) and _is_num_list(c["pos"], 3) and _is_num_list(c["frame"], 9)
                         and _is_num_list(c["force_contact_frame"], 6) and isinstance(c["body1"], int) and isinstance(c["body2"], int)
                         and 0 <= c["body1"] < nbody and 0 <= c["body2"] < nbody, f"{cid}[{i}]: contact shape")
            if case["family"] == "squat":
                _require(_is_num_list(sample.get("q_ref"), n_joint) and _is_num_list(sample.get("qd_ref"), n_joint), f"{cid}[{i}]: reference")
    suite = primary.get("suite")
    _require(isinstance(suite, dict) and isinstance(suite.get("criteria"), list), "suite block missing")


# ---------------------------------------------------------------- 純 Python 重算

def _criterion(criterion_id: str, value, operator: str, limit, unit: str) -> dict:
    ops = {"<=": lambda a, b: a <= b, ">=": lambda a, b: a >= b, "==": lambda a, b: a == b, "<": lambda a, b: a < b}
    finite = value is not None and (not isinstance(value, float) or math.isfinite(value))
    passed = bool(finite and ops[operator](value, limit))
    return {"id": criterion_id, "value": value, "operator": operator, "limit": limit, "unit": unit, "passed": passed}


def quaternion_pitch_roll(quat) -> tuple[float, float]:
    w, x, y, z = [float(v) for v in quat]
    pitch = math.asin(max(-1.0, min(1.0, 2.0 * (w * y - z * x))))
    roll = math.atan2(2.0 * (w * x + y * z), 1.0 - 2.0 * (x * x + y * y))
    return pitch, roll


def prescribed_ctrl(t: float, force_upper: list[float], contract: dict) -> list[float]:
    o = contract["openloop"]
    return [o["amplitude_fraction"] * float(force_upper[j]) * math.sin(2.0 * math.pi * o["frequencies_hz"][j] * t + o["phase_step_rad"] * j)
            for j in range(len(force_upper))]


def body_kinetic_energy(sample_body: dict, body_receipt: dict) -> float:
    m = body_receipt["mass_kg"]
    inertia = body_receipt["inertia_principal_kgm2"]
    w = sample_body["angvel_world"]
    v_com = sample_body["linvel_com_world"]
    mat = sample_body["ximat"]
    w_local = [sum(mat[3 * k + i] * w[k] for k in range(3)) for i in range(3)]
    rot = 0.5 * sum(inertia[i] * w_local[i] * w_local[i] for i in range(3))
    return 0.5 * m * sum(x * x for x in v_com) + rot


def replay_energies(sample: dict, model_receipt: dict, gravity: float) -> tuple[float, float]:
    ke = 0.0
    pe = 0.0
    for body, receipt in zip(sample["bodies"], model_receipt["bodies"]):
        ke += body_kinetic_energy(body, receipt)
        pe += receipt["mass_kg"] * gravity * body["xipos"][2]
    for joint in model_receipt["joints"]:
        if joint["type"] == "HINGE":
            qd = sample["qvel"][joint["dof_adr"]]
            ke += 0.5 * joint["armature"] * qd * qd
    return ke, pe


def _dot(a, b) -> float:
    return sum(float(x) * float(y) for x, y in zip(a, b))


def _cross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def contact_force_on_robot(contact: dict) -> list[float]:
    fr = [float(x) for x in contact["frame"]]
    f = [float(x) for x in contact["force_contact_frame"][:3]]
    world = [f[0] * fr[0] + f[1] * fr[3] + f[2] * fr[6],
             f[0] * fr[1] + f[1] * fr[4] + f[2] * fr[7],
             f[0] * fr[2] + f[1] * fr[5] + f[2] * fr[8]]
    return world if contact["body1"] == 0 else [-x for x in world]


def contact_robot_body(contact: dict) -> int:
    return contact["body2"] if contact["body1"] == 0 else contact["body1"]


def contact_power(sample: dict) -> float:
    total = 0.0
    for c in sample["contacts"]:
        body = sample["bodies"][contact_robot_body(c) - 1]
        f = contact_force_on_robot(c)
        r = [float(c["pos"][i]) - float(body["xipos"][i]) for i in range(3)]
        wxr = _cross([float(x) for x in body["angvel_world"]], r)
        v = [float(body["linvel_com_world"][i]) + wxr[i] for i in range(3)]
        total += _dot(f, v)
    return total


def _trapezoid_cumulative(values: list[float], dt: float) -> list[float]:
    out = [0.0]
    acc = 0.0
    for k in range(1, len(values)):
        acc += 0.5 * (values[k] + values[k - 1]) * dt
        out.append(acc)
    return out


def _axis_alignment_error(frame: list[float]) -> float:
    err = 0.0
    for r in range(3):
        row = frame[3 * r:3 * r + 3]
        best = math.inf
        for a in range(3):
            for s in (1.0, -1.0):
                unit = [s if i == a else 0.0 for i in range(3)]
                best = min(best, max(abs(row[i] - unit[i]) for i in range(3)))
        err = max(err, best)
    return err


def energy_accounting(case: dict, contract: dict) -> dict:
    trace = case["raw_trace"]
    dt = float(case["physics_dt_s"])
    damping = [float(x) for x in case["compiled_model"]["dof_damping"]]
    w_act = [0.0]
    acc = 0.0
    for k in range(len(trace) - 1):
        tau = trace[k]["qfrc_actuator"]; v0 = trace[k]["qvel"]; v1 = trace[k + 1]["qvel"]
        acc += sum(float(tau[i]) * 0.5 * (float(v0[i]) + float(v1[i])) for i in range(len(tau))) * dt
        w_act.append(acc)
    p_damp = [sum(damping[i] * float(v) * float(v) for i, v in enumerate(s["qvel"])) for s in trace]
    w_damp = _trapezoid_cumulative(p_damp, dt)
    if case["family"] == "squat":
        w_con = _trapezoid_cumulative([contact_power(s) for s in trace], dt)
    else:
        w_con = [0.0] * len(trace)
    energy = [float(s["energy_engine"][0]) + float(s["energy_engine"][1]) for s in trace]
    residual = [energy[k] - energy[0] - w_act[k] + w_damp[k] - w_con[k] for k in range(len(trace))]
    w_act_abs_max = max(abs(x) for x in w_act)
    e_range = max(energy) - min(energy)
    e_scale = max(w_act_abs_max, e_range, float(contract["tolerances"]["energy_scale_min_j"]))
    n_joint = len(contract["joint_order"])
    w_disc = [0.0]
    acc = 0.0
    for k in range(len(trace) - 1):
        q0 = trace[k]["qpos"][-n_joint:]; q1 = trace[k + 1]["qpos"][-n_joint:]; tau = trace[k]["qfrc_actuator"][-n_joint:]
        acc += sum(float(tau[j]) * (float(q1[j]) - float(q0[j])) for j in range(n_joint))
        w_disc.append(acc)
    residual_disc = [energy[k] - energy[0] - w_disc[k] + w_damp[k] - w_con[k] for k in range(len(trace))]
    return {
        "actuator_work_abs_max_j": w_act_abs_max,
        "actuator_work_final_j": w_act[-1],
        "damping_work_final_j": w_damp[-1],
        "contact_work_final_j": w_con[-1],
        "energy_change_final_j": energy[-1] - energy[0],
        "energy_range_j": e_range,
        "energy_scale_j": e_scale,
        "energy_residual_abs_max_j": max(abs(x) for x in residual),
        "energy_residual_relative_max": max(abs(x) for x in residual) / e_scale,
        "discrete_work_residual_relative_max": max(abs(x) for x in residual_disc) / e_scale,
    }


def common_metrics(case: dict, contract: dict) -> dict:
    trace = case["raw_trace"]
    dt = float(case["physics_dt_s"])
    cm = case["compiled_model"]
    g = float(contract["gravity_mps2"])
    grid_err = max(abs(float(s["time_s"]) - dt * n) for n, s in enumerate(trace))
    ext = max(max(float(s["qfrc_applied_abs_max"]), float(s["xfrc_applied_abs_max"])) for s in trace)
    lo = [float(a["forcerange"][0]) for a in cm["actuators"]]
    hi = [float(a["forcerange"][1]) for a in cm["actuators"]]
    gear = [float(a["gear"][0]) for a in cm["actuators"]]
    dof = [int(a["dof_adr"]) for a in cm["actuators"]]
    nv = int(cm["nv"])
    clip_err = gear_err = ke_err = pe_err = implicit = 0.0
    ke_scale = pe_scale = float(contract["tolerances"]["energy_scale_min_j"])
    for n, s in enumerate(trace):
        for j in range(len(hi)):
            clipped = min(max(float(s["ctrl"][j]), lo[j]), hi[j])
            clip_err = max(clip_err, abs(float(s["actuator_force"][j]) - clipped))
        projected = [0.0] * nv
        for j in range(len(hi)):
            projected[dof[j]] += gear[j] * float(s["actuator_force"][j])
        gear_err = max(gear_err, max(abs(float(s["qfrc_actuator"][i]) - projected[i]) for i in range(nv)))
        ke, pe = replay_energies(s, cm, g)
        ke_err = max(ke_err, abs(ke - float(s["energy_engine"][1])))
        pe_err = max(pe_err, abs(pe - float(s["energy_engine"][0])))
        ke_scale = max(ke_scale, abs(float(s["energy_engine"][1])))
        pe_scale = max(pe_scale, abs(float(s["energy_engine"][0])))
        if n + 1 < len(trace):
            nxt = trace[n + 1]
            implicit = max(implicit, max(abs(float(nxt["qvel"][i]) - float(s["qvel"][i]) - dt * float(s["qacc"][i])) for i in range(nv)))
    metrics = {
        "time_grid_error_max_s": grid_err,
        "external_force_abs_max": ext,
        "actuator_clip_error_max": clip_err,
        "gear_projection_error_max": gear_err,
        "engine_kinetic_energy_agreement_relative_max": ke_err / ke_scale,
        "engine_potential_energy_agreement_relative_max": pe_err / pe_scale,
        "implicit_velocity_correction_max": implicit,
        "ncon_max": max(int(s["ncon"]) for s in trace),
        "sample_count": len(trace),
    }
    metrics.update(energy_accounting(case, contract))
    return metrics


def _model_contract_ok(case: dict, contract: dict) -> bool:
    cm = case["compiled_model"]
    if cm["integrator"] != contract["integrator"] or not cm["energy_flag_enabled"]:
        return False
    if [float(x) for x in cm["gravity_mps2"]] != [0.0, 0.0, -float(contract["gravity_mps2"])]:
        return False
    if int(cm["nu"]) != len(contract["joint_order"]) or [a["joint"] for a in cm["actuators"]] != contract["joint_order"]:
        return False
    for a in cm["actuators"]:
        if float(a["gear"][0]) != 1.0 or a["ctrlrange"] != a["forcerange"] or float(a["forcerange"][1]) <= 0.0 or a["trntype"] != "mjTRN_JOINT":
            return False
    expect_floor = case["family"] == "squat"
    if bool(cm["has_floor"]) != expect_floor or bool(cm["has_freejoint"]) != expect_floor:
        return False
    joints = {j["name"]: j for j in cm["joints"]}
    for name in contract["joint_order"]:
        j = joints.get(name)
        if j is None or j["type"] != "HINGE":
            return False
        if float(j["damping"]) != (0.3 if name.startswith(("shoulder", "elbow")) else 1.0):
            return False
    if case["family"] == "squat" and case["mjcf"].count('friction="1.0 0.005 0.0001"') < 3:
        return False
    return True


def _common_criteria(case: dict, contract: dict, metrics: dict) -> list[dict]:
    tol = contract["tolerances"]
    trace = case["raw_trace"]
    return [
        _criterion("FINITE_RAW_VALUES", 1 if _finite_tree(trace) else 0, "==", 1, "flag"),
        _criterion("TRACE_STEP_COUNT", len(trace), "==", case["expected_sample_count"], "samples"),
        _criterion("TRACE_TIME_GRID", metrics["time_grid_error_max_s"], "<=", tol["time_grid_error_max_s"], "s"),
        _criterion("COMPILED_TIMESTEP_IDENTITY", case["compiled_model"]["timestep_s"], "==", case["physics_dt_s"], "s"),
        _criterion("COMPILED_MODEL_CONTRACT", 1 if _model_contract_ok(case, contract) else 0, "==", 1, "flag"),
        _criterion("EXTERNAL_FORCE_ABSENT", metrics["external_force_abs_max"], "<=", 0.0, "N or N·m"),
        _criterion("ACTUATOR_FORCE_IS_CLIPPED_CTRL", metrics["actuator_clip_error_max"], "<=", tol["actuator_clip_abs_max"], "N·m"),
        _criterion("QFRC_ACTUATOR_MATCHES_GEAR_FORCE", metrics["gear_projection_error_max"], "<=", tol["gear_projection_abs_max"], "N·m"),
        _criterion("ENGINE_KINETIC_ENERGY_AGREEMENT", metrics["engine_kinetic_energy_agreement_relative_max"], "<=", tol["engine_energy_agreement_relative_max"], "relative"),
        _criterion("ENGINE_POTENTIAL_ENERGY_AGREEMENT", metrics["engine_potential_energy_agreement_relative_max"], "<=", tol["engine_energy_agreement_relative_max"], "relative"),
        _criterion("ACTUATOR_WORK_SCALE_MIN", metrics["actuator_work_abs_max_j"], ">=", tol["actuator_work_scale_min_j"], "J"),
        _criterion("ENERGY_BALANCE_RESIDUAL_RELATIVE_MAX", metrics["energy_residual_relative_max"], "<=", case["spec"]["energy_residual_relative_max"], "relative to energy scale"),
    ]


def evaluate_openloop_case(case: dict, contract: dict) -> dict:
    tol = contract["tolerances"]
    trace = case["raw_trace"]
    metrics = common_metrics(case, contract)
    hi = [float(a["forcerange"][1]) for a in case["compiled_model"]["actuators"]]
    err = 0.0
    for s in trace:
        expected = prescribed_ctrl(float(s["time_s"]), hi, contract)
        err = max(err, max(abs(float(c) - e) / h for c, e, h in zip(s["ctrl"], expected, hi)))
    metrics["prescribed_ctrl_relative_error_max"] = err
    criteria = _common_criteria(case, contract, metrics) + [
        _criterion("CTRL_MATCHES_PRESCRIBED", err, "<=", tol["prescribed_ctrl_relative_max"], "relative to forcerange"),
        _criterion("NO_CONTACT", metrics["ncon_max"], "==", 0, "contacts"),
    ]
    return {"case_id": case["case_id"], "family": "openloop", "physics_dt_s": case["physics_dt_s"],
            "status": "PASS" if all(c["passed"] for c in criteria) else "FAIL", "criteria": criteria, "metrics": metrics}


def evaluate_squat_case(case: dict, contract: dict) -> dict:
    tol = contract["tolerances"]
    sq = contract["squat"]
    trace = case["raw_trace"]
    dt = float(case["physics_dt_s"])
    metrics = common_metrics(case, contract)
    ctl = case["controller"]
    kp = [float(x) for x in ctl["kp"]]; kd = [float(x) for x in ctl["kd"]]
    n_joint = len(contract["joint_order"])
    mu = float(sq["mu"])
    pd_err = qd_err = angle_max = util_max = axis_err = closure = 0.0
    z_min_frac = math.inf
    fn_min = math.inf
    planted_ok = True
    for n, s in enumerate(trace):
        q = s["qpos"][-n_joint:]; qd = s["qvel"][-n_joint:]; bias = s["qfrc_bias"][-n_joint:]
        for j in range(n_joint):
            law = kp[j] * (float(s["q_ref"][j]) - float(q[j])) + kd[j] * (float(s["qd_ref"][j]) - float(qd[j])) + sq["bias_feedforward"] * float(bias[j])
            pd_err = max(pd_err, abs(float(s["ctrl"][j]) - law))
            expected_qd = 0.0 if n == 0 else (float(s["q_ref"][j]) - float(trace[n - 1]["q_ref"][j])) / dt
            qd_err = max(qd_err, abs(float(s["qd_ref"][j]) - expected_qd))
        z_min_frac = min(z_min_frac, float(s["qpos"][2]) / float(ctl["z_nom_m"]))
        pitch, roll = quaternion_pitch_roll(s["qpos"][3:7])
        angle_max = max(angle_max, abs(pitch), abs(roll))
        if float(s["time_s"]) >= sq["planted_from_s"] - 1e-9 * dt and int(s["ncon"]) != sq["contact_count"]:
            planted_ok = False
        world = [0.0, 0.0, 0.0]
        for c in s["contacts"]:
            axis_err = max(axis_err, _axis_alignment_error([float(x) for x in c["frame"]]))
            f = c["force_contact_frame"]
            fn_min = min(fn_min, float(f[0]))
            tangential = math.hypot(float(f[1]), float(f[2]))
            if f[0] > 0.0:
                util_max = max(util_max, tangential / (mu * float(f[0])))
            elif tangential > 0.0:
                util_max = math.inf
            fw = contact_force_on_robot(c)
            for i in range(3):
                world[i] += fw[i]
        closure = max(closure, max(abs(world[i] - float(s["qfrc_constraint"][i])) for i in range(3)))
    if not math.isfinite(fn_min):
        fn_min = 0.0
    metrics.update({
        "pd_law_error_max": pd_err, "qd_ref_error_max": qd_err,
        "pelvis_z_fraction_min": z_min_frac, "trunk_angle_abs_max_rad": angle_max,
        "planted_contact_count_constant": 1 if planted_ok else 0,
        "normal_force_min_n": fn_min, "friction_cone_utilisation_max": util_max,
        "frame_axis_alignment_error_max": axis_err, "contact_force_closure_error_max_n": closure,
    })
    criteria = _common_criteria(case, contract, metrics) + [
        _criterion("CTRL_MATCHES_PD_LAW", pd_err, "<=", tol["pd_law_abs_max"], "N·m"),
        _criterion("QD_REF_IS_BACKWARD_DIFFERENCE", qd_err, "<=", tol["qd_ref_abs_max"], "rad/s"),
        _criterion("NO_FALL", 1 if (z_min_frac >= sq["fall_z_fraction_min"] and angle_max <= sq["fall_angle_max_rad"]) else 0, "==", 1, "flag"),
        _criterion("CONTACT_COUNT_PLANTED", metrics["planted_contact_count_constant"], "==", 1, "flag"),
        _criterion("UNILATERAL_NORMAL_FORCE", fn_min, ">=", tol["unilateral_normal_force_min_n"], "N"),
        _criterion("FRICTION_CONE_RESPECTED", util_max, "<=", tol["friction_cone_utilisation_max"], "ratio"),
        _criterion("CONTACT_FRAME_AXIS_ALIGNED", axis_err, "<=", tol["frame_axis_alignment_max"], "unit vector"),
        _criterion("CONTACT_FORCE_WORLD_SUM_MATCHES_QFRC_CONSTRAINT", closure, "<=", tol["contact_force_closure_max_n"], "N"),
    ]
    return {"case_id": case["case_id"], "family": "squat", "physics_dt_s": dt,
            "status": "PASS" if all(c["passed"] for c in criteria) else "FAIL", "criteria": criteria, "metrics": metrics}


def _orders(errors: list[float]) -> dict:
    if min(errors) <= 0.0:
        return {"coarse_medium": None, "medium_fine": None, "status": "ESTIMATED"}
    return {"coarse_medium": math.log2(errors[0] / errors[1]), "medium_fine": math.log2(errors[1] / errors[2]), "status": "ESTIMATED"}


def evaluate_suite(evaluations: list[dict], contract: dict) -> dict:
    by_id = {e["case_id"]: e for e in evaluations}
    open_e = [by_id[f"actuated_openloop_{k}ms"]["metrics"]["energy_residual_relative_max"] for k in (4, 2, 1)]
    squat_e = [by_id[f"planted_squat_{k}ms"]["metrics"]["energy_residual_relative_max"] for k in (4, 2, 1)]
    criteria = [
        _criterion("OPENLOOP_RESIDUAL_TIMESTEP_MONOTONE", 1 if open_e[0] > open_e[1] > open_e[2] else 0, "==", 1, "flag"),
        _criterion("SQUAT_RESIDUAL_TIMESTEP_MONOTONE", 1 if squat_e[0] > squat_e[1] > squat_e[2] else 0, "==", 1, "flag"),
    ]
    order = [s["case_id"] for s in contract["case_matrix"]]
    gate_ok = all(e["status"] == "PASS" for e in evaluations) and all(c["passed"] for c in criteria)
    return {
        "status": "PASS" if gate_ok else "FAIL",
        "criteria": criteria,
        "timestep_study": {
            "openloop_residual_relative": open_e, "openloop_observed_order": _orders(open_e),
            "squat_residual_relative": squat_e, "squat_observed_order": _orders(squat_e),
            "implicit_velocity_correction_max": [by_id[c]["metrics"]["implicit_velocity_correction_max"] for c in order],
            "discrete_work_residual_relative": [by_id[c]["metrics"]["discrete_work_residual_relative_max"] for c in order],
            "contact_work_final_j": [by_id[f"planted_squat_{k}ms"]["metrics"]["contact_work_final_j"] for k in (4, 2, 1)],
        },
    }


# ---------------------------------------------------------------- primary 對 replay

def _agree(a, b, rel: float, absolute: float) -> bool:
    if a is None or b is None:
        return a is None and b is None
    if isinstance(a, bool) or isinstance(b, bool):
        return a == b
    a, b = float(a), float(b)
    if math.isnan(a) or math.isnan(b):
        return False
    return abs(a - b) <= max(absolute, rel * max(abs(a), abs(b)))


def compare_metrics(primary_case: dict, replayed: dict, tol: dict) -> dict:
    rel, absolute = tol["primary_replay_relative_max"], tol["primary_replay_absolute_max"]
    p_metrics, r_metrics = primary_case["metrics"], replayed["metrics"]
    keys = sorted(set(p_metrics) | set(r_metrics))
    disagreements = []
    max_rel = 0.0
    for key in keys:
        a, b = p_metrics.get(key, math.nan), r_metrics.get(key, math.nan)
        if isinstance(a, (list, dict)) or isinstance(b, (list, dict)):
            if a != b:
                disagreements.append(key)
            continue
        if not _agree(a, b, rel, absolute):
            disagreements.append(key)
        if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool) and not isinstance(b, bool):
            scale = max(abs(float(a)), abs(float(b)))
            if scale > 0 and math.isfinite(scale) and abs(float(a) - float(b)) > absolute:
                max_rel = max(max_rel, abs(float(a) - float(b)) / scale)
    p_crit = [(k["id"], bool(k["passed"])) for k in primary_case["criteria"]]
    r_crit = [(k["id"], bool(k["passed"])) for k in replayed["criteria"]]
    return {"case_id": primary_case["case_id"], "metric_count": len(keys), "disagreements": disagreements,
            "max_relative_difference": max_rel, "criteria_identical": p_crit == r_crit,
            "agree": not disagreements and p_crit == r_crit}


def replay_actuated_suite(primary: dict, primary_sha256: str | None = None) -> dict:
    validate_primary(primary)
    contract = primary["contract"]
    tol = contract["tolerances"]
    evaluations = [evaluate_openloop_case(c, contract) if c["family"] == "openloop" else evaluate_squat_case(c, contract) for c in primary["cases"]]
    suite = evaluate_suite(evaluations, contract)
    comparisons = [compare_metrics(pc, ev, tol) for pc, ev in zip(primary["cases"], evaluations)]
    suite_identical = [(k["id"], bool(k["passed"])) for k in primary["suite"]["criteria"]] == [(k["id"], bool(k["passed"])) for k in suite["criteria"]]
    all_agree = all(c["agree"] for c in comparisons) and suite_identical
    return {
        "schema_version": REPLAY_SCHEMA_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "claim_boundary": REPLAY_CLAIM_BOUNDARY,
        "primary_schema_version": primary["schema_version"],
        "primary_file_sha256": primary_sha256,
        "primary_status": primary.get("status"),
        "cases": evaluations,
        "suite": suite,
        "primary_replay_agreement": {"all_agree": all_agree, "suite_criteria_identical": suite_identical, "cases": comparisons},
        "status": "PASS" if suite["status"] == "PASS" and all_agree else "FAIL",
    }


def _reject_non_standard(constant: str):
    raise ReplayValidationError(f"non-standard JSON constant {constant!r} rejected")


def load_primary(path: Path) -> tuple[dict, str]:
    raw = path.read_bytes()
    digest = "sha256:" + hashlib.sha256(raw).hexdigest()
    try:
        primary = json.loads(raw.decode("utf-8"), parse_constant=_reject_non_standard)
    except json.JSONDecodeError as exc:
        raise ReplayValidationError(f"primary is not valid JSON: {exc}") from exc
    return primary, digest


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="stdlib-only replay of the V1 actuated energy suite")
    parser.add_argument("primary", type=Path)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)
    primary, digest = load_primary(args.primary)
    receipt = replay_actuated_suite(primary, digest)
    if args.output is not None:
        args.output.write_text(json.dumps(receipt, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({"status": receipt["status"], "primary_status": receipt["primary_status"],
                      "all_agree": receipt["primary_replay_agreement"]["all_agree"],
                      "cases": [{"case_id": c["case_id"], "status": c["status"], "failed": [k["id"] for k in c["criteria"] if not k["passed"]]} for c in receipt["cases"]],
                      "comparisons": receipt["primary_replay_agreement"]["cases"]}, indent=2, allow_nan=False))
    return 0 if receipt["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())

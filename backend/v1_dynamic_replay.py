"""Stdlib-only replay for the frozen V1 dynamic reference suite.

No MuJoCo, no NumPy, no project imports.  The replay validates the primary result's
schema and frozen contract, then recomputes every scientific metric from the
serialized raw traces and compiled-model receipts (period from zero crossings and the
AGM elliptic integral, energies from body kinematics, damping work by trapezoid,
sphere/box inertia from the MJCF geometry) and compares with the primary metrics.
Primary metrics are comparison receipts, never replay inputs.

    python -I -S backend/v1_dynamic_replay.py PRIMARY_RESULT.json
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sys

PRIMARY_SCHEMA_VERSION = "V1_DYNAMIC_REFERENCE_SUITE_V1"
REPLAY_SCHEMA_VERSION = "V1_DYNAMIC_REPLAY_RECEIPT_V1"
REPLAY_CLAIM_BOUNDARY = (
    "SIM_ONLY_MUJOCO / NOT_PHYSICALLY_VALIDATED. This stdlib-only process replay "
    "recomputes the pendulum period against the closed form, energy fluctuation and "
    "drift, articulated energy balance including damping work, engine energy agreement "
    "and sphere/box inertia agreement from serialized evidence. Body masses, compiled "
    "inertias and kinematics remain MuJoCo receipts; this is not physical validation "
    "and does not make V1 PASS."
)

# 與 primary 的 DYNAMIC_SUITE_CONTRACT 逐字相同的凍結常數；漂移即 ReplayValidationError。
FROZEN_CONTRACT_ID = "v1_dynamic_reference_suite_v1"
FROZEN_TOLERANCES = {
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
}
FROZEN_CASE_IDS = (
    "known_pendulum_4ms", "known_pendulum_2ms", "known_pendulum_1ms",
    "articulated_passive_swing_4ms", "articulated_passive_swing_2ms", "articulated_passive_swing_1ms",
)
FROZEN_PENDULUM = {"mass_kg": 2.0, "radius_m": 0.05, "length_m": 0.5, "pivot_z_m": 1.5,
                   "theta0_rad": math.pi / 3.0, "duration_s": 6.0, "min_period_count": 3}
FROZEN_ARTICULATED_DURATION_S = 3.0
FROZEN_GRAVITY = 9.81
SAMPLE_KEYS = ("time_s", "qpos", "qvel", "energy_engine", "ncon", "qfrc_applied_abs_max", "xfrc_applied_abs_max", "bodies")
BODY_KEYS = ("xpos", "xipos", "ximat", "angvel_world", "linvel_com_world")


class ReplayValidationError(RuntimeError):
    pass


# ---------------------------------------------------------------- 驗證

def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ReplayValidationError(message)


def _finite_tree(value) -> bool:
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return True
    if isinstance(value, (int, float)):
        return math.isfinite(float(value))
    if isinstance(value, dict):
        return all(_finite_tree(v) for v in value.values())
    if isinstance(value, list):
        return all(_finite_tree(v) for v in value)
    return False


def validate_primary(primary: dict) -> None:
    _require(isinstance(primary, dict), "primary result must be an object")
    _require(primary.get("schema_version") == PRIMARY_SCHEMA_VERSION, "primary schema_version mismatch")
    contract = primary.get("contract")
    _require(isinstance(contract, dict), "contract missing")
    _require(contract.get("contract_id") == FROZEN_CONTRACT_ID, "contract_id drift")
    _require(contract.get("tolerances") == FROZEN_TOLERANCES, "tolerances drift against the frozen replay copy")
    _require(contract.get("gravity_mps2") == FROZEN_GRAVITY, "gravity drift")
    pend = contract.get("pendulum", {})
    for key, value in FROZEN_PENDULUM.items():
        _require(pend.get(key) == value, f"pendulum contract drift: {key}")
    _require(contract.get("articulated", {}).get("duration_s") == FROZEN_ARTICULATED_DURATION_S, "articulated duration drift")
    cases = primary.get("cases")
    _require(isinstance(cases, list) and [c.get("case_id") for c in cases] == list(FROZEN_CASE_IDS), "case inventory drift")
    for case in cases:
        for key in ("family", "physics_dt_s", "expected_sample_count", "compiled_model", "raw_trace", "metrics", "criteria", "spec"):
            _require(key in case, f"{case.get('case_id')}: missing {key}")
        trace = case["raw_trace"]
        _require(isinstance(trace, list) and len(trace) == case["expected_sample_count"],
                 f"{case['case_id']}: raw_trace length {len(trace) if isinstance(trace, list) else 'n/a'} != {case['expected_sample_count']}")
        nbody = case["compiled_model"]["nbody"] - 1
        nq, nv = case["compiled_model"]["nq"], case["compiled_model"]["nv"]
        for sample in trace:
            for key in SAMPLE_KEYS:
                _require(key in sample, f"{case['case_id']}: sample missing {key}")
            _require(len(sample["qpos"]) == nq and len(sample["qvel"]) == nv, f"{case['case_id']}: qpos/qvel shape")
            _require(len(sample["bodies"]) == nbody, f"{case['case_id']}: body count")
            for body in sample["bodies"]:
                for key in BODY_KEYS:
                    _require(key in body, f"{case['case_id']}: body sample missing {key}")
                _require(len(body["ximat"]) == 9 and len(body["xpos"]) == 3 and len(body["xipos"]) == 3
                         and len(body["angvel_world"]) == 3 and len(body["linvel_com_world"]) == 3, f"{case['case_id']}: body shape")
        _require(_finite_tree(trace), f"{case['case_id']}: non-finite raw value")
        _require(_finite_tree(case["compiled_model"]), f"{case['case_id']}: non-finite compiled model value")


# ---------------------------------------------------------------- 純 Python 的重算（與 primary 同樣的算式）

def complete_elliptic_integral_first_kind(k: float) -> float:
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


def _criterion(criterion_id: str, value, operator: str, limit, unit: str) -> dict:
    if operator == "<=":
        passed = float(value) <= float(limit)
    elif operator == ">=":
        passed = float(value) >= float(limit)
    elif operator == "==":
        passed = value == limit
    else:
        raise ReplayValidationError(f"unsupported operator {operator}")
    return {"id": criterion_id, "passed": bool(passed), "value": value, "operator": operator, "limit": limit, "unit": unit}


def body_kinetic_energy(sample_body: dict, body_receipt: dict) -> float:
    m = body_receipt["mass_kg"]
    inertia = body_receipt["inertia_principal_kgm2"]
    w = sample_body["angvel_world"]
    v_com = sample_body["linvel_com_world"]     # mjOBJ_BODY 速度的參考點就是質心
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


def upward_zero_crossings(times, theta):
    out = []
    for i in range(1, len(theta)):
        if theta[i - 1] < 0.0 <= theta[i]:
            frac = -theta[i - 1] / (theta[i] - theta[i - 1])
            out.append(times[i - 1] + frac * (times[i] - times[i - 1]))
    return out


def _sym3_eigenvalues(matrix):
    a = [row[:] for row in matrix]
    for _ in range(100):
        off = abs(a[0][1]) + abs(a[0][2]) + abs(a[1][2])
        if off < 1e-300:
            break
        for p, q in ((0, 1), (0, 2), (1, 2)):
            if abs(a[p][q]) < 1e-300:
                continue
            theta = 0.5 * math.atan2(2.0 * a[p][q], a[q][q] - a[p][p])
            c, s = math.cos(theta), math.sin(theta)
            for k in range(3):
                akp, akq = a[k][p], a[k][q]
                a[k][p], a[k][q] = c * akp - s * akq, s * akp + c * akq
            for k in range(3):
                apk, aqk = a[p][k], a[q][k]
                a[p][k], a[q][k] = c * apk - s * aqk, s * apk + c * aqk
    return sorted([a[0][0], a[1][1], a[2][2]])


def analytic_body_inertia(geoms):
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


def _common_criteria(case, contract, ke_replay, pe_replay):
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
    model_ok = (compiled["integrator"] == contract["integrator"]
                and compiled["gravity_mps2"] == [0.0, 0.0, -contract["gravity_mps2"]]
                and compiled["nu"] == 0 and compiled["energy_flag_enabled"] is True)
    joints = compiled["joints"]
    if case["family"] == "articulated":
        a = contract["articulated"]
        model_ok = model_ok and len(joints) == a["expected_joint_count"] and all(
            abs(j["damping"] - (a["expected_arm_damping"] if j["name"].startswith(("shoulder", "elbow"))
                                else a["expected_leg_damping"])) <= 1e-12 for j in joints)
    else:
        model_ok = model_ok and len(joints) == 1 and joints[0]["damping"] == 0.0 and joints[0]["armature"] == 0.0
    return [
        _criterion("FINITE_RAW_VALUES", _finite_tree(trace), "==", True, "bool"),
        _criterion("TRACE_STEP_COUNT", len(trace), "==", case["expected_sample_count"], "samples"),
        _criterion("TRACE_TIME_GRID", grid_err, "<=", tol["time_grid_error_max_s"], "s"),
        _criterion("COMPILED_TIMESTEP_IDENTITY", compiled["timestep_s"], "==", dt, "s"),
        _criterion("COMPILED_MODEL_CONTRACT", model_ok, "==", True, "bool"),
        _criterion("EXTERNAL_FORCE_ABSENT", max(max(s["qfrc_applied_abs_max"], s["xfrc_applied_abs_max"]) for s in trace), "<=", 0.0, "N or N·m"),
        _criterion("NO_CONTACT", max(s["ncon"] for s in trace), "<=", 0, "contacts"),
        _criterion("ENGINE_KINETIC_ENERGY_AGREEMENT", ke_diff, "<=", tol["engine_energy_agreement_relative_max"], "relative"),
        _criterion("ENGINE_POTENTIAL_ENERGY_AGREEMENT", pe_diff, "<=", tol["engine_energy_agreement_relative_max"], "relative"),
    ]


def evaluate_pendulum_case(case, contract):
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
        "closed_form": closed, "period_measured_s": period_meas, "period_count": period_count,
        "period_relative_error": period_rel_err, "energy_relative_fluctuation_max": fluctuation,
        "energy_secular_drift_relative": drift, "zero_crossings_s": crossings,
        "engine_ke_agreement_relative": criteria[7]["value"], "engine_pe_agreement_relative": criteria[8]["value"],
        "compiled_inertia_relative_error": inertia_rel, "compiled_ipos_abs_error_m": ipos_err,
    }
    return {"metrics": metrics, "criteria": criteria, "status": "PASS" if all(c["passed"] for c in criteria) else "FAIL"}


def evaluate_articulated_case(case, contract):
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
    power = [sum(d * s["qvel"][adr] ** 2 for adr, d in hinge_dofs) for s in trace]
    work = [0.0]
    for i in range(1, len(trace)):
        work.append(work[-1] + 0.5 * (power[i - 1] + power[i]) * (times[i] - times[i - 1]))
    e0 = ke_replay[0] + pe_replay[0]
    residual = [ke + pe + w - e0 for ke, pe, w in zip(ke_replay, pe_replay, work)]
    e_scale = e0 - min(pe_replay)
    residual_rel = max(abs(r) for r in residual) / e_scale if e_scale > 0 else float("inf")
    geoms_by_body = {}
    for gm in receipt["geoms_from_mjcf"]:
        geoms_by_body.setdefault(gm["body"], []).append(gm)
    mass_err_max = inertia_rel_max = com_err_max = 0.0
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
        "energy_initial_j": e0, "energy_scale_j": e_scale, "damping_work_final_j": work[-1],
        "kinetic_energy_max_j": max(ke_replay), "energy_balance_residual_abs_max_j": max(abs(r) for r in residual),
        "energy_balance_residual_relative_max": residual_rel,
        "engine_ke_agreement_relative": criteria[7]["value"], "engine_pe_agreement_relative": criteria[8]["value"],
        "body_mass_abs_error_max_kg": mass_err_max, "body_inertia_relative_error_max": inertia_rel_max,
        "body_com_abs_error_max_m": com_err_max, "inertia_bodies_checked": sorted(inertia_bodies_checked),
    }
    return {"metrics": metrics, "criteria": criteria, "status": "PASS" if all(c["passed"] for c in criteria) else "FAIL"}


def _observed_order(q_coarse, q_medium, q_fine, floor):
    d1, d2 = q_coarse - q_medium, q_medium - q_fine
    if abs(d1) <= floor or abs(d2) <= floor:
        return None, "ROUNDOFF_LIMITED"
    if (d1 > 0) != (d2 > 0):
        return None, "NON_MONOTONIC"
    return math.log(abs(d1) / abs(d2)) / math.log(2.0), "ESTIMATED"


def _non_dt_config(case):
    cfg = {k: v for k, v in case["compiled_model"].items() if k not in ("timestep_s", "mjcf_sha256")}
    cfg["spec"] = {k: v for k, v in case["spec"].items() if k not in ("physics_dt_s", "case_id", "roles",
                                                                      "energy_fluctuation_relative_max",
                                                                      "energy_residual_relative_max")}
    return cfg


def evaluate_suite(cases, evaluations, contract):
    tol = contract["tolerances"]
    expected = [(s["case_id"], s["family"], s["physics_dt_s"]) for s in contract["case_matrix"]]
    actual = [(c["case_id"], c["family"], c["physics_dt_s"]) for c in cases]
    by_id = {c["case_id"]: (c, e) for c, e in zip(cases, evaluations)}

    def metric(case_id, key):
        return by_id[case_id][1]["metrics"][key]

    closed = pendulum_closed_form(contract)
    t4, t2, t1 = (metric(f"known_pendulum_{n}ms", "period_measured_s") for n in (4, 2, 1))
    fine_delta_rel = abs(t2 - t1) / closed["period_s"]
    period_monotone = abs(t2 - t1) <= max(abs(t4 - t2), tol["pendulum_period_roundoff_floor_s"])
    r4, r2, r1 = (metric(f"articulated_passive_swing_{n}ms", "energy_balance_residual_relative_max") for n in (4, 2, 1))
    floor = tol["articulated_residual_roundoff_floor"]
    residual_monotone = (r1 <= max(r2, floor)) and (r2 <= max(r4, floor))
    non_dt_ok = all(_non_dt_config(by_id[f"{fam}_{n}ms"][0]) == _non_dt_config(by_id[f"{fam}_4ms"][0])
                    for fam in ("known_pendulum", "articulated_passive_swing") for n in (2, 1))
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


# ---------------------------------------------------------------- primary 對 replay

def _flatten_numbers(value, prefix=""):
    if value is None:
        return {prefix: float("nan")}          # 例如「無法估計的 observed order」；與數值相比視為不一致
    if isinstance(value, bool) or isinstance(value, str):
        return {}
    if isinstance(value, (int, float)):
        return {prefix: float(value)}
    out = {}
    if isinstance(value, dict):
        for k, v in value.items():
            out.update(_flatten_numbers(v, f"{prefix}.{k}" if prefix else str(k)))
    elif isinstance(value, list):
        for i, v in enumerate(value):
            out.update(_flatten_numbers(v, f"{prefix}[{i}]"))
    return out


def compare_metrics(primary_metrics: dict, replay_metrics: dict, tol: dict) -> dict:
    a, b = _flatten_numbers(primary_metrics), _flatten_numbers(replay_metrics)
    _require(set(a) == set(b), f"metric key set differs: {sorted(set(a) ^ set(b))[:5]}")
    worst_key, worst_rel = None, 0.0
    for key in a:
        pa, pb = a[key], b[key]
        if math.isinf(pa) and math.isinf(pb) and (pa > 0) == (pb > 0):
            continue
        if math.isnan(pa) and math.isnan(pb):
            continue
        if math.isnan(pa) != math.isnan(pb):
            if worst_key is None:
                worst_key, worst_rel = key, float("inf")
            continue
        diff = abs(pa - pb)
        rel = diff / max(abs(pa), abs(pb), 1e-300)
        ok = diff <= tol["primary_replay_absolute_max"] or rel <= tol["primary_replay_relative_max"]
        if not ok and rel > worst_rel:
            worst_key, worst_rel = key, rel
    return {"agree": worst_key is None, "worst_key": worst_key, "worst_relative_difference": worst_rel, "compared": len(a)}


def replay_dynamic_suite(primary: dict) -> dict:
    validate_primary(primary)
    contract = primary["contract"]
    tol = contract["tolerances"]
    cases = primary["cases"]
    evaluations = []
    comparisons = []
    for case in cases:
        replay_case = {k: case[k] for k in ("case_id", "family", "physics_dt_s", "expected_sample_count", "compiled_model", "raw_trace", "spec")}
        evaluation = evaluate_pendulum_case(replay_case, contract) if case["family"] == "pendulum" else evaluate_articulated_case(replay_case, contract)
        evaluations.append(evaluation)
        comparison = compare_metrics(case["metrics"], evaluation["metrics"], tol)
        primary_passed = [c["passed"] for c in case["criteria"]]
        replay_passed = [c["passed"] for c in evaluation["criteria"]]
        comparison["criteria_identical"] = ([c["id"] for c in case["criteria"]] == [c["id"] for c in evaluation["criteria"]]
                                            and primary_passed == replay_passed)
        comparison["case_id"] = case["case_id"]
        comparisons.append(comparison)
    suite = evaluate_suite([{k: c[k] for k in ("case_id", "family", "physics_dt_s", "compiled_model", "spec")} for c in cases],
                           evaluations, contract)
    suite_comparison = compare_metrics(primary["suite"]["timestep_study"], suite["timestep_study"], tol)
    suite_comparison["criteria_identical"] = [c["passed"] for c in primary["suite"]["criteria"]] == [c["passed"] for c in suite["criteria"]]
    all_agree = all(c["agree"] and c["criteria_identical"] for c in comparisons) and suite_comparison["agree"] and suite_comparison["criteria_identical"]
    replay_status = "PASS" if suite["status"] == "PASS" and all(e["status"] == "PASS" for e in evaluations) else "FAIL"
    return {
        "schema_version": REPLAY_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "claim_boundary": REPLAY_CLAIM_BOUNDARY,
        "primary_schema_version": primary["schema_version"],
        "primary_contract_sha256": primary.get("contract_sha256"),
        "primary_status": primary["status"],
        "cases": [{"case_id": c["case_id"], "status": e["status"], "metrics": e["metrics"], "criteria": e["criteria"]}
                  for c, e in zip(cases, evaluations)],
        "suite": suite,
        "primary_replay_agreement": {"cases": comparisons, "suite": suite_comparison, "all_agree": all_agree},
        "status": replay_status if all_agree else "FAIL",
        "status_reason": None if all_agree else "PRIMARY_REPLAY_DISAGREEMENT",
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("primary", type=Path)
    args = parser.parse_args(argv)
    text = args.primary.read_text(encoding="utf-8")
    primary = json.loads(text, parse_constant=lambda name: (_ for _ in ()).throw(ReplayValidationError(f"non-standard JSON constant {name}")))
    receipt = replay_dynamic_suite(primary)
    receipt["primary_file_sha256"] = "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()
    for case in receipt["cases"]:
        case["metrics"].pop("zero_crossings_s", None)
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 0 if receipt["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())

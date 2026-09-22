"""Stdlib-only replay for the frozen V1 contact reference suite.

No MuJoCo, no NumPy, no project imports.  The replay validates the primary result's schema and
frozen contract, then recomputes every metric from the serialized per-step samples and the
compiled-model receipts (discrete free fall and touchdown step, impulse sums, rest statistics,
the soft-contact equilibrium penetration fixed point, the viscous slip rate and its
discrete/continuous gap, cone utilisation, Jacobian closure) and compares with the primary
metrics.  Primary metrics are comparison receipts, never replay inputs.

    python -I -S backend/v1_contact_replay.py PRIMARY_RESULT.json
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sys

PRIMARY_SCHEMA_VERSION = "V1_CONTACT_REFERENCE_SUITE_V1"
REPLAY_SCHEMA_VERSION = "V1_CONTACT_REPLAY_RECEIPT_V1"
REPLAY_CLAIM_BOUNDARY = (
    "SIM_ONLY_MUJOCO / NOT_PHYSICALLY_VALIDATED. This stdlib-only process replay recomputes the "
    "drop-and-settle, viscous-slider and Coulomb-hypothesis metrics from serialized evidence and "
    "compares them with the primary. Contact forces, kinematics and compiled parameters remain "
    "MuJoCo receipts; this is not physical validation and does not make V1 PASS."
)

# 與 primary 的 CONTACT_SUITE_CONTRACT 逐字相同的凍結常數；漂移即 ReplayValidationError。
FROZEN_CONTRACT_ID = "v1_contact_reference_suite_v1"
FROZEN_GRAVITY = 9.81
FROZEN_FRICTION = [1.0, 0.005, 0.0001]
FROZEN_SOLREF = [0.02, 1.0]
FROZEN_SOLIMP = [0.9, 0.95, 0.001, 0.5, 2.0]
FROZEN_SOLVER = {"tolerance": 1.0e-8, "iterations": 100, "impratio": 1.0, "noslip_iterations": 0}
FROZEN_DROP = {"mass_kg": 1.0, "radius_m": 0.05, "gap_m": 0.5, "duration_s": 2.0, "rest_window_s": [1.5, 2.0], "contact_count": 1}
FROZEN_SLIDER = {"mass_kg": 1.0, "half_sizes_m": [0.10, 0.10, 0.02], "settle_s": 1.0, "duration_s": 2.0,
                 "pre_rest_window_s": [0.7, 1.0], "post_rest_window_s": [1.5, 2.0],
                 "contact_count_from_s": 0.1, "contact_count": 4, "mu": 1.0, "slip_velocity_floor_relative": 1.0e-3}
FROZEN_HYPOTHESIS = {"speed_floor_mps": 0.1, "post_rest_window_s": [1.7, 2.0],
                     "normal_force_relative_max": 0.02, "deceleration_relative_max": 0.02}
FROZEN_TOLERANCES = {
    "time_grid_error_max_s": 1.0e-12,
    "frame_axis_alignment_max": 1.0e-12,
    "unilateral_normal_force_min_n": -1.0e-12,
    "friction_cone_utilisation_max": 1.0 + 1.0e-9,
    "step_velocity_update_max": 1.0e-8,
    "contact_force_closure_max_n": 1.0e-9,
    "touchdown_step_delta_max": 0,
    "free_fall_position_abs_max_m": 1.0e-10,
    "impulse_identity_relative_max": 1.0e-6,
    "impulse_weight_relative_max": 1.0e-6,
    "rest_normal_force_relative_max": 1.0e-6,
    "rest_velocity_max": 1.0e-6,
    "rest_penetration_relative_max": 1.0e-5,
    "viscous_discrete_relative_max": 1.0e-4,
    "viscous_continuous_extra_relative": 1.0e-3,
    "viscous_rate_relative_max": 1.0e-4,
    "slip_utilisation_max": 0.5,
    "slip_normal_force_relative_max": 1.0e-6,
    "tangential_impulse_relative_max": 1.0e-6,
    "rest_penetration_dt_spread_relative_max": 1.0e-5,
    "mass_abs_error_max_kg": 1.0e-12,
    "primary_replay_relative_max": 1.0e-10,
    "primary_replay_absolute_max": 1.0e-12,
}
FROZEN_CASE_IDS = (
    "drop_and_settle_4ms", "drop_and_settle_2ms", "drop_and_settle_1ms",
    "viscous_slider_4ms", "viscous_slider_2ms", "viscous_slider_1ms",
    "coulomb_hypothesis_slider_2ms",
)
FROZEN_CASE_DT = (0.004, 0.002, 0.001, 0.004, 0.002, 0.001, 0.002)
FROZEN_CASE_GATES = (True, True, True, True, True, True, False)
FROZEN_KICKS = (None, None, None, 0.02, 0.02, 0.02, 0.5)
SAMPLE_KEYS = ("time_s", "qpos", "qvel", "qacc", "ncon", "qfrc_constraint", "qfrc_applied_abs_max", "xfrc_applied_abs_max", "contacts")
CONTACT_KEYS = ("geom1", "geom2", "dim", "dist", "pos", "frame", "force_contact_frame")
COMMON_IDS = (
    "FINITE_RAW_VALUES", "TRACE_STEP_COUNT", "TRACE_TIME_GRID", "COMPILED_TIMESTEP_IDENTITY",
    "COMPILED_MODEL_CONTRACT", "EXTERNAL_FORCE_ABSENT", "CONTACT_FRAME_AXIS_ALIGNED",
    "UNILATERAL_NORMAL_FORCE", "FRICTION_CONE_RESPECTED", "STEP_VELOCITY_UPDATE_IDENTITY",
    "CONTACT_FORCE_WORLD_SUM_MATCHES_QFRC_CONSTRAINT",
)


class ReplayValidationError(RuntimeError):
    pass


# ---------------------------------------------------------------- 驗證

def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ReplayValidationError(message)


def _finite_tree(value) -> bool:
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return True
    if isinstance(value, int):
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
    _require(contract.get("friction") == FROZEN_FRICTION and contract.get("solref") == FROZEN_SOLREF
             and contract.get("solimp") == FROZEN_SOLIMP and contract.get("solver") == FROZEN_SOLVER, "contact parameter drift")
    _require(contract.get("drop") == FROZEN_DROP and contract.get("slider") == FROZEN_SLIDER
             and contract.get("hypothesis") == FROZEN_HYPOTHESIS, "case definition drift")
    matrix = contract.get("case_matrix")
    _require(isinstance(matrix, list) and [s.get("case_id") for s in matrix] == list(FROZEN_CASE_IDS), "case matrix drift")
    _require([s.get("physics_dt_s") for s in matrix] == list(FROZEN_CASE_DT), "case dt drift")
    _require([bool(s.get("gates_suite")) for s in matrix] == list(FROZEN_CASE_GATES), "gates_suite drift")
    _require([s.get("kick_velocity_mps") for s in matrix] == list(FROZEN_KICKS), "kick velocity drift")
    cases = primary.get("cases")
    _require(isinstance(cases, list) and [c.get("case_id") for c in cases] == list(FROZEN_CASE_IDS), "case inventory drift")
    for case, dt in zip(cases, FROZEN_CASE_DT):
        _require(case.get("physics_dt_s") == dt, f"{case.get('case_id')}: dt drift")
        _require(isinstance(case.get("compiled_model"), dict) and isinstance(case.get("raw_trace"), list), f"{case.get('case_id')}: raw_trace or compiled_model missing")
        _require(isinstance(case.get("criteria"), list) and all(isinstance(k, dict) and "id" in k and "passed" in k for k in case["criteria"]), f"{case.get('case_id')}: criteria malformed")
        _require(isinstance(case.get("hypotheses"), list), f"{case.get('case_id')}: hypotheses missing")
        _require(isinstance(case.get("metrics"), dict), f"{case.get('case_id')}: metrics missing")
        cm = case["compiled_model"]
        for key in ("timestep_s", "integrator", "cone", "gravity", "nu", "nv", "nq", "body_mass", "geoms", "joints",
                    "solver_tolerance", "solver_iterations", "impratio", "noslip_iterations"):
            _require(key in cm, f"{case['case_id']}: compiled_model.{key} missing")
        nq, nv = int(cm["nq"]), int(cm["nv"])
        _require(len(case["raw_trace"]) == case.get("expected_sample_count"), f"{case['case_id']}: sample count mismatch")
        if case["family"] == "slider":
            _require(isinstance(case.get("kick_step"), int) and 0 < case["kick_step"] < len(case["raw_trace"]), f"{case['case_id']}: kick_step invalid")
        else:
            _require(case.get("kick_step") is None, f"{case['case_id']}: drop case has kick_step")
        for i, sample in enumerate(case["raw_trace"]):
            _require(isinstance(sample, dict) and all(k in sample for k in SAMPLE_KEYS), f"{case['case_id']}[{i}]: sample keys")
            _require(isinstance(sample["time_s"], (int, float)) and math.isfinite(sample["time_s"]), f"{case['case_id']}[{i}]: time")
            _require(_is_num_list(sample["qpos"], nq) and _is_num_list(sample["qvel"], nv) and _is_num_list(sample["qacc"], nv)
                     and _is_num_list(sample["qfrc_constraint"], nv), f"{case['case_id']}[{i}]: state shape")
            _require(isinstance(sample["ncon"], int) and sample["ncon"] == len(sample["contacts"]), f"{case['case_id']}[{i}]: ncon")
            _require(_is_num_list([sample["qfrc_applied_abs_max"], sample["xfrc_applied_abs_max"]]), f"{case['case_id']}[{i}]: applied force fields")
            for c in sample["contacts"]:
                _require(isinstance(c, dict) and all(k in c for k in CONTACT_KEYS), f"{case['case_id']}[{i}]: contact keys")
                _require(_is_num_list(c["pos"], 3) and _is_num_list(c["frame"], 9) and _is_num_list(c["force_contact_frame"], 6)
                         and isinstance(c["dist"], (int, float)) and math.isfinite(c["dist"]), f"{case['case_id']}[{i}]: contact shape")
    suite = primary.get("suite")
    _require(isinstance(suite, dict) and isinstance(suite.get("criteria"), list), "suite block missing")


# ---------------------------------------------------------------- 閉式（與 primary 逐字對應）

def impedance(pen: float, solimp) -> float:
    dmin, dmax, width, mid, power = [float(x) for x in solimp]
    x = min(abs(pen) / width, 1.0)
    if x <= mid:
        y = (x ** power) / (mid ** (power - 1.0))
    else:
        y = 1.0 - ((1.0 - x) ** power) / ((1.0 - mid) ** (power - 1.0))
    return dmin + (dmax - dmin) * y


def constraint_stiffness(solref, solimp) -> float:
    tc, zeta = float(solref[0]), float(solref[1])
    return 1.0 / (float(solimp[1]) ** 2 * tc ** 2 * zeta ** 2)


def constraint_damping(solref, solimp) -> float:
    return 2.0 / (float(solimp[1]) * float(solref[0]))


def equilibrium_penetration(n_contacts: int, gravity: float, solref, solimp, iterations: int = 400) -> float:
    k = constraint_stiffness(solref, solimp)
    pen = 0.0
    for _ in range(iterations):
        d = impedance(pen, solimp)
        pen = 0.5 * pen + 0.5 * (1.0 - d) * gravity / (n_contacts * d * d * k)
    return pen


def viscous_slip_rate(n_contacts: int, d: float, solref, solimp) -> float:
    b = constraint_damping(solref, solimp)
    return b * n_contacts * d / (n_contacts * d + 2.0 * (1.0 - d))


def discrete_continuous_gap(x: float, k_max: int) -> float:
    return max(abs((1.0 - x) ** k - math.exp(-k * x)) for k in range(1, k_max + 1))


def closed_forms(contract: dict) -> dict:
    g = contract["gravity_mps2"]
    drop, slider = contract["drop"], contract["slider"]
    pen_drop = equilibrium_penetration(drop["contact_count"], g, contract["solref"], contract["solimp"])
    pen_slider = equilibrium_penetration(slider["contact_count"], g, contract["solref"], contract["solimp"])
    d_slider = impedance(pen_slider, contract["solimp"])
    rho = viscous_slip_rate(slider["contact_count"], d_slider, contract["solref"], contract["solimp"])
    return {
        "stiffness_k": constraint_stiffness(contract["solref"], contract["solimp"]),
        "damping_b": constraint_damping(contract["solref"], contract["solimp"]),
        "touchdown_time_continuous_s": math.sqrt(2.0 * drop["gap_m"] / g),
        "rest_penetration_drop_m": pen_drop,
        "rest_penetration_slider_m": pen_slider,
        "slider_rest_impedance": d_slider,
        "viscous_slip_rate_per_s": rho,
        "saturation_speed_mps": slider["mu"] * g / rho,
    }


def discrete_touchdown_step(gap: float, gravity: float, dt: float) -> int:
    n = 1
    while gravity * dt * dt * n * (n + 1) / 2.0 <= gap:
        n += 1
        if n > 10_000_000:
            raise ReplayValidationError("discrete touchdown search did not terminate")
    return n


# ---------------------------------------------------------------- 純 Python 重算

def _criterion(criterion_id: str, value, operator: str, limit, unit: str, role: str = "gate") -> dict:
    ops = {"<=": lambda a, b: a <= b, ">=": lambda a, b: a >= b, "==": lambda a, b: a == b, "<": lambda a, b: a < b}
    finite = value is not None and (not isinstance(value, float) or math.isfinite(value))
    passed = bool(finite and ops[operator](value, limit))
    return {"id": criterion_id, "value": value, "operator": operator, "limit": limit, "unit": unit, "role": role, "passed": passed}


def contact_world_force(contact: dict) -> list[float]:
    fr = [float(x) for x in contact["frame"]]
    f = [float(x) for x in contact["force_contact_frame"][:3]]
    # rows of the frame are normal, tangent1, tangent2; world force = Σ_row f_row · row
    return [f[0] * fr[0] + f[1] * fr[3] + f[2] * fr[6],
            f[0] * fr[1] + f[1] * fr[4] + f[2] * fr[7],
            f[0] * fr[2] + f[1] * fr[5] + f[2] * fr[8]]


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


def _translational_dof_axes(case: dict) -> list[tuple[int, int]]:
    pairs = []
    for j in case["compiled_model"]["joints"]:
        if j["type"] == "mjJNT_FREE":
            pairs.extend((int(j["dofadr"]) + a, a) for a in range(3))
        elif j["type"] == "mjJNT_SLIDE":
            axis = max(range(3), key=lambda i: abs(float(j["axis"][i])))
            pairs.append((int(j["dofadr"]), axis))
    return pairs


def _world_sum(sample: dict) -> list[float]:
    total = [0.0, 0.0, 0.0]
    for c in sample["contacts"]:
        w = contact_world_force(c)
        for i in range(3):
            total[i] += w[i]
    return total


def common_metrics(case: dict, contract: dict) -> dict:
    trace = case["raw_trace"]
    dt = float(case["physics_dt_s"])
    mu = float(contract["friction"][0])
    grid_err = max(abs(float(s["time_s"]) - dt * n) for n, s in enumerate(trace))
    ext = max(max(float(s["qfrc_applied_abs_max"]), float(s["xfrc_applied_abs_max"])) for s in trace)
    axis_err = 0.0
    fn_min = math.inf
    util_max = 0.0
    closure = 0.0
    pairs = _translational_dof_axes(case)
    for s in trace:
        world = _world_sum(s)
        for c in s["contacts"]:
            axis_err = max(axis_err, _axis_alignment_error([float(x) for x in c["frame"]]))
            f = c["force_contact_frame"]
            fn_min = min(fn_min, float(f[0]))
            tangential = math.hypot(float(f[1]), float(f[2]))
            if f[0] > 0.0:
                util_max = max(util_max, tangential / (mu * float(f[0])))
            elif tangential > 0.0:
                util_max = math.inf
        for dof, axis in pairs:
            closure = max(closure, abs(world[axis] - float(s["qfrc_constraint"][dof])))
    if not math.isfinite(fn_min):
        fn_min = 0.0
    vel_update = 0.0
    kick = case.get("kick_step")
    for n in range(len(trace) - 1):
        if kick is not None and n + 1 == kick:
            continue
        v0, v1, a0 = trace[n]["qvel"], trace[n + 1]["qvel"], trace[n]["qacc"]
        vel_update = max(vel_update, max(abs(float(v1[i]) - float(v0[i]) - dt * float(a0[i])) for i in range(len(v0))))
    return {
        "time_grid_error_max_s": grid_err,
        "external_force_abs_max": ext,
        "frame_axis_alignment_error_max": axis_err,
        "normal_force_min_n": fn_min,
        "friction_cone_utilisation_max": util_max,
        "step_velocity_update_error_max": vel_update,
        "contact_force_closure_error_max_n": closure,
    }


def _model_contract_ok(case: dict, contract: dict) -> bool:
    cm = case["compiled_model"]
    if cm["integrator"] != contract["integrator"] or cm["cone"] != contract["cone"]:
        return False
    if [float(x) for x in cm["gravity"]] != [0.0, 0.0, -float(contract["gravity_mps2"])] or int(cm["nu"]) != 0:
        return False
    sol = contract["solver"]
    if cm["solver_tolerance"] != sol["tolerance"] or cm["solver_iterations"] != sol["iterations"] \
            or cm["impratio"] != sol["impratio"] or cm["noslip_iterations"] != sol["noslip_iterations"]:
        return False
    names = {g["name"] for g in cm["geoms"]}
    if names != ({"floor", "ball"} if case["family"] == "drop" else {"floor", "slider"}):
        return False
    for g in cm["geoms"]:
        if g["friction"] != contract["friction"] or g["condim"] != contract["condim"] or g["solref"] != contract["solref"] \
                or g["solimp"] != contract["solimp"] or g["margin"] != contract["margin_m"]:
            return False
        if g["name"] == "floor" and (g["contype"], g["conaffinity"]) != (2, 1):
            return False
        if g["name"] != "floor" and (g["contype"], g["conaffinity"]) != (1, 2):
            return False
    body = "ball" if case["family"] == "drop" else "slider"
    if body not in cm["body_mass"] or abs(float(cm["body_mass"][body]) - contract[case["family"]]["mass_kg"]) > contract["tolerances"]["mass_abs_error_max_kg"]:
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
        _criterion("CONTACT_FRAME_AXIS_ALIGNED", metrics["frame_axis_alignment_error_max"], "<=", tol["frame_axis_alignment_max"], "unit vector"),
        _criterion("UNILATERAL_NORMAL_FORCE", metrics["normal_force_min_n"], ">=", tol["unilateral_normal_force_min_n"], "N"),
        _criterion("FRICTION_CONE_RESPECTED", metrics["friction_cone_utilisation_max"], "<=", tol["friction_cone_utilisation_max"], "ratio"),
        _criterion("STEP_VELOCITY_UPDATE_IDENTITY", metrics["step_velocity_update_error_max"], "<=", tol["step_velocity_update_max"], "m/s or rad/s"),
        _criterion("CONTACT_FORCE_WORLD_SUM_MATCHES_QFRC_CONSTRAINT", metrics["contact_force_closure_error_max_n"], "<=", tol["contact_force_closure_max_n"], "N"),
    ]


def _window_indices(trace: list[dict], window, dt: float) -> list[int]:
    lo, hi = float(window[0]), float(window[1])
    return [n for n, s in enumerate(trace) if float(s["time_s"]) >= lo - 1e-9 * dt and float(s["time_s"]) <= hi + 1e-9 * dt]


def _median(values: list[float]) -> float:
    v = sorted(values)
    n = len(v)
    return v[n // 2] if n % 2 else 0.5 * (v[n // 2 - 1] + v[n // 2])


def evaluate_drop_case(case: dict, contract: dict) -> dict:
    tol = contract["tolerances"]
    drop = contract["drop"]
    g = float(contract["gravity_mps2"])
    m, r, gap, dt = float(drop["mass_kg"]), float(drop["radius_m"]), float(drop["gap_m"]), float(case["physics_dt_s"])
    trace = case["raw_trace"]
    metrics = common_metrics(case, contract)
    forms = closed_forms(contract)
    n_samples = len(trace)
    total_t = dt * (n_samples - 1)
    touchdown = next((n for n, s in enumerate(trace) if s["ncon"] > 0), None)
    n_star = discrete_touchdown_step(gap, g, dt)
    z0 = r + gap
    pre = touchdown if touchdown is not None else n_samples
    free_fall_err = max((abs(float(trace[n]["qpos"][2]) - (z0 - g * dt * dt * n * (n + 1.0) / 2.0)) for n in range(pre)), default=0.0)
    fz = [_world_sum(s)[2] for s in trace]
    impulse = 0.0
    for n in range(n_samples - 1):
        impulse += fz[n]
    impulse *= dt
    vz0, vzN = float(trace[0]["qvel"][2]), float(trace[-1]["qvel"][2])
    weight_integral = m * g * total_t
    identity_res = abs(impulse - m * (vzN - vz0) - weight_integral) / weight_integral
    weight_err = abs(impulse - weight_integral) / weight_integral
    rest = _window_indices(trace, drop["rest_window_s"], dt)
    rest_force_err = max(abs(fz[n] - m * g) for n in rest) / (m * g)
    rest_vel = max(max(abs(float(x)) for x in trace[n]["qvel"]) for n in rest)
    pen_rest = r - float(trace[rest[-1]]["qpos"][2])
    pen_star = forms["rest_penetration_drop_m"]
    pen_err = abs(pen_rest - pen_star) / pen_star
    ncon = [s["ncon"] for s in trace]
    separations = 0
    if touchdown is not None:
        separations = sum(1 for n in range(touchdown + 1, n_samples) if ncon[n] == 0 and ncon[n - 1] > 0)
    metrics.update({
        "touchdown_step": touchdown, "touchdown_step_closed": n_star,
        "touchdown_step_delta": (None if touchdown is None else abs(touchdown - n_star)),
        "touchdown_time_s": (None if touchdown is None else touchdown * dt),
        "touchdown_time_continuous_s": forms["touchdown_time_continuous_s"],
        "touchdown_time_error_s": (None if touchdown is None else abs(touchdown * dt - forms["touchdown_time_continuous_s"])),
        "free_fall_position_error_max_m": free_fall_err,
        "normal_impulse_ns": impulse, "weight_integral_ns": weight_integral,
        "impulse_identity_relative_error": identity_res, "impulse_weight_relative_error": weight_err,
        "rest_normal_force_relative_error_max": rest_force_err, "rest_velocity_max": rest_vel,
        "rest_penetration_m": pen_rest, "rest_penetration_closed_m": pen_star, "rest_penetration_relative_error": pen_err,
        "max_penetration_m": max(max(0.0, r - float(s["qpos"][2])) for s in trace), "peak_normal_force_n": max(fz),
        "separation_events_after_touchdown": separations,
        "sample_count": n_samples,
    })
    criteria = _common_criteria(case, contract, metrics) + [
        _criterion("TOUCHDOWN_STEP_MATCHES_DISCRETE_FREE_FALL", metrics["touchdown_step_delta"], "<=", tol["touchdown_step_delta_max"], "steps"),
        _criterion("TOUCHDOWN_TIME_VS_CONTINUOUS_CLOSED_FORM", metrics["touchdown_time_error_s"], "<=", dt, "s"),
        _criterion("FREE_FALL_POSITION_DISCRETE_EXACT", free_fall_err, "<=", tol["free_fall_position_abs_max_m"], "m"),
        _criterion("NORMAL_IMPULSE_MOMENTUM_IDENTITY", identity_res, "<=", tol["impulse_identity_relative_max"], "relative"),
        _criterion("NORMAL_IMPULSE_VS_WEIGHT_INTEGRAL", weight_err, "<=", tol["impulse_weight_relative_max"], "relative"),
        _criterion("REST_NORMAL_FORCE_VS_WEIGHT", rest_force_err, "<=", tol["rest_normal_force_relative_max"], "relative"),
        _criterion("REST_VELOCITY", rest_vel, "<=", tol["rest_velocity_max"], "m/s or rad/s"),
        _criterion("REST_PENETRATION_VS_CLOSED_FORM", pen_err, "<=", tol["rest_penetration_relative_max"], "relative"),
    ]
    return {"case_id": case["case_id"], "family": "drop", "physics_dt_s": dt, "gates_suite": case["gates_suite"],
            "status": "PASS" if all(c["passed"] for c in criteria) else "FAIL", "criteria": criteria, "hypotheses": [], "metrics": metrics}


def evaluate_slider_case(case: dict, contract: dict) -> dict:
    tol = contract["tolerances"]
    sl = contract["slider"]
    hyp = contract["hypothesis"]
    g = float(contract["gravity_mps2"])
    mu = float(sl["mu"])
    m, dt = float(sl["mass_kg"]), float(case["physics_dt_s"])
    trace = case["raw_trace"]
    metrics = common_metrics(case, contract)
    forms = closed_forms(contract)
    n_samples = len(trace)
    kick = int(case["kick_step"])
    v0 = float(case["spec"]["kick_velocity_mps"])
    is_hyp = bool(case["spec"].get("hypothesis"))
    world = [_world_sum(s) for s in trace]
    fz = [w[2] for w in world]
    fx = [w[0] for w in world]
    vx = [float(s["qvel"][0]) for s in trace]
    x = [float(s["qpos"][0]) for s in trace]
    pen = [-float(s["qpos"][1]) for s in trace]
    ncon = [s["ncon"] for s in trace]
    pre = [n for n in _window_indices(trace, sl["pre_rest_window_s"], dt) if n < kick]
    pre_force_err = max(abs(fz[n] - m * g) for n in pre) / (m * g)
    pen_star = forms["rest_penetration_slider_m"]
    pre_pen = pen[kick - 1]
    pre_pen_err = abs(pre_pen - pen_star) / pen_star
    floor_v = float(hyp["speed_floor_mps"]) if is_hyp else float(sl["slip_velocity_floor_relative"]) * v0
    slip = []
    for n in range(kick, n_samples):
        if vx[n] >= floor_v:
            slip.append(n)
        else:
            break
    util_slip = 0.0
    for n in slip:
        for c in trace[n]["contacts"]:
            f = c["force_contact_frame"]
            if f[0] > 0.0:
                util_slip = max(util_slip, math.hypot(float(f[1]), float(f[2])) / (mu * float(f[0])))
    slip_force_err = max(abs(fz[n] - m * g) for n in slip) / (m * g) if slip else math.inf
    contact_ok_from = _window_indices(trace, [sl["contact_count_from_s"], case["duration_s"]], dt)
    contact_count_ok = all(ncon[n] == sl["contact_count"] for n in contact_ok_from)
    tangential_impulse = 0.0
    for n in range(kick, n_samples - 1):
        tangential_impulse += fx[n]
    tangential_impulse *= dt
    tangential_identity = abs(tangential_impulse - m * (vx[-1] - v0)) / (m * v0)
    post_window = hyp["post_rest_window_s"] if is_hyp else sl["post_rest_window_s"]
    post = _window_indices(trace, post_window, dt)
    post_force_err = max(abs(fz[n] - m * g) for n in post) / (m * g)
    post_vel = max(max(abs(float(v)) for v in trace[n]["qvel"]) for n in post)
    post_pen = pen[post[-1]]
    post_pen_err = abs(post_pen - pen_star) / pen_star
    metrics.update({
        "kick_step": kick, "kick_velocity_mps": v0, "slip_window_samples": len(slip),
        "pre_rest_normal_force_relative_error_max": pre_force_err,
        "pre_rest_penetration_m": pre_pen, "rest_penetration_closed_m": pen_star,
        "pre_rest_penetration_relative_error": pre_pen_err,
        "slip_utilisation_max": util_slip, "slip_normal_force_relative_error_max": slip_force_err,
        "contact_count_constant": 1 if contact_count_ok else 0,
        "tangential_impulse_ns": tangential_impulse, "tangential_impulse_relative_error": tangential_identity,
        "post_rest_normal_force_relative_error_max": post_force_err, "post_rest_velocity_max": post_vel,
        "post_rest_penetration_m": post_pen, "post_rest_penetration_relative_error": post_pen_err,
        "slide_distance_m": x[-1] - x[kick], "normal_force_inflation_max_ratio": max(fz[kick:]) / (m * g),
        "lost_contact_samples_after_kick": sum(1 for n in range(kick, n_samples) if ncon[n] < sl["contact_count"]),
        "sample_count": n_samples,
    })
    criteria = _common_criteria(case, contract, metrics) + [
        _criterion("PRE_KICK_REST_NORMAL_FORCE_VS_WEIGHT", pre_force_err, "<=", tol["rest_normal_force_relative_max"], "relative"),
        _criterion("PRE_KICK_REST_PENETRATION_VS_CLOSED_FORM", pre_pen_err, "<=", tol["rest_penetration_relative_max"], "relative"),
        _criterion("TANGENTIAL_IMPULSE_IDENTITY", tangential_identity, "<=", tol["tangential_impulse_relative_max"], "relative"),
        _criterion("POST_REST_NORMAL_FORCE_VS_WEIGHT", post_force_err, "<=", tol["rest_normal_force_relative_max"], "relative"),
        _criterion("POST_REST_VELOCITY", post_vel, "<=", tol["rest_velocity_max"], "m/s"),
        _criterion("POST_REST_PENETRATION_VS_CLOSED_FORM", post_pen_err, "<=", tol["rest_penetration_relative_max"], "relative"),
    ]
    hypotheses = []
    if is_hyp:
        slip_set = set(slip)
        decel = [(vx[n] - vx[n + 1]) / dt for n in slip if (n + 1) in slip_set]
        mean_decel = sum(decel) / len(decel) if decel else math.nan
        decel_err = abs(mean_decel - mu * g) / (mu * g) if decel else math.inf
        slide_contact_ok = all(ncon[n] == sl["contact_count"] for n in slip) if slip else False
        metrics.update({"hypothesis_mean_deceleration_mps2": mean_decel,
                        "hypothesis_deceleration_relative_error": decel_err,
                        "hypothesis_slide_contact_count_constant": 1 if slide_contact_ok else 0})
        hypotheses = [
            _criterion("H1_CONTACT_COUNT_CONSTANT_FOUR_IN_SLIDE", metrics["hypothesis_slide_contact_count_constant"], "==", 1, "flag", role="hypothesis"),
            _criterion("H2_SLIDE_NORMAL_FORCE_VS_WEIGHT", slip_force_err, "<=", hyp["normal_force_relative_max"], "relative", role="hypothesis"),
            _criterion("H3_COULOMB_DECELERATION_VS_MU_G", decel_err, "<=", hyp["deceleration_relative_max"], "relative", role="hypothesis"),
        ]
    else:
        rho = forms["viscous_slip_rate_per_s"]
        xk = dt * rho
        geo_err = max(abs(vx[n] - v0 * (1.0 - xk) ** (n - kick)) for n in slip) / v0 if slip else math.inf
        exp_err = max(abs(vx[n] - v0 * math.exp(-rho * (n - kick) * dt)) for n in slip) / v0 if slip else math.inf
        gap_d = discrete_continuous_gap(xk, n_samples - 1 - kick)
        rates = [(vx[n] - vx[n + 1]) / (dt * vx[n]) for n in slip[:-1]]
        rate_mean = sum(rates) / len(rates) if rates else math.nan
        rate_err = abs(rate_mean - rho) / rho if rates else math.inf
        metrics.update({"viscous_rate_closed_per_s": rho, "viscous_rate_measured_mean_per_s": rate_mean,
                        "viscous_rate_relative_error": rate_err,
                        "viscous_discrete_relative_error_max": geo_err, "viscous_continuous_relative_error_max": exp_err,
                        "viscous_discrete_continuous_gap": gap_d})
        criteria += [
            _criterion("CONTACT_COUNT_CONSTANT_FOUR", metrics["contact_count_constant"], "==", 1, "flag"),
            _criterion("VISCOUS_SLIP_VS_DISCRETE_CLOSED_FORM", geo_err, "<=", tol["viscous_discrete_relative_max"], "relative to v0"),
            _criterion("VISCOUS_SLIP_VS_CONTINUOUS_CLOSED_FORM", exp_err, "<=", gap_d + tol["viscous_continuous_extra_relative"], "relative to v0"),
            _criterion("VISCOUS_SLIP_RATE_VS_CLOSED_FORM", rate_err, "<=", tol["viscous_rate_relative_max"], "relative"),
            _criterion("FRICTION_UNSATURATED_IN_SLIP", util_slip, "<", tol["slip_utilisation_max"], "ratio"),
            _criterion("SLIP_NORMAL_FORCE_VS_WEIGHT", slip_force_err, "<=", tol["slip_normal_force_relative_max"], "relative"),
        ]
    return {"case_id": case["case_id"], "family": "slider", "physics_dt_s": dt, "gates_suite": case["gates_suite"],
            "status": "PASS" if all(c["passed"] for c in criteria) else "FAIL", "criteria": criteria, "hypotheses": hypotheses, "metrics": metrics}


def evaluate_suite(evaluations: list[dict], contract: dict) -> dict:
    tol = contract["tolerances"]
    by_id = {e["case_id"]: e for e in evaluations}
    drops = [by_id[f"drop_and_settle_{k}ms"] for k in (4, 2, 1)]
    sliders = [by_id[f"viscous_slider_{k}ms"] for k in (4, 2, 1)]
    pen_drop = [e["metrics"]["rest_penetration_m"] for e in drops]
    pen_slider = [e["metrics"]["post_rest_penetration_m"] for e in sliders]
    spread_drop = (max(pen_drop) - min(pen_drop)) / _median(pen_drop)
    spread_slider = (max(pen_slider) - min(pen_slider)) / _median(pen_slider)
    e_cont = [e["metrics"]["viscous_continuous_relative_error_max"] for e in sliders]
    monotone = 1 if (e_cont[0] > e_cont[1] > e_cont[2]) else 0
    touchdown_all = 1 if all(next(c for c in e["criteria"] if c["id"] == "TOUCHDOWN_TIME_VS_CONTINUOUS_CLOSED_FORM")["passed"] for e in drops) else 0
    criteria = [
        _criterion("REST_PENETRATION_DT_INDEPENDENT_DROP", spread_drop, "<=", tol["rest_penetration_dt_spread_relative_max"], "relative spread"),
        _criterion("REST_PENETRATION_DT_INDEPENDENT_SLIDER", spread_slider, "<=", tol["rest_penetration_dt_spread_relative_max"], "relative spread"),
        _criterion("VISCOUS_CONTINUOUS_ERROR_MONOTONE", monotone, "==", 1, "flag"),
        _criterion("TOUCHDOWN_ERROR_WITHIN_DT_ALL", touchdown_all, "==", 1, "flag"),
    ]
    positive = min(e_cont) > 0.0
    gate_ok = all(e["status"] == "PASS" for e in evaluations) and all(c["passed"] for c in criteria)
    return {
        "status": "PASS" if gate_ok else "FAIL",
        "criteria": criteria,
        "timestep_study": {
            "rest_penetration_drop_m": pen_drop, "rest_penetration_slider_m": pen_slider,
            "viscous_continuous_relative_error": e_cont,
            "viscous_continuous_observed_order": {
                "coarse_medium": (math.log2(e_cont[0] / e_cont[1]) if positive else None),
                "medium_fine": (math.log2(e_cont[1] / e_cont[2]) if positive else None), "status": "ESTIMATED"},
            "touchdown_time_error_s": [e["metrics"]["touchdown_time_error_s"] for e in drops],
        },
        "closed_forms": closed_forms(contract),
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
                max_rel = max(max_rel, abs(float(a) - float(b)) / scale)      # 絕對差已在 1e-12 內的不列入
    p_crit = [(k["id"], bool(k["passed"])) for k in primary_case["criteria"]]
    r_crit = [(k["id"], bool(k["passed"])) for k in replayed["criteria"]]
    p_hyp = [(k["id"], bool(k["passed"])) for k in primary_case["hypotheses"]]
    r_hyp = [(k["id"], bool(k["passed"])) for k in replayed["hypotheses"]]
    return {"case_id": primary_case["case_id"], "metric_count": len(keys), "disagreements": disagreements,
            "max_relative_difference": max_rel, "criteria_identical": p_crit == r_crit,
            "hypotheses_identical": p_hyp == r_hyp,
            "agree": not disagreements and p_crit == r_crit and p_hyp == r_hyp}


def replay_contact_suite(primary: dict, primary_sha256: str | None = None) -> dict:
    validate_primary(primary)
    contract = primary["contract"]
    tol = contract["tolerances"]
    evaluations = []
    for case in primary["cases"]:
        evaluations.append(evaluate_drop_case(case, contract) if case["family"] == "drop" else evaluate_slider_case(case, contract))
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
    parser = argparse.ArgumentParser(description="stdlib-only replay of the V1 contact reference suite")
    parser.add_argument("primary", type=Path)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)
    primary, digest = load_primary(args.primary)
    receipt = replay_contact_suite(primary, digest)
    if args.output is not None:
        args.output.write_text(json.dumps(receipt, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({"status": receipt["status"], "primary_status": receipt["primary_status"],
                      "all_agree": receipt["primary_replay_agreement"]["all_agree"],
                      "cases": [{"case_id": c["case_id"], "status": c["status"],
                                 "failed": [k["id"] for k in c["criteria"] if not k["passed"]],
                                 "hypotheses": [(h["id"], h["passed"]) for h in c["hypotheses"]]} for c in receipt["cases"]],
                      "comparisons": receipt["primary_replay_agreement"]["cases"]}, indent=2, allow_nan=False))
    return 0 if receipt["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())

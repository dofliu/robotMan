"""V1 contact reference suite (V1-CONTACT-REFERENCE-SUITE-V1): frozen contract, MuJoCo primary run,
NumPy recomputation against closed forms.

Two contact-bearing, controller-free, actuation-free reference families on the plant's contact
parameters, plus one preregistered Coulomb hypothesis measurement:

  C. drop_and_settle_{4,2,1}ms   free sphere (1 contact): discrete free fall and touchdown step,
                                  normal impulse = weight integral, rest GRF = weight, equilibrium
                                  penetration of the engine's soft-contact model.
  S. viscous_slider_{4,2,1}ms    translational plate (4 contacts): unsaturated-friction viscous decay
                                  with the rate derived from the engine's soft-constraint model,
                                  n_c-scaled equilibrium penetration, normal force = weight.
  H. coulomb_hypothesis_slider_2ms same plate at 0.5 m/s; three preregistered hypotheses that do not
                                  gate the suite (gates_suite = False), bookkeeping criteria that do.

Specification: docs/V1_CONTACT_REFERENCE_SUITE_SPEC.md.  Thresholds live in CONTACT_SUITE_CONTRACT and
were frozen before the first execution; they must not be relaxed after seeing results.

    python backend/v1_contact_reference_suite.py --raw-output backend/run_traces/v1-contact-<ts>.json
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
import sys

import mujoco
import numpy as np

PRIMARY_SCHEMA_VERSION = "V1_CONTACT_REFERENCE_SUITE_V1"
CLAIM_BOUNDARY = (
    "SIM_ONLY_MUJOCO / NOT_PHYSICALLY_VALIDATED. Free-sphere drop-and-settle and a translational "
    "slider on the plant's contact parameters, compared with closed forms of free fall, momentum "
    "balance, rest equilibrium and the engine's own soft-contact model. The Coulomb hypothesis case "
    "is a preregistered measurement of the plant's contact model and does not gate the suite. "
    "No articulated body, no actuation, no controller, no physical validation; V1 stays PARTIAL."
)

GRAVITY = 9.81
FLOOR_XML = ('<geom name="floor" type="plane" group="2" contype="2" conaffinity="1" '
             'friction="1.0 0.005 0.0001" size="60 8 0.1"/>')
BODY_CONTACT_ATTRS = 'contype="1" conaffinity="2" friction="1.0 0.005 0.0001"'

CASE_SPECS = (
    {"case_id": "drop_and_settle_4ms", "family": "drop", "physics_dt_s": 0.004, "gates_suite": True,
     "roles": ["touchdown_schedule", "impulse", "rest_grf", "rest_penetration"]},
    {"case_id": "drop_and_settle_2ms", "family": "drop", "physics_dt_s": 0.002, "gates_suite": True,
     "roles": ["touchdown_schedule", "impulse", "rest_grf", "rest_penetration", "plant_dt"]},
    {"case_id": "drop_and_settle_1ms", "family": "drop", "physics_dt_s": 0.001, "gates_suite": True,
     "roles": ["touchdown_schedule", "impulse", "rest_grf", "rest_penetration"]},
    {"case_id": "viscous_slider_4ms", "family": "slider", "physics_dt_s": 0.004, "kick_velocity_mps": 0.02,
     "gates_suite": True, "hypothesis": False, "roles": ["viscous_slip", "rest_penetration_nc4"]},
    {"case_id": "viscous_slider_2ms", "family": "slider", "physics_dt_s": 0.002, "kick_velocity_mps": 0.02,
     "gates_suite": True, "hypothesis": False, "roles": ["viscous_slip", "rest_penetration_nc4", "plant_dt"]},
    {"case_id": "viscous_slider_1ms", "family": "slider", "physics_dt_s": 0.001, "kick_velocity_mps": 0.02,
     "gates_suite": True, "hypothesis": False, "roles": ["viscous_slip", "rest_penetration_nc4"]},
    {"case_id": "coulomb_hypothesis_slider_2ms", "family": "slider", "physics_dt_s": 0.002, "kick_velocity_mps": 0.5,
     "gates_suite": False, "hypothesis": True, "roles": ["coulomb_hypothesis", "plant_dt"]},
)

CONTACT_SUITE_CONTRACT = {
    "contract_id": "v1_contact_reference_suite_v1",
    "schema_version": PRIMARY_SCHEMA_VERSION,
    "claim_boundary": CLAIM_BOUNDARY,
    "gravity_mps2": GRAVITY,
    "integrator": "mjINT_IMPLICITFAST",
    "cone": "mjCONE_PYRAMIDAL",
    "condim": 3,
    "friction": [1.0, 0.005, 0.0001],
    "solref": [0.02, 1.0],
    "solimp": [0.9, 0.95, 0.001, 0.5, 2.0],
    "margin_m": 0.0,
    "solver": {"tolerance": 1.0e-8, "iterations": 100, "impratio": 1.0, "noslip_iterations": 0},
    "drop": {"mass_kg": 1.0, "radius_m": 0.05, "gap_m": 0.5, "duration_s": 2.0,
             "rest_window_s": [1.5, 2.0], "contact_count": 1},
    "slider": {"mass_kg": 1.0, "half_sizes_m": [0.10, 0.10, 0.02], "settle_s": 1.0, "duration_s": 2.0,
               "pre_rest_window_s": [0.7, 1.0], "post_rest_window_s": [1.5, 2.0],
               "contact_count_from_s": 0.1, "contact_count": 4, "mu": 1.0,
               "slip_velocity_floor_relative": 1.0e-3},
    "hypothesis": {"speed_floor_mps": 0.1, "post_rest_window_s": [1.7, 2.0],
                   "normal_force_relative_max": 0.02, "deceleration_relative_max": 0.02},
    "tolerances": {
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
    },
    "case_matrix": [deepcopy(s) for s in CASE_SPECS],
}

COMMON_CRITERION_IDS = (
    "FINITE_RAW_VALUES", "TRACE_STEP_COUNT", "TRACE_TIME_GRID", "COMPILED_TIMESTEP_IDENTITY",
    "COMPILED_MODEL_CONTRACT", "EXTERNAL_FORCE_ABSENT", "CONTACT_FRAME_AXIS_ALIGNED",
    "UNILATERAL_NORMAL_FORCE", "FRICTION_CONE_RESPECTED", "STEP_VELOCITY_UPDATE_IDENTITY",
    "CONTACT_FORCE_WORLD_SUM_MATCHES_QFRC_CONSTRAINT",
)
DROP_CRITERION_IDS = COMMON_CRITERION_IDS + (
    "TOUCHDOWN_STEP_MATCHES_DISCRETE_FREE_FALL", "TOUCHDOWN_TIME_VS_CONTINUOUS_CLOSED_FORM",
    "FREE_FALL_POSITION_DISCRETE_EXACT", "NORMAL_IMPULSE_MOMENTUM_IDENTITY",
    "NORMAL_IMPULSE_VS_WEIGHT_INTEGRAL", "REST_NORMAL_FORCE_VS_WEIGHT", "REST_VELOCITY",
    "REST_PENETRATION_VS_CLOSED_FORM",
)
SLIDER_GATE_CRITERION_IDS = COMMON_CRITERION_IDS + (
    "PRE_KICK_REST_NORMAL_FORCE_VS_WEIGHT", "PRE_KICK_REST_PENETRATION_VS_CLOSED_FORM",
    "TANGENTIAL_IMPULSE_IDENTITY", "POST_REST_NORMAL_FORCE_VS_WEIGHT", "POST_REST_VELOCITY",
    "POST_REST_PENETRATION_VS_CLOSED_FORM",
)
VISCOUS_CRITERION_IDS = SLIDER_GATE_CRITERION_IDS + (
    "CONTACT_COUNT_CONSTANT_FOUR", "VISCOUS_SLIP_VS_DISCRETE_CLOSED_FORM",
    "VISCOUS_SLIP_VS_CONTINUOUS_CLOSED_FORM", "VISCOUS_SLIP_RATE_VS_CLOSED_FORM",
    "FRICTION_UNSATURATED_IN_SLIP", "SLIP_NORMAL_FORCE_VS_WEIGHT",
)
HYPOTHESIS_IDS = ("H1_CONTACT_COUNT_CONSTANT_FOUR_IN_SLIDE", "H2_SLIDE_NORMAL_FORCE_VS_WEIGHT",
                  "H3_COULOMB_DECELERATION_VS_MU_G")
SUITE_CRITERION_IDS = ("REST_PENETRATION_DT_INDEPENDENT_DROP", "REST_PENETRATION_DT_INDEPENDENT_SLIDER",
                       "VISCOUS_CONTINUOUS_ERROR_MONOTONE", "TOUCHDOWN_ERROR_WITHIN_DT_ALL")

SAMPLE_KEYS = ("time_s", "qpos", "qvel", "qacc", "ncon", "qfrc_constraint",
               "qfrc_applied_abs_max", "xfrc_applied_abs_max", "contacts")
CONTACT_KEYS = ("geom1", "geom2", "dim", "dist", "pos", "frame", "force_contact_frame")


# ---------------------------------------------------------------- 小工具

def _sha256_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _criterion(criterion_id: str, value, operator: str, limit, unit: str, role: str = "gate") -> dict:
    ops = {"<=": lambda a, b: a <= b, ">=": lambda a, b: a >= b, "==": lambda a, b: a == b, "<": lambda a, b: a < b}
    finite = value is not None and (not isinstance(value, float) or math.isfinite(value))
    passed = bool(finite and ops[operator](value, limit))
    return {"id": criterion_id, "value": value, "operator": operator, "limit": limit, "unit": unit,
            "role": role, "passed": passed}


def _finite_tree(value) -> bool:
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return True
    if isinstance(value, (int,)):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, dict):
        return all(_finite_tree(v) for v in value.values())
    if isinstance(value, (list, tuple)):
        return all(_finite_tree(v) for v in value)
    return False


# ---------------------------------------------------------------- 閉式（與 v1_contact_replay.py 逐字對應）

def impedance(pen: float, solimp) -> float:
    dmin, dmax, width, mid, power = [float(x) for x in solimp]
    x = min(abs(pen) / width, 1.0)
    if x <= mid:
        y = (x ** power) / (mid ** (power - 1.0))
    else:
        y = 1.0 - ((1.0 - x) ** power) / ((1.0 - mid) ** (power - 1.0))
    return dmin + (dmax - dmin) * y


def constraint_stiffness(solref, solimp) -> float:
    """K = 1/(d_max² t_c² ζ²); the engine's efc_KBIP[0]."""
    tc, zeta = float(solref[0]), float(solref[1])
    return 1.0 / (float(solimp[1]) ** 2 * tc ** 2 * zeta ** 2)


def constraint_damping(solref, solimp) -> float:
    """B = 2/(d_max t_c); the engine's efc_KBIP[1]."""
    return 2.0 / (float(solimp[1]) * float(solref[0]))


def equilibrium_penetration(n_contacts: int, gravity: float, solref, solimp, iterations: int = 400) -> float:
    """pen* = (1 − d(pen*))·g / (n_c · d(pen*)² · K), damped fixed point."""
    k = constraint_stiffness(solref, solimp)
    pen = 0.0
    for _ in range(iterations):
        d = impedance(pen, solimp)
        pen = 0.5 * pen + 0.5 * (1.0 - d) * gravity / (n_contacts * d * d * k)
    return pen


def viscous_slip_rate(n_contacts: int, d: float, solref, solimp) -> float:
    """ρ = B · n_c d / (n_c d + 2(1 − d)) for μ = 1, condim 3, pyramidal facets with diag(A) = 4/m."""
    b = constraint_damping(solref, solimp)
    return b * n_contacts * d / (n_contacts * d + 2.0 * (1.0 - d))


def discrete_continuous_gap(x: float, k_max: int) -> float:
    """D = max_{1≤k≤k_max} |(1−x)^k − e^{−kx}|, computed from frozen constants only."""
    return max(abs((1.0 - x) ** k - math.exp(-k * x)) for k in range(1, k_max + 1))


def closed_forms(contract: dict = CONTACT_SUITE_CONTRACT) -> dict:
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
            raise RuntimeError("discrete touchdown search did not terminate")
    return n


# ---------------------------------------------------------------- MJCF

def build_drop_mjcf(dt: float, contract: dict = CONTACT_SUITE_CONTRACT) -> str:
    d = contract["drop"]
    return f"""<mujoco model="v1_contact_drop">
  <option gravity="0 0 -{contract['gravity_mps2']}" timestep="{dt}" integrator="implicitfast"/>
  <worldbody>
    {FLOOR_XML}
    <body name="ball" pos="0 0 {d['radius_m'] + d['gap_m']}">
      <freejoint name="root"/>
      <geom name="ball" type="sphere" size="{d['radius_m']}" mass="{d['mass_kg']}" {BODY_CONTACT_ATTRS}/>
    </body>
  </worldbody>
</mujoco>
"""


def build_slider_mjcf(dt: float, contract: dict = CONTACT_SUITE_CONTRACT) -> str:
    s = contract["slider"]
    hx, hy, hz = s["half_sizes_m"]
    return f"""<mujoco model="v1_contact_slider">
  <option gravity="0 0 -{contract['gravity_mps2']}" timestep="{dt}" integrator="implicitfast"/>
  <worldbody>
    {FLOOR_XML}
    <body name="slider" pos="0 0 {hz}">
      <joint name="slide_x" type="slide" axis="1 0 0"/>
      <joint name="slide_z" type="slide" axis="0 0 1"/>
      <geom name="slider" type="box" size="{hx} {hy} {hz}" mass="{s['mass_kg']}" {BODY_CONTACT_ATTRS}/>
    </body>
  </worldbody>
</mujoco>
"""


def compiled_model_receipt(model: mujoco.MjModel, xml: str) -> dict:
    geoms = []
    for g in range(model.ngeom):
        geoms.append({
            "name": mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, g),
            "type": mujoco.mjtGeom(int(model.geom_type[g])).name,
            "size": [float(x) for x in model.geom_size[g]],
            "friction": [float(x) for x in model.geom_friction[g]],
            "condim": int(model.geom_condim[g]),
            "solref": [float(x) for x in model.geom_solref[g]],
            "solimp": [float(x) for x in model.geom_solimp[g]],
            "margin": float(model.geom_margin[g]),
            "contype": int(model.geom_contype[g]),
            "conaffinity": int(model.geom_conaffinity[g]),
            "body": mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, int(model.geom_bodyid[g])),
        })
    joints = []
    for j in range(model.njnt):
        joints.append({"name": mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_JOINT, j),
                       "type": mujoco.mjtJoint(int(model.jnt_type[j])).name,
                       "qposadr": int(model.jnt_qposadr[j]), "dofadr": int(model.jnt_dofadr[j]),
                       "axis": [float(x) for x in model.jnt_axis[j]]})
    return {
        "mjcf_sha256": _sha256_text(xml),
        "timestep_s": float(model.opt.timestep),
        "integrator": mujoco.mjtIntegrator(int(model.opt.integrator)).name,
        "cone": mujoco.mjtCone(int(model.opt.cone)).name,
        "solver": mujoco.mjtSolver(int(model.opt.solver)).name,
        "gravity": [float(x) for x in model.opt.gravity],
        "solver_tolerance": float(model.opt.tolerance),
        "solver_iterations": int(model.opt.iterations),
        "impratio": float(model.opt.impratio),
        "noslip_iterations": int(model.opt.noslip_iterations),
        "nu": int(model.nu), "nv": int(model.nv), "nq": int(model.nq), "nbody": int(model.nbody),
        "body_mass": {mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_BODY, b): float(model.body_mass[b])
                      for b in range(1, model.nbody)},
        "geoms": geoms,
        "joints": joints,
    }


# ---------------------------------------------------------------- primary run

def _record_sample(model: mujoco.MjModel, data: mujoco.MjData) -> dict:
    mujoco.mj_forward(model, data)          # 接觸、約束力與 qacc 對應此 sample 的狀態
    force = np.zeros(6)
    contacts = []
    for i in range(data.ncon):
        c = data.contact[i]
        mujoco.mj_contactForce(model, data, i, force)
        contacts.append({
            "geom1": int(c.geom1), "geom2": int(c.geom2), "dim": int(c.dim), "dist": float(c.dist),
            "pos": [float(x) for x in c.pos],
            "frame": [float(x) for x in c.frame],
            "force_contact_frame": [float(x) for x in force],
        })
    return {
        "time_s": float(data.time),
        "qpos": [float(x) for x in data.qpos],
        "qvel": [float(x) for x in data.qvel],
        "qacc": [float(x) for x in data.qacc],
        "ncon": int(data.ncon),
        "qfrc_constraint": [float(x) for x in data.qfrc_constraint],
        "qfrc_applied_abs_max": float(np.max(np.abs(data.qfrc_applied))) if model.nv else 0.0,
        "xfrc_applied_abs_max": float(np.max(np.abs(data.xfrc_applied))),
        "contacts": contacts,
    }


def run_case(spec: dict, contract: dict = CONTACT_SUITE_CONTRACT) -> dict:
    dt = float(spec["physics_dt_s"])
    if spec["family"] == "drop":
        xml = build_drop_mjcf(dt, contract)
        duration = contract["drop"]["duration_s"]
        kick_step = None
    else:
        xml = build_slider_mjcf(dt, contract)
        duration = contract["slider"]["duration_s"]
        kick_step = int(round(contract["slider"]["settle_s"] / dt))
    model = mujoco.MjModel.from_xml_string(xml)
    data = mujoco.MjData(model)
    data.qvel[:] = 0.0
    n_steps = int(round(duration / dt))
    samples = [_record_sample(model, data)]
    for n in range(n_steps):
        if kick_step is not None and n == kick_step:
            # 狀態設定（不是外力）：這個 sample 記錄的是設定後、步進前的狀態
            data.qvel[0] = float(spec["kick_velocity_mps"])
            samples[n] = _record_sample(model, data)
        mujoco.mj_step(model, data)
        samples.append(_record_sample(model, data))
    return {
        "case_id": spec["case_id"], "family": spec["family"], "physics_dt_s": dt,
        "roles": list(spec["roles"]), "duration_s": duration, "expected_sample_count": n_steps + 1,
        "kick_step": kick_step, "gates_suite": bool(spec["gates_suite"]),
        "spec": deepcopy(spec),
        "compiled_model": compiled_model_receipt(model, xml),
        "mjcf": xml,
        "raw_trace": samples,
    }


# ---------------------------------------------------------------- 獨立可重算的量（NumPy；replay 用純 Python 重做）

def _frame_rows(contact: dict) -> np.ndarray:
    return np.asarray(contact["frame"], dtype=float).reshape(3, 3)


def contact_world_force(contact: dict) -> np.ndarray:
    """World-frame force on the contact body: frameᵀ · (f_n, f_t1, f_t2)."""
    return _frame_rows(contact).T @ np.asarray(contact["force_contact_frame"][:3], dtype=float)


def _axis_alignment_error(frame_rows: np.ndarray) -> float:
    err = 0.0
    for row in frame_rows:
        best = min(np.max(np.abs(row - s * np.eye(3)[a])) for a in range(3) for s in (1.0, -1.0))
        err = max(err, float(best))
    return err


def _translational_dof_axes(case: dict) -> list[tuple[int, int]]:
    """(dof index, world axis) pairs for the translational dofs of the reference body."""
    pairs = []
    for j in case["compiled_model"]["joints"]:
        if j["type"] == "mjJNT_FREE":
            pairs.extend((j["dofadr"] + a, a) for a in range(3))
        elif j["type"] == "mjJNT_SLIDE":
            axis = int(np.argmax(np.abs(j["axis"])))
            pairs.append((j["dofadr"], axis))
    return pairs


def common_metrics(case: dict, contract: dict) -> dict:
    trace = case["raw_trace"]
    dt = case["physics_dt_s"]
    mu = contract["friction"][0]
    times = np.array([s["time_s"] for s in trace])
    grid_err = float(np.max(np.abs(times - dt * np.arange(len(trace)))))
    ext = max(max(s["qfrc_applied_abs_max"], s["xfrc_applied_abs_max"]) for s in trace)
    axis_err = 0.0
    fn_min = math.inf
    util_max = 0.0
    closure = 0.0
    pairs = _translational_dof_axes(case)
    for s in trace:
        world_sum = np.zeros(3)
        for c in s["contacts"]:
            rows = _frame_rows(c)
            axis_err = max(axis_err, _axis_alignment_error(rows))
            f = c["force_contact_frame"]
            fn_min = min(fn_min, float(f[0]))
            tangential = math.hypot(float(f[1]), float(f[2]))
            if f[0] > 0.0:
                util_max = max(util_max, tangential / (mu * float(f[0])))
            elif tangential > 0.0:
                util_max = math.inf
            world_sum += contact_world_force(c)
        qfrc = np.asarray(s["qfrc_constraint"], dtype=float)
        for dof, axis in pairs:
            closure = max(closure, abs(world_sum[axis] - qfrc[dof]))
    if not math.isfinite(fn_min):
        fn_min = 0.0
    vel_update = 0.0
    kick = case.get("kick_step")
    for n in range(len(trace) - 1):
        if kick is not None and n + 1 == kick:
            continue                        # 狀態設定那一步不屬於積分器的更新
        v0 = np.asarray(trace[n]["qvel"], dtype=float)
        v1 = np.asarray(trace[n + 1]["qvel"], dtype=float)
        a0 = np.asarray(trace[n]["qacc"], dtype=float)
        vel_update = max(vel_update, float(np.max(np.abs(v1 - v0 - dt * a0))))
    return {
        "time_grid_error_max_s": grid_err,
        "external_force_abs_max": float(ext),
        "frame_axis_alignment_error_max": float(axis_err),
        "normal_force_min_n": float(fn_min),
        "friction_cone_utilisation_max": float(util_max),
        "step_velocity_update_error_max": float(vel_update),
        "contact_force_closure_error_max_n": float(closure),
    }


def _model_contract_ok(case: dict, contract: dict) -> tuple[bool, list[str]]:
    cm = case["compiled_model"]
    problems = []
    if cm["integrator"] != contract["integrator"]:
        problems.append(f"integrator {cm['integrator']}")
    if cm["cone"] != contract["cone"]:
        problems.append(f"cone {cm['cone']}")
    if cm["gravity"] != [0.0, 0.0, -contract["gravity_mps2"]]:
        problems.append(f"gravity {cm['gravity']}")
    if cm["nu"] != 0:
        problems.append(f"nu {cm['nu']}")
    sol = contract["solver"]
    if cm["solver_tolerance"] != sol["tolerance"] or cm["solver_iterations"] != sol["iterations"] \
            or cm["impratio"] != sol["impratio"] or cm["noslip_iterations"] != sol["noslip_iterations"]:
        problems.append("solver options")
    names = {g["name"] for g in cm["geoms"]}
    expected = {"floor", "ball"} if case["family"] == "drop" else {"floor", "slider"}
    if names != expected:
        problems.append(f"geoms {sorted(names)}")
    for g in cm["geoms"]:
        if g["friction"] != contract["friction"] or g["condim"] != contract["condim"] \
                or g["solref"] != contract["solref"] or g["solimp"] != contract["solimp"] or g["margin"] != contract["margin_m"]:
            problems.append(f"contact params of {g['name']}")
        if g["name"] == "floor" and (g["contype"], g["conaffinity"]) != (2, 1):
            problems.append("floor bitmask")
        if g["name"] != "floor" and (g["contype"], g["conaffinity"]) != (1, 2):
            problems.append("body bitmask")
    fam = contract[case["family"]]
    body = "ball" if case["family"] == "drop" else "slider"
    if abs(cm["body_mass"].get(body, math.nan) - fam["mass_kg"]) > contract["tolerances"]["mass_abs_error_max_kg"]:
        problems.append("body mass")
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
        _criterion("CONTACT_FRAME_AXIS_ALIGNED", metrics["frame_axis_alignment_error_max"], "<=", tol["frame_axis_alignment_max"], "unit vector"),
        _criterion("UNILATERAL_NORMAL_FORCE", metrics["normal_force_min_n"], ">=", tol["unilateral_normal_force_min_n"], "N"),
        _criterion("FRICTION_CONE_RESPECTED", metrics["friction_cone_utilisation_max"], "<=", tol["friction_cone_utilisation_max"], "ratio"),
        _criterion("STEP_VELOCITY_UPDATE_IDENTITY", metrics["step_velocity_update_error_max"], "<=", tol["step_velocity_update_max"], "m/s or rad/s"),
        _criterion("CONTACT_FORCE_WORLD_SUM_MATCHES_QFRC_CONSTRAINT", metrics["contact_force_closure_error_max_n"], "<=", tol["contact_force_closure_max_n"], "N"),
    ]


def _window_indices(trace: list[dict], window: list[float], dt: float) -> list[int]:
    lo, hi = window
    return [n for n, s in enumerate(trace) if s["time_s"] >= lo - 1e-9 * dt and s["time_s"] <= hi + 1e-9 * dt]


def _world_normal_sum(sample: dict) -> float:
    return float(sum(contact_world_force(c)[2] for c in sample["contacts"]))


def _world_x_sum(sample: dict) -> float:
    return float(sum(contact_world_force(c)[0] for c in sample["contacts"]))


def evaluate_drop_case(case: dict, contract: dict = CONTACT_SUITE_CONTRACT) -> dict:
    tol = contract["tolerances"]
    drop = contract["drop"]
    g = contract["gravity_mps2"]
    m, r, gap, dt = drop["mass_kg"], drop["radius_m"], drop["gap_m"], case["physics_dt_s"]
    trace = case["raw_trace"]
    metrics = common_metrics(case, contract)
    forms = closed_forms(contract)
    n_samples = len(trace)
    total_t = dt * (n_samples - 1)

    touchdown = next((n for n, s in enumerate(trace) if s["ncon"] > 0), None)
    n_star = discrete_touchdown_step(gap, g, dt)
    z = np.array([s["qpos"][2] for s in trace])
    z0 = r + gap
    n_idx = np.arange(n_samples, dtype=float)
    z_closed = z0 - g * dt * dt * n_idx * (n_idx + 1.0) / 2.0
    pre = min(touchdown if touchdown is not None else n_samples, n_samples)
    free_fall_err = float(np.max(np.abs(z[:pre] - z_closed[:pre]))) if pre > 0 else 0.0

    fz = np.array([_world_normal_sum(s) for s in trace])
    impulse = float(np.sum(fz[:-1]) * dt)            # 左端點和：第 n 個 sample 的力用於 n→n+1
    vz0, vzN = trace[0]["qvel"][2], trace[-1]["qvel"][2]
    weight_integral = m * g * total_t
    identity_res = abs(impulse - m * (vzN - vz0) - weight_integral) / weight_integral
    weight_err = abs(impulse - weight_integral) / weight_integral

    rest = _window_indices(trace, drop["rest_window_s"], dt)
    rest_force_err = float(max(abs(fz[n] - m * g) for n in rest) / (m * g))
    rest_vel = float(max(np.max(np.abs(trace[n]["qvel"])) for n in rest))
    pen_rest = r - float(trace[rest[-1]]["qpos"][2])
    pen_star = forms["rest_penetration_drop_m"]
    pen_err = abs(pen_rest - pen_star) / pen_star

    ncon = [s["ncon"] for s in trace]
    separations = 0
    if touchdown is not None:
        separations = sum(1 for n in range(touchdown + 1, n_samples) if ncon[n] == 0 and ncon[n - 1] > 0)
    penetration = np.maximum(0.0, r - z)
    metrics.update({
        "touchdown_step": touchdown, "touchdown_step_closed": n_star,
        "touchdown_step_delta": (None if touchdown is None else abs(touchdown - n_star)),
        "touchdown_time_s": (None if touchdown is None else touchdown * dt),
        "touchdown_time_continuous_s": forms["touchdown_time_continuous_s"],
        "touchdown_time_error_s": (None if touchdown is None else abs(touchdown * dt - forms["touchdown_time_continuous_s"])),
        "free_fall_position_error_max_m": free_fall_err,
        "normal_impulse_ns": impulse, "weight_integral_ns": weight_integral,
        "impulse_identity_relative_error": float(identity_res), "impulse_weight_relative_error": float(weight_err),
        "rest_normal_force_relative_error_max": rest_force_err, "rest_velocity_max": rest_vel,
        "rest_penetration_m": pen_rest, "rest_penetration_closed_m": pen_star, "rest_penetration_relative_error": float(pen_err),
        "max_penetration_m": float(np.max(penetration)), "peak_normal_force_n": float(np.max(fz)),
        "separation_events_after_touchdown": int(separations),
        "sample_count": n_samples,
    })
    criteria = _common_criteria(case, contract, metrics) + [
        _criterion("TOUCHDOWN_STEP_MATCHES_DISCRETE_FREE_FALL", metrics["touchdown_step_delta"], "<=", tol["touchdown_step_delta_max"], "steps"),
        _criterion("TOUCHDOWN_TIME_VS_CONTINUOUS_CLOSED_FORM", metrics["touchdown_time_error_s"], "<=", dt, "s"),
        _criterion("FREE_FALL_POSITION_DISCRETE_EXACT", free_fall_err, "<=", tol["free_fall_position_abs_max_m"], "m"),
        _criterion("NORMAL_IMPULSE_MOMENTUM_IDENTITY", float(identity_res), "<=", tol["impulse_identity_relative_max"], "relative"),
        _criterion("NORMAL_IMPULSE_VS_WEIGHT_INTEGRAL", float(weight_err), "<=", tol["impulse_weight_relative_max"], "relative"),
        _criterion("REST_NORMAL_FORCE_VS_WEIGHT", rest_force_err, "<=", tol["rest_normal_force_relative_max"], "relative"),
        _criterion("REST_VELOCITY", rest_vel, "<=", tol["rest_velocity_max"], "m/s or rad/s"),
        _criterion("REST_PENETRATION_VS_CLOSED_FORM", float(pen_err), "<=", tol["rest_penetration_relative_max"], "relative"),
    ]
    assert [c["id"] for c in criteria] == list(DROP_CRITERION_IDS)
    return {"case_id": case["case_id"], "family": "drop", "physics_dt_s": dt, "gates_suite": case["gates_suite"],
            "status": "PASS" if all(c["passed"] for c in criteria) else "FAIL",
            "criteria": criteria, "hypotheses": [], "metrics": metrics}


def evaluate_slider_case(case: dict, contract: dict = CONTACT_SUITE_CONTRACT) -> dict:
    tol = contract["tolerances"]
    sl = contract["slider"]
    hyp = contract["hypothesis"]
    g = contract["gravity_mps2"]
    mu = sl["mu"]
    m, dt = sl["mass_kg"], case["physics_dt_s"]
    trace = case["raw_trace"]
    metrics = common_metrics(case, contract)
    forms = closed_forms(contract)
    n_samples = len(trace)
    kick = case["kick_step"]
    v0 = float(case["spec"]["kick_velocity_mps"])
    is_hyp = bool(case["spec"].get("hypothesis"))

    fz = np.array([_world_normal_sum(s) for s in trace])
    fx = np.array([_world_x_sum(s) for s in trace])
    vx = np.array([s["qvel"][0] for s in trace])
    x = np.array([s["qpos"][0] for s in trace])
    pen = -np.array([s["qpos"][1] for s in trace])
    ncon = [s["ncon"] for s in trace]

    pre = _window_indices(trace, sl["pre_rest_window_s"], dt)
    pre = [n for n in pre if n < kick]
    pre_force_err = float(max(abs(fz[n] - m * g) for n in pre) / (m * g))
    pen_star = forms["rest_penetration_slider_m"]
    pre_pen = float(pen[kick - 1])
    pre_pen_err = abs(pre_pen - pen_star) / pen_star

    floor_v = hyp["speed_floor_mps"] if is_hyp else sl["slip_velocity_floor_relative"] * v0
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
    slip_force_err = float(max(abs(fz[n] - m * g) for n in slip) / (m * g)) if slip else math.inf
    contact_ok_from = _window_indices(trace, [sl["contact_count_from_s"], case["duration_s"]], dt)
    contact_count_ok = all(ncon[n] == sl["contact_count"] for n in contact_ok_from)

    tangential_impulse = float(np.sum(fx[kick:-1]) * dt)
    tangential_identity = abs(tangential_impulse - m * (vx[-1] - v0)) / (m * v0)

    post_window = hyp["post_rest_window_s"] if is_hyp else sl["post_rest_window_s"]
    post = _window_indices(trace, post_window, dt)
    post_force_err = float(max(abs(fz[n] - m * g) for n in post) / (m * g))
    post_vel = float(max(np.max(np.abs(trace[n]["qvel"])) for n in post))
    post_pen = float(pen[post[-1]])
    post_pen_err = abs(post_pen - pen_star) / pen_star

    metrics.update({
        "kick_step": kick, "kick_velocity_mps": v0, "slip_window_samples": len(slip),
        "pre_rest_normal_force_relative_error_max": pre_force_err,
        "pre_rest_penetration_m": pre_pen, "rest_penetration_closed_m": pen_star,
        "pre_rest_penetration_relative_error": float(pre_pen_err),
        "slip_utilisation_max": float(util_slip), "slip_normal_force_relative_error_max": slip_force_err,
        "contact_count_constant": 1 if contact_count_ok else 0,
        "tangential_impulse_ns": tangential_impulse, "tangential_impulse_relative_error": float(tangential_identity),
        "post_rest_normal_force_relative_error_max": post_force_err, "post_rest_velocity_max": post_vel,
        "post_rest_penetration_m": post_pen, "post_rest_penetration_relative_error": float(post_pen_err),
        "slide_distance_m": float(x[-1] - x[kick]), "normal_force_inflation_max_ratio": float(np.max(fz[kick:]) / (m * g)),
        "lost_contact_samples_after_kick": int(sum(1 for n in range(kick, n_samples) if ncon[n] < sl["contact_count"])),
        "sample_count": n_samples,
    })
    criteria = _common_criteria(case, contract, metrics) + [
        _criterion("PRE_KICK_REST_NORMAL_FORCE_VS_WEIGHT", pre_force_err, "<=", tol["rest_normal_force_relative_max"], "relative"),
        _criterion("PRE_KICK_REST_PENETRATION_VS_CLOSED_FORM", float(pre_pen_err), "<=", tol["rest_penetration_relative_max"], "relative"),
        _criterion("TANGENTIAL_IMPULSE_IDENTITY", float(tangential_identity), "<=", tol["tangential_impulse_relative_max"], "relative"),
        _criterion("POST_REST_NORMAL_FORCE_VS_WEIGHT", post_force_err, "<=", tol["rest_normal_force_relative_max"], "relative"),
        _criterion("POST_REST_VELOCITY", post_vel, "<=", tol["rest_velocity_max"], "m/s"),
        _criterion("POST_REST_PENETRATION_VS_CLOSED_FORM", float(post_pen_err), "<=", tol["rest_penetration_relative_max"], "relative"),
    ]
    hypotheses = []
    if is_hyp:
        slip_set = set(slip)
        decel = [(vx[n] - vx[n + 1]) / dt for n in slip if (n + 1) in slip_set]
        mean_decel = float(np.mean(decel)) if decel else math.nan
        decel_err = abs(mean_decel - mu * g) / (mu * g) if decel else math.inf
        slide_contact_ok = all(ncon[n] == sl["contact_count"] for n in slip) if slip else False
        metrics.update({"hypothesis_mean_deceleration_mps2": mean_decel,
                        "hypothesis_deceleration_relative_error": float(decel_err),
                        "hypothesis_slide_contact_count_constant": 1 if slide_contact_ok else 0})
        hypotheses = [
            _criterion("H1_CONTACT_COUNT_CONSTANT_FOUR_IN_SLIDE", metrics["hypothesis_slide_contact_count_constant"], "==", 1, "flag", role="hypothesis"),
            _criterion("H2_SLIDE_NORMAL_FORCE_VS_WEIGHT", slip_force_err, "<=", hyp["normal_force_relative_max"], "relative", role="hypothesis"),
            _criterion("H3_COULOMB_DECELERATION_VS_MU_G", float(decel_err), "<=", hyp["deceleration_relative_max"], "relative", role="hypothesis"),
        ]
        assert [c["id"] for c in criteria] == list(SLIDER_GATE_CRITERION_IDS)
    else:
        rho = forms["viscous_slip_rate_per_s"]
        xk = dt * rho
        k = np.array([n - kick for n in slip], dtype=float)
        v_slip = vx[slip]
        geo_err = float(np.max(np.abs(v_slip - v0 * (1.0 - xk) ** k)) / v0) if slip else math.inf
        exp_err = float(np.max(np.abs(v_slip - v0 * np.exp(-rho * k * dt))) / v0) if slip else math.inf
        k_max = n_samples - 1 - kick
        gap_d = discrete_continuous_gap(xk, k_max)
        rates = [(vx[n] - vx[n + 1]) / (dt * vx[n]) for n in slip[:-1]]
        rate_mean = float(np.mean(rates)) if rates else math.nan
        rate_err = abs(rate_mean - rho) / rho if rates else math.inf
        metrics.update({"viscous_rate_closed_per_s": rho, "viscous_rate_measured_mean_per_s": rate_mean,
                        "viscous_rate_relative_error": float(rate_err),
                        "viscous_discrete_relative_error_max": geo_err, "viscous_continuous_relative_error_max": exp_err,
                        "viscous_discrete_continuous_gap": float(gap_d)})
        criteria += [
            _criterion("CONTACT_COUNT_CONSTANT_FOUR", metrics["contact_count_constant"], "==", 1, "flag"),
            _criterion("VISCOUS_SLIP_VS_DISCRETE_CLOSED_FORM", geo_err, "<=", tol["viscous_discrete_relative_max"], "relative to v0"),
            _criterion("VISCOUS_SLIP_VS_CONTINUOUS_CLOSED_FORM", exp_err, "<=", float(gap_d) + tol["viscous_continuous_extra_relative"], "relative to v0"),
            _criterion("VISCOUS_SLIP_RATE_VS_CLOSED_FORM", float(rate_err), "<=", tol["viscous_rate_relative_max"], "relative"),
            _criterion("FRICTION_UNSATURATED_IN_SLIP", float(util_slip), "<", tol["slip_utilisation_max"], "ratio"),
            _criterion("SLIP_NORMAL_FORCE_VS_WEIGHT", slip_force_err, "<=", tol["slip_normal_force_relative_max"], "relative"),
        ]
        assert [c["id"] for c in criteria] == list(VISCOUS_CRITERION_IDS)
    return {"case_id": case["case_id"], "family": "slider", "physics_dt_s": dt, "gates_suite": case["gates_suite"],
            "status": "PASS" if all(c["passed"] for c in criteria) else "FAIL",
            "criteria": criteria, "hypotheses": hypotheses, "metrics": metrics}


def evaluate_case(case: dict, contract: dict = CONTACT_SUITE_CONTRACT) -> dict:
    return evaluate_drop_case(case, contract) if case["family"] == "drop" else evaluate_slider_case(case, contract)


def _observed_order(e_coarse: float, e_medium: float, e_fine: float) -> float | None:
    if min(e_coarse, e_medium, e_fine) <= 0.0:
        return None
    return float(math.log2(e_coarse / e_medium))


def evaluate_suite(cases: list[dict], evaluations: list[dict], contract: dict = CONTACT_SUITE_CONTRACT) -> dict:
    tol = contract["tolerances"]
    by_id = {e["case_id"]: e for e in evaluations}
    drops = [by_id[f"drop_and_settle_{k}ms"] for k in (4, 2, 1)]
    sliders = [by_id[f"viscous_slider_{k}ms"] for k in (4, 2, 1)]
    pen_drop = [e["metrics"]["rest_penetration_m"] for e in drops]
    pen_slider = [e["metrics"]["post_rest_penetration_m"] for e in sliders]
    spread_drop = (max(pen_drop) - min(pen_drop)) / float(np.median(pen_drop))
    spread_slider = (max(pen_slider) - min(pen_slider)) / float(np.median(pen_slider))
    e_cont = [e["metrics"]["viscous_continuous_relative_error_max"] for e in sliders]
    monotone = 1 if (e_cont[0] > e_cont[1] > e_cont[2]) else 0
    touchdown_all = 1 if all(next(c for c in e["criteria"] if c["id"] == "TOUCHDOWN_TIME_VS_CONTINUOUS_CLOSED_FORM")["passed"] for e in drops) else 0
    criteria = [
        _criterion("REST_PENETRATION_DT_INDEPENDENT_DROP", float(spread_drop), "<=", tol["rest_penetration_dt_spread_relative_max"], "relative spread"),
        _criterion("REST_PENETRATION_DT_INDEPENDENT_SLIDER", float(spread_slider), "<=", tol["rest_penetration_dt_spread_relative_max"], "relative spread"),
        _criterion("VISCOUS_CONTINUOUS_ERROR_MONOTONE", monotone, "==", 1, "flag"),
        _criterion("TOUCHDOWN_ERROR_WITHIN_DT_ALL", touchdown_all, "==", 1, "flag"),
    ]
    assert [c["id"] for c in criteria] == list(SUITE_CRITERION_IDS)
    order_42 = _observed_order(e_cont[0], e_cont[1], e_cont[2])
    order_21 = None if min(e_cont) <= 0 else float(math.log2(e_cont[1] / e_cont[2]))
    hyp_cases = [e for e in evaluations if e["hypotheses"]]
    gate_ok = all(e["status"] == "PASS" for e in evaluations) and all(c["passed"] for c in criteria)
    return {
        "status": "PASS" if gate_ok else "FAIL",
        "criteria": criteria,
        "timestep_study": {
            "rest_penetration_drop_m": pen_drop, "rest_penetration_slider_m": pen_slider,
            "viscous_continuous_relative_error": e_cont,
            "viscous_continuous_observed_order": {"coarse_medium": order_42, "medium_fine": order_21, "status": "ESTIMATED"},
            "touchdown_time_error_s": [e["metrics"]["touchdown_time_error_s"] for e in drops],
        },
        "hypothesis_outcomes": [{"case_id": e["case_id"], "hypotheses": [{"id": h["id"], "passed": h["passed"], "value": h["value"], "limit": h["limit"]} for h in e["hypotheses"]],
                                 "gates_suite": e["gates_suite"]} for e in hyp_cases],
        "closed_forms": closed_forms(contract),
    }


def run_contact_suite(contract: dict = CONTACT_SUITE_CONTRACT) -> dict:
    cases = [run_case(spec, contract) for spec in contract["case_matrix"]]
    evaluations = [evaluate_case(c, contract) for c in cases]
    suite = evaluate_suite(cases, evaluations, contract)
    merged = []
    for case, ev in zip(cases, evaluations):
        entry = deepcopy(case)
        entry.update({"status": ev["status"], "criteria": ev["criteria"], "hypotheses": ev["hypotheses"], "metrics": ev["metrics"]})
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
    parser = argparse.ArgumentParser(description="V1 contact reference suite (frozen contract).")
    parser.add_argument("--raw-output", type=Path, default=None, help="write the full primary result here (exclusive create)")
    args = parser.parse_args(argv)
    result = run_contact_suite()
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
                                 "hypotheses": [{"id": h["id"], "passed": h["passed"], "value": h["value"]} for h in c["hypotheses"]]} for c in compact["cases"]],
                      "suite_failed": [k["id"] for k in compact["suite"]["criteria"] if not k["passed"]],
                      "closed_forms": compact["suite"]["closed_forms"],
                      "timestep_study": compact["suite"]["timestep_study"]}, indent=2, allow_nan=False))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())

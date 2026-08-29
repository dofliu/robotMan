"""Versioned Motion Task registry and deterministic trace evaluator.

The first task is intentionally bounded.  It evaluates only realized MuJoCo
samples and keeps all thresholds in one frozen contract so the UI cannot tune
criteria after seeing a result.
"""

from __future__ import annotations

from copy import deepcopy

import numpy as np


TASK_ID = "stand_start_walk_stop_v1"

_TASKS: dict[str, dict] = {
    TASK_ID: {
        "schema_version": "MOTION_TASK_V1",
        "task_id": TASK_ID,
        "name": "stand → start → steady walk → stop",
        "duration_s": 9.0,
        "physics_rate_hz": 500.0,
        "initialization": {
            "reset_state": True,
            "clear_obstacles": True,
            "clear_external_push": True,
            "assist_enabled": False,
        },
        "gait": {
            "mode": "walk",
            "speed": 0.7,
            "step_length": 0.35,
            "duty": 0.62,
            "clearance": 0.07,
        },
        "phases": [
            {"id": "INITIAL_STAND", "start_s": 0.0, "end_s": 1.0, "mode": "stand"},
            {"id": "START", "start_s": 1.0, "end_s": 2.5, "mode": "walk"},
            {"id": "STEADY_WALK", "start_s": 2.5, "end_s": 6.5, "mode": "walk"},
            {"id": "STOP", "start_s": 6.5, "end_s": 8.0, "mode": "stand"},
            {"id": "FINAL_STAND", "start_s": 8.0, "end_s": 9.0, "mode": "stand"},
        ],
        "criteria": {
            "posture_limit_deg": 15.0,
            "steady_speed_min_mps": 0.35,
            "steady_speed_max_mps": 1.05,
            "steady_progress_min_m": 1.40,
            "stop_speed_max_mps": 0.15,
            "lateral_drift_max_m": 0.30,
            "saturation_threshold_pct": 95.0,
            "saturation_duty_max_pct": 30.0,
            "final_window_s": 0.50,
        },
    },
}


def get_motion_task(task_id: str) -> dict:
    """Return an isolated contract copy; unknown IDs fail closed."""
    if task_id not in _TASKS:
        raise KeyError(task_id)
    return deepcopy(_TASKS[task_id])


def list_motion_tasks() -> list[dict]:
    return [get_motion_task(task_id) for task_id in _TASKS]


class MotionTaskRunner:
    """Tracks phase transitions against simulation time, not wall time."""

    def __init__(self, contract: dict, *, started_sim_t: float, group_id: str | None):
        self.contract = deepcopy(contract)
        self.task_id = str(contract["task_id"])
        self.started_sim_t = float(started_sim_t)
        self.group_id = group_id
        self.phase_index = 0
        self.active = True
        self.phase_events: list[dict] = [{
            "phase": contract["phases"][0]["id"],
            "scheduled_s": 0.0,
            "actual_s": 0.0,
            "mode": contract["phases"][0]["mode"],
        }]

    def elapsed(self, sim_t: float) -> float:
        return max(float(sim_t) - self.started_sim_t, 0.0)

    def apply_due_transitions(self, session) -> None:
        """Apply every phase event due before the next physics step."""
        elapsed = self.elapsed(session.sim_t)
        phases = self.contract["phases"]
        while self.active and self.phase_index + 1 < len(phases):
            candidate = phases[self.phase_index + 1]
            if elapsed + 1e-9 < float(candidate["start_s"]):
                break
            self.phase_index += 1
            session._set_mode_internal(candidate["mode"], preserve_fall=True)
            self.phase_events.append({
                "phase": candidate["id"],
                "scheduled_s": float(candidate["start_s"]),
                "actual_s": round(elapsed, 6),
                "mode": candidate["mode"],
            })

    def status(self, sim_t: float) -> dict:
        phase = self.contract["phases"][self.phase_index]
        return {
            "active": self.active,
            "task_id": self.task_id,
            "group_id": self.group_id,
            "phase": phase["id"],
            "elapsed_s": round(self.elapsed(sim_t), 3),
            "duration_s": float(self.contract["duration_s"]),
            "target_speed_mps": float(self.contract["gait"]["speed"]),
        }


def _criterion(
    criterion_id: str,
    passed: bool,
    value,
    operator: str,
    limit,
    unit: str,
) -> dict:
    if isinstance(value, (np.floating, float)):
        value = round(float(value), 6)
    return {
        "id": criterion_id,
        "passed": bool(passed),
        "value": value,
        "operator": operator,
        "limit": limit,
        "unit": unit,
    }


def evaluate_motion_task(
    arrays: dict[str, np.ndarray],
    contract: dict,
    *,
    physics_dt: float,
    stop_reason: str,
    assist_enabled_at_start: bool,
) -> dict:
    """Deterministically evaluate a completed or cancelled raw trace."""
    if stop_reason == "task_cancelled":
        return {"status": "CANCELLED", "criteria": [], "evaluated_samples": int(len(arrays["time"]))}

    time = np.asarray(arrays["time"], dtype=float)
    relative = time - time[0] + float(physics_dt)
    criteria_contract = contract["criteria"]
    initial = relative <= 1.0 + 0.5 * physics_dt
    steady = (relative >= 2.5 - 0.5 * physics_dt) & (relative <= 6.5 + 0.5 * physics_dt)
    final_window = relative >= float(contract["duration_s"]) - criteria_contract["final_window_s"]

    def max_posture(mask: np.ndarray) -> float:
        return float(max(
            np.max(np.abs(arrays["pitch_deg"][mask])),
            np.max(np.abs(arrays["roll_deg"][mask])),
        ))

    trace_duration = float(relative[-1])
    trace_complete = (
        stop_reason == "task_complete"
        and trace_duration + 0.5 * physics_dt >= float(contract["duration_s"])
    )
    fallen = bool(np.any(arrays["state_code"] == 2))
    initial_posture = max_posture(initial)
    steady_speed = float(np.mean(arrays["com_vel"][steady, 0]))
    steady_indices = np.flatnonzero(steady)
    steady_progress = float(
        arrays["qpos"][steady_indices[-1], 0] - arrays["qpos"][steady_indices[0], 0]
    )
    stop_speed = float(np.mean(np.abs(arrays["com_vel"][final_window, 0])))
    final_posture = max_posture(final_window)
    final_state = int(arrays["state_code"][-1])
    lateral_drift = float(abs(arrays["qpos"][-1, 1] - arrays["qpos"][0, 1]))
    max_saturation = np.nanmax(arrays["saturation_pct"], axis=1)
    saturation_duty = float(np.mean(max_saturation >= criteria_contract["saturation_threshold_pct"]) * 100.0)

    criteria = [
        _criterion("TRACE_INTEGRITY", trace_complete, trace_duration, ">=", contract["duration_s"], "s"),
        _criterion("ASSIST_DISABLED", not assist_enabled_at_start, bool(assist_enabled_at_start), "==", False, "bool"),
        _criterion("NO_FALL", not fallen, fallen, "==", False, "bool"),
        _criterion("INITIAL_STAND_POSTURE", initial_posture <= criteria_contract["posture_limit_deg"], initial_posture, "<=", criteria_contract["posture_limit_deg"], "deg"),
        _criterion(
            "STEADY_SPEED",
            criteria_contract["steady_speed_min_mps"] <= steady_speed <= criteria_contract["steady_speed_max_mps"],
            steady_speed,
            "between",
            [criteria_contract["steady_speed_min_mps"], criteria_contract["steady_speed_max_mps"]],
            "m/s",
        ),
        _criterion("STEADY_PROGRESS", steady_progress >= criteria_contract["steady_progress_min_m"], steady_progress, ">=", criteria_contract["steady_progress_min_m"], "m"),
        _criterion("STOP_SPEED", stop_speed <= criteria_contract["stop_speed_max_mps"], stop_speed, "<=", criteria_contract["stop_speed_max_mps"], "m/s"),
        _criterion("FINAL_STAND_POSTURE", final_posture <= criteria_contract["posture_limit_deg"], final_posture, "<=", criteria_contract["posture_limit_deg"], "deg"),
        _criterion("FINAL_STATE", final_state == 0, "STAND" if final_state == 0 else ("WALK" if final_state == 1 else "FALLEN"), "==", "STAND", "state"),
        _criterion("LATERAL_DRIFT", lateral_drift <= criteria_contract["lateral_drift_max_m"], lateral_drift, "<=", criteria_contract["lateral_drift_max_m"], "m"),
        _criterion("SATURATION_DUTY", saturation_duty <= criteria_contract["saturation_duty_max_pct"], saturation_duty, "<=", criteria_contract["saturation_duty_max_pct"], "% samples"),
    ]
    return {
        "status": "PASS" if all(item["passed"] for item in criteria) else "FAIL",
        "criteria": criteria,
        "evaluated_samples": int(len(time)),
    }

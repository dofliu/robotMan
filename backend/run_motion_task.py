"""Run one frozen Motion Task and print a compact development receipt.

Examples:
  python backend/run_motion_task.py
  python backend/run_motion_task.py --controller rl_task_v2
  python backend/run_motion_task.py --controller rl_task_v5

The runner writes normal hash-validated Dynamic Run Trace artifacts.  Results
remain SIM-only development evidence and do not establish controller ranking.
"""

from __future__ import annotations

import argparse
import json

from compare_live import CONTROLLERS, CompareSession
from config_schema import GaitParams, default_robot
from live_sim import LiveSession
from motion_tasks import TASK_ID


SINGLE_CONTROLLERS = (*CONTROLLERS, "rl_task_v2", "rl_task_v5")


def result_row(session: LiveSession) -> dict:
    evaluation = session.last_task_result["evaluation"]
    return {
        "run_id": session.last_trace_receipt["run_id"],
        "status": evaluation["status"],
        "first_fall_time_s": session.last_trace_receipt["summary"]["first_fall_time_s"],
        "failed": [
            {"id": item["id"], "value": item["value"]}
            for item in evaluation["criteria"]
            if not item["passed"]
        ],
    }


def run_all() -> dict:
    comparison = CompareSession(default_robot(), GaitParams(), [])
    started = comparison.command({"type": "task_start", "task_id": TASK_ID})
    while comparison.sessions["track"].motion_task.active:
        comparison.advance(0.2)
    return {
        "task_id": TASK_ID,
        "group_id": started["group_id"],
        "evidence_scope": "SOFTWARE_ONLY_MUJOCO_REALIZED_SIMULATION",
        "results": {
            controller: result_row(comparison.sessions[controller])
            for controller in CONTROLLERS
        },
    }


def run_one(controller: str) -> dict:
    session = LiveSession(default_robot(), GaitParams(), [])
    if controller != session.walk_controller:
        switched = session.command({"type": "mode", "mode": "stand", "controller": controller})
        if isinstance(switched, dict) and switched.get("type") == "error":
            raise RuntimeError(switched["code"])
    started = session.command({"type": "task_start", "task_id": TASK_ID})
    if isinstance(started, dict) and started.get("type") == "error":
        raise RuntimeError(started["code"])
    while session.motion_task.active:
        session._advance_sim(0.2)
    return {
        "task_id": TASK_ID,
        "group_id": session.last_trace_receipt["group_id"],
        "evidence_scope": "SOFTWARE_ONLY_MUJOCO_REALIZED_SIMULATION",
        "results": {controller: result_row(session)},
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--controller", choices=[*SINGLE_CONTROLLERS, "all"], default="all")
    args = parser.parse_args()
    receipt = run_all() if args.controller == "all" else run_one(args.controller)
    print(json.dumps(receipt, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

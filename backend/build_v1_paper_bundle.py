"""Build one bounded V1 regression bundle using the paper-data contract.

The output is an integrity-validated REGRESSION bundle, not formal paper data.
It proves the packaging path before controller training/evaluation is scaled up.
"""

from __future__ import annotations

from datetime import datetime, timezone
import importlib.metadata
import json
from pathlib import Path
import platform
import subprocess
import sys
import uuid

import mujoco
import numpy as np

from config_schema import GaitParams, default_robot
from model_builder import build_mjcf
from paper_data_contract import artifact_record, sha256_file, validate_paper_run_bundle
from vv_oracles import run_static_double_support_oracle


BACKEND_DIR = Path(__file__).resolve().parent
REPO_ROOT = BACKEND_DIR.parent


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
        newline="\n",
    )


def _git_output(*args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    return completed.stdout.strip()


def _source_identity() -> tuple[str, bool]:
    git_sha = _git_output("rev-parse", "HEAD")
    dirty = bool(_git_output("status", "--porcelain", "--untracked-files=all"))
    return git_sha, dirty


def _environment_receipt() -> dict:
    packages = {}
    for distribution in ("mujoco", "numpy", "pydantic", "pytest"):
        try:
            packages[distribution] = importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            packages[distribution] = None
    return {
        "python": sys.version,
        "implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "packages": packages,
        "mujoco_runtime": mujoco.__version__,
        "numpy_runtime": np.__version__,
    }


def build_v1_paper_bundle(output_dir: Path) -> dict:
    """建立第一包 paper-contract regression evidence並立即 readback。"""
    output_dir = output_dir.resolve()
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(exist_ok=False)
    started_at = _utc_now()
    run_id = f"v1-regression-{datetime.now(timezone.utc):%Y%m%dt%H%M%S}-{uuid.uuid4().hex[:8]}"
    robot = default_robot()
    gait = GaitParams()
    model_xml = build_mjcf(robot, [], dynamic=True)

    result = run_static_double_support_oracle(include_raw_trace=True)
    raw_path = output_dir / "raw_oracle.json"
    _write_json(raw_path, result)

    replay_process = subprocess.run(
        [sys.executable, "-X", "utf8", str(BACKEND_DIR / "v1_replay.py"), str(raw_path)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    stdout_path = output_dir / "stdout.txt"
    stderr_path = output_dir / "stderr.txt"
    stdout_path.write_text(
        json.dumps({
            "primary_schema": result["schema_version"],
            "primary_status": result["status"],
            "criteria_passed": sum(item["passed"] for item in result["criteria"]),
            "criteria_total": len(result["criteria"]),
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )
    stderr_path.write_text(
        replay_process.stderr,
        encoding="utf-8",
        newline="\n",
    )
    if replay_process.returncode != 0:
        raise RuntimeError(
            f"process-independent replay failed with exit code {replay_process.returncode}"
        )
    replay_receipt = json.loads(replay_process.stdout)
    replay_path = output_dir / "evaluator_receipt.json"
    _write_json(replay_path, replay_receipt)

    protocol_path = output_dir / "protocol.json"
    config_path = output_dir / "resolved_config.json"
    model_path = output_dir / "model.xml"
    controller_path = output_dir / "controller.json"
    environment_path = output_dir / "environment.json"
    metrics_path = output_dir / "metrics.json"
    _write_json(protocol_path, {
        "protocol_id": "V1-STATIC-CONTACT-REGRESSION",
        "protocol_version": "3.0.0",
        "protocol_status": "FROZEN",
        "research_question_id": "RQ-MODEL-STATIC-CONTACT",
        "hypothesis_id": "H-MODEL-STATIC-CLOSURE-V3",
        "contract": result["contract"],
        "claim_boundary": result["claim_boundary"],
    })
    _write_json(config_path, {
        "robot": robot.model_dump(mode="json"),
        "gait": gait.model_dump(mode="json"),
        "obstacles": [],
        "assist_enabled": False,
    })
    model_path.write_text(model_xml, encoding="utf-8", newline="\n")
    _write_json(controller_path, {
        "controller_id": "STATIC-DOUBLE-SUPPORT-HOLD-V1",
        "controller_family": "ORACLE",
        "assist_enabled": False,
        "startup_assist_enabled": False,
    })
    _write_json(environment_path, _environment_receipt())
    _write_json(metrics_path, {
        "primary": {
            "schema_version": result["schema_version"],
            "status": result["status"],
            "metrics": result["metrics"],
            "criteria": result["criteria"],
        },
        "replay": replay_receipt,
    })

    role_files = [
        ("protocol", protocol_path, "application/json"),
        ("resolved_config", config_path, "application/json"),
        ("model", model_path, "application/xml"),
        ("controller", controller_path, "application/json"),
        ("environment", environment_path, "application/json"),
        ("raw_trace", raw_path, "application/json"),
        ("metrics", metrics_path, "application/json"),
        ("evaluator_receipt", replay_path, "application/json"),
        ("stdout", stdout_path, "text/plain"),
        ("stderr", stderr_path, "text/plain"),
    ]
    artifacts = [
        artifact_record(
            output_dir,
            path,
            role=role,
            media_type=media_type,
        )
        for role, path, media_type in role_files
    ]
    git_sha, source_dirty = _source_identity()
    completed_at = _utc_now()
    failed_criteria = [item for item in result["criteria"] if not item["passed"]]
    failures = [
        {
            "failure_type": "ORACLE_CRITERION_FAIL",
            "timestamp_s": None,
            "detail": f"{item['id']} value={item['value']} limit={item['limit']}",
        }
        for item in failed_criteria
    ]
    manifest = {
        "schema_version": "PAPER_RUN_MANIFEST_V1",
        "run_id": run_id,
        "experiment_id": "EXP-V1-MODEL-EVIDENCE-REGRESSION",
        "protocol_id": "V1-STATIC-CONTACT-REGRESSION",
        "protocol_version": "3.0.0",
        "protocol_status": "FROZEN",
        "research_question_id": "RQ-MODEL-STATIC-CONTACT",
        "hypothesis_id": "H-MODEL-STATIC-CLOSURE-V3",
        "run_class": "REGRESSION",
        "data_partition": "REGRESSION",
        "status": "COMPLETED" if result["status"] == "PASS" else "FAILED",
        "evidence_scope": "SIM_ONLY_MUJOCO",
        "claim_boundary": (
            "Static MuJoCo numerical/contact regression only. This bundle is not a formal "
            "controller comparison, physical validation, or paper result."
        ),
        "source_git_sha": git_sha,
        "source_dirty": source_dirty,
        "started_at": started_at,
        "completed_at": completed_at,
        "task_id": "V1-STATIC-DOUBLE-SUPPORT",
        "controller_family": "ORACLE",
        "controller_id": "STATIC-DOUBLE-SUPPORT-HOLD-V1",
        "metric_set_id": "V1-STATIC-CONTACT-METRICS-V3",
        "evaluator_id": "V1-RAW-REPLAY-RECEIPT-V1",
        "plant": {
            "identity_id": "HUMANOID-DESIGN-MUJOCO-V1",
            "sha256": sha256_file(model_path),
        },
        "controller": {
            "identity_id": "STATIC-DOUBLE-SUPPORT-HOLD-V1",
            "sha256": sha256_file(controller_path),
        },
        "seeds": {
            "deterministic": True,
            "training_seed": None,
            "evaluation_seed": None,
            "environment_seed": None,
            "scenario_seed": None,
            "seed_schedule_sha256": None,
        },
        "scenario": {
            "duration_s": float(result["contract"]["duration_s"]),
            "physics_dt_s": float(result["contract"]["physics_dt_s"]),
            "payload_kg": float(robot.masses.payload),
            "support_mode": "DOUBLE_SUPPORT",
        },
        "primary_outcomes": [
            "base_force_residual_relative_max",
            "base_moment_residual_relative_max",
            "joint_torque_residual_relative_max",
            "maximum_friction_utilization",
            "minimum_cop_support_margin_m",
        ],
        "secondary_outcomes": [
            "weight_balance_relative_error",
            "minimum_contact_normal_force_n",
            "mean_linear_speed_mps",
        ],
        "assist_enabled": False,
        "tuning_performed_after_freeze": False,
        "artifacts": artifacts,
        "failures": failures,
    }
    manifest_path = output_dir / "paper_run_manifest.json"
    _write_json(manifest_path, manifest)
    validation = validate_paper_run_bundle(manifest_path)
    return {
        "bundle_root": str(output_dir),
        "manifest": str(manifest_path),
        "primary_status": result["status"],
        "replay_status": replay_receipt["status"],
        "source_dirty": source_dirty,
        "validation": validation,
    }


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Build a V1 paper-contract regression bundle")
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    receipt = build_v1_paper_bundle(args.output_dir)
    print(json.dumps(receipt, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

"""Paper-data manifest, artifact inventory, and V1 bundle tests."""

from datetime import datetime, timezone
import json

import pytest
from pydantic import ValidationError

from build_v1_paper_bundle import build_v1_paper_bundle
from paper_data_contract import (
    PaperDataIntegrityError,
    PaperRunManifest,
    artifact_record,
    validate_paper_run_bundle,
)


REQUIRED_FILES = {
    "protocol": "protocol.json",
    "resolved_config": "resolved_config.json",
    "model": "model.xml",
    "controller": "controller.json",
    "environment": "environment.json",
    "raw_trace": "raw_trace.npz",
    "metrics": "metrics.json",
    "evaluator_receipt": "evaluator_receipt.json",
    "stdout": "stdout.txt",
    "stderr": "stderr.txt",
}


def _minimal_manifest(tmp_path, *, run_class="REGRESSION", source_dirty=False):
    artifacts = []
    for role, filename in REQUIRED_FILES.items():
        path = tmp_path / filename
        path.write_bytes(f"{role}\n".encode())
        artifacts.append(artifact_record(
            tmp_path,
            path,
            role=role,
            media_type="application/octet-stream",
        ))
    now = datetime.now(timezone.utc).isoformat()
    formal = run_class == "FORMAL_EVALUATION"
    return {
        "schema_version": "PAPER_RUN_MANIFEST_V1",
        "run_id": "run-paper-contract-001",
        "experiment_id": "EXP-PAPER-CONTRACT",
        "protocol_id": "PROTOCOL-PAPER-CONTRACT",
        "protocol_version": "1.0.0",
        "protocol_status": "FROZEN",
        "research_question_id": "RQ-PAPER-DATA",
        "hypothesis_id": "H-PAPER-DATA-INTEGRITY",
        "run_class": run_class,
        "data_partition": "HOLDOUT" if formal else "REGRESSION",
        "status": "COMPLETED",
        "evidence_scope": "SIM_ONLY_MUJOCO",
        "claim_boundary": "Synthetic contract fixture only; no scientific or physical claim.",
        "source_git_sha": "a" * 40,
        "source_dirty": source_dirty,
        "started_at": now,
        "completed_at": now,
        "task_id": "TASK-PAPER-CONTRACT",
        "controller_family": "LEARNING_BASED" if formal else "ORACLE",
        "controller_id": "CONTROLLER-PAPER-CONTRACT",
        "metric_set_id": "METRICS-PAPER-CONTRACT",
        "evaluator_id": "EVALUATOR-PAPER-CONTRACT",
        "plant": {"identity_id": "PLANT-PAPER-CONTRACT", "sha256": "sha256:" + "b" * 64},
        "controller": {
            "identity_id": "CONTROLLER-PAPER-CONTRACT",
            "sha256": "sha256:" + "c" * 64,
        },
        "seeds": {
            "deterministic": not formal,
            "training_seed": 101 if formal else None,
            "evaluation_seed": 201 if formal else None,
            "environment_seed": 301 if formal else None,
            "scenario_seed": 401 if formal else None,
            "seed_schedule_sha256": "sha256:" + "d" * 64 if formal else None,
        },
        "scenario": {"friction": 1.0, "payload_kg": 0.0},
        "primary_outcomes": ["task_success"],
        "secondary_outcomes": ["saturation_duty"],
        "assist_enabled": False,
        "tuning_performed_after_freeze": False,
        "artifacts": artifacts,
        "failures": [],
    }


def _write_manifest(tmp_path, payload):
    path = tmp_path / "paper_run_manifest.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_regression_bundle_validates_but_is_not_paper_ready(tmp_path):
    manifest_path = _write_manifest(tmp_path, _minimal_manifest(tmp_path))

    receipt = validate_paper_run_bundle(manifest_path)

    assert receipt["validation_status"] == "REGRESSION_BUNDLE_VALID_ONLY"
    assert receipt["paper_data_ready"] is False
    assert receipt["artifact_count"] == len(REQUIRED_FILES)


def test_formal_holdout_bundle_requires_clean_frozen_seeded_contract(tmp_path):
    manifest_path = _write_manifest(
        tmp_path,
        _minimal_manifest(tmp_path, run_class="FORMAL_EVALUATION"),
    )

    receipt = validate_paper_run_bundle(manifest_path)

    assert receipt["validation_status"] == "PAPER_DATA_READY"
    assert receipt["paper_data_ready"] is True


def test_formal_bundle_rejects_dirty_source(tmp_path):
    payload = _minimal_manifest(
        tmp_path,
        run_class="FORMAL_EVALUATION",
        source_dirty=True,
    )

    with pytest.raises(ValidationError, match="dirty source"):
        PaperRunManifest.model_validate(payload)


def test_cancelled_formal_bundle_is_retained_but_not_paper_ready(tmp_path):
    payload = _minimal_manifest(tmp_path, run_class="FORMAL_EVALUATION")
    payload["status"] = "CANCELLED"
    payload["failures"] = [{
        "failure_type": "INTERRUPTED",
        "timestamp_s": 1.0,
        "detail": "Synthetic interruption for contract testing.",
    }]
    manifest_path = _write_manifest(tmp_path, payload)

    receipt = validate_paper_run_bundle(manifest_path)

    assert receipt["validation_status"] == "FORMAL_EVALUATION_BUNDLE_VALID_ONLY"
    assert receipt["paper_data_ready"] is False


def test_bundle_rejects_tampered_artifact(tmp_path):
    manifest_path = _write_manifest(tmp_path, _minimal_manifest(tmp_path))
    (tmp_path / "metrics.json").write_text("tampered", encoding="utf-8")

    with pytest.raises(PaperDataIntegrityError, match="size mismatch|SHA-256 mismatch"):
        validate_paper_run_bundle(manifest_path)


def test_v1_oracle_builds_integrity_validated_regression_bundle(tmp_path):
    receipt = build_v1_paper_bundle(tmp_path / "v1-paper-bundle")

    assert receipt["primary_status"] == "PASS"
    assert receipt["replay_status"] == "PASS"
    assert receipt["validation"]["validation_status"] == "REGRESSION_BUNDLE_VALID_ONLY"
    assert receipt["validation"]["paper_data_ready"] is False
    assert receipt["validation"]["artifact_count"] == 10

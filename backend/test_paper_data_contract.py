"""Paper-data manifest, artifact inventory, and V1 bundle tests."""

from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

import build_v1_paper_bundle as bundle_module
from build_v1_paper_bundle import build_v1_paper_bundle
from paper_data_contract import (
    PaperDataIntegrityError,
    PaperRunManifest,
    artifact_record,
    sha256_file,
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
    manifest = json.loads(Path(receipt["manifest"]).read_text(encoding="utf-8"))
    evaluator_path = Path(receipt["bundle_root"]) / "evaluator_receipt.json"
    evaluator = json.loads(evaluator_path.read_text(encoding="utf-8"))

    assert receipt["primary_status"] == "PASS"
    assert receipt["replay_status"] == "PASS"
    assert receipt["validation"]["validation_status"] == "REGRESSION_BUNDLE_VALID_ONLY"
    assert receipt["validation"]["paper_data_ready"] is False
    assert receipt["validation"]["artifact_count"] == 10
    assert manifest["status"] == "COMPLETED"
    assert manifest["protocol_version"] == "4.0.0"
    assert manifest["metric_set_id"] == "V1-STATIC-CONTACT-METRICS-V4"
    assert manifest["evaluator_id"] == "V1-RAW-JACOBIAN-REPLAY-RECEIPT-V2"
    assert evaluator["schema_version"] == "V1_RAW_JACOBIAN_REPLAY_RECEIPT_V2"

    raw_path = Path(receipt["bundle_root"]) / "raw_oracle.json"
    raw_result = json.loads(raw_path.read_text(encoding="utf-8"))
    assert manifest["plant"]["sha256"] == raw_result["resolved_model"][
        "model_xml_sha256"
    ]
    forged = deepcopy(evaluator)
    for item in forged["criteria"]:
        item.update({
            "passed": True,
            "value": 1.0e30,
            "operator": "<=",
            "limit": -1.0e30,
        })
    forged["status"] = "PASS"
    assert bundle_module._valid_replay_receipt(
        forged,
        raw_result,
        sha256_file(raw_path),
    ) is False
    forged_claim = deepcopy(evaluator)
    forged_claim["claim_boundary"] = "PHYSICALLY_VALIDATED hardware result"
    assert bundle_module._valid_replay_receipt(
        forged_claim,
        raw_result,
        sha256_file(raw_path),
    ) is False
    overflow = deepcopy(evaluator)
    overflow["replayed_at"] = float("inf")
    assert bundle_module._valid_replay_receipt(
        overflow,
        raw_result,
        sha256_file(raw_path),
    ) is False


def test_v1_bundle_retains_replay_process_error_as_failed_bundle(tmp_path, monkeypatch):
    original_run = bundle_module.subprocess.run

    def replay_failure(args, *positional, **keyword):
        if any(str(item).endswith("v1_replay.py") for item in args):
            return bundle_module.subprocess.CompletedProcess(
                args,
                returncode=7,
                stdout="",
                stderr="synthetic replay process failure",
            )
        return original_run(args, *positional, **keyword)

    monkeypatch.setattr(bundle_module.subprocess, "run", replay_failure)
    receipt = bundle_module.build_v1_paper_bundle(tmp_path / "v1-failed-bundle")
    manifest = json.loads(Path(receipt["manifest"]).read_text(encoding="utf-8"))
    evaluator_path = Path(receipt["bundle_root"]) / "evaluator_receipt.json"
    evaluator = json.loads(evaluator_path.read_text(encoding="utf-8"))

    assert receipt["primary_status"] == "PASS"
    assert receipt["replay_status"] == "ERROR"
    assert receipt["validation"]["validation_status"] == "REGRESSION_BUNDLE_VALID_ONLY"
    assert manifest["status"] == "FAILED"
    assert manifest["failures"][0]["failure_type"] == "REPLAY_PROCESS_ERROR"
    assert evaluator["status"] == "ERROR"
    assert evaluator["return_code"] == 7
    assert (Path(receipt["bundle_root"]) / "stderr.txt").read_text(
        encoding="utf-8"
    ) == "synthetic replay process failure"


def test_v1_bundle_retains_replay_spawn_exception_as_failed_bundle(
    tmp_path,
    monkeypatch,
):
    original_run = bundle_module.subprocess.run

    def replay_exception(args, *positional, **keyword):
        if any(str(item).endswith("v1_replay.py") for item in args):
            raise OSError("synthetic replay spawn failure")
        return original_run(args, *positional, **keyword)

    monkeypatch.setattr(bundle_module.subprocess, "run", replay_exception)
    receipt = bundle_module.build_v1_paper_bundle(tmp_path / "v1-spawn-error-bundle")
    bundle_root = Path(receipt["bundle_root"])
    manifest = json.loads(Path(receipt["manifest"]).read_text(encoding="utf-8"))
    evaluator = json.loads(
        (bundle_root / "evaluator_receipt.json").read_text(encoding="utf-8")
    )

    assert receipt["primary_status"] == "PASS"
    assert receipt["replay_status"] == "ERROR"
    assert manifest["status"] == "FAILED"
    assert manifest["failures"][0]["failure_type"] == "REPLAY_PROCESS_ERROR"
    assert evaluator["error_type"] == "PROCESS_EXCEPTION"
    assert evaluator["return_code"] is None
    assert "OSError: synthetic replay spawn failure" in (
        bundle_root / "stderr.txt"
    ).read_text(encoding="utf-8")


def test_v1_bundle_fails_when_source_identity_changes_during_run(
    tmp_path,
    monkeypatch,
):
    identities = iter([("a" * 40, False), ("b" * 40, False)])
    monkeypatch.setattr(bundle_module, "_source_identity", lambda: next(identities))

    receipt = bundle_module.build_v1_paper_bundle(tmp_path / "v1-source-drift-bundle")
    bundle_root = Path(receipt["bundle_root"])
    manifest = json.loads(Path(receipt["manifest"]).read_text(encoding="utf-8"))
    environment = json.loads(
        (bundle_root / "environment.json").read_text(encoding="utf-8")
    )

    assert receipt["primary_status"] == "PASS"
    assert receipt["replay_status"] == "PASS"
    assert manifest["status"] == "FAILED"
    assert manifest["source_git_sha"] == "a" * 40
    assert any(
        item["failure_type"] == "SOURCE_IDENTITY_CHANGED_DURING_RUN"
        for item in manifest["failures"]
    )
    assert environment["source_identity"]["stable_during_run"] is False


def test_v1_bundle_retains_primary_oracle_exception_as_failed_bundle(
    tmp_path,
    monkeypatch,
):
    def primary_failure(**_keyword):
        raise RuntimeError("synthetic primary oracle failure")

    monkeypatch.setattr(
        bundle_module,
        "run_static_double_support_oracle",
        primary_failure,
    )
    receipt = bundle_module.build_v1_paper_bundle(
        tmp_path / "v1-primary-exception-bundle"
    )
    bundle_root = Path(receipt["bundle_root"])
    manifest = json.loads(Path(receipt["manifest"]).read_text(encoding="utf-8"))
    raw_receipt = json.loads(
        (bundle_root / "raw_oracle.json").read_text(encoding="utf-8")
    )
    evaluator = json.loads(
        (bundle_root / "evaluator_receipt.json").read_text(encoding="utf-8")
    )

    assert receipt["primary_status"] == "ERROR"
    assert receipt["replay_status"] == "ERROR"
    assert receipt["validation"]["validation_status"] == "REGRESSION_BUNDLE_VALID_ONLY"
    assert receipt["validation"]["artifact_count"] == 10
    assert manifest["status"] == "FAILED"
    assert manifest["failures"][0]["failure_type"] == "PRIMARY_ORACLE_EXCEPTION"
    assert raw_receipt["status"] == "ERROR"
    assert raw_receipt["error_type"] == "PRIMARY_ORACLE_EXCEPTION"
    assert raw_receipt["error_class"] == "RuntimeError"
    assert evaluator["status"] == "ERROR"
    assert evaluator["error_type"] == "PRIMARY_ORACLE_NOT_REPLAYED"
    assert evaluator["return_code"] is None
    assert (bundle_root / "stdout.txt").read_text(encoding="utf-8") == ""
    assert "RuntimeError: synthetic primary oracle failure" in (
        bundle_root / "stderr.txt"
    ).read_text(encoding="utf-8")


def test_v1_bundle_rejects_incomplete_or_forged_primary_pass(
    tmp_path,
    monkeypatch,
):
    valid = bundle_module.run_static_double_support_oracle(include_raw_trace=True)
    incomplete = deepcopy(valid)
    incomplete["criteria"] = []
    forged = deepcopy(valid)
    forged["metrics"]["forward_inverse_joint_force_norm_max"] = 1.0e30
    forged["criteria"][1]["value"] = 1.0e30
    forged["criteria"][1]["passed"] = True
    forged["status"] = "PASS"

    for name, invalid in (("missing-criteria", incomplete), ("forged-pass", forged)):
        monkeypatch.setattr(
            bundle_module,
            "run_static_double_support_oracle",
            lambda **_keyword: deepcopy(invalid),
        )
        receipt = bundle_module.build_v1_paper_bundle(tmp_path / name)
        bundle_root = Path(receipt["bundle_root"])
        manifest = json.loads(Path(receipt["manifest"]).read_text(encoding="utf-8"))
        raw_receipt = json.loads(
            (bundle_root / "raw_oracle.json").read_text(encoding="utf-8")
        )

        assert receipt["primary_status"] == "ERROR"
        assert receipt["replay_status"] == "ERROR"
        assert manifest["status"] == "FAILED"
        assert manifest["failures"][0]["failure_type"] == (
            "PRIMARY_RESULT_INVALID_RECEIPT"
        )
        assert raw_receipt["error_type"] == "PRIMARY_RESULT_INVALID_RECEIPT"


@pytest.mark.parametrize(
    ("non_finite_value", "diagnostic"),
    [
        (float("nan"), "$.metrics.synthetic=NaN"),
        (float("inf"), "$.metrics.synthetic=+Infinity"),
        (float("-inf"), "$.metrics.synthetic=-Infinity"),
    ],
    ids=["nan", "positive-infinity", "negative-infinity"],
)
def test_v1_bundle_retains_non_finite_primary_result_as_failed_bundle(
    tmp_path,
    monkeypatch,
    non_finite_value,
    diagnostic,
):
    monkeypatch.setattr(
        bundle_module,
        "run_static_double_support_oracle",
        lambda **_keyword: {
            "schema_version": "V1_STATIC_DOUBLE_SUPPORT_ORACLE_V4",
            "status": "PASS",
            "metrics": {"synthetic": non_finite_value},
            "criteria": [],
        },
    )
    receipt = bundle_module.build_v1_paper_bundle(
        tmp_path / f"v1-primary-non-finite-{diagnostic.rsplit('=', 1)[-1]}"
    )
    bundle_root = Path(receipt["bundle_root"])
    manifest = json.loads(Path(receipt["manifest"]).read_text(encoding="utf-8"))
    raw_receipt = json.loads(
        (bundle_root / "raw_oracle.json").read_text(encoding="utf-8")
    )
    evaluator = json.loads(
        (bundle_root / "evaluator_receipt.json").read_text(encoding="utf-8")
    )

    assert receipt["primary_status"] == "ERROR"
    assert receipt["replay_status"] == "ERROR"
    assert receipt["validation"]["artifact_count"] == 10
    assert manifest["status"] == "FAILED"
    assert manifest["failures"][0]["failure_type"] == "PRIMARY_RESULT_NONFINITE"
    assert raw_receipt["status"] == "ERROR"
    assert raw_receipt["error_type"] == "PRIMARY_RESULT_NONFINITE"
    assert diagnostic in raw_receipt["detail"]
    assert evaluator["status"] == "ERROR"
    assert evaluator["error_type"] == "PRIMARY_ORACLE_NOT_REPLAYED"
    assert diagnostic in (bundle_root / "stderr.txt").read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "invalid_stdout",
    ['{"status":"PASS"}', '{"status":"ERROR"}', "[]"],
)
def test_v1_bundle_rejects_incomplete_replay_stdout(
    tmp_path,
    monkeypatch,
    invalid_stdout,
):
    original_run = bundle_module.subprocess.run

    def incomplete_replay(args, *positional, **keyword):
        if any(str(item).endswith("v1_replay.py") for item in args):
            return bundle_module.subprocess.CompletedProcess(
                args,
                returncode=0,
                stdout=invalid_stdout,
                stderr="",
            )
        return original_run(args, *positional, **keyword)

    monkeypatch.setattr(bundle_module.subprocess, "run", incomplete_replay)
    receipt = bundle_module.build_v1_paper_bundle(
        tmp_path / f"v1-invalid-replay-{len(invalid_stdout)}"
    )
    manifest = json.loads(Path(receipt["manifest"]).read_text(encoding="utf-8"))
    evaluator_path = Path(receipt["bundle_root"]) / "evaluator_receipt.json"
    evaluator = json.loads(evaluator_path.read_text(encoding="utf-8"))

    assert receipt["replay_status"] == "ERROR"
    assert manifest["status"] == "FAILED"
    assert manifest["failures"][0]["failure_type"] == "REPLAY_PROCESS_ERROR"
    assert evaluator["error_type"] == "INVALID_REPLAY_RECEIPT"
    assert (Path(receipt["bundle_root"]) / "stdout.txt").read_text(
        encoding="utf-8"
    ) == invalid_stdout

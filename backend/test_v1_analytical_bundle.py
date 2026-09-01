"""Fast fail-closed tests for the V1 analytical evidence bundle builder."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess

import pytest

import build_v1_analytical_bundle as bundle_module
from paper_data_contract import (
    PaperDataIntegrityError,
    sha256_file,
    validate_paper_run_bundle,
)


EXPECTED_ROLES = {
    "protocol",
    "resolved_config",
    "model",
    "controller",
    "environment",
    "raw_trace",
    "metrics",
    "evaluator_receipt",
    "stdout",
    "stderr",
}


def _source_identity(marker: str = "a") -> dict:
    """Return a small but content-sensitive source identity receipt."""
    return {
        "git_sha": marker * 40,
        "dirty": False,
        "porcelain_sha256": "sha256:" + marker * 64,
        "tracked_diff_sha256": "sha256:" + marker * 64,
        "untracked_content_sha256": "sha256:" + marker * 64,
    }


def _model_package() -> dict:
    return {
        "schema_version": bundle_module.MODEL_PACKAGE_SCHEMA_VERSION,
        "content_sha256": "sha256:" + "1" * 64,
        "models": [],
    }


def _primary_result(*, status: str = "PASS") -> dict:
    criteria = []
    if status == "FAIL":
        criteria = [{
            "id": "SYNTHETIC_FROZEN_CRITERION",
            "passed": False,
            "value": 2.0,
            "operator": "<=",
            "limit": 1.0,
            "unit": "ratio",
        }]
    return {
        "schema_version": bundle_module.PRIMARY_SCHEMA_VERSION,
        "evidence_scope": "SIM_ONLY_MUJOCO",
        "claim_boundary": bundle_module.CLAIM_BOUNDARY,
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "case_receipts": [],
        "metrics": {"synthetic_metric": 0.0},
        "criteria": criteria,
    }


def _identity_criterion(
    criterion_id: str,
    value: float | bool,
    operator: str,
    limit: float | bool,
    unit: str,
) -> dict:
    if operator == "<=":
        passed = float(value) <= float(limit)
    else:
        passed = value == limit
    return {
        "id": criterion_id,
        "passed": passed,
        "value": value,
        "operator": operator,
        "limit": limit,
        "unit": unit,
    }


def _valid_replay_stdout(raw_path: Path, model_path: Path) -> str:
    """Mirror only the small identity envelope expected from stdlib replay."""
    primary = json.loads(raw_path.read_text(encoding="utf-8"))
    model_package = json.loads(model_path.read_text(encoding="utf-8"))
    metrics = deepcopy(primary["metrics"])
    metrics.update({
        "raw_serialized_receipt_delta_max": 0.0,
        "primary_summary_numeric_delta_max": 0.0,
        "primary_case_receipts_exact": True,
        "primary_metrics_exact": True,
        "primary_criteria_exact": True,
        "primary_status_matches_replay": True,
    })
    criteria = deepcopy(primary["criteria"])
    criteria.extend([
        _identity_criterion(
            "RAW_SERIALIZED_RECEIPT_IDENTITY",
            0.0,
            "<=",
            1.0e-12,
            "max absolute delta",
        ),
        _identity_criterion(
            "PRIMARY_CASE_RECEIPT_IDENTITY", True, "==", True, "bool"
        ),
        _identity_criterion(
            "PRIMARY_SUITE_METRIC_IDENTITY", True, "==", True, "bool"
        ),
        _identity_criterion(
            "PRIMARY_SUITE_CRITERIA_IDENTITY", True, "==", True, "bool"
        ),
        _identity_criterion(
            "PRIMARY_STATUS_IDENTITY", True, "==", True, "bool"
        ),
    ])
    receipt = {
        "schema_version": bundle_module.REPLAY_SCHEMA_VERSION,
        "source_schema_version": bundle_module.PRIMARY_SCHEMA_VERSION,
        "source_artifact_sha256": sha256_file(raw_path),
        "model_package_schema_version": bundle_module.MODEL_PACKAGE_SCHEMA_VERSION,
        "model_package_artifact_sha256": sha256_file(model_path),
        "model_package_content_sha256": model_package["content_sha256"],
        "evidence_scope": "PROCESS_INDEPENDENT_ANALYTICAL_REPLAY_ONLY",
        "claim_boundary": bundle_module.REPLAY_CLAIM_BOUNDARY,
        "replayed_at": datetime.now(timezone.utc).isoformat(),
        "status": (
            "PASS" if all(item["passed"] is True for item in criteria) else "FAIL"
        ),
        "case_receipts": deepcopy(primary["case_receipts"]),
        "metrics": metrics,
        "criteria": criteria,
    }
    return json.dumps(receipt, allow_nan=False)


@pytest.fixture
def synthetic_pipeline(monkeypatch):
    """Install tiny deterministic model/primary/replay substitutes."""

    def install(
        *,
        primary: dict | None = None,
        primary_error: BaseException | None = None,
        replay_mode: str = "valid",
        source_identities: list[dict] | None = None,
    ) -> None:
        identities = iter(source_identities or [_source_identity(), _source_identity()])
        monkeypatch.setattr(bundle_module, "_source_identity", lambda: next(identities))
        monkeypatch.setattr(
            bundle_module,
            "build_analytical_model_package",
            lambda: _model_package(),
        )
        monkeypatch.setattr(
            bundle_module,
            "validate_analytical_model_package",
            lambda _value: None,
        )

        def run_primary(*, model_package):
            assert model_package == _model_package()
            if primary_error is not None:
                raise primary_error
            return deepcopy(primary if primary is not None else _primary_result())

        monkeypatch.setattr(bundle_module, "run_analytical_suite", run_primary)
        monkeypatch.setattr(
            bundle_module,
            "validate_primary_result",
            lambda _primary, _model: None,
        )

        def run_replay(args, **_keyword):
            raw_path = Path(args[-2])
            model_path = Path(args[-1])
            if replay_mode == "interrupt":
                raise KeyboardInterrupt("synthetic replay cancellation")
            if replay_mode == "exception":
                raise OSError("synthetic replay spawn failure")
            if replay_mode == "nonzero":
                return subprocess.CompletedProcess(
                    args,
                    returncode=7,
                    stdout="partial replay output",
                    stderr="synthetic replay process failure",
                )
            if replay_mode == "invalid_receipt":
                return subprocess.CompletedProcess(
                    args,
                    returncode=0,
                    stdout=json.dumps({"status": "PASS"}),
                    stderr="",
                )
            assert replay_mode == "valid"
            return subprocess.CompletedProcess(
                args,
                returncode=0,
                stdout=_valid_replay_stdout(raw_path, model_path),
                stderr="",
            )

        monkeypatch.setattr(bundle_module.subprocess, "run", run_replay)

    return install


def _read_bundle(receipt: dict) -> tuple[Path, dict]:
    root = Path(receipt["bundle_root"])
    manifest = json.loads(Path(receipt["manifest"]).read_text(encoding="utf-8"))
    return root, manifest


def test_successful_bundle_has_ten_roles_and_passes_paper_validator(
    tmp_path,
    synthetic_pipeline,
):
    synthetic_pipeline()
    receipt = bundle_module.build_v1_analytical_bundle(tmp_path / "bundle")
    root, manifest = _read_bundle(receipt)

    assert receipt["primary_status"] == "PASS"
    assert receipt["replay_status"] == "PASS"
    assert receipt["validation"]["validation_status"] == (
        "REGRESSION_BUNDLE_VALID_ONLY"
    )
    assert receipt["validation"]["paper_data_ready"] is False
    assert receipt["validation"]["artifact_count"] == 10
    assert manifest["status"] == "COMPLETED"
    assert manifest["failures"] == []
    assert {item["role"] for item in manifest["artifacts"]} == EXPECTED_ROLES
    assert receipt["validation"] == validate_paper_run_bundle(
        root / "paper_run_manifest.json"
    )
    # The fixture must stay lightweight and never regenerate the large physics trace.
    assert receipt["validation"]["artifact_bytes"] < 100_000


def test_existing_output_directory_is_not_overwritten(tmp_path, synthetic_pipeline):
    synthetic_pipeline()
    output_dir = tmp_path / "existing"
    output_dir.mkdir()
    sentinel = output_dir / "user-content.txt"
    sentinel.write_text("preserve me", encoding="utf-8")

    with pytest.raises(FileExistsError):
        bundle_module.build_v1_analytical_bundle(output_dir)

    assert sentinel.read_text(encoding="utf-8") == "preserve me"
    assert list(output_dir.iterdir()) == [sentinel]


def test_primary_exception_is_retained_as_failed_bundle(tmp_path, synthetic_pipeline):
    synthetic_pipeline(primary_error=RuntimeError("synthetic primary failure"))
    receipt = bundle_module.build_v1_analytical_bundle(tmp_path / "bundle")
    root, manifest = _read_bundle(receipt)
    raw = json.loads((root / "raw_suite.json").read_text(encoding="utf-8"))

    assert receipt["primary_status"] == "ERROR"
    assert receipt["replay_status"] == "ERROR"
    assert manifest["status"] == "FAILED"
    assert manifest["failures"][0]["failure_type"] == "PRIMARY_SUITE_EXCEPTION"
    assert raw["error_type"] == "PRIMARY_SUITE_EXCEPTION"
    assert raw["error_class"] == "RuntimeError"
    assert "synthetic primary failure" in (root / "stderr.txt").read_text(
        encoding="utf-8"
    )


def test_nonfinite_primary_is_rejected_without_writing_nan(
    tmp_path,
    synthetic_pipeline,
):
    primary = _primary_result()
    primary["metrics"]["nonfinite"] = float("nan")
    synthetic_pipeline(primary=primary)
    receipt = bundle_module.build_v1_analytical_bundle(tmp_path / "bundle")
    root, manifest = _read_bundle(receipt)
    raw_text = (root / "raw_suite.json").read_text(encoding="utf-8")
    raw = json.loads(raw_text)

    assert manifest["status"] == "FAILED"
    assert manifest["failures"][0]["failure_type"] == "PRIMARY_RESULT_NONFINITE"
    assert raw["error_type"] == "PRIMARY_RESULT_NONFINITE"
    assert "$.metrics.nonfinite=NaN" in raw["detail"]
    assert '"NaN"' not in raw_text


def test_primary_fail_and_negative_criterion_are_preserved(
    tmp_path,
    synthetic_pipeline,
):
    synthetic_pipeline(primary=_primary_result(status="FAIL"))
    receipt = bundle_module.build_v1_analytical_bundle(tmp_path / "bundle")
    root, manifest = _read_bundle(receipt)
    raw = json.loads((root / "raw_suite.json").read_text(encoding="utf-8"))

    assert receipt["primary_status"] == "FAIL"
    assert receipt["replay_status"] == "FAIL"
    assert manifest["status"] == "FAILED"
    assert raw["criteria"][0]["passed"] is False
    failure_types = {item["failure_type"] for item in manifest["failures"]}
    assert "PRIMARY_SUITE_CRITERION_FAIL" in failure_types
    assert "REPLAY_SUITE_CRITERION_FAIL" in failure_types


def test_replay_nonzero_process_is_retained_as_failed_bundle(
    tmp_path,
    synthetic_pipeline,
):
    synthetic_pipeline(replay_mode="nonzero")
    receipt = bundle_module.build_v1_analytical_bundle(tmp_path / "bundle")
    root, manifest = _read_bundle(receipt)
    replay = json.loads(
        (root / "evaluator_receipt.json").read_text(encoding="utf-8")
    )

    assert receipt["primary_status"] == "PASS"
    assert receipt["replay_status"] == "ERROR"
    assert manifest["status"] == "FAILED"
    assert manifest["failures"][0]["failure_type"] == (
        "REPLAY_PROCESS_EXIT_NONZERO"
    )
    assert replay["return_code"] == 7
    assert (root / "stdout.txt").read_text(encoding="utf-8") == (
        "partial replay output"
    )
    assert "synthetic replay process failure" in (root / "stderr.txt").read_text(
        encoding="utf-8"
    )


def test_incomplete_replay_receipt_is_rejected(tmp_path, synthetic_pipeline):
    synthetic_pipeline(replay_mode="invalid_receipt")
    receipt = bundle_module.build_v1_analytical_bundle(tmp_path / "bundle")
    root, manifest = _read_bundle(receipt)
    replay = json.loads(
        (root / "evaluator_receipt.json").read_text(encoding="utf-8")
    )

    assert receipt["replay_status"] == "ERROR"
    assert manifest["status"] == "FAILED"
    assert manifest["failures"][0]["failure_type"] == "REPLAY_RECEIPT_INVALID"
    assert replay["error_type"] == "REPLAY_RECEIPT_INVALID"
    assert (root / "stdout.txt").read_text(encoding="utf-8") == '{"status": "PASS"}'


def test_source_identity_drift_fails_closed(tmp_path, synthetic_pipeline):
    synthetic_pipeline(source_identities=[_source_identity("a"), _source_identity("b")])
    receipt = bundle_module.build_v1_analytical_bundle(tmp_path / "bundle")
    root, manifest = _read_bundle(receipt)
    environment = json.loads(
        (root / "environment.json").read_text(encoding="utf-8")
    )

    assert receipt["primary_status"] == "PASS"
    assert receipt["replay_status"] == "PASS"
    assert manifest["status"] == "FAILED"
    assert environment["source_identity"]["stable_during_run"] is False
    assert any(
        item["failure_type"] == "SOURCE_IDENTITY_CHANGED_DURING_RUN"
        for item in manifest["failures"]
    )


@pytest.mark.parametrize("phase", ["primary", "replay"])
def test_keyboard_interrupt_produces_cancelled_bundle(
    tmp_path,
    synthetic_pipeline,
    phase,
):
    if phase == "primary":
        synthetic_pipeline(primary_error=KeyboardInterrupt("synthetic cancellation"))
    else:
        synthetic_pipeline(replay_mode="interrupt")
    receipt = bundle_module.build_v1_analytical_bundle(tmp_path / phase)
    root, manifest = _read_bundle(receipt)

    assert manifest["status"] == "CANCELLED"
    assert any(
        item["failure_type"]
        == ("PRIMARY_SUITE_CANCELLED" if phase == "primary" else "REPLAY_CANCELLED")
        for item in manifest["failures"]
    )
    assert "KeyboardInterrupt" in (root / "stderr.txt").read_text(encoding="utf-8")


@pytest.mark.parametrize("artifact_name", ["protocol.json", "models.json"])
def test_paper_validator_rejects_same_size_artifact_and_model_hash_tamper(
    tmp_path,
    synthetic_pipeline,
    artifact_name,
):
    synthetic_pipeline()
    receipt = bundle_module.build_v1_analytical_bundle(tmp_path / artifact_name)
    root, _manifest = _read_bundle(receipt)
    artifact_path = root / artifact_name
    original = artifact_path.read_bytes()
    tampered = bytes([original[0] ^ 1]) + original[1:]
    assert len(tampered) == len(original)
    artifact_path.write_bytes(tampered)

    with pytest.raises(PaperDataIntegrityError, match="SHA-256 mismatch"):
        validate_paper_run_bundle(root / "paper_run_manifest.json")

"""Fail-closed experiment-matrix completeness contract tests."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

import pytest
from pydantic import ValidationError

import experiment_matrix_contract as matrix_module
from experiment_matrix_contract import (
    ExpectedCell,
    ExperimentMatrixSpec,
    FROZEN_CLAIM_BOUNDARY,
    MatrixIntegrityError,
    expected_seed_schedule_sha256,
    validate_experiment_matrix,
)
from paper_data_contract import artifact_record, sha256_file


CLAIM_BOUNDARY = FROZEN_CLAIM_BOUNDARY
PROTOCOL_BYTES = b'{"protocol":"frozen-matrix-v1"}\n'
ENVIRONMENT_BYTES = b'{"environment":"synthetic-contract-fixture"}\n'
MODEL_BYTES = b"<mujoco model='synthetic-matrix-contract'/>\n"


def _sha256_bytes(payload: bytes) -> str:
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _controller_bytes(controller_id: str) -> bytes:
    return json.dumps(
        {"controller_id": controller_id},
        sort_keys=True,
        separators=(",", ":"),
    ).encode() + b"\n"


def _resolved_config_bytes(cell_id: str) -> bytes:
    return json.dumps(
        {"cell_id": cell_id, "physics_step_s": 0.002},
        sort_keys=True,
        separators=(",", ":"),
    ).encode() + b"\n"


def _cell(
    cell_id: str,
    evaluation_seed: int,
    *,
    scenario_id: str = "SCENARIO-NOMINAL",
    payload_kg: float = 0.0,
    controller_id: str = "PPO-CONTRACT-V1",
) -> dict:
    return {
        "cell_id": cell_id,
        "scenario_id": scenario_id,
        "replicate_id": f"REPLICATE-{evaluation_seed}",
        "controller_family": "LEARNING_BASED",
        "controller": {
            "identity_id": controller_id,
            "sha256": _sha256_bytes(_controller_bytes(controller_id)),
        },
        "deterministic": False,
        "training_seed": 101,
        "evaluation_seed": evaluation_seed,
        "environment_seed": evaluation_seed + 1000,
        "scenario_seed": evaluation_seed + 2000,
        "resolved_config_sha256": _sha256_bytes(_resolved_config_bytes(cell_id)),
        "scenario": {
            "friction": 1.0,
            "payload_kg": payload_kg,
            "terrain": "flat",
        },
    }


def _spec(cells: list[dict]) -> dict:
    payload = {
        "schema_version": "EXPERIMENT_MATRIX_SPEC_V1",
        "matrix_id": "MATRIX-STUDY-A-CONTRACT",
        "matrix_version": "1.0.0",
        "experiment_id": "EXP-STUDY-A-CONTRACT",
        "protocol_id": "PROTOCOL-STUDY-A-CONTRACT",
        "protocol_version": "1.0.0",
        "protocol_status": "FROZEN",
        "research_question_id": "RQ-STUDY-A-CONTRACT",
        "hypothesis_id": "H-STUDY-A-CONTRACT",
        "run_class": "FORMAL_EVALUATION",
        "data_partition": "HOLDOUT",
        "evidence_scope": "SIM_ONLY_MUJOCO",
        "claim_boundary": CLAIM_BOUNDARY,
        "source_git_sha": "a" * 40,
        "source_dirty": False,
        "task_id": "TASK-STAND-WALK-STOP",
        "plant": {
            "identity_id": "PLANT-CONTRACT-V1",
            "sha256": _sha256_bytes(MODEL_BYTES),
        },
        "protocol_artifact_sha256": _sha256_bytes(PROTOCOL_BYTES),
        "environment_artifact_sha256": _sha256_bytes(ENVIRONMENT_BYTES),
        "metric_set_id": "METRICS-STUDY-A-V1",
        "evaluator_id": "EVALUATOR-STUDY-A-V1",
        "seed_schedule_sha256": "sha256:" + "0" * 64,
        "primary_outcomes": ["task_success"],
        "secondary_outcomes": ["saturation_duty"],
        "assist_enabled": False,
        "tuning_performed_after_freeze": False,
        "failure_semantics_id": "MATRIX_FAILURE_RETENTION_V1",
        "expected_cell_count": len(cells),
        "expected_cells": cells,
    }
    payload["seed_schedule_sha256"] = expected_seed_schedule_sha256(
        payload["matrix_id"],
        payload["matrix_version"],
        [ExpectedCell.model_validate(cell) for cell in cells],
    )
    return payload


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
            sort_keys=True,
        ) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _write_run_bundle(
    root: Path,
    spec: dict,
    cell: dict,
    *,
    run_id: str,
    status: str = "COMPLETED",
) -> dict:
    run_root = root / "runs" / run_id
    run_root.mkdir(parents=True)
    files = {
        "protocol": ("protocol.json", PROTOCOL_BYTES),
        "resolved_config": (
            "resolved_config.json",
            _resolved_config_bytes(cell["cell_id"]),
        ),
        "model": ("model.xml", MODEL_BYTES),
        "controller": (
            "controller.json",
            _controller_bytes(cell["controller"]["identity_id"]),
        ),
        "environment": ("environment.json", ENVIRONMENT_BYTES),
        "raw_trace": ("raw_trace.bin", b"synthetic raw trace\n"),
        "metrics": ("metrics.json", b'{"metric_value":null}\n'),
        "evaluator_receipt": (
            "evaluator_receipt.json",
            b'{"status":"SYNTHETIC_CONTRACT_ONLY"}\n',
        ),
        "stdout": ("stdout.txt", b""),
        "stderr": ("stderr.txt", b""),
    }
    artifacts = []
    for role, (filename, content) in files.items():
        path = run_root / filename
        path.write_bytes(content)
        artifacts.append(artifact_record(
            run_root,
            path,
            role=role,
            media_type="application/octet-stream",
        ))

    failures = []
    if status in {"FAILED", "CANCELLED"}:
        failures.append({
            "failure_type": f"SYNTHETIC_{status}",
            "timestamp_s": 1.0,
            "detail": "Synthetic terminal status retained for contract verification.",
        })
    manifest = {
        "schema_version": "PAPER_RUN_MANIFEST_V1",
        "run_id": run_id,
        "experiment_id": spec["experiment_id"],
        "protocol_id": spec["protocol_id"],
        "protocol_version": spec["protocol_version"],
        "protocol_status": spec["protocol_status"],
        "research_question_id": spec["research_question_id"],
        "hypothesis_id": spec["hypothesis_id"],
        "run_class": spec["run_class"],
        "data_partition": spec["data_partition"],
        "status": status,
        "evidence_scope": spec["evidence_scope"],
        "claim_boundary": spec["claim_boundary"],
        "source_git_sha": spec["source_git_sha"],
        "source_dirty": spec["source_dirty"],
        "started_at": "2026-09-03T00:00:00+00:00",
        "completed_at": "2026-09-03T00:00:01+00:00",
        "task_id": spec["task_id"],
        "controller_family": cell["controller_family"],
        "controller_id": cell["controller"]["identity_id"],
        "metric_set_id": spec["metric_set_id"],
        "evaluator_id": spec["evaluator_id"],
        "plant": spec["plant"],
        "controller": cell["controller"],
        "seeds": {
            "deterministic": cell["deterministic"],
            "training_seed": cell["training_seed"],
            "evaluation_seed": cell["evaluation_seed"],
            "environment_seed": cell["environment_seed"],
            "scenario_seed": cell["scenario_seed"],
            "seed_schedule_sha256": spec["seed_schedule_sha256"],
        },
        "scenario": cell["scenario"],
        "primary_outcomes": spec["primary_outcomes"],
        "secondary_outcomes": spec["secondary_outcomes"],
        "assist_enabled": spec["assist_enabled"],
        "tuning_performed_after_freeze": spec[
            "tuning_performed_after_freeze"
        ],
        "artifacts": artifacts,
        "failures": failures,
    }
    manifest_path = run_root / "paper_run_manifest.json"
    _write_json(manifest_path, manifest)
    return {
        "cell_id": cell["cell_id"],
        "run_id": run_id,
        "path": manifest_path.relative_to(root).as_posix(),
        "bytes": manifest_path.stat().st_size,
        "sha256": sha256_file(manifest_path),
    }


def _write_matrix(
    root: Path,
    spec: dict,
    references: list[dict],
) -> tuple[Path, Path]:
    spec_path = root / "experiment_matrix.json"
    index_path = root / "experiment_matrix_run_index.json"
    _write_json(spec_path, spec)
    _write_json(index_path, {
        "schema_version": "EXPERIMENT_MATRIX_RUN_INDEX_V1",
        "matrix_id": spec["matrix_id"],
        "matrix_spec_sha256": sha256_file(spec_path),
        "run_manifests": references,
    })
    return spec_path, index_path


def _rewrite_reference(root: Path, reference: dict, manifest: dict) -> dict:
    manifest_path = root / reference["path"]
    _write_json(manifest_path, manifest)
    updated = deepcopy(reference)
    updated["bytes"] = manifest_path.stat().st_size
    updated["sha256"] = sha256_file(manifest_path)
    return updated


def test_complete_matrix_retains_failed_cancelled_and_null_artifact(tmp_path):
    cells = [_cell(f"CELL-{seed}", seed) for seed in (201, 202, 203)]
    spec = _spec(cells)
    references = [
        _write_run_bundle(
            tmp_path,
            spec,
            cell,
            run_id=f"run-matrix-{cell['evaluation_seed']}",
            status=status,
        )
        for cell, status in zip(cells, ("COMPLETED", "FAILED", "CANCELLED"))
    ]
    spec_path, index_path = _write_matrix(tmp_path, spec, references)

    first = validate_experiment_matrix(spec_path, index_path)
    second = validate_experiment_matrix(spec_path, index_path)

    assert first == second
    assert first["validation_status"] == "MATRIX_COMPLETE"
    assert first["matrix_complete"] is True
    assert first["paper_data_ready"] is False
    assert first["statistics_input_ready"] is False
    assert first["run_status_counts"] == {
        "COMPLETED": 1,
        "FAILED": 1,
        "CANCELLED": 1,
    }
    assert first["failed_cells"] == [{
        "cell_id": "CELL-202",
        "run_id": "run-matrix-202",
    }]
    assert first["cancelled_cells"] == [{
        "cell_id": "CELL-203",
        "run_id": "run-matrix-203",
    }]
    assert [item["id"] for item in first["criteria"]] == [
        f"MX-{index:02d}" for index in range(1, 11)
    ]
    metrics = tmp_path / "runs" / "run-matrix-201" / "metrics.json"
    assert json.loads(metrics.read_text(encoding="utf-8"))["metric_value"] is None


def test_missing_expected_cell_returns_incomplete_receipt(tmp_path):
    cells = [_cell("CELL-201", 201), _cell("CELL-202", 202)]
    spec = _spec(cells)
    reference = _write_run_bundle(
        tmp_path,
        spec,
        cells[0],
        run_id="run-matrix-201",
    )
    spec_path, index_path = _write_matrix(tmp_path, spec, [reference])

    receipt = validate_experiment_matrix(spec_path, index_path)

    assert receipt["matrix_complete"] is False
    assert receipt["declared_missing_cells"] == ["CELL-202"]
    assert receipt["unvalidated_expected_cells"] == ["CELL-202"]


def test_completed_and_failed_cells_are_statistics_handoff_eligible(tmp_path):
    cells = [_cell("CELL-201", 201), _cell("CELL-202", 202)]
    spec = _spec(cells)
    references = [
        _write_run_bundle(
            tmp_path,
            spec,
            cell,
            run_id=f"run-matrix-{cell['evaluation_seed']}",
            status=status,
        )
        for cell, status in zip(cells, ("COMPLETED", "FAILED"))
    ]
    spec_path, index_path = _write_matrix(tmp_path, spec, references)

    receipt = validate_experiment_matrix(spec_path, index_path)

    assert receipt["matrix_complete"] is True
    assert receipt["statistics_input_ready"] is True
    assert receipt["run_status_counts"]["FAILED"] == 1


def test_duplicate_cell_path_and_run_id_fail_closed(tmp_path):
    cell = _cell("CELL-201", 201)
    spec = _spec([cell])
    reference = _write_run_bundle(
        tmp_path,
        spec,
        cell,
        run_id="run-matrix-201",
    )
    spec_path, index_path = _write_matrix(
        tmp_path,
        spec,
        [reference, deepcopy(reference)],
    )

    receipt = validate_experiment_matrix(spec_path, index_path)

    assert receipt["matrix_complete"] is False
    assert receipt["duplicate_cells"] == ["CELL-201"]
    assert receipt["duplicate_run_ids"] == ["run-matrix-201"]
    assert receipt["duplicate_manifest_paths"] == [reference["path"]]


def test_unexpected_cell_is_not_silently_accepted(tmp_path):
    expected = _cell("CELL-201", 201)
    unexpected = _cell("CELL-999", 999, scenario_id="SCENARIO-UNEXPECTED")
    spec = _spec([expected])
    references = [
        _write_run_bundle(tmp_path, spec, expected, run_id="run-matrix-201"),
        _write_run_bundle(tmp_path, spec, unexpected, run_id="run-matrix-999"),
    ]
    spec_path, index_path = _write_matrix(tmp_path, spec, references)

    receipt = validate_experiment_matrix(spec_path, index_path)

    assert receipt["matrix_complete"] is False
    assert receipt["unexpected_cells"] == ["CELL-999"]
    unexpected_receipt = next(
        item for item in receipt["cell_receipts"] if item["cell_id"] == "CELL-999"
    )
    assert unexpected_receipt["identity_valid"] is False


def test_unindexed_manifest_in_dedicated_root_fails_closed(tmp_path):
    expected = _cell("CELL-201", 201)
    unindexed = _cell("CELL-999", 999, scenario_id="SCENARIO-UNINDEXED")
    spec = _spec([expected])
    reference = _write_run_bundle(
        tmp_path,
        spec,
        expected,
        run_id="run-matrix-201",
    )
    _write_run_bundle(
        tmp_path,
        spec,
        unindexed,
        run_id="run-matrix-unindexed",
    )
    spec_path, index_path = _write_matrix(tmp_path, spec, [reference])

    receipt = validate_experiment_matrix(spec_path, index_path)

    assert receipt["matrix_complete"] is False
    assert receipt["unindexed_manifest_paths"] == [
        "runs/run-matrix-unindexed/paper_run_manifest.json"
    ]


def test_tampered_artifact_is_invalid_not_skipped(tmp_path):
    cell = _cell("CELL-201", 201)
    spec = _spec([cell])
    reference = _write_run_bundle(
        tmp_path,
        spec,
        cell,
        run_id="run-matrix-201",
    )
    spec_path, index_path = _write_matrix(tmp_path, spec, [reference])
    (tmp_path / "runs" / "run-matrix-201" / "metrics.json").write_text(
        "tampered",
        encoding="utf-8",
    )

    receipt = validate_experiment_matrix(spec_path, index_path)

    assert receipt["matrix_complete"] is False
    assert receipt["integrity_valid_run_count"] == 0
    assert receipt["unvalidated_expected_cells"] == ["CELL-201"]
    assert receipt["invalid_references"][0]["cell_id"] == "CELL-201"
    assert "mismatch" in receipt["invalid_references"][0]["error"]


@pytest.mark.parametrize(
    ("field", "replacement", "receipt_field"),
    [
        ("source_git_sha", "b" * 40, "source_git_sha"),
        ("scenario.payload_kg", 9.0, "scenario"),
        ("seeds.evaluation_seed", 777, "seeds.evaluation_seed"),
    ],
)
def test_common_or_cell_identity_drift_is_reported(
    tmp_path,
    field,
    replacement,
    receipt_field,
):
    cell = _cell("CELL-201", 201)
    spec = _spec([cell])
    reference = _write_run_bundle(
        tmp_path,
        spec,
        cell,
        run_id="run-matrix-201",
    )
    manifest_path = tmp_path / reference["path"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if field == "source_git_sha":
        manifest[field] = replacement
    elif field == "scenario.payload_kg":
        manifest["scenario"]["payload_kg"] = replacement
    else:
        manifest["seeds"]["evaluation_seed"] = replacement
    reference = _rewrite_reference(tmp_path, reference, manifest)
    spec_path, index_path = _write_matrix(tmp_path, spec, [reference])

    receipt = validate_experiment_matrix(spec_path, index_path)

    assert receipt["matrix_complete"] is False
    assert receipt["unvalidated_expected_cells"] == ["CELL-201"]
    assert receipt_field in {
        item["field"] for item in receipt["identity_mismatches"]
    }


def test_spec_hash_mismatch_is_structural_error(tmp_path):
    cell = _cell("CELL-201", 201)
    spec = _spec([cell])
    spec_path, index_path = _write_matrix(tmp_path, spec, [])
    index = json.loads(index_path.read_text(encoding="utf-8"))
    index["matrix_spec_sha256"] = "sha256:" + "0" * 64
    _write_json(index_path, index)

    with pytest.raises(MatrixIntegrityError, match="spec SHA-256 mismatch"):
        validate_experiment_matrix(spec_path, index_path)


@pytest.mark.parametrize("invalid_kind", ["path-escape", "unknown-field"])
def test_index_and_spec_schema_fail_closed(tmp_path, invalid_kind):
    cell = _cell("CELL-201", 201)
    spec = _spec([cell])
    reference = _write_run_bundle(
        tmp_path,
        spec,
        cell,
        run_id="run-matrix-201",
    )
    if invalid_kind == "path-escape":
        reference["path"] = "../paper_run_manifest.json"
    else:
        spec["unexpected_field"] = True
    spec_path, index_path = _write_matrix(tmp_path, spec, [reference])

    with pytest.raises(MatrixIntegrityError, match="invalid experiment_matrix"):
        validate_experiment_matrix(spec_path, index_path)


@pytest.mark.parametrize("invalid_kind", ["duplicate-key", "nan"])
def test_strict_json_rejects_duplicate_keys_and_nan(tmp_path, invalid_kind):
    cell = _cell("CELL-201", 201)
    spec = _spec([cell])
    spec_path, index_path = _write_matrix(tmp_path, spec, [])
    if invalid_kind == "duplicate-key":
        spec_path.write_text(
            '{"schema_version":"EXPERIMENT_MATRIX_SPEC_V1",'
            '"schema_version":"EXPERIMENT_MATRIX_SPEC_V1"}',
            encoding="utf-8",
        )
        pattern = "duplicate JSON key"
    else:
        raw = spec_path.read_text(encoding="utf-8").replace(
            '"payload_kg": 0.0',
            '"payload_kg": NaN',
        )
        spec_path.write_text(raw, encoding="utf-8")
        pattern = "non-finite"

    with pytest.raises(MatrixIntegrityError, match=pattern):
        validate_experiment_matrix(spec_path, index_path)


def test_spec_rejects_duplicate_logical_cell_and_scenario_label_drift():
    first = _cell("CELL-201", 201)
    duplicate = deepcopy(first)
    duplicate.update({
        "cell_id": "CELL-DUPLICATE",
        "scenario_id": "SCENARIO-RENAMED",
        "replicate_id": "REPLICATE-RENAMED",
    })
    with pytest.raises(ValidationError, match="logical cell tuple"):
        ExperimentMatrixSpec.model_validate(_spec([first, duplicate]))

    changed = _cell("CELL-202", 202)
    changed["scenario"]["payload_kg"] = 5.0
    with pytest.raises(ValidationError, match="相同 scenario_id"):
        ExperimentMatrixSpec.model_validate(_spec([first, changed]))


@pytest.mark.parametrize(
    ("first_value", "second_value"),
    [(0, 0.0), (0.0, -0.0)],
    ids=["int-float-equivalence", "signed-zero-equivalence"],
)
def test_numeric_equivalent_scenarios_cannot_bypass_duplicate_cell_gate(
    first_value,
    second_value,
):
    first = _cell("CELL-201", 201, payload_kg=first_value)
    duplicate = deepcopy(first)
    duplicate.update({
        "cell_id": "CELL-DUPLICATE",
        "scenario_id": "SCENARIO-RENAMED",
        "replicate_id": "REPLICATE-RENAMED",
    })
    duplicate["scenario"]["payload_kg"] = second_value
    spec = _spec([first, duplicate])

    with pytest.raises(ValidationError, match="logical cell tuple"):
        ExperimentMatrixSpec.model_validate(spec)


def test_boolean_and_numeric_scenario_values_remain_type_distinct(tmp_path):
    cell = _cell("CELL-201", 201)
    cell["scenario"]["feature_enabled"] = 1
    spec = _spec([cell])
    reference = _write_run_bundle(
        tmp_path,
        spec,
        cell,
        run_id="run-matrix-201",
    )
    manifest_path = tmp_path / reference["path"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["scenario"]["feature_enabled"] = True
    reference = _rewrite_reference(tmp_path, reference, manifest)
    spec_path, index_path = _write_matrix(tmp_path, spec, [reference])

    receipt = validate_experiment_matrix(spec_path, index_path)

    assert receipt["matrix_complete"] is False
    assert {item["field"] for item in receipt["identity_mismatches"]} == {
        "scenario"
    }


def test_seed_schedule_hash_is_derived_from_expected_cells():
    spec = _spec([_cell("CELL-201", 201)])
    spec["seed_schedule_sha256"] = "sha256:" + "d" * 64

    with pytest.raises(ValidationError, match="canonical expected cells"):
        ExperimentMatrixSpec.model_validate(spec)


def test_claim_boundary_is_exact_and_cannot_include_contradictory_claims():
    spec = _spec([_cell("CELL-201", 201)])
    spec["claim_boundary"] += " PHYSICALLY_VALIDATED and safe."

    with pytest.raises(ValidationError, match="frozen bounded wording"):
        ExperimentMatrixSpec.model_validate(spec)


def test_outcome_ids_are_bounded():
    spec = _spec([_cell("CELL-201", 201)])
    spec["primary_outcomes"] = [""]

    with pytest.raises(ValidationError, match="bounded ID"):
        ExperimentMatrixSpec.model_validate(spec)


def test_spec_rejects_null_or_nonfinite_required_cell_values():
    cell = _cell("CELL-201", 201)
    cell["evaluation_seed"] = None
    with pytest.raises(ValidationError):
        ExperimentMatrixSpec.model_validate(_spec([cell]))

    cell = _cell("CELL-201", 201)
    cell["scenario"]["payload_kg"] = float("nan")
    with pytest.raises(ValidationError):
        ExperimentMatrixSpec.model_validate(_spec([cell]))


def test_cli_returns_nonzero_and_machine_receipt_for_incomplete_matrix(
    tmp_path,
    monkeypatch,
    capsys,
):
    cell = _cell("CELL-201", 201)
    spec = _spec([cell])
    spec_path, index_path = _write_matrix(tmp_path, spec, [])
    monkeypatch.setattr(
        sys,
        "argv",
        ["experiment_matrix_contract.py", str(spec_path), str(index_path)],
    )

    with pytest.raises(SystemExit) as exc_info:
        matrix_module.main()

    assert exc_info.value.code == 1
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["validation_status"] == "MATRIX_INCOMPLETE"
    assert receipt["matrix_complete"] is False


def test_dedicated_root_and_no_follow_scan_are_fail_closed(
    tmp_path,
    monkeypatch,
):
    cell = _cell("CELL-201", 201)
    spec = _spec([cell])
    reference = _write_run_bundle(
        tmp_path,
        spec,
        cell,
        run_id="run-matrix-201",
    )
    spec_path, index_path = _write_matrix(tmp_path, spec, [reference])
    (tmp_path / ".git").mkdir()
    with pytest.raises(MatrixIntegrityError, match="dedicated bounded"):
        validate_experiment_matrix(spec_path, index_path)
    (tmp_path / ".git").rmdir()

    monkeypatch.setattr(
        matrix_module,
        "_is_link_or_junction",
        lambda path: path.name == "runs",
    )
    with pytest.raises(MatrixIntegrityError, match="symlink/junction"):
        validate_experiment_matrix(spec_path, index_path)


def test_case_variant_manifest_filename_is_fail_closed(tmp_path):
    cell = _cell("CELL-201", 201)
    spec = _spec([cell])
    reference = _write_run_bundle(
        tmp_path,
        spec,
        cell,
        run_id="run-matrix-201",
    )
    spec_path, index_path = _write_matrix(tmp_path, spec, [reference])
    shadow_root = tmp_path / "runs" / "case-variant-shadow"
    shadow_root.mkdir(parents=True)
    (shadow_root / "PAPER_RUN_MANIFEST.JSON").write_text("{}", encoding="utf-8")

    with pytest.raises(MatrixIntegrityError, match="noncanonical.*casing"):
        validate_experiment_matrix(spec_path, index_path)


def test_cli_wraps_pathological_json_as_machine_error_receipt(
    tmp_path,
    monkeypatch,
    capsys,
):
    cell = _cell("CELL-201", 201)
    spec = _spec([cell])
    spec_path, index_path = _write_matrix(tmp_path, spec, [])
    raw_spec = spec_path.read_text(encoding="utf-8")
    marker = '"expected_cell_count": 1,'
    assert marker in raw_spec
    spec_path.write_text(
        raw_spec.replace(
            marker,
            '"expected_cell_count": ' + "9" * 5000 + ",",
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["experiment_matrix_contract.py", str(spec_path), str(index_path)],
    )

    with pytest.raises(SystemExit) as exc_info:
        matrix_module.main()

    assert exc_info.value.code == 2
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["validation_status"] == "ERROR"
    assert receipt["matrix_complete"] is False
    assert receipt["paper_data_ready"] is False
    assert receipt["statistics_input_ready"] is False


def test_discovery_entry_limit_is_fail_closed(tmp_path, monkeypatch):
    cell = _cell("CELL-201", 201)
    spec = _spec([cell])
    reference = _write_run_bundle(
        tmp_path,
        spec,
        cell,
        run_id="run-matrix-201",
    )
    spec_path, index_path = _write_matrix(tmp_path, spec, [reference])
    monkeypatch.setattr(matrix_module, "MAX_DISCOVERY_ENTRIES", 1)

    with pytest.raises(MatrixIntegrityError, match="entry limit"):
        validate_experiment_matrix(spec_path, index_path)

"""Fail-closed paired statistics and paper export contract tests."""

from copy import deepcopy
import ast
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

import paired_statistics_contract as stats_module
from experiment_matrix_contract import (
    ExpectedCell,
    FROZEN_CLAIM_BOUNDARY as MATRIX_CLAIM_BOUNDARY,
    expected_seed_schedule_sha256,
)
from paired_statistics_contract import (
    FROZEN_STATISTICS_CLAIM_BOUNDARY,
    OutcomeObservation,
    PairedStatisticsSpec,
    StatisticsIntegrityError,
    build_paired_statistics_bundle,
    validate_paired_statistics_bundle,
)
from paper_data_contract import artifact_record, sha256_file


SOURCE_SHA = "a" * 40
PROTOCOL_BYTES = b'{"protocol":"paired-statistics-regression-v1"}\n'
ENVIRONMENT_BYTES = b'{"environment":"synthetic-regression"}\n'
MODEL_BYTES = b"<mujoco model='paired-statistics-regression'/>\n"
REFERENCE_CONTROLLER = "REFERENCE-CONTROLLER-V1"
CANDIDATE_CONTROLLER = "CANDIDATE-CONTROLLER-V1"


def _sha256_bytes(payload: bytes) -> str:
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _json_bytes(payload: dict) -> bytes:
    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _controller_bytes(controller_id: str) -> bytes:
    return _json_bytes({"controller_id": controller_id})


def _config_bytes(cell_id: str) -> bytes:
    return _json_bytes({"cell_id": cell_id, "physics_step_s": 0.002})


def _continuous_outcome(
    outcome_id: str = "path_error_m",
    *,
    role: str = "PRIMARY",
    unit: str = "m",
    minimum_pairs: int = 3,
) -> dict:
    return {
        "outcome_id": outcome_id,
        "role": role,
        "outcome_type": "CONTINUOUS",
        "unit": unit,
        "favorable_direction": "LOWER",
        "estimand": "PAIRED_MEAN_DIFFERENCE",
        "confidence_level": 0.95,
        "interval_method": "PAIRED_PERCENTILE_BOOTSTRAP_V1",
        "bootstrap_seed": 20260904,
        "bootstrap_resamples": 1000,
        "minimum_pairs": minimum_pairs,
        "missing_policy": "PRESERVE_AND_BLOCK",
        "nonfinite_policy": "PRESERVE_AND_BLOCK",
        "censoring_policy": "PRESERVE_AND_BLOCK",
        "terminal_failure_policy": "PRESERVE_EXPLICIT_STATE_V1",
    }


def _binary_outcome(
    outcome_id: str = "task_success",
    *,
    role: str = "SECONDARY",
    terminal_failure_policy: str = "REQUIRE_EXPLICIT_FALSE_FOR_FAILED_V1",
) -> dict:
    return {
        "outcome_id": outcome_id,
        "role": role,
        "outcome_type": "BINARY",
        "unit": "boolean",
        "favorable_direction": "HIGHER",
        "estimand": "PAIRED_RISK_DIFFERENCE",
        "confidence_level": 0.95,
        "interval_method": "PAIRED_BINARY_CI_NOT_IMPLEMENTED_V1",
        "bootstrap_seed": None,
        "bootstrap_resamples": None,
        "minimum_pairs": 3,
        "missing_policy": "PRESERVE_AND_BLOCK",
        "nonfinite_policy": "PRESERVE_AND_BLOCK",
        "censoring_policy": "PRESERVE_AND_BLOCK",
        "terminal_failure_policy": terminal_failure_policy,
    }


def _observed(outcome: dict, value) -> dict:
    return {
        "outcome_id": outcome["outcome_id"],
        "outcome_type": outcome["outcome_type"],
        "unit": outcome["unit"],
        "state": "OBSERVED",
        "value": value,
        "reason": None,
        "censoring_side": None,
        "censoring_bound": None,
    }


def _nonobserved(
    outcome: dict,
    state: str,
    *,
    reason: str,
    side: str | None = None,
    bound: float | None = None,
) -> dict:
    return {
        "outcome_id": outcome["outcome_id"],
        "outcome_type": outcome["outcome_type"],
        "unit": outcome["unit"],
        "state": state,
        "value": None,
        "reason": reason,
        "censoring_side": side,
        "censoring_bound": bound,
    }


def _cell(pair_number: int, role: str) -> dict:
    controller_id = (
        REFERENCE_CONTROLLER if role == "reference" else CANDIDATE_CONTROLLER
    )
    cell_id = f"CELL-{'REF' if role == 'reference' else 'CAND'}-{pair_number:03d}"
    evaluation_seed = 300 + pair_number
    return {
        "cell_id": cell_id,
        "scenario_id": f"SCENARIO-{pair_number:03d}",
        "replicate_id": f"REPLICATE-{pair_number:03d}",
        "controller_family": "LEARNING_BASED",
        "controller": {
            "identity_id": controller_id,
            "sha256": _sha256_bytes(_controller_bytes(controller_id)),
        },
        "deterministic": False,
        "training_seed": 101 if role == "reference" else 202,
        "evaluation_seed": evaluation_seed,
        "environment_seed": 1300 + pair_number,
        "scenario_seed": 2300 + pair_number,
        "resolved_config_sha256": _sha256_bytes(_config_bytes(cell_id)),
        "scenario": {
            "friction": 1.0,
            "payload_kg": float(pair_number - 1),
            "terrain": "flat",
        },
    }


def _matrix_spec(
    cells: list[dict],
    outcomes: list[dict],
    *,
    source_sha: str = SOURCE_SHA,
) -> dict:
    primary = [item["outcome_id"] for item in outcomes if item["role"] == "PRIMARY"]
    secondary = [
        item["outcome_id"] for item in outcomes if item["role"] == "SECONDARY"
    ]
    payload = {
        "schema_version": "EXPERIMENT_MATRIX_SPEC_V1",
        "matrix_id": "MATRIX-PAIRED-STATS-REGRESSION",
        "matrix_version": "1.0.0",
        "experiment_id": "EXP-PAIRED-STATS-REGRESSION",
        "protocol_id": "PROTOCOL-PAIRED-STATS-REGRESSION",
        "protocol_version": "1.0.0",
        "protocol_status": "FROZEN",
        "research_question_id": "RQ-PAIRED-STATS-CONTRACT",
        "hypothesis_id": "H-PAIRED-STATS-CONTRACT",
        "run_class": "REGRESSION",
        "data_partition": "REGRESSION",
        "evidence_scope": "SIM_ONLY_MUJOCO",
        "claim_boundary": MATRIX_CLAIM_BOUNDARY,
        "source_git_sha": source_sha,
        "source_dirty": False,
        "task_id": "TASK-PAIRED-STATS-CONTRACT",
        "plant": {
            "identity_id": "PLANT-PAIRED-STATS-V1",
            "sha256": _sha256_bytes(MODEL_BYTES),
        },
        "protocol_artifact_sha256": _sha256_bytes(PROTOCOL_BYTES),
        "environment_artifact_sha256": _sha256_bytes(ENVIRONMENT_BYTES),
        "metric_set_id": "METRICS-PAIRED-STATS-V1",
        "evaluator_id": "EVALUATOR-PAIRED-STATS-V1",
        "seed_schedule_sha256": "sha256:" + "0" * 64,
        "primary_outcomes": primary,
        "secondary_outcomes": secondary,
        "assist_enabled": False,
        "tuning_performed_after_freeze": False,
        "failure_semantics_id": "MATRIX_FAILURE_RETENTION_V1",
        "expected_cell_count": len(cells),
        "expected_cells": cells,
    }
    payload["seed_schedule_sha256"] = expected_seed_schedule_sha256(
        payload["matrix_id"],
        payload["matrix_version"],
        [ExpectedCell.model_validate(item) for item in cells],
    )
    return payload


def _default_measurements(
    outcomes: list[dict],
    pair_number: int,
    role: str,
    status: str,
) -> list[dict]:
    reference_values = [0.30, -0.10, 0.20, 0.40]
    candidate_values = [0.20, -0.05, 0.25, 0.10]
    measurements = []
    for outcome in outcomes:
        if outcome["outcome_type"] == "BINARY":
            value = False if status == "FAILED" else True
        else:
            values = reference_values if role == "reference" else candidate_values
            value = values[pair_number - 1]
        measurements.append(_observed(outcome, value))
    return measurements


def _write_run_bundle(
    root: Path,
    spec: dict,
    cell: dict,
    outcomes: list[dict],
    *,
    pair_number: int,
    role: str,
    status: str,
    measurement_override: dict[str, dict] | None = None,
    raw_hash_override: str | None = None,
) -> dict:
    run_id = f"run-stats-{role}-{pair_number:03d}"
    run_root = root / "runs" / run_id
    run_root.mkdir(parents=True)
    raw_trace = run_root / "raw_trace.bin"
    raw_trace.write_bytes(f"synthetic raw {run_id}\n".encode())
    raw_trace_sha256 = sha256_file(raw_trace)
    measurements = _default_measurements(outcomes, pair_number, role, status)
    if measurement_override:
        measurements = [
            deepcopy(measurement_override.get(item["outcome_id"], item))
            for item in measurements
        ]
    metrics_payload = {
        "schema_version": "PAPER_RUN_METRICS_V1",
        "run_id": run_id,
        "cell_id": cell["cell_id"],
        "metric_set_id": spec["metric_set_id"],
        "evaluator_id": spec["evaluator_id"],
        "run_status": status,
        "evidence_scope": spec["evidence_scope"],
        "raw_trace_sha256": raw_hash_override or raw_trace_sha256,
        "measurements": measurements,
    }
    files: dict[str, tuple[str, bytes | None]] = {
        "protocol": ("protocol.json", PROTOCOL_BYTES),
        "resolved_config": (
            "resolved_config.json",
            _config_bytes(cell["cell_id"]),
        ),
        "model": ("model.xml", MODEL_BYTES),
        "controller": (
            "controller.json",
            _controller_bytes(cell["controller"]["identity_id"]),
        ),
        "environment": ("environment.json", ENVIRONMENT_BYTES),
        "raw_trace": ("raw_trace.bin", None),
        "metrics": ("metrics.json", _json_bytes(metrics_payload)),
        "evaluator_receipt": (
            "evaluator_receipt.json",
            _json_bytes({"status": "SYNTHETIC_REGRESSION_ONLY"}),
        ),
        "stdout": ("stdout.txt", b""),
        "stderr": ("stderr.txt", b""),
    }
    artifacts = []
    for artifact_role, (filename, content) in files.items():
        path = run_root / filename
        if content is not None:
            path.write_bytes(content)
        artifacts.append(artifact_record(
            run_root,
            path,
            role=artifact_role,
            media_type="application/octet-stream",
        ))
    failures = []
    if status in {"FAILED", "CANCELLED"}:
        failures.append({
            "failure_type": f"SYNTHETIC_{status}",
            "timestamp_s": 1.0,
            "detail": "Synthetic terminal state retained for statistics contract tests.",
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
        "started_at": "2026-09-04T00:00:00+00:00",
        "completed_at": "2026-09-04T00:00:01+00:00",
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
        "tuning_performed_after_freeze": spec["tuning_performed_after_freeze"],
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


def _build_fixture(
    root: Path,
    outcomes: list[dict],
    *,
    pair_count: int = 4,
    statuses: dict[tuple[int, str], str] | None = None,
    overrides: dict[tuple[int, str], dict[str, dict]] | None = None,
    raw_hash_overrides: dict[tuple[int, str], str] | None = None,
    source_sha: str = SOURCE_SHA,
) -> dict[str, Path]:
    statuses = statuses or {}
    overrides = overrides or {}
    raw_hash_overrides = raw_hash_overrides or {}
    cells = [
        _cell(pair_number, role)
        for pair_number in range(1, pair_count + 1)
        for role in ("reference", "candidate")
    ]
    spec = _matrix_spec(cells, outcomes, source_sha=source_sha)
    references = []
    for pair_number in range(1, pair_count + 1):
        for role in ("reference", "candidate"):
            cell = next(
                item
                for item in cells
                if item["cell_id"]
                == f"CELL-{'REF' if role == 'reference' else 'CAND'}-{pair_number:03d}"
            )
            status = statuses.get((pair_number, role), "COMPLETED")
            references.append(_write_run_bundle(
                root,
                spec,
                cell,
                outcomes,
                pair_number=pair_number,
                role=role,
                status=status,
                measurement_override=overrides.get((pair_number, role)),
                raw_hash_override=raw_hash_overrides.get((pair_number, role)),
            ))
    matrix_spec_path = root / "experiment_matrix.json"
    matrix_index_path = root / "experiment_matrix_run_index.json"
    _write_json(matrix_spec_path, spec)
    _write_json(matrix_index_path, {
        "schema_version": "EXPERIMENT_MATRIX_RUN_INDEX_V1",
        "matrix_id": spec["matrix_id"],
        "matrix_spec_sha256": sha256_file(matrix_spec_path),
        "run_manifests": references,
    })
    plan = {
        "schema_version": "PAIRED_STATISTICS_SPEC_V1",
        "analysis_id": "ANALYSIS-PAIRED-STATS-REGRESSION",
        "analysis_version": "1.0.0",
        "matrix_id": spec["matrix_id"],
        "matrix_version": spec["matrix_version"],
        "matrix_spec_sha256": sha256_file(matrix_spec_path),
        "matrix_run_index_sha256": sha256_file(matrix_index_path),
        "source_git_sha": spec["source_git_sha"],
        "source_dirty": False,
        "run_class": spec["run_class"],
        "data_partition": spec["data_partition"],
        "evidence_scope": spec["evidence_scope"],
        "claim_boundary": FROZEN_STATISTICS_CLAIM_BOUNDARY,
        "metric_set_id": spec["metric_set_id"],
        "evaluator_id": spec["evaluator_id"],
        "reference_controller": next(
            item["controller"] for item in cells if item["cell_id"] == "CELL-REF-001"
        ),
        "candidate_controller": next(
            item["controller"] for item in cells if item["cell_id"] == "CELL-CAND-001"
        ),
        "expected_pair_count": pair_count,
        "pairs": [
            {
                "pair_id": f"PAIR-{pair_number:03d}",
                "reference_cell_id": f"CELL-REF-{pair_number:03d}",
                "candidate_cell_id": f"CELL-CAND-{pair_number:03d}",
            }
            for pair_number in range(1, pair_count + 1)
        ],
        "outcomes": outcomes,
        "resampling_algorithm": "SHA256_REJECTION_V1",
        "quantile_method": "LINEAR_TYPE7_V1",
        "failure_semantics_id": "PAIRED_FAILURE_RETENTION_V1",
    }
    statistics_spec_path = root / "paired_statistics_spec.json"
    _write_json(statistics_spec_path, plan)
    return {
        "root": root,
        "statistics_spec": statistics_spec_path,
        "matrix_spec": matrix_spec_path,
        "matrix_index": matrix_index_path,
        "output": root / "aggregate",
    }


def _run_bundle(paths: dict[str, Path], output: Path | None = None) -> dict:
    return build_paired_statistics_bundle(
        paths["statistics_spec"],
        paths["matrix_spec"],
        paths["matrix_index"],
        output or paths["output"],
    )


def test_continuous_paired_statistics_are_deterministic_and_replay_exact(tmp_path):
    paths = _build_fixture(tmp_path / "matrix-a", [_continuous_outcome()])
    receipt = _run_bundle(paths)

    assert receipt["validation_status"] == "STATISTICS_CONTRACT_VALID"
    assert receipt["contract_valid"] is True
    assert receipt["statistics_ready"] is True
    assert receipt["paper_data_ready"] is False
    assert [item["id"] for item in receipt["criteria"]] == [
        f"PS-{index:02d}" for index in range(1, 13)
    ]
    assert all(item["passed"] for item in receipt["criteria"])

    summary = json.loads(
        (paths["output"] / "statistics_summary.json").read_text(encoding="utf-8")
    )
    outcome = summary["outcomes"][0]
    assert outcome["inference_status"] == "READY"
    assert outcome["complete_pair_count"] == 4
    assert outcome["effect"]["estimate"] == pytest.approx(-0.075)
    assert outcome["effect"]["median_difference"] == pytest.approx(-0.025)
    assert outcome["effect"]["cohen_dz"] == pytest.approx(
        -0.45226701686664544
    )
    assert [item["difference"] for item in outcome["pair_values"]] == pytest.approx(
        [-0.1, 0.05, 0.05, -0.3]
    )
    assert outcome["effect"]["confidence_interval"]["resamples"] == 1000
    assert outcome["effect"]["confidence_interval"]["lower"] == pytest.approx(
        -0.25
    )
    assert outcome["effect"]["confidence_interval"]["upper"] == pytest.approx(
        0.05
    )
    assert outcome["effect"]["confidence_interval_null_reason"] is None

    replay = json.loads(
        (paths["output"] / "replay_receipt.json").read_text(encoding="utf-8")
    )
    assert replay["status"] == "PASS"
    assert replay["exact_identity"] is True
    for artifact in receipt["artifacts"]:
        path = paths["output"] / artifact["path"]
        assert path.stat().st_size == artifact["bytes"]
        assert sha256_file(path) == artifact["sha256"]

    second_paths = _build_fixture(tmp_path / "matrix-b", [_continuous_outcome()])
    second_receipt = _run_bundle(second_paths)
    for filename in (
        "paired_raw_table.json",
        "statistics_summary.json",
        "paper_table_input.json",
        "paper_figure_input.json",
    ):
        assert (paths["output"] / filename).read_bytes() == (
            second_paths["output"] / filename
        ).read_bytes()
    assert second_receipt["statistics_ready"] is True


def test_replay_module_imports_only_python_standard_library():
    tree = ast.parse(stats_module.REPLAY_SCRIPT.read_text(encoding="utf-8"))
    imported_roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.split(".")[0])
    assert imported_roots <= (set(sys.stdlib_module_names) | {"__future__"})


def test_failed_binary_is_retained_but_paired_ci_stays_blocked(tmp_path):
    outcomes = [_continuous_outcome(), _binary_outcome()]
    paths = _build_fixture(
        tmp_path / "matrix",
        outcomes,
        statuses={(2, "candidate"): "FAILED"},
    )
    receipt = _run_bundle(paths)

    assert receipt["contract_valid"] is True
    assert receipt["statistics_ready"] is False
    assert receipt["run_status_counts"]["candidate"]["FAILED"] == 1
    assert receipt["blocked_outcomes"] == ["task_success"]
    summary = json.loads(
        (paths["output"] / "statistics_summary.json").read_text(encoding="utf-8")
    )
    binary = summary["outcomes"][1]
    assert binary["inference_status"] == "BLOCKED_BINARY_CI_METHOD"
    assert binary["effect"]["estimate"] == pytest.approx(-0.25)
    assert binary["effect"]["confidence_interval"] is None
    assert binary["effect"]["confidence_interval_null_reason"] == (
        "PAIRED_BINARY_CI_NOT_IMPLEMENTED_V1"
    )
    assert binary["paired_binary_counts"] == {
        "both_true": 3,
        "reference_only": 1,
        "candidate_only": 0,
        "both_false": 0,
    }
    assert binary["reference_summary"]["total"] == 4
    assert binary["candidate_summary"]["successes"] == 3
    assert binary["reference_summary"]["lower"] == pytest.approx(
        0.5101091635454027
    )
    assert binary["candidate_summary"]["lower"] == pytest.approx(
        0.300641842582402
    )
    assert binary["candidate_summary"]["upper"] == pytest.approx(
        0.9544127391902995
    )
    raw = json.loads(
        (paths["output"] / "paired_raw_table.json").read_text(encoding="utf-8")
    )
    failed = next(item for item in raw["pairs"] if item["pair_id"] == "PAIR-002")
    assert failed["candidate"]["run_status"] == "FAILED"
    assert failed["candidate"]["failure_record_count"] == 1
    assert next(
        item for item in failed["candidate"]["measurements"]
        if item["outcome_id"] == "task_success"
    )["value"] is False


def test_null_nonfinite_and_censored_states_are_preserved_and_blocked(tmp_path):
    null_outcome = _continuous_outcome("energy_j", role="PRIMARY", unit="J")
    nonfinite_outcome = _continuous_outcome(
        "solver_residual_n", role="SECONDARY", unit="N"
    )
    censored_outcome = _continuous_outcome(
        "push_threshold_n", role="SECONDARY", unit="N"
    )
    outcomes = [null_outcome, nonfinite_outcome, censored_outcome]
    paths = _build_fixture(
        tmp_path / "matrix",
        outcomes,
        overrides={
            (2, "candidate"): {
                "energy_j": _nonobserved(
                    null_outcome,
                    "NULL",
                    reason="TERMINATED_BEFORE_ENERGY_WINDOW",
                ),
            },
            (3, "candidate"): {
                "solver_residual_n": _nonobserved(
                    nonfinite_outcome,
                    "NONFINITE",
                    reason="SOURCE_EVALUATOR_REPORTED_NAN",
                ),
            },
            (4, "candidate"): {
                "push_threshold_n": _nonobserved(
                    censored_outcome,
                    "CENSORED",
                    reason="UPPER_SEARCH_BOUND_REACHED",
                    side="RIGHT",
                    bound=100.0,
                ),
            },
        },
    )
    receipt = _run_bundle(paths)

    assert receipt["contract_valid"] is True
    assert receipt["statistics_ready"] is False
    assert receipt["blocked_outcomes"] == [
        "energy_j",
        "solver_residual_n",
        "push_threshold_n",
    ]
    summary = json.loads(
        (paths["output"] / "statistics_summary.json").read_text(encoding="utf-8")
    )
    by_id = {item["outcome_id"]: item for item in summary["outcomes"]}
    assert by_id["energy_j"]["candidate_state_counts"]["NULL"] == 1
    assert by_id["solver_residual_n"]["candidate_state_counts"]["NONFINITE"] == 1
    assert by_id["push_threshold_n"]["candidate_state_counts"]["CENSORED"] == 1
    assert by_id["push_threshold_n"]["pair_values"][3][
        "candidate_censoring_bound"
    ] == 100.0
    assert all(item["effect"]["estimate"] is None for item in by_id.values())


def test_cancelled_matrix_is_preserved_and_blocks_aggregate(tmp_path):
    outcome = _continuous_outcome()
    paths = _build_fixture(
        tmp_path / "matrix",
        [outcome],
        statuses={(4, "candidate"): "CANCELLED"},
    )
    receipt = _run_bundle(paths)

    assert receipt["validation_status"] == "BLOCKED_UPSTREAM_MATRIX"
    assert receipt["contract_valid"] is False
    assert receipt["statistics_ready"] is False
    assert receipt["cancelled_cells"] == [{
        "cell_id": "CELL-CAND-004",
        "run_id": "run-stats-candidate-004",
    }]
    assert not (paths["output"] / "paired_raw_table.json").exists()
    matrix_receipt = json.loads(
        (paths["output"] / "matrix_completeness_receipt.json").read_text(
            encoding="utf-8"
        )
    )
    assert matrix_receipt["matrix_complete"] is True
    assert matrix_receipt["statistics_input_ready"] is False


def test_failed_binary_requires_explicit_observed_false(tmp_path):
    binary = _binary_outcome(role="PRIMARY")
    paths = _build_fixture(
        tmp_path / "matrix",
        [binary],
        statuses={(2, "candidate"): "FAILED"},
        overrides={
            (2, "candidate"): {
                "task_success": _nonobserved(
                    binary,
                    "NULL",
                    reason="SYNTHETIC_MISSING_FAILURE_OUTCOME",
                )
            }
        },
    )

    with pytest.raises(StatisticsIntegrityError, match="明示OBSERVED false"):
        _run_bundle(paths)


def test_failed_binary_without_task_failure_mapping_preserves_null(tmp_path):
    binary = _binary_outcome(
        outcome_id="contact_detected",
        role="PRIMARY",
        terminal_failure_policy="PRESERVE_EXPLICIT_STATE_V1",
    )
    paths = _build_fixture(
        tmp_path / "matrix",
        [binary],
        statuses={(2, "candidate"): "FAILED"},
        overrides={
            (2, "candidate"): {
                "contact_detected": _nonobserved(
                    binary,
                    "NULL",
                    reason="FAILED_BEFORE_CONTACT_WINDOW",
                )
            }
        },
    )

    receipt = _run_bundle(paths)
    summary = json.loads(
        (paths["output"] / "statistics_summary.json").read_text(encoding="utf-8")
    )["outcomes"][0]
    assert receipt["contract_valid"] is True
    assert receipt["statistics_ready"] is False
    assert summary["candidate_state_counts"]["NULL"] == 1
    assert summary["effect"]["estimate"] is None


def test_finite_inputs_with_overflowing_difference_fail_closed(tmp_path):
    outcome = _continuous_outcome()
    paths = _build_fixture(
        tmp_path / "matrix",
        [outcome],
        overrides={
            (1, "reference"): {
                outcome["outcome_id"]: _observed(outcome, -1e308)
            },
            (1, "candidate"): {
                outcome["outcome_id"]: _observed(outcome, 1e308)
            },
        },
    )

    with pytest.raises(StatisticsIntegrityError, match="non-finite paired difference"):
        _run_bundle(paths)


def test_metrics_raw_trace_identity_drift_fails_closed(tmp_path):
    paths = _build_fixture(
        tmp_path / "matrix",
        [_continuous_outcome()],
        raw_hash_overrides={(1, "candidate"): "sha256:" + "f" * 64},
    )

    with pytest.raises(StatisticsIntegrityError, match="raw_trace_sha256"):
        _run_bundle(paths)


def test_cross_pair_or_scenario_drift_fails_closed(tmp_path):
    paths = _build_fixture(tmp_path / "matrix", [_continuous_outcome()])
    plan = json.loads(paths["statistics_spec"].read_text(encoding="utf-8"))
    plan["pairs"][0]["candidate_cell_id"] = "CELL-CAND-002"
    plan["pairs"][1]["candidate_cell_id"] = "CELL-CAND-001"
    _write_json(paths["statistics_spec"], plan)

    with pytest.raises(StatisticsIntegrityError, match="pair identity drift"):
        _run_bundle(paths)


def test_reused_cell_and_binary_bootstrap_are_schema_errors(tmp_path):
    paths = _build_fixture(tmp_path / "matrix", [_continuous_outcome()])
    plan = json.loads(paths["statistics_spec"].read_text(encoding="utf-8"))
    plan["pairs"][1]["candidate_cell_id"] = plan["pairs"][0][
        "candidate_cell_id"
    ]
    with pytest.raises(ValidationError, match="重用"):
        PairedStatisticsSpec.model_validate(plan)

    binary = _binary_outcome(role="PRIMARY")
    binary["interval_method"] = "PAIRED_PERCENTILE_BOOTSTRAP_V1"
    binary["bootstrap_seed"] = 1
    binary["bootstrap_resamples"] = 1000
    plan["pairs"][1]["candidate_cell_id"] = "CELL-CAND-002"
    plan["outcomes"] = [binary]
    with pytest.raises(ValidationError, match="未實作"):
        PairedStatisticsSpec.model_validate(plan)

    plan["outcomes"] = [_continuous_outcome()]
    plan["reference_controller"]["sha256"] = "sha256:" + "1" * 64
    plan["candidate_controller"] = {
        "identity_id": plan["reference_controller"]["identity_id"],
        "sha256": "sha256:" + "2" * 64,
    }
    with pytest.raises(ValidationError, match="identity_id"):
        PairedStatisticsSpec.model_validate(plan)


def test_bootstrap_operation_budget_is_bounded(tmp_path):
    paths = _build_fixture(tmp_path / "matrix", [_continuous_outcome()])
    plan = json.loads(paths["statistics_spec"].read_text(encoding="utf-8"))
    plan["outcomes"][0]["bootstrap_resamples"] = 200_000
    plan["expected_pair_count"] = 26
    plan["pairs"] = [
        {
            "pair_id": f"PAIR-BUDGET-{index:03d}",
            "reference_cell_id": f"CELL-BUDGET-REF-{index:03d}",
            "candidate_cell_id": f"CELL-BUDGET-CAND-{index:03d}",
        }
        for index in range(26)
    ]
    with pytest.raises(ValidationError, match="draw budget"):
        PairedStatisticsSpec.model_validate(plan)


@pytest.mark.parametrize("invalid_value", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_observed_value_is_rejected(invalid_value):
    with pytest.raises(ValidationError, match="finite"):
        OutcomeObservation.model_validate({
            "outcome_id": "metric-value",
            "outcome_type": "CONTINUOUS",
            "unit": "m",
            "state": "OBSERVED",
            "value": invalid_value,
            "reason": None,
            "censoring_side": None,
            "censoring_bound": None,
        })


def test_strict_json_rejects_nan_and_duplicate_keys(tmp_path):
    for invalid_kind in ("nan", "duplicate"):
        paths = _build_fixture(
            tmp_path / invalid_kind,
            [_continuous_outcome()],
        )
        raw = paths["statistics_spec"].read_text(encoding="utf-8")
        if invalid_kind == "nan":
            raw = raw.replace('"confidence_level": 0.95', '"confidence_level": NaN')
            pattern = "non-finite"
        else:
            raw = raw.replace(
                '"schema_version": "PAIRED_STATISTICS_SPEC_V1",',
                '"schema_version": "PAIRED_STATISTICS_SPEC_V1",\n'
                '  "schema_version": "PAIRED_STATISTICS_SPEC_V1",',
            )
            pattern = "duplicate JSON key"
        paths["statistics_spec"].write_text(raw, encoding="utf-8")

        with pytest.raises(StatisticsIntegrityError, match=pattern):
            _run_bundle(paths)


def test_minimum_pairs_and_zero_variance_have_explicit_nulls(tmp_path):
    too_few = _continuous_outcome(minimum_pairs=5)
    paths = _build_fixture(tmp_path / "few", [too_few], pair_count=4)
    receipt = _run_bundle(paths)
    summary = json.loads(
        (paths["output"] / "statistics_summary.json").read_text(encoding="utf-8")
    )["outcomes"][0]
    assert receipt["contract_valid"] is True
    assert receipt["statistics_ready"] is False
    assert summary["inference_status"] == "BLOCKED_MINIMUM_PAIRS"
    assert summary["effect"]["confidence_interval"] is None

    constant = _continuous_outcome()
    overrides = {
        (pair, "candidate"): {
            constant["outcome_id"]: _observed(constant, 1.0)
        }
        for pair in range(1, 5)
    }
    overrides.update({
        (pair, "reference"): {
            constant["outcome_id"]: _observed(constant, 0.5)
        }
        for pair in range(1, 5)
    })
    constant_paths = _build_fixture(
        tmp_path / "constant",
        [constant],
        overrides=overrides,
    )
    constant_receipt = _run_bundle(constant_paths)
    constant_summary = json.loads(
        (constant_paths["output"] / "statistics_summary.json").read_text(
            encoding="utf-8"
        )
    )["outcomes"][0]
    assert constant_receipt["statistics_ready"] is True
    assert constant_summary["effect"]["estimate"] == 0.5
    assert constant_summary["effect"]["cohen_dz"] is None
    assert constant_summary["effect"]["cohen_dz_null_reason"] == "ZERO_VARIANCE"


def test_binary_minimum_pair_block_still_retains_four_cell_counts(tmp_path):
    binary = _binary_outcome(role="PRIMARY")
    binary["minimum_pairs"] = 5
    paths = _build_fixture(tmp_path / "binary-few", [binary], pair_count=4)
    receipt = _run_bundle(paths)
    summary = json.loads(
        (paths["output"] / "statistics_summary.json").read_text(encoding="utf-8")
    )["outcomes"][0]

    assert receipt["contract_valid"] is True
    assert receipt["statistics_ready"] is False
    assert summary["inference_status"] == "BLOCKED_MINIMUM_PAIRS"
    assert sum(summary["paired_binary_counts"].values()) == 4
    assert summary["reference_summary"]["total"] == 4
    assert summary["candidate_summary"]["total"] == 4
    assert summary["effect"]["estimate"] is None


def test_replay_detects_tampered_summary(tmp_path):
    paths = _build_fixture(tmp_path / "matrix", [_continuous_outcome()])
    _run_bundle(paths)
    summary_path = paths["output"] / "statistics_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["outcomes"][0]["effect"]["estimate"] = 999.0
    _write_json(summary_path, summary)

    completed = subprocess.run(
        [
            sys.executable,
            "-I",
            "-S",
            str(stats_module.REPLAY_SCRIPT),
            str(paths["statistics_spec"]),
            str(paths["output"] / "paired_raw_table.json"),
            str(summary_path),
            str(paths["output"] / "paper_table_input.json"),
            str(paths["output"] / "paper_figure_input.json"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    replay = json.loads(completed.stdout)
    assert completed.returncode == 2
    assert completed.stderr == ""
    assert replay["status"] == "ERROR"
    assert replay["exact_identity"] is False


@pytest.mark.parametrize(
    "filename",
    [
        "paired_raw_table.json",
        "paper_table_input.json",
        "paper_figure_input.json",
    ],
)
def test_bundle_validator_detects_each_tampered_aggregate_artifact(
    tmp_path,
    filename,
):
    paths = _build_fixture(tmp_path / filename, [_continuous_outcome()])
    _run_bundle(paths)
    target = paths["output"] / filename
    target.write_bytes(target.read_bytes() + b" ")

    with pytest.raises(StatisticsIntegrityError, match="bytes mismatch"):
        validate_paired_statistics_bundle(
            paths["output"] / "statistics_receipt.json"
        )


def test_forged_or_unbounded_replay_receipt_fails_closed(tmp_path, monkeypatch):
    paths = _build_fixture(tmp_path / "matrix", [_continuous_outcome()])
    forged = {
        "schema_version": "PAIRED_STATISTICS_REPLAY_RECEIPT_V1",
        "status": "PASS",
        "exact_identity": True,
        "unexpected": "not-strict",
    }
    monkeypatch.setattr(
        stats_module.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout=json.dumps(forged),
            stderr="",
        ),
    )
    with pytest.raises(StatisticsIntegrityError, match="receipt schema"):
        _run_bundle(paths)


def test_replay_timeout_fails_closed(tmp_path, monkeypatch):
    paths = _build_fixture(tmp_path / "matrix", [_continuous_outcome()])

    def _timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="replay", timeout=120)

    monkeypatch.setattr(stats_module.subprocess, "run", _timeout)
    with pytest.raises(StatisticsIntegrityError, match="timeout"):
        _run_bundle(paths)


def test_output_root_cannot_overwrite_existing_bundle(tmp_path):
    paths = _build_fixture(tmp_path / "matrix", [_continuous_outcome()])
    paths["output"].mkdir()
    (paths["output"] / "existing.json").write_text("{}", encoding="utf-8")

    with pytest.raises(StatisticsIntegrityError, match="不存在或為空"):
        _run_bundle(paths)


def test_cli_exit_codes_are_machine_readable(tmp_path, monkeypatch, capsys):
    ready = _build_fixture(tmp_path / "ready", [_continuous_outcome()])
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "paired_statistics_contract.py",
            str(ready["statistics_spec"]),
            str(ready["matrix_spec"]),
            str(ready["matrix_index"]),
            str(ready["output"]),
        ],
    )
    with pytest.raises(SystemExit) as ready_exit:
        stats_module.main()
    assert ready_exit.value.code == 0
    assert json.loads(capsys.readouterr().out)["statistics_ready"] is True

    blocked = _build_fixture(
        tmp_path / "blocked",
        [_continuous_outcome(), _binary_outcome()],
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "paired_statistics_contract.py",
            str(blocked["statistics_spec"]),
            str(blocked["matrix_spec"]),
            str(blocked["matrix_index"]),
            str(blocked["output"]),
        ],
    )
    with pytest.raises(SystemExit) as blocked_exit:
        stats_module.main()
    assert blocked_exit.value.code == 1
    assert json.loads(capsys.readouterr().out)["contract_valid"] is True

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "paired_statistics_contract.py",
            str(tmp_path / "missing.json"),
            str(blocked["matrix_spec"]),
            str(blocked["matrix_index"]),
            str(tmp_path / "error-output"),
        ],
    )
    with pytest.raises(SystemExit) as error_exit:
        stats_module.main()
    assert error_exit.value.code == 2
    error_receipt = json.loads(capsys.readouterr().out)
    assert error_receipt["validation_status"] == "ERROR"
    assert error_receipt["paper_data_ready"] is False


def test_structurally_invalid_matrix_uses_cli_exit_two(tmp_path, monkeypatch, capsys):
    paths = _build_fixture(tmp_path / "matrix", [_continuous_outcome()])
    raw_trace = paths["root"] / "runs" / "run-stats-reference-001" / "raw_trace.bin"
    raw_trace.write_bytes(b"tampered but retained\n")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "paired_statistics_contract.py",
            str(paths["statistics_spec"]),
            str(paths["matrix_spec"]),
            str(paths["matrix_index"]),
            str(paths["output"]),
        ],
    )

    with pytest.raises(SystemExit) as error_exit:
        stats_module.main()
    assert error_exit.value.code == 2
    error_receipt = json.loads(capsys.readouterr().out)
    assert error_receipt["validation_status"] == "ERROR"
    assert error_receipt["contract_valid"] is False

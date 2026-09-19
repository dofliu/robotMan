"""Fail-closed experiment-matrix completeness validation.

This module validates frozen run inventory and identity only.  A complete
matrix is not a scientific outcome, statistical sufficiency, or physical
validation receipt.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import sys
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from paper_data_contract import (
    GIT_SHA_PATTERN,
    ID_PATTERN,
    SHA256_PATTERN,
    IdentityRecord,
    PaperDataIntegrityError,
    PaperRunManifest,
    ScenarioValue,
    load_json_object_strict,
    sha256_file,
    validate_paper_run_bundle,
)


MATRIX_SPEC_SCHEMA_VERSION = "EXPERIMENT_MATRIX_SPEC_V1"
MATRIX_INDEX_SCHEMA_VERSION = "EXPERIMENT_MATRIX_RUN_INDEX_V1"
MATRIX_RECEIPT_SCHEMA_VERSION = "EXPERIMENT_MATRIX_COMPLETENESS_RECEIPT_V1"
SEED_SCHEDULE_SCHEMA_VERSION = "EXPERIMENT_MATRIX_SEED_SCHEDULE_V1"
FROZEN_CLAIM_BOUNDARY = (
    "SIM_ONLY_MUJOCO / NOT_PHYSICALLY_VALIDATED; matrix inventory identity only, "
    "without controller superiority, sim-to-real, physical fidelity, or safety claims."
)
CRITERION_IDS = tuple(f"MX-{index:02d}" for index in range(1, 11))
MAX_MATRIX_CELLS = 1000
MAX_DISCOVERY_DEPTH = 8
MAX_DISCOVERY_ENTRIES = 110000
MAX_RUN_MANIFESTS = MAX_MATRIX_CELLS


class MatrixIntegrityError(RuntimeError):
    """Matrix schema、identity、path 或 hash 無法建立可信 readback。"""


class MatrixContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, strict=True)


class ExpectedCell(MatrixContractModel):
    cell_id: str = Field(pattern=ID_PATTERN)
    scenario_id: str = Field(pattern=ID_PATTERN)
    replicate_id: str = Field(pattern=ID_PATTERN)
    controller_family: Literal[
        "MODEL_BASED",
        "LEARNING_BASED",
        "HYBRID",
        "ORACLE",
    ]
    controller: IdentityRecord
    deterministic: bool
    training_seed: int | None = Field(default=None, ge=0)
    evaluation_seed: int = Field(ge=0)
    environment_seed: int = Field(ge=0)
    scenario_seed: int = Field(ge=0)
    resolved_config_sha256: str = Field(pattern=SHA256_PATTERN)
    scenario: dict[str, ScenarioValue] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def enforce_training_seed_semantics(self):
        if (
            self.controller_family in {"LEARNING_BASED", "HYBRID"}
            and self.training_seed is None
        ):
            raise ValueError("learning/hybrid expected cell 必須保存 training_seed")
        if (
            self.controller_family in {"MODEL_BASED", "ORACLE"}
            and self.training_seed is not None
        ):
            raise ValueError("model-based/oracle expected cell 的 training_seed 必須為 null")
        for key, value in self.scenario.items():
            if re.fullmatch(ID_PATTERN, key) is None:
                raise ValueError(f"scenario key不是 bounded ID: {key}")
            if isinstance(value, str) and not (1 <= len(value) <= 256):
                raise ValueError(f"scenario string value長度超出範圍: {key}")
        return self


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _canonical_scenario_payload(
    scenario: dict[str, ScenarioValue],
) -> list[dict[str, Any]]:
    """Canonicalize numeric equality while keeping booleans type-distinct."""

    payload: list[dict[str, Any]] = []
    for key in sorted(scenario):
        value = scenario[key]
        if type(value) is bool:
            canonical_value: dict[str, Any] = {
                "type": "boolean",
                "value": value,
            }
        elif type(value) is int:
            canonical_value = {
                "type": "number",
                "numerator": str(value),
                "denominator": "1",
            }
        elif type(value) is float:
            numerator, denominator = value.as_integer_ratio()
            canonical_value = {
                "type": "number",
                "numerator": str(numerator),
                "denominator": str(denominator),
            }
        elif type(value) is str:
            canonical_value = {
                "type": "string",
                "value": value,
            }
        else:
            raise TypeError(f"unsupported scenario value type: {type(value).__name__}")
        payload.append({"key": key, "value": canonical_value})
    return payload


def _scenario_fingerprint(scenario: dict[str, ScenarioValue]) -> str:
    encoded = _canonical_json(_canonical_scenario_payload(scenario)).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _logical_cell_key(cell: ExpectedCell) -> str:
    payload = cell.model_dump(mode="json")
    payload.pop("cell_id")
    payload.pop("scenario_id")
    payload.pop("replicate_id")
    payload["scenario"] = _canonical_scenario_payload(cell.scenario)
    return _canonical_json(payload)


def expected_seed_schedule_sha256(
    matrix_id: str,
    matrix_version: str,
    cells: list[ExpectedCell],
) -> str:
    """Hash the exact canonical seed/controller/scenario linkage."""

    entries = []
    for cell in sorted(cells, key=lambda item: item.cell_id):
        entries.append({
            "cell_id": cell.cell_id,
            "scenario_id": cell.scenario_id,
            "replicate_id": cell.replicate_id,
            "controller": cell.controller.model_dump(mode="json"),
            "deterministic": cell.deterministic,
            "training_seed": cell.training_seed,
            "evaluation_seed": cell.evaluation_seed,
            "environment_seed": cell.environment_seed,
            "scenario_seed": cell.scenario_seed,
            "scenario_fingerprint": _scenario_fingerprint(cell.scenario),
        })
    payload = {
        "schema_version": SEED_SCHEDULE_SCHEMA_VERSION,
        "matrix_id": matrix_id,
        "matrix_version": matrix_version,
        "cells": entries,
    }
    encoded = _canonical_json(payload).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


class ExperimentMatrixSpec(MatrixContractModel):
    schema_version: Literal["EXPERIMENT_MATRIX_SPEC_V1"]
    matrix_id: str = Field(pattern=ID_PATTERN)
    matrix_version: str = Field(pattern=ID_PATTERN)
    experiment_id: str = Field(pattern=ID_PATTERN)
    protocol_id: str = Field(pattern=ID_PATTERN)
    protocol_version: str = Field(pattern=ID_PATTERN)
    protocol_status: Literal["FROZEN"]
    research_question_id: str = Field(pattern=ID_PATTERN)
    hypothesis_id: str = Field(pattern=ID_PATTERN)
    run_class: Literal[
        "DEVELOPMENT",
        "CALIBRATION",
        "FORMAL_EVALUATION",
        "REGRESSION",
    ]
    data_partition: Literal[
        "DEVELOPMENT",
        "CALIBRATION",
        "HOLDOUT",
        "REGRESSION",
    ]
    evidence_scope: Literal["SIM_ONLY_MUJOCO"]
    claim_boundary: str = Field(min_length=40, max_length=2000)
    source_git_sha: str = Field(pattern=GIT_SHA_PATTERN)
    source_dirty: Literal[False]
    task_id: str = Field(pattern=ID_PATTERN)
    plant: IdentityRecord
    protocol_artifact_sha256: str = Field(pattern=SHA256_PATTERN)
    environment_artifact_sha256: str = Field(pattern=SHA256_PATTERN)
    metric_set_id: str = Field(pattern=ID_PATTERN)
    evaluator_id: str = Field(pattern=ID_PATTERN)
    seed_schedule_sha256: str = Field(pattern=SHA256_PATTERN)
    primary_outcomes: list[str] = Field(min_length=1, max_length=20)
    secondary_outcomes: list[str] = Field(default_factory=list, max_length=100)
    assist_enabled: Literal[False]
    tuning_performed_after_freeze: Literal[False]
    failure_semantics_id: Literal["MATRIX_FAILURE_RETENTION_V1"]
    expected_cell_count: int = Field(ge=1, le=MAX_MATRIX_CELLS)
    expected_cells: list[ExpectedCell] = Field(
        min_length=1,
        max_length=MAX_MATRIX_CELLS,
    )

    @model_validator(mode="after")
    def enforce_frozen_matrix(self):
        if self.expected_cell_count != len(self.expected_cells):
            raise ValueError("expected_cell_count 必須等於 expected_cells 長度")
        cell_ids = [cell.cell_id for cell in self.expected_cells]
        if len(cell_ids) != len(set(cell_ids)):
            raise ValueError("expected cell_id 不可重複")
        logical_keys = [_logical_cell_key(cell) for cell in self.expected_cells]
        if len(logical_keys) != len(set(logical_keys)):
            raise ValueError("expected logical cell tuple 不可重複")
        scenario_payloads: dict[str, str] = {}
        for cell in self.expected_cells:
            scenario_payload = _canonical_json(
                _canonical_scenario_payload(cell.scenario)
            )
            existing = scenario_payloads.setdefault(cell.scenario_id, scenario_payload)
            if existing != scenario_payload:
                raise ValueError("相同 scenario_id 必須對應相同 canonical scenario")
        outcomes = self.primary_outcomes + self.secondary_outcomes
        if len(outcomes) != len(set(outcomes)):
            raise ValueError("primary/secondary outcomes 不可重複或重疊")
        if any(re.fullmatch(ID_PATTERN, outcome) is None for outcome in outcomes):
            raise ValueError("primary/secondary outcome 必須是 bounded ID")
        if self.claim_boundary != FROZEN_CLAIM_BOUNDARY:
            raise ValueError("claim_boundary 必須等於 frozen bounded wording")
        expected_schedule_hash = expected_seed_schedule_sha256(
            self.matrix_id,
            self.matrix_version,
            self.expected_cells,
        )
        if self.seed_schedule_sha256 != expected_schedule_hash:
            raise ValueError("seed_schedule_sha256 不符合 canonical expected cells")
        if (
            self.run_class == "FORMAL_EVALUATION"
            and self.data_partition != "HOLDOUT"
        ):
            raise ValueError("FORMAL_EVALUATION matrix 必須使用 HOLDOUT partition")
        return self


class RunManifestReference(MatrixContractModel):
    cell_id: str = Field(pattern=ID_PATTERN)
    run_id: str = Field(pattern=ID_PATTERN)
    path: str = Field(min_length=1, max_length=240)
    bytes: int = Field(ge=0)
    sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def require_manifest_path(self):
        normalized = self.path.replace("\\", "/")
        pure = PurePosixPath(normalized)
        if pure.is_absolute() or ".." in pure.parts or normalized != pure.as_posix():
            raise ValueError("run manifest path 必須是 canonical safe relative POSIX path")
        if pure.name != "paper_run_manifest.json":
            raise ValueError("run manifest path 必須以 paper_run_manifest.json 結尾")
        return self


class ExperimentMatrixRunIndex(MatrixContractModel):
    schema_version: Literal["EXPERIMENT_MATRIX_RUN_INDEX_V1"]
    matrix_id: str = Field(pattern=ID_PATTERN)
    matrix_spec_sha256: str = Field(pattern=SHA256_PATTERN)
    run_manifests: list[RunManifestReference] = Field(
        default_factory=list,
        max_length=MAX_MATRIX_CELLS,
    )


def _load_model(path: Path, model_type: type[MatrixContractModel]):
    try:
        return model_type.model_validate(load_json_object_strict(path))
    except (PaperDataIntegrityError, ValidationError) as exc:
        raise MatrixIntegrityError(f"invalid {path.name}: {exc}") from exc


def _safe_manifest_path(root: Path, relative_path: str) -> Path:
    resolved = (root / relative_path).resolve()
    if not resolved.is_relative_to(root):
        raise MatrixIntegrityError(f"run manifest path escapes matrix root: {relative_path}")
    return resolved


def _is_link_or_junction(path: Path) -> bool:
    if path.is_symlink():
        return True
    is_junction = getattr(path, "is_junction", None)
    return bool(is_junction is not None and is_junction())


def _discover_manifests(root: Path) -> list[str]:
    if root == Path(root.anchor) or (root / ".git").exists():
        raise MatrixIntegrityError("matrix root must be a dedicated bounded directory")
    discovered: list[str] = []
    entry_count = 0
    stack: list[tuple[Path, int]] = [(root, 0)]
    try:
        while stack:
            directory, depth = stack.pop()
            if depth > MAX_DISCOVERY_DEPTH:
                raise MatrixIntegrityError("matrix root exceeds discovery depth limit")
            with os.scandir(directory) as entries:
                for entry in entries:
                    entry_count += 1
                    if entry_count > MAX_DISCOVERY_ENTRIES:
                        raise MatrixIntegrityError(
                            "matrix root exceeds discovery entry limit"
                        )
                    candidate = Path(entry.path)
                    if entry.is_symlink() or _is_link_or_junction(candidate):
                        raise MatrixIntegrityError(
                            f"symlink/junction forbidden in matrix root: {candidate.name}"
                        )
                    if entry.is_dir(follow_symlinks=False):
                        stack.append((candidate, depth + 1))
                    elif entry.is_file(
                        follow_symlinks=False
                    ) and entry.name.casefold() == "paper_run_manifest.json":
                        if entry.name != "paper_run_manifest.json":
                            raise MatrixIntegrityError(
                                "noncanonical run manifest filename casing"
                            )
                        if candidate.stat().st_size > 16 * 1024 * 1024:
                            raise MatrixIntegrityError(
                                "discovered run manifest exceeds JSON size limit"
                            )
                        resolved = candidate.resolve()
                        if not resolved.is_relative_to(root):
                            raise MatrixIntegrityError(
                                f"discovered run manifest escapes matrix root: {candidate}"
                            )
                        discovered.append(resolved.relative_to(root).as_posix())
                        if len(discovered) > MAX_RUN_MANIFESTS:
                            raise MatrixIntegrityError(
                                "matrix root exceeds run manifest count limit"
                            )
    except OSError as exc:
        raise MatrixIntegrityError("cannot enumerate matrix run manifests") from exc
    return sorted(discovered)


def _add_mismatch(
    mismatches: list[dict[str, Any]],
    *,
    cell_id: str,
    run_id: str,
    field: str,
    expected: Any,
    actual: Any,
    equivalent: bool | None = None,
) -> None:
    if equivalent is None:
        equivalent = actual == expected
    if not equivalent:
        mismatches.append({
            "cell_id": cell_id,
            "run_id": run_id,
            "field": field,
            "expected": expected,
            "actual": actual,
        })


def _identity_mismatches(
    spec: ExperimentMatrixSpec,
    cell: ExpectedCell,
    manifest: PaperRunManifest,
    *,
    run_id: str,
) -> list[dict[str, Any]]:
    mismatches: list[dict[str, Any]] = []
    artifacts_by_role = {item.role: item for item in manifest.artifacts}
    common_pairs = {
        "experiment_id": (spec.experiment_id, manifest.experiment_id),
        "protocol_id": (spec.protocol_id, manifest.protocol_id),
        "protocol_version": (spec.protocol_version, manifest.protocol_version),
        "protocol_status": (spec.protocol_status, manifest.protocol_status),
        "research_question_id": (
            spec.research_question_id,
            manifest.research_question_id,
        ),
        "hypothesis_id": (spec.hypothesis_id, manifest.hypothesis_id),
        "run_class": (spec.run_class, manifest.run_class),
        "data_partition": (spec.data_partition, manifest.data_partition),
        "evidence_scope": (spec.evidence_scope, manifest.evidence_scope),
        "claim_boundary": (spec.claim_boundary, manifest.claim_boundary),
        "source_git_sha": (spec.source_git_sha, manifest.source_git_sha),
        "source_dirty": (spec.source_dirty, manifest.source_dirty),
        "task_id": (spec.task_id, manifest.task_id),
        "plant": (
            spec.plant.model_dump(mode="json"),
            manifest.plant.model_dump(mode="json"),
        ),
        "artifacts.protocol.sha256": (
            spec.protocol_artifact_sha256,
            artifacts_by_role["protocol"].sha256,
        ),
        "artifacts.environment.sha256": (
            spec.environment_artifact_sha256,
            artifacts_by_role["environment"].sha256,
        ),
        "artifacts.model.sha256": (
            spec.plant.sha256,
            artifacts_by_role["model"].sha256,
        ),
        "metric_set_id": (spec.metric_set_id, manifest.metric_set_id),
        "evaluator_id": (spec.evaluator_id, manifest.evaluator_id),
        "seed_schedule_sha256": (
            spec.seed_schedule_sha256,
            manifest.seeds.seed_schedule_sha256,
        ),
        "primary_outcomes": (spec.primary_outcomes, manifest.primary_outcomes),
        "secondary_outcomes": (
            spec.secondary_outcomes,
            manifest.secondary_outcomes,
        ),
        "assist_enabled": (spec.assist_enabled, manifest.assist_enabled),
        "tuning_performed_after_freeze": (
            spec.tuning_performed_after_freeze,
            manifest.tuning_performed_after_freeze,
        ),
    }
    cell_pairs = {
        "controller_family": (cell.controller_family, manifest.controller_family),
        "controller_id": (cell.controller.identity_id, manifest.controller_id),
        "controller": (
            cell.controller.model_dump(mode="json"),
            manifest.controller.model_dump(mode="json"),
        ),
        "artifacts.controller.sha256": (
            cell.controller.sha256,
            artifacts_by_role["controller"].sha256,
        ),
        "artifacts.resolved_config.sha256": (
            cell.resolved_config_sha256,
            artifacts_by_role["resolved_config"].sha256,
        ),
        "seeds.deterministic": (cell.deterministic, manifest.seeds.deterministic),
        "seeds.training_seed": (cell.training_seed, manifest.seeds.training_seed),
        "seeds.evaluation_seed": (
            cell.evaluation_seed,
            manifest.seeds.evaluation_seed,
        ),
        "seeds.environment_seed": (
            cell.environment_seed,
            manifest.seeds.environment_seed,
        ),
        "seeds.scenario_seed": (cell.scenario_seed, manifest.seeds.scenario_seed),
    }
    for field, (expected, actual) in {**common_pairs, **cell_pairs}.items():
        _add_mismatch(
            mismatches,
            cell_id=cell.cell_id,
            run_id=run_id,
            field=field,
            expected=expected,
            actual=actual,
        )
    _add_mismatch(
        mismatches,
        cell_id=cell.cell_id,
        run_id=run_id,
        field="scenario",
        expected=cell.scenario,
        actual=manifest.scenario,
        equivalent=(
            _canonical_scenario_payload(cell.scenario)
            == _canonical_scenario_payload(manifest.scenario)
        ),
    )
    return mismatches


def validate_experiment_matrix(
    spec_path: Path,
    index_path: Path,
) -> dict[str, Any]:
    """Validate exact expected-to-observed run linkage and return a receipt."""

    spec_path = spec_path.resolve()
    index_path = index_path.resolve()
    if not spec_path.is_file():
        raise FileNotFoundError(spec_path)
    if not index_path.is_file():
        raise FileNotFoundError(index_path)
    if spec_path.name != "experiment_matrix.json":
        raise MatrixIntegrityError("matrix spec filename must be experiment_matrix.json")
    if index_path.name != "experiment_matrix_run_index.json":
        raise MatrixIntegrityError(
            "matrix index filename must be experiment_matrix_run_index.json"
        )
    root = spec_path.parent.resolve()
    if index_path.parent.resolve() != root:
        raise MatrixIntegrityError("matrix spec and index must share one dedicated root")

    spec = _load_model(spec_path, ExperimentMatrixSpec)
    index = _load_model(index_path, ExperimentMatrixRunIndex)
    spec_sha256 = sha256_file(spec_path)
    if index.matrix_id != spec.matrix_id:
        raise MatrixIntegrityError("matrix_id mismatch between spec and index")
    if index.matrix_spec_sha256 != spec_sha256:
        raise MatrixIntegrityError("matrix spec SHA-256 mismatch")

    expected_by_id = {cell.cell_id: cell for cell in spec.expected_cells}
    reference_cell_counts = Counter(item.cell_id for item in index.run_manifests)
    reference_path_counts = Counter(item.path.casefold() for item in index.run_manifests)
    reference_run_counts = Counter(item.run_id for item in index.run_manifests)
    expected_ids = set(expected_by_id)
    referenced_ids = set(reference_cell_counts)

    declared_missing_cells = sorted(expected_ids - referenced_ids)
    duplicate_cells = sorted(
        cell_id for cell_id, count in reference_cell_counts.items() if count > 1
    )
    unexpected_cells = sorted(referenced_ids - expected_ids)
    duplicate_manifest_paths = sorted(
        item.path
        for item in index.run_manifests
        if reference_path_counts[item.path.casefold()] > 1
    )
    duplicate_manifest_paths = sorted(set(duplicate_manifest_paths))
    duplicate_run_ids = sorted(
        run_id for run_id, count in reference_run_counts.items() if count > 1
    )

    discovered_paths = _discover_manifests(root)
    indexed_paths = {item.path for item in index.run_manifests}
    unindexed_manifest_paths = sorted(set(discovered_paths) - indexed_paths)

    invalid_references: list[dict[str, Any]] = []
    identity_mismatches: list[dict[str, Any]] = []
    cell_receipts: list[dict[str, Any]] = []
    failed_cells: list[dict[str, str]] = []
    cancelled_cells: list[dict[str, str]] = []
    status_counts = {"COMPLETED": 0, "FAILED": 0, "CANCELLED": 0}
    integrity_valid_run_count = 0
    identity_valid_run_count = 0
    identity_valid_cell_ids: set[str] = set()

    for reference in index.run_manifests:
        try:
            manifest_path = _safe_manifest_path(root, reference.path)
            if not manifest_path.is_file():
                raise MatrixIntegrityError("referenced run manifest is missing")
            if manifest_path.stat().st_size != reference.bytes:
                raise MatrixIntegrityError("run manifest bytes mismatch")
            manifest_sha256 = sha256_file(manifest_path)
            if manifest_sha256 != reference.sha256:
                raise MatrixIntegrityError("run manifest SHA-256 mismatch")
            try:
                manifest = PaperRunManifest.model_validate(
                    load_json_object_strict(manifest_path)
                )
            except (PaperDataIntegrityError, ValidationError) as exc:
                raise MatrixIntegrityError(f"invalid paper run manifest: {exc}") from exc
            if manifest.run_id != reference.run_id:
                raise MatrixIntegrityError("indexed run_id does not match actual run_id")
            bundle_receipt = validate_paper_run_bundle(manifest_path)
            if bundle_receipt["manifest_sha256"] != reference.sha256:
                raise MatrixIntegrityError("bundle receipt manifest identity mismatch")
        except (OSError, MatrixIntegrityError, PaperDataIntegrityError) as exc:
            invalid_references.append({
                "cell_id": reference.cell_id,
                "run_id": reference.run_id,
                "path": reference.path,
                "error": f"{type(exc).__name__}: {exc}"[:1000],
            })
            continue

        integrity_valid_run_count += 1
        status_counts[manifest.status] += 1
        if manifest.status == "FAILED":
            failed_cells.append({
                "cell_id": reference.cell_id,
                "run_id": manifest.run_id,
            })
        elif manifest.status == "CANCELLED":
            cancelled_cells.append({
                "cell_id": reference.cell_id,
                "run_id": manifest.run_id,
            })

        expected_cell = expected_by_id.get(reference.cell_id)
        run_mismatches: list[dict[str, Any]] = []
        if expected_cell is not None:
            run_mismatches = _identity_mismatches(
                spec,
                expected_cell,
                manifest,
                run_id=manifest.run_id,
            )
            identity_mismatches.extend(run_mismatches)
            if not run_mismatches:
                identity_valid_run_count += 1
                identity_valid_cell_ids.add(reference.cell_id)

        cell_receipts.append({
            "cell_id": reference.cell_id,
            "scenario_id": (
                expected_cell.scenario_id if expected_cell is not None else None
            ),
            "replicate_id": (
                expected_cell.replicate_id if expected_cell is not None else None
            ),
            "run_id": manifest.run_id,
            "path": reference.path,
            "manifest_sha256": reference.sha256,
            "run_status": manifest.status,
            "failure_record_count": len(manifest.failures),
            "bundle_validation_status": bundle_receipt["validation_status"],
            "bundle_paper_data_ready": bundle_receipt["paper_data_ready"],
            "identity_valid": expected_cell is not None and not run_mismatches,
        })

    unvalidated_expected_cells = sorted(expected_ids - identity_valid_cell_ids)
    terminal_receipts = [
        item
        for item in cell_receipts
        if item["run_status"] in {"FAILED", "CANCELLED"}
    ]
    status_retention_valid = (
        sum(status_counts.values()) == integrity_valid_run_count
        and all(item["failure_record_count"] > 0 for item in terminal_receipts)
    )
    criteria = [
        {"id": "MX-01", "passed": True},
        {"id": "MX-02", "passed": True},
        {"id": "MX-03", "passed": True},
        {"id": "MX-04", "passed": not invalid_references},
        {"id": "MX-05", "passed": not identity_mismatches},
        {
            "id": "MX-06",
            "passed": not (
                declared_missing_cells
                or duplicate_cells
                or unexpected_cells
                or unvalidated_expected_cells
            ),
        },
        {
            "id": "MX-07",
            "passed": not (
                duplicate_manifest_paths
                or duplicate_run_ids
                or unindexed_manifest_paths
            ),
        },
        {"id": "MX-08", "passed": status_retention_valid},
        {"id": "MX-09", "passed": True},
        {"id": "MX-10", "passed": True},
    ]
    if tuple(item["id"] for item in criteria) != CRITERION_IDS:
        raise AssertionError("internal criterion mapping drift")
    matrix_complete = all(item["passed"] for item in criteria)

    return {
        "schema_version": MATRIX_RECEIPT_SCHEMA_VERSION,
        "matrix_id": spec.matrix_id,
        "matrix_version": spec.matrix_version,
        "experiment_id": spec.experiment_id,
        "validation_status": (
            "MATRIX_COMPLETE" if matrix_complete else "MATRIX_INCOMPLETE"
        ),
        "matrix_complete": matrix_complete,
        "paper_data_ready": False,
        "statistics_input_ready": matrix_complete and not cancelled_cells,
        "outcome_status": "NOT_EVALUATED",
        "matrix_spec_sha256": spec_sha256,
        "matrix_spec_bytes": spec_path.stat().st_size,
        "run_index_sha256": sha256_file(index_path),
        "run_index_bytes": index_path.stat().st_size,
        "seed_schedule_sha256": spec.seed_schedule_sha256,
        "seed_schedule_entry_count": spec.expected_cell_count,
        "expected_cell_count": spec.expected_cell_count,
        "indexed_run_count": len(index.run_manifests),
        "integrity_valid_run_count": integrity_valid_run_count,
        "identity_valid_run_count": identity_valid_run_count,
        "run_status_counts": status_counts,
        "declared_missing_cells": declared_missing_cells,
        "unvalidated_expected_cells": unvalidated_expected_cells,
        "duplicate_cells": duplicate_cells,
        "unexpected_cells": unexpected_cells,
        "duplicate_manifest_paths": duplicate_manifest_paths,
        "duplicate_run_ids": duplicate_run_ids,
        "unindexed_manifest_paths": unindexed_manifest_paths,
        "invalid_references": invalid_references,
        "identity_mismatches": identity_mismatches,
        "failed_cells": failed_cells,
        "cancelled_cells": cancelled_cells,
        "cell_receipts": cell_receipts,
        "criteria": criteria,
        "frozen_claim_boundary": spec.claim_boundary,
        "claim_boundary": (
            "Experiment inventory and exact identity completeness only; this receipt does "
            "not establish metric correctness, statistical sufficiency, controller "
            "superiority, physical fidelity, sim-to-real performance, or safety."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate an EXPERIMENT_MATRIX_SPEC_V1 run inventory"
    )
    parser.add_argument("spec", type=Path)
    parser.add_argument("index", type=Path)
    args = parser.parse_args()
    try:
        receipt = validate_experiment_matrix(args.spec, args.index)
    except (FileNotFoundError, MatrixIntegrityError) as exc:
        error_receipt = {
            "schema_version": MATRIX_RECEIPT_SCHEMA_VERSION,
            "validation_status": "ERROR",
            "matrix_complete": False,
            "paper_data_ready": False,
            "statistics_input_ready": False,
            "error": f"{type(exc).__name__}: {exc}",
        }
        print(json.dumps(error_receipt, ensure_ascii=False, indent=2))
        raise SystemExit(2) from exc
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    raise SystemExit(0 if receipt["matrix_complete"] else 1)


if __name__ == "__main__":
    main()

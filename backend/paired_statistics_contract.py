"""Fail-closed paired statistics and paper-input generation.

This module only establishes a bounded software contract.  It never upgrades
simulation observations into physical validation or controller-superiority
evidence.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import stat
import statistics
import subprocess
import sys
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from experiment_matrix_contract import (
    ExperimentMatrixRunIndex,
    ExperimentMatrixSpec,
    validate_experiment_matrix,
)
from paper_data_contract import (
    GIT_SHA_PATTERN,
    ID_PATTERN,
    MAX_JSON_BYTES,
    SHA256_PATTERN,
    IdentityRecord,
    PaperDataIntegrityError,
    PaperRunManifest,
    load_json_object_strict,
    sha256_file,
)


STATISTICS_SPEC_SCHEMA_VERSION = "PAIRED_STATISTICS_SPEC_V1"
RUN_METRICS_SCHEMA_VERSION = "PAPER_RUN_METRICS_V1"
RAW_TABLE_SCHEMA_VERSION = "PAIRED_RAW_TABLE_V1"
SUMMARY_SCHEMA_VERSION = "PAIRED_STATISTICS_SUMMARY_V1"
TABLE_INPUT_SCHEMA_VERSION = "PAPER_TABLE_INPUT_V1"
FIGURE_INPUT_SCHEMA_VERSION = "PAPER_FIGURE_INPUT_V1"
STATISTICS_RECEIPT_SCHEMA_VERSION = "PAIRED_STATISTICS_RECEIPT_V1"
REPLAY_RECEIPT_SCHEMA_VERSION = "PAIRED_STATISTICS_REPLAY_RECEIPT_V1"
ERROR_RECEIPT_SCHEMA_VERSION = "PAIRED_STATISTICS_ERROR_RECEIPT_V1"
FROZEN_STATISTICS_CLAIM_BOUNDARY = (
    "SIM_ONLY_MUJOCO / NOT_PHYSICALLY_VALIDATED; paired statistical software "
    "output only, without Study A or formal authorization, controller superiority, "
    "sim-to-real, physical fidelity, safety, or paper-acceptance claims."
)
CRITERION_IDS = tuple(f"PS-{index:02d}" for index in range(1, 13))
MAX_OUTCOMES = 100
MAX_PAIRS = 1000
MAX_BOOTSTRAP_DRAWS = 5_000_000
MAX_REPLAY_STDOUT_BYTES = 1024 * 1024
REPLAY_TIMEOUT_SECONDS = 120
REPLAY_SCRIPT = Path(__file__).with_name("paired_statistics_replay.py")


class StatisticsIntegrityError(RuntimeError):
    """Statistics schema、pair identity、artifact或replay不可信。"""


class StatisticsContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, strict=True)


class PairDefinition(StatisticsContractModel):
    pair_id: str = Field(pattern=ID_PATTERN)
    reference_cell_id: str = Field(pattern=ID_PATTERN)
    candidate_cell_id: str = Field(pattern=ID_PATTERN)

    @model_validator(mode="after")
    def require_distinct_cells(self):
        if self.reference_cell_id == self.candidate_cell_id:
            raise ValueError("pair兩側不可使用同一cell")
        return self


class OutcomeDefinition(StatisticsContractModel):
    outcome_id: str = Field(pattern=ID_PATTERN)
    role: Literal["PRIMARY", "SECONDARY"]
    outcome_type: Literal["CONTINUOUS", "BINARY"]
    unit: str = Field(min_length=1, max_length=80)
    favorable_direction: Literal["HIGHER", "LOWER", "NEUTRAL"]
    estimand: Literal["PAIRED_MEAN_DIFFERENCE", "PAIRED_RISK_DIFFERENCE"]
    confidence_level: Literal[0.95]
    interval_method: Literal[
        "PAIRED_PERCENTILE_BOOTSTRAP_V1",
        "PAIRED_BINARY_CI_NOT_IMPLEMENTED_V1",
    ]
    bootstrap_seed: int | None = Field(default=None, ge=0, le=2**63 - 1)
    bootstrap_resamples: int | None = Field(default=None, ge=1000, le=200000)
    minimum_pairs: int = Field(ge=2, le=MAX_PAIRS)
    missing_policy: Literal["PRESERVE_AND_BLOCK"]
    nonfinite_policy: Literal["PRESERVE_AND_BLOCK"]
    censoring_policy: Literal["PRESERVE_AND_BLOCK"]
    terminal_failure_policy: Literal[
        "PRESERVE_EXPLICIT_STATE_V1",
        "REQUIRE_EXPLICIT_FALSE_FOR_FAILED_V1",
    ]

    @model_validator(mode="after")
    def require_type_specific_semantics(self):
        if self.outcome_type == "CONTINUOUS":
            if self.estimand != "PAIRED_MEAN_DIFFERENCE":
                raise ValueError("continuous outcome必須使用paired mean difference")
            if self.interval_method != "PAIRED_PERCENTILE_BOOTSTRAP_V1":
                raise ValueError("continuous outcome必須使用frozen paired bootstrap")
            if self.bootstrap_seed is None or self.bootstrap_resamples is None:
                raise ValueError("continuous bootstrap必須凍結seed與resample count")
            if self.terminal_failure_policy != "PRESERVE_EXPLICIT_STATE_V1":
                raise ValueError("continuous outcome必須保留explicit measurement state")
        else:
            if self.estimand != "PAIRED_RISK_DIFFERENCE":
                raise ValueError("binary outcome必須使用paired risk difference")
            if self.interval_method != "PAIRED_BINARY_CI_NOT_IMPLEMENTED_V1":
                raise ValueError("binary paired CI在V1必須明示未實作")
            if self.bootstrap_seed is not None or self.bootstrap_resamples is not None:
                raise ValueError("binary V1不得偽裝成bootstrap paired CI")
            if self.terminal_failure_policy not in {
                "PRESERVE_EXPLICIT_STATE_V1",
                "REQUIRE_EXPLICIT_FALSE_FOR_FAILED_V1",
            }:
                raise ValueError("binary outcome必須凍結explicit failure mapping")
        return self


class PairedStatisticsSpec(StatisticsContractModel):
    schema_version: Literal["PAIRED_STATISTICS_SPEC_V1"]
    analysis_id: str = Field(pattern=ID_PATTERN)
    analysis_version: str = Field(pattern=ID_PATTERN)
    matrix_id: str = Field(pattern=ID_PATTERN)
    matrix_version: str = Field(pattern=ID_PATTERN)
    matrix_spec_sha256: str = Field(pattern=SHA256_PATTERN)
    matrix_run_index_sha256: str = Field(pattern=SHA256_PATTERN)
    source_git_sha: str = Field(pattern=GIT_SHA_PATTERN)
    source_dirty: Literal[False]
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
    claim_boundary: str = Field(min_length=100, max_length=2000)
    metric_set_id: str = Field(pattern=ID_PATTERN)
    evaluator_id: str = Field(pattern=ID_PATTERN)
    reference_controller: IdentityRecord
    candidate_controller: IdentityRecord
    expected_pair_count: int = Field(ge=1, le=MAX_PAIRS)
    pairs: list[PairDefinition] = Field(min_length=1, max_length=MAX_PAIRS)
    outcomes: list[OutcomeDefinition] = Field(min_length=1, max_length=MAX_OUTCOMES)
    resampling_algorithm: Literal["SHA256_REJECTION_V1"]
    quantile_method: Literal["LINEAR_TYPE7_V1"]
    failure_semantics_id: Literal["PAIRED_FAILURE_RETENTION_V1"]

    @model_validator(mode="after")
    def enforce_frozen_analysis(self):
        if self.claim_boundary != FROZEN_STATISTICS_CLAIM_BOUNDARY:
            raise ValueError("claim_boundary必須等於frozen bounded wording")
        if self.reference_controller == self.candidate_controller:
            raise ValueError("reference與candidate controller必須不同")
        if (
            self.reference_controller.identity_id
            == self.candidate_controller.identity_id
        ):
            raise ValueError("reference與candidate controller identity_id必須不同")
        if self.expected_pair_count != len(self.pairs):
            raise ValueError("expected_pair_count必須等於pairs長度")
        pair_ids = [item.pair_id for item in self.pairs]
        if len(pair_ids) != len(set(pair_ids)):
            raise ValueError("pair_id不可重複")
        cell_ids = [
            cell_id
            for item in self.pairs
            for cell_id in (item.reference_cell_id, item.candidate_cell_id)
        ]
        if len(cell_ids) != len(set(cell_ids)):
            raise ValueError("matrix cell不可跨pair或角色重用")
        outcome_ids = [item.outcome_id for item in self.outcomes]
        if len(outcome_ids) != len(set(outcome_ids)):
            raise ValueError("outcome_id不可重複")
        bootstrap_draws = sum(
            item.bootstrap_resamples * self.expected_pair_count
            for item in self.outcomes
            if item.bootstrap_resamples is not None
        )
        if bootstrap_draws > MAX_BOOTSTRAP_DRAWS:
            raise ValueError(
                "frozen bootstrap workload exceeds bounded V1 draw budget"
            )
        return self


class OutcomeObservation(StatisticsContractModel):
    outcome_id: str = Field(pattern=ID_PATTERN)
    outcome_type: Literal["CONTINUOUS", "BINARY"]
    unit: str = Field(min_length=1, max_length=80)
    state: Literal["OBSERVED", "NULL", "NONFINITE", "CENSORED"]
    value: Any = None
    reason: str | None = Field(default=None, min_length=1, max_length=500)
    censoring_side: Literal["LEFT", "RIGHT"] | None = None
    censoring_bound: float | None = None

    @model_validator(mode="after")
    def enforce_state_payload(self):
        if self.state == "OBSERVED":
            if self.reason is not None:
                raise ValueError("OBSERVED不得夾帶reason")
            if self.censoring_side is not None or self.censoring_bound is not None:
                raise ValueError("OBSERVED不得夾帶censoring payload")
            if self.outcome_type == "BINARY":
                if type(self.value) is not bool:
                    raise ValueError("binary OBSERVED value必須是boolean")
            else:
                if type(self.value) not in {int, float}:
                    raise ValueError("continuous OBSERVED value必須是number且不能是boolean")
                try:
                    finite = math.isfinite(float(self.value))
                except (OverflowError, ValueError):
                    finite = False
                if not finite:
                    raise ValueError("continuous OBSERVED value必須finite")
            return self

        if self.value is not None or self.reason is None:
            raise ValueError("non-observed state必須使用null value與bounded reason")
        if self.state == "CENSORED":
            if self.outcome_type != "CONTINUOUS":
                raise ValueError("binary outcome不接受CENSORED state")
            if self.censoring_side is None or self.censoring_bound is None:
                raise ValueError("CENSORED必須保存side與finite bound")
            if not math.isfinite(self.censoring_bound):
                raise ValueError("censoring bound必須finite")
        elif self.censoring_side is not None or self.censoring_bound is not None:
            raise ValueError("NULL/NONFINITE不得夾帶censoring payload")
        return self


class PaperRunMetrics(StatisticsContractModel):
    schema_version: Literal["PAPER_RUN_METRICS_V1"]
    run_id: str = Field(pattern=ID_PATTERN)
    cell_id: str = Field(pattern=ID_PATTERN)
    metric_set_id: str = Field(pattern=ID_PATTERN)
    evaluator_id: str = Field(pattern=ID_PATTERN)
    run_status: Literal["COMPLETED", "FAILED", "CANCELLED"]
    evidence_scope: Literal["SIM_ONLY_MUJOCO"]
    raw_trace_sha256: str = Field(pattern=SHA256_PATTERN)
    measurements: list[OutcomeObservation] = Field(
        min_length=1,
        max_length=MAX_OUTCOMES,
    )

    @model_validator(mode="after")
    def require_unique_measurements(self):
        outcome_ids = [item.outcome_id for item in self.measurements]
        if len(outcome_ids) != len(set(outcome_ids)):
            raise ValueError("metrics artifact的outcome_id不可重複")
        return self


class ReplayChecks(StatisticsContractModel):
    statistics_summary: Literal[True]
    paper_table_input: Literal[True]
    paper_figure_input: Literal[True]


class PairedStatisticsReplayReceipt(StatisticsContractModel):
    schema_version: Literal["PAIRED_STATISTICS_REPLAY_RECEIPT_V1"]
    status: Literal["PASS"]
    exact_identity: Literal[True]
    checks: ReplayChecks
    statistics_spec_sha256: str = Field(pattern=SHA256_PATTERN)
    paired_raw_table_sha256: str = Field(pattern=SHA256_PATTERN)
    statistics_summary_sha256: str = Field(pattern=SHA256_PATTERN)
    paper_table_input_sha256: str = Field(pattern=SHA256_PATTERN)
    paper_figure_input_sha256: str = Field(pattern=SHA256_PATTERN)
    paper_data_ready: Literal[False]
    claim_boundary: str = Field(min_length=100, max_length=2000)

    @model_validator(mode="after")
    def require_frozen_boundary(self):
        if self.claim_boundary != FROZEN_STATISTICS_CLAIM_BOUNDARY:
            raise ValueError("replay claim boundary drift")
        return self


class AggregateArtifactRecord(StatisticsContractModel):
    role: Literal[
        "matrix_completeness_receipt",
        "paired_raw_table",
        "statistics_summary",
        "table_input",
        "figure_input",
        "independent_replay_receipt",
    ]
    path: str = Field(min_length=1, max_length=240)
    bytes: int = Field(ge=0, le=MAX_JSON_BYTES)
    sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def require_safe_path(self):
        normalized = self.path.replace("\\", "/")
        pure = PurePosixPath(normalized)
        if pure.is_absolute() or ".." in pure.parts or normalized != pure.as_posix():
            raise ValueError("aggregate artifact path必須是canonical relative POSIX path")
        return self


class CriterionResult(StatisticsContractModel):
    id: Literal[
        "PS-01", "PS-02", "PS-03", "PS-04", "PS-05", "PS-06",
        "PS-07", "PS-08", "PS-09", "PS-10", "PS-11", "PS-12",
    ]
    passed: bool
    evidence: str = Field(min_length=1, max_length=300)


class CancelledCell(StatisticsContractModel):
    cell_id: str = Field(pattern=ID_PATTERN)
    run_id: str = Field(pattern=ID_PATTERN)


class ArmRunStatusCounts(StatisticsContractModel):
    COMPLETED: int = Field(ge=0, le=MAX_PAIRS)
    FAILED: int = Field(ge=0, le=MAX_PAIRS)
    CANCELLED: int = Field(ge=0, le=MAX_PAIRS)


class AggregateRunStatusCounts(StatisticsContractModel):
    reference: ArmRunStatusCounts
    candidate: ArmRunStatusCounts


class PairedStatisticsReceipt(StatisticsContractModel):
    schema_version: Literal["PAIRED_STATISTICS_RECEIPT_V1"]
    analysis_id: str = Field(pattern=ID_PATTERN)
    analysis_version: str = Field(pattern=ID_PATTERN)
    validation_status: Literal[
        "STATISTICS_CONTRACT_VALID",
        "BLOCKED_UPSTREAM_MATRIX",
    ]
    contract_valid: bool
    statistics_ready: bool
    paper_inputs_generated: bool
    paper_data_ready: Literal[False]
    statistics_spec_sha256: str = Field(pattern=SHA256_PATTERN)
    matrix_spec_sha256: str = Field(pattern=SHA256_PATTERN)
    matrix_run_index_sha256: str = Field(pattern=SHA256_PATTERN)
    run_status_counts: AggregateRunStatusCounts
    expected_pair_count: int = Field(ge=1, le=MAX_PAIRS)
    blocked_outcomes: list[str] = Field(max_length=MAX_OUTCOMES)
    cancelled_cells: list[CancelledCell] = Field(max_length=MAX_PAIRS)
    criteria: list[CriterionResult] = Field(min_length=12, max_length=12)
    artifacts: list[AggregateArtifactRecord] = Field(min_length=1, max_length=6)
    source_git_sha: str = Field(pattern=GIT_SHA_PATTERN)
    evidence_scope: Literal["SIM_ONLY_MUJOCO"]
    claim_boundary: str = Field(min_length=100, max_length=2000)

    @model_validator(mode="after")
    def enforce_receipt_semantics(self):
        if [item.id for item in self.criteria] != list(CRITERION_IDS):
            raise ValueError("receipt criterion mapping drift")
        if self.claim_boundary != FROZEN_STATISTICS_CLAIM_BOUNDARY:
            raise ValueError("receipt claim boundary drift")
        roles = [item.role for item in self.artifacts]
        paths = [item.path.casefold() for item in self.artifacts]
        if len(roles) != len(set(roles)) or len(paths) != len(set(paths)):
            raise ValueError("receipt artifact role/path不可重複")
        if self.validation_status == "STATISTICS_CONTRACT_VALID":
            expected_roles = {
                "matrix_completeness_receipt",
                "paired_raw_table",
                "statistics_summary",
                "table_input",
                "figure_input",
                "independent_replay_receipt",
            }
            if not self.contract_valid or not self.paper_inputs_generated:
                raise ValueError("valid receipt semantics drift")
            if not all(item.passed for item in self.criteria):
                raise ValueError("valid receipt cannot contain failed criterion")
        else:
            expected_roles = {"matrix_completeness_receipt"}
            if self.contract_valid or self.statistics_ready or self.paper_inputs_generated:
                raise ValueError("blocked receipt semantics drift")
        if set(roles) != expected_roles:
            raise ValueError("receipt artifact role set mismatch")
        if self.statistics_ready and not self.contract_valid:
            raise ValueError("statistics_ready requires contract_valid")
        return self


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _write_json(path: Path, payload: Any) -> None:
    text = json.dumps(
        payload,
        ensure_ascii=False,
        allow_nan=False,
        indent=2,
        sort_keys=True,
    ) + "\n"
    if len(text.encode("utf-8")) > MAX_JSON_BYTES:
        raise StatisticsIntegrityError(
            f"aggregate JSON exceeds {MAX_JSON_BYTES} byte limit: {path.name}"
        )
    path.write_text(
        text,
        encoding="utf-8",
        newline="\n",
    )


def _load_model(path: Path, model_type: type[StatisticsContractModel]):
    try:
        return model_type.model_validate(load_json_object_strict(path))
    except (PaperDataIntegrityError, ValidationError) as exc:
        raise StatisticsIntegrityError(f"invalid {path.name}: {exc}") from exc


def _reject_text_json_constant(value: str) -> None:
    raise StatisticsIntegrityError(
        f"replay receipt contains non-finite constant: {value}"
    )


def _reject_text_json_duplicate_keys(
    pairs: list[tuple[str, Any]],
) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key, value in pairs:
        if key in payload:
            raise StatisticsIntegrityError(
                f"replay receipt contains duplicate JSON key: {key}"
            )
        payload[key] = value
    return payload


def _load_json_text_strict(text: str, *, label: str) -> dict[str, Any]:
    if len(text.encode("utf-8")) > MAX_REPLAY_STDOUT_BYTES:
        raise StatisticsIntegrityError(f"{label} exceeds bounded stdout size")
    try:
        payload = json.loads(
            text,
            parse_constant=_reject_text_json_constant,
            object_pairs_hook=_reject_text_json_duplicate_keys,
        )
    except StatisticsIntegrityError:
        raise
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise StatisticsIntegrityError(f"invalid {label} JSON") from exc
    if not isinstance(payload, dict):
        raise StatisticsIntegrityError(f"{label} root must be an object")
    return payload


def _is_link_or_junction(path: Path) -> bool:
    try:
        metadata = path.lstat()
    except OSError:
        return True
    return path.is_symlink() or bool(
        getattr(metadata, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    )


def _validate_output_artifact_path(root: Path, relative_path: str) -> Path:
    normalized = relative_path.replace("\\", "/")
    pure = PurePosixPath(normalized)
    if pure.is_absolute() or ".." in pure.parts or normalized != pure.as_posix():
        raise StatisticsIntegrityError("aggregate artifact path is not canonical")
    candidate = root / normalized
    current = candidate
    while current != root:
        if _is_link_or_junction(current):
            raise StatisticsIntegrityError(
                f"aggregate artifact path traverses link/reparse point: {relative_path}"
            )
        current = current.parent
    resolved = candidate.resolve()
    if not resolved.is_relative_to(root) or not resolved.is_file():
        raise StatisticsIntegrityError(
            f"aggregate artifact missing or escapes root: {relative_path}"
        )
    return resolved


def _canonical_scenario_payload(scenario: dict[str, Any]) -> list[dict[str, Any]]:
    """與matrix contract相同地保留bool/number型別差異。"""

    payload: list[dict[str, Any]] = []
    for key in sorted(scenario):
        value = scenario[key]
        if type(value) is bool:
            canonical_value = {"type": "boolean", "value": value}
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
            canonical_value = {"type": "string", "value": value}
        else:
            raise StatisticsIntegrityError(
                f"unsupported scenario value type: {type(value).__name__}"
            )
        payload.append({"key": key, "value": canonical_value})
    return payload


def _safe_relative_file(root: Path, relative_path: str) -> Path:
    normalized = relative_path.replace("\\", "/")
    pure = PurePosixPath(normalized)
    if pure.is_absolute() or ".." in pure.parts or normalized != pure.as_posix():
        raise StatisticsIntegrityError("artifact path不是canonical safe POSIX relative path")
    resolved = (root / normalized).resolve()
    if not resolved.is_relative_to(root) or not resolved.is_file():
        raise StatisticsIntegrityError(f"artifact missing or escapes root: {relative_path}")
    return resolved


def _artifact_record(root: Path, path: Path, *, role: str) -> dict[str, Any]:
    resolved = path.resolve()
    if not resolved.is_relative_to(root) or not resolved.is_file():
        raise StatisticsIntegrityError("statistics artifact必須位於output root")
    return {
        "role": role,
        "path": resolved.relative_to(root).as_posix(),
        "bytes": resolved.stat().st_size,
        "sha256": sha256_file(resolved),
    }


def _mean(values: list[float]) -> float:
    try:
        result = math.fsum(values) / len(values)
    except OverflowError as exc:
        raise StatisticsIntegrityError("derived mean overflowed") from exc
    if not math.isfinite(result):
        raise StatisticsIntegrityError("derived mean is non-finite")
    return result


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    midpoint = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[midpoint]
    try:
        result = math.fsum((ordered[midpoint - 1], ordered[midpoint])) / 2.0
    except OverflowError as exc:
        raise StatisticsIntegrityError("derived median overflowed") from exc
    if not math.isfinite(result):
        raise StatisticsIntegrityError("derived median is non-finite")
    return result


def _uniform_index(
    *,
    seed: int,
    replicate: int,
    draw: int,
    population_size: int,
) -> int:
    """SHA-256 rejection sampling避免依賴runtime RNG與modulo bias。"""

    upper = 1 << 64
    limit = upper - (upper % population_size)
    retry = 0
    while True:
        token = f"{seed}:{replicate}:{draw}:{retry}".encode("ascii")
        value = int.from_bytes(hashlib.sha256(token).digest()[:8], "big")
        if value < limit:
            return value % population_size
        retry += 1


def _type7_quantile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower_index = math.floor(position)
    upper_index = math.ceil(position)
    if lower_index == upper_index:
        return ordered[lower_index]
    fraction = position - lower_index
    return math.fsum((
        ordered[lower_index] * (1.0 - fraction),
        ordered[upper_index] * fraction,
    ))


def _bootstrap_interval(
    differences: list[float],
    *,
    seed: int,
    resamples: int,
    confidence_level: float,
) -> dict[str, Any]:
    bootstrap_estimates: list[float] = []
    sample_size = len(differences)
    for replicate in range(resamples):
        sample = [
            differences[_uniform_index(
                seed=seed,
                replicate=replicate,
                draw=draw,
                population_size=sample_size,
            )]
            for draw in range(sample_size)
        ]
        bootstrap_estimates.append(_mean(sample))
    alpha = 1.0 - confidence_level
    return {
        "confidence_level": confidence_level,
        "method": "PAIRED_PERCENTILE_BOOTSTRAP_V1",
        "resampling_algorithm": "SHA256_REJECTION_V1",
        "quantile_method": "LINEAR_TYPE7_V1",
        "seed": seed,
        "resamples": resamples,
        "lower": _type7_quantile(bootstrap_estimates, alpha / 2.0),
        "upper": _type7_quantile(bootstrap_estimates, 1.0 - alpha / 2.0),
    }


def _wilson_interval(successes: int, total: int, confidence_level: float) -> dict[str, Any]:
    proportion = successes / total
    alpha = 1.0 - confidence_level
    z = statistics.NormalDist().inv_cdf(1.0 - alpha / 2.0)
    z_squared = z * z
    denominator = 1.0 + z_squared / total
    center = (proportion + z_squared / (2.0 * total)) / denominator
    half_width = (
        z
        * math.sqrt(
            proportion * (1.0 - proportion) / total
            + z_squared / (4.0 * total * total)
        )
        / denominator
    )
    return {
        "successes": successes,
        "total": total,
        "proportion": proportion,
        "confidence_level": confidence_level,
        "method": "WILSON_SCORE_V1",
        "lower": max(0.0, center - half_width),
        "upper": min(1.0, center + half_width),
    }


def _blocked_effect(outcome: OutcomeDefinition, reason: str) -> dict[str, Any]:
    return {
        "estimand": outcome.estimand,
        "direction": "CANDIDATE_MINUS_REFERENCE",
        "estimate": None,
        "median_difference": None,
        "cohen_dz": None,
        "cohen_dz_null_reason": reason,
        "confidence_interval": None,
        "confidence_interval_null_reason": reason,
    }


def _binary_descriptives(
    reference_values: list[float],
    candidate_values: list[float],
    confidence_level: float,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, int]]:
    reference_successes = sum(int(value) for value in reference_values)
    candidate_successes = sum(int(value) for value in candidate_values)
    reference_summary = _wilson_interval(
        reference_successes,
        len(reference_values),
        confidence_level,
    )
    candidate_summary = _wilson_interval(
        candidate_successes,
        len(candidate_values),
        confidence_level,
    )
    counts = {
        "both_true": 0,
        "reference_only": 0,
        "candidate_only": 0,
        "both_false": 0,
    }
    for reference_value, candidate_value in zip(
        reference_values,
        candidate_values,
    ):
        if reference_value == candidate_value == 1.0:
            counts["both_true"] += 1
        elif reference_value == 1.0 and candidate_value == 0.0:
            counts["reference_only"] += 1
        elif reference_value == 0.0 and candidate_value == 1.0:
            counts["candidate_only"] += 1
        else:
            counts["both_false"] += 1
    return reference_summary, candidate_summary, counts


def _outcome_summary(
    outcome: OutcomeDefinition,
    pairs: list[dict[str, Any]],
) -> dict[str, Any]:
    reference_states: Counter[str] = Counter()
    candidate_states: Counter[str] = Counter()
    nonestimable_pair_ids: list[str] = []
    reference_values: list[float] = []
    candidate_values: list[float] = []
    differences: list[float] = []
    pair_values: list[dict[str, Any]] = []

    for pair in pairs:
        reference = next(
            item
            for item in pair["reference"]["measurements"]
            if item["outcome_id"] == outcome.outcome_id
        )
        candidate = next(
            item
            for item in pair["candidate"]["measurements"]
            if item["outcome_id"] == outcome.outcome_id
        )
        reference_states[reference["state"]] += 1
        candidate_states[candidate["state"]] += 1
        difference: float | None = None
        if reference["state"] == candidate["state"] == "OBSERVED":
            reference_value = float(reference["value"])
            candidate_value = float(candidate["value"])
            difference = candidate_value - reference_value
            if not math.isfinite(difference):
                raise StatisticsIntegrityError(
                    "finite observations produced non-finite paired difference: "
                    f"{pair['pair_id']}:{outcome.outcome_id}"
                )
            reference_values.append(reference_value)
            candidate_values.append(candidate_value)
            differences.append(difference)
        else:
            nonestimable_pair_ids.append(pair["pair_id"])
        pair_values.append({
            "pair_id": pair["pair_id"],
            "scenario_id": pair["scenario_id"],
            "replicate_id": pair["replicate_id"],
            "evaluation_seed": pair["evaluation_seed"],
            "environment_seed": pair["environment_seed"],
            "scenario_seed": pair["scenario_seed"],
            "scenario": pair["scenario"],
            "reference_cell_id": pair["reference"]["cell_id"],
            "reference_run_id": pair["reference"]["run_id"],
            "reference_run_status": pair["reference"]["run_status"],
            "reference_failure_record_count": pair["reference"][
                "failure_record_count"
            ],
            "reference_manifest_path": pair["reference"]["manifest_path"],
            "reference_manifest_sha256": pair["reference"]["manifest_sha256"],
            "reference_metrics_sha256": pair["reference"]["metrics_sha256"],
            "reference_raw_trace_sha256": pair["reference"]["raw_trace_sha256"],
            "reference_state": reference["state"],
            "reference_value": reference["value"],
            "reference_reason": reference["reason"],
            "reference_censoring_side": reference["censoring_side"],
            "reference_censoring_bound": reference["censoring_bound"],
            "candidate_cell_id": pair["candidate"]["cell_id"],
            "candidate_run_id": pair["candidate"]["run_id"],
            "candidate_run_status": pair["candidate"]["run_status"],
            "candidate_failure_record_count": pair["candidate"][
                "failure_record_count"
            ],
            "candidate_manifest_path": pair["candidate"]["manifest_path"],
            "candidate_manifest_sha256": pair["candidate"]["manifest_sha256"],
            "candidate_metrics_sha256": pair["candidate"]["metrics_sha256"],
            "candidate_raw_trace_sha256": pair["candidate"]["raw_trace_sha256"],
            "candidate_state": candidate["state"],
            "candidate_value": candidate["value"],
            "candidate_reason": candidate["reason"],
            "candidate_censoring_side": candidate["censoring_side"],
            "candidate_censoring_bound": candidate["censoring_bound"],
            "difference": difference,
        })

    common = {
        "outcome_id": outcome.outcome_id,
        "role": outcome.role,
        "outcome_type": outcome.outcome_type,
        "unit": outcome.unit,
        "favorable_direction": outcome.favorable_direction,
        "expected_pair_count": len(pairs),
        "complete_pair_count": len(differences),
        "reference_state_counts": {
            state: reference_states.get(state, 0)
            for state in ("OBSERVED", "NULL", "NONFINITE", "CENSORED")
        },
        "candidate_state_counts": {
            state: candidate_states.get(state, 0)
            for state in ("OBSERVED", "NULL", "NONFINITE", "CENSORED")
        },
        "nonestimable_pair_ids": nonestimable_pair_ids,
        "pair_values": pair_values,
    }

    if nonestimable_pair_ids:
        return {
            **common,
            "inference_status": "BLOCKED_NONOBSERVED",
            "block_reason": "PRESERVE_AND_BLOCK",
            "reference_summary": None,
            "candidate_summary": None,
            "paired_binary_counts": None,
            "effect": _blocked_effect(outcome, "BLOCKED_NONOBSERVED"),
        }
    if len(differences) < outcome.minimum_pairs:
        if outcome.outcome_type == "BINARY":
            (
                reference_summary,
                candidate_summary,
                paired_binary_counts,
            ) = _binary_descriptives(
                reference_values,
                candidate_values,
                outcome.confidence_level,
            )
        else:
            reference_summary = None
            candidate_summary = None
            paired_binary_counts = None
        return {
            **common,
            "inference_status": "BLOCKED_MINIMUM_PAIRS",
            "block_reason": (
                f"complete_pair_count={len(differences)} < minimum_pairs="
                f"{outcome.minimum_pairs}"
            ),
            "reference_summary": reference_summary,
            "candidate_summary": candidate_summary,
            "paired_binary_counts": paired_binary_counts,
            "effect": _blocked_effect(outcome, "BLOCKED_MINIMUM_PAIRS"),
        }

    effect: dict[str, Any] = {
        "estimand": outcome.estimand,
        "direction": "CANDIDATE_MINUS_REFERENCE",
        "estimate": _mean(differences),
        "median_difference": _median(differences),
    }
    paired_binary_counts: dict[str, int] | None = None
    if outcome.outcome_type == "CONTINUOUS":
        if outcome.bootstrap_seed is None or outcome.bootstrap_resamples is None:
            raise AssertionError("validated continuous bootstrap settings missing")
        effect["confidence_interval"] = _bootstrap_interval(
            differences,
            seed=outcome.bootstrap_seed,
            resamples=outcome.bootstrap_resamples,
            confidence_level=outcome.confidence_level,
        )
        effect["confidence_interval_null_reason"] = None
        try:
            sample_sd = statistics.stdev(differences)
        except (AttributeError, OverflowError, statistics.StatisticsError) as exc:
            raise StatisticsIntegrityError(
                f"derived sample SD failed: {outcome.outcome_id}"
            ) from exc
        if not math.isfinite(sample_sd):
            raise StatisticsIntegrityError(
                f"derived sample SD is non-finite: {outcome.outcome_id}"
            )
        effect["cohen_dz"] = (
            None if sample_sd == 0.0 else effect["estimate"] / sample_sd
        )
        if effect["cohen_dz"] is not None and not math.isfinite(effect["cohen_dz"]):
            raise StatisticsIntegrityError(
                f"derived Cohen dz is non-finite: {outcome.outcome_id}"
            )
        effect["cohen_dz_null_reason"] = (
            "ZERO_VARIANCE" if sample_sd == 0.0 else None
        )
        reference_summary = {
            "mean": _mean(reference_values),
            "median": _median(reference_values),
        }
        candidate_summary = {
            "mean": _mean(candidate_values),
            "median": _median(candidate_values),
        }
    else:
        effect["confidence_interval"] = None
        effect["confidence_interval_null_reason"] = (
            "PAIRED_BINARY_CI_NOT_IMPLEMENTED_V1"
        )
        effect["cohen_dz"] = None
        effect["cohen_dz_null_reason"] = "NOT_APPLICABLE_BINARY"
        (
            reference_summary,
            candidate_summary,
            paired_binary_counts,
        ) = _binary_descriptives(
            reference_values,
            candidate_values,
            outcome.confidence_level,
        )

    inference_status = (
        "READY"
        if outcome.outcome_type == "CONTINUOUS"
        else "BLOCKED_BINARY_CI_METHOD"
    )
    return {
        **common,
        "inference_status": inference_status,
        "block_reason": (
            None
            if inference_status == "READY"
            else "PAIRED_BINARY_CI_NOT_IMPLEMENTED_V1"
        ),
        "reference_summary": reference_summary,
        "candidate_summary": candidate_summary,
        "paired_binary_counts": paired_binary_counts,
        "effect": effect,
    }


def _criteria(
    *,
    upstream_ready: bool,
    aggregate_generated: bool,
    replay_passed: bool,
) -> list[dict[str, Any]]:
    """Map each frozen criterion to a gate actually reached by this execution."""

    checks = [
        (True, "bounded strict schemas parsed"),
        (upstream_ready, "upstream matrix exact-complete and statistics-ready"),
        (True, "spec-to-matrix identities checked before aggregation"),
        (True, "explicit pair map and paired scenario/seed identities checked"),
        (aggregate_generated, "run metrics and raw-trace identities read back"),
        (True, "terminal status and failure counts retained by matrix validator"),
        (aggregate_generated, "negative/null/nonfinite/censored semantics evaluated"),
        (aggregate_generated, "continuous estimand and bounded bootstrap evaluated"),
        (aggregate_generated, "paired binary counts and explicit CI blocker evaluated"),
        (aggregate_generated, "raw/summary/table/figure payloads generated"),
        (aggregate_generated, "aggregate artifact path/bytes/SHA inventory validated"),
        (replay_passed, "stdlib-only replay returned exact hash-bound identity"),
    ]
    return [
        {"id": criterion_id, "passed": passed, "evidence": evidence}
        for criterion_id, (passed, evidence) in zip(CRITERION_IDS, checks)
    ]


def _arm_status_counts_from_matrix(
    plan: PairedStatisticsSpec,
    matrix_receipt: dict[str, Any],
) -> dict[str, dict[str, int]]:
    status_by_cell = {
        item["cell_id"]: item["run_status"]
        for item in matrix_receipt["cell_receipts"]
    }
    return {
        role: {
            status: sum(
                status_by_cell[
                    getattr(pair, f"{role}_cell_id")
                ] == status
                for pair in plan.pairs
            )
            for status in ("COMPLETED", "FAILED", "CANCELLED")
        }
        for role in ("reference", "candidate")
    }


def _validate_plan_against_matrix(
    plan: PairedStatisticsSpec,
    matrix: ExperimentMatrixSpec,
    index_path: Path,
    spec_path: Path,
) -> None:
    expected = {
        "matrix_id": (matrix.matrix_id, plan.matrix_id),
        "matrix_version": (matrix.matrix_version, plan.matrix_version),
        "matrix_spec_sha256": (sha256_file(spec_path), plan.matrix_spec_sha256),
        "matrix_run_index_sha256": (
            sha256_file(index_path),
            plan.matrix_run_index_sha256,
        ),
        "source_git_sha": (matrix.source_git_sha, plan.source_git_sha),
        "source_dirty": (matrix.source_dirty, plan.source_dirty),
        "run_class": (matrix.run_class, plan.run_class),
        "data_partition": (matrix.data_partition, plan.data_partition),
        "evidence_scope": (matrix.evidence_scope, plan.evidence_scope),
        "metric_set_id": (matrix.metric_set_id, plan.metric_set_id),
        "evaluator_id": (matrix.evaluator_id, plan.evaluator_id),
    }
    mismatches = [
        key for key, (matrix_value, plan_value) in expected.items()
        if matrix_value != plan_value
    ]
    if mismatches:
        raise StatisticsIntegrityError(
            f"statistics spec與matrix identity mismatch: {sorted(mismatches)}"
        )
    matrix_outcomes = matrix.primary_outcomes + matrix.secondary_outcomes
    planned_outcomes = [item.outcome_id for item in plan.outcomes]
    if planned_outcomes != matrix_outcomes:
        raise StatisticsIntegrityError(
            "statistics outcomes必須依matrix primary/secondary順序exact match"
        )
    primary = set(matrix.primary_outcomes)
    for outcome in plan.outcomes:
        expected_role = "PRIMARY" if outcome.outcome_id in primary else "SECONDARY"
        if outcome.role != expected_role:
            raise StatisticsIntegrityError(
                f"outcome role與matrix drift: {outcome.outcome_id}"
            )


def _validate_pair_map(
    plan: PairedStatisticsSpec,
    matrix: ExperimentMatrixSpec,
) -> None:
    cells = {item.cell_id: item for item in matrix.expected_cells}
    paired_cell_ids = {
        cell_id
        for item in plan.pairs
        for cell_id in (item.reference_cell_id, item.candidate_cell_id)
    }
    if paired_cell_ids != set(cells):
        raise StatisticsIntegrityError(
            "explicit pair map必須exact覆蓋全部matrix cells"
        )
    for pair in plan.pairs:
        reference = cells[pair.reference_cell_id]
        candidate = cells[pair.candidate_cell_id]
        if reference.controller != plan.reference_controller:
            raise StatisticsIntegrityError(f"reference controller drift: {pair.pair_id}")
        if candidate.controller != plan.candidate_controller:
            raise StatisticsIntegrityError(f"candidate controller drift: {pair.pair_id}")
        identity_pairs = {
            "scenario_id": (reference.scenario_id, candidate.scenario_id),
            "replicate_id": (reference.replicate_id, candidate.replicate_id),
            "evaluation_seed": (
                reference.evaluation_seed,
                candidate.evaluation_seed,
            ),
            "environment_seed": (
                reference.environment_seed,
                candidate.environment_seed,
            ),
            "scenario_seed": (reference.scenario_seed, candidate.scenario_seed),
            "scenario": (
                _canonical_scenario_payload(reference.scenario),
                _canonical_scenario_payload(candidate.scenario),
            ),
        }
        drift = [
            key for key, (left, right) in identity_pairs.items() if left != right
        ]
        if drift:
            raise StatisticsIntegrityError(
                f"pair identity drift {pair.pair_id}: {sorted(drift)}"
            )


def _load_metrics_by_cell(
    root: Path,
    matrix: ExperimentMatrixSpec,
    index: ExperimentMatrixRunIndex,
    plan: PairedStatisticsSpec,
) -> dict[str, dict[str, Any]]:
    expected_cells = {item.cell_id: item for item in matrix.expected_cells}
    outcomes = {item.outcome_id: item for item in plan.outcomes}
    loaded: dict[str, dict[str, Any]] = {}
    for reference in index.run_manifests:
        manifest_path = _safe_relative_file(root, reference.path)
        if (
            manifest_path.stat().st_size != reference.bytes
            or sha256_file(manifest_path) != reference.sha256
        ):
            raise StatisticsIntegrityError(
                f"run manifest post-read identity mismatch: {reference.cell_id}"
            )
        try:
            manifest = PaperRunManifest.model_validate(
                load_json_object_strict(manifest_path)
            )
        except (PaperDataIntegrityError, ValidationError) as exc:
            raise StatisticsIntegrityError(
                f"invalid paper run manifest for {reference.cell_id}: {exc}"
            ) from exc
        artifacts = {item.role: item for item in manifest.artifacts}
        metrics_record = artifacts["metrics"]
        raw_trace_record = artifacts["raw_trace"]
        metrics_path = _safe_relative_file(manifest_path.parent, metrics_record.path)
        raw_trace_path = _safe_relative_file(
            manifest_path.parent,
            raw_trace_record.path,
        )
        if (
            metrics_path.stat().st_size != metrics_record.bytes
            or sha256_file(metrics_path) != metrics_record.sha256
        ):
            raise StatisticsIntegrityError(
                f"metrics artifact identity mismatch: {reference.cell_id}"
            )
        if (
            raw_trace_path.stat().st_size != raw_trace_record.bytes
            or sha256_file(raw_trace_path) != raw_trace_record.sha256
        ):
            raise StatisticsIntegrityError(
                f"raw trace artifact identity mismatch: {reference.cell_id}"
            )
        metrics = _load_model(metrics_path, PaperRunMetrics)
        identity = {
            "run_id": (manifest.run_id, metrics.run_id),
            "cell_id": (reference.cell_id, metrics.cell_id),
            "metric_set_id": (plan.metric_set_id, metrics.metric_set_id),
            "evaluator_id": (plan.evaluator_id, metrics.evaluator_id),
            "run_status": (manifest.status, metrics.run_status),
            "evidence_scope": (plan.evidence_scope, metrics.evidence_scope),
            "raw_trace_sha256": (
                raw_trace_record.sha256,
                metrics.raw_trace_sha256,
            ),
        }
        drift = [key for key, (left, right) in identity.items() if left != right]
        if drift:
            raise StatisticsIntegrityError(
                f"metrics identity mismatch {reference.cell_id}: {sorted(drift)}"
            )
        measurement_map = {
            item.outcome_id: item for item in metrics.measurements
        }
        if set(measurement_map) != set(outcomes):
            raise StatisticsIntegrityError(
                f"metrics outcome set mismatch: {reference.cell_id}"
            )
        for outcome_id, definition in outcomes.items():
            observation = measurement_map[outcome_id]
            if (
                observation.outcome_type != definition.outcome_type
                or observation.unit != definition.unit
            ):
                raise StatisticsIntegrityError(
                    f"metrics type/unit drift {reference.cell_id}:{outcome_id}"
                )
            if (
                manifest.status == "FAILED"
                and definition.outcome_type == "BINARY"
                and definition.terminal_failure_policy
                == "REQUIRE_EXPLICIT_FALSE_FOR_FAILED_V1"
                and (
                    observation.state != "OBSERVED"
                    or observation.value is not False
                )
            ):
                raise StatisticsIntegrityError(
                    "FAILED binary outcome必須明示OBSERVED false: "
                    f"{reference.cell_id}:{outcome_id}"
                )
        loaded[reference.cell_id] = {
            "cell": expected_cells[reference.cell_id],
            "reference": reference,
            "manifest": manifest,
            "metrics": metrics,
            "metrics_sha256": metrics_record.sha256,
            "raw_trace_sha256": raw_trace_record.sha256,
        }
    return loaded


def _arm_payload(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "cell_id": item["reference"].cell_id,
        "run_id": item["manifest"].run_id,
        "run_status": item["manifest"].status,
        "failure_record_count": len(item["manifest"].failures),
        "manifest_path": item["reference"].path,
        "manifest_sha256": item["reference"].sha256,
        "metrics_sha256": item["metrics_sha256"],
        "raw_trace_sha256": item["raw_trace_sha256"],
        "measurements": [
            measurement.model_dump(mode="json")
            for measurement in item["metrics"].measurements
        ],
    }


def _build_raw_table(
    plan: PairedStatisticsSpec,
    matrix: ExperimentMatrixSpec,
    loaded: dict[str, dict[str, Any]],
    *,
    statistics_spec_sha256: str,
) -> dict[str, Any]:
    pairs: list[dict[str, Any]] = []
    for pair in sorted(plan.pairs, key=lambda item: item.pair_id):
        reference = loaded[pair.reference_cell_id]
        candidate = loaded[pair.candidate_cell_id]
        cell = reference["cell"]
        pairs.append({
            "pair_id": pair.pair_id,
            "scenario_id": cell.scenario_id,
            "replicate_id": cell.replicate_id,
            "evaluation_seed": cell.evaluation_seed,
            "environment_seed": cell.environment_seed,
            "scenario_seed": cell.scenario_seed,
            "scenario": cell.scenario,
            "reference": _arm_payload(reference),
            "candidate": _arm_payload(candidate),
        })
    run_status_counts = {
        role: {
            status: sum(
                pair[role]["run_status"] == status for pair in pairs
            )
            for status in ("COMPLETED", "FAILED", "CANCELLED")
        }
        for role in ("reference", "candidate")
    }
    return {
        "schema_version": RAW_TABLE_SCHEMA_VERSION,
        "analysis_id": plan.analysis_id,
        "analysis_version": plan.analysis_version,
        "matrix_id": plan.matrix_id,
        "matrix_version": plan.matrix_version,
        "statistics_spec_sha256": statistics_spec_sha256,
        "matrix_spec_sha256": plan.matrix_spec_sha256,
        "matrix_run_index_sha256": plan.matrix_run_index_sha256,
        "source_git_sha": plan.source_git_sha,
        "evidence_scope": plan.evidence_scope,
        "expected_pair_count": plan.expected_pair_count,
        "pair_count": len(pairs),
        "run_status_counts": run_status_counts,
        "pairs": pairs,
        "claim_boundary": plan.claim_boundary,
    }


def _summary_payload(
    plan: PairedStatisticsSpec,
    raw_table: dict[str, Any],
) -> dict[str, Any]:
    outcome_summaries = [
        _outcome_summary(outcome, raw_table["pairs"])
        for outcome in plan.outcomes
    ]
    blocked_outcomes = [
        item["outcome_id"]
        for item in outcome_summaries
        if item["inference_status"] != "READY"
    ]
    return {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "analysis_id": plan.analysis_id,
        "analysis_version": plan.analysis_version,
        "statistics_spec_sha256": raw_table["statistics_spec_sha256"],
        "matrix_spec_sha256": plan.matrix_spec_sha256,
        "matrix_run_index_sha256": plan.matrix_run_index_sha256,
        "source_git_sha": plan.source_git_sha,
        "evidence_scope": plan.evidence_scope,
        "statistics_ready": not blocked_outcomes,
        "expected_pair_count": plan.expected_pair_count,
        "run_status_counts": raw_table["run_status_counts"],
        "blocked_outcomes": blocked_outcomes,
        "outcomes": outcome_summaries,
        "paper_data_ready": False,
        "claim_boundary": plan.claim_boundary,
    }


def _table_payload(
    plan: PairedStatisticsSpec,
    summary: dict[str, Any],
) -> dict[str, Any]:
    rows = []
    for item in summary["outcomes"]:
        rows.append({
            "outcome_id": item["outcome_id"],
            "role": item["role"],
            "outcome_type": item["outcome_type"],
            "unit": item["unit"],
            "favorable_direction": item["favorable_direction"],
            "inference_status": item["inference_status"],
            "block_reason": item["block_reason"],
            "expected_pair_count": item["expected_pair_count"],
            "complete_pair_count": item["complete_pair_count"],
            "nonestimable_pair_ids": item["nonestimable_pair_ids"],
            "reference_summary": item["reference_summary"],
            "candidate_summary": item["candidate_summary"],
            "paired_binary_counts": item["paired_binary_counts"],
            "effect": item["effect"],
            "pair_values": item["pair_values"],
        })
    return {
        "schema_version": TABLE_INPUT_SCHEMA_VERSION,
        "analysis_id": plan.analysis_id,
        "analysis_version": plan.analysis_version,
        "statistics_spec_sha256": summary["statistics_spec_sha256"],
        "matrix_spec_sha256": plan.matrix_spec_sha256,
        "matrix_run_index_sha256": plan.matrix_run_index_sha256,
        "source_git_sha": plan.source_git_sha,
        "evidence_scope": plan.evidence_scope,
        "expected_pair_count": plan.expected_pair_count,
        "run_status_counts": summary["run_status_counts"],
        "blocked_outcomes": summary["blocked_outcomes"],
        "rows": rows,
        "paper_data_ready": False,
        "claim_boundary": plan.claim_boundary,
    }


def _figure_payload(
    plan: PairedStatisticsSpec,
    summary: dict[str, Any],
) -> dict[str, Any]:
    series = []
    for item in summary["outcomes"]:
        series.append({
            "outcome_id": item["outcome_id"],
            "outcome_type": item["outcome_type"],
            "unit": item["unit"],
            "favorable_direction": item["favorable_direction"],
            "inference_status": item["inference_status"],
            "block_reason": item["block_reason"],
            "points": item["pair_values"],
            "effect": item["effect"],
        })
    return {
        "schema_version": FIGURE_INPUT_SCHEMA_VERSION,
        "analysis_id": plan.analysis_id,
        "analysis_version": plan.analysis_version,
        "statistics_spec_sha256": summary["statistics_spec_sha256"],
        "matrix_spec_sha256": plan.matrix_spec_sha256,
        "matrix_run_index_sha256": plan.matrix_run_index_sha256,
        "source_git_sha": plan.source_git_sha,
        "evidence_scope": plan.evidence_scope,
        "expected_pair_count": plan.expected_pair_count,
        "run_status_counts": summary["run_status_counts"],
        "blocked_outcomes": summary["blocked_outcomes"],
        "series": series,
        "paper_data_ready": False,
        "claim_boundary": plan.claim_boundary,
    }


def _prepare_output_root(output_root: Path, matrix_root: Path) -> Path:
    output_root = output_root.resolve()
    if not output_root.is_relative_to(matrix_root):
        raise StatisticsIntegrityError("output root必須位於dedicated matrix root內")
    if output_root.exists():
        if not output_root.is_dir() or any(output_root.iterdir()):
            raise StatisticsIntegrityError("output root必須不存在或為空目錄")
    else:
        output_root.mkdir(parents=True)
    return output_root


def _blocked_receipt(
    plan: PairedStatisticsSpec,
    matrix_receipt: dict[str, Any],
    *,
    output_root: Path,
    matrix_receipt_path: Path,
    statistics_spec_sha256: str,
) -> dict[str, Any]:
    artifact = _artifact_record(
        output_root,
        matrix_receipt_path,
        role="matrix_completeness_receipt",
    )
    payload = {
        "schema_version": STATISTICS_RECEIPT_SCHEMA_VERSION,
        "analysis_id": plan.analysis_id,
        "analysis_version": plan.analysis_version,
        "validation_status": "BLOCKED_UPSTREAM_MATRIX",
        "contract_valid": False,
        "statistics_ready": False,
        "paper_inputs_generated": False,
        "paper_data_ready": False,
        "statistics_spec_sha256": statistics_spec_sha256,
        "matrix_spec_sha256": plan.matrix_spec_sha256,
        "matrix_run_index_sha256": plan.matrix_run_index_sha256,
        "run_status_counts": _arm_status_counts_from_matrix(plan, matrix_receipt),
        "expected_pair_count": plan.expected_pair_count,
        "blocked_outcomes": [item.outcome_id for item in plan.outcomes],
        "cancelled_cells": matrix_receipt.get("cancelled_cells", []),
        "criteria": _criteria(
            upstream_ready=False,
            aggregate_generated=False,
            replay_passed=False,
        ),
        "artifacts": [artifact],
        "source_git_sha": plan.source_git_sha,
        "evidence_scope": plan.evidence_scope,
        "claim_boundary": plan.claim_boundary,
    }
    try:
        return PairedStatisticsReceipt.model_validate(payload).model_dump(mode="json")
    except ValidationError as exc:
        raise StatisticsIntegrityError("invalid blocked statistics receipt schema") from exc


def validate_paired_statistics_bundle(receipt_path: Path) -> dict[str, Any]:
    """Fail closed on aggregate receipt shape, paths, bytes, SHA-256, and replay binding."""

    receipt_path = receipt_path.resolve()
    if receipt_path.name != "statistics_receipt.json":
        raise StatisticsIntegrityError(
            "statistics receipt filename must be statistics_receipt.json"
        )
    receipt = _load_model(receipt_path, PairedStatisticsReceipt)
    root = receipt_path.parent.resolve()
    artifact_paths: set[str] = set()
    artifacts_by_role: dict[str, Path] = {}
    total_bytes = 0
    for record in receipt.artifacts:
        resolved = _validate_output_artifact_path(root, record.path)
        if resolved.stat().st_size != record.bytes:
            raise StatisticsIntegrityError(
                f"aggregate artifact bytes mismatch: {record.path}"
            )
        if sha256_file(resolved) != record.sha256:
            raise StatisticsIntegrityError(
                f"aggregate artifact SHA-256 mismatch: {record.path}"
            )
        artifact_paths.add(record.path)
        artifacts_by_role[record.role] = resolved
        total_bytes += record.bytes

    discovered_files: set[str] = set()
    for path in root.rglob("*"):
        if _is_link_or_junction(path):
            raise StatisticsIntegrityError(
                f"aggregate bundle contains link/reparse point: {path.name}"
            )
        if path.is_file():
            discovered_files.add(path.relative_to(root).as_posix())
    expected_files = artifact_paths | {"statistics_receipt.json"}
    if discovered_files != expected_files:
        raise StatisticsIntegrityError(
            "aggregate bundle has missing or unindexed files: "
            f"{sorted(discovered_files ^ expected_files)}"
        )

    if receipt.validation_status == "STATISTICS_CONTRACT_VALID":
        replay_path = artifacts_by_role["independent_replay_receipt"]
        replay = _load_model(replay_path, PairedStatisticsReplayReceipt)
        replay_hashes = {
            "statistics_spec_sha256": receipt.statistics_spec_sha256,
            "paired_raw_table_sha256": sha256_file(
                artifacts_by_role["paired_raw_table"]
            ),
            "statistics_summary_sha256": sha256_file(
                artifacts_by_role["statistics_summary"]
            ),
            "paper_table_input_sha256": sha256_file(
                artifacts_by_role["table_input"]
            ),
            "paper_figure_input_sha256": sha256_file(
                artifacts_by_role["figure_input"]
            ),
        }
        drift = [
            key
            for key, expected in replay_hashes.items()
            if getattr(replay, key) != expected
        ]
        if drift:
            raise StatisticsIntegrityError(
                f"aggregate replay receipt hash drift: {sorted(drift)}"
            )

    return {
        "schema_version": "PAIRED_STATISTICS_BUNDLE_VALIDATION_V1",
        "validation_status": "AGGREGATE_BUNDLE_VALID",
        "artifact_count": len(receipt.artifacts),
        "artifact_bytes": total_bytes,
        "receipt_sha256": sha256_file(receipt_path),
        "contract_valid": receipt.contract_valid,
        "statistics_ready": receipt.statistics_ready,
        "paper_data_ready": False,
        "evidence_scope": receipt.evidence_scope,
        "claim_boundary": receipt.claim_boundary,
    }


def build_paired_statistics_bundle(
    statistics_spec_path: Path,
    matrix_spec_path: Path,
    matrix_index_path: Path,
    output_root: Path,
) -> dict[str, Any]:
    """Build, process-replay, and inventory one aggregate statistics bundle."""

    statistics_spec_path = statistics_spec_path.resolve()
    matrix_spec_path = matrix_spec_path.resolve()
    matrix_index_path = matrix_index_path.resolve()
    if statistics_spec_path.name != "paired_statistics_spec.json":
        raise StatisticsIntegrityError(
            "statistics spec filename必須是paired_statistics_spec.json"
        )
    if not REPLAY_SCRIPT.is_file():
        raise StatisticsIntegrityError("independent replay script is missing")
    matrix_root = matrix_spec_path.parent.resolve()
    if (
        statistics_spec_path.parent.resolve() != matrix_root
        or matrix_index_path.parent.resolve() != matrix_root
    ):
        raise StatisticsIntegrityError("statistics/matrix spec/index必須位於同一root")

    plan = _load_model(statistics_spec_path, PairedStatisticsSpec)
    try:
        matrix = ExperimentMatrixSpec.model_validate(
            load_json_object_strict(matrix_spec_path)
        )
        index = ExperimentMatrixRunIndex.model_validate(
            load_json_object_strict(matrix_index_path)
        )
    except (PaperDataIntegrityError, ValidationError) as exc:
        raise StatisticsIntegrityError(f"invalid upstream matrix schema: {exc}") from exc
    _validate_plan_against_matrix(
        plan,
        matrix,
        matrix_index_path,
        matrix_spec_path,
    )
    _validate_pair_map(plan, matrix)
    output_root = _prepare_output_root(output_root, matrix_root)

    matrix_receipt = validate_experiment_matrix(
        matrix_spec_path,
        matrix_index_path,
    )
    matrix_receipt_path = output_root / "matrix_completeness_receipt.json"
    _write_json(matrix_receipt_path, matrix_receipt)
    if not matrix_receipt["matrix_complete"]:
        raise StatisticsIntegrityError(
            "upstream matrix completeness/integrity gate failed"
        )
    if not matrix_receipt["statistics_input_ready"]:
        receipt = _blocked_receipt(
            plan,
            matrix_receipt,
            output_root=output_root,
            matrix_receipt_path=matrix_receipt_path,
            statistics_spec_sha256=sha256_file(statistics_spec_path),
        )
        receipt_path = output_root / "statistics_receipt.json"
        _write_json(receipt_path, receipt)
        validate_paired_statistics_bundle(receipt_path)
        return receipt

    loaded = _load_metrics_by_cell(matrix_root, matrix, index, plan)
    raw_table = _build_raw_table(
        plan,
        matrix,
        loaded,
        statistics_spec_sha256=sha256_file(statistics_spec_path),
    )
    summary = _summary_payload(plan, raw_table)
    table_input = _table_payload(plan, summary)
    figure_input = _figure_payload(plan, summary)
    output_payloads = {
        "paired_raw_table": ("paired_raw_table.json", raw_table),
        "statistics_summary": ("statistics_summary.json", summary),
        "table_input": ("paper_table_input.json", table_input),
        "figure_input": ("paper_figure_input.json", figure_input),
    }
    for filename, payload in output_payloads.values():
        _write_json(output_root / filename, payload)

    replay_args = [
        sys.executable,
        "-I",
        "-S",
        str(REPLAY_SCRIPT),
        str(statistics_spec_path),
        str(output_root / "paired_raw_table.json"),
        str(output_root / "statistics_summary.json"),
        str(output_root / "paper_table_input.json"),
        str(output_root / "paper_figure_input.json"),
    ]
    try:
        completed = subprocess.run(
            replay_args,
            cwd=matrix_root,
            capture_output=True,
            text=True,
            check=False,
            timeout=REPLAY_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise StatisticsIntegrityError(
            f"independent replay exceeded {REPLAY_TIMEOUT_SECONDS}s timeout"
        ) from exc
    try:
        replay_payload = _load_json_text_strict(
            completed.stdout,
            label="independent replay receipt",
        )
    except StatisticsIntegrityError as exc:
        raise StatisticsIntegrityError("independent replay未輸出valid JSON") from exc
    if completed.returncode != 0 or completed.stderr != "":
        raise StatisticsIntegrityError(
            "independent replay failed: "
            f"returncode={completed.returncode}, stderr={completed.stderr[:500]!r}, "
            f"status={replay_payload.get('status')!r}"
        )
    try:
        replay_model = PairedStatisticsReplayReceipt.model_validate(replay_payload)
    except ValidationError as exc:
        raise StatisticsIntegrityError("invalid independent replay receipt schema") from exc
    replay_receipt = replay_model.model_dump(mode="json")
    expected_replay_hashes = {
        "statistics_spec_sha256": sha256_file(statistics_spec_path),
        "paired_raw_table_sha256": sha256_file(
            output_root / "paired_raw_table.json"
        ),
        "statistics_summary_sha256": sha256_file(
            output_root / "statistics_summary.json"
        ),
        "paper_table_input_sha256": sha256_file(
            output_root / "paper_table_input.json"
        ),
        "paper_figure_input_sha256": sha256_file(
            output_root / "paper_figure_input.json"
        ),
    }
    replay_hash_drift = [
        key
        for key, expected in expected_replay_hashes.items()
        if replay_receipt[key] != expected
    ]
    if replay_hash_drift:
        raise StatisticsIntegrityError(
            f"independent replay hash binding drift: {sorted(replay_hash_drift)}"
        )
    replay_receipt_path = output_root / "replay_receipt.json"
    _write_json(replay_receipt_path, replay_receipt)
    replay_passed = True
    if not replay_passed:
        raise StatisticsIntegrityError(
            "independent replay failed: "
            f"returncode={completed.returncode}, stderr={completed.stderr[:500]!r}"
        )

    artifacts = [
        _artifact_record(
            output_root,
            matrix_receipt_path,
            role="matrix_completeness_receipt",
        ),
        *[
            _artifact_record(output_root, output_root / filename, role=role)
            for role, (filename, _payload) in output_payloads.items()
        ],
        _artifact_record(
            output_root,
            replay_receipt_path,
            role="independent_replay_receipt",
        ),
    ]
    final_matrix_receipt = validate_experiment_matrix(
        matrix_spec_path,
        matrix_index_path,
    )
    if final_matrix_receipt != matrix_receipt:
        raise StatisticsIntegrityError("matrix identity changed during aggregation")
    if (
        sha256_file(statistics_spec_path)
        != raw_table["statistics_spec_sha256"]
    ):
        raise StatisticsIntegrityError("statistics spec changed during aggregation")
    criteria = _criteria(
        upstream_ready=True,
        aggregate_generated=True,
        replay_passed=True,
    )
    contract_valid = all(item["passed"] for item in criteria)
    receipt_payload = {
        "schema_version": STATISTICS_RECEIPT_SCHEMA_VERSION,
        "analysis_id": plan.analysis_id,
        "analysis_version": plan.analysis_version,
        "validation_status": (
            "STATISTICS_CONTRACT_VALID" if contract_valid else "STATISTICS_CONTRACT_INVALID"
        ),
        "contract_valid": contract_valid,
        "statistics_ready": summary["statistics_ready"],
        "paper_inputs_generated": True,
        "paper_data_ready": False,
        "statistics_spec_sha256": sha256_file(statistics_spec_path),
        "matrix_spec_sha256": plan.matrix_spec_sha256,
        "matrix_run_index_sha256": plan.matrix_run_index_sha256,
        "run_status_counts": raw_table["run_status_counts"],
        "expected_pair_count": plan.expected_pair_count,
        "blocked_outcomes": summary["blocked_outcomes"],
        "cancelled_cells": [],
        "criteria": criteria,
        "artifacts": artifacts,
        "source_git_sha": plan.source_git_sha,
        "evidence_scope": plan.evidence_scope,
        "claim_boundary": plan.claim_boundary,
    }
    try:
        receipt = PairedStatisticsReceipt.model_validate(receipt_payload).model_dump(
            mode="json"
        )
    except ValidationError as exc:
        raise StatisticsIntegrityError("invalid statistics receipt schema") from exc
    receipt_path = output_root / "statistics_receipt.json"
    _write_json(receipt_path, receipt)
    validate_paired_statistics_bundle(receipt_path)
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a PAIRED_STATISTICS_SPEC_V1 aggregate bundle"
    )
    parser.add_argument("statistics_spec", type=Path)
    parser.add_argument("matrix_spec", type=Path)
    parser.add_argument("matrix_index", type=Path)
    parser.add_argument("output_root", type=Path)
    args = parser.parse_args()
    try:
        receipt = build_paired_statistics_bundle(
            args.statistics_spec,
            args.matrix_spec,
            args.matrix_index,
            args.output_root,
        )
    except Exception as exc:
        error_receipt = {
            "schema_version": ERROR_RECEIPT_SCHEMA_VERSION,
            "validation_status": "ERROR",
            "contract_valid": False,
            "statistics_ready": False,
            "paper_data_ready": False,
            "error": f"{type(exc).__name__}: {exc}",
        }
        print(json.dumps(error_receipt, ensure_ascii=False, indent=2))
        raise SystemExit(2) from exc
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    raise SystemExit(0 if receipt["statistics_ready"] else 1)


if __name__ == "__main__":
    main()

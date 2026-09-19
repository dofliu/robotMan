"""Standard-library-only replay for paired statistics paper inputs.

The replay intentionally does not import the primary evaluator, Pydantic, NumPy,
MuJoCo, or controller code.  It recomputes every derived statistics/table/figure
payload from the frozen spec and paired raw table, then compares exact JSON values.
"""

from __future__ import annotations

from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import re
import statistics
import sys
from typing import Any


SPEC_SCHEMA = "PAIRED_STATISTICS_SPEC_V1"
RAW_SCHEMA = "PAIRED_RAW_TABLE_V1"
SUMMARY_SCHEMA = "PAIRED_STATISTICS_SUMMARY_V1"
TABLE_SCHEMA = "PAPER_TABLE_INPUT_V1"
FIGURE_SCHEMA = "PAPER_FIGURE_INPUT_V1"
REPLAY_SCHEMA = "PAIRED_STATISTICS_REPLAY_RECEIPT_V1"
REPLAY_ERROR_SCHEMA = "PAIRED_STATISTICS_REPLAY_ERROR_RECEIPT_V1"
CLAIM_BOUNDARY = (
    "SIM_ONLY_MUJOCO / NOT_PHYSICALLY_VALIDATED; paired statistical software "
    "output only, without Study A or formal authorization, controller superiority, "
    "sim-to-real, physical fidelity, safety, or paper-acceptance claims."
)
MAX_JSON_BYTES = 16 * 1024 * 1024
MAX_JSON_DEPTH = 64
MAX_JSON_NODES = 250_000
MAX_PAIRS = 1000
MAX_OUTCOMES = 100
MAX_BOOTSTRAP_DRAWS = 5_000_000
ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{2,95}$")
SHA256_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
GIT_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")


class ReplayError(RuntimeError):
    """Replay input or exact-identity validation failed."""


def _reject_constant(value: str) -> None:
    raise ReplayError(f"JSON non-finite constant is forbidden: {value}")


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ReplayError(f"duplicate JSON key is forbidden: {key}")
        result[key] = value
    return result


def _bounded_int(value: str) -> int:
    if len(value.lstrip("-")) > 1000:
        raise ReplayError("pathological JSON integer is forbidden")
    return int(value)


def _check_tree(root: Any) -> None:
    stack = [(root, 1)]
    nodes = 0
    while stack:
        value, depth = stack.pop()
        nodes += 1
        if nodes > MAX_JSON_NODES:
            raise ReplayError("JSON node limit exceeded")
        if depth > MAX_JSON_DEPTH:
            raise ReplayError("JSON nesting limit exceeded")
        if isinstance(value, dict):
            stack.extend((item, depth + 1) for item in value.values())
        elif isinstance(value, list):
            stack.extend((item, depth + 1) for item in value)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        if not path.is_file():
            raise ReplayError(f"missing JSON artifact: {path.name}")
        if path.stat().st_size > MAX_JSON_BYTES:
            raise ReplayError(f"JSON file exceeds byte limit: {path.name}")
        payload = json.loads(
            path.read_text(encoding="utf-8"),
            parse_constant=_reject_constant,
            parse_int=_bounded_int,
            object_pairs_hook=_reject_duplicate_keys,
        )
        _check_tree(payload)
    except ReplayError:
        raise
    except (OSError, UnicodeError, ValueError, RecursionError) as exc:
        raise ReplayError(f"invalid JSON file: {path.name}") from exc
    if not isinstance(payload, dict):
        raise ReplayError(f"JSON root must be an object: {path.name}")
    return payload


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _require_exact_keys(value: Any, keys: set[str], context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ReplayError(f"{context} must be an object")
    actual = set(value)
    if actual != keys:
        raise ReplayError(
            f"{context} fields mismatch: missing={sorted(keys - actual)}, "
            f"unexpected={sorted(actual - keys)}"
        )
    return value


def _require_string(value: Any, context: str, *, pattern: re.Pattern[str] | None = None) -> str:
    if not isinstance(value, str):
        raise ReplayError(f"{context} must be a string")
    if pattern is not None and pattern.fullmatch(value) is None:
        raise ReplayError(f"{context} has invalid format")
    return value


def _require_int(value: Any, context: str, *, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ReplayError(f"{context} must be an integer in [{minimum}, {maximum}]")
    return value


def _require_number(value: Any, context: str) -> float:
    if type(value) not in {int, float}:
        raise ReplayError(f"{context} must be a number")
    result = float(value)
    if not math.isfinite(result):
        raise ReplayError(f"{context} must be finite")
    return result


def _validate_identity(value: Any, context: str) -> dict[str, Any]:
    item = _require_exact_keys(value, {"identity_id", "sha256"}, context)
    _require_string(item["identity_id"], f"{context}.identity_id", pattern=ID_PATTERN)
    _require_string(item["sha256"], f"{context}.sha256", pattern=SHA256_PATTERN)
    return item


def _validate_outcome(value: Any, index: int) -> dict[str, Any]:
    context = f"spec.outcomes[{index}]"
    item = _require_exact_keys(
        value,
        {
            "outcome_id",
            "role",
            "outcome_type",
            "unit",
            "favorable_direction",
            "estimand",
            "confidence_level",
            "interval_method",
            "bootstrap_seed",
            "bootstrap_resamples",
            "minimum_pairs",
            "missing_policy",
            "nonfinite_policy",
            "censoring_policy",
            "terminal_failure_policy",
        },
        context,
    )
    _require_string(item["outcome_id"], f"{context}.outcome_id", pattern=ID_PATTERN)
    if item["role"] not in {"PRIMARY", "SECONDARY"}:
        raise ReplayError(f"{context}.role is invalid")
    if item["outcome_type"] not in {"CONTINUOUS", "BINARY"}:
        raise ReplayError(f"{context}.outcome_type is invalid")
    if not isinstance(item["unit"], str) or not 1 <= len(item["unit"]) <= 80:
        raise ReplayError(f"{context}.unit is invalid")
    if item["favorable_direction"] not in {"HIGHER", "LOWER", "NEUTRAL"}:
        raise ReplayError(f"{context}.favorable_direction is invalid")
    if type(item["confidence_level"]) is not float or item["confidence_level"] != 0.95:
        raise ReplayError(f"{context}.confidence_level must be 0.95")
    _require_int(item["minimum_pairs"], f"{context}.minimum_pairs", minimum=2, maximum=MAX_PAIRS)
    for field in ("missing_policy", "nonfinite_policy", "censoring_policy"):
        if item[field] != "PRESERVE_AND_BLOCK":
            raise ReplayError(f"{context}.{field} is not frozen")
    if item["outcome_type"] == "CONTINUOUS":
        if (
            item["estimand"] != "PAIRED_MEAN_DIFFERENCE"
            or item["interval_method"] != "PAIRED_PERCENTILE_BOOTSTRAP_V1"
            or item["terminal_failure_policy"] != "PRESERVE_EXPLICIT_STATE_V1"
        ):
            raise ReplayError(f"{context} continuous semantics drift")
        _require_int(item["bootstrap_seed"], f"{context}.bootstrap_seed", minimum=0, maximum=2**63 - 1)
        _require_int(item["bootstrap_resamples"], f"{context}.bootstrap_resamples", minimum=1000, maximum=200000)
    else:
        if (
            item["estimand"] != "PAIRED_RISK_DIFFERENCE"
            or item["interval_method"] != "PAIRED_BINARY_CI_NOT_IMPLEMENTED_V1"
            or item["bootstrap_seed"] is not None
            or item["bootstrap_resamples"] is not None
        ):
            raise ReplayError(f"{context} binary semantics drift")
        if item["terminal_failure_policy"] not in {
            "PRESERVE_EXPLICIT_STATE_V1",
            "REQUIRE_EXPLICIT_FALSE_FOR_FAILED_V1",
        }:
            raise ReplayError(f"{context} binary failure mapping drift")
    return item


def _validate_spec(spec: dict[str, Any], spec_path: Path) -> list[dict[str, Any]]:
    _require_exact_keys(
        spec,
        {
            "schema_version",
            "analysis_id",
            "analysis_version",
            "matrix_id",
            "matrix_version",
            "matrix_spec_sha256",
            "matrix_run_index_sha256",
            "source_git_sha",
            "source_dirty",
            "run_class",
            "data_partition",
            "evidence_scope",
            "claim_boundary",
            "metric_set_id",
            "evaluator_id",
            "reference_controller",
            "candidate_controller",
            "expected_pair_count",
            "pairs",
            "outcomes",
            "resampling_algorithm",
            "quantile_method",
            "failure_semantics_id",
        },
        "spec",
    )
    if spec_path.name != "paired_statistics_spec.json":
        raise ReplayError("statistics spec filename is not frozen")
    if spec["schema_version"] != SPEC_SCHEMA:
        raise ReplayError("statistics spec schema version mismatch")
    for field in ("analysis_id", "analysis_version", "matrix_id", "matrix_version", "metric_set_id", "evaluator_id"):
        _require_string(spec[field], f"spec.{field}", pattern=ID_PATTERN)
    for field in ("matrix_spec_sha256", "matrix_run_index_sha256"):
        _require_string(spec[field], f"spec.{field}", pattern=SHA256_PATTERN)
    _require_string(spec["source_git_sha"], "spec.source_git_sha", pattern=GIT_SHA_PATTERN)
    if spec["source_dirty"] is not False:
        raise ReplayError("spec.source_dirty must be false")
    if spec["run_class"] not in {"DEVELOPMENT", "CALIBRATION", "FORMAL_EVALUATION", "REGRESSION"}:
        raise ReplayError("spec.run_class is invalid")
    if spec["data_partition"] not in {"DEVELOPMENT", "CALIBRATION", "HOLDOUT", "REGRESSION"}:
        raise ReplayError("spec.data_partition is invalid")
    if spec["evidence_scope"] != "SIM_ONLY_MUJOCO" or spec["claim_boundary"] != CLAIM_BOUNDARY:
        raise ReplayError("spec evidence/claim boundary drift")
    reference_controller = _validate_identity(spec["reference_controller"], "spec.reference_controller")
    candidate_controller = _validate_identity(spec["candidate_controller"], "spec.candidate_controller")
    if (
        reference_controller == candidate_controller
        or reference_controller["identity_id"]
        == candidate_controller["identity_id"]
    ):
        raise ReplayError("reference and candidate controllers must differ")
    expected_pair_count = _require_int(spec["expected_pair_count"], "spec.expected_pair_count", minimum=1, maximum=MAX_PAIRS)
    if not isinstance(spec["pairs"], list) or len(spec["pairs"]) != expected_pair_count:
        raise ReplayError("spec pair count mismatch")
    pair_ids: set[str] = set()
    cell_ids: set[str] = set()
    for index, value in enumerate(spec["pairs"]):
        item = _require_exact_keys(value, {"pair_id", "reference_cell_id", "candidate_cell_id"}, f"spec.pairs[{index}]")
        for field in ("pair_id", "reference_cell_id", "candidate_cell_id"):
            _require_string(item[field], f"spec.pairs[{index}].{field}", pattern=ID_PATTERN)
        if item["reference_cell_id"] == item["candidate_cell_id"]:
            raise ReplayError("pair cannot reuse one cell on both arms")
        if item["pair_id"] in pair_ids:
            raise ReplayError("duplicate pair_id")
        if item["reference_cell_id"] in cell_ids or item["candidate_cell_id"] in cell_ids:
            raise ReplayError("matrix cell reused across pairs")
        pair_ids.add(item["pair_id"])
        cell_ids.update((item["reference_cell_id"], item["candidate_cell_id"]))
    if not isinstance(spec["outcomes"], list) or not 1 <= len(spec["outcomes"]) <= MAX_OUTCOMES:
        raise ReplayError("spec outcomes count is invalid")
    outcomes = [_validate_outcome(value, index) for index, value in enumerate(spec["outcomes"])]
    if len({item["outcome_id"] for item in outcomes}) != len(outcomes):
        raise ReplayError("duplicate outcome_id")
    bootstrap_draws = sum(
        item["bootstrap_resamples"] * expected_pair_count
        for item in outcomes
        if item["bootstrap_resamples"] is not None
    )
    if bootstrap_draws > MAX_BOOTSTRAP_DRAWS:
        raise ReplayError("bootstrap workload exceeds bounded V1 draw budget")
    if spec["resampling_algorithm"] != "SHA256_REJECTION_V1" or spec["quantile_method"] != "LINEAR_TYPE7_V1":
        raise ReplayError("spec resampling semantics drift")
    if spec["failure_semantics_id"] != "PAIRED_FAILURE_RETENTION_V1":
        raise ReplayError("spec failure semantics drift")
    return outcomes


def _validate_measurement(value: Any, outcome: dict[str, Any], context: str) -> None:
    item = _require_exact_keys(
        value,
        {"outcome_id", "outcome_type", "unit", "state", "value", "reason", "censoring_side", "censoring_bound"},
        context,
    )
    if item["outcome_id"] != outcome["outcome_id"] or item["outcome_type"] != outcome["outcome_type"] or item["unit"] != outcome["unit"]:
        raise ReplayError(f"{context} outcome identity drift")
    state = item["state"]
    if state not in {"OBSERVED", "NULL", "NONFINITE", "CENSORED"}:
        raise ReplayError(f"{context}.state is invalid")
    if state == "OBSERVED":
        if item["reason"] is not None or item["censoring_side"] is not None or item["censoring_bound"] is not None:
            raise ReplayError(f"{context} observed payload is invalid")
        if outcome["outcome_type"] == "BINARY":
            if type(item["value"]) is not bool:
                raise ReplayError(f"{context} binary value must be boolean")
        else:
            _require_number(item["value"], f"{context}.value")
        return
    if item["value"] is not None or not isinstance(item["reason"], str) or not 1 <= len(item["reason"]) <= 500:
        raise ReplayError(f"{context} non-observed payload is invalid")
    if state == "CENSORED":
        if outcome["outcome_type"] != "CONTINUOUS" or item["censoring_side"] not in {"LEFT", "RIGHT"}:
            raise ReplayError(f"{context} censoring semantics are invalid")
        _require_number(item["censoring_bound"], f"{context}.censoring_bound")
    elif item["censoring_side"] is not None or item["censoring_bound"] is not None:
        raise ReplayError(f"{context} NULL/NONFINITE cannot carry censoring payload")


def _validate_arm(value: Any, expected_cell_id: str, outcomes: list[dict[str, Any]], context: str) -> dict[str, Any]:
    arm = _require_exact_keys(
        value,
        {"cell_id", "run_id", "run_status", "failure_record_count", "manifest_path", "manifest_sha256", "metrics_sha256", "raw_trace_sha256", "measurements"},
        context,
    )
    if arm["cell_id"] != expected_cell_id:
        raise ReplayError(f"{context}.cell_id drift")
    _require_string(arm["run_id"], f"{context}.run_id", pattern=ID_PATTERN)
    if arm["run_status"] not in {"COMPLETED", "FAILED", "CANCELLED"}:
        raise ReplayError(f"{context}.run_status is invalid")
    failures = _require_int(arm["failure_record_count"], f"{context}.failure_record_count", minimum=0, maximum=1000)
    if (arm["run_status"] == "COMPLETED" and failures != 0) or (arm["run_status"] in {"FAILED", "CANCELLED"} and failures == 0):
        raise ReplayError(f"{context} terminal failure count mismatch")
    if arm["run_status"] == "CANCELLED":
        raise ReplayError("replay aggregate cannot contain CANCELLED cells")
    _require_string(arm["manifest_path"], f"{context}.manifest_path")
    for field in ("manifest_sha256", "metrics_sha256", "raw_trace_sha256"):
        _require_string(arm[field], f"{context}.{field}", pattern=SHA256_PATTERN)
    if not isinstance(arm["measurements"], list) or len(arm["measurements"]) != len(outcomes):
        raise ReplayError(f"{context}.measurements count mismatch")
    by_id: dict[str, dict[str, Any]] = {}
    for index, measurement in enumerate(arm["measurements"]):
        if not isinstance(measurement, dict) or not isinstance(measurement.get("outcome_id"), str):
            raise ReplayError(f"{context}.measurements[{index}] is invalid")
        outcome_id = measurement["outcome_id"]
        if outcome_id in by_id:
            raise ReplayError(f"{context} duplicate measurement")
        by_id[outcome_id] = measurement
    if set(by_id) != {item["outcome_id"] for item in outcomes}:
        raise ReplayError(f"{context} measurement outcome set mismatch")
    for outcome in outcomes:
        measurement = by_id[outcome["outcome_id"]]
        _validate_measurement(measurement, outcome, f"{context}.{outcome['outcome_id']}")
        if (
            arm["run_status"] == "FAILED"
            and outcome["outcome_type"] == "BINARY"
            and outcome["terminal_failure_policy"]
            == "REQUIRE_EXPLICIT_FALSE_FOR_FAILED_V1"
            and (measurement["state"] != "OBSERVED" or measurement["value"] is not False)
        ):
            raise ReplayError(f"{context} FAILED binary outcome must be explicit false")
    return arm


def _validate_raw(raw: dict[str, Any], spec: dict[str, Any], outcomes: list[dict[str, Any]], spec_sha256: str) -> list[dict[str, Any]]:
    _require_exact_keys(
        raw,
        {"schema_version", "analysis_id", "analysis_version", "matrix_id", "matrix_version", "statistics_spec_sha256", "matrix_spec_sha256", "matrix_run_index_sha256", "source_git_sha", "evidence_scope", "expected_pair_count", "pair_count", "run_status_counts", "pairs", "claim_boundary"},
        "raw_table",
    )
    expected_identity = {
        "schema_version": RAW_SCHEMA,
        "analysis_id": spec["analysis_id"],
        "analysis_version": spec["analysis_version"],
        "matrix_id": spec["matrix_id"],
        "matrix_version": spec["matrix_version"],
        "statistics_spec_sha256": spec_sha256,
        "matrix_spec_sha256": spec["matrix_spec_sha256"],
        "matrix_run_index_sha256": spec["matrix_run_index_sha256"],
        "source_git_sha": spec["source_git_sha"],
        "evidence_scope": spec["evidence_scope"],
        "expected_pair_count": spec["expected_pair_count"],
        "claim_boundary": spec["claim_boundary"],
    }
    drift = [key for key, expected in expected_identity.items() if raw[key] != expected]
    if drift:
        raise ReplayError(f"raw table identity drift: {sorted(drift)}")
    if type(raw["pair_count"]) is not int or raw["pair_count"] != spec["expected_pair_count"]:
        raise ReplayError("raw pair_count mismatch")
    if not isinstance(raw["pairs"], list) or len(raw["pairs"]) != raw["pair_count"]:
        raise ReplayError("raw pairs length mismatch")
    spec_pairs = {item["pair_id"]: item for item in spec["pairs"]}
    raw_pair_ids: set[str] = set()
    pairs: list[dict[str, Any]] = []
    for index, value in enumerate(raw["pairs"]):
        context = f"raw_table.pairs[{index}]"
        pair = _require_exact_keys(
            value,
            {"pair_id", "scenario_id", "replicate_id", "evaluation_seed", "environment_seed", "scenario_seed", "scenario", "reference", "candidate"},
            context,
        )
        pair_id = _require_string(pair["pair_id"], f"{context}.pair_id", pattern=ID_PATTERN)
        if pair_id in raw_pair_ids or pair_id not in spec_pairs:
            raise ReplayError(f"{context}.pair_id is duplicate or unexpected")
        raw_pair_ids.add(pair_id)
        _require_string(pair["scenario_id"], f"{context}.scenario_id", pattern=ID_PATTERN)
        _require_string(pair["replicate_id"], f"{context}.replicate_id", pattern=ID_PATTERN)
        for field in ("evaluation_seed", "environment_seed", "scenario_seed"):
            if pair[field] is not None:
                _require_int(pair[field], f"{context}.{field}", minimum=0, maximum=2**63 - 1)
        if not isinstance(pair["scenario"], dict) or not 1 <= len(pair["scenario"]) <= 100:
            raise ReplayError(f"{context}.scenario is invalid")
        for key, scenario_value in pair["scenario"].items():
            if not isinstance(key, str) or type(scenario_value) not in {str, int, float, bool}:
                raise ReplayError(f"{context}.scenario value is invalid")
            if type(scenario_value) is float and not math.isfinite(scenario_value):
                raise ReplayError(f"{context}.scenario value is non-finite")
        mapping = spec_pairs[pair_id]
        pair["reference"] = _validate_arm(pair["reference"], mapping["reference_cell_id"], outcomes, f"{context}.reference")
        pair["candidate"] = _validate_arm(pair["candidate"], mapping["candidate_cell_id"], outcomes, f"{context}.candidate")
        pairs.append(pair)
    if raw_pair_ids != set(spec_pairs) or [item["pair_id"] for item in pairs] != sorted(spec_pairs):
        raise ReplayError("raw pair map/order mismatch")
    expected_status_counts = {
        role: {
            status: sum(pair[role]["run_status"] == status for pair in pairs)
            for status in ("COMPLETED", "FAILED", "CANCELLED")
        }
        for role in ("reference", "candidate")
    }
    if raw["run_status_counts"] != expected_status_counts:
        raise ReplayError("raw run_status_counts mismatch")
    return pairs


def _mean(values: list[float]) -> float:
    try:
        result = math.fsum(values) / len(values)
    except OverflowError as exc:
        raise ReplayError("derived mean overflowed") from exc
    if not math.isfinite(result):
        raise ReplayError("derived mean is non-finite")
    return result


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    midpoint = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[midpoint]
    try:
        result = math.fsum((ordered[midpoint - 1], ordered[midpoint])) / 2.0
    except OverflowError as exc:
        raise ReplayError("derived median overflowed") from exc
    if not math.isfinite(result):
        raise ReplayError("derived median is non-finite")
    return result


def _uniform_index(*, seed: int, replicate: int, draw: int, population_size: int) -> int:
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
    return math.fsum((ordered[lower_index] * (1.0 - fraction), ordered[upper_index] * fraction))


def _bootstrap_interval(differences: list[float], outcome: dict[str, Any]) -> dict[str, Any]:
    estimates: list[float] = []
    for replicate in range(outcome["bootstrap_resamples"]):
        sample = [
            differences[_uniform_index(seed=outcome["bootstrap_seed"], replicate=replicate, draw=draw, population_size=len(differences))]
            for draw in range(len(differences))
        ]
        estimates.append(_mean(sample))
    alpha = 1.0 - outcome["confidence_level"]
    return {
        "confidence_level": outcome["confidence_level"],
        "method": "PAIRED_PERCENTILE_BOOTSTRAP_V1",
        "resampling_algorithm": "SHA256_REJECTION_V1",
        "quantile_method": "LINEAR_TYPE7_V1",
        "seed": outcome["bootstrap_seed"],
        "resamples": outcome["bootstrap_resamples"],
        "lower": _type7_quantile(estimates, alpha / 2.0),
        "upper": _type7_quantile(estimates, 1.0 - alpha / 2.0),
    }


def _wilson_interval(successes: int, total: int, confidence_level: float) -> dict[str, Any]:
    proportion = successes / total
    alpha = 1.0 - confidence_level
    z = statistics.NormalDist().inv_cdf(1.0 - alpha / 2.0)
    z_squared = z * z
    denominator = 1.0 + z_squared / total
    center = (proportion + z_squared / (2.0 * total)) / denominator
    half_width = z * math.sqrt(proportion * (1.0 - proportion) / total + z_squared / (4.0 * total * total)) / denominator
    return {
        "successes": successes,
        "total": total,
        "proportion": proportion,
        "confidence_level": confidence_level,
        "method": "WILSON_SCORE_V1",
        "lower": max(0.0, center - half_width),
        "upper": min(1.0, center + half_width),
    }


def _blocked_effect(outcome: dict[str, Any], reason: str) -> dict[str, Any]:
    return {
        "estimand": outcome["estimand"],
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


def _outcome_summary(outcome: dict[str, Any], pairs: list[dict[str, Any]]) -> dict[str, Any]:
    reference_states: Counter[str] = Counter()
    candidate_states: Counter[str] = Counter()
    nonestimable_pair_ids: list[str] = []
    reference_values: list[float] = []
    candidate_values: list[float] = []
    differences: list[float] = []
    pair_values: list[dict[str, Any]] = []
    for pair in pairs:
        reference = next(item for item in pair["reference"]["measurements"] if item["outcome_id"] == outcome["outcome_id"])
        candidate = next(item for item in pair["candidate"]["measurements"] if item["outcome_id"] == outcome["outcome_id"])
        reference_states[reference["state"]] += 1
        candidate_states[candidate["state"]] += 1
        difference = None
        if reference["state"] == candidate["state"] == "OBSERVED":
            reference_value = float(reference["value"])
            candidate_value = float(candidate["value"])
            difference = candidate_value - reference_value
            if not math.isfinite(difference):
                raise ReplayError(
                    "finite observations produced non-finite paired difference: "
                    f"{pair['pair_id']}:{outcome['outcome_id']}"
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
            "reference_failure_record_count": pair["reference"]["failure_record_count"],
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
            "candidate_failure_record_count": pair["candidate"]["failure_record_count"],
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
        "outcome_id": outcome["outcome_id"],
        "role": outcome["role"],
        "outcome_type": outcome["outcome_type"],
        "unit": outcome["unit"],
        "favorable_direction": outcome["favorable_direction"],
        "expected_pair_count": len(pairs),
        "complete_pair_count": len(differences),
        "reference_state_counts": {state: reference_states.get(state, 0) for state in ("OBSERVED", "NULL", "NONFINITE", "CENSORED")},
        "candidate_state_counts": {state: candidate_states.get(state, 0) for state in ("OBSERVED", "NULL", "NONFINITE", "CENSORED")},
        "nonestimable_pair_ids": nonestimable_pair_ids,
        "pair_values": pair_values,
    }
    if nonestimable_pair_ids:
        return {**common, "inference_status": "BLOCKED_NONOBSERVED", "block_reason": "PRESERVE_AND_BLOCK", "reference_summary": None, "candidate_summary": None, "paired_binary_counts": None, "effect": _blocked_effect(outcome, "BLOCKED_NONOBSERVED")}
    if len(differences) < outcome["minimum_pairs"]:
        if outcome["outcome_type"] == "BINARY":
            (
                reference_summary,
                candidate_summary,
                paired_binary_counts,
            ) = _binary_descriptives(
                reference_values,
                candidate_values,
                outcome["confidence_level"],
            )
        else:
            reference_summary = None
            candidate_summary = None
            paired_binary_counts = None
        return {
            **common,
            "inference_status": "BLOCKED_MINIMUM_PAIRS",
            "block_reason": f"complete_pair_count={len(differences)} < minimum_pairs={outcome['minimum_pairs']}",
            "reference_summary": reference_summary,
            "candidate_summary": candidate_summary,
            "paired_binary_counts": paired_binary_counts,
            "effect": _blocked_effect(outcome, "BLOCKED_MINIMUM_PAIRS"),
        }
    effect: dict[str, Any] = {
        "estimand": outcome["estimand"],
        "direction": "CANDIDATE_MINUS_REFERENCE",
        "estimate": _mean(differences),
        "median_difference": _median(differences),
    }
    paired_binary_counts = None
    if outcome["outcome_type"] == "CONTINUOUS":
        effect["confidence_interval"] = _bootstrap_interval(differences, outcome)
        effect["confidence_interval_null_reason"] = None
        try:
            sample_sd = statistics.stdev(differences)
        except (AttributeError, OverflowError, statistics.StatisticsError) as exc:
            raise ReplayError(
                f"derived sample SD failed: {outcome['outcome_id']}"
            ) from exc
        if not math.isfinite(sample_sd):
            raise ReplayError(
                f"derived sample SD is non-finite: {outcome['outcome_id']}"
            )
        effect["cohen_dz"] = None if sample_sd == 0.0 else effect["estimate"] / sample_sd
        if effect["cohen_dz"] is not None and not math.isfinite(effect["cohen_dz"]):
            raise ReplayError(
                f"derived Cohen dz is non-finite: {outcome['outcome_id']}"
            )
        effect["cohen_dz_null_reason"] = "ZERO_VARIANCE" if sample_sd == 0.0 else None
        reference_summary = {"mean": _mean(reference_values), "median": _median(reference_values)}
        candidate_summary = {"mean": _mean(candidate_values), "median": _median(candidate_values)}
        inference_status = "READY"
        block_reason = None
    else:
        effect["confidence_interval"] = None
        effect["confidence_interval_null_reason"] = "PAIRED_BINARY_CI_NOT_IMPLEMENTED_V1"
        effect["cohen_dz"] = None
        effect["cohen_dz_null_reason"] = "NOT_APPLICABLE_BINARY"
        (
            reference_summary,
            candidate_summary,
            paired_binary_counts,
        ) = _binary_descriptives(
            reference_values,
            candidate_values,
            outcome["confidence_level"],
        )
        inference_status = "BLOCKED_BINARY_CI_METHOD"
        block_reason = "PAIRED_BINARY_CI_NOT_IMPLEMENTED_V1"
    return {
        **common,
        "inference_status": inference_status,
        "block_reason": block_reason,
        "reference_summary": reference_summary,
        "candidate_summary": candidate_summary,
        "paired_binary_counts": paired_binary_counts,
        "effect": effect,
    }


def _build_outputs(spec: dict[str, Any], raw: dict[str, Any], outcomes: list[dict[str, Any]], pairs: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    outcome_summaries = [_outcome_summary(outcome, pairs) for outcome in outcomes]
    blocked_outcomes = [item["outcome_id"] for item in outcome_summaries if item["inference_status"] != "READY"]
    summary = {
        "schema_version": SUMMARY_SCHEMA,
        "analysis_id": spec["analysis_id"],
        "analysis_version": spec["analysis_version"],
        "statistics_spec_sha256": raw["statistics_spec_sha256"],
        "matrix_spec_sha256": spec["matrix_spec_sha256"],
        "matrix_run_index_sha256": spec["matrix_run_index_sha256"],
        "source_git_sha": spec["source_git_sha"],
        "evidence_scope": spec["evidence_scope"],
        "statistics_ready": not blocked_outcomes,
        "expected_pair_count": spec["expected_pair_count"],
        "run_status_counts": raw["run_status_counts"],
        "blocked_outcomes": blocked_outcomes,
        "outcomes": outcome_summaries,
        "paper_data_ready": False,
        "claim_boundary": spec["claim_boundary"],
    }
    rows = [
        {
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
        }
        for item in outcome_summaries
    ]
    table = {
        "schema_version": TABLE_SCHEMA,
        "analysis_id": spec["analysis_id"],
        "analysis_version": spec["analysis_version"],
        "statistics_spec_sha256": raw["statistics_spec_sha256"],
        "matrix_spec_sha256": spec["matrix_spec_sha256"],
        "matrix_run_index_sha256": spec["matrix_run_index_sha256"],
        "source_git_sha": spec["source_git_sha"],
        "evidence_scope": spec["evidence_scope"],
        "expected_pair_count": spec["expected_pair_count"],
        "run_status_counts": raw["run_status_counts"],
        "blocked_outcomes": blocked_outcomes,
        "rows": rows,
        "paper_data_ready": False,
        "claim_boundary": spec["claim_boundary"],
    }
    series = [
        {
            "outcome_id": item["outcome_id"],
            "outcome_type": item["outcome_type"],
            "unit": item["unit"],
            "favorable_direction": item["favorable_direction"],
            "inference_status": item["inference_status"],
            "block_reason": item["block_reason"],
            "points": item["pair_values"],
            "effect": item["effect"],
        }
        for item in outcome_summaries
    ]
    figure = {
        "schema_version": FIGURE_SCHEMA,
        "analysis_id": spec["analysis_id"],
        "analysis_version": spec["analysis_version"],
        "statistics_spec_sha256": raw["statistics_spec_sha256"],
        "matrix_spec_sha256": spec["matrix_spec_sha256"],
        "matrix_run_index_sha256": spec["matrix_run_index_sha256"],
        "source_git_sha": spec["source_git_sha"],
        "evidence_scope": spec["evidence_scope"],
        "expected_pair_count": spec["expected_pair_count"],
        "run_status_counts": raw["run_status_counts"],
        "blocked_outcomes": blocked_outcomes,
        "series": series,
        "paper_data_ready": False,
        "claim_boundary": spec["claim_boundary"],
    }
    return summary, table, figure


def _run(paths: list[Path]) -> dict[str, Any]:
    spec_path, raw_path, summary_path, table_path, figure_path = paths
    spec = _load_json(spec_path)
    outcomes = _validate_spec(spec, spec_path)
    raw = _load_json(raw_path)
    pairs = _validate_raw(raw, spec, outcomes, _sha256_file(spec_path))
    actual_summary = _load_json(summary_path)
    actual_table = _load_json(table_path)
    actual_figure = _load_json(figure_path)
    expected_summary, expected_table, expected_figure = _build_outputs(spec, raw, outcomes, pairs)
    checks = {
        "statistics_summary": actual_summary == expected_summary,
        "paper_table_input": actual_table == expected_table,
        "paper_figure_input": actual_figure == expected_figure,
    }
    exact_identity = all(checks.values())
    if not exact_identity:
        raise ReplayError(f"derived output mismatch: {[key for key, passed in checks.items() if not passed]}")
    return {
        "schema_version": REPLAY_SCHEMA,
        "status": "PASS",
        "exact_identity": True,
        "checks": checks,
        "statistics_spec_sha256": _sha256_file(spec_path),
        "paired_raw_table_sha256": _sha256_file(raw_path),
        "statistics_summary_sha256": _sha256_file(summary_path),
        "paper_table_input_sha256": _sha256_file(table_path),
        "paper_figure_input_sha256": _sha256_file(figure_path),
        "paper_data_ready": False,
        "claim_boundary": CLAIM_BOUNDARY,
    }


def main() -> None:
    if len(sys.argv) != 6:
        receipt = {
            "schema_version": REPLAY_ERROR_SCHEMA,
            "status": "ERROR",
            "exact_identity": False,
            "error": "expected five input paths",
            "paper_data_ready": False,
            "claim_boundary": CLAIM_BOUNDARY,
        }
        print(json.dumps(receipt, ensure_ascii=False, indent=2))
        raise SystemExit(2)
    try:
        receipt = _run([Path(value).resolve() for value in sys.argv[1:]])
    except Exception as exc:
        receipt = {
            "schema_version": REPLAY_ERROR_SCHEMA,
            "status": "ERROR",
            "exact_identity": False,
            "error": f"{type(exc).__name__}: {exc}"[:1000],
            "paper_data_ready": False,
            "claim_boundary": CLAIM_BOUNDARY,
        }
        print(json.dumps(receipt, ensure_ascii=False, indent=2))
        raise SystemExit(2) from exc
    print(json.dumps(receipt, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

"""Read-only early-termination / exposure-censoring validity audit for the v7 pilot.

The audit consumes an already retained ``V7_PILOT_EVIDENCE_RECEIPT_V1`` bundle.
It launches no training, no evaluation and no simulation, it never writes into
the audited bundle, and it re-hashes every consumed source artifact before and
after the audit so that read-only access is checkable rather than asserted.

The module deliberately imports nothing from ``v7_pilot_contract``.  An audit
that reused the audited pipeline's own validators and derivations would only
restate that pipeline's assumptions, so the strict loaders, the exposure
reconstruction and the phase schedule are re-derived here from the frozen
``AUDIT-V7-EXPOSURE-CENSORING-V1`` protocol.

A second ``python -I -S`` process reconstructs the audit summary from the same
canonical raw episode rows and must reach exact JSON identity.
"""

from __future__ import annotations

from collections import Counter
import argparse
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import statistics
import subprocess
import sys
from typing import Any


AUDIT_PROTOCOL_SCHEMA = "V7_EXPOSURE_CENSORING_AUDIT_PROTOCOL_V1"
AUDIT_PROTOCOL_ID = "AUDIT-V7-EXPOSURE-CENSORING-V1"
AUDIT_PROTOCOL_SHA256 = (
    "sha256:ab40cb577b43c9befbc6c0d2850bc98b8d5ba89e93acb0b7804dce6aafb109dd"
)
SUMMARY_SCHEMA = "V7_EXPOSURE_AUDIT_SUMMARY_V1"
SOURCE_INDEX_SCHEMA = "V7_EXPOSURE_AUDIT_SOURCE_INDEX_V1"
RECEIPT_SCHEMA = "V7_EXPOSURE_AUDIT_RECEIPT_V1"
REPLAY_SCHEMA = "V7_EXPOSURE_AUDIT_REPLAY_RECEIPT_V1"
VALIDATION_SCHEMA = "V7_EXPOSURE_AUDIT_VALIDATION_V1"
ERROR_SCHEMA = "V7_EXPOSURE_AUDIT_ERROR_RECEIPT_V1"

PILOT_PROTOCOL_ID = "PILOT-V7-ACTION-INTERFACE-DEV-V1"
PILOT_RAW_SCHEMA = "V7_PILOT_RAW_EPISODES_V1"
PILOT_SUMMARY_SCHEMA = "V7_PILOT_SUMMARY_V1"
PILOT_RECEIPT_SCHEMA = "V7_PILOT_EVIDENCE_RECEIPT_V1"
FROZEN_PILOT_RECEIPT_SHA256 = (
    "sha256:ed3e3eaa7c86f2b855d24aca68b09ce45bce61ac2fb6e573328b12157d758435"
)
DEVELOPMENT_BUNDLE_CLASS = "V7_PILOT_DEVELOPMENT_BUNDLE"
SYNTHETIC_BUNDLE_CLASS = "SYNTHETIC_REGRESSION_BUNDLE"
BUNDLE_CLASSES = (DEVELOPMENT_BUNDLE_CLASS, SYNTHETIC_BUNDLE_CLASS)

CLAIM_BOUNDARY = (
    "SIM_ONLY_MUJOCO / NOT_PHYSICALLY_VALIDATED / DEVELOPMENT_ONLY. This audit "
    "may support only a statement about the internal validity of the retained "
    "v7 pilot contrast under unequal realized exposure. It creates no new "
    "performance result, selects no candidate arm, and does not support "
    "controller superiority, method-population power, formal sample-size "
    "adequacy, paper readiness, physical torque or thermal margins, safety, or "
    "sim-to-real claims."
)

REFERENCE_ARM_ID = "V7A_REWARD_ONLY"
CANDIDATE_ARM_IDS = ("V7B_REDUCED_JOINT_ENVELOPE", "V7C_FILTERED_ACTION")
ARM_IDS = (REFERENCE_ARM_ID,) + CANDIDATE_ARM_IDS
EXPECTED_SEEDS = tuple(range(18000, 18030))
RETIRED_SEED_RANGE = range(19000, 19030)
SEALED_SEED_RANGE = range(20000, 20030)
RETAINED_TERMINAL_STATES = ("COMPLETED", "FAILED", "CANCELLED")
RETAINED_OUTCOME_STATES = ("OBSERVED", "NULL", "NONFINITE")
PRIMARY_MEASUREMENT_ID = "saturation_duty_pct"

EXPOSURE_CLASSES = ("FULL_EXPOSURE", "EARLY_TERMINATED", "NO_EXPOSURE")
COMPARABILITY_STATES = (
    "COMPARABLE",
    "EXPOSURE_CENSORED",
    "METHOD_FAILURE_NOT_CENSORING",
)
REASON_COMPARABLE = "FULL_EXPOSURE_OBSERVED_COMPARABLE"
REASON_EXPOSURE_CENSORED = "EARLY_TERMINATION_EXPOSURE_CENSORED"
REASON_METHOD_FAILURE_OUTCOME = "REQUIRED_PRIMARY_OUTCOME_NOT_OBSERVED_METHOD_FAILURE"
REASON_METHOD_FAILURE_NO_EXPOSURE = "NO_EXPOSURE_TERMINAL_FAILURE_METHOD_FAILURE"
PAIR_REASON_CENSORED = "CENSORED_UNEQUAL_EXPOSURE_NON_COMPARABLE"
PAIR_REASON_METHOD_FAILURE = "METHOD_FAILURE_NOT_CENSORING_NON_COMPARABLE"
BLOCKED_AGGREGATE_REASON = (
    "BLOCKED_EXPOSURE_CENSORED_PAIRS_RETAINED_NO_COMPLETE_CASE_DELETION"
)
FORMAL_SAMPLE_SIZE_DECISION = (
    "BLOCKED_INDEPENDENT_TRAINING_SEED_VARIANCE_NOT_ESTIMATED"
)
INFORMATIVE_CENSORING = "SUSPECTED_DEPENDENT_ON_ARM_BEHAVIOUR"
SENSITIVITY_INTERPRETATION_LIMIT = (
    "Truncation matching equalizes the measurement denominator only. It does "
    "not remove informative censoring, because the truncation point is produced "
    "by the arm's own early termination, and it does not recover the "
    "full-horizon estimand."
)
SENSITIVITY_PROHIBITED_USES = (
    "candidate_selection",
    "confidence_interval",
    "p_value",
    "hypothesis_test",
    "restoring_comparability",
    "sample_size_decision",
)
BOUND_PROHIBITED_USES = (
    "confidence_interval",
    "p_value",
    "hypothesis_test",
    "candidate_selection",
    "sample_size_decision",
)

AUDIT_STATUS_CLEAN = "AUDIT_COMPLETE_NO_CENSORING_BLOCKER"
AUDIT_STATUS_BLOCKED = "AUDIT_COMPLETE_RETAINED_CENSORING_BLOCKER"
VERDICT_COMPARABLE = "PAIRED_CONTRAST_COMPARABLE"
VERDICT_NON_COMPARABLE = "PAIRED_CONTRAST_NON_COMPARABLE_EXPOSURE_CENSORED"

ACCEPTANCE_IDS = tuple(f"AX-{index:02d}" for index in range(1, 13))
EXPECTED_ACCEPTANCE = (
    "AX-01_READ_ONLY_SOURCE_BUNDLE_PRE_POST_IDENTITY",
    "AX-02_FROZEN_TASK_HORIZON_AND_RATE_INTEGRALITY",
    "AX-03_PER_EPISODE_EXPOSURE_AND_TERMINATION_RECONSTRUCTION",
    "AX-04_RECORDED_COMMAND_PHASE_MATCHES_REPRODUCED_RECORDER_CONVENTION",
    "AX-05_EXPOSURE_CENSORING_AND_METHOD_FAILURE_CLASSIFIED_SEPARATELY",
    "AX-06_ASSUMPTION_FREE_FULL_HORIZON_AND_PAIRED_IDENTIFICATION_BOUNDS",
    "AX-07_PAIRED_COMPARABILITY_WITH_RETAINED_ARITHMETIC_DIFFERENCE_AND_BLOCKED_AGGREGATE",
    "AX-08_EXPOSURE_MATCHED_DESCRIPTIVE_SENSITIVITY_WITH_INFORMATIVE_CENSORING_BLOCKER",
    "AX-09_ORIGINAL_PILOT_RECEIPT_AND_NULL_SELECTION_PRESERVED",
    "AX-10_SAFE_ARTIFACT_PATH_BYTES_AND_SHA256_INVENTORY",
    "AX-11_STDLIB_ONLY_RAW_TO_AUDIT_SUMMARY_EXACT_REPLAY",
    "AX-12_SIM_ONLY_CLAIM_BOUNDARY_AND_PAPER_DATA_FALSE",
)
ACCEPTANCE_DETAIL = (
    "source bundle bytes and SHA-256 identical before and after the audit",
    "frozen task horizon and rate quotients are exact integers",
    "per-episode exposure, termination step, sim time and phase reconstructed",
    "every recorded command phase equals the frozen schedule phase",
    "exposure censoring and retained method failure classified separately",
    "assumption-free full-horizon and paired identification bounds emitted",
    "paired comparability retained with blocked aggregate and raw difference",
    "exposure-matched sensitivity emitted as descriptive with censoring blocker",
    "original pilot receipt hash and null selection preserved unchanged",
    "safe audit inventory has bytes and SHA-256 readback",
    "python -I -S replay reconstructed the audit summary exactly",
    "SIM_ONLY claim boundary and paper_data_ready=false retained",
)

REQUIRED_SOURCE_ROLES = ("protocol", "raw_episodes", "pilot_summary")
MAX_JSON_BYTES = 256 * 1024 * 1024
MAX_ARTIFACT_BYTES = 1024 * 1024 * 1024
MAX_JSON_DEPTH = 96
MAX_JSON_NODES = 5_000_000
MAX_BUNDLE_ENTRIES = 1000
MAX_REPLAY_STDOUT_BYTES = 4 * 1024 * 1024
REPLAY_TIMEOUT_SECONDS = 900
REPLAY_SCRIPT = Path(__file__).with_name("v7_exposure_audit_replay.py")
DEFAULT_PROTOCOL = Path(__file__).with_name("v7_exposure_audit_protocol.json")
SHA256_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
GIT_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
PERCENT_DECIMALS = 6
FRACTION_DECIMALS = 9
SECOND_DECIMALS = 9


class V7ExposureAuditError(RuntimeError):
    """A structural, identity, path, exposure, or replay gate failed closed."""


def _reject_constant(value: str) -> None:
    raise V7ExposureAuditError(f"JSON non-finite constant is forbidden: {value}")


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise V7ExposureAuditError(f"duplicate JSON key is forbidden: {key}")
        result[key] = value
    return result


def _bounded_int(value: str) -> int:
    if len(value.lstrip("-")) > 1000:
        raise V7ExposureAuditError("pathological JSON integer is forbidden")
    return int(value)


def _check_tree(root: Any) -> None:
    stack = [(root, 1)]
    nodes = 0
    while stack:
        value, depth = stack.pop()
        nodes += 1
        if nodes > MAX_JSON_NODES:
            raise V7ExposureAuditError("JSON node limit exceeded")
        if depth > MAX_JSON_DEPTH:
            raise V7ExposureAuditError("JSON nesting limit exceeded")
        if isinstance(value, dict):
            stack.extend((item, depth + 1) for item in value.values())
        elif isinstance(value, list):
            stack.extend((item, depth + 1) for item in value)
        elif type(value) is float and not math.isfinite(value):
            # ``json.loads('1e400')`` yields infinity without parse_constant.
            raise V7ExposureAuditError("JSON non-finite number is forbidden")


def _load_json_bytes(payload: bytes, label: str) -> dict[str, Any]:
    if len(payload) > MAX_JSON_BYTES:
        raise V7ExposureAuditError(f"JSON artifact exceeds byte limit: {label}")
    try:
        value = json.loads(
            payload.decode("utf-8"),
            parse_constant=_reject_constant,
            parse_int=_bounded_int,
            object_pairs_hook=_reject_duplicate_keys,
        )
        _check_tree(value)
    except V7ExposureAuditError:
        raise
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise V7ExposureAuditError(f"invalid JSON artifact: {label}") from exc
    if not isinstance(value, dict):
        raise V7ExposureAuditError(f"JSON root must be an object: {label}")
    return value


def load_json_object_strict(path: Path) -> dict[str, Any]:
    """Load bounded UTF-8 JSON with duplicate keys and NaN/Infinity rejected."""
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise V7ExposureAuditError(f"cannot read JSON artifact: {path.name}") from exc
    return _load_json_bytes(payload, path.name)


def _load_json_text_strict(payload: str, label: str) -> dict[str, Any]:
    return _load_json_bytes(payload.encode("utf-8"), label)


def _sha256_bytes(payload: bytes) -> str:
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _require_object(value: Any, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise V7ExposureAuditError(f"{context} must be an object")
    return value


def _require_list(value: Any, context: str) -> list[Any]:
    if not isinstance(value, list):
        raise V7ExposureAuditError(f"{context} must be an array")
    return value


def _require_string(
    value: Any,
    context: str,
    *,
    pattern: re.Pattern[str] | None = None,
    choices: set[str] | None = None,
) -> str:
    if not isinstance(value, str) or not value:
        raise V7ExposureAuditError(f"{context} must be a non-empty string")
    if pattern is not None and pattern.fullmatch(value) is None:
        raise V7ExposureAuditError(f"{context} has invalid format")
    if choices is not None and value not in choices:
        raise V7ExposureAuditError(f"{context} has unsupported value: {value}")
    return value


def _require_int(value: Any, context: str, *, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise V7ExposureAuditError(
            f"{context} must be an integer in [{minimum}, {maximum}]"
        )
    return value


def _require_number(value: Any, context: str) -> float:
    if type(value) not in {int, float}:
        raise V7ExposureAuditError(f"{context} must be a number")
    try:
        number = float(value)
        finite = math.isfinite(number)
    except (OverflowError, ValueError):
        finite = False
        number = 0.0
    if not finite:
        raise V7ExposureAuditError(f"{context} must be finite")
    return number


def _exact_positive_integer(value: float, context: str) -> int:
    """Require a float to be an exact positive integer without rounding."""
    if not float(value).is_integer():
        raise V7ExposureAuditError(f"{context} must be an exact integer: {value!r}")
    number = int(value)
    if number <= 0:
        raise V7ExposureAuditError(f"{context} must be positive: {value!r}")
    return number


def _safe_relative_path(value: Any, context: str) -> str:
    path = _require_string(value, context)
    normalized = path.replace("\\", "/")
    pure = PurePosixPath(normalized)
    if (
        pure.is_absolute()
        or normalized.startswith("//")
        or any(":" in part for part in pure.parts)
        or ".." in pure.parts
        or normalized != pure.as_posix()
    ):
        raise V7ExposureAuditError(f"{context} must be a canonical safe relative path")
    return normalized


def _is_link_or_junction(path: Path) -> bool:
    if path.is_symlink():
        return True
    is_junction = getattr(path, "is_junction", None)
    return bool(is_junction is not None and is_junction())


def _safe_source_file(root: Path, relative_path: str, context: str) -> Path:
    normalized = _safe_relative_path(relative_path, context)
    candidate = root.joinpath(*PurePosixPath(normalized).parts)
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise V7ExposureAuditError(f"missing source artifact: {normalized}") from exc
    if not resolved.is_relative_to(root.resolve()):
        raise V7ExposureAuditError(f"source artifact escapes bounded root: {normalized}")
    current = root.resolve()
    for part in PurePosixPath(normalized).parts:
        current = current / part
        if _is_link_or_junction(current):
            raise V7ExposureAuditError(
                f"source artifact uses link/reparse point: {normalized}"
            )
    if not resolved.is_file():
        raise V7ExposureAuditError(f"source artifact is not a file: {normalized}")
    return resolved


def _write_bytes(path: Path, payload: bytes) -> None:
    if path.exists():
        raise V7ExposureAuditError(f"refusing to overwrite artifact: {path.name}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".partial")
    if temporary.exists():
        raise V7ExposureAuditError(f"refusing to reuse partial artifact: {temporary.name}")
    temporary.write_bytes(payload)
    os.replace(temporary, path)
    if path.stat().st_size != len(payload) or sha256_file(path) != _sha256_bytes(payload):
        raise V7ExposureAuditError(f"artifact readback mismatch: {path.name}")


def _json_bytes(payload: Any) -> bytes:
    try:
        return (
            json.dumps(
                payload,
                ensure_ascii=False,
                allow_nan=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise V7ExposureAuditError("derived payload is not strict finite JSON") from exc


def _write_json(path: Path, payload: Any) -> None:
    _write_bytes(path, _json_bytes(payload))


def _inventory_record(root: Path, path: Path, role: str) -> dict[str, Any]:
    resolved_root = root.resolve()
    resolved = path.resolve()
    if not resolved.is_relative_to(resolved_root) or not resolved.is_file():
        raise V7ExposureAuditError(f"inventory artifact escapes audit root: {path.name}")
    return {
        "role": role,
        "path": resolved.relative_to(resolved_root).as_posix(),
        "bytes": resolved.stat().st_size,
        "sha256": sha256_file(resolved),
    }


def _require_false(value: Any, context: str) -> bool:
    if value is not False:
        raise V7ExposureAuditError(f"{context} must be false")
    return False


def _round_percent(value: float) -> float:
    return round(value, PERCENT_DECIMALS)


def _state_counts(values: list[str], states: tuple[str, ...]) -> dict[str, int]:
    counts = Counter(values)
    unexpected = sorted(set(counts) - set(states))
    if unexpected:
        raise V7ExposureAuditError(f"unexpected retained state: {unexpected[0]}")
    return {state: counts[state] for state in states}


def load_audit_protocol(path: Path) -> dict[str, Any]:
    """Load the frozen audit protocol and require its exact artifact identity."""
    digest = sha256_file(path)
    if digest != AUDIT_PROTOCOL_SHA256:
        raise V7ExposureAuditError(
            f"frozen audit protocol SHA-256 mismatch: {digest}"
        )
    protocol = load_json_object_strict(path)
    if protocol.get("schema_version") != AUDIT_PROTOCOL_SCHEMA:
        raise V7ExposureAuditError("audit protocol schema mismatch")
    if protocol.get("protocol_id") != AUDIT_PROTOCOL_ID:
        raise V7ExposureAuditError("audit protocol id mismatch")
    if protocol.get("protocol_status") != "FROZEN_INTERNAL_DEVELOPMENT":
        raise V7ExposureAuditError("audit protocol is not frozen")
    if protocol.get("run_class") != "DEVELOPMENT":
        raise V7ExposureAuditError("audit protocol run class must be DEVELOPMENT")
    if protocol.get("audit_class") != "READ_ONLY_VALIDITY_AUDIT":
        raise V7ExposureAuditError("audit protocol class must be read-only")
    if protocol.get("evidence_scope") != "SIM_ONLY_MUJOCO":
        raise V7ExposureAuditError("audit protocol evidence scope mismatch")
    if protocol.get("validation_status") != "NOT_PHYSICALLY_VALIDATED":
        raise V7ExposureAuditError("audit protocol validation status mismatch")
    _require_false(protocol.get("paper_data_ready"), "protocol.paper_data_ready")
    if protocol.get("claim_boundary") != CLAIM_BOUNDARY:
        raise V7ExposureAuditError("audit protocol claim boundary mismatch")
    audited = _require_object(protocol.get("audited_protocol"), "protocol.audited_protocol")
    if audited.get("protocol_id") != PILOT_PROTOCOL_ID:
        raise V7ExposureAuditError("audited protocol id mismatch")
    if audited.get("frozen_pilot_receipt_sha256") != FROZEN_PILOT_RECEIPT_SHA256:
        raise V7ExposureAuditError("frozen pilot receipt SHA-256 mismatch")
    _require_string(
        audited.get("frozen_pilot_source_git_sha"),
        "protocol.audited_protocol.frozen_pilot_source_git_sha",
        pattern=GIT_SHA_PATTERN,
    )
    arms = _require_object(protocol.get("arms"), "protocol.arms")
    if arms.get("reference_arm_id") != REFERENCE_ARM_ID:
        raise V7ExposureAuditError("audit protocol reference arm mismatch")
    if arms.get("candidate_arm_ids") != list(CANDIDATE_ARM_IDS):
        raise V7ExposureAuditError("audit protocol candidate arms mismatch")
    if arms.get("all_arm_ids") != list(ARM_IDS):
        raise V7ExposureAuditError("audit protocol arm inventory mismatch")
    if arms.get("expected_evaluation_seeds") != list(EXPECTED_SEEDS):
        raise V7ExposureAuditError("audit protocol evaluation seeds mismatch")
    if arms.get("episodes_per_arm") != len(EXPECTED_SEEDS):
        raise V7ExposureAuditError("audit protocol episodes per arm mismatch")
    if arms.get("retired_seed_range") != [19000, 19029]:
        raise V7ExposureAuditError("audit protocol retired seed range mismatch")
    if arms.get("sealed_formal_seed_range") != [20000, 20029]:
        raise V7ExposureAuditError("audit protocol sealed seed range mismatch")
    outcome = _require_object(protocol.get("primary_outcome"), "protocol.primary_outcome")
    if outcome.get("measurement_id") != PRIMARY_MEASUREMENT_ID:
        raise V7ExposureAuditError("audit protocol primary outcome mismatch")
    if protocol.get("acceptance_criteria") != list(EXPECTED_ACCEPTANCE):
        raise V7ExposureAuditError("audit protocol acceptance criteria mismatch")
    semantics = _require_object(protocol.get("failure_semantics"), "protocol.failure_semantics")
    if semantics.get("threshold_change") != "FORBIDDEN":
        raise V7ExposureAuditError("audit protocol must forbid threshold change")
    exit_codes = _require_object(
        semantics.get("cli_exit_codes"), "protocol.failure_semantics.cli_exit_codes"
    )
    expected_exit_codes = {
        "audit_complete_no_censoring_blocker": 0,
        "audit_complete_retained_censoring_blocker": 1,
        "structural_failure": 2,
    }
    if exit_codes != expected_exit_codes:
        raise V7ExposureAuditError("audit protocol exit codes mismatch")
    blockers = _require_object(protocol.get("retained_blockers"), "protocol.retained_blockers")
    for key in ("pilot_planning_ready", "method_level_power_ready", "statistics_ready", "paper_data_ready"):
        _require_false(blockers.get(key), f"protocol.retained_blockers.{key}")
    if blockers.get("selected_candidate_arm_id") is not None:
        raise V7ExposureAuditError("audit protocol must retain a null selection")
    if blockers.get("formal_sample_size_decision") != FORMAL_SAMPLE_SIZE_DECISION:
        raise V7ExposureAuditError("audit protocol sample-size blocker mismatch")
    _exposure_contract(protocol)
    _phase_schedule(protocol)
    return protocol


def _exposure_contract(protocol: dict[str, Any]) -> dict[str, Any]:
    """Derive the exposure horizon from the frozen task contract, integrality first."""
    horizon = _require_object(
        protocol.get("frozen_task_horizon"), "protocol.frozen_task_horizon"
    )
    task_id = _require_string(horizon.get("task_id"), "protocol.frozen_task_horizon.task_id")
    source = _safe_relative_path(
        horizon.get("motion_task_source"), "protocol.frozen_task_horizon.motion_task_source"
    )
    source_sha = _require_string(
        horizon.get("motion_task_source_sha256"),
        "protocol.frozen_task_horizon.motion_task_source_sha256",
        pattern=SHA256_PATTERN,
    )
    duration_s = _require_number(
        horizon.get("duration_s"), "protocol.frozen_task_horizon.duration_s"
    )
    physics_rate_hz = _require_number(
        horizon.get("physics_rate_hz"), "protocol.frozen_task_horizon.physics_rate_hz"
    )
    control_rate_hz = _require_number(
        horizon.get("control_rate_hz"), "protocol.frozen_task_horizon.control_rate_hz"
    )
    if duration_s <= 0.0 or physics_rate_hz <= 0.0 or control_rate_hz <= 0.0:
        raise V7ExposureAuditError("frozen task horizon rates must be positive")
    substeps = _exact_positive_integer(
        physics_rate_hz / control_rate_hz, "physics_substeps_per_control_step"
    )
    control_steps = _exact_positive_integer(
        duration_s * control_rate_hz, "full_exposure_control_steps"
    )
    physics_substeps = control_steps * substeps
    control_period_s = round(1.0 / control_rate_hz, SECOND_DECIMALS)
    declared = {
        "control_period_s": control_period_s,
        "physics_substeps_per_control_step": substeps,
        "full_exposure_control_steps": control_steps,
        "full_exposure_physics_substeps": physics_substeps,
    }
    for key, value in declared.items():
        if horizon.get(key) != value:
            raise V7ExposureAuditError(
                f"protocol.frozen_task_horizon.{key} disagrees with the derivation"
            )
    return {
        "task_id": task_id,
        "motion_task_source": source,
        "motion_task_source_sha256": source_sha,
        "duration_s": duration_s,
        "physics_rate_hz": physics_rate_hz,
        "control_rate_hz": control_rate_hz,
        "control_period_s": control_period_s,
        "physics_substeps_per_control_step": substeps,
        "full_exposure_control_steps": control_steps,
        "full_exposure_physics_substeps": physics_substeps,
    }


def _phase_schedule(protocol: dict[str, Any]) -> list[dict[str, Any]]:
    """Derive a contiguous, exact half-open control-step phase schedule."""
    contract = _exposure_contract(protocol)
    control_rate_hz = contract["control_rate_hz"]
    total_steps = contract["full_exposure_control_steps"]
    entries = _require_list(protocol.get("frozen_phase_schedule"), "protocol.frozen_phase_schedule")
    if not entries:
        raise V7ExposureAuditError("frozen phase schedule must not be empty")
    schedule: list[dict[str, Any]] = []
    seen: set[str] = set()
    cursor = 0
    for index, entry_value in enumerate(entries):
        context = f"protocol.frozen_phase_schedule[{index}]"
        entry = _require_object(entry_value, context)
        phase_id = _require_string(entry.get("phase_id"), context + ".phase_id")
        if phase_id in seen:
            raise V7ExposureAuditError(f"{context} duplicate phase identifier")
        seen.add(phase_id)
        start_s = _require_number(entry.get("start_s"), context + ".start_s")
        end_s = _require_number(entry.get("end_s"), context + ".end_s")
        if end_s <= start_s:
            raise V7ExposureAuditError(f"{context} phase window is not increasing")
        start_steps = start_s * control_rate_hz
        end_steps = end_s * control_rate_hz
        if not float(start_steps).is_integer() or not float(end_steps).is_integer():
            raise V7ExposureAuditError(f"{context} phase boundary is not an exact control step")
        first = int(start_steps)
        end_exclusive = int(end_steps)
        if first != cursor:
            raise V7ExposureAuditError(f"{context} phase schedule is not contiguous")
        if entry.get("first_control_step") != first:
            raise V7ExposureAuditError(f"{context}.first_control_step mismatch")
        if entry.get("last_control_step") != end_exclusive - 1:
            raise V7ExposureAuditError(f"{context}.last_control_step mismatch")
        if entry.get("control_steps") != end_exclusive - first:
            raise V7ExposureAuditError(f"{context}.control_steps mismatch")
        schedule.append({
            "phase_id": phase_id,
            "first_control_step": first,
            "last_control_step": end_exclusive - 1,
            "control_steps": end_exclusive - first,
        })
        cursor = end_exclusive
    if cursor != total_steps:
        raise V7ExposureAuditError(
            "frozen phase schedule does not cover the full exposure horizon"
        )
    return schedule


def _phase_of_control_step(schedule: list[dict[str, Any]], step: int) -> str:
    for entry in schedule:
        if entry["first_control_step"] <= step <= entry["last_control_step"]:
            return entry["phase_id"]
    raise V7ExposureAuditError(f"control step {step} is outside the frozen phase schedule")


def _recorder_phase_labels(
    protocol: dict[str, Any], contract: dict[str, Any]
) -> tuple[str, ...]:
    """Reproduce the recorder's end-of-step accumulated-time phase labels.

    ``backend/rl/humanoid_env.py`` advances ``task_elapsed_s`` by one control
    period *after* the substep loop and only then re-samples the command phase,
    so the label stored for control step ``k`` is the phase at the simulation
    time reached after ``k + 1`` additions.  The repeated addition is
    reproduced exactly; substituting an exact product would disagree at the
    phase boundaries.
    """
    windows = [
        (
            _require_string(entry.get("phase_id"), "protocol.frozen_phase_schedule[].phase_id"),
            _require_number(entry.get("start_s"), "protocol.frozen_phase_schedule[].start_s"),
            _require_number(entry.get("end_s"), "protocol.frozen_phase_schedule[].end_s"),
        )
        for entry in _require_list(
            protocol.get("frozen_phase_schedule"), "protocol.frozen_phase_schedule"
        )
    ]
    if not windows:
        raise V7ExposureAuditError("frozen phase schedule must not be empty")
    period = contract["control_period_s"]
    labels: list[str] = []
    accumulated = 0.0
    for _ in range(contract["full_exposure_control_steps"]):
        accumulated += period
        labels.append(
            next(
                (
                    phase_id
                    for phase_id, start_s, end_s in windows
                    if start_s <= accumulated < end_s
                ),
                windows[-1][0],
            )
        )
    return tuple(labels)


def _recorder_phase_schedule(
    protocol: dict[str, Any], contract: dict[str, Any]
) -> list[dict[str, Any]]:
    """Derive and verify the reproduced recorder phase boundary table."""
    labels = _recorder_phase_labels(protocol, contract)
    convention = _require_object(protocol.get("phase_convention"), "protocol.phase_convention")
    if convention.get("recorder_convention") != "END_OF_CONTROL_STEP_ACCUMULATED_SIM_TIME":
        raise V7ExposureAuditError("audit protocol recorder convention mismatch")
    _require_string(
        convention.get("recorder_source_sha256"),
        "protocol.phase_convention.recorder_source_sha256",
        pattern=SHA256_PATTERN,
    )
    schedule: list[dict[str, Any]] = []
    for entry in _require_list(
        protocol.get("frozen_phase_schedule"), "protocol.frozen_phase_schedule"
    ):
        phase_id = entry["phase_id"]
        indices = [index for index, label in enumerate(labels) if label == phase_id]
        if not indices:
            raise V7ExposureAuditError(
                f"reproduced recorder convention never records phase {phase_id}"
            )
        first = min(indices)
        last = max(indices)
        if indices != list(range(first, last + 1)):
            raise V7ExposureAuditError(
                f"reproduced recorder phase {phase_id} is not contiguous"
            )
        schedule.append({
            "phase_id": phase_id,
            "first_control_step": first,
            "last_control_step": last,
            "control_steps": len(indices),
        })
    if sum(item["control_steps"] for item in schedule) != contract["full_exposure_control_steps"]:
        raise V7ExposureAuditError(
            "reproduced recorder convention does not cover the full exposure horizon"
        )
    declared = _require_list(
        convention.get("recorder_phase_boundaries"),
        "protocol.phase_convention.recorder_phase_boundaries",
    )
    if declared != schedule:
        raise V7ExposureAuditError(
            "protocol.phase_convention.recorder_phase_boundaries disagrees with the "
            "reproduced recorder convention"
        )
    return schedule


def _phase_convention_finding(
    protocol: dict[str, Any],
    contract_schedule: list[dict[str, Any]],
    recorder_schedule: list[dict[str, Any]],
) -> dict[str, Any]:
    """Retain the contract-versus-recorder phase offset as a validity finding."""
    convention = _require_object(protocol.get("phase_convention"), "protocol.phase_convention")
    recorder_by_id = {item["phase_id"]: item for item in recorder_schedule}
    phases: list[dict[str, Any]] = []
    disagreeing: list[str] = []
    for entry in contract_schedule:
        phase_id = entry["phase_id"]
        recorder = recorder_by_id[phase_id]
        agrees = (
            entry["first_control_step"] == recorder["first_control_step"]
            and entry["last_control_step"] == recorder["last_control_step"]
        )
        if not agrees:
            disagreeing.append(phase_id)
        phases.append({
            "phase_id": phase_id,
            "contract_first_control_step": entry["first_control_step"],
            "contract_last_control_step": entry["last_control_step"],
            "recorder_first_control_step": recorder["first_control_step"],
            "recorder_last_control_step": recorder["last_control_step"],
            "conventions_agree": agrees,
        })
    return {
        "contract_convention": convention.get("contract_convention"),
        "recorder_convention": convention.get("recorder_convention"),
        "recorder_source": convention.get("recorder_source"),
        "recorder_source_sha256": convention.get("recorder_source_sha256"),
        "conventions_agree": not disagreeing,
        "disagreeing_phase_ids": disagreeing,
        "finding": (
            "RECORDED_PHASE_LABEL_FOLLOWS_END_OF_STEP_ACCUMULATED_TIME_AND_IS_OFFSET_"
            "FROM_THE_CONTRACT_START_OF_STEP_SCHEDULE"
            if disagreeing
            else "CONTRACT_AND_RECORDER_PHASE_CONVENTIONS_AGREE"
        ),
        "phases": phases,
    }


def _validate_raw(raw: dict[str, Any]) -> None:
    if raw.get("schema_version") != PILOT_RAW_SCHEMA:
        raise V7ExposureAuditError("audited raw episodes schema mismatch")
    if raw.get("protocol_id") != PILOT_PROTOCOL_ID:
        raise V7ExposureAuditError("audited raw episodes protocol mismatch")
    _require_string(
        raw.get("protocol_sha256"), "raw.protocol_sha256", pattern=SHA256_PATTERN
    )
    pre = _require_string(
        raw.get("source_git_sha_pre"), "raw.source_git_sha_pre", pattern=GIT_SHA_PATTERN
    )
    post = _require_string(
        raw.get("source_git_sha_post"), "raw.source_git_sha_post", pattern=GIT_SHA_PATTERN
    )
    if pre != post:
        raise V7ExposureAuditError("audited raw episodes Git pre/post identity drift")
    _require_false(raw.get("source_dirty_pre"), "raw.source_dirty_pre")
    _require_false(raw.get("source_dirty_post"), "raw.source_dirty_post")
    if raw.get("run_class") != "DEVELOPMENT" or raw.get("data_partition") != "DEVELOPMENT":
        raise V7ExposureAuditError("audited raw episodes must remain DEVELOPMENT")
    if raw.get("evidence_scope") != "SIM_ONLY_MUJOCO":
        raise V7ExposureAuditError("audited raw episodes evidence scope mismatch")
    if raw.get("expected_arm_count") != len(ARM_IDS):
        raise V7ExposureAuditError("audited raw episodes arm count mismatch")
    if raw.get("expected_episodes_per_arm") != len(EXPECTED_SEEDS):
        raise V7ExposureAuditError("audited raw episodes episode count mismatch")
    _require_false(raw.get("paper_data_ready"), "raw.paper_data_ready")
    arms = _require_list(raw.get("arms"), "raw.arms")
    arm_ids = [
        _require_string(_require_object(item, f"raw.arms[{index}]").get("arm_id"), f"raw.arms[{index}].arm_id")
        for index, item in enumerate(arms)
    ]
    if arm_ids != list(ARM_IDS):
        raise V7ExposureAuditError("audited raw episodes arm inventory mismatch")


def _validate_pilot_summary(pilot_summary: dict[str, Any], raw: dict[str, Any]) -> None:
    if pilot_summary.get("schema_version") != PILOT_SUMMARY_SCHEMA:
        raise V7ExposureAuditError("audited pilot summary schema mismatch")
    if pilot_summary.get("protocol_id") != PILOT_PROTOCOL_ID:
        raise V7ExposureAuditError("audited pilot summary protocol mismatch")
    if pilot_summary.get("protocol_sha256") != raw.get("protocol_sha256"):
        raise V7ExposureAuditError("audited pilot summary protocol hash drift")
    for key in ("source_git_sha_pre", "source_git_sha_post"):
        if pilot_summary.get(key) != raw.get(key):
            raise V7ExposureAuditError(f"audited pilot summary {key} drift")
    if pilot_summary.get("selected_candidate_arm_id") is not None:
        raise V7ExposureAuditError(
            "audited pilot summary selected a candidate; the audit refuses to "
            "reinterpret a pilot whose frozen selection is not null"
        )
    _require_false(pilot_summary.get("paper_data_ready"), "pilot_summary.paper_data_ready")
    _require_string(pilot_summary.get("selection_status"), "pilot_summary.selection_status")
    summaries = _require_list(pilot_summary.get("arm_summaries"), "pilot_summary.arm_summaries")
    ids = [
        _require_string(
            _require_object(item, f"pilot_summary.arm_summaries[{index}]").get("arm_id"),
            f"pilot_summary.arm_summaries[{index}].arm_id",
        )
        for index, item in enumerate(summaries)
    ]
    if ids != list(ARM_IDS):
        raise V7ExposureAuditError("audited pilot summary arm inventory mismatch")
    contrasts = _require_list(
        pilot_summary.get("paired_contrasts"), "pilot_summary.paired_contrasts"
    )
    candidate_ids = [
        _require_string(
            _require_object(item, f"pilot_summary.paired_contrasts[{index}]").get("candidate_arm_id"),
            f"pilot_summary.paired_contrasts[{index}].candidate_arm_id",
        )
        for index, item in enumerate(contrasts)
    ]
    if candidate_ids != list(CANDIDATE_ARM_IDS):
        raise V7ExposureAuditError("audited pilot summary contrast inventory mismatch")


def _retained_measurement(value: Any, context: str) -> dict[str, Any]:
    """Retain a pilot measurement verbatim after typing its state and value."""
    item = _require_object(value, context)
    state = _require_string(
        item.get("state"), context + ".state", choices=set(RETAINED_OUTCOME_STATES)
    )
    raw_value = item.get("value")
    if state == "OBSERVED":
        number = _require_number(raw_value, context + ".value")
    else:
        if raw_value is not None:
            raise V7ExposureAuditError(f"{context}.value must be null when not observed")
        number = None
    return {"state": state, "value": number}


def _episode_exposure(
    episode: Any,
    contract: dict[str, Any],
    schedule: list[dict[str, Any]],
    recorder_schedule: list[dict[str, Any]],
    context: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Reconstruct exposure, termination and censoring for one retained episode."""
    row = _require_object(episode, context)
    seed = _require_int(
        row.get("evaluation_seed"), context + ".evaluation_seed", minimum=0, maximum=2**63 - 1
    )
    if seed in RETIRED_SEED_RANGE:
        raise V7ExposureAuditError(f"{context} observed retired seed {seed}")
    if seed in SEALED_SEED_RANGE:
        raise V7ExposureAuditError(f"{context} observed sealed FORMAL/HOLDOUT seed {seed}")
    terminal_state = _require_string(
        row.get("terminal_record_state"),
        context + ".terminal_record_state",
        choices=set(RETAINED_TERMINAL_STATES),
    )
    outcome_state = _require_string(
        row.get("outcome_state"), context + ".outcome_state", choices=set(RETAINED_OUTCOME_STATES)
    )
    measurements = _require_object(row.get("measurements"), context + ".measurements")
    if PRIMARY_MEASUREMENT_ID not in measurements:
        raise V7ExposureAuditError(f"{context}.measurements missing {PRIMARY_MEASUREMENT_ID}")
    primary = _retained_measurement(
        measurements[PRIMARY_MEASUREMENT_ID], f"{context}.measurements.{PRIMARY_MEASUREMENT_ID}"
    )
    substeps_per_step = contract["physics_substeps_per_control_step"]
    full_steps = contract["full_exposure_control_steps"]
    full_substeps = contract["full_exposure_physics_substeps"]
    trace = _require_list(row.get("control_step_trace"), context + ".control_step_trace")
    observed_steps = len(trace)
    if observed_steps > full_steps:
        raise V7ExposureAuditError(
            f"{context} OVER_EXPOSURE: {observed_steps} control steps exceed the "
            f"frozen horizon of {full_steps}"
        )
    if (terminal_state == "COMPLETED") != (observed_steps > 0):
        raise V7ExposureAuditError(
            f"{context} terminal record state and retained trace presence disagree"
        )
    prefix_over = [0]
    prefix_total = [0]
    recorded_phase_counts = {entry["phase_id"]: 0 for entry in recorder_schedule}
    for index, item_value in enumerate(trace):
        item_context = f"{context}.control_step_trace[{index}]"
        item = _require_object(item_value, item_context)
        if item.get("control_step") != index:
            raise V7ExposureAuditError(f"{item_context}.control_step is not contiguous")
        over = _require_int(
            item.get("saturation_substeps_over_threshold"),
            item_context + ".saturation_substeps_over_threshold",
            minimum=0,
            maximum=substeps_per_step,
        )
        total = _require_int(
            item.get("saturation_substeps_total"),
            item_context + ".saturation_substeps_total",
            minimum=substeps_per_step,
            maximum=substeps_per_step,
        )
        if over > total:
            raise V7ExposureAuditError(f"{item_context} saturation count exceeds total")
        recorded_phase = _require_string(
            item.get("command_phase"), item_context + ".command_phase"
        )
        expected_phase = _phase_of_control_step(recorder_schedule, index)
        if recorded_phase != expected_phase:
            raise V7ExposureAuditError(
                f"{item_context}.command_phase {recorded_phase!r} disagrees with the "
                f"reproduced recorder convention phase {expected_phase!r}"
            )
        recorded_phase_counts[recorded_phase] += 1
        prefix_over.append(prefix_over[-1] + over)
        prefix_total.append(prefix_total[-1] + total)
    over_total = prefix_over[-1]
    substep_total = prefix_total[-1]
    if substep_total != observed_steps * substeps_per_step:
        raise V7ExposureAuditError(
            f"{context} exposure denominator disagrees with the retained control steps"
        )
    trace_receipt = _require_object(row.get("trace_receipt"), context + ".trace_receipt")
    if trace_receipt.get("control_step_count") != observed_steps:
        raise V7ExposureAuditError(f"{context}.trace_receipt.control_step_count mismatch")
    if trace_receipt.get("saturation_substeps_total") != substep_total:
        raise V7ExposureAuditError(f"{context}.trace_receipt.saturation_substeps_total mismatch")
    if trace_receipt.get("saturation_substeps_over_threshold") != over_total:
        raise V7ExposureAuditError(
            f"{context}.trace_receipt.saturation_substeps_over_threshold mismatch"
        )
    if observed_steps:
        truncated_duty = _round_percent(100.0 * over_total / substep_total)
        if trace_receipt.get("recomputed_saturation_duty_pct") != truncated_duty:
            raise V7ExposureAuditError(
                f"{context}.trace_receipt.recomputed_saturation_duty_pct mismatch"
            )
        if primary["state"] == "OBSERVED" and abs(truncated_duty - primary["value"]) > 1.0e-12:
            raise V7ExposureAuditError(
                f"{context} retained saturation duty disagrees with the retained counts"
            )
    else:
        truncated_duty = None
        if trace_receipt.get("recomputed_saturation_duty_pct") is not None:
            raise V7ExposureAuditError(
                f"{context}.trace_receipt.recomputed_saturation_duty_pct must be null"
            )
    if observed_steps == 0:
        exposure_class = "NO_EXPOSURE"
    elif observed_steps == full_steps:
        exposure_class = "FULL_EXPOSURE"
    else:
        exposure_class = "EARLY_TERMINATED"
    if observed_steps:
        termination_control_step: int | None = observed_steps - 1
        termination_sim_time_s: float | None = round(
            observed_steps / contract["control_rate_hz"], SECOND_DECIMALS
        )
        termination_contract_phase_id: str | None = _phase_of_control_step(
            schedule, termination_control_step
        )
        termination_recorder_phase_id: str | None = _phase_of_control_step(
            recorder_schedule, termination_control_step
        )
        recorded_termination_phase: str | None = _require_string(
            _require_object(trace[-1], context + ".control_step_trace[-1]").get("command_phase"),
            context + ".control_step_trace[-1].command_phase",
        )
    else:
        termination_control_step = None
        termination_sim_time_s = None
        termination_contract_phase_id = None
        termination_recorder_phase_id = None
        recorded_termination_phase = None
    if recorded_termination_phase is not None and (
        recorded_termination_phase != termination_recorder_phase_id
    ):
        raise V7ExposureAuditError(
            f"{context} recorded termination phase disagrees with the "
            "reproduced recorder convention"
        )
    phase_coverage: list[dict[str, Any]] = []
    for entry in recorder_schedule:
        expected = entry["control_steps"]
        observed_in_phase = max(
            0, min(observed_steps, entry["last_control_step"] + 1) - entry["first_control_step"]
        )
        if observed_in_phase != recorded_phase_counts[entry["phase_id"]]:
            raise V7ExposureAuditError(
                f"{context} recorded phase coverage disagrees with the frozen schedule"
            )
        phase_coverage.append({
            "phase_id": entry["phase_id"],
            "expected_control_steps": expected,
            "observed_control_steps": observed_in_phase,
            "complete": observed_in_phase == expected,
        })
    if primary["state"] != "OBSERVED" or terminal_state != "COMPLETED" or exposure_class == "NO_EXPOSURE":
        comparability_state = "METHOD_FAILURE_NOT_CENSORING"
        comparability_reason = (
            REASON_METHOD_FAILURE_NO_EXPOSURE
            if exposure_class == "NO_EXPOSURE"
            else REASON_METHOD_FAILURE_OUTCOME
        )
    elif exposure_class == "EARLY_TERMINATED":
        comparability_state = "EXPOSURE_CENSORED"
        comparability_reason = REASON_EXPOSURE_CENSORED
    else:
        comparability_state = "COMPARABLE"
        comparability_reason = REASON_COMPARABLE
    if comparability_state == "METHOD_FAILURE_NOT_CENSORING":
        bound = {
            "state": "NULL",
            "lower_pct": None,
            "upper_pct": None,
            "width_pct": None,
            "reason": comparability_reason,
        }
    else:
        lower_pct = _round_percent(100.0 * over_total / full_substeps)
        upper_pct = _round_percent(
            100.0 * (over_total + full_substeps - substep_total) / full_substeps
        )
        if upper_pct < lower_pct:
            raise V7ExposureAuditError(f"{context} identification bound is inverted")
        if exposure_class == "FULL_EXPOSURE" and not (
            lower_pct == upper_pct == truncated_duty
        ):
            raise V7ExposureAuditError(
                f"{context} full-exposure identification bound must be degenerate"
            )
        bound = {
            "state": "OBSERVED",
            "lower_pct": lower_pct,
            "upper_pct": upper_pct,
            "width_pct": _round_percent(upper_pct - lower_pct),
            "reason": None,
        }
    record = {
        "evaluation_seed": seed,
        "terminal_record_state": terminal_state,
        "outcome_state": outcome_state,
        "retained_saturation_duty_pct": primary,
        "recomputed_truncated_duty_pct": truncated_duty,
        "observed_control_steps": observed_steps,
        "observed_physics_substeps": substep_total,
        "observed_over_threshold_substeps": over_total,
        "exposure_fraction": round(observed_steps / full_steps, FRACTION_DECIMALS),
        "exposure_class": exposure_class,
        "termination_control_step": termination_control_step,
        "termination_sim_time_s": termination_sim_time_s,
        "termination_contract_phase_id": termination_contract_phase_id,
        "termination_recorder_phase_id": termination_recorder_phase_id,
        "recorded_termination_command_phase": recorded_termination_phase,
        "phase_coverage": phase_coverage,
        "comparability_state": comparability_state,
        "comparability_reason": comparability_reason,
        "full_horizon_duty_bound_pct": bound,
    }
    internals = {
        "evaluation_seed": seed,
        "observed_control_steps": observed_steps,
        "prefix_over": prefix_over,
        "prefix_total": prefix_total,
    }
    return record, internals


def _integer_statistics(values: list[int]) -> dict[str, Any]:
    if len(values) != len(EXPECTED_SEEDS):
        raise V7ExposureAuditError("exposure statistics require the exact seed inventory")
    return {
        "state": "OBSERVED",
        "n_expected": len(EXPECTED_SEEDS),
        "n_observed": len(values),
        "mean": statistics.fmean(values),
        "sample_standard_deviation": statistics.stdev(values),
        "minimum": min(values),
        "maximum": max(values),
        "reason": None,
    }


def _arm_exposure(
    arm: Any,
    pilot_arm_summary: dict[str, Any],
    contract: dict[str, Any],
    schedule: list[dict[str, Any]],
    recorder_schedule: list[dict[str, Any]],
    context: str,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """Audit one arm's exposure and retain its frozen pilot statistics verbatim."""
    block = _require_object(arm, context)
    arm_id = _require_string(block.get("arm_id"), context + ".arm_id")
    if pilot_arm_summary.get("arm_id") != arm_id:
        raise V7ExposureAuditError(f"{context} pilot summary arm binding mismatch")
    rows = _require_list(block.get("episodes"), context + ".episodes")
    if len(rows) != len(EXPECTED_SEEDS):
        raise V7ExposureAuditError(
            f"{context} must retain exactly {len(EXPECTED_SEEDS)} terminal records"
        )
    records: list[dict[str, Any]] = []
    internals: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(rows):
        record, internal = _episode_exposure(
            row, contract, schedule, recorder_schedule, f"{context}.episodes[{index}]"
        )
        records.append(record)
        internals[str(record["evaluation_seed"])] = internal
    seeds = [item["evaluation_seed"] for item in records]
    if len(set(seeds)) != len(seeds):
        raise V7ExposureAuditError(f"{context} duplicate evaluation seed")
    if sorted(seeds) != list(EXPECTED_SEEDS):
        raise V7ExposureAuditError(f"{context} missing or unexpected evaluation seed")
    records.sort(key=lambda item: item["evaluation_seed"])
    bounded = [
        item["full_horizon_duty_bound_pct"]
        for item in records
        if item["full_horizon_duty_bound_pct"]["state"] == "OBSERVED"
    ]
    if len(bounded) == len(EXPECTED_SEEDS):
        bound_aggregate = {
            "state": "OBSERVED",
            "n_expected": len(EXPECTED_SEEDS),
            "n_observed": len(bounded),
            "mean_lower_pct": statistics.fmean(item["lower_pct"] for item in bounded),
            "mean_upper_pct": statistics.fmean(item["upper_pct"] for item in bounded),
            "reason": None,
        }
    else:
        bound_aggregate = {
            "state": "NULL",
            "n_expected": len(EXPECTED_SEEDS),
            "n_observed": len(bounded),
            "mean_lower_pct": None,
            "mean_upper_pct": None,
            "reason": BLOCKED_AGGREGATE_REASON,
        }
    termination_contract_phase_counts = {entry["phase_id"]: 0 for entry in schedule}
    termination_contract_phase_counts["NO_EXPOSURE"] = 0
    termination_recorder_phase_counts = {
        entry["phase_id"]: 0 for entry in recorder_schedule
    }
    termination_recorder_phase_counts["NO_EXPOSURE"] = 0
    for item in records:
        termination_contract_phase_counts[
            item["termination_contract_phase_id"] or "NO_EXPOSURE"
        ] += 1
        termination_recorder_phase_counts[
            item["termination_recorder_phase_id"] or "NO_EXPOSURE"
        ] += 1
    terminated_steps = [
        item["termination_control_step"]
        for item in records
        if item["termination_control_step"] is not None
    ]
    summary = {
        "arm_id": arm_id,
        "record_count": len(records),
        "training_terminal_state": _require_string(
            block.get("training_terminal_state"), context + ".training_terminal_state",
            choices=set(RETAINED_TERMINAL_STATES),
        ),
        "evaluation_terminal_state": _require_string(
            block.get("evaluation_terminal_state"), context + ".evaluation_terminal_state",
            choices=set(RETAINED_TERMINAL_STATES),
        ),
        "exposure_class_counts": _state_counts(
            [item["exposure_class"] for item in records], EXPOSURE_CLASSES
        ),
        "comparability_state_counts": _state_counts(
            [item["comparability_state"] for item in records], COMPARABILITY_STATES
        ),
        "termination_contract_phase_counts": termination_contract_phase_counts,
        "termination_recorder_phase_counts": termination_recorder_phase_counts,
        "observed_control_steps": _integer_statistics(
            [item["observed_control_steps"] for item in records]
        ),
        "earliest_termination_control_step": min(terminated_steps) if terminated_steps else None,
        "latest_termination_control_step": max(terminated_steps) if terminated_steps else None,
        "full_horizon_duty_bound_pct": bound_aggregate,
        "pilot_reported_saturation_duty_pct": _pilot_reported_statistics(
            pilot_arm_summary, context
        ),
        "episodes": records,
    }
    return summary, internals


def _pilot_reported_statistics(
    pilot_arm_summary: dict[str, Any], context: str
) -> dict[str, Any]:
    """Retain the frozen pilot conditional statistics without recomputing them."""
    reported = _require_object(
        pilot_arm_summary.get(PRIMARY_MEASUREMENT_ID),
        f"{context}.pilot_summary.{PRIMARY_MEASUREMENT_ID}",
    )
    state = _require_string(
        reported.get("state"),
        f"{context}.pilot_summary.{PRIMARY_MEASUREMENT_ID}.state",
        choices=set(RETAINED_OUTCOME_STATES),
    )
    mean = reported.get("mean")
    deviation = reported.get("sample_standard_deviation")
    if state == "OBSERVED":
        mean = _require_number(mean, f"{context}.pilot_summary.mean")
        deviation = _require_number(deviation, f"{context}.pilot_summary.sd")
    else:
        if mean is not None or deviation is not None:
            raise V7ExposureAuditError(f"{context} pilot statistics must be null when not observed")
    return {
        "state": state,
        "n_observed": _require_int(
            reported.get("n_observed"),
            f"{context}.pilot_summary.n_observed",
            minimum=0,
            maximum=len(EXPECTED_SEEDS),
        ),
        "mean": mean,
        "sample_standard_deviation": deviation,
        "retention": "RETAINED_VERBATIM_FROM_FROZEN_PILOT_SUMMARY_NOT_RECOMPUTED",
    }


def _pilot_reported_contrast(
    pilot_summary: dict[str, Any], candidate_arm_id: str
) -> dict[str, Any]:
    for index, item in enumerate(pilot_summary["paired_contrasts"]):
        block = _require_object(item, f"pilot_summary.paired_contrasts[{index}]")
        if block.get("candidate_arm_id") != candidate_arm_id:
            continue
        context = f"pilot_summary.paired_contrasts[{index}]"
        state = _require_string(
            block.get("state"), context + ".state", choices=set(RETAINED_OUTCOME_STATES)
        )
        mean = block.get("mean_difference")
        deviation = block.get("sample_standard_deviation")
        if state == "OBSERVED":
            mean = _require_number(mean, context + ".mean_difference")
            deviation = _require_number(deviation, context + ".sample_standard_deviation")
        elif mean is not None or deviation is not None:
            raise V7ExposureAuditError(f"{context} statistics must be null when not observed")
        return {
            "state": state,
            "n_observed": _require_int(
                block.get("n_observed"), context + ".n_observed", minimum=0, maximum=len(EXPECTED_SEEDS)
            ),
            "mean_difference": mean,
            "sample_standard_deviation": deviation,
            "retention": "RETAINED_VERBATIM_FROM_FROZEN_PILOT_SUMMARY_NOT_RECOMPUTED",
        }
    raise V7ExposureAuditError(f"pilot summary has no contrast for {candidate_arm_id}")


def _paired_comparability(
    reference: dict[str, Any],
    candidate: dict[str, Any],
    pilot_summary: dict[str, Any],
) -> dict[str, Any]:
    """Decide per-pair comparability and emit assumption-free paired bounds."""
    reference_rows = {item["evaluation_seed"]: item for item in reference["episodes"]}
    candidate_rows = {item["evaluation_seed"]: item for item in candidate["episodes"]}
    pairs: list[dict[str, Any]] = []
    comparable_differences: list[float] = []
    bound_lowers: list[float] = []
    bound_uppers: list[float] = []
    sign_identified_count = 0
    for seed in EXPECTED_SEEDS:
        reference_row = reference_rows[seed]
        candidate_row = candidate_rows[seed]
        reference_state = reference_row["comparability_state"]
        candidate_state = candidate_row["comparability_state"]
        comparable = reference_state == candidate_state == "COMPARABLE"
        if comparable:
            pair_state = "COMPARABLE"
            pair_reason = REASON_COMPARABLE
        elif "METHOD_FAILURE_NOT_CENSORING" in {reference_state, candidate_state}:
            pair_state = "METHOD_FAILURE_NOT_CENSORING"
            pair_reason = PAIR_REASON_METHOD_FAILURE
        else:
            pair_state = "EXPOSURE_CENSORED"
            pair_reason = PAIR_REASON_CENSORED
        reference_value = reference_row["retained_saturation_duty_pct"]
        candidate_value = candidate_row["retained_saturation_duty_pct"]
        if reference_value["state"] == candidate_value["state"] == "OBSERVED":
            arithmetic = {
                "state": "OBSERVED",
                "value": _round_percent(candidate_value["value"] - reference_value["value"]),
                "valid_contrast": comparable,
                "reason": None if comparable else pair_reason,
            }
        else:
            arithmetic = {
                "state": (
                    "NONFINITE"
                    if "NONFINITE" in {reference_value["state"], candidate_value["state"]}
                    else "NULL"
                ),
                "value": None,
                "valid_contrast": False,
                "reason": pair_reason,
            }
        if comparable and arithmetic["state"] == "OBSERVED":
            comparable_differences.append(arithmetic["value"])
        reference_bound = reference_row["full_horizon_duty_bound_pct"]
        candidate_bound = candidate_row["full_horizon_duty_bound_pct"]
        if reference_bound["state"] == candidate_bound["state"] == "OBSERVED":
            lower_pct = _round_percent(candidate_bound["lower_pct"] - reference_bound["upper_pct"])
            upper_pct = _round_percent(candidate_bound["upper_pct"] - reference_bound["lower_pct"])
            if upper_pct < lower_pct:
                raise V7ExposureAuditError(f"paired identification bound for seed {seed} is inverted")
            if lower_pct > 0.0:
                sign: str | None = "POSITIVE"
                identified = True
            elif upper_pct < 0.0:
                sign = "NEGATIVE"
                identified = True
            else:
                sign = None
                identified = False
            if identified:
                sign_identified_count += 1
            bound_lowers.append(lower_pct)
            bound_uppers.append(upper_pct)
            paired_bound = {
                "state": "OBSERVED",
                "lower_pct": lower_pct,
                "upper_pct": upper_pct,
                "sign_identified": identified,
                "sign": sign,
                "reason": None,
            }
        else:
            paired_bound = {
                "state": "NULL",
                "lower_pct": None,
                "upper_pct": None,
                "sign_identified": False,
                "sign": None,
                "reason": PAIR_REASON_METHOD_FAILURE,
            }
        reference_steps = reference_row["observed_control_steps"]
        candidate_steps = candidate_row["observed_control_steps"]
        pairs.append({
            "evaluation_seed": seed,
            "reference_comparability_state": reference_state,
            "candidate_comparability_state": candidate_state,
            "reference_exposure_class": reference_row["exposure_class"],
            "candidate_exposure_class": candidate_row["exposure_class"],
            "reference_observed_control_steps": reference_steps,
            "candidate_observed_control_steps": candidate_steps,
            "matched_exposure_control_steps": min(reference_steps, candidate_steps),
            "exposure_ratio_candidate_over_reference": (
                round(candidate_steps / reference_steps, FRACTION_DECIMALS)
                if reference_steps
                else None
            ),
            "pair_comparability_state": pair_state,
            "pair_comparability_reason": pair_reason,
            "retained_arithmetic_difference_pct": arithmetic,
            "paired_identification_bound_pct": paired_bound,
        })
    comparable_count = sum(
        1 for item in pairs if item["pair_comparability_state"] == "COMPARABLE"
    )
    if comparable_count == len(EXPECTED_SEEDS):
        audited_difference = {
            "state": "OBSERVED",
            "n_expected": len(EXPECTED_SEEDS),
            "n_observed": len(comparable_differences),
            "mean_difference": statistics.fmean(comparable_differences),
            "sample_standard_deviation": statistics.stdev(comparable_differences),
            "reason": None,
        }
    else:
        audited_difference = {
            "state": "NULL",
            "n_expected": len(EXPECTED_SEEDS),
            "n_observed": comparable_count,
            "mean_difference": None,
            "sample_standard_deviation": None,
            "reason": BLOCKED_AGGREGATE_REASON,
        }
    if len(bound_lowers) == len(EXPECTED_SEEDS):
        bound_aggregate = {
            "state": "OBSERVED",
            "n_expected": len(EXPECTED_SEEDS),
            "n_observed": len(bound_lowers),
            "mean_lower_pct": statistics.fmean(bound_lowers),
            "mean_upper_pct": statistics.fmean(bound_uppers),
            "sign_identified_pair_count": sign_identified_count,
            "reason": None,
        }
    else:
        bound_aggregate = {
            "state": "NULL",
            "n_expected": len(EXPECTED_SEEDS),
            "n_observed": len(bound_lowers),
            "mean_lower_pct": None,
            "mean_upper_pct": None,
            "sign_identified_pair_count": sign_identified_count,
            "reason": BLOCKED_AGGREGATE_REASON,
        }
    return {
        "reference_arm_id": reference["arm_id"],
        "candidate_arm_id": candidate["arm_id"],
        "contrast": "candidate_minus_reference_by_evaluation_seed",
        "comparable_pair_count": comparable_count,
        "exposure_censored_pair_count": sum(
            1 for item in pairs if item["pair_comparability_state"] == "EXPOSURE_CENSORED"
        ),
        "method_failure_pair_count": sum(
            1 for item in pairs if item["pair_comparability_state"] == "METHOD_FAILURE_NOT_CENSORING"
        ),
        "validity_verdict": (
            VERDICT_COMPARABLE if comparable_count == len(EXPECTED_SEEDS) else VERDICT_NON_COMPARABLE
        ),
        "audited_paired_difference_pct": audited_difference,
        "paired_identification_bound_pct": bound_aggregate,
        "pilot_reported_paired_difference_pct": _pilot_reported_contrast(
            pilot_summary, candidate["arm_id"]
        ),
        "bound_prohibited_uses": list(BOUND_PROHIBITED_USES),
        "pairs": pairs,
    }


def _matched_duty(internal: dict[str, Any], steps: int) -> float | None:
    if steps <= 0:
        return None
    total = internal["prefix_total"][steps]
    if total <= 0:
        raise V7ExposureAuditError("matched exposure denominator must be positive")
    return _round_percent(100.0 * internal["prefix_over"][steps] / total)


def _exposure_matched_sensitivity(
    reference: dict[str, Any],
    candidate: dict[str, Any],
    reference_internals: dict[str, dict[str, Any]],
    candidate_internals: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Recompute both arms over the shared realized exposure, descriptive only."""
    pairs: list[dict[str, Any]] = []
    differences: list[float] = []
    for seed in EXPECTED_SEEDS:
        key = str(seed)
        reference_internal = reference_internals[key]
        candidate_internal = candidate_internals[key]
        matched = min(
            reference_internal["observed_control_steps"],
            candidate_internal["observed_control_steps"],
        )
        reference_duty = _matched_duty(reference_internal, matched)
        candidate_duty = _matched_duty(candidate_internal, matched)
        if reference_duty is None or candidate_duty is None:
            pairs.append({
                "evaluation_seed": seed,
                "matched_exposure_control_steps": matched,
                "state": "NULL",
                "reference_matched_duty_pct": None,
                "candidate_matched_duty_pct": None,
                "matched_difference_pct": None,
                "reason": REASON_METHOD_FAILURE_NO_EXPOSURE,
            })
            continue
        difference = _round_percent(candidate_duty - reference_duty)
        differences.append(difference)
        pairs.append({
            "evaluation_seed": seed,
            "matched_exposure_control_steps": matched,
            "state": "OBSERVED",
            "reference_matched_duty_pct": reference_duty,
            "candidate_matched_duty_pct": candidate_duty,
            "matched_difference_pct": difference,
            "reason": None,
        })
    if len(differences) == len(EXPECTED_SEEDS):
        aggregate = {
            "state": "OBSERVED",
            "n_expected": len(EXPECTED_SEEDS),
            "n_observed": len(differences),
            "mean_difference": statistics.fmean(differences),
            "sample_standard_deviation": statistics.stdev(differences),
            "reason": None,
        }
    else:
        aggregate = {
            "state": "NULL",
            "n_expected": len(EXPECTED_SEEDS),
            "n_observed": len(differences),
            "mean_difference": None,
            "sample_standard_deviation": None,
            "reason": BLOCKED_AGGREGATE_REASON,
        }
    return {
        "reference_arm_id": reference["arm_id"],
        "candidate_arm_id": candidate["arm_id"],
        "status": "DESCRIPTIVE_ONLY",
        "matched_difference_pct": aggregate,
        "informative_censoring": INFORMATIVE_CENSORING,
        "interpretation_limit": SENSITIVITY_INTERPRETATION_LIMIT,
        "prohibited_uses": list(SENSITIVITY_PROHIBITED_USES),
        "pairs": pairs,
    }


def _censoring_blockers(
    arm_blocks: list[dict[str, Any]], paired_blocks: list[dict[str, Any]]
) -> list[str]:
    blockers: list[str] = []
    for arm in arm_blocks:
        arm_id = arm["arm_id"]
        for episode in arm["episodes"]:
            state = episode["comparability_state"]
            if state != "COMPARABLE":
                blockers.append(f"{arm_id}:SEED_{episode['evaluation_seed']}_{state}")
    for block in paired_blocks:
        candidate_id = block["candidate_arm_id"]
        if block["validity_verdict"] != VERDICT_COMPARABLE:
            blockers.append(
                f"{candidate_id}:PAIRED_CONTRAST_{block['validity_verdict']}"
            )
    return blockers


def build_audit_summary(
    protocol: dict[str, Any],
    raw: dict[str, Any],
    pilot_summary: dict[str, Any],
    *,
    source_bundle_class: str,
    pilot_receipt_sha256: str,
) -> dict[str, Any]:
    """Deterministically reconstruct the audit summary from validated inputs."""
    if source_bundle_class not in BUNDLE_CLASSES:
        raise V7ExposureAuditError(f"unsupported source bundle class: {source_bundle_class}")
    _require_string(pilot_receipt_sha256, "pilot_receipt_sha256", pattern=SHA256_PATTERN)
    if (pilot_receipt_sha256 == FROZEN_PILOT_RECEIPT_SHA256) != (
        source_bundle_class == DEVELOPMENT_BUNDLE_CLASS
    ):
        raise V7ExposureAuditError(
            "source bundle class binding disagrees with the pilot receipt SHA-256"
        )
    _validate_raw(raw)
    _validate_pilot_summary(pilot_summary, raw)
    contract = _exposure_contract(protocol)
    schedule = _phase_schedule(protocol)
    recorder_schedule = _recorder_phase_schedule(protocol, contract)
    phase_convention = _phase_convention_finding(protocol, schedule, recorder_schedule)
    pilot_arm_summaries = {
        _require_object(item, "pilot_summary.arm_summaries[]")["arm_id"]: item
        for item in pilot_summary["arm_summaries"]
    }
    arm_blocks: list[dict[str, Any]] = []
    internals: dict[str, dict[str, dict[str, Any]]] = {}
    for index, arm in enumerate(raw["arms"]):
        arm_id = ARM_IDS[index]
        block, arm_internals = _arm_exposure(
            arm,
            _require_object(pilot_arm_summaries[arm_id], f"pilot_summary.arm_summaries[{arm_id}]"),
            contract,
            schedule,
            recorder_schedule,
            f"raw.arms[{index}]",
        )
        arm_blocks.append(block)
        internals[arm_id] = arm_internals
    by_id = {item["arm_id"]: item for item in arm_blocks}
    paired_blocks = [
        _paired_comparability(by_id[REFERENCE_ARM_ID], by_id[candidate_id], pilot_summary)
        for candidate_id in CANDIDATE_ARM_IDS
    ]
    sensitivity_blocks = [
        _exposure_matched_sensitivity(
            by_id[REFERENCE_ARM_ID],
            by_id[candidate_id],
            internals[REFERENCE_ARM_ID],
            internals[candidate_id],
        )
        for candidate_id in CANDIDATE_ARM_IDS
    ]
    blockers = _censoring_blockers(arm_blocks, paired_blocks)
    audit_status = AUDIT_STATUS_BLOCKED if blockers else AUDIT_STATUS_CLEAN
    zero_duty_arms = sorted(
        arm["arm_id"]
        for arm in arm_blocks
        if arm["exposure_class_counts"]["FULL_EXPOSURE"] == 0
        and arm["comparability_state_counts"]["COMPARABLE"] == 0
    )
    return {
        "schema_version": SUMMARY_SCHEMA,
        "audit_protocol_id": AUDIT_PROTOCOL_ID,
        "audit_protocol_sha256": AUDIT_PROTOCOL_SHA256,
        "audited_protocol_id": PILOT_PROTOCOL_ID,
        "audited_protocol_sha256": raw["protocol_sha256"],
        "source_bundle_class": source_bundle_class,
        "source_pilot_receipt_sha256": pilot_receipt_sha256,
        "audit_applies_to_frozen_v7_pilot": source_bundle_class == DEVELOPMENT_BUNDLE_CLASS,
        "source_git_sha_pre": raw["source_git_sha_pre"],
        "source_git_sha_post": raw["source_git_sha_post"],
        "run_class": "DEVELOPMENT",
        "data_partition": "DEVELOPMENT",
        "evidence_scope": "SIM_ONLY_MUJOCO",
        "validation_status": "NOT_PHYSICALLY_VALIDATED",
        "exposure_contract": contract,
        "contract_phase_schedule": schedule,
        "recorder_phase_schedule": recorder_schedule,
        "phase_convention": phase_convention,
        "arm_exposure": arm_blocks,
        "paired_comparability": paired_blocks,
        "exposure_matched_sensitivity": sensitivity_blocks,
        "audit_findings": {
            "primary_outcome_measurement_id": PRIMARY_MEASUREMENT_ID,
            "target_estimand": "FULL_HORIZON_SATURATION_DUTY_PCT",
            "arms_without_any_comparable_episode": zero_duty_arms,
            "zero_duty_interpretation": (
                "NON_COMPARABLE_EXPOSURE_CENSORED"
                if zero_duty_arms
                else "NOT_APPLICABLE_ALL_ARMS_HAVE_COMPARABLE_EPISODES"
            ),
            "censored_estimator": "NOT_FROZEN_BOUNDS_ONLY",
            "method_failure_doctrine": (
                "METHOD_FAILURE_IS_RETAINED_AND_IS_NOT_TREATED_AS_CENSORING"
            ),
        },
        "censoring_blockers": blockers,
        "censoring_blocker_count": len(blockers),
        "audit_status": audit_status,
        "audit_complete": True,
        "preserved_pilot_selection": {
            "pilot_receipt_sha256": pilot_receipt_sha256,
            "selection_status": pilot_summary["selection_status"],
            "selected_candidate_arm_id": None,
            "pilot_planning_ready": pilot_summary.get("pilot_planning_ready"),
            "audit_modified_pilot_conclusions": False,
        },
        "pilot_planning_ready": False,
        "method_level_power_ready": False,
        "formal_sample_size_decision": FORMAL_SAMPLE_SIZE_DECISION,
        "statistics_ready": False,
        "paper_data_ready": False,
        "claim_boundary": CLAIM_BOUNDARY,
    }


def _source_digest_index(root: Path, receipt: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Verify the audited bundle inventory and return a role-keyed digest index."""
    artifacts = _require_list(receipt.get("artifacts"), "pilot_receipt.artifacts")
    index: dict[str, dict[str, Any]] = {}
    casefold_paths: set[str] = set()
    for position, record_value in enumerate(artifacts):
        context = f"pilot_receipt.artifacts[{position}]"
        record = _require_object(record_value, context)
        if set(record) != {"role", "path", "bytes", "sha256"}:
            raise V7ExposureAuditError(f"{context} fields mismatch")
        role = _require_string(record["role"], context + ".role")
        path_text = _safe_relative_path(record["path"], context + ".path")
        if role in index or path_text.casefold() in casefold_paths:
            raise V7ExposureAuditError(
                "duplicate or case-colliding audited inventory role or path"
            )
        casefold_paths.add(path_text.casefold())
        path = _safe_source_file(root, path_text, context + ".path")
        expected_bytes = _require_int(
            record["bytes"], context + ".bytes", minimum=1, maximum=MAX_ARTIFACT_BYTES
        )
        expected_sha = _require_string(
            record["sha256"], context + ".sha256", pattern=SHA256_PATTERN
        )
        actual_bytes = path.stat().st_size
        actual_sha = sha256_file(path)
        if actual_bytes != expected_bytes or actual_sha != expected_sha:
            raise V7ExposureAuditError(
                f"audited bundle artifact bytes/SHA-256 mismatch: {path_text}"
            )
        index[role] = {
            "role": role,
            "path": path,
            "relative_path": path_text,
            "bytes": actual_bytes,
            "sha256": actual_sha,
        }
    missing = [role for role in REQUIRED_SOURCE_ROLES if role not in index]
    if missing:
        raise V7ExposureAuditError(f"audited bundle is missing required roles: {missing}")
    discovered: set[str] = set()
    entry_count = 0
    for directory, directories, filenames in os.walk(root, followlinks=False):
        directory_path = Path(directory)
        for name in list(directories) + list(filenames):
            entry_count += 1
            if entry_count > MAX_BUNDLE_ENTRIES:
                raise V7ExposureAuditError("audited bundle entry count exceeds bound")
            if _is_link_or_junction(directory_path / name):
                raise V7ExposureAuditError("audited bundle contains link/reparse point")
        for filename in filenames:
            discovered.add((directory_path / filename).relative_to(root).as_posix())
    expected = {item["relative_path"] for item in index.values()} | {"pilot_receipt.json"}
    if discovered != expected:
        raise V7ExposureAuditError(
            "audited bundle contains missing or unindexed files: "
            f"{sorted(discovered ^ expected)}"
        )
    return index


def _readback_source(index: dict[str, dict[str, Any]], phase: str) -> None:
    """Re-hash every consumed source artifact and reject any drift."""
    for role, item in sorted(index.items()):
        path = item["path"]
        if not path.is_file():
            raise V7ExposureAuditError(
                f"{phase} audited artifact disappeared: {item['relative_path']}"
            )
        if path.stat().st_size != item["bytes"] or sha256_file(path) != item["sha256"]:
            raise V7ExposureAuditError(
                f"{phase} audited artifact drifted, read-only contract violated: "
                f"{item['relative_path']} ({role})"
            )


def _source_bundle_class(receipt_sha256: str, receipt: dict[str, Any]) -> str:
    """Bind the bundle class to the receipt hash in both directions."""
    declared = receipt.get("audit_source_bundle_class")
    if declared is None:
        declared = (
            DEVELOPMENT_BUNDLE_CLASS
            if receipt_sha256 == FROZEN_PILOT_RECEIPT_SHA256
            else SYNTHETIC_BUNDLE_CLASS
        )
    resolved = _require_string(
        declared, "pilot_receipt.audit_source_bundle_class", choices=set(BUNDLE_CLASSES)
    )
    if (receipt_sha256 == FROZEN_PILOT_RECEIPT_SHA256) != (
        resolved == DEVELOPMENT_BUNDLE_CLASS
    ):
        raise V7ExposureAuditError(
            "audited bundle class binding disagrees with the pilot receipt SHA-256; a "
            "bundle that is not the frozen v7 pilot must declare "
            f"{SYNTHETIC_BUNDLE_CLASS}"
        )
    return resolved


def read_source_bundle(bundle_root: Path) -> dict[str, Any]:
    """Open the audited bundle read-only and verify its whole inventory."""
    root = bundle_root.resolve()
    if not root.is_dir():
        raise V7ExposureAuditError(f"audited bundle root is not a directory: {bundle_root}")
    receipt_path = root / "pilot_receipt.json"
    if not receipt_path.is_file() or _is_link_or_junction(receipt_path):
        raise V7ExposureAuditError("audited bundle is missing a regular pilot_receipt.json")
    receipt_sha256 = sha256_file(receipt_path)
    receipt = load_json_object_strict(receipt_path)
    if receipt.get("schema_version") != PILOT_RECEIPT_SCHEMA:
        raise V7ExposureAuditError("audited bundle receipt schema mismatch")
    if receipt.get("protocol_id") != PILOT_PROTOCOL_ID:
        raise V7ExposureAuditError("audited bundle receipt protocol mismatch")
    if receipt.get("contract_valid") is not True:
        raise V7ExposureAuditError("audited bundle receipt is not contract valid")
    if receipt.get("selected_candidate_arm_id") is not None:
        raise V7ExposureAuditError("audited bundle receipt selected a candidate")
    _require_false(receipt.get("paper_data_ready"), "pilot_receipt.paper_data_ready")
    bundle_class = _source_bundle_class(receipt_sha256, receipt)
    index = _source_digest_index(root, receipt)
    raw = load_json_object_strict(index["raw_episodes"]["path"])
    pilot_summary = load_json_object_strict(index["pilot_summary"]["path"])
    return {
        "root": root,
        "receipt_path": receipt_path,
        "receipt": receipt,
        "receipt_sha256": receipt_sha256,
        "bundle_class": bundle_class,
        "index": index,
        "raw": raw,
        "pilot_summary": pilot_summary,
    }


def _prepare_output_root(output_root: Path, source_root: Path) -> Path:
    resolved = output_root.resolve()
    if resolved == Path(resolved.anchor) or (resolved / ".git").exists():
        raise V7ExposureAuditError("audit output root must be a bounded evidence directory")
    if resolved == source_root or resolved.is_relative_to(source_root):
        raise V7ExposureAuditError(
            "audit output root must not be inside or equal to the audited bundle root"
        )
    if source_root.is_relative_to(resolved):
        raise V7ExposureAuditError(
            "audited bundle root must not be inside the audit output root"
        )
    if resolved.exists():
        if not resolved.is_dir() or any(resolved.iterdir()):
            raise V7ExposureAuditError("audit output root must not exist or must be empty")
    else:
        resolved.mkdir(parents=True)
    return resolved


def _verify_motion_task_source(contract: dict[str, Any]) -> dict[str, Any]:
    """Require the frozen task source that defines the horizon to be unchanged."""
    path = Path(__file__).with_name(PurePosixPath(contract["motion_task_source"]).name)
    if not path.is_file():
        raise V7ExposureAuditError(
            f"frozen motion task source is missing: {contract['motion_task_source']}"
        )
    digest = sha256_file(path)
    if digest != contract["motion_task_source_sha256"]:
        raise V7ExposureAuditError(
            "frozen motion task source SHA-256 drifted; the exposure horizon is no "
            f"longer the audited one: {digest}"
        )
    return {
        "path": contract["motion_task_source"],
        "bytes": path.stat().st_size,
        "sha256": digest,
    }


def _verify_recorder_source(protocol: dict[str, Any]) -> dict[str, Any]:
    """Require the recorder whose phase convention the audit reproduces to be unchanged."""
    convention = _require_object(protocol.get("phase_convention"), "protocol.phase_convention")
    relative = _safe_relative_path(
        convention.get("recorder_source"), "protocol.phase_convention.recorder_source"
    )
    expected = _require_string(
        convention.get("recorder_source_sha256"),
        "protocol.phase_convention.recorder_source_sha256",
        pattern=SHA256_PATTERN,
    )
    path = Path(__file__).parent.joinpath(*PurePosixPath(relative).parts[1:])
    if not path.is_file():
        raise V7ExposureAuditError(f"frozen recorder source is missing: {relative}")
    digest = sha256_file(path)
    if digest != expected:
        raise V7ExposureAuditError(
            "frozen recorder source SHA-256 drifted; the reproduced phase convention "
            f"is no longer the audited one: {digest}"
        )
    return {"path": relative, "bytes": path.stat().st_size, "sha256": digest}


def _run_replay(
    protocol_path: Path,
    receipt_path: Path,
    raw_path: Path,
    pilot_summary_path: Path,
    audit_summary_path: Path,
    *,
    cwd: Path,
) -> dict[str, Any]:
    if not REPLAY_SCRIPT.is_file():
        raise V7ExposureAuditError("stdlib-only audit replay script is missing")
    command = [
        sys.executable,
        "-I",
        "-S",
        str(REPLAY_SCRIPT),
        str(protocol_path),
        str(receipt_path),
        str(raw_path),
        str(pilot_summary_path),
        str(audit_summary_path),
    ]
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
            timeout=REPLAY_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise V7ExposureAuditError("stdlib-only audit replay failed to run") from exc
    if len(completed.stdout.encode("utf-8")) > MAX_REPLAY_STDOUT_BYTES:
        raise V7ExposureAuditError("stdlib-only audit replay stdout exceeds bounded size")
    replay = _load_json_text_strict(completed.stdout, "stdlib-only audit replay stdout")
    if completed.returncode != 0 or completed.stderr != "":
        raise V7ExposureAuditError(
            "stdlib-only audit replay failed: "
            f"returncode={completed.returncode}, stderr={completed.stderr[:500]!r}, "
            f"status={replay.get('status')!r}, error={replay.get('error')!r}"
        )
    expected = {
        "schema_version": REPLAY_SCHEMA,
        "status": "PASS",
        "exact_identity": True,
        "paper_data_ready": False,
        "claim_boundary": CLAIM_BOUNDARY,
        "audit_protocol_sha256": sha256_file(protocol_path),
        "pilot_receipt_sha256": sha256_file(receipt_path),
        "raw_episodes_sha256": sha256_file(raw_path),
        "pilot_summary_sha256": sha256_file(pilot_summary_path),
        "audit_summary_sha256": sha256_file(audit_summary_path),
    }
    for key, value in expected.items():
        if replay.get(key) != value:
            raise V7ExposureAuditError(f"stdlib-only audit replay receipt {key} mismatch")
    checks = replay.get("checks")
    if (
        not isinstance(checks, dict)
        or not checks
        or not all(value is True for value in checks.values())
    ):
        raise V7ExposureAuditError("stdlib-only audit replay checks are incomplete")
    return replay


def audit_v7_exposure_censoring(
    protocol_path: Path,
    source_bundle_root: Path,
    output_root: Path,
) -> dict[str, Any]:
    """Audit one retained v7 pilot bundle read-only and emit an audit bundle."""
    protocol_path = protocol_path.resolve()
    if protocol_path.name != "v7_exposure_audit_protocol.json":
        raise V7ExposureAuditError("audit protocol filename is not the frozen contract")
    protocol = load_audit_protocol(protocol_path)
    contract = _exposure_contract(protocol)
    motion_task = _verify_motion_task_source(contract)
    recorder_source = _verify_recorder_source(protocol)
    source = read_source_bundle(source_bundle_root)
    index = source["index"]
    _readback_source(index, "pre-audit")
    output = _prepare_output_root(output_root, source["root"])
    inventory_paths: list[tuple[Path, str]] = []
    bundle_protocol_path = output / "v7_exposure_audit_protocol.json"
    _write_bytes(bundle_protocol_path, protocol_path.read_bytes())
    if sha256_file(bundle_protocol_path) != AUDIT_PROTOCOL_SHA256:
        raise V7ExposureAuditError("audit protocol copy SHA-256 mismatch")
    inventory_paths.append((bundle_protocol_path, "audit_protocol"))
    summary = build_audit_summary(
        protocol,
        source["raw"],
        source["pilot_summary"],
        source_bundle_class=source["bundle_class"],
        pilot_receipt_sha256=source["receipt_sha256"],
    )
    source_index = {
        "schema_version": SOURCE_INDEX_SCHEMA,
        "audit_protocol_id": AUDIT_PROTOCOL_ID,
        "audit_protocol_sha256": AUDIT_PROTOCOL_SHA256,
        "audited_protocol_id": PILOT_PROTOCOL_ID,
        "source_bundle_class": source["bundle_class"],
        "audit_applies_to_frozen_v7_pilot": summary["audit_applies_to_frozen_v7_pilot"],
        "source_bundle_directory_name": source["root"].name,
        "source_pilot_receipt_sha256": source["receipt_sha256"],
        "source_git_sha_pre": summary["source_git_sha_pre"],
        "source_git_sha_post": summary["source_git_sha_post"],
        "frozen_motion_task_source": motion_task,
        "frozen_recorder_source": recorder_source,
        "access_mode": "READ_ONLY",
        "source_artifacts": [
            {
                "role": item["role"],
                "path": item["relative_path"],
                "bytes": item["bytes"],
                "sha256": item["sha256"],
            }
            for item in sorted(index.values(), key=lambda entry: entry["relative_path"])
        ],
        "run_class": "DEVELOPMENT",
        "data_partition": "DEVELOPMENT",
        "paper_data_ready": False,
        "claim_boundary": CLAIM_BOUNDARY,
    }
    source_index_path = output / "source_index.json"
    _write_json(source_index_path, source_index)
    inventory_paths.append((source_index_path, "source_index"))
    summary_path = output / "audit_summary.json"
    _write_json(summary_path, summary)
    inventory_paths.append((summary_path, "audit_summary"))
    replay = _run_replay(
        bundle_protocol_path,
        source["receipt_path"],
        index["raw_episodes"]["path"],
        index["pilot_summary"]["path"],
        summary_path,
        cwd=output,
    )
    replay_path = output / "audit_replay_receipt.json"
    _write_json(replay_path, replay)
    inventory_paths.append((replay_path, "independent_replay_receipt"))
    _readback_source(index, "post-audit")
    if sha256_file(source["receipt_path"]) != source["receipt_sha256"]:
        raise V7ExposureAuditError(
            "audited pilot receipt drifted, read-only contract violated"
        )
    artifacts = [
        _inventory_record(output, path, role)
        for path, role in sorted(inventory_paths, key=lambda item: item[0].as_posix())
    ]
    criteria = [
        {"criterion_id": criterion_id, "passed": True, "detail": detail}
        for criterion_id, detail in zip(ACCEPTANCE_IDS, ACCEPTANCE_DETAIL, strict=True)
    ]
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "audit_protocol_id": AUDIT_PROTOCOL_ID,
        "audit_protocol_sha256": AUDIT_PROTOCOL_SHA256,
        "audited_protocol_id": PILOT_PROTOCOL_ID,
        "validation_status": "AUDIT_CONTRACT_VALID",
        "contract_valid": True,
        "audit_complete": True,
        "audit_status": summary["audit_status"],
        "censoring_blocker_count": summary["censoring_blocker_count"],
        "source_bundle_class": source["bundle_class"],
        "audit_applies_to_frozen_v7_pilot": summary["audit_applies_to_frozen_v7_pilot"],
        "source_pilot_receipt_sha256": source["receipt_sha256"],
        "source_bundle_read_only_verified": True,
        "source_artifact_count": len(index),
        "source_artifact_bytes": sum(item["bytes"] for item in index.values()),
        "frozen_motion_task_source": motion_task,
        "frozen_recorder_source": recorder_source,
        "source_git_sha_pre": summary["source_git_sha_pre"],
        "source_git_sha_post": summary["source_git_sha_post"],
        "preserved_pilot_selection": summary["preserved_pilot_selection"],
        "criteria": criteria,
        "artifacts": artifacts,
        "pilot_planning_ready": False,
        "method_level_power_ready": False,
        "formal_sample_size_decision": FORMAL_SAMPLE_SIZE_DECISION,
        "statistics_ready": False,
        "paper_data_ready": False,
        "evidence_scope": "SIM_ONLY_MUJOCO",
        "validation_boundary": "NOT_PHYSICALLY_VALIDATED",
        "claim_boundary": CLAIM_BOUNDARY,
    }
    receipt_path = output / "audit_receipt.json"
    _write_json(receipt_path, receipt)
    validate_v7_exposure_audit_bundle(receipt_path)
    return receipt


def validate_v7_exposure_audit_bundle(receipt_path: Path) -> dict[str, Any]:
    """Re-validate a written audit bundle without reading the audited bundle."""
    receipt_path = receipt_path.resolve()
    if receipt_path.name != "audit_receipt.json":
        raise V7ExposureAuditError("audit receipt filename mismatch")
    root = receipt_path.parent
    receipt = load_json_object_strict(receipt_path)
    if receipt.get("schema_version") != RECEIPT_SCHEMA:
        raise V7ExposureAuditError("audit receipt schema mismatch")
    if receipt.get("audit_protocol_id") != AUDIT_PROTOCOL_ID:
        raise V7ExposureAuditError("audit receipt protocol mismatch")
    if receipt.get("audit_protocol_sha256") != AUDIT_PROTOCOL_SHA256:
        raise V7ExposureAuditError("audit receipt protocol hash mismatch")
    if receipt.get("contract_valid") is not True or receipt.get("audit_complete") is not True:
        raise V7ExposureAuditError("audit receipt is not contract valid")
    if receipt.get("source_bundle_read_only_verified") is not True:
        raise V7ExposureAuditError("audit receipt did not verify read-only access")
    if receipt.get("claim_boundary") != CLAIM_BOUNDARY:
        raise V7ExposureAuditError("audit receipt claim boundary mismatch")
    for key in ("pilot_planning_ready", "method_level_power_ready", "statistics_ready", "paper_data_ready"):
        _require_false(receipt.get(key), f"audit_receipt.{key}")
    bundle_class = _require_string(
        receipt.get("source_bundle_class"),
        "audit_receipt.source_bundle_class",
        choices=set(BUNDLE_CLASSES),
    )
    receipt_sha = _require_string(
        receipt.get("source_pilot_receipt_sha256"),
        "audit_receipt.source_pilot_receipt_sha256",
        pattern=SHA256_PATTERN,
    )
    if (receipt_sha == FROZEN_PILOT_RECEIPT_SHA256) != (bundle_class == DEVELOPMENT_BUNDLE_CLASS):
        raise V7ExposureAuditError("audit receipt bundle class binding mismatch")
    if receipt.get("audit_applies_to_frozen_v7_pilot") is not (
        bundle_class == DEVELOPMENT_BUNDLE_CLASS
    ):
        raise V7ExposureAuditError("audit receipt applicability flag mismatch")
    criteria = _require_list(receipt.get("criteria"), "audit_receipt.criteria")
    if [item.get("criterion_id") for item in criteria] != list(ACCEPTANCE_IDS):
        raise V7ExposureAuditError("audit receipt criteria inventory mismatch")
    if not all(item.get("passed") is True for item in criteria):
        raise V7ExposureAuditError("audit receipt retains a failed acceptance criterion")
    artifacts = _require_list(receipt.get("artifacts"), "audit_receipt.artifacts")
    paths: dict[str, Path] = {}
    casefold_paths: set[str] = set()
    for position, record_value in enumerate(artifacts):
        context = f"audit_receipt.artifacts[{position}]"
        record = _require_object(record_value, context)
        if set(record) != {"role", "path", "bytes", "sha256"}:
            raise V7ExposureAuditError(f"{context} fields mismatch")
        role = _require_string(record["role"], context + ".role")
        path_text = _safe_relative_path(record["path"], context + ".path")
        if role in paths or path_text.casefold() in casefold_paths:
            raise V7ExposureAuditError("duplicate/case-colliding audit inventory role or path")
        casefold_paths.add(path_text.casefold())
        path = _safe_source_file(root, path_text, context + ".path")
        expected_bytes = _require_int(
            record["bytes"], context + ".bytes", minimum=1, maximum=MAX_ARTIFACT_BYTES
        )
        expected_sha = _require_string(
            record["sha256"], context + ".sha256", pattern=SHA256_PATTERN
        )
        if path.stat().st_size != expected_bytes or sha256_file(path) != expected_sha:
            raise V7ExposureAuditError(f"audit artifact bytes/SHA-256 mismatch: {path_text}")
        paths[role] = path
    required_roles = {
        "audit_protocol",
        "source_index",
        "audit_summary",
        "independent_replay_receipt",
    }
    if not required_roles.issubset(paths):
        raise V7ExposureAuditError(
            f"audit bundle is missing required roles: {sorted(required_roles - set(paths))}"
        )
    discovered: set[str] = set()
    entry_count = 0
    for directory, directories, filenames in os.walk(root, followlinks=False):
        directory_path = Path(directory)
        for name in list(directories) + list(filenames):
            entry_count += 1
            if entry_count > MAX_BUNDLE_ENTRIES:
                raise V7ExposureAuditError("audit bundle entry count exceeds bound")
            if _is_link_or_junction(directory_path / name):
                raise V7ExposureAuditError("audit bundle contains link/reparse point")
        for filename in filenames:
            discovered.add((directory_path / filename).relative_to(root).as_posix())
    expected_paths = {
        path.relative_to(root).as_posix() for path in paths.values()
    } | {"audit_receipt.json"}
    if discovered != expected_paths:
        raise V7ExposureAuditError(
            f"audit bundle contains missing or unindexed files: {sorted(discovered ^ expected_paths)}"
        )
    if sha256_file(paths["audit_protocol"]) != AUDIT_PROTOCOL_SHA256:
        raise V7ExposureAuditError("audit bundle protocol copy hash mismatch")
    summary = load_json_object_strict(paths["audit_summary"])
    if summary.get("schema_version") != SUMMARY_SCHEMA:
        raise V7ExposureAuditError("audit summary schema mismatch")
    if summary.get("audit_status") != receipt.get("audit_status"):
        raise V7ExposureAuditError("audit summary status disagrees with the receipt")
    if summary.get("censoring_blocker_count") != receipt.get("censoring_blocker_count"):
        raise V7ExposureAuditError("audit summary blocker count disagrees with the receipt")
    if summary.get("source_pilot_receipt_sha256") != receipt_sha:
        raise V7ExposureAuditError("audit summary receipt binding mismatch")
    if summary.get("source_bundle_class") != bundle_class:
        raise V7ExposureAuditError("audit summary bundle class mismatch")
    if summary.get("preserved_pilot_selection") != receipt.get("preserved_pilot_selection"):
        raise V7ExposureAuditError("audit summary preserved selection mismatch")
    replay = load_json_object_strict(paths["independent_replay_receipt"])
    if replay.get("schema_version") != REPLAY_SCHEMA or replay.get("status") != "PASS":
        raise V7ExposureAuditError("audit replay receipt is not a passing receipt")
    if replay.get("exact_identity") is not True:
        raise V7ExposureAuditError("audit replay receipt is not exact")
    if replay.get("audit_summary_sha256") != sha256_file(paths["audit_summary"]):
        raise V7ExposureAuditError("audit replay receipt summary hash mismatch")
    if replay.get("pilot_receipt_sha256") != receipt_sha:
        raise V7ExposureAuditError("audit replay receipt pilot binding mismatch")
    source_index = load_json_object_strict(paths["source_index"])
    if source_index.get("schema_version") != SOURCE_INDEX_SCHEMA:
        raise V7ExposureAuditError("audit source index schema mismatch")
    if source_index.get("access_mode") != "READ_ONLY":
        raise V7ExposureAuditError("audit source index access mode mismatch")
    if source_index.get("source_pilot_receipt_sha256") != receipt_sha:
        raise V7ExposureAuditError("audit source index receipt binding mismatch")
    if source_index.get("frozen_motion_task_source") != receipt.get("frozen_motion_task_source"):
        raise V7ExposureAuditError("audit source index motion task binding mismatch")
    if source_index.get("frozen_recorder_source") != receipt.get("frozen_recorder_source"):
        raise V7ExposureAuditError("audit source index recorder binding mismatch")
    return {
        "schema_version": VALIDATION_SCHEMA,
        "validation_status": "AUDIT_BUNDLE_VALID",
        "contract_valid": True,
        "audit_complete": True,
        "audit_status": summary["audit_status"],
        "censoring_blocker_count": summary["censoring_blocker_count"],
        "source_bundle_class": bundle_class,
        "audit_applies_to_frozen_v7_pilot": summary["audit_applies_to_frozen_v7_pilot"],
        "source_pilot_receipt_sha256": receipt_sha,
        "artifact_count": len(artifacts),
        "artifact_bytes": sum(item["bytes"] for item in artifacts),
        "receipt_sha256": sha256_file(receipt_path),
        "pilot_planning_ready": False,
        "method_level_power_ready": False,
        "statistics_ready": False,
        "paper_data_ready": False,
        "evidence_scope": "SIM_ONLY_MUJOCO",
        "claim_boundary": CLAIM_BOUNDARY,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Run or validate the read-only v7 early-termination / "
            "exposure-censoring validity audit"
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    audit_parser = subparsers.add_parser("audit")
    audit_parser.add_argument("source_bundle", type=Path)
    audit_parser.add_argument("output_root", type=Path)
    audit_parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("receipt", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "audit":
            payload = audit_v7_exposure_censoring(
                args.protocol, args.source_bundle, args.output_root
            )
        else:
            payload = validate_v7_exposure_audit_bundle(args.receipt)
        exit_code = 0 if payload["audit_status"] == AUDIT_STATUS_CLEAN else 1
    except Exception as exc:
        payload = {
            "schema_version": ERROR_SCHEMA,
            "validation_status": "STRUCTURAL_FAILURE",
            "contract_valid": False,
            "audit_complete": False,
            "pilot_planning_ready": False,
            "error": f"{type(exc).__name__}: {exc}"[:1000],
            "paper_data_ready": False,
            "evidence_scope": "SIM_ONLY_MUJOCO",
            "claim_boundary": CLAIM_BOUNDARY,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False))
        raise SystemExit(2) from exc
    print(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False))
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()

"""Standard-library-only replay for the v7 exposure-censoring validity audit.

The process imports neither the audit contract nor the pilot pipeline.  It
re-validates the frozen audit protocol, re-derives the exposure horizon and the
phase schedule from that protocol, reconstructs every exposure, termination,
censoring, identification-bound, paired-comparability and descriptive
sensitivity value from the canonical raw episode rows, and requires exact JSON
identity with the primary audit summary.

What that identity does and does not establish: it establishes that the written
summary is a faithful function of the retained raw rows under a separate
interpreter with no project imports and no site-packages, so a transport,
serialization or bundle-assembly defect cannot hide in it. It does not
establish that the shared derivation is scientifically correct -- the two
implementations deliberately encode the same frozen rules, so agreement is
evidence about faithfulness, not about the rules themselves.
"""

from __future__ import annotations

from collections import Counter
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
import statistics
import sys
from typing import Any


AUDIT_PROTOCOL_SCHEMA = "V7_EXPOSURE_CENSORING_AUDIT_PROTOCOL_V1"
AUDIT_PROTOCOL_ID = "AUDIT-V7-EXPOSURE-CENSORING-V1"
AUDIT_PROTOCOL_SHA256 = (
    "sha256:b15505b73f3745141c2dfa31cf57564b0863242949f5d1ad4d351dfb96dec6ce"
)
SUMMARY_SCHEMA = "V7_EXPOSURE_AUDIT_SUMMARY_V1"
REPLAY_SCHEMA = "V7_EXPOSURE_AUDIT_REPLAY_RECEIPT_V1"
REPLAY_ERROR_SCHEMA = "V7_EXPOSURE_AUDIT_REPLAY_ERROR_RECEIPT_V1"
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
BLOCKED_CENSORED_REASON = (
    "BLOCKED_EXPOSURE_CENSORED_PAIRS_RETAINED_NO_COMPLETE_CASE_DELETION"
)
BLOCKED_METHOD_FAILURE_REASON = (
    "BLOCKED_METHOD_FAILURE_RETAINED_NO_COMPLETE_CASE_DELETION"
)
BLOCKED_MIXED_REASON = (
    "BLOCKED_EXPOSURE_CENSORED_AND_METHOD_FAILURE_RETAINED_NO_COMPLETE_CASE_DELETION"
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
VERDICT_NON_COMPARABLE_CENSORED = "PAIRED_CONTRAST_NON_COMPARABLE_EXPOSURE_CENSORED"
VERDICT_NON_COMPARABLE_METHOD_FAILURE = "PAIRED_CONTRAST_NON_COMPARABLE_METHOD_FAILURE"
VERDICT_NON_COMPARABLE_MIXED = (
    "PAIRED_CONTRAST_NON_COMPARABLE_EXPOSURE_CENSORED_AND_METHOD_FAILURE"
)
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
EXPECTED_REPLAY_CHECKS = (
    "audit_findings_exact",
    "audit_summary_exact",
    "censoring_blockers_exact",
    "contract_phase_schedule_exact",
    "exact_three_arm_seed_inventory",
    "exposure_and_censoring_exact",
    "exposure_matched_sensitivity_exact",
    "frozen_audit_protocol_exact",
    "frozen_task_horizon_exact",
    "identification_bounds_exact",
    "original_pilot_selection_preserved",
    "paired_comparability_exact",
    "phase_convention_offset_exact",
    "recorder_phase_convention_exact",
)
AUDITED_PROTOCOL_SHA256 = (
    "sha256:719b70a2bdf8d23af5f4ec5dff51a6099e88d6de4e2221fa74f6f7464cdfcb96"
)
MAX_JSON_BYTES = 256 * 1024 * 1024
MAX_JSON_DEPTH = 96
MAX_JSON_NODES = 5_000_000
SHA256_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
GIT_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
PERCENT_DECIMALS = 6
FRACTION_DECIMALS = 9
SECOND_DECIMALS = 9


class V7ExposureAuditReplayError(RuntimeError):
    """The independent audit reconstruction failed closed."""


def _reject_constant(value: str) -> None:
    raise V7ExposureAuditReplayError(f"JSON non-finite constant is forbidden: {value}")


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise V7ExposureAuditReplayError(f"duplicate JSON key is forbidden: {key}")
        result[key] = value
    return result


def _bounded_int(value: str) -> int:
    if len(value.lstrip("-")) > 1000:
        raise V7ExposureAuditReplayError("pathological JSON integer is forbidden")
    return int(value)


def _check_tree(root: Any) -> None:
    stack = [(root, 1)]
    nodes = 0
    while stack:
        value, depth = stack.pop()
        nodes += 1
        if nodes > MAX_JSON_NODES:
            raise V7ExposureAuditReplayError("JSON node limit exceeded")
        if depth > MAX_JSON_DEPTH:
            raise V7ExposureAuditReplayError("JSON nesting limit exceeded")
        if isinstance(value, dict):
            stack.extend((item, depth + 1) for item in value.values())
        elif isinstance(value, list):
            stack.extend((item, depth + 1) for item in value)
        elif type(value) is float and not math.isfinite(value):
            raise V7ExposureAuditReplayError("JSON non-finite number is forbidden")


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise V7ExposureAuditReplayError(f"cannot read JSON artifact: {path.name}") from exc
    if len(payload) > MAX_JSON_BYTES:
        raise V7ExposureAuditReplayError(f"JSON artifact exceeds byte limit: {path.name}")
    try:
        value = json.loads(
            payload.decode("utf-8"),
            parse_constant=_reject_constant,
            parse_int=_bounded_int,
            object_pairs_hook=_reject_duplicate_keys,
        )
        _check_tree(value)
    except V7ExposureAuditReplayError:
        raise
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise V7ExposureAuditReplayError(f"invalid JSON artifact: {path.name}") from exc
    if not isinstance(value, dict):
        raise V7ExposureAuditReplayError(f"JSON root must be an object: {path.name}")
    return value


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _require_object(value: Any, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise V7ExposureAuditReplayError(f"{context} must be an object")
    return value


def _require_list(value: Any, context: str) -> list[Any]:
    if not isinstance(value, list):
        raise V7ExposureAuditReplayError(f"{context} must be an array")
    return value


def _require_string(
    value: Any,
    context: str,
    *,
    pattern: re.Pattern[str] | None = None,
    choices: set[str] | None = None,
) -> str:
    if not isinstance(value, str) or not value:
        raise V7ExposureAuditReplayError(f"{context} must be a non-empty string")
    if pattern is not None and pattern.fullmatch(value) is None:
        raise V7ExposureAuditReplayError(f"{context} has invalid format")
    if choices is not None and value not in choices:
        raise V7ExposureAuditReplayError(f"{context} has unsupported value: {value}")
    return value


def _require_int(value: Any, context: str, *, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise V7ExposureAuditReplayError(
            f"{context} must be an integer in [{minimum}, {maximum}]"
        )
    return value


def _require_number(value: Any, context: str) -> float:
    if type(value) not in {int, float}:
        raise V7ExposureAuditReplayError(f"{context} must be a number")
    try:
        number = float(value)
        finite = math.isfinite(number)
    except (OverflowError, ValueError):
        finite = False
        number = 0.0
    if not finite:
        raise V7ExposureAuditReplayError(f"{context} must be finite")
    return number


def _require_false(value: Any, context: str) -> bool:
    if value is not False:
        raise V7ExposureAuditReplayError(f"{context} must be false")
    return False


def _exact_positive_integer(value: float, context: str) -> int:
    if not float(value).is_integer():
        raise V7ExposureAuditReplayError(f"{context} must be an exact integer: {value!r}")
    number = int(value)
    if number <= 0:
        raise V7ExposureAuditReplayError(f"{context} must be positive: {value!r}")
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
        raise V7ExposureAuditReplayError(f"{context} must be a canonical safe relative path")
    return normalized


def _round_percent(value: float) -> float:
    return round(value, PERCENT_DECIMALS)


def _state_counts(values: list[str], states: tuple[str, ...]) -> dict[str, int]:
    counts = Counter(values)
    unexpected = sorted(set(counts) - set(states))
    if unexpected:
        raise V7ExposureAuditReplayError(f"unexpected retained state: {unexpected[0]}")
    return {state: counts[state] for state in states}


def _non_comparable_verdict(censored: int, method_failure: int) -> str:
    """Name the actual cause instead of always blaming exposure censoring."""
    if censored and method_failure:
        return VERDICT_NON_COMPARABLE_MIXED
    if method_failure:
        return VERDICT_NON_COMPARABLE_METHOD_FAILURE
    return VERDICT_NON_COMPARABLE_CENSORED


def _blocked_reason(censored: int, method_failure: int) -> str:
    """Name the actual cause of a blocked aggregate."""
    if censored and method_failure:
        return BLOCKED_MIXED_REASON
    if method_failure:
        return BLOCKED_METHOD_FAILURE_REASON
    return BLOCKED_CENSORED_REASON


def _validate_audit_protocol(protocol: dict[str, Any], protocol_sha256: str) -> None:
    if protocol_sha256 != AUDIT_PROTOCOL_SHA256:
        raise V7ExposureAuditReplayError("frozen audit protocol SHA-256 mismatch")
    if protocol.get("schema_version") != AUDIT_PROTOCOL_SCHEMA:
        raise V7ExposureAuditReplayError("audit protocol schema mismatch")
    if protocol.get("protocol_id") != AUDIT_PROTOCOL_ID:
        raise V7ExposureAuditReplayError("audit protocol id mismatch")
    if protocol.get("protocol_status") != "FROZEN_INTERNAL_DEVELOPMENT":
        raise V7ExposureAuditReplayError("audit protocol is not frozen")
    if protocol.get("audit_class") != "READ_ONLY_VALIDITY_AUDIT":
        raise V7ExposureAuditReplayError("audit protocol class mismatch")
    if protocol.get("claim_boundary") != CLAIM_BOUNDARY:
        raise V7ExposureAuditReplayError("audit protocol claim boundary mismatch")
    if protocol.get("acceptance_criteria") != list(EXPECTED_ACCEPTANCE):
        raise V7ExposureAuditReplayError("audit protocol acceptance criteria mismatch")
    _require_false(protocol.get("paper_data_ready"), "protocol.paper_data_ready")
    audited = _require_object(protocol.get("audited_protocol"), "protocol.audited_protocol")
    if audited.get("protocol_id") != PILOT_PROTOCOL_ID:
        raise V7ExposureAuditReplayError("audited protocol id mismatch")
    if audited.get("frozen_pilot_receipt_sha256") != FROZEN_PILOT_RECEIPT_SHA256:
        raise V7ExposureAuditReplayError("frozen pilot receipt SHA-256 mismatch")
    arms = _require_object(protocol.get("arms"), "protocol.arms")
    if arms.get("all_arm_ids") != list(ARM_IDS):
        raise V7ExposureAuditReplayError("audit protocol arm inventory mismatch")
    if arms.get("expected_evaluation_seeds") != list(EXPECTED_SEEDS):
        raise V7ExposureAuditReplayError("audit protocol evaluation seeds mismatch")
    outcome = _require_object(protocol.get("primary_outcome"), "protocol.primary_outcome")
    if outcome.get("measurement_id") != PRIMARY_MEASUREMENT_ID:
        raise V7ExposureAuditReplayError("audit protocol primary outcome mismatch")
    blockers = _require_object(protocol.get("retained_blockers"), "protocol.retained_blockers")
    if blockers.get("selected_candidate_arm_id") is not None:
        raise V7ExposureAuditReplayError("audit protocol must retain a null selection")


def _exposure_contract(protocol: dict[str, Any]) -> dict[str, Any]:
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
    duration_s = _require_number(horizon.get("duration_s"), "protocol.duration_s")
    physics_rate_hz = _require_number(horizon.get("physics_rate_hz"), "protocol.physics_rate_hz")
    control_rate_hz = _require_number(horizon.get("control_rate_hz"), "protocol.control_rate_hz")
    if duration_s <= 0.0 or physics_rate_hz <= 0.0 or control_rate_hz <= 0.0:
        raise V7ExposureAuditReplayError("frozen task horizon rates must be positive")
    substeps = _exact_positive_integer(
        physics_rate_hz / control_rate_hz, "physics_substeps_per_control_step"
    )
    control_steps = _exact_positive_integer(
        duration_s * control_rate_hz, "full_exposure_control_steps"
    )
    control_period_s = round(1.0 / control_rate_hz, SECOND_DECIMALS)
    derived = {
        "task_id": task_id,
        "motion_task_source": source,
        "motion_task_source_sha256": source_sha,
        "duration_s": duration_s,
        "physics_rate_hz": physics_rate_hz,
        "control_rate_hz": control_rate_hz,
        "control_period_s": control_period_s,
        "physics_substeps_per_control_step": substeps,
        "full_exposure_control_steps": control_steps,
        "full_exposure_physics_substeps": control_steps * substeps,
    }
    for key in (
        "control_period_s",
        "physics_substeps_per_control_step",
        "full_exposure_control_steps",
        "full_exposure_physics_substeps",
    ):
        if horizon.get(key) != derived[key]:
            raise V7ExposureAuditReplayError(
                f"protocol.frozen_task_horizon.{key} disagrees with the derivation"
            )
    return derived


def _phase_schedule(protocol: dict[str, Any]) -> list[dict[str, Any]]:
    contract = _exposure_contract(protocol)
    control_rate_hz = contract["control_rate_hz"]
    entries = _require_list(
        protocol.get("frozen_phase_schedule"), "protocol.frozen_phase_schedule"
    )
    if not entries:
        raise V7ExposureAuditReplayError("frozen phase schedule must not be empty")
    schedule: list[dict[str, Any]] = []
    seen: set[str] = set()
    cursor = 0
    for index, entry_value in enumerate(entries):
        context = f"protocol.frozen_phase_schedule[{index}]"
        entry = _require_object(entry_value, context)
        phase_id = _require_string(entry.get("phase_id"), context + ".phase_id")
        if phase_id in seen:
            raise V7ExposureAuditReplayError(f"{context} duplicate phase identifier")
        seen.add(phase_id)
        start_s = _require_number(entry.get("start_s"), context + ".start_s")
        end_s = _require_number(entry.get("end_s"), context + ".end_s")
        if end_s <= start_s:
            raise V7ExposureAuditReplayError(f"{context} phase window is not increasing")
        start_steps = start_s * control_rate_hz
        end_steps = end_s * control_rate_hz
        if not float(start_steps).is_integer() or not float(end_steps).is_integer():
            raise V7ExposureAuditReplayError(
                f"{context} phase boundary is not an exact control step"
            )
        first = int(start_steps)
        end_exclusive = int(end_steps)
        if first != cursor:
            raise V7ExposureAuditReplayError(f"{context} phase schedule is not contiguous")
        if (
            entry.get("first_control_step") != first
            or entry.get("last_control_step") != end_exclusive - 1
            or entry.get("control_steps") != end_exclusive - first
        ):
            raise V7ExposureAuditReplayError(f"{context} declared phase indices mismatch")
        schedule.append({
            "phase_id": phase_id,
            "first_control_step": first,
            "last_control_step": end_exclusive - 1,
            "control_steps": end_exclusive - first,
        })
        cursor = end_exclusive
    if cursor != contract["full_exposure_control_steps"]:
        raise V7ExposureAuditReplayError(
            "frozen phase schedule does not cover the full exposure horizon"
        )
    return schedule


def _phase_of_control_step(schedule: list[dict[str, Any]], step: int) -> str:
    for entry in schedule:
        if entry["first_control_step"] <= step <= entry["last_control_step"]:
            return entry["phase_id"]
    raise V7ExposureAuditReplayError(
        f"control step {step} is outside the frozen phase schedule"
    )


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
        raise V7ExposureAuditReplayError("frozen phase schedule must not be empty")
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
        raise V7ExposureAuditReplayError("audit protocol recorder convention mismatch")
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
            raise V7ExposureAuditReplayError(
                f"reproduced recorder convention never records phase {phase_id}"
            )
        first = min(indices)
        last = max(indices)
        if indices != list(range(first, last + 1)):
            raise V7ExposureAuditReplayError(
                f"reproduced recorder phase {phase_id} is not contiguous"
            )
        schedule.append({
            "phase_id": phase_id,
            "first_control_step": first,
            "last_control_step": last,
            "control_steps": len(indices),
        })
    if sum(item["control_steps"] for item in schedule) != contract["full_exposure_control_steps"]:
        raise V7ExposureAuditReplayError(
            "reproduced recorder convention does not cover the full exposure horizon"
        )
    declared = _require_list(
        convention.get("recorder_phase_boundaries"),
        "protocol.phase_convention.recorder_phase_boundaries",
    )
    if declared != schedule:
        raise V7ExposureAuditReplayError(
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
        raise V7ExposureAuditReplayError("audited raw episodes schema mismatch")
    if raw.get("protocol_id") != PILOT_PROTOCOL_ID:
        raise V7ExposureAuditReplayError("audited raw episodes protocol mismatch")
    _require_string(raw.get("protocol_sha256"), "raw.protocol_sha256", pattern=SHA256_PATTERN)
    pre = _require_string(
        raw.get("source_git_sha_pre"), "raw.source_git_sha_pre", pattern=GIT_SHA_PATTERN
    )
    post = _require_string(
        raw.get("source_git_sha_post"), "raw.source_git_sha_post", pattern=GIT_SHA_PATTERN
    )
    if pre != post:
        raise V7ExposureAuditReplayError("audited raw episodes Git pre/post identity drift")
    _require_false(raw.get("source_dirty_pre"), "raw.source_dirty_pre")
    _require_false(raw.get("source_dirty_post"), "raw.source_dirty_post")
    if raw.get("run_class") != "DEVELOPMENT" or raw.get("data_partition") != "DEVELOPMENT":
        raise V7ExposureAuditReplayError("audited raw episodes must remain DEVELOPMENT")
    if raw.get("evidence_scope") != "SIM_ONLY_MUJOCO":
        raise V7ExposureAuditReplayError("audited raw episodes evidence scope mismatch")
    if raw.get("expected_arm_count") != len(ARM_IDS):
        raise V7ExposureAuditReplayError("audited raw episodes arm count mismatch")
    if raw.get("expected_episodes_per_arm") != len(EXPECTED_SEEDS):
        raise V7ExposureAuditReplayError("audited raw episodes episode count mismatch")
    _require_false(raw.get("paper_data_ready"), "raw.paper_data_ready")
    arms = _require_list(raw.get("arms"), "raw.arms")
    ids = [
        _require_string(
            _require_object(item, f"raw.arms[{index}]").get("arm_id"), f"raw.arms[{index}].arm_id"
        )
        for index, item in enumerate(arms)
    ]
    if ids != list(ARM_IDS):
        raise V7ExposureAuditReplayError("audited raw episodes arm inventory mismatch")


def _validate_pilot_summary(pilot_summary: dict[str, Any], raw: dict[str, Any]) -> None:
    if pilot_summary.get("schema_version") != PILOT_SUMMARY_SCHEMA:
        raise V7ExposureAuditReplayError("audited pilot summary schema mismatch")
    if pilot_summary.get("protocol_id") != PILOT_PROTOCOL_ID:
        raise V7ExposureAuditReplayError("audited pilot summary protocol mismatch")
    if pilot_summary.get("protocol_sha256") != raw.get("protocol_sha256"):
        raise V7ExposureAuditReplayError("audited pilot summary protocol hash drift")
    for key in ("source_git_sha_pre", "source_git_sha_post"):
        if pilot_summary.get(key) != raw.get(key):
            raise V7ExposureAuditReplayError(f"audited pilot summary {key} drift")
    if "selected_candidate_arm_id" not in pilot_summary:
        raise V7ExposureAuditReplayError(
            "audited pilot summary omits selected_candidate_arm_id"
        )
    if pilot_summary["selected_candidate_arm_id"] is not None:
        raise V7ExposureAuditReplayError("audited pilot summary selected a candidate")
    _require_false(pilot_summary.get("paper_data_ready"), "pilot_summary.paper_data_ready")
    _require_string(pilot_summary.get("selection_status"), "pilot_summary.selection_status")
    summaries = _require_list(
        pilot_summary.get("arm_summaries"), "pilot_summary.arm_summaries"
    )
    ids = [
        _require_string(
            _require_object(item, f"pilot_summary.arm_summaries[{index}]").get("arm_id"),
            f"pilot_summary.arm_summaries[{index}].arm_id",
        )
        for index, item in enumerate(summaries)
    ]
    if ids != list(ARM_IDS):
        raise V7ExposureAuditReplayError("audited pilot summary arm inventory mismatch")
    contrasts = _require_list(
        pilot_summary.get("paired_contrasts"), "pilot_summary.paired_contrasts"
    )
    candidates = [
        _require_string(
            _require_object(item, f"pilot_summary.paired_contrasts[{index}]").get(
                "candidate_arm_id"
            ),
            f"pilot_summary.paired_contrasts[{index}].candidate_arm_id",
        )
        for index, item in enumerate(contrasts)
    ]
    if candidates != list(CANDIDATE_ARM_IDS):
        raise V7ExposureAuditReplayError("audited pilot summary contrast inventory mismatch")


def _bind_receipt_artifacts(
    receipt: dict[str, Any],
    *,
    raw_sha256: str,
    pilot_summary_sha256: str,
    audited_protocol_sha256: str,
) -> None:
    """Require the handed files to be the ones the pilot receipt indexes.

    Without this the replay would happily mint a PASS receipt asserting a
    bundle class over files that the audited receipt never indexed.
    """
    artifacts = _require_list(receipt.get("artifacts"), "pilot_receipt.artifacts")
    by_role: dict[str, str] = {}
    for position, record_value in enumerate(artifacts):
        context = f"pilot_receipt.artifacts[{position}]"
        record = _require_object(record_value, context)
        role = _require_string(record.get("role"), context + ".role")
        digest = _require_string(
            record.get("sha256"), context + ".sha256", pattern=SHA256_PATTERN
        )
        if role in by_role:
            raise V7ExposureAuditReplayError(f"duplicate audited inventory role: {role}")
        by_role[role] = digest
    for role, actual in (
        ("raw_episodes", raw_sha256),
        ("pilot_summary", pilot_summary_sha256),
        ("protocol", audited_protocol_sha256),
    ):
        if role not in by_role:
            raise V7ExposureAuditReplayError(
                f"audited bundle receipt does not index the {role} role"
            )
        if by_role[role] != actual:
            raise V7ExposureAuditReplayError(
                f"file handed to the replay is not the indexed {role} artifact"
            )


def _validate_pilot_receipt(receipt: dict[str, Any], receipt_sha256: str) -> str:
    if receipt.get("schema_version") != PILOT_RECEIPT_SCHEMA:
        raise V7ExposureAuditReplayError("audited bundle receipt schema mismatch")
    if receipt.get("protocol_id") != PILOT_PROTOCOL_ID:
        raise V7ExposureAuditReplayError("audited bundle receipt protocol mismatch")
    if receipt.get("contract_valid") is not True:
        raise V7ExposureAuditReplayError("audited bundle receipt is not contract valid")
    if "selected_candidate_arm_id" not in receipt:
        raise V7ExposureAuditReplayError(
            "audited bundle receipt omits selected_candidate_arm_id"
        )
    if receipt["selected_candidate_arm_id"] is not None:
        raise V7ExposureAuditReplayError("audited bundle receipt selected a candidate")
    if receipt.get("evidence_complete") is not True:
        raise V7ExposureAuditReplayError("audited bundle receipt is not evidence complete")
    _require_false(receipt.get("paper_data_ready"), "pilot_receipt.paper_data_ready")
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
        raise V7ExposureAuditReplayError(
            "audited bundle class binding disagrees with the pilot receipt SHA-256"
        )
    return resolved


def _retained_measurement(value: Any, context: str) -> dict[str, Any]:
    item = _require_object(value, context)
    state = _require_string(
        item.get("state"), context + ".state", choices=set(RETAINED_OUTCOME_STATES)
    )
    raw_value = item.get("value")
    if state == "OBSERVED":
        number = _require_number(raw_value, context + ".value")
    else:
        if raw_value is not None:
            raise V7ExposureAuditReplayError(
                f"{context}.value must be null when not observed"
            )
        number = None
    return {"state": state, "value": number}


def _episode_exposure(
    episode: Any,
    contract: dict[str, Any],
    schedule: list[dict[str, Any]],
    recorder_schedule: list[dict[str, Any]],
    context: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    row = _require_object(episode, context)
    seed = _require_int(
        row.get("evaluation_seed"), context + ".evaluation_seed", minimum=0, maximum=2**63 - 1
    )
    if seed in RETIRED_SEED_RANGE:
        raise V7ExposureAuditReplayError(f"{context} observed retired seed {seed}")
    if seed in SEALED_SEED_RANGE:
        raise V7ExposureAuditReplayError(f"{context} observed sealed FORMAL/HOLDOUT seed {seed}")
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
        raise V7ExposureAuditReplayError(
            f"{context}.measurements missing {PRIMARY_MEASUREMENT_ID}"
        )
    primary = _retained_measurement(
        measurements[PRIMARY_MEASUREMENT_ID],
        f"{context}.measurements.{PRIMARY_MEASUREMENT_ID}",
    )
    substeps_per_step = contract["physics_substeps_per_control_step"]
    full_steps = contract["full_exposure_control_steps"]
    full_substeps = contract["full_exposure_physics_substeps"]
    trace = _require_list(row.get("control_step_trace"), context + ".control_step_trace")
    observed_steps = len(trace)
    if observed_steps > full_steps:
        raise V7ExposureAuditReplayError(f"{context} OVER_EXPOSURE beyond the frozen horizon")
    if (terminal_state == "COMPLETED") != (observed_steps > 0):
        raise V7ExposureAuditReplayError(
            f"{context} terminal record state and retained trace presence disagree"
        )
    prefix_over = [0]
    prefix_total = [0]
    phase_counts = {entry["phase_id"]: 0 for entry in recorder_schedule}
    for index, item_value in enumerate(trace):
        item_context = f"{context}.control_step_trace[{index}]"
        item = _require_object(item_value, item_context)
        if item.get("control_step") != index:
            raise V7ExposureAuditReplayError(f"{item_context}.control_step is not contiguous")
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
            raise V7ExposureAuditReplayError(f"{item_context} saturation count exceeds total")
        recorded_phase = _require_string(
            item.get("command_phase"), item_context + ".command_phase"
        )
        if recorded_phase != _phase_of_control_step(recorder_schedule, index):
            raise V7ExposureAuditReplayError(
                f"{item_context}.command_phase disagrees with the reproduced "
                "recorder convention"
            )
        phase_counts[recorded_phase] += 1
        prefix_over.append(prefix_over[-1] + over)
        prefix_total.append(prefix_total[-1] + total)
    over_total = prefix_over[-1]
    substep_total = prefix_total[-1]
    if substep_total != observed_steps * substeps_per_step:
        raise V7ExposureAuditReplayError(
            f"{context} exposure denominator disagrees with the retained control steps"
        )
    trace_receipt = _require_object(row.get("trace_receipt"), context + ".trace_receipt")
    for counter in (
        "control_step_count",
        "saturation_substeps_total",
        "saturation_substeps_over_threshold",
    ):
        _require_int(
            trace_receipt.get(counter),
            f"{context}.trace_receipt.{counter}",
            minimum=0,
            maximum=full_substeps,
        )
    if (
        trace_receipt.get("control_step_count") != observed_steps
        or trace_receipt.get("saturation_substeps_total") != substep_total
        or trace_receipt.get("saturation_substeps_over_threshold") != over_total
    ):
        raise V7ExposureAuditReplayError(f"{context}.trace_receipt count mismatch")
    if observed_steps:
        truncated_duty = _round_percent(100.0 * over_total / substep_total)
        if trace_receipt.get("recomputed_saturation_duty_pct") != truncated_duty:
            raise V7ExposureAuditReplayError(
                f"{context}.trace_receipt.recomputed_saturation_duty_pct mismatch"
            )
        if primary["state"] == "OBSERVED" and abs(truncated_duty - primary["value"]) > 1.0e-12:
            raise V7ExposureAuditReplayError(
                f"{context} retained saturation duty disagrees with the retained counts"
            )
    else:
        truncated_duty = None
        if primary["state"] == "OBSERVED":
            raise V7ExposureAuditReplayError(
                f"{context} has no exposure but retains an observed primary outcome"
            )
        if trace_receipt.get("recomputed_saturation_duty_pct") is not None:
            raise V7ExposureAuditReplayError(
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
        raise V7ExposureAuditReplayError(
            f"{context} recorded termination phase disagrees with the "
            "reproduced recorder convention"
        )
    phase_coverage: list[dict[str, Any]] = []
    for entry in recorder_schedule:
        observed_in_phase = max(
            0, min(observed_steps, entry["last_control_step"] + 1) - entry["first_control_step"]
        )
        if observed_in_phase != phase_counts[entry["phase_id"]]:
            raise V7ExposureAuditReplayError(
                f"{context} recorded phase coverage disagrees with the frozen schedule"
            )
        phase_coverage.append({
            "phase_id": entry["phase_id"],
            "expected_control_steps": entry["control_steps"],
            "observed_control_steps": observed_in_phase,
            "complete": observed_in_phase == entry["control_steps"],
        })
    if (
        primary["state"] != "OBSERVED"
        or terminal_state != "COMPLETED"
        or exposure_class == "NO_EXPOSURE"
    ):
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
            raise V7ExposureAuditReplayError(f"{context} identification bound is inverted")
        if exposure_class == "FULL_EXPOSURE" and not (lower_pct == upper_pct == truncated_duty):
            raise V7ExposureAuditReplayError(
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
        raise V7ExposureAuditReplayError("exposure statistics require the exact seed inventory")
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


def _pilot_reported_statistics(pilot_arm_summary: dict[str, Any], context: str) -> dict[str, Any]:
    reported = _require_object(
        pilot_arm_summary.get(PRIMARY_MEASUREMENT_ID),
        f"{context}.pilot_summary.{PRIMARY_MEASUREMENT_ID}",
    )
    state = _require_string(
        reported.get("state"),
        f"{context}.pilot_summary.state",
        choices=set(RETAINED_OUTCOME_STATES),
    )
    mean = reported.get("mean")
    deviation = reported.get("sample_standard_deviation")
    if state == "OBSERVED":
        mean = _require_number(mean, f"{context}.pilot_summary.mean")
        deviation = _require_number(deviation, f"{context}.pilot_summary.sd")
    elif mean is not None or deviation is not None:
        raise V7ExposureAuditReplayError(
            f"{context} pilot statistics must be null when not observed"
        )
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


def _arm_exposure(
    arm: Any,
    pilot_arm_summary: dict[str, Any],
    contract: dict[str, Any],
    schedule: list[dict[str, Any]],
    recorder_schedule: list[dict[str, Any]],
    context: str,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    block = _require_object(arm, context)
    arm_id = _require_string(block.get("arm_id"), context + ".arm_id")
    if pilot_arm_summary.get("arm_id") != arm_id:
        raise V7ExposureAuditReplayError(f"{context} pilot summary arm binding mismatch")
    rows = _require_list(block.get("episodes"), context + ".episodes")
    if len(rows) != len(EXPECTED_SEEDS):
        raise V7ExposureAuditReplayError(f"{context} terminal record count mismatch")
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
        raise V7ExposureAuditReplayError(f"{context} duplicate evaluation seed")
    if sorted(seeds) != list(EXPECTED_SEEDS):
        raise V7ExposureAuditReplayError(f"{context} missing or unexpected evaluation seed")
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
            # An episode lacks a bound only when it is a retained method
            # failure, so naming exposure censoring here would misattribute it.
            "reason": BLOCKED_METHOD_FAILURE_REASON,
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
    terminated = [
        item["termination_control_step"]
        for item in records
        if item["termination_control_step"] is not None
    ]
    summary = {
        "arm_id": arm_id,
        "record_count": len(records),
        "training_terminal_state": _require_string(
            block.get("training_terminal_state"),
            context + ".training_terminal_state",
            choices=set(RETAINED_TERMINAL_STATES),
        ),
        "evaluation_terminal_state": _require_string(
            block.get("evaluation_terminal_state"),
            context + ".evaluation_terminal_state",
            choices=set(RETAINED_TERMINAL_STATES),
        ),
        "terminal_record_state_counts": _state_counts(
            [item["terminal_record_state"] for item in records], RETAINED_TERMINAL_STATES
        ),
        "outcome_state_counts": _state_counts(
            [item["outcome_state"] for item in records], RETAINED_OUTCOME_STATES
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
        "earliest_termination_control_step": min(terminated) if terminated else None,
        "latest_termination_control_step": max(terminated) if terminated else None,
        "full_horizon_duty_bound_pct": bound_aggregate,
        "pilot_reported_saturation_duty_pct": _pilot_reported_statistics(
            pilot_arm_summary, context
        ),
        "episodes": records,
    }
    return summary, internals


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
            raise V7ExposureAuditReplayError(
                f"{context} statistics must be null when not observed"
            )
        return {
            "state": state,
            "n_observed": _require_int(
                block.get("n_observed"),
                context + ".n_observed",
                minimum=0,
                maximum=len(EXPECTED_SEEDS),
            ),
            "mean_difference": mean,
            "sample_standard_deviation": deviation,
            "retention": "RETAINED_VERBATIM_FROM_FROZEN_PILOT_SUMMARY_NOT_RECOMPUTED",
        }
    raise V7ExposureAuditReplayError(f"pilot summary has no contrast for {candidate_arm_id}")


def _paired_comparability(
    reference: dict[str, Any],
    candidate: dict[str, Any],
    pilot_summary: dict[str, Any],
) -> dict[str, Any]:
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
            lower_pct = _round_percent(
                candidate_bound["lower_pct"] - reference_bound["upper_pct"]
            )
            upper_pct = _round_percent(
                candidate_bound["upper_pct"] - reference_bound["lower_pct"]
            )
            if upper_pct < lower_pct:
                raise V7ExposureAuditReplayError(
                    f"paired identification bound for seed {seed} is inverted"
                )
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
    censored_count = sum(
        1 for item in pairs if item["pair_comparability_state"] == "EXPOSURE_CENSORED"
    )
    method_failure_count = sum(
        1
        for item in pairs
        if item["pair_comparability_state"] == "METHOD_FAILURE_NOT_CENSORING"
    )
    blocked_reason = _blocked_reason(censored_count, method_failure_count)
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
            "reason": blocked_reason,
        }
    if len(bound_lowers) == len(EXPECTED_SEEDS):
        bound_aggregate = {
            "state": "OBSERVED",
            "n_expected": len(EXPECTED_SEEDS),
            "n_observed": len(bound_lowers),
            "mean_lower_pct": statistics.fmean(bound_lowers),
            "mean_upper_pct": statistics.fmean(bound_uppers),
            "sign_identified_pair_count": sign_identified_count,
            "sign_identified_is_complete_case": True,
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
            "sign_identified_is_complete_case": False,
            "reason": BLOCKED_METHOD_FAILURE_REASON,
        }
    return {
        "reference_arm_id": reference["arm_id"],
        "candidate_arm_id": candidate["arm_id"],
        "contrast": "candidate_minus_reference_by_evaluation_seed",
        "comparable_pair_count": comparable_count,
        "exposure_censored_pair_count": censored_count,
        "method_failure_pair_count": method_failure_count,
        "validity_verdict": (
            VERDICT_COMPARABLE
            if comparable_count == len(EXPECTED_SEEDS)
            else _non_comparable_verdict(censored_count, method_failure_count)
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
        raise V7ExposureAuditReplayError("matched exposure denominator must be positive")
    return _round_percent(100.0 * internal["prefix_over"][steps] / total)


def _exposure_matched_sensitivity(
    reference: dict[str, Any],
    candidate: dict[str, Any],
    reference_internals: dict[str, dict[str, Any]],
    candidate_internals: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    reference_states = {
        item["evaluation_seed"]: item["comparability_state"] for item in reference["episodes"]
    }
    candidate_states = {
        item["evaluation_seed"]: item["comparability_state"] for item in candidate["episodes"]
    }
    pairs: list[dict[str, Any]] = []
    differences: list[float] = []
    method_failure_pairs = 0
    for seed in EXPECTED_SEEDS:
        key = str(seed)
        reference_internal = reference_internals[key]
        candidate_internal = candidate_internals[key]
        matched = min(
            reference_internal["observed_control_steps"],
            candidate_internal["observed_control_steps"],
        )
        # A retained method failure is never re-materialized as an observed
        # matched duty, even when its trace still carries usable counts.
        method_failure = "METHOD_FAILURE_NOT_CENSORING" in {
            reference_states[seed],
            candidate_states[seed],
        }
        reference_duty = None if method_failure else _matched_duty(reference_internal, matched)
        candidate_duty = None if method_failure else _matched_duty(candidate_internal, matched)
        if reference_duty is None or candidate_duty is None:
            method_failure_pairs += 1
            pairs.append({
                "evaluation_seed": seed,
                "matched_exposure_control_steps": matched,
                "state": "NULL",
                "reference_matched_duty_pct": None,
                "candidate_matched_duty_pct": None,
                "matched_difference_pct": None,
                "reason": (
                    REASON_METHOD_FAILURE_OUTCOME
                    if method_failure
                    else REASON_METHOD_FAILURE_NO_EXPOSURE
                ),
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
            "reason": _blocked_reason(
                len(EXPECTED_SEEDS) - len(differences) - method_failure_pairs,
                method_failure_pairs,
            ),
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
        for episode in arm["episodes"]:
            state = episode["comparability_state"]
            if state != "COMPARABLE":
                blockers.append(
                    f"{arm['arm_id']}:SEED_{episode['evaluation_seed']}_{state}"
                )
    for block in paired_blocks:
        if block["validity_verdict"] != VERDICT_COMPARABLE:
            blockers.append(f"{block['candidate_arm_id']}:{block['validity_verdict']}")
    return blockers


def build_audit_summary(
    protocol: dict[str, Any],
    raw: dict[str, Any],
    pilot_summary: dict[str, Any],
    *,
    source_bundle_class: str,
    pilot_receipt_sha256: str,
) -> dict[str, Any]:
    """Independently reconstruct the audit summary from canonical raw rows.

    The preconditions are deliberately identical to the contract module's
    builder so that the two implementations cannot diverge on which inputs
    they accept, not only on what they compute.
    """
    if source_bundle_class not in BUNDLE_CLASSES:
        raise V7ExposureAuditReplayError(
            f"unsupported source bundle class: {source_bundle_class}"
        )
    _require_string(pilot_receipt_sha256, "pilot_receipt_sha256", pattern=SHA256_PATTERN)
    if (pilot_receipt_sha256 == FROZEN_PILOT_RECEIPT_SHA256) != (
        source_bundle_class == DEVELOPMENT_BUNDLE_CLASS
    ):
        raise V7ExposureAuditReplayError(
            "source bundle class binding disagrees with the pilot receipt SHA-256"
        )
    _validate_raw(raw)
    _validate_pilot_summary(pilot_summary, raw)
    if (
        source_bundle_class == DEVELOPMENT_BUNDLE_CLASS
        and raw["protocol_sha256"] != AUDITED_PROTOCOL_SHA256
    ):
        raise V7ExposureAuditReplayError(
            "a frozen v7 pilot bundle must retain the pinned audited protocol "
            f"SHA-256, found {raw['protocol_sha256']}"
        )
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
            _require_object(
                pilot_arm_summaries[arm_id], f"pilot_summary.arm_summaries[{arm_id}]"
            ),
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
    # An arm is non-comparable when it has no comparable episode at all; full
    # exposure elsewhere in the arm does not excuse that, so exposure class is
    # deliberately not part of the condition.
    non_comparable_arms: list[str] = []
    non_comparable_causes: dict[str, str] = {}
    for arm in arm_blocks:
        counts = arm["comparability_state_counts"]
        if counts["COMPARABLE"]:
            continue
        non_comparable_arms.append(arm["arm_id"])
        censored = counts["EXPOSURE_CENSORED"]
        failed = counts["METHOD_FAILURE_NOT_CENSORING"]
        if censored and failed:
            non_comparable_causes[arm["arm_id"]] = "EXPOSURE_CENSORED_AND_METHOD_FAILURE"
        elif failed:
            non_comparable_causes[arm["arm_id"]] = "METHOD_FAILURE_NOT_CENSORING"
        else:
            non_comparable_causes[arm["arm_id"]] = "EXPOSURE_CENSORED"
    non_comparable_arms.sort()
    causes = set(non_comparable_causes.values())
    if not causes:
        zero_duty_interpretation = "NOT_APPLICABLE_ALL_ARMS_HAVE_COMPARABLE_EPISODES"
    elif causes == {"EXPOSURE_CENSORED"}:
        zero_duty_interpretation = "NON_COMPARABLE_EXPOSURE_CENSORED"
    elif causes == {"METHOD_FAILURE_NOT_CENSORING"}:
        zero_duty_interpretation = "NON_COMPARABLE_RETAINED_METHOD_FAILURE"
    else:
        zero_duty_interpretation = (
            "NON_COMPARABLE_EXPOSURE_CENSORED_AND_RETAINED_METHOD_FAILURE"
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
            "arms_without_any_comparable_episode": non_comparable_arms,
            "non_comparable_arm_causes": non_comparable_causes,
            "zero_duty_interpretation": zero_duty_interpretation,
            "censored_estimator": "NOT_FROZEN_BOUNDS_ONLY",
            "identification_bound_assumption": (
                "THE_BOUNDS_ARE_ASSUMPTION_FREE_GIVEN_THE_CONTRACT_DEFINED_FULL_HORIZON"
                "_ESTIMAND; FOR_AN_EARLY_TERMINATED_EPISODE_THAT_ESTIMAND_IS_A_FROZEN"
                "_TASK_TARGET_AND_NOT_AN_OBSERVED_COUNTERFACTUAL_OF_A_CONTINUABLE_EPISODE"
            ),
            "method_failure_doctrine": (
                "METHOD_FAILURE_IS_RETAINED_AND_IS_NOT_TREATED_AS_CENSORING"
            ),
        },
        "censoring_blockers": blockers,
        "censoring_blocker_count": len(blockers),
        "audit_status": AUDIT_STATUS_BLOCKED if blockers else AUDIT_STATUS_CLEAN,
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
        "pilot_planning_ready": False,
        "method_level_power_ready": False,
        "statistics_ready": False,
        "paper_data_ready": False,
        "claim_boundary": CLAIM_BOUNDARY,
    }


def replay_audit(
    protocol: dict[str, Any],
    pilot_receipt: dict[str, Any],
    raw: dict[str, Any],
    pilot_summary: dict[str, Any],
    audit_summary: dict[str, Any],
    *,
    protocol_sha256: str,
    receipt_sha256: str,
    raw_sha256: str,
    pilot_summary_sha256: str,
    audit_summary_sha256: str,
) -> dict[str, Any]:
    """Validate inputs, reconstruct the audit summary, and require exact identity."""
    _validate_audit_protocol(protocol, protocol_sha256)
    bundle_class = _validate_pilot_receipt(pilot_receipt, receipt_sha256)
    _bind_receipt_artifacts(
        pilot_receipt,
        raw_sha256=raw_sha256,
        pilot_summary_sha256=pilot_summary_sha256,
        audited_protocol_sha256=_require_string(
            raw.get("protocol_sha256"), "raw.protocol_sha256", pattern=SHA256_PATTERN
        ),
    )
    # build_audit_summary re-validates raw and the pilot summary itself, so the
    # builder's preconditions stay identical to the contract module's.
    expected = build_audit_summary(
        protocol,
        raw,
        pilot_summary,
        source_bundle_class=bundle_class,
        pilot_receipt_sha256=receipt_sha256,
    )
    staged = (
        ("frozen_task_horizon_exact", "exposure_contract"),
        ("contract_phase_schedule_exact", "contract_phase_schedule"),
        ("recorder_phase_convention_exact", "recorder_phase_schedule"),
        ("phase_convention_offset_exact", "phase_convention"),
        ("exposure_and_censoring_exact", "arm_exposure"),
        ("paired_comparability_exact", "paired_comparability"),
        ("exposure_matched_sensitivity_exact", "exposure_matched_sensitivity"),
        ("audit_findings_exact", "audit_findings"),
        ("censoring_blockers_exact", "censoring_blockers"),
        ("original_pilot_selection_preserved", "preserved_pilot_selection"),
    )
    for _, key in staged:
        if audit_summary.get(key) != expected[key]:
            raise V7ExposureAuditReplayError(
                f"primary audit summary differs from the raw-episode replay at {key}"
            )
    if audit_summary != expected:
        differing = sorted(
            key
            for key in set(audit_summary) | set(expected)
            if audit_summary.get(key) != expected.get(key)
        )
        raise V7ExposureAuditReplayError(
            f"primary audit summary differs from the raw-episode replay: {differing}"
        )
    checks = {name: True for name, _ in staged}
    checks["frozen_audit_protocol_exact"] = True
    checks["exact_three_arm_seed_inventory"] = True
    checks["identification_bounds_exact"] = True
    checks["audit_summary_exact"] = True
    if tuple(sorted(checks)) != EXPECTED_REPLAY_CHECKS:
        raise V7ExposureAuditReplayError(
            "replay check inventory drifted from the frozen set: "
            f"{sorted(set(checks) ^ set(EXPECTED_REPLAY_CHECKS))}"
        )
    return {
        "schema_version": REPLAY_SCHEMA,
        "status": "PASS",
        "exact_identity": True,
        "checks": dict(sorted(checks.items())),
        "source_bundle_class": bundle_class,
        "audit_applies_to_frozen_v7_pilot": bundle_class == DEVELOPMENT_BUNDLE_CLASS,
        "audit_status": expected["audit_status"],
        "censoring_blocker_count": expected["censoring_blocker_count"],
        "audit_protocol_sha256": protocol_sha256,
        "pilot_receipt_sha256": receipt_sha256,
        "raw_episodes_sha256": raw_sha256,
        "pilot_summary_sha256": pilot_summary_sha256,
        "audit_summary_sha256": audit_summary_sha256,
        "pilot_planning_ready": False,
        "method_level_power_ready": False,
        "statistics_ready": False,
        "paper_data_ready": False,
        "claim_boundary": CLAIM_BOUNDARY,
    }


def _run(paths: list[Path]) -> dict[str, Any]:
    protocol_path, receipt_path, raw_path, pilot_summary_path, audit_summary_path = paths
    return replay_audit(
        _load_json(protocol_path),
        _load_json(receipt_path),
        _load_json(raw_path),
        _load_json(pilot_summary_path),
        _load_json(audit_summary_path),
        protocol_sha256=_sha256_file(protocol_path),
        receipt_sha256=_sha256_file(receipt_path),
        raw_sha256=_sha256_file(raw_path),
        pilot_summary_sha256=_sha256_file(pilot_summary_path),
        audit_summary_sha256=_sha256_file(audit_summary_path),
    )


def main() -> None:
    if len(sys.argv) != 6:
        payload = {
            "schema_version": REPLAY_ERROR_SCHEMA,
            "status": "ERROR",
            "exact_identity": False,
            "error": (
                "expected audit protocol, pilot receipt, raw episodes, pilot "
                "summary, and audit summary paths"
            ),
            "pilot_planning_ready": False,
            "method_level_power_ready": False,
            "statistics_ready": False,
            "paper_data_ready": False,
            "claim_boundary": CLAIM_BOUNDARY,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False))
        raise SystemExit(2)
    try:
        receipt = _run([Path(value).resolve() for value in sys.argv[1:]])
    except Exception as exc:
        receipt = {
            "schema_version": REPLAY_ERROR_SCHEMA,
            "status": "ERROR",
            "exact_identity": False,
            "error": f"{type(exc).__name__}: {exc}"[:1000],
            "pilot_planning_ready": False,
            "method_level_power_ready": False,
            "statistics_ready": False,
            "paper_data_ready": False,
            "claim_boundary": CLAIM_BOUNDARY,
        }
        print(json.dumps(receipt, ensure_ascii=False, indent=2, allow_nan=False))
        raise SystemExit(2) from exc
    print(json.dumps(receipt, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()

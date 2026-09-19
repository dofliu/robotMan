"""Standard-library-only replay for the frozen v7 action-interface pilot.

The process intentionally imports neither the primary bundle builder nor the
training/evaluation stack.  It validates the frozen protocol and canonical raw
episode rows, reconstructs every descriptive statistic and selection outcome,
and requires exact JSON identity with the primary summary.
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


PROTOCOL_SCHEMA = "V7_ACTION_INTERFACE_PILOT_PROTOCOL_V1"
RAW_SCHEMA = "V7_PILOT_RAW_EPISODES_V1"
SUMMARY_SCHEMA = "V7_PILOT_SUMMARY_V1"
REPLAY_SCHEMA = "V7_PILOT_REPLAY_RECEIPT_V1"
REPLAY_ERROR_SCHEMA = "V7_PILOT_REPLAY_ERROR_RECEIPT_V1"
PROTOCOL_ID = "PILOT-V7-ACTION-INTERFACE-DEV-V1"
PROTOCOL_SHA256 = (
    "sha256:719b70a2bdf8d23af5f4ec5dff51a6099e88d6de4e2221fa74f6f7464cdfcb96"
)
CLAIM_BOUNDARY = (
    "SIM_ONLY_MUJOCO / NOT_PHYSICALLY_VALIDATED / DEVELOPMENT_ONLY. The pilot "
    "may support only a conditional action-interface screening statement for this "
    "frozen simulated plant, checkpoint, task, and evaluation-seed set. It does "
    "not support controller superiority, method-population power, formal sample-"
    "size adequacy, paper readiness, physical torque or thermal margins, safety, "
    "or sim-to-real claims."
)
ARM_IDS = (
    "V7A_REWARD_ONLY",
    "V7B_REDUCED_JOINT_ENVELOPE",
    "V7C_FILTERED_ACTION",
)
CANDIDATE_ARM_IDS = ARM_IDS[1:]
EXPECTED_SEEDS = tuple(range(18000, 18030))
RETAINED_TERMINAL_STATES = ("COMPLETED", "FAILED", "CANCELLED")
RETAINED_OUTCOME_STATES = ("OBSERVED", "NULL", "NONFINITE")
MEASUREMENT_IDS = (
    "no_fall",
    "steady_speed_mps",
    "steady_progress_m",
    "final_stop_speed_mps",
    "lateral_drift_m",
    "saturation_duty_pct",
)
GATE_SPECS = (
    ("NO_FALL", "no_fall", "==", True, None),
    ("STEADY_SPEED", "steady_speed_mps", "between_inclusive", 0.35, 1.05),
    ("STEADY_PROGRESS", "steady_progress_m", ">=", 1.4, None),
    ("STOP_SPEED", "final_stop_speed_mps", "<=", 0.15, None),
    ("LATERAL_DRIFT", "lateral_drift_m", "<=", 0.3, None),
    ("SATURATION_DUTY", "saturation_duty_pct", "<=", 30.0, None),
)
MAX_JSON_BYTES = 64 * 1024 * 1024
MAX_JSON_DEPTH = 96
MAX_JSON_NODES = 2_000_000
SHA256_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
GIT_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")


class V7PilotReplayError(RuntimeError):
    """The protocol, raw rows, or exact replay identity is untrusted."""


def _reject_constant(value: str) -> None:
    raise V7PilotReplayError(f"JSON non-finite constant is forbidden: {value}")


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise V7PilotReplayError(f"duplicate JSON key is forbidden: {key}")
        result[key] = value
    return result


def _bounded_int(value: str) -> int:
    if len(value.lstrip("-")) > 1000:
        raise V7PilotReplayError("pathological JSON integer is forbidden")
    return int(value)


def _check_tree(root: Any) -> None:
    stack = [(root, 1)]
    nodes = 0
    while stack:
        value, depth = stack.pop()
        nodes += 1
        if nodes > MAX_JSON_NODES:
            raise V7PilotReplayError("JSON node limit exceeded")
        if depth > MAX_JSON_DEPTH:
            raise V7PilotReplayError("JSON nesting limit exceeded")
        if isinstance(value, dict):
            stack.extend((item, depth + 1) for item in value.values())
        elif isinstance(value, list):
            stack.extend((item, depth + 1) for item in value)
        elif type(value) is float and not math.isfinite(value):
            raise V7PilotReplayError("JSON non-finite number is forbidden")


def _load_json(path: Path) -> dict[str, Any]:
    try:
        if not path.is_file():
            raise V7PilotReplayError(f"missing JSON artifact: {path.name}")
        if path.stat().st_size > MAX_JSON_BYTES:
            raise V7PilotReplayError(f"JSON artifact exceeds byte limit: {path.name}")
        value = json.loads(
            path.read_text(encoding="utf-8"),
            parse_constant=_reject_constant,
            parse_int=_bounded_int,
            object_pairs_hook=_reject_duplicate_keys,
        )
        _check_tree(value)
    except V7PilotReplayError:
        raise
    except (OSError, UnicodeError, ValueError, RecursionError) as exc:
        raise V7PilotReplayError(f"invalid JSON artifact: {path.name}") from exc
    if not isinstance(value, dict):
        raise V7PilotReplayError(f"JSON root must be an object: {path.name}")
    return value


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _require_object(value: Any, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise V7PilotReplayError(f"{context} must be an object")
    return value


def _require_exact_keys(
    value: Any,
    keys: set[str],
    context: str,
) -> dict[str, Any]:
    item = _require_object(value, context)
    actual = set(item)
    if actual != keys:
        raise V7PilotReplayError(
            f"{context} fields mismatch: missing={sorted(keys - actual)}, "
            f"unexpected={sorted(actual - keys)}"
        )
    return item


def _require_string(
    value: Any,
    context: str,
    *,
    pattern: re.Pattern[str] | None = None,
    choices: set[str] | None = None,
) -> str:
    if not isinstance(value, str):
        raise V7PilotReplayError(f"{context} must be a string")
    if pattern is not None and pattern.fullmatch(value) is None:
        raise V7PilotReplayError(f"{context} has invalid format")
    if choices is not None and value not in choices:
        raise V7PilotReplayError(f"{context} has unsupported value: {value}")
    return value


def _require_int(
    value: Any,
    context: str,
    *,
    minimum: int,
    maximum: int,
) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise V7PilotReplayError(
            f"{context} must be an integer in [{minimum}, {maximum}]"
        )
    return value


def _safe_relative_path(value: Any, context: str) -> str:
    path = _require_string(value, context)
    normalized = path.replace("\\", "/")
    pure = PurePosixPath(normalized)
    if (
        not normalized
        or pure.is_absolute()
        or normalized.startswith("//")
        or any(":" in part for part in pure.parts)
        or ".." in pure.parts
        or normalized != pure.as_posix()
    ):
        raise V7PilotReplayError(f"{context} must be a canonical safe relative path")
    return normalized


def _validate_protocol(protocol: dict[str, Any], protocol_sha256: str) -> None:
    if protocol_sha256 != PROTOCOL_SHA256:
        raise V7PilotReplayError("frozen protocol SHA-256 mismatch")
    if protocol.get("schema_version") != PROTOCOL_SCHEMA:
        raise V7PilotReplayError("frozen protocol schema mismatch")
    exact = {
        "protocol_id": PROTOCOL_ID,
        "protocol_status": "FROZEN_INTERNAL_DEVELOPMENT",
        "run_class": "DEVELOPMENT",
        "evidence_scope": "SIM_ONLY_MUJOCO",
        "validation_status": "NOT_PHYSICALLY_VALIDATED",
        "paper_data_ready": False,
        "claim_boundary": CLAIM_BOUNDARY,
    }
    for key, expected in exact.items():
        if protocol.get(key) != expected:
            raise V7PilotReplayError(f"frozen protocol {key} mismatch")
    evaluation = _require_object(protocol.get("evaluation_design"), "evaluation_design")
    if evaluation.get("evaluation_seeds") != list(EXPECTED_SEEDS):
        raise V7PilotReplayError("frozen evaluation seeds mismatch")
    if evaluation.get("retired_seed_range") != [19000, 19029]:
        raise V7PilotReplayError("retired seed range mismatch")
    if evaluation.get("sealed_formal_seed_range") != [20000, 20029]:
        raise V7PilotReplayError("sealed FORMAL seed range mismatch")
    if evaluation.get("deterministic_policy") is not True:
        raise V7PilotReplayError("evaluation must be deterministic")
    training = _require_object(protocol.get("training_design"), "training_design")
    frozen_training = {
        "agent_seed": 8700,
        "parallel_envs": 12,
        "environment_seed_start": 8700,
        "environment_seed_end": 8711,
        "independent_training_replicates_per_arm": 1,
        "requested_timesteps": 100000,
        "expected_realized_timesteps": 122880,
        "ppo_rollout_steps_per_env": 2048,
        "ppo_batch_size": 8192,
        "ppo_epochs": 5,
        "device": "cpu",
    }
    for key, expected in frozen_training.items():
        if training.get(key) != expected:
            raise V7PilotReplayError(f"frozen training {key} mismatch")
    arms = protocol.get("arms")
    if not isinstance(arms, list) or len(arms) != 3:
        raise V7PilotReplayError("frozen protocol must contain exactly three arms")
    if tuple(item.get("arm_id") for item in arms if isinstance(item, dict)) != ARM_IDS:
        raise V7PilotReplayError("frozen arm identity/order mismatch")
    criteria = protocol.get("acceptance_criteria")
    if criteria != [f"AP-{index:02d}_{suffix}" for index, suffix in (
        (1, "PROTOCOL_AND_ARM_IDENTITY"),
        (2, "CLEAN_GIT_SOURCE_PRE_POST_IDENTITY"),
        (3, "EXACT_COMMON_TRAINING_SEED_BUDGET_AND_WARM_START"),
        (4, "EXACT_30_PAIRED_DEV_EVALUATION_SEEDS_PER_ARM"),
        (5, "FAILED_CANCELLED_NULL_NONFINITE_RETENTION"),
        (6, "UNCHANGED_PILOT_SUBSET_THRESHOLDS_AND_EXPLICIT_GATE_RESULTS"),
        (7, "CONDITIONAL_VARIANCE_AND_PAIRED_DIFFERENCE_WITH_POWER_BLOCKER"),
        (8, "SAFE_ARTIFACT_PATH_BYTES_AND_SHA256_INVENTORY"),
        (9, "STDLIB_ONLY_RAW_EPISODE_TO_SUMMARY_EXACT_REPLAY"),
        (10, "SIM_ONLY_CLAIM_BOUNDARY_AND_PAPER_DATA_FALSE"),
    )]:
        raise V7PilotReplayError("acceptance criteria identity mismatch")


def _validate_artifact_binding(value: Any, context: str) -> dict[str, Any]:
    item = _require_exact_keys(
        value,
        {"state", "path", "bytes", "sha256", "reason"},
        context,
    )
    state = _require_string(
        item["state"], context + ".state", choices={"PRESENT", "NULL"}
    )
    if state == "PRESENT":
        _safe_relative_path(item["path"], context + ".path")
        _require_int(item["bytes"], context + ".bytes", minimum=1, maximum=2**63 - 1)
        _require_string(item["sha256"], context + ".sha256", pattern=SHA256_PATTERN)
        if item["reason"] is not None:
            raise V7PilotReplayError(f"{context}.reason must be null when PRESENT")
    else:
        if any(item[key] is not None for key in ("path", "bytes", "sha256")):
            raise V7PilotReplayError(f"{context} NULL binding must not name an artifact")
        _require_string(item["reason"], context + ".reason")
    return item


def _validate_measurement(
    value: Any,
    measurement_id: str,
    context: str,
) -> dict[str, Any]:
    item = _require_exact_keys(value, {"state", "value", "reason"}, context)
    state = _require_string(
        item["state"], context + ".state", choices=set(RETAINED_OUTCOME_STATES)
    )
    if state == "OBSERVED":
        if item["reason"] is not None:
            raise V7PilotReplayError(f"{context}.reason must be null when observed")
        if measurement_id == "no_fall":
            if type(item["value"]) is not bool:
                raise V7PilotReplayError(f"{context}.value must be boolean")
        else:
            if type(item["value"]) not in {int, float}:
                raise V7PilotReplayError(f"{context}.value must be numeric")
            try:
                finite = math.isfinite(float(item["value"]))
            except (OverflowError, ValueError):
                finite = False
            if not finite:
                raise V7PilotReplayError(f"{context}.value must be finite")
    else:
        if item["value"] is not None:
            raise V7PilotReplayError(f"{context}.value must be null when non-observed")
        _require_string(item["reason"], context + ".reason")
    return item


def _gate_results(measurements: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for gate_id, measurement_id, operator, threshold, upper in GATE_SPECS:
        measurement = measurements[measurement_id]
        state = measurement["state"]
        value = measurement["value"]
        passed: bool | None
        if state != "OBSERVED":
            passed = None
        elif operator == "==":
            passed = value == threshold
        elif operator == "between_inclusive":
            passed = float(threshold) <= float(value) <= float(upper)
        elif operator == ">=":
            passed = float(value) >= float(threshold)
        elif operator == "<=":
            passed = float(value) <= float(threshold)
        else:  # pragma: no cover - constants above are frozen
            raise V7PilotReplayError(f"unsupported frozen gate operator: {operator}")
        results.append({
            "gate_id": gate_id,
            "measurement_id": measurement_id,
            "state": state,
            "observed_value": value,
            "operator": operator,
            "threshold": threshold,
            "upper_threshold": upper,
            "passed": passed,
            "reason": measurement["reason"],
        })
    return results


def _trace_vector(value: Any, context: str) -> list[float]:
    if not isinstance(value, list) or len(value) != 12:
        raise V7PilotReplayError(f"{context} must contain exactly 12 values")
    return [
        _require_number(item, f"{context}[{index}]")
        for index, item in enumerate(value)
    ]


def _require_number(value: Any, context: str) -> float:
    if type(value) not in {int, float}:
        raise V7PilotReplayError(f"{context} must be numeric")
    try:
        result = float(value)
        finite = math.isfinite(result)
    except (OverflowError, ValueError):
        result = 0.0
        finite = False
    if not finite:
        raise V7PilotReplayError(f"{context} must be finite")
    return result


def _validate_control_trace(
    episode: dict[str, Any],
    frozen_arm: dict[str, Any],
    context: str,
) -> None:
    trace = episode["control_step_trace"]
    if not isinstance(trace, list):
        raise V7PilotReplayError(f"{context}.control_step_trace must be an array")
    terminal_state = episode["terminal_record_state"]
    if terminal_state == "COMPLETED" and not trace:
        raise V7PilotReplayError(f"{context} completed row requires non-empty trace")
    if terminal_state != "COMPLETED" and trace:
        raise V7PilotReplayError(f"{context} terminal failure trace must be empty")
    alpha = frozen_arm["low_pass_alpha"]
    rate_limit = frozen_arm["rate_limit_normalized_per_control_step"]
    previous = [0.0] * 12
    over_total = 0
    substep_total = 0
    max_delta = 0.0
    for index, value in enumerate(trace):
        item = _require_exact_keys(
            value,
            {
                "control_step",
                "command_phase",
                "requested_action",
                "applied_action",
                "joint_target_rad",
                "applied_action_delta_l2",
                "requested_applied_delta_l2",
                "saturation_substeps_over_threshold",
                "saturation_substeps_total",
            },
            f"{context}.control_step_trace[{index}]",
        )
        if item["control_step"] != index:
            raise V7PilotReplayError(f"{context} trace step is not contiguous")
        over = _require_int(
            item["saturation_substeps_over_threshold"],
            f"{context}.trace[{index}].over",
            minimum=0,
            maximum=10,
        )
        total = _require_int(
            item["saturation_substeps_total"],
            f"{context}.trace[{index}].total",
            minimum=10,
            maximum=10,
        )
        requested = _trace_vector(
            item["requested_action"], f"{context}.trace[{index}].requested_action"
        )
        applied = _trace_vector(
            item["applied_action"], f"{context}.trace[{index}].applied_action"
        )
        _require_string(item["command_phase"], f"{context}.trace[{index}].command_phase")
        _joint_target = _trace_vector(
            item["joint_target_rad"], f"{context}.trace[{index}].joint_target_rad"
        )
        applied_delta_raw = item["applied_action_delta_l2"]
        requested_delta_raw = item["requested_applied_delta_l2"]
        applied_delta = _require_number(
            applied_delta_raw, f"{context}.trace[{index}].applied_action_delta_l2"
        )
        requested_delta = _require_number(
            requested_delta_raw,
            f"{context}.trace[{index}].requested_applied_delta_l2",
        )
        if applied_delta < 0.0 or requested_delta < 0.0:
            raise V7PilotReplayError(f"{context} L2 delta must be non-negative")
        requested_values = [float(item) for item in requested]
        applied_values = [float(item) for item in applied]
        if any(not -1.0 <= item <= 1.0 for item in requested_values):
            raise V7PilotReplayError(f"{context} requested action is not clipped")
        if alpha is None:
            expected = requested_values
        else:
            expected = []
            for prior, requested_value in zip(previous, requested_values, strict=True):
                candidate = prior + float(alpha) * (requested_value - prior)
                delta = max(-float(rate_limit), min(float(rate_limit), candidate - prior))
                expected.append(prior + delta)
        step_delta = max(
            abs(actual - expected_value)
            for actual, expected_value in zip(applied_values, expected, strict=True)
        )
        max_delta = max(max_delta, step_delta)
        if step_delta > 1.0e-12:
            raise V7PilotReplayError(f"{context} action operator identity mismatch")
        applied_delta_expected = math.sqrt(sum(
            (actual - prior) ** 2
            for actual, prior in zip(applied_values, previous, strict=True)
        ))
        requested_delta_expected = math.sqrt(sum(
            (requested_value - actual) ** 2
            for requested_value, actual in zip(
                requested_values, applied_values, strict=True
            )
        ))
        if (
            abs(applied_delta - applied_delta_expected) > 1.0e-12
            or abs(requested_delta - requested_delta_expected) > 1.0e-12
        ):
            raise V7PilotReplayError(f"{context} action delta receipt mismatch")
        previous = applied_values
        over_total += over
        substep_total += total
    if trace:
        recomputed = round(100.0 * over_total / substep_total, 6)
        reported = episode["measurements"]["saturation_duty_pct"]
        reported_value = (
            float(reported["value"]) if reported["state"] == "OBSERVED" else None
        )
        reported_delta = (
            abs(recomputed - reported_value) if reported_value is not None else None
        )
        if reported_delta is not None and reported_delta > 1.0e-12:
            raise V7PilotReplayError(f"{context} 500 Hz saturation duty mismatch")
    else:
        recomputed = None
        reported_value = None
        reported_delta = None
    expected_receipt = {
        "sample_rate_hz": 500.0,
        "control_step_count": len(trace),
        "saturation_substeps_total": substep_total,
        "saturation_substeps_over_threshold": over_total,
        "recomputed_saturation_duty_pct": recomputed,
        "reported_saturation_duty_pct": reported_value,
        "reported_absolute_delta": reported_delta,
        "action_operator_state": "NULL" if not trace else "PASS",
        "action_operator_max_abs_delta": None if not trace else max_delta,
    }
    if episode["trace_receipt"] != expected_receipt:
        raise V7PilotReplayError(f"{context} trace receipt mismatch")


def _validate_raw(
    raw: dict[str, Any],
    protocol: dict[str, Any],
    protocol_sha256: str,
) -> list[dict[str, Any]]:
    _require_exact_keys(
        raw,
        {
            "schema_version",
            "protocol_id",
            "protocol_sha256",
            "source_git_sha_pre",
            "source_git_sha_post",
            "source_dirty_pre",
            "source_dirty_post",
            "run_class",
            "data_partition",
            "evidence_scope",
            "validation_status",
            "expected_arm_count",
            "expected_episodes_per_arm",
            "retained_terminal_states",
            "retained_outcome_states",
            "arms",
            "paper_data_ready",
            "claim_boundary",
        },
        "raw",
    )
    exact = {
        "schema_version": RAW_SCHEMA,
        "protocol_id": PROTOCOL_ID,
        "protocol_sha256": protocol_sha256,
        "source_dirty_pre": False,
        "source_dirty_post": False,
        "run_class": "DEVELOPMENT",
        "data_partition": "DEVELOPMENT",
        "evidence_scope": "SIM_ONLY_MUJOCO",
        "validation_status": "NOT_PHYSICALLY_VALIDATED",
        "expected_arm_count": 3,
        "expected_episodes_per_arm": 30,
        "retained_terminal_states": list(RETAINED_TERMINAL_STATES),
        "retained_outcome_states": list(RETAINED_OUTCOME_STATES),
        "paper_data_ready": False,
        "claim_boundary": CLAIM_BOUNDARY,
    }
    for key, expected in exact.items():
        if raw[key] != expected:
            raise V7PilotReplayError(f"raw {key} mismatch")
    pre_sha = _require_string(
        raw["source_git_sha_pre"], "raw.source_git_sha_pre", pattern=GIT_SHA_PATTERN
    )
    post_sha = _require_string(
        raw["source_git_sha_post"], "raw.source_git_sha_post", pattern=GIT_SHA_PATTERN
    )
    if pre_sha != post_sha:
        raise V7PilotReplayError("raw Git pre/post identity drift")
    arms = raw["arms"]
    if not isinstance(arms, list) or len(arms) != 3:
        raise V7PilotReplayError("raw must contain exactly three arms")
    protocol_arms = {item["arm_id"]: item for item in protocol["arms"]}
    validated: list[dict[str, Any]] = []
    seen_arm_ids: list[str] = []
    for arm_index, arm_value in enumerate(arms):
        context = f"raw.arms[{arm_index}]"
        arm = _require_exact_keys(
            arm_value,
            {
                "arm_id",
                "profile_id",
                "environment_id",
                "training_run_id",
                "training_terminal_state",
                "training_terminal_reason",
                "actual_total_timesteps",
                "evaluation_terminal_state",
                "evaluation_terminal_reason",
                "expected_evaluation_seeds",
                "accessed_evaluation_seeds",
                "artifacts",
                "episodes",
            },
            context,
        )
        arm_id = _require_string(arm["arm_id"], context + ".arm_id")
        seen_arm_ids.append(arm_id)
        if arm_id not in protocol_arms:
            raise V7PilotReplayError(f"unexpected arm: {arm_id}")
        frozen_arm = protocol_arms[arm_id]
        for key in ("profile_id", "environment_id", "training_run_id"):
            if arm[key] != frozen_arm[key]:
                raise V7PilotReplayError(f"{context}.{key} mismatch")
        training_state = _require_string(
            arm["training_terminal_state"],
            context + ".training_terminal_state",
            choices=set(RETAINED_TERMINAL_STATES),
        )
        evaluation_state = _require_string(
            arm["evaluation_terminal_state"],
            context + ".evaluation_terminal_state",
            choices=set(RETAINED_TERMINAL_STATES),
        )
        for state, reason_key in (
            (training_state, "training_terminal_reason"),
            (evaluation_state, "evaluation_terminal_reason"),
        ):
            reason = arm[reason_key]
            if state == "COMPLETED":
                if reason is not None:
                    raise V7PilotReplayError(f"{context}.{reason_key} must be null")
            else:
                _require_string(reason, context + "." + reason_key)
        actual_steps = arm["actual_total_timesteps"]
        if training_state == "COMPLETED":
            if actual_steps != 122880:
                raise V7PilotReplayError(f"{context} realized training budget mismatch")
        elif actual_steps is not None:
            _require_int(
                actual_steps,
                context + ".actual_total_timesteps",
                minimum=0,
                maximum=122880,
            )
        if arm["expected_evaluation_seeds"] != list(EXPECTED_SEEDS):
            raise V7PilotReplayError(f"{context} expected evaluation seeds mismatch")
        accessed = arm["accessed_evaluation_seeds"]
        if not isinstance(accessed, list):
            raise V7PilotReplayError(f"{context} access log must be an array")
        for accessed_seed in accessed:
            _require_int(
                accessed_seed,
                context + ".accessed_evaluation_seeds[]",
                minimum=0,
                maximum=2**63 - 1,
            )
            if 19000 <= accessed_seed <= 19029:
                raise V7PilotReplayError("retired evaluation seed access detected")
            if 20000 <= accessed_seed <= 20029:
                raise V7PilotReplayError("sealed FORMAL/HOLDOUT seed access detected")
            if accessed_seed not in EXPECTED_SEEDS:
                raise V7PilotReplayError("unexpected evaluation seed access detected")
        if len(accessed) != len(set(accessed)):
            raise V7PilotReplayError("duplicate evaluation seed access detected")
        if accessed != list(EXPECTED_SEEDS):
            raise V7PilotReplayError(f"{context} evaluation seed access log mismatch")
        artifacts = _require_exact_keys(
            arm["artifacts"],
            {"training_manifest", "trained_policy", "evaluation"},
            context + ".artifacts",
        )
        _validate_artifact_binding(
            artifacts["training_manifest"], context + ".artifacts.training_manifest"
        )
        policy_binding = _validate_artifact_binding(
            artifacts["trained_policy"], context + ".artifacts.trained_policy"
        )
        _validate_artifact_binding(
            artifacts["evaluation"], context + ".artifacts.evaluation"
        )
        if training_state == "COMPLETED" and policy_binding["state"] != "PRESENT":
            raise V7PilotReplayError(f"{context} completed training lacks policy artifact")
        episodes = arm["episodes"]
        if not isinstance(episodes, list) or len(episodes) != 30:
            raise V7PilotReplayError(f"{context} must contain exactly 30 episodes")
        seen_seeds: list[int] = []
        for episode_index, episode_value in enumerate(episodes):
            episode_context = f"{context}.episodes[{episode_index}]"
            episode = _require_exact_keys(
                episode_value,
                {
                    "evaluation_seed",
                    "terminal_record_state",
                    "outcome_state",
                    "reason",
                    "measurements",
                    "gates",
                    "control_step_trace",
                    "trace_receipt",
                },
                episode_context,
            )
            seed = _require_int(
                episode["evaluation_seed"],
                episode_context + ".evaluation_seed",
                minimum=0,
                maximum=2**63 - 1,
            )
            if 19000 <= seed <= 19029:
                raise V7PilotReplayError("retired evaluation seed record detected")
            if 20000 <= seed <= 20029:
                raise V7PilotReplayError("sealed FORMAL/HOLDOUT seed record detected")
            seen_seeds.append(seed)
            terminal_state = _require_string(
                episode["terminal_record_state"],
                episode_context + ".terminal_record_state",
                choices=set(RETAINED_TERMINAL_STATES),
            )
            outcome_state = _require_string(
                episode["outcome_state"],
                episode_context + ".outcome_state",
                choices=set(RETAINED_OUTCOME_STATES),
            )
            reason = episode["reason"]
            if terminal_state == "COMPLETED" and outcome_state == "OBSERVED":
                if reason is not None:
                    raise V7PilotReplayError(
                        f"{episode_context}.reason must be null for observed completion"
                    )
            else:
                _require_string(reason, episode_context + ".reason")
            measurements = _require_exact_keys(
                episode["measurements"], set(MEASUREMENT_IDS), episode_context + ".measurements"
            )
            for measurement_id in MEASUREMENT_IDS:
                _validate_measurement(
                    measurements[measurement_id],
                    measurement_id,
                    f"{episode_context}.measurements.{measurement_id}",
                )
            measurement_states = {
                measurements[measurement_id]["state"]
                for measurement_id in MEASUREMENT_IDS
            }
            aggregate_state = (
                "NONFINITE"
                if "NONFINITE" in measurement_states
                else "NULL"
                if "NULL" in measurement_states
                else "OBSERVED"
            )
            severity = {"OBSERVED": 0, "NULL": 1, "NONFINITE": 2}
            if severity[outcome_state] < severity[aggregate_state]:
                raise V7PilotReplayError(
                    f"{episode_context} row outcome understates measurement state"
                )
            expected_gates = _gate_results(measurements)
            if episode["gates"] != expected_gates:
                raise V7PilotReplayError(f"{episode_context} gate result mismatch")
            _validate_control_trace(episode, frozen_arm, episode_context)
        if len(seen_seeds) != len(set(seen_seeds)):
            raise V7PilotReplayError(f"{context} contains duplicate evaluation seeds")
        if sorted(seen_seeds) != list(EXPECTED_SEEDS):
            raise V7PilotReplayError(f"{context} episode seed inventory mismatch")
        validated.append(arm)
    if tuple(seen_arm_ids) != ARM_IDS or len(set(seen_arm_ids)) != 3:
        raise V7PilotReplayError("raw arm order/identity mismatch")
    return validated


def _state_counts(values: list[str], states: tuple[str, ...]) -> dict[str, int]:
    counts = Counter(values)
    return {state: counts[state] for state in states}


def _conditional_statistics(episodes: list[dict[str, Any]]) -> dict[str, Any]:
    measurements = [
        episode["measurements"]["saturation_duty_pct"] for episode in episodes
    ]
    observed = [
        float(item["value"]) for item in measurements if item["state"] == "OBSERVED"
    ]
    if len(observed) == len(EXPECTED_SEEDS):
        return {
            "state": "OBSERVED",
            "n_expected": len(EXPECTED_SEEDS),
            "n_observed": len(observed),
            "mean": statistics.fmean(observed),
            "sample_standard_deviation": statistics.stdev(observed),
            "reason": None,
        }
    return {
        "state": "NULL",
        "n_expected": len(EXPECTED_SEEDS),
        "n_observed": len(observed),
        "mean": None,
        "sample_standard_deviation": None,
        "reason": "BLOCKED_REQUIRED_OUTCOME_NOT_OBSERVED_NO_COMPLETE_CASE_DELETION",
    }


def _arm_summary(arm: dict[str, Any]) -> dict[str, Any]:
    episodes = arm["episodes"]
    terminal_counts = _state_counts(
        [item["terminal_record_state"] for item in episodes],
        RETAINED_TERMINAL_STATES,
    )
    outcome_counts = _state_counts(
        [item["outcome_state"] for item in episodes],
        RETAINED_OUTCOME_STATES,
    )
    negative_count = sum(
        any(gate["passed"] is False for gate in item["gates"]) for item in episodes
    )
    blockers: list[str] = []
    if arm["training_terminal_state"] != "COMPLETED":
        blockers.append("TRAINING_TERMINAL_STATE_" + arm["training_terminal_state"])
    if arm["evaluation_terminal_state"] != "COMPLETED":
        blockers.append("EVALUATION_TERMINAL_STATE_" + arm["evaluation_terminal_state"])
    for episode in episodes:
        seed = episode["evaluation_seed"]
        if episode["terminal_record_state"] != "COMPLETED":
            blockers.append(
                f"SEED_{seed}_TERMINAL_{episode['terminal_record_state']}"
            )
        if episode["outcome_state"] != "OBSERVED":
            blockers.append(f"SEED_{seed}_OUTCOME_{episode['outcome_state']}")
        for gate in episode["gates"]:
            if gate["passed"] is False:
                blockers.append(f"SEED_{seed}_GATE_{gate['gate_id']}_FAIL")
            elif gate["passed"] is None:
                blockers.append(f"SEED_{seed}_GATE_{gate['gate_id']}_UNOBSERVED")
    return {
        "arm_id": arm["arm_id"],
        "record_count": len(episodes),
        "training_terminal_state": arm["training_terminal_state"],
        "evaluation_terminal_state": arm["evaluation_terminal_state"],
        "terminal_record_state_counts": terminal_counts,
        "outcome_state_counts": outcome_counts,
        "negative_episode_count": negative_count,
        "saturation_duty_pct": _conditional_statistics(episodes),
        "eligible": arm["arm_id"] in CANDIDATE_ARM_IDS and not blockers,
        "eligibility_blockers": blockers,
    }


def _paired_contrast(reference: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    reference_rows = {item["evaluation_seed"]: item for item in reference["episodes"]}
    candidate_rows = {item["evaluation_seed"]: item for item in candidate["episodes"]}
    differences: list[dict[str, Any]] = []
    observed: list[float] = []
    for seed in EXPECTED_SEEDS:
        reference_value = reference_rows[seed]["measurements"]["saturation_duty_pct"]
        candidate_value = candidate_rows[seed]["measurements"]["saturation_duty_pct"]
        if reference_value["state"] == candidate_value["state"] == "OBSERVED":
            difference = float(candidate_value["value"]) - float(reference_value["value"])
            observed.append(difference)
            differences.append({
                "evaluation_seed": seed,
                "state": "OBSERVED",
                "value": difference,
                "reason": None,
            })
        else:
            state = (
                "NONFINITE"
                if "NONFINITE" in {reference_value["state"], candidate_value["state"]}
                else "NULL"
            )
            differences.append({
                "evaluation_seed": seed,
                "state": state,
                "value": None,
                "reason": (
                    "PAIRED_REQUIRED_OUTCOME_NOT_OBSERVED:"
                    f"reference={reference_value['state']},candidate={candidate_value['state']}"
                ),
            })
    complete = len(observed) == len(EXPECTED_SEEDS)
    return {
        "reference_arm_id": reference["arm_id"],
        "candidate_arm_id": candidate["arm_id"],
        "contrast": "candidate_minus_reference_by_evaluation_seed",
        "state": "OBSERVED" if complete else "NULL",
        "n_expected": len(EXPECTED_SEEDS),
        "n_observed": len(observed),
        "mean_difference": statistics.fmean(observed) if complete else None,
        "sample_standard_deviation": statistics.stdev(observed) if complete else None,
        "reason": (
            None
            if complete
            else "BLOCKED_REQUIRED_PAIR_NOT_OBSERVED_NO_COMPLETE_CASE_DELETION"
        ),
        "differences": differences,
    }


def _semantic_blockers(arms: list[dict[str, Any]]) -> list[str]:
    blockers: list[str] = []
    for arm in arms:
        arm_id = arm["arm_id"]
        if arm["training_terminal_state"] != "COMPLETED":
            blockers.append(f"{arm_id}:TRAINING_{arm['training_terminal_state']}")
        if arm["evaluation_terminal_state"] != "COMPLETED":
            blockers.append(f"{arm_id}:EVALUATION_{arm['evaluation_terminal_state']}")
        for episode in arm["episodes"]:
            seed = episode["evaluation_seed"]
            if episode["terminal_record_state"] != "COMPLETED":
                blockers.append(
                    f"{arm_id}:SEED_{seed}_{episode['terminal_record_state']}"
                )
            if episode["outcome_state"] != "OBSERVED":
                blockers.append(
                    f"{arm_id}:SEED_{seed}_{episode['outcome_state']}"
                )
    return blockers


def build_summary(protocol: dict[str, Any], raw: dict[str, Any]) -> dict[str, Any]:
    """Recompute the deterministic summary after callers validate protocol/raw."""
    arms = raw["arms"]
    arm_summaries = [_arm_summary(arm) for arm in arms]
    by_id = {item["arm_id"]: item for item in arms}
    summary_by_id = {item["arm_id"]: item for item in arm_summaries}
    contrasts = [
        _paired_contrast(by_id[ARM_IDS[0]], by_id[candidate_id])
        for candidate_id in CANDIDATE_ARM_IDS
    ]
    semantic_blockers = _semantic_blockers(arms)
    selected: str | None = None
    if semantic_blockers:
        selection_status = "PILOT_RETAINED_SEMANTIC_BLOCKER"
    else:
        eligible = [
            candidate_id
            for candidate_id in CANDIDATE_ARM_IDS
            if summary_by_id[candidate_id]["eligible"]
        ]
        if not eligible:
            selection_status = "PILOT_COMPLETE_NEGATIVE_RESULT_NO_CANDIDATE"
        elif len(eligible) == 1:
            selected = eligible[0]
            selection_status = "PILOT_COMPLETE_CANDIDATE_SELECTED"
        else:
            means = {
                candidate_id: summary_by_id[candidate_id]["saturation_duty_pct"]["mean"]
                for candidate_id in eligible
            }
            if means[eligible[0]] == means[eligible[1]]:
                selection_status = "PILOT_COMPLETE_NO_SELECTION_EXACT_TIE"
            else:
                selected = min(eligible, key=lambda arm_id: means[arm_id])
                selection_status = "PILOT_COMPLETE_CANDIDATE_SELECTED"
    return {
        "schema_version": SUMMARY_SCHEMA,
        "protocol_id": PROTOCOL_ID,
        "protocol_sha256": raw["protocol_sha256"],
        "source_git_sha_pre": raw["source_git_sha_pre"],
        "source_git_sha_post": raw["source_git_sha_post"],
        "source_dirty_pre": False,
        "source_dirty_post": False,
        "evidence_scope": "SIM_ONLY_MUJOCO",
        "validation_status": "NOT_PHYSICALLY_VALIDATED",
        "evidence_complete": True,
        "pilot_planning_ready": not semantic_blockers,
        "selection_status": selection_status,
        "selected_candidate_arm_id": selected,
        "arm_summaries": arm_summaries,
        "paired_contrasts": contrasts,
        "semantic_blockers": semantic_blockers,
        "confidence_interval": "NOT_COMPUTED_DEVELOPMENT_PILOT",
        "method_level_power_ready": False,
        "formal_sample_size_decision": (
            "BLOCKED_INDEPENDENT_TRAINING_SEED_VARIANCE_NOT_ESTIMATED"
        ),
        "paper_data_ready": False,
        "claim_boundary": CLAIM_BOUNDARY,
    }


def replay_pilot(
    protocol: dict[str, Any],
    raw: dict[str, Any],
    primary_summary: dict[str, Any],
    *,
    protocol_sha256: str,
    raw_sha256: str,
    summary_sha256: str,
) -> dict[str, Any]:
    """Validate and independently reconstruct the primary pilot summary."""
    _validate_protocol(protocol, protocol_sha256)
    _validate_raw(raw, protocol, protocol_sha256)
    expected = build_summary(protocol, raw)
    if primary_summary != expected:
        raise V7PilotReplayError("primary summary differs from raw-episode replay")
    return {
        "schema_version": REPLAY_SCHEMA,
        "status": "PASS",
        "exact_identity": True,
        "checks": {
            "frozen_protocol_exact": True,
            "exact_three_arm_seed_inventory": True,
            "explicit_gate_reconstruction": True,
            "conditional_statistics_exact": True,
            "paired_differences_exact": True,
            "primary_summary_exact": True,
        },
        "protocol_sha256": protocol_sha256,
        "raw_episodes_sha256": raw_sha256,
        "pilot_summary_sha256": summary_sha256,
        "paper_data_ready": False,
        "claim_boundary": CLAIM_BOUNDARY,
    }


def _run(paths: list[Path]) -> dict[str, Any]:
    protocol_path, raw_path, summary_path = paths
    protocol = _load_json(protocol_path)
    raw = _load_json(raw_path)
    summary = _load_json(summary_path)
    return replay_pilot(
        protocol,
        raw,
        summary,
        protocol_sha256=_sha256_file(protocol_path),
        raw_sha256=_sha256_file(raw_path),
        summary_sha256=_sha256_file(summary_path),
    )


def main() -> None:
    if len(sys.argv) != 4:
        payload = {
            "schema_version": REPLAY_ERROR_SCHEMA,
            "status": "ERROR",
            "exact_identity": False,
            "error": "expected protocol, raw episodes, and primary summary paths",
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
            "paper_data_ready": False,
            "claim_boundary": CLAIM_BOUNDARY,
        }
        print(json.dumps(receipt, ensure_ascii=False, indent=2, allow_nan=False))
        raise SystemExit(2) from exc
    print(json.dumps(receipt, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()

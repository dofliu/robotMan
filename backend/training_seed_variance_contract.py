"""Method-level variance evidence contract for SEEDVAR-V7-TRAINING-REPLICATE-DEV-V1.

The v7 pilot trained one seed per arm, so everything it measured is conditional
on one checkpoint.  This contract answers the other question: across independent
training replicates, how much does the paired action-interface contrast move?

Three structural rules do the real work here, all frozen in
``docs/TRAINING_SEED_VARIANCE_SPEC.md`` before this file existed.

The analysis unit is the training replicate.  Every method-level statistic has
denominator ``replicate_count``.  The 150 episode-level pairs are *not* 150
independent units: using them would pass evaluation-seed variation off as
training-seed variation and shrink the standard error by roughly ``sqrt(30)``.
So the forbidden denominators are named in the protocol and checked, rather
than left to whoever writes the next analysis script.

Exposure censoring composes upward instead of collapsing.  A cell with a
censored episode yields an interval; the paired difference of two intervals is
an interval; the method-level mean of intervals is an interval.  A sample SD is
not defined on intervals, so a partially identified replicate difference blocks
``between_replicate_sd`` outright rather than being replaced by its midpoint.

Method failure is not censoring.  A cell containing a method failure has no
mean at all, because producing one would require deleting the failure.

This module consumes audit output rather than re-deriving exposure from raw
traces: ``AUDIT-V7-EXPOSURE-CENSORING-V1`` is the frozen upstream contract and
each cell is bound to the audit summary that produced it.  It does not take
those numbers on trust, though — every inherited bound is re-checked for
internal consistency against its own declared comparability state.
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
import subprocess
import sys
from typing import Any

from environment_lock import (
    FULL_LOCK,
    MEASURED_LOCK_CLASS,
    THREADING_PINNED,
    EnvironmentLockError,
    validate_lock_record,
)


PROTOCOL_SCHEMA = "TRAINING_SEED_VARIANCE_PROTOCOL_V1"
PROTOCOL_ID = "SEEDVAR-V7-TRAINING-REPLICATE-DEV-V1"
PROTOCOL_SHA256 = (
    "sha256:9ab17c74ddb021f9b69b1df843f9fa49ea45ecf790837204270d8bc01046b359"
)
RAW_SCHEMA = "TRAINING_SEED_VARIANCE_RAW_V1"
SUMMARY_SCHEMA = "TRAINING_SEED_VARIANCE_SUMMARY_V1"
SOURCE_INDEX_SCHEMA = "TRAINING_SEED_VARIANCE_SOURCE_INDEX_V1"
RECEIPT_SCHEMA = "TRAINING_SEED_VARIANCE_RECEIPT_V1"
REPLAY_SCHEMA = "TRAINING_SEED_VARIANCE_REPLAY_RECEIPT_V1"
VALIDATION_SCHEMA = "TRAINING_SEED_VARIANCE_VALIDATION_V1"
ERROR_SCHEMA = "TRAINING_SEED_VARIANCE_ERROR_RECEIPT_V1"

AUDIT_PROTOCOL_SHA256 = (
    "sha256:b15505b73f3745141c2dfa31cf57564b0863242949f5d1ad4d351dfb96dec6ce"
)
# The two implementations whose frozen derivations produce the inherited
# episode classification. Pinning them is what makes "the audit rules were
# applied" checkable rather than asserted: a drifted audit implementation would
# otherwise silently reclassify exposure under an unchanged protocol digest.
AUDIT_CONTRACT_SOURCE = Path(__file__).resolve().parent / "v7_exposure_audit_contract.py"
AUDIT_CONTRACT_SOURCE_SHA256 = (
    "sha256:365d7669f0f5a388d34afe8f4960e39d533c43b35c733a4f5852546d7957c376"
)
PILOT_CONTRACT_SOURCE = Path(__file__).resolve().parent / "v7_pilot_contract.py"
PILOT_CONTRACT_SOURCE_SHA256 = (
    "sha256:ee920fba5b75e2570831381dbb460d25c4d0a96a3c2fac9631b29591434ccbc5"
)

DEVELOPMENT_BUNDLE_CLASS = "SEED_VARIANCE_DEVELOPMENT_BUNDLE"
SYNTHETIC_BUNDLE_CLASS = "SYNTHETIC_REGRESSION_BUNDLE"
BUNDLE_CLASSES = (DEVELOPMENT_BUNDLE_CLASS, SYNTHETIC_BUNDLE_CLASS)

ANALYSIS_UNIT = "TRAINING_REPLICATE"
PRIMARY_MEASUREMENT_ID = "saturation_duty_pct"

REFERENCE_ARM_ID = "V7A_REWARD_ONLY"
CANDIDATE_ARM_IDS = ("V7B_REDUCED_JOINT_ENVELOPE", "V7C_FILTERED_ACTION")
ARM_IDS = (REFERENCE_ARM_ID,) + CANDIDATE_ARM_IDS

COMPARABLE = "COMPARABLE"
EXPOSURE_CENSORED = "EXPOSURE_CENSORED"
METHOD_FAILURE = "METHOD_FAILURE_NOT_CENSORING"
COMPARABILITY_STATES = (COMPARABLE, EXPOSURE_CENSORED, METHOD_FAILURE)

EXPOSURE_CLASSES = ("FULL_EXPOSURE", "EARLY_TERMINATED", "NO_EXPOSURE")
RETAINED_TERMINAL_STATES = ("COMPLETED", "FAILED", "CANCELLED")
RETAINED_OUTCOME_STATES = ("OBSERVED", "NULL", "NONFINITE")

CELL_POINT_IDENTIFIED = "POINT_IDENTIFIED"
CELL_PARTIALLY_IDENTIFIED = "PARTIALLY_IDENTIFIED"
CELL_BLOCKED_METHOD_FAILURE = "BLOCKED_METHOD_FAILURE"

SIGN_NEGATIVE = "NEGATIVE"
SIGN_POSITIVE = "POSITIVE"
SIGN_UNIDENTIFIED = "UNIDENTIFIED"
SIGN_NULL = "NULL"

REASON_METHOD_FAILURE_CELL = "CELL_CONTAINS_METHOD_FAILURE_NO_MEAN_DEFINED"
REASON_PARTIAL_SD = "BLOCKED_PARTIALLY_IDENTIFIED_REPLICATE_DIFFERENCES"
REASON_BLOCKED_PAIR = "BLOCKED_METHOD_FAILURE_IN_PAIRED_CELL"
REASON_WITHIN_SD_CENSORED = "BLOCKED_CENSORED_EPISODES_NO_POINT_VALUES"

STATUS_CLEAN = "SEED_VARIANCE_EVIDENCE_COMPLETE"
STATUS_BLOCKED = "SEED_VARIANCE_EVIDENCE_COMPLETE_WITH_RETAINED_BLOCKERS"

PERCENT_DECIMALS = 6
RATIO_DECIMALS = 9
GIT_SHA_PATTERN = r"^[0-9a-f]{40}$"

CLAIM_BOUNDARY = (
    "SIM_ONLY_MUJOCO / NOT_PHYSICALLY_VALIDATED / DEVELOPMENT_ONLY. This "
    "contract may support only a statement about the conditional magnitude of "
    "replicate-level variation in the frozen v7 action-interface contrast, "
    "under a fixed v5 warm start and DEVELOPMENT evaluation seeds. It selects "
    "no candidate and supports no claim of controller superiority, sample-size "
    "adequacy, paper readiness, physical torque or thermal margins, safety, or "
    "sim-to-real performance."
)

DEFAULT_PROTOCOL = Path(__file__).resolve().parent / "rl" / "training_seed_variance_protocol.json"
DEFAULT_PILOT_PROTOCOL = (
    Path(__file__).resolve().parent / "rl" / "v7_action_interface_pilot_protocol.json"
)

EPISODE_FIELDS = (
    "comparability_reason",
    "comparability_state",
    "evaluation_seed",
    "exposure_class",
    "full_horizon_duty_bound_pct",
    "outcome_state",
    "terminal_record_state",
)
BOUND_FIELDS = ("lower_pct", "reason", "state", "upper_pct", "width_pct")
CELL_FIELDS = (
    "arm_id",
    "audit_contract_source_sha256",
    "audit_protocol_sha256",
    "episodes",
    "evaluation_environment_lock_verified",
    "evaluation_output_sha256",
    "pilot_contract_source_sha256",
    "realized_timesteps",
    "training_environment_lock_verified",
    "training_terminal_state",
)
# Provenance for the inherited classification. The audit protocol says which
# rules applied, the two source digests say which implementations applied them,
# and the evaluation digest says which raw output they were applied to. That
# last one is the binding that matters: it reaches the actual measured episodes
# rather than a derived summary of them.
CELL_PROVENANCE_FIELDS = (
    "audit_contract_source_sha256",
    "evaluation_output_sha256",
    "pilot_contract_source_sha256",
)
# The spec requires the lock verified before *every* training and evaluation
# run. One flag per cell would conflate two separate runs, so each cell carries
# both and both must be true.
CELL_LOCK_FIELDS = (
    "training_environment_lock_verified",
    "evaluation_environment_lock_verified",
)
REPLICATE_FIELDS = ("arms", "environment_seed_block", "replicate_index", "training_seed")
RAW_FIELDS = (
    "bundle_class",
    "environment_lock_sha256",
    "protocol_id",
    "replicates",
    "schema_version",
    "source_dirty_post",
    "source_dirty_pre",
    "source_git_sha_post",
    "source_git_sha_pre",
)


class SeedVarianceError(RuntimeError):
    """Structural failure in a seed-variance bundle or its derivation."""


# --------------------------------------------------------------------------- #
# strict JSON, digests and exact reductions
# --------------------------------------------------------------------------- #


def _reject_nonfinite(constant: str) -> Any:
    raise SeedVarianceError(f"payload contains a non-finite JSON constant: {constant}")


def _load_json_bytes(payload: bytes, label: str) -> dict[str, Any]:
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SeedVarianceError(f"{label} is not UTF-8") from exc
    duplicates: list[str] = []

    def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        keys = [key for key, _ in pairs]
        if len(set(keys)) != len(keys):
            duplicates.append(label)
        return dict(pairs)

    try:
        value = json.loads(text, object_pairs_hook=_pairs, parse_constant=_reject_nonfinite)
    except json.JSONDecodeError as exc:
        raise SeedVarianceError(f"{label} is not valid JSON") from exc
    if duplicates:
        raise SeedVarianceError(f"{label} has duplicate object keys")
    return _require_object(value, label)


def _load_json_file(path: Path) -> dict[str, Any]:
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise SeedVarianceError(f"cannot read JSON artifact: {path.name}") from exc
    return _load_json_bytes(payload, path.name)


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
        raise SeedVarianceError("derived payload is not strict finite JSON") from exc


def _sha256_bytes(payload: bytes) -> str:
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def ordered_mean(values: list[float]) -> float:
    """Left-to-right float addition in the caller's order, then one division.

    The reduction order is part of the contract, not an implementation detail:
    the independent stdlib-only replay must reach bit-exact identity, and float
    addition is not associative.  Callers pass values in ascending
    ``replicate_index`` or ascending ``evaluation_seed`` order.
    """
    if not values:
        raise SeedVarianceError("mean requires at least one value")
    total = 0.0
    for value in values:
        total += value
    return total / len(values)


def ordered_sample_sd(values: list[float]) -> float:
    """Two-pass sample SD with ``df = n - 1``, same fixed summation order."""
    count = len(values)
    if count < 2:
        raise SeedVarianceError("sample standard deviation requires at least two values")
    mean = ordered_mean(values)
    accumulator = 0.0
    for value in values:
        delta = value - mean
        accumulator += delta * delta
    return math.sqrt(accumulator / (count - 1))


def _round_percent(value: float) -> float:
    return round(value, PERCENT_DECIMALS)


def _round_ratio(value: float) -> float:
    return round(value, RATIO_DECIMALS)


# --------------------------------------------------------------------------- #
# typed requirement helpers
# --------------------------------------------------------------------------- #


def _require_object(value: Any, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SeedVarianceError(f"{context} must be an object")
    return value


def _require_list(value: Any, context: str) -> list[Any]:
    if not isinstance(value, list):
        raise SeedVarianceError(f"{context} must be an array")
    return value


def _require_exact_keys(
    value: dict[str, Any], expected: tuple[str, ...], context: str
) -> None:
    present = set(value)
    allowed = set(expected)
    missing = sorted(allowed - present)
    unexpected = sorted(present - allowed)
    if missing:
        raise SeedVarianceError(f"{context} is missing fields: {missing}")
    if unexpected:
        raise SeedVarianceError(f"{context} has undeclared fields: {unexpected}")


def _require_string(value: Any, context: str, *, allowed: tuple[str, ...] | None = None) -> str:
    if not isinstance(value, str) or not value:
        raise SeedVarianceError(f"{context} must be a non-empty string")
    if allowed is not None and value not in allowed:
        raise SeedVarianceError(f"{context} must be one of {list(allowed)}")
    return value


def _require_integer(
    value: Any, context: str, *, minimum: int | None = None, maximum: int | None = None
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise SeedVarianceError(f"{context} must be an integer")
    if minimum is not None and value < minimum:
        raise SeedVarianceError(f"{context} must be at least {minimum}")
    if maximum is not None and value > maximum:
        raise SeedVarianceError(f"{context} must be at most {maximum}")
    return value


def _require_percent(value: Any, context: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SeedVarianceError(f"{context} must be a number")
    number = float(value)
    if not math.isfinite(number):
        raise SeedVarianceError(f"{context} must be finite")
    if not 0.0 <= number <= 100.0:
        raise SeedVarianceError(f"{context} must lie within 0..100 percent")
    return number


def _require_true(value: Any, context: str) -> None:
    if value is not True:
        raise SeedVarianceError(f"{context} must be true")


def _require_false(value: Any, context: str) -> None:
    if value is not False:
        raise SeedVarianceError(f"{context} must be false")


# --------------------------------------------------------------------------- #
# frozen protocol
# --------------------------------------------------------------------------- #


def load_protocol(path: Path = DEFAULT_PROTOCOL) -> dict[str, Any]:
    """Load the frozen protocol and bind it to its pinned digest.

    The digest gate is what makes every downstream number attributable: a
    protocol edited after the freeze would silently redefine the seeds, the
    denominators, or the censoring rules that this contract enforces.
    """
    resolved = Path(path)
    digest = sha256_file(resolved)
    if digest != PROTOCOL_SHA256:
        raise SeedVarianceError(
            f"protocol digest drift: expected {PROTOCOL_SHA256}, read {digest}"
        )
    protocol = _load_json_file(resolved)
    validate_protocol(protocol)
    return protocol


def validate_protocol(protocol: dict[str, Any]) -> dict[str, Any]:
    """Semantic invariants that any protocol version must satisfy.

    These are separate from the digest gate on purpose.  The digest catches an
    edit to the frozen file; this catches a *re-freeze* that updates the pin
    and the file together while breaking an invariant the analysis depends on.
    """
    if protocol.get("schema_version") != PROTOCOL_SCHEMA:
        raise SeedVarianceError("unexpected protocol schema_version")
    if protocol.get("protocol_id") != PROTOCOL_ID:
        raise SeedVarianceError("unexpected protocol_id")
    if protocol.get("paper_data_ready") is not False:
        raise SeedVarianceError("protocol must retain paper_data_ready=false")
    estimand = _require_object(protocol.get("estimand"), "protocol.estimand")
    if estimand.get("analysis_unit") != ANALYSIS_UNIT:
        raise SeedVarianceError("protocol.estimand.analysis_unit must be TRAINING_REPLICATE")
    selection = _require_object(protocol.get("selection"), "protocol.selection")
    if selection.get("selected_candidate_arm_id") is not None:
        raise SeedVarianceError("protocol must not preselect a candidate arm")
    _require_false(selection.get("selection_permitted"), "protocol.selection.selection_permitted")
    prerequisites = _require_object(
        protocol.get("prerequisite_contracts"), "protocol.prerequisite_contracts"
    )
    if prerequisites.get("audit_protocol_sha256") != AUDIT_PROTOCOL_SHA256:
        raise SeedVarianceError("protocol pins an unexpected audit protocol digest")
    amendment = protocol.get("amendment")
    if amendment is not None:
        # An amendment may only narrow, and only before any execution. A
        # post-hoc or widening amendment would let the design be rewritten
        # around whatever the data turned out to be.
        entry = _require_object(amendment, "protocol.amendment")
        if entry.get("narrowing_only") is not True:
            raise SeedVarianceError("protocol amendment must be narrowing only")
        if entry.get("applied_before_any_execution") is not True:
            raise SeedVarianceError(
                "protocol amendment must be applied before any execution"
            )
        _require_string(entry.get("defect"), "protocol.amendment.defect")
        _require_string(entry.get("resolution"), "protocol.amendment.resolution")
    return _protocol_design(protocol)


def verify_inherited_implementations() -> dict[str, Any]:
    """Re-hash the reused implementations against their pins.

    The cell fields record which implementation was claimed; this checks the
    claim against the file actually importable here. Without it a pin is only
    a copied string.
    """
    findings = []
    for path, expected in (
        (AUDIT_CONTRACT_SOURCE, AUDIT_CONTRACT_SOURCE_SHA256),
        (PILOT_CONTRACT_SOURCE, PILOT_CONTRACT_SOURCE_SHA256),
    ):
        actual = sha256_file(path)
        if actual != expected:
            findings.append(
                f"{path.name}: pinned {expected}, read {actual}"
            )
    if findings:
        raise SeedVarianceError(
            "inherited implementation drift: " + "; ".join(findings)
        )
    return {
        "audit_contract_source_sha256": AUDIT_CONTRACT_SOURCE_SHA256,
        "pilot_contract_source_sha256": PILOT_CONTRACT_SOURCE_SHA256,
        "inherited_implementations_verified": True,
    }


def verify_pilot_inheritance(
    protocol: dict[str, Any], pilot_protocol_path: Path = DEFAULT_PILOT_PROTOCOL
) -> dict[str, Any]:
    """Check that the inherited v7 design really is the pilot's, field by field.

    SV-01 says the arms and the warm start match the pilot exactly. Pinning the
    pilot's digest in this protocol only proves which file was intended; it does
    not stop this protocol from copying a wrong number out of it. So the fields
    that make the two protocols comparable are compared against the pilot file
    itself.
    """
    path = Path(pilot_protocol_path)
    prerequisites = _require_object(
        protocol.get("prerequisite_contracts"), "protocol.prerequisite_contracts"
    )
    digest = sha256_file(path)
    if digest != prerequisites.get("pilot_protocol_sha256"):
        raise SeedVarianceError(
            "pilot protocol digest drift: protocol pins "
            f"{prerequisites.get('pilot_protocol_sha256')!r}, read {digest}"
        )
    pilot = _load_json_file(path)
    if pilot.get("protocol_id") != prerequisites.get("pilot_protocol_id"):
        raise SeedVarianceError("pilot protocol_id does not match the pinned identity")

    baseline = _require_object(protocol.get("source_baseline"), "protocol.source_baseline")
    pilot_baseline = _require_object(pilot.get("source_baseline"), "pilot.source_baseline")
    for field in (
        "warm_start_policy_id",
        "warm_start_path",
        "warm_start_bytes",
        "warm_start_sha256",
    ):
        if baseline.get(field) != pilot_baseline.get(field):
            raise SeedVarianceError(
                f"source_baseline.{field} does not match the pilot: "
                f"{baseline.get(field)!r} != {pilot_baseline.get(field)!r}"
            )

    pilot_arms = [item.get("arm_id") for item in _require_list(pilot.get("arms"), "pilot.arms")]
    arms = [item.get("arm_id") for item in _require_list(protocol.get("arms"), "protocol.arms")]
    if arms != pilot_arms:
        raise SeedVarianceError(
            f"arm inventory does not match the pilot: {arms} != {pilot_arms}"
        )
    if arms != list(ARM_IDS):
        raise SeedVarianceError(f"arm inventory does not match the frozen arm ids: {arms}")

    training = _require_object(protocol.get("training_design"), "protocol.training_design")
    pilot_training = _require_object(pilot.get("training_design"), "pilot.training_design")
    for field in (
        "parallel_envs",
        "requested_timesteps",
        "expected_realized_timesteps",
        "ppo_rollout_steps_per_env",
        "ppo_batch_size",
        "ppo_epochs",
        "device",
    ):
        if training.get(field) != pilot_training.get(field):
            raise SeedVarianceError(
                f"training_design.{field} does not match the pilot: "
                f"{training.get(field)!r} != {pilot_training.get(field)!r}"
            )

    evaluation = _require_object(protocol.get("evaluation_design"), "protocol.evaluation_design")
    pilot_evaluation = _require_object(pilot.get("evaluation_design"), "pilot.evaluation_design")
    if evaluation.get("episodes_per_arm_replicate") != pilot_evaluation.get("episodes_per_arm"):
        raise SeedVarianceError("episodes per arm do not match the pilot")
    for field in ("evaluation_seed_start", "evaluation_seed_end", "deterministic_policy"):
        if evaluation.get(field) != pilot_evaluation.get(field):
            raise SeedVarianceError(f"evaluation_design.{field} does not match the pilot")
    for field in ("retired_seed_range", "sealed_formal_seed_range"):
        if evaluation.get(field) != pilot_evaluation.get(field):
            raise SeedVarianceError(f"evaluation_design.{field} does not match the pilot")

    # The pilot ran one replicate per arm. If that ever read as more than one,
    # this protocol would not be measuring anything the pilot could not.
    if pilot_training.get("independent_training_replicates_per_arm") != 1:
        raise SeedVarianceError(
            "the pilot no longer declares a single training replicate per arm"
        )
    return {
        "pilot_protocol_id": pilot.get("protocol_id"),
        "pilot_protocol_sha256": digest,
        "pilot_independent_training_replicates_per_arm": 1,
        "pilot_inheritance_verified": True,
    }


def _protocol_design(protocol: dict[str, Any]) -> dict[str, Any]:
    """Derive and self-check the frozen design numbers the analysis depends on."""
    training = _require_object(protocol.get("training_design"), "protocol.training_design")
    evaluation = _require_object(protocol.get("evaluation_design"), "protocol.evaluation_design")
    estimand = _require_object(protocol.get("estimand"), "protocol.estimand")

    replicate_count = _require_integer(
        training.get("replicate_count"), "protocol.training_design.replicate_count", minimum=2
    )
    seeds = _require_list(training.get("training_seeds"), "protocol.training_design.training_seeds")
    if len(seeds) != replicate_count:
        raise SeedVarianceError("training_seeds length must equal replicate_count")
    for index, seed in enumerate(seeds):
        _require_integer(seed, f"protocol.training_design.training_seeds[{index}]", minimum=0)
    if sorted(seeds) != list(seeds) or len(set(seeds)) != len(seeds):
        raise SeedVarianceError("training_seeds must be strictly ascending and unique")

    parallel_envs = _require_integer(
        training.get("parallel_envs"), "protocol.training_design.parallel_envs", minimum=1
    )
    blocks = _require_list(
        training.get("environment_seed_blocks"), "protocol.training_design.environment_seed_blocks"
    )
    if len(blocks) != replicate_count:
        raise SeedVarianceError("environment_seed_blocks length must equal replicate_count")
    pilot_block = _require_list(
        training.get("pilot_environment_seed_block"),
        "protocol.training_design.pilot_environment_seed_block",
    )
    if len(pilot_block) != 2:
        raise SeedVarianceError("pilot_environment_seed_block must be a pair")
    occupied: set[int] = set(range(int(pilot_block[0]), int(pilot_block[1]) + 1))
    expected_blocks: list[list[int]] = []
    for index, block in enumerate(blocks):
        context = f"protocol.training_design.environment_seed_blocks[{index}]"
        pair = _require_list(block, context)
        if len(pair) != 2:
            raise SeedVarianceError(f"{context} must be a pair")
        start = _require_integer(pair[0], f"{context}[0]", minimum=0)
        end = _require_integer(pair[1], f"{context}[1]", minimum=0)
        if start != seeds[index]:
            raise SeedVarianceError(f"{context} must start at its training seed")
        if end - start + 1 != parallel_envs:
            raise SeedVarianceError(f"{context} must span exactly parallel_envs seeds")
        span = set(range(start, end + 1))
        if span & occupied:
            raise SeedVarianceError(
                f"{context} overlaps an already occupied environment seed range"
            )
        occupied |= span
        expected_blocks.append([start, end])

    seed_start = _require_integer(
        evaluation.get("evaluation_seed_start"), "protocol.evaluation_design.evaluation_seed_start"
    )
    seed_end = _require_integer(
        evaluation.get("evaluation_seed_end"), "protocol.evaluation_design.evaluation_seed_end"
    )
    episodes = _require_integer(
        evaluation.get("episodes_per_arm_replicate"),
        "protocol.evaluation_design.episodes_per_arm_replicate",
        minimum=2,
    )
    if seed_end - seed_start + 1 != episodes:
        raise SeedVarianceError("evaluation seed range must match episodes_per_arm_replicate")
    expected_records = replicate_count * episodes * len(ARM_IDS)
    if evaluation.get("expected_terminal_records") != expected_records:
        raise SeedVarianceError("expected_terminal_records disagrees with the frozen design")
    pairs_per_candidate = replicate_count * episodes
    if evaluation.get("pairs_per_candidate") != pairs_per_candidate:
        raise SeedVarianceError("pairs_per_candidate disagrees with the frozen design")

    retired = _require_list(
        evaluation.get("retired_seed_range"), "protocol.evaluation_design.retired_seed_range"
    )
    sealed = _require_list(
        evaluation.get("sealed_formal_seed_range"),
        "protocol.evaluation_design.sealed_formal_seed_range",
    )
    evaluation_seeds = tuple(range(seed_start, seed_end + 1))
    forbidden = set(range(int(retired[0]), int(retired[1]) + 1)) | set(
        range(int(sealed[0]), int(sealed[1]) + 1)
    )
    if forbidden & set(evaluation_seeds):
        raise SeedVarianceError("evaluation seeds intersect a retired or sealed range")

    # The point of naming forbidden denominators in the protocol is that the
    # check runs here, not in whichever script someone writes next.
    if estimand.get("method_level_denominator") != replicate_count:
        raise SeedVarianceError("estimand.method_level_denominator must equal replicate_count")
    forbidden_denominators = _require_list(
        estimand.get("forbidden_denominators"), "protocol.estimand.forbidden_denominators"
    )
    if pairs_per_candidate not in forbidden_denominators:
        raise SeedVarianceError(
            "the episode-level pair count must be listed as a forbidden denominator"
        )
    if expected_records not in forbidden_denominators:
        raise SeedVarianceError(
            "the terminal record count must be listed as a forbidden denominator"
        )
    if replicate_count in forbidden_denominators:
        raise SeedVarianceError("replicate_count must not be listed as a forbidden denominator")

    return {
        "replicate_count": replicate_count,
        "training_seeds": [int(seed) for seed in seeds],
        "environment_seed_blocks": expected_blocks,
        "parallel_envs": parallel_envs,
        "evaluation_seeds": evaluation_seeds,
        "episodes_per_arm_replicate": episodes,
        "expected_terminal_records": expected_records,
        "pairs_per_candidate": pairs_per_candidate,
        "forbidden_denominators": sorted(int(value) for value in forbidden_denominators),
        "forbidden_evaluation_seeds": forbidden,
        "expected_realized_timesteps": _require_integer(
            training.get("expected_realized_timesteps"),
            "protocol.training_design.expected_realized_timesteps",
            minimum=1,
        ),
    }


# --------------------------------------------------------------------------- #
# environment lock gate
# --------------------------------------------------------------------------- #


def check_environment_lock(
    protocol: dict[str, Any], record: Any
) -> dict[str, Any]:
    """Require a complete, measured, thread-pinned lock, or fail closed.

    Thread pinning is not housekeeping here.  Thread count changes
    floating-point reduction order, so leaving it unpinned mixes
    thread-induced variation into the very quantity this protocol isolates.
    """
    requirement = _require_object(
        protocol.get("environment_lock_requirement"), "protocol.environment_lock_requirement"
    )
    try:
        validation = validate_lock_record(record)
    except EnvironmentLockError as exc:
        raise SeedVarianceError(f"environment lock record is invalid: {exc}") from exc
    required_class = requirement.get("required_lock_class", MEASURED_LOCK_CLASS)
    required_completeness = requirement.get("required_lock_completeness", FULL_LOCK)
    required_threading = requirement.get("required_threading_determinism", THREADING_PINNED)
    if validation["lock_class"] != required_class:
        raise SeedVarianceError(
            f"environment lock class {validation['lock_class']!r} does not meet the "
            f"required {required_class!r}"
        )
    if validation["lock_completeness"] != required_completeness:
        raise SeedVarianceError(
            f"environment lock completeness {validation['lock_completeness']!r} does not "
            f"meet the required {required_completeness!r}"
        )
    if validation["threading_determinism"] != required_threading:
        raise SeedVarianceError(
            f"environment lock threading {validation['threading_determinism']!r} does not "
            f"meet the required {required_threading!r}"
        )
    return {
        "environment_lock_contract_id": validation["contract_id"],
        "environment_lock_class": validation["lock_class"],
        "environment_lock_completeness": validation["lock_completeness"],
        "environment_lock_threading": validation["threading_determinism"],
        "environment_locked_sha256": validation["locked_sha256"],
        "environment_lock_satisfied": True,
    }


# --------------------------------------------------------------------------- #
# raw bundle validation
# --------------------------------------------------------------------------- #


def _validate_bound(bound: Any, comparability_state: str, context: str) -> dict[str, Any]:
    """Re-check an inherited audit bound against its own declared state.

    The audit is the upstream authority on exposure, but its output arrives
    here as data.  A censored episode carrying a degenerate bound, or a
    comparable episode carrying a wide one, would silently change every
    downstream interval, so the two are cross-checked rather than assumed
    consistent.
    """
    payload = _require_object(bound, context)
    _require_exact_keys(payload, BOUND_FIELDS, context)
    state = _require_string(payload["state"], f"{context}.state", allowed=("OBSERVED", "NULL"))
    if state == "NULL":
        if comparability_state != METHOD_FAILURE:
            raise SeedVarianceError(
                f"{context} is NULL but the episode is {comparability_state}, not a method failure"
            )
        for field in ("lower_pct", "upper_pct", "width_pct"):
            if payload[field] is not None:
                raise SeedVarianceError(f"{context}.{field} must be null for a NULL bound")
        _require_string(payload["reason"], f"{context}.reason")
        return payload
    if comparability_state == METHOD_FAILURE:
        raise SeedVarianceError(
            f"{context} carries a measured bound but the episode is a method failure"
        )
    lower = _require_percent(payload["lower_pct"], f"{context}.lower_pct")
    upper = _require_percent(payload["upper_pct"], f"{context}.upper_pct")
    width = _require_percent(payload["width_pct"], f"{context}.width_pct")
    if upper < lower:
        raise SeedVarianceError(f"{context} identification bound is inverted")
    if _round_percent(upper - lower) != _round_percent(width):
        raise SeedVarianceError(f"{context}.width_pct does not match the bound")
    if comparability_state == COMPARABLE and lower != upper:
        raise SeedVarianceError(
            f"{context} must be degenerate for a comparable episode"
        )
    if comparability_state == EXPOSURE_CENSORED and lower == upper:
        raise SeedVarianceError(
            f"{context} must be a non-degenerate interval for a censored episode"
        )
    if payload["reason"] is not None:
        raise SeedVarianceError(f"{context}.reason must be null for a measured bound")
    return payload


def _validate_episode(episode: Any, seed: int, context: str) -> dict[str, Any]:
    payload = _require_object(episode, context)
    _require_exact_keys(payload, EPISODE_FIELDS, context)
    if payload["evaluation_seed"] != seed:
        raise SeedVarianceError(
            f"{context}.evaluation_seed must be {seed}, read {payload['evaluation_seed']!r}"
        )
    _require_string(
        payload["terminal_record_state"],
        f"{context}.terminal_record_state",
        allowed=RETAINED_TERMINAL_STATES,
    )
    _require_string(
        payload["outcome_state"], f"{context}.outcome_state", allowed=RETAINED_OUTCOME_STATES
    )
    _require_string(
        payload["exposure_class"], f"{context}.exposure_class", allowed=EXPOSURE_CLASSES
    )
    state = _require_string(
        payload["comparability_state"],
        f"{context}.comparability_state",
        allowed=COMPARABILITY_STATES,
    )
    _require_string(payload["comparability_reason"], f"{context}.comparability_reason")
    if state == COMPARABLE and payload["exposure_class"] != "FULL_EXPOSURE":
        raise SeedVarianceError(f"{context} is comparable but not fully exposed")
    if state == EXPOSURE_CENSORED and payload["exposure_class"] != "EARLY_TERMINATED":
        raise SeedVarianceError(f"{context} is censored but not early terminated")
    _validate_bound(payload["full_horizon_duty_bound_pct"], state, f"{context}.bound")
    return payload


def _validate_cell(cell: Any, design: dict[str, Any], context: str) -> dict[str, Any]:
    payload = _require_object(cell, context)
    _require_exact_keys(payload, CELL_FIELDS, context)
    _require_string(payload["arm_id"], f"{context}.arm_id", allowed=ARM_IDS)
    if payload["audit_protocol_sha256"] != AUDIT_PROTOCOL_SHA256:
        raise SeedVarianceError(f"{context}.audit_protocol_sha256 is not the frozen audit digest")
    if payload["audit_contract_source_sha256"] != AUDIT_CONTRACT_SOURCE_SHA256:
        raise SeedVarianceError(
            f"{context}.audit_contract_source_sha256 is not the pinned audit implementation"
        )
    if payload["pilot_contract_source_sha256"] != PILOT_CONTRACT_SOURCE_SHA256:
        raise SeedVarianceError(
            f"{context}.pilot_contract_source_sha256 is not the pinned pilot implementation"
        )
    for field in CELL_PROVENANCE_FIELDS:
        _require_string(payload[field], f"{context}.{field}")
    for field in CELL_LOCK_FIELDS:
        _require_true(payload[field], f"{context}.{field}")
    _require_string(
        payload["training_terminal_state"],
        f"{context}.training_terminal_state",
        allowed=RETAINED_TERMINAL_STATES,
    )
    if payload["realized_timesteps"] != design["expected_realized_timesteps"]:
        raise SeedVarianceError(
            f"{context}.realized_timesteps must equal the frozen expected budget"
        )
    episodes = _require_list(payload["episodes"], f"{context}.episodes")
    expected_seeds = design["evaluation_seeds"]
    if len(episodes) != len(expected_seeds):
        raise SeedVarianceError(
            f"{context}.episodes must hold exactly {len(expected_seeds)} records"
        )
    observed_seeds = [item.get("evaluation_seed") if isinstance(item, dict) else None for item in episodes]
    if observed_seeds != list(expected_seeds):
        raise SeedVarianceError(
            f"{context}.episodes must be the exact ascending frozen evaluation seed inventory"
        )
    forbidden = design["forbidden_evaluation_seeds"] & set(expected_seeds)
    if forbidden:
        raise SeedVarianceError(f"{context}.episodes touch a retired or sealed seed")
    validated = [
        _validate_episode(item, seed, f"{context}.episodes[{seed}]")
        for item, seed in zip(episodes, expected_seeds)
    ]
    return {**payload, "episodes": validated}


def validate_raw_bundle(raw: Any, protocol: dict[str, Any]) -> dict[str, Any]:
    """Fail-closed validation of the raw replicate inventory."""
    design = _protocol_design(protocol)
    payload = _require_object(raw, "raw")
    _require_exact_keys(payload, RAW_FIELDS, "raw")
    if payload["schema_version"] != RAW_SCHEMA:
        raise SeedVarianceError("unexpected raw schema_version")
    if payload["protocol_id"] != PROTOCOL_ID:
        raise SeedVarianceError("raw.protocol_id does not match the frozen protocol")
    _require_string(payload["bundle_class"], "raw.bundle_class", allowed=BUNDLE_CLASSES)
    _require_string(payload["environment_lock_sha256"], "raw.environment_lock_sha256")
    for key in ("source_git_sha_pre", "source_git_sha_post"):
        value = _require_string(payload[key], f"raw.{key}")
        if not re.fullmatch(GIT_SHA_PATTERN, value):
            raise SeedVarianceError(f"raw.{key} must be a full 40-character Git SHA")
    if payload["source_git_sha_pre"] != payload["source_git_sha_post"]:
        raise SeedVarianceError("raw source Git SHA drifted during execution")
    _require_false(payload["source_dirty_pre"], "raw.source_dirty_pre")
    _require_false(payload["source_dirty_post"], "raw.source_dirty_post")

    replicates = _require_list(payload["replicates"], "raw.replicates")
    if len(replicates) != design["replicate_count"]:
        raise SeedVarianceError(
            f"raw.replicates must hold exactly {design['replicate_count']} replicates"
        )
    validated: list[dict[str, Any]] = []
    for index, replicate in enumerate(replicates):
        context = f"raw.replicates[{index}]"
        entry = _require_object(replicate, context)
        _require_exact_keys(entry, REPLICATE_FIELDS, context)
        if entry["replicate_index"] != index:
            raise SeedVarianceError(f"{context}.replicate_index must be {index}")
        if entry["training_seed"] != design["training_seeds"][index]:
            raise SeedVarianceError(f"{context}.training_seed does not match the frozen schedule")
        if entry["environment_seed_block"] != design["environment_seed_blocks"][index]:
            raise SeedVarianceError(
                f"{context}.environment_seed_block does not match the frozen schedule"
            )
        arms = _require_list(entry["arms"], f"{context}.arms")
        if [item.get("arm_id") if isinstance(item, dict) else None for item in arms] != list(ARM_IDS):
            raise SeedVarianceError(
                f"{context}.arms must be the exact frozen arm inventory in order"
            )
        validated.append(
            {
                **entry,
                "arms": [
                    _validate_cell(arm, design, f"{context}.arms[{arm_id}]")
                    for arm, arm_id in zip(arms, ARM_IDS)
                ],
            }
        )
    total_records = sum(
        len(cell["episodes"]) for replicate in validated for cell in replicate["arms"]
    )
    if total_records != design["expected_terminal_records"]:
        raise SeedVarianceError(
            f"raw holds {total_records} terminal records, expected "
            f"{design['expected_terminal_records']}"
        )
    return {**payload, "replicates": validated}


# --------------------------------------------------------------------------- #
# replicate-level aggregation
# --------------------------------------------------------------------------- #


def _cell_summary(cell: dict[str, Any], context: str) -> dict[str, Any]:
    """Aggregate one (replicate, arm) cell into a point value or an interval."""
    episodes = cell["episodes"]
    comparability = Counter(item["comparability_state"] for item in episodes)
    exposure = Counter(item["exposure_class"] for item in episodes)
    outcomes = Counter(item["outcome_state"] for item in episodes)
    terminals = Counter(item["terminal_record_state"] for item in episodes)
    common = {
        "arm_id": cell["arm_id"],
        "evaluation_output_sha256": cell["evaluation_output_sha256"],
        "realized_timesteps": cell["realized_timesteps"],
        "training_terminal_state": cell["training_terminal_state"],
        "episode_count": len(episodes),
        "comparability_counts": {state: comparability.get(state, 0) for state in COMPARABILITY_STATES},
        "exposure_counts": {state: exposure.get(state, 0) for state in EXPOSURE_CLASSES},
        "outcome_counts": {state: outcomes.get(state, 0) for state in RETAINED_OUTCOME_STATES},
        "terminal_counts": {state: terminals.get(state, 0) for state in RETAINED_TERMINAL_STATES},
    }

    if comparability.get(METHOD_FAILURE, 0):
        # A method failure has no primary outcome to bound, so the cell mean is
        # undefined.  Producing one would require deleting the failure, which
        # the protocol forbids.
        return {
            **common,
            "cell_state": CELL_BLOCKED_METHOD_FAILURE,
            "mean_bound_pct": {
                "state": "NULL",
                "lower_pct": None,
                "upper_pct": None,
                "width_pct": None,
                "reason": REASON_METHOD_FAILURE_CELL,
            },
            "within_replicate_level_sd_pct": None,
            "within_replicate_level_sd_reason": REASON_METHOD_FAILURE_CELL,
        }

    lowers = [item["full_horizon_duty_bound_pct"]["lower_pct"] for item in episodes]
    uppers = [item["full_horizon_duty_bound_pct"]["upper_pct"] for item in episodes]
    lower = _round_percent(ordered_mean(lowers))
    upper = _round_percent(ordered_mean(uppers))
    if upper < lower:
        raise SeedVarianceError(f"{context} aggregated bound is inverted")
    censored = comparability.get(EXPOSURE_CENSORED, 0)
    if censored:
        cell_state = CELL_PARTIALLY_IDENTIFIED
        level_sd: float | None = None
        level_reason: str | None = REASON_WITHIN_SD_CENSORED
    else:
        cell_state = CELL_POINT_IDENTIFIED
        if lower != upper:
            raise SeedVarianceError(
                f"{context} has no censored episode but a non-degenerate mean bound"
            )
        level_sd = _round_percent(ordered_sample_sd(lowers))
        level_reason = None
    return {
        **common,
        "cell_state": cell_state,
        "mean_bound_pct": {
            "state": "OBSERVED",
            "lower_pct": lower,
            "upper_pct": upper,
            "width_pct": _round_percent(upper - lower),
            "reason": None,
        },
        "within_replicate_level_sd_pct": level_sd,
        "within_replicate_level_sd_reason": level_reason,
    }


def _paired_difference(
    reference: dict[str, Any], candidate: dict[str, Any], replicate_index: int
) -> dict[str, Any]:
    """Interval arithmetic on two cell bounds, never a point shortcut."""
    if (
        reference["cell_state"] == CELL_BLOCKED_METHOD_FAILURE
        or candidate["cell_state"] == CELL_BLOCKED_METHOD_FAILURE
    ):
        return {
            "replicate_index": replicate_index,
            "state": "NULL",
            "lower_pp": None,
            "upper_pp": None,
            "width_pp": None,
            "point_identified": False,
            "sign": SIGN_NULL,
            "reason": REASON_BLOCKED_PAIR,
        }
    reference_bound = reference["mean_bound_pct"]
    candidate_bound = candidate["mean_bound_pct"]
    lower = _round_percent(candidate_bound["lower_pct"] - reference_bound["upper_pct"])
    upper = _round_percent(candidate_bound["upper_pct"] - reference_bound["lower_pct"])
    if upper < lower:
        raise SeedVarianceError(
            f"replicate {replicate_index} paired identification bound is inverted"
        )
    point_identified = (
        reference["cell_state"] == CELL_POINT_IDENTIFIED
        and candidate["cell_state"] == CELL_POINT_IDENTIFIED
    )
    if upper < 0.0:
        sign = SIGN_NEGATIVE
    elif lower > 0.0:
        sign = SIGN_POSITIVE
    else:
        sign = SIGN_UNIDENTIFIED
    return {
        "replicate_index": replicate_index,
        "state": "OBSERVED",
        "lower_pp": lower,
        "upper_pp": upper,
        "width_pp": _round_percent(upper - lower),
        "point_identified": point_identified,
        "sign": sign,
        "reason": None,
    }


def _within_replicate_paired_sd(
    reference_cell: dict[str, Any], candidate_cell: dict[str, Any], replicate_index: int
) -> dict[str, Any]:
    """Episode-level paired SD inside one replicate, when every pair is a point.

    This is the quantity a pseudo-replicated analysis would divide by
    ``sqrt(150)``, so it is kept next to the between-replicate SD that the
    correct analysis divides by ``sqrt(5)``.
    """
    reference_episodes = reference_cell["episodes"]
    candidate_episodes = candidate_cell["episodes"]
    differences: list[float] = []
    for reference_episode, candidate_episode in zip(reference_episodes, candidate_episodes):
        if (
            reference_episode["comparability_state"] != COMPARABLE
            or candidate_episode["comparability_state"] != COMPARABLE
        ):
            return {
                "replicate_index": replicate_index,
                "paired_sd_pp": None,
                "reason": REASON_WITHIN_SD_CENSORED,
            }
        differences.append(
            candidate_episode["full_horizon_duty_bound_pct"]["lower_pct"]
            - reference_episode["full_horizon_duty_bound_pct"]["lower_pct"]
        )
    return {
        "replicate_index": replicate_index,
        "paired_sd_pp": _round_percent(ordered_sample_sd(differences)),
        "reason": None,
    }


def _mean_or_none(values: list[float | None]) -> float | None:
    if any(value is None for value in values):
        return None
    return _round_percent(ordered_mean([float(value) for value in values]))


def _method_level(
    differences: list[dict[str, Any]],
    paired_sds: list[dict[str, Any]],
    design: dict[str, Any],
) -> dict[str, Any]:
    """Method-level statistics with denominator ``replicate_count``, always."""
    denominator = len(differences)
    if denominator != design["replicate_count"]:
        raise SeedVarianceError(
            "method-level denominator must equal replicate_count, got "
            f"{denominator} for {design['replicate_count']} replicates"
        )
    if denominator in design["forbidden_denominators"]:
        raise SeedVarianceError("PSEUDO_REPLICATION_FORBIDDEN: episode-level denominator used")
    if [item["replicate_index"] for item in differences] != list(range(denominator)):
        raise SeedVarianceError("paired differences must be in ascending replicate order")

    mean_paired_sd = _mean_or_none([item["paired_sd_pp"] for item in paired_sds])
    blocked = [item for item in differences if item["state"] == "NULL"]
    if blocked:
        return {
            "analysis_unit": ANALYSIS_UNIT,
            "method_level_n": denominator,
            "theta_bound_pp": {
                "state": "NULL",
                "lower_pp": None,
                "upper_pp": None,
                "width_pp": None,
                "reason": REASON_BLOCKED_PAIR,
            },
            "sign": SIGN_NULL,
            "sign_identified_replicate_count": 0,
            "between_replicate_sd_pp": None,
            "between_replicate_sd_reason": REASON_BLOCKED_PAIR,
            "mean_within_replicate_paired_sd_pp": mean_paired_sd,
            "variance_ratio_between_over_within": None,
            "sample_size_decision_input_ready": False,
            "blocked_replicate_indices": [item["replicate_index"] for item in blocked],
        }

    lowers = [item["lower_pp"] for item in differences]
    uppers = [item["upper_pp"] for item in differences]
    theta_lower = _round_percent(ordered_mean(lowers))
    theta_upper = _round_percent(ordered_mean(uppers))
    if theta_upper < theta_lower:
        raise SeedVarianceError("method-level identification bound is inverted")
    if theta_upper < 0.0:
        sign = SIGN_NEGATIVE
    elif theta_lower > 0.0:
        sign = SIGN_POSITIVE
    else:
        sign = SIGN_UNIDENTIFIED
    all_point = all(item["point_identified"] for item in differences)
    if all_point:
        between_sd: float | None = _round_percent(ordered_sample_sd(lowers))
        between_reason: str | None = None
    else:
        # A sample SD is not defined on intervals and an interval midpoint would
        # be an imputation, so the statistic is withheld rather than estimated.
        between_sd = None
        between_reason = REASON_PARTIAL_SD
    ratio = None
    if between_sd is not None and mean_paired_sd is not None and mean_paired_sd > 0.0:
        ratio = _round_ratio(between_sd / mean_paired_sd)
    return {
        "analysis_unit": ANALYSIS_UNIT,
        "method_level_n": denominator,
        "theta_bound_pp": {
            "state": "OBSERVED",
            "lower_pp": theta_lower,
            "upper_pp": theta_upper,
            "width_pp": _round_percent(theta_upper - theta_lower),
            "reason": None,
        },
        "sign": sign,
        "sign_identified_replicate_count": sum(
            1 for item in differences if item["sign"] in (SIGN_NEGATIVE, SIGN_POSITIVE)
        ),
        "between_replicate_sd_pp": between_sd,
        "between_replicate_sd_reason": between_reason,
        "mean_within_replicate_paired_sd_pp": mean_paired_sd,
        "variance_ratio_between_over_within": ratio,
        "sample_size_decision_input_ready": between_sd is not None,
        "blocked_replicate_indices": [],
    }


def build_summary(raw: dict[str, Any], protocol: dict[str, Any]) -> dict[str, Any]:
    """Derive the whole seed-variance summary from validated raw rows."""
    design = _protocol_design(protocol)
    validated = validate_raw_bundle(raw, protocol)
    replicates = validated["replicates"]

    cells: dict[str, list[dict[str, Any]]] = {arm_id: [] for arm_id in ARM_IDS}
    for replicate in replicates:
        for cell in replicate["arms"]:
            context = (
                f"replicate {replicate['replicate_index']} arm {cell['arm_id']}"
            )
            cells[cell["arm_id"]].append(_cell_summary(cell, context))

    replicate_rows = []
    for replicate in replicates:
        replicate_rows.append(
            {
                "replicate_index": replicate["replicate_index"],
                "training_seed": replicate["training_seed"],
                "environment_seed_block": replicate["environment_seed_block"],
                "arms": [
                    cells[arm_id][replicate["replicate_index"]] for arm_id in ARM_IDS
                ],
            }
        )

    candidates = {}
    for candidate_id in CANDIDATE_ARM_IDS:
        differences = []
        paired_sds = []
        for replicate in replicates:
            index = replicate["replicate_index"]
            reference_cell = next(
                cell for cell in replicate["arms"] if cell["arm_id"] == REFERENCE_ARM_ID
            )
            candidate_cell = next(
                cell for cell in replicate["arms"] if cell["arm_id"] == candidate_id
            )
            differences.append(
                _paired_difference(
                    cells[REFERENCE_ARM_ID][index], cells[candidate_id][index], index
                )
            )
            paired_sds.append(
                _within_replicate_paired_sd(reference_cell, candidate_cell, index)
            )
        candidates[candidate_id] = {
            "candidate_arm_id": candidate_id,
            "reference_arm_id": REFERENCE_ARM_ID,
            "replicate_paired_differences": differences,
            "within_replicate_paired_sd": paired_sds,
            "method_level": _method_level(differences, paired_sds, design),
        }

    within_level = {
        arm_id: {
            "per_replicate": [
                {
                    "replicate_index": index,
                    "level_sd_pct": cell["within_replicate_level_sd_pct"],
                    "reason": cell["within_replicate_level_sd_reason"],
                }
                for index, cell in enumerate(cells[arm_id])
            ],
            "mean_level_sd_pct": _mean_or_none(
                [cell["within_replicate_level_sd_pct"] for cell in cells[arm_id]]
            ),
        }
        for arm_id in ARM_IDS
    }

    blockers = _retained_blockers(candidates, cells)
    status = STATUS_CLEAN if not blockers else STATUS_BLOCKED
    return {
        "schema_version": SUMMARY_SCHEMA,
        "protocol_id": PROTOCOL_ID,
        "protocol_sha256": PROTOCOL_SHA256,
        "audit_protocol_sha256": AUDIT_PROTOCOL_SHA256,
        "bundle_class": validated["bundle_class"],
        "environment_lock_sha256": validated["environment_lock_sha256"],
        "source_git_sha_pre": validated["source_git_sha_pre"],
        "source_git_sha_post": validated["source_git_sha_post"],
        "analysis_unit": ANALYSIS_UNIT,
        "primary_measurement_id": PRIMARY_MEASUREMENT_ID,
        "replicate_count": design["replicate_count"],
        "training_seeds": design["training_seeds"],
        "evaluation_seed_first": design["evaluation_seeds"][0],
        "evaluation_seed_last": design["evaluation_seeds"][-1],
        "terminal_record_count": design["expected_terminal_records"],
        "forbidden_denominators": design["forbidden_denominators"],
        "replicates": replicate_rows,
        "within_replicate_level_sd": within_level,
        "candidates": [candidates[candidate_id] for candidate_id in CANDIDATE_ARM_IDS],
        "selected_candidate_arm_id": None,
        "selection_permitted": False,
        "method_level_power_ready": False,
        "statistics_ready": False,
        "paper_data_ready": False,
        "training_replicate_scope": "CONDITIONAL_ON_FIXED_WARM_START",
        "cross_protocol_comparability": "NON_VERIFIABLE_ENVIRONMENT",
        "seed_variance_status": status,
        "retained_blockers": blockers,
        # The frozen protocol is the single source of the claim boundary; the
        # module constant exists only for error receipts, where no protocol may
        # be loadable. Two wordings would make the independent replay diverge.
        "claim_boundary": protocol["claim_boundary"],
    }


def _retained_blockers(
    candidates: dict[str, dict[str, Any]], cells: dict[str, list[dict[str, Any]]]
) -> list[dict[str, Any]]:
    """Every withheld statistic is reported as a retained blocker, never dropped."""
    blockers: list[dict[str, Any]] = []
    for arm_id in ARM_IDS:
        for index, cell in enumerate(cells[arm_id]):
            if cell["cell_state"] != CELL_POINT_IDENTIFIED:
                blockers.append(
                    {
                        "scope": "cell",
                        "arm_id": arm_id,
                        "replicate_index": index,
                        "state": cell["cell_state"],
                        "reason": cell["within_replicate_level_sd_reason"],
                    }
                )
    for candidate_id in CANDIDATE_ARM_IDS:
        method_level = candidates[candidate_id]["method_level"]
        if method_level["between_replicate_sd_pp"] is None:
            blockers.append(
                {
                    "scope": "method_level",
                    "arm_id": candidate_id,
                    "replicate_index": None,
                    "state": "BETWEEN_REPLICATE_SD_WITHHELD",
                    "reason": method_level["between_replicate_sd_reason"],
                }
            )
        if method_level["sign"] == SIGN_UNIDENTIFIED:
            blockers.append(
                {
                    "scope": "method_level",
                    "arm_id": candidate_id,
                    "replicate_index": None,
                    "state": "SIGN_UNIDENTIFIED",
                    "reason": "METHOD_LEVEL_BOUND_CONTAINS_ZERO",
                }
            )
    return blockers


# --------------------------------------------------------------------------- #
# bundle IO and read-only verification
# --------------------------------------------------------------------------- #


PROTOCOL_ARTIFACT = "training_seed_variance_protocol.json"
LOCK_ARTIFACT = "environment_lock.json"
RAW_ARTIFACT = "raw_replicates.json"
SUMMARY_ARTIFACT = "seed_variance_summary.json"
RECEIPT_ARTIFACT = "seed_variance_receipt.json"
SOURCE_INDEX_ARTIFACT = "seed_variance_source_index.json"
SOURCE_ARTIFACTS = (PROTOCOL_ARTIFACT, LOCK_ARTIFACT, RAW_ARTIFACT)

REPLAY_MODULE = Path(__file__).resolve().parent / "training_seed_variance_replay.py"


def _safe_relative(root: Path, path: Path, context: str) -> str:
    resolved_root = root.resolve()
    resolved = path.resolve()
    if not resolved.is_relative_to(resolved_root) or not resolved.is_file():
        raise SeedVarianceError(f"{context} escapes the bundle root: {path.name}")
    relative = resolved.relative_to(resolved_root)
    if any(part in ("..", "") for part in relative.parts):
        raise SeedVarianceError(f"{context} uses an unsafe relative path: {relative}")
    return PurePosixPath(relative).as_posix()


def _bundle_file_set(root: Path) -> list[str]:
    resolved = root.resolve()
    return sorted(
        PurePosixPath(item.resolve().relative_to(resolved)).as_posix()
        for item in resolved.rglob("*")
        if item.is_file()
    )


def _source_index(root: Path) -> dict[str, Any]:
    entries = []
    for name in SOURCE_ARTIFACTS:
        path = root / name
        if not path.is_file():
            raise SeedVarianceError(f"bundle is missing a required artifact: {name}")
        entries.append(
            {
                "path": _safe_relative(root, path, "source artifact"),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return {
        "schema_version": SOURCE_INDEX_SCHEMA,
        "protocol_id": PROTOCOL_ID,
        "artifact_count": len(entries),
        "total_bytes": sum(entry["bytes"] for entry in entries),
        "artifacts": entries,
    }


def read_source_bundle(root: Path) -> dict[str, Any]:
    """Load the bundle and index it, so read-only access is checkable later."""
    resolved = Path(root)
    if not resolved.is_dir():
        raise SeedVarianceError(f"bundle root is not a directory: {resolved}")
    index = _source_index(resolved)
    protocol = load_protocol(resolved / PROTOCOL_ARTIFACT)
    lock_record = _load_json_file(resolved / LOCK_ARTIFACT)
    raw = _load_json_file(resolved / RAW_ARTIFACT)
    lock_status = check_environment_lock(protocol, lock_record)
    if raw.get("environment_lock_sha256") != lock_status["environment_locked_sha256"]:
        raise SeedVarianceError(
            "raw.environment_lock_sha256 does not match the bundle's lock record"
        )
    return {
        "root": resolved,
        "source_index": index,
        "file_set": _bundle_file_set(resolved),
        "protocol": protocol,
        "lock_record": lock_record,
        "lock_status": lock_status,
        "raw": raw,
    }


def _verify_read_only(bundle: dict[str, Any]) -> dict[str, Any]:
    """Re-hash and re-enumerate the bundle, so read-only is proved not asserted."""
    root = bundle["root"]
    post_index = _source_index(root)
    post_files = _bundle_file_set(root)
    if post_index["artifacts"] != bundle["source_index"]["artifacts"]:
        raise SeedVarianceError("read-only contract violated: source artifact digests changed")
    if post_files != bundle["file_set"]:
        raise SeedVarianceError("read-only contract violated: bundle file set changed")
    return {
        "source_bundle_read_only_verified": True,
        "source_artifact_count": post_index["artifact_count"],
        "source_total_bytes": post_index["total_bytes"],
    }


def _write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".partial")
    if temporary.exists():
        raise SeedVarianceError(f"refusing to reuse partial artifact: {temporary.name}")
    descriptor = os.open(
        temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    )
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
    os.replace(temporary, path)
    if path.stat().st_size != len(payload) or sha256_file(path) != _sha256_bytes(payload):
        raise SeedVarianceError(f"artifact readback mismatch: {path.name}")


def _write_json(path: Path, payload: Any) -> str:
    encoded = _json_bytes(payload)
    _write_bytes(path, encoded)
    return _sha256_bytes(encoded)


# --------------------------------------------------------------------------- #
# independent stdlib-only replay
# --------------------------------------------------------------------------- #


def run_replay(bundle_root: Path, summary_path: Path) -> dict[str, Any]:
    """Rebuild the summary in a separate ``python -I -S`` process.

    The replay is a second implementation, not a second call: it must reach
    exact JSON identity from the same raw rows, which is what makes the fixed
    reduction order in ``ordered_mean`` part of the contract rather than an
    accident of this file.
    """
    if not REPLAY_MODULE.is_file():
        raise SeedVarianceError("independent replay module is missing")
    root = Path(bundle_root)
    completed = subprocess.run(
        [
            sys.executable,
            "-I",
            "-S",
            str(REPLAY_MODULE),
            str((root / PROTOCOL_ARTIFACT).resolve()),
            str((root / LOCK_ARTIFACT).resolve()),
            str((root / RAW_ARTIFACT).resolve()),
            str(Path(summary_path).resolve()),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise SeedVarianceError(
            "independent replay failed: "
            f"exit {completed.returncode}: {completed.stderr.strip()[:600]}"
        )
    receipt = _load_json_bytes(completed.stdout.encode("utf-8"), "replay receipt")
    if receipt.get("schema_version") != REPLAY_SCHEMA:
        raise SeedVarianceError("unexpected replay receipt schema_version")
    if receipt.get("replay_exact") is not True:
        raise SeedVarianceError("independent replay did not reach exact identity")
    return receipt


# --------------------------------------------------------------------------- #
# top-level analysis
# --------------------------------------------------------------------------- #


def analyse_seed_variance(
    bundle_root: Path, output_root: Path, *, protocol_path: Path | None = None
) -> dict[str, Any]:
    """Read a seed-variance bundle, derive the summary, and emit a receipt."""
    source = Path(bundle_root).resolve()
    output = Path(output_root).resolve()
    # Writing derived artifacts into the audited bundle would break the
    # read-only guarantee this contract exists to prove, and the resulting
    # "file set changed" failure would blame the wrong thing.
    if output == source or output.is_relative_to(source):
        raise SeedVarianceError(
            "output root must live outside the source bundle: "
            f"{output} is inside {source}"
        )
    bundle = read_source_bundle(source)
    inheritance = verify_pilot_inheritance(bundle["protocol"])
    implementations = verify_inherited_implementations()
    if protocol_path is not None:
        # An explicitly supplied protocol must still be the frozen one; this is
        # only a path override, never a contract override.
        load_protocol(Path(protocol_path))
    summary = build_summary(bundle["raw"], bundle["protocol"])
    summary_path = output / SUMMARY_ARTIFACT
    summary_sha256 = _write_json(summary_path, summary)
    index_sha256 = _write_json(output / SOURCE_INDEX_ARTIFACT, bundle["source_index"])
    replay = run_replay(bundle["root"], summary_path)
    read_only = _verify_read_only(bundle)

    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "protocol_id": PROTOCOL_ID,
        "protocol_sha256": PROTOCOL_SHA256,
        "audit_protocol_sha256": AUDIT_PROTOCOL_SHA256,
        "bundle_class": summary["bundle_class"],
        "analysis_unit": ANALYSIS_UNIT,
        "replicate_count": summary["replicate_count"],
        "method_level_n": [
            candidate["method_level"]["method_level_n"] for candidate in summary["candidates"]
        ],
        "terminal_record_count": summary["terminal_record_count"],
        "environment_lock_sha256": summary["environment_lock_sha256"],
        "environment_lock_class": bundle["lock_status"]["environment_lock_class"],
        "environment_lock_completeness": bundle["lock_status"]["environment_lock_completeness"],
        "environment_lock_threading": bundle["lock_status"]["environment_lock_threading"],
        "bundle_class_is_declared_not_derived": True,
        **implementations,
        "environment_lock_verified_runs": 2
        * summary["replicate_count"]
        * len(ARM_IDS),
        **inheritance,
        "source_git_sha_pre": summary["source_git_sha_pre"],
        "source_git_sha_post": summary["source_git_sha_post"],
        "summary_path": SUMMARY_ARTIFACT,
        "summary_sha256": summary_sha256,
        "source_index_path": SOURCE_INDEX_ARTIFACT,
        "source_index_sha256": index_sha256,
        "replay": replay,
        "seed_variance_status": summary["seed_variance_status"],
        "retained_blocker_count": len(summary["retained_blockers"]),
        "selected_candidate_arm_id": None,
        "selection_permitted": False,
        "method_level_power_ready": False,
        "statistics_ready": False,
        "paper_data_ready": False,
        "training_replicate_scope": summary["training_replicate_scope"],
        "cross_protocol_comparability": summary["cross_protocol_comparability"],
        "evidence_scope": "SIM_ONLY_MUJOCO",
        "validation_status": "NOT_PHYSICALLY_VALIDATED",
        "claim_boundary": CLAIM_BOUNDARY,
        **read_only,
    }
    receipt_sha256 = _write_json(output / RECEIPT_ARTIFACT, receipt)
    return {**receipt, "receipt_path": RECEIPT_ARTIFACT, "receipt_sha256": receipt_sha256}


def validate_seed_variance_bundle(receipt_path: Path) -> dict[str, Any]:
    """Re-check an emitted receipt against the artifacts it points at."""
    receipt_file = Path(receipt_path)
    receipt = _load_json_file(receipt_file)
    if receipt.get("schema_version") != RECEIPT_SCHEMA:
        raise SeedVarianceError("unexpected receipt schema_version")
    if receipt.get("protocol_sha256") != PROTOCOL_SHA256:
        raise SeedVarianceError("receipt pins an unexpected protocol digest")
    root = receipt_file.parent
    summary_path = root / _require_string(receipt.get("summary_path"), "receipt.summary_path")
    if sha256_file(summary_path) != receipt.get("summary_sha256"):
        raise SeedVarianceError("summary digest does not match the receipt")
    summary = _load_json_file(summary_path)
    if summary.get("schema_version") != SUMMARY_SCHEMA:
        raise SeedVarianceError("unexpected summary schema_version")
    if summary.get("selected_candidate_arm_id") is not None:
        raise SeedVarianceError("summary must not select a candidate arm")
    for key in ("method_level_power_ready", "statistics_ready", "paper_data_ready"):
        if summary.get(key) is not False:
            raise SeedVarianceError(f"summary must retain {key}=false")
    for candidate in _require_list(summary.get("candidates"), "summary.candidates"):
        method_level = _require_object(candidate.get("method_level"), "candidate.method_level")
        if method_level.get("method_level_n") != summary.get("replicate_count"):
            raise SeedVarianceError(
                "PSEUDO_REPLICATION_FORBIDDEN: method_level_n does not equal replicate_count"
            )
        if method_level.get("method_level_n") in _require_list(
            summary.get("forbidden_denominators"), "summary.forbidden_denominators"
        ):
            raise SeedVarianceError(
                "PSEUDO_REPLICATION_FORBIDDEN: method_level_n is a forbidden denominator"
            )
    return {
        "schema_version": VALIDATION_SCHEMA,
        "protocol_id": PROTOCOL_ID,
        "contract_valid": True,
        "analysis_unit": summary.get("analysis_unit"),
        "replicate_count": summary.get("replicate_count"),
        "seed_variance_status": receipt.get("seed_variance_status"),
        "retained_blocker_count": receipt.get("retained_blocker_count"),
        "selected_candidate_arm_id": None,
        "method_level_power_ready": False,
        "statistics_ready": False,
        "paper_data_ready": False,
        "claim_boundary": CLAIM_BOUNDARY,
    }


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def _print(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False))


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Derive SEEDVAR-V7-TRAINING-REPLICATE-DEV-V1 method-level variance "
            "evidence from a retained replicate bundle. Exit 0 on complete "
            "evidence, 1 on retained blockers, 2 on structural failure."
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    analyse_parser = subparsers.add_parser("analyse")
    analyse_parser.add_argument("source_bundle", type=Path)
    analyse_parser.add_argument("output_root", type=Path)
    analyse_parser.add_argument("--protocol", type=Path, default=None)
    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("receipt", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "analyse":
            payload = analyse_seed_variance(
                args.source_bundle, args.output_root, protocol_path=args.protocol
            )
        else:
            payload = validate_seed_variance_bundle(args.receipt)
        exit_code = 0 if payload["seed_variance_status"] == STATUS_CLEAN else 1
    except Exception as exc:
        _print(
            {
                "schema_version": ERROR_SCHEMA,
                "protocol_id": PROTOCOL_ID,
                "validation_status": "STRUCTURAL_FAILURE",
                "contract_valid": False,
                "selected_candidate_arm_id": None,
                "method_level_power_ready": False,
                "statistics_ready": False,
                "paper_data_ready": False,
                "error": f"{type(exc).__name__}: {exc}"[:1000],
                "evidence_scope": "SIM_ONLY_MUJOCO",
                "claim_boundary": CLAIM_BOUNDARY,
            }
        )
        raise SystemExit(2) from exc
    _print(payload)
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()

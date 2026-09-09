"""Evidence contract for ``SECONDCASE-EXPOSURE-CENSORING-WALKER2D-V1`` (PUB-A1).

Read-only over a raw bundle produced by ``rl/second_case_runner.py``.  Standard
library only, so ``python -I -S`` can replay the summary; the two local modules
it needs (``exposure_identification``, ``environment_lock``) are themselves
stdlib-only at import and are found by an explicit ``sys.path`` entry, which
isolated mode permits.

What this contract refuses to do
--------------------------------
* Report a direction for ``W2D_C_FILTERED - W2D_A_DIRECT``.  The protocol makes
  no prediction about it and the summary carries ``direction_claim_permitted =
  false``.
* Compute anything with an episode denominator.  The analysis unit is the
  training replicate; 30 / 60 / 150 / 300 are refused by the arithmetic core.
* Drop or impute a censored episode, or drop a failed replicate.  A method
  failure makes the replicate's paired difference ``NULL`` and blocks the
  method-level decision; the denominator does not move.
* Load a protocol whose digest differs from the pinned one, or one that claims
  to be preregistered.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import exposure_identification as ei  # noqa: E402
from environment_lock import (  # noqa: E402
    EnvironmentLockError,
    FULL_LOCK,
    MEASURED_LOCK_CLASS,
    THREADING_PINNED,
    validate_lock_record,
)

PROTOCOL_SCHEMA = "SECOND_CASE_EXPOSURE_PROTOCOL_V1"
PROTOCOL_ID = "SECONDCASE-EXPOSURE-CENSORING-WALKER2D-V1"
PROTOCOL_SHA256 = "sha256:45d1ec553a1124fd613f90a8034b27f10ef8f01f23a219cca216479fc4c5350c"
PUBLICATION_GATE = "PUB-A1"

RAW_SCHEMA = "SECOND_CASE_EXPOSURE_RAW_V1"
CELL_SCHEMA = "SECOND_CASE_EXPOSURE_CELL_V1"
CELL_SCHEMA_V2 = "SECOND_CASE_EXPOSURE_CELL_V2"
SUMMARY_SCHEMA = "SECOND_CASE_EXPOSURE_SUMMARY_V1"
RECEIPT_SCHEMA = "SECOND_CASE_EXPOSURE_RECEIPT_V1"
REPLAY_SCHEMA = "SECOND_CASE_EXPOSURE_REPLAY_RECEIPT_V1"

DEVELOPMENT_BUNDLE_CLASS = "SECOND_CASE_DEVELOPMENT_BUNDLE"
SYNTHETIC_BUNDLE_CLASS = "SYNTHETIC_REGRESSION_BUNDLE"
BUNDLE_CLASSES = (DEVELOPMENT_BUNDLE_CLASS, SYNTHETIC_BUNDLE_CLASS)

OUTCOME_UNINFORMATIVE = "SECOND_CASE_UNINFORMATIVE_NO_CENSORING"
OUTCOME_REPRODUCED = "SECOND_CASE_ARTIFACT_REPRODUCED"
OUTCOME_AGREE = "SECOND_CASE_NAIVE_AND_BOUND_AGREE"
OUTCOME_BOUND_ONLY = "SECOND_CASE_BOUND_IDENTIFIED_NAIVE_UNCERTAIN"
OUTCOME_BLOCKED = "SECOND_CASE_BLOCKED_METHOD_FAILURE"
OUTCOME_LABELS = (
    OUTCOME_UNINFORMATIVE,
    OUTCOME_REPRODUCED,
    OUTCOME_AGREE,
    OUTCOME_BOUND_ONLY,
    OUTCOME_BLOCKED,
)

# ---- V2: same design, plus a reference-adequacy precondition (P0) --------- #
# V1 measured that with both arms censored the bound contains zero by
# construction.  V2 therefore requires the reference arm to reach a frozen
# full-exposure fraction before P1/P2 are even evaluated, and scopes P1 to the
# candidate arm.  The V1 path is untouched: its summary must stay byte-identical
# to the retained evidence, which a test asserts.
PROTOCOL_SCHEMA_V2 = "SECOND_CASE_EXPOSURE_PROTOCOL_V2"
PROTOCOL_SCHEMAS = (PROTOCOL_SCHEMA, PROTOCOL_SCHEMA_V2)
PROTOCOL_ID_V2 = "SECONDCASE-EXPOSURE-CENSORING-WALKER2D-V2"
PROTOCOL_V2_SHA256: str | None = None  # never pinned; withdrawn 2026-09-09 (see WITHDRAWN_PROTOCOLS)
PROTOCOL_ID_HOPPER = "SECONDCASE-EXPOSURE-CENSORING-HOPPER-V1"
PROTOCOL_HOPPER_SHA256: str | None = None  # never pinned; withdrawn 2026-09-09 (see WITHDRAWN_PROTOCOLS)
PINNED_PROTOCOLS: dict[str, str | None] = {
    PROTOCOL_ID: PROTOCOL_SHA256,
    PROTOCOL_ID_V2: PROTOCOL_V2_SHA256,
    PROTOCOL_ID_HOPPER: PROTOCOL_HOPPER_SHA256,
}
# Withdrawn on 2026-09-09 by the project owner's decision to stop the second-case V2 line and
# reframe Track A (docs/TRACK_A_REFRAME_2026-09-09.md, PUBLICATION-PLAN-V2).  Three budget probes
# ran first: Walker2d probes V1 and V2 were negative at their frozen caps, and the Hopper probe
# found a budget but its exposure-only adequacy rule selected a standing reference whose
# saturation was near zero, for which the artifact is impossible by construction.  Neither id
# was ever pinned, so neither ever loaded; both stay in PINNED_PROTOCOLS with a None digest so
# that a protocol carrying one of them is refused with the decision as the reason rather than a
# still-pending freeze.  The V2 schema and its P0 logic remain implemented and tested as software.
# Any future attempt must mint a new protocol id, and its budget probe must add a
# reference-saturation floor to the exposure rule.
WITHDRAWN_PROTOCOLS: dict[str, str] = {
    PROTOCOL_ID_V2: (
        "withdrawn 2026-09-09: Walker2d-v5 budget probes V1 and V2 were negative at their frozen "
        "caps; the second-case V2 line was closed by decision (docs/TRACK_A_REFRAME_2026-09-09.md)"
    ),
    PROTOCOL_ID_HOPPER: (
        "withdrawn 2026-09-09: the Hopper-v5 budget probe selected a near-zero-saturation standing "
        "reference under an exposure-only adequacy rule; the line was closed by decision "
        "(docs/TRACK_A_REFRAME_2026-09-09.md)"
    ),
}
if any(PINNED_PROTOCOLS[_withdrawn] is not None for _withdrawn in WITHDRAWN_PROTOCOLS):
    raise RuntimeError("a withdrawn second-case protocol id must never carry a pinned digest")
SUMMARY_SCHEMA_V2 = "SECOND_CASE_EXPOSURE_SUMMARY_V2"
OUTCOME_REFERENCE_NOT_ADEQUATE = "SECOND_CASE_REFERENCE_NOT_ADEQUATE"
OUTCOME_LABELS_V2 = OUTCOME_LABELS + (OUTCOME_REFERENCE_NOT_ADEQUATE,)
P1_SCOPE_ANY = "ANY_ARM"
P1_SCOPE_CANDIDATE = "CANDIDATE_ARM"

OUTCOME_OBSERVED = "OBSERVED"
OUTCOME_NONFINITE = "NONFINITE"
TERMINAL_STATES = ("COMPLETED", "FAILED")

COMPARABLE = "COMPARABLE"
EXPOSURE_CENSORED = "EXPOSURE_CENSORED"
METHOD_FAILURE = "METHOD_FAILURE_NOT_CENSORING"

CELL_POINT = "POINT_IDENTIFIED"
CELL_PARTIAL = "PARTIALLY_IDENTIFIED"
CELL_BLOCKED = "BLOCKED_METHOD_FAILURE"

SHA_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
GIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")

DEFAULT_PROTOCOL = _HERE / "rl" / "second_case_exposure_protocol.json"

CLAIM_BOUNDARY = (
    "Supports only whether the naive per-step saturation estimator and the assumption-free "
    "full-horizon bound disagree on Walker2d-v5 under its default early termination.",
    "Does not support any statement about Walker2d locomotion quality, about low-pass action "
    "filtering as a design choice, about the v7 humanoid, or about physical actuators.",
    "DEVELOPMENT evidence under an internal hash freeze; not preregistered; no direction is "
    "claimed for the contrast; no candidate is selected; paper_data_ready is unchanged.",
)

EPISODE_FIELDS = (
    "all_finite",
    "comparability_state",
    "episode_return",
    "evaluation_seed",
    "exposure_class",
    "full_horizon_duty_bound_pct",
    "naive_duty_pct",
    "outcome_state",
    "realized_steps",
    "saturated_joint_steps",
    "terminated",
    "trace_sha256",
    "truncated",
)
CELL_FIELDS = (
    "arm_id",
    "environment_locked_sha256",
    "episodes",
    "evaluation_environment_lock_verified",
    "evaluation_output_sha256",
    "evaluation_terminal_state",
    "low_pass_alpha",
    "policy_sha256",
    "realized_timesteps",
    "schema_version",
    "training_environment_lock_verified",
    "training_terminal_state",
)
CELL_FIELDS_V2 = tuple(sorted(CELL_FIELDS + ("normalizer_sha256",)))
REPLICATE_FIELDS = ("arms", "replicate_index", "training_seed")
RAW_FIELDS = (
    "bundle_class",
    "environment_lock_sha256",
    "plant_asset_sha256",
    "protocol_id",
    "protocol_sha256",
    "replicates",
    "schema_version",
    "source_dirty_post",
    "source_dirty_pre",
    "source_git_sha_post",
    "source_git_sha_pre",
)
PROTOCOL_FIELDS = (
    "analysis",
    "arms",
    "claim_boundary",
    "environment",
    "environment_lock_requirement",
    "evaluation",
    "forbidden_seed_ranges",
    "predictions",
    "preregistration",
    "primary_measurement",
    "protocol_id",
    "publication_gate",
    "purpose",
    "schema_version",
    "shared_action_interface",
    "source_requirement",
    "training",
)


class SecondCaseError(RuntimeError):
    """Fail-closed contract violation."""


# --------------------------------------------------------------------------- #
# json / hashing
# --------------------------------------------------------------------------- #


def _reject_nonfinite(constant: str) -> Any:
    raise SecondCaseError(f"non-finite JSON constant {constant!r} is forbidden")


def load_json_bytes(payload: bytes, label: str) -> Any:
    try:
        return json.loads(payload.decode("utf-8"), parse_constant=_reject_nonfinite)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SecondCaseError(f"{label} is not strict JSON: {exc}") from exc


def load_json_file(path: Path) -> Any:
    return load_json_bytes(Path(path).read_bytes(), str(path))


def json_bytes(payload: Any) -> bytes:
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)
    return (text + "\n").encode("utf-8")


def sha256_bytes(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


# --------------------------------------------------------------------------- #
# validation helpers
# --------------------------------------------------------------------------- #


def _obj(value: Any, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SecondCaseError(f"{context} must be an object")
    return value


def _lst(value: Any, context: str) -> list[Any]:
    if not isinstance(value, list):
        raise SecondCaseError(f"{context} must be a list")
    return value


def _exact_keys(value: dict[str, Any], expected: tuple[str, ...], context: str) -> None:
    actual = tuple(sorted(value))
    if actual != tuple(sorted(expected)):
        missing = sorted(set(expected) - set(actual))
        extra = sorted(set(actual) - set(expected))
        raise SecondCaseError(f"{context} keys mismatch: missing={missing} extra={extra}")


def _int(value: Any, context: str, *, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise SecondCaseError(f"{context} must be an integer")
    if minimum is not None and value < minimum:
        raise SecondCaseError(f"{context} must be >= {minimum}")
    return value


def _num(value: Any, context: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SecondCaseError(f"{context} must be a number")
    if not math.isfinite(float(value)):
        raise SecondCaseError(f"{context} must be finite")
    return float(value)


def _str(value: Any, context: str, *, allowed: tuple[str, ...] | None = None) -> str:
    if not isinstance(value, str) or not value:
        raise SecondCaseError(f"{context} must be a non-empty string")
    if allowed is not None and value not in allowed:
        raise SecondCaseError(f"{context} must be one of {allowed}, got {value!r}")
    return value


def _bool(value: Any, context: str) -> bool:
    if not isinstance(value, bool):
        raise SecondCaseError(f"{context} must be a boolean")
    return value


def _sha(value: Any, context: str) -> str:
    text = _str(value, context)
    if not SHA_PATTERN.match(text):
        raise SecondCaseError(f"{context} must look like sha256:<64 hex>")
    return text


# --------------------------------------------------------------------------- #
# protocol
# --------------------------------------------------------------------------- #


def protocol_digest(path: Path = DEFAULT_PROTOCOL) -> str:
    return sha256_file(Path(path))


def load_protocol(path: Path = DEFAULT_PROTOCOL, *, require_pinned_digest: bool = True) -> dict[str, Any]:
    payload = Path(path).read_bytes()
    digest = sha256_bytes(payload)
    protocol = _obj(load_json_bytes(payload, str(path)), "protocol")
    validate_protocol(protocol)
    protocol_id = protocol["protocol_id"]
    if protocol_id in WITHDRAWN_PROTOCOLS:
        # A withdrawn id is refused on every path, pinned-digest requirement or not: it must
        # never be executed, frozen or analysed as DEVELOPMENT evidence.
        raise SecondCaseError(f"SECONDCASE_PROTOCOL_WITHDRAWN: {protocol_id} {WITHDRAWN_PROTOCOLS[protocol_id]}")
    if require_pinned_digest:
        pinned = PINNED_PROTOCOLS.get(protocol_id)
        if pinned is None:
            raise SecondCaseError(
                f"SECONDCASE_PROTOCOL_NOT_FROZEN: {protocol_id} has no pinned digest yet"
            )
        if digest != pinned:
            raise SecondCaseError(f"SECONDCASE_PROTOCOL_DIGEST_MISMATCH: {digest} != pinned {pinned}")
    return protocol


def _range_overlaps(seeds: list[int], ranges: dict[str, Any]) -> list[str]:
    hits = []
    for name, bounds in ranges.items():
        lo, hi = _lst(bounds, f"forbidden_seed_ranges.{name}")
        lo = _int(lo, name)
        hi = _int(hi, name)
        if any(lo <= seed <= hi for seed in seeds):
            hits.append(name)
    return hits


def validate_protocol(protocol: dict[str, Any]) -> dict[str, Any]:
    """Return the frozen design or raise.  Every constant the analysis uses comes from here."""
    _exact_keys(protocol, PROTOCOL_FIELDS, "protocol")
    schema = protocol["schema_version"]
    if schema not in PROTOCOL_SCHEMAS:
        raise SecondCaseError("protocol schema_version mismatch")
    protocol_id = protocol["protocol_id"]
    if protocol_id not in PINNED_PROTOCOLS:
        raise SecondCaseError("protocol_id mismatch")
    if (schema == PROTOCOL_SCHEMA) != (protocol_id == PROTOCOL_ID):
        raise SecondCaseError("protocol schema_version and protocol_id disagree about the version")
    if protocol["publication_gate"] != PUBLICATION_GATE:
        raise SecondCaseError("publication_gate mismatch")

    prereg = _obj(protocol["preregistration"], "preregistration")
    if _bool(prereg.get("preregistered"), "preregistration.preregistered") is not False:
        raise SecondCaseError("this protocol must declare preregistered=false")
    if _bool(prereg.get("internally_frozen_before_execution"), "preregistration.internally_frozen_before_execution") is not True:
        raise SecondCaseError("protocol must declare internally_frozen_before_execution=true")
    _str(prereg.get("disclosure"), "preregistration.disclosure")

    arms = _lst(protocol["arms"], "arms")
    if len(arms) != 2:
        raise SecondCaseError("exactly two arms are frozen")
    roles = {}
    alphas = {}
    for index, arm in enumerate(arms):
        arm = _obj(arm, f"arms[{index}]")
        arm_id = _str(arm.get("arm_id"), f"arms[{index}].arm_id")
        role = _str(arm.get("role"), f"arms[{index}].role", allowed=("REFERENCE", "CANDIDATE"))
        alpha = _num(arm.get("low_pass_alpha"), f"arms[{index}].low_pass_alpha")
        if not (0.0 < alpha <= 1.0):
            raise SecondCaseError("low_pass_alpha must lie in (0, 1]")
        roles[role] = arm_id
        alphas[arm_id] = alpha
    if set(roles) != {"REFERENCE", "CANDIDATE"}:
        raise SecondCaseError("arms must carry one REFERENCE and one CANDIDATE role")
    if alphas[roles["REFERENCE"]] != 1.0:
        raise SecondCaseError("the reference arm must be the identity filter (alpha = 1.0)")

    env = _obj(protocol["environment"], "environment")
    horizon = _int(env.get("horizon_control_steps"), "environment.horizon_control_steps", minimum=1)
    if horizon != _int(env.get("max_episode_steps"), "environment.max_episode_steps"):
        raise SecondCaseError("horizon must equal max_episode_steps")
    joints = _int(env.get("action_dim"), "environment.action_dim", minimum=1)
    _sha(env.get("plant_asset_sha256"), "environment.plant_asset_sha256")
    if _obj(env.get("gymnasium_make_kwargs"), "environment.gymnasium_make_kwargs"):
        raise SecondCaseError("gymnasium_make_kwargs must be empty: defaults are the point")

    measurement = _obj(protocol["primary_measurement"], "primary_measurement")
    horizon_units = _int(measurement.get("horizon_total_units"), "primary_measurement.horizon_total_units", minimum=1)
    if horizon_units != horizon * joints:
        raise SecondCaseError("horizon_total_units must equal horizon x joints")

    training = _obj(protocol["training"], "training")
    replicate_count = _int(training.get("replicate_count"), "training.replicate_count", minimum=2)
    seed_base = _int(training.get("training_seed_base"), "training.training_seed_base", minimum=0)
    training_seeds = [_int(s, "training.training_seeds[]") for s in _lst(training.get("training_seeds"), "training.training_seeds")]
    if training_seeds != list(range(seed_base, seed_base + replicate_count)):
        raise SecondCaseError("training_seeds must be base .. base + replicate_count - 1")
    requested = _int(training.get("requested_timesteps"), "training.requested_timesteps", minimum=1)
    expected_realized = _int(training.get("expected_realized_timesteps"), "training.expected_realized_timesteps", minimum=1)
    if requested != expected_realized:
        raise SecondCaseError("requested_timesteps must equal expected_realized_timesteps")
    hyper = _obj(training.get("hyperparameters"), "training.hyperparameters")
    n_steps = _int(hyper.get("n_steps"), "training.hyperparameters.n_steps", minimum=1)
    parallel = _int(training.get("parallel_envs"), "training.parallel_envs", minimum=1)
    if requested % (n_steps * parallel) != 0:
        raise SecondCaseError("requested_timesteps must be a whole number of rollouts")
    if training.get("warm_start") is not None:
        raise SecondCaseError("warm_start must be null: this line is from scratch")
    if training.get("device") != "cpu":
        raise SecondCaseError("device must be cpu")
    normalize_spec = training.get("normalize")
    if normalize_spec is not None:
        normalize_spec = _obj(normalize_spec, "training.normalize")
        for key in ("norm_obs", "norm_reward"):
            _bool(normalize_spec.get(key), f"training.normalize.{key}")
        _num(normalize_spec.get("clip_obs"), "training.normalize.clip_obs")
    policy_spec = training.get("policy_kwargs")
    if policy_spec is not None:
        policy_spec = _obj(policy_spec, "training.policy_kwargs")
        _num(policy_spec.get("log_std_init"), "training.policy_kwargs.log_std_init")
        _bool(policy_spec.get("ortho_init"), "training.policy_kwargs.ortho_init")
        _str(policy_spec.get("activation_fn"), "training.policy_kwargs.activation_fn", allowed=("Tanh", "ReLU"))
        arch = _obj(policy_spec.get("net_arch"), "training.policy_kwargs.net_arch")
        for side in ("pi", "vf"):
            for width in _lst(arch.get(side), f"training.policy_kwargs.net_arch.{side}"):
                _int(width, "net_arch width", minimum=1)
    if schema == PROTOCOL_SCHEMA and (normalize_spec is not None or policy_spec is not None):
        raise SecondCaseError("normalize / policy_kwargs are recipe fields for V2 protocols only")

    evaluation = _obj(protocol["evaluation"], "evaluation")
    seed_first = _int(evaluation.get("evaluation_seed_first"), "evaluation.evaluation_seed_first", minimum=0)
    seed_last = _int(evaluation.get("evaluation_seed_last"), "evaluation.evaluation_seed_last", minimum=seed_first)
    per_cell = _int(evaluation.get("evaluation_seeds_per_cell"), "evaluation.evaluation_seeds_per_cell", minimum=1)
    evaluation_seeds = list(range(seed_first, seed_last + 1))
    if len(evaluation_seeds) != per_cell:
        raise SecondCaseError("evaluation seed range length must equal evaluation_seeds_per_cell")
    if _bool(evaluation.get("deterministic_policy"), "evaluation.deterministic_policy") is not True:
        raise SecondCaseError("evaluation must use the deterministic policy")
    threshold = _num(evaluation.get("saturation_threshold_abs_applied_action"), "evaluation.saturation_threshold_abs_applied_action")
    if not (0.0 < threshold <= 1.0):
        raise SecondCaseError("saturation threshold must lie in (0, 1]")

    forbidden_ranges = _obj(protocol["forbidden_seed_ranges"], "forbidden_seed_ranges")
    hits = _range_overlaps(training_seeds + evaluation_seeds, forbidden_ranges)
    if hits:
        raise SecondCaseError(f"seeds overlap forbidden ranges: {hits}")
    if set(training_seeds) & set(evaluation_seeds):
        raise SecondCaseError("training and evaluation seeds must be disjoint")

    analysis = _obj(protocol["analysis"], "analysis")
    if analysis.get("analysis_unit") != "TRAINING_REPLICATE":
        raise SecondCaseError("analysis_unit must be TRAINING_REPLICATE")
    denominator = _int(analysis.get("method_level_denominator"), "analysis.method_level_denominator", minimum=2)
    if denominator != replicate_count:
        raise SecondCaseError("method_level_denominator must equal replicate_count")
    forbidden_denominators = tuple(_int(d, "analysis.forbidden_denominators[]") for d in _lst(analysis.get("forbidden_denominators"), "analysis.forbidden_denominators"))
    if denominator in forbidden_denominators:
        raise SecondCaseError("replicate_count cannot be a forbidden denominator")
    if per_cell not in forbidden_denominators or per_cell * replicate_count not in forbidden_denominators:
        raise SecondCaseError("episode counts per cell and per arm must be forbidden denominators")
    if analysis.get("complete_case_deletion") != "FORBIDDEN" or analysis.get("interval_imputation") != "FORBIDDEN":
        raise SecondCaseError("complete-case deletion and interval imputation must be FORBIDDEN")
    naive_rule = _obj(analysis.get("naive_reporting_criterion"), "analysis.naive_reporting_criterion")
    t_critical = _num(naive_rule.get("t_critical_df4_two_sided_95"), "analysis.naive_reporting_criterion.t_critical_df4_two_sided_95")

    predictions = _obj(protocol["predictions"], "predictions")
    labels = _lst(predictions.get("outcome_labels"), "predictions.outcome_labels")
    expected_labels = OUTCOME_LABELS if schema == PROTOCOL_SCHEMA else OUTCOME_LABELS_V2
    if tuple(labels) != expected_labels:
        raise SecondCaseError("predictions.outcome_labels must equal the contract's labels for this schema, in order")
    _str(predictions.get("no_direction_prediction"), "predictions.no_direction_prediction")
    p1 = _obj(predictions.get("P1_censoring_present"), "predictions.P1_censoring_present")
    _str(p1.get("statement"), "P1.statement")
    p1_scope = p1.get("arm_scope", P1_SCOPE_ANY)
    if p1_scope not in (P1_SCOPE_ANY, P1_SCOPE_CANDIDATE):
        raise SecondCaseError("P1.arm_scope must be ANY_ARM or CANDIDATE_ARM")
    reference_adequacy: dict[str, int] | None = None
    if schema == PROTOCOL_SCHEMA_V2:
        p0 = _obj(predictions.get("P0_reference_adequacy"), "predictions.P0_reference_adequacy")
        _str(p0.get("statement"), "P0.statement")
        min_full = _int(p0.get("minimum_full_exposure_episodes"), "P0.minimum_full_exposure_episodes", minimum=1)
        min_reps = _int(p0.get("minimum_adequate_replicates"), "P0.minimum_adequate_replicates", minimum=1)
        if min_full > per_cell or min_reps > replicate_count:
            raise SecondCaseError("P0 thresholds exceed the design")
        if p1_scope != P1_SCOPE_CANDIDATE:
            raise SecondCaseError("a V2 protocol must scope P1 to the candidate arm")
        reference_adequacy = {
            "minimum_full_exposure_episodes": min_full,
            "minimum_adequate_replicates": min_reps,
        }
    elif "P0_reference_adequacy" in predictions:
        raise SecondCaseError("P0_reference_adequacy is a V2 field")

    requirement = _obj(protocol["environment_lock_requirement"], "environment_lock_requirement")
    if requirement.get("required_lock_class") != MEASURED_LOCK_CLASS:
        raise SecondCaseError("required_lock_class must be MEASURED_ENVIRONMENT_LOCK")
    if requirement.get("required_lock_completeness") != FULL_LOCK:
        raise SecondCaseError("required_lock_completeness must be FULL_LOCK")
    if requirement.get("required_threading_determinism") != THREADING_PINNED:
        raise SecondCaseError("required_threading_determinism must be AMBIENT_THREADING_PINNED")

    source = _obj(protocol["source_requirement"], "source_requirement")
    if source.get("clean_git_required") is not True:
        raise SecondCaseError("clean_git_required must be true")

    return {
        "protocol_id": protocol_id,
        "schema_version": schema,
        "normalize": normalize_spec,
        "policy_kwargs": policy_spec,
        "p1_arm_scope": p1_scope,
        "reference_adequacy": reference_adequacy,
        "reference_arm_id": roles["REFERENCE"],
        "candidate_arm_id": roles["CANDIDATE"],
        "arm_ids": (roles["REFERENCE"], roles["CANDIDATE"]),
        "alphas": alphas,
        "horizon_steps": horizon,
        "joints": joints,
        "horizon_units": horizon_units,
        "replicate_count": replicate_count,
        "training_seeds": training_seeds,
        "evaluation_seeds": evaluation_seeds,
        "expected_realized_timesteps": expected_realized,
        "saturation_threshold": threshold,
        "forbidden_denominators": forbidden_denominators,
        "t_critical": t_critical,
        "p1_minimum_censored_replicates": 3,
        "plant_asset_sha256": env["plant_asset_sha256"],
        "lock_requirement": requirement,
    }


# --------------------------------------------------------------------------- #
# canonical episode rows
# --------------------------------------------------------------------------- #


def episode_row(
    *,
    evaluation_seed: int,
    realized_steps: int,
    saturated_joint_steps: int,
    terminated: bool,
    truncated: bool,
    all_finite: bool,
    episode_return: float | None,
    trace_sha256: str,
    design: dict[str, Any],
) -> dict[str, Any]:
    """Build one canonical row.  Exposure comes from trace length, never from a flag."""
    horizon = design["horizon_steps"]
    joints = design["joints"]
    realized_steps = _int(realized_steps, "realized_steps", minimum=1)
    if realized_steps > horizon:
        raise SecondCaseError("SECONDCASE_TRACE_INCONSISTENT: realized steps exceed the horizon")
    saturated_joint_steps = _int(saturated_joint_steps, "saturated_joint_steps", minimum=0)
    if saturated_joint_steps > realized_steps * joints:
        raise SecondCaseError("SECONDCASE_TRACE_INCONSISTENT: saturated pairs exceed observed pairs")
    terminated = _bool(terminated, "terminated")
    truncated = _bool(truncated, "truncated")
    if realized_steps < horizon and not terminated:
        raise SecondCaseError(
            "SECONDCASE_TRACE_INCONSISTENT: an episode shorter than the horizon must have terminated"
        )
    if realized_steps == horizon and not (terminated or truncated):
        raise SecondCaseError(
            "SECONDCASE_TRACE_INCONSISTENT: a full-horizon episode must end by truncation or termination"
        )
    all_finite = _bool(all_finite, "all_finite")
    outcome_state = OUTCOME_OBSERVED if all_finite else OUTCOME_NONFINITE
    observed_units = realized_steps * joints
    bound = ei.episode_bound_pct(saturated_joint_steps, observed_units, design["horizon_units"])
    naive = ei.naive_rate_pct(saturated_joint_steps, observed_units)
    if outcome_state == OUTCOME_OBSERVED:
        comparability = COMPARABLE if bound["exposure_class"] == ei.EXPOSURE_FULL else EXPOSURE_CENSORED
    else:
        comparability = METHOD_FAILURE
    if episode_return is not None:
        episode_return = round(_num(episode_return, "episode_return"), 6)
    return {
        "all_finite": all_finite,
        "comparability_state": comparability,
        "episode_return": episode_return,
        "evaluation_seed": _int(evaluation_seed, "evaluation_seed", minimum=0),
        "exposure_class": bound["exposure_class"],
        "full_horizon_duty_bound_pct": {
            "lower_pct": bound["lower_pct"],
            "upper_pct": bound["upper_pct"],
            "width_pct": bound["width_pct"],
            "point_identified": bound["point_identified"],
        },
        "naive_duty_pct": naive,
        "outcome_state": outcome_state,
        "realized_steps": realized_steps,
        "saturated_joint_steps": saturated_joint_steps,
        "terminated": terminated,
        "trace_sha256": _sha(trace_sha256, "trace_sha256"),
        "truncated": truncated,
    }


def _validate_episode(row: Any, expected_seed: int, design: dict[str, Any], context: str) -> dict[str, Any]:
    row = _obj(row, context)
    _exact_keys(row, EPISODE_FIELDS, context)
    if row["evaluation_seed"] != expected_seed:
        raise SecondCaseError(f"{context} evaluation_seed {row['evaluation_seed']} != expected {expected_seed}")
    recomputed = episode_row(
        evaluation_seed=row["evaluation_seed"],
        realized_steps=row["realized_steps"],
        saturated_joint_steps=row["saturated_joint_steps"],
        terminated=row["terminated"],
        truncated=row["truncated"],
        all_finite=row["all_finite"],
        episode_return=row["episode_return"],
        trace_sha256=row["trace_sha256"],
        design=design,
    )
    if recomputed != row:
        raise SecondCaseError(f"{context} does not reproduce from its own counts (SC-03)")
    return row


# --------------------------------------------------------------------------- #
# raw bundle
# --------------------------------------------------------------------------- #


def check_environment_lock(design: dict[str, Any], record: Any) -> dict[str, Any]:
    requirement = design["lock_requirement"]
    try:
        validation = validate_lock_record(record)
    except EnvironmentLockError as exc:
        raise SecondCaseError(f"environment lock record is invalid: {exc}") from exc
    for key, field in (
        ("required_lock_class", "lock_class"),
        ("required_lock_completeness", "lock_completeness"),
        ("required_threading_determinism", "threading_determinism"),
    ):
        if validation[field] != requirement[key]:
            raise SecondCaseError(
                f"environment lock {field} {validation[field]!r} does not meet {requirement[key]!r}"
            )
    return {
        "environment_lock_class": validation["lock_class"],
        "environment_lock_completeness": validation["lock_completeness"],
        "environment_lock_threading": validation["threading_determinism"],
        "environment_locked_sha256": validation["locked_sha256"],
    }


def _validate_cell(cell: Any, design: dict[str, Any], expected_arm: str, context: str) -> dict[str, Any]:
    cell = _obj(cell, context)
    is_v2 = design["schema_version"] == PROTOCOL_SCHEMA_V2
    _exact_keys(cell, CELL_FIELDS_V2 if is_v2 else CELL_FIELDS, context)
    if cell["schema_version"] != (CELL_SCHEMA_V2 if is_v2 else CELL_SCHEMA):
        raise SecondCaseError(f"{context} schema_version mismatch")
    if is_v2:
        normalized = bool(design.get("normalize"))
        if cell["normalizer_sha256"] is not None:
            _sha(cell["normalizer_sha256"], f"{context}.normalizer_sha256")
        if normalized and cell["training_terminal_state"] == "COMPLETED" and cell["normalizer_sha256"] is None:
            raise SecondCaseError(f"{context} recipe normalizes but no normalizer digest was recorded")
        if not normalized and cell["normalizer_sha256"] is not None:
            raise SecondCaseError(f"{context} records a normalizer the recipe does not use")
    if cell["arm_id"] != expected_arm:
        raise SecondCaseError(f"{context} arm_id {cell['arm_id']} != expected {expected_arm}")
    if _num(cell["low_pass_alpha"], f"{context}.low_pass_alpha") != design["alphas"][expected_arm]:
        raise SecondCaseError(f"{context} low_pass_alpha does not match the frozen arm")
    training_state = _str(cell["training_terminal_state"], f"{context}.training_terminal_state", allowed=TERMINAL_STATES)
    evaluation_state = _str(cell["evaluation_terminal_state"], f"{context}.evaluation_terminal_state", allowed=TERMINAL_STATES)
    realized = _int(cell["realized_timesteps"], f"{context}.realized_timesteps", minimum=0)
    if training_state == "COMPLETED" and realized != design["expected_realized_timesteps"]:
        raise SecondCaseError(
            f"{context} realized_timesteps {realized} != frozen {design['expected_realized_timesteps']}"
        )
    for flag in ("training_environment_lock_verified", "evaluation_environment_lock_verified"):
        if _bool(cell[flag], f"{context}.{flag}") is not True:
            raise SecondCaseError(f"{context}.{flag} must be true")
    _sha(cell["environment_locked_sha256"], f"{context}.environment_locked_sha256")
    if cell["policy_sha256"] is not None:
        _sha(cell["policy_sha256"], f"{context}.policy_sha256")
    elif training_state == "COMPLETED":
        raise SecondCaseError(f"{context} completed training must record policy_sha256")
    episodes = _lst(cell["episodes"], f"{context}.episodes")
    if training_state == "COMPLETED" and evaluation_state == "COMPLETED":
        if len(episodes) != len(design["evaluation_seeds"]):
            raise SecondCaseError(f"{context} must hold exactly {len(design['evaluation_seeds'])} episodes")
    validated = []
    for index, row in enumerate(episodes):
        if index >= len(design["evaluation_seeds"]):
            raise SecondCaseError(f"{context} holds more episodes than evaluation seeds")
        validated.append(_validate_episode(row, design["evaluation_seeds"][index], design, f"{context}.episodes[{index}]"))
    expected_output_sha = sha256_bytes(json_bytes(validated))
    if cell["evaluation_output_sha256"] != expected_output_sha:
        raise SecondCaseError(f"{context} evaluation_output_sha256 does not match its episode rows")
    return cell


def validate_raw_bundle(raw: Any, protocol: dict[str, Any]) -> dict[str, Any]:
    design = validate_protocol(protocol)
    raw = _obj(raw, "raw")
    _exact_keys(raw, RAW_FIELDS, "raw")
    if raw["schema_version"] != RAW_SCHEMA:
        raise SecondCaseError("raw schema_version mismatch")
    if raw["protocol_id"] != design["protocol_id"]:
        raise SecondCaseError("raw protocol_id mismatch")
    bundle_class = _str(raw["bundle_class"], "raw.bundle_class", allowed=BUNDLE_CLASSES)
    _sha(raw["protocol_sha256"], "raw.protocol_sha256")
    if bundle_class == DEVELOPMENT_BUNDLE_CLASS and raw["protocol_sha256"] != PINNED_PROTOCOLS.get(design["protocol_id"]):
        raise SecondCaseError("development bundle must bind the pinned protocol digest")
    _sha(raw["environment_lock_sha256"], "raw.environment_lock_sha256")
    if _sha(raw["plant_asset_sha256"], "raw.plant_asset_sha256") != design["plant_asset_sha256"]:
        raise SecondCaseError("raw.plant_asset_sha256 does not match the frozen plant")
    for key in ("source_git_sha_pre", "source_git_sha_post"):
        if not GIT_PATTERN.match(_str(raw[key], f"raw.{key}")):
            raise SecondCaseError(f"raw.{key} must be a 40-hex git sha")
    if raw["source_git_sha_pre"] != raw["source_git_sha_post"]:
        raise SecondCaseError("source changed during execution")
    if _bool(raw["source_dirty_pre"], "raw.source_dirty_pre") or _bool(raw["source_dirty_post"], "raw.source_dirty_post"):
        raise SecondCaseError("SECONDCASE_SOURCE_GIT_NOT_CLEAN")
    replicates = _lst(raw["replicates"], "raw.replicates")
    if len(replicates) != design["replicate_count"]:
        raise SecondCaseError(f"raw.replicates must hold exactly {design['replicate_count']} replicates")
    total_records = 0
    for index, replicate in enumerate(replicates):
        context = f"raw.replicates[{index}]"
        replicate = _obj(replicate, context)
        _exact_keys(replicate, REPLICATE_FIELDS, context)
        if replicate["replicate_index"] != index:
            raise SecondCaseError(f"{context} replicate_index must be {index}")
        if replicate["training_seed"] != design["training_seeds"][index]:
            raise SecondCaseError(f"{context} training_seed mismatch")
        arms = _lst(replicate["arms"], f"{context}.arms")
        if len(arms) != 2:
            raise SecondCaseError(f"{context} must hold exactly two arms")
        for arm_index, expected_arm in enumerate(design["arm_ids"]):
            cell = _validate_cell(arms[arm_index], design, expected_arm, f"{context}.arms[{arm_index}]")
            total_records += len(cell["episodes"])
    return {"design": design, "terminal_record_count": total_records, "bundle_class": bundle_class}


# --------------------------------------------------------------------------- #
# summary
# --------------------------------------------------------------------------- #


def _cell_summary(cell: dict[str, Any], design: dict[str, Any]) -> dict[str, Any]:
    episodes = cell["episodes"]
    exposure_counts = {klass: 0 for klass in (ei.EXPOSURE_FULL, ei.EXPOSURE_EARLY, ei.EXPOSURE_NONE)}
    outcome_counts = {OUTCOME_OBSERVED: 0, OUTCOME_NONFINITE: 0}
    comparability_counts = {COMPARABLE: 0, EXPOSURE_CENSORED: 0, METHOD_FAILURE: 0}
    early_observed = 0
    for row in episodes:
        exposure_counts[row["exposure_class"]] += 1
        outcome_counts[row["outcome_state"]] += 1
        comparability_counts[row["comparability_state"]] += 1
        if row["exposure_class"] != ei.EXPOSURE_FULL and row["outcome_state"] == OUTCOME_OBSERVED:
            early_observed += 1
    method_failure = (
        cell["training_terminal_state"] != "COMPLETED"
        or cell["evaluation_terminal_state"] != "COMPLETED"
        or comparability_counts[METHOD_FAILURE] > 0
        or len(episodes) != len(design["evaluation_seeds"])
    )
    base = {
        "arm_id": cell["arm_id"],
        "low_pass_alpha": cell["low_pass_alpha"],
        "realized_timesteps": cell["realized_timesteps"],
        "training_terminal_state": cell["training_terminal_state"],
        "evaluation_terminal_state": cell["evaluation_terminal_state"],
        "episode_count": len(episodes),
        "exposure_counts": exposure_counts,
        "outcome_counts": outcome_counts,
        "comparability_counts": comparability_counts,
        "early_terminated_with_observed_outcome": early_observed,
        "evaluation_output_sha256": cell["evaluation_output_sha256"],
    }
    if method_failure:
        base.update(
            {
                "cell_state": CELL_BLOCKED,
                "mean_bound_pct": None,
                "naive_mean_duty_pct": None,
                "level_sd_pct": None,
                "level_sd_reason": "CELL_CONTAINS_METHOD_FAILURE_NO_MEAN_DEFINED",
            }
        )
        return base
    bounds = [
        {
            "lower_pct": row["full_horizon_duty_bound_pct"]["lower_pct"],
            "upper_pct": row["full_horizon_duty_bound_pct"]["upper_pct"],
            "point_identified": row["full_horizon_duty_bound_pct"]["point_identified"],
        }
        for row in episodes
    ]
    aggregate = ei.aggregate_bounds(bounds)
    naive_mean = ei.round_percent(ei.ordered_mean([float(row["naive_duty_pct"]) for row in episodes]))
    base.update(
        {
            "cell_state": CELL_POINT if aggregate["point_identified"] else CELL_PARTIAL,
            "mean_bound_pct": {
                "lower_pct": aggregate["lower_pct"],
                "upper_pct": aggregate["upper_pct"],
                "width_pct": aggregate["width_pct"],
                "point_identified": aggregate["point_identified"],
            },
            "naive_mean_duty_pct": naive_mean,
            "level_sd_pct": aggregate["level_sd_pct"],
            "level_sd_reason": aggregate["level_sd_reason"],
        }
    )
    return base


def _null_difference(reason: str) -> dict[str, Any]:
    return {
        "lower_pp": None,
        "upper_pp": None,
        "width_pp": None,
        "point_identified": False,
        "sign": "NULL",
        "reason": reason,
    }


def build_summary(raw: dict[str, Any], protocol: dict[str, Any]) -> dict[str, Any]:
    validation = validate_raw_bundle(raw, protocol)
    design = validation["design"]
    reference_id = design["reference_arm_id"]
    candidate_id = design["candidate_arm_id"]

    replicate_summaries = []
    bound_differences: list[dict[str, Any] | None] = []
    naive_differences: list[float | None] = []
    censored_replicates = 0
    adequate_reference_replicates = 0
    blocked_replicates = []
    early_total = 0
    early_observed_total = 0
    per_cell = len(design["evaluation_seeds"])
    adequacy = design["reference_adequacy"]
    is_v2 = adequacy is not None

    for replicate in raw["replicates"]:
        cells = {cell["arm_id"]: _cell_summary(cell, design) for cell in replicate["arms"]}
        reference = cells[reference_id]
        candidate = cells[candidate_id]
        for cell in cells.values():
            early_total += cell["exposure_counts"][ei.EXPOSURE_EARLY] + cell["exposure_counts"][ei.EXPOSURE_NONE]
            early_observed_total += cell["early_terminated_with_observed_outcome"]
        any_censored = any(
            cell["exposure_counts"][ei.EXPOSURE_FULL] < len(design["evaluation_seeds"]) for cell in cells.values()
        )
        candidate_censored = candidate["exposure_counts"][ei.EXPOSURE_FULL] < per_cell
        censored_here = candidate_censored if design["p1_arm_scope"] == P1_SCOPE_CANDIDATE else any_censored
        reference_adequate = (
            None if not is_v2 else reference["exposure_counts"][ei.EXPOSURE_FULL] >= adequacy["minimum_full_exposure_episodes"]
        )
        blocked = reference["cell_state"] == CELL_BLOCKED or candidate["cell_state"] == CELL_BLOCKED
        if blocked:
            blocked_replicates.append(replicate["replicate_index"])
            difference = _null_difference("BLOCKED_METHOD_FAILURE_IN_PAIRED_CELL")
            naive_difference = None
            bound_differences.append(None)
            naive_differences.append(None)
        else:
            if censored_here:
                censored_replicates += 1
            if reference_adequate:
                adequate_reference_replicates += 1
            difference = ei.paired_difference_pp(candidate["mean_bound_pct"], reference["mean_bound_pct"])
            difference["reason"] = None
            naive_difference = ei.round_percent(candidate["naive_mean_duty_pct"] - reference["naive_mean_duty_pct"])
            bound_differences.append(difference)
            naive_differences.append(naive_difference)
        naive_sign = (
            None if naive_difference is None else ei.SIGN_NEGATIVE if naive_difference < 0.0 else ei.SIGN_POSITIVE if naive_difference > 0.0 else "ZERO"
        )
        entry = {
            "replicate_index": replicate["replicate_index"],
            "training_seed": replicate["training_seed"],
            "arms": [cells[reference_id], cells[candidate_id]],
            "any_arm_censored": any_censored,
            "paired_difference_bound_pp": difference,
            "naive_paired_difference_pp": naive_difference,
            "naive_sign": naive_sign,
            "naive_and_bound_sign_agree": (
                None if naive_difference is None else difference["sign"] == naive_sign
            ),
        }
        if is_v2:
            entry["candidate_censored"] = candidate_censored
            entry["reference_adequate"] = reference_adequate
        replicate_summaries.append(entry)

    p1_holds = censored_replicates >= design["p1_minimum_censored_replicates"]
    p0_holds = None if not is_v2 else adequate_reference_replicates >= adequacy["minimum_adequate_replicates"]
    retained_blockers: list[dict[str, Any]] = []
    method_level: dict[str, Any] | None = None
    naive_method_level: dict[str, Any] | None = None
    comparison: dict[str, Any] | None = None

    if blocked_replicates:
        outcome = OUTCOME_BLOCKED
        retained_blockers.append(
            {
                "blocker_id": "METHOD_FAILURE_BLOCKS_METHOD_LEVEL",
                "replicate_indices": blocked_replicates,
                "detail": "Paired differences are NULL for these replicates; the denominator stays "
                f"{design['replicate_count']} and no method-level decision is issued.",
            }
        )
    else:
        differences = [item for item in bound_differences if item is not None]
        method_level = ei.method_level_pp(
            differences,
            expected_denominator=design["replicate_count"],
            forbidden_denominators=design["forbidden_denominators"],
        )
        naive_method_level = ei.naive_method_level_pp(
            [float(item) for item in naive_differences if item is not None],
            t_critical=design["t_critical"],
            expected_denominator=design["replicate_count"],
            forbidden_denominators=design["forbidden_denominators"],
        )
        comparison = ei.compare_naive_to_bound(naive_method_level, method_level)
        if is_v2 and not p0_holds:
            # The V1 lesson: with a censored reference the bound contains zero by
            # construction, so P1/P2 would be decided by the reference, not the estimator.
            outcome = OUTCOME_REFERENCE_NOT_ADEQUATE
            retained_blockers.append(
                {
                    "blocker_id": "P0_FAILED_REFERENCE_NOT_ADEQUATE",
                    "adequate_reference_replicates": adequate_reference_replicates,
                    "required": adequacy["minimum_adequate_replicates"],
                    "detail": "The reference arm did not reach the frozen full-exposure fraction in enough "
                    "replicates; the paired bound is wide because of the reference, so no artifact "
                    "decision is issued.",
                }
            )
        elif not p1_holds:
            outcome = OUTCOME_UNINFORMATIVE
            retained_blockers.append(
                {
                    "blocker_id": "P1_FAILED_NO_CENSORING",
                    "censored_replicates": censored_replicates,
                    "detail": "Fewer than the frozen minimum of replicates show any early termination; "
                    "the bound equals the naive value and the case cannot speak to the artifact.",
                }
            )
        elif comparison["outcome"] == "NAIVE_ASSERTS_DIRECTION_BOUND_CONTAINS_ZERO":
            outcome = OUTCOME_REPRODUCED
        elif comparison["outcome"] == "BOUND_IDENTIFIED_NAIVE_UNCERTAIN":
            outcome = OUTCOME_BOUND_ONLY
        else:
            outcome = OUTCOME_AGREE
            if comparison["outcome"] == "BOTH_IDENTIFIED_OPPOSITE_SIGN":
                # Impossible if the naive mean lies inside the bound; record rather than trust.
                retained_blockers.append(
                    {
                        "blocker_id": "NAIVE_OUTSIDE_BOUND_ARITHMETIC_INCONSISTENCY",
                        "detail": "Naive and bound identified opposite signs; the naive mean should lie inside the bound.",
                    }
                )
    if method_level is not None and method_level["between_replicate_sd_pp"] is None:
        retained_blockers.append(
            {
                "blocker_id": "BETWEEN_REPLICATE_SD_NOT_IDENTIFIED",
                "detail": method_level["between_replicate_sd_reason"],
            }
        )
    if outcome not in (OUTCOME_LABELS_V2 if is_v2 else OUTCOME_LABELS):
        raise SecondCaseError("outcome label outside the frozen set")

    v2_keys: dict[str, Any] = {}
    if is_v2:
        v2_keys = {
            "p0_reference_adequacy": {
                "holds": p0_holds,
                "adequate_reference_replicate_count": adequate_reference_replicates,
                "minimum_full_exposure_episodes": adequacy["minimum_full_exposure_episodes"],
                "minimum_adequate_replicates": adequacy["minimum_adequate_replicates"],
            },
            "p1_arm_scope": design["p1_arm_scope"],
        }
    return {
        **v2_keys,
        "schema_version": SUMMARY_SCHEMA_V2 if is_v2 else SUMMARY_SCHEMA,
        "protocol_id": raw["protocol_id"],
        "protocol_sha256": raw["protocol_sha256"],
        "publication_gate": PUBLICATION_GATE,
        "bundle_class": raw["bundle_class"],
        "environment_lock_sha256": raw["environment_lock_sha256"],
        "plant_asset_sha256": raw["plant_asset_sha256"],
        "source_git_sha_pre": raw["source_git_sha_pre"],
        "source_git_sha_post": raw["source_git_sha_post"],
        "analysis_unit": "TRAINING_REPLICATE",
        "replicate_count": design["replicate_count"],
        "training_seeds": design["training_seeds"],
        "evaluation_seed_first": design["evaluation_seeds"][0],
        "evaluation_seed_last": design["evaluation_seeds"][-1],
        "terminal_record_count": validation["terminal_record_count"],
        "forbidden_denominators": list(design["forbidden_denominators"]),
        "reference_arm_id": reference_id,
        "candidate_arm_id": candidate_id,
        "contrast": f"{candidate_id} minus {reference_id}",
        "replicates": replicate_summaries,
        "censored_replicate_count": censored_replicates,
        "p1_censoring_present": p1_holds,
        "p3_early_terminated_episodes": early_total,
        "p3_early_terminated_with_observed_outcome": early_observed_total,
        "p3_observed_does_not_imply_full_exposure": early_total > 0 and early_observed_total == early_total,
        "method_level_bound": method_level,
        "naive_method_level": naive_method_level,
        "naive_versus_bound": comparison,
        "outcome": outcome,
        "retained_blockers": retained_blockers,
        "direction_claim_permitted": False,
        "selection_permitted": False,
        "preregistered": False,
        "paper_data_ready": False,
        "claim_boundary": list(CLAIM_BOUNDARY),
    }


# --------------------------------------------------------------------------- #
# bundle io, analysis, replay
# --------------------------------------------------------------------------- #


def read_bundle(bundle_root: Path) -> dict[str, Any]:
    bundle_root = Path(bundle_root).resolve()
    raw_path = bundle_root / "raw_replicates.json"
    protocol_path = bundle_root / "second_case_exposure_protocol.json"
    lock_path = bundle_root / "environment_lock.json"
    for path in (raw_path, protocol_path, lock_path):
        if not path.is_file():
            raise SecondCaseError(f"bundle is missing {path.name}")
    raw = _obj(load_json_file(raw_path), "raw")
    protocol_bytes = protocol_path.read_bytes()
    protocol = _obj(load_json_bytes(protocol_bytes, str(protocol_path)), "protocol")
    protocol_sha = sha256_bytes(protocol_bytes)
    if raw.get("protocol_sha256") != protocol_sha:
        raise SecondCaseError("raw.protocol_sha256 does not match the protocol copy in the bundle")
    lock_bytes = lock_path.read_bytes()
    if raw.get("environment_lock_sha256") != sha256_bytes(lock_bytes):
        raise SecondCaseError("raw.environment_lock_sha256 does not match the lock record in the bundle")
    return {
        "root": bundle_root,
        "raw": raw,
        "protocol": protocol,
        "protocol_sha256": protocol_sha,
        "lock_record": load_json_bytes(lock_bytes, str(lock_path)),
        "files": {
            "raw_replicates.json": sha256_file(raw_path),
            "second_case_exposure_protocol.json": protocol_sha,
            "environment_lock.json": sha256_bytes(lock_bytes),
        },
    }


def analyse(bundle_root: Path, output_root: Path) -> dict[str, Any]:
    bundle = read_bundle(bundle_root)
    output_root = Path(output_root).resolve()
    try:
        output_root.relative_to(bundle["root"])
    except ValueError:
        pass
    else:
        raise SecondCaseError("output_root must not lie inside the bundle (the bundle is read-only)")
    design = validate_protocol(bundle["protocol"])
    if bundle["raw"]["bundle_class"] == DEVELOPMENT_BUNDLE_CLASS and bundle["protocol_sha256"] != PINNED_PROTOCOLS.get(design["protocol_id"]):
        raise SecondCaseError("development bundle protocol copy is not the pinned protocol")
    lock = check_environment_lock(design, bundle["lock_record"])
    summary = build_summary(bundle["raw"], bundle["protocol"])
    output_root.mkdir(parents=True, exist_ok=True)
    summary_bytes = json_bytes(summary)
    summary_path = output_root / "second_case_summary.json"
    summary_path.write_bytes(summary_bytes)
    receipt = {
        "schema_version": RECEIPT_SCHEMA,
        "protocol_id": summary["protocol_id"],
        "protocol_sha256": bundle["protocol_sha256"],
        "publication_gate": PUBLICATION_GATE,
        "bundle_class": summary["bundle_class"],
        "bundle_root_relative_files": bundle["files"],
        "environment_lock": lock,
        "summary_sha256": sha256_bytes(summary_bytes),
        "outcome": summary["outcome"],
        "p1_censoring_present": summary["p1_censoring_present"],
        "terminal_record_count": summary["terminal_record_count"],
        "source_git_sha": summary["source_git_sha_post"],
        "retained_blocker_count": len(summary["retained_blockers"]),
        "direction_claim_permitted": False,
        "paper_data_ready": False,
        "claim_boundary": list(CLAIM_BOUNDARY),
    }
    receipt_bytes = json_bytes(receipt)
    (output_root / "second_case_receipt.json").write_bytes(receipt_bytes)
    receipt["receipt_sha256"] = sha256_bytes(receipt_bytes)
    receipt["summary_path"] = str(summary_path)
    return receipt


def run_replay(bundle_root: Path, summary_path: Path) -> dict[str, Any]:
    """Recompute the summary from raw + protocol and compare bytes with the retained file."""
    bundle = read_bundle(bundle_root)
    recomputed = json_bytes(build_summary(bundle["raw"], bundle["protocol"]))
    retained = Path(summary_path).read_bytes()
    identical = recomputed == retained
    result = {
        "schema_version": REPLAY_SCHEMA,
        "protocol_id": bundle["raw"]["protocol_id"],
        "recomputed_summary_sha256": sha256_bytes(recomputed),
        "retained_summary_sha256": sha256_bytes(retained),
        "identical": identical,
        "interpreter_isolated": bool(sys.flags.isolated),
        "site_disabled": bool(sys.flags.no_site),
        "third_party_modules_loaded": sorted(
            name for name in ("numpy", "torch", "gymnasium", "mujoco", "stable_baselines3") if name in sys.modules
        ),
    }
    if not identical:
        raise SecondCaseError(f"SECONDCASE_REPLAY_MISMATCH: {result}")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    v = sub.add_parser("validate-protocol")
    v.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    a = sub.add_parser("analyse")
    a.add_argument("--bundle", type=Path, required=True)
    a.add_argument("--output", type=Path, required=True)
    r = sub.add_parser("replay")
    r.add_argument("--bundle", type=Path, required=True)
    r.add_argument("--summary", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "validate-protocol":
            payload = {"protocol_sha256": protocol_digest(args.protocol), "design": validate_protocol(load_protocol(args.protocol, require_pinned_digest=False))}
            payload["design"]["alphas"] = dict(payload["design"]["alphas"])
            payload["design"]["forbidden_denominators"] = list(payload["design"]["forbidden_denominators"])
            payload["design"]["arm_ids"] = list(payload["design"]["arm_ids"])
        elif args.command == "analyse":
            payload = analyse(args.bundle, args.output)
        else:
            payload = run_replay(args.bundle, args.summary)
    except SecondCaseError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        sys.exit(2)
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

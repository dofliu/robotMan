"""Fail-closed selection gate for SELECT-V7-CANDIDATE-FORMAL-V1.

The protocol this enforces was written after its author had already seen the
development result, which makes preregistration impossible. What is still
possible is to make the rule unable to bend: the conditions live in a frozen
protocol, the gate refuses to decide on data anyone has already inspected, it
refuses to decide at all without authorization evidence, and it refuses to run
while the measured execution preconditions are unresolved.

Two design choices carry most of that weight.

A condition is eligible only when it is explicitly PASS. Once one condition
fails the remaining ones are reported ``NOT_REACHED``, and ``NOT_REACHED`` is
never treated as agreement - a candidate needs six explicit passes. So a
missing input can only ever block a selection, never permit one.

The rule self-check on development evidence is a separate function that cannot
return a candidate at all. Checking the rule against already-seen data is
useful for testing the rule; letting that path emit a selection would be the
exact thing the protocol exists to prevent.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any

from environment_lock import (
    FULL_LOCK,
    MEASURED_LOCK_CLASS,
    THREADING_PINNED,
    EnvironmentLockError,
    validate_lock_record,
)


PROTOCOL_SCHEMA = "V7_CANDIDATE_SELECTION_PROTOCOL_V1"
PROTOCOL_ID = "SELECT-V7-CANDIDATE-FORMAL-V1"
PROTOCOL_SHA256 = (
    "sha256:b4e16370b5744c510fa11b06343dafb3c1893711639721a406504720bbe99b58"
)
DEFAULT_PROTOCOL = (
    Path(__file__).resolve().parent / "rl" / "v7_candidate_selection_protocol.json"
)

SELECTION_RECEIPT_SCHEMA = "V7_CANDIDATE_SELECTION_RECEIPT_V1"
RULE_CHECK_SCHEMA = "V7_CANDIDATE_SELECTION_RULE_CHECK_V1"
ERROR_SCHEMA = "V7_CANDIDATE_SELECTION_ERROR_RECEIPT_V1"
SEEDVAR_SUMMARY_SCHEMA = "TRAINING_SEED_VARIANCE_SUMMARY_V1"

STATUS_NO_CANDIDATE = "SELECTION_COMPLETE_NO_CANDIDATE"
STATUS_CANDIDATE_SELECTED = "SELECTION_COMPLETE_CANDIDATE_SELECTED"

SEED_CLASS_SEALED_FORMAL = "SEALED_FORMAL"
SEED_CLASS_DEVELOPMENT_EXHAUSTED = "DEVELOPMENT_EXHAUSTED"
SEED_CLASS_RETIRED = "RETIRED"
SEED_CLASSES = (
    SEED_CLASS_SEALED_FORMAL,
    SEED_CLASS_DEVELOPMENT_EXHAUSTED,
    SEED_CLASS_RETIRED,
)

CONDITION_IDS = ("SEL-C1", "SEL-C2", "SEL-C3", "SEL-C4", "SEL-C5", "SEL-C6")
STATE_PASS = "PASS"
STATE_FAIL = "FAIL"
STATE_NOT_REACHED = "NOT_REACHED"
# Only the rule self-check uses this, for the two conditions that are not
# decidable from a seed-variance summary. Selection needs six explicit passes,
# so NOT_APPLICABLE can never satisfy a selection.
STATE_NOT_APPLICABLE = "NOT_APPLICABLE"

SCOPE_SELECTION = "SELECTION"
SCOPE_SELF_CHECK = "SELF_CHECK"

CELL_POINT_IDENTIFIED = "POINT_IDENTIFIED"
COMPARABLE = "COMPARABLE"

GIT_SHA_PATTERN = r"^[0-9a-f]{40}$"


class SelectionError(RuntimeError):
    """Structural failure in the selection protocol, its inputs or its use."""


# --------------------------------------------------------------------------- #
# strict IO
# --------------------------------------------------------------------------- #


def _reject_nonfinite(constant: str) -> Any:
    raise SelectionError(f"payload contains a non-finite JSON constant: {constant}")


def _load_json_file(path: Path) -> dict[str, Any]:
    try:
        payload = Path(path).read_bytes()
    except OSError as exc:
        raise SelectionError(f"cannot read JSON artifact: {path}") from exc
    duplicates: list[str] = []

    def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        keys = [key for key, _ in pairs]
        if len(set(keys)) != len(keys):
            duplicates.append(str(path))
        return dict(pairs)

    try:
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_pairs,
            parse_constant=_reject_nonfinite,
        )
    except UnicodeDecodeError as exc:
        raise SelectionError(f"{path} is not UTF-8") from exc
    except json.JSONDecodeError as exc:
        raise SelectionError(f"{path} is not valid JSON") from exc
    if duplicates:
        raise SelectionError(f"{path} has duplicate object keys")
    return _require_object(value, str(path))


def _json_bytes(payload: Any) -> bytes:
    try:
        return (
            json.dumps(
                payload, ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise SelectionError("derived payload is not strict finite JSON") from exc


def _sha256_bytes(payload: bytes) -> str:
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _require_object(value: Any, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SelectionError(f"{context} must be an object")
    return value


def _require_list(value: Any, context: str) -> list[Any]:
    if not isinstance(value, list):
        raise SelectionError(f"{context} must be an array")
    return value


def _require_string(value: Any, context: str) -> str:
    if not isinstance(value, str) or not value:
        raise SelectionError(f"{context} must be a non-empty string")
    return value


def _require_false(value: Any, context: str) -> None:
    if value is not False:
        raise SelectionError(f"{context} must be false")


# --------------------------------------------------------------------------- #
# protocol
# --------------------------------------------------------------------------- #


def load_protocol(path: Path = DEFAULT_PROTOCOL) -> dict[str, Any]:
    resolved = Path(path)
    digest = sha256_file(resolved)
    if digest != PROTOCOL_SHA256:
        raise SelectionError(
            f"protocol digest drift: expected {PROTOCOL_SHA256}, read {digest}"
        )
    protocol = _load_json_file(resolved)
    validate_protocol(protocol)
    return protocol


def validate_protocol(protocol: dict[str, Any]) -> dict[str, Any]:
    """Semantic invariants, including the ones that keep the rule honest."""
    payload = _require_object(protocol, "protocol")
    if payload.get("schema_version") != PROTOCOL_SCHEMA:
        raise SelectionError("unexpected protocol schema_version")
    if payload.get("protocol_id") != PROTOCOL_ID:
        raise SelectionError("unexpected protocol_id")
    _require_false(payload.get("paper_data_ready"), "protocol.paper_data_ready")
    if payload.get("selected_candidate_arm_id") is not None:
        raise SelectionError("protocol must not preselect a candidate arm")

    # SEL-01. A protocol authored after seeing the result may be used only while
    # it says so; a silently "preregistered" version of this file would be a
    # false claim about how the rule was chosen.
    _require_false(payload.get("preregistered"), "protocol.preregistered")
    disclosure = _require_object(
        payload.get("post_hoc_disclosure"), "protocol.post_hoc_disclosure"
    )
    for field in ("authored_after_seeing", "known_at_freeze_time", "consequence", "mitigation"):
        _require_string(disclosure.get(field), f"protocol.post_hoc_disclosure.{field}")

    data = _require_object(payload.get("evaluation_data"), "protocol.evaluation_data")
    if data.get("permitted_seed_class") != SEED_CLASS_SEALED_FORMAL:
        raise SelectionError("protocol must permit only SEALED_FORMAL evaluation seeds")
    formal = _require_list(data.get("formal_seed_range"), "protocol.evaluation_data.formal_seed_range")
    if len(formal) != 2 or not all(isinstance(item, int) for item in formal):
        raise SelectionError("formal_seed_range must be an integer pair")
    if formal[1] < formal[0]:
        raise SelectionError("formal_seed_range is inverted")
    for field in ("development_exhausted_seed_range", "retired_seed_range"):
        span = _require_list(data.get(field), f"protocol.evaluation_data.{field}")
        if len(span) != 2:
            raise SelectionError(f"{field} must be an integer pair")
        if set(range(int(span[0]), int(span[1]) + 1)) & set(
            range(int(formal[0]), int(formal[1]) + 1)
        ):
            raise SelectionError(f"{field} overlaps the FORMAL range")

    authorization = _require_object(payload.get("authorization"), "protocol.authorization")
    if authorization.get("required") is not True:
        raise SelectionError("protocol must require formal authorization")

    rule = _require_object(payload.get("decision_rule"), "protocol.decision_rule")
    if rule.get("default_outcome") != STATUS_NO_CANDIDATE:
        raise SelectionError("the default decision outcome must be no candidate")
    if rule.get("single_application") is not True:
        raise SelectionError("the rule must declare single application")
    conditions = _require_list(
        rule.get("eligibility_conditions"), "protocol.decision_rule.eligibility_conditions"
    )
    declared = tuple(str(item.get("id")) for item in conditions)
    if declared != CONDITION_IDS:
        raise SelectionError(
            f"eligibility conditions must be exactly {list(CONDITION_IDS)}, got {list(declared)}"
        )
    _require_list(payload.get("execution_preconditions"), "protocol.execution_preconditions")
    _require_string(payload.get("claim_boundary"), "protocol.claim_boundary")
    return payload


def unresolved_execution_preconditions(protocol: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        item
        for item in _require_list(
            protocol.get("execution_preconditions"), "protocol.execution_preconditions"
        )
        if _require_object(item, "execution precondition").get("state") != "RESOLVED"
    ]


def assert_executable(protocol: dict[str, Any]) -> None:
    """SEL-06. Refuse to run while any measured precondition is unresolved.

    These were measured before the freeze rather than discovered mid-run, which
    is the lesson SEEDVAR-AMENDMENT-01 cost. Naming them here keeps the refusal
    diagnostic instead of mysterious.
    """
    blocking = unresolved_execution_preconditions(protocol)
    if blocking:
        named = "; ".join(
            f"{item.get('id')}: {item.get('finding')}" for item in blocking
        )
        raise SelectionError(
            f"selection is not executable, {len(blocking)} unresolved precondition(s): {named}"
        )


def _require_authorization(protocol: dict[str, Any], authorization: Any) -> dict[str, Any]:
    """SEL-03. No authorization evidence, no selection - and no partial answer."""
    if authorization is None:
        raise SelectionError(
            "formal authorization evidence is required before any selection may be emitted"
        )
    payload = _require_object(authorization, "authorization evidence")
    for field in ("authority", "reference", "granted_at_utc", "scope_git_sha"):
        _require_string(payload.get(field), f"authorization evidence.{field}")
    if not re.fullmatch(GIT_SHA_PATTERN, payload["scope_git_sha"]):
        raise SelectionError("authorization evidence scope_git_sha must be a full 40-character Git SHA")
    if payload.get("protocol_sha256") != PROTOCOL_SHA256:
        raise SelectionError(
            "authorization evidence must name this protocol's digest, so an authorization "
            "granted for a different rule cannot be reused here"
        )
    return payload


# --------------------------------------------------------------------------- #
# condition chain
# --------------------------------------------------------------------------- #


def _condition(identifier: str, state: str, detail: str) -> dict[str, Any]:
    return {"id": identifier, "state": state, "detail": detail}


def _cells_for(summary: dict[str, Any], arm_id: str) -> list[dict[str, Any]]:
    cells = []
    for replicate in _require_list(summary.get("replicates"), "summary.replicates"):
        entry = _require_object(replicate, "summary replicate")
        for cell in _require_list(entry.get("arms"), "summary replicate arms"):
            item = _require_object(cell, "summary cell")
            if item.get("arm_id") == arm_id:
                cells.append(item)
    if not cells:
        raise SelectionError(f"summary carries no cells for arm {arm_id}")
    return cells


def _fully_exposed(cells: list[dict[str, Any]]) -> tuple[bool, int, int]:
    full = 0
    total = 0
    for cell in cells:
        counts = _require_object(cell.get("comparability_counts"), "comparability_counts")
        episodes = int(cell.get("episode_count", 0))
        total += episodes
        full += int(counts.get(COMPARABLE, 0))
    return (full == total and total > 0), full, total


def _candidate_block(summary: dict[str, Any], candidate_id: str) -> dict[str, Any]:
    for candidate in _require_list(summary.get("candidates"), "summary.candidates"):
        entry = _require_object(candidate, "summary candidate")
        if entry.get("candidate_arm_id") == candidate_id:
            return entry
    raise SelectionError(f"summary carries no candidate block for {candidate_id}")


def evaluate_conditions(
    protocol: dict[str, Any],
    summary: dict[str, Any],
    candidate_id: str,
    *,
    seed_class: str,
    gate_report: Any = None,
    environment_lock_record: Any = None,
    scope: str = SCOPE_SELECTION,
) -> list[dict[str, Any]]:
    """Run SEL-C1..SEL-C6 in order, short-circuiting to NOT_REACHED after a failure.

    ``scope`` decides how much of the rule is in play.

    ``SCOPE_SELECTION`` runs all six conditions, and eligibility means six
    explicit passes.

    ``SCOPE_SELF_CHECK`` asks a narrower question: do the conditions that are
    decidable from a seed-variance summary stop the candidate on data its author
    has already seen? It drops SEL-C1's seed-class clause, because a check that
    stopped at "development seeds are not FORMAL" would test nothing
    substantive, and it marks SEL-C5 and SEL-C6 ``NOT_APPLICABLE`` rather than
    failing them for missing inputs. That distinction matters: a self-check that
    always failed on input availability could never have passed for any data, so
    it would be no evidence at all about the rule.
    """
    if summary.get("schema_version") != SEEDVAR_SUMMARY_SCHEMA:
        raise SelectionError("selection input must be a TRAINING_SEED_VARIANCE_SUMMARY_V1")
    if seed_class not in SEED_CLASSES:
        raise SelectionError(f"unknown seed class: {seed_class!r}")
    if scope not in (SCOPE_SELECTION, SCOPE_SELF_CHECK):
        raise SelectionError(f"unknown evaluation scope: {scope!r}")
    enforce_seed_class = scope == SCOPE_SELECTION
    data = protocol["evaluation_data"]
    reference_id = protocol["arms"]["reference_arm_id"]
    results: list[dict[str, Any]] = []

    def _remaining(from_index: int, reason: str) -> list[dict[str, Any]]:
        return [
            _condition(identifier, STATE_NOT_REACHED, reason)
            for identifier in CONDITION_IDS[from_index:]
        ]

    # SEL-C1 seed class and inventory.
    if enforce_seed_class and seed_class != data["permitted_seed_class"]:
        results.append(
            _condition(
                "SEL-C1",
                STATE_FAIL,
                f"evaluation seeds are {seed_class}, and only "
                f"{data['permitted_seed_class']} may decide a selection",
            )
        )
        return results + _remaining(1, "SEL-C1 failed")
    first = summary.get("evaluation_seed_first")
    last = summary.get("evaluation_seed_last")
    if not isinstance(first, int) or not isinstance(last, int):
        results.append(_condition("SEL-C1", STATE_FAIL, "summary declares no evaluation seed range"))
        return results + _remaining(1, "SEL-C1 failed")
    formal_low, formal_high = int(data["formal_seed_range"][0]), int(data["formal_seed_range"][1])
    if enforce_seed_class and (first < formal_low or last > formal_high):
        results.append(
            _condition(
                "SEL-C1",
                STATE_FAIL,
                f"evaluation seeds {first}-{last} fall outside the FORMAL range "
                f"{formal_low}-{formal_high}",
            )
        )
        return results + _remaining(1, "SEL-C1 failed")
    expected_records = (
        int(summary.get("replicate_count", 0))
        * (last - first + 1)
        * (1 + len(protocol["arms"]["candidate_arm_ids"]))
    )
    if summary.get("terminal_record_count") != expected_records:
        results.append(
            _condition(
                "SEL-C1",
                STATE_FAIL,
                f"terminal record count {summary.get('terminal_record_count')} does not match the "
                f"expected {expected_records}",
            )
        )
        return results + _remaining(1, "SEL-C1 failed")
    inventory_detail = f"{expected_records} terminal records present over seeds {first}-{last}"
    if not enforce_seed_class:
        inventory_detail += "; seed-class clause not applicable in a rule self-check"
    results.append(_condition("SEL-C1", STATE_PASS, inventory_detail))

    # SEL-C2 full exposure for candidate and reference.
    candidate_cells = _cells_for(summary, candidate_id)
    reference_cells = _cells_for(summary, reference_id)
    candidate_ok, candidate_full, candidate_total = _fully_exposed(candidate_cells)
    reference_ok, reference_full, reference_total = _fully_exposed(reference_cells)
    if not (candidate_ok and reference_ok):
        results.append(
            _condition(
                "SEL-C2",
                STATE_FAIL,
                f"{candidate_id} comparable {candidate_full}/{candidate_total}, "
                f"{reference_id} comparable {reference_full}/{reference_total}; "
                "duty under censored exposure is not point-identified",
            )
        )
        return results + _remaining(2, "SEL-C2 failed")
    if any(cell.get("cell_state") != CELL_POINT_IDENTIFIED for cell in candidate_cells + reference_cells):
        results.append(
            _condition("SEL-C2", STATE_FAIL, "a cell is not point-identified despite full exposure")
        )
        return results + _remaining(2, "SEL-C2 failed")
    results.append(
        _condition("SEL-C2", STATE_PASS, f"all {candidate_total} candidate and reference episodes comparable")
    )

    method_level = _require_object(
        _candidate_block(summary, candidate_id).get("method_level"), "candidate.method_level"
    )

    # SEL-C3 identified negative direction.
    bound = _require_object(method_level.get("theta_bound_pp"), "method_level.theta_bound_pp")
    if bound.get("state") != "OBSERVED":
        results.append(_condition("SEL-C3", STATE_FAIL, f"method-level bound is {bound.get('state')}"))
        return results + _remaining(3, "SEL-C3 failed")
    upper = bound.get("upper_pp")
    lower = bound.get("lower_pp")
    if not isinstance(upper, (int, float)) or not isinstance(lower, (int, float)):
        results.append(_condition("SEL-C3", STATE_FAIL, "method-level bound is not numeric"))
        return results + _remaining(3, "SEL-C3 failed")
    if not upper < 0.0:
        results.append(
            _condition(
                "SEL-C3",
                STATE_FAIL,
                f"method-level bound [{lower}, {upper}] does not exclude zero on the negative side",
            )
        )
        return results + _remaining(3, "SEL-C3 failed")
    results.append(
        _condition("SEL-C3", STATE_PASS, f"method-level bound [{lower}, {upper}] excludes zero and is negative")
    )

    # SEL-C4 estimable variance.
    between = method_level.get("between_replicate_sd_pp")
    if between is None:
        results.append(
            _condition(
                "SEL-C4",
                STATE_FAIL,
                f"between_replicate_sd is null ({method_level.get('between_replicate_sd_reason')}); "
                "an identified direction without an estimable variance cannot size a formal study",
            )
        )
        return results + _remaining(4, "SEL-C4 failed")
    results.append(_condition("SEL-C4", STATE_PASS, f"between_replicate_sd = {between}"))

    if scope == SCOPE_SELF_CHECK:
        # Neither the frozen gate subset nor the run environment discriminates
        # between candidates, and neither is derivable from a seed-variance
        # summary. Marking them not applicable keeps the self-check answerable.
        results.append(
            _condition(
                "SEL-C5",
                STATE_NOT_APPLICABLE,
                "the frozen gate subset is not derivable from a seed-variance summary",
            )
        )
        results.append(
            _condition(
                "SEL-C6",
                STATE_NOT_APPLICABLE,
                "the run environment does not discriminate between candidates",
            )
        )
        return results

    # SEL-C5 frozen gate subset. Not derivable from the summary, so a missing
    # report blocks rather than passes.
    if gate_report is None:
        results.append(
            _condition(
                "SEL-C5",
                STATE_FAIL,
                "no frozen-gate report was supplied; the gate subset is not derivable from the "
                "seed-variance summary and may not be assumed",
            )
        )
        return results + _remaining(5, "SEL-C5 failed")
    gates = _require_object(gate_report, "gate report")
    failures: list[str] = []
    for arm_id in (reference_id, candidate_id):
        arm_gates = _require_object(gates.get(arm_id), f"gate report[{arm_id}]")
        for replicate_index in range(int(summary["replicate_count"])):
            cell = _require_object(
                arm_gates.get(str(replicate_index)), f"gate report[{arm_id}][{replicate_index}]"
            )
            if cell.get("all_gates_passed") is not True:
                failures.append(f"{arm_id} r{replicate_index} gate failure")
            if cell.get("required_null_or_nonfinite") is not False:
                failures.append(f"{arm_id} r{replicate_index} required null or non-finite")
    if failures:
        results.append(_condition("SEL-C5", STATE_FAIL, "; ".join(failures[:6])))
        return results + _remaining(5, "SEL-C5 failed")
    results.append(_condition("SEL-C5", STATE_PASS, "frozen six-gate subset passes for every episode"))

    # SEL-C6 environment lock.
    if environment_lock_record is None:
        results.append(
            _condition("SEL-C6", STATE_FAIL, "no environment lock record was supplied")
        )
        return results
    try:
        validation = validate_lock_record(environment_lock_record)
    except EnvironmentLockError as exc:
        results.append(_condition("SEL-C6", STATE_FAIL, f"environment lock invalid: {exc}"))
        return results
    if (
        validation["lock_class"] != MEASURED_LOCK_CLASS
        or validation["lock_completeness"] != FULL_LOCK
        or validation["threading_determinism"] != THREADING_PINNED
    ):
        results.append(
            _condition(
                "SEL-C6",
                STATE_FAIL,
                f"environment lock is {validation['lock_class']}/"
                f"{validation['lock_completeness']}/{validation['threading_determinism']}",
            )
        )
        return results
    results.append(
        _condition("SEL-C6", STATE_PASS, f"locked_sha256 {validation['locked_sha256']}")
    )
    return results


def _eligible(conditions: list[dict[str, Any]]) -> bool:
    """Six explicit passes. Neither NOT_REACHED nor NOT_APPLICABLE is agreement."""
    return len(conditions) == len(CONDITION_IDS) and all(
        item["state"] == STATE_PASS for item in conditions
    )


def _self_check_unblocked(conditions: list[dict[str, Any]]) -> bool:
    """Did every condition a self-check can decide actually pass?

    True here means the rule failed to stop a candidate on the data its author
    already saw, which is the outcome that would discredit the rule.
    """
    decidable = {"SEL-C1", "SEL-C2", "SEL-C3", "SEL-C4"}
    return all(
        item["state"] == STATE_PASS
        for item in conditions
        if item["id"] in decidable
    ) and len([item for item in conditions if item["id"] in decidable]) == len(decidable)


# --------------------------------------------------------------------------- #
# the two entry points, deliberately not interchangeable
# --------------------------------------------------------------------------- #


def check_rule_on_development_evidence(
    protocol: dict[str, Any], summary: dict[str, Any]
) -> dict[str, Any]:
    """SEL-07. Apply the rule to already-seen data to test the rule, not to select.

    This function cannot return a candidate. Checking a post-hoc rule against
    the data that inspired it is the honest way to show the rule is not tuned;
    letting the same path emit a selection would be the exact failure the
    protocol exists to prevent, so the two paths are separate functions rather
    than one function with a flag.
    """
    validate_protocol(protocol)
    per_candidate = {}
    for candidate_id in protocol["arms"]["candidate_arm_ids"]:
        conditions = evaluate_conditions(
            protocol,
            summary,
            candidate_id,
            seed_class=SEED_CLASS_DEVELOPMENT_EXHAUSTED,
            scope=SCOPE_SELF_CHECK,
        )
        per_candidate[candidate_id] = {
            "conditions": conditions,
            "eligible": _eligible(conditions),
            "unblocked_by_decidable_conditions": _self_check_unblocked(conditions),
        }
    eligible = [
        key
        for key, value in per_candidate.items()
        if value["unblocked_by_decidable_conditions"]
    ]
    if eligible:
        # A post-hoc rule that passes on the data it was written after is not a
        # rule; it is a restatement of that data.
        raise SelectionError(
            "the frozen rule is eligible on already-seen development evidence "
            f"({eligible}); a rule that passes there provides no protection against "
            "post-hoc design bias and must be reconsidered rather than used"
        )
    return {
        "schema_version": RULE_CHECK_SCHEMA,
        "protocol_id": PROTOCOL_ID,
        "protocol_sha256": PROTOCOL_SHA256,
        "purpose": "RULE_SELF_CHECK_NOT_A_SELECTION",
        "seed_class": SEED_CLASS_DEVELOPMENT_EXHAUSTED,
        "outcome": STATUS_NO_CANDIDATE,
        "selected_candidate_arm_id": None,
        "per_candidate": per_candidate,
        "interpretation": protocol["rule_self_check_on_development_evidence"][
            "interpretation"
        ],
        "paper_data_ready": False,
        "claim_boundary": protocol["claim_boundary"],
    }


def select_candidate(
    protocol: dict[str, Any],
    summary: dict[str, Any],
    *,
    authorization: Any = None,
    gate_report: Any = None,
    environment_lock_record: Any = None,
    formal_evidence_sha256: str | None = None,
    output_root: Path | None = None,
) -> dict[str, Any]:
    """The one path that may emit a selection, and it refuses today.

    Order matters: executability, then authorization, then single-application,
    then the conditions. Checking the conditions first would mean computing a
    verdict on sealed data before establishing anyone was allowed to look.
    """
    validate_protocol(protocol)
    assert_executable(protocol)
    granted = _require_authorization(protocol, authorization)
    if summary.get("schema_version") != SEEDVAR_SUMMARY_SCHEMA:
        raise SelectionError("selection input must be a TRAINING_SEED_VARIANCE_SUMMARY_V1")
    digest = _require_string(formal_evidence_sha256, "formal_evidence_sha256")

    # SEL-08. One application per FORMAL evidence set.
    if output_root is not None:
        existing = Path(output_root) / "selection_receipt.json"
        if existing.is_file():
            previous = _load_json_file(existing)
            if previous.get("formal_evidence_sha256") == digest:
                raise SelectionError(
                    "this FORMAL evidence has already been decided; the rule applies once and "
                    "re-applying it would let the outcome be retried"
                )

    per_candidate = {}
    for candidate_id in protocol["arms"]["candidate_arm_ids"]:
        conditions = evaluate_conditions(
            protocol,
            summary,
            candidate_id,
            seed_class=SEED_CLASS_SEALED_FORMAL,
            gate_report=gate_report,
            environment_lock_record=environment_lock_record,
            scope=SCOPE_SELECTION,
        )
        per_candidate[candidate_id] = {
            "conditions": conditions,
            "eligible": _eligible(conditions),
        }

    eligible = [key for key, value in per_candidate.items() if value["eligible"]]
    selected: str | None = None
    tie = False
    if len(eligible) == 1:
        selected = eligible[0]
    elif len(eligible) > 1:
        uppers = {
            key: _candidate_block(summary, key)["method_level"]["theta_bound_pp"]["upper_pp"]
            for key in eligible
        }
        best = min(uppers.values())
        winners = [key for key, value in uppers.items() if value == best]
        if len(winners) == 1:
            selected = winners[0]
        else:
            # SEL-05. An exact tie is unresolved, not broken arbitrarily.
            tie = True

    receipt = {
        "schema_version": SELECTION_RECEIPT_SCHEMA,
        "protocol_id": PROTOCOL_ID,
        "protocol_sha256": PROTOCOL_SHA256,
        "preregistered": False,
        "post_hoc_disclosure": protocol["post_hoc_disclosure"],
        "seed_class": SEED_CLASS_SEALED_FORMAL,
        "formal_evidence_sha256": digest,
        "authorization": granted,
        "applied_once": True,
        "per_candidate": per_candidate,
        "eligible_candidate_arm_ids": eligible,
        "exact_tie_unresolved": tie,
        "selected_candidate_arm_id": selected,
        "selection_status": STATUS_CANDIDATE_SELECTED if selected else STATUS_NO_CANDIDATE,
        "training_replicate_scope": protocol["training_replicate_scope"],
        "training_replicate_scope_permanence": protocol["training_replicate_scope_permanence"],
        "method_level_power_ready": False,
        "statistics_ready": False,
        "paper_data_ready": False,
        "evidence_scope": "SIM_ONLY_MUJOCO",
        "validation_status": "NOT_PHYSICALLY_VALIDATED",
        "claim_boundary": protocol["claim_boundary"],
    }
    if output_root is not None:
        target = Path(output_root)
        target.mkdir(parents=True, exist_ok=True)
        payload = _json_bytes(receipt)
        path = target / "selection_receipt.json"
        descriptor = os.open(
            path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
        )
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
        if sha256_file(path) != _sha256_bytes(payload):
            raise SelectionError("selection receipt readback mismatch")
        receipt["receipt_sha256"] = _sha256_bytes(payload)
    return receipt


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def _print(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False))


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "SELECT-V7-CANDIDATE-FORMAL-V1. 'status' reports whether selection is "
            "executable at all; 'rule-check' applies the frozen rule to already-seen "
            "development evidence to test the rule and can never select. Exit 0 when "
            "the command completes, 1 when no candidate is selected, 2 on structural failure."
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    status_parser = subparsers.add_parser("status")
    status_parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    check_parser = subparsers.add_parser("rule-check")
    check_parser.add_argument("summary", type=Path)
    check_parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    args = parser.parse_args()
    try:
        protocol = load_protocol(args.protocol)
        if args.command == "status":
            blocking = unresolved_execution_preconditions(protocol)
            payload = {
                "schema_version": RULE_CHECK_SCHEMA,
                "protocol_id": PROTOCOL_ID,
                "protocol_sha256": PROTOCOL_SHA256,
                "preregistered": False,
                "executable": not blocking,
                "authorization_state": protocol["authorization"]["state"],
                "unresolved_execution_preconditions": [
                    {"id": item.get("id"), "finding": item.get("finding")}
                    for item in blocking
                ],
                "selected_candidate_arm_id": None,
                "paper_data_ready": False,
                "claim_boundary": protocol["claim_boundary"],
            }
            exit_code = 0 if not blocking else 1
        else:
            payload = check_rule_on_development_evidence(
                protocol, _load_json_file(args.summary)
            )
            exit_code = 0 if payload["outcome"] == STATUS_CANDIDATE_SELECTED else 1
    except Exception as exc:
        _print(
            {
                "schema_version": ERROR_SCHEMA,
                "protocol_id": PROTOCOL_ID,
                "validation_status": "STRUCTURAL_FAILURE",
                "selected_candidate_arm_id": None,
                "paper_data_ready": False,
                "error": f"{type(exc).__name__}: {exc}"[:1000],
            }
        )
        raise SystemExit(2) from exc
    _print(payload)
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()

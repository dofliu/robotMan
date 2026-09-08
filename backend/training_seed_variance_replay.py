"""Independent stdlib-only replay of the seed-variance summary.

This module imports nothing from ``training_seed_variance_contract``. A replay
that reused the contract's own helpers would only restate that contract's
arithmetic, so the design (arm roles, seeds, denominators, censoring rules) is
re-read from the frozen protocol JSON here rather than from shared constants,
and the aggregation is written as its own single pass.

It runs under ``python -I -S``: no site packages, no repository imports.

Usage::

    python -I -S training_seed_variance_replay.py \\
        protocol.json environment_lock.json raw_replicates.json summary.json
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
from typing import Any


REPLAY_SCHEMA = "TRAINING_SEED_VARIANCE_REPLAY_RECEIPT_V1"
SUMMARY_SCHEMA = "TRAINING_SEED_VARIANCE_SUMMARY_V1"
RAW_SCHEMA = "TRAINING_SEED_VARIANCE_RAW_V1"
PROTOCOL_SCHEMA = "TRAINING_SEED_VARIANCE_PROTOCOL_V1"
PROTOCOL_ID = "SEEDVAR-V7-TRAINING-REPLICATE-DEV-V1"
ANALYSIS_UNIT = "TRAINING_REPLICATE"
PRIMARY_MEASUREMENT_ID = "saturation_duty_pct"

COMPARABLE = "COMPARABLE"
EXPOSURE_CENSORED = "EXPOSURE_CENSORED"
METHOD_FAILURE = "METHOD_FAILURE_NOT_CENSORING"
COMPARABILITY_STATES = (COMPARABLE, EXPOSURE_CENSORED, METHOD_FAILURE)
EXPOSURE_CLASSES = ("FULL_EXPOSURE", "EARLY_TERMINATED", "NO_EXPOSURE")
TERMINAL_STATES = ("COMPLETED", "FAILED", "CANCELLED")
OUTCOME_STATES = ("OBSERVED", "NULL", "NONFINITE")

CELL_POINT = "POINT_IDENTIFIED"
CELL_PARTIAL = "PARTIALLY_IDENTIFIED"
CELL_BLOCKED = "BLOCKED_METHOD_FAILURE"

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


class SeedVarianceReplayError(RuntimeError):
    """The replay could not reproduce the summary."""


def _fail(message: str) -> None:
    raise SeedVarianceReplayError(message)


def _reject_constant(constant: str) -> Any:
    _fail(f"non-finite JSON constant: {constant}")


def _load(path: str, label: str) -> dict[str, Any]:
    with open(path, "rb") as stream:
        payload = stream.read()
    duplicates = []

    def _pairs(pairs):
        keys = [key for key, _ in pairs]
        if len(set(keys)) != len(keys):
            duplicates.append(label)
        return dict(pairs)

    value = json.loads(
        payload.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_reject_constant
    )
    if duplicates:
        _fail(f"{label} has duplicate object keys")
    if not isinstance(value, dict):
        _fail(f"{label} must be an object")
    return value


def _canonical(payload: Any) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True)
        + "\n"
    ).encode("utf-8")


def _digest(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _mean(values):
    """Left-to-right addition in the caller's order, then one division.

    Float addition is not associative, so the order is part of the contract
    rather than an implementation choice; exact identity with the primary
    implementation depends on it.
    """
    if not values:
        _fail("mean requires at least one value")
    total = 0.0
    for value in values:
        total += value
    return total / len(values)


def _sample_sd(values):
    count = len(values)
    if count < 2:
        _fail("sample standard deviation requires at least two values")
    mean = _mean(values)
    accumulator = 0.0
    for value in values:
        delta = value - mean
        accumulator += delta * delta
    return math.sqrt(accumulator / (count - 1))


def _pct(value):
    return round(value, PERCENT_DECIMALS)


def _ratio(value):
    return round(value, RATIO_DECIMALS)


def _counts(values, states):
    tally = {state: 0 for state in states}
    for value in values:
        if value not in tally:
            _fail(f"unexpected state {value!r}")
        tally[value] += 1
    return tally


def _design(protocol: dict[str, Any]) -> dict[str, Any]:
    """Re-read the frozen design from the protocol instead of hard-coding it."""
    if protocol.get("schema_version") != PROTOCOL_SCHEMA:
        _fail("unexpected protocol schema_version")
    if protocol.get("protocol_id") != PROTOCOL_ID:
        _fail("unexpected protocol_id")
    arms = protocol.get("arms")
    if not isinstance(arms, list) or not arms:
        _fail("protocol.arms must be a non-empty array")
    reference = [item["arm_id"] for item in arms if item.get("role") == "reference"]
    candidates = [item["arm_id"] for item in arms if item.get("role") == "candidate"]
    if len(reference) != 1 or not candidates:
        _fail("protocol.arms must declare exactly one reference and at least one candidate")
    training = protocol.get("training_design", {})
    evaluation = protocol.get("evaluation_design", {})
    estimand = protocol.get("estimand", {})
    replicate_count = training.get("replicate_count")
    seeds = training.get("training_seeds")
    blocks = training.get("environment_seed_blocks")
    start = evaluation.get("evaluation_seed_start")
    end = evaluation.get("evaluation_seed_end")
    if not isinstance(replicate_count, int) or replicate_count < 2:
        _fail("protocol.training_design.replicate_count must be an integer >= 2")
    if not isinstance(seeds, list) or len(seeds) != replicate_count:
        _fail("training_seeds must match replicate_count")
    if not isinstance(blocks, list) or len(blocks) != replicate_count:
        _fail("environment_seed_blocks must match replicate_count")
    if not isinstance(start, int) or not isinstance(end, int) or end < start:
        _fail("evaluation seed range is invalid")
    if estimand.get("analysis_unit") != ANALYSIS_UNIT:
        _fail("estimand.analysis_unit must be TRAINING_REPLICATE")
    if estimand.get("method_level_denominator") != replicate_count:
        _fail("estimand.method_level_denominator must equal replicate_count")
    forbidden = estimand.get("forbidden_denominators")
    if not isinstance(forbidden, list):
        _fail("estimand.forbidden_denominators must be an array")
    arm_ids = tuple(reference + candidates)
    return {
        "arm_ids": arm_ids,
        "reference": reference[0],
        "candidates": tuple(candidates),
        "replicate_count": replicate_count,
        "training_seeds": [int(seed) for seed in seeds],
        "environment_seed_blocks": [[int(pair[0]), int(pair[1])] for pair in blocks],
        "evaluation_seeds": tuple(range(start, end + 1)),
        "expected_terminal_records": replicate_count * (end - start + 1) * len(arm_ids),
        "forbidden_denominators": sorted(int(value) for value in forbidden),
    }


def _check_lock(protocol: dict[str, Any], record: dict[str, Any], raw: dict[str, Any]) -> str:
    """Re-derive the lock digest and re-check the protocol's lock requirement."""
    locked = record.get("locked")
    if not isinstance(locked, dict):
        _fail("environment lock record has no locked subtree")
    digest = _digest(_canonical(locked))
    if record.get("locked_sha256") != digest:
        _fail("environment lock record digest does not match its locked subtree")
    requirement = protocol.get("environment_lock_requirement", {})
    if record.get("lock_class") != requirement.get("required_lock_class"):
        _fail("environment lock class does not meet the protocol requirement")
    if record.get("lock_completeness") != requirement.get("required_lock_completeness"):
        _fail("environment lock completeness does not meet the protocol requirement")
    if record.get("threading_determinism") != requirement.get("required_threading_determinism"):
        _fail("environment lock threading does not meet the protocol requirement")
    if raw.get("environment_lock_sha256") != digest:
        _fail("raw.environment_lock_sha256 does not match the bundle's lock record")
    return digest


def _cell(cell: dict[str, Any], seeds) -> dict[str, Any]:
    episodes = cell.get("episodes")
    if not isinstance(episodes, list) or len(episodes) != len(seeds):
        _fail("cell episode inventory is wrong")
    if [item.get("evaluation_seed") for item in episodes] != list(seeds):
        _fail("cell episodes are not the exact ascending seed inventory")
    comparability = _counts(
        [item["comparability_state"] for item in episodes], COMPARABILITY_STATES
    )
    common = {
        "arm_id": cell["arm_id"],
        "evaluation_output_sha256": cell["evaluation_output_sha256"],
        "realized_timesteps": cell["realized_timesteps"],
        "training_terminal_state": cell["training_terminal_state"],
        "episode_count": len(episodes),
        "comparability_counts": comparability,
        "exposure_counts": _counts([item["exposure_class"] for item in episodes], EXPOSURE_CLASSES),
        "outcome_counts": _counts([item["outcome_state"] for item in episodes], OUTCOME_STATES),
        "terminal_counts": _counts(
            [item["terminal_record_state"] for item in episodes], TERMINAL_STATES
        ),
    }
    if comparability[METHOD_FAILURE]:
        return dict(
            common,
            cell_state=CELL_BLOCKED,
            mean_bound_pct={
                "state": "NULL",
                "lower_pct": None,
                "upper_pct": None,
                "width_pct": None,
                "reason": REASON_METHOD_FAILURE_CELL,
            },
            within_replicate_level_sd_pct=None,
            within_replicate_level_sd_reason=REASON_METHOD_FAILURE_CELL,
        )
    lowers = [item["full_horizon_duty_bound_pct"]["lower_pct"] for item in episodes]
    uppers = [item["full_horizon_duty_bound_pct"]["upper_pct"] for item in episodes]
    lower = _pct(_mean(lowers))
    upper = _pct(_mean(uppers))
    if upper < lower:
        _fail("aggregated cell bound is inverted")
    if comparability[EXPOSURE_CENSORED]:
        state = CELL_PARTIAL
        level_sd = None
        level_reason = REASON_WITHIN_SD_CENSORED
    else:
        state = CELL_POINT
        if lower != upper:
            _fail("uncensored cell produced a non-degenerate mean bound")
        level_sd = _pct(_sample_sd(lowers))
        level_reason = None
    return dict(
        common,
        cell_state=state,
        mean_bound_pct={
            "state": "OBSERVED",
            "lower_pct": lower,
            "upper_pct": upper,
            "width_pct": _pct(upper - lower),
            "reason": None,
        },
        within_replicate_level_sd_pct=level_sd,
        within_replicate_level_sd_reason=level_reason,
    )


def _difference(reference_cell, candidate_cell, index):
    if CELL_BLOCKED in (reference_cell["cell_state"], candidate_cell["cell_state"]):
        return {
            "replicate_index": index,
            "state": "NULL",
            "lower_pp": None,
            "upper_pp": None,
            "width_pp": None,
            "point_identified": False,
            "sign": SIGN_NULL,
            "reason": REASON_BLOCKED_PAIR,
        }
    lower = _pct(
        candidate_cell["mean_bound_pct"]["lower_pct"] - reference_cell["mean_bound_pct"]["upper_pct"]
    )
    upper = _pct(
        candidate_cell["mean_bound_pct"]["upper_pct"] - reference_cell["mean_bound_pct"]["lower_pct"]
    )
    if upper < lower:
        _fail("paired identification bound is inverted")
    if upper < 0.0:
        sign = SIGN_NEGATIVE
    elif lower > 0.0:
        sign = SIGN_POSITIVE
    else:
        sign = SIGN_UNIDENTIFIED
    return {
        "replicate_index": index,
        "state": "OBSERVED",
        "lower_pp": lower,
        "upper_pp": upper,
        "width_pp": _pct(upper - lower),
        "point_identified": reference_cell["cell_state"] == CELL_POINT
        and candidate_cell["cell_state"] == CELL_POINT,
        "sign": sign,
        "reason": None,
    }


def _paired_sd(reference_raw, candidate_raw, index):
    differences = []
    for reference_episode, candidate_episode in zip(
        reference_raw["episodes"], candidate_raw["episodes"]
    ):
        if (
            reference_episode["comparability_state"] != COMPARABLE
            or candidate_episode["comparability_state"] != COMPARABLE
        ):
            return {
                "replicate_index": index,
                "paired_sd_pp": None,
                "reason": REASON_WITHIN_SD_CENSORED,
            }
        differences.append(
            candidate_episode["full_horizon_duty_bound_pct"]["lower_pct"]
            - reference_episode["full_horizon_duty_bound_pct"]["lower_pct"]
        )
    return {
        "replicate_index": index,
        "paired_sd_pp": _pct(_sample_sd(differences)),
        "reason": None,
    }


def _mean_or_none(values):
    if any(value is None for value in values):
        return None
    return _pct(_mean([float(value) for value in values]))


def _method_level(differences, paired_sds, design):
    denominator = len(differences)
    if denominator != design["replicate_count"]:
        _fail("method-level denominator must equal replicate_count")
    if denominator in design["forbidden_denominators"]:
        _fail("PSEUDO_REPLICATION_FORBIDDEN: episode-level denominator used")
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
    theta_lower = _pct(_mean(lowers))
    theta_upper = _pct(_mean(uppers))
    if theta_upper < theta_lower:
        _fail("method-level identification bound is inverted")
    if theta_upper < 0.0:
        sign = SIGN_NEGATIVE
    elif theta_lower > 0.0:
        sign = SIGN_POSITIVE
    else:
        sign = SIGN_UNIDENTIFIED
    if all(item["point_identified"] for item in differences):
        between = _pct(_sample_sd(lowers))
        between_reason = None
    else:
        between = None
        between_reason = REASON_PARTIAL_SD
    ratio = None
    if between is not None and mean_paired_sd is not None and mean_paired_sd > 0.0:
        ratio = _ratio(between / mean_paired_sd)
    return {
        "analysis_unit": ANALYSIS_UNIT,
        "method_level_n": denominator,
        "theta_bound_pp": {
            "state": "OBSERVED",
            "lower_pp": theta_lower,
            "upper_pp": theta_upper,
            "width_pp": _pct(theta_upper - theta_lower),
            "reason": None,
        },
        "sign": sign,
        "sign_identified_replicate_count": sum(
            1 for item in differences if item["sign"] in (SIGN_NEGATIVE, SIGN_POSITIVE)
        ),
        "between_replicate_sd_pp": between,
        "between_replicate_sd_reason": between_reason,
        "mean_within_replicate_paired_sd_pp": mean_paired_sd,
        "variance_ratio_between_over_within": ratio,
        "sample_size_decision_input_ready": between is not None,
        "blocked_replicate_indices": [],
    }


def rebuild_summary(protocol, lock_record, raw, protocol_sha256) -> dict[str, Any]:
    design = _design(protocol)
    if raw.get("schema_version") != RAW_SCHEMA:
        _fail("unexpected raw schema_version")
    if raw.get("protocol_id") != PROTOCOL_ID:
        _fail("raw.protocol_id does not match the frozen protocol")
    if raw.get("source_git_sha_pre") != raw.get("source_git_sha_post"):
        _fail("raw source Git SHA drifted during execution")
    if raw.get("source_dirty_pre") is not False or raw.get("source_dirty_post") is not False:
        _fail("raw source worktree was dirty")
    lock_digest = _check_lock(protocol, lock_record, raw)

    replicates = raw.get("replicates")
    if not isinstance(replicates, list) or len(replicates) != design["replicate_count"]:
        _fail("raw.replicates inventory is wrong")
    arm_ids = design["arm_ids"]
    seeds = design["evaluation_seeds"]

    raw_cells = {arm_id: [] for arm_id in arm_ids}
    cells = {arm_id: [] for arm_id in arm_ids}
    records = 0
    for index, replicate in enumerate(replicates):
        if replicate.get("replicate_index") != index:
            _fail("replicate_index is not the ascending frozen order")
        if replicate.get("training_seed") != design["training_seeds"][index]:
            _fail("training_seed does not match the frozen schedule")
        if replicate.get("environment_seed_block") != design["environment_seed_blocks"][index]:
            _fail("environment_seed_block does not match the frozen schedule")
        arms = replicate.get("arms")
        if [item.get("arm_id") for item in arms] != list(arm_ids):
            _fail("replicate arms are not the exact frozen inventory in order")
        for arm in arms:
            raw_cells[arm["arm_id"]].append(arm)
            cells[arm["arm_id"]].append(_cell(arm, seeds))
            records += len(arm["episodes"])
    if records != design["expected_terminal_records"]:
        _fail("terminal record count does not match the frozen design")

    replicate_rows = [
        {
            "replicate_index": index,
            "training_seed": design["training_seeds"][index],
            "environment_seed_block": design["environment_seed_blocks"][index],
            "arms": [cells[arm_id][index] for arm_id in arm_ids],
        }
        for index in range(design["replicate_count"])
    ]

    reference = design["reference"]
    candidates = []
    for candidate_id in design["candidates"]:
        differences = [
            _difference(cells[reference][index], cells[candidate_id][index], index)
            for index in range(design["replicate_count"])
        ]
        paired_sds = [
            _paired_sd(raw_cells[reference][index], raw_cells[candidate_id][index], index)
            for index in range(design["replicate_count"])
        ]
        candidates.append(
            {
                "candidate_arm_id": candidate_id,
                "reference_arm_id": reference,
                "replicate_paired_differences": differences,
                "within_replicate_paired_sd": paired_sds,
                "method_level": _method_level(differences, paired_sds, design),
            }
        )

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
        for arm_id in arm_ids
    }

    blockers = []
    for arm_id in arm_ids:
        for index, cell in enumerate(cells[arm_id]):
            if cell["cell_state"] != CELL_POINT:
                blockers.append(
                    {
                        "scope": "cell",
                        "arm_id": arm_id,
                        "replicate_index": index,
                        "state": cell["cell_state"],
                        "reason": cell["within_replicate_level_sd_reason"],
                    }
                )
    for candidate in candidates:
        method_level = candidate["method_level"]
        if method_level["between_replicate_sd_pp"] is None:
            blockers.append(
                {
                    "scope": "method_level",
                    "arm_id": candidate["candidate_arm_id"],
                    "replicate_index": None,
                    "state": "BETWEEN_REPLICATE_SD_WITHHELD",
                    "reason": method_level["between_replicate_sd_reason"],
                }
            )
        if method_level["sign"] == SIGN_UNIDENTIFIED:
            blockers.append(
                {
                    "scope": "method_level",
                    "arm_id": candidate["candidate_arm_id"],
                    "replicate_index": None,
                    "state": "SIGN_UNIDENTIFIED",
                    "reason": "METHOD_LEVEL_BOUND_CONTAINS_ZERO",
                }
            )

    return {
        "schema_version": SUMMARY_SCHEMA,
        "protocol_id": PROTOCOL_ID,
        "protocol_sha256": protocol_sha256,
        "audit_protocol_sha256": protocol["prerequisite_contracts"]["audit_protocol_sha256"],
        "bundle_class": raw["bundle_class"],
        "environment_lock_sha256": lock_digest,
        "source_git_sha_pre": raw["source_git_sha_pre"],
        "source_git_sha_post": raw["source_git_sha_post"],
        "analysis_unit": ANALYSIS_UNIT,
        "primary_measurement_id": PRIMARY_MEASUREMENT_ID,
        "replicate_count": design["replicate_count"],
        "training_seeds": design["training_seeds"],
        "evaluation_seed_first": seeds[0],
        "evaluation_seed_last": seeds[-1],
        "terminal_record_count": design["expected_terminal_records"],
        "forbidden_denominators": design["forbidden_denominators"],
        "replicates": replicate_rows,
        "within_replicate_level_sd": within_level,
        "candidates": candidates,
        "selected_candidate_arm_id": None,
        "selection_permitted": False,
        "method_level_power_ready": False,
        "statistics_ready": False,
        "paper_data_ready": False,
        "training_replicate_scope": "CONDITIONAL_ON_FIXED_WARM_START",
        "cross_protocol_comparability": "NON_VERIFIABLE_ENVIRONMENT",
        "seed_variance_status": STATUS_CLEAN if not blockers else STATUS_BLOCKED,
        "retained_blockers": blockers,
        "claim_boundary": protocol["claim_boundary"],
    }


def main(argv) -> int:
    if len(argv) != 4:
        _fail("expected protocol, environment lock, raw and summary paths")
    protocol_path, lock_path, raw_path, summary_path = argv
    with open(protocol_path, "rb") as stream:
        protocol_sha256 = _digest(stream.read())
    protocol = _load(protocol_path, "protocol")
    lock_record = _load(lock_path, "environment lock")
    raw = _load(raw_path, "raw")
    with open(summary_path, "rb") as stream:
        expected = stream.read()
    rebuilt = _canonical(rebuild_summary(protocol, lock_record, raw, protocol_sha256))
    if rebuilt != expected:
        _fail(
            "replay mismatch: rebuilt "
            f"{_digest(rebuilt)} != summary {_digest(expected)}"
        )
    print(
        json.dumps(
            {
                "schema_version": REPLAY_SCHEMA,
                "protocol_id": PROTOCOL_ID,
                "replay_exact": True,
                "replay_interpreter_flags": ["-I", "-S"],
                "summary_sha256": _digest(expected),
                "analysis_unit": ANALYSIS_UNIT,
                "method_level_power_ready": False,
                "paper_data_ready": False,
            },
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except SeedVarianceReplayError as error:
        print(f"SeedVarianceReplayError: {error}", file=sys.stderr)
        raise SystemExit(2)

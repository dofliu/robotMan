"""Fail-closed analysis for R0-REGIME-HORIZON-PROBE-V1.

Read-only. Given the version-controlled horizon trace index, it evaluates the
frozen two-part adequacy rule over the frozen horizon grid and returns one of
the four frozen labels per contrast.

Stdlib only, on purpose: the whole module must run under ``python -I -S`` so the
result can be recomputed with no site packages, exactly as the seed-variance and
second-case analyses are. Nothing here may be changed to alter a threshold, the
grid or the selection rule; those are frozen in
``backend/rl/r0_regime_probe_protocol.json`` and documented in
``docs/R0_REGIME_PROBE_SPEC.md``.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

CONTRACT_ID = "R0-REGIME-HORIZON-PROBE-V1"
RESULT_SCHEMA = "R0_REGIME_PROBE_RESULT_V1"
INDEX_SCHEMA = "R0_HORIZON_TRACE_INDEX_V1"
PROTOCOL_SCHEMA = "R0_REGIME_PROBE_PROTOCOL_V1"

# Pinned at the freeze (commit 06ebf60, pushed before any truncated horizon was
# computed). A digest mismatch is a method failure, never a silent re-pin.
PROTOCOL_SHA256 = "sha256:07cf6d21dbc84d299384846d21abb8e25d921da8aea9214a77c95abe7bed08fe"
SPECIFICATION_SHA256 = "sha256:a15cada64637800a9fa50184d0e4dec1eaad958602c296c3211b90edf031c03a"
HORIZON_TRACE_INDEX_SHA256 = "sha256:6ad44934232e110741a69879027ccc1f84c10ae4c63b0acf2877756af0d330c7"

EXPECTED_EPISODE_TOTAL = 450
EXPECTED_EPISODES_PER_ARM = 150
EXPECTED_SOURCE_COUNT = 15
REQUIRED_TERMINAL_STATE = "COMPLETED"

# Denominators the parent protocol forbids at method level. Recorded so a reader
# can check no aggregate here divides by them.
FORBIDDEN_DENOMINATORS = (150, 450)

LABEL_WINDOW_FOUND = "R0_WINDOW_FOUND"
LABEL_EXPOSURE_ONLY = "R0_EXPOSURE_ONLY"
LABEL_NOT_REACHABLE = "R0_NOT_REACHABLE"
LABEL_METHOD_FAILURE = "R0_PROBE_METHOD_FAILURE"

DUTY_DECIMALS = 6


class R0ProbeError(RuntimeError):
    """Any contract violation. Never downgraded to one of the three result labels."""


def _sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _load_json(path: Path) -> Any:
    try:
        text = Path(path).read_bytes().decode("utf-8")
    except OSError as exc:
        raise R0ProbeError(f"R0_INPUT_UNREADABLE: {path}") from exc
    except UnicodeDecodeError as exc:
        raise R0ProbeError(f"R0_INPUT_NOT_UTF8: {path}") from exc

    def _reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        keys = [key for key, _ in pairs]
        if len(set(keys)) != len(keys):
            raise R0ProbeError(f"R0_INPUT_DUPLICATE_KEYS: {path}")
        return dict(pairs)

    def _reject_nonfinite(_: str) -> Any:
        raise R0ProbeError(f"R0_INPUT_NONFINITE: {path}")

    try:
        return json.loads(text, object_pairs_hook=_reject_duplicates, parse_constant=_reject_nonfinite)
    except json.JSONDecodeError as exc:
        raise R0ProbeError(f"R0_INPUT_NOT_JSON: {path}") from exc


def load_protocol(path: Path, *, require_pinned_digest: bool = True) -> dict[str, Any]:
    """Load the frozen protocol, refusing anything that is not the pinned freeze."""
    protocol = _load_json(path)
    if not isinstance(protocol, dict):
        raise R0ProbeError("R0_PROTOCOL_NOT_OBJECT")
    if protocol.get("schema_version") != PROTOCOL_SCHEMA:
        raise R0ProbeError(f"R0_PROTOCOL_SCHEMA_UNKNOWN: {protocol.get('schema_version')!r}")
    if protocol.get("protocol_id") != CONTRACT_ID:
        raise R0ProbeError(f"R0_PROTOCOL_ID_UNKNOWN: {protocol.get('protocol_id')!r}")
    if protocol.get("status") != "FROZEN_BEFORE_EXECUTION":
        raise R0ProbeError(f"R0_PROTOCOL_NOT_FROZEN: {protocol.get('status')!r}")
    if protocol.get("specification_sha256") != SPECIFICATION_SHA256:
        raise R0ProbeError("R0_PROTOCOL_SPEC_DIGEST_MISMATCH")
    if require_pinned_digest:
        measured = _sha256_file(path)
        if measured != PROTOCOL_SHA256:
            raise R0ProbeError(f"R0_PROTOCOL_DIGEST_MISMATCH: {measured} != {PROTOCOL_SHA256}")
    return protocol


def load_index(path: Path, *, require_pinned_digest: bool = True) -> dict[str, Any]:
    """Load and fully validate the horizon trace index (acceptance R0-01, R0-03)."""
    index = _load_json(path)
    if not isinstance(index, dict):
        raise R0ProbeError("R0_INDEX_NOT_OBJECT")
    if index.get("schema_version") != INDEX_SCHEMA:
        raise R0ProbeError(f"R0_INDEX_SCHEMA_UNKNOWN: {index.get('schema_version')!r}")
    if require_pinned_digest:
        measured = _sha256_file(path)
        if measured != HORIZON_TRACE_INDEX_SHA256:
            raise R0ProbeError(f"R0_INDEX_DIGEST_MISMATCH: {measured} != {HORIZON_TRACE_INDEX_SHA256}")

    substeps = index.get("substeps_per_control_step")
    if not isinstance(substeps, int) or substeps <= 0:
        raise R0ProbeError(f"R0_INDEX_SUBSTEPS_INVALID: {substeps!r}")

    sources = index.get("sources")
    if not isinstance(sources, list) or len(sources) != EXPECTED_SOURCE_COUNT:
        raise R0ProbeError(f"R0_INDEX_SOURCE_COUNT: {len(sources) if isinstance(sources, list) else None}")

    episodes = index.get("episodes")
    if not isinstance(episodes, list) or len(episodes) != EXPECTED_EPISODE_TOTAL:
        raise R0ProbeError(f"R0_INDEX_EPISODE_COUNT: {len(episodes) if isinstance(episodes, list) else None}")

    seen: set[tuple[str, int, int]] = set()
    per_arm: dict[str, int] = {}
    for episode in episodes:
        if not isinstance(episode, dict):
            raise R0ProbeError("R0_EPISODE_NOT_OBJECT")
        arm = episode.get("arm_id")
        replicate = episode.get("replicate_index")
        seed = episode.get("evaluation_seed")
        steps = episode.get("control_steps")
        over = episode.get("saturation_substeps_over_threshold")
        terminal = episode.get("terminal_record_state")
        frozen_duty = episode.get("frozen_full_horizon_duty_pct")

        if not isinstance(arm, str) or not arm:
            raise R0ProbeError("R0_EPISODE_ARM_INVALID")
        if not isinstance(replicate, int) or not isinstance(seed, int):
            raise R0ProbeError(f"R0_EPISODE_KEY_INVALID: {arm}")
        key = (arm, replicate, seed)
        if key in seen:
            raise R0ProbeError(f"R0_EPISODE_DUPLICATE: {key}")
        seen.add(key)

        if terminal != REQUIRED_TERMINAL_STATE:
            # A non-COMPLETED record is a method failure, not censoring: the
            # distinction the parent audit exists to preserve.
            raise R0ProbeError(f"R0_EPISODE_TERMINAL_STATE: {key} {terminal!r}")
        if not isinstance(steps, int) or steps <= 0:
            raise R0ProbeError(f"R0_EPISODE_STEPS_INVALID: {key} {steps!r}")
        if not isinstance(over, list) or len(over) != steps:
            raise R0ProbeError(f"R0_EPISODE_TRACE_LENGTH: {key}")
        for value in over:
            if not isinstance(value, int) or value < 0 or value > substeps:
                raise R0ProbeError(f"R0_EPISODE_SUBSTEP_RANGE: {key} {value!r}")
        if not isinstance(frozen_duty, (int, float)) or isinstance(frozen_duty, bool):
            raise R0ProbeError(f"R0_EPISODE_FROZEN_DUTY_INVALID: {key} {frozen_duty!r}")

        # R0-03: the truncation formula must agree with the frozen metric at the
        # full horizon, or the whole recomputation is a different quantity.
        recomputed = duty_pct(over, steps, substeps)
        if abs(recomputed - round(float(frozen_duty), DUTY_DECIMALS)) > 1e-9:
            raise R0ProbeError(f"R0_FULL_HORIZON_IDENTITY: {key} {recomputed} != {frozen_duty}")

        per_arm[arm] = per_arm.get(arm, 0) + 1

    for arm, count in sorted(per_arm.items()):
        if count != EXPECTED_EPISODES_PER_ARM:
            raise R0ProbeError(f"R0_ARM_EPISODE_COUNT: {arm} {count}")

    return index


def duty_pct(over_threshold: list[int], horizon: int, substeps: int) -> float:
    """500 Hz saturation duty over the first ``horizon`` control steps.

    The reduction is a plain left-to-right sum of integers, so it is exact and
    carries no reduction-order ambiguity; the single float division and the
    6-decimal rounding are the frozen definition.
    """
    if horizon <= 0 or horizon > len(over_threshold):
        raise R0ProbeError(f"R0_DUTY_HORIZON_OUT_OF_RANGE: {horizon} of {len(over_threshold)}")
    total = 0
    for index in range(horizon):
        total += over_threshold[index]
    return round(total / (substeps * horizon) * 100.0, DUTY_DECIMALS)


def _mean_duty(values: list[float]) -> float:
    """Left-to-right mean of already-rounded per-episode duties."""
    total = 0.0
    for value in values:
        total += value
    return total / len(values)


def evaluate_contrast(index: dict[str, Any], protocol: dict[str, Any], contrast: dict[str, Any]) -> dict[str, Any]:
    """Apply the frozen grid, adequacy rule and selection rule to one contrast."""
    substeps = index["substeps_per_control_step"]
    grid = protocol["horizon_grid"]
    low = grid["minimum_control_steps"]
    high = grid["maximum_control_steps"]
    step = grid["step"]
    rule = protocol["adequacy_rule"]["R0_P0b_non_degeneracy"]
    floor_pct = rule["minimum_mean_duty_pct"]
    ceiling_pct = rule["maximum_mean_duty_pct"]
    required_per_arm = protocol["adequacy_rule"]["R0_P0a_exposure"]["required_h_covered_episodes_per_arm"]

    reference_id = contrast["reference_arm_id"]
    candidate_id = contrast["candidate_arm_id"]
    reference = [e for e in index["episodes"] if e["arm_id"] == reference_id]
    candidate = [e for e in index["episodes"] if e["arm_id"] == candidate_id]
    if len(reference) != required_per_arm or len(candidate) != required_per_arm:
        raise R0ProbeError(f"R0_CONTRAST_ARM_SIZE: {contrast['contrast_id']}")

    reference_steps = [e["control_steps"] for e in reference]
    candidate_steps = [e["control_steps"] for e in candidate]
    # An arm is fully H_COVERED exactly while H does not exceed its shortest episode.
    reference_min_steps = min(reference_steps)
    candidate_min_steps = min(candidate_steps)

    p0a_horizons: list[int] = []
    adequate_horizons: list[int] = []
    reference_mean_by_horizon: dict[int, float] = {}

    for horizon in range(low, high + 1, step):
        reference_covered = sum(1 for value in reference_steps if value >= horizon)
        candidate_covered = sum(1 for value in candidate_steps if value >= horizon)
        if reference_covered != required_per_arm or candidate_covered != required_per_arm:
            # R0-P0a not satisfied: R0-P0b is NOT_REACHED, which never counts as a pass.
            continue
        p0a_horizons.append(horizon)
        duties = [duty_pct(e["saturation_substeps_over_threshold"], horizon, substeps) for e in reference]
        mean_duty = round(_mean_duty(duties), DUTY_DECIMALS)
        reference_mean_by_horizon[horizon] = mean_duty
        if floor_pct <= mean_duty <= ceiling_pct:
            adequate_horizons.append(horizon)

    if adequate_horizons:
        label = LABEL_WINDOW_FOUND
        selected = max(adequate_horizons)
    elif p0a_horizons:
        label = LABEL_EXPOSURE_ONLY
        selected = None
    else:
        label = LABEL_NOT_REACHABLE
        selected = None

    return {
        "contrast_id": contrast["contrast_id"],
        "reference_arm_id": reference_id,
        "candidate_arm_id": candidate_id,
        "label": label,
        "selected_horizon_control_steps": selected,
        "selected_horizon_seconds": None if selected is None else round(selected / 50.0, 6),
        "reference_mean_duty_pct_at_selected": None if selected is None else reference_mean_by_horizon[selected],
        "p0a_horizon_count": len(p0a_horizons),
        "p0a_horizon_min": min(p0a_horizons) if p0a_horizons else None,
        "p0a_horizon_max": max(p0a_horizons) if p0a_horizons else None,
        "adequate_horizon_count": len(adequate_horizons),
        "adequate_horizon_min": min(adequate_horizons) if adequate_horizons else None,
        "adequate_horizon_max": max(adequate_horizons) if adequate_horizons else None,
        "reference_shortest_episode_control_steps": reference_min_steps,
        "candidate_shortest_episode_control_steps": candidate_min_steps,
        "reference_mean_duty_pct_at_p0a_max": (
            reference_mean_by_horizon[max(p0a_horizons)] if p0a_horizons else None
        ),
        "reference_mean_duty_pct_at_p0a_min": (
            reference_mean_by_horizon[min(p0a_horizons)] if p0a_horizons else None
        ),
    }


def run_probe(index_path: Path, protocol_path: Path, *, require_pinned_digest: bool = True) -> dict[str, Any]:
    """Full probe: validate inputs, then evaluate every frozen contrast."""
    protocol = load_protocol(protocol_path, require_pinned_digest=require_pinned_digest)
    index = load_index(index_path, require_pinned_digest=require_pinned_digest)

    contrasts = protocol.get("contrasts")
    if not isinstance(contrasts, list) or not contrasts:
        raise R0ProbeError("R0_PROTOCOL_CONTRASTS_MISSING")

    results = [evaluate_contrast(index, protocol, contrast) for contrast in contrasts]
    return {
        "schema_version": RESULT_SCHEMA,
        "protocol_id": CONTRACT_ID,
        "protocol_sha256": PROTOCOL_SHA256 if require_pinned_digest else None,
        "specification_sha256": SPECIFICATION_SHA256,
        "horizon_trace_index_sha256": HORIZON_TRACE_INDEX_SHA256 if require_pinned_digest else None,
        "evidence_class": "PILOT_NOT_EVIDENCE",
        "conditional_on_fixed_warm_start": True,
        "forbidden_denominators": list(FORBIDDEN_DENOMINATORS),
        "horizon_grid": {
            "minimum_control_steps": protocol["horizon_grid"]["minimum_control_steps"],
            "maximum_control_steps": protocol["horizon_grid"]["maximum_control_steps"],
            "step": protocol["horizon_grid"]["step"],
        },
        "adequacy_thresholds": {
            "minimum_mean_duty_pct": protocol["adequacy_rule"]["R0_P0b_non_degeneracy"]["minimum_mean_duty_pct"],
            "maximum_mean_duty_pct": protocol["adequacy_rule"]["R0_P0b_non_degeneracy"]["maximum_mean_duty_pct"],
        },
        "contrasts": results,
    }

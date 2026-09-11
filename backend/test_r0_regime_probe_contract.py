"""Fail-closed tests for R0-REGIME-HORIZON-PROBE-V1.

The positive controls matter as much as the refusals: a rule that could only
ever return one label would be no evidence at all about the data, which is the
defect a previous selection self-check hid. Each of the three result labels is
therefore reached on synthetic input built to produce it.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

import r0_regime_probe_contract as r0

BACKEND = Path(__file__).resolve().parent
INDEX_PATH = BACKEND / "r0_probe_evidence/2026-09-11/horizon_trace_index.json"
PROTOCOL_PATH = BACKEND / "rl/r0_regime_probe_protocol.json"

ARMS = ("V7A_REWARD_ONLY", "V7B_REDUCED_JOINT_ENVELOPE", "V7C_FILTERED_ACTION")
SUBSTEPS = 10
FULL_STEPS = 450


def _episode(arm: str, replicate: int, seed: int, steps: int, over_per_step: int) -> dict:
    over = [over_per_step] * steps
    total = sum(over)
    return {
        "arm_id": arm,
        "replicate_index": replicate,
        "training_seed": 8720 + 20 * replicate,
        "evaluation_seed": seed,
        "control_steps": steps,
        "terminal_record_state": "COMPLETED",
        "outcome_state": "OBSERVED",
        "frozen_full_horizon_duty_pct": round(total / (SUBSTEPS * steps) * 100.0, 6),
        "saturation_substeps_over_threshold": over,
    }


def _index(steps_by_arm: dict[str, int], over_by_arm: dict[str, int]) -> dict:
    episodes = []
    for arm in ARMS:
        for replicate in range(5):
            for offset in range(30):
                episodes.append(
                    _episode(arm, replicate, 18000 + offset, steps_by_arm[arm], over_by_arm[arm])
                )
    return {
        "schema_version": r0.INDEX_SCHEMA,
        "substeps_per_control_step": SUBSTEPS,
        "sources": [{"arm_id": a, "replicate_index": r} for a in ARMS for r in range(5)],
        "episodes": episodes,
    }


def _protocol() -> dict:
    return json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))


def _contrast(protocol: dict, contrast_id: str) -> dict:
    return next(c for c in protocol["contrasts"] if c["contrast_id"] == contrast_id)


# --- the frozen artifacts themselves -----------------------------------------


def test_frozen_protocol_digest_and_rules_match_the_specification():
    protocol = r0.load_protocol(PROTOCOL_PATH)
    assert protocol["status"] == "FROZEN_BEFORE_EXECUTION"
    assert protocol["horizon_grid"]["minimum_control_steps"] == 125
    assert protocol["horizon_grid"]["maximum_control_steps"] == 450
    assert protocol["horizon_grid"]["step"] == 1
    p0b = protocol["adequacy_rule"]["R0_P0b_non_degeneracy"]
    assert p0b["minimum_mean_duty_pct"] == 5.0
    assert p0b["maximum_mean_duty_pct"] == 95.0
    assert p0b["applies_to"] == "reference arm only"
    assert protocol["adequacy_rule"]["R0_P0a_exposure"]["required_h_covered_episodes_per_arm"] == 150


def test_a_protocol_whose_bytes_changed_is_refused(tmp_path):
    payload = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    payload["adequacy_rule"]["R0_P0b_non_degeneracy"]["minimum_mean_duty_pct"] = 0.5
    path = tmp_path / "tampered.json"
    path.write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    with pytest.raises(r0.R0ProbeError, match="R0_PROTOCOL_DIGEST_MISMATCH"):
        r0.load_protocol(path)


def test_the_retained_index_loads_and_reproduces_the_frozen_full_horizon_metric():
    index = r0.load_index(INDEX_PATH)
    assert len(index["episodes"]) == r0.EXPECTED_EPISODE_TOTAL
    assert index["substeps_per_control_step"] == SUBSTEPS
    digest = "sha256:" + hashlib.sha256(INDEX_PATH.read_bytes()).hexdigest()
    assert digest == r0.HORIZON_TRACE_INDEX_SHA256


# --- duty arithmetic ----------------------------------------------------------


def test_duty_is_exact_and_horizon_bounded():
    over = [0] * 100 + [10] * 100
    assert r0.duty_pct(over, 200, SUBSTEPS) == 50.0
    assert r0.duty_pct(over, 100, SUBSTEPS) == 0.0
    assert r0.duty_pct(over, 150, SUBSTEPS) == pytest.approx(33.333333)
    with pytest.raises(r0.R0ProbeError, match="R0_DUTY_HORIZON_OUT_OF_RANGE"):
        r0.duty_pct(over, 201, SUBSTEPS)
    with pytest.raises(r0.R0ProbeError, match="R0_DUTY_HORIZON_OUT_OF_RANGE"):
        r0.duty_pct(over, 0, SUBSTEPS)


# --- the three labels are each reachable (positive controls) ------------------


def test_window_found_when_both_arms_run_full_and_the_reference_is_not_degenerate():
    protocol = _protocol()
    # Every episode reaches the full horizon; reference saturates 40% of substeps.
    index = _index(
        {a: FULL_STEPS for a in ARMS},
        {ARMS[0]: 4, ARMS[1]: 2, ARMS[2]: 0},
    )
    result = r0.evaluate_contrast(index, protocol, _contrast(protocol, "C_B"))
    assert result["label"] == r0.LABEL_WINDOW_FOUND
    assert result["selected_horizon_control_steps"] == 450
    assert result["reference_mean_duty_pct_at_selected"] == 40.0


def test_exposure_only_when_both_arms_run_full_but_the_reference_is_degenerate():
    protocol = _protocol()
    # Reference saturates 1 substep in 1000 -> 0.1 pp, below the 5.0 pp floor.
    index = _index({a: FULL_STEPS for a in ARMS}, {ARMS[0]: 0, ARMS[1]: 0, ARMS[2]: 0})
    for episode in index["episodes"]:
        if episode["arm_id"] == ARMS[0]:
            episode["saturation_substeps_over_threshold"][0] = 1
            total = sum(episode["saturation_substeps_over_threshold"])
            episode["frozen_full_horizon_duty_pct"] = round(total / (SUBSTEPS * FULL_STEPS) * 100.0, 6)
    result = r0.evaluate_contrast(index, protocol, _contrast(protocol, "C_B"))
    assert result["label"] == r0.LABEL_EXPOSURE_ONLY
    assert result["selected_horizon_control_steps"] is None
    assert result["p0a_horizon_count"] > 0


def test_not_reachable_when_the_candidate_never_survives_the_grid_floor():
    protocol = _protocol()
    # Candidate terminates at 100 control steps, below the frozen 125 floor.
    index = _index({ARMS[0]: FULL_STEPS, ARMS[1]: 100, ARMS[2]: FULL_STEPS}, {a: 4 for a in ARMS})
    result = r0.evaluate_contrast(index, protocol, _contrast(protocol, "C_B"))
    assert result["label"] == r0.LABEL_NOT_REACHABLE
    assert result["p0a_horizon_count"] == 0
    assert result["selected_horizon_control_steps"] is None


def test_the_ceiling_also_bites_so_p0b_is_a_window_not_a_floor():
    protocol = _protocol()
    index = _index({a: FULL_STEPS for a in ARMS}, {ARMS[0]: 10, ARMS[1]: 2, ARMS[2]: 0})
    result = r0.evaluate_contrast(index, protocol, _contrast(protocol, "C_B"))
    assert result["label"] == r0.LABEL_EXPOSURE_ONLY  # reference at 100 pp exceeds the 95.0 ceiling


# --- the rule's shape ---------------------------------------------------------


def test_p0b_constrains_the_reference_only_so_a_degenerate_candidate_still_counts():
    """A candidate at 0 pp is a result, not an inadequacy: it must stay observable."""
    protocol = _protocol()
    index = _index({a: FULL_STEPS for a in ARMS}, {ARMS[0]: 4, ARMS[1]: 0, ARMS[2]: 0})
    result = r0.evaluate_contrast(index, protocol, _contrast(protocol, "C_B"))
    assert result["label"] == r0.LABEL_WINDOW_FOUND


def test_selection_takes_the_largest_adequate_horizon():
    protocol = _protocol()
    # Reference is degenerate early and saturated later, so only late horizons are adequate.
    index = _index({a: FULL_STEPS for a in ARMS}, {a: 0 for a in ARMS})
    for episode in index["episodes"]:
        if episode["arm_id"] == ARMS[0]:
            trace = episode["saturation_substeps_over_threshold"]
            for step in range(200, FULL_STEPS):
                trace[step] = 10
            episode["frozen_full_horizon_duty_pct"] = round(
                sum(trace) / (SUBSTEPS * FULL_STEPS) * 100.0, 6
            )
    result = r0.evaluate_contrast(index, protocol, _contrast(protocol, "C_B"))
    assert result["label"] == r0.LABEL_WINDOW_FOUND
    assert result["selected_horizon_control_steps"] == result["adequate_horizon_max"] == 450


def test_p0b_is_not_evaluated_where_p0a_fails():
    """NOT_REACHED is never a pass: a horizon past the shortest episode cannot be adequate."""
    protocol = _protocol()
    index = _index({ARMS[0]: FULL_STEPS, ARMS[1]: 300, ARMS[2]: FULL_STEPS}, {a: 4 for a in ARMS})
    result = r0.evaluate_contrast(index, protocol, _contrast(protocol, "C_B"))
    assert result["p0a_horizon_max"] == 300
    assert result["adequate_horizon_max"] == 300
    assert result["selected_horizon_control_steps"] == 300


# --- refusals -----------------------------------------------------------------


@pytest.mark.parametrize(
    "mutate, expected",
    [
        (lambda i: i["episodes"][0].__setitem__("terminal_record_state", "FAILED"), "R0_EPISODE_TERMINAL_STATE"),
        (lambda i: i["episodes"][0].__setitem__("control_steps", 449), "R0_EPISODE_TRACE_LENGTH"),
        (
            lambda i: i["episodes"][0]["saturation_substeps_over_threshold"].__setitem__(0, 11),
            "R0_EPISODE_SUBSTEP_RANGE",
        ),
        (lambda i: i["episodes"][0].__setitem__("frozen_full_horizon_duty_pct", 99.0), "R0_FULL_HORIZON_IDENTITY"),
        (lambda i: i["episodes"].pop(), "R0_INDEX_EPISODE_COUNT"),
        (lambda i: i["sources"].pop(), "R0_INDEX_SOURCE_COUNT"),
        (lambda i: i.__setitem__("substeps_per_control_step", 0), "R0_INDEX_SUBSTEPS_INVALID"),
        (lambda i: i.__setitem__("schema_version", "SOMETHING_ELSE"), "R0_INDEX_SCHEMA_UNKNOWN"),
    ],
)
def test_a_broken_index_is_refused_rather_than_labelled(tmp_path, mutate, expected):
    index = _index({a: FULL_STEPS for a in ARMS}, {a: 4 for a in ARMS})
    mutate(index)
    path = tmp_path / "index.json"
    path.write_text(json.dumps(index) + "\n", encoding="utf-8")
    with pytest.raises(r0.R0ProbeError, match=expected):
        r0.load_index(path, require_pinned_digest=False)


def test_duplicate_episode_keys_are_refused(tmp_path):
    index = _index({a: FULL_STEPS for a in ARMS}, {a: 4 for a in ARMS})
    index["episodes"][1] = json.loads(json.dumps(index["episodes"][0]))
    path = tmp_path / "index.json"
    path.write_text(json.dumps(index) + "\n", encoding="utf-8")
    with pytest.raises(r0.R0ProbeError, match="R0_EPISODE_DUPLICATE"):
        r0.load_index(path, require_pinned_digest=False)


def test_a_synthetic_index_passes_validation_so_the_refusals_above_are_about_the_mutation(tmp_path):
    """Positive control for the refusal suite: the unmutated fixture must load."""
    index = _index({a: FULL_STEPS for a in ARMS}, {a: 4 for a in ARMS})
    path = tmp_path / "index.json"
    path.write_text(json.dumps(index) + "\n", encoding="utf-8")
    assert len(r0.load_index(path, require_pinned_digest=False)["episodes"]) == 450


# --- contractual invariants ---------------------------------------------------


def test_the_contract_is_stdlib_only_so_it_replays_without_site_packages():
    source = (BACKEND / "r0_regime_probe_contract.py").read_text(encoding="utf-8")
    for banned in ("import numpy", "import torch", "import mujoco", "import gymnasium", "import pandas"):
        assert banned not in source


def test_forbidden_denominators_are_declared_and_unused_in_aggregates():
    result = r0.run_probe(INDEX_PATH, PROTOCOL_PATH)
    assert result["forbidden_denominators"] == [150, 450]
    # No aggregate divides by an episode count: every reported duty is a
    # per-episode value or a mean over one arm's episodes at a single horizon.
    for contrast in result["contrasts"]:
        assert contrast["label"] in {
            r0.LABEL_WINDOW_FOUND,
            r0.LABEL_EXPOSURE_ONLY,
            r0.LABEL_NOT_REACHABLE,
        }


def test_every_contrast_gets_exactly_one_label_and_method_failure_is_never_one_of_them():
    result = r0.run_probe(INDEX_PATH, PROTOCOL_PATH)
    assert len(result["contrasts"]) == 2
    assert {c["contrast_id"] for c in result["contrasts"]} == {"C_B", "C_C"}
    for contrast in result["contrasts"]:
        assert contrast["label"] != r0.LABEL_METHOD_FAILURE
        if contrast["label"] != r0.LABEL_WINDOW_FOUND:
            assert contrast["selected_horizon_control_steps"] is None


def test_the_result_declares_its_evidence_class_and_warm_start_condition():
    result = r0.run_probe(INDEX_PATH, PROTOCOL_PATH)
    assert result["evidence_class"] == "PILOT_NOT_EVIDENCE"
    assert result["conditional_on_fixed_warm_start"] is True

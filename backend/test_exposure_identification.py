"""Tests for the generic exposure-identification core.

The decisive test is the cross-check against retained v7 evidence: the module
must reproduce, bit for bit, every replicate paired-difference bound and both
method-level theta bounds that ``seed_variance_summary.json`` records, starting
from nothing but ``raw_replicates.json``.  If it cannot, the generic module and
the frozen seed-variance contract disagree about arithmetic and neither may be
cited until the disagreement is understood.
"""

from __future__ import annotations

import json
import pathlib

import pytest

import exposure_identification as ei

EVIDENCE = pathlib.Path(__file__).resolve().parent / "seed_variance_evidence" / "2026-09-08"


def test_module_is_stdlib_only():
    import ast

    source = (pathlib.Path(__file__).resolve().parent / "exposure_identification.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert imported <= {"math", "typing", "__future__"}


# --------------------------------------------------------------------------- #
# episode level
# --------------------------------------------------------------------------- #


def test_full_exposure_bound_is_a_point_equal_to_the_naive_rate():
    bound = ei.episode_bound_pct(1740, 4500, 4500)
    assert bound["exposure_class"] == ei.EXPOSURE_FULL
    assert bound["point_identified"] is True
    assert bound["lower_pct"] == bound["upper_pct"] == 38.666667
    assert ei.naive_rate_pct(1740, 4500) == 38.666667


def test_early_termination_widens_the_bound_and_naive_sits_inside_it():
    # V7C-like: 1597 of 4500 substeps observed, nothing saturated.
    bound = ei.episode_bound_pct(0, 1597, 4500)
    assert bound["exposure_class"] == ei.EXPOSURE_EARLY
    assert bound["point_identified"] is False
    assert bound["lower_pct"] == 0.0
    assert bound["upper_pct"] == round(100.0 * (4500 - 1597) / 4500, 6)
    naive = ei.naive_rate_pct(0, 1597)
    assert bound["lower_pct"] <= naive <= bound["upper_pct"]


@pytest.mark.parametrize("positive,observed", [(5, 10), (0, 999), (999, 999), (300, 1000)])
def test_naive_rate_always_lies_inside_the_full_horizon_bound(positive, observed):
    bound = ei.episode_bound_pct(positive, observed, 1000)
    naive = ei.naive_rate_pct(positive, observed)
    assert bound["lower_pct"] <= naive <= bound["upper_pct"]


def test_no_exposure_is_its_own_class_and_naive_is_undefined():
    bound = ei.episode_bound_pct(0, 0, 4500)
    assert bound["exposure_class"] == ei.EXPOSURE_NONE
    assert bound["lower_pct"] == 0.0 and bound["upper_pct"] == 100.0
    assert ei.naive_rate_pct(0, 0) is None


@pytest.mark.parametrize(
    "positive,observed,horizon",
    [(11, 10, 100), (5, 101, 100), (-1, 10, 100), (1, 10, 0), (True, 10, 100)],
)
def test_impossible_counts_are_refused(positive, observed, horizon):
    with pytest.raises(ei.ExposureIdentificationError):
        ei.episode_bound_pct(positive, observed, horizon)


# --------------------------------------------------------------------------- #
# aggregation
# --------------------------------------------------------------------------- #


def test_reduction_order_is_left_to_right():
    # Forward: (1.0 + 1e16) loses the 1.0, then -1e16 gives 0.0.
    # Reversed: (-1e16 + 1e16) = 0.0, then + 1.0 keeps it.  Same values, different sum.
    values = [1.0, 1e16, -1e16]
    assert ei.ordered_mean(values) == 0.0
    assert ei.ordered_mean(list(reversed(values))) == 1.0 / 3
    assert ei.ordered_mean(list(reversed(values))) != ei.ordered_mean(values)


def test_interval_mean_has_no_sd_and_refuses_midpoints():
    bounds = [ei.episode_bound_pct(10, 100, 100), ei.episode_bound_pct(0, 50, 100)]
    agg = ei.aggregate_bounds(bounds)
    assert agg["point_identified"] is False
    assert agg["level_sd_pct"] is None
    assert agg["level_sd_reason"] == "BLOCKED_CENSORED_EPISODES_NO_POINT_VALUES"
    assert agg["point_identified_count"] == 1


def test_sign_needs_the_whole_interval_on_one_side():
    negative = ei.paired_difference_pp({"lower_pct": 10.0, "upper_pct": 12.0, "point_identified": False}, {"lower_pct": 20.0, "upper_pct": 21.0, "point_identified": False})
    assert negative["sign"] == ei.SIGN_NEGATIVE and negative["lower_pp"] == -11.0 and negative["upper_pp"] == -8.0
    straddle = ei.paired_difference_pp({"lower_pct": 0.0, "upper_pct": 60.0, "point_identified": False}, {"lower_pct": 36.0, "upper_pct": 36.0, "point_identified": True})
    assert straddle["sign"] == ei.SIGN_UNIDENTIFIED


def test_method_level_refuses_episode_denominators():
    diffs = [{"lower_pp": -1.0, "upper_pp": -0.5, "point_identified": True, "sign": ei.SIGN_NEGATIVE}] * 30
    with pytest.raises(ei.ExposureIdentificationError):
        ei.method_level_pp(diffs, expected_denominator=30, forbidden_denominators=(30, 150))
    with pytest.raises(ei.ExposureIdentificationError):
        ei.method_level_pp(diffs[:5], expected_denominator=4)


def test_compare_classifies_the_four_outcomes():
    bound_zero = {"sign": ei.SIGN_UNIDENTIFIED}
    bound_neg = {"sign": ei.SIGN_NEGATIVE}
    naive_neg = {"asserts_direction": True, "asserted_sign": ei.SIGN_NEGATIVE}
    naive_pos = {"asserts_direction": True, "asserted_sign": ei.SIGN_POSITIVE}
    naive_none = {"asserts_direction": False, "asserted_sign": ei.SIGN_UNIDENTIFIED}
    assert ei.compare_naive_to_bound(naive_neg, bound_zero)["outcome"] == "NAIVE_ASSERTS_DIRECTION_BOUND_CONTAINS_ZERO"
    assert ei.compare_naive_to_bound(naive_neg, bound_neg)["outcome"] == "BOTH_IDENTIFIED_SAME_SIGN"
    assert ei.compare_naive_to_bound(naive_pos, bound_neg)["outcome"] == "BOTH_IDENTIFIED_OPPOSITE_SIGN"
    assert ei.compare_naive_to_bound(naive_none, bound_neg)["outcome"] == "BOUND_IDENTIFIED_NAIVE_UNCERTAIN"
    assert ei.compare_naive_to_bound(naive_none, bound_zero)["outcome"] == "NEITHER_IDENTIFIED"


def test_naive_t_interval_uses_the_replicate_denominator_only():
    naive = ei.naive_method_level_pp([-1.0, -1.2, -0.8, -1.1, -0.9], t_critical=2.776445, expected_denominator=5)
    assert naive["asserts_direction"] is True and naive["asserted_sign"] == ei.SIGN_NEGATIVE
    # 30 evaluation episodes are not 30 replicates: wrong count, and a forbidden denominator.
    with pytest.raises(ei.ExposureIdentificationError):
        ei.naive_method_level_pp([-1.0] * 30, t_critical=2.776445, expected_denominator=5)
    with pytest.raises(ei.ExposureIdentificationError):
        ei.naive_method_level_pp([-1.0] * 30, t_critical=2.776445, expected_denominator=30, forbidden_denominators=(30,))


# --------------------------------------------------------------------------- #
# cross-check against retained v7 seed-variance evidence
# --------------------------------------------------------------------------- #


@pytest.mark.skipif(not EVIDENCE.exists(), reason="retained seed-variance evidence not present")
def test_reproduces_the_retained_seed_variance_summary_bit_for_bit():
    raw = json.loads((EVIDENCE / "bundle" / "raw_replicates.json").read_text(encoding="utf-8"))
    summary = json.loads((EVIDENCE / "analysis" / "seed_variance_summary.json").read_text(encoding="utf-8"))
    reference_id = "V7A_REWARD_ONLY"
    forbidden = tuple(summary["forbidden_denominators"])
    replicates = sorted(raw["replicates"], key=lambda item: item["replicate_index"])

    def cell_bound(replicate: dict, arm_id: str) -> dict:
        arm = next(item for item in replicate["arms"] if item["arm_id"] == arm_id)
        episodes = sorted(arm["episodes"], key=lambda item: item["evaluation_seed"])
        bounds = []
        for episode in episodes:
            b = episode["full_horizon_duty_bound_pct"]
            bounds.append({"lower_pct": b["lower_pct"], "upper_pct": b["upper_pct"], "point_identified": episode["exposure_class"] == ei.EXPOSURE_FULL})
        return ei.aggregate_bounds(bounds)

    checked = 0
    for candidate in summary["candidates"]:
        candidate_id = candidate["candidate_arm_id"]
        expected_method = candidate["method_level"]
        expected_reps = {item["replicate_index"]: item for item in candidate["replicate_paired_differences"]}
        differences = []
        for replicate in replicates:
            diff = ei.paired_difference_pp(cell_bound(replicate, candidate_id), cell_bound(replicate, reference_id))
            exp = expected_reps[replicate["replicate_index"]]
            assert diff["lower_pp"] == exp["lower_pp"], (candidate_id, replicate["replicate_index"], "lower")
            assert diff["upper_pp"] == exp["upper_pp"], (candidate_id, replicate["replicate_index"], "upper")
            assert diff["sign"] == exp["sign"]
            assert diff["point_identified"] == exp["point_identified"]
            differences.append(diff)
            checked += 1
        method = ei.method_level_pp(differences, expected_denominator=summary["replicate_count"], forbidden_denominators=forbidden)
        assert method["theta_bound_pp"]["lower_pp"] == expected_method["theta_bound_pp"]["lower_pp"], candidate_id
        assert method["theta_bound_pp"]["upper_pp"] == expected_method["theta_bound_pp"]["upper_pp"], candidate_id
        assert method["sign"] == expected_method["sign"]
        assert method["sign_identified_replicate_count"] == expected_method["sign_identified_replicate_count"]
        assert method["between_replicate_sd_pp"] == expected_method["between_replicate_sd_pp"]
        assert method["between_replicate_sd_reason"] == expected_method["between_replicate_sd_reason"]
    assert checked == 10  # 2 candidates x 5 replicates


@pytest.mark.skipif(not EVIDENCE.exists(), reason="retained seed-variance evidence not present")
def test_the_v7_point_identified_cells_reproduce_the_recorded_level_sd():
    raw = json.loads((EVIDENCE / "bundle" / "raw_replicates.json").read_text(encoding="utf-8"))
    summary = json.loads((EVIDENCE / "analysis" / "seed_variance_summary.json").read_text(encoding="utf-8"))
    recorded = {}
    for replicate in summary["replicates"]:
        for cell in replicate["arms"]:
            recorded[(replicate["replicate_index"], cell["arm_id"])] = cell
    assert len(recorded) == 15  # 5 replicates x 3 arms
    point_cells = 0
    for replicate in raw["replicates"]:
        for arm in replicate["arms"]:
            key = (replicate["replicate_index"], arm["arm_id"])
            episodes = sorted(arm["episodes"], key=lambda item: item["evaluation_seed"])
            agg = ei.aggregate_bounds(
                [
                    {
                        "lower_pct": e["full_horizon_duty_bound_pct"]["lower_pct"],
                        "upper_pct": e["full_horizon_duty_bound_pct"]["upper_pct"],
                        "point_identified": e["exposure_class"] == ei.EXPOSURE_FULL,
                    }
                    for e in episodes
                ]
            )
            cell = recorded[key]
            assert agg["lower_pct"] == cell["mean_bound_pct"]["lower_pct"], key
            assert agg["upper_pct"] == cell["mean_bound_pct"]["upper_pct"], key
            assert agg["level_sd_pct"] == cell["within_replicate_level_sd_pct"], key
            assert agg["level_sd_reason"] == cell["within_replicate_level_sd_reason"], key
            if agg["level_sd_pct"] is not None:
                point_cells += 1
    # The seed-variance receipt records exactly two point-identified cells (V7A r0, r1).
    assert point_cells == 2

"""Fail-closed tests for the second-case exposure-censoring contract (SC-01..SC-08).

Synthetic bundles are built from counts only.  Each of the five frozen outcome
labels has a fixture that reaches it, so that the label logic is exercised in
both directions rather than by a single happy path.
"""

from __future__ import annotations

import copy
import json
import pathlib
import shutil
import subprocess
import sys

import pytest

import exposure_identification as ei
import second_case_exposure_contract as sc

HERE = pathlib.Path(__file__).resolve().parent
LOCK_FIXTURE = HERE / "environment_locks" / "lock-2026-09-08-seedvar-execution.json"
GIT_SHA = "0123456789abcdef0123456789abcdef01234567"


@pytest.fixture(scope="module")
def protocol() -> dict:
    return sc.load_protocol()


@pytest.fixture(scope="module")
def design(protocol) -> dict:
    return sc.validate_protocol(protocol)


# --------------------------------------------------------------------------- #
# synthetic bundle builder
# --------------------------------------------------------------------------- #


def _episode(design, seed, saturated, realized, *, finite=True):
    horizon = design["horizon_steps"]
    return sc.episode_row(
        evaluation_seed=seed,
        realized_steps=realized,
        saturated_joint_steps=saturated,
        terminated=realized < horizon,
        truncated=realized == horizon,
        all_finite=finite,
        episode_return=100.0,
        trace_sha256="sha256:" + "ab" * 32,
        design=design,
    )


def _cell(design, arm_id, per_seed, *, training_state="COMPLETED", evaluation_state="COMPLETED"):
    """per_seed: callable(seed_index) -> (saturated, realized[, finite])."""
    episodes = []
    if training_state == "COMPLETED" and evaluation_state == "COMPLETED":
        for index, seed in enumerate(design["evaluation_seeds"]):
            spec = per_seed(index)
            finite = spec[2] if len(spec) > 2 else True
            episodes.append(_episode(design, seed, spec[0], spec[1], finite=finite))
    return {
        "schema_version": sc.CELL_SCHEMA,
        "arm_id": arm_id,
        "low_pass_alpha": design["alphas"][arm_id],
        "realized_timesteps": design["expected_realized_timesteps"] if training_state == "COMPLETED" else 0,
        "training_terminal_state": training_state,
        "evaluation_terminal_state": evaluation_state,
        "policy_sha256": ("sha256:" + "cd" * 32) if training_state == "COMPLETED" else None,
        "training_environment_lock_verified": True,
        "evaluation_environment_lock_verified": True,
        "environment_locked_sha256": "sha256:" + "ef" * 32,
        "evaluation_output_sha256": sc.sha256_bytes(sc.json_bytes(episodes)),
        "episodes": episodes,
    }


def _bundle(design, protocol_sha, lock_sha, reference_spec, candidate_spec, *, overrides=None):
    """reference_spec/candidate_spec: callable(replicate_index) -> cell kwargs (per_seed + states)."""
    replicates = []
    for r in range(design["replicate_count"]):
        ref_kwargs = reference_spec(r)
        cand_kwargs = candidate_spec(r)
        replicates.append(
            {
                "replicate_index": r,
                "training_seed": design["training_seeds"][r],
                "arms": [
                    _cell(design, design["reference_arm_id"], **ref_kwargs),
                    _cell(design, design["candidate_arm_id"], **cand_kwargs),
                ],
            }
        )
    raw = {
        "schema_version": sc.RAW_SCHEMA,
        "protocol_id": sc.PROTOCOL_ID,
        "protocol_sha256": protocol_sha,
        "bundle_class": sc.SYNTHETIC_BUNDLE_CLASS,
        "environment_lock_sha256": lock_sha,
        "plant_asset_sha256": design["plant_asset_sha256"],
        "source_git_sha_pre": GIT_SHA,
        "source_git_sha_post": GIT_SHA,
        "source_dirty_pre": False,
        "source_dirty_post": False,
        "replicates": replicates,
    }
    if overrides:
        raw.update(overrides)
    return raw


def _write_bundle(tmp_path, raw):
    root = tmp_path / "bundle"
    root.mkdir()
    shutil.copy(sc.DEFAULT_PROTOCOL, root / "second_case_exposure_protocol.json")
    shutil.copy(LOCK_FIXTURE, root / "environment_lock.json")
    (root / "raw_replicates.json").write_bytes(sc.json_bytes(raw))
    return root


@pytest.fixture(scope="module")
def digests():
    return {
        "protocol": sc.sha256_file(sc.DEFAULT_PROTOCOL),
        "lock": sc.sha256_file(LOCK_FIXTURE),
    }


# Shared specs.  Reference: full exposure, 1800 / 6000 saturated pairs = 30 %.
def REF_FULL_30(_r):
    return {"per_seed": lambda i: (1800, 1000)}


# --------------------------------------------------------------------------- #
# SC-01 protocol
# --------------------------------------------------------------------------- #


def test_frozen_protocol_matches_the_pinned_digest_and_validates(protocol, design):
    assert sc.protocol_digest() == sc.PROTOCOL_SHA256
    assert design["replicate_count"] == 5
    assert design["evaluation_seeds"] == list(range(41000, 41030))
    assert design["training_seeds"] == list(range(40000, 40005))
    assert design["horizon_units"] == 6000
    assert design["alphas"] == {"W2D_A_DIRECT": 1.0, "W2D_C_FILTERED": 0.25}


def test_a_protocol_claiming_preregistration_cannot_load(protocol, tmp_path):
    tampered = copy.deepcopy(protocol)
    tampered["preregistration"]["preregistered"] = True
    path = tmp_path / "p.json"
    path.write_bytes(sc.json_bytes(tampered))
    with pytest.raises(sc.SecondCaseError):
        sc.load_protocol(path, require_pinned_digest=False)


def test_a_protocol_with_a_different_digest_is_refused_by_default(protocol, tmp_path):
    tampered = copy.deepcopy(protocol)
    tampered["purpose"] = tampered["purpose"] + " "
    path = tmp_path / "p.json"
    path.write_bytes(sc.json_bytes(tampered))
    with pytest.raises(sc.SecondCaseError, match="PROTOCOL_DIGEST_MISMATCH"):
        sc.load_protocol(path)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda p: p["training"].__setitem__("training_seed_base", 18000),  # v7 DEV range
        lambda p: p["evaluation"].__setitem__("evaluation_seed_first", 20000),  # sealed FORMAL
        lambda p: p["training"].__setitem__("requested_timesteps", 300000),  # not a whole rollout
        lambda p: p["analysis"].__setitem__("method_level_denominator", 30),
        lambda p: p["arms"][0].__setitem__("low_pass_alpha", 0.5),  # reference must be identity
        lambda p: p["environment"].__setitem__("gymnasium_make_kwargs", {"terminate_when_unhealthy": False}),
        lambda p: p["predictions"].__setitem__("outcome_labels", list(sc.OUTCOME_LABELS[:4])),
        lambda p: p["training"].__setitem__("warm_start", "some_policy"),
    ],
)
def test_protocol_mutations_are_refused(protocol, mutate):
    tampered = copy.deepcopy(protocol)
    mutate(tampered)
    if tampered["training"].get("training_seed_base") == 18000:
        tampered["training"]["training_seeds"] = list(range(18000, 18005))
    if tampered["evaluation"].get("evaluation_seed_first") == 20000:
        tampered["evaluation"]["evaluation_seed_last"] = 20029
    with pytest.raises(sc.SecondCaseError):
        sc.validate_protocol(tampered)


# --------------------------------------------------------------------------- #
# SC-03 episode rows
# --------------------------------------------------------------------------- #


def test_episode_row_classifies_exposure_from_length_not_flags(design):
    full = _episode(design, 41000, 1800, 1000)
    assert full["exposure_class"] == ei.EXPOSURE_FULL and full["comparability_state"] == sc.COMPARABLE
    assert full["naive_duty_pct"] == full["full_horizon_duty_bound_pct"]["lower_pct"] == 30.0
    early = _episode(design, 41000, 0, 300)
    assert early["exposure_class"] == ei.EXPOSURE_EARLY
    assert early["comparability_state"] == sc.EXPOSURE_CENSORED
    assert early["outcome_state"] == sc.OUTCOME_OBSERVED  # OBSERVED does not imply full exposure
    assert early["naive_duty_pct"] == 0.0
    assert early["full_horizon_duty_bound_pct"]["upper_pct"] == 70.0
    nonfinite = _episode(design, 41000, 10, 500, finite=False)
    assert nonfinite["comparability_state"] == sc.METHOD_FAILURE


def test_episode_row_refuses_inconsistent_traces(design):
    with pytest.raises(sc.SecondCaseError, match="TRACE_INCONSISTENT"):
        sc.episode_row(evaluation_seed=41000, realized_steps=500, saturated_joint_steps=0, terminated=False, truncated=False, all_finite=True, episode_return=0.0, trace_sha256="sha256:" + "00" * 32, design=design)
    with pytest.raises(sc.SecondCaseError, match="TRACE_INCONSISTENT"):
        sc.episode_row(evaluation_seed=41000, realized_steps=1001, saturated_joint_steps=0, terminated=True, truncated=False, all_finite=True, episode_return=0.0, trace_sha256="sha256:" + "00" * 32, design=design)
    with pytest.raises(sc.SecondCaseError, match="TRACE_INCONSISTENT"):
        sc.episode_row(evaluation_seed=41000, realized_steps=10, saturated_joint_steps=61, terminated=True, truncated=False, all_finite=True, episode_return=0.0, trace_sha256="sha256:" + "00" * 32, design=design)


# --------------------------------------------------------------------------- #
# SC-05 the five outcomes
# --------------------------------------------------------------------------- #


def test_outcome_uninformative_when_nothing_is_censored(protocol, design, digests):
    raw = _bundle(design, digests["protocol"], digests["lock"], REF_FULL_30, lambda r: {"per_seed": lambda i: (600, 1000)})
    summary = sc.build_summary(raw, protocol)
    assert summary["outcome"] == sc.OUTCOME_UNINFORMATIVE
    assert summary["p1_censoring_present"] is False
    assert summary["censored_replicate_count"] == 0
    # With full exposure the bound is the naive value: -20 pp as a point.
    for rep in summary["replicates"]:
        assert rep["paired_difference_bound_pp"]["lower_pp"] == rep["paired_difference_bound_pp"]["upper_pp"] == -20.0
        assert rep["naive_paired_difference_pp"] == -20.0
    assert summary["method_level_bound"]["between_replicate_sd_pp"] == 0.0
    assert summary["direction_claim_permitted"] is False


def test_outcome_reproduced_when_naive_asserts_and_bound_contains_zero(protocol, design, digests):
    # Candidate falls at step 300 with no saturation: naive 0 %, bound [0, 70] %.
    raw = _bundle(design, digests["protocol"], digests["lock"], REF_FULL_30, lambda r: {"per_seed": lambda i: (0, 300)})
    summary = sc.build_summary(raw, protocol)
    assert summary["p1_censoring_present"] is True and summary["censored_replicate_count"] == 5
    for rep in summary["replicates"]:
        assert rep["naive_paired_difference_pp"] == -30.0
        bound = rep["paired_difference_bound_pp"]
        assert bound["lower_pp"] == -30.0 and bound["upper_pp"] == 40.0 and bound["sign"] == ei.SIGN_UNIDENTIFIED
        assert rep["naive_and_bound_sign_agree"] is False
    assert summary["naive_method_level"]["asserts_direction"] is True
    assert summary["method_level_bound"]["sign"] == ei.SIGN_UNIDENTIFIED
    assert summary["naive_versus_bound"]["outcome"] == "NAIVE_ASSERTS_DIRECTION_BOUND_CONTAINS_ZERO"
    assert summary["outcome"] == sc.OUTCOME_REPRODUCED
    assert summary["p3_observed_does_not_imply_full_exposure"] is True
    assert summary["p3_early_terminated_episodes"] == 150 == summary["p3_early_terminated_with_observed_outcome"]


def test_outcome_agree_when_censoring_is_too_small_to_flip_the_sign(protocol, design, digests):
    # Candidate survives 900 steps with 540 saturated pairs: naive 10 %, bound [9, 19] %.
    raw = _bundle(design, digests["protocol"], digests["lock"], REF_FULL_30, lambda r: {"per_seed": lambda i: (540, 900)})
    summary = sc.build_summary(raw, protocol)
    assert summary["p1_censoring_present"] is True
    rep = summary["replicates"][0]
    assert rep["paired_difference_bound_pp"]["lower_pp"] == -21.0 and rep["paired_difference_bound_pp"]["upper_pp"] == -11.0
    assert rep["paired_difference_bound_pp"]["sign"] == ei.SIGN_NEGATIVE
    assert summary["naive_versus_bound"]["outcome"] == "BOTH_IDENTIFIED_SAME_SIGN"
    assert summary["outcome"] == sc.OUTCOME_AGREE
    assert summary["method_level_bound"]["between_replicate_sd_pp"] is None


def test_outcome_bound_identified_while_naive_is_uncertain(protocol, design, digests):
    # Candidate survives 990 steps; naive values swing so the naive t-interval covers 0,
    # while every replicate's bound excludes 0.
    saturated = [1723, 297, 1663, 356, 1604]  # ~29.0, 5.0, 28.0, 6.0, 27.0 % of 5940 pairs
    raw = _bundle(design, digests["protocol"], digests["lock"], REF_FULL_30, lambda r: {"per_seed": (lambda i, r=r: (saturated[r], 990))})
    summary = sc.build_summary(raw, protocol)
    assert summary["p1_censoring_present"] is True
    for rep in summary["replicates"]:
        assert rep["paired_difference_bound_pp"]["sign"] == ei.SIGN_NEGATIVE
    assert summary["method_level_bound"]["sign"] == ei.SIGN_NEGATIVE
    assert summary["naive_method_level"]["asserts_direction"] is False
    assert summary["outcome"] == sc.OUTCOME_BOUND_ONLY


def test_outcome_blocked_keeps_the_denominator_and_issues_no_decision(protocol, design, digests):
    def candidate(r):
        if r == 2:
            return {"per_seed": lambda i: (0, 300), "training_state": "FAILED"}
        return {"per_seed": lambda i: (0, 300)}

    raw = _bundle(design, digests["protocol"], digests["lock"], REF_FULL_30, candidate)
    summary = sc.build_summary(raw, protocol)
    assert summary["outcome"] == sc.OUTCOME_BLOCKED
    assert summary["method_level_bound"] is None and summary["naive_method_level"] is None
    assert summary["replicates"][2]["paired_difference_bound_pp"]["sign"] == "NULL"
    assert summary["replicates"][2]["arms"][1]["cell_state"] == sc.CELL_BLOCKED
    assert len(summary["replicates"]) == 5
    assert any(b["blocker_id"] == "METHOD_FAILURE_BLOCKS_METHOD_LEVEL" and b["replicate_indices"] == [2] for b in summary["retained_blockers"])


def test_a_nonfinite_episode_is_a_method_failure_not_censoring(protocol, design, digests):
    raw = _bundle(design, digests["protocol"], digests["lock"], REF_FULL_30, lambda r: {"per_seed": lambda i: (0, 300, i != 7)})
    summary = sc.build_summary(raw, protocol)
    assert summary["outcome"] == sc.OUTCOME_BLOCKED
    cell = summary["replicates"][0]["arms"][1]
    assert cell["comparability_counts"][sc.METHOD_FAILURE] == 1
    assert cell["comparability_counts"][sc.EXPOSURE_CENSORED] == 29


# --------------------------------------------------------------------------- #
# SC-02 / SC-04 raw validation
# --------------------------------------------------------------------------- #


def _good_raw(design, digests):
    return _bundle(design, digests["protocol"], digests["lock"], REF_FULL_30, lambda r: {"per_seed": lambda i: (0, 300)})


def test_tampered_episode_rows_are_caught_by_the_output_digest(protocol, design, digests):
    raw = _good_raw(design, digests)
    raw["replicates"][0]["arms"][1]["episodes"][0]["saturated_joint_steps"] = 5
    with pytest.raises(sc.SecondCaseError):
        sc.validate_raw_bundle(raw, protocol)


def test_wrong_realized_timesteps_are_refused(protocol, design, digests):
    raw = _good_raw(design, digests)
    raw["replicates"][1]["arms"][0]["realized_timesteps"] = 300000
    with pytest.raises(sc.SecondCaseError, match="realized_timesteps"):
        sc.validate_raw_bundle(raw, protocol)


def test_dirty_source_is_refused(protocol, design, digests):
    raw = _good_raw(design, digests)
    raw["source_dirty_post"] = True
    with pytest.raises(sc.SecondCaseError, match="GIT_NOT_CLEAN"):
        sc.validate_raw_bundle(raw, protocol)


def test_unverified_lock_flag_is_refused(protocol, design, digests):
    raw = _good_raw(design, digests)
    raw["replicates"][0]["arms"][0]["training_environment_lock_verified"] = False
    with pytest.raises(sc.SecondCaseError, match="lock_verified"):
        sc.validate_raw_bundle(raw, protocol)


def test_wrong_plant_digest_is_refused(protocol, design, digests):
    raw = _good_raw(design, digests)
    raw["plant_asset_sha256"] = "sha256:" + "11" * 32
    with pytest.raises(sc.SecondCaseError, match="plant"):
        sc.validate_raw_bundle(raw, protocol)


def test_episode_level_denominators_are_refused_by_the_core(design):
    diffs = [{"lower_pp": -1.0, "upper_pp": -1.0, "point_identified": True, "sign": ei.SIGN_NEGATIVE}] * 30
    with pytest.raises(ei.ExposureIdentificationError):
        ei.method_level_pp(diffs, expected_denominator=30, forbidden_denominators=design["forbidden_denominators"])


# --------------------------------------------------------------------------- #
# SC-06 analyse + replay
# --------------------------------------------------------------------------- #


def test_analyse_then_isolated_replay_is_bit_exact(tmp_path, design, digests):
    raw = _good_raw(design, digests)
    root = _write_bundle(tmp_path, raw)
    output = tmp_path / "analysis"
    receipt = sc.analyse(root, output)
    assert receipt["outcome"] == sc.OUTCOME_REPRODUCED
    assert receipt["environment_lock"]["environment_lock_class"] == "MEASURED_ENVIRONMENT_LOCK"
    summary_path = output / "second_case_summary.json"
    # In-process replay
    result = sc.run_replay(root, summary_path)
    assert result["identical"] is True
    # Isolated interpreter: no site packages, no cwd on sys.path.
    proc = subprocess.run(
        [sys.executable, "-I", "-S", str(HERE / "second_case_exposure_contract.py"), "replay", "--bundle", str(root), "--summary", str(summary_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["identical"] is True
    assert payload["interpreter_isolated"] is True and payload["site_disabled"] is True
    assert payload["third_party_modules_loaded"] == []


def test_replay_detects_a_tampered_summary(tmp_path, design, digests):
    raw = _good_raw(design, digests)
    root = _write_bundle(tmp_path, raw)
    output = tmp_path / "analysis"
    sc.analyse(root, output)
    summary_path = output / "second_case_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["outcome"] = sc.OUTCOME_AGREE
    summary_path.write_bytes(sc.json_bytes(summary))
    with pytest.raises(sc.SecondCaseError, match="REPLAY_MISMATCH"):
        sc.run_replay(root, summary_path)


def test_analyse_refuses_to_write_inside_the_bundle(tmp_path, design, digests):
    raw = _good_raw(design, digests)
    root = _write_bundle(tmp_path, raw)
    with pytest.raises(sc.SecondCaseError, match="read-only"):
        sc.analyse(root, root / "analysis")


def test_bundle_with_mismatched_protocol_copy_is_refused(tmp_path, design, digests, protocol):
    raw = _good_raw(design, digests)
    root = _write_bundle(tmp_path, raw)
    tampered = copy.deepcopy(protocol)
    tampered["purpose"] += " "
    (root / "second_case_exposure_protocol.json").write_bytes(sc.json_bytes(tampered))
    with pytest.raises(sc.SecondCaseError, match="protocol"):
        sc.read_bundle(root)


def test_summary_never_permits_a_direction_claim_or_selection(protocol, design, digests):
    for cand in (lambda r: {"per_seed": lambda i: (0, 300)}, lambda r: {"per_seed": lambda i: (540, 900)}):
        summary = sc.build_summary(_bundle(design, digests["protocol"], digests["lock"], REF_FULL_30, cand), protocol)
        assert summary["direction_claim_permitted"] is False
        assert summary["selection_permitted"] is False
        assert summary["preregistered"] is False
        assert summary["paper_data_ready"] is False


# --------------------------------------------------------------------------- #
# retained development evidence
# --------------------------------------------------------------------------- #

EVIDENCE = HERE / "second_case_evidence" / "2026-09-08"


@pytest.mark.skipif(not EVIDENCE.exists(), reason="retained second-case evidence not present")
def test_retained_development_evidence_revalidates_and_replays_exactly():
    bundle = sc.read_bundle(EVIDENCE / "bundle")
    assert bundle["protocol_sha256"] == sc.PROTOCOL_SHA256
    stats = sc.validate_raw_bundle(bundle["raw"], bundle["protocol"])
    assert stats["bundle_class"] == sc.DEVELOPMENT_BUNDLE_CLASS
    assert stats["terminal_record_count"] == 300
    summary_path = EVIDENCE / "analysis" / "second_case_summary.json"
    assert sc.run_replay(EVIDENCE / "bundle", summary_path)["identical"] is True
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    receipt = json.loads((EVIDENCE / "analysis" / "second_case_receipt.json").read_text(encoding="utf-8"))
    assert receipt["summary_sha256"] == sc.sha256_file(summary_path)
    # The frozen decision, as recorded.
    assert summary["outcome"] == sc.OUTCOME_REPRODUCED == receipt["outcome"]
    assert summary["p1_censoring_present"] is True and summary["censored_replicate_count"] == 5
    assert summary["p3_observed_does_not_imply_full_exposure"] is True
    assert summary["naive_method_level"]["asserts_direction"] is True
    assert summary["method_level_bound"]["sign"] == ei.SIGN_UNIDENTIFIED
    assert summary["method_level_bound"]["sign_identified_replicate_count"] == 0
    # And what it never permits.
    assert summary["direction_claim_permitted"] is False
    assert summary["preregistered"] is False
    assert summary["paper_data_ready"] is False

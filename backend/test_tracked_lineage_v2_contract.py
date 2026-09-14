"""Acceptance tests for TRACKED-LINEAGE-TRAINING-V2 (specification section 10).

Every criterion in both directions, as in V1. The tests that matter most here
are the ones about the resume source: V2's whole claim to reconstructable
provenance rests on having continued from exactly the V1 checkpoint the protocol
froze, and on that checkpoint being in version control.
"""

from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import tracked_lineage_v2_contract as tl2
import tracked_lineage_contract as tl1
from rl import train_ppo


REPO_ROOT = Path(__file__).resolve().parent.parent
PROTOCOL_PATH = REPO_ROOT / "backend" / "rl" / "tracked_lineage_training_v2_protocol.json"
SPEC_PATH = REPO_ROOT / "docs" / "TRACKED_LINEAGE_TRAINING_V2_SPEC.md"
V1_REFERENCE_STEPS = 1_999_968


@pytest.fixture()
def protocol() -> dict:
    return tl2.load_protocol()


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# The digest chain and the mandatory disclosure
# ---------------------------------------------------------------------------

def test_the_digest_chain_is_pinned_and_verifies(protocol):
    payload = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    assert payload["specification_sha256"] == _sha256(SPEC_PATH)
    assert tl2.PROTOCOL_SHA256 == _sha256(PROTOCOL_PATH)
    baseline = payload["source_baseline"]
    assert baseline["training_driver_source_sha256"] == _sha256(
        REPO_ROOT / baseline["training_driver_source"]
    )


def test_the_mandatory_disclosure_is_present_and_says_what_it_must(protocol):
    """The requirement V1 sections 9 and 14 impose on any budget increase.

    Checked as a contract term rather than left to prose, because it is the one
    thing that makes V2's result readable at all.
    """
    disclosure = protocol["mandatory_disclosure"]
    assert disclosure["designed_after_the_v1_result_was_known"] is True
    assert "TL_BUDGET_EXHAUSTED" in disclosure["what_was_known"]
    assert "LESS evidential weight" in disclosure["evidential_weight"]
    # It must explicitly refuse the extrapolation that would make V2 look
    # pre-justified.
    assert "30/30" in disclosure["does_not_claim"]
    assert "not done here" in disclosure["does_not_claim"]


def test_the_threshold_is_unchanged_from_v1(protocol):
    """V2 raises the input, not the pass mark."""
    assert protocol["unchanged_from_v1"]["full_exposure_threshold"].startswith("30/30")
    v1_protocol = tl1.load_protocol()
    assert v1_protocol["full_exposure_threshold"]["value"] == "30/30"
    assert tl2.classify(protocol, [(29, 30)] * 5, curve_converged=True)["label"] == (
        tl2.LABEL_NOT_ATTAINED
    )
    assert tl2.classify(protocol, [(30, 30)] * 5, curve_converged=True)["label"] == (
        tl2.LABEL_ATTAINED
    )


def test_a_protocol_whose_bytes_changed_is_refused(tmp_path: Path):
    payload = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    payload["training_design"]["increment_planned_timesteps"] = 4_000_000
    forged = tmp_path / "forged.json"
    forged.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    with pytest.raises(tl2.TrackedLineageMethodFailure, match="TL2_PROTOCOL_DIGEST_MISMATCH"):
        tl2.load_protocol(forged)


# ---------------------------------------------------------------------------
# TL2-01 / TL2-02: driver identity
# ---------------------------------------------------------------------------

def test_tl2_01_driver_digests_match_and_eval_policy_is_unmodified(protocol):
    measured = tl2.verify_driver_digests(protocol)
    assert set(measured) == {"backend/rl/train_ppo.py", "backend/rl/eval_policy.py"}
    assert measured["backend/rl/eval_policy.py"] == (
        "sha256:0cf274341a10a56fbf544d86eab4bfbfd6f630056689280af51aff111b0058d4"
    )


def test_tl2_02_both_driver_digests_are_carried_and_differ(protocol):
    baseline = protocol["source_baseline"]
    current = baseline["training_driver_source_sha256"]
    superseded = baseline["superseded_training_driver_source_sha256"]
    assert current and superseded and current != superseded
    # The superseded value is V1's pin, which V2's edit stops making true of the
    # live repository. That is the fact this protocol exists to disclose.
    assert superseded == tl1.load_protocol()["source_baseline"][
        "training_driver_source_sha256"
    ]


# ---------------------------------------------------------------------------
# TL2-03 / TL2-04: the resume source
# ---------------------------------------------------------------------------

def _manifest(index: int, seed: int, source: dict) -> dict:
    return {
        "run_id": f"stand_start_walk_stop_0p7_tracked_lineage_b2_r{index}-run",
        "profile": {"warm_start_policy_id": None},
        "warm_start": None,
        "resume": {
            "artifact": source["relative_path"],
            "sha256": source["sha256"],
            "mode": "PPO_FULL_STATE_RESUME_V1",
            "source_num_timesteps": V1_REFERENCE_STEPS,
        },
        "resolved": {"seed_base": seed},
    }


def _manifests(protocol: dict) -> list[dict]:
    seeds = protocol["training_design"]["training_seeds"]
    sources = protocol["tracked_warm_start"]["sources"]
    return [_manifest(i, s, sources[str(i)]) for i, s in enumerate(seeds)]


def test_tl2_03_a_correct_resume_is_accepted(protocol):
    tl2.verify_resume_sources(protocol, _manifests(protocol))


def test_tl2_03_resume_is_required_not_optional(protocol):
    """The inverse of V1's TL-03, which required resume to be null."""
    manifests = _manifests(protocol)
    manifests[2]["resume"] = None
    with pytest.raises(tl2.TrackedLineageMethodFailure, match="TL2_RESUME_MISSING"):
        tl2.verify_resume_sources(protocol, manifests)


def test_tl2_03_a_resume_from_the_wrong_checkpoint_fails_closed(protocol):
    manifests = _manifests(protocol)
    manifests[1]["resume"]["sha256"] = "sha256:" + "0" * 64
    with pytest.raises(tl2.TrackedLineageMethodFailure, match="TL2_RESUME_DIGEST_MISMATCH"):
        tl2.verify_resume_sources(protocol, manifests)


def test_tl2_03_a_resume_from_another_replicates_checkpoint_fails_closed(protocol):
    """A pinned checkpoint is not enough; it must be THIS replicate's."""
    manifests = _manifests(protocol)
    sources = protocol["tracked_warm_start"]["sources"]
    manifests[0]["resume"]["sha256"] = sources["3"]["sha256"]
    with pytest.raises(tl2.TrackedLineageMethodFailure, match="TL2_RESUME_DIGEST_MISMATCH"):
        tl2.verify_resume_sources(protocol, manifests)


def test_tl2_03_a_resume_at_the_wrong_step_count_fails_closed(protocol):
    """V1's policy.zip sits at 2_015_232, the reference at 1_999_968."""
    manifests = _manifests(protocol)
    manifests[4]["resume"]["source_num_timesteps"] = 2_015_232
    with pytest.raises(tl2.TrackedLineageMethodFailure, match="TL2_RESUME_STEP_COUNT_MISMATCH"):
        tl2.verify_resume_sources(protocol, manifests)


def test_tl2_03_warm_start_must_still_be_null(protocol):
    """V2 resumes full PPO state; it does not transplant weights."""
    manifests = _manifests(protocol)
    manifests[3]["warm_start"] = {"policy_id": "v5"}
    with pytest.raises(tl2.TrackedLineageMethodFailure, match="TL2_WARM_START_RECORD_PRESENT"):
        tl2.verify_resume_sources(protocol, manifests)


def test_tl2_04_every_resume_source_is_version_controlled(protocol):
    """The point of the driver change: a gitignored source cannot be rebuilt."""
    for entry in protocol["tracked_warm_start"]["sources"].values():
        assert entry["relative_path"].startswith("backend/tracked_lineage_evidence/")
        path = REPO_ROOT / entry["relative_path"]
        assert path.is_file()
        assert _sha256(path) == entry["sha256"]
    tl2.verify_resume_sources(protocol, _manifests(protocol))


def test_tl2_04_a_gitignored_resume_source_fails_closed(protocol):
    mutated = copy.deepcopy(protocol)
    mutated["tracked_warm_start"]["sources"]["0"]["relative_path"] = (
        "backend/rl/artifacts/stand_start_walk_stop_0p7_tracked_lineage_b1_r0-run/policy.zip"
    )
    with pytest.raises(
        tl2.TrackedLineageMethodFailure, match="TL2_RESUME_SOURCE_NOT_VERSION_CONTROLLED"
    ):
        tl2.verify_resume_sources(mutated, _manifests(mutated))


def test_tl2_04_the_pinned_sources_are_the_reference_not_the_byproduct(protocol):
    tl2.verify_resume_source_is_not_the_byproduct(protocol)
    mutated = copy.deepcopy(protocol)
    mutated["tracked_warm_start"]["sources"]["2"]["realized_timesteps"] = 2_015_232
    with pytest.raises(
        tl2.TrackedLineageMethodFailure, match="TL2_RESUME_SOURCE_NOT_THE_REFERENCE"
    ):
        tl2.verify_resume_source_is_not_the_byproduct(mutated)


# ---------------------------------------------------------------------------
# TL2-05: seeds
# ---------------------------------------------------------------------------

def test_tl2_05_seeds_match_v1_in_order(protocol):
    assert tl2.verify_training_seeds(protocol, _manifests(protocol)) == [
        9100, 9112, 9124, 9136, 9148
    ]
    v1_protocol = tl1.load_protocol()
    assert protocol["training_design"]["training_seeds"] == (
        v1_protocol["training_design"]["training_seeds"]
    )


def test_tl2_05_a_permuted_seed_order_fails_closed(protocol):
    """Replicate i must continue replicate i, so order is part of the identity."""
    manifests = _manifests(protocol)
    manifests[0]["resolved"]["seed_base"], manifests[1]["resolved"]["seed_base"] = (
        manifests[1]["resolved"]["seed_base"], manifests[0]["resolved"]["seed_base"],
    )
    with pytest.raises(
        tl2.TrackedLineageMethodFailure, match="TL2_TRAINING_SEED_ORDER_MISMATCH"
    ):
        tl2.verify_training_seeds(protocol, manifests)


def test_tl2_05_evaluation_seed_reuse_is_disclosed(protocol):
    design = protocol["evaluation_design"]
    assert (design["evaluation_seed_start"], design["evaluation_seed_end"]) == (22000, 22029)
    assert "second use" in design["seed_reuse_disclosure"]
    assert "DEVELOPMENT_EXHAUSTED" in design["seed_reuse_disclosure"]


# ---------------------------------------------------------------------------
# TL2-06: the step arithmetic and the checkpoint landings
# ---------------------------------------------------------------------------

def test_tl2_06_the_resume_arithmetic_is_the_one_that_was_verified(protocol):
    design = protocol["training_design"]
    base = design["resume_from_realized_timesteps"]
    rollout = design["rollout_size"]
    target = base + design["increment_planned_timesteps"]
    total = base
    while total < target:
        total += rollout
    assert design["stop_condition_num_timesteps"] == target
    assert design["total_realized_timesteps"] == total == 4_015_200
    assert design["increment_realized_timesteps"] == total - base == 2_015_232


def test_tl2_06_checkpoints_land_where_the_protocol_says(protocol):
    design = protocol["training_design"]
    save_freq = design["checkpoint_interval"] // 12
    base = design["resume_from_realized_timesteps"]
    expected = [base + save_freq * 12 * k for k in range(1, 5)]
    assert expected == [2_499_960, 2_999_952, 3_499_944, 3_999_936]
    assert protocol["checkpoint_lineage"]["expected_realized_timesteps"] == expected
    assert all(value % 500_000 for value in expected)


def test_tl2_06_the_storage_decision_is_recorded_with_its_cost(protocol):
    lineage = protocol["checkpoint_lineage"]
    assert lineage["storage"] == "GIT_DIRECT"
    assert lineage["per_replicate_count"] == 4 and lineage["total_count"] == 20
    assert "Option A" in lineage["owner_decision"]
    # The cost exceeds what V1 accepted, so it was re-confirmed, not carried over.
    assert "EXCEEDS" in lineage["accepted_cost"]
    assert "not cancelled" in lineage["accepted_cost"] or "NOT cancelled" in lineage["accepted_cost"]


# ---------------------------------------------------------------------------
# TL2-09: labels
# ---------------------------------------------------------------------------

def test_tl2_09_one_positive_control_per_label(protocol):
    assert tl2.classify(protocol, [(30, 30)] * 5, curve_converged=True)["label"] == tl2.LABEL_ATTAINED
    partial = tl2.classify(
        protocol, [(30, 30), (29, 30), (30, 30), (0, 30), (30, 30)], curve_converged=True
    )
    assert partial["label"] == tl2.LABEL_PARTIAL
    assert partial["replicates_attaining_threshold"] == 3
    assert tl2.classify(protocol, [(0, 30)] * 5, curve_converged=True)["label"] == (
        tl2.LABEL_NOT_ATTAINED
    )
    assert tl2.classify(protocol, [(0, 30)] * 5, curve_converged=False)["label"] == (
        tl2.LABEL_BUDGET_EXHAUSTED
    )


def test_tl2_09_labels_are_mutually_exclusive_unlike_v1s(protocol):
    """V1 amendment 03's correction, applied at design time rather than after."""
    labels = protocol["outcome_labels"]
    assert "converged" in labels["TL2_REFERENCE_NOT_ATTAINED"]
    assert "not converged" in labels["TL2_BUDGET_EXHAUSTED"]
    assert "amendment 03" in protocol["label_precedence_fixed"]


def test_tl2_09_the_convergence_verdict_has_no_default(protocol):
    import inspect
    param = inspect.signature(tl2.classify).parameters["curve_converged"]
    assert param.default is inspect.Parameter.empty
    assert param.kind is inspect.Parameter.KEYWORD_ONLY
    with pytest.raises(TypeError):
        tl2.classify(protocol, [(0, 30)] * 5)


def test_tl2_09_the_convergence_rule_may_not_be_retuned(protocol):
    """It is V1's rule, already declared and applied, not a fresh knob."""
    assert "already declared and applied in V1" in protocol["convergence_rule"]
    assert "MAY NOT be retuned" in protocol["convergence_rule"]
    from rl import retain_tracked_lineage_curves as curves
    assert curves.CONVERGED_SLOPE_FRACTION == 0.10
    assert curves.CONVERGED_ABSOLUTE_SLOPE == 1.0


def test_tl2_09_method_failure_is_never_downgraded(protocol):
    failures = [
        (tl2.verify_resume_sources, (protocol, [{"run_id": "r0", "resume": None}]), {}),
        (tl2.verify_run_lock_bindings, ({"r0": "RUN_LOCK_UNBOUND"},), {}),
        (tl2.verify_evaluation_seeds, (protocol, [{"run_id": "r0", "evaluation_seeds": [20000]}]), {}),
    ]
    for function, args, kwargs in failures:
        with pytest.raises(tl2.TrackedLineageMethodFailure) as caught:
            function(*args, **kwargs)
        assert not any(label in str(caught.value) for label in tl2.RESULT_LABELS)
    assert tl2.LABEL_METHOD_FAILURE not in tl2.RESULT_LABELS


def test_tl2_the_escalation_rule_is_recorded(protocol):
    """Another TL2_BUDGET_EXHAUSTED does not authorise simply adding budget."""
    rule = protocol["escalation_rule"]
    assert "does NOT authorize" in rule.replace("not authorize", "NOT authorize")
    assert "new protocol version" in rule


def test_tl2_the_claim_boundary_refuses_the_comparisons_it_must(protocol):
    joined = " ".join(protocol["claim_boundary"])
    assert "Does NOT support that more steps would reach 30/30" in joined
    assert "method-variance" in joined
    assert "no control" in joined
    result = tl2.classify(protocol, [(30, 30)] * 5, curve_converged=True)
    assert result["not_independent_of_v1"] is True


# ---------------------------------------------------------------------------
# The driver, from the profile side
# ---------------------------------------------------------------------------

def test_the_v2_profiles_declare_the_v2_identity_and_carry_the_increment():
    profiles = train_ppo.load_profiles().profiles
    v2 = [
        item for item in profiles
        if item.tracked_lineage_protocol_id == "TRACKED-LINEAGE-TRAINING-V2"
    ]
    assert len(v2) == 5
    for item in v2:
        assert item.pilot_protocol_id is None and item.seedvar_protocol_id is None
        assert item.warm_start_policy_id is None
        assert item.environment_id == "motion_task_phase_observable_v5"
        assert item.planned_timesteps == 2_000_000
        assert item.parallel_envs == 12
    assert [item.seed_base for item in v2] == [9100, 9112, 9124, 9136, 9148]


def test_v1s_guard_still_refuses_resume(tmp_path: Path):
    """V1 is executed evidence; V2 must not have loosened its rules."""
    profile = train_ppo.resolve_profile("stand_start_walk_stop_0p7_tracked_lineage_b1_r0")
    source = train_ppo.tracked_lineage_v2_resume_source(0)
    with pytest.raises(ValueError, match="TRACKED_LINEAGE_CHECKPOINT_OVERRIDE_FORBIDDEN"):
        train_ppo.validate_tracked_lineage_request(
            profile=profile,
            run_id=train_ppo.tracked_lineage_run_id(profile),
            total=2_000_000, n_envs=12, seed_base=9100,
            replicate_index=None, seed_base_from_cli=False, device="cpu",
            resume_from=REPO_ROOT / source["relative_path"],
            warm_start_from=None, smoke=False, preflight=False,
            source_git={"available": True, "git_sha": "x", "working_tree_dirty": False},
        )


def test_the_v2_guard_requires_the_pinned_resume():
    profile = train_ppo.resolve_profile("stand_start_walk_stop_0p7_tracked_lineage_b2_r1")
    source = train_ppo.tracked_lineage_v2_resume_source(1)
    common = dict(
        profile=profile, run_id=train_ppo.tracked_lineage_v2_run_id(profile),
        total=2_000_000, n_envs=12, seed_base=9112, replicate_index=None,
        seed_base_from_cli=False, device="cpu", warm_start_from=None,
        smoke=False, preflight=False,
        source_git={"available": True, "git_sha": "x", "working_tree_dirty": False},
    )
    train_ppo.validate_tracked_lineage_v2_request(
        resume_from=REPO_ROOT / source["relative_path"], **common
    )
    with pytest.raises(ValueError, match="TRACKED_LINEAGE_V2_RESUME_REQUIRED"):
        train_ppo.validate_tracked_lineage_v2_request(resume_from=None, **common)
    other = train_ppo.tracked_lineage_v2_resume_source(4)
    with pytest.raises(ValueError, match="TRACKED_LINEAGE_V2_RESUME_PATH_MISMATCH"):
        train_ppo.validate_tracked_lineage_v2_request(
            resume_from=REPO_ROOT / other["relative_path"], **common
        )


def test_the_v2_checkpoint_interval_comes_from_the_v2_protocol():
    assert train_ppo.tracked_lineage_v2_checkpoint_interval() == 500_000


def test_a_v2_profile_passes_through_both_guards():
    """The dispatch path main() actually takes, which no earlier test covered.

    main() calls the V2 guard and then the V1 guard on every run. V1's guard
    originally returned early only when tracked_lineage_protocol_id was None, so
    a V2 profile - which sets that field - fell through into V1's branch and
    raised TRACKED_LINEAGE_PROFILE_ID_MISMATCH on the b2_ profile id. Testing
    each guard alone missed it; this exercises the pair the way main() does.
    """
    profile = train_ppo.resolve_profile("stand_start_walk_stop_0p7_tracked_lineage_b2_r3")
    source = train_ppo.tracked_lineage_v2_resume_source(3)
    common = dict(
        profile=profile, run_id=train_ppo.tracked_lineage_v2_run_id(profile),
        total=2_000_000, n_envs=12, seed_base=9136, replicate_index=None,
        seed_base_from_cli=False, device="cpu",
        resume_from=REPO_ROOT / source["relative_path"], warm_start_from=None,
        smoke=False, preflight=False,
        source_git={"available": True, "git_sha": "x", "working_tree_dirty": False},
    )
    train_ppo.validate_tracked_lineage_v2_request(**common)
    # The V1 guard must now decline this profile rather than choke on it.
    train_ppo.validate_tracked_lineage_request(**common)


def test_a_v1_profile_passes_through_both_guards():
    """The mirror case: V2's guard must decline a V1 profile, not choke."""
    profile = train_ppo.resolve_profile("stand_start_walk_stop_0p7_tracked_lineage_b1_r2")
    common = dict(
        profile=profile, run_id=train_ppo.tracked_lineage_run_id(profile),
        total=2_000_000, n_envs=12, seed_base=9124, replicate_index=None,
        seed_base_from_cli=False, device="cpu", resume_from=None,
        warm_start_from=None, smoke=False, preflight=False,
        source_git={"available": True, "git_sha": "x", "working_tree_dirty": False},
    )
    train_ppo.validate_tracked_lineage_v2_request(**common)
    train_ppo.validate_tracked_lineage_request(**common)

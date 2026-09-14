"""Acceptance tests for TRACKED-LINEAGE-TRAINING-V1 (specification section 12).

Every criterion is tested in both directions. A test that only shows the happy
path proves the code runs, not that the guard fires, and a guard that never
fires is indistinguishable from no guard at all.
"""

from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import tracked_lineage_contract as tl
from rl import train_ppo


REPO_ROOT = Path(__file__).resolve().parent.parent
PROTOCOL_PATH = REPO_ROOT / "backend" / "rl" / "tracked_lineage_training_protocol.json"
SPEC_PATH = REPO_ROOT / "docs" / "TRACKED_LINEAGE_TRAINING_SPEC.md"


@pytest.fixture()
def protocol() -> dict:
    return tl.load_protocol()


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


# V1's implementation commit. TL-01 is an EXECUTION-TIME precondition ("re-derive
# before execution, refuse to execute on mismatch"), so its tests must ask what
# was true when V1 executed, not what the working tree holds today. Asking the
# live tree would freeze train_ppo.py forever, which V1 section 6.2 explicitly
# anticipated other lines would need to change - the same defect
# LOCKBIND-AMENDMENT-01 corrected in LB-12.
V1_IMPLEMENTATION_COMMIT = "2036625"


def _materialise_at_v1_commit(root: Path, *relatives: str) -> None:
    for relative in relatives:
        blob = subprocess.run(
            ["git", "cat-file", "-p", f"{V1_IMPLEMENTATION_COMMIT}:{relative}"],
            cwd=REPO_ROOT, capture_output=True, check=True,
        ).stdout
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(blob)


# ---------------------------------------------------------------------------
# The digest chain
# ---------------------------------------------------------------------------

def test_the_three_layer_digest_chain_is_pinned_and_verifies():
    payload = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    # Layer 1: protocol pins the specification.
    assert payload["specification_sha256"] == _sha256(SPEC_PATH)
    # Layer 2: this contract module pins the protocol.
    assert tl.PROTOCOL_SHA256 == _sha256(PROTOCOL_PATH)
    # Layer 3: the protocol pins the driver as it stood when V1 was implemented.
    # Read from git, not the working tree: later lines are expected to change
    # that file, and V1's pin is a statement about V1's execution.
    baseline = payload["source_baseline"]
    blob = subprocess.run(
        ["git", "cat-file", "-p",
         f"{V1_IMPLEMENTATION_COMMIT}:{baseline['training_driver_source']}"],
        cwd=REPO_ROOT, capture_output=True, check=True,
    ).stdout
    assert baseline["training_driver_source_sha256"] == (
        "sha256:" + hashlib.sha256(blob).hexdigest()
    )


def test_a_protocol_whose_bytes_changed_is_refused(tmp_path: Path):
    payload = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    payload["training_design"]["checkpoint_interval"] = 250_000
    forged = tmp_path / "forged.json"
    forged.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    with pytest.raises(tl.TrackedLineageMethodFailure, match="TL_PROTOCOL_DIGEST_MISMATCH"):
        tl.load_protocol(forged)


# ---------------------------------------------------------------------------
# TL-01 / TL-02: driver identity
# ---------------------------------------------------------------------------

def test_tl01_driver_digests_are_re_derived_and_match(protocol, tmp_path: Path):
    root = tmp_path / "v1"
    _materialise_at_v1_commit(root, "backend/rl/train_ppo.py", "backend/rl/eval_policy.py")
    measured = tl.verify_driver_digests(protocol, root=root)
    assert set(measured) == {"backend/rl/train_ppo.py", "backend/rl/eval_policy.py"}


def test_tl01_eval_policy_must_equal_its_unmodified_value(protocol, tmp_path: Path):
    """Section 6.4: this line does NOT modify eval_policy.py.

    Modifying it would turn test_v7_candidate_selection_contract.py red under the
    protocol the owner authorized on 2026-09-10, which is why the scope is
    narrowed to PUB-B1 and PUB-B2 instead.
    """
    root = tmp_path / "repo"
    _materialise_at_v1_commit(root, "backend/rl/train_ppo.py", "backend/rl/eval_policy.py")
    tl.verify_driver_digests(protocol, root=root)

    edited = root / "backend" / "rl" / "eval_policy.py"
    edited.write_bytes(edited.read_bytes() + b"\n# drift\n")
    with pytest.raises(tl.TrackedLineageMethodFailure, match="TL_DRIVER_DIGEST_MISMATCH"):
        tl.verify_driver_digests(protocol, root=root)


def test_tl01_an_edited_training_driver_is_refused(protocol, tmp_path: Path):
    root = tmp_path / "repo"
    _materialise_at_v1_commit(root, "backend/rl/train_ppo.py", "backend/rl/eval_policy.py")
    edited = root / "backend" / "rl" / "train_ppo.py"
    edited.write_bytes(edited.read_bytes() + b"\n# drift\n")
    with pytest.raises(tl.TrackedLineageMethodFailure, match="TL_DRIVER_DIGEST_MISMATCH"):
        tl.verify_driver_digests(protocol, root=root)


def test_tl02_both_driver_digests_are_carried(protocol):
    baseline = protocol["source_baseline"]
    current = baseline["training_driver_source_sha256"]
    superseded = baseline["superseded_training_driver_source_sha256"]
    assert current and superseded
    # The disclosure is only meaningful because they differ: the retained
    # 2026-09-08 evidence was produced on the superseded driver.
    assert current != superseded
    assert superseded == (
        "sha256:877da3b41e7c44ce73758877f40e257e45c6203b045eb9e2d3cd5aa6f606f6ce"
    )


def test_tl02_dropping_the_superseded_digest_fails_closed(protocol):
    mutated = copy.deepcopy(protocol)
    mutated["source_baseline"].pop("superseded_training_driver_source_sha256")
    with pytest.raises(
        tl.TrackedLineageMethodFailure, match="TL_SUPERSEDED_TRAINING_DRIVER_DIGEST_MISSING"
    ):
        tl.verify_driver_digests(mutated)


# ---------------------------------------------------------------------------
# TL-03: scratch
# ---------------------------------------------------------------------------

def _manifest(index: int, seed: int) -> dict:
    return {
        "run_id": f"stand_start_walk_stop_0p7_tracked_lineage_b1_r{index}-run",
        "profile": {"warm_start_policy_id": None},
        "warm_start": None,
        "resume": None,
        "resolved": {"seed_base": seed},
    }


def _manifests(protocol: dict) -> list[dict]:
    seeds = protocol["training_design"]["training_seeds"]
    return [_manifest(index, seed) for index, seed in enumerate(seeds)]


def test_tl03_scratch_start_is_accepted(protocol):
    tl.verify_scratch_start(_manifests(protocol))


@pytest.mark.parametrize(
    "mutation, code",
    [
        ({"profile": {"warm_start_policy_id": "v5"}}, "TL_WARM_START_NOT_NULL"),
        ({"warm_start": {"policy_id": "v5"}}, "TL_WARM_START_RECORD_PRESENT"),
        ({"resume": {"source_num_timesteps": 1}}, "TL_RESUME_NOT_NULL"),
    ],
)
def test_tl03_any_warm_start_or_resume_fails_closed(protocol, mutation, code):
    manifests = _manifests(protocol)
    manifests[2].update(mutation)
    with pytest.raises(tl.TrackedLineageMethodFailure, match=code):
        tl.verify_scratch_start(manifests)


# ---------------------------------------------------------------------------
# TL-04: training seeds
# ---------------------------------------------------------------------------

def test_tl04_training_seeds_match_the_frozen_schedule(protocol):
    assert tl.verify_training_seeds(protocol, _manifests(protocol)) == [
        9100, 9112, 9124, 9136, 9148
    ]


def test_tl04_a_seed_outside_the_schedule_fails_closed(protocol):
    manifests = _manifests(protocol)
    manifests[1]["resolved"]["seed_base"] = 8700
    with pytest.raises(
        tl.TrackedLineageMethodFailure, match="TL_TRAINING_SEED_SCHEDULE_MISMATCH"
    ):
        tl.verify_training_seeds(protocol, manifests)


def test_tl04_environment_seed_blocks_do_not_overlap(protocol):
    """The stride is parallel_envs, so the blocks abut without overlapping.

    Overlapping blocks would make two replicates share environment streams,
    which is not an independent replicate.
    """
    design = protocol["training_design"]
    seeds = [int(seed) for seed in design["training_seeds"]]
    parallel = int(design["parallel_envs"])
    blocks = [[seed, seed + parallel - 1] for seed in seeds]
    assert blocks == [[int(x) for x in pair] for pair in design["environment_seed_blocks"]]
    for (_, end), (start, _) in zip(blocks, blocks[1:]):
        assert start > end


def test_tl04_overlapping_seed_blocks_fail_closed(protocol):
    mutated = copy.deepcopy(protocol)
    # A stride of 6 with 12 parallel envs makes consecutive blocks overlap.
    mutated["training_design"]["training_seeds"] = [9100, 9106, 9112, 9118, 9124]
    manifests = [_manifest(i, s) for i, s in enumerate([9100, 9106, 9112, 9118, 9124])]
    with pytest.raises(
        tl.TrackedLineageMethodFailure, match="TL_ENVIRONMENT_SEED_BLOCK_OVERLAP"
    ):
        tl.verify_training_seeds(mutated, manifests)


def test_tl04_the_frozen_seeds_are_disjoint_from_every_existing_training_seed(protocol):
    design = protocol["training_design"]
    existing = {int(seed) for seed in design["seeds_disjoint_from_existing"]}
    assert existing.isdisjoint({int(seed) for seed in design["training_seeds"]})
    # Cross-checked against the live profiles rather than the protocol's own
    # list, so the claim cannot be true only of a stale copy.
    live = {
        item.seed_base
        for item in train_ppo.load_profiles().profiles
        if item.tracked_lineage_protocol_id is None
    }
    assert live.isdisjoint({int(seed) for seed in design["training_seeds"]})


# ---------------------------------------------------------------------------
# TL-01b / TL-05: evaluation seeds, enforced at analysis time
# ---------------------------------------------------------------------------

def _outputs(protocol: dict, seeds: list[int] | None = None) -> list[dict]:
    design = protocol["evaluation_design"]
    default = list(range(design["evaluation_seed_start"], design["evaluation_seed_end"] + 1))
    return [
        {"run_id": f"r{index}", "evaluation_seeds": list(seeds or default)}
        for index in range(protocol["training_design"]["replicate_count"])
    ]


def test_tl01b_the_frozen_evaluation_seed_range_is_accepted(protocol):
    tl.verify_evaluation_seeds(protocol, _outputs(protocol))


def test_tl01b_the_generic_path_has_no_driver_side_seed_guard():
    """The reason TL-01b has to exist at all.

    The v7 and seedvar branches each refuse a seed-schedule override inside
    eval_policy.py. The generic path this line uses has no such guard, so the
    only remaining place to enforce the schedule is analysis time.
    """
    source = (REPO_ROOT / "backend" / "rl" / "eval_policy.py").read_text(encoding="utf-8")
    assert "SEEDVAR_EVALUATION_SEED_SCHEDULE_OVERRIDE_FORBIDDEN" in source
    assert "V7_EVALUATION_SEED_SCHEDULE_OVERRIDE_FORBIDDEN" in source
    assert "TRACKED_LINEAGE_EVALUATION_SEED_SCHEDULE_OVERRIDE_FORBIDDEN" not in source
    assert (
        json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))["evaluation_design"][
            "driver_is_modified"
        ]
        is False
    )


def test_tl01b_a_seed_outside_the_range_is_method_failure(protocol):
    outputs = _outputs(protocol)
    outputs[3]["evaluation_seeds"][7] = 22999
    with pytest.raises(
        tl.TrackedLineageMethodFailure, match="TL_EVALUATION_SEED_SCHEDULE_MISMATCH"
    ):
        tl.verify_evaluation_seeds(protocol, outputs)


@pytest.mark.parametrize("seed", [18000, 18029, 19000, 19029, 20000, 20029])
def test_tl05_exhausted_retired_and_sealed_ranges_fail_closed(protocol, seed):
    outputs = _outputs(protocol)
    outputs[0]["evaluation_seeds"][0] = seed
    with pytest.raises(
        tl.TrackedLineageMethodFailure, match="TL_EVALUATION_SEED_FORBIDDEN"
    ):
        tl.verify_evaluation_seeds(protocol, outputs)


def test_tl05_a_permuted_schedule_is_still_refused(protocol):
    """Order is part of the schedule: episode i must be seed 22000 + i."""
    design = protocol["evaluation_design"]
    reversed_seeds = list(
        range(design["evaluation_seed_end"], design["evaluation_seed_start"] - 1, -1)
    )
    with pytest.raises(
        tl.TrackedLineageMethodFailure, match="TL_EVALUATION_SEED_SCHEDULE_MISMATCH"
    ):
        tl.verify_evaluation_seeds(protocol, _outputs(protocol, reversed_seeds))


# ---------------------------------------------------------------------------
# TL-06: checkpoint lineage
# ---------------------------------------------------------------------------

def _lineage(protocol: dict, tmp_path: Path) -> dict:
    lineage = protocol["checkpoint_lineage"]
    steps = [int(value) for value in lineage["expected_realized_timesteps"]]
    root = tmp_path / "backend" / "tracked_lineage_evidence" / "2026-09-14" / "checkpoints"
    root.mkdir(parents=True)
    entries = []
    for replicate_index in range(protocol["training_design"]["replicate_count"]):
        for step in steps:
            name = f"r{replicate_index}-{step:07d}.zip"
            path = root / name
            path.write_bytes(f"policy-{replicate_index}-{step}".encode())
            entries.append(
                {
                    "relative_path": str(path.relative_to(tmp_path)).replace("\\", "/"),
                    "bytes": path.stat().st_size,
                    "sha256": _sha256(path),
                    "realized_timesteps": step,
                    "replicate_index": replicate_index,
                }
            )
    return {"checkpoints": entries}


def test_tl06_a_complete_lineage_is_accepted(protocol, tmp_path: Path):
    tl.verify_checkpoint_lineage(protocol, _lineage(protocol, tmp_path), root=tmp_path)


def test_tl06_the_expected_steps_are_the_corrected_ones_not_multiples_of_500k(protocol):
    """Amendment 01 item 2.

    save_freq = checkpoint_interval // n_envs = 500000 // 12 = 41666, and SB3
    fires on n_calls % save_freq == 0 with num_timesteps = n_calls * n_envs, so
    multiples of 500_000 are unreachable at 12 parallel envs.
    """
    design = protocol["training_design"]
    save_freq = design["checkpoint_interval"] // design["parallel_envs"]
    expected = [
        save_freq * design["parallel_envs"] * k
        for k in range(1, protocol["checkpoint_lineage"]["per_replicate_count"] + 1)
    ]
    assert expected == [499_992, 999_984, 1_499_976, 1_999_968]
    assert protocol["checkpoint_lineage"]["expected_realized_timesteps"] == expected
    assert 500_000 not in expected


def test_tl06_realized_timesteps_follow_the_rollout_boundary(protocol):
    """The same arithmetic reproduces the seedvar line's recorded 122880."""
    design = protocol["training_design"]
    rollout = 2048 * design["parallel_envs"]

    def realized(planned: int) -> int:
        return -(-planned // rollout) * rollout

    assert realized(100_000) == 122_880  # matches SEEDVAR's retained value
    assert realized(design["planned_timesteps_per_replicate"]) == 2_015_232
    assert design["realized_timesteps_per_replicate"] == 2_015_232


def test_tl06_a_gap_in_the_sequence_fails_closed(protocol, tmp_path: Path):
    index = _lineage(protocol, tmp_path)
    index["checkpoints"] = [
        entry for entry in index["checkpoints"]
        if not (entry["replicate_index"] == 1 and entry["realized_timesteps"] == 999_984)
    ]
    with pytest.raises(tl.TrackedLineageMethodFailure, match="TL_CHECKPOINT_COUNT_MISMATCH"):
        tl.verify_checkpoint_lineage(protocol, index, root=tmp_path)


def test_tl06_a_duplicate_instead_of_the_next_step_fails_closed(protocol, tmp_path: Path):
    index = _lineage(protocol, tmp_path)
    for entry in index["checkpoints"]:
        if entry["replicate_index"] == 0 and entry["realized_timesteps"] == 1_499_976:
            entry["realized_timesteps"] = 999_984
    with pytest.raises(
        tl.TrackedLineageMethodFailure, match="TL_CHECKPOINT_SEQUENCE_MISMATCH"
    ):
        tl.verify_checkpoint_lineage(protocol, index, root=tmp_path)


def test_tl06_a_digest_that_does_not_match_the_bytes_fails_closed(protocol, tmp_path: Path):
    index = _lineage(protocol, tmp_path)
    index["checkpoints"][6]["sha256"] = "sha256:" + "0" * 64
    with pytest.raises(
        tl.TrackedLineageMethodFailure, match="TL_CHECKPOINT_DIGEST_MISMATCH"
    ):
        tl.verify_checkpoint_lineage(protocol, index, root=tmp_path)


def test_tl06_an_indexed_but_absent_checkpoint_fails_closed(protocol, tmp_path: Path):
    index = _lineage(protocol, tmp_path)
    (tmp_path / index["checkpoints"][0]["relative_path"]).unlink()
    with pytest.raises(tl.TrackedLineageMethodFailure, match="TL_CHECKPOINT_FILE_MISSING"):
        tl.verify_checkpoint_lineage(protocol, index, root=tmp_path)


def test_tl06_a_missing_required_field_fails_closed(protocol, tmp_path: Path):
    index = _lineage(protocol, tmp_path)
    index["checkpoints"][4].pop("realized_timesteps")
    with pytest.raises(tl.TrackedLineageMethodFailure, match="TL_CHECKPOINT_FIELD_MISSING"):
        tl.verify_checkpoint_lineage(protocol, index, root=tmp_path)


def test_tl06_the_retention_root_is_not_gitignored(protocol):
    """GIT_DIRECT's credibility is that the bytes are in the repository.

    A retained-but-ignored checkpoint looks identical locally and is absent for
    everyone else, so this is checked against real `git check-ignore` output.
    """
    lineage = protocol["checkpoint_lineage"]
    assert lineage["storage"] == "GIT_DIRECT"
    candidates = [
        f"backend/tracked_lineage_evidence/2026-09-14/checkpoints/r{index}-{step:07d}.zip"
        for index in range(5)
        for step in lineage["expected_realized_timesteps"]
    ] + ["backend/tracked_lineage_evidence/2026-09-14/checkpoint_index.json"]
    result = subprocess.run(
        ["git", "check-ignore", "--no-index", *candidates],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    ignored = [line for line in result.stdout.splitlines() if line.strip()]
    tl.verify_checkpoints_are_version_controlled(protocol, ignored)
    assert ignored == []


def test_tl06_a_gitignored_checkpoint_fails_closed(protocol):
    with pytest.raises(
        tl.TrackedLineageMethodFailure, match="TL_CHECKPOINT_PATH_GITIGNORED"
    ):
        tl.verify_checkpoints_are_version_controlled(protocol, ["backend/rl/artifacts/x.zip"])


# ---------------------------------------------------------------------------
# TL-07: lock binding
# ---------------------------------------------------------------------------

def test_tl07_all_bound_runs_are_accepted():
    tl.verify_run_lock_bindings({f"r{index}": "RUN_LOCK_BOUND" for index in range(5)})


@pytest.mark.parametrize(
    "label",
    [
        "RUN_LOCK_UNBOUND",
        "RUN_LOCK_INSUFFICIENT",
        "RUN_LOCK_MISMATCH",
        "RUN_LOCK_BINDING_METHOD_FAILURE",
    ],
)
def test_tl07_any_label_other_than_bound_fails_closed(label):
    labels = {f"r{index}": "RUN_LOCK_BOUND" for index in range(5)}
    labels["r3"] = label
    with pytest.raises(tl.TrackedLineageMethodFailure, match="TL_RUN_LOCK_NOT_BOUND"):
        tl.verify_run_lock_bindings(labels)


# ---------------------------------------------------------------------------
# Full exposure
# ---------------------------------------------------------------------------

def _episodes(full_count: int, total: int = 30) -> list[dict]:
    episodes = [{"duration_s": 9.0, "outcome_state": "OBSERVED"} for _ in range(full_count)]
    episodes += [
        {"duration_s": 8.98, "outcome_state": "EARLY_TERMINATION_REQUIRED_OUTCOME_UNOBSERVED"}
        for _ in range(total - full_count)
    ]
    return episodes


def test_full_exposure_uses_the_measured_duration_resolution(protocol):
    """450 control steps gives exactly 9.0 and 449 gives 8.98.

    duration_s is round(len(rewards) * 0.02, 3) at rl/eval_policy.py:325, so the
    two are separable at three decimals with no tolerance to argue about.
    """
    assert round(450 * 0.02, 3) == 9.0
    assert round(449 * 0.02, 3) == 8.98
    assert tl.episode_is_fully_exposed({"duration_s": 9.0, "outcome_state": "OBSERVED"})
    assert not tl.episode_is_fully_exposed({"duration_s": 8.98, "outcome_state": "OBSERVED"})
    assert not tl.episode_is_fully_exposed({"duration_s": 9.0, "outcome_state": "NULL"})


def test_disagreeing_exposure_signals_are_method_failure_not_a_judgement_call(protocol):
    episodes = _episodes(30)
    episodes[11]["duration_s"] = 8.98  # short, but still marked OBSERVED
    with pytest.raises(tl.TrackedLineageMethodFailure, match="TL_EXPOSURE_SIGNALS_DISAGREE"):
        tl.replicate_full_exposure(protocol, episodes)


def test_the_wrong_episode_count_fails_closed(protocol):
    with pytest.raises(tl.TrackedLineageMethodFailure, match="TL_EPISODE_COUNT_MISMATCH"):
        tl.replicate_full_exposure(protocol, _episodes(29, total=29))


# ---------------------------------------------------------------------------
# TL-08: one positive control per label, and no downgrade
# ---------------------------------------------------------------------------

def test_tl08_label_attained(protocol):
    result = tl.classify(protocol, [(30, 30)] * 5, curve_converged=True)
    assert result["label"] == tl.LABEL_ATTAINED
    assert result["pub_b2_pass"] is True


def test_tl08_label_partial(protocol):
    result = tl.classify(protocol, [(30, 30), (29, 30), (30, 30), (27, 30), (30, 30)], curve_converged=True)
    assert result["label"] == tl.LABEL_PARTIAL
    assert result["replicates_attaining_threshold"] == 3
    assert result["pub_b2_pass"] is False


def test_tl08_label_not_attained(protocol):
    result = tl.classify(protocol, [(29, 30)] * 5, curve_converged=True)
    assert result["label"] == tl.LABEL_NOT_ATTAINED
    assert result["pub_b2_pass"] is False


def test_tl08_label_budget_exhausted(protocol):
    result = tl.classify(protocol, [(28, 30)] * 5, curve_converged=False)
    assert result["label"] == tl.LABEL_BUDGET_EXHAUSTED


def test_tl08_budget_exhausted_cannot_mask_a_replicate_that_attained(protocol):
    """A run that met the threshold has not exhausted anything."""
    result = tl.classify(protocol, [(30, 30), (28, 30), (28, 30), (28, 30), (28, 30)],
                         curve_converged=False)
    assert result["label"] == tl.LABEL_PARTIAL


def test_tl08_method_failure_is_never_downgraded(protocol):
    """The decisive test for the whole contract.

    Every guard raises the same exception type, and none of them returns one of
    the four result labels instead. A contract violation does not mean the line
    did worse; it means the measurement did not happen.
    """
    failures = [
        (tl.verify_scratch_start, ([{"run_id": "r0", "profile": {"warm_start_policy_id": "v5"}}],), {}),
        (tl.verify_run_lock_bindings, ({"r0": "RUN_LOCK_UNBOUND"},), {}),
        (tl.verify_evaluation_seeds, (protocol, [{"run_id": "r0", "evaluation_seeds": [20000]}]), {}),
        (tl.replicate_full_exposure, (protocol, _episodes(5, total=5)), {}),
    ]
    for function, args, kwargs in failures:
        with pytest.raises(tl.TrackedLineageMethodFailure) as caught:
            function(*args, **kwargs)
        assert not any(label in str(caught.value) for label in tl.RESULT_LABELS)
    assert tl.LABEL_METHOD_FAILURE not in tl.RESULT_LABELS
    assert set(tl.ALL_LABELS) == set(tl.RESULT_LABELS) | {tl.LABEL_METHOD_FAILURE}


def test_the_threshold_is_30_of_30_and_is_compared_exactly(protocol):
    """Section 4.2: at 30 episodes the attainable proportions are thirtieths.

    0.98 does not exist under this design -- it rounds to 30/30 -- which is why
    the frozen value is the rational 30/30 rather than a float.
    """
    threshold = protocol["full_exposure_threshold"]
    assert threshold["value"] == "30/30"
    assert threshold["numeric"] == 1.0
    assert threshold["judged"] == "per replicate"
    assert tl.classify(protocol, [(29, 30)] * 5, curve_converged=True)["label"] == tl.LABEL_NOT_ATTAINED


def test_forbidden_denominators_are_declared_and_the_method_unit_is_the_replicate(protocol):
    unit = protocol["analysis_unit"]
    assert unit["unit"] == "training_replicate"
    assert unit["method_level_denominator"] == tl.METHOD_LEVEL_DENOMINATOR == 5
    assert sorted(unit["forbidden_denominators"]) == sorted(tl.FORBIDDEN_DENOMINATORS)
    assert tl.classify(protocol, [(30, 30)] * 5, curve_converged=True)["method_level_denominator"] == 5


def test_the_wrong_replicate_count_fails_closed(protocol):
    with pytest.raises(tl.TrackedLineageMethodFailure, match="TL_REPLICATE_COUNT_MISMATCH"):
        tl.classify(protocol, [(30, 30)] * 4, curve_converged=True)


# ---------------------------------------------------------------------------
# The driver identity, as seen from the profile side
# ---------------------------------------------------------------------------

def test_the_third_identity_is_mutually_exclusive_with_the_other_two():
    profiles = train_ppo.load_profiles().profiles
    tracked = [
        item for item in profiles
        if item.tracked_lineage_protocol_id == "TRACKED-LINEAGE-TRAINING-V1"
    ]
    assert len(tracked) == 5
    for item in tracked:
        assert item.pilot_protocol_id is None
        assert item.seedvar_protocol_id is None
        assert item.pilot_arm_id is None
        assert item.warm_start_policy_id is None
        assert item.environment_id == "motion_task_phase_observable_v5"
        assert item.planned_timesteps == 2_000_000
        assert item.parallel_envs == 12


def test_a_v7_profile_may_not_declare_the_tracked_lineage_identity():
    payload = json.loads(
        (REPO_ROOT / "backend" / "rl" / "training_profiles.json").read_text(encoding="utf-8")
    )
    victim = next(
        item for item in payload["profiles"]
        if item["profile_id"] == "stand_start_walk_stop_0p7_action_reward_v7a"
    )
    victim["tracked_lineage_protocol_id"] = "TRACKED-LINEAGE-TRAINING-V1"
    with pytest.raises(ValueError, match="V7_PROFILE_HAS_TRACKED_LINEAGE_IDENTITY"):
        train_ppo.TrainingProfiles.model_validate(payload)


def test_the_existing_pilot_rejection_still_fires_first_for_a_non_v7_profile():
    """Section 6.1 forbids changing the order the existing checks fire in."""
    payload = json.loads(
        (REPO_ROOT / "backend" / "rl" / "training_profiles.json").read_text(encoding="utf-8")
    )
    victim = next(
        item for item in payload["profiles"]
        if item["profile_id"] == "stand_start_walk_stop_0p7_tracked_lineage_b1_r0"
    )
    victim["pilot_arm_id"] = "V7A_REWARD_ONLY"
    with pytest.raises(ValueError, match="NON_V7_PROFILE_HAS_PILOT_IDENTITY"):
        train_ppo.TrainingProfiles.model_validate(payload)


@pytest.mark.parametrize(
    "field, value, code",
    [
        ("environment_id", "motion_task_substep_saturation_v6", "TRACKED_LINEAGE_ENVIRONMENT_ID_MISMATCH"),
        ("task_id", "walk_v1", "TRACKED_LINEAGE_TASK_ID_MISMATCH"),
        ("warm_start_policy_id", "stand_start_walk_stop_0p7_phase_observable_v5", "TRACKED_LINEAGE_WARM_START_FORBIDDEN"),
        ("seed_base", 8700, "TRACKED_LINEAGE_TRAINING_SEED_MISMATCH"),
        ("parallel_envs", 8, "TRACKED_LINEAGE_PARALLEL_ENVS_MISMATCH"),
        ("planned_timesteps", 3_000_000, "TRACKED_LINEAGE_TRAINING_BUDGET_MISMATCH"),
        ("speed_mps", 1.0, "TRACKED_LINEAGE_GAIT_MISMATCH"),
    ],
)
def test_a_tracked_lineage_profile_that_drifts_from_the_protocol_is_refused(field, value, code):
    payload = json.loads(
        (REPO_ROOT / "backend" / "rl" / "training_profiles.json").read_text(encoding="utf-8")
    )
    victim = next(
        item for item in payload["profiles"]
        if item["profile_id"] == "stand_start_walk_stop_0p7_tracked_lineage_b1_r0"
    )
    victim[field] = value
    with pytest.raises(ValueError, match=code):
        train_ppo.TrainingProfiles.model_validate(payload)


def test_the_checkpoint_interval_comes_from_the_protocol_not_the_driver_default():
    """Without this, a 2M-step run keeps no intermediate checkpoint at all.

    train_ppo.py's full-run branch pins 2_000_000, which is the lineage gap
    ROADMAP section 9 item 2 exists to close.
    """
    assert train_ppo.tracked_lineage_checkpoint_interval() == 500_000
    # Measured from the protocol, which is the single source for it.
    protocol = json.loads(
        (REPO_ROOT / "backend" / "rl" / "tracked_lineage_training_protocol.json")
        .read_text(encoding="utf-8")
    )
    assert protocol["training_design"]["checkpoint_interval"] == 500_000
    # The earlier version of this test asserted that the literal
    # "checkpoint_interval = 2_000_000" was absent from the driver source. That
    # was a brittle proxy, not a measurement of the claim: the default still
    # legitimately applies to every profile that is NOT a tracked-lineage one,
    # and V2 reintroduced the literal in exactly that branch. The claim - this
    # line's interval comes from its protocol - is unchanged and is what is
    # checked above.


def test_the_replicate_index_is_derived_from_the_profile_id_not_the_command_line():
    for index in range(5):
        assert train_ppo.tracked_lineage_replicate_index(
            f"stand_start_walk_stop_0p7_tracked_lineage_b1_r{index}"
        ) == index
    for bad in ("stand_start_walk_stop_0p7_phase_observable_v5", "tracked_lineage_b1_rX"):
        with pytest.raises(ValueError, match="TRACKED_LINEAGE_PROFILE_ID_MISMATCH"):
            train_ppo.tracked_lineage_replicate_index(bad)


# ---------------------------------------------------------------------------
# TL-CK-06 (amendment 02): the evaluated policy is a retained checkpoint
# ---------------------------------------------------------------------------

def test_amendment_02_is_recorded_and_tl_ck_06_exists(protocol):
    ids = [item["amendment_id"] for item in protocol["amendments"]]
    assert "TRACKED-LINEAGE-AMENDMENT-02-FINAL-ARTIFACT" in ids
    rules = protocol["checkpoint_lineage"]["rules"]
    assert "TL-CK-06" in rules
    # The costed parts of the section 4.1 decision are untouched.
    assert protocol["checkpoint_lineage"]["per_replicate_count"] == 4
    assert protocol["checkpoint_lineage"]["total_count"] == 20
    assert protocol["training_design"]["checkpoint_interval"] == 500_000


def test_tl_ck_04_reference_is_the_last_retained_checkpoint(protocol, tmp_path: Path):
    index = _lineage(protocol, tmp_path)
    for replicate_index in range(5):
        reference = tl.reference_checkpoint(index, replicate_index)
        assert reference["realized_timesteps"] == 1_999_968
        assert reference["replicate_index"] == replicate_index


def test_tl_ck_06_accepts_a_retained_checkpoint(protocol, tmp_path: Path):
    index = _lineage(protocol, tmp_path)
    evaluated = {
        replicate_index: tl.reference_checkpoint(index, replicate_index)["sha256"]
        for replicate_index in range(5)
    }
    tl.verify_evaluated_policy_is_a_retained_checkpoint(index, evaluated)


def test_tl_ck_06_refuses_the_unretained_byproduct(protocol, tmp_path: Path):
    """The measured case: policy.zip is 15_264 steps past the last checkpoint.

    Amendment 02 exists because TL-CK-03 as written could never be satisfied
    here, and this is the check that replaced the prose claim.
    """
    index = _lineage(protocol, tmp_path)
    evaluated = {
        replicate_index: tl.reference_checkpoint(index, replicate_index)["sha256"]
        for replicate_index in range(5)
    }
    evaluated[2] = "sha256:6378115d21e805e1a6f72adff04e3aacf3a97a91b6395e63e7546294dca4480c"
    with pytest.raises(
        tl.TrackedLineageMethodFailure, match="TL_EVALUATED_POLICY_NOT_A_RETAINED_CHECKPOINT"
    ):
        tl.verify_evaluated_policy_is_a_retained_checkpoint(index, evaluated)


def test_tl_ck_06_refuses_another_replicates_checkpoint(protocol, tmp_path: Path):
    """A retained checkpoint is not enough; it must be THIS replicate's."""
    index = _lineage(protocol, tmp_path)
    evaluated = {
        replicate_index: tl.reference_checkpoint(index, replicate_index)["sha256"]
        for replicate_index in range(5)
    }
    evaluated[1] = tl.reference_checkpoint(index, 4)["sha256"]
    with pytest.raises(
        tl.TrackedLineageMethodFailure, match="TL_EVALUATED_POLICY_NOT_A_RETAINED_CHECKPOINT"
    ):
        tl.verify_evaluated_policy_is_a_retained_checkpoint(index, evaluated)


# ---------------------------------------------------------------------------
# Amendment 03: label precedence, and a verdict that cannot be skipped
# ---------------------------------------------------------------------------

def test_amendment_03_convergence_verdict_has_no_default(protocol):
    """The defect that produced the wrong label on 2026-09-14.

    classify() previously took budget_exhausted=False, so a caller could get a
    label without ever measuring the condition separating the two, and that is
    exactly what happened. A determination that can be skipped silently will be.
    """
    import inspect
    sig = inspect.signature(tl.classify)
    param = sig.parameters["curve_converged"]
    assert param.default is inspect.Parameter.empty
    assert param.kind is inspect.Parameter.KEYWORD_ONLY
    assert "budget_exhausted" not in sig.parameters
    with pytest.raises(TypeError):
        tl.classify(protocol, [(0, 30)] * 5)


def test_amendment_03_precedence_when_both_labels_hold(protocol):
    """Not converged wins: it is more specific and carries the stricter rule."""
    not_converged = tl.classify(protocol, [(0, 30)] * 5, curve_converged=False)
    converged = tl.classify(protocol, [(0, 30)] * 5, curve_converged=True)
    assert not_converged["label"] == tl.LABEL_BUDGET_EXHAUSTED
    assert converged["label"] == tl.LABEL_NOT_ATTAINED
    # Neither passes PUB-B2; only the name of the outcome differs.
    assert not_converged["pub_b2_pass"] is False
    assert converged["pub_b2_pass"] is False
    assert protocol["outcome_label_precedence"]


def test_amendment_03_retained_curves_show_no_replicate_converged():
    """The measurement that corrected the line's label, re-derived here."""
    index = json.loads(
        (REPO_ROOT / "backend" / "tracked_lineage_evidence" / "2026-09-14"
         / "training_curve_index.json").read_text(encoding="utf-8")
    )
    assert index["any_replicate_converged"] is False
    assert len(index["replicates"]) == 5
    for item in index["replicates"].values():
        assert item["converged"] is False
        # Still clearly rising when the ceiling cut training off.
        assert item["final_quarter_slope_per_500k"] > 1.0
        assert item["final_over_first"] > 0.10
    rule = index["convergence_rule"]
    assert rule["declared_before_application"] is True
    assert rule["converged_slope_fraction"] == 0.10


def test_amendment_03_retained_curve_files_match_their_digests():
    index = json.loads(
        (REPO_ROOT / "backend" / "tracked_lineage_evidence" / "2026-09-14"
         / "training_curve_index.json").read_text(encoding="utf-8")
    )
    for item in index["replicates"].values():
        path = REPO_ROOT / item["relative_path"]
        assert path.is_file(), item["relative_path"]
        assert _sha256(path) == item["sha256"]
        assert path.stat().st_size == item["bytes"]

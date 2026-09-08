"""Fail-closed tests for SEEDVAR-V7-TRAINING-REPLICATE-DEV-V1.

The fixtures are synthetic on purpose. What is being tested is whether the
contract refuses to produce a number it is not entitled to: the wrong
denominator, a point estimate over censored exposure, a mean over a cell
containing a method failure, or a candidate selection.
"""

from __future__ import annotations

import ast
from copy import deepcopy
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

import environment_lock as lock_module
from environment_lock import (
    SYNTHETIC_LOCK_CLASS,
    write_lock_record,
)
import build_training_seed_variance_regression_bundle as builder
import training_seed_variance_contract as svc
from training_seed_variance_contract import (
    ARM_IDS,
    CANDIDATE_ARM_IDS,
    CELL_BLOCKED_METHOD_FAILURE,
    CELL_PARTIALLY_IDENTIFIED,
    CELL_POINT_IDENTIFIED,
    DEFAULT_PROTOCOL,
    LOCK_ARTIFACT,
    PROTOCOL_ARTIFACT,
    PROTOCOL_SHA256,
    RAW_ARTIFACT,
    REASON_BLOCKED_PAIR,
    REASON_PARTIAL_SD,
    REFERENCE_ARM_ID,
    SIGN_NEGATIVE,
    SIGN_NULL,
    SIGN_UNIDENTIFIED,
    STATUS_BLOCKED,
    STATUS_CLEAN,
    SUMMARY_ARTIFACT,
    SYNTHETIC_BUNDLE_CLASS,
    DEVELOPMENT_BUNDLE_CLASS,
    SeedVarianceError,
    analyse_seed_variance,
    build_summary,
    load_protocol,
    ordered_mean,
    ordered_sample_sd,
    validate_raw_bundle,
    validate_seed_variance_bundle,
)


BACKEND_ROOT = Path(__file__).resolve().parent
CONTRACT_PATH = BACKEND_ROOT / "training_seed_variance_contract.py"
REPLAY_PATH = BACKEND_ROOT / "training_seed_variance_replay.py"
FIXTURE_GIT_SHA = "a" * 40

# The replay must run under ``python -I -S``, so its top level may not reach
# for site packages or for this repository's own modules.
REPLAY_ALLOWED_IMPORTS = {"__future__", "hashlib", "json", "math", "sys", "typing"}


@pytest.fixture(scope="module")
def protocol() -> dict:
    return load_protocol(DEFAULT_PROTOCOL)


@pytest.fixture(scope="module")
def design(protocol: dict) -> dict:
    return svc._protocol_design(protocol)


@pytest.fixture(scope="module")
def pinned_lock() -> dict:
    """One thread-pinned capture, reused: the probes are not free."""
    return builder.capture_pinned_lock()


def _raw(design: dict, pinned_lock: dict, **kwargs) -> dict:
    return builder.build_raw_bundle(
        design, pinned_lock["locked_sha256"], FIXTURE_GIT_SHA, **kwargs
    )


@pytest.fixture
def raw(design: dict, pinned_lock: dict) -> dict:
    return _raw(design, pinned_lock)


@pytest.fixture
def censored_raw(design: dict, pinned_lock: dict) -> dict:
    return _raw(design, pinned_lock, censored_arms=("V7C_FILTERED_ACTION",))


@pytest.fixture
def method_failure_raw(design: dict, pinned_lock: dict) -> dict:
    return _raw(
        design,
        pinned_lock,
        method_failures={("V7B_REDUCED_JOINT_ENVELOPE", 2): (18007,)},
    )


def _bundle(tmp_path: Path, raw_payload: dict, lock_record: dict) -> tuple[Path, Path]:
    root = tmp_path / "bundle"
    analysis = tmp_path / "analysis"
    root.mkdir()
    shutil.copyfile(DEFAULT_PROTOCOL, root / PROTOCOL_ARTIFACT)
    write_lock_record(root / LOCK_ARTIFACT, lock_record)
    svc._write_bytes(root / RAW_ARTIFACT, svc._json_bytes(raw_payload))
    return root, analysis


def _refreeze_lock(record: dict) -> dict:
    locked = record["locked"]
    record["lock_completeness"] = lock_module._lock_completeness(locked)
    record["threading_determinism"] = lock_module._threading_determinism(
        locked["determinism_environment"]
    )
    record["locked_sha256"] = lock_module.locked_digest(locked)
    return record


def _cell(raw_payload: dict, replicate_index: int, arm_id: str) -> dict:
    replicate = raw_payload["replicates"][replicate_index]
    return next(cell for cell in replicate["arms"] if cell["arm_id"] == arm_id)


def _method_level(summary: dict, candidate_id: str) -> dict:
    candidate = next(
        item for item in summary["candidates"] if item["candidate_arm_id"] == candidate_id
    )
    return candidate["method_level"]


# --------------------------------------------------------------------------- #
# exact reductions
# --------------------------------------------------------------------------- #


def test_ordered_mean_and_sample_sd_definitions() -> None:
    assert ordered_mean([1.0, 2.0, 3.0]) == 2.0
    assert ordered_sample_sd([2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0]) == pytest.approx(
        2.138089935299395, rel=0, abs=1e-15
    )


def test_ordered_reductions_fail_closed_on_short_input() -> None:
    with pytest.raises(SeedVarianceError):
        ordered_mean([])
    with pytest.raises(SeedVarianceError):
        ordered_sample_sd([1.0])


def test_reduction_order_is_fixed_not_sorted() -> None:
    """Float addition is not associative, so order is part of the contract."""
    # Adding the large magnitude first absorbs the small ones; adding them
    # last does not. Both orders are IEEE-conformant, which is exactly why the
    # contract fixes one and the replay has to use the same one.
    absorbing = [1e16, 1.0, 1.0]
    accumulating = list(reversed(absorbing))
    assert ordered_mean(absorbing) != ordered_mean(accumulating)


# --------------------------------------------------------------------------- #
# SV-01 protocol identity
# --------------------------------------------------------------------------- #


def test_frozen_protocol_loads_at_its_pinned_digest(protocol: dict) -> None:
    assert protocol["protocol_id"] == "SEEDVAR-V7-TRAINING-REPLICATE-DEV-V1"
    assert protocol["paper_data_ready"] is False
    assert svc.sha256_file(DEFAULT_PROTOCOL) == PROTOCOL_SHA256


def test_protocol_digest_drift_fails_closed(tmp_path: Path) -> None:
    edited = tmp_path / "protocol.json"
    payload = json.loads(DEFAULT_PROTOCOL.read_text(encoding="utf-8"))
    payload["training_design"]["replicate_count"] = 3
    edited.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(SeedVarianceError, match="protocol digest drift"):
        load_protocol(edited)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda payload: payload["estimand"].update({"analysis_unit": "EPISODE"}),
            "analysis_unit must be TRAINING_REPLICATE",
        ),
        (
            lambda payload: payload["selection"].update(
                {"selected_candidate_arm_id": "V7B_REDUCED_JOINT_ENVELOPE"}
            ),
            "must not preselect a candidate arm",
        ),
        (
            lambda payload: payload["selection"].update({"selection_permitted": True}),
            "selection_permitted",
        ),
        (
            lambda payload: payload.update({"paper_data_ready": True}),
            "paper_data_ready",
        ),
        (
            lambda payload: payload["estimand"].update({"method_level_denominator": 150}),
            "method_level_denominator must equal replicate_count",
        ),
        (
            lambda payload: payload["estimand"].update({"forbidden_denominators": [450]}),
            "episode-level pair count must be listed as a forbidden denominator",
        ),
        (
            lambda payload: payload["estimand"].update({"forbidden_denominators": [5, 150, 450]}),
            "replicate_count must not be listed as a forbidden denominator",
        ),
        (
            lambda payload: payload["training_design"].update(
                {"environment_seed_blocks": [[8700, 8711]] * 5}
            ),
            "must start at its training seed",
        ),
        (
            lambda payload: payload["training_design"].update(
                {"training_seeds": [8720, 8740, 8760, 8780, 8720]}
            ),
            "strictly ascending and unique",
        ),
        (
            lambda payload: payload["evaluation_design"].update(
                {"retired_seed_range": [18010, 18015]}
            ),
            "intersect a retired or sealed range",
        ),
        (
            lambda payload: payload["evaluation_design"].update({"pairs_per_candidate": 30}),
            "pairs_per_candidate disagrees",
        ),
    ],
)
def test_protocol_semantic_invariants_are_checked(
    protocol: dict, mutate, message: str
) -> None:
    """These guard a future re-freeze, which the digest pin cannot catch."""
    payload = deepcopy(protocol)
    mutate(payload)
    with pytest.raises(SeedVarianceError, match=message):
        svc.validate_protocol(payload)


def test_protocol_design_rejects_a_block_overlapping_the_pilot(protocol: dict) -> None:
    payload = deepcopy(protocol)
    payload["training_design"]["training_seeds"] = [8700, 8740, 8760, 8780, 8800]
    payload["training_design"]["environment_seed_blocks"] = [
        [8700, 8711],
        [8740, 8751],
        [8760, 8771],
        [8780, 8791],
        [8800, 8811],
    ]
    with pytest.raises(SeedVarianceError, match="overlaps an already occupied"):
        svc._protocol_design(payload)


def test_protocol_design_rejects_overlapping_replicate_blocks(protocol: dict) -> None:
    payload = deepcopy(protocol)
    payload["training_design"]["training_seeds"] = [8720, 8725, 8760, 8780, 8800]
    payload["training_design"]["environment_seed_blocks"] = [
        [8720, 8731],
        [8725, 8736],
        [8760, 8771],
        [8780, 8791],
        [8800, 8811],
    ]
    with pytest.raises(SeedVarianceError, match="overlaps an already occupied"):
        svc._protocol_design(payload)


# --------------------------------------------------------------------------- #
# SV-02 source identity
# --------------------------------------------------------------------------- #


def test_source_git_sha_drift_fails_closed(raw: dict, protocol: dict) -> None:
    raw["source_git_sha_post"] = "b" * 40
    with pytest.raises(SeedVarianceError, match="Git SHA drifted"):
        validate_raw_bundle(raw, protocol)


def test_short_git_sha_fails_closed(raw: dict, protocol: dict) -> None:
    raw["source_git_sha_pre"] = "abc123"
    raw["source_git_sha_post"] = "abc123"
    with pytest.raises(SeedVarianceError, match="full 40-character Git SHA"):
        validate_raw_bundle(raw, protocol)


def test_dirty_worktree_fails_closed(raw: dict, protocol: dict) -> None:
    raw["source_dirty_pre"] = True
    with pytest.raises(SeedVarianceError, match="source_dirty_pre"):
        validate_raw_bundle(raw, protocol)


@pytest.mark.skipif(shutil.which("git") is None, reason="git is unavailable")
def test_builder_refuses_a_dirty_worktree(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()

    def _git(*arguments: str) -> None:
        subprocess.run(
            ["git", "-C", str(repository), *arguments],
            check=True,
            capture_output=True,
            text=True,
        )

    _git("init", "--quiet")
    _git("config", "user.email", "fixture@example.invalid")
    _git("config", "user.name", "fixture")
    (repository / "tracked.txt").write_text("one\n", encoding="utf-8")
    _git("add", "tracked.txt")
    _git("commit", "--quiet", "-m", "seed")
    assert len(builder._git_identity(repository)) == 40
    (repository / "tracked.txt").write_text("two\n", encoding="utf-8")
    with pytest.raises(SeedVarianceError, match="dirty tracked worktree"):
        builder._git_identity(repository)


# --------------------------------------------------------------------------- #
# SV-03 and SV-04 inventory
# --------------------------------------------------------------------------- #


def test_valid_raw_bundle_holds_the_exact_frozen_inventory(
    raw: dict, protocol: dict, design: dict
) -> None:
    validated = validate_raw_bundle(raw, protocol)
    assert len(validated["replicates"]) == design["replicate_count"]
    assert [item["training_seed"] for item in validated["replicates"]] == design["training_seeds"]
    total = sum(len(cell["episodes"]) for item in validated["replicates"] for cell in item["arms"])
    assert total == design["expected_terminal_records"] == 450


def test_training_seed_must_match_the_frozen_schedule(raw: dict, protocol: dict) -> None:
    raw["replicates"][1]["training_seed"] = 8741
    with pytest.raises(SeedVarianceError, match="training_seed does not match"):
        validate_raw_bundle(raw, protocol)


def test_environment_seed_block_must_match_the_frozen_schedule(
    raw: dict, protocol: dict
) -> None:
    raw["replicates"][0]["environment_seed_block"] = [8720, 8730]
    with pytest.raises(SeedVarianceError, match="environment_seed_block does not match"):
        validate_raw_bundle(raw, protocol)


def test_replicate_count_must_be_exact(raw: dict, protocol: dict) -> None:
    raw["replicates"].pop()
    with pytest.raises(SeedVarianceError, match="exactly 5 replicates"):
        validate_raw_bundle(raw, protocol)


def test_replicate_index_must_be_ascending(raw: dict, protocol: dict) -> None:
    raw["replicates"][0], raw["replicates"][1] = raw["replicates"][1], raw["replicates"][0]
    with pytest.raises(SeedVarianceError, match="replicate_index must be 0"):
        validate_raw_bundle(raw, protocol)


def test_arm_inventory_must_be_exact_and_ordered(raw: dict, protocol: dict) -> None:
    arms = raw["replicates"][0]["arms"]
    arms[0], arms[1] = arms[1], arms[0]
    with pytest.raises(SeedVarianceError, match="exact frozen arm inventory"):
        validate_raw_bundle(raw, protocol)


def test_missing_arm_fails_closed(raw: dict, protocol: dict) -> None:
    raw["replicates"][0]["arms"].pop()
    with pytest.raises(SeedVarianceError, match="exact frozen arm inventory"):
        validate_raw_bundle(raw, protocol)


def test_missing_evaluation_seed_fails_closed(raw: dict, protocol: dict) -> None:
    _cell(raw, 0, REFERENCE_ARM_ID)["episodes"].pop()
    with pytest.raises(SeedVarianceError, match="exactly 30 records"):
        validate_raw_bundle(raw, protocol)


def test_duplicate_evaluation_seed_fails_closed(raw: dict, protocol: dict) -> None:
    episodes = _cell(raw, 0, REFERENCE_ARM_ID)["episodes"]
    episodes[5] = deepcopy(episodes[4])
    with pytest.raises(SeedVarianceError, match="exact ascending frozen evaluation seed"):
        validate_raw_bundle(raw, protocol)


def test_unexpected_evaluation_seed_fails_closed(raw: dict, protocol: dict) -> None:
    _cell(raw, 0, REFERENCE_ARM_ID)["episodes"][0]["evaluation_seed"] = 20000
    with pytest.raises(SeedVarianceError, match="exact ascending frozen evaluation seed"):
        validate_raw_bundle(raw, protocol)


def test_realized_budget_must_match_the_frozen_expectation(raw: dict, protocol: dict) -> None:
    _cell(raw, 0, REFERENCE_ARM_ID)["realized_timesteps"] = 100000
    with pytest.raises(SeedVarianceError, match="frozen expected budget"):
        validate_raw_bundle(raw, protocol)


@pytest.mark.parametrize(
    ("field", "message"),
    [
        ("audit_protocol_sha256", "frozen audit digest"),
        ("audit_contract_source_sha256", "pinned audit implementation"),
        ("pilot_contract_source_sha256", "pinned pilot implementation"),
    ],
)
def test_inherited_classification_provenance_must_match(
    raw: dict, protocol: dict, field: str, message: str
) -> None:
    """The protocol says which rules; the source pins say which code applied them."""
    _cell(raw, 0, REFERENCE_ARM_ID)[field] = "sha256:" + "0" * 64
    with pytest.raises(SeedVarianceError, match=message):
        validate_raw_bundle(raw, protocol)


def test_pinned_implementations_are_re_hashed_against_disk(raw: dict) -> None:
    """A pin copied into a field is only a string until it is checked."""
    assert svc.verify_inherited_implementations()["inherited_implementations_verified"] is True


def test_evaluation_output_digest_is_carried_into_the_summary(
    raw: dict, protocol: dict
) -> None:
    digest = "sha256:" + "7" * 64
    _cell(raw, 0, REFERENCE_ARM_ID)["evaluation_output_sha256"] = digest
    summary = build_summary(raw, protocol)
    cell = next(
        item
        for item in summary["replicates"][0]["arms"]
        if item["arm_id"] == REFERENCE_ARM_ID
    )
    assert cell["evaluation_output_sha256"] == digest


@pytest.mark.parametrize(
    "field",
    ["training_environment_lock_verified", "evaluation_environment_lock_verified"],
)
def test_unverified_environment_lock_on_a_cell_fails_closed(
    raw: dict, protocol: dict, field: str
) -> None:
    """Training and evaluation are separate runs, so each needs its own flag."""
    _cell(raw, 0, REFERENCE_ARM_ID)[field] = False
    with pytest.raises(SeedVarianceError, match=field):
        validate_raw_bundle(raw, protocol)


def test_receipt_counts_both_lock_verifications_per_cell(
    tmp_path: Path, raw: dict, pinned_lock: dict
) -> None:
    root, analysis = _bundle(tmp_path, raw, pinned_lock)
    receipt = analyse_seed_variance(root, analysis)
    assert receipt["environment_lock_verified_runs"] == 2 * 5 * len(ARM_IDS) == 30


def test_undeclared_raw_field_fails_closed(raw: dict, protocol: dict) -> None:
    raw["notes"] = "hand edited"
    with pytest.raises(SeedVarianceError, match="undeclared fields"):
        validate_raw_bundle(raw, protocol)


def test_undeclared_episode_field_fails_closed(raw: dict, protocol: dict) -> None:
    _cell(raw, 0, REFERENCE_ARM_ID)["episodes"][0]["note"] = "x"
    with pytest.raises(SeedVarianceError, match="undeclared fields"):
        validate_raw_bundle(raw, protocol)


# --------------------------------------------------------------------------- #
# SV-05 environment lock
# --------------------------------------------------------------------------- #


def test_pinned_measured_full_lock_is_accepted(protocol: dict, pinned_lock: dict) -> None:
    status = svc.check_environment_lock(protocol, pinned_lock)
    assert status["environment_lock_satisfied"] is True
    assert status["environment_lock_threading"] == "AMBIENT_THREADING_PINNED"


def test_unpinned_threading_lock_is_rejected(protocol: dict, pinned_lock: dict) -> None:
    record = deepcopy(pinned_lock)
    record["locked"]["determinism_environment"]["OMP_NUM_THREADS"] = {
        "state": "SET",
        "value": "4",
    }
    _refreeze_lock(record)
    with pytest.raises(SeedVarianceError, match="threading .* does not"):
        svc.check_environment_lock(protocol, record)


def test_partial_lock_is_rejected(protocol: dict, pinned_lock: dict) -> None:
    record = deepcopy(pinned_lock)
    record["locked"]["plant_fingerprint"] = {
        "state": "UNAVAILABLE",
        "reason": "mujoco import failed",
    }
    _refreeze_lock(record)
    with pytest.raises(SeedVarianceError, match="completeness .* does not"):
        svc.check_environment_lock(protocol, record)


def test_synthetic_lock_class_is_rejected(protocol: dict, pinned_lock: dict) -> None:
    record = deepcopy(pinned_lock)
    record["lock_class"] = SYNTHETIC_LOCK_CLASS
    with pytest.raises(SeedVarianceError, match="class .* does not meet"):
        svc.check_environment_lock(protocol, record)


def test_invalid_lock_record_is_rejected(protocol: dict, pinned_lock: dict) -> None:
    record = deepcopy(pinned_lock)
    record["locked_sha256"] = "sha256:" + "1" * 64
    with pytest.raises(SeedVarianceError, match="environment lock record is invalid"):
        svc.check_environment_lock(protocol, record)


def test_raw_lock_digest_must_match_the_bundle_lock_record(
    tmp_path: Path, raw: dict, pinned_lock: dict
) -> None:
    raw["environment_lock_sha256"] = "sha256:" + "2" * 64
    root, analysis = _bundle(tmp_path, raw, pinned_lock)
    with pytest.raises(SeedVarianceError, match="does not match the bundle's lock record"):
        analyse_seed_variance(root, analysis)


# --------------------------------------------------------------------------- #
# SV-06 analysis unit
# --------------------------------------------------------------------------- #


def test_method_level_denominator_is_the_replicate_count(
    raw: dict, protocol: dict, design: dict
) -> None:
    summary = build_summary(raw, protocol)
    assert summary["analysis_unit"] == "TRAINING_REPLICATE"
    for candidate_id in CANDIDATE_ARM_IDS:
        method_level = _method_level(summary, candidate_id)
        assert method_level["method_level_n"] == design["replicate_count"] == 5
        assert method_level["method_level_n"] not in summary["forbidden_denominators"]
    assert summary["forbidden_denominators"] == [150, 450]


def test_pseudo_replicated_denominator_is_refused(protocol: dict, design: dict) -> None:
    differences = [
        {
            "replicate_index": index,
            "state": "OBSERVED",
            "lower_pp": -1.0,
            "upper_pp": -1.0,
            "width_pp": 0.0,
            "point_identified": True,
            "sign": SIGN_NEGATIVE,
            "reason": None,
        }
        for index in range(150)
    ]
    paired = [{"replicate_index": index, "paired_sd_pp": 1.0, "reason": None} for index in range(150)]
    with pytest.raises(SeedVarianceError, match="must equal replicate_count"):
        svc._method_level(differences, paired, design)


def test_receipt_validation_refuses_a_pseudo_replicated_method_level_n(
    tmp_path: Path, raw: dict, pinned_lock: dict
) -> None:
    root, analysis = _bundle(tmp_path, raw, pinned_lock)
    receipt = analyse_seed_variance(root, analysis)
    summary_path = analysis / SUMMARY_ARTIFACT
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["candidates"][0]["method_level"]["method_level_n"] = 150
    payload = svc._json_bytes(summary)
    summary_path.write_bytes(payload)
    receipt_path = analysis / svc.RECEIPT_ARTIFACT
    stored = json.loads(receipt_path.read_text(encoding="utf-8"))
    stored["summary_sha256"] = svc._sha256_bytes(payload)
    receipt_path.write_bytes(svc._json_bytes(stored))
    with pytest.raises(SeedVarianceError, match="PSEUDO_REPLICATION_FORBIDDEN"):
        validate_seed_variance_bundle(receipt_path)
    assert receipt["retained_blocker_count"] == 0


# --------------------------------------------------------------------------- #
# SV-07 and SV-08 retention and upward composition
# --------------------------------------------------------------------------- #


def test_all_comparable_bundle_is_point_identified(raw: dict, protocol: dict) -> None:
    summary = build_summary(raw, protocol)
    assert summary["seed_variance_status"] == STATUS_CLEAN
    assert summary["retained_blockers"] == []
    for candidate_id in CANDIDATE_ARM_IDS:
        method_level = _method_level(summary, candidate_id)
        bound = method_level["theta_bound_pp"]
        assert bound["state"] == "OBSERVED"
        assert bound["lower_pp"] == bound["upper_pp"]
        assert bound["width_pp"] == 0.0
        assert method_level["sign"] == SIGN_NEGATIVE
        assert method_level["between_replicate_sd_pp"] is not None
        assert method_level["sample_size_decision_input_ready"] is True
        assert method_level["sign_identified_replicate_count"] == 5


def test_censored_candidate_widens_the_bound_and_withholds_the_sd(
    censored_raw: dict, protocol: dict
) -> None:
    summary = build_summary(censored_raw, protocol)
    assert summary["seed_variance_status"] == STATUS_BLOCKED
    censored = _method_level(summary, "V7C_FILTERED_ACTION")
    assert censored["theta_bound_pp"]["state"] == "OBSERVED"
    assert censored["theta_bound_pp"]["lower_pp"] < 0.0 < censored["theta_bound_pp"]["upper_pp"]
    assert censored["sign"] == SIGN_UNIDENTIFIED
    assert censored["between_replicate_sd_pp"] is None
    assert censored["between_replicate_sd_reason"] == REASON_PARTIAL_SD
    assert censored["sample_size_decision_input_ready"] is False
    # The comparable candidate in the same bundle is untouched: censoring in one
    # arm must not contaminate another.
    comparable = _method_level(summary, "V7B_REDUCED_JOINT_ENVELOPE")
    assert comparable["between_replicate_sd_pp"] is not None
    assert comparable["sign"] == SIGN_NEGATIVE


def test_censored_cells_are_intervals_and_retain_their_counts(
    censored_raw: dict, protocol: dict
) -> None:
    summary = build_summary(censored_raw, protocol)
    for replicate in summary["replicates"]:
        cell = next(
            item for item in replicate["arms"] if item["arm_id"] == "V7C_FILTERED_ACTION"
        )
        assert cell["cell_state"] == CELL_PARTIALLY_IDENTIFIED
        assert cell["mean_bound_pct"]["width_pct"] > 0.0
        assert cell["comparability_counts"]["EXPOSURE_CENSORED"] == 30
        assert cell["exposure_counts"]["EARLY_TERMINATED"] == 30
        assert cell["within_replicate_level_sd_pct"] is None
        assert cell["episode_count"] == 30


def test_method_failure_blocks_the_cell_without_deleting_it(
    method_failure_raw: dict, protocol: dict
) -> None:
    summary = build_summary(method_failure_raw, protocol)
    cell = next(
        item
        for item in summary["replicates"][2]["arms"]
        if item["arm_id"] == "V7B_REDUCED_JOINT_ENVELOPE"
    )
    assert cell["cell_state"] == CELL_BLOCKED_METHOD_FAILURE
    assert cell["mean_bound_pct"]["state"] == "NULL"
    # The failure is retained in the counts, not dropped to rescue a mean.
    assert cell["comparability_counts"]["METHOD_FAILURE_NOT_CENSORING"] == 1
    assert cell["comparability_counts"]["COMPARABLE"] == 29
    assert cell["episode_count"] == 30
    assert cell["terminal_counts"]["FAILED"] == 1


def test_method_failure_makes_the_method_level_bound_null(
    method_failure_raw: dict, protocol: dict
) -> None:
    summary = build_summary(method_failure_raw, protocol)
    method_level = _method_level(summary, "V7B_REDUCED_JOINT_ENVELOPE")
    assert method_level["theta_bound_pp"]["state"] == "NULL"
    assert method_level["sign"] == SIGN_NULL
    assert method_level["between_replicate_sd_pp"] is None
    assert method_level["between_replicate_sd_reason"] == REASON_BLOCKED_PAIR
    assert method_level["blocked_replicate_indices"] == [2]
    assert method_level["sample_size_decision_input_ready"] is False


def test_every_withheld_statistic_appears_as_a_retained_blocker(
    censored_raw: dict, protocol: dict
) -> None:
    summary = build_summary(censored_raw, protocol)
    scopes = {(item["scope"], item["arm_id"], item["state"]) for item in summary["retained_blockers"]}
    assert ("cell", "V7C_FILTERED_ACTION", CELL_PARTIALLY_IDENTIFIED) in scopes
    assert ("method_level", "V7C_FILTERED_ACTION", "BETWEEN_REPLICATE_SD_WITHHELD") in scopes
    assert ("method_level", "V7C_FILTERED_ACTION", "SIGN_UNIDENTIFIED") in scopes


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda episode: episode["full_horizon_duty_bound_pct"].update({"upper_pct": 90.0, "width_pct": 90.0 - episode["full_horizon_duty_bound_pct"]["lower_pct"]}),
            "must be degenerate for a comparable episode",
        ),
        (
            lambda episode: episode["full_horizon_duty_bound_pct"].update({"upper_pct": 0.0}),
            "bound is inverted",
        ),
        (
            lambda episode: episode["full_horizon_duty_bound_pct"].update({"width_pct": 5.0}),
            "width_pct does not match",
        ),
        (
            lambda episode: episode["full_horizon_duty_bound_pct"].update(
                {"state": "NULL", "lower_pct": None, "upper_pct": None, "width_pct": None, "reason": "x"}
            ),
            "not a method failure",
        ),
        (
            lambda episode: episode["full_horizon_duty_bound_pct"].update({"reason": "unexpected"}),
            "reason must be null",
        ),
        (
            lambda episode: episode.update({"exposure_class": "EARLY_TERMINATED"}),
            "comparable but not fully exposed",
        ),
        (
            lambda episode: episode["full_horizon_duty_bound_pct"].update({"lower_pct": 120.0}),
            "within 0..100 percent",
        ),
    ],
)
def test_inconsistent_inherited_bound_fails_closed(
    raw: dict, protocol: dict, mutate, message: str
) -> None:
    """The audit is upstream authority, but its output arrives here as data."""
    mutate(_cell(raw, 0, REFERENCE_ARM_ID)["episodes"][0])
    with pytest.raises(SeedVarianceError, match=message):
        validate_raw_bundle(raw, protocol)


def test_censored_episode_with_a_degenerate_bound_fails_closed(
    censored_raw: dict, protocol: dict
) -> None:
    episode = _cell(censored_raw, 0, "V7C_FILTERED_ACTION")["episodes"][0]
    bound = episode["full_horizon_duty_bound_pct"]
    bound["upper_pct"] = bound["lower_pct"]
    bound["width_pct"] = 0.0
    with pytest.raises(SeedVarianceError, match="non-degenerate interval for a censored episode"):
        validate_raw_bundle(censored_raw, protocol)


def test_method_failure_carrying_a_measured_bound_fails_closed(
    method_failure_raw: dict, protocol: dict
) -> None:
    episode = next(
        item
        for item in _cell(method_failure_raw, 2, "V7B_REDUCED_JOINT_ENVELOPE")["episodes"]
        if item["comparability_state"] == "METHOD_FAILURE_NOT_CENSORING"
    )
    episode["full_horizon_duty_bound_pct"] = {
        "state": "OBSERVED",
        "lower_pct": 10.0,
        "upper_pct": 10.0,
        "width_pct": 0.0,
        "reason": None,
    }
    with pytest.raises(SeedVarianceError, match="method failure"):
        validate_raw_bundle(method_failure_raw, protocol)


def test_censored_state_requires_early_termination(raw: dict, protocol: dict) -> None:
    episode = _cell(raw, 0, REFERENCE_ARM_ID)["episodes"][0]
    episode["comparability_state"] = "EXPOSURE_CENSORED"
    with pytest.raises(SeedVarianceError, match="censored but not early terminated"):
        validate_raw_bundle(raw, protocol)


# --------------------------------------------------------------------------- #
# SV-09 and SV-12 retained labels and readiness
# --------------------------------------------------------------------------- #


def test_summary_retains_scope_and_comparability_labels(raw: dict, protocol: dict) -> None:
    summary = build_summary(raw, protocol)
    assert summary["training_replicate_scope"] == "CONDITIONAL_ON_FIXED_WARM_START"
    assert summary["cross_protocol_comparability"] == "NON_VERIFIABLE_ENVIRONMENT"
    assert summary["claim_boundary"] == protocol["claim_boundary"]


def test_summary_never_selects_a_candidate(raw: dict, protocol: dict) -> None:
    summary = build_summary(raw, protocol)
    assert summary["selected_candidate_arm_id"] is None
    assert summary["selection_permitted"] is False
    assert summary["method_level_power_ready"] is False
    assert summary["statistics_ready"] is False
    assert summary["paper_data_ready"] is False


def test_clean_bundle_still_reports_no_candidate_and_no_power(
    tmp_path: Path, raw: dict, pinned_lock: dict
) -> None:
    """Even the happy path must not turn a variance estimate into a selection."""
    root, analysis = _bundle(tmp_path, raw, pinned_lock)
    receipt = analyse_seed_variance(root, analysis)
    assert receipt["seed_variance_status"] == STATUS_CLEAN
    assert receipt["selected_candidate_arm_id"] is None
    assert receipt["method_level_power_ready"] is False
    assert receipt["paper_data_ready"] is False
    assert receipt["training_replicate_scope"] == "CONDITIONAL_ON_FIXED_WARM_START"
    assert validate_seed_variance_bundle(analysis / svc.RECEIPT_ARTIFACT)["contract_valid"] is True


# --------------------------------------------------------------------------- #
# SV-10 artifact identity and read-only access
# --------------------------------------------------------------------------- #


def test_missing_source_artifact_fails_closed(
    tmp_path: Path, raw: dict, pinned_lock: dict
) -> None:
    root, analysis = _bundle(tmp_path, raw, pinned_lock)
    (root / RAW_ARTIFACT).unlink()
    with pytest.raises(SeedVarianceError, match="missing a required artifact"):
        analyse_seed_variance(root, analysis)


def test_output_root_inside_the_bundle_is_refused(
    tmp_path: Path, raw: dict, pinned_lock: dict
) -> None:
    root, _ = _bundle(tmp_path, raw, pinned_lock)
    with pytest.raises(SeedVarianceError, match="must live outside the source bundle"):
        analyse_seed_variance(root, root / "analysis")


def test_source_drift_during_the_run_is_detected(
    tmp_path: Path, raw: dict, pinned_lock: dict
) -> None:
    root, _ = _bundle(tmp_path, raw, pinned_lock)
    bundle = svc.read_source_bundle(root)
    (root / RAW_ARTIFACT).write_bytes(svc._json_bytes(raw) + b"\n")
    with pytest.raises(SeedVarianceError, match="source artifact digests changed"):
        svc._verify_read_only(bundle)


def test_new_file_in_the_bundle_during_the_run_is_detected(
    tmp_path: Path, raw: dict, pinned_lock: dict
) -> None:
    root, _ = _bundle(tmp_path, raw, pinned_lock)
    bundle = svc.read_source_bundle(root)
    (root / "extra.json").write_text("{}", encoding="utf-8")
    with pytest.raises(SeedVarianceError, match="bundle file set changed"):
        svc._verify_read_only(bundle)


def test_receipt_summary_digest_must_match(
    tmp_path: Path, raw: dict, pinned_lock: dict
) -> None:
    root, analysis = _bundle(tmp_path, raw, pinned_lock)
    analyse_seed_variance(root, analysis)
    summary_path = analysis / SUMMARY_ARTIFACT
    summary_path.write_bytes(summary_path.read_bytes() + b"\n")
    with pytest.raises(SeedVarianceError, match="summary digest does not match"):
        validate_seed_variance_bundle(analysis / svc.RECEIPT_ARTIFACT)


def test_receipt_records_read_only_verification(
    tmp_path: Path, raw: dict, pinned_lock: dict
) -> None:
    root, analysis = _bundle(tmp_path, raw, pinned_lock)
    receipt = analyse_seed_variance(root, analysis)
    assert receipt["source_bundle_read_only_verified"] is True
    assert receipt["source_artifact_count"] == 3
    assert receipt["source_total_bytes"] > 0


def test_duplicate_json_keys_in_the_raw_artifact_fail_closed(
    tmp_path: Path, raw: dict, pinned_lock: dict
) -> None:
    root, analysis = _bundle(tmp_path, raw, pinned_lock)
    (root / RAW_ARTIFACT).write_text(
        '{"schema_version": "a", "schema_version": "b"}', encoding="utf-8"
    )
    with pytest.raises(SeedVarianceError, match="duplicate object keys"):
        analyse_seed_variance(root, analysis)


def test_non_finite_json_constant_in_the_raw_artifact_fails_closed(
    tmp_path: Path, raw: dict, pinned_lock: dict
) -> None:
    root, analysis = _bundle(tmp_path, raw, pinned_lock)
    (root / RAW_ARTIFACT).write_text('{"value": NaN}', encoding="utf-8")
    with pytest.raises(SeedVarianceError, match="non-finite JSON constant"):
        analyse_seed_variance(root, analysis)


# --------------------------------------------------------------------------- #
# SV-11 independent replay
# --------------------------------------------------------------------------- #


def test_independent_replay_reaches_exact_identity(
    tmp_path: Path, raw: dict, pinned_lock: dict
) -> None:
    root, analysis = _bundle(tmp_path, raw, pinned_lock)
    receipt = analyse_seed_variance(root, analysis)
    assert receipt["replay"]["replay_exact"] is True
    assert receipt["replay"]["replay_interpreter_flags"] == ["-I", "-S"]
    assert receipt["replay"]["summary_sha256"] == receipt["summary_sha256"]


@pytest.mark.parametrize("fixture_name", ["raw", "censored_raw", "method_failure_raw"])
def test_replay_is_exact_on_every_regression_case(
    tmp_path: Path, pinned_lock: dict, request: pytest.FixtureRequest, fixture_name: str
) -> None:
    payload = request.getfixturevalue(fixture_name)
    root, analysis = _bundle(tmp_path, payload, pinned_lock)
    receipt = analyse_seed_variance(root, analysis)
    assert receipt["replay"]["replay_exact"] is True


def test_replay_detects_a_tampered_summary(
    tmp_path: Path, raw: dict, pinned_lock: dict
) -> None:
    root, analysis = _bundle(tmp_path, raw, pinned_lock)
    analyse_seed_variance(root, analysis)
    summary_path = analysis / SUMMARY_ARTIFACT
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["candidates"][0]["method_level"]["between_replicate_sd_pp"] = 0.0
    summary_path.write_bytes(svc._json_bytes(summary))
    with pytest.raises(SeedVarianceError, match="replay"):
        svc.run_replay(root, summary_path)


def test_replay_module_imports_no_repository_code_at_top_level() -> None:
    """A repository import would break ``python -I -S`` and the independence.

    Reusing the contract's own helpers would make the replay restate that
    contract's arithmetic instead of checking it, so the constraint is asserted
    structurally rather than left to reviewer discipline.
    """
    tree = ast.parse(REPLAY_PATH.read_text(encoding="utf-8"))
    roots: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])
    assert roots <= REPLAY_ALLOWED_IMPORTS, sorted(roots - REPLAY_ALLOWED_IMPORTS)
    source = REPLAY_PATH.read_text(encoding="utf-8")
    assert "training_seed_variance_contract" not in source.replace(
        "training_seed_variance_contract``", ""
    ).replace("``training_seed_variance_contract", "")


# --------------------------------------------------------------------------- #
# bundle class binding and the CLI
# --------------------------------------------------------------------------- #


def test_builder_cannot_emit_the_development_bundle_class(
    design: dict, pinned_lock: dict
) -> None:
    payload = builder.build_raw_bundle(design, pinned_lock["locked_sha256"], FIXTURE_GIT_SHA)
    assert payload["bundle_class"] == SYNTHETIC_BUNDLE_CLASS
    source = (BACKEND_ROOT / "build_training_seed_variance_regression_bundle.py").read_text(
        encoding="utf-8"
    )
    assert DEVELOPMENT_BUNDLE_CLASS not in source


def test_bundle_class_is_propagated_verbatim(
    tmp_path: Path, raw: dict, pinned_lock: dict
) -> None:
    root, analysis = _bundle(tmp_path, raw, pinned_lock)
    receipt = analyse_seed_variance(root, analysis)
    summary = json.loads((analysis / SUMMARY_ARTIFACT).read_text(encoding="utf-8"))
    assert receipt["bundle_class"] == summary["bundle_class"] == SYNTHETIC_BUNDLE_CLASS


def test_unknown_bundle_class_fails_closed(raw: dict, protocol: dict) -> None:
    raw["bundle_class"] = "PRODUCTION"
    with pytest.raises(SeedVarianceError, match="bundle_class"):
        validate_raw_bundle(raw, protocol)


def _cli(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CONTRACT_PATH), *arguments],
        capture_output=True,
        text=True,
        check=False,
        cwd=BACKEND_ROOT,
    )


def test_cli_exits_zero_on_complete_evidence(
    tmp_path: Path, raw: dict, pinned_lock: dict
) -> None:
    root, analysis = _bundle(tmp_path, raw, pinned_lock)
    result = _cli("analyse", str(root), str(analysis))
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["seed_variance_status"] == STATUS_CLEAN


def test_cli_exits_one_on_retained_blockers(
    tmp_path: Path, censored_raw: dict, pinned_lock: dict
) -> None:
    root, analysis = _bundle(tmp_path, censored_raw, pinned_lock)
    result = _cli("analyse", str(root), str(analysis))
    assert result.returncode == 1, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["seed_variance_status"] == STATUS_BLOCKED
    assert payload["retained_blocker_count"] > 0


def test_cli_exits_two_on_structural_failure(tmp_path: Path) -> None:
    result = _cli("analyse", str(tmp_path / "absent"), str(tmp_path / "out"))
    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["validation_status"] == "STRUCTURAL_FAILURE"
    assert payload["paper_data_ready"] is False


# --------------------------------------------------------------------------- #
# SV-01 inherited pilot design
# --------------------------------------------------------------------------- #


def test_pilot_inheritance_is_verified_against_the_real_pilot_protocol(
    protocol: dict,
) -> None:
    inheritance = svc.verify_pilot_inheritance(protocol)
    assert inheritance["pilot_inheritance_verified"] is True
    assert inheritance["pilot_protocol_id"] == "PILOT-V7-ACTION-INTERFACE-DEV-V1"
    assert inheritance["pilot_independent_training_replicates_per_arm"] == 1


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda payload: payload["source_baseline"].update(
                {"warm_start_sha256": "sha256:" + "0" * 64}
            ),
            "warm_start_sha256 does not match the pilot",
        ),
        (
            lambda payload: payload["source_baseline"].update({"warm_start_bytes": 1}),
            "warm_start_bytes does not match the pilot",
        ),
        (
            lambda payload: payload.update({"arms": list(reversed(payload["arms"]))}),
            "arm inventory does not match the pilot",
        ),
        (
            lambda payload: payload["training_design"].update({"parallel_envs": 8}),
            "parallel_envs does not match the pilot",
        ),
        (
            lambda payload: payload["training_design"].update(
                {"expected_realized_timesteps": 61440}
            ),
            "expected_realized_timesteps does not match the pilot",
        ),
        (
            lambda payload: payload["evaluation_design"].update(
                {"episodes_per_arm_replicate": 20}
            ),
            "episodes per arm do not match the pilot",
        ),
        (
            lambda payload: payload["evaluation_design"].update(
                {"evaluation_seed_start": 17000}
            ),
            "evaluation_seed_start does not match the pilot",
        ),
        (
            lambda payload: payload["evaluation_design"].update(
                {"sealed_formal_seed_range": [21000, 21029]}
            ),
            "sealed_formal_seed_range does not match the pilot",
        ),
        (
            lambda payload: payload["prerequisite_contracts"].update(
                {"pilot_protocol_sha256": "sha256:" + "1" * 64}
            ),
            "pilot protocol digest drift",
        ),
    ],
)
def test_broken_pilot_inheritance_fails_closed(protocol: dict, mutate, message: str) -> None:
    payload = deepcopy(protocol)
    mutate(payload)
    with pytest.raises(SeedVarianceError, match=message):
        svc.verify_pilot_inheritance(payload)


def test_pilot_protocol_substitution_fails_closed(tmp_path: Path, protocol: dict) -> None:
    decoy = tmp_path / "pilot.json"
    decoy.write_text(json.dumps({"protocol_id": "PILOT-V7-ACTION-INTERFACE-DEV-V1"}), encoding="utf-8")
    with pytest.raises(SeedVarianceError, match="pilot protocol digest drift"):
        svc.verify_pilot_inheritance(protocol, decoy)


def test_receipt_records_pilot_inheritance(
    tmp_path: Path, raw: dict, pinned_lock: dict
) -> None:
    root, analysis = _bundle(tmp_path, raw, pinned_lock)
    receipt = analyse_seed_variance(root, analysis)
    assert receipt["pilot_inheritance_verified"] is True
    assert receipt["bundle_class_is_declared_not_derived"] is True


def test_symlink_escaping_the_bundle_fails_closed(
    tmp_path: Path, raw: dict, pinned_lock: dict
) -> None:
    outside = tmp_path / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    root, analysis = _bundle(tmp_path, raw, pinned_lock)
    (root / RAW_ARTIFACT).unlink()
    (root / RAW_ARTIFACT).symlink_to(outside)
    with pytest.raises(SeedVarianceError, match="escapes the bundle root"):
        analyse_seed_variance(root, analysis)


def test_fixture_paired_differences_vary_between_replicates(
    raw: dict, protocol: dict
) -> None:
    """The fixture must actually exercise the phenomenon under test.

    If all three arms shared one replicate offset it would cancel in the paired
    contrast, between_replicate_sd would collapse toward zero, and the suite
    would be green while never testing between-replicate variance at all.
    """
    summary = build_summary(raw, protocol)
    for candidate_id in CANDIDATE_ARM_IDS:
        method_level = _method_level(summary, candidate_id)
        differences = [
            item["lower_pp"]
            for item in next(
                candidate
                for candidate in summary["candidates"]
                if candidate["candidate_arm_id"] == candidate_id
            )["replicate_paired_differences"]
        ]
        assert len(set(differences)) == 5
        # Between-replicate spread must be comparable to the within-replicate
        # spread, not orders of magnitude below it.
        assert method_level["between_replicate_sd_pp"] > 0.5
        assert method_level["variance_ratio_between_over_within"] > 0.5


# --------------------------------------------------------------------------- #
# amendments may only narrow, and only before execution
# --------------------------------------------------------------------------- #


def test_frozen_protocol_carries_the_pre_execution_driver_amendment(protocol: dict) -> None:
    amendment = protocol["amendment"]
    assert amendment["amendment_id"] == "SEEDVAR-AMENDMENT-01-DRIVER-IDENTITY"
    assert amendment["applied_before_any_execution"] is True
    assert amendment["narrowing_only"] is True
    assert amendment["superseded_pins"]["training_driver_source_sha256"].startswith("sha256:")
    for item in (
        "training seed schedule and environment seed blocks",
        "analysis unit and forbidden denominators",
        "exposure censoring composition rules",
        "the prohibition on selection",
    ):
        assert item in amendment["unchanged_by_this_amendment"]


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda payload: payload["amendment"].update({"narrowing_only": False}),
            "must be narrowing only",
        ),
        (
            lambda payload: payload["amendment"].update(
                {"applied_before_any_execution": False}
            ),
            "before any execution",
        ),
        (
            lambda payload: payload["amendment"].update({"defect": ""}),
            "defect",
        ),
        (
            lambda payload: payload["amendment"].update({"resolution": ""}),
            "resolution",
        ),
    ],
)
def test_widening_or_post_hoc_amendment_fails_closed(
    protocol: dict, mutate, message: str
) -> None:
    """A post-hoc amendment would let the design be rewritten around the data."""
    payload = deepcopy(protocol)
    mutate(payload)
    with pytest.raises(SeedVarianceError, match=message):
        svc.validate_protocol(payload)

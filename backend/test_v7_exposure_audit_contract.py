"""Synthetic, fail-closed tests for the v7 exposure-censoring validity audit."""

from __future__ import annotations

import ast
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

import v7_exposure_audit_contract as audit_module
from v7_exposure_audit_contract import (
    AUDIT_PROTOCOL_SHA256,
    AUDIT_STATUS_BLOCKED,
    DEVELOPMENT_BUNDLE_CLASS,
    FROZEN_PILOT_RECEIPT_SHA256,
    SYNTHETIC_BUNDLE_CLASS,
    V7ExposureAuditError,
    audit_v7_exposure_censoring,
    validate_v7_exposure_audit_bundle,
)
import v7_exposure_audit_replay
import v7_pilot_replay


BACKEND_ROOT = Path(__file__).resolve().parent
AUDIT_PROTOCOL_PATH = BACKEND_ROOT / "v7_exposure_audit_protocol.json"
PILOT_PROTOCOL_PATH = BACKEND_ROOT / "rl" / "v7_action_interface_pilot_protocol.json"
REPLAY_SCRIPT = BACKEND_ROOT / "v7_exposure_audit_replay.py"
SOURCE_SHA = "a" * 40
FULL_STEPS = 450
SUBSTEPS_PER_STEP = 10
FULL_SUBSTEPS = FULL_STEPS * SUBSTEPS_PER_STEP
CONTROL_PERIOD_S = 0.02
ARM_IDS = ("V7A_REWARD_ONLY", "V7B_REDUCED_JOINT_ENVELOPE", "V7C_FILTERED_ACTION")
SEEDS = tuple(range(18000, 18030))
STDLIB_IMPORTS = {
    "__future__",
    "collections",
    "hashlib",
    "json",
    "math",
    "pathlib",
    "re",
    "statistics",
    "sys",
    "typing",
}


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _write_json(path: Path, payload: object) -> None:
    """Mirror the production canonical writer byte for byte."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
        newline="\n",
    )


_RECORDER_LABEL_CACHE: tuple[str, ...] | None = None


def _recorder_labels() -> tuple[str, ...]:
    """Independently reproduce the recorder's end-of-step accumulated phase labels."""
    global _RECORDER_LABEL_CACHE
    if _RECORDER_LABEL_CACHE is not None:
        return _RECORDER_LABEL_CACHE
    task_contract = json.loads(PILOT_PROTOCOL_PATH.read_text("utf-8"))["task_contract"]
    assert task_contract["control_rate_hz"] == 1.0 / CONTROL_PERIOD_S
    assert task_contract["duration_s"] == FULL_STEPS * CONTROL_PERIOD_S
    windows = [
        (str(item["phase_id"]), float(item["start_s"]), float(item["end_s"]))
        for item in json.loads(AUDIT_PROTOCOL_PATH.read_text("utf-8"))["frozen_phase_schedule"]
    ]
    labels: list[str] = []
    accumulated = 0.0
    for _ in range(FULL_STEPS):
        accumulated += CONTROL_PERIOD_S
        labels.append(
            next(
                (
                    phase_id
                    for phase_id, start_s, end_s in windows
                    if start_s <= accumulated < end_s
                ),
                windows[-1][0],
            )
        )
    _RECORDER_LABEL_CACHE = tuple(labels)
    return _RECORDER_LABEL_CACHE


def _over_count(arm_index: int, seed: int, step: int, scale: int) -> int:
    """Deterministic, RNG-free per-substep saturation count in [0, scale)."""
    if scale <= 0:
        return 0
    value = (
        seed * 6364136223846793005 + step * 1442695040888963407 + arm_index * 2654435761
    ) & ((1 << 63) - 1)
    value ^= value >> 29
    return value % scale


def _measurement(state: str, value: object, reason: str | None) -> dict[str, object]:
    return {"state": state, "value": value, "reason": reason}


def _episode_row(
    arm_index: int,
    seed: int,
    *,
    steps: int,
    scale: int,
    kind: str,
) -> dict[str, object]:
    """Build one canonical ``V7_PILOT_RAW_EPISODES_V1`` episode row."""
    labels = _recorder_labels()
    if kind == "TERMINAL_FAILURE":
        reason = "EVALUATION_PROCESS_FAILED_BEFORE_ANY_CONTROL_STEP"
        measurements = {
            "no_fall": _measurement("NULL", None, reason),
            "steady_speed_mps": _measurement("NULL", None, reason),
            "steady_progress_m": _measurement("NULL", None, reason),
            "final_stop_speed_mps": _measurement("NULL", None, reason),
            "lateral_drift_m": _measurement("NULL", None, reason),
            "saturation_duty_pct": _measurement("NULL", None, reason),
        }
        return {
            "evaluation_seed": seed,
            "terminal_record_state": "FAILED",
            "outcome_state": "NULL",
            "reason": reason,
            "measurements": measurements,
            "gates": v7_pilot_replay._gate_results(measurements),
            "control_step_trace": [],
            "trace_receipt": {
                "sample_rate_hz": 500.0,
                "control_step_count": 0,
                "saturation_substeps_total": 0,
                "saturation_substeps_over_threshold": 0,
                "recomputed_saturation_duty_pct": None,
                "reported_saturation_duty_pct": None,
                "reported_absolute_delta": None,
                "action_operator_state": "NULL",
                "action_operator_max_abs_delta": None,
            },
        }
    trace: list[dict[str, object]] = []
    over_total = 0
    for step in range(steps):
        over = _over_count(arm_index, seed, step, scale)
        over_total += over
        trace.append({
            "control_step": step,
            "command_phase": labels[step],
            "requested_action": [0.0] * 12,
            "applied_action": [0.0] * 12,
            "joint_target_rad": [0.0] * 12,
            "applied_action_delta_l2": 0.0,
            "requested_applied_delta_l2": 0.0,
            "saturation_substeps_over_threshold": over,
            "saturation_substeps_total": SUBSTEPS_PER_STEP,
        })
    substep_total = steps * SUBSTEPS_PER_STEP
    duty = round(100.0 * over_total / substep_total, 6)
    fell = steps < FULL_STEPS
    if kind == "EARLY_METHOD_FAILURE":
        reason = "SOURCE_EVALUATOR_REPORTED_NAN"
        measurements = {
            "no_fall": _measurement("OBSERVED", not fell, None),
            "steady_speed_mps": _measurement("NULL", None, reason),
            "steady_progress_m": _measurement("NULL", None, reason),
            "final_stop_speed_mps": _measurement("NULL", None, reason),
            "lateral_drift_m": _measurement("NULL", None, reason),
            "saturation_duty_pct": _measurement("NULL", None, reason),
        }
        outcome_state = "NULL"
    elif kind == "EARLY_NULL":
        reason = "EARLY_TERMINATION_REQUIRED_OUTCOME_UNOBSERVED"
        measurements = {
            "no_fall": _measurement("OBSERVED", not fell, None),
            "steady_speed_mps": _measurement("NULL", None, reason),
            "steady_progress_m": _measurement("NULL", None, reason),
            "final_stop_speed_mps": _measurement("NULL", None, reason),
            "lateral_drift_m": _measurement("NULL", None, reason),
            "saturation_duty_pct": _measurement("OBSERVED", duty, None),
        }
        outcome_state = "NULL"
    else:
        reason = None
        measurements = {
            "no_fall": _measurement("OBSERVED", not fell, None),
            "steady_speed_mps": _measurement("OBSERVED", 0.6, None),
            "steady_progress_m": _measurement("OBSERVED", 2.4, None),
            "final_stop_speed_mps": _measurement("OBSERVED", 0.05, None),
            "lateral_drift_m": _measurement("OBSERVED", 0.05, None),
            "saturation_duty_pct": _measurement("OBSERVED", duty, None),
        }
        outcome_state = "OBSERVED"
    return {
        "evaluation_seed": seed,
        "terminal_record_state": "COMPLETED",
        "outcome_state": outcome_state,
        "reason": reason,
        "measurements": measurements,
        "gates": v7_pilot_replay._gate_results(measurements),
        "control_step_trace": trace,
        "trace_receipt": {
            "sample_rate_hz": 500.0,
            "control_step_count": steps,
            "saturation_substeps_total": substep_total,
            "saturation_substeps_over_threshold": over_total,
            "recomputed_saturation_duty_pct": duty,
            "reported_saturation_duty_pct": (
                None if measurements["saturation_duty_pct"]["state"] != "OBSERVED" else duty
            ),
            "reported_absolute_delta": (
                None if measurements["saturation_duty_pct"]["state"] != "OBSERVED" else 0.0
            ),
            "action_operator_state": "PASS",
            "action_operator_max_abs_delta": 0.0,
        },
    }


def _default_plan() -> dict[str, dict[str, object]]:
    """Arm layouts that exercise every retained comparability state."""
    return {
        "V7A_REWARD_ONLY": {"scale": 8, "steps": FULL_STEPS, "kind": "FULL", "overrides": {}},
        "V7B_REDUCED_JOINT_ENVELOPE": {
            "scale": 5,
            "steps": FULL_STEPS,
            "kind": "FULL",
            "overrides": {
                # An episode that ends inside FINAL_STAND still reports every
                # required numeric, so it looks arithmetically clean while
                # being exposure censored.
                18011: {"steps": 430, "kind": "FULL"},
                18015: {"steps": 120, "kind": "EARLY_NULL"},
            },
        },
        "V7C_FILTERED_ACTION": {"scale": 0, "steps": 60, "kind": "EARLY_NULL", "overrides": {}},
    }


def _raw_arm(arm_index: int, arm_id: str, layout: dict[str, object]) -> dict[str, object]:
    overrides = layout.get("overrides") or {}
    episodes = []
    for seed in SEEDS:
        spec = dict(layout)
        spec.update(overrides.get(seed, {}))
        episodes.append(
            _episode_row(
                arm_index,
                seed,
                steps=int(spec["steps"]),
                scale=int(spec["scale"]),
                kind=str(spec["kind"]),
            )
        )
    # Take the per-arm identifiers from the frozen pilot protocol; inventing
    # them here would make the fixture something the real pipeline could never
    # produce, which the pilot's own raw validator rejects.
    frozen_arm = next(
        item
        for item in json.loads(PILOT_PROTOCOL_PATH.read_text("utf-8"))["arms"]
        if item["arm_id"] == arm_id
    )
    return {
        "arm_id": arm_id,
        "profile_id": frozen_arm["profile_id"],
        "environment_id": frozen_arm["environment_id"],
        "training_run_id": frozen_arm["training_run_id"],
        "training_terminal_state": "COMPLETED",
        "training_terminal_reason": None,
        "actual_total_timesteps": 122880,
        "evaluation_terminal_state": "COMPLETED",
        "evaluation_terminal_reason": None,
        "expected_evaluation_seeds": list(SEEDS),
        "accessed_evaluation_seeds": list(SEEDS),
        "artifacts": {
            "training_manifest": {
                "state": "PRESENT",
                "path": f"arms/{arm_id}/training_manifest.json",
                "bytes": 1,
                "sha256": "sha256:" + "0" * 64,
                "reason": None,
            },
            "trained_policy": {
                "state": "PRESENT",
                "path": f"arms/{arm_id}/policy.zip",
                "bytes": 1,
                "sha256": "sha256:" + "0" * 64,
                "reason": None,
            },
            "evaluation": {
                "state": "PRESENT",
                "path": f"arms/{arm_id}/evaluation_dev18000_18029.json",
                "bytes": 1,
                "sha256": "sha256:" + "0" * 64,
                "reason": None,
            },
        },
        "episodes": episodes,
    }


def _build_synthetic_pilot_bundle(
    root: Path,
    *,
    plan: dict[str, dict[str, object]] | None = None,
    source_sha: str = SOURCE_SHA,
    bundle_class: str = SYNTHETIC_BUNDLE_CLASS,
) -> Path:
    """Write a schema-exact synthetic v7 pilot bundle and return its root."""
    plan = plan or _default_plan()
    protocol = json.loads(PILOT_PROTOCOL_PATH.read_text("utf-8"))
    protocol_sha = _sha256_file(PILOT_PROTOCOL_PATH)
    claim_boundary = v7_pilot_replay.CLAIM_BOUNDARY
    raw = {
        "schema_version": "V7_PILOT_RAW_EPISODES_V1",
        "protocol_id": "PILOT-V7-ACTION-INTERFACE-DEV-V1",
        "protocol_sha256": protocol_sha,
        "source_git_sha_pre": source_sha,
        "source_git_sha_post": source_sha,
        "source_dirty_pre": False,
        "source_dirty_post": False,
        "run_class": "DEVELOPMENT",
        "data_partition": "DEVELOPMENT",
        "evidence_scope": "SIM_ONLY_MUJOCO",
        "validation_status": "NOT_PHYSICALLY_VALIDATED",
        "expected_arm_count": 3,
        "expected_episodes_per_arm": 30,
        "retained_terminal_states": ["COMPLETED", "FAILED", "CANCELLED"],
        "retained_outcome_states": ["OBSERVED", "NULL", "NONFINITE"],
        "arms": [
            _raw_arm(index, arm_id, plan[arm_id]) for index, arm_id in enumerate(ARM_IDS)
        ],
        "paper_data_ready": False,
        "claim_boundary": claim_boundary,
    }
    summary = v7_pilot_replay.build_summary(protocol, raw)
    root.mkdir(parents=True, exist_ok=True)
    protocol_copy = root / "v7_action_interface_pilot_protocol.json"
    protocol_copy.write_bytes(PILOT_PROTOCOL_PATH.read_bytes())
    _write_json(root / "raw_episodes.json", raw)
    _write_json(root / "pilot_summary.json", summary)
    artifacts = [
        {
            "role": role,
            "path": name,
            "bytes": (root / name).stat().st_size,
            "sha256": _sha256_file(root / name),
        }
        for role, name in (
            ("protocol", "v7_action_interface_pilot_protocol.json"),
            ("pilot_summary", "pilot_summary.json"),
            ("raw_episodes", "raw_episodes.json"),
        )
    ]
    receipt = {
        "schema_version": "V7_PILOT_EVIDENCE_RECEIPT_V1",
        "protocol_id": "PILOT-V7-ACTION-INTERFACE-DEV-V1",
        "protocol_sha256": protocol_sha,
        "validation_status": "PILOT_CONTRACT_VALID",
        "contract_valid": True,
        "evidence_complete": True,
        "audit_source_bundle_class": bundle_class,
        "pilot_planning_ready": summary["pilot_planning_ready"],
        "selection_status": summary["selection_status"],
        "selected_candidate_arm_id": summary["selected_candidate_arm_id"],
        "semantic_blockers": summary["semantic_blockers"],
        "source_git_sha_pre": source_sha,
        "source_git_sha_post": source_sha,
        "source_dirty_pre": False,
        "source_dirty_post": False,
        "artifacts": sorted(artifacts, key=lambda item: item["path"]),
        "method_level_power_ready": False,
        "formal_sample_size_decision": (
            "BLOCKED_INDEPENDENT_TRAINING_SEED_VARIANCE_NOT_ESTIMATED"
        ),
        "paper_data_ready": False,
        "evidence_scope": "SIM_ONLY_MUJOCO",
        "validation_boundary": "NOT_PHYSICALLY_VALIDATED",
        "claim_boundary": claim_boundary,
    }
    _write_json(root / "pilot_receipt.json", receipt)
    return root


@pytest.fixture
def synthetic_bundle(tmp_path: Path) -> dict[str, Path]:
    """A synthetic source bundle plus a sibling, non-existent output root."""
    source = _build_synthetic_pilot_bundle(tmp_path / "source-bundle")
    return {"source": source, "output": tmp_path / "audit-bundle", "root": tmp_path}


def _audit(paths: dict[str, Path]) -> dict[str, object]:
    return audit_v7_exposure_censoring(
        AUDIT_PROTOCOL_PATH, paths["source"], paths["output"]
    )


def _summary(paths: dict[str, Path]) -> dict[str, object]:
    return json.loads((paths["output"] / "audit_summary.json").read_text("utf-8"))


def _rewrite(path: Path, mutate) -> None:
    payload = json.loads(path.read_text("utf-8"))
    mutate(payload)
    _write_json(path, payload)


def _reindex(root: Path) -> None:
    """Recompute the source receipt inventory after a deliberate mutation."""
    def mutate(receipt: dict[str, object]) -> None:
        for record in receipt["artifacts"]:
            target = root / record["path"]
            record["bytes"] = target.stat().st_size
            record["sha256"] = _sha256_file(target)

    _rewrite(root / "pilot_receipt.json", mutate)


def _method_failure_plan() -> dict[str, dict[str, object]]:
    """A whole candidate arm whose evaluation failed before any control step."""
    plan = _default_plan()
    plan["V7C_FILTERED_ACTION"] = {
        "scale": 0,
        "steps": 0,
        "kind": "TERMINAL_FAILURE",
        "overrides": {},
    }
    return plan


def test_audit_reconstructs_exposure_and_retains_a_censoring_blocker(synthetic_bundle):
    receipt = _audit(synthetic_bundle)
    assert receipt["validation_status"] == "AUDIT_CONTRACT_VALID"
    assert receipt["audit_complete"] is True
    assert receipt["audit_status"] == AUDIT_STATUS_BLOCKED
    assert receipt["censoring_blocker_count"] > 0
    assert receipt["source_bundle_read_only_verified"] is True
    assert receipt["paper_data_ready"] is False
    assert receipt["pilot_planning_ready"] is False
    assert [item["criterion_id"] for item in receipt["criteria"]] == [
        f"AX-{index:02d}" for index in range(1, 13)
    ]
    summary = _summary(synthetic_bundle)
    by_id = {arm["arm_id"]: arm for arm in summary["arm_exposure"]}
    assert by_id["V7A_REWARD_ONLY"]["exposure_class_counts"]["FULL_EXPOSURE"] == 30
    assert by_id["V7C_FILTERED_ACTION"]["exposure_class_counts"]["EARLY_TERMINATED"] == 30
    assert by_id["V7C_FILTERED_ACTION"]["comparability_state_counts"]["EXPOSURE_CENSORED"] == 30


def test_termination_step_time_and_phase_are_reconstructed_from_the_retained_trace(
    synthetic_bundle,
):
    _audit(synthetic_bundle)
    summary = _summary(synthetic_bundle)
    by_id = {arm["arm_id"]: arm for arm in summary["arm_exposure"]}
    censored = by_id["V7C_FILTERED_ACTION"]["episodes"][0]
    assert censored["observed_control_steps"] == 60
    assert censored["observed_physics_substeps"] == 600
    assert censored["termination_control_step"] == 59
    assert censored["termination_sim_time_s"] == 1.2
    assert censored["termination_recorder_phase_id"] == "START"
    assert censored["recorded_termination_command_phase"] == "START"
    assert censored["exposure_fraction"] == round(60 / 450, 9)
    full = by_id["V7A_REWARD_ONLY"]["episodes"][0]
    assert full["observed_control_steps"] == 450
    assert full["observed_physics_substeps"] == 4500
    assert full["termination_control_step"] == 449
    assert full["termination_sim_time_s"] == 9.0
    assert full["exposure_fraction"] == 1.0


def test_zero_duty_full_horizon_bound_is_wide_and_the_paired_sign_is_unidentified(
    synthetic_bundle,
):
    _audit(synthetic_bundle)
    summary = _summary(synthetic_bundle)
    by_id = {arm["arm_id"]: arm for arm in summary["arm_exposure"]}
    censored = by_id["V7C_FILTERED_ACTION"]["episodes"][0]
    assert censored["retained_saturation_duty_pct"]["value"] == 0.0
    bound = censored["full_horizon_duty_bound_pct"]
    # 60 of 450 control steps observed with zero saturated substeps: the
    # full-horizon duty is bounded by [0, (4500 - 600) / 4500].
    assert bound["lower_pct"] == 0.0
    assert bound["upper_pct"] == round(100.0 * 3900 / 4500, 6)
    assert bound["width_pct"] == bound["upper_pct"]
    contrast = next(
        item
        for item in summary["paired_comparability"]
        if item["candidate_arm_id"] == "V7C_FILTERED_ACTION"
    )
    assert contrast["validity_verdict"] == "PAIRED_CONTRAST_NON_COMPARABLE_EXPOSURE_CENSORED"
    assert contrast["comparable_pair_count"] == 0
    assert contrast["paired_identification_bound_pct"]["sign_identified_pair_count"] == 0
    for pair in contrast["pairs"]:
        paired_bound = pair["paired_identification_bound_pct"]
        assert paired_bound["lower_pct"] < 0.0 < paired_bound["upper_pct"]
        assert paired_bound["sign_identified"] is False
        assert paired_bound["sign"] is None
        assert pair["retained_arithmetic_difference_pct"]["valid_contrast"] is False


def test_full_exposure_identification_bound_collapses_onto_the_recorded_value(
    synthetic_bundle,
):
    _audit(synthetic_bundle)
    summary = _summary(synthetic_bundle)
    reference = next(
        arm for arm in summary["arm_exposure"] if arm["arm_id"] == "V7A_REWARD_ONLY"
    )
    for episode in reference["episodes"]:
        bound = episode["full_horizon_duty_bound_pct"]
        assert episode["exposure_class"] == "FULL_EXPOSURE"
        assert bound["lower_pct"] == bound["upper_pct"]
        assert bound["width_pct"] == 0.0
        assert bound["lower_pct"] == episode["recomputed_truncated_duty_pct"]
    aggregate = reference["full_horizon_duty_bound_pct"]
    assert aggregate["state"] == "OBSERVED"
    assert aggregate["mean_lower_pct"] == aggregate["mean_upper_pct"]


def test_early_termination_with_every_required_outcome_observed_is_still_censored(
    synthetic_bundle,
):
    _audit(synthetic_bundle)
    summary = _summary(synthetic_bundle)
    candidate = next(
        arm
        for arm in summary["arm_exposure"]
        if arm["arm_id"] == "V7B_REDUCED_JOINT_ENVELOPE"
    )
    episode = next(item for item in candidate["episodes"] if item["evaluation_seed"] == 18011)
    assert episode["observed_control_steps"] == 430
    assert episode["outcome_state"] == "OBSERVED"
    assert episode["retained_saturation_duty_pct"]["state"] == "OBSERVED"
    assert episode["exposure_class"] == "EARLY_TERMINATED"
    assert episode["comparability_state"] == "EXPOSURE_CENSORED"
    assert episode["comparability_reason"] == "EARLY_TERMINATION_EXPOSURE_CENSORED"
    assert episode["full_horizon_duty_bound_pct"]["width_pct"] > 0.0


def test_paired_aggregate_is_blocked_without_complete_case_deletion(synthetic_bundle):
    _audit(synthetic_bundle)
    summary = _summary(synthetic_bundle)
    contrast = next(
        item
        for item in summary["paired_comparability"]
        if item["candidate_arm_id"] == "V7B_REDUCED_JOINT_ENVELOPE"
    )
    assert contrast["comparable_pair_count"] == 28
    assert contrast["exposure_censored_pair_count"] == 2
    aggregate = contrast["audited_paired_difference_pct"]
    assert aggregate["state"] == "NULL"
    assert aggregate["mean_difference"] is None
    assert aggregate["reason"] == (
        "BLOCKED_EXPOSURE_CENSORED_PAIRS_RETAINED_NO_COMPLETE_CASE_DELETION"
    )
    # Nothing is deleted: all 30 pairs stay in the retained record.
    assert len(contrast["pairs"]) == 30
    assert contrast["pilot_reported_paired_difference_pct"]["retention"] == (
        "RETAINED_VERBATIM_FROM_FROZEN_PILOT_SUMMARY_NOT_RECOMPUTED"
    )


def test_method_failure_is_retained_and_is_not_reported_as_censoring(tmp_path):
    source = _build_synthetic_pilot_bundle(
        tmp_path / "source-bundle", plan=_method_failure_plan()
    )
    paths = {"source": source, "output": tmp_path / "audit-bundle"}
    _audit(paths)
    summary = _summary(paths)
    failed = next(
        arm for arm in summary["arm_exposure"] if arm["arm_id"] == "V7C_FILTERED_ACTION"
    )
    assert failed["exposure_class_counts"]["NO_EXPOSURE"] == 30
    assert failed["comparability_state_counts"]["METHOD_FAILURE_NOT_CENSORING"] == 30
    assert failed["comparability_state_counts"]["EXPOSURE_CENSORED"] == 0
    assert failed["termination_recorder_phase_counts"]["NO_EXPOSURE"] == 30
    assert failed["full_horizon_duty_bound_pct"]["state"] == "NULL"
    for episode in failed["episodes"]:
        assert episode["terminal_record_state"] == "FAILED"
        assert episode["full_horizon_duty_bound_pct"]["state"] == "NULL"
        assert episode["comparability_reason"] == (
            "NO_EXPOSURE_TERMINAL_FAILURE_METHOD_FAILURE"
        )
    contrast = next(
        item
        for item in summary["paired_comparability"]
        if item["candidate_arm_id"] == "V7C_FILTERED_ACTION"
    )
    assert contrast["method_failure_pair_count"] == 30
    assert contrast["exposure_censored_pair_count"] == 0
    assert contrast["paired_identification_bound_pct"]["state"] == "NULL"
    assert summary["audit_findings"]["method_failure_doctrine"] == (
        "METHOD_FAILURE_IS_RETAINED_AND_IS_NOT_TREATED_AS_CENSORING"
    )


def test_exposure_matched_sensitivity_is_descriptive_only(synthetic_bundle):
    _audit(synthetic_bundle)
    summary = _summary(synthetic_bundle)
    for block in summary["exposure_matched_sensitivity"]:
        assert block["status"] == "DESCRIPTIVE_ONLY"
        assert block["informative_censoring"] == "SUSPECTED_DEPENDENT_ON_ARM_BEHAVIOUR"
        assert "candidate_selection" in block["prohibited_uses"]
        assert "confidence_interval" in block["prohibited_uses"]
        assert len(block["pairs"]) == 30
    censored = next(
        block
        for block in summary["exposure_matched_sensitivity"]
        if block["candidate_arm_id"] == "V7C_FILTERED_ACTION"
    )
    for pair in censored["pairs"]:
        assert pair["matched_exposure_control_steps"] == 60
        assert pair["candidate_matched_duty_pct"] == 0.0
        assert pair["reference_matched_duty_pct"] > 0.0


def test_phase_convention_offset_is_retained_as_a_validity_finding(synthetic_bundle):
    _audit(synthetic_bundle)
    summary = _summary(synthetic_bundle)
    convention = summary["phase_convention"]
    assert convention["contract_convention"] == "START_OF_CONTROL_STEP_EXACT"
    assert convention["recorder_convention"] == "END_OF_CONTROL_STEP_ACCUMULATED_SIM_TIME"
    assert convention["conventions_agree"] is False
    assert convention["disagreeing_phase_ids"] == [
        "INITIAL_STAND",
        "START",
        "STEADY_WALK",
    ]
    assert convention["finding"] == (
        "RECORDED_PHASE_LABEL_FOLLOWS_END_OF_STEP_ACCUMULATED_TIME_AND_IS_OFFSET_"
        "FROM_THE_CONTRACT_START_OF_STEP_SCHEDULE"
    )
    contract_phases = {item["phase_id"]: item for item in summary["contract_phase_schedule"]}
    recorder_phases = {item["phase_id"]: item for item in summary["recorder_phase_schedule"]}
    assert contract_phases["START"]["first_control_step"] == 50
    assert recorder_phases["START"]["first_control_step"] == 49
    assert sum(item["control_steps"] for item in summary["recorder_phase_schedule"]) == 450


def test_original_pilot_receipt_and_null_selection_are_preserved(synthetic_bundle):
    source_receipt = synthetic_bundle["source"] / "pilot_receipt.json"
    before = _sha256_file(source_receipt)
    receipt = _audit(synthetic_bundle)
    assert _sha256_file(source_receipt) == before
    preserved = receipt["preserved_pilot_selection"]
    assert preserved["pilot_receipt_sha256"] == before
    assert preserved["selected_candidate_arm_id"] is None
    assert preserved["audit_modified_pilot_conclusions"] is False


def test_audit_leaves_every_source_artifact_byte_identical(synthetic_bundle):
    source = synthetic_bundle["source"]
    before = {
        path.relative_to(source).as_posix(): (path.stat().st_size, _sha256_file(path))
        for path in sorted(source.rglob("*"))
        if path.is_file()
    }
    _audit(synthetic_bundle)
    after = {
        path.relative_to(source).as_posix(): (path.stat().st_size, _sha256_file(path))
        for path in sorted(source.rglob("*"))
        if path.is_file()
    }
    assert after == before


def test_stdlib_only_replay_reconstructs_the_audit_summary_exactly(synthetic_bundle):
    _audit(synthetic_bundle)
    source = synthetic_bundle["source"]
    output = synthetic_bundle["output"]
    completed = subprocess.run(
        [
            sys.executable,
            "-I",
            "-S",
            str(REPLAY_SCRIPT),
            str(output / "v7_exposure_audit_protocol.json"),
            str(source / "pilot_receipt.json"),
            str(source / "raw_episodes.json"),
            str(source / "pilot_summary.json"),
            str(output / "audit_summary.json"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0
    assert completed.stderr == ""
    receipt = json.loads(completed.stdout)
    assert receipt["schema_version"] == "V7_EXPOSURE_AUDIT_REPLAY_RECEIPT_V1"
    assert receipt["status"] == "PASS"
    assert receipt["exact_identity"] is True
    assert receipt["source_bundle_class"] == SYNTHETIC_BUNDLE_CLASS
    assert receipt["audit_applies_to_frozen_v7_pilot"] is False
    assert receipt["checks"] and all(value is True for value in receipt["checks"].values())
    assert "exposure_and_censoring_exact" in receipt["checks"]
    assert "recorder_phase_convention_exact" in receipt["checks"]


def test_replay_and_contract_import_only_the_standard_library():
    for script in (REPLAY_SCRIPT, Path(audit_module.__file__)):
        tree = ast.parse(script.read_text("utf-8"))
        roots: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    raise AssertionError(f"{script.name} uses a relative import")
                roots.add((node.module or "").split(".")[0])
        allowed = STDLIB_IMPORTS | {"argparse", "os", "subprocess"}
        assert roots <= allowed, sorted(roots - allowed)


def test_replay_mismatch_after_summary_tampering_fails_closed(synthetic_bundle):
    _audit(synthetic_bundle)
    summary_path = synthetic_bundle["output"] / "audit_summary.json"
    _rewrite(
        summary_path,
        lambda payload: payload["arm_exposure"][2]["episodes"][0].__setitem__(
            "comparability_state", "COMPARABLE"
        ),
    )
    completed = subprocess.run(
        [
            sys.executable,
            "-I",
            "-S",
            str(REPLAY_SCRIPT),
            str(synthetic_bundle["output"] / "v7_exposure_audit_protocol.json"),
            str(synthetic_bundle["source"] / "pilot_receipt.json"),
            str(synthetic_bundle["source"] / "raw_episodes.json"),
            str(synthetic_bundle["source"] / "pilot_summary.json"),
            str(summary_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 2
    receipt = json.loads(completed.stdout)
    assert receipt["status"] == "ERROR"
    assert receipt["exact_identity"] is False
    assert "arm_exposure" in receipt["error"]


def test_builder_invokes_exactly_one_isolated_stdlib_replay(synthetic_bundle, monkeypatch):
    commands: list[list[str]] = []
    original_run = audit_module.subprocess.run

    def capture(command, *args, **kwargs):
        commands.append(list(command))
        return original_run(command, *args, **kwargs)

    monkeypatch.setattr(audit_module.subprocess, "run", capture)
    _audit(synthetic_bundle)
    assert len(commands) == 1
    command = commands[0]
    assert command[0] == sys.executable
    assert command[1:3] == ["-I", "-S"]
    assert Path(command[3]).name == "v7_exposure_audit_replay.py"
    assert len(command) == 9


def test_output_root_inside_the_audited_bundle_fails_closed(synthetic_bundle):
    with pytest.raises(V7ExposureAuditError, match="inside or equal to the audited bundle"):
        audit_v7_exposure_censoring(
            AUDIT_PROTOCOL_PATH,
            synthetic_bundle["source"],
            synthetic_bundle["source"] / "audit-output",
        )


def test_audited_bundle_inside_the_output_root_fails_closed(tmp_path):
    output = tmp_path / "audit"
    source = _build_synthetic_pilot_bundle(output / "source-bundle")
    with pytest.raises(V7ExposureAuditError, match="must not be inside the audit output"):
        audit_v7_exposure_censoring(AUDIT_PROTOCOL_PATH, source, output)


def test_non_empty_output_root_fails_closed(synthetic_bundle):
    synthetic_bundle["output"].mkdir(parents=True)
    (synthetic_bundle["output"] / "stale.json").write_text("{}", encoding="utf-8")
    with pytest.raises(V7ExposureAuditError, match="must not exist or must be empty"):
        _audit(synthetic_bundle)


def test_audited_artifact_bytes_mismatch_fails_closed(synthetic_bundle):
    _rewrite(
        synthetic_bundle["source"] / "pilot_receipt.json",
        lambda payload: payload["artifacts"][0].__setitem__(
            "bytes", payload["artifacts"][0]["bytes"] + 1
        ),
    )
    with pytest.raises(V7ExposureAuditError, match="bytes/SHA-256 mismatch"):
        _audit(synthetic_bundle)


def test_audited_artifact_sha256_mismatch_fails_closed(synthetic_bundle):
    _rewrite(
        synthetic_bundle["source"] / "pilot_receipt.json",
        lambda payload: payload["artifacts"][0].__setitem__(
            "sha256", "sha256:" + "0" * 64
        ),
    )
    with pytest.raises(V7ExposureAuditError, match="bytes/SHA-256 mismatch"):
        _audit(synthetic_bundle)


def test_unindexed_file_in_the_audited_bundle_fails_closed(synthetic_bundle):
    (synthetic_bundle["source"] / "extra_notes.json").write_text("{}", encoding="utf-8")
    with pytest.raises(V7ExposureAuditError, match="unindexed"):
        _audit(synthetic_bundle)


def test_path_escape_in_the_audited_inventory_fails_closed(synthetic_bundle):
    _rewrite(
        synthetic_bundle["source"] / "pilot_receipt.json",
        lambda payload: payload["artifacts"][0].__setitem__("path", "../escape.json"),
    )
    with pytest.raises(V7ExposureAuditError, match="safe relative path"):
        _audit(synthetic_bundle)


def test_duplicate_json_key_in_raw_episodes_fails_closed(synthetic_bundle):
    raw_path = synthetic_bundle["source"] / "raw_episodes.json"
    text = raw_path.read_text("utf-8")
    literal = '"protocol_id": "PILOT-V7-ACTION-INTERFACE-DEV-V1",'
    assert literal in text
    raw_path.write_text(text.replace(literal, literal + "\n  " + literal, 1), encoding="utf-8")
    _reindex(synthetic_bundle["source"])
    with pytest.raises(V7ExposureAuditError, match="duplicate JSON key"):
        _audit(synthetic_bundle)


def test_non_finite_json_number_in_raw_episodes_fails_closed(synthetic_bundle):
    raw_path = synthetic_bundle["source"] / "raw_episodes.json"
    text = raw_path.read_text("utf-8")
    literal = '"applied_action_delta_l2": 0.0'
    assert literal in text
    raw_path.write_text(
        text.replace(literal, '"applied_action_delta_l2": NaN', 1), encoding="utf-8"
    )
    _reindex(synthetic_bundle["source"])
    with pytest.raises(V7ExposureAuditError, match="non-finite constant is forbidden"):
        _audit(synthetic_bundle)


def test_json_overflow_number_in_raw_episodes_fails_closed(synthetic_bundle):
    raw_path = synthetic_bundle["source"] / "raw_episodes.json"
    text = raw_path.read_text("utf-8")
    literal = '"applied_action_delta_l2": 0.0'
    assert literal in text
    raw_path.write_text(
        text.replace(literal, '"applied_action_delta_l2": 1e400', 1), encoding="utf-8"
    )
    _reindex(synthetic_bundle["source"])
    with pytest.raises(V7ExposureAuditError, match="non-finite number is forbidden"):
        _audit(synthetic_bundle)


def test_sealed_formal_seed_access_fails_closed(synthetic_bundle):
    def mutate(payload):
        payload["arms"][0]["episodes"][0]["evaluation_seed"] = 20000

    _rewrite(synthetic_bundle["source"] / "raw_episodes.json", mutate)
    _reindex(synthetic_bundle["source"])
    with pytest.raises(V7ExposureAuditError, match="sealed FORMAL/HOLDOUT seed"):
        _audit(synthetic_bundle)


def test_retired_seed_access_fails_closed(synthetic_bundle):
    def mutate(payload):
        payload["arms"][0]["episodes"][0]["evaluation_seed"] = 19000

    _rewrite(synthetic_bundle["source"] / "raw_episodes.json", mutate)
    _reindex(synthetic_bundle["source"])
    with pytest.raises(V7ExposureAuditError, match="retired seed"):
        _audit(synthetic_bundle)


def test_over_exposure_beyond_the_frozen_horizon_fails_closed(synthetic_bundle):
    def mutate(payload):
        trace = payload["arms"][0]["episodes"][0]["control_step_trace"]
        extra = deepcopy(trace[-1])
        extra["control_step"] = len(trace)
        trace.append(extra)

    _rewrite(synthetic_bundle["source"] / "raw_episodes.json", mutate)
    _reindex(synthetic_bundle["source"])
    with pytest.raises(V7ExposureAuditError, match="OVER_EXPOSURE"):
        _audit(synthetic_bundle)


def test_per_control_step_substep_total_must_be_exactly_ten(synthetic_bundle):
    def mutate(payload):
        payload["arms"][0]["episodes"][0]["control_step_trace"][0][
            "saturation_substeps_total"
        ] = 9

    _rewrite(synthetic_bundle["source"] / "raw_episodes.json", mutate)
    _reindex(synthetic_bundle["source"])
    with pytest.raises(V7ExposureAuditError, match=r"integer in \[10, 10\]"):
        _audit(synthetic_bundle)


def test_recorded_command_phase_drift_fails_closed(synthetic_bundle):
    def mutate(payload):
        payload["arms"][0]["episodes"][0]["control_step_trace"][0][
            "command_phase"
        ] = "STEADY_WALK"

    _rewrite(synthetic_bundle["source"] / "raw_episodes.json", mutate)
    _reindex(synthetic_bundle["source"])
    with pytest.raises(V7ExposureAuditError, match="reproduced recorder convention"):
        _audit(synthetic_bundle)


def test_trace_receipt_count_drift_fails_closed(synthetic_bundle):
    def mutate(payload):
        payload["arms"][0]["episodes"][0]["trace_receipt"]["control_step_count"] = 449

    _rewrite(synthetic_bundle["source"] / "raw_episodes.json", mutate)
    _reindex(synthetic_bundle["source"])
    with pytest.raises(V7ExposureAuditError, match="control_step_count"):
        _audit(synthetic_bundle)


def test_non_null_pilot_selection_is_refused(synthetic_bundle):
    _rewrite(
        synthetic_bundle["source"] / "pilot_summary.json",
        lambda payload: payload.__setitem__(
            "selected_candidate_arm_id", "V7B_REDUCED_JOINT_ENVELOPE"
        ),
    )
    _reindex(synthetic_bundle["source"])
    with pytest.raises(V7ExposureAuditError, match="selected a candidate"):
        _audit(synthetic_bundle)


def test_synthetic_bundle_cannot_declare_itself_the_frozen_pilot(tmp_path):
    source = _build_synthetic_pilot_bundle(
        tmp_path / "source-bundle", bundle_class=DEVELOPMENT_BUNDLE_CLASS
    )
    assert _sha256_file(source / "pilot_receipt.json") != FROZEN_PILOT_RECEIPT_SHA256
    with pytest.raises(V7ExposureAuditError, match="class binding disagrees"):
        audit_v7_exposure_censoring(AUDIT_PROTOCOL_PATH, source, tmp_path / "audit-bundle")


def test_audit_protocol_hash_drift_fails_closed(synthetic_bundle, tmp_path):
    forged = tmp_path / "forged" / "v7_exposure_audit_protocol.json"
    forged.parent.mkdir(parents=True)
    payload = json.loads(AUDIT_PROTOCOL_PATH.read_text("utf-8"))
    payload["frozen_task_horizon"]["duration_s"] = 8.0
    _write_json(forged, payload)
    with pytest.raises(V7ExposureAuditError, match="protocol SHA-256 mismatch"):
        audit_v7_exposure_censoring(
            forged, synthetic_bundle["source"], synthetic_bundle["output"]
        )


def test_frozen_horizon_must_be_integral():
    contract = {
        "task_id": "t",
        "motion_task_source": "backend/motion_tasks.py",
        "motion_task_source_sha256": "sha256:" + "0" * 64,
        "duration_s": 9.0,
        "physics_rate_hz": 500.0,
        "control_rate_hz": 33.0,
    }
    protocol = {"frozen_task_horizon": contract}
    with pytest.raises(V7ExposureAuditError, match="exact integer"):
        audit_module._exposure_contract(protocol)


def test_frozen_source_hash_drift_fails_closed():
    with pytest.raises(V7ExposureAuditError, match="motion task source SHA-256 drifted"):
        audit_module._verify_motion_task_source({
            "motion_task_source": "backend/motion_tasks.py",
            "motion_task_source_sha256": "sha256:" + "0" * 64,
        })
    with pytest.raises(V7ExposureAuditError, match="recorder source SHA-256 drifted"):
        audit_module._verify_recorder_source({
            "phase_convention": {
                "recorder_source": "backend/rl/humanoid_env.py",
                "recorder_source_sha256": "sha256:" + "0" * 64,
            }
        })


def test_validate_rejects_a_tampered_audit_summary(synthetic_bundle):
    receipt_path = synthetic_bundle["output"] / "audit_receipt.json"
    _audit(synthetic_bundle)
    _rewrite(
        synthetic_bundle["output"] / "audit_summary.json",
        lambda payload: payload.__setitem__("censoring_blocker_count", 0),
    )
    with pytest.raises(V7ExposureAuditError, match="bytes/SHA-256 mismatch"):
        validate_v7_exposure_audit_bundle(receipt_path)


def test_cli_exit_codes_distinguish_censoring_blocker_and_structural_failure(
    synthetic_bundle, tmp_path
):
    completed = subprocess.run(
        [
            sys.executable,
            "-I",
            "-S",
            str(Path(audit_module.__file__)),
            "audit",
            str(synthetic_bundle["source"]),
            str(synthetic_bundle["output"]),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 1
    payload = json.loads(completed.stdout)
    assert payload["audit_status"] == AUDIT_STATUS_BLOCKED
    assert payload["paper_data_ready"] is False

    validated = subprocess.run(
        [
            sys.executable,
            "-I",
            "-S",
            str(Path(audit_module.__file__)),
            "validate",
            str(synthetic_bundle["output"] / "audit_receipt.json"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert validated.returncode == 1
    assert json.loads(validated.stdout)["validation_status"] == "AUDIT_BUNDLE_VALID"

    broken = subprocess.run(
        [
            sys.executable,
            "-I",
            "-S",
            str(Path(audit_module.__file__)),
            "audit",
            str(tmp_path / "missing-bundle"),
            str(tmp_path / "other-output"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert broken.returncode == 2
    failure = json.loads(broken.stdout)
    assert failure["validation_status"] == "STRUCTURAL_FAILURE"
    assert failure["contract_valid"] is False


def _raw_from_plan(plan: dict[str, dict[str, object]], source_sha: str = SOURCE_SHA) -> dict[str, object]:
    """Build a canonical raw payload without writing a bundle to disk."""
    return {
        "schema_version": "V7_PILOT_RAW_EPISODES_V1",
        "protocol_id": "PILOT-V7-ACTION-INTERFACE-DEV-V1",
        "protocol_sha256": _sha256_file(PILOT_PROTOCOL_PATH),
        "source_git_sha_pre": source_sha,
        "source_git_sha_post": source_sha,
        "source_dirty_pre": False,
        "source_dirty_post": False,
        "run_class": "DEVELOPMENT",
        "data_partition": "DEVELOPMENT",
        "evidence_scope": "SIM_ONLY_MUJOCO",
        "validation_status": "NOT_PHYSICALLY_VALIDATED",
        "expected_arm_count": 3,
        "expected_episodes_per_arm": 30,
        "retained_terminal_states": ["COMPLETED", "FAILED", "CANCELLED"],
        "retained_outcome_states": ["OBSERVED", "NULL", "NONFINITE"],
        "arms": [_raw_arm(index, arm_id, plan[arm_id]) for index, arm_id in enumerate(ARM_IDS)],
        "paper_data_ready": False,
        "claim_boundary": v7_pilot_replay.CLAIM_BOUNDARY,
    }


def _arm_layout(scale: int, steps: int, kind: str, overrides=None) -> dict[str, object]:
    return {"scale": scale, "steps": steps, "kind": kind, "overrides": overrides or {}}


def _force_nonfinite_primary(raw: dict[str, object]) -> None:
    row = raw["arms"][2]["episodes"][0]
    reason = "SOURCE_EVALUATOR_REPORTED_NAN"
    row["outcome_state"] = "NONFINITE"
    row["reason"] = reason
    for measurement_id in ("saturation_duty_pct", "steady_speed_mps"):
        row["measurements"][measurement_id] = {
            "state": "NONFINITE",
            "value": None,
            "reason": reason,
        }
    row["trace_receipt"]["reported_saturation_duty_pct"] = None
    row["trace_receipt"]["reported_absolute_delta"] = None
    row["gates"] = v7_pilot_replay._gate_results(row["measurements"])


# Step counts chosen to straddle every boundary at which the contract
# start-of-step schedule and the reproduced recorder convention disagree.
DIFFERENTIAL_CASES = (
    ("phase_boundary_49", {"steps": 49, "kind": "EARLY_NULL", "scale": 5}, None),
    ("phase_boundary_124", {"steps": 124, "kind": "EARLY_NULL", "scale": 11}, None),
    ("phase_boundary_325", {"steps": 325, "kind": "EARLY_NULL", "scale": 1}, None),
    ("final_stand_430", {"steps": 430, "kind": "FULL", "scale": 8}, None),
    ("zero_saturation_60", {"steps": 60, "kind": "EARLY_NULL", "scale": 0}, None),
    ("nonfinite_primary", {"steps": 450, "kind": "FULL", "scale": 5}, _force_nonfinite_primary),
)


@pytest.mark.parametrize("label,layout,mutate", DIFFERENTIAL_CASES, ids=[c[0] for c in DIFFERENTIAL_CASES])
def test_contract_and_replay_builders_agree_exactly(label, layout, mutate):
    """The two independent builders must agree, or refuse the same input."""
    plan = {
        "V7A_REWARD_ONLY": _arm_layout(8, FULL_STEPS, "FULL"),
        "V7B_REDUCED_JOINT_ENVELOPE": _arm_layout(
            int(layout["scale"]), int(layout["steps"]), str(layout["kind"])
        ),
        "V7C_FILTERED_ACTION": _arm_layout(
            int(layout["scale"]), int(layout["steps"]), str(layout["kind"])
        ),
    }
    raw = _raw_from_plan(plan)
    if mutate is not None:
        mutate(raw)
    pilot_summary = v7_pilot_replay.build_summary(
        json.loads(PILOT_PROTOCOL_PATH.read_text("utf-8")), raw
    )
    protocol = audit_module.load_audit_protocol(AUDIT_PROTOCOL_PATH)
    kwargs = {
        "source_bundle_class": SYNTHETIC_BUNDLE_CLASS,
        "pilot_receipt_sha256": "sha256:" + "b" * 64,
    }

    def build(module):
        try:
            return ("OK", module.build_audit_summary(protocol, raw, pilot_summary, **kwargs))
        except Exception as exc:  # noqa: BLE001 - both modules raise their own type
            return ("REFUSED", type(exc).__name__)

    contract_state, contract_value = build(audit_module)
    replay_state, replay_value = build(v7_exposure_audit_replay)
    assert contract_state == replay_state, (
        f"{label}: one builder refused and the other accepted "
        f"({contract_state} vs {replay_state})"
    )
    if contract_state == "OK":
        assert contract_value == replay_value, (
            f"{label}: builders disagree on "
            f"{sorted(k for k in set(contract_value) | set(replay_value) if contract_value.get(k) != replay_value.get(k))}"
        )


def test_mixed_comparability_within_one_arm_is_retained_per_episode():
    plan = {
        "V7A_REWARD_ONLY": _arm_layout(8, FULL_STEPS, "FULL"),
        "V7B_REDUCED_JOINT_ENVELOPE": _arm_layout(
            5,
            FULL_STEPS,
            "FULL",
            {
                18000: {"steps": 60, "kind": "EARLY_NULL"},
                18001: {"steps": 449, "kind": "FULL"},
            },
        ),
        "V7C_FILTERED_ACTION": _arm_layout(0, 60, "EARLY_NULL"),
    }
    raw = _raw_from_plan(plan)
    pilot_summary = v7_pilot_replay.build_summary(
        json.loads(PILOT_PROTOCOL_PATH.read_text("utf-8")), raw
    )
    summary = audit_module.build_audit_summary(
        audit_module.load_audit_protocol(AUDIT_PROTOCOL_PATH),
        raw,
        pilot_summary,
        source_bundle_class=SYNTHETIC_BUNDLE_CLASS,
        pilot_receipt_sha256="sha256:" + "b" * 64,
    )
    candidate = next(
        arm for arm in summary["arm_exposure"] if arm["arm_id"] == "V7B_REDUCED_JOINT_ENVELOPE"
    )
    assert candidate["comparability_state_counts"] == {
        "COMPARABLE": 28,
        "EXPOSURE_CENSORED": 2,
        "METHOD_FAILURE_NOT_CENSORING": 0,
    }
    # A 449-step episode reports every required numeric yet is still censored.
    near_full = next(item for item in candidate["episodes"] if item["evaluation_seed"] == 18001)
    assert near_full["observed_control_steps"] == 449
    assert near_full["outcome_state"] == "OBSERVED"
    assert near_full["comparability_state"] == "EXPOSURE_CENSORED"
    assert near_full["full_horizon_duty_bound_pct"]["width_pct"] == round(100.0 * 10 / 4500, 6)


def _all_comparable_plan() -> dict[str, dict[str, object]]:
    """Every episode fully exposed; the pilot still selects nothing.

    Each arm's saturation duty exceeds the frozen 30 percent gate, so no
    candidate is eligible and the pilot selection stays null, while every
    episode remains comparable. This is the only route to a zero-blocker audit.
    """
    return {arm_id: _arm_layout(8, FULL_STEPS, "FULL") for arm_id in ARM_IDS}


def test_zero_blocker_audit_reports_clean_status_and_observed_aggregates(tmp_path):
    source = _build_synthetic_pilot_bundle(
        tmp_path / "source-bundle", plan=_all_comparable_plan()
    )
    paths = {"source": source, "output": tmp_path / "audit-bundle"}
    receipt = _audit(paths)
    assert receipt["audit_status"] == "AUDIT_COMPLETE_NO_CENSORING_BLOCKER"
    assert receipt["censoring_blocker_count"] == 0
    summary = _summary(paths)
    assert summary["censoring_blockers"] == []
    assert summary["audit_findings"]["zero_duty_interpretation"] == (
        "NOT_APPLICABLE_ALL_ARMS_HAVE_COMPARABLE_EPISODES"
    )
    assert summary["audit_findings"]["non_comparable_arm_causes"] == {}
    assert summary["audit_findings"]["arms_without_any_comparable_episode"] == []
    for arm in summary["arm_exposure"]:
        assert arm["comparability_state_counts"]["COMPARABLE"] == 30
        assert arm["full_horizon_duty_bound_pct"]["state"] == "OBSERVED"
    for block in summary["paired_comparability"]:
        assert block["validity_verdict"] == "PAIRED_CONTRAST_COMPARABLE"
        aggregate = block["audited_paired_difference_pct"]
        assert aggregate["state"] == "OBSERVED"
        assert aggregate["n_observed"] == 30
        assert aggregate["mean_difference"] is not None
        assert aggregate["reason"] is None
        bound = block["paired_identification_bound_pct"]
        assert bound["state"] == "OBSERVED"
        assert bound["sign_identified_is_complete_case"] is True
    # At full exposure every pair is matched over the whole horizon, so the
    # descriptive matched difference must equal the audited paired difference.
    for block, sensitivity in zip(
        summary["paired_comparability"], summary["exposure_matched_sensitivity"], strict=True
    ):
        assert sensitivity["candidate_arm_id"] == block["candidate_arm_id"]
        assert all(p["matched_exposure_control_steps"] == FULL_STEPS for p in sensitivity["pairs"])
        assert (
            sensitivity["matched_difference_pct"]["mean_difference"]
            == block["audited_paired_difference_pct"]["mean_difference"]
        )


def test_clean_audit_returns_cli_exit_zero(tmp_path):
    source = _build_synthetic_pilot_bundle(
        tmp_path / "source-bundle", plan=_all_comparable_plan()
    )
    output = tmp_path / "audit-bundle"
    completed = subprocess.run(
        [
            sys.executable, "-I", "-S", str(Path(audit_module.__file__)),
            "audit", str(source), str(output),
        ],
        capture_output=True, text=True, check=False,
    )
    assert completed.returncode == 0
    assert json.loads(completed.stdout)["audit_status"] == (
        "AUDIT_COMPLETE_NO_CENSORING_BLOCKER"
    )


def test_partial_exposure_with_unobserved_primary_is_method_failure_not_censoring(tmp_path):
    plan = _default_plan()
    plan["V7B_REDUCED_JOINT_ENVELOPE"]["overrides"] = {
        18007: {"steps": 200, "kind": "EARLY_METHOD_FAILURE"},
    }
    source = _build_synthetic_pilot_bundle(tmp_path / "source-bundle", plan=plan)
    paths = {"source": source, "output": tmp_path / "audit-bundle"}
    _audit(paths)
    summary = _summary(paths)
    arm = next(
        item for item in summary["arm_exposure"]
        if item["arm_id"] == "V7B_REDUCED_JOINT_ENVELOPE"
    )
    episode = next(item for item in arm["episodes"] if item["evaluation_seed"] == 18007)
    # Partial exposure, so not NO_EXPOSURE, yet still a retained method failure.
    assert episode["observed_control_steps"] == 200
    assert episode["exposure_class"] == "EARLY_TERMINATED"
    assert episode["comparability_state"] == "METHOD_FAILURE_NOT_CENSORING"
    assert episode["comparability_reason"] == (
        "REQUIRED_PRIMARY_OUTCOME_NOT_OBSERVED_METHOD_FAILURE"
    )
    assert episode["full_horizon_duty_bound_pct"]["state"] == "NULL"
    # The descriptive sensitivity must not re-materialize it as observed.
    sensitivity = next(
        item for item in summary["exposure_matched_sensitivity"]
        if item["candidate_arm_id"] == "V7B_REDUCED_JOINT_ENVELOPE"
    )
    pair = next(item for item in sensitivity["pairs"] if item["evaluation_seed"] == 18007)
    assert pair["matched_exposure_control_steps"] == 200
    assert pair["state"] == "NULL"
    assert pair["candidate_matched_duty_pct"] is None
    assert pair["reason"] == "REQUIRED_PRIMARY_OUTCOME_NOT_OBSERVED_METHOD_FAILURE"


def test_method_failure_only_contrast_is_not_labelled_exposure_censored(tmp_path):
    source = _build_synthetic_pilot_bundle(
        tmp_path / "source-bundle", plan=_method_failure_plan()
    )
    paths = {"source": source, "output": tmp_path / "audit-bundle"}
    _audit(paths)
    summary = _summary(paths)
    block = next(
        item for item in summary["paired_comparability"]
        if item["candidate_arm_id"] == "V7C_FILTERED_ACTION"
    )
    assert block["method_failure_pair_count"] == 30
    assert block["exposure_censored_pair_count"] == 0
    assert block["validity_verdict"] == "PAIRED_CONTRAST_NON_COMPARABLE_METHOD_FAILURE"
    assert block["audited_paired_difference_pct"]["reason"] == (
        "BLOCKED_METHOD_FAILURE_RETAINED_NO_COMPLETE_CASE_DELETION"
    )
    arm = next(
        item for item in summary["arm_exposure"]
        if item["arm_id"] == "V7C_FILTERED_ACTION"
    )
    assert arm["full_horizon_duty_bound_pct"]["reason"] == (
        "BLOCKED_METHOD_FAILURE_RETAINED_NO_COMPLETE_CASE_DELETION"
    )
    assert summary["audit_findings"]["zero_duty_interpretation"] == (
        "NON_COMPARABLE_RETAINED_METHOD_FAILURE"
    )
    assert summary["audit_findings"]["non_comparable_arm_causes"] == {
        "V7C_FILTERED_ACTION": "METHOD_FAILURE_NOT_CENSORING"
    }
    # Blocker identifiers must name the arm and the state, with no doubled prefix.
    assert f"V7C_FILTERED_ACTION:PAIRED_CONTRAST_NON_COMPARABLE_METHOD_FAILURE" in (
        summary["censoring_blockers"]
    )
    assert not any("PAIRED_CONTRAST_PAIRED_CONTRAST" in b for b in summary["censoring_blockers"])
    assert summary["censoring_blocker_count"] == len(summary["censoring_blockers"])


def test_censoring_blocker_identifiers_are_exact(synthetic_bundle):
    _audit(synthetic_bundle)
    summary = _summary(synthetic_bundle)
    blockers = summary["censoring_blockers"]
    assert summary["censoring_blocker_count"] == len(blockers)
    assert not any("PAIRED_CONTRAST_PAIRED_CONTRAST" in item for item in blockers)
    assert blockers.count(
        "V7C_FILTERED_ACTION:PAIRED_CONTRAST_NON_COMPARABLE_EXPOSURE_CENSORED"
    ) == 1
    assert (
        "V7C_FILTERED_ACTION:SEED_18000_EXPOSURE_CENSORED" in blockers
    )
    assert sum(1 for item in blockers if item.startswith("V7C_FILTERED_ACTION:SEED_")) == 30


def test_exposure_matched_duty_arithmetic_is_pinned(synthetic_bundle):
    """Pin the prefix-sum index so an off-by-one cannot pass."""
    _audit(synthetic_bundle)
    summary = _summary(synthetic_bundle)
    sensitivity = next(
        item for item in summary["exposure_matched_sensitivity"]
        if item["candidate_arm_id"] == "V7C_FILTERED_ACTION"
    )
    reference_index = ARM_IDS.index("V7A_REWARD_ONLY")
    for pair in sensitivity["pairs"]:
        seed = pair["evaluation_seed"]
        matched = pair["matched_exposure_control_steps"]
        assert matched == 60
        over = sum(_over_count(reference_index, seed, step, 8) for step in range(matched))
        expected = round(100.0 * over / (matched * SUBSTEPS_PER_STEP), 6)
        assert pair["reference_matched_duty_pct"] == expected
        assert pair["candidate_matched_duty_pct"] == 0.0
        assert pair["matched_difference_pct"] == round(0.0 - expected, 6)


def _reindex_output(root: Path) -> None:
    """Recompute the audit receipt inventory so deeper checks can be reached."""
    def mutate(receipt: dict[str, object]) -> None:
        for record in receipt["artifacts"]:
            target = root / record["path"]
            record["bytes"] = target.stat().st_size
            record["sha256"] = _sha256_file(target)

    _rewrite(root / "audit_receipt.json", mutate)


def test_validate_re_derives_the_blocker_list_from_retained_states(synthetic_bundle):
    """A consistently re-stamped receipt must not certify a rewritten summary."""
    _audit(synthetic_bundle)
    output = synthetic_bundle["output"]

    def clear_blockers(payload: dict[str, object]) -> None:
        payload["censoring_blockers"] = []
        payload["censoring_blocker_count"] = 0
        payload["audit_status"] = "AUDIT_COMPLETE_NO_CENSORING_BLOCKER"

    _rewrite(output / "audit_summary.json", clear_blockers)

    def restamp(receipt: dict[str, object]) -> None:
        receipt["censoring_blocker_count"] = 0
        receipt["audit_status"] = "AUDIT_COMPLETE_NO_CENSORING_BLOCKER"

    _rewrite(output / "audit_receipt.json", restamp)
    _reindex_output(output)
    with pytest.raises(V7ExposureAuditError, match="retained comparability states"):
        validate_v7_exposure_audit_bundle(output / "audit_receipt.json")


def test_validate_rejects_a_blocker_count_that_disagrees_with_its_own_list(synthetic_bundle):
    _audit(synthetic_bundle)
    output = synthetic_bundle["output"]
    _rewrite(
        output / "audit_summary.json",
        lambda payload: payload.__setitem__("censoring_blocker_count", 999),
    )
    _rewrite(
        output / "audit_receipt.json",
        lambda payload: payload.__setitem__("censoring_blocker_count", 999),
    )
    _reindex_output(output)
    with pytest.raises(V7ExposureAuditError, match="its own blocker list"):
        validate_v7_exposure_audit_bundle(output / "audit_receipt.json")


def test_validate_rejects_a_forged_applicability_flag(synthetic_bundle):
    _audit(synthetic_bundle)
    output = synthetic_bundle["output"]
    _rewrite(
        output / "audit_summary.json",
        lambda payload: payload.__setitem__("audit_applies_to_frozen_v7_pilot", True),
    )
    _reindex_output(output)
    with pytest.raises(V7ExposureAuditError, match="applicability flag mismatch"):
        validate_v7_exposure_audit_bundle(output / "audit_receipt.json")


def test_post_audit_readback_detects_source_drift(synthetic_bundle, monkeypatch):
    """Prove the post-audit readback can actually fire, not just pass.

    The drifted artifact is the audited bundle's retained protocol copy, which
    _run_replay does not re-hash, so only the post-audit readback can catch it.
    """
    original_run = audit_module.subprocess.run
    drifted = synthetic_bundle["source"] / "v7_action_interface_pilot_protocol.json"

    def mutate_then_run(command, *args, **kwargs):
        result = original_run(command, *args, **kwargs)
        drifted.write_bytes(drifted.read_bytes() + b"\n")
        return result

    monkeypatch.setattr(audit_module.subprocess, "run", mutate_then_run)
    with pytest.raises(V7ExposureAuditError, match="read-only contract violated"):
        _audit(synthetic_bundle)


def test_replay_input_hash_gate_also_detects_raw_drift(synthetic_bundle, monkeypatch):
    """Raw-episode drift is caught independently of the post-audit readback."""
    original_run = audit_module.subprocess.run
    raw_path = synthetic_bundle["source"] / "raw_episodes.json"

    def mutate_then_run(command, *args, **kwargs):
        result = original_run(command, *args, **kwargs)
        raw_path.write_text(raw_path.read_text("utf-8") + "\n", encoding="utf-8")
        return result

    monkeypatch.setattr(audit_module.subprocess, "run", mutate_then_run)
    with pytest.raises(V7ExposureAuditError, match="raw_episodes_sha256 mismatch"):
        _audit(synthetic_bundle)


def test_file_added_to_the_audited_bundle_during_the_audit_is_detected(
    synthetic_bundle, monkeypatch
):
    original_run = audit_module.subprocess.run
    source = synthetic_bundle["source"]

    def add_then_run(command, *args, **kwargs):
        result = original_run(command, *args, **kwargs)
        (source / "smuggled.json").write_text("{}", encoding="utf-8")
        return result

    monkeypatch.setattr(audit_module.subprocess, "run", add_then_run)
    with pytest.raises(V7ExposureAuditError, match="gained or lost files"):
        _audit(synthetic_bundle)


def test_duplicate_evaluation_seed_fails_closed(synthetic_bundle):
    def mutate(payload):
        payload["arms"][0]["episodes"][1]["evaluation_seed"] = 18000

    _rewrite(synthetic_bundle["source"] / "raw_episodes.json", mutate)
    _reindex(synthetic_bundle["source"])
    with pytest.raises(V7ExposureAuditError, match="duplicate evaluation seed"):
        _audit(synthetic_bundle)


def test_unexpected_evaluation_seed_fails_closed(synthetic_bundle):
    def mutate(payload):
        payload["arms"][0]["episodes"][0]["evaluation_seed"] = 18030

    _rewrite(synthetic_bundle["source"] / "raw_episodes.json", mutate)
    _reindex(synthetic_bundle["source"])
    with pytest.raises(V7ExposureAuditError, match="missing or unexpected evaluation seed"):
        _audit(synthetic_bundle)


def test_arm_inventory_mismatch_fails_closed(synthetic_bundle):
    def mutate(payload):
        payload["arms"][2]["arm_id"] = "V7D_UNDECLARED_ARM"

    _rewrite(synthetic_bundle["source"] / "raw_episodes.json", mutate)
    _reindex(synthetic_bundle["source"])
    with pytest.raises(V7ExposureAuditError, match="arm inventory mismatch"):
        _audit(synthetic_bundle)


def test_zero_exposure_episode_may_not_retain_an_observed_primary(synthetic_bundle):
    def mutate(payload):
        row = payload["arms"][0]["episodes"][0]
        row["terminal_record_state"] = "FAILED"
        row["outcome_state"] = "OBSERVED"
        row["control_step_trace"] = []
        row["trace_receipt"] = {
            "sample_rate_hz": 500.0,
            "control_step_count": 0,
            "saturation_substeps_total": 0,
            "saturation_substeps_over_threshold": 0,
            "recomputed_saturation_duty_pct": None,
            "reported_saturation_duty_pct": None,
            "reported_absolute_delta": None,
            "action_operator_state": "NULL",
            "action_operator_max_abs_delta": None,
        }

    _rewrite(synthetic_bundle["source"] / "raw_episodes.json", mutate)
    _reindex(synthetic_bundle["source"])
    with pytest.raises(V7ExposureAuditError, match="no exposure but retains an observed"):
        _audit(synthetic_bundle)


def test_missing_selection_key_is_not_treated_as_a_null_selection(synthetic_bundle):
    _rewrite(
        synthetic_bundle["source"] / "pilot_summary.json",
        lambda payload: payload.pop("selected_candidate_arm_id"),
    )
    _reindex(synthetic_bundle["source"])
    with pytest.raises(V7ExposureAuditError, match="omits selected_candidate_arm_id"):
        _audit(synthetic_bundle)


def test_replay_staged_comparison_names_the_diverging_block(synthetic_bundle):
    _audit(synthetic_bundle)
    summary_path = synthetic_bundle["output"] / "audit_summary.json"
    _rewrite(
        summary_path,
        lambda payload: payload["exposure_matched_sensitivity"][0].__setitem__(
            "status", "CONFIRMATORY"
        ),
    )
    completed = subprocess.run(
        [
            sys.executable, "-I", "-S", str(REPLAY_SCRIPT),
            str(synthetic_bundle["output"] / "v7_exposure_audit_protocol.json"),
            str(synthetic_bundle["source"] / "pilot_receipt.json"),
            str(synthetic_bundle["source"] / "raw_episodes.json"),
            str(synthetic_bundle["source"] / "pilot_summary.json"),
            str(summary_path),
        ],
        capture_output=True, text=True, check=False,
    )
    assert completed.returncode == 2
    error = json.loads(completed.stdout)["error"]
    # The staged loop must name the block; the fallback prints a bracketed list.
    assert "at exposure_matched_sensitivity" in error


def test_forged_replay_receipt_with_a_short_check_inventory_is_rejected(
    synthetic_bundle, monkeypatch
):
    original_run = audit_module.subprocess.run

    def forge(command, *args, **kwargs):
        result = original_run(command, *args, **kwargs)
        receipt = json.loads(result.stdout)
        receipt["checks"] = {"audit_summary_exact": True}
        return subprocess.CompletedProcess(
            command, 0, json.dumps(receipt), ""
        )

    monkeypatch.setattr(audit_module.subprocess, "run", forge)
    with pytest.raises(V7ExposureAuditError, match="check inventory mismatch"):
        _audit(synthetic_bundle)


def test_replay_receipt_booleans_must_be_real_booleans(synthetic_bundle, monkeypatch):
    original_run = audit_module.subprocess.run

    def forge(command, *args, **kwargs):
        result = original_run(command, *args, **kwargs)
        receipt = json.loads(result.stdout)
        receipt["exact_identity"] = 1
        return subprocess.CompletedProcess(command, 0, json.dumps(receipt), "")

    monkeypatch.setattr(audit_module.subprocess, "run", forge)
    with pytest.raises(V7ExposureAuditError, match="exact_identity mismatch"):
        _audit(synthetic_bundle)


def test_replay_imports_no_process_or_argument_modules():
    """The replay must stay an isolated reimplementation, not a driver."""
    tree = ast.parse(REPLAY_SCRIPT.read_text("utf-8"))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert not node.level, "the replay must not use relative imports"
            roots.add((node.module or "").split(".")[0])
    assert roots <= STDLIB_IMPORTS, sorted(roots - STDLIB_IMPORTS)
    for forbidden in ("subprocess", "os", "argparse"):
        assert forbidden not in roots


def test_replay_check_inventory_matches_the_contract_expectation():
    assert (
        v7_exposure_audit_replay.EXPECTED_REPLAY_CHECKS
        == audit_module.EXPECTED_REPLAY_CHECKS
    )
    assert len(set(audit_module.EXPECTED_REPLAY_CHECKS)) == 14


def test_synthetic_fixture_satisfies_the_frozen_pilot_raw_schema(synthetic_bundle):
    """Guard against fixture drift: the pilot's own validator must accept it.

    Without this the audit could be exercised only against input the real
    pipeline would never produce, and a future pilot schema change would go
    unnoticed here.
    """
    raw = json.loads((synthetic_bundle["source"] / "raw_episodes.json").read_text("utf-8"))
    protocol = json.loads(PILOT_PROTOCOL_PATH.read_text("utf-8"))
    v7_pilot_replay._validate_raw(raw, protocol, _sha256_file(PILOT_PROTOCOL_PATH))


def test_replay_rejects_a_bundle_class_the_receipt_hash_contradicts(synthetic_bundle):
    """Reach the replay's own copy of the class-binding gate.

    The contract refuses such a bundle before spawning the replay, so the
    replay is invoked directly to prove its independent gate also fires.
    """
    _audit(synthetic_bundle)
    source = synthetic_bundle["source"]
    forged = source.parent / "forged_receipt.json"
    payload = json.loads((source / "pilot_receipt.json").read_text("utf-8"))
    payload["audit_source_bundle_class"] = DEVELOPMENT_BUNDLE_CLASS
    _write_json(forged, payload)
    assert _sha256_file(forged) != FROZEN_PILOT_RECEIPT_SHA256
    completed = subprocess.run(
        [
            sys.executable, "-I", "-S", str(REPLAY_SCRIPT),
            str(synthetic_bundle["output"] / "v7_exposure_audit_protocol.json"),
            str(forged),
            str(source / "raw_episodes.json"),
            str(source / "pilot_summary.json"),
            str(synthetic_bundle["output"] / "audit_summary.json"),
        ],
        capture_output=True, text=True, check=False,
    )
    assert completed.returncode == 2
    assert "class binding" in json.loads(completed.stdout)["error"]


def test_replay_rejects_files_the_audited_receipt_does_not_index(synthetic_bundle, tmp_path):
    """The replay must not mint a PASS receipt over unindexed data."""
    _audit(synthetic_bundle)
    source = synthetic_bundle["source"]
    swapped = tmp_path / "swapped_raw_episodes.json"
    payload = json.loads((source / "raw_episodes.json").read_text("utf-8"))
    payload["arms"][0]["episodes"][0]["control_step_trace"] = []
    _write_json(swapped, payload)
    completed = subprocess.run(
        [
            sys.executable, "-I", "-S", str(REPLAY_SCRIPT),
            str(synthetic_bundle["output"] / "v7_exposure_audit_protocol.json"),
            str(source / "pilot_receipt.json"),
            str(swapped),
            str(source / "pilot_summary.json"),
            str(synthetic_bundle["output"] / "audit_summary.json"),
        ],
        capture_output=True, text=True, check=False,
    )
    assert completed.returncode == 2
    assert "not the indexed raw_episodes artifact" in json.loads(completed.stdout)["error"]


def test_arm_rollups_retain_the_pilot_terminal_and_outcome_states(synthetic_bundle):
    _audit(synthetic_bundle)
    summary = _summary(synthetic_bundle)
    censored = next(
        arm for arm in summary["arm_exposure"] if arm["arm_id"] == "V7C_FILTERED_ACTION"
    )
    assert censored["terminal_record_state_counts"] == {
        "COMPLETED": 30,
        "FAILED": 0,
        "CANCELLED": 0,
    }
    # Every censored episode here is also a retained pilot-level null outcome.
    assert censored["outcome_state_counts"] == {"OBSERVED": 0, "NULL": 30, "NONFINITE": 0}
    reference = next(
        arm for arm in summary["arm_exposure"] if arm["arm_id"] == "V7A_REWARD_ONLY"
    )
    assert reference["outcome_state_counts"] == {"OBSERVED": 30, "NULL": 0, "NONFINITE": 0}


def test_identification_bound_assumption_is_stated_in_the_summary(synthetic_bundle):
    _audit(synthetic_bundle)
    findings = _summary(synthetic_bundle)["audit_findings"]
    assumption = findings["identification_bound_assumption"]
    assert "ASSUMPTION_FREE_GIVEN_THE_CONTRACT_DEFINED_FULL_HORIZON" in assumption
    assert "NOT_AN_OBSERVED_COUNTERFACTUAL" in assumption
    assert findings["censored_estimator"] == "NOT_FROZEN_BOUNDS_ONLY"

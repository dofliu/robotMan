"""Synthetic, fail-closed tests for the frozen v7 pilot evidence contract."""

from __future__ import annotations

import ast
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

import v7_pilot_contract as pilot_module
from v7_pilot_contract import (
    ARM_IDS,
    CLAIM_BOUNDARY,
    EXPECTED_SEEDS,
    PROTOCOL_ID,
    PROTOCOL_SHA256,
    V7PilotIntegrityError,
    build_v7_pilot_bundle,
    validate_v7_pilot_bundle,
)


REPO_ROOT = Path(__file__).resolve().parent.parent
PROTOCOL_PATH = REPO_ROOT / "backend" / "rl" / "v7_action_interface_pilot_protocol.json"
SOURCE_SHA = "a" * 40


def _sha256(payload: bytes) -> str:
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, allow_nan=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _git_identity(sha: str = SOURCE_SHA) -> dict:
    return {
        "available": True,
        "git_sha": sha,
        "working_tree_dirty": False,
        "working_tree_status": [],
    }


def _source_files() -> dict[str, str]:
    return {
        "backend/rl/action_interface_v7.py": "sha256:" + "1" * 64,
        "backend/rl/eval_policy.py": "sha256:" + "2" * 64,
        "backend/rl/humanoid_env.py": "sha256:" + "3" * 64,
        "backend/rl/train_ppo.py": "sha256:" + "4" * 64,
        "backend/rl/training_profiles.json": "sha256:" + "5" * 64,
        "backend/rl/v7_action_interface_pilot_protocol.json": PROTOCOL_SHA256,
        "backend/motion_tasks.py": (
            "sha256:3dd9a47b6798a2fba713eda3654b428377f3a75e825105b233a1da375d4215af"
        ),
        "backend/model_builder.py": (
            "sha256:0beabfa2df6fde118dc2dfaea94a22da9af42c69c49ee2290993322cf96aab29"
        ),
        "backend/config_schema.py": (
            "sha256:426ce01561284dc84f50018c6f2558951c9dd820a7cf2756ac2ae8ee728ed298"
        ),
    }


def _training_manifest(arm: dict, policy: bytes) -> dict:
    interface = {
        "pilot_arm_id": arm["arm_id"],
        "action_interface_id": arm["action_interface_id"],
        "action_scale_rad": arm["action_scale_rad"],
        "low_pass_alpha": arm["low_pass_alpha"],
        "rate_limit_normalized_per_control_step": arm[
            "rate_limit_normalized_per_control_step"
        ],
        "previous_action_semantics": "PREVIOUS_APPLIED_NORMALIZED_ACTION",
    }
    return {
        "schema_version": "RL_TRAINING_RUN_V2",
        "run_id": arm["training_run_id"],
        "profile": {
            "profile_id": arm["profile_id"],
            "speed_mps": 0.7,
            "step_length_m": 0.35,
            "duty": 0.62,
            "clearance_m": 0.07,
            "planned_timesteps": 100000,
            "parallel_envs": 12,
            "seed_base": 8700,
            "status": "FROZEN_DEVELOPMENT_PILOT_CONFIGURATION",
            "environment_id": arm["environment_id"],
            "task_id": "stand_start_walk_stop_v1",
            "warm_start_policy_id": "stand_start_walk_stop_0p7_phase_observable_v5",
            "pilot_protocol_id": PROTOCOL_ID,
            "pilot_arm_id": arm["arm_id"],
        },
        "resolved": {
            "total_timesteps": 100000,
            "parallel_envs": 12,
            "seed_base": 8700,
            "device": "cpu",
            "run_kind": "development_training",
        },
        "status": "DEVELOPMENT_TRAINING_UNEVALUATED",
        "started_at": "2026-09-06T00:00:00+00:00",
        "completed_at": "2026-09-06T00:10:00+00:00",
        "artifact": {
            "relative_path": "policy.zip",
            "bytes": len(policy),
            "sha256": _sha256(policy),
        },
        "actual_total_timesteps": 122880,
        "source_files": _source_files(),
        "evidence_scope": "SOFTWARE_TRAINING_PIPELINE_ONLY",
        "source_git_pre": _git_identity(),
        "source_git_post": _git_identity(),
        "pilot_protocol": {
            "protocol_id": PROTOCOL_ID,
            "pilot_arm_id": arm["arm_id"],
            "path": "backend/rl/v7_action_interface_pilot_protocol.json",
            "bytes": PROTOCOL_PATH.stat().st_size,
            "sha256": PROTOCOL_SHA256,
            "action_interface": {
                key: interface[key]
                for key in (
                    "action_interface_id",
                    "action_scale_rad",
                    "low_pass_alpha",
                    "rate_limit_normalized_per_control_step",
                )
            },
        },
        "warm_start": {
            "policy_id": "stand_start_walk_stop_0p7_phase_observable_v5",
            "artifact": "ppo_stand_start_walk_stop_0p7_phase_observable_v5.zip",
            "bytes": 1983126,
            "sha256": (
                "sha256:c548867fbd17c736d54c1b1598d2abed1c7cb2dd28c7d310ea6e86ac3b36718c"
            ),
            "evidence_status": "LIVE_500HZ_TASK_EVALUATED_FAIL_SATURATION_DUTY",
            "transfer": {"method": "EXACT_POLICY_STATE_TRANSFER_V1"},
        },
        "policy_contract": {
            "observation_dim": 51,
            "action_dim": 12,
            "algorithm": "PPO_MLP",
            "n_steps_per_env": 2048,
            "batch_size": 8192,
            "n_epochs": 5,
            "action_interface": interface,
        },
    }


def _episode(seed: int, saturation: float) -> dict:
    remaining_over = int(saturation)
    trace = []
    for control_step in range(10):
        over = min(10, remaining_over)
        remaining_over -= over
        trace.append({
            "control_step": control_step,
            "command_phase": "STEADY_WALK",
            "requested_action": [0.0] * 12,
            "applied_action": [0.0] * 12,
            "joint_target_rad": [0.0] * 12,
            "applied_action_delta_l2": 0.0,
            "requested_applied_delta_l2": 0.0,
            "saturation_substeps_over_threshold": over,
            "saturation_substeps_total": 10,
        })
    return {
        "episode": seed - EXPECTED_SEEDS[0],
        "seed": seed,
        "terminal_record_state": "COMPLETED",
        "outcome_state": "OBSERVED",
        "reason": None,
        "metrics": {
            "fell": False,
            "steady_walk_mean_speed_mps": 0.7,
            "steady_walk_progress_m": 1.6,
            "final_stand_mean_abs_speed_mps": 0.1,
            "lateral_drift_m": 0.1,
            "saturation_duty_pct": saturation,
        },
        "control_step_trace": trace,
        "saturation_sample_rate_hz": 500.0,
    }


def _evaluation(arm: dict, policy: bytes, saturation: float) -> dict:
    return {
        "schema_version": "RL_TRAINING_ENV_EVALUATION_V4",
        "evidence_scope": "SOFTWARE_TRAINING_ENV_DEVELOPMENT_EVALUATION_ONLY",
        "status": "COMPLETED",
        "failure": None,
        "model": {
            "path": "policy.zip",
            "bytes": len(policy),
            "sha256": _sha256(policy),
        },
        "profile_id": arm["profile_id"],
        "episodes": 30,
        "seed_base": 18000,
        "evaluation_seeds": list(EXPECTED_SEEDS),
        "pilot_protocol": {
            "protocol_id": PROTOCOL_ID,
            "arm_id": arm["arm_id"],
            "path": "backend/rl/v7_action_interface_pilot_protocol.json",
            "bytes": PROTOCOL_PATH.stat().st_size,
            "sha256": PROTOCOL_SHA256,
        },
        "source_git_pre": _git_identity(),
        "source_git_post": _git_identity(),
        "source_files": _source_files(),
        "action_interface": {
            "pilot_arm_id": arm["arm_id"],
            "action_interface_id": arm["action_interface_id"],
            "action_scale_rad": arm["action_scale_rad"],
            "low_pass_alpha": arm["low_pass_alpha"],
            "rate_limit_normalized_per_control_step": arm[
                "rate_limit_normalized_per_control_step"
            ],
            "previous_action_semantics": "PREVIOUS_APPLIED_NORMALIZED_ACTION",
        },
        "episode_results": [_episode(seed, saturation) for seed in EXPECTED_SEEDS],
        "summary": {"untrusted_source_summary": True},
    }


@pytest.fixture
def synthetic_runs(tmp_path: Path) -> dict:
    protocol = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    artifacts_root = tmp_path / "artifacts"
    manifests: dict[str, Path] = {}
    evaluations: dict[str, Path] = {}
    policies: dict[str, Path] = {}
    saturations = {
        "V7A_REWARD_ONLY": 24.0,
        "V7B_REDUCED_JOINT_ENVELOPE": 18.0,
        "V7C_FILTERED_ACTION": 20.0,
    }
    for arm in protocol["arms"]:
        run_dir = artifacts_root / arm["training_run_id"]
        policy = ("synthetic-policy-" + arm["arm_id"]).encode("ascii")
        policy_path = run_dir / "policy.zip"
        policy_path.parent.mkdir(parents=True)
        policy_path.write_bytes(policy)
        manifest_path = run_dir / "run_manifest.json"
        evaluation_path = run_dir / "evaluation_dev18000_18029.json"
        _write_json(manifest_path, _training_manifest(arm, policy))
        _write_json(evaluation_path, _evaluation(arm, policy, saturations[arm["arm_id"]]))
        manifests[arm["arm_id"]] = manifest_path
        evaluations[arm["arm_id"]] = evaluation_path
        policies[arm["arm_id"]] = policy_path
    return {
        "root": tmp_path,
        "artifacts": artifacts_root,
        "manifests": manifests,
        "evaluations": evaluations,
        "policies": policies,
        "output": tmp_path / "bundle",
    }


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _rewrite(path: Path, mutate) -> dict:
    payload = _load(path)
    mutate(payload)
    _write_json(path, payload)
    return payload


def _set_row_saturation(row: dict, value: float) -> None:
    row["metrics"]["saturation_duty_pct"] = value
    remaining = int(value)
    for trace_row in row["control_step_trace"]:
        over = min(10, remaining)
        remaining -= over
        trace_row["saturation_substeps_over_threshold"] = over


def _build(paths: dict) -> dict:
    return build_v7_pilot_bundle(
        PROTOCOL_PATH,
        paths["output"],
        artifacts_root=paths["artifacts"],
        repo_root=REPO_ROOT,
        verify_repository=False,
    )


def test_builds_valid_three_arm_bundle_with_exact_statistics_and_replay(synthetic_runs):
    receipt = _build(synthetic_runs)

    assert receipt["contract_valid"] is True
    assert receipt["pilot_planning_ready"] is True
    assert receipt["selection_status"] == "PILOT_COMPLETE_CANDIDATE_SELECTED"
    assert receipt["selected_candidate_arm_id"] == "V7B_REDUCED_JOINT_ENVELOPE"
    assert receipt["method_level_power_ready"] is False
    assert receipt["paper_data_ready"] is False
    assert receipt["claim_boundary"] == CLAIM_BOUNDARY
    summary = _load(synthetic_runs["output"] / "pilot_summary.json")
    summaries = {item["arm_id"]: item for item in summary["arm_summaries"]}
    assert summaries["V7A_REWARD_ONLY"]["saturation_duty_pct"]["mean"] == 24.0
    assert summaries["V7A_REWARD_ONLY"]["saturation_duty_pct"][
        "sample_standard_deviation"
    ] == 0.0
    contrasts = {item["candidate_arm_id"]: item for item in summary["paired_contrasts"]}
    assert contrasts["V7B_REDUCED_JOINT_ENVELOPE"]["mean_difference"] == -6.0
    assert contrasts["V7C_FILTERED_ACTION"]["mean_difference"] == -4.0
    replay = _load(synthetic_runs["output"] / "replay_receipt.json")
    assert replay["status"] == "PASS"
    assert replay["exact_identity"] is True
    raw = _load(synthetic_runs["output"] / "raw_episodes.json")
    trace_row = raw["arms"][0]["episodes"][0]["control_step_trace"][0]
    assert trace_row["command_phase"] == "STEADY_WALK"
    assert trace_row["joint_target_rad"] == [0.0] * 12
    assert trace_row["applied_action_delta_l2"] == 0.0
    assert trace_row["requested_applied_delta_l2"] == 0.0
    validation = validate_v7_pilot_bundle(synthetic_runs["output"] / "pilot_receipt.json")
    assert validation["validation_status"] == "BUNDLE_VALID"
    assert validation["artifact_count"] == 14


def test_complete_performance_failures_are_retained_as_negative_result(synthetic_runs):
    for arm_id in ARM_IDS[1:]:
        _rewrite(
            synthetic_runs["evaluations"][arm_id],
            lambda payload: [
                _set_row_saturation(row, 35.0)
                for row in payload["episode_results"]
            ],
        )
    receipt = _build(synthetic_runs)
    summary = _load(synthetic_runs["output"] / "pilot_summary.json")

    assert receipt["pilot_planning_ready"] is True
    assert receipt["selection_status"] == "PILOT_COMPLETE_NEGATIVE_RESULT_NO_CANDIDATE"
    assert receipt["selected_candidate_arm_id"] is None
    candidates = [item for item in summary["arm_summaries"] if item["arm_id"] in ARM_IDS[1:]]
    assert all(item["negative_episode_count"] == 30 for item in candidates)
    assert all(item["eligible"] is False for item in candidates)


def test_failed_cancelled_null_and_nonfinite_states_are_retained_without_deletion(
    synthetic_runs,
):
    def nonfinite(payload):
        payload["status"] = "COMPLETED_WITH_BLOCKER"
        row = payload["episode_results"][0]
        row["outcome_state"] = "NONFINITE"
        row["reason"] = "SOURCE_EVALUATOR_REPORTED_NAN"
        row["metrics"]["saturation_duty_pct"] = None

    def cancelled(payload):
        payload["status"] = "CANCELLED"
        payload["failure"] = {"type": "KeyboardInterrupt"}
        payload.pop("action_interface")
        for row in payload["episode_results"]:
            row["terminal_record_state"] = "CANCELLED"
            row["outcome_state"] = "NULL"
            row["reason"] = "EVALUATION_CANCELLED:KeyboardInterrupt"
            row["metrics"] = {
                "fell": None,
                "steady_walk_mean_speed_mps": None,
                "steady_walk_progress_m": None,
                "final_stand_mean_abs_speed_mps": None,
                "lateral_drift_m": None,
                "saturation_duty_pct": None,
            }
            row["control_step_trace"] = []

    def failed(payload):
        payload["status"] = "FAILED"
        payload["failure"] = {"type": "RuntimeError"}
        payload.pop("action_interface")
        for row in payload["episode_results"]:
            row["terminal_record_state"] = "FAILED"
            row["outcome_state"] = "NULL"
            row["reason"] = "EVALUATION_FAILED:RuntimeError"
            row["metrics"] = {
                "fell": None,
                "steady_walk_mean_speed_mps": None,
                "steady_walk_progress_m": None,
                "final_stand_mean_abs_speed_mps": None,
                "lateral_drift_m": None,
                "saturation_duty_pct": None,
            }
            row["control_step_trace"] = []

    _rewrite(synthetic_runs["evaluations"][ARM_IDS[0]], nonfinite)
    _rewrite(synthetic_runs["evaluations"][ARM_IDS[1]], cancelled)
    _rewrite(synthetic_runs["evaluations"][ARM_IDS[2]], failed)
    receipt = _build(synthetic_runs)
    raw = _load(synthetic_runs["output"] / "raw_episodes.json")
    summary = _load(synthetic_runs["output"] / "pilot_summary.json")

    assert receipt["pilot_planning_ready"] is False
    assert receipt["selection_status"] == "PILOT_RETAINED_SEMANTIC_BLOCKER"
    assert any("FAILED" in item for item in receipt["semantic_blockers"])
    assert any("CANCELLED" in item for item in receipt["semantic_blockers"])
    assert raw["arms"][0]["episodes"][0]["measurements"]["saturation_duty_pct"] == {
        "state": "NONFINITE",
        "value": None,
        "reason": "SOURCE_EVALUATOR_REPORTED_NAN",
    }
    reference = summary["arm_summaries"][0]
    assert reference["outcome_state_counts"]["NONFINITE"] == 1
    assert reference["saturation_duty_pct"]["mean"] is None
    assert reference["saturation_duty_pct"]["n_observed"] == 29
    assert summary["paired_contrasts"][0]["mean_difference"] is None
    assert summary["paired_contrasts"][0]["n_observed"] == 0


@pytest.mark.parametrize("invalid", ["duplicate", "nan", "overflow"])
def test_strict_json_rejects_duplicate_keys_and_nan(synthetic_runs, invalid):
    path = synthetic_runs["evaluations"][ARM_IDS[0]]
    text = path.read_text(encoding="utf-8")
    if invalid == "duplicate":
        text = text.replace(
            '"schema_version": "RL_TRAINING_ENV_EVALUATION_V4",',
            '"schema_version": "RL_TRAINING_ENV_EVALUATION_V4",\n'
            '  "schema_version": "RL_TRAINING_ENV_EVALUATION_V4",',
            1,
        )
    elif invalid == "nan":
        text = text.replace('"saturation_duty_pct": 24.0', '"saturation_duty_pct": NaN', 1)
    else:
        text = text.replace('"saturation_duty_pct": 24.0', '"saturation_duty_pct": 1e400', 1)
    path.write_text(text, encoding="utf-8")

    with pytest.raises(V7PilotIntegrityError, match="duplicate JSON key|non-finite"):
        _build(synthetic_runs)


@pytest.mark.parametrize(
    ("seed", "message"),
    [
        (19000, "retired seed"),
        (20000, "sealed FORMAL/HOLDOUT"),
        (18000, "duplicate evaluation seed"),
        (17000, "missing or unexpected evaluation seed"),
    ],
)
def test_seed_inventory_rejects_retired_sealed_duplicate_and_unexpected(
    synthetic_runs,
    seed,
    message,
):
    def mutate(payload):
        payload["episode_results"][-1]["seed"] = seed

    _rewrite(synthetic_runs["evaluations"][ARM_IDS[2]], mutate)
    with pytest.raises(V7PilotIntegrityError, match=message):
        _build(synthetic_runs)


def test_policy_path_escape_and_bytes_tamper_fail_closed(synthetic_runs):
    manifest_path = synthetic_runs["manifests"][ARM_IDS[0]]
    _rewrite(
        manifest_path,
        lambda payload: payload["artifact"].__setitem__("relative_path", "../policy.zip"),
    )
    with pytest.raises(V7PilotIntegrityError, match="safe relative path"):
        _build(synthetic_runs)


def test_policy_sha_mismatch_fails_closed(synthetic_runs):
    synthetic_runs["policies"][ARM_IDS[0]].write_bytes(b"tampered-policy")
    with pytest.raises(V7PilotIntegrityError, match="policy bytes/SHA-256 mismatch"):
        _build(synthetic_runs)


@pytest.mark.parametrize("unsafe_path", ["C:/outside/policy.zip", "//server/share/policy.zip"])
def test_windows_drive_and_unc_model_paths_fail_closed(synthetic_runs, unsafe_path):
    _rewrite(
        synthetic_runs["evaluations"][ARM_IDS[0]],
        lambda payload: payload["model"].__setitem__("path", unsafe_path),
    )
    with pytest.raises(V7PilotIntegrityError, match="safe relative path"):
        _build(synthetic_runs)


def test_completed_episode_requires_nonempty_500hz_trace(synthetic_runs):
    _rewrite(
        synthetic_runs["evaluations"][ARM_IDS[0]],
        lambda payload: payload["episode_results"][0].__setitem__(
            "control_step_trace", []
        ),
    )
    with pytest.raises(V7PilotIntegrityError, match="non-empty 500 Hz trace"):
        _build(synthetic_runs)


def test_saturation_duty_is_recomputed_from_substep_counts(synthetic_runs):
    def mutate(payload):
        payload["episode_results"][0]["control_step_trace"][2][
            "saturation_substeps_over_threshold"
        ] += 1

    _rewrite(synthetic_runs["evaluations"][ARM_IDS[0]], mutate)
    with pytest.raises(V7PilotIntegrityError, match="500 Hz saturation duty mismatch"):
        _build(synthetic_runs)


def test_filtered_action_operator_is_replayed_from_raw_trace(synthetic_runs):
    def mutate(payload):
        payload["episode_results"][0]["control_step_trace"][0]["applied_action"][0] = 0.1
        payload["episode_results"][0]["control_step_trace"][0][
            "applied_action_delta_l2"
        ] = 0.1

    _rewrite(synthetic_runs["evaluations"][ARM_IDS[2]], mutate)
    with pytest.raises(V7PilotIntegrityError, match="action operator identity mismatch"):
        _build(synthetic_runs)


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("joint_target_rad", [None] + [0.0] * 11),
        ("applied_action_delta_l2", None),
        ("requested_applied_delta_l2", None),
        ("command_phase", ""),
    ],
)
def test_frozen_control_trace_fields_must_be_finite_and_nonempty(
    synthetic_runs, field, replacement
):
    def mutate(payload):
        payload["episode_results"][0]["control_step_trace"][0][field] = replacement

    _rewrite(synthetic_runs["evaluations"][ARM_IDS[0]], mutate)
    with pytest.raises(V7PilotIntegrityError):
        _build(synthetic_runs)


def test_git_pre_post_identity_drift_fails_closed(synthetic_runs):
    _rewrite(
        synthetic_runs["manifests"][ARM_IDS[0]],
        lambda payload: payload["source_git_post"].__setitem__("git_sha", "b" * 40),
    )
    with pytest.raises(V7PilotIntegrityError, match="Git pre/post identity drift"):
        _build(synthetic_runs)


def test_bundle_validator_rejects_unindexed_file_and_summary_tamper(synthetic_runs):
    _build(synthetic_runs)
    receipt_path = synthetic_runs["output"] / "pilot_receipt.json"
    extra = synthetic_runs["output"] / "unindexed.txt"
    extra.write_text("unexpected", encoding="utf-8")
    with pytest.raises(V7PilotIntegrityError, match="missing or unindexed"):
        validate_v7_pilot_bundle(receipt_path)
    extra.unlink()
    summary_path = synthetic_runs["output"] / "pilot_summary.json"
    payload = _load(summary_path)
    payload["selected_candidate_arm_id"] = ARM_IDS[2]
    _write_json(summary_path, payload)
    with pytest.raises(V7PilotIntegrityError, match="bytes/SHA-256 mismatch"):
        validate_v7_pilot_bundle(receipt_path)


def test_validator_deep_checks_source_index_bindings_after_receipt_rehash(synthetic_runs):
    _build(synthetic_runs)
    root = synthetic_runs["output"]
    source_index_path = root / "source_index.json"
    source_index = _load(source_index_path)
    source_index["arms"][0]["trained_policy"]["sha256"] = "sha256:" + "f" * 64
    _write_json(source_index_path, source_index)
    receipt_path = root / "pilot_receipt.json"
    receipt = _load(receipt_path)
    record = next(item for item in receipt["artifacts"] if item["role"] == "source_index")
    record["bytes"] = source_index_path.stat().st_size
    record["sha256"] = pilot_module.sha256_file(source_index_path)
    _write_json(receipt_path, receipt)

    with pytest.raises(V7PilotIntegrityError, match="trained_policy inventory drift"):
        validate_v7_pilot_bundle(receipt_path)


def test_builder_invokes_exact_isolated_python_replay(synthetic_runs, monkeypatch):
    original_run = pilot_module.subprocess.run
    commands: list[list[str]] = []

    def recording_run(command, *args, **kwargs):
        commands.append(command)
        return original_run(command, *args, **kwargs)

    monkeypatch.setattr(pilot_module.subprocess, "run", recording_run)
    _build(synthetic_runs)
    replay_commands = [
        command for command in commands if str(command[3]).endswith("v7_pilot_replay.py")
    ]
    assert len(replay_commands) == 2
    assert all(command[1:3] == ["-I", "-S"] for command in replay_commands)


def test_cli_exit_codes_distinguish_complete_semantic_and_structural(synthetic_runs):
    _build(synthetic_runs)
    receipt_path = synthetic_runs["output"] / "pilot_receipt.json"
    command = [
        sys.executable,
        "-I",
        "-S",
        str(Path(pilot_module.__file__)),
        "validate",
        str(receipt_path),
    ]
    complete = subprocess.run(command, capture_output=True, text=True, check=False)
    assert complete.returncode == 0, complete.stderr
    assert json.loads(complete.stdout)["validation_status"] == "BUNDLE_VALID"

    receipt = _load(receipt_path)
    receipt["unexpected"] = "not part of the receipt schema"
    _write_json(receipt_path, receipt)
    structural = subprocess.run(command, capture_output=True, text=True, check=False)
    assert structural.returncode == 2
    assert json.loads(structural.stdout)["validation_status"] == "STRUCTURAL_FAILURE"


def test_cli_returns_one_for_retained_semantic_blocker(synthetic_runs):
    def mutate(payload):
        payload["status"] = "COMPLETED_WITH_BLOCKER"
        row = payload["episode_results"][0]
        row["outcome_state"] = "NONFINITE"
        row["reason"] = "NONFINITE_REQUIRED_OUTCOME"
        row["metrics"]["saturation_duty_pct"] = None

    _rewrite(synthetic_runs["evaluations"][ARM_IDS[0]], mutate)
    receipt = _build(synthetic_runs)
    assert receipt["pilot_planning_ready"] is False
    completed = subprocess.run(
        [
            sys.executable,
            "-I",
            "-S",
            str(Path(pilot_module.__file__)),
            "validate",
            str(synthetic_runs["output"] / "pilot_receipt.json"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 1, completed.stderr
    assert json.loads(completed.stdout)["pilot_planning_ready"] is False


def test_replay_runs_under_isolated_stdlib_python_and_has_no_project_imports(
    synthetic_runs,
):
    _build(synthetic_runs)
    replay_path = Path(__file__).with_name("v7_pilot_replay.py")
    source = replay_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        (node.module or "").split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }
    assert imports <= {
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
    completed = subprocess.run(
        [
            sys.executable,
            "-I",
            "-S",
            str(replay_path),
            str(synthetic_runs["output"] / "protocol.json"),
            str(synthetic_runs["output"] / "raw_episodes.json"),
            str(synthetic_runs["output"] / "pilot_summary.json"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout)["exact_identity"] is True


def test_protocol_copy_with_mutated_arm_is_rejected_before_source_use(
    synthetic_runs,
    tmp_path,
):
    protocol_dir = tmp_path / "protocol-copy"
    copied = protocol_dir / PROTOCOL_PATH.name
    payload = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    payload["arms"][0]["action_scale_rad"][0] = 0.6
    _write_json(copied, payload)
    with pytest.raises(V7PilotIntegrityError, match="protocol SHA-256 mismatch"):
        build_v7_pilot_bundle(
            copied,
            tmp_path / "mutated-output",
            artifacts_root=synthetic_runs["artifacts"],
            repo_root=REPO_ROOT,
            verify_repository=False,
        )

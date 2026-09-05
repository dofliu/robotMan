"""Fixed-speed and command-conditioned RL training contract tests."""

import numpy as np
import pytest
from fastapi.testclient import TestClient

import main
from rl.humanoid_env import (
    HumanoidMotionTaskCurriculumEnv,
    HumanoidMotionTaskEnv,
    HumanoidMotionTaskFilteredActionV7Env,
    HumanoidMotionTaskPathEfficiencyEnv,
    HumanoidMotionTaskPathStopEnv,
    HumanoidMotionTaskPhaseObservableEnv,
    HumanoidMotionTaskReducedJointEnvelopeV7Env,
    HumanoidMotionTaskRewardOnlyV7Env,
    HumanoidMotionTaskSubstepSaturationEnv,
    HumanoidWalkEnv,
)
from rl.train_ppo import load_profiles, make_env, public_training_inventory, resolve_profile


ACTION_DIAGNOSTIC_KEYS = {
    "action_interface_id",
    "requested_action",
    "applied_action",
    "joint_target_rad",
    "applied_action_delta_l2",
    "requested_applied_delta_l2",
}


def test_fixed_speed_and_motion_task_profiles_are_versioned_and_not_marked_trained():
    profiles = load_profiles()

    assert profiles.schema_version == "RL_TRAINING_PROFILES_V4"
    assert [item.profile_id for item in profiles.profiles] == [
        "walk_0p4_fixed_v1", "walk_0p7_fixed_v1", "walk_1p0_fixed_v1",
        "stand_start_walk_stop_0p7_v1", "stand_start_walk_stop_0p7_curriculum_v2",
        "stand_start_walk_stop_0p7_path_efficiency_v3",
        "stand_start_walk_stop_0p7_path_stop_v4",
        "stand_start_walk_stop_0p7_phase_observable_v5",
        "stand_start_walk_stop_0p7_substep_saturation_v6",
        "stand_start_walk_stop_0p7_action_reward_v7a",
        "stand_start_walk_stop_0p7_reduced_joint_envelope_v7b",
        "stand_start_walk_stop_0p7_filtered_action_v7c",
    ]
    assert [item.speed_mps for item in profiles.profiles] == pytest.approx(
        [0.4, 0.7, 1.0] + [0.7] * 9
    )
    by_id = {item.profile_id: item for item in profiles.profiles}
    assert by_id["stand_start_walk_stop_0p7_v1"].status == (
        "EARLY_STOPPED_FAILED_SPEED_GATE_2026_08_30"
    )
    assert by_id["stand_start_walk_stop_0p7_curriculum_v2"].status == (
        "LIVE_500HZ_EVALUATED_FAIL_LATERAL_SATURATION_2026_08_30"
    )
    assert by_id["stand_start_walk_stop_0p7_substep_saturation_v6"].status == (
        "DEVELOPMENT_100K_EVALUATED_FAIL_2026_08_30"
    )
    assert all(
        by_id[profile_id].status == "FROZEN_DEVELOPMENT_PILOT_CONFIGURATION"
        for profile_id in [
            "stand_start_walk_stop_0p7_action_reward_v7a",
            "stand_start_walk_stop_0p7_reduced_joint_envelope_v7b",
            "stand_start_walk_stop_0p7_filtered_action_v7c",
        ]
    )


@pytest.mark.parametrize("profile_id", [
    "walk_0p4_fixed_v1", "walk_0p7_fixed_v1", "walk_1p0_fixed_v1",
])
def test_profile_resolves_into_matching_environment_contract(profile_id):
    profile = resolve_profile(profile_id)
    env = HumanoidWalkEnv(
        speed=profile.speed_mps,
        step_length=profile.step_length_m,
        duty=profile.duty,
        clearance=profile.clearance_m,
        episode_s=0.1,
    )
    try:
        observation, _ = env.reset(seed=profile.seed_base)
        _, reward, terminated, truncated, info = env.step(env.action_space.sample() * 0)
    finally:
        env.close()

    assert env.gait.speed == pytest.approx(profile.speed_mps)
    assert env.gait.step_length == pytest.approx(profile.step_length_m)
    assert env.gait.duty == pytest.approx(profile.duty)
    assert env.gait.clearance == pytest.approx(profile.clearance_m)
    assert observation.shape == env.observation_space.shape
    assert reward == pytest.approx(float(reward))
    assert isinstance(terminated, bool)
    assert isinstance(truncated, bool)
    assert set(info) == {"x", "vx"}


def test_unknown_training_profile_is_rejected():
    with pytest.raises(KeyError, match="unknown training profile"):
        resolve_profile("walk_unknown")


def test_public_training_inventory_is_read_only_and_explicit():
    body = public_training_inventory()
    assert body["schema_version"] == "RL_TRAINING_PROFILES_V4"
    assert body["execution_mode"] == "OFFLINE_EXPLICIT_COMMAND_ONLY"
    assert len(body["profiles"]) == 12
    assert [item["pilot_arm_id"] for item in body["profiles"][-3:]] == [
        "V7A_REWARD_ONLY",
        "V7B_REDUCED_JOINT_ENVELOPE",
        "V7C_FILTERED_ACTION",
    ]


def test_training_profile_api_exposes_inventory_without_starting_a_run():
    response = TestClient(main.app).get("/api/training/profiles")
    assert response.status_code == 200
    body = response.json()
    assert body["execution_mode"] == "OFFLINE_EXPLICIT_COMMAND_ONLY"
    assert body["profiles"][-1]["task_id"] == "stand_start_walk_stop_v1"


def test_motion_task_profile_adds_command_observation_and_frozen_schedule():
    profile = resolve_profile("stand_start_walk_stop_0p7_v1")
    factory = make_env(profile.model_dump(), rank=0, seed_base=profile.seed_base)
    env = factory()
    try:
        assert isinstance(env, HumanoidMotionTaskEnv)
        observation, info = env.reset(seed=profile.seed_base)
        assert observation.shape == (48,)
        assert info == {"command_vx": 0.0, "command_phase": "INITIAL_STAND"}
        steady_speed, steady_phase = env._command_at(2.5)
        assert steady_phase == "STEADY_WALK"
        assert steady_speed == pytest.approx(0.7)
        stop_speed, stop_phase = env._command_at(7.25)
        assert stop_phase == "STOP"
        assert stop_speed == pytest.approx(0.35)
        _, reward, terminated, truncated, step_info = env.step(np.zeros(12))
    finally:
        env.close()

    assert reward == pytest.approx(float(reward))
    assert isinstance(terminated, bool)
    assert isinstance(truncated, bool)
    assert {
        "x", "vx", "command_vx", "command_phase",
        "saturation_substeps_over_threshold", "saturation_substeps_total",
        "saturation_excess_sq_mean_500hz", *ACTION_DIAGNOSTIC_KEYS,
    } == set(step_info)


def test_curriculum_profile_uses_warm_start_envelope_and_forward_rewards():
    profile = resolve_profile("stand_start_walk_stop_0p7_curriculum_v2")
    factory = make_env(profile.model_dump(), rank=0, seed_base=profile.seed_base)
    env = factory()
    try:
        assert isinstance(env, HumanoidMotionTaskCurriculumEnv)
        assert env.command_action_envelope is True
        assert env.velocity_reward_weight == pytest.approx(1.2)
        assert env.progress_reward_weight == pytest.approx(0.35)
        assert env.reverse_penalty_weight == pytest.approx(0.8)
        observation, info = env.reset(seed=profile.seed_base)
        _, reward, terminated, truncated, step_info = env.step(np.ones(12))
    finally:
        env.close()

    assert observation.shape == (48,)
    assert info == {"command_vx": 0.0, "command_phase": "INITIAL_STAND"}
    assert reward == pytest.approx(float(reward))
    assert isinstance(terminated, bool)
    assert isinstance(truncated, bool)
    assert {
        "x", "vx", "command_vx", "command_phase",
        "saturation_substeps_over_threshold", "saturation_substeps_total",
        "saturation_excess_sq_mean_500hz", *ACTION_DIAGNOSTIC_KEYS,
    } == set(step_info)


def test_path_efficiency_profile_adds_observable_path_errors_and_load_metrics():
    profile = resolve_profile("stand_start_walk_stop_0p7_path_efficiency_v3")
    factory = make_env(profile.model_dump(), rank=0, seed_base=profile.seed_base)
    env = factory()
    try:
        assert isinstance(env, HumanoidMotionTaskPathEfficiencyEnv)
        observation, _ = env.reset(seed=profile.seed_base)
        _, reward, terminated, truncated, step_info = env.step(np.zeros(12))
    finally:
        env.close()

    assert observation.shape == (50,)
    assert reward == pytest.approx(float(reward))
    assert isinstance(terminated, bool)
    assert isinstance(truncated, bool)
    assert {"lateral_y", "lateral_vy", "yaw_rad", "yaw_rate_rps", "max_torque_ratio"} <= set(step_info)


def test_path_stop_profile_preserves_50d_contract_and_terminal_penalty_environment():
    profile = resolve_profile("stand_start_walk_stop_0p7_path_stop_v4")
    factory = make_env(profile.model_dump(), rank=0, seed_base=profile.seed_base)
    env = factory()
    try:
        observation, _ = env.reset(seed=profile.seed_base)
        _, reward, terminated, truncated, _ = env.step(np.zeros(12))
    finally:
        env.close()

    assert isinstance(env, HumanoidMotionTaskPathStopEnv)
    assert observation.shape == (50,)
    assert reward == pytest.approx(float(reward))
    assert isinstance(terminated, bool)
    assert isinstance(truncated, bool)


def test_phase_observable_profile_adds_signed_start_stop_trend():
    profile = resolve_profile("stand_start_walk_stop_0p7_phase_observable_v5")
    factory = make_env(profile.model_dump(), rank=0, seed_base=profile.seed_base)
    env = factory()
    try:
        observation, _ = env.reset(seed=profile.seed_base)
        assert isinstance(env, HumanoidMotionTaskPhaseObservableEnv)
        assert observation.shape == (51,)
        assert observation[-1] == pytest.approx(0.0)
        env.command_phase = "START"
        assert env._obs()[-1] == pytest.approx(1.0)
        env.command_phase = "STOP"
        assert env._obs()[-1] == pytest.approx(-1.0)
    finally:
        env.close()


def test_substep_saturation_profile_preserves_51d_contract_and_reports_500hz_load():
    profile = resolve_profile("stand_start_walk_stop_0p7_substep_saturation_v6")
    factory = make_env(profile.model_dump(), rank=0, seed_base=profile.seed_base)
    env = factory()
    try:
        observation, _ = env.reset(seed=profile.seed_base)
        _, reward, terminated, truncated, info = env.step(np.zeros(12))
    finally:
        env.close()

    assert isinstance(env, HumanoidMotionTaskSubstepSaturationEnv)
    assert observation.shape == (51,)
    assert reward == pytest.approx(float(reward))
    assert isinstance(terminated, bool)
    assert isinstance(truncated, bool)
    assert info["saturation_substeps_total"] == 10
    assert 0 <= info["saturation_substeps_over_threshold"] <= 10
    assert 0.0 <= info["saturation_duty_fraction_500hz"] <= 1.0

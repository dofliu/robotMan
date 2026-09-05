"""Frozen v7 action-interface and profile regression tests."""

import json

import numpy as np
import pytest

from rl.action_interface_v7 import (
    PROTOCOL_PATH,
    load_v7_protocol,
    resolve_v7_action_interface,
)
from rl.eval_policy import evaluate
from rl.humanoid_env import (
    HumanoidMotionTaskFilteredActionV7Env,
    HumanoidMotionTaskReducedJointEnvelopeV7Env,
    HumanoidMotionTaskRewardOnlyV7Env,
    HumanoidMotionTaskSubstepSaturationEnv,
)
from rl.train_ppo import (
    TrainingProfile,
    make_env,
    resolve_profile,
    validate_v7_training_request,
)


V7_PROFILE_CLASSES = [
    (
        "stand_start_walk_stop_0p7_action_reward_v7a",
        HumanoidMotionTaskRewardOnlyV7Env,
        "V7A_REWARD_ONLY",
    ),
    (
        "stand_start_walk_stop_0p7_reduced_joint_envelope_v7b",
        HumanoidMotionTaskReducedJointEnvelopeV7Env,
        "V7B_REDUCED_JOINT_ENVELOPE",
    ),
    (
        "stand_start_walk_stop_0p7_filtered_action_v7c",
        HumanoidMotionTaskFilteredActionV7Env,
        "V7C_FILTERED_ACTION",
    ),
]


def test_protocol_is_strict_and_freezes_exact_three_arm_seed_contract():
    protocol = load_v7_protocol()

    assert [arm["arm_id"] for arm in protocol["arms"]] == [
        item[2] for item in V7_PROFILE_CLASSES
    ]
    assert protocol["evaluation_design"]["evaluation_seeds"] == list(
        range(18000, 18030)
    )
    assert protocol["training_design"]["agent_seed"] == 8700
    assert protocol["training_design"]["requested_timesteps"] == 100_000
    assert protocol["training_design"]["expected_realized_timesteps"] == 122_880
    assert protocol["estimand_and_selection"]["method_level_power_ready"] is False


@pytest.mark.parametrize(
    "mutated",
    [
        '{"schema_version":"V7_ACTION_INTERFACE_PILOT_PROTOCOL_V1",'
        '"schema_version":"V7_ACTION_INTERFACE_PILOT_PROTOCOL_V1"}',
        '{"schema_version":"V7_ACTION_INTERFACE_PILOT_PROTOCOL_V1",'
        '"value":NaN}',
    ],
)
def test_protocol_rejects_duplicate_keys_and_nonfinite_json(tmp_path, mutated):
    path = tmp_path / "protocol.json"
    path.write_text(mutated, encoding="utf-8")

    with pytest.raises(ValueError, match="V7_PROTOCOL_INVALID"):
        load_v7_protocol(path)


@pytest.mark.parametrize(
    "mutator,error",
    [
        (
            lambda payload: payload["training_design"].__setitem__("agent_seed", 8701),
            "V7_PROTOCOL_TRAINING_DESIGN_MISMATCH",
        ),
        (
            lambda payload: payload["task_contract"]["criteria"].__setitem__(
                "saturation_duty_max_pct", 30.1
            ),
            "V7_PROTOCOL_TASK_THRESHOLDS_MISMATCH",
        ),
        (
            lambda payload: payload["joint_order"].reverse(),
            "V7_PROTOCOL_JOINT_ORDER_INVALID",
        ),
    ],
)
def test_protocol_rejects_frozen_design_drift(tmp_path, mutator, error):
    payload = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    mutator(payload)
    path = tmp_path / "protocol.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match=error):
        load_v7_protocol(path)


@pytest.mark.parametrize("profile_id,expected_class,arm_id", V7_PROFILE_CLASSES)
def test_profiles_route_to_exact_frozen_action_interface(
    profile_id,
    expected_class,
    arm_id,
):
    profile = resolve_profile(profile_id)
    factory = make_env(profile.model_dump(), rank=0, seed_base=profile.seed_base)
    env = factory()
    try:
        observation, _ = env.reset(seed=18000)
        contract = env.action_interface_contract()
    finally:
        env.close()

    assert isinstance(env, expected_class)
    assert observation.shape == (51,)
    assert profile.pilot_arm_id == arm_id
    assert contract["pilot_arm_id"] == arm_id
    assert contract["previous_action_semantics"] == (
        "PREVIOUS_APPLIED_NORMALIZED_ACTION"
    )


def test_reward_only_arm_is_step_equivalent_to_v6_direct_interface():
    kwargs = {
        "task_id": "stand_start_walk_stop_v1",
        "speed": 0.7,
        "step_length": 0.35,
        "duty": 0.62,
        "clearance": 0.07,
    }
    baseline = HumanoidMotionTaskSubstepSaturationEnv(**kwargs)
    arm = HumanoidMotionTaskRewardOnlyV7Env(**kwargs)
    try:
        baseline.reset(seed=18000)
        arm.reset(seed=18000)
        action = np.linspace(-0.9, 0.9, 12)
        baseline_step = baseline.step(action)
        arm_step = arm.step(action)
    finally:
        baseline.close()
        arm.close()

    assert np.array_equal(baseline.data.qpos, arm.data.qpos)
    assert np.array_equal(baseline.data.qvel, arm.data.qvel)
    assert baseline_step[1] == pytest.approx(arm_step[1], abs=0.0)
    for key in (
        "saturation_substeps_over_threshold",
        "saturation_substeps_total",
        "saturation_excess_sq_mean_500hz",
        "saturation_duty_fraction_500hz",
    ):
        assert baseline_step[4][key] == pytest.approx(arm_step[4][key], abs=0.0)


def test_reduced_envelope_is_exact_symmetric_hypothesis_vector():
    interface = resolve_v7_action_interface("V7B_REDUCED_JOINT_ENVELOPE")

    assert interface.action_scale_rad == pytest.approx((
        0.5, 0.8, 0.675, 0.45,
        0.5, 0.8, 0.675, 0.45,
        0.45, 0.45, 0.45, 0.45,
    ))
    requested, applied = interface.transform(np.ones(12), np.zeros(12))
    assert requested == pytest.approx(np.ones(12))
    assert applied == pytest.approx(requested)


def test_filtered_arm_observes_applied_state_and_enforces_operator_order():
    interface = resolve_v7_action_interface("V7C_FILTERED_ACTION")
    requested, first = interface.transform(np.ones(12), np.zeros(12))
    _, second = interface.transform(np.ones(12), first)

    assert requested == pytest.approx(np.ones(12))
    assert first == pytest.approx(np.full(12, 0.1))
    assert second == pytest.approx(np.full(12, 0.2))
    assert np.max(np.abs(second - first)) <= 0.1

    env = HumanoidMotionTaskFilteredActionV7Env()
    try:
        env.reset(seed=18000)
        observation, _, _, _, info = env.step(np.ones(12))
    finally:
        env.close()

    assert info["requested_action"] == pytest.approx(np.ones(12))
    assert info["applied_action"] == pytest.approx(np.full(12, 0.1))
    assert observation[35:47] == pytest.approx(info["applied_action"])
    assert info["requested_applied_delta_l2"] > 0.0


@pytest.mark.parametrize(
    "invalid_action,error",
    [
        (np.zeros(11), "ACTION_SHAPE_INVALID"),
        (np.array([0.0] * 11 + [np.nan]), "ACTION_NONFINITE"),
        (np.array([0.0] * 11 + [np.inf]), "ACTION_NONFINITE"),
    ],
)
def test_all_motion_task_actions_fail_closed_before_mujoco(invalid_action, error):
    env = HumanoidMotionTaskSubstepSaturationEnv()
    try:
        env.reset(seed=18000)
        with pytest.raises(ValueError, match=error):
            env.step(invalid_action)
    finally:
        env.close()


def test_v7_profile_rejects_training_seed_or_arm_drift():
    profile = resolve_profile("stand_start_walk_stop_0p7_action_reward_v7a")
    payload = profile.model_dump()
    payload["seed_base"] = 8701
    with pytest.raises(ValueError, match="V7_TRAINING_SEED_OR_ENV_COUNT_MISMATCH"):
        TrainingProfile.model_validate(payload)

    payload = profile.model_dump()
    payload["pilot_arm_id"] = "V7C_FILTERED_ACTION"
    with pytest.raises(ValueError, match="V7_PROFILE_ID_MISMATCH"):
        TrainingProfile.model_validate(payload)


def test_protocol_file_is_the_runtime_single_source_of_truth():
    payload = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    for arm in payload["arms"]:
        resolved = resolve_v7_action_interface(arm["arm_id"])
        assert list(resolved.action_scale_rad) == arm["action_scale_rad"]


def _valid_training_request() -> dict:
    profile = resolve_profile("stand_start_walk_stop_0p7_action_reward_v7a")
    return {
        "profile": profile,
        "run_id": "v7a-reward-only-seed8700-100k-run01",
        "total": 100_000,
        "n_envs": 12,
        "seed_base": 8700,
        "device": "cpu",
        "resume_from": None,
        "warm_start_from": None,
        "smoke": False,
        "preflight": False,
        "source_git": {
            "available": True,
            "git_sha": "a" * 40,
            "working_tree_dirty": False,
            "working_tree_status": [],
        },
    }


@pytest.mark.parametrize(
    "field,value,error",
    [
        ("run_id", "ad-hoc-run", "V7_PILOT_RUN_ID_OVERRIDE_FORBIDDEN"),
        ("device", "cuda", "V7_PILOT_DEVICE_OVERRIDE_FORBIDDEN"),
        ("resume_from", PROTOCOL_PATH, "V7_PILOT_CHECKPOINT_OVERRIDE_FORBIDDEN"),
        ("warm_start_from", PROTOCOL_PATH, "V7_PILOT_CHECKPOINT_OVERRIDE_FORBIDDEN"),
        ("smoke", True, "V7_PILOT_RUN_KIND_OVERRIDE_FORBIDDEN"),
    ],
)
def test_v7_training_request_rejects_cli_drift(field, value, error):
    request = _valid_training_request()
    request[field] = value

    with pytest.raises(ValueError, match=error):
        validate_v7_training_request(**request)


def test_v7_training_request_rejects_dirty_or_unavailable_source_identity():
    request = _valid_training_request()
    request["source_git"]["working_tree_dirty"] = True
    request["source_git"]["working_tree_status"] = ["?? untracked_source.py"]

    with pytest.raises(ValueError, match="V7_PILOT_SOURCE_GIT_NOT_CLEAN"):
        validate_v7_training_request(**request)


def test_v7_training_request_accepts_only_the_exact_frozen_request():
    validate_v7_training_request(**_valid_training_request())


def test_v7_evaluator_rejects_seed_and_policy_path_drift_before_loading(tmp_path):
    fake_policy = tmp_path / "policy.zip"
    fake_policy.write_bytes(b"not-a-policy")
    profile_id = "stand_start_walk_stop_0p7_action_reward_v7a"

    with pytest.raises(
        ValueError,
        match="V7_EVALUATION_SEED_SCHEDULE_OVERRIDE_FORBIDDEN",
    ):
        evaluate(
            fake_policy,
            profile_id,
            29,
            18000,
            pilot_arm_id="V7A_REWARD_ONLY",
        )

    with pytest.raises(ValueError, match="V7_EVALUATION_POLICY_PATH_MISMATCH"):
        evaluate(
            fake_policy,
            profile_id,
            30,
            18000,
            pilot_arm_id="V7A_REWARD_ONLY",
        )

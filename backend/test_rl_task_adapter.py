"""Curriculum-v2 Live adapter 與 frozen training contract 的回歸測試。"""

import numpy as np
import pytest

from config_schema import GaitParams, default_robot
from controller_rl import RLPhaseTaskController, RLTaskController
from rl.humanoid_env import (
    HumanoidMotionTaskCurriculumEnv,
    HumanoidMotionTaskPhaseObservableEnv,
)


def test_live_adapter_observation_matches_training_environment_semantics():
    env = HumanoidMotionTaskCurriculumEnv()
    try:
        env.reset(seed=3700)
        controller = RLTaskController(
            env.model,
            default_robot(),
            GaitParams(speed=0.7, step_length=0.35, duty=0.62, clearance=0.07),
            lean=0.0,
        )
        controller.phase = env.phase = 0.23
        controller.prev_action = env.prev_action = np.linspace(-0.2, 0.2, 12)
        controller._held_command_scale = 0.5
        env.command_speed = 0.35

        live_obs = controller._obs(env.data)
        training_obs = env._obs()
    finally:
        env.close()

    assert live_obs.shape == training_obs.shape == (48,)
    np.testing.assert_allclose(live_obs, training_obs, atol=1e-12, rtol=0.0)
    assert live_obs[-1] == pytest.approx(0.5)


def test_live_adapter_action_envelope_matches_training_formula():
    env = HumanoidMotionTaskCurriculumEnv()
    try:
        controller = RLTaskController(
            env.model,
            default_robot(),
            GaitParams(speed=0.7, step_length=0.35, duty=0.62, clearance=0.07),
            lean=0.0,
        )
        action = np.linspace(-1.0, 1.0, 12)
        scale = 0.4
        actual = controller._target_from_action(action, scale)
        gait_target = env.rl_stand_q + action * env.act_scale
        expected = env.static_stand_q + scale * (gait_target - env.static_stand_q)
    finally:
        env.close()

    np.testing.assert_allclose(actual, expected, atol=1e-12, rtol=0.0)


@pytest.mark.parametrize(
    ("state", "controller_t", "walk_start_t", "training_phase", "expected_trend"),
    [
        ("WALK", 1.0, 0.0, "START", 1.0),
        ("WALK", 2.0, 0.0, "STEADY_WALK", 0.0),
        ("STOPPING", 2.0, 0.0, "STOP", -1.0),
    ],
)
def test_phase_observable_live_adapter_matches_training_observation(
    state, controller_t, walk_start_t, training_phase, expected_trend,
):
    env = HumanoidMotionTaskPhaseObservableEnv()
    try:
        env.reset(seed=6700)
        controller = RLPhaseTaskController(
            env.model,
            default_robot(),
            GaitParams(speed=0.7, step_length=0.35, duty=0.62, clearance=0.07),
            lean=0.0,
        )
        controller.phase = env.phase = 0.23
        controller.prev_action = env.prev_action = np.linspace(-0.2, 0.2, 12)
        controller._held_command_scale = 0.5
        controller.state = state
        controller.t = controller_t
        controller._walk_start_t = walk_start_t
        env.command_speed = 0.35
        env.command_phase = training_phase

        live_obs = controller._obs(env.data)
        training_obs = env._obs()
    finally:
        env.close()

    assert live_obs.shape == training_obs.shape == (51,)
    np.testing.assert_allclose(live_obs, training_obs, atol=1e-12, rtol=0.0)
    assert live_obs[-1] == pytest.approx(expected_trend)

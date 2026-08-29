"""Fixed-speed RL training profile and environment contract tests."""

import pytest

from rl.humanoid_env import HumanoidWalkEnv
from rl.train_ppo import load_profiles, resolve_profile


def test_three_fixed_speed_profiles_are_versioned_and_not_marked_trained():
    profiles = load_profiles()

    assert profiles.schema_version == "RL_TRAINING_PROFILES_V1"
    assert [item.profile_id for item in profiles.profiles] == [
        "walk_0p4_fixed_v1", "walk_0p7_fixed_v1", "walk_1p0_fixed_v1",
    ]
    assert [item.speed_mps for item in profiles.profiles] == pytest.approx([0.4, 0.7, 1.0])
    assert all(item.status == "DEVELOPMENT_PROFILE_NOT_TRAINED" for item in profiles.profiles)


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

"""Runner tests: the shared action interface, a tiny end-to-end train/evaluate, and guards.

The full budget is never run here.  The runner's ``train_cell`` / ``evaluate_cell``
take protocol/design dicts, so a test can pass a reduced copy without the CLI
ever growing an override flag.
"""

from __future__ import annotations

import copy
import importlib.util
import pathlib

import numpy as np
import pytest

import second_case_exposure_contract as sc

HERE = pathlib.Path(__file__).resolve().parent
RUNNER = HERE / "rl" / "second_case_runner.py"

gym = pytest.importorskip("gymnasium")
pytest.importorskip("stable_baselines3")


def _load_runner():
    spec = importlib.util.spec_from_file_location("second_case_runner", RUNNER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def runner():
    return _load_runner()


@pytest.fixture(scope="module")
def protocol():
    return sc.load_protocol()


@pytest.fixture(scope="module")
def design(protocol):
    return sc.validate_protocol(protocol)


def test_runner_has_no_override_flags():
    source = RUNNER.read_text(encoding="utf-8")
    for forbidden in ("--timesteps", "--seed", "--alpha", "--threshold", "--allow-unpinned", "--budget"):
        assert forbidden not in source


def test_plant_and_defaults_match_the_frozen_protocol(runner, protocol, design):
    env = runner.make_env(protocol, design, 1.0)
    assert env.observation_space.shape == (23,)
    assert env.action_space.shape == (6,)
    env.close()


def test_alpha_one_is_the_identity_filter_and_records_saturation(runner, protocol, design):
    recorder = {"raw": [], "applied": [], "saturated": [], "reward": [], "terminated": [], "truncated": []}
    env = runner.make_env(protocol, design, 1.0, recorder)
    obs, _ = env.reset(seed=41000)
    assert obs.shape == (23,) and np.all(obs[17:] == 0.0)
    action = np.array([2.0, -2.0, 0.5, 0.995, -0.99, 0.0])
    obs, _, _, _, _ = env.step(action)
    raw = recorder["raw"][0]
    applied = recorder["applied"][0]
    assert np.array_equal(raw, np.array([1.0, -1.0, 0.5, 0.995, -0.99, 0.0]))
    assert np.array_equal(applied, raw)
    assert recorder["saturated"][0].tolist() == [True, True, False, True, True, False]
    assert np.array_equal(obs[17:], applied)  # previous applied action is in the observation
    env.close()


def test_alpha_quarter_follows_the_frozen_recursion_exactly(runner, protocol, design):
    recorder = {"raw": [], "applied": [], "saturated": [], "reward": [], "terminated": [], "truncated": []}
    env = runner.make_env(protocol, design, 0.25, recorder)
    env.reset(seed=41001)
    prev = np.zeros(6)
    for step in range(5):
        action = np.full(6, 1.0 if step % 2 == 0 else -1.0)
        env.step(action)
        expected = 0.25 * np.clip(action, -1, 1) + 0.75 * prev
        assert np.array_equal(recorder["applied"][-1], expected)
        prev = expected
    # After five alternating steps the filtered action is far from the bounds: no saturation.
    assert not recorder["saturated"][-1].any()
    env.close()


def test_filter_state_resets_to_zero(runner, protocol, design):
    env = runner.make_env(protocol, design, 0.25)
    env.reset(seed=41002)
    env.step(np.ones(6))
    obs, _ = env.reset(seed=41003)
    assert np.all(obs[17:] == 0.0)
    env.close()


def test_tiny_end_to_end_cell_produces_contract_valid_rows(runner, protocol, design, tmp_path):
    small_protocol = copy.deepcopy(protocol)
    small_protocol["training"]["requested_timesteps"] = 2048
    small_protocol["training"]["expected_realized_timesteps"] = 2048
    small_design = dict(design)
    small_design["expected_realized_timesteps"] = 2048
    small_design["evaluation_seeds"] = design["evaluation_seeds"][:2]

    policy_path = tmp_path / "policy.zip"
    training = runner.train_cell(small_protocol, small_design, 0.25, training_seed=design["training_seeds"][0], policy_path=policy_path)
    assert training["realized_timesteps"] == 2048
    assert policy_path.is_file() and training["policy_sha256"].startswith("sha256:")

    rows = runner.evaluate_cell(small_protocol, small_design, 0.25, policy_path, tmp_path / "traces")
    assert [row["evaluation_seed"] for row in rows] == small_design["evaluation_seeds"]
    for row in rows:
        # Every row reproduces from its own counts through the contract (SC-03).
        rebuilt = sc.episode_row(
            evaluation_seed=row["evaluation_seed"],
            realized_steps=row["realized_steps"],
            saturated_joint_steps=row["saturated_joint_steps"],
            terminated=row["terminated"],
            truncated=row["truncated"],
            all_finite=row["all_finite"],
            episode_return=row["episode_return"],
            trace_sha256=row["trace_sha256"],
            design=small_design,
        )
        assert rebuilt == row
        assert 1 <= row["realized_steps"] <= 1000
        assert row["exposure_class"] in ("FULL_EXPOSURE", "EARLY_TERMINATED")
        # Trace file digest is bound to the row.
        trace = tmp_path / "traces" / f"seed_{row['evaluation_seed']}.npz"
        assert runner.sha256_file(trace) == row["trace_sha256"]
        with np.load(trace) as data:
            assert data["applied_action"].shape == (row["realized_steps"], 6)
            assert int(data["saturated_joint_flags"].sum()) == row["saturated_joint_steps"]
            # Exposure was derived from length, and length agrees with the flags' story.
            assert bool(data["terminated"][-1]) == row["terminated"]
            assert bool(data["truncated"][-1]) == row["truncated"]


def test_training_is_deterministic_for_a_fixed_seed(runner, protocol, design, tmp_path):
    small_protocol = copy.deepcopy(protocol)
    small_protocol["training"]["requested_timesteps"] = 2048
    small_protocol["training"]["expected_realized_timesteps"] = 2048
    small_design = dict(design)
    small_design["expected_realized_timesteps"] = 2048
    a = runner.train_cell(small_protocol, small_design, 1.0, training_seed=40000, policy_path=tmp_path / "a.zip")
    b = runner.train_cell(small_protocol, small_design, 1.0, training_seed=40000, policy_path=tmp_path / "b.zip")
    from stable_baselines3 import PPO

    pa = PPO.load(tmp_path / "a.zip", device="cpu").policy.state_dict()
    pb = PPO.load(tmp_path / "b.zip", device="cpu").policy.state_dict()
    assert all(np.array_equal(pa[k].numpy(), pb[k].numpy()) for k in pa)
    assert a["realized_timesteps"] == b["realized_timesteps"] == 2048


def test_git_identity_reports_the_repository(runner):
    identity = runner.git_source_identity()
    assert identity["available"] is True
    assert isinstance(identity["working_tree_dirty"], bool)
    assert len(identity["git_sha"]) == 40

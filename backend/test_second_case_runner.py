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


# --------------------------------------------------------------------------- #
# V2 budget probe (pilot): validation and a tiny compute loop
# --------------------------------------------------------------------------- #

PROBE = HERE / "rl" / "second_case_budget_probe.py"


def _load_probe_module():
    spec = importlib.util.spec_from_file_location("second_case_budget_probe", PROBE)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_probe_protocol_validates_against_the_pinned_v1(protocol, design):
    probe_mod = _load_probe_module()
    probe = probe_mod.load_probe()
    pdesign = probe_mod.validate_probe(probe, protocol, design)
    assert pdesign["arm_id"] == design["reference_arm_id"] and pdesign["alpha"] == 1.0
    assert pdesign["training_seed"] == 42000 and pdesign["evaluation_seeds"] == list(range(43000, 43030))
    assert pdesign["interval"] == 245760 and pdesign["max_checkpoints"] == 12 and pdesign["minimum_full"] == 27
    # Probe seeds are disjoint from V1, sealed v7 ranges, and the planned V2 ranges.
    for lo, hi in list(probe["forbidden_seed_ranges"].values()) + list(probe["planned_v2_seed_ranges"].values()):
        assert not any(lo <= s <= hi for s in pdesign["evaluation_seeds"] + [pdesign["training_seed"]])


def test_probe_refuses_a_candidate_arm_or_reused_seeds(protocol, design):
    probe_mod = _load_probe_module()
    probe = probe_mod.load_probe()
    bad = copy.deepcopy(probe)
    bad["arm_id"] = design["candidate_arm_id"]
    with pytest.raises(probe_mod.ProbeError):
        probe_mod.validate_probe(bad, protocol, design)
    bad = copy.deepcopy(probe)
    bad["training_seed"] = 40001  # a V1 training seed
    with pytest.raises(probe_mod.ProbeError):
        probe_mod.validate_probe(bad, protocol, design)
    bad = copy.deepcopy(probe)
    bad["max_checkpoints"] = 13  # raising the max must also break the cumulative pin
    with pytest.raises(probe_mod.ProbeError):
        probe_mod.validate_probe(bad, protocol, design)


def test_probe_tiny_loop_records_checkpoints_and_applies_the_rule(protocol, design, tmp_path):
    probe_mod = _load_probe_module()
    pdesign = {
        "arm_id": design["reference_arm_id"],
        "alpha": 1.0,
        "training_seed": 42000,
        "evaluation_seeds": [43000, 43001],
        "interval": 2048,
        "max_checkpoints": 2,
        "minimum_full": 1,
    }
    result = probe_mod.probe_training_loop(protocol, design, pdesign, tmp_path / "ckpt")
    assert len(result["checkpoints"]) == 2
    assert [c["cumulative_timesteps"] for c in result["checkpoints"]] == [2048, 4096]
    for c in result["checkpoints"]:
        assert c["full_exposure_count"] + c["early_terminated_count"] == 2
        assert (tmp_path / "ckpt" / f"checkpoint_{c['checkpoint_index']:02d}_{c['cumulative_timesteps']}.zip").is_file()
    # 4096 steps of PPO do not keep a Walker2d up: the rule cannot select a budget here.
    assert result["outcome"] in (probe_mod.OUTCOME_NEGATIVE, probe_mod.OUTCOME_FOUND)
    if result["outcome"] == probe_mod.OUTCOME_NEGATIVE:
        assert result["selected_budget_timesteps"] is None
    else:
        assert result["selected_budget_timesteps"] == 4096


# --------------------------------------------------------------------------- #
# recipe support: policy kwargs and VecNormalize round trip
# --------------------------------------------------------------------------- #

TUNED = {
    "hyperparameters": {"learning_rate": 5.05041e-05, "n_steps": 512, "batch_size": 32, "n_epochs": 2, "gamma": 0.99, "gae_lambda": 0.95, "clip_range": 0.1, "ent_coef": 0.000585045, "vf_coef": 0.871923, "max_grad_norm": 1.0, "normalize_advantage": True},
    "normalize": {"norm_obs": True, "norm_reward": True, "clip_obs": 10.0},
    "policy_kwargs": {"log_std_init": -2.0, "ortho_init": False, "activation_fn": "ReLU", "net_arch": {"pi": [64, 64], "vf": [64, 64]}},
}


def test_tuned_recipe_trains_saves_normalizer_and_evaluates_through_it(runner, protocol, design, tmp_path):
    tuned = copy.deepcopy(protocol)
    tuned["training"].update(copy.deepcopy(TUNED))
    tuned["training"]["requested_timesteps"] = 2048
    tuned["training"]["expected_realized_timesteps"] = 2048
    small_design = dict(design)
    small_design["expected_realized_timesteps"] = 2048
    small_design["evaluation_seeds"] = design["evaluation_seeds"][:2]
    policy_path = tmp_path / "policy.zip"
    training = runner.train_cell(tuned, small_design, 1.0, training_seed=46000, policy_path=policy_path)
    assert training["realized_timesteps"] == 2048
    assert training["normalizer_sha256"] is not None
    assert runner.normalizer_path_for(policy_path).is_file()
    rows = runner.evaluate_cell(tuned, small_design, 1.0, policy_path, tmp_path / "traces")
    assert len(rows) == 2
    for row in rows:
        assert 1 <= row["realized_steps"] <= 1000
        # recorder sits below VecNormalize: rewards and actions are raw env-level values
        with np.load(tmp_path / "traces" / f"seed_{row['evaluation_seed']}.npz") as data:
            assert np.all(np.abs(data["applied_action"]) <= 1.0)


def test_default_recipe_records_no_normalizer(runner, protocol, design, tmp_path):
    small = copy.deepcopy(protocol)
    small["training"]["requested_timesteps"] = 2048
    small["training"]["expected_realized_timesteps"] = 2048
    small_design = dict(design)
    small_design["expected_realized_timesteps"] = 2048
    training = runner.train_cell(small, small_design, 1.0, training_seed=40000, policy_path=tmp_path / "p.zip")
    assert training["normalizer_sha256"] is None
    assert not runner.normalizer_path_for(tmp_path / "p.zip").exists()


def test_build_model_applies_policy_kwargs(runner, protocol, design):
    import torch.nn as nn
    from stable_baselines3.common.vec_env import DummyVecEnv

    tuned = copy.deepcopy(protocol["training"])
    tuned.update(copy.deepcopy(TUNED))
    vec = DummyVecEnv([lambda: runner.make_env(protocol, design, 1.0)])
    vec, normalized = runner.wrap_normalizer(tuned, vec)
    assert normalized
    model = runner.build_model(tuned, vec, 1)
    assert model.n_steps == 512 and model.batch_size == 32
    assert isinstance(model.policy.mlp_extractor.policy_net[1], nn.ReLU)
    vec.close()


def test_probe_v2_recipe_override_is_validated_and_effective(protocol, design):
    probe_mod = _load_probe_module()
    path = HERE / "rl" / "second_case_v2_budget_probe_v2.json"
    if not path.exists():
        pytest.skip("probe V2 not written yet")
    probe = probe_mod.load_probe(path)
    pdesign = probe_mod.validate_probe(probe, protocol, design)
    assert pdesign["training"]["hyperparameters"]["n_steps"] == 512
    assert pdesign["training"]["normalize"]["norm_obs"] is True
    assert pdesign["interval"] % 512 == 0
    assert pdesign["training_seed"] == 46000 and pdesign["evaluation_seeds"] == list(range(47000, 47030))
    bad = copy.deepcopy(probe)
    bad["recipe_override"]["device"] = "cuda"
    with pytest.raises(probe_mod.ProbeError, match="may not set"):
        probe_mod.validate_probe(bad, protocol, design)

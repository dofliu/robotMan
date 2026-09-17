"""Tests for ``TEACHING-BOUNDARY-V1`` and the read-only training inventory.

Two things have to hold for the teaching split to be real rather than asserted.

The boundary has to be clean *and* checked: the teaching application's import
closure must contain no research module, and the check must fail when one
appears. The decisive negative test rebuilds the state this repository was in
before 2026-09-17 -- ``main.py`` importing ``public_training_inventory`` from
``rl/train_ppo.py`` -- and requires the contract to catch it.

The cut has to be behaviour-preserving: the new read-only inventory must serve
the byte-identical payload the training driver served, key order included,
otherwise the split silently changed the API.
"""

from __future__ import annotations

import io
import json
import os
import shutil
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import teaching_boundary_contract as tbc  # noqa: E402
from rl import training_inventory  # noqa: E402

REPO_ROOT = tbc.REPO_ROOT


# --------------------------------------------------------------------------
# the boundary as it stands
# --------------------------------------------------------------------------

def test_registry_loads_and_is_well_formed():
    registry = tbc.load_registry()
    assert registry["registry_id"] == "TEACHING-BOUNDARY-V1"
    assert registry["entry_points"] == ["main"]


def test_teaching_closure_is_clean():
    summary = tbc.verify()
    assert summary["result"] == "TEACHING_BOUNDARY_CLEAN"
    assert summary["modules"] >= 10


def test_no_research_module_is_reachable_from_the_application():
    """The property in its own right, independent of the registry's contents."""
    registry = tbc.load_registry()
    reached = set(tbc.closure(registry))
    forbidden = {
        "rl.train_ppo", "rl.eval_policy", "rl.humanoid_env", "rl.action_interface_v7",
        "rl.second_case_runner", "rl.bind_run_lock",
        "v7_pilot_contract", "v7_exposure_audit_contract", "second_case_exposure_contract",
        "training_seed_variance_contract", "tracked_lineage_contract",
        "paired_statistics_contract", "experiment_matrix_contract", "paper_data_contract",
        "environment_lock", "run_manifest_lock", "exposure_identification",
    }
    assert not (reached & forbidden), sorted(reached & forbidden)


def test_the_two_rl_modules_in_the_closure_are_the_teaching_ones():
    registry = tbc.load_registry()
    reached = sorted(m for m in tbc.closure(registry) if m.startswith("rl."))
    assert reached == ["rl.policy_registry", "rl.training_inventory"]


def test_imports_are_read_statically_not_by_importing():
    """A function-local import still counts: reachability, not one code path."""
    source = io.open(os.path.join(REPO_ROOT, "backend/teaching_boundary_contract.py"),
                     encoding="utf-8").read()
    assert "ast.parse" in source
    assert "importlib" not in source


# --------------------------------------------------------------------------
# the failure this boundary exists for, replayed
# --------------------------------------------------------------------------

@pytest.fixture
def tree(tmp_path):
    """A copy of backend/ without the heavy evidence directories."""
    root = tmp_path / "repo"
    shutil.copytree(os.path.join(REPO_ROOT, "backend"), root / "backend",
                    ignore=shutil.ignore_patterns("__pycache__", "artifacts", "*_evidence",
                                                  "run_traces", "*.zip", "*.npz"))
    return str(root)


def test_clean_copy_passes(tree):
    assert tbc.verify(tbc.REGISTRY_PATH, tree)["result"] == "TEACHING_BOUNDARY_CLEAN"


def test_the_import_that_was_cut_is_caught(tree):
    """Before 2026-09-17 main.py took its inventory from the training driver."""
    path = os.path.join(tree, "backend", "main.py")
    text = io.open(path, encoding="utf-8").read()
    assert "from rl.training_inventory import public_training_inventory" in text
    io.open(path, "w", encoding="utf-8").write(text.replace(
        "from rl.training_inventory import public_training_inventory",
        "from rl.train_ppo import public_training_inventory"))
    with pytest.raises(tbc.TeachingBoundaryError) as caught:
        tbc.verify(tbc.REGISTRY_PATH, tree)
    message = str(caught.value)
    assert "RESEARCH_MODULE_IN_TEACHING_CLOSURE" in message
    assert "rl.train_ppo" in message
    # and it names how the research module was reached, not merely that it was
    assert "main -> rl.train_ppo" in message


def test_a_new_research_import_anywhere_in_the_closure_is_caught(tree):
    """Not only the entry point: a deep module pulling research in fails too."""
    path = os.path.join(tree, "backend", "controller.py")
    text = io.open(path, encoding="utf-8").read()
    io.open(path, "w", encoding="utf-8").write(
        "import environment_lock  # noqa: F401\n" + text)
    with pytest.raises(tbc.TeachingBoundaryError) as caught:
        tbc.verify(tbc.REGISTRY_PATH, tree)
    message = str(caught.value)
    assert "environment_lock" in message
    # the trail is reported from the entry point, however deep the module sits
    assert "reached by main ->" in message
    assert message.count("controller -> environment_lock") == 1


def test_a_function_local_research_import_is_caught(tree):
    """Hiding the import inside a function does not hide it from the check."""
    path = os.path.join(tree, "backend", "motion_tasks.py")
    text = io.open(path, encoding="utf-8").read()
    io.open(path, "w", encoding="utf-8").write(
        text + "\n\ndef _later():\n    from v7_pilot_contract import *  # noqa: F401,F403\n")
    with pytest.raises(tbc.TeachingBoundaryError) as caught:
        tbc.verify(tbc.REGISTRY_PATH, tree)
    assert "v7_pilot_contract" in str(caught.value)


def test_a_stale_registry_entry_is_caught(tree):
    """An allowlist nothing loads would let a module back in unnoticed."""
    registry = tbc.load_registry()
    registry["teaching_modules"] = sorted(registry["teaching_modules"] + ["vv_oracles"])
    path = os.path.join(tree, "registry.json")
    io.open(path, "w", encoding="utf-8").write(json.dumps(registry, ensure_ascii=False))
    with pytest.raises(tbc.TeachingBoundaryError) as caught:
        tbc.verify(path, tree)
    assert "STALE_REGISTRY_ENTRY" in str(caught.value)
    assert "vv_oracles" in str(caught.value)


def test_entry_point_outside_the_module_list_is_rejected(tmp_path):
    registry = tbc.load_registry()
    registry["entry_points"] = ["not_a_teaching_module"]
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(registry, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(tbc.TeachingBoundaryError, match="not itself a registered"):
        tbc.load_registry(str(path))


# --------------------------------------------------------------------------
# the cut has to be behaviour-preserving
# --------------------------------------------------------------------------

def test_inventory_payload_is_identical_to_the_driver_s():
    """Exact equality, key order included: the split changed no API byte."""
    from rl.train_ppo import public_training_inventory as from_driver
    served = training_inventory.public_training_inventory()
    assert json.dumps(served, ensure_ascii=False) == \
        json.dumps(from_driver(), ensure_ascii=False)


def test_inventory_is_read_only_and_explicit():
    body = training_inventory.public_training_inventory()
    assert body["execution_mode"] == "OFFLINE_EXPLICIT_COMMAND_ONLY"
    assert body["schema_version"] == "RL_TRAINING_PROFILES_V4"
    assert len(body["profiles"]) == 25


def test_inventory_needs_no_site_packages():
    """It must run under python -I -S, so the boundary holds for a thin install."""
    source = io.open(os.path.join(REPO_ROOT, "backend/rl/training_inventory.py"),
                     encoding="utf-8").read()
    for banned in ("pydantic", "stable_baselines3", "gymnasium", "numpy", "torch"):
        assert f"import {banned}" not in source, banned


def test_main_serves_the_inventory_from_the_teaching_module():
    source = io.open(os.path.join(REPO_ROOT, "backend/main.py"), encoding="utf-8").read()
    assert "from rl.training_inventory import public_training_inventory" in source
    assert "from rl.train_ppo import" not in source


@pytest.mark.parametrize("mutate,expected", [
    (lambda d: d["profiles"][0].pop("speed_mps"), "missing required field"),
    (lambda d: d["profiles"][0].update(speed_mps="fast"), "expected float"),
    (lambda d: d["profiles"][0].update(planned_timesteps=True), "is a bool"),
    (lambda d: d["profiles"][0].update(surprise=1), "unknown field"),
    (lambda d: d.update(profiles=[]), "non-empty list"),
    (lambda d: d.pop("schema_version"), "missing or empty"),
])
def test_inventory_fails_closed_on_a_malformed_profile_file(tmp_path, mutate, expected):
    raw = json.loads(io.open(training_inventory.PROFILE_PATH, encoding="utf-8").read())
    mutate(raw)
    path = tmp_path / "training_profiles.json"
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(training_inventory.TrainingInventoryError, match=expected):
        training_inventory.public_training_inventory(path)


def test_duplicate_profile_id_is_rejected(tmp_path):
    raw = json.loads(io.open(training_inventory.PROFILE_PATH, encoding="utf-8").read())
    raw["profiles"].append(dict(raw["profiles"][0]))
    path = tmp_path / "training_profiles.json"
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(training_inventory.TrainingInventoryError, match="duplicate profile_id"):
        training_inventory.public_training_inventory(path)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def test_cli_reports_a_clean_boundary():
    assert tbc.main([]) == 0


def test_cli_list_prints_the_closure(capsys):
    assert tbc.main(["--list"]) == 0
    printed = capsys.readouterr().out
    assert "main" in printed and "TOTAL" in printed
    assert "train_ppo" not in printed


def test_cli_returns_nonzero_on_a_violation(tree, capsys):
    path = os.path.join(tree, "backend", "gait.py")
    text = io.open(path, encoding="utf-8").read()
    io.open(path, "w", encoding="utf-8").write("import paper_data_contract  # noqa: F401\n" + text)
    assert tbc.main(["--registry", tbc.REGISTRY_PATH, "--repo-root", tree]) == 1
    assert "TEACHING BOUNDARY CHECK FAILED" in capsys.readouterr().err

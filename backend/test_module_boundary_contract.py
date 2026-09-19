"""Tests for ``MODULE-BOUNDARY-V1`` and the read-only training inventory.

``PROJECT_ASSESSMENT`` section 4.1 proposes two products, and each proposal is a
claim about imports. One contract checks both, by one rule, because copying the
rule for the second product would have reproduced the failure this repository
spent two contracts learning to catch: one fact, two implementations.

The teaching boundary has to be clean *and* checked: the application's import
closure must contain no research module, and the check must fail when one
appears. The decisive negative test rebuilds the state this repository was in
before 2026-09-17 -- ``main.py`` importing ``public_training_inventory`` from
``rl/train_ppo.py`` -- and requires the contract to catch it.

The toolkit boundary points the other way: the *library* must not reach into the
project at all. That is strictly stronger than the teaching property, and it is
measured true, so the tests pin both halves of the asymmetry -- the toolkit
reaches nothing, while the project reaches it from thirteen places.

Two things the tests deliberately do not claim. A clean toolkit boundary is not
portability: ``test_the_boundary_is_not_a_portability_claim`` exists to keep the
green light from being read as one. And the teaching cut has to be
behaviour-preserving, so the new read-only inventory must serve the
byte-identical payload the training driver served, key order included.
"""

from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import module_boundary_contract as mbc  # noqa: E402
from rl import training_inventory  # noqa: E402

REPO_ROOT = mbc.REPO_ROOT


# --------------------------------------------------------------------------
# the boundary as it stands
# --------------------------------------------------------------------------

def test_registry_loads_and_is_well_formed():
    registry = mbc.load_registry()
    assert registry["registry_id"] == "MODULE-BOUNDARY-V1"
    assert sorted(registry["boundaries"]) == ["teaching", "toolkit"]
    assert registry["boundaries"]["teaching"]["entry_points"] == ["main"]


def test_every_declared_boundary_is_clean():
    summary = mbc.verify()
    assert summary["result"] == "MODULE_BOUNDARIES_CLEAN"
    assert summary["boundaries"]["teaching"]["modules"] >= 10
    assert summary["boundaries"]["toolkit"]["modules"] == 7


def test_no_research_module_is_reachable_from_the_application():
    """The property in its own right, independent of the registry's contents."""
    registry = mbc.load_registry()
    reached = set(mbc.closure(registry, "teaching"))
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
    registry = mbc.load_registry()
    reached = sorted(m for m in mbc.closure(registry, "teaching") if m.startswith("rl."))
    assert reached == ["rl.policy_registry", "rl.training_inventory"]


def test_imports_are_read_statically_not_by_importing():
    """A function-local import still counts: reachability, not one code path."""
    source = io.open(os.path.join(REPO_ROOT, "backend/module_boundary_contract.py"),
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
    assert mbc.verify(mbc.REGISTRY_PATH, tree)["result"] == "MODULE_BOUNDARIES_CLEAN"


def test_the_import_that_was_cut_is_caught(tree):
    """Before 2026-09-17 main.py took its inventory from the training driver."""
    path = os.path.join(tree, "backend", "main.py")
    text = io.open(path, encoding="utf-8").read()
    assert "from rl.training_inventory import public_training_inventory" in text
    io.open(path, "w", encoding="utf-8").write(text.replace(
        "from rl.training_inventory import public_training_inventory",
        "from rl.train_ppo import public_training_inventory"))
    with pytest.raises(mbc.ModuleBoundaryError) as caught:
        mbc.verify(mbc.REGISTRY_PATH, tree)
    message = str(caught.value)
    assert "MODULE_OUTSIDE_BOUNDARY" in message
    assert "rl.train_ppo" in message
    # and it names how the research module was reached, not merely that it was
    assert "main -> rl.train_ppo" in message


def test_a_new_research_import_anywhere_in_the_closure_is_caught(tree):
    """Not only the entry point: a deep module pulling research in fails too."""
    path = os.path.join(tree, "backend", "controller.py")
    text = io.open(path, encoding="utf-8").read()
    io.open(path, "w", encoding="utf-8").write(
        "import environment_lock  # noqa: F401\n" + text)
    with pytest.raises(mbc.ModuleBoundaryError) as caught:
        mbc.verify(mbc.REGISTRY_PATH, tree)
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
    with pytest.raises(mbc.ModuleBoundaryError) as caught:
        mbc.verify(mbc.REGISTRY_PATH, tree)
    assert "v7_pilot_contract" in str(caught.value)


def test_a_stale_registry_entry_is_caught(tree):
    """An allowlist nothing loads would let a module back in unnoticed."""
    registry = mbc.load_registry()
    registry["boundaries"]["teaching"]["modules"] = sorted(
        registry["boundaries"]["teaching"]["modules"] + ["vv_oracles"])
    path = os.path.join(tree, "registry.json")
    io.open(path, "w", encoding="utf-8").write(json.dumps(registry, ensure_ascii=False))
    with pytest.raises(mbc.ModuleBoundaryError) as caught:
        mbc.verify(path, tree)
    assert "STALE_REGISTRY_ENTRY" in str(caught.value)
    assert "vv_oracles" in str(caught.value)


def test_entry_point_outside_the_module_list_is_rejected(tmp_path):
    registry = mbc.load_registry()
    registry["boundaries"]["teaching"]["entry_points"] = ["not_a_teaching_module"]
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(registry, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(mbc.ModuleBoundaryError, match="not one of its own modules"):
        mbc.load_registry(str(path))


# --------------------------------------------------------------------------
# the toolkit boundary: the same rule, pointing the other way
# --------------------------------------------------------------------------

def test_the_toolkit_closure_is_exactly_its_seven_modules():
    """The library reaches nothing beyond itself -- no project module at all."""
    registry = mbc.load_registry()
    reached = sorted(mbc.closure(registry, "toolkit"))
    assert reached == sorted(registry["boundaries"]["toolkit"]["modules"])
    assert reached == [
        "environment_lock", "experiment_matrix_contract", "exposure_identification",
        "paired_statistics_contract", "paper_data_contract", "rl.bind_run_lock",
        "run_manifest_lock",
    ]


def test_the_two_boundaries_share_no_module():
    """A module on both sides would make either boundary meaningless."""
    registry = mbc.load_registry()
    teaching = set(mbc.closure(registry, "teaching"))
    toolkit = set(mbc.closure(registry, "toolkit"))
    assert not (teaching & toolkit), sorted(teaching & toolkit)


def test_the_dependency_runs_from_the_project_to_the_toolkit_not_back():
    """The asymmetry is the point: many depend on it, it depends on none.

    Thirteen non-test project modules imported a toolkit module on 2026-09-17.
    The floor is asserted rather than the exact count, because a new bundle
    script is a legitimate fourteenth and must not turn this red; a collapse to
    single digits means the registry's note has gone stale.
    """
    registry = mbc.load_registry()
    toolkit = set(registry["boundaries"]["toolkit"]["modules"])
    root = os.path.join(REPO_ROOT, registry["package_root"])

    dependents = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in ("__pycache__", "artifacts", "run_traces")]
        for filename in sorted(filenames):
            if not filename.endswith(".py") or filename.startswith("test_"):
                continue
            relative = os.path.relpath(os.path.join(dirpath, filename), root)
            module = relative[: -len(".py")].replace(os.sep, ".")
            if module in toolkit:
                continue
            if mbc.imported_names(os.path.join(dirpath, filename)) & toolkit:
                dependents.append(module)

    assert len(dependents) >= 10, dependents
    assert "rl.second_case_runner" in dependents


def test_a_toolkit_module_reaching_into_the_project_is_caught(tree):
    """The failure this boundary exists for, in the toolkit's direction."""
    path = os.path.join(tree, "backend", "exposure_identification.py")
    text = io.open(path, encoding="utf-8").read()
    io.open(path, "w", encoding="utf-8").write(
        "import v7_pilot_contract  # noqa: F401\n" + text)
    with pytest.raises(mbc.ModuleBoundaryError) as caught:
        mbc.verify(mbc.REGISTRY_PATH, tree)
    message = str(caught.value)
    assert "[toolkit]" in message
    assert "MODULE_OUTSIDE_BOUNDARY: v7_pilot_contract" in message
    assert "reached by exposure_identification -> v7_pilot_contract" in message


def test_a_toolkit_module_importing_a_teaching_module_is_caught(tree):
    """Reaching sideways into the other product fails as surely as reaching up."""
    path = os.path.join(tree, "backend", "run_manifest_lock.py")
    text = io.open(path, encoding="utf-8").read()
    io.open(path, "w", encoding="utf-8").write("import simulator  # noqa: F401\n" + text)
    with pytest.raises(mbc.ModuleBoundaryError) as caught:
        mbc.verify(mbc.REGISTRY_PATH, tree)
    assert "[toolkit]" in str(caught.value)
    assert "simulator" in str(caught.value)


def test_the_boundary_is_not_a_portability_claim():
    """A green light here says nothing about whether an outsider can use it.

    Measured 2026-09-17 and recorded in docs/TOOLKIT_PORTABILITY.md: the closure
    is clean while closed ``Literal`` vocabularies still bind three modules to
    this project's frozen claim boundary. The registry has to keep saying so,
    otherwise the clean result reads as "reusable today", which it is not.
    """
    registry = mbc.load_registry()
    note = registry["boundaries"]["toolkit"]["notes"]["portability_is_separate"]
    assert "docs/TOOLKIT_PORTABILITY.md" in note
    assert os.path.exists(os.path.join(REPO_ROOT, "docs/TOOLKIT_PORTABILITY.md"))
    source = io.open(os.path.join(REPO_ROOT, "backend/module_boundary_contract.py"),
                     encoding="utf-8").read()
    assert "does NOT check is portability" in source


# --------------------------------------------------------------------------
# docs/TOOLKIT_USAGE.md tells outsiders to vendor exactly three files
# --------------------------------------------------------------------------
#
# That guide's sections 1 and 2 name three modules and say that copying them
# into one directory on sys.path is enough. It is the claim most likely to rot
# silently: one added cross-import inside any of the three and the instruction
# becomes false with nothing to say so. So it is checked here rather than
# asserted there.

VENDORED = ("exposure_identification.py", "environment_lock.py", "run_manifest_lock.py")


def _vendor(tmp_path):
    kit = tmp_path / "lockkit"
    kit.mkdir()
    for name in VENDORED:
        shutil.copyfile(os.path.join(REPO_ROOT, "backend", name), kit / name)
    return kit


def test_the_usage_guide_vendor_list_is_self_contained(tmp_path):
    """Exactly the three named files, copied out, import each other and nothing else."""
    kit = _vendor(tmp_path)
    script = (
        "import sys; sys.path.insert(0, %r);\n"
        "import exposure_identification, environment_lock, run_manifest_lock;\n"
        "leaked = [m for m in ('numpy','torch','mujoco','pydantic','gymnasium','fastapi')\n"
        "          if m in sys.modules];\n"
        "print('LEAKED' if leaked else 'CLEAN', leaked)\n"
    ) % str(kit)
    completed = subprocess.run(
        [sys.executable, "-I", "-S", "-c", script], capture_output=True, text=True
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.startswith("CLEAN"), completed.stdout


def test_the_usage_guide_flow_produces_the_labels_it_promises(tmp_path):
    """Section 4.1's table, run from a vendored copy with no site-packages.

    Three of its four rows need no heavy packages and are asserted here. The
    fourth (RUN_LOCK_BOUND) requires numpy/torch/mujoco to be installed, which
    is the guide's section 4.2 point rather than an omission: a lock that did
    not measure the RL stack reports PARTIAL_LOCK, and the gate then says
    RUN_LOCK_INSUFFICIENT rather than BOUND.
    """
    kit = _vendor(tmp_path)
    run_dir = tmp_path / "runs" / "exp-001"
    run_dir.mkdir(parents=True)

    script = r"""
import json, sys
from pathlib import Path
sys.path.insert(0, %r)
import run_manifest_lock as rml

root, run = Path(%r), Path(%r)
rml.CLAIM_BOUNDARY = "An outside project's own boundary, validated as text rather than by equality."
cap = rml.capture_lock_for_run(run)
(run / "run_manifest.json").write_text(
    json.dumps({"schema_version": "MY_RUN_MANIFEST_V1", "run_id": "exp-001"}, indent=1) + "\n",
    encoding="utf-8")
record = rml.build_binding_record(
    root=root, manifest_path=run / "run_manifest.json",
    manifest_schema_version="MY_RUN_MANIFEST_V1",
    lock_record_path=cap["lock_record_path"],
    binding_mode=rml.MODE_SIDECAR_ONLY,
    sidecar_reason="an outside project's own reason",
    verified_before_run=cap["verified_before_run"],
    lock_verified_at_utc=cap["lock_verified_at_utc"])
rml.write_binding_record(run, record)
print("claim_boundary_is_mine", record["claim_boundary"].startswith("An outside project"))
print("no_packages", rml.evaluate_run(run, "run_manifest.json", root=root)["label"])

manifest = run / "run_manifest.json"
manifest.write_text(manifest.read_text(encoding="utf-8").replace("exp-001", "exp-XXX"),
                    encoding="utf-8")
print("tampered", rml.evaluate_run(run, "run_manifest.json", root=root)["label"])

manifest.write_text(manifest.read_text(encoding="utf-8").replace("exp-XXX", "exp-001"),
                    encoding="utf-8")
(run / "environment_lock.json").unlink()
print("lock_deleted", rml.evaluate_run(run, "run_manifest.json", root=root)["label"])
""" % (str(kit), str(tmp_path), str(run_dir))

    completed = subprocess.run(
        [sys.executable, "-I", "-S", "-c", script], capture_output=True, text=True
    )
    assert completed.returncode == 0, completed.stderr
    printed = dict(line.split(maxsplit=1) for line in completed.stdout.strip().splitlines())
    import run_manifest_lock as rml
    # the guide tells outsiders they may supply their own claim boundary
    assert printed["claim_boundary_is_mine"] == "True", completed.stdout
    # section 4.2: without the RL stack the lock is PARTIAL, so the gate withholds BOUND
    assert printed["no_packages"] == rml.LABEL_INSUFFICIENT, completed.stdout
    assert printed["tampered"] == rml.LABEL_MISMATCH, completed.stdout
    assert printed["lock_deleted"] == rml.LABEL_METHOD_FAILURE, completed.stdout


def test_the_usage_guide_names_only_modules_inside_the_toolkit_boundary():
    """The guide must not send an outsider to a module outside the toolkit boundary."""
    toolkit = set(mbc.load_registry()["boundaries"]["toolkit"]["modules"])
    for name in VENDORED:
        assert name[: -len(".py")] in toolkit, name


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
    assert mbc.main([]) == 0


def test_cli_list_prints_the_closure(capsys):
    assert mbc.main(["--list"]) == 0
    printed = capsys.readouterr().out
    assert "main" in printed and "TOTAL" in printed
    assert "train_ppo" not in printed


def test_cli_returns_nonzero_on_a_violation(tree, capsys):
    path = os.path.join(tree, "backend", "gait.py")
    text = io.open(path, encoding="utf-8").read()
    io.open(path, "w", encoding="utf-8").write("import paper_data_contract  # noqa: F401\n" + text)
    assert mbc.main(["--registry", mbc.REGISTRY_PATH, "--repo-root", tree]) == 1
    assert "MODULE BOUNDARY CHECK FAILED" in capsys.readouterr().err


# --------------------------------------------------------------------------
# relative sibling imports must not be invisible to the closure
# --------------------------------------------------------------------------
#
# Measured 2026-09-19 while answering decision 6 of docs/TOOLKIT_PORTABILITY.md
# section 8: ``imported_names`` read ``node.module`` and never ``node.level``,
# so ``from . import environment_lock`` contributed NOTHING to the closure. A
# toolkit module could have reached into the teaching product that way and the
# contract would still have printed MODULE_BOUNDARIES_CLEAN. No module in this
# repo uses the form today, so closing it changed no closure -- which is the
# point: it is closed BEFORE decision 6 could ever make it load-bearing.

def test_a_relative_sibling_import_is_visible_to_the_closure(tmp_path):
    """All four import forms reach the closure, not only the two absolute ones."""
    probe = tmp_path / "probe.py"
    probe.write_text(
        "import environment_lock\n"
        "from paper_data_contract import ArtifactRecord\n"
        "from . import run_manifest_lock\n"
        "from .exposure_identification import episode_bound_pct\n",
        encoding="utf-8")
    names = mbc.imported_names(str(probe))
    assert "environment_lock" in names          # import X
    assert "paper_data_contract" in names       # from X import Y
    assert "run_manifest_lock" in names         # from . import X  <-- was invisible
    assert "exposure_identification" in names   # from .X import Y


def test_a_toolkit_module_reaching_out_by_relative_import_is_caught(tree):
    """The same violation as the absolute case, written the relative way."""
    path = os.path.join(tree, "backend", "run_manifest_lock.py")
    text = io.open(path, encoding="utf-8").read()
    io.open(path, "w", encoding="utf-8").write(
        "from . import simulator  # noqa: F401\n" + text)
    with pytest.raises(mbc.ModuleBoundaryError) as caught:
        mbc.verify(mbc.REGISTRY_PATH, tree)
    message = str(caught.value)
    assert "[toolkit]" in message
    assert "MODULE_OUTSIDE_BOUNDARY: simulator" in message
    assert "run_manifest_lock -> simulator" in message


def test_the_toolkit_modules_stay_flat_vendorable(tree):
    """No toolkit module may use a relative import: the usage guide forbids it.

    docs/TOOLKIT_USAGE.md section 2 tells outsiders to copy three files into one
    directory on ``sys.path``. Measured 2026-09-19: rewriting the three sibling
    imports in ``run_manifest_lock`` to ``from . import environment_lock as el``
    still IMPORTS cleanly under that recipe and then fails at the first real
    call with ``ImportError: attempted relative import with no known parent
    package`` -- a late failure, after the caller believes the install worked.
    Adding ``__init__.py`` beside the flat copies does not rescue it.
    """
    registry = mbc.load_registry()
    offenders = []
    for module in registry["boundaries"]["toolkit"]["modules"]:
        path = os.path.join(tree, "backend", module.replace(".", os.sep) + ".py")
        for number, line in enumerate(io.open(path, encoding="utf-8"), start=1):
            stripped = line.strip()
            if stripped.startswith("from .") or stripped.startswith("from ..") \
                    or stripped.startswith("import ."):
                offenders.append(f"{module}:{number}: {stripped}")
    assert offenders == [], (
        "a relative import would break the flat vendoring recipe published in "
        "docs/TOOLKIT_USAGE.md section 2: " + "; ".join(offenders))

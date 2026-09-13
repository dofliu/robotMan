"""RUN-MANIFEST-LOCK-BINDING-V1 acceptance criteria LB-01 .. LB-12.

Frozen in docs/RUN_MANIFEST_LOCK_BINDING_SPEC.md and
backend/run_manifest_lock_binding_protocol.json, both pushed before any
producer was edited.
"""

from __future__ import annotations

import ast
import copy
import json
import shutil
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import environment_lock as el  # noqa: E402
import run_manifest_lock as rml  # noqa: E402
from paper_data_contract import PaperRunManifest  # noqa: E402

REPO_ROOT = BACKEND.parent
MODULE_PATH = BACKEND / "run_manifest_lock.py"
PROTOCOL_PATH = BACKEND / "run_manifest_lock_binding_protocol.json"
SPEC_PATH = REPO_ROOT / "docs" / "RUN_MANIFEST_LOCK_BINDING_SPEC.md"
SEEDVAR_LOCK = BACKEND / "environment_locks" / "lock-2026-09-08-seedvar-execution.json"
SECOND_CASE_LOCK = BACKEND / "environment_locks" / "lock-2026-09-08-second-case-execution.json"

MANIFEST_BYTES = b'{\n "schema_version": "RL_TRAINING_RUN_V2",\n "run_id": "fixture"\n}\n'


def _bound_run(root: Path, *, lock_source: Path = SEEDVAR_LOCK) -> tuple[Path, dict]:
    """A run directory that evaluates to RUN_LOCK_BOUND."""
    run_dir = root / "runs" / "fixture"
    run_dir.mkdir(parents=True)
    (run_dir / "run_manifest.json").write_bytes(MANIFEST_BYTES)
    lock_path = run_dir / "environment_lock.json"
    shutil.copyfile(lock_source, lock_path)
    record = rml.build_binding_record(
        root=root,
        manifest_path=run_dir / "run_manifest.json",
        manifest_schema_version="RL_TRAINING_RUN_V2",
        lock_record_path=lock_path,
        binding_mode=rml.MODE_SIDECAR_ONLY,
        sidecar_reason="fixture: the driver is pinned by an executed protocol",
        verified_before_run=True,
        lock_verified_at_utc="2026-09-13T00:00:00Z",
    )
    rml.write_binding_record(run_dir, record)
    return run_dir, record


@pytest.fixture()
def bound(tmp_path):
    run_dir, record = _bound_run(tmp_path)
    return tmp_path, run_dir, record


def _label(root: Path, run_dir: Path) -> str:
    return rml.evaluate_run(run_dir, "run_manifest.json", root=root)["label"]


# --------------------------------------------------------------------------- #
# the freeze itself
# --------------------------------------------------------------------------- #


def test_protocol_and_specification_digests_match_the_pins():
    """A freeze that nothing re-derives is a claim, not a control."""
    assert rml.sha256_file(PROTOCOL_PATH) == rml.PROTOCOL_SHA256
    assert rml.sha256_file(SPEC_PATH) == rml.SPECIFICATION_SHA256
    protocol = rml.load_protocol()
    assert protocol["status"] == "FROZEN_BEFORE_IMPLEMENTATION"
    assert protocol["contract_id"] == rml.CONTRACT_ID


def test_a_retagged_protocol_is_refused_rather_than_silently_repinned(tmp_path):
    tampered = tmp_path / "protocol.json"
    payload = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    payload["lock_requirement"]["required_lock_completeness"] = "PARTIAL_LOCK"
    tampered.write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    with pytest.raises(rml.RunLockBindingError, match="digest"):
        rml.load_protocol(tampered)


# --------------------------------------------------------------------------- #
# LB-12: the three files this contract promised not to touch
# --------------------------------------------------------------------------- #


def test_lb12_the_immutable_sources_are_byte_unchanged():
    """The promise 'I will not edit these' is checked, not asserted.

    rl/eval_policy.py is re-hashed by the candidate-selection contract against an
    owner-authorized protocol; rl/train_ppo.py is pinned by an executed protocol
    that nothing re-derives; simulator.py enters a deterministic content hash.
    """
    pinned = rml.load_protocol()["immutable_sources"]
    for relative, digest in pinned.items():
        if relative == "rule":
            continue
        assert rml.sha256_file(REPO_ROOT / relative) == digest, relative


# --------------------------------------------------------------------------- #
# LB-01 exact key set
# --------------------------------------------------------------------------- #


def test_lb01_the_key_set_is_exact_in_both_directions(bound):
    _, _, record = bound
    assert tuple(sorted(record)) == rml.RECORD_FIELDS

    missing = {k: v for k, v in record.items() if k != "bound_at_utc"}
    with pytest.raises(rml.RunLockBindingError, match="key set mismatch"):
        rml.validate_binding_record(missing)

    extra = dict(record, unexpected_field="x")
    with pytest.raises(rml.RunLockBindingError, match="key set mismatch"):
        rml.validate_binding_record(extra)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema_version", "RUN_LOCK_BINDING_V2"),
        ("contract_id", "SOMETHING-ELSE"),
        ("binding_mode", "EMBEDDED"),
        ("bound_manifest_sha256", "sha256:" + "Z" * 64),
        ("lock_record_sha256", "deadbeef"),
        ("environment_locked_sha256", "sha256:" + "a" * 63),
        ("bound_manifest_schema_version", ""),
        ("lock_verified_at_utc", "2026-09-13"),
        ("bound_at_utc", "2026-09-13T00:00:00+00:00"),
        ("verified_before_run", "true"),
        ("satisfies_full_lock_requirement", 1),
        ("claim_boundary", "   "),
    ],
)
def test_lb01_each_malformed_field_fails_closed(bound, field, value):
    _, _, record = bound
    with pytest.raises(rml.RunLockBindingError):
        rml.validate_binding_record(dict(record, **{field: value}))


# --------------------------------------------------------------------------- #
# LB-02 the binding pins the manifest bytes
# --------------------------------------------------------------------------- #


def test_lb02_one_flipped_byte_in_the_manifest_is_a_mismatch(bound):
    root, run_dir, _ = bound
    assert _label(root, run_dir) == rml.LABEL_BOUND
    manifest = run_dir / "run_manifest.json"
    manifest.write_bytes(MANIFEST_BYTES[:-1] + b" \n")
    assert _label(root, run_dir) == rml.LABEL_MISMATCH


def test_lb02_a_binding_that_names_another_manifest_is_a_mismatch(bound):
    root, run_dir, record = bound
    rml.write_binding_record(run_dir, dict(record, bound_manifest_path="runs/other/run_manifest.json"))
    assert _label(root, run_dir) == rml.LABEL_MISMATCH


# --------------------------------------------------------------------------- #
# LB-03 / LB-04 two digests, two names
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("lock_source", [SEEDVAR_LOCK, SECOND_CASE_LOCK], ids=["seedvar", "second_case"])
def test_lb03_the_two_digests_are_different_quantities(tmp_path, lock_source):
    """Positive control for the defect this vocabulary exists to prevent.

    The two retained lock records share one locked_sha256 - the two executions
    really did run in the same locked environment - while their file bytes
    differ. A single field could not have carried both meanings.
    """
    run_dir, record = _bound_run(tmp_path, lock_source=lock_source)
    assert record["lock_record_sha256"] != record["environment_locked_sha256"]
    assert record["lock_record_sha256"] == rml.sha256_file(run_dir / "environment_lock.json")
    validation = el.validate_lock_record(el.load_lock_record(lock_source))
    assert record["environment_locked_sha256"] == validation["locked_sha256"]


def test_lb03_both_retained_records_share_a_locked_digest_but_not_their_bytes():
    seedvar = el.validate_lock_record(el.load_lock_record(SEEDVAR_LOCK))
    second = el.validate_lock_record(el.load_lock_record(SECOND_CASE_LOCK))
    assert seedvar["locked_sha256"] == second["locked_sha256"]
    assert rml.sha256_file(SEEDVAR_LOCK) != rml.sha256_file(SECOND_CASE_LOCK)


def test_lb04_the_ambiguous_field_name_is_absent_and_refused(bound):
    _, _, record = bound
    assert rml.FORBIDDEN_FIELD_NAME == "environment_lock_sha256"
    assert rml.FORBIDDEN_FIELD_NAME not in rml.RECORD_FIELDS
    assert rml.FORBIDDEN_FIELD_NAME not in rml.EMBEDDED_LOCK_FIELDS
    assert rml.FORBIDDEN_FIELD_NAME not in record
    with pytest.raises(rml.RunLockBindingError, match="forbidden"):
        rml.validate_binding_record(dict(record, environment_lock_sha256="sha256:" + "a" * 64))


# --------------------------------------------------------------------------- #
# LB-05 completeness, not just class
# --------------------------------------------------------------------------- #


def _partial_lock(path: Path) -> Path:
    record = el.load_lock_record(SEEDVAR_LOCK)
    record["locked"]["plant_fingerprint"] = el._unavailable("synthetic: probe not run")
    record["lock_completeness"] = el._lock_completeness(record["locked"])
    record["locked_sha256"] = el.locked_digest(record["locked"])
    el.write_lock_record(path, record)
    return path


def test_lb05_a_measured_but_partial_lock_is_insufficient_not_bound(tmp_path):
    run_dir = tmp_path / "runs" / "partial"
    run_dir.mkdir(parents=True)
    (run_dir / "run_manifest.json").write_bytes(MANIFEST_BYTES)
    lock_path = _partial_lock(run_dir / "environment_lock.json")

    validation = el.validate_lock_record(el.load_lock_record(lock_path))
    # A lock_class-only gate would wave this through; that is the point.
    assert validation["lock_class"] == el.MEASURED_LOCK_CLASS
    assert validation["lock_completeness"] == el.PARTIAL_LOCK

    record = rml.build_binding_record(
        root=tmp_path,
        manifest_path=run_dir / "run_manifest.json",
        manifest_schema_version="RL_TRAINING_RUN_V2",
        lock_record_path=lock_path,
        binding_mode=rml.MODE_SIDECAR_ONLY,
        sidecar_reason="fixture",
        verified_before_run=True,
        lock_verified_at_utc="2026-09-13T00:00:00Z",
    )
    assert record["satisfies_full_lock_requirement"] is False
    rml.write_binding_record(run_dir, record)
    assert _label(tmp_path, run_dir) == rml.LABEL_INSUFFICIENT
    with pytest.raises(rml.RunLockBindingError, match=rml.LABEL_INSUFFICIENT):
        rml.require_bound_run(run_dir, "run_manifest.json", root=tmp_path)


def test_lb05_the_full_lock_flag_is_derived_rather_than_declared(bound):
    _, _, record = bound
    liar = dict(record, environment_lock_completeness=el.PARTIAL_LOCK)
    with pytest.raises(rml.RunLockBindingError, match="disagrees"):
        rml.validate_binding_record(liar)


def test_lb05_a_protocol_governed_run_refuses_to_start_below_full_lock(tmp_path, monkeypatch):
    partial = _partial_lock(tmp_path / "pinned.json")
    monkeypatch.setattr(el, "capture_environment_lock", lambda *a, **k: el.load_lock_record(partial))
    with pytest.raises(rml.RunLockBindingError, match="RUN_LOCK_NOT_FULL"):
        rml.capture_lock_for_run(tmp_path / "run", require_full_lock=True)


def test_lb05_a_smoke_run_records_the_partial_lock_truthfully(tmp_path, monkeypatch):
    partial = _partial_lock(tmp_path / "pinned.json")
    monkeypatch.setattr(el, "capture_environment_lock", lambda *a, **k: el.load_lock_record(partial))
    capture = rml.capture_lock_for_run(tmp_path / "run", require_full_lock=False)
    block = rml.lock_block_from_record(capture["lock_record_path"], verified_before_run=True)
    assert block["environment_lock_completeness"] == el.PARTIAL_LOCK
    assert block["satisfies_full_lock_requirement"] is False


# --------------------------------------------------------------------------- #
# LB-06 absence is a named result, never a pass
# --------------------------------------------------------------------------- #


def test_lb06_a_run_without_a_binding_is_unbound(bound):
    root, run_dir, _ = bound
    (run_dir / rml.BINDING_FILENAME).unlink()
    assert _label(root, run_dir) == rml.LABEL_UNBOUND
    with pytest.raises(rml.RunLockBindingError, match=rml.LABEL_UNBOUND):
        rml.require_bound_run(run_dir, "run_manifest.json", root=root)


def test_lb06_only_bound_passes_the_gate(bound):
    root, run_dir, _ = bound
    assert rml.require_bound_run(run_dir, "run_manifest.json", root=root)["label"] == rml.LABEL_BOUND


# --------------------------------------------------------------------------- #
# LB-07 mode and reason must agree
# --------------------------------------------------------------------------- #


def test_lb07_sidecar_only_requires_a_named_reason(bound):
    _, _, record = bound
    with pytest.raises(rml.RunLockBindingError, match="sidecar_reason"):
        rml.validate_binding_record(dict(record, sidecar_reason=None))


def test_lb07_an_embedded_binding_must_not_carry_a_reason(bound):
    _, _, record = bound
    embedded = dict(record, binding_mode=rml.MODE_EMBEDDED_AND_SIDECAR)
    with pytest.raises(rml.RunLockBindingError, match="must be null"):
        rml.validate_binding_record(embedded)
    rml.validate_binding_record(dict(embedded, sidecar_reason=None))


def test_lb07_every_frozen_producer_declares_a_consistent_mode_and_reason():
    for entry in rml.load_protocol()["producers_in_scope"]:
        if entry["binding_mode"] == rml.MODE_SIDECAR_ONLY:
            assert entry["sidecar_reason"], entry["producer"]
        else:
            assert entry["binding_mode"] == rml.MODE_EMBEDDED_AND_SIDECAR
            assert entry["sidecar_reason"] is None, entry["producer"]


# --------------------------------------------------------------------------- #
# LB-08 paths may not escape
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "path",
    ["/etc/passwd", "../outside/run_manifest.json", "runs\\fixture\\run_manifest.json",
     "runs/./fixture/run_manifest.json", "", "runs//fixture/run_manifest.json"],
)
@pytest.mark.parametrize("field", ["bound_manifest_path", "lock_record_path"])
def test_lb08_unsafe_paths_fail_closed(bound, field, path):
    _, _, record = bound
    with pytest.raises(rml.RunLockBindingError):
        rml.validate_binding_record(dict(record, **{field: path}))


def test_lb08_a_lock_record_outside_the_run_root_is_refused(tmp_path):
    run_dir = tmp_path / "runs" / "fixture"
    run_dir.mkdir(parents=True)
    (run_dir / "run_manifest.json").write_bytes(MANIFEST_BYTES)
    with pytest.raises(rml.RunLockBindingError, match="must live inside the run root"):
        rml.build_binding_record(
            root=tmp_path,
            manifest_path=run_dir / "run_manifest.json",
            manifest_schema_version="RL_TRAINING_RUN_V2",
            lock_record_path=SEEDVAR_LOCK,
            binding_mode=rml.MODE_SIDECAR_ONLY,
            sidecar_reason="fixture",
            verified_before_run=True,
            lock_verified_at_utc="2026-09-13T00:00:00Z",
        )


# --------------------------------------------------------------------------- #
# LB-09 five labels, and method failure is never downgraded
# --------------------------------------------------------------------------- #


def test_lb09_a_broken_binding_is_a_method_failure_not_one_of_the_others(bound):
    root, run_dir, _ = bound
    (run_dir / rml.BINDING_FILENAME).write_text("{ not json", encoding="utf-8")
    assert _label(root, run_dir) == rml.LABEL_METHOD_FAILURE


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(lambda r: r.pop("claim_boundary"), id="missing-field"),
        pytest.param(lambda r: r.update(schema_version="WRONG"), id="wrong-schema"),
        pytest.param(lambda r: r.update(environment_lock_sha256="x"), id="forbidden-name"),
        pytest.param(lambda r: r.update(bound_manifest_path="../escape.json"), id="path-escape"),
        pytest.param(lambda r: r.update(sidecar_reason=None), id="missing-reason"),
    ],
)
def test_lb09_contract_violations_never_become_bound_unbound_mismatch_or_insufficient(bound, mutate):
    root, run_dir, record = bound
    broken = copy.deepcopy(record)
    mutate(broken)
    (run_dir / rml.BINDING_FILENAME).write_text(
        json.dumps(broken, indent=1, sort_keys=True) + "\n", encoding="utf-8"
    )
    assert _label(root, run_dir) == rml.LABEL_METHOD_FAILURE


def test_lb09_a_missing_manifest_is_a_method_failure(bound):
    root, run_dir, _ = bound
    (run_dir / "run_manifest.json").unlink()
    assert _label(root, run_dir) == rml.LABEL_METHOD_FAILURE


def test_lb09_the_five_labels_are_exactly_the_frozen_ones():
    assert set(rml.LABELS) == set(rml.load_protocol()["outcome_labels"])


# --------------------------------------------------------------------------- #
# LB-10 the PAPER_RUN_MANIFEST upgrade
# --------------------------------------------------------------------------- #


def _paper_manifest(**overrides) -> dict:
    base = {
        "schema_version": "PAPER_RUN_MANIFEST_V1",
        "run_id": "run-lb10",
        "experiment_id": "EXP-LB10",
        "protocol_id": "PROTO-LB10",
        "protocol_version": "1.0.0",
        "protocol_status": "FROZEN",
        "research_question_id": "RQ-LB10",
        "hypothesis_id": "H-LB10",
        "run_class": "REGRESSION",
        "data_partition": "REGRESSION",
        "status": "COMPLETED",
        "evidence_scope": "SIM_ONLY_MUJOCO",
        "claim_boundary": "Fixture bundle for LB-10; not evidence of anything.",
        "source_git_sha": "a" * 40,
        "source_dirty": False,
        "started_at": "2026-09-13T00:00:00+00:00",
        "completed_at": "2026-09-13T00:00:01+00:00",
        "task_id": "TASK-LB10",
        "controller_family": "ORACLE",
        "controller_id": "CTRL-LB10",
        "metric_set_id": "METRICS-LB10",
        "evaluator_id": "EVAL-LB10",
        "plant": {"identity_id": "PLANT-LB10", "sha256": "sha256:" + "b" * 64},
        "controller": {"identity_id": "CTRL-LB10", "sha256": "sha256:" + "c" * 64},
        "seeds": {"deterministic": True},
        "scenario": {"duration_s": 1.0},
        "primary_outcomes": ["x"],
        "assist_enabled": False,
        "tuning_performed_after_freeze": False,
        "artifacts": [
            {
                "role": role,
                "path": f"{role}.json",
                "media_type": "application/json",
                "bytes": 1,
                "sha256": "sha256:" + "d" * 64,
            }
            for role in sorted(
                {
                    "protocol", "resolved_config", "model", "controller", "environment",
                    "raw_trace", "metrics", "evaluator_receipt", "stdout", "stderr",
                }
            )
        ],
    }
    base.update(overrides)
    return base


LOCK_BLOCK = {
    "environment_lock_class": "MEASURED_ENVIRONMENT_LOCK",
    "environment_lock_completeness": "FULL_LOCK",
    "environment_lock_threading_determinism": "AMBIENT_THREADING_PINNED",
    "environment_locked_sha256": "sha256:" + "e" * 64,
    "lock_record_sha256": "sha256:" + "f" * 64,
    "satisfies_full_lock_requirement": True,
    "verified_before_run": True,
}


def test_lb10_v1_still_validates_and_must_not_carry_the_block():
    PaperRunManifest.model_validate(_paper_manifest())
    with pytest.raises(Exception, match="V1"):
        PaperRunManifest.model_validate(_paper_manifest(environment_lock=dict(LOCK_BLOCK)))


def test_lb10_v2_requires_the_block():
    with pytest.raises(Exception, match="V2"):
        PaperRunManifest.model_validate(_paper_manifest(schema_version="PAPER_RUN_MANIFEST_V2"))
    PaperRunManifest.model_validate(
        _paper_manifest(schema_version="PAPER_RUN_MANIFEST_V2", environment_lock=dict(LOCK_BLOCK))
    )


def test_lb10_the_v2_block_derives_its_flag_rather_than_trusting_it():
    lying = dict(LOCK_BLOCK, environment_lock_completeness="PARTIAL_LOCK")
    with pytest.raises(Exception):
        PaperRunManifest.model_validate(
            _paper_manifest(schema_version="PAPER_RUN_MANIFEST_V2", environment_lock=lying)
        )


def test_lb10_the_v2_block_refuses_the_ambiguous_field_name():
    with pytest.raises(Exception):
        PaperRunManifest.model_validate(
            _paper_manifest(
                schema_version="PAPER_RUN_MANIFEST_V2",
                environment_lock=dict(LOCK_BLOCK, environment_lock_sha256="sha256:" + "a" * 64),
            )
        )


def test_lb10_the_embedded_block_is_the_binding_record_subset(bound):
    _, _, record = bound
    block = rml.embedded_lock_block(record)
    assert set(block) == set(rml.EMBEDDED_LOCK_FIELDS) == set(LOCK_BLOCK)
    assert all(block[field] == record[field] for field in block)


# --------------------------------------------------------------------------- #
# LB-11 stdlib only
# --------------------------------------------------------------------------- #


def test_lb11_the_module_imports_nothing_outside_the_standard_library():
    """Checked by parsing, not by substring: a lazy import inside a function is
    exactly how environment_lock keeps its own replay path clean, so only
    module-scope imports are constrained."""
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    allowed = {
        "__future__", "hashlib", "json", "re", "datetime", "pathlib", "typing",
    }
    top_level = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            top_level.extend(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            top_level.append((node.module or "").split(".")[0])
    assert top_level, "the module must import something; an empty result would pass vacuously"
    assert set(top_level) <= allowed, sorted(set(top_level) - allowed)


def test_lb11_the_checking_path_runs_without_site_packages(tmp_path):
    run_dir, _ = _bound_run(tmp_path)
    import subprocess

    script = (
        "import sys; sys.path.insert(0, %r);\n"
        "import run_manifest_lock as rml;\n"
        "print(rml.evaluate_run(%r, 'run_manifest.json', root=%r)['label'])\n"
        % (str(BACKEND), str(run_dir), str(tmp_path))
    )
    completed = subprocess.run(
        [sys.executable, "-I", "-S", "-c", script],
        capture_output=True, text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == rml.LABEL_BOUND


# --------------------------------------------------------------------------- #
# serialization and capture ordering
# --------------------------------------------------------------------------- #


def test_the_record_serializes_deterministically(bound):
    _, _, record = bound
    first = rml.serialize_binding_record(record)
    assert first == rml.serialize_binding_record(json.loads(first))
    assert first.endswith("\n")
    assert json.loads(first) == record


def test_capture_records_the_verification_time_before_the_binding_time(bound):
    _, _, record = bound
    assert record["lock_verified_at_utc"] <= record["bound_at_utc"]
    assert record["verified_before_run"] is True


def test_capture_refuses_an_environment_that_is_not_the_pinned_one(tmp_path, monkeypatch):
    other = el.load_lock_record(SEEDVAR_LOCK)
    other["locked"]["architecture"]["machine"] = "not-this-machine"
    other["locked_sha256"] = el.locked_digest(other["locked"])
    monkeypatch.setattr(el, "capture_environment_lock", lambda *a, **k: other)
    with pytest.raises(rml.RunLockBindingError, match="RUN_LOCK_ENVIRONMENT_MISMATCH"):
        rml.capture_lock_for_run(tmp_path / "run", pinned_lock_record_path=SEEDVAR_LOCK)

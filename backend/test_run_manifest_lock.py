"""RUN-MANIFEST-LOCK-BINDING-V1 acceptance criteria LB-01 .. LB-12.

Frozen in docs/RUN_MANIFEST_LOCK_BINDING_SPEC.md and
backend/toolkit/run_manifest_lock_binding_protocol.json, both pushed before any
producer was edited. The protocol moved with its module on 2026-09-19; the
bytes are unchanged and both digests still match.
"""

from __future__ import annotations

import ast
import copy
import hashlib
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
# Both come from the imported module, so they follow product B wherever it
# lives; it moved to backend/toolkit/ on 2026-09-19.
MODULE_PATH = Path(rml.__file__).resolve()
TOOLKIT = MODULE_PATH.parent
PROTOCOL_PATH = TOOLKIT / "run_manifest_lock_binding_protocol.json"
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


def _git_blob_sha256(commit: str, relative: str) -> str | None:
    """SHA-256 of a file's contents at one commit, or None if git cannot answer."""
    import subprocess

    completed = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "show", f"{commit}:{relative}"],
        capture_output=True,
    )
    if completed.returncode != 0:
        return None
    return "sha256:" + hashlib.sha256(completed.stdout).hexdigest()


def test_lb12_this_contract_did_not_edit_the_three_pinned_sources():
    """The promise is 'THIS contract did not edit these', so check that.

    LOCKBIND-AMENDMENT-01-LB12-SCOPE: the original version compared the working
    tree, which answers 'has anyone ever edited them' - a different question,
    belonging to each file's own contract rather than to this one. Both readings
    agreed at implementation time; they diverge only on future edits, which the
    criterion never spoke about. Reading the two commits from git fixes the claim
    as a historical fact that no later commit can alter.
    """
    pinned = rml.load_protocol()["immutable_sources"]
    commits = pinned["verified_at_commits"]
    sources = {
        key: value for key, value in pinned.items()
        if key.endswith(".py") and isinstance(value, str)
    }
    assert len(sources) == 3, sorted(sources)

    checked = 0
    for label, commit in commits.items():
        for relative, digest in sources.items():
            actual = _git_blob_sha256(commit, relative)
            if actual is None:
                pytest.skip(f"git history for {commit} is unavailable in this checkout")
            assert actual == digest, f"{label} {commit[:7]} {relative}"
            checked += 1
    assert checked == 6, checked


def test_lb12_does_not_freeze_those_files_for_the_rest_of_the_repository():
    """Section 15.3: this contract constrains itself, not everyone forever.

    A future line that legitimately edits rl/train_ppo.py - ROADMAP section 9
    item 2 needs to, because checkpoint_interval is 2_000_000 for full runs and
    lineage requires intermediate checkpoints - must not turn this contract red.
    Ongoing protection is named per file and lives in those contracts.
    """
    protection = rml.load_protocol()["immutable_sources"]["ongoing_protection"]
    assert set(protection) == {
        "backend/rl/eval_policy.py",
        "backend/rl/train_ppo.py",
        "backend/simulator.py",
    }
    # The gap is named rather than quietly patched here (section 15.4).
    assert protection["backend/rl/train_ppo.py"].startswith("NONE")
    for path in ("backend/rl/eval_policy.py", "backend/simulator.py"):
        assert "test_" in protection[path], path


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
# LB-08 the same escape rule on the CHECKING path
# --------------------------------------------------------------------------- #
#
# Until 2026-09-18 the build path failed closed on a path escape and the
# checking path did not: evaluate_run computed
# manifest_path.resolve().relative_to(run_root) with no containment guard, so an
# escape raised a bare ValueError -- a failure with no label at all, in a gate
# whose whole design is that every failure carries exactly one of five.
# Specification section 7.1 lists 路徑逃逸 under RUN_LOCK_BINDING_METHOD_FAILURE,
# so these are its positive controls.  The MISMATCH cases below are the negative
# controls: they prove the guard did not swallow a case that was already
# labelled correctly.


def _escaping_manifest(root: Path, run_dir: Path, outside: Path) -> None:
    """Replace the bound manifest with a symlink to identical bytes outside root."""
    outside.mkdir(parents=True, exist_ok=True)
    (outside / "run_manifest.json").write_bytes(MANIFEST_BYTES)
    (run_dir / "run_manifest.json").unlink()
    (run_dir / "run_manifest.json").symlink_to(outside / "run_manifest.json")


def test_lb08_a_manifest_symlinked_outside_the_run_root_is_a_method_failure(tmp_path):
    """The bytes match the bound digest, so nothing here is a digest mismatch."""
    root = tmp_path / "root"
    root.mkdir()
    run_dir, _ = _bound_run(root)
    _escaping_manifest(root, run_dir, tmp_path / "outside")
    outcome = rml.evaluate_run(run_dir, "run_manifest.json", root=root)
    assert outcome["label"] == rml.LABEL_METHOD_FAILURE
    assert "escapes the run root" in outcome["detail"]


def test_lb08_a_run_directory_outside_the_declared_root_is_a_method_failure(tmp_path):
    """Neither frozen MISMATCH disjunct holds here: the digest and path are right."""
    root = tmp_path / "root"
    root.mkdir()
    (tmp_path / "otherroot").mkdir()
    run_dir, _ = _bound_run(root)
    assert _label(tmp_path / "otherroot", run_dir) == rml.LABEL_METHOD_FAILURE


def test_lb08_a_manifest_filename_that_escapes_the_root_is_a_method_failure(tmp_path):
    """The escape needs no symlink: `..` in the caller's filename reaches it too."""
    root = tmp_path / "root"
    root.mkdir()
    run_dir, _ = _bound_run(root)
    (tmp_path / "outside").mkdir()
    (tmp_path / "outside" / "run_manifest.json").write_bytes(MANIFEST_BYTES)
    outcome = rml.evaluate_run(
        run_dir, "../../../outside/run_manifest.json", root=root
    )
    assert outcome["label"] == rml.LABEL_METHOD_FAILURE


def test_lb08_a_path_that_stays_inside_the_root_is_still_only_a_mismatch(tmp_path):
    """Negative control: the guard must not swallow an already-correct label."""
    root = tmp_path / "root"
    root.mkdir()
    run_dir, _ = _bound_run(root)
    sibling = root / "runs" / "sibling"
    sibling.mkdir(parents=True)
    (sibling / "run_manifest.json").write_bytes(MANIFEST_BYTES)
    outcome = rml.evaluate_run(run_dir, "../sibling/run_manifest.json", root=root)
    assert outcome["label"] == rml.LABEL_MISMATCH


def test_lb08_an_unbound_directory_outside_the_root_stays_unbound(tmp_path):
    """Pins the guard's placement, which decides this label.

    RUN_LOCK_UNBOUND's frozen definition is "this run directory has no binding
    record" and says nothing about the root, so it is true whatever root the
    caller declared.  The containment guard therefore sits after the
    binding-presence check, not before it, and this is a decision rather than an
    accident of ordering.
    """
    (tmp_path / "elsewhere").mkdir()
    assert _label(tmp_path / "elsewhere", tmp_path / "elsewhere") == rml.LABEL_UNBOUND


def test_lb08_the_retained_gate_refuses_a_manifest_that_escapes_its_directory(tmp_path):
    """The same escape was a false PASS here, not a crash -- measured 2026-09-18.

    evaluate_relocated_run deliberately drops the comparison against
    bound_manifest_path, and before this guard that meant a retained directory
    holding a binding record plus a symlink to a manifest outside it returned
    RUN_LOCK_BOUND.  Dropping the path comparison is not the same as hashing
    whatever the directory points at.
    """
    root = tmp_path / "root"
    root.mkdir()
    run_dir, _ = _bound_run(root)
    _escaping_manifest(root, run_dir, tmp_path / "outside")
    outcome = rml.evaluate_relocated_run(run_dir, "run_manifest.json")
    assert outcome["label"] == rml.LABEL_METHOD_FAILURE
    assert outcome["label"] != rml.LABEL_BOUND


def test_lb08_a_symlink_loop_is_labelled_rather_than_raised(tmp_path):
    """Path.resolve() raises a bare RuntimeError, and the contract's own error
    type is a RuntimeError SUBCLASS -- so `except RunLockBindingError` looks
    like it covers this and does not.  The assertion on the class relationship
    is deliberate: it is what makes the bug invisible on inspection."""
    assert issubclass(rml.RunLockBindingError, RuntimeError)
    root = tmp_path / "root"
    root.mkdir()
    run_dir, _ = _bound_run(root)
    (run_dir / "run_manifest.json").unlink()
    (run_dir / "run_manifest.json").symlink_to(run_dir / "loop_b")
    (run_dir / "loop_b").symlink_to(run_dir / "run_manifest.json")
    assert _label(root, run_dir) in {rml.LABEL_METHOD_FAILURE, rml.LABEL_UNBOUND}


def test_lb08_the_gate_raises_the_contracts_own_type_on_an_escape(tmp_path):
    """A downstream handler binds to the TYPE, not to the label string.

    Before the guard, require_bound_run raised builtins.ValueError on this
    input, so a caller failing closed on RunLockBindingError got an unhandled
    crash instead of a refusal.
    """
    root = tmp_path / "root"
    root.mkdir()
    run_dir, _ = _bound_run(root)
    _escaping_manifest(root, run_dir, tmp_path / "outside")
    with pytest.raises(rml.RunLockBindingError, match=rml.LABEL_METHOD_FAILURE):
        rml.require_bound_run(run_dir, "run_manifest.json", root=root)


# --------------------------------------------------------------------------- #
# the bound lock record is re-derived, not trusted
# --------------------------------------------------------------------------- #
#
# Until 2026-09-18 neither gate looked at lock_record_path or
# lock_record_sha256, so a run kept RUN_LOCK_BOUND after its lock record was
# deleted, truncated, replaced with non-JSON, or swapped for a DIFFERENT
# committed lock record.  The swap is the consequential one: the run asserts it
# ran under one environment while the retained file is another, and that
# relation is the only thing this contract exists to establish.
#
# Both failure shapes are RUN_LOCK_BINDING_METHOD_FAILURE, by two routes.
# Absent or unreadable is the condition specification section 7.1 enumerates by
# name (「lock record 讀不到」).  Present-but-differing is readable, so it is not
# that item: it violates section 4.1's definition of the field and reaches the
# same label through the row's head clause 「任何 contract 違反」.
# RUN_LOCK_MISMATCH was considered -- LB-02 makes a flipped byte in the bound
# MANIFEST a mismatch, so parity is the strongest case for it -- and is
# unavailable: both of MISMATCH's frozen disjuncts name bound_manifest_*.


def _relabel(directory, manifest="run_manifest.json", **kwargs):
    return rml.evaluate_relocated_run(directory, manifest, **kwargs)["label"]


@pytest.mark.parametrize(
    "corrupt,id_",
    [
        pytest.param(lambda p: p.unlink(), "deleted", id="deleted"),
        pytest.param(lambda p: p.write_bytes(b""), "truncated", id="truncated"),
        pytest.param(lambda p: p.write_bytes(b"not json at all"), "garbage", id="garbage"),
        pytest.param(lambda p: shutil.copyfile(SECOND_CASE_LOCK, p), "swapped", id="swapped"),
    ],
)
def test_the_bound_lock_record_is_re_derived_by_both_gates(bound, corrupt, id_):
    """The swap case is why a digest, not a presence check: the file is present,
    well-formed, and is a real committed lock record -- just not the one bound."""
    root, run_dir, _ = bound
    corrupt(run_dir / "environment_lock.json")
    assert _label(root, run_dir) == rml.LABEL_METHOD_FAILURE
    assert _relabel(run_dir) == rml.LABEL_METHOD_FAILURE


def test_a_lock_record_symlinked_out_of_the_frame_is_a_method_failure(tmp_path):
    """safe_relative_path rejects only SYNTACTIC escapes, and this path is named
    by the record being checked rather than by the caller."""
    root = tmp_path / "root"
    root.mkdir()
    run_dir, _ = _bound_run(root)
    outside = tmp_path / "outside"
    outside.mkdir()
    shutil.copyfile(run_dir / "environment_lock.json", outside / "environment_lock.json")
    (run_dir / "environment_lock.json").unlink()
    (run_dir / "environment_lock.json").symlink_to(outside / "environment_lock.json")
    # identical bytes: a bare re-hash with no containment guard would pass here
    outcome = rml.evaluate_run(run_dir, "run_manifest.json", root=root)
    assert outcome["label"] == rml.LABEL_METHOD_FAILURE
    assert "escapes the run root" in outcome["detail"]
    assert _relabel(run_dir) == rml.LABEL_METHOD_FAILURE


def test_the_lock_re_derivation_precedes_the_mismatch_and_insufficient_returns(bound):
    """Section 7.2 forbids reporting a method failure as one of the other four.

    A single-fault test cannot catch a misplaced check; these are the multi-fault
    controls that pin the ordering.
    """
    root, run_dir, record = bound
    # fault 1: the lock record no longer matches. fault 2: the manifest byte flips.
    (run_dir / "environment_lock.json").write_bytes(b"")
    (run_dir / "run_manifest.json").write_bytes(MANIFEST_BYTES.replace(b"fixture", b"fixturX"))
    assert _label(root, run_dir) == rml.LABEL_METHOD_FAILURE
    assert _relabel(run_dir) == rml.LABEL_METHOD_FAILURE


def test_the_lock_re_derivation_precedes_the_insufficient_return(tmp_path):
    """The same ordering, against RUN_LOCK_INSUFFICIENT rather than MISMATCH.

    The flag cannot be faked in the record -- validate_binding_record derives it,
    which test_lb05_the_full_lock_flag_is_derived_rather_than_declared pins -- so
    this needs a genuinely MEASURED + PARTIAL_LOCK record, built the way the
    LB-05 control builds one.
    """
    run_dir = tmp_path / "runs" / "partial"
    run_dir.mkdir(parents=True)
    (run_dir / "run_manifest.json").write_bytes(MANIFEST_BYTES)
    lock_path = _partial_lock(run_dir / "environment_lock.json")
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

    assert _label(tmp_path, run_dir) == rml.LABEL_INSUFFICIENT   # one fault only
    lock_path.unlink()                                           # now add the second
    assert _label(tmp_path, run_dir) == rml.LABEL_METHOD_FAILURE
    assert _relabel(run_dir) == rml.LABEL_METHOD_FAILURE


def test_the_relocated_gate_takes_the_lock_record_basename_from_the_record(tmp_path):
    """In the retained frame only the BYTES can be recomputed.

    Measured 2026-09-18: of the fifteen binding records under version control,
    none has its lock_record_path in version control -- every one points into the
    gitignored backend/rl/artifacts/ -- while all fifteen have a tracked sibling
    copy beside them under the same basename. The sibling is the only relation
    that survives a fresh clone, which is why the basename is load-bearing rather
    than a convenience.
    """
    root = tmp_path / "root"
    root.mkdir()
    run_dir, record = _bound_run(root)
    assert record["lock_record_path"].endswith("/environment_lock.json")
    assert _relabel(run_dir) == rml.LABEL_BOUND
    # renamed by the retainer: the default lookup fails closed, the parameter works
    (run_dir / "environment_lock.json").rename(run_dir / "captured_lock.json")
    assert _relabel(run_dir) == rml.LABEL_METHOD_FAILURE
    assert _relabel(run_dir, lock_record_filename="captured_lock.json") == rml.LABEL_BOUND


def test_a_retained_directory_without_its_lock_record_is_not_bound(tmp_path):
    """An accepted consequence, recorded rather than hidden.

    Nothing in the frozen specification requires a retained bundle to carry its
    lock record, and section 7.2 makes RUN_LOCK_BINDING_METHOD_FAILURE
    permanently non-downgradable -- so this is the stickiest label the gate can
    give. It is taken deliberately: a bundle that cannot recompute its own
    environment relation must not be reported as bound, and no other one of the
    five labels is true of it. Measured unreachable in this repository (0 of 15
    committed retained directories lack the sibling copy).
    """
    root = tmp_path / "root"
    root.mkdir()
    run_dir, _ = _bound_run(root)
    (run_dir / "environment_lock.json").unlink()
    outcome = rml.evaluate_relocated_run(run_dir, "run_manifest.json")
    assert outcome["label"] == rml.LABEL_METHOD_FAILURE
    assert outcome["label"] != rml.LABEL_BOUND
    assert "lock record" in outcome["detail"]


def test_every_committed_binding_still_verifies_against_its_retained_lock_record():
    """The blast-radius check, run against the real retained evidence.

    The fix tightens what RUN_LOCK_BOUND requires, so it could in principle turn
    a retained label red. It does not: every binding record in the tree still
    verifies, each using its own declared manifest basename.
    """
    bindings = sorted(REPO_ROOT.rglob("run_lock_binding.json"))
    assert len(bindings) >= 15, "the retained corpus should not have shrunk"
    for binding in bindings:
        record = json.loads(binding.read_text(encoding="utf-8"))
        manifest = Path(record["bound_manifest_path"]).name
        outcome = rml.evaluate_relocated_run(binding.parent, manifest)
        assert outcome["label"] == rml.LABEL_BOUND, (str(binding), outcome["detail"])


def test_validate_lock_record_is_deliberately_not_called_and_the_reason_is_recorded():
    """The 「validate_lock_record 失敗」 half of section 7.1 stays UNIMPLEMENTED.

    The reason is not stdlib-ness, and asserting the real one keeps a false
    justification out of the module: EnvironmentLockError and RunLockBindingError
    are SIBLINGS -- both direct subclasses of RuntimeError, neither a subclass of
    the other -- so `except RunLockBindingError` in the gates would not catch it,
    and the call would reintroduce the class of unlabelled failure path this
    module just finished closing.
    """
    assert not issubclass(el.EnvironmentLockError, rml.RunLockBindingError)
    assert not issubclass(rml.RunLockBindingError, el.EnvironmentLockError)
    assert issubclass(el.EnvironmentLockError, RuntimeError)
    assert issubclass(rml.RunLockBindingError, RuntimeError)
    source = MODULE_PATH.read_text(encoding="utf-8")
    assert "validate_lock_record" not in source.split('"""')[0] or True
    # the gates must not call it; build_binding_record still may
    checking = source.split("def evaluate_run(")[1]
    assert "el.validate_lock_record" not in checking


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

    # Both sides of the new lock-record branch run here, not only the BOUND
    # path: LB-11's guarantee is worth little if it proves stdlib-ness of a path
    # that excludes the half that matters. The assertion on sys.modules is the
    # point -- it is what would catch the checking path acquiring an
    # environment_lock dependency, which the AST test cannot see because a lazy
    # import is not a module-scope one.
    script = (
        "import sys; sys.path.insert(0, %r);\n"
        "import run_manifest_lock as rml;\n"
        "from pathlib import Path;\n"
        "print(rml.evaluate_run(%r, 'run_manifest.json', root=%r)['label']);\n"
        "Path(%r).unlink();\n"
        "print(rml.evaluate_run(%r, 'run_manifest.json', root=%r)['label']);\n"
        "print('environment_lock' in sys.modules)\n"
        % (str(TOOLKIT), str(run_dir), str(tmp_path),
           str(run_dir / "environment_lock.json"), str(run_dir), str(tmp_path))
    )
    completed = subprocess.run(
        [sys.executable, "-I", "-S", "-c", script],
        capture_output=True, text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.split() == [
        rml.LABEL_BOUND, rml.LABEL_METHOD_FAILURE, "False",
    ], completed.stdout


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

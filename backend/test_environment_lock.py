"""Fail-closed tests for the ENVIRONMENT-LOCK-V1 contract.

Every test here is about whether the lock can be *trusted*, not about which
versions this machine happens to have.  Nothing asserts a concrete version
string: that would make the suite a snapshot of one container instead of a
check on the mechanism.
"""

from __future__ import annotations

import ast
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys

import pytest

import environment_lock as lock_module
from environment_lock import (
    ABSENT_LOCK_CLASS,
    DETERMINISM_ENVIRONMENT_VARIABLES,
    FULL_LOCK,
    LOCKED_SECTIONS,
    LOCK_RECORD_SCHEMA,
    MEASURED_LOCK_CLASS,
    NO_LOCK,
    PARTIAL_LOCK,
    REQUIRED_DISTRIBUTIONS,
    SEVERITY_MISMATCH,
    SEVERITY_RETAINED,
    SYNTHETIC_LOCK_CLASS,
    EnvironmentLockError,
    absent_lock_record,
    capture_environment_lock,
    lcg_floats,
    load_lock_record,
    locked_digest,
    replay_locked_digest,
    satisfies_full_lock_requirement,
    validate_lock_record,
    verify_environment_lock,
    write_lock_record,
)


BACKEND_ROOT = Path(__file__).resolve().parent
MODULE_PATH = BACKEND_ROOT / "environment_lock.py"

# Third-party imports must stay inside the probes.  These are the only module
# roots the top level of environment_lock.py is allowed to reach for.
ALLOWED_TOP_LEVEL_IMPORTS = {
    "__future__",
    "argparse",
    "datetime",
    "hashlib",
    "importlib",
    "json",
    "math",
    "os",
    "pathlib",
    "platform",
    "subprocess",
    "sys",
    "typing",
}


@pytest.fixture(scope="module")
def measured_record() -> dict:
    """One real capture, reused: the torch and MuJoCo probes are not free."""
    return capture_environment_lock()


@pytest.fixture
def record(measured_record: dict) -> dict:
    return deepcopy(measured_record)


def _refreeze(payload: dict) -> dict:
    """Recompute every field the record derives from its own locked subtree.

    Mutating a locked field and only re-digesting would leave
    ``lock_completeness`` and ``threading_determinism`` stale, so the record
    would fail validation for the wrong reason and hide what the test meant to
    exercise.
    """
    locked = payload["locked"]
    payload["lock_completeness"] = lock_module._lock_completeness(locked)
    payload["threading_determinism"] = lock_module._threading_determinism(
        locked["determinism_environment"]
    )
    payload["locked_sha256"] = locked_digest(locked)
    return payload


# --------------------------------------------------------------------------- #
# EL-01 field registry
# --------------------------------------------------------------------------- #


def test_captured_record_validates_with_a_matching_digest(record: dict) -> None:
    validation = validate_lock_record(record)
    assert validation["record_valid"] is True
    assert validation["lock_class"] == MEASURED_LOCK_CLASS
    assert validation["locked_sha256"] == locked_digest(record["locked"])
    assert record["schema_version"] == LOCK_RECORD_SCHEMA


def test_locked_section_set_is_exactly_the_frozen_registry(record: dict) -> None:
    assert tuple(sorted(record["locked"])) == LOCKED_SECTIONS
    assert tuple(sorted(record["locked"]["distributions"])) == REQUIRED_DISTRIBUTIONS
    assert (
        tuple(sorted(record["locked"]["determinism_environment"]))
        == DETERMINISM_ENVIRONMENT_VARIABLES
    )


def test_undeclared_locked_field_fails_closed(record: dict) -> None:
    record["locked"]["interpreter"]["extra_probe"] = "1"
    with pytest.raises(EnvironmentLockError, match="undeclared fields"):
        validate_lock_record(_refreeze(record))


def test_missing_locked_field_fails_closed(record: dict) -> None:
    del record["locked"]["architecture"]["machine"]
    with pytest.raises(EnvironmentLockError, match="missing fields"):
        validate_lock_record(_refreeze(record))


def test_undeclared_top_level_record_field_fails_closed(record: dict) -> None:
    record["notes"] = "hand written"
    with pytest.raises(EnvironmentLockError, match="undeclared fields"):
        validate_lock_record(record)


def test_undeclared_observed_field_fails_closed(record: dict) -> None:
    record["observed"]["hostname"] = "somewhere"
    with pytest.raises(EnvironmentLockError, match="undeclared fields"):
        validate_lock_record(record)


# --------------------------------------------------------------------------- #
# EL-02 digest scope and independent replay
# --------------------------------------------------------------------------- #


def test_digest_covers_only_the_locked_subtree(record: dict) -> None:
    baseline = locked_digest(record["locked"])
    record["observed"]["cpu_count"] += 1
    record["captured_at_utc"] = "1999-12-31T23:59:59Z"
    assert locked_digest(record["locked"]) == baseline
    assert validate_lock_record(record)["locked_sha256"] == baseline


def test_declared_digest_drift_fails_closed(record: dict) -> None:
    record["locked_sha256"] = "sha256:" + "0" * 64
    with pytest.raises(EnvironmentLockError, match="locked_sha256 does not match"):
        validate_lock_record(record)


def test_stdlib_only_digest_replay_is_exact(tmp_path: Path, record: dict) -> None:
    target = tmp_path / "lock.json"
    write_lock_record(target, record)
    replay = replay_locked_digest(target)
    assert replay["replay_exact"] is True
    assert replay["locked_sha256"] == record["locked_sha256"]
    assert replay["replay_interpreter_flags"] == ["-I", "-S"]


def test_digest_replay_detects_a_tampered_declared_digest(
    tmp_path: Path, record: dict
) -> None:
    record["locked_sha256"] = "sha256:" + "1" * 64
    target = tmp_path / "lock.json"
    target.write_text(
        json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(EnvironmentLockError, match="digest replay mismatch"):
        replay_locked_digest(target)


def test_module_keeps_every_third_party_import_inside_a_probe() -> None:
    """The stdlib-only replay only works because nothing heavy loads at import.

    A future top-level ``import numpy`` would still pass every other test here
    while silently breaking ``python -I -S`` replay, so the constraint is
    asserted structurally rather than left to convention.
    """
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    roots: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])
    assert roots <= ALLOWED_TOP_LEVEL_IMPORTS, sorted(roots - ALLOWED_TOP_LEVEL_IMPORTS)


# --------------------------------------------------------------------------- #
# EL-03 run-to-run determinism
# --------------------------------------------------------------------------- #


def test_two_captures_in_one_process_agree(measured_record: dict) -> None:
    again = capture_environment_lock()
    assert again["locked_sha256"] == measured_record["locked_sha256"]
    assert again["locked"] == measured_record["locked"]


def test_probe_inputs_are_exact_and_bounded() -> None:
    values = lcg_floats(64, 4242)
    assert len(values) == 64
    assert all(-1.0 <= value < 1.0 for value in values)
    assert values == lcg_floats(64, 4242)
    assert values != lcg_floats(64, 4243)
    # The mapping divides by a power of two, so every value round-trips exactly.
    assert all(float(repr(value)) == value for value in values)


def test_probe_input_count_must_be_positive() -> None:
    with pytest.raises(EnvironmentLockError):
        lcg_floats(0, 1)


def test_plant_probe_model_is_self_contained() -> None:
    """The probe must measure MuJoCo, not this repository's model code.

    Importing ``model_builder`` here would make every unrelated model edit read
    as an environment change, so the frozen inline MJCF is the whole model.
    """
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    assert not any(name.startswith("model_builder") for name in imported)
    assert "<mujoco" in lock_module.PLANT_PROBE_MJCF
    assert lock_module.PLANT_PROBE_STEPS > 0


# --------------------------------------------------------------------------- #
# EL-04 locked versus observed severity
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("section", "mutate", "expected_finding"),
    [
        (
            "interpreter",
            lambda locked: locked["interpreter"].update({"version": "3.9.0"}),
            "INTERPRETER_DRIFT",
        ),
        (
            "architecture",
            lambda locked: locked["architecture"].update({"machine": "aarch64"}),
            "ARCHITECTURE_DRIFT",
        ),
        (
            "distributions",
            lambda locked: locked["distributions"].update({"numpy": "0.0.1"}),
            "DISTRIBUTION_VERSION_DRIFT",
        ),
        (
            "distributions",
            lambda locked: locked["distributions"].update({"torch": {"state": "MISSING"}}),
            "DISTRIBUTION_MISSING",
        ),
        (
            "determinism_environment",
            lambda locked: locked["determinism_environment"].update(
                {"MKL_NUM_THREADS": {"state": "SET", "value": "8"}}
            ),
            "DETERMINISM_ENVIRONMENT_DRIFT",
        ),
        (
            "numeric_fingerprint",
            lambda locked: locked["numeric_fingerprint"].update({"numpy_dot": "0.0"}),
            "NUMERIC_FINGERPRINT_DRIFT",
        ),
        (
            "plant_fingerprint",
            lambda locked: locked["plant_fingerprint"].update(
                {"state_sha256": "sha256:" + "2" * 64}
            ),
            "PLANT_FINGERPRINT_DRIFT",
        ),
        (
            "learning_fingerprint",
            lambda locked: locked["learning_fingerprint"].update(
                {"rng_sha256": "sha256:" + "3" * 64}
            ),
            "LEARNING_FINGERPRINT_DRIFT",
        ),
    ],
)
def test_locked_drift_is_a_mismatch(
    measured_record: dict, section: str, mutate, expected_finding: str
) -> None:
    observed = deepcopy(measured_record)
    mutate(observed["locked"])
    _refreeze(observed)
    result = verify_environment_lock(measured_record, observed)
    assert result["environment_lock_match"] is False
    assert result["mismatch_count"] >= 1
    findings = [item for item in result["findings"] if item["severity"] == SEVERITY_MISMATCH]
    assert expected_finding in {item["finding_id"] for item in findings}
    assert all(item["section"] in LOCKED_SECTIONS for item in findings)


def test_observed_drift_is_retained_not_a_mismatch(measured_record: dict) -> None:
    observed = deepcopy(measured_record)
    observed["observed"]["cpu_count"] += 7
    observed["observed"]["executable"] = "/somewhere/else/python3"
    result = verify_environment_lock(measured_record, observed)
    assert result["environment_lock_match"] is True
    assert result["mismatch_count"] == 0
    assert result["retained_finding_count"] == 2
    assert {item["finding_id"] for item in result["findings"]} == {
        "OBSERVED_CONTEXT_DRIFT"
    }
    assert all(item["severity"] == SEVERITY_RETAINED for item in result["findings"])


def test_identical_records_verify_clean(measured_record: dict) -> None:
    result = verify_environment_lock(measured_record, deepcopy(measured_record))
    assert result["environment_lock_match"] is True
    assert result["findings"] == []


def test_findings_follow_the_frozen_registry_order(measured_record: dict) -> None:
    observed = deepcopy(measured_record)
    observed["locked"]["numeric_fingerprint"]["numpy_dot"] = "0.0"
    observed["locked"]["architecture"]["machine"] = "aarch64"
    observed["locked"]["interpreter"]["byteorder"] = "big"
    _refreeze(observed)
    sections = [
        item["section"]
        for item in verify_environment_lock(measured_record, observed)["findings"]
    ]
    assert sections == ["interpreter", "architecture", "numeric_fingerprint"]


def test_declared_completeness_drift_fails_closed(record: dict) -> None:
    record["lock_completeness"] = PARTIAL_LOCK
    with pytest.raises(EnvironmentLockError, match="lock_completeness does not match"):
        validate_lock_record(record)


def test_declared_threading_determinism_drift_fails_closed(record: dict) -> None:
    record["threading_determinism"] = "AMBIENT_THREADING_PINNED_BY_HAND"
    with pytest.raises(EnvironmentLockError, match="threading_determinism does not match"):
        validate_lock_record(record)


def test_threading_determinism_is_derived_from_the_locked_variable(record: dict) -> None:
    record["locked"]["determinism_environment"]["OMP_NUM_THREADS"] = {
        "state": "SET",
        "value": "1",
    }
    assert (
        validate_lock_record(_refreeze(record))["threading_determinism"]
        == "AMBIENT_THREADING_PINNED"
    )
    record["locked"]["determinism_environment"]["OMP_NUM_THREADS"] = {
        "state": "SET",
        "value": "4",
    }
    assert (
        validate_lock_record(_refreeze(record))["threading_determinism"]
        == "AMBIENT_THREADING_NOT_PINNED"
    )


# --------------------------------------------------------------------------- #
# EL-05 unset is not empty
# --------------------------------------------------------------------------- #


def test_unset_and_empty_environment_variable_are_distinct_states(
    measured_record: dict,
) -> None:
    expected = deepcopy(measured_record)
    expected["locked"]["determinism_environment"]["MUJOCO_GL"] = {"state": "UNSET"}
    _refreeze(expected)
    observed = deepcopy(expected)
    observed["locked"]["determinism_environment"]["MUJOCO_GL"] = {
        "state": "SET",
        "value": "",
    }
    _refreeze(observed)
    result = verify_environment_lock(expected, observed)
    assert result["environment_lock_match"] is False
    assert result["findings"][0]["finding_id"] == "DETERMINISM_ENVIRONMENT_DRIFT"


def test_unknown_environment_variable_state_fails_closed(record: dict) -> None:
    record["locked"]["determinism_environment"]["MUJOCO_GL"] = {"state": "PROBABLY_EGL"}
    with pytest.raises(EnvironmentLockError, match="must be UNSET or SET"):
        validate_lock_record(_refreeze(record))


def test_set_state_requires_a_string_value(record: dict) -> None:
    record["locked"]["determinism_environment"]["OMP_NUM_THREADS"] = {
        "state": "SET",
        "value": 1,
    }
    with pytest.raises(EnvironmentLockError, match="value must be a string"):
        validate_lock_record(_refreeze(record))


# --------------------------------------------------------------------------- #
# EL-06 partial locks
# --------------------------------------------------------------------------- #


def test_unavailable_fingerprint_downgrades_to_partial_lock(record: dict) -> None:
    record["locked"]["plant_fingerprint"] = {
        "state": "UNAVAILABLE",
        "reason": "mujoco import failed: ImportError: no module named mujoco",
    }
    validation = validate_lock_record(_refreeze(record))
    assert validation["lock_completeness"] == PARTIAL_LOCK
    assert satisfies_full_lock_requirement(record) is False


def test_missing_distribution_downgrades_to_partial_lock(record: dict) -> None:
    record["locked"]["distributions"]["stable-baselines3"] = {"state": "MISSING"}
    assert validate_lock_record(_refreeze(record))["lock_completeness"] == PARTIAL_LOCK
    assert satisfies_full_lock_requirement(record) is False


def test_full_lock_requirement_accepts_only_a_complete_measured_lock(
    record: dict,
) -> None:
    assert record["lock_completeness"] == FULL_LOCK
    assert satisfies_full_lock_requirement(record) is True


def test_fingerprint_availability_difference_is_a_mismatch(
    measured_record: dict,
) -> None:
    observed = deepcopy(measured_record)
    observed["locked"]["learning_fingerprint"] = {
        "state": "UNAVAILABLE",
        "reason": "torch import failed",
    }
    _refreeze(observed)
    result = verify_environment_lock(measured_record, observed)
    assert result["environment_lock_match"] is False
    assert result["findings"][0]["finding_id"] == "FINGERPRINT_UNAVAILABLE"
    assert result["observed_lock_completeness"] == PARTIAL_LOCK


def test_unavailable_fingerprint_requires_a_reason(record: dict) -> None:
    record["locked"]["plant_fingerprint"] = {"state": "UNAVAILABLE"}
    with pytest.raises(EnvironmentLockError, match="missing fields"):
        validate_lock_record(_refreeze(record))


# --------------------------------------------------------------------------- #
# EL-07 lock class binding, both directions
# --------------------------------------------------------------------------- #


def test_synthetic_lock_is_never_accepted_for_a_measured_one(
    measured_record: dict,
) -> None:
    synthetic = deepcopy(measured_record)
    synthetic["lock_class"] = SYNTHETIC_LOCK_CLASS
    result = verify_environment_lock(measured_record, synthetic)
    assert result["environment_lock_match"] is False
    assert result["lock_class_match"] is False
    assert result["findings"][0]["finding_id"] == "LOCK_CLASS_MISMATCH"
    assert satisfies_full_lock_requirement(synthetic) is False


def test_measured_lock_is_never_accepted_for_a_synthetic_one(
    measured_record: dict,
) -> None:
    synthetic = deepcopy(measured_record)
    synthetic["lock_class"] = SYNTHETIC_LOCK_CLASS
    result = verify_environment_lock(synthetic, measured_record)
    assert result["environment_lock_match"] is False
    assert result["expected_lock_class"] == SYNTHETIC_LOCK_CLASS
    assert result["observed_lock_class"] == MEASURED_LOCK_CLASS


def test_capture_refuses_to_mint_an_absent_record() -> None:
    with pytest.raises(EnvironmentLockError, match="capture requires"):
        capture_environment_lock(ABSENT_LOCK_CLASS)


def test_unknown_lock_class_fails_closed(record: dict) -> None:
    record["lock_class"] = "PROBABLY_FINE"
    with pytest.raises(EnvironmentLockError, match="unexpected lock_class"):
        validate_lock_record(record)


# --------------------------------------------------------------------------- #
# EL-08 absent locks
# --------------------------------------------------------------------------- #


def test_absent_record_holds_no_measurement() -> None:
    absent = absent_lock_record("v7 pilot predates ENVIRONMENT-LOCK-V1")
    validation = validate_lock_record(absent)
    assert validation["lock_completeness"] == NO_LOCK
    assert validation["locked_sha256"] is None
    assert "locked" not in absent
    assert "observed" not in absent
    assert satisfies_full_lock_requirement(absent) is False


def test_absent_record_cannot_be_verified() -> None:
    absent = absent_lock_record("environment not recoverable")
    with pytest.raises(EnvironmentLockError, match="carries no measurement"):
        verify_environment_lock(absent, deepcopy(absent))


def test_absent_record_requires_an_explicit_reason() -> None:
    with pytest.raises(EnvironmentLockError, match="explicit reason"):
        absent_lock_record("   ")


def test_absent_record_must_not_smuggle_a_digest() -> None:
    absent = absent_lock_record("environment not recoverable")
    absent["locked_sha256"] = "sha256:" + "4" * 64
    with pytest.raises(EnvironmentLockError, match="must not carry a digest"):
        validate_lock_record(absent)


def test_current_capture_cannot_stand_in_for_an_absent_lock(
    measured_record: dict,
) -> None:
    """Attaching today's environment to older evidence would be an imputation."""
    absent = absent_lock_record("v7 pilot predates ENVIRONMENT-LOCK-V1")
    result = verify_environment_lock(measured_record, absent)
    assert result["environment_lock_match"] is False
    assert result["findings"][0]["finding_id"] == "LOCK_CLASS_MISMATCH"


# --------------------------------------------------------------------------- #
# EL-09 strict finite JSON
# --------------------------------------------------------------------------- #


def test_non_finite_measurement_uses_a_typed_state() -> None:
    assert lock_module._measurement(float("nan")) == {
        "state": "NONFINITE",
        "kind": "nan",
    }
    assert lock_module._measurement(float("inf")) == {
        "state": "NONFINITE",
        "kind": "inf",
    }
    assert lock_module._measurement(float("-inf")) == {
        "state": "NONFINITE",
        "kind": "-inf",
    }
    assert lock_module._measurement(0.5) == "0.5"


def test_non_finite_float_text_is_rejected(record: dict) -> None:
    record["locked"]["numeric_fingerprint"]["numpy_dot"] = "nan"
    with pytest.raises(EnvironmentLockError, match="typed non-finite state"):
        validate_lock_record(_refreeze(record))


def test_typed_non_finite_measurement_validates(record: dict) -> None:
    record["locked"]["numeric_fingerprint"]["numpy_dot"] = {
        "state": "NONFINITE",
        "kind": "nan",
    }
    assert validate_lock_record(_refreeze(record))["record_valid"] is True


def test_record_file_rejects_non_finite_json_constants(tmp_path: Path) -> None:
    target = tmp_path / "lock.json"
    target.write_text('{"locked_sha256": NaN}', encoding="utf-8")
    with pytest.raises(EnvironmentLockError, match="non-finite JSON constant"):
        load_lock_record(target)


def test_record_file_rejects_duplicate_object_keys(tmp_path: Path) -> None:
    target = tmp_path / "lock.json"
    target.write_text('{"lock_class": "A", "lock_class": "B"}', encoding="utf-8")
    with pytest.raises(EnvironmentLockError, match="duplicate object keys"):
        load_lock_record(target)


def test_record_file_must_exist(tmp_path: Path) -> None:
    with pytest.raises(EnvironmentLockError, match="cannot read lock record"):
        load_lock_record(tmp_path / "absent.json")


def test_write_refuses_to_reuse_a_partial_artifact(tmp_path: Path, record: dict) -> None:
    target = tmp_path / "lock.json"
    (tmp_path / "lock.json.partial").write_text("stale", encoding="utf-8")
    with pytest.raises(EnvironmentLockError, match="partial artifact"):
        write_lock_record(target, record)


def test_written_record_round_trips(tmp_path: Path, record: dict) -> None:
    target = tmp_path / "lock.json"
    digest = write_lock_record(target, record)
    assert digest.startswith("sha256:")
    assert load_lock_record(target) == record


# --------------------------------------------------------------------------- #
# EL-10 CLI exit codes
# --------------------------------------------------------------------------- #


def _cli(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(MODULE_PATH), *arguments],
        capture_output=True,
        text=True,
        check=False,
        cwd=BACKEND_ROOT,
    )


def test_cli_capture_and_match_exit_zero(tmp_path: Path) -> None:
    target = tmp_path / "lock.json"
    captured = _cli("capture", str(target))
    assert captured.returncode == 0, captured.stderr
    payload = json.loads(captured.stdout)
    assert payload["record_valid"] is True
    assert payload["replay"]["replay_exact"] is True

    validated = _cli("validate", str(target))
    assert validated.returncode == 0, validated.stderr

    verified = _cli("verify", str(target), "--observed", str(target))
    assert verified.returncode == 0, verified.stderr
    assert json.loads(verified.stdout)["environment_lock_match"] is True


def test_cli_lock_mismatch_exits_one(tmp_path: Path, record: dict) -> None:
    expected = tmp_path / "expected.json"
    observed = tmp_path / "observed.json"
    write_lock_record(expected, record)
    drifted = deepcopy(record)
    drifted["locked"]["architecture"]["machine"] = "aarch64"
    write_lock_record(observed, _refreeze(drifted))
    result = _cli("verify", str(expected), "--observed", str(observed))
    assert result.returncode == 1, result.stderr
    payload = json.loads(result.stdout)
    assert payload["environment_lock_match"] is False
    assert payload["findings"][0]["finding_id"] == "ARCHITECTURE_DRIFT"


def test_cli_structural_failure_exits_two(tmp_path: Path) -> None:
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    result = _cli("validate", str(broken))
    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["validation_status"] == "STRUCTURAL_FAILURE"
    assert payload["record_valid"] is False
    assert payload["environment_lock_match"] is False


# --------------------------------------------------------------------------- #
# the tracked measured record
# --------------------------------------------------------------------------- #

TRACKED_RECORDS = sorted((BACKEND_ROOT / "environment_locks").glob("lock-*.json"))


def test_at_least_one_measured_record_is_tracked() -> None:
    assert TRACKED_RECORDS, "no ENVIRONMENT-LOCK-V1 record is committed"


@pytest.mark.parametrize("path", TRACKED_RECORDS, ids=lambda item: item.name)
def test_tracked_record_validates_anywhere(path: Path) -> None:
    """Validation is schema plus digest, so it must pass off the capture machine.

    A tracked record that only validated where it was captured would be useless
    as evidence: the point is that a reviewer on other hardware can check it.
    """
    tracked = load_lock_record(path)
    validation = validate_lock_record(tracked)
    assert validation["record_valid"] is True
    assert validation["lock_class"] == MEASURED_LOCK_CLASS
    assert replay_locked_digest(path)["replay_exact"] is True


@pytest.mark.parametrize("path", TRACKED_RECORDS, ids=lambda item: item.name)
def test_tracked_record_pins_match_the_constraints_file(path: Path) -> None:
    tracked = load_lock_record(path)
    constraints = BACKEND_ROOT / f"requirements-lock-{tracked['captured_at_utc'][:10]}.txt"
    if not constraints.exists():
        pytest.skip(f"no constraints file for {constraints.name}")
    pinned = dict(
        line.split("==", 1)
        for line in constraints.read_text(encoding="utf-8").splitlines()
        if "==" in line and not line.startswith("#")
    )
    measured = {
        name: version
        for name, version in tracked["locked"]["distributions"].items()
        if isinstance(version, str)
    }
    assert pinned == measured

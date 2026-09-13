"""Bind an ``ENVIRONMENT-LOCK-V1`` record to a retained run manifest.

``RUN-MANIFEST-LOCK-BINDING-V1``, frozen in
``docs/RUN_MANIFEST_LOCK_BINDING_SPEC.md`` and
``backend/run_manifest_lock_binding_protocol.json``.

A lock record that no run refers to proves only that some machine looked a
certain way at some moment.  It does not prove that a given piece of evidence
was produced on that machine.  This module builds the missing relation and
checks it fail-closed.

Three design points are load-bearing rather than incidental.

First, the binding is a *sidecar* record that pins its manifest by SHA-256, not
a field injected into the manifest.  Three producers cannot take an injected
field without making something that is true today false: editing
``rl/eval_policy.py`` turns a currently green test red, editing
``rl/train_ppo.py`` silently falsifies an executed protocol's pinned driver
digest, and editing ``simulator.py`` changes a deterministic content hash that
``test_p0_contract.py`` independently recomputes.  Specification sections 2.2,
2.3 and 3.4 record the measurements.

Second, two digests are kept under two names.  ``lock_record_sha256`` is the
lock file's bytes; ``environment_locked_sha256`` is the canonical digest of its
``locked`` subtree.  The name ``environment_lock_sha256`` is forbidden here
because it already carries the first quantity in one retained bundle and the
second in another, while both executions ran under records whose
``locked_sha256`` is identical.

Third, every top-level import is stdlib.  ``environment_lock`` is imported
lazily inside the builder, so the reading and checking path runs under
``python -I -S`` with no site packages at all.

Paths inside a binding record are canonical POSIX paths relative to the run's
root: the repository root for a run directory that lives in the tree, the bundle
root for a self-contained bundle, matching what every other artifact path in that
manifest is already relative to.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

CONTRACT_ID = "RUN-MANIFEST-LOCK-BINDING-V1"
RECORD_SCHEMA = "RUN_LOCK_BINDING_V1"
PROTOCOL_SCHEMA = "RUN_MANIFEST_LOCK_BINDING_PROTOCOL_V1"

# Pinned at the freeze, pushed before any producer was edited.  A mismatch is a
# method failure, never a silent re-pin.
PROTOCOL_SHA256 = "sha256:2e3bde9ad8a691a3242f6afac6d6189f5084fc0d42d632581fb0e8fbd51364f1"
SPECIFICATION_SHA256 = "sha256:1b3a7b26cd1e86807a3de66c9177bc2159c2f58e6d87701f552360152993ffdf"

BINDING_FILENAME = "run_lock_binding.json"
DEFAULT_PROTOCOL_PATH = Path(__file__).resolve().parent / "run_manifest_lock_binding_protocol.json"

MODE_EMBEDDED_AND_SIDECAR = "EMBEDDED_AND_SIDECAR"
MODE_SIDECAR_ONLY = "SIDECAR_ONLY"
BINDING_MODES = (MODE_EMBEDDED_AND_SIDECAR, MODE_SIDECAR_ONLY)

LABEL_BOUND = "RUN_LOCK_BOUND"
LABEL_UNBOUND = "RUN_LOCK_UNBOUND"
LABEL_INSUFFICIENT = "RUN_LOCK_INSUFFICIENT"
LABEL_MISMATCH = "RUN_LOCK_MISMATCH"
LABEL_METHOD_FAILURE = "RUN_LOCK_BINDING_METHOD_FAILURE"
LABELS = (LABEL_BOUND, LABEL_UNBOUND, LABEL_INSUFFICIENT, LABEL_MISMATCH, LABEL_METHOD_FAILURE)

# Specification section 4.1.  Never reintroduce this name: it means the lock
# file's bytes in backend/second_case_evidence/ and the locked subtree digest in
# backend/seed_variance_evidence/, and the two retained values differ for
# definitional rather than environmental reasons.
FORBIDDEN_FIELD_NAME = "environment_lock_sha256"

REQUIRED_LOCK_CLASS = "MEASURED_ENVIRONMENT_LOCK"
REQUIRED_LOCK_COMPLETENESS = "FULL_LOCK"

# Specification section 5.  The key set is exact in both directions.
RECORD_FIELDS = (
    "binding_mode",
    "bound_at_utc",
    "bound_manifest_path",
    "bound_manifest_schema_version",
    "bound_manifest_sha256",
    "claim_boundary",
    "contract_id",
    "environment_lock_class",
    "environment_lock_completeness",
    "environment_lock_threading_determinism",
    "environment_locked_sha256",
    "lock_record_path",
    "lock_record_sha256",
    "lock_verified_at_utc",
    "satisfies_full_lock_requirement",
    "schema_version",
    "sidecar_reason",
    "verified_before_run",
)

# Specification section 7.4: the subset a PAPER_RUN_MANIFEST_V2 carries inline.
EMBEDDED_LOCK_FIELDS = (
    "environment_lock_class",
    "environment_lock_completeness",
    "environment_lock_threading_determinism",
    "environment_locked_sha256",
    "lock_record_sha256",
    "satisfies_full_lock_requirement",
    "verified_before_run",
)

CLAIM_BOUNDARY = (
    "RUN-MANIFEST-LOCK-BINDING-V1 establishes only that this run manifest and one "
    "ENVIRONMENT-LOCK-V1 record are linked by a recomputable relation, and that the "
    "record is MEASURED and FULL_LOCK. It supports no statement about the correctness "
    "of any numeric result, any task PASS, any controller superiority, or any change "
    "to paper_data_ready, statistics_ready or method_level_power_ready; no physical "
    "feasibility, safety, sim-to-real or actuator claim; and no claim that the run "
    "reproduces on another machine. The lock detects environment differences; it does "
    "not guarantee cross-environment numeric identity. This is infrastructure, not "
    "evidence."
)

SHA256_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
UTC_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

MAX_JSON_BYTES = 4 * 1024 * 1024


class RunLockBindingError(RuntimeError):
    """Any contract violation.  Never downgraded to one of the other four labels."""


# --------------------------------------------------------------------------- #
# primitives
# --------------------------------------------------------------------------- #


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _reject_json_constant(value: str) -> Any:
    raise RunLockBindingError(f"JSON non-finite constant is forbidden: {value}")


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key, value in pairs:
        if key in payload:
            raise RunLockBindingError(f"duplicate JSON key is forbidden: {key}")
        payload[key] = value
    return payload


def load_json_object(path: Path, context: str) -> dict[str, Any]:
    """Read one UTF-8 JSON object with no duplicate keys and no non-finite values."""
    target = Path(path)
    try:
        if target.stat().st_size > MAX_JSON_BYTES:
            raise RunLockBindingError(f"{context} exceeds {MAX_JSON_BYTES} bytes")
        payload = json.loads(
            target.read_bytes().decode("utf-8"),
            parse_constant=_reject_json_constant,
            object_pairs_hook=_reject_duplicate_keys,
        )
    except RunLockBindingError:
        raise
    except (OSError, UnicodeError, ValueError, RecursionError) as exc:
        raise RunLockBindingError(f"unreadable {context}: {target.name}") from exc
    if not isinstance(payload, dict):
        raise RunLockBindingError(f"{context} root must be a JSON object")
    return payload


def safe_relative_path(value: Any, context: str) -> str:
    """A canonical POSIX path relative to the repository root, with no escape."""
    if not isinstance(value, str) or not value:
        raise RunLockBindingError(f"{context} must be a non-empty string")
    if "\\" in value:
        raise RunLockBindingError(f"{context} must use POSIX separators: {value!r}")
    pure = PurePosixPath(value)
    if pure.is_absolute() or ".." in pure.parts or "." in pure.parts:
        raise RunLockBindingError(f"{context} must not be absolute or contain . or ..: {value!r}")
    if value != pure.as_posix():
        raise RunLockBindingError(f"{context} must be canonical: {value!r}")
    return value


def _require_digest(value: Any, context: str) -> str:
    if not isinstance(value, str) or not SHA256_PATTERN.match(value):
        raise RunLockBindingError(f"{context} must match sha256:<64 lowercase hex>")
    return value


def _require_utc(value: Any, context: str) -> str:
    if not isinstance(value, str) or not UTC_PATTERN.match(value):
        raise RunLockBindingError(f"{context} must be YYYY-MM-DDTHH:MM:SSZ")
    return value


def _require_text(value: Any, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RunLockBindingError(f"{context} must be a non-empty string")
    return value


def _require_bool(value: Any, context: str) -> bool:
    # bool is a subclass of int; check the type, not truthiness.
    if not isinstance(value, bool):
        raise RunLockBindingError(f"{context} must be a JSON boolean")
    return value


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------------------- #
# protocol
# --------------------------------------------------------------------------- #


def load_protocol(
    path: Path | None = None,
    *,
    require_pinned_digest: bool = True,
) -> dict[str, Any]:
    target = Path(path) if path is not None else DEFAULT_PROTOCOL_PATH
    if require_pinned_digest:
        digest = sha256_file(target)
        if digest != PROTOCOL_SHA256:
            raise RunLockBindingError(
                f"protocol digest does not match the pin: expected {PROTOCOL_SHA256}, read {digest}"
            )
    protocol = load_json_object(target, "protocol")
    if protocol.get("schema_version") != PROTOCOL_SCHEMA:
        raise RunLockBindingError("unexpected protocol schema_version")
    if protocol.get("contract_id") != CONTRACT_ID:
        raise RunLockBindingError("unexpected protocol contract_id")
    if protocol.get("specification_sha256") != SPECIFICATION_SHA256:
        raise RunLockBindingError("protocol specification_sha256 does not match the pin")
    return protocol


# --------------------------------------------------------------------------- #
# record validation
# --------------------------------------------------------------------------- #


def validate_binding_record(record: Any) -> dict[str, Any]:
    """Fail-closed schema check.  Says nothing about whether the manifest matches."""
    if not isinstance(record, dict):
        raise RunLockBindingError("binding record must be a JSON object")
    if FORBIDDEN_FIELD_NAME in record:
        raise RunLockBindingError(
            f"{FORBIDDEN_FIELD_NAME} is forbidden: it names two different quantities in "
            "two retained bundles (specification section 4.1)"
        )
    keys = tuple(sorted(record))
    if keys != RECORD_FIELDS:
        missing = sorted(set(RECORD_FIELDS) - set(keys))
        extra = sorted(set(keys) - set(RECORD_FIELDS))
        raise RunLockBindingError(f"binding record key set mismatch: missing={missing} extra={extra}")

    if record["schema_version"] != RECORD_SCHEMA:
        raise RunLockBindingError("unexpected binding record schema_version")
    if record["contract_id"] != CONTRACT_ID:
        raise RunLockBindingError("unexpected binding record contract_id")

    mode = record["binding_mode"]
    if mode not in BINDING_MODES:
        raise RunLockBindingError(f"unexpected binding_mode: {mode!r}")
    reason = record["sidecar_reason"]
    if mode == MODE_SIDECAR_ONLY:
        _require_text(reason, "sidecar_reason")
    elif reason is not None:
        raise RunLockBindingError("sidecar_reason must be null when binding_mode is embedded")

    safe_relative_path(record["bound_manifest_path"], "bound_manifest_path")
    safe_relative_path(record["lock_record_path"], "lock_record_path")
    _require_text(record["bound_manifest_schema_version"], "bound_manifest_schema_version")
    _require_digest(record["bound_manifest_sha256"], "bound_manifest_sha256")
    _require_digest(record["lock_record_sha256"], "lock_record_sha256")
    _require_digest(record["environment_locked_sha256"], "environment_locked_sha256")
    _require_text(record["environment_lock_class"], "environment_lock_class")
    _require_text(record["environment_lock_completeness"], "environment_lock_completeness")
    _require_text(
        record["environment_lock_threading_determinism"],
        "environment_lock_threading_determinism",
    )
    _require_text(record["claim_boundary"], "claim_boundary")
    _require_utc(record["lock_verified_at_utc"], "lock_verified_at_utc")
    _require_utc(record["bound_at_utc"], "bound_at_utc")
    satisfies = _require_bool(record["satisfies_full_lock_requirement"], "satisfies_full_lock_requirement")
    _require_bool(record["verified_before_run"], "verified_before_run")

    # The flag is derived, not declared: a record may not claim a full lock while
    # reporting a class or completeness that cannot support one.
    derived = (
        record["environment_lock_class"] == REQUIRED_LOCK_CLASS
        and record["environment_lock_completeness"] == REQUIRED_LOCK_COMPLETENESS
    )
    if satisfies != derived:
        raise RunLockBindingError(
            "satisfies_full_lock_requirement disagrees with the recorded class and "
            f"completeness: declared {satisfies}, derived {derived}"
        )
    return record


def embedded_lock_block(record: dict[str, Any]) -> dict[str, Any]:
    """The subset a ``PAPER_RUN_MANIFEST_V2`` carries inline (section 7.4)."""
    validate_binding_record(record)
    return {field: record[field] for field in EMBEDDED_LOCK_FIELDS}


def lock_block_from_record(
    lock_record_path: Path,
    *,
    verified_before_run: bool,
) -> dict[str, Any]:
    """The same inline block, derived from a lock record alone.

    A manifest must carry the block *before* it is written, while the sidecar can
    only pin the manifest once its final bytes exist.  Deriving the block here
    keeps that ordering honest instead of building a throwaway binding first.
    """
    import environment_lock as el

    lock_file = Path(lock_record_path).resolve()
    pinned = el.load_lock_record(lock_file)
    validation = el.validate_lock_record(pinned)
    return {
        "environment_lock_class": validation["lock_class"],
        "environment_lock_completeness": validation["lock_completeness"],
        "environment_lock_threading_determinism": validation["threading_determinism"],
        "environment_locked_sha256": validation["locked_sha256"],
        "lock_record_sha256": sha256_file(lock_file),
        "satisfies_full_lock_requirement": el.satisfies_full_lock_requirement(pinned),
        "verified_before_run": verified_before_run,
    }


# --------------------------------------------------------------------------- #
# building
# --------------------------------------------------------------------------- #


def build_binding_record(
    *,
    root: Path,
    manifest_path: Path,
    manifest_schema_version: str,
    lock_record_path: Path,
    binding_mode: str,
    sidecar_reason: str | None,
    verified_before_run: bool,
    lock_verified_at_utc: str,
    bound_at_utc: str | None = None,
) -> dict[str, Any]:
    """Assemble a ``RUN_LOCK_BINDING_V1`` record for a manifest already written.

    ``environment_lock`` is imported here rather than at module scope so the
    reading and checking path stays stdlib-only.
    """
    import environment_lock as el

    run_root = Path(root).resolve()
    manifest = Path(manifest_path).resolve()
    lock_file = Path(lock_record_path).resolve()
    for target, label in ((manifest, "manifest"), (lock_file, "lock record")):
        if not target.is_file():
            raise RunLockBindingError(f"{label} is not an existing file: {target}")
        if not target.is_relative_to(run_root):
            raise RunLockBindingError(f"{label} must live inside the run root: {target}")

    pinned = el.load_lock_record(lock_file)
    validation = el.validate_lock_record(pinned)

    record = {
        "schema_version": RECORD_SCHEMA,
        "contract_id": CONTRACT_ID,
        "binding_mode": binding_mode,
        "sidecar_reason": sidecar_reason,
        "bound_manifest_path": manifest.relative_to(run_root).as_posix(),
        "bound_manifest_schema_version": manifest_schema_version,
        "bound_manifest_sha256": sha256_file(manifest),
        "lock_record_path": lock_file.relative_to(run_root).as_posix(),
        "lock_record_sha256": sha256_file(lock_file),
        "environment_locked_sha256": validation["locked_sha256"],
        "environment_lock_class": validation["lock_class"],
        "environment_lock_completeness": validation["lock_completeness"],
        "environment_lock_threading_determinism": validation["threading_determinism"],
        "satisfies_full_lock_requirement": el.satisfies_full_lock_requirement(pinned),
        "verified_before_run": verified_before_run,
        "lock_verified_at_utc": lock_verified_at_utc,
        "bound_at_utc": bound_at_utc or _utc_now(),
        "claim_boundary": CLAIM_BOUNDARY,
    }
    return validate_binding_record(record)


def serialize_binding_record(record: dict[str, Any]) -> str:
    validate_binding_record(record)
    return json.dumps(record, indent=1, sort_keys=True) + "\n"


def write_binding_record(run_dir: Path, record: dict[str, Any]) -> Path:
    """Write ``run_lock_binding.json`` beside the manifest it binds."""
    target = Path(run_dir) / BINDING_FILENAME
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(serialize_binding_record(record), encoding="utf-8")
    return target


# --------------------------------------------------------------------------- #
# capture before the run
# --------------------------------------------------------------------------- #


def capture_lock_for_run(
    run_root: Path,
    *,
    pinned_lock_record_path: Path | None = None,
    filename: str = "environment_lock.json",
    require_full_lock: bool = False,
) -> dict[str, Any]:
    """Measure the environment *before* the run and retain the record with it.

    Specification section 6.1: capturing at manifest-assembly time would record
    the environment at write time rather than the one that produced the data, and
    the difference between the two is exactly what this lock exists to detect.

    With a pinned record, re-measure and require identity with it, the discipline
    ``rl/second_case_runner.verify_lock_now`` already uses.  Without one, the
    fresh measurement *is* the record for this run.

    ``require_full_lock`` implements section 6.2: a run governed by a frozen
    protocol refuses to start below MEASURED + FULL_LOCK, while a smoke or
    development run records its measured class truthfully and proceeds.
    """
    import environment_lock as el

    verified_at = _utc_now()
    observed = el.capture_environment_lock()
    verification: dict[str, Any] | None = None
    if pinned_lock_record_path is not None:
        pinned = el.load_lock_record(Path(pinned_lock_record_path))
        verification = el.verify_environment_lock(pinned, observed)
        if verification.get("environment_lock_match") is not True:
            raise RunLockBindingError(
                "RUN_LOCK_ENVIRONMENT_MISMATCH: this environment is not the pinned one "
                f"({verification.get('mismatch_count')} mismatches, "
                f"{verification.get('retained_finding_count')} retained findings)"
            )
        record = pinned
    else:
        record = observed

    if require_full_lock and not el.satisfies_full_lock_requirement(record):
        validation = el.validate_lock_record(record)
        raise RunLockBindingError(
            "RUN_LOCK_NOT_FULL: a protocol-governed run requires "
            f"{REQUIRED_LOCK_CLASS} / {REQUIRED_LOCK_COMPLETENESS}, measured "
            f"{validation['lock_class']} / {validation['lock_completeness']}"
        )

    target = Path(run_root) / filename
    target.parent.mkdir(parents=True, exist_ok=True)
    el.write_lock_record(target, record)
    return {
        "lock_record_path": target,
        "lock_verified_at_utc": verified_at,
        "verified_before_run": True,
        "verification": verification,
    }

# --------------------------------------------------------------------------- #
# the analysis-time gate
# --------------------------------------------------------------------------- #


def _result(label: str, detail: str, record: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "schema_version": "RUN_LOCK_BINDING_RESULT_V1",
        "contract_id": CONTRACT_ID,
        "label": label,
        "detail": detail,
        "binding": record,
    }


def evaluate_run(
    run_dir: Path,
    manifest_filename: str,
    *,
    root: Path,
) -> dict[str, Any]:
    """Classify one run directory into exactly one of the five frozen labels.

    Returns a label rather than raising, because ``RUN_LOCK_UNBOUND`` and
    ``RUN_LOCK_INSUFFICIENT`` are results.  A contract violation still becomes
    ``RUN_LOCK_BINDING_METHOD_FAILURE`` and is never any of the other four.
    """
    try:
        run_root = Path(root).resolve()
        directory = Path(run_dir).resolve()
        binding_path = directory / BINDING_FILENAME
        if not binding_path.is_file():
            return _result(
                LABEL_UNBOUND,
                f"no {BINDING_FILENAME} in {directory}",
            )
        record = validate_binding_record(load_json_object(binding_path, "binding record"))

        manifest_path = directory / manifest_filename
        if not manifest_path.is_file():
            raise RunLockBindingError(f"bound manifest is missing: {manifest_path}")
        declared = record["bound_manifest_path"]
        actual = manifest_path.resolve().relative_to(run_root).as_posix()
        if declared != actual:
            return _result(
                LABEL_MISMATCH,
                f"bound_manifest_path points at {declared!r}, checked {actual!r}",
                record,
            )
        digest = sha256_file(manifest_path)
        if digest != record["bound_manifest_sha256"]:
            return _result(
                LABEL_MISMATCH,
                f"manifest digest {digest} does not match the binding's "
                f"{record['bound_manifest_sha256']}",
                record,
            )
        if record["satisfies_full_lock_requirement"] is not True:
            return _result(
                LABEL_INSUFFICIENT,
                f"lock is {record['environment_lock_class']} / "
                f"{record['environment_lock_completeness']}, which is below "
                f"{REQUIRED_LOCK_CLASS} / {REQUIRED_LOCK_COMPLETENESS}",
                record,
            )
        return _result(LABEL_BOUND, "binding verified against the manifest", record)
    except RunLockBindingError as exc:
        return _result(LABEL_METHOD_FAILURE, str(exc))


def require_bound_run(
    run_dir: Path,
    manifest_filename: str,
    *,
    root: Path,
) -> dict[str, Any]:
    """Fail closed unless the run is ``RUN_LOCK_BOUND``.

    ``RUN_LOCK_UNBOUND`` and ``RUN_LOCK_INSUFFICIENT`` are reported faithfully by
    ``evaluate_run``; neither is a pass, so both raise here.
    """
    outcome = evaluate_run(run_dir, manifest_filename, root=root)
    if outcome["label"] != LABEL_BOUND:
        raise RunLockBindingError(f"{outcome['label']}: {outcome['detail']}")
    return outcome

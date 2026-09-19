"""Run a pipeline driver under a verified environment lock, without editing it.

``RUN-MANIFEST-LOCK-BINDING-V1``, the ``SIDECAR_ONLY`` half.  Specification
sections 2.2, 2.3 and 3.2.

``rl/train_ppo.py`` and ``rl/eval_policy.py`` cannot take an injected lock field:
one of them is re-hashed by a test against a digest pinned in a protocol the
project owner authorized, and the other is pinned by an executed protocol that
nothing re-derives at runtime.  Editing either would make something that is true
today false.  So this wrapper measures the environment *before* the driver
starts, runs the driver untouched as a subprocess, and then binds the lock to
whatever manifest the driver produced by pinning that manifest's bytes.

The binding mode and its reason are not free text: they are read out of the
frozen protocol by producer path, so the wrapper cannot quietly claim a weaker
reason than the one that was frozen.

Usage::

    python rl/bind_run_lock.py \\
        --producer backend/rl/train_ppo.py \\
        --run-dir backend/rl/artifacts/<run_id> \\
        --manifest run_manifest.json \\
        [--lock-record backend/environment_locks/<pinned>.json] \\
        [--require-full-lock] \\
        -- python rl/train_ppo.py --profile ... --run-id <run_id>

``--lock-record`` pins the environment: the run refuses to start unless this
machine is identical to the record.  ``--require-full-lock`` is the section 6.2
rule for a protocol-governed run: refuse to start below MEASURED + FULL_LOCK.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import run_manifest_lock as rml  # noqa: E402

LOCK_FILENAME = "environment_lock.json"


def _producer_entry(producer: str) -> dict:
    """The frozen binding mode and reason for this producer, or fail closed."""
    protocol = rml.load_protocol()
    for entry in protocol["producers_in_scope"]:
        if entry["producer"] == producer:
            return entry
    known = sorted(item["producer"] for item in protocol["producers_in_scope"])
    raise rml.RunLockBindingError(
        f"{producer!r} is not a producer in scope of {rml.CONTRACT_ID}; known: {known}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--producer", required=True, help="repository-relative producer path")
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--manifest", default="run_manifest.json")
    parser.add_argument("--lock-record", type=Path, default=None)
    parser.add_argument("--require-full-lock", action="store_true")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)

    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("a driver command is required after --")

    entry = _producer_entry(args.producer)

    # Section 6.1: measure before the driver starts, into a staging file, because
    # train_ppo.py creates its run directory with exist_ok=False as an overwrite gate.
    staging = Path(tempfile.mkdtemp(prefix="run-lock-"))
    try:
        capture = rml.capture_lock_for_run(
            staging,
            pinned_lock_record_path=args.lock_record,
            filename=LOCK_FILENAME,
            require_full_lock=args.require_full_lock,
        )
        staged_lock = capture["lock_record_path"]

        completed = subprocess.run(command, cwd=str(BACKEND))
        if completed.returncode != 0:
            print(
                f"driver exited {completed.returncode}; no binding written",
                file=sys.stderr,
            )
            return completed.returncode

        run_dir = Path(args.run_dir).resolve()
        manifest_path = run_dir / args.manifest
        if not manifest_path.is_file():
            print(f"driver produced no {manifest_path}", file=sys.stderr)
            return 1

        lock_path = run_dir / LOCK_FILENAME
        shutil.copyfile(staged_lock, lock_path)
        binding = rml.build_binding_record(
            root=REPO_ROOT,
            manifest_path=manifest_path,
            manifest_schema_version=str(
                rml.load_json_object(manifest_path, "manifest").get("schema_version")
            ),
            lock_record_path=lock_path,
            binding_mode=entry["binding_mode"],
            sidecar_reason=entry["sidecar_reason"],
            verified_before_run=capture["verified_before_run"],
            lock_verified_at_utc=capture["lock_verified_at_utc"],
        )
        rml.write_binding_record(run_dir, binding)
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    outcome = rml.evaluate_run(run_dir, args.manifest, root=REPO_ROOT)
    print(f"{outcome['label']}: {outcome['detail']}")
    print(f"  lock_record_sha256       {binding['lock_record_sha256']}")
    print(f"  environment_locked_sha256 {binding['environment_locked_sha256']}")
    print(f"  bound_manifest_sha256    {binding['bound_manifest_sha256']}")
    return 0 if outcome["label"] == rml.LABEL_BOUND else 1


if __name__ == "__main__":
    sys.exit(main())

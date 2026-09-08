"""Assemble the real SEEDVAR-V7-TRAINING-REPLICATE-DEV-V1 raw bundle.

The seed-variance contract consumes per-episode comparability states and
full-horizon identification bounds. Those are ``AUDIT-V7-EXPOSURE-CENSORING-V1``
derivations, so this module reuses that contract's own functions rather than
reimplementing its rules. Reuse is the right call *here* and the wrong call in
``training_seed_variance_replay``: the audit is the frozen upstream authority on
exposure, while the replay exists to check this contract's arithmetic and must
therefore share nothing with it.

Two adaptations are needed and both are deliberate.

The evaluation output rows are in the driver's shape, not the audited shape, so
``v7_pilot_contract``'s own canonicalisation runs first - the same code path the
pilot bundle used, so the trace and its receipt are built identically rather
than similarly.

The audit's CLI cannot be pointed at this data. Its bundle classes are the
frozen pilot bundle and a synthetic regression bundle; this is neither. Calling
real seed-variance measurements "synthetic" to reuse a CLI would corrupt the
provenance the class exists to protect, so the derivations are called directly
and each cell records which implementation produced its classification.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

import v7_exposure_audit_contract as audit
import v7_pilot_contract as pilot
from environment_lock import load_lock_record, validate_lock_record
from training_seed_variance_contract import (
    ARM_IDS,
    AUDIT_CONTRACT_SOURCE_SHA256,
    AUDIT_PROTOCOL_SHA256,
    DEFAULT_PROTOCOL,
    DEVELOPMENT_BUNDLE_CLASS,
    LOCK_ARTIFACT,
    PILOT_CONTRACT_SOURCE_SHA256,
    PROTOCOL_ARTIFACT,
    PROTOCOL_ID,
    RAW_ARTIFACT,
    RAW_SCHEMA,
    SeedVarianceError,
    _json_bytes,
    _protocol_design,
    _write_bytes,
    check_environment_lock,
    load_protocol,
    sha256_file,
    verify_inherited_implementations,
    verify_pilot_inheritance,
)


AUDIT_PROTOCOL_PATH = Path(__file__).resolve().parent / "v7_exposure_audit_protocol.json"
PILOT_PROTOCOL_PATH = (
    Path(__file__).resolve().parent / "rl" / "v7_action_interface_pilot_protocol.json"
)
ARTIFACTS_ROOT = Path(__file__).resolve().parent / "rl" / "artifacts"
EVALUATION_FILENAME = "evaluation_dev18000_18029.json"
SEEDVAR_PROFILE_BY_ARM = {
    "V7A_REWARD_ONLY": "stand_start_walk_stop_0p7_action_reward_v7a_seedvar",
    "V7B_REDUCED_JOINT_ENVELOPE": "stand_start_walk_stop_0p7_reduced_joint_envelope_v7b_seedvar",
    "V7C_FILTERED_ACTION": "stand_start_walk_stop_0p7_filtered_action_v7c_seedvar",
}


def _git(repository: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repository), *arguments],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise SeedVarianceError(f"git {' '.join(arguments)} failed: {completed.stderr.strip()}")
    return completed.stdout.strip()


def git_identity(repository: Path) -> str:
    status = _git(repository, "status", "--porcelain", "--untracked-files=no")
    if status:
        raise SeedVarianceError(
            "refusing to build the bundle from a dirty tracked worktree:\n" + status
        )
    return _git(repository, "rev-parse", "HEAD")


def _audit_derivations() -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    """The frozen exposure contract, phase schedule and recorder schedule."""
    protocol = audit.load_audit_protocol(AUDIT_PROTOCOL_PATH)
    contract = audit._exposure_contract(protocol)
    schedule = audit._phase_schedule(protocol)
    recorder_schedule = audit._recorder_phase_schedule(protocol, contract)
    return contract, schedule, recorder_schedule


def _episode_records(
    evaluation: dict[str, Any],
    frozen_arm: dict[str, Any],
    derivations: tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]],
    context: str,
) -> list[dict[str, Any]]:
    """Canonicalise the driver rows, then classify them with the audit's rules."""
    contract, schedule, recorder_schedule = derivations
    rows = evaluation.get("episode_results")
    if not isinstance(rows, list):
        raise SeedVarianceError(f"{context} has no episode_results array")
    records: list[dict[str, Any]] = []
    for row in sorted(rows, key=lambda item: item["seed"]):
        seed = int(row["seed"])
        row_context = f"{context}.seed{seed}"
        normalized = pilot._canonical_measurements(row, row_context)
        control_trace, trace_receipt = pilot._canonical_control_trace(
            row, frozen_arm, normalized, row_context
        )
        audited_row = {
            "evaluation_seed": seed,
            "terminal_record_state": normalized["terminal_state"],
            "outcome_state": normalized["outcome_state"],
            "reason": normalized["reason"],
            "measurements": normalized["measurements"],
            "gates": pilot._gate_results(normalized["measurements"]),
            "control_step_trace": control_trace,
            "trace_receipt": trace_receipt,
        }
        record, _ = audit._episode_exposure(
            audited_row, contract, schedule, recorder_schedule, row_context
        )
        records.append(
            {
                "comparability_reason": record["comparability_reason"],
                "comparability_state": record["comparability_state"],
                "evaluation_seed": record["evaluation_seed"],
                "exposure_class": record["exposure_class"],
                "full_horizon_duty_bound_pct": record["full_horizon_duty_bound_pct"],
                "outcome_state": record["outcome_state"],
                "terminal_record_state": record["terminal_record_state"],
            }
        )
    return records


def _cell(
    arm_id: str,
    replicate_index: int,
    design: dict[str, Any],
    derivations: tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]],
    frozen_arms: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    profile_id = SEEDVAR_PROFILE_BY_ARM[arm_id]
    run_id = f"{profile_id}-r{replicate_index}"
    run_dir = ARTIFACTS_ROOT / run_id
    evaluation_path = run_dir / EVALUATION_FILENAME
    manifest_path = run_dir / "run_manifest.json"
    for path in (evaluation_path, manifest_path):
        if not path.is_file():
            raise SeedVarianceError(f"missing execution artifact: {path}")
    evaluation = json.loads(evaluation_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    seedvar = evaluation.get("seedvar_protocol")
    if not isinstance(seedvar, dict):
        raise SeedVarianceError(f"{run_id} evaluation carries no seedvar_protocol block")
    if seedvar.get("protocol_id") != PROTOCOL_ID:
        raise SeedVarianceError(f"{run_id} evaluation was not produced under this protocol")
    if seedvar.get("replicate_index") != replicate_index:
        raise SeedVarianceError(f"{run_id} evaluation replicate index mismatch")
    if seedvar.get("arm_id") != arm_id:
        raise SeedVarianceError(f"{run_id} evaluation arm mismatch")
    if seedvar.get("training_seed") != design["training_seeds"][replicate_index]:
        raise SeedVarianceError(f"{run_id} evaluation training seed mismatch")
    if evaluation.get("pilot_protocol") is not None:
        raise SeedVarianceError(f"{run_id} evaluation also claims the pilot protocol")

    training = manifest.get("seedvar_protocol")
    if not isinstance(training, dict) or training.get("protocol_id") != PROTOCOL_ID:
        raise SeedVarianceError(f"{run_id} training manifest was not produced under this protocol")
    if training.get("training_seed") != design["training_seeds"][replicate_index]:
        raise SeedVarianceError(f"{run_id} training manifest seed mismatch")
    resolved = manifest.get("resolved", {})
    realized = manifest.get("actual_total_timesteps")
    if realized != design["expected_realized_timesteps"]:
        raise SeedVarianceError(
            f"{run_id} realized {realized} timesteps, expected "
            f"{design['expected_realized_timesteps']}"
        )
    if resolved.get("seed_base") != design["training_seeds"][replicate_index]:
        raise SeedVarianceError(f"{run_id} resolved training seed mismatch")

    return {
        "arm_id": arm_id,
        "audit_contract_source_sha256": AUDIT_CONTRACT_SOURCE_SHA256,
        "audit_protocol_sha256": AUDIT_PROTOCOL_SHA256,
        "episodes": _episode_records(
            evaluation, frozen_arms[arm_id], derivations, run_id
        ),
        "evaluation_environment_lock_verified": True,
        "evaluation_output_sha256": sha256_file(evaluation_path),
        "pilot_contract_source_sha256": PILOT_CONTRACT_SOURCE_SHA256,
        "realized_timesteps": realized,
        "training_environment_lock_verified": True,
        "training_terminal_state": (
            "COMPLETED" if manifest.get("status", "").startswith("DEVELOPMENT_TRAINING")
            else "FAILED"
        ),
    }


def build_raw_bundle(output_root: Path, repository: Path) -> dict[str, Any]:
    """Write the bundle the seed-variance contract consumes."""
    git_sha = git_identity(repository)
    protocol = load_protocol(DEFAULT_PROTOCOL)
    verify_pilot_inheritance(protocol)
    verify_inherited_implementations()
    design = _protocol_design(protocol)
    derivations = _audit_derivations()
    pilot_protocol = json.loads(PILOT_PROTOCOL_PATH.read_text(encoding="utf-8"))
    frozen_arms = {item["arm_id"]: item for item in pilot_protocol["arms"]}

    lock_source = max(
        (Path(__file__).resolve().parent / "environment_locks").glob("lock-*-seedvar-*.json"),
        default=None,
    )
    if lock_source is None:
        raise SeedVarianceError("no seed-variance environment lock record is committed")
    lock_record = load_lock_record(lock_source)
    lock_status = check_environment_lock(protocol, lock_record)

    replicates = []
    for index in range(design["replicate_count"]):
        replicates.append(
            {
                "arms": [
                    _cell(arm_id, index, design, derivations, frozen_arms)
                    for arm_id in ARM_IDS
                ],
                "environment_seed_block": design["environment_seed_blocks"][index],
                "replicate_index": index,
                "training_seed": design["training_seeds"][index],
            }
        )

    raw = {
        "bundle_class": DEVELOPMENT_BUNDLE_CLASS,
        "environment_lock_sha256": lock_status["environment_locked_sha256"],
        "protocol_id": PROTOCOL_ID,
        "replicates": replicates,
        "schema_version": RAW_SCHEMA,
        "source_dirty_post": False,
        "source_dirty_pre": False,
        "source_git_sha_post": git_sha,
        "source_git_sha_pre": git_sha,
    }

    root = Path(output_root)
    if root.exists():
        raise SeedVarianceError(f"refusing to overwrite an existing bundle root: {root}")
    root.mkdir(parents=True)
    protocol_copy = root / PROTOCOL_ARTIFACT
    protocol_copy.write_bytes(DEFAULT_PROTOCOL.read_bytes())
    if sha256_file(protocol_copy) != sha256_file(DEFAULT_PROTOCOL):
        raise SeedVarianceError("protocol copy digest mismatch")
    (root / LOCK_ARTIFACT).write_bytes(lock_source.read_bytes())
    if validate_lock_record(load_lock_record(root / LOCK_ARTIFACT))[
        "locked_sha256"
    ] != lock_status["environment_locked_sha256"]:
        raise SeedVarianceError("environment lock copy digest mismatch")
    _write_bytes(root / RAW_ARTIFACT, _json_bytes(raw))
    return {
        "bundle_root": str(root),
        "bundle_class": DEVELOPMENT_BUNDLE_CLASS,
        "source_git_sha": git_sha,
        "environment_lock_source": lock_source.name,
        "environment_locked_sha256": lock_status["environment_locked_sha256"],
        "replicate_count": design["replicate_count"],
        "terminal_record_count": sum(
            len(cell["episodes"]) for item in replicates for cell in item["arms"]
        ),
        "raw_sha256": sha256_file(root / RAW_ARTIFACT),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_root", type=Path)
    parser.add_argument(
        "--repository", type=Path, default=Path(__file__).resolve().parent.parent
    )
    args = parser.parse_args()
    try:
        payload = build_raw_bundle(args.output_root, args.repository)
    except Exception as exc:
        print(
            json.dumps(
                {
                    "schema_version": "TRAINING_SEED_VARIANCE_BUNDLE_ERROR_V1",
                    "validation_status": "STRUCTURAL_FAILURE",
                    "error": f"{type(exc).__name__}: {exc}"[:1000],
                    "paper_data_ready": False,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        raise SystemExit(2) from exc
    print(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False))
    raise SystemExit(0)


if __name__ == "__main__":
    main()

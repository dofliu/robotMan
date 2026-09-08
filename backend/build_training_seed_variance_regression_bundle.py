"""Synthetic regression bundles for SEEDVAR-V7-TRAINING-REPLICATE-DEV-V1.

No training runs here.  The purpose is to prove the evidence contract behaves
correctly on the three cases that decide whether its output can be trusted:

``all-comparable``
    Every cell fully exposed, so the method-level bound is degenerate and
    ``between_replicate_sd`` is a point value.  The happy path.

``censored-candidate``
    One candidate is truncated in every replicate, mirroring what the exposure
    audit actually measured for V7C.  The bound must widen, the sign must
    become unidentified, and the SD must be withheld rather than estimated from
    interval midpoints.

``method-failure``
    One cell contains a method failure.  It has no mean at all, so the
    method-level bound must go NULL rather than quietly dropping the failure.

Every bundle is stamped ``SYNTHETIC_REGRESSION_BUNDLE``.  This builder cannot
emit the development class: software verified on synthetic rows is not
development evidence, and the two must never be confusable downstream.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any

from environment_lock import (
    MEASURED_LOCK_CLASS,
    THREADING_PINNED,
    capture_environment_lock,
    validate_lock_record,
    write_lock_record,
)
from training_seed_variance_contract import (
    ARM_IDS,
    AUDIT_CONTRACT_SOURCE_SHA256,
    AUDIT_PROTOCOL_SHA256,
    CANDIDATE_ARM_IDS,
    DEFAULT_PROTOCOL,
    LOCK_ARTIFACT,
    PROTOCOL_ARTIFACT,
    PILOT_CONTRACT_SOURCE_SHA256,
    PROTOCOL_ID,
    RAW_ARTIFACT,
    RAW_SCHEMA,
    REFERENCE_ARM_ID,
    SYNTHETIC_BUNDLE_CLASS,
    SeedVarianceError,
    analyse_seed_variance,
    load_protocol,
    sha256_file,
    _json_bytes,
    _protocol_design,
    _round_percent,
    _write_bytes,
)


PACKAGE_RECEIPT_SCHEMA = "TRAINING_SEED_VARIANCE_REGRESSION_PACKAGE_V1"

# Anchored on the exposure audit's measured v7 values so the fixtures exercise
# the same magnitudes the real bundle produced, not arbitrary ones.
ARM_BASE_DUTY_PCT = {
    "V7A_REWARD_ONLY": 36.2185185,
    "V7B_REDUCED_JOINT_ENVELOPE": 23.3896264,
    "V7C_FILTERED_ACTION": 21.5,
}
ARM_SPREAD_PCT = {
    "V7A_REWARD_ONLY": 1.0328300,
    "V7B_REDUCED_JOINT_ENVELOPE": 1.0044698,
    "V7C_FILTERED_ACTION": 1.1,
}
# Replicate offsets are the point of the exercise: they are the between-seed
# shifts a single-seed pilot cannot see. They must differ *per arm*. A common
# offset is exactly what pairing removes, so a fixture that shifted all three
# arms together would cancel in the contrast, make the pairing look perfectly
# effective, and never exercise between-replicate variance at all.
REPLICATE_OFFSET_PCT = {
    "V7A_REWARD_ONLY": (0.0, 0.62, -0.41, 1.05, -0.86),
    "V7B_REDUCED_JOINT_ENVELOPE": (0.0, 1.94, -1.37, -0.58, 2.11),
    "V7C_FILTERED_ACTION": (0.0, -1.22, 2.05, 0.74, -1.63),
}
CENSORED_EXPOSURE_FRACTION = 0.354889
DUTY_DECIMALS = 6


def _lcg(seed: int) -> Any:
    """Fixed 32-bit LCG so fixtures are reproducible without numpy."""
    state = seed & 0xFFFFFFFF

    def _next() -> float:
        nonlocal state
        state = (1664525 * state + 1013904223) & 0xFFFFFFFF
        return state / 2147483648.0 - 1.0

    return _next


def _episode(
    seed: int,
    duty_pct: float,
    *,
    comparability_state: str,
    exposure_fraction: float = 1.0,
) -> dict[str, Any]:
    if comparability_state == "METHOD_FAILURE_NOT_CENSORING":
        return {
            "evaluation_seed": seed,
            "terminal_record_state": "FAILED",
            "outcome_state": "NULL",
            "exposure_class": "NO_EXPOSURE",
            "comparability_state": "METHOD_FAILURE_NOT_CENSORING",
            "comparability_reason": "NO_EXPOSURE_TERMINAL_FAILURE_METHOD_FAILURE",
            "full_horizon_duty_bound_pct": {
                "state": "NULL",
                "lower_pct": None,
                "upper_pct": None,
                "width_pct": None,
                "reason": "NO_EXPOSURE_TERMINAL_FAILURE_METHOD_FAILURE",
            },
        }
    if comparability_state == "COMPARABLE":
        value = _round_percent(duty_pct)
        return {
            "evaluation_seed": seed,
            "terminal_record_state": "COMPLETED",
            "outcome_state": "OBSERVED",
            "exposure_class": "FULL_EXPOSURE",
            "comparability_state": "COMPARABLE",
            "comparability_reason": "FULL_EXPOSURE_OBSERVED_COMPARABLE",
            "full_horizon_duty_bound_pct": {
                "state": "OBSERVED",
                "lower_pct": value,
                "upper_pct": value,
                "width_pct": 0.0,
                "reason": None,
            },
        }
    # Censored: the observed window carries the measured over-threshold
    # substeps, and the unobserved remainder of the horizon is unknown, so the
    # bound spans everything the missing exposure could still have contributed.
    lower = _round_percent(duty_pct * exposure_fraction)
    upper = _round_percent(lower + 100.0 * (1.0 - exposure_fraction))
    if upper > 100.0:
        raise SeedVarianceError("synthetic censored bound exceeds 100 percent")
    return {
        "evaluation_seed": seed,
        "terminal_record_state": "COMPLETED",
        "outcome_state": "NULL",
        "exposure_class": "EARLY_TERMINATED",
        "comparability_state": "EXPOSURE_CENSORED",
        "comparability_reason": "EARLY_TERMINATION_EXPOSURE_CENSORED",
        "full_horizon_duty_bound_pct": {
            "state": "OBSERVED",
            "lower_pct": lower,
            "upper_pct": upper,
            "width_pct": _round_percent(upper - lower),
            "reason": None,
        },
    }


def _cell(
    arm_id: str,
    replicate_index: int,
    design: dict[str, Any],
    evaluation_output_sha256: str,
    *,
    censored: bool = False,
    method_failure_seeds: tuple[int, ...] = (),
) -> dict[str, Any]:
    draw = _lcg(9000 + replicate_index * 31 + ARM_IDS.index(arm_id))
    base = ARM_BASE_DUTY_PCT[arm_id] + REPLICATE_OFFSET_PCT[arm_id][replicate_index]
    spread = ARM_SPREAD_PCT[arm_id]
    episodes = []
    for seed in design["evaluation_seeds"]:
        duty = base + spread * draw()
        if seed in method_failure_seeds:
            episodes.append(_episode(seed, duty, comparability_state="METHOD_FAILURE_NOT_CENSORING"))
        elif censored:
            episodes.append(
                _episode(
                    seed,
                    duty,
                    comparability_state="EXPOSURE_CENSORED",
                    exposure_fraction=CENSORED_EXPOSURE_FRACTION,
                )
            )
        else:
            episodes.append(_episode(seed, duty, comparability_state="COMPARABLE"))
    return {
        "arm_id": arm_id,
        "audit_contract_source_sha256": AUDIT_CONTRACT_SOURCE_SHA256,
        "audit_protocol_sha256": AUDIT_PROTOCOL_SHA256,
        "episodes": episodes,
        "evaluation_environment_lock_verified": True,
        "evaluation_output_sha256": evaluation_output_sha256,
        "pilot_contract_source_sha256": PILOT_CONTRACT_SOURCE_SHA256,
        "realized_timesteps": design["expected_realized_timesteps"],
        "training_environment_lock_verified": True,
        "training_terminal_state": "COMPLETED",
    }


def build_raw_bundle(
    design: dict[str, Any],
    lock_sha256: str,
    git_sha: str,
    *,
    censored_arms: tuple[str, ...] = (),
    method_failures: dict[tuple[str, int], tuple[int, ...]] | None = None,
) -> dict[str, Any]:
    """Assemble a raw replicate inventory for one regression case."""
    failures = method_failures or {}
    replicates = []
    for index in range(design["replicate_count"]):
        arms = []
        for arm_id in ARM_IDS:
            evaluation_digest = (
                "sha256:" + f"{index:02d}{ARM_IDS.index(arm_id):02d}".ljust(64, "e")
            )
            arms.append(
                _cell(
                    arm_id,
                    index,
                    design,
                    evaluation_digest,
                    censored=arm_id in censored_arms,
                    method_failure_seeds=failures.get((arm_id, index), ()),
                )
            )
        replicates.append(
            {
                "arms": arms,
                "environment_seed_block": design["environment_seed_blocks"][index],
                "replicate_index": index,
                "training_seed": design["training_seeds"][index],
            }
        )
    return {
        "bundle_class": SYNTHETIC_BUNDLE_CLASS,
        "environment_lock_sha256": lock_sha256,
        "protocol_id": PROTOCOL_ID,
        "replicates": replicates,
        "schema_version": RAW_SCHEMA,
        "source_dirty_post": False,
        "source_dirty_pre": False,
        "source_git_sha_post": git_sha,
        "source_git_sha_pre": git_sha,
    }


def capture_pinned_lock() -> dict[str, Any]:
    """Capture with threads pinned, because the protocol requires it.

    The protocol demands AMBIENT_THREADING_PINNED, so the capture has to happen
    with OMP_NUM_THREADS=1 actually set rather than have the requirement waived
    for a fixture.
    """
    previous = os.environ.get("OMP_NUM_THREADS")
    os.environ["OMP_NUM_THREADS"] = "1"
    try:
        record = capture_environment_lock(MEASURED_LOCK_CLASS)
    finally:
        if previous is None:
            os.environ.pop("OMP_NUM_THREADS", None)
        else:
            os.environ["OMP_NUM_THREADS"] = previous
    validation = validate_lock_record(record)
    if validation["threading_determinism"] != THREADING_PINNED:
        raise SeedVarianceError("captured lock is not thread-pinned")
    return record


def _git_identity(repository_root: Path) -> str:
    """A synthetic bundle still has to come from a clean checkout."""
    def _git(*arguments: str) -> str:
        completed = subprocess.run(
            ["git", "-C", str(repository_root), *arguments],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            raise SeedVarianceError(f"git {' '.join(arguments)} failed: {completed.stderr.strip()}")
        return completed.stdout.strip()

    status = _git("status", "--porcelain", "--untracked-files=no")
    if status:
        raise SeedVarianceError(
            "refusing to build a regression bundle from a dirty tracked worktree:\n" + status
        )
    return _git("rev-parse", "HEAD")


CASES = (
    {
        "case_id": "all-comparable",
        "censored_arms": (),
        "method_failures": {},
        "expectation": "point-identified method-level bound and a point between_replicate_sd",
    },
    {
        "case_id": "censored-candidate",
        "censored_arms": ("V7C_FILTERED_ACTION",),
        "method_failures": {},
        "expectation": "V7C partially identified, sign unidentified, between_replicate_sd withheld",
    },
    {
        "case_id": "method-failure",
        "censored_arms": (),
        "method_failures": {("V7B_REDUCED_JOINT_ENVELOPE", 2): (18007,)},
        "expectation": "V7B method-level bound NULL with replicate 2 blocked",
    },
)


def build_package(output_root: Path, repository_root: Path) -> dict[str, Any]:
    git_sha = _git_identity(repository_root)
    protocol = load_protocol(DEFAULT_PROTOCOL)
    design = _protocol_design(protocol)
    lock_record = capture_pinned_lock()
    output = Path(output_root)
    if output.exists():
        raise SeedVarianceError(f"refusing to overwrite an existing output root: {output}")
    output.mkdir(parents=True)

    cases = []
    for case in CASES:
        # The bundle and its derived analysis are siblings: the contract
        # refuses to write into the bundle it just proved it only read.
        root = output / case["case_id"] / "bundle"
        analysis = output / case["case_id"] / "analysis"
        root.mkdir(parents=True)
        shutil.copyfile(DEFAULT_PROTOCOL, root / PROTOCOL_ARTIFACT)
        if sha256_file(root / PROTOCOL_ARTIFACT) != sha256_file(DEFAULT_PROTOCOL):
            raise SeedVarianceError("protocol copy digest mismatch")
        lock_sha256 = write_lock_record(root / LOCK_ARTIFACT, lock_record)
        raw = build_raw_bundle(
            design,
            lock_record["locked_sha256"],
            git_sha,
            censored_arms=case["censored_arms"],
            method_failures=case["method_failures"],
        )
        raw_bytes = _json_bytes(raw)
        _write_bytes(root / RAW_ARTIFACT, raw_bytes)
        receipt = analyse_seed_variance(root, analysis)
        cases.append(
            {
                "case_id": case["case_id"],
                "expectation": case["expectation"],
                "bundle_class": receipt["bundle_class"],
                "seed_variance_status": receipt["seed_variance_status"],
                "retained_blocker_count": receipt["retained_blocker_count"],
                "summary_sha256": receipt["summary_sha256"],
                "receipt_sha256": receipt["receipt_sha256"],
                "replay_exact": receipt["replay"]["replay_exact"],
                "environment_lock_sha256": lock_sha256,
            }
        )

    package = {
        "schema_version": PACKAGE_RECEIPT_SCHEMA,
        "protocol_id": PROTOCOL_ID,
        "bundle_class": SYNTHETIC_BUNDLE_CLASS,
        "source_git_sha": git_sha,
        "environment_locked_sha256": lock_record["locked_sha256"],
        "case_count": len(cases),
        "cases": cases,
        "development_evidence": False,
        "method_level_power_ready": False,
        "statistics_ready": False,
        "paper_data_ready": False,
        "claim_boundary": protocol["claim_boundary"],
    }
    _write_bytes(output / "regression_package_receipt.json", _json_bytes(package))
    return package


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_root", type=Path)
    parser.add_argument(
        "--repository-root", type=Path, default=Path(__file__).resolve().parent.parent
    )
    args = parser.parse_args()
    try:
        package = build_package(args.output_root, args.repository_root)
    except Exception as exc:
        print(
            json.dumps(
                {
                    "schema_version": "TRAINING_SEED_VARIANCE_REGRESSION_ERROR_V1",
                    "validation_status": "STRUCTURAL_FAILURE",
                    "error": f"{type(exc).__name__}: {exc}"[:1000],
                    "paper_data_ready": False,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        raise SystemExit(2) from exc
    print(json.dumps(package, ensure_ascii=False, indent=2, allow_nan=False))
    raise SystemExit(0)


if __name__ == "__main__":
    main()

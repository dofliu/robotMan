"""Build clean-source synthetic evidence for the paired-statistics V1 contract.

The generated fixtures are REGRESSION-only.  They intentionally include failed,
negative, null, non-finite, censored, and cancelled states while keeping every
scientific and physical-readiness claim false.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any

from paired_statistics_contract import (
    build_paired_statistics_bundle,
    validate_paired_statistics_bundle,
)
from test_paired_statistics_contract import (
    _binary_outcome,
    _build_fixture,
    _continuous_outcome,
    _nonobserved,
)


PACKAGE_SCHEMA = "PAIRED_STATISTICS_REGRESSION_PACKAGE_V1"
CLAIM_BOUNDARY = (
    "SIM_ONLY_MUJOCO / NOT_PHYSICALLY_VALIDATED; synthetic regression evidence "
    "for paired-statistics software behavior only; no Study A, controller "
    "superiority, sim-to-real, physical fidelity, safety, or paper-readiness claim."
)


class RegressionBundleError(RuntimeError):
    """Clean-source identity or synthetic evidence construction failed."""


def _git(repo_root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RegressionBundleError(
            f"git {' '.join(args)} failed: {completed.stderr[:500]}"
        )
    return completed.stdout.strip()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _artifact_inventory(root: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise RegressionBundleError(f"evidence contains symlink: {path}")
        if not path.is_file() or path.name == "regression_package_receipt.json":
            continue
        records.append({
            "path": path.relative_to(root).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": _sha256_file(path),
        })
    return records


def build_regression_package(repo_root: Path, output_root: Path) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    output_root = output_root.resolve()
    if output_root.exists():
        raise RegressionBundleError("output root must not already exist")
    if not output_root.is_relative_to((repo_root / "backend" / "run_traces").resolve()):
        raise RegressionBundleError("output root must be inside backend/run_traces")

    pre_sha = _git(repo_root, "rev-parse", "HEAD")
    pre_status = _git(repo_root, "status", "--porcelain=v1", "--untracked-files=all")
    if pre_status:
        raise RegressionBundleError("source worktree must be clean before evidence run")
    output_root.mkdir(parents=True)

    continuous = _continuous_outcome()
    binary = _binary_outcome()
    energy = _continuous_outcome("energy_j", role="SECONDARY", unit="J")
    residual = _continuous_outcome(
        "solver_residual_n",
        role="SECONDARY",
        unit="N",
    )
    threshold = _continuous_outcome(
        "push_threshold_n",
        role="SECONDARY",
        unit="N",
    )
    outcomes = [continuous, binary, energy, residual, threshold]
    aggregate_paths = _build_fixture(
        output_root / "aggregate-case",
        outcomes,
        statuses={(2, "candidate"): "FAILED"},
        overrides={
            (2, "candidate"): {
                "energy_j": _nonobserved(
                    energy,
                    "NULL",
                    reason="TERMINATED_BEFORE_ENERGY_WINDOW",
                )
            },
            (3, "candidate"): {
                "solver_residual_n": _nonobserved(
                    residual,
                    "NONFINITE",
                    reason="SOURCE_EVALUATOR_REPORTED_NAN",
                )
            },
            (4, "candidate"): {
                "push_threshold_n": _nonobserved(
                    threshold,
                    "CENSORED",
                    reason="UPPER_SEARCH_BOUND_REACHED",
                    side="RIGHT",
                    bound=100.0,
                )
            },
        },
        source_sha=pre_sha,
    )
    aggregate_receipt = build_paired_statistics_bundle(
        aggregate_paths["statistics_spec"],
        aggregate_paths["matrix_spec"],
        aggregate_paths["matrix_index"],
        aggregate_paths["output"],
    )
    aggregate_validation = validate_paired_statistics_bundle(
        aggregate_paths["output"] / "statistics_receipt.json"
    )

    cancelled_paths = _build_fixture(
        output_root / "cancelled-case",
        [_continuous_outcome()],
        statuses={(4, "candidate"): "CANCELLED"},
        source_sha=pre_sha,
    )
    cancelled_receipt = build_paired_statistics_bundle(
        cancelled_paths["statistics_spec"],
        cancelled_paths["matrix_spec"],
        cancelled_paths["matrix_index"],
        cancelled_paths["output"],
    )
    cancelled_validation = validate_paired_statistics_bundle(
        cancelled_paths["output"] / "statistics_receipt.json"
    )

    post_sha = _git(repo_root, "rev-parse", "HEAD")
    post_status = _git(repo_root, "status", "--porcelain=v1", "--untracked-files=all")
    if post_sha != pre_sha or post_status:
        raise RegressionBundleError("Git source identity changed during evidence run")
    if not aggregate_receipt["contract_valid"]:
        raise RegressionBundleError("aggregate regression contract did not validate")
    if aggregate_receipt["statistics_ready"]:
        raise RegressionBundleError("mixed regression must retain semantic blockers")
    if cancelled_receipt["validation_status"] != "BLOCKED_UPSTREAM_MATRIX":
        raise RegressionBundleError("cancelled regression did not retain upstream block")

    artifacts = _artifact_inventory(output_root)
    receipt = {
        "schema_version": PACKAGE_SCHEMA,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_git_sha_pre": pre_sha,
        "source_git_sha_post": post_sha,
        "source_dirty_pre": False,
        "source_dirty_post": False,
        "aggregate_case": {
            "validation_status": aggregate_receipt["validation_status"],
            "contract_valid": aggregate_receipt["contract_valid"],
            "statistics_ready": aggregate_receipt["statistics_ready"],
            "blocked_outcomes": aggregate_receipt["blocked_outcomes"],
            "run_status_counts": aggregate_receipt["run_status_counts"],
            "bundle_validation": aggregate_validation,
        },
        "cancelled_case": {
            "validation_status": cancelled_receipt["validation_status"],
            "contract_valid": cancelled_receipt["contract_valid"],
            "statistics_ready": cancelled_receipt["statistics_ready"],
            "cancelled_cells": cancelled_receipt["cancelled_cells"],
            "run_status_counts": cancelled_receipt["run_status_counts"],
            "bundle_validation": cancelled_validation,
        },
        "retained_states": [
            "FAILED",
            "CANCELLED",
            "NEGATIVE",
            "NULL",
            "NONFINITE",
            "CENSORED",
        ],
        "artifact_count": len(artifacts),
        "artifact_bytes": sum(item["bytes"] for item in artifacts),
        "artifacts": artifacts,
        "paper_data_ready": False,
        "evidence_scope": "SIM_ONLY_MUJOCO",
        "claim_boundary": CLAIM_BOUNDARY,
    }
    receipt_path = output_root / "regression_package_receipt.json"
    _write_json(receipt_path, receipt)
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build clean-source paired-statistics V1 regression evidence"
    )
    parser.add_argument("output_root", type=Path)
    args = parser.parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    try:
        receipt = build_regression_package(repo_root, args.output_root)
    except Exception as exc:
        print(json.dumps({
            "schema_version": "PAIRED_STATISTICS_REGRESSION_ERROR_V1",
            "status": "ERROR",
            "paper_data_ready": False,
            "error": f"{type(exc).__name__}: {exc}"[:1000],
        }, ensure_ascii=False, indent=2))
        raise SystemExit(2) from exc
    print(json.dumps(receipt, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

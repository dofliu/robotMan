"""Build clean-source synthetic evidence for the v7 exposure-censoring audit V1.

The generated fixtures are REGRESSION-only.  They exercise the audit software on
schema-exact synthetic pilot bundles that deliberately retain full exposure,
early-terminated exposure censoring, an arithmetically clean but censored
episode, and whole-arm method failure.  They support no statement about the
frozen v7 action-interface pilot: every bundle declares
``SYNTHETIC_REGRESSION_BUNDLE`` and every readiness claim stays false.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any

from v7_exposure_audit_contract import (
    AUDIT_STATUS_BLOCKED,
    SYNTHETIC_BUNDLE_CLASS,
    audit_v7_exposure_censoring,
    validate_v7_exposure_audit_bundle,
)
from test_v7_exposure_audit_contract import (
    AUDIT_PROTOCOL_PATH,
    _build_synthetic_pilot_bundle,
    _default_plan,
    _method_failure_plan,
)


PACKAGE_SCHEMA = "V7_EXPOSURE_AUDIT_REGRESSION_PACKAGE_V1"
CLAIM_BOUNDARY = (
    "SIM_ONLY_MUJOCO / NOT_PHYSICALLY_VALIDATED; synthetic regression evidence "
    "for exposure-censoring audit software behavior only; no statement about the "
    "frozen v7 pilot, no Study A, controller superiority, sim-to-real, physical "
    "fidelity, safety, or paper-readiness claim."
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
        json.dumps(payload, ensure_ascii=False, allow_nan=False, indent=2, sort_keys=True)
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


def _case(
    case_root: Path,
    plan: dict[str, dict[str, Any]],
    source_sha: str,
) -> dict[str, Any]:
    """Build one synthetic pilot bundle, audit it read-only, and re-validate."""
    source = _build_synthetic_pilot_bundle(
        case_root / "source-bundle",
        plan=plan,
        source_sha=source_sha,
        bundle_class=SYNTHETIC_BUNDLE_CLASS,
    )
    before = {
        path.relative_to(source).as_posix(): (path.stat().st_size, _sha256_file(path))
        for path in sorted(source.rglob("*"))
        if path.is_file()
    }
    receipt = audit_v7_exposure_censoring(
        AUDIT_PROTOCOL_PATH, source, case_root / "audit-bundle"
    )
    after = {
        path.relative_to(source).as_posix(): (path.stat().st_size, _sha256_file(path))
        for path in sorted(source.rglob("*"))
        if path.is_file()
    }
    if after != before:
        raise RegressionBundleError("audit mutated the audited bundle")
    if receipt["audit_status"] != AUDIT_STATUS_BLOCKED:
        raise RegressionBundleError("synthetic case must retain a censoring blocker")
    if receipt["audit_applies_to_frozen_v7_pilot"] is not False:
        raise RegressionBundleError("synthetic case must not claim the frozen v7 pilot")
    validation = validate_v7_exposure_audit_bundle(
        case_root / "audit-bundle" / "audit_receipt.json"
    )
    summary = json.loads(
        (case_root / "audit-bundle" / "audit_summary.json").read_text("utf-8")
    )
    return {
        "audit_status": receipt["audit_status"],
        "contract_valid": receipt["contract_valid"],
        "audit_applies_to_frozen_v7_pilot": receipt["audit_applies_to_frozen_v7_pilot"],
        "source_bundle_class": receipt["source_bundle_class"],
        "censoring_blocker_count": receipt["censoring_blocker_count"],
        "source_bundle_read_only_verified": receipt["source_bundle_read_only_verified"],
        "exposure_class_counts": {
            arm["arm_id"]: arm["exposure_class_counts"] for arm in summary["arm_exposure"]
        },
        "comparability_state_counts": {
            arm["arm_id"]: arm["comparability_state_counts"]
            for arm in summary["arm_exposure"]
        },
        "paired_validity_verdicts": {
            item["candidate_arm_id"]: item["validity_verdict"]
            for item in summary["paired_comparability"]
        },
        "sign_identified_pair_counts": {
            item["candidate_arm_id"]: item["paired_identification_bound_pct"][
                "sign_identified_pair_count"
            ]
            for item in summary["paired_comparability"]
        },
        "audited_paired_difference_states": {
            item["candidate_arm_id"]: item["audited_paired_difference_pct"]["state"]
            for item in summary["paired_comparability"]
        },
        "phase_convention_finding": summary["phase_convention"]["finding"],
        "audit_findings": summary["audit_findings"],
        "bundle_validation": validation,
    }


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

    censored = _case(output_root / "exposure-censored-case", _default_plan(), pre_sha)
    method_failure = _case(
        output_root / "method-failure-case", _method_failure_plan(), pre_sha
    )

    post_sha = _git(repo_root, "rev-parse", "HEAD")
    post_status = _git(repo_root, "status", "--porcelain=v1", "--untracked-files=all")
    if post_sha != pre_sha or post_status:
        raise RegressionBundleError("Git source identity changed during evidence run")
    if censored["comparability_state_counts"]["V7C_FILTERED_ACTION"]["EXPOSURE_CENSORED"] != 30:
        raise RegressionBundleError("censored case lost its exposure-censored retention")
    if (
        method_failure["comparability_state_counts"]["V7C_FILTERED_ACTION"][
            "METHOD_FAILURE_NOT_CENSORING"
        ]
        != 30
    ):
        raise RegressionBundleError("method-failure case lost its method-failure retention")

    artifacts = _artifact_inventory(output_root)
    receipt = {
        "schema_version": PACKAGE_SCHEMA,
        "audit_protocol_id": "AUDIT-V7-EXPOSURE-CENSORING-V1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_git_sha_pre": pre_sha,
        "source_git_sha_post": post_sha,
        "source_dirty_pre": False,
        "source_dirty_post": False,
        "exposure_censored_case": censored,
        "method_failure_case": method_failure,
        "retained_states": [
            "COMPLETED",
            "FAILED",
            "NULL",
            "EXPOSURE_CENSORED",
            "METHOD_FAILURE_NOT_CENSORING",
        ],
        "audit_applies_to_frozen_v7_pilot": False,
        "artifact_count": len(artifacts),
        "artifact_bytes": sum(item["bytes"] for item in artifacts),
        "artifacts": artifacts,
        "pilot_planning_ready": False,
        "method_level_power_ready": False,
        "statistics_ready": False,
        "paper_data_ready": False,
        "evidence_scope": "SIM_ONLY_MUJOCO",
        "claim_boundary": CLAIM_BOUNDARY,
    }
    receipt_path = output_root / "regression_package_receipt.json"
    _write_json(receipt_path, receipt)
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build clean-source v7 exposure-censoring audit V1 regression evidence"
    )
    parser.add_argument("output_root", type=Path)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    receipt = build_regression_package(args.repo_root, args.output_root)
    print(json.dumps(receipt, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()

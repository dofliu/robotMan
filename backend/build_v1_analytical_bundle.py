"""Build one fail-closed V1 analytical regression bundle.

The bundle binds the frozen passive-fixture primary result to its exact embedded
MJCF package and to an independent standard-library replay process.  A valid
bundle is regression evidence only; it is never formal or physical evidence.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import math
from numbers import Real
from pathlib import Path
import platform
import subprocess
import sys
import traceback
from typing import Any
import uuid

from paper_data_contract import artifact_record, sha256_file, validate_paper_run_bundle
from v1_analytical_suite import (
    ANALYTICAL_SUITE_CONTRACT,
    CASE_SPECS,
    CLAIM_BOUNDARY,
    MODEL_PACKAGE_SCHEMA_VERSION,
    PRIMARY_SCHEMA_VERSION,
    build_analytical_model_package,
    run_analytical_suite,
    validate_analytical_model_package,
    validate_primary_result,
)


BACKEND_DIR = Path(__file__).resolve().parent
REPO_ROOT = BACKEND_DIR.parent
REPLAY_SCRIPT = BACKEND_DIR / "v1_analytical_replay.py"

REPLAY_SCHEMA_VERSION = "V1_ANALYTICAL_REPLAY_RECEIPT_V1"
REPLAY_CLAIM_BOUNDARY = (
    "SIM_ONLY_MUJOCO / NOT_PHYSICALLY_VALIDATED. This stdlib-only process replay "
    "recomputes J^T contact-wrench closure, static single-support load balance, "
    "the centered 5 kg simulated mass/GRF increment, and selected 4/2/1 ms QoIs "
    "from serialized evidence. The model, Jacobians, and wrenches remain MuJoCo "
    "receipts; this is not an independent contact model, articulated-humanoid or "
    "controller validation, physical payload validation, safety evidence, or "
    "sim-to-real evidence."
)
REPLAY_RECEIPT_KEYS = frozenset({
    "schema_version",
    "source_schema_version",
    "source_artifact_sha256",
    "model_package_schema_version",
    "model_package_artifact_sha256",
    "model_package_content_sha256",
    "evidence_scope",
    "claim_boundary",
    "replayed_at",
    "status",
    "case_receipts",
    "metrics",
    "criteria",
})
REPLAY_IDENTITY_METRIC_KEYS = frozenset({
    "raw_serialized_receipt_delta_max",
    "primary_summary_numeric_delta_max",
    "primary_case_receipts_exact",
    "primary_metrics_exact",
    "primary_criteria_exact",
    "primary_status_matches_replay",
})
REPLAY_IDENTITY_CRITERION_IDS = (
    "RAW_SERIALIZED_RECEIPT_IDENTITY",
    "PRIMARY_CASE_RECEIPT_IDENTITY",
    "PRIMARY_SUITE_METRIC_IDENTITY",
    "PRIMARY_SUITE_CRITERIA_IDENTITY",
    "PRIMARY_STATUS_IDENTITY",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _reject_nonstandard_json(value: str) -> None:
    raise ValueError(f"non-standard JSON constant is forbidden: {value}")


def _read_json(path: Path) -> Any:
    return json.loads(
        path.read_text(encoding="utf-8"),
        parse_constant=_reject_nonstandard_json,
    )


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
        newline="\n",
    )


def _write_text(path: Path, value: object) -> None:
    if value is None:
        text = ""
    elif isinstance(value, bytes):
        text = value.decode("utf-8", errors="replace")
    else:
        text = str(value)
    path.write_text(text, encoding="utf-8", newline="\n")


def _captured_process_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _sha256_bytes(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def _git_bytes(*args: str) -> bytes:
    completed = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        check=True,
    )
    return completed.stdout


def _source_identity() -> dict:
    """Capture HEAD plus content-sensitive tracked/untracked worktree identity."""
    git_sha = _git_bytes("rev-parse", "HEAD").decode("ascii").strip()
    porcelain = _git_bytes("status", "--porcelain=v1", "--untracked-files=all")
    tracked_diff = _git_bytes("diff", "--binary", "HEAD", "--")
    untracked_output = _git_bytes("ls-files", "--others", "--exclude-standard", "-z")
    untracked_digest = hashlib.sha256()
    for raw_name in sorted(item for item in untracked_output.split(b"\0") if item):
        relative_name = raw_name.decode("utf-8", errors="surrogateescape")
        candidate = (REPO_ROOT / relative_name).resolve()
        untracked_digest.update(raw_name)
        untracked_digest.update(b"\0")
        if candidate.is_file() and candidate.is_relative_to(REPO_ROOT.resolve()):
            untracked_digest.update(candidate.read_bytes())
        untracked_digest.update(b"\0")
    return {
        "git_sha": git_sha,
        "dirty": bool(porcelain),
        "porcelain_sha256": _sha256_bytes(porcelain),
        "tracked_diff_sha256": _sha256_bytes(tracked_diff),
        "untracked_content_sha256": f"sha256:{untracked_digest.hexdigest()}",
    }


def _environment_receipt(source_before: dict, source_after: dict) -> dict:
    packages: dict[str, str | None] = {}
    for distribution in ("mujoco", "numpy", "pydantic", "pytest"):
        try:
            packages[distribution] = importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            packages[distribution] = None
    return {
        "python": sys.version,
        "implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "packages": packages,
        "source_identity": {
            "before": source_before,
            "after": source_after,
            "stable_during_run": source_before == source_after,
        },
    }


def _non_finite_diagnostics(value: object) -> list[str]:
    """Return paths for non-finite numerics without emitting invalid JSON."""
    found: list[str] = []

    def visit(item: object, path: str) -> None:
        if len(found) >= 40:
            return
        if isinstance(item, Real) and not isinstance(item, bool):
            numeric = float(item)
            if not math.isfinite(numeric):
                if math.isnan(numeric):
                    label = "NaN"
                elif numeric > 0.0:
                    label = "+Infinity"
                else:
                    label = "-Infinity"
                found.append(f"{path}={label}")
            return
        if isinstance(item, dict):
            for key, child in item.items():
                visit(child, f"{path}.{key}")
        elif isinstance(item, (list, tuple)):
            for index, child in enumerate(item):
                visit(child, f"{path}[{index}]")

    visit(value, "$")
    return found


def _exception_detail(exc: BaseException) -> str:
    detail = str(exc) or repr(exc)
    return f"{type(exc).__name__}: {detail}"


def _primary_error_receipt(
    *,
    status: str,
    error_type: str,
    error_class: str,
    detail: str,
    rejected_result: object | None = None,
) -> dict:
    receipt = {
        "schema_version": "V1_ANALYTICAL_PRIMARY_ERROR_RECEIPT_V1",
        "evidence_scope": "SIM_ONLY_MUJOCO_SOFTWARE_ERROR",
        "claim_boundary": CLAIM_BOUNDARY,
        "executed_at": _utc_now(),
        "status": status,
        "error_type": error_type,
        "error_class": error_class,
        "detail": detail,
        "contract": deepcopy(ANALYTICAL_SUITE_CONTRACT),
        "metrics": {},
        "criteria": [],
    }
    if rejected_result is not None:
        receipt["rejected_result"] = rejected_result
    return receipt


def _strict_json_serializable(value: object) -> bool:
    try:
        json.dumps(value, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError):
        return False
    return True


def _model_error_receipt(*, status: str, error_type: str, detail: str) -> dict:
    return {
        "schema_version": "V1_ANALYTICAL_MODEL_PACKAGE_ERROR_RECEIPT_V1",
        "evidence_scope": "SIM_ONLY_MUJOCO_SOFTWARE_ERROR",
        "claim_boundary": CLAIM_BOUNDARY,
        "created_at": _utc_now(),
        "status": status,
        "error_type": error_type,
        "detail": detail,
        "contract_id": ANALYTICAL_SUITE_CONTRACT["contract_id"],
        "models": [],
    }


def _replay_error_receipt(
    *,
    status: str,
    error_type: str,
    detail: str,
    raw_path: Path,
    model_path: Path,
    primary: dict,
    model_package: dict,
    return_code: int | None,
) -> dict:
    return {
        "schema_version": "V1_ANALYTICAL_REPLAY_ERROR_RECEIPT_V1",
        "source_schema_version": primary.get("schema_version"),
        "source_artifact_sha256": sha256_file(raw_path),
        "model_package_schema_version": model_package.get("schema_version"),
        "model_package_artifact_sha256": sha256_file(model_path),
        "model_package_content_sha256": model_package.get("content_sha256"),
        "evidence_scope": "PROCESS_INDEPENDENT_ANALYTICAL_REPLAY_ERROR",
        "claim_boundary": CLAIM_BOUNDARY,
        "replayed_at": _utc_now(),
        "status": status,
        "return_code": return_code,
        "error_type": error_type,
        "detail": detail,
        "case_receipts": [],
        "metrics": {},
        "criteria": [],
    }


def _valid_aware_iso_timestamp(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() is not None


def _tree_match(left: object, right: object) -> tuple[bool, float]:
    """Mirror replay structural matching while retaining maximum numeric delta."""
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is bool and type(right) is bool and left == right, 0.0
    if (
        isinstance(left, Real)
        and not isinstance(left, bool)
        and isinstance(right, Real)
        and not isinstance(right, bool)
    ):
        left_number = float(left)
        right_number = float(right)
        if not math.isfinite(left_number) or not math.isfinite(right_number):
            return False, math.inf
        return True, abs(left_number - right_number)
    if left is None or right is None:
        return left is None and right is None, 0.0
    if isinstance(left, str) or isinstance(right, str):
        return isinstance(left, str) and isinstance(right, str) and left == right, 0.0
    if isinstance(left, list) and isinstance(right, list):
        if len(left) != len(right):
            return False, 0.0
        exact = True
        delta = 0.0
        for left_item, right_item in zip(left, right, strict=True):
            item_exact, item_delta = _tree_match(left_item, right_item)
            exact = exact and item_exact
            delta = max(delta, item_delta)
        return exact, delta
    if isinstance(left, dict) and isinstance(right, dict):
        if set(left) != set(right):
            return False, 0.0
        exact = True
        delta = 0.0
        for key in left:
            item_exact, item_delta = _tree_match(left[key], right[key])
            exact = exact and item_exact
            delta = max(delta, item_delta)
        return exact, delta
    return left == right, 0.0


def _valid_replay_identity_criterion(
    criterion: object,
    *,
    criterion_id: str,
    value: float | bool,
    operator: str,
    limit: float | bool,
    unit: str,
) -> bool:
    if not isinstance(criterion, dict) or set(criterion) != {
        "id", "passed", "value", "operator", "limit", "unit"
    }:
        return False
    if criterion.get("id") != criterion_id:
        return False
    if criterion.get("operator") != operator or criterion.get("unit") != unit:
        return False
    observed_value = criterion.get("value")
    observed_limit = criterion.get("limit")
    if isinstance(value, bool):
        if type(observed_value) is not bool or observed_value is not value:
            return False
    elif (
        isinstance(observed_value, bool)
        or not isinstance(observed_value, (int, float))
        or not math.isfinite(float(observed_value))
        or float(observed_value) != float(value)
    ):
        return False
    if isinstance(limit, bool):
        if type(observed_limit) is not bool or observed_limit is not limit:
            return False
    elif (
        isinstance(observed_limit, bool)
        or not isinstance(observed_limit, (int, float))
        or not math.isfinite(float(observed_limit))
        or float(observed_limit) != float(limit)
    ):
        return False
    if operator == "<=":
        expected_pass = float(value) <= float(limit)
    elif operator == "==":
        expected_pass = value == limit
    else:
        return False
    return type(criterion.get("passed")) is bool and criterion["passed"] is expected_pass


def _valid_replay_receipt(
    receipt: object,
    primary: dict,
    model_package: dict,
    raw_sha256: str,
    model_sha256: str,
) -> bool:
    """Reject replay stdout unless every source/model/summary binding is exact."""
    if not isinstance(receipt, dict) or set(receipt) != REPLAY_RECEIPT_KEYS:
        return False
    if _non_finite_diagnostics(receipt):
        return False
    if receipt.get("schema_version") != REPLAY_SCHEMA_VERSION:
        return False
    if receipt.get("source_schema_version") != PRIMARY_SCHEMA_VERSION:
        return False
    if receipt.get("source_artifact_sha256") != raw_sha256:
        return False
    if receipt.get("model_package_schema_version") != MODEL_PACKAGE_SCHEMA_VERSION:
        return False
    if receipt.get("model_package_artifact_sha256") != model_sha256:
        return False
    if receipt.get("model_package_content_sha256") != model_package.get("content_sha256"):
        return False
    if receipt.get("evidence_scope") != "PROCESS_INDEPENDENT_ANALYTICAL_REPLAY_ONLY":
        return False
    if receipt.get("claim_boundary") != REPLAY_CLAIM_BOUNDARY:
        return False
    if not _valid_aware_iso_timestamp(receipt.get("replayed_at")):
        return False
    if receipt.get("status") not in {"PASS", "FAIL"}:
        return False

    replay_case_receipts = receipt.get("case_receipts")
    primary_case_receipts = primary.get("case_receipts")
    case_exact, case_delta = _tree_match(primary_case_receipts, replay_case_receipts)
    if not isinstance(replay_case_receipts, list):
        return False

    primary_metrics = primary.get("metrics")
    replay_metrics = receipt.get("metrics")
    if not isinstance(primary_metrics, dict) or not isinstance(replay_metrics, dict):
        return False
    if set(replay_metrics) != set(primary_metrics) | REPLAY_IDENTITY_METRIC_KEYS:
        return False
    replay_scientific_metrics = {
        key: replay_metrics[key] for key in primary_metrics
    }
    metric_exact, metric_delta = _tree_match(
        primary_metrics, replay_scientific_metrics
    )

    primary_criteria = primary.get("criteria")
    replay_criteria = receipt.get("criteria")
    if not isinstance(primary_criteria, list) or not isinstance(replay_criteria, list):
        return False
    if len(replay_criteria) != len(primary_criteria) + len(REPLAY_IDENTITY_CRITERION_IDS):
        return False
    replay_scientific_criteria = replay_criteria[:len(primary_criteria)]
    criteria_exact, criteria_delta = _tree_match(
        primary_criteria, replay_scientific_criteria
    )
    if not (case_exact and metric_exact and criteria_exact):
        return False

    raw_delta = replay_metrics.get("raw_serialized_receipt_delta_max")
    summary_delta = replay_metrics.get("primary_summary_numeric_delta_max")
    if (
        isinstance(raw_delta, bool)
        or not isinstance(raw_delta, (int, float))
        or not math.isfinite(float(raw_delta))
        or float(raw_delta) < 0.0
        or isinstance(summary_delta, bool)
        or not isinstance(summary_delta, (int, float))
        or not math.isfinite(float(summary_delta))
        or float(summary_delta) < 0.0
    ):
        return False
    expected_summary_delta = max(case_delta, metric_delta, criteria_delta)
    if float(summary_delta) != expected_summary_delta:
        return False

    expected_primary_status = (
        "PASS"
        if all(
            isinstance(item, dict) and item.get("passed") is True
            for item in replay_scientific_criteria
        )
        else "FAIL"
    )
    status_matches = primary.get("status") == expected_primary_status
    expected_flags = {
        "primary_case_receipts_exact": case_exact,
        "primary_metrics_exact": metric_exact,
        "primary_criteria_exact": criteria_exact,
        "primary_status_matches_replay": status_matches,
    }
    if any(type(replay_metrics.get(key)) is not bool for key in expected_flags):
        return False
    if any(replay_metrics[key] is not value for key, value in expected_flags.items()):
        return False

    identity_values: tuple[tuple[str, float | bool, str, float | bool, str], ...] = (
        (
            "RAW_SERIALIZED_RECEIPT_IDENTITY",
            float(raw_delta),
            "<=",
            1.0e-12,
            "max absolute delta",
        ),
        (
            "PRIMARY_CASE_RECEIPT_IDENTITY",
            case_exact and case_delta <= 1.0e-12,
            "==",
            True,
            "bool",
        ),
        (
            "PRIMARY_SUITE_METRIC_IDENTITY",
            metric_exact and metric_delta <= 1.0e-12,
            "==",
            True,
            "bool",
        ),
        (
            "PRIMARY_SUITE_CRITERIA_IDENTITY",
            criteria_exact and criteria_delta <= 1.0e-12,
            "==",
            True,
            "bool",
        ),
        (
            "PRIMARY_STATUS_IDENTITY",
            status_matches,
            "==",
            True,
            "bool",
        ),
    )
    replay_identity_criteria = replay_criteria[len(primary_criteria):]
    if [item["id"] if isinstance(item, dict) and "id" in item else None
            for item in replay_identity_criteria] != list(REPLAY_IDENTITY_CRITERION_IDS):
        return False
    for criterion, (criterion_id, value, operator, limit, unit) in zip(
        replay_identity_criteria, identity_values, strict=True
    ):
        if not _valid_replay_identity_criterion(
            criterion,
            criterion_id=criterion_id,
            value=value,
            operator=operator,
            limit=limit,
            unit=unit,
        ):
            return False
    expected_replay_status = (
        "PASS"
        if all(
            isinstance(item, dict) and item.get("passed") is True
            for item in replay_criteria
        )
        else "FAIL"
    )
    return receipt.get("status") == expected_replay_status


def _failure_record(failure_type: str, detail: str) -> dict:
    return {
        "failure_type": failure_type[:120],
        "timestamp_s": None,
        "detail": detail[:1000] or failure_type,
    }


def _criterion_failures(prefix: str, receipts: object) -> list[dict]:
    failures: list[dict] = []
    if not isinstance(receipts, list):
        return failures
    for item in receipts:
        if not isinstance(item, dict):
            continue
        case_id = item.get("case_id")
        criteria = item.get("criteria") if case_id is not None else receipts
        if case_id is None:
            criteria = [item]
        if not isinstance(criteria, list):
            continue
        for criterion in criteria:
            if not isinstance(criterion, dict) or criterion.get("passed") is not False:
                continue
            criterion_id = str(criterion.get("id", "UNKNOWN"))
            case_label = f" case={case_id}" if case_id is not None else ""
            detail = (
                f"{criterion_id}{case_label} value={criterion.get('value')!r} "
                f"operator={criterion.get('operator')!r} limit={criterion.get('limit')!r}"
            )
            failures.append(_failure_record(prefix, detail))
        if case_id is None:
            break
    return failures


def _artifact_records_with_readback(
    output_dir: Path,
    role_files: list[tuple[str, Path, str]],
) -> list[dict]:
    records: list[dict] = []
    for role, path, media_type in role_files:
        record = artifact_record(output_dir, path, role=role, media_type=media_type)
        resolved = (output_dir / record["path"]).resolve()
        if not resolved.is_relative_to(output_dir.resolve()):
            raise RuntimeError(f"artifact path escapes output directory: {record['path']}")
        if resolved.stat().st_size != record["bytes"]:
            raise RuntimeError(f"artifact byte readback mismatch: {record['path']}")
        if sha256_file(resolved) != record["sha256"]:
            raise RuntimeError(f"artifact SHA-256 readback mismatch: {record['path']}")
        records.append(record)
    return records


def build_v1_analytical_bundle(output_dir: Path) -> dict:
    """Build and validate one 10-role ``PAPER_RUN_MANIFEST_V1`` bundle."""
    source_before = _source_identity()
    output_dir = Path(output_dir).resolve()
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(exist_ok=False)
    started_at = _utc_now()
    run_id = (
        f"v1-analytical-{datetime.now(timezone.utc):%Y%m%dt%H%M%S}-"
        f"{uuid.uuid4().hex[:8]}"
    )

    protocol_path = output_dir / "protocol.json"
    config_path = output_dir / "resolved_config.json"
    model_path = output_dir / "models.json"
    controller_path = output_dir / "controller.json"
    environment_path = output_dir / "environment.json"
    raw_path = output_dir / "raw_suite.json"
    metrics_path = output_dir / "metrics.json"
    replay_path = output_dir / "evaluator_receipt.json"
    stdout_path = output_dir / "stdout.txt"
    stderr_path = output_dir / "stderr.txt"

    failures: list[dict] = []
    cancelled = False
    diagnostic_stderr = ""
    package_valid = False
    try:
        model_package = build_analytical_model_package()
        validate_analytical_model_package(model_package)
        if _non_finite_diagnostics(model_package):
            raise ValueError("model package contains non-finite values")
        _write_json(model_path, model_package)
        model_readback = _read_json(model_path)
        validate_analytical_model_package(model_readback)
        if model_readback != model_package:
            raise ValueError("model package JSON readback identity mismatch")
        package_valid = True
    except (KeyboardInterrupt, SystemExit) as exc:
        cancelled = True
        detail = _exception_detail(exc)
        failures.append(_failure_record("MODEL_PACKAGE_CANCELLED", detail))
        diagnostic_stderr += traceback.format_exc()
        model_package = _model_error_receipt(
            status="CANCELLED", error_type="MODEL_PACKAGE_CANCELLED", detail=detail
        )
        _write_json(model_path, model_package)
    except Exception as exc:  # noqa: BLE001 - the failed artifact must survive
        detail = _exception_detail(exc)
        failures.append(_failure_record("MODEL_PACKAGE_INVALID", detail))
        diagnostic_stderr += traceback.format_exc()
        model_package = _model_error_receipt(
            status="ERROR", error_type="MODEL_PACKAGE_INVALID", detail=detail
        )
        _write_json(model_path, model_package)

    primary_valid = False
    if not package_valid:
        primary = _primary_error_receipt(
            status="CANCELLED" if cancelled else "ERROR",
            error_type="PRIMARY_NOT_RUN_MODEL_INVALID",
            error_class="InvalidModelPackage",
            detail="Primary suite was not run because models.json failed validation.",
        )
    else:
        try:
            candidate_primary = run_analytical_suite(model_package=model_package)
        except (KeyboardInterrupt, SystemExit) as exc:
            cancelled = True
            detail = _exception_detail(exc)
            failures.append(_failure_record("PRIMARY_SUITE_CANCELLED", detail))
            diagnostic_stderr += traceback.format_exc()
            primary = _primary_error_receipt(
                status="CANCELLED",
                error_type="PRIMARY_SUITE_CANCELLED",
                error_class=type(exc).__name__,
                detail=detail,
            )
        except Exception as exc:  # noqa: BLE001 - preserve primary execution failure
            detail = _exception_detail(exc)
            failures.append(_failure_record("PRIMARY_SUITE_EXCEPTION", detail))
            diagnostic_stderr += traceback.format_exc()
            primary = _primary_error_receipt(
                status="ERROR",
                error_type="PRIMARY_SUITE_EXCEPTION",
                error_class=type(exc).__name__,
                detail=detail,
            )
        else:
            non_finite = _non_finite_diagnostics(candidate_primary)
            if non_finite:
                detail = "Non-finite primary values retained at " + ", ".join(non_finite)
                failures.append(_failure_record("PRIMARY_RESULT_NONFINITE", detail))
                diagnostic_stderr += detail + "\n"
                primary = _primary_error_receipt(
                    status="ERROR",
                    error_type="PRIMARY_RESULT_NONFINITE",
                    error_class="NonFinitePrimaryResult",
                    detail=detail,
                )
            else:
                try:
                    validate_primary_result(candidate_primary, model_package)
                    # Serialization is part of the frozen primary acceptance boundary.
                    json.dumps(candidate_primary, ensure_ascii=False, allow_nan=False)
                except Exception as exc:  # noqa: BLE001 - preserve rejected finite result
                    detail = _exception_detail(exc)
                    failures.append(_failure_record("PRIMARY_RESULT_INVALID", detail))
                    diagnostic_stderr += traceback.format_exc()
                    primary = _primary_error_receipt(
                        status="ERROR",
                        error_type="PRIMARY_RESULT_INVALID",
                        error_class=type(exc).__name__,
                        detail=detail,
                        rejected_result=(
                            candidate_primary
                            if _strict_json_serializable(candidate_primary)
                            else None
                        ),
                    )
                else:
                    primary = candidate_primary
                    primary_valid = True

    _write_json(raw_path, primary)
    raw_readback = _read_json(raw_path)
    if raw_readback != primary:
        failures.append(_failure_record(
            "PRIMARY_ARTIFACT_READBACK_MISMATCH",
            "raw_suite.json content changed during immediate JSON readback.",
        ))
        primary_valid = False
    if primary_valid:
        try:
            validate_primary_result(raw_readback, model_package)
        except Exception as exc:  # noqa: BLE001 - post-write identity is evidence-critical
            detail = _exception_detail(exc)
            failures.append(_failure_record("PRIMARY_ARTIFACT_INVALID", detail))
            diagnostic_stderr += traceback.format_exc()
            primary_valid = False

    raw_sha256 = sha256_file(raw_path)
    model_sha256 = sha256_file(model_path)
    replay_receipt: dict
    replay_stdout = ""
    replay_stderr = ""
    if not primary_valid:
        replay_receipt = _replay_error_receipt(
            status="CANCELLED" if cancelled else "ERROR",
            error_type="PRIMARY_NOT_REPLAYED",
            detail="Independent replay was skipped because the primary artifact is invalid.",
            raw_path=raw_path,
            model_path=model_path,
            primary=primary,
            model_package=model_package,
            return_code=None,
        )
    else:
        try:
            replay_process = subprocess.run(
                [
                    sys.executable,
                    "-X",
                    "utf8",
                    str(REPLAY_SCRIPT),
                    str(raw_path),
                    str(model_path),
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
                timeout=120,
            )
        except (KeyboardInterrupt, SystemExit) as exc:
            cancelled = True
            replay_stdout = _captured_process_text(getattr(exc, "stdout", None))
            replay_stderr = (
                _captured_process_text(getattr(exc, "stderr", None))
                + traceback.format_exc()
            )
            detail = _exception_detail(exc)
            failures.append(_failure_record("REPLAY_CANCELLED", detail))
            replay_receipt = _replay_error_receipt(
                status="CANCELLED",
                error_type="REPLAY_CANCELLED",
                detail=detail,
                raw_path=raw_path,
                model_path=model_path,
                primary=primary,
                model_package=model_package,
                return_code=None,
            )
        except Exception as exc:  # noqa: BLE001 - preserve process/spawn/timeout failure
            replay_stdout = _captured_process_text(getattr(exc, "stdout", None))
            replay_stderr = (
                _captured_process_text(getattr(exc, "stderr", None))
                + traceback.format_exc()
            )
            detail = _exception_detail(exc)
            failures.append(_failure_record("REPLAY_PROCESS_ERROR", detail))
            replay_receipt = _replay_error_receipt(
                status="ERROR",
                error_type="REPLAY_PROCESS_ERROR",
                detail=detail,
                raw_path=raw_path,
                model_path=model_path,
                primary=primary,
                model_package=model_package,
                return_code=None,
            )
        else:
            replay_stdout = replay_process.stdout
            replay_stderr = replay_process.stderr
            if replay_process.returncode != 0:
                detail = f"Independent replay exited with code {replay_process.returncode}."
                failures.append(_failure_record("REPLAY_PROCESS_EXIT_NONZERO", detail))
                replay_receipt = _replay_error_receipt(
                    status="ERROR",
                    error_type="REPLAY_PROCESS_EXIT_NONZERO",
                    detail=detail,
                    raw_path=raw_path,
                    model_path=model_path,
                    primary=primary,
                    model_package=model_package,
                    return_code=replay_process.returncode,
                )
            else:
                try:
                    parsed_replay = json.loads(
                        replay_process.stdout,
                        parse_constant=_reject_nonstandard_json,
                    )
                except (TypeError, json.JSONDecodeError, ValueError) as exc:
                    detail = _exception_detail(exc)
                    failures.append(_failure_record("REPLAY_STDOUT_INVALID_JSON", detail))
                    replay_receipt = _replay_error_receipt(
                        status="ERROR",
                        error_type="REPLAY_STDOUT_INVALID_JSON",
                        detail=detail,
                        raw_path=raw_path,
                        model_path=model_path,
                        primary=primary,
                        model_package=model_package,
                        return_code=replay_process.returncode,
                    )
                else:
                    if _valid_replay_receipt(
                        parsed_replay,
                        primary,
                        model_package,
                        raw_sha256,
                        model_sha256,
                    ):
                        replay_receipt = parsed_replay
                    else:
                        detail = (
                            "Replay receipt failed exact schema, source/model hash, "
                            "finite-value, timestamp, or raw-to-summary identity checks."
                        )
                        failures.append(_failure_record("REPLAY_RECEIPT_INVALID", detail))
                        replay_receipt = _replay_error_receipt(
                            status="ERROR",
                            error_type="REPLAY_RECEIPT_INVALID",
                            detail=detail,
                            raw_path=raw_path,
                            model_path=model_path,
                            primary=primary,
                            model_package=model_package,
                            return_code=replay_process.returncode,
                        )

    _write_text(stdout_path, replay_stdout)
    _write_text(stderr_path, diagnostic_stderr + replay_stderr)
    _write_json(replay_path, replay_receipt)
    if _read_json(replay_path) != replay_receipt:
        failures.append(_failure_record(
            "REPLAY_ARTIFACT_READBACK_MISMATCH",
            "evaluator_receipt.json content changed during immediate JSON readback.",
        ))

    _write_json(protocol_path, {
        "protocol_id": "V1-ANALYTICAL-FIXTURE-SUITE",
        "protocol_version": "1.0.0",
        "protocol_status": "FROZEN",
        "research_question_id": "RQ-V1-ANALYTICAL-FIXTURE",
        "hypothesis_id": "H-V1-SUPPORT-PAYLOAD-TIMESTEP",
        "specification": "docs/V1_ANALYTICAL_SUITE_SPEC.md",
        "contract": deepcopy(ANALYTICAL_SUITE_CONTRACT),
        "claim_boundary": CLAIM_BOUNDARY,
    })
    _write_json(config_path, {
        "contract_id": ANALYTICAL_SUITE_CONTRACT["contract_id"],
        "case_matrix": deepcopy(list(CASE_SPECS)),
        "assist_enabled": False,
        "controller_cadence": None,
        "deterministic": True,
        "model_package_content_sha256": model_package.get("content_sha256"),
    })
    _write_json(controller_path, {
        "controller_id": "PASSIVE_ANALYTICAL_FIXTURE_NO_ACTUATION_V1",
        "controller_family": "ORACLE",
        "controller_present": False,
        "actuation_present": False,
        "assist_enabled": False,
    })
    _write_json(metrics_path, {
        "primary": {
            "schema_version": primary.get("schema_version"),
            "status": primary.get("status"),
            "case_receipts": primary.get("case_receipts", []),
            "metrics": primary.get("metrics", {}),
            "criteria": primary.get("criteria", []),
        },
        "replay": {
            "schema_version": replay_receipt.get("schema_version"),
            "status": replay_receipt.get("status"),
            "case_receipts": replay_receipt.get("case_receipts", []),
            "metrics": replay_receipt.get("metrics", {}),
            "criteria": replay_receipt.get("criteria", []),
        },
    })

    try:
        source_after = _source_identity()
    except (KeyboardInterrupt, SystemExit) as exc:
        cancelled = True
        detail = _exception_detail(exc)
        failures.append(_failure_record("SOURCE_IDENTITY_CAPTURE_CANCELLED", detail))
        diagnostic_stderr += traceback.format_exc()
        source_after = {
            **source_before,
            "capture_error": detail,
        }
    except Exception as exc:  # noqa: BLE001 - preserve identity collection failure
        detail = _exception_detail(exc)
        failures.append(_failure_record("SOURCE_IDENTITY_CAPTURE_ERROR", detail))
        diagnostic_stderr += traceback.format_exc()
        source_after = {
            **source_before,
            "capture_error": detail,
        }
    source_stable = source_before == source_after
    if not source_stable:
        failures.append(_failure_record(
            "SOURCE_IDENTITY_CHANGED_DURING_RUN",
            "Git HEAD or tracked/untracked content identity changed between snapshots.",
        ))
    # Source-identity capture can itself fail after the first stderr write.
    _write_text(stderr_path, diagnostic_stderr + replay_stderr)
    _write_json(environment_path, _environment_receipt(source_before, source_after))

    try:
        model_readback = _read_json(model_path)
        if not package_valid:
            raise ValueError("models.json is an error receipt, not a valid model package")
        validate_analytical_model_package(model_readback)
        model_identity_matches = model_readback == model_package
    except Exception as exc:  # noqa: BLE001 - convert model drift to a failed run
        model_identity_matches = False
        failures.append(_failure_record("MODEL_ARTIFACT_IDENTITY_MISMATCH", _exception_detail(exc)))

    role_files = [
        ("protocol", protocol_path, "application/json"),
        ("resolved_config", config_path, "application/json"),
        ("model", model_path, "application/json"),
        ("controller", controller_path, "application/json"),
        ("environment", environment_path, "application/json"),
        ("raw_trace", raw_path, "application/json"),
        ("metrics", metrics_path, "application/json"),
        ("evaluator_receipt", replay_path, "application/json"),
        ("stdout", stdout_path, "text/plain"),
        ("stderr", stderr_path, "text/plain"),
    ]
    artifacts = _artifact_records_with_readback(output_dir, role_files)
    model_artifact_sha256 = next(
        item["sha256"] for item in artifacts if item["role"] == "model"
    )
    if model_artifact_sha256 != model_sha256:
        model_identity_matches = False
        failures.append(_failure_record(
            "MODEL_ARTIFACT_CHANGED_AFTER_REPLAY",
            "models.json SHA-256 changed after the replay-bound identity was captured.",
        ))

    failures.extend(_criterion_failures(
        "PRIMARY_CASE_CRITERION_FAIL", primary.get("case_receipts", [])
    ))
    failures.extend(_criterion_failures(
        "PRIMARY_SUITE_CRITERION_FAIL", primary.get("criteria", [])
    ))
    if replay_receipt.get("schema_version") == REPLAY_SCHEMA_VERSION:
        failures.extend(_criterion_failures(
            "REPLAY_CASE_CRITERION_FAIL", replay_receipt.get("case_receipts", [])
        ))
        failures.extend(_criterion_failures(
            "REPLAY_SUITE_CRITERION_FAIL", replay_receipt.get("criteria", [])
        ))

    primary_status = str(primary.get("status", "ERROR"))
    replay_status = str(replay_receipt.get("status", "ERROR"))
    if cancelled:
        manifest_status = "CANCELLED"
    elif (
        primary_status == "PASS"
        and replay_status == "PASS"
        and source_stable
        and model_identity_matches
        and not failures
    ):
        manifest_status = "COMPLETED"
    else:
        manifest_status = "FAILED"
    if manifest_status != "COMPLETED" and not failures:
        failures.append(_failure_record(
            "ANALYTICAL_BUNDLE_NOT_COMPLETED",
            f"primary={primary_status}, replay={replay_status}",
        ))

    manifest = {
        "schema_version": "PAPER_RUN_MANIFEST_V1",
        "run_id": run_id,
        "experiment_id": "EXP-V1-ANALYTICAL-FIXTURE-REGRESSION",
        "protocol_id": "V1-ANALYTICAL-FIXTURE-SUITE",
        "protocol_version": "1.0.0",
        "protocol_status": "FROZEN",
        "research_question_id": "RQ-V1-ANALYTICAL-FIXTURE",
        "hypothesis_id": "H-V1-SUPPORT-PAYLOAD-TIMESTEP",
        "run_class": "REGRESSION",
        "data_partition": "REGRESSION",
        "status": manifest_status,
        "evidence_scope": "SIM_ONLY_MUJOCO",
        "claim_boundary": CLAIM_BOUNDARY,
        "source_git_sha": source_before["git_sha"],
        "source_dirty": source_before["dirty"],
        "started_at": started_at,
        "completed_at": _utc_now(),
        "task_id": "V1-ANALYTICAL-FIXTURE-SUITE",
        "controller_family": "ORACLE",
        "controller_id": "PASSIVE_ANALYTICAL_FIXTURE_NO_ACTUATION_V1",
        "metric_set_id": "V1-ANALYTICAL-FIXTURE-METRICS-V1",
        "evaluator_id": "V1-ANALYTICAL-INDEPENDENT-REPLAY-V1",
        "plant": {
            "identity_id": "V1-ANALYTICAL-MODEL-PACKAGE-V1",
            "sha256": model_artifact_sha256,
        },
        "controller": {
            "identity_id": "PASSIVE_ANALYTICAL_FIXTURE_NO_ACTUATION_V1",
            "sha256": sha256_file(controller_path),
        },
        "seeds": {
            "deterministic": True,
            "training_seed": None,
            "evaluation_seed": None,
            "environment_seed": None,
            "scenario_seed": None,
            "seed_schedule_sha256": None,
        },
        "scenario": {
            "case_count": len(CASE_SPECS),
            "duration_s": float(ANALYTICAL_SUITE_CONTRACT["duration_s"]),
            "base_mass_kg": float(ANALYTICAL_SUITE_CONTRACT["base_mass_kg"]),
            "known_payload_kg": float(ANALYTICAL_SUITE_CONTRACT["known_payload_kg"]),
            "minimum_physics_dt_s": min(float(item["physics_dt_s"]) for item in CASE_SPECS),
            "maximum_physics_dt_s": max(float(item["physics_dt_s"]) for item in CASE_SPECS),
            "support_mode": "SINGLE_SUPPORT",
            "model_package_content_sha256": str(model_package.get("content_sha256", "UNAVAILABLE")),
        },
        "primary_outcomes": [
            "weight_balance_relative_error",
            "payload_mass_delta_error_kg",
            "payload_grf_delta_relative_error",
            "timestep_fine_delta",
            "raw_jacobian_closure_relative_max",
        ],
        "secondary_outcomes": [
            "minimum_contact_normal_force_n",
            "maximum_friction_utilization",
            "minimum_cop_support_margin_m",
            "timestep_observed_order",
        ],
        "assist_enabled": False,
        "tuning_performed_after_freeze": False,
        "artifacts": artifacts,
        "failures": failures,
    }
    manifest_path = output_dir / "paper_run_manifest.json"
    _write_json(manifest_path, manifest)
    if _read_json(manifest_path) != manifest:
        raise RuntimeError("paper_run_manifest.json JSON readback mismatch")
    validation = validate_paper_run_bundle(manifest_path)
    if validation["validation_status"] != "REGRESSION_BUNDLE_VALID_ONLY":
        raise RuntimeError("unexpected bundle validation status")
    if validation["paper_data_ready"] is not False:
        raise RuntimeError("regression bundle must not be paper-data ready")
    if validation["artifact_count"] != 10:
        raise RuntimeError("analytical bundle must contain exactly 10 artifact roles")
    return {
        "bundle_root": str(output_dir),
        "manifest": str(manifest_path),
        "primary_status": primary_status,
        "replay_status": replay_status,
        "source_dirty": source_before["dirty"],
        "validation": validation,
    }


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Build one bounded V1 analytical regression bundle"
    )
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    receipt = build_v1_analytical_bundle(args.output_dir)
    print(json.dumps(receipt, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()

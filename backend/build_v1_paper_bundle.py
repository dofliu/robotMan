"""Build one bounded V1 regression bundle using the paper-data contract.

The output is an integrity-validated REGRESSION bundle, not formal paper data.
It proves the packaging path before controller training/evaluation is scaled up.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import platform
import subprocess
import sys
import traceback
import uuid

import mujoco
import numpy as np

from config_schema import GaitParams, default_robot
from model_builder import build_mjcf
from paper_data_contract import artifact_record, sha256_file, validate_paper_run_bundle
from vv_oracles import STATIC_DOUBLE_SUPPORT_CONTRACT, run_static_double_support_oracle


BACKEND_DIR = Path(__file__).resolve().parent
REPO_ROOT = BACKEND_DIR.parent
PRIMARY_RESULT_KEYS = frozenset({
    "schema_version",
    "evidence_scope",
    "claim_boundary",
    "contract",
    "resolved_model",
    "completed_at",
    "status",
    "metrics",
    "criteria",
    "raw_trace",
})
REPLAY_RECEIPT_KEYS = frozenset({
    "schema_version",
    "source_schema_version",
    "source_artifact_sha256",
    "evidence_scope",
    "claim_boundary",
    "replayed_at",
    "status",
    "metrics",
    "criteria",
})
EXPECTED_RESOLVED_MODEL_KEYS = frozenset({
    "mass_kg",
    "gravity_mps2",
    "friction_cone",
    "solver",
    "adhesion_enabled",
    "model_xml_sha256",
    "nv",
    "nq",
    "nu",
    "nbody",
})
EXPECTED_PRIMARY_CRITERION_IDS = (
    "FINITE_STATE",
    "FWDINV_JOINT_FORCE",
    "FWDINV_CONSTRAINT_FORCE",
    "CONTACT_GENERALIZED_FORCE_CLOSURE",
    "BASE_FORCE_CLOSURE",
    "BASE_MOMENT_CLOSURE",
    "JOINT_TORQUE_CLOSURE",
    "UNILATERAL_NORMAL_FORCE",
    "FRICTION_CONE_FEASIBILITY",
    "COP_SUPPORT_MARGIN",
    "BILATERAL_COP_AVAILABLE",
    "WEIGHT_BALANCE",
    "LINEAR_STATICITY",
    "ANGULAR_STATICITY",
    "POSTURE_STATICITY",
    "BILATERAL_CONTACT",
)
EXPECTED_PRIMARY_METRIC_KEYS = frozenset({
    "finite",
    "forward_inverse_joint_force_norm_max",
    "forward_inverse_constraint_force_norm_max",
    "contact_generalized_force_component_relative_max",
    "base_force_residual_relative_max",
    "base_moment_residual_relative_max",
    "joint_torque_residual_relative_max",
    "minimum_contact_normal_force_n",
    "maximum_friction_utilization",
    "minimum_cop_support_margin_m",
    "minimum_loaded_foot_count",
    "physics_step_count",
    "physics_sample_rate_hz",
    "evaluation_step_count",
    "model_mass_kg",
    "model_weight_n",
    "mean_vertical_grf_n",
    "weight_balance_relative_error",
    "mean_linear_speed_mps",
    "mean_angular_speed_rps",
    "max_abs_posture_deg",
    "bilateral_contact_duty",
})
EXPECTED_REPLAY_CRITERION_IDS = (
    "TRACE_STEP_COUNT",
    "TRACE_SAMPLE_PERIOD",
    "TRACE_TIME_GRID",
    "EVALUATION_STEP_COUNT",
    "RAW_JACOBIAN_CLOSURE_ALL_STEPS",
    "CONTACT_GENERALIZED_FORCE_CLOSURE",
    "BASE_FORCE_CLOSURE",
    "BASE_MOMENT_CLOSURE",
    "JOINT_TORQUE_CLOSURE",
    "UNILATERAL_NORMAL_FORCE",
    "FRICTION_CONE_FEASIBILITY",
    "COP_SUPPORT_MARGIN",
    "BILATERAL_COP_AVAILABLE",
    "PRIMARY_REPLAY_METRIC_MATCH",
)
EXPECTED_REPLAY_METRIC_KEYS = frozenset({
    "trace_step_count",
    "evaluation_step_count",
    "sample_period_error_max_s",
    "time_grid_error_max_s",
    "raw_jacobian_closure_all_steps_relative_max",
    "contact_generalized_force_component_relative_max",
    "base_force_residual_relative_max",
    "base_moment_residual_relative_max",
    "joint_torque_residual_relative_max",
    "minimum_contact_normal_force_n",
    "maximum_friction_utilization",
    "minimum_cop_support_margin_m",
    "minimum_loaded_foot_count",
    "primary_metric_delta_max",
})


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
        newline="\n",
    )


def _git_output(*args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    return completed.stdout.strip()


def _source_identity() -> tuple[str, bool]:
    git_sha = _git_output("rev-parse", "HEAD")
    dirty = bool(_git_output("status", "--porcelain", "--untracked-files=all"))
    return git_sha, dirty


def _environment_receipt(
    source_before: tuple[str, bool],
    source_after: tuple[str, bool],
) -> dict:
    packages = {}
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
        "mujoco_runtime": mujoco.__version__,
        "numpy_runtime": np.__version__,
        "source_identity": {
            "before": {
                "git_sha": source_before[0],
                "dirty": source_before[1],
            },
            "after": {
                "git_sha": source_after[0],
                "dirty": source_after[1],
            },
            "stable_during_run": source_before == source_after,
        },
    }


def _replay_error_receipt(
    result: dict,
    raw_path: Path,
    *,
    return_code: int | None,
    error_type: str,
    detail: str | None = None,
) -> dict:
    """保留 replay process/schema error，而不是遺失整個 regression bundle。"""
    return {
        "schema_version": "V1_RAW_JACOBIAN_REPLAY_ERROR_RECEIPT_V1",
        "source_schema_version": result["schema_version"],
        "source_artifact_sha256": sha256_file(raw_path),
        "evidence_scope": "PROCESS_INDEPENDENT_RAW_JACOBIAN_REPLAY_ERROR",
        "claim_boundary": (
            "SIM_ONLY_MUJOCO / NOT_PHYSICALLY_VALIDATED. Replay process error "
            "retained for software diagnosis only; this is not "
            "contact-model, plant, hardware, or V1 validation."
        ),
        "replayed_at": _utc_now(),
        "status": "ERROR",
        "return_code": return_code,
        "error_type": error_type,
        "detail": detail,
        "criteria": [],
    }


def _primary_error_receipt(
    *,
    error_type: str,
    error_class: str,
    detail: str,
) -> dict:
    """將 primary oracle failure 轉成可序列化、不可誤判 PASS 的 receipt。"""
    return {
        "schema_version": "V1_PRIMARY_ORACLE_ERROR_RECEIPT_V1",
        "evidence_scope": "SIM_ONLY_MUJOCO_SOFTWARE_ERROR",
        "claim_boundary": (
            "SIM_ONLY_MUJOCO / NOT_PHYSICALLY_VALIDATED. Primary oracle error "
            "retained for software diagnosis only; this is not "
            "contact-model, plant, hardware, or V1 validation."
        ),
        "executed_at": _utc_now(),
        "status": "ERROR",
        "error_type": error_type,
        "error_class": error_class,
        "detail": detail,
        "contract": STATIC_DOUBLE_SUPPORT_CONTRACT,
        "metrics": {},
        "criteria": [],
    }


def _non_finite_diagnostics(value: object) -> list[str]:
    """回報 non-finite JSON path；以字串保存 NaN/Infinity 而不輸出非法 JSON。"""
    found: list[str] = []

    def visit(item: object, path: str) -> None:
        if len(found) >= 20:
            return
        if isinstance(item, (float, np.floating)) and not math.isfinite(float(item)):
            numeric = float(item)
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


def _valid_replay_receipt(
    receipt: object,
    source_result: dict,
    source_artifact_sha256: str,
) -> bool:
    if not isinstance(receipt, dict):
        return False
    if set(receipt) != REPLAY_RECEIPT_KEYS:
        return False
    if _non_finite_diagnostics(receipt):
        return False
    if receipt.get("schema_version") != "V1_RAW_JACOBIAN_REPLAY_RECEIPT_V2":
        return False
    if receipt.get("source_schema_version") != source_result.get("schema_version"):
        return False
    if receipt.get("source_artifact_sha256") != source_artifact_sha256:
        return False
    if receipt.get("evidence_scope") != "PROCESS_INDEPENDENT_RAW_JACOBIAN_REPLAY_ONLY":
        return False
    if "SIM_ONLY_MUJOCO / NOT_PHYSICALLY_VALIDATED" not in str(
        receipt.get("claim_boundary", "")
    ):
        return False
    if not _valid_aware_iso_timestamp(receipt.get("replayed_at")):
        return False
    metrics = receipt.get("metrics")
    if not isinstance(metrics, dict) or set(metrics) != EXPECTED_REPLAY_METRIC_KEYS:
        return False
    if any(
        isinstance(metrics[key], bool)
        or not isinstance(metrics[key], (int, float))
        or not math.isfinite(float(metrics[key]))
        for key in EXPECTED_REPLAY_METRIC_KEYS
    ):
        return False
    criteria = receipt.get("criteria")
    if not isinstance(criteria, list) or len(criteria) != len(EXPECTED_REPLAY_CRITERION_IDS):
        return False
    if [item.get("id") if isinstance(item, dict) else None for item in criteria] != list(
        EXPECTED_REPLAY_CRITERION_IDS
    ):
        return False

    try:
        contract = source_result["contract"]
        tolerances = contract["tolerances"]
        expected_step_count = round(
            float(contract["duration_s"]) / float(contract["physics_dt_s"])
        )
        expected_evaluation_step_count = round(
            float(contract["evaluation_window_s"])
            / float(contract["physics_dt_s"])
        )
        expected_specs = {
            "TRACE_STEP_COUNT": (
                "trace_step_count",
                "==",
                expected_step_count,
                "count",
            ),
            "TRACE_SAMPLE_PERIOD": (
                "sample_period_error_max_s",
                "<=",
                1.0e-12,
                "s",
            ),
            "TRACE_TIME_GRID": (
                "time_grid_error_max_s",
                "<=",
                1.0e-12,
                "s",
            ),
            "EVALUATION_STEP_COUNT": (
                "evaluation_step_count",
                "==",
                expected_evaluation_step_count,
                "count",
            ),
            "RAW_JACOBIAN_CLOSURE_ALL_STEPS": (
                "raw_jacobian_closure_all_steps_relative_max",
                "<=",
                tolerances["contact_generalized_force_component_relative_max"],
                "normalized max component",
            ),
            "CONTACT_GENERALIZED_FORCE_CLOSURE": (
                "contact_generalized_force_component_relative_max",
                "<=",
                tolerances["contact_generalized_force_component_relative_max"],
                "normalized max component",
            ),
            "BASE_FORCE_CLOSURE": (
                "base_force_residual_relative_max",
                "<=",
                tolerances["base_force_residual_relative_max"],
                "normalized force norm",
            ),
            "BASE_MOMENT_CLOSURE": (
                "base_moment_residual_relative_max",
                "<=",
                tolerances["base_moment_residual_relative_max"],
                "normalized moment norm",
            ),
            "JOINT_TORQUE_CLOSURE": (
                "joint_torque_residual_relative_max",
                "<=",
                tolerances["joint_torque_residual_relative_max"],
                "normalized torque norm",
            ),
            "UNILATERAL_NORMAL_FORCE": (
                "minimum_contact_normal_force_n",
                ">=",
                tolerances["minimum_contact_normal_force_n"],
                "N",
            ),
            "FRICTION_CONE_FEASIBILITY": (
                "maximum_friction_utilization",
                "<=",
                tolerances["maximum_friction_utilization"],
                "utilization ratio",
            ),
            "COP_SUPPORT_MARGIN": (
                "minimum_cop_support_margin_m",
                ">=",
                tolerances["minimum_cop_support_margin_m"],
                "m",
            ),
            "BILATERAL_COP_AVAILABLE": (
                "minimum_loaded_foot_count",
                ">=",
                tolerances["minimum_loaded_foot_count"],
                "foot count",
            ),
            "PRIMARY_REPLAY_METRIC_MATCH": (
                "primary_metric_delta_max",
                "<=",
                1.0e-12,
                "max absolute delta",
            ),
        }
    except (KeyError, TypeError, ValueError, ZeroDivisionError, OverflowError):
        return False

    recomputed_passes = _validated_criterion_passes(
        metrics,
        criteria,
        EXPECTED_REPLAY_CRITERION_IDS,
        expected_specs,
    )
    if recomputed_passes is None:
        return False
    expected_status = "PASS" if all(recomputed_passes) else "FAIL"
    return receipt.get("status") == expected_status


def _finite_criterion_value(value: object) -> bool:
    if isinstance(value, bool):
        return True
    return isinstance(value, (int, float)) and math.isfinite(float(value))


def _valid_aware_iso_timestamp(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _same_scalar(left: object, right: object) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is bool and type(right) is bool and left is right
    return (
        _finite_criterion_value(left)
        and _finite_criterion_value(right)
        and float(left) == float(right)
    )


def _validated_criterion_passes(
    metrics: dict,
    criteria: list,
    expected_ids: tuple[str, ...],
    expected_specs: dict[str, tuple[str, str, object, str]],
) -> list[bool] | None:
    if [item.get("id") if isinstance(item, dict) else None for item in criteria] != list(
        expected_ids
    ):
        return None
    recomputed_passes: list[bool] = []
    for item in criteria:
        if set(item) != {"id", "passed", "value", "operator", "limit", "unit"}:
            return None
        if type(item["passed"]) is not bool:
            return None
        metric_key, operator, limit, unit = expected_specs[item["id"]]
        if item["operator"] != operator or item["unit"] != unit:
            return None
        if not _same_scalar(item["value"], metrics.get(metric_key)):
            return None
        if not _same_scalar(item["limit"], limit):
            return None
        if operator == "<=":
            recomputed_passed = float(item["value"]) <= float(limit)
        elif operator == ">=":
            recomputed_passed = float(item["value"]) >= float(limit)
        else:
            recomputed_passed = item["value"] == limit
        if item["passed"] is not recomputed_passed:
            return None
        recomputed_passes.append(recomputed_passed)
    return recomputed_passes


def _valid_primary_result(
    result: object,
    expected_model_xml_sha256: str,
) -> bool:
    """Primary result 必須符合 frozen V4 schema，不信任自報 PASS。"""
    if not isinstance(result, dict):
        return False
    if set(result) != PRIMARY_RESULT_KEYS:
        return False
    if result.get("schema_version") != "V1_STATIC_DOUBLE_SUPPORT_ORACLE_V4":
        return False
    if result.get("evidence_scope") != (
        "MUJOCO_INTERNAL_RAW_JACOBIAN_WRENCH_RECONSTRUCTION_ONLY"
    ):
        return False
    if "SIM_ONLY_MUJOCO / NOT_PHYSICALLY_VALIDATED" not in str(
        result.get("claim_boundary", "")
    ):
        return False
    if not _valid_aware_iso_timestamp(result.get("completed_at")):
        return False
    if result.get("contract") != STATIC_DOUBLE_SUPPORT_CONTRACT:
        return False
    resolved_model = result.get("resolved_model")
    if not isinstance(resolved_model, dict):
        return False
    if set(resolved_model) != EXPECTED_RESOLVED_MODEL_KEYS:
        return False
    if resolved_model.get("model_xml_sha256") != expected_model_xml_sha256:
        return False
    trace = result.get("raw_trace")
    if not isinstance(trace, list):
        return False

    metrics = result.get("metrics")
    if not isinstance(metrics, dict) or set(metrics) != EXPECTED_PRIMARY_METRIC_KEYS:
        return False
    if type(metrics.get("finite")) is not bool:
        return False
    if any(
        isinstance(metrics[key], bool)
        or not isinstance(metrics[key], (int, float))
        or not math.isfinite(float(metrics[key]))
        for key in EXPECTED_PRIMARY_METRIC_KEYS - {"finite"}
    ):
        return False

    contract = result["contract"]
    expected_steps = round(contract["duration_s"] / contract["physics_dt_s"])
    expected_evaluation_steps = round(
        contract["evaluation_window_s"] / contract["physics_dt_s"]
    )
    if len(trace) != expected_steps:
        return False
    if metrics["physics_step_count"] != expected_steps:
        return False
    if metrics["evaluation_step_count"] != expected_evaluation_steps:
        return False
    if float(metrics["physics_sample_rate_hz"]) != 1.0 / contract["physics_dt_s"]:
        return False

    tolerances = contract["tolerances"]
    expected_specs = {
        "FINITE_STATE": ("finite", "==", True, "bool"),
        "FWDINV_JOINT_FORCE": (
            "forward_inverse_joint_force_norm_max",
            "<=",
            tolerances["forward_inverse_joint_force_norm_max"],
            "generalized-force norm",
        ),
        "FWDINV_CONSTRAINT_FORCE": (
            "forward_inverse_constraint_force_norm_max",
            "<=",
            tolerances["forward_inverse_constraint_force_norm_max"],
            "constraint-force norm",
        ),
        "CONTACT_GENERALIZED_FORCE_CLOSURE": (
            "contact_generalized_force_component_relative_max",
            "<=",
            tolerances["contact_generalized_force_component_relative_max"],
            "normalized max component",
        ),
        "BASE_FORCE_CLOSURE": (
            "base_force_residual_relative_max",
            "<=",
            tolerances["base_force_residual_relative_max"],
            "normalized force norm",
        ),
        "BASE_MOMENT_CLOSURE": (
            "base_moment_residual_relative_max",
            "<=",
            tolerances["base_moment_residual_relative_max"],
            "normalized moment norm",
        ),
        "JOINT_TORQUE_CLOSURE": (
            "joint_torque_residual_relative_max",
            "<=",
            tolerances["joint_torque_residual_relative_max"],
            "normalized torque norm",
        ),
        "UNILATERAL_NORMAL_FORCE": (
            "minimum_contact_normal_force_n",
            ">=",
            tolerances["minimum_contact_normal_force_n"],
            "N",
        ),
        "FRICTION_CONE_FEASIBILITY": (
            "maximum_friction_utilization",
            "<=",
            tolerances["maximum_friction_utilization"],
            "utilization ratio",
        ),
        "COP_SUPPORT_MARGIN": (
            "minimum_cop_support_margin_m",
            ">=",
            tolerances["minimum_cop_support_margin_m"],
            "m",
        ),
        "BILATERAL_COP_AVAILABLE": (
            "minimum_loaded_foot_count",
            ">=",
            tolerances["minimum_loaded_foot_count"],
            "foot count",
        ),
        "WEIGHT_BALANCE": (
            "weight_balance_relative_error",
            "<=",
            tolerances["weight_balance_relative_error_max"],
            "relative error",
        ),
        "LINEAR_STATICITY": (
            "mean_linear_speed_mps",
            "<=",
            tolerances["mean_linear_speed_max_mps"],
            "m/s",
        ),
        "ANGULAR_STATICITY": (
            "mean_angular_speed_rps",
            "<=",
            tolerances["mean_angular_speed_max_rps"],
            "rad/s",
        ),
        "POSTURE_STATICITY": (
            "max_abs_posture_deg",
            "<=",
            tolerances["max_abs_posture_deg"],
            "deg",
        ),
        "BILATERAL_CONTACT": (
            "bilateral_contact_duty",
            ">=",
            tolerances["bilateral_contact_duty_min"],
            "fraction",
        ),
    }
    criteria = result.get("criteria")
    if not isinstance(criteria, list) or len(criteria) != len(
        EXPECTED_PRIMARY_CRITERION_IDS
    ):
        return False
    recomputed_passes = _validated_criterion_passes(
        metrics,
        criteria,
        EXPECTED_PRIMARY_CRITERION_IDS,
        expected_specs,
    )
    if recomputed_passes is None:
        return False
    expected_status = "PASS" if all(recomputed_passes) else "FAIL"
    return result.get("status") == expected_status


def _reject_nonstandard_json(value: str) -> None:
    raise ValueError(f"non-standard JSON constant is forbidden: {value}")


def _captured_process_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def build_v1_paper_bundle(output_dir: Path) -> dict:
    """建立第一包 paper-contract regression evidence並立即 readback。"""
    source_before = _source_identity()
    output_dir = output_dir.resolve()
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(exist_ok=False)
    started_at = _utc_now()
    run_id = f"v1-regression-{datetime.now(timezone.utc):%Y%m%dt%H%M%S}-{uuid.uuid4().hex[:8]}"
    robot = default_robot()
    gait = GaitParams()
    model_xml = build_mjcf(robot, [], dynamic=True)
    model_xml_sha256 = f"sha256:{hashlib.sha256(model_xml.encode('utf-8')).hexdigest()}"

    raw_path = output_dir / "raw_oracle.json"
    stdout_path = output_dir / "stdout.txt"
    stderr_path = output_dir / "stderr.txt"
    replay_path = output_dir / "evaluator_receipt.json"
    primary_failure: dict | None = None
    primary_stderr = ""
    try:
        result = run_static_double_support_oracle(
            include_raw_trace=True,
            robot_config=robot,
            gait_params=gait,
        )
    except Exception as exc:  # noqa: BLE001 - evidence bundle 必須保留原始 oracle failure
        primary_failure = {
            "error_type": "PRIMARY_ORACLE_EXCEPTION",
            "error_class": type(exc).__name__,
            "detail": str(exc) or repr(exc),
        }
        primary_stderr = traceback.format_exc()
        result = _primary_error_receipt(**primary_failure)
    else:
        non_finite = _non_finite_diagnostics(result)
        if non_finite:
            detail = "Non-finite primary result retained at " + ", ".join(non_finite)
            primary_failure = {
                "error_type": "PRIMARY_RESULT_NONFINITE",
                "error_class": "NonFinitePrimaryResult",
                "detail": detail,
            }
            primary_stderr = detail + "\n"
            result = _primary_error_receipt(**primary_failure)
        elif not _valid_primary_result(result, model_xml_sha256):
            primary_failure = {
                "error_type": "PRIMARY_RESULT_INVALID_RECEIPT",
                "error_class": "InvalidPrimaryResult",
                "detail": (
                    "Primary result did not match the frozen V4 schema, metric, "
                    "criterion, threshold, or raw-trace contract."
                ),
            }
            primary_stderr = primary_failure["detail"] + "\n"
            result = _primary_error_receipt(**primary_failure)
        else:
            try:
                _write_json(raw_path, result)
            except (TypeError, ValueError) as exc:
                primary_failure = {
                    "error_type": "PRIMARY_RESULT_SERIALIZATION_ERROR",
                    "error_class": type(exc).__name__,
                    "detail": str(exc) or repr(exc),
                }
                primary_stderr = f"{type(exc).__name__}: {str(exc) or repr(exc)}\n"
                result = _primary_error_receipt(**primary_failure)

    if primary_failure is not None:
        _write_json(raw_path, result)
        stdout_path.write_text("", encoding="utf-8", newline="\n")
        stderr_path.write_text(primary_stderr, encoding="utf-8", newline="\n")
        replay_receipt = _replay_error_receipt(
            result,
            raw_path,
            return_code=None,
            error_type="PRIMARY_ORACLE_NOT_REPLAYED",
            detail=primary_failure["detail"],
        )
    else:
        try:
            replay_process = subprocess.run(
                [
                    sys.executable,
                    "-X",
                    "utf8",
                    str(BACKEND_DIR / "v1_replay.py"),
                    str(raw_path),
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
                timeout=60,
            )
        except (OSError, subprocess.SubprocessError, UnicodeError) as exc:
            captured_stdout = _captured_process_text(getattr(exc, "stdout", None))
            captured_stderr = _captured_process_text(getattr(exc, "stderr", None))
            diagnostic = traceback.format_exc()
            stdout_path.write_text(
                captured_stdout,
                encoding="utf-8",
                newline="\n",
            )
            stderr_path.write_text(
                captured_stderr + diagnostic,
                encoding="utf-8",
                newline="\n",
            )
            replay_receipt = _replay_error_receipt(
                result,
                raw_path,
                return_code=None,
                error_type="PROCESS_EXCEPTION",
                detail=f"{type(exc).__name__}: {str(exc) or repr(exc)}",
            )
        else:
            stdout_path.write_text(
                replay_process.stdout,
                encoding="utf-8",
                newline="\n",
            )
            stderr_path.write_text(
                replay_process.stderr,
                encoding="utf-8",
                newline="\n",
            )
            if replay_process.returncode != 0:
                replay_receipt = _replay_error_receipt(
                    result,
                    raw_path,
                    return_code=replay_process.returncode,
                    error_type="PROCESS_EXIT_NONZERO",
                )
            else:
                try:
                    parsed_replay_receipt = json.loads(
                        replay_process.stdout,
                        parse_constant=_reject_nonstandard_json,
                    )
                except (json.JSONDecodeError, ValueError):
                    replay_receipt = _replay_error_receipt(
                        result,
                        raw_path,
                        return_code=replay_process.returncode,
                        error_type="INVALID_JSON_STDOUT",
                    )
                else:
                    if _valid_replay_receipt(
                        parsed_replay_receipt,
                        result,
                        sha256_file(raw_path),
                    ):
                        replay_receipt = parsed_replay_receipt
                    else:
                        replay_receipt = _replay_error_receipt(
                            result,
                            raw_path,
                            return_code=replay_process.returncode,
                            error_type="INVALID_REPLAY_RECEIPT",
                        )
    _write_json(replay_path, replay_receipt)

    protocol_path = output_dir / "protocol.json"
    config_path = output_dir / "resolved_config.json"
    model_path = output_dir / "model.xml"
    controller_path = output_dir / "controller.json"
    environment_path = output_dir / "environment.json"
    metrics_path = output_dir / "metrics.json"
    _write_json(protocol_path, {
        "protocol_id": "V1-STATIC-CONTACT-REGRESSION",
        "protocol_version": "4.0.0",
        "protocol_status": "FROZEN",
        "research_question_id": "RQ-MODEL-STATIC-CONTACT",
        "hypothesis_id": "H-MODEL-STATIC-RAW-JACOBIAN-CLOSURE-V4",
        "contract": result["contract"],
        "claim_boundary": result["claim_boundary"],
    })
    _write_json(config_path, {
        "robot": robot.model_dump(mode="json"),
        "gait": gait.model_dump(mode="json"),
        "obstacles": [],
        "assist_enabled": False,
    })
    model_path.write_text(model_xml, encoding="utf-8", newline="\n")
    _write_json(controller_path, {
        "controller_id": "STATIC-DOUBLE-SUPPORT-HOLD-V1",
        "controller_family": "ORACLE",
        "assist_enabled": False,
        "startup_assist_enabled": False,
    })
    source_after = _source_identity()
    source_identity_stable = source_before == source_after
    _write_json(
        environment_path,
        _environment_receipt(source_before, source_after),
    )
    _write_json(metrics_path, {
        "primary": {
            "schema_version": result["schema_version"],
            "status": result["status"],
            "metrics": result["metrics"],
            "criteria": result["criteria"],
        },
        "replay": replay_receipt,
    })

    role_files = [
        ("protocol", protocol_path, "application/json"),
        ("resolved_config", config_path, "application/json"),
        ("model", model_path, "application/xml"),
        ("controller", controller_path, "application/json"),
        ("environment", environment_path, "application/json"),
        ("raw_trace", raw_path, "application/json"),
        ("metrics", metrics_path, "application/json"),
        ("evaluator_receipt", replay_path, "application/json"),
        ("stdout", stdout_path, "text/plain"),
        ("stderr", stderr_path, "text/plain"),
    ]
    artifacts = [
        artifact_record(
            output_dir,
            path,
            role=role,
            media_type=media_type,
        )
        for role, path, media_type in role_files
    ]
    git_sha, source_dirty = source_before
    model_artifact_sha256 = sha256_file(model_path)
    model_identity_matches = model_artifact_sha256 == model_xml_sha256
    completed_at = _utc_now()
    failed_criteria = [item for item in result["criteria"] if not item["passed"]]
    replay_failed_criteria = [
        item for item in replay_receipt.get("criteria", []) if not item["passed"]
    ]
    failures = [
        {
            "failure_type": "ORACLE_CRITERION_FAIL",
            "timestamp_s": None,
            "detail": f"{item['id']} value={item['value']} limit={item['limit']}",
        }
        for item in failed_criteria
    ]
    if primary_failure is not None:
        failures.append({
            "failure_type": primary_failure["error_type"],
            "timestamp_s": None,
            "detail": (
                f"{primary_failure['error_class']}: {primary_failure['detail']}"
            )[:1000],
        })
    failures.extend({
        "failure_type": "REPLAY_CRITERION_FAIL",
        "timestamp_s": None,
        "detail": f"{item['id']} value={item['value']} limit={item['limit']}",
    } for item in replay_failed_criteria)
    if replay_receipt["status"] == "ERROR" and primary_failure is None:
        failures.append({
            "failure_type": "REPLAY_PROCESS_ERROR",
            "timestamp_s": None,
            "detail": (
                f"Replay error {replay_receipt['error_type']}; process exit code "
                f"{replay_receipt['return_code']}; stderr artifact retained."
            ),
        })
    if not source_identity_stable:
        failures.append({
            "failure_type": "SOURCE_IDENTITY_CHANGED_DURING_RUN",
            "timestamp_s": None,
            "detail": (
                "Git SHA/dirty identity changed between the pre-run and post-run "
                "snapshots; both snapshots are retained in environment.json."
            ),
        })
    if not model_identity_matches:
        failures.append({
            "failure_type": "MODEL_ARTIFACT_IDENTITY_MISMATCH",
            "timestamp_s": None,
            "detail": (
                "The model.xml artifact SHA-256 does not match the XML identity bound "
                "to the primary oracle configuration."
            ),
        })
    manifest = {
        "schema_version": "PAPER_RUN_MANIFEST_V1",
        "run_id": run_id,
        "experiment_id": "EXP-V1-MODEL-EVIDENCE-REGRESSION",
        "protocol_id": "V1-STATIC-CONTACT-REGRESSION",
        "protocol_version": "4.0.0",
        "protocol_status": "FROZEN",
        "research_question_id": "RQ-MODEL-STATIC-CONTACT",
        "hypothesis_id": "H-MODEL-STATIC-RAW-JACOBIAN-CLOSURE-V4",
        "run_class": "REGRESSION",
        "data_partition": "REGRESSION",
        "status": (
            "COMPLETED"
            if (
                result["status"] == "PASS"
                and replay_receipt["status"] == "PASS"
                and source_identity_stable
                and model_identity_matches
            )
            else "FAILED"
        ),
        "evidence_scope": "SIM_ONLY_MUJOCO",
        "claim_boundary": (
            "SIM_ONLY_MUJOCO / NOT_PHYSICALLY_VALIDATED. Static MuJoCo raw-Jacobian "
            "numerical/contact regression only. This bundle is not a formal controller "
            "comparison, physical validation, or paper result."
        ),
        "source_git_sha": git_sha,
        "source_dirty": source_dirty,
        "started_at": started_at,
        "completed_at": completed_at,
        "task_id": "V1-STATIC-DOUBLE-SUPPORT",
        "controller_family": "ORACLE",
        "controller_id": "STATIC-DOUBLE-SUPPORT-HOLD-V1",
        "metric_set_id": "V1-STATIC-CONTACT-METRICS-V4",
        "evaluator_id": "V1-RAW-JACOBIAN-REPLAY-RECEIPT-V2",
        "plant": {
            "identity_id": "HUMANOID-DESIGN-MUJOCO-V1",
            "sha256": model_artifact_sha256,
        },
        "controller": {
            "identity_id": "STATIC-DOUBLE-SUPPORT-HOLD-V1",
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
            "duration_s": float(result["contract"]["duration_s"]),
            "physics_dt_s": float(result["contract"]["physics_dt_s"]),
            "payload_kg": float(robot.masses.payload),
            "support_mode": "DOUBLE_SUPPORT",
        },
        "primary_outcomes": [
            "base_force_residual_relative_max",
            "base_moment_residual_relative_max",
            "joint_torque_residual_relative_max",
            "maximum_friction_utilization",
            "minimum_cop_support_margin_m",
        ],
        "secondary_outcomes": [
            "weight_balance_relative_error",
            "minimum_contact_normal_force_n",
            "mean_linear_speed_mps",
        ],
        "assist_enabled": False,
        "tuning_performed_after_freeze": False,
        "artifacts": artifacts,
        "failures": failures,
    }
    manifest_path = output_dir / "paper_run_manifest.json"
    _write_json(manifest_path, manifest)
    validation = validate_paper_run_bundle(manifest_path)
    return {
        "bundle_root": str(output_dir),
        "manifest": str(manifest_path),
        "primary_status": result["status"],
        "replay_status": replay_receipt["status"],
        "source_dirty": source_dirty,
        "validation": validation,
    }


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Build a V1 paper-contract regression bundle")
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    receipt = build_v1_paper_bundle(args.output_dir)
    print(json.dumps(receipt, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

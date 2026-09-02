"""Paper-run manifest and fail-closed artifact inventory validation.

Passing this validator establishes bundle integrity only. Formal paper-data
readiness additionally requires a frozen HOLDOUT protocol and clean source.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


SCHEMA_VERSION = "PAPER_RUN_MANIFEST_V1"
SHA256_PATTERN = r"^sha256:[0-9a-f]{64}$"
GIT_SHA_PATTERN = r"^[0-9a-f]{40}$"
ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_.-]{2,95}$"
MAX_JSON_BYTES = 16 * 1024 * 1024
REQUIRED_ARTIFACT_ROLES = {
    "protocol",
    "resolved_config",
    "model",
    "controller",
    "environment",
    "raw_trace",
    "metrics",
    "evaluator_receipt",
    "stdout",
    "stderr",
}


class PaperDataIntegrityError(RuntimeError):
    """Artifact path、size、hash 或 inventory integrity失敗。"""


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, strict=True)


class ArtifactRecord(ContractModel):
    role: Literal[
        "protocol",
        "resolved_config",
        "model",
        "controller",
        "environment",
        "raw_trace",
        "metrics",
        "evaluator_receipt",
        "stdout",
        "stderr",
        "events",
        "checkpoint",
        "statistics",
        "table_input",
        "figure_input",
    ]
    path: str = Field(min_length=1, max_length=240)
    media_type: str = Field(min_length=1, max_length=120)
    bytes: int = Field(ge=0)
    sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def require_safe_relative_path(self):
        normalized = self.path.replace("\\", "/")
        pure = PurePosixPath(normalized)
        if pure.is_absolute() or ".." in pure.parts or normalized != pure.as_posix():
            raise ValueError("artifact path 必須是 canonical safe relative POSIX path")
        return self


class SeedContract(ContractModel):
    deterministic: bool
    training_seed: int | None = Field(default=None, ge=0)
    evaluation_seed: int | None = Field(default=None, ge=0)
    environment_seed: int | None = Field(default=None, ge=0)
    scenario_seed: int | None = Field(default=None, ge=0)
    seed_schedule_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)


class IdentityRecord(ContractModel):
    identity_id: str = Field(pattern=ID_PATTERN)
    sha256: str = Field(pattern=SHA256_PATTERN)


class FailureRecord(ContractModel):
    failure_type: str = Field(min_length=1, max_length=120)
    timestamp_s: float | None = Field(default=None, ge=0.0)
    detail: str = Field(min_length=1, max_length=1000)


ScenarioValue = str | int | float | bool


class PaperRunManifest(ContractModel):
    schema_version: Literal["PAPER_RUN_MANIFEST_V1"]
    run_id: str = Field(pattern=ID_PATTERN)
    experiment_id: str = Field(pattern=ID_PATTERN)
    protocol_id: str = Field(pattern=ID_PATTERN)
    protocol_version: str = Field(pattern=ID_PATTERN)
    protocol_status: Literal["DRAFT", "FROZEN"]
    research_question_id: str = Field(pattern=ID_PATTERN)
    hypothesis_id: str = Field(pattern=ID_PATTERN)
    run_class: Literal["DEVELOPMENT", "CALIBRATION", "FORMAL_EVALUATION", "REGRESSION"]
    data_partition: Literal["DEVELOPMENT", "CALIBRATION", "HOLDOUT", "REGRESSION"]
    status: Literal["COMPLETED", "FAILED", "CANCELLED"]
    evidence_scope: Literal["SIM_ONLY_MUJOCO", "SIL", "HIL", "BENCH", "ROBOT"]
    claim_boundary: str = Field(min_length=20, max_length=2000)
    source_git_sha: str = Field(pattern=GIT_SHA_PATTERN)
    source_dirty: bool
    started_at: str = Field(min_length=20, max_length=40)
    completed_at: str = Field(min_length=20, max_length=40)
    task_id: str = Field(pattern=ID_PATTERN)
    controller_family: Literal["MODEL_BASED", "LEARNING_BASED", "HYBRID", "ORACLE"]
    controller_id: str = Field(pattern=ID_PATTERN)
    metric_set_id: str = Field(pattern=ID_PATTERN)
    evaluator_id: str = Field(pattern=ID_PATTERN)
    plant: IdentityRecord
    controller: IdentityRecord
    seeds: SeedContract
    scenario: dict[str, ScenarioValue] = Field(min_length=1, max_length=100)
    primary_outcomes: list[str] = Field(min_length=1, max_length=20)
    secondary_outcomes: list[str] = Field(default_factory=list, max_length=100)
    assist_enabled: bool
    tuning_performed_after_freeze: bool
    artifacts: list[ArtifactRecord] = Field(min_length=1, max_length=100)
    failures: list[FailureRecord] = Field(default_factory=list, max_length=1000)

    @model_validator(mode="after")
    def enforce_inventory_and_formal_rules(self):
        if self.controller_id != self.controller.identity_id:
            raise ValueError("controller_id 必須等於 actual controller identity_id")
        roles = [item.role for item in self.artifacts]
        paths = [item.path for item in self.artifacts]
        if len(roles) != len(set(roles)):
            raise ValueError("artifact role 不可重複")
        if len(paths) != len(set(paths)):
            raise ValueError("artifact path 不可重複")
        missing_roles = sorted(REQUIRED_ARTIFACT_ROLES - set(roles))
        if missing_roles:
            raise ValueError(f"required artifact roles missing: {missing_roles}")
        if self.status in {"FAILED", "CANCELLED"} and not self.failures:
            raise ValueError("FAILED/CANCELLED run 必須保留 failure record")
        if self.status == "COMPLETED" and self.failures:
            raise ValueError("COMPLETED run 不可夾帶 failure record或改標 terminal failure")
        if self.run_class == "FORMAL_EVALUATION":
            if self.protocol_status != "FROZEN":
                raise ValueError("FORMAL_EVALUATION protocol 必須 FROZEN")
            if self.data_partition != "HOLDOUT":
                raise ValueError("FORMAL_EVALUATION 必須使用 HOLDOUT partition")
            if self.source_dirty:
                raise ValueError("FORMAL_EVALUATION 不可使用 dirty source")
            if self.assist_enabled:
                raise ValueError("current Study A formal contract要求 assist OFF")
            if self.tuning_performed_after_freeze:
                raise ValueError("freeze 後 tuning 的 run 不可進入 formal evidence")
            if self.seeds.evaluation_seed is None or self.seeds.seed_schedule_sha256 is None:
                raise ValueError("FORMAL_EVALUATION 必須保存 evaluation seed與 schedule hash")
            if (
                self.controller_family in {"LEARNING_BASED", "HYBRID"}
                and self.seeds.training_seed is None
            ):
                raise ValueError("learning/hybrid formal run 必須保存 training seed")
        return self


def _reject_json_constant(value: str) -> None:
    raise PaperDataIntegrityError(f"JSON non-finite constant is forbidden: {value}")


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key, value in pairs:
        if key in payload:
            raise PaperDataIntegrityError(f"duplicate JSON key is forbidden: {key}")
        payload[key] = value
    return payload


def load_json_object_strict(path: Path) -> dict[str, Any]:
    """Read one UTF-8 JSON object without duplicate keys or non-finite values."""

    try:
        if path.stat().st_size > MAX_JSON_BYTES:
            raise PaperDataIntegrityError(
                f"JSON file exceeds {MAX_JSON_BYTES} byte limit: {path.name}"
            )
        payload = json.loads(
            path.read_text(encoding="utf-8"),
            parse_constant=_reject_json_constant,
            object_pairs_hook=_reject_duplicate_json_keys,
        )
    except (OSError, UnicodeError, ValueError, RecursionError) as exc:
        raise PaperDataIntegrityError(f"invalid JSON file: {path.name}") from exc
    if not isinstance(payload, dict):
        raise PaperDataIntegrityError(f"JSON root must be an object: {path.name}")
    return payload


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def artifact_record(
    root: Path,
    path: Path,
    *,
    role: str,
    media_type: str,
) -> dict:
    root = root.resolve()
    resolved = path.resolve()
    if not resolved.is_relative_to(root) or not resolved.is_file():
        raise PaperDataIntegrityError("artifact must be an existing file inside bundle root")
    relative_path = resolved.relative_to(root).as_posix()
    return {
        "role": role,
        "path": relative_path,
        "media_type": media_type,
        "bytes": resolved.stat().st_size,
        "sha256": sha256_file(resolved),
    }


def validate_paper_run_bundle(manifest_path: Path) -> dict:
    manifest_path = manifest_path.resolve()
    if not manifest_path.is_file():
        raise FileNotFoundError(manifest_path)
    bundle_root = manifest_path.parent.resolve()
    payload = load_json_object_strict(manifest_path)
    manifest = PaperRunManifest.model_validate(payload)
    for artifact in manifest.artifacts:
        resolved = (bundle_root / artifact.path).resolve()
        if not resolved.is_relative_to(bundle_root):
            raise PaperDataIntegrityError(f"artifact path escapes bundle: {artifact.path}")
        if not resolved.is_file():
            raise PaperDataIntegrityError(f"artifact missing: {artifact.path}")
        if resolved.stat().st_size != artifact.bytes:
            raise PaperDataIntegrityError(f"artifact size mismatch: {artifact.path}")
        if sha256_file(resolved) != artifact.sha256:
            raise PaperDataIntegrityError(f"artifact SHA-256 mismatch: {artifact.path}")

    paper_ready = (
        manifest.run_class == "FORMAL_EVALUATION"
        and manifest.status in {"COMPLETED", "FAILED"}
    )
    validation_status = (
        "PAPER_DATA_READY" if paper_ready else f"{manifest.run_class}_BUNDLE_VALID_ONLY"
    )
    return {
        "schema_version": "PAPER_BUNDLE_VALIDATION_RECEIPT_V1",
        "run_id": manifest.run_id,
        "experiment_id": manifest.experiment_id,
        "validation_status": validation_status,
        "paper_data_ready": paper_ready,
        "artifact_count": len(manifest.artifacts),
        "artifact_bytes": sum(item.bytes for item in manifest.artifacts),
        "manifest_sha256": sha256_file(manifest_path),
        "claim_boundary": (
            "Artifact integrity and manifest completeness only; validation does not prove "
            "physical fidelity, controller superiority, statistical sufficiency, or paper "
            "acceptance."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate a PAPER_RUN_MANIFEST_V1 bundle")
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    receipt = validate_paper_run_bundle(args.manifest)
    print(json.dumps(receipt, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

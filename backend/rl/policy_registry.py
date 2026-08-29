"""Versioned RL policy registry with fail-closed artifact verification."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


RL_DIR = Path(__file__).resolve().parent
DEFAULT_REGISTRY_PATH = RL_DIR / "policy_registry.json"


class RegistryModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class GaitContract(RegistryModel):
    mode: Literal["walk", "run"]
    speed_mps: float = Field(gt=0.0)
    step_length_m: float = Field(gt=0.0)
    duty: float = Field(gt=0.0, lt=1.0)
    clearance_m: float = Field(ge=0.0)


class TrainingContract(RegistryModel):
    algorithm: str
    total_timesteps: int = Field(gt=0)
    parallel_envs: int = Field(gt=0)
    seed_rule: str
    controller_hz: float = Field(gt=0.0)
    physics_hz: float = Field(gt=0.0)


class PolicyRecord(RegistryModel):
    policy_id: str = Field(min_length=1, pattern=r"^[a-z0-9][a-z0-9_.-]*$")
    display_name: str = Field(min_length=1)
    artifact: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    bytes: int = Field(gt=0)
    gait_contract: GaitContract
    training_contract: TrainingContract
    created_at: str
    evidence_status: str = Field(min_length=1)
    notes: str = ""


class PolicyRegistry(RegistryModel):
    schema_version: Literal["RL_POLICY_REGISTRY_V1"]
    default_policy_id: str
    policies: list[PolicyRecord] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_ids_and_valid_default(self):
        ids = [record.policy_id for record in self.policies]
        if len(ids) != len(set(ids)):
            raise ValueError("policy_id 不可重複")
        if self.default_policy_id not in ids:
            raise ValueError("default_policy_id 不存在於 policies")
        return self


def load_registry(path: Path = DEFAULT_REGISTRY_PATH) -> PolicyRegistry:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return PolicyRegistry.model_validate(raw)


def _safe_artifact_path(record: PolicyRecord, registry_path: Path) -> Path:
    root = registry_path.resolve().parent
    path = (root / record.artifact).resolve()
    if not path.is_relative_to(root):
        raise ValueError(f"policy artifact path escapes registry directory: {record.policy_id}")
    return path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_policy(
    policy_id: str | None = None,
    *,
    registry_path: Path = DEFAULT_REGISTRY_PATH,
    verify_artifact: bool = True,
) -> tuple[PolicyRecord, Path]:
    registry = load_registry(registry_path)
    selected_id = policy_id or registry.default_policy_id
    record = next((item for item in registry.policies if item.policy_id == selected_id), None)
    if record is None:
        raise KeyError(f"unknown policy_id: {selected_id}")
    artifact = _safe_artifact_path(record, registry_path)
    if verify_artifact:
        if not artifact.is_file():
            raise FileNotFoundError(f"policy artifact missing: {record.policy_id}")
        if artifact.stat().st_size != record.bytes:
            raise ValueError(f"policy artifact size mismatch: {record.policy_id}")
        actual_hash = sha256_file(artifact)
        if actual_hash != record.sha256:
            raise ValueError(f"policy artifact SHA-256 mismatch: {record.policy_id}")
    return record, artifact


def public_policy_inventory() -> dict:
    registry = load_registry()
    return {
        "schema_version": registry.schema_version,
        "default_policy_id": registry.default_policy_id,
        "evidence_scope": "SOFTWARE_ARTIFACT_INVENTORY_ONLY",
        "policies": [
            {
                "policy_id": item.policy_id,
                "display_name": item.display_name,
                "sha256": f"sha256:{item.sha256}",
                "bytes": item.bytes,
                "gait_contract": item.gait_contract.model_dump(),
                "training_contract": item.training_contract.model_dump(),
                "created_at": item.created_at,
                "evidence_status": item.evidence_status,
            }
            for item in registry.policies
        ],
    }

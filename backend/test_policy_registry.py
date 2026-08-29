"""RL policy registry identity and fail-closed verification tests."""

import json

import pytest
from fastapi.testclient import TestClient

from main import app
from rl.policy_registry import DEFAULT_REGISTRY_PATH, load_registry, resolve_policy, sha256_file


def test_default_policy_registry_matches_retained_checkpoint():
    registry = load_registry()
    record, artifact = resolve_policy()

    assert registry.schema_version == "RL_POLICY_REGISTRY_V1"
    assert record.policy_id == registry.default_policy_id == "walk_0p7_legacy"
    assert artifact.name == "ppo_walk_final.zip"
    assert artifact.stat().st_size == record.bytes
    assert sha256_file(artifact) == record.sha256
    assert record.gait_contract.speed_mps == pytest.approx(0.7)
    assert record.training_contract.total_timesteps == 30_000_000
    assert record.evidence_status == "LEGACY_RECONSTRUCTED_LOCAL_LOG_NO_FROZEN_ENVIRONMENT"


def test_policy_inventory_endpoint_discloses_contract_and_evidence_scope():
    response = TestClient(app).get("/api/policies")

    assert response.status_code == 200
    body = response.json()
    assert body["evidence_scope"] == "SOFTWARE_ARTIFACT_INVENTORY_ONLY"
    assert body["default_policy_id"] == "walk_0p7_legacy"
    assert body["policies"][0]["sha256"].startswith("sha256:")
    assert body["policies"][0]["gait_contract"]["speed_mps"] == pytest.approx(0.7)


def test_policy_registry_rejects_hash_or_size_mismatch(tmp_path):
    raw = json.loads(DEFAULT_REGISTRY_PATH.read_text(encoding="utf-8"))
    artifact = tmp_path / "ppo_walk_final.zip"
    artifact.write_bytes(b"tampered")
    raw["policies"][0]["bytes"] = len(b"tampered")
    registry_path = tmp_path / "policy_registry.json"
    registry_path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        resolve_policy(registry_path=registry_path)


def test_policy_registry_rejects_path_escape(tmp_path):
    raw = json.loads(DEFAULT_REGISTRY_PATH.read_text(encoding="utf-8"))
    raw["policies"][0]["artifact"] = "../outside.zip"
    registry_path = tmp_path / "policy_registry.json"
    registry_path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(ValueError, match="escapes registry directory"):
        resolve_policy(registry_path=registry_path, verify_artifact=False)


def test_unknown_policy_id_is_rejected():
    with pytest.raises(KeyError, match="unknown policy_id"):
        resolve_policy("does_not_exist")

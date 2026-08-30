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
    assert record.observation_contract.dimension == 47
    assert record.runtime_adapter == "legacy_walk_v1"
    assert record.evidence_status == "LEGACY_RECONSTRUCTED_LOCAL_LOG_NO_FROZEN_ENVIRONMENT"


def test_curriculum_policy_registry_matches_promoted_candidate():
    record, artifact = resolve_policy("stand_start_walk_stop_0p7_curriculum_v2")

    assert artifact.name == "ppo_stand_start_walk_stop_0p7_curriculum_v2.zip"
    assert artifact.stat().st_size == 1_964_161
    assert sha256_file(artifact) == "d3e1fc41be570d19cabaa86a760f11e631f5a9970eb3844e481a983b20e3e8ad"
    assert record.observation_contract.dimension == 48
    assert record.observation_contract.command_conditioned is True
    assert record.runtime_adapter == "motion_task_command_envelope_v2"
    assert record.evidence_status == "LIVE_500HZ_TASK_EVALUATED_FAIL_LATERAL_SATURATION"


def test_phase_observable_policy_registry_matches_selected_holdout_candidate():
    record, artifact = resolve_policy("stand_start_walk_stop_0p7_phase_observable_v5")

    assert artifact.name == "ppo_stand_start_walk_stop_0p7_phase_observable_v5.zip"
    assert artifact.stat().st_size == 1_983_126
    assert sha256_file(artifact) == "c548867fbd17c736d54c1b1598d2abed1c7cb2dd28c7d310ea6e86ac3b36718c"
    assert record.observation_contract.dimension == 51
    assert record.observation_contract.command_conditioned is True
    assert record.runtime_adapter == "motion_task_phase_observable_v5"
    assert record.evidence_status == "LIVE_500HZ_TASK_EVALUATED_FAIL_SATURATION_DUTY"


def test_policy_inventory_endpoint_discloses_contract_and_evidence_scope():
    response = TestClient(app).get("/api/policies")

    assert response.status_code == 200
    body = response.json()
    assert body["evidence_scope"] == "SOFTWARE_ARTIFACT_INVENTORY_ONLY"
    assert body["default_policy_id"] == "walk_0p7_legacy"
    assert len(body["policies"]) == 3
    assert body["policies"][0]["sha256"].startswith("sha256:")
    assert body["policies"][0]["gait_contract"]["speed_mps"] == pytest.approx(0.7)
    assert body["policies"][1]["observation_contract"]["dimension"] == 48
    assert body["policies"][2]["observation_contract"]["dimension"] == 51


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

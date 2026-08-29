"""Dynamic Run Trace V1 recorder and bounded artifact store.

Raw samples are captured from MuJoCo physics steps. WebSocket frame data is
never used as an analysis source.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

import mujoco
import numpy as np


TRACE_SCHEMA_VERSION = "DYNAMIC_RUN_TRACE_V1"
RUN_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{7,79}$")
STATE_CODES = {"STAND": 0, "WALK": 1, "FALLEN": 2}
STATE_LABELS = {value: key for key, value in STATE_CODES.items()}
DEFAULT_TRACE_ROOT = Path(__file__).resolve().parent / "run_traces"


class TraceIntegrityError(RuntimeError):
    pass


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_run_id(controller: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dt%H%M%S")
    safe_controller = re.sub(r"[^a-z0-9_-]", "-", controller.lower())[:20]
    return f"run-{stamp}-{safe_controller}-{uuid.uuid4().hex[:8]}"


class RunTraceRecorder:
    """Preallocated physics-step recorder with a fixed duration cap."""

    def __init__(
        self,
        *,
        model: mujoco.MjModel,
        config: dict,
        gait: dict,
        obstacles: list[dict],
        controller: str,
        policy_id: str | None,
        policy_evidence_status: str | None,
        assist_enabled: bool,
        sim_t: float,
        physics_dt: float,
        max_duration_s: float,
        label: str = "",
        group_id: str | None = None,
        source_mode: str = "live",
        task_id: str | None = None,
        task_contract: dict | None = None,
        task_phase_events: list[dict] | None = None,
    ):
        self.run_id = new_run_id(controller)
        self.group_id = group_id
        self.label = label.strip()[:120]
        self.source_mode = source_mode
        self.task_id = task_id
        self.task_contract = task_contract
        self.task_phase_events = task_phase_events
        self.controller = controller
        self.policy_id = policy_id
        self.policy_evidence_status = policy_evidence_status
        self.config = config
        self.gait = gait
        self.obstacles = obstacles
        self.assist_enabled_at_start = bool(assist_enabled)
        self.sim_t_start = float(sim_t)
        self.physics_dt = float(physics_dt)
        self.max_duration_s = float(max_duration_s)
        self.started_at = _utc_now()
        self.stop_reason: str | None = None
        self.active = True
        self.count = 0
        self.max_samples = int(math.ceil(max_duration_s / physics_dt)) + 1
        self.group_names = list(config.get("actuators", {}).keys())
        self.joint_names = [
            mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_ACTUATOR, i) or f"actuator_{i}"
            for i in range(model.nu)
        ]

        # float32 keeps a 60 s three-controller capture bounded while preserving
        # substantially more precision than the UI's decimated/readout values.
        n = self.max_samples
        self.arrays: dict[str, np.ndarray] = {
            "time": np.empty(n, dtype=np.float64),
            "qpos": np.empty((n, model.nq), dtype=np.float32),
            "qvel": np.empty((n, model.nv), dtype=np.float32),
            "qacc": np.empty((n, model.nv), dtype=np.float32),
            "ctrl": np.empty((n, model.nu), dtype=np.float32),
            "tau": np.empty((n, model.nu), dtype=np.float32),
            "q_ref": np.empty((n, model.nu), dtype=np.float32),
            "tracking_error": np.empty((n, model.nu), dtype=np.float32),
            "com": np.empty((n, 3), dtype=np.float32),
            "com_vel": np.empty((n, 3), dtype=np.float32),
            "pitch_deg": np.empty(n, dtype=np.float32),
            "roll_deg": np.empty(n, dtype=np.float32),
            "grf_lr": np.empty((n, 2), dtype=np.float32),
            "cop_xy": np.full((n, 2), np.nan, dtype=np.float32),
            "contact_count": np.empty(n, dtype=np.int16),
            "saturation_pct": np.empty((n, len(self.group_names)), dtype=np.float32),
            "positive_power_w": np.empty(n, dtype=np.float32),
            "absolute_power_w": np.empty(n, dtype=np.float32),
            "state_code": np.empty(n, dtype=np.int8),
        }

    def record_step(self, *, data, controller, engine, gait_t: float) -> bool:
        """Capture one completed physics step. Returns True when cap is reached."""
        if not self.active:
            return False
        if self.count >= self.max_samples:
            return True
        i = self.count
        telemetry = controller.telemetry(data)
        try:
            q_ref = engine.qpos_at(gait_t, controller.model.nq)[7:]
        except Exception:
            q_ref = np.full(controller.model.nu, np.nan, dtype=float)
        q_actual = np.asarray(data.qpos[7:7 + controller.model.nu], dtype=float)
        tau = np.asarray(data.actuator_force, dtype=float)
        joint_vel = np.asarray(data.qvel[6:6 + controller.model.nu], dtype=float)
        power = tau * joint_vel

        self.arrays["time"][i] = float(data.time)
        self.arrays["qpos"][i] = data.qpos
        self.arrays["qvel"][i] = data.qvel
        self.arrays["qacc"][i] = data.qacc
        self.arrays["ctrl"][i] = data.ctrl
        self.arrays["tau"][i] = tau
        self.arrays["q_ref"][i] = q_ref
        self.arrays["tracking_error"][i] = q_actual - q_ref
        self.arrays["com"][i] = telemetry["com"]
        self.arrays["com_vel"][i] = telemetry["com_vel"]
        self.arrays["pitch_deg"][i] = telemetry["pitch_deg"]
        self.arrays["roll_deg"][i] = telemetry["roll_deg"]
        self.arrays["grf_lr"][i] = [telemetry["grf"]["l"], telemetry["grf"]["r"]]
        if telemetry["cop"] is not None:
            self.arrays["cop_xy"][i] = telemetry["cop"]
        self.arrays["contact_count"][i] = len(telemetry["contacts"])
        self.arrays["saturation_pct"][i] = [
            telemetry["saturation"].get(name, np.nan) for name in self.group_names
        ]
        self.arrays["positive_power_w"][i] = float(np.sum(np.maximum(power, 0.0)))
        self.arrays["absolute_power_w"][i] = float(np.sum(np.abs(power)))
        self.arrays["state_code"][i] = STATE_CODES.get(controller.state, -1)
        self.count += 1
        elapsed = float(data.time) - self.sim_t_start
        return self.count >= self.max_samples or elapsed + 0.5 * self.physics_dt >= self.max_duration_s

    def sliced_arrays(self) -> dict[str, np.ndarray]:
        return {name: values[:self.count].copy() for name, values in self.arrays.items()}


class RunTraceStore:
    def __init__(self, root: Path = DEFAULT_TRACE_ROOT):
        self.root = root.resolve()

    def _paths(self, run_id: str) -> tuple[Path, Path]:
        if not RUN_ID_PATTERN.fullmatch(run_id):
            raise TraceIntegrityError("invalid run_id")
        manifest = (self.root / f"{run_id}.manifest.json").resolve()
        artifact = (self.root / f"{run_id}.npz").resolve()
        if not manifest.is_relative_to(self.root) or not artifact.is_relative_to(self.root):
            raise TraceIntegrityError("trace path escapes store")
        return manifest, artifact

    def finalize(self, recorder: RunTraceRecorder, *, stop_reason: str, decisions: list[dict]) -> dict:
        if not recorder.active:
            raise TraceIntegrityError("recording already finalized")
        if recorder.count == 0:
            raise TraceIntegrityError("recording contains no physics samples")
        recorder.active = False
        recorder.stop_reason = stop_reason
        arrays = recorder.sliced_arrays()
        self.root.mkdir(parents=True, exist_ok=True)
        manifest_path, artifact_path = self._paths(recorder.run_id)
        if manifest_path.exists() or artifact_path.exists():
            raise TraceIntegrityError("run_id collision; artifact not overwritten")

        artifact_tmp = self.root / f".{recorder.run_id}.npz.tmp"
        manifest_tmp = self.root / f".{recorder.run_id}.manifest.json.tmp"
        try:
            with artifact_tmp.open("wb") as stream:
                np.savez_compressed(stream, **arrays)
            artifact_hash = _sha256_file(artifact_tmp)
            summary = self._summary(recorder, arrays)
            task = None
            if recorder.task_id is not None and recorder.task_contract is not None:
                from motion_tasks import evaluate_motion_task
                task = {
                    "task_id": recorder.task_id,
                    "contract": recorder.task_contract,
                    "phase_events": list(recorder.task_phase_events or []),
                    "evaluation": evaluate_motion_task(
                        arrays,
                        recorder.task_contract,
                        physics_dt=recorder.physics_dt,
                        stop_reason=stop_reason,
                        assist_enabled_at_start=recorder.assist_enabled_at_start,
                    ),
                }
            manifest = {
                "schema_version": TRACE_SCHEMA_VERSION,
                "run_id": recorder.run_id,
                "group_id": recorder.group_id,
                "label": recorder.label,
                "source_mode": recorder.source_mode,
                "evidence_scope": "SOFTWARE_ONLY_MUJOCO_REALIZED_SIMULATION",
                "controller": recorder.controller,
                "policy_id": recorder.policy_id,
                "policy_evidence_status": recorder.policy_evidence_status,
                "assist_enabled_at_start": recorder.assist_enabled_at_start,
                "robot": recorder.config,
                "gait": recorder.gait,
                "obstacles": recorder.obstacles,
                "physics_dt_s": recorder.physics_dt,
                "sample_rate_hz": 1.0 / recorder.physics_dt,
                "max_duration_s": recorder.max_duration_s,
                "sample_count": recorder.count,
                "started_at": recorder.started_at,
                "completed_at": _utc_now(),
                "stop_reason": stop_reason,
                "group_names": recorder.group_names,
                "joint_names": recorder.joint_names,
                "reference_definition": "SESSION_GAIT_ENGINE_COMMON_REFERENCE_NOT_CONTROLLER_INTERNAL_TARGET",
                "state_codes": STATE_LABELS,
                "artifact": {
                    "filename": artifact_path.name,
                    "bytes": artifact_tmp.stat().st_size,
                    "sha256": f"sha256:{artifact_hash}",
                },
                "arrays": {
                    name: {"shape": list(values.shape), "dtype": str(values.dtype)}
                    for name, values in arrays.items()
                },
                "summary": summary,
                "task": task,
                "decisions": decisions[-100:],
            }
            manifest_tmp.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False),
                encoding="utf-8",
            )
            artifact_tmp.replace(artifact_path)
            manifest_tmp.replace(manifest_path)
        finally:
            if artifact_tmp.exists():
                artifact_tmp.unlink()
            if manifest_tmp.exists():
                manifest_tmp.unlink()
        return self._receipt(manifest)

    def _summary(self, recorder: RunTraceRecorder, arrays: dict[str, np.ndarray]) -> dict:
        n = recorder.count
        duration = max(float(arrays["time"][-1] - arrays["time"][0] + recorder.physics_dt), recorder.physics_dt)
        distance = float(arrays["qpos"][-1, 0] - arrays["qpos"][0, 0])
        fallen_idx = np.flatnonzero(arrays["state_code"] == STATE_CODES["FALLEN"])
        tracking_rmse = np.sqrt(np.nanmean(arrays["tracking_error"] ** 2, axis=0))
        return {
            "duration_s": round(duration, 6),
            "distance_m": round(distance, 6),
            "average_forward_speed_mps": round(distance / duration, 6),
            "final_state": STATE_LABELS.get(int(arrays["state_code"][-1]), "UNKNOWN"),
            "fell": bool(fallen_idx.size),
            "first_fall_time_s": (
                round(float(arrays["time"][fallen_idx[0]] - arrays["time"][0]), 6)
                if fallen_idx.size else None
            ),
            "max_abs_pitch_deg": round(float(np.max(np.abs(arrays["pitch_deg"]))), 6),
            "max_abs_roll_deg": round(float(np.max(np.abs(arrays["roll_deg"]))), 6),
            "positive_mechanical_work_j": round(float(np.sum(arrays["positive_power_w"]) * recorder.physics_dt), 6),
            "absolute_mechanical_work_j": round(float(np.sum(arrays["absolute_power_w"]) * recorder.physics_dt), 6),
            "tracking_rmse_rad": [round(float(value), 6) for value in tracking_rmse],
            "max_saturation_pct": {
                name: round(float(np.nanmax(arrays["saturation_pct"][:, i])), 3)
                for i, name in enumerate(recorder.group_names)
            },
            "max_grf_n": {
                "left": round(float(np.max(arrays["grf_lr"][:, 0])), 3),
                "right": round(float(np.max(arrays["grf_lr"][:, 1])), 3),
            },
            "cop_coverage_pct": round(float(np.mean(np.all(np.isfinite(arrays["cop_xy"]), axis=1)) * 100.0), 3),
            "max_contact_count": int(np.max(arrays["contact_count"])),
        }

    @staticmethod
    def _receipt(manifest: dict) -> dict:
        return {
            "run_id": manifest["run_id"],
            "group_id": manifest["group_id"],
            "controller": manifest["controller"],
            "sample_count": manifest["sample_count"],
            "summary": manifest["summary"],
            "artifact_sha256": manifest["artifact"]["sha256"],
            "evidence_scope": manifest["evidence_scope"],
            "task": manifest.get("task"),
        }

    def list_traces(self, limit: int = 100) -> list[dict]:
        if not self.root.exists():
            return []
        records = []
        for path in self.root.glob("*.manifest.json"):
            try:
                manifest = json.loads(path.read_text(encoding="utf-8"))
                if manifest.get("schema_version") != TRACE_SCHEMA_VERSION:
                    continue
                records.append({
                    **self._receipt(manifest),
                    "label": manifest.get("label", ""),
                    "completed_at": manifest["completed_at"],
                    "source_mode": manifest["source_mode"],
                    "policy_id": manifest.get("policy_id"),
                })
            except (OSError, KeyError, json.JSONDecodeError):
                continue
        records.sort(key=lambda item: item["completed_at"], reverse=True)
        return records[:limit]

    def load_trace(self, run_id: str, max_points: int = 2000) -> dict:
        if not 10 <= max_points <= 5000:
            raise TraceIntegrityError("max_points must be between 10 and 5000")
        manifest_path, artifact_path = self._paths(run_id)
        if not manifest_path.is_file() or not artifact_path.is_file():
            raise FileNotFoundError(run_id)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("schema_version") != TRACE_SCHEMA_VERSION or manifest.get("run_id") != run_id:
            raise TraceIntegrityError("manifest identity mismatch")
        if artifact_path.stat().st_size != manifest["artifact"]["bytes"]:
            raise TraceIntegrityError("trace artifact size mismatch")
        actual_hash = f"sha256:{_sha256_file(artifact_path)}"
        if actual_hash != manifest["artifact"]["sha256"]:
            raise TraceIntegrityError("trace artifact SHA-256 mismatch")

        with np.load(artifact_path, allow_pickle=False) as loaded:
            arrays = {name: loaded[name] for name in loaded.files}
        expected_count = int(manifest["sample_count"])
        for name, spec in manifest["arrays"].items():
            if name not in arrays:
                raise TraceIntegrityError(f"trace array missing: {name}")
            if list(arrays[name].shape) != spec["shape"] or str(arrays[name].dtype) != spec["dtype"]:
                raise TraceIntegrityError(f"trace array shape/dtype mismatch: {name}")
            if arrays[name].shape[0] != expected_count:
                raise TraceIntegrityError(f"trace sample count mismatch: {name}")

        if expected_count <= max_points:
            index = np.arange(expected_count)
        else:
            index = np.unique(np.linspace(0, expected_count - 1, max_points, dtype=int))
        tracking_rmse = np.sqrt(np.nanmean(arrays["tracking_error"][index] ** 2, axis=1))
        max_saturation = np.nanmax(arrays["saturation_pct"][index], axis=1)
        cop_values = arrays["cop_xy"][index]
        cop_json = [
            [round(float(value), 6) if np.isfinite(value) else None for value in row]
            for row in cop_values
        ]
        series = {
            "time": arrays["time"][index].round(6).tolist(),
            "base_x": arrays["qpos"][index, 0].round(6).tolist(),
            "com": arrays["com"][index].round(6).tolist(),
            "com_vel": arrays["com_vel"][index].round(6).tolist(),
            "pitch_deg": arrays["pitch_deg"][index].round(4).tolist(),
            "roll_deg": arrays["roll_deg"][index].round(4).tolist(),
            "grf_lr": arrays["grf_lr"][index].round(3).tolist(),
            "cop_xy": cop_json,
            "positive_power_w": arrays["positive_power_w"][index].round(3).tolist(),
            "absolute_power_w": arrays["absolute_power_w"][index].round(3).tolist(),
            "tracking_rmse_rad": tracking_rmse.round(6).tolist(),
            "max_saturation_pct": max_saturation.round(3).tolist(),
            "state_code": arrays["state_code"][index].tolist(),
            "joint_q": arrays["qpos"][index, 7:].round(6).tolist(),
            "joint_q_ref": arrays["q_ref"][index].round(6).tolist(),
            "joint_tau": arrays["tau"][index].round(4).tolist(),
        }
        return {"manifest": manifest, "series": series, "returned_points": len(index)}


TRACE_STORE = RunTraceStore()

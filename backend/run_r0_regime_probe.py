"""Execute R0-REGIME-HORIZON-PROBE-V1 and retain its result.

Step 3 of the frozen execution order in docs/R0_REGIME_PROBE_SPEC.md section 8.
The environment lock is verified here, where site packages are available; the
analysis itself lives in ``r0_regime_probe_contract`` and is stdlib-only so step
4 can recompute it under ``python -I -S``.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import environment_lock as el
import r0_regime_probe_contract as r0

BACKEND = Path(__file__).resolve().parent
REPO = BACKEND.parent
INDEX_PATH = BACKEND / "r0_probe_evidence/2026-09-11/horizon_trace_index.json"
PROTOCOL_PATH = BACKEND / "rl/r0_regime_probe_protocol.json"
OUT_PATH = BACKEND / "r0_probe_evidence/2026-09-11/probe_result.json"
SEEDVAR_LOCK_PATH = BACKEND / "environment_locks/lock-2026-09-08-seedvar-execution.json"


def _git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, text=True).stdout.strip()


def main() -> int:
    source_sha_pre = _git("rev-parse", "HEAD")
    dirty_pre = bool(_git("status", "--porcelain"))

    # The protocol requires a measured, complete lock before the analysis runs.
    record = el.capture_environment_lock()
    validation = el.validate_lock_record(record)
    lock_class = validation["lock_class"]
    completeness = validation["lock_completeness"]
    if lock_class != el.MEASURED_LOCK_CLASS:
        raise SystemExit(f"R0_LOCK_CLASS_NOT_MEASURED: {lock_class}")
    if completeness != el.FULL_LOCK:
        raise SystemExit(f"R0_LOCK_NOT_FULL: {completeness}")

    # Informational provenance: whether this environment is byte-identical to the
    # one that produced the parent evidence. The analysis is exact integer
    # arithmetic, so a difference would not change the result, but it is recorded
    # rather than assumed.
    seedvar_lock = el.load_lock_record(SEEDVAR_LOCK_PATH)
    seedvar_validation = el.validate_lock_record(seedvar_lock)
    lock_matches_parent = seedvar_validation["locked_sha256"] == validation["locked_sha256"]

    result = r0.run_probe(INDEX_PATH, PROTOCOL_PATH)

    source_sha_post = _git("rev-parse", "HEAD")
    dirty_post = bool(_git("status", "--porcelain"))
    if source_sha_pre != source_sha_post:
        raise SystemExit("R0_SOURCE_MOVED_DURING_RUN")

    result["execution"] = {
        "executed_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_git_sha_pre": source_sha_pre,
        "source_git_sha_post": source_sha_post,
        "source_dirty_pre": dirty_pre,
        "source_dirty_post": dirty_post,
        "environment_lock_class": lock_class,
        "environment_lock_completeness": completeness,
        "environment_lock_threading_determinism": record["threading_determinism"],
        "environment_locked_sha256": validation["locked_sha256"],
        "parent_evidence_locked_sha256": seedvar_validation["locked_sha256"],
        "locked_sha256_matches_parent_evidence": lock_matches_parent,
        "analysis_uses_third_party_packages": False,
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(result, indent=1, sort_keys=True) + "\n"
    OUT_PATH.write_text(payload, encoding="utf-8")
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()

    for contrast in result["contrasts"]:
        print(
            f"{contrast['contrast_id']} ({contrast['candidate_arm_id']} vs {contrast['reference_arm_id']}): "
            f"{contrast['label']}"
        )
        print(
            f"   P0a horizons={contrast['p0a_horizon_count']} "
            f"range={contrast['p0a_horizon_min']}..{contrast['p0a_horizon_max']} | "
            f"adequate={contrast['adequate_horizon_count']} | selected={contrast['selected_horizon_control_steps']}"
        )
        print(
            f"   shortest episode: reference={contrast['reference_shortest_episode_control_steps']} "
            f"candidate={contrast['candidate_shortest_episode_control_steps']} control steps"
        )
        print(
            f"   reference mean duty at P0a min/max: "
            f"{contrast['reference_mean_duty_pct_at_p0a_min']} / {contrast['reference_mean_duty_pct_at_p0a_max']} pp"
        )
    print(f"lock: {lock_class} / {completeness} / matches parent evidence: {lock_matches_parent}")
    print(f"result written: {OUT_PATH.relative_to(REPO)}  sha256:{digest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

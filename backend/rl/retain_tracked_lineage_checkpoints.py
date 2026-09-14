"""Retain one tracked-lineage replicate's checkpoints into version control.

TRACKED-LINEAGE-TRAINING-V1 specification section 7.1. Stable Baselines3 writes
its checkpoints into the run directory under backend/rl/artifacts/, which is
gitignored, so a run that is never retained leaves nothing behind -- and the
container is ephemeral. This copies the four checkpoints of one replicate into
backend/tracked_lineage_evidence/<date>/checkpoints/ under the frozen naming
rule and rewrites the index.

It is a script rather than a sequence of typed commands so that the retention is
reproducible and reviewable, and so that the naming rule exists in exactly one
place.

Retention is per replicate on purpose: train, retain, evaluate, commit, push,
then the next one. Running all five and retaining at the end would lose
everything if the container went away in between.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from rl.train_ppo import (  # noqa: E402
    TRACKED_LINEAGE_PROFILE_PREFIX,
    load_tracked_lineage_protocol,
    tracked_lineage_replicate_index,
)

EVIDENCE_ROOT = BACKEND / "tracked_lineage_evidence"
INDEX_FILENAME = "checkpoint_index.json"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return f"sha256:{digest.hexdigest()}"


def retain(replicate_index: int, date: str, *, dry_run: bool = False) -> dict:
    protocol = load_tracked_lineage_protocol()
    lineage = protocol["checkpoint_lineage"]
    expected_steps = [int(value) for value in lineage["expected_realized_timesteps"]]

    profile_id = f"{TRACKED_LINEAGE_PROFILE_PREFIX}{replicate_index}"
    if tracked_lineage_replicate_index(profile_id) != replicate_index:
        raise SystemExit(f"profile id does not carry replicate {replicate_index}")

    run_dir = BACKEND / "rl" / "artifacts" / f"{profile_id}-run"
    source_dir = run_dir / "checkpoints"
    if not source_dir.is_dir():
        raise SystemExit(f"no checkpoint directory at {source_dir}")

    target_dir = EVIDENCE_ROOT / date / "checkpoints"
    index_path = EVIDENCE_ROOT / date / INDEX_FILENAME

    entries = []
    for step in expected_steps:
        # SB3's CheckpointCallback names files {name_prefix}_{num_timesteps}_steps.zip.
        source = source_dir / f"{profile_id}_{step}_steps.zip"
        if not source.is_file():
            available = sorted(item.name for item in source_dir.glob("*.zip"))
            raise SystemExit(
                f"expected checkpoint at {step} steps is missing: {source.name}\n"
                f"  available: {available}"
            )
        target_name = f"r{replicate_index}-{step:07d}.zip"
        target = target_dir / target_name
        if not dry_run:
            target_dir.mkdir(parents=True, exist_ok=True)
            if target.exists():
                # Retained evidence is never silently overwritten.
                raise SystemExit(f"refusing to overwrite retained checkpoint {target}")
            shutil.copyfile(source, target)
        entries.append(
            {
                "bytes": source.stat().st_size,
                "realized_timesteps": step,
                "relative_path": f"backend/tracked_lineage_evidence/{date}/checkpoints/{target_name}",
                "replicate_index": replicate_index,
                "sha256": sha256_file(target if not dry_run else source),
            }
        )

    manifest_path = run_dir / "run_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    realized = int(manifest["actual_total_timesteps"])
    if realized != int(protocol["training_design"]["realized_timesteps_per_replicate"]):
        raise SystemExit(f"realized timesteps {realized} is not the protocol's value")

    # Amendment 02: the driver's policy.zip is an UNRETAINED BYPRODUCT. It is
    # written after learn() returns, at the rollout boundary, so it sits 15_264
    # steps past the last checkpoint and is not a copy of any retained file. The
    # reference policy is TL-CK-04's last retained checkpoint. The byproduct's
    # digest is still recorded, so the fact that it exists and was not used is on
    # the record and a later substitution would be detectable.
    byproduct = run_dir / manifest["artifact"]["relative_path"]
    byproduct_digest = sha256_file(byproduct)

    index = {"checkpoints": [], "replicates": {}}
    if index_path.is_file():
        index = json.loads(index_path.read_text(encoding="utf-8"))
    index["checkpoints"] = [
        item for item in index.get("checkpoints", [])
        if int(item["replicate_index"]) != replicate_index
    ] + entries
    index["checkpoints"].sort(key=lambda item: (item["replicate_index"], item["realized_timesteps"]))
    index.setdefault("replicates", {})[str(replicate_index)] = {
        "profile_id": profile_id,
        "run_id": manifest["run_id"],
        "seed_base": int(manifest["resolved"]["seed_base"]),
        "realized_timesteps": realized,
        "reference_checkpoint_sha256": entries[-1]["sha256"],
        "reference_checkpoint_realized_timesteps": entries[-1]["realized_timesteps"],
        "unretained_byproduct_sha256": byproduct_digest,
        "unretained_byproduct_note": (
            "backend/rl/artifacts/<run_id>/policy.zip, saved at realized_timesteps rather "
            "than at a checkpoint boundary. Not version-controlled, not evaluated, not this "
            "line's output. See specification amendment 02."
        ),
        "run_manifest_sha256": sha256_file(manifest_path),
        "environment_lock_sha256_note": "see run_lock_binding.json in the run directory",
    }
    index["contract_id"] = protocol["protocol_id"]
    index["protocol_sha256"] = sha256_file(
        BACKEND / "rl" / "tracked_lineage_training_protocol.json"
    )

    if not dry_run:
        index_path.write_text(
            json.dumps(index, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return index["replicates"][str(replicate_index)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--replicate-index", type=int, required=True)
    parser.add_argument("--date", required=True, help="execution date, e.g. 2026-09-14")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    summary = retain(args.replicate_index, args.date, dry_run=args.dry_run)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Retain one tracked-lineage replicate's checkpoints into version control.

TRACKED-LINEAGE-TRAINING-V1 specification section 7.1, and V2 section 7 for the
continuation line. Stable Baselines3 writes its checkpoints into the run
directory under backend/rl/artifacts/, which is gitignored, so a run that is
never retained leaves nothing behind -- and the container is ephemeral. This
copies the four checkpoints of one replicate into
backend/tracked_lineage_evidence/<date>/checkpoints/ under the frozen naming
rule and rewrites the index.

It is a script rather than a sequence of typed commands so that the retention is
reproducible and reviewable, and so that the naming rule exists in exactly one
place. That is also why V2 is a --line switch here rather than a second copy of
the file: two copies of a naming rule are two things that can drift apart.

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

import toolkit_path  # noqa: E402,F401  puts backend/toolkit on sys.path
import run_manifest_lock  # noqa: E402
from rl.train_ppo import (  # noqa: E402
    TRACKED_LINEAGE_PROFILE_PREFIX,
    TRACKED_LINEAGE_V2_PROFILE_PREFIX,
    load_tracked_lineage_protocol,
    load_tracked_lineage_v2_protocol,
    tracked_lineage_replicate_index,
    tracked_lineage_v2_replicate_index,
)

EVIDENCE_ROOT = BACKEND / "tracked_lineage_evidence"
INDEX_FILENAME = "checkpoint_index.json"


class Line:
    """What differs between the two tracked lineages, named once.

    Both lines executed on 2026-09-14, so they share an evidence date directory.
    Their checkpoint filenames cannot collide -- V1 stops at 1999968 and V2
    starts at 2499960 -- but their indexes and evaluation directories would, so
    V2 writes its own. A V2 retention never rewrites a V1 record.
    """

    def __init__(
        self,
        line_id: str,
        profile_prefix: str,
        protocol_loader,
        replicate_index_of,
        protocol_filename: str,
        realized_field: str,
        index_filename: str,
        evaluations_dirname: str,
        training_runs_dirname: str,
        training_run_index_filename: str,
    ) -> None:
        self.line_id = line_id
        self.profile_prefix = profile_prefix
        self.protocol_loader = protocol_loader
        self.replicate_index_of = replicate_index_of
        self.protocol_filename = protocol_filename
        self.realized_field = realized_field
        self.index_filename = index_filename
        self.evaluations_dirname = evaluations_dirname
        self.training_runs_dirname = training_runs_dirname
        self.training_run_index_filename = training_run_index_filename


LINES = {
    "v1": Line(
        line_id="v1",
        profile_prefix=TRACKED_LINEAGE_PROFILE_PREFIX,
        protocol_loader=load_tracked_lineage_protocol,
        replicate_index_of=tracked_lineage_replicate_index,
        protocol_filename="tracked_lineage_training_protocol.json",
        realized_field="realized_timesteps_per_replicate",
        index_filename=INDEX_FILENAME,
        evaluations_dirname="evaluations",
        training_runs_dirname="training_runs",
        training_run_index_filename="training_run_index.json",
    ),
    "v2": Line(
        line_id="v2",
        profile_prefix=TRACKED_LINEAGE_V2_PROFILE_PREFIX,
        protocol_loader=load_tracked_lineage_v2_protocol,
        replicate_index_of=tracked_lineage_v2_replicate_index,
        protocol_filename="tracked_lineage_training_v2_protocol.json",
        realized_field="total_realized_timesteps",
        index_filename="checkpoint_index_v2.json",
        evaluations_dirname="evaluations_v2",
        training_runs_dirname="training_runs_v2",
        training_run_index_filename="training_run_index_v2.json",
    ),
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return f"sha256:{digest.hexdigest()}"


def derive_run_lock_label(directory: Path, manifest_filename: str) -> str:
    """Re-derive TL-07 / TL2-07 from the retained bytes instead of trusting a string.

    The gate prints RUN_LOCK_BOUND to the console; the sidecar it writes carries
    no label field at all. Reading binding["label"] therefore always fell back to
    a placeholder, and V1's retained index records "see gate output" for all five
    evaluations -- a criterion whose evidence existed only in a terminal.

    The derivation itself lives in run_manifest_lock, beside evaluate_run, which
    is where lock semantics belong. It was briefly duplicated here, and the
    duplicate immediately diverged: the contract runner kept reading the absent
    label field and failed closed on all ten runs. One implementation, two
    callers.
    """
    return run_manifest_lock.evaluate_relocated_run(directory, manifest_filename)["label"]


def retain(replicate_index: int, date: str, *, line: str = "v1", dry_run: bool = False) -> dict:
    spec = LINES[line]
    protocol = spec.protocol_loader()
    lineage = protocol["checkpoint_lineage"]
    expected_steps = [int(value) for value in lineage["expected_realized_timesteps"]]

    profile_id = f"{spec.profile_prefix}{replicate_index}"
    if spec.replicate_index_of(profile_id) != replicate_index:
        raise SystemExit(f"profile id does not carry replicate {replicate_index}")

    run_dir = BACKEND / "rl" / "artifacts" / f"{profile_id}-run"
    source_dir = run_dir / "checkpoints"
    if not source_dir.is_dir():
        raise SystemExit(f"no checkpoint directory at {source_dir}")

    target_dir = EVIDENCE_ROOT / date / "checkpoints"
    index_path = EVIDENCE_ROOT / date / spec.index_filename

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
    if realized != int(protocol["training_design"][spec.realized_field]):
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
    record = {
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
    if manifest.get("resume"):
        # V2 only: the run did not start from scratch, so the record carries the
        # source it continued and the digest that was verified at resume time.
        record["resume_source"] = dict(manifest["resume"])
    index.setdefault("replicates", {})[str(replicate_index)] = record
    index["contract_id"] = protocol["protocol_id"]
    index["protocol_sha256"] = sha256_file(BACKEND / "rl" / spec.protocol_filename)
    if spec.line_id == "v2":
        index["shares_date_directory_with"] = INDEX_FILENAME
        index["shares_date_directory_note"] = (
            "V1 and V2 both executed on this date. Checkpoint filenames cannot collide "
            "(V1 ends at 1999968, V2 starts at 2499960) so both lines' checkpoints sit in "
            "one checkpoints/ directory, but each line keeps its own index and its own "
            "evaluations directory and neither rewrites the other's records."
        )

    if not dry_run:
        index_path.write_text(
            json.dumps(index, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return index["replicates"][str(replicate_index)]


def retain_evaluation(
    replicate_index: int, date: str, *, line: str = "v1", dry_run: bool = False
) -> dict:
    """Retain one replicate's evaluation output, lock record and binding.

    The driver writes these into backend/rl/artifacts/, which is gitignored, so
    an evaluation that is never retained disappears with the container exactly
    like a checkpoint would. The lock record and the binding travel with the
    output because TL-CK-05 is judged on them.
    """
    spec = LINES[line]
    profile_id = f"{spec.profile_prefix}{replicate_index}"
    eval_dir = BACKEND / "rl" / "artifacts" / f"{profile_id}-eval"
    target_dir = EVIDENCE_ROOT / date / spec.evaluations_dirname / f"r{replicate_index}"
    index_path = EVIDENCE_ROOT / date / spec.index_filename

    names = ["evaluation_dev22000_22029.json", "environment_lock.json", "run_lock_binding.json"]
    retained = {}
    for name in names:
        source = eval_dir / name
        if not source.is_file():
            raise SystemExit(f"missing evaluation artefact {source}")
        target = target_dir / name
        if not dry_run:
            target_dir.mkdir(parents=True, exist_ok=True)
            if target.exists():
                raise SystemExit(f"refusing to overwrite retained evidence {target}")
            shutil.copyfile(source, target)
        retained[name] = sha256_file(source)

    payload = json.loads((eval_dir / names[0]).read_text(encoding="utf-8"))
    episodes = payload["episode_results"]
    full = sum(
        1 for item in episodes
        if float(item["duration_s"]) == 9.0 and item["outcome_state"] == "OBSERVED"
    )
    summary = {
        "evaluation_seeds": [payload["evaluation_seeds"][0], payload["evaluation_seeds"][-1]],
        "episodes": len(episodes),
        "full_exposure": full,
        "full_exposure_proportion": f"{full}/{len(episodes)}",
        "evaluated_policy_sha256": _evaluated_policy_digest(payload),
        "run_lock_label": derive_run_lock_label(
            target_dir if not dry_run else eval_dir, names[0]
        ),
        "retained_sha256": retained,
        "relative_dir": (
            f"backend/tracked_lineage_evidence/{date}/{spec.evaluations_dirname}/r{replicate_index}"
        ),
    }

    index = json.loads(index_path.read_text(encoding="utf-8")) if index_path.is_file() else {}
    index.setdefault("evaluations", {})[str(replicate_index)] = summary
    if not dry_run:
        index_path.write_text(
            json.dumps(index, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return summary


def retain_training_run(
    replicate_index: int, date: str, *, line: str = "v1", dry_run: bool = False
) -> dict:
    """Retain one replicate's TRAINING run manifest, lock record and binding.

    V1 retained its evaluations' manifests but not its trainings'. That left
    every claim judged on a training manifest -- V1's TL-03 and TL-05, V2's
    TL2-03, TL2-04, TL2-05 and TL2-07 -- resting on files in gitignored
    backend/rl/artifacts/ that die with the container, exactly the failure this
    project has now hit twice. Only the manifest's digest reached the index, and
    a digest of a file nobody has is not evidence.

    For V2 this is required: TL2-03 is THE new criterion and it is judged on the
    resume block of a training manifest. For V1 it is an additive rescue of
    records that still exist in this container; it rewrites nothing, and writes
    to its own index so V1's frozen checkpoint_index.json is left untouched.
    """
    spec = LINES[line]
    profile_id = f"{spec.profile_prefix}{replicate_index}"
    run_dir = BACKEND / "rl" / "artifacts" / f"{profile_id}-run"
    target_dir = EVIDENCE_ROOT / date / spec.training_runs_dirname / f"r{replicate_index}"
    index_path = EVIDENCE_ROOT / date / spec.training_run_index_filename

    names = ["run_manifest.json", "environment_lock.json", "run_lock_binding.json"]
    retained = {}
    for name in names:
        source = run_dir / name
        if not source.is_file():
            raise SystemExit(f"missing training run artefact {source}")
        target = target_dir / name
        if not dry_run:
            target_dir.mkdir(parents=True, exist_ok=True)
            if target.exists():
                raise SystemExit(f"refusing to overwrite retained evidence {target}")
            shutil.copyfile(source, target)
        retained[name] = sha256_file(source)

    manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
    summary = {
        "profile_id": profile_id,
        "run_id": manifest["run_id"],
        "seed_base": int(manifest["resolved"]["seed_base"]),
        "realized_timesteps": int(manifest["actual_total_timesteps"]),
        "resume": manifest.get("resume"),
        "warm_start": manifest.get("warm_start"),
        "run_lock_label": derive_run_lock_label(
            target_dir if not dry_run else run_dir, "run_manifest.json"
        ),
        "retained_sha256": retained,
        "relative_dir": (
            f"backend/tracked_lineage_evidence/{date}/"
            f"{spec.training_runs_dirname}/r{replicate_index}"
        ),
    }

    index = json.loads(index_path.read_text(encoding="utf-8")) if index_path.is_file() else {}
    index["contract_id"] = (
        "TRACKED-LINEAGE-TRAINING-V1" if spec.line_id == "v1" else "TRACKED-LINEAGE-TRAINING-V2"
    )
    index["why_this_index_exists"] = (
        "The training run manifests, lock records and lock bindings live in gitignored "
        "backend/rl/artifacts/ and die with the container. Every criterion judged on a "
        "training manifest needs them, not just their digests. Kept in its own file so no "
        "already-retained index is rewritten."
    )
    index.setdefault("training_runs", {})[str(replicate_index)] = summary
    if not dry_run:
        index_path.write_text(
            json.dumps(index, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return summary


def _evaluated_policy_digest(payload: dict) -> str:
    """The digest of the policy the evaluation actually loaded (TL-CK-06).

    Taken from the evaluation output's own model block rather than recomputed
    from a path, so the claim survives in the retained evidence even when the
    gitignored run directory is gone.
    """
    model = payload.get("model") or {}
    digest = model.get("sha256")
    if not digest:
        raise SystemExit("evaluation output carries no model digest; TL-CK-06 unverifiable")
    return digest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--replicate-index", type=int, required=True)
    parser.add_argument("--date", required=True, help="execution date, e.g. 2026-09-14")
    parser.add_argument("--line", choices=sorted(LINES), default="v1",
                        help="which tracked lineage: v1 (scratch) or v2 (continuation)")
    parser.add_argument("--evaluation", action="store_true",
                        help="retain the evaluation output instead of the checkpoints")
    parser.add_argument("--training-run", action="store_true",
                        help="retain the training run manifest, lock record and binding")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.evaluation and args.training_run:
        raise SystemExit("choose one of --evaluation and --training-run")
    if args.evaluation:
        summary = retain_evaluation(
            args.replicate_index, args.date, line=args.line, dry_run=args.dry_run
        )
    elif args.training_run:
        summary = retain_training_run(
            args.replicate_index, args.date, line=args.line, dry_run=args.dry_run
        )
    else:
        summary = retain(args.replicate_index, args.date, line=args.line, dry_run=args.dry_run)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Run the TRACKED-LINEAGE-TRAINING-V2 contract over the retained evidence.

V1 checked its acceptance criteria by hand and wrote the answers into a receipt.
That is not re-derivable: a reader has to trust the receipt's author. This runs
TL2-01 .. TL2-09 as code, over files that are all in version control, and emits
a receipt JSON that anyone can regenerate and diff.

Reads ONLY retained evidence -- never backend/rl/artifacts/, which is gitignored
and dies with the container. If something the contract needs was not retained,
this fails rather than reaching into the run directory, because a check that
silently depends on an unretained file is a check that stops working the moment
it matters.

Stdlib only, so the verdict can be re-derived under python -I -S.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import toolkit_path  # noqa: E402,F401  puts backend/toolkit on sys.path
import run_manifest_lock  # noqa: E402
import tracked_lineage_v2_contract as tl2  # noqa: E402

EVIDENCE_ROOT = BACKEND / "tracked_lineage_evidence"
REPLICATES = range(5)


def _read(path: Path) -> dict:
    if not path.is_file():
        raise SystemExit(f"required retained evidence is missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def run(date: str) -> dict:
    root = EVIDENCE_ROOT / date
    protocol = tl2.load_protocol()

    checkpoint_index = _read(root / "checkpoint_index_v2.json")
    training_run_index = _read(root / "training_run_index_v2.json")
    curve_index = _read(root / "training_curve_index_v2.json")

    run_manifests = []
    binding_labels = {}
    for index in REPLICATES:
        directory = root / "training_runs_v2" / f"r{index}"
        manifest = _read(directory / "run_manifest.json")
        run_manifests.append(manifest)
        # Re-derived from the retained bytes, not read out of the index: an index
        # that says RUN_LOCK_BOUND is a claim, and this is the check of it.
        binding_labels[manifest["run_id"]] = run_manifest_lock.evaluate_relocated_run(
            directory, "run_manifest.json"
        )["label"]

    evaluations = []
    evaluated_by_replicate = {}
    for index in REPLICATES:
        directory = root / "evaluations_v2" / f"r{index}"
        payload = _read(directory / "evaluation_dev22000_22029.json")
        evaluations.append(payload)
        binding_labels[f"{payload['profile_id']}-eval"] = (
            run_manifest_lock.evaluate_relocated_run(
                directory, "evaluation_dev22000_22029.json"
            )["label"]
        )
        evaluated_by_replicate[index] = payload["model"]["sha256"]

    checks = {}
    checks["TL2-01/TL2-02"] = tl2.verify_driver_digests(protocol)
    tl2.verify_resume_sources(protocol, run_manifests)
    tl2.verify_resume_source_is_not_the_byproduct(protocol)
    checks["TL2-03/TL2-04"] = "resume pinned by digest, source version-controlled"
    checks["TL2-05"] = {
        "training_seeds": tl2.verify_training_seeds(protocol, run_manifests),
        "evaluation_seeds": "22000..22029",
    }
    tl2.verify_evaluation_seeds(protocol, evaluations)
    tl2.verify_checkpoint_lineage(protocol, checkpoint_index)
    checks["TL2-06"] = "20 checkpoints, re-hashed from the repository"
    tl2.verify_run_lock_bindings(binding_labels)
    checks["TL2-07"] = {"runs_bound": len(binding_labels)}
    tl2.verify_evaluated_policy_is_a_retained_checkpoint(checkpoint_index, evaluated_by_replicate)
    checks["TL2-08"] = "every evaluated policy is a retained V2 checkpoint"

    per_replicate = [
        tl2.replicate_full_exposure(protocol, payload["episode_results"])
        for payload in evaluations
    ]

    # The convergence verdict comes from the retained curve index, measured on
    # the lineage curve under the rule V1 declared. It is read, never inferred:
    # classify() refuses to be called without it.
    #
    # WHICH AGGREGATE, declared here before any V2 curve existed: the line counts
    # as converged if ANY replicate's lineage curve has flattened. Both aggregates
    # are recorded either way. The direction is disclosed because it moves the
    # label: "any" makes converged easier, which yields TL2_REFERENCE_NOT_ATTAINED,
    # the result that does NOT invite more budget; "all" would make
    # TL2_BUDGET_EXHAUSTED easier. The choice that is stricter against this
    # project's own escalation is the one taken, as with the lineage curve itself.
    converged = bool(curve_index["any_replicate_converged"])
    result = tl2.classify(protocol, per_replicate, curve_converged=converged)

    reference = {
        str(index): tl2.reference_checkpoint(checkpoint_index, index) for index in REPLICATES
    }
    return {
        "schema_version": "TRACKED_LINEAGE_TRAINING_V2_CONTRACT_RECEIPT_V1",
        "contract_id": tl2.CONTRACT_ID,
        "protocol_sha256": tl2.PROTOCOL_SHA256,
        "evidence_date": date,
        "checks": checks,
        "curve_converged": converged,
        "curve_converged_aggregate": "any_replicate_converged",
        "curve_converged_aggregate_note": (
            "Declared before any V2 curve existed. 'any' makes converged easier and so "
            "yields TL2_REFERENCE_NOT_ATTAINED rather than TL2_BUDGET_EXHAUSTED; it is the "
            "choice that is stricter against adding further budget. Both aggregates are "
            "recorded below so the other reading is checkable."
        ),
        "curve_converged_any": bool(curve_index["any_replicate_converged"]),
        "curve_converged_all": bool(curve_index["all_replicates_converged"]),
        "curve_converged_measured_on": curve_index.get("measured_on", "own_curve"),
        "per_replicate_full_exposure": [
            {"replicate_index": i, "full": f, "episodes": t}
            for i, (f, t) in enumerate(per_replicate)
        ],
        "reference_checkpoints": reference,
        "result": result,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--date", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    receipt = run(args.date)
    text = json.dumps(receipt, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    if args.output is not None:
        if args.output.exists():
            raise SystemExit(f"refusing to overwrite {args.output}")
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

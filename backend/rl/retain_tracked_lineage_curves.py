"""Retain the tracked-lineage training curves and measure convergence.

Written after the fact, for a reason worth stating plainly: the line's result
label distinguishes TL_REFERENCE_NOT_ATTAINED from TL_BUDGET_EXHAUSTED by
whether the training curve converged, and the first analysis never measured
that -- it accepted the contract's default. The curves that settle the question
live in gitignored backend/rl/artifacts/ and would have died with the container,
exactly like the v7 pilot's control_step_trace did.

The convergence measure is deliberately crude and stated in full rather than
tuned: compare the mean reward gain per 500_000 steps over the final quarter of
training against the same quantity over the first quarter. A curve is called
converged only if the final-quarter slope has fallen to at most
CONVERGED_SLOPE_FRACTION of the first-quarter slope AND is below
CONVERGED_ABSOLUTE_SLOPE in absolute terms. Both thresholds are declared here,
in one place, before being applied -- they are a measurement definition, not a
result-dependent knob, and any change to them belongs in a protocol amendment.
V2's protocol carries them forward unchanged and forbids retuning them to obtain
a preferred label, so they are NOT restated for V2: there is one copy.

WHICH CURVE V2'S VERDICT IS MEASURED ON -- declared here before any V2 curve was
complete, and stated because the choice moves the label:

  V2 continues V1's replicates, so a V2 run's own progress.csv covers only the
  2_015_232-step increment, not the training that produced the evaluated policy.
  The verdict is therefore measured on the LINEAGE curve: V1's retained curve
  truncated at the resumed checkpoint, followed by V2's. V1's last logged point
  sits at 2_015_232, past the 1_999_968 checkpoint V2 resumed from, and those
  15_264 steps are not in the resumed policy, so they are dropped rather than
  spliced in.

  The increment-only measurement is computed and recorded alongside it, but is
  NOT used to assign the label. The direction matters and is disclosed: the
  lineage curve's first quarter is early training, so its slope is large, the
  ratio is small, and "converged" is EASIER to reach -- which yields
  TL2_REFERENCE_NOT_ATTAINED, the result that does not invite more budget. The
  increment-only reading would make TL2_BUDGET_EXHAUSTED easier. The stricter
  choice against this project's own escalation is the one taken.

Stdlib only, so the measurement can be re-derived under python -I -S.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
EVIDENCE_ROOT = BACKEND / "tracked_lineage_evidence"
PROFILE_PREFIX = "stand_start_walk_stop_0p7_tracked_lineage_b1_r"
V2_PROFILE_PREFIX = "stand_start_walk_stop_0p7_tracked_lineage_b2_r"

REWARD_COLUMN = "rollout/ep_rew_mean"
STEP_COLUMN = "time/total_timesteps"
SLOPE_WINDOW = 500_000

# A curve counts as converged only if BOTH hold. Declared before application.
CONVERGED_SLOPE_FRACTION = 0.10   # final-quarter slope <= 10% of first-quarter
CONVERGED_ABSOLUTE_SLOPE = 1.0    # and <= 1.0 reward per 500k steps

# V2 resumed here; V1 points beyond it are not in the resumed policy.
V2_RESUME_TIMESTEPS = 1_999_968


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return f"sha256:{digest.hexdigest()}"


def read_curve(path: Path) -> list[tuple[int, float]]:
    points = []
    for row in csv.DictReader(path.open(encoding="utf-8")):
        reward, step = row.get(REWARD_COLUMN), row.get(STEP_COLUMN)
        if reward in (None, "") or step in (None, ""):
            continue
        points.append((int(float(step)), float(reward)))
    if len(points) < 8:
        raise SystemExit(f"{path}: too few points to judge convergence")
    return points


def slope_per_window(points: list[tuple[int, float]], lo: float, hi: float) -> float:
    """Mean reward gain per SLOPE_WINDOW steps across the [lo, hi) fraction."""
    n = len(points)
    start, end = points[int(n * lo)], points[int(n * hi) - 1]
    spanned = (end[0] - start[0]) / SLOPE_WINDOW
    if spanned <= 0:
        raise SystemExit("degenerate slope window")
    return (end[1] - start[1]) / spanned


def measure(points: list[tuple[int, float]]) -> dict:
    first = slope_per_window(points, 0.0, 0.25)
    final = slope_per_window(points, 0.75, 1.0)
    fraction = final / first if first else None
    converged = (
        fraction is not None
        and fraction <= CONVERGED_SLOPE_FRACTION
        and abs(final) <= CONVERGED_ABSOLUTE_SLOPE
    )
    return {
        "first_quarter_slope_per_500k": round(first, 6),
        "final_quarter_slope_per_500k": round(final, 6),
        "final_over_first": round(fraction, 6) if fraction is not None else None,
        "converged": bool(converged),
        "peak_reward": round(max(p[1] for p in points), 6),
        "peak_at_timesteps": max(points, key=lambda p: p[1])[0],
        "final_reward": round(points[-1][1], 6),
        "final_timesteps": points[-1][0],
    }


def lineage_points(
    v1_curve: Path, v2_points: list[tuple[int, float]]
) -> list[tuple[int, float]]:
    """V1's curve up to the resumed checkpoint, then V2's. See the module docstring."""
    kept = [point for point in read_curve(v1_curve) if point[0] <= V2_RESUME_TIMESTEPS]
    if not kept:
        raise SystemExit(f"{v1_curve}: no point at or before the resume point")
    if kept[-1][0] >= v2_points[0][0]:
        raise SystemExit("lineage curve is not monotone in timesteps")
    return kept + v2_points


def retain(date: str, *, line: str = "v1", dry_run: bool = False) -> dict:
    if line == "v1":
        prefix, dirname, index_name = PROFILE_PREFIX, "training_curves", "training_curve_index.json"
    else:
        prefix = V2_PROFILE_PREFIX
        dirname, index_name = "training_curves_v2", "training_curve_index_v2.json"
    target_dir = EVIDENCE_ROOT / date / dirname
    index_path = EVIDENCE_ROOT / date / index_name

    per_replicate = {}
    for index in range(5):
        source = BACKEND / "rl" / "artifacts" / f"{prefix}{index}-run" / "logs" / "progress.csv"
        if not source.is_file():
            raise SystemExit(f"missing training curve {source}")
        target = target_dir / f"r{index}-progress.csv"
        if not dry_run:
            target_dir.mkdir(parents=True, exist_ok=True)
            if target.exists():
                raise SystemExit(f"refusing to overwrite retained evidence {target}")
            shutil.copyfile(source, target)
        points = read_curve(source)
        if line == "v1":
            result = measure(points)
        else:
            v1_curve = EVIDENCE_ROOT / date / "training_curves" / f"r{index}-progress.csv"
            result = measure(lineage_points(v1_curve, points))
            result["measured_on"] = "lineage"
            result["lineage_v1_curve"] = (
                f"backend/tracked_lineage_evidence/{date}/training_curves/r{index}-progress.csv"
            )
            result["lineage_v1_truncated_at"] = V2_RESUME_TIMESTEPS
            # Disclosure only. Not used to assign the label; see the module docstring.
            result["increment_only_not_used_for_label"] = measure(points)
        result["relative_path"] = (
            f"backend/tracked_lineage_evidence/{date}/{dirname}/r{index}-progress.csv"
        )
        result["sha256"] = sha256_file(source)
        result["bytes"] = source.stat().st_size
        per_replicate[str(index)] = result

    any_converged = any(item["converged"] for item in per_replicate.values())
    payload = {
        "contract_id": (
            "TRACKED-LINEAGE-TRAINING-V1" if line == "v1" else "TRACKED-LINEAGE-TRAINING-V2"
        ),
        "convergence_rule": {
            "slope_window_steps": SLOPE_WINDOW,
            "converged_slope_fraction": CONVERGED_SLOPE_FRACTION,
            "converged_absolute_slope": CONVERGED_ABSOLUTE_SLOPE,
            "definition": (
                "converged iff final-quarter slope <= converged_slope_fraction of the "
                "first-quarter slope AND |final-quarter slope| <= converged_absolute_slope, "
                "both measured as reward gain per slope_window_steps"
            ),
            "declared_before_application": True,
        },
        "replicates": per_replicate,
        "any_replicate_converged": any_converged,
        "all_replicates_converged": all(item["converged"] for item in per_replicate.values()),
    }
    if line == "v2":
        payload["measured_on"] = "lineage"
        payload["measured_on_note"] = (
            "V1's retained curve truncated at the resumed checkpoint (1999968) followed by "
            "V2's own curve, because a V2 run's progress.csv covers only the increment and "
            "not the training that produced the evaluated policy. The increment-only reading "
            "is recorded per replicate under increment_only_not_used_for_label and is NOT "
            "used to assign the label. Declared in the script before any V2 curve was "
            "complete; see the module docstring for which way the choice moves the label."
        )
    if not dry_run:
        index_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--date", required=True)
    parser.add_argument("--line", choices=("v1", "v2"), default="v1")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    payload = retain(args.date, line=args.line, dry_run=args.dry_run)
    for index, item in sorted(payload["replicates"].items()):
        print(
            f"r{index}: first {item['first_quarter_slope_per_500k']:+8.3f}  "
            f"final {item['final_quarter_slope_per_500k']:+8.3f}  "
            f"ratio {item['final_over_first']:.3f}  converged={item['converged']}"
        )
        disclosure = item.get("increment_only_not_used_for_label")
        if disclosure:
            print(
                f"    increment-only (disclosure, not used): "
                f"first {disclosure['first_quarter_slope_per_500k']:+8.3f}  "
                f"final {disclosure['final_quarter_slope_per_500k']:+8.3f}  "
                f"ratio {disclosure['final_over_first']:.3f}  "
                f"converged={disclosure['converged']}"
            )
    print(f"any converged: {payload['any_replicate_converged']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

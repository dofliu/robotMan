"""Budget probe for ``SECONDCASE-EXPOSURE-CENSORING-WALKER2D-V2`` (pilot only).

Trains the V1 reference arm once (a probe seed), evaluates every
``checkpoint_interval_timesteps`` on 30 probe seeds, and applies the frozen
adequacy rule: the first two consecutive checkpoints with at least
``minimum_full_exposure_episodes`` FULL_EXPOSURE episodes select the later
checkpoint's cumulative timesteps as the V2 budget.

This is a pilot.  Nothing it produces is evidence about the artifact, its seeds
are forbidden for V2, and the maximum budget is never raised after seeing the
curve.  The compute loop is separated from the provenance wrapper so tests can
shrink it without the CLI growing an override flag.

Usage
-----
    python rl/second_case_budget_probe.py run --output-root <dir> --lock-record <lock.json>
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from pathlib import Path
from typing import Any

RL_DIR = Path(__file__).resolve().parent
BACKEND_DIR = RL_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import exposure_identification as ei  # noqa: E402
import second_case_exposure_contract as sc  # noqa: E402

PROBE_SCHEMA = "SECOND_CASE_V2_BUDGET_PROBE_V1"
PROBE_ID = "SECONDCASE-V2-BUDGET-PROBE-V1"
RESULT_SCHEMA = "SECOND_CASE_V2_BUDGET_PROBE_RESULT_V1"
DEFAULT_PROBE = RL_DIR / "second_case_v2_budget_probe.json"

OUTCOME_FOUND = "PROBE_BUDGET_FOUND"
OUTCOME_NEGATIVE = "PROBE_NEGATIVE_MAX_BUDGET_REACHED"
OUTCOME_BLOCKED = "PROBE_BLOCKED_METHOD_FAILURE"
OUTCOME_LABELS = (OUTCOME_FOUND, OUTCOME_NEGATIVE, OUTCOME_BLOCKED)

PROBE_FIELDS = (
    "adequacy_rule",
    "arm_id",
    "base_protocol_id",
    "base_protocol_sha256",
    "checkpoint_interval_note",
    "checkpoint_interval_timesteps",
    "claim_boundary",
    "disclosure",
    "environment_lock_requirement",
    "evaluation_seed_first",
    "evaluation_seed_last",
    "evaluation_seeds_per_checkpoint",
    "forbidden_seed_ranges",
    "if_negative",
    "inherits_from_base",
    "low_pass_alpha",
    "max_checkpoints",
    "max_cumulative_timesteps",
    "outcome_labels",
    "planned_v2_seed_ranges",
    "probe_id",
    "purpose",
    "role",
    "schema_version",
    "source_requirement",
    "training_seed",
)


class ProbeError(RuntimeError):
    pass


def _runner():
    spec = importlib.util.spec_from_file_location("second_case_runner", RL_DIR / "second_case_runner.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def load_probe(path: Path = DEFAULT_PROBE) -> dict[str, Any]:
    probe = sc.load_json_file(Path(path))
    if not isinstance(probe, dict):
        raise ProbeError("probe must be an object")
    return probe


def validate_probe(probe: dict[str, Any], base_protocol: dict[str, Any], base_design: dict[str, Any]) -> dict[str, Any]:
    keys = tuple(sorted(probe))
    if keys != tuple(sorted(PROBE_FIELDS)):
        raise ProbeError(f"probe keys mismatch: missing={sorted(set(PROBE_FIELDS) - set(keys))} extra={sorted(set(keys) - set(PROBE_FIELDS))}")
    if probe["schema_version"] != PROBE_SCHEMA or probe["probe_id"] != PROBE_ID:
        raise ProbeError("probe identity mismatch")
    if probe["role"] != "PILOT_FOR_V2_BUDGET_ONLY":
        raise ProbeError("probe must declare itself a pilot")
    if probe["base_protocol_id"] != base_design["protocol_id"] or probe["base_protocol_id"] != sc.PROTOCOL_ID:
        raise ProbeError("probe must inherit from the V1 protocol")
    if probe["base_protocol_sha256"] != sc.PINNED_PROTOCOLS[sc.PROTOCOL_ID]:
        raise ProbeError("probe base_protocol_sha256 must equal the pinned V1 digest")
    if probe["arm_id"] != base_design["reference_arm_id"] or float(probe["low_pass_alpha"]) != base_design["alphas"][probe["arm_id"]]:
        raise ProbeError("probe must train the reference arm with its frozen alpha")
    interval = int(probe["checkpoint_interval_timesteps"])
    n_steps = int(base_protocol["training"]["hyperparameters"]["n_steps"]) * int(base_protocol["training"]["parallel_envs"])
    if interval <= 0 or interval % n_steps != 0:
        raise ProbeError("checkpoint interval must be a whole number of rollouts")
    max_checkpoints = int(probe["max_checkpoints"])
    if max_checkpoints < 2:
        raise ProbeError("at least two checkpoints are needed for the consecutive rule")
    if int(probe["max_cumulative_timesteps"]) != interval * max_checkpoints:
        raise ProbeError("max_cumulative_timesteps must equal interval x max_checkpoints")
    seeds = list(range(int(probe["evaluation_seed_first"]), int(probe["evaluation_seed_last"]) + 1))
    if len(seeds) != int(probe["evaluation_seeds_per_checkpoint"]):
        raise ProbeError("evaluation seed range length mismatch")
    training_seed = int(probe["training_seed"])
    for name, (lo, hi) in probe["forbidden_seed_ranges"].items():
        if any(lo <= s <= hi for s in seeds + [training_seed]):
            raise ProbeError(f"probe seeds overlap forbidden range {name}")
    for name, (lo, hi) in probe["planned_v2_seed_ranges"].items():
        if any(lo <= s <= hi for s in seeds + [training_seed]):
            raise ProbeError(f"probe seeds overlap planned V2 range {name}")
    rule = probe["adequacy_rule"]
    min_full = int(rule["minimum_full_exposure_episodes"])
    if not (1 <= min_full <= len(seeds)):
        raise ProbeError("minimum_full_exposure_episodes outside [1, seeds]")
    if int(rule["consecutive_checkpoints"]) != 2:
        raise ProbeError("the frozen rule uses exactly two consecutive checkpoints")
    if tuple(probe["outcome_labels"]) != OUTCOME_LABELS:
        raise ProbeError("probe outcome labels mismatch")
    return {
        "arm_id": probe["arm_id"],
        "alpha": float(probe["low_pass_alpha"]),
        "training_seed": training_seed,
        "evaluation_seeds": seeds,
        "interval": interval,
        "max_checkpoints": max_checkpoints,
        "minimum_full": min_full,
    }


def probe_training_loop(
    base_protocol: dict[str, Any],
    base_design: dict[str, Any],
    probe_design: dict[str, Any],
    output_dir: Path,
) -> dict[str, Any]:
    """Pure compute: incremental training with a checkpoint evaluation after each interval."""
    import torch
    from stable_baselines3 import PPO
    from stable_baselines3.common.vec_env import DummyVecEnv

    runner = _runner()
    design = dict(base_design)
    design["evaluation_seeds"] = list(probe_design["evaluation_seeds"])
    torch.set_num_threads(int(base_protocol["training"]["torch_threads"]))
    torch.use_deterministic_algorithms(True, warn_only=True)
    hyper = base_protocol["training"]["hyperparameters"]
    vec = DummyVecEnv([lambda: runner.make_env(base_protocol, design, probe_design["alpha"])])
    model = PPO(
        base_protocol["training"]["policy"],
        vec,
        learning_rate=hyper["learning_rate"],
        n_steps=hyper["n_steps"],
        batch_size=hyper["batch_size"],
        n_epochs=hyper["n_epochs"],
        gamma=hyper["gamma"],
        gae_lambda=hyper["gae_lambda"],
        clip_range=hyper["clip_range"],
        ent_coef=hyper["ent_coef"],
        vf_coef=hyper["vf_coef"],
        max_grad_norm=hyper["max_grad_norm"],
        normalize_advantage=hyper["normalize_advantage"],
        seed=probe_design["training_seed"],
        device=base_protocol["training"]["device"],
        verbose=0,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    checkpoints: list[dict[str, Any]] = []
    selected: int | None = None
    previous_full: int | None = None
    started = time.time()
    for k in range(1, probe_design["max_checkpoints"] + 1):
        model.learn(total_timesteps=probe_design["interval"], reset_num_timesteps=False)
        cumulative = int(model.num_timesteps)
        if cumulative != k * probe_design["interval"]:
            raise ProbeError(f"cumulative timesteps {cumulative} != {k * probe_design['interval']}")
        policy_path = output_dir / f"checkpoint_{k:02d}_{cumulative}.zip"
        model.save(policy_path)
        rows = runner.evaluate_cell(base_protocol, design, probe_design["alpha"], policy_path, output_dir / f"traces_{k:02d}")
        rows_path = output_dir / f"checkpoint_{k:02d}_episodes.json"
        rows_path.write_bytes(sc.json_bytes(rows))
        full = sum(1 for r in rows if r["exposure_class"] == ei.EXPOSURE_FULL)
        steps = sorted(r["realized_steps"] for r in rows)
        naive = ei.round_percent(ei.ordered_mean([float(r["naive_duty_pct"]) for r in rows]))
        nonfinite = sum(1 for r in rows if r["outcome_state"] != sc.OUTCOME_OBSERVED)
        entry = {
            "checkpoint_index": k,
            "cumulative_timesteps": cumulative,
            "policy_sha256": runner.sha256_file(policy_path),
            "episodes_sha256": runner.sha256_file(rows_path),
            "full_exposure_count": full,
            "early_terminated_count": len(rows) - full,
            "nonfinite_count": nonfinite,
            "realized_steps_min_median_max": [steps[0], steps[len(steps) // 2], steps[-1]],
            "naive_mean_duty_pct": naive,
            "adequate": full >= probe_design["minimum_full"],
            "elapsed_s": round(time.time() - started, 1),
        }
        checkpoints.append(entry)
        if nonfinite:
            return {"checkpoints": checkpoints, "outcome": OUTCOME_BLOCKED, "selected_budget_timesteps": None}
        if previous_full is not None and previous_full >= probe_design["minimum_full"] and full >= probe_design["minimum_full"]:
            selected = cumulative
            break
        previous_full = full
    vec.close()
    outcome = OUTCOME_FOUND if selected is not None else OUTCOME_NEGATIVE
    return {"checkpoints": checkpoints, "outcome": outcome, "selected_budget_timesteps": selected}


def run(args: argparse.Namespace) -> dict[str, Any]:
    runner = _runner()
    base_protocol = sc.load_protocol(sc.DEFAULT_PROTOCOL)
    base_design = sc.validate_protocol(base_protocol)
    probe = load_probe(args.probe)
    probe_design = validate_probe(probe, base_protocol, base_design)
    source_pre = runner.require_clean_source()
    output_root = Path(args.output_root).resolve()
    output_root.mkdir(parents=True, exist_ok=False)
    lock = runner.verify_lock_now(Path(args.lock_record), base_design)
    result: dict[str, Any] = {
        "schema_version": RESULT_SCHEMA,
        "probe_id": PROBE_ID,
        "probe_sha256": runner.sha256_file(Path(args.probe)),
        "base_protocol_id": sc.PROTOCOL_ID,
        "base_protocol_sha256": sc.PINNED_PROTOCOLS[sc.PROTOCOL_ID],
        "plant_asset_sha256": base_design["plant_asset_sha256"],
        "role": probe["role"],
        "arm_id": probe_design["arm_id"],
        "training_seed": probe_design["training_seed"],
        "evaluation_seed_first": probe_design["evaluation_seeds"][0],
        "evaluation_seed_last": probe_design["evaluation_seeds"][-1],
        "adequacy_rule": probe["adequacy_rule"],
        "environment_lock": lock,
        "source_git_sha_pre": source_pre["git_sha"],
        "source_dirty_pre": source_pre["working_tree_dirty"],
        "started_at_unix": time.time(),
        "claim_boundary": probe["claim_boundary"],
        "disclosure": probe["disclosure"],
    }
    try:
        result.update(probe_training_loop(base_protocol, base_design, probe_design, output_root / "checkpoints"))
    except Exception as exc:  # retained
        result["outcome"] = OUTCOME_BLOCKED
        result["failure"] = {"type": type(exc).__name__, "message": str(exc)}
        result.setdefault("checkpoints", [])
        result.setdefault("selected_budget_timesteps", None)
    finally:
        post = runner.git_source_identity()
        result["source_git_sha_post"] = post.get("git_sha")
        result["source_dirty_post"] = post.get("working_tree_dirty")
        result["finished_at_unix"] = time.time()
        (output_root / "probe_result.json").write_bytes(sc.json_bytes(result))
    if result["outcome"] not in OUTCOME_LABELS:
        raise ProbeError("outcome outside the frozen labels")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    r = sub.add_parser("run")
    r.add_argument("--output-root", type=Path, required=True)
    r.add_argument("--lock-record", type=Path, required=True)
    r.add_argument("--probe", type=Path, default=DEFAULT_PROBE)
    args = parser.parse_args()
    try:
        payload = run(args)
    except (ProbeError, sc.SecondCaseError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        sys.exit(2)
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

"""TRACKED-LINEAGE-TRAINING-V1 evidence contract (stdlib only, fail closed).

Implements the acceptance criteria of docs/TRACKED_LINEAGE_TRAINING_SPEC.md
section 12 over the artefacts a completed replicate leaves behind. Nothing here
trains, evaluates or reads a policy: it decides whether what was retained is
admissible as evidence for PUB-B1 and PUB-B2, and refuses otherwise.

Three properties are deliberate.

The five outcome labels are exhaustive and TL_METHOD_FAILURE is never
downgraded to one of the other four. A contract violation is not a weaker
result; it means the measurement did not happen.

Every threshold is read from the frozen protocol rather than restated here. A
value that appears in two places is a value that can drift, and the whole point
of this line is that its parameters were fixed before any curve was seen.

The evaluation seed schedule is enforced at ANALYSIS time. The generic
evaluation path has no *_EVALUATION_SEED_SCHEDULE_OVERRIDE_FORBIDDEN guard of
the kind the v7 and seedvar paths carry (rl/eval_policy.py:124, :161), so the
only place left to check it is here, over the retained output -- see TL-01b.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


CONTRACT_ID = "TRACKED-LINEAGE-TRAINING-V1"
REPO_ROOT = Path(__file__).resolve().parent.parent
PROTOCOL_PATH = REPO_ROOT / "backend" / "rl" / "tracked_lineage_training_protocol.json"
SPECIFICATION_PATH = REPO_ROOT / "docs" / "TRACKED_LINEAGE_TRAINING_SPEC.md"

# Layer two of the three-layer chain: this module pins the protocol, the
# protocol pins the specification. Layer three, the driver digest, is pinned
# inside the protocol itself.
PROTOCOL_SHA256 = "sha256:9963a2b25ee1640186e721ba9b7e745126b593eb083454aa33a64a709765e2fa"

LABEL_ATTAINED = "TL_REFERENCE_ATTAINED"
LABEL_PARTIAL = "TL_REFERENCE_PARTIAL"
LABEL_NOT_ATTAINED = "TL_REFERENCE_NOT_ATTAINED"
LABEL_BUDGET_EXHAUSTED = "TL_BUDGET_EXHAUSTED"
LABEL_METHOD_FAILURE = "TL_METHOD_FAILURE"

RESULT_LABELS = (
    LABEL_ATTAINED,
    LABEL_PARTIAL,
    LABEL_NOT_ATTAINED,
    LABEL_BUDGET_EXHAUSTED,
)
ALL_LABELS = RESULT_LABELS + (LABEL_METHOD_FAILURE,)

FULL_EXPOSURE_DURATION_S = 9.0
FULL_EXPOSURE_OUTCOME_STATE = "OBSERVED"

# An episode-level denominator is never a method-level one. 30 is this line's
# per-replicate episode count, 150 its total; 450 is inherited from the seedvar
# line so a reader cannot reach for it out of habit.
FORBIDDEN_DENOMINATORS = (30, 150, 450)
METHOD_LEVEL_DENOMINATOR = 5

CHECKPOINT_FIELDS = (
    "bytes",
    "realized_timesteps",
    "relative_path",
    "replicate_index",
    "sha256",
)


class TrackedLineageMethodFailure(Exception):
    """Raised for every contract violation.

    A single exception type on purpose: the caller must not be able to catch
    "just the recoverable ones" and carry on, because none of them are.
    """


def _fail(code: str, detail: str = "") -> None:
    raise TrackedLineageMethodFailure(f"{code}{': ' + detail if detail else ''}")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return f"sha256:{digest.hexdigest()}"


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        _fail("TL_FILE_MISSING", str(path))
    except json.JSONDecodeError as exc:
        _fail("TL_FILE_NOT_JSON", f"{path}: {exc}")


def load_protocol(
    path: Path = PROTOCOL_PATH, *, require_pinned_digest: bool = True
) -> dict[str, Any]:
    """Load the frozen protocol, refusing one that is not the pinned bytes.

    require_pinned_digest exists for the tests that build a mutated protocol to
    prove a criterion actually fires. It is never False on a real evaluation.
    """
    payload = _load_json(path)
    if not isinstance(payload, dict):
        _fail("TL_PROTOCOL_NOT_OBJECT")
    if payload.get("protocol_id") != CONTRACT_ID:
        _fail("TL_PROTOCOL_ID_MISMATCH", str(payload.get("protocol_id")))
    if require_pinned_digest:
        measured = sha256_file(path)
        if measured != PROTOCOL_SHA256:
            _fail("TL_PROTOCOL_DIGEST_MISMATCH", f"{measured} != {PROTOCOL_SHA256}")
        specification = payload.get("specification_sha256")
        measured_spec = sha256_file(SPECIFICATION_PATH)
        if specification != measured_spec:
            _fail(
                "TL_SPECIFICATION_DIGEST_MISMATCH",
                f"{measured_spec} != {specification}",
            )
    return payload


# --------------------------------------------------------------------------
# TL-01 / TL-02: driver identity
# --------------------------------------------------------------------------

def verify_driver_digests(
    protocol: dict[str, Any], *, root: Path = REPO_ROOT
) -> dict[str, str]:
    """TL-01 and TL-02: re-derive the driver digests and compare the pins.

    This is the runtime re-derivation the seed-variance protocol never had. It
    is also where eval_policy.py is held to its UNMODIFIED value: this line is
    scoped to PUB-B1 and PUB-B2 precisely because modifying that file would
    turn a green test red under an authorization the owner granted on
    2026-09-10 (specification section 6.4).
    """
    baseline = protocol.get("source_baseline")
    if not isinstance(baseline, dict):
        _fail("TL_PROTOCOL_MISSING_SOURCE_BASELINE")

    # TL-02: both digests are carried, or the disclosure is incomplete and the
    # contract fails closed rather than reporting a comparable line.
    superseded = baseline.get("superseded_training_driver_source_sha256")
    if not superseded:
        _fail("TL_SUPERSEDED_TRAINING_DRIVER_DIGEST_MISSING")

    measured: dict[str, str] = {}
    for key, source_key in (
        ("training_driver_source_sha256", "training_driver_source"),
        ("evaluation_driver_source_sha256", "evaluation_driver_source"),
    ):
        pinned = baseline.get(key)
        relative = baseline.get(source_key)
        if not relative:
            _fail("TL_PROTOCOL_MISSING_DRIVER_PATH", source_key)
        if not pinned:
            _fail("TL_DRIVER_DIGEST_NOT_PINNED", key)
        path = root / relative
        if not path.is_file():
            _fail("TL_DRIVER_SOURCE_MISSING", str(path))
        actual = sha256_file(path)
        if actual != pinned:
            _fail("TL_DRIVER_DIGEST_MISMATCH", f"{relative}: {actual} != {pinned}")
        measured[relative] = actual

    if measured.get(baseline["training_driver_source"]) == superseded:
        # The point of this line is that its driver differs from the one behind
        # the 2026-09-08 evidence. If they are equal, either the pin is stale or
        # the driver change was never made, and both are method failures.
        _fail("TL_TRAINING_DRIVER_EQUALS_SUPERSEDED")
    return measured


# --------------------------------------------------------------------------
# TL-03 / TL-04: scratch start and seed disjointness
# --------------------------------------------------------------------------

def verify_scratch_start(run_manifests: list[dict[str, Any]]) -> None:
    """TL-03: every replicate starts from scratch.

    A warm start here would carry CONDITIONAL_ON_FIXED_WARM_START straight back
    into the line built to remove it, so this is a contradiction rather than a
    configuration difference.
    """
    if not run_manifests:
        _fail("TL_NO_RUN_MANIFESTS")
    for manifest in run_manifests:
        profile = manifest.get("profile") or {}
        run_id = manifest.get("run_id", "<unknown>")
        if profile.get("warm_start_policy_id") is not None:
            _fail("TL_WARM_START_NOT_NULL", run_id)
        if manifest.get("warm_start") is not None:
            _fail("TL_WARM_START_RECORD_PRESENT", run_id)
        if manifest.get("resume") is not None:
            _fail("TL_RESUME_NOT_NULL", run_id)


def verify_training_seeds(
    protocol: dict[str, Any], run_manifests: list[dict[str, Any]]
) -> list[int]:
    """TL-04: the realised seeds are the frozen schedule, and the blocks do not overlap."""
    design = protocol["training_design"]
    expected = [int(seed) for seed in design["training_seeds"]]
    parallel = int(design["parallel_envs"])

    realised = [int((item.get("resolved") or {}).get("seed_base", -1)) for item in run_manifests]
    if sorted(realised) != sorted(expected):
        _fail("TL_TRAINING_SEED_SCHEDULE_MISMATCH", f"{sorted(realised)} != {sorted(expected)}")

    for existing in design.get("seeds_disjoint_from_existing", []):
        if int(existing) in expected:
            _fail("TL_TRAINING_SEED_COLLIDES_WITH_EXISTING", str(existing))

    # Each replicate seeds parallel_envs environments from [seed, seed + n - 1].
    # Overlapping blocks would make two replicates share environment streams,
    # which is not an independent replicate at all.
    blocks = sorted((seed, seed + parallel - 1) for seed in expected)
    for (_, previous_end), (next_start, _) in zip(blocks, blocks[1:]):
        if next_start <= previous_end:
            _fail("TL_ENVIRONMENT_SEED_BLOCK_OVERLAP", f"{previous_end} >= {next_start}")
    return expected


# --------------------------------------------------------------------------
# TL-01b / TL-05: evaluation seed schedule, enforced at analysis time
# --------------------------------------------------------------------------

def verify_evaluation_seeds(
    protocol: dict[str, Any], evaluation_outputs: list[dict[str, Any]]
) -> None:
    """TL-01b and TL-05: the retained seeds are exactly the frozen range.

    The generic evaluation path accepts whatever schedule it is handed, so this
    check is the only thing standing between the line and an evaluation on the
    wrong seeds. Both directions are checked: the exhausted, retired and sealed
    ranges must not appear, AND the retained set must equal the frozen one --
    absence of a forbidden seed is not presence of the right one.
    """
    design = protocol["evaluation_design"]
    start = int(design["evaluation_seed_start"])
    end = int(design["evaluation_seed_end"])
    expected = list(range(start, end + 1))

    forbidden: list[tuple[int, int, str]] = []
    for spec, reason in (design.get("forbidden_seed_ranges") or {}).items():
        low, _, high = spec.partition("-")
        forbidden.append((int(low), int(high), reason))

    if not evaluation_outputs:
        _fail("TL_NO_EVALUATION_OUTPUTS")

    for output in evaluation_outputs:
        seeds = output.get("evaluation_seeds")
        if not isinstance(seeds, list):
            _fail("TL_EVALUATION_SEEDS_MISSING", str(output.get("run_id")))
        seeds = [int(seed) for seed in seeds]
        for seed in seeds:
            for low, high, reason in forbidden:
                if low <= seed <= high:
                    _fail("TL_EVALUATION_SEED_FORBIDDEN", f"{seed} in {low}-{high} ({reason})")
        if seeds != expected:
            _fail(
                "TL_EVALUATION_SEED_SCHEDULE_MISMATCH",
                f"{seeds[:3]}...{seeds[-3:] if len(seeds) > 3 else ''} != {start}..{end}",
            )


# --------------------------------------------------------------------------
# TL-06: checkpoint lineage
# --------------------------------------------------------------------------

def verify_checkpoint_lineage(
    protocol: dict[str, Any], index: dict[str, Any], *, root: Path = REPO_ROOT
) -> None:
    """TL-06 / TL-CK-01..TL-CK-03: the retained lineage is complete and real.

    GIT_DIRECT was chosen because anyone can re-hash the files straight out of
    the repository, so the index is corroborated against the bytes on disk
    rather than trusted.
    """
    lineage = protocol["checkpoint_lineage"]
    per_replicate = int(lineage["per_replicate_count"])
    total = int(lineage["total_count"])
    expected_steps = [int(value) for value in lineage["expected_realized_timesteps"]]

    entries = index.get("checkpoints")
    if not isinstance(entries, list):
        _fail("TL_CHECKPOINT_INDEX_MALFORMED")
    if len(entries) != total:
        _fail("TL_CHECKPOINT_COUNT_MISMATCH", f"{len(entries)} != {total}")

    by_replicate: dict[int, list[dict[str, Any]]] = {}
    for entry in entries:
        missing = [field for field in CHECKPOINT_FIELDS if field not in entry]
        if missing:
            _fail("TL_CHECKPOINT_FIELD_MISSING", ",".join(sorted(missing)))
        by_replicate.setdefault(int(entry["replicate_index"]), []).append(entry)

    replicate_count = int(protocol["training_design"]["replicate_count"])
    if sorted(by_replicate) != list(range(replicate_count)):
        _fail("TL_CHECKPOINT_REPLICATE_SET_MISMATCH", str(sorted(by_replicate)))

    for replicate_index in sorted(by_replicate):
        items = sorted(by_replicate[replicate_index], key=lambda item: int(item["realized_timesteps"]))
        if len(items) != per_replicate:
            _fail(
                "TL_CHECKPOINT_PER_REPLICATE_COUNT_MISMATCH",
                f"r{replicate_index}: {len(items)} != {per_replicate}",
            )
        steps = [int(item["realized_timesteps"]) for item in items]
        # TL-CK-02: strictly increasing, no gap, no duplicate. Compared against
        # the corrected values from amendment 01, not the unattainable multiples
        # of 500_000 the first freeze named.
        if steps != expected_steps:
            _fail(
                "TL_CHECKPOINT_SEQUENCE_MISMATCH",
                f"r{replicate_index}: {steps} != {expected_steps}",
            )
        for item in items:
            path = root / item["relative_path"]
            if not path.is_file():
                _fail("TL_CHECKPOINT_FILE_MISSING", item["relative_path"])
            actual = sha256_file(path)
            if actual != item["sha256"]:
                _fail("TL_CHECKPOINT_DIGEST_MISMATCH", f"{item['relative_path']}: {actual}")
            if path.stat().st_size != int(item["bytes"]):
                _fail("TL_CHECKPOINT_SIZE_MISMATCH", item["relative_path"])


def verify_evaluated_policy_is_a_retained_checkpoint(
    index: dict, evaluated_policy_sha256_by_replicate: dict[int, str]
) -> None:
    """TL-CK-06 (amendment 02): the policy that was evaluated is a retained checkpoint.

    TL-CK-03 as first written required the final policy artifact to be a copy of
    a retained checkpoint or be the last one. Measured on replicate 0, that is
    unsatisfiable in this configuration: CheckpointCallback's last save lands at
    1_999_968 while the driver's policy.zip is written after learn() returns, at
    the rollout boundary 2_015_232 -- 15_264 steps apart. Amendment 02 reads
    TL-CK-03's "final policy artifact" as the reference policy TL-CK-04 already
    designated, the last retained checkpoint, and adds this check so the claim is
    recomputed rather than asserted. The driver's policy.zip is an unretained
    byproduct and may never be what gets evaluated.
    """
    retained: dict[int, set[str]] = {}
    for entry in index.get("checkpoints", []):
        retained.setdefault(int(entry["replicate_index"]), set()).add(entry["sha256"])
    if not evaluated_policy_sha256_by_replicate:
        _fail("TL_NO_EVALUATED_POLICY_DIGESTS")
    for replicate_index, digest in sorted(evaluated_policy_sha256_by_replicate.items()):
        available = retained.get(int(replicate_index))
        if not available:
            _fail("TL_NO_RETAINED_CHECKPOINT_FOR_REPLICATE", str(replicate_index))
        if digest not in available:
            _fail(
                "TL_EVALUATED_POLICY_NOT_A_RETAINED_CHECKPOINT",
                f"r{replicate_index}: {digest}",
            )


def reference_checkpoint(index: dict, replicate_index: int) -> dict:
    """TL-CK-04: the reference policy is the replicate's LAST retained checkpoint.

    Frozen before any evaluation result was seen. v5's checkpoint was chosen
    after its results were seen, out of a run that had regressed, which is part
    of why its provenance cannot be explained.
    """
    entries = [
        entry for entry in index.get("checkpoints", [])
        if int(entry["replicate_index"]) == int(replicate_index)
    ]
    if not entries:
        _fail("TL_NO_RETAINED_CHECKPOINT_FOR_REPLICATE", str(replicate_index))
    return max(entries, key=lambda entry: int(entry["realized_timesteps"]))


def verify_checkpoints_are_version_controlled(
    protocol: dict[str, Any], ignored_paths: list[str]
) -> None:
    """TL-06: a gitignored checkpoint is not version-controlled lineage.

    ignored_paths is whatever `git check-ignore` reported. GIT_DIRECT's entire
    credibility is that the bytes are in the repository; a retained-but-ignored
    checkpoint looks identical locally and vanishes for everyone else.
    """
    if not protocol["checkpoint_lineage"].get("must_not_be_gitignored"):
        _fail("TL_PROTOCOL_MISSING_GITIGNORE_RULE")
    if ignored_paths:
        _fail("TL_CHECKPOINT_PATH_GITIGNORED", ",".join(sorted(ignored_paths)))


# --------------------------------------------------------------------------
# TL-07: lock binding
# --------------------------------------------------------------------------

def verify_run_lock_bindings(binding_labels: dict[str, str]) -> None:
    """TL-07: every run was bound, as judged by the RUN-MANIFEST-LOCK-BINDING-V1 gate."""
    if not binding_labels:
        _fail("TL_NO_RUN_LOCK_BINDINGS")
    unbound = sorted(
        run_id for run_id, label in binding_labels.items() if label != "RUN_LOCK_BOUND"
    )
    if unbound:
        _fail("TL_RUN_LOCK_NOT_BOUND", ",".join(unbound))


# --------------------------------------------------------------------------
# Full exposure and the outcome label
# --------------------------------------------------------------------------

def episode_is_fully_exposed(episode: dict[str, Any]) -> bool:
    """duration_s == 9.0 AND outcome_state == OBSERVED.

    Both halves are required and cross-checked by the caller. duration_s is
    round(len(rewards) * 0.02, 3), so a full 450-step episode gives exactly 9.0
    and 449 gives 8.98 -- separable at three decimals without a tolerance.
    """
    return (
        float(episode.get("duration_s", -1.0)) == FULL_EXPOSURE_DURATION_S
        and episode.get("outcome_state") == FULL_EXPOSURE_OUTCOME_STATE
    )


def replicate_full_exposure(
    protocol: dict[str, Any], episodes: list[dict[str, Any]]
) -> tuple[int, int]:
    """Count fully exposed episodes in one replicate, cross-checking the two signals.

    An early termination must make duration_s short AND outcome_state non-
    OBSERVED. If the two disagree, one of them is wrong and neither can be
    trusted, so it is a method failure rather than a judgement call.
    """
    expected = int(protocol["evaluation_design"]["episodes_per_replicate"])
    if len(episodes) != expected:
        _fail("TL_EPISODE_COUNT_MISMATCH", f"{len(episodes)} != {expected}")
    full = 0
    for episode in episodes:
        duration_full = float(episode.get("duration_s", -1.0)) == FULL_EXPOSURE_DURATION_S
        outcome_full = episode.get("outcome_state") == FULL_EXPOSURE_OUTCOME_STATE
        if duration_full != outcome_full:
            _fail(
                "TL_EXPOSURE_SIGNALS_DISAGREE",
                f"duration_s={episode.get('duration_s')} outcome_state={episode.get('outcome_state')}",
            )
        full += int(duration_full)
    return full, expected


def classify(
    protocol: dict[str, Any],
    per_replicate_full: list[tuple[int, int]],
    *,
    budget_exhausted: bool = False,
) -> dict[str, Any]:
    """Assign one of the five frozen labels.

    The threshold is read from the protocol and compared as an exact rational,
    never as a rounded float: at 30 episodes the attainable proportions are
    thirtieths, which is why 0.98 does not exist under this design and why the
    frozen value is 30/30.
    """
    threshold = protocol["full_exposure_threshold"]
    numerator, _, denominator = str(threshold["value"]).partition("/")
    required_numerator, required_denominator = int(numerator), int(denominator)

    replicate_count = int(protocol["training_design"]["replicate_count"])
    if len(per_replicate_full) != replicate_count:
        _fail(
            "TL_REPLICATE_COUNT_MISMATCH",
            f"{len(per_replicate_full)} != {replicate_count}",
        )

    attained: list[bool] = []
    for full, total in per_replicate_full:
        if total != required_denominator:
            _fail("TL_EPISODE_DENOMINATOR_MISMATCH", f"{total} != {required_denominator}")
        attained.append(full >= required_numerator)

    if all(attained):
        label = LABEL_ATTAINED
    elif any(attained):
        label = LABEL_PARTIAL
    elif budget_exhausted:
        # Only reachable when no replicate met the threshold; a run that did
        # meet it has not exhausted anything.
        label = LABEL_BUDGET_EXHAUSTED
    else:
        label = LABEL_NOT_ATTAINED

    return {
        "contract_id": CONTRACT_ID,
        "label": label,
        "threshold": threshold["value"],
        "analysis_unit": "training_replicate",
        "method_level_denominator": METHOD_LEVEL_DENOMINATOR,
        "forbidden_denominators": list(FORBIDDEN_DENOMINATORS),
        "per_replicate_full_exposure": [
            {"replicate_index": index, "full": full, "total": total}
            for index, (full, total) in enumerate(per_replicate_full)
        ],
        "replicates_attaining_threshold": sum(attained),
        "pub_b2_pass": label == LABEL_ATTAINED,
    }

"""TRACKED-LINEAGE-TRAINING-V2 evidence contract (stdlib only, fail closed).

Implements the acceptance criteria of docs/TRACKED_LINEAGE_TRAINING_V2_SPEC.md
section 10 over what a completed V2 replicate leaves behind.

V2 continues V1's replicates rather than rerunning them, so this module reuses
V1's contract wherever the rule is unchanged -- full exposure, evaluation seeds,
checkpoint lineage, the label vocabulary -- and adds only what the continuation
makes different:

  TL2-03  resume is REQUIRED and its digest must equal the V1 reference
          checkpoint this protocol pins for that replicate, where V1's TL-03
          required resume to be null.
  TL2-04  the resume source must live in version control, not in the gitignored
          artifacts directory.

Reusing V1's code rather than restating its rules is deliberate: two copies of
the same threshold are two things that can drift apart, and the whole point of
V2 is that only the budget changed.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import tracked_lineage_contract as v1


CONTRACT_ID = "TRACKED-LINEAGE-TRAINING-V2"
REPO_ROOT = Path(__file__).resolve().parent.parent
PROTOCOL_PATH = REPO_ROOT / "backend" / "rl" / "tracked_lineage_training_v2_protocol.json"
SPECIFICATION_PATH = REPO_ROOT / "docs" / "TRACKED_LINEAGE_TRAINING_V2_SPEC.md"
EVIDENCE_PREFIX = "backend/tracked_lineage_evidence/"

PROTOCOL_SHA256 = "sha256:a38662d99c6c6a25015e3ab5f8d642b0bc601be8b1d5d157d7f5e00b8d9292d0"

LABEL_ATTAINED = "TL2_REFERENCE_ATTAINED"
LABEL_PARTIAL = "TL2_REFERENCE_PARTIAL"
LABEL_NOT_ATTAINED = "TL2_REFERENCE_NOT_ATTAINED"
LABEL_BUDGET_EXHAUSTED = "TL2_BUDGET_EXHAUSTED"
LABEL_METHOD_FAILURE = "TL2_METHOD_FAILURE"

RESULT_LABELS = (LABEL_ATTAINED, LABEL_PARTIAL, LABEL_NOT_ATTAINED, LABEL_BUDGET_EXHAUSTED)
ALL_LABELS = RESULT_LABELS + (LABEL_METHOD_FAILURE,)

# The same exception type as V1: a contract violation is never a weaker result,
# and a caller must not be able to catch "just the recoverable ones".
TrackedLineageMethodFailure = v1.TrackedLineageMethodFailure
_fail = v1._fail
sha256_file = v1.sha256_file


def load_protocol(
    path: Path = PROTOCOL_PATH, *, require_pinned_digest: bool = True
) -> dict[str, Any]:
    """Load the frozen V2 protocol, refusing bytes that are not the pinned ones."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        _fail("TL2_FILE_MISSING", str(path))
    except json.JSONDecodeError as exc:
        _fail("TL2_FILE_NOT_JSON", f"{path}: {exc}")
    if payload.get("protocol_id") != CONTRACT_ID:
        _fail("TL2_PROTOCOL_ID_MISMATCH", str(payload.get("protocol_id")))
    if require_pinned_digest:
        measured = sha256_file(path)
        if measured != PROTOCOL_SHA256:
            _fail("TL2_PROTOCOL_DIGEST_MISMATCH", f"{measured} != {PROTOCOL_SHA256}")
        spec = sha256_file(SPECIFICATION_PATH)
        if payload.get("specification_sha256") != spec:
            _fail("TL2_SPECIFICATION_DIGEST_MISMATCH", spec)
    return payload


# --------------------------------------------------------------------------
# TL2-01 / TL2-02: driver identity
# --------------------------------------------------------------------------

def verify_driver_digests(protocol: dict[str, Any], *, root: Path = REPO_ROOT) -> dict[str, str]:
    """TL2-01 and TL2-02, delegated to V1's implementation.

    The rule is identical: re-derive both driver digests, compare the pins,
    require the superseded one to be carried and to differ. Only the pinned
    values differ between V1 and V2, and those come from the protocol.
    """
    return v1.verify_driver_digests(protocol, root=root)


# --------------------------------------------------------------------------
# TL2-03 / TL2-04: the resume source
# --------------------------------------------------------------------------

def verify_resume_sources(
    protocol: dict[str, Any], run_manifests: list[dict[str, Any]], *, root: Path = REPO_ROOT
) -> None:
    """TL2-03 and TL2-04: every replicate resumed from its pinned V1 checkpoint.

    The inverse of V1's TL-03, which required resume to be null. Here resume is
    the mechanism, so what must be proved is that it pointed at exactly the
    checkpoint the protocol froze -- by digest, not by path, so that a file
    swapped underneath a correct-looking path is still caught.

    warm_start must still be null: V2 resumes full PPO state, it does not
    transplant weights into a fresh model.
    """
    sources = protocol["tracked_warm_start"]["sources"]
    if not run_manifests:
        _fail("TL2_NO_RUN_MANIFESTS")
    if len(run_manifests) != len(sources):
        _fail("TL2_RUN_MANIFEST_COUNT_MISMATCH", f"{len(run_manifests)} != {len(sources)}")

    for index, manifest in enumerate(run_manifests):
        run_id = manifest.get("run_id", f"<replicate {index}>")
        expected = sources.get(str(index))
        if expected is None:
            _fail("TL2_RESUME_SOURCE_NOT_PINNED", str(index))

        if (manifest.get("profile") or {}).get("warm_start_policy_id") is not None:
            _fail("TL2_WARM_START_NOT_NULL", run_id)
        if manifest.get("warm_start") is not None:
            _fail("TL2_WARM_START_RECORD_PRESENT", run_id)

        resume = manifest.get("resume")
        if not isinstance(resume, dict):
            _fail("TL2_RESUME_MISSING", run_id)
        if resume.get("sha256") != expected["sha256"]:
            _fail("TL2_RESUME_DIGEST_MISMATCH", f"{run_id}: {resume.get('sha256')}")
        if int(resume.get("source_num_timesteps", -1)) != int(expected["realized_timesteps"]):
            _fail(
                "TL2_RESUME_STEP_COUNT_MISMATCH",
                f"{run_id}: {resume.get('source_num_timesteps')}",
            )

        # TL2-04: the pinned source must be version-controlled. A resume from the
        # gitignored artifacts directory cannot be reconstructed by anyone else.
        relative = expected["relative_path"]
        if not relative.startswith(EVIDENCE_PREFIX):
            _fail("TL2_RESUME_SOURCE_NOT_VERSION_CONTROLLED", relative)
        path = root / relative
        if not path.is_file():
            _fail("TL2_RESUME_SOURCE_MISSING", relative)
        if sha256_file(path) != expected["sha256"]:
            _fail("TL2_RESUME_SOURCE_DIGEST_DRIFT", relative)


def verify_resume_source_is_not_the_byproduct(protocol: dict[str, Any]) -> None:
    """V1's policy.zip sits 15_264 steps past the reference and is not retained.

    Pinning it would make V2's starting point impossible to reconstruct offline,
    which is the whole reason V1 amendment 02 classified it as a byproduct.
    """
    for entry in protocol["tracked_warm_start"]["sources"].values():
        if int(entry["realized_timesteps"]) != 1_999_968:
            _fail("TL2_RESUME_SOURCE_NOT_THE_REFERENCE", str(entry["realized_timesteps"]))
        if entry["relative_path"].endswith("policy.zip"):
            _fail("TL2_RESUME_SOURCE_IS_THE_BYPRODUCT", entry["relative_path"])


# --------------------------------------------------------------------------
# TL2-05 .. TL2-08: delegated, because the rules are unchanged
# --------------------------------------------------------------------------

def verify_training_seeds(
    protocol: dict[str, Any], run_manifests: list[dict[str, Any]]
) -> list[int]:
    """TL2-05 (training half): the seeds match V1's, in order.

    Order matters here where it did not in V1: replicate i must continue
    replicate i, so a permutation would pair a checkpoint with another
    replicate's seed.
    """
    expected = [int(seed) for seed in protocol["training_design"]["training_seeds"]]
    realised = [int((item.get("resolved") or {}).get("seed_base", -1)) for item in run_manifests]
    if realised != expected:
        _fail("TL2_TRAINING_SEED_ORDER_MISMATCH", f"{realised} != {expected}")
    return expected


def verify_evaluation_seeds(
    protocol: dict[str, Any], evaluation_outputs: list[dict[str, Any]]
) -> None:
    """TL2-05 (evaluation half), delegated to V1: same range, same enforcement."""
    v1.verify_evaluation_seeds(protocol, evaluation_outputs)


def replicate_count(protocol: dict[str, Any]) -> int:
    """How many replicates the frozen V2 protocol describes.

    V1's protocol states this outright as training_design.replicate_count; V2's
    does not, and V2's protocol is frozen so the key cannot be added to it. The
    count is instead derivable from three frozen facts that must agree:
    total_count over per_replicate_count, the number of training seeds, and the
    number of pinned resume sources. Disagreement is a method failure rather
    than a casting vote -- if the protocol contradicts itself about how many
    replicates it has, nothing downstream of that is trustworthy.
    """
    lineage = protocol["checkpoint_lineage"]
    per_replicate = int(lineage["per_replicate_count"])
    if per_replicate <= 0:
        _fail("TL2_PER_REPLICATE_COUNT_INVALID", str(per_replicate))
    total = int(lineage["total_count"])
    if total % per_replicate:
        _fail("TL2_CHECKPOINT_TOTAL_NOT_DIVISIBLE", f"{total} / {per_replicate}")
    derived = {
        "checkpoint_counts": total // per_replicate,
        "training_seeds": len(protocol["training_design"]["training_seeds"]),
        "resume_sources": len(protocol["tracked_warm_start"]["sources"]),
    }
    if len(set(derived.values())) != 1:
        _fail("TL2_REPLICATE_COUNT_AMBIGUOUS", str(derived))
    return derived["checkpoint_counts"]


def verify_checkpoint_lineage(
    protocol: dict[str, Any], index: dict[str, Any], *, root: Path = REPO_ROOT
) -> None:
    """TL2-06, delegated to V1. Only the expected step values differ.

    The delegation needs one key V2's frozen protocol does not carry, so the
    count is derived and handed over in a shallow copy. The copy exists so this
    never mutates the caller's protocol: a verifier that edits the thing it is
    verifying is how a contract stops being one.
    """
    view = dict(protocol)
    view["training_design"] = dict(protocol["training_design"])
    view["training_design"]["replicate_count"] = replicate_count(protocol)
    v1.verify_checkpoint_lineage(view, index, root=root)


def verify_run_lock_bindings(binding_labels: dict[str, str]) -> None:
    """TL2-07, delegated to V1."""
    v1.verify_run_lock_bindings(binding_labels)


def verify_evaluated_policy_is_a_retained_checkpoint(
    index: dict[str, Any], evaluated_policy_sha256_by_replicate: dict[int, str]
) -> None:
    """TL2-08, delegated to V1's TL-CK-06."""
    v1.verify_evaluated_policy_is_a_retained_checkpoint(index, evaluated_policy_sha256_by_replicate)


def reference_checkpoint(index: dict[str, Any], replicate_index: int) -> dict[str, Any]:
    """The replicate's last retained V2 checkpoint, frozen before any result."""
    return v1.reference_checkpoint(index, replicate_index)


def replicate_full_exposure(
    protocol: dict[str, Any], episodes: list[dict[str, Any]]
) -> tuple[int, int]:
    """Unchanged from V1, including the cross-check between the two signals."""
    return v1.replicate_full_exposure(protocol, episodes)


# --------------------------------------------------------------------------
# The label
# --------------------------------------------------------------------------

def classify(
    protocol: dict[str, Any],
    per_replicate_full: list[tuple[int, int]],
    *,
    curve_converged: bool,
) -> dict[str, Any]:
    """Assign one of the five frozen V2 labels.

    Mutually exclusive by construction, applying V1 amendment 03's correction
    rather than repeating its defect: TL2_REFERENCE_NOT_ATTAINED carries "and
    the curve has converged", so it cannot hold at the same time as
    TL2_BUDGET_EXHAUSTED.

    curve_converged has no default, for the reason V1 amendment 03 recorded: a
    determination that can be skipped silently will be, and skipping it is
    exactly what produced V1's wrong label.
    """
    threshold = protocol["unchanged_from_v1"]["full_exposure_threshold"]
    numerator, _, denominator = threshold.split("=")[0].strip().partition("/")
    required_numerator, required_denominator = int(numerator), int(denominator)

    replicate_count = int(protocol["unchanged_from_v1"]["replicate_count"])
    if len(per_replicate_full) != replicate_count:
        _fail("TL2_REPLICATE_COUNT_MISMATCH", f"{len(per_replicate_full)} != {replicate_count}")

    attained = []
    for full, total in per_replicate_full:
        if total != required_denominator:
            _fail("TL2_EPISODE_DENOMINATOR_MISMATCH", f"{total} != {required_denominator}")
        attained.append(full >= required_numerator)

    if all(attained):
        label = LABEL_ATTAINED
    elif any(attained):
        label = LABEL_PARTIAL
    elif not curve_converged:
        label = LABEL_BUDGET_EXHAUSTED
    else:
        label = LABEL_NOT_ATTAINED

    return {
        "contract_id": CONTRACT_ID,
        "label": label,
        "threshold": f"{required_numerator}/{required_denominator}",
        "analysis_unit": "training_replicate",
        "method_level_denominator": v1.METHOD_LEVEL_DENOMINATOR,
        "forbidden_denominators": list(v1.FORBIDDEN_DENOMINATORS),
        "per_replicate_full_exposure": [
            {"replicate_index": i, "full": f, "total": t}
            for i, (f, t) in enumerate(per_replicate_full)
        ],
        "replicates_attaining_threshold": sum(attained),
        "curve_converged": bool(curve_converged),
        "pub_b2_pass": label == LABEL_ATTAINED,
        "not_independent_of_v1": True,
    }

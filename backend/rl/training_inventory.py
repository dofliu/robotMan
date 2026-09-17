"""Read-only training-profile inventory for the teaching application.

``TEACHING-BOUNDARY-V1``, specified in ``docs/TEACHING_BOUNDARY.md``.

``PROJECT_ASSESSMENT`` section 4.1 says the teaching simulator and the research
infrastructure are already decoupled and splitting them needs no refactor, only
a move.  That was true of twelve of the thirteen modules the application
actually loads, and false of one line: ``main.py`` imported
``public_training_inventory`` from ``rl/train_ppo.py``, so serving a read-only
list of training profiles pulled in a 1,292-line training driver, and through it
``stable_baselines3``, ``gymnasium`` and every frozen research protocol the
profile schema validates against.  This module is that one line's replacement.

Three design points are load-bearing rather than incidental.

First, ``train_ppo.py`` is not touched, byte for byte.  Moving the profile
schema out of it was the obvious refactor and measurement rejected it: the
``TrainingProfile`` validators call ``load_tracked_lineage_protocol()`` and
compare against ``TRACKED-LINEAGE-TRAINING-V1``/``V2`` and the seed-variance
protocol, so the schema is entangled with frozen research identity and would
have dragged that identity across the boundary with it.  Leaving the driver
alone also keeps this change clear of every digest question: the protocols pin
``train_ppo.py``'s digest at execution time, and nothing here changes it.

Second, this is a *projection*, not a second copy of the schema.
``training_profiles.json`` remains the single source.  ``train_ppo.py``
validates that file for *training* -- does this profile match the frozen
protocol it names.  This module validates it for *display* -- are the fields the
endpoint serves present and of the right type.  A read-only endpoint has no
business re-verifying a research freeze, and narrowing what the teaching
application asserts is the safe direction.

Third, the projection is exact, not approximate.  The served payload is not the
raw JSON: the pydantic model fills seven optional fields per profile
(``environment_id`` defaults to ``fixed_walk_v1``, six others to ``null``) and
emits fields in declaration order.  ``test_training_inventory.py`` asserts this
module's payload equals ``train_ppo.public_training_inventory()`` exactly, so
the split is proven behaviour-preserving rather than assumed to be.

Validation is fail-closed in the directions a display can be wrong: a missing
required field, a wrong type, or an unknown field all raise.  What it
deliberately does not do is re-run the research validators; ``train_ppo.py``
still does that when training actually runs.

Every import is stdlib, so this module runs under ``python -I -S``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

PROFILE_PATH = Path(__file__).resolve().parent / "training_profiles.json"

#: The endpoint never launches anything; the value is part of the payload so a
#: reader of the API, not only of the code, can see that.
EXECUTION_MODE = "OFFLINE_EXPLICIT_COMMAND_ONLY"

#: Required fields and the Python types a display may serve them as, in the
#: order ``TrainingProfile`` declares them. ``int`` is accepted where a float is
#: expected because JSON writes ``1`` for ``1.0``; ``bool`` is not, since it is
#: an ``int`` subclass and would silently pass.
REQUIRED_FIELDS: tuple[tuple[str, tuple[type, ...]], ...] = (
    ("profile_id", (str,)),
    ("speed_mps", (float, int)),
    ("step_length_m", (float, int)),
    ("duty", (float, int)),
    ("clearance_m", (float, int)),
    ("planned_timesteps", (int,)),
    ("parallel_envs", (int,)),
    ("seed_base", (int,)),
    ("status", (str,)),
)

#: Optional fields with the defaults the model fills in, in declaration order.
OPTIONAL_FIELDS: tuple[tuple[str, Any], ...] = (
    ("environment_id", "fixed_walk_v1"),
    ("task_id", None),
    ("warm_start_policy_id", None),
    ("pilot_protocol_id", None),
    ("seedvar_protocol_id", None),
    ("tracked_lineage_protocol_id", None),
    ("pilot_arm_id", None),
)

FIELD_ORDER: tuple[str, ...] = (
    tuple(name for name, _ in REQUIRED_FIELDS) + tuple(name for name, _ in OPTIONAL_FIELDS)
)


class TrainingInventoryError(Exception):
    """``training_profiles.json`` cannot be served as a profile inventory."""


def _check_type(where: str, field: str, value: Any, allowed: tuple[type, ...]) -> None:
    if isinstance(value, bool) and bool not in allowed:
        raise TrainingInventoryError(
            f"{where}: field {field!r} is a bool, which is not a {allowed[0].__name__}")
    if not isinstance(value, allowed):
        names = "/".join(t.__name__ for t in allowed)
        raise TrainingInventoryError(
            f"{where}: field {field!r} is {type(value).__name__}, expected {names}")


def _project(profile: Any, index: int) -> Dict[str, Any]:
    """One profile as the endpoint serves it, defaults filled, order fixed."""
    where = f"profiles[{index}]"
    if not isinstance(profile, dict):
        raise TrainingInventoryError(f"{where}: expected an object")

    known = set(FIELD_ORDER)
    unknown = sorted(set(profile) - known)
    if unknown:
        raise TrainingInventoryError(
            f"{where}: unknown field(s) {unknown}. The inventory forbids extra fields, "
            "so a profile schema change is a deliberate edit here rather than a silent "
            "passthrough")

    out: Dict[str, Any] = {}
    for field, allowed in REQUIRED_FIELDS:
        if field not in profile:
            raise TrainingInventoryError(f"{where}: missing required field {field!r}")
        _check_type(where, field, profile[field], allowed)
        out[field] = profile[field]
    for field, default in OPTIONAL_FIELDS:
        value = profile.get(field, default)
        if value is not None and not isinstance(value, str):
            raise TrainingInventoryError(
                f"{where}: field {field!r} is {type(value).__name__}, expected str or null")
        out[field] = value
    return out


def load_inventory(path: Path = PROFILE_PATH) -> Dict[str, Any]:
    """Read and validate the profile file as far as a display needs it."""
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise TrainingInventoryError(f"profile file not found: {path}") from error
    except json.JSONDecodeError as error:
        raise TrainingInventoryError(f"profile file is not valid JSON: {error}") from error

    if not isinstance(raw, dict):
        raise TrainingInventoryError("profile file must contain an object")
    for field in ("schema_version", "evidence_scope"):
        if not isinstance(raw.get(field), str) or not raw[field]:
            raise TrainingInventoryError(f"missing or empty {field!r}")
    profiles = raw.get("profiles")
    if not isinstance(profiles, list) or not profiles:
        raise TrainingInventoryError("'profiles' must be a non-empty list")

    projected: List[Dict[str, Any]] = [_project(item, i) for i, item in enumerate(profiles)]
    seen = set()
    for item in projected:
        if item["profile_id"] in seen:
            raise TrainingInventoryError(f"duplicate profile_id {item['profile_id']!r}")
        seen.add(item["profile_id"])

    return {
        "schema_version": raw["schema_version"],
        "evidence_scope": raw["evidence_scope"],
        "profiles": projected,
    }


def public_training_inventory(path: Path = PROFILE_PATH) -> Dict[str, Any]:
    """Read-only UI inventory; this endpoint never launches a training process."""
    inventory = load_inventory(path)
    return {
        "schema_version": inventory["schema_version"],
        "evidence_scope": inventory["evidence_scope"],
        "execution_mode": EXECUTION_MODE,
        "profiles": inventory["profiles"],
    }

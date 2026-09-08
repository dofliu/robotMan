"""Measured software-environment identity for retained simulation evidence.

``docs/VV_PLAN.md`` V0-R02 requires run identity to bind code, config, MJCF,
checkpoint *and* environment.  The first four already have content-sensitive
identity; the fifth had only ``>=`` floors in ``backend/requirements*.txt``.
A floor names an unbounded set of environments, not one environment, so it can
never be used to re-verify a numeric result.

This module implements ``ENVIRONMENT-LOCK-V1`` as frozen in
``docs/ENVIRONMENT_LOCK_SPEC.md``: it captures a typed lock record, digests the
part of it that must be byte-identical on a compliant machine, and compares two
records fail-closed.

Two properties of the implementation are load-bearing rather than incidental.

First, every third-party import is lazy and confined to a probe.  The record
schema, the canonical digest and the whole verification path are stdlib-only, so
a second ``python -I -S`` process can re-derive the digest of a record without
numpy, MuJoCo or torch installed at all.

Second, the fingerprints measure behaviour instead of trusting version strings.
The same ``numpy`` version can link a different BLAS and reduce in a different
order; IEEE 754 constrains each operation, not the order they are combined in.
So the record carries an actually-stepped MuJoCo state digest and an actually
executed torch optimiser step, not just ``__version__``.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata as importlib_metadata
import json
import math
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


LOCK_RECORD_SCHEMA = "ENVIRONMENT_LOCK_RECORD_V1"
LOCK_CONTRACT_ID = "ENVIRONMENT-LOCK-V1"
VERIFICATION_SCHEMA = "ENVIRONMENT_LOCK_VERIFICATION_V1"
DIGEST_REPLAY_SCHEMA = "ENVIRONMENT_LOCK_DIGEST_REPLAY_V1"
ERROR_SCHEMA = "ENVIRONMENT_LOCK_ERROR_RECEIPT_V1"

MEASURED_LOCK_CLASS = "MEASURED_ENVIRONMENT_LOCK"
SYNTHETIC_LOCK_CLASS = "SYNTHETIC_REGRESSION_LOCK"
ABSENT_LOCK_CLASS = "ABSENT_UNRECOVERABLE"
LOCK_CLASSES = (MEASURED_LOCK_CLASS, SYNTHETIC_LOCK_CLASS, ABSENT_LOCK_CLASS)
CAPTURED_LOCK_CLASSES = (MEASURED_LOCK_CLASS, SYNTHETIC_LOCK_CLASS)

FULL_LOCK = "FULL_LOCK"
PARTIAL_LOCK = "PARTIAL_LOCK"
NO_LOCK = "NO_LOCK"

THREADING_PINNED = "AMBIENT_THREADING_PINNED"
THREADING_NOT_PINNED = "AMBIENT_THREADING_NOT_PINNED"
THREADING_UNKNOWN = "AMBIENT_THREADING_UNKNOWN"

SEVERITY_MISMATCH = "LOCK_MISMATCH"
SEVERITY_RETAINED = "RETAINED_FINDING"

FINDING_INTERPRETER = "INTERPRETER_DRIFT"
FINDING_ARCHITECTURE = "ARCHITECTURE_DRIFT"
FINDING_DISTRIBUTION_VERSION = "DISTRIBUTION_VERSION_DRIFT"
FINDING_DISTRIBUTION_MISSING = "DISTRIBUTION_MISSING"
FINDING_DETERMINISM_ENVIRONMENT = "DETERMINISM_ENVIRONMENT_DRIFT"
FINDING_NUMERIC = "NUMERIC_FINGERPRINT_DRIFT"
FINDING_PLANT = "PLANT_FINGERPRINT_DRIFT"
FINDING_LEARNING = "LEARNING_FINGERPRINT_DRIFT"
FINDING_FINGERPRINT_UNAVAILABLE = "FINGERPRINT_UNAVAILABLE"
FINDING_OBSERVED_CONTEXT = "OBSERVED_CONTEXT_DRIFT"
FINDING_THREAD_COUNT = "THREAD_COUNT_NOT_PINNED"

# The distributions whose exact versions can change this project's numeric
# results or code paths.  Anything outside this set is deliberately excluded
# from the digest: locking the full site-packages inventory would make every
# unrelated tooling upgrade a false mismatch.
REQUIRED_DISTRIBUTIONS = (
    "cloudpickle",
    "fastapi",
    "gymnasium",
    "httpx",
    "mujoco",
    "numpy",
    "orjson",
    "pydantic",
    "pytest",
    "stable-baselines3",
    "torch",
    "uvicorn",
)

# Thread-count and RNG-affecting variables.  ``UNSET`` is a distinct state from
# an empty string and the two are never imputed onto each other.
DETERMINISM_ENVIRONMENT_VARIABLES = (
    "CUBLAS_WORKSPACE_CONFIG",
    "CUDA_VISIBLE_DEVICES",
    "MKL_NUM_THREADS",
    "MUJOCO_EGL_DEVICE_ID",
    "MUJOCO_GL",
    "NUMEXPR_NUM_THREADS",
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "PYTHONDONTWRITEBYTECODE",
    "PYTHONHASHSEED",
    "PYTHONOPTIMIZE",
    "PYTHONUTF8",
    "VECLIB_MAXIMUM_THREADS",
)

LOCKED_SECTIONS = (
    "architecture",
    "determinism_environment",
    "distributions",
    "interpreter",
    "learning_fingerprint",
    "numeric_fingerprint",
    "plant_fingerprint",
)
FINGERPRINT_SECTIONS = (
    "numeric_fingerprint",
    "plant_fingerprint",
    "learning_fingerprint",
)
FINGERPRINT_FINDING_IDS = {
    "numeric_fingerprint": FINDING_NUMERIC,
    "plant_fingerprint": FINDING_PLANT,
    "learning_fingerprint": FINDING_LEARNING,
}

INTERPRETER_FIELDS = (
    "byteorder",
    "float_info",
    "float_repr_style",
    "implementation",
    "int_bits_per_digit",
    "maxsize",
    "version",
    "version_info",
)
FLOAT_INFO_FIELDS = ("dig", "epsilon", "mant_dig", "max", "min", "radix")
ARCHITECTURE_FIELDS = ("machine", "system")
NUMERIC_FINGERPRINT_FIELDS = (
    "dtype_sizes",
    "longdouble_itemsize",
    "numpy_dot",
    "numpy_matmul_trace",
    "numpy_reciprocal_sum",
    "numpy_version",
    "stdlib_reciprocal_sum",
)
DTYPE_SIZE_NAMES = ("bool_", "float32", "float64", "int32", "int64", "intp")
PLANT_FINGERPRINT_FIELDS = (
    "final_qpos_z",
    "mjcf_sha256",
    "mujoco_version",
    "mujoco_version_string",
    "state_sha256",
    "step_count",
)
LEARNING_FINGERPRINT_FIELDS = (
    "default_dtype",
    "loss_value",
    "parameter_sha256",
    "probe_num_threads",
    "rng_sha256",
    "torch_version",
)
FINGERPRINT_FIELDS = {
    "numeric_fingerprint": NUMERIC_FINGERPRINT_FIELDS,
    "plant_fingerprint": PLANT_FINGERPRINT_FIELDS,
    "learning_fingerprint": LEARNING_FINGERPRINT_FIELDS,
}

OBSERVED_FIELDS = (
    "ambient_torch_num_threads",
    "cpu_count",
    "cuda_available",
    "executable",
    "installed_distribution_count",
    "libc",
    "platform",
    "processor",
    "recursion_limit",
    "sys_path_entry_count",
)

STATE_UNSET = "UNSET"
STATE_SET = "SET"
STATE_MISSING = "MISSING"
STATE_UNAVAILABLE = "UNAVAILABLE"
STATE_NONFINITE = "NONFINITE"
STATE_UNKNOWN = "UNKNOWN"

PLANT_PROBE_STEPS = 500
PLANT_PROBE_CTRL = 0.7

# Frozen inline MJCF.  It deliberately does not use ``backend/model_builder.py``:
# the probe must measure MuJoCo, not this repository's model code, and coupling
# it to repo source would make every unrelated model edit look like an
# environment change.  A free joint over a plane plus one actuated hinge is
# enough to exercise the contact solver, which is where builds actually differ.
PLANT_PROBE_MJCF = """<mujoco model="environment_lock_probe_v1">
  <option timestep="0.002" gravity="0 0 -9.81" integrator="Euler"/>
  <worldbody>
    <geom name="floor" type="plane" size="5 5 0.1"/>
    <body name="trunk" pos="0 0 0.6">
      <freejoint name="root"/>
      <geom name="trunk_geom" type="capsule" fromto="0 0 -0.15 0 0 0.15" size="0.08" density="900"/>
      <body name="link" pos="0 0 -0.15">
        <joint name="hinge" type="hinge" axis="0 1 0" range="-1.2 1.2"/>
        <geom name="link_geom" type="capsule" fromto="0 0 0 0 0 -0.3" size="0.05" density="900"/>
      </body>
    </body>
  </worldbody>
  <actuator>
    <motor name="hinge_motor" joint="hinge" gear="1" ctrlrange="-5 5"/>
  </actuator>
</mujoco>
"""

LEARNING_PROBE_INPUT_DIM = 16
LEARNING_PROBE_OUTPUT_DIM = 4
LEARNING_PROBE_BATCH = 2
LEARNING_PROBE_LR = 0.1
LEARNING_PROBE_SEED = 0

CLAIM_BOUNDARY = (
    "SIM_ONLY_MUJOCO / NOT_PHYSICALLY_VALIDATED. An environment lock record "
    "may support only a statement about software-environment identity. Equal "
    "fingerprints prove that the measured behaviours agree, not that the two "
    "environments are equivalent, and no lock record supports controller "
    "superiority, paper readiness, safety, or sim-to-real claims."
)


class EnvironmentLockError(RuntimeError):
    """Structural failure in an environment lock record or its verification."""


# --------------------------------------------------------------------------- #
# canonical JSON, digests and typed scalars
# --------------------------------------------------------------------------- #


def _json_bytes(payload: Any) -> bytes:
    try:
        return (
            json.dumps(
                payload,
                ensure_ascii=False,
                allow_nan=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError) as exc:
        raise EnvironmentLockError("lock payload is not strict finite JSON") from exc


def _sha256_bytes(payload: bytes) -> str:
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _sha256_text(text: str) -> str:
    return _sha256_bytes(text.encode("utf-8"))


def locked_digest(locked: dict[str, Any]) -> str:
    """SHA-256 over the canonical JSON of the ``locked`` subtree only.

    ``observed`` and ``captured_at_utc`` are excluded on purpose: if they were
    digested, the same environment would get a new identity on every capture
    and the lock would carry no information.
    """
    return _sha256_bytes(_json_bytes(locked))


def _measurement(value: float) -> Any:
    """Store a measured float as ``repr`` text, or as a typed non-finite state.

    Text keeps the digest independent of any float formatting behaviour and
    lets a NaN or infinity be retained without writing an illegal JSON number.
    """
    number = float(value)
    if not math.isfinite(number):
        if math.isnan(number):
            kind = "nan"
        else:
            kind = "inf" if number > 0 else "-inf"
        return {"state": STATE_NONFINITE, "kind": kind}
    return repr(number)


def _environment_variable_state(name: str) -> dict[str, str]:
    raw = os.environ.get(name)
    if raw is None:
        return {"state": STATE_UNSET}
    return {"state": STATE_SET, "value": raw}


def _unavailable(reason: str) -> dict[str, str]:
    return {"state": STATE_UNAVAILABLE, "reason": reason[:400]}


def _is_unavailable(section: Any) -> bool:
    return isinstance(section, dict) and section.get("state") == STATE_UNAVAILABLE


# --------------------------------------------------------------------------- #
# deterministic probe inputs
# --------------------------------------------------------------------------- #


def lcg_floats(count: int, seed: int) -> list[float]:
    """Fixed 32-bit LCG mapped exactly onto ``[-1, 1)``.

    Probe inputs must not come from ``numpy.random`` or ``torch.random``: RNG
    stream stability is itself a version-dependent fact, so using it as the
    carrier would confound the very thing being measured.  The divisor is a
    power of two and the state is an exact integer, so the mapping introduces
    no rounding of its own.
    """
    if count <= 0:
        raise EnvironmentLockError("probe input count must be positive")
    state = seed & 0xFFFFFFFF
    values: list[float] = []
    for _ in range(count):
        state = (1664525 * state + 1013904223) & 0xFFFFFFFF
        values.append(state / 2147483648.0 - 1.0)
    return values


def _reciprocals() -> list[float]:
    return [1.0 / index for index in range(1, 1001)]


# --------------------------------------------------------------------------- #
# fingerprints
# --------------------------------------------------------------------------- #


def numeric_fingerprint() -> dict[str, Any]:
    """stdlib plus numpy arithmetic behaviour."""
    reciprocals = _reciprocals()
    stdlib_sum = 0.0
    for value in reciprocals:
        stdlib_sum += value
    try:
        import numpy
    except Exception as exc:  # pragma: no cover - numpy is a hard dependency
        return _unavailable(f"numpy import failed: {type(exc).__name__}: {exc}")
    try:
        array = numpy.array(reciprocals, dtype=numpy.float64)
        vector = numpy.array(lcg_floats(257, 12345), dtype=numpy.float64)
        matrix = numpy.array(lcg_floats(33 * 33, 777), dtype=numpy.float64).reshape(33, 33)
        return {
            "dtype_sizes": {
                name: int(numpy.dtype(getattr(numpy, name)).itemsize)
                for name in DTYPE_SIZE_NAMES
            },
            "longdouble_itemsize": int(numpy.dtype(numpy.longdouble).itemsize),
            "numpy_dot": _measurement(vector @ vector),
            "numpy_matmul_trace": _measurement(numpy.trace(matrix @ matrix)),
            "numpy_reciprocal_sum": _measurement(array.sum()),
            "numpy_version": str(numpy.__version__),
            "stdlib_reciprocal_sum": _measurement(stdlib_sum),
        }
    except Exception as exc:
        return _unavailable(f"numpy probe failed: {type(exc).__name__}: {exc}")


def plant_fingerprint() -> dict[str, Any]:
    """Actually stepped MuJoCo state, not just the reported version."""
    try:
        import mujoco
    except Exception as exc:
        return _unavailable(f"mujoco import failed: {type(exc).__name__}: {exc}")
    try:
        model = mujoco.MjModel.from_xml_string(PLANT_PROBE_MJCF)
        data = mujoco.MjData(model)
        mujoco.mj_resetData(model, data)
        for index in range(model.nu):
            data.ctrl[index] = PLANT_PROBE_CTRL
        for _ in range(PLANT_PROBE_STEPS):
            mujoco.mj_step(model, data)
        parts = [repr(float(value)) for value in data.qpos]
        parts.extend(repr(float(value)) for value in data.qvel)
        return {
            "final_qpos_z": _measurement(data.qpos[2]),
            "mjcf_sha256": _sha256_text(PLANT_PROBE_MJCF),
            "mujoco_version": str(mujoco.__version__),
            "mujoco_version_string": str(mujoco.mj_versionString()),
            "state_sha256": _sha256_text("|".join(parts)),
            "step_count": int(PLANT_PROBE_STEPS),
        }
    except Exception as exc:
        return _unavailable(f"mujoco probe failed: {type(exc).__name__}: {exc}")


def learning_fingerprint() -> dict[str, Any]:
    """One real torch optimiser step, plus the seeded RNG stream identity.

    The two are separate locked facts.  ``rng_sha256`` catches a changed RNG
    stream (which silently changes what a training seed means); the parameter
    digest catches changed arithmetic even when the stream is identical.  The
    probe pins ``set_num_threads(1)`` so the locked values do not move with the
    machine's core count; the ambient thread count is recorded as observed
    context instead.
    """
    try:
        import torch
    except Exception as exc:
        return _unavailable(f"torch import failed: {type(exc).__name__}: {exc}")
    ambient_threads = None
    try:
        ambient_threads = int(torch.get_num_threads())
        torch.set_num_threads(1)
        torch.manual_seed(LEARNING_PROBE_SEED)
        stream = torch.rand(8)
        rng_parts = [repr(float(value)) for value in stream]

        layer = torch.nn.Linear(
            LEARNING_PROBE_INPUT_DIM, LEARNING_PROBE_OUTPUT_DIM, bias=True
        )
        weight_values = lcg_floats(LEARNING_PROBE_OUTPUT_DIM * LEARNING_PROBE_INPUT_DIM, 4242)
        bias_values = lcg_floats(LEARNING_PROBE_OUTPUT_DIM, 99)
        input_values = lcg_floats(LEARNING_PROBE_BATCH * LEARNING_PROBE_INPUT_DIM, 31337)
        target_values = lcg_floats(LEARNING_PROBE_BATCH * LEARNING_PROBE_OUTPUT_DIM, 5150)
        with torch.no_grad():
            layer.weight.copy_(
                torch.tensor(weight_values, dtype=torch.float32).reshape(
                    LEARNING_PROBE_OUTPUT_DIM, LEARNING_PROBE_INPUT_DIM
                )
            )
            layer.bias.copy_(torch.tensor(bias_values, dtype=torch.float32))
        inputs = torch.tensor(input_values, dtype=torch.float32).reshape(
            LEARNING_PROBE_BATCH, LEARNING_PROBE_INPUT_DIM
        )
        targets = torch.tensor(target_values, dtype=torch.float32).reshape(
            LEARNING_PROBE_BATCH, LEARNING_PROBE_OUTPUT_DIM
        )
        optimiser = torch.optim.SGD(layer.parameters(), lr=LEARNING_PROBE_LR)
        optimiser.zero_grad()
        loss = torch.nn.functional.mse_loss(layer(inputs), targets)
        loss.backward()
        optimiser.step()
        parameter_parts = [repr(float(value)) for value in layer.weight.detach().reshape(-1)]
        parameter_parts.extend(
            repr(float(value)) for value in layer.bias.detach().reshape(-1)
        )
        return {
            "default_dtype": str(torch.get_default_dtype()),
            "loss_value": _measurement(loss.detach().item()),
            "parameter_sha256": _sha256_text("|".join(parameter_parts)),
            "probe_num_threads": 1,
            "rng_sha256": _sha256_text("|".join(rng_parts)),
            "torch_version": str(torch.__version__),
        }
    except Exception as exc:
        return _unavailable(f"torch probe failed: {type(exc).__name__}: {exc}")
    finally:
        if ambient_threads is not None:
            try:
                torch.set_num_threads(ambient_threads)
            except Exception:  # pragma: no cover - restoring must never mask a result
                pass


# --------------------------------------------------------------------------- #
# capture
# --------------------------------------------------------------------------- #


def _interpreter_section() -> dict[str, Any]:
    info = sys.float_info
    return {
        "byteorder": sys.byteorder,
        "float_info": {
            "dig": int(info.dig),
            "epsilon": _measurement(info.epsilon),
            "mant_dig": int(info.mant_dig),
            "max": _measurement(info.max),
            "min": _measurement(info.min),
            "radix": int(info.radix),
        },
        "float_repr_style": sys.float_repr_style,
        "implementation": platform.python_implementation(),
        "int_bits_per_digit": int(sys.int_info.bits_per_digit),
        "maxsize": int(sys.maxsize),
        "version": platform.python_version(),
        "version_info": [
            int(sys.version_info.major),
            int(sys.version_info.minor),
            int(sys.version_info.micro),
            str(sys.version_info.releaselevel),
            int(sys.version_info.serial),
        ],
    }


def _distributions_section() -> dict[str, Any]:
    versions: dict[str, Any] = {}
    for name in REQUIRED_DISTRIBUTIONS:
        try:
            versions[name] = str(importlib_metadata.version(name))
        except importlib_metadata.PackageNotFoundError:
            versions[name] = {"state": STATE_MISSING}
        except Exception as exc:
            versions[name] = {
                "state": STATE_MISSING,
                "reason": f"{type(exc).__name__}: {exc}"[:400],
            }
    return versions


def _installed_distribution_count() -> Any:
    try:
        return len(list(importlib_metadata.distributions()))
    except Exception:
        return {"state": STATE_UNKNOWN}


def _ambient_torch_threads() -> Any:
    try:
        import torch

        return int(torch.get_num_threads())
    except Exception:
        return {"state": STATE_UNKNOWN}


def _cuda_available() -> Any:
    try:
        import torch

        return bool(torch.cuda.is_available())
    except Exception:
        return {"state": STATE_UNKNOWN}


def _observed_section() -> dict[str, Any]:
    try:
        libc = "/".join(part for part in platform.libc_ver() if part) or STATE_UNKNOWN
    except Exception:  # pragma: no cover - platform probe is best effort
        libc = STATE_UNKNOWN
    return {
        "ambient_torch_num_threads": _ambient_torch_threads(),
        "cpu_count": int(os.cpu_count() or 0),
        "cuda_available": _cuda_available(),
        "executable": sys.executable,
        "installed_distribution_count": _installed_distribution_count(),
        "libc": libc,
        "platform": platform.platform(),
        "processor": platform.processor(),
        "recursion_limit": int(sys.getrecursionlimit()),
        "sys_path_entry_count": len(sys.path),
    }


def _threading_determinism(determinism_environment: dict[str, Any]) -> str:
    """Derived from locked fields only, so a replay can recompute it exactly."""
    state = determinism_environment.get("OMP_NUM_THREADS")
    if not isinstance(state, dict):
        return THREADING_UNKNOWN
    if state.get("state") != STATE_SET:
        return THREADING_NOT_PINNED
    return THREADING_PINNED if state.get("value") == "1" else THREADING_NOT_PINNED


def _lock_completeness(locked: dict[str, Any]) -> str:
    for section in FINGERPRINT_SECTIONS:
        if _is_unavailable(locked.get(section)):
            return PARTIAL_LOCK
    for value in locked.get("distributions", {}).values():
        if not isinstance(value, str):
            return PARTIAL_LOCK
    return FULL_LOCK


def capture_environment_lock(
    lock_class: str = MEASURED_LOCK_CLASS,
    *,
    captured_at_utc: str | None = None,
) -> dict[str, Any]:
    """Measure the current environment into an ``ENVIRONMENT_LOCK_RECORD_V1``."""
    if lock_class not in CAPTURED_LOCK_CLASSES:
        raise EnvironmentLockError(
            f"capture requires one of {CAPTURED_LOCK_CLASSES}, got {lock_class!r}"
        )
    determinism_environment = {
        name: _environment_variable_state(name)
        for name in DETERMINISM_ENVIRONMENT_VARIABLES
    }
    locked = {
        "architecture": {
            "machine": platform.machine(),
            "system": platform.system(),
        },
        "determinism_environment": determinism_environment,
        "distributions": _distributions_section(),
        "interpreter": _interpreter_section(),
        "learning_fingerprint": learning_fingerprint(),
        "numeric_fingerprint": numeric_fingerprint(),
        "plant_fingerprint": plant_fingerprint(),
    }
    stamp = captured_at_utc or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    record = {
        "schema_version": LOCK_RECORD_SCHEMA,
        "contract_id": LOCK_CONTRACT_ID,
        "lock_class": lock_class,
        "captured_at_utc": stamp,
        "lock_completeness": _lock_completeness(locked),
        "threading_determinism": _threading_determinism(determinism_environment),
        "locked": locked,
        "observed": _observed_section(),
        "locked_sha256": locked_digest(locked),
        "claim_boundary": CLAIM_BOUNDARY,
    }
    return record


def absent_lock_record(reason: str) -> dict[str, Any]:
    """Typed statement that retained evidence carries no recoverable lock.

    This is not a placeholder to be filled in later.  Capturing the *current*
    environment and attaching it to evidence produced in an unknown one would
    be an imputation, so an absent record holds no measured value at all.
    """
    text = str(reason).strip()
    if not text:
        raise EnvironmentLockError("absent lock record requires an explicit reason")
    return {
        "schema_version": LOCK_RECORD_SCHEMA,
        "contract_id": LOCK_CONTRACT_ID,
        "lock_class": ABSENT_LOCK_CLASS,
        "lock_completeness": NO_LOCK,
        "absence_reason": text[:1000],
        "locked_sha256": None,
        "claim_boundary": CLAIM_BOUNDARY,
    }


# --------------------------------------------------------------------------- #
# validation
# --------------------------------------------------------------------------- #


def _require_object(value: Any, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise EnvironmentLockError(f"{context} must be an object")
    return value


def _require_exact_keys(
    value: dict[str, Any], expected: tuple[str, ...], context: str
) -> None:
    """Both directions, always.

    Only checking for missing keys would let an unknown field ride along
    undigested on the verification side; only checking for unknown fields would
    let a silently dropped field pass as agreement.
    """
    present = set(value)
    allowed = set(expected)
    missing = sorted(allowed - present)
    unexpected = sorted(present - allowed)
    if missing:
        raise EnvironmentLockError(f"{context} is missing fields: {missing}")
    if unexpected:
        raise EnvironmentLockError(f"{context} has undeclared fields: {unexpected}")


def _require_text(value: Any, context: str) -> str:
    if not isinstance(value, str) or not value:
        raise EnvironmentLockError(f"{context} must be a non-empty string")
    return value


def _require_int(value: Any, context: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise EnvironmentLockError(f"{context} must be an integer")
    return value


def _require_measurement(value: Any, context: str) -> Any:
    """A measured scalar is ``repr`` text or an explicit non-finite state."""
    if isinstance(value, str):
        try:
            parsed = float(value)
        except ValueError as exc:
            raise EnvironmentLockError(f"{context} is not a float repr") from exc
        # ``float("nan")`` parses, so text alone would let a non-finite value in
        # through the finite branch and bypass the typed state.
        if not math.isfinite(parsed):
            raise EnvironmentLockError(
                f"{context} must use the typed non-finite state, not float text"
            )
        return value
    if isinstance(value, dict):
        _require_exact_keys(value, ("kind", "state"), context)
        if value["state"] != STATE_NONFINITE:
            raise EnvironmentLockError(f"{context} has an unexpected state")
        if value["kind"] not in ("nan", "inf", "-inf"):
            raise EnvironmentLockError(f"{context} has an unexpected non-finite kind")
        return value
    raise EnvironmentLockError(f"{context} must be a float repr or a non-finite state")


def _validate_unavailable(section: Any, context: str) -> None:
    _require_exact_keys(_require_object(section, context), ("reason", "state"), context)
    _require_text(section["reason"], f"{context}.reason")


def _validate_interpreter(section: Any) -> None:
    interpreter = _require_object(section, "locked.interpreter")
    _require_exact_keys(interpreter, INTERPRETER_FIELDS, "locked.interpreter")
    _require_text(interpreter["byteorder"], "locked.interpreter.byteorder")
    _require_text(interpreter["float_repr_style"], "locked.interpreter.float_repr_style")
    _require_text(interpreter["implementation"], "locked.interpreter.implementation")
    _require_text(interpreter["version"], "locked.interpreter.version")
    _require_int(interpreter["int_bits_per_digit"], "locked.interpreter.int_bits_per_digit")
    _require_int(interpreter["maxsize"], "locked.interpreter.maxsize")
    version_info = interpreter["version_info"]
    if not isinstance(version_info, list) or len(version_info) != 5:
        raise EnvironmentLockError("locked.interpreter.version_info must have 5 entries")
    for index in (0, 1, 2, 4):
        _require_int(version_info[index], f"locked.interpreter.version_info[{index}]")
    _require_text(version_info[3], "locked.interpreter.version_info[3]")
    float_info = _require_object(interpreter["float_info"], "locked.interpreter.float_info")
    _require_exact_keys(float_info, FLOAT_INFO_FIELDS, "locked.interpreter.float_info")
    for field in ("dig", "mant_dig", "radix"):
        _require_int(float_info[field], f"locked.interpreter.float_info.{field}")
    for field in ("epsilon", "max", "min"):
        _require_measurement(float_info[field], f"locked.interpreter.float_info.{field}")


def _validate_architecture(section: Any) -> None:
    architecture = _require_object(section, "locked.architecture")
    _require_exact_keys(architecture, ARCHITECTURE_FIELDS, "locked.architecture")
    for field in ARCHITECTURE_FIELDS:
        _require_text(architecture[field], f"locked.architecture.{field}")


def _validate_distributions(section: Any) -> None:
    distributions = _require_object(section, "locked.distributions")
    _require_exact_keys(distributions, REQUIRED_DISTRIBUTIONS, "locked.distributions")
    for name in REQUIRED_DISTRIBUTIONS:
        value = distributions[name]
        context = f"locked.distributions.{name}"
        if isinstance(value, str):
            _require_text(value, context)
            continue
        entry = _require_object(value, context)
        if entry.get("state") != STATE_MISSING:
            raise EnvironmentLockError(f"{context} must be a version or a MISSING state")
        unexpected = sorted(set(entry) - {"reason", "state"})
        if unexpected:
            raise EnvironmentLockError(f"{context} has undeclared fields: {unexpected}")


def _validate_determinism_environment(section: Any) -> None:
    environment = _require_object(section, "locked.determinism_environment")
    _require_exact_keys(
        environment, DETERMINISM_ENVIRONMENT_VARIABLES, "locked.determinism_environment"
    )
    for name in DETERMINISM_ENVIRONMENT_VARIABLES:
        context = f"locked.determinism_environment.{name}"
        entry = _require_object(environment[name], context)
        state = entry.get("state")
        if state == STATE_UNSET:
            _require_exact_keys(entry, ("state",), context)
        elif state == STATE_SET:
            _require_exact_keys(entry, ("state", "value"), context)
            if not isinstance(entry["value"], str):
                raise EnvironmentLockError(f"{context}.value must be a string")
        else:
            raise EnvironmentLockError(f"{context} must be UNSET or SET")


def _validate_numeric_fingerprint(section: Any) -> None:
    fingerprint = _require_object(section, "locked.numeric_fingerprint")
    _require_exact_keys(
        fingerprint, NUMERIC_FINGERPRINT_FIELDS, "locked.numeric_fingerprint"
    )
    _require_text(fingerprint["numpy_version"], "locked.numeric_fingerprint.numpy_version")
    _require_int(
        fingerprint["longdouble_itemsize"],
        "locked.numeric_fingerprint.longdouble_itemsize",
    )
    for field in ("numpy_dot", "numpy_matmul_trace", "numpy_reciprocal_sum", "stdlib_reciprocal_sum"):
        _require_measurement(fingerprint[field], f"locked.numeric_fingerprint.{field}")
    sizes = _require_object(
        fingerprint["dtype_sizes"], "locked.numeric_fingerprint.dtype_sizes"
    )
    _require_exact_keys(sizes, DTYPE_SIZE_NAMES, "locked.numeric_fingerprint.dtype_sizes")
    for name in DTYPE_SIZE_NAMES:
        _require_int(sizes[name], f"locked.numeric_fingerprint.dtype_sizes.{name}")


def _validate_plant_fingerprint(section: Any) -> None:
    fingerprint = _require_object(section, "locked.plant_fingerprint")
    _require_exact_keys(fingerprint, PLANT_FINGERPRINT_FIELDS, "locked.plant_fingerprint")
    for field in ("mjcf_sha256", "mujoco_version", "mujoco_version_string", "state_sha256"):
        _require_text(fingerprint[field], f"locked.plant_fingerprint.{field}")
    _require_int(fingerprint["step_count"], "locked.plant_fingerprint.step_count")
    _require_measurement(fingerprint["final_qpos_z"], "locked.plant_fingerprint.final_qpos_z")


def _validate_learning_fingerprint(section: Any) -> None:
    fingerprint = _require_object(section, "locked.learning_fingerprint")
    _require_exact_keys(
        fingerprint, LEARNING_FINGERPRINT_FIELDS, "locked.learning_fingerprint"
    )
    for field in ("default_dtype", "parameter_sha256", "rng_sha256", "torch_version"):
        _require_text(fingerprint[field], f"locked.learning_fingerprint.{field}")
    _require_int(
        fingerprint["probe_num_threads"], "locked.learning_fingerprint.probe_num_threads"
    )
    _require_measurement(fingerprint["loss_value"], "locked.learning_fingerprint.loss_value")


_FINGERPRINT_VALIDATORS = {
    "numeric_fingerprint": _validate_numeric_fingerprint,
    "plant_fingerprint": _validate_plant_fingerprint,
    "learning_fingerprint": _validate_learning_fingerprint,
}


def _validate_observed(section: Any) -> None:
    observed = _require_object(section, "observed")
    _require_exact_keys(observed, OBSERVED_FIELDS, "observed")
    for field in ("executable", "libc", "platform"):
        if not isinstance(observed[field], str):
            raise EnvironmentLockError(f"observed.{field} must be a string")
    if not isinstance(observed["processor"], str):
        raise EnvironmentLockError("observed.processor must be a string")
    for field in ("cpu_count", "recursion_limit", "sys_path_entry_count"):
        _require_int(observed[field], f"observed.{field}")
    for field in ("ambient_torch_num_threads", "installed_distribution_count"):
        value = observed[field]
        if isinstance(value, bool) or not isinstance(value, (int, dict)):
            raise EnvironmentLockError(f"observed.{field} must be an integer or a state")
        if isinstance(value, dict):
            _require_exact_keys(value, ("state",), f"observed.{field}")
    cuda = observed["cuda_available"]
    if not isinstance(cuda, bool):
        _require_exact_keys(
            _require_object(cuda, "observed.cuda_available"),
            ("state",),
            "observed.cuda_available",
        )


def validate_lock_record(record: Any) -> dict[str, Any]:
    """Fail-closed schema check plus digest and derived-field recomputation."""
    payload = _require_object(record, "lock record")
    if payload.get("schema_version") != LOCK_RECORD_SCHEMA:
        raise EnvironmentLockError("unexpected lock record schema_version")
    if payload.get("contract_id") != LOCK_CONTRACT_ID:
        raise EnvironmentLockError("unexpected lock record contract_id")
    lock_class = payload.get("lock_class")
    if lock_class not in LOCK_CLASSES:
        raise EnvironmentLockError(f"unexpected lock_class: {lock_class!r}")

    if lock_class == ABSENT_LOCK_CLASS:
        _require_exact_keys(
            payload,
            (
                "absence_reason",
                "claim_boundary",
                "contract_id",
                "lock_class",
                "lock_completeness",
                "locked_sha256",
                "schema_version",
            ),
            "absent lock record",
        )
        if payload["lock_completeness"] != NO_LOCK:
            raise EnvironmentLockError("absent lock record must declare NO_LOCK")
        if payload["locked_sha256"] is not None:
            raise EnvironmentLockError("absent lock record must not carry a digest")
        _require_text(payload["absence_reason"], "absent lock record absence_reason")
        return {
            "schema_version": VERIFICATION_SCHEMA,
            "contract_id": LOCK_CONTRACT_ID,
            "record_valid": True,
            "lock_class": lock_class,
            "lock_completeness": NO_LOCK,
            "threading_determinism": THREADING_UNKNOWN,
            "locked_sha256": None,
            "claim_boundary": CLAIM_BOUNDARY,
        }

    _require_exact_keys(
        payload,
        (
            "captured_at_utc",
            "claim_boundary",
            "contract_id",
            "lock_class",
            "lock_completeness",
            "locked",
            "locked_sha256",
            "observed",
            "schema_version",
            "threading_determinism",
        ),
        "captured lock record",
    )
    _require_text(payload["captured_at_utc"], "captured_at_utc")
    locked = _require_object(payload["locked"], "locked")
    _require_exact_keys(locked, LOCKED_SECTIONS, "locked")
    _validate_interpreter(locked["interpreter"])
    _validate_architecture(locked["architecture"])
    _validate_distributions(locked["distributions"])
    _validate_determinism_environment(locked["determinism_environment"])
    for section in FINGERPRINT_SECTIONS:
        if _is_unavailable(locked[section]):
            _validate_unavailable(locked[section], f"locked.{section}")
        else:
            _FINGERPRINT_VALIDATORS[section](locked[section])
    _validate_observed(payload["observed"])

    expected_completeness = _lock_completeness(locked)
    if payload["lock_completeness"] != expected_completeness:
        raise EnvironmentLockError(
            "lock_completeness does not match the locked sections: "
            f"declared {payload['lock_completeness']!r}, derived {expected_completeness!r}"
        )
    expected_threading = _threading_determinism(locked["determinism_environment"])
    if payload["threading_determinism"] != expected_threading:
        raise EnvironmentLockError(
            "threading_determinism does not match OMP_NUM_THREADS: "
            f"declared {payload['threading_determinism']!r}, derived {expected_threading!r}"
        )
    expected_digest = locked_digest(locked)
    if payload["locked_sha256"] != expected_digest:
        raise EnvironmentLockError(
            "locked_sha256 does not match the locked subtree: "
            f"declared {payload['locked_sha256']!r}, derived {expected_digest!r}"
        )
    return {
        "schema_version": VERIFICATION_SCHEMA,
        "contract_id": LOCK_CONTRACT_ID,
        "record_valid": True,
        "lock_class": lock_class,
        "lock_completeness": expected_completeness,
        "threading_determinism": expected_threading,
        "locked_sha256": expected_digest,
        "claim_boundary": CLAIM_BOUNDARY,
    }


# --------------------------------------------------------------------------- #
# verification
# --------------------------------------------------------------------------- #


def _finding(
    finding_id: str,
    severity: str,
    section: str,
    field: str,
    expected: Any,
    observed: Any,
) -> dict[str, Any]:
    return {
        "finding_id": finding_id,
        "severity": severity,
        "section": section,
        "field": field,
        "expected": expected,
        "observed": observed,
    }


def _compare_mapping(
    finding_id: str,
    section: str,
    fields: tuple[str, ...],
    expected: dict[str, Any],
    observed: dict[str, Any],
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for field in fields:
        if expected[field] != observed[field]:
            findings.append(
                _finding(
                    finding_id,
                    SEVERITY_MISMATCH,
                    section,
                    field,
                    expected[field],
                    observed[field],
                )
            )
    return findings


def verify_environment_lock(
    expected_record: Any, observed_record: Any
) -> dict[str, Any]:
    """Compare two captured records field by field, fail closed on the locked set.

    Neither an absent record nor a synthetic record may stand in for a measured
    one, so lock-class agreement is checked before any field comparison: a
    synthetic fixture that matched a measured lock would let a regression test
    certify a real environment.
    """
    expected_validation = validate_lock_record(expected_record)
    observed_validation = validate_lock_record(observed_record)
    expected_class = expected_validation["lock_class"]
    observed_class = observed_validation["lock_class"]

    findings: list[dict[str, Any]] = []
    if expected_class != observed_class:
        return {
            "schema_version": VERIFICATION_SCHEMA,
            "contract_id": LOCK_CONTRACT_ID,
            "environment_lock_match": False,
            "lock_class_match": False,
            "expected_lock_class": expected_class,
            "observed_lock_class": observed_class,
            "expected_locked_sha256": expected_validation["locked_sha256"],
            "observed_locked_sha256": observed_validation["locked_sha256"],
            "expected_lock_completeness": expected_validation["lock_completeness"],
            "observed_lock_completeness": observed_validation["lock_completeness"],
            "mismatch_count": 1,
            "retained_finding_count": 0,
            "findings": [
                _finding(
                    "LOCK_CLASS_MISMATCH",
                    SEVERITY_MISMATCH,
                    "record",
                    "lock_class",
                    expected_class,
                    observed_class,
                )
            ],
            "claim_boundary": CLAIM_BOUNDARY,
        }
    if expected_class == ABSENT_LOCK_CLASS:
        raise EnvironmentLockError(
            "an absent lock record carries no measurement and cannot be verified"
        )

    expected_locked = expected_record["locked"]
    observed_locked = observed_record["locked"]

    findings.extend(
        _compare_mapping(
            FINDING_INTERPRETER,
            "interpreter",
            INTERPRETER_FIELDS,
            expected_locked["interpreter"],
            observed_locked["interpreter"],
        )
    )
    findings.extend(
        _compare_mapping(
            FINDING_ARCHITECTURE,
            "architecture",
            ARCHITECTURE_FIELDS,
            expected_locked["architecture"],
            observed_locked["architecture"],
        )
    )
    for name in REQUIRED_DISTRIBUTIONS:
        expected_version = expected_locked["distributions"][name]
        observed_version = observed_locked["distributions"][name]
        if expected_version == observed_version:
            continue
        finding_id = (
            FINDING_DISTRIBUTION_MISSING
            if not isinstance(observed_version, str)
            else FINDING_DISTRIBUTION_VERSION
        )
        findings.append(
            _finding(
                finding_id,
                SEVERITY_MISMATCH,
                "distributions",
                name,
                expected_version,
                observed_version,
            )
        )
    findings.extend(
        _compare_mapping(
            FINDING_DETERMINISM_ENVIRONMENT,
            "determinism_environment",
            DETERMINISM_ENVIRONMENT_VARIABLES,
            expected_locked["determinism_environment"],
            observed_locked["determinism_environment"],
        )
    )
    for section in FINGERPRINT_SECTIONS:
        expected_section = expected_locked[section]
        observed_section = observed_locked[section]
        expected_missing = _is_unavailable(expected_section)
        observed_missing = _is_unavailable(observed_section)
        if expected_missing or observed_missing:
            if expected_missing != observed_missing or expected_section != observed_section:
                findings.append(
                    _finding(
                        FINDING_FINGERPRINT_UNAVAILABLE,
                        SEVERITY_MISMATCH,
                        section,
                        "state",
                        expected_section,
                        observed_section,
                    )
                )
            continue
        findings.extend(
            _compare_mapping(
                FINGERPRINT_FINDING_IDS[section],
                section,
                FINGERPRINT_FIELDS[section],
                expected_section,
                observed_section,
            )
        )

    for field in OBSERVED_FIELDS:
        expected_value = expected_record["observed"][field]
        observed_value = observed_record["observed"][field]
        if expected_value != observed_value:
            findings.append(
                _finding(
                    FINDING_OBSERVED_CONTEXT,
                    SEVERITY_RETAINED,
                    "observed",
                    field,
                    expected_value,
                    observed_value,
                )
            )

    mismatches = [item for item in findings if item["severity"] == SEVERITY_MISMATCH]
    retained = [item for item in findings if item["severity"] == SEVERITY_RETAINED]
    digest_equal = (
        expected_validation["locked_sha256"] == observed_validation["locked_sha256"]
    )
    # A digest difference with no field-level mismatch would mean the field
    # registry no longer covers the digested subtree, which is a contract defect
    # rather than an environment difference.
    if digest_equal != (not mismatches):
        raise EnvironmentLockError(
            "locked digest and field comparison disagree; the locked field "
            "registry does not cover the digested subtree"
        )
    return {
        "schema_version": VERIFICATION_SCHEMA,
        "contract_id": LOCK_CONTRACT_ID,
        "environment_lock_match": not mismatches,
        "lock_class_match": True,
        "expected_lock_class": expected_class,
        "observed_lock_class": observed_class,
        "expected_locked_sha256": expected_validation["locked_sha256"],
        "observed_locked_sha256": observed_validation["locked_sha256"],
        "expected_lock_completeness": expected_validation["lock_completeness"],
        "observed_lock_completeness": observed_validation["lock_completeness"],
        "mismatch_count": len(mismatches),
        "retained_finding_count": len(retained),
        "findings": findings,
        "claim_boundary": CLAIM_BOUNDARY,
    }


def satisfies_full_lock_requirement(record: Any) -> bool:
    """A protocol demanding ``FULL_LOCK`` accepts only a complete measured lock."""
    validation = validate_lock_record(record)
    return (
        validation["lock_class"] == MEASURED_LOCK_CLASS
        and validation["lock_completeness"] == FULL_LOCK
    )


# --------------------------------------------------------------------------- #
# independent stdlib-only digest replay
# --------------------------------------------------------------------------- #


def replay_locked_digest(record_path: Path) -> dict[str, Any]:
    """Re-derive ``locked_sha256`` in a separate ``python -I -S`` interpreter.

    Every third-party import in this module is lazy, so the replay runs with no
    site packages at all: the digest is proved to depend on the record bytes
    rather than on the environment reading them.
    """
    module = Path(__file__).resolve()
    completed = subprocess.run(
        [sys.executable, "-I", "-S", str(module), "digest", str(Path(record_path).resolve())],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise EnvironmentLockError(
            "stdlib-only digest replay failed: "
            f"exit {completed.returncode}: {completed.stderr.strip()[:400]}"
        )
    try:
        replayed = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise EnvironmentLockError("stdlib-only digest replay emitted invalid JSON") from exc
    record = load_lock_record(Path(record_path))
    declared = record.get("locked_sha256")
    if replayed.get("locked_sha256") != declared:
        raise EnvironmentLockError(
            "stdlib-only digest replay mismatch: "
            f"{replayed.get('locked_sha256')!r} != {declared!r}"
        )
    return {
        "schema_version": DIGEST_REPLAY_SCHEMA,
        "contract_id": LOCK_CONTRACT_ID,
        "replay_exact": True,
        "replay_interpreter_flags": ["-I", "-S"],
        "locked_sha256": declared,
        "claim_boundary": CLAIM_BOUNDARY,
    }


# --------------------------------------------------------------------------- #
# file IO
# --------------------------------------------------------------------------- #


def _reject_nonfinite(constant: str) -> Any:
    raise EnvironmentLockError(f"lock record contains a non-finite JSON constant: {constant}")


def load_lock_record(path: Path) -> dict[str, Any]:
    try:
        payload = Path(path).read_bytes()
    except OSError as exc:
        raise EnvironmentLockError(f"cannot read lock record: {path}") from exc
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise EnvironmentLockError(f"lock record is not UTF-8: {path}") from exc
    seen: list[str] = []

    def _reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        keys = [key for key, _ in pairs]
        if len(set(keys)) != len(keys):
            seen.append("duplicate")
        return dict(pairs)

    try:
        record = json.loads(text, object_pairs_hook=_reject_duplicates, parse_constant=_reject_nonfinite)
    except json.JSONDecodeError as exc:
        raise EnvironmentLockError(f"lock record is not valid JSON: {path}") from exc
    if seen:
        raise EnvironmentLockError(f"lock record has duplicate object keys: {path}")
    return _require_object(record, "lock record")


def write_lock_record(path: Path, record: dict[str, Any]) -> str:
    """Write the record and prove the readback matches what was intended."""
    target = Path(path)
    payload = _json_bytes(record)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".partial")
    if temporary.exists():
        raise EnvironmentLockError(f"refusing to reuse partial artifact: {temporary.name}")
    descriptor = os.open(
        temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    )
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
    os.replace(temporary, target)
    written = target.read_bytes()
    if written != payload:
        raise EnvironmentLockError(f"lock record readback mismatch: {target.name}")
    return _sha256_bytes(payload)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def _print(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False))


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Capture, validate, digest and verify ENVIRONMENT-LOCK-V1 records. "
            "Exit 0 on match, 1 on lock mismatch, 2 on structural failure."
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    capture_parser = subparsers.add_parser("capture")
    capture_parser.add_argument("output", type=Path)
    capture_parser.add_argument(
        "--lock-class", choices=CAPTURED_LOCK_CLASSES, default=MEASURED_LOCK_CLASS
    )
    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("record", type=Path)
    digest_parser = subparsers.add_parser("digest")
    digest_parser.add_argument("record", type=Path)
    verify_parser = subparsers.add_parser("verify")
    verify_parser.add_argument("expected", type=Path)
    verify_parser.add_argument("--observed", type=Path, default=None)
    args = parser.parse_args()

    try:
        if args.command == "capture":
            record = capture_environment_lock(args.lock_class)
            record_sha256 = write_lock_record(args.output, record)
            payload = validate_lock_record(record)
            payload["record_path"] = str(args.output)
            payload["record_sha256"] = record_sha256
            payload["replay"] = replay_locked_digest(args.output)
            exit_code = 0
        elif args.command == "validate":
            payload = validate_lock_record(load_lock_record(args.record))
            exit_code = 0
        elif args.command == "digest":
            record = load_lock_record(args.record)
            locked = record.get("locked")
            payload = {
                "schema_version": DIGEST_REPLAY_SCHEMA,
                "contract_id": LOCK_CONTRACT_ID,
                "locked_sha256": None if locked is None else locked_digest(locked),
            }
            exit_code = 0
        else:
            expected = load_lock_record(args.expected)
            if args.observed is None:
                observed = capture_environment_lock(expected.get("lock_class", MEASURED_LOCK_CLASS))
            else:
                observed = load_lock_record(args.observed)
            payload = verify_environment_lock(expected, observed)
            exit_code = 0 if payload["environment_lock_match"] else 1
    except Exception as exc:
        _print(
            {
                "schema_version": ERROR_SCHEMA,
                "contract_id": LOCK_CONTRACT_ID,
                "validation_status": "STRUCTURAL_FAILURE",
                "record_valid": False,
                "environment_lock_match": False,
                "error": f"{type(exc).__name__}: {exc}"[:1000],
                "claim_boundary": CLAIM_BOUNDARY,
            }
        )
        raise SystemExit(2) from exc
    _print(payload)
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()

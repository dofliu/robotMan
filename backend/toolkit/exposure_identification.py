"""Assumption-free identification bounds for rate-type outcomes under exposure censoring.

This module is the generic core that both ``training_seed_variance_contract``
(v7 humanoid) and ``second_case_exposure_contract`` (Walker2d) rely on
semantically.  It depends on the standard library only, so a ``python -I -S``
process can re-derive every number it produces.

Vocabulary
----------
An *episode* realizes ``observed_total`` units of exposure out of a frozen
``horizon_total`` (e.g. 4500 substeps, or 1000 control steps x 6 joints), and
``observed_positive`` of the observed units carry the event (saturated).

* The **naive rate** divides by what was observed: ``positive / observed_total``.
  It is what a per-step average reports and it silently conditions on survival.
* The **full-horizon bound** divides by the horizon and lets every unobserved
  unit be either 0 or 1: ``[positive / horizon, (positive + horizon - observed)
  / horizon]``.  It assumes nothing about what the episode would have done had
  it survived.  When the episode ran the full horizon the bound is a point and
  equals the naive rate.

Arithmetic rules (contractual, not incidental)
---------------------------------------------
* Sums are left-to-right in the caller's order and float addition is not
  associative, so callers pass values in ascending seed / replicate order.
* Cell means are rounded to ``PERCENT_DECIMALS`` **before** differencing, and
  differences are rounded again; the seed-variance summary was produced this
  way and ``test_exposure_identification`` asserts bit-exact agreement with it.
* A sample SD is defined only over point values.  Intervals have no SD; the
  midpoint is an imputation and is refused.
* ``NOT_IDENTIFIED`` never collapses to a sign.
"""

from __future__ import annotations

import math
from typing import Any

PERCENT_DECIMALS = 6

SIGN_NEGATIVE = "NEGATIVE"
SIGN_POSITIVE = "POSITIVE"
SIGN_UNIDENTIFIED = "UNIDENTIFIED"

EXPOSURE_FULL = "FULL_EXPOSURE"
EXPOSURE_EARLY = "EARLY_TERMINATED"
EXPOSURE_NONE = "NO_EXPOSURE"


class ExposureIdentificationError(ValueError):
    """Raised when an input would force an assumption the bound does not make."""


def round_percent(value: float) -> float:
    return round(value, PERCENT_DECIMALS)


def ordered_mean(values: list[float]) -> float:
    """Left-to-right float addition, then one division."""
    if not values:
        raise ExposureIdentificationError("mean requires at least one value")
    total = 0.0
    for value in values:
        total += value
    return total / len(values)


def ordered_sample_sd(values: list[float]) -> float:
    """Two-pass sample SD, ``df = n - 1``, same summation order as the mean."""
    count = len(values)
    if count < 2:
        raise ExposureIdentificationError("sample SD requires at least two values")
    mean = ordered_mean(values)
    accumulator = 0.0
    for value in values:
        delta = value - mean
        accumulator += delta * delta
    return math.sqrt(accumulator / (count - 1))


def _require_count(value: Any, context: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ExposureIdentificationError(f"{context} must be an integer count")
    if value < 0:
        raise ExposureIdentificationError(f"{context} must be non-negative")
    return value


def exposure_class(observed_total: int, horizon_total: int) -> str:
    observed_total = _require_count(observed_total, "observed_total")
    horizon_total = _require_count(horizon_total, "horizon_total")
    if horizon_total == 0:
        raise ExposureIdentificationError("horizon_total must be positive")
    if observed_total > horizon_total:
        raise ExposureIdentificationError("observed exposure exceeds the frozen horizon")
    if observed_total == 0:
        return EXPOSURE_NONE
    if observed_total == horizon_total:
        return EXPOSURE_FULL
    return EXPOSURE_EARLY


def naive_rate_pct(observed_positive: int, observed_total: int) -> float | None:
    """``100 * positive / observed``; ``None`` when nothing was observed."""
    observed_positive = _require_count(observed_positive, "observed_positive")
    observed_total = _require_count(observed_total, "observed_total")
    if observed_total == 0:
        return None
    if observed_positive > observed_total:
        raise ExposureIdentificationError("positive count exceeds observed exposure")
    return round_percent(100.0 * observed_positive / observed_total)


def episode_bound_pct(
    observed_positive: int, observed_total: int, horizon_total: int
) -> dict[str, Any]:
    """Assumption-free full-horizon bound on the rate, in percent."""
    observed_positive = _require_count(observed_positive, "observed_positive")
    klass = exposure_class(observed_total, horizon_total)
    if observed_positive > observed_total:
        raise ExposureIdentificationError("positive count exceeds observed exposure")
    lower = round_percent(100.0 * observed_positive / horizon_total)
    upper = round_percent(
        100.0 * (observed_positive + (horizon_total - observed_total)) / horizon_total
    )
    return {
        "exposure_class": klass,
        "lower_pct": lower,
        "upper_pct": upper,
        "width_pct": round_percent(upper - lower),
        "point_identified": klass == EXPOSURE_FULL,
    }


def _sign(lower: float, upper: float) -> str:
    if upper < 0.0:
        return SIGN_NEGATIVE
    if lower > 0.0:
        return SIGN_POSITIVE
    return SIGN_UNIDENTIFIED


def aggregate_bounds(bounds: list[dict[str, Any]]) -> dict[str, Any]:
    """Interval mean over episodes of one cell, in the caller's order.

    Lower and upper are averaged separately (interval arithmetic for a mean is
    exact because the mean is linear), then each is rounded.  The result is a
    point only when every input was a point.  ``level_sd_pct`` is defined only
    in that case; otherwise it is ``None`` with a reason rather than a midpoint
    guess.
    """
    if not bounds:
        raise ExposureIdentificationError("aggregate requires at least one bound")
    lowers = [float(item["lower_pct"]) for item in bounds]
    uppers = [float(item["upper_pct"]) for item in bounds]
    lower = round_percent(ordered_mean(lowers))
    upper = round_percent(ordered_mean(uppers))
    if upper < lower:
        raise ExposureIdentificationError("aggregate upper fell below lower")
    all_point = all(bool(item.get("point_identified", item["lower_pct"] == item["upper_pct"])) for item in bounds)
    if all_point and lower != upper:
        raise ExposureIdentificationError("point inputs cannot produce an interval mean")
    level_sd: float | None
    reason: str | None
    if all_point and len(lowers) >= 2:
        level_sd = round_percent(ordered_sample_sd(lowers))
        reason = None
    elif all_point:
        level_sd = None
        reason = "SINGLE_VALUE_NO_SD"
    else:
        level_sd = None
        reason = "BLOCKED_CENSORED_EPISODES_NO_POINT_VALUES"
    return {
        "lower_pct": lower,
        "upper_pct": upper,
        "width_pct": round_percent(upper - lower),
        "point_identified": all_point,
        "count": len(bounds),
        "point_identified_count": sum(1 for item in bounds if item.get("point_identified", item["lower_pct"] == item["upper_pct"])),
        "level_sd_pct": level_sd,
        "level_sd_reason": reason,
    }


def paired_difference_pp(candidate: dict[str, Any], reference: dict[str, Any]) -> dict[str, Any]:
    """Candidate minus reference as an interval, in percentage points.

    ``[c_lo - r_hi, c_hi - r_lo]`` is the sharp bound on a difference of two
    quantities each known only to lie in an interval.  Sign is identified only
    when the whole interval is on one side of zero.
    """
    lower = round_percent(float(candidate["lower_pct"]) - float(reference["upper_pct"]))
    upper = round_percent(float(candidate["upper_pct"]) - float(reference["lower_pct"]))
    if upper < lower:
        raise ExposureIdentificationError("paired difference upper fell below lower")
    point = bool(candidate.get("point_identified")) and bool(reference.get("point_identified"))
    return {
        "lower_pp": lower,
        "upper_pp": upper,
        "width_pp": round_percent(upper - lower),
        "point_identified": point,
        "sign": _sign(lower, upper),
    }


def method_level_pp(differences: list[dict[str, Any]], *, expected_denominator: int, forbidden_denominators: tuple[int, ...] | list[int] = ()) -> dict[str, Any]:
    """Interval mean of per-replicate differences; denominator is enforced.

    ``expected_denominator`` is the number of independent replicates.  Any
    other denominator, and any denominator listed as forbidden (episode
    counts), is refused: the analysis unit is the replicate, full stop.
    """
    denominator = len(differences)
    if denominator != expected_denominator:
        raise ExposureIdentificationError(
            f"method-level denominator {denominator} != expected {expected_denominator}"
        )
    if denominator in set(int(item) for item in forbidden_denominators):
        raise ExposureIdentificationError(f"denominator {denominator} is a forbidden episode-level denominator")
    lowers = [float(item["lower_pp"]) for item in differences]
    uppers = [float(item["upper_pp"]) for item in differences]
    theta_lower = round_percent(ordered_mean(lowers))
    theta_upper = round_percent(ordered_mean(uppers))
    if theta_upper < theta_lower:
        raise ExposureIdentificationError("method-level upper fell below lower")
    all_point = all(bool(item["point_identified"]) for item in differences)
    between_sd: float | None
    between_reason: str | None
    if all_point and denominator >= 2:
        between_sd = round_percent(ordered_sample_sd(lowers))
        between_reason = None
    else:
        between_sd = None
        between_reason = "BLOCKED_PARTIALLY_IDENTIFIED_REPLICATE_DIFFERENCES" if not all_point else "SINGLE_REPLICATE_NO_SD"
    return {
        "analysis_unit": "TRAINING_REPLICATE",
        "method_level_n": denominator,
        "theta_bound_pp": {
            "lower_pp": theta_lower,
            "upper_pp": theta_upper,
            "width_pp": round_percent(theta_upper - theta_lower),
        },
        "sign": _sign(theta_lower, theta_upper),
        "sign_identified_replicate_count": sum(1 for item in differences if item["sign"] in (SIGN_NEGATIVE, SIGN_POSITIVE)),
        "point_identified": all_point,
        "between_replicate_sd_pp": between_sd,
        "between_replicate_sd_reason": between_reason,
    }


def naive_method_level_pp(
    replicate_naive_means_pp: list[float],
    *,
    t_critical: float,
    expected_denominator: int,
    forbidden_denominators: tuple[int, ...] | list[int] = (),
) -> dict[str, Any]:
    """What a per-step average would report: a point, an SD and a t-interval.

    This is deliberately implemented so that its answer can be placed next to
    :func:`method_level_pp`.  It is the estimator under test, not an estimator
    this module endorses -- but even the estimator under test is denied an
    episode-level denominator, so that the comparison isolates censoring from
    pseudo-replication.
    """
    denominator = len(replicate_naive_means_pp)
    if denominator != expected_denominator:
        raise ExposureIdentificationError(
            f"naive method-level denominator {denominator} != expected {expected_denominator}"
        )
    if denominator in set(int(item) for item in forbidden_denominators):
        raise ExposureIdentificationError(f"denominator {denominator} is a forbidden episode-level denominator")
    if denominator < 2:
        raise ExposureIdentificationError("naive t-interval requires at least two replicates")
    values = [float(item) for item in replicate_naive_means_pp]
    mean = round_percent(ordered_mean(values))
    sd = round_percent(ordered_sample_sd(values))
    half_width = round_percent(t_critical * sd / math.sqrt(denominator))
    lower = round_percent(mean - half_width)
    upper = round_percent(mean + half_width)
    return {
        "estimator": "NAIVE_PER_STEP_RATE",
        "method_level_n": denominator,
        "mean_pp": mean,
        "sd_pp": sd,
        "t_critical": t_critical,
        "t_interval_pp": {"lower_pp": lower, "upper_pp": upper},
        "asserts_direction": lower > 0.0 or upper < 0.0,
        "asserted_sign": SIGN_POSITIVE if lower > 0.0 else SIGN_NEGATIVE if upper < 0.0 else SIGN_UNIDENTIFIED,
    }


def compare_naive_to_bound(naive: dict[str, Any], bound: dict[str, Any]) -> dict[str, Any]:
    """Classify agreement between the naive t-interval and the identification bound."""
    naive_asserts = bool(naive["asserts_direction"])
    bound_sign = bound["sign"]
    bound_identified = bound_sign in (SIGN_NEGATIVE, SIGN_POSITIVE)
    if naive_asserts and not bound_identified:
        outcome = "NAIVE_ASSERTS_DIRECTION_BOUND_CONTAINS_ZERO"
    elif naive_asserts and bound_identified:
        outcome = "BOTH_IDENTIFIED_SAME_SIGN" if naive["asserted_sign"] == bound_sign else "BOTH_IDENTIFIED_OPPOSITE_SIGN"
    elif not naive_asserts and bound_identified:
        outcome = "BOUND_IDENTIFIED_NAIVE_UNCERTAIN"
    else:
        outcome = "NEITHER_IDENTIFIED"
    return {
        "naive_asserts_direction": naive_asserts,
        "naive_asserted_sign": naive["asserted_sign"],
        "bound_sign": bound_sign,
        "outcome": outcome,
    }

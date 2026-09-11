"""Confidence intervals quoted by the verification and label reports.

Three small pieces of arithmetic, kept in one place so that every report computes an
interval the same way and none of them needs a statistics library:

* :func:`wilson_interval` for a proportion, such as a detection rate over CARE's 45
  anomalous datasets. Wilson rather than the normal approximation, which misbehaves at
  the small counts and extreme rates a dataset-level probe produces.
* :func:`poisson_interval` for an event count; a rate per turbine-year follows by
  dividing both ends by the exposure. Byar's approximation to the exact (Garwood)
  interval, within a fraction of a percent of it from a count of one up.
* :func:`rate_ratio_interval` for the ratio of two such rates, on the log scale.
* :func:`mantel_haenszel_rate_ratio` for that ratio pooled over strata -- calendar months,
  in the core-channel rule -- so that two groups are compared only where both have
  exposure.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

#: The two-sided 95% normal quantile.
Z95 = 1.959963984540054


def wilson_interval(successes: int, trials: int, z: float = Z95) -> tuple[float, float]:
    """The Wilson score interval for a binomial proportion.

    Args:
        successes: Trials that succeeded.
        trials: Trials in all.
        z: Normal quantile of the interval.

    Returns:
        Lower and upper bound, inside ``[0, 1]``.

    Raises:
        ValueError: If there are no trials or the successes are outside ``[0, trials]``.
    """
    if trials <= 0:
        raise ValueError(f"a proportion needs at least one trial, got {trials}")
    if not 0 <= successes <= trials:
        raise ValueError(f"{successes} successes is outside [0, {trials}]")
    share = successes / trials
    z2 = z * z
    denominator = 1.0 + z2 / trials
    centre = (share + z2 / (2 * trials)) / denominator
    half = z * math.sqrt(share * (1 - share) / trials + z2 / (4 * trials * trials)) / denominator
    return max(0.0, centre - half), min(1.0, centre + half)


def poisson_interval(count: int, z: float = Z95) -> tuple[float, float]:
    """Byar's approximation to the exact interval for a Poisson count.

    Args:
        count: Events observed.
        z: Normal quantile of the interval.

    Returns:
        Lower and upper bound on the expected count.

    Raises:
        ValueError: If the count is negative.
    """
    if count < 0:
        raise ValueError(f"a count cannot be negative, got {count}")
    lower = 0.0 if count == 0 else count * (1 - 1 / (9 * count) - z / (3 * math.sqrt(count))) ** 3
    upper = (count + 1) * (1 - 1 / (9 * (count + 1)) + z / (3 * math.sqrt(count + 1))) ** 3
    return lower, upper


def rate_ratio_interval(
    count_a: int, exposure_a: float, count_b: int, exposure_b: float, z: float = Z95
) -> tuple[float, float, float]:
    """The ratio of two Poisson rates, with a log-normal interval.

    Args:
        count_a: Events in the first group.
        exposure_a: Exposure of the first group, for example turbine-years.
        count_b: Events in the second group.
        exposure_b: Exposure of the second group.
        z: Normal quantile of the interval.

    Returns:
        The ratio of the first rate to the second, and its lower and upper bound; all
        ``nan`` when either count or exposure is zero.
    """
    if min(count_a, count_b) <= 0 or min(exposure_a, exposure_b) <= 0:
        return math.nan, math.nan, math.nan
    ratio = (count_a / exposure_a) / (count_b / exposure_b)
    spread = z * math.sqrt(1 / count_a + 1 / count_b)
    return ratio, ratio * math.exp(-spread), ratio * math.exp(spread)


def mantel_haenszel_rate_ratio(
    strata: Sequence[tuple[int, float, int, float]], z: float = Z95
) -> tuple[float, float, float]:
    """The Mantel-Haenszel ratio of two Poisson rates pooled over strata, with an interval.

    Each stratum weighs the first group's events against the second's by how much exposure
    the stratum holds on both sides, so a group concentrated in one season is compared
    with the same season elsewhere, and a stratum with exposure on one side only adds
    nothing. The interval is log-normal with the Greenland-Robins variance, which reduces
    to that of :func:`rate_ratio_interval` for a single stratum.

    Args:
        strata: One ``(count_a, exposure_a, count_b, exposure_b)`` per stratum.
        z: Normal quantile of the interval.

    Returns:
        The pooled ratio of the first rate to the second, and its lower and upper bound;
        all ``nan`` when either group has no events in the strata both sides share.
    """
    numerator = denominator = variance = 0.0
    for count_a, exposure_a, count_b, exposure_b in strata:
        if exposure_a <= 0 or exposure_b <= 0:
            continue
        total = exposure_a + exposure_b
        numerator += count_a * exposure_b / total
        denominator += count_b * exposure_a / total
        variance += exposure_a * exposure_b * (count_a + count_b) / (total * total)
    if numerator <= 0 or denominator <= 0:
        return math.nan, math.nan, math.nan
    ratio = numerator / denominator
    spread = z * math.sqrt(variance / (numerator * denominator))
    return ratio, ratio * math.exp(-spread), ratio * math.exp(spread)

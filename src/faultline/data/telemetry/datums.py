"""Harmonising reporting datums across sites, after the plausibility bounds (ADR-0012).

Datums are conventions and are harmonised across sites. Physics is not harmonised;
differences in physics between sites are what the held-out evaluation measures.

A *datum* is where a provider decides zero is. Two machines in the same operating state
can report different numbers because their control systems were commissioned against
different references: Senvion reports fine pitch as a hard exact ``0.0``, Siemens as a
continuous band centred on ``-1.0``. That difference says nothing about either machine.
Left alone it reaches the tokenizer as a distribution shift, and the model reads the
held-out site's commonest operating state as one the training split almost never shows.

So this module exists, and nothing else does. It is deliberately small and deliberately
*not* a place for corrections:

* **It is declared, per channel, in the telemetry configuration** -- never per source.
  A datum rule that names a site is a correction fitted to that site, and fitting to the
  held-out site is what the pre-registered protocol forbids. A rule here is site-agnostic
  and applies everywhere, however large or small its effect turns out to be at each site.
* **It runs after the plausibility bounds**, never before. A bound says a value is not a
  reading at all; a datum says a reading is expressed against a different zero. A pitch
  angle of -40 degrees is out of bounds and becomes ``NaN`` in the cleaning stage; the
  floor below must not rescue it to 0 and present an instrument failure as fine pitch.
  That ordering is why this is not in :mod:`faultline.data.telemetry.clean`.
* **Missing stays missing.** A floor never fills a gap; ``NaN`` in is ``NaN`` out.

:mod:`faultline.data.telemetry.harmonise` is the *event* rule -- one event definition for
every site. This is its telemetry counterpart for channel values, and the two are separate
because they harmonise different things.
"""

from __future__ import annotations

import pandas as pd

from faultline.config import StrictModel
from faultline.logging_utils import get_logger

logger = get_logger(__name__)


class DatumSpec(StrictModel):
    """One channel's datum harmonisation, with the evidence for it.

    Attributes:
        floor: Values below this are raised to it, at every source. ``None`` leaves the
            channel alone.
        reason: Why the datum differs between providers, and what measured it. Required,
            because a datum rule with no evidence is indistinguishable from a correction
            someone preferred.
    """

    floor: float | None = None
    reason: str = ""


def apply_datums(
    frame: pd.DataFrame, datums: dict[str, DatumSpec]
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Harmonise the declared channels' datums, counting the values each rule moves.

    Args:
        frame: Wide telemetry table, already bounded.
        datums: Per channel, the rule in force. A channel absent from the table is
            skipped, as a provider dropping a signal is normal.

    Returns:
        The harmonised table, and per channel the number of values the rule moved.
        A value already ``NaN`` is never moved and never counted.
    """
    result = frame.copy()
    moved: dict[str, int] = {}
    for channel, spec in datums.items():
        if channel not in result.columns or spec.floor is None:
            continue
        values = pd.to_numeric(result[channel], errors="coerce")
        below = values < spec.floor
        count = int(below.sum())
        if count:
            logger.info(
                "channel %s: %d values raised to the datum floor %g", channel, count, spec.floor
            )
        moved[channel] = count
        result[channel] = values.mask(below, spec.floor)
    return result, moved

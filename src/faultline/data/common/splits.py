"""Site and time split assignment.

The evaluation endpoint is performance *under shift*, so splits are never random.
Two axes are encoded here: whole sites held out (leave-wind-farm-out) and a temporal
cut inside the training sites (drift). The assignment is a pure function of
``(site, timestamp)`` and a configuration, so a split can be reproduced from the
YAML alone without touching the data.

The split specification is also where two rules are enforced rather than merely
written down.

**An evaluation that holds a whole site out may read core channels only.** An
extended channel is one that is not published by every training site, so a
leave-site-out score that depends on it is partly a measurement of instrumentation
differences between sites, which is not the quantity the project reports. The check
runs at configuration-validation time, before any data is read.

**A source listed in ``eval_only_sources`` never lands in train or val.** This one is
a licence constraint, not a modelling preference: CARE is CC BY-SA 4.0, and whether
model weights trained on share-alike data are adapted material is genuinely
unsettled (``docs/DATA_LICENSES.md``, ADR-0004). The project's answer is to not need
the answer -- CARE is used for evaluation and label cross-check only. That is worth
nothing as a sentence in a document, so it is applied last in :func:`assign_splits`,
after the site and time axes, and it overrides both.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pandas as pd
from pydantic import Field, model_validator

from faultline.config import StrictModel
from faultline.data.telemetry.channels import derive_core, load_channel_maps
from faultline.data.telemetry.schemas import CHANNELS_BY_NAME, CORE_CHANNELS

Split = Literal["train", "val", "test"]
SPLITS: tuple[Split, ...] = ("train", "val", "test")


class TimeSplitSpec(StrictModel):
    """The temporal cut applied inside the training sites.

    Attributes:
        train_until: Last timestamp assigned to ``train`` (inclusive).
        val_until: Last timestamp assigned to ``val`` (inclusive); must be later
            than ``train_until``.
    """

    train_until: datetime
    val_until: datetime

    @model_validator(mode="after")
    def _ordered(self) -> TimeSplitSpec:
        """Reject a validation cut that does not follow the training cut."""
        if self.val_until <= self.train_until:
            raise ValueError("time.val_until must be strictly after time.train_until")
        return self


class SplitsConfig(StrictModel):
    """Specification of one split of the corpus.

    Attributes:
        version: Version of this split specification.
        seed: Seed reserved for any future randomized tie-breaking; unused today.
        site_column: Column naming the site.
        time_column: Column holding the UTC timestamp.
        holdout_sites: Sites removed from training entirely.
        holdout_site_split: Split label given to every row of a held-out site.
        time: Temporal cut applied to the remaining sites.
        late_period_split: Split label for training-site rows after ``val_until``.
        eval_channels: Canonical channels the evaluation reads. When any site is
            held out, every name here must be a ``core`` channel.
        source_column: Column naming the source a row came from.
        eval_only_sources: Sources that may never enter training or validation.
            Every row of such a source is labelled ``test``, whatever the site and
            time axes say. This is a licence constraint (ADR-0004), not a tunable.
    """

    version: int = 0
    seed: int = 20260909
    site_column: str = "site"
    time_column: str = "timestamp_utc"
    holdout_sites: list[str] = Field(default_factory=list)
    holdout_site_split: Split = "test"
    time: TimeSplitSpec
    late_period_split: Split = "test"
    eval_channels: list[str] = Field(default_factory=list)
    source_column: str = "source"
    eval_only_sources: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _leave_site_out_reads_core_channels_only(self) -> SplitsConfig:
        """Reject an extended channel in a configuration that holds a site out.

        Raises:
            ValueError: If ``eval_channels`` names something that is not a canonical
                channel, or names an ``extended`` channel while ``holdout_sites`` is
                non-empty.
        """
        unknown = [name for name in self.eval_channels if name not in CHANNELS_BY_NAME]
        if unknown:
            raise ValueError(
                f"eval_channels names {unknown}, which are not canonical channels. "
                "A typo must fail here rather than silently escape the core-only rule."
            )
        if not self.holdout_sites:
            return self
        extended = [name for name in self.eval_channels if CHANNELS_BY_NAME[name].tier != "core"]
        if extended:
            raise ValueError(
                f"holdout_sites is set, so this is a leave-site-out evaluation, but "
                f"eval_channels names extended channels {extended}. An extended "
                "channel is not published by every training site, so a held-out-site "
                "score that depends on it partly measures instrumentation differences "
                f"rather than transfer. Core channels: {', '.join(CORE_CHANNELS)}."
            )
        return self


def check_eval_channels_against_maps(
    config: SplitsConfig, configs_dir: Path, sources: Sequence[str]
) -> list[str]:
    """Check a leave-site-out evaluation's channels against the resolved channel maps.

    The validator on :class:`SplitsConfig` checks ``eval_channels`` against the tiers
    ``schemas.py`` declares. A declaration is only as good as the evidence behind it,
    so this derives the core set from the channel maps themselves -- resolved at every
    training source and at every held-out source -- and checks against that. The two
    agree today; this is what notices the day they do not.

    Args:
        config: Split specification.
        configs_dir: The repository ``configs`` directory.
        sources: Every source with a channel map; training sources are those neither
            held out nor evaluation-only.

    Returns:
        The derived core set, empty when no site is held out.

    Raises:
        KeyError: If a held-out site names no source with a channel map.
        ValueError: If an evaluation channel is not core on the maps.
    """
    if not config.holdout_sites:
        return []
    unknown = [site for site in config.holdout_sites if site not in sources]
    if unknown:
        raise KeyError(
            f"holdout_sites {unknown} name no source with a channel map ({', '.join(sources)}); "
            "the leave-site-out rule cannot be checked, and a held-out site that matches "
            "nothing leaves that site in the training data"
        )
    training = [
        source
        for source in sources
        if source not in config.holdout_sites and source not in config.eval_only_sources
    ]
    maps = load_channel_maps(configs_dir, [*training, *config.holdout_sites])
    core, _ = derive_core(maps, training, config.holdout_sites)
    outside = [channel for channel in config.eval_channels if channel not in core]
    if outside:
        raise ValueError(
            f"eval_channels names {outside}, which the resolved channel maps do not show at "
            f"every training site ({', '.join(training)}) and at the held-out site "
            f"({', '.join(config.holdout_sites)}). Core on the maps: {', '.join(core)}."
        )
    return core


def _as_utc(value: datetime) -> pd.Timestamp:
    """Coerce a configured datetime to a UTC-aware pandas timestamp.

    A naive value in the YAML is interpreted as UTC rather than local time, so the
    same configuration cuts the corpus identically on every machine.

    Args:
        value: Timestamp from the split configuration.

    Returns:
        The equivalent UTC-aware timestamp.
    """
    stamp = pd.Timestamp(value)
    return stamp.tz_localize("UTC") if stamp.tzinfo is None else stamp.tz_convert("UTC")


def assign_splits(frame: pd.DataFrame, config: SplitsConfig) -> pd.Series[Any]:
    """Assign a split label to every row of a table.

    Three rules, applied in strengthening order. Rows are first cut by timestamp: up
    to ``train_until`` is ``train``, up to ``val_until`` is ``val``, anything later
    takes ``late_period_split``. Rows belonging to a held-out site then take
    ``holdout_site_split`` regardless of time, so the site axis dominates the time
    axis. Finally, rows from an evaluation-only source are forced to ``test``,
    overriding both.

    Args:
        frame: Table containing the site and timestamp columns named by ``config``,
            and the source column when ``eval_only_sources`` is configured.
        config: Split specification.

    Returns:
        A string Series of split labels aligned with ``frame.index``.

    Raises:
        KeyError: If a configured column the specification needs is missing. In
            particular, a missing source column with ``eval_only_sources`` set is
            fatal: the alternative is silently not applying a licence constraint.
    """
    for column in (config.site_column, config.time_column):
        if column not in frame.columns:
            raise KeyError(f"column {column!r} required by the split spec is missing")
    if config.eval_only_sources and config.source_column not in frame.columns:
        raise KeyError(
            f"column {config.source_column!r} is missing, so eval_only_sources "
            f"{config.eval_only_sources} cannot be enforced. This is a licence "
            "constraint (ADR-0004, docs/DATA_LICENSES.md) and is not skipped quietly."
        )

    stamps = pd.to_datetime(frame[config.time_column], utc=True)
    train_until = _as_utc(config.time.train_until)
    val_until = _as_utc(config.time.val_until)

    labels = np.full(len(frame), config.late_period_split, dtype=object)
    labels[(stamps <= train_until).to_numpy()] = "train"
    labels[((stamps > train_until) & (stamps <= val_until)).to_numpy()] = "val"

    if config.holdout_sites:
        held_out = frame[config.site_column].astype(str).isin(config.holdout_sites).to_numpy()
        labels[held_out] = config.holdout_site_split
        # The v0 failure mode, made loud: a site rule that does not match the held-out
        # source's rows leaves that source in training without a word. The adapters write
        # the source id verbatim, so where the frame carries it, it is the check.
        if config.source_column in frame.columns and config.source_column != config.site_column:
            from_holdout = (
                frame[config.source_column].astype(str).isin(config.holdout_sites).to_numpy()
            )
            missed = from_holdout & ~held_out
            if missed.any():
                sites = sorted(frame.loc[missed, config.site_column].astype(str).unique())
                raise ValueError(
                    f"{int(missed.sum())} rows come from held-out source(s) "
                    f"{sorted(frame.loc[missed, config.source_column].astype(str).unique())} "
                    f"but the site rule on column {config.site_column!r} does not match them "
                    f"(it reads {sites}); they would be left in training"
                )

    # Applied last, and not configurable: an evaluation-only source is test, whatever
    # the axes above decided. See docs/DATA_LICENSES.md.
    if config.eval_only_sources:
        restricted = (
            frame[config.source_column].astype(str).isin(config.eval_only_sources).to_numpy()
        )
        labels[restricted] = "test"

    return pd.Series(labels, index=frame.index, name="split", dtype="object")


def split_counts(labels: pd.Series[Any]) -> dict[str, int]:
    """Count rows per split, always reporting all three labels.

    Args:
        labels: Split labels produced by :func:`assign_splits`.

    Returns:
        A mapping from split name to row count, including zeros.
    """
    counts = labels.value_counts().to_dict()
    return {split: int(counts.get(split, 0)) for split in SPLITS}

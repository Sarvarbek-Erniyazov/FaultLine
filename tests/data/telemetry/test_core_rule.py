"""The core channel rule (M1b step 10), on synthetic tables."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from faultline.data.common.splits import TrainingExclusion
from faultline.data.telemetry.core_rule import (
    ChannelVerdict,
    MatchedRatio,
    OutageTally,
    matched_ratio,
    month_window,
    read_ratio,
    seasonal_control,
    shares,
    site_days,
    span_window,
)
from faultline.data.telemetry.harmonise import to_seconds
from faultline.data.telemetry.labels import STEPS_PER_YEAR
from faultline.data.telemetry.pipeline import stage_source_dir
from faultline.paths import ProjectPaths

CHANNELS = ["ambient_temp_c", "nacelle_temp_c"]


def outage(start: str, end: str, channels: list[str] | None = None) -> TrainingExclusion:
    return TrainingExclusion(
        source="penmanshiel",
        start=pd.Timestamp(start).to_pydatetime(),
        end=pd.Timestamp(end).to_pydatetime(),
        channels=channels or CHANNELS,
        reason="site-wide outage",
    )


# -- reading a ratio ------------------------------------------------------------------------


def test_a_ratio_is_read_by_the_rule_fixed_in_advance() -> None:
    assert read_ratio(0.93, 0.82, 1.06) == "clears"
    assert read_ratio(0.24, 0.14, 0.43) == "does not clear"
    assert read_ratio(1.6, 1.1, 2.3) == "does not clear"
    # contains 1, but cannot rule out a halving
    assert read_ratio(0.49, 0.22, 1.09) == "inconclusive"
    assert read_ratio(float("nan"), float("nan"), float("nan")) == "no events"


# -- the turbine-day table ----------------------------------------------------------------


def test_a_turbine_day_table_counts_steps_gaps_labels_and_events_inside_and_outside(
    repo_paths: ProjectPaths,
) -> None:
    source = "penmanshiel"
    cleaned = stage_source_dir(repo_paths, "cleaned", source)
    (cleaned / "labels").mkdir(parents=True, exist_ok=True)
    stamps = pd.date_range("2018-02-28", periods=432, freq="10min", tz="UTC")  # 3 days
    out = (stamps >= "2018-03-01") & (stamps < "2018-03-02")
    temperature = np.where(out, np.nan, 5.0)
    pd.DataFrame(
        {
            "source": source,
            "site": "Penmanshiel",
            "turbine_id": "P01",
            "timestamp_utc": stamps,
            "wind_speed_ms": 7.0,
            "ambient_temp_c": temperature,
            "nacelle_temp_c": temperature,
        }
    ).to_parquet(cleaned / "P01__2018.parquet", index=False)
    label = pd.array([True] * 10 + [False] * 422, dtype="boolean")
    pd.DataFrame({"timestamp_utc": stamps, "narrow_within_24h": label}).to_parquet(
        cleaned / "labels" / "P01__2018.parquet", index=False
    )
    pd.DataFrame(
        {
            "turbine_id": ["P01", "P01", "P01"],
            "start_utc": pd.to_datetime(
                ["2018-02-28T12:00Z", "2018-03-01T06:00Z", "2018-03-09T00:00Z"], utc=True
            ),
            "in_grid": [True, True, False],
        }
    ).to_parquet(cleaned / "labels" / "events_narrow.parquet", index=False)

    span = outage("2018-03-01T00:00Z", "2018-03-01T23:50Z")
    days, (tally,) = site_days(repo_paths, source, CHANNELS, "narrow_within_24h", [span])

    assert days["steps"].tolist() == [144, 144, 144]
    assert days["kept"].tolist() == [144, 0, 144]
    assert days["missing:ambient_temp_c"].tolist() == [0, 144, 0]
    assert days["missing_kept:ambient_temp_c"].tolist() == [0, 0, 0]
    assert days["events"].tolist() == [1, 1, 0]
    assert days["events_kept"].tolist() == [1, 0, 0]
    assert (int(days["known"].sum()), int(days["positive"].sum())) == (432, 10)
    assert shares(days, CHANNELS)["ambient_temp_c"] == pytest.approx(288 / 432)
    assert shares(days, CHANNELS, kept=True)["ambient_temp_c"] == 1.0

    assert tally.steps == 144
    assert tally.turbine_shares == {"P01": 1.0}
    assert tally.edge_shares == (1.0, 1.0)
    assert tally.holds(turbines=1) == {
        "several": True,
        "site-wide": True,
        "simultaneous": True,
        "bounded": True,
    }
    # a second turbine that never reports in the span makes it not site-wide
    assert not tally.holds(turbines=2)["site-wide"]


def test_a_gap_that_began_before_the_span_is_an_era_not_an_outage() -> None:
    span = outage("2018-03-01T00:00Z", "2018-03-10T00:00Z")
    stamps = pd.Series(pd.date_range("2018-02-20", "2018-03-20", freq="10min", tz="UTC"))
    seconds = to_seconds(stamps)
    before_end = (stamps <= "2018-03-10T00:00Z").to_numpy()
    present = {"ambient_temp_c": ~before_end, "nacelle_temp_c": ~before_end}
    tally = OutageTally(span)
    tally.add("P01", seconds, np.ones(len(seconds), dtype=bool), present)
    before, after = tally.edge_shares
    assert (before, after) == (0.0, 1.0)
    holds = tally.holds(turbines=1)
    assert holds["simultaneous"]
    assert not holds["bounded"]


# -- the seasonal control and the matched ratio ------------------------------------------------


def day_rows(days: pd.DatetimeIndex, events: list[int], affected: list[bool]) -> pd.DataFrame:
    frame = pd.DataFrame({"turbine_id": "P01", "day": days})
    frame["steps"] = frame["kept"] = frame["reporting"] = frame["reporting_kept"] = 144
    frame["known"] = 144
    frame["positive"] = np.array(events) * 10
    frame["events"] = frame["events_kept"] = events
    gap = np.where(affected, 144, 0)
    frame["missing:ambient_temp_c"] = frame["missing_kept:ambient_temp_c"] = gap
    return frame


def seasons() -> pd.DataFrame:
    """Two years: January busy, July quiet. July 2017 is missing the channel."""
    parts = []
    for year in (2017, 2018):
        january = pd.date_range(f"{year}-01-01", periods=31, freq="D", tz="UTC")
        july = pd.date_range(f"{year}-07-01", periods=31, freq="D", tz="UTC")
        parts.append(day_rows(january, [1] * 31, [False] * 31))
        quiet = [1 if i % 10 == 0 else 0 for i in range(31)]
        parts.append(day_rows(july, quiet, [year == 2017] * 31))
    return pd.concat(parts, ignore_index=True)


def test_a_gap_in_a_quiet_season_looks_safe_crude_and_neutral_matched() -> None:
    result = matched_ratio(
        seasons(), "penmanshiel", "ambient_temp_c", pd.Timestamp("2020-12-31T23:59:59Z")
    )
    assert result.affected_days == 31
    assert result.crude[0] < 0.5
    assert result.matched[0] == pytest.approx(1.0)
    assert result.months == (7,)
    # four events a side cannot rule out a halving
    assert result.verdict == "inconclusive"


def test_a_seasonal_control_sets_one_window_against_the_same_window_elsewhere() -> None:
    days = seasons()
    control = seasonal_control(
        days, month_window(days, (7,)), "penmanshiel", "Jul", 2017, [2017, 2018]
    )
    assert [(row.year, row.events) for row in control.rows] == [(2017, 4), (2018, 4)]
    assert control.control.events == 4
    assert control.ratio[0] == pytest.approx(1.0)
    assert control.tested.turbine_years == pytest.approx(31 * 144 / STEPS_PER_YEAR)


def test_a_span_window_is_its_calendar_days_in_every_year() -> None:
    days = seasons()
    window = span_window(days, [outage("2017-07-05T10:00Z", "2017-07-06T02:00Z")])
    chosen = pd.DatetimeIndex(days.loc[window, "day"])
    assert [f"{d:%Y-%m-%d}" for d in chosen] == [
        "2017-07-05",
        "2017-07-06",
        "2018-07-05",
        "2018-07-06",
    ]


# -- the verdict per channel ---------------------------------------------------------------


def verdict(**overrides: object) -> ChannelVerdict:
    fields: dict[str, object] = {
        "channel": "pitch_angle_deg",
        "mappable": True,
        "held_out": {"hill_of_towie": 0.996},
        "held_out_years": {"hill_of_towie": {2019: 0.997, 2023: 0.995}},
        "training": {"kelmarsh": 0.952, "penmanshiel": 0.700},
        "training_kept": {"kelmarsh": 0.952, "penmanshiel": 0.719},
        "shortcut": {},
    }
    fields.update(overrides)
    return ChannelVerdict(**fields)  # type: ignore[arg-type]


def ratio(matched: tuple[float, float, float]) -> MatchedRatio:
    return MatchedRatio(
        source="penmanshiel",
        channel="pitch_angle_deg",
        kept=True,
        affected_days=100,
        affected=(10, 1.0),
        unaffected=(10, 1.0),
        crude=matched,
        matched=matched,
        months=(1,),
    )


def test_a_channel_below_the_threshold_at_one_training_site_is_core_if_its_control_clears() -> None:
    passes = verdict(shortcut={"penmanshiel": ratio((0.95, 0.83, 1.09))})
    assert (passes.tier, passes.reason) == ("core", "all hold")
    fails = verdict(shortcut={"penmanshiel": ratio((0.44, 0.22, 0.88))})
    assert (fails.tier, fails.reason) == ("extended", "(c)")


def test_a_held_out_year_without_the_channel_fails_integrity() -> None:
    wind = verdict(
        channel="wind_direction_deg",
        held_out={"hill_of_towie": 0.498},
        held_out_years={"hill_of_towie": {2019: 0.0, 2023: 0.995}},
    )
    assert (wind.tier, wind.reason) == ("extended", "(a)")
    # the pooled share alone can pass while a year fails
    one_year = verdict(held_out_years={"hill_of_towie": {2019: 0.90, 2023: 0.999}})
    assert not one_year.integrity


def test_sufficiency_needs_one_site_at_the_threshold_and_every_site_above_zero() -> None:
    assert verdict(training_kept={"kelmarsh": 0.94, "penmanshiel": 0.94}).reason == "(b)"
    assert verdict(training_kept={"kelmarsh": 0.99, "penmanshiel": 0.0}).reason == "(b)"
    assert verdict(mappable=False).reason == "maps"

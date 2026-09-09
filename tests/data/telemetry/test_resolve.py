"""Resolving the power unit and the timezone from measured data.

Every case here is synthetic or reads the committed Kelmarsh excerpt. Nothing
touches the staged archives, so the suite still runs without any data present.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from faultline.data.telemetry.adapters.base import RawMember, read_csv_member_columns
from faultline.data.telemetry.resolve import (
    PowerScaleRow,
    TimezoneRow,
    affected_local_window,
    dst_transitions,
    judge_power_scale,
    judge_timezone,
    timezone_row,
)

LONDON = "Europe/London"
STEP = timedelta(minutes=10)


def utc_year(year: int) -> pd.Series:
    """A full year of 10-minute labels as published in UTC."""
    index = pd.date_range(f"{year}-01-01", f"{year + 1}-01-01", freq="10min", inclusive="left")
    return pd.Series(index)


def local_year(year: int, zone: str = LONDON) -> pd.Series:
    """The same year of instants, but labelled in local civil time.

    Built by converting the UTC instants into the zone and dropping the offset,
    which is exactly what an exporter writing local timestamps produces: the
    spring-forward hour never appears and the fall-back hour appears twice.
    """
    index = pd.date_range(
        f"{year}-01-01", f"{year + 1}-01-01", freq="10min", inclusive="left", tz="UTC"
    )
    return pd.Series(index.tz_convert(zone).tz_localize(None))


# -- transitions ---------------------------------------------------------------------


def test_dst_transitions_match_the_tz_database() -> None:
    spring, autumn = dst_transitions(2016, LONDON) or (None, None)
    assert spring == datetime(2016, 3, 27, 1, tzinfo=ZoneInfo("UTC"))
    assert autumn == datetime(2016, 10, 30, 1, tzinfo=ZoneInfo("UTC"))


def test_a_zone_without_transitions_has_none() -> None:
    assert dst_transitions(2016, "UTC") is None


def test_affected_window_is_expressed_in_local_labels() -> None:
    # The labels a UK spring forward skips are 01:00-01:59 local, not 02:00-02:59:
    # the clock goes from 00:59 GMT to 02:00 BST.
    spring, autumn = dst_transitions(2016, LONDON) or (None, None)
    assert spring is not None and autumn is not None
    assert affected_local_window(spring, LONDON) == (
        datetime(2016, 3, 27, 1),
        timedelta(hours=1),
    )
    assert affected_local_window(autumn, LONDON) == (
        datetime(2016, 10, 30, 1),
        timedelta(hours=1),
    )


# -- the fingerprint -----------------------------------------------------------------


def test_utc_labels_show_neither_half_of_the_fingerprint() -> None:
    row = timezone_row("m", "T1", utc_year(2016), LONDON)
    assert row is not None
    assert row.steps_in_spring_hour == 6  # the hour is fully populated
    assert row.repeated_steps_in_autumn_hour == 0
    assert row.duplicate_timestamps == 0


def test_local_labels_show_both_halves_of_the_fingerprint() -> None:
    row = timezone_row("m", "T1", local_year(2016), LONDON)
    assert row is not None
    assert row.steps_in_spring_hour == 0  # the hour does not exist locally
    # The autumn hour is the only repetition in an otherwise clean series, so the
    # test is applicable and finds it.
    assert row.repeated_steps_in_autumn_hour == 6
    # Those six repeats are the only duplicates in the member, which is what makes
    # the autumn half applicable here and not on the padded 2023 exports.
    assert row.duplicate_timestamps == 6


def test_the_autumn_half_is_withheld_when_a_member_repeats_timestamps() -> None:
    # A member that repeats every label -- as the Kelmarsh 2023 and 2024 exports do
    # -- cannot be tested for a fall-back, because repetition is what the test looks
    # for. The spring half still works, because it asks whether an hour is empty.
    doubled = pd.concat([utc_year(2016), utc_year(2016)], ignore_index=True)
    row = timezone_row("m", "T1", doubled, LONDON)
    assert row is not None
    assert row.repeated_steps_in_autumn_hour is None
    assert row.steps_in_spring_hour == 6
    assert row.distinct_timestamps * 2 == row.rows


def test_no_transition_in_the_year_yields_no_row() -> None:
    assert timezone_row("m", "T1", utc_year(2016), "UTC") is None


def test_empty_timestamps_yield_no_row() -> None:
    assert timezone_row("m", "T1", pd.Series([], dtype="datetime64[ns]"), LONDON) is None


# -- the timezone verdict ------------------------------------------------------------


def zone_row(spring_steps: int, autumn_repeats: int | None, duplicates: int = 0) -> TimezoneRow:
    return TimezoneRow(
        member="m",
        turbine_id="T1",
        year=2016,
        rows=52_560,
        distinct_timestamps=52_560 - duplicates,
        duplicate_timestamps=duplicates,
        spring_hour="2016-03-27 01",
        steps_in_spring_hour=spring_steps,
        autumn_hour="2016-10-30 01",
        repeated_steps_in_autumn_hour=autumn_repeats,
    )


def test_verdict_utc_when_neither_fingerprint_appears() -> None:
    verdict = judge_timezone("t", LONDON, "UTC", [zone_row(6, 0), zone_row(6, 0)])
    assert verdict.verdict == "UTC"
    assert "neither fingerprint" in verdict.rationale


def test_verdict_local_when_both_halves_appear_everywhere() -> None:
    verdict = judge_timezone("t", LONDON, "UTC", [zone_row(0, 6), zone_row(0, 6)])
    assert verdict.verdict == LONDON


def test_verdict_unresolved_when_the_years_disagree() -> None:
    verdict = judge_timezone("t", LONDON, "UTC", [zone_row(6, 0), zone_row(0, 6)])
    assert verdict.verdict == "unresolved"


def test_untestable_autumn_rows_are_counted_in_the_rationale() -> None:
    verdict = judge_timezone("t", LONDON, "UTC", [zone_row(6, 0), zone_row(6, None, duplicates=10)])
    assert verdict.verdict == "UTC"
    assert "not applicable on 1 of 2" in verdict.rationale
    assert len(verdict.duplicating_members) == 1


def test_verdict_unresolved_without_any_transition() -> None:
    assert judge_timezone("t", LONDON, "UTC", []).verdict == "unresolved"


# -- the power scale verdict ---------------------------------------------------------


def scale_row(tail: float) -> PowerScaleRow:
    return PowerScaleRow(
        member="m",
        turbine_id="T1",
        rows=52_560,
        non_null=52_000,
        tail=tail,
        maximum=tail * 1.01,
        minimum=-17.0,
        energy_tail=tail / 6,
    )


def test_a_tail_at_rated_power_reads_as_kw() -> None:
    verdict = judge_power_scale(
        "Power (kW)", "Energy Export (kWh)", 2050, 1 / 6, [scale_row(2057.3)]
    )
    assert verdict.verdict == "kW"
    assert verdict.kw_reference == 2050.0
    assert round(verdict.kwh_reference, 1) == 341.7
    assert "6.0x" in verdict.rationale


def test_a_tail_at_one_sixth_of_rated_power_reads_as_energy() -> None:
    verdict = judge_power_scale("Power", None, 2050, 1 / 6, [scale_row(340.0)])
    assert verdict.verdict == "kWh per step"


def test_a_tail_between_the_two_references_is_unresolved() -> None:
    # 850 is too small to be a rated power and too large to be a 10-minute energy
    # total. Landing between the two references means the scale test has failed, and
    # failing loudly beats picking the nearer one.
    verdict = judge_power_scale("Power", None, 2050, 1 / 6, [scale_row(850.0)])
    assert verdict.verdict == "unresolved"
    assert "not within a factor of 2" in verdict.rationale


def test_no_measurements_is_unresolved_rather_than_a_guess() -> None:
    verdict = judge_power_scale("Power", None, 2050, 1 / 6, [])
    assert verdict.verdict == "unresolved"
    assert verdict.median_tail != verdict.median_tail  # NaN


def test_an_unpublished_rating_cannot_decide_anything() -> None:
    # CARE does not publish rated power per farm; the scale test must abstain rather
    # than divide by zero and declare something.
    verdict = judge_power_scale("Power", None, 0, 1 / 6, [scale_row(2057.3)])
    assert verdict.verdict == "unresolved"


def test_the_median_tail_ignores_a_single_bad_turbine_year() -> None:
    rows = [scale_row(2050.0), scale_row(2055.0), scale_row(3.0)]
    assert judge_power_scale("Power", None, 2050, 1 / 6, rows).verdict == "kW"


# -- the streaming column reader -----------------------------------------------------


def test_read_csv_member_columns_takes_only_what_is_asked_for(fixtures_dir: Path) -> None:
    path = fixtures_dir / "telemetry" / "kelmarsh" / "Turbine_Data_Kelmarsh_1_excerpt.csv"
    member = RawMember(
        archive=path,
        name="",
        kind="scada_10min",
        size=path.stat().st_size,
        compressed_size=path.stat().st_size,
        in_archive=False,
    )
    frame = read_csv_member_columns(member, ["Date and time", "Power (kW)", "Energy Export (kWh)"])
    assert list(frame.columns) == ["Date and time", "Energy Export (kWh)", "Power (kW)"]
    assert len(frame) > 0


def test_columns_the_member_does_not_have_are_skipped_not_raised(fixtures_dir: Path) -> None:
    # A provider dropping a signal in one year is normal, and must surface as
    # absent data rather than as a crash mid-pass.
    path = fixtures_dir / "telemetry" / "kelmarsh" / "Turbine_Data_Kelmarsh_1_excerpt.csv"
    member = RawMember(
        archive=path,
        name="",
        kind="scada_10min",
        size=path.stat().st_size,
        compressed_size=path.stat().st_size,
        in_archive=False,
    )
    frame = read_csv_member_columns(member, ["Power (kW)", "Not A Column"])
    assert list(frame.columns) == ["Power (kW)"]
    assert read_csv_member_columns(member, ["Not A Column"]).empty


@pytest.mark.parametrize("year", [2016, 2019, 2023])
def test_the_fingerprint_is_computed_for_every_year_tested(year: int) -> None:
    utc = timezone_row("m", "T1", utc_year(year), LONDON)
    local = timezone_row("m", "T1", local_year(year), LONDON)
    assert utc is not None and local is not None
    assert utc.steps_in_spring_hour == 6
    assert local.steps_in_spring_hour == 0

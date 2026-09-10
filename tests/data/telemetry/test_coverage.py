"""Value ranges and missingness, on synthetic tables."""

from __future__ import annotations

import numpy as np
import pandas as pd

from faultline.data.telemetry.coverage import (
    SiteTally,
    gap_runs,
    ranges_rows,
    render_missingness,
    tally_final,
    tally_grid,
)

CORE = ["wind_speed_ms", "wind_direction_deg"]
STEPS = 150  # more than a day, so the year is printed


def test_gap_runs_are_the_lengths_of_the_missing_stretches() -> None:
    missing = np.array([False, True, True, False, True, False, True, True, True])
    assert gap_runs(missing).tolist() == [2, 1, 3]
    assert gap_runs(np.zeros(4, dtype=bool)).tolist() == []


def test_a_sentinel_shows_up_as_a_repeated_tail_value_and_is_removed_before_bounds() -> None:
    values = pd.Series([10.0] * 5000 + [323.70001220703114] * 20 + [200.0])
    row = ranges_rows(values, (-30.0, 100.0), [323.7])
    assert "323.7 x20" in str(row["repeated tail values"])
    assert row["sentinel values removed"] == 20
    assert row["outside bounds"] == 1  # the lone 200, not the code


def grid(year: int, direction: float | None) -> pd.DataFrame:
    stamps = pd.date_range(f"{year}-06-01", periods=STEPS, freq="10min", tz="UTC")
    wind = np.full(STEPS, 6.0)
    wind[1:3] = np.nan  # one two-step gap
    return pd.DataFrame(
        {
            "timestamp_utc": stamps,
            "wind_speed_ms": wind,
            "wind_direction_deg": np.full(STEPS, np.nan if direction is None else direction),
        }
    )


def test_the_held_out_year_table_shows_a_channel_missing_in_one_year() -> None:
    site = SiteTally()
    tally_grid(grid(2019, None), CORE, site)
    tally_grid(grid(2023, 180.0), CORE, site)
    # a one-row year, as the interval-start shift leaves before each staged year
    tally_grid(grid(2018, None).iloc[:1], CORE, site)
    final = grid(2023, 180.0).assign(wind_speed_ms__imputed=[False, True] + [False] * (STEPS - 2))
    final.loc[1, "wind_speed_ms"] = 6.0
    tally_final(final, CORE, site)
    assert site.by_year[2019]["wind_direction_deg"] == [STEPS, 0]
    assert site.by_year[2023]["wind_direction_deg"] == [STEPS, STEPS]
    speed = site.channels["wind_speed_ms"]
    assert (speed.final_before, speed.final_after, speed.imputed) == (STEPS - 2, STEPS - 1, 1)
    assert speed.gaps[2] == 2  # the two-step gap, once per staged year
    # 2019: wind in 148 steps, no direction; 2023: both in 148, direction alone in 2;
    # the 2018 row: wind alone
    assert (site.presence_grid[0], site.presence_grid[1], site.presence_grid[2]) == (2, 151, 148)
    report = render_missingness({"hill_of_towie": site}, CORE, "# h\n", "hill_of_towie")
    assert "hill_of_towie: each core channel per year" in report
    assert "| wind_direction_deg | 0.0% | 100.0% |" in report
    assert "2018" not in report.split("each core channel per year")[1]
    assert f"| {1 / STEPS * 100:.3f}% |" in report  # the imputed share, to three decimals

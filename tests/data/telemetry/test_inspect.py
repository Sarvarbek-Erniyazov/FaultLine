"""Archive inspection: CSV preamble handling and the free-text verdict.

The layout tests are a regression guard. The first run of the inspection on real
Kelmarsh archives reported "no message column" for status tables that plainly have
one, because the provider prefixes each export with a commented preamble and the
reader parsed that preamble as data. A silent parse failure that produces a confident
wrong answer is the worst outcome this module can have, so both provider layouts are
pinned here with synthetic fixtures.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pandas as pd

from faultline.data.telemetry.adapters.base import RawMember
from faultline.data.telemetry.inspect import (
    free_text_verdict,
    pick_column,
    profile_event_table,
    read_member_table,
    sniff_csv_layout,
)

# The turbine-data layout: a commented preamble whose LAST line is the header.
GREENBYTE_SCADA = (
    b"# This file was exported by a vendor tool.\n"
    b"#\n"
    b"# Turbine: Testfarm 1\n"
    b"# Time zone: UTC\n"
    b"#\n"
    b'# Date and time,Wind speed (m/s),"Wind speed, Maximum (m/s)",Power (kW)\n'
    b"2016-01-03 00:00:00,7.1,9.2,1850\n"
    b"2016-01-03 00:10:00,6.4,8.1,1600\n"
)

# The status layout: a commented preamble followed by a clean header row.
GREENBYTE_STATUS = (
    b"# This file was exported by a vendor tool.\n"
    b"#\n"
    b"# Turbine: Testfarm 1\n"
    b"# Time zone: UTC\n"
    b"#\n"
    b"Timestamp start,Timestamp end,Duration,Status,Code,Message,Comment\n"
    b"2016-01-14 19:28:03,2016-01-23 14:36:32,211:08:29,Stop,111,Emergency stop nacelle,\n"
    b"2016-01-14 19:28:03,2016-01-14 19:38:03,00:10:00,Warning,5720,Brake accumulator defect,\n"
    b"2016-01-15 04:00:00,2016-01-15 04:10:00,00:10:00,Informational,1,System OK,\n"
)

PLAIN_CSV = b"a,b,c\n1,2,3\n4,5,6\n"


def member_for(tmp_path: Path, name: str, payload: bytes) -> RawMember:
    archive = tmp_path / "archive.zip"
    with zipfile.ZipFile(archive, "a") as handle:
        handle.writestr(name, payload)
    return RawMember(
        archive=archive,
        name=name,
        kind="scada_10min",
        size=len(payload),
        compressed_size=len(payload),
        in_archive=True,
    )


def test_layout_of_a_plain_csv() -> None:
    assert sniff_csv_layout(PLAIN_CSV) == (0, None)


def test_layout_recovers_a_commented_header_row() -> None:
    skiprows, names = sniff_csv_layout(GREENBYTE_SCADA)
    assert skiprows == 6
    assert names is not None
    # the quoted field carrying an internal comma must survive as one column
    assert names == [
        "Date and time",
        "Wind speed (m/s)",
        "Wind speed, Maximum (m/s)",
        "Power (kW)",
    ]


def test_layout_skips_a_preamble_before_a_clean_header() -> None:
    skiprows, names = sniff_csv_layout(GREENBYTE_STATUS)
    assert skiprows == 5
    assert names is None  # the row after the preamble is a real header


def test_scada_member_parses_into_named_columns(tmp_path: Path) -> None:
    frame = read_member_table(member_for(tmp_path, "Turbine_Data_1.csv", GREENBYTE_SCADA))
    assert frame is not None
    assert list(frame.columns)[:2] == ["Date and time", "Wind speed (m/s)"]
    assert len(frame) == 2
    assert frame["Power (kW)"].tolist() == [1850, 1600]


def test_status_member_parses_and_keeps_its_message_column(tmp_path: Path) -> None:
    frame = read_member_table(member_for(tmp_path, "Status_1.csv", GREENBYTE_STATUS))
    assert frame is not None
    assert "Message" in frame.columns
    assert "Code" in frame.columns
    assert len(frame) == 3


def test_oversized_members_are_skipped(tmp_path: Path) -> None:
    member = member_for(tmp_path, "big.csv", PLAIN_CSV)
    huge = RawMember(
        archive=member.archive,
        name=member.name,
        kind="scada_10min",
        size=10**12,
        compressed_size=10**12,
        in_archive=True,
    )
    assert read_member_table(huge) is None


def test_pick_column_prefers_the_most_specific_hint() -> None:
    assert pick_column(["Status", "Message", "Comment"], ("message", "text", "status")) == "Message"
    assert pick_column(["a", "b"], ("message",)) is None


def test_profile_of_a_status_table(tmp_path: Path) -> None:
    member = member_for(tmp_path, "Status_1.csv", GREENBYTE_STATUS)
    frame = read_member_table(member)
    assert frame is not None
    profile = profile_event_table(member, frame)

    assert profile["message_column"] == "Message"
    assert profile["code_column"] == "Code"
    assert profile["rows"] == 3
    assert profile["unique_messages"] == 3
    assert profile["free_text_fraction"] == 1.0
    assert "System OK" in profile["top_messages"]


def test_verdict_without_any_event_table() -> None:
    verdict, rationale = free_text_verdict([])
    assert verdict == "UNVERIFIED"
    assert "no status, alarm or event member" in rationale


def test_verdict_when_no_message_column_exists() -> None:
    verdict, _ = free_text_verdict([{"message_column": None, "unique_messages": 0}])
    assert verdict == "VERIFIED no"


def test_verdict_for_a_controlled_vocabulary() -> None:
    # What the real Kelmarsh status tables look like: every row carries a message, but
    # only a few dozen distinct short strings exist. That is a code book, not language.
    verdict, rationale = free_text_verdict(
        [{"message_column": "Message", "unique_messages": 75, "mean_message_chars": 14.7}]
    )
    assert verdict == "VERIFIED no"
    assert "template-like" in rationale


def test_verdict_for_genuinely_open_ended_text() -> None:
    verdict, rationale = free_text_verdict(
        [{"message_column": "narrative", "unique_messages": 20_000, "mean_message_chars": 480.0}]
    )
    assert verdict == "VERIFIED yes"
    assert "revisit ADR-0001" in rationale


def test_profile_handles_a_table_with_no_message_column(tmp_path: Path) -> None:
    member = member_for(tmp_path, "plain.csv", PLAIN_CSV)
    frame = read_member_table(member)
    assert frame is not None
    profile = profile_event_table(member, frame)
    assert profile["message_column"] is None
    assert profile["unique_messages"] == 0


def test_empty_dataframe_profile(tmp_path: Path) -> None:
    member = member_for(tmp_path, "empty.csv", b"Message\n")
    profile = profile_event_table(member, pd.DataFrame({"Message": []}))
    assert profile["rows"] == 0
    assert profile["free_text_fraction"] == 0.0

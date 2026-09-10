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

from faultline.data.telemetry.adapters.base import RawMember, sniff_csv_layout
from faultline.data.telemetry.adapters.hill_of_towie import HillOfTowieAdapter
from faultline.data.telemetry.adapters.kelmarsh import KelmarshAdapter
from faultline.data.telemetry.inspect import (
    CODE_HINTS,
    code_description_map,
    collect_event_evidence,
    free_text_verdict,
    is_share_alike,
    measure_text,
    normalise_code,
    pick_column,
    pooled_codes,
    profile_event_table,
    read_code_table,
    read_member_table,
    sample_headers,
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


def test_verdict_when_nothing_is_staged() -> None:
    # Distinct from "searched and found nothing": reporting an empty data directory as
    # a finding about the record would be a false negative dressed up as evidence.
    verdict, rationale = free_text_verdict(None, members_staged=0)
    assert verdict == "UNVERIFIED"
    assert "absence of evidence" in rationale


def test_verdict_when_archives_are_staged_but_hold_no_event_table() -> None:
    verdict, rationale = free_text_verdict(None, members_staged=42)
    assert verdict == "UNVERIFIED"
    assert "archives are staged" in rationale


def test_verdict_for_codes_only() -> None:
    # The Hill of Towie alarm log: a million rows, a code on every one, no text.
    verdict, rationale = free_text_verdict(measure_text([_text_profile(1_004_341, {})]))
    assert verdict == "VERIFIED no"
    assert rationale.startswith("codes only")


def test_verdict_for_a_code_book() -> None:
    # What the Kelmarsh status tables look like: every row carries a message, but a
    # few dozen short labels recur thousands of times.
    counts = {
        "System OK": 911,
        "Wind < start wind": 753,
        "Brake accumulator defect": 68,
        "Manual yaw": 33,
        "Grid loss": 7,
        "4-20 mA vane 2": 1,
    }
    verdict, rationale = free_text_verdict(measure_text([_text_profile(2_122, counts)]))
    assert verdict == "VERIFIED no"
    assert rationale.startswith("a code book")
    assert "ADR-0001 holds" in rationale


def test_long_labels_that_recur_are_still_a_code_book() -> None:
    # Length does not decide; recurrence does. Long labels drawn from a fixed list are
    # still a code book.
    stem = "Converter cabinet temperature supervision error, stage " * 2
    counts = {f"{stem}{i}": 40 for i in range(50)}
    verdict, _ = free_text_verdict(measure_text([_text_profile(2_000, counts)]))
    assert verdict == "VERIFIED no"


def test_verdict_for_short_written_descriptions() -> None:
    # What the CARE event_info files look like: a few dozen descriptions, most written
    # once for the event they describe. Neither a code book nor a corpus.
    counts = {"Hydraulic group": 6, "high temperature in transformer cell": 3}
    counts |= {f"Pitch failure - defect encoder on axis {i}, rectified": 1 for i in range(30)}
    verdict, rationale = free_text_verdict(measure_text([_text_profile(95, counts)]))
    assert verdict == "VERIFIED short written descriptions"
    assert "closed set of 32 strings" in rationale
    assert "qualified rather than overturned" in rationale


def test_long_written_descriptions_are_not_called_short() -> None:
    counts = {("The turbine stopped. " * 15) + str(i): 1 for i in range(10)}
    verdict, _ = free_text_verdict(measure_text([_text_profile(10, counts)]))
    assert verdict == "VERIFIED written descriptions"


def test_verdict_for_genuinely_open_ended_text() -> None:
    counts = {f"narrative number {i} about a gearbox": 1 for i in range(20_000)}
    verdict, rationale = free_text_verdict(measure_text([_text_profile(20_000, counts)]))
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


# The Hill of Towie alarm log layout: codes only, one file per month for all turbines.
ALARM_LOG = (
    b"TimeOn,TimeOff,StationNr,Alarmcode\n"
    b"2019-01-01 00:04:48,,2304525,127\n"
    b"2019-01-03 13:59:13,,2304519,25\n"
    b"2019-01-03 13:59:56,,2304519,20\n"
    b"2019-01-03 14:01:06,,2304519,25\n"
)

ALARM_DESCRIPTIONS = (
    b"Alarm Code,Description,Stopping\n"
    b"20,Large generator Cut-in,0\n"
    b"25,Fast cut-out of generator,0\n"
    b'8210,"Stopped, due to icing",1\n'
)

# The CARE event_info layout: semicolon-separated, one row per dataset, and a
# description only on anomaly rows -- normal rows leave it empty.
CARE_EVENT_INFO = (
    b"asset;event_id;event_label;event_start;event_end;event_description\n"
    b"0;73;anomaly;2023-06-10 11:40:00;2023-06-17 11:40:00;Hydraulic group\n"
    b"11;25;normal;2023-05-23 06:50:00;2023-06-05 02:30:00;\n"
    b"10;10;anomaly;2023-10-11 08:40:00;2023-10-18 08:40:00;Gearbox failure\n"
)


def test_normalise_code_treats_float_and_integer_renderings_as_one_code() -> None:
    assert normalise_code(127) == "127"
    assert normalise_code(127.0) == "127"
    assert normalise_code(" 127 ") == "127"
    assert normalise_code("A12") == "A12"
    assert normalise_code(2.5) == "2.5"


def test_profile_counts_every_code_for_pooling(tmp_path: Path) -> None:
    member = member_for(tmp_path, "tblAlarmLog_2019_01.csv", ALARM_LOG)
    frame = read_member_table(member)
    assert frame is not None
    profile = profile_event_table(member, frame)
    assert profile["code_column"] == "Alarmcode"
    assert profile["message_column"] is None
    assert profile["code_counts"] == {"127": 1, "25": 2, "20": 1}


def test_codes_pool_across_tables(tmp_path: Path) -> None:
    first = member_for(tmp_path, "tblAlarmLog_2019_01.csv", ALARM_LOG)
    second = member_for(tmp_path, "tblAlarmLog_2019_02.csv", ALARM_LOG)
    profiles = []
    for member in (first, second):
        frame = read_member_table(member)
        assert frame is not None
        profiles.append(profile_event_table(member, frame))
    assert pooled_codes(profiles) == {"127": 2, "25": 4, "20": 2}


def test_provider_code_descriptions_are_read_and_keyed_by_code(tmp_path: Path) -> None:
    (tmp_path / "Hill_of_Towie_alarms_description.csv").write_bytes(ALARM_DESCRIPTIONS)
    adapter = HillOfTowieAdapter()
    frame = read_code_table(adapter, adapter.discover(tmp_path))
    assert frame is not None
    assert len(frame) == 3
    # the quoted description keeps its internal comma
    assert code_description_map(frame) == {
        "20": "Large generator Cut-in",
        "25": "Fast cut-out of generator",
        "8210": "Stopped, due to icing",
    }


def test_missing_code_description_file_is_none_not_an_error(tmp_path: Path) -> None:
    assert read_code_table(HillOfTowieAdapter(), []) is None
    assert read_code_table(KelmarshAdapter(), []) is None  # names no such file
    assert code_description_map(None) == {}


def test_event_evidence_reports_members_beyond_the_cap(tmp_path: Path) -> None:
    archive = tmp_path / "2019.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        for month in ("01", "02", "03"):
            handle.writestr(f"tblAlarmLog_2019_{month}.csv", ALARM_LOG)
    adapter = HillOfTowieAdapter()
    evidence = collect_event_evidence(adapter, adapter.discover(tmp_path), max_event_members=2)
    assert evidence.candidates == 3
    assert len(evidence.profiles) == 2
    assert len(evidence.skipped) == 1
    member, reason = evidence.skipped[0]
    assert member.name == "tblAlarmLog_2019_03.csv"
    assert "cap of 2" in reason


def test_header_samples_skip_binary_members(tmp_path: Path) -> None:
    (tmp_path / "Penmanshiel_WT_dataSignalMapping.xlsx").write_bytes(b"PK\x03\x04\x00binary\t\n")
    (tmp_path / "Penmanshiel_WT_static.csv").write_bytes(b"Title,Rated power  \n1,2050\n")
    samples = sample_headers(KelmarshAdapter().discover(tmp_path))
    assert list(samples) == ["Penmanshiel_WT_static.csv"]
    # trailing whitespace is stripped so a generated report passes the repository hooks
    assert samples["Penmanshiel_WT_static.csv"][0] == "Title,Rated power"


def test_missing_messages_are_not_counted_as_text(tmp_path: Path) -> None:
    # Regression: under pandas 3 a missing value survives astype(str) as missing, not
    # as the string "nan", so every empty CARE description was once counted as a row
    # with text and listed as the message "nan".
    member = member_for(tmp_path, "Wind Farm A/event_info.csv", CARE_EVENT_INFO)
    frame = read_member_table(member)
    assert frame is not None
    profile = profile_event_table(member, frame)
    assert profile["message_column"] == "event_description"
    assert profile["unique_messages"] == 2
    assert profile["free_text_fraction"] == 2 / 3
    assert profile["message_counts"] == {"Hydraulic group": 1, "Gearbox failure": 1}
    assert "nan" not in profile["top_messages"]


def test_an_identifier_is_not_an_event_code(tmp_path: Path) -> None:
    assert pick_column(["asset", "event_id", "event_description"], CODE_HINTS) is None
    assert pick_column(["TimeOn", "StationNr", "Alarmcode"], CODE_HINTS) == "Alarmcode"
    member = member_for(tmp_path, "Wind Farm A/event_info.csv", CARE_EVENT_INFO)
    frame = read_member_table(member)
    assert frame is not None
    assert profile_event_table(member, frame)["code_column"] is None


def _text_profile(rows: int, counts: dict[str, int]) -> dict[str, object]:
    total = sum(counts.values())
    return {
        "rows": rows,
        "message_counts": counts,
        "unique_messages": len(counts),
        "mean_message_chars": sum(len(m) * n for m, n in counts.items()) / total if total else 0.0,
    }


def test_text_is_pooled_across_tables() -> None:
    measured = measure_text(
        [_text_profile(5, {"a": 3, "bb": 1}), _text_profile(4, {"a": 1, "ccc two": 1})]
    )
    assert measured.tables == 2
    assert measured.rows == 9
    assert measured.text_rows == 6
    assert measured.distinct == 3
    # row-weighted: four rows of "a", one of "bb", one of "ccc two"
    assert measured.mean_chars == (4 * 1 + 2 + 7) / 6
    assert measured.mean_words == (4 * 1 + 1 + 2) / 6
    # "bb" and "ccc two" occur once; "a" recurs
    assert measured.once_share == 2 / 3
    assert measured.max_table_distinct == 2
    assert measured.counts["a"] == 4


def test_measuring_tables_without_text() -> None:
    measured = measure_text([_text_profile(10, {})])
    assert measured.rows == 10
    assert measured.text_rows == 0
    assert measured.distinct == 0
    assert measured.mean_chars == 0.0
    assert measured.once_share == 0.0


def test_share_alike_licences_are_recognised() -> None:
    assert is_share_alike("CC-BY-SA-4.0")
    assert not is_share_alike("CC-BY-4.0")
    assert not is_share_alike("CC0-1.0")

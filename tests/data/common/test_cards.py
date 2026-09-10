"""Dataset cards: carrying the inventory verdict onto the card."""

from __future__ import annotations

from pathlib import Path

import pytest

from faultline.data.common.cards import build_card, extract_verdict, latest_inventory
from faultline.download.zenodo import SourceSpec
from faultline.paths import ProjectPaths


@pytest.mark.parametrize(
    "verdict",
    [
        "VERIFIED no",
        "VERIFIED yes",
        "VERIFIED short written descriptions",
        "VERIFIED written descriptions",
        "UNVERIFIED",
    ],
)
def test_every_verdict_label_is_carried_onto_the_card(tmp_path: Path, verdict: str) -> None:
    # A label the card reader does not know must not degrade to "no verdict line
    # found": the card would then say UNVERIFIED about a record that was measured.
    report = tmp_path / "raw_inventory_x_20260910.md"
    report.write_text(
        "# Raw inventory: x\n\n**Top 20 codes**\n\n## Free-text verdict\n\n"
        f"**{verdict}** - measured, not assumed\n",
        encoding="utf-8",
    )
    assert extract_verdict(report) == (verdict, "measured, not assumed")


def test_a_missing_report_is_unverified() -> None:
    verdict, rationale = extract_verdict(None)
    assert verdict == "UNVERIFIED"
    assert "no raw inventory report" in rationale


def _spec(**overrides: object) -> SourceSpec:
    payload: dict[str, object] = {
        "provider": "Somebody",
        "zenodo_record": 1,
        "license": "CC-BY-SA-4.0",
        "attribution": "Somebody, a record (CC BY-SA 4.0)",
        "site": {"name": "Farm X"},
    }
    payload.update(overrides)
    return SourceSpec.model_validate(payload)


def test_a_republished_source_carries_its_provenance_chain(tmp_paths: ProjectPaths) -> None:
    # ADR-0004, amended 2026-09-10: a republished source is admitted only with its chain
    # written down, and the card is where a reader looks for it.
    chain = "Upstream Co open data -> Republisher, record 42 -> CC BY-SA 4.0"
    card = build_card("x", _spec(provenance=chain), tmp_paths).read_text(encoding="utf-8")
    assert f"| provenance chain | {chain} |" in card


def test_anonymised_timestamps_are_marked_on_the_card(tmp_paths: ProjectPaths) -> None:
    card = build_card("x", _spec(absolute_time=False), tmp_paths).read_text(encoding="utf-8")
    assert "excluded from every absolute-time and seasonal feature" in card
    plain = build_card("y", _spec(), tmp_paths).read_text(encoding="utf-8")
    assert "| real calendar timestamps | yes |" in plain
    assert "| provenance chain | none stated by the publisher |" in plain


def test_the_card_says_when_the_verdict_thresholds_were_chosen(tmp_paths: ProjectPaths) -> None:
    card = build_card("x", _spec(), tmp_paths).read_text(encoding="utf-8")
    assert "chosen after all four sources had been inspected" in card
    assert "between 20% and 80%" in card


def test_the_newest_inventory_wins(tmp_path: Path) -> None:
    for stamp in ("20260908", "20260910"):
        (tmp_path / f"raw_inventory_care_{stamp}.md").write_text("x", encoding="utf-8")
    newest = latest_inventory(tmp_path, "care")
    assert newest is not None
    assert newest.name == "raw_inventory_care_20260910.md"

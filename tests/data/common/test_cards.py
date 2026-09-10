"""Dataset cards: carrying the inventory verdict onto the card."""

from __future__ import annotations

from pathlib import Path

import pytest

from faultline.data.common.cards import extract_verdict, latest_inventory


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


def test_the_newest_inventory_wins(tmp_path: Path) -> None:
    for stamp in ("20260908", "20260910"):
        (tmp_path / f"raw_inventory_care_{stamp}.md").write_text("x", encoding="utf-8")
    newest = latest_inventory(tmp_path, "care")
    assert newest is not None
    assert newest.name == "raw_inventory_care_20260910.md"

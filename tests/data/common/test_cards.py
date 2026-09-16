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


# ------------------------------------------------------------------ hand-written sections

REPO = Path(__file__).resolve().parents[3]

#: The hand-written note the held-out site's card must keep (ADR-0018 rulings, 2026-09-16).
HILL_OF_TOWIE_GAP = (
    "**275 Hill of Towie status messages are not written into the `tel+status` stream.**"
)


def test_a_hand_written_section_survives_regeneration(tmp_paths: ProjectPaths) -> None:
    written = (
        "\n## Evaluation gaps (added by hand, 2026-09-16; not produced by `faultline cards build`)"
        "\n\n- a gap the generator has no field for.\n"
    )
    card = build_card("x", _spec(), tmp_paths)
    generated = card.read_text(encoding="utf-8")
    card.write_text(
        generated.replace("\n## Generation", written + "\n## Generation"), encoding="utf-8"
    )
    text = build_card("x", _spec(), tmp_paths).read_text(encoding="utf-8")
    assert written.strip() in text
    assert text.index("## Evaluation gaps") < text.index("## Generation")
    # carried once, not appended again on every regeneration
    assert text.count("## Evaluation gaps") == 1
    again = build_card("x", _spec(), tmp_paths).read_text(encoding="utf-8")
    assert again.count("## Evaluation gaps") == 1


def test_the_tracked_hill_of_towie_card_carries_the_275_message_gap() -> None:
    card = (REPO / "data" / "cards" / "hill_of_towie.md").read_text(encoding="utf-8")
    assert HILL_OF_TOWIE_GAP in card


def test_a_regenerated_hill_of_towie_card_keeps_the_275_message_gap(
    tmp_paths: ProjectPaths,
) -> None:
    # The guard the E0-E5 ruling asked for, in the pattern of the torch.load and 32,769-row
    # tests: `faultline cards build` overwrites the card, so a regeneration that dropped the
    # hand-written note would silently remove the held-out site's evaluation gap.
    tracked = (REPO / "data" / "cards" / "hill_of_towie.md").read_text(encoding="utf-8")
    (tmp_paths.cards_dir / "hill_of_towie.md").write_text(tracked, encoding="utf-8")
    regenerated = build_card("hill_of_towie", _spec(), tmp_paths).read_text(encoding="utf-8")
    assert HILL_OF_TOWIE_GAP in regenerated
    assert "added by hand" in regenerated

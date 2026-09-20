"""The figure set, drawn from the committed record."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from faultline.evaluation.figures import (
    BUILDERS,
    FORWARD_CAVEAT,
    FORWARD_SPAN,
    Figure,
    Marker,
    Panel,
    RecordSet,
    Row,
    delta,
    interval,
    render_intervals,
    stack,
    write_figures,
)
from faultline.paths import ProjectPaths

SVG = "{http://www.w3.org/2000/svg}"

#: The pre-commit hook's ceiling for a committed file.
MAX_KB = 5000


@pytest.fixture(scope="module")
def paths() -> ProjectPaths:
    return ProjectPaths.resolve()


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory, paths: ProjectPaths) -> list[Path]:
    """Run the whole set once, writing into a scratch reports directory."""
    scratch = tmp_path_factory.mktemp("reports")
    # Values are read from the repository; output goes to scratch, so running the tests
    # never rewrites the committed figure set.
    return write_figures(paths, out_dir=scratch)


def test_every_named_source_exists(paths: ProjectPaths) -> None:
    """Every source a figure names is a file in this repository."""
    records = RecordSet(paths)
    missing: list[str] = []
    for _, builder in BUILDERS:
        figure = builder(records)
        assert figure is not None, "the committed record should support every figure"
        for source in figure.sources:
            if source in figure.missing:
                continue
            if not (paths.repo_root / source).is_file():
                missing.append(source)
    assert not missing, f"named sources that do not exist: {missing}"


def test_the_command_runs_headless_and_writes_the_set(built: list[Path]) -> None:
    """Building needs no display, no model and no network, and writes every output."""
    stems = {path.name for path in built}
    assert "figures_index.md" in stems
    assert "ledger_gates.md" in stems
    assert sum(1 for name in stems if name.endswith(".svg")) == 6
    for path in built:
        assert path.is_file() and path.stat().st_size > 0


def test_no_output_exceeds_the_size_rule(built: list[Path]) -> None:
    """No written file approaches the pre-commit large-file ceiling."""
    for path in built:
        assert path.stat().st_size / 1024 < MAX_KB, path


def test_every_svg_is_well_formed_and_inside_its_canvas(built: list[Path]) -> None:
    """Each figure parses as XML and draws nothing outside the canvas it declares."""
    for path in (p for p in built if p.suffix == ".svg"):
        root = ET.fromstring(path.read_text(encoding="utf-8"))
        width, height = float(root.get("width", "0")), float(root.get("height", "0"))
        assert width > 0 and height > 0
        for mark in root.iter(f"{SVG}circle"):
            x, y = float(mark.get("cx", "0")), float(mark.get("cy", "0"))
            assert -2 <= x <= width + 2 and -2 <= y <= height + 2, path


def test_the_split_is_never_named_by_its_old_span(built: list[Path]) -> None:
    """No output writes "2022-2024"; the split is named as Penmanshiel's shard allows."""
    for path in built:
        text = path.read_text(encoding="utf-8")
        assert "2022-2024" not in text and "2022–2024" not in text, path


def test_forward_figures_carry_the_standing_caveat(paths: ProjectPaths) -> None:
    """Every figure read from the forward-in-time split says so in its caption."""
    records = RecordSet(paths)
    for name in ("F4", "F2", "F3"):
        builder = dict(BUILDERS)[name]
        figure = builder(records)
        assert figure is not None
        assert FORWARD_CAVEAT in figure.caption, name


def test_the_index_names_every_figure_and_its_sentence(built: list[Path]) -> None:
    """The index lists each output, the files it wrote and the sentence it supports."""
    index = next(path for path in built if path.name == "figures_index.md")
    text = index.read_text(encoding="utf-8")
    assert FORWARD_SPAN in text
    for path in built:
        if path.name != "figures_index.md":
            assert path.stem in text, path


def test_the_ledger_covers_the_six_gates(built: list[Path]) -> None:
    """One row a gate, ADR-0021 through ADR-0026, with the registering commit."""
    ledger = next(path for path in built if path.name == "ledger_gates.md")
    text = ledger.read_text(encoding="utf-8")
    for number in range(21, 27):
        assert f"ADR-00{number}" in text
    # Every rule's own registering commit, as its section asserts it.
    for sha in ("ce9c8ad", "801ab71", "c9489a2", "79d4e97", "3e29202", "319ae3b"):
        assert f"`{sha}`" in text, sha


def test_readers_pull_the_recorded_fields() -> None:
    """The two readers take the point estimate and both bounds, and nothing else."""
    assert interval({"auprc": 0.05, "low": 0.04, "high": 0.06}) == (0.05, 0.04, 0.06)
    assert delta({"delta": -0.01, "low": -0.02, "high": 0.0}) == (-0.01, -0.02, 0.0)


def test_a_missing_record_skips_its_figure_rather_than_substituting(
    tmp_path: Path, paths: ProjectPaths
) -> None:
    """A figure whose source is absent is left out, and the absence is recorded."""
    empty = ProjectPaths(repo_root=tmp_path, data_root=tmp_path / "data")
    empty.data_reports_dir.mkdir(parents=True, exist_ok=True)
    records = RecordSet(empty)
    for _, builder in BUILDERS:
        assert builder(records) is None
    assert records.missing


def test_stacked_panels_keep_their_own_axes() -> None:
    """Stacking nests each panel, so a squashed scale never leaks between them."""
    one = render_intervals(
        [Panel("a", [Row("x", 0.5, 0.4, 0.6)])],
        title="t",
        subtitle="s",
        markers=[Marker(0.45, "line")],
        value_label="v",
    )
    two = render_intervals(
        [Panel("b", [Row("y", 0.001, 0.0005, 0.002)])],
        title="",
        subtitle="",
        value_label="v",
    )
    combined = stack([one, two])
    root = ET.fromstring(combined)
    assert len(list(root.findall(f"{SVG}svg"))) == 2


def test_a_figure_without_svg_still_carries_its_sentence() -> None:
    """The ledger is Markdown, not a drawing, and the index treats it as one output."""
    figure = Figure(stem="s", title="t", sentence="one sentence.", sources=[], markdown="| a |")
    assert figure.svg is None and figure.markdown

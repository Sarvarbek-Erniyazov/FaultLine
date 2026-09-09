"""Command line entry points.

Every command is a thin shell over the package: it resolves paths, loads a config,
opens a run and delegates. Scripts under ``scripts/`` call these same functions, so
there is exactly one implementation of each operation.

Heavy modules are imported inside the command bodies to keep ``faultline --help``
responsive.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Annotated

import typer
from dotenv import load_dotenv

from faultline import __version__
from faultline.logging_utils import get_logger
from faultline.paths import ProjectPaths

logger = get_logger(__name__)

app = typer.Typer(
    name="faultline",
    help="FaultLine data pipelines and staging (M0: no model code).",
    no_args_is_help=True,
    add_completion=False,
)
download_app = typer.Typer(
    help="Stage public datasets with checksum verification.", no_args_is_help=True
)
inspect_app = typer.Typer(
    help="Inspect staged archives without extracting them.", no_args_is_help=True
)
cards_app = typer.Typer(
    help="Build dataset cards from record metadata and manifests.", no_args_is_help=True
)
text_app = typer.Typer(help="Run the text corpus pipeline.", no_args_is_help=True)
telemetry_app = typer.Typer(help="Run the telemetry pipeline.", no_args_is_help=True)
check_app = typer.Typer(help="Repository self-checks.", no_args_is_help=True)

app.add_typer(download_app, name="download")
app.add_typer(inspect_app, name="inspect")
app.add_typer(cards_app, name="cards")
app.add_typer(text_app, name="text")
app.add_typer(telemetry_app, name="telemetry")
app.add_typer(check_app, name="check")

ConfigOption = Annotated[
    Path, typer.Option("--config", "-c", help="Path to the run configuration.")
]


@app.callback()
def main(
    version: Annotated[bool, typer.Option("--version", help="Print the version and exit.")] = False,
) -> None:
    """Load ``.env`` and handle global options.

    Args:
        version: Print the package version and exit.
    """
    load_dotenv(override=False)
    if version:
        typer.echo(__version__)
        raise typer.Exit()


@download_app.command(
    "telemetry",
    help="Stage telemetry archives from Zenodo and update the checksum manifests.",
)
def download_telemetry(
    config: ConfigOption = Path("configs/data/sources_telemetry.yaml"),
    tier: Annotated[int, typer.Option("--tier", help="Highest download tier to include.")] = 1,
    source: Annotated[str | None, typer.Option("--source", help="Limit to one source id.")] = None,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Resolve and print the plan without downloading.")
    ] = False,
    attempts: Annotated[
        int, typer.Option("--attempts", help="Whole-run attempts if the archive is unreachable.")
    ] = 1,
    retry_delay: Annotated[
        int, typer.Option("--retry-delay", help="Seconds to wait between whole-run attempts.")
    ] = 300,
) -> None:
    """Stage telemetry archives from Zenodo and update the checksum manifests.

    Zenodo is a public service that does go down. Verified files are skipped and
    partial files resume, so re-running is cheap: ``--attempts`` retries the whole
    run after a transport failure, which is what lets a multi-hour staging survive an
    outage. A configuration error, such as a file missing from the pinned record, is
    never retried.

    Args:
        config: Source specification file.
        tier: Highest tier to include.
        source: Restrict the run to a single source.
        dry_run: Print the plan and total size, then stop.
        attempts: Number of whole-run attempts on transport failure.
        retry_delay: Seconds to wait between attempts.

    Raises:
        typer.Exit: With code 1 if a configured file is missing from a record, or if
            every attempt failed.
    """
    import requests

    from faultline.download.zenodo import ZenodoClient, download_source, load_sources_config

    paths = ProjectPaths.resolve()
    spec = load_sources_config(config)
    client = ZenodoClient(api_base=spec.defaults.api_base)
    if source and source not in spec.sources:
        typer.echo(f"unknown source {source!r}; configured: {', '.join(spec.sources)}")
        raise typer.Exit(code=1)
    selected = {source: spec.sources[source]} if source else spec.sources

    for attempt in range(1, max(attempts, 1) + 1):
        try:
            grand_total = 0
            grand_pending = 0
            for name, source_spec in selected.items():
                plan = download_source(
                    source=name,
                    spec=source_spec,
                    tier=tier,
                    paths=paths,
                    client=client,
                    defaults=spec.defaults,
                    dry_run=dry_run,
                )
                grand_total += plan.total_bytes
                grand_pending += plan.pending_bytes
                typer.echo(
                    f"{name}: {len(plan.files)} files, {plan.total_bytes / 1e9:.2f} GB total, "
                    f"{plan.pending_bytes / 1e9:.2f} GB still to fetch"
                )
                if dry_run:
                    for filename, size, verified in plan.files:
                        state = "verified" if verified else "pending"
                        typer.echo(f"    {state:9} {size / 1e6:10.1f} MB  {filename}")
            typer.echo(
                f"TOTAL: {grand_total / 1e9:.2f} GB configured, "
                f"{grand_pending / 1e9:.2f} GB to fetch"
            )
            return
        except requests.RequestException as exc:
            logger.warning("attempt %d/%d failed: %s", attempt, attempts, exc)
            if attempt >= attempts:
                typer.echo(f"giving up after {attempt} attempt(s): {exc}")
                raise typer.Exit(code=1) from exc
            typer.echo(f"attempt {attempt}/{attempts} failed; retrying in {retry_delay}s")
            time.sleep(retry_delay)


@inspect_app.command(
    "telemetry",
    help="Inventory staged archives in place and write raw inventory reports.",
)
def inspect_telemetry(
    source: Annotated[
        str | None, typer.Option("--source", help="Source id; all configured sources when omitted.")
    ] = None,
    config: ConfigOption = Path("configs/data/sources_telemetry.yaml"),
    max_members: Annotated[
        int, typer.Option("--max-members", help="Cap on archive members listed per archive.")
    ] = 5000,
) -> None:
    """Inventory staged archives in place and write raw inventory reports.

    Args:
        source: Restrict the inventory to one source.
        config: Source specification file, used for licence and provider metadata.
        max_members: Cap on the number of members listed per archive.

    Raises:
        typer.Exit: With code 1 if the source id is unknown.
    """
    from faultline.data.telemetry.inspect import inspect_source
    from faultline.download.zenodo import load_sources_config

    paths = ProjectPaths.resolve()
    spec = load_sources_config(config)
    if source and source not in spec.sources:
        typer.echo(f"unknown source {source!r}; configured: {', '.join(spec.sources)}")
        raise typer.Exit(code=1)
    names = [source] if source else list(spec.sources)
    for name in names:
        report_path = inspect_source(name, spec.sources[name], paths, max_members=max_members)
        typer.echo(f"{name}: wrote {report_path}")


@inspect_app.command(
    "resolve",
    help="Measure the power scale and the DST fingerprint of a staged record.",
)
def inspect_resolve(
    source: Annotated[
        str, typer.Option("--source", help="Source id whose archives are measured.")
    ] = "kelmarsh",
    config: ConfigOption = Path("configs/data/sources_telemetry.yaml"),
    timestamp_column: Annotated[
        str, typer.Option("--timestamp-column", help="Timestamp column as published.")
    ] = "Date and time",
    power_column: Annotated[
        str, typer.Option("--power-column", help="Power column as published.")
    ] = "Power (kW)",
    energy_column: Annotated[
        str | None, typer.Option("--energy-column", help="Separate energy column, if any.")
    ] = "Energy Export (kWh)",
    zone: Annotated[
        str, typer.Option("--zone", help="Local zone the timestamps are tested against.")
    ] = "Europe/London",
    max_members: Annotated[
        int | None, typer.Option("--max-members", help="Cap on SCADA members read.")
    ] = None,
) -> None:
    """Measure the power scale and the DST fingerprint of a staged record.

    Answers two questions the provider metadata contradicts itself about: whether
    the power column is a mean power or an energy total, and whether the timestamps
    are UTC or local civil time. Both are measured from the staged archives; neither
    is taken from a header.

    Args:
        source: Source whose staged archives are measured.
        config: Source specification file.
        timestamp_column: Timestamp column as published.
        power_column: Power column as published.
        energy_column: Separate energy column, when the export publishes one.
        zone: Local zone the timestamps are tested against.
        max_members: Cap on the number of SCADA members read.

    Raises:
        typer.Exit: With code 1 if the source id is unknown.
    """
    from faultline.data.telemetry.resolve import resolve_source
    from faultline.download.zenodo import load_sources_config

    paths = ProjectPaths.resolve()
    spec = load_sources_config(config)
    if source not in spec.sources:
        typer.echo(f"unknown source {source!r}; configured: {', '.join(spec.sources)}")
        raise typer.Exit(code=1)
    report = resolve_source(
        source=source,
        spec=spec.sources[source],
        paths=paths,
        timestamp_column=timestamp_column,
        power_column=power_column,
        energy_column=energy_column,
        candidate_zone=zone,
        max_members=max_members,
    )
    typer.echo(f"{source}: wrote {report}")


@cards_app.command(
    "build",
    help="Render dataset cards from record metadata, manifests and inventory reports.",
)
def cards_build(
    config: ConfigOption = Path("configs/data/sources_telemetry.yaml"),
    source: Annotated[
        str | None, typer.Option("--source", help="Source id; all configured sources when omitted.")
    ] = None,
) -> None:
    """Render dataset cards from record metadata, manifests and inventory reports.

    Args:
        config: Source specification file.
        source: Restrict rendering to one source.

    Raises:
        typer.Exit: With code 1 if the source id is unknown.
    """
    from faultline.data.common.cards import build_card
    from faultline.download.zenodo import load_sources_config

    paths = ProjectPaths.resolve()
    spec = load_sources_config(config)
    if source and source not in spec.sources:
        typer.echo(f"unknown source {source!r}; configured: {', '.join(spec.sources)}")
        raise typer.Exit(code=1)
    for name in [source] if source else list(spec.sources):
        card = build_card(name, spec.sources[name], paths)
        typer.echo(f"{name}: wrote {card}")


@text_app.command("run", help="Run the text corpus pipeline and write per-stage reports.")
def text_run(
    config: ConfigOption = Path("configs/data/text_v0.yaml"),
    stage: Annotated[
        str, typer.Option("--stage", help="Stage to run: clean, filter, dedup, pii, final, or all.")
    ] = "all",
    input_path: Annotated[
        Path | None, typer.Option("--input", help="Override the configured raw input file.")
    ] = None,
) -> None:
    """Run the text corpus pipeline and write per-stage reports.

    Args:
        config: Text pipeline configuration.
        stage: Stage to execute, or ``all``.
        input_path: Override for the raw input file, for smoke runs on fixtures.
    """
    from faultline.data.common.stage import run_pipeline
    from faultline.data.text.pipeline import TextLayout, build_stages, load_text_config
    from faultline.runs import start_run

    paths = ProjectPaths.resolve()
    cfg = load_text_config(config)
    if input_path is not None:
        cfg = cfg.model_copy(
            update={"io": cfg.io.model_copy(update={"input_path": str(input_path)})}
        )
    layout = TextLayout.build(cfg, paths)
    stages = build_stages(cfg, layout, stage)
    with start_run(config, cfg, stage, "text", paths) as ctx:
        results = run_pipeline(stages, ctx)
        for result in results:
            typer.echo(
                f"{result.name}: {result.rows_in} -> {result.rows_out} "
                f"({result.retention * 100:.2f}% retained)"
            )
        typer.echo(f"reports: {ctx.run_dir}")


@telemetry_app.command("run", help="Run the telemetry pipeline and write per-stage reports.")
def telemetry_run(
    config: ConfigOption = Path("configs/data/telemetry_v0.yaml"),
    stage: Annotated[
        str, typer.Option("--stage", help="Stage to run: ingest, clean, filter, final, or all.")
    ] = "all",
    source: Annotated[
        str | None, typer.Option("--source", help="Restrict the run to one source id.")
    ] = None,
) -> None:
    """Run the telemetry pipeline and write per-stage reports.

    Args:
        config: Telemetry pipeline configuration.
        stage: Stage to execute, or ``all``.
        source: Restrict the run to a single source.
    """
    from faultline.data.common.stage import run_pipeline
    from faultline.data.telemetry.pipeline import build_stages, load_telemetry_config
    from faultline.runs import start_run

    paths = ProjectPaths.resolve()
    cfg = load_telemetry_config(config)
    stages = build_stages(cfg, paths, stage, source=source)
    with start_run(config, cfg, stage, "telemetry", paths) as ctx:
        results = run_pipeline(stages, ctx)
        for result in results:
            typer.echo(f"{result.name}: {result.rows_in} -> {result.rows_out}")
        typer.echo(f"reports: {ctx.run_dir}")


@check_app.command(
    "naming",
    help="Fail if a forbidden string appears in a tracked file (ADR-0002).",
)
def check_naming() -> None:
    """Fail if a forbidden string appears in a tracked file (ADR-0002).

    Raises:
        typer.Exit: With code 1 when any violation is found.
    """
    from faultline.naming import scan_repository

    paths = ProjectPaths.resolve()
    violations = scan_repository(paths.repo_root)
    for violation in violations:
        typer.echo(str(violation))
    if violations:
        typer.echo(f"{len(violations)} naming violation(s); see ADR-0002 in docs/DECISIONS.md")
        raise typer.Exit(code=1)
    typer.echo("naming check passed")


if __name__ == "__main__":  # pragma: no cover
    app()

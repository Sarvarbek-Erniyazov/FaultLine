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
from faultline.tokenizers.layout import VocabLayout

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
model_app = typer.Typer(help="Train and evaluate models.", no_args_is_help=True)
check_app = typer.Typer(help="Repository self-checks.", no_args_is_help=True)

app.add_typer(download_app, name="download")
app.add_typer(inspect_app, name="inspect")
app.add_typer(cards_app, name="cards")
app.add_typer(text_app, name="text")
app.add_typer(telemetry_app, name="telemetry")
app.add_typer(model_app, name="model")
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


@download_app.command(
    "text",
    help="Stage the NRC operator-narrative text sources and update their manifests.",
)
def download_text(
    config: ConfigOption = Path("configs/data/sources_text.yaml"),
    source: Annotated[str | None, typer.Option("--source", help="Limit to one source id.")] = None,
) -> None:
    """Stage every enabled text source and write its manifest.

    Args:
        config: Text source specification file.
        source: Restrict the run to a single source.

    Raises:
        typer.Exit: With code 1 if the source id is unknown.
    """
    from faultline.download.nrc_text import (
        NrcTextClient,
        fetch_source,
        load_sources_text_config,
        shard_key_for,
        stage_documents,
    )

    paths = ProjectPaths.resolve()
    spec = load_sources_text_config(config)
    if source and source not in spec.sources:
        typer.echo(f"unknown source {source!r}; configured: {', '.join(spec.sources)}")
        raise typer.Exit(code=1)
    names = [source] if source else [name for name, s in spec.sources.items() if s.enabled]
    client = NrcTextClient()
    for name in names:
        source_spec = spec.sources[name]
        documents = fetch_source(name, source_spec, client, paths)
        manifest = stage_documents(
            name, source_spec, documents, paths, shard_key_for(name, source_spec)
        )
        typer.echo(f"{name}: staged {len(manifest.files)} documents")


@download_app.command(
    "phmsa",
    help="Fetch one PHMSA incident-data attachment from data.transportation.gov.",
)
def download_phmsa(
    asset_id: Annotated[str, typer.Option("--asset-id", help="The attachment's assetId.")],
    filename: Annotated[str, typer.Option("--filename", help="The attachment's filename.")],
    view: Annotated[str, typer.Option("--view", help="Socrata view id.")] = "27nc-rsge",
) -> None:
    """Fetch one attachment through the robots-gated client, for ``inspect phmsa``.

    Args:
        asset_id: The attachment's ``assetId``.
        filename: The attachment's ``filename``.
        view: The Socrata view the attachment belongs to.

    Raises:
        typer.Exit: With code 1 if the request was refused or failed.
    """
    import requests

    from faultline.data.common.manifest import hash_file
    from faultline.data.text.phmsa_manual import fetch_socrata_attachment
    from faultline.download.nrc_text import NrcTextClient

    paths = ProjectPaths.resolve()
    try:
        destination, url = fetch_socrata_attachment(
            NrcTextClient(), paths, view=view, asset_id=asset_id, filename=filename
        )
    except requests.HTTPError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"url: {url}")
    typer.echo(f"file: {destination} ({destination.stat().st_size} bytes)")
    typer.echo(f"sha256: {hash_file(destination, 'sha256')}")


@inspect_app.command(
    "phmsa",
    help="Hash, record and read-only-profile a manually retrieved PHMSA archive.",
)
def inspect_phmsa(
    zip_path: Annotated[
        Path, typer.Option("--file", help="The manually retrieved zip file.")
    ] = Path("data/raw/text/phmsa/PHMSA_Pipeline_Safety_Flagged_Incidents.zip"),
    url: Annotated[
        str,
        typer.Option("--url", help="URL the file was downloaded from, for the manifest."),
    ] = (
        "https://www.phmsa.dot.gov/sites/phmsa.dot.gov/files/data_statistics/pipeline/"
        "PHMSA_Pipeline_Safety_Flagged_Incidents.zip"
    ),
    retrieved_at: Annotated[
        str | None,
        typer.Option(
            "--retrieved-at",
            help="ISO date/time the human retrieved it (their own record); now, when omitted.",
        ),
    ] = None,
    automated: Annotated[
        bool,
        typer.Option(
            "--automated/--manual",
            help="Fetched by `download phmsa` (robots-gated client) rather than by hand.",
        ),
    ] = False,
) -> None:
    """Hash, manifest and read-only-profile a retrieved PHMSA archive.

    Does not run any pipeline stage against the file (ADR-0016: staged, not yet used).

    Args:
        zip_path: The retrieved file.
        url: Its source URL, for the manifest.
        retrieved_at: When it was retrieved; now (UTC) when omitted.
        automated: Record the project's own client as the retrieval method.

    Raises:
        typer.Exit: With code 1 if the file does not exist yet, code 2 if it does not
            parse (nothing is written to the manifest in either case).
    """
    from datetime import UTC, datetime

    from faultline.data.text.phmsa_manual import (
        RETRIEVAL_METHOD,
        ArchiveParseError,
        inspect_archive,
        record_manual_retrieval,
        render_report,
    )

    if not zip_path.is_file():
        typer.echo(f"{zip_path} does not exist yet; nothing to inspect")
        raise typer.Exit(code=1)
    paths = ProjectPaths.resolve()
    when = datetime.fromisoformat(retrieved_at) if retrieved_at else datetime.now(tz=UTC)
    # parse first: the manifest records verified=True, which only a parsed file earns
    try:
        profiles = inspect_archive(zip_path)
    except ArchiveParseError as exc:
        typer.echo(f"{exc}; nothing recorded", err=True)
        raise typer.Exit(code=2) from exc
    manifest = record_manual_retrieval(
        paths,
        zip_path,
        url=url,
        retrieved_at=when,
        retrieval_method=None if automated else RETRIEVAL_METHOD,
    )
    report = render_report(zip_path, manifest, profiles)
    stamp = datetime.now(tz=UTC).strftime("%Y%m%d")
    destination = paths.data_reports_dir / f"phmsa_manual_{stamp}.md"
    destination.write_text(report, encoding="utf-8")
    typer.echo(f"wrote {destination}")


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
    station_column: Annotated[
        str | None,
        typer.Option("--station-column", help="Turbine column, when one file holds every turbine."),
    ] = None,
    member_prefix: Annotated[
        str | None,
        typer.Option("--member-prefix", help="Read only members named with this prefix."),
    ] = None,
    label_offset_minutes: Annotated[
        int,
        typer.Option(
            "--label-offset-minutes", help="Added to labels; -10 for interval-end labels."
        ),
    ] = 0,
) -> None:
    """Measure the power scale and the DST fingerprint of a staged record.

    Answers two questions the provider metadata contradicts itself about: whether
    the power column is a mean power or an energy total, and whether the timestamps
    are UTC or local civil time. Both are measured from the staged archives; neither
    is taken from a header.

    Hill of Towie, for example:
    ``--source hill_of_towie --timestamp-column TimeStamp --power-column
    wtc_ActPower_mean --energy-column "" --station-column StationId --member-prefix
    tblSCTurGrid_ --label-offset-minutes -10``.

    Args:
        source: Source whose staged archives are measured.
        config: Source specification file.
        timestamp_column: Timestamp column as published.
        power_column: Power column as published.
        energy_column: Separate energy column, when the export publishes one.
        zone: Local zone the timestamps are tested against.
        max_members: Cap on the number of SCADA members read.
        station_column: Turbine column, when one member holds every turbine.
        member_prefix: Read only members whose name starts with this.
        label_offset_minutes: Minutes added to every label before testing.

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
        energy_column=energy_column or None,
        candidate_zone=zone,
        max_members=max_members,
        station_column=station_column,
        member_prefix=member_prefix,
        label_offset_minutes=label_offset_minutes,
    )
    typer.echo(f"{source}: wrote {report}")


@inspect_app.command(
    "downtime",
    help="Stream a staged downtime series (Hill of Towie ShutdownDuration) and profile it.",
)
def inspect_downtime_command(
    source: Annotated[
        str, typer.Option("--source", help="Source whose downtime series is profiled.")
    ] = "hill_of_towie",
) -> None:
    """Stream a staged downtime series and write its profile report.

    Args:
        source: Source whose downtime series is profiled.
    """
    from faultline.data.telemetry.downtime import inspect_downtime

    report = inspect_downtime(ProjectPaths.resolve(), source)
    typer.echo(f"wrote {report}")


@inspect_app.command(
    "ranges",
    help="Percentiles, repeated tail values and what sentinels and bounds remove, pre-bounds.",
)
def inspect_ranges_command(
    config: ConfigOption = Path("configs/data/telemetry_v2.yaml"),
    source: Annotated[
        str | None, typer.Option("--source", help="Source id; every source when omitted.")
    ] = None,
) -> None:
    """Measure every ingested value, before any bound, and write the ranges report.

    Args:
        config: The configuration whose sentinels and bounds are applied.
        source: Restrict to one source.
    """
    from faultline.data.telemetry.adapters import ADAPTERS
    from faultline.data.telemetry.coverage import inspect_ranges
    from faultline.data.telemetry.pipeline import load_telemetry_config

    report = inspect_ranges(
        ProjectPaths.resolve(),
        load_telemetry_config(config),
        config,
        [source] if source else list(ADAPTERS),
    )
    typer.echo(f"wrote {report}")


@inspect_app.command(
    "missingness",
    help="Coverage before and after imputation, gaps and channels present per step.",
)
def inspect_missingness_command(
    config: ConfigOption = Path("configs/data/telemetry_v2.yaml"),
) -> None:
    """Measure missingness on the cleaned and final tables and write its report.

    Args:
        config: The configuration the tables were produced under.
    """
    from faultline.data.telemetry.adapters import ADAPTERS
    from faultline.data.telemetry.coverage import inspect_missingness
    from faultline.data.telemetry.pipeline import load_telemetry_config

    report = inspect_missingness(
        ProjectPaths.resolve(), load_telemetry_config(config), config, list(ADAPTERS)
    )
    typer.echo(f"wrote {report}")


@inspect_app.command(
    "verification",
    help="Four checks on the harmonised labels: stop classes, late-period rates, channel gaps "
    "and CARE at dataset level, in one report.",
)
def inspect_verification_command(
    config: ConfigOption = Path("configs/data/telemetry_v3.yaml"),
) -> None:
    """Run the four verification checks and write their report.

    Args:
        config: The configuration the labels and tables were produced under.
    """
    from faultline.data.telemetry.pipeline import load_telemetry_config
    from faultline.data.telemetry.verify import inspect_verification

    report = inspect_verification(ProjectPaths.resolve(), load_telemetry_config(config), config)
    typer.echo(f"wrote {report}")


@inspect_app.command(
    "vocab-overlap",
    help="H3's word overlap under three corpus conditions, PHMSA's movers, and the "
    "pre-registered testability gate on held-out events.",
)
def inspect_vocab_overlap_command(
    labels: Annotated[
        Path, typer.Option("--labels", help="Event labelling file the labels were built under.")
    ] = Path("configs/data/events_v2.yaml"),
) -> None:
    """Measure H3's vocabulary split and its gate, and write the report.

    Args:
        labels: The event labelling file.
    """
    from faultline.data.text.vocab_overlap import inspect_vocab_overlap

    report, record = inspect_vocab_overlap(ProjectPaths.resolve(), labels)
    typer.echo(f"wrote {report} and {record}")


@inspect_app.command(
    "status-convention",
    help="H3' Stage A: status-string token coverage lowercased after a space, frozen "
    "tokenizer, against ADR-0017's pre-registered line.",
)
def inspect_status_convention_command(
    tokenizer: Annotated[
        Path, typer.Option("--tokenizer", help="Frozen text tokenizer to encode with.")
    ] = Path("data/tokenizers/text_bpe_v1_22c56e49.json"),
    corpus: Annotated[
        str, typer.Option("--corpus", help="Corpus the tokenizer was fitted on.")
    ] = "operator_narratives",
) -> None:
    """Measure H3' Stage A and write its report.

    Args:
        tokenizer: The frozen text tokenizer; its shards give token frequency.
        corpus: The corpus it was fitted on, for the narrative bytes/token baseline.
    """
    from faultline.data.text.status_convention import inspect_status_convention

    paths = ProjectPaths.resolve()
    report, record = inspect_status_convention(
        paths, (paths.repo_root / tokenizer).resolve(), corpus
    )
    typer.echo(f"wrote {report} and {record}")


@inspect_app.command(
    "core",
    help="The core channel rule on the cleaned grid: coverage per site and year, the "
    "seasonally matched shortcut control, and the training exclusions.",
)
def inspect_core_command(
    config: ConfigOption = Path("configs/data/telemetry_v3.yaml"),
) -> None:
    """Measure the core channel rule and write its report.

    Args:
        config: The configuration whose tiers and split specification are checked.
    """
    from faultline.data.telemetry.core_rule import inspect_core
    from faultline.data.telemetry.pipeline import load_telemetry_config

    report = inspect_core(ProjectPaths.resolve(), load_telemetry_config(config), config)
    typer.echo(f"wrote {report}")


@inspect_app.command(
    "channels",
    help="Report each canonical channel's status per source, checked against staged headers.",
)
def inspect_channels_command(
    splits: Annotated[
        Path, typer.Option("--splits", help="Split spec naming the held-out and eval-only sources.")
    ] = Path("configs/data/splits_v2.yaml"),
) -> None:
    """Report each canonical channel's status per source, checked against staged headers.

    Training and held-out sources are read from the split specification, so the
    report's cross-site findings follow the design rather than a list typed here.

    Args:
        splits: Split specification.
    """
    from faultline.config import load_config
    from faultline.data.common.splits import SplitsConfig
    from faultline.data.telemetry.adapters import ADAPTERS
    from faultline.data.telemetry.channels import inspect_channels

    paths = ProjectPaths.resolve()
    spec = load_config(splits, SplitsConfig)
    holdout = [source for source in ADAPTERS if source in spec.holdout_sites]
    training = [
        source
        for source in ADAPTERS
        if source not in spec.holdout_sites and source not in spec.eval_only_sources
    ]
    report = inspect_channels(paths, list(ADAPTERS), training, holdout)
    typer.echo(f"wrote {report}")


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


@cards_app.command(
    "text",
    help="Render text-source dataset cards from manifests and a finished text corpus.",
)
def cards_text(
    config: ConfigOption = Path("configs/data/sources_text.yaml"),
    text_config: Annotated[
        Path, typer.Option("--text-config", help="Text pipeline config whose corpus is read.")
    ] = Path("configs/data/text_v2.yaml"),
    source: Annotated[
        str | None, typer.Option("--source", help="Source id; every enabled narrative source.")
    ] = None,
) -> None:
    """Render one card per enabled narrative text source.

    Args:
        config: Text source specification file.
        text_config: The text pipeline configuration naming the finished corpus.
        source: Restrict rendering to one source.

    Raises:
        typer.Exit: With code 1 if the source id is unknown.
    """
    from faultline.data.text.cards import build_text_card
    from faultline.download.nrc_text import CodeBookSpec, load_sources_text_config

    paths = ProjectPaths.resolve()
    spec = load_sources_text_config(config)
    if source and source not in spec.sources:
        typer.echo(f"unknown source {source!r}; configured: {', '.join(spec.sources)}")
        raise typer.Exit(code=1)
    names = [source] if source else list(spec.sources)
    for name in names:
        source_spec = spec.sources[name]
        if not source_spec.enabled or isinstance(source_spec, CodeBookSpec):
            continue
        card = build_text_card(name, source_spec, paths, text_config)
        typer.echo(f"{name}: wrote {card}")


@cards_app.command(
    "code-book",
    help="Measure the status code book against the fitted tokenizer and render its card.",
)
def cards_code_book(
    config: ConfigOption = Path("configs/data/sources_text.yaml"),
    tokenizer: Annotated[
        Path, typer.Option("--tokenizer", help="Fitted text tokenizer to measure with.")
    ] = Path("data/tokenizers/text_bpe_v1_22c56e49.json"),
    corpus: Annotated[
        str, typer.Option("--corpus", help="Finished corpus the tokenizer was fitted on.")
    ] = "operator_narratives",
) -> None:
    """Render the status code book's dataset card from its measurements.

    Args:
        config: Text source specification file naming the code book's sites.
        tokenizer: The fitted text tokenizer; its shards are read for token frequency.
        corpus: The finished corpus, for word frequency and the narrative comparison.
    """
    from faultline.data.text.code_book import CODE_BOOK_SOURCE, build_code_book_card
    from faultline.data.text.shards import shards_dir
    from faultline.download.nrc_text import CodeBookSpec, load_sources_text_config

    paths = ProjectPaths.resolve()
    spec = load_sources_text_config(config).sources[CODE_BOOK_SOURCE]
    if not isinstance(spec, CodeBookSpec):
        raise typer.BadParameter(f"{CODE_BOOK_SOURCE} is not a code-book source in {config}")
    tokenizer_file = (paths.repo_root / tokenizer).resolve()
    card = build_code_book_card(
        paths, spec, tokenizer_file, shards_dir(paths, tokenizer_file), corpus
    )
    typer.echo(f"{CODE_BOOK_SOURCE}: wrote {card}")


@text_app.command(
    "corpus",
    help="Combine staged per-source raw text into one JSONL corpus for `text run`.",
)
def text_corpus(
    source: Annotated[
        list[str], typer.Option("--source", help="Source id to include; repeat for several.")
    ],
    corpus_name: Annotated[
        str, typer.Option("--corpus-name", help="Name written as <corpus_name>.jsonl.")
    ],
) -> None:
    """Assemble named, already-staged text sources into one pipeline input file.

    Args:
        source: Source ids to combine, each already staged with `download text`.
        corpus_name: Output corpus name.

    Raises:
        typer.Exit: With code 1 if a named source has not been staged yet.
    """
    from faultline.download.nrc_text import assemble_corpus

    paths = ProjectPaths.resolve()
    try:
        destination = assemble_corpus(paths, source, corpus_name)
    except FileNotFoundError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc
    typer.echo(f"wrote {destination}")


@text_app.command(
    "bpe", help="Fit the byte-level BPE tokenizer on a finished corpus and report it."
)
def text_bpe(
    config: ConfigOption = Path("configs/tokenizer/text_bpe_v1.yaml"),
) -> None:
    """Fit the text BPE tokenizer and write it and its report.

    Args:
        config: The tokenizer configuration.
    """
    from faultline.data.text.bpe_fit import fit_text_bpe

    tokenizer_path, report_path = fit_text_bpe(ProjectPaths.resolve(), config)
    typer.echo(f"wrote {tokenizer_path}")
    typer.echo(f"wrote {report_path}")


@text_app.command(
    "shards", help="Write the text token shards and the window index, and report them."
)
def text_shards(
    config: ConfigOption = Path("configs/tokenizer/text_shards_v1.yaml"),
) -> None:
    """Write the text token shards and their report.

    Args:
        config: The shards configuration, naming the fitted tokenizer to encode with.
    """
    from faultline.data.text.shards import build_text_shards

    manifest, report = build_text_shards(ProjectPaths.resolve(), config)
    typer.echo(f"wrote {manifest}")
    typer.echo(f"wrote {report}")


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
    labels: Annotated[
        Path | None,
        typer.Option(
            "--labels",
            help="Override events.labels_config, relative to the repo root. The override is "
            "part of the hashed configuration, so the run id says it happened.",
        ),
    ] = None,
) -> None:
    """Run the telemetry pipeline and write per-stage reports.

    Args:
        config: Telemetry pipeline configuration.
        stage: Stage to execute, or ``all``.
        source: Restrict the run to a single source.
        labels: Event labelling file to use instead of the one the configuration names.
    """
    from faultline.data.common.stage import run_pipeline
    from faultline.data.telemetry.pipeline import build_stages, load_telemetry_config
    from faultline.runs import start_run

    paths = ProjectPaths.resolve()
    cfg = load_telemetry_config(config)
    if labels is not None:
        cfg = cfg.model_copy(
            update={"events": cfg.events.model_copy(update={"labels_config": labels.as_posix()})}
        )
    stages = build_stages(cfg, paths, stage, source=source)
    with start_run(config, cfg, stage, "telemetry", paths) as ctx:
        results = run_pipeline(stages, ctx)
        for result in results:
            typer.echo(f"{result.name}: {result.rows_in} -> {result.rows_out}")
        typer.echo(f"reports: {ctx.run_dir}")


@telemetry_app.command(
    "bins",
    help="Fit the quantile-bin tokenizer on the training split, write it, and report every "
    "candidate bin count.",
)
def telemetry_bins(
    config: ConfigOption = Path("configs/tokenizer/quantile_bins_v0.yaml"),
) -> None:
    """Fit the quantile-bin tokenizer and write it and its report.

    Args:
        config: The tokenizer configuration.
    """
    from faultline.data.telemetry.bins import fit_bins

    tokenizer, report = fit_bins(ProjectPaths.resolve(), config)
    typer.echo(f"wrote {tokenizer}")
    typer.echo(f"wrote {report}")


@telemetry_app.command(
    "shards",
    help="Write the fixed-order token shards and the window index, one file per site and "
    "split, and report them.",
)
def telemetry_shards(
    config: ConfigOption = Path("configs/tokenizer/quantile_bins_v0.yaml"),
) -> None:
    """Write the token shards and the window index, and their report.

    Args:
        config: The tokenizer configuration whose fitted tokenizer encodes the stream.
    """
    from faultline.data.telemetry.shards import build_shards

    manifest, report = build_shards(ProjectPaths.resolve(), config)
    typer.echo(f"wrote {manifest}")
    typer.echo(f"wrote {report}")


@model_app.command(
    "ladder",
    help="Train the size ladder -- language model, frozen probe, fine-tune and the "
    "randomly initialised control at every rung -- and write the ladder report.",
)
def model_ladder(
    config: ConfigOption = Path("configs/train/telemetry_v0.yaml"),
    device: Annotated[
        str | None,
        typer.Option("--device", help="Torch device; chosen automatically when omitted."),
    ] = None,
) -> None:
    """Run the whole ladder and write its report.

    Args:
        config: The training configuration, which names the model configuration.
        device: Torch device to run on.
    """
    from faultline.evaluation.ladder import run_ladder

    report = run_ladder(ProjectPaths.resolve(), config, device)
    typer.echo(f"wrote {report}")


@model_app.command(
    "text-pretrain",
    help="Pretrain the text-only decoder at S2 and S3 and write the M2d/M2e report.",
)
def model_text_pretrain(
    config: ConfigOption = Path("configs/train/text_v1.yaml"),
    device: Annotated[
        str | None,
        typer.Option("--device", help="Torch device; chosen automatically when omitted."),
    ] = None,
) -> None:
    """Run the text-only pretraining rungs and write their report.

    Args:
        config: The training configuration, which names the shards and model configs.
        device: Torch device to run on.
    """
    from faultline.evaluation.text_ladder import run_text_ladder

    _json_path, report = run_text_ladder(ProjectPaths.resolve(), config, device)
    typer.echo(f"wrote {report}")


@model_app.command(
    "text-curves",
    help="Loss against tokens seen and terminal slopes for the text ladder, read from its "
    "pretraining record; nothing is retrained.",
)
def model_text_curves(
    record: Annotated[
        Path, typer.Option("--record", help="The text pretraining record to read.")
    ] = Path("reports/data/text_pretrain_v1_20260916.json"),
) -> None:
    """Write the text ladder's curves report and figure.

    Args:
        record: The ``text_pretrain_v*.json`` the runs wrote.
    """
    from faultline.evaluation.text_curves import write_text_curves

    paths = ProjectPaths.resolve()
    report, figure = write_text_curves(paths, (paths.repo_root / record).resolve())
    typer.echo(f"wrote {report} and {figure}")


@model_app.command(
    "status-nll",
    help="H3' measured behaviourally: single-token-word rate per status string, and per-string "
    "NLL under the text-only checkpoints against held-out narrative text. No training.",
)
def model_status_nll(
    tokenizer: Annotated[
        Path, typer.Option("--tokenizer", help="The frozen text tokenizer.")
    ] = Path("data/tokenizers/text_bpe_v1_22c56e49.json"),
    record: Annotated[Path, typer.Option("--record", help="The text pretraining record.")] = Path(
        "reports/data/text_pretrain_v1_20260916.json"
    ),
    device: Annotated[str | None, typer.Option("--device", help="Torch device.")] = None,
) -> None:
    """Write the behavioural H3' report.

    Args:
        tokenizer: The frozen text tokenizer file.
        record: The ``text_pretrain_v*.json`` the text runs wrote.
        device: Torch device; chosen automatically when omitted.
    """
    import torch

    from faultline.evaluation.status_nll import write_behaviour_report

    paths = ProjectPaths.resolve()
    checkpoints = {
        rung: paths.checkpoints_dir / "text" / f"{rung}_text_seed1.pt" for rung in ("S2", "S3")
    }
    chosen = torch.device(device or ("cuda" if torch.cuda.is_available() else "cpu"))
    report, json_path = write_behaviour_report(
        paths,
        (paths.repo_root / tokenizer).resolve(),
        "operator_narratives",
        checkpoints,
        (paths.repo_root / record).resolve(),
        chosen,
        _joint_layout(paths),
    )
    typer.echo(f"wrote {report} and {json_path}")


def _joint_layout(paths: ProjectPaths, bins_config: Path | None = None) -> VocabLayout:
    """The M3 joint layout: the M1 bins tokenizer's blocks plus the full text block.

    Args:
        paths: Resolved project paths.
        bins_config: The M1 quantile bin configuration; ``quantile_bins_v2`` when omitted.

    Returns:
        The layout.
    """
    from faultline.config import load_config
    from faultline.data.telemetry.bins import QuantileBinsConfig
    from faultline.data.telemetry.shards import tokenizer_path
    from faultline.tokenizers.joint_check import joint_layout
    from faultline.tokenizers.layout import TEXT_CAPACITY
    from faultline.tokenizers.quantile_bins import QuantileBinTokenizer

    config_path = bins_config or Path("configs/tokenizer/quantile_bins_v2.yaml")
    config = load_config(paths.repo_root / config_path, QuantileBinsConfig)
    bins = QuantileBinTokenizer.load(tokenizer_path(paths, config))
    return joint_layout(bins, TEXT_CAPACITY)


@check_app.command(
    "text-migration",
    help="Locate the text checkpoints' separator row, migrate them onto the joint vocabulary, "
    "and check the migrated models score text exactly as before. Exits 1 on any failure.",
)
def check_text_migration(
    tokenizer: Annotated[
        Path, typer.Option("--tokenizer", help="The frozen text tokenizer.")
    ] = Path("data/tokenizers/text_bpe_v1_22c56e49.json"),
    record: Annotated[
        Path, typer.Option("--record", help="The behavioural H3' record to compare against.")
    ] = Path("reports/data/h3prime_behavioural_v1_20260916.json"),
    device: Annotated[str | None, typer.Option("--device", help="Torch device.")] = None,
) -> None:
    """Write the migration check report.

    Args:
        tokenizer: The frozen text tokenizer file.
        record: The E1 JSON record.
        device: Torch device; chosen automatically when omitted.

    Raises:
        typer.Exit: With code 1 if any check fails.
    """
    import torch

    from faultline.evaluation.text_migration import write_migration_report

    paths = ProjectPaths.resolve()
    checkpoints = {
        rung: paths.checkpoints_dir / "text" / f"{rung}_text_seed1.pt" for rung in ("S2", "S3")
    }
    chosen = torch.device(device or ("cuda" if torch.cuda.is_available() else "cpu"))
    report, check = write_migration_report(
        paths,
        (paths.repo_root / tokenizer).resolve(),
        checkpoints,
        _joint_layout(paths),
        (paths.repo_root / record).resolve(),
        chosen,
    )
    typer.echo(f"wrote {report}")
    if not check.passed():
        raise typer.Exit(code=1)


@model_app.command(
    "mixture-shards",
    help="Write the M3 mixture's txt and tel+status shards and every stream's run index, "
    "and report per-stream token counts and per-arm token budgets. Trains nothing.",
)
def model_mixture_shards(
    config: ConfigOption = Path("configs/train/joint_v0.yaml"),
) -> None:
    """Build the mixture shards and write their report.

    Args:
        config: The joint mixture configuration.
    """
    from faultline.data.joint.mixture_shards import build_mixture_shards

    report, record = build_mixture_shards(ProjectPaths.resolve(), config)
    typer.echo(f"wrote {report} and {record}")


@check_app.command(
    "joint-vocab",
    help="Verify ADR-0003 v2 on disk: no id collision, M1 telemetry ids bit-identical, the "
    "text region exactly full, and a telemetry+text round trip. Exits 1 on any failure.",
)
def check_joint_vocab(
    bins_config: Annotated[
        Path, typer.Option("--bins-config", help="The M1 tokenizer configuration.")
    ] = Path("configs/tokenizer/quantile_bins_v2.yaml"),
    text_tokenizer: Annotated[
        Path, typer.Option("--text-tokenizer", help="The fitted M2 text tokenizer.")
    ] = Path("data/tokenizers/text_bpe_v1_22c56e49.json"),
    checkpoints: Annotated[
        Path, typer.Option("--checkpoints", help="The M1 ladder checkpoint directory.")
    ] = Path("checkpoints/ladder_v0_70860821"),
) -> None:
    """Verify the joint vocabulary and write its report.

    Args:
        bins_config: The quantile bin configuration whose shards and tokenizer are read.
        text_tokenizer: The text tokenizer.
        checkpoints: The M1 checkpoints whose embedding rows are compared.

    Raises:
        typer.Exit: With code 1 if any assertion fails.
    """
    from faultline.config import load_config
    from faultline.data.telemetry.bins import QuantileBinsConfig
    from faultline.data.telemetry.shards import shards_dir, tokenizer_path
    from faultline.tokenizers.joint_check import verify_joint_vocabulary

    paths = ProjectPaths.resolve()
    config = load_config(paths.repo_root / bins_config, QuantileBinsConfig)
    bins = tokenizer_path(paths, config)
    report, checks = verify_joint_vocabulary(
        paths,
        bins,
        (paths.repo_root / text_tokenizer).resolve(),
        shards_dir(paths, bins),
        (paths.repo_root / checkpoints).resolve(),
        config.excluded,
    )
    for result in checks:
        typer.echo(f"{'PASS' if result.passed else 'FAIL'}  {result.name}")
    typer.echo(f"wrote {report}")
    if not all(result.passed for result in checks):
        raise typer.Exit(code=1)


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

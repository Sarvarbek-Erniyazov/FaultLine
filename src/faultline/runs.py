"""Run identity, run directories and the machine-readable run record.

Every pipeline invocation gets a directory under ``reports/data/<run_id>/`` holding
a verbatim copy of its YAML, one Markdown stats report per stage, ``run.log`` and
``run.json``. A run never edits its own configuration: the copy is the evidence of
what was actually executed.
"""

from __future__ import annotations

import json
import platform
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Any, Self

from faultline.config import RunMeta, config_hash
from faultline.logging_utils import get_logger, log_to_file
from faultline.paths import Modality, ProjectPaths

logger = get_logger(__name__)


def git_sha(repo_root: Path | None = None, short: bool = False) -> str:
    """Return the current commit SHA, or ``unknown`` outside a usable checkout.

    Args:
        repo_root: Directory to run git in; the process working directory when omitted.
        short: Return the abbreviated SHA instead of the full one.

    Returns:
        The commit SHA, or the literal string ``unknown``.
    """
    cmd = ["git", "rev-parse", "--short", "HEAD"] if short else ["git", "rev-parse", "HEAD"]
    try:
        completed = subprocess.run(
            cmd,
            cwd=str(repo_root) if repo_root else None,
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    if completed.returncode != 0:
        return "unknown"
    return completed.stdout.strip() or "unknown"


def new_run_id(stage: str, modality: Modality, cfg_hash: str, now: datetime | None = None) -> str:
    """Build the identifier for one run.

    Args:
        stage: Stage or command name, for example ``clean`` or ``all``.
        modality: Data modality the run operates on.
        cfg_hash: Short configuration hash from :func:`faultline.config.config_hash`.
        now: Timestamp to use; the current UTC time when omitted.

    Returns:
        An identifier of the form ``<YYYYMMDD-HHMMSS>_<stage>_<modality>_<hash8>``.
    """
    stamp = (now or datetime.now(tz=UTC)).strftime("%Y%m%d-%H%M%S")
    return f"{stamp}_{stage}_{modality}_{cfg_hash}"


@dataclass
class StageRecord:
    """Counts and extras reported by one stage of a run.

    Attributes:
        name: Stage name.
        rows_in: Records read by the stage.
        rows_out: Records written by the stage.
        extra: Stage-specific counters, serialized verbatim into ``run.json``.
        report_path: File name of the stage report, if one was written.
    """

    name: str
    rows_in: int
    rows_out: int
    extra: dict[str, Any] = field(default_factory=dict)
    report_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return the JSON-serializable form of this record.

        Returns:
            A mapping with counts, the derived drop count and stage extras.
        """
        return {
            "name": self.name,
            "rows_in": self.rows_in,
            "rows_out": self.rows_out,
            "dropped": self.rows_in - self.rows_out,
            "extra": self.extra,
            "report_path": self.report_path,
        }


class RunContext:
    """Context manager owning one run directory, its log file and its run record.

    Attributes:
        meta: Immutable run identity.
        run_dir: Directory holding the copied config, reports and logs.
        paths: Project path resolver used by stages for input and output locations.
        stages: Records appended by each stage as it completes.
    """

    def __init__(self, meta: RunMeta, run_dir: Path, paths: ProjectPaths) -> None:
        """Initialize the context.

        Use :func:`start_run` rather than constructing this directly.

        Args:
            meta: Run identity.
            run_dir: Run report directory, already created.
            paths: Resolved project paths.
        """
        self.meta = meta
        self.run_dir = run_dir
        self.paths = paths
        self.stages: list[StageRecord] = []
        self._started = time.perf_counter()
        self._log_ctx = log_to_file(run_dir / "run.log")

    def __enter__(self) -> Self:
        """Attach the run log handler.

        Returns:
            This context.
        """
        self._log_ctx.__enter__()
        logger.info("run %s started (config hash %s)", self.meta.run_id, self.meta.config_hash)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Write ``run.json`` and detach the run log handler.

        Args:
            exc_type: Exception type raised inside the context, if any.
            exc: Exception instance raised inside the context, if any.
            tb: Traceback of that exception, if any.
        """
        elapsed = time.perf_counter() - self._started
        status = "ok" if exc is None else "failed"
        record: dict[str, Any] = {
            "run_id": self.meta.run_id,
            "status": status,
            "error": None if exc is None else f"{type(exc).__name__}: {exc}",
            "config_path": self.meta.config_path,
            "config_hash": self.meta.config_hash,
            "git_sha": self.meta.git_sha,
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "started_at": self.meta.created_at.isoformat(),
            "ended_at": datetime.now(tz=UTC).isoformat(),
            "elapsed_seconds": round(elapsed, 3),
            "stages": [stage.to_dict() for stage in self.stages],
        }
        (self.run_dir / "run.json").write_text(
            json.dumps(record, indent=2) + "\n", encoding="utf-8"
        )
        logger.info("run %s %s in %.2fs -> %s", self.meta.run_id, status, elapsed, self.run_dir)
        self._log_ctx.__exit__(exc_type, exc, tb)

    def record_stage(
        self,
        name: str,
        rows_in: int,
        rows_out: int,
        extra: dict[str, Any] | None = None,
        report_path: Path | None = None,
    ) -> StageRecord:
        """Append one stage's counts to the run record.

        Args:
            name: Stage name.
            rows_in: Records read.
            rows_out: Records written.
            extra: Stage-specific counters.
            report_path: Path of the stage report, if one was written.

        Returns:
            The stored record.
        """
        record = StageRecord(
            name=name,
            rows_in=rows_in,
            rows_out=rows_out,
            extra=dict(extra or {}),
            report_path=None if report_path is None else report_path.name,
        )
        self.stages.append(record)
        return record

    def write_report(self, stage: str, markdown: str) -> Path:
        """Write a stage's Markdown stats report into the run directory.

        Args:
            stage: Stage name, used as the file stem.
            markdown: Report body.

        Returns:
            The path written.
        """
        path = self.run_dir / f"{stage}_stats_report.md"
        path.write_text(markdown, encoding="utf-8")
        logger.info("wrote %s", path.name)
        return path


def start_run(
    config_path: Path,
    config_obj: Any,
    stage: str,
    modality: Modality,
    paths: ProjectPaths | None = None,
) -> RunContext:
    """Create a run directory, copy the driving YAML into it and build the context.

    Args:
        config_path: YAML file that drives the run.
        config_obj: Validated configuration, hashed into the run identifier.
        stage: Stage or command name.
        modality: Data modality.
        paths: Resolved project paths; resolved from the environment when omitted.

    Returns:
        An unentered :class:`RunContext`.
    """
    resolved = paths or ProjectPaths.resolve()
    cfg_hash = config_hash(config_obj)
    run_id = new_run_id(stage, modality, cfg_hash)
    run_dir = resolved.run_dir(run_id)
    (run_dir / config_path.name).write_text(
        config_path.read_text(encoding="utf-8"), encoding="utf-8"
    )
    try:
        rel = config_path.resolve().relative_to(resolved.repo_root).as_posix()
    except ValueError:
        rel = config_path.as_posix()
    meta = RunMeta(
        run_id=run_id,
        config_path=rel,
        config_hash=cfg_hash,
        git_sha=git_sha(resolved.repo_root),
    )
    return RunContext(meta=meta, run_dir=run_dir, paths=resolved)

"""Structured logging for pipelines.

A Rich handler is used when stderr is a terminal and a plain handler otherwise, so
that captured output stays greppable. When a run is active, a file handler mirrors
every record into ``<run_dir>/run.log``. Nothing in ``src/`` uses ``print``.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from rich.logging import RichHandler

_CONFIGURED = False
_PLAIN_FORMAT = "%(asctime)s %(levelname)-8s %(name)s | %(message)s"
_FILE_FORMAT = "%(asctime)s %(levelname)-8s %(name)s | %(message)s"


def configure_logging(level: int = logging.INFO) -> None:
    """Install the root handler once per process.

    Args:
        level: Minimum level emitted by the root logger.
    """
    global _CONFIGURED
    if _CONFIGURED:
        return
    root = logging.getLogger("faultline")
    root.setLevel(level)
    handler: logging.Handler
    if sys.stderr.isatty():
        handler = RichHandler(rich_tracebacks=True, show_path=False, log_time_format="%H:%M:%S")
        handler.setFormatter(logging.Formatter("%(name)s | %(message)s"))
    else:
        handler = logging.StreamHandler(stream=sys.stderr)
        handler.setFormatter(logging.Formatter(_PLAIN_FORMAT))
    root.addHandler(handler)
    root.propagate = False
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Return a namespaced logger, configuring the root handler on first use.

    Args:
        name: Module name, typically ``__name__``.

    Returns:
        A logger under the ``faultline`` namespace.
    """
    configure_logging()
    suffix = name.removeprefix("faultline.").removeprefix("faultline")
    return logging.getLogger(f"faultline.{suffix}" if suffix else "faultline")


@contextmanager
def log_to_file(path: Path, level: int = logging.DEBUG) -> Iterator[Path]:
    """Mirror log records into a file for the duration of the context.

    Args:
        path: Destination log file; parent directories are created.
        level: Minimum level written to the file.

    Yields:
        The log file path.
    """
    configure_logging()
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setLevel(level)
    handler.setFormatter(logging.Formatter(_FILE_FORMAT))
    root = logging.getLogger("faultline")
    root.addHandler(handler)
    try:
        yield path
    finally:
        handler.close()
        root.removeHandler(handler)

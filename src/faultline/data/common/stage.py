"""The stage contract shared by the text and telemetry pipelines.

A pipeline is an ordered list of stages. Each stage reads only from the previous
stage's directory, writes to its own, and must produce a Markdown report: a stage
that cannot describe what it did is not allowed in a pipeline.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar

from faultline.paths import Modality
from faultline.runs import RunContext


@dataclass
class StageResult:
    """What one stage did, in a form both reports and ``run.json`` can consume.

    Attributes:
        name: Stage name.
        rows_in: Records read from the input location.
        rows_out: Records written to the output location.
        counters: Integer counters, typically one per drop reason or edit type.
        details: Arbitrary structured detail used by the stage's own report section.
        outputs: Files the stage wrote.
    """

    name: str
    rows_in: int
    rows_out: int
    counters: dict[str, int] = field(default_factory=dict)
    details: dict[str, Any] = field(default_factory=dict)
    outputs: list[Path] = field(default_factory=list)

    @property
    def dropped(self) -> int:
        """Number of records the stage removed."""
        return self.rows_in - self.rows_out

    @property
    def retention(self) -> float:
        """Fraction of input records that survived the stage, or 0.0 for an empty input."""
        return self.rows_out / self.rows_in if self.rows_in else 0.0


class Stage(ABC):
    """Base class for a single pipeline stage.

    Subclasses set :attr:`name` and :attr:`modality`, implement :meth:`run` for the
    work and :meth:`report` for the Markdown summary. :meth:`execute` wires both into
    the active run so that every stage leaves the same evidence behind.
    """

    name: ClassVar[str] = "stage"
    modality: ClassVar[Modality] = "text"

    @abstractmethod
    def run(self, ctx: RunContext) -> StageResult:
        """Perform the stage's work.

        Args:
            ctx: Active run context providing paths and the run directory.

        Returns:
            The stage's result counts and details.
        """

    @abstractmethod
    def report(self, result: StageResult) -> str:
        """Render the stage's Markdown stats report.

        Args:
            result: The result returned by :meth:`run`.

        Returns:
            A complete Markdown document for this stage.
        """

    def execute(self, ctx: RunContext) -> StageResult:
        """Run the stage, write its report and record it in the run.

        Args:
            ctx: Active run context.

        Returns:
            The stage's result.
        """
        result = self.run(ctx)
        report_path = ctx.write_report(result.name, self.report(result))
        ctx.record_stage(
            name=result.name,
            rows_in=result.rows_in,
            rows_out=result.rows_out,
            extra={"counters": result.counters, "outputs": [p.name for p in result.outputs]},
            report_path=report_path,
        )
        return result


def run_pipeline(stages: Sequence[Stage], ctx: RunContext) -> list[StageResult]:
    """Execute stages in order against one run context.

    Args:
        stages: Stages to execute, in pipeline order.
        ctx: Active run context.

    Returns:
        One result per stage, in the same order.
    """
    return [stage.execute(ctx) for stage in stages]

"""Collapsing an export that repeats its timestamp labels, and proving nothing is lost.

The Kelmarsh 2023 and 2024 exports repeat every 10-minute label about 41 times:
2,174,760 rows over 52,560 labels. Read on 2026-09-10, the file is 80 cumulative
blocks, each restarting at 1 January and running 655 labels further than the one
before, followed by one complete year (655 x (1 + ... + 80) = 2,122,200 surplus
rows, exactly). Every measured channel carries a value on one of a label's rows only;
the repeats carry nine derived availability columns and nothing else.

That is an export-format change, not duplicated data, and it is handled as one:

1. drop the rows that are null in every ingested column;
2. **assert** that no (label, column) pair then holds more than one *distinct* non-null
   value;
3. collapse to one row per label, taking the one value each column has.

Step 2 is what makes step 3 lossless, and it is not skipped. If it fails, two rows
disagree about the same instant -- that is genuine duplication, and it belongs to the
duplicate-timestamp rule in the cleaning stage, not to a collapse that would quietly
pick one of them. :class:`RepeatedLabelConflictError` stops the ingest instead.

The assertion counts distinct values, not non-null cells (tightened at M1a step 6c). The
repeated Kelmarsh rows carry nine derived availability columns with the *same* value on
several rows of a label; a rule that counted cells would call that a conflict, and it
could then only hold on the ingested channels. Counting distinct values, it holds on all
311 columns of every repeated file (``reports/data/resolved_kelmarsh_*.md``), and a
collapse that keeps the one value loses nothing either way.

The same arithmetic is reported for every file, repeated or not, so an export that
does not repeat shows ``rows_raw == labels_distinct`` and the claim is checked rather
than assumed.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import pandas as pd


class RepeatedLabelConflictError(RuntimeError):
    """Two rows carry different values for the same label and column: genuine duplication.

    A ``RuntimeError`` rather than a ``ValueError`` on purpose: the ingest stage
    logs and skips members that raise ``ValueError``, and this must stop the run.
    """


@dataclass(frozen=True)
class CollapseStats:
    """Row accounting for one file.

    Attributes:
        rows_raw: Rows read.
        rows_after_null_drop: Rows carrying at least one non-null ingested value.
        labels_distinct: Distinct labels among the rows read.
        rows_out: Rows after collapsing, one per label that carries any value.
        labels_repeated: Labels still appearing on more than one row after the null
            drop, all of which were proven to hold one distinct value per column before
            collapsing.
    """

    rows_raw: int
    rows_after_null_drop: int
    labels_distinct: int
    rows_out: int
    labels_repeated: int

    @property
    def repeated_export(self) -> bool:
        """Whether the file repeated labels at all."""
        return self.rows_raw > self.labels_distinct


def collapse_repeated_labels(
    frame: pd.DataFrame, key_columns: Sequence[str], value_columns: Sequence[str]
) -> tuple[pd.DataFrame, CollapseStats]:
    """Drop all-null rows, prove the repeats single-valued, and collapse to one row per key.

    Args:
        frame: Rows as read, keyed by ``key_columns`` (the timestamp label, plus the
            turbine where one file carries several).
        key_columns: Columns identifying one observation.
        value_columns: The ingested value columns. A row null in all of them carries
            nothing and is dropped.

    Returns:
        One row per key that carries any value, sorted by key, and the accounting.

    Raises:
        RepeatedLabelConflictError: If any key holds more than one distinct non-null value
            in any value column after the null drop.
    """
    keys = list(key_columns)
    values = [column for column in value_columns if column in frame.columns]
    rows_raw = len(frame)
    labels_distinct = int(frame.drop_duplicates(subset=keys).shape[0]) if rows_raw else 0

    kept = frame[frame[values].notna().any(axis=1)] if values else frame.iloc[0:0]
    rows_after = len(kept)
    repeated = kept.duplicated(subset=keys, keep=False)
    labels_repeated = int(kept.loc[repeated, keys].drop_duplicates().shape[0])

    if labels_repeated:
        group = kept.loc[repeated]
        distinct = group.groupby([group[k] for k in keys])[values].nunique(dropna=True)
        clashes = distinct.gt(1)
        if clashes.to_numpy().any():
            columns = [str(column) for column in clashes.columns[clashes.any()]]
            examples = [str(key) for key in clashes.index[clashes.any(axis=1)][:3]]
            raise RepeatedLabelConflictError(
                f"{int(clashes.any(axis=1).sum())} labels carry two different values in "
                f"columns {columns} (for example {examples}). This is genuine duplication, "
                "not a repeated export: it belongs to the duplicate-timestamp rule, and "
                "ingest stops rather than pick a value."
            )
        # At most one distinct value per (key, column), so first() keeps every value.
        collapsed = kept.groupby(keys, sort=True, as_index=False, dropna=False).first()
    else:
        collapsed = kept.sort_values(keys)

    stats = CollapseStats(
        rows_raw=rows_raw,
        rows_after_null_drop=rows_after,
        labels_distinct=labels_distinct,
        rows_out=len(collapsed),
        labels_repeated=labels_repeated,
    )
    return collapsed.reset_index(drop=True), stats

"""Penmanshiel wind farm adapter (Cubico Sustainable Investments, CC BY 4.0).

Fourteen Senvion MM82 turbines, 2016-2024, published as zips split by turbine
range as well as by year, so a single year spans two archives. Turbine WT03 is
absent from the record.

Same publisher and the same Greenbyte export as Kelmarsh, and the M0 inspection
confirmed it rather than assuming it: the preambles, the commented turbine-data header
in all 98 turbine-year members, and the status table columns match Kelmarsh's
(``reports/data/raw_inventory_penmanshiel_20260910.md``). The channel map was resolved
from Penmanshiel's own signal-mapping workbook and headers. So the loaders are the
shared :class:`GreenbyteAdapter`, not a copy of Kelmarsh's.

Tier 1 stages 2016-2022. The 2023-2024 exports are tier 2 and not staged; Kelmarsh's
2023-2024 exports from the same publisher repeat every label about 41 times, and the
same is predicted here. The shared reader collapses that layout after proving it
lossless, and the prediction is checked when those files land (see
``configs/data/sources_telemetry.yaml``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from faultline.data.telemetry.adapters.greenbyte import GreenbyteAdapter


@dataclass
class PenmanshielAdapter(GreenbyteAdapter):
    """Reads the Penmanshiel record into the canonical schema."""

    source_id: ClassVar[str] = "penmanshiel"
    site_name: ClassVar[str] = "Penmanshiel"

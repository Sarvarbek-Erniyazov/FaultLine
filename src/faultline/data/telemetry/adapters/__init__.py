"""Per-source readers that map published archives onto the canonical schema.

The registry below is the single place that knows which sources exist. Adding a
site means adding an adapter module, a channel map YAML and one entry here.
"""

from __future__ import annotations

from pathlib import Path

from faultline.data.telemetry.adapters.base import (
    BaseAdapter,
    MemberKind,
    RawMember,
    SourceAdapter,
    load_channel_map,
    open_member,
)
from faultline.data.telemetry.adapters.care import CareAdapter
from faultline.data.telemetry.adapters.hill_of_towie import HillOfTowieAdapter
from faultline.data.telemetry.adapters.kelmarsh import KelmarshAdapter
from faultline.data.telemetry.adapters.penmanshiel import PenmanshielAdapter

#: Every implemented adapter, keyed by source id.
ADAPTERS: dict[str, type[BaseAdapter]] = {
    KelmarshAdapter.source_id: KelmarshAdapter,
    PenmanshielAdapter.source_id: PenmanshielAdapter,
    HillOfTowieAdapter.source_id: HillOfTowieAdapter,
    CareAdapter.source_id: CareAdapter,
}


def get_adapter(source: str, configs_dir: Path) -> BaseAdapter:
    """Build the adapter for a source with its channel map loaded.

    Args:
        source: Source identifier.
        configs_dir: The repository ``configs`` directory.

    Returns:
        A configured adapter.

    Raises:
        KeyError: If no adapter is registered for the source.
    """
    try:
        adapter_class = ADAPTERS[source]
    except KeyError as exc:
        raise KeyError(f"no adapter for source {source!r}; known: {sorted(ADAPTERS)}") from exc
    return adapter_class.from_configs(configs_dir)


__all__ = [
    "ADAPTERS",
    "BaseAdapter",
    "CareAdapter",
    "HillOfTowieAdapter",
    "KelmarshAdapter",
    "MemberKind",
    "PenmanshielAdapter",
    "RawMember",
    "SourceAdapter",
    "get_adapter",
    "load_channel_map",
    "open_member",
]

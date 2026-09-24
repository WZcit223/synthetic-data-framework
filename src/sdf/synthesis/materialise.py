"""Materialise a ``GenerationSpec`` into a registry of canonical entity streams.

This is the seam between the Synthesis Layer and the Foundation Layer: the
generator produces a ``SyntheticWarehouse`` bundle, and every entity list is
registered as a synthetic ``DataSource`` so the Application Layer reads it the
same way it would read a real feed.
"""

from __future__ import annotations

from sdf.foundation.registry import DataSourceRegistry
from .registry import SynthesizerRegistry, default_registry
from .spec import GenerationSpec
from .warehouse import SyntheticWarehouse

DEFAULT_WAREHOUSE_SYNTHESIZER = "warehouse-spec"


def build_registry(
    spec: GenerationSpec,
    *,
    synthesizer: str = DEFAULT_WAREHOUSE_SYNTHESIZER,
    synthesizers: SynthesizerRegistry | None = None,
) -> tuple[SyntheticWarehouse, DataSourceRegistry]:
    """Generate the world described by ``spec`` with ``synthesizer`` and register all six entity streams.

    ``synthesizers`` is the registry to create it from (default ``default_registry()``); a
    synthesizer that does not produce a ``SyntheticWarehouse`` is refused with ``ValueError``.
    """
    reg = synthesizers if synthesizers is not None else default_registry()
    info = reg.info(synthesizer)
    if info.produces != "warehouse":
        raise ValueError(f"{synthesizer} produces a {info.produces}, not a warehouse; choose a warehouse synthesizer")
    wh = reg.create(synthesizer, spec=spec).sample()
    if not isinstance(wh, SyntheticWarehouse):
        raise ValueError(f"{synthesizer} returned {type(wh).__name__}, not a SyntheticWarehouse")
    reg = DataSourceRegistry()
    reg.register("syn_skus", "SKU", wh.skus)
    reg.register("syn_locations", "Location", wh.locations)
    reg.register("syn_inventory", "InventorySnapshot", wh.inventory)
    reg.register("syn_inbound", "InboundOrder", wh.inbound)
    reg.register("syn_outbound", "OutboundOrder", wh.outbound)
    reg.register("syn_sensors", "SensorReading", wh.sensors)
    return wh, reg

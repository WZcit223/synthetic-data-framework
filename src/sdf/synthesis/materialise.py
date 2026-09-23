"""Materialise a ``GenerationSpec`` into a registry of canonical entity streams.

This is the seam between the Synthesis Layer and the Foundation Layer: the
generator produces a ``SyntheticWarehouse`` bundle, and every entity list is
registered as a synthetic ``DataSource`` so the Application Layer reads it the
same way it would read a real feed.
"""

from __future__ import annotations

from sdf.foundation.registry import DataSourceRegistry
from .spec import GenerationSpec
from .warehouse import SyntheticWarehouse, WarehouseGenerator


def build_registry(spec: GenerationSpec) -> tuple[SyntheticWarehouse, DataSourceRegistry]:
    """Generate the world described by ``spec`` and register all six entity streams."""
    wh = WarehouseGenerator(spec).generate()
    reg = DataSourceRegistry()
    reg.register("syn_skus", "SKU", wh.skus)
    reg.register("syn_locations", "Location", wh.locations)
    reg.register("syn_inventory", "InventorySnapshot", wh.inventory)
    reg.register("syn_inbound", "InboundOrder", wh.inbound)
    reg.register("syn_outbound", "OutboundOrder", wh.outbound)
    reg.register("syn_sensors", "SensorReading", wh.sensors)
    return wh, reg

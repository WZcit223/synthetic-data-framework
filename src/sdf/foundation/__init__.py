"""Foundation Layer: canonical entities and the multi-source data registry."""

from .registry import DataSource, DataSourceRegistry
from .schema import (
    SKU,
    InboundOrder,
    InventorySnapshot,
    Location,
    OutboundOrder,
    SensorReading,
)

__all__ = [
    "SKU",
    "Location",
    "InventorySnapshot",
    "InboundOrder",
    "OutboundOrder",
    "SensorReading",
    "DataSourceRegistry",
    "DataSource",
]

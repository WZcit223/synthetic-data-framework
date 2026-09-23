"""Foundation Layer: canonical entities and the multi-source data registry."""

from sdf.foundation.registry import DataSource, DataSourceRegistry
from sdf.foundation.schema import (
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

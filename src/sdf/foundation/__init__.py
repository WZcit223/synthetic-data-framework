"""Foundation Layer: canonical entities and the multi-source data registry."""

from sdf.foundation.schema import (
    SKU,
    Location,
    InventorySnapshot,
    InboundOrder,
    OutboundOrder,
    SensorReading,
)
from sdf.foundation.registry import DataSourceRegistry, DataSource

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

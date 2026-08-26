"""Canonical warehouse entities (Foundation Layer).

These dataclasses define the *contract* every layer speaks. Synthetic data and
(later) real data must both materialise into these shapes, which is what lets
the platform "overlay multiple sources" — a synthetic inventory feed and a real
one are interchangeable as long as they satisfy these schemas.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Dict, Optional


class Entity:
    """Mixin giving every entity a uniform ``to_dict`` for serialisation."""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SKU(Entity):
    """A stock-keeping unit — the catalogue view of a product."""

    sku_id: str
    name: str
    category: str
    unit_cost: float
    unit_price: float
    weight_kg: float
    volume_m3: float
    abc_class: str  # A/B/C velocity class (Pareto)
    shelf_life_days: Optional[int] = None


@dataclass
class Location(Entity):
    """A physical storage location (aisle/rack/shelf/bin)."""

    location_id: str
    zone: str
    aisle: str
    rack: str
    level: int
    capacity_units: int
    temperature_controlled: bool = False


@dataclass
class InventorySnapshot(Entity):
    """On-hand quantity for one SKU at one location at a point in time."""

    ts: datetime
    sku_id: str
    location_id: str
    on_hand: int
    reserved: int
    in_transit: int

    @property
    def available(self) -> int:
        return max(0, self.on_hand - self.reserved)


@dataclass
class InboundOrder(Entity):
    """A replenishment / receiving order."""

    order_id: str
    ts: datetime
    sku_id: str
    quantity: int
    supplier_id: str
    lead_time_days: int
    status: str  # created | in_transit | received


@dataclass
class OutboundOrder(Entity):
    """A customer / picking order line."""

    order_id: str
    ts: datetime
    sku_id: str
    quantity: int
    channel: str  # ecommerce | wholesale | store
    priority: str  # standard | express
    status: str  # created | picked | shipped | cancelled


@dataclass
class SensorReading(Entity):
    """A multimodal placeholder: IoT / vision-derived signal for a location.

    In the framework these are synthetic scalars. The real system replaces this with
    edge-device telemetry and CV model outputs (e.g. shelf-occupancy from
    camera frames, defect scores from the fabric-inspection pipeline).
    """

    ts: datetime
    location_id: str
    modality: str  # temperature | humidity | occupancy | vision_occupancy
    value: float
    unit: str
    meta: Dict[str, Any] = field(default_factory=dict)

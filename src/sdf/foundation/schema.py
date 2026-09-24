"""Canonical warehouse entities (Foundation Layer).

These dataclasses define the *contract* every layer speaks. Synthetic data and
(later) real data must both materialise into these shapes, which is what lets
the platform "overlay multiple sources" — a synthetic inventory feed and a real
one are interchangeable as long as they satisfy these schemas.

Each entity checks its fields when it is built and raises ``ValueError`` naming
the entity and the field, so a record no warehouse can have never enters the
platform. The allowed values of the enumerated fields are the module constants
below.

DATA-HOOK[D3]: these checks are the framework's data contract; production data
is held to a schema registry and dataset-level validation (Great Expectations /
Pandera) at the point it enters the registry.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

ABC_CLASSES = frozenset({"A", "B", "C", "?"})  # "?" = unclassified (an imported SKU)
INBOUND_STATUSES = frozenset({"created", "in_transit", "received"})
OUTBOUND_CHANNELS = frozenset({"ecommerce", "wholesale", "store"})
OUTBOUND_PRIORITIES = frozenset({"standard", "express"})
OUTBOUND_STATUSES = frozenset({"created", "picked", "shipped", "cancelled"})
SENSOR_MODALITIES = frozenset({"temperature", "humidity", "occupancy", "vision_occupancy"})


class Entity:
    """Mixin giving every entity a uniform ``to_dict`` for serialisation."""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def _fail(self, name: str, problem: str) -> None:
        raise ValueError(f"{type(self).__name__}.{name} {problem}, got {getattr(self, name)!r}")

    def _identifier(self, *names: str) -> None:
        for name in names:
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                self._fail(name, "must be a non-empty string")

    def _not_negative(self, *names: str) -> None:
        for name in names:
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                self._fail(name, "must be a finite number that is not negative")

    def _positive(self, *names: str) -> None:
        for name in names:
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                self._fail(name, "must be a finite positive number")

    def _one_of(self, name: str, allowed: frozenset[str]) -> None:
        if getattr(self, name) not in allowed:
            self._fail(name, f"must be one of {sorted(allowed)}")


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
    abc_class: str  # A/B/C velocity class (Pareto), "?" when unclassified
    shelf_life_days: int | None = None

    def __post_init__(self) -> None:
        self._identifier("sku_id")
        self._not_negative("unit_cost", "unit_price", "weight_kg", "volume_m3")
        self._one_of("abc_class", ABC_CLASSES)
        if self.shelf_life_days is not None:
            self._positive("shelf_life_days")


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

    def __post_init__(self) -> None:
        self._identifier("location_id")
        self._not_negative("level", "capacity_units")


@dataclass
class InventorySnapshot(Entity):
    """On-hand quantity for one SKU at one location at a point in time."""

    ts: datetime
    sku_id: str
    location_id: str
    on_hand: int
    reserved: int
    in_transit: int

    def __post_init__(self) -> None:
        self._identifier("sku_id", "location_id")
        self._not_negative("on_hand", "reserved", "in_transit")

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

    def __post_init__(self) -> None:
        self._identifier("order_id", "sku_id", "supplier_id")
        self._positive("quantity")
        self._not_negative("lead_time_days")
        self._one_of("status", INBOUND_STATUSES)


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

    def __post_init__(self) -> None:
        self._identifier("order_id", "sku_id")
        self._positive("quantity")
        self._one_of("channel", OUTBOUND_CHANNELS)
        self._one_of("priority", OUTBOUND_PRIORITIES)
        self._one_of("status", OUTBOUND_STATUSES)


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
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self._identifier("location_id")
        self._one_of("modality", SENSOR_MODALITIES)
        if isinstance(self.value, bool) or not isinstance(self.value, (int, float)) or not math.isfinite(self.value):
            self._fail("value", "must be a finite number")

"""The dataset catalogue: named tables built from a world, mounted as plug-ins.

A dataset provider is any class with a ``DatasetInfo`` ``info`` class attribute
and a ``rows(world)`` method that yields one tuple per row, in field order. The
providers this package declares in the ``sdf.datasets`` entry-point group of
its own ``pyproject.toml`` are the built-ins; any installed package can
declare more the same way:

    [project.entry-points."sdf.datasets"]
    channel-mix = "my_package.tables:ChannelMix"

Every business number in a built-in table (line value, stock value, the plan's
levels and order quantity) is computed here, so a client only groups, filters
and aggregates what it receives.
"""

from __future__ import annotations

import inspect
from collections.abc import Iterable
from itertools import islice
from typing import Any, ClassVar, Protocol

from sdf.foundation.plugins import (
    DISTRIBUTION as DISTRIBUTION,  # re-exported: the names this module always had
    Origin as Origin,
    PluginRegistry,
    Registration as Registration,
)
from sdf.foundation.tables import DatasetInfo, Field, Table
from sdf.simulation.policy import ServiceLevelPolicy, plan_orders
from sdf.simulation.world import World

ENTRY_POINT_GROUP = "sdf.datasets"
PLAN_SERVICE_LEVEL = 0.95  # the replenishment-plan dataset's policy, as on the dashboard


class DatasetProvider(Protocol):
    info: ClassVar[DatasetInfo]

    def rows(self, world: World) -> Iterable[tuple[Any, ...]]: ...


def _money(x: float) -> float:
    return round(x, 2)


class OrderLinesDataset:
    info: ClassVar[DatasetInfo] = DatasetInfo(
        name="order-lines",
        label="Outbound order lines",
        description="Every outbound order line with its SKU's category and ABC class; cancelled lines included.",
        fields=(
            Field("date", "Order date", "time"),
            Field("sku_id", "SKU", "dimension"),
            Field("category", "Category", "dimension"),
            Field("abc_class", "ABC class", "dimension"),
            Field("channel", "Channel", "dimension"),
            Field("priority", "Priority", "dimension"),
            Field("status", "Status", "dimension"),
            Field("quantity", "Quantity", "measure", unit="units"),
            Field("line_value", "Line value", "measure", unit="currency"),
        ),
    )

    def rows(self, world: World) -> Iterable[tuple[Any, ...]]:
        skus = {s.sku_id: s for s in world.stream("SKU")}
        for o in world.stream("OutboundOrder"):
            sku = skus.get(o.sku_id)
            yield (
                o.ts.date().isoformat(),
                o.sku_id,
                sku.category if sku else None,
                sku.abc_class if sku else None,
                o.channel,
                o.priority,
                o.status,
                o.quantity,
                _money(o.quantity * sku.unit_price) if sku else None,
            )


class InventoryDataset:
    info: ClassVar[DatasetInfo] = DatasetInfo(
        name="inventory",
        label="Inventory",
        description="Every inventory snapshot with its SKU and location attributes and its stock value at unit cost.",
        fields=(
            Field("sku_id", "SKU", "dimension"),
            Field("category", "Category", "dimension"),
            Field("abc_class", "ABC class", "dimension"),
            Field("location_id", "Location", "dimension"),
            Field("zone", "Zone", "dimension"),
            Field("on_hand", "On hand", "measure", unit="units"),
            Field("reserved", "Reserved", "measure", unit="units"),
            Field("available", "Available", "measure", unit="units"),
            Field("in_transit", "In transit", "measure", unit="units"),
            Field("stock_value", "Stock value", "measure", unit="currency"),
        ),
    )

    def rows(self, world: World) -> Iterable[tuple[Any, ...]]:
        skus = {s.sku_id: s for s in world.stream("SKU")}
        zones = {loc.location_id: loc.zone for loc in world.stream("Location")}
        for snap in world.stream("InventorySnapshot"):
            sku = skus.get(snap.sku_id)
            yield (
                snap.sku_id,
                sku.category if sku else None,
                sku.abc_class if sku else None,
                snap.location_id,
                zones.get(snap.location_id),
                snap.on_hand,
                snap.reserved,
                snap.available,
                snap.in_transit,
                _money(snap.on_hand * sku.unit_cost) if sku else None,
            )


class SkuDataset:
    info: ClassVar[DatasetInfo] = DatasetInfo(
        name="skus",
        label="SKUs",
        description="The SKU catalogue: category, ABC class, unit cost and price, shelf life.",
        fields=(
            Field("sku_id", "SKU", "dimension"),
            Field("name", "Name", "dimension"),
            Field("category", "Category", "dimension"),
            Field("abc_class", "ABC class", "dimension"),
            Field("unit_cost", "Unit cost", "measure", unit="currency", aggregate="mean"),
            Field("unit_price", "Unit price", "measure", unit="currency", aggregate="mean"),
            Field("shelf_life_days", "Shelf life", "measure", unit="days", aggregate="mean"),
        ),
    )

    def rows(self, world: World) -> Iterable[tuple[Any, ...]]:
        for s in world.stream("SKU"):
            yield (s.sku_id, s.name, s.category, s.abc_class, s.unit_cost, s.unit_price, s.shelf_life_days)


class ReplenishmentPlanDataset:
    info: ClassVar[DatasetInfo] = DatasetInfo(
        name="replenishment-plan",
        label="Replenishment plan (95 % service level)",
        description=(
            "The (s,S) plan for every SKU with demand under a 95 % service level: its demand profile, "
            "levels and order quantity."
        ),
        fields=(
            Field("sku_id", "SKU", "dimension"),
            Field("category", "Category", "dimension"),
            Field("abc_class", "ABC class", "dimension"),
            Field("demand_pattern", "Demand pattern", "dimension"),
            Field("needs_order", "Needs an order", "dimension"),
            Field("demand_mean", "Mean daily demand", "measure", unit="units per day", aggregate="mean"),
            Field("demand_std", "Daily demand std", "measure", unit="units per day", aggregate="mean"),
            Field("zero_day_share", "Share of days without demand", "measure", unit="share", aggregate="mean"),
            Field("safety_stock", "Safety stock", "measure", unit="units"),
            Field("reorder_point", "Reorder point", "measure", unit="units"),
            Field("order_up_to", "Order-up-to level", "measure", unit="units"),
            Field("available", "Available", "measure", unit="units"),
            Field("order_qty", "Order quantity", "measure", unit="units"),
        ),
    )

    def rows(self, world: World) -> Iterable[tuple[Any, ...]]:
        skus = {s.sku_id: s for s in world.stream("SKU")}
        for r in plan_orders(world, ServiceLevelPolicy(service_level=PLAN_SERVICE_LEVEL)):
            sku = skus.get(r.sku_id)
            yield (
                r.sku_id,
                sku.category if sku else None,
                sku.abc_class if sku else None,
                "intermittent" if r.profile.is_intermittent else "smooth",
                "yes" if r.order_qty > 0 else "no",
                round(r.profile.mean, 3),
                round(r.profile.std, 3),
                round(r.profile.zero_ratio, 4),
                round(r.safety_stock, 2),
                round(r.reorder_point, 2),
                round(r.order_up_to, 2),
                r.available,
                r.order_qty,
            )


class DatasetCatalog(PluginRegistry[DatasetProvider]):
    """Dataset providers by name; built-ins and plug-ins are mounted from the ``sdf.datasets`` group."""

    kind: ClassVar[str] = "dataset"
    info_type: ClassVar[type] = DatasetInfo
    group: ClassVar[str] = ENTRY_POINT_GROUP
    made_by: ClassVar[str] = "build(name)"

    def check(self, cls: type[DatasetProvider]) -> None:
        """A ``rows(world)`` method and constructor defaults."""
        if not callable(getattr(cls, "rows", None)) or not _takes_world(cls):
            raise TypeError(f"{cls.info.name}: a dataset provider needs a rows(world) method")
        super().check(cls)

    def info(self, name: str) -> DatasetInfo:
        return self._entry(name).cls.info

    def build(self, name: str, world: World) -> Table:
        """The table ``name`` over ``world``; every value is checked against its field."""
        cls = self._entry(name).cls
        return Table(cls.info, [tuple(row) for row in cls().rows(world)])

    def head(self, name: str, world: World, limit: int) -> tuple[Table, int]:
        """The first ``limit`` rows of ``name`` over ``world``, checked, and the dataset's total row count.

        Only the kept rows are stored and checked; the rest are counted as the
        provider yields them, so a response cap bounds memory for a provider
        that yields its rows instead of returning a list.
        """
        if limit < 1:
            raise ValueError(f"limit must be at least 1, got {limit}")
        cls = self._entry(name).cls
        rows = iter(cls().rows(world))
        kept = [tuple(row) for row in islice(rows, limit)]
        total = len(kept) + sum(1 for _ in rows)
        return Table(cls.info, kept), total


def _takes_world(cls: type) -> bool:
    """Whether ``cls().rows(world)`` binds: a plain method takes self and the world; a static or class method, the world."""
    args = (None, None) if inspect.isfunction(inspect.getattr_static(cls, "rows")) else (None,)
    try:
        signature = inspect.signature(cls.rows)
    except (TypeError, ValueError):
        return True  # no signature to read (a builtin): the build reports a mismatch
    try:
        signature.bind(*args)
    except TypeError:
        return False
    return True


def default_datasets() -> DatasetCatalog:
    """A fresh catalogue with every installed dataset provider, the built-ins included."""
    cat = DatasetCatalog()
    cat.load_entry_points()
    return cat

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

from collections.abc import Iterable
from dataclasses import dataclass
from importlib.metadata import EntryPoint, entry_points
from typing import Any, ClassVar, Protocol

from sdf.foundation.tables import DatasetInfo, Field, Table
from sdf.simulation.policy import ServiceLevelPolicy, plan_orders
from sdf.simulation.world import World
from sdf.synthesis.registry import DISTRIBUTION, Origin

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


@dataclass(frozen=True)
class Registration:
    cls: type[DatasetProvider]
    origin: Origin  # builtin: declared by this package; plugin: another package; runtime: register() call


class DatasetCatalog:
    """Dataset providers by name; built-ins and plug-ins are mounted from the ``sdf.datasets`` group."""

    def __init__(self) -> None:
        self._entries: dict[str, Registration] = {}
        self._unavailable: dict[str, str] = {}

    def register(self, cls: type[DatasetProvider], *, replace: bool = False, origin: Origin = "runtime") -> None:
        """Add ``cls`` under ``cls.info.name``; a duplicate name raises unless ``replace``."""
        info = getattr(cls, "info", None)
        if not isinstance(info, DatasetInfo):
            raise TypeError(f"{getattr(cls, '__name__', cls)!r} has no DatasetInfo `info` class attribute")
        if not callable(getattr(cls, "rows", None)):
            raise TypeError(f"{info.name}: a dataset provider needs a rows(world) method")
        if info.name in self._entries and not replace:
            raise ValueError(f"dataset {info.name!r} is already registered; pass replace=True to override")
        self._entries[info.name] = Registration(cls, origin)
        self._unavailable.pop(info.name, None)

    def load_entry_points(self, group: str = ENTRY_POINT_GROUP) -> list[str]:
        """Mount every provider declared in ``group``; return the names mounted.

        Built-ins mount first and keep their names; a plug-in that reuses one, or
        fails to load, is listed by ``unavailable()`` instead of raising.
        """
        mounted: list[str] = []
        declared = sorted(entry_points(group=group), key=lambda e: (_origin(e) != "builtin", _dist_name(e), e.name))
        reserved = {e.name for e in declared if _origin(e) == "builtin"}
        for ep in declared:
            origin = _origin(ep)
            if ep.name in self._entries or (origin != "builtin" and ep.name in reserved):
                self._unavailable[f"{ep.name} ({_dist_name(ep)})"] = f"name already taken; {ep.value} not mounted"
                continue
            try:
                problem = self._mount(ep, origin)
            except Exception as exc:  # a broken third-party plug-in must not break the catalogue or the API
                problem = f"failed to load {ep.value}: {exc}"
            if problem:
                self._unavailable[ep.name] = problem
            else:
                mounted.append(ep.name)
        return mounted

    def _mount(self, ep: EntryPoint, origin: Origin) -> str | None:
        cls = ep.load()
        info = getattr(cls, "info", None)
        if not isinstance(info, DatasetInfo):
            return f"{ep.value} has no DatasetInfo `info` class attribute"
        if info.name != ep.name:
            return f"entry point name differs from info.name {info.name!r}"
        try:
            self.register(cls, origin=origin)
        except (TypeError, ValueError) as exc:
            return str(exc)
        return None

    def names(self, *, origin: Origin | None = None) -> list[str]:
        return sorted(n for n, e in self._entries.items() if origin is None or e.origin == origin)

    def info(self, name: str) -> DatasetInfo:
        return self._entry(name).cls.info

    def origin(self, name: str) -> Origin:
        return self._entry(name).origin

    def unavailable(self) -> dict[str, str]:
        """Declared providers that could not be mounted, with the reason."""
        return dict(self._unavailable)

    def build(self, name: str, world: World) -> Table:
        """The table ``name`` over ``world``; every value is checked against its field."""
        cls = self._entry(name).cls
        return Table(cls.info, [tuple(row) for row in cls().rows(world)])

    def _entry(self, name: str) -> Registration:
        if name not in self._entries:
            hint = f" ({self._unavailable[name]})" if name in self._unavailable else ""
            raise KeyError(f"unknown dataset {name!r}{hint}; choose from {self.names()}")
        return self._entries[name]


def _dist_name(ep: EntryPoint) -> str:
    return ep.dist.name if ep.dist is not None else ""


def _origin(ep: EntryPoint) -> Origin:
    return "builtin" if _dist_name(ep) == DISTRIBUTION else "plugin"


def default_datasets() -> DatasetCatalog:
    """A fresh catalogue with every installed dataset provider, the built-ins included."""
    cat = DatasetCatalog()
    cat.load_entry_points()
    return cat

"""Tests for the dataset catalogue and its built-in datasets."""

from __future__ import annotations

from importlib.metadata import EntryPoint
from typing import ClassVar

import pytest

from sdf.application import datasets as datasets_module
from sdf.application.kpi import kpis
from sdf.foundation.tables import DatasetInfo, Field
from sdf.simulation.world import World
from sdf.synthesis.registry import DISTRIBUTION
from sdf.synthesis.spec import GenerationSpec
from .datasets import DatasetCatalog, default_datasets


@pytest.fixture(scope="module")
def world():
    return World.generate(GenerationSpec())


@pytest.fixture(scope="module")
def cat():
    return default_datasets()


class ChannelMix:
    """The contract's example provider (docs/refactor/explore/interfaces.md §1.2)."""

    info: ClassVar[DatasetInfo] = DatasetInfo(
        name="channel-mix",
        label="Channel mix",
        description="Order lines per channel",
        fields=(Field("channel", "Channel", "dimension"), Field("lines", "Lines", "measure", unit="lines")),
    )

    def rows(self, world):
        counts = {}
        for o in world.stream("OutboundOrder"):
            counts[o.channel] = counts.get(o.channel, 0) + 1
        return sorted(counts.items())


class BadValues:
    info: ClassVar[DatasetInfo] = DatasetInfo(
        name="bad-values",
        label="Bad",
        description="A date object in a time field",
        fields=(Field("day", "Day", "time"),),
    )

    def rows(self, world):
        return [(world.stream("OutboundOrder")[0].ts,)]


class Counter:
    """A large provider: 100 000 rows, yielded one at a time, the last one invalid."""

    info: ClassVar[DatasetInfo] = DatasetInfo(
        name="counter",
        label="Counter",
        description="Integers",
        fields=(Field("n", "N", "measure"),),
    )
    yielded = 0

    def rows(self, world):
        for n in range(100_000):
            Counter.yielded += 1
            yield (n,) if n < 99_999 else ("not a number",)


class NeedsArgument:
    info: ClassVar[DatasetInfo] = DatasetInfo(
        name="needs-argument", label="x", description="x", fields=(Field("n", "N", "measure"),)
    )

    def __init__(self, path):
        self.path = path

    def rows(self, world):
        return []


def test_the_built_ins_are_mounted_from_the_entry_point_group(cat):
    assert cat.names() == ["inventory", "order-lines", "replenishment-plan", "skus"]
    assert {cat.origin(n) for n in cat.names()} == {"builtin"} and cat.unavailable() == {}
    info = cat.info("order-lines")
    assert [f.name for f in info.fields] == [
        "date",
        "sku_id",
        "category",
        "abc_class",
        "channel",
        "priority",
        "status",
        "quantity",
        "line_value",
    ]
    assert info.fields[-1] == Field("line_value", "Line value", "measure", unit="currency", aggregate="sum")


def _column(table, name):
    i = [f.name for f in table.info.fields].index(name)
    return [row[i] for row in table.rows]


def test_the_tables_add_up_to_the_dashboard_figures(cat, world):
    k = kpis(world.registry)
    lines = cat.build("order-lines", world)
    assert len(lines.rows) == k.outbound_lines == 28897
    price = {s.sku_id: s.unit_price for s in world.stream("SKU")}
    first = lines.rows[0]
    assert first[0] == "2025-01-01" and first[-1] == round(first[-2] * price[first[1]], 2)

    inventory = cat.build("inventory", world)
    assert sum(_column(inventory, "on_hand")) == k.total_on_hand
    assert sum(_column(inventory, "stock_value")) == pytest.approx(k.inventory_value, abs=0.01 * len(inventory.rows))

    plan = cat.build("replenishment-plan", world)
    assert _column(plan, "needs_order").count("yes") == 62  # SKUs needing an order at 95 %, as on the dashboard
    assert set(_column(plan, "demand_pattern")) == {"smooth", "intermittent"}

    skus = cat.build("skus", world)
    assert len(skus.rows) == k.total_skus == 200
    assert {f.name: f.aggregate for f in skus.info.fields if f.kind == "measure"} == {
        "unit_cost": "mean",
        "unit_price": "mean",
        "shelf_life_days": "mean",
    }


def test_a_runtime_provider_is_registered_and_built(world):
    cat = default_datasets()
    cat.register(ChannelMix)
    assert cat.origin("channel-mix") == "runtime"
    rows = cat.build("channel-mix", world).rows
    assert [r[0] for r in rows] == ["ecommerce", "store", "wholesale"]
    assert sum(r[1] for r in rows) == 28897
    with pytest.raises(ValueError, match="already registered"):
        cat.register(ChannelMix)


def test_a_provider_with_a_bad_value_fails_at_build_with_a_clear_message(world):
    cat = DatasetCatalog()
    cat.register(BadValues)
    with pytest.raises(ValueError, match=r"dataset bad-values: row 0, field day: a time field holds an ISO date"):
        cat.build("bad-values", world)


def test_register_rejects_a_class_that_is_not_a_provider():
    cat = DatasetCatalog()
    with pytest.raises(TypeError, match="no DatasetInfo"):
        cat.register(object)
    with pytest.raises(KeyError, match=r"unknown dataset 'nope'; choose from \[\]"):
        cat.info("nope")


def test_head_keeps_and_checks_only_the_first_rows_and_counts_the_rest(world):
    cat = DatasetCatalog()
    cat.register(Counter)
    Counter.yielded = 0
    table, total = cat.head("counter", world, 3)
    assert table.rows == [(0,), (1,), (2,)] and total == 100_000 == Counter.yielded
    with pytest.raises(ValueError, match="field n: a measure holds a number"):
        cat.head("counter", world, 100_000)
    with pytest.raises(ValueError, match="limit must be at least 1"):
        cat.head("counter", world, 0)


def test_register_rejects_a_provider_whose_constructor_needs_arguments():
    with pytest.raises(TypeError, match=r"needs-argument: every constructor argument needs a default.*\['path'\]"):
        DatasetCatalog().register(NeedsArgument)


def _entry_point(name, value, dist=None):
    ep = EntryPoint(name=name, value=value, group=datasets_module.ENTRY_POINT_GROUP)
    if dist is None:
        return ep

    class FakeDist:
        def __init__(self, n):
            self.name = n

    return ep._for(FakeDist(dist)) if hasattr(ep, "_for") else ep


def test_plug_ins_mount_and_a_broken_or_clashing_one_is_listed_not_raised(monkeypatch):
    builtin = _entry_point("order-lines", "sdf.application.datasets:OrderLinesDataset", DISTRIBUTION)
    squatter = _entry_point("order-lines", f"{__name__}:ChannelMix", "vendor-pkg")
    if builtin.dist is None:
        pytest.skip("EntryPoint cannot carry a distribution on this Python")
    eps = [
        squatter,
        builtin,
        _entry_point("channel-mix", f"{__name__}:ChannelMix", "vendor-pkg"),
        _entry_point("missing", "no_such_package.tables:Nope", "vendor-pkg"),
        _entry_point("wrong-name", f"{__name__}:ChannelMix", "vendor-pkg"),
        _entry_point("needs-argument", f"{__name__}:NeedsArgument", "vendor-pkg"),
    ]
    monkeypatch.setattr(datasets_module, "entry_points", lambda group: eps)
    cat = default_datasets()
    assert cat.names() == ["channel-mix", "order-lines"]
    assert cat.origin("order-lines") == "builtin" and cat.origin("channel-mix") == "plugin"
    problems = cat.unavailable()
    assert "name already taken" in problems["order-lines (vendor-pkg)"]
    assert "failed to load" in problems["missing"]
    assert "differs from info.name" in problems["wrong-name"]
    assert "constructor argument needs a default" in problems["needs-argument"]

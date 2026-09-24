"""Tests for ``World``."""

from __future__ import annotations

import dataclasses
from typing import ClassVar

import pytest

from sdf.synthesis.api import SynthesizerInfo
from sdf.synthesis.registry import default_registry
from sdf.synthesis.spec import GenerationSpec
from sdf.synthesis.warehouse import WarehouseGenerator
from .intervention import SpecIntervention
from .world import World


def test_generate_records_spec_label_and_streams():
    w = World.generate(GenerationSpec(n_skus=20, horizon_days=10, seed=7))
    assert w.label == "GenerationSpec(seed=7)"
    assert w.spec == GenerationSpec(n_skus=20, horizon_days=10, seed=7)
    assert w.warehouse is not None and len(w.stream("SKU")) == 20


def test_default_world_matches_the_contract(world):
    assert len(world.stream("OutboundOrder")) == 28897


def test_world_is_immutable(small_world):
    with pytest.raises(dataclasses.FrozenInstanceError):
        small_world.label = "other"  # type: ignore[misc]


def test_demand_is_computed_once(small_world):
    assert small_world.demand() is small_world.demand()


def test_with_stream_replaces_one_stream_and_leaves_the_original(small_world):
    orders = small_world.stream("OutboundOrder")
    new = small_world.with_stream("OutboundOrder", orders[:5], label="first-five")
    assert (new.label, new.spec) == ("first-five", None)
    assert len(new.stream("OutboundOrder")) == 5
    assert len(small_world.stream("OutboundOrder")) == len(orders)
    for entity in ("SKU", "Location", "InventorySnapshot", "InboundOrder", "SensorReading"):
        assert len(new.stream(entity)) == len(small_world.stream(entity))


# -- the warehouse generator ------------------------------------------------------------------


class MyWarehouseGenerator:
    """The contract's warehouse plug-in (interfaces.md §4.1): it wraps the built-in generator and counts its uses."""

    info: ClassVar[SynthesizerInfo] = SynthesizerInfo(
        name="my-warehouse", produces="warehouse", needs_fit=False, description="Example warehouse generator"
    )
    built: ClassVar[list[str]] = []

    def __init__(self, *, spec: GenerationSpec | None = None) -> None:
        self.spec = spec or GenerationSpec()

    def fit(self, data=None):
        return self

    def sample(self, n=None, *, seed=None):
        MyWarehouseGenerator.built.append(f"seed={self.spec.seed}")
        return WarehouseGenerator(self.spec).generate()


def test_a_world_keeps_its_generator_through_a_scenario():
    spec = GenerationSpec(n_skus=60, horizon_days=45)
    synthesizers = default_registry()
    synthesizers.register(MyWarehouseGenerator)
    MyWarehouseGenerator.built.clear()
    world = World.generate(spec, synthesizer="my-warehouse", synthesizers=synthesizers)
    assert world.synthesizer == "my-warehouse" and world.synthesizers is synthesizers
    scenario = SpecIntervention.named("promo_spike").apply(world)
    assert scenario.synthesizer == "my-warehouse" and scenario.synthesizers is synthesizers
    assert len(MyWarehouseGenerator.built) == 2  # the scenario regenerated with it, not with warehouse-spec
    assert world.with_stream("SKU", world.stream("SKU"), label="same").synthesizer == "my-warehouse"


def test_the_default_generator_and_equal_worlds():
    spec = GenerationSpec(n_skus=40, horizon_days=30)
    world = World.generate(spec)
    assert world.synthesizer == "warehouse-spec" and world.synthesizers is not None
    again = World.generate(spec)
    entities = sorted(world.registry.summary()["by_entity"])
    assert entities and all(again.stream(e) == world.stream(e) for e in entities)  # the same spec, the same data
    assert (again.spec, again.label, again.synthesizer) == (world.spec, world.label, world.synthesizer)
    assert "synthesizers" not in repr(world)


def test_a_generator_that_is_not_a_warehouse_is_refused():
    with pytest.raises(ValueError, match="seasonal-profile produces a series, not a warehouse"):
        World.generate(GenerationSpec(n_skus=20, horizon_days=14), synthesizer="seasonal-profile")
    with pytest.raises(KeyError, match="unknown synthesizer 'nope'"):
        World.generate(GenerationSpec(n_skus=20, horizon_days=14), synthesizer="nope")

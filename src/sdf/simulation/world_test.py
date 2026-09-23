"""Tests for ``World``."""

from __future__ import annotations

import dataclasses

import pytest

from sdf.synthesis.spec import GenerationSpec
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

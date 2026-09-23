"""Tests for the interventions."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from sdf.synthesis.scenarios import SCENARIOS, apply_scenario
from .intervention import Baseline, SpecIntervention
from .world import World


@dataclass(frozen=True)
class DropExpressOrders:
    """The contract's data-level extension (interfaces.md §1.4)."""

    name: str = "no_express"

    def apply(self, world):
        orders = [o for o in world.stream("OutboundOrder") if o.priority != "express"]
        return world.with_stream("OutboundOrder", orders, label=self.name)


def test_baseline_returns_the_same_world(small_world):
    assert Baseline().apply(small_world) is small_world


def test_spec_intervention_regenerates_from_the_scenario_spec(small_world):
    promo = SpecIntervention.named("promo_spike")
    assert promo.tweaks == SCENARIOS["promo_spike"]
    changed = promo.apply(small_world)
    assert changed.label == "promo_spike"
    assert changed.spec == apply_scenario(small_world.spec, SCENARIOS["promo_spike"])
    assert len(changed.stream("OutboundOrder")) > len(small_world.stream("OutboundOrder"))


def test_unknown_scenario_is_a_key_error():
    with pytest.raises(KeyError, match="unknown scenario 'nope'"):
        SpecIntervention.named("nope")


def test_spec_intervention_needs_a_spec(small_world):
    edited = World(registry=small_world.registry, label="loaded")
    with pytest.raises(ValueError, match="no GenerationSpec"):
        SpecIntervention.named("promo_spike").apply(edited)


def test_data_level_intervention(small_world):
    changed = DropExpressOrders().apply(small_world)
    assert changed.label == "no_express" and changed.spec is None
    assert all(o.priority != "express" for o in changed.stream("OutboundOrder"))
    assert any(o.priority == "express" for o in small_world.stream("OutboundOrder"))

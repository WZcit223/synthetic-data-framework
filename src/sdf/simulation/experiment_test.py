"""Tests for ``Experiment`` and the outcomes it measures."""

from __future__ import annotations

import pytest

from .experiment import Experiment, OutcomeRow
from .intervention import Baseline, SpecIntervention
from .outcome import ActiveStockouts, CostModel, ReplenishmentNeed, SimulatedCost
from .policy import NaivePolicy, ServiceLevelPolicy

METRICS = {
    "skus_needing_order",
    "safety_stock_units",
    "intermittent_needing_order",
    "active_stockouts",
    "unmet_units",
    "fill_rate",
    "holding_cost",
    "order_cost",
    "lost_margin",
}


def test_contract_example_returns_tidy_rows(small_world):
    exp = Experiment(
        world=small_world,
        interventions=[Baseline(), SpecIntervention.named("promo_spike")],
        policies=[NaivePolicy(), ServiceLevelPolicy(service_level=0.95)],
        outcomes=[ReplenishmentNeed(), ActiveStockouts(), SimulatedCost(CostModel())],
    )
    rows = exp.run()
    assert all(isinstance(r, OutcomeRow) for r in rows)
    assert (rows[0].intervention, rows[0].policy, rows[0].metric) == ("baseline", "naive", "skus_needing_order")
    assert {r.metric for r in rows} == METRICS
    assert len(rows) == 2 * 2 * len(METRICS)
    assert {(r.intervention, r.policy) for r in rows} == {
        (i, p) for i in ("baseline", "promo_spike") for p in ("naive", "service-level-95")
    }


def test_safety_stock_serves_more_demand(world):
    rows = Experiment(
        world=world,
        interventions=[Baseline()],
        policies=[NaivePolicy(), ServiceLevelPolicy(z=1.645)],
        outcomes=[SimulatedCost(CostModel())],
    ).run()
    v = {(r.policy, r.metric): r.value for r in rows}
    assert round(v["naive", "unmet_units"]) == 5269 and round(v["service-level-z1.645", "unmet_units"]) == 0
    assert v["naive", "fill_rate"] < v["service-level-z1.645", "fill_rate"] == pytest.approx(1.0)


def test_outcomes_on_the_default_world(world):
    policy = ServiceLevelPolicy(service_level=0.95)
    assert ReplenishmentNeed().measure(world, policy) == {
        "skus_needing_order": 62,
        "safety_stock_units": 4541.0,
        "intermittent_needing_order": 40,
    }
    assert ActiveStockouts().measure(world, policy) == {"active_stockouts": 2}

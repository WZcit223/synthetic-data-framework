"""The world's signal frame and the anomaly benchmark (docs/refactor/algorithms/interfaces.md §6.2, §6.3)."""

from __future__ import annotations

import numpy as np
import pytest

from sdf.analytics.detectors import score_detectors
from sdf.analytics.detectors.builtin import SeasonalResidual
from .benchmark import AnomalyBenchmark
from .engine import simulate_inventory
from .policy import Levels, ServiceLevelPolicy, levels_for, policy_input
from .signals import signal_frame


def test_record_adds_the_daily_stock_and_receipts_and_changes_nothing_else():
    demand = [5.0, 0.0, 9.0, 4.0, 7.0, 3.0, 8.0]
    levels = Levels(reorder_point=6.0, order_up_to=12.0)
    plain = simulate_inventory(demand, levels, lead_time_days=2)
    recorded = simulate_inventory(demand, levels, lead_time_days=2, record=True)
    assert (plain.on_hand, plain.receipts) == ((), ())
    assert (recorded.unmet_units, recorded.holding_unit_days, recorded.orders) == (
        plain.unmet_units,
        plain.holding_unit_days,
        plain.orders,
    )
    # stock today = stock yesterday + receipts − what was served (min of what was there and the demand)
    stock = levels.order_up_to
    for t, d in enumerate(demand):
        stock = stock + recorded.receipts[t] - min(stock + recorded.receipts[t], d)
        assert recorded.on_hand[t] == stock
    assert sum(recorded.on_hand) == recorded.holding_unit_days


def test_the_frame_holds_the_world_s_demand_and_the_policy_s_replayed_stock(world):
    policy = ServiceLevelPolicy(lead_time_days=3)  # not the default: the frame replays the policy it is given
    frame = signal_frame(world, policy)
    table = world.demand()
    assert frame.days == table.days and frame.sku_ids == tuple(table.series)
    assert set(frame.signals) == {"demand", "on_hand", "receipts"}
    sku = frame.sku_ids[0]
    assert np.array_equal(frame.signals["demand"][0], np.array(table.series[sku]))
    skus = {s.sku_id: s for s in world.stream("SKU")}
    trace = simulate_inventory(
        table.series[sku],
        levels_for(policy, policy_input(sku, table.series[sku], skus, table.profile(sku))),
        lead_time_days=3,
        record=True,
    )
    assert tuple(frame.signals["on_hand"][0]) == trace.on_hand and tuple(frame.signals["receipts"][0]) == trace.receipts
    assert not np.array_equal(frame.signals["on_hand"], signal_frame(world).signals["on_hand"])


@pytest.fixture(scope="module")
def injected(world):
    clean = signal_frame(world)
    frame, places = AnomalyBenchmark().inject(clean)
    return clean, frame, places


def test_the_benchmark_injects_where_it_says_and_nothing_else(injected):
    clean, frame, places = injected
    n_skus, n_days = clean.shape
    assert len(places) == round(0.01 * n_skus * n_days)
    assert {k for *_, k in places} == {"spike", "drop", "shrinkage"}
    idx = {s: i for i, s in enumerate(clean.sku_ids)}
    day = {d: t for t, d in enumerate(clean.days)}
    changed = np.argwhere(frame.signals["demand"] != clean.signals["demand"])
    demand_places = {(clean.sku_ids[i], clean.days[t]) for i, t in changed}
    assert demand_places == {(s, d) for s, d, k in places if k in ("spike", "drop")}
    for s, d, k in places:
        i, t = idx[s], day[d]
        if k == "spike":
            assert frame.signals["demand"][i, t] > clean.signals["demand"][i, t]
        elif k == "drop":
            assert frame.signals["demand"][i, t] == 0 < clean.signals["demand"][i, t]
    # the stock balance breaks on the shrinkage days only, and stock never goes below 0
    d, o, r = (frame.signals[k] for k in ("demand", "on_hand", "receipts"))
    unexplained = np.diff(o, axis=1) - r[:, 1:] + d[:, 1:]
    missing = {(clean.sku_ids[i], clean.days[t + 1]) for i, t in np.argwhere(unexplained < -1e-6)}
    assert missing == {(s, d) for s, d, k in places if k == "shrinkage"}
    assert np.nanmin(o) >= 0
    assert AnomalyBenchmark().inject(clean)[1] == places  # the seed makes it reproducible


def test_the_benchmark_checks_its_parameters():
    with pytest.raises(ValueError, match="rate must be from 0.001 to 0.05"):
        AnomalyBenchmark(rate=0.5)
    with pytest.raises(ValueError, match="kinds must be distinct names"):
        AnomalyBenchmark(kinds=("spike", "sparkle"))


def test_seasonal_residual_cannot_see_shrinkage(injected):
    clean, _, _ = injected
    frame, places = AnomalyBenchmark(kinds=("shrinkage",)).inject(clean)
    assert {k for *_, k in places} == {"shrinkage"} and len(places) >= 100  # a SKU-day short of stock gets none
    det = SeasonalResidual()
    # shrinkage leaves demand as it was: the demand-only rule reports exactly what it reported before
    assert {(x.sku_id, x.day) for x in det.detect(frame)} == {(x.sku_id, x.day) for x in det.detect(clean)}


def test_on_the_default_benchmark_isolation_forest_recalls_shrinkage(injected):
    _, frame, places = injected
    table = score_detectors(["seasonal-residual", "isolation-forest"], frame, places)
    names = [f.name for f in table.info.fields]
    rows = {(r[0], r[1], r[2]): dict(zip(names, r)) for r in table.rows}
    assert rows["isolation-forest", "shrinkage", "threshold"]["recall"] >= 0.8
    assert rows["seasonal-residual", "spike", "threshold"]["recall"] > 0.3  # the rule is strong on demand

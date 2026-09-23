"""Tests for the shared demand aggregation."""

from __future__ import annotations

from datetime import date, datetime

import pytest

from sdf.foundation.schema import OutboundOrder
from .demand import DemandTable


def _order(day: int, sku: str, qty: int, status: str = "shipped") -> OutboundOrder:
    return OutboundOrder(
        order_id=f"o{day}{sku}",
        ts=datetime(2025, 1, day, 10),
        sku_id=sku,
        quantity=qty,
        channel="store",
        priority="standard",
        status=status,
    )


def test_dense_axis_and_first_appearance_order():
    t = DemandTable.from_orders(
        [_order(3, "B", 2), _order(1, "A", 5), _order(3, "A", 1), _order(2, "C", 4, "cancelled")]
    )
    assert t.days == (date(2025, 1, 1), date(2025, 1, 2), date(2025, 1, 3))
    assert list(t.series) == ["B", "A"]
    assert t.series["A"] == (5.0, 0.0, 1.0)
    assert t.total() == (5.0, 0.0, 3.0)
    assert t.active_days == 2
    assert t.mean("A") == 2.0
    assert t.std("A") == ((9 + 4 + 1) / 3) ** 0.5


def test_cancelled_orders_can_be_included():
    t = DemandTable.from_orders([_order(1, "A", 5), _order(2, "A", 4, "cancelled")], include_cancelled=True)
    assert t.series["A"] == (5.0, 4.0)


def test_empty():
    t = DemandTable.from_orders([])
    assert t.days == () and t.series == {} and t.total() == () and t.active_days == 0


def test_default_world_has_no_empty_days(default_world):
    """The golden numbers rely on the dense axis and the active-day count agreeing."""
    _, reg, _ = default_world
    t = DemandTable.from_orders(reg.stream("OutboundOrder"))
    assert len(t.days) == t.active_days == 90


def test_profile_distinguishes_smooth_and_intermittent_demand():
    from .demand import DemandProfile

    t = DemandTable.from_orders([_order(d, "S", 4) for d in range(1, 11)] + [_order(3, "I", 20), _order(8, "I", 10)])
    smooth, sparse = t.profile("S"), t.profile("I")
    assert (smooth.zero_ratio, smooth.is_intermittent, smooth.variability) == (0.0, False, 0.0)
    assert sparse.zero_ratio == 0.8 and sparse.is_intermittent
    assert sparse.mean == 3.0
    assert sparse.variability == pytest.approx(15.0)  # a typical selling day, larger than std 6.4
    assert DemandProfile(mean=0.0, std=0.0, zero_ratio=1.0).variability == 0.0

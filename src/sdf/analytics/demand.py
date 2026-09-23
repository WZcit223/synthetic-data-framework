"""The one place that turns ``OutboundOrder`` rows into per-SKU daily demand series.

Before this module existed the aggregation was written five times with slightly
different conventions. ``DemandTable`` is the shared result: a dense day axis
from the first to the last order day and one quantity series per SKU on that
axis. Callers that need a different divisor (the number of days that had any
order at all, as the rule-of-thumb replenishment does) read ``active_days``.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta

from sdf.foundation.schema import OutboundOrder


@dataclass(frozen=True)
class DemandTable:
    """Per-SKU daily demand on a dense day axis.

    ``days`` is sorted and dense from the first to the last order day;
    ``series`` maps ``sku_id`` to one quantity per day (``len == len(days)``),
    in first-appearance order of the SKUs in the order stream.
    """

    days: tuple[date, ...]
    series: dict[str, tuple[float, ...]]

    @classmethod
    def from_orders(cls, orders: Iterable[OutboundOrder], *, include_cancelled: bool = False) -> "DemandTable":
        by_sku_day: dict[str, dict[date, float]] = defaultdict(lambda: defaultdict(float))
        for o in orders:
            if not include_cancelled and o.status == "cancelled":
                continue
            by_sku_day[o.sku_id][o.ts.date()] += o.quantity
        if not by_sku_day:
            return cls(days=(), series={})
        d0 = min(min(d) for d in by_sku_day.values())
        d1 = max(max(d) for d in by_sku_day.values())
        days = tuple(d0 + timedelta(days=i) for i in range((d1 - d0).days + 1))
        series = {sku: tuple(float(by_day.get(d, 0.0)) for d in days) for sku, by_day in by_sku_day.items()}
        return cls(days=days, series=series)

    def total(self) -> tuple[float, ...]:
        """Sum over SKUs per day (the series the forecasters consume)."""
        return tuple(sum(col) for col in zip(*self.series.values())) if self.series else ()

    @property
    def active_days(self) -> int:
        """Number of days on which at least one SKU had demand."""
        return sum(1 for q in self.total() if q > 0)

    def mean(self, sku_id: str) -> float:
        """Mean daily demand over all days (zero days included)."""
        s = self.series[sku_id]
        return sum(s) / len(s) if s else 0.0

    def std(self, sku_id: str) -> float:
        """Population standard deviation of daily demand over all days."""
        s = self.series[sku_id]
        if not s:
            return 0.0
        mu = self.mean(sku_id)
        return (sum((x - mu) ** 2 for x in s) / len(s)) ** 0.5

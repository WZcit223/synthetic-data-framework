"""The one place that turns ``OutboundOrder`` rows into per-SKU daily demand series.

Before this module existed the aggregation was written five times with slightly
different conventions. ``DemandTable`` is the shared result: a dense day axis
from the first to the last order day and one quantity series per SKU on that
axis. Daily rates everywhere divide by the number of calendar days in the
table (``len(days)``); ``active_days`` (days with any order) is kept for
reporting only.

``DemandProfile`` describes the *shape* of one SKU's demand. An SKU with no
demand on more than half of the days is *intermittent*: its risk is not a
little extra demand every day but one large order on a rare selling day, so its
``variability`` is at least the average size of a selling day.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, timedelta

from sdf.foundation.schema import OutboundOrder

INTERMITTENT_ZERO_RATIO = 0.5


@dataclass(frozen=True)
class DemandProfile:
    """Mean, spread and zero-day share of one SKU's daily demand."""

    mean: float
    std: float
    zero_ratio: float

    @classmethod
    def of(cls, series: Sequence[float]) -> DemandProfile:
        """The profile of one daily series, with ``DemandTable.profile``'s arithmetic: mean over every
        day, population standard deviation, share of days without demand."""
        n = len(series)
        if not n:
            return cls(mean=0.0, std=0.0, zero_ratio=1.0)
        mu = sum(series) / n
        return cls(
            mean=mu,
            std=(sum((x - mu) ** 2 for x in series) / n) ** 0.5,
            zero_ratio=sum(1 for x in series if x <= 0) / n,
        )

    @property
    def is_intermittent(self) -> bool:
        return self.zero_ratio > INTERMITTENT_ZERO_RATIO

    @property
    def variability(self) -> float:
        """Standard deviation to size safety stock with.

        Smooth SKUs: the day-to-day ``std``. Intermittent SKUs: the larger of
        ``std`` and the average quantity on a day that sold,
        ``mean / (1 − zero_ratio)``, so one typical order is buffered.
        ALGORITHM-HOOK[C2]: replace with a Croston/TSB lead-time-demand model.
        """
        if not self.is_intermittent or self.zero_ratio >= 1.0:
            return self.std
        return max(self.std, self.mean / (1.0 - self.zero_ratio))


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

    def until(self, day: date) -> "DemandTable":
        """The days before ``day``, same SKUs: the history a forecaster may see at that origin."""
        keep = sum(1 for d in self.days if d < day)
        if keep == 0:
            raise ValueError(f"no day before {day.isoformat()}; the table starts on {self._first()}")
        return DemandTable(days=self.days[:keep], series={k: v[:keep] for k, v in self.series.items()})

    def window(self, start: date, days: int) -> "DemandTable":
        """``days`` days from ``start``, same SKUs, for scoring; ``ValueError`` when the table has fewer."""
        if days < 1:
            raise ValueError(f"days must be at least 1, got {days}")
        if start not in self.days:
            raise ValueError(f"{start.isoformat()} is not a day of the table ({self._first()} to {self._last()})")
        i = self.days.index(start)
        if i + days > len(self.days):
            raise ValueError(f"the table has {len(self.days) - i} days from {start.isoformat()}, not {days}")
        return DemandTable(days=self.days[i : i + days], series={k: v[i : i + days] for k, v in self.series.items()})

    def _first(self) -> str:
        return self.days[0].isoformat() if self.days else "nothing (no day)"

    def _last(self) -> str:
        return self.days[-1].isoformat() if self.days else "nothing"

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

    def daily_rates(self) -> dict[str, float]:
        """Mean daily demand per SKU over the calendar days of the table."""
        horizon = max(1, len(self.days))
        return {sku: sum(series) / horizon for sku, series in self.series.items()}

    def zero_ratio(self, sku_id: str) -> float:
        """Share of days on which the SKU had no demand."""
        s = self.series[sku_id]
        return sum(1 for x in s if x <= 0) / len(s) if s else 1.0

    def profile(self, sku_id: str) -> DemandProfile:
        return DemandProfile(mean=self.mean(sku_id), std=self.std(sku_id), zero_ratio=self.zero_ratio(sku_id))

    def std(self, sku_id: str) -> float:
        """Population standard deviation of daily demand over all days."""
        s = self.series[sku_id]
        if not s:
            return 0.0
        mu = self.mean(sku_id)
        return (sum((x - mu) ** 2 for x in s) / len(s)) ** 0.5

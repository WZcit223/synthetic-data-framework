"""Fit a demand synthesizer on real data (Phase 2.1).

The framework's default generator invents plausible numbers. This module instead
*learns* from a real series: it estimates the seasonal **profile** (mean per
position-in-cycle) and the pool of multiplicative **residuals**, then samples new
points that reproduce the real shape. Transparent, dependency-free.

`FittedSeasonalDemand` is granularity-agnostic (give it any series + period).
`FittedHourlyDemand` is the convenience wrapper that derives an hourly series
from raw orders. ALGORITHM-HOOK: swap either for SDV CTGAN/TVAE (or DoppelGANger
for sequences); the fidelity/TSTR harness scores whichever generator you use.
"""

from __future__ import annotations

import random
from typing import List, Optional

from sdf.synthesis.forecast import hourly_business_series


class FittedSeasonalDemand:
    """Learns a per-cycle profile + residual pool from any numeric series."""

    def __init__(self, seed: int = 7) -> None:
        self.seed = seed
        self.period = 1
        self.profile: List[float] = []
        self.resid: List[float] = []
        self.reference: List[float] = []

    def fit(self, series: List[float], period: int) -> "FittedSeasonalDemand":
        self.period = max(1, period)
        self.reference = list(series)
        prof = [0.0] * self.period
        cnt = [0] * self.period
        for i, v in enumerate(series):
            prof[i % self.period] += v
            cnt[i % self.period] += 1
        self.profile = [prof[h] / c if c else 0.0 for h, c in enumerate(cnt)]
        self.resid = [
            v / self.profile[i % self.period]
            for i, v in enumerate(series)
            if self.profile[i % self.period] > 0
        ] or [1.0]
        return self

    def generate(self, n_points: Optional[int] = None) -> List[float]:
        rng = random.Random(self.seed)
        if n_points is None:
            n_points = len(self.reference)
        return [self.profile[i % self.period] * rng.choice(self.resid)
                for i in range(n_points)]


class FittedHourlyDemand:
    """Convenience wrapper: derive an hourly series from orders, then fit."""

    def __init__(self, seed: int = 7) -> None:
        self._m = FittedSeasonalDemand(seed)
        self.ppd = 0
        self.real_series: List[float] = []

    def fit(self, orders, lo: int = 8, hi: int = 19) -> "FittedHourlyDemand":
        series, ppd = hourly_business_series(orders, lo, hi)
        self.ppd = ppd or 1
        self.real_series = series
        self._m.fit(series, self.ppd)
        return self

    @property
    def profile(self) -> List[float]:
        return self._m.profile

    def generate(self, n_days: Optional[int] = None) -> List[float]:
        n_points = None if n_days is None else n_days * self.ppd
        return self._m.generate(n_points)

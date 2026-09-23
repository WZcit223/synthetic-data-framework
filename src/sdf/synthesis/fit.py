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

from sdf.analytics.forecast import hourly_business_series


class FittedSeasonalDemand:
    """Learns a per-cycle profile + residual pool from any numeric series."""

    def __init__(self, seed: int = 7) -> None:
        self.seed = seed
        self._rng = random.Random(seed)  # one stream: repeated generate() calls differ
        self.period = 1
        self.profile: list[float] = []
        self.resid: list[float] = []
        self.reference: list[float] = []

    def fit(self, series: list[float], period: int) -> "FittedSeasonalDemand":
        self.period = max(1, period)
        self.reference = list(series)
        prof = [0.0] * self.period
        cnt = [0] * self.period
        for i, v in enumerate(series):
            prof[i % self.period] += v
            cnt[i % self.period] += 1
        self.profile = [prof[h] / c if c else 0.0 for h, c in enumerate(cnt)]
        self.resid = [
            v / self.profile[i % self.period] for i, v in enumerate(series) if self.profile[i % self.period] > 0
        ] or [1.0]
        return self

    def generate(self, n_points: int | None = None, *, seed: int | None = None) -> list[float]:
        """Sample a series; each call continues the instance's random stream unless ``seed`` pins it."""
        rng = random.Random(seed) if seed is not None else self._rng
        if n_points is None:
            n_points = len(self.reference)
        return [self.profile[i % self.period] * rng.choice(self.resid) for i in range(n_points)]


class FittedHourlyDemand:
    """Convenience wrapper: derive an hourly series from orders, then fit."""

    def __init__(self, seed: int = 7) -> None:
        self._m = FittedSeasonalDemand(seed)
        self.ppd = 0
        self.real_series: list[float] = []

    def fit(self, orders, *, lo: int = 8, hi: int = 19) -> "FittedHourlyDemand":
        series, ppd = hourly_business_series(orders, lo=lo, hi=hi)
        self.ppd = ppd or 1
        self.real_series = series
        self._m.fit(series, self.ppd)
        return self

    @property
    def profile(self) -> list[float]:
        return self._m.profile

    def generate(self, n_days: int | None = None, *, seed: int | None = None) -> list[float]:
        n_points = None if n_days is None else n_days * self.ppd
        return self._m.generate(n_points, seed=seed)

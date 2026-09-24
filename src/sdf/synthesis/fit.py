"""Fit a demand synthesizer on real data (Phase 2.1).

The framework's default generator invents plausible numbers. This module instead
*learns* from a real series: it estimates the seasonal **profile** (mean per
position-in-cycle) and the pool of multiplicative **residuals**, then samples new
points that reproduce the real shape. Transparent, dependency-free.

`FittedSeasonalDemand` is granularity-agnostic (give it any series + period).
`FittedHourlyDemand` is the convenience wrapper that derives an hourly series
from raw orders. ALGORITHM-HOOK[A2]: swap either for SDV CTGAN/TVAE (or DoppelGANger
for sequences); the fidelity/TSTR harness scores whichever generator you use.
"""

from __future__ import annotations

import random
from typing import ClassVar

from sdf.analytics.forecast import hourly_business_series
from .api import SeriesData, Synthesizer, SynthesizerInfo


class FittedSeasonalDemand:
    """Learns a per-cycle profile + residual pool from any numeric series (``seasonal-profile``)."""

    info: ClassVar[SynthesizerInfo] = SynthesizerInfo(
        name="seasonal-profile",
        produces="series",
        needs_fit=True,
        description="Per-cycle mean profile × resampled multiplicative residuals",
    )

    def __init__(self, *, seed: int = 7) -> None:
        self.seed = seed
        self._rng = random.Random(seed)  # one stream: repeated sample() calls differ
        self.period = 1
        self.profile: list[float] = []
        self.resid: list[float] = []
        self.reference: list[float] = []

    def fit(self, data: SeriesData) -> FittedSeasonalDemand:
        series = list(data.values)
        self.period = max(1, data.period)
        self.reference = series
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

    def sample(self, n: int | None = None, *, seed: int | None = None) -> list[float]:
        """Sample ``n`` points (default: the fitted length); each call continues the stream unless ``seed`` pins it."""
        rng = random.Random(seed) if seed is not None else self._rng
        if n is None:
            n = len(self.reference)
        return [self.profile[i % self.period] * rng.choice(self.resid) for i in range(n)]


class FittedHourlyDemand:
    """Convenience wrapper: derive an hourly series from orders, then fit a series synthesizer.

    ``model`` is any synthesizer that produces a series (default: ``seasonal-profile``).
    """

    def __init__(self, model: Synthesizer | None = None, *, seed: int = 7) -> None:
        if model is not None and model.info.produces != "series":
            raise ValueError(f"{model.info.name} produces {model.info.produces!r}, not a series")
        self.model = model if model is not None else FittedSeasonalDemand(seed=seed)
        self.ppd = 0
        self.real_series: list[float] = []

    def fit(self, orders, *, lo: int = 8, hi: int = 19) -> FittedHourlyDemand:
        series, ppd = hourly_business_series(orders, lo=lo, hi=hi)
        self.ppd = ppd or 1
        self.real_series = series
        self.model.fit(SeriesData(values=series, period=self.ppd))
        return self

    def generate(self, n_days: int | None = None, *, seed: int | None = None) -> list[float]:
        n_points = len(self.real_series) if n_days is None else n_days * self.ppd
        return self.model.sample(n_points, seed=seed)

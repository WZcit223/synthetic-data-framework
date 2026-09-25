"""Benchmarks with a known answer: a promotion with a known effect, and demand with a known distribution.

``PromotionBenchmark`` scores causal estimators; ``DemandBenchmark`` scores
forecasters (``docs/refactor/algorithms/interfaces.md`` §3). The promotion part:

The world's SKUs with demand are the units. A declared mechanism promotes
high-demand SKUs more often (the confounding) and lifts a promoted SKU's weekly
units by ``uplift``. Both potential outcomes are generated, so the true average
effect is exact; the table shows only what an analyst would observe. The
contract is ``docs/refactor/causal/interfaces.md`` §3.3.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from typing import ClassVar

import numpy as np
from scipy import stats

from sdf.analytics.causal import CausalQuestion
from sdf.analytics.demand import DemandTable
from sdf.foundation.params import Param, constructor_params
from sdf.foundation.tables import DatasetInfo, Field, Table
from .world import World

BENCHMARK_INFO = DatasetInfo(
    name="promotion-benchmark",
    label="Promotion benchmark",
    description="Each SKU with demand, whether it was promoted and its weekly units; the promotion favours high demand",
    fields=(
        Field("sku_id", "SKU", "dimension"),
        Field("abc_class", "ABC class", "dimension"),
        Field("log_demand", "Log mean daily demand", "measure", aggregate="mean"),
        Field("log_price", "Log (1 + unit price)", "measure", aggregate="mean"),
        Field("promoted", "Promoted", "measure", aggregate="mean"),
        Field("weekly_units", "Weekly units", "measure", unit="units", aggregate="mean"),
    ),
)

QUESTION = CausalQuestion("promoted", "weekly_units", ("log_demand", "abc_class", "log_price"))


@dataclass(frozen=True)
class BenchmarkDraw:
    table: Table  # dataset "promotion-benchmark": what an analyst would observe
    question: CausalQuestion  # promoted → weekly_units, adjusting for log_demand, abc_class, log_price
    true_effect: float  # the mean over SKUs of y(1) − y(0): exact, because both are generated


@dataclass(frozen=True)
class PromotionBenchmark:
    """The world's SKUs as units, with a declared promotion mechanism on top, so the true effect is known.

    DATA-HOOK[C8]: the mechanism is declared, not observed; real promotion or intervention
    history with its assignment rules replaces it.
    """

    uplift: float = 0.3  # promoted weekly units = (1 + uplift) × unpromoted
    confounding: float = 1.0  # how strongly high-demand SKUs are promoted; 0 is random
    noise: float = 0.25  # lognormal sigma of weekly units
    seed: int = 7

    # The bounds, declared once, in the shape synthesizers use.
    param_bounds: ClassVar[dict[str, tuple[float | None, float | None]]] = {
        "uplift": (-0.9, 3.0),
        "confounding": (0.0, 3.0),
        "noise": (0.0, 1.0),
        "seed": (0, None),  # numpy's generator takes a non-negative integer
    }

    @classmethod
    def params(cls) -> tuple[Param, ...]:
        """The four fields as Params: the reader the synthesizer registry uses, so every caller checks alike."""
        return constructor_params(cls)

    def __post_init__(self) -> None:
        for p in self.params():
            problem = p.check(getattr(self, p.name))
            if problem:
                raise ValueError(f"{p.name} {problem}")

    def draw(self, world: World) -> BenchmarkDraw:
        demand = world.demand()
        units = []
        for sku in world.stream("SKU"):
            if sku.sku_id not in demand.series:
                continue
            mean = demand.profile(sku.sku_id).mean
            if mean > 0:
                units.append((sku, mean))
        if len(units) < 4:
            raise ValueError(f"the benchmark needs at least 4 SKUs with demand; the world has {len(units)}")
        log_demand = np.array([math.log(m) for _, m in units])
        sd = float(log_demand.std())
        z = (log_demand - log_demand.mean()) / sd if sd > 0 else np.zeros(len(units))  # one shared demand: random
        rng = np.random.default_rng(self.seed)
        p = 1 / (1 + np.exp(0.5 - self.confounding * z))
        promoted = rng.random(len(units)) < p
        e = rng.lognormal(0.0, self.noise, len(units)) if self.noise > 0 else np.ones(len(units))
        y0 = 7 * np.array([m for _, m in units]) * e
        y1 = (1 + self.uplift) * y0
        rows = [
            (
                sku.sku_id,
                sku.abc_class,
                float(log_demand[i]),
                math.log1p(sku.unit_price),
                int(promoted[i]),
                float(y1[i] if promoted[i] else y0[i]),
            )
            for i, (sku, _) in enumerate(units)
        ]
        return BenchmarkDraw(Table(BENCHMARK_INFO, rows), QUESTION, float((y1 - y0).mean()))


# -- the demand benchmark: forecasts scored against the exact distribution ------------------------

WEEKDAY_PROFILE = (1.0, 1.05, 1.1, 1.1, 1.25, 0.8, 0.7)  # Monday to Sunday, shared by every SKU
DEMAND_START = date(2025, 1, 1)

DEMAND_BENCHMARK_INFO = DatasetInfo(
    name="demand-benchmark",
    label="Demand benchmark",
    description="Each SKU's daily demand drawn from a declared process, with the mean a forecaster can know",
    fields=(
        Field("sku_id", "SKU", "dimension"),
        Field("date", "Date", "time"),
        Field("units", "Units", "measure", unit="units", aggregate="sum"),
        Field("true_mean", "True mean", "measure", unit="units", aggregate="sum"),
    ),
)


@dataclass(frozen=True)
class TrueDemand:
    """The exact distribution of each SKU's demand on each day, as a forecaster can know it.

    Promotions are unannounced, so it is the mixture over "promotion or not": demand is
    0 with probability ``zero[i]``, otherwise negative binomial with mean ``c[i, t]``, or
    ``c[i, t] × (1 + uplift)`` on a promotion day (probability ``promo_rate``).
    """

    days: tuple[date, ...]
    sku_ids: tuple[str, ...]
    component: np.ndarray  # SKUs × days: the negative binomial mean on a day without promotion
    zero: np.ndarray  # per SKU: the probability of a structural zero
    promo_rate: float
    promo_uplift: float
    dispersion: float

    def _at(self, day: date) -> int:
        try:
            return self.days.index(day)
        except ValueError:
            raise ValueError(f"{day.isoformat()} is not a day of the benchmark") from None

    def mean(self, day: date) -> np.ndarray:
        c = self.component[:, self._at(day)]
        return (1 - self.zero) * c * (1 + self.promo_rate * self.promo_uplift)

    def cdf(self, day: date, x: np.ndarray) -> np.ndarray:
        """P(demand ≤ x) per SKU (rows) for each count in ``x`` (columns)."""
        c = self.component[:, self._at(day)][:, None]
        n = self.dispersion
        plain = stats.nbinom.cdf(x[None, :], n, n / (n + c))
        lifted = stats.nbinom.cdf(x[None, :], n, n / (n + c * (1 + self.promo_uplift)))
        mixed = (1 - self.promo_rate) * plain + self.promo_rate * lifted
        return self.zero[:, None] + (1 - self.zero[:, None]) * mixed

    def quantiles(self, day: date, levels: Sequence[float]) -> dict[float, np.ndarray]:
        """The smallest count whose probability of not being exceeded reaches each level, per SKU."""
        c = self.component[:, self._at(day)]
        n = self.dispersion
        top = stats.nbinom.ppf(max(levels), n, n / (n + c.max() * (1 + self.promo_uplift)))
        x = np.arange(int(top) + 1)
        cdf = self.cdf(day, x)
        return {lv: x[np.argmax(cdf >= lv - 1e-12, axis=1)].astype(float) for lv in levels}


@dataclass(frozen=True)
class DemandDraw:
    table: DemandTable  # the drawn daily demand, one series per SKU
    truth: TrueDemand

    def observed(self) -> Table:
        """The draw as a ``demand-benchmark`` table: every SKU and day, with the mean a forecaster can know."""
        rows = []
        for i, sku in enumerate(self.truth.sku_ids):
            series = self.table.series[sku]
            for j, d in enumerate(self.table.days):
                rows.append((sku, d.isoformat(), series[j], round(float(self.truth.mean(d)[i]), 4)))
        return Table(DEMAND_BENCHMARK_INFO, rows)


@dataclass(frozen=True)
class DemandBenchmark:
    """Daily demand from a declared process, so every forecast can be scored against the exact distribution.

    Per SKU: a level ``exp(N(1, 1))``, the shared weekday profile and a small trend
    ``exp(β t)``, ``β ~ N(0, 0.001)``. A share ``intermittent_share`` of the SKUs has a
    structural zero with probability ``U(0.4, 0.8)``. On each SKU-day a promotion
    happens with probability ``promo_rate`` and lifts the mean by ``promo_uplift``.
    Demand is negative binomial with ``dispersion``; the mean over zeros and non-zeros
    is the level × weekday × trend (× the uplift on a promotion day).
    DATA-HOOK[C1]: the process is declared; real demand history with its promotions replaces it.
    """

    n_skus: int = 200
    days: int = 365
    intermittent_share: float = 0.3
    promo_rate: float = 0.03
    promo_uplift: float = 0.6
    dispersion: float = 2.0
    seed: int | None = None  # empty: 7

    param_bounds: ClassVar[dict[str, tuple[float | None, float | None]]] = {
        "n_skus": (10, 400),
        "days": (84, 730),
        "intermittent_share": (0.0, 0.9),
        "promo_rate": (0.0, 0.2),
        "promo_uplift": (0.0, 3.0),
        "dispersion": (0.5, 50.0),
        "seed": (0, None),
    }

    @classmethod
    def params(cls) -> tuple[Param, ...]:
        return constructor_params(cls)

    def __post_init__(self) -> None:
        for p in self.params():
            problem = p.check(getattr(self, p.name))
            if problem:
                raise ValueError(f"{p.name} {problem}")

    def draw(self) -> DemandDraw:
        rng = np.random.default_rng(7 if self.seed is None else self.seed)
        n, t = self.n_skus, self.days
        days = tuple(DEMAND_START + timedelta(days=j) for j in range(t))
        weekday = np.array([WEEKDAY_PROFILE[d.weekday()] for d in days])
        level = np.exp(rng.normal(1.0, 1.0, n))
        trend = rng.normal(0.0, 0.001, n)
        mu = level[:, None] * weekday[None, :] * np.exp(trend[:, None] * np.arange(t)[None, :])
        zero = np.zeros(n)
        intermittent = rng.permutation(n)[: round(self.intermittent_share * n)]
        zero[intermittent] = rng.uniform(0.4, 0.8, len(intermittent))
        component = mu / (1 - zero[:, None])  # the negative binomial mean, so the mean over zeros is mu
        promo = rng.random((n, t)) < self.promo_rate
        c = component * np.where(promo, 1 + self.promo_uplift, 1.0)
        k = self.dispersion
        units = rng.negative_binomial(k, k / (k + c)) * (rng.random((n, t)) >= zero[:, None])
        sku_ids = tuple(f"B-{i:04d}" for i in range(n))
        table = DemandTable(days=days, series={s: tuple(float(v) for v in units[i]) for i, s in enumerate(sku_ids)})
        truth = TrueDemand(days, sku_ids, component, zero, self.promo_rate, self.promo_uplift, self.dispersion)
        return DemandDraw(table, truth)

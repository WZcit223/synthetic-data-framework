"""A promotion benchmark: observational rows with a known true effect, to score estimators on.

The world's SKUs with demand are the units. A declared mechanism promotes
high-demand SKUs more often (the confounding) and lifts a promoted SKU's weekly
units by ``uplift``. Both potential outcomes are generated, so the true average
effect is exact; the table shows only what an analyst would observe. The
contract is ``docs/refactor/causal/interfaces.md`` §3.3.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import ClassVar

import numpy as np

from sdf.analytics.causal import CausalQuestion
from sdf.foundation.tables import DatasetInfo, Field, Table
from sdf.synthesis.api import Param
from sdf.synthesis.registry import synthesizer_params
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
        return synthesizer_params(cls)

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

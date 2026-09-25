"""Demand forecasting with forecasters as plug-ins, scored by one probabilistic backtest.

A forecaster fits on a ``DemandTable`` and forecasts every SKU's next days with
a mean and quantiles; ``backtest`` scores several on the same rolling origins,
against seasonal naive and, on a benchmark, against the exact distribution.
The contract is ``docs/refactor/algorithms/interfaces.md`` §1 and §2.
"""

from .backtest import (
    BY_HORIZON_INFO,
    MAX_BACKTEST_SECONDS,
    MAX_FORECASTERS,
    MAX_HORIZON,
    MAX_ORIGINS,
    MIN_HISTORY,
    SCORES_INFO,
    TRUE_DISTRIBUTION,
    BacktestResult,
    backtest,
    forecasts_info,
    quantile_field,
)
from .core import MAX_QUANTILES, Forecast, Forecaster, ForecasterInfo, TrueDistribution, check_quantiles
from .registry import ENTRY_POINT_GROUP, ForecasterRegistry, default_forecasters

__all__ = [
    "BY_HORIZON_INFO",
    "ENTRY_POINT_GROUP",
    "MAX_BACKTEST_SECONDS",
    "MAX_FORECASTERS",
    "MAX_HORIZON",
    "MAX_ORIGINS",
    "MAX_QUANTILES",
    "MIN_HISTORY",
    "SCORES_INFO",
    "TRUE_DISTRIBUTION",
    "BacktestResult",
    "Forecast",
    "Forecaster",
    "ForecasterInfo",
    "ForecasterRegistry",
    "TrueDistribution",
    "backtest",
    "check_quantiles",
    "default_forecasters",
    "forecasts_info",
    "quantile_field",
]

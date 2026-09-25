"""The forecaster catalogue, and the guard every forecast passes through.

Forecasters are plug-ins in the ``sdf.forecasters`` entry-point group, mounted by
the shared loader (``sdf.foundation.plugins``). The backtest and every endpoint
call ``ForecasterRegistry.forecast``, never a forecaster directly, so a result
of the wrong shape, for other SKUs, with a non-finite value or under another
name is refused in one place. The contract is
``docs/refactor/algorithms/interfaces.md`` §1.2 and §1.3.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, ClassVar

import numpy as np

from sdf.analytics.demand import DemandTable
from sdf.foundation.params import Param, constructor_params
from sdf.foundation.plugins import PluginRegistry
from .core import Forecast, Forecaster, ForecasterInfo, check_quantiles

ENTRY_POINT_GROUP = "sdf.forecasters"


class ForecasterRegistry(PluginRegistry[Forecaster]):
    """Forecasters by name; built-ins and plug-ins are mounted from the ``sdf.forecasters`` group."""

    kind: ClassVar[str] = "forecaster"
    info_type: ClassVar[type] = ForecasterInfo
    group: ClassVar[str] = ENTRY_POINT_GROUP
    made_by: ClassVar[str] = "create(name)"

    def check(self, cls: type[Forecaster]) -> None:
        for method in ("fit", "forecast"):
            if not callable(getattr(cls, method, None)):
                raise TypeError(f"{cls.info.name}: a forecaster needs a {method}() method")
        super().check(cls)
        constructor_params(cls)  # a malformed param_bounds is refused when mounted, not at run time

    def info(self, name: str) -> ForecasterInfo:
        return self._entry(name).cls.info

    def params(self, name: str) -> tuple[Param, ...]:
        """The parameters a client may set on ``name``: its typed constructor keywords."""
        return constructor_params(self._entry(name).cls)

    def create(self, name: str, **params: Any) -> Forecaster:
        """A new instance of ``name`` with ``params``, each checked against its published bounds first."""
        declared = {p.name: p for p in self.params(name)}
        unknown = sorted(set(params) - set(declared))
        if unknown:
            raise ValueError(f"{name} takes no parameter {unknown}; it takes {sorted(declared)}")
        for key, value in params.items():
            problem = declared[key].check(value)
            if problem:
                raise ValueError(f"{name}: {key} {problem}")
        return self._entry(name).cls(**params)

    def forecast(
        self, model: Forecaster, history: DemandTable, *, horizon: int, quantiles: Sequence[float]
    ) -> Forecast:
        """``model.forecast`` through the guard: a checked, repaired ``Forecast`` or ``ValueError``."""
        levels = check_quantiles(quantiles)
        if isinstance(horizon, bool) or not isinstance(horizon, int) or horizon < 1:
            raise ValueError(f"horizon must be a whole number of days, at least 1, got {horizon!r}")
        name = type(model).info.name
        return _checked(name, model.forecast(history, horizon=horizon, quantiles=levels), history, horizon, levels)


def _checked(name: str, fc: Any, history: DemandTable, horizon: int, levels: tuple[float, ...]) -> Forecast:
    """Refuse a result the backtest cannot score; repair negatives and crossed quantiles, and say so."""
    if not isinstance(fc, Forecast):
        raise ValueError(f"{name} returned {type(fc).__name__}, not a Forecast")
    if fc.forecaster != name:
        raise ValueError(f"{name} returned a forecast labelled {fc.forecaster!r}")
    skus = tuple(history.series)
    if tuple(fc.sku_ids) != skus:
        raise ValueError(f"{name} forecast other SKUs than the history's ({len(fc.sku_ids)} for {len(skus)})")
    if set(fc.quantiles) != set(levels):
        raise ValueError(f"{name} returned the levels {sorted(fc.quantiles)}, not the requested {list(levels)}")
    shape = (len(skus), horizon)
    arrays = {"mean": np.asarray(fc.mean, dtype=float)} | {
        f"quantile {lv:g}": np.asarray(fc.quantiles[lv], dtype=float) for lv in levels
    }
    for label, arr in arrays.items():
        if arr.shape != shape:
            raise ValueError(f"{name} returned {label} of shape {arr.shape}, not {shape} (SKUs × horizon)")
        if not np.isfinite(arr).all():
            raise ValueError(f"{name} returned a non-finite {label}")
    mean = arrays["mean"]
    stack = np.stack([arrays[f"quantile {lv:g}"] for lv in levels])
    negative = int((mean < 0).sum() + (stack < 0).sum())
    ordered = np.sort(stack, axis=0)  # monotone rearrangement: each point's quantiles, non-decreasing in level
    crossed = int((ordered != stack).any(axis=0).sum())
    notes = [fc.method] if fc.method else []
    if negative:
        notes.append(f"{negative} negative value(s) set to 0")
    if crossed:
        notes.append(f"crossed quantiles sorted at {crossed} point(s)")
    return Forecast(
        forecaster=name,
        origin=fc.origin,
        sku_ids=skus,
        mean=np.maximum(mean, 0.0),
        quantiles={lv: np.maximum(ordered[j], 0.0) for j, lv in enumerate(levels)},
        method="; ".join(notes),
    )


def default_forecasters() -> ForecasterRegistry:
    """A registry with the ``sdf.forecasters`` group mounted, like ``default_registry()``."""
    reg = ForecasterRegistry()
    reg.load_entry_points()
    return reg

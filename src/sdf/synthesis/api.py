"""The synthesizer contract: one way to fit, sample and describe any synthesis algorithm.

A synthesizer is any class with an ``info`` class attribute (``SynthesizerInfo``)
and ``fit`` / ``sample`` methods. Every synthesizer, the built-ins included, is a
plug-in mounted by ``sdf.synthesis.registry`` from the ``sdf.synthesizers``
entry-point group, and callers choose one by name. See ``docs/refactor/structure/interfaces.md`` §2.
"""

from __future__ import annotations

import math
from bisect import bisect_left
from dataclasses import dataclass
from functools import partial
from typing import Any, ClassVar, Literal, Protocol, Self

from sdf.foundation.params import (  # re-exported: the names this module always had
    Param as Param,
    ParamType as ParamType,
)

Produces = Literal["warehouse", "series", "table"]


@dataclass(frozen=True)
class SynthesizerInfo:
    name: str  # registry key, lower-case, dash-separated
    produces: Produces
    needs_fit: bool  # False: configured entirely by constructor arguments
    description: str
    requires: tuple[str, ...] = ()  # importable modules it needs; missing ones make it unavailable


@dataclass(frozen=True)
class SeriesData:
    """A numeric series with its seasonal period (e.g. 7 for daily data with a weekly cycle)."""

    values: tuple[float, ...] | list[float]
    period: int


ColumnKind = Literal["real", "integer", "category"]
KINDS: tuple[str, ...] = ("real", "integer", "category")


@dataclass(frozen=True)
class TableData:
    """Numeric rows with named columns, and optionally each column's kind (``None``: every column ``real``).

    ``integer``: whole numbers within the observed range; ``category``: only the values
    observed. A table synthesizer honours them by passing its rows through
    ``apply_kinds``; one that ignores them still works, and the detection test shows it.
    """

    rows: list[tuple[float, ...]]
    columns: tuple[str, ...]
    kinds: tuple[ColumnKind, ...] | None = None

    def __post_init__(self) -> None:
        if self.kinds is None:
            return
        object.__setattr__(self, "kinds", tuple(self.kinds))  # a list is taken, and kept as a tuple
        if len(self.kinds) != len(self.columns):
            raise ValueError(f"{len(self.kinds)} kinds for {len(self.columns)} columns")
        unknown = [k for k in self.kinds if k not in KINDS]
        if unknown:
            raise ValueError(f"unknown column kinds {unknown}; each is one of {list(KINDS)}")


def apply_kinds(rows: list[tuple[float, ...]], data: TableData) -> list[tuple[float, ...]]:
    """``rows`` sampled from a fit on ``data``, made to respect its kinds: an ``integer`` column rounded to the
    nearest whole number and clipped to the whole numbers within the observed range, a ``category`` column moved
    to the nearest observed value (the lower one on a tie). A ``nan`` stays ``nan``, and is never observed.
    ``rows`` unchanged when ``data.kinds`` is ``None`` or ``data`` has no row; ``ValueError`` for a row that has
    not one value per column."""
    if data.kinds is None or not data.rows or all(k == "real" for k in data.kinds):
        return rows
    width = len(data.columns)
    wrong = next((r for r in rows if len(r) != width), None)
    if wrong is not None:
        raise ValueError(f"a sampled row has {len(wrong)} values for the {width} columns {list(data.columns)}")
    observed = [[v for v in col if not math.isnan(v)] for col in zip(*data.rows)]
    fixes = []
    for kind, values in zip(data.kinds, observed):
        if kind == "real" or not values:
            fixes.append(None)
        elif kind == "integer":
            lo = math.ceil(min(values))
            hi = max(lo, math.floor(max(values)))  # no whole number within the observed range: the next one up
            fixes.append(partial(_whole, lo, hi))
        else:
            fixes.append(partial(_nearest, sorted(set(values))))
    return [tuple(v if fix is None or math.isnan(v) else fix(v) for v, fix in zip(row, fixes)) for row in rows]


def _whole(lo: int, hi: int, v: float) -> float:
    return float(min(max(round(v), lo), hi))


def _nearest(levels: list[float], v: float) -> float:
    i = bisect_left(levels, v)
    if i == 0:
        return float(levels[0])
    if i == len(levels):
        return float(levels[-1])
    below, above = levels[i - 1], levels[i]
    return float(below if v - below <= above - v else above)


class Synthesizer(Protocol):
    info: ClassVar[SynthesizerInfo]

    def fit(self, data: Any) -> Self: ...  # SeriesData | TableData | None

    def sample(self, n: int | None = None, *, seed: int | None = None) -> Any: ...

"""The synthesizer contract: one way to fit, sample and describe any synthesis algorithm.

A synthesizer is any class with an ``info`` class attribute (``SynthesizerInfo``)
and ``fit`` / ``sample`` methods. Every synthesizer, the built-ins included, is a
plug-in mounted by ``sdf.synthesis.registry`` from the ``sdf.synthesizers``
entry-point group, and callers choose one by name. See ``docs/refactor/structure/interfaces.md`` §2.
"""

from __future__ import annotations

from dataclasses import dataclass
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


@dataclass(frozen=True)
class TableData:
    """Numeric rows with named columns."""

    rows: list[tuple[float, ...]]
    columns: tuple[str, ...]


class Synthesizer(Protocol):
    info: ClassVar[SynthesizerInfo]

    def fit(self, data: Any) -> Self: ...  # SeriesData | TableData | None

    def sample(self, n: int | None = None, *, seed: int | None = None) -> Any: ...

"""The synthesizer contract: one way to fit, sample and describe any synthesis algorithm.

A synthesizer is any class with an ``info`` class attribute (``SynthesizerInfo``)
and ``fit`` / ``sample`` methods. ``sdf.synthesis.registry`` lists the built-ins
and lets callers choose one by name. See ``docs/refactor/structure/interfaces.md`` §2.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar, Literal, Protocol, Self

Produces = Literal["warehouse", "series", "table"]


@dataclass(frozen=True)
class SynthesizerInfo:
    name: str  # registry key, lower-case, dash-separated
    produces: Produces
    needs_fit: bool  # False: configured entirely by constructor arguments
    description: str


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

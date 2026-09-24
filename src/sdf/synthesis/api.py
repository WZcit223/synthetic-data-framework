"""The synthesizer contract: one way to fit, sample and describe any synthesis algorithm.

A synthesizer is any class with an ``info`` class attribute (``SynthesizerInfo``)
and ``fit`` / ``sample`` methods. Every synthesizer, the built-ins included, is a
plug-in mounted by ``sdf.synthesis.registry`` from the ``sdf.synthesizers``
entry-point group, and callers choose one by name. See ``docs/refactor/structure/interfaces.md`` §2.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, ClassVar, Literal, Protocol, Self

Produces = Literal["warehouse", "series", "table"]
ParamType = Literal["int", "float", "str", "bool"]


@dataclass(frozen=True)
class SynthesizerInfo:
    name: str  # registry key, lower-case, dash-separated
    produces: Produces
    needs_fit: bool  # False: configured entirely by constructor arguments
    description: str
    requires: tuple[str, ...] = ()  # importable modules it needs; missing ones make it unavailable


@dataclass(frozen=True)
class Param:
    """One constructor parameter a client may set, in the shape every catalogue publishes.

    ``min`` and ``max`` are ``None`` when unbounded; ``exclusive`` means the bounds
    themselves are not allowed; ``nullable`` means ``None`` is also accepted.
    """

    name: str
    type: ParamType
    default: Any
    min: float | None = None
    max: float | None = None
    exclusive: bool = False
    nullable: bool = False

    def check(self, value: Any) -> str | None:
        """Why ``value`` cannot be passed for this parameter, or ``None`` when it can."""
        if value is None:
            return None if self.nullable else "must not be null"
        if self.type == "bool":
            return None if isinstance(value, bool) else f"must be true or false, got {value!r}"
        if self.type == "str":
            return None if isinstance(value, str) else f"must be text, got {value!r}"
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return f"must be a number, got {value!r}"
        if self.type == "int" and not isinstance(value, int):
            return f"must be a whole number, got {value!r}"
        if not math.isfinite(value):
            return f"must be finite, got {value!r}"
        below = self.min is not None and (value <= self.min if self.exclusive else value < self.min)
        above = self.max is not None and (value >= self.max if self.exclusive else value > self.max)
        if below or above:
            word = "between" if self.exclusive else "from"
            join = "and" if self.exclusive else "to"
            lo = "-inf" if self.min is None else self.min
            hi = "inf" if self.max is None else self.max
            return f"must be {word} {lo} {join} {hi}{', both excluded' if self.exclusive else ''}, got {value!r}"
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "type": self.type,
            "default": self.default,
            "min": self.min,
            "max": self.max,
            "exclusive": self.exclusive,
            "nullable": self.nullable,
        }


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

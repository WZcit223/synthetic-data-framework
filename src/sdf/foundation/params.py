"""Constructor parameters a client may set, in the one shape every catalogue publishes.

A plug-in (a synthesizer, a forecaster) is configured by keyword arguments of its
constructor. ``constructor_params`` reads the ones typed ``int``, ``float``,
``str`` or ``bool`` (or one of those or ``None``), with their defaults and the
bounds of an optional ``param_bounds`` class attribute, and publishes each as a
``Param``. It lives in the foundation so any layer's catalogue can use it; the
contract is ``docs/refactor/explore/interfaces.md`` §2.1.
"""

from __future__ import annotations

import inspect
import math
import sys
import types
from dataclasses import dataclass
from typing import Any, Literal, Union, get_args, get_origin, get_type_hints

ParamType = Literal["int", "float", "str", "bool"]

_PARAM_TYPES: dict[Any, ParamType] = {int: "int", float: "float", str: "str", bool: "bool"}


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
        if isinstance(value, float) and not math.isfinite(value):  # an int is exact at any size
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


def constructor_params(cls: type) -> tuple[Param, ...]:
    """The constructor's keyword arguments typed ``int``, ``float``, ``str`` or ``bool`` (or one of
    those or ``None``), with their defaults and the bounds of an optional ``param_bounds`` class
    attribute. Other arguments (a ``GenerationSpec``, a model) are supplied by the framework.
    """
    name = getattr(getattr(cls, "info", None), "name", getattr(cls, "__name__", repr(cls)))
    hints = _constructor_hints(cls)
    bounds = getattr(cls, "param_bounds", None)
    bounds = {} if bounds is None else bounds  # only a missing attribute or None means "no bounds"
    if not isinstance(bounds, dict):
        raise TypeError(f"{name}: param_bounds must be a dict of name -> (min, max)")
    for key, pair in bounds.items():
        if (
            not isinstance(pair, tuple)
            or len(pair) != 2
            or not all(b is None or (isinstance(b, (int, float)) and not isinstance(b, bool)) for b in pair)
        ):
            raise TypeError(f"{name}: param_bounds[{key!r}] must be a (min, max) pair of numbers or None")
        lo, hi = pair
        if any(isinstance(b, float) and not math.isfinite(b) for b in pair):
            raise TypeError(f"{name}: param_bounds[{key!r}] must be finite numbers or None, got {pair}")
        if lo is not None and hi is not None and lo > hi:
            raise TypeError(f"{name}: param_bounds[{key!r}] has min {lo} above max {hi}")
    params = []
    for p in inspect.signature(cls).parameters.values():
        if p.kind in (p.VAR_POSITIONAL, p.VAR_KEYWORD, p.POSITIONAL_ONLY):
            continue  # a parameter is passed by keyword: create(name, **params)
        kind, nullable = _param_type(hints.get(p.name))
        if kind is None:
            continue
        lo, hi = bounds.get(p.name, (None, None))
        # a default of None admits None, however the annotation is written (``seed: int = None``)
        param = Param(p.name, kind, p.default, min=lo, max=hi, nullable=nullable or p.default is None)
        problem = param.check(p.default)
        if problem:
            raise TypeError(f"{name}: the default of {p.name} breaks its own declaration: {problem}")
        params.append(param)
    numeric = {p.name for p in params if p.type in ("int", "float")}
    for key in bounds:
        if key not in numeric:
            raise TypeError(f"{name}: param_bounds names {key!r}, which is not a numeric constructor parameter")
    return tuple(params)


def _constructor_hints(cls: type) -> dict[str, Any]:
    """The constructor's resolved annotations. One that cannot be resolved (a type imported only
    for type checkers) is left out, so its argument is not a parameter and the plug-in still mounts."""
    try:
        return get_type_hints(cls.__init__)
    except Exception:
        pass
    init = cls.__init__
    namespace = getattr(sys.modules.get(init.__module__), "__dict__", {})
    hints = {}
    for arg, annotation in inspect.get_annotations(init).items():
        if not isinstance(annotation, str):
            hints[arg] = annotation
            continue
        try:
            hints[arg] = eval(annotation, dict(namespace))  # noqa: S307 - the plug-in's own annotation text
        except Exception:
            continue
    return hints


def _param_type(annotation: Any) -> tuple[ParamType | None, bool]:
    """The parameter type of an annotation and whether it also admits ``None``; ``(None, False)`` if not a parameter."""
    if annotation in _PARAM_TYPES:
        return _PARAM_TYPES[annotation], False
    if get_origin(annotation) in (Union, types.UnionType):
        rest = [a for a in get_args(annotation) if a is not type(None)]
        if len(rest) == 1 and len(get_args(annotation)) == 2 and rest[0] in _PARAM_TYPES:
            return _PARAM_TYPES[rest[0]], True
    return None, False

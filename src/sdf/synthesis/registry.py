"""Mount synthesizers as plug-ins and choose one by name.

Every synthesis algorithm, ours included, is a plug-in: a class that satisfies
``sdf.synthesis.api.Synthesizer``, declared in the ``sdf.synthesizers``
entry-point group. The ones this package declares in its own ``pyproject.toml``
are the built-ins; any other installed package can declare more the same way:

    [project.entry-points."sdf.synthesizers"]
    my-synth = "my_package.synth:MySynth"

``default_registry()`` mounts the whole group. ``register`` adds a class at
runtime (for example from a notebook) without packaging it.
"""

from __future__ import annotations

import inspect
import math
import sys
import types
from typing import Any, ClassVar, Union, get_args, get_origin, get_type_hints

from sdf.foundation.plugins import (
    DISTRIBUTION as DISTRIBUTION,  # re-exported: the names this module always had
    Origin as Origin,
    PluginRegistry,
    Registration as Registration,
)
from .api import Param, ParamType, Produces, Synthesizer, SynthesizerInfo

ENTRY_POINT_GROUP = "sdf.synthesizers"

_PARAM_TYPES: dict[Any, ParamType] = {int: "int", float: "float", str: "str", bool: "bool"}


class SynthesizerRegistry(PluginRegistry[Synthesizer]):
    """Synthesizers by name; built-ins and plug-ins are mounted from the ``sdf.synthesizers`` group."""

    kind: ClassVar[str] = "synthesizer"
    info_type: ClassVar[type] = SynthesizerInfo
    group: ClassVar[str] = ENTRY_POINT_GROUP
    made_by: ClassVar[str] = "create(name)"

    def check(self, cls: type[Synthesizer]) -> None:
        """What produces, the methods, the constructor defaults and the parameters' declarations."""
        info = cls.info
        if info.produces not in get_args(Produces):
            raise ValueError(f"{info.name}: produces must be one of {list(get_args(Produces))}, got {info.produces!r}")
        for method in ("fit", "sample"):
            if not callable(getattr(cls, method, None)):
                raise TypeError(f"{info.name}: a synthesizer needs a {method}() method")
        super().check(cls)
        synthesizer_params(cls)  # a malformed param_bounds or unreadable annotation is refused here, not at run time

    def create(self, name: str, **config: Any) -> Synthesizer:
        """A new instance of the synthesizer registered as ``name``, configured by ``config``."""
        return self._entry(name).cls(**config)

    def params(self, name: str) -> tuple[Param, ...]:
        """The parameters a client may set on ``name``: see ``synthesizer_params``."""
        return synthesizer_params(self._entry(name).cls)

    def info(self, name: str) -> SynthesizerInfo:
        return self._entry(name).cls.info


def synthesizer_params(cls: type) -> tuple[Param, ...]:
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


def default_registry() -> SynthesizerRegistry:
    """A fresh registry with every installed synthesizer plug-in, the built-ins included.

    ``gaussian-copula`` is declared like the other built-ins but is only
    available when the optional ``synthesis`` extra is installed.
    """
    reg = SynthesizerRegistry()
    reg.load_entry_points()
    return reg

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
import re
import sys
import types
from dataclasses import dataclass
from importlib.metadata import EntryPoint, entry_points
from importlib.util import find_spec
from typing import Any, Literal, Union, get_args, get_origin, get_type_hints

from .api import Param, ParamType, Produces, Synthesizer, SynthesizerInfo

ENTRY_POINT_GROUP = "sdf.synthesizers"
DISTRIBUTION = "synthetic-data-framework"  # entry points declared by this package are the built-ins
_NAME = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")

Origin = Literal["builtin", "plugin", "runtime"]
_PARAM_TYPES: dict[Any, ParamType] = {int: "int", float: "float", str: "str", bool: "bool"}


@dataclass(frozen=True)
class Registration:
    cls: type[Synthesizer]
    origin: Origin  # builtin: declared by this package; plugin: another package; runtime: register() call


class SynthesizerRegistry:
    def __init__(self) -> None:
        self._entries: dict[str, Registration] = {}
        self._unavailable: dict[str, str] = {}

    def register(self, cls: type[Synthesizer], *, replace: bool = False, origin: Origin = "runtime") -> None:
        """Add ``cls`` under ``cls.info.name``; a duplicate name raises unless ``replace``.

        Raises ``TypeError``/``ValueError`` for malformed metadata or when a module in
        ``info.requires`` cannot be imported, so nothing unusable is ever listed as mounted.
        """
        info = getattr(cls, "info", None)
        if not isinstance(info, SynthesizerInfo):
            raise TypeError(f"{getattr(cls, '__name__', cls)!r} has no SynthesizerInfo `info` class attribute")
        if not _NAME.fullmatch(info.name):
            raise ValueError(f"synthesizer name {info.name!r} must be lower-case words joined by dashes")
        if info.produces not in get_args(Produces):
            raise ValueError(f"{info.name}: produces must be one of {list(get_args(Produces))}, got {info.produces!r}")
        for method in ("fit", "sample"):
            if not callable(getattr(cls, method, None)):
                raise TypeError(f"{info.name}: a synthesizer needs a {method}() method")
        required = [
            p.name
            for p in inspect.signature(cls).parameters.values()
            if p.default is p.empty and p.kind not in (p.VAR_POSITIONAL, p.VAR_KEYWORD)
        ]
        if required:
            raise TypeError(
                f"{info.name}: every constructor argument needs a default so create(name) works; missing {required}"
            )
        synthesizer_params(cls)  # a malformed param_bounds or unreadable annotation is refused here, not at run time
        if not isinstance(info.requires, tuple) or not all(isinstance(m, str) for m in info.requires):
            raise TypeError("info.requires must be a tuple of module names")
        missing = [m for m in info.requires if not _importable(m)]
        if missing:
            raise ValueError(f"needs {', '.join(missing)}")
        if info.name in self._entries and not replace:
            raise ValueError(f"synthesizer {info.name!r} is already registered; pass replace=True to override")
        self._entries[info.name] = Registration(cls, origin)
        self._unavailable.pop(info.name, None)

    def load_entry_points(self, group: str = ENTRY_POINT_GROUP) -> list[str]:
        """Mount every synthesizer declared in ``group``; return the names mounted.

        A plug-in whose ``info.requires`` modules are not installed, or that fails
        to load, is skipped and listed by ``unavailable()`` instead of breaking
        the registry.
        """
        mounted: list[str] = []
        # Built-ins first, then plug-ins by distribution name: a plug-in reusing a
        # built-in's name never replaces it, and equal-name plug-ins resolve the same way on every run.
        # Built-in names stay reserved even when the built-in itself is unavailable (e.g. a missing extra).
        declared = sorted(entry_points(group=group), key=lambda e: (_origin(e) != "builtin", _dist_name(e), e.name))
        reserved = {e.name for e in declared if _origin(e) == "builtin"}
        for ep in declared:
            origin = _origin(ep)
            entry = self._entries.get(ep.name)
            if entry is not None and f"{entry.cls.__module__}:{entry.cls.__qualname__}" == f"{ep.module}:{ep.attr}":
                continue  # mounted by an earlier call (ep.value may also carry extras)
            if ep.name in self._entries or (origin != "builtin" and ep.name in reserved):
                holder = (
                    f"a {self._entries[ep.name].origin} synthesizer ({self._entries[ep.name].cls.__module__})"
                    if ep.name in self._entries
                    else "an unavailable built-in"
                )
                self._unavailable[f"{ep.name} ({_dist_name(ep)})"] = (
                    f"name already provided by {holder}; {ep.value} not mounted"
                )
                continue
            try:
                problem = self._mount(ep, origin)
            except Exception as exc:  # a broken third-party plug-in must not break the registry or the CLI
                problem = f"failed to load {ep.value}: {exc}"
            if problem:
                self._unavailable[ep.name] = problem
            else:
                mounted.append(ep.name)
        return mounted

    def _mount(self, ep: EntryPoint, origin: Origin) -> str | None:
        """Register one entry point; return why it cannot be mounted, or None."""
        cls = ep.load()
        info = getattr(cls, "info", None)
        if not isinstance(info, SynthesizerInfo):
            return f"{ep.value} has no SynthesizerInfo `info` class attribute"
        if info.name != ep.name:
            return f"entry point name differs from info.name {info.name!r}"
        try:
            self.register(cls, origin=origin)
        except (TypeError, ValueError) as exc:
            return str(exc)
        return None

    def create(self, name: str, **config: Any) -> Synthesizer:
        """A new instance of the synthesizer registered as ``name``, configured by ``config``."""
        return self._entry(name).cls(**config)

    def params(self, name: str) -> tuple[Param, ...]:
        """The parameters a client may set on ``name``: see ``synthesizer_params``."""
        return synthesizer_params(self._entry(name).cls)

    def names(self, *, origin: Origin | None = None) -> list[str]:
        return sorted(n for n, e in self._entries.items() if origin is None or e.origin == origin)

    def info(self, name: str) -> SynthesizerInfo:
        return self._entry(name).cls.info

    def origin(self, name: str) -> Origin:
        return self._entry(name).origin

    def unavailable(self) -> dict[str, str]:
        """Declared synthesizers that could not be mounted, with the reason."""
        return dict(self._unavailable)

    def _entry(self, name: str) -> Registration:
        if name not in self._entries:
            hint = f" ({self._unavailable[name]})" if name in self._unavailable else ""
            raise KeyError(f"unknown synthesizer {name!r}{hint}; choose from {self.names()}")
        return self._entries[name]


def synthesizer_params(cls: type) -> tuple[Param, ...]:
    """The constructor's keyword arguments typed ``int``, ``float``, ``str`` or ``bool`` (or one of
    those or ``None``), with their defaults and the bounds of an optional ``param_bounds`` class
    attribute. Other arguments (a ``GenerationSpec``, a model) are supplied by the framework.
    """
    name = getattr(getattr(cls, "info", None), "name", getattr(cls, "__name__", repr(cls)))
    hints = _constructor_hints(cls)
    bounds = getattr(cls, "param_bounds", None) or {}
    if not isinstance(bounds, dict):
        raise TypeError(f"{name}: param_bounds must be a dict of name -> (min, max)")
    for key, pair in bounds.items():
        if (
            not isinstance(pair, tuple)
            or len(pair) != 2
            or not all(b is None or (isinstance(b, (int, float)) and not isinstance(b, bool)) for b in pair)
        ):
            raise TypeError(f"{name}: param_bounds[{key!r}] must be a (min, max) pair of numbers or None")
    params = []
    for p in inspect.signature(cls).parameters.values():
        if p.kind in (p.VAR_POSITIONAL, p.VAR_KEYWORD):
            continue
        kind, nullable = _param_type(hints.get(p.name))
        if kind is None:
            continue
        lo, hi = bounds.get(p.name, (None, None))
        params.append(Param(p.name, kind, p.default, min=lo, max=hi, nullable=nullable))
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


def _dist_name(ep: EntryPoint) -> str:
    return ep.dist.name if ep.dist is not None else ""


def _origin(ep: EntryPoint) -> Origin:
    return "builtin" if _dist_name(ep) == DISTRIBUTION else "plugin"


def _importable(module: str) -> bool:
    """Whether ``module`` can be imported; a missing parent package counts as missing, not as an error."""
    try:
        return find_spec(module) is not None
    except (ImportError, ValueError):  # find_spec("absent.child") raises ModuleNotFoundError
        return False


def default_registry() -> SynthesizerRegistry:
    """A fresh registry with every installed synthesizer plug-in, the built-ins included.

    ``gaussian-copula`` is declared like the other built-ins but is only
    available when the optional ``synthesis`` extra is installed.
    """
    reg = SynthesizerRegistry()
    reg.load_entry_points()
    return reg

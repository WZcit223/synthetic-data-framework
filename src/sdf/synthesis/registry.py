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
from dataclasses import dataclass
from importlib.metadata import EntryPoint, entry_points
from importlib.util import find_spec
from typing import Any, Literal, get_args

from .api import Produces, Synthesizer, SynthesizerInfo

ENTRY_POINT_GROUP = "sdf.synthesizers"
DISTRIBUTION = "synthetic-data-framework"  # entry points declared by this package are the built-ins
_NAME = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")

Origin = Literal["builtin", "plugin", "runtime"]


@dataclass(frozen=True)
class Registration:
    cls: type[Synthesizer]
    origin: Origin  # builtin: declared by this package; plugin: another package; runtime: register() call


class SynthesizerRegistry:
    def __init__(self) -> None:
        self._entries: dict[str, Registration] = {}
        self._unavailable: dict[str, str] = {}

    def register(self, cls: type[Synthesizer], *, replace: bool = False, origin: Origin = "runtime") -> None:
        """Add ``cls`` under ``cls.info.name``; a duplicate name raises unless ``replace``."""
        info = getattr(cls, "info", None)
        if not isinstance(info, SynthesizerInfo):
            raise TypeError(f"{getattr(cls, '__name__', cls)!r} has no SynthesizerInfo `info` class attribute")
        if not _NAME.match(info.name):
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
        for ep in sorted(entry_points(group=group), key=lambda e: e.name):
            origin: Origin = "builtin" if ep.dist is not None and ep.dist.name == DISTRIBUTION else "plugin"
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
        if not isinstance(info.requires, tuple) or not all(isinstance(m, str) for m in info.requires):
            return "info.requires must be a tuple of module names"
        missing = [m for m in info.requires if not _importable(m)]
        if missing:
            return f"needs {', '.join(missing)}"
        try:
            self.register(cls, origin=origin)
        except (TypeError, ValueError) as exc:
            return str(exc)
        return None

    def create(self, name: str, **config: Any) -> Synthesizer:
        """A new instance of the synthesizer registered as ``name``, configured by ``config``."""
        return self._entry(name).cls(**config)

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

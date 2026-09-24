"""One way to mount plug-ins: classes with an ``info`` class attribute, found by entry point.

Every catalogue of the framework (synthesizers, datasets, and later estimators) is
a ``PluginRegistry`` subclass. The classes this package declares in its own
``pyproject.toml`` are the built-ins; any installed package can declare more in
the same entry-point group, and ``register`` adds a class at runtime (from a
notebook, say) without packaging it. The contract is
``docs/refactor/causal/interfaces.md`` §2.

What every catalogue shares lives here: the origin of each entry, the reserved
built-in names, idempotent re-loading, the reasons a declared plug-in is not
mounted, and the checks common to every kind. A subclass adds its own checks by
overriding ``check`` and its own methods (``create``, ``build``, ...).
"""

from __future__ import annotations

import inspect
import re
from dataclasses import dataclass
from importlib.metadata import EntryPoint, entry_points
from importlib.util import find_spec
from typing import Any, ClassVar, Generic, Literal, TypeVar

Origin = Literal["builtin", "plugin", "runtime"]
DISTRIBUTION = "synthetic-data-framework"  # entry points declared by this package are the built-ins
_NAME = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")

T = TypeVar("T")


@dataclass(frozen=True)
class Registration(Generic[T]):
    cls: type[T]
    origin: Origin  # builtin: declared by this package; plugin: another package; runtime: register() call


class PluginRegistry(Generic[T]):
    """Classes with an ``info`` class attribute, by ``info.name``; mounted from one entry-point group."""

    kind: ClassVar[str]  # "synthesizer", "dataset", "estimator": used in every message
    info_type: ClassVar[type]  # SynthesizerInfo, DatasetInfo, EstimatorInfo
    group: ClassVar[str]  # "sdf.synthesizers", "sdf.datasets", "sdf.estimators"
    made_by: ClassVar[str] = "create(name)"  # how the catalogue instantiates a class, for the defaults message

    def __init__(self) -> None:
        self._entries: dict[str, Registration[T]] = {}
        self._unavailable: dict[str, str] = {}

    # -- mounting ---------------------------------------------------------------------------------

    def register(self, cls: type[T], *, replace: bool = False, origin: Origin = "runtime") -> None:
        """Add ``cls`` under ``cls.info.name``; a duplicate name raises unless ``replace``.

        Raises ``TypeError``/``ValueError`` for malformed metadata or when a module in
        ``info.requires`` cannot be imported, so nothing unusable is ever listed as mounted.
        """
        info = getattr(cls, "info", None)
        if not isinstance(info, self.info_type):
            raise TypeError(
                f"{getattr(cls, '__name__', cls)!r} has no {self.info_type.__name__} `info` class attribute"
            )
        if not _NAME.fullmatch(info.name):
            raise ValueError(f"{self.kind} name {info.name!r} must be lower-case words joined by dashes")
        self.check(cls)
        requires = getattr(info, "requires", ())
        if not isinstance(requires, tuple) or not all(isinstance(m, str) for m in requires):
            raise TypeError("info.requires must be a tuple of module names")
        missing = [m for m in requires if not _importable(m)]
        if missing:
            raise ValueError(f"needs {', '.join(missing)}")
        if info.name in self._entries and not replace:
            raise ValueError(f"{self.kind} {info.name!r} is already registered; pass replace=True to override")
        self._entries[info.name] = Registration(cls, origin)
        self._unavailable.pop(info.name, None)

    def check(self, cls: type[T]) -> None:
        """Kind-specific checks, called by ``register`` after the ``info`` and its name.

        Raise ``TypeError`` or ``ValueError``. The default checks that every constructor
        argument has a default; a subclass extends it and calls ``super().check(cls)``.
        """
        self.check_defaults(cls)

    def check_defaults(self, cls: type[T]) -> None:
        """Every constructor argument needs a default, since the catalogue instantiates by name."""
        required = [
            p.name
            for p in inspect.signature(cls).parameters.values()
            if p.default is p.empty and p.kind not in (p.VAR_POSITIONAL, p.VAR_KEYWORD)
        ]
        if required:
            raise TypeError(
                f"{cls.info.name}: every constructor argument needs a default so {self.made_by} works; missing {required}"
            )

    def load_entry_points(self, group: str | None = None) -> list[str]:
        """Mount every class declared in ``group`` (the catalogue's own by default); return the names mounted.

        A plug-in whose ``info.requires`` modules are not installed, or that fails
        to load, is skipped and listed by ``unavailable()`` instead of breaking
        the catalogue.
        """
        mounted: list[str] = []
        # Built-ins first, then plug-ins by distribution name: a plug-in reusing a
        # built-in's name never replaces it, and equal-name plug-ins resolve the same way on every run.
        # Built-in names stay reserved even when the built-in itself is unavailable (e.g. a missing extra).
        declared = sorted(
            entry_points(group=group or self.group), key=lambda e: (_origin(e) != "builtin", _dist_name(e), e.name)
        )
        reserved = {e.name for e in declared if _origin(e) == "builtin"}
        for ep in declared:
            origin = _origin(ep)
            entry = self._entries.get(ep.name)
            if entry is not None and _class_path(entry.cls) == f"{ep.module}:{ep.attr}":
                continue  # mounted by an earlier call (ep.value may also carry extras)
            if entry is not None or (origin != "builtin" and ep.name in reserved):
                holder = (
                    f"a {entry.origin} {self.kind} ({entry.cls.__module__})"
                    if entry is not None
                    else "an unavailable built-in"
                )
                self._unavailable[f"{ep.name} ({_dist_name(ep)})"] = (
                    f"name already provided by {holder}; {ep.value} not mounted"
                )
                continue
            try:
                problem = self._mount(ep, origin)
            except Exception as exc:  # a broken third-party plug-in must not break the catalogue, the CLI or the API
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
        if not isinstance(info, self.info_type):
            return f"{ep.value} has no {self.info_type.__name__} `info` class attribute"
        if info.name != ep.name:
            return f"entry point name differs from info.name {info.name!r}"
        try:
            self.register(cls, origin=origin)
        except (TypeError, ValueError) as exc:
            return str(exc)
        return None

    # -- reading ----------------------------------------------------------------------------------

    def names(self, *, origin: Origin | None = None) -> list[str]:
        return sorted(n for n, e in self._entries.items() if origin is None or e.origin == origin)

    def info(self, name: str) -> Any:
        return self._entry(name).cls.info

    def origin(self, name: str) -> Origin:
        return self._entry(name).origin

    def unavailable(self) -> dict[str, str]:
        """Declared classes that could not be mounted, with the reason."""
        return dict(self._unavailable)

    def _entry(self, name: str) -> Registration[T]:
        if name not in self._entries:
            hint = f" ({self._unavailable[name]})" if name in self._unavailable else ""
            raise KeyError(f"unknown {self.kind} {name!r}{hint}; choose from {self.names()}")
        return self._entries[name]


def _class_path(cls: type) -> str:
    return f"{cls.__module__}:{cls.__qualname__}"


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

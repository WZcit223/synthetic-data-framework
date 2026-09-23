"""Choose a synthesizer by name.

``default_registry()`` holds the built-ins; ``register`` adds a user-written
one (any class that satisfies ``sdf.synthesis.api.Synthesizer``).
Later (F1): ``load_entry_points()`` will mount third-party plug-ins declared in
the ``sdf.synthesizers`` entry-point group.
"""

from __future__ import annotations

from importlib.util import find_spec
from typing import Any

from .api import Synthesizer, SynthesizerInfo
from .bootstrap import BootstrapTable
from .fit import FittedSeasonalDemand
from .warehouse import WarehouseSpecSynthesizer

ENTRY_POINT_GROUP = "sdf.synthesizers"


class SynthesizerRegistry:
    def __init__(self) -> None:
        self._classes: dict[str, type[Synthesizer]] = {}

    def register(self, cls: type[Synthesizer], *, replace: bool = False) -> None:
        """Add ``cls`` under ``cls.info.name``; a duplicate name raises unless ``replace``."""
        info = getattr(cls, "info", None)
        if not isinstance(info, SynthesizerInfo):
            raise TypeError(f"{cls.__name__} has no SynthesizerInfo `info` class attribute")
        if info.name in self._classes and not replace:
            raise ValueError(f"synthesizer {info.name!r} is already registered; pass replace=True to override")
        self._classes[info.name] = cls

    def create(self, name: str, **config: Any) -> Synthesizer:
        """A new instance of the synthesizer registered as ``name``, configured by ``config``."""
        if name not in self._classes:
            raise KeyError(f"unknown synthesizer {name!r}; choose from {self.names()}")
        return self._classes[name](**config)

    def names(self) -> list[str]:
        return sorted(self._classes)

    def info(self, name: str) -> SynthesizerInfo:
        if name not in self._classes:
            raise KeyError(f"unknown synthesizer {name!r}; choose from {self.names()}")
        return self._classes[name].info


def default_registry() -> SynthesizerRegistry:
    """A fresh registry with the built-in synthesizers.

    ``gaussian-copula`` is added only when the optional ``synthesis`` extra
    (``copulas``) is installed.
    """
    reg = SynthesizerRegistry()
    for cls in (BootstrapTable, FittedSeasonalDemand, WarehouseSpecSynthesizer):
        reg.register(cls)
    if find_spec("copulas") is not None:
        from .sdv_synth import GaussianCopulaTable

        reg.register(GaussianCopulaTable)
    return reg

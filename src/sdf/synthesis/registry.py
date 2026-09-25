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

from typing import Any, ClassVar, get_args

from sdf.foundation.params import Param, constructor_params
from sdf.foundation.plugins import (
    DISTRIBUTION as DISTRIBUTION,  # re-exported: the names this module always had
    Origin as Origin,
    PluginRegistry,
    Registration as Registration,
)
from .api import Produces, Synthesizer, SynthesizerInfo

ENTRY_POINT_GROUP = "sdf.synthesizers"


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
    """The parameters a synthesizer publishes: ``sdf.foundation.params.constructor_params``, under its old name."""
    return constructor_params(cls)


def default_registry() -> SynthesizerRegistry:
    """A fresh registry with every installed synthesizer plug-in, the built-ins included.

    ``gaussian-copula`` is declared like the other built-ins but is only
    available when the optional ``synthesis`` extra is installed.
    """
    reg = SynthesizerRegistry()
    reg.load_entry_points()
    return reg

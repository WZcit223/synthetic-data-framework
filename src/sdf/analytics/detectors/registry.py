"""The detector catalogue, and the guard every detector's result passes through.

Detectors are plug-ins in the ``sdf.detectors`` entry-point group, mounted by the
shared loader (``sdf.foundation.plugins``). Every caller runs a detector through
``DetectorRegistry.run``, never directly, so scores of the wrong shape or with a
non-finite value, and a detection outside the frame, with a score that is not a
finite number or with reasons that are not signals of the frame, are refused in one
place; each detection passes on rebuilt, with its score a plain ``float``.
The contract is ``docs/refactor/algorithms/interfaces.md`` §6.2.
"""

from __future__ import annotations

from typing import Any, ClassVar

import numpy as np

from sdf.foundation.params import Param, constructor_params
from sdf.foundation.plugins import PluginRegistry
from .core import DIRECTIONS, Detection, Detector, DetectorInfo, SignalFrame

ENTRY_POINT_GROUP = "sdf.detectors"


class DetectorRegistry(PluginRegistry[Detector]):
    """Detectors by name; built-ins and plug-ins are mounted from the ``sdf.detectors`` group."""

    kind: ClassVar[str] = "detector"
    info_type: ClassVar[type] = DetectorInfo
    group: ClassVar[str] = ENTRY_POINT_GROUP
    made_by: ClassVar[str] = "create(name)"

    def check(self, cls: type[Detector]) -> None:
        for method in ("scores", "detect"):
            if not callable(getattr(cls, method, None)):
                raise TypeError(f"{cls.info.name}: a detector needs a {method}() method")
        super().check(cls)
        constructor_params(cls)  # a malformed param_bounds is refused when mounted, not at run time

    def info(self, name: str) -> DetectorInfo:
        return self._entry(name).cls.info

    def params(self, name: str) -> tuple[Param, ...]:
        """The parameters a client may set on ``name``: its typed constructor keywords."""
        return constructor_params(self._entry(name).cls)

    def check_params(self, name: str, params: dict[str, Any]) -> None:
        """``KeyError`` for an unknown or unavailable ``name``; ``ValueError`` for a parameter it does not take
        or one outside its published bounds."""
        declared = {p.name: p for p in self.params(name)}
        unknown = sorted(set(params) - set(declared))
        if unknown:
            raise ValueError(f"{name} takes no parameter {unknown}; it takes {sorted(declared)}")
        for key, value in params.items():
            problem = declared[key].check(value)
            if problem:
                raise ValueError(f"{name}: {key} {problem}")

    def create(self, name: str, **params: Any) -> Detector:
        """A new instance of ``name`` with ``params``, each checked against its published bounds first."""
        self.check_params(name, params)
        return self._entry(name).cls(**params)

    def run(self, model: Detector, frame: SignalFrame) -> tuple[np.ndarray, list[Detection]]:
        """``model.scores`` and ``model.detect`` through the guard: checked results or ``ValueError``."""
        name = type(model).info.name
        missing = [s for s in type(model).info.signals if s not in frame.signals]
        if missing:
            raise ValueError(f"{name} reads the signals {missing}, which the frame does not have")
        scores = np.asarray(model.scores(frame), dtype=float)
        if scores.shape != frame.shape:
            raise ValueError(f"{name} returned scores of shape {scores.shape}, not {frame.shape} (SKUs × days)")
        if not np.isfinite(scores).all():
            raise ValueError(f"{name} returned a non-finite score")
        checked = []
        skus, days = set(frame.sku_ids), set(frame.days)
        for d in model.detect(frame):
            if not isinstance(d, Detection):
                raise ValueError(f"{name} returned {type(d).__name__}, not a Detection")
            if d.sku_id not in skus or d.day not in days:
                raise ValueError(f"{name} reported {d.sku_id} on {d.day}, which is not in the frame")
            if d.direction not in DIRECTIONS:
                raise ValueError(f"{name} reported the direction {d.direction!r}; it must be one of {list(DIRECTIONS)}")
            try:
                score = float(d.score) if not isinstance(d.score, (str, bytes)) else None
            except (TypeError, ValueError):
                score = None
            if score is None or not np.isfinite(score):
                raise ValueError(
                    f"{name} reported the score {d.score!r} for {d.sku_id} on {d.day}, not a finite number"
                )
            reasons = d.signals
            if not isinstance(reasons, tuple) or any(not isinstance(r, str) or r not in frame.signals for r in reasons):
                raise ValueError(f"{name} named the signals {reasons!r}; they must be a tuple of the frame's signals")
            checked.append(Detection(d.sku_id, d.day, score, d.direction, reasons))
        return scores, checked


def default_detectors() -> DetectorRegistry:
    """A registry with the ``sdf.detectors`` group mounted, like ``default_forecasters()``."""
    reg = DetectorRegistry()
    reg.load_entry_points()
    return reg

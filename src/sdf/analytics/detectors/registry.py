"""The detector catalogue, and the guard every detector's result passes through.

Detectors are plug-ins in the ``sdf.detectors`` entry-point group, mounted by the
shared loader (``sdf.foundation.plugins``). Every caller runs a detector through
``DetectorRegistry.run``, never directly, so scores of the wrong shape or with a
non-finite value, and a detection outside the frame, are refused in one place.
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

    def create(self, name: str, **params: Any) -> Detector:
        """A new instance of ``name`` with ``params``, each checked against its published bounds first."""
        declared = {p.name: p for p in self.params(name)}
        unknown = sorted(set(params) - set(declared))
        if unknown:
            raise ValueError(f"{name} takes no parameter {unknown}; it takes {sorted(declared)}")
        for key, value in params.items():
            problem = declared[key].check(value)
            if problem:
                raise ValueError(f"{name}: {key} {problem}")
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
        detections = list(model.detect(frame))
        skus, days = set(frame.sku_ids), set(frame.days)
        for d in detections:
            if not isinstance(d, Detection):
                raise ValueError(f"{name} returned {type(d).__name__}, not a Detection")
            if d.sku_id not in skus or d.day not in days:
                raise ValueError(f"{name} reported {d.sku_id} on {d.day}, which is not in the frame")
            if d.direction not in DIRECTIONS:
                raise ValueError(f"{name} reported the direction {d.direction!r}; it must be one of {list(DIRECTIONS)}")
            if not np.isfinite(d.score):
                raise ValueError(f"{name} reported a non-finite score for {d.sku_id} on {d.day}")
        return scores, detections


def default_detectors() -> DetectorRegistry:
    """A registry with the ``sdf.detectors`` group mounted, like ``default_forecasters()``."""
    reg = DetectorRegistry()
    reg.load_entry_points()
    return reg

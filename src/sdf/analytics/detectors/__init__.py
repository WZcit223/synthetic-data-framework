"""Anomaly detectors as plug-ins over a frame of daily signals per SKU, scored on injected anomalies.

A detector rates every SKU-day of a ``SignalFrame`` and reports the points it would
alarm on; ``score_detectors`` measures several on a frame with known anomalies. The
frame of a world is built in ``sdf.simulation.signals``. The contract is
``docs/refactor/algorithms/interfaces.md`` §6.
"""

from .core import DIRECTIONS, Detection, Detector, DetectorInfo, SignalFrame
from .registry import ENTRY_POINT_GROUP, DetectorRegistry, default_detectors
from .scoring import CUTS, MAX_DETECTORS, SCORES_INFO, score_detectors, top_k

__all__ = [
    "CUTS",
    "DIRECTIONS",
    "ENTRY_POINT_GROUP",
    "MAX_DETECTORS",
    "SCORES_INFO",
    "Detection",
    "Detector",
    "DetectorInfo",
    "DetectorRegistry",
    "SignalFrame",
    "default_detectors",
    "score_detectors",
    "top_k",
]

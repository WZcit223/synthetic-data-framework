"""Causal effect estimation from observational rows, with estimators as plug-ins.

The question names a treatment, an outcome and an adjustment set (the user's
claim); every estimator answers it on the rows ``design`` prepares, and ``score``
compares several on the same rows, against the true effect when it is known.
The contract is ``docs/refactor/causal/interfaces.md`` §3.
"""

from .core import CausalQuestion, Design, Estimate, Estimator, EstimatorInfo, check_confidence, design, identify
from .registry import (
    ENTRY_POINT_GROUP,
    MAX_ESTIMATE_SECONDS,
    SCORES_INFO,
    EstimatorRegistry,
    default_estimators,
    score,
    scores_info,
)

__all__ = [
    "ENTRY_POINT_GROUP",
    "MAX_ESTIMATE_SECONDS",
    "SCORES_INFO",
    "CausalQuestion",
    "Design",
    "Estimate",
    "Estimator",
    "EstimatorInfo",
    "EstimatorRegistry",
    "check_confidence",
    "default_estimators",
    "design",
    "identify",
    "score",
    "scores_info",
]

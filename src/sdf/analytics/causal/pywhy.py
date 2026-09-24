"""Estimators from the PyWhy stack, mounted only with the ``causal`` extra.

``dowhy-backdoor`` needs DoWhy (Python 3.13 only, see pyproject.toml) and ``econml-dml``
needs EconML. Each declares its module in ``info.requires``, so without it the estimator
is listed as unavailable with the reason instead of failing. Both work on the arrays
``design`` prepares, under column names the libraries accept.
"""

from __future__ import annotations

import warnings
from typing import ClassVar

import numpy as np

from sdf.foundation.tables import Table
from .core import CausalQuestion, Estimate, EstimatorInfo, design


def _pct(confidence: float) -> str:
    return f"{confidence * 100:g} %"


class DowhyBackdoor:
    """DoWhy's back-door adjustment over the declared covariates, estimated by linear regression."""

    info: ClassVar[EstimatorInfo] = EstimatorInfo(
        "dowhy-backdoor",
        "DoWhy: back-door criterion over the declared covariates, linear regression",
        requires=("dowhy",),
    )

    def estimate(self, table: Table, question: CausalQuestion, *, confidence: float = 0.95, seed: int = 7) -> Estimate:
        import pandas as pd
        from dowhy import CausalModel

        d = design(table, question)
        causes = [f"w{i}" for i in range(len(d.columns))]
        frame = pd.DataFrame({"t": d.treated, "y": d.outcome, **{c: d.covariates[:, i] for i, c in enumerate(causes)}})
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            model = CausalModel(data=frame, treatment="t", outcome="y", common_causes=causes or None)
            estimand = model.identify_effect(proceed_when_unidentifiable=True)
            est = model.estimate_effect(
                estimand,
                method_name="backdoor.linear_regression",
                confidence_intervals=True,
                test_significance=False,
                method_params={"confidence_level": confidence},
            )
            lo, hi = (
                float(v) for v in np.asarray(est.get_confidence_intervals(confidence_level=confidence)).ravel()[:2]
            )
        n1 = int(d.treated.sum())
        return Estimate(
            self.info.name,
            float(est.value),
            lo,
            hi,
            n1,
            len(d.outcome) - n1,
            f"DoWhy back-door, linear regression, {_pct(confidence)}",
        )


class EconmlDml:
    """EconML's LinearDML with the covariates as controls; its average effect and interval."""

    info: ClassVar[EstimatorInfo] = EstimatorInfo(
        "econml-dml",
        "EconML: double machine learning (LinearDML) with the covariates as controls",
        requires=("econml",),
    )

    def estimate(self, table: Table, question: CausalQuestion, *, confidence: float = 0.95, seed: int = 7) -> Estimate:
        from econml.dml import LinearDML

        d = design(table, question)
        controls = d.covariates if d.columns else None
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            model = LinearDML(discrete_treatment=True, random_state=seed)
            model.fit(d.outcome, d.treated.astype(int), X=None, W=controls)
            effect = float(np.ravel(model.ate())[0])
            lo, hi = (float(np.ravel(v)[0]) for v in model.ate_interval(alpha=1 - confidence))
        n1 = int(d.treated.sum())
        return Estimate(
            self.info.name, effect, lo, hi, n1, len(d.outcome) - n1, f"EconML LinearDML, {_pct(confidence)}"
        )

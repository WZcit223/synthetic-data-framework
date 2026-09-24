"""The built-in estimators: the naive difference, regression adjustment and inverse propensity weighting.

Each is a stand-in for the estimators the algorithm phase brings (docs/ALGORITHM_AND_DATA_CHECKLIST.md,
row C8). They take their arrays from ``design`` and report an interval with the method that made it.
"""

from __future__ import annotations

import math
import warnings
from typing import ClassVar

import numpy as np
from scipy import stats

from sdf.foundation.tables import Table
from .core import CausalQuestion, Estimate, EstimatorInfo, design, model_matrix

CLIP = (0.01, 0.99)  # ipw's propensity bounds
MAX_CLIPPED_SHARE = 0.10  # above this share of rows outside CLIP, ipw refuses: too little overlap
BOOTSTRAP = 200  # ipw's resamples


def _pct(confidence: float) -> str:
    return f"{confidence * 100:g} %"


class DifferenceInMeans:
    """Treated mean minus control mean, ignoring the covariates, with a Welch t interval.

    ALGORITHM-HOOK[C8]: the naive comparison, kept as the reference that shows what confounding does.
    """

    info: ClassVar[EstimatorInfo] = EstimatorInfo(
        "difference-in-means",
        "Treated mean minus control mean, ignoring the covariates (the naive comparison)",
        uses_covariates=False,
    )

    def estimate(self, table: Table, question: CausalQuestion, *, confidence: float = 0.95, seed: int = 7) -> Estimate:
        d = design(table, question)
        y1, y0 = d.outcome[d.treated], d.outcome[~d.treated]
        n1, n0 = len(y1), len(y0)
        effect = float(y1.mean() - y0.mean())
        v1, v0 = float(y1.var(ddof=1)) / n1, float(y0.var(ddof=1)) / n0
        se = math.sqrt(v1 + v0)
        if se == 0:
            half = 0.0  # both groups constant: the difference is exact
        else:
            df = (v1 + v0) ** 2 / ((v1**2 / (n1 - 1) if v1 else 0.0) + (v0**2 / (n0 - 1) if v0 else 0.0))
            half = float(stats.t.ppf((1 + confidence) / 2, df)) * se
        return Estimate(self.info.name, effect, effect - half, effect + half, n1, n0, f"Welch t, {_pct(confidence)}")


class RegressionAdjustment:
    """Least squares of the outcome on the treatment and the covariates; the treatment's coefficient.

    ALGORITHM-HOOK[C8]: a linear adjustment on a declared set; the algorithm phase brings double
    machine learning with flexible learners, causal forests and sensitivity analysis.
    """

    info: ClassVar[EstimatorInfo] = EstimatorInfo(
        "regression-adjustment",
        "Least squares of the outcome on the treatment and the covariates, with robust (HC1) errors",
    )

    def estimate(self, table: Table, question: CausalQuestion, *, confidence: float = 0.95, seed: int = 7) -> Estimate:
        d = design(table, question)
        x, _ = model_matrix(d, uses_covariates=True)
        y = d.outcome
        n, p = x.shape
        xtx_inv = np.linalg.inv(x.T @ x)
        beta = xtx_inv @ x.T @ y
        resid = y - x @ beta
        meat = (x * (resid**2)[:, None]).T @ x
        cov = xtx_inv @ meat @ xtx_inv * (n / (n - p))  # HC1
        effect = float(beta[1])
        se = math.sqrt(max(float(cov[1, 1]), 0.0))
        half = float(stats.t.ppf((1 + confidence) / 2, n - p)) * se
        n1 = int(d.treated.sum())
        return Estimate(
            self.info.name, effect, effect - half, effect + half, n1, n - n1, f"OLS, HC1 errors, {_pct(confidence)}"
        )


class Ipw:
    """Hajek inverse propensity weighting with a logistic propensity on the covariates.

    The propensity's overlap is checked before clipping: more than 10 % of the rows outside
    [0.01, 0.99] is refused; fewer are clipped, and ``method`` says how many. The interval is
    the percentile interval of 200 bootstrap resamples drawn with ``seed``.

    ALGORITHM-HOOK[C8]: a logistic propensity on a declared set; the algorithm phase brings
    flexible propensity models, doubly robust estimation and overlap diagnostics.
    """

    info: ClassVar[EstimatorInfo] = EstimatorInfo(
        "ipw",
        "Inverse propensity weighting (Hajek) with a logistic propensity; bootstrap interval",
    )

    def estimate(self, table: Table, question: CausalQuestion, *, confidence: float = 0.95, seed: int = 7) -> Estimate:
        d = design(table, question)
        t, y, x = d.treated, d.outcome, d.covariates
        n = len(y)
        e = _propensity(t, x)
        outside = int(((e < CLIP[0]) | (e > CLIP[1])).sum())
        if outside > MAX_CLIPPED_SHARE * n:
            raise ValueError(f"no overlap: {outside} of {n} rows have a propensity outside [{CLIP[0]}, {CLIP[1]}]")
        effect = _hajek(t, y, np.clip(e, *CLIP))
        rng = np.random.default_rng(seed)
        draws = []
        while len(draws) < BOOTSTRAP:
            i = rng.integers(0, n, n)
            tb = t[i]
            if tb.sum() < 1 or (~tb).sum() < 1:
                continue  # a resample needs both groups
            draws.append(_hajek(tb, y[i], np.clip(_propensity(tb, x[i]), *CLIP)))
        alpha = (1 - confidence) / 2
        lo, hi = (float(q) for q in np.quantile(draws, [alpha, 1 - alpha]))
        method = f"Hajek IPW, logistic propensity, {BOOTSTRAP} bootstrap resamples, {_pct(confidence)}"
        if outside:
            method += f", {outside} rows clipped"
        n1 = int(t.sum())
        return Estimate(self.info.name, effect, lo, hi, n1, n - n1, method)


def _propensity(t: np.ndarray, x: np.ndarray) -> np.ndarray:
    """The fitted probability of treatment per row; the treated share when there are no covariates."""
    if x.shape[1] == 0:
        return np.full(len(t), t.mean())
    from sklearn.linear_model import LogisticRegression  # the core dependency, imported on first use

    sd = x.std(axis=0)
    z = (x - x.mean(axis=0)) / np.where(sd > 0, sd, 1.0)  # standardised: the fit converges on any scale
    model = LogisticRegression(C=1e4, max_iter=2000)  # all but unpenalised
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # a separating covariate does not converge; the overlap check refuses it
        model.fit(z, t)
    return model.predict_proba(z)[:, 1]


def _hajek(t: np.ndarray, y: np.ndarray, e: np.ndarray) -> float:
    w1 = t / e
    w0 = (~t) / (1 - e)
    return float((w1 * y).sum() / w1.sum() - (w0 * y).sum() / w0.sum())

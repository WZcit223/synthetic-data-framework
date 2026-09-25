"""SDV-family synthesis + real SDMetrics fidelity (Phase 2.1 full, checklist B1).

This is the production-path synthesizer: it fits a **Gaussian copula** (the same
engine behind SDV's ``GaussianCopulaSynthesizer``) on the real transaction table
and scores fidelity with **SDMetrics** (column-shape KSComplement + pair-trend
CorrelationSimilarity). It is an OPTIONAL extra — it needs
``pandas numpy copulas sdmetrics`` — so it is imported lazily and never on the
core path. The dependency-free `fit.py`/`fidelity.py` remain the default.

    uv sync --extra synthesis
    uv run sdf sdv data/online_retail_ii_2010_10k.csv

ALGORITHM-HOOK[A1]: swap GaussianCopula for CTGAN/TVAE (adds torch) for higher
fidelity on complex joint distributions; the SDMetrics scoring is identical.
"""

from __future__ import annotations

from typing import ClassVar

from .api import SynthesizerInfo, TableData, apply_kinds

_COLS = ["Quantity", "Price", "hour", "weekday"]
_PAIRS = [("Quantity", "Price"), ("Quantity", "hour"), ("Price", "weekday")]


def _load_line_table(path: str, max_rows: int = 2000, seed: int = 1):
    import pandas as pd

    df = pd.read_csv(path, on_bad_lines="skip", engine="python")
    df.columns = [c.strip() for c in df.columns]
    df = df[(df["Quantity"] > 0) & (df["Price"] > 0)].copy()
    dt = pd.to_datetime(df["InvoiceDate"], format="%m/%d/%y %H:%M", errors="coerce")
    dt = dt.fillna(pd.to_datetime(df["InvoiceDate"], errors="coerce"))
    df["hour"] = dt.dt.hour
    df["weekday"] = dt.dt.weekday
    real = df[_COLS].dropna().astype(float)
    # Trim the top 1% of Quantity so a few huge orders don't dominate the fit.
    q99 = real["Quantity"].quantile(0.99)
    real = real[real["Quantity"] < q99]
    if len(real) > max_rows:
        real = real.sample(max_rows, random_state=seed)
    return real.reset_index(drop=True)


class GaussianCopulaTable:
    """Gaussian copula over a numeric table (``gaussian-copula``; needs the ``synthesis`` extra).

    ``copulas`` fits the marginals and the correlation. Sampling is done here on
    this model's own ``numpy.random.Generator`` (multivariate normal → normal
    CDF → each marginal's inverse CDF, the same steps as
    ``GaussianMultivariate.sample``), because that method draws from NumPy's
    process-global generator. Nothing global is read or written, repeated
    ``sample()`` calls continue the model's stream, and ``seed`` pins one draw. The
    table's column kinds are applied to every row (``apply_kinds``).
    """

    info: ClassVar[SynthesizerInfo] = SynthesizerInfo(
        name="gaussian-copula",
        produces="table",
        needs_fit=True,
        description="Gaussian copula with fitted marginals (copulas.GaussianMultivariate)",
        requires=("copulas", "pandas", "numpy", "scipy"),
    )

    def __init__(self, *, seed: int | None = None) -> None:
        import numpy as np

        self._rng = np.random.default_rng(seed)
        self._n_rows = 0
        self._model = None
        self._data: TableData | None = None

    def fit(self, data: TableData) -> GaussianCopulaTable:
        import pandas as pd
        from copulas.multivariate import GaussianMultivariate

        self._data = data
        self._n_rows = len(data.rows)
        self._model = GaussianMultivariate()
        self._model.fit(pd.DataFrame(data.rows, columns=list(data.columns), dtype=float))
        return self

    def sample(self, n: int | None = None, *, seed: int | None = None) -> list[tuple[float, ...]]:
        import numpy as np
        from scipy import stats

        if self._model is None:
            raise RuntimeError("gaussian-copula: call fit() before sample()")
        n = self._n_rows if n is None else n
        if n == 0:
            return []
        rng = np.random.default_rng(seed) if seed is not None else self._rng
        correlation = np.asarray(
            self._model.correlation, dtype=float
        )  # a DataFrame in copulas 0.14; an array elsewhere
        normal = rng.multivariate_normal(np.zeros(len(correlation)), correlation, size=n)
        cdf = stats.norm.cdf(normal)
        columns = [np.asarray(u.percent_point(cdf[:, j]), dtype=float) for j, u in enumerate(self._model.univariates)]
        return apply_kinds([tuple(float(c[i]) for c in columns) for i in range(n)], self._data)


def gaussian_copula_fidelity(path: str, *, max_rows: int = 2000, seed: int = 1) -> dict:
    """Fit a Gaussian copula on the real table and score it with SDMetrics."""
    from copulas.multivariate import GaussianMultivariate
    from sdmetrics.column_pairs import CorrelationSimilarity
    from sdmetrics.single_column import KSComplement

    real = _load_line_table(path, max_rows=max_rows, seed=seed)
    model = GaussianMultivariate()
    model.fit(real)
    synth = model.sample(len(real))

    ks: dict[str, float] = {c: round(float(KSComplement.compute(real[c], synth[c])), 4) for c in _COLS}
    corr: dict[str, float] = {}
    for a, b in _PAIRS:
        try:
            corr[f"{a}~{b}"] = round(float(CorrelationSimilarity.compute(real[[a, b]], synth[[a, b]])), 4)
        except Exception:
            pass

    column_shape = sum(ks.values()) / len(ks)
    pair_trend = sum(corr.values()) / len(corr) if corr else 0.0
    overall = 0.5 * column_shape + 0.5 * pair_trend
    return {
        "rows_used": int(len(real)),
        "column_shape_ks": ks,
        "pair_trend_corr": corr,
        "column_shape_score": round(column_shape, 4),
        "pair_trend_score": round(pair_trend, 4),
        "sdmetrics_overall": round(overall, 4),  # 0..1, higher = more faithful
    }

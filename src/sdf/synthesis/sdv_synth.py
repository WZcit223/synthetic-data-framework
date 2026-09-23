"""SDV-family synthesis + real SDMetrics fidelity (Phase 2.1 full, checklist B1).

This is the production-path synthesizer: it fits a **Gaussian copula** (the same
engine behind SDV's ``GaussianCopulaSynthesizer``) on the real transaction table
and scores fidelity with **SDMetrics** (column-shape KSComplement + pair-trend
CorrelationSimilarity). It is an OPTIONAL extra — it needs
``pandas numpy copulas sdmetrics`` — so it is imported lazily and never on the
core path. The dependency-free `fit.py`/`fidelity.py` remain the default.

    uv sync --extra synthesis
    uv run sdf sdv data/online_retail_ii_2010_10k.csv

ALGORITHM-HOOK: swap GaussianCopula for CTGAN/TVAE (adds torch) for higher
fidelity on complex joint distributions; the SDMetrics scoring is identical.
"""

from __future__ import annotations

from typing import ClassVar

from .api import SynthesizerInfo, TableData

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

    ``seed`` seeds numpy's global generator before each draw, which is where
    ``copulas`` samples from; without a seed a draw uses whatever state numpy has.
    """

    info: ClassVar[SynthesizerInfo] = SynthesizerInfo(
        name="gaussian-copula",
        produces="table",
        needs_fit=True,
        description="Gaussian copula with fitted marginals (copulas.GaussianMultivariate)",
    )

    def __init__(self, *, seed: int | None = None) -> None:
        self.seed = seed
        self._columns: tuple[str, ...] = ()
        self._n_rows = 0
        self._model = None

    def fit(self, data: TableData) -> GaussianCopulaTable:
        import pandas as pd
        from copulas.multivariate import GaussianMultivariate

        self._columns, self._n_rows = tuple(data.columns), len(data.rows)
        self._model = GaussianMultivariate()
        self._model.fit(pd.DataFrame(data.rows, columns=list(data.columns), dtype=float))
        return self

    def sample(self, n: int | None = None, *, seed: int | None = None) -> list[tuple[float, ...]]:
        import numpy as np

        if self._model is None:
            raise RuntimeError("gaussian-copula: call fit() before sample()")
        pinned = seed if seed is not None else self.seed
        if pinned is not None:
            np.random.seed(pinned)
        n = self._n_rows if n is None else n
        if n == 0:
            return []
        frame = self._model.sample(n)
        return [tuple(float(v) for v in row) for row in frame[list(self._columns)].itertuples(index=False)]


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

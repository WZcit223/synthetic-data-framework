"""SDV-family synthesis + real SDMetrics fidelity (Phase 2.1 full, checklist B1).

This is the production-path synthesizer: it fits a **Gaussian copula** (the same
engine behind SDV's ``GaussianCopulaSynthesizer``) on the real transaction table
and scores fidelity with **SDMetrics** (column-shape KSComplement + pair-trend
CorrelationSimilarity). It is an OPTIONAL extra — it needs
``pandas numpy copulas sdmetrics`` — so it is imported lazily and never on the
core path. The dependency-free `fit.py`/`fidelity.py` remain the default.

    pip install copulas sdmetrics pandas numpy
    python -m sdf.cli sdv data/online_retail_ii_2010_10k.csv

ALGORITHM-HOOK: swap GaussianCopula for CTGAN/TVAE (adds torch) for higher
fidelity on complex joint distributions; the SDMetrics scoring is identical.
"""

from __future__ import annotations

from typing import Dict, List

_COLS = ["Quantity", "Price", "hour", "weekday"]
_PAIRS = [("Quantity", "Price"), ("Quantity", "hour"), ("Price", "weekday")]


def _load_line_table(path: str, max_rows: int = 2000, seed: int = 1):
    import pandas as pd

    df = pd.read_csv(path)
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


def gaussian_copula_fidelity(path: str, max_rows: int = 2000,
                             seed: int = 1) -> Dict:
    """Fit a Gaussian copula on the real table and score it with SDMetrics."""
    from copulas.multivariate import GaussianMultivariate
    from sdmetrics.single_column import KSComplement
    from sdmetrics.column_pairs import CorrelationSimilarity

    real = _load_line_table(path, max_rows=max_rows, seed=seed)
    model = GaussianMultivariate()
    model.fit(real)
    synth = model.sample(len(real))

    ks: Dict[str, float] = {
        c: round(float(KSComplement.compute(real[c], synth[c])), 4) for c in _COLS
    }
    corr: Dict[str, float] = {}
    for a, b in _PAIRS:
        try:
            corr[f"{a}~{b}"] = round(float(CorrelationSimilarity.compute(
                real[[a, b]], synth[[a, b]])), 4)
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
        "sdmetrics_overall": round(overall, 4),   # 0..1, higher = more faithful
    }

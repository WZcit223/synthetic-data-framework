"""Synthetic-data fidelity metrics (checklist B1), dependency-free.

Scores how well a synthetic series matches a real reference on:
  - distribution   : two-sample Kolmogorov–Smirnov statistic (0 = identical)
  - seasonality    : Pearson correlation of the hour-of-day profiles (1 = identical)
  - moments        : relative delta of mean and standard deviation

This is a lightweight stand-in for SDMetrics. ALGORITHM-HOOK: for production use
SDMetrics' full report (column-shape, pair-trends) and add privacy (DCR) and a
synthetic-vs-real detection AUC — see docs/ALGORITHM_AND_DATA_CHECKLIST.md (B1–B4).
"""

from __future__ import annotations

import math
from typing import Dict, List


def ks_2samp(a: List[float], b: List[float]) -> float:
    """Two-sample KS statistic = max |F_a(x) - F_b(x)| (ties handled)."""
    import bisect
    if not a or not b:
        return 1.0
    sa, sb = sorted(a), sorted(b)
    na, nb = len(sa), len(sb)
    d = 0.0
    for x in sorted(set(sa) | set(sb)):
        fa = bisect.bisect_right(sa, x) / na
        fb = bisect.bisect_right(sb, x) / nb
        d = max(d, abs(fa - fb))
    return round(d, 4)


def pearson(a: List[float], b: List[float]) -> float:
    n = min(len(a), len(b))
    if n < 2:
        return 0.0
    a, b = a[:n], b[:n]
    ma, mb = sum(a) / n, sum(b) / n
    cov = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    va = math.sqrt(sum((x - ma) ** 2 for x in a))
    vb = math.sqrt(sum((y - mb) ** 2 for y in b))
    if va == 0 or vb == 0:
        return 0.0
    return round(cov / (va * vb), 4)


def _profile(series: List[float], ppd: int) -> List[float]:
    prof = [0.0] * ppd
    cnt = [0] * ppd
    for i, v in enumerate(series):
        prof[i % ppd] += v
        cnt[i % ppd] += 1
    return [prof[h] / c if c else 0.0 for h, c in enumerate(cnt)]


def _std(x: List[float]) -> float:
    n = len(x)
    if n < 2:
        return 0.0
    m = sum(x) / n
    return math.sqrt(sum((v - m) ** 2 for v in x) / n)


def fidelity_report(real: List[float], synth: List[float], ppd: int) -> Dict:
    """Compare a synthetic series to a real reference; higher = more faithful."""
    rmean = sum(real) / len(real) if real else 0.0
    smean = sum(synth) / len(synth) if synth else 0.0
    rstd, sstd = _std(real), _std(synth)
    prof_corr = pearson(_profile(real, ppd), _profile(synth, ppd))
    ks = ks_2samp(real, synth)
    return {
        "ks_statistic": ks,                       # 0 = distributions identical
        "profile_corr": prof_corr,                # 1 = seasonality identical
        "mean_delta_pct": round(100 * (smean - rmean) / rmean, 2) if rmean else None,
        "std_delta_pct": round(100 * (sstd - rstd) / rstd, 2) if rstd else None,
        "real_mean": round(rmean, 2),
        "synth_mean": round(smean, 2),
        # Convenience 0–100 score: rewards low KS + high profile correlation.
        "fidelity_score": round(100 * (1 - ks) * max(0.0, prof_corr), 1),
    }

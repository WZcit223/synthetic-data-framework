"""Anomaly detection on demand series (checklist C3), dependency-free.

Method: **seasonal residual + robust z-score**. We estimate a seasonal profile
(median per position-in-cycle), take residuals, and flag points whose residual is
more than ``k`` robust-z (MAD-scaled) from the residual median. Using medians/MAD
makes it resistant to the very outliers it is trying to find.

ALGORITHM-HOOK: replace with Isolation Forest / autoencoder over the multivariate
inventory + demand + sensor state for richer, multi-signal anomalies.
"""

from __future__ import annotations

import statistics
from typing import Dict, List


def _profile_median(values: List[float], period: int) -> List[float]:
    buckets: List[List[float]] = [[] for _ in range(period)]
    for i, v in enumerate(values):
        buckets[i % period].append(v)
    return [statistics.median(b) if b else 0.0 for b in buckets]


def seasonal_residual_anomalies(values: List[float], period: int,
                                k: float = 3.5) -> List[Dict]:
    """Flag points whose seasonal residual exceeds k robust-z (MAD-scaled)."""
    if len(values) < max(2 * period, 8):
        return []
    profile = _profile_median(values, period)
    resid = [v - profile[i % period] for i, v in enumerate(values)]
    med = statistics.median(resid)
    mad = statistics.median([abs(r - med) for r in resid]) or 1e-9
    out: List[Dict] = []
    for i, (v, r) in enumerate(zip(values, resid)):
        z = 0.6745 * (r - med) / mad          # robust z-score
        if abs(z) >= k:
            out.append({
                "index": i,
                "value": round(v, 2),
                "expected": round(profile[i % period], 2),
                "residual": round(r, 2),
                "robust_z": round(z, 2),
                "direction": "spike" if z > 0 else "drop",
            })
    out.sort(key=lambda a: abs(a["robust_z"]), reverse=True)
    return out

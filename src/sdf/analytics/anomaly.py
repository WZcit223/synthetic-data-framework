"""Anomaly detection on demand series (checklist C3), dependency-free.

Method: **seasonal residual + robust z-score**. We estimate a seasonal profile
(median per position-in-cycle), take residuals, and flag points whose residual is
more than ``k`` robust-z from the residual median. Using medians/MAD makes it
resistant to the very outliers it is trying to find.

The scale is the MAD converted to a standard deviation. When more than half of
the residuals equal their median (a flat or mostly-zero series) the MAD is 0;
the mean absolute deviation is used instead, and the scale never goes below
``min_scale`` demand units, so selling one unit on an otherwise empty day is
never an "anomaly" and a perfectly flat series has none.

ALGORITHM-HOOK[C3]: replace with Isolation Forest / autoencoder over the multivariate
inventory + demand + sensor state for richer, multi-signal anomalies.
"""

from __future__ import annotations

import statistics


def _profile_median(values: list[float], period: int) -> list[float]:
    buckets: list[list[float]] = [[] for _ in range(period)]
    for i, v in enumerate(values):
        buckets[i % period].append(v)
    return [statistics.median(b) if b else 0.0 for b in buckets]


MAD_TO_SIGMA = 0.6745  # MAD = 0.6745 σ for normal data
MEAN_ABS_TO_SIGMA = 0.7979  # mean absolute deviation = 0.7979 σ


def residual_scale(resid: list[float], *, min_scale: float = 1.0) -> tuple[float, str]:
    """Robust standard-deviation estimate of residuals and the method that produced it."""
    med = statistics.median(resid)
    mad = statistics.median([abs(r - med) for r in resid])
    if mad > 0 and mad / MAD_TO_SIGMA >= min_scale:
        return mad / MAD_TO_SIGMA, "mad"
    mean_abs = sum(abs(r - med) for r in resid) / len(resid)
    if mad == 0 and mean_abs / MEAN_ABS_TO_SIGMA >= min_scale:
        return mean_abs / MEAN_ABS_TO_SIGMA, "mean_abs_dev"
    return min_scale, "floor"


def seasonal_residual_anomalies(
    values: list[float], period: int, k: float = 3.5, *, min_scale: float = 1.0
) -> list[dict]:
    """Flag points whose seasonal residual exceeds ``k`` robust-z."""
    if len(values) < max(2 * period, 8):
        return []
    profile = _profile_median(values, period)
    resid = [v - profile[i % period] for i, v in enumerate(values)]
    med = statistics.median(resid)
    scale, _method = residual_scale(resid, min_scale=min_scale)
    out: list[dict] = []
    for i, (v, r) in enumerate(zip(values, resid)):
        z = (r - med) / scale  # robust z-score
        if abs(z) >= k:
            out.append(
                {
                    "index": i,
                    "value": round(v, 2),
                    "expected": round(profile[i % period], 2),
                    "residual": round(r, 2),
                    "robust_z": round(z, 2),
                    "direction": "spike" if z > 0 else "drop",
                }
            )
    out.sort(key=lambda a: abs(a["robust_z"]), reverse=True)
    return out

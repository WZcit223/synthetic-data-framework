"""Synthetic-data privacy metrics (checklist B3), dependency-free.

Privacy is the precondition for *sharing or selling* synthetic data. We compute
leakage risk between a synthetic table and the real table it was derived from:

  - DCR  (Distance to Closest Record): for each synthetic row, the distance to the
          nearest real row. Larger = safer (synthetic isn't copying real records).
  - NNDR (Nearest-Neighbour Distance Ratio): nearest / second-nearest distance;
          values near 1 mean the synthetic point is not singling out one real row.
  - clone risk: fraction of synthetic rows that are near-duplicates of a real row
          (DCR below a small epsilon) — a direct membership-leakage proxy.

Features are min-max normalised so distances are comparable across columns.
ALGORITHM-HOOK: for production add full membership-inference attacks and, if
sharing externally, differential-privacy guarantees.
"""

from __future__ import annotations

import math
import random
import statistics
from typing import Dict, List, Sequence, Tuple

Row = Sequence[float]


def _normaliser(rows: List[Row]):
    cols = list(zip(*rows)) if rows else []
    lo = [min(c) for c in cols]
    hi = [max(c) for c in cols]
    span = [(h - l) or 1.0 for l, h in zip(lo, hi)]

    def norm(r: Row) -> List[float]:
        return [(v - l) / s for v, l, s in zip(r, lo, span)]
    return norm


def _two_nearest(p: List[float], reals: List[List[float]]) -> Tuple[float, float]:
    d1 = d2 = float("inf")
    for q in reals:
        d = math.sqrt(sum((a - b) ** 2 for a, b in zip(p, q)))
        if d < d1:
            d1, d2 = d, d1
        elif d < d2:
            d2 = d
    return d1, d2


def privacy_report(real: List[Row], synth: List[Row], eps: float = 0.02,
                   max_n: int = 800, seed: int = 7) -> Dict:
    """Compute DCR / NNDR / clone-risk between synthetic and real tables."""
    if not real or not synth:
        return {"error": "empty input"}
    rng = random.Random(seed)
    real_s = real if len(real) <= max_n else rng.sample(list(real), max_n)
    synth_s = synth if len(synth) <= max_n else rng.sample(list(synth), max_n)
    norm = _normaliser(list(real_s) + list(synth_s))
    R = [norm(r) for r in real_s]
    dcrs, nndrs, clones = [], [], 0
    for p in (norm(s) for s in synth_s):
        d1, d2 = _two_nearest(p, R)
        dcrs.append(d1)
        nndrs.append(d1 / d2 if d2 > 0 else 1.0)
        if d1 < eps:
            clones += 1
    dcrs.sort()
    return {
        "n_real": len(real_s), "n_synth": len(synth_s), "dims": len(R[0]),
        "dcr_median": round(statistics.median(dcrs), 4),
        "dcr_p05": round(dcrs[max(0, int(0.05 * len(dcrs)) - 1)], 4),
        "nndr_median": round(statistics.median(nndrs), 4),
        "clone_risk_pct": round(100 * clones / len(synth_s), 2),
        "verdict": ("low leakage risk" if dcrs[max(0, int(0.05 * len(dcrs)) - 1)] > eps
                    else "review — some synthetic rows are close to real rows"),
    }


def read_retail_feature_table(path: str, limit: int = 3000) -> List[Row]:
    """Continuous feature table [quantity, price, hour, weekday] from a real CSV.

    Price adds continuity so distances are meaningful (not all-ties).
    """
    import csv
    from sdf.foundation.adapters.retail_csv import _parse_dt
    rows: List[Row] = []
    with open(path, newline="", encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            try:
                q = float(r.get("Quantity", 0)); p = float(r.get("Price", 0) or 0)
                if q <= 0 or p <= 0:
                    continue
                dt = _parse_dt(r.get("InvoiceDate", ""))
            except (ValueError, KeyError):
                continue
            rows.append((q, p, float(dt.hour), float(dt.weekday())))
            if len(rows) >= limit:
                break
    return rows


def bootstrap_synthesize(real: List[Row], n: int = None, jitter: float = 0.05,
                         seed: int = 7) -> List[Row]:
    """A minimal stdlib synthesizer: per-column bootstrap + Gaussian jitter.

    Stands in for a fitted generator so privacy can be measured with no heavy
    deps. ALGORITHM-HOOK: use SDV CTGAN/copula output rows instead.
    """
    if not real:
        return []
    rng = random.Random(seed)
    n = n or len(real)
    cols = list(zip(*real))
    stds = [statistics.pstdev(c) or 1.0 for c in cols]
    out: List[Row] = []
    for _ in range(n):
        out.append(tuple(rng.choice(cols[j]) + rng.gauss(0, jitter * stds[j])
                         for j in range(len(cols))))
    return out

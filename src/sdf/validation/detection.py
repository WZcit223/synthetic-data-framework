"""The detection test (checklist B4): how easily a classifier tells synthetic rows from real ones.

A gradient-boosted classifier learns to label rows real or synthetic; its
cross-validated area under the ROC curve (AUC) is the score. 0.5 means the rows
cannot be told apart, 1.0 means every row gives itself away. The columns that
give them away are ranked by permutation importance on the held-out folds. The
contract is ``docs/refactor/algorithms/interfaces.md`` §7.3.
ALGORITHM-HOOK[B4]: a stronger discriminator, scored on a real holdout set the
synthesizer never saw.
"""

from __future__ import annotations

import threading
from collections.abc import Sequence

import numpy as np

Row = Sequence[float]

MAX_ROWS = 3000  # per side: the test compares as many real rows as synthetic ones
MAX_FEATURES = 3  # the most telling columns reported
MODEL = "HistGradientBoostingClassifier"
# The classifier runs on one thread. On a few thousand rows that is faster than one per core (1.5 s against
# 2.4 s for 3,000 rows a side on 4 cores), and it does not collapse when another process holds a core: with
# one core busy, one thread per core took 11.6 s. The thread limit is process-wide, so one test runs at a time.
_FIT_LOCK = threading.Lock()


def verdict(auc: float) -> str:
    """Below 0.6 ``hard to distinguish``, 0.6 to 0.8 ``distinguishable``, above 0.8 ``easily distinguished``."""
    if auc < 0.6:
        return "hard to distinguish"
    return "distinguishable" if auc <= 0.8 else "easily distinguished"


def detection_report(
    real: Sequence[Row],
    synth: Sequence[Row],
    *,
    columns: Sequence[str] | None = None,
    folds: int = 5,
    seed: int = 7,
) -> dict:
    """The classifier's cross-validated AUC at telling ``synth`` from ``real``, the lowest and highest fold,
    and the ``columns`` that tell them apart most (by permutation importance); ``{"error": ...}`` when a side
    has fewer rows than ``folds``. The same inputs and ``seed`` give the same report."""
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.inspection import permutation_importance
    from sklearn.metrics import roc_auc_score
    from sklearn.model_selection import StratifiedKFold
    from threadpoolctl import threadpool_limits

    rng = np.random.default_rng(seed)
    n = min(len(real), len(synth), MAX_ROWS)
    if n < folds:
        return {"error": f"too few rows for {folds}-fold detection: {len(real)} real, {len(synth)} synthetic"}
    a = np.asarray(real, dtype=float)
    b = np.asarray(synth, dtype=float)
    if a.ndim != 2 or b.ndim != 2 or a.shape[1] != b.shape[1]:
        raise ValueError(f"real and synthetic rows must have the same columns, got {a.shape} and {b.shape}")
    names = list(columns) if columns is not None else [f"column {j + 1}" for j in range(a.shape[1])]
    if len(names) != a.shape[1]:
        raise ValueError(f"{len(names)} column names for {a.shape[1]} columns")
    a = a[np.sort(rng.choice(len(a), n, replace=False))]
    b = b[np.sort(rng.choice(len(b), n, replace=False))]
    x = np.vstack([a, b])
    y = np.r_[np.zeros(n), np.ones(n)]
    aucs, importance = [], np.zeros(x.shape[1])
    with _FIT_LOCK, threadpool_limits(limits=1, user_api="openmp"):
        for train, test in StratifiedKFold(folds, shuffle=True, random_state=seed).split(x, y):
            model = HistGradientBoostingClassifier(random_state=seed).fit(x[train], y[train])
            aucs.append(roc_auc_score(y[test], model.predict_proba(x[test])[:, 1]))
            importance += permutation_importance(
                model, x[test], y[test], scoring="roc_auc", n_repeats=5, random_state=seed
            ).importances_mean
    auc = float(np.mean(aucs))
    ranked = sorted(range(len(names)), key=lambda j: (-importance[j], j))
    return {
        "auc": round(auc, 4),
        "auc_low": round(float(min(aucs)), 4),
        "auc_high": round(float(max(aucs)), 4),
        "n_real": n,
        "n_synth": n,
        "model": f"{MODEL}, {folds}-fold",
        "top_features": [names[j] for j in ranked[:MAX_FEATURES] if importance[j] > 0],
        "verdict": verdict(auc),
    }


def detection_metrics(real: Sequence[Row], synth: Sequence[Row], *, columns: Sequence[str] | None = None) -> dict:
    """``detection_report`` as an evaluation's metrics: ``detection_auc``, ``detection_auc_low``,
    ``detection_auc_high``, ``detection_verdict`` and ``detection_top_features`` (comma-separated); all ``None``
    when there are too few rows, and ``detection_verdict`` then says why."""
    rep = detection_report(real, synth, columns=columns)
    if "error" in rep:
        return {
            "detection_auc": None,
            "detection_auc_low": None,
            "detection_auc_high": None,
            "detection_verdict": rep["error"],
            "detection_top_features": None,
        }
    return {
        "detection_auc": rep["auc"],
        "detection_auc_low": rep["auc_low"],
        "detection_auc_high": rep["auc_high"],
        "detection_verdict": rep["verdict"],
        "detection_top_features": ", ".join(rep["top_features"]),
    }

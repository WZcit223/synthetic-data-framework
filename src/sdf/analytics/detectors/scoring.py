"""Detectors scored on a frame with injected anomalies: precision and recall per kind, at two cuts.

``threshold`` keeps the detections a detector reports; ``top-k`` keeps the
``len(injected)`` SKU-days it rates highest, ties broken by SKU order and then day,
so a detector is not judged by its threshold alone. Per kind, precision counts only
the flagged points at an injected place of that kind or at no injected place. A
detector that fails is an error row, not a failed run. The contract is
``docs/refactor/algorithms/interfaces.md`` §6.3.
"""

from __future__ import annotations

import time
from collections.abc import Mapping, Sequence, Set
from datetime import date
from typing import Any

import numpy as np

from sdf.foundation.tables import DatasetInfo, Field, Table
from .core import SignalFrame
from .registry import DetectorRegistry, default_detectors

MAX_DETECTORS = 6
CUTS = ("threshold", "top-k")

SCORES_INFO = DatasetInfo(
    name="anomaly-scores",
    label="Anomaly scores",
    description="Each detector's precision and recall on injected anomalies, per kind, at its threshold and at the top-k",
    fields=(
        Field("detector", "Detector", "dimension"),
        Field("kind", "Anomaly kind", "dimension"),
        Field("cut", "Cut", "dimension"),
        Field("precision", "Precision", "measure", unit="share", aggregate="mean"),
        Field("recall", "Recall", "measure", unit="share", aggregate="mean"),
        Field("f1", "F1", "measure", unit="share", aggregate="mean"),
        Field("flagged", "Flagged", "measure", unit="rows", aggregate="sum"),
        Field("seconds", "Run time", "measure", unit="s", aggregate="sum"),
        Field("error", "Error", "dimension"),
    ),
)

Place = tuple[str, date]


def top_k(scores: np.ndarray, frame: SignalFrame, k: int) -> set[Place]:
    """The ``k`` SKU-days with the highest scores; ties go to the earlier SKU, then the earlier day."""
    n_skus, n_days = frame.shape
    sku = np.repeat(np.arange(n_skus), n_days)
    day = np.tile(np.arange(n_days), n_skus)
    order = np.lexsort((day, sku, -scores.ravel()))[:k]  # the last key sorts first
    return {(frame.sku_ids[sku[i]], frame.days[day[i]]) for i in order}


def _rows(detector: str, flagged: set[Place], injected: Set[tuple[str, date, str]], kinds: Sequence[str], cut: str):
    by_place = {(s, d): k for s, d, k in injected}
    false = {p for p in flagged if p not in by_place}
    rows = []
    for kind in (*kinds, "all"):
        places = set(by_place) if kind == "all" else {p for p, k in by_place.items() if k == kind}
        hit = flagged & places
        counted = len(flagged) if kind == "all" else len(hit) + len(false)
        precision = len(hit) / counted if counted else None
        recall = len(hit) / len(places) if places else None
        f1 = (
            2 * precision * recall / (precision + recall)
            if precision is not None and recall is not None and precision + recall > 0
            else (0.0 if precision is not None and recall is not None else None)
        )
        rows.append([detector, kind, cut, precision, recall, f1, counted, None, None])
    return rows


def score_detectors(
    detectors: Sequence[str],
    frame: SignalFrame,
    injected: Set[tuple[str, date, str]],
    *,
    params: Mapping[str, Mapping[str, Any]] | None = None,
    registry: DetectorRegistry | None = None,
) -> Table:
    """The ``anomaly-scores`` table of ``detectors`` on ``frame``, whose anomalies ``injected`` are
    ``(sku_id, day, kind)``; ``ValueError`` for an empty, too long or repeated list, or unknown parameters."""
    reg = registry if registry is not None else default_detectors()
    names = list(detectors)
    if not names:
        raise ValueError("choose at least one detector")
    if len(names) > MAX_DETECTORS:
        raise ValueError(f"at most {MAX_DETECTORS} detectors, got {len(names)}")
    if len(set(names)) != len(names):
        raise ValueError(f"each detector may appear once, got {names}")
    params = dict(params or {})
    for name in params:
        if name not in names:
            raise ValueError(f"parameters for {name}, which is not among the detectors {names}")
    models = {n: reg.create(n, **params.get(n, {})) for n in names}  # unknown names and bad parameters fail first
    kinds = list(dict.fromkeys(k for _, _, k in sorted(injected, key=lambda p: (p[1], p[0]))))
    rows = []
    for name in names:
        t0 = time.perf_counter()
        try:
            scores, detections = reg.run(models[name], frame)
        except Exception as exc:  # a failing detector is a row, not a failed run
            rows.append([name, "all", None, None, None, None, None, round(time.perf_counter() - t0, 3), str(exc)])
            continue
        seconds = round(time.perf_counter() - t0, 3)
        threshold = {(d.sku_id, d.day) for d in detections}
        ranked = top_k(scores, frame, len(injected))
        for cut, flagged in zip(CUTS, (threshold, ranked)):
            block = _rows(name, flagged, injected, kinds, cut)
            if cut == "threshold":
                block[-1][7] = seconds  # the run time once per detector: on its all-kinds threshold row
            rows += block
    return Table(SCORES_INFO, rows)

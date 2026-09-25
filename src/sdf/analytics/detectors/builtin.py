"""The built-in detectors: today's seasonal rule per SKU, and an isolation forest over every signal.

``seasonal-residual`` wraps ``sdf.analytics.anomaly.seasonal_residual_anomalies`` (its
answer, not a copy of it) on each SKU's demand. ``isolation-forest`` rates every
SKU-day from per-SKU scaled features of every signal in the frame, and from the
stock balance: the day's change in stock that demand and receipts do not explain,
which no single series shows. The contract is
``docs/refactor/algorithms/interfaces.md`` §6.2.
"""

from __future__ import annotations

from typing import ClassVar

import numpy as np

from sdf.analytics.anomaly import seasonal_residual_anomalies, seasonal_residual_z
from .core import Detection, DetectorInfo, SignalFrame

STRONG = 3.0  # a scaled feature at least this far out names its signal among a detection's reasons
MAX_SAMPLES = 8192  # SKU-days each tree of the forest draws: enough for a feature that is 0 almost everywhere
STOCK = ("on_hand", "receipts")  # read through the stock balance, not as series of their own


class SeasonalResidual:
    info: ClassVar[DetectorInfo] = DetectorInfo(
        "seasonal-residual",
        "Each SKU's demand against its median weekly profile: a robust z beyond k is an anomaly",
        signals=("demand",),
    )
    param_bounds: ClassVar[dict[str, tuple[float | None, float | None]]] = {"k": (2.0, 10.0), "period": (2, 28)}

    def __init__(self, k: float = 3.5, period: int = 7) -> None:
        self.k = k
        self.period = period

    def scores(self, frame: SignalFrame) -> np.ndarray:
        """The absolute robust z of every point; 0 for a SKU too short for the rule."""
        demand = np.nan_to_num(frame.signals["demand"])
        out = np.zeros(frame.shape)
        for i, row in enumerate(demand):
            measured = seasonal_residual_z([float(v) for v in row], self.period)
            if measured is not None:
                out[i] = np.abs(measured[0])
        return out

    def detect(self, frame: SignalFrame) -> list[Detection]:
        demand = np.nan_to_num(frame.signals["demand"])
        found = []
        for i, row in enumerate(demand):
            for a in seasonal_residual_anomalies([float(v) for v in row], self.period, self.k):
                found.append(
                    Detection(frame.sku_ids[i], frame.days[a["index"]], abs(a["robust_z"]), a["direction"], ("demand",))
                )
        return found


def _rolling_median(x: np.ndarray, window: int = 7) -> np.ndarray:
    """The centred rolling median of each row, the row's first and last values repeated beyond its ends."""
    half = window // 2
    padded = np.pad(x, ((0, 0), (half, half)), mode="edge")
    windows = np.lib.stride_tricks.sliding_window_view(padded, window, axis=1)
    return np.median(windows, axis=2)


def _weekday_median(x: np.ndarray, weekdays: np.ndarray) -> np.ndarray:
    """Each point's weekday median, per row."""
    out = np.zeros_like(x)
    for w in range(7):
        on = weekdays == w
        if on.any():
            out[:, on] = np.median(x[:, on], axis=1, keepdims=True)
    return out


class IsolationForestDetector:
    """scikit-learn's ``IsolationForest`` over every SKU-day, from per-SKU scaled features.

    Per signal: its value, its residual from the weekday median and from the centred
    7-day rolling median, and whether it is zero, scaled by the SKU's spread of that
    signal (at least one unit). With ``demand``, ``on_hand`` and ``receipts`` in the
    frame, the stock enters as the missing stock instead: today's stock minus
    yesterday's, minus receipts, plus demand, where it is below 0, in days of the SKU's
    mean demand (0 whenever stock is accounted for). The stock and receipts series
    themselves are a policy's restocking cycle, not a signal of anything amiss: as
    features of their own they only added false alarms. An unknown value (``nan``)
    counts as 0. Each tree draws up to ``MAX_SAMPLES`` SKU-days, so a feature that is 0
    almost everywhere still gets split on; the ``contamination`` share is reported.
    ALGORITHM-HOOK[C3]: an autoencoder over real multi-sensor history replaces the
    hand-made features.
    """

    info: ClassVar[DetectorInfo] = DetectorInfo(
        "isolation-forest",
        "An isolation forest over every signal of every SKU-day, the stock balance included",
        signals=("demand", "on_hand", "receipts"),
    )
    param_bounds: ClassVar[dict[str, tuple[float | None, float | None]]] = {
        "contamination": (0.001, 0.2),
        "seed": (0, None),
    }

    def __init__(self, contamination: float = 0.01, seed: int = 0) -> None:
        self.contamination = contamination
        self.seed = seed

    def _features(self, frame: SignalFrame) -> tuple[np.ndarray, dict[str, np.ndarray], np.ndarray]:
        """The feature matrix (SKU-days × features), each signal's strongest scaled feature per SKU-day, and
        the demand's weekday residual (for the direction)."""
        weekdays = np.array([d.weekday() for d in frame.days])
        columns, strength = [], {}
        spread = {}
        balance = {"demand", *STOCK} <= set(frame.signals)
        for name in sorted(frame.signals):
            if balance and name in STOCK:
                continue
            x = np.nan_to_num(np.asarray(frame.signals[name], dtype=float))
            s = np.maximum(x.std(axis=1, keepdims=True), 1.0)
            spread[name] = s
            parts = [
                (x - np.median(x, axis=1, keepdims=True)) / s,
                (x - _weekday_median(x, weekdays)) / s,
                (x - _rolling_median(x)) / s,
            ]
            columns += parts + [(x == 0).astype(float)]
            strength[name] = np.max(np.abs(np.stack(parts)), axis=0)
        if {"demand", "on_hand", "receipts"} <= set(frame.signals):
            on_hand = np.nan_to_num(frame.signals["on_hand"])
            change = np.diff(on_hand, axis=1, prepend=on_hand[:, :1])
            unexplained = change - np.nan_to_num(frame.signals["receipts"]) + np.nan_to_num(frame.signals["demand"])
            unexplained[:, 0] = 0.0
            # stock gone without demand or receipt to explain it, in days of the SKU's mean demand (a stock-out,
            # the positive part, is demand the stock could not serve: not missing stock)
            mean = np.maximum(np.nan_to_num(frame.signals["demand"]).mean(axis=1, keepdims=True), 1e-9)
            unexplained[np.abs(unexplained) < 1e-6] = 0.0  # rounding in the arithmetic, not missing stock
            missing = np.minimum(unexplained, 0.0) / mean
            columns.append(missing)
            strength["on_hand"] = np.abs(missing) * STRONG  # a day's mean demand gone missing, or more, is a reason
        demand = np.nan_to_num(frame.signals["demand"])
        direction = (demand - _weekday_median(demand, weekdays)) / spread["demand"]
        x = np.stack([c.ravel() for c in columns], axis=1)
        return x, strength, direction

    def _fit(self, frame: SignalFrame):
        """The forest's scores on ``frame`` (SKUs × days, larger is more anomalous), its cut-off, and the
        reasons and directions, kept for the frame: ``scores`` and ``detect`` of one frame fit once. A frame is
        never changed after it is built, so the same frame object always has the same answer."""
        from sklearn.ensemble import IsolationForest

        kept = getattr(self, "_kept", None)
        if kept is not None and kept[0] is frame:
            return kept[1]
        x, strength, direction = self._features(frame)
        forest = IsolationForest(
            n_estimators=200,
            max_samples=min(MAX_SAMPLES, len(x)),
            contamination=self.contamination,
            random_state=self.seed,
        ).fit(x)
        score = -forest.score_samples(x).reshape(frame.shape)
        # scikit-learn's predict() flags a sample whose score_samples is below offset_: the same cut, scored once
        self._kept = (frame, (score, -forest.offset_, strength, direction))
        return self._kept[1]

    def scores(self, frame: SignalFrame) -> np.ndarray:
        return self._fit(frame)[0].copy()

    def detect(self, frame: SignalFrame) -> list[Detection]:
        score, cut, strength, direction = self._fit(frame)
        flagged = score > cut
        found = []
        for i, t in zip(*np.nonzero(flagged)):
            reasons = tuple(n for n in sorted(strength) if strength[n][i, t] >= STRONG)
            if not reasons:
                reasons = (max(strength, key=lambda n: strength[n][i, t]),)
            if "demand" in reasons and direction[i, t] != 0:
                way = "spike" if direction[i, t] > 0 else "drop"
            else:
                way = "other"
            found.append(Detection(frame.sku_ids[i], frame.days[t], float(score[i, t]), way, reasons))
        return found

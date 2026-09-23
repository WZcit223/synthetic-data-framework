"""TSTR — Train on Synthetic, Test on Real (checklist B2), dependency-free.

The decisive question for synthetic data is not "does it look real?" but "can a
model trained on it perform on real data?" TSTR answers it:

  1. split a real reference series into train / test,
  2. fit the forecaster on the REAL train  -> weights w_real   (TRTR baseline),
  3. fit a synthesizer on the real train, generate synthetic, fit the forecaster
     on the SYNTHETIC series               -> weights w_synth  (TSTR),
  4. evaluate BOTH weight sets on the SAME real test window (identical real
     features), and compare error.

A TSTR/TRTR ratio near 1.0 means synthetic data is ~as useful as real for
training — the property that lets us build on synthetic data before real data
exists. ALGORITHM-HOOK: swap the synthesizer for SDV and the model for
DeepAR/TFT; this harness scores them unchanged.
"""

from __future__ import annotations

from collections.abc import Iterable

from sdf.analytics import metrics
from sdf.analytics.forecast import build_series
from sdf.analytics.models import fit_weights_with_rank, predict_at
from sdf.foundation.schema import OutboundOrder
from sdf.synthesis.api import SeriesData
from sdf.synthesis.registry import default_registry


def _mae(weights, series, period, start) -> float:
    preds = [predict_at(weights, i, period, series[i - 1], series[i - period]) for i in range(start, len(series))]
    return metrics.mae(series[start:], preds)


def tstr_report(
    orders: Iterable[OutboundOrder], test_frac: float = 0.3, *, synthesizer: str = "seasonal-profile"
) -> dict:
    """Run TSTR on a real order stream (auto daily/hourly granularity).

    ``synthesizer`` names a registered synthesizer that produces a series.
    """
    registry = default_registry()
    if registry.info(synthesizer).produces != "series":
        raise ValueError(f"{synthesizer} produces {registry.info(synthesizer).produces!r}; TSTR needs a series")
    series, freq, period = build_series(orders)
    n = len(series)
    split = max(2 * period + 2, int(n * (1 - test_frac)))
    if split >= n - 1:
        return {"error": "series too short for a TSTR split", "series_len": n, "granularity": freq}

    real_train = series[:split]

    # TRTR — train the forecaster on the REAL train window.
    w_real, real_rank_deficient = fit_weights_with_rank(real_train, period)

    # TSTR — fit the synthesizer on the SAME real train (same granularity),
    # generate a synthetic series of equal length, train the forecaster on it.
    synth = registry.create(synthesizer).fit(SeriesData(values=real_train, period=period))
    synth_series = synth.sample(max(len(real_train), 2 * period + 2))
    w_synth, synth_rank_deficient = fit_weights_with_rank(synth_series, period)

    trtr = _mae(w_real, series, period, split)
    tstr = _mae(w_synth, series, period, split)
    return {
        "granularity": freq,
        "seasonal_period": period,
        "series_len": n,
        "train_len": split,
        "test_len": n - split,
        "TRTR_mae": round(trtr, 3),
        "TSTR_mae": round(tstr, 3),
        "ratio_tstr_over_trtr": round(tstr / trtr, 3) if trtr else None,
        "rank_deficient": {"trtr": real_rank_deficient, "tstr": synth_rank_deficient},
    }

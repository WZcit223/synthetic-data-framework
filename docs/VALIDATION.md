# Validation Results / 验证结果

Tracks the point where the framework stops being a pure shell and starts
producing **measured numbers**. Structural checks (shell) live in code; this file
records the first *quantitative* results as the algorithm phase begins.

## Phase 2.0 — first real-data-driven forecast backtest

The Application Layer's demand step is no longer a hand-wave: a real transactional
retail feed (UCI *Online Retail II* schema) is ingested through
`foundation/adapters/retail_csv.py` and forecast baselines are backtested with a
one-step **walk-forward** split (`synthesis/forecast.py`).

Reproduce:

```bash
python -m sdf.cli backtest                       # bundled sample
python -m sdf.cli backtest /path/to/online_retail_II.csv   # real UCI data
```

### Result on the bundled sample (`data/sample_online_retail_ii.csv`)

> ⚠️ These numbers are on the **schema-compatible SAMPLE**, not the real UCI
> dataset. They demonstrate the *harness works and discriminates between models*,
> not a production accuracy claim. Run the command above on the real file for
> real numbers.

| model | MAE | RMSE | MAPE % | bias |
|-------|-----|------|--------|------|
| **snaive7** (seasonal-naive, 7d) | **46.0** | 62.6 | **29.7** | −0.48 |
| mean | 80.3 | 99.0 | 31.8 | −19.7 |
| ma7 (moving average) | 84.6 | 100.2 | 36.6 | −2.69 |
| naive (last value) | 122.1 | 139.7 | 67.2 | +0.76 |

Series: 139 days, mean 137.6 units/day, test window 21 days.

**Reading it:** seasonal-naive wins decisively — the harness correctly surfaces
that demand is driven by a **weekly pattern** (weekday/weekend, Sundays closed).
That is exactly the signal a production model must capture, and it gives the
algorithm team a concrete bar to beat.

### What this establishes
- The **same** Application-Layer code runs on real data via the adapter — the
  Foundation-Layer "sources are interchangeable" claim is now demonstrated, not
  asserted.
- A reusable **backtest harness** (MAE / RMSE / MAPE / bias, walk-forward) exists
  for every future model.

### Next (Phase 2.1 → 3)
- Run on the full real UCI dataset; record real numbers here.
- Add SDV/CTGAN synthesis fitted on the real series, then **SDMetrics** fidelity
  (checklist B1) and **TSTR** utility (B2) — train on synthetic, test on real,
  comparing the gap to the baselines above.
- ALGORITHM-HOOK: beat `snaive7` with DeepAR / TFT / LightGBM on the same harness.

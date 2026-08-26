# Validation Results / 验证结果

Tracks the point where the framework stops being a pure shell and starts
producing **measured numbers**. Structural checks (shell) live in code; this file
records the first *quantitative* results as the algorithm phase begins.

## Phase 2.0 — first real-data-driven forecast backtest

The Application Layer's demand step is no longer a hand-wave: a real transactional
retail feed (UCI *Online Retail II* schema) is ingested through
`foundation/adapters/retail_csv.py` and forecast baselines are backtested with a
one-step **walk-forward** split (`synthesis/forecast.py`).

The harness auto-selects the finest granularity the data can support (daily when
≥14 days, otherwise hourly), and matches the seasonal period to it.

Reproduce:

```bash
python -m sdf.cli backtest                                   # bundled synthetic sample (daily)
python -m sdf.cli backtest data/online_retail_ii_2010_10k.csv  # real UCI extract (hourly)
```

### A. Real UCI data — `data/online_retail_ii_2010_10k.csv` (10k rows)

Real *Online Retail II* extract. **Coverage caveat:** these 10k rows span only
**4 days** (2010-12-01 → 05), so a daily/weekly model is not yet possible — the
harness falls back to **hourly** granularity (intraday seasonality).

| model | MAE | RMSE | MAPE % | bias |
|-------|-----|------|--------|------|
| **naive** (last hour) | **951** | 1328 | 99.0 | +51 |
| ma11 (11h moving avg) | 1381 | 1497 | 64.3 | +267 |
| snaive11 (same hour, prev day) | 1489 | 1873 | 79.7 | +674 |
| mean | 1535 | 1661 | 79.8 | +912 |

Series: 44 business-hour buckets, mean 2049 units/hour, 2015 SKUs, 10k orders.

**Reading it:** on a 4-day slice, **persistence (naive) wins** and no baseline is
strong (MAPE ~99%) — hourly retail demand is volatile and 4 days is too little to
learn seasonality. This is the honest signal that we need the **full ~2-year
dataset** to fit a real daily/weekly model. The pipeline, however, ingests real
data end-to-end and produces measured numbers — that part is proven.

### B. Synthetic sample — `data/sample_online_retail_ii.csv` (daily)

> Schema-compatible SAMPLE (not real UCI). It has the 120-day span the real
> extract lacks, so it exercises the **daily/weekly** path.

| model | MAE | RMSE | MAPE % | bias |
|-------|-----|------|--------|------|
| **snaive7** (seasonal-naive, 7d) | **32.8** | 44.9 | **20.6** | −0.93 |
| mean | 81.2 | 101.2 | 33.0 | −18.5 |
| ma7 (moving average) | 84.4 | 99.6 | 38.2 | +2.71 |
| naive (last value) | 130.3 | 148.2 | 69.0 | +3.29 |

Series: 139 days, mean 137.6 units/day, test window 14 days.

**Reading it:** with enough history, seasonal-naive wins decisively — the harness
correctly surfaces a **weekly pattern**. That is the bar a production model beats,
and what we expect to reproduce once the full real dataset is loaded.

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

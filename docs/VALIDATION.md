# Validation Results / 验证结果

Tracks the point where the framework stops being a pure framework and starts
producing **measured numbers**. Structural checks (framework) live in code; this file
records the first *quantitative* results as the algorithm phase begins.

## Headline — full 13-month real dataset (2009-12 → 2010-12)

The complete UCI *Online Retail II* 2009–2010 data (**525,460 orders, 4,631 SKUs,
374 daily points**) was run through every stage. This is the production-scale
result; the small-extract sections below are kept as honest history.

| stage | metric | result |
|-------|--------|--------|
| Forecast backtest (C1) | best model MAE / MAPE | **seas_linear7 3924 / 13.5 %** — beats seasonal-naive (5305 / 21.3 %) by **26 %** |
| Fidelity, baseline (B1) | KS / profile-corr / score | 0.10 / 0.98 / **87.9 / 100** |
| Fidelity, Gaussian copula (B1) | SDMetrics overall | **0.9235** |
| Utility, TSTR (B2) | TSTR/TRTR ratio | **1.035** (synthetic ≈ real for training) |

**On adequate real data the Phase 3 model wins** (26 % better than the best
baseline — the trend+holiday structure it exploits is present at full scale),
**fidelity rises** with more data (87.9 vs 78 on the 4-day extract; copula 0.92),
and **TSTR ≈ 1.0** confirms synthetic data is as useful as real for training.
Reproduce with any of the CLI commands below pointed at the full CSV.

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

## Phase 2.1 — fitted synthesis + fidelity (checklist B1)

A generator is now **fitted on the real data** (`synthesis/fit.py`) — it learns the
intraday demand profile and residual pool and samples a synthetic series that
reproduces the real shape. Fidelity is scored dependency-free
(`synthesis/fidelity.py`).

Reproduce:
```bash
python -m sdf.cli synth data/online_retail_ii_2010_10k.csv
```

Result on the real 10k extract:

| metric | value | meaning |
|--------|-------|---------|
| KS statistic | **0.136** | 0 = identical distribution |
| profile correlation | **0.904** | 1 = identical intraday seasonality |
| mean delta | −5.0 % | synthetic vs real average |
| std delta | −14.5 % | synthetic slightly under-disperses |
| **fidelity score** | **78 / 100** | (1−KS)·profile_corr |

**Reading it:** the fitted synthesizer captures the **seasonality strongly (0.90)**
and the demand distribution reasonably (KS 0.16), under-dispersing a little — a
credible first B1 number with clear headroom. That headroom is exactly what a
learned model closes.

### Phase 2.1 (full) — Gaussian copula + real SDMetrics

Upgraded from the dependency-free baseline to a real **Gaussian-copula** synthesizer
(the engine behind SDV's `GaussianCopulaSynthesizer`) scored by real **SDMetrics**,
on the transaction-line table `[Quantity, Price, hour, weekday]`.

```bash
pip install copulas sdmetrics pandas numpy
python -m sdf.cli sdv data/online_retail_ii_2010_10k.csv
```

| SDMetrics dimension | score (1.0 = identical) |
|---------------------|-------------------------|
| column shapes (KSComplement, mean) | 0.851 |
| pair trends (CorrelationSimilarity, mean) | 0.981 |
| **overall quality** | **0.916** |

Per-column KSComplement: Quantity 0.78, Price 0.90, hour 0.90, weekday 0.83.
Pair-trend: Quantity~Price 0.95, Quantity~hour 1.00, Price~weekday 0.99.

**Reading it:** the copula reproduces the real **joint** distribution well —
**0.92 overall**, up from the 78/100 baseline — capturing cross-column correlations
(price/quantity/time) the marginal bootstrap could not. This is a production-grade
B1 number. (Note: 0.92 and 0.78 score different representations — the tabular
line-item joint vs the hourly demand series — so they are complementary, not a
strict apples-to-apples delta.)

> ALGORITHM-HOOK: swap GaussianCopula for **CTGAN/TVAE** (adds torch) for complex
> distributions; add privacy (DCR) and detection-AUC (B3–B4). Same SDMetrics harness.

## Phase 3 — real forecasting model + TSTR utility (checklist B2, C1)

### C1 — a real model (AR + seasonal OLS)

`synthesis/models.py` adds `seasonal_linear`: an autoregressive + seasonal
least-squares forecaster (trend + cycle dummies + lag-1 + lag-period), solved with
pure-Python normal equations. It plugs into the same backtest harness.

**Capability check** (controlled series, so the result is unambiguous):

| series | seasonal_linear MAE | snaive MAE | winner |
|--------|--------------------|-----------|--------|
| trend + weekly season, low noise | **0.0** | 5.6 | model (captures trend) |
| pure weekly season, high noise | **24.6** | 29.6 | model (averages noise) |

> **Honest note on our two datasets:** the model does *not* win on either the
> synthetic sample (near-pure weekly structure → seasonal-naive is already
> near-optimal) or the 4-day real extract (too short — the model overfits). Both
> outcomes are expected and both point to the same conclusion: showcasing a
> learned model needs the **full ~2-year real dataset**, which has the trend and
> holiday structure the model exploits. The model and harness are ready for it.

### C2 — (s, S) inventory optimisation

`application/warehouse_demo.py` adds a classic (s, S) policy: safety stock sized
from each SKU's demand variability and a target service level
(`s = μ·(L+R) + z·σ·√(L+R)`). Live in the dashboard with a service-level selector.

| service level | z | SKUs needing an order | total safety stock (units) |
|---------------|---|-----------------------|----------------------------|
| 90 % | 1.28 | 33 | 2 626 |
| 95 % | 1.64 | 38 | 3 369 |
| 99 % | 2.33 | 43 | 4 764 |

**Reading it:** the classic service/inventory tradeoff, quantified — raising the
service level from 90→99 % lifts required safety stock ~81 %. ALGORITHM-HOOK: a
cost-based newsvendor with a fitted lead-time-demand distribution replaces the
normal approximation.

### B2 — TSTR: train on synthetic, test on real

The decisive test for synthetic data: fit the forecaster on synthetic data, then
measure it on **real** held-out data, vs the same model trained on real data.
A ratio near **1.0** means synthetic data is as useful as real for training.

```bash
python -m sdf.cli tstr                                   # synthetic sample (daily)
python -m sdf.cli tstr data/online_retail_ii_2010_10k.csv  # real extract (hourly)
```

| reference | TRTR MAE (real-trained) | TSTR MAE (synthetic-trained) | **ratio** |
|-----------|-------------------------|------------------------------|-----------|
| synthetic sample (daily) | 53.6 | 48.5 | **0.905** |
| real UCI extract (hourly) | 2629 | 2635 | **1.002** |

**Reading it:** on both, the synthetic-trained model matches the real-trained one
(**ratio ≈ 0.9–1.0**). This is the framework's core claim — *build on synthetic
data before real data exists* — now **measured**. (Absolute MAEs are high on these
small/short series; the meaningful quantity is the ratio, which is robust to that.)

## Phase 3/4 — anomaly detection (C3) + knowledge Q&A (C6)

**C3 — demand anomaly detection** (`synthesis/anomaly.py`): seasonal-residual +
robust-z (MAD-scaled) flags demand spikes/drops resistant to the outliers it
hunts. On the demo world it recovers the injected shock days (e.g. a spike of
~2400 vs an expected ~740, robust-z ≫ 3.5). Live in the dashboard.
ALGORITHM-HOOK: Isolation Forest / autoencoder over multivariate state.

**C6 — grounded knowledge Q&A** (`application/knowledge.py`): a natural-language
interface that routes questions to computed facts and answers with real numbers —
stockouts, (s,S) safety stock, forecast accuracy, anomalies, vision stocktake,
ABC, inventory value. Every answer is backed by data, nothing invented. Live in
the dashboard ("Ask the warehouse"). ALGORITHM-HOOK: LLM over a knowledge graph,
same "answers grounded in computed facts" contract.

## What this establishes
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

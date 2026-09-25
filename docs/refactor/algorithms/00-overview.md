# Algorithm phase — overview

Status: proposed on 2026-09-24, approved by the project lead on 2026-09-25
with the recommended decisions: D1 (a), and D2 and D3 left out of this
sequence. PR 1 merged on 2026-09-25 (#38). The sequence then pauses, at the
project lead's request, for the frontend refactor
([`../frontend/00-overview.md`](../frontend/00-overview.md)), and resumes with
PR 2; PR 6 (the pages) is written on the new frontend. On 2026-09-24 the project lead asked for four
items, in this order: synthesizer choice from the UI (item 1) and the pivot
table (item 3) first, then causal modelling (item 2) and the algorithm phase
(item 4). Items 1 to 3 are done (the exploration sequence, #26 to #30, and the
causal sequence, #31 to #36). This sequence is item 4. It replaces the
stand-in algorithms marked in the code (`ALGORITHM-HOOK`) with real ones, one
capability at a time: demand forecasting, replenishment, anomaly detection,
and the quality checks on synthetic data. Each one is measured against the
stand-in it replaces.

The interface contract every PR follows is [`interfaces.md`](interfaces.md).

## Why

The framework shows the full flow, but the numbers in its middle come from
stand-ins:

- **The forecast is a point, and on a SKU it is a trailing mean.** The
  backtest (`/api/v1/backtest`) compares five one-step models on the total
  demand of the world. It says nothing about single SKUs, where replenishment
  decides, and nothing about uncertainty. The SKU chart on the dashboard
  draws a 14-day average (`demand_series`, `ALGORITHM-HOOK[C1]`).
- **Replenishment sizes the reorder point with a normal approximation and
  ignores the order size.** `ServiceLevelPolicy` sets the order-up-to level
  equal to the reorder point, so it orders almost every review. The simulated
  cost is measured on the same history the levels were fitted on.
- **Anomaly detection is one univariate rule** with no measure of how often it
  is right.
- **Synthetic tables are scored on fidelity, usefulness and privacy, not on
  whether they can be told apart from the real rows** (checklist B4, no code
  yet).

A synthetic data framework can measure all of this honestly, for the same
reason it could in the causal sequence: where it generates the data, it knows
the answer. Where the answer is known, each algorithm is scored against it.
Where it is not, the algorithm is scored out of sample against the stand-in.

## What the spikes showed

Short scripts on the default world (`GenerationSpec()`, 200 SKUs × 90 days) and
on a declared demand process, before any design was fixed. Each implementing
PR re-measures its own numbers.

1. **A gradient-boosted forecaster is close to the best possible, and the
   stand-ins are not.** On a declared demand process (200 SKUs × 365 days,
   weekday profile, trend, promotions, intermittent SKUs, negative binomial
   noise), one-step forecasts over the last 28 days:

   | Forecast | WAPE % | Pinball loss (10/50/90 %) |
   |---|---|---|
   | The true mean, knowing the promotion days (an oracle, for comparison only) | 83.5 | 2.61 |
   | Gradient boosting, one model over all SKUs | 84.5 | 2.70 |
   | 28-day moving average | 86.8 | |
   | Seasonal naive (same weekday last week) | 107.6 | |

   Most of the error on low-volume SKUs is noise no method removes; the
   benchmark says how much. In the spike both the oracle and the forecaster
   were told the promotion days. In the contract promotions are unannounced
   (contract §3), so the reference is the `true-distribution` row without that
   knowledge; PR 1 reports it and PR 2's targets are set against it, not
   against this spike's oracle. On the default world's SKUs the same forecaster
   gives WAPE 60.6 % against 80.6 % for seasonal naive.
2. **Interval coverage needs two numbers on count data.** Demand comes in
   whole units, so outcomes often sit exactly on an interval's bound. The
   true distribution's own 80 % interval covers 89.7 % of the benchmark's
   outcomes with the bounds included and 47.9 % with them excluded; the
   gradient-boosted forecaster gives 89.8 % and 53.4 %. A calibrated
   forecaster has the nominal level between the two, so both are reported
   (contract §2.3).
3. **In replenishment the saving is in the order size, not the reorder
   point.** Fitting on the first 60 days of the default world and replaying
   the last 30:

   | Policy | Total simulated cost | Holding | Ordering | Lost margin | Fill rate |
   |---|---|---|---|---|---|
   | No safety stock | 357,198 | 15,170 | 13,425 | 328,603 | 90.3 % |
   | Service level 95 % (today) | 119,736 | 40,401 | 78,000 | 1,335 | 99.97 % |
   | Service level 95 % + economic order quantity | **66,146** | 56,571 | 9,200 | 374 | 99.99 % |
   | Cost-based reorder point (critical ratio), no lot size | 127,777 | 49,752 | 78,025 | 0 | 100 % |
   | Both levels searched per SKU on the replayed cost of the first 60 days | **60,370** | 36,238 | 9,850 | 14,281 | 99.67 % |

   Adding a lot size cuts the simulated cost by 45 %. A reorder point from the
   textbook cost ratio alone costs more: margins in the default world are far
   above holding costs (critical ratios 0.965 to 0.996), so it only adds stock.
   Searching both levels per SKU, on the cost of replaying the fitting window,
   cuts it by 50 % and takes 0.4 s for 200 SKUs. The policy must therefore see
   each SKU's costs and history, and choose both levels.
4. **Isolation Forest is not better on one series.** With 400 anomalies
   injected into the default world's SKU series:

   | Detector | Precision | Recall | Flagged |
   |---|---|---|---|
   | Seasonal residual + robust z (today) | 0.28 | 0.72 | 1,019 |
   | Isolation Forest, same number flagged | 0.21 | 0.53 | 1,019 |

   The existing rule stays the default for one series. Isolation Forest's
   place is the combined state (demand, stock, receipts), where a single-series
   rule cannot see an anomaly, such as stock falling with no demand.
5. **Synthetic tables are trivially recognisable.** A classifier trained to
   tell real rows from synthetic ones (checklist B4; 0.5 is ideal):

   | Source | Synthesizer | Detection AUC | After rounding integer columns |
   |---|---|---|---|
   | `sample_online_retail_ii.csv` | bootstrap-table | 1.00 | 0.98 |
   | `sample_online_retail_ii.csv` | gaussian-copula | 1.00 | 0.99 |
   | `online_retail_ii_2010_10k.csv` | bootstrap-table | 1.00 | 0.68 |
   | `online_retail_ii_2010_10k.csv` | gaussian-copula | 0.96 | 0.67 |

   Both synthesizers write hours, weekdays and quantities as decimals. On the
   sample, the prices are also a short list of catalogue values that no
   continuous synthesizer reproduces. The existing fidelity and privacy
   scores did not show either problem.

## Decisions

1. **Every algorithm is a plug-in, scored by one harness.** Forecasters
   (`sdf.forecasters`) and anomaly detectors (`sdf.detectors`) are new
   entry-point groups on the shared loader (`sdf.foundation.plugins`), like
   synthesizers and estimators. A replacement algorithm is a plug-in scored
   on the same rows as the stand-in. It becomes the default only where it
   wins, and the numbers go in `docs/VALIDATION.md`.
2. **Forecasts are probabilistic.** A forecaster returns quantiles for every
   SKU and horizon, not one number. The built-in point models get intervals
   from their own past errors (empirical residual quantiles), so every
   forecaster is scored the same way: WAPE, bias, pinball loss, interval
   coverage and width, and the ratio to seasonal naive.
3. **Benchmarks with a known answer, next to real rows.** A demand benchmark
   declares its process, so the true mean and quantiles are exact. An anomaly
   benchmark injects anomalies at known places. Each is the place where "how
   good is this algorithm" has an exact answer; the world's own rows and the
   real extract show that the result holds outside it.
4. **Scored out of sample.** Forecasts are backtested from rolling origins.
   Replenishment policies are fitted on the first part of the history and
   replayed on the rest. The existing in-sample numbers stay as they are, so
   nothing recorded changes.
5. **The core stays light.** Gradient boosting uses scikit-learn's
   histogram-based model, already a core dependency. LightGBM comes as an
   optional plug-in of the existing `app` extra, listed as unavailable with
   the reason when it is not installed. Deep models (DeepAR, Temporal Fusion
   Transformer, CTGAN) are not in this sequence (decision D3).
6. **Nothing recorded changes, with one stated exception.** `sdf demo`,
   `/api/v1/backtest` and every number in `docs/VALIDATION.md` stay as they
   are, and new numbers go in new sections. The exception is PR 5: declaring
   column kinds changes the built-in synthesizers' rows, so the table privacy
   numbers they are measured on are re-recorded, old and new side by side.

## Decisions for the project lead

These change the scope; the sequence below does not wait for them, except
PR 7.

**Decided on 2026-09-25:** D1 (a), the compact daily table is committed; D2
and D3 are not in this sequence. PR 7 therefore runs once the project lead
provides the dataset file.

- **D1. Real data at full size.** The only real rows in the repository are the
  5-day extract `data/online_retail_ii_2010_10k.csv`;
  `sample_online_retail_ii.csv` is a synthetic file in the same layout. The
  UCI Online Retail II dataset (two years, CC BY 4.0) cannot be downloaded
  from this environment (the host is blocked). Options:
  - **(a, recommended)** You download the dataset once and add it to the
    session (or to a branch). PR 7 adds `sdf prepare-retail`, which turns it
    into a compact daily table (the 200 SKUs with most demand × about 740
    days, well under 1 MB), and commits that table with its attribution. CI
    then validates every algorithm on two years of real demand.
  - (b) The same command, but the table is not committed. The real-data
    numbers are then measured by whoever has the file, and CI checks only
    the benchmarks and the extract.
  - (c) No full dataset. Validation stays on the benchmarks, the world and the
    5-day extract.
- **D2. A large language model for questions and the agent** (checklist C6,
  C7). The interfaces are already there: `Planner` for the agent and
  `KnowledgeQA` for questions, both grounded in computed facts. What is
  missing is a decision on the provider, the API key and which data may be
  sent to it. This sequence does not include it; with a decision, it becomes
  its own short plan.
- **D3. Deep models** (DeepAR, Temporal Fusion Transformer, CTGAN/TVAE). They
  need torch and are only worth it on the full dataset (D1). This sequence
  leaves them out; the forecaster and synthesizer plug-in points take them
  later without a change.
- Not planned, for lack of data: slotting (C4, needs pick paths and location
  geometry) and vision (C5, needs labelled shelf images).

## Sequence

Each PR passes the full gate (review, fixes, squash merge) before the next one
starts.

| # | Plan | Outcome | Version |
|---|---|---|---|
| 1 | [`01-forecasters.md`](01-forecasters.md) | Forecaster plug-ins (`sdf.forecasters`), the built-in models with intervals, a rolling-origin probabilistic backtest, the demand benchmark, `GET /api/v1/forecasters`, `POST /api/v1/forecasts/backtest`, `sdf forecast` | MINOR 1.8.0 → 1.9.0 |
| 2 | [`02-boosted-forecaster.md`](02-boosted-forecaster.md) | `gradient-boosting` (one model over all SKUs, quantile loss), optional `lightgbm`; the SKU forecast on the dashboard gets its interval | MINOR 1.9.0 → 1.10.0 |
| 3 | [`03-replenishment.md`](03-replenishment.md) | `CostBasedPolicy`: both levels chosen per SKU on the replayed cost of its history; out-of-sample replay | MINOR 1.10.0 → 1.11.0 |
| 4 | [`04-anomaly-detectors.md`](04-anomaly-detectors.md) | Detector plug-ins (`sdf.detectors`), the anomaly benchmark (precision, recall), `isolation-forest` over the combined state | MINOR 1.11.0 → 1.12.0 |
| 5 | [`05-synthesis-checks.md`](05-synthesis-checks.md) | The detection test (B4) in every synthesizer evaluation; column kinds in `TableData`, kept by the built-in table synthesizers | MINOR 1.12.0 → 1.13.0 |
| 6 | [`06-pages.md`](06-pages.md) | A Forecasts page (forecasters against the benchmark and the world), detectors on the dashboard, detection AUC on the synthesizer page | none (UI and documentation) |
| 7 | [`07-real-data.md`](07-real-data.md) | Only with D1 (a) or (b): `sdf prepare-retail` and every algorithm of PR 1 to 5 validated on two years of real demand | MINOR 1.13.0 → 1.14.0 |

## Non-goals

- **No deep models and no language model** (D2, D3).
- **No change to the warehouse generator or any recorded number**, except
  PR 5's table privacy numbers (Decision 6).
- **No new core dependency.** LightGBM stays in the `app` extra.
- **No automatic model selection in production paths.** A forecaster or
  detector becomes a default only through a reviewed PR that records the
  numbers that justify it.
- **No hierarchical reconciliation** (SKU forecasts summing to the total). The
  total's backtest stays as it is.

## Version

Planned per PR in the sequence table. The plan PR itself:
`Version: none, documentation and plans only`.

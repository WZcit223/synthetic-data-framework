# Causal modelling — overview

Status: proposed on 2026-09-24. On 2026-09-24 the project lead asked for four
items, in this order: synthesizer choice from the UI (item 1) and the pivot
table (item 3) first, then causal modelling (item 2) and the algorithm phase
(item 4). Items 1 and 3 are done (the exploration sequence, #26 to #30). This
sequence is item 2: causal inference in the simulation layer, to answer "what
happens if we take this action". The algorithm phase follows as its own
sequence.

The interface contract every PR follows is [`interfaces.md`](interfaces.md).

## Why

The simulation layer can already apply an intervention to a world and measure
outcomes under a policy (`Experiment`, `POST /api/v1/experiments`), but it
cannot yet answer a causal question well:

- **No uncertainty.** An experiment runs each intervention once, on one seed.
  A 3 % change in fill rate may be the intervention or may be the one draw, and
  nothing says which.
- **No effect.** The rows hold each arm's level; the difference to the baseline,
  with its interval, is left to the reader.
- **Only the simulator can answer.** With real data there is no simulator to
  rerun: the question must be answered from observational rows, where the
  treated units differ from the untreated ones before any treatment. Nothing in
  the framework estimates an effect from such rows, or shows how wrong a naive
  comparison is.

A synthetic data framework is in the right position for the third point: it
knows the true effect, because it generated the data. It can therefore show
which estimation method recovers the truth, and by how much the others miss.

## Decisions

1. **The simulator's answer is the ground truth, with replicates.** An effect
   study runs the baseline and each intervention on R replicate worlds. Every
   arm of one replicate shares that replicate's seed (common random numbers), so
   the effect of an intervention is the mean of R paired differences, with a
   Student-t interval. This is the effect of `do(intervention)` on the
   simulated warehouse; no model of the data is needed to compute it.
   *Alternative rejected:* bootstrap over the SKUs of one world. It measures
   the spread across SKUs, not across plausible worlds, and understates the
   uncertainty of a world-level metric such as fill rate.
2. **Estimating from observational rows is a plug-in point, like synthesizers.**
   An estimator takes a table, a treatment, an outcome and an adjustment set
   (declared by the user; the framework does not discover causal structure) and
   returns an average treatment effect with its interval. The built-ins are:
   - `difference-in-means`, the naive comparison, kept on purpose as the
     reference that shows the bias;
   - `regression-adjustment`, least squares with heteroscedasticity-robust
     errors;
   - `ipw`, inverse propensity weighting with a logistic propensity model.

   These use numpy, scipy and scikit-learn only, the core dependencies. DoWhy
   and EconML come as plug-ins of the existing `causal` extra, listed as
   unavailable with the reason when it is not installed, like `gaussian-copula`
   without `synthesis`. Estimators are declared in a new `sdf.estimators`
   entry-point group.
3. **A benchmark with a known answer.** A semi-synthetic benchmark takes the
   world's SKUs as units, with their real covariates (ABC class, price, mean
   daily demand), and adds a declared mechanism on top: a promotion whose
   assignment favours high-demand SKUs (the confounding strength is a
   parameter), and weekly units with a declared uplift. Both potential outcomes
   are generated for every SKU, so the true effect is exact. Every estimator is
   scored against it: the estimate, its interval, the truth, the bias, and
   whether the interval covers the truth. A spike on the default world, with
   uplift 30 % and 50 draws, gives this:

   | Confounding | Truth | Naive difference | Regression adjustment | Propensity weighting |
   |---|---|---|---|---|
   | none | 7.2 | 6.5 | 7.3 | 7.4 |
   | 1 | 7.2 | 38.1 | 7.7 | 8.1 |
   | 2 | 7.2 | 52.1 | 6.4 | 11.5 |

   The naive difference is up to seven times the truth. Both adjusted
   estimators recover the truth, and propensity weighting degrades as overlap
   thins. This is the lesson the benchmark is for. The implementing PR records
   its own numbers from its tests.
4. **Every result is a table.** Effects, replicate rows and benchmark scores are
   `{fields, rows}` tables (the exploration contract,
   [`../explore/interfaces.md`](../explore/interfaces.md) §1), so the Explore
   page pivots them with no change. The new page draws what a table cannot:
   estimates with their intervals.
5. **One plug-in loader.** Synthesizers and datasets each carry a copy of the
   entry-point loading (origin, unavailable reasons, name checks). Estimators
   would be the third copy, so the loader moves to the foundation first, in a
   PR that changes no behaviour.

## Sequence

Each PR passes the full gate (review, fixes, squash merge) before the next one
starts.

| # | Plan | Outcome | Version |
|---|---|---|---|
| 1 | [`01-effect-study.md`](01-effect-study.md) | `EffectStudy`: replicated interventions with paired effects and intervals; `POST /api/v1/effects`; `sdf effects` | MINOR 1.5.0 → 1.6.0 |
| 2 | [`02-effects-page.md`](02-effects-page.md) | The Effects page: choose, run, and read effects with their intervals; open them in Explore | none (UI only) |
| 3 | [`03-plugin-loader.md`](03-plugin-loader.md) | One entry-point loader in `sdf.foundation.plugins`, used by synthesizers and datasets | PATCH 1.6.0 → 1.6.1 |
| 4 | [`04-estimators-and-benchmark.md`](04-estimators-and-benchmark.md) | Estimator plug-ins (`sdf.estimators`), the promotion benchmark, `GET /api/v1/estimators`, `POST /api/v1/causal/estimates`, `sdf estimate` | MINOR 1.6.1 → 1.7.0 |
| 5 | [`05-estimation-page.md`](05-estimation-page.md) | The Effects page's estimation view (estimators against the truth), and estimators in the plug-in guide | none (UI and documentation) |

## Non-goals

- **No causal discovery.** The adjustment set is the user's claim, stated in the
  question; the framework does not learn a graph from data.
- **No change to the warehouse generator or any recorded number.**
  `docs/VALIDATION.md` and `sdf demo` stay as they are. The benchmark's
  mechanism lives in the benchmark, not in the generator.
- **No new heavy dependency in the core.** DoWhy and EconML stay in the `causal`
  extra; the built-in estimators use numpy, scipy and scikit-learn.
- **No time-series causal methods** (difference in differences, synthetic
  control, interrupted time series). They need a dated panel with a
  treatment start, which the benchmark does not have yet. The estimator
  protocol does not rule them out; they can come as plug-ins.
- **No real-data effect claims.** The framework shows how to estimate and how
  wrong each method is on data with a known answer; it does not claim an effect
  on the sample datasets.

## Version

Planned per PR in the sequence table. The plan PR itself:
`Version: none, documentation and plans only`.

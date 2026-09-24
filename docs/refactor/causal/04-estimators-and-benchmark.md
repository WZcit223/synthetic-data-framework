# PR 4 — Estimator plug-ins and a benchmark with a known answer

> Status: planned (causal modelling sequence PR 4).

Contract: [`interfaces.md`](interfaces.md) §3.

## Goal

The framework estimates an average treatment effect from observational rows,
with any mounted estimator, and shows how far each estimator is from the truth
on data where the truth is known.

## Scope

- **New `sdf.analytics.causal`**, holding:
  - the question and estimate types: `CausalQuestion`, `EstimatorInfo`,
    `Estimate`, `Estimator`;
  - the shared data preparation, `design` and `Design`;
  - the registry: `EstimatorRegistry` (a `PluginRegistry`) and
    `default_estimators()`;
  - `score` and the `estimator-scores` table info;
  - three built-ins: `difference-in-means`, `regression-adjustment` and `ipw`;
  - two optional plug-ins, `dowhy-backdoor` and `econml-dml`, each with its
    `requires`.

  All five are declared in the new `sdf.estimators` entry-point group.
- **New `sdf.simulation.benchmark`**: `PromotionBenchmark`, `BenchmarkDraw`,
  and the `promotion-benchmark` table info.
- **API:**
  - `GET /api/v1/estimators`, with the benchmark's parameters and question and
    the request limits;
  - `MAX_ESTIMATE_ROWS`, measured and set in this PR (contract §3.4);
  - `POST /api/v1/causal/estimates`, on the benchmark or on a catalogue
    dataset over the current world;
  - `create_app(estimators=…)`, like `synthesizers` and `datasets`;
  - the response models, and the paths in the UI contract test's allowed list.
- **CLI:** `sdf estimate`, as in the contract (§3.4), with `--csv`.
- **CI:** the job with the optional extras also installs `causal` on Python
  3.13, so the DoWhy and EconML plug-ins are tested there. Elsewhere they skip,
  and are listed as unavailable with the reason.
- **Tests:**
  - each built-in against a closed-form case: a known difference; a linear
    outcome that regression adjustment recovers exactly; balanced propensities
    where `ipw` equals the difference in means;
  - the interval methods and the seeded bootstrap;
  - `design`: missing rows, the one-hot encoding, and every refusal:
    - a time treatment, or a measure treatment with values other than 0 and 1;
    - a time covariate, the treatment or outcome among the covariates, and a
      duplicate covariate;
    - a confidence of 0.5 or 1;
    - a rank-deficient design by `matrix_rank`, for example two covariates
      that are exact copies, or dummies that with the intercept are
      collinear; and a covariate constant within the treated rows but varying
      in the control rows, which is kept;
    - no residual degree of freedom;
    - redundant covariates do not refuse `difference-in-means`
      (`uses_covariates = False`), and do refuse `regression-adjustment`:
      `estimate` raises, while `score` and the API return a number for the
      first and an error row for the second in one 200 answer;
  - the promotion-benchmark and estimator-scores tables' fields, in order,
    with kinds, units and aggregates as in the contract (§3.3);
  - the registry's guard (§3.1): an estimator returning a non-finite value,
    and `ipw` on a perfectly separating covariate (its overlap check, §3.2),
    each give an error row; `ipw` with a few extreme propensities clips them
    and reports the count in `method`;
  - the time budget (§5): after an estimator that uses up
    `MAX_ESTIMATE_SECONDS`, the ones not yet started are error rows, not run;
    a runtime dataset provider that sleeps between rows is stopped with a 422
    once the deadline passes;
    a constant outcome shared by both groups gives a finite zero-width row
    that stays;
  - the benchmark: exact truth, `confounding=0` is unconfounded, a world
    whose SKUs all share one demand gives `z = 0` (random promotion) instead
    of a division by zero, the
    parameter bounds refused by `PromotionBenchmark(...)` itself and by the
    API alike, and a SKU with unit price 0 giving `log_price` 0;
  - `score`'s `seconds` per estimator, empty for one not run;
  - `score`: a failing estimator becomes a row; without a truth the truth
    fields are empty; with a zero truth `relative_bias` is empty;
  - one snapshot per request: a `POST /world` issued while an estimation
    reads its dataset does not change the rows or metadata of that response;
  - the API's 422 and 500 cases, a failing estimator answered as a row in a
    200, and the benchmark's `params` and `question` in `GET /estimators`;
  - the row limit's 422, reached without reading past `MAX_ESTIMATE_ROWS + 1`
    rows of a provider that yields endlessly, and a request at the limits with
    six estimators that finishes under 30 s;
  - the CLI output;
  - the contract examples in §3 run as written.
- **Hook markers.** The built-in estimators and the benchmark are stand-ins, so
  they carry markers under a new checklist row C8, "Causal effect estimation":
  - stand-in: regression adjustment and IPW on a declared adjustment set;
  - algorithm needed: double machine learning with flexible learners, causal
    forests, sensitivity analysis for unobserved confounding;
  - data needed: real promotion or intervention history with its assignment
    rules.

  Each built-in estimator's class carries an `ALGORITHM-HOOK[C8]` marker in its
  docstring. The benchmark's mechanism carries a `DATA-HOOK[C8]` marker: real
  promotion history replaces the declared mechanism. The code index is
  regenerated with `uv run sdf hooks --update-doc`.
- **Docs:** `ARCHITECTURE.md` (analytics gains causal estimation; simulation
  gains the benchmark), the README command list, the new row C8 in
  `ALGORITHM_AND_DATA_CHECKLIST.md` (the stand-in table and the capability
  summary), and this plan's status note with the measured benchmark numbers.

## Non-goals

- No UI (PR 5).
- No causal discovery.
- No time-series causal methods.
- No change to the warehouse generator or any recorded number.

## Acceptance

- The full check list of PR 1's acceptance, with `sdf demo` byte-identical to
  `main`.
- `uv run sdf estimate --confounding 1` shows the naive difference biased by
  several times the truth and both adjusted estimators close to it. Over 50
  seeds, the mean absolute bias of `regression-adjustment` is under 15 % of
  the truth at confounding 1; the PR records the numbers.
- With `uv sync --extra causal` on Python 3.13, `dowhy-backdoor` and
  `econml-dml` run on the same draw and land near the adjusted built-ins.
- `uv run sdf hooks` passes with the new C8 markers, and the checklist's code
  index lists them.
- `POST /api/v1/causal/estimates` returns the same rows as the CLI for the same
  request, and answers a dataset question (`order-lines`, express against
  standard) with empty truth fields.

## Version

`Version: MINOR 1.7.0 → 1.8.0` — a new capability: estimator plug-ins, the
promotion benchmark, two endpoints and `sdf estimate`.

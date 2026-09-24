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
  - `GET /api/v1/estimators`, with the benchmark's parameters and question;
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
  - `design`: missing rows, the one-hot encoding, and every refusal (a time
    treatment, a measure treatment with values other than 0 and 1, a time
    covariate, a confidence of 0.5 or 1);
  - the benchmark: exact truth, `confounding=0` is unconfounded, and the
    parameter bounds;
  - `score`: a failing estimator becomes a row; without a truth the truth
    fields are empty; with a zero truth `relative_bias` is empty;
  - the API's 422 and 500 cases, a failing estimator answered as a row in a
    200, and the benchmark's `params` and `question` in `GET /estimators`;
  - the CLI output;
  - the contract examples in §3 run as written.
- **Docs:** `ARCHITECTURE.md` (analytics gains causal estimation; simulation
  gains the benchmark), the README command list, the
  `ALGORITHM_AND_DATA_CHECKLIST.md` rows for causal estimation, and this
  plan's status note with the measured benchmark numbers.

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
- `POST /api/v1/causal/estimates` returns the same rows as the CLI for the same
  request, and answers a dataset question (`order-lines`, express against
  standard) with empty truth fields.

## Version

`Version: MINOR 1.6.1 → 1.7.0` — a new capability: estimator plug-ins, the
promotion benchmark, two endpoints and `sdf estimate`.

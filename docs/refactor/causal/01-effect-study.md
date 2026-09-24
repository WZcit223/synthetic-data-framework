# PR 1 — Effect study: replicated interventions with intervals

> Status: planned (causal modelling sequence PR 1).

Contract: [`interfaces.md`](interfaces.md) §1.

## Goal

The simulation layer answers "what happens if we take this action" with an
effect and its uncertainty. Each intervention is compared with the baseline on
paired replicate worlds, and the answer is an effects table: the difference, a
confidence interval, and the relative change.

## Scope

- New `sdf.simulation.effects`: `EffectStudy`, `EffectResult`,
  `MAX_REPLICATES`, the `effects` and `effect-replicates` table infos, and the
  paired-t computation (`scipy.stats.t`).
- API (`sdf.api`):
  - `POST /api/v1/effects` with `EffectsRequest` and `EffectsResult`, on the
    current world's spec and generator;
  - the work budget `MAX_EFFECT_WORK`, re-measured and set in this PR;
  - `PolicyChoice` reused from `POST /experiments`, and the same catalogue
    names;
  - the endpoint in the OpenAPI schema and the UI contract test's list of
    allowed paths (no UI uses it yet).
- CLI: `sdf effects`, as in the contract (§1.5), with `--csv`.
- Tests:
  - replicate 0 equals `Experiment` on the same world;
  - pairing: the baseline and the intervention of a replicate share the seed;
  - the interval against a hand computation on fixed differences;
  - the zero-width interval of an unmoved metric (`active_stockouts` under
    `promo_spike`);
  - the relative effect with a zero baseline;
  - every refusal message;
  - the study leaves the API's current world unchanged;
  - the budget's 422;
  - the CLI output on a small spec.
- Docs: `ARCHITECTURE.md` (the simulation layer gains effects), README's
  command list, and this plan's status note with the measured timing.

## Non-goals

- No UI (PR 2), no estimator (PR 4).
- No change to `Experiment`, `POST /experiments` or any recorded number.
- No parallel execution. The work budget keeps a request short. Running
  replicates in processes is a later optimisation, with its own measurement.

## Acceptance

- `uv run ruff check`, `uv run ruff format --check`, `uv run pytest`,
  `node --test ui/*.test.js`, `uv run sdf hooks`, and
  `uv run sdf validate --update-doc docs/VALIDATION.md` with no diff.
- `uv run sdf demo` is byte-identical to `main`.
- `uv run sdf effects --intervention promo_spike --outcome simulated_cost
  --replicates 10` prints the effects. `holding_cost` rises, with an interval
  that excludes 0, and `unmet_units` has an interval that covers 0; the PR
  records the numbers.
- `POST /api/v1/effects` returns the same numbers as the CLI for the same
  request, and a request over budget answers 422 naming `MAX_EFFECT_WORK`.
- The contract examples in §1 run as written (a test executes them).

## Version

`Version: MINOR 1.5.0 → 1.6.0` — a new capability: `sdf.simulation.effects`,
`POST /api/v1/effects` and `sdf effects`.

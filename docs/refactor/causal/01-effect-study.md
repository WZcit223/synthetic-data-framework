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
  - the work budget: `MEASURE_WEIGHT` and `MAX_EFFECT_WORK`, re-measured and
    set in this PR, counting generations and policy × outcome measurements,
    and published in `GET /api/v1/experiments/catalog` under `effects`;
  - `PolicyChoice` reused from `POST /experiments`, and the same catalogue
    names;
  - the endpoint in the OpenAPI schema and the UI contract test's list of
    allowed paths (no UI uses it yet).
- CLI: `sdf effects`, as in the contract (§1.5), with `--csv`.
- Tests:
  - replicate 0 equals `Experiment` on the same world;
  - the replicate table's `difference` equals each arm's value minus the same
    replicate's baseline, and its mean is the effect;
  - pairing: the baseline and the intervention of a replicate share the seed;
  - the interval against a hand computation on fixed differences;
  - the zero-width interval of an unmoved metric (`active_stockouts` under
    `promo_spike`);
  - the relative effect with a zero baseline;
  - every refusal message;
  - the study leaves the API's current world unchanged;
  - the determinism check: a runtime generator that ignores `spec.seed` is
    refused with the message of §1.2, and `warehouse-spec` passes;
  - the check compares against the held world: a runtime generator whose
    first call differs from its later, mutually identical calls is refused
    through the API, and replicate 0's baseline rows equal
    `POST /experiments` on the current world;
  - `warehouse-spec`'s pairing: the baseline and `promo_spike` worlds of one
    seed share their SKU and location tables;
  - the cooperative deadline (§5): a runtime generator that is fast on the
    timed seed and slow on later ones is stopped at the next generation after
    30 s, with a 422 naming the step reached;
  - the timing check: a runtime generator that sleeps per world is refused
    before the study runs, with the measured time and the number of
    replicates that would fit; the projection counts the two check
    generations, and a study at the limit finishes within 30 s;
  - the endpoint studies a world built by a runtime-registered warehouse
    generator, which a default registry would not know, through the
    snapshot's own registry;
  - the budget's 422, and a request at the limit with 6 policies × 6 outcomes
    that finishes under 30 s;
  - the CLI output on a small spec.
- Docs: the plug-in guide (`docs/PLUGINS.md`) states that a warehouse
  generator must be deterministic in its spec (its randomness from
  `spec.seed`); `ARCHITECTURE.md` (the simulation layer gains effects), README's
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

# Layout refactor — overview

Status: accepted by the project lead on 2026-09-23. Companion to
[`docs/REFACTOR_PREP.md`](../../REFACTOR_PREP.md) (the audit) and the first
sequence of the nine steps listed there (§5). Later steps (splitting the
`WarehouseIntelligence` facade, the API state model, the agent executor,
`sdf validate`, HOOK markers) are **not** part of this sequence and get their own
plan directory when they start.

## Why

The audit found that the package's problems are mostly *placement*, not logic:

- `build_registry()` (materialising a world) lives in `cli.py`, so the API,
  the workflow and the scenario runner all import an entry point, and the
  synthesis layer imports the application layer.
- `synthesis/` holds three unrelated kinds of module: generation, validation
  metrics and forecasting/anomaly algorithms.
- One computation (per-SKU daily demand aggregation) exists five times in
  three modules with different semantics.
- The repository breaks its own instruction files: 67 absolute intra-package
  imports and no single-dot relative ones, tests in a separate `tests/` tree
  with `sys.path` hacks, no `__post_init__` validation on any config
  dataclass, duck-typed public functions.
- Nothing has an import-time cycle only because ~30 lazy imports paper over
  the reverse edges; any of them moved to module level breaks import.

## Decision

Move code to where its meaning lives, in pure-move PRs first, before any
behaviour changes. Target layout after this sequence:

```
src/sdf/
  __init__.py        __version__ only
  foundation/        schema.py  registry.py  adapters/retail_csv.py
  synthesis/         spec.py  warehouse.py  materialise.py  fit.py  sdv_synth.py  scenarios.py
  analytics/         demand.py  forecast.py  models.py  anomaly.py
  validation/        quality.py  fidelity.py  tstr.py  privacy.py
  application/       intelligence.py  economics.py  knowledge.py  agent.py  scenarios.py
  observability.py   workflow/pipeline.py   api/app.py   cli.py
```

Layer direction (enforced by a test from PR 2 on):
`foundation → analytics → synthesis → validation → application → workflow → api/cli`
(`observability` ranks with `synthesis`). `analytics` may import only
`foundation`; `synthesis` may import `analytics` (fitting a synthesiser consumes
the shared series aggregation); `validation` may import both; `application` may
import everything below it; entry points may import everything. Nothing imports
an entry point. (PR 3 amended the original `synthesis → analytics` order to
match the code; see its plan file.)

### Alternatives considered

- **Fix only the reverse edges, keep `synthesis/` as is.** Rejected: the
  reverse edges are a symptom of `synthesis/` being a catch-all; without
  splitting it, the next algorithm module lands in the wrong place again.
- **Big-bang restructure in one PR.** Rejected: it would mix moves with the
  demand-aggregation unification and the config validation, so a reviewer
  could not tell which lines changed meaning; the golden numbers would also
  be unverifiable mid-way.
- **Compatibility shims at the old import paths.** Rejected per
  `in-branch-api-compat.instructions.md`; call sites are updated in the same
  PR that moves a file.

### Consequences

- Import paths of `build_registry`, `run_scenarios`, `forecast`, `models`,
  `anomaly`, `quality`, `fidelity`, `tstr`, `privacy` and `warehouse_demo`
  change. None of them is documented as public API (the documented contracts
  are the CLI, the HTTP endpoints, the entities and `GenerationSpec`, see
  `REFACTOR_PREP.md` §2), so the sequence is versioned MINOR, not MAJOR; the
  project lead can override this in PR 2's review.
- `tests/` and `demo/` disappear; their content moves next to the code it
  tests and into the `sdf demo` command respectively.
- Every golden number in `REFACTOR_PREP.md` §2.5 stays unchanged through
  PRs 1–3 and is asserted by `test_golden.py` from PR 1 on. PR 4 may change
  none of them either (validation only rejects inputs the defaults never
  produce).

## Non-goals

- No behaviour change to any command, endpoint or number.
- No split of `WarehouseIntelligence` into services (that is
  `REFACTOR_PREP.md` §5 step 4).
- No numpy/scipy port of the algorithms (step 3 of that sequence; it changes
  numbers and needs its own plan).
- No API state model, agent executor or `validate` subcommand work.

## Planned PRs (sequential; each one passes the review gate before the next starts)

| # | Plan | Purpose | Golden numbers |
|---|---|---|---|
| 1 | [`01-safety-net.md`](01-safety-net.md) | Characterisation tests, colocated test layout, no `sys.path` hacks | unchanged (asserted) |
| 2 | [`02-import-direction.md`](02-import-direction.md) | Remove reverse edges, relative imports, no import-time side effects, layering test | unchanged (asserted) |
| 3 | [`03-module-layout.md`](03-module-layout.md) | `analytics/` + `validation/` split, `intelligence.py`, single demand aggregation | unchanged (asserted) |
| 4 | [`04-contracts.md`](04-contracts.md) | Config validation, typed public functions, built-in generics | unchanged (asserted) |

The interface contract for this sequence is the current code: no new API is
designed, so no example-code contract file is needed. PR 3 introduces one new
module (`analytics/demand.py`); its signature is specified in that plan.

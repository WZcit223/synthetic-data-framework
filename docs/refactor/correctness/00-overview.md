# Correctness refactor — overview

Status: accepted by the project lead on 2026-09-23 (with the two recommended
decisions below). Second sequence after [`docs/refactor/layout/`](../layout/00-overview.md);
it implements step 3 of [`docs/REFACTOR_PREP.md`](../../REFACTOR_PREP.md) §5 and
the `sdf validate` part of step 7. The remaining steps (splitting
`WarehouseIntelligence`, a replenishment-policy interface, the API state
model, the agent executor, HOOK markers) get their own plan directory when
they start.

## Why

The layout sequence moved code to the right place and locked every recorded
number with `golden_test.py`. Some of those numbers are wrong, and nothing ties
the numbers in `docs/VALIDATION.md` to the code:

- The backtest's MAPE divides a sum over positive-actual days by the count of
  all days, so it under-reports error on series with zero days (25.51 % instead
  of 51.01 % on `[0, 10, 0, 10, …]`).
- Safety stock treats an SKU that sells nothing most days like one that sells a
  little every day, which under-sizes the buffer for intermittent SKUs.
- Anomaly detection turns a zero spread into `1e-9`, so any non-zero point on a
  flat series becomes an "anomaly".
- Empty or too-short inputs crash (`IndexError`, `KeyError`) instead of
  answering "no data", and several functions silently accept wrong input
  (duplicate data-source names, unknown scenario names, unparseable CSV rows,
  a quality report with no checks counting as passed).
- `VALIDATION.md` already disagrees with the code (the (s,S) table was recorded
  before demand shocks were added to the generator), because its numbers are
  copied by hand.

Every later step (structural splits, API state, agent, LLM planner) is
verified against the recorded numbers, so they must be correct first.

## Decision

Four implementation PRs, each carrying exactly one kind of change so its diff
explains itself:

| # | Plan | Purpose | Recorded numbers |
|---|---|---|---|
| 1 | [`01-validate-snapshot.md`](01-validate-snapshot.md) | `sdf validate`: one function computes every recorded number; tests and `VALIDATION.md` read it | unchanged |
| 2 | [`02-fail-loudly.md`](02-fail-loudly.md) | Wrong or empty input is reported, never silently absorbed | unchanged |
| 3 | [`03-metrics.md`](03-metrics.md) | Shared error metrics, correct MAPE plus WAPE, too-short series, zero-spread anomaly scale, numpy least squares | MAPE values change |
| 4 | [`04-demand-profile.md`](04-demand-profile.md) | Demand shape (`zero_ratio`) drives the variability used for safety stock; one daily-rate convention | (s,S), economics and scenario values change |

PR 1 comes first so PRs 3 and 4 regenerate the documentation with one command
and show every moved number in one diff. PR 2 comes before the number-changing
PRs so the new guards are in place when formulas change.

### Decisions taken with the plan

1. **MAPE.** Report the corrected MAPE (denominator = number of days with a
   positive actual) *and* WAPE (total absolute error / total actual). The model
   ranking stays by MAE, so no winner changes. `VALIDATION.md` shows old and new
   MAPE side by side once, in PR 3, and only the new convention afterwards.
2. **Intermittent SKUs.** An SKU with no demand on more than half of the days is
   *intermittent*. Its variability for safety stock is
   `max(std, mean / (1 − zero_ratio))`, i.e. the larger of the day-to-day
   spread and the average size of a selling day, so one large order is
   buffered. Croston/TSB forecasting stays an `ALGORITHM-HOOK[C2]` for the
   algorithm phase.

### Alternatives considered

- **Fix numbers inside the upcoming structural split.** Rejected: a diff that
  both moves code and changes results cannot be reviewed; the layout sequence
  deliberately kept numbers fixed for this reason.
- **Replace MAPE by WAPE only.** Rejected for now: it breaks the comparison with
  the numbers already quoted in reports; the side-by-side table in PR 3 keeps
  continuity.
- **Croston's method for intermittent SKUs now.** Rejected for this sequence:
  it is a new forecasting model, not a correction, and belongs to the
  algorithm phase.

### Consequences

- MAPE columns, (s,S) policy counts and safety-stock totals, the economics
  estimate and the scenario table change in PRs 3 and 4. Each of those PRs
  lists every moved golden number with its old value, new value and cause.
- `DataSourceRegistry.register` raises on a duplicate name unless
  `replace=True`; several functions take their numeric options by keyword only
  (PR 2). All in-repo callers are updated in the same PR.
- `WarehouseIntelligence.sku_daily_stats` is replaced by `demand_profiles`
  (PR 4), without an alias, per `in-branch-api-compat.instructions.md`.

## Non-goals

- No split of `WarehouseIntelligence`, no `ReplenishmentPolicy` interface, no
  change to which callers use the rule-based suggestions versus (s,S).
- No API state model, agent executor or dashboard change.
- No new forecasting or anomaly model.
- The headline numbers in `VALIDATION.md` measured on the full 13-month dataset
  (not bundled in the repository) stay as recorded and are labelled as a
  manual run.

## Version

`Version: none` for the plan itself (documentation only). Each implementation
PR records its own bump in its plan file.

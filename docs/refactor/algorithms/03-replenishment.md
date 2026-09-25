# PR 3 — Cost-based replenishment, scored out of sample

> Status: implemented. The numbers are in `docs/VALIDATION.md` ("C2 —
> Replenishment out of sample"); every acceptance target is met. Two details
> the plan left open: the holdout outcome names its metrics `holdout_…` (with a
> `holdout_total_cost`), since an effect study refuses two outcomes reporting
> the same metric; and the comparison endpoint reports the holdout metrics for
> every row, not only the new one, so the three can be compared.

Contract: [`interfaces.md`](interfaces.md) §5.

## Goal

The replenishment policy chooses both levels per SKU from its own costs and
history, and every policy can be compared on days it was not fitted on.

## Scope

- **`PolicyInput` and `levels_for`** (§5.2). `plan_orders` and
  `SimulatedCost` call `levels_for`; existing policies are unchanged.
- **`CostBasedPolicy`** (§5.3): the search over the contract's grid of
  reorder points and order sizes on the replayed cost of each SKU's history.
- **`SimulatedCost(holdout_days=…)`** (§5.4) and, in the simulation
  catalogue, the policy kind `cost-based` and the outcome
  `simulated_cost_holdout`, so `POST /api/v1/experiments`,
  `POST /api/v1/effects` and the Effects page can use them with no other
  change. `GET /api/v1/experiments/catalog` lists them.
- **`/api/v1/replenishment/comparison`** gains the cost-based policy as a
  third row next to the service-level and no-safety-stock policies, with the
  holdout cost; the existing rows stay as they are.
- **Hook markers.** `ServiceLevelPolicy` keeps `ALGORITHM-HOOK[C2]` (it stays
  the default for the recorded numbers); `CostBasedPolicy` carries one
  (stochastic lead times and a fitted lead-time demand distribution), and
  `CostModel` keeps its `DATA-HOOK[C2]` (real unit costs).
- **Docs:** a new section in `docs/VALIDATION.md`, "Replenishment out of
  sample", with the table of the overview's spike re-measured, per policy;
  checklist row C2.

## Tests

- `levels_for` calls `levels_for` when the policy has it and `levels`
  otherwise; the existing policies give the same levels as before.
- `CostBasedPolicy` on a hand-built history finds the grid point a brute
  force over the same grid finds; ties go to the smaller levels; it never
  reads beyond `item.history`.
- With zero order cost every candidate order size is 0; with a zero
  holding cost (a zero rate or a zero unit cost) the order size is capped at
  one order for the whole history, with no division by zero; with a zero
  margin, `z = 0`.
- `SimulatedCost(holdout_days=None)` gives today's numbers exactly;
  `holdout_days` too large for the history raises with the numbers.
- Experiments and effect studies run with `cost-based` and
  `simulated_cost_holdout`.

## Non-goals

- No change to the default policy, `sdf demo`, `sdf impact` or any recorded
  number. Making the cost-based policy the default is a separate decision,
  taken on this PR's numbers.
- No stochastic lead times, no back-orders (the replay stays lost-sales, as
  today).
- No forecaster inside the policy. `PolicyInput` has no day axis and no other
  SKUs, which a forecaster needs; planning on a forecast is a later contract
  change, decided on this PR's and PR 2's numbers.
- No page change beyond what the catalogue gives the Effects page.

## Acceptance

- The required checks of `AGENTS.md`, with `sdf demo` byte-identical to
  `main`.
- On the default world, fitted on the first 60 days and replayed on the last
  30, `cost-based`'s total simulated cost is below `service-level-95`'s by at
  least 30 %, with a fill rate of at least 99 %. An effect study with 10
  replicates gives the saving with its interval. The PR records the numbers.
- 200 SKUs are planned in under 2 s.

## Version

`Version: MINOR 1.10.0 → 1.11.0` — a new policy, a new outcome, and
`levels_for` for policies that need the SKU.

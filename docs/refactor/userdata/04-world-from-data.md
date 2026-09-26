# U4 — A world from data

> Status: planned.

Contract: [`interfaces.md`](interfaces.md) §4.

## Goal

The warehouse the dashboard, replenishment and anomalies read can be built
around demand that really happened, so every operational flow runs on real
orders.

## Scope

- **`OrdersData`** in the synthesis contract, with the `orders-only`
  example as a test fixture and in the plug-in guide, and
  **`warehouse-from-demand`** (`produces="warehouse"`, `needs_fit=True`),
  fitted on a source's orders: the cut (busiest SKUs, at most 400; date
  window, at most 730 days), SKUs' category, ABC class, unit price and cost
  as §4 says, and synthesized locations, inventory, receipts and sensors,
  with their hook markers and checklist rows.
- **`build_registry_from_source`**, used by `POST /api/v1/world {source, …}`
  and the command line. `build_registry` refuses a warehouse synthesizer
  that needs fitting (422 through the API).
- `SyntheticWarehouse.spec` becomes optional; every reader checked.
- A world from data has `spec=None` and records its source and cut; the
  refusals of spec-level flows name the reason, and `GET /scenarios`
  answers 422 instead of 500; `POST /world` with a spec and no synthesizer
  after a world from data uses `warehouse-spec`.
- The replenishment comparison takes `holdout_days` (default 30, as today)
  and lists its cost assumptions in its answer.
- Command line: `--source`, `--max-skus`, `--days` on `export`, `pipeline`,
  `agent`, `anomalies`; `scenarios`, `effects`, `impact` refuse a source.
- Docs: `docs/PLUGINS.md` with a minimal `OrdersData` synthesizer,
  `docs/ARCHITECTURE.md`, `docs/VALIDATION.md` (what a world from data keeps
  and what it synthesizes).

## Tests

- A world from a small source: every entity check passes, SKUs and orders
  equal the source's within the cut, ABC classes from units, assumed prices
  and costs marked.
- The dashboard, comparison, anomalies (every signal) and export answer on it.
- Effect studies, experiments and `GET /scenarios` refused with 422 and the
  reason; a data-level intervention applied; regeneration after it
  generates; `POST /world {synthesizer: "warehouse-from-demand"}` without a
  source refused.
- `holdout_days` 30 gives today's comparison exactly; other values replay
  the last days given.
- The `orders-only` fixture builds a world every flow reading only SKUs and
  orders accepts.
- Occupancy of a world from data within a generated world's range.

## Non-goals

- No change to the default policy (decision E4).
- No spec-level scenarios or effect studies on a world from data.
- No change to generated worlds or any recorded number.

## Acceptance

- The required checks, with `sdf demo` byte-identical and no recorded number
  changed.
- **Size.** Measured on a generated source of the largest cut (400 SKUs ×
  730 days): building the world, the first dashboard answer and the
  replenishment comparison each take under 30 seconds on the CI runner, and
  the process stays under 1 GB. If not, the maxima come down in this PR, and
  the PR says to what.

## Version

Version: MINOR 1.16.0 → 1.17.0, a new warehouse synthesizer with a new
input type, and `POST /world` takes a source.

# U4 — A world from data

> Status: planned.

Contract: [`interfaces.md`](interfaces.md) §4.

## Goal

The warehouse the dashboard, replenishment and anomalies read can be built
around demand that really happened, so every operational flow runs on real
orders.

## Scope

- **`OrdersData`** in the synthesis contract, and **`warehouse-from-demand`**
  (`produces="warehouse"`), fitted on a source's orders: the cut (busiest
  SKUs, date window), SKUs' category, ABC class, unit price and cost as §4
  says, and synthesized locations, inventory, receipts and sensors.
- **`build_registry_from_source`**, used by `POST /api/v1/world {source, …}`
  and the command line; `build_registry` and regenerations unchanged.
- A world from data has `spec=None` and records its source and cut; the
  refusals of spec-level flows name the reason; `POST /world` with a spec and
  no synthesizer after a world from data uses `warehouse-spec`.
- The replenishment comparison's answer lists its cost assumptions.
- `DELETE /sources/{name}` refused while the current world reads it.
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
- Effect studies and spec-level scenarios refused with the reason; a
  data-level intervention applied; regeneration after it generates.
- Occupancy of a world from data within a generated world's range.

## Non-goals

- No change to the default policy (decision E4).
- No spec-level scenarios or effect studies on a world from data.
- No change to generated worlds or any recorded number.

## Acceptance

- The required checks, with `sdf demo` byte-identical and no recorded number
  changed.
- **Size.** Measured on a generated source of the largest cut (500 SKUs ×
  730 days): building the world, the first dashboard answer and the
  replenishment comparison each take under 30 seconds on the CI runner, and
  the process stays under 1 GB. If not, the maxima come down in this PR, and
  the PR says to what.

## Version

`Version: MINOR 1.16.0 → 1.17.0` — a new warehouse synthesizer with a new
input type, and `POST /world` takes a source.

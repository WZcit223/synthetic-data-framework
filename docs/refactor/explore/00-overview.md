# Data exploration and synthesizer choice — overview

Status: proposed on 2026-09-24. The project lead asked for this sequence on
2026-09-24: build the pivot table (with priority, and professional in look and
behaviour) and the synthesizer choice first, and design the interfaces the
causal modelling and the algorithm phase will need while doing so. Those two
follow as separate sequences after this one.

The interface contract every PR follows is [`interfaces.md`](interfaces.md).

## Why

Two of the extension points the structure refactor prepared are still closed to
users:

- **Synthesizers are plug-ins, but only the CLI can choose one.** Every
  synthesis algorithm, ours included, is mounted through the `sdf.synthesizers`
  entry-point group, yet the dashboard always generates with `warehouse-spec`,
  and nothing shows which synthesizers are installed, which are unavailable and
  why, or how well one reproduces a real dataset. The project lead's requirement
  is that users can choose, add and develop their own synthesis algorithms.
- **The UI shows fixed panels only.** The project lead's rule for the UI is
  that it may carry lightweight transformations and statistics that need no
  audit trail, such as a pivot table. Today no panel lets a user group, filter
  or cross-tabulate the data behind it.

## Decisions

1. **The backend publishes tables; the browser pivots them.** A table is a list
   of typed fields (dimension, time or measure) plus rows. The backend decides
   what a table contains and computes every business number in it (line value,
   stock value, order quantity); the pivot page only groups, filters,
   aggregates and draws what it received. Nothing a pivot shows is written
   back, so it needs no audit trail. *Alternative rejected:* a server-side
   aggregation endpoint. It would make every exploratory view a logged API
   call and still need a client for the interaction, with no gain at the
   framework's data sizes (at most a few hundred thousand rows).
2. **Tables come from a catalogue of dataset providers, mounted like
   synthesizers.** Built-in providers (order lines, inventory, SKUs, the
   replenishment plan) are declared in the `sdf.datasets` entry-point group of
   this package's own `pyproject.toml`; another package adds a table the same
   way. This is where the algorithm phase publishes its outputs (forecast
   against actual, anomaly scores) and where the causal modelling publishes its
   effect estimates, without any UI change.
3. **Any endpoint that returns `{fields, rows}` can be pivoted.** Datasets,
   experiment results and synthesizer runs share one table shape, so the pivot
   page opens each of them the same way. The experiment result gains its
   `fields`; its rows keep their current form.
4. **Synthesizers describe their own parameters.** The registry reads each
   synthesizer's keyword arguments and their defaults (`seed`, `jitter`, …), so
   the UI builds a form for any plug-in without new metadata. A synthesizer is
   evaluated on a bundled real dataset with the checks the CLI already runs:
   fidelity for a series synthesizer, privacy for a table synthesizer. The CLI
   and the API share that one evaluation.
5. **The UI stays plain HTML and JavaScript modules, with no build step and no
   npm dependency.** The pivot engine is a pure module, tested with Node's
   built-in test runner in CI. *Alternative rejected:* a frontend framework or
   a third-party pivot library. It would add a toolchain the repository does
   not have, for a view this sequence can build and test directly.

## Sequence

Each PR passes the full gate (review, fixes, squash merge) before the next one
starts.

| # | Plan | Outcome | Version |
|---|---|---|---|
| 1 | [`01-dataset-catalogue.md`](01-dataset-catalogue.md) | Dataset catalogue with typed fields; `GET /api/v1/datasets`, `GET /api/v1/datasets/{name}`, `GET /api/v1/experiments/catalog`; the experiment result carries its fields | MINOR 1.3.1 → 1.4.0 |
| 2 | [`02-pivot-page.md`](02-pivot-page.md) | The Explore page: a pivot table and chart over any catalogue table or experiment result | none (UI only) |
| 3 | [`03-synthesizer-catalogue.md`](03-synthesizer-catalogue.md) | `GET /api/v1/synthesizers` with parameters, `POST /api/v1/synthesis/runs`, and `POST /api/v1/world` choosing its synthesizer | MINOR 1.4.0 → 1.5.0 |
| 4 | [`04-synthesizer-page.md`](04-synthesizer-page.md) | The Synthesizers page, the world-generator choice on the dashboard, and the plug-in guide | none (UI and documentation) |

## Non-goals

- No causal estimation and no new algorithm. Both come after this sequence; this
  sequence only fixes the interfaces they plug into (see
  [`interfaces.md`](interfaces.md), "Later").
- No server-side pivot, no saved views on the server (a view is kept in the page
  address, so a link reproduces it), and no upload of a user's own CSV.
- No change to any recorded number: `docs/VALIDATION.md` and `sdf demo` stay as
  they are.

## Version

Planned per PR in the sequence table. The plan PR itself:
`Version: none, documentation and plans only`.

# U1 — Sources

> Status: implemented. As built, where it differs from the plan below (the
> contract, `interfaces.md` §1, is updated to match):
> - No `source_demand` function: nothing in U1 reads demand, and
>   `DemandTable.from_orders(store.orders(name)[1])` is the whole of it; U3
>   calls that where it reads demand.
> - The merge is a class, `Datasets(catalogue, store)`, since the API asks it
>   for names, fields, origin and rows; the API reads through it, and the
>   command line will from U7, the first command that reads a dataset.
> - An app takes a store with its own limits, `create_app(sources=…)`,
>   instead of `source_limits=…`, so tests and deployments choose both the
>   folder and the limits.
> - A full store answers 409 (a conflict with what is stored), not 413.
> - Refusing to delete a source the current world reads comes with the world
>   from data (U4): until then no world reads a source.
> - `GET /synthesis/sources` still lists only the bundled files, the only
>   ones a run can use until U2.

Contract: [`interfaces.md`](interfaces.md) §1.

## Goal

A user can hand the framework a CSV, see how it was read, correct it, and
find it next to the bundled data wherever data is listed.

## Scope

- **New `sdf.foundation.sources`:** `ColumnSpec`, `Roles`, `SourceSchema`
  with its checks, `infer_schema`, `SourceLimits`, `SourceStore` (§1.1, §1.2),
  returning foundation types only (layering). `source_demand` in
  `sdf.analytics.demand`. The two bundled files are declared as read-only
  sources.
- **Uploads** streamed to a temporary file with a byte counter, checked, and
  moved into place with one rename; one store lock for adding and removing.
- **HTTP:** `GET/POST/PUT/DELETE /api/v1/sources` (§1.3);
  `create_app(source_limits=…)`; CORS allows `PUT` and `DELETE`. The API
  refuses to delete a source the current world reads.
- **Sources as datasets:** one function in the application layer,
  `datasets(catalogue, store)`, merges them with the catalogue's datasets as
  `source-<name>`, with the field mapping and the row and cell limits of
  §1.3; the API and the command line both call it. The `source-` prefix is
  refused for dataset plug-ins.
- **CSV exports** prefix text cells that start with `=`, `+`, `-` or `@`
  (§1.3).
- **Command line:** `sdf data add/list/show/remove` (§1.4).
- `data/sources/` gitignored. Docs: README (a short "Your own data"),
  `docs/ONBOARDING.md`, `docs/ARCHITECTURE.md`.

## Tests

- Inference on small files: each rule in its order (a date column named
  `OrderDate` is `time`, not `id`; unique amounts stay `real`; numeric ids
  read as `id`), blanks ignored, ambiguous day and month order flagged, the
  category fallback, semicolons with decimal commas, roles guessed from
  names.
- The layering test passes: the store imports nothing above the foundation.
- Checks: a quantity column unreadable on 6 % of rows refused, on 2 % kept
  with the count and examples.
- The store: names checked and reserved, each limit refused with its name, an
  oversized upload refused without a declared length and its temporary file
  gone, a concurrent add of the same name refused, a bundled source not
  removable, a source in use not removable.
- The endpoints through the test client, including 413, 409 and 422; the
  dataset view of a source, including field mapping, collisions, a
  timestamp's hour field and the sample answer over the row limit.
- The CSV guard on exports.

## Non-goals

- No change to evaluation, forecasting, anomalies or the world (U2 to U4).
- No page (U5); Explore lists the new datasets as it lists every dataset.
- No file formats but CSV.

## Acceptance

- The required checks of `AGENTS.md`, with `sdf demo` byte-identical to
  `main`, and no recorded number changed.
- `sdf data add` on the bundled `retail-10k` file under a new name infers
  these kinds: `Invoice` id, `StockCode` id, `Description` text, `Quantity`
  integer, `InvoiceDate` time (month-first, flagged ambiguous only if every
  sampled day is at most 12), `Price` real, `Customer ID` id, `Country`
  category; and these roles: time `InvoiceDate`, item `StockCode`, quantity
  `Quantity`, price `Price`. The bundled declaration is the same.

## Version

Version: MINOR 1.13.0 → 1.14.0, a new module, four endpoints and a
command group.

# U1 — Sources

> Status: planned.

Contract: [`interfaces.md`](interfaces.md) §1.

## Goal

A user can hand the framework a CSV, see how it was read, correct it, and
find it next to the bundled data wherever data is listed.

## Scope

- **New `sdf.foundation.sources`:** `ColumnSpec`, `Roles`, `SourceSchema`
  with its checks, `infer_schema`, `SourceLimits`, `SourceStore` (§1.1, §1.2).
  The two bundled files are declared as read-only sources.
- **Uploads** streamed to a temporary file with a byte counter, checked, and
  moved into place with one rename; one store lock for adding and removing.
- **HTTP:** `GET/POST/PUT/DELETE /api/v1/sources` (§1.3);
  `create_app(source_limits=…)`; CORS allows `PUT` and `DELETE`.
- **Sources as datasets:** the API merges them with the catalogue's datasets
  as `source-<name>`, with the field mapping and the row sample of §1.3; the
  `source-` prefix is refused for dataset plug-ins.
- **CSV exports** prefix text cells that start with `=`, `+`, `-` or `@`
  (§1.3).
- **Command line:** `sdf data add/list/show/remove` (§1.4).
- `data/sources/` gitignored. Docs: README (a short "Your own data"),
  `docs/ONBOARDING.md`, `docs/ARCHITECTURE.md`.

## Tests

- Inference on small files: numeric ids read as `id`, blanks ignored,
  ambiguous day and month order flagged, the category fallback, semicolons
  with decimal commas, roles guessed from names.
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
  the schema the bundled declaration has, except for the time format.

## Version

`Version: MINOR 1.13.0 → 1.14.0` — a new module, four endpoints and a
command group.

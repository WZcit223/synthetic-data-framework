# PR 1 — Dataset catalogue and table API

Contract: [`interfaces.md`](interfaces.md) §1 and §2.1.

## Goal

The backend publishes the data behind the dashboard as typed tables, one per
catalogue dataset, and the experiment result says what its columns are, so a
client can group, filter and cross-tabulate any of them without knowing their
meaning in advance.

## Scope

- New `sdf.foundation.tables`: `Field`, `DatasetInfo`, `Table`, with their
  checks in `__post_init__`.
- New `sdf.application.datasets`: `DatasetProvider` (protocol),
  `DatasetCatalog`, `default_datasets()`, and the four built-in providers
  `OrderLinesDataset`, `InventoryDataset`, `SkuDataset`,
  `ReplenishmentPlanDataset`, declared in the `sdf.datasets` entry-point group
  of `pyproject.toml`. Every business number in a table (line value, stock
  value, the plan's levels and order quantity) is computed here, from the same
  functions the dashboard already uses; the replenishment plan is
  `plan_orders(world, ServiceLevelPolicy(service_level=0.95))`.
- API (`sdf.api`): `GET /api/v1/datasets`, `GET /api/v1/datasets/{name}` (with
  `limit`, capped at `MAX_DATASET_ROWS`), `GET /api/v1/experiments/catalog`, and
  `fields` added to the `POST /api/v1/experiments` response. The catalogue's
  policy parameter bounds are read from the same model that validates
  `POST /experiments`, so the two cannot drift. Response models follow the
  existing rule: declared fields plus pass-through.
- Tests: field and table checks; each built-in dataset's field names and row
  count on the default world, with its totals matching the dashboard's figures
  (units on hand, inventory value, SKUs needing an order at 95 %); a runtime
  provider and an entry-point plug-in (mounted, name clash, failing import);
  each endpoint, including 404, `limit`, `truncated`, and a catalogue whose
  bounds are the ones `POST /experiments` enforces.
- Docs: `ARCHITECTURE.md` describes the catalogue, the table shape and the
  `sdf.datasets` plug-in group; `README.md` lists the new endpoints next to the
  existing API description.

## Non-goals

- No UI change; the pivot page is PR 2.
- No change to any existing endpoint's fields or numbers besides the added
  `fields` on the experiment result.
- No caching of built tables: a dataset is built per request from the current
  world snapshot. The default world's largest table builds well under a
  second; caching is added only if a later measurement needs it.

## Acceptance

```bash
uv sync --locked --extra api
uv run ruff check && uv run ruff format --check
uv run pytest
uv run sdf hooks
uv run sdf validate --update-doc docs/VALIDATION.md && git diff --exit-code docs/VALIDATION.md
git worktree add /tmp/sdf-main origin/main && (cd /tmp/sdf-main && uv run sdf demo) > /tmp/demo-main.out
uv run sdf demo | diff /tmp/demo-main.out -            # byte-identical
git worktree remove /tmp/sdf-main
```

The examples in `interfaces.md` §1.2 and §2.1 run as written, checked by tests.

## Version

`Version: MINOR 1.3.1 → 1.4.0` — new modules, a new plug-in group, three new
endpoints and an added field on the experiment result.

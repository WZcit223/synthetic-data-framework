# PR 3 — Synthesizer catalogue, evaluation and world-generator choice (API)

Contract: [`interfaces.md`](interfaces.md) §4.

## Goal

A client can list every mounted synthesizer with its parameters, see which
declared ones are unavailable and why, run any series or table synthesizer
against a bundled real dataset and get its quality scores plus a
real-against-synthetic table, and generate the world with any synthesizer that
produces a warehouse.

## Scope

- `sdf.synthesis.api`: `Param(name, type, default, min=None, max=None,
  exclusive=False)`. `sdf.synthesis.registry`: `SynthesizerRegistry.params(name)`
  reads the keyword arguments of the synthesizer's constructor (resolving string
  annotations) and an optional `param_bounds` class attribute.
  `bootstrap-table` declares `jitter` bounds.
- New `sdf.validation.evaluation`: `sources()`, which lists the bundled CSVs
  present under `$SDF_DATA_DIR` (default `./data`), and `evaluate(synthesizer, *,
  source, params=None) -> SynthesisRun(synthesizer, source, kind, metrics,
  table)`. A series synthesizer is fitted on the source's hourly demand and
  scored with `fidelity_report`; a table synthesizer on its feature table and
  scored with `privacy_report`. Both scorers keep their `ALGORITHM-HOOK`
  markers. `sdf synth` and `sdf privacy` call `evaluate` and print unchanged
  output.
- `World.generate(spec, *, synthesizer="warehouse-spec", synthesizers=None)`
  builds the world with the named synthesizer from the given registry (default
  `default_registry()`); `build_registry` takes the same arguments. A
  synthesizer that does not produce a `SyntheticWarehouse` is rejected. The
  world keeps `synthesizer` and its registry, and `SpecIntervention.apply`
  regenerates with both, so a scenario never silently switches generator.
- `create_app(synthesizers=…)`: the app holds one synthesizer registry for its
  lifetime (default `default_registry()`, built once), and the catalogue, runs,
  `POST /world` and the scenario regeneration all use it. `evaluate` takes the
  registry as an argument.
- API: `GET /api/v1/synthesizers`, `GET /api/v1/synthesis/sources`,
  `POST /api/v1/synthesis/runs`; `POST /api/v1/world` and the world snapshot
  accept and report `synthesizer`. The run endpoint validates parameter names,
  types and bounds before creating the synthesizer and answers 422 otherwise.
  Only the bundled source IDs are accepted; a client never sends a path.
- Tests:
  - `params` for each built-in and for a plug-in with bounds;
  - `evaluate` for series and table against the numbers `sdf synth` and
    `sdf privacy` print today, and each rejection;
  - a runtime warehouse synthesizer registered on the registry passed to
    `create_app` is listed, runs, builds the world through `POST /world`, and
    is kept by `/scenarios` and `/experiments` when they regenerate the world;
  - each endpoint, including every 422 case and an unavailable synthesizer.
- Docs: `ARCHITECTURE.md` (synthesizer parameters, evaluation, the world
  generator choice).

## Non-goals

- No UI; the Synthesizers page is PR 4.
- No new synthesizer and no new metric: runs are scored by the fidelity and
  privacy checks that exist today.
- No user upload or arbitrary file path; the sources are the bundled CSVs.

## Acceptance

```bash
uv sync --locked --extra api
uv run ruff check && uv run ruff format --check
uv run pytest
uv run sdf hooks
uv run sdf validate --update-doc docs/VALIDATION.md && git diff --exit-code docs/VALIDATION.md
uv run sdf synth data/sample_online_retail_ii.csv     # output identical to main's
uv run sdf privacy data/sample_online_retail_ii.csv   # output identical to main's
git worktree add /tmp/sdf-main origin/main && (cd /tmp/sdf-main && uv run sdf demo) > /tmp/demo-main.out
uv run sdf demo | diff /tmp/demo-main.out -            # byte-identical
git worktree remove /tmp/sdf-main
```

The examples in `interfaces.md` §4 run as written, checked by tests.

## Version

`Version: MINOR 1.4.0 → 1.5.0` — new registry and world-generation parameters,
a new evaluation module and three new endpoints.

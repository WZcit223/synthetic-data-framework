# PR 4 — The Synthesizers page, the world-generator choice and the plug-in guide

Contract: [`interfaces.md`](interfaces.md) §4.2 (the endpoints it uses) and §3
(the pivot page it links to).

## Goal

A user sees every synthesizer the installation offers, runs one against a real
dataset with chosen parameters, compares real and synthetic data, and picks the
generator of the dashboard's world; a developer finds, in one guide, how to
write and mount their own synthesizer or dataset.

## Scope

- **`ui/synthesizers.html`, `ui/synthesizers.js`.**
  - *Catalogue.* A card per synthesizer: name, what it produces (series, table
    or warehouse), its origin (built-in, plug-in or runtime), its description
    and required modules. Unavailable synthesizers are listed with their reason.
  - *Run panel.* A form built from the synthesizer's parameters: number and text
    inputs with their bounds, defaults shown, invalid input flagged before
    sending. It also takes a source choice and a Run button.
  - *Result.* Score tiles:
    - series synthesizer: fidelity score, KS statistic, profile correlation,
      mean and standard-deviation deltas;
    - table synthesizer: median distance to closest real record, clone risk
      and verdict.

    Below the tiles, a real-against-synthetic chart: overlaid lines for a
    series, per-column distribution comparison for a table. An "Open in
    Explore" link opens the run's table in the pivot page (the link carries the
    run request, and the Explore page repeats it; runs are seeded, so the same
    request gives the same table).
- **Dashboard.** The generation controls gain a "Generator" choice listing the
  synthesizers that produce a warehouse; the regenerate request sends it, and
  the page shows which generator built the current world.
- **Navigation.** Dashboard, Explore, Synthesizers on every page.
- **`docs/PLUGINS.md`.** How to write a synthesizer (the protocol, parameters
  and bounds, what each kind must return) and a dataset provider, how to
  declare either in a package's `pyproject.toml`, how the registry reports a
  plug-in that fails to load, and how to check it with `sdf` and the API.
  `README.md` links to it.
- **Tests.**
  - A test runs the guide's two examples (a series synthesizer and a dataset
    provider) through the registry and the catalogue.
  - The UI-path-in-OpenAPI check covers the new page.
  - `node --test ui/` covers any new pure helper.

## Non-goals

- No backend change beyond what PR 3 delivered.
- No installing of packages from the UI: a plug-in is installed with `uv` (or
  pip) in the environment that runs the API, then appears in the catalogue.

## Acceptance

```bash
uv sync --locked --extra api
uv run ruff check && uv run ruff format --check
uv run pytest
node --test ui/
```

Manual, in a browser against `SDF_UI_DIR=ui uv run uvicorn sdf.api.app:app`:

- Each built-in series and table synthesizer runs on each bundled source; the
  scores equal `sdf synth` and `sdf privacy` for the same source and seed.
- "Open in Explore" reproduces the run's table in the pivot page.
- Regenerating the world with the generator choice updates the dashboard and
  names the generator.
- With a runtime-registered test plug-in, the plug-in appears and runs without
  any UI change.
- No failed request and no console error.

## Version

`Version: none` — the UI, the guide and tests are not part of the Python
distribution; no shipped code changes.

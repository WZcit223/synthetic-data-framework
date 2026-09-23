# PR 7 — Separate UI and a versioned JSON API

Interface contract: [`interfaces.md` §4.3](interfaces.md#43-target-after-pr-7-versioned-json-api-and-a-separate-ui).

## Goal

The UI is a separate component that only carries user intent to the backend
and presents results. The backend is a JSON-only API whose OpenAPI schema is the
contract (F3).

## Scope

- Move `src/sdf/api/static/dashboard.html` to `ui/` (`index.html`, `app.js`,
  `style.css`). All backend calls go through the `api()` helper with a
  configurable base URL, as in the contract.
- API: every endpoint moves under `/api/v1` with the names in the contract's
  table. `POST /api/v1/world` takes a JSON body. Response models are declared so
  `/api/v1/openapi.json` describes every field. The HTML route and the static
  directory leave the Python package. CORS origins come from `SDF_CORS_ORIGINS`.
- `POST /api/v1/experiments` runs a PR 2 `Experiment` from built-in
  intervention, policy and outcome names, and returns tidy rows.
- Development hosting: `create_app(ui_dir=…)` or `SDF_UI_DIR=ui` mounts `ui/`
  at `/`; README and ONBOARDING describe it.
- UI rule written into `AGENTS.md` and `docs/ARCHITECTURE.md`: the UI may
  reshape received data (sort, filter, group, pivot, chart) but computes no
  business number.
- Tests:
  - every path `ui/app.js` passes to `api()` exists in the OpenAPI schema;
  - the Python package contains no `.html` file;
  - the experiment endpoint returns the same rows as `Experiment.run()`.

## Non-goals

- No pivot view or new UI feature (F3 follow-up), no JavaScript build tool.

## Acceptance

```bash
uv run ruff check && uv run ruff format --check
uv run --extra api pytest                              # contract, UI-path and experiment tests pass
SDF_UI_DIR=ui uv run --extra api uvicorn sdf.api.app:app   # manual: dashboard loads from ui/ and every panel renders
```

## Version

`Version: MAJOR 0.14.0 → 1.0.0` (needs the project lead's approval, see the
overview): every HTTP path changes to the versioned `/api/v1` contract, which
becomes the first stable API.

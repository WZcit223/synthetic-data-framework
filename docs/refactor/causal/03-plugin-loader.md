# PR 3 — One plug-in loader for every catalogue

> Status: planned (causal modelling sequence PR 3).

Contract: [`interfaces.md`](interfaces.md) §2.

## Goal

Entry-point loading is written once. Synthesizers and datasets share it now,
and estimators (PR 4) use it instead of adding a third copy.

## Scope

- New `sdf.foundation.plugins`: `PluginRegistry`, `Origin`, and the shared
  checks and entry-point handling now duplicated in `sdf.synthesis.registry`
  and `sdf.application.datasets`.
- `SynthesizerRegistry` and `DatasetCatalog` become subclasses that keep only
  their own checks and methods (`create`, `params`; `build`, `head`).
- One change a user can see: the dataset catalogue's name-clash reason names
  the holder, as the synthesizer one does.
- Tests: the shared behaviour is tested once, on a minimal registry, in
  `sdf/foundation/plugins_test.py`. The existing registry and catalogue tests
  pass unchanged apart from that one message, which proves the move changed
  nothing else. The layering test passes (`foundation` imports nothing above
  it).

## Non-goals

- No estimator yet (PR 4).
- No change to any public name, signature or entry-point group.
- No change to an API response apart from the one reason text.

## Acceptance

- The full check list of PR 1's acceptance, with `sdf demo` byte-identical to
  `main`.
- `GET /api/v1/synthesizers` and `GET /api/v1/datasets` answer as before with
  and without the `synthesis` extra, except the reworded clash reason.
- The plug-in guide's examples (`src/sdf/plugins_guide_test.py`) pass
  unchanged.

## Version

`Version: PATCH 1.6.0 → 1.6.1` — a contained internal change: one reason text
changes, nothing else a user or plug-in author can see.

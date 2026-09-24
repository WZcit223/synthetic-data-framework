# PR 3 — One plug-in loader for every catalogue

> Status: implemented (causal modelling sequence PR 3). `sdf.foundation.plugins`
> holds `PluginRegistry`, `Origin`, `Registration` and `DISTRIBUTION`; the
> synthesizer registry and the dataset catalogue are subclasses, and the old
> module names (`Origin`, `Registration`, `DISTRIBUTION`) stay importable where
> they were. Each catalogue keeps its checks in their old order, so every
> message is unchanged apart from the dataset clash reason, which now names the
> holder. One kind of test line moved with the code: tests that replace the
> entry-point lookup now patch `sdf.foundation.plugins.entry_points`, where the
> lookup lives, instead of the registry's own module; their assertions are
> unchanged. A subclass also sets `made_by` ("create(name)", "build(name)"),
> the wording of the constructor-defaults message.

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
  `src/sdf/foundation/plugins_test.py`. The existing registry and catalogue tests
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

`Version: MINOR 1.6.0 → 1.7.0` — a new import path, `sdf.foundation.plugins`
(`PluginRegistry`, `Origin`), which plug-in registries build on; the behaviour
of the existing registries is unchanged apart from one reason text.

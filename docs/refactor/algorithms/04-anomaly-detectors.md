# PR 4 — Anomaly detector plug-ins, measured on injected anomalies

> Status: implemented. The numbers are in `docs/VALIDATION.md` ("C3 — Anomaly
> detection on injected anomalies"); the acceptance target is met
> (`isolation-forest`'s shrinkage recall 1.0). Where the implementation departs
> from the contract, and why:
>
> - `isolation-forest` reads the stock and receipts through the missing stock
>   only (in days of the SKU's mean demand), not as series of their own: as
>   features they only added false alarms and cut the shrinkage recall to 0.6.
>   Each tree draws up to 8,192 SKU-days instead of scikit-learn's 256, without
>   which the missing stock, 0 almost everywhere, was never split on.
> - The benchmark keeps the stock consistent with the changed demand and never
>   takes stock a later day does not have, so only shrinkage breaks the stock
>   balance; a SKU-day that cannot hold its kind gets a spike, or nothing when
>   spikes are not among the kinds.
> - `GET /api/v1/anomalies` answers 422 for a detector the guard refuses (a
>   single detector: there is no other row to show); in `score_detectors` a
>   failing detector is an error row, as planned.

Contract: [`interfaces.md`](interfaces.md) §6.

## Goal

Anomaly detectors are plug-ins over the combined daily state of each SKU,
and each is measured by how many injected anomalies it finds and how many of
its alarms are real.

## Scope

- **New `sdf.analytics.detectors`**: `DetectorInfo`, `SignalFrame`,
  `Detection`, `Detector`, `DetectorRegistry` over the new `sdf.detectors`
  group, `default_detectors()`, and `score_detectors` with the
  `anomaly-scores` table info.
- **New `sdf.simulation.signals`** with `signal_frame(world, policy=…)`,
  and `simulate_inventory(record=True)` with the new `on_hand` and
  `receipts` trace fields (§6.2). The frame is built in `simulation`, not in
  `analytics`, which may not import a world or a policy
  (`src/sdf/layering_test.py`); the detectors see only the `SignalFrame`.
- **Built-ins:** `seasonal-residual` (wrapping
  `seasonal_residual_anomalies`, not copying it) and `isolation-forest`.
- **`AnomalyBenchmark`** in `sdf.simulation.benchmark` (§6.3).
- **API:** `GET /api/v1/detectors` (the catalogue, the benchmark's
  parameters, the limits) and `GET /api/v1/anomalies?detector=…`.
  `/api/v1/demand-anomalies` is unchanged.
- **CLI:** `sdf anomalies [--detector NAME] [--benchmark] [--csv]`.
- **Hook markers.** `seasonal_residual_anomalies` keeps its
  `ALGORITHM-HOOK[C3]`; `isolation-forest` carries one (an autoencoder over
  real multi-sensor history).
- **Docs:** a new section in `docs/VALIDATION.md`, "Anomaly detection on
  injected anomalies", per detector and kind; checklist row C3; the plug-in
  guide gains a detector section.

## Tests

- The frame: `on_hand` follows the replay exactly (`on_hand` today = on hand
  yesterday + receipts − served demand); `record=False` leaves the trace as
  today.
- The benchmark: injected positions are where it says; a detector that
  returns exactly the injected set scores precision and recall 1; the empty
  detector scores recall 0 and empty precision.
- `seasonal-residual` gives the same anomalies as the function it wraps.
- `isolation-forest` finds `shrinkage`, which `seasonal-residual` cannot
  (recall 0 on that kind by construction).
- Both cuts (`threshold`, `top-k`) are reported; `top-k` ranks every
  SKU-day by `scores`, so a detector with no alarm still has a `top-k` row;
  ties are broken by SKU order and day.
- The registry refuses `scores` of the wrong shape or with a non-finite
  value, and a detection outside the frame.
- The API's 422 cases and a failing detector as an error row.
- The layering test passes: `sdf.analytics.detectors` imports nothing from
  `simulation`.

## Non-goals

- No change to `/api/v1/demand-anomalies`, the dashboard (PR 6) or the
  default detector.
- No sensor signals in the frame: the world's sensors belong to locations,
  not SKUs. A plug-in can add signals; the frame's type allows it.

## Acceptance

- The required checks of `AGENTS.md`, with `sdf demo` byte-identical to
  `main`.
- On the default world with the benchmark's defaults, the PR records
  precision and recall per detector and kind. `isolation-forest` must have a
  `shrinkage` recall of at least 0.8; on `spike` and `drop` it is reported,
  not required to win (the spike showed the single-series rule is stronger
  there).

## Version

`Version: MINOR 1.11.0 → 1.12.0` — detector plug-ins, the anomaly benchmark,
two endpoints and `sdf anomalies`.

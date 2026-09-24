# PR 5 — The detection test, and column kinds for synthetic tables

> Status: planned.

Contract: [`interfaces.md`](interfaces.md) §7.

## Goal

Every table evaluation says how easily synthetic rows can be told from real
ones (checklist B4), and the built-in table synthesizers stop giving
themselves away by writing whole numbers as decimals.

## Scope

- **New `sdf.validation.detection`** with `detection_report` (§7.3),
  on scikit-learn's `HistGradientBoostingClassifier` with stratified 5-fold
  cross-validation and permutation importance.
- **`TableData.kinds`** and `apply_kinds` (§7.2); the two built-in table
  synthesizers apply it; the retail feature table declares its kinds.
- **The evaluation:** `evaluate`, `POST /api/v1/synthesis/runs` and
  `sdf privacy` add the detection metrics next to the privacy ones.
- **Hook markers.** `detection_report` carries `ALGORITHM-HOOK[B4]` (a
  stronger discriminator, and a real holdout set), which gives row B4 its
  first code marker. The code index is regenerated.
- **Docs:** a new section in `docs/VALIDATION.md`, "Detection test", with the
  AUC per synthesizer and source before and after column kinds; checklist
  row B4 and the synthesis rows of the capability summary; the plug-in guide
  explains `kinds` and `apply_kinds` for table synthesizer authors.

## Tests

- Identical real and synthetic rows give an AUC near 0.5; rows from two
  clearly different distributions give an AUC near 1; the report is
  repeatable with the same seed.
- `apply_kinds`: integers rounded and clipped to the observed range,
  categories mapped to the nearest observed value, `kinds=None` unchanged.
- The built-ins with kinds produce only whole numbers in integer columns and
  only observed values in category columns.
- The evaluation answers carry the four new metrics; a plug-in synthesizer
  that ignores `kinds` still evaluates.

## Non-goals

- No new synthesizer. Whether a better one (CTGAN, a Bayesian network) is
  worth adding is decided on this PR's numbers, and deep models wait for D3.
- No change to the privacy metrics or to the series evaluation.
- No change to any recorded fidelity, TSTR or privacy number. The built-ins'
  output changes only for evaluations that declare kinds, and the recorded
  privacy numbers are measured without them; if a recorded number would
  change, the PR stops and says so.

## Acceptance

- The required checks of `AGENTS.md`, with `sdf demo` byte-identical to
  `main`.
- On the real extract, the detection AUC of both built-ins falls from about
  1.0 without kinds to under 0.75 with them. The PR records the numbers and,
  for the synthetic sample, which columns still give the rows away.

## Version

`Version: MINOR 1.12.0 → 1.13.0` — the detection test in every table
evaluation, and column kinds in the table synthesis contract.

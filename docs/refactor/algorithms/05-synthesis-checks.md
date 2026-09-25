# PR 5 — The detection test, and column kinds for synthetic tables

> Status: implemented. The numbers are in `docs/VALIDATION.md` ("Detection
> test"). **The acceptance target is met on the sample and not on the real
> extract:** the detection AUC falls from 1.00 to 0.55 (`bootstrap-table`)
> and 0.62 (`gaussian-copula`) on the sample, but only to 0.89 and 0.90 on
> the extract, against a target under 0.75. Column kinds cannot reach it
> there: the extract's real columns, each shuffled on its own, already score
> 0.78, and both built-ins sample without learning how price, quantity and
> hour depend on each other. The spike's 0.68 is not reproduced. Where the
> implementation departs from the contract, and why:
>
> - The retail feature table declares `price` a `category`, not `real`: with
>   the price a real number, the AUC only falls from 1.00 to 0.96–0.99, since
>   a price between two list prices gives the row away.
> - `detection_report` takes the column names as a keyword (`columns`), for
>   `top_features`; without them the columns are "column 1", "column 2", ….
>   With fewer rows than folds it returns `{"error": ...}`, and the
>   evaluation's metrics are then `None` with the reason as the verdict.
> - The evaluation adds a fifth metric, `detection_top_features` (the columns
>   joined by commas; the API's metrics are single values), for PR 6's
>   Synthesizers page.
> - The recorded privacy numbers change more than foreseen: clone risk 4.38 %
>   → 18.25 % on the sample and 7.62 % → 93.62 % on the extract, both now
>   "review". Half the real rows scored against the other half give 17.7 %
>   and 96.3 % (the mean of 10 random halvings), so on this discrete table
>   the jump is realism, not copying; `docs/VALIDATION.md` records both.

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
- **Recorded privacy numbers change, on purpose.** The retail feature table
  declares its kinds, and that table feeds the privacy report, so the
  built-ins' synthetic rows change and so do the privacy numbers recorded in
  `docs/VALIDATION.md` (today: clone risk 4.38 % on the sample and 7.62 % on
  the extract). This is the one exception in the sequence to "nothing
  recorded changes": keeping them would mean scoring privacy on rows the
  evaluation no longer produces. The PR regenerates them with
  `uv run sdf validate --update-doc docs/VALIDATION.md`, lists the old and
  new values side by side in its description and in the new "Detection
  test" section, and changes no other recorded number.
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
- No change to any recorded fidelity or TSTR number (series evaluations do
  not use `TableData`).

## Acceptance

- The required checks of `AGENTS.md`, with `sdf demo` byte-identical to
  `main`.
- On the real extract, the detection AUC of both built-ins falls from about
  1.0 without kinds to under 0.75 with them. The PR records the numbers and,
  for the synthetic sample, which columns still give the rows away.

## Version

`Version: MINOR 1.12.0 → 1.13.0` — the detection test in every table
evaluation, and column kinds in the table synthesis contract.

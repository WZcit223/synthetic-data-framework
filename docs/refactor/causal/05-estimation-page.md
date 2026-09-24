# PR 5 — Estimation on the Effects page, and estimators in the plug-in guide

> Status: implemented (causal modelling sequence PR 5). In Chromium, against an
> app with one runtime-registered estimator (`median-difference`) and without
> the `causal` extra:
> - At confounding 1 the view shows the numbers `sdf estimate` prints:
>   difference-in-means +36.5 (misses the truth +6.88), regression-adjustment
>   +6.29 and ipw +6.52 (both cover it).
> - Unchecking `log_demand` leaves regression adjustment near the truth
>   (+6.63), because `abc_class` is a proxy of demand; unchecking `abc_class`
>   too brings the naive bias back (+35.4, misses the truth). The acceptance
>   line below is corrected to name both, as PR 4 measured.
> - The sweep shows difference-in-means' bias growing from +6.4 at
>   confounding 0 to +44.5 at 3, while regression adjustment and ipw stay
>   within a few units of 0.
> - `median-difference` appears and runs with no UI change, drawn as a point
>   labelled "no interval"; DoWhy and EconML are listed "needs dowhy",
>   "needs econml".
> - The view reads without horizontal scrolling at 700, 1024 and 1440 px, with
>   no failed request and no console error. The estimator colours (the first
>   six series hues) pass the palette validator on the dark surface.
>
> The view lives on the Effects page as a second tab ("Estimate from data",
> address `#estimate=…`), so each view keeps its own study and link.

Contract: [`interfaces.md`](interfaces.md) §3.3 and §3.4.

## Goal

A user sees why the adjustment set matters. On the benchmark, every mounted
estimator is compared with the true effect as confounding grows. A developer
finds in the plug-in guide how to write, mount and score their own estimator.

## Scope

- **An "Estimate from data" view on the Effects page**, with pure helpers and
  their Node tests in `ui/effects-model.test.js` (the file PR 2 creates, found
  by `node --test ui/*.test.js`).
- **The form** is built from `GET /api/v1/estimators` (contract §3.4):
  - the mounted estimators, with the unavailable ones listed and their reason;
  - the benchmark's uplift, confounding, noise and seed, from its `benchmark.params`,
    with the bounds and defaults the server checks (the same `readParam` helper
    as the Synthesizers page);
  - the confidence;
  - the adjustment set, from `benchmark.question`'s covariates. The user can
    remove covariates to watch the bias return; the request sends the reduced
    `question`.
- **The result:**
  - **An interval chart.** One row per estimator: its estimate and interval,
    a reference line at the true effect, and a zero line. An interval that
    covers the truth is marked so in text, not only by colour. An estimator
    that gives no interval (both bounds empty, contract §3.1) is drawn as a
    point without a line and labelled "no interval". Its `covers` cell is
    empty. An error row is drawn as a text row with its message, with no
    point.
  - **A table:** estimate, interval, bias, relative bias, covers.
  - **A confounding sweep** (0 to 3, five steps) that draws each estimator's
    bias against confounding as lines, one colour per estimator in fixed
    order, with a legend and direct labels.
  - **Open in Explore** for the scores and for the benchmark's observed table.
    This adds the `estimates` source shape to Explore's validator and loader
    (exploration contract §3.2), with a round-trip Node test, and a test that
    `table: "data"` with a `dataset` request is refused.
- **The plug-in guide** (`docs/PLUGINS.md`) gains an estimator section:
  - the protocol, `design`, the `sdf.estimators` group, and how to score an
    estimator with `sdf estimate` and the API;
  - the time expectation: an estimator finishes in a few seconds at the
    published `max_rows`, because a request's 30 s budget is enforced only
    between estimators;
  - a worked example, run by `src/sdf/plugins_guide_test.py` as written.
- **UI contract test:** the page's new paths are covered.
- **Docs:** README and this plan's status note.

## Non-goals

- No backend change. If one is needed, it goes back to PR 4's contract first.
- No estimation on a user's own uploaded data.

## Acceptance

- The full check list of PR 1's acceptance, and `node --test ui/*.test.js`.
- In Chromium:
  - At confounding 1, the page shows the same numbers as `sdf estimate`.
  - Removing `log_demand` and `abc_class` (a proxy of demand) from the
    adjustment set brings back the naive bias; removing `log_demand` alone
    does not, which the view makes visible.
  - The sweep shows the naive estimator's bias growing with confounding.
  - A runtime-registered estimator appears and runs with no UI change.
  - Without the `causal` extra, DoWhy and EconML are listed with "needs …".
  - The page reads correctly from 700 to 1440 px.
  - There is no failed request and no console error.
- The estimator palette passes the palette validator on the dark surface.

## Version

`Version: none` — UI and documentation: neither `ui/` nor the guide is part of
the Python distribution.

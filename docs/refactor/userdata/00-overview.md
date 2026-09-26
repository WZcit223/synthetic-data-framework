# Your own data — overview

Status: proposed on 2026-09-26, at the project lead's request ("user's own
data, first"), and approved by the project lead the same day with the
recommended decisions: E1 (a), E2 as stated, and E3 (UCI Online Retail II
first, then M5; the committed daily table keeps 200 SKUs, about 4 MB). E4
was left to me and is decided below.

The interface contract every PR follows is [`interfaces.md`](interfaces.md).
Each PR has its own plan file (the sequence table's "Plan" column).

## Why

The project lead set two aims for this stage:

1. **The interfaces are complete, and every flow runs end to end as a user
   would run it.**
2. **The framework runs on real data, with real algorithms, as a demo.**

The algorithm phase showed that the *algorithm* half is open. A user's own
synthesizer, forecaster or detector mounts from an entry-point group and
reaches the catalogue, the API, the pages and the command line with nothing
naming it (`bayesian-network`, algorithm PR 5). The *data* half is not open.
Every flow reads data the framework chose:

- **Evaluation.** A synthesizer is evaluated only on the retail feature table
  (`qty`, `price`, `hour`, `weekday`) of an Online Retail II CSV, or on its
  demand series. The API and the pages offer only the two bundled files. The
  command line takes a path, but only in that layout. Column kinds are fixed
  by the framework (`FEATURE_KINDS`).
- **Forecasting and anomaly detection.** The API and the pages read the
  generated world or the demand benchmark. Only `sdf backtest CSV` reads a
  real file, and only in the retail layout.
- **The world.** It is always generated from a `GenerationSpec`. The
  dashboard, the replenishment comparison and the anomaly panel never see
  demand that really happened.
- **The table shape.** The retail table is also written into the run table's
  fields, Explore's synthesis presets and the Synthesizers page's score tiles.

So a user who brings a CSV can do nothing with it through the product. The
same gap blocks the second aim: real data cannot enter except as a file the
code already knows. Closing it once serves both aims. Real datasets become
ordinary sources, loaded through the same path a user's file takes, so the
demo is also the proof that the path works.

## The design: a data source

A **data source** (`source` in the API) is a CSV file plus a **schema**:

- the kind of each column: `id`, `category`, `integer`, `real`, `time`, `text`;
- optional **roles**, which say where the demand is: `time` (when), `item`
  (which SKU), `quantity` (how many), and optionally `price` and `cost` (per
  unit).

The schema is inferred when a file arrives, and the user confirms or corrects
it. Everything else follows from it:

| Flow | What a source gives it |
|---|---|
| Explore, causal estimation | the rows, as a dataset |
| Table synthesizers | the chosen columns, with the source's kinds, and the privacy and detection checks on them |
| Series synthesizers, forecasters, detectors | the demand: `quantity` summed by `item` and day of `time` |
| The world | real SKUs and real orders, cut to the busiest SKUs and a date window; locations, inventory, receipts and sensors synthesized around them |
| Replenishment | real demand, and real unit prices and costs when the roles are declared |

**Alternatives considered.**

- *One adapter per dataset* (what exists today, `retail_csv`). Every new file
  needs code, so a user cannot bring one. Kept only as the converter
  `sdf data fetch` uses for a known public dataset.
- *A fixed layout users convert to* (date, sku, quantity, price) before
  uploading. The work moves to the user, and every other column is lost to
  Explore and table synthesis.
- **Chosen: the file as it is, plus a schema.** The roles are exactly the
  mapping to that fixed layout, so the demand flows read one shape, but the
  user maps columns instead of rewriting the file, and every column stays
  available.

**Consequences.** The two bundled files become sources with declared schemas.
Their default runs keep today's readers, so no recorded number changes (U2).
A world from data has no `GenerationSpec`: the flows that regenerate a world
with changed parameters (spec-level scenarios, effect studies) refuse it,
with the reason, as they already refuse any world without a spec (U4).

## Sequence

Each PR passes the full gate (independent review, fixes, squash merge) before
the next one starts. A PR may refine its own plan file and `interfaces.md`;
the refinement is reviewed with it.

| # | Plan | Outcome | Version |
|---|---|---|---|
| U1 | [`01-sources.md`](01-sources.md) | **Sources.** A source store (`sdf.foundation.sources`): schema inference, checks, limits, safe uploads, the bundled files declared. `GET/POST/PUT/DELETE /api/v1/sources`, `sdf data add/list/show/remove`. Every source is a dataset in Explore and in causal estimation. | MINOR 1.13.0 → 1.14.0 |
| U2 | [`02-evaluation.md`](02-evaluation.md) | **Evaluation on any source.** A synthesizer run takes any source, a column choice and a row choice. Table runs use the source's columns and kinds; series runs use its demand. `--source`, `--columns`, `--param` on the command line. | MINOR → 1.15.0 |
| U3 | [`03-forecasts-anomalies.md`](03-forecasts-anomalies.md) | **Forecasts and anomalies on any source.** The backtest takes `source: {data: {name}}`; `GET /anomalies` takes `source=` (a demand-only frame). `--source` on `forecast`, `anomalies` and `backtest`. | MINOR → 1.16.0 |
| U4 | [`04-world-from-data.md`](04-world-from-data.md) | **A world from data.** `warehouse-from-demand`, fitted on a source's orders: the busiest real SKUs (at most 400) and their real orders over a date window (at most 730 days), with synthesized locations, inventory, receipts and sensors. `POST /api/v1/world {source}`. The dashboard, replenishment and its comparison, anomalies and exports run on real demand. | MINOR → 1.17.0 |
| U5 | [`05-data-page.md`](05-data-page.md) | **A Data page.** Upload a CSV, see a preview, confirm the kinds and roles, then use it: open it in Explore, pick it on the Synthesizers and Forecasts pages, or make it the world. | none (UI and documentation) |
| U6 | [`06-real-data.md`](06-real-data.md) | **Real data.** It replaces algorithm PR 7. `sdf data fetch NAME [--from FILE]` converts a public dataset and registers it (decision E3). The compact UCI daily table is committed as a bundled source (D1 (a)). Every algorithm is validated on real demand through the user's path, and CI checks the numbers. | MINOR → 1.18.0 |
| U7 | [`07-demo.md`](07-demo.md) | **The demo.** `sdf demo --source NAME` and `docs/DEMO.md`: load, explore, synthesize and check, forecast, replenish, detect, estimate an effect, on real data. | MINOR → 1.19.0 |

U1 to U4 give a user every flow through the API and the command line. U5
gives it to them in the browser. U6 brings real data in; U7 turns it into the
demo.

## Decisions for the project lead

- **E1. Where uploaded data lives.** (a) In the server's data directory
  (`$SDF_DATA_DIR/sources/`, default `./data/sources/`), one folder per source
  holding the CSV and its schema, gitignored. (b) A database.
  **Recommended: (a).** Files are what users bring, what the command line
  reads, and what the tests can create in a temporary folder. A database adds
  a service and changes nothing a user sees.
- **E2. Limits.** One upload at most 200 MB and 2,000,000 rows, 64 columns,
  and at most 20 user sources. A source over a limit is refused with the
  limits named. They are published by `GET /sources` and set by the store
  an app is built with, `create_app(sources=SourceStore(root, limits=…))`. **Recommended as stated.** The full UCI
  Online Retail II (1,067,371 rows, about 100 MB as CSV) fits; M5 fits after
  the conversion E3 describes.
- **E3. Which real data, from where.** This environment's network policy
  refuses `archive.ics.uci.edu`, `www.kaggle.com`, `zenodo.org` and
  `huggingface.co` today (checked: the proxy answers 403). Downloads need the
  hosts allowed in the environment's settings, and Kaggle also needs an API
  token as an environment secret and the competition's rules accepted on the
  site. Without them, `sdf data fetch NAME --from FILE` converts an archive
  the project lead downloaded, so no step depends on the network.

  | Dataset | What it holds | Licence | Fits the limits |
  |---|---|---|---|
  | UCI Online Retail II | 1,067,371 order lines of a UK online retailer, Dec 2009 – Dec 2011: invoice, SKU, quantity, time, unit price, customer, country | CC BY 4.0: any use, commercial included, with attribution | yes |
  | M5 Forecasting — Accuracy (Walmart, Kaggle) | daily unit sales of 3,049 products in 10 stores over 1,941 days, with weekly prices and a calendar | the competition's rules: no redistribution, and as I read them use for the competition and non-commercial research only | after conversion: sales summed over the stores per product and day, days without sales left out, the 1,000 products with the most units, prices averaged per product and week (under 1.94 M rows, 6 columns) |
  | Olist Brazilian e-commerce (Kaggle) | 100 k orders with items, prices, sellers and delivery dates | CC BY-NC-SA 4.0: non-commercial | yes, but 32 k products in 100 k orders give almost no demand per product; useful only for table synthesis |
  | Corporación Favorita (Kaggle) | 125 M daily sales lines of an Ecuadorian grocery chain | the competition's rules | no: 60 times the row limit |
  | Store Item Demand Forecasting (Kaggle) | 913,000 daily sales, 50 items × 10 stores | the competition's rules | yes, but it is widely reported to be simulated, so it does not serve "real data" |

  **Recommended:** UCI Online Retail II first, then M5 as the Kaggle dataset.
  This departs from "especially Kaggle" in the order only: UCI needs no token,
  its licence allows the proprietary use `pyproject.toml` declares, and it is
  the layout the framework already reads. M5 is the best-known real
  demand-forecasting competition, but its terms limit it to non-commercial
  research. It is fetched to the user's data directory and never committed,
  and its numbers enter `docs/VALIDATION.md` only after the project lead
  confirms the terms allow it. From UCI, as decision D1 (a) of the algorithm
  phase already settled, one compact table is committed with its
  attribution: the daily units and price of the SKUs with the most units,
  every day of the two years. It is a bundled source, `uci-retail-daily`,
  so continuous integration, the tests and the demo run on real demand with
  no download. The full order lines are never committed.

  **One correction to D1 (a), for your decision.** D1 estimated the table at
  "well under 1 MB" for 200 SKUs. Measured on a table of that shape, it is
  about 148,000 rows and **4 MB**; 1 MB holds about 50 SKUs. **Recommended:
  200 SKUs, 4 MB.** Fifty SKUs are too few for the replenishment comparison
  and the detectors to mean much, and 4 MB is five times the real extract
  already committed.
- **E4. The cost-based policy as the default.** The project lead left this to
  me. **Decided: `service-level-95` stays the default everywhere, and
  `cost-based` stays one click away in the comparison.** The cost-based
  policy's saving (49 % out of sample) comes mostly from ordering less often.
  It rests on the order cost (25 per order), the holding rate (25 % a year)
  and the lead time (7 days) that `CostModel` assumes, and on unit costs
  that the generator draws. A world from data does not remove those
  assumptions: UCI declares a price but no cost, and no dataset here carries
  order or holding costs. Making the policy the default would turn
  assumptions into the headline number of every page. The comparison already
  shows both policies side by side; U4 adds the assumptions it used to the
  comparison's answer, so a reader sees what the saving rests on. I'll
  revisit this when a source can declare its order and holding costs.

## Non-goals

- **No database, no user accounts, no access control.** A source is visible to
  whoever can reach the API, as every other endpoint is. Serving the API
  beyond one's own machine needs its own front door (`docs/ONBOARDING.md`).
- **No file formats but CSV** (UTF-8, comma or semicolon, a header row).
  Excel files are converted before upload; `sdf data fetch` converts what it
  downloads.
- **No spec-level scenarios or effect studies on a world from data.** They
  regenerate the world with changed generation parameters, which real demand
  does not have, and their replicates would vary only the synthesized parts.
  They keep running on generated worlds. Data-level interventions (dropping
  express orders, for example) already work on a world without a spec, and
  keep working. The demo's effect step is causal estimation on the source
  (U7).
- **No deep models or language model** (decisions D2 and D3 still hold).
- **No change to any recorded number or to `sdf demo`'s output.** The
  bundled sources' default runs keep today's readers, and the default world
  stays generated. Real-data numbers are added in their own section (U6),
  next to the existing ones.
- **No runtime plug-in loading into the served app.** Plug-ins are installed
  packages (the entry-point groups), as today.

## Version

Planned per PR in the sequence table. The plan PR itself:
`Version: none, documentation and plans only.`

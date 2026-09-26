# Your own data — overview

Status: proposed on 2026-09-26, at the project lead's request ("user's own
data, first"). Waiting for the project lead's approval and decisions E1 to E4.

The interface contract every PR follows is [`interfaces.md`](interfaces.md).

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
- **Forecasting and anomaly detection.** They read the generated world or the
  demand benchmark; there is no third source.
- **The world.** It is always generated from a `GenerationSpec`. The
  dashboard, the replenishment comparison, the effect studies and the anomaly
  panel never see demand that really happened.
- **The table shape.** The retail table is also written into the run table's
  fields, Explore's synthesis presets and the Synthesizers page's score tiles.

So a user who brings a CSV can do nothing with it through the product. The
same gap blocks the second aim: real data cannot enter except as a file the
code already knows. Closing it once serves both aims. Real datasets become
ordinary sources, loaded through the same path a user's file takes, so the
demo is also the proof that the path works.

## The idea: a data source

A **source** is a CSV file plus a **schema**:

- the kind of each column: `id`, `category`, `integer`, `real`, `time`, `text`;
- optional **roles**, which say where the demand is: `time` (when), `item`
  (which SKU), `quantity` (how many), and optionally `price` and `cost` (per
  unit).

The schema is inferred when a file arrives, and the user confirms or corrects
it. Everything else follows from it:

| Flow | What a source gives it |
|---|---|
| Explore | the rows, as a dataset to pivot |
| Table synthesizers | the chosen columns, with the source's kinds, and the privacy and detection checks on them |
| Series synthesizers, forecasters, detectors | the demand: `quantity` summed by `item` and day (or hour) of `time` |
| The world | real SKUs and real orders; locations, inventory, receipts and sensors synthesized around them by a warehouse synthesizer *fitted* on the source |
| Replenishment | real demand; real unit prices and costs when the roles are declared |

The two bundled files become sources with declared schemas, so every flow
that reads them today reads them through the same path.

## Sequence

Each PR passes the full gate (review, fixes, squash merge) before the next one
starts. Each PR's plan file is written, and reviewed with it, when it starts;
this overview fixes the scope, the contract and the order.

| # | Outcome | Version |
|---|---|---|
| U1 | **Sources.** A source store (`sdf.foundation.sources`): schema inference, checks and limits, the bundled files declared. `GET/POST/PUT/DELETE /api/v1/sources`, `sdf data add/list/show/remove`. Every source is a dataset in Explore. | MINOR 1.13.0 → 1.14.0 |
| U2 | **Evaluation on any source.** A synthesizer run takes any source and a column choice. Table runs use the source's columns and kinds; series runs use the demand its roles give. The run table's fields come from the source. The command line takes `--source`, `--columns` and `--param`. | MINOR → 1.15.0 |
| U3 | **Forecasts and anomalies on any source.** `POST /forecasts/backtest` takes `source: {data: id}`, and `GET /anomalies` takes `source=id` (a demand-only frame). The command line takes `--source`. | MINOR → 1.16.0 |
| U4 | **A world from data.** A warehouse synthesizer fitted on a source's demand, `warehouse-from-demand`: real SKUs and orders, with synthesized locations, inventory, receipts and sensors. `POST /api/v1/world` takes `source`. The dashboard, replenishment, the comparison, effects and anomalies run on real demand. Unit prices and costs come from the roles when declared. | MINOR → 1.17.0 |
| U5 | **A Data page.** Upload a CSV, see a preview, confirm the kinds and roles, then use it: open it in Explore, pick it on the Synthesizers and Forecasts pages, or make it the world. Every page's source picker lists every source. | none (UI and documentation) |
| U6 | **Real data and the demo.** It replaces algorithm PR 7. `sdf data fetch NAME` downloads a public dataset from its official host and registers it as a source (Decision E3). Every algorithm is then validated on real demand through the user's path. A demo walkthrough (`docs/DEMO.md` and `sdf demo --source`) runs the whole flow on it: load, explore, synthesize and check, forecast, replenish, detect, estimate an effect. | MINOR → 1.18.0 |

U1 to U4 give a user every flow through the API and the command line. U5
gives it to them in the browser. U6 turns it into the real-data demo.

## Decisions for the project lead

- **E1. Where uploaded data lives.** (a) In the server's data directory
  (`$SDF_DATA_DIR/sources/`, default `./data/sources/`), one folder per source
  holding the CSV and its schema. It is never committed; `data/sources/` is
  gitignored. (b) A database. **Recommended: (a).** Files are what users
  bring, what the command line reads, and what the tests can create in a
  temporary folder. A database adds a service and changes nothing a user
  sees.
- **E2. Limits.** One upload at most 200 MB and 2,000,000 rows, 64 columns,
  and at most 20 user sources. A source over a limit is refused with the
  limits named. **Recommended as stated.** The full UCI Online Retail II
  (about 1.07 million rows, roughly 100 MB as CSV) fits. The limits are
  published by `GET /sources` and set by `create_app(limits=…)`.
- **E3. Which real data, from where.** This environment's network policy
  refuses `archive.ics.uci.edu`, `www.kaggle.com`, `zenodo.org` and
  `huggingface.co` today. Downloads need the hosts allowed in the
  environment's settings, and Kaggle also needs an API token as an
  environment secret. The candidates, with their licences:

  | Dataset | What it holds | Licence | Host |
  |---|---|---|---|
  | UCI Online Retail II | 1.07 M order lines of a UK online retailer, 2009–2011: invoice, SKU, quantity, time, unit price, customer, country | CC BY 4.0 (may be shared, with attribution) | `archive.ics.uci.edu` |
  | M5 Forecasting (Walmart, Kaggle) | daily unit sales of 3,049 products in 10 stores over 5.4 years, with prices and a calendar | the competition's rules: download after accepting them, no redistribution | `www.kaggle.com` |
  | Brazilian e-commerce by Olist (Kaggle) | 100 k orders with items, prices, sellers and delivery dates | CC BY-NC-SA 4.0 | `www.kaggle.com` |
  | Corporación Favorita (Kaggle) | 125 M daily sales lines of an Ecuadorian grocery chain | the competition's rules | `www.kaggle.com` |

  **Recommended:** UCI Online Retail II first (it is the layout the adapter
  already reads, and its licence lets a compact daily table be committed, as
  decision D1 (a) allowed), then M5 as the second demo, kept outside the
  repository (fetched, never committed). `sdf data fetch` records each
  dataset's source URL, licence and download date in the source's schema and
  in `docs/DATASETS.md`.
- **E4. The cost-based policy as the default.** The project lead left this to
  me. **Decided: the default stays `service-level-95` for a generated world.**
  The cost-based policy's saving (49 % out of sample) rests on unit costs the
  framework assumed (`DEFAULT_UNIT_COST`, `DEFAULT_UNIT_PRICE`). Making it the
  default would turn an assumption into the headline number of every page,
  and change every recorded number with it. It stays one click away in the
  comparison. **On a world from data whose source declares `price` or `cost`
  (U4), the cost-based policy becomes that world's default,** because its
  costs are then real. This is recorded in U4's plan.

## Non-goals

- **No database, no user accounts, no access control.** A source is visible to
  whoever can reach the API, as every other endpoint is. Serving the API
  beyond one's own machine needs its own front door (`docs/ONBOARDING.md`).
- **No file formats but CSV** (UTF-8, comma or semicolon, a header row).
  Excel files are converted before upload; `sdf data fetch` converts what it
  downloads.
- **No deep models or language model** (decisions D2 and D3 still hold).
- **No change to any recorded number or to `sdf demo`'s output** until U4.
  From U4 on, recorded numbers change only where a PR says so and why. The
  default world stays generated, so `sdf demo` without `--source` is unchanged
  throughout.
- **No runtime plug-in loading into the served app.** Plug-ins are installed
  packages (the entry-point groups), as today.

## Version

Planned per PR in the sequence table. The plan PR itself:
`Version: none, documentation and plans only.`

# Your own data — interface contract

The contract every PR of [`00-overview.md`](00-overview.md) follows. Each
section says which PR brings it. Examples are the shapes the code and the API
will have; names may still be refined in a PR's own plan, which then updates
this file in the same PR.

## 1. The source (U1)

### 1.1 Schema

```python
from sdf.foundation.sources import ColumnSpec, Roles, SourceSchema

SourceSchema(
    name="uci-online-retail-ii",            # lower-case words joined by dashes; the source's id
    label="UCI Online Retail II",
    columns=(
        ColumnSpec("Invoice", "id"),
        ColumnSpec("StockCode", "category"),
        ColumnSpec("Description", "text"),
        ColumnSpec("Quantity", "integer"),
        ColumnSpec("InvoiceDate", "time", format="%m/%d/%Y %H:%M"),  # strptime format; None: ISO 8601
        ColumnSpec("Price", "real"),
        ColumnSpec("Customer ID", "id"),
        ColumnSpec("Country", "category"),
    ),
    roles=Roles(time="InvoiceDate", item="StockCode", quantity="Quantity", price="Price"),  # all optional
    provenance={"url": "...", "licence": "CC BY 4.0", "fetched": "2026-09-26"},  # optional, free text values
)
```

- **Kinds.**
  - `id`: an identifier (never aggregated, never a model feature);
  - `category`: a few repeated labels;
  - `integer` and `real`: numbers;
  - `time`: a date or a timestamp;
  - `text`: free text (shown, never modelled).

  A table synthesizer receives the `integer`, `real` and `category` columns
  as numbers. A `category` column holding text is coded to 0, 1, … in first-seen
  order, and decoded back in the run table, so a synthesizer never sees text.
  `TableData.kinds` carries `integer`, `real` and `category` as in algorithm
  PR 5.
- **Roles** name columns. `quantity` must be `integer` or `real`, `time` must
  be `time`, and `item` is `category` or `id`. `price` and `cost` must be
  `real` or `integer`. A source has **demand** when `time` and `quantity` are
  declared. Without `item`, all rows are one series.
- **Inference** (`infer_schema(path) -> SourceSchema`). It reads the header
  and up to 10,000 rows:
  - a column whose values all parse as numbers is `integer` or `real`;
  - one whose values all parse as dates or times (ISO 8601, then the formats
    the retail adapter knows) is `time`;
  - otherwise it is `category` when it has at most 1,000 distinct values and
    fewer than half the rows, `id` when nearly every value is distinct, and
    `text` when its values are long.

  Roles are guessed from the column names:
  - `time`: date, time, day, timestamp, invoicedate;
  - `item`: sku, item, product, stockcode, article;
  - `quantity`: quantity, qty, units, sales, demand;
  - `price`: price, unitprice;
  - `cost`: cost, unitcost.

  The guess is only a proposal; the user confirms it (U5) or passes it
  (`sdf data add --role …`).
- **Checks** (`SourceSchema.check(path)`). Every row is read once when a
  source is added or its schema changed. A value that does not parse as its
  column's kind is counted per column, with the first three examples. A
  source whose `quantity` or `time` column cannot be read on more than 5 % of
  its rows is refused, naming the column; below that, the rows are skipped
  and the report says how many. The report is kept with the source.

### 1.2 Store

```python
from sdf.foundation.sources import SourceStore, SourceLimits

store = SourceStore(root="data/sources", bundled=BUNDLED, limits=SourceLimits())
store.list() -> list[SourceEntry]          # bundled first, then the user's, by name
store.get(name) -> SourceEntry              # schema, row count, load report, origin ("bundled" | "user"), path
store.add(path_or_bytes, schema=None, name=None) -> SourceEntry   # schema None: inferred; ValueError with the reason
store.update_schema(name, schema) -> SourceEntry                  # re-checked; bundled sources are read-only
store.remove(name)                          # user sources only
store.rows(name, *, columns=None, limit=None) -> Table             # typed values, time as ISO strings
store.demand(name, *, grain="day") -> DemandTable                  # needs the time and quantity roles
store.orders(name) -> tuple[list[SKU], list[OutboundOrder]]         # needs time, item and quantity (U4)
```

- One folder per user source: `<root>/<name>/data.csv` and `schema.json`.
  The name is checked against `^[a-z0-9]+(-[a-z0-9]+)*$`, so no path is ever
  built from user text.
- **Bundled sources** are the two sample files, with declared schemas
  (`sample`, `retail-10k`). They are read-only, and today's evaluation and
  recorded numbers read them unchanged.
- **Limits** (`SourceLimits`, decision E2):
  - an upload is at most 200 MB and 2,000,000 rows;
  - at most 64 columns;
  - at most 20 user sources.
- `demand` sums `quantity` by `item` and day (or hour), with negative
  quantities treated as returns and left out, as the retail adapter does. It
  returns the `DemandTable` every forecaster and detector already reads.

### 1.3 HTTP

```
GET    /api/v1/sources                     → {sources: [SourceEntry], limits: SourceLimits}
GET    /api/v1/sources/{name}              → SourceEntry + {preview: {fields, rows}} (first 50 rows)
POST   /api/v1/sources?name=my-sales       body: the CSV (text/csv), at most the limit
                                           → 201 SourceEntry (schema inferred) | 413 too large | 422 unreadable
PUT    /api/v1/sources/{name}/schema       body: SourceSchema → SourceEntry (re-checked) | 422 with the report
DELETE /api/v1/sources/{name}              → 204 | 404 | 409 (bundled)
```

- Every source is also a dataset: `GET /api/v1/datasets` lists it as
  `source:<name>`, with fields built from its schema. `id` and `category`
  columns become dimensions, `integer` and `real` columns measures, `time`
  columns time fields; `text` columns are left out of the fields.
  `GET /api/v1/datasets/source:<name>` returns the rows. Explore needs no
  change beyond listing them.
- `GET /api/v1/synthesis/sources` is kept for existing callers, and lists the
  same sources.

### 1.4 Command line

```bash
uv run sdf data add sales.csv --name my-sales \
    --role time=OrderDate --role item=Sku --role quantity=Units --kind Store=category
uv run sdf data list
uv run sdf data show my-sales        # schema, row count, load report, first rows
uv run sdf data remove my-sales
```

## 2. Evaluation on any source (U2)

```json
POST /api/v1/synthesis/runs
{"synthesizer": "bayesian-network", "source": "my-sales",
 "columns": ["Units", "Price", "Store"], "params": {"bins": 20}}
```

- **A table synthesizer** is fitted on `columns`, or by default on every
  `integer`, `real` and `category` column, at most 3,000 rows as today. It is
  then scored with the privacy and detection checks on those columns. The run
  table's fields are the columns, labelled from the schema, plus `origin`.
- **A series synthesizer** is fitted on the source's demand, summed over
  items, by day. A source without demand is refused (422) with the reason.
- The retail feature table of the two bundled files is their declared default
  column choice (`qty`, `price`, `hour`, `weekday` stay what they are today),
  so every recorded number is unchanged.
- Command line: `sdf privacy --source NAME [--columns a,b] [--param k=v]`,
  `sdf synth --source NAME [--param k=v]`, `sdf tstr --source NAME`. A path is
  still accepted and read as an unnamed source with an inferred schema.

## 3. Forecasts and anomalies on any source (U3)

```json
POST /api/v1/forecasts/backtest
{"forecasters": ["seasonal-naive", "gradient-boosting"], "source": {"data": {"name": "my-sales"}}, ...}
```

```
GET /api/v1/anomalies?detector=seasonal-residual&source=my-sales
```

- A backtest on a source reads its demand, at most `max_skus` items (the
  items with the most units first).
- Anomalies on a source read a frame with the `demand` signal only. A
  detector that needs stock (`isolation-forest`) is refused on such a source
  (422, naming the signals it lacks), which is the guard's existing rule. On
  a world from data (§4), every signal is there.
- Command line: `sdf forecast --source NAME`, `sdf anomalies --source NAME`.

## 4. A world from data (U4)

```json
POST /api/v1/world
{"source": "my-sales", "seed": 7}
```

- A warehouse synthesizer fitted on a source's orders, `warehouse-from-demand`,
  follows the synthesizer contract with `produces="warehouse"`. Its `fit`
  receives an `OrdersData(skus, orders)`, and its `sample` returns a
  `SyntheticWarehouse`:
  - **Kept from the data:** the real SKUs (id; category from a declared column
    or "unknown"; unit price from `price`, else the median line price) and
    the real outbound orders.
  - **Synthesized:** locations (as today); inventory sized from each SKU's
    demand (on hand drawn around the service-level policy's order-up-to level
    at the last day); inbound orders; sensor readings.
- The world's label names the source (`source:my-sales`). Its `spec` holds
  the seed and the source's dates; `n_skus` and `horizon_days` are read from
  the data.
- Every flow that reads the world reads real demand from then on: the
  dashboard, replenishment and the comparison, experiments and effect studies,
  anomalies (with every signal), exports. A regeneration from a spec returns
  to a generated world.
- **Decision E4:** on a world from data whose source declares `price` or
  `cost`, the replenishment plan's default policy is `cost-based`, with those
  unit prices and costs. Elsewhere it stays `service-level-95`.

## 5. The Data page (U5)

`ui/data.html`, the sixth page:

- **Upload** (drag a file or choose one). The server infers the schema, and the
  page shows the preview and every column's kind and role as a choice. On
  saving, the schema is `PUT` and the check's report is shown.
- **A list of every source**, with rows, dates and demand (yes or no). For
  each: open in Explore, run a synthesizer on it, backtest forecasters on it,
  and make it the world.
- The Synthesizers and Forecasts pages list every source in their pickers, and
  their links carry the source's name, so a link reproduces the run on that
  source.

## 6. Real data and the demo (U6)

```bash
uv run sdf data fetch uci-online-retail-ii     # downloads from the official host, converts, registers
uv run sdf demo --source uci-online-retail-ii  # the whole flow on real demand, printed step by step
```

- `sdf data fetch` knows each public dataset's official URL, licence and
  conversion. It records them in the source's `provenance` and in
  `docs/DATASETS.md`, and fails with the host named when the network refuses
  it.
- The validation that algorithm PR 7 planned runs on this source through the
  same calls a user makes: every forecaster's backtest, the replenishment
  comparison out of sample, the detectors, and the synthesizers' privacy and
  detection. Results go in `docs/VALIDATION.md` ("Real demand"), and results
  that contradict the benchmarks are reported, not hidden.
- `docs/DEMO.md` is the walkthrough, with the commands, the pages and what to
  look at in each.

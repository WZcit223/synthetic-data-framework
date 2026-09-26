# Your own data — interface contract

The contract every PR of [`00-overview.md`](00-overview.md) follows. Each
section says which PR brings it. Examples are the shapes the code and the API
will have; names may still be refined in a PR's own plan, which then updates
this file in the same PR.

**Terms.** A *data source* (`source`) is a CSV plus its schema (§1). The word
already names other things, which keep their meaning: the Explore link's
`source`, the forecast backtest's `source` (`world`, `benchmark`, and from U3
`data`), and `EvaluationRun.source`. Where a source is one choice among
others, it is written `{"data": {"name": …}}`.

## 1. The source (U1)

### 1.1 Schema

```python
from sdf.foundation.sources import ColumnSpec, Roles, SourceSchema

SourceSchema(
    name="uci-online-retail-ii",            # lower-case words joined by dashes; the source's id
    label="UCI Online Retail II",
    columns=(
        ColumnSpec("Invoice", "id"),
        ColumnSpec("StockCode", "id"),
        ColumnSpec("Description", "text"),
        ColumnSpec("Quantity", "integer"),
        ColumnSpec("InvoiceDate", "time", formats=("%Y-%m-%d %H:%M:%S",)),  # strptime formats tried in order; () = ISO 8601 only
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
  - `category`: repeated labels;
  - `integer` and `real`: numbers;
  - `time`: a date or a timestamp;
  - `text`: free text (shown, never modelled).

  A blank cell is a missing value in every kind. A table synthesizer receives
  the `integer`, `real` and `category` columns as numbers (U2).
- **Roles** name columns. `quantity` must be `integer` or `real`, `time` must
  be `time`, and `item` is `category` or `id`. `price` and `cost` must be
  `real` or `integer`. A source has **demand** when `time` and `quantity` are
  declared. Without `item`, all rows are one series.
- **Inference** (`infer_schema(path) -> SourceSchema`). It reads the header
  and up to 10,000 rows, and ignores blank cells. The rules run in this
  order, and the first that fits decides:
  1. a column whose values all parse as dates or times is `time`. The
     formats tried are ISO 8601, then the formats the retail adapter knows.
     When a day-first and a month-first reading both fit every sampled
     value, the column is marked **ambiguous**, and the schema cannot be
     saved until the user picks one;
  2. a column whose name suggests an identifier (`id`, `code`, `no`,
     `number`, `invoice`, `customer`, `zip`, `postcode`, as a word of the
     name split at spaces, underscores and capitals) is `id`, even when its
     values look like numbers;
  3. a column whose values are whole numbers or text codes without spaces,
     and more than 95 % distinct, is `id`. Real numbers are never `id` by
     this rule;
  4. a column whose values all parse as numbers is `integer` or `real`;
  5. a column whose values contain spaces and have more than 100 distinct
     values, or a median over 40 characters, is `text`;
  6. otherwise `category`, whatever the number of distinct values.

  Roles are guessed from the column names:
  - `time`: date, time, day, timestamp, invoicedate, orderdate;
  - `item`: sku, item, product, stockcode, article;
  - `quantity`: quantity, qty, units, sales, demand;
  - `price`: price, unitprice;
  - `cost`: cost, unitcost.

  The guess is only a proposal; the user confirms it (U5) or passes it
  (`sdf data add --role …`).
- **Delimiter and numbers.** A comma or a semicolon delimiter is detected
  from the header. With a semicolon, a decimal comma (`3,5`) is read as a
  decimal point. Thousands separators are not supported; such values do not
  parse.
- **Checks** (`SourceSchema.check(path)`). Every row is read once when a
  source is added or its schema changed. A value that does not parse as its
  column's kind is counted per column, with the first three examples. A
  source whose `quantity` or `time` column cannot be read on more than 5 % of
  its rows is refused, naming the column; below that, the rows are skipped
  and the report says how many. Blank cells are counted apart and are not
  errors. The report is kept with the source.

### 1.2 Store

```python
from sdf.foundation.sources import SourceStore, SourceLimits

store = SourceStore(root="data/sources", bundled=BUNDLED, limits=SourceLimits())
store.list() -> list[SourceEntry]          # bundled first, then the user's, by name
store.get(name) -> SourceEntry              # schema, row count, date range, load report, origin ("bundled" | "user")
store.add(stream, *, name, schema=None) -> SourceEntry            # schema None: inferred; ValueError with the reason
store.update_schema(name, schema) -> SourceEntry                  # re-checked; bundled sources are read-only
store.remove(name)                          # user sources only
store.rows(name, *, columns=None, limit=None, seed=None) -> Table  # typed values; limit with seed: a uniform sample
store.orders(name) -> tuple[list[SKU], list[OutboundOrder]]         # needs time, item and quantity
```

The store is in the foundation layer, so it returns only foundation types
(tables, and the `SKU` and `OutboundOrder` entities). Demand is built one
layer up, in `sdf.analytics.demand`:

```python
source_demand(store, name) -> DemandTable    # DemandTable.from_orders over store.orders(name)
```

- One folder per user source: `<root>/<name>/data.csv` and `schema.json`.
- **Names.** The name is checked against `^[a-z0-9]+(-[a-z0-9]+)*$`, at most
  40 characters, so no path is ever built from user text. The names of the
  bundled sources (`sample`, `retail-10k`, and from U6 `uci-retail-daily`) are
  reserved. A name is required;
  the page proposes one from the file name.
- **Bundled sources** are the two sample files, with declared schemas. They
  are read-only.
- **Limits** (`SourceLimits`, decision E2):
  - an upload is at most 200 MB and 2,000,000 rows;
  - at most 64 columns;
  - at most 20 user sources.
- **Adding safely.** The upload is streamed to a temporary file in `<root>`
  with a byte counter, and refused (and the file deleted) as soon as it
  passes the limit, whether or not a length was declared. It is checked, then
  moved into place with one rename. Adding and removing hold one store lock,
  so the source count and the name are checked and taken together; a second
  add of a name already present is refused.
- **Orders and demand.** `orders` reads lines as the retail adapter does: a
  negative quantity is a return, kept as a cancelled line; a zero quantity
  is skipped. A source without `item` gives one SKU, `all`. `source_demand`
  sums the orders that are not cancelled by SKU and day, into the daily
  `DemandTable` every forecaster and detector already reads.

### 1.3 HTTP

```
GET    /api/v1/sources                     → {sources: [SourceEntry], limits: SourceLimits}
GET    /api/v1/sources/{name}              → SourceEntry + {preview: {fields, rows}} (first 50 rows)
POST   /api/v1/sources?name=my-sales       body: the CSV (text/csv), streamed
                                           → 201 SourceEntry (schema inferred) | 409 name taken or reserved
                                             | 413 over a limit | 422 unreadable
PUT    /api/v1/sources/{name}/schema       body: SourceSchema → SourceEntry (re-checked) | 422 with the report
DELETE /api/v1/sources/{name}              → 204 | 404 | 409 (bundled, or read by the current world: checked by the API, which holds the world)
```

- The served app's CORS setting allows `PUT` and `DELETE` as well as `GET`
  and `POST`, so a page hosted elsewhere can use them.
- **Every source is also a dataset**, listed by `GET /api/v1/datasets` as
  `source-<name>`. The `source-` prefix is reserved: a dataset plug-in with
  that prefix is refused when the catalogue is built. The API merges the
  store's datasets with the catalogue's; the catalogue's entry-point
  registry is unchanged.
  - **Fields.** Each column's name becomes a `lower_snake_case` field name
    (`InvoiceDate` → `invoice_date`, `Customer ID` → `customer_id`); a
    collision gets `_2`, `_3`. The field's label is the column's own name.
    `id` and `category` columns become dimensions, `integer` and `real`
    columns measures; a dimension's values are written as text (`12`, not
    `12.0`). A `time` column becomes a date field, plus a dimension
    `<field>_hour` (its values `00` to `23`) when the column holds times.
    `text` columns are left out.
  - **Rows.** `GET /api/v1/datasets/source-<name>` returns at most
    `MAX_DATASET_ROWS` (250,000) rows and at most 2,000,000 cells, so a
    wide source returns fewer rows; a larger source answers a seeded uniform
    sample, and the answer says so, with the source's row count.
  - **One merge.** The catalogue's datasets and the store's are merged by one
    function in the application layer, `datasets(catalogue, store)`, which
    the API and the command line both call.
  - **Causal estimation.** `POST /causal/estimates` reads the merged list,
    so a source is also an estimation dataset, within the estimators' own
    limits (at most `MAX_ESTIMATE_ROWS`, 40,000 rows, and a two-valued
    treatment). U7 uses this for the demo's effect step.
- `GET /api/v1/synthesis/sources` is kept and lists the same sources. The API
  is published as v1, so removing it would be a MAJOR change; the pages move
  to `/sources` in U5.
- **Exports.** Server-side CSV (`/export`, `sdf export`, every `--csv`
  option) prefixes a text cell that starts with `=`, `+`, `-`, `@`, a tab or
  a carriage return with `'`, the same characters the pages' `csvCell`
  guards, because sources bring user text. Numbers are written unchanged.

### 1.4 Command line

```bash
uv run sdf data add sales.csv --name my-sales \
    --role time=OrderDate --role item=Sku --role quantity=Units \
    --kind Store=category --time-format OrderDate=%d/%m/%Y
uv run sdf data list
uv run sdf data show my-sales        # schema, row count, date range, load report, first rows
uv run sdf data remove my-sales
```

## 2. Evaluation on any source (U2)

```json
POST /api/v1/synthesis/runs
{"synthesizer": "bayesian-network", "source": "my-sales",
 "columns": ["Units", "Price", "Store", "OrderDate.hour"], "rows": "sample",
 "params": {"bins": 20}}
```

- **A table synthesizer** is fitted on `columns`, by default every `integer`,
  `real` and `category` column. Two derived columns of the `time` role may be
  named: `<time>.hour` (integer) and `<time>.weekday` (category). Rows with a
  missing chosen value, or a chosen `quantity` or `price` column at or below
  zero, are left out. At most 3,000 rows are used: `rows: "sample"` (the
  default) is a uniform sample drawn with the run's seed; `rows: "first"`
  takes the first rows.
- **Categories.** A `category` column holding text is coded 0, 1, … from the
  most frequent label down (ties in first-seen order), and decoded back in
  the run table, so a synthesizer never sees text. The Gaussian copula and
  the privacy and detection distances read these codes as ordered numbers;
  the run's answer says so when a category column with more than two labels
  is chosen. The Bayesian network reads labels as labels.
- **A series synthesizer** is fitted as today, through `FittedHourlyDemand`:
  the source's orders (not cancelled), summed over items into an hourly
  series in business hours. A source without demand is refused (422) with
  the reason, and so is one whose `time` column holds dates without times of
  day, which cannot give an hourly series. A daily grain for series
  synthesizers is not part of this sequence.
- **The bundled sources keep today's readers.** With no `columns` given,
  `sample` and `retail-10k` run the retail feature table exactly as today
  (`qty`, `price`, `hour`, `weekday`; positive quantity and price; the first
  3,000 rows), and their series runs read the retail adapter's orders as
  today, so their answers, and every recorded number, are unchanged. A
  column choice on a bundled source takes the path above.
- The run table's fields are the columns, named as in §1.3, plus `origin`.
- Command line: `sdf privacy --source NAME [--columns a,b] [--rows sample|first]
  [--param k=v]`, `sdf synth --source NAME [--param k=v]`,
  `sdf tstr --source NAME`. A path is still accepted, read as today, with
  `--date-format`.

## 3. Forecasts and anomalies on any source (U3)

```json
POST /api/v1/forecasts/backtest
{"forecasters": ["seasonal-naive", "gradient-boosting"], "source": {"data": {"name": "my-sales"}}, ...}
```

```
GET /api/v1/anomalies?detector=seasonal-residual&source=my-sales
```

- A backtest on a source reads its daily demand: at most `MAX_FORECAST_SKUS`
  (400) items, those with the most units first. The world path keeps its
  rule, the first 400 SKUs in order of appearance: a generated world has at
  most 500 SKUs, and changing the rule would change recorded numbers. A
  world from data is cut to at most 400 SKUs (§4), so the rule never drops
  one there. A source whose demand spans
  fewer days than the backtest needs is refused with the days it has and
  needs, as the benchmark is.
- Anomalies on a source read a frame with the `demand` signal only. A
  detector that needs stock (`isolation-forest`) is refused on such a source
  (422, naming the signals it lacks), which is the guard's existing rule. On
  a world from data (§4), every signal is there.
- Command line: `sdf forecast --source NAME`, `sdf anomalies --source NAME`.
  `sdf backtest CSV` keeps working and also takes `--source NAME`.

## 4. A world from data (U4)

```json
POST /api/v1/world
{"source": "my-sales", "max_skus": 200, "days": 365, "seed": 7}
```

- **The new input and a minimal synthesizer.** A warehouse synthesizer that
  is fitted on data receives the orders it keeps:

  ```python
  @dataclass(frozen=True)
  class OrdersData:                      # sdf.synthesis.api, next to SeriesData and TableData
      skus: tuple[SKU, ...]              # the cut's SKUs, prices and costs set as below
      orders: tuple[OutboundOrder, ...]  # their outbound orders in the window, returns as cancelled lines
      label: str                         # names the source and the cut, for the world's label

  class OrdersOnly:
      """The smallest OrdersData synthesizer: the real SKUs and orders, nothing around them."""
      info = SynthesizerInfo(name="orders-only", produces="warehouse", needs_fit=True,
                             description="the real SKUs and orders; no stock, locations or sensors")

      def fit(self, data: OrdersData) -> "OrdersOnly":
          self._data = data
          return self

      def sample(self, n: int | None = None) -> SyntheticWarehouse:
          d = self._data
          return SyntheticWarehouse(skus=list(d.skus), locations=[], inventory=[], inbound=[],
                                    outbound=list(d.orders), sensors=[], spec=None)
  ```

  `orders-only` is a test fixture and the example in the plug-in guide; it
  is not registered. The built-in is **`warehouse-from-demand`**
  (`produces="warehouse"`, `needs_fit=True`), which synthesizes the rest.
- **`SyntheticWarehouse.spec`** becomes `GenerationSpec | None`; U4 checks
  every reader of it. A world from data is built by its own function,
  `build_registry_from_source(store, name, cut, seed, synthesizer=
  "warehouse-from-demand")`, which reads the orders, fits and samples.
  `build_registry`, and so `POST /world {spec, synthesizer}`, refuses a
  warehouse synthesizer with `needs_fit=True` (422: "fitted on a source; use
  `{source}`"), and the dashboard's generator picker leaves such
  synthesizers out (U5).
- **The cut.** The world keeps the `max_skus` SKUs with the most units
  (default 200, at most 400, the forecast backtest's `MAX_FORECAST_SKUS`, so
  no later step drops one) over the last `days` days of the source (default
  365, at most 730). The cut is recorded in the world's label:
  `source:my-sales top 200 SKUs, 2010-12-09 to 2011-12-09`.
- **Kept from the data:** the SKUs' ids and their outbound orders in the
  window. For each SKU:
  - `category`: from a declared column, else `unknown`;
  - `abc_class`: from its units, A for the SKUs that make the first 80 % of
    units, B for the next 15 %, C for the rest;
  - `unit_price`: the median positive `price` of its lines; without a price
    role, 1.0, and the world is marked as having assumed prices;
  - `unit_cost`: the median positive `cost` of its lines; without a cost role,
    0.6 × the unit price, as the retail adapter does, marked as assumed.

  Lines with a price at or below zero are left out of the medians.
- **Synthesized, seeded:** locations and their capacities, sized from the
  SKUs' demand so shelf occupancy stays in the range of a generated world;
  inventory (on hand drawn around the `service-level-95` order-up-to level on
  the first day); inbound receipts; sensor readings.
- **Stand-ins marked.** The synthesized parts carry `ALGORITHM-HOOK`
  markers, and the assumed prices and costs `DATA-HOOK` markers, each with
  its checklist row, as every other stand-in does (invariant 1).
- **No spec.** The world's `spec` is `None`, and it records its source and
  cut instead. The flows that regenerate a world from its spec refuse it
  with the reason: `POST /experiments` and `POST /effects` already answer
  422 for a world without a spec; `GET /scenarios` answers 500 today (its
  `ValueError` is not caught), and U4 makes it 422. Data-level interventions
  keep working. `POST /world` with a spec and
  no synthesizer, while the current world is from data, generates with
  `warehouse-spec`.
- **Everything that reads the current world reads real demand:** the
  dashboard, replenishment and its comparison, anomalies (every signal), the
  exports and the agent. The replenishment comparison's answer lists the
  cost assumptions it used (order cost, holding rate, lead time, and whether
  prices and costs are assumed). The default policy stays `service-level-95`
  (decision E4).
- **The comparison's holdout.** `GET /replenishment/comparison` takes
  `holdout_days` (default 30, today's `HOLDOUT_DAYS`, so today's answers are
  unchanged; at most half the world's days): the policies' levels are set
  on the days before, and their cost is replayed on the last `holdout_days`.
  U6 uses it to fit on the first year and replay the second.
- Command line: `export`, `pipeline`, `agent` and `anomalies` take
  `--source NAME [--max-skus N] [--days N]`. `scenarios`, `effects` and
  `impact` refuse a source with the reason.

## 5. The Data page (U5)

`ui/data.html`, the sixth page:

- **Upload** (drag a file or choose one), with a name proposed from the file
  name. The server infers the schema, and the page shows the preview and
  every column's kind and role as a choice. An ambiguous date format must be
  picked. On saving, the schema is `PUT` and the check's report is shown.
- **A list of every source**, with rows, dates and demand (yes or no). For
  each: open in Explore, run a synthesizer on it, backtest forecasters on it,
  make it the world, and remove it.
- The Synthesizers and Forecasts pages list every source in their pickers
  (from `/sources`), and their links carry the source's name, so a link
  reproduces the run on that source.
- On a world from data, the dashboard names the source and cut, labels the
  synthesized panels (shelf occupancy, stocktake, sensors) as synthesized,
  and shows the scenarios panel's refusal as its reason. The generator
  picker leaves out warehouse synthesizers that need fitting.
- The pages' `api()` helper accepts an answer with no body (204).

## 6. Real data (U6)

```bash
uv run sdf data fetch uci-online-retail-ii                  # download from the official host, convert, register
uv run sdf data fetch uci-online-retail-ii --from ~/Downloads/online+retail+ii.zip   # no network
uv run sdf data fetch m5 --from ~/Downloads/m5-forecasting-accuracy.zip
```

- `sdf data fetch` knows each public dataset's official URL, licence and
  conversion, and records them in the source's `provenance` and in
  `docs/DATASETS.md`. It fails with the host named when the network refuses
  it, and says how to use `--from`.
- **Conversions.**
  - UCI Online Retail II ships as an Excel workbook in a zip. It is read
    with `openpyxl` (a new extra, `data`), written as one CSV, and the
    non-product codes (postage, bank charges, manual adjustments and the
    like) are left out. The list of codes is recorded in the provenance.
  - M5: sales summed over the stores per product and day, days without
    sales left out, the 1,000 products with the most units kept, prices
    averaged per product and week (decision E3).
- **The committed table** (decision D1 (a) of the algorithm phase).
  `sdf data fetch uci-online-retail-ii --compact` also writes
  `data/uci_retail_daily.csv` (date, sku, units, price): the daily units
  and median price of the SKUs with the most units, every day of the two
  years (0 on a day without sales), with the attribution in
  `docs/DATASETS.md`. It is the third bundled source, `uci-retail-daily`,
  with a declared schema. Its size is decision E3's: 200 SKUs are about
  148,000 rows and 4 MB; 50 SKUs are about 1 MB. A test pins its shape and
  totals. The full order lines and M5 are never committed.
- **Validation.** It runs on the real sources through the same calls a user
  makes: every forecaster's backtest, the replenishment comparison on a
  world from data with `holdout_days=365` (levels set on the first year,
  cost replayed on the second), the detectors, and the synthesizers'
  privacy and detection. The numbers on `uci-retail-daily` from algorithms
  that need no optional extra are a new section of the generated block of
  `docs/VALIDATION.md`, "Real demand", so `sdf validate` recomputes them and
  CI checks them (`golden_test.py` is extended). Numbers that need an extra
  (`gradient-boosting` with LightGBM), or the full order lines, or M5, are
  recorded by hand beside it, with the fetch date and the commands. Results
  that contradict the benchmarks are reported, not hidden.

## 7. The demo (U7)

```bash
uv run sdf demo --source uci-retail-daily   # the whole flow on real data, printed step by step; no download needed
```

- `sdf demo` without `--source` is unchanged, byte for byte.
- With `--source`, it runs, and prints, each step a user takes: the source's
  schema and load report; the demand; a table synthesizer's privacy and
  detection; the forecasters' backtest; a world from data and its
  replenishment comparison; the detectors; and an effect estimated on real
  data.
- **The effect step** asks: *does a price cut raise the units sold?* U7
  adds a derived dataset, `source-<name>-price-weeks`, for a source with
  time, item, quantity and price roles: one row per SKU and week (for
  `uci-retail-daily`, about 200 × 106 = 21,000 rows, under the 40,000 the
  estimators take). Its treatment is 1 when the week's median price is at
  least 5 % under the SKU's median price; its outcome is the week's units;
  its covariates are the SKU's mean weekly units over the 4 weeks before and
  the week of the year. The estimators run on it through the same function
  as `POST /causal/estimates`. The answer is observational: the demo says
  that it assumes no unmeasured cause of both price and units (promotions,
  stock-outs), and shows the estimators' spread, not one number.
- `docs/DEMO.md` walks through the same steps on the pages, with what to look
  at in each.

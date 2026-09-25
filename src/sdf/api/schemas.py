"""Request and response models of the ``/api/v1`` contract.

Each model declares the fields a client may rely on, so ``/api/v1/openapi.json``
describes them; ``extra="allow"`` passes any further fields through unchanged,
so adding a field to a response is not a breaking change. Fields that are absent
when there is too little data (for example a backtest on a very short series)
are optional.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from sdf.simulation.effects import MAX_REPLICATES


class Model(BaseModel):
    model_config = ConfigDict(extra="allow")


# -- world ----------------------------------------------------------------------------------


class Health(Model):
    status: str


class WorldSummary(Model):
    source_count: int
    by_entity: dict[str, int]
    by_origin: dict[str, int]


class CurrentWorld(WorldSummary):
    """``GET /world``: the current world's sources and the warehouse generator that built it."""

    synthesizer: str


class Range(Model):
    min: int
    max: int


class WorldLimits(Model):
    n_skus: Range
    horizon_days: Range


class WorldSpec(Model):
    n_skus: int
    horizon_days: int
    daily_orders_per_a_sku: float
    stockout_pressure: float
    seed: int


class WorldGenerated(Model):
    ok: bool
    spec: WorldSpec
    generated_ms: int
    synthesizer: str  # the warehouse generator that built the world


class Quality(Model):
    mode: str
    passed: bool
    checks: dict[str, bool]
    metrics: dict[str, float]
    notes: list[str]


# -- application ----------------------------------------------------------------------------


class KPIs(Model):
    total_skus: int
    total_on_hand: int
    inventory_value: float
    outbound_lines: int
    cancel_rate: float
    express_rate: float


class Overview(Model):
    kpis: KPIs
    abc: dict[str, int]
    insights: list[str]
    anomalies_sample: list[dict[str, Any]]
    foundation: WorldSummary
    quality: Quality


class ReplenishmentRow(Model):
    sku_id: str
    name: str
    avg_daily_demand: float
    demand_std: float
    variability: float
    intermittent: bool
    safety_stock: float
    reorder_point_s: float
    order_up_to_S: float
    available: int
    order_qty: int


class Replenishment(Model):
    service_level: float
    z: float
    lead_time_days: int
    review_days: int
    skus_needing_order: int
    intermittent_needing_order: int
    total_safety_stock_units: float
    rows: list[ReplenishmentRow]


class PolicyMetrics(Model):
    policy: str
    skus_needing_order: int
    safety_stock_units: float
    intermittent_needing_order: int
    unmet_units: float
    fill_rate: float
    holding_cost: float
    order_cost: float
    lost_margin: float
    # out of sample: levels from all but the last `holdout_days`, costs on those days; absent on a short history
    holdout_unmet_units: float | None = None
    holdout_fill_rate: float | None = None
    holdout_holding_cost: float | None = None
    holdout_order_cost: float | None = None
    holdout_lost_margin: float | None = None
    holdout_total_cost: float | None = None


class ReplenishmentComparison(Model):
    service_level: float
    horizon_days: int
    holdout_days: int | None = Field(
        None, description="the days the holdout_* metrics are measured on; null when the history is too short"
    )
    policies: list[PolicyMetrics]


class TopMover(Model):
    sku_id: str
    name: str
    abc_class: str
    avg_daily_demand: float


class DemandPoint(Model):
    date: str
    qty: int


class ForecastDay(Model):
    date: str
    mean: float
    low: float
    high: float


class SkuForecast(Model):
    forecaster: str
    level: float = Field(description="the central interval's probability: 0.8 is the 10 % to 90 % quantiles")
    days: list[ForecastDay]


class DemandSeries(Model):
    sku_id: str
    history: list[DemandPoint]
    forecast_avg_daily: float = Field(
        description="Deprecated: the trailing 14-day mean; use `forecast`, the fitted forecast with its interval"
    )
    forecast_horizon_days: int
    forecast_total: float = Field(description="Deprecated: forecast_avg_daily × the horizon; use `forecast`")
    forecast: SkuForecast


class DemandAnomaly(Model):
    index: int
    value: float
    expected: float
    robust_z: float
    direction: str


class DemandAnomalies(Model):
    granularity: str
    seasonal_period: int
    series_len: int
    count: int
    anomalies: list[DemandAnomaly]


class ShelfCell(Model):
    location_id: str
    occupancy: float
    book_units: int
    est_units: int


class ShelfAisle(Model):
    aisle: str
    cells: list[ShelfCell]


class ShelfZone(Model):
    zone: str
    aisles: list[ShelfAisle]


class Discrepancy(Model):
    location_id: str
    book_units: int
    vision_units: int
    diff: int
    direction: str


class Stocktake(Model):
    locations_scanned: int
    matched: int
    flagged: int
    match_rate: float
    net_unit_variance: int
    discrepancies: list[Discrepancy]


class BacktestResult(Model):
    model: str
    MAE: float
    RMSE: float
    MAPE_pct: float | None = None  # n/a when no test day has positive demand
    WAPE_pct: float | None = None
    bias: float


class Backtest(Model):
    granularity: str
    seasonal_period: int
    series_len: int
    series_mean: float | None = None
    best_model: str | None = None
    results: list[BacktestResult] = []
    error: str | None = None  # set instead of results when the series is too short


class Answer(Model):
    intent: str
    answer: str


# -- agent, economics, workflow, scenarios -------------------------------------------------------


class RunSummary(Model):
    run_id: str
    steps: int
    ok: int
    errors: int
    total_ms: int


class TraceEntry(Model):
    seq: int
    name: str
    status: str
    duration_ms: int
    note: str = ""


class ProposedAction(Model):
    """A call held for approval: the action, its arguments and its status."""

    proposed_action: str
    status: str
    sku_id: str | None = None  # the arguments of a place_order proposal
    quantity: int | None = None


class AgentAnswer(Model):
    query: str | None
    answer: str
    plan: list[str]
    proposed_actions: list[ProposedAction]
    requires_approval: bool
    run: RunSummary
    trace: list[TraceEntry]


class ToolInfo(Model):
    name: str
    description: str
    read_only: bool
    requires_approval: bool


class AgentTools(Model):
    tools: list[ToolInfo]


class Economics(Model):
    assumptions: dict[str, float] | None = None
    skus_considered: int | None = None
    horizon_days: int | None = None
    unmet_units: dict[str, int] | None = None
    stockout_units_avoided: int | None = None
    period: dict[str, int] | None = None
    annualised_net_saving: int | None = None
    error: str | None = None  # set instead of the figures when the world has no demand


class WorkflowRun(Model):
    pipeline: str
    order: list[str]
    run: RunSummary
    trace: list[TraceEntry]


class ScenarioRow(Model):
    scenario: str
    outbound_lines: int
    inventory_value: float
    skus_needing_order: int
    safety_stock_units: float
    active_stockouts: int
    safety_stock_vs_baseline_pct: float


class Scenarios(Model):
    service_level: float
    scenarios: list[ScenarioRow]


# -- tables ----------------------------------------------------------------------------------


class FieldModel(Model):
    """A table column: dimension (group by it), time (an ISO date) or measure (a number)."""

    name: str
    label: str
    kind: Literal["dimension", "time", "measure"]
    unit: str | None = None
    aggregate: Literal["sum", "mean", "min", "max"] | None = None


class DatasetEntry(Model):
    name: str
    label: str
    description: str
    origin: Literal["builtin", "plugin", "runtime"]
    fields: list[FieldModel]


class DatasetList(Model):
    datasets: list[DatasetEntry]
    unavailable: dict[str, str]


class DatasetTable(Model):
    """One dataset over the current world; each row is an array in field order."""

    name: str
    label: str
    world: str
    fields: list[FieldModel]
    rows: list[list[Any]]
    total_rows: int
    truncated: bool


# -- experiments ------------------------------------------------------------------------------


class PolicyChoice(BaseModel):
    """A built-in policy: ``naive``, ``service-level`` (with its service level) or ``cost-based``."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["naive", "service-level", "cost-based"]
    service_level: float = Field(0.95, gt=0.5, lt=1.0)
    lead_time_days: int = Field(7, ge=1, le=90)
    review_days: int = Field(7, ge=1, le=90)


MAX_PER_LIST = 6  # interventions, policies and outcomes per experiment


class ExperimentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    interventions: list[str] = Field(default_factory=lambda: ["baseline"], min_length=1, max_length=MAX_PER_LIST)
    policies: list[PolicyChoice] = Field(min_length=1, max_length=MAX_PER_LIST)
    outcomes: list[str] = Field(min_length=1, max_length=MAX_PER_LIST)


class OutcomeRowModel(Model):
    intervention: str
    policy: str
    metric: str
    value: float


class ExperimentResult(Model):
    rows: list[OutcomeRowModel]
    fields: list[FieldModel]


class ParamModel(Model):
    """One parameter a form can set: its type, default and bounds (``null`` when unbounded)."""

    name: str
    type: Literal["int", "float", "str", "bool"]
    default: Any = None
    min: int | float | None = None
    max: int | float | None = None
    exclusive: bool = False  # the bounds themselves are not allowed
    nullable: bool = False


class PolicyKind(Model):
    kind: str
    params: list[ParamModel]


class EffectsLimits(Model):
    max_replicates: int  # the form's input bound; the work budget is the server's (POST /effects check_only)


class ExperimentCatalog(Model):
    interventions: list[str]
    policies: list[PolicyKind]
    outcomes: list[str]
    max_per_list: int
    effects: EffectsLimits


class EffectsRequest(BaseModel):
    """An effect study: every intervention against the baseline, over paired replicate worlds."""

    model_config = ConfigDict(extra="forbid")

    interventions: list[str] = Field(min_length=1, max_length=MAX_PER_LIST)
    policies: list[PolicyChoice] = Field(
        default_factory=lambda: [PolicyChoice(kind="service-level")], min_length=1, max_length=MAX_PER_LIST
    )
    outcomes: list[str] = Field(default_factory=lambda: ["simulated_cost"], min_length=1, max_length=MAX_PER_LIST)
    replicates: int = Field(10, ge=2, le=MAX_REPLICATES)
    confidence: float = Field(0.95, gt=0.5, lt=1.0)
    check_only: bool = False  # validate and answer the budget, generating nothing


class TableModel(Model):
    fields: list[FieldModel]
    rows: list[list[Any]]


class EffectsResult(Model):
    fields: list[FieldModel]
    rows: list[list[Any]]
    replicates: TableModel
    spec: dict[str, Any]  # the spec replicate 0 used: the current world's
    synthesizer: str
    elapsed_ms: int


class EffectsBudget(Model):
    work: int
    max_work: int
    within_budget: bool
    size: str


# -- synthesis --------------------------------------------------------------------------------


class SynthesizerEntry(Model):
    name: str
    produces: Literal["warehouse", "series", "table"]
    needs_fit: bool
    origin: Literal["builtin", "plugin", "runtime"]
    description: str
    requires: list[str]
    params: list[ParamModel]  # what a run may set; a warehouse generator's spec comes from the world request


class SynthesizerList(Model):
    synthesizers: list[SynthesizerEntry]
    unavailable: dict[str, str]  # declared synthesizers that could not be mounted, with the reason


class SynthesisSource(Model):
    id: str
    label: str


class SynthesisSources(Model):
    sources: list[SynthesisSource]


class SynthesisRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    synthesizer: str
    source: str  # a source ID from GET /synthesis/sources; never a path
    params: dict[str, Any] = Field(default_factory=dict)


class SynthesisRunResult(Model):
    """One run: every parameter it used, its scores, and the real and synthetic data as a table."""

    synthesizer: str
    source: str
    kind: Literal["series", "table"]
    params: dict[str, Any]
    repeatable: bool  # the same params give the same table: the synthesizer has a seed
    metrics: dict[str, float | int | str | None]
    fields: list[FieldModel]
    rows: list[list[Any]]


# -- causal estimates -------------------------------------------------------------------------

MAX_ESTIMATORS = 6  # estimators per request


class EstimatorEntry(Model):
    name: str
    description: str
    origin: Literal["builtin", "plugin", "runtime"]
    requires: list[str]  # modules it needs; already importable, since it is mounted
    uses_covariates: bool


class EstimateLimits(Model):
    max_rows: int  # MAX_ESTIMATE_ROWS: rows read from a dataset, before the missing-value rule
    max_estimators: int
    max_seconds: float  # MAX_ESTIMATE_SECONDS: estimators not started by then are "not run" rows


class QuestionModel(BaseModel):
    """A causal question: the treatment and outcome fields, the adjustment set, the treated value."""

    model_config = ConfigDict(extra="forbid")

    treatment: str
    outcome: str
    covariates: list[str] = []
    treated_value: str | int = 1  # text for a dimension treatment; 0 or 1 for a 0/1 measure


class BenchmarkSpec(Model):
    params: list[ParamModel]  # uplift, confounding, noise, seed, with the bounds PromotionBenchmark checks
    question: QuestionModel  # the benchmark's question; a request may only drop covariates from it


class EstimatorList(Model):
    estimators: list[EstimatorEntry]
    unavailable: dict[str, str]
    limits: EstimateLimits
    benchmark: BenchmarkSpec


class BenchmarkRequest(BaseModel):
    """The promotion benchmark's parameters. Their bounds are checked by PromotionBenchmark itself (422)."""

    model_config = ConfigDict(extra="forbid")

    uplift: float = 0.3
    confounding: float = 1.0
    noise: float = 0.25
    seed: int = 7


class EstimatesRequest(BaseModel):
    """Estimators on the promotion benchmark, or on a catalogue dataset over the current world."""

    model_config = ConfigDict(extra="forbid")

    estimators: list[str] = Field(min_length=1, max_length=MAX_ESTIMATORS)
    benchmark: BenchmarkRequest | None = None
    dataset: str | None = None
    question: QuestionModel | None = None  # required with a dataset; with the benchmark, may drop covariates
    confidence: float = 0.95  # above 0.5, below 1: checked as the estimators check it (422)


class EstimatesResult(Model):
    fields: list[FieldModel]
    rows: list[list[Any]]
    question: QuestionModel
    true_effect: float | None  # the benchmark's exact effect; null for a dataset
    data: TableModel | None = None  # the benchmark's observed rows, for Explore; null for a dataset
    source: str  # "promotion-benchmark" or the dataset's name
    world: str  # the label of the world the rows came from
    elapsed_ms: int


# -- forecasting -------------------------------------------------------------------------------

MAX_FORECAST_SKUS = 400  # SKUs one backtest reads from the world or draws from the benchmark


class ForecasterEntry(Model):
    name: str
    description: str
    origin: Literal["builtin", "plugin", "runtime"]
    requires: list[str]  # modules it needs; already importable, since it is mounted
    global_model: bool  # one model over all SKUs, or one per SKU
    params: list[ParamModel]


class ForecastLimits(Model):
    max_forecasters: int
    max_horizon: int
    max_origins: int
    max_quantiles: int
    max_skus: int  # MAX_FORECAST_SKUS
    max_seconds: float  # MAX_BACKTEST_SECONDS: forecasters not started by then are "not run" rows
    min_history: int  # days of history before the first origin


class DemandBenchmarkSpec(Model):
    params: list[ParamModel]  # with the bounds DemandBenchmark checks


class ForecasterList(Model):
    forecasters: list[ForecasterEntry]
    unavailable: dict[str, str]
    limits: ForecastLimits
    benchmark: DemandBenchmarkSpec


class DemandBenchmarkRequest(BaseModel):
    """The demand benchmark's parameters. Their bounds are checked by DemandBenchmark itself (422)."""

    model_config = ConfigDict(extra="forbid")

    n_skus: int = 200
    days: int = 365
    intermittent_share: float = 0.3
    promo_rate: float = 0.03
    promo_uplift: float = 0.6
    dispersion: float = 2.0
    seed: int | None = None


class WorldSource(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ForecastSource(BaseModel):
    """Exactly one of ``world`` (the current world's demand) and ``benchmark`` (a declared process)."""

    model_config = ConfigDict(extra="forbid")

    world: WorldSource | None = None
    benchmark: DemandBenchmarkRequest | None = None


class ForecastBacktestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    forecasters: list[str] = Field(min_length=1)  # at most max_forecasters, checked with the rest (422)
    params: dict[str, dict[str, Any]] = {}
    source: ForecastSource = ForecastSource(world=WorldSource())
    horizon: int = 14
    origins: int = 4
    step: int = 7
    quantiles: list[float] = [0.1, 0.5, 0.9]
    refit: Literal["each-origin", "once"] = "each-origin"


class ForecastBacktestResult(Model):
    scores: TableModel  # "forecast-scores": one row per forecaster, then "true-distribution" on the benchmark
    by_horizon: TableModel  # "by-horizon"
    forecasts: TableModel  # "forecasts": the last origin only
    origins: list[str]  # the first forecast day of each origin, ISO dates
    source: str  # "world" or "demand-benchmark"
    world: str | None  # the label of the world the demand came from; null for the benchmark
    skus: int  # SKUs scored
    elapsed_ms: int


# -- anomaly detectors (docs/refactor/algorithms/interfaces.md §6) ------------------------------------


class DetectorEntry(Model):
    name: str
    description: str
    origin: Literal["builtin", "plugin", "runtime"]
    requires: list[str]  # modules it needs; already importable, since it is mounted
    signals: list[str]  # the signals of the frame it reads
    params: list[ParamModel]


class DetectorLimits(Model):
    max_detectors: int  # detectors one benchmark scoring takes


class AnomalyBenchmarkSpec(Model):
    params: list[ParamModel]  # with the bounds AnomalyBenchmark checks
    kinds: list[str]  # the anomalies it can inject


class DetectorList(Model):
    detectors: list[DetectorEntry]
    unavailable: dict[str, str]
    limits: DetectorLimits
    signals: list[str]  # the signals of the world's frame
    benchmark: AnomalyBenchmarkSpec


class AnomaliesResult(Model):
    """One detector's detections on the current world's frame, highest score first."""

    detector: str
    world: str
    fields: list[FieldModel]
    rows: list[list[Any]]  # sku_id, date, score, direction, signals
    elapsed_ms: int

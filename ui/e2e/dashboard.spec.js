import { test } from "@playwright/test";

import { smoke } from "./smoke.js";

test("the dashboard loads and makes its API calls", async ({ page }) => {
  await smoke(page, "/index.html", [
    "GET /api/v1/backtest",
    "GET /api/v1/demand-anomalies",
    "GET /api/v1/demand-series?sku_id=SKU-00040",
    "GET /api/v1/economics",
    "GET /api/v1/overview",
    "GET /api/v1/replenishment/comparison?service_level=0.95",
    "GET /api/v1/replenishment?service_level=0.95",
    "GET /api/v1/scenarios",
    "GET /api/v1/shelf-occupancy",
    "GET /api/v1/stocktake",
    "GET /api/v1/synthesizers",
    "GET /api/v1/top-movers?n=8",
    "GET /api/v1/workflow/run",
    "GET /api/v1/world",
    "GET /api/v1/world/limits",
  ]);
});

import { expect, test } from "@playwright/test";

import { smoke } from "./smoke.js";

const CALLS = [
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
];

// The card whose heading starts with `title`.
const card = (page, title) => page.locator(".card", { has: page.getByRole("heading", { name: title }) });

test("the dashboard loads and makes its API calls", async ({ page }) => {
  await smoke(page, "/index.html", CALLS);
});

for (const colorScheme of ["light", "dark"]) {
  test(`the dashboard loads without errors in the ${colorScheme} theme`, async ({ page }) => {
    await page.emulateMedia({ colorScheme });
    await smoke(page, "/index.html", CALLS);
  });
}

test("the dashboard shows the numbers the API returned", async ({ page, request }) => {
  const overview = await (await request.get("/api/v1/overview")).json();
  const backtest = await (await request.get("/api/v1/backtest")).json();
  const plan = await (await request.get("/api/v1/replenishment?service_level=0.95")).json();
  await page.goto("/index.html", { waitUntil: "networkidle" });

  const n = v => v.toLocaleString("en-US", { maximumFractionDigits: 2 });
  await expect(page.locator(".kpi", { hasText: "Total SKUs" }).locator(".v")).toHaveText(n(overview.kpis.total_skus));
  await expect(page.locator(".kpi", { hasText: "Units on hand" }).locator(".v")).toHaveText(n(overview.kpis.total_on_hand));
  await expect(page.locator(".kpi", { hasText: "Cancel rate" }).locator(".v")).toHaveText((overview.kpis.cancel_rate * 100).toFixed(1) + "%");

  const models = card(page, /Forecast backtest/).locator(".tabulator-row .tabulator-cell:first-child");
  await expect(models).toHaveText(backtest.results.map(r => (r.model === backtest.best_model ? "🏆 " : "") + r.model));
  const mae = card(page, /Forecast backtest/).locator('.tabulator-row .tabulator-cell[tabulator-field="MAE"]');
  await expect(mae).toHaveText(backtest.results.map(r => n(r.MAE)));

  const planCard = card(page, /\(s, S\) inventory optimisation/);
  await expect(planCard.locator(".tabulator-row").first()).toBeVisible();
  const skus = await planCard.locator('.tabulator-row .tabulator-cell[tabulator-field="sku_id"]').allTextContents();
  expect(skus.slice(0, 5)).toEqual(plan.rows.slice(0, 5).map(r => r.sku_id));
});

test("choosing a SKU redraws its demand chart", async ({ page }) => {
  await page.goto("/index.html", { waitUntil: "networkidle" });
  const select = page.getByLabel("SKU shown in the demand chart");
  const second = await select.locator("option").nth(1).getAttribute("value");
  const series = page.waitForResponse(r => r.url().includes(`/demand-series?sku_id=${second}`));
  await select.selectOption(second);
  const answer = await (await series).json();
  const meta = page.getByTestId("series-meta");
  await expect(meta).toContainText(`(${answer.history.length} days with demand in the history)`);
  // the fitted forecast the API returned, summed over its days
  const total = Math.round(answer.forecast.days.reduce((s, d) => s + d.mean, 0)).toLocaleString();
  await expect(meta).toContainText(`Forecast (${answer.forecast.forecaster}) ≈ ${total} units over the next ${answer.forecast.days.length} days`);
});

test("a table sorts by the column clicked, and the other way on a second click", async ({ page }) => {
  await page.goto("/index.html", { waitUntil: "networkidle" });
  const planCard = card(page, /\(s, S\) inventory optimisation/);
  const header = planCard.locator('.tabulator-col[tabulator-field="order_qty"]');
  const orders = async () => (await planCard.locator('.tabulator-row .tabulator-cell[tabulator-field="order_qty"]').allTextContents())
    .map(c => Number(c.replaceAll(",", "")));
  const sorted = (xs, dir) => xs.every((x, i) => i === 0 || (dir === "asc" ? xs[i - 1] <= x : xs[i - 1] >= x));

  await header.click();
  const once = await orders();
  const dir = sorted(once, "asc") ? "asc" : "desc";
  expect(sorted(once, dir)).toBe(true);
  await header.click();
  const twice = await orders();
  expect(sorted(twice, dir === "asc" ? "desc" : "asc")).toBe(true);
  expect(twice).not.toEqual(once);
});

test("each slider's label and the regenerate request say what the slider holds", async ({ page }) => {
  await page.goto("/index.html", { waitUntil: "networkidle" });
  const sliders = page.locator('.ctrl input[type="range"]');
  const held = [];
  for (let i = 0; i < await sliders.count(); i++) {
    const slider = sliders.nth(i);
    const value = await slider.inputValue();
    held.push(Number(value));
    await expect(slider.locator("xpath=..").locator("output")).toHaveText(new RegExp(`^${Number(value)}(\\.0+)?$`));
  }
  const post = page.waitForRequest(r => r.url().endsWith("/api/v1/world") && r.method() === "POST");
  await page.getByRole("button", { name: /Regenerate/ }).click();
  const body = (await post).postDataJSON();
  expect([body.n_skus, body.horizon_days, body.daily_orders_per_a_sku, body.stockout_pressure, body.seed]).toEqual(held);
});

test("a table header from the API is shown as text", async ({ page }) => {
  await page.goto("/index.html", { waitUntil: "networkidle" });
  const titles = card(page, /Policy comparison/).locator(".tabulator-col-title");
  await expect(titles).toHaveText(["Metric", "naive", "service-level-95"]);
});

test("at 390 px the dashboard does not overflow sideways", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 800 });
  await page.goto("/index.html", { waitUntil: "networkidle" });
  const [scroll, inner] = await page.evaluate(() => [document.documentElement.scrollWidth, window.innerWidth]);
  expect(scroll).toBeLessThanOrEqual(inner);
});

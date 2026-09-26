import { expect, test } from "@playwright/test";

import { smoke } from "./smoke.js";

const BACKTEST = "/api/v1/forecasts/backtest";
// a small benchmark backtest: the reference row, and an answer in about a second
const LINKED = { forecasters: ["seasonal-naive", "moving-average"], params: { "moving-average": { window: 14 } }, source: "benchmark",
  benchmark: { n_skus: 20, days: 120, intermittent_share: 0.3, promo_rate: 0.03, promo_uplift: 0.6, dispersion: 2, seed: 3 },
  horizon: 7, origins: 2, level: 0.9 };
const linkedHash = "#backtest=" + encodeURIComponent(JSON.stringify(LINKED));

test("the Forecasts page loads and makes its API calls", async ({ page }) => {
  await smoke(page, "/forecasts.html", ["GET /api/v1/forecasters"]);
});

for (const colorScheme of ["light", "dark"]) {
  test(`a backtest shows the scores the API returned, in the ${colorScheme} theme`, async ({ page }) => {
    await page.emulateMedia({ colorScheme });
    await page.goto("/forecasts.html", { waitUntil: "networkidle" });
    const answer = page.waitForResponse(r => r.url().endsWith(BACKTEST));
    await page.getByRole("button", { name: "Run backtest" }).click();
    const body = await (await answer).json();
    const table = page.locator(".section", { hasText: "Scores" }).locator(".tabulator");
    await expect(table.locator(".tabulator-row")).toHaveCount(body.scores.rows.length);
    const first = body.scores.rows[0];
    await expect(table.locator(".tabulator-row").first()).toContainText(first[0]);
    await expect(table.locator(".tabulator-row").first()).toContainText(`${(first[1] * 100).toFixed(1)} %`); // WAPE
    await expect(page.locator(".multiple")).toHaveCount(body.scores.rows.length); // one chart per forecaster
    await expect(page).toHaveURL(/#backtest=/);
  });
}

test("a link with a request runs it once, with the benchmark's reference row", async ({ page }) => {
  let posts = 0;
  page.on("request", r => { if (r.method() === "POST" && r.url().endsWith(BACKTEST)) posts++; });
  const answer = page.waitForResponse(r => r.url().endsWith(BACKTEST));
  await page.goto("/forecasts.html" + linkedHash);
  const body = await (await answer).json();
  expect(body.source).toBe("demand-benchmark");
  await expect(page.getByText("true-distribution (reference)")).toBeVisible();
  await expect(page.locator("#f-moving-average-window")).toHaveValue("14");
  await expect(page.locator("#level")).toHaveValue("0.9");
  await page.waitForLoadState("networkidle");
  expect(posts).toBe(1);
});

test("a link naming a forecaster this installation lacks says so and runs nothing", async ({ page }) => {
  let posted = false;
  page.on("request", r => { if (r.method() === "POST") posted = true; });
  await page.goto("/forecasts.html#backtest=" + encodeURIComponent(JSON.stringify({ forecasters: ["prophet", "mean"] })), { waitUntil: "networkidle" });
  await expect(page.locator(".notice.bad")).toContainText("prophet");
  expect(posted).toBe(false);
});

for (const [link, table, preset] of [
  ["Open scores in Explore", "scores", "Error, interval and run time by forecaster"],
  ["Open scores by days ahead in Explore", "by_horizon", "Mean error over the days ahead by forecaster"],
  ["Open the forecasts in Explore", "forecasts", "Forecast demand by day and forecaster"],
]) {
  test(`"${link}" opens the ${table} table in Explore`, async ({ page }) => {
    const answer = page.waitForResponse(r => r.url().endsWith(BACKTEST));
    await page.goto("/forecasts.html" + linkedHash);
    await answer;
    const href = await page.getByRole("link", { name: link }).getAttribute("href");
    const view = JSON.parse(decodeURIComponent(href.replace("explore.html#view=", "")));
    expect(view.source.forecasts.table).toBe(table);
    await page.getByRole("link", { name: link }).click();
    await expect(page.locator(".preset[aria-pressed=true]")).toHaveText(preset, { timeout: 30_000 });
  });
}

test("at 390 px the Forecasts page does not overflow sideways", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 800 });
  const answer = page.waitForResponse(r => r.url().endsWith(BACKTEST));
  await page.goto("/forecasts.html" + linkedHash);
  await answer;
  await expect(page.locator(".multiple").first()).toBeVisible();
  const [scroll, inner] = await page.evaluate(() => [document.documentElement.scrollWidth, window.innerWidth]);
  expect(scroll).toBeLessThanOrEqual(inner);
});

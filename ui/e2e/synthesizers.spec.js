import { expect, test } from "@playwright/test";

import { smoke } from "./smoke.js";

test("the Synthesizers page loads and makes its API calls", async ({ page }) => {
  await smoke(page, "/synthesizers.html", ["GET /api/v1/synthesis/sources", "GET /api/v1/synthesizers"]);
});

test("a run shows the scores the API returned and opens in Explore", async ({ page }) => {
  await page.goto("/synthesizers.html#bootstrap-table", { waitUntil: "networkidle" });
  await expect(page.locator(".scard[aria-current=true] .name")).toHaveText("bootstrap-table");
  const answer = page.waitForResponse(r => r.url().endsWith("/api/v1/synthesis/runs"));
  await page.getByRole("button", { name: "Run" }).click();
  const run = await (await answer).json();
  await expect(page.locator(".tile", { hasText: "Clone risk" }).locator(".v"))
    .toHaveText(`${run.metrics.clone_risk_pct.toLocaleString("en-US", { minimumFractionDigits: 1, maximumFractionDigits: 1 })} %`);
  await expect(page.locator(".charts canvas")).toHaveCount(run.fields.filter(f => f.kind === "measure").length);
  await expect(page.locator(".detection .verdict")).toContainText(`${run.metrics.detection_verdict}: AUC ${run.metrics.detection_auc.toFixed(2)}`);
  await expect(page.locator(".detection canvas")).toHaveCount(1);
  const href = await page.getByRole("link", { name: "Open in Explore" }).getAttribute("href");
  const view = JSON.parse(decodeURIComponent(href.replace("explore.html#view=", "")));
  expect(view.source.synthesis).toEqual({ synthesizer: "bootstrap-table", source: run.source, params: run.params });
});

test("a table synthesizer mounted as a plug-in runs from the page and opens in Explore", async ({ page }) => {
  // bayesian-network is written as a plug-in and declared in the entry-point group: nothing in the page names
  // it, so the catalogue, the run form, the scores and Explore all come from the API
  test.slow(); // two server runs, each with the detection test
  await page.goto("/synthesizers.html#bayesian-network", { waitUntil: "networkidle" });
  await expect(page.locator(".scard[aria-current=true] .name")).toHaveText("bayesian-network");
  await page.locator("#p-bins").fill("12");
  const answer = page.waitForResponse(r => r.url().endsWith("/api/v1/synthesis/runs"));
  await page.getByRole("button", { name: "Run" }).click();
  const run = await (await answer).json();
  expect(run.params).toEqual({ seed: 7, bins: 12 });
  await expect(page.locator(".tile", { hasText: "Clone risk" })).toBeVisible();
  const href = await page.getByRole("link", { name: "Open in Explore" }).getAttribute("href");
  const view = JSON.parse(decodeURIComponent(href.replace("explore.html#view=", "")));
  expect(view.source.synthesis).toEqual({ synthesizer: "bayesian-network", source: run.source, params: run.params });
  await page.getByRole("link", { name: "Open in Explore" }).click();
  await expect(page.locator(".result .tabulator-tableholder .tabulator-row")).toHaveCount(2, { timeout: 30_000 });
});

test("choosing a synthesizer puts it in the address", async ({ page }) => {
  await page.goto("/synthesizers.html", { waitUntil: "networkidle" });
  await page.locator(".scard", { hasText: "bootstrap-table" }).click();
  await expect(page).toHaveURL(/#bootstrap-table$/);
  await expect(page.getByRole("heading", { name: "bootstrap-table" })).toBeVisible();
});

test("a parameter outside its catalogue bounds is refused before any request", async ({ page }) => {
  await page.goto("/synthesizers.html#bootstrap-table", { waitUntil: "networkidle" });
  let posted = false;
  page.on("request", r => { if (r.method() === "POST") posted = true; });
  await page.locator("#p-jitter").fill("2");
  await page.getByRole("button", { name: "Run" }).click();
  await expect(page.locator(".err", { hasText: "jitter" })).toHaveText("jitter: from 0 to 1");
  await expect(page.locator("#p-jitter")).toHaveAttribute("aria-invalid", "true");
  expect(posted).toBe(false);
});

test("at 390 px the Synthesizers page does not overflow sideways", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 800 });
  await page.goto("/synthesizers.html#seasonal-profile", { waitUntil: "networkidle" });
  await page.getByRole("button", { name: "Run" }).click();
  await expect(page.locator(".tiles")).toBeVisible();
  const [scroll, inner] = await page.evaluate(() => [document.documentElement.scrollWidth, window.innerWidth]);
  expect(scroll).toBeLessThanOrEqual(inner);
});

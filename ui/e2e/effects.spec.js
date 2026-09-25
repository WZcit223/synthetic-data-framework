import { expect, test } from "@playwright/test";

import { exploreLink } from "../src/lib/effects-model.js";
import { smoke } from "./smoke.js";

const STUDY = {
  interventions: ["promo_spike"],
  policies: [{ kind: "service-level", service_level: 0.95, lead_time_days: 7, review_days: 7 }],
  outcomes: ["simulated_cost"],
  replicates: 4,
  confidence: 0.95,
};

test("the Effects page loads and makes its API calls", async ({ page }) => {
  await smoke(page, "/effects.html", ["GET /api/v1/experiments/catalog", "POST /api/v1/effects"]);
});

test("a study runs and shows the effects the API returned", async ({ page }) => {
  await page.goto("/effects.html", { waitUntil: "networkidle" });
  const run = page.getByRole("button", { name: "Run study" });
  await expect(run).toBeEnabled(); // the budget answer came back within budget
  const answer = page.waitForResponse(r => r.url().endsWith("/api/v1/effects") && !r.request().postData().includes("check_only"));
  await run.click();
  const response = await answer;
  const sent = JSON.parse(response.request().postData());
  const study = await response.json();
  const effects = study.rows.map(r => Object.fromEntries(study.fields.map((f, i) => [f.name, r[i]])));
  const shown = effects.filter(r => !(r.ci_low <= 0 && 0 <= r.ci_high)).length;
  await expect(page.locator(".headline")).toContainText(`${shown} of ${effects.length}`);
  await expect(page).toHaveURL(/#request=/);
  const allEffects = page.locator(".section", { hasText: "All effects" }).locator(".tabulator-row");
  await expect(allEffects).toHaveCount(effects.length);
  await expect(page.getByRole("link", { name: "Open effects in Explore" })).toHaveAttribute("href", exploreLink(sent, "effects"));
  await expect(page.getByRole("link", { name: "Open replicate rows in Explore" })).toHaveAttribute("href", exploreLink(sent, "replicates"));
});

test("a link with a study in its address runs that study", async ({ page }) => {
  const runs = [];
  page.on("request", r => r.url().endsWith("/api/v1/effects") && !r.postData().includes("check_only") && runs.push(r));
  await page.goto("/effects.html#request=" + encodeURIComponent(JSON.stringify(STUDY)));
  await expect(page.locator(".headline")).toBeVisible();
  await page.waitForTimeout(1000); // a repeated run would have started by now
  expect(runs.map(r => JSON.parse(r.postData()))).toEqual([STUDY]); // once, and exactly the linked study
  await expect(page.locator("#replicates")).toHaveValue("4");
});

test("the estimation view estimates, keeps its address, and its tab returns to it", async ({ page }) => {
  await page.goto("/effects.html", { waitUntil: "networkidle" });
  await page.getByRole("tab", { name: "Estimate from data" }).click();
  const answer = page.waitForResponse(r => r.url().endsWith("/api/v1/causal/estimates"));
  await page.getByRole("button", { name: "Estimate", exact: true }).click();
  const scores = await (await answer).json();
  const truth = scores.true_effect;
  await expect(page.locator("#estimateView .headline")).toContainText("True effect");
  await expect(page).toHaveURL(/#estimate=/);
  const estimateUrl = page.url();
  await expect(page.locator("#estimateView .tabulator-row")).toHaveCount(scores.rows.length);
  expect(truth).not.toBeNull();

  await page.getByRole("tab", { name: "Simulate an action" }).click();
  await expect(page.locator("#simulateView")).toBeVisible();
  await page.getByRole("tab", { name: "Estimate from data" }).click();
  expect(page.url()).toBe(estimateUrl);
  await expect(page.locator("#estimateView .headline")).toBeVisible();
});

test("a link with an estimation in its address runs it", async ({ page }) => {
  await page.goto("/effects.html#estimate", { waitUntil: "networkidle" });
  const catalog = await (await page.request.get("/api/v1/estimators")).json();
  const request = {
    estimators: ["difference-in-means"],
    benchmark: Object.fromEntries(catalog.benchmark.params.map(p => [p.name, p.default])),
    question: { ...catalog.benchmark.question, covariates: [] },
    confidence: 0.9,
  };
  const runs = [];
  page.on("request", r => r.url().endsWith("/api/v1/causal/estimates") && runs.push(r));
  // a new address in the same document, with the catalogue already loaded
  await page.goto("/effects.html#estimate=" + encodeURIComponent(JSON.stringify(request)));
  await expect(page.locator("#estimateView .tabulator-row")).toHaveCount(1);
  await page.waitForTimeout(1000); // a repeated estimation would have started by now
  expect(runs.map(r => JSON.parse(r.postData()))).toEqual([request]); // once, and exactly the linked request

  // the tabs return to this address, and an edit is not reset by the view
  await page.getByRole("tab", { name: "Simulate an action" }).click();
  await page.getByRole("tab", { name: "Estimate from data" }).click();
  await expect(page.locator("#estimateConfidence")).toHaveValue("0.9");
  await page.locator("#estimateConfidence").selectOption("0.99");
  await page.waitForTimeout(500);
  await expect(page.locator("#estimateConfidence")).toHaveValue("0.99");
  expect(runs.length).toBe(1);
});

test("the Estimate tab keeps the address the page opened on, even when it did not run", async ({ page }) => {
  const link = "#estimate=" + encodeURIComponent(JSON.stringify({ estimators: ["no-such-estimator"] }));
  await page.goto("/effects.html" + link, { waitUntil: "networkidle" });
  await expect(page.locator("#estimateView .notice.bad")).toContainText("no-such-estimator");
  await page.getByRole("tab", { name: "Simulate an action" }).click();
  await page.getByRole("tab", { name: "Estimate from data" }).click();
  await expect(page.locator("#estimateView .notice.bad")).toContainText("no-such-estimator");
});

test("at 390 px the Effects page does not overflow sideways", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 800 });
  await page.goto("/effects.html#request=" + encodeURIComponent(JSON.stringify(STUDY)));
  await expect(page.locator(".headline")).toBeVisible({ timeout: 60_000 });
  const [scroll, inner] = await page.evaluate(() => [document.documentElement.scrollWidth, window.innerWidth]);
  expect(scroll).toBeLessThanOrEqual(inner);
});

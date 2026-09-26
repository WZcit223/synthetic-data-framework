import { expect, test } from "@playwright/test";

import { PRESETS } from "../src/pages/explore/view.js";
import { smoke } from "./smoke.js";

const chips = (page, shelf) => page.locator(`.shelf[data-shelf="${shelf}"] .pchip .main`);
const linked = page => JSON.parse(decodeURIComponent(new URL(page.url()).hash.slice("#view=".length)));

test("the Explore page loads and makes its API calls", async ({ page }) => {
  await smoke(page, "/explore.html", ["GET /api/v1/datasets", "GET /api/v1/datasets/order-lines"]);
});

test("every order-lines preset renders, as a table or as charts", async ({ page }) => {
  const errors = [];
  page.on("pageerror", e => errors.push(String(e)));
  await page.goto("/explore.html", { waitUntil: "networkidle" });
  const presets = PRESETS["order-lines"];
  await expect(page.locator(".preset")).toHaveCount(presets.length);
  for (const [i, p] of presets.entries()) {
    await page.locator(".preset").nth(i).click();
    await expect(page.locator(".preset").nth(i)).toHaveAttribute("aria-pressed", "true");
    if (p.display?.as === "chart") await expect(page.locator(".result canvas")).toHaveCount(p.view.values.length);
    else await expect(page.locator(".result .tabulator-row").first()).toBeVisible();
    expect(linked(page).view.rows).toEqual(p.view.rows);
  }
  expect(errors).toEqual([]);
});

test("a pivot built by dragging, clicking and the menus is kept in the link", async ({ page }) => {
  await page.goto("/explore.html", { waitUntil: "networkidle" });
  // a field dropped before the first row chip goes first
  await page.locator('.field[data-field="channel"]').dragTo(page.locator('.shelf[data-shelf="rows"] .pchip').first(), { targetPosition: { x: 3, y: 5 } });
  await expect(chips(page, "rows")).toHaveText(["Channel▾", "Category▾"]);
  // a chip dragged onto another shelf moves there
  await page.locator('.shelf[data-shelf="rows"] .pchip').first().dragTo(page.locator('.shelf[data-shelf="columns"]'));
  await expect(chips(page, "columns")).toHaveText(["Order date · Month▾", "Channel▾"]);
  // a measure clicked goes to Values; its menu changes the aggregation
  await page.locator('.field[data-field="quantity"]').click();
  await chips(page, "values").nth(1).click();
  await page.locator(".popover .item", { hasText: "Mean" }).click();
  await expect(chips(page, "values")).toHaveText(["Sum of Line value▾", "Mean of Quantity▾"]);
  // a field dropped on Filters opens its values; unticking one filters it out
  await page.locator('.field[data-field="priority"]').dragTo(page.locator('.shelf[data-shelf="filters"]'));
  await expect(page.locator(".popover h4")).toHaveText("Filter · Priority");
  await page.locator(".popover .vals input").first().uncheck();
  await page.keyboard.press("Escape");
  await expect(page.locator(".popover")).toHaveCount(0);
  const view = linked(page).view;
  expect(view.columns).toEqual([{ field: "date", grain: "month" }, { field: "channel" }]);
  expect(view.values).toEqual([{ field: "line_value", agg: "sum" }, { field: "quantity", agg: "mean" }]);
  expect(Object.keys(view.filters)).toEqual(["status", "priority"]);
  // a header click sorts, and again flips the direction
  await page.locator(".tabulator-col-title", { hasText: /^Category/ }).click();
  expect(linked(page).view.sort).toEqual({ by: "label", dir: "asc" });
  await page.locator(".tabulator-col-title", { hasText: /^Category/ }).click();
  expect(linked(page).view.sort).toEqual({ by: "label", dir: "desc" });
  // the link reopens the same view
  const url = page.url();
  const again = await page.context().newPage();
  await again.goto(url, { waitUntil: "networkidle" });
  await expect(chips(again, "columns")).toHaveText(["Order date · Month▾", "Channel▾"]);
  expect(linked(again)).toEqual(linked(page));
});

test("the chart view draws one chart per value and folds the smallest series into Other", async ({ page }) => {
  const view = { rows: [{ field: "channel" }], columns: [{ field: "sku_id" }], values: [{ field: "quantity", agg: "sum" }, { field: "line_value", agg: "sum" }] };
  await page.goto("/explore.html#view=" + encodeURIComponent(JSON.stringify({ source: { dataset: "order-lines" }, view, display: { as: "chart" } })), { waitUntil: "networkidle" });
  await expect(page.locator(".result canvas")).toHaveCount(2);
  await expect(page.locator(".result figcaption")).toHaveText(["Sum of Quantity by Channel", "Sum of Line value by Channel"]);
  await expect(page.locator(".chartnote")).toContainText("folded into “Other”");
  await expect(page.locator(".chartnote")).toContainText("Each value has its own chart and scale.");
});

test("a large result scrolls in a bounded table that draws only the rows in sight", async ({ page }) => {
  const view = { rows: [{ field: "sku_id" }, { field: "date", grain: "day" }, { field: "channel" }], values: [{ field: "quantity", agg: "sum" }] };
  await page.goto("/explore.html#view=" + encodeURIComponent(JSON.stringify({ source: { dataset: "order-lines" }, view })), { waitUntil: "networkidle" });
  await expect(page.locator(".result .tabulator-row").first()).toBeVisible();
  const groups = Number((await page.locator(".statusline span", { hasText: "groups" }).textContent()).replace(/\D/g, ""));
  expect(groups).toBeGreaterThanOrEqual(10_000);
  const drawn = page.locator(".result .tabulator-tableholder .tabulator-row");
  expect(await drawn.count()).toBeLessThan(200);
  await page.locator(".result .tabulator-tableholder").evaluate(el => el.scrollTo(0, el.scrollHeight));
  await expect(drawn.last()).toBeVisible();
  expect(await drawn.count()).toBeLessThan(200);
});

test("a collapsed subtotal group stays collapsed when the table is sorted", async ({ page }) => {
  const view = { rows: [{ field: "category" }, { field: "abc_class" }], values: [{ field: "quantity", agg: "sum" }], subtotals: true };
  await page.goto("/explore.html#view=" + encodeURIComponent(JSON.stringify({ source: { dataset: "order-lines" }, view })), { waitUntil: "networkidle" });
  const rows = page.locator(".result .tabulator-tableholder .tabulator-row");
  const before = await rows.count();
  const first = await rows.first().locator(".tabulator-cell").first().textContent();
  await rows.first().locator(".tabulator-data-tree-control").click();
  await expect(rows).toHaveCount(before - 3); // its three ABC classes fold away
  await page.locator(".tabulator-col-title", { hasText: /^Sum of Quantity/ }).click(); // sort by value: the table is built again
  expect(linked(page).view.sort).toEqual({ by: "value", dir: "desc" });
  await expect(rows).toHaveCount(before - 3);
  const group = rows.filter({ hasText: first.trim() }).first();
  await expect(group.locator(".tabulator-data-tree-control-expand")).toHaveCount(1);
});

test("collapsed groups open again when the row fields change", async ({ page }) => {
  const view = { rows: [{ field: "category" }, { field: "abc_class" }], values: [{ field: "quantity", agg: "sum" }], subtotals: true };
  await page.goto("/explore.html#view=" + encodeURIComponent(JSON.stringify({ source: { dataset: "order-lines" }, view })), { waitUntil: "networkidle" });
  const rows = page.locator(".result .tabulator-tableholder .tabulator-row");
  await rows.first().locator(".tabulator-data-tree-control").click();
  await expect(rows.first().locator(".tabulator-data-tree-control-expand")).toHaveCount(1);
  await page.locator('.field[data-field="channel"]').click(); // a third row field: the first group is still there
  await expect(chips(page, "rows")).toHaveText(["Category▾", "ABC class▾", "Channel▾"]);
  await expect(rows.first().locator(".tabulator-data-tree-control-collapse")).toHaveCount(1);
});

test("a link that cannot be opened says why", async ({ page }) => {
  await page.goto("/explore.html#view=%7Bbad", { waitUntil: "networkidle" });
  await expect(page.locator(".failure")).toContainText("the view in this link is not valid JSON");
  const view = { rows: [{ field: "nope" }], values: [] };
  await page.goto("/explore.html#view=" + encodeURIComponent(JSON.stringify({ source: { dataset: "order-lines" }, view })), { waitUntil: "networkidle" });
  await expect(page.locator(".failure")).toContainText('unknown field "nope"');
});

test("the policy experiment runs from its form", async ({ page }) => {
  await page.goto("/explore.html", { waitUntil: "networkidle" });
  await page.selectOption("#source", "experiment");
  await expect(page.locator(".result")).toContainText("Run an experiment");
  const answer = page.waitForResponse(r => r.url().endsWith("/api/v1/experiments"));
  await page.getByRole("button", { name: "Run experiment" }).click();
  const d = await (await answer).json();
  await expect(page.locator(".statusline")).toContainText(`${d.rows.length} rows read`);
  expect(linked(page).source.experiment.outcomes.length).toBeGreaterThan(0);
});

test("an experiment that fails keeps the form as the user left it", async ({ page }) => {
  await page.goto("/explore.html", { waitUntil: "networkidle" });
  await page.selectOption("#source", "experiment");
  await page.getByRole("button", { name: "Run experiment" }).click();
  await expect(page.locator(".statusline")).toContainText("rows read");
  await page.route("**/api/v1/experiments", route => route.fulfill({ status: 500, contentType: "application/json", body: '{"detail":"boom"}' }));
  const outcome = page.locator(".expform input[name=outcome]").first();
  await outcome.uncheck();
  await page.getByRole("button", { name: "Run experiment" }).click();
  await expect(page.locator(".failure")).toContainText("Could not load the experiment");
  await expect(outcome).not.toBeChecked();
});

test("a synthesizer run opens in Explore", async ({ page }) => {
  await page.goto("/synthesizers.html#bootstrap-table", { waitUntil: "networkidle" });
  await page.getByRole("button", { name: "Run" }).click();
  await page.getByRole("link", { name: "Open in Explore" }).click();
  // Explore runs the evaluation again on the server, detection test included: seconds of work, so it gets
  // more than the default 5 s
  await expect(page.locator(".preset[aria-pressed=true]")).toHaveText(PRESETS["synthesis-table"][0].label, {
    timeout: 30_000,
  });
  await expect(page.locator(".result .tabulator-tableholder .tabulator-row")).toHaveCount(2); // real and synthetic
});

test("an effect study and an estimation open in Explore", async ({ page }) => {
  test.slow(); // four server runs: the study and the estimation, each on its page and again in Explore
  const study = {
    interventions: ["promo_spike"],
    policies: [{ kind: "service-level", service_level: 0.95, lead_time_days: 7, review_days: 7 }],
    outcomes: ["simulated_cost"],
    replicates: 4,
    confidence: 0.95,
  };
  await page.goto("/effects.html#request=" + encodeURIComponent(JSON.stringify(study)));
  await page.getByRole("link", { name: "Open effects in Explore" }).click();
  // Explore runs the study again on the server: seconds of work, longer while the server is busy
  // (a forecast fitted for a world another spec regenerated), so it gets more than the default 5 s
  const rerun = { timeout: 30_000 };
  await expect(page.locator(".preset[aria-pressed=true]")).toHaveText(PRESETS["effects-effects"][0].label, rerun);
  await expect(page.locator(".result .tabulator-row").first()).toBeVisible();

  await page.goto("/effects.html#estimate", { waitUntil: "networkidle" });
  await page.getByRole("button", { name: "Estimate", exact: true }).click();
  await page.getByRole("link", { name: "Open scores in Explore" }).click();
  await expect(page.locator(".preset[aria-pressed=true]")).toHaveText(PRESETS["estimates-scores"][0].label, rerun);
  await expect(page.locator(".result .tabulator-row").first()).toBeVisible();
});

test("at 390 px the Explore page does not overflow sideways", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 800 });
  await page.goto("/explore.html", { waitUntil: "networkidle" });
  await expect(page.locator(".result .tabulator-row").first()).toBeVisible();
  const [scroll, inner] = await page.evaluate(() => [document.documentElement.scrollWidth, window.innerWidth]);
  expect(scroll).toBeLessThanOrEqual(inner);
});

test("a data source is a dataset, pivoted without a world", async ({ page }) => {
  const errors = [];
  page.on("pageerror", e => errors.push(String(e)));
  const view = { rows: [{ field: "country" }], values: [{ field: "quantity", agg: "sum" }] };
  const link = source => "/explore.html#view=" + encodeURIComponent(JSON.stringify({ source, view }));
  await page.goto(link({ dataset: "source-retail-10k" }), { waitUntil: "networkidle" });
  await expect(page.locator(".result .tabulator-row", { hasText: "United Kingdom" })).toBeVisible();
  await expect(page.locator('.field[data-field="invoice_date_hour"]')).toBeVisible(); // the hour of a timestamp
  await expect(page.locator(".muted", { hasText: "bundled data source retail-10k" })).toContainText("10,000 rows");
  await expect(page.getByText(/world /)).toHaveCount(0); // a source's rows are its file's, not the world's
  expect(errors).toEqual([]);
});

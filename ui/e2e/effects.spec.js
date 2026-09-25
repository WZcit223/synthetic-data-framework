import { test } from "@playwright/test";

import { smoke } from "./smoke.js";

test("the Effects page loads and makes its API calls", async ({ page }) => {
  await smoke(page, "/effects.html", ["GET /api/v1/experiments/catalog", "POST /api/v1/effects"]);
});

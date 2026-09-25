import { test } from "@playwright/test";

import { smoke } from "./smoke.js";

test("the Explore page loads and makes its API calls", async ({ page }) => {
  await smoke(page, "/explore.html", ["GET /api/v1/datasets", "GET /api/v1/datasets/order-lines"]);
});

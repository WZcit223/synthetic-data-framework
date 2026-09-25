import { test } from "@playwright/test";

import { smoke } from "./smoke.js";

test("the Synthesizers page loads and makes its API calls", async ({ page }) => {
  await smoke(page, "/synthesizers.html", ["GET /api/v1/synthesis/sources", "GET /api/v1/synthesizers"]);
});

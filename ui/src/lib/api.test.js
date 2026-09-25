// Tests for the API helper: npm test
import assert from "node:assert/strict";
import { test } from "vitest";

import { describeDetail } from "./api.js";

test("an API error detail reads as one line", () => {
  assert.equal(describeDetail("unknown dataset 'x'"), "unknown dataset 'x'");
  assert.equal(
    describeDetail([{ loc: ["body", "policies", 0, "service_level"], msg: "Input should be less than 1" }]),
    "policies.0.service_level: Input should be less than 1",
  );
  assert.equal(describeDetail(undefined), null);
});

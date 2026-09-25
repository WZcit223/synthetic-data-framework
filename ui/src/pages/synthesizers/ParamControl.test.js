// @vitest-environment jsdom
// Tests for a parameter's field: npm test
import assert from "node:assert/strict";
import { render } from "@testing-library/svelte";
import { test } from "vitest";

import { initialEntry } from "./form.js";
import ParamControl from "./ParamControl.svelte";

const field = param => render(ParamControl, { param, entry: initialEntry(param) }).container;

test("a number field takes its inclusive bounds from the catalogue and says them", () => {
  const c = field({ name: "jitter", type: "float", default: 0.05, nullable: false, min: 0, max: 1, exclusive: false });
  const input = c.querySelector("input");
  assert.equal(input.type, "number");
  assert.equal(input.min, "0");
  assert.equal(input.max, "1");
  assert.equal(input.step, "any");
  assert.equal(input.value, "0.05");
  assert.equal(c.querySelector(".hint").textContent, "from 0 to 1");
});

test("exclusive bounds are said but not set on the field, whose limits are inclusive", () => {
  const c = field({ name: "share", type: "float", default: 0.5, nullable: true, min: 0, max: 1, exclusive: true });
  const input = c.querySelector("input");
  assert.equal(input.min, "");
  assert.equal(input.max, "");
  assert.equal(c.querySelector(".hint").textContent, "empty: none · between 0 and 1, both excluded");
});

test("a whole number steps by one; a bool is a checkbox, a nullable bool a three-way choice", () => {
  assert.equal(field({ name: "seed", type: "int", default: 7, nullable: false }).querySelector("input").step, "1");
  assert.equal(field({ name: "weekly", type: "bool", default: true, nullable: false }).querySelector("input").type, "checkbox");
  const choice = field({ name: "weekly", type: "bool", default: null, nullable: true }).querySelector("select");
  assert.deepEqual([...choice.options].map(o => o.value), ["", "true", "false"]);
});

test("an error is shown under its field and marks it invalid", () => {
  const p = { name: "jitter", type: "float", default: 0.05, nullable: false, min: 0, max: 1, exclusive: false };
  const c = render(ParamControl, { param: p, entry: initialEntry(p), error: "jitter: from 0 to 1" }).container;
  assert.equal(c.querySelector(".err").textContent, "jitter: from 0 to 1");
  assert.equal(c.querySelector("input").getAttribute("aria-invalid"), "true");
});

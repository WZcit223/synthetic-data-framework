// Tests for the Synthesizers page helpers: node --test ui/*.test.js
import assert from "node:assert/strict";
import { test } from "node:test";

import { boundsText, column, exploreLink, histogram, readParam } from "./synthesis.js";

const seed = { name: "seed", type: "int", default: 7, min: null, max: null, exclusive: false, nullable: false };
const nullableSeed = { ...seed, default: null, nullable: true };
const jitter = { name: "jitter", type: "float", default: 0.05, min: 0, max: 1, exclusive: false, nullable: false };
const level = { name: "level", type: "float", default: 0.95, min: 0.5, max: 1, exclusive: true, nullable: false };

test("a parameter's input is read as the server would accept it", () => {
  assert.deepEqual(readParam(seed, "7"), { value: 7 });
  assert.deepEqual(readParam(seed, " 12 "), { value: 12 });
  assert.deepEqual(readParam(nullableSeed, ""), { value: null });
  assert.deepEqual(readParam(jitter, "0"), { value: 0 });
  assert.deepEqual(readParam(jitter, "1"), { value: 1 }); // inclusive bounds
  assert.deepEqual(readParam(level, "0.99"), { value: 0.99 });
  assert.deepEqual(readParam({ name: "mode", type: "str" }, "fast"), { value: "fast" });
  assert.deepEqual(readParam({ name: "flag", type: "bool" }, true), { value: true });
  assert.deepEqual(readParam({ name: "flag", type: "bool" }, false), { value: false });
  const maybe = { name: "flag", type: "bool", default: null, nullable: true };
  assert.deepEqual(readParam(maybe, ""), { value: null }); // "none" keeps a nullable bool's null
  assert.deepEqual(readParam(maybe, "true"), { value: true });
  assert.deepEqual(readParam(maybe, "false"), { value: false });
});

test("an input the server would refuse is refused with a reason", () => {
  assert.equal(readParam(seed, "").error, "seed: enter a value");
  assert.equal(readParam(seed, "1.5").error, "seed: enter a whole number");
  assert.equal(readParam(seed, "abc").error, "seed: enter a number");
  assert.equal(readParam(jitter, "1.5").error, "jitter: from 0 to 1");
  assert.equal(readParam(level, "1").error, "level: between 0.5 and 1, both excluded");
  assert.equal(readParam({ name: "flag", type: "bool", nullable: false }, "").error, "flag: choose true or false");
});

test("bounds read in words", () => {
  assert.equal(boundsText(jitter), "from 0 to 1");
  assert.equal(boundsText({ min: 0, max: null }), "at least 0");
  assert.equal(boundsText({ min: null, max: 5, exclusive: true }), "below 5");
  assert.equal(boundsText(seed), "");
});

test("a column of one origin", () => {
  const fields = [{ name: "origin" }, { name: "qty" }];
  const rows = [["real", 1], ["synthetic", 2], ["real", 3], ["real", null]];
  assert.deepEqual(column(rows, fields, "qty", "real"), [1, 3]);
  assert.deepEqual(column(rows, fields, "qty", "synthetic"), [2]);
  assert.throws(() => column(rows, fields, "price", "real"), /no price column/);
});

test("whole values with few distinct levels get one bin each", () => {
  const h = histogram([0, 1, 1, 2, 6], [1, 1, 6, 6]);
  assert.deepEqual(h.labels, ["0", "1", "2", "6"]);
  assert.deepEqual(h.real, [0.2, 0.4, 0.2, 0.2]);
  assert.deepEqual(h.synthetic, [0, 0.5, 0, 0.5]);
});

test("continuous values share bins over the real data's bulk, outliers in the edge bins", () => {
  const real = Array.from({ length: 100 }, (_, i) => i + 0.5);
  const h = histogram(real, [-1000, 50.5, 5000], 4);
  assert.equal(h.labels.length, 4);
  assert.ok(Math.abs(h.real.reduce((a, b) => a + b, 0) - 1) < 1e-9);
  assert.deepEqual(h.synthetic.map(x => Math.round(x * 3)), [1, 0, 1, 1]); // -1000 → first bin, 5000 → last
  assert.deepEqual(histogram([], []), { labels: [], real: [], synthetic: [] });
});

test("only a repeatable run links to Explore, with the parameters it used", () => {
  const run = { synthesizer: "bootstrap-table", source: "sample", params: { seed: 7, jitter: 0.05 }, repeatable: true };
  const link = exploreLink(run);
  assert.ok(link.startsWith("explore.html#view="));
  assert.deepEqual(JSON.parse(decodeURIComponent(link.slice("explore.html#view=".length))), {
    source: { synthesis: { synthesizer: "bootstrap-table", source: "sample", params: { seed: 7, jitter: 0.05 } } },
  });
  assert.equal(exploreLink({ ...run, repeatable: false }), null);
});

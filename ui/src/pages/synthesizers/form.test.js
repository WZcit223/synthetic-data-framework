// Tests for the Synthesizers run form: npm test
import assert from "node:assert/strict";
import { test } from "vitest";

import { initialEntry, readForm } from "./form.js";

const SEED = { name: "seed", type: "int", default: 7, nullable: false, min: 0, max: null, exclusive: false };
const SHARE = { name: "noise", type: "float", default: 0.1, nullable: true, min: 0, max: 1, exclusive: true };
const FLAG = { name: "weekly", type: "bool", default: null, nullable: true };
const TAG = { name: "tag", type: "str", default: null, nullable: true };
const PARAMS = [SEED, SHARE, FLAG, TAG];
const start = () => Object.fromEntries(PARAMS.map(p => [p.name, initialEntry(p)]));

test("the defaults make a valid request", () => {
  assert.deepEqual(readForm(PARAMS, start()), { values: { seed: 7, noise: 0.1, weekly: null, tag: null }, errors: {}, ok: true });
});

test("a bound from the catalogue is checked, exclusive bounds included", () => {
  const e = start();
  e.seed.text = "-1";
  e.noise.text = "1";
  const r = readForm(PARAMS, e);
  assert.equal(r.ok, false);
  assert.equal(r.errors.seed, "seed: at least 0");
  assert.equal(r.errors.noise, "noise: between 0 and 1, both excluded");
});

test("text a number field cannot parse is an error, not a missing value", () => {
  const e = start();
  e.noise.text = "";
  e.noise.bad = true; // the browser reports "1e" as "" with badInput
  assert.equal(readForm(PARAMS, e).errors.noise, "noise: enter a number");
  e.noise.bad = false; // a truly empty nullable field is none
  assert.equal(readForm(PARAMS, e).values.noise, null);
});

test("a nullable bool reads its choice; a nullable string its none box", () => {
  const e = start();
  e.weekly.choice = "false";
  e.tag.none = false;
  e.tag.text = "";
  assert.deepEqual(readForm(PARAMS, e).values, { seed: 7, noise: 0.1, weekly: false, tag: "" }); // "" is a string, not none
});

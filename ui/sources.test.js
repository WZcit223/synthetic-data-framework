// Tests for the sources an Explore link may name: node --test ui/*.test.js
import assert from "node:assert/strict";
import { test } from "node:test";

import { sourceError } from "./sources.js";

test("the existing source shapes are accepted", () => {
  assert.equal(sourceError({ dataset: "order-lines" }), null);
  assert.equal(sourceError({ experiment: { interventions: ["baseline"] } }), null);
  assert.equal(sourceError({ synthesis: { synthesizer: "seasonal-profile", source: "sample", params: {} } }), null);
});

test("an effects source holds a request and one of its two tables", () => {
  const request = { interventions: ["promo_spike"] };
  assert.equal(sourceError({ effects: { request, table: "effects" } }), null);
  assert.equal(sourceError({ effects: { request, table: "replicates" } }), null);
  assert.match(sourceError({ effects: { request, table: "data" } }), /effects.table must be one of effects or replicates/);
  assert.match(sourceError({ effects: { request } }), /effects.table/);
  assert.match(sourceError({ effects: { table: "effects" } }), /effects.request must be a request body/);
  assert.match(sourceError({ effects: { request: [], table: "effects" } }), /effects.request must be a request body/);
  assert.match(sourceError({ effects: { request, table: "effects", view: {} } }), /only request and table; got \["view"\]/);
  assert.match(sourceError({ effects: "promo_spike" }), /effects must hold a request and a table/);
  assert.match(sourceError({ effects: { request: { ...request, check_only: true }, table: "effects" } }), /budget only/);
  assert.match(sourceError({ effects: { request: { ...request, check_only: "yes" }, table: "effects" } }), /budget only/);
  assert.equal(sourceError({ effects: { request: { ...request, check_only: false }, table: "effects" } }), null);
});

test("a source names exactly one known shape", () => {
  assert.match(sourceError(null), /names no source/);
  assert.match(sourceError([]), /names no source/);
  assert.match(sourceError({ dataset: "a", effects: {} }), /exactly one of dataset, experiment, synthesis, effects or estimates/);
  assert.match(sourceError({ nope: {} }), /unknown source "nope"/);
  assert.match(sourceError({ dataset: 3 }), /dataset must be a name/);
});

test("an estimates source holds a request and the scores or, for the benchmark, its observed rows", () => {
  const bench = { estimators: ["ipw"], benchmark: { confounding: 1 } };
  const data = { estimators: ["ipw"], dataset: "order-lines", question: { treatment: "priority", outcome: "line_value" } };
  assert.equal(sourceError({ estimates: { request: bench, table: "scores" } }), null);
  assert.equal(sourceError({ estimates: { request: bench, table: "data" } }), null);
  assert.equal(sourceError({ estimates: { request: data, table: "scores" } }), null);
  assert.match(sourceError({ estimates: { request: data, table: "data" } }), /"data" needs a benchmark request; a catalogue dataset opens as \{dataset: name\}/);
  assert.match(sourceError({ estimates: { request: bench, table: "rows" } }), /estimates.table must be one of scores or data/);
  assert.match(sourceError({ estimates: { request: bench } }), /estimates.table/);
  assert.match(sourceError({ estimates: { table: "scores" } }), /estimates.request must be a request body/);
  assert.match(sourceError({ estimates: { request: bench, table: "scores", view: 1 } }), /only request and table/);
});

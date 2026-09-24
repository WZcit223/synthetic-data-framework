// The Effects page's "Estimate from data" view: estimators scored on the promotion benchmark,
// whose true effect is known (POST /causal/estimates). The form is built from GET /estimators;
// every estimate, interval, bias and bound comes from the server. The address keeps the request.
import { $, api, esc } from "./common.js";
import { bindBars, bindLine, clip, lineChart } from "./chart.js";
import { SURFACE } from "./palette.js";
import { CONFIDENCES, amount, axisFor, intervalText, records, relativeText } from "./effects-model.js";
import {
  SWEEP, estimateHash, estimateRequestError, estimatesLink, estimatorColors, fitEstimateRequest, readEstimateHash,
  scoreReading, sweepRequests, sweepSeries,
} from "./estimate-model.js";
import { boundsText, readParam } from "./synthesis.js";

const CHAR = 6.6; // average glyph width at 11px, for sizing the label column

const state = {
  catalog: null,
  colors: new Map(),
  result: null, // {response, request, rows}
  sweep: null, // {request, series, labels}
  seq: 0, // the latest estimation; an older answer is dropped
  sweepSeq: 0,
  drawnWidth: 0,
  written: "", // the last #estimate= this view wrote
  onAddress: () => {}, // told when the view writes its address (the tabs keep it)
};

// -- entry --------------------------------------------------------------------------------------------

/** Show the view for the current address; the catalogue is loaded once, on first use. */
export async function routeEstimate({ onAddress } = {}) {
  if (onAddress) state.onAddress = onAddress;
  if (!state.catalog) {
    try {
      state.catalog = await api("/estimators");
    } catch (err) {
      $("#estimateResult").innerHTML = `<div class="notice bad"><b>Could not load the estimators.</b> ${esc(err.detail ?? err.message)}</div>`;
      return;
    }
    state.colors = estimatorColors(state.catalog.estimators.map(e => e.name));
    wire();
  }
  if (location.hash === state.written && state.result) return; // the address this view wrote itself
  loadFromAddress();
}

function wire() {
  $("#estimateForm").addEventListener("submit", e => {
    e.preventDefault();
    run();
  });
  $("#estimateForm").addEventListener("change", e => {
    if (e.target.name === "estimator") limitEstimators();
    showFormError();
  });
  $("#estimateForm").addEventListener("input", () => showFormError());
  $("#estimateResult").addEventListener("click", e => {
    if (e.target.id === "runSweep") runSweep();
  });
  let pending = 0;
  new ResizeObserver(() => {
    cancelAnimationFrame(pending);
    pending = requestAnimationFrame(() => {
      const box = $("#scoreChart");
      if (state.result && box && box.clientWidth !== state.drawnWidth) drawCharts();
    });
  }).observe($("#estimateResult"));
}

function loadFromAddress() {
  state.seq++;
  state.sweepSeq++;
  state.result = null;
  state.sweep = null;
  state.written = location.hash;
  const link = readEstimateHash(location.hash) ?? {};
  const { request, dropped } = fitEstimateRequest(link.request ?? null, state.catalog);
  renderForm(request);
  const box = $("#estimateResult");
  box.classList.remove("busy");
  if (link.error) {
    box.innerHTML = `<div class="notice bad"><b>This link cannot be opened:</b> ${esc(link.error)}. The form shows the default estimation.</div>`;
    return;
  }
  if (dropped.length) {
    box.innerHTML = `<div class="notice bad">This link names what this installation does not offer: <b>${esc(dropped.join(", "))}</b>. Check the form, then estimate.</div>`;
    return;
  }
  box.innerHTML = `<div class="notice">Choose the estimators and the adjustment set, then estimate.</div>`;
  if (link.request && !estimateRequestError(readForm(), state.catalog)) run(); // a link reproduces its estimation
}

// -- the form -----------------------------------------------------------------------------------------

function renderForm(request) {
  const cat = state.catalog;
  $("#estimators").innerHTML = cat.estimators.map(e => `<label title="${esc(e.description)}">`
    + `<input type="checkbox" name="estimator" value="${esc(e.name)}" ${request.estimators.includes(e.name) ? "checked" : ""}/>`
    + `<span class="swatch" style="background:${state.colors.get(e.name)}"></span>${esc(e.name)}`
    + `${e.origin === "builtin" ? "" : ` <span class="desc">(${esc(e.origin)})</span>`}</label>`).join("");
  const broken = Object.entries(cat.unavailable);
  $("#unavailableEstimators").innerHTML = broken.length
    ? `Unavailable: ${broken.map(([n, why]) => `<b>${esc(n)}</b> (${esc(why)})`).join(", ")}`
    : "";
  $("#benchmarkParams").innerHTML = cat.benchmark.params.map(p => {
    const bounds = p.exclusive ? "" : `${p.min != null ? ` min="${esc(p.min)}"` : ""}${p.max != null ? ` max="${esc(p.max)}"` : ""}`;
    return `<div class="ctrl"><label for="bench-${esc(p.name)}">${esc(p.name)}</label>`
      + `<input id="bench-${esc(p.name)}" type="number" data-param="${esc(p.name)}" value="${esc(request.benchmark[p.name] ?? "")}"`
      + ` step="${p.type === "int" ? 1 : "any"}"${bounds}/><div class="hint">${esc(boundsText(p))}</div></div>`;
  }).join("");
  const q = cat.benchmark.question;
  $("#covariates").innerHTML = q.covariates.map(c => `<label><input type="checkbox" name="covariate" value="${esc(c)}"`
    + ` ${request.question.covariates.includes(c) ? "checked" : ""}/>${esc(c)}</label>`).join("");
  $("#questionHint").textContent = `${q.treatment} → ${q.outcome}; uncheck a covariate to leave it out`;
  $("#estimateConfidence").innerHTML = CONFIDENCES.map(c => `<option value="${c}" ${c === request.confidence ? "selected" : ""}>${c * 100} %</option>`).join("");
  const l = cat.limits;
  $("#estimateLimits").textContent = `At most ${l.max_estimators} estimators, ${l.max_rows.toLocaleString()} rows and ${l.max_seconds} s per request.`;
  limitEstimators();
  showFormError();
}

function limitEstimators() {
  const boxes = [...document.querySelectorAll("#estimators input[name=estimator]")];
  const n = boxes.filter(b => b.checked).length;
  for (const b of boxes) b.disabled = !b.checked && n >= state.catalog.limits.max_estimators;
}

function readForm() {
  const checked = name => [...document.querySelectorAll(`#estimateForm input[name=${name}]:checked`)].map(b => b.value);
  const benchmark = {};
  for (const input of document.querySelectorAll("#benchmarkParams [data-param]")) {
    const p = state.catalog.benchmark.params.find(x => x.name === input.dataset.param);
    const read = input.validity.badInput ? { error: "" } : readParam(p, input.value);
    benchmark[p.name] = read.error == null ? read.value : input.value; // an invalid text stays, so the check names it
  }
  const q = state.catalog.benchmark.question;
  return {
    estimators: checked("estimator"),
    benchmark,
    question: { ...q, covariates: q.covariates.filter(c => checked("covariate").includes(c)) },
    confidence: Number($("#estimateConfidence").value),
  };
}

function showFormError() {
  const problem = estimateRequestError(readForm(), state.catalog);
  $("#estimateError").textContent = problem ?? "";
  $("#estimateRun").disabled = !!problem;
  return problem;
}

// -- the estimation -----------------------------------------------------------------------------------

async function run() {
  const request = readForm();
  if (showFormError()) return;
  const seq = ++state.seq;
  state.sweepSeq++; // a sweep of the previous request no longer applies
  state.written = estimateHash(request);
  if (location.hash !== state.written) history.replaceState(null, "", state.written);
  state.onAddress(state.written);
  const box = $("#estimateResult");
  box.classList.add("busy");
  box.setAttribute("aria-busy", "true");
  if (!state.result) box.innerHTML = `<div class="notice">Estimating with ${request.estimators.length} estimators…</div>`;
  $("#estimateRun").disabled = true;
  try {
    const response = await api("/causal/estimates", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(request) });
    if (seq === state.seq) render(response, request);
  } catch (err) {
    if (seq === state.seq) {
      state.result = null;
      box.innerHTML = `<div class="notice bad"><b>The estimation did not run.</b> ${esc(err.detail ?? err.message)}</div>`;
    }
  } finally {
    if (seq === state.seq) {
      box.classList.remove("busy");
      box.setAttribute("aria-busy", "false");
      showFormError();
    }
  }
}

function render(response, request) {
  const rows = records(response);
  state.result = { response, request, rows };
  state.sweep = null;
  const truth = response.true_effect;
  const unit = response.fields.find(f => f.name === "effect")?.unit;
  const per = unit === "units" ? " units/week" : unit ? ` ${unit}` : "";
  const scored = rows.filter(r => r.effect != null && r.ci_low != null);
  const covering = scored.filter(r => r.covers === "yes").length;
  const b = request.benchmark;
  const adjusted = response.question.covariates.join(", ") || "nothing";
  let h = `<p class="headline">True effect <b>${esc(amount(truth, { signed: true }))}${esc(per)}</b>: ${covering} of ${scored.length} intervals cover it.</p>`;
  h += `<p class="runline">${response.data?.rows.length ?? "–"} SKUs of the current world, uplift ${esc(amount(b.uplift * 100))} %,`
    + ` confounding ${esc(b.confounding)}, noise ${esc(b.noise)}, seed ${esc(b.seed)}; adjusting for <b>${esc(adjusted)}</b>;`
    + ` ${(response.elapsed_ms / 1000).toFixed(1)} s.</p>`;
  h += `<div class="legend effects"><span class="item"><svg width="30" height="12" aria-hidden="true"><line x1="15" x2="15" y1="0" y2="12" class="truth" style="stroke:var(--ink);stroke-width:1.5;stroke-dasharray:4 3"/></svg>true effect</span>`
    + `<span class="item">each estimator: its estimate and ${esc(request.confidence * 100)} % interval, in its own colour</span></div>`;
  h += `<div id="scoreChart"></div>`;
  h += `<div class="section"><h3>Scores</h3>${scoresTable(rows)}</div>`;
  h += `<div class="section sweep"><h3>Bias as confounding grows</h3>
    <div class="pick"><button type="button" id="runSweep">Sweep confounding from ${SWEEP[0]} to ${SWEEP.at(-1)}</button>
    <span class="muted">${SWEEP.length} estimations with everything else as above; each estimator's bias at each step.</span></div>
    <div id="sweepChart"></div></div>`;
  h += `<div class="actions">
    <a class="button primary" href="${esc(estimatesLink(request, "scores"))}">Open scores in Explore</a>
    <a class="button" href="${esc(estimatesLink(request, "data"))}">Open the observed rows in Explore</a>
    <span class="muted">Explore repeats this request on the current world and opens its table to pivot.</span></div>`;
  $("#estimateResult").innerHTML = h;
  drawCharts();
}

function scoresTable(rows) {
  const head = `<th>Estimator</th><th class="num">Estimate</th><th class="num">Interval</th><th class="num">Bias</th>`
    + `<th class="num">Relative bias</th><th>Reading</th><th class="num">Run time</th><th>Method</th>`;
  const body = rows.map(r => {
    const reading = scoreReading(r);
    const muted = r.effect == null || reading === "misses the truth";
    return `<tr class="${muted ? "covers" : ""}"><td>${esc(r.estimator)}</td><td class="num">${amount(r.effect, { signed: true })}</td>`
      + `<td class="num">${r.ci_low == null ? "–" : intervalText(r)}</td><td class="num">${amount(r.bias, { signed: true })}</td>`
      + `<td class="num">${relativeText(r.relative_bias)}</td><td class="reading">${esc(reading)}</td>`
      + `<td class="num">${r.seconds == null ? "–" : `${r.seconds.toFixed(2)} s`}</td><td class="method">${esc(r.method ?? "")}</td></tr>`;
  }).join("");
  return `<div class="tablewrap"><table class="effects"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
}

function drawCharts() {
  const r = state.result;
  const box = $("#scoreChart");
  if (!r || !box) return;
  const width = Math.max(320, box.clientWidth);
  state.drawnWidth = box.clientWidth;
  const chart = scoreChart(r.rows, { width, truth: r.response.true_effect });
  box.innerHTML = chart.svg;
  bindBars(box, chart.tips, $("#tooltip"));
  if (state.sweep) drawSweep();
}

/**
 * One row per estimator on one axis: a point at the estimate across its interval, a dashed line
 * at the true effect and a zero line. A row without an interval is a point, labelled so; an
 * error row is its message. The reading beside each row says in words what the marks show.
 */
function scoreChart(rows, { width, truth }) {
  const labelW = Math.min(Math.max(150, width * 0.3), Math.max(110, ...rows.map(r => r.estimator.length * CHAR + 16)));
  const right = 150;
  const top = 6, rowH = 36, axisH = 24;
  const plotW = Math.max(120, width - labelW - right);
  const height = top + rows.length * rowH + axisH;
  const scale = axisFor([...rows.flatMap(r => [r.effect, r.ci_low, r.ci_high]), truth], Math.max(2, Math.round(plotW / 110)));
  const X = v => labelW + ((v - scale.lo) / (scale.hi - scale.lo)) * plotW;
  let s = `<svg class="chart" role="img" aria-label="Each estimator's estimate and interval against the true effect" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">`;
  s += `<g class="grid">`;
  for (const t of scale.ticks) s += `<line x1="${X(t)}" x2="${X(t)}" y1="${top}" y2="${height - axisH}"/>`;
  s += `</g><line class="zero" x1="${X(0)}" x2="${X(0)}" y1="${top}" y2="${height - axisH}"/>`;
  if (truth != null) s += `<line class="truth" x1="${X(truth)}" x2="${X(truth)}" y1="${top}" y2="${height - axisH}"/>`;
  for (const t of scale.ticks) s += `<text x="${X(t)}" y="${height - 8}" text-anchor="middle">${esc(amount(t))}</text>`;
  const tips = [];
  rows.forEach((r, i) => {
    const y = top + i * rowH, cy = y + rowH / 2;
    const color = state.colors.get(r.estimator) ?? "#6e7681";
    const reading = scoreReading(r);
    const said = r.effect == null ? `${r.estimator}: ${r.method}` : `${r.estimator}: estimate ${amount(r.effect, { signed: true })}, ${reading}`;
    s += `<g class="band" tabindex="0" data-tip="${i}" aria-label="${esc(said)}">`;
    s += `<rect class="hit" x="0" y="${y}" width="${width}" height="${rowH}"/>`;
    s += `<text class="label" x="${labelW - 12}" y="${cy + 4}" text-anchor="end">${esc(clip(r.estimator, Math.floor((labelW - 14) / CHAR)))}</text>`;
    const tx = labelW + plotW + 12;
    if (r.effect == null) {
      s += `<text class="error" x="${labelW}" y="${cy + 4}">${esc(clip(`${reading}: ${r.method}`, Math.floor((plotW + right) / 6)))}</text>`;
    } else {
      if (r.ci_low != null) {
        const a = X(r.ci_low), b = X(r.ci_high);
        s += `<line x1="${a}" x2="${b}" y1="${cy}" y2="${cy}" stroke="${color}" stroke-width="2" stroke-linecap="round"/>`;
        for (const x of [a, b]) s += `<line x1="${x}" x2="${x}" y1="${cy - 5}" y2="${cy + 5}" stroke="${color}" stroke-width="2" stroke-linecap="round"/>`;
      }
      s += `<circle cx="${X(r.effect)}" cy="${cy}" r="5" fill="${color}" stroke="${SURFACE}" stroke-width="2"/>`;
      s += `<text class="value" x="${tx}" y="${cy - 2}">${esc(amount(r.effect, { signed: true }))}</text><text class="note" x="${tx}" y="${cy + 11}">${esc(reading)}</text>`;
    }
    s += `</g>`;
    tips.push(scoreTip(r, color, reading));
  });
  return { svg: s + `</svg>`, tips };
}

function scoreTip(r, color, reading) {
  if (r.effect == null) return { head: r.estimator, lines: [{ color: "transparent", label: r.method ?? "", value: reading }] };
  const none = "transparent";
  return {
    head: r.estimator,
    lines: [
      { color, label: "estimate", value: amount(r.effect, { signed: true }) },
      { color: none, label: "interval", value: r.ci_low == null ? "none" : intervalText(r) },
      { color: none, label: "true effect", value: amount(r.true_effect, { signed: true }) },
      { color: none, label: "bias", value: amount(r.bias, { signed: true }) },
      { color: none, label: "relative bias", value: relativeText(r.relative_bias) },
      { color: none, label: r.method ?? "", value: reading },
    ],
  };
}

// -- the confounding sweep ----------------------------------------------------------------------------

async function runSweep() {
  const r = state.result;
  if (!r) return;
  const seq = ++state.sweepSeq;
  const button = $("#runSweep");
  button.disabled = true;
  const box = $("#sweepChart");
  const results = [];
  try {
    for (const [k, request] of sweepRequests(r.request).entries()) {
      box.innerHTML = `<div class="notice">Estimating at confounding ${SWEEP[k]} (${k + 1} of ${SWEEP.length})…</div>`;
      const response = await api("/causal/estimates", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(request) });
      if (seq !== state.sweepSeq) return;
      results.push(records(response));
    }
  } catch (err) {
    if (seq === state.sweepSeq) box.innerHTML = `<div class="notice bad"><b>The sweep stopped.</b> ${esc(err.detail ?? err.message)}</div>`;
    return;
  } finally {
    if (seq === state.sweepSeq && $("#runSweep")) $("#runSweep").disabled = false;
  }
  state.sweep = { series: sweepSeries(results, r.request.estimators), labels: SWEEP.map(String) };
  drawSweep();
}

function drawSweep() {
  const box = $("#sweepChart");
  if (!box || !state.sweep) return;
  const series = state.sweep.series.map(sr => ({ ...sr, color: state.colors.get(sr.name) }));
  const fmt = v => amount(v, { signed: true });
  const model = { points: state.sweep.labels, series, format: fmt, compact: v => amount(v), width: Math.max(320, box.clientWidth) };
  const { svg, geometry } = lineChart(model);
  const legend = `<div class="legend effects">${series.map(sr => `<span class="item"><span class="ln" style="background:${sr.color}"></span>${esc(sr.name)}</span>`).join("")}</div>`;
  box.innerHTML = legend + `<p class="note">Bias (estimate minus the true effect) against confounding; 0 is no bias.</p>${svg}`;
  bindLine(box.querySelector("svg"), { ...model, geometry, points: state.sweep.labels.map(l => `confounding ${l}`) }, $("#tooltip"));
}

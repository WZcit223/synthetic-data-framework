// The Effects page: choose interventions, policies, outcomes and replicates, run an
// effect study (POST /effects), and read each effect with its interval. The work budget
// shown while editing is the server's check_only answer; every number drawn comes from
// the study's tables. The address keeps the request, so a link reproduces the study.
import { $ } from "./dom.js";
import { api } from "../lib/api.js";
import { esc } from "../lib/format.js";
import { bindBars, clip } from "../lib/chart.js";
import { OTHER, SERIES, SURFACE } from "../lib/palette.js";
import {
  CONFIDENCES, COVERS, amount, axisFor, budgetView, byMetric, coversZero, exploreLink, fitRequest, intervalText, nextPolicy,
  reading, readRequestHash, records, relativeText, replicateRows, requestError, requestHash, rowLabel,
} from "../lib/effects-model.js";
import { routeEstimate } from "./estimate.js";
import { readEstimateHash } from "../lib/estimate-model.js";

// Two colours: an interval that excludes 0 in the first series hue, one that covers 0 in
// the neutral grey. Each row also says its reading in text, so colour is never the only cue.
const SHOWN = SERIES[0], MUTED = OTHER;
const CHAR = 6.6; // average glyph width at 11px, for sizing the label column
const TWO_COLUMNS = 980; // below this width, one chart per row keeps each readable

const state = {
  catalog: null,
  result: null, // {response, request, effects, replicates}
  metric: null, // the replicate view's metric
  budgetSeq: 0, // the latest budget question; an older answer is dropped
  runSeq: 0, // the latest run; an older answer is dropped
  timer: 0,
  budget: { pending: true }, // the budget line's last state
  budgetKey: "", // the form's request the latest budget answer is for
  running: false,
  policyRows: 0, // policy rows made so far, for their label ids
  loadSeq: 0, // the latest address loaded; a slower earlier one never runs // a study is in flight: Run stays disabled whatever the budget says
  drawnWidth: 0,
  written: "", // the last #request= this page wrote
};

// -- the form -------------------------------------------------------------------------------------

function renderForm(request) {
  const cat = state.catalog;
  const checks = (list, chosen, name) => list
    .map(x => `<label><input type="checkbox" name="${name}" value="${esc(x)}" ${chosen.includes(x) ? "checked" : ""}/>${esc(x.replaceAll("_", " "))}</label>`)
    .join("");
  $("#interventions").innerHTML = checks(cat.interventions.filter(n => n !== "baseline"), request.interventions, "intervention");
  $("#outcomes").innerHTML = checks(cat.outcomes, request.outcomes, "outcome");
  $("#policies").innerHTML = "";
  for (const p of request.policies) addPolicyRow(p);
  const most = cat.effects.max_replicates;
  $("#replicates").max = String(most);
  $("#replicates").value = String(request.replicates);
  $("#replicatesHint").textContent = `from 2 to ${most}`;
  $("#confidence").innerHTML = CONFIDENCES.map(c => `<option value="${c}" ${c === request.confidence ? "selected" : ""}>${c * 100} %</option>`).join("");
  limitChecks();
}

function addPolicyRow(p = {}) {
  const cat = state.catalog;
  const kind = cat.policies.some(c => c.kind === p.kind) ? p.kind : cat.policies[0].kind;
  const row = document.createElement("div");
  row.className = "policy";
  row.dataset.n = String(++state.policyRows); // a unique id for each row's labels
  const drawParams = k => {
    const spec = cat.policies.find(c => c.kind === k);
    row.querySelector(".params").innerHTML = spec.params.map(pr => {
      const val = p.kind === k && p[pr.name] != null ? p[pr.name] : pr.default;
      const bounds = pr.exclusive ? "" : `${pr.min != null ? ` min="${esc(pr.min)}"` : ""}${pr.max != null ? ` max="${esc(pr.max)}"` : ""}`;
      const id = `policy-${row.dataset.n}-${pr.name}`;
      return `<div class="ctrl"><label for="${esc(id)}">${esc(pr.name.replaceAll("_", " "))}</label>`
        + `<input id="${esc(id)}" type="number" data-param="${esc(pr.name)}" value="${esc(val)}" step="${pr.type === "int" ? 1 : 0.005}"${bounds}/></div>`;
    }).join("");
  };
  row.innerHTML = `<div class="ctrl"><label for="policy-${row.dataset.n}">Policy</label><select id="policy-${row.dataset.n}" class="kind-select">${cat.policies.map(c => `<option ${c.kind === kind ? "selected" : ""}>${esc(c.kind)}</option>`).join("")}</select></div>`
    + `<span class="params" style="display:contents"></span><button type="button" class="remove-policy" aria-label="Remove this policy">×</button>`;
  $("#policies").append(row);
  drawParams(kind);
  row.querySelector(".kind-select").addEventListener("change", e => {
    drawParams(e.target.value);
    formChanged();
  });
  row.querySelector(".remove-policy").addEventListener("click", () => {
    row.remove();
    formChanged();
  });
}

// At most max_per_list of each list; the last policy cannot be removed.
function limitChecks() {
  const max = state.catalog.max_per_list;
  for (const name of ["intervention", "outcome"]) {
    const boxes = [...document.querySelectorAll(`#study input[name=${name}]`)];
    const n = boxes.filter(b => b.checked).length;
    for (const b of boxes) b.disabled = !b.checked && n >= max;
  }
  const rows = document.querySelectorAll("#policies .policy");
  $("#addPolicy").disabled = rows.length >= max;
  rows.forEach(r => (r.querySelector(".remove-policy").disabled = rows.length <= 1));
}

function readForm() {
  const picked = name => [...document.querySelectorAll(`#study input[name=${name}]:checked`)].map(b => b.value);
  const policies = [...document.querySelectorAll("#policies .policy")].map(row => {
    const p = { kind: row.querySelector(".kind-select").value };
    for (const input of row.querySelectorAll("[data-param]")) {
      // text a number field cannot parse reads as "": send nothing the server would take as a default
      p[input.dataset.param] = input.validity.badInput || input.value.trim() === "" ? NaN : Number(input.value);
    }
    return p;
  });
  const replicates = $("#replicates");
  return {
    interventions: picked("intervention"),
    policies,
    outcomes: picked("outcome"),
    replicates: replicates.validity.badInput || replicates.value.trim() === "" ? NaN : Number(replicates.value),
    confidence: Number($("#confidence").value),
  };
}

function formChanged() {
  limitChecks();
  // "input" and then "change" fire for one edit (the change as the field loses focus, often to the
  // Run button's click): only a different request waits for a new answer, so that click still runs
  const key = JSON.stringify(readForm());
  if (key === state.budgetKey) return;
  state.budgetKey = key;
  showBudget({ pending: true }); // Run waits for the server's answer on what the form now holds
  state.budgetSeq++; // an answer already in flight is for the form before this edit
  clearTimeout(state.timer);
  state.timer = setTimeout(checkBudget, 250);
}

// The server's answer to "is this within budget?", asked while the user edits (check_only).
// Resolves to that answer, or null when the form is invalid, the request fails or a later edit superseded it.
async function checkBudget() {
  const request = readForm();
  state.budgetKey = JSON.stringify(request);
  const seq = ++state.budgetSeq;
  const problem = requestError(request, state.catalog);
  $("#replicates").setAttribute("aria-invalid", /^Replicates/.test(problem ?? "") ? "true" : "false");
  if (problem) {
    showBudget({ error: problem });
    return null;
  }
  showBudget({ pending: true });
  try {
    const answer = await api("/effects", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ ...request, check_only: true }),
    });
    if (seq !== state.budgetSeq) return null;
    showBudget({ answer });
    return answer;
  } catch (err) {
    if (seq === state.budgetSeq) showBudget({ error: err.detail ?? err.message });
    return null;
  }
}

function showBudget(shown) {
  const { answer = null, error = null, pending = false } = shown;
  state.budget = shown; // what the budget line says, restored when a run ends
  const box = $("#budget");
  const fill = box.querySelector(".meter span");
  const text = box.querySelector(".btext");
  box.classList.toggle("error", !!error);
  if (pending) {
    $("#run").disabled = true;
    text.textContent = "Checking the work budget…";
    return;
  }
  if (error) {
    box.classList.remove("over");
    fill.style.width = "0";
    text.textContent = error;
    $("#run").disabled = true;
    return;
  }
  const view = budgetView(answer);
  box.classList.toggle("over", view.over);
  fill.style.width = `${(view.share * 100).toFixed(1)}%`;
  text.textContent = view.text;
  $("#run").disabled = view.over || state.running;
}

// -- the run --------------------------------------------------------------------------------------

async function run(request = readForm()) {
  const problem = requestError(request, state.catalog);
  if (problem) return showBudget({ error: problem });
  const seq = ++state.runSeq;
  state.written = requestHash(request);
  if (location.hash !== state.written) history.replaceState(null, "", state.written);
  rememberAddress();
  const result = $("#result");
  result.classList.add("busy");
  result.setAttribute("aria-busy", "true");
  if (!state.result) result.innerHTML = `<div class="notice">Running ${request.replicates} paired replicates…</div>`;
  $("#run").disabled = true;
  state.running = true;
  try {
    const response = await api("/effects", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(request) });
    if (seq === state.runSeq) renderResult(response, request);
  } catch (err) {
    if (seq === state.runSeq) {
      state.result = null;
      result.innerHTML = `<div class="notice bad"><b>The study did not run.</b> ${esc(err.detail ?? err.message)}</div>`;
    }
  } finally {
    if (seq === state.runSeq) {
      state.running = false;
      result.classList.remove("busy");
      result.setAttribute("aria-busy", "false");
      showBudget(state.budget); // Run again follows the budget answer for the form as it now is
    }
  }
}

// -- the result -----------------------------------------------------------------------------------

function renderResult(response, request) {
  const effects = records(response);
  const replicates = records(response.replicates);
  state.result = { response, request, effects, replicates };
  const groups = byMetric(effects);
  const metrics = groups.map(g => g.metric);
  // the replicate view opens on the first metric with an effect distinguishable from 0
  if (!metrics.includes(state.metric)) state.metric = (groups.find(g => g.rows.some(r => !coversZero(r))) ?? groups[0])?.metric ?? null;

  const n = effects[0]?.replicates ?? request.replicates;
  const spec = response.spec ?? {};
  const shown = effects.filter(r => !coversZero(r)).length;
  const method = effects[0]?.method ?? "";
  let h = `<p class="headline"><b>${shown} of ${effects.length}</b> effects are distinguishable from 0 (${esc(method)}).</p>`;
  h += `<p class="runline">${n} paired replicates of the current world: <b>${esc(spec.n_skus)} SKUs × ${esc(spec.horizon_days)} days</b>,`
    + ` seeds ${esc(spec.seed)} to ${esc(spec.seed + n - 1)}, generator <b>${esc(response.synthesizer)}</b>;`
    + ` ${(response.elapsed_ms / 1000).toFixed(1)} s.</p>`;
  h += legend();
  h += `<div class="metrics" id="charts"></div>`;
  h += `<div class="section"><h3>All effects</h3>${effectsTable(effects, method)}</div>`;
  h += `<div class="section" id="replicateView"><h3>Paired differences per replicate</h3>
    <div class="pick"><label for="repMetric">Metric</label><select id="repMetric">${metrics.map(m => `<option ${m === state.metric ? "selected" : ""}>${esc(m)}</option>`).join("")}</select></div>
    <p class="note">Each dot is one replicate: the intervention's value minus the same replicate's baseline. The tick is their mean, the effect.</p>
    <div id="repChart"></div></div>`;
  h += `<div class="actions">
    <a class="button primary" href="${esc(exploreLink(request, "effects"))}">Open effects in Explore</a>
    <a class="button" href="${esc(exploreLink(request, "replicates"))}">Open replicate rows in Explore</a>
    <span class="muted">Explore repeats this request on the current world and opens its table to pivot.</span></div>`;
  $("#result").innerHTML = h;
  drawCharts();
}

function legend() {
  const mark = color => `<svg width="30" height="12" aria-hidden="true"><line x1="3" x2="27" y1="6" y2="6" stroke="${color}" stroke-width="2" stroke-linecap="round"/>`
    + `<circle cx="15" cy="6" r="4.5" fill="${color}" stroke="${SURFACE}" stroke-width="2"/></svg>`;
  return `<div class="legend effects"><span class="item">${mark(SHOWN)}interval excludes 0</span>`
    + `<span class="item">${mark(MUTED)}interval covers 0: ${COVERS}</span></div>`;
}

function effectsTable(rows, method, { metric = true } = {}) {
  const head = `${metric ? "<th>Metric</th>" : ""}<th>Intervention</th><th>Policy</th><th class="num">Baseline mean</th><th class="num">Treated mean</th>`
    + `<th class="num">Effect</th><th class="num">Interval (${esc(method.replace(/^paired t, /, ""))})</th><th class="num">Relative change</th><th>Reading</th>`;
  const body = rows.map(r => `<tr class="${coversZero(r) ? "covers" : ""}">${metric ? `<td>${esc(r.metric)}</td>` : ""}<td>${esc(r.intervention)}</td><td>${esc(r.policy)}</td>`
    + `<td class="num">${amount(r.baseline)}</td><td class="num">${amount(r.treated)}</td><td class="num">${amount(r.effect, { signed: true })}</td>`
    + `<td class="num">${intervalText(r)}</td><td class="num">${relativeText(r.relative_effect)}</td><td class="reading">${esc(reading(r))}</td></tr>`).join("");
  return `<div class="tablewrap"><table class="effects"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
}

function drawCharts() {
  const r = state.result;
  const box = $("#charts");
  if (!r || !box) return;
  const width = Math.max(320, box.clientWidth);
  state.drawnWidth = box.clientWidth;
  const two = width >= TWO_COLUMNS && byMetric(r.effects).length > 1;
  box.classList.toggle("two", two);
  const w = two ? Math.floor((width - 22) / 2) : width;
  const method = r.effects[0]?.method ?? "";
  const tip = $("#tooltip");
  const groups = byMetric(r.effects);
  box.innerHTML = groups.map((g, i) => {
    const moved = g.rows.filter(x => !coversZero(x)).length;
    return `<section class="metric" data-block="${i}"><h3>${esc(g.metric)} <span class="muted">· ${moved} of ${g.rows.length} distinguishable from 0</span></h3>`
      + `<div class="plot"></div><details class="tableview"><summary>Table view</summary>${effectsTable(g.rows, method, { metric: false })}</details></section>`;
  }).join("");
  groups.forEach((g, i) => {
    const block = box.querySelector(`[data-block="${i}"]`);
    const chart = rowChart(g.rows, { width: w, metric: g.metric, method });
    block.querySelector(".plot").innerHTML = chart.svg;
    bindBars(block, chart.tips, tip);
  });
  drawReplicates();
}

function drawReplicates() {
  const r = state.result;
  const box = $("#repChart");
  if (!r || !box) return;
  const rows = replicateRows(r.effects, r.replicates, state.metric);
  const chart = rowChart(rows, { width: Math.max(320, box.clientWidth), metric: state.metric, dots: true });
  box.innerHTML = chart.svg;
  bindBars(box, chart.tips, $("#tooltip"));
}

/**
 * One row per intervention × policy on a horizontal axis with a zero line. As intervals:
 * a point at the effect and a line across the interval, the reading beside it. As dots:
 * each replicate's paired difference, with a tick at their mean (the effect).
 * Returns {svg, tips} for bindBars.
 */
function rowChart(rows, { width, metric, method = "", dots = false }) {
  // the label column takes what the longest label needs, up to 40 % of the chart; a longer one is clipped (the tooltip has it whole)
  const labelW = Math.min(Math.max(160, width * 0.4), Math.max(96, Math.max(...rows.map(r => rowLabel(r).length)) * CHAR + 14));
  const right = dots ? 18 : 156;
  const top = 6, rowH = 36, axisH = 24;
  const plotW = Math.max(120, width - labelW - right);
  const height = top + rows.length * rowH + axisH;
  const values = rows.flatMap(r => (dots ? [...r.dots.map(d => d.difference), r.effect] : [r.ci_low, r.ci_high, r.effect]));
  const scale = axisFor(values, Math.max(2, Math.round(plotW / 110)));
  const X = v => labelW + ((v - scale.lo) / (scale.hi - scale.lo)) * plotW;
  const big = Math.max(...scale.ticks.map(Math.abs)) >= 10000;
  const tick = big ? v => new Intl.NumberFormat(undefined, { notation: "compact", maximumFractionDigits: 1 }).format(v).replace("-", "−") : v => amount(v);

  const what = dots ? "paired differences per replicate" : "effects with their intervals";
  let s = `<svg class="chart" role="img" aria-label="${esc(`${metric}: ${what}`)}" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">`;
  s += `<g class="grid">`;
  for (const t of scale.ticks) s += `<line x1="${X(t)}" x2="${X(t)}" y1="${top}" y2="${height - axisH}"/>`;
  s += `</g><line class="zero" x1="${X(0)}" x2="${X(0)}" y1="${top}" y2="${height - axisH}"/>`;
  for (const t of scale.ticks) s += `<text x="${X(t)}" y="${height - 8}" text-anchor="middle">${esc(tick(t))}</text>`;

  const tips = [];
  rows.forEach((r, i) => {
    const y = top + i * rowH, cy = y + rowH / 2;
    const covers = coversZero(r);
    const color = covers ? MUTED : SHOWN;
    const label = rowLabel(r);
    const said = dots
      ? `${label}: ${r.dots.length} paired differences, mean ${amount(r.effect, { signed: true })}`
      : `${label}: effect ${amount(r.effect, { signed: true })}, interval ${intervalText(r)}, ${reading(r)}`;
    s += `<g class="band" tabindex="0" data-tip="${i}" aria-label="${esc(said)}">`;
    s += `<rect class="hit" x="0" y="${y}" width="${width}" height="${rowH}"/>`;
    s += `<text class="label" x="${labelW - 12}" y="${cy + 4}" text-anchor="end">${esc(clip(label, Math.floor((labelW - 14) / CHAR)))}</text>`;
    if (dots) {
      r.dots.forEach((d, k) => {
        if (d.difference == null) return;
        const jitter = ((k % 5) - 2) * 3; // a small vertical spread, so equal differences stay countable
        s += `<circle cx="${X(d.difference).toFixed(1)}" cy="${cy + jitter}" r="3.5" fill="${color}" fill-opacity=".85" stroke="${SURFACE}" stroke-width="1.5"/>`;
      });
      s += `<line x1="${X(r.effect)}" x2="${X(r.effect)}" y1="${cy - 11}" y2="${cy + 11}" style="stroke:var(--ink)" stroke-width="2" stroke-linecap="round"/>`;
    } else {
      const a = X(r.ci_low), b = X(r.ci_high);
      s += `<line x1="${a}" x2="${b}" y1="${cy}" y2="${cy}" stroke="${color}" stroke-width="2" stroke-linecap="round"/>`;
      for (const x of [a, b]) s += `<line x1="${x}" x2="${x}" y1="${cy - 5}" y2="${cy + 5}" stroke="${color}" stroke-width="2" stroke-linecap="round"/>`;
      s += `<circle cx="${X(r.effect)}" cy="${cy}" r="5" fill="${color}" stroke="${SURFACE}" stroke-width="2"/>`;
      const tx = labelW + plotW + 12;
      s += covers
        ? `<text class="value" x="${tx}" y="${cy - 2}">${esc(amount(r.effect, { signed: true }))}</text><text class="covers" x="${tx}" y="${cy + 11}">${esc(COVERS)}</text>`
        : `<text class="value" x="${tx}" y="${cy + 4}">${esc(amount(r.effect, { signed: true }))}</text>`;
    }
    s += `</g>`;
    tips.push(dots ? dotTip(r, color) : intervalTip(r, color, method));
  });
  return { svg: s + `</svg>`, tips };
}

function intervalTip(r, color, method) {
  const none = "transparent";
  return {
    head: `${r.metric} · ${rowLabel(r)}`,
    lines: [
      { color, label: "effect", value: amount(r.effect, { signed: true }) },
      { color: none, label: `interval (${method.replace(/^paired t, /, "")})`, value: intervalText(r) },
      { color: none, label: "baseline mean", value: amount(r.baseline) },
      { color: none, label: "treated mean", value: amount(r.treated) },
      { color: none, label: "relative change", value: relativeText(r.relative_effect) },
      { color: none, label: `${r.replicates} replicates`, value: reading(r) },
    ],
  };
}

function dotTip(r, color) {
  return {
    head: `${r.metric} · ${rowLabel(r)}`,
    lines: [
      { color: "var(--ink)", label: "mean, the effect", value: amount(r.effect, { signed: true }) },
      ...r.dots.map(d => ({ color, label: `replicate ${d.replicate}, seed ${d.seed}`, value: amount(d.difference, { signed: true }) })),
    ],
  };
}

// -- wiring ---------------------------------------------------------------------------------------

async function loadFromAddress() {
  // a new address is a new study: the previous result, and any run still in flight, no longer apply
  const load = ++state.loadSeq;
  state.written = location.hash; // the address this page now shows: going back to an earlier one reloads it
  rememberAddress();
  state.runSeq++;
  state.running = false;
  state.result = null;
  $("#result").classList.remove("busy");
  $("#result").setAttribute("aria-busy", "false");
  $("#result").innerHTML = `<div class="notice">Choose the interventions and what to measure, then run the study.</div>`;
  const link = readRequestHash(location.hash);
  const { request, dropped } = fitRequest(link?.request ?? null, state.catalog);
  renderForm(request);
  const budget = checkBudget();
  const asked = state.budgetKey; // the form as the budget question saw it
  if (link?.error) {
    $("#result").innerHTML = `<div class="notice bad"><b>This link cannot be opened:</b> ${esc(link.error)}. The form shows the default study.</div>`;
    return;
  }
  if (dropped.length) {
    $("#result").innerHTML = `<div class="notice bad">This link names what this installation does not offer: <b>${esc(dropped.join(", "))}</b>. Check the form, then run the study.</div>`;
    return;
  }
  if (!link?.request) return;
  // a link reproduces its study, once the server says it is within budget; else the budget line says why not
  const answer = await budget;
  if (load !== state.loadSeq) return; // another address was opened meanwhile
  if (answer?.within_budget && state.budgetKey === asked) run(readForm()); // unless the user edited meanwhile
  else if (answer && !answer.within_budget) {
    $("#result").innerHTML = `<div class="notice bad"><b>This link's study is over the work budget,</b> so it was not run. Lower the replicates or the lists, then run it.</div>`;
  }
}

async function init() {
  const form = $("#study");
  form.addEventListener("change", formChanged);
  form.addEventListener("input", formChanged);
  form.addEventListener("submit", e => {
    e.preventDefault();
    run();
  });
  $("#addPolicy").addEventListener("click", () => {
    addPolicyRow(nextPolicy(state.catalog, readForm().policies));
    formChanged();
  });
  $("#result").addEventListener("change", e => {
    if (e.target.id !== "repMetric") return;
    state.metric = e.target.value;
    drawReplicates();
  });
  // the charts are drawn at a fixed width, so a change of the result's width redraws them
  let pending = 0;
  new ResizeObserver(() => {
    cancelAnimationFrame(pending);
    pending = requestAnimationFrame(() => {
      const box = $("#charts");
      if (state.result && box && box.clientWidth !== state.drawnWidth) drawCharts();
    });
  }).observe($("#result"));
  addEventListener("hashchange", route);
  route();
}

// -- the two views --------------------------------------------------------------------------------

// The address picks the view: #estimate… is the estimation view, anything else this one.
// Each view keeps its own last address, so switching tabs returns to where it was.
async function route() {
  if (readEstimateHash(location.hash) !== null) {
    showView("estimate");
    routeEstimate({ onAddress: hash => ($("#tabEstimate").href = hash) });
    return;
  }
  showView("simulate");
  if (!state.catalog) {
    catalogLoad ??= api("/experiments/catalog"); // one load, however many addresses arrive meanwhile
    let catalog;
    try {
      catalog = await catalogLoad;
    } catch (err) {
      catalogLoad = null; // a later visit tries again
      $("#result").innerHTML = `<div class="notice bad"><b>Could not load the catalogue.</b> ${esc(err.detail ?? err.message)}</div>`;
      return;
    }
    if (state.catalog) return; // an earlier call, waiting on the same load, has already shown the view
    state.catalog = catalog;
    if (readEstimateHash(location.hash) !== null) return; // the user moved to the other view while it loaded
    loadFromAddress();
  } else if (location.hash !== state.written) {
    loadFromAddress();
  }
}

let catalogLoad = null; // the experiment catalogue's load, shared by every call made while it runs

function showView(which) {
  const estimate = which === "estimate";
  $("#simulateView").hidden = estimate;
  $("#estimateView").hidden = !estimate;
  $("#tabSimulate").setAttribute("aria-selected", String(!estimate));
  $("#tabEstimate").setAttribute("aria-selected", String(estimate));
  if (estimate) $("#tabEstimate").href = location.hash;
  $("#tooltip").hidden = true;
}

function rememberAddress() {
  $("#tabSimulate").href = state.written || "#";
}

init();

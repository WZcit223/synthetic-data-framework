// The Synthesizers page: the catalogue of synthesis algorithms, a run form built
// from each one's parameters, and the run's scores with real and synthetic data
// side by side. Every number comes from the API; this page only lays it out.
import { $, api, esc, valueFormatter } from "./common.js";
import { bindLine, lineChart } from "./chart.js";
import { SERIES } from "./palette.js";
import { boundsText, column, exploreLink, histogram, readParam } from "./synthesis.js";

const PRODUCES = { series: "Series", table: "Table", warehouse: "Warehouse" };
const ORIGIN = { builtin: "Built-in", plugin: "Plug-in", runtime: "Registered at runtime" };
const REAL = SERIES[0], SYNTH = SERIES[1];
const SERIES_WINDOW = 240; // steps of a series drawn at once; the whole run is one click away in Explore

const state = { catalogue: [], unavailable: {}, sources: [], selected: null, seq: 0 };

// -- catalogue ------------------------------------------------------------------------------------

function renderCatalogue() {
  $("#catalogue").innerHTML = state.catalogue.map(s => `
    <button type="button" class="scard" data-name="${esc(s.name)}" aria-current="${s.name === state.selected}">
      <div class="name">${esc(s.name)}</div>
      <div class="desc">${esc(s.description)}</div>
      <div class="tags">
        <span class="tag2 ${esc(s.produces)}">${esc(PRODUCES[s.produces] ?? s.produces)}</span>
        <span class="tag2">${esc(ORIGIN[s.origin] ?? s.origin)}</span>
        ${s.requires.length ? `<span class="tag2" title="modules it needs">needs ${esc(s.requires.join(", "))}</span>` : ""}
      </div>
    </button>`).join("") || `<div class="notice">No synthesizer is installed.</div>`;
  const broken = Object.entries(state.unavailable);
  $("#unavailable").innerHTML = broken.length
    ? `<div class="unavail"><h3>Unavailable</h3><ul>${broken.map(([n, why]) => `<li><b>${esc(n)}</b>: ${esc(why)}</li>`).join("")}</ul></div>`
    : "";
}

function select(name) {
  state.selected = name;
  state.seq++; // a run still in flight belongs to the previous choice
  history.replaceState(null, "", `#${encodeURIComponent(name)}`);
  renderCatalogue();
  renderPanel();
}

// -- the run panel --------------------------------------------------------------------------------

function control(p) {
  const hint = [p.nullable ? "empty: none" : "", boundsText(p)].filter(Boolean).join(" · ");
  if (p.type === "bool") {
    return `<div class="ctrl"><label class="checkline"><input type="checkbox" data-param="${esc(p.name)}" ${p.default ? "checked" : ""}/>${esc(p.name)}</label>
      <div class="err" data-err="${esc(p.name)}"></div></div>`;
  }
  const numeric = p.type === "int" || p.type === "float";
  const attrs = numeric
    ? `type="number" step="${p.type === "int" ? 1 : "any"}"${!p.exclusive && p.min != null ? ` min="${esc(p.min)}"` : ""}${!p.exclusive && p.max != null ? ` max="${esc(p.max)}"` : ""}`
    : `type="text"`;
  return `<div class="ctrl"><label for="p-${esc(p.name)}">${esc(p.name.replaceAll("_", " "))}</label>
    <input id="p-${esc(p.name)}" ${attrs} data-param="${esc(p.name)}" value="${esc(p.default ?? "")}"/>
    <div class="hint">${esc(hint)}</div><div class="err" data-err="${esc(p.name)}"></div></div>`;
}

function renderPanel() {
  const s = state.catalogue.find(x => x.name === state.selected);
  if (!s) {
    $("#panel").innerHTML = `<div class="notice">Choose a synthesizer on the left.</div>`;
    return;
  }
  let h = `<h2>${esc(s.name)}</h2><p class="about">${esc(s.description)}</p>`;
  if (s.produces === "warehouse") {
    h += `<div class="notice">This synthesizer builds the whole warehouse world rather than a series or a table, so it is not
      scored against a sample. Choose it as the <b>Generator</b> on the <a href="index.html">Dashboard</a> to build the world with it.</div>`;
    $("#panel").innerHTML = h;
    return;
  }
  if (!state.sources.length) {
    h += `<div class="notice bad">The server found no sample data to run on. Start the API from the repository folder, or set
      <code>SDF_DATA_DIR</code> to the folder that holds <code>sample_online_retail_ii.csv</code>.</div>`;
    $("#panel").innerHTML = h;
    return;
  }
  h += `<form class="runform" id="runform" novalidate>
    <div class="ctrl"><label for="src">Real data</label>
      <select id="src">${state.sources.map(x => `<option value="${esc(x.id)}">${esc(x.label)}</option>`).join("")}</select>
      <div class="hint">fitted on, then compared with</div></div>
    ${s.params.map(control).join("")}
    <button type="submit" class="primary go" id="run">Run</button>
  </form>
  <div class="result" id="result"><div class="notice">${s.produces === "series"
    ? "A series synthesizer learns the sample's hourly demand; the run scores how close its series comes (fidelity)."
    : "A table synthesizer learns the sample's order lines (quantity, price, hour, weekday); the run scores how close its rows come to real ones (privacy)."}</div></div>`;
  $("#panel").innerHTML = h;
}

function readForm(s) {
  const params = {};
  let ok = true;
  for (const p of s.params) {
    const input = document.querySelector(`[data-param="${CSS.escape(p.name)}"]`);
    const read = readParam(p, p.type === "bool" ? input.checked : input.value);
    document.querySelector(`[data-err="${CSS.escape(p.name)}"]`).textContent = read.error ?? "";
    input.setAttribute("aria-invalid", read.error ? "true" : "false");
    if (read.error) ok = false;
    else params[p.name] = read.value;
  }
  return ok ? params : null;
}

async function run() {
  const s = state.catalogue.find(x => x.name === state.selected);
  const params = readForm(s);
  if (!params) return;
  const body = { synthesizer: s.name, source: $("#src").value, params };
  const seq = ++state.seq;
  const result = $("#result");
  result.classList.add("busy");
  result.setAttribute("aria-busy", "true");
  $("#run").disabled = true;
  try {
    const r = await api("/synthesis/runs", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
    if (seq === state.seq) renderResult(r);
  } catch (err) {
    if (seq === state.seq) result.innerHTML = `<div class="notice bad"><b>The run did not complete.</b> ${esc(err.detail ?? err.message)}</div>`;
  } finally {
    if (seq === state.seq) {
      result.classList.remove("busy");
      result.setAttribute("aria-busy", "false");
      $("#run").disabled = false;
    }
  }
}

// -- the result -----------------------------------------------------------------------------------

const num = (v, digits) => (v == null ? "–" : Number(v).toLocaleString(undefined, { minimumFractionDigits: digits, maximumFractionDigits: digits }));
const signedPct = v => (v == null ? "–" : `${v > 0 ? "+" : ""}${num(v, 1)} %`);

function tiles(r) {
  const m = r.metrics;
  const list = r.kind === "series"
    ? [
        [`${num(m.fidelity_score, 1)}`, "Fidelity score", "out of 100: low KS and high profile correlation"],
        [num(m.ks_statistic, 4), "KS statistic", "0 = the same distribution of values"],
        [num(m.profile_corr, 4), "Profile correlation", "1 = the same daily shape"],
        [signedPct(m.mean_delta_pct), "Mean difference", "synthetic against real"],
        [signedPct(m.std_delta_pct), "Spread difference", "standard deviation, synthetic against real"],
      ]
    : [
        [num(m.dcr_median, 4), "Median distance to closest real row", "higher = further from copying a real row"],
        [`${num(m.clone_risk_pct, 1)} %`, "Clone risk", "synthetic rows that nearly duplicate a real one"],
        [String(m.verdict ?? "–"), "Verdict", `${num(m.n_real, 0)} real and ${num(m.n_synth, 0)} synthetic rows compared`],
      ];
  return `<div class="tiles">${list.map(([v, k, h]) => `<div class="tile"><div class="v">${esc(v)}</div><div class="k">${esc(k)}</div><div class="h">${esc(h)}</div></div>`).join("")}</div>`;
}

function legend() {
  return `<div class="legend" style="padding:10px 4px 0"><span class="item"><span class="ln" style="background:${REAL}"></span>real</span>`
    + `<span class="item"><span class="ln" style="background:${SYNTH}"></span>synthetic</span></div>`;
}

function renderResult(r) {
  const used = Object.entries(r.params).map(([k, v]) => `${esc(k)} <b>${esc(JSON.stringify(v))}</b>`).join(" · ");
  const source = state.sources.find(x => x.id === r.source)?.label ?? r.source;
  let h = `<div class="runline">Run of <b>${esc(r.synthesizer)}</b> on <b>${esc(source)}</b>${used ? ` · ${used}` : ""}</div>`;
  h += tiles(r);
  h += `<div class="charts" id="charts"></div>`;
  const link = exploreLink(r);
  h += `<div class="actions">${link
    ? `<a class="button primary" href="${esc(link)}">Open in Explore</a><span class="muted">The same run, repeated with these parameters, as a table to pivot.</span>`
    : `<span class="muted">${esc(r.synthesizer)} has no seed parameter, so its run cannot be repeated exactly and is not offered in Explore.</span>`}</div>`;
  $("#result").innerHTML = h;
  drawCharts(r);
}

function drawCharts(r) {
  const box = $("#charts");
  const width = Math.max(320, box.clientWidth);
  const tip = $("#tooltip");
  if (r.kind === "series") {
    const real = column(r.rows, r.fields, "value", "real");
    const synth = column(r.rows, r.fields, "value", "synthetic");
    const n = Math.min(SERIES_WINDOW, Math.max(real.length, synth.length));
    const fmt = valueFormatter({ unit: "units", agg: "mean" });
    const model = {
      points: Array.from({ length: n }, (_, i) => String(i)),
      series: [
        { name: "real", color: REAL, values: real.slice(0, n) },
        { name: "synthetic", color: SYNTH, values: synth.slice(0, n) },
      ],
      format: fmt,
      compact: v => fmt(v),
      width,
    };
    const { svg, geometry } = lineChart(model);
    box.innerHTML = legend() + `<h3>Demand per step, first ${n.toLocaleString()} of ${real.length.toLocaleString()} steps</h3>${svg}`;
    bindLine(box.querySelector("svg"), { ...model, geometry }, tip);
    return;
  }
  const share = valueFormatter({ showAs: "share_of_total" });
  const measures = r.fields.filter(f => f.kind === "measure");
  const w = width > 900 ? Math.floor((width - 18) / 2) : width;
  const blocks = measures.map(f => {
    const hgram = histogram(column(r.rows, r.fields, f.name, "real"), column(r.rows, r.fields, f.name, "synthetic"));
    const model = {
      points: hgram.labels,
      series: [
        { name: "real", color: REAL, values: hgram.real },
        { name: "synthetic", color: SYNTH, values: hgram.synthetic },
      ],
      format: share,
      compact: v => share(v),
      width: w,
    };
    return { f, model, chart: lineChart(model) };
  });
  box.innerHTML = legend() + `<div class="grid2">${blocks.map((b, i) => `<div data-block="${i}"><h3>${esc(b.f.label)}: share of rows per range</h3>${b.chart.svg}</div>`).join("")}</div>`;
  blocks.forEach((b, i) => bindLine(box.querySelector(`[data-block="${i}"] svg`), { ...b.model, geometry: b.chart.geometry }, tip));
}

// -- wiring ---------------------------------------------------------------------------------------

async function init() {
  $("#catalogue").addEventListener("click", e => {
    const card = e.target.closest(".scard");
    if (card) select(card.dataset.name);
  });
  $("#panel").addEventListener("submit", e => {
    e.preventDefault();
    run();
  });
  let catalogue, sources;
  try {
    [catalogue, sources] = await Promise.all([api("/synthesizers"), api("/synthesis/sources")]);
  } catch (err) {
    $("#panel").innerHTML = `<div class="notice bad"><b>Could not load the synthesizers.</b> ${esc(err.detail ?? err.message)}</div>`;
    return;
  }
  const order = { series: 0, table: 1, warehouse: 2 };
  state.catalogue = catalogue.synthesizers.sort((a, b) => order[a.produces] - order[b.produces] || a.name.localeCompare(b.name));
  state.unavailable = catalogue.unavailable;
  state.sources = sources.sources;
  const wanted = decodeURIComponent(location.hash.slice(1));
  const first = state.catalogue.find(s => s.name === wanted) ?? state.catalogue.find(s => s.produces !== "warehouse") ?? state.catalogue[0];
  if (first) select(first.name);
  else renderCatalogue();
}

init();

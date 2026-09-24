// The dashboard. It reaches the backend only through api() (ui/common.js), so the
// base URL is configurable and every path it uses can be checked against the
// OpenAPI schema.
// UI rule: reshape what the API returned (sort, filter, group, pivot, chart);
// never compute a business number here.
import { $, API, api, esc, fmt } from "./common.js";

const CAPS = [
  {h:"Data management", p:"Multi-source overlay via the DataSourceRegistry; canonical entities keep synthetic & real interchangeable.", t:"Foundation Layer"},
  {h:"Decision support", p:"(s,S) reorder points and order quantities per SKU, sized to a service level.", t:"Application · ALGO-HOOK: newsvendor"},
  {h:"Insight / anomaly", p:"Stockout & dead-stock detection and portfolio KPIs surfaced automatically.", t:"Application · ALGO-HOOK: anomaly model"},
  {h:"Knowledge organisation", p:"Templated narrative insights today; LLM + knowledge-graph is the upgrade path.", t:"Application · ALGO-HOOK: LLM+KG"},
];

for(const id of ["skus","days","dem","stk","seed"]){
  const map={skus:"o_skus",days:"o_days",dem:"o_dem",stk:"o_stk",seed:"o_seed"};
  $("#"+id).addEventListener("input",e=>$("#"+map[id]).textContent=e.target.value);
}

function bars(data, opts={}){
  // data: [{label, value, color}] -> horizontal bar SVG
  const w=opts.w||360, rowH=26, pad=90, max=Math.max(1,...data.map(d=>d.value));
  const h=data.length*rowH+8;
  let s=`<svg viewBox="0 0 ${w} ${h}" width="100%" height="${h}">`;
  data.forEach((d,i)=>{
    const y=i*rowH+6, bw=(w-pad-40)*(d.value/max);
    s+=`<text x="0" y="${y+13}">${esc(d.label)}</text>`;
    s+=`<rect x="${pad}" y="${y+3}" width="${Math.max(2,bw)}" height="15" rx="3" fill="${d.color||'var(--accent)'}"/>`;
    s+=`<text x="${pad+bw+6}" y="${y+15}" style="fill:var(--ink)">${fmt(d.value)}</text>`;
  });
  return s+"</svg>";
}

function lineChart(hist, forecastAvg){
  const w=440,h=180,pad=28;
  if(!hist.length) return `<div class="muted">No demand for this SKU.</div>`;
  const xs=hist.map((d,i)=>i), ys=hist.map(d=>d.qty);
  const maxY=Math.max(1,...ys), n=hist.length;
  const X=i=>pad+(w-pad-8)*(i/Math.max(1,n-1));
  const Y=v=>h-pad-(h-pad-10)*(v/maxY);
  let path=ys.map((v,i)=>`${i?'L':'M'}${X(i).toFixed(1)},${Y(v).toFixed(1)}`).join(" ");
  let s=`<svg viewBox="0 0 ${w} ${h}" width="100%" height="${h}">`;
  s+=`<line x1="${pad}" y1="${h-pad}" x2="${w-8}" y2="${h-pad}" stroke="var(--line)"/>`;
  s+=`<line x1="${pad}" y1="10" x2="${pad}" y2="${h-pad}" stroke="var(--line)"/>`;
  const fy=Y(forecastAvg);
  s+=`<line x1="${pad}" y1="${fy}" x2="${w-8}" y2="${fy}" stroke="var(--warn)" stroke-dasharray="4 3"/>`;
  s+=`<text x="${w-8}" y="14" text-anchor="end" style="fill:var(--warn)">— forecast avg</text>`;
  s+=`<path d="${path}" fill="none" stroke="var(--accent)" stroke-width="2"/>`;
  s+=`<text x="${pad}" y="${h-8}">day 1</text><text x="${w-8}" y="${h-8}" text-anchor="end">day ${n}</text>`;
  s+=`<text x="4" y="16">${maxY}</text>`;
  return s+"</svg>";
}

async function loadOverview(){
  const o = await api("/overview");
  const k=o.kpis;
  $("#kpis").innerHTML = [
    ["Total SKUs",k.total_skus],["Units on hand",k.total_on_hand],
    ["Inventory value","≈ "+fmt(Math.round(k.inventory_value))],
    ["Outbound lines",k.outbound_lines],
    ["Cancel rate",(k.cancel_rate*100).toFixed(1)+"%"],
    ["Express share",(k.express_rate*100).toFixed(1)+"%"],
  ].map(([kk,v])=>`<div class="card kpi"><div class="v">${fmt(v)}</div><div class="k">${kk}</div></div>`).join("");

  $("#caps").innerHTML = CAPS.map(c=>`<div class="card cap"><h3>${c.h}</h3><p>${c.p}</p><span class="tag">${c.t}</span></div>`).join("");

  const abc=Object.entries(o.abc).map(([l,v])=>({label:"Class "+l,value:v,
    color:l==="A"?"var(--a)":l==="B"?"var(--b)":"var(--c)"}));
  $("#abc").innerHTML=bars(abc);
  $("#insights").innerHTML=o.insights.map(x=>`<li>${esc(x)}</li>`).join("");
}

async function loadComparison(){
  const sl = $("#sl") ? $("#sl").value : "0.95";
  const c = await api("/replenishment/comparison?service_level="+sl);
  const [naive, ours] = c.policies;
  $("#cmp").innerHTML = `
    <div style="display:flex;gap:24px;align-items:flex-end;margin-bottom:10px">
      <div><div class="k muted">Fill rate — ${esc(naive.policy)}</div><div class="big badv">${(naive.fill_rate*100).toFixed(1)}%</div></div>
      <div style="font-size:22px;color:var(--muted)">→</div>
      <div><div class="k muted">Fill rate — ${esc(ours.policy)}</div><div class="big good">${(ours.fill_rate*100).toFixed(1)}%</div></div>
    </div>
    <table><thead><tr><th>metric</th><th class="num">${esc(naive.policy)}</th><th class="num">${esc(ours.policy)}</th></tr></thead><tbody>
      ${[["SKUs needing an order","skus_needing_order"],["Safety stock (units)","safety_stock_units"],
         ["Unmet units","unmet_units"],["Holding cost","holding_cost"],["Order cost","order_cost"]]
        .map(([l,k])=>`<tr><td>${l}</td><td class="num">${fmt(naive[k])}</td><td class="num">${fmt(ours[k])}</td></tr>`).join("")}
    </tbody></table>
    <div class="note">Each SKU's ${c.horizon_days}-day demand history is replayed under both policies
      (default cost assumptions). ALGO-HOOK: a stochastic demand and lead-time model gives distributions,
      not one number.</div>`;
}

async function loadMovers(){
  const m = await api("/top-movers?n=8");
  $("#mover").innerHTML = m.map(x=>`<option value="${esc(x.sku_id)}">${esc(x.sku_id)} · ${esc(x.name)} (${esc(x.abc_class)})</option>`).join("");
  if(m.length) await loadSeries();  // part of the refresh, so its failure is reported and it cannot land late
}

async function loadSeries(){
  const sku=$("#mover").value; if(!sku) return;
  const d = await api("/demand-series?sku_id="+encodeURIComponent(sku));
  $("#series").innerHTML=lineChart(d.history,d.forecast_avg_daily);
  $("#seriesMeta").innerHTML=`Forecast ≈ <b>${fmt(d.forecast_avg_daily)}</b> units/day →
    <b>${fmt(d.forecast_total)}</b> over next ${d.forecast_horizon_days} days
    (${d.history.length} days of history).`;
}

function occColor(o){
  // 0 -> panel dim, 0.5 -> blue, 1 -> green
  if(o<0.5){ const t=o/0.5; return `rgb(${28+ (31-28)*t|0},${36+(111-36)*t|0},${48+(235-48)*t|0})`; }
  const t=(o-0.5)/0.5; return `rgb(${31+(46-31)*t|0},${111+(160-111)*t|0},${235+(67-235)*t|0})`;
}

async function loadVision(){
  const [grid, stock] = await Promise.all([
    api("/shelf-occupancy"),
    api("/stocktake"),
  ]);
  const flagged = new Set(stock.discrepancies.map(d=>d.location_id));

  let html="";
  for(const z of grid){
    const cells = z.aisles.flatMap(a=>a.cells);
    html += `<div style="margin-bottom:10px">
      <div style="font-size:11px;color:var(--muted);margin-bottom:4px">${esc(z.zone)}
        <span style="opacity:.6">· ${cells.length} loc</span></div>
      <div style="display:flex;flex-wrap:wrap;gap:3px">`;
    for(const c of cells){
      const ring = flagged.has(c.location_id) ? "box-shadow:0 0 0 2px var(--bad)" : "";
      const tip = `${c.location_id}\noccupancy ${(c.occupancy*100).toFixed(0)}%\nbook ${c.book_units} · vision ${c.est_units}`;
      html += `<div role="img" aria-label="${esc(tip.replace(/\n/g, ", "))}" title="${esc(tip)}" style="width:16px;height:16px;border-radius:3px;
        background:${occColor(c.occupancy)};${ring}"></div>`;
    }
    html += `</div></div>`;
  }
  document.querySelector("#heatmap").innerHTML = html || `<div class="muted">No vision signal.</div>`;

  const mr=(stock.match_rate*100).toFixed(1);
  document.querySelector("#stockSummary").innerHTML = `
    <div style="display:flex;gap:22px;align-items:flex-end">
      <div><div class="k muted">Match rate</div><div class="big good">${mr}%</div></div>
      <div><div class="k muted">Flagged</div><div class="big" style="color:var(--warn)">${stock.flagged}</div></div>
      <div><div class="k muted">Scanned</div><div class="big">${stock.locations_scanned}</div></div>
      <div><div class="k muted">Net variance</div><div class="big ${stock.net_unit_variance<0?'badv':''}">${stock.net_unit_variance>0?'+':''}${stock.net_unit_variance}</div></div>
    </div>`;
  document.querySelector("#stockRows").innerHTML = stock.discrepancies.length
    ? stock.discrepancies.map(d=>`<tr>
        <td>${esc(d.location_id)}</td><td class="num">${d.book_units}</td>
        <td class="num">${d.vision_units}</td>
        <td class="num" style="color:${d.diff<0?'var(--bad)':'var(--warn)'}">${d.diff>0?'+':''}${d.diff}</td>
        <td><span class="pill" style="border-color:${d.direction==='shortage'?'var(--bad)':'var(--warn)'}">${esc(d.direction)}</span></td>
      </tr>`).join("")
    : `<tr><td colspan="5" class="muted">Vision matches the books at these settings.</td></tr>`;
}

async function loadBacktest(){
  const r = await api("/backtest");
  $("#btMeta").innerHTML = `${esc(r.granularity)} granularity · ${r.series_len} points ·
    mean ${fmt(r.series_mean)}/bucket · winner <b style="color:var(--accent2)">${esc(r.best_model)}</b>`;
  $("#btRows").innerHTML = r.results.map((m,i)=>`<tr>
    <td>${i===0?'🏆 ':''}${esc(m.model)}</td>
    <td class="num"><b>${fmt(m.MAE)}</b></td><td class="num">${fmt(m.RMSE)}</td>
    <td class="num">${fmt(m.MAPE_pct)}</td><td class="num">${fmt(m.WAPE_pct)}</td>
    <td class="num">${fmt(m.bias)}</td></tr>`).join("");
}

async function loadSS(){
  const sl = $("#sl").value;
  const r = await api("/replenishment?service_level="+sl);
  $("#ssMeta").innerHTML = `z=${fmt(r.z)} · lead ${r.lead_time_days}d + review ${r.review_days}d ·
    <b>${r.skus_needing_order}</b> SKUs need an order · total safety stock
    <b>${fmt(r.total_safety_stock_units)}</b> units`;
  $("#ssRows").innerHTML = r.rows.map(x=>`<tr>
    <td>${esc(x.sku_id)}</td><td class="num">${fmt(x.avg_daily_demand)}</td>
    <td class="num">${fmt(x.demand_std)}</td><td class="num">${fmt(x.safety_stock)}</td>
    <td class="num">${fmt(x.reorder_point_s)}</td><td class="num">${fmt(x.order_up_to_S)}</td>
    <td class="num"><b>${x.order_qty}</b></td></tr>`).join("");
}

const SAMPLE_Q = ["which SKUs are stockout?","safety stock at 95%?",
  "how good is the forecast?","any demand anomalies?","inventory value?","ABC mix?"];

async function ask(q){
  q = (typeof q === "string") ? q : $("#q").value;
  if(!q) return;
  $("#q").value = q;
  $("#answer").innerHTML = `<span class="muted">…</span>`;
  const r = await api("/ask?q="+encodeURIComponent(q));
  $("#answer").innerHTML = `<span class="pill" style="margin-right:8px">${esc(r.intent)}</span>${esc(r.answer)}`;
}

function renderChips(){
  $("#qchips").innerHTML = SAMPLE_Q.map(q =>
    `<button type="button" class="pill chip" data-question="${esc(q)}">${esc(q)}</button>`).join("");
}

async function loadAnomalies(){
  const a = await api("/demand-anomalies");
  $("#anoMeta").innerHTML = `<b>${a.count}</b> anomalies on a ${a.series_len}-point
    ${esc(a.granularity)} series (period ${a.seasonal_period}).`;
  $("#anoRows").innerHTML = a.anomalies.length ? a.anomalies.map(x=>`<tr>
    <td>${x.index}</td>
    <td><span class="pill" style="border-color:${x.direction==='spike'?'var(--warn)':'var(--bad)'}">${esc(x.direction)}</span></td>
    <td class="num">${fmt(x.value)}</td><td class="num">${fmt(x.expected)}</td>
    <td class="num"><b>${fmt(x.robust_z)}</b></td></tr>`).join("")
    : `<tr><td colspan="5" class="muted">No anomalies at current settings.</td></tr>`;
}

async function agentAsk(q){
  q = (typeof q === "string") ? q : $("#aq").value;
  if(!q){ q = "should I reorder and what's the money impact?"; $("#aq").value = q; }
  $("#aAnswer").innerHTML = `<span class="muted">…</span>`;
  $("#aTrace").innerHTML = ""; $("#aAction").innerHTML = "";
  const r = await api("/agent/ask?q="+encodeURIComponent(q));
  $("#aAnswer").innerHTML = `<span class="pill" style="margin-right:8px">${esc(r.plan.join(" → "))}</span>${esc(r.answer)}`;
  if(r.proposed_actions && r.proposed_actions.length){
    const a = r.proposed_actions[0];
    $("#aAction").innerHTML = `<div style="margin-top:8px"><span class="pill"
      style="border-color:var(--warn)">⏳ proposed: ${esc(a.proposed_action)} ${esc(a.sku_id)} ×${esc(a.quantity)} — ${esc(a.status)}</span></div>`;
  }
  $("#aTrace").innerHTML = r.trace.map(e=>`<tr>
    <td>${e.seq}</td><td>${esc(e.name)}</td>
    <td><span class="pill" style="border-color:${e.status==='ok'?'var(--accent2)':'var(--bad)'}">${esc(e.status)}</span></td>
    <td class="num">${e.duration_ms}</td></tr>`).join("");
}

async function loadImpact(){
  const r = await api("/economics");
  const p = r.period || {};
  $("#impact").innerHTML = `
    <div style="display:flex;gap:22px;align-items:flex-end;flex-wrap:wrap">
      <div><div class="k muted">Annualised net saving</div>
        <div class="big good">≈ ${fmt(r.annualised_net_saving)}</div></div>
      <div><div class="k muted">Stockout-units avoided</div>
        <div class="big">${fmt(r.stockout_units_avoided)}</div></div>
    </div>
    <div class="note">naive ${fmt(r.unmet_units.naive)} → ours ${fmt(r.unmet_units.ours)} unmet units
      over ${r.horizon_days} days · assumes ${(r.assumptions.holding_cost_annual_rate*100).toFixed(0)}% holding,
      95% service. DATA-HOOK: real unit costs.</div>`;
}

async function loadWorkflow(){
  const r = await api("/workflow/run");
  $("#wf").innerHTML = r.trace.map(e=>
    `<span class="pill" style="margin:2px;border-color:${e.status==='ok'?'var(--accent2)':'var(--bad)'}">${e.seq}. ${esc(e.name)} · ${e.duration_ms}ms</span>`).join(" ")
    + `<div style="margin-top:6px">run <b>${esc(r.run.run_id)}</b> · ${r.run.steps} steps · ${r.run.total_ms}ms · ${r.run.errors} errors</div>`;
}

async function loadScenarios(){
  const r = await api("/scenarios");
  $("#scen").innerHTML = r.scenarios.map(s=>`<tr>
    <td>${s.scenario==='baseline'?'<b>'+esc(s.scenario)+'</b>':esc(s.scenario)}</td>
    <td class="num">${fmt(s.outbound_lines)}</td><td class="num">${s.skus_needing_order}</td>
    <td class="num">${fmt(Math.round(s.safety_stock_units))}</td>
    <td class="num" style="color:${s.safety_stock_vs_baseline_pct>0?'var(--warn)':'var(--muted)'}">
      ${s.safety_stock_vs_baseline_pct>0?'+':''}${s.safety_stock_vs_baseline_pct}%</td></tr>`).join("");
}

async function refreshAll(){
  renderChips();
  await Promise.all([loadOverview(),loadComparison(),loadMovers(),
    loadVision(),loadBacktest(),loadSS(),loadAnomalies(),
    loadImpact(),loadWorkflow(),loadScenarios()]);
}

async function loadLimits(){
  // Size the generation sliders to what this backend accepts; keep the page defaults if it cannot say.
  let l;
  try { l = await api("/world/limits"); } catch (err) { console.warn("world limits unavailable:", err.message); return; }
  for (const [id, key] of [["skus","n_skus"],["days","horizon_days"]]) {
    const el = $("#"+id);
    el.min = l[key].min;
    el.max = l[key].max;  // the browser clamps a value outside the new range
    el.dispatchEvent(new Event("input"));  // keep the label in step with the (possibly clamped) value
  }
}

// The warehouse generators this server offers; the current world's is preselected and named.
async function loadGenerators(){
  let catalogue, world;
  try { [catalogue, world] = await Promise.all([api("/synthesizers"), api("/world")]); }
  catch (err) { console.warn("generators unavailable:", err.message); $("#gen").closest(".ctrl").hidden = true; return; }
  const generators = catalogue.synthesizers.filter(s => s.produces === "warehouse");
  $("#gen").innerHTML = generators.map(g => `<option value="${esc(g.name)}" title="${esc(g.description)}">${esc(g.name)}</option>`).join("");
  $("#gen").value = world.synthesizer;
  showGenerator(world.synthesizer);
}

function showGenerator(name){
  $("#genNote").innerHTML = `World built by <b>${esc(name)}</b> (<a href="synthesizers.html">synthesizers</a>).`;
}

async function regen(){
  $("#status").textContent="regenerating…";
  const body={n_skus:+$("#skus").value,horizon_days:+$("#days").value,
    daily_orders_per_a_sku:+$("#dem").value,stockout_pressure:+$("#stk").value,seed:+$("#seed").value,
    synthesizer:$("#gen").value || undefined};
  let g;
  try {
    g = await api("/world",{method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify(body)});
  } catch (err) {
    const why = err.status===409 ? "another generation is running — try again in a moment"
                                 : `rejected: ${err.detail ?? err.status ?? err.message}`;
    $("#status").textContent="✗ "+why;
    return;
  }
  try {
    await refreshAll();
  } catch (err) {
    $("#status").textContent=`✓ generated (${g.generated_ms} ms), but a panel failed to refresh: ${err.message}`;
    return;
  }
  showGenerator(g.synthesizer);
  $("#status").textContent=`✓ updated with ${g.synthesizer} (${g.generated_ms} ms)`;
  setTimeout(()=>$("#status").textContent="",1500);
}

// Every control is wired here: a module's functions are not globals, so the page has no inline handler.
$("#regen").addEventListener("click", regen);
$("#mover").addEventListener("change", () => loadSeries());
$("#sl").addEventListener("change", () => { loadSS(); loadComparison(); });
$("#askBtn").addEventListener("click", () => ask());
$("#q").addEventListener("keydown", e => { if (e.key === "Enter") ask(); });
$("#qchips").addEventListener("click", e => {
  const chip = e.target.closest("[data-question]");
  if (chip) ask(chip.dataset.question);
});
$("#agentBtn").addEventListener("click", () => agentAsk());
$("#aq").addEventListener("keydown", e => { if (e.key === "Enter") agentAsk(); });

for (const a of document.querySelectorAll("a[data-export]")) a.href = API + "/export?entity=" + a.dataset.export;
loadLimits();
loadGenerators();
refreshAll().catch(err => { $("#status").textContent = "✗ could not load: " + err.message; });

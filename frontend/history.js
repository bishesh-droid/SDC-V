/* History: stat tiles with a pass/fail timeline, filterable table, expandable rows, replay and compare. */
import { $, $$, esc, api, download, announce, state, reduced } from "./core.js";
import { icon, panel, statTile, runCountUps, statusPill, reviewedPill, originTag, skeleton, errorState, bindRetry, dataTable, emptyState, pill } from "./ui.js";
import { N, fix, utc, friendlyError, LABELS, TONE } from "./fmt.js";
import { registerView, show, setHistoryCount } from "./chrome.js";
import { openRecord } from "./design.js";
import { counts } from "./result.js";

const host = $("#view-history");
const PAGE = 15;
let page = 0, total = 0, rowsCache = [], table = null, selected = new Set();

host.innerHTML = `<div id="hist-stats" class="tiles tight">${skeleton(2)}</div>` + panel({ title: "Audit history", sub: originTag("deterministic"), crop: true, body: `
  <form class="filters" id="filters" autocomplete="off">
    <div class="search">${icon("search")}<input name="q" type="search" placeholder="Search summary, run id or reviewer" maxlength="80" aria-label="Search runs"></div>
    <select name="status" aria-label="Status"><option value="">Any status</option><option>designed</option><option>needs_engineer</option><option>needs_info</option><option>rejected</option><option>out_of_scope</option><option>refused</option><option>error</option></select>
    <select name="mode" aria-label="Mode"><option value="">Any mode</option><option>chat</option><option>structured</option></select>
    <select name="reviewed" aria-label="Review"><option value="">Reviewed or not</option><option value="true">Reviewed</option><option value="false">Not reviewed</option></select>
    <button type="button" class="btn ghost" id="btn-csv">${icon("export")} Export CSV</button>
    <button type="button" class="btn ghost" id="btn-compare" disabled>Compare selected (0/2)</button></form>
  <div id="hist-table">${skeleton(5)}</div>
  <div class="pager"><button class="btn ghost sm" id="pg-prev" type="button">Previous</button><span id="pg-info" class="hint num"></span><button class="btn ghost sm" id="pg-next" type="button">Next</button></div>
  <div id="hist-extra"></div>` });

const params = () => { const p = new URLSearchParams(); for (const [k, v] of new FormData($("#filters"))) if (v) p.set(k, v); return p; };

function stats(s, recent) {
  const n = (k) => s.by_status[k] || 0;
  const line = recent.length ? `<svg class="spark" viewBox="0 0 ${recent.length * 8} 16" role="img" aria-label="Recent runs, oldest to newest: ${recent.filter((r) => r.status === "designed").length} passed of ${recent.length}" preserveAspectRatio="none">${[...recent].reverse().map((r, i) => `<rect x="${i * 8}" y="${TONE[r.status] === "pass" ? 1 : TONE[r.status] === "fail" ? 10 : 5}" width="6" height="5" class="sp ${TONE[r.status] || "neutral"}"/>`).join("")}</svg>` : "";
  $("#hist-stats").innerHTML = statTile({ value: s.total, label: "runs", spark: line }) + statTile({ value: s.last_24h, label: "last 24 h" }) + statTile({ value: n("designed"), label: "designed" }) + statTile({ value: n("needs_engineer"), label: "needs engineer" })
    + statTile({ value: s.reviewed, label: "reviewed" }) + statTile({ value: s.narrative_source.llm || 0, label: "LLM narratives" }) + statTile({ value: s.narrative_source.template || 0, label: "template" });
  runCountUps($("#hist-stats")); setHistoryCount(s.total);
}

/* ---- expanded row: the stored run */
async function expand(r) {
  const box = document.createElement("div"); box.className = "xbox"; box.innerHTML = skeleton(3);
  try {
    const rec = await api(`/api/runs/${encodeURIComponent(r.id)}`), res = rec.record?.result || {};
    const fe = res.status === "error" ? friendlyError(res.message) : null, i = res.final_input || res.original_input || {};
    box.innerHTML = `${fe ? `<div class="state error-s">${icon("warn")}<div><b>${esc(fe.summary)}</b>${fe.friendly ? `<ul class="chain">${fe.items.map((x) => `<li class="bad"><code>${esc(x.model)}</code>${pill("fail", x.note)}</li>`).join("")}</ul>` : ""}<details class="rawerr"><summary>Technical detail</summary><pre>${esc(fe.raw)}</pre></details></div></div>` : ""}
      <dl class="kv wide"><dt>Mode</dt><dd>${esc(res.mode || r.mode)}</dd><dt>Model used</dt><dd>${esc(rec.record?.llm_model || res.llm_model || "none")}</dd><dt>Narrative</dt><dd>${esc(res.narrative_source || "—")}</dd>
      ${i.span_m ? `<dt>Input</dt><dd>${N(`${String(i.support).replace("_", " ")}, ${i.span_m} m, ${i.b_mm} x ${i.D_mm} mm, cover ${i.cover_mm} mm, M${i.fck}/Fe${i.fy}, DL ${i.dead_load_kN_per_m} + LL ${i.live_load_kN_per_m} kN/m`)}</dd>` : ""}
      ${res.design ? `<dt>Verdicts</dt><dd>${(() => { const c = counts(res); return `${c.n} rules · ${c.fail} failed · ${c.warn} warnings`; })()}</dd>` : ""}
      <dt>Rules fingerprint</dt><dd>${esc(rec.record?.versions?.rules_fingerprint || "—")}</dd></dl>
      <div class="actions"><button class="btn ghost sm" data-open type="button">Open full run</button>${res.design ? `<button class="btn ghost sm" data-md type="button">${icon("dl")} report.md</button>` : ""}<button class="btn ghost sm" data-replay type="button">${icon("play")} Replay run</button></div>`;
    $("[data-open]", box).onclick = () => openRecord(rec);
    const m = $("[data-md]", box); if (m) m.onclick = () => download(`/api/runs/${r.id}/report.md`, `sdcv-${r.id}.md`).catch((e) => announce(e.message));
    $("[data-replay]", box).onclick = () => replay(res);
  } catch (err) { box.innerHTML = errorState({ title: "Could not load this run", text: err.message }); bindRetry(box, () => expand(r)); }
  return box;
}

/* ---- replay: animate the stored stages */
function replay(res) {
  const t = res.trace;
  const stages = t?.length ? t.map((s) => ({ name: s.stage, o: s.origin, note: `${s.ms == null ? "recorded" : fix(s.ms, 0) + " ms"} · ${s.status}` }))
    : [["Brief", "llm"], ["Guardrails", "deterministic"], ["Calculator", "deterministic"], ["Verifier", "deterministic"], ["Reviser", "deterministic"], ["Narrative", res.narrative_source === "llm" ? "llm" : "deterministic"], ["Audit", "deterministic"]].map(([name, o]) => ({ name, o, note: "no timing recorded for this run" }));
  const box = $("#hist-extra"); const id = res.run_id;
  box.innerHTML = panel({ title: `Replay of run ${esc(id)}`, sub: t?.length ? "from the stored trace" : "stored stages (this run predates timing)", body: `<ol class="demo" id="replay">${stages.map((s, i) => `<li data-i="${i}"><span class="n">${i + 1}</span><span class="pkt ${s.o === "llm" ? "llm" : "det"}" aria-hidden="true"></span><div><b>${esc(s.name)} ${originTag(s.o)}</b><span class="d">${esc(s.note)}</span></div></li>`).join("")}</ol>` });
  const lis = $$("#replay li"); let i = 0;
  const paint = () => lis.forEach((li, j) => { li.className = reduced() ? "done" : j < i ? "done" : j === i ? "on" : ""; });
  paint(); if (reduced()) return;
  const h = setInterval(() => { i++; paint(); if (i > lis.length) clearInterval(h); }, 700);
  box.scrollIntoView({ block: "nearest" });
}

/* ---- compare two runs: diff inputs and results */
async function compare() {
  const [a, b] = [...selected];
  const box = $("#hist-extra"); box.innerHTML = panel({ title: "Compare", body: skeleton(4) });
  try {
    const [ra, rb] = await Promise.all([api(`/api/runs/${a}`), api(`/api/runs/${b}`)]);
    const A = ra.record?.result || {}, B = rb.record?.result || {};
    const f = (r, k) => (r.final_input || r.original_input || {})[k], d = (r, k) => (r.design || {})[k];
    const rows = [["Status", LABELS[A.status] || A.status, LABELS[B.status] || B.status], ["Mode", A.mode, B.mode], ["Support", f(A, "support"), f(B, "support")], ["Span (m)", f(A, "span_m"), f(B, "span_m")], ["Width b (mm)", f(A, "b_mm"), f(B, "b_mm")], ["Depth D (mm)", f(A, "D_mm"), f(B, "D_mm")], ["Cover (mm)", f(A, "cover_mm"), f(B, "cover_mm")], ["Concrete fck", f(A, "fck"), f(B, "fck")], ["Steel fy", f(A, "fy"), f(B, "fy")], ["Dead load (kN/m)", f(A, "dead_load_kN_per_m"), f(B, "dead_load_kN_per_m")], ["Live load (kN/m)", f(A, "live_load_kN_per_m"), f(B, "live_load_kN_per_m")],
      ["Mu (kN·m)", d(A, "Mu"), d(B, "Mu")], ["Ast provided (mm²)", d(A, "ast_prov"), d(B, "ast_prov")], ["Stirrup spacing (mm)", d(A, "sv_prov"), d(B, "sv_prov")], ["span/d actual", d(A, "ld_actual"), d(B, "ld_actual")], ["Failed checks", A.design ? counts(A).fail : "—", B.design ? counts(B).fail : "—"], ["Model", ra.record?.llm_model || "none", rb.record?.llm_model || "none"]];
    const fmt = (v) => v === undefined || v === null ? "—" : typeof v === "number" ? fix(v, Number.isInteger(v) ? 0 : 2) : String(v);
    box.innerHTML = panel({ title: "Compare two runs", sub: `<span class="num">${esc(a)}</span> against <span class="num">${esc(b)}</span>`, body: `<div class="tbl-wrap"><table class="tbl"><thead><tr><th>Field</th><th class="r">${esc(a)}</th><th class="r">${esc(b)}</th><th>Difference</th></tr></thead><tbody>${rows.map(([k, x, y]) => { const diff = fmt(x) !== fmt(y); return `<tr class="${diff ? "diff" : ""}"><td>${esc(k)}</td><td class="r num">${N(fmt(x))}</td><td class="r num">${N(fmt(y))}</td><td>${diff ? pill("warn", "differs") : '<span class="mut">same</span>'}</td></tr>`; }).join("")}</tbody></table></div>` });
    box.scrollIntoView({ block: "nearest" });
  } catch (err) { box.innerHTML = errorState({ title: "Could not compare these runs", text: err.message }); bindRetry(box, compare); }
}

async function load() {
  const host_ = $("#hist-table");
  try {
    const p = params(); p.set("limit", PAGE); p.set("offset", page * PAGE);
    const [r, st, recent] = await Promise.all([api("/api/runs?" + p, { raw: true }), api("/api/stats"), api("/api/runs?limit=30")]);
    total = +r.headers.get("X-Total-Count") || 0;
    rowsCache = await r.json();
    stats(st, recent);
    drawTable(host_);
    const from = total ? page * PAGE + 1 : 0, to = Math.min(total, (page + 1) * PAGE);
    $("#pg-info").textContent = `${from}–${to} of ${total}`;
    $("#pg-prev").disabled = page === 0; $("#pg-next").disabled = (page + 1) * PAGE >= total;
  } catch (err) { host_.innerHTML = errorState({ title: "Could not load the history", text: err.message }); bindRetry(host_, load); }
}
function drawTable(host_) {
  const cmpState = () => { const b = $("#btn-compare"); b.disabled = selected.size !== 2; b.textContent = `Compare selected (${selected.size}/2)`; };
  const cols = [
    { key: "sel", label: "", sort: false, render: (r) => `<input type="checkbox" class="selbox" data-sel="${esc(r.id)}" aria-label="Select run ${esc(r.id)} for comparison" ${selected.has(r.id) ? "checked" : ""}>` },
    { key: "created_at", label: "Time (UTC)", cls: "num nowrap", render: (r) => esc(utc(r.created_at)) },
    { key: "id", label: "Run", cls: "clause" }, { key: "mode", label: "Mode" },
    { key: "status", label: "Status", render: (r) => statusPill(r.status) },
    { key: "summary", label: "Summary", cls: "wrapok", render: (r) => N(r.summary || "") },
    { key: "reviewer", label: "Review", cls: "nowrap", render: (r) => r.reviewer ? reviewedPill() + ` <span class="hint">${esc(r.reviewer)}</span>` : '<span class="mut">none</span>' }];
  table = dataTable(host_, { rows: rowsCache, id: "hist-tbl", sortable: false, cols, empty: emptyState({ title: "No runs match", text: "Change the filters, or run a design to create the first entry." }),
    expand: () => `<div class="xph"></div>`, rowCls: (r) => (selected.has(r.id) ? "selrow" : ""),
    after: (h) => {
      $$("[data-sel]", h).forEach((c) => { c.onclick = (e) => { e.stopPropagation(); const id = c.dataset.sel; if (c.checked) { if (selected.size >= 2) { c.checked = false; announce("Select at most two runs"); return; } selected.add(id); } else selected.delete(id); cmpState(); }; });
      $$(".xrow .xph", h).forEach(async (ph) => { const row = ph.closest("tr").previousElementSibling, i = +row.dataset.i; ph.replaceWith(await expand(rowsCache[i])); });
    } });
  cmpState();
}
let ft; $("#filters").addEventListener("input", () => { clearTimeout(ft); ft = setTimeout(() => { page = 0; load(); }, 250); });
$("#filters").addEventListener("submit", (e) => e.preventDefault());
$("#pg-prev").onclick = () => { page = Math.max(0, page - 1); load(); };
$("#pg-next").onclick = () => { page += 1; load(); };
$("#btn-csv").onclick = () => download("/api/runs.csv?" + params(), "sdcv-runs.csv").catch((e) => announce(e.message));
$("#btn-compare").onclick = compare;
registerView("history", { load });

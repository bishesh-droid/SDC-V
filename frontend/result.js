/* Result rendering shared by Form design, History and the Assistant: verdict dashboard, checks, utilisation, drawings, trace. */
import { $, $$, esc, state, api, download, emit, announce, noteRun } from "./core.js";
import { icon, pill, statusPill, originTag, panel, checkCell, utilBar, titleBlock, consoleView, bindCopy, errorState, emptyState, runCountUps } from "./ui.js";
import { N, notation, fix, LABELS, TONE, friendlyError } from "./fmt.js";
import { crossSection, elevation, diagrams, strain } from "./beam.js";

/* rule categories come from /api/system (read once) */
let cats = null;
export async function loadCategories() {
  if (cats) return cats;
  try { const s = await api("/api/system"); cats = Object.fromEntries(s.verifier_rules.map((r) => [r.rule_id, r.category])); state.sys = s; } catch { cats = {}; }
  return cats;
}
const CAT_ORDER = ["Cross-check", "Flexure", "Shear", "Deflection", "Detailing and durability"];
/* the ratios worth a bar; each bar uses the check's own value, limit and op */
const UTIL = ["MU_LIM", "MOMENT_CAPACITY", "XU_MAX", "TAU_V_MAX", "DEFLECTION", "MIN_TENSION_STEEL", "MAX_TENSION_STEEL", "STEEL_CONGESTION"];

/* ------------------------------------------------------------- markdown (escape first, then a tiny subset) */
export function md(src) {
  const out = []; let list = false;
  const inline = (t) => esc(notation(t)).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>");
  for (const line of String(src || "").split("\n")) {
    const h = /^#{1,4}\s+(.*)/.exec(line), li = /^\s*[-*]\s+(.*)/.exec(line);
    if (li) { if (!list) { out.push("<ul>"); list = true; } out.push(`<li>${inline(li[1])}</li>`); continue; }
    if (list) { out.push("</ul>"); list = false; }
    if (h) out.push(`<h4>${inline(h[1])}</h4>`); else if (line.trim()) out.push(`<p>${inline(line)}</p>`);
  }
  if (list) out.push("</ul>");
  return out.join("");
}
const ul = (a) => a && a.length ? `<ul class="errs">${a.map((x) => `<li>${N(x)}</li>`).join("")}</ul>` : "";

/* ------------------------------------------------------------- blocks */
export function counts(res) {
  const c = res.checks || [];
  return { n: c.length, fail: c.filter((x) => !x.passed && x.severity === "error").length, warn: c.filter((x) => !x.passed && x.severity === "warning").length };
}
const WORD = { designed: "PASS", needs_engineer: "NEEDS ENGINEER" };

export function verdictDash(res) {
  const tone = TONE[res.status] || "neutral", c = counts(res), word = WORD[res.status] || (LABELS[res.status] || res.status).toUpperCase();
  const ic = tone === "pass" ? "pass" : tone === "fail" ? "fail" : "warn";
  return `<div class="vd ${tone}"><div class="vd-main">${icon(ic, "vd-ic")}<div><div class="vd-word">${esc(word)}</div><div class="vd-msg">${N(res.message || "")}</div>${res.status === "needs_info" ? "" : ul(res.out_of_scope)}${ul(res.errors)}</div></div>
    <div class="vd-side">${res.design ? `<span class="num">${c.n} rules · ${c.fail} failed · ${c.warn} warnings</span>` : ""}<span class="vd-stamp">${esc(res.stamp || "DRAFT")}</span></div></div>`;
}

export function missingList(res) {
  if (res.status !== "needs_info" || !res.missing?.length) return "";
  return `<div class="checklist" role="list" aria-label="Missing information">${res.missing.map((m) => `<div role="listitem">${icon("warn")}<span>${esc(m.replace(/_/g, " "))}</span></div>`).join("")}</div>`;
}

export function checksGrid(res) {
  const list = res.checks || []; if (!list.length) return "";
  const by = {};
  for (const c of list) (by[cats?.[c.rule_id] || "Checks"] ||= []).push(c);
  const order = [...CAT_ORDER, ...Object.keys(by).filter((k) => !CAT_ORDER.includes(k))].filter((k) => by[k]);
  return `<div class="cgrid">${order.map((k) => `<div class="cg"><h4>${esc(k)}</h4><div class="cg-cells">${by[k].map(checkCell).join("")}</div></div>`).join("")}</div>
    <p class="legend"><span>${icon("pass")} Pass</span><span>${icon("warn")} Warning</span><span>${icon("fail")} Fail</span><span class="hint">Hover or focus a cell for the rule, clause, value and limit.</span></p>`;
}

export function utilPanel(res) {
  const by = Object.fromEntries((res.checks || []).map((c) => [c.rule_id, c]));
  const bars = UTIL.map((id) => by[id]).filter(Boolean).map(utilBar).join("");
  return bars ? `<div class="ubars">${bars}</div>` : "";
}

/* warnings first (meta-rule M3), then failed errors with their action and what the reviser did */
export function attention(res) {
  const bad = (res.checks || []).filter((c) => !c.passed);
  if (!bad.length) return `<p class="hint">${icon("pass")} No failed checks and no warnings in the final design.</p>`;
  const warns = bad.filter((c) => c.severity === "warning"), errs = bad.filter((c) => c.severity !== "warning");
  const its = res.iterations || [];
  const row = (c) => {
    const rev = its.find((i) => i.failed?.includes(c.rule_id));
    return `<li class="att ${c.severity === "warning" ? "warn" : "fail"}"><div>${pill(c.severity === "warning" ? "warn" : "fail", c.severity === "warning" ? "Warning" : "Failed")} <b>${esc(c.title)}</b> <span class="clause">${esc(c.clause)}</span></div><p>${N(c.message)}</p>
      <div class="att-a">${c.severity === "warning" ? "" : `<span class="pill-s neutral">If it fails: ${c.revisable ? "enlarge section" : "needs engineer"}</span>`}${rev ? `<span class="hint">Reviser: ${N(rev.action)}</span>` : ""}</div></li>`;
  };
  return `<ul class="atts">${[...warns, ...errs].map(row).join("")}</ul>`;
}

export function keyNumbers(res) {
  const rows = res.report?.design; if (!rows?.length) return "";
  return `<dl class="kv">${rows.map((r) => `<dt>${N(r.label)}</dt><dd>${N(r.value)}</dd>`).join("")}</dl>`;
}

export function drawingsPanel(res) {
  const des = res.design, inp = res.final_input || res.original_input; if (!des || !inp) return "";
  const parts = [crossSection(des, inp), elevation(des, inp), diagrams(des, inp), strain(des)].filter(Boolean);
  return parts.length ? `<div class="drw-grid">${parts.join("")}</div>` : "";
}

export function revisionList(res) {
  const its = res.iterations || []; if (!its.length) return "";
  return `<ol class="timeline">${its.map((it) => `<li class="${it.failed.length ? "bad" : "ok"}"><span class="num">${fix(it.b, 0)} × ${fix(it.D, 0)} mm</span> — ${it.failed.length ? "failed " + it.failed.map((f) => `<code>${esc(f)}</code>`).join(", ") + ". " : ""}${N(it.action)}</li>`).join("")}</ol>`;
}

export function narrativeBlock(res) {
  const llm = res.narrative_source === "llm";
  return `<div class="narr-h">${originTag(llm ? "llm" : "deterministic")}<span class="hint">${llm ? "Written by Gemini · every number checked against the result" : "Deterministic template (fail-closed)"}</span></div><div class="narr">${md(res.narrative || "")}</div>`;
}

export function eventsBlock(res) {
  const out = [];
  if (res.conversions?.length) out.push(`<h4>Unit conversions applied</h4><ul class="events">${res.conversions.map((c) => `<li><code>${N(c)}</code></li>`).join("")}</ul>`);
  if (res.guardrail_events?.length) out.push(`<h4>Guardrail events <small>${res.guardrail_events.length}</small></h4><ul class="events">${res.guardrail_events.map((e) => `<li><b>${esc(String(e.type || "").replace(/_/g, " "))}</b> <code>${esc(JSON.stringify({ ...e, type: undefined }))}</code></li>`).join("")}</ul>`);
  return out.join("");
}

/* ------------------------------------------------------------- execution trace: waterfall, console, raw JSON */
export function traceView(res) {
  const t = res.trace;
  if (!t?.length) return `<p class="hint">No timings were recorded for this run (runs made before timing was added have none).</p>`;
  const total = t.reduce((a, s) => a + (s.ms || 0), 0) || 1;
  let acc = 0;
  const bars = t.map((s) => {
    const left = (acc / total) * 100, w = Math.max(1.5, ((s.ms || 0) / total) * 100); acc += s.ms || 0;
    return `<div class="wf-r"><span class="wf-n">${originTag(s.origin)} ${esc(s.stage)}</span><div class="wf-t"><i class="${s.origin === "llm" ? "llm" : "det"} ${esc(s.status)}" style="left:${Math.min(left, 99)}%;width:${Math.min(w, 100 - Math.min(left, 99))}%"></i></div><span class="wf-ms num">${s.ms == null ? "—" : fix(s.ms, s.ms < 10 ? 2 : 0) + " ms"}</span><span class="wf-s">${esc(s.status)}</span></div>`;
  }).join("");
  const lines = [...t.map((s) => ({ t: s.ms == null ? "   —" : String(Math.round(s.ms)).padStart(5) + "ms", level: s.status === "error" ? "err" : s.status === "fallback" ? "warn" : "", text: `${s.stage} [${s.origin}] ${s.status}` })),
    ...(res.guardrail_events || []).map((e) => ({ t: "guard", level: /error|reject|injection|unsafe/.test(e.type) ? "warn" : "", text: `${e.type} ${JSON.stringify({ ...e, type: undefined })}` }))];
  const id = "tr" + Math.random().toString(36).slice(2, 7);
  return `<div class="tabs2" data-tabs="${id}"><div role="tablist" class="tab-r"><button role="tab" aria-selected="true" data-t="wf">Waterfall</button><button role="tab" aria-selected="false" data-t="con">Console</button><button role="tab" aria-selected="false" data-t="json">Raw JSON</button></div>
    <div data-p="wf"><div class="wf">${bars}</div><p class="hint">Stage timings are wall-clock and informational. They are never part of the rules fingerprint or any comparison. Total ${fix(total, 0)} ms.</p></div>
    <div data-p="con" hidden>${consoleView(lines)}</div>
    <div data-p="json" hidden>${consoleView([{ text: JSON.stringify({ trace: t, llm_attempts: res.llm_attempts || [] }, null, 1) }])}</div></div>`;
}
export function bindTabs(root) {
  $$("[data-tabs]", root).forEach((g) => {
    const btns = $$("[role=tab]", g);
    btns.forEach((b) => { b.onclick = () => { btns.forEach((x) => x.setAttribute("aria-selected", x === b)); $$("[data-p]", g).forEach((p) => { p.hidden = p.dataset.p !== b.dataset.t; }); }; });
    g.addEventListener("keydown", (e) => { const i = btns.indexOf(document.activeElement); if (i < 0) return; if (e.key === "ArrowRight") { e.preventDefault(); btns[(i + 1) % btns.length].focus(); } if (e.key === "ArrowLeft") { e.preventDefault(); btns[(i - 1 + btns.length) % btns.length].focus(); } });
  });
  bindCopy(root);
}

/* ------------------------------------------------------------- model fallback chain */
const OUT_LABEL = { ok: "OK", timeout: "Timeout", http_404: "HTTP 404", http_429: "HTTP 429 (quota)", http_500: "HTTP 500", http_503: "HTTP 503 (busy)", unusable_output: "Unusable output", network_error: "Network error" };
export function attemptsView(res) {
  const a = res.llm_attempts || [];
  if (!a.length) {
    if (res.llm_model) return `<p class="hint">Answered by <code>${esc(res.llm_model)}</code>. Per-attempt detail was not recorded for this run.</p>`;
    return `<p class="hint">${res.narrative_source === "template" ? "No model answered; the deterministic template was used." : "No model call was made for this run."}</p>`;
  }
  const answered = a.find((x) => x.outcome === "ok");
  return `<ol class="chain">${a.map((x, i) => `<li class="${x.outcome === "ok" ? "ok" : "bad"}"><span class="ch-i">${i + 1}</span><code>${esc(x.model)}</code>${pill(x.outcome === "ok" ? "pass" : "fail", OUT_LABEL[x.outcome] || x.outcome)}<span class="num ch-ms">${x.ms} ms</span></li>`).join("")}</ol>
    <p class="hint">${answered ? `Answered by <code>${esc(answered.model)}</code>.` : "No model answered; the deterministic template was used."}</p>`;
}

/* ------------------------------------------------------------- whole result */
export function resultView(res, { fingerprint } = {}) {
  const parts = [];
  parts.push(titleBlock(res, fingerprint || state.health?.versions?.rules_fingerprint));
  if (res.status === "error") {
    const fe = friendlyError(res.message);
    parts.push(verdictDash({ ...res, message: fe.friendly ? fe.summary : res.message }));
    if (fe.friendly) parts.push(`<details class="rawerr"><summary>Model attempts and technical detail</summary><ul class="chain">${fe.items.map((i) => `<li class="bad"><code>${esc(i.model)}</code>${pill("fail", i.note)}</li>`).join("")}</ul><pre>${esc(fe.raw)}</pre></details>`);
  } else parts.push(verdictDash(res));
  parts.push(missingList(res));
  if (res.design) {
    parts.push(panel({ title: "Verifier checks", sub: `<span class="num">${res.checks.length} rules</span> ${originTag("deterministic")}`, cls: "tight", body: checksGrid(res) + attention(res) }));
    parts.push(panel({ title: "Utilisation", sub: "demand against limit, from the returned values", body: utilPanel(res) || '<p class="hint">No ratio data in this result.</p>' }));
    parts.push(panel({ title: "Design values", sub: originTag("deterministic"), body: keyNumbers(res) }));
    parts.push(panel({ title: "Drawings", sub: "from the returned values", body: drawingsPanel(res) || emptyState({ title: "No drawing data in this result" }) }));
    parts.push(panel({ title: "Section revision", sub: "deterministic reviser: depth +25 mm, then width", body: revisionList(res) }));
    parts.push(panel({ title: "Narrative", body: narrativeBlock(res) }));
  }
  parts.push(panel({ title: "Model fallback chain", sub: originTag("llm"), body: attemptsView(res) }));
  parts.push(panel({ title: "Execution trace", body: traceView(res) }));
  const ev = eventsBlock(res); if (ev) parts.push(panel({ title: "Run events", body: ev }));
  if (res.design) {
    parts.push(`<div class="actions"><button class="btn ghost" id="btn-md" type="button">${icon("dl")} Report (.md)</button><button class="btn ghost" id="btn-print" type="button">Print / save as PDF</button><button class="btn ghost" id="btn-json" type="button">Download JSON</button><button class="btn ghost" id="btn-copy" type="button">${icon("copy")} Copy narrative</button><button class="btn ghost" id="btn-copyid" type="button">Copy run ID</button><button class="btn ghost" id="btn-explore-from" type="button">Explore nearby sections</button></div>
      <form class="review" id="review-form"><input name="reviewer" placeholder="Reviewing engineer (name, reg. no.)" required minlength="2" maxlength="120" aria-label="Reviewing engineer"><input name="note" placeholder="Review note (optional)" maxlength="2000" aria-label="Review note"><button class="btn ghost" type="submit">Log review</button></form>`);
  }
  return parts.join("");
}

export function bindResult(host, res) {
  runCountUps(host); bindTabs(host);
  const on = (id, fn) => { const el = $(id, host); if (el) el.onclick = fn; };
  on("#btn-print", () => print());
  on("#btn-json", () => { const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([JSON.stringify(res, null, 2)], { type: "application/json" })); a.download = `sdcv-${res.run_id}.json`; a.click(); URL.revokeObjectURL(a.href); });
  on("#btn-md", () => download(`/api/runs/${res.run_id}/report.md`, `sdcv-${res.run_id}.md`).catch((e) => announce(e.message)));
  const flash = (e, ok, label) => { e.target.textContent = ok; setTimeout(() => { e.target.innerHTML = label; }, 1500); };
  on("#btn-copy", async (e) => { const l = e.target.innerHTML; try { await navigator.clipboard.writeText(res.narrative || ""); flash(e, "Copied", l); } catch { flash(e, "Copy failed", l); } });
  on("#btn-copyid", async (e) => { const l = e.target.innerHTML; try { await navigator.clipboard.writeText(res.run_id); flash(e, "Copied", l); } catch { flash(e, "Copy failed", l); } });
  on("#btn-explore-from", () => emit("explore:from", res.final_input));
  const rf = $("#review-form", host);
  if (rf) rf.onsubmit = async (e) => {
    e.preventDefault(); const f = Object.fromEntries(new FormData(rf));
    try { await api(`/api/runs/${res.run_id}/review`, { method: "POST", body: f }); rf.innerHTML = `<span class="hint">${icon("pass")} Review by ${esc(f.reviewer)} recorded in the audit log (a log entry, not a certification).</span>`; announce("Review logged"); }
    catch (err) { rf.insertAdjacentHTML("beforeend", `<span class="hint warnline">${esc(err.message)}</span>`); }
  };
}

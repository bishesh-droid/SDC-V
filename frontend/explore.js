/* Explore nearby sections: pass/fail heatmap plus a sortable table. Uses no model and writes nothing to the audit log. */
import { $, $$, esc, api, busy, on } from "./core.js";
import { icon, panel, originTag, skeleton, errorState, bindRetry, dataTable, pill, emptyState } from "./ui.js";
import { N, fix, notation } from "./fmt.js";
import { show, registerView } from "./chrome.js";
import { fieldsHTML, readForm, fillForm, useSection } from "./design.js";

const host = $("#view-explore");
let form, outEl, last = null;

function init() {
  host.innerHTML = panel({ title: "Explore nearby sections", sub: `${originTag("deterministic")} <span class="pill-s neutral">No LLM · nothing written to the audit log</span>`, crop: true, body: `
    <p class="lede">Scans sections around yours (width −50, 0, +50 mm; depth −100 to +300 mm in 25 mm steps) through the same deterministic calculator and rules as a design run.</p>
    <form id="explore-form" autocomplete="off"><div class="fgrid f5">${fieldsHTML("ex")}</div><div class="row"><button type="submit" class="btn primary" id="btn-explore">Scan sections</button></div></form>` })
    + `<div id="explore-out">${panel({ title: "No scan yet", cls: "grid-bg", body: emptyState({ title: "Run a scan to see the heatmap", text: "Each cell is one candidate section: pass, fail or warning, with the lightest passing section outlined." }) })}</div>`;
  form = $("#explore-form"); outEl = $("#explore-out");
  form.addEventListener("submit", (e) => { e.preventDefault(); run(); });
}

async function run() {
  const btn = $("#btn-explore"); busy(btn, true, "Scan sections");
  outEl.innerHTML = panel({ title: "Scanning", body: skeleton(6) });
  try {
    const r = await api("/api/explore", { method: "POST", body: readForm(form) });
    last = r; draw(r);
  } catch (err) { outEl.innerHTML = errorState({ title: "The scan failed", text: err.message }); bindRetry(outEl, run); }
  busy(btn, false, "Scan sections");
}

function draw(r) {
  if (r.status !== "ok") {
    const tone = r.status === "needs_info" ? "warn" : "fail";
    outEl.innerHTML = panel({ title: "Scan not run", body: `<div class="vd ${tone}"><div class="vd-main"><div><div class="vd-word">${esc(r.status.replace("_", " ").toUpperCase())}</div>${(r.errors || []).map((e) => `<p>${N(e)}</p>`).join("")}${(r.missing || []).map((m) => `<p>Missing: ${esc(m)}</p>`).join("")}</div></div></div>` });
    return;
  }
  const best = r.lightest_passing, base = r.base;
  const widths = [...new Set(r.rows.map((x) => x.b))].sort((a, b) => a - b), depths = [...new Set(r.rows.map((x) => x.D))].sort((a, b) => a - b);
  const at = (b, D) => r.rows.find((x) => x.b === b && x.D === D);
  const state_ = (x) => !x ? "none" : x.ok ? (x.warnings?.length ? "warn" : "pass") : "fail";
  const mark = { pass: "pass", warn: "warn", fail: "fail" };
  const head = best ? `Lightest passing section: ${best.b} × ${best.D} mm (${best.bars}, ${best.ast_prov} mm² provided).` : "No section in this scan passes all error-level checks.";
  const cells = depths.map((D) => `<tr><th scope="row" class="num">${D}</th>${widths.map((b) => {
    const x = at(b, D), s = state_(x), isBest = best && b === best.b && D === best.D, isBase = b === base.b && D === base.D;
    return x ? `<td><button type="button" class="hm ${s}${isBest ? " best" : ""}${isBase ? " base" : ""}" data-bw="${b}" data-dd="${D}" data-tip="${esc(`${b} × ${D} mm|${isBest ? "Lightest passing" : isBase ? "Your section" : "Candidate"}|${s === "pass" ? "PASS" : s === "warn" ? "WARN" : "FAIL"}|Ast ${x.ast_req}/${x.ast_prov} mm², span/d ${x.ld_actual}/${x.ld_allow}${x.failed.length ? " · " + x.failed.join(", ") : ""}`)}" aria-label="${b} by ${D} mm: ${s}${isBest ? ", lightest passing" : ""}${isBase ? ", your section" : ""}">${icon(mark[s] === "pass" ? "pass" : mark[s] === "warn" ? "warn" : "fail")}</button></td>` : "<td></td>";
  }).join("")}</tr>`).join("");
  outEl.innerHTML = panel({ title: "Section heatmap", sub: `<span class="num">${r.scanned} scanned · ${r.passing} pass</span>`, body: `
    <p class="lede">${esc(notation(head))}</p>
    <div class="hm-wrap"><table class="hm-t" aria-label="Pass or fail by width and depth"><caption class="sr">Rows are depth D in mm, columns are width b in mm</caption><thead><tr><td class="hm-corner">D \\ b</td>${widths.map((b) => `<th scope="col" class="num">${b}</th>`).join("")}</tr></thead><tbody>${cells}</tbody></table>
    <div class="hm-side"><div class="legend col"><span class="lg pass">${icon("pass")} Pass</span><span class="lg warn">${icon("warn")} Pass with warnings</span><span class="lg fail">${icon("fail")} Fail</span><span class="lg"><i class="sw best"></i> Lightest passing</span><span class="lg"><i class="sw base"></i> Your section</span></div>
    <div id="hm-detail" class="detail" aria-live="polite"><p class="hint">Select a cell for its numbers.</p></div></div></div>
    <p class="hint">${esc(r.note)}</p>` }) + panel({ title: "All sections", sub: "sortable", body: '<div id="ex-table"></div>' });
  $$(".hm", outEl).forEach((bt) => { bt.onclick = () => detail(at(+bt.dataset.bw, +bt.dataset.dd), bt); });
  const rows = r.rows.map((x) => ({ ...x, id: `${x.b}x${x.D}`, area: x.b * x.D, verdict: x.ok ? (x.warnings?.length ? "WARN" : "PASS") : "FAIL" }));
  dataTable($("#ex-table"), { rows, id: "ex-tbl", rowCls: (x) => (x.b === base.b && x.D === base.D ? "base" : "") + (best && x.b === best.b && x.D === best.D ? " best" : ""), cols: [
    { key: "area", label: "b × D (mm)", num: true, render: (x) => `${x.b} × ${x.D}` },
    { key: "verdict", label: "Verdict", render: (x) => `${pill(x.ok ? (x.warnings?.length ? "warn" : "pass") : "fail", x.verdict)}${x.failed.length ? `<small class="mut"> ${esc(x.failed.join(", "))}</small>` : ""}` },
    { key: "ast_prov", label: "Ast req / prov (mm²)", num: true, render: (x) => `${x.ast_req} / ${x.ast_prov}` },
    { key: "pt", label: "pt %", num: true }, { key: "bars", label: "Tension bars" }, { key: "sv", label: "sv (mm)", num: true },
    { key: "ld_actual", label: "span/d act / allow", num: true, render: (x) => `${x.ld_actual} / ${x.ld_allow}` }, { key: "self_weight", label: "Self-wt (kN/m)", num: true },
    { key: "use", label: "", sort: false, render: (x) => x.ok ? `<button class="btn ghost sm" data-use="${x.b},${x.D}" type="button">Use</button>` : "" }],
    after: (h) => $$("[data-use]", h).forEach((b) => { b.onclick = () => use(...b.dataset.use.split(",")); }) });
}

function detail(x, el) {
  const d = $("#hm-detail");
  $$(".hm.sel", outEl).forEach((e) => e.classList.remove("sel")); el.classList.add("sel");
  d.innerHTML = `<h4 class="num">${x.b} × ${x.D} mm</h4>${pill(x.ok ? "pass" : "fail", x.ok ? "Passes error-level checks" : "Fails: " + x.failed.join(", "))}
    <dl class="kv"><dt>Ast required / provided</dt><dd>${x.ast_req} / ${x.ast_prov} mm²</dd><dt>Tension bars</dt><dd>${esc(x.bars)}</dd><dt>pt</dt><dd>${x.pt} %</dd><dt>Stirrup spacing</dt><dd>${x.sv} mm</dd><dt>Mu</dt><dd>${x.Mu} kN·m</dd><dt>span/d actual / allowed</dt><dd>${x.ld_actual} / ${x.ld_allow}</dd><dt>Self-weight</dt><dd>${x.self_weight} kN/m</dd></dl>
    ${x.ok ? `<button class="btn primary sm" data-use2 type="button">Use this section in Form design</button>` : ""}`;
  const u = $("[data-use2]", d); if (u) u.onclick = () => use(x.b, x.D);
}
function use(b, D) {
  const v = {}; for (const n of ["support", "span", "cover", "exposure", "fck", "fy", "dead", "live"]) v[n] = form.elements[n].value;
  useSection({ ...v, b, D });
}

on("explore:from", (inp) => { fillForm(form, inp); show("explore"); run(); });
init();
registerView("explore", { load() {} });

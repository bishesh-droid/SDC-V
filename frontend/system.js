/* Expert system: flow diagram with inspector, pan and zoom, and the knowledge tables. Built from /api/system. */
import { $, $$, esc, api, reduced, announce } from "./core.js";
import { icon, panel, originTag, skeleton, errorState, bindRetry, dataTable, pill, methodBadge } from "./ui.js";
import { N, notation } from "./fmt.js";
import { registerView } from "./chrome.js";

const host = $("#view-system");
const TABS = [["flow", "Flow"], ["facts", "Facts"], ["rules", "Rules"], ["meta", "Meta-rules"], ["cog", "Cognitive system"], ["iface", "Interface"]];
let sys = null, tab = "flow", traceTimer = null, zoom = 1;

host.innerHTML = panel({ title: "Expert system", sub: '<span class="num" id="sys-summary"></span>', crop: true, body: `
  <p class="lede">How the calculator is built as a knowledge-based system: the facts it holds, the rules it applies, the meta-rules that control those rules, how the modules connect, and the interface around them. Everything here is read from the running code.</p>
  <div class="chips" id="sys-tabs" role="tablist" aria-label="Expert system sections"></div>
  <div id="sys-body">${skeleton(5)}</div>` });

async function load() {
  if (!sys) {
    try { sys = await api("/api/system"); } catch (err) { $("#sys-body").innerHTML = errorState({ title: "Could not load the expert system", text: err.message }); bindRetry($("#sys-body"), load); return; }
    const s = sys.summary;
    $("#sys-summary").textContent = `${s.facts} facts · ${s.derivation_rules + s.verifier_rules + s.guardrail_rules} rules · ${s.meta_rules} meta-rules · fingerprint ${s.rules_fingerprint}`;
  }
  drawTabs(); drawBody();
}
function drawTabs() {
  $("#sys-tabs").innerHTML = TABS.map(([id, l]) => `<button type="button" class="chip" role="tab" data-sys="${id}" aria-selected="${tab === id}" tabindex="${tab === id ? 0 : -1}">${esc(l)}</button>`).join("");
  const btns = $$("#sys-tabs [data-sys]");
  btns.forEach((b, i) => {
    b.onclick = () => { tab = b.dataset.sys; clearInterval(traceTimer); drawTabs(); drawBody(); $(`#sys-tabs [data-sys=${tab}]`).focus(); };
    b.onkeydown = (e) => { const to = { ArrowRight: i + 1, ArrowLeft: i - 1, Home: 0, End: btns.length - 1 }[e.key]; if (to !== undefined) { e.preventDefault(); btns[(to + btns.length) % btns.length].focus(); } };
  });
}
const isLLM = (n) => /(^|, )llm\//.test(n.module);
const group = (rows, key) => [...new Set(rows.map((r) => r[key]))];

function drawBody() {
  const body = $("#sys-body");
  if (tab === "flow") return flow(body);
  if (tab === "facts") {
    body.innerHTML = `<p class="lede">Facts are the declarative knowledge the calculator reads. Values come from the live tables and input schema.</p>` + group(sys.facts, "group").map((g, i) => `<h3 class="sec">${esc(g)}</h3><div id="facts-${i}"></div>`).join("");
    group(sys.facts, "group").forEach((g, i) => dataTable($(`#facts-${i}`), { rows: sys.facts.filter((f) => f.group === g).map((f, j) => ({ ...f, id: g + j })), cols: [{ key: "name", label: "Fact" }, { key: "value", label: "Value", cls: "num", render: (r) => N(r.value) }, { key: "clause", label: "Clause", cls: "clause" }] }));
  } else if (tab === "rules") {
    body.innerHTML = `<p class="lede">Rules are condition-action knowledge. Derivation rules produce values, verifier rules judge them, guardrail rules screen what goes in and out.</p>
      <h3 class="sec">Derivation rules <small class="mut">calculator, forward chaining</small> ${originTag("deterministic")}</h3><div id="t-der"></div>
      <h3 class="sec">Verifier rules <small class="mut">${sys.verifier_rules.length} clause-tagged checks</small> ${originTag("deterministic")}</h3>
      <div class="search narrow">${icon("search")}<input id="rules-filter" type="search" placeholder="Filter by name, clause or id" aria-label="Filter verifier rules"></div><div id="vr-table"></div>
      <h3 class="sec">Guardrail rules</h3><div id="t-guard"></div>`;
    dataTable($("#t-der"), { rows: sys.derivation_rules, cols: [{ key: "id", label: "ID", cls: "clause" }, { key: "name", label: "Rule" }, { key: "if", label: "If", render: (r) => N(r.if) }, { key: "then", label: "Then", render: (r) => N(r.then) }, { key: "clause", label: "Clause", cls: "clause" }] });
    dataTable($("#t-guard"), { rows: sys.guardrail_rules, cols: [{ key: "id", label: "ID", cls: "clause" }, { key: "stage", label: "Stage", cls: "clause" }, { key: "name", label: "Rule" }, { key: "if", label: "If", render: (r) => N(r.if) }, { key: "then", label: "Then", render: (r) => N(r.then) }] });
    const vt = dataTable($("#vr-table"), { rows: sys.verifier_rules.map((r) => ({ ...r, id: r.rule_id })), cols: [
      { key: "rule_id", label: "Rule", cls: "clause" }, { key: "category", label: "Category" }, { key: "title", label: "Check" }, { key: "clause", label: "Clause", cls: "clause", render: (r) => N(r.clause) },
      { key: "severity", label: "Severity", render: (r) => pill(r.severity === "error" ? "fail" : "warn", r.severity) },
      { key: "revisable", label: "If it fails", render: (r) => `<span class="pill-s neutral">${r.revisable ? "Enlarge section" : "Needs engineer"}</span>`, sortVal: (r) => (r.revisable ? 1 : 0) }] });
    $("#rules-filter").addEventListener("input", (e) => { const q = e.target.value.trim().toLowerCase(); vt.setRows(sys.verifier_rules.filter((r) => !q || `${r.rule_id} ${r.title} ${r.clause} ${r.category}`.toLowerCase().includes(q)).map((r) => ({ ...r, id: r.rule_id }))); });
  } else if (tab === "meta") {
    body.innerHTML = `<p class="lede">Meta-rules are rules about rules: they decide which rules may run, in what order, and what happens when they fail.</p><div id="t-meta"></div>`;
    dataTable($("#t-meta"), { rows: sys.meta_rules, cols: [{ key: "id", label: "ID", cls: "clause" }, { key: "name", label: "Meta-rule" }, { key: "statement", label: "Statement", render: (r) => N(r.statement) }, { key: "enforced_in", label: "Enforced in", cls: "clause" }, { key: "parameter", label: "Parameter", cls: "clause" }] });
  } else if (tab === "cog") {
    body.innerHTML = `<p class="lede">The system mapped to the functions of a cognitive architecture.</p><div id="t-cog"></div>`;
    dataTable($("#t-cog"), { rows: sys.cognitive.map((c, i) => ({ ...c, id: i })), cols: [{ key: "function", label: "Function" }, { key: "implemented_by", label: "Implemented by" }, { key: "purpose", label: "Purpose" }] });
  } else {
    body.innerHTML = `<p class="lede">The browser UI talks to these endpoints through one origin. Add an Authorization bearer token when the server requires one.</p><div id="t-if"></div>
      <h3 class="sec">Views</h3><p class="views">${["Home", "Assistant", "Form design", "Explore sections", "Knowledge base", "Expert system", "History", "Scope & status"].map((v) => `<span class="chip-s">${esc(v)}</span>`).join(" ")}</p>`;
    dataTable($("#t-if"), { rows: sys.interface.map((r, i) => ({ ...r, id: i })), cols: [{ key: "method", label: "Method", render: (r) => methodBadge(r.method) }, { key: "path", label: "Path", cls: "clause" }, { key: "purpose", label: "Purpose" }] });
  }
}

/* ------------------------------------------------------------------ swim-lane flow diagram */
function flow(body) {
  const LW = 128, CW = 140, RH = 96, BW = 122, BH = 50, PAD = 14;
  const layers = sys.layers, lane = Object.fromEntries(layers.map((l, i) => [l.id, i]));
  const maxCol = Math.max(...sys.nodes.map((n) => n.col));
  const W = LW + (maxCol + 1) * CW + 70, H = layers.length * RH + 20;
  const pos = Object.fromEntries(sys.nodes.map((n) => [n.id, { x: LW + n.col * CW + CW / 2, y: lane[n.layer] * RH + RH / 2 + 10, n }]));
  const wrap = (t) => { if (t.length < 17) return [t]; const w = t.split(" "); let a = "", i = 0; while (i < w.length && (a + " " + w[i]).trim().length <= 16) a = (a + " " + w[i++]).trim(); return [a, w.slice(i).join(" ")].filter(Boolean); };
  let svg = `<svg viewBox="0 0 ${W} ${H}" class="flow" role="group" aria-label="Module flow of the SDC-V expert system"><defs><marker id="ah" viewBox="0 0 10 10" refX="8.5" refY="5" markerWidth="9" markerHeight="9" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" fill="currentColor"/></marker></defs>`;
  layers.forEach((l, i) => { svg += `<rect x="0" y="${i * RH + 10}" width="${W}" height="${RH}" class="lane${i % 2 ? " alt" : ""}"/><text x="${PAD}" y="${i * RH + RH / 2 + 14}" class="lane-t">${esc(l.label)}</text>`; });
  let back = 0, k = 0;
  sys.edges.forEach((e) => {
    const a = pos[e.source], b = pos[e.target], la = lane[a.n.layer], lb = lane[b.n.layer];
    let d;
    if (la === lb) {
      if (b.n.col === a.n.col + 1) d = `M${a.x + BW / 2} ${a.y}H${b.x - BW / 2}`;
      else { const top = a.y - BH / 2; d = `M${a.x} ${top}V${top - 18}H${b.x}V${b.y - BH / 2}`; }
    } else if (lb < la && la - lb >= 2) {
      back += 1; const xr = W - 34 + back * 9; d = `M${a.x + BW / 2} ${a.y}H${xr}V${b.y}H${b.x + BW / 2}`;
    } else {
      const down = lb > la, y1 = a.y + (down ? BH / 2 : -BH / 2), y2 = b.y + (down ? -BH / 2 : BH / 2), ym = (y1 + y2) / 2 + ((k % 3) - 1) * 9;
      d = a.x === b.x ? `M${a.x} ${y1}V${y2}` : `M${a.x} ${y1}V${ym}H${b.x}V${y2}`;
    }
    k++;
    svg += `<path d="${d}" class="edge${e.dashed ? " dash" : ""}" data-edge="${e.source}>${e.target}" marker-end="url(#ah)"><title>${esc(e.source)} to ${esc(e.target)}${e.label ? ": " + esc(e.label) : ""}</title></path>`;
  });
  sys.nodes.forEach((n) => {
    const p = pos[n.id], lines = wrap(n.label), o = isLLM(n) ? "llm" : "det";
    svg += `<g class="node ${o}" tabindex="0" data-node="${n.id}" role="button" aria-label="${esc(n.label)}, ${o === "llm" ? "language model" : "deterministic"} module"><rect x="${p.x - BW / 2}" y="${p.y - BH / 2}" width="${BW}" height="${BH}" rx="5"/>${lines.map((t, i) => `<text x="${p.x}" y="${p.y + (i - (lines.length - 1) / 2) * 13 + 4}" text-anchor="middle">${esc(t)}</text>`).join("")}</g>`;
  });
  svg += "</svg>";
  body.innerHTML = `<div class="flow-tools"><button class="btn ghost sm" id="trace-btn" type="button">${icon("play")} Trace a run</button>
      <span class="legend inline"><span>${originTag("deterministic")}</span><span>${originTag("llm")}</span><span class="hint">Solid arrows are the main flow, dashed arrows are optional or return paths.</span></span>
      <span class="zoom" role="group" aria-label="Zoom"><button class="btn ghost sm" id="z-out" type="button" aria-label="Zoom out">−</button><button class="btn ghost sm num" id="z-reset" type="button" aria-label="Reset zoom">100%</button><button class="btn ghost sm" id="z-in" type="button" aria-label="Zoom in">+</button></span></div>
    <div class="flow-grid"><div class="flowwrap" id="flowwrap" tabindex="0" aria-label="Flow diagram, scrollable. Drag to pan.">${svg}</div>
    <aside class="inspector" id="node-info" aria-live="polite"><p class="hint">Hover, focus or select a module to inspect it here.</p></aside></div>`;
  const wrapEl = $("#flowwrap"), svgEl = $("svg.flow", wrapEl);
  const setZoom = (z) => { zoom = Math.max(0.6, Math.min(2.4, z)); svgEl.style.width = (zoom * 100) + "%"; $("#z-reset").textContent = Math.round(zoom * 100) + "%"; };
  setZoom(zoom);
  $("#z-in").onclick = () => setZoom(zoom + 0.2); $("#z-out").onclick = () => setZoom(zoom - 0.2); $("#z-reset").onclick = () => setZoom(1);
  wrapEl.addEventListener("wheel", (e) => { if (e.ctrlKey || e.metaKey) { e.preventDefault(); setZoom(zoom + (e.deltaY < 0 ? 0.1 : -0.1)); } }, { passive: false });
  let drag = null;
  wrapEl.addEventListener("pointerdown", (e) => { if (e.target.closest(".node")) return; drag = { x: e.clientX, y: e.clientY, sl: wrapEl.scrollLeft, st: wrapEl.scrollTop }; wrapEl.setPointerCapture(e.pointerId); wrapEl.classList.add("drag"); });
  wrapEl.addEventListener("pointermove", (e) => { if (drag) { wrapEl.scrollLeft = drag.sl - (e.clientX - drag.x); wrapEl.scrollTop = drag.st - (e.clientY - drag.y); } });
  wrapEl.addEventListener("pointerup", () => { drag = null; wrapEl.classList.remove("drag"); });

  const facts = (id) => { const n = sys.nodes.find((x) => x.id === id); return { n, into: sys.edges.filter((e) => e.target === id).map((e) => sys.nodes.find((x) => x.id === e.source).label), out: sys.edges.filter((e) => e.source === id).map((e) => sys.nodes.find((x) => x.id === e.target).label) }; };
  let pinned = null;
  const info = (id) => {
    const { n, into, out } = facts(id);
    $("#node-info").innerHTML = `<h3>${esc(n.label)}</h3><p class="row-tags">${originTag(isLLM(n) ? "llm" : "deterministic")} <span class="chip-s">${esc(sys.layers.find((l) => l.id === n.layer).label)}</span></p><p>${esc(n.role)}</p>
      <dl class="kv wide"><dt>Module</dt><dd>${esc(n.module)}</dd><dt>Libraries</dt><dd>${esc(n.libraries.join(", ") || "none")}</dd><dt>Receives from</dt><dd>${esc(into.join(", ") || "—")}</dd><dt>Sends to</dt><dd>${esc(out.join(", ") || "—")}</dd></dl>`;
  };
  $$(".node", body).forEach((g) => {
    g.onmouseenter = () => info(g.dataset.node); g.onfocus = () => info(g.dataset.node);
    g.onmouseleave = () => { if (pinned) info(pinned); }; g.onblur = () => { if (pinned) info(pinned); };
    g.onclick = () => { pinned = g.dataset.node; $$(".node.sel", body).forEach((x) => x.classList.remove("sel")); g.classList.add("sel"); info(pinned); };
    g.onkeydown = (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); g.onclick(); } };
  });
  $("#trace-btn").onclick = () => {
    clearInterval(traceTimer);
    const clear = () => $$(".hot", body).forEach((x) => x.classList.remove("hot"));
    clear(); const path = sys.main_path; let i = 0;
    const stepFn = () => {
      clear(); const id = path[i]; $(`[data-node="${id}"]`, body)?.classList.add("hot");
      if (i > 0) $(`[data-edge="${path[i - 1]}>${id}"]`, body)?.classList.add("hot");
      info(id); announce(`Trace: ${sys.nodes.find((n) => n.id === id).label}`);
      if (++i >= path.length) { clearInterval(traceTimer); setTimeout(clear, 1200); }
    };
    stepFn(); if (reduced()) { while (i < path.length) stepFn(); } else traceTimer = setInterval(stepFn, 800);
  };
}
registerView("system", { load, leave: () => clearInterval(traceTimer) });

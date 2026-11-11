/* Home: hero with a live-drawn example section, the example pipeline (precomputed fixture, no endpoint that writes), capabilities, database tiles. */
import { $, $$, esc, api, on, reduced, announce } from "./core.js";
import { icon, panel, originTag, statTile, runCountUps, skeleton, errorState, bindRetry } from "./ui.js";
import { N, fix, notation } from "./fmt.js";
import { registerView } from "./chrome.js";
import { crossSection } from "./beam.js";
import { EXAMPLE as X } from "./fixture.js";

const host = $("#view-home");
let step = 0, playing = !reduced(), timer = null, steps = [];

function buildSteps() {
  const f = X.first.design, g = X.final.design, failed = X.first.checks.filter((c) => !c.passed && c.severity === "error").map((c) => c.rule_id);
  const bars = (d) => `${d.bars.n}-${d.bars.dia} mm bars in a ${d.bars.n_layer2 ? "double" : "single"} layer`;
  const n = X.iterations.length - 1, fin = X.final.input;
  return [
    { n: "Brief", o: "llm", t: X.brief, tag: "input" },
    { n: "Guardrails", o: "deterministic", t: "In scope, no unsafe request, units normalised, every value found in the brief." },
    { n: "Calculator", o: "deterministic", t: `${X.first.input.b_mm} x ${X.first.input.D_mm} mm: Mu ${fix(f.Mu, 1)} kN·m, Ast required ${fix(f.ast_req, 0)} mm², ${bars(f)}.` },
    { n: "Verifier", o: "deterministic", t: `Fails ${failed.join(", ")}. This section is not acceptable.`, hot: failed.join(", "), tone: "fail" },
    { n: "Reviser", o: "deterministic", t: `Depth +25 mm per step, ${n} steps, to ${fin.b_mm} x ${fin.D_mm} mm. Every rule is run again.`, tone: "warn" },
    { n: "Verified result", o: "deterministic", t: `${bars(g)}, stirrups at ${g.sv_prov} mm c/c, span/d ${fix(g.ld_actual, 2)} against ${fix(g.ld_allow, 2)} allowed.`, hot: `span/d ${fix(g.ld_actual, 2)} against ${fix(g.ld_allow, 2)} allowed.`, tone: "pass" },
    { n: "Narrative", o: "llm", t: "The model writes the explanation from the formatted result only. A number that is not in the result is rejected; after 3 tries a template is used." },
    { n: "Audit", o: "deterministic", t: "The report is stamped DRAFT and the run is stored with the code edition and rules fingerprint." },
  ];
}

const CAPS = [
  ["design", "Design", "singly reinforced rectangular beams (simply supported or cantilever, UDL): flexure, shear, deflection, bar and stirrup detailing."],
  ["brief", "Understand", "a written brief or a photo of a problem, and ask for missing values instead of guessing."],
  ["rules", "Verify", "with 19 clause-tagged rules, then enlarge the section automatically if a check fails."],
  ["explorer", "Explore", "nearby sections and find the lightest one that passes."],
  ["report", "Explain", "in a narrative where every number is traced back to the verified result."],
  ["audit", "Record", "every run in an audit log, with CSV and Markdown export."],
  ["kb", "Look up", "structural engineering reference material in the knowledge base."],
  ["system", "Inspect", "the facts, rules and meta-rules behind the calculator in the expert system view."],
];

function demoHTML() {
  return `<ol class="demo" id="demo">${steps.map((s, i) => `<li data-i="${i}"${s.tone ? ` data-tone="${s.tone}"` : ""}><span class="n">${i + 1}</span><span class="pkt ${s.o === "llm" ? "llm" : "det"}" aria-hidden="true"></span><div><b>${esc(s.n)} ${originTag(s.o)}</b><span class="d">${s.hot ? esc(notation(s.t)).replace(esc(notation(s.hot)), (m) => `<em class="t">${m}</em>`) : N(s.t)}</span></div></li>`).join("")}</ol>`;
}
function paint() {
  $$("#demo li").forEach((li, i) => { li.className = !playing && reduced() ? "done" : i < step ? "done" : i === step ? "on" : ""; if (li.dataset.tone) li.dataset.tone = li.dataset.tone; });
  const r = $("#demo-range"); if (r) { r.value = step + 1; r.setAttribute("aria-valuetext", `Step ${step + 1} of ${steps.length}: ${steps[step].n}`); }
  const c = $("#demo-count"); if (c) c.textContent = `${step + 1} / ${steps.length}`;
  const p = $("#demo-toggle"); if (p) { p.innerHTML = `${icon(playing ? "pause" : "play")} ${playing ? "Pause" : "Play"}`; p.setAttribute("aria-pressed", String(!playing)); }
}
function tick() { if (!playing) return; step = step + 1 >= steps.length ? 0 : step + 1; paint(); }
function start() { stop(); if (reduced()) { playing = false; paint(); return; } timer = setInterval(tick, 2400); }
function stop() { clearInterval(timer); timer = null; }
const goto = (i) => { step = Math.max(0, Math.min(steps.length - 1, i)); paint(); };

function render() {
  steps = buildSteps();
  const fin = X.final, d = fin.design;
  host.innerHTML = `
    <section class="hero grid-bg"><div class="hero-t">
      <h2>Draft reinforced-concrete beam designs to IS 456:2000, with every number checked.</h2>
      <p>Describe a beam in plain English or fill in a form. A deterministic calculator produces the numbers, clause-tagged rules decide pass or fail, and the language model only reads your brief and explains the result.</p>
      <div class="row"><button class="btn primary" type="button" data-go="chat">Open the assistant</button><button class="btn ghost" type="button" data-go="design">Use the form</button></div>
      <p class="origin-key"><span>${originTag("deterministic")} calculator, rules, audit</span><span>${originTag("llm")} reads the brief, explains the result</span></p></div>
      <div class="hero-d crop"><div class="ex-tag">Example</div>${crossSection(d, fin.input, { caption: false })}<p class="hint">${fin.input.b_mm} × ${fin.input.D_mm} mm after the example run below</p></div>
    </section>
    ${panel({ title: "Example run", sub: `<span class="pill-s accent">${icon("info")}<span>Example: precomputed, nothing is run or logged</span></span>`, actions: `<button class="btn ghost sm" id="demo-toggle" type="button" aria-pressed="false"></button>`, cls: "demo-p", body: `
      <p class="hint" id="demo-caption">A 250 × 400 mm beam is too shallow. Watch the pipeline find a section that passes.</p>
      <div class="scrub"><button class="btn ghost sm" id="demo-prev" type="button" aria-label="Previous step">${icon("chevL")}</button><input id="demo-range" type="range" min="1" max="${steps.length}" step="1" value="1" aria-label="Pipeline step"><button class="btn ghost sm" id="demo-next" type="button" aria-label="Next step">${icon("chevR")}</button><span class="num hint" id="demo-count"></span></div>
      ${demoHTML()}` })}
    ${panel({ title: "What it can do", body: `<div class="caps">${CAPS.map(([ic, v, t]) => `<div class="cap-i">${icon(ic)}<p><b>${esc(v)}</b> ${esc(t)}</p></div>`).join("")}</div>` })}
    ${panel({ title: "Viewable database", body: `<div class="tiles" id="db-cards">${skeleton(2)}</div>` })}`;
  $("#demo-toggle").onclick = () => { playing = !playing; paint(); announce(playing ? "Example playing" : "Example paused"); };
  $("#demo-range").oninput = (e) => { playing = false; goto(+e.target.value - 1); };
  $("#demo-prev").onclick = () => { playing = false; goto(step - 1); };
  $("#demo-next").onclick = () => { playing = false; goto(step + 1); };
  paint();
}

async function tiles() {
  const box = $("#db-cards"); if (!box) return;
  try {
    const [kb, sys, st] = await Promise.all([api("/api/kb"), api("/api/system"), api("/api/stats")]), s = sys.summary;
    box.innerHTML = statTile({ value: kb.count, label: "Knowledge base entries", sub: `${kb.topics.length} topics, searchable`, go: "kb" })
      + statTile({ value: s.facts, label: "Facts", sub: "code constants, tables and limits", go: "system" })
      + statTile({ value: s.derivation_rules + s.verifier_rules + s.guardrail_rules, label: "Rules", sub: `${s.derivation_rules} derivation, ${s.verifier_rules} verifier, ${s.guardrail_rules} guardrail`, go: "system" })
      + statTile({ value: s.meta_rules, label: "Meta-rules", sub: "rules that control the rules", go: "system" })
      + statTile({ value: s.endpoints, label: "API endpoints", sub: "the interface around the system", go: "system" })
      + statTile({ value: st.total, label: "Audit log runs", sub: "every design, with verdicts", go: "history" });
    runCountUps(box);
  } catch (err) { box.innerHTML = errorState({ title: "Could not load the database summary", text: err.message }); bindRetry(box, tiles); }
}

on("cmd:demo", () => { playing = true; step = 0; paint(); start(); announce("Example playing"); });
render();
registerView("home", { load() { tiles(); start(); }, leave: stop });

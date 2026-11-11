/* Form design: structured input (no intake model), live preview from inputs, full result. */
import { $, $$, esc, api, busy, modelQS, on, state, announce, noteRun, emit } from "./core.js";
import { icon, panel, originTag, skeleton, errorState, bindRetry } from "./ui.js";
import { show, registerView } from "./chrome.js";
import { resultView, bindResult, loadCategories } from "./result.js";
import { previewSection, previewElevation } from "./beam.js";

/* [name, label, unit suffix, type, options, helper] */
export const FIELDS = [
  ["support", "Support", "", "select", [["simply_supported", "Simply supported"], ["cantilever", "Cantilever"]], ""],
  ["span", "Effective span", "m", "number", { step: 0.01, min: 0, value: 6 }, ""],
  ["b", "Width b", "mm", "number", { step: 5, value: 300 }, ""],
  ["D", "Overall depth D", "mm", "number", { step: 5, value: 550 }, ""],
  ["cover", "Nominal cover", "mm", "number", { step: 5, value: 30 }, ""],
  ["exposure", "Exposure", "", "select", ["mild", "moderate", "severe", "very severe", "extreme"].map((x) => [x, x[0].toUpperCase() + x.slice(1)]), ""],
  ["fck", "Concrete", "", "select", [20, 25, 30, 35, 40].map((x) => [x, "M" + x]), ""],
  ["fy", "Steel", "", "select", [250, 415, 500].map((x) => [x, "Fe" + x]), ""],
  ["dead", "Dead load", "kN/m", "number", { step: 0.1, min: 0, value: 15 }, "excl. self-weight"],
  ["live", "Live load", "kN/m", "number", { step: 0.1, min: 0, value: 12 }, ""],
];
const DEFAULT_SELECT = { exposure: "moderate", fck: "25", fy: "500" };
export function fieldsHTML(prefix) {
  return FIELDS.map(([name, label, unit, type, opt, help]) => {
    const id = `${prefix}-${name}`;
    const lbl = `<span class="lbl"><span>${esc(label)}</span>${unit ? `<span class="u">${esc(unit)}</span>` : ""}</span>`;
    const ctl = type === "select"
      ? `<select id="${id}" name="${name}">${opt.map(([v, t]) => `<option value="${esc(v)}"${String(v) === DEFAULT_SELECT[name] ? " selected" : ""}>${esc(t)}</option>`).join("")}</select>`
      : `<input id="${id}" name="${name}" type="number" inputmode="decimal" required ${Object.entries(opt).map(([k, v]) => `${k}="${v}"`).join(" ")}>`;
    return `<div class="fld"><label for="${id}">${lbl}</label>${ctl}<small class="hlp">${esc(help)}</small></div>`;
  }).join("");
}
export function readForm(form) {
  const f = Object.fromEntries(new FormData(form)), q = (v, unit) => ({ value: +v, unit });
  return { support: f.support, span: q(f.span, "m"), b: q(f.b, "mm"), D: q(f.D, "mm"), cover: q(f.cover, "mm"), fck: +f.fck, fy: +f.fy,
    dead_load: q(f.dead, "kN/m"), live_load: q(f.live, "kN/m"), exposure: f.exposure };
}
export function fillForm(form, i) {
  const set = (n, v) => { const el = form.elements[n]; if (el && v !== undefined && v !== null) el.value = v; };
  set("support", i.support); set("span", i.span_m); set("b", i.b_mm); set("D", i.D_mm); set("cover", i.cover_mm);
  set("exposure", String(i.exposure).replace("_", " ")); set("fck", i.fck); set("fy", i.fy); set("dead", i.dead_load_kN_per_m); set("live", i.live_load_kN_per_m);
}

const host = $("#view-design");
let form, out, current = null, t;

const strip = () => `<ol class="stages" aria-label="Pipeline for this form">
  <li class="skip">${originTag("llm")}<b>Intake</b><span>LLM skipped for this form</span></li>
  <li>${originTag("deterministic")}<b>Guardrails</b><span>scope, units, limits</span></li>
  <li>${originTag("deterministic")}<b>Calculator</b><span>IS 456 flexure, shear, deflection</span></li>
  <li>${originTag("deterministic")}<b>Verifier + reviser</b><span>19 rules, resize if needed</span></li>
  <li>${originTag("llm")}<b>Narrative</b><span>Gemini if a key is set, template otherwise</span></li>
  <li>${originTag("deterministic")}<b>Audit log</b><span>run stored, stamped DRAFT</span></li></ol>`;

function preview() {
  const f = form.elements, b = +f.b.value, D = +f.D.value, c = +f.cover.value, span = +f.span.value;
  $("#live-prev").innerHTML = `<div class="prev-grid">${previewSection(b, D, c)}${previewElevation(span, f.support.value)}</div>`;
}

function init() {
  host.innerHTML = `<div class="split">
    ${panel({ title: "Form design", sub: originTag("deterministic"), crop: true, body: `<form id="pane-form" autocomplete="off"><div class="fgrid">${fieldsHTML("fd")}</div>
      <p class="hint">Loads are characteristic values. Self-weight and the 1.5 load factor are added by the calculator, never by the user or the AI. The intake model is not used for this form.</p>
      <button type="submit" class="btn primary" id="btn-form">Run deterministic design</button></form>` })}
    <div class="out" id="design-out" aria-live="polite">
      ${panel({ title: "No design yet", cls: "grid-bg", body: `<p class="lede">Every number in the report comes from a deterministic IS 456 calculator and clause-tagged rules. The language model only reads your brief and explains the result.</p>${strip()}<div id="live-prev"></div>` })}
    </div></div>`;
  form = $("#pane-form"); out = $("#design-out");
  form.addEventListener("input", () => { clearTimeout(t); t = setTimeout(() => { if ($("#live-prev")) preview(); }, 120); });
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const btn = $("#btn-form"); busy(btn, true, "Run deterministic design");
    out.innerHTML = panel({ title: "Running", body: skeleton(5) });
    announce("Running the design");
    try { render(await api("/api/design" + modelQS(), { method: "POST", body: readForm(form) })); }
    catch (err) { out.innerHTML = errorState({ title: "The design run failed", text: err.message }); bindRetry(out, () => form.requestSubmit()); announce("Design run failed"); }
    busy(btn, false, "Run deterministic design");
  });
  preview();
}
export async function render(res) {
  current = res; state.current = res; noteRun(res);
  await loadCategories();
  out.innerHTML = resultView(res);
  bindResult(out, res);
  announce(`Design result: ${res.status.replace("_", " ")}`);
  $("#main").scrollTop = 0;
}
/* open a stored run (History) */
export async function openRecord(rec) {
  show("design");
  await render(rec.record.result);
  if (rec.reviewer) out.insertAdjacentHTML("beforeend", `<p class="hint">Review logged by ${esc(rec.reviewer)} at ${esc(rec.reviewed_at)}${rec.review_note ? " · " + esc(rec.review_note) : ""}</p>`);
}
export function useSection(src) { // from Explore: copy all fields then set the section
  for (const n of ["support", "span", "cover", "exposure", "fck", "fy", "dead", "live", "b", "D"]) if (src[n] !== undefined) form.elements[n].value = src[n];
  show("design"); if ($("#live-prev")) preview(); form.scrollIntoView({ block: "center" });
}
export const designForm = () => form;
init();
registerView("design", { load() { if (!current) preview(); } });

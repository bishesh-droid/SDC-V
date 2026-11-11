/* Scope and status: spec sheet, health panel with LEDs, model fallback chain and the live model check. */
import { $, $$, esc, api, busy, modelQS, state, markUnavailable, on, announce } from "./core.js";
import { icon, panel, led, pill, originTag, skeleton, errorState, bindRetry } from "./ui.js";
import { N, fix } from "./fmt.js";
import { registerView, copyFingerprint, loadHealth } from "./chrome.js";

const host = $("#view-scope");
host.innerHTML = `<div class="split2">${panel({ title: "Scope", sub: originTag("deterministic"), crop: true, body: '<div id="scope-body">' + skeleton(6) + "</div>" })}
  ${panel({ title: "System status", crop: true, actions: '<button class="btn ghost sm" id="btn-deep" type="button">Run live model check</button>', body: '<div id="status-body">' + skeleton(6) + "</div>" })}</div>`;

const bound = (b) => `${b.ge !== undefined ? b.ge : "above " + b.gt} to ${b.le}`;
let deep = null;

async function loadScope() {
  const box = $("#scope-body");
  try {
    const s = await api("/api/scope"), L = s.limits;
    const spec = (rows) => `<dl class="spec">${rows.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${N(v)}</dd>`).join("")}</dl>`;
    const tags = (a) => `<ul class="tags">${a.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>`;
    box.innerHTML = `<h3 class="sec">Supported (${esc(s.code)})</h3><ul class="plain">${s.supported.map((x) => `<li>${N(x)}</li>`).join("")}</ul>
      <h3 class="sec">Input limits</h3>${spec([["Span", `${bound(L.span_m)} m (cantilever up to ${L.cantilever_max_m} m)`], ["Width b", `${bound(L.b_mm)} mm`], ["Depth D", `${bound(L.D_mm)} mm (D/b up to ${L.max_D_over_b})`], ["Cover", `${bound(L.cover_mm)} mm`], ["Dead / live load", `${bound(L.dead_load_kN_per_m)} kN/m each`], ["Concrete", L.fck.map((x) => "M" + x).join(", ")], ["Steel", L.fy.map((x) => "Fe" + x).join(", ")], ["Exposure", L.exposure.map((x) => x.replace("_", " ")).join(", ")]])}
      <h3 class="sec">Detected and declined</h3>${tags(s.out_of_scope)}
      <h3 class="sec">Refused outright</h3>${tags(s.refused)}
      <h3 class="sec">Fixed assumptions</h3><ul class="plain">${s.fixed_assumptions.map((x) => `<li>${N(x)}</li>`).join("")}</ul>
      <h3 class="sec">Reviser</h3><p>Up to ${s.reviser.max_iterations} revisions in ${s.reviser.step_mm} mm steps: ${esc(s.reviser.order)}.</p>
      <p class="hint">${esc(s.rule_count)} verifier rules. ${N(s.limits_note)}</p>`;
  } catch (err) { box.innerHTML = errorState({ title: "Could not load the scope", text: err.message }); bindRetry(box, loadScope); }
  renderStatus();
}

function renderStatus() {
  const h = state.health, box = $("#status-body");
  if (!h) { box.innerHTML = errorState({ title: "Backend not reachable", text: "Start the server, then retry." }); bindRetry(box, async () => { await loadHealth(); renderStatus(); }); return; }
  const v = h.versions, sel = $("#model-select")?.value || h.default_model;
  const row = (l, ledS, val, extra = "") => `<div class="hrow">${ledS ? led(ledS) : '<span class="led off"></span>'}<span class="hl">${esc(l)}</span><span class="hv num">${val}</span>${extra}</div>`;
  const chain = `<ol class="chain fb">${h.model_options.map((m, i) => `<li class="${m.id === sel ? "sel" : ""}${state.unavailable.has(m.id) ? " bad" : ""}"><span class="ch-i">${i + 1}</span><code>${esc(m.id)}</code>${m.id === sel ? pill("accent", "selected") : ""}${state.unavailable.has(m.id) ? pill("fail", "unavailable") : ""}</li>`).join("")}</ol>`;
  let live = "";
  if (deep) {
    const p = deep.probe, sk = p.skipped || {};
    live = `<h3 class="sec">Live model check ${deep.cached ? "<small class='mut'>(cached, under 60 s old)</small>" : ""}</h3>
      <div class="vd ${p.ok ? "pass" : "fail"}"><div class="vd-main">${icon(p.ok ? "pass" : "fail", "vd-ic")}<div><div class="vd-word">${p.ok ? "OK" : "FAILED"}</div><div class="vd-msg">${p.ok ? `Answered from <code>${esc(p.model)}</code> in <span class="num">${p.latency_ms} ms</span>` : esc(p.error)}</div></div></div></div>
      ${Object.keys(sk).length ? `<ul class="chain">${Object.entries(sk).map(([m, e]) => `<li class="bad"><code>${esc(m)}</code>${pill("fail", String(e).slice(0, 90))}</li>`).join("")}</ul>` : ""}
      ${deep.unavailable_models?.length ? `<p class="warnline">Configured but not offered by the API any more: ${esc(deep.unavailable_models.join(", "))}. They are marked unavailable in the model selector.</p>` : deep.unavailable_models ? '<p class="hint">All configured models are listed by the API.</p>' : '<p class="hint">Model list lookup failed.</p>'}`;
  }
  box.innerHTML = `<div class="health">${row("Backend", "pass", `online, v${esc(v.app)}`)}${row("Gemini key", h.llm_configured ? "pass" : "warn", h.llm_configured ? "configured" : "missing")}
    ${row("Selected model", state.unavailable.has(sel) ? "fail" : "", esc(sel))}${row("Database", "db_ok" in h ? (h.db_ok ? "pass" : "fail") : "", "db_ok" in h ? (h.db_ok ? "ok" : "error") : "—")}
    ${row("Code edition", "", esc(h.code_edition))}
    <div class="hrow">${'<span class="led off"></span>'}<span class="hl">Rules fingerprint</span><span class="hv num">${esc(v.rules_fingerprint)}</span><button type="button" class="btn ghost sm" id="fp-copy">${icon("copy")} Copy</button></div>
    ${row("Python / pydantic", "", `${esc(v.python)} / ${esc(v.pydantic)}`)}${row("Rate limit", "", h.rate_limit_per_min ? `${h.rate_limit_per_min} requests/min per client` : "off")}
    ${row("API token", h.auth_required ? "pass" : "warn", h.auth_required ? "required" : "not required")}</div>
    ${h.auth_required ? "" : '<p class="hint note">The API token is not required. Enable SDCV_API_TOKEN before any public deployment.</p>'}
    <h3 class="sec">Model fallback order</h3>${chain}<p class="hint">If the selected model fails, the others are tried in the listed order; if none answers, the deterministic template is used.</p>${live}`;
  $("#fp-copy").onclick = copyFingerprint;
}

$("#btn-deep").onclick = async (e) => {
  busy(e.target, true, "Run live model check");
  $("#status-body").insertAdjacentHTML("beforeend", `<div id="deep-wait" class="state">${skeleton(2)}<p class="hint">Calling the model…</p></div>`);
  try {
    const h = await api("/api/health?deep=true" + modelQS("&"));
    state.health = h; deep = h.llm;
    // models the check could not use become "unavailable" in the selector
    const bad = new Set([...(deep.unavailable_models || []), ...Object.keys(deep.probe.skipped || {})]);
    if (deep.probe.ok) bad.delete(deep.probe.model);
    markUnavailable([...bad]); announce(deep.probe.ok ? "Live check passed" : "Live check failed");
  } catch (err) { $("#deep-wait")?.remove(); $("#status-body").insertAdjacentHTML("beforeend", `<p class="warnline">${esc(err.message)}</p>`); }
  renderStatus(); busy(e.target, false, "Run live model check");
};
on("model", renderStatus); on("models", renderStatus);
registerView("scope", { load: loadScope });

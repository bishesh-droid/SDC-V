/* Presentation-layer formatting. One place for engineering notation; stored data is never edited. */
import { esc } from "./core.js";

/* N/mm2 -> N/mm², kN/m3 -> kN/m³, mm2 -> mm², 250 x 400 -> 250 × 400, -> to →, "-50" -> "−50", kN.m -> kN·m */
export function notation(text) {
  return String(text ?? "")
    .replace(/\b(N\/mm|kN\/m|mm|cm|m)([23])(?![\d.])/g, (_, u, p) => u + (p === "2" ? "²" : "³"))
    .replace(/(\d)\s*[xX]\s*(?=\d)/g, "$1 × ")
    .replace(/\s*->\s*/g, " → ")
    .replace(/(^|[\s(=:,;])-(?=\d)/g, "$1−")
    .replace(/\bkN\.m\b/g, "kN·m")
    .replace(/\btau_c,max\b/g, "τc,max").replace(/\btau_([cv])\b/g, "τ$1");
}
export const N = (s) => esc(notation(s));          // notation + HTML escape, for use in templates
export const fix = (v, d = 1) => (v === null || v === undefined || Number.isNaN(+v)) ? "—" : (+v).toFixed(d).replace(/^-/, "−");
export const withUnit = (v, unit, d = 1) => `${fix(v, d)}${unit ? " " + notation(unit) : ""}`;

/* verdict labels (kept from the previous UI) and their tone/icon */
export const LABELS = { designed: "Draft ready", needs_engineer: "Needs engineer", needs_info: "More info needed", rejected: "Input rejected",
  out_of_scope: "Out of scope", refused: "Declined", error: "Unavailable" };
export const TONE = { designed: "pass", needs_engineer: "warn", needs_info: "warn", rejected: "fail", out_of_scope: "warn", refused: "warn", error: "fail" };

export function utc(iso) { return String(iso || "").replace("T", " ").replace("+00:00", ""); }

/* Parse the raw model error stored in old History rows into something readable. The raw text stays available. */
export function friendlyError(raw) {
  raw = String(raw || "");
  const m = /\(([\s\S]*)\)\.?\s*$/.exec(raw);
  const body = m ? m[1] : raw;
  const items = [];
  const re = /(?:^|;\s*)([a-z][a-z0-9.\-]*[a-z0-9]):\s*([\s\S]*?)(?=;\s*[a-z][a-z0-9.\-]*[a-z0-9]:\s|$)/g;
  let x;
  while ((x = re.exec(body))) {
    const d = x[2].trim();
    let outcome = "failed", note = d.replace(/\s+/g, " ").slice(0, 140);
    if (/timed out/i.test(d)) { outcome = "timeout"; note = d.match(/timed out after \d+s/i)?.[0] || "timed out"; }
    else if (/HTTP 404|no longer available|not found/i.test(d)) { outcome = "unavailable"; note = "no longer available (HTTP 404)"; }
    else if (/HTTP 429|quota/i.test(d)) { outcome = "quota"; note = "quota exceeded (HTTP 429)"; }
    else if (/HTTP 5\d\d|high demand|overloaded/i.test(d)) { outcome = "busy"; note = "model busy (HTTP " + (d.match(/HTTP (5\d\d)/)?.[1] || "5xx") + ")"; }
    else if (/empty response|unusable/i.test(d)) { outcome = "unusable"; note = "returned nothing usable"; }
    else if (/network/i.test(d)) { outcome = "network"; note = "network error"; }
    items.push({ model: x[1], outcome, note });
  }
  if (!/language model could not be reached|returned unusable output/i.test(raw) || !items.length) {
    return { summary: raw.length > 160 ? raw.slice(0, 157) + "…" : raw, items: [], raw, friendly: false };
  }
  const first = items[0];
  const verb = { unavailable: "is no longer available", timeout: "timed out", quota: "has no quota left", busy: "was busy", unusable: "returned unusable output", network: "could not be reached", failed: "failed" };
  const summary = `Model unavailable: ${first.model} ${verb[first.outcome]}.` + (items.length > 1 ? ` ${items.length - 1} other model${items.length > 2 ? "s" : ""} also failed.` : "") + " No result was produced; the run was logged as an error.";
  return { summary, items, raw, friendly: true };
}

/* animate a stat from 0 to its final value; instant when the user prefers reduced motion */
export function countUp(el, reduced) {
  const end = parseFloat(el.dataset.count), dec = +(el.dataset.dec || 0);
  if (Number.isNaN(end)) return;
  const show = (v) => { el.textContent = v.toFixed(dec).replace(/^-/, "−"); };
  if (reduced || !isFinite(end)) { show(end); return; }
  const t0 = performance.now(), dur = 700;
  const step = (t) => { const k = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - k, 3); show(end * e); if (k < 1) requestAnimationFrame(step); else show(end); };
  requestAnimationFrame(step);
}

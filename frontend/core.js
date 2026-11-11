/* Shared helpers: DOM, escaping, storage, API client, application state. No engineering logic lives in the front end. */
export const $ = (s, el = document) => el.querySelector(s);
export const $$ = (s, el = document) => [...el.querySelectorAll(s)];
export const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
export const reduced = () => matchMedia("(prefers-reduced-motion: reduce)").matches;
export const keep = {
  get: (k, s = sessionStorage) => { try { return s.getItem(k); } catch { return null; } },
  set: (k, v, s = sessionStorage) => { try { s.setItem(k, v); } catch { /* storage unavailable */ } },
};
export const bus = new EventTarget();
export const emit = (name, detail) => bus.dispatchEvent(new CustomEvent(name, { detail }));
export const on = (name, fn) => bus.addEventListener(name, (e) => fn(e.detail));

/* state shared between modules */
export const state = {
  health: null,          // last /api/health
  backendUp: null,       // null unknown, true, false
  lastRunMs: null,       // sum of trace ms of the latest run that carried a trace
  unavailable: new Set(JSON.parse(keep.get("sdcv_unavailable", localStorage) || "[]")), // models that failed the last live check
  current: null,         // result shown in Form design
};
export function markUnavailable(ids) {
  state.unavailable = new Set(ids);
  keep.set("sdcv_unavailable", JSON.stringify([...ids]), localStorage);
  emit("models");
}

/* ------------------------------------------------------------------ api */
let inflight = 0;
const track = (d) => { inflight = Math.max(0, inflight + d); document.body.classList.toggle("busy", inflight > 0); };
let askTokenFn = async () => "";
export const setTokenAsk = (fn) => { askTokenFn = fn; };

export async function api(url, opts = {}, retried = false) {
  track(1);
  try { return await call(url, opts, retried); } finally { track(-1); }
}
async function call(url, { method = "GET", body, raw = false } = {}, retried = false) {
  const headers = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const tok = keep.get("sdcv_token");
  if (tok) headers.Authorization = "Bearer " + tok;
  let r;
  try { r = await fetch(url, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) }); }
  catch { state.backendUp = false; emit("backend"); throw new Error("The backend is not reachable. Check that the server is running."); }
  if (url.startsWith("/api/health")) { state.backendUp = r.ok; emit("backend"); }
  if (r.status === 401 && !retried && (await askTokenFn())) return call(url, { method, body, raw }, true);
  if (!r.ok) {
    let detail = "";
    try { const j = await r.json(); detail = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail).slice(0, 200); } catch { /* not json */ }
    throw new Error(r.status === 429 ? detail || "Too many requests" : r.status === 401 ? "API token missing or invalid" : r.status === 502 ? "The backend is not reachable. Check that the server is running." : `Server returned ${r.status}${detail ? ": " + detail : ""}`);
  }
  return raw ? r : r.json();
}
export async function download(url, filename) {
  const blob = await (await api(url, { raw: true })).blob();
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob); a.download = filename; a.click(); URL.revokeObjectURL(a.href);
}
export const busy = (btn, on_, label) => { btn.disabled = on_; if (label) btn.textContent = on_ ? "Working…" : label; };
export const modelQS = (sep = "?") => { const m = $("#model-select")?.value; return m ? `${sep}model=${encodeURIComponent(m)}` : ""; };

/* announce to the polite live region (run progress and results) */
export function announce(msg) { const el = $("#live"); if (el) { el.textContent = ""; setTimeout(() => { el.textContent = msg; }, 30); } }

/* record the latest run's total time (sum of stage ms) once a trace exists */
export function noteRun(res) {
  const t = res?.trace;
  if (t?.length) { state.lastRunMs = Math.round(t.reduce((a, s) => a + (s.ms || 0), 0) * 10) / 10; emit("lastrun"); }
}

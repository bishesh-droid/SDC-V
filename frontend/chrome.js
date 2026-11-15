/* Global chrome: header, sidebar (collapse and drawer), router, status bar, command palette, theme control. */
import { $, $$, esc, keep, api, state, bus, emit, on, setTokenAsk, download, announce } from "./core.js";
import { icon, kbd, led } from "./ui.js";
import { fix } from "./fmt.js";

/* ------------------------------------------------------------------ theme */
const root = document.documentElement;
const mq = matchMedia("(prefers-color-scheme: dark)");
const pref = () => { const v = keep.get("sdcv_theme", localStorage); return v === "light" || v === "dark" ? v : "system"; };
function applyTheme(p, animate = true) {
  const resolved = p === "system" ? (mq.matches ? "dark" : "light") : p;
  if (animate) { root.classList.add("theme-anim"); setTimeout(() => root.classList.remove("theme-anim"), 220); }
  root.setAttribute("data-theme", resolved); root.setAttribute("data-theme-pref", p);
  $$("#theme-seg button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.themePref === p)));
}
export function setTheme(p) { keep.set("sdcv_theme", p, localStorage); applyTheme(p); announce(`Theme: ${p}`); emit("theme", p); }
function initTheme() {
  const ic = { system: "monitor", light: "sun", dark: "moon" };
  $$("#theme-seg button").forEach((b) => { b.innerHTML = icon(ic[b.dataset.themePref]); b.onclick = () => setTheme(b.dataset.themePref); });
  applyTheme(pref(), false);
  mq.addEventListener?.("change", () => { if (pref() === "system") applyTheme("system"); });
}

/* ------------------------------------------------------------------ views and router */
export const NAV = [["home", "Home", "home"], ["chat", "Assistant", "chat"], ["design", "Form design", "form"], ["explore", "Explore sections", "explore"],
  ["kb", "Knowledge base", "kb"], ["system", "Expert system", "system"], ["history", "History", "history"], ["tests", "Test cases", "rules"], ["scope", "Scope & status", "scope"]];
const registry = {};
export const registerView = (id, v) => { registry[id] = v; };
let currentView = null;
export const currentRoute = () => currentView;

export function show(route, push = true) {
  let [view, sub] = route.split("/");
  if (!$(`#view-${view}`)) { view = "home"; sub = ""; }
  route = sub ? `${view}/${sub}` : view;
  if (currentView && currentView !== view) registry[currentView]?.leave?.();
  currentView = view;
  $$(".view").forEach((v) => { v.hidden = v.id !== `view-${view}`; });
  $$("#nav [data-view]").forEach((b) => { const on_ = b.dataset.view === view; b.setAttribute("aria-selected", on_); b.tabIndex = on_ ? 0 : -1; if (on_) b.setAttribute("aria-current", "page"); else b.removeAttribute("aria-current"); });
  if (push && location.hash !== "#" + route) history.replaceState(null, "", "#" + route);
  closeDrawer();
  $("#main").scrollTop = 0;
  registry[view]?.load?.(sub || "");
  document.title = `${NAV.find((n) => n[0] === view)[1]} · SDC-V`;
}

function buildNav() {
  const nav = $("#nav");
  nav.innerHTML = NAV.map(([id, label, ic]) => `<button type="button" role="tab" data-view="${id}" aria-selected="false" tabindex="-1" title="${esc(label)}">${icon(ic)}<span class="nav-l">${esc(label)}</span>${id === "history" ? '<span class="count" id="count-history" hidden></span>' : ""}</button>`).join("")
    + `<button type="button" class="nav-collapse" id="nav-collapse" aria-label="Collapse sidebar" title="Collapse sidebar">${icon("chevL")}<span class="nav-l">Collapse</span></button>`;
  $$("#nav [data-view]").forEach((b) => { b.onclick = () => show(b.dataset.view); });
  nav.addEventListener("keydown", (e) => {
    const tabs = $$("#nav [data-view]"), i = tabs.indexOf(document.activeElement);
    if (i < 0) return;
    const to = { ArrowDown: i + 1, ArrowUp: i - 1, Home: 0, End: tabs.length - 1 }[e.key];
    if (to !== undefined) { e.preventDefault(); const t = tabs[(to + tabs.length) % tabs.length]; t.focus(); }
  });
  const set = (c) => { $("#app").classList.toggle("nav-collapsed", c); keep.set("sdcv_nav", c ? "1" : "0", localStorage); const b = $("#nav-collapse"); b.setAttribute("aria-label", c ? "Expand sidebar" : "Collapse sidebar"); b.title = b.getAttribute("aria-label"); b.innerHTML = icon(c ? "chevR" : "chevL") + '<span class="nav-l">Collapse</span>'; };
  $("#nav-collapse").onclick = () => set(!$("#app").classList.contains("nav-collapsed"));
  if (keep.get("sdcv_nav", localStorage) === "1") set(true);
  $("#btn-menu").innerHTML = icon("menu");
  $("#btn-menu").onclick = () => { const o = $("#app").classList.toggle("nav-open"); $("#btn-menu").setAttribute("aria-expanded", o); $("#nav-backdrop").hidden = !o; if (o) $("#nav [aria-selected=true]")?.focus(); };
  $("#nav-backdrop").onclick = closeDrawer;
  addEventListener("keydown", (e) => { if (e.key === "Escape" && $("#app").classList.contains("nav-open")) { closeDrawer(); $("#btn-menu").focus(); } });
}
function closeDrawer() { $("#app").classList.remove("nav-open"); $("#btn-menu")?.setAttribute("aria-expanded", "false"); const b = $("#nav-backdrop"); if (b) b.hidden = true; }

export function setHistoryCount(n) { const c = $("#count-history"); if (c) { c.textContent = n; c.hidden = !n; } }

/* ------------------------------------------------------------------ token dialog */
function initToken() {
  const dlg = $("#dlg-token");
  const ask = () => new Promise((resolve) => {
    $("#token-input").value = "";
    dlg.addEventListener("close", () => { const v = dlg.returnValue === "ok" ? $("#token-input").value.trim() : ""; if (v) keep.set("sdcv_token", v); resolve(v); }, { once: true });
    dlg.showModal();
  });
  setTokenAsk(ask);
  $("#btn-token").onclick = ask;
}

/* ------------------------------------------------------------------ health, model selector, gemini pill */
export async function loadHealth() {
  try { state.health = await api("/api/health"); } catch { state.health = null; }
  fillModels(); drawGemini(); drawReadouts();
  $("#btn-token").hidden = !state.health?.auth_required;
  return state.health;
}
function fillModels() {
  const h = state.health, sel = $("#model-select");
  if (!h) { sel.innerHTML = '<option value="">Models unavailable</option>'; sel.disabled = true; return; }
  const saved = keep.get("sdcv_model", localStorage), cur = sel.value, ids = h.model_options.map((m) => m.id);
  sel.innerHTML = h.model_options.map((m) => { const bad = state.unavailable.has(m.id); return `<option value="${esc(m.id)}" title="${esc(m.note)}">${esc(m.label)}${bad ? " · unavailable" : ""}</option>`; }).join("");
  sel.value = ids.includes(cur) ? cur : ids.includes(saved) ? saved : h.default_model;
  sel.disabled = !h.llm_configured;
  sel.title = (h.model_options.find((m) => m.id === sel.value) || {}).note || "";
  sel.classList.toggle("bad", state.unavailable.has(sel.value));
}
function initModelSelect() {
  $("#model-select").onchange = (e) => { keep.set("sdcv_model", e.target.value, localStorage); fillModels(); drawReadouts(); emit("model"); };
  on("models", () => { fillModels(); drawReadouts(); });
}
function drawGemini() {
  const h = state.health, l = $("#led-gem"), t = $("#txt-gem");
  if (!h) { l.className = "led fail"; t.textContent = "backend offline"; return; }
  l.className = "led " + (h.llm_configured ? "pass" : "warn");
  t.textContent = h.llm_configured ? "Gemini key found" : "Gemini key missing · form mode only";
}

/* ------------------------------------------------------------------ status bar (only data that exists) */
let copied = false;
export function drawReadouts() {
  const h = state.health, v = h?.versions, sel = $("#model-select")?.value || h?.default_model || "—";
  const item = (label, ledState, value, extra = "") => `<li>${ledState ? led(ledState) : ""}<span class="ro-l">${esc(label)}</span><b class="num">${value}</b>${extra}</li>`;
  const items = [
    item("Backend", h ? "pass" : (state.backendUp === false ? "fail" : "warn"), h ? `online v${esc(v.app)}` : "offline"),
    item("Gemini", h ? (h.llm_configured ? "pass" : "warn") : "fail", h ? (h.llm_configured ? "configured" : "missing") : "—"),
    item("Database", h && "db_ok" in h ? (h.db_ok ? "pass" : "fail") : "", h && "db_ok" in h ? (h.db_ok ? "ok" : "error") : "—"),
    item("Code", "", esc(h?.code_edition || "—")),
    `<li><span class="ro-l">Rules</span><button type="button" class="ro-btn num" id="ro-fp" title="Copy rules fingerprint" ${v ? "" : "disabled"}>${v ? esc(v.rules_fingerprint) : "—"}${icon("copy")}<span class="ro-ok" aria-live="polite">${copied ? "copied" : ""}</span></button></li>`,
    item("Model", "", esc(sel)),
    item("Last run", "", state.lastRunMs != null ? `${state.lastRunMs} ms` : "—"),
    item("Rate limit", "", h?.rate_limit_per_min ? `${h.rate_limit_per_min}/min` : (h ? "off" : "—")),
  ];
  $("#readouts").innerHTML = items.join("");
  const b = $("#ro-fp"); if (b) b.onclick = copyFingerprint;
}
export async function copyFingerprint() {
  const fp = state.health?.versions?.rules_fingerprint; if (!fp) return;
  try { await navigator.clipboard.writeText(fp); copied = true; announce("Rules fingerprint copied"); } catch { copied = false; announce("Copy failed"); }
  drawReadouts(); setTimeout(() => { copied = false; drawReadouts(); }, 1600);
}

/* ------------------------------------------------------------------ command palette */
const THEMES = [["system", "Theme: System"], ["light", "Theme: Light"], ["dark", "Theme: Dark"]];
function commands() {
  return [
    ...NAV.map(([id, label, ic]) => ({ id: "go-" + id, label: "Go to " + label, group: "View", ic, run: () => show(id) })),
    { id: "demo", label: "Run the Home example", group: "Action", ic: "play", run: () => { show("home"); emit("cmd:demo"); } },
    { id: "kb", label: "Search the knowledge base", group: "Action", ic: "search", run: () => { show("kb"); setTimeout(() => $("#kb-search")?.focus(), 60); } },
    { id: "csv", label: "Export history as CSV", group: "Action", ic: "export", run: () => download("/api/runs.csv", "sdcv-runs.csv").catch((e) => announce(e.message)) },
    { id: "fp", label: "Copy rules fingerprint", group: "Action", ic: "copy", run: copyFingerprint },
    ...THEMES.map(([p, label]) => ({ id: "th-" + p, label, group: "Theme", ic: p === "dark" ? "moon" : p === "light" ? "sun" : "monitor", run: () => setTheme(p) })),
  ];
}
function initPalette() {
  const dlg = $("#dlg-palette"), q = $("#pal-q"), list = $("#pal-list");
  let items = [], idx = 0, opener = null;
  const draw = () => {
    const t = q.value.trim().toLowerCase();
    items = commands().filter((c) => !t || c.label.toLowerCase().includes(t) || c.group.toLowerCase().includes(t));
    idx = Math.min(idx, Math.max(0, items.length - 1));
    list.innerHTML = items.length ? items.map((c, i) => `<li role="option" id="pal-${i}" data-i="${i}" aria-selected="${i === idx}">${icon(c.ic)}<span>${esc(c.label)}</span><small>${esc(c.group)}</small></li>`).join("") : '<li class="pal-none" aria-disabled="true">No matching command</li>';
    q.setAttribute("aria-activedescendant", items.length ? "pal-" + idx : "");
    $(`#pal-${idx}`)?.scrollIntoView({ block: "nearest" });
  };
  const run = (i) => { const c = items[i]; if (!c) return; dlg.close(); c.run(); };
  const open = () => { opener = document.activeElement; q.value = ""; idx = 0; draw(); dlg.showModal(); q.focus(); };
  q.addEventListener("input", () => { idx = 0; draw(); });
  q.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown") { e.preventDefault(); idx = (idx + 1) % Math.max(1, items.length); draw(); }
    else if (e.key === "ArrowUp") { e.preventDefault(); idx = (idx - 1 + items.length) % Math.max(1, items.length); draw(); }
    else if (e.key === "Enter") { e.preventDefault(); run(idx); }
  });
  list.addEventListener("click", (e) => { const li = e.target.closest("[data-i]"); if (li) run(+li.dataset.i); });
  dlg.addEventListener("click", (e) => { if (e.target === dlg) dlg.close(); });
  dlg.addEventListener("close", () => { if (opener?.isConnected) opener.focus(); });
  $("#btn-cmd").onclick = open;
  $("#btn-cmd .cmdk-i").innerHTML = icon("cmd");
  addEventListener("keydown", (e) => { if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); dlg.open ? dlg.close() : open(); } });
}

/* ------------------------------------------------------------------ init */
export function initChrome() {
  initTheme(); buildNav(); initToken(); initModelSelect(); initPalette();
  on("lastrun", drawReadouts); on("backend", drawReadouts);
  $("#pill-llm").onclick = () => show("scope");
  drawReadouts();
  addEventListener("hashchange", () => show((location.hash || "#home").slice(1), false));
}

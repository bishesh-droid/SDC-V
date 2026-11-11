/* Shared components. They return HTML strings (everything user- or API-derived goes through esc/N). */
import { $, $$, esc, reduced } from "./core.js";
import { N, notation, LABELS, TONE, fix, countUp } from "./fmt.js";

/* ------------------------------------------------------------- icons (inline, self-hosted) */
const P = {
  home: "M3 11l9-8 9 8M5 10v10h14V10", chat: "M4 5h16v11H9l-5 4V5z", form: "M5 3h14v18H5zM9 8h6M9 12h6M9 16h4",
  explore: "M4 20V10M10 20V4M16 20v-8M22 20H2", kb: "M4 4h12a4 4 0 0 1 4 4v12H8a4 4 0 0 1-4-4V4zM8 8h8", system: "M12 3v4M12 17v4M3 12h4M17 12h4M7 7l2 2M15 15l2 2M17 7l-2 2M9 15l-2 2M10 10h4v4h-4z",
  history: "M3 12a9 9 0 1 0 3-6.7L3 8M3 3v5h5M12 7v5l3 2", scope: "M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6l8-3zM9 12l2 2 4-4",
  pass: "M5 12l4 4 10-10", fail: "M6 6l12 12M18 6L6 18", warn: "M12 4l9 16H3L12 4zM12 10v5M12 18v.5", info: "M12 8v.5M12 11v6M3 12a9 9 0 1 0 18 0 9 9 0 0 0-18 0",
  search: "M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14zM21 21l-5-5", menu: "M4 6h16M4 12h16M4 18h16", close: "M6 6l12 12M18 6L6 18",
  chevL: "M15 6l-6 6 6 6", chevR: "M9 6l6 6-6 6", sun: "M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8zM12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4",
  moon: "M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z", monitor: "M3 4h18v12H3zM8 20h8M12 16v4", copy: "M9 9h11v11H9zM5 15V4h11", play: "M7 4l12 8-12 8z", pause: "M7 4v16M17 4v16",
  attach: "M21 11.5l-8.6 8.6a5 5 0 0 1-7.1-7.1l9-9a3.3 3.3 0 0 1 4.7 4.7l-9 9a1.7 1.7 0 0 1-2.4-2.4l8.3-8.3", cmd: "M9 6a3 3 0 1 0-3 3h12a3 3 0 1 0-3-3v12a3 3 0 1 0 3-3H6a3 3 0 1 0 3 3V6z",
  design: "M4 20L20 4M14 4h6v6M4 14v6h6", brief: "M5 4h14v16H5zM9 9h6M9 13h6", shield: "M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6l8-3z", calc: "M6 3h12v18H6zM9 7h6M9 12h2M13 12h2M9 16h2M13 16h2",
  rules: "M9 11l3 3 8-8M4 12v7h14", reviser: "M3 12a9 9 0 0 1 15-6.7L21 8M21 3v5h-5M21 12a9 9 0 0 1-15 6.7L3 16M3 21v-5h5", report: "M5 3h10l4 4v14H5zM9 12h6M9 16h6", audit: "M12 3a9 3 0 0 1 9 3v12a9 3 0 0 1-18 0V6a9 3 0 0 1 9-3zM3 12a9 3 0 0 0 18 0M3 6a9 3 0 0 0 18 0",
  explorer: "M3 3h18v18H3zM3 9h18M3 15h18M9 3v18M15 3v18", export: "M12 3v12M7 10l5 5 5-5M4 21h16", dl: "M12 3v12M7 10l5 5 5-5M4 21h16", retry: "M3 12a9 9 0 0 1 15-6.7L21 8M21 3v5h-5", led: "M12 12m-3 0a3 3 0 1 0 6 0 3 3 0 1 0-6 0",
};
export const icon = (name, cls = "") => `<svg class="ic ${cls}" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="${P[name] || P.info}"/></svg>`;

/* ------------------------------------------------------------- panel, pill, tags */
export const panel = ({ title = "", actions = "", body = "", cls = "", crop = false, id = "", sub = "" } = {}) =>
  `<section class="pnl${crop ? " crop" : ""} ${cls}"${id ? ` id="${id}"` : ""}>${(title || actions) ? `<header class="pnl-h"><h2>${title}</h2>${sub ? `<span class="pnl-sub">${sub}</span>` : ""}<div class="pnl-a">${actions}</div></header>` : ""}<div class="pnl-b">${body}</div></section>`;

const TONE_ICON = { pass: "pass", warn: "warn", fail: "fail", neutral: "info", accent: "info" };
export const pill = (tone, label, extra = "") => `<span class="pill-s ${tone}${extra ? " " + extra : ""}">${icon(TONE_ICON[tone] || "info")}<span>${esc(label)}</span></span>`;
export const statusPill = (status) => pill(TONE[status] || "neutral", LABELS[status] || status);
export const reviewedPill = () => pill("accent", "Reviewed");
export const originTag = (o) => `<span class="otag ${o === "llm" ? "llm" : "det"}" title="${o === "llm" ? "Produced by the language model" : "Produced by deterministic code"}">${o === "llm" ? "LLM" : "Deterministic"}</span>`;
export const led = (state, label = "") => `<span class="led ${state}" role="img" aria-label="${esc(label || state)}"></span>`;
export const kbd = (s) => `<kbd>${esc(s)}</kbd>`;

/* method badge for the Interface table */
export const methodBadge = (m) => `<span class="mth ${esc(m.toLowerCase())}">${esc(m)}</span>`;

/* ------------------------------------------------------------- stat tile */
export function statTile({ value, label, sub = "", go = "", dec = 0, spark = "" }) {
  const num = typeof value === "number" && isFinite(value);
  const inner = `<b class="stat-v num" ${num ? `data-count="${value}" data-dec="${dec}"` : ""}>${num ? fix(value, dec) : esc(value)}</b><span class="stat-l">${esc(label)}</span>${sub ? `<small class="stat-s">${esc(sub)}</small>` : ""}${spark}`;
  return go ? `<button type="button" class="tile" data-go="${esc(go)}">${inner}</button>` : `<div class="tile">${inner}</div>`;
}
export const runCountUps = (root = document) => $$("[data-count]", root).forEach((el) => countUp(el, reduced()));

/* ------------------------------------------------------------- states */
export const skeleton = (n = 3, cls = "") => `<div class="skel ${cls}" aria-busy="true" aria-label="Loading">${Array.from({ length: n }, (_, i) => `<i style="width:${92 - (i % 3) * 14}%"></i>`).join("")}</div>`;
export const emptyState = ({ title, text = "", action = "" }) => `<div class="state empty-s">${icon("info")}<div><b>${esc(title)}</b>${text ? `<p>${esc(text)}</p>` : ""}${action}</div></div>`;
export const errorState = ({ title = "Something went wrong", text = "", retry = true, raw = "" }) =>
  `<div class="state error-s" role="alert">${icon("warn")}<div><b>${esc(title)}</b>${text ? `<p>${esc(text)}</p>` : ""}${raw ? `<details class="rawerr"><summary>Technical detail</summary><pre>${esc(raw)}</pre></details>` : ""}${retry ? `<button type="button" class="btn ghost sm" data-retry>${icon("retry")} Retry</button>` : ""}</div></div>`;
export function bindRetry(root, fn) { const b = $("[data-retry]", root); if (b) b.onclick = fn; }

/* ------------------------------------------------------------- data table */
/* cfg: {cols:[{key,label,num,sort,render(row)->html,cls}], rows, id, empty, expand(row)->html, onRow(row), rowCls(row)} */
export function dataTable(host, cfg) {
  let sortKey = null, dir = 1;
  const open = new Set();
  const cols = cfg.cols;
  const val = (r, c) => (c.sortVal ? c.sortVal(r) : r[c.key]);
  const cell = (r, c) => c.render ? c.render(r) : esc(r[c.key] ?? "");
  function draw() {
    let rows = [...cfg.rows];
    if (sortKey) { const c = cols.find((x) => x.key === sortKey); rows.sort((a, b) => { const x = val(a, c), y = val(b, c); return (typeof x === "number" && typeof y === "number" ? x - y : String(x).localeCompare(String(y), undefined, { numeric: true })) * dir; }); }
    if (!rows.length) { host.innerHTML = cfg.empty || emptyState({ title: "Nothing to show" }); return; }
    host.innerHTML = `<div class="tbl-wrap"><table class="tbl"${cfg.id ? ` id="${cfg.id}"` : ""}><thead><tr>${cfg.expand ? '<th class="xc"></th>' : ""}${cols.map((c) => {
      const s = c.sort !== false && cfg.sortable !== false;
      return `<th class="${c.num ? "r" : ""}"${s ? ` aria-sort="${sortKey === c.key ? (dir > 0 ? "ascending" : "descending") : "none"}"` : ""}>${s ? `<button type="button" data-sort="${c.key}">${esc(c.label)}<span class="sorti" aria-hidden="true">${sortKey === c.key ? (dir > 0 ? "▲" : "▼") : ""}</span></button>` : esc(c.label)}</th>`;
    }).join("")}</tr></thead><tbody>${rows.map((r, i) => {
      const id = r.id ?? i, isOpen = open.has(id);
      return `<tr class="${cfg.onRow ? "click " : ""}${cfg.rowCls ? cfg.rowCls(r) : ""}" data-i="${i}" ${cfg.onRow ? 'tabindex="0"' : ""}>${cfg.expand ? `<td class="xc"><button type="button" class="xbtn" data-x="${esc(id)}" aria-expanded="${isOpen}" aria-label="Details">${icon(isOpen ? "chevL" : "chevR", isOpen ? "rot" : "")}</button></td>` : ""}${cols.map((c) => `<td class="${c.num ? "r num" : ""} ${c.cls || ""}">${cell(r, c)}</td>`).join("")}</tr>${cfg.expand && isOpen ? `<tr class="xrow"><td colspan="${cols.length + 1}">${cfg.expand(r)}</td></tr>` : ""}`;
    }).join("")}</tbody></table></div>`;
    $$("[data-sort]", host).forEach((b) => { b.onclick = () => { if (sortKey === b.dataset.sort) dir = -dir; else { sortKey = b.dataset.sort; dir = 1; } draw(); }; });
    $$("[data-x]", host).forEach((b) => { b.onclick = (e) => { e.stopPropagation(); const k = b.dataset.x; open.has(k) ? open.delete(k) : open.add(k); draw(); host.querySelector(`[data-x="${CSS.escape(k)}"]`)?.focus(); cfg.onExpand?.(); }; });
    if (cfg.onRow) $$("tbody tr.click", host).forEach((tr) => {
      const r = rows[+tr.dataset.i], go = () => cfg.onRow(r);
      tr.onclick = (e) => { if (!e.target.closest("button,a,input")) go(); };
      tr.onkeydown = (e) => { if (e.key === "Enter" && e.target === tr) go(); };
    });
    cfg.after?.(host, rows);
  }
  draw();
  return { redraw: draw, setRows(r) { cfg.rows = r; draw(); } };
}
/* a plain (non-interactive) table for static reference data */
export const simpleTable = (head, rows, cls = []) => `<div class="tbl-wrap"><table class="tbl"><thead><tr>${head.map((h, i) => `<th class="${cls[i] === "num" ? "r" : ""}">${esc(h)}</th>`).join("")}</tr></thead><tbody>${rows.map((r) => `<tr>${r.map((c, i) => `<td class="${cls[i] || ""}">${typeof c === "object" && c !== null && "html" in c ? c.html : esc(c)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;

/* ------------------------------------------------------------- verifier visuals */
const stOf = (c) => c.passed ? "pass" : (c.severity === "warning" ? "warn" : "fail");
const stWord = { pass: "PASS", warn: "WARN", fail: "FAIL" };
export function checkCell(c) {
  const s = stOf(c), d = c.decimals ?? 2, u = c.unit ? " " + notation(c.unit) : "";
  const tip = `${c.title}|${c.clause}|${stWord[s]}|${fix(c.value, d)}${u} ${notation(c.op)} ${fix(c.limit, d)}${u}`;
  return `<button type="button" class="chk ${s}" data-tip="${esc(tip)}" data-rule="${esc(c.rule_id)}" aria-label="${esc(c.rule_id)}: ${stWord[s]}. ${esc(c.title)}">${icon(s === "pass" ? "pass" : s === "warn" ? "warn" : "fail")}</button>`;
}
/* Display-only utilisation. op "<=": demand=value against an upper limit. op ">=": provided=value against a minimum. Values come from the response. */
export function utilBar(c) {
  if (c.value === null || c.limit === null || c.value === undefined || c.limit === undefined) return "";
  const s = stOf(c), d = c.decimals ?? 2, u = c.unit ? " " + notation(c.unit) : "", lower = c.op === ">=";
  const max = Math.max(c.value, c.limit) * 1.18 || 1;
  const fill = Math.max(0, Math.min(100, (c.value / max) * 100)), mark = Math.max(0, Math.min(100, (c.limit / max) * 100));
  const [l, r] = lower ? ["provided", "minimum"] : ["demand", "limit"];
  return `<div class="ubar ${s}" role="img" aria-label="${esc(c.title)}: ${l} ${fix(c.value, d)}${esc(u)}, ${r} ${fix(c.limit, d)}${esc(u)}, ${stWord[s]}">
    <div class="ubar-h"><span>${esc(c.title)}</span><span class="num">${stWord[s]}</span></div>
    <div class="ubar-t"><i style="width:${fill}%"></i><b style="left:${mark}%" title="${r}"></b></div>
    <div class="ubar-f num"><span>${l} ${fix(c.value, d)}${esc(u)}</span><span>${lower ? "min" : "max"} ${fix(c.limit, d)}${esc(u)}</span></div></div>`;
}

/* ------------------------------------------------------------- title block */
export function titleBlock(res, fingerprint) {
  const rd = res.report, when = new Date().toISOString().slice(0, 16).replace("T", " ");
  const f = (k, v) => `<div><span>${esc(k)}</span><b class="num">${v}</b></div>`;
  return `<div class="tblock" aria-label="Title block">${f("Run ID", esc(res.run_id))}${f("Rules fingerprint", esc(fingerprint || "—"))}${f("Code", esc(rd?.code_edition || "IS456:2000"))}${f("Opened (UTC)", esc(when))}${f("Mode", esc(res.mode || "—"))}${f("Model", res.llm_model ? esc(res.llm_model) : "none used")}${f("Status", esc(LABELS[res.status] || res.status))}<div class="tb-stamp">${esc(res.stamp || "DRAFT")}</div></div>`;
}

/* a small console block */
export const consoleView = (lines) => `<div class="console" role="log"><button type="button" class="btn ghost sm cpy" data-copy>${icon("copy")} Copy</button><pre>${lines.map((l) => `<span class="ln ${esc(l.level || "")}"><i>${esc(l.t || "")}</i> ${esc(l.text)}</span>`).join("\n")}</pre></div>`;
export function bindCopy(root) { $$("[data-copy]", root).forEach((b) => { b.onclick = async () => { try { await navigator.clipboard.writeText($("pre", b.parentElement).innerText); b.textContent = "Copied"; } catch { b.textContent = "Copy failed"; } setTimeout(() => { b.innerHTML = `${icon("copy")} Copy`; }, 1400); }; }); }

/* ------------------------------------------------------------- tooltips (hover and keyboard) */
let tip;
export function installTooltips() {
  tip = document.createElement("div"); tip.className = "tip"; tip.setAttribute("role", "tooltip"); tip.id = "tip"; tip.hidden = true; document.body.appendChild(tip);
  const showTip = (el) => {
    const [t, clause, st, nums] = el.dataset.tip.split("|");
    tip.innerHTML = clause !== undefined && st ? `<b>${esc(t)}</b><span class="tip-c num">${esc(clause)}</span><span class="tip-s ${st.toLowerCase()}">${esc(st)}</span><span class="num">${esc(nums)}</span>` : `<b>${esc(t)}</b>`;
    tip.hidden = false;
    const r = el.getBoundingClientRect(), w = tip.getBoundingClientRect();
    tip.style.left = Math.min(Math.max(8, r.left + r.width / 2 - w.width / 2), innerWidth - w.width - 8) + "px";
    let y = r.top - w.height - 8; if (y < 8) y = r.bottom + 8; tip.style.top = y + "px";
    el.setAttribute("aria-describedby", "tip");
  };
  const hide = () => { tip.hidden = true; $$("[aria-describedby=tip]").forEach((e) => e.removeAttribute("aria-describedby")); };
  document.addEventListener("pointerover", (e) => { const t = e.target.closest?.("[data-tip]"); if (t) showTip(t); });
  document.addEventListener("pointerout", (e) => { if (e.target.closest?.("[data-tip]")) hide(); });
  document.addEventListener("focusin", (e) => { const t = e.target.closest?.("[data-tip]"); if (t) showTip(t); });
  document.addEventListener("focusout", hide);
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") hide(); });
}

/* Chart viewer: any beam drawing or knowledge-base chart opens large on the page (Gmail-style preview).
   Zoom with the toolbar, + / - / 0 keys, Ctrl+wheel or double-click; drag to pan; download as SVG or PNG. */
import { $, esc, announce } from "./core.js";
import { icon } from "./ui.js";

const STEPS = [0.5, 0.75, 1, 1.5, 2, 3, 4, 6];
let dlg, stage, holder, svg, zoom = 1, opener = null, vb = [1, 1], title = "Chart";

function build() {
  dlg = document.createElement("dialog");
  dlg.id = "dlg-viewer"; dlg.className = "viewer"; dlg.setAttribute("aria-label", "Chart viewer");
  dlg.innerHTML = `<header class="vw-top"><button type="button" class="icon-btn" id="vw-close" aria-label="Close viewer">${icon("close")}</button><h2 id="vw-title"></h2>
    <div class="vw-tools" role="toolbar" aria-label="Zoom">
      <button type="button" class="icon-btn" id="vw-out" aria-label="Zoom out" title="Zoom out (−)">−</button>
      <button type="button" class="vw-pct num" id="vw-pct" aria-label="Reset zoom to fit" title="Fit to window (0)">100%</button>
      <button type="button" class="icon-btn" id="vw-in" aria-label="Zoom in" title="Zoom in (+)">+</button>
      <span class="vw-sep"></span>
      <button type="button" class="btn ghost sm" id="vw-svg">${icon("dl")} SVG</button>
      <button type="button" class="btn ghost sm" id="vw-png">${icon("dl")} PNG</button>
    </div></header>
    <div class="vw-stage" id="vw-stage" tabindex="0" aria-label="Chart. Scroll or drag to pan; plus and minus zoom."></div>
    <p class="vw-cap" id="vw-cap"></p>`;
  document.body.appendChild(dlg);
  stage = $("#vw-stage", dlg);
  $("#vw-close", dlg).onclick = () => dlg.close();
  $("#vw-in", dlg).onclick = () => step(1); $("#vw-out", dlg).onclick = () => step(-1); $("#vw-pct", dlg).onclick = () => setZoom(1);
  $("#vw-svg", dlg).onclick = () => exportSvg(false); $("#vw-png", dlg).onclick = () => exportSvg(true);
  dlg.addEventListener("click", (e) => { if (e.target === dlg) dlg.close(); });
  dlg.addEventListener("close", () => { holder?.remove(); if (opener?.isConnected) opener.focus(); });
  dlg.addEventListener("keydown", (e) => {
    if (e.key === "+" || e.key === "=") { e.preventDefault(); step(1); }
    else if (e.key === "-" || e.key === "_") { e.preventDefault(); step(-1); }
    else if (e.key === "0") { e.preventDefault(); setZoom(1); }
  });
  stage.addEventListener("wheel", (e) => { if (e.ctrlKey || e.metaKey) { e.preventDefault(); step(e.deltaY < 0 ? 1 : -1); } }, { passive: false });
  stage.addEventListener("dblclick", () => setZoom(zoom >= 2 ? 1 : 2));
  let drag = null;
  stage.addEventListener("pointerdown", (e) => { if (e.button !== 0) return; drag = { x: e.clientX, y: e.clientY, l: stage.scrollLeft, t: stage.scrollTop }; stage.setPointerCapture(e.pointerId); stage.classList.add("drag"); });
  stage.addEventListener("pointermove", (e) => { if (drag) { stage.scrollLeft = drag.l - (e.clientX - drag.x); stage.scrollTop = drag.t - (e.clientY - drag.y); } });
  stage.addEventListener("pointerup", () => { drag = null; stage.classList.remove("drag"); });
  new ResizeObserver(() => { if (dlg.open) layout(); }).observe(stage);
}

/* unique ids in the clone so markers and hatch patterns keep working beside the original */
function reId(node, tag) {
  const map = {};
  node.querySelectorAll("[id]").forEach((el) => { map[el.id] = el.id + tag; el.id += tag; });
  node.querySelectorAll("*").forEach((el) => { for (const a of el.attributes) { if (a.value.includes("url(#")) a.value = a.value.replace(/url\(#([^)]+)\)/g, (m, id) => (map[id] ? `url(#${map[id]})` : m)); } });
}

function layout() {
  const w = stage.clientWidth - 40, h = stage.clientHeight - 40;
  const base = Math.max(160, Math.min(w, h * (vb[0] / vb[1])));
  svg.style.width = base * zoom + "px";
  svg.style.height = base * zoom * (vb[1] / vb[0]) + "px";
  $("#vw-pct", dlg).textContent = Math.round(zoom * 100) + "%";
  stage.classList.toggle("zoomed", zoom > 1);
}
function setZoom(z) {
  const prev = zoom, cx = (stage.scrollLeft + stage.clientWidth / 2) / (svg.getBoundingClientRect().width || 1), cy = (stage.scrollTop + stage.clientHeight / 2) / (svg.getBoundingClientRect().height || 1);
  zoom = Math.max(STEPS[0], Math.min(STEPS[STEPS.length - 1], z)); layout();
  if (zoom !== prev) { const r = svg.getBoundingClientRect(); stage.scrollLeft = cx * r.width - stage.clientWidth / 2; stage.scrollTop = cy * r.height - stage.clientHeight / 2; }
  announce(`Zoom ${Math.round(zoom * 100)} percent`);
}
function step(dir) {
  const i = STEPS.findIndex((s) => s >= zoom - 1e-6), cur = i < 0 ? STEPS.length - 1 : i;
  setZoom(STEPS[Math.max(0, Math.min(STEPS.length - 1, cur + dir))]);
}

/* inline the computed paint properties so the exported file looks the same outside the page */
function standalone() {
  const out = svg.cloneNode(true);
  const src = [svg, ...svg.querySelectorAll("*")], dst = [out, ...out.querySelectorAll("*")];
  const props = ["fill", "stroke", "stroke-width", "stroke-dasharray", "opacity", "font-family", "font-size", "font-weight", "text-anchor"];
  src.forEach((el, i) => { const cs = getComputedStyle(el); dst[i].setAttribute("style", props.map((p) => `${p}:${cs.getPropertyValue(p)}`).join(";")); dst[i].removeAttribute("class"); });
  out.removeAttribute("style"); out.setAttribute("xmlns", "http://www.w3.org/2000/svg");
  out.setAttribute("width", vb[0] * 2); out.setAttribute("height", vb[1] * 2);
  const bg = document.createElementNS("http://www.w3.org/2000/svg", "rect");
  bg.setAttribute("width", "100%"); bg.setAttribute("height", "100%"); bg.setAttribute("fill", getComputedStyle(document.documentElement).getPropertyValue("--surface").trim() || "#ffffff");
  out.insertBefore(bg, out.firstChild);
  return out;
}
function save(blob, name) { const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = name; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 2000); }
function exportSvg(png) {
  const name = "sdcv-" + title.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 40);
  const markup = new XMLSerializer().serializeToString(standalone());
  if (!png) { save(new Blob([markup], { type: "image/svg+xml" }), name + ".svg"); return; }
  const img = new Image();
  img.onload = () => {
    const c = document.createElement("canvas"); c.width = vb[0] * 2; c.height = vb[1] * 2;
    c.getContext("2d").drawImage(img, 0, 0, c.width, c.height);
    c.toBlob((b) => b && save(b, name + ".png"), "image/png");
  };
  img.src = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(markup);
}

let uid = 0;
export function openViewer(source, trigger) {
  if (!dlg) build();
  const fig = source.closest("figure") || source.parentElement;
  title = (fig.querySelector("figcaption")?.textContent || source.getAttribute("aria-label") || "Chart").trim();
  holder = document.createElement("div");
  holder.className = "vw-holder " + (source.closest(".kbchart") ? "kbchart" : "");
  svg = source.cloneNode(true); svg.removeAttribute("style"); svg.removeAttribute("width"); svg.removeAttribute("height"); svg.classList.add("vw-svg");
  reId(svg, "-v" + ++uid);
  const v = svg.viewBox.baseVal; vb = [v.width || 600, v.height || 400];
  holder.appendChild(svg); stage.replaceChildren(holder);
  $("#vw-title", dlg).textContent = title;
  opener = trigger || document.activeElement; zoom = 1;
  dlg.showModal(); layout(); stage.scrollLeft = 0; stage.scrollTop = 0; stage.focus();
  announce(`${title} opened. Plus and minus zoom, Escape closes.`);
}

/* add a magnifier button to every drawing and chart, and open on click of the drawing itself */
function decorate(root) {
  root.querySelectorAll("svg.bm, .kbchart svg").forEach((s) => {
    const host = s.closest("figure") || s.parentElement;
    if (!host || host.dataset.zoomable) return;
    host.dataset.zoomable = "1";
    const b = document.createElement("button");
    b.type = "button"; b.className = "zoom-btn"; b.setAttribute("aria-label", "Enlarge chart"); b.title = "Enlarge";
    b.innerHTML = `<svg class="ic" viewBox="0 0 24 24" aria-hidden="true"><path d="M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14zM21 21l-5-5M11 8v6M8 11h6"/></svg>`;
    b.onclick = (e) => { e.stopPropagation(); openViewer(s, b); };
    host.appendChild(b);
    s.addEventListener("click", () => openViewer(s, b));
  });
}
export function initViewer() {
  const main = $("#main");
  decorate(main);
  new MutationObserver((list) => { for (const m of list) for (const n of m.addedNodes) if (n.nodeType === 1) decorate(n); }).observe(main, { childList: true, subtree: true });
}

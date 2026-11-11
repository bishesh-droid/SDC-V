/* Knowledge base: topic grid as the entry state, chip filter once a topic or search is active. */
import { $, $$, esc, api } from "./core.js";
import { icon, panel, skeleton, emptyState, errorState, bindRetry } from "./ui.js";
import { N, notation } from "./fmt.js";
import { registerView } from "./chrome.js";

const host = $("#view-kb");
let kb = null, topic = "", t;

host.innerHTML = panel({ title: "Knowledge base", sub: '<span class="num" id="kb-count"></span>', crop: true, body: `
  <label class="sr" for="kb-search">Search the knowledge base</label>
  <div class="search">${icon("search")}<input id="kb-search" type="search" placeholder="Search keywords, e.g. development length, tau_c, wind, M25, Hardy Cross" autocomplete="off"></div>
  <div id="kb-chips" class="chips" role="group" aria-label="Filter by topic" hidden></div>
  <nav class="topicgrid" id="kb-topics" aria-label="Topics"></nav>
  <div id="kb-list">${skeleton(4)}</div><p class="hint" id="kb-note"></p>` });

const toks = () => $("#kb-search").value.trim().toLowerCase().split(/\s+/).filter(Boolean);
const hay = (e) => (e.title + " " + e.summary + " " + e.points.join(" ") + " " + e.formulas.join(" ") + " " + e.tags.join(" ") + " " + e.clause).toLowerCase();
const score = (e, ks) => { const ti = e.title.toLowerCase(), g = e.tags.join(" ").toLowerCase(), c = e.clause.toLowerCase(); return ks.reduce((s, k) => s + (ti.includes(k) ? 3 : 0) + (g.includes(k) ? 2 : 0) + (c.includes(k) ? 1 : 0), 0); };
/* highlight matches: split the plain text, escape each piece */
function hl(text, ks) {
  text = notation(text);
  if (!ks.length) return esc(text);
  const re = new RegExp("(" + ks.map((k) => k.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|") + ")", "gi");
  return text.split(re).map((p, i) => i % 2 ? `<mark>${esc(p)}</mark>` : esc(p)).join("");
}

function entry(e, label, ks) {
  const body = (e.points.length ? `<ul>${e.points.map((p) => `<li>${hl(p, ks)}</li>`).join("")}</ul>` : "") + (e.formulas.length ? `<pre>${e.formulas.map((f) => esc(notation(f))).join("\n")}</pre>` : "");
  const meta = [label, e.clause].filter(Boolean).map((m) => esc(notation(m))).join(" · ");
  return `<article class="kbe"><div class="kbt"><b>${hl(e.title, ks)}</b>${e.implemented ? '<span class="otag det">in calculator</span>' : ""}</div>${meta ? `<div class="src clause">${meta}</div>` : ""}<p>${hl(e.summary, ks)}</p>${window.kbChart ? window.kbChart(e.id) : ""}${body ? `<details${topic ? " open" : ""}><summary>Details</summary>${body}</details>` : ""}</article>`;
}

function draw() {
  const ks = toks(), active = !!topic || ks.length;
  $("#kb-topics").hidden = !!active; $("#kb-chips").hidden = !active;
  $("#kb-topics").innerHTML = kb.topics.map((x) => `<a class="topiccard" href="#kb/${esc(x.id)}"><b>${esc(x.label)}</b><small class="num">${x.count} ${x.count === 1 ? "entry" : "entries"}</small></a>`).join("");
  $("#kb-chips").innerHTML = `<a class="chip" href="#kb" aria-current="${!topic}">All</a>` + kb.topics.map((x) => `<a class="chip" href="#kb/${esc(x.id)}" aria-current="${topic === x.id}">${esc(x.label)} <small class="num">${x.count}</small></a>`).join("");
  const label = Object.fromEntries(kb.topics.map((x) => [x.id, x.label]));
  let list = kb.entries.filter((e) => (!topic || e.topic === topic) && ks.every((k) => hay(e).includes(k)));
  $("#kb-count").textContent = `${list.length} of ${kb.count} entries`;
  const out = $("#kb-list");
  if (!active) { out.innerHTML = ""; return; }
  if (!list.length) { out.innerHTML = emptyState({ title: `Nothing matches "${$("#kb-search").value.trim()}"`, text: "Try a shorter keyword or another topic." }); return; }
  if (ks.length) list = [...list].sort((a, b) => score(b, ks) - score(a, ks));
  out.innerHTML = list.map((e) => entry(e, ks.length || !topic ? label[e.topic] : "", ks)).join("");
}

async function load(sub) {
  topic = sub || "";
  if (!kb) {
    try { kb = await api("/api/kb"); } catch (err) { $("#kb-list").innerHTML = errorState({ title: "Could not load the knowledge base", text: err.message }); bindRetry($("#kb-list"), () => load(sub)); return; }
    $("#kb-note").textContent = kb.note;
  }
  if (topic && !kb.topics.some((x) => x.id === topic)) topic = "";
  draw();
}
$("#kb-search").addEventListener("input", () => { clearTimeout(t); t = setTimeout(() => kb && draw(), 120); });
registerView("kb", { load });

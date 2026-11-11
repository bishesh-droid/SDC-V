/* Beam drawings as inline SVG, drawn from numbers returned by the API only (b, D, d, xu, bars, stirrups, spacing, wu, Mu, Vu, eps_cu).
   Nothing here computes an engineering result: positions are geometry of returned values, labels are returned values.
   Strokes and fills use CSS classes (see styles.css, section "drawings") that read theme variables. */
import { esc } from "./core.js";
import { fix, notation } from "./fmt.js";

let uid = 0;
const nid = () => "d" + (++uid);
const has = (...v) => v.every((x) => x !== null && x !== undefined && Number.isFinite(+x));
const defs = (id) => `<defs><marker id="ar-${id}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" class="dim-ah"/></marker>
  <pattern id="ht-${id}" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="6" class="hatch"/></pattern></defs>`;
const svgOpen = (w, h, label, cls = "bm") => `<svg class="${cls}" viewBox="0 0 ${w} ${h}" role="img" aria-label="${esc(label)}" preserveAspectRatio="xMidYMid meet">`;

/* horizontal / vertical dimension lines with end ticks */
const dimH = (id, x1, x2, y, label, off = -6) => `<g class="dim"><line x1="${x1}" y1="${y}" x2="${x2}" y2="${y}" marker-start="url(#ar-${id})" marker-end="url(#ar-${id})"/><line x1="${x1}" y1="${y - 5}" x2="${x1}" y2="${y + 5}"/><line x1="${x2}" y1="${y - 5}" x2="${x2}" y2="${y + 5}"/><text x="${(x1 + x2) / 2}" y="${y + off}" text-anchor="middle">${esc(label)}</text></g>`;
const dimV = (id, x, y1, y2, label, side = 1) => `<g class="dim"><line x1="${x}" y1="${y1}" x2="${x}" y2="${y2}" marker-start="url(#ar-${id})" marker-end="url(#ar-${id})"/><line x1="${x - 5}" y1="${y1}" x2="${x + 5}" y2="${y1}"/><line x1="${x - 5}" y1="${y2}" x2="${x + 5}" y2="${y2}"/><text transform="translate(${x + side * 9} ${(y1 + y2) / 2}) rotate(-90)" text-anchor="middle">${esc(label)}</text></g>`;

/* ----------------------------------------------------------------- cross-section */
export function crossSection(des, inp, { caption = true } = {}) {
  if (!des || !inp || !has(des.b, des.D, des.d, inp.cover_mm) || !des.bars || !has(des.bars.dia, des.bars.n)) return "";
  const id = nid(), { b, D, d } = des, c = inp.cover_mm, sd = des.stirrup_dia || 8, dia = des.bars.dia;
  const sc = 190 / Math.max(b, D), pl = 66, pt = 40, pr = 96, pb = 30, W = b * sc + pl + pr, H = D * sc + pt + pb, x0 = pl, y0 = pt;
  const bw = b * sc, dh = D * sc;
  let s = svgOpen(W, H, `Cross-section ${fix(b, 0)} by ${fix(D, 0)} mm`) + defs(id);
  if (has(des.xu) && des.xu > 0 && des.xu <= D) s += `<rect x="${x0}" y="${y0}" width="${bw}" height="${des.xu * sc}" fill="url(#ht-${id})" class="comp"/>`;
  s += `<rect x="${x0}" y="${y0}" width="${bw}" height="${dh}" class="sect"/>`;
  const cx = x0 + c * sc, cy = y0 + c * sc, sw = Math.max(1.6, sd * sc);
  s += `<rect x="${cx + sw / 2}" y="${cy + sw / 2}" width="${bw - 2 * c * sc - sw}" height="${dh - 2 * c * sc - sw}" rx="3" class="stir" style="stroke-width:${sw}"/>`;
  if (has(des.xu) && des.xu <= D) s += `<line x1="${x0 - 6}" y1="${y0 + des.xu * sc}" x2="${x0 + bw + 6}" y2="${y0 + des.xu * sc}" class="na"/>`;
  const rr = Math.max(2.2, (dia * sc) / 2), inner0 = c + sd + dia / 2, inner1 = b - c - sd - dia / 2;
  const row = (n, yc) => Array.from({ length: n }, (_, i) => `<circle cx="${x0 + (n === 1 ? b / 2 : inner0 + (i * (inner1 - inner0)) / (n - 1)) * sc}" cy="${yc}" r="${rr}" class="bar"/>`).join("");
  const y1 = y0 + (D - c - sd - dia / 2) * sc;
  s += row(des.bars.n_layer1 || des.bars.n, y1);
  if (des.bars.n_layer2) s += row(des.bars.n_layer2, y1 - (dia + (des.min_clear_spacing || 25)) * sc);
  if (has(des.hanger_dia)) { const hy = y0 + (c + sd + des.hanger_dia / 2) * sc, hr = Math.max(2, (des.hanger_dia * sc) / 2), xa = x0 + (c + sd + des.hanger_dia / 2) * sc, xb = x0 + bw - (c + sd + des.hanger_dia / 2) * sc; s += `<circle cx="${xa}" cy="${hy}" r="${hr}" class="bar hang"/><circle cx="${xb}" cy="${hy}" r="${hr}" class="bar hang"/>`; }
  s += dimH(id, x0, x0 + bw, y0 - 18, `b = ${fix(b, 0)}`);
  s += dimV(id, x0 + bw + 18, y0, y0 + dh, `D = ${fix(D, 0)}`);
  s += dimV(id, x0 - 18, y0, y0 + d * sc, `d = ${fix(d, 1)}`, -1);
  if (has(des.xu)) s += dimV(id, x0 + bw + 52, y0, y0 + des.xu * sc, `xu = ${fix(des.xu, 1)}`);
  s += `<text x="${x0 + bw / 2}" y="${y0 + dh + 20}" text-anchor="middle" class="cap">${des.bars.n}–${fix(dia, 0)} mm bars${des.bars.n_layer2 ? " (2 layers)" : ""} · ${des.stirrup_legs || 2}-leg ${fix(sd, 0)} mm stirrups</text></svg>`;
  return caption ? `<figure class="drw">${s}<figcaption>Cross-section, drawn to scale from the returned values</figcaption></figure>` : s;
}

/* ----------------------------------------------------------------- elevation */
export function elevation(des, inp) {
  if (!des || !inp || !has(inp.span_m, des.wu)) return "";
  return elevationSvg({ span: inp.span_m, support: inp.support, wu: des.wu, sv: des.sv_prov, legs: des.stirrup_legs, sdia: des.stirrup_dia, caption: "Elevation, drawn from the returned values" });
}
export function elevationSvg({ span, support, wu = null, sv = null, legs = 2, sdia = 8, caption = "", preview = false }) {
  const id = nid(), W = 580, H = 190, x0 = 70, x1 = 510, by = 84, bh = 34;
  let s = svgOpen(W, H, `Beam elevation, ${support === "cantilever" ? "cantilever" : "simply supported"}, span ${fix(span, 2)} m`) + defs(id);
  s += `<rect x="${x0}" y="${by}" width="${x1 - x0}" height="${bh}" class="sect"/>`;
  if (has(sv) && sv > 0 && has(span)) {
    const n = Math.floor((span * 1000) / sv), step = (x1 - x0) / (span * 1000 / sv), draw = Math.min(n, 90);
    const k = n > 90 ? n / 90 : 1;
    for (let i = 1; i <= draw; i++) { const x = x0 + i * step * k; if (x < x1 - 1) s += `<line x1="${x}" y1="${by + 4}" x2="${x}" y2="${by + bh - 4}" class="tick"/>`; }
  }
  if (support === "cantilever") {
    s += `<rect x="${x0 - 14}" y="${by - 14}" width="14" height="${bh + 28}" fill="url(#ht-${id})" class="wall"/><line x1="${x0}" y1="${by - 14}" x2="${x0}" y2="${by + bh + 14}" class="sect-l"/>`;
  } else {
    s += `<path d="M${x0} ${by + bh}L${x0 - 12} ${by + bh + 20}H${x0 + 12}z" class="sup"/><circle cx="${x1}" cy="${by + bh + 8}" r="8" class="sup"/><line x1="${x1 - 16}" y1="${by + bh + 18}" x2="${x1 + 16}" y2="${by + bh + 18}" class="sup-l"/>`;
  }
  if (!preview && has(wu)) {
    const n = 15;
    s += `<line x1="${x0}" y1="${by - 30}" x2="${x1}" y2="${by - 30}" class="load"/>` + Array.from({ length: n }, (_, i) => { const x = x0 + (i * (x1 - x0)) / (n - 1); return `<line x1="${x}" y1="${by - 30}" x2="${x}" y2="${by - 3}" class="load" marker-end="url(#ar-${id})"/>`; }).join("");
    s += `<text x="${(x0 + x1) / 2}" y="${by - 38}" text-anchor="middle" class="dl">wu = ${fix(wu, 2)} kN/m</text>`;
  } else if (preview) s += `<text x="${(x0 + x1) / 2}" y="${by - 12}" text-anchor="middle" class="cap">UDL (value from the calculator after a run)</text>`;
  s += dimH(id, x0, x1, by + bh + 46, `L = ${fix(span, 2)} m`);
  if (has(sv)) s += `<text x="${(x0 + x1) / 2}" y="${by + bh + 76}" text-anchor="middle" class="cap">${legs}-leg ${fix(sdia, 0)} mm stirrups at ${fix(sv, 0)} mm c/c</text>`;
  s += "</svg>";
  return `<figure class="drw">${s}${caption ? `<figcaption>${esc(caption)}</figcaption>` : ""}</figure>`;
}

/* ----------------------------------------------------------------- shear force and bending moment */
export function diagrams(des, inp) {
  if (!des || !inp || !has(des.Vu, des.Mu, des.wu, inp.span_m)) return "";
  const id = nid(), W = 580, H = 300, x0 = 70, x1 = 510, ss = inp.support !== "cantilever";
  let s = svgOpen(W, H, `Shear force and bending moment diagrams, Vu ${fix(des.Vu, 1)} kN, Mu ${fix(des.Mu, 1)} kN·m`) + defs(id);
  // shear force (zero line at y=78)
  const z1 = 78, h1 = 46;
  s += `<text x="${x0}" y="22" class="dl">Shear force (kN)</text><line x1="${x0}" y1="${z1}" x2="${x1}" y2="${z1}" class="axisl"/>`;
  if (ss) s += `<path d="M${x0} ${z1}V${z1 - h1}L${x1} ${z1 + h1}V${z1}" class="sfd"/><text x="${x0 + 6}" y="${z1 - h1 - 6}" class="dl">+${fix(des.Vu, 1)}</text><text x="${x1 - 6}" y="${z1 + h1 + 14}" text-anchor="end" class="dl">−${fix(des.Vu, 1)}</text>`;
  else s += `<path d="M${x0} ${z1}V${z1 - h1}L${x1} ${z1}" class="sfd"/><text x="${x0 + 6}" y="${z1 - h1 - 6}" class="dl">${fix(des.Vu, 1)}</text>`;
  // bending moment (zero line at y=200)
  const z2 = 205, h2 = 56;
  s += `<text x="${x0}" y="150" class="dl">Bending moment (kN·m)</text><line x1="${x0}" y1="${z2}" x2="${x1}" y2="${z2}" class="axisl"/>`;
  if (ss) s += `<path d="M${x0} ${z2}Q${(x0 + x1) / 2} ${z2 + 2 * h2} ${x1} ${z2}Z" class="bmd"/><text x="${(x0 + x1) / 2}" y="${z2 + h2 + 18}" text-anchor="middle" class="dl">${fix(des.Mu, 1)}</text>`;
  else s += `<path d="M${x0} ${z2}V${z2 + h2}Q${(x0 + x1) / 2} ${z2} ${x1} ${z2}Z" class="bmd"/><text x="${x0 + 6}" y="${z2 + h2 + 14}" class="dl">${fix(des.Mu, 1)}</text>`;
  s += `<text x="${(x0 + x1) / 2}" y="${H - 8}" text-anchor="middle" class="cap">Shape for a uniformly distributed load; maxima are the returned Vu and Mu</text></svg>`;
  return `<figure class="drw">${s}<figcaption>Shear force and bending moment (${ss ? "simply supported" : "cantilever"})</figcaption></figure>`;
}

/* ----------------------------------------------------------------- strain and stress block (schematic) */
export function strain(des) {
  if (!des || !has(des.xu, des.d, des.D, des.xu_max)) return "";
  const id = nid(), W = 520, H = 280, top = 36, sc = 190 / des.D, ax = 190;
  const yXu = top + des.xu * sc, yD = top + des.d * sc, yMax = top + des.xu_max * sc, yB = top + des.D * sc;
  const ext = 70, tens = Math.min(110, ext * ((des.d - des.xu) / Math.max(des.xu, 1)));
  let s = svgOpen(W, H, `Strain diagram, eps_cu ${des.eps_cu ?? "n/a"}, xu ${fix(des.xu, 1)} mm`) + defs(id);
  s += `<line x1="${ax}" y1="${top - 8}" x2="${ax}" y2="${yB + 6}" class="axisl"/>`;
  s += `<path d="M${ax} ${top}L${ax + ext} ${top}L${ax} ${yXu}L${ax - tens} ${yD}L${ax} ${yD}Z" class="strn"/>`;
  if (has(des.eps_cu)) s += `<text x="${ax + ext + 6}" y="${top + 4}" class="dl">εcu = ${des.eps_cu}</text>`;
  s += `<line x1="40" y1="${yXu}" x2="${ax + 150}" y2="${yXu}" class="na"/><text x="44" y="${yXu - 5}" class="dl">neutral axis, xu = ${fix(des.xu, 1)}</text>`;
  s += `<line x1="40" y1="${yMax}" x2="${ax + 150}" y2="${yMax}" class="lim"/><text x="${ax + 154}" y="${yMax + 4}" class="dl lim-t">xu,max = ${fix(des.xu_max, 1)}</text>`;
  s += `<line x1="40" y1="${yD}" x2="${ax + 150}" y2="${yD}" class="tick"/><text x="44" y="${yD + 14}" class="dl">d = ${fix(des.d, 1)}</text>`;
  // stress block (schematic): compression zone to the right, tension force at steel level
  const sx = ax + 230;
  s += `<path d="M${sx} ${top}H${sx + 60}V${yXu * 0.5 + top * 0.5}Q${sx + 60} ${yXu} ${sx + 20} ${yXu}H${sx}Z" class="comp-b"/><text x="${sx + 66}" y="${top + 14}" class="dl">C</text>`;
  s += `<line x1="${sx - 6}" y1="${yD}" x2="${sx + 60}" y2="${yD}" class="load" marker-end="url(#ar-${id})"/><text x="${sx + 66}" y="${yD + 4}" class="dl">T</text>`;
  s += `<text x="${W / 2}" y="${H - 6}" text-anchor="middle" class="cap">Schematic, not to scale · xu/d = ${fix(des.xu_d, 3)}</text></svg>`;
  return `<figure class="drw">${s}<figcaption>Strain diagram and compression block (IS 456 limit state, schematic)</figcaption></figure>`;
}

/* ----------------------------------------------------------------- live preview from form inputs only */
export function previewSection(b, D, cover) {
  if (!has(b, D, cover) || b <= 0 || D <= 0) return "";
  const id = nid(), sc = 190 / Math.max(b, D), pl = 60, pt = 36, W = b * sc + pl + 70, H = D * sc + pt + 30, bw = b * sc, dh = D * sc;
  let s = svgOpen(W, H, `Section preview ${fix(b, 0)} by ${fix(D, 0)} mm, cover ${fix(cover, 0)} mm`) + defs(id);
  s += `<rect x="${pl}" y="${pt}" width="${bw}" height="${dh}" class="sect"/>`;
  if (cover * 2 < Math.min(b, D)) s += `<rect x="${pl + cover * sc}" y="${pt + cover * sc}" width="${bw - 2 * cover * sc}" height="${dh - 2 * cover * sc}" rx="3" class="stir thin"/>`;
  s += dimH(id, pl, pl + bw, pt - 16, `b = ${fix(b, 0)}`) + dimV(id, pl + bw + 18, pt, pt + dh, `D = ${fix(D, 0)}`);
  s += `<text x="${pl + bw / 2}" y="${pt + dh + 18}" text-anchor="middle" class="cap">cover ${fix(cover, 0)} mm · bars appear after a run</text></svg>`;
  return `<figure class="drw">${s}<figcaption>Preview from your inputs (no calculation yet)</figcaption></figure>`;
}
export const previewElevation = (span, support) => has(span) && span > 0 ? elevationSvg({ span, support, preview: true, caption: "Preview from your inputs" }) : "";

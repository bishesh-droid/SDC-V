/* Knowledge-base charts: dependency-free SVG, themed through CSS classes.
   Every number comes from the entry's own text or the calculator's published formulas (tables.py). */
(function () {
  const W = 480, H = 250, M = { l: 52, r: 16, t: 16, b: 44 };
  const f = (n, d = 2) => (+n.toFixed(d)).toString();
  const fig = (svg, cap, label) => `<figure class="kbchart"><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${label}">${svg}</svg><figcaption>${cap}</figcaption></figure>`;
  const ticks = (lo, hi, n) => {
    const raw = (hi - lo) / n, p = Math.pow(10, Math.floor(Math.log10(raw))), st = [1, 2, 2.5, 5, 10].map((m) => m * p).find((v) => v >= raw);
    const out = []; for (let v = Math.ceil(lo / st - 1e-9) * st; v <= hi + 1e-9; v += st) out.push(+v.toFixed(6)); return out;
  };

  function axes(xr, yr, xt, yt, xl, yl, sx, sy) {
    let s = "";
    yt.forEach((v) => { s += `<line class="grid" x1="${M.l}" x2="${W - M.r}" y1="${sy(v)}" y2="${sy(v)}"/><text class="tick" x="${M.l - 6}" y="${sy(v) + 4}" text-anchor="end">${f(v, 2)}</text>`; });
    xt.forEach((v) => { s += `<text class="tick" x="${sx(v)}" y="${H - M.b + 16}" text-anchor="middle">${f(v, 2)}</text>`; });
    s += `<line class="axis" x1="${M.l}" x2="${W - M.r}" y1="${H - M.b}" y2="${H - M.b}"/><line class="axis" x1="${M.l}" x2="${M.l}" y1="${M.t}" y2="${H - M.b}"/>`;
    s += `<text class="albl" x="${(M.l + W - M.r) / 2}" y="${H - 6}" text-anchor="middle">${xl}</text><text class="albl" transform="translate(12 ${(M.t + H - M.b) / 2}) rotate(-90)" text-anchor="middle">${yl}</text>`;
    return s;
  }
  const STYLES = ["s0", "s1", "s2", "s3", "s4"];
  // series: [{name, pts:[[x,y]...], pts at which to place the end label}]
  function line(o) {
    const [x0, x1] = o.x, [y0, y1] = o.y;
    const sx = (v) => M.l + ((v - x0) / (x1 - x0)) * (W - M.l - M.r), sy = (v) => H - M.b - ((v - y0) / (y1 - y0)) * (H - M.t - M.b);
    let s = axes(o.x, o.y, o.xt || ticks(x0, x1, 5), o.yt || ticks(y0, y1, 4), o.xl, o.yl, sx, sy);
    o.series.forEach((se, i) => {
      const d = se.pts.map((p, j) => (j ? "L" : "M") + f(sx(p[0]), 1) + " " + f(sy(p[1]), 1)).join("");
      s += `<path class="ln ${STYLES[i % 5]}" d="${d}"/>`;
    });
    if (o.series.length > 1) o.series.forEach((se, i) => { const x = M.l + 10 + i * 62; s += `<line class="ln ${STYLES[i % 5]}" x1="${x}" x2="${x + 16}" y1="${M.t + 2}" y2="${M.t + 2}"/><text class="slbl" x="${x + 20}" y="${M.t + 6}">${se.name}</text>`; });
    (o.marks || []).forEach((m) => { s += `<circle class="dot" cx="${sx(m[0])}" cy="${sy(m[1])}" r="3.5"/>${m[2] ? `<text class="slbl" x="${sx(m[0])}" y="${sy(m[1]) - 8}" text-anchor="middle">${m[2]}</text>` : ""}`; });
    return fig(s, o.cap, o.cap);
  }
  // bars: [{label, value, text}], handles negatives
  function bars(o) {
    const vals = o.bars.map((b) => b.value), lo = Math.min(0, ...vals) * 1.15, hi = Math.max(0, ...vals) * 1.18 || 1;
    const sy = (v) => H - M.b - ((v - lo) / (hi - lo)) * (H - M.t - M.b);
    let s = axes(null, null, [], o.yt || ticks(lo, hi, 4), "", o.yl, () => 0, sy);
    const bw = (W - M.l - M.r) / o.bars.length;
    o.bars.forEach((b, i) => {
      const x = M.l + i * bw + bw * 0.2, w = bw * 0.6, y0 = sy(0), y1 = sy(b.value), neg = b.value < 0;
      s += `<rect class="bar${b.hl ? " hl" : ""}" x="${f(x, 1)}" y="${f(Math.min(y0, y1), 1)}" width="${f(w, 1)}" height="${f(Math.abs(y1 - y0), 1)}"/>`
        + `<text class="slbl" x="${f(x + w / 2, 1)}" y="${neg ? y1 + 13 : y1 - 5}" text-anchor="middle">${b.text ?? f(b.value)}</text>`
        + `<text class="tick" x="${f(x + w / 2, 1)}" y="${H - M.b + 16 + (neg ? 0 : 0)}" text-anchor="middle">${b.label}</text>`;
    });
    if (lo < 0) s += `<line class="axis" x1="${M.l}" x2="${W - M.r}" y1="${sy(0)}" y2="${sy(0)}"/>`;
    return fig(s, o.cap, o.cap);
  }
  // horizontal bars
  function hbars(o) {
    const max = Math.max(...o.bars.map((b) => b.value)) * 1.1, rh = (H - 20) / o.bars.length, L = 190;
    let s = "";
    o.bars.forEach((b, i) => {
      const y = 10 + i * rh, w = ((W - L - 50) * b.value) / max;
      s += `<text class="tick" x="${L - 8}" y="${y + rh / 2 + 4}" text-anchor="end">${b.label}</text><rect class="bar" x="${L}" y="${y + 4}" width="${f(w, 1)}" height="${rh - 8}"/><text class="slbl" x="${L + w + 6}" y="${y + rh / 2 + 4}">${b.text}</text>`;
    });
    s += `<line class="axis" x1="${L}" x2="${L}" y1="6" y2="${H - 10}"/>`;
    return fig(s, o.cap, o.cap);
  }
  // bending moment diagrams, sagging drawn below the beam
  function bmd() {
    // m(t) is the moment in units where the largest value is about 1; sagging positive (drawn below the beam)
    const cells = [
      ["Simply supported, UDL", (t) => 4 * t * (1 - t), "max wL²/8"],
      ["Simply supported, central point load", (t) => 2 * Math.min(t, 1 - t), "max PL/4"],
      ["Cantilever, UDL (fixed end on the left)", (t) => -(1 - t) * (1 - t), "support wL²/2 (hogging)"],
      ["Fixed both ends, UDL", (t) => (6 * t - 6 * t * t - 1) * 0.5, "ends wL²/12, mid wL²/24"],
    ];
    let s = "";
    cells.forEach(([name, fn, lab], i) => {
      const cx = 20 + (i % 2) * 230, cy = 70 + Math.floor(i / 2) * 140, w = 200, sc = 34;
      const ys = Array.from({ length: 41 }, (_, k) => [cx + (k / 40) * w, cy + fn(k / 40) * sc]);
      const d = ys.map((p) => f(p[0], 1) + " " + f(p[1], 1)).join("L");
      s += `<text class="slbl" x="${cx}" y="${cy - 46}">${name}</text><path class="fill" d="M${cx} ${cy}L${d}L${cx + w} ${cy}Z"/><path class="ln s0" d="M${d}"/>`
        + `<line class="axis" x1="${cx}" x2="${cx + w}" y1="${cy}" y2="${cy}"/><text class="tick" x="${cx + w / 2}" y="${cy + sc + 18}" text-anchor="middle">${lab}</text>`;
    });
    return `<figure class="kbchart"><svg viewBox="0 0 ${W} 300" role="img" aria-label="Bending moment diagrams">${s}</svg><figcaption>Bending moment diagrams, sagging drawn below the beam. Peak values in terms of w, P and span L.</figcaption></figure>`;
  }
  function interaction() {
    const pts = [[0, 1], [0.12, 0.93], [0.3, 0.72], [0.46, 0.45], [0.55, 0.3], [0.42, 0.1], [0.3, 0]];
    return line({ x: [0, 0.7], y: [0, 1.1], xt: [0, 0.35, 0.7], yt: [0, 0.5, 1], xl: "Mu / (fck b D²)", yl: "Pu / (fck b D)", series: [{ name: "", pts }],
      marks: [[0, 1, "pure compression"], [0.55, 0.3, "balanced"], [0.3, 0, "pure bending"]], cap: "Schematic shape of a column interaction diagram (not to scale). Use the SP 16 charts for design values." });
  }

  const sqrt = Math.sqrt;
  const tauC = (pt, fck) => { pt = Math.min(Math.max(pt, 0.15), 3); const b = Math.max(1, (0.8 * fck) / (6.89 * pt)); return (0.85 * sqrt(0.8 * fck) * (sqrt(1 + 5 * b) - 1)) / (6 * b); };
  const kt = (fs, pt) => Math.min(2, 1 / (0.225 + 0.00322 * fs - 0.625 * Math.log10(Math.max(pt, 0.05))));
  const range = (a, b, n) => Array.from({ length: n + 1 }, (_, i) => a + ((b - a) * i) / n);
  const EXPO = ["Mild", "Moderate", "Severe", "Very severe", "Extreme"];

  const charts = {
    "shear-nominal-shear-stress-and-concrete-shear-strength": () =>
      line({ x: [0.15, 3], y: [0.2, 1.4], yt: [0.2, 0.6, 1, 1.4], xt: [0.15, 1, 2, 3], xl: "pt = 100 Ast / (b d)  (%)", yl: "tau_c (N/mm²)",
        series: [20, 25, 30, 35, 40].map((g) => ({ name: "M" + g, pts: range(0.15, 3, 60).map((p) => [p, tauC(p, g)]) })), cap: "Design shear strength of concrete tau_c against steel percentage, by grade (Table 19)." })
      + bars({ yl: "tau_c,max (N/mm²)", bars: [20, 25, 30, 35, 40].map((g, i) => ({ label: "M" + g, value: [2.8, 3.1, 3.5, 3.7, 4.0][i] })), cap: "Maximum shear stress tau_c,max by grade (Table 20)." }),
    "serviceability-deflection-control-by-span-to-depth-ratio": () =>
      line({ x: [0.1, 3], y: [0.8, 2.1], yt: [1, 1.5, 2], xt: [0.1, 1, 2, 3], xl: "pt = 100 Ast / (b d)  (%)", yl: "modification factor kt",
        series: [120, 160, 200, 240, 290].map((s) => ({ name: "fs " + s, pts: range(0.1, 3, 58).map((p) => [p, kt(s, p)]) })), cap: "Tension-steel modification factor kt (Fig. 4, analytic fit, capped at 2.0), for steel stress fs in N/mm²." })
      + bars({ yl: "basic L/d", bars: [{ label: "Cantilever", value: 7 }, { label: "Simply supported", value: 20 }, { label: "Continuous", value: 26 }], cap: "Basic span to effective depth ratios." }),
    "limit-state-limiting-neutral-axis-depth-and-mu-lim": () => {
      const fy = [250, 415, 500], k = [0.53, 0.48, 0.46];
      return bars({ yl: "xu,max / d", bars: fy.map((y, i) => ({ label: "Fe" + y, value: k[i] })), cap: "Limiting neutral axis depth ratio by steel grade." })
        + bars({ yl: "Mu,lim / (fck b d²)", bars: fy.map((y, i) => ({ label: "Fe" + y, value: 0.36 * k[i] * (1 - 0.42 * k[i]), text: f(0.36 * k[i] * (1 - 0.42 * k[i]), 3) })), cap: "Limiting moment of resistance coefficient by steel grade." });
    },
    "materials-elastic-modulus-and-tensile-strength-of-concrete": () =>
      line({ x: [20, 40], y: [20000, 34000], yt: [20000, 25000, 30000], xt: [20, 25, 30, 35, 40], xl: "fck (N/mm²)", yl: "Ec (N/mm²)", series: [{ name: "", pts: range(20, 40, 20).map((g) => [g, 5000 * sqrt(g)]) }], marks: [25, 30, 35].map((g) => [g, 5000 * sqrt(g), ""]), cap: "Elastic modulus Ec = 5000 sqrt(fck)." })
      + line({ x: [20, 40], y: [2.5, 4.8], yt: [3, 4], xt: [20, 25, 30, 35, 40], xl: "fck (N/mm²)", yl: "fcr (N/mm²)", series: [{ name: "", pts: range(20, 40, 20).map((g) => [g, 0.7 * sqrt(g)]) }], cap: "Flexural tensile strength fcr = 0.7 sqrt(fck)." }),
    "detailing-nominal-cover": () => bars({ yl: "Nominal cover (mm)", bars: EXPO.map((e, i) => ({ label: e, value: [20, 30, 45, 50, 75][i] })), cap: "Nominal cover for reinforced concrete by exposure condition (Table 16)." }),
    "durability-exposure-conditions": () => bars({ yl: "Min. grade (fck)", bars: EXPO.map((e, i) => ({ label: e, value: [20, 25, 30, 35, 40][i], text: "M" + [20, 25, 30, 35, 40][i] })), cap: "Minimum concrete grade for reinforced concrete by exposure (Table 5)." })
      + bars({ yl: "Nominal cover (mm)", bars: EXPO.map((e, i) => ({ label: e, value: [20, 30, 45, 50, 75][i] })), cap: "Nominal cover by exposure (Table 16)." }),
    "detailing-bar-spacing": () => bars({ yl: "Max clear spacing (mm)", bars: [{ label: "Fe250", value: 300 }, { label: "Fe415", value: 180 }, { label: "Fe500", value: 150 }], cap: "Maximum clear spacing of tension bars for crack control (Table 15, no redistribution)." }),
    "flexure-continuous-beam-moment-coefficients": () => bars({ yl: "coefficient of w L²", yt: [-0.1, -0.05, 0, 0.05, 0.1],
      bars: [{ label: "End span", value: 1 / 12, text: "+1/12" }, { label: "Interior span", value: 1 / 16, text: "+1/16" }, { label: "Next to end supp.", value: -1 / 10, text: "-1/10" }, { label: "Other supports", value: -1 / 12, text: "-1/12" }], cap: "Moment coefficients for continuous beams, dead + imposed load (Table 12). Positive = sagging." }),
    "analysis-standard-beam-formulas": bmd,
    "analysis-euler-buckling": () => bars({ yl: "Pcr relative to pinned-pinned", bars: [["Fixed-free", 2], ["Pinned-pinned", 1], ["Fixed-pinned", 0.7], ["Fixed-fixed", 0.5]].map(([l, K]) => ({ label: l, value: 1 / (K * K), text: "K = " + K + ", " + f(1 / (K * K)) + "×" })), cap: "Effect of the effective length factor K on buckling load (Pcr is proportional to 1 / K²)." }),
    "construction-formwork-stripping-times": () => hbars({ bars: [["Vertical formwork (16-24 h)", 1, "16-24 h"], ["Slab soffit, props left", 3, "3 days"], ["Beam soffit, props left", 7, "7 days"], ["Slab props, span ≤ 4.5 m", 7, "7 days"], ["Slab props, span > 4.5 m", 14, "14 days"], ["Beam props, span ≤ 6 m", 14, "14 days"], ["Beam props, span > 6 m", 21, "21 days"]].map(([label, value, text]) => ({ label, value, text })), cap: "Minimum periods before removal, OPC at normal temperatures (Cl. 11.3)." }),
    "columns-interaction-diagrams": interaction,
  };
  window.kbChart = (id) => (charts[id] ? `<div class="kbcharts">${charts[id]()}</div>` : "");
})();

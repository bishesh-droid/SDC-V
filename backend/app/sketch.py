"""Deterministic cross-section sketch (SVG). Dimensions come from the Design only."""
from __future__ import annotations

from .schemas import BeamInput, Design


def section_svg(inp: BeamInput, d: Design) -> str:
    W, H = 360, 330
    ox, oy = 70, 40
    avail_w, avail_h = 220, 220
    s = min(avail_w / d.b, avail_h / d.D)
    bw, bh = d.b * s, d.D * s
    c = inp.cover_mm * s
    sdia = d.stirrup_dia * s
    top = inp.support == "cantilever"
    ox += (avail_w - bw) / 2
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" role="img" '
             f'aria-label="Beam cross-section {d.b:.0f} by {d.D:.0f} mm">',
             '<style>text{font:11px ui-monospace,Menlo,monospace;fill:currentColor}'
             '.dim{stroke:currentColor;stroke-width:1;fill:none;opacity:.6}'
             '.concrete{fill:currentColor;fill-opacity:.07;stroke:currentColor;stroke-width:2}'
             '.stir{fill:none;stroke:currentColor;stroke-width:1.6;opacity:.85}'
             '.bar{fill:currentColor}.hanger{fill:currentColor;fill-opacity:.45}</style>',
             f'<rect class="concrete" x="{ox:.1f}" y="{oy}" width="{bw:.1f}" height="{bh:.1f}" rx="2"/>',
             f'<rect class="stir" x="{ox + c:.1f}" y="{oy + c:.1f}" width="{bw - 2 * c:.1f}" height="{bh - 2 * c:.1f}" rx="{max(2, sdia * 2):.1f}"/>']

    def row(n: int, dia: float, y: float, cls: str):
        r = max(dia * s / 2, 2.2)
        x0 = ox + c + sdia + r
        x1 = ox + bw - c - sdia - r
        for i in range(n):
            x = (x0 + x1) / 2 if n == 1 else x0 + (x1 - x0) * i / (n - 1)
            parts.append(f'<circle class="{cls}" cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}"/>')

    a = d.bars
    r_main = max(a.dia * s / 2, 2.2)
    r_h = max(d.hanger_dia * s / 2, 2.2)
    base = c + sdia
    if top:
        y1 = oy + base + r_main
        y2 = y1 + (a.dia + max(15, a.dia)) * s
        hy = oy + bh - base - r_h
    else:
        y1 = oy + bh - base - r_main
        y2 = y1 - (a.dia + max(15, a.dia)) * s
        hy = oy + base + r_h
    row(a.n_layer1, a.dia, y1, "bar")
    if a.n_layer2:
        row(a.n_layer2, a.dia, y2, "bar")
    row(2, d.hanger_dia, hy, "hanger")

    # dimensions
    parts += [
        f'<line class="dim" x1="{ox:.1f}" y1="{oy + bh + 16:.1f}" x2="{ox + bw:.1f}" y2="{oy + bh + 16:.1f}"/>',
        f'<text x="{ox + bw / 2:.1f}" y="{oy + bh + 32:.1f}" text-anchor="middle">b = {d.b:.0f}</text>',
        f'<line class="dim" x1="{ox - 16:.1f}" y1="{oy}" x2="{ox - 16:.1f}" y2="{oy + bh:.1f}"/>',
        f'<text transform="translate({ox - 22:.1f},{oy + bh / 2:.1f}) rotate(-90)" text-anchor="middle">D = {d.D:.0f}</text>',
        f'<text x="{ox + bw + 10:.1f}" y="{(y1 if not top else y1):.1f}" dominant-baseline="middle">{a.n}-{a.dia}φ</text>',
        f'<text x="{ox + bw / 2:.1f}" y="{oy - 14}" text-anchor="middle">{d.stirrup_legs}L-{d.stirrup_dia}φ @ {d.sv_prov:.0f} c/c</text>',
        f'<text x="{ox + bw + 10:.1f}" y="{hy:.1f}" dominant-baseline="middle">2-{d.hanger_dia}φ</text>',
        '</svg>',
    ]
    return "".join(parts)

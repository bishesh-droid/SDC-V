"""Generate sections/appendix_c_generated.tex from real runs of the SDC-V calculator and verifier.

Run from docs/report:  python3 tools/gen_example.py
Nothing here computes an engineering value: every number is read from design_with_verification().
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
BACKEND = HERE.parent.parent / "backend"
sys.path.insert(0, str(BACKEND))
os.environ.setdefault("SDCV_DATA_DIR", tempfile.mkdtemp())  # keep imports away from the real audit log

from app.guardrails.input import RawIntake, normalise  # noqa: E402
from app.pipeline import design_with_verification  # noqa: E402

Q = lambda v, u: {"value": v, "unit": u}  # noqa: E731

EXAMPLES = [
    ("A", "Section passes as submitted", {
        "span": Q(6, "m"), "support": "simply_supported", "b": Q(300, "mm"), "D": Q(550, "mm"), "cover": Q(30, "mm"),
        "fck": 25, "fy": 500, "dead_load": Q(15, "kN/m"), "live_load": Q(12, "kN/m"), "exposure": "moderate"}),
    ("B", "Section is enlarged by the reviser", {
        "span": Q(6, "m"), "support": "simply_supported", "b": Q(250, "mm"), "D": Q(350, "mm"), "cover": Q(30, "mm"),
        "fck": 25, "fy": 415, "dead_load": Q(10, "kN/m"), "live_load": Q(10, "kN/m"), "exposure": "moderate"}),
]


def tex(s: str) -> str:
    return (s.replace("\\", r"\textbackslash{}").replace("_", r"\_").replace("%", r"\%").replace("&", r"\&")
             .replace("#", r"\#").replace("<=", r"$\le$").replace(">=", r"$\ge$"))


def num(v, d):
    return "n/a" if v is None else f"{v:.{d}f}"


def build(tag, title, raw_d):
    raw = RawIntake.model_validate(raw_d)
    beam = normalise(raw).beam
    final, des, checks, its, status = design_with_verification(beam)
    L = []
    L.append(rf"\section{{Example {tag}: {tex(title)}}}\label{{sec:ex{tag.lower()}}}")
    L.append(rf"Input (as submitted to \code{{POST /api/design}}): {beam.support.replace(chr(95), chr(32))}, span {beam.span_m:g}~m, "
             rf"$b \times D = {beam.b_mm:.0f} \times {beam.D_mm:.0f}$~mm, nominal cover {beam.cover_mm:.0f}~mm, "
             rf"M{beam.fck}, Fe{beam.fy}, superimposed dead load {beam.dead_load_kN_per_m:g}~kN/m, "
             rf"live load {beam.live_load_kN_per_m:g}~kN/m, {beam.exposure} exposure. "
             rf"Outcome: status \code{{{status}}}, final section ${final.b_mm:.0f} \times {final.D_mm:.0f}$~mm.")
    L.append("")
    if len(its) > 1:
        L.append(rf"\begin{{table}}[H]\centering\caption{{Example {tag}: reviser iterations}}")
        L.append(r"\label{tab:ex%s-iter}\small" % tag.lower())
        L.append(r"\begin{tabular}{@{}rrrp{4.2cm}p{4.6cm}@{}}\toprule")
        L.append(r"Iter. & $b$ (mm) & $D$ (mm) & Failed error rules & Action \\ \midrule")
        for it in its:
            failed = ", ".join(rf"\code{{{f}}}" for f in it.failed) or "none"
            L.append(rf"{it.iteration} & {it.b:.0f} & {it.D:.0f} & {failed} & {tex(it.action)} \\")
        L.append(r"\bottomrule\end{tabular}\end{table}")
        L.append("")
    rows = [
        ("Self-weight", rf"{des.self_weight:.3f}", "kN/m"), ("Characteristic load $w$", rf"{des.w_char:.3f}", "kN/m"),
        ("Factored load $w_u$", rf"{des.wu:.3f}", "kN/m"), ("Design moment $M_u$", rf"{des.Mu:.2f}", "kN$\\cdot$m"),
        ("Design shear $V_u$", rf"{des.Vu:.2f}", "kN"), ("Effective depth $d$", rf"{des.d:.1f}", "mm"),
        ("Limiting moment $M_{u,\\mathrm{lim}}$", rf"{des.Mu_lim:.2f}", "kN$\\cdot$m"),
        ("$A_{st}$ required for flexure", rf"{des.ast_flex:.1f}", "mm$^2$"),
        ("$A_{st,\\min}$", rf"{des.ast_min:.1f}", "mm$^2$"), ("$A_{st,\\max}$", rf"{des.ast_max:.0f}", "mm$^2$"),
        ("Bars provided", rf"{des.bars.n}--{des.bars.dia}~mm ({des.bars.n_layer1} in layer 1, {des.bars.n_layer2} in layer 2)", ""),
        ("$A_{st}$ provided", rf"{des.ast_prov:.1f}", "mm$^2$"), ("$x_u$", rf"{des.xu:.1f}", "mm"),
        ("$x_u/d$ (limit " + f"{des.xu_max / des.d:.2f})", rf"{des.xu_d:.3f}", "--"), ("$p_t$", rf"{des.pt:.3f}", "\\%"),
        ("$\\tau_v$", rf"{des.tau_v:.3f}", "N/mm$^2$"), ("$\\tau_c$", rf"{des.tau_c:.3f}", "N/mm$^2$"),
        ("$\\tau_{c,\\max}$", rf"{des.tau_c_max:.1f}", "N/mm$^2$"), ("$V_{us}$", rf"{des.Vus:.2f}", "kN"),
        ("$s_v$ for strength", num(des.sv_strength, 1), "mm"), ("$s_v$ for minimum steel", rf"{des.sv_minsteel:.1f}", "mm"),
        ("$s_v$ upper limit $\\min(0.75d, 300)$", rf"{des.sv_limit:.1f}", "mm"),
        ("Stirrup spacing provided", rf"{des.sv_prov:.0f} ({des.stirrup_legs}-legged {des.stirrup_dia}~mm)", "mm c/c"),
        ("Actual $L/d$", rf"{des.ld_actual:.3f}", "--"), ("Basic $L/d$", rf"{des.ld_basic:.1f}", "--"),
        ("Steel stress $f_s$", rf"{des.fs:.2f}", "N/mm$^2$"), ("Modification factor $k_t$", rf"{des.kt:.3f}", "--"),
        ("Allowable $L/d$", rf"{des.ld_allow:.3f}", "--"),
        ("Clear bar spacing (layer 1)", num(des.clear_spacing, 2), "mm"),
    ]
    L.append(rf"\begin{{table}}[H]\centering\caption{{Example {tag}: calculator outputs for the final section.}}\label{{tab:ex{tag.lower()}-design}}\small")
    L.append(r"\begin{tabular}{@{}lrl@{}}\toprule Quantity & Value & Unit \\ \midrule")
    for a, b, c in rows:
        L.append(rf"{a} & {b} & {c} \\")
    L.append(r"\bottomrule\end{tabular}\end{table}")
    L.append("")
    L.append(rf"\begin{{longtable}}{{@{{}}L{{4.4cm}}c r c r l@{{}}}}\caption{{Example {tag}: verifier results for the final section ({len(checks)} rules).}}\label{{tab:ex{tag.lower()}-checks}}\\")
    L.append(r"\toprule Rule & Result & Value & Op. & Limit & Unit \\ \midrule \endfirsthead")
    L.append(r"\toprule Rule & Result & Value & Op. & Limit & Unit \\ \midrule \endhead \bottomrule \endlastfoot")
    for c in checks:
        res = "PASS" if c.passed else ("FAIL" if c.severity == "error" else "WARN")
        op = r"$\le$" if c.op == "<=" else r"$\ge$"
        unit = {"kN.m": r"kN$\cdot$m", "mm2": r"mm$^2$", "N/mm2": r"N/mm$^2$"}.get(c.unit, tex(c.unit))
        L.append(rf"\code{{{c.rule_id}}} & {res} & {num(c.value, c.decimals)} & {op} & {num(c.limit, c.decimals)} & {unit} \\")
    L.append(r"\end{longtable}")
    L.append("")
    return "\n".join(L)


def main():
    out = ["% Generated by tools/gen_example.py from real calculator and verifier runs. Do not edit by hand.", ""]
    for tag, title, raw in EXAMPLES:
        out.append(build(tag, title, raw))
    (HERE / "sections" / "appendix_c_generated.tex").write_text("\n".join(out), encoding="utf-8")
    print("wrote sections/appendix_c_generated.tex")


if __name__ == "__main__":
    main()

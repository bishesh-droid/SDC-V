"""Turns the verified Design + CheckResults into pre-formatted strings (ReportData).

The report writer (LLM) only ever sees these strings. The same strings define the set of
numbers an LLM narrative is allowed to contain (see guardrails/output.py).
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from .is456 import tables as T
from .schemas import BeamInput, CheckResult, Design

STAMP = ("DRAFT: requires review and sign-off by a licensed structural engineer. "
         "This output is not a certified design.")

_UNIT_DISPLAY = {"kN.m": "kN·m", "mm2": "mm²", "N/mm2": "N/mm²", "ratio": "", "%": "%", "mm": "mm"}


def u(unit: str) -> str:
    return _UNIT_DISPLAY.get(unit, unit)


def fmt(v: float | None, dec: int, unit: str = "") -> str:
    if v is None:
        return "n/a"
    s = f"{v:.{dec}f}"
    un = u(unit)
    return f"{s} {un}".strip()


class Row(BaseModel):
    label: str
    value: str


class CheckRow(BaseModel):
    rule_id: str
    title: str
    clause: str
    status: str            # PASS | FAIL | WARN
    severity: str
    value: str
    limit: str
    op: str
    message: str


class ReportData(BaseModel):
    code_edition: str
    status_text: str
    inputs: list[Row]
    design: list[Row]
    checks: list[CheckRow]
    assumptions: list[str]
    revision_log: list[str]
    unit_conversions: list[str] = Field(default_factory=list)
    stamp: str = STAMP


def check_row(c: CheckResult) -> CheckRow:
    status = "PASS" if c.passed else ("FAIL" if c.severity == "error" else "WARN")
    return CheckRow(
        rule_id=c.rule_id, title=c.title, clause=c.clause, status=status, severity=c.severity,
        value=fmt(c.value, c.decimals, c.unit), limit=fmt(c.limit, c.decimals, c.unit),
        op=c.op, message=c.message,
    )


def bar_text(d: Design, inp: BeamInput) -> str:
    a = d.bars
    if a.n_layer2:
        return f"{a.n_layer1}-{a.dia} mm bars in layer 1 and {a.n_layer2}-{a.dia} mm bars in layer 2"
    return f"{a.n}-{a.dia} mm bars in a single layer"


def stirrup_text(d: Design) -> str:
    return f"{d.stirrup_legs}-legged {d.stirrup_dia} mm stirrups at {d.sv_prov:.0f} mm c/c"


def build_report_data(inp: BeamInput, d: Design, checks: list[CheckResult], status: str,
                      history: list[str], conversions: list[str]) -> ReportData:
    fck, fy = inp.fck, inp.fy
    inputs = [
        Row(label="Code edition", value=T.CODE_EDITION),
        Row(label="Support", value=T.SUPPORT_LABEL[inp.support]),
        Row(label="Effective span", value=f"{inp.span_m:.2f} m"),
        Row(label="Concrete", value=f"M{fck}"),
        Row(label="Steel", value=f"Fe{fy}"),
        Row(label="Nominal cover", value=f"{inp.cover_mm:.0f} mm"),
        Row(label="Exposure", value=T.EXPOSURE_LABEL[inp.exposure]),
        Row(label="Superimposed dead load", value=f"{inp.dead_load_kN_per_m:.2f} kN/m"),
        Row(label="Live load", value=f"{inp.live_load_kN_per_m:.2f} kN/m"),
    ]
    design = [
        Row(label="Final section", value=f"{d.b:.0f} x {d.D:.0f} mm (b x D)"),
        Row(label="Effective depth d", value=f"{d.d:.1f} mm"),
        Row(label="Self-weight", value=f"{d.self_weight:.2f} kN/m"),
        Row(label="Factored load wu", value=f"{d.wu:.2f} kN/m"),
        Row(label="Design moment Mu", value=f"{d.Mu:.1f} kN·m"),
        Row(label="Design shear Vu", value=f"{d.Vu:.1f} kN"),
        Row(label="Limiting moment Mu,lim", value=f"{d.Mu_lim:.1f} kN·m"),
        Row(label="Ast required (flexure)", value=f"{d.ast_flex:.0f} mm²"),
        Row(label="Ast minimum", value=f"{d.ast_min:.0f} mm²"),
        Row(label="Tension steel provided", value=f"{bar_text(d, inp)} ({d.ast_prov:.0f} mm²)"),
        Row(label="Percentage steel pt", value=f"{d.pt:.2f} %"),
        Row(label="Neutral axis xu/d", value=f"{d.xu_d:.3f}"),
        Row(label="Nominal shear stress τv", value=f"{d.tau_v:.2f} N/mm²"),
        Row(label="Concrete shear strength τc", value=f"{d.tau_c:.2f} N/mm²"),
        Row(label="Shear reinforcement", value=stirrup_text(d)),
        Row(label="Actual span/d", value=f"{d.ld_actual:.2f}"),
        Row(label="Allowable span/d", value=f"{d.ld_allow:.2f}"),
    ]
    status_text = {
        "designed": "All error-level checks passed.",
        "needs_engineer": "One or more error-level checks failed; this section needs an engineer's attention.",
    }.get(status, status)
    return ReportData(
        code_edition=T.CODE_EDITION, status_text=status_text, inputs=inputs, design=design,
        checks=[check_row(c) for c in checks], assumptions=list(d.assumptions),
        revision_log=history, unit_conversions=conversions,
    )


def template_narrative(rd: ReportData) -> str:
    """Deterministic fallback report (fail closed). Built only from ReportData strings."""
    fails = [c for c in rd.checks if c.status == "FAIL"]
    warns = [c for c in rd.checks if c.status == "WARN"]
    passes = [c for c in rd.checks if c.status == "PASS"]
    row = {r.label: r.value for r in rd.design}
    L = ["## Summary", "",
         f"Design to {rd.code_edition}, limit state method. {rd.status_text}",
         f"- Final section: {row['Final section']}, effective depth {row['Effective depth d']}.",
         f"- Design moment {row['Design moment Mu']} and design shear {row['Design shear Vu']}.",
         f"- Tension steel: {row['Tension steel provided']}.",
         f"- Shear reinforcement: {row['Shear reinforcement']}.", ""]
    if fails or warns:
        L += ["## Issues requiring attention", ""]
        for c in fails + warns:
            tag = "FAILED" if c.status == "FAIL" else "WARNING"
            L.append(f"- {tag}: {c.title} ({c.clause}): value {c.value}, limit {c.limit}. {c.message}.")
        L.append("")
    L += ["## Checks passed", ""]
    for c in passes:
        L.append(f"- {c.title} ({c.clause}): {c.value} against {c.limit}.")
    L += ["", "## Assumptions", ""] + [f"- {a}" for a in rd.assumptions]
    if rd.revision_log:
        L += ["", "## Revision history", ""] + [f"- {h}" for h in rd.revision_log]
    L += ["", f"**{rd.stamp}**"]
    return "\n".join(L)

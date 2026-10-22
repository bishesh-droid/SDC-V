"""What-if explorer: scan nearby sections with the same deterministic calculator and rules. No LLM, no audit."""
from __future__ import annotations

from pydantic import ValidationError

from .guardrails.input import RawIntake, normalise
from .is456.calculator import design_beam
from .report import bar_text
from .schemas import BeamInput
from .verifier import run_rules

STEP = 25.0


def _row(inp: BeamInput) -> dict:
    des = design_beam(inp)
    checks = run_rules(inp, des)
    errs = [c.rule_id for c in checks if not c.passed and c.severity == "error"]
    warns = [c.rule_id for c in checks if not c.passed and c.severity == "warning"]
    return {"b": inp.b_mm, "D": inp.D_mm, "d": round(des.d, 1), "ok": not errs, "failed": errs, "warnings": warns,
            "ast_req": round(max(des.ast_flex, des.ast_min)), "ast_prov": round(des.ast_prov),
            "pt": round(des.pt, 2), "bars": bar_text(des, inp), "sv": des.sv_prov,
            "concrete_area_mm2": round(inp.b_mm * inp.D_mm), "self_weight": round(des.self_weight, 2),
            "Mu": round(des.Mu, 1), "ld_actual": round(des.ld_actual, 2), "ld_allow": round(des.ld_allow, 2)}


def explore(raw: RawIntake, depth_below: int = 4, depth_above: int = 12) -> dict:
    out = normalise(raw)
    if out.out_of_scope:
        return {"status": "out_of_scope", "errors": out.out_of_scope, "rows": []}
    if out.errors:
        return {"status": "rejected", "errors": out.errors, "rows": []}
    if out.missing:
        return {"status": "needs_info", "missing": out.missing, "errors": [], "rows": []}
    base = out.beam
    assert base is not None
    depths = [base.D_mm + STEP * k for k in range(-depth_below, depth_above + 1)]
    widths = sorted({max(150.0, base.b_mm - 50), base.b_mm, min(1000.0, base.b_mm + 50)})
    rows = []
    for b in widths:
        for D in depths:
            try:
                cand = BeamInput.model_validate({**base.model_dump(), "b_mm": b, "D_mm": D})
            except ValidationError:
                continue
            rows.append(_row(cand))
    rows.sort(key=lambda r: (r["concrete_area_mm2"], r["ast_prov"]))
    passing = [r for r in rows if r["ok"]]
    return {"status": "ok", "base": {"b": base.b_mm, "D": base.D_mm}, "rows": rows,
            "lightest_passing": passing[0] if passing else None, "passing": len(passing), "scanned": len(rows),
            "conversions": out.conversions,
            "note": "Deterministic scan using the same calculator and rules as a design run. "
                    "Lightest means smallest concrete area, then least steel. Not a cost optimisation."}

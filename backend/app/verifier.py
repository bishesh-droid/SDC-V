"""Rule registry: every pass/fail verdict comes from here.

Each rule is one function carrying a clause ID. Rules recompute key quantities
from the raw input with their own formulas, so a fault injected into the
calculator (mutation) is caught as a cross-check failure instead of passing silently.
"""
from __future__ import annotations

import math
from typing import Callable

from .is456 import tables as T
from .schemas import BeamInput, CheckResult, Design

Rule = Callable[[BeamInput, Design], CheckResult]
RULES: list[Rule] = []
RULE_META: dict[str, dict] = {}


def rule(rule_id: str, title: str, clause: str, *, severity: str = "error", revisable: bool = True):
    def deco(fn: Callable[[BeamInput, Design], dict]) -> Rule:
        def wrapped(inp: BeamInput, des: Design) -> CheckResult:
            out = fn(inp, des)
            return CheckResult(rule_id=rule_id, title=title, clause=clause,
                               severity=severity, revisable=revisable, **out)
        wrapped.__name__ = fn.__name__
        RULES.append(wrapped)
        RULE_META[rule_id] = {"title": title, "clause": clause, "severity": severity, "revisable": revisable}
        return wrapped
    return deco


def _le(value: float, limit: float, tol: float = 1e-9) -> bool:
    return value <= limit * (1 + tol) + 1e-12


def _ge(value: float, limit: float, tol: float = 1e-9) -> bool:
    return value >= limit * (1 - tol) - 1e-12


# ---------------------------------------------------------------- cross-checks
@rule("XCHK_MU", "Independent check of design moment", "IS456 Table 18; Cl. 22.2", revisable=False)
def xchk_mu(inp, des):
    sw = 25.0 * inp.b_mm * inp.D_mm / 1e6
    wu = 1.5 * (inp.dead_load_kN_per_m + inp.live_load_kN_per_m + sw)
    ref = wu * inp.span_m ** 2 / (8.0 if inp.support == "simply_supported" else 2.0)
    return dict(passed=abs(des.Mu - ref) <= 0.005 * ref + 1e-9, value=des.Mu, limit=ref,
                op="<=", unit="kN.m", decimals=1, message="Design moment agrees with an independent recomputation")


@rule("XCHK_D", "Effective depth consistent with bar arrangement", "IS456 Cl. 26.4; Cl. 22.2", revisable=False)
def xchk_d(inp, des):
    ref = inp.D_mm - des.bars.y_bar
    return dict(passed=abs(des.d - ref) <= 0.5, value=des.d, limit=ref, unit="mm", decimals=1,
                message="Effective depth equals D minus cover to bar centroid")


# --------------------------------------------------------------------- flexure
@rule("MU_LIM", "Moment within singly reinforced limit", "IS456 38.1; Annex G-1.1(a)")
def mu_lim(inp, des):
    x = T.XU_MAX_RATIO[inp.fy]
    lim = 0.36 * inp.fck * inp.b_mm * x * des.d * (des.d - 0.42 * x * des.d) / 1e6
    return dict(passed=_le(des.Mu, lim), value=des.Mu, limit=lim, unit="kN.m", decimals=1,
                message="Factored moment must not exceed Mu,lim (otherwise doubly reinforced section needed)")


@rule("MOMENT_CAPACITY", "Moment of resistance of provided steel", "IS456 Annex G-1.1(b)")
def moment_capacity(inp, des):
    a = des.ast_prov
    mr = 0.87 * inp.fy * a * des.d * (1 - a * inp.fy / (inp.b_mm * des.d * inp.fck)) / 1e6
    return dict(passed=_ge(mr, des.Mu), value=des.Mu, limit=mr, unit="kN.m", decimals=1,
                message="Factored moment must not exceed the moment of resistance Mu,R")


@rule("XU_MAX", "Neutral axis within limiting depth", "IS456 38.1")
def xu_max(inp, des):
    ratio = T.XU_MAX_RATIO[inp.fy]
    xu = 0.87 * inp.fy * des.ast_prov / (0.36 * inp.fck * inp.b_mm)
    return dict(passed=_le(xu / des.d, ratio), value=xu / des.d, limit=ratio, unit="ratio", decimals=3,
                message="Neutral axis depth within limiting value (under-reinforced section)")


@rule("MIN_TENSION_STEEL", "Minimum tension reinforcement", "IS456 26.5.1.1(a)")
def min_steel(inp, des):
    limit = 0.85 / inp.fy
    actual = des.ast_prov / (inp.b_mm * des.d)
    return dict(passed=_ge(actual, limit), value=actual, limit=limit, op=">=", unit="ratio", decimals=5,
                message="Minimum tension reinforcement As/bd >= 0.85/fy")


@rule("MAX_TENSION_STEEL", "Maximum tension reinforcement", "IS456 26.5.1.1(b)")
def max_steel(inp, des):
    limit = 0.04 * inp.b_mm * inp.D_mm
    return dict(passed=_le(des.ast_prov, limit), value=des.ast_prov, limit=limit, unit="mm2", decimals=0,
                message="Maximum tension reinforcement 4% of gross area")


# ----------------------------------------------------------------------- shear
@rule("TAU_V_MAX", "Maximum shear stress", "IS456 40.2.3; Table 20")
def tau_v_max(inp, des):
    tv = des.Vu * 1e3 / (inp.b_mm * des.d)
    return dict(passed=_le(tv, T.TAU_C_MAX[inp.fck]), value=tv, limit=T.TAU_C_MAX[inp.fck], unit="N/mm2",
                decimals=2, message="Nominal shear stress must not exceed tau_c,max (section too small otherwise)")


@rule("SHEAR_STIRRUPS", "Stirrup spacing provides shear strength", "IS456 40.4(a)")
def shear_stirrups(inp, des):
    pt = 100.0 * des.ast_prov / (inp.b_mm * des.d)
    tc = T.tau_c(pt, inp.fck)
    vus = max(0.0, des.Vu - tc * inp.b_mm * des.d / 1e3)
    asv = des.stirrup_legs * math.pi * des.stirrup_dia ** 2 / 4.0
    if vus <= 0:
        return dict(passed=True, value=des.sv_prov, limit=None, unit="mm", decimals=0,
                    message="Concrete alone resists the shear; minimum stirrups govern")
    req = 0.87 * inp.fy * asv * des.d / (vus * 1e3)
    return dict(passed=_le(des.sv_prov, req), value=des.sv_prov, limit=req, unit="mm", decimals=0,
                message="Provided stirrup spacing must not exceed the spacing required for Vus")


@rule("MIN_SHEAR_REINF", "Minimum shear reinforcement", "IS456 26.5.1.6")
def min_shear(inp, des):
    asv = des.stirrup_legs * math.pi * des.stirrup_dia ** 2 / 4.0
    lim = 0.87 * inp.fy * asv / (0.4 * inp.b_mm)
    return dict(passed=_le(des.sv_prov, lim), value=des.sv_prov, limit=lim, unit="mm", decimals=0,
                message="Stirrup spacing for Asv/(b.sv) >= 0.4/(0.87 fy)")


@rule("MAX_STIRRUP_SPACING", "Maximum stirrup spacing", "IS456 26.5.1.5")
def max_sv(inp, des):
    lim = min(0.75 * des.d, 300.0)
    return dict(passed=_le(des.sv_prov, lim), value=des.sv_prov, limit=lim, unit="mm", decimals=0,
                message="Stirrup spacing must not exceed 0.75d or 300 mm")


@rule("STIRRUP_PRACTICAL", "Stirrup spacing is practical to place", "IS456 26.5.1.5; good practice")
def sv_practical(inp, des):
    return dict(passed=_ge(des.sv_prov, T.MIN_STIRRUP_SPACING), value=des.sv_prov, limit=T.MIN_STIRRUP_SPACING,
                op=">=", unit="mm", decimals=0, message="Stirrups closer than 75 mm are difficult to place and compact")


# ------------------------------------------------------------------ deflection
@rule("DEFLECTION", "Span / effective depth (deflection control)", "IS456 23.2.1; Fig. 4")
def deflection(inp, des):
    ld = inp.span_m * 1000.0 / des.d
    basic = T.BASIC_LD[inp.support]
    if inp.support == "simply_supported" and inp.span_m > 10:
        basic *= 10.0 / inp.span_m
    pt = 100.0 * des.ast_prov / (inp.b_mm * des.d)
    ast_req = max(des.ast_flex, 0.85 * inp.b_mm * des.d / inp.fy)
    fs = 0.58 * inp.fy * ast_req / des.ast_prov
    allow = basic * T.deflection_modification(fs, pt)
    return dict(passed=_le(ld, allow), value=ld, limit=allow, unit="ratio", decimals=2,
                message="Actual span/d must not exceed basic ratio x modification factor")


# ------------------------------------------------------------------- detailing
@rule("COVER_EXPOSURE", "Nominal cover for exposure", "IS456 26.4.2; Table 16", revisable=False)
def cover_exposure(inp, des):
    lim = T.MIN_COVER[inp.exposure]
    return dict(passed=_ge(inp.cover_mm, lim), value=inp.cover_mm, limit=lim, op=">=", unit="mm", decimals=0,
                message=f"Nominal cover for {T.EXPOSURE_LABEL[inp.exposure].lower()} exposure")


@rule("GRADE_EXPOSURE", "Minimum concrete grade for exposure", "IS456 Table 5", revisable=False)
def grade_exposure(inp, des):
    lim = T.MIN_GRADE[inp.exposure]
    return dict(passed=_ge(inp.fck, lim), value=inp.fck, limit=lim, op=">=", unit="N/mm2", decimals=0,
                message=f"Minimum grade for {T.EXPOSURE_LABEL[inp.exposure].lower()} exposure")


@rule("BAR_SPACING_MIN", "Minimum clear spacing between bars", "IS456 26.3.2")
def bar_spacing_min(inp, des):
    smin = max(des.bars.dia, T.AGG_MAX + 5.0)
    n1 = des.bars.n_layer1
    clear = (inp.b_mm - 2 * (inp.cover_mm + des.stirrup_dia) - n1 * des.bars.dia) / (n1 - 1) if n1 > 1 else None
    if clear is None:
        return dict(passed=False, value=None, limit=smin, op=">=", unit="mm", decimals=0,
                    message="At least two tension bars are required in a beam")
    return dict(passed=_ge(clear, smin), value=clear, limit=smin, op=">=", unit="mm", decimals=0,
                message="Clear horizontal spacing >= max(bar dia, aggregate size + 5 mm)")


@rule("BAR_SPACING_MAX", "Maximum clear spacing of tension bars", "IS456 26.3.3(b); Table 15")
def bar_spacing_max(inp, des):
    n1 = des.bars.n_layer1
    clear = (inp.b_mm - 2 * (inp.cover_mm + des.stirrup_dia) - n1 * des.bars.dia) / (n1 - 1) if n1 > 1 else None
    lim = T.MAX_CLEAR_SPACING[inp.fy]
    if clear is None:
        return dict(passed=True, value=None, limit=lim, unit="mm", decimals=0, message="Single bar: not applicable")
    return dict(passed=_le(clear, lim), value=clear, limit=lim, unit="mm", decimals=0,
                message="Clear spacing for crack control")


@rule("SIDE_FACE_STEEL", "Side-face reinforcement for deep beams", "IS456 26.5.1.3", severity="warning", revisable=False)
def side_face(inp, des):
    lim = 750.0
    return dict(passed=_le(inp.D_mm, lim), value=inp.D_mm, limit=lim, unit="mm", decimals=0,
                message="Depth above 750 mm needs 0.1% side-face steel (not designed here)")


@rule("STEEL_CONGESTION", "Tension steel percentage reasonable", "IS456 26.5.1.1; good practice", severity="warning", revisable=False)
def congestion(inp, des):
    pt = 100.0 * des.ast_prov / (inp.b_mm * des.d)
    return dict(passed=_le(pt, 2.5), value=pt, limit=2.5, unit="%", decimals=2,
                message="Steel above 2.5% makes placing and compaction difficult")


def run_rules(inp: BeamInput, des: Design) -> list[CheckResult]:
    return [r(inp, des) for r in RULES]


def rules_fingerprint() -> str:
    import hashlib
    return hashlib.sha256("|".join(f"{k}:{v['clause']}" for k, v in RULE_META.items()).encode()).hexdigest()[:12]

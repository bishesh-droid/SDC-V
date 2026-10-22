"""Deterministic IS 456:2000 calculator for singly reinforced rectangular beams.

Pure Python. No LLM, no I/O. Units: N, mm, N/mm2 internally; kN, kN.m, kN/m at the API.
"""
from __future__ import annotations

import math

from ..schemas import BarArrangement, BeamInput, Design
from . import tables as T


def bar_area(dia: float) -> float:
    return math.pi * dia * dia / 4.0


def mu_lim_Nmm(fck: float, fy: int, b: float, d: float) -> float:
    """Limiting moment of resistance, Annex G-1.1(a) / Cl. 38.1."""
    x = T.XU_MAX_RATIO[fy]
    return 0.36 * fck * b * (x * d) * (d - 0.42 * x * d)


def mu_resistance_Nmm(ast: float, fck: float, fy: int, b: float, d: float) -> float:
    """Moment of resistance of an under-reinforced section, Annex G-1.1(b)."""
    return 0.87 * fy * ast * d * (1 - ast * fy / (b * d * fck))


def ast_for_moment(mu_Nmm: float, fck: float, fy: int, b: float, d: float) -> float | None:
    """Ast required for a given Mu (Annex G-1.1(b)); None if beyond any singly-reinforced capacity."""
    disc = 1 - 4.6 * mu_Nmm / (fck * b * d * d)
    if disc < 0:
        return None
    return 0.5 * fck / fy * (1 - math.sqrt(disc)) * b * d


def _min_horizontal_spacing(dia: float) -> float:
    return max(dia, T.AGG_MAX + 5.0)  # Cl. 26.3.2: bar dia or agg + 5 mm


def _single_layer_capacity(b: float, cover: float, phi_s: float, dia: float) -> int:
    smin = _min_horizontal_spacing(dia)
    avail = b - 2 * (cover + phi_s) - dia
    return max(0, int(math.floor(avail / (dia + smin))) + 1)


def pick_bars(ast_target: float, b: float, cover: float, phi_s: float, fy: int | None = None) -> BarArrangement:
    """Choose the lightest practical arrangement with area >= ast_target.

    Prefers a single layer; falls back to two layers. Candidates whose clear spacing exceeds the
    Table 15 crack-control limit are skipped (an extra bar is added instead). If nothing is big
    enough, returns the largest arrangement tried (the verifier will then flag the shortfall).
    """
    smax = T.MAX_CLEAR_SPACING[fy] if fy is not None else None
    best: BarArrangement | None = None
    largest: BarArrangement | None = None
    for layers in (1, 2):
        for dia in T.BAR_DIAS:
            nmax1 = _single_layer_capacity(b, cover, phi_s, dia)
            if nmax1 < 2:
                continue
            n_cap = 4 if dia == 12 else (6 if layers == 1 else 10)
            for n in range(2, n_cap + 1):
                if layers == 1:
                    if n > nmax1:
                        break
                    n1, n2 = n, 0
                else:
                    if n <= nmax1:
                        continue
                    n1 = nmax1
                    n2 = n - n1
                    if n2 > n1:
                        break
                vs = max(15.0, dia)
                c0 = cover + phi_s + dia / 2.0
                y_bar = c0 + (n2 * (dia + vs) / n if n2 else 0.0)
                if smax is not None and n1 > 1:
                    clear = (b - 2 * (cover + phi_s) - n1 * dia) / (n1 - 1)
                    if clear > smax:
                        continue
                arr = BarArrangement(dia=dia, n=n, n_layer1=n1, n_layer2=n2,
                                     area=n * bar_area(dia), y_bar=y_bar)
                if largest is None or arr.area > largest.area:
                    largest = arr
                if arr.area >= ast_target:
                    key = (arr.area, arr.n)
                    if best is None or key < (best.area, best.n):
                        best = arr
        if best is not None:
            return best
    assert largest is not None
    return largest


def design_beam(inp: BeamInput) -> Design:
    b, D, L = inp.b_mm, inp.D_mm, inp.span_m
    fck, fy, cover = inp.fck, inp.fy, inp.cover_mm
    phi_s = T.STIRRUP_DIA

    # --- loads (Table 18) -------------------------------------------------
    sw = T.GAMMA_RC * b * D / 1e6
    w_char = inp.dead_load_kN_per_m + inp.live_load_kN_per_m + sw
    wu = T.LOAD_FACTOR * w_char
    if inp.support == "simply_supported":
        Mu = wu * L * L / 8.0
        Vu = wu * L / 2.0
    else:
        Mu = wu * L * L / 2.0
        Vu = wu * L
    mu_Nmm = Mu * 1e6

    # --- flexure with bar-arrangement iteration (d depends on the bars) ---
    d = D - cover - phi_s - 16 / 2.0
    arr = pick_bars(0.0, b, cover, phi_s, fy)
    for _ in range(12):
        mlim = mu_lim_Nmm(fck, fy, b, d)
        ast_f = ast_for_moment(min(mu_Nmm, mlim), fck, fy, b, d)
        if ast_f is None:  # cannot happen for mu<=mlim, defensive
            ast_f = 0.0
        ast_min = 0.85 * b * d / fy
        target = max(ast_f, ast_min)
        arr = pick_bars(target, b, cover, phi_s, fy)
        d_new = D - arr.y_bar
        if abs(d_new - d) < 1e-9:
            break
        d = d_new
    # final values at the converged d
    mlim = mu_lim_Nmm(fck, fy, b, d)
    ast_f = ast_for_moment(min(mu_Nmm, mlim), fck, fy, b, d) or 0.0
    ast_min = 0.85 * b * d / fy
    ast_max = 0.04 * b * D
    ast_req = max(ast_f, ast_min)
    ast_prov = arr.area
    xu = 0.87 * fy * ast_prov / (0.36 * fck * b)
    xu_max = T.XU_MAX_RATIO[fy] * d
    pt = 100.0 * ast_prov / (b * d)

    # --- shear (Cl. 40) ---------------------------------------------------
    tau_v = Vu * 1e3 / (b * d)
    tc = T.tau_c(pt, fck)
    tc_max = T.TAU_C_MAX[fck]
    Vus = max(0.0, Vu - tc * b * d / 1e3)
    asv = T.STIRRUP_LEGS * bar_area(phi_s)
    sv_minsteel = 0.87 * fy * asv / (0.4 * b)  # Cl. 26.5.1.6
    sv_strength = (0.87 * fy * asv * d / (Vus * 1e3)) if Vus > 0 else None
    sv_limit = min(0.75 * d, 300.0)           # Cl. 26.5.1.5
    sv_calc = min(sv_limit, sv_minsteel, sv_strength if sv_strength is not None else 1e9)
    sv_prov = math.floor(sv_calc / 5.0) * 5.0

    # --- deflection (Cl. 23.2.1) -----------------------------------------
    ld_basic = T.BASIC_LD[inp.support]
    if inp.support == "simply_supported" and L > 10:
        ld_basic *= 10.0 / L
    fs = 0.58 * fy * (ast_req / ast_prov)
    kt = T.deflection_modification(fs, pt)
    ld_allow = ld_basic * kt
    ld_actual = L * 1000.0 / d

    # --- detailing --------------------------------------------------------
    smin = _min_horizontal_spacing(arr.dia)
    n1 = arr.n_layer1
    clear = (b - 2 * (cover + phi_s) - n1 * arr.dia) / (n1 - 1) if n1 > 1 else None
    smax = T.MAX_CLEAR_SPACING[fy]

    assumptions = [
        f"Span {L:.2f} m is taken as the effective span (Cl. 22.2) and is supplied by the user.",
        "Concrete unit weight 25 kN/m3 for self-weight (Cl. 19.2.1); load factor 1.5 on DL + LL (Table 18).",
        "Rectangular section, singly reinforced, uniformly distributed load; limit state method.",
        f"{T.STIRRUP_LEGS}-legged {phi_s} mm stirrups; nominal cover is measured to the stirrup.",
        "Design shear taken at the support (conservative; no reduction for the section at d from the face).",
        "Deflection modification factor uses an analytic fit of IS 456 Fig. 4 (capped at 2.0); verify against the chart.",
        "Nominal maximum aggregate size 20 mm; no moment redistribution; normal-weight concrete.",
        "2 nos. 12 mm hanger bars assumed at the compression face for the stirrup cage.",
    ]
    if inp.support == "cantilever":
        assumptions.append("Cantilever: tension steel is at the top face and must be anchored into the support.")

    return Design(
        b=b, D=D, d=d, self_weight=sw, w_char=w_char, wu=wu, Mu=Mu, Vu=Vu,
        Mu_lim=mlim / 1e6, xu_max=xu_max, ast_flex=ast_f, ast_min=ast_min, ast_max=ast_max,
        ast_req=ast_req, bars=arr, ast_prov=ast_prov, xu=xu, xu_d=xu / d, pt=pt,
        tau_v=tau_v, tau_c=tc, tau_c_max=tc_max, Vus=Vus, stirrup_dia=phi_s,
        stirrup_legs=T.STIRRUP_LEGS, asv=asv, sv_strength=sv_strength, sv_minsteel=sv_minsteel,
        sv_limit=sv_limit, sv_prov=sv_prov, ld_actual=ld_actual, ld_basic=ld_basic, fs=fs,
        kt=kt, ld_allow=ld_allow, clear_spacing=clear, min_clear_spacing=smin,
        max_clear_spacing=smax, assumptions=assumptions,
    )

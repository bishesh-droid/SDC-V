"""IS 456:2000 constants and lookup tables, each tagged with its clause."""
from __future__ import annotations

import math

CODE_EDITION = "IS456:2000"
ES = 2.0e5  # N/mm2

EPS_CU = 0.0035         # limiting concrete strain in flexure (Cl. 38.1); shown in the UI strain diagram, not used by the calculator
GAMMA_RC = 25.0          # kN/m3, unit weight of reinforced concrete (Cl. 19.2.1)
LOAD_FACTOR = 1.5        # Table 18, DL + LL combination
STIRRUP_DIA = 8          # mm, design assumption
STIRRUP_LEGS = 2
MIN_STIRRUP_SPACING = 75.0   # mm, practical lower limit
BAR_DIAS = (12, 16, 20, 25, 32)
AGG_MAX = 20.0           # mm, nominal max aggregate size assumed (Cl. 26.3.2)

# Cl. 38.1 Note: limiting xu,max/d
XU_MAX_RATIO = {250: 0.53, 415: 0.48, 500: 0.46}

# Table 16 (nominal cover for RCC, mm) by exposure; Cl. 26.4.2
MIN_COVER = {"mild": 20, "moderate": 30, "severe": 45, "very_severe": 50, "extreme": 75}

# Table 5 (minimum grade for RCC) by exposure
MIN_GRADE = {"mild": 20, "moderate": 25, "severe": 30, "very_severe": 35, "extreme": 40}

# Table 20: maximum shear stress tau_c,max (N/mm2) by grade
TAU_C_MAX = {20: 2.8, 25: 3.1, 30: 3.5, 35: 3.7, 40: 4.0}

# Table 15 (Cl. 26.3.3(b)): max clear spacing of tension bars for crack control, mm
MAX_CLEAR_SPACING = {250: 300.0, 415: 180.0, 500: 150.0}

# Cl. 23.2.1: basic span / effective depth ratios
BASIC_LD = {"simply_supported": 20.0, "cantilever": 7.0}

EXPOSURE_LABEL = {
    "mild": "Mild", "moderate": "Moderate", "severe": "Severe",
    "very_severe": "Very severe", "extreme": "Extreme",
}
SUPPORT_LABEL = {"simply_supported": "Simply supported", "cantilever": "Cantilever"}


def tau_c(pt_percent: float, fck: float) -> float:
    """Design shear strength of concrete, Table 19 (N/mm2).

    Closed-form expression that reproduces Table 19 (IS 456:2000, Cl. 40.2.1),
    with pt clamped to the table range 0.15 .. 3.0 %.
    """
    pt = min(max(pt_percent, 0.15), 3.0)
    beta = max(1.0, 0.8 * fck / (6.89 * pt))
    return 0.85 * math.sqrt(0.8 * fck) * (math.sqrt(1 + 5 * beta) - 1) / (6 * beta)


def deflection_modification(fs: float, pt_percent: float) -> float:
    """Modification factor kt for tension steel (Cl. 23.2.1, Fig. 4), capped at 2.0."""
    pt = max(pt_percent, 0.05)
    denom = 0.225 + 0.00322 * fs - 0.625 * math.log10(pt)
    return min(2.0, 1.0 / denom)

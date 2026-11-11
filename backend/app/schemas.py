"""Pydantic schemas shared across the pipeline."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from .is456.tables import CODE_EDITION, EPS_CU

Exposure = Literal["mild", "moderate", "severe", "very_severe", "extreme"]
Support = Literal["simply_supported", "cantilever"]


class BeamInput(BaseModel):
    """Validated, unit-normalised design input (mm, m, kN/m, N/mm2)."""

    code: Literal["IS456:2000"] = CODE_EDITION
    span_m: float = Field(gt=0, le=15, description="Effective span / cantilever length, m")
    support: Support
    b_mm: float = Field(ge=150, le=1000, description="Beam width")
    D_mm: float = Field(ge=200, le=2000, description="Overall depth")
    cover_mm: float = Field(ge=20, le=100, description="Nominal cover to stirrups")
    fck: Literal[20, 25, 30, 35, 40]
    fy: Literal[250, 415, 500]
    dead_load_kN_per_m: float = Field(ge=0, le=500, description="Superimposed DL, excl. self-weight")
    live_load_kN_per_m: float = Field(ge=0, le=500, description="Imposed (live) load")
    exposure: Exposure

    @model_validator(mode="after")
    def sanity(self):
        if self.D_mm / self.b_mm > 4:
            raise ValueError("D/b > 4: unusual section, needs engineer confirmation")
        if self.support == "cantilever" and self.span_m > 6:
            raise ValueError("Cantilever length > 6 m is outside the supported range")
        if self.dead_load_kN_per_m + self.live_load_kN_per_m <= 0:
            raise ValueError("No external load given: dead or live load must be greater than zero")
        if self.D_mm < self.cover_mm + 100:
            raise ValueError("Overall depth is too small for the stated cover")
        return self


class CheckResult(BaseModel):
    rule_id: str
    title: str
    clause: str
    passed: bool
    value: float | None = None
    limit: float | None = None
    op: Literal["<=", ">="] = "<="
    unit: str = ""
    decimals: int = 2
    severity: Literal["error", "warning"] = "error"
    revisable: bool = True  # can enlarging the section fix it?
    message: str = ""


class BarArrangement(BaseModel):
    dia: int
    n: int
    n_layer1: int
    n_layer2: int
    area: float
    y_bar: float  # distance from tension face to centroid of bars, mm


class Design(BaseModel):
    """Everything the calculator produces. Pure numbers, no prose."""

    # section and loads
    b: float
    D: float
    d: float
    self_weight: float
    w_char: float
    wu: float
    Mu: float            # kN.m
    Vu: float            # kN
    # flexure
    Mu_lim: float        # kN.m
    xu_max: float        # mm
    ast_flex: float      # mm2, required for flexure
    ast_min: float
    ast_max: float
    ast_req: float       # governing requirement
    bars: BarArrangement
    ast_prov: float
    xu: float
    xu_d: float
    pt: float            # %
    # shear
    tau_v: float
    tau_c: float
    tau_c_max: float
    Vus: float           # kN
    stirrup_dia: int
    stirrup_legs: int
    asv: float
    sv_strength: float | None
    sv_minsteel: float
    sv_limit: float
    sv_prov: float
    # deflection
    ld_actual: float
    ld_basic: float
    fs: float
    kt: float
    ld_allow: float
    # detailing
    clear_spacing: float | None
    min_clear_spacing: float
    max_clear_spacing: float
    hanger_dia: int = 12
    eps_cu: float = EPS_CU  # presentation constant (IS 456 Cl. 38.1), never used in a calculation
    assumptions: list[str] = Field(default_factory=list)

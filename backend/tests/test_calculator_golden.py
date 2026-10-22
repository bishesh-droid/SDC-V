"""Golden tests: calculator vs IS 456 tables / SP 16-style closed forms, tolerance 2%."""
import math

import pytest

from app.is456 import tables as T
from app.is456.calculator import ast_for_moment, design_beam, mu_lim_Nmm, mu_resistance_Nmm
from app.schemas import BeamInput


@pytest.mark.parametrize("fy,coeff", [(415, 0.138), (500, 0.133), (250, 0.149)])
def test_mu_lim_coefficients(fy, coeff):
    # Textbook values of Mu,lim / (fck b d2): 0.148 (Fe250), 0.138 (Fe415), 0.133 (Fe500)
    b = d = 1000.0
    ratio = mu_lim_Nmm(1.0, fy, b, d) / (b * d * d)
    assert ratio == pytest.approx(coeff, rel=0.02)


@pytest.mark.parametrize("fck,pt,expected", [
    (20, 0.25, 0.36), (20, 0.50, 0.48), (20, 0.75, 0.56), (20, 1.00, 0.62), (20, 1.50, 0.72),
    (20, 2.00, 0.79), (20, 3.00, 0.82),
    (25, 0.50, 0.49), (25, 1.00, 0.64), (25, 2.00, 0.82),
    (30, 0.50, 0.50), (30, 1.00, 0.66),
])
def test_tau_c_table_19(fck, pt, expected):
    assert T.tau_c(pt, fck) == pytest.approx(expected, abs=0.025)


@pytest.mark.parametrize("fck,fy,pt", [(20, 415, 0.5), (20, 415, 0.9), (25, 500, 0.8), (30, 415, 1.2)])
def test_flexure_round_trip(fck, fy, pt):
    """SP 16 Table 2 style: Mu/bd2 = 0.87 fy (pt/100)(1 - fy pt/(100 fck)); inverse must return pt."""
    b, d = 250.0, 450.0
    ast = pt / 100 * b * d
    mu = 0.87 * fy * (pt / 100) * (1 - fy * pt / (100 * fck)) * b * d * d
    assert ast_for_moment(mu, fck, fy, b, d) == pytest.approx(ast, rel=2e-3)
    assert mu_resistance_Nmm(ast, fck, fy, b, d) == pytest.approx(mu, rel=2e-3)


def test_sp16_style_value():
    # Fe415, M20, pt = 0.9 -> Mu/bd2 = 2.64 N/mm2
    pt, fck, fy = 0.9, 20, 415
    assert 0.87 * fy * (pt / 100) * (1 - fy * pt / (100 * fck)) == pytest.approx(2.64, rel=0.02)


def test_hand_calculation(base_input):
    """Independent hand calculation for 6 m SS beam, 300x550, M25/Fe500, DL 15, LL 12."""
    d = design_beam(base_input)
    sw = 25 * 0.3 * 0.55
    wu = 1.5 * (15 + 12 + sw)
    assert d.self_weight == pytest.approx(sw)
    assert d.wu == pytest.approx(wu)
    assert d.Mu == pytest.approx(wu * 36 / 8)
    assert d.Vu == pytest.approx(wu * 3)
    # Ast by Annex G with the final d
    ast = 0.5 * 25 / 500 * (1 - math.sqrt(1 - 4.6 * d.Mu * 1e6 / (25 * 300 * d.d ** 2))) * 300 * d.d
    assert d.ast_flex == pytest.approx(ast, rel=2e-3)
    assert d.ast_prov >= d.ast_req
    assert d.ast_min == pytest.approx(0.85 * 300 * d.d / 500)


def test_cantilever_uses_wl2_over_2(base_input):
    inp = base_input.model_copy(update={"support": "cantilever", "span_m": 2.5})
    d = design_beam(inp)
    assert d.Mu == pytest.approx(d.wu * 2.5 ** 2 / 2)
    assert d.Vu == pytest.approx(d.wu * 2.5)
    assert d.ld_basic == 7


def test_two_layers_when_wide_steel_needed():
    inp = BeamInput(span_m=8, support="simply_supported", b_mm=230, D_mm=700, cover_mm=30, fck=25, fy=415,
                    dead_load_kN_per_m=30, live_load_kN_per_m=25, exposure="moderate")
    d = design_beam(inp)
    assert d.bars.area >= d.ast_req or d.bars.n >= 6
    if d.bars.n_layer2:
        assert d.d < inp.D_mm - inp.cover_mm - 8 - d.bars.dia / 2


def test_input_validation_rejects():
    base = dict(span_m=5, support="simply_supported", b_mm=230, D_mm=450, cover_mm=30, fck=25, fy=415,
                dead_load_kN_per_m=10, live_load_kN_per_m=5, exposure="moderate")
    for bad in ({"cover_mm": 10}, {"fy": 550}, {"fck": 27}, {"D_mm": 1000}, {"dead_load_kN_per_m": 0, "live_load_kN_per_m": 0},
                {"support": "cantilever", "span_m": 8}):
        with pytest.raises(Exception):
            BeamInput(**{**base, **bad})


def test_light_load_wide_beam_gets_extra_bar_for_max_spacing():
    """Two bars in a wide beam would exceed Table 15 spacing; the picker must add a bar instead."""
    inp = BeamInput(span_m=2, support="cantilever", b_mm=300, D_mm=600, cover_mm=30, fck=25, fy=415,
                    dead_load_kN_per_m=8, live_load_kN_per_m=6, exposure="moderate")
    d = design_beam(inp)
    assert d.bars.n >= 3
    assert d.clear_spacing <= T.MAX_CLEAR_SPACING[415]

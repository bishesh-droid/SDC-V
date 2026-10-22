"""Mutation tests: perturb the calculator output; the verifier must flag every injected fault."""
import pytest

from app.is456.calculator import design_beam
from app.pipeline import design_with_verification
from app.schemas import BarArrangement
from app.verifier import RULE_META, run_rules


def failed(inp, des):
    return {c.rule_id for c in run_rules(inp, des) if not c.passed and c.severity == "error"}


def test_clean_design_passes(base_input):
    des = design_beam(base_input)
    assert failed(base_input, des) == set()


MUTATIONS = {
    "Mu_low": lambda d: d.model_copy(update={"Mu": d.Mu * 0.8}),
    "Mu_high": lambda d: d.model_copy(update={"Mu": d.Mu * 1.3}),
    "d_wrong": lambda d: d.model_copy(update={"d": d.d * 1.1}),
    "steel_short": lambda d: d.model_copy(update={"ast_prov": d.ast_prov * 0.5}),
    "steel_huge": lambda d: d.model_copy(update={"ast_prov": 99999.0}),
    "stirrup_wide": lambda d: d.model_copy(update={"sv_prov": 500.0}),
    "Vu_high": lambda d: d.model_copy(update={"Vu": 5000.0}),
}


@pytest.mark.parametrize("name", list(MUTATIONS))
def test_mutation_detected(base_input, name):
    des = design_beam(base_input)
    assert failed(base_input, MUTATIONS[name](des)), f"mutation {name} not detected"


def test_one_bar_detected(base_input):
    des = design_beam(base_input)
    bars = BarArrangement(dia=32, n=1, n_layer1=1, n_layer2=0, area=804.2, y_bar=des.bars.y_bar)
    assert "BAR_SPACING_MIN" in failed(base_input, des.model_copy(update={"bars": bars}))


def test_deflection_rule_catches_slender_beam(base_input):
    inp = base_input.model_copy(update={"span_m": 12.0, "D_mm": 400})
    des = design_beam(inp)
    assert "DEFLECTION" in failed(inp, des)


def test_every_rule_has_clause():
    assert len(RULE_META) >= 15
    assert all(m["clause"].startswith("IS456") for m in RULE_META.values())


def test_reviser_fixes_undersized_section(base_input):
    inp = base_input.model_copy(update={"D_mm": 400, "span_m": 6, "live_load_kN_per_m": 22})
    final, des, checks, its, status = design_with_verification(inp)
    assert status == "designed"
    assert final.D_mm > inp.D_mm or final.b_mm > inp.b_mm
    assert len(its) >= 2
    assert not [c for c in checks if not c.passed and c.severity == "error"]


def test_hopeless_beam_needs_engineer(base_input):
    inp = base_input.model_copy(update={"b_mm": 150, "D_mm": 300, "span_m": 14, "live_load_kN_per_m": 100})
    *_, status = design_with_verification(inp)
    assert status == "needs_engineer"


def test_cover_for_exposure_is_not_silently_fixed(base_input):
    inp = base_input.model_copy(update={"exposure": "severe", "fck": 30, "cover_mm": 30})
    final, des, checks, its, status = design_with_verification(inp)
    assert status == "needs_engineer"
    assert any(c.rule_id == "COVER_EXPOSURE" and not c.passed for c in checks)

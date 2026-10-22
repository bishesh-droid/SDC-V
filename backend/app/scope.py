"""Describes what the tool supports. Limits are read from the BeamInput schema so they cannot drift from validation."""
from __future__ import annotations

import typing

from . import config
from .guardrails import input as G
from .is456 import tables as T
from .schemas import BeamInput
from .verifier import RULE_META


def _bounds(field: str) -> dict:
    out = {}
    for m in BeamInput.model_fields[field].metadata:
        for k in ("gt", "ge", "lt", "le"):
            if hasattr(m, k):
                out[k] = getattr(m, k)
    return out


def _literal(field: str) -> list:
    return list(typing.get_args(BeamInput.model_fields[field].annotation))


def scope() -> dict:
    return {
        "code": T.CODE_EDITION,
        "supported": ["Singly reinforced rectangular beams", "Simply supported or cantilever",
                      "Uniformly distributed load", "Limit state method, IS 456:2000"],
        "limits": {
            "span_m": _bounds("span_m"), "b_mm": _bounds("b_mm"), "D_mm": _bounds("D_mm"), "cover_mm": _bounds("cover_mm"),
            "dead_load_kN_per_m": _bounds("dead_load_kN_per_m"), "live_load_kN_per_m": _bounds("live_load_kN_per_m"),
            "fck": _literal("fck"), "fy": _literal("fy"), "support": _literal("support"), "exposure": _literal("exposure"),
            "cantilever_max_m": 6, "max_D_over_b": 4,
        },
        "out_of_scope": sorted({label for _, label in G._OOS_PATTERNS}),
        "refused": sorted({label for _, label in G._UNSAFE_PATTERNS}),
        "fixed_assumptions": [
            f"Concrete unit weight {T.GAMMA_RC:g} kN/m3; load factor {T.LOAD_FACTOR:g} on DL + LL",
            f"{T.STIRRUP_LEGS}-legged {T.STIRRUP_DIA} mm stirrups; nominal cover measured to the stirrup",
            f"Nominal maximum aggregate size {T.AGG_MAX:g} mm; bar diameters {', '.join(map(str, T.BAR_DIAS))} mm",
            "12 mm hanger bars at the compression face; no moment redistribution",
            "Design shear taken at the support face (conservative)",
            "Deflection factor uses an analytic fit of IS 456 Fig. 4; tau_c uses a closed-form fit of Table 19",
        ],
        "reviser": {"max_iterations": config.MAX_REVISER_ITERATIONS, "step_mm": 25,
                    "order": "depth first (while D <= 3b and <= 2000 mm), then width (up to 1000 mm)"},
        "rule_count": len(RULE_META),
        "limits_note": "Every output is a draft that needs review by a licensed structural engineer.",
    }

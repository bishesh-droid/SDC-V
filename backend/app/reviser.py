"""Deterministic section reviser: depth in 25 mm steps, then width. No LLM."""
from __future__ import annotations

from pydantic import ValidationError

from .schemas import BeamInput

STEP = 25.0


def revise(inp: BeamInput) -> tuple[BeamInput | None, str]:
    """Return (new input, description) or (None, reason) if the section cannot grow further."""
    b, D = inp.b_mm, inp.D_mm
    if D + STEP <= 3.0 * b and D + STEP <= 2000:
        new = {"D_mm": D + STEP}
        desc = f"Depth increased {D:.0f} -> {D + STEP:.0f} mm"
    elif b + STEP <= 1000:
        new = {"b_mm": b + STEP}
        desc = f"Width increased {b:.0f} -> {b + STEP:.0f} mm"
    else:
        return None, "Section is at the supported size limits"
    try:
        return BeamInput.model_validate({**inp.model_dump(), **new}), desc
    except ValidationError as e:
        return None, f"Revised section is invalid: {e.errors()[0]['msg']}"

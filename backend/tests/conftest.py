import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from app.schemas import BeamInput


@pytest.fixture
def base_input():
    return BeamInput(span_m=6, support="simply_supported", b_mm=300, D_mm=550, cover_mm=30, fck=25, fy=500,
                     dead_load_kN_per_m=15, live_load_kN_per_m=12, exposure="moderate")


class FakeLLM:
    """Scripted LLM for tests. `responses` is a list consumed one per generate() call."""
    name = "fake"
    available = True
    last_model = "fake-model"

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.image_counts = []

    def generate(self, system, user, *, json_mode=False, images=None):
        self.calls.append((system, user, json_mode))
        self.image_counts.append(len(images or []))
        r = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        return r(user) if callable(r) else r

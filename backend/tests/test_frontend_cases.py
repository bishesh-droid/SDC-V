"""The 100 frontend test cases: structure, variety, freshness of the generated files, and expected outcomes."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

BENCH = Path(__file__).resolve().parents[2] / "benchmark"
sys.path.insert(0, str(BENCH))

import generate_frontend_cases as gen  # noqa: E402
import verify_frontend_cases as ver  # noqa: E402
from app.guardrails.input import RawIntake  # noqa: E402
from app.pipeline import Pipeline  # noqa: E402

CASES = gen.build()


def test_exactly_100_unique_cases():
    assert len(CASES) == 100
    assert len({c["id"] for c in CASES}) == 100


def test_cases_are_varied():
    assert len({c["cat"] for c in CASES}) >= 12
    assert len({c["expect"]["status"] for c in CASES}) == 7 - 1  # every status except `error`
    assert {c["path"] for c in CASES} == {"form", "chat"}
    assert any(c["llm"] for c in CASES) and any(not c["llm"] for c in CASES)


def test_generated_files_are_current():
    assert json.loads((BENCH / "frontend_cases.json").read_text(encoding="utf-8")) == CASES
    js = (BENCH.parent / "frontend" / "testcases.js").read_text(encoding="utf-8")
    assert js.split("export const CASES = ", 1)[1].rstrip().rstrip(";") == json.dumps(CASES, indent=1, ensure_ascii=False)


@pytest.mark.parametrize("case", [c for c in CASES if c["path"] == "form"], ids=lambda c: c["id"])
def test_form_case_outcome(case):
    res = Pipeline(None, None).run_structured(RawIntake.model_validate(case["input"]))
    assert ver.check(res, case["expect"]) == []


@pytest.mark.parametrize("case", [c for c in CASES if c["path"] == "chat" and not c["llm"]], ids=lambda c: c["id"])
def test_screened_chat_case_outcome(case):
    res = Pipeline(None, None).run_chat([{"role": "user", "text": case["input"]["brief"]}], case["input"].get("attachment", ""))
    assert ver.check(res, case["expect"]) == []


def test_model_dependent_cases_pass_the_deterministic_screens():
    assert ver.main() == 0

"""Runs the frontend test cases through the real pipeline with no model and no audit write, and compares to `expect`.

Form cases and the deterministic chat cases are fully checked. Cases flagged `llm` need Gemini for intake, so only the
deterministic part is checked here: the scope screen must let them through, and injection text must be flagged.

Run:  cd benchmark && python3 verify_frontend_cases.py
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "backend"))
sys.path.insert(0, str(HERE))

from app.guardrails.input import RawIntake, detect_injection, screen_scope  # noqa: E402
from app.pipeline import Pipeline  # noqa: E402
from generate_frontend_cases import build  # noqa: E402


def check(res, exp: dict) -> list[str]:
    bad = []
    if res.status != exp["status"]:
        bad.append(f"status {res.status!r}, expected {exp['status']!r}")
    if exp.get("enlarged"):
        a, b = res.original_input, res.final_input
        if not (a and b and (a.b_mm != b.b_mm or a.D_mm != b.D_mm)):
            bad.append("section was not enlarged")
    if exp.get("conversions") and not res.conversions:
        bad.append("no unit conversion recorded")
    failed = {c.rule_id for c in res.checks if not c.passed and c.severity == "error"}
    warned = {c.rule_id for c in res.checks if not c.passed and c.severity == "warning"}
    for r in exp.get("failed", []):
        if r not in failed:
            bad.append(f"rule {r} did not fail (failed: {sorted(failed)})")
    for r in exp.get("warn", []):
        if r not in warned:
            bad.append(f"rule {r} did not warn (warned: {sorted(warned)})")
    for m in exp.get("missing", []):
        if m not in res.missing:
            bad.append(f"{m} not reported missing (missing: {res.missing})")
    return bad


def main() -> int:
    pipe = Pipeline(None, None)
    problems, counts = [], {"checked": 0, "partial": 0}
    for c in build():
        exp = c["expect"]
        if c["path"] == "form":
            res = pipe.run_structured(RawIntake.model_validate(c["input"]))
            bad = check(res, exp)
            counts["checked"] += 1
        elif not c["llm"]:
            res = pipe.run_chat([{"role": "user", "text": c["input"]["brief"]}], c["input"].get("attachment", ""))
            bad = check(res, exp)
            counts["checked"] += 1
        else:
            oos, unsafe = screen_scope(c["input"]["brief"])
            bad = []
            if oos or unsafe:
                bad.append(f"deterministic screen blocks a brief that should reach the model: {oos + unsafe}")
            if "injection_suspected" in exp.get("events", []):
                text = c["input"].get("attachment", "") or c["input"]["brief"]
                if not detect_injection(text):
                    bad.append("injection text not flagged by detect_injection")
            counts["partial"] += 1
        if bad:
            problems.append((c["id"], c["title"], bad))
    print(f"fully checked {counts['checked']}, deterministic part only {counts['partial']}, problems {len(problems)}")
    for cid, title, bad in problems:
        print(f"  {cid} {title}")
        for b in bad:
            print("      -", b)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())

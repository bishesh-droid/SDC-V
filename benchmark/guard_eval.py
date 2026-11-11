"""Scores the deterministic regex guards (backend/app/guardrails/input.py) on labelled cases. No model, no network.

Two tasks, BLOCK is the positive class:
  scope      screen_scope() refuses the text (out of scope, or an unsafe request)
  injection  detect_injection() flags the text or its attachment
Sources: benchmark/cases.jsonl (adapted: out_of_scope cases are scope positives, injection cases are injection
positives, everything with a brief is a negative) and benchmark/guard_cases.jsonl (the false-positive set).
"""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).parent


def load_jsonl(name):
    return [json.loads(l) for l in open(HERE / name) if l.strip()]


def from_main_cases(cases):
    """Adapts cases.jsonl. Invalid-input cases are validation tests, not guard tests, and are skipped."""
    rows = []
    for c in cases:
        if c["category"] == "invalid":
            continue
        text, att = c.get("brief", ""), c.get("attachment", "")
        rows.append({"id": c["id"] + "/scope", "source": "cases", "task": "scope", "text": text, "attachment": "",
                     "gold": "BLOCK" if c["category"] == "out_of_scope" else "ALLOW", "known_gap": False, "note": c["category"]})
        rows.append({"id": c["id"] + "/injection", "source": "cases", "task": "injection", "text": text, "attachment": att,
                     "gold": "BLOCK" if c["category"] == "injection" else "ALLOW", "known_gap": False, "note": c["category"]})
    return rows


def all_rows():
    guard = [{**r, "source": "guard_cases"} for r in load_jsonl("guard_cases.jsonl")]
    return from_main_cases(load_jsonl("cases.jsonl")) + guard


def decide(row, guards=None):
    """Returns (BLOCK|ALLOW, detail). `guards` = (screen_scope, detect_injection); defaults to the backend's."""
    if guards is None:
        import sys
        sys.path.insert(0, str(HERE.parent / "backend"))
        from app.guardrails.input import detect_injection, screen_scope
        guards = (screen_scope, detect_injection)
    scope, inj = guards
    if row["task"] == "scope":
        oos, unsafe = scope(row["text"])
        return ("BLOCK" if (oos or unsafe) else "ALLOW"), {"oos": oos, "unsafe": unsafe}
    hits = inj(row["text"]) + inj(row["attachment"])
    return ("BLOCK" if hits else "ALLOW"), {"patterns": hits}


def evaluate(rows, guards=None):
    for r in rows:
        r["pred"], r["detail"] = decide(r, guards)
    return rows


def failures(rows, include_gaps=False):
    return [r for r in rows if r["pred"] != r["gold"] and (include_gaps or not r["known_gap"])]

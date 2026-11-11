"""Pre-flight checks for the benchmark inputs (A3).

Stops a run that could not be trusted: labels leaking into the text a guard or model sees, empty or oversized
inputs, duplicate cases, missing fields. Severity "error" aborts the run; "warning" is printed.
Adapted from ../LLM/web_guard_testing/wgtest/checks.py.
"""
from __future__ import annotations

import re
from collections import Counter

MAX_BRIEF, MAX_ATTACHMENT = 8000, 20000      # the API limits in backend/app/main.py
LABEL_TOKENS = re.compile(r"\b(out_of_scope|needs_info|needs_engineer|needs_revision|missing_contains|ast_tol|known_gap)\b")
CASE_ID = re.compile(r"\b[GRIJOVSN]\d{2}\b")   # ids such as G01, S12 or N03 must never reach the model


def model_view(case: dict) -> dict:
    """The only part of a case a guard or model may see. Everything else (id, category, expect, gold, note) is a label."""
    return {"text": case.get("brief", case.get("text", "")), "attachment": case.get("attachment", "")}


def _issue(sev, case_id, msg):
    return {"severity": sev, "case": case_id, "message": msg}


def check_cases(cases: list[dict]) -> list[dict]:
    """Checks for benchmark/cases.jsonl."""
    out, seen_ids, seen_text = [], set(), Counter()
    for c in cases:
        cid = c.get("id", "?")
        if cid in seen_ids:
            out.append(_issue("error", cid, "duplicate case id"))
        seen_ids.add(cid)
        for key in ("id", "category", "mode", "expect"):
            if key not in c:
                out.append(_issue("error", cid, f"missing field '{key}'"))
        if c.get("mode") == "structured" and not c.get("input"):
            out.append(_issue("error", cid, "structured case without an input"))
        if c.get("mode") == "chat" and not str(c.get("brief", "")).strip():
            out.append(_issue("error", cid, "chat case without a brief"))
        v = model_view(c)
        out += _leak_and_size(cid, v)
        seen_text[(v["text"], v["attachment"], c.get("category"))] += 1
    out += [_issue("warning", "-", f"{n} cases share the same text, attachment and category: {t[0][:50]!r}")
            for t, n in seen_text.items() if n > 1 and t[2] not in ("golden", "needs_revision")]
    return out


def check_guard_cases(cases: list[dict]) -> list[dict]:
    """Checks for benchmark/guard_cases.jsonl."""
    out, seen_ids, seen_text = [], set(), set()
    for c in cases:
        cid = c.get("id", "?")
        if cid in seen_ids:
            out.append(_issue("error", cid, "duplicate case id"))
        seen_ids.add(cid)
        if c.get("task") not in ("scope", "injection"):
            out.append(_issue("error", cid, f"unknown task {c.get('task')!r}"))
        if c.get("gold") not in ("ALLOW", "BLOCK"):
            out.append(_issue("error", cid, f"gold must be ALLOW or BLOCK, got {c.get('gold')!r}"))
        if not str(c.get("text", "")).strip():
            out.append(_issue("error", cid, "empty text"))
        out += _leak_and_size(cid, model_view(c))
        key = (c.get("task"), c.get("text"), c.get("attachment", ""))
        if key in seen_text:
            out.append(_issue("error", cid, "duplicate text for the same task"))
        seen_text.add(key)
    for task in ("scope", "injection"):
        golds = Counter(c["gold"] for c in cases if c.get("task") == task)
        for g in ("ALLOW", "BLOCK"):
            if golds[g] == 0:
                out.append(_issue("error", "-", f"task {task} has no {g} cases, so its metrics are meaningless"))
            elif golds[g] < 10:
                out.append(_issue("warning", "-", f"task {task} has only {golds[g]} {g} cases; intervals will be wide"))
    return out


def _leak_and_size(cid, view):
    out = []
    for field, limit in (("text", MAX_BRIEF), ("attachment", MAX_ATTACHMENT)):
        t = view[field]
        if len(t) > limit:
            out.append(_issue("error", cid, f"{field} is {len(t)} characters, over the API limit of {limit}"))
        if m := LABEL_TOKENS.search(t):
            out.append(_issue("error", cid, f"label token {m.group(0)!r} appears in the {field} the model sees"))
        if m := CASE_ID.search(t):
            out.append(_issue("error", cid, f"case-id-like token {m.group(0)!r} appears in the {field} the model sees"))
    return out


def report(issues: list[dict]) -> bool:
    """Prints issues. Returns True when the run may continue (no errors)."""
    errs = [i for i in issues if i["severity"] == "error"]
    for i in issues:
        print(f"  {i['severity'].upper():7} {i['case']}: {i['message']}")
    print(f"pre-flight checks: {len(errs)} error(s), {len(issues) - len(errs)} warning(s)")
    return not errs

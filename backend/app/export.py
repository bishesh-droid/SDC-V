"""Markdown export of a stored run. Built only from the stored, already-verified result."""
from __future__ import annotations

import csv
import io

_CSV_COLS = ["id", "created_at", "status", "mode", "summary", "reviewer", "reviewed_at"]


def _cell(v) -> str:
    return str(v if v is not None else "").replace("|", "\\|").replace("\n", " ")


def _table(head: list[str], rows: list[list]) -> list[str]:
    out = ["| " + " | ".join(head) + " |", "|" + "|".join("---" for _ in head) + "|"]
    out += ["| " + " | ".join(_cell(c) for c in r) + " |" for r in rows]
    return out + [""]


def report_markdown(run: dict) -> str:
    res = run["record"]["result"]
    rd = res.get("report")
    versions = run["record"].get("versions", {})
    L = [f"# SDC-V design report {run['id']}", "",
         f"- Created: {run['created_at']}",
         f"- Status: {res['status']} ({res['mode']} mode)",
         f"- Code edition: {versions.get('code_edition', '')}; rules fingerprint {versions.get('rules_fingerprint', '')}",
         f"- Narrative source: {res.get('narrative_source') or 'none'}; model: {res.get('llm_model') or 'none'}"]
    if run.get("reviewer"):
        L.append(f"- Review logged by: {run['reviewer']} at {run.get('reviewed_at')}"
                 + (f" ({run['review_note']})" if run.get("review_note") else "") + " (log entry, not a certification)")
    L += ["", f"**{res.get('message') or res['status']}**", ""]
    if rd:
        L += ["## Inputs", ""] + _table(["Item", "Value"], [[r["label"], r["value"]] for r in rd["inputs"]])
        if rd.get("unit_conversions"):
            L += ["Unit conversions applied:", ""] + [f"- {c}" for c in rd["unit_conversions"]] + [""]
        L += ["## Design", ""] + _table(["Item", "Value"], [[r["label"], r["value"]] for r in rd["design"]])
        order = {"FAIL": 0, "WARN": 1, "PASS": 2}
        checks = sorted(rd["checks"], key=lambda c: order[c["status"]])
        L += ["## Verifier checks", ""] + _table(
            ["Status", "Check", "Clause", "Value", "Limit"],
            [[c["status"], c["title"], c["clause"], c["value"], f"{c['op']} {c['limit']}"] for c in checks])
        if res.get("iterations"):
            L += ["## Section revision", ""] + _table(
                ["Step", "b x D (mm)", "Failed", "Action"],
                [[i["iteration"], f"{i['b']:.0f} x {i['D']:.0f}", ", ".join(i["failed"]) or "none", i["action"]]
                 for i in res["iterations"]])
    if res.get("narrative"):
        L += ["## Narrative", "", res["narrative"], ""]
    L += ["---", "", f"**{res['stamp']}**", ""]
    return "\n".join(L)


def _safe(v) -> str:
    s = "" if v is None else str(v)
    return "'" + s if s[:1] in ("=", "+", "-", "@") else s  # neutralise spreadsheet formula injection


def runs_csv(rows: list[dict]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(_CSV_COLS)
    for r in rows:
        w.writerow([_safe(r.get(c)) for c in _CSV_COLS])
    return buf.getvalue()

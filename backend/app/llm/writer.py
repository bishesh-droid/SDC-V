"""LLM report writer: narrates the verified result. Output is checked by the number-trace guardrail."""
from __future__ import annotations

import json

from ..guardrails.output import trace_numbers
from ..report import STAMP, ReportData, template_narrative
from .gemini import LLM, LLMError

WRITER_SYSTEM = f"""You write the narrative section of a structural design report from a JSON result produced by a deterministic calculator and verifier.

Rules:
1. Use ONLY numbers that appear verbatim in the provided JSON strings. Never compute, round differently, convert units or introduce any other number. If you want a number that is not in the JSON, describe it in words instead.
2. Cite the clause for every check you mention, exactly as written in the JSON.
3. Put all failed (FAIL) and warning (WARN) checks first, before passing checks. If none, say so.
4. List every assumption from the JSON under the heading "Assumptions".
5. Do not say the design is safe, adequate, approved or compliant; only report what each check found. Never recommend reducing any margin.
6. Use Markdown with these ## headings in order: Summary, Issues requiring attention, Checks passed, Assumptions, and Revision history (only if the log is non-empty). Use bullet points only, never numbered lists, and do not number headings.
7. Keep it concise (under 350 words).
8. End with exactly this line in bold: **{STAMP}**
"""


def write_report(llm: LLM, rd: ReportData, max_attempts: int = 3) -> tuple[str, str, list[dict]]:
    """Returns (narrative, source, events). source is 'llm' or 'template'."""
    payload = rd.model_dump()
    prompt = "Result JSON:\n" + json.dumps(payload, ensure_ascii=False, indent=1)
    events: list[dict] = []
    for attempt in range(1, max_attempts + 1):
        try:
            text = llm.generate(WRITER_SYSTEM, prompt, json_mode=False).strip()
        except LLMError as e:
            events.append({"type": "writer_llm_error", "attempt": attempt, "detail": str(e)[:200]})
            break
        bad = trace_numbers(text, payload)
        if STAMP not in text:
            bad = bad + ["<missing draft stamp>"]
        if not bad:
            return text, "llm", events
        events.append({"type": "number_trace_rejected", "attempt": attempt, "untraceable": bad})
        prompt = ("Result JSON:\n" + json.dumps(payload, ensure_ascii=False, indent=1)
                  + f"\n\nYour previous draft was rejected because these numbers/items are not in the JSON: {bad}. "
                    "Rewrite using only numbers copied verbatim from the JSON.")
    events.append({"type": "fallback_template"})
    return template_narrative(rd), "template", events

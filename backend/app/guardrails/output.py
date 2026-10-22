"""Output guardrail: every number in the narrative must trace to the verified result."""
from __future__ import annotations

import re
from typing import Any

_NUM = re.compile(r"(?<![\d.])\d+(?:\.\d+)?")
_LIST_MARKER = re.compile(r"^\s*(?:\d+[.)]\s+)", re.M)


def _norm(text: str) -> str:
    text = text.replace("²", "2").replace("³", "3")
    return re.sub(r"(?<=[A-Za-z/])([23])\b", "", text)   # mm2, m3 -> unit text, not a number


def numbers(text: str, *, strip_list_markers: bool = False) -> list[str]:
    if strip_list_markers:
        text = _LIST_MARKER.sub("", text)
    return _NUM.findall(_norm(text))


def _strings(obj: Any):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _strings(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from _strings(v)


def allowed_numbers(report_data: dict) -> set[str]:
    allowed: set[str] = set()
    for s in _strings(report_data):
        allowed.update(numbers(s))
    return allowed


def trace_numbers(narrative: str, report_data: dict) -> list[str]:
    """Return the numbers in the narrative that do NOT exist in the verified result (empty = accepted)."""
    allowed = allowed_numbers(report_data)
    bad = []
    for n in numbers(narrative, strip_list_markers=True):
        if n not in allowed and n not in bad:
            bad.append(n)
    return bad

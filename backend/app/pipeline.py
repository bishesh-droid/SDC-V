"""Orchestration: intake -> guardrails -> calculator -> verifier/reviser -> writer -> trace -> audit."""
from __future__ import annotations

import platform
import uuid
from typing import Literal

import pydantic
from pydantic import BaseModel, Field

from . import config
from .audit import AuditLog
from .guardrails.input import (FIELD_LABELS, NormaliseOutcome, Quantity, RawIntake, detect_injection,
                               normalise, numbers_in, redact, screen_scope)
from .is456 import tables as T
from .is456.calculator import design_beam
from .llm.gemini import LLM, LLMError
from .llm.intake import run_intake
from .llm.writer import write_report
from .report import STAMP, ReportData, build_report_data, template_narrative
from .reviser import revise
from .schemas import BeamInput, CheckResult, Design
from .sketch import section_svg
from .verifier import rules_fingerprint, run_rules

Status = Literal["designed", "needs_engineer", "needs_info", "rejected", "out_of_scope", "refused", "error"]


class Iteration(BaseModel):
    iteration: int
    b: float
    D: float
    failed: list[str]
    action: str


class RunResult(BaseModel):
    run_id: str
    status: Status
    mode: str
    message: str = ""
    question: str | None = None
    missing: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    out_of_scope: list[str] = Field(default_factory=list)
    conversions: list[str] = Field(default_factory=list)
    original_input: BeamInput | None = None
    final_input: BeamInput | None = None
    design: Design | None = None
    checks: list[CheckResult] = Field(default_factory=list)
    iterations: list[Iteration] = Field(default_factory=list)
    report: ReportData | None = None
    narrative: str | None = None
    narrative_source: str | None = None
    sketch_svg: str | None = None
    guardrail_events: list[dict] = Field(default_factory=list)
    llm_model: str | None = None
    stamp: str = STAMP


def tool_versions() -> dict:
    return {"app": config.APP_VERSION, "python": platform.python_version(), "pydantic": pydantic.VERSION,
            "code_edition": T.CODE_EDITION, "rules_fingerprint": rules_fingerprint()}


# ----------------------------------------------------------- core design loop
def design_with_verification(inp: BeamInput, max_iter: int = config.MAX_REVISER_ITERATIONS):
    """Calculator -> rules -> (reviser -> calculator ...). Returns (final_input, design, checks, iterations, status)."""
    cur = inp
    its: list[Iteration] = []
    for i in range(max_iter + 1):
        des = design_beam(cur)
        checks = run_rules(cur, des)
        errs = [c for c in checks if not c.passed and c.severity == "error"]
        failed = [c.rule_id for c in errs]
        if not errs:
            its.append(Iteration(iteration=i, b=cur.b_mm, D=cur.D_mm, failed=[], action="All error checks pass"))
            return cur, des, checks, its, "designed"
        if any(not c.revisable for c in errs):
            its.append(Iteration(iteration=i, b=cur.b_mm, D=cur.D_mm, failed=failed,
                                 action="Failure cannot be fixed by resizing; engineer input needed"))
            return cur, des, checks, its, "needs_engineer"
        if i == max_iter:
            its.append(Iteration(iteration=i, b=cur.b_mm, D=cur.D_mm, failed=failed,
                                 action=f"Reached the limit of {max_iter} revisions"))
            return cur, des, checks, its, "needs_engineer"
        new, desc = revise(cur)
        its.append(Iteration(iteration=i, b=cur.b_mm, D=cur.D_mm, failed=failed, action=desc))
        if new is None:
            return cur, des, checks, its, "needs_engineer"
        cur = new
    raise AssertionError("unreachable")


def _history_lines(its: list[Iteration]) -> list[str]:
    lines = []
    for it in its:
        if it.failed:
            lines.append(f"Section {it.b:.0f} x {it.D:.0f} mm failed {', '.join(it.failed)}. {it.action}.")
    return lines


# ----------------------------------------------------------------- pipeline
class Pipeline:
    def __init__(self, llm: LLM | None, audit: AuditLog | None = None):
        self.llm = llm
        self.audit = audit

    # -- helpers
    def _finish(self, res: RunResult, record_extra: dict | None = None) -> RunResult:
        if self.llm is not None and getattr(self.llm, "last_model", None):
            res.llm_model = self.llm.last_model
        if self.audit:
            summary = res.message or res.status
            if res.final_input:
                i = res.final_input
                summary = (f"{i.support.replace('_', ' ')} {i.span_m:g} m, M{i.fck}/Fe{i.fy}, "
                           f"{i.b_mm:.0f}x{i.D_mm:.0f} -> {res.status}")
            self.audit.save(res.run_id, res.status, res.mode, summary,
                            {"result": res.model_dump(mode="json"), "versions": tool_versions(),
                             "llm_model": res.llm_model, **(record_extra or {})})
        return res

    def _writer_llm(self):
        return self.llm if (self.llm is not None and getattr(self.llm, "available", True)) else None

    # -- structured mode (no LLM needed)
    def run_structured(self, raw: RawIntake) -> RunResult:
        run_id = uuid.uuid4().hex[:12]
        out = normalise(raw)
        return self._from_normalised(run_id, "structured", out, [], {"raw_input": raw.model_dump()})

    def _from_normalised(self, run_id: str, mode: str, out: NormaliseOutcome, events: list[dict],
                         extra: dict) -> RunResult:
        if out.out_of_scope:
            return self._finish(RunResult(run_id=run_id, status="out_of_scope", mode=mode,
                                          out_of_scope=out.out_of_scope, guardrail_events=events,
                                          message="Outside the supported scope: " + "; ".join(out.out_of_scope)), extra)
        if out.errors:
            return self._finish(RunResult(run_id=run_id, status="rejected", mode=mode, errors=out.errors,
                                          conversions=out.conversions, guardrail_events=events,
                                          message="Input rejected by the guardrails"), extra)
        if out.missing:
            q = _question(out.missing)
            return self._finish(RunResult(run_id=run_id, status="needs_info", mode=mode, missing=out.missing,
                                          question=q, message=q, conversions=out.conversions,
                                          guardrail_events=events), extra)
        assert out.beam is not None
        return self._design(run_id, mode, out.beam, out.conversions, events, extra)

    # -- design + report
    def _design(self, run_id: str, mode: str, beam: BeamInput, conversions: list[str], events: list[dict],
                extra: dict) -> RunResult:
        final, des, checks, its, status = design_with_verification(beam)
        history = _history_lines(its)
        rd = build_report_data(final, des, checks, status, history, conversions)
        llm = self._writer_llm()
        if llm is not None:
            narrative, source, wev = write_report(llm, rd, config.MAX_WRITER_ATTEMPTS)
            events = events + wev
        else:
            narrative, source = template_narrative(rd), "template"
            events = events + [{"type": "writer_skipped", "detail": "No LLM configured; deterministic template used"}]
        msg = ("Draft design produced; all error-level checks pass." if status == "designed"
               else "No passing design found automatically; this beam needs an engineer.")
        if final.b_mm != beam.b_mm or final.D_mm != beam.D_mm:
            msg += f" Section revised from {beam.b_mm:.0f} x {beam.D_mm:.0f} to {final.b_mm:.0f} x {final.D_mm:.0f} mm."
        return self._finish(RunResult(
            run_id=run_id, status=status, mode=mode, message=msg, conversions=conversions, original_input=beam,
            final_input=final, design=des, checks=checks, iterations=its, report=rd, narrative=narrative,
            narrative_source=source, sketch_svg=section_svg(final, des), guardrail_events=events), extra)

    # -- natural-language mode
    def run_chat(self, messages: list[dict], attachment: str = "") -> RunResult:
        run_id = uuid.uuid4().hex[:12]
        events: list[dict] = []
        user_text = "\n".join(m["text"] for m in messages if m.get("role") == "user")
        # the audit log keeps only redacted text; the attachment is never stored, only its length
        extra = {"messages": [{**m, "text": redact(m["text"])[0]} for m in messages],
                 "attachment_chars": len(attachment)}

        # 1. deterministic scope screen on the user's own words (never on the attachment)
        oos, unsafe = screen_scope(user_text)
        if unsafe:
            events.append({"type": "unsafe_request", "detail": unsafe})
            return self._finish(RunResult(
                run_id=run_id, status="refused", mode="chat", guardrail_events=events, out_of_scope=unsafe,
                message="I can't help with " + ", ".join(unsafe) + ". This tool only drafts designs for engineer review; "
                        "it cannot approve, certify or relax safety requirements."), extra)
        if oos:
            events.append({"type": "out_of_scope", "detail": oos})
            return self._finish(RunResult(
                run_id=run_id, status="out_of_scope", mode="chat", guardrail_events=events, out_of_scope=oos,
                message="Not supported yet: " + ", ".join(oos) + ". Supported: singly reinforced rectangular beams, "
                        "simply supported or cantilever, UDL, IS 456:2000."), extra)

        # 2. injection flags (logged; the attachment is only ever passed as data)
        for label, txt in (("brief", user_text), ("attachment", attachment)):
            hits = detect_injection(txt)
            if hits:
                events.append({"type": "injection_suspected", "where": label, "patterns": hits})

        if self.llm is None or not getattr(self.llm, "available", True):
            return self._finish(RunResult(
                run_id=run_id, status="error", mode="chat", guardrail_events=events,
                message="The Gemini API key is not configured, so natural-language intake is unavailable. "
                        "Set GEMINI_API_KEY in backend/.env or use the structured form."), extra)

        # 3. redact PII before leaving the machine
        transcript = []
        n_red = 0
        for m in messages:
            t, k = redact(m["text"])
            n_red += k
            transcript.append(("Engineer" if m.get("role") == "user" else "Tool asked") + ": " + t)
        att, k = redact(attachment)
        n_red += k
        if n_red:
            events.append({"type": "pii_redacted", "count": n_red})

        try:
            intake = run_intake(self.llm, "\n".join(transcript), att)
        except LLMError as e:
            events.append({"type": "intake_llm_error", "detail": str(e)[:300]})
            return self._finish(RunResult(run_id=run_id, status="error", mode="chat", guardrail_events=events,
                                          message=f"The language model could not be reached or returned unusable output ({str(e)[:160]})."), extra)
        extra["intake"] = intake.model_dump()

        if intake.intent == "unsafe_request":
            return self._finish(RunResult(run_id=run_id, status="refused", mode="chat", guardrail_events=events,
                                          message="I can't help with that request. This tool only drafts designs for engineer review."), extra)
        if intake.intent in ("out_of_scope", "not_a_beam_brief"):
            why = intake.out_of_scope_reason or "this is not a supported beam design brief"
            return self._finish(RunResult(run_id=run_id, status="out_of_scope", mode="chat", guardrail_events=events,
                                          out_of_scope=[why], message=f"Not supported: {why}. Supported: singly reinforced rectangular beams, simply supported or cantilever, UDL, IS 456:2000."), extra)

        # 4. grounding: every extracted number must appear in what the user/attachment wrote
        raw = intake.fields
        grounded_pool = numbers_in(user_text) | numbers_in(attachment)
        ungrounded = []
        data = raw.model_dump()
        for name in ("span", "b", "D", "cover", "dead_load", "live_load"):
            q = data.get(name)
            if q and float(q["value"]) not in grounded_pool:
                ungrounded.append(name)
                data[name] = None
        for name in ("fck", "fy"):
            if data.get(name) is not None:
                try:
                    v = float(str(data[name]).strip().lstrip("MmFfEe ").strip() or data[name])
                except ValueError:
                    v = None
                if v is None or v not in grounded_pool:
                    ungrounded.append(name)
                    data[name] = None
        if ungrounded:
            events.append({"type": "ungrounded_values_dropped", "fields": ungrounded})
        raw = RawIntake.model_validate(data)

        if intake.loads_are_factored:
            q = ("The loads you gave look factored. Please give the characteristic (unfactored) superimposed dead load "
                 "and imposed load in kN/m instead; the tool applies the 1.5 load factor itself.")
            return self._finish(RunResult(run_id=run_id, status="needs_info", mode="chat", question=q, message=q,
                                          missing=["dead_load", "live_load"], guardrail_events=events), extra)

        out = normalise(raw)
        return self._from_normalised(run_id, "chat", out, events, extra)


def _question(missing: list[str]) -> str:
    items = "\n".join(f"- {FIELD_LABELS[m]}" for m in missing)
    return ("I need these details before I can design the beam (I won't guess them):\n" + items +
            "\nPlease give them all in one reply.")

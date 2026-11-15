"""Orchestration: intake -> guardrails -> calculator -> verifier/reviser -> writer -> trace -> audit."""
from __future__ import annotations

import platform
import re
import time
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
from .llm.vision import LLMTranscriber
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


class TraceStep(BaseModel):
    """Wall-clock timing of one pipeline stage. Presentation only: never hashed, fingerprinted or compared."""
    stage: str
    origin: Literal["deterministic", "llm"]
    ms: float | None = None
    status: str = "ok"


class LLMAttempt(BaseModel):
    model: str
    outcome: str
    ms: int


class Tracer:
    def __init__(self):
        self.steps: list[TraceStep] = []

    def add(self, stage: str, origin: str, ms: float | None, status: str = "ok") -> None:
        for s in self.steps:  # a stage that runs more than once (e.g. calculator in the reviser loop) is summed
            if s.stage == stage and s.ms is not None and ms is not None:
                s.ms = round(s.ms + ms, 2)
                if status != "ok":
                    s.status = status
                return
        self.steps.append(TraceStep(stage=stage, origin=origin, ms=None if ms is None else round(ms, 2), status=status))


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
    image_text: str | None = None
    sketch_svg: str | None = None
    guardrail_events: list[dict] = Field(default_factory=list)
    llm_model: str | None = None
    stamp: str = STAMP
    trace: list[TraceStep] = Field(default_factory=list)
    llm_attempts: list[LLMAttempt] = Field(default_factory=list)


def tool_versions() -> dict:
    return {"app": config.APP_VERSION, "python": platform.python_version(), "pydantic": pydantic.VERSION,
            "code_edition": T.CODE_EDITION, "rules_fingerprint": rules_fingerprint()}


# ----------------------------------------------------------- core design loop
def design_with_verification(inp: BeamInput, max_iter: int = config.MAX_REVISER_ITERATIONS, tr: Tracer | None = None):
    """Calculator -> rules -> (reviser -> calculator ...). Returns (final_input, design, checks, iterations, status)."""
    cur = inp
    its: list[Iteration] = []
    for i in range(max_iter + 1):
        t0 = time.perf_counter()
        des = design_beam(cur)
        t1 = time.perf_counter()
        checks = run_rules(cur, des)
        if tr is not None:
            tr.add("Calculator", "deterministic", (t1 - t0) * 1000)
            tr.add("Verifier", "deterministic", (time.perf_counter() - t1) * 1000)
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
        t0 = time.perf_counter()
        new, desc = revise(cur)
        if tr is not None:
            tr.add("Reviser", "deterministic", (time.perf_counter() - t0) * 1000)
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

_MISSING_WORDS = re.compile(r"missing|detail|insufficient|incomplete|not (?:specified|provided|stated|enough)|no (?:span|info|data|dimension|value|number)|unspecified|unclear|vague", re.I)


def _is_missing_info_refusal(reason: str | None, brief: str) -> bool:
    """True when an out_of_scope / not_a_beam_brief verdict looks like "information is missing" rather than a real unsupported feature.

    Conditions: the text talks about a beam, and the model either gave no reason or a reason that only says details are missing.
    A reason naming a feature (T-beam, slab, Eurocode...) is never overridden."""
    if not re.search(r"\bbeams?\b|\bRCC\b|\bcantilever\b", brief, re.I):
        return False
    return not (reason or "").strip() or bool(_MISSING_WORDS.search(reason or ""))

class Pipeline:
    """llm is the Gemini-style client (narrative, and intake unless intake_llm is given).

    intake_llm   optional local text model that reads briefs instead of `llm` (fine-tuned Qwen, see training/)
    vision_mode  "gemini" or "local": snapshots are first transcribed to text by that model, then read by the intake model.
                 None keeps the single-stage behaviour: images go straight to the intake model.
    vision_llm   the local vision model when vision_mode is "local"
    """
    def __init__(self, llm: LLM | None, audit: AuditLog | None = None, *, intake_llm: LLM | None = None,
                 vision_mode: str | None = None, vision_llm: LLM | None = None):
        self.llm = llm
        self.audit = audit
        self.intake_llm, self.vision_mode, self.vision_llm = intake_llm, vision_mode, vision_llm
        self.tr = Tracer()  # one Pipeline serves one request (see with_model), reset at the start of each run
        self._mark: dict[int, int] = {}

    def with_model(self, model: str | None) -> "Pipeline":
        """A pipeline for one request whose model calls try `model` first (no effect without a model client)."""
        pick = getattr(self.llm, "for_model", None)
        return Pipeline(pick(model) if pick else self.llm, self.audit, intake_llm=self.intake_llm,
                        vision_mode=self.vision_mode, vision_llm=self.vision_llm)

    def _llms(self) -> list:
        seen, out = set(), []
        for m in (self.intake_llm, self.vision_llm, self.llm):   # intake first, narrative last: attempts read in pipeline order
            if m is not None and id(m) not in seen:
                seen.add(id(m)); out.append(m)
        return out

    def _start(self) -> None:
        """Called at the start of a run. Local models are shared between requests, so remember where their attempt lists were."""
        self.tr = Tracer()
        self._mark = {id(m): len(getattr(m, "attempts", None) or []) for m in self._llms()}

    def _intake_model(self):
        return self.intake_llm if self.intake_llm is not None else self.llm

    def _transcriber(self) -> LLMTranscriber | None:
        if self.vision_mode == "local" and self.vision_llm is not None:
            return LLMTranscriber(self.vision_llm)
        if self.vision_mode == "gemini" and self.llm is not None:
            return LLMTranscriber(self.llm)
        return None

    # -- helpers
    def _finish(self, res: RunResult, record_extra: dict | None = None) -> RunResult:
        tr = self.tr
        used = [m for m in self._llms() if getattr(m, "last_model", None) and len(getattr(m, "attempts", None) or []) > self._mark.get(id(m), 0)]
        if used:
            res.llm_model = ", ".join(dict.fromkeys(m.last_model for m in used))
        res.llm_attempts = [LLMAttempt(**a) for m in self._llms() for a in (getattr(m, "attempts", None) or [])[self._mark.get(id(m), 0):]]
        if tr is not None:
            if self.audit:
                tr.add("Audit", "deterministic", None)  # its own write cannot be timed inside the record it stores
            res.trace = tr.steps
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
        self._start()
        t0 = time.perf_counter()
        out = normalise(raw)
        self.tr.add("Guardrails", "deterministic", (time.perf_counter() - t0) * 1000)
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
        final, des, checks, its, status = design_with_verification(beam, tr=self.tr)
        history = _history_lines(its)
        rd = build_report_data(final, des, checks, status, history, conversions)
        llm = self._writer_llm()
        t0 = time.perf_counter()
        if llm is not None:
            narrative, source, wev = write_report(llm, rd, config.MAX_WRITER_ATTEMPTS)
            events = events + wev
            self.tr.add("Narrative", "llm" if source == "llm" else "deterministic",
                        (time.perf_counter() - t0) * 1000, "ok" if source == "llm" else "fallback")
        else:
            narrative, source = template_narrative(rd), "template"
            self.tr.add("Narrative", "deterministic", (time.perf_counter() - t0) * 1000, "fallback")
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
    def run_chat(self, messages: list[dict], attachment: str = "", images: list[dict] | None = None) -> RunResult:
        images = images or []
        run_id = uuid.uuid4().hex[:12]
        self._start()
        t_g = time.perf_counter()
        events: list[dict] = []
        user_text = "\n".join(m["text"] for m in messages if m.get("role") == "user")
        # the audit log keeps only redacted text; the attachment is never stored, only its length
        extra = {"messages": [{**m, "text": redact(m["text"])[0]} for m in messages],
                 "attachment_chars": len(attachment), "image_count": len(images)}

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

        intake_llm = self._intake_model()
        if intake_llm is None or not getattr(intake_llm, "available", True):
            local = self.intake_llm is not None
            return self._finish(RunResult(
                run_id=run_id, status="error", mode="chat", guardrail_events=events,
                message=("The local intake model is not available. Install torch and transformers (and peft for an adapter), "
                         "or set SDCV_INTAKE_BACKEND=gemini." if local else
                         "The Gemini API key is not configured, so natural-language intake is unavailable. "
                         "Set GEMINI_API_KEY in backend/.env or use the structured form.")), extra)

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

        self.tr.add("Guardrails", "deterministic", (time.perf_counter() - t_g) * 1000)

        # 3b. snapshots (two-stage mode): a vision model copies what it can read into text; the intake model then reads that text
        snap_text, reader = "", self._transcriber() if images else None
        if reader is not None:
            t0 = time.perf_counter()
            try:
                snap_text, k = redact(reader.transcribe(images))
                self.tr.add("Snapshot", "llm", (time.perf_counter() - t0) * 1000)
                events.append({"type": "snapshot_transcribed", "chars": len(snap_text), "model": reader.name})
                if k:
                    events.append({"type": "pii_redacted", "count": k, "where": "snapshot"})
            except LLMError as e:
                self.tr.add("Snapshot", "llm", (time.perf_counter() - t0) * 1000, "error")
                events.append({"type": "snapshot_llm_error", "detail": str(e)[:300]})
                return self._finish(RunResult(run_id=run_id, status="error", mode="chat", guardrail_events=events,
                                              message=f"The snapshot could not be read ({str(e)[:160]}). Describe the beam in words, or try again."), extra)

        t0 = time.perf_counter()
        try:
            intake = run_intake(intake_llm, "\n".join(transcript), att, None if reader is not None else images, image_text=snap_text)
            self.tr.add("Brief", "llm", (time.perf_counter() - t0) * 1000)
        except LLMError as e:
            self.tr.add("Brief", "llm", (time.perf_counter() - t0) * 1000, "error")
            events.append({"type": "intake_llm_error", "detail": str(e)[:300]})
            return self._finish(RunResult(run_id=run_id, status="error", mode="chat", guardrail_events=events,
                                          message=f"The language model could not be reached or returned unusable output ({str(e)[:160]})."), extra)
        extra["intake"] = intake.model_dump()
        image_text = (intake.image_text or "").strip()[:4000] if images else ""
        if images:
            events.append({"type": "images_read", "count": len(images), "chars": len(image_text)})
            hits = detect_injection(image_text)
            if hits:
                events.append({"type": "injection_suspected", "where": "image", "patterns": hits})

        if intake.intent == "unsafe_request":
            return self._finish(RunResult(run_id=run_id, status="refused", mode="chat", guardrail_events=events,
                                          message="I can't help with that request. This tool only drafts designs for engineer review."), extra)
        if intake.intent in ("out_of_scope", "not_a_beam_brief") and _is_missing_info_refusal(intake.out_of_scope_reason, "\n".join(transcript)):
            # A model must not answer "not supported" because values are missing: the rule-based scope screen above already found
            # no unsupported feature, so ask for the details instead.
            events.append({"type": "intake_intent_overridden", "detail": f"model said {intake.intent} ({intake.out_of_scope_reason!r}) but the brief is a beam request with no unsupported feature"})
            intake.intent = "design"
        if intake.intent in ("out_of_scope", "not_a_beam_brief"):
            why = intake.out_of_scope_reason or "this is not a supported beam design brief"
            return self._finish(RunResult(run_id=run_id, status="out_of_scope", mode="chat", guardrail_events=events,
                                          out_of_scope=[why], message=f"Not supported: {why}. Supported: singly reinforced rectangular beams, simply supported or cantilever, UDL, IS 456:2000."), extra)

        # 4. grounding: every extracted number must appear in what the user/attachment wrote
        t_g = time.perf_counter()
        raw = intake.fields
        grounded_pool = numbers_in(user_text) | numbers_in(attachment) | numbers_in(image_text)
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
        self.tr.add("Guardrails", "deterministic", (time.perf_counter() - t_g) * 1000)
        res = self._from_normalised(run_id, "chat", out, events, extra)
        if image_text:
            res.image_text = image_text
        return res


def _question(missing: list[str]) -> str:
    items = "\n".join(f"- {FIELD_LABELS[m]}" for m in missing)
    return ("I need these details before I can design the beam (I won't guess them):\n" + items +
            "\nPlease give them all in one reply.")

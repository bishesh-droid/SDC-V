"""Minimal Gemini REST client: model fallback, retries, a total time budget and per-model error reporting."""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Protocol

import httpx

from .. import config

API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
LIST_API = "https://generativelanguage.googleapis.com/v1beta/models?pageSize=200"
log = logging.getLogger("sdcv.llm")


class LLMError(RuntimeError):
    pass


class LLM(Protocol):
    name: str

    def generate(self, system: str, user: str, *, json_mode: bool = False, images: list[dict] | None = None) -> str: ...


class GeminiClient:
    def __init__(self, api_key: str | None = None, models: list[str] | None = None,
                 timeout: float | None = None, budget: float | None = None):
        self.api_key = api_key or config.gemini_api_key()
        self.models = models or config.gemini_models()
        self.timeout = timeout if timeout is not None else config.llm_timeout_s()
        self.budget = budget if budget is not None else config.llm_budget_s()
        self.last_model: str | None = None
        self.last_errors: dict[str, str] = {}
        self.attempts: list[dict] = []  # [{model, outcome, ms}] for every upstream call made by this client

    def for_model(self, model: str | None) -> "GeminiClient":
        """A per-request client that tries `model` first and falls back to the other configured models."""
        order = ([model] if model else []) + [m for m in self.models if m != model]
        return GeminiClient(self.api_key, order, self.timeout, self.budget)

    @property
    def name(self) -> str:
        return self.last_model or (self.models[0] if self.models else "gemini")

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def generate(self, system: str, user: str, *, json_mode: bool = False, images: list[dict] | None = None) -> str:
        """`images` is a list of {"mime": "image/png", "data": <base64>} sent as inline parts after the text."""
        if not self.api_key:
            raise LLMError("GEMINI_API_KEY is not set")
        parts = [{"text": user}] + [{"inlineData": {"mimeType": i["mime"], "data": i["data"]}} for i in images or []]
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {"temperature": 0, "maxOutputTokens": 8192,
                                 **({"responseMimeType": "application/json"} if json_mode else {})},
        }
        deadline = time.monotonic() + self.budget
        errors: dict[str, str] = {}
        self.last_errors = errors
        for model in self.models:
            for attempt in range(2):
                remaining = deadline - time.monotonic()
                if remaining < 1.0:
                    errors.setdefault("budget", f"time budget of {self.budget:g}s exhausted")
                    return self._fail(errors)
                t0 = time.monotonic()
                try:
                    r = httpx.post(API.format(model=model), json=body, timeout=min(self.timeout, remaining),
                                   headers={"x-goog-api-key": self.api_key, "Content-Type": "application/json"})
                except httpx.TimeoutException:
                    errors[model] = f"timed out after {time.monotonic() - t0:.0f}s"
                    self._note(model, "timeout", t0)
                    break  # a model that hangs is skipped, not retried
                except httpx.HTTPError as e:
                    errors[model] = f"network error {type(e).__name__}"
                    self._note(model, "network_error", t0)
                    time.sleep(min(1.0, max(0.0, deadline - time.monotonic())))
                    continue
                if r.status_code == 200:
                    text = _extract_text(r.json())
                    if text:
                        self.last_model = model
                        self._note(model, "ok", t0)
                        log.info("llm ok model=%s ms=%d", model, (time.monotonic() - t0) * 1000)
                        return text
                    errors[model] = "empty response"
                    self._note(model, "unusable_output", t0)
                    break
                errors[model] = f"HTTP {r.status_code} {_api_message(r)}"
                self._note(model, f"http_{r.status_code}", t0)
                if r.status_code in (429, 500, 503) and attempt == 0:
                    time.sleep(min(2.0, max(0.0, deadline - time.monotonic())))
                    continue
                break  # try next model (404 unknown model, 400, quota, ...)
        return self._fail(errors)

    def _note(self, model: str, outcome: str, t0: float) -> None:
        self.attempts.append({"model": model, "outcome": outcome, "ms": int((time.monotonic() - t0) * 1000)})
        del self.attempts[:-60]  # bounded: the shared client also serves health probes

    def _fail(self, errors: dict[str, str]):
        log.warning("llm failed: %s", errors)
        raise LLMError("; ".join(f"{m}: {e}" for m, e in errors.items()) or "no models configured")

    # ---- diagnostics (used by /api/health?deep=1)
    def probe(self) -> dict:
        """One tiny real call. Never raises."""
        if not self.api_key:
            return {"ok": False, "error": "GEMINI_API_KEY is not set"}
        t0 = time.monotonic()
        saved = self.budget
        self.budget = min(self.budget, 20.0)
        try:
            self.generate("Reply with the single word OK.", "OK")
            return {"ok": True, "model": self.last_model, "latency_ms": int((time.monotonic() - t0) * 1000),
                    "skipped": {m: e for m, e in self.last_errors.items()}}
        except LLMError as e:
            return {"ok": False, "error": str(e)[:400], "latency_ms": int((time.monotonic() - t0) * 1000)}
        finally:
            self.budget = saved

    def remote_models(self) -> list[str] | None:
        """Model IDs the API currently offers for generateContent, or None if the lookup failed."""
        if not self.api_key:
            return None
        try:
            r = httpx.get(LIST_API, headers={"x-goog-api-key": self.api_key}, timeout=10.0)
            if r.status_code != 200:
                return None
            return [m["name"].removeprefix("models/") for m in r.json().get("models", [])
                    if "generateContent" in m.get("supportedGenerationMethods", [])]
        except (httpx.HTTPError, ValueError):
            return None


def _api_message(r: httpx.Response) -> str:
    try:
        return str(r.json()["error"]["message"])[:160]
    except (ValueError, KeyError, TypeError):
        return r.text[:160]


def _extract_text(payload: dict) -> str:
    try:
        parts = payload["candidates"][0]["content"]["parts"]
    except (KeyError, IndexError, TypeError):
        return ""
    return "".join(p.get("text", "") for p in parts if not p.get("thought"))


def parse_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            return json.loads(m.group(0))
        raise LLMError("model did not return valid JSON")

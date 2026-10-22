"""Minimal Gemini REST client (free-tier friendly, model fallback, retries)."""
from __future__ import annotations

import json
import re
import time
from typing import Protocol

import httpx

from .. import config

API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


class LLMError(RuntimeError):
    pass


class LLM(Protocol):
    name: str

    def generate(self, system: str, user: str, *, json_mode: bool = False) -> str: ...


class GeminiClient:
    def __init__(self, api_key: str | None = None, models: list[str] | None = None, timeout: float = 60.0):
        self.api_key = api_key or config.gemini_api_key()
        self.models = models or config.gemini_models()
        self.timeout = timeout
        self.last_model: str | None = None

    @property
    def name(self) -> str:
        return self.last_model or (self.models[0] if self.models else "gemini")

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def generate(self, system: str, user: str, *, json_mode: bool = False) -> str:
        if not self.api_key:
            raise LLMError("GEMINI_API_KEY is not set")
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {"temperature": 0, "maxOutputTokens": 8192,
                                 **({"responseMimeType": "application/json"} if json_mode else {})},
        }
        last_err = "no models configured"
        for model in self.models:
            for attempt in range(2):
                try:
                    r = httpx.post(API.format(model=model), json=body, timeout=self.timeout,
                                   headers={"x-goog-api-key": self.api_key, "Content-Type": "application/json"})
                except httpx.HTTPError as e:
                    last_err = f"{model}: network error {e}"
                    time.sleep(1.0)
                    continue
                if r.status_code == 200:
                    text = _extract_text(r.json())
                    if text:
                        self.last_model = model
                        return text
                    last_err = f"{model}: empty response"
                    break
                last_err = f"{model}: HTTP {r.status_code} {r.text[:200]}"
                if r.status_code in (429, 500, 503) and attempt == 0:
                    time.sleep(2.0)
                    continue
                break  # try next model (404 unknown model, 400, quota, ...)
        raise LLMError(last_err)


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

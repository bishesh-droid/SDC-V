"""FastAPI app: JSON API plus the static frontend."""
from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import config
from .audit import AuditLog
from .guardrails.input import RawIntake
from .is456 import tables as T
from .llm.gemini import GeminiClient
from .pipeline import Pipeline, RunResult, tool_versions
from .verifier import RULE_META

app = FastAPI(title="SDC-V: Structural Design Copilot with Deterministic Verifier", version=config.APP_VERSION)
audit = AuditLog()
llm = GeminiClient()
pipeline = Pipeline(llm, audit)


class ChatMessage(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    text: str = Field(max_length=8000)


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1, max_length=20)
    attachment_text: str = Field(default="", max_length=20000)


class ReviewRequest(BaseModel):
    reviewer: str = Field(min_length=2, max_length=120)
    note: str = Field(default="", max_length=2000)


@app.get("/api/health")
def health():
    return {"ok": True, "llm_configured": llm.available, "models": llm.models, "code_edition": T.CODE_EDITION,
            "versions": tool_versions()}


@app.get("/api/rules")
def rules():
    return [{"rule_id": k, **v} for k, v in RULE_META.items()]


@app.post("/api/design", response_model=RunResult)
def design(raw: RawIntake):
    return pipeline.run_structured(raw)


@app.post("/api/chat", response_model=RunResult)
def chat(req: ChatRequest):
    return pipeline.run_chat([m.model_dump() for m in req.messages], req.attachment_text)


@app.get("/api/runs")
def runs(limit: int = 50):
    return audit.list(min(max(limit, 1), 200))


@app.get("/api/runs/{run_id}")
def run(run_id: str):
    r = audit.get(run_id)
    if not r:
        raise HTTPException(404, "run not found")
    return r


@app.post("/api/runs/{run_id}/review")
def review(run_id: str, req: ReviewRequest):
    if not audit.review(run_id, req.reviewer, req.note):
        raise HTTPException(404, "run not found")
    return {"ok": True}


if config.FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=config.FRONTEND_DIR), name="static")

    @app.get("/")
    def index():
        return FileResponse(config.FRONTEND_DIR / "index.html")

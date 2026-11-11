"""FastAPI app: JSON API plus the static frontend."""
from __future__ import annotations

import base64
import binascii
import logging
import threading
import time

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field, model_validator

from . import config
from .audit import AuditLog
from .explore import explore
from .export import report_markdown, runs_csv
from .guardrails.input import RawIntake
from .is456 import tables as T
from .kb import kb_payload
from .system_model import system_payload
from .llm.gemini import GeminiClient
from .pipeline import Pipeline, RunResult, tool_versions
from .scope import scope
from .security import SECURITY_HEADERS, RateLimiter, client_ip, token_ok
from .verifier import RULE_META

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("sdcv.http")

app = FastAPI(title="SDC-V: Structural Design Copilot with Deterministic Verifier", version=config.APP_VERSION)
audit = AuditLog()
llm = GeminiClient()
pipeline = Pipeline(llm, audit)
limiter = RateLimiter()

LIMITED = {"/api/chat", "/api/design", "/api/explore"}
MODEL_PATTERN = "^(" + "|".join(config.gemini_models()) + ")$"
STATUSES = "designed|needs_engineer|needs_info|rejected|out_of_scope|refused|error"


class ChatMessage(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    text: str = Field(max_length=8000)


_IMAGE_MAGIC = {"image/png": (b"\x89PNG",), "image/jpeg": (b"\xff\xd8\xff",), "image/webp": (b"RIFF",)}
MAX_IMAGE_B64 = 5_000_000  # ~3.7 MB of image; the browser downsizes before upload


class ChatImage(BaseModel):
    mime: str = Field(pattern="^image/(png|jpeg|webp)$")
    data: str = Field(min_length=16, max_length=MAX_IMAGE_B64)

    @model_validator(mode="after")
    def genuine(self):
        try:
            head = base64.b64decode(self.data[:16] + "=" * (-len(self.data[:16]) % 4))
        except (ValueError, binascii.Error):
            raise ValueError("image data is not valid base64")
        if not head.startswith(_IMAGE_MAGIC[self.mime]):
            raise ValueError("image content does not match its declared type")
        return self


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1, max_length=20)
    attachment_text: str = Field(default="", max_length=20000)
    images: list[ChatImage] = Field(default_factory=list, max_length=3)


class ReviewRequest(BaseModel):
    reviewer: str = Field(min_length=2, max_length=120)
    note: str = Field(default="", max_length=2000)


# ------------------------------------------------------------------ middleware
@app.middleware("http")
async def guard(request: Request, call_next):
    t0 = time.monotonic()
    path, ip = request.url.path, client_ip(request)
    resp: Response | None = None
    if path.startswith("/api/") and path != "/api/health" and (token := config.api_token()):
        if not token_ok(request, token):
            resp = JSONResponse({"detail": "missing or invalid API token"}, status_code=401,
                                headers={"WWW-Authenticate": "Bearer"})
    if resp is None and request.method == "POST" and path in LIMITED:
        wait = limiter.check(f"{ip}|{path}", config.rate_limit_per_min())
        if wait:
            resp = JSONResponse({"detail": f"rate limit exceeded; retry in {wait:.0f}s"}, status_code=429,
                                headers={"Retry-After": str(int(wait))})
    if resp is None:
        resp = await call_next(request)
    for k, v in SECURITY_HEADERS.items():
        resp.headers.setdefault(k, v)
    if path.startswith("/api/"):
        resp.headers.setdefault("Cache-Control", "no-store")
        log.info("%s %s %d %dms ip=%s", request.method, path, resp.status_code, (time.monotonic() - t0) * 1000, ip)
    return resp


# ---------------------------------------------------------------------- health
_probe_cache: dict = {"at": 0.0, "value": None}
_probe_lock = threading.Lock()


def _deep_status(model: str | None = None) -> dict:
    """Real model call plus model-list check, cached for 60 s per model so health polling cannot burn quota."""
    with _probe_lock:
        if _probe_cache["value"] and _probe_cache.get("model") == model and time.monotonic() - _probe_cache["at"] < 60:
            return {**_probe_cache["value"], "cached": True}
        probe = (llm.for_model(model) if model else llm).probe()
        remote = llm.remote_models()
        value = {"probe": probe, "unavailable_models": ([m for m in llm.models if m not in remote] if remote else None)}
        _probe_cache.update(at=time.monotonic(), value=value, model=model)
        return {**value, "cached": False}


@app.get("/api/health")
def health(deep: bool = False, model: str | None = Query(None, pattern=MODEL_PATTERN)):
    out = {"ok": True, "llm_configured": llm.available, "models": llm.models, "model_options": config.MODEL_OPTIONS, "default_model": config.DEFAULT_MODEL,
           "code_edition": T.CODE_EDITION,
           "auth_required": bool(config.api_token()), "rate_limit_per_min": config.rate_limit_per_min(),
           "versions": tool_versions(), "db_ok": audit.ping()}
    if deep:
        out["llm"] = _deep_status(model)
    return out


# ------------------------------------------------------------------ reference
@app.get("/api/rules")
def rules():
    return [{"rule_id": k, **v} for k, v in RULE_META.items()]


@app.get("/api/scope")
def get_scope():
    return scope()


@app.get("/api/kb")
def knowledge_base():
    return kb_payload()


@app.get("/api/system")
def system_model():
    return system_payload()


# ----------------------------------------------------------------------- design
@app.post("/api/design", response_model=RunResult)
def design(raw: RawIntake, model: str | None = Query(None, pattern=MODEL_PATTERN)):
    return pipeline.with_model(model).run_structured(raw)


@app.post("/api/chat", response_model=RunResult)
def chat(req: ChatRequest, model: str | None = Query(None, pattern=MODEL_PATTERN)):
    return pipeline.with_model(model).run_chat([m.model_dump() for m in req.messages], req.attachment_text,
                             [i.model_dump() for i in req.images])


@app.post("/api/explore")
def explore_sections(raw: RawIntake):
    return explore(raw)


# ---------------------------------------------------------------------- history
@app.get("/api/runs")
def runs(response: Response, limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
         status: str | None = Query(None, pattern=f"^({STATUSES})$"), mode: str | None = Query(None, pattern="^(chat|structured)$"),
         q: str | None = Query(None, max_length=80), reviewed: bool | None = None):
    rows, total = audit.search(limit, offset, status, mode, q, reviewed)
    response.headers["X-Total-Count"] = str(total)
    return rows


@app.get("/api/runs.csv")
def runs_export(status: str | None = Query(None, pattern=f"^({STATUSES})$"), mode: str | None = Query(None, pattern="^(chat|structured)$"),
                q: str | None = Query(None, max_length=80), reviewed: bool | None = None):
    rows, _ = audit.search(5000, 0, status, mode, q, reviewed)
    return PlainTextResponse(runs_csv(rows), media_type="text/csv",
                             headers={"Content-Disposition": 'attachment; filename="sdcv-runs.csv"'})


@app.get("/api/stats")
def stats():
    return audit.stats()


@app.get("/api/runs/{run_id}")
def run(run_id: str):
    r = audit.get(run_id)
    if not r:
        raise HTTPException(404, "run not found")
    return r


@app.get("/api/runs/{run_id}/report.md")
def run_report(run_id: str):
    r = audit.get(run_id)
    if not r:
        raise HTTPException(404, "run not found")
    return PlainTextResponse(report_markdown(r), media_type="text/markdown",
                             headers={"Content-Disposition": f'attachment; filename="sdcv-{run_id}.md"'})


@app.post("/api/runs/{run_id}/review")
def review(run_id: str, req: ReviewRequest):
    if not audit.review(run_id, req.reviewer.strip(), req.note.strip()):
        raise HTTPException(404, "run not found")
    return {"ok": True}


if config.FRONTEND_DIR.exists():
    # explicit allowlist (flat filenames only): package.json and server.mjs live in the same folder
    ASSETS = {n: ("text/css" if n.endswith(".css") else "text/javascript") for n in (
        "app.js",
        "core.js",
        "fmt.js",
        "ui.js",
        "beam.js",
        "chrome.js",
        "result.js",
        "design.js",
        "explore.js",
        "home.js",
        "chat.js",
        "kb.js",
        "system.js",
        "history.js",
        "scope.js",
        "fixture.js",
        "kbcharts.js",
        "theme-init.js",
        "styles.css",
        "theme.css",
    )}

    @app.get("/static/{name}")
    def static_asset(name: str):
        if name not in ASSETS:  # whitelist: package.json and server.mjs live in the same folder
            raise HTTPException(404, "not found")
        return FileResponse(config.FRONTEND_DIR / name, media_type=ASSETS[name], headers={"Cache-Control": "no-cache"})

    @app.get("/")
    def index():
        return FileResponse(config.FRONTEND_DIR / "index.html")

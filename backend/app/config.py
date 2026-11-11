"""Runtime configuration. Reads backend/.env, then the repository-root .env, then the environment.

The Gemini API key is the only model-related setting read from the environment; models are chosen in the web UI."""
from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("SDCV_DATA_DIR") or BASE_DIR / "data")  # override for tests / throwaway databases
FRONTEND_DIR = BASE_DIR.parent / "frontend"
APP_VERSION = "0.2.0"


def _load_dotenv() -> None:
    # backend/.env wins over the repository-root .env; real environment variables win over both
    for env in (BASE_DIR / ".env", BASE_DIR.parent / ".env"):
        if not env.exists():
            continue
        for line in env.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_dotenv()


def _float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


def gemini_api_key() -> str:
    return os.environ.get("GEMINI_API_KEY", "").strip()


# Models offered in the web UI. Only the API key comes from the environment; the model is chosen per request.
# The first entry is the default. Tested against the live API with plain and JSON-mode calls on 11 Nov 2026.
# Gemini Pro models (3.1 Pro, Pro-latest) returned 429 quota errors on the free key and 2.5 Pro/Flash return 404 for new users,
# so they are left out. Gemma 4 was unreliable in the same test (500/503, and it printed its reasoning instead of clean JSON).
MODEL_OPTIONS = [
    {"id": "gemini-3.5-flash-lite", "label": "Gemini 3.5 Flash-Lite", "note": "Fastest, good for most briefs (default)"},
    {"id": "gemini-3.5-flash", "label": "Gemini 3.5 Flash", "note": "Balanced speed and quality"},
    {"id": "gemini-3.6-flash", "label": "Gemini 3.6 Flash", "note": "Newer Flash, stronger, slightly slower"},
    {"id": "gemini-3.8-flash", "label": "Gemini 3.8 Flash", "note": "Latest Flash; often busy, falls back if it is"},
    {"id": "gemini-3-flash-preview", "label": "Gemini 3 Flash (preview)", "note": "Fast preview release"},
]
DEFAULT_MODEL = MODEL_OPTIONS[0]["id"]


def gemini_models() -> list[str]:
    return [m["id"] for m in MODEL_OPTIONS]


def llm_timeout_s() -> float:
    """Per-request timeout for one Gemini call."""
    return _float("LLM_TIMEOUT_S", 25.0)


def llm_budget_s() -> float:
    """Total wall-clock budget for one generate() call across every model and retry."""
    return _float("LLM_BUDGET_S", 60.0)


def api_token() -> str:
    """If set, every /api route except /api/health requires this token."""
    return os.environ.get("SDCV_API_TOKEN", "").strip()


def rate_limit_per_min() -> int:
    """Requests per minute per client for the design endpoints; 0 disables the limit."""
    return int(_float("RATE_LIMIT_PER_MIN", 30))


MAX_REVISER_ITERATIONS = 8
MAX_WRITER_ATTEMPTS = 3  # first try + 2 regenerations, then fallback template

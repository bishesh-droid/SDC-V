"""Runtime configuration. Reads backend/.env, then the repository-root .env, then the environment."""
from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
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


def gemini_models() -> list[str]:
    raw = os.environ.get("GEMINI_MODELS", "gemini-3.5-flash,gemini-3.5-flash-lite,gemini-3.1-flash-lite")
    return [m.strip() for m in raw.split(",") if m.strip()]


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

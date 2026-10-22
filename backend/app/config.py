"""Runtime configuration. Reads backend/.env (if present) then the environment."""
from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
FRONTEND_DIR = BASE_DIR.parent / "frontend"
APP_VERSION = "0.1.0"


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


def gemini_api_key() -> str:
    return os.environ.get("GEMINI_API_KEY", "").strip()


def gemini_models() -> list[str]:
    raw = os.environ.get("GEMINI_MODELS", "gemini-3.5-flash,gemini-3.5-flash-lite,gemini-3.1-flash-lite")
    return [m.strip() for m in raw.split(",") if m.strip()]


MAX_REVISER_ITERATIONS = 8
MAX_WRITER_ATTEMPTS = 3  # first try + 2 regenerations, then fallback template

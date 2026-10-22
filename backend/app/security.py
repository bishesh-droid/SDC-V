"""Request-level controls: client IP, sliding-window rate limit, optional bearer token, security headers."""
from __future__ import annotations

import hmac
import threading
import time
from collections import defaultdict, deque

from fastapi import Request

LOOPBACK = {"127.0.0.1", "::1", "localhost"}
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Content-Security-Policy": ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
                                "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'"),
}


def client_ip(request: Request) -> str:
    """The socket peer, or the first X-Forwarded-For entry when the peer is a local reverse proxy."""
    peer = request.client.host if request.client else "unknown"
    if peer in LOOPBACK:
        xff = request.headers.get("x-forwarded-for", "")
        if xff:
            return xff.split(",")[0].strip() or peer
    return peer


class RateLimiter:
    def __init__(self, window_s: float = 60.0):
        self.window = window_s
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str, limit: int) -> float:
        """Returns 0 if allowed, otherwise the seconds until the oldest hit leaves the window."""
        if limit <= 0:
            return 0.0
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            while q and now - q[0] >= self.window:
                q.popleft()
            if len(q) >= limit:
                return max(1.0, self.window - (now - q[0]))
            q.append(now)
            if len(self._hits) > 5000:  # bound memory: drop idle keys
                for k in [k for k, v in self._hits.items() if not v or now - v[-1] >= self.window]:
                    del self._hits[k]
            return 0.0


def token_ok(request: Request, expected: str) -> bool:
    auth = request.headers.get("authorization", "")
    given = auth[7:].strip() if auth.lower().startswith("bearer ") else request.headers.get("x-api-key", "").strip()
    return bool(given) and hmac.compare_digest(given.encode(), expected.encode())

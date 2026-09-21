"""
In-memory sliding-window rate limiter.

Designed for the HPQMS single-worker deployment. Storage is a plain
dict, so it does NOT survive process restarts and is NOT shared across
multiple uvicorn workers or hosts. When HPQMS moves to multi-worker or
multi-node operation, replace the `_hits` dict with a Redis-backed
store; the public interface (get_limiter / check) is designed so that
swap is contained to this file.

Usage (route-level dependency, applied next to existing dependencies):

    @router.post("/login", dependencies=[Depends(rate_limit_login)])
    async def login(...): ...
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Callable, Deque, Dict, Tuple

from fastapi import HTTPException, Request, status

from app.core.config import settings


def _client_ip(request: Request) -> str:
    """
    Best-effort client IP extraction.

    Behind a reverse proxy, X-Forwarded-For carries the original
    client; otherwise fall back to the socket peer. For the pilot
    (single LAN, optional single proxy hop) first-hop extraction is
    sufficient and avoids trusting spoofable header chains.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client is not None:
        return request.client.host
    return "unknown"


class SlidingWindowLimiter:
    """
    Sliding-window counter keyed by (scope, client_ip).

    Keeps at most `limit` timestamps per key inside `window_seconds`;
    requests beyond the limit raise HTTP 429 with a Retry-After header.
    """

    def __init__(self, scope: str, limit: int, window_seconds: int):
        self.scope = scope
        self.limit = limit
        self.window_seconds = window_seconds
        # key -> deque of monotonic timestamps of accepted requests
        self._hits: Dict[Tuple[str, str], Deque[float]] = defaultdict(deque)

    def check(self, request: Request) -> None:
        """
        Record this request and raise HTTPException(429) when the
        client has exceeded the limit inside the current window.
        """
        if not settings.RATE_LIMIT_ENABLED:
            return

        key = (self.scope, _client_ip(request))
        now = time.monotonic()
        window_start = now - self.window_seconds

        hits = self._hits[key]

        # Evict timestamps that fell out of the window.
        while hits and hits[0] <= window_start:
            hits.popleft()

        if len(hits) >= self.limit:
            retry_after = max(1, int(self.window_seconds - (now - hits[0])))
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests. Please try again later.",
                headers={"Retry-After": str(retry_after)},
            )

        hits.append(now)

        # Opportunistic cleanup so the dict cannot grow unbounded.
        if len(self._hits) > 10_000:
            self._prune(now)

    def _prune(self, now: float) -> None:
        window_start = now - self.window_seconds
        dead_keys = [
            key
            for key, hits in self._hits.items()
            if not hits or hits[-1] <= window_start
        ]
        for key in dead_keys:
            del self._hits[key]


# Shared limiters. Tune limits here, not at call sites.

# Brute-force resistance for credential endpoints: 5 attempts/minute/IP.
rate_limit_auth = SlidingWindowLimiter("auth", limit=5, window_seconds=60)

# Kiosks are legitimate automated clients, but a single device should
# still not hammer check-in: 30 requests/minute/IP.
rate_limit_kiosk = SlidingWindowLimiter("kiosk", limit=30, window_seconds=60)


def rate_limit_auth_dependency(request: Request) -> None:
    """FastAPI dependency wrapping the auth limiter."""
    rate_limit_auth.check(request)


def rate_limit_kiosk_dependency(request: Request) -> None:
    """FastAPI dependency wrapping the kiosk limiter."""
    rate_limit_kiosk.check(request)


def reset_all_limiters() -> None:
    """
    Clear all limiter state. Intended for test teardown/fixtures so
    tests are isolated from each other's request counts.
    """
    rate_limit_auth._hits.clear()
    rate_limit_kiosk._hits.clear()

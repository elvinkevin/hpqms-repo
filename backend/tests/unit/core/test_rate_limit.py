"""
Tests for the in-memory sliding-window rate limiter
(backend/app/core/rate_limit.py).

Covers:
 1. Requests within the limit pass through.
 2. Exceeding the limit returns 429 with a Retry-After header.
 3. The window slides — after it expires, requests are allowed again.
 4. The client-IP extractor handles X-Forwarded-For and missing clients.
 5. RATE_LIMIT_ENABLED=False disables enforcement entirely.
 6. The login/refresh/kiosk routes are wired to the limiter.
"""

from unittest.mock import patch

import pytest
from fastapi import HTTPException, Request

from app.core import rate_limit as rl
from app.core.rate_limit import SlidingWindowLimiter, _client_ip, reset_all_limiters


# ============================================================================
# Helpers
# ============================================================================


def make_request(x_forwarded_for=None, client_host="10.0.0.1") -> Request:
    """Build a minimal fake Request for _client_ip / limiter.check."""
    scope = {
        "type": "http",
        "client": (client_host, 12345),
        "headers": (
            [(b"x-forwarded-for", x_forwarded_for.encode())]
            if x_forwarded_for
            else []
        ),
    }
    return Request(scope=scope)


@pytest.fixture(autouse=True)
def isolated_limiter_state():
    """Reset shared limiter state around every test."""
    reset_all_limiters()
    yield
    reset_all_limiters()


# ============================================================================
# 1. Within-limit behaviour
# ============================================================================


def test_requests_within_limit_pass():
    limiter = SlidingWindowLimiter("test", limit=3, window_seconds=60)
    request = make_request()

    for _ in range(3):
        limiter.check(request)  # must not raise


def test_request_at_limit_raises_429_with_retry_after():
    limiter = SlidingWindowLimiter("test", limit=3, window_seconds=60)
    request = make_request()

    for _ in range(3):
        limiter.check(request)

    with pytest.raises(HTTPException) as exc_info:
        limiter.check(request)

    assert exc_info.value.status_code == 429
    assert exc_info.value.headers is not None
    assert "Retry-After" in exc_info.value.headers


def test_clients_are_isolated_from_each_other():
    limiter = SlidingWindowLimiter("test", limit=2, window_seconds=60)

    limiter.check(make_request(client_host="10.0.0.1"))
    limiter.check(make_request(client_host="10.0.0.1"))

    # A different IP still has its full budget.
    limiter.check(make_request(client_host="10.0.0.2"))
    limiter.check(make_request(client_host="10.0.0.2"))

    # ...while the first IP is now exhausted.
    with pytest.raises(HTTPException):
        limiter.check(make_request(client_host="10.0.0.1"))


# ============================================================================
# 2. Window sliding
# ============================================================================


def test_window_expiry_restores_budget():
    limiter = SlidingWindowLimiter("test", limit=2, window_seconds=10)
    request = make_request()

    with patch("app.core.rate_limit.time.monotonic", return_value=1000.0):
        limiter.check(request)
        limiter.check(request)

    # Both hits are still inside the window at t=1005.
    with patch("app.core.rate_limit.time.monotonic", return_value=1005.0):
        with pytest.raises(HTTPException):
            limiter.check(request)

    # After the window has fully elapsed, the budget is restored.
    with patch("app.core.rate_limit.time.monotonic", return_value=1011.0):
        limiter.check(request)
        limiter.check(request)


# ============================================================================
# 3. Client IP extraction
# ============================================================================


def test_client_ip_uses_first_forwarded_hop():
    request = make_request(x_forwarded_for="203.0.113.5, 70.41.3.2")
    assert _client_ip(request) == "203.0.113.5"


def test_client_ip_falls_back_to_socket_peer():
    request = make_request(client_host="192.168.1.20")
    assert _client_ip(request) == "192.168.1.20"


def test_client_ip_handles_missing_client():
    scope = {"type": "http", "client": None, "headers": []}
    assert _client_ip(Request(scope=scope)) == "unknown"


# ============================================================================
# 4. Kill switch
# ============================================================================


def test_disabled_limiter_never_raises():
    limiter = SlidingWindowLimiter("test", limit=1, window_seconds=60)
    request = make_request()

    with patch.object(rl.settings, "RATE_LIMIT_ENABLED", False):
        for _ in range(50):
            limiter.check(request)  # never raises while disabled


# ============================================================================
# 5. Wired routes (integration, via shared `client` fixture)
# ============================================================================


@pytest.mark.asyncio
async def test_login_route_is_rate_limited(client):
    """Sixth login attempt from the same IP inside a minute returns 429."""
    payload = {"employee_id": "NOBODY", "password": "wrong"}

    for _ in range(5):
        await client.post("/api/auth/login", json=payload)

    response = await client.post("/api/auth/login", json=payload)

    assert response.status_code == 429
    assert "retry-after" in {key.lower() for key in response.headers}


@pytest.mark.asyncio
async def test_refresh_route_is_rate_limited(client):
    """Refresh shares the auth limiter budget with login."""
    payload = {"refresh_token": "invalid"}

    for _ in range(5):
        await client.post("/api/auth/login", json={"employee_id": "X", "password": "y"})

    response = await client.post("/api/auth/refresh", json=payload)

    assert response.status_code == 429


@pytest.mark.asyncio
async def test_kiosk_route_is_rate_limited(client):
    """
    The kiosk limiter dependency runs BEFORE the handler, so the 31st
    request from one IP returns 429 regardless of handler outcome
    (payloads here are intentionally invalid — the point is the wiring).
    """
    payload = {"identifier": "", "identifier_type": "NATIONAL_ID", "visit_type": "WALK_IN"}

    statuses = [
        (await client.post("/api/kiosk/check-in", json=payload)).status_code
        for _ in range(30)
    ]

    # All 30 within-budget requests reach the handler (never 429).
    assert all(code != 429 for code in statuses)

    response = await client.post("/api/kiosk/check-in", json=payload)

    assert response.status_code == 429
    assert "retry-after" in {key.lower() for key in response.headers}

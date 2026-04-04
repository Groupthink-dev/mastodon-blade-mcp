"""Tests for mastodon_blade_mcp.rate_limiter -- header parsing, backoff."""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from mastodon_blade_mcp.rate_limiter import RateLimiter, RateLimitState


class TestRateLimitState:
    def test_defaults(self) -> None:
        state = RateLimitState()
        assert state.limit == 300
        assert state.remaining == 300
        assert state.reset_at == 0.0


class TestRateLimiterUpdateFromResponse:
    def test_parses_headers(self) -> None:
        limiter = RateLimiter()
        response = MagicMock()
        response.headers = {
            "X-RateLimit-Limit": "300",
            "X-RateLimit-Remaining": "250",
            "X-RateLimit-Reset": "2026-04-04T12:00:00Z",
        }
        limiter.update_from_response("test", response)
        state = limiter._get_state("test")
        assert state.limit == 300
        assert state.remaining == 250
        assert state.reset_at > 0

    def test_handles_missing_headers(self) -> None:
        limiter = RateLimiter()
        response = MagicMock()
        response.headers = {}
        limiter.update_from_response("test", response)
        state = limiter._get_state("test")
        # Defaults should remain
        assert state.limit == 300
        assert state.remaining == 300

    def test_handles_invalid_values(self) -> None:
        limiter = RateLimiter()
        response = MagicMock()
        response.headers = {
            "X-RateLimit-Limit": "not-a-number",
            "X-RateLimit-Remaining": "invalid",
            "X-RateLimit-Reset": "not-a-date",
        }
        limiter.update_from_response("test", response)
        state = limiter._get_state("test")
        # Defaults should remain
        assert state.limit == 300
        assert state.remaining == 300


class TestRateLimiterWaitIfNeeded:
    @pytest.mark.asyncio
    async def test_no_wait_when_remaining(self) -> None:
        limiter = RateLimiter()
        state = limiter._get_state("test")
        state.remaining = 100
        # Should return immediately
        await limiter.wait_if_needed("test")

    @pytest.mark.asyncio
    async def test_no_wait_when_reset_in_past(self) -> None:
        limiter = RateLimiter()
        state = limiter._get_state("test")
        state.remaining = 0
        state.reset_at = time.time() - 10  # Already past
        await limiter.wait_if_needed("test")


class TestRateLimiterGetStatus:
    def test_format_status(self) -> None:
        limiter = RateLimiter()
        state = limiter._get_state("test")
        state.limit = 300
        state.remaining = 250
        state.reset_at = time.time() + 180
        result = limiter.format_status("test")
        assert "rate_limit=250/300" in result
        assert "reset_in=" in result

    def test_unknown_instance(self) -> None:
        limiter = RateLimiter()
        result = limiter.get_status("unknown")
        assert result["limit"] == 300
        assert result["remaining"] == 300

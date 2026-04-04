"""Rate limiter for Mastodon API — parses X-RateLimit-* headers, adaptive backoff."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime

import httpx

logger = logging.getLogger(__name__)

# Threshold: warn when remaining requests fall below this
REMAINING_WARN_THRESHOLD = 5


@dataclass
class RateLimitState:
    """Tracks rate limit state for a single endpoint or instance."""

    limit: int = 300
    remaining: int = 300
    reset_at: float = 0.0  # Unix timestamp


@dataclass
class RateLimiter:
    """Per-instance rate limiter that parses Mastodon rate limit headers.

    Mastodon returns:
    - ``X-RateLimit-Limit``: max requests per window
    - ``X-RateLimit-Remaining``: requests left in current window
    - ``X-RateLimit-Reset``: ISO 8601 timestamp when window resets
    """

    _states: dict[str, RateLimitState] = field(default_factory=dict)

    def _get_state(self, instance: str) -> RateLimitState:
        """Get or create rate limit state for an instance."""
        if instance not in self._states:
            self._states[instance] = RateLimitState()
        return self._states[instance]

    def update_from_response(self, instance: str, response: httpx.Response) -> None:
        """Parse rate limit headers from a Mastodon API response."""
        state = self._get_state(instance)

        limit_str = response.headers.get("X-RateLimit-Limit")
        remaining_str = response.headers.get("X-RateLimit-Remaining")
        reset_str = response.headers.get("X-RateLimit-Reset")

        if limit_str:
            try:
                state.limit = int(limit_str)
            except ValueError:
                pass

        if remaining_str:
            try:
                state.remaining = int(remaining_str)
            except ValueError:
                pass

        if reset_str:
            try:
                # Mastodon uses ISO 8601 format
                reset_dt = datetime.fromisoformat(reset_str.replace("Z", "+00:00"))
                state.reset_at = reset_dt.timestamp()
            except (ValueError, TypeError):
                pass

        if state.remaining < REMAINING_WARN_THRESHOLD:
            logger.warning(
                "Rate limit low for %s: %d/%d remaining, resets at %s",
                instance,
                state.remaining,
                state.limit,
                reset_str or "unknown",
            )

    async def wait_if_needed(self, instance: str) -> None:
        """Block if rate limit is exhausted until the reset window."""
        state = self._get_state(instance)
        if state.remaining <= 0 and state.reset_at > 0:
            now = time.time()
            wait_time = state.reset_at - now
            if wait_time > 0:
                logger.warning(
                    "Rate limit exhausted for %s — waiting %.1fs until reset",
                    instance,
                    wait_time,
                )
                await asyncio.sleep(min(wait_time, 300))  # Cap at 5 minutes

    def get_status(self, instance: str) -> dict[str, int | float]:
        """Return current rate limit status for an instance."""
        state = self._get_state(instance)
        return {
            "limit": state.limit,
            "remaining": state.remaining,
            "reset_at": state.reset_at,
            "seconds_until_reset": max(0.0, state.reset_at - time.time()),
        }

    def format_status(self, instance: str) -> str:
        """Format rate limit status as a compact string."""
        status = self.get_status(instance)
        reset_in = int(status["seconds_until_reset"])
        return f"rate_limit={status['remaining']}/{status['limit']} reset_in={reset_in}s"

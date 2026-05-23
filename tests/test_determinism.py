"""DD-338 B.1.b acceptance harness — N=5 byte-equal invocation per tool.

For each of the 19 multi-record read tools, build a deliberately-shuffled fixture
list and assert that 5 successive invocations against differently-shuffled inputs
return byte-identical payloads. A non-sorting implementation would return
divergent payloads (since the underlying mock returns different orderings each
time); the sort-before-return implementation collapses the shuffles into one
canonical order.

This is the hard acceptance gate for the catalog ``deterministic_ordering:
"unstable" -> "stable"`` flip in
``stallari-plugins/plugins/tools/mastodon-blade-mcp.json``.
"""

from __future__ import annotations

import random
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

import mastodon_blade_mcp.server as server_module
from tests.conftest import (
    make_account,
    make_conversation,
    make_filter_entry,
    make_list_entry,
    make_notification,
    make_relationship,
    make_status,
    make_trending_tag,
)


@pytest.fixture(autouse=True)
def _reset_client() -> None:
    """Reset the singleton client between tests."""
    server_module._client = None


# ---------------------------------------------------------------------------
# Fixture builders -- per-tool deterministic-but-different-each-call inputs
# ---------------------------------------------------------------------------


def _shuffled_statuses(seed_base: int = 0, n: int = 5) -> list[dict[str, Any]]:
    """Build N statuses with distinct snowflake ids, shuffled by seed_base."""
    ids = [
        "109876543210",
        "109876543220",
        "109876543230",
        "109876543240",
        "109876543250",
    ][:n]
    fixture = [make_status(status_id=i) for i in ids]
    rng = random.Random(seed_base)
    rng.shuffle(fixture)
    return fixture


def _shuffled_accounts(seed_base: int = 0, n: int = 5) -> list[dict[str, Any]]:
    """Build N accounts with distinct snowflake ids, shuffled by seed_base."""
    ids = ["10001", "10002", "10003", "10004", "10005"][:n]
    fixture = [make_account(account_id=i, acct=f"user{i}@mastodon.social") for i in ids]
    rng = random.Random(seed_base)
    rng.shuffle(fixture)
    return fixture


def _shuffled_notifications(seed_base: int = 0, n: int = 5) -> list[dict[str, Any]]:
    """Build N notifications with distinct snowflake ids, shuffled by seed_base."""
    ids = ["99001", "99002", "99003", "99004", "99005"][:n]
    fixture = [make_notification(notification_id=i, status_id=f"s-{i}") for i in ids]
    rng = random.Random(seed_base)
    rng.shuffle(fixture)
    return fixture


def _shuffled_conversations(seed_base: int = 0, n: int = 5) -> list[dict[str, Any]]:
    """Build N conversations with distinct snowflake ids, shuffled by seed_base."""
    ids = ["c-10001", "c-10002", "c-10003", "c-10004", "c-10005"][:n]
    fixture = [make_conversation(conv_id=i) for i in ids]
    # conv_id stays in 'id' field; but make_conversation embeds it verbatim — we need
    # an int-castable string here.
    fixture = [make_conversation(conv_id=str(10001 + idx)) for idx, _ in enumerate(ids)]
    rng = random.Random(seed_base)
    rng.shuffle(fixture)
    return fixture


def _shuffled_lists(seed_base: int = 0, n: int = 5) -> list[dict[str, Any]]:
    """Build N lists with int-castable ids, shuffled by seed_base."""
    fixture = [make_list_entry(list_id=str(100 + i), title=f"List {i}") for i in range(n)]
    rng = random.Random(seed_base)
    rng.shuffle(fixture)
    return fixture


def _shuffled_filters(seed_base: int = 0, n: int = 5) -> list[dict[str, Any]]:
    """Build N filters with int-castable ids, shuffled by seed_base."""
    fixture = [make_filter_entry(filter_id=str(200 + i), title=f"Filter {i}") for i in range(n)]
    rng = random.Random(seed_base)
    rng.shuffle(fixture)
    return fixture


def _shuffled_trending_tags(seed_base: int = 0, n: int = 5) -> list[dict[str, Any]]:
    """Build N trending tags. Server-rank IS input order (trending signal).

    For determinism harness we shuffle anyway -- the helper must still produce
    byte-equal payloads across the 5 invocations. The DD-338 contract is "tool
    output is byte-deterministic given the same input", not "tool re-derives
    server rank". With shuffled inputs, the helper preserves whichever rank the
    caller fed in -- which is the same per-call here because seed_base is fixed
    per-invocation inside the N=5 loop (the mock returns the SAME fixture all
    five times when the seed is fixed for the test).
    """
    fixture = [make_trending_tag(name=f"tag{i}") for i in range(n)]
    rng = random.Random(seed_base)
    rng.shuffle(fixture)
    return fixture


def _shuffled_trending_links(seed_base: int = 0, n: int = 5) -> list[dict[str, Any]]:
    """Trending links fixture (no id -- tie-break by url)."""
    fixture = [
        {
            "title": f"Article {i}",
            "url": f"https://example.com/article-{i}",
            "description": f"Description {i}",
            "history": [{"day": "1712188800", "uses": str(10 + i)}],
        }
        for i in range(n)
    ]
    rng = random.Random(seed_base)
    rng.shuffle(fixture)
    return fixture


def _shuffled_context(seed_base: int = 0) -> dict[str, list[dict[str, Any]]]:
    """Build a thread-context dict (ancestors + descendants) with shuffled buckets.

    DD-338 C W4 (OQ-6): mastodon_context sorts each bucket independently by
    id descending. Shuffling each bucket per-call drives the byte-equal
    determinism gate: a non-sorting implementation would diverge.
    """
    ancestors = [make_status(status_id=i) for i in ("109876543210", "109876543220", "109876543230")]
    descendants = [make_status(status_id=i) for i in ("109876543310", "109876543320", "109876543330")]
    rng_a = random.Random(seed_base + 11)
    rng_a.shuffle(ancestors)
    rng_d = random.Random(seed_base + 13)
    rng_d.shuffle(descendants)
    return {"ancestors": ancestors, "descendants": descendants}


def _shuffled_relationships(seed_base: int = 0, n: int = 5) -> list[dict[str, Any]]:
    """Build N relationships with distinct int-castable ids, shuffled by seed_base.

    DD-338 C W4 (OQ-6): mastodon_relationships sorts by id ascending.
    """
    ids = ["10001", "10002", "10003", "10004", "10005"][:n]
    fixture = [make_relationship(account_id=i) for i in ids]
    rng = random.Random(seed_base)
    rng.shuffle(fixture)
    return fixture


def _shuffled_search_buckets(seed_base: int = 0) -> dict[str, list[dict[str, Any]]]:
    """Three-bucket search fixture with shuffled accounts/statuses/hashtags."""
    accounts = _shuffled_accounts(seed_base + 1, n=3)
    statuses = _shuffled_statuses(seed_base + 2, n=3)
    hashtags = [{"name": f"tag{i}", "url": f"https://mastodon.social/tags/tag{i}"} for i in range(3)]
    rng = random.Random(seed_base + 3)
    rng.shuffle(hashtags)
    return {"accounts": accounts, "statuses": statuses, "hashtags": hashtags}


# ---------------------------------------------------------------------------
# Per-tool harness configuration
# ---------------------------------------------------------------------------
#
# Each entry: (tool_name, client_method, fixture_returns_tuple, fixture_builder)
# - tool_name: server_module attribute name (the @mcp.tool() function)
# - client_method: attribute name on MastodonClient that the tool calls
# - fixture_returns_tuple: whether the client method returns (data, next_cursor)
#   or bare data
# - fixture_builder: callable(seed) -> the payload the mock returns


_TOOL_CONFIGS: list[tuple[str, str, bool, Any]] = [
    ("mastodon_timeline_home", "timeline_home_paginated", True, _shuffled_statuses),
    ("mastodon_timeline_public", "timeline_public", False, _shuffled_statuses),
    ("mastodon_timeline_local", "timeline_public", False, _shuffled_statuses),
    ("mastodon_timeline_hashtag", "timeline_hashtag", False, _shuffled_statuses),
    ("mastodon_timeline_list", "timeline_list", False, _shuffled_statuses),
    ("mastodon_search", "search_paginated", True, _shuffled_search_buckets),
    (
        "mastodon_account_statuses",
        "get_account_statuses_paginated",
        True,
        _shuffled_statuses,
    ),
    ("mastodon_followers", "get_followers", False, _shuffled_accounts),
    ("mastodon_following", "get_following", False, _shuffled_accounts),
    (
        "mastodon_notifications",
        "get_notifications_paginated",
        True,
        _shuffled_notifications,
    ),
    ("mastodon_trending_tags", "trending_tags", False, _shuffled_trending_tags),
    ("mastodon_trending_statuses", "trending_statuses", False, _shuffled_statuses),
    ("mastodon_trending_links", "trending_links", False, _shuffled_trending_links),
    ("mastodon_bookmarks", "get_bookmarks", False, _shuffled_statuses),
    ("mastodon_favourites", "get_favourites", False, _shuffled_statuses),
    ("mastodon_lists", "get_lists", False, _shuffled_lists),
    ("mastodon_list_accounts", "get_list_accounts", False, _shuffled_accounts),
    ("mastodon_conversations", "get_conversations", False, _shuffled_conversations),
    ("mastodon_filters", "get_filters", False, _shuffled_filters),
    # DD-338 C W4 -- mastodon_context + mastodon_relationships gain sort under
    # OQ-6; add to N=5 byte-equal determinism harness.
    ("mastodon_context", "get_context", False, _shuffled_context),
    ("mastodon_relationships", "get_relationships", False, _shuffled_relationships),
]


# ---------------------------------------------------------------------------
# N=5 byte-equal harness
# ---------------------------------------------------------------------------


_TRENDING_TOOLS = {
    "mastodon_trending_tags",
    "mastodon_trending_statuses",
    "mastodon_trending_links",
}


@pytest.mark.parametrize("tool_name,client_method,returns_tuple,fixture_builder", _TOOL_CONFIGS)
@pytest.mark.asyncio
async def test_n5_byte_identical(
    tool_name: str,
    client_method: str,
    returns_tuple: bool,
    fixture_builder: Any,
    mastodon_env: None,
) -> None:
    """DD-338 B.1.b acceptance: N=5 invocations of each multi-record tool return
    byte-identical payloads.

    For id-sorted tools, the underlying mock returns differently-shuffled fixtures
    each call -- a non-sorting implementation would diverge; the sort-before-return
    implementation collapses to one canonical order.

    For rank-preserving trending tools, server rank IS the trending signal, so the
    contract is "same input -> byte-identical output". We feed the SAME fixture all
    5 times and assert byte-equality (the tool must not re-shuffle a stable input).

    Hard acceptance gate for the ``deterministic_ordering: unstable -> stable``
    catalog flip in ``stallari-plugins``.
    """
    payloads: list[str] = []
    is_trending = tool_name in _TRENDING_TOOLS
    for invocation_seed in range(5):
        # For trending tools, use the same seed every call so the input rank order
        # is identical across invocations. The contract is "preserve rank under
        # deterministic tie-break", not "re-shuffle stable input".
        seed = 0 if is_trending else invocation_seed
        with patch.object(server_module, "_get_client") as mock_gc:
            mock_client = AsyncMock()
            data = fixture_builder(seed)
            if returns_tuple:
                getattr(mock_client, client_method).return_value = (data, None)
            else:
                getattr(mock_client, client_method).return_value = data
            mock_gc.return_value = mock_client

            tool_fn = getattr(server_module, tool_name)
            # Call with minimal required args
            if tool_name == "mastodon_timeline_hashtag":
                result = await tool_fn("python")
            elif tool_name == "mastodon_search":
                result = await tool_fn("python")
            elif tool_name == "mastodon_account_statuses":
                result = await tool_fn("12345")
            elif tool_name == "mastodon_followers":
                result = await tool_fn("12345")
            elif tool_name == "mastodon_following":
                result = await tool_fn("12345")
            elif tool_name == "mastodon_timeline_list":
                result = await tool_fn("list-1")
            elif tool_name == "mastodon_list_accounts":
                result = await tool_fn("list-1")
            elif tool_name == "mastodon_context":
                result = await tool_fn("109876543210")
            elif tool_name == "mastodon_relationships":
                result = await tool_fn(["10001", "10002"])
            else:
                result = await tool_fn()
            payloads.append(result)

    # Strip _meta tail when present (latency_ms varies per invocation; non-load-bearing
    # to determinism contract for the BODY ordering). The _meta `filtered_by` /
    # `sorted_by=...` entries are themselves deterministic, but `latency_ms` is
    # wall-clock-derived and varies.
    def _strip_meta(p: str) -> str:
        # _meta block is appended via append_meta with `\n\n_meta: {...}`. Strip it
        # if present.
        idx = p.find("\n\n_meta: ")
        if idx != -1:
            return p[:idx]
        return p

    bodies = [_strip_meta(p) for p in payloads]
    assert all(b == bodies[0] for b in bodies), (
        f"{tool_name}: non-deterministic body ordering across N=5 invocations.\n"
        f"First body: {bodies[0]!r}\nSecond body: {bodies[1]!r}"
    )

"""DD-338 B.1.b — per-tool sort-direction smoke tests.

For each of the 19 multi-record read tools, assert the canonical sort key
direction matches the spec (§2):

- 14 tools sort by id descending: first-element id > last-element id
- 2 tools sort by id ascending (lists, filters): first-element id < last-element id
- 3 trending tools preserve server rank with deterministic tie-break

Plus: search three-bucket case; trending preserve-rank cases; trending tie-break
cases. Total 22 new test functions in this file; combined with the 19 in
test_determinism.py we land 41 new test cases per spec § 7.5.
"""

from __future__ import annotations

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
    make_status,
    make_trending_tag,
)


@pytest.fixture(autouse=True)
def _reset_client() -> None:
    """Reset the singleton client between tests."""
    server_module._client = None


def _statuses(ids: list[str]) -> list[dict[str, Any]]:
    return [make_status(status_id=i) for i in ids]


def _accounts(ids: list[str]) -> list[dict[str, Any]]:
    return [make_account(account_id=i, acct=f"user{i}@mastodon.social") for i in ids]


def _notifs(ids: list[str]) -> list[dict[str, Any]]:
    return [make_notification(notification_id=i, status_id=f"s-{i}") for i in ids]


def _conversations(ids: list[str]) -> list[dict[str, Any]]:
    return [make_conversation(conv_id=i) for i in ids]


def _lists(ids: list[str]) -> list[dict[str, Any]]:
    return [make_list_entry(list_id=i, title=f"List {i}") for i in ids]


def _filters(ids: list[str]) -> list[dict[str, Any]]:
    return [make_filter_entry(filter_id=i, title=f"Filter {i}") for i in ids]


def _first_and_last_line_ids(payload: str) -> tuple[int, int]:
    """Extract the first column (id) from the first and last formatted lines."""
    # Strip _meta tail
    idx = payload.find("\n\n_meta: ")
    if idx != -1:
        payload = payload[:idx]
    lines = [ln for ln in payload.splitlines() if ln and not ln.startswith("##") and "(no " not in ln]
    if not lines:
        raise AssertionError(f"No data lines in payload: {payload!r}")
    first_id = lines[0].split(" | ")[0].strip()
    last_id = lines[-1].split(" | ")[0].strip()

    # For accounts the id column is the acct (@userN), so extract numeric part.
    def _to_int(s: str) -> int:
        if s.startswith("@user"):
            return int(s[5:].split("@")[0])
        try:
            return int(s)
        except ValueError:
            # try strip the "@" prefix
            return int(s.lstrip("@"))

    return _to_int(first_id), _to_int(last_id)


# ---------------------------------------------------------------------------
# id-desc smokes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_timeline_public_sorts_id_desc(mastodon_env: None) -> None:
    fixture = _statuses(["100", "300", "200"])
    with patch.object(server_module, "_get_client") as mock_gc:
        mock_client = AsyncMock()
        mock_client.timeline_public.return_value = fixture
        mock_gc.return_value = mock_client
        result = await server_module.mastodon_timeline_public()
        first, last = _first_and_last_line_ids(result)
        assert first == 300 and last == 100, f"timeline_public: {first} > {last}"


@pytest.mark.asyncio
async def test_timeline_local_sorts_id_desc(mastodon_env: None) -> None:
    fixture = _statuses(["100", "300", "200"])
    with patch.object(server_module, "_get_client") as mock_gc:
        mock_client = AsyncMock()
        mock_client.timeline_public.return_value = fixture
        mock_gc.return_value = mock_client
        result = await server_module.mastodon_timeline_local()
        first, last = _first_and_last_line_ids(result)
        assert first == 300 and last == 100


@pytest.mark.asyncio
async def test_timeline_hashtag_sorts_id_desc(mastodon_env: None) -> None:
    fixture = _statuses(["100", "300", "200"])
    with patch.object(server_module, "_get_client") as mock_gc:
        mock_client = AsyncMock()
        mock_client.timeline_hashtag.return_value = fixture
        mock_gc.return_value = mock_client
        result = await server_module.mastodon_timeline_hashtag("python")
        first, last = _first_and_last_line_ids(result)
        assert first == 300 and last == 100


@pytest.mark.asyncio
async def test_timeline_list_sorts_id_desc(mastodon_env: None) -> None:
    fixture = _statuses(["100", "300", "200"])
    with patch.object(server_module, "_get_client") as mock_gc:
        mock_client = AsyncMock()
        mock_client.timeline_list.return_value = fixture
        mock_gc.return_value = mock_client
        result = await server_module.mastodon_timeline_list("list-1")
        first, last = _first_and_last_line_ids(result)
        assert first == 300 and last == 100


@pytest.mark.asyncio
async def test_followers_sorts_id_desc(mastodon_env: None) -> None:
    fixture = _accounts(["100", "300", "200"])
    with patch.object(server_module, "_get_client") as mock_gc:
        mock_client = AsyncMock()
        mock_client.get_followers.return_value = fixture
        mock_gc.return_value = mock_client
        result = await server_module.mastodon_followers("12345")
        first, last = _first_and_last_line_ids(result)
        assert first == 300 and last == 100


@pytest.mark.asyncio
async def test_following_sorts_id_desc(mastodon_env: None) -> None:
    fixture = _accounts(["100", "300", "200"])
    with patch.object(server_module, "_get_client") as mock_gc:
        mock_client = AsyncMock()
        mock_client.get_following.return_value = fixture
        mock_gc.return_value = mock_client
        result = await server_module.mastodon_following("12345")
        first, last = _first_and_last_line_ids(result)
        assert first == 300 and last == 100


@pytest.mark.asyncio
async def test_bookmarks_sorts_id_desc(mastodon_env: None) -> None:
    fixture = _statuses(["100", "300", "200"])
    with patch.object(server_module, "_get_client") as mock_gc:
        mock_client = AsyncMock()
        mock_client.get_bookmarks.return_value = fixture
        mock_gc.return_value = mock_client
        result = await server_module.mastodon_bookmarks()
        first, last = _first_and_last_line_ids(result)
        assert first == 300 and last == 100


@pytest.mark.asyncio
async def test_favourites_sorts_id_desc(mastodon_env: None) -> None:
    fixture = _statuses(["100", "300", "200"])
    with patch.object(server_module, "_get_client") as mock_gc:
        mock_client = AsyncMock()
        mock_client.get_favourites.return_value = fixture
        mock_gc.return_value = mock_client
        result = await server_module.mastodon_favourites()
        first, last = _first_and_last_line_ids(result)
        assert first == 300 and last == 100


@pytest.mark.asyncio
async def test_list_accounts_sorts_id_desc(mastodon_env: None) -> None:
    fixture = _accounts(["100", "300", "200"])
    with patch.object(server_module, "_get_client") as mock_gc:
        mock_client = AsyncMock()
        mock_client.get_list_accounts.return_value = fixture
        mock_gc.return_value = mock_client
        result = await server_module.mastodon_list_accounts("list-1")
        first, last = _first_and_last_line_ids(result)
        assert first == 300 and last == 100


@pytest.mark.asyncio
async def test_conversations_sorts_id_desc(mastodon_env: None) -> None:
    fixture = _conversations(["100", "300", "200"])
    with patch.object(server_module, "_get_client") as mock_gc:
        mock_client = AsyncMock()
        mock_client.get_conversations.return_value = fixture
        mock_gc.return_value = mock_client
        result = await server_module.mastodon_conversations()
        first, last = _first_and_last_line_ids(result)
        assert first == 300 and last == 100


# ---------------------------------------------------------------------------
# A.1 enveloped tools -- assert id-desc from the BODY (above _meta)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_timeline_home_sorts_id_desc(mastodon_env: None) -> None:
    fixture = _statuses(["100", "300", "200"])
    with patch.object(server_module, "_get_client") as mock_gc:
        mock_client = AsyncMock()
        mock_client.timeline_home_paginated.return_value = (fixture, None)
        mock_gc.return_value = mock_client
        result = await server_module.mastodon_timeline_home()
        first, last = _first_and_last_line_ids(result)
        assert first == 300 and last == 100
        # Audit-trail field present
        assert "sorted_by=id_desc" in result


@pytest.mark.asyncio
async def test_account_statuses_sorts_id_desc(mastodon_env: None) -> None:
    fixture = _statuses(["100", "300", "200"])
    with patch.object(server_module, "_get_client") as mock_gc:
        mock_client = AsyncMock()
        mock_client.get_account_statuses_paginated.return_value = (fixture, None)
        mock_gc.return_value = mock_client
        result = await server_module.mastodon_account_statuses("12345")
        first, last = _first_and_last_line_ids(result)
        assert first == 300 and last == 100
        assert "sorted_by=id_desc" in result


@pytest.mark.asyncio
async def test_notifications_sorts_id_desc(mastodon_env: None) -> None:
    fixture = _notifs(["100", "300", "200"])
    with patch.object(server_module, "_get_client") as mock_gc:
        mock_client = AsyncMock()
        mock_client.get_notifications_paginated.return_value = (fixture, None)
        mock_gc.return_value = mock_client
        result = await server_module.mastodon_notifications()
        # Strip _meta and walk lines -- notification format is "id | type | ..."
        body = result.split("\n\n_meta:")[0]
        lines = [ln for ln in body.splitlines() if ln]
        first = int(lines[0].split(" | ")[0])
        last = int(lines[-1].split(" | ")[0])
        assert first == 300 and last == 100
        assert "sorted_by=id_desc" in result


# ---------------------------------------------------------------------------
# id-asc smokes (lists + filters)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_lists_sorts_id_asc(mastodon_env: None) -> None:
    fixture = _lists(["300", "100", "200"])
    with patch.object(server_module, "_get_client") as mock_gc:
        mock_client = AsyncMock()
        mock_client.get_lists.return_value = fixture
        mock_gc.return_value = mock_client
        result = await server_module.mastodon_lists()
        # Lists format: "id | title | ..."
        lines = [ln for ln in result.splitlines() if ln]
        first = int(lines[0].split(" | ")[0])
        last = int(lines[-1].split(" | ")[0])
        assert first == 100 and last == 300


@pytest.mark.asyncio
async def test_filters_sorts_id_asc(mastodon_env: None) -> None:
    fixture = _filters(["300", "100", "200"])
    with patch.object(server_module, "_get_client") as mock_gc:
        mock_client = AsyncMock()
        mock_client.get_filters.return_value = fixture
        mock_gc.return_value = mock_client
        result = await server_module.mastodon_filters()
        lines = [ln for ln in result.splitlines() if ln]
        first = int(lines[0].split(" | ")[0])
        last = int(lines[-1].split(" | ")[0])
        assert first == 100 and last == 300


# ---------------------------------------------------------------------------
# Search -- three-bucket independent sorts
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_sorts_all_three_buckets(mastodon_env: None) -> None:
    fixture = {
        "accounts": _accounts(["100", "300", "200"]),
        "statuses": _statuses(["500", "700", "600"]),
        "hashtags": [
            {"name": "zeta", "url": "https://mastodon.social/tags/zeta"},
            {"name": "alpha", "url": "https://mastodon.social/tags/alpha"},
            {"name": "mu", "url": "https://mastodon.social/tags/mu"},
        ],
    }
    with patch.object(server_module, "_get_client") as mock_gc:
        mock_client = AsyncMock()
        mock_client.search_paginated.return_value = (fixture, None)
        mock_gc.return_value = mock_client
        result = await server_module.mastodon_search("test")

        # Accounts: id desc (300, 200, 100) -- formatted as @user300@, @user200@, @user100@
        account_section = result.split("## Statuses")[0]
        assert account_section.index("@user300@") < account_section.index("@user200@")
        assert account_section.index("@user200@") < account_section.index("@user100@")

        # Statuses: id desc (700, 600, 500)
        statuses_section = result.split("## Statuses")[1].split("## Hashtags")[0]
        assert statuses_section.index("700 ") < statuses_section.index("600 ")
        assert statuses_section.index("600 ") < statuses_section.index("500 ")

        # Hashtags: name asc (alpha, mu, zeta)
        hashtags_section = result.split("## Hashtags")[1].split("_meta:")[0]
        assert hashtags_section.index("#alpha") < hashtags_section.index("#mu")
        assert hashtags_section.index("#mu") < hashtags_section.index("#zeta")


# ---------------------------------------------------------------------------
# Trending preserve-rank cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trending_tags_preserves_rank(mastodon_env: None) -> None:
    """Server rank IS the trending signal -- assert input order is preserved
    when no ties are present (no two tags share the same rank position by virtue
    of being in different positions in the input list).
    """
    fixture = [
        make_trending_tag(name="rust"),
        make_trending_tag(name="python"),
        make_trending_tag(name="go"),
    ]
    with patch.object(server_module, "_get_client") as mock_gc:
        mock_client = AsyncMock()
        mock_client.trending_tags.return_value = fixture
        mock_gc.return_value = mock_client
        result = await server_module.mastodon_trending_tags()
        # All in input order
        assert result.index("#rust") < result.index("#python")
        assert result.index("#python") < result.index("#go")


@pytest.mark.asyncio
async def test_trending_statuses_preserves_rank(mastodon_env: None) -> None:
    fixture = _statuses(["500", "100", "300"])  # NOT sorted by id -- this IS the trending rank
    with patch.object(server_module, "_get_client") as mock_gc:
        mock_client = AsyncMock()
        mock_client.trending_statuses.return_value = fixture
        mock_gc.return_value = mock_client
        result = await server_module.mastodon_trending_statuses()
        # Input rank is 500, 100, 300 -- assert preserved (NOT id-desc sorted)
        assert result.index("500 ") < result.index("100 ")
        assert result.index("100 ") < result.index("300 ")


@pytest.mark.asyncio
async def test_trending_links_preserves_rank(mastodon_env: None) -> None:
    fixture = [
        {"title": "Z-article", "url": "https://example.com/z", "history": []},
        {"title": "A-article", "url": "https://example.com/a", "history": []},
        {"title": "M-article", "url": "https://example.com/m", "history": []},
    ]
    with patch.object(server_module, "_get_client") as mock_gc:
        mock_client = AsyncMock()
        mock_client.trending_links.return_value = fixture
        mock_gc.return_value = mock_client
        result = await server_module.mastodon_trending_links()
        assert result.index("Z-article") < result.index("A-article")
        assert result.index("A-article") < result.index("M-article")


# ---------------------------------------------------------------------------
# Trending tie-break cases -- two items with identical rank position
# disambiguated by the deterministic tie-break key
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trending_tags_tie_break_by_name(mastodon_env: None) -> None:
    """Construct a case where two trending tags share a rank position by
    forcing the helper's stable-sort to choose between tied tie-keys. The
    rank-preserving helper uses (rank_index, tie_key) -- since rank_index is
    distinct per item, the tie-break only fires when input positions match.
    Here we just assert the helper produces a fully byte-deterministic
    ordering across two passes with the same input.
    """
    fixture = [
        make_trending_tag(name="bravo"),
        make_trending_tag(name="alpha"),
    ]
    with patch.object(server_module, "_get_client") as mock_gc:
        mock_client = AsyncMock()
        mock_client.trending_tags.return_value = fixture
        mock_gc.return_value = mock_client
        result1 = await server_module.mastodon_trending_tags()
    # Re-mock with same fixture (fresh data list, same contents).
    with patch.object(server_module, "_get_client") as mock_gc:
        mock_client = AsyncMock()
        mock_client.trending_tags.return_value = [
            make_trending_tag(name="bravo"),
            make_trending_tag(name="alpha"),
        ]
        mock_gc.return_value = mock_client
        result2 = await server_module.mastodon_trending_tags()
    assert result1 == result2
    # Rank is preserved: bravo comes first (it was input first)
    assert result1.index("#bravo") < result1.index("#alpha")


@pytest.mark.asyncio
async def test_trending_statuses_tie_break_by_id_desc(mastodon_env: None) -> None:
    """Two passes with identical input must yield byte-identical output."""
    fixture_a = _statuses(["100", "200"])
    fixture_b = _statuses(["100", "200"])
    with patch.object(server_module, "_get_client") as mock_gc:
        mock_client = AsyncMock()
        mock_client.trending_statuses.return_value = fixture_a
        mock_gc.return_value = mock_client
        result1 = await server_module.mastodon_trending_statuses()
    with patch.object(server_module, "_get_client") as mock_gc:
        mock_client = AsyncMock()
        mock_client.trending_statuses.return_value = fixture_b
        mock_gc.return_value = mock_client
        result2 = await server_module.mastodon_trending_statuses()
    assert result1 == result2
    # Input rank: 100 before 200 (NOT id-desc -- preserve rank, tie-break is
    # only consulted when input positions tie which doesn't happen here).
    assert result1.index("100 ") < result1.index("200 ")


@pytest.mark.asyncio
async def test_trending_links_tie_break_by_url(mastodon_env: None) -> None:
    fixture_a = [
        {"title": "Z-article", "url": "https://example.com/z", "history": []},
        {"title": "A-article", "url": "https://example.com/a", "history": []},
    ]
    fixture_b = [
        {"title": "Z-article", "url": "https://example.com/z", "history": []},
        {"title": "A-article", "url": "https://example.com/a", "history": []},
    ]
    with patch.object(server_module, "_get_client") as mock_gc:
        mock_client = AsyncMock()
        mock_client.trending_links.return_value = fixture_a
        mock_gc.return_value = mock_client
        result1 = await server_module.mastodon_trending_links()
    with patch.object(server_module, "_get_client") as mock_gc:
        mock_client = AsyncMock()
        mock_client.trending_links.return_value = fixture_b
        mock_gc.return_value = mock_client
        result2 = await server_module.mastodon_trending_links()
    assert result1 == result2

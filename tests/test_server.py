"""Tests for mastodon_blade_mcp.server -- MCP tool integration tests."""

from __future__ import annotations

import json
import re as _re
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
# Tool registration
# ---------------------------------------------------------------------------


class TestToolRegistration:
    @pytest.mark.asyncio
    async def test_all_45_tools_registered(self) -> None:
        """Verify all 45 tools are registered with the MCP server."""
        tools = await server_module.mcp.list_tools()
        tool_names = [t.name for t in tools]
        assert len(tool_names) >= 45, f"Expected 45 tools, found {len(tool_names)}: {tool_names}"

        # Verify specific tool names exist
        expected_tools = [
            "mastodon_info",
            "mastodon_verify",
            "mastodon_timeline_home",
            "mastodon_timeline_public",
            "mastodon_timeline_local",
            "mastodon_timeline_hashtag",
            "mastodon_timeline_list",
            "mastodon_status",
            "mastodon_context",
            "mastodon_search",
            "mastodon_account",
            "mastodon_account_statuses",
            "mastodon_relationships",
            "mastodon_followers",
            "mastodon_following",
            "mastodon_notifications",
            "mastodon_trending_tags",
            "mastodon_trending_statuses",
            "mastodon_trending_links",
            "mastodon_bookmarks",
            "mastodon_favourites",
            "mastodon_lists",
            "mastodon_list_accounts",
            "mastodon_conversations",
            "mastodon_filters",
            "mastodon_post",
            "mastodon_reply",
            "mastodon_edit",
            "mastodon_delete",
            "mastodon_favourite",
            "mastodon_unfavourite",
            "mastodon_boost",
            "mastodon_unboost",
            "mastodon_bookmark",
            "mastodon_unbookmark",
            "mastodon_pin",
            "mastodon_unpin",
            "mastodon_follow",
            "mastodon_unfollow",
            "mastodon_block",
            "mastodon_unblock",
            "mastodon_mute",
            "mastodon_unmute",
            "mastodon_dismiss_notification",
            "mastodon_media_upload",
        ]
        for tool_name in expected_tools:
            assert tool_name in tool_names, f"Missing tool: {tool_name}"


# ---------------------------------------------------------------------------
# Read tools (no gate)
# ---------------------------------------------------------------------------


class TestMastodonInfo:
    @pytest.mark.asyncio
    async def test_returns_info(self, mastodon_env: None) -> None:
        with patch.object(server_module, "_get_client") as mock_gc:
            mock_client = AsyncMock()
            mock_client.instance_info.return_value = {
                "title": "Mastodon Social",
                "version": "4.2.0",
                "domain": "mastodon.social",
            }
            # get_rate_status is a sync method, not async
            mock_client.get_rate_status = lambda instance=None: "rate_limit=300/300 reset_in=0s"
            mock_gc.return_value = mock_client
            result = await server_module.mastodon_info()
            assert "Mastodon Social" in result
            assert "write_gate=" in result


class TestMastodonVerify:
    @pytest.mark.asyncio
    async def test_returns_user(self, mastodon_env: None) -> None:
        with patch.object(server_module, "_get_client") as mock_gc:
            mock_client = AsyncMock()
            mock_client.verify_credentials.return_value = make_account()
            mock_gc.return_value = mock_client
            result = await server_module.mastodon_verify()
            assert "@user@mastodon.social" in result


class TestMastodonTimelineHome:
    @pytest.mark.asyncio
    async def test_returns_statuses(self, mastodon_env: None) -> None:
        with patch.object(server_module, "_get_client") as mock_gc:
            mock_client = AsyncMock()
            mock_client.timeline_home_paginated.return_value = ([make_status()], None)
            mock_gc.return_value = mock_client
            result = await server_module.mastodon_timeline_home()
            assert "Hello world!" in result

    @pytest.mark.asyncio
    async def test_error_handling(self, mastodon_env: None) -> None:
        from mastodon_blade_mcp.client import MastodonError

        with patch.object(server_module, "_get_client") as mock_gc:
            mock_client = AsyncMock()
            mock_client.timeline_home_paginated.side_effect = MastodonError("test error")
            mock_gc.return_value = mock_client
            result = await server_module.mastodon_timeline_home()
            assert "Error:" in result


class TestMastodonStatus:
    @pytest.mark.asyncio
    async def test_returns_status(self, mastodon_env: None) -> None:
        with patch.object(server_module, "_get_client") as mock_gc:
            mock_client = AsyncMock()
            mock_client.get_status.return_value = make_status()
            mock_gc.return_value = mock_client
            result = await server_module.mastodon_status("109876543210")
            assert "109876543210" in result

    @pytest.mark.asyncio
    async def test_not_found(self, mastodon_env: None) -> None:
        from mastodon_blade_mcp.client import NotFoundError

        with patch.object(server_module, "_get_client") as mock_gc:
            mock_client = AsyncMock()
            mock_client.get_status.side_effect = NotFoundError("not found")
            mock_gc.return_value = mock_client
            result = await server_module.mastodon_status("nonexistent")
            assert "Error:" in result


class TestMastodonSearch:
    @pytest.mark.asyncio
    async def test_search(self, mastodon_env: None) -> None:
        with patch.object(server_module, "_get_client") as mock_gc:
            mock_client = AsyncMock()
            mock_client.search_paginated.return_value = (
                {
                    "accounts": [make_account()],
                    "statuses": [],
                    "hashtags": [],
                },
                None,
            )
            mock_gc.return_value = mock_client
            result = await server_module.mastodon_search("test")
            assert "Accounts" in result


class TestMastodonContext:
    @pytest.mark.asyncio
    async def test_returns_context(self, mastodon_env: None) -> None:
        with patch.object(server_module, "_get_client") as mock_gc:
            mock_client = AsyncMock()
            mock_client.get_context.return_value = {
                "ancestors": [make_status(status_id="anc-1")],
                "descendants": [make_status(status_id="desc-1")],
            }
            mock_gc.return_value = mock_client
            result = await server_module.mastodon_context("test-id")
            assert "Ancestors" in result
            assert "Descendants" in result


class TestMastodonNotifications:
    @pytest.mark.asyncio
    async def test_returns_notifications(self, mastodon_env: None) -> None:
        with patch.object(server_module, "_get_client") as mock_gc:
            mock_client = AsyncMock()
            mock_client.get_notifications_paginated.return_value = ([make_notification()], None)
            mock_gc.return_value = mock_client
            result = await server_module.mastodon_notifications()
            assert "mention" in result


class TestMastodonRelationships:
    @pytest.mark.asyncio
    async def test_returns_relationships(self, mastodon_env: None) -> None:
        with patch.object(server_module, "_get_client") as mock_gc:
            mock_client = AsyncMock()
            mock_client.get_relationships.return_value = [make_relationship()]
            mock_gc.return_value = mock_client
            result = await server_module.mastodon_relationships(["12345"])
            assert "following" in result


class TestMastodonTrendingTags:
    @pytest.mark.asyncio
    async def test_returns_tags(self, mastodon_env: None) -> None:
        with patch.object(server_module, "_get_client") as mock_gc:
            mock_client = AsyncMock()
            mock_client.trending_tags.return_value = [make_trending_tag()]
            mock_gc.return_value = mock_client
            result = await server_module.mastodon_trending_tags()
            assert "#python" in result


class TestMastodonBookmarks:
    @pytest.mark.asyncio
    async def test_returns_bookmarks(self, mastodon_env: None) -> None:
        with patch.object(server_module, "_get_client") as mock_gc:
            mock_client = AsyncMock()
            mock_client.get_bookmarks.return_value = [make_status()]
            mock_gc.return_value = mock_client
            result = await server_module.mastodon_bookmarks()
            assert "Hello world!" in result


class TestMastodonLists:
    @pytest.mark.asyncio
    async def test_returns_lists(self, mastodon_env: None) -> None:
        with patch.object(server_module, "_get_client") as mock_gc:
            mock_client = AsyncMock()
            mock_client.get_lists.return_value = [make_list_entry()]
            mock_gc.return_value = mock_client
            result = await server_module.mastodon_lists()
            assert "Tech News" in result


class TestMastodonConversations:
    @pytest.mark.asyncio
    async def test_returns_conversations(self, mastodon_env: None) -> None:
        with patch.object(server_module, "_get_client") as mock_gc:
            mock_client = AsyncMock()
            mock_client.get_conversations.return_value = [make_conversation()]
            mock_gc.return_value = mock_client
            result = await server_module.mastodon_conversations()
            assert "conv-1" in result


class TestMastodonFilters:
    @pytest.mark.asyncio
    async def test_returns_filters(self, mastodon_env: None) -> None:
        with patch.object(server_module, "_get_client") as mock_gc:
            mock_client = AsyncMock()
            mock_client.get_filters.return_value = [make_filter_entry()]
            mock_gc.return_value = mock_client
            result = await server_module.mastodon_filters()
            assert "Spoilers" in result


# ---------------------------------------------------------------------------
# Write-gated tools
# ---------------------------------------------------------------------------


class TestMastodonPost:
    @pytest.mark.asyncio
    async def test_blocked_without_write(self, mastodon_env: None) -> None:
        result = await server_module.mastodon_post("Hello!")
        assert "disabled" in result.lower()

    @pytest.mark.asyncio
    async def test_succeeds_with_write(self, mastodon_env_write: None) -> None:
        with patch.object(server_module, "_get_client") as mock_gc:
            mock_client = AsyncMock()
            mock_client.post_status.return_value = make_status(content="<p>Hello!</p>")
            mock_gc.return_value = mock_client
            result = await server_module.mastodon_post("Hello!")
            assert "Posted:" in result


class TestMastodonReply:
    @pytest.mark.asyncio
    async def test_blocked_without_write(self, mastodon_env: None) -> None:
        result = await server_module.mastodon_reply("123", "Reply text")
        assert "disabled" in result.lower()

    @pytest.mark.asyncio
    async def test_succeeds_with_write(self, mastodon_env_write: None) -> None:
        with patch.object(server_module, "_get_client") as mock_gc:
            mock_client = AsyncMock()
            mock_client.post_status.return_value = make_status(content="<p>Reply</p>")
            mock_gc.return_value = mock_client
            result = await server_module.mastodon_reply("123", "Reply text")
            assert "Replied:" in result


class TestMastodonFavourite:
    @pytest.mark.asyncio
    async def test_blocked_without_write(self, mastodon_env: None) -> None:
        result = await server_module.mastodon_favourite("123")
        assert "disabled" in result.lower()

    @pytest.mark.asyncio
    async def test_succeeds_with_write(self, mastodon_env_write: None) -> None:
        with patch.object(server_module, "_get_client") as mock_gc:
            mock_client = AsyncMock()
            mock_client.favourite_status.return_value = make_status()
            mock_gc.return_value = mock_client
            result = await server_module.mastodon_favourite("123")
            assert "Favourited:" in result


class TestMastodonBoost:
    @pytest.mark.asyncio
    async def test_blocked_without_write(self, mastodon_env: None) -> None:
        result = await server_module.mastodon_boost("123")
        assert "disabled" in result.lower()

    @pytest.mark.asyncio
    async def test_succeeds_with_write(self, mastodon_env_write: None) -> None:
        with patch.object(server_module, "_get_client") as mock_gc:
            mock_client = AsyncMock()
            mock_client.reblog_status.return_value = make_status()
            mock_gc.return_value = mock_client
            result = await server_module.mastodon_boost("123")
            assert "Boosted:" in result


class TestMastodonFollow:
    @pytest.mark.asyncio
    async def test_blocked_without_write(self, mastodon_env: None) -> None:
        result = await server_module.mastodon_follow("12345")
        assert "disabled" in result.lower()

    @pytest.mark.asyncio
    async def test_succeeds_with_write(self, mastodon_env_write: None) -> None:
        with patch.object(server_module, "_get_client") as mock_gc:
            mock_client = AsyncMock()
            mock_client.follow_account.return_value = {"following": True, "requested": False}
            mock_gc.return_value = mock_client
            result = await server_module.mastodon_follow("12345")
            assert "following" in result


# ---------------------------------------------------------------------------
# Confirm-gated tools
# ---------------------------------------------------------------------------


class TestMastodonDelete:
    @pytest.mark.asyncio
    async def test_blocked_without_write(self, mastodon_env: None) -> None:
        result = await server_module.mastodon_delete("123")
        assert "disabled" in result.lower()

    @pytest.mark.asyncio
    async def test_blocked_without_confirm(self, mastodon_env_write: None) -> None:
        result = await server_module.mastodon_delete("123")
        assert "confirm" in result.lower()

    @pytest.mark.asyncio
    async def test_succeeds_with_confirm(self, mastodon_env_write: None) -> None:
        with patch.object(server_module, "_get_client") as mock_gc:
            mock_client = AsyncMock()
            mock_client.delete_status.return_value = {"id": "123"}
            mock_gc.return_value = mock_client
            result = await server_module.mastodon_delete("123", confirm=True)
            assert "Deleted" in result


class TestMastodonBlock:
    @pytest.mark.asyncio
    async def test_blocked_without_write(self, mastodon_env: None) -> None:
        result = await server_module.mastodon_block("12345")
        assert "disabled" in result.lower()

    @pytest.mark.asyncio
    async def test_blocked_without_confirm(self, mastodon_env_write: None) -> None:
        result = await server_module.mastodon_block("12345")
        assert "confirm" in result.lower()

    @pytest.mark.asyncio
    async def test_succeeds_with_confirm(self, mastodon_env_write: None) -> None:
        with patch.object(server_module, "_get_client") as mock_gc:
            mock_client = AsyncMock()
            mock_client.block_account.return_value = {"id": "12345", "blocking": True}
            mock_gc.return_value = mock_client
            result = await server_module.mastodon_block("12345", confirm=True)
            assert "Blocked" in result


class TestMastodonMute:
    @pytest.mark.asyncio
    async def test_blocked_without_write(self, mastodon_env: None) -> None:
        result = await server_module.mastodon_mute("12345")
        assert "disabled" in result.lower()

    @pytest.mark.asyncio
    async def test_blocked_without_confirm(self, mastodon_env_write: None) -> None:
        result = await server_module.mastodon_mute("12345")
        assert "confirm" in result.lower()

    @pytest.mark.asyncio
    async def test_succeeds_with_confirm(self, mastodon_env_write: None) -> None:
        with patch.object(server_module, "_get_client") as mock_gc:
            mock_client = AsyncMock()
            mock_client.mute_account.return_value = {"id": "12345", "muting": True}
            mock_gc.return_value = mock_client
            result = await server_module.mastodon_mute("12345", confirm=True, duration=3600)
            assert "Muted" in result
            assert "3600s" in result


class TestMastodonDismissNotification:
    @pytest.mark.asyncio
    async def test_blocked_without_write(self, mastodon_env: None) -> None:
        result = await server_module.mastodon_dismiss_notification("99999")
        assert "disabled" in result.lower()

    @pytest.mark.asyncio
    async def test_succeeds_with_write(self, mastodon_env_write: None) -> None:
        with patch.object(server_module, "_get_client") as mock_gc:
            mock_client = AsyncMock()
            mock_client.dismiss_notification.return_value = None
            mock_gc.return_value = mock_client
            result = await server_module.mastodon_dismiss_notification("99999")
            assert "Dismissed" in result


class TestMastodonMediaUpload:
    @pytest.mark.asyncio
    async def test_blocked_without_write(self, mastodon_env: None) -> None:
        result = await server_module.mastodon_media_upload("/tmp/test.jpg")
        assert "disabled" in result.lower()

    @pytest.mark.asyncio
    async def test_succeeds_with_write(self, mastodon_env_write: None) -> None:
        with patch.object(server_module, "_get_client") as mock_gc:
            mock_client = AsyncMock()
            mock_client.upload_media.return_value = {
                "id": "media-1",
                "type": "image",
                "url": "https://mastodon.social/media/test.jpg",
                "description": "A test image",
            }
            mock_gc.return_value = mock_client
            result = await server_module.mastodon_media_upload("/tmp/test.jpg", description="A test image")
            assert "id=media-1" in result


# ===========================================================================
# DD-338 A.1 -- scope + _meta envelope tests
# ===========================================================================


def _parse_meta(result: str) -> dict:
    """Extract the trailing _meta JSON block from a tool return string."""
    match = _re.search(r"\n\n_meta: (\{.*\})$", result)
    assert match is not None, f"No _meta block found in:\n{result}"
    return json.loads(match.group(1))


# -- mastodon_timeline_home ------------------------------------------------


class TestTimelineHomeScope:
    @pytest.mark.asyncio
    async def test_happy_path_scope_personal_resolves(
        self, mastodon_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("MASTODON_PERSONAL_LIST_ID", "list-42")
        with patch.object(server_module, "_get_client") as mock_gc:
            mock_client = AsyncMock()
            mock_client.timeline_list_paginated.return_value = ([make_status()], None)
            mock_gc.return_value = mock_client
            result = await server_module.mastodon_timeline_home(scope="personal")
            mock_client.timeline_list_paginated.assert_awaited_once()
            assert "Hello world!" in result
            meta = _parse_meta(result)
            assert "scope=personal" in meta["filtered_by"]
            assert meta["redactions"] == []

    @pytest.mark.asyncio
    async def test_happy_path_scope_public_passthrough(self, mastodon_env: None) -> None:
        with patch.object(server_module, "_get_client") as mock_gc:
            mock_client = AsyncMock()
            mock_client.timeline_home_paginated.return_value = ([make_status()], None)
            mock_gc.return_value = mock_client
            result = await server_module.mastodon_timeline_home(scope="public")
            meta = _parse_meta(result)
            assert not any(f.startswith("scope=") for f in meta["filtered_by"])
            assert meta["redactions"] == []

    @pytest.mark.asyncio
    async def test_degradation_unconfigured_list(self, mastodon_env: None) -> None:
        with patch.object(server_module, "_get_client") as mock_gc:
            mock_client = AsyncMock()
            mock_client.timeline_home_paginated.return_value = ([make_status()], None)
            mock_gc.return_value = mock_client
            result = await server_module.mastodon_timeline_home(scope="personal")
            mock_client.timeline_home_paginated.assert_awaited_once()
            meta = _parse_meta(result)
            assert "scope=personal_unconfigured" in meta["redactions"]

    @pytest.mark.asyncio
    async def test_rejection_unknown_scope(self, mastodon_env: None) -> None:
        result = await server_module.mastodon_timeline_home(scope="invalid")
        assert "Error:" in result
        assert "public" in result and "personal" in result

    @pytest.mark.asyncio
    async def test_back_compat_omitted_scope(self, mastodon_env: None) -> None:
        with patch.object(server_module, "_get_client") as mock_gc:
            mock_client = AsyncMock()
            mock_client.timeline_home_paginated.return_value = ([make_status()], None)
            mock_gc.return_value = mock_client
            result = await server_module.mastodon_timeline_home()
            assert "Hello world!" in result
            meta = _parse_meta(result)
            assert not any(f.startswith("scope=") for f in meta["filtered_by"])

    @pytest.mark.asyncio
    async def test_cursor_passthrough(self, mastodon_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MASTODON_PERSONAL_LIST_ID", "list-42")
        with patch.object(server_module, "_get_client") as mock_gc:
            mock_client = AsyncMock()
            mock_client.timeline_list_paginated.return_value = ([], "next-9999")
            mock_gc.return_value = mock_client
            result = await server_module.mastodon_timeline_home(scope="personal", max_id="abc")
            mock_client.timeline_list_paginated.assert_awaited_once_with("list-42", 20, "abc", None)
            meta = _parse_meta(result)
            assert meta["next_cursor"] == "next-9999"

    @pytest.mark.asyncio
    async def test_meta_envelope_shape(self, mastodon_env: None) -> None:
        with patch.object(server_module, "_get_client") as mock_gc:
            mock_client = AsyncMock()
            mock_client.timeline_home_paginated.return_value = ([make_status()], None)
            mock_gc.return_value = mock_client
            result = await server_module.mastodon_timeline_home()
            assert result.endswith(_re.search(r"_meta: \{.*\}$", result).group(0))
            meta = _parse_meta(result)
            for key in ("matched_total", "returned", "filtered_by", "redactions", "next_cursor", "latency_ms"):
                assert key in meta
            assert isinstance(meta["matched_total"], int)
            assert isinstance(meta["returned"], int)
            assert isinstance(meta["filtered_by"], list)
            assert isinstance(meta["redactions"], list)
            assert isinstance(meta["latency_ms"], int)


# -- mastodon_search -------------------------------------------------------


class TestSearchScope:
    @pytest.mark.asyncio
    async def test_happy_path_scope_personal_resolves(
        self, mastodon_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("MASTODON_PERSONAL_LIST_ID", "list-42")
        with patch.object(server_module, "_get_client") as mock_gc:
            mock_client = AsyncMock()
            in_list = make_status(status_id="s1", acct="alice@mastodon.social")
            in_list["account"]["id"] = "11"
            out_of_list = make_status(status_id="s2", acct="bob@mastodon.social")
            out_of_list["account"]["id"] = "22"
            mock_client.search_paginated.return_value = (
                {"accounts": [], "statuses": [in_list, out_of_list], "hashtags": []},
                None,
            )
            mock_client.list_accounts_cached.return_value = {"11"}
            mock_gc.return_value = mock_client
            result = await server_module.mastodon_search("test", scope="personal")
            meta = _parse_meta(result)
            assert "scope=personal:statuses_only" in meta["filtered_by"]
            assert meta["matched_total"] == 2
            assert meta["returned"] == 1

    @pytest.mark.asyncio
    async def test_happy_path_scope_public_passthrough(self, mastodon_env: None) -> None:
        with patch.object(server_module, "_get_client") as mock_gc:
            mock_client = AsyncMock()
            mock_client.search_paginated.return_value = (
                {"accounts": [make_account()], "statuses": [], "hashtags": []},
                None,
            )
            mock_gc.return_value = mock_client
            result = await server_module.mastodon_search("test", scope="public")
            meta = _parse_meta(result)
            assert not any(f.startswith("scope=") for f in meta["filtered_by"])

    @pytest.mark.asyncio
    async def test_degradation_unconfigured_list(self, mastodon_env: None) -> None:
        with patch.object(server_module, "_get_client") as mock_gc:
            mock_client = AsyncMock()
            mock_client.search_paginated.return_value = (
                {"accounts": [], "statuses": [make_status()], "hashtags": []},
                None,
            )
            mock_gc.return_value = mock_client
            result = await server_module.mastodon_search("test", scope="family")
            meta = _parse_meta(result)
            assert "scope=family_unconfigured" in meta["redactions"]

    @pytest.mark.asyncio
    async def test_rejection_unknown_scope(self, mastodon_env: None) -> None:
        result = await server_module.mastodon_search("test", scope="invalid")
        assert "Error:" in result

    @pytest.mark.asyncio
    async def test_back_compat_omitted_scope(self, mastodon_env: None) -> None:
        with patch.object(server_module, "_get_client") as mock_gc:
            mock_client = AsyncMock()
            mock_client.search_paginated.return_value = (
                {"accounts": [make_account()], "statuses": [], "hashtags": []},
                None,
            )
            mock_gc.return_value = mock_client
            result = await server_module.mastodon_search("test")
            meta = _parse_meta(result)
            assert not any(f.startswith("scope=") for f in meta["filtered_by"])

    @pytest.mark.asyncio
    async def test_cursor_passthrough(self, mastodon_env: None) -> None:
        with patch.object(server_module, "_get_client") as mock_gc:
            mock_client = AsyncMock()
            mock_client.search_paginated.return_value = (
                {"accounts": [], "statuses": [], "hashtags": []},
                None,
            )
            mock_gc.return_value = mock_client
            await server_module.mastodon_search("test", type="statuses", limit=15)
            mock_client.search_paginated.assert_awaited_once_with("test", "statuses", 15, None)

    @pytest.mark.asyncio
    async def test_meta_envelope_shape(self, mastodon_env: None) -> None:
        with patch.object(server_module, "_get_client") as mock_gc:
            mock_client = AsyncMock()
            mock_client.search_paginated.return_value = (
                {"accounts": [], "statuses": [], "hashtags": []},
                None,
            )
            mock_gc.return_value = mock_client
            result = await server_module.mastodon_search("test")
            meta = _parse_meta(result)
            for key in ("matched_total", "returned", "filtered_by", "redactions", "next_cursor", "latency_ms"):
                assert key in meta

    @pytest.mark.asyncio
    async def test_list_membership_unavailable(self, mastodon_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
        from mastodon_blade_mcp.client import MastodonError

        monkeypatch.setenv("MASTODON_PERSONAL_LIST_ID", "list-42")
        with patch.object(server_module, "_get_client") as mock_gc:
            mock_client = AsyncMock()
            mock_client.list_accounts_cached.side_effect = MastodonError("list fetch failed")
            mock_client.search_paginated.return_value = (
                {"accounts": [], "statuses": [make_status()], "hashtags": []},
                None,
            )
            mock_gc.return_value = mock_client
            result = await server_module.mastodon_search("test", scope="personal")
            meta = _parse_meta(result)
            assert "list_membership_unavailable" in meta["redactions"]


# -- mastodon_notifications ------------------------------------------------


class TestNotificationsScope:
    @pytest.mark.asyncio
    async def test_happy_path_scope_personal_resolves(
        self, mastodon_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("MASTODON_PERSONAL_LIST_ID", "list-42")
        with patch.object(server_module, "_get_client") as mock_gc:
            mock_client = AsyncMock()
            in_list = make_notification(notification_id="n1", acct="alice@mastodon.social")
            in_list["account"]["id"] = "11"
            out_of_list = make_notification(notification_id="n2", acct="bob@mastodon.social")
            out_of_list["account"]["id"] = "22"
            mock_client.get_notifications_paginated.return_value = ([in_list, out_of_list], None)
            mock_client.list_accounts_cached.return_value = {"11"}
            mock_gc.return_value = mock_client
            result = await server_module.mastodon_notifications(scope="personal")
            meta = _parse_meta(result)
            assert meta["matched_total"] == 2
            assert meta["returned"] == 1
            assert "scope=personal" in meta["filtered_by"]

    @pytest.mark.asyncio
    async def test_happy_path_scope_public_passthrough(self, mastodon_env: None) -> None:
        with patch.object(server_module, "_get_client") as mock_gc:
            mock_client = AsyncMock()
            mock_client.get_notifications_paginated.return_value = ([make_notification()], None)
            mock_gc.return_value = mock_client
            result = await server_module.mastodon_notifications(scope="public")
            meta = _parse_meta(result)
            assert not any(f.startswith("scope=") for f in meta["filtered_by"])

    @pytest.mark.asyncio
    async def test_degradation_unconfigured_list(self, mastodon_env: None) -> None:
        with patch.object(server_module, "_get_client") as mock_gc:
            mock_client = AsyncMock()
            mock_client.get_notifications_paginated.return_value = ([make_notification()], None)
            mock_gc.return_value = mock_client
            result = await server_module.mastodon_notifications(scope="work")
            meta = _parse_meta(result)
            assert "scope=work_unconfigured" in meta["redactions"]

    @pytest.mark.asyncio
    async def test_rejection_unknown_scope(self, mastodon_env: None) -> None:
        result = await server_module.mastodon_notifications(scope="invalid")
        assert "Error:" in result

    @pytest.mark.asyncio
    async def test_back_compat_omitted_scope(self, mastodon_env: None) -> None:
        with patch.object(server_module, "_get_client") as mock_gc:
            mock_client = AsyncMock()
            mock_client.get_notifications_paginated.return_value = ([make_notification()], None)
            mock_gc.return_value = mock_client
            result = await server_module.mastodon_notifications()
            meta = _parse_meta(result)
            assert not any(f.startswith("scope=") for f in meta["filtered_by"])

    @pytest.mark.asyncio
    async def test_cursor_passthrough(self, mastodon_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MASTODON_PERSONAL_LIST_ID", "list-42")
        with patch.object(server_module, "_get_client") as mock_gc:
            mock_client = AsyncMock()
            mock_client.get_notifications_paginated.return_value = ([], "n-cursor")
            mock_client.list_accounts_cached.return_value = set()
            mock_gc.return_value = mock_client
            await server_module.mastodon_notifications(scope="personal", max_id="abc", limit=15)
            mock_client.get_notifications_paginated.assert_awaited_once_with(None, 15, "abc", None)

    @pytest.mark.asyncio
    async def test_meta_envelope_shape(self, mastodon_env: None) -> None:
        with patch.object(server_module, "_get_client") as mock_gc:
            mock_client = AsyncMock()
            mock_client.get_notifications_paginated.return_value = ([], None)
            mock_gc.return_value = mock_client
            result = await server_module.mastodon_notifications()
            meta = _parse_meta(result)
            for key in ("matched_total", "returned", "filtered_by", "redactions", "next_cursor", "latency_ms"):
                assert key in meta


# -- mastodon_account_statuses ---------------------------------------------


class TestAccountStatusesScope:
    @pytest.mark.asyncio
    async def test_happy_path_scope_personal_resolves(
        self, mastodon_env: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("MASTODON_PERSONAL_LIST_ID", "list-42")
        with patch.object(server_module, "_get_client") as mock_gc:
            mock_client = AsyncMock()
            mock_client.list_accounts_cached.return_value = {"11"}
            mock_client.get_account_statuses_paginated.return_value = ([make_status()], None)
            mock_gc.return_value = mock_client
            result = await server_module.mastodon_account_statuses("11", scope="personal")
            assert "Hello world!" in result
            meta = _parse_meta(result)
            assert "scope=personal" in meta["filtered_by"]
            assert meta["redactions"] == []

    @pytest.mark.asyncio
    async def test_happy_path_scope_public_passthrough(self, mastodon_env: None) -> None:
        with patch.object(server_module, "_get_client") as mock_gc:
            mock_client = AsyncMock()
            mock_client.get_account_statuses_paginated.return_value = ([make_status()], None)
            mock_gc.return_value = mock_client
            result = await server_module.mastodon_account_statuses("11", scope="public")
            meta = _parse_meta(result)
            assert not any(f.startswith("scope=") for f in meta["filtered_by"])

    @pytest.mark.asyncio
    async def test_degradation_unconfigured_list(self, mastodon_env: None) -> None:
        with patch.object(server_module, "_get_client") as mock_gc:
            mock_client = AsyncMock()
            mock_client.get_account_statuses_paginated.return_value = ([make_status()], None)
            mock_gc.return_value = mock_client
            result = await server_module.mastodon_account_statuses("11", scope="family")
            meta = _parse_meta(result)
            assert "scope=family_unconfigured" in meta["redactions"]

    @pytest.mark.asyncio
    async def test_rejection_unknown_scope(self, mastodon_env: None) -> None:
        result = await server_module.mastodon_account_statuses("11", scope="invalid")
        assert "Error:" in result

    @pytest.mark.asyncio
    async def test_back_compat_omitted_scope(self, mastodon_env: None) -> None:
        with patch.object(server_module, "_get_client") as mock_gc:
            mock_client = AsyncMock()
            mock_client.get_account_statuses_paginated.return_value = ([make_status()], None)
            mock_gc.return_value = mock_client
            result = await server_module.mastodon_account_statuses("11")
            meta = _parse_meta(result)
            assert not any(f.startswith("scope=") for f in meta["filtered_by"])

    @pytest.mark.asyncio
    async def test_cursor_passthrough(self, mastodon_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MASTODON_PERSONAL_LIST_ID", "list-42")
        with patch.object(server_module, "_get_client") as mock_gc:
            mock_client = AsyncMock()
            mock_client.list_accounts_cached.return_value = {"11"}
            mock_client.get_account_statuses_paginated.return_value = ([], "cur-1")
            mock_gc.return_value = mock_client
            await server_module.mastodon_account_statuses("11", scope="personal", max_id="abc")
            mock_client.get_account_statuses_paginated.assert_awaited_once_with(
                "11", 20, "abc", False, False, False, None
            )

    @pytest.mark.asyncio
    async def test_meta_envelope_shape(self, mastodon_env: None) -> None:
        with patch.object(server_module, "_get_client") as mock_gc:
            mock_client = AsyncMock()
            mock_client.get_account_statuses_paginated.return_value = ([], None)
            mock_gc.return_value = mock_client
            result = await server_module.mastodon_account_statuses("11")
            meta = _parse_meta(result)
            for key in ("matched_total", "returned", "filtered_by", "redactions", "next_cursor", "latency_ms"):
                assert key in meta

    @pytest.mark.asyncio
    async def test_membership_precondition_fail(self, mastodon_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MASTODON_FAMILY_LIST_ID", "list-99")
        with patch.object(server_module, "_get_client") as mock_gc:
            mock_client = AsyncMock()
            mock_client.list_accounts_cached.return_value = {"11"}
            mock_gc.return_value = mock_client
            result = await server_module.mastodon_account_statuses("22", scope="family")
            assert "Error: account_id not in scope=family list" in result
            meta = _parse_meta(result)
            assert "account_outside_scope" in meta["redactions"]
            # Should NOT have fetched statuses
            mock_client.get_account_statuses_paginated.assert_not_awaited()


# -- conformance stub ------------------------------------------------------


class TestPerInstanceEnvVarSuffix:
    """OQ-1: per-instance env var suffix uppercases + replaces non-alphanumeric with _."""

    @pytest.mark.asyncio
    async def test_per_instance_suffix_wins(self, mastodon_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MASTODON_PERSONAL_LIST_ID", "fallback-list")
        monkeypatch.setenv("MASTODON_PERSONAL_LIST_ID_HACHYDERM", "instance-list")
        with patch.object(server_module, "_get_client") as mock_gc:
            mock_client = AsyncMock()
            mock_client.timeline_list_paginated.return_value = ([], None)
            mock_gc.return_value = mock_client
            await server_module.mastodon_timeline_home(scope="personal", instance="hachyderm")
            mock_client.timeline_list_paginated.assert_awaited_once_with("instance-list", 20, None, "hachyderm")


# ===========================================================================
# DD-338 C W4 -- _meta envelope shape + filtered_by content tests
# ===========================================================================


_W4_REQUIRED_META_KEYS = ("matched_total", "returned", "filtered_by", "redactions", "next_cursor", "latency_ms")


def _assert_meta_shape(meta: dict) -> None:
    """Assert the canonical _meta envelope shape for a W4-promoted tool."""
    for key in _W4_REQUIRED_META_KEYS:
        assert key in meta, f"missing _meta key: {key}"
    assert isinstance(meta["matched_total"], int)
    assert isinstance(meta["returned"], int)
    assert isinstance(meta["filtered_by"], list)
    assert isinstance(meta["redactions"], list)
    assert isinstance(meta["latency_ms"], int)


class TestW4MastodonTimelinePublic:
    @pytest.mark.asyncio
    async def test_meta_envelope_shape(self, mastodon_env: None) -> None:
        with patch.object(server_module, "_get_client") as mock_gc:
            mock_client = AsyncMock()
            mock_client.timeline_public.return_value = [make_status()]
            mock_gc.return_value = mock_client
            result = await server_module.mastodon_timeline_public()
            meta = _parse_meta(result)
            _assert_meta_shape(meta)

    @pytest.mark.asyncio
    async def test_filtered_by_content(self, mastodon_env: None) -> None:
        with patch.object(server_module, "_get_client") as mock_gc:
            mock_client = AsyncMock()
            mock_client.timeline_public.return_value = [make_status()]
            mock_gc.return_value = mock_client
            result = await server_module.mastodon_timeline_public(local=True, limit=10, max_id="999")
            meta = _parse_meta(result)
            assert "local=true" in meta["filtered_by"]
            assert "limit=10" in meta["filtered_by"]
            assert "max_id=999" in meta["filtered_by"]
            assert "sorted_by=id_desc" in meta["filtered_by"]
            assert meta["filtered_by"] == sorted(meta["filtered_by"])


class TestW4MastodonTimelineLocal:
    @pytest.mark.asyncio
    async def test_meta_envelope_shape(self, mastodon_env: None) -> None:
        with patch.object(server_module, "_get_client") as mock_gc:
            mock_client = AsyncMock()
            mock_client.timeline_public.return_value = [make_status()]
            mock_gc.return_value = mock_client
            result = await server_module.mastodon_timeline_local()
            meta = _parse_meta(result)
            _assert_meta_shape(meta)

    @pytest.mark.asyncio
    async def test_filtered_by_content(self, mastodon_env: None) -> None:
        with patch.object(server_module, "_get_client") as mock_gc:
            mock_client = AsyncMock()
            mock_client.timeline_public.return_value = [make_status()]
            mock_gc.return_value = mock_client
            result = await server_module.mastodon_timeline_local(limit=15)
            meta = _parse_meta(result)
            assert "local=true" in meta["filtered_by"]
            assert "limit=15" in meta["filtered_by"]
            assert "sorted_by=id_desc" in meta["filtered_by"]


class TestW4MastodonTimelineHashtag:
    @pytest.mark.asyncio
    async def test_meta_envelope_shape(self, mastodon_env: None) -> None:
        with patch.object(server_module, "_get_client") as mock_gc:
            mock_client = AsyncMock()
            mock_client.timeline_hashtag.return_value = [make_status()]
            mock_gc.return_value = mock_client
            result = await server_module.mastodon_timeline_hashtag("python")
            meta = _parse_meta(result)
            _assert_meta_shape(meta)

    @pytest.mark.asyncio
    async def test_filtered_by_content(self, mastodon_env: None) -> None:
        with patch.object(server_module, "_get_client") as mock_gc:
            mock_client = AsyncMock()
            mock_client.timeline_hashtag.return_value = [make_status()]
            mock_gc.return_value = mock_client
            result = await server_module.mastodon_timeline_hashtag("rust", limit=5, local=True)
            meta = _parse_meta(result)
            assert "hashtag=rust" in meta["filtered_by"]
            assert "limit=5" in meta["filtered_by"]
            assert "local=true" in meta["filtered_by"]
            assert "sorted_by=id_desc" in meta["filtered_by"]


class TestW4MastodonTimelineList:
    @pytest.mark.asyncio
    async def test_meta_envelope_shape(self, mastodon_env: None) -> None:
        with patch.object(server_module, "_get_client") as mock_gc:
            mock_client = AsyncMock()
            mock_client.timeline_list.return_value = [make_status()]
            mock_gc.return_value = mock_client
            result = await server_module.mastodon_timeline_list("list-1")
            meta = _parse_meta(result)
            _assert_meta_shape(meta)

    @pytest.mark.asyncio
    async def test_filtered_by_content(self, mastodon_env: None) -> None:
        with patch.object(server_module, "_get_client") as mock_gc:
            mock_client = AsyncMock()
            mock_client.timeline_list.return_value = [make_status()]
            mock_gc.return_value = mock_client
            result = await server_module.mastodon_timeline_list("list-42", limit=30)
            meta = _parse_meta(result)
            assert "list_id=list-42" in meta["filtered_by"]
            assert "limit=30" in meta["filtered_by"]
            assert "sorted_by=id_desc" in meta["filtered_by"]


class TestW4MastodonContext:
    @pytest.mark.asyncio
    async def test_meta_envelope_shape(self, mastodon_env: None) -> None:
        with patch.object(server_module, "_get_client") as mock_gc:
            mock_client = AsyncMock()
            mock_client.get_context.return_value = {
                "ancestors": [make_status(status_id="anc-1")],
                "descendants": [make_status(status_id="desc-1")],
            }
            mock_gc.return_value = mock_client
            result = await server_module.mastodon_context("test-id")
            meta = _parse_meta(result)
            _assert_meta_shape(meta)

    @pytest.mark.asyncio
    async def test_filtered_by_content(self, mastodon_env: None) -> None:
        with patch.object(server_module, "_get_client") as mock_gc:
            mock_client = AsyncMock()
            mock_client.get_context.return_value = {"ancestors": [], "descendants": []}
            mock_gc.return_value = mock_client
            result = await server_module.mastodon_context("seed-42")
            meta = _parse_meta(result)
            assert "status_id=seed-42" in meta["filtered_by"]
            assert "sorted_by=id_desc" in meta["filtered_by"]

    @pytest.mark.asyncio
    async def test_sort_applied(self, mastodon_env: None) -> None:
        # OQ-6: confirm sort_by_id_desc is applied to each bucket.
        # Status format begins each line with `<id> | ...`.
        with patch.object(server_module, "_get_client") as mock_gc:
            mock_client = AsyncMock()
            mock_client.get_context.return_value = {
                "ancestors": [make_status(status_id="100"), make_status(status_id="200")],
                "descendants": [make_status(status_id="300"), make_status(status_id="400")],
            }
            mock_gc.return_value = mock_client
            result = await server_module.mastodon_context("seed")
            # newest-first within ancestors bucket: 200 before 100
            assert result.index("200 |") < result.index("100 |")
            # newest-first within descendants bucket: 400 before 300
            assert result.index("400 |") < result.index("300 |")


class TestW4MastodonRelationships:
    @pytest.mark.asyncio
    async def test_meta_envelope_shape(self, mastodon_env: None) -> None:
        with patch.object(server_module, "_get_client") as mock_gc:
            mock_client = AsyncMock()
            mock_client.get_relationships.return_value = [make_relationship()]
            mock_gc.return_value = mock_client
            result = await server_module.mastodon_relationships(["12345"])
            meta = _parse_meta(result)
            _assert_meta_shape(meta)

    @pytest.mark.asyncio
    async def test_filtered_by_content(self, mastodon_env: None) -> None:
        with patch.object(server_module, "_get_client") as mock_gc:
            mock_client = AsyncMock()
            mock_client.get_relationships.return_value = []
            mock_gc.return_value = mock_client
            result = await server_module.mastodon_relationships(["1", "2", "3"])
            meta = _parse_meta(result)
            assert "account_ids=3" in meta["filtered_by"]
            assert "sorted_by=id_asc" in meta["filtered_by"]

    @pytest.mark.asyncio
    async def test_sort_applied(self, mastodon_env: None) -> None:
        # OQ-6: confirm sort_by_id_asc is applied (id ascending).
        with patch.object(server_module, "_get_client") as mock_gc:
            mock_client = AsyncMock()
            mock_client.get_relationships.return_value = [
                make_relationship(account_id="300"),
                make_relationship(account_id="100"),
                make_relationship(account_id="200"),
            ]
            mock_gc.return_value = mock_client
            result = await server_module.mastodon_relationships(["100", "200", "300"])
            # ascending: 100 before 200 before 300
            i1 = result.index("100")
            i2 = result.index("200")
            i3 = result.index("300")
            assert i1 < i2 < i3


class TestW4MastodonFollowers:
    @pytest.mark.asyncio
    async def test_meta_envelope_shape(self, mastodon_env: None) -> None:
        with patch.object(server_module, "_get_client") as mock_gc:
            mock_client = AsyncMock()
            mock_client.get_followers.return_value = [make_account()]
            mock_gc.return_value = mock_client
            result = await server_module.mastodon_followers("12345")
            meta = _parse_meta(result)
            _assert_meta_shape(meta)

    @pytest.mark.asyncio
    async def test_filtered_by_content(self, mastodon_env: None) -> None:
        with patch.object(server_module, "_get_client") as mock_gc:
            mock_client = AsyncMock()
            mock_client.get_followers.return_value = []
            mock_gc.return_value = mock_client
            result = await server_module.mastodon_followers("acc-1", limit=80)
            meta = _parse_meta(result)
            assert "account_id=acc-1" in meta["filtered_by"]
            assert "limit=80" in meta["filtered_by"]
            assert "sorted_by=id_desc" in meta["filtered_by"]


class TestW4MastodonFollowing:
    @pytest.mark.asyncio
    async def test_meta_envelope_shape(self, mastodon_env: None) -> None:
        with patch.object(server_module, "_get_client") as mock_gc:
            mock_client = AsyncMock()
            mock_client.get_following.return_value = [make_account()]
            mock_gc.return_value = mock_client
            result = await server_module.mastodon_following("12345")
            meta = _parse_meta(result)
            _assert_meta_shape(meta)

    @pytest.mark.asyncio
    async def test_filtered_by_content(self, mastodon_env: None) -> None:
        with patch.object(server_module, "_get_client") as mock_gc:
            mock_client = AsyncMock()
            mock_client.get_following.return_value = []
            mock_gc.return_value = mock_client
            result = await server_module.mastodon_following("acc-2", limit=50)
            meta = _parse_meta(result)
            assert "account_id=acc-2" in meta["filtered_by"]
            assert "limit=50" in meta["filtered_by"]


class TestW4MastodonListAccounts:
    @pytest.mark.asyncio
    async def test_meta_envelope_shape(self, mastodon_env: None) -> None:
        with patch.object(server_module, "_get_client") as mock_gc:
            mock_client = AsyncMock()
            mock_client.get_list_accounts.return_value = [make_account()]
            mock_gc.return_value = mock_client
            result = await server_module.mastodon_list_accounts("list-1")
            meta = _parse_meta(result)
            _assert_meta_shape(meta)

    @pytest.mark.asyncio
    async def test_filtered_by_content(self, mastodon_env: None) -> None:
        with patch.object(server_module, "_get_client") as mock_gc:
            mock_client = AsyncMock()
            mock_client.get_list_accounts.return_value = []
            mock_gc.return_value = mock_client
            result = await server_module.mastodon_list_accounts("list-7", limit=60)
            meta = _parse_meta(result)
            assert "list_id=list-7" in meta["filtered_by"]
            assert "limit=60" in meta["filtered_by"]
            assert "sorted_by=id_desc" in meta["filtered_by"]


class TestW4MastodonTrendingTags:
    @pytest.mark.asyncio
    async def test_meta_envelope_shape(self, mastodon_env: None) -> None:
        with patch.object(server_module, "_get_client") as mock_gc:
            mock_client = AsyncMock()
            mock_client.trending_tags.return_value = [make_trending_tag()]
            mock_gc.return_value = mock_client
            result = await server_module.mastodon_trending_tags()
            meta = _parse_meta(result)
            _assert_meta_shape(meta)

    @pytest.mark.asyncio
    async def test_filtered_by_content(self, mastodon_env: None) -> None:
        with patch.object(server_module, "_get_client") as mock_gc:
            mock_client = AsyncMock()
            mock_client.trending_tags.return_value = []
            mock_gc.return_value = mock_client
            result = await server_module.mastodon_trending_tags(limit=25)
            meta = _parse_meta(result)
            assert "limit=25" in meta["filtered_by"]
            assert "sorted_by=server_rank;tie_name_asc" in meta["filtered_by"]


class TestW4MastodonTrendingStatuses:
    @pytest.mark.asyncio
    async def test_meta_envelope_shape(self, mastodon_env: None) -> None:
        with patch.object(server_module, "_get_client") as mock_gc:
            mock_client = AsyncMock()
            mock_client.trending_statuses.return_value = [make_status()]
            mock_gc.return_value = mock_client
            result = await server_module.mastodon_trending_statuses()
            meta = _parse_meta(result)
            _assert_meta_shape(meta)

    @pytest.mark.asyncio
    async def test_filtered_by_content(self, mastodon_env: None) -> None:
        with patch.object(server_module, "_get_client") as mock_gc:
            mock_client = AsyncMock()
            mock_client.trending_statuses.return_value = []
            mock_gc.return_value = mock_client
            result = await server_module.mastodon_trending_statuses(limit=15)
            meta = _parse_meta(result)
            assert "limit=15" in meta["filtered_by"]
            assert "sorted_by=server_rank;tie_id_desc" in meta["filtered_by"]


class TestW4MastodonTrendingLinks:
    @pytest.mark.asyncio
    async def test_meta_envelope_shape(self, mastodon_env: None) -> None:
        with patch.object(server_module, "_get_client") as mock_gc:
            mock_client = AsyncMock()
            mock_client.trending_links.return_value = [
                {"title": "X", "url": "https://example.com/x", "history": []},
            ]
            mock_gc.return_value = mock_client
            result = await server_module.mastodon_trending_links()
            meta = _parse_meta(result)
            _assert_meta_shape(meta)

    @pytest.mark.asyncio
    async def test_filtered_by_content(self, mastodon_env: None) -> None:
        with patch.object(server_module, "_get_client") as mock_gc:
            mock_client = AsyncMock()
            mock_client.trending_links.return_value = []
            mock_gc.return_value = mock_client
            result = await server_module.mastodon_trending_links(limit=12)
            meta = _parse_meta(result)
            assert "limit=12" in meta["filtered_by"]
            assert "sorted_by=server_rank;tie_url_asc" in meta["filtered_by"]

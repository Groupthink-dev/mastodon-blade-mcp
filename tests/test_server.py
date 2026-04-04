"""Tests for mastodon_blade_mcp.server -- MCP tool integration tests."""

from __future__ import annotations

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
            mock_client.timeline_home.return_value = [make_status()]
            mock_gc.return_value = mock_client
            result = await server_module.mastodon_timeline_home()
            assert "Hello world!" in result

    @pytest.mark.asyncio
    async def test_error_handling(self, mastodon_env: None) -> None:
        from mastodon_blade_mcp.client import MastodonError

        with patch.object(server_module, "_get_client") as mock_gc:
            mock_client = AsyncMock()
            mock_client.timeline_home.side_effect = MastodonError("test error")
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
            mock_client.search.return_value = {
                "accounts": [make_account()],
                "statuses": [],
                "hashtags": [],
            }
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
            mock_client.get_notifications.return_value = [make_notification()]
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

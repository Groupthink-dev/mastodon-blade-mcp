"""Mastodon Blade MCP Server -- timelines, statuses, notifications, search, interactions, multi-instance.

Wraps the Mastodon REST API as MCP tools. Token-efficient by default: compact
pipe-delimited output, HTML stripping, null-field omission. Write operations
gated by MASTODON_WRITE_ENABLED. Destructive operations (delete, block, mute)
require explicit confirm=true.
"""

from __future__ import annotations

import logging
import os
from typing import Annotated

from fastmcp import FastMCP
from pydantic import Field

from mastodon_blade_mcp.client import MastodonClient, MastodonError
from mastodon_blade_mcp.formatters import (
    format_account,
    format_account_list,
    format_context,
    format_conversations,
    format_filters,
    format_instance_info,
    format_lists,
    format_media,
    format_notifications,
    format_relationships,
    format_search_results,
    format_status,
    format_timeline,
    format_trending_links,
    format_trending_tags,
    format_verify_credentials,
)
from mastodon_blade_mcp.models import (
    check_confirm_gate,
    check_write_gate,
    is_write_enabled,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Transport configuration
# ---------------------------------------------------------------------------

TRANSPORT = os.environ.get("MASTODON_MCP_TRANSPORT", "stdio")
HTTP_HOST = os.environ.get("MASTODON_MCP_HOST", "127.0.0.1")
HTTP_PORT = int(os.environ.get("MASTODON_MCP_PORT", "8770"))

# ---------------------------------------------------------------------------
# FastMCP server
# ---------------------------------------------------------------------------

mcp = FastMCP(
    "MastodonBlade",
    instructions=(
        "Mastodon operations across one or more instances. "
        "Browse timelines, read/create statuses, manage notifications, search, and interact. "
        "Multi-instance: pass instance= to target a specific Mastodon server. "
        "Write operations require MASTODON_WRITE_ENABLED=true. "
        "Destructive operations (delete, block, mute, dismiss-all) require confirm=true."
    ),
)

# Lazy-initialized client
_client: MastodonClient | None = None


def _get_client() -> MastodonClient:
    """Get or create the MastodonClient singleton."""
    global _client  # noqa: PLW0603
    if _client is None:
        _client = MastodonClient()
    return _client


def _error(e: MastodonError) -> str:
    """Format a client error as a user-friendly string."""
    return f"Error: {e}"


# ===========================================================================
# READ TOOLS (25)
# ===========================================================================


# ---------------------------------------------------------------------------
# 1. mastodon_info
# ---------------------------------------------------------------------------


@mcp.tool()
async def mastodon_info(
    instance: Annotated[str | None, Field(description="Target instance (omit for default)")] = None,
) -> str:
    """Instance info, API version, current user, write gate status, and rate limit status."""
    try:
        client = _get_client()
        info = await client.instance_info(instance)
        rate_status = client.get_rate_status(instance)
        return format_instance_info(info, is_write_enabled(), rate_status)
    except MastodonError as e:
        return _error(e)


# ---------------------------------------------------------------------------
# 2. mastodon_verify
# ---------------------------------------------------------------------------


@mcp.tool()
async def mastodon_verify(
    instance: Annotated[str | None, Field(description="Target instance (omit for default)")] = None,
) -> str:
    """Verify credentials and show current authenticated user."""
    try:
        data = await _get_client().verify_credentials(instance)
        return format_verify_credentials(data)
    except MastodonError as e:
        return _error(e)


# ---------------------------------------------------------------------------
# 3. mastodon_timeline_home
# ---------------------------------------------------------------------------


@mcp.tool()
async def mastodon_timeline_home(
    limit: Annotated[int, Field(description="Max statuses to return")] = 20,
    max_id: Annotated[str | None, Field(description="Return statuses older than this ID (pagination)")] = None,
    instance: Annotated[str | None, Field(description="Target instance (omit for default)")] = None,
) -> str:
    """Home timeline -- statuses from followed accounts."""
    try:
        data = await _get_client().timeline_home(limit, max_id, instance)
        return format_timeline(data)
    except MastodonError as e:
        return _error(e)


# ---------------------------------------------------------------------------
# 4. mastodon_timeline_public
# ---------------------------------------------------------------------------


@mcp.tool()
async def mastodon_timeline_public(
    local: Annotated[bool, Field(description="Show only local instance statuses")] = False,
    limit: Annotated[int, Field(description="Max statuses to return")] = 20,
    max_id: Annotated[str | None, Field(description="Return statuses older than this ID (pagination)")] = None,
    instance: Annotated[str | None, Field(description="Target instance (omit for default)")] = None,
) -> str:
    """Public (federated) timeline. Set local=true for local-only."""
    try:
        data = await _get_client().timeline_public(local, limit, max_id, instance)
        return format_timeline(data)
    except MastodonError as e:
        return _error(e)


# ---------------------------------------------------------------------------
# 5. mastodon_timeline_local
# ---------------------------------------------------------------------------


@mcp.tool()
async def mastodon_timeline_local(
    limit: Annotated[int, Field(description="Max statuses to return")] = 20,
    max_id: Annotated[str | None, Field(description="Return statuses older than this ID (pagination)")] = None,
    instance: Annotated[str | None, Field(description="Target instance (omit for default)")] = None,
) -> str:
    """Local instance timeline (convenience wrapper for public timeline with local=true)."""
    try:
        data = await _get_client().timeline_public(local=True, limit=limit, max_id=max_id, instance=instance)
        return format_timeline(data)
    except MastodonError as e:
        return _error(e)


# ---------------------------------------------------------------------------
# 6. mastodon_timeline_hashtag
# ---------------------------------------------------------------------------


@mcp.tool()
async def mastodon_timeline_hashtag(
    hashtag: Annotated[str, Field(description="Hashtag to search (with or without #)")],
    limit: Annotated[int, Field(description="Max statuses to return")] = 20,
    max_id: Annotated[str | None, Field(description="Return statuses older than this ID (pagination)")] = None,
    local: Annotated[bool, Field(description="Show only local instance statuses")] = False,
    instance: Annotated[str | None, Field(description="Target instance (omit for default)")] = None,
) -> str:
    """Hashtag timeline -- statuses tagged with a specific hashtag."""
    try:
        data = await _get_client().timeline_hashtag(hashtag, limit, max_id, local, instance)
        return format_timeline(data)
    except MastodonError as e:
        return _error(e)


# ---------------------------------------------------------------------------
# 7. mastodon_timeline_list
# ---------------------------------------------------------------------------


@mcp.tool()
async def mastodon_timeline_list(
    list_id: Annotated[str, Field(description="List ID")],
    limit: Annotated[int, Field(description="Max statuses to return")] = 20,
    max_id: Annotated[str | None, Field(description="Return statuses older than this ID (pagination)")] = None,
    instance: Annotated[str | None, Field(description="Target instance (omit for default)")] = None,
) -> str:
    """List timeline -- statuses from accounts in a specific list."""
    try:
        data = await _get_client().timeline_list(list_id, limit, max_id, instance)
        return format_timeline(data)
    except MastodonError as e:
        return _error(e)


# ---------------------------------------------------------------------------
# 8. mastodon_status
# ---------------------------------------------------------------------------


@mcp.tool()
async def mastodon_status(
    status_id: Annotated[str, Field(description="Status ID")],
    instance: Annotated[str | None, Field(description="Target instance (omit for default)")] = None,
) -> str:
    """Get a specific status by ID."""
    try:
        data = await _get_client().get_status(status_id, instance)
        return format_status(data)
    except MastodonError as e:
        return _error(e)


# ---------------------------------------------------------------------------
# 9. mastodon_context
# ---------------------------------------------------------------------------


@mcp.tool()
async def mastodon_context(
    status_id: Annotated[str, Field(description="Status ID to get thread context for")],
    instance: Annotated[str | None, Field(description="Target instance (omit for default)")] = None,
) -> str:
    """Thread context -- ancestors and descendants of a status."""
    try:
        data = await _get_client().get_context(status_id, instance)
        return format_context(data)
    except MastodonError as e:
        return _error(e)


# ---------------------------------------------------------------------------
# 10. mastodon_search
# ---------------------------------------------------------------------------


@mcp.tool()
async def mastodon_search(
    q: Annotated[str, Field(description="Search query")],
    type: Annotated[str | None, Field(description="Filter by type: accounts, statuses, or hashtags")] = None,
    limit: Annotated[int, Field(description="Max results per type")] = 20,
    instance: Annotated[str | None, Field(description="Target instance (omit for default)")] = None,
) -> str:
    """Unified search across accounts, statuses, and hashtags."""
    try:
        data = await _get_client().search(q, type, limit, instance)
        return format_search_results(data)
    except MastodonError as e:
        return _error(e)


# ---------------------------------------------------------------------------
# 11. mastodon_account
# ---------------------------------------------------------------------------


@mcp.tool()
async def mastodon_account(
    account_id: Annotated[str, Field(description="Account ID")],
    instance: Annotated[str | None, Field(description="Target instance (omit for default)")] = None,
) -> str:
    """Get account info by ID."""
    try:
        data = await _get_client().get_account(account_id, instance)
        return format_account(data)
    except MastodonError as e:
        return _error(e)


# ---------------------------------------------------------------------------
# 12. mastodon_account_statuses
# ---------------------------------------------------------------------------


@mcp.tool()
async def mastodon_account_statuses(
    account_id: Annotated[str, Field(description="Account ID")],
    limit: Annotated[int, Field(description="Max statuses to return")] = 20,
    max_id: Annotated[str | None, Field(description="Return statuses older than this ID (pagination)")] = None,
    exclude_reblogs: Annotated[bool, Field(description="Exclude reblogs")] = False,
    only_media: Annotated[bool, Field(description="Only show statuses with media")] = False,
    pinned: Annotated[bool, Field(description="Only show pinned statuses")] = False,
    instance: Annotated[str | None, Field(description="Target instance (omit for default)")] = None,
) -> str:
    """Get an account's statuses with filtering options."""
    try:
        data = await _get_client().get_account_statuses(
            account_id, limit, max_id, exclude_reblogs, only_media, pinned, instance
        )
        return format_timeline(data)
    except MastodonError as e:
        return _error(e)


# ---------------------------------------------------------------------------
# 13. mastodon_relationships
# ---------------------------------------------------------------------------


@mcp.tool()
async def mastodon_relationships(
    account_ids: Annotated[list[str], Field(description="List of account IDs to check relationships with")],
    instance: Annotated[str | None, Field(description="Target instance (omit for default)")] = None,
) -> str:
    """Check relationships with one or more accounts (following, blocked, muted, etc.)."""
    try:
        data = await _get_client().get_relationships(account_ids, instance)
        return format_relationships(data)
    except MastodonError as e:
        return _error(e)


# ---------------------------------------------------------------------------
# 14. mastodon_followers
# ---------------------------------------------------------------------------


@mcp.tool()
async def mastodon_followers(
    account_id: Annotated[str, Field(description="Account ID")],
    limit: Annotated[int, Field(description="Max results")] = 40,
    instance: Annotated[str | None, Field(description="Target instance (omit for default)")] = None,
) -> str:
    """List followers of an account."""
    try:
        data = await _get_client().get_followers(account_id, limit, instance)
        return format_account_list(data)
    except MastodonError as e:
        return _error(e)


# ---------------------------------------------------------------------------
# 15. mastodon_following
# ---------------------------------------------------------------------------


@mcp.tool()
async def mastodon_following(
    account_id: Annotated[str, Field(description="Account ID")],
    limit: Annotated[int, Field(description="Max results")] = 40,
    instance: Annotated[str | None, Field(description="Target instance (omit for default)")] = None,
) -> str:
    """List accounts followed by an account."""
    try:
        data = await _get_client().get_following(account_id, limit, instance)
        return format_account_list(data)
    except MastodonError as e:
        return _error(e)


# ---------------------------------------------------------------------------
# 16. mastodon_notifications
# ---------------------------------------------------------------------------


@mcp.tool()
async def mastodon_notifications(
    types: Annotated[
        list[str] | None,
        Field(description="Filter by types: mention, favourite, reblog, follow, poll, update"),
    ] = None,
    limit: Annotated[int, Field(description="Max notifications")] = 20,
    max_id: Annotated[str | None, Field(description="Return notifications older than this ID")] = None,
    instance: Annotated[str | None, Field(description="Target instance (omit for default)")] = None,
) -> str:
    """List notifications, optionally filtered by type."""
    try:
        data = await _get_client().get_notifications(types, limit, max_id, instance)
        return format_notifications(data)
    except MastodonError as e:
        return _error(e)


# ---------------------------------------------------------------------------
# 17. mastodon_trending_tags
# ---------------------------------------------------------------------------


@mcp.tool()
async def mastodon_trending_tags(
    limit: Annotated[int, Field(description="Max results")] = 10,
    instance: Annotated[str | None, Field(description="Target instance (omit for default)")] = None,
) -> str:
    """Trending hashtags on the instance."""
    try:
        data = await _get_client().trending_tags(limit, instance)
        return format_trending_tags(data)
    except MastodonError as e:
        return _error(e)


# ---------------------------------------------------------------------------
# 18. mastodon_trending_statuses
# ---------------------------------------------------------------------------


@mcp.tool()
async def mastodon_trending_statuses(
    limit: Annotated[int, Field(description="Max results")] = 20,
    instance: Annotated[str | None, Field(description="Target instance (omit for default)")] = None,
) -> str:
    """Trending statuses on the instance."""
    try:
        data = await _get_client().trending_statuses(limit, instance)
        return format_timeline(data)
    except MastodonError as e:
        return _error(e)


# ---------------------------------------------------------------------------
# 19. mastodon_trending_links
# ---------------------------------------------------------------------------


@mcp.tool()
async def mastodon_trending_links(
    limit: Annotated[int, Field(description="Max results")] = 10,
    instance: Annotated[str | None, Field(description="Target instance (omit for default)")] = None,
) -> str:
    """Trending links shared on the instance."""
    try:
        data = await _get_client().trending_links(limit, instance)
        return format_trending_links(data)
    except MastodonError as e:
        return _error(e)


# ---------------------------------------------------------------------------
# 20. mastodon_bookmarks
# ---------------------------------------------------------------------------


@mcp.tool()
async def mastodon_bookmarks(
    limit: Annotated[int, Field(description="Max results")] = 20,
    max_id: Annotated[str | None, Field(description="Return bookmarks older than this ID (pagination)")] = None,
    instance: Annotated[str | None, Field(description="Target instance (omit for default)")] = None,
) -> str:
    """List bookmarked statuses."""
    try:
        data = await _get_client().get_bookmarks(limit, max_id, instance)
        return format_timeline(data)
    except MastodonError as e:
        return _error(e)


# ---------------------------------------------------------------------------
# 21. mastodon_favourites
# ---------------------------------------------------------------------------


@mcp.tool()
async def mastodon_favourites(
    limit: Annotated[int, Field(description="Max results")] = 20,
    max_id: Annotated[str | None, Field(description="Return favourites older than this ID (pagination)")] = None,
    instance: Annotated[str | None, Field(description="Target instance (omit for default)")] = None,
) -> str:
    """List favourited statuses."""
    try:
        data = await _get_client().get_favourites(limit, max_id, instance)
        return format_timeline(data)
    except MastodonError as e:
        return _error(e)


# ---------------------------------------------------------------------------
# 22. mastodon_lists
# ---------------------------------------------------------------------------


@mcp.tool()
async def mastodon_lists(
    instance: Annotated[str | None, Field(description="Target instance (omit for default)")] = None,
) -> str:
    """List all lists."""
    try:
        data = await _get_client().get_lists(instance)
        return format_lists(data)
    except MastodonError as e:
        return _error(e)


# ---------------------------------------------------------------------------
# 23. mastodon_list_accounts
# ---------------------------------------------------------------------------


@mcp.tool()
async def mastodon_list_accounts(
    list_id: Annotated[str, Field(description="List ID")],
    limit: Annotated[int, Field(description="Max results")] = 40,
    instance: Annotated[str | None, Field(description="Target instance (omit for default)")] = None,
) -> str:
    """Get accounts in a specific list."""
    try:
        data = await _get_client().get_list_accounts(list_id, limit, instance)
        return format_account_list(data)
    except MastodonError as e:
        return _error(e)


# ---------------------------------------------------------------------------
# 24. mastodon_conversations
# ---------------------------------------------------------------------------


@mcp.tool()
async def mastodon_conversations(
    limit: Annotated[int, Field(description="Max results")] = 20,
    max_id: Annotated[str | None, Field(description="Return conversations older than this ID (pagination)")] = None,
    instance: Annotated[str | None, Field(description="Target instance (omit for default)")] = None,
) -> str:
    """List direct message conversations."""
    try:
        data = await _get_client().get_conversations(limit, max_id, instance)
        return format_conversations(data)
    except MastodonError as e:
        return _error(e)


# ---------------------------------------------------------------------------
# 25. mastodon_filters
# ---------------------------------------------------------------------------


@mcp.tool()
async def mastodon_filters(
    instance: Annotated[str | None, Field(description="Target instance (omit for default)")] = None,
) -> str:
    """List active content filters (v2 API with v1 fallback)."""
    try:
        data = await _get_client().get_filters(instance)
        return format_filters(data)
    except MastodonError as e:
        return _error(e)


# ===========================================================================
# WRITE TOOLS (20)
# ===========================================================================


# ---------------------------------------------------------------------------
# 26. mastodon_post
# ---------------------------------------------------------------------------


@mcp.tool()
async def mastodon_post(
    text: Annotated[str, Field(description="Status text content")],
    visibility: Annotated[str, Field(description="Visibility: public, unlisted, private, or direct")] = "public",
    spoiler_text: Annotated[str | None, Field(description="Content warning text")] = None,
    in_reply_to_id: Annotated[str | None, Field(description="Status ID to reply to")] = None,
    media_ids: Annotated[list[str] | None, Field(description="Media attachment IDs")] = None,
    sensitive: Annotated[bool, Field(description="Mark media as sensitive")] = False,
    language: Annotated[str | None, Field(description="ISO 639-1 language code")] = None,
    scheduled_at: Annotated[str | None, Field(description="ISO 8601 datetime to schedule")] = None,
    instance: Annotated[str | None, Field(description="Target instance (omit for default)")] = None,
) -> str:
    """Create a new status. Requires MASTODON_WRITE_ENABLED=true."""
    gate = check_write_gate()
    if gate:
        return gate
    try:
        data = await _get_client().post_status(
            text, visibility, spoiler_text, in_reply_to_id, media_ids, sensitive, language, scheduled_at, instance
        )
        return f"Posted: {format_status(data)}"
    except MastodonError as e:
        return _error(e)


# ---------------------------------------------------------------------------
# 27. mastodon_reply
# ---------------------------------------------------------------------------


@mcp.tool()
async def mastodon_reply(
    status_id: Annotated[str, Field(description="Status ID to reply to")],
    text: Annotated[str, Field(description="Reply text content")],
    visibility: Annotated[str, Field(description="Visibility: public, unlisted, private, or direct")] = "public",
    spoiler_text: Annotated[str | None, Field(description="Content warning text")] = None,
    media_ids: Annotated[list[str] | None, Field(description="Media attachment IDs")] = None,
    sensitive: Annotated[bool, Field(description="Mark media as sensitive")] = False,
    instance: Annotated[str | None, Field(description="Target instance (omit for default)")] = None,
) -> str:
    """Reply to a status. Convenience wrapper for mastodon_post with in_reply_to_id.

    Requires MASTODON_WRITE_ENABLED=true.
    """
    gate = check_write_gate()
    if gate:
        return gate
    try:
        data = await _get_client().post_status(
            text, visibility, spoiler_text, status_id, media_ids, sensitive, instance=instance
        )
        return f"Replied: {format_status(data)}"
    except MastodonError as e:
        return _error(e)


# ---------------------------------------------------------------------------
# 28. mastodon_edit
# ---------------------------------------------------------------------------


@mcp.tool()
async def mastodon_edit(
    status_id: Annotated[str, Field(description="Status ID to edit")],
    text: Annotated[str, Field(description="Updated text content")],
    spoiler_text: Annotated[str | None, Field(description="Updated content warning text")] = None,
    sensitive: Annotated[bool | None, Field(description="Updated sensitive flag")] = None,
    media_ids: Annotated[list[str] | None, Field(description="Updated media attachment IDs")] = None,
    instance: Annotated[str | None, Field(description="Target instance (omit for default)")] = None,
) -> str:
    """Edit an existing status. Requires MASTODON_WRITE_ENABLED=true."""
    gate = check_write_gate()
    if gate:
        return gate
    try:
        data = await _get_client().edit_status(status_id, text, spoiler_text, sensitive, media_ids, instance)
        return f"Edited: {format_status(data)}"
    except MastodonError as e:
        return _error(e)


# ---------------------------------------------------------------------------
# 29. mastodon_delete [confirm gate]
# ---------------------------------------------------------------------------


@mcp.tool()
async def mastodon_delete(
    status_id: Annotated[str, Field(description="Status ID to delete")],
    confirm: Annotated[bool, Field(description="Must be true -- destructive operation")] = False,
    instance: Annotated[str | None, Field(description="Target instance (omit for default)")] = None,
) -> str:
    """Delete a status. Destructive: requires MASTODON_WRITE_ENABLED=true AND confirm=true."""
    gate = check_write_gate()
    if gate:
        return gate
    conf = check_confirm_gate(confirm, "Delete status")
    if conf:
        return conf
    try:
        await _get_client().delete_status(status_id, instance)
        return f"Deleted status {status_id}"
    except MastodonError as e:
        return _error(e)


# ---------------------------------------------------------------------------
# 30. mastodon_favourite
# ---------------------------------------------------------------------------


@mcp.tool()
async def mastodon_favourite(
    status_id: Annotated[str, Field(description="Status ID to favourite")],
    instance: Annotated[str | None, Field(description="Target instance (omit for default)")] = None,
) -> str:
    """Favourite a status. Requires MASTODON_WRITE_ENABLED=true."""
    gate = check_write_gate()
    if gate:
        return gate
    try:
        data = await _get_client().favourite_status(status_id, instance)
        return f"Favourited: {format_status(data)}"
    except MastodonError as e:
        return _error(e)


# ---------------------------------------------------------------------------
# 31. mastodon_unfavourite
# ---------------------------------------------------------------------------


@mcp.tool()
async def mastodon_unfavourite(
    status_id: Annotated[str, Field(description="Status ID to unfavourite")],
    instance: Annotated[str | None, Field(description="Target instance (omit for default)")] = None,
) -> str:
    """Remove favourite from a status. Requires MASTODON_WRITE_ENABLED=true."""
    gate = check_write_gate()
    if gate:
        return gate
    try:
        data = await _get_client().unfavourite_status(status_id, instance)
        return f"Unfavourited: {format_status(data)}"
    except MastodonError as e:
        return _error(e)


# ---------------------------------------------------------------------------
# 32. mastodon_boost
# ---------------------------------------------------------------------------


@mcp.tool()
async def mastodon_boost(
    status_id: Annotated[str, Field(description="Status ID to boost (reblog)")],
    instance: Annotated[str | None, Field(description="Target instance (omit for default)")] = None,
) -> str:
    """Boost (reblog) a status. Requires MASTODON_WRITE_ENABLED=true."""
    gate = check_write_gate()
    if gate:
        return gate
    try:
        data = await _get_client().reblog_status(status_id, instance)
        return f"Boosted: {format_status(data)}"
    except MastodonError as e:
        return _error(e)


# ---------------------------------------------------------------------------
# 33. mastodon_unboost
# ---------------------------------------------------------------------------


@mcp.tool()
async def mastodon_unboost(
    status_id: Annotated[str, Field(description="Status ID to unboost (un-reblog)")],
    instance: Annotated[str | None, Field(description="Target instance (omit for default)")] = None,
) -> str:
    """Remove boost from a status. Requires MASTODON_WRITE_ENABLED=true."""
    gate = check_write_gate()
    if gate:
        return gate
    try:
        data = await _get_client().unreblog_status(status_id, instance)
        return f"Unboosted: {format_status(data)}"
    except MastodonError as e:
        return _error(e)


# ---------------------------------------------------------------------------
# 34. mastodon_bookmark
# ---------------------------------------------------------------------------


@mcp.tool()
async def mastodon_bookmark(
    status_id: Annotated[str, Field(description="Status ID to bookmark")],
    instance: Annotated[str | None, Field(description="Target instance (omit for default)")] = None,
) -> str:
    """Bookmark a status. Requires MASTODON_WRITE_ENABLED=true."""
    gate = check_write_gate()
    if gate:
        return gate
    try:
        data = await _get_client().bookmark_status(status_id, instance)
        return f"Bookmarked: {format_status(data)}"
    except MastodonError as e:
        return _error(e)


# ---------------------------------------------------------------------------
# 35. mastodon_unbookmark
# ---------------------------------------------------------------------------


@mcp.tool()
async def mastodon_unbookmark(
    status_id: Annotated[str, Field(description="Status ID to unbookmark")],
    instance: Annotated[str | None, Field(description="Target instance (omit for default)")] = None,
) -> str:
    """Remove bookmark from a status. Requires MASTODON_WRITE_ENABLED=true."""
    gate = check_write_gate()
    if gate:
        return gate
    try:
        data = await _get_client().unbookmark_status(status_id, instance)
        return f"Unbookmarked: {format_status(data)}"
    except MastodonError as e:
        return _error(e)


# ---------------------------------------------------------------------------
# 36. mastodon_pin
# ---------------------------------------------------------------------------


@mcp.tool()
async def mastodon_pin(
    status_id: Annotated[str, Field(description="Status ID to pin to profile")],
    instance: Annotated[str | None, Field(description="Target instance (omit for default)")] = None,
) -> str:
    """Pin a status to your profile. Requires MASTODON_WRITE_ENABLED=true."""
    gate = check_write_gate()
    if gate:
        return gate
    try:
        data = await _get_client().pin_status(status_id, instance)
        return f"Pinned: {format_status(data)}"
    except MastodonError as e:
        return _error(e)


# ---------------------------------------------------------------------------
# 37. mastodon_unpin
# ---------------------------------------------------------------------------


@mcp.tool()
async def mastodon_unpin(
    status_id: Annotated[str, Field(description="Status ID to unpin from profile")],
    instance: Annotated[str | None, Field(description="Target instance (omit for default)")] = None,
) -> str:
    """Unpin a status from your profile. Requires MASTODON_WRITE_ENABLED=true."""
    gate = check_write_gate()
    if gate:
        return gate
    try:
        data = await _get_client().unpin_status(status_id, instance)
        return f"Unpinned: {format_status(data)}"
    except MastodonError as e:
        return _error(e)


# ---------------------------------------------------------------------------
# 38. mastodon_follow
# ---------------------------------------------------------------------------


@mcp.tool()
async def mastodon_follow(
    account_id: Annotated[str, Field(description="Account ID to follow")],
    instance: Annotated[str | None, Field(description="Target instance (omit for default)")] = None,
) -> str:
    """Follow an account. Requires MASTODON_WRITE_ENABLED=true."""
    gate = check_write_gate()
    if gate:
        return gate
    try:
        data = await _get_client().follow_account(account_id, instance)
        following = data.get("following", False)
        requested = data.get("requested", False)
        status = "following" if following else ("requested" if requested else "unknown")
        return f"Follow {account_id}: {status}"
    except MastodonError as e:
        return _error(e)


# ---------------------------------------------------------------------------
# 39. mastodon_unfollow
# ---------------------------------------------------------------------------


@mcp.tool()
async def mastodon_unfollow(
    account_id: Annotated[str, Field(description="Account ID to unfollow")],
    instance: Annotated[str | None, Field(description="Target instance (omit for default)")] = None,
) -> str:
    """Unfollow an account. Requires MASTODON_WRITE_ENABLED=true."""
    gate = check_write_gate()
    if gate:
        return gate
    try:
        await _get_client().unfollow_account(account_id, instance)
        return f"Unfollowed {account_id}"
    except MastodonError as e:
        return _error(e)


# ---------------------------------------------------------------------------
# 40. mastodon_block [confirm gate]
# ---------------------------------------------------------------------------


@mcp.tool()
async def mastodon_block(
    account_id: Annotated[str, Field(description="Account ID to block")],
    confirm: Annotated[bool, Field(description="Must be true -- destructive operation")] = False,
    instance: Annotated[str | None, Field(description="Target instance (omit for default)")] = None,
) -> str:
    """Block an account. Destructive: requires MASTODON_WRITE_ENABLED=true AND confirm=true."""
    gate = check_write_gate()
    if gate:
        return gate
    conf = check_confirm_gate(confirm, "Block account")
    if conf:
        return conf
    try:
        await _get_client().block_account(account_id, instance)
        return f"Blocked {account_id}"
    except MastodonError as e:
        return _error(e)


# ---------------------------------------------------------------------------
# 41. mastodon_unblock
# ---------------------------------------------------------------------------


@mcp.tool()
async def mastodon_unblock(
    account_id: Annotated[str, Field(description="Account ID to unblock")],
    instance: Annotated[str | None, Field(description="Target instance (omit for default)")] = None,
) -> str:
    """Unblock an account. Requires MASTODON_WRITE_ENABLED=true."""
    gate = check_write_gate()
    if gate:
        return gate
    try:
        await _get_client().unblock_account(account_id, instance)
        return f"Unblocked {account_id}"
    except MastodonError as e:
        return _error(e)


# ---------------------------------------------------------------------------
# 42. mastodon_mute [confirm gate]
# ---------------------------------------------------------------------------


@mcp.tool()
async def mastodon_mute(
    account_id: Annotated[str, Field(description="Account ID to mute")],
    confirm: Annotated[bool, Field(description="Must be true -- destructive operation")] = False,
    duration: Annotated[int | None, Field(description="Mute duration in seconds (0 or omit for indefinite)")] = None,
    instance: Annotated[str | None, Field(description="Target instance (omit for default)")] = None,
) -> str:
    """Mute an account. Destructive: requires MASTODON_WRITE_ENABLED=true AND confirm=true."""
    gate = check_write_gate()
    if gate:
        return gate
    conf = check_confirm_gate(confirm, "Mute account")
    if conf:
        return conf
    try:
        await _get_client().mute_account(account_id, duration, instance)
        dur_str = f" for {duration}s" if duration else " indefinitely"
        return f"Muted {account_id}{dur_str}"
    except MastodonError as e:
        return _error(e)


# ---------------------------------------------------------------------------
# 43. mastodon_unmute
# ---------------------------------------------------------------------------


@mcp.tool()
async def mastodon_unmute(
    account_id: Annotated[str, Field(description="Account ID to unmute")],
    instance: Annotated[str | None, Field(description="Target instance (omit for default)")] = None,
) -> str:
    """Unmute an account. Requires MASTODON_WRITE_ENABLED=true."""
    gate = check_write_gate()
    if gate:
        return gate
    try:
        await _get_client().unmute_account(account_id, instance)
        return f"Unmuted {account_id}"
    except MastodonError as e:
        return _error(e)


# ---------------------------------------------------------------------------
# 44. mastodon_dismiss_notification
# ---------------------------------------------------------------------------


@mcp.tool()
async def mastodon_dismiss_notification(
    notification_id: Annotated[str, Field(description="Notification ID to dismiss")],
    instance: Annotated[str | None, Field(description="Target instance (omit for default)")] = None,
) -> str:
    """Dismiss a single notification. Requires MASTODON_WRITE_ENABLED=true."""
    gate = check_write_gate()
    if gate:
        return gate
    try:
        await _get_client().dismiss_notification(notification_id, instance)
        return f"Dismissed notification {notification_id}"
    except MastodonError as e:
        return _error(e)


# ---------------------------------------------------------------------------
# 45. mastodon_media_upload
# ---------------------------------------------------------------------------


@mcp.tool()
async def mastodon_media_upload(
    file_path: Annotated[str, Field(description="Local file path to upload")],
    description: Annotated[str | None, Field(description="Alt text / media description")] = None,
    instance: Annotated[str | None, Field(description="Target instance (omit for default)")] = None,
) -> str:
    """Upload a media attachment for use in statuses. Requires MASTODON_WRITE_ENABLED=true."""
    gate = check_write_gate()
    if gate:
        return gate
    try:
        data = await _get_client().upload_media(file_path, description, instance)
        return format_media(data)
    except MastodonError as e:
        return _error(e)


# ===========================================================================
# Entry point
# ===========================================================================


def main() -> None:
    """Run the MCP server."""
    if TRANSPORT == "http":
        from starlette.middleware import Middleware

        from mastodon_blade_mcp.auth import BearerAuthMiddleware

        mcp.run(
            transport="streamable-http",
            host=HTTP_HOST,
            port=HTTP_PORT,
            middleware=[Middleware(BearerAuthMiddleware)],
        )
    else:
        mcp.run(transport="stdio")

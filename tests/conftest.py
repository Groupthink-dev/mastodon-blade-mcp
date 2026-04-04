"""Shared fixtures and mock builders for Mastodon Blade MCP tests."""

from __future__ import annotations

import os
from typing import Any

import pytest


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure no real Mastodon credentials leak into tests."""
    for key in list(os.environ.keys()):
        if key.startswith("MASTODON_"):
            monkeypatch.delenv(key, raising=False)


@pytest.fixture()
def mastodon_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set up single-provider Mastodon environment."""
    monkeypatch.setenv("MASTODON_INSTANCE", "https://mastodon.social")
    monkeypatch.setenv("MASTODON_TOKEN", "test-token-123")


@pytest.fixture()
def mastodon_env_multi(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set up multi-provider Mastodon environment."""
    monkeypatch.setenv("MASTODON_PROVIDERS", "social,hachyderm")
    monkeypatch.setenv("MASTODON_SOCIAL_INSTANCE", "https://mastodon.social")
    monkeypatch.setenv("MASTODON_SOCIAL_TOKEN", "social-token")
    monkeypatch.setenv("MASTODON_HACHYDERM_INSTANCE", "https://hachyderm.io")
    monkeypatch.setenv("MASTODON_HACHYDERM_TOKEN", "hachyderm-token")


@pytest.fixture()
def mastodon_env_write(monkeypatch: pytest.MonkeyPatch, mastodon_env: None) -> None:
    """Single-provider with write enabled."""
    monkeypatch.setenv("MASTODON_WRITE_ENABLED", "true")


# ---------------------------------------------------------------------------
# Mock data builders
# ---------------------------------------------------------------------------


def make_account(
    account_id: str = "12345",
    acct: str = "user@mastodon.social",
    display_name: str = "Test User",
    followers_count: int = 100,
    following_count: int = 50,
    statuses_count: int = 200,
    bot: bool = False,
    locked: bool = False,
    note: str = "<p>A test user bio</p>",
) -> dict[str, Any]:
    """Build a mock Mastodon account dict."""
    return {
        "id": account_id,
        "username": acct.split("@")[0],
        "acct": acct,
        "display_name": display_name,
        "locked": locked,
        "bot": bot,
        "created_at": "2023-01-01T00:00:00.000Z",
        "note": note,
        "url": f"https://mastodon.social/@{acct.split('@')[0]}",
        "followers_count": followers_count,
        "following_count": following_count,
        "statuses_count": statuses_count,
    }


def make_status(
    status_id: str = "109876543210",
    acct: str = "user@mastodon.social",
    content: str = "<p>Hello world!</p>",
    visibility: str = "public",
    favourites_count: int = 5,
    reblogs_count: int = 2,
    replies_count: int = 1,
    spoiler_text: str = "",
    media_attachments: list[dict[str, Any]] | None = None,
    reblog: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a mock Mastodon status dict."""
    return {
        "id": status_id,
        "created_at": "2026-04-04T10:30:00.000Z",
        "content": content,
        "visibility": visibility,
        "spoiler_text": spoiler_text,
        "favourites_count": favourites_count,
        "reblogs_count": reblogs_count,
        "replies_count": replies_count,
        "media_attachments": media_attachments or [],
        "reblog": reblog,
        "account": make_account(acct=acct),
        "url": f"https://mastodon.social/@{acct.split('@')[0]}/{status_id}",
    }


def make_notification(
    notification_id: str = "99999",
    notif_type: str = "mention",
    acct: str = "other@mastodon.social",
    status_id: str | None = "109876543210",
    content: str = "<p>@user Hey there!</p>",
) -> dict[str, Any]:
    """Build a mock Mastodon notification dict."""
    notif: dict[str, Any] = {
        "id": notification_id,
        "type": notif_type,
        "created_at": "2026-04-04T11:00:00.000Z",
        "account": make_account(acct=acct),
    }
    if status_id and content:
        notif["status"] = make_status(status_id=status_id, content=content)
    return notif


def make_relationship(
    account_id: str = "12345",
    following: bool = True,
    followed_by: bool = False,
    blocking: bool = False,
    muting: bool = False,
) -> dict[str, Any]:
    """Build a mock Mastodon relationship dict."""
    return {
        "id": account_id,
        "following": following,
        "followed_by": followed_by,
        "blocking": blocking,
        "muting": muting,
        "requested": False,
        "domain_blocking": False,
        "showing_reblogs": True,
        "notifying": False,
        "note": "",
    }


def make_conversation(
    conv_id: str = "conv-1",
    accts: list[str] | None = None,
    unread: bool = False,
    content: str = "<p>Private message</p>",
) -> dict[str, Any]:
    """Build a mock Mastodon conversation dict."""
    accounts = [make_account(acct=a) for a in (accts or ["friend@mastodon.social"])]
    return {
        "id": conv_id,
        "accounts": accounts,
        "unread": unread,
        "last_status": make_status(content=content, visibility="direct"),
    }


def make_list_entry(
    list_id: str = "list-1",
    title: str = "Tech News",
    replies_policy: str = "list",
) -> dict[str, Any]:
    """Build a mock Mastodon list dict."""
    return {
        "id": list_id,
        "title": title,
        "replies_policy": replies_policy,
        "exclusive": False,
    }


def make_filter_entry(
    filter_id: str = "filter-1",
    title: str = "Spoilers",
    context: list[str] | None = None,
    filter_action: str = "warn",
    keywords: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Build a mock Mastodon v2 filter dict."""
    return {
        "id": filter_id,
        "title": title,
        "context": context or ["home", "public"],
        "filter_action": filter_action,
        "keywords": keywords or [{"keyword": "spoiler", "whole_word": True}],
        "expires_at": None,
    }


def make_trending_tag(
    name: str = "python",
    uses_today: int = 42,
    accounts_today: int = 15,
) -> dict[str, Any]:
    """Build a mock trending tag dict."""
    return {
        "name": name,
        "url": f"https://mastodon.social/tags/{name}",
        "history": [
            {"day": "1712188800", "uses": str(uses_today), "accounts": str(accounts_today)},
        ],
    }

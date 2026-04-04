"""Token-efficient output formatters for Mastodon Blade MCP server.

All formatters return compact strings optimised for LLM consumption:
- One line per status/account/notification
- Pipe-delimited fields
- Null-field omission
- HTML stripped from content
"""

from __future__ import annotations

import html
import re
from typing import Any

# ---------------------------------------------------------------------------
# HTML / text utilities
# ---------------------------------------------------------------------------


def strip_html(text: str) -> str:
    """Remove HTML tags, decode entities, and collapse whitespace."""
    if not text:
        return ""
    # Remove HTML tags
    clean = re.sub(r"<br\s*/?>", "\n", text)
    clean = re.sub(r"<p>", "", clean)
    clean = re.sub(r"</p>", "\n", clean)
    clean = re.sub(r"<[^>]+>", "", clean)
    # Decode HTML entities
    clean = html.unescape(clean)
    # Collapse whitespace (preserve single newlines)
    clean = re.sub(r"[ \t]+", " ", clean)
    clean = re.sub(r"\n{3,}", "\n\n", clean)
    return clean.strip()


def truncate(text: str, max_len: int = 300) -> str:
    """Truncate text with ellipsis for excerpts."""
    if not text or len(text) <= max_len:
        return text
    return text[:max_len].rstrip() + "..."


# ---------------------------------------------------------------------------
# Status formatting
# ---------------------------------------------------------------------------


def _format_acct(account: dict[str, Any]) -> str:
    """Format account as @user@instance or @user."""
    acct = account.get("acct", account.get("username", "?"))
    return f"@{acct}"


def _format_timestamp(ts: str | None) -> str:
    """Extract compact timestamp from ISO 8601."""
    if not ts:
        return "?"
    # 2026-04-04T10:30:00.000Z -> 2026-04-04 10:30
    if "T" in ts:
        date_part = ts.split("T")[0]
        time_part = ts.split("T")[1][:5]
        return f"{date_part} {time_part}"
    return ts


def format_status(status: dict[str, Any]) -> str:
    """Format a single status as pipe-delimited compact line.

    Format: id | @user | timestamp | visibility | content | fav=N | boost=N | reply=N
    """
    parts: list[str] = []
    parts.append(status.get("id", "?"))

    account = status.get("account", {})
    parts.append(_format_acct(account))
    parts.append(_format_timestamp(status.get("created_at")))
    parts.append(status.get("visibility", "public"))

    # Content: strip HTML, truncate
    content = strip_html(status.get("content", ""))
    if status.get("spoiler_text"):
        content = f"CW: {status['spoiler_text']} | {content}"
    parts.append(truncate(content))

    # Engagement counts (omit if zero)
    fav = status.get("favourites_count", 0)
    boost = status.get("reblogs_count", 0)
    reply = status.get("replies_count", 0)
    if fav:
        parts.append(f"fav={fav}")
    if boost:
        parts.append(f"boost={boost}")
    if reply:
        parts.append(f"reply={reply}")

    # Media indicator
    media = status.get("media_attachments", [])
    if media:
        types = [m.get("type", "?") for m in media]
        parts.append(f"media={','.join(types)}")

    # Reblog indicator
    reblog = status.get("reblog")
    if reblog:
        parts.append(f"reblog_of={reblog.get('id', '?')}")

    return " | ".join(parts)


def format_timeline(statuses: list[dict[str, Any]]) -> str:
    """Format a list of statuses, one per line."""
    if not statuses:
        return "(no statuses)"
    return "\n".join(format_status(s) for s in statuses)


# ---------------------------------------------------------------------------
# Account formatting
# ---------------------------------------------------------------------------


def format_account(account: dict[str, Any]) -> str:
    """Format an account as pipe-delimited compact line.

    Format: @user@instance | display_name | followers=N | following=N | statuses=N
    """
    parts: list[str] = []
    parts.append(_format_acct(account))

    display_name = account.get("display_name")
    if display_name:
        parts.append(display_name)

    followers = account.get("followers_count")
    following = account.get("following_count")
    statuses = account.get("statuses_count")
    if followers is not None:
        parts.append(f"followers={followers}")
    if following is not None:
        parts.append(f"following={following}")
    if statuses is not None:
        parts.append(f"statuses={statuses}")

    note = account.get("note")
    if note:
        parts.append(f"bio={truncate(strip_html(note), 150)}")

    if account.get("bot"):
        parts.append("BOT")
    if account.get("locked"):
        parts.append("LOCKED")

    return " | ".join(str(p) for p in parts)


def format_account_list(accounts: list[dict[str, Any]]) -> str:
    """Format a list of accounts, one per line."""
    if not accounts:
        return "(no accounts)"
    return "\n".join(format_account(a) for a in accounts)


# ---------------------------------------------------------------------------
# Notification formatting
# ---------------------------------------------------------------------------


def format_notification(notif: dict[str, Any]) -> str:
    """Format a notification as pipe-delimited compact line.

    Format: type | @from | status_id | "excerpt"
    """
    parts: list[str] = []
    parts.append(notif.get("id", "?"))
    parts.append(notif.get("type", "?"))

    account = notif.get("account", {})
    parts.append(_format_acct(account))
    parts.append(_format_timestamp(notif.get("created_at")))

    status = notif.get("status")
    if status:
        parts.append(f"status={status.get('id', '?')}")
        content = strip_html(status.get("content", ""))
        if content:
            parts.append(f'"{truncate(content, 100)}"')

    return " | ".join(parts)


def format_notifications(notifications: list[dict[str, Any]]) -> str:
    """Format a list of notifications, one per line."""
    if not notifications:
        return "(no notifications)"
    return "\n".join(format_notification(n) for n in notifications)


# ---------------------------------------------------------------------------
# Search results
# ---------------------------------------------------------------------------


def format_search_results(results: dict[str, Any]) -> str:
    """Format search results grouped by type with headers."""
    lines: list[str] = []

    accounts = results.get("accounts", [])
    if accounts:
        lines.append(f"## Accounts ({len(accounts)})")
        for a in accounts:
            lines.append(format_account(a))

    statuses = results.get("statuses", [])
    if statuses:
        lines.append(f"## Statuses ({len(statuses)})")
        for s in statuses:
            lines.append(format_status(s))

    hashtags = results.get("hashtags", [])
    if hashtags:
        lines.append(f"## Hashtags ({len(hashtags)})")
        for h in hashtags:
            name = h.get("name", "?")
            url = h.get("url", "")
            history = h.get("history", [])
            uses = sum(int(d.get("uses", 0)) for d in history[:7]) if history else 0
            parts = [f"#{name}"]
            if uses:
                parts.append(f"uses_7d={uses}")
            if url:
                parts.append(url)
            lines.append(" | ".join(parts))

    if not lines:
        return "(no results)"
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Relationships
# ---------------------------------------------------------------------------


def format_relationship(rel: dict[str, Any]) -> str:
    """Format a relationship as pipe-delimited compact line."""
    parts: list[str] = [f"id={rel.get('id', '?')}"]
    flags = []
    if rel.get("following"):
        flags.append("following")
    if rel.get("followed_by"):
        flags.append("followed_by")
    if rel.get("blocking"):
        flags.append("blocking")
    if rel.get("muting"):
        flags.append("muting")
    if rel.get("requested"):
        flags.append("requested")
    if rel.get("domain_blocking"):
        flags.append("domain_blocking")
    if rel.get("showing_reblogs") is False:
        flags.append("hiding_reblogs")
    if rel.get("notifying"):
        flags.append("notifying")
    parts.append(", ".join(flags) if flags else "none")
    note = rel.get("note", "")
    if note:
        parts.append(f'note="{truncate(note, 80)}"')
    return " | ".join(parts)


def format_relationships(rels: list[dict[str, Any]]) -> str:
    """Format a list of relationships, one per line."""
    if not rels:
        return "(no relationships)"
    return "\n".join(format_relationship(r) for r in rels)


# ---------------------------------------------------------------------------
# Conversations
# ---------------------------------------------------------------------------


def format_conversation(conv: dict[str, Any]) -> str:
    """Format a DM conversation as compact line."""
    parts: list[str] = [conv.get("id", "?")]
    accounts = conv.get("accounts", [])
    if accounts:
        accts = [_format_acct(a) for a in accounts[:3]]
        parts.append(", ".join(accts))
    if conv.get("unread"):
        parts.append("UNREAD")
    last_status = conv.get("last_status")
    if last_status:
        content = strip_html(last_status.get("content", ""))
        parts.append(truncate(content, 100))
    return " | ".join(parts)


def format_conversations(convos: list[dict[str, Any]]) -> str:
    """Format a list of conversations, one per line."""
    if not convos:
        return "(no conversations)"
    return "\n".join(format_conversation(c) for c in convos)


# ---------------------------------------------------------------------------
# Lists
# ---------------------------------------------------------------------------


def format_list_entry(lst: dict[str, Any]) -> str:
    """Format a list as compact line."""
    parts = [lst.get("id", "?"), lst.get("title", "?")]
    policy = lst.get("replies_policy")
    if policy:
        parts.append(f"replies={policy}")
    exclusive = lst.get("exclusive")
    if exclusive:
        parts.append("EXCLUSIVE")
    return " | ".join(parts)


def format_lists(lists: list[dict[str, Any]]) -> str:
    """Format all lists, one per line."""
    if not lists:
        return "(no lists)"
    return "\n".join(format_list_entry(lst) for lst in lists)


# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------


def format_filter(f: dict[str, Any]) -> str:
    """Format a content filter as compact line."""
    parts = [f.get("id", "?"), f.get("title", "?")]
    context = f.get("context", [])
    if context:
        parts.append(f"context={','.join(context)}")
    action = f.get("filter_action", "warn")
    parts.append(f"action={action}")
    keywords = f.get("keywords", [])
    if keywords:
        kw_str = ", ".join(k.get("keyword", "?") for k in keywords[:5])
        if len(keywords) > 5:
            kw_str += f" (+{len(keywords) - 5} more)"
        parts.append(f'keywords="{kw_str}"')
    expires = f.get("expires_at")
    if expires:
        parts.append(f"expires={_format_timestamp(expires)}")
    return " | ".join(parts)


def format_filters(filters: list[dict[str, Any]]) -> str:
    """Format content filters, one per line."""
    if not filters:
        return "(no filters)"
    return "\n".join(format_filter(f) for f in filters)


# ---------------------------------------------------------------------------
# Trending
# ---------------------------------------------------------------------------


def format_trending_tags(tags: list[dict[str, Any]]) -> str:
    """Format trending hashtags."""
    if not tags:
        return "(no trending tags)"
    lines = []
    for t in tags:
        name = t.get("name", "?")
        history = t.get("history", [])
        uses_today = int(history[0].get("uses", 0)) if history else 0
        accounts_today = int(history[0].get("accounts", 0)) if history else 0
        parts = [f"#{name}", f"uses_today={uses_today}", f"accounts_today={accounts_today}"]
        lines.append(" | ".join(parts))
    return "\n".join(lines)


def format_trending_links(links: list[dict[str, Any]]) -> str:
    """Format trending links."""
    if not links:
        return "(no trending links)"
    lines = []
    for link in links:
        parts = [link.get("title", "?")]
        url = link.get("url")
        if url:
            parts.append(url)
        desc = link.get("description")
        if desc:
            parts.append(truncate(strip_html(desc), 100))
        history = link.get("history", [])
        if history:
            uses = int(history[0].get("uses", 0))
            parts.append(f"uses_today={uses}")
        lines.append(" | ".join(parts))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Instance info
# ---------------------------------------------------------------------------


def format_instance_info(info: dict[str, Any], write_enabled: bool, rate_status: str) -> str:
    """Format instance info as compact output."""
    parts: list[str] = []

    # V2 API format
    title = info.get("title", info.get("uri", "?"))
    parts.append(title)

    version = info.get("version")
    if version:
        parts.append(f"v{version}")

    domain = info.get("domain", info.get("uri", ""))
    if domain:
        parts.append(domain)

    usage = info.get("usage", {})
    users = usage.get("users", {})
    active = users.get("active_month")
    if active is not None:
        parts.append(f"active_users={active}")

    stats = info.get("stats", {})
    if stats:
        for key in ("user_count", "status_count", "domain_count"):
            val = stats.get(key)
            if val is not None:
                parts.append(f"{key}={val}")

    parts.append(f"write_gate={'enabled' if write_enabled else 'disabled'}")
    parts.append(rate_status)

    return " | ".join(parts)


def format_verify_credentials(account: dict[str, Any]) -> str:
    """Format verified credentials (current user) as compact output."""
    parts: list[str] = [
        _format_acct(account),
        account.get("display_name", ""),
        f"id={account.get('id', '?')}",
        f"followers={account.get('followers_count', 0)}",
        f"following={account.get('following_count', 0)}",
        f"statuses={account.get('statuses_count', 0)}",
    ]
    return " | ".join(p for p in parts if p)


# ---------------------------------------------------------------------------
# Context (thread)
# ---------------------------------------------------------------------------


def format_context(context: dict[str, Any]) -> str:
    """Format thread context (ancestors + descendants)."""
    lines: list[str] = []
    ancestors = context.get("ancestors", [])
    descendants = context.get("descendants", [])

    if ancestors:
        lines.append(f"## Ancestors ({len(ancestors)})")
        for s in ancestors:
            lines.append(format_status(s))

    if descendants:
        lines.append(f"## Descendants ({len(descendants)})")
        for s in descendants:
            lines.append(format_status(s))

    if not lines:
        return "(no thread context)"
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Media upload
# ---------------------------------------------------------------------------


def format_media(media: dict[str, Any]) -> str:
    """Format uploaded media as compact line."""
    parts = [
        f"id={media.get('id', '?')}",
        f"type={media.get('type', '?')}",
    ]
    url = media.get("url") or media.get("preview_url")
    if url:
        parts.append(url)
    desc = media.get("description")
    if desc:
        parts.append(f'alt="{truncate(desc, 100)}"')
    return " | ".join(parts)

"""Mastodon Blade MCP Server -- timelines, statuses, notifications, search, interactions, multi-instance.

Wraps the Mastodon REST API as MCP tools. Token-efficient by default: compact
pipe-delimited output, HTML stripping, null-field omission. Write operations
gated by MASTODON_WRITE_ENABLED. Destructive operations (delete, block, mute)
require explicit confirm=true.
"""

from __future__ import annotations

import logging
import os
import re
import time
from typing import Annotated, Any

from fastmcp import FastMCP
from pydantic import Field
from stallari_mcp_helpers import (
    Pattern,
    compute_domain_hint,
    load_patterns_from_yaml,
)

from mastodon_blade_mcp.client import MastodonClient, MastodonError
from mastodon_blade_mcp.formatters import (
    append_meta,
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
    meta_envelope,
    sort_by_id_asc,
    sort_by_id_desc,
    sort_preserve_rank_tie_break_by,
)
from mastodon_blade_mcp.models import (
    check_confirm_gate,
    check_write_gate,
    is_write_enabled,
)

# ---------------------------------------------------------------------------
# DD-338 A.1 -- scope-tag vocabulary
# ---------------------------------------------------------------------------

_VALID_SCOPES = ("public", "personal", "family", "work")
_SCOPE_ENV_PREFIX = {
    "personal": "MASTODON_PERSONAL_LIST_ID",
    "family": "MASTODON_FAMILY_LIST_ID",
    "work": "MASTODON_WORK_LIST_ID",
}


def _normalise_instance(instance: str | None) -> str:
    """Uppercase + non-alphanumeric -> _, for env var suffix."""
    if not instance:
        return ""
    return re.sub(r"[^A-Z0-9]", "_", instance.upper())


def _resolve_list_id(scope: str, instance: str | None) -> str | None:
    """Map (scope, instance) to a Mastodon list ID via env-var indirection.

    Priority: per-instance suffix (MASTODON_<SCOPE>_LIST_ID_<INSTANCE>) -> bare
    form (MASTODON_<SCOPE>_LIST_ID). Returns None when neither resolves; caller
    surfaces the unconfigured degradation in _meta.redactions.
    """
    if scope not in _SCOPE_ENV_PREFIX:
        return None
    base_env = _SCOPE_ENV_PREFIX[scope]
    suffix = _normalise_instance(instance)
    if suffix:
        per_instance = os.environ.get(f"{base_env}_{suffix}", "").strip()
        if per_instance:
            return per_instance
    bare = os.environ.get(base_env, "").strip()
    return bare or None


def _validate_scope(scope: str | None) -> tuple[str | None, str | None]:
    """Validate scope; return (normalised_scope, error_string_if_invalid)."""
    if scope is None:
        return None, None
    if scope not in _VALID_SCOPES:
        return None, (f"Error: Unknown scope: {scope}. Valid: " + "|".join(_VALID_SCOPES))
    return scope, None


logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# DD-338 A.2.dom.c -- per-record domain hint loader + projector
# ---------------------------------------------------------------------------


def _state_root() -> str:
    """Resolve the Stallari state root (env override or default Application Support path)."""
    return os.environ.get(
        "STALLARI_STATE_ROOT",
        os.path.expanduser("~/Library/Application Support/Stallari"),
    )


def _sanitize_blade_id(blade_id: str) -> str:
    """Sanitize a blade id for filesystem use (matches StallariPaths.bladeConfig case)."""
    return blade_id.lower().replace("/", "_")


def _load_blade_config(blade_id: str) -> list[Pattern]:
    """Load domain-hint patterns for ``blade_id`` from BladeConfigStore.

    Path: ``<state-root>/blade-config/<sanitized-blade-id>/config.yaml``.

    Missing file / IO error / parse error ⇒ empty list (Convention #22
    graceful degradation). Reader of the DD-338 A.2.dom.a substrate contract
    (Convention #23).
    """
    sanitized = _sanitize_blade_id(blade_id)
    path = os.path.join(_state_root(), "blade-config", sanitized, "config.yaml")
    try:
        with open(path, encoding="utf-8") as f:
            content = f.read()
    except OSError:
        return []
    patterns: list[Pattern] = load_patterns_from_yaml(content)
    return patterns


# Module-level cache of patterns (loaded once at import time).
_PATTERNS: list[Pattern] = _load_blade_config("mastodon-blade-mcp")


def _compute_domain_hints(records: list[dict[str, Any]]) -> dict[str, str]:
    """Compute per-record domain hints for a list of status records.

    Returns a ``{status_id: domain}`` mapping. Records that don't match any
    pattern are omitted (no key emitted). Empty when ``_PATTERNS`` is empty.

    DD-338 Phase E.python: delegates to ``stallari_mcp_helpers.compute_domain_hint``
    which uses dot-path field resolution (e.g. ``account.acct``) — the local
    field-projector was retired in favour of canonical dot-path semantics.
    """
    if not _PATTERNS:
        return {}
    out: dict[str, str] = {}
    for rec in records:
        if not isinstance(rec, dict):
            continue
        rec_id = rec.get("id")
        if rec_id is None:
            continue
        hint = compute_domain_hint(rec, _PATTERNS)
        if hint is not None:
            out[str(rec_id)] = hint
    return out


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
    scope: Annotated[
        str | None,
        Field(
            description=(
                "Scope tag (public|personal|family|work). Maps to a Mastodon list via "
                "MASTODON_*_LIST_ID env vars (per-instance suffix supported); scope=public "
                "or omitted is unfiltered."
            )
        ),
    ] = None,
    instance: Annotated[str | None, Field(description="Target instance (omit for default)")] = None,
) -> str:
    """Home timeline -- statuses from followed accounts.

    DD-338 A.1: when scope ∈ {personal,family,work} and the matching list-id env var
    resolves, the request swaps to /api/v1/timelines/list/{list_id}. Unset env var
    degrades to passthrough with _meta.redactions: ["scope=<scope>_unconfigured"].

    DD-338 B.1.b: returns statuses sorted by id descending (newest first);
    ordering is byte-deterministic across invocations.
    """
    norm_scope, scope_err = _validate_scope(scope)
    if scope_err:
        return scope_err
    filtered_by: list[str] = []
    redactions: list[str] = []
    list_id: str | None = None
    if norm_scope and norm_scope != "public":
        list_id = _resolve_list_id(norm_scope, instance)
        if list_id:
            filtered_by.append(f"scope={norm_scope}")
        else:
            redactions.append(f"scope={norm_scope}_unconfigured")
    filtered_by.append(f"limit={limit}")
    if max_id:
        filtered_by.append(f"max_id={max_id}")
    filtered_by.append("sorted_by=id_desc")
    filtered_by.sort()
    start = time.perf_counter()
    try:
        if list_id:
            data, next_cursor = await _get_client().timeline_list_paginated(list_id, limit, max_id, instance)
        else:
            data, next_cursor = await _get_client().timeline_home_paginated(limit, max_id, instance)
        latency_ms = int((time.perf_counter() - start) * 1000)
        data = sort_by_id_desc(data)
        payload = format_timeline(data)
        domain_hints = _compute_domain_hints(data)
        meta = meta_envelope(
            matched_total=len(data),
            returned=len(data),
            filtered_by=filtered_by,
            redactions=redactions,
            next_cursor=next_cursor,
            latency_ms=latency_ms,
            domain_hints=domain_hints or None,
        )
        return append_meta(payload, meta)
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
    """Public (federated) timeline. Set local=true for local-only.

    DD-338 B.1.b: returns statuses sorted by id descending (newest first);
    ordering is byte-deterministic across invocations.

    DD-338 C W4: emits a ``_meta`` envelope describing the filter parameters,
    sort order, and latency (assembler audit trail per DD-287 ContextPacket).
    """
    filtered_by = [f"local={str(bool(local)).lower()}", f"limit={limit}", "sorted_by=id_desc"]
    if max_id:
        filtered_by.append(f"max_id={max_id}")
    filtered_by.sort()
    start = time.perf_counter()
    try:
        data = await _get_client().timeline_public(local, limit, max_id, instance)
        latency_ms = int((time.perf_counter() - start) * 1000)
        data = sort_by_id_desc(data)
        payload = format_timeline(data)
        domain_hints = _compute_domain_hints(data)
        meta = meta_envelope(
            matched_total=len(data),
            returned=len(data),
            filtered_by=filtered_by,
            redactions=[],
            next_cursor=None,
            latency_ms=latency_ms,
            domain_hints=domain_hints or None,
        )
        return append_meta(payload, meta)
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
    """Local instance timeline (convenience wrapper for public timeline with local=true).

    DD-338 B.1.b: returns statuses sorted by id descending (newest first);
    ordering is byte-deterministic across invocations.

    DD-338 C W4: emits a ``_meta`` envelope describing the filter parameters,
    sort order, and latency (assembler audit trail per DD-287 ContextPacket).
    """
    filtered_by = ["local=true", f"limit={limit}", "sorted_by=id_desc"]
    if max_id:
        filtered_by.append(f"max_id={max_id}")
    filtered_by.sort()
    start = time.perf_counter()
    try:
        data = await _get_client().timeline_public(local=True, limit=limit, max_id=max_id, instance=instance)
        latency_ms = int((time.perf_counter() - start) * 1000)
        data = sort_by_id_desc(data)
        payload = format_timeline(data)
        domain_hints = _compute_domain_hints(data)
        meta = meta_envelope(
            matched_total=len(data),
            returned=len(data),
            filtered_by=filtered_by,
            redactions=[],
            next_cursor=None,
            latency_ms=latency_ms,
            domain_hints=domain_hints or None,
        )
        return append_meta(payload, meta)
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
    """Hashtag timeline -- statuses tagged with a specific hashtag.

    DD-338 B.1.b: returns statuses sorted by id descending (newest first);
    ordering is byte-deterministic across invocations.

    DD-338 C W4: emits a ``_meta`` envelope describing the filter parameters,
    sort order, and latency (assembler audit trail per DD-287 ContextPacket).
    """
    filtered_by = [
        f"hashtag={hashtag}",
        f"limit={limit}",
        f"local={str(bool(local)).lower()}",
        "sorted_by=id_desc",
    ]
    if max_id:
        filtered_by.append(f"max_id={max_id}")
    filtered_by.sort()
    start = time.perf_counter()
    try:
        data = await _get_client().timeline_hashtag(hashtag, limit, max_id, local, instance)
        latency_ms = int((time.perf_counter() - start) * 1000)
        data = sort_by_id_desc(data)
        payload = format_timeline(data)
        domain_hints = _compute_domain_hints(data)
        meta = meta_envelope(
            matched_total=len(data),
            returned=len(data),
            filtered_by=filtered_by,
            redactions=[],
            next_cursor=None,
            latency_ms=latency_ms,
            domain_hints=domain_hints or None,
        )
        return append_meta(payload, meta)
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
    """List timeline -- statuses from accounts in a specific list.

    DD-338 B.1.b: returns statuses sorted by id descending (newest first);
    ordering is byte-deterministic across invocations.

    DD-338 C W4: emits a ``_meta`` envelope describing the filter parameters,
    sort order, and latency (assembler audit trail per DD-287 ContextPacket).
    """
    filtered_by = [f"limit={limit}", f"list_id={list_id}", "sorted_by=id_desc"]
    if max_id:
        filtered_by.append(f"max_id={max_id}")
    filtered_by.sort()
    start = time.perf_counter()
    try:
        data = await _get_client().timeline_list(list_id, limit, max_id, instance)
        latency_ms = int((time.perf_counter() - start) * 1000)
        data = sort_by_id_desc(data)
        payload = format_timeline(data)
        domain_hints = _compute_domain_hints(data)
        meta = meta_envelope(
            matched_total=len(data),
            returned=len(data),
            filtered_by=filtered_by,
            redactions=[],
            next_cursor=None,
            latency_ms=latency_ms,
            domain_hints=domain_hints or None,
        )
        return append_meta(payload, meta)
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
    """Thread context -- ancestors and descendants of a status.

    DD-338 C W4 (OQ-6): ancestors + descendants are each sorted by id descending
    to honestly meet the catalog ``deterministic_ordering: stable`` declaration.
    Emits a ``_meta`` envelope describing the seed status, sort order, and
    latency (assembler audit trail per DD-287 ContextPacket).
    """
    filtered_by = [f"status_id={status_id}", "sorted_by=id_desc"]
    filtered_by.sort()
    start = time.perf_counter()
    try:
        data = await _get_client().get_context(status_id, instance)
        latency_ms = int((time.perf_counter() - start) * 1000)
        # DD-338 OQ-6: sort each bucket independently for byte-deterministic ordering.
        if isinstance(data, dict):
            data = dict(data)
            data["ancestors"] = sort_by_id_desc(list(data.get("ancestors", []) or []))
            data["descendants"] = sort_by_id_desc(list(data.get("descendants", []) or []))
        all_statuses: list[dict[str, Any]] = []
        if isinstance(data, dict):
            all_statuses = list(data.get("ancestors", []) or []) + list(data.get("descendants", []) or [])
        matched_total = len(all_statuses)
        payload = format_context(data)
        domain_hints = _compute_domain_hints(all_statuses)
        meta = meta_envelope(
            matched_total=matched_total,
            returned=matched_total,
            filtered_by=filtered_by,
            redactions=[],
            next_cursor=None,
            latency_ms=latency_ms,
            domain_hints=domain_hints or None,
        )
        return append_meta(payload, meta)
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
    scope: Annotated[
        str | None,
        Field(
            description=(
                "Scope tag (public|personal|family|work). Restricts status results to "
                "accounts in the scope's list (accounts + hashtags pass through). "
                "scope=public or omitted is unfiltered."
            )
        ),
    ] = None,
    instance: Annotated[str | None, Field(description="Target instance (omit for default)")] = None,
) -> str:
    """Unified search across accounts, statuses, and hashtags.

    DD-338 A.1: when scope ∈ {personal,family,work} and the matching list-id env var
    resolves, the ``statuses`` portion of results is filtered to authors in the list.
    Accounts and hashtags are not scope-filtered (scope vocabulary doesn't apply).

    DD-338 B.1.b: each result bucket is sorted independently for byte-deterministic
    ordering -- accounts and statuses by id descending; hashtags alphabetically by
    name.
    """
    norm_scope, scope_err = _validate_scope(scope)
    if scope_err:
        return scope_err
    filtered_by: list[str] = [f"limit={limit}"]
    if type:
        filtered_by.append(f"type={type}")
    redactions: list[str] = []
    member_ids: set[str] | None = None
    list_id: str | None = None
    if norm_scope and norm_scope != "public":
        list_id = _resolve_list_id(norm_scope, instance)
        if list_id:
            try:
                member_ids = await _get_client().list_accounts_cached(list_id, instance)
                filtered_by.append(f"scope={norm_scope}:statuses_only")
            except MastodonError:
                redactions.append("list_membership_unavailable")
        else:
            redactions.append(f"scope={norm_scope}_unconfigured")
    filtered_by.append("sorted_by=id_desc:accounts,statuses;name_asc:hashtags")
    filtered_by.sort()
    start = time.perf_counter()
    try:
        data, next_cursor = await _get_client().search_paginated(q, type, limit, instance)
        latency_ms = int((time.perf_counter() - start) * 1000)
        statuses = list(data.get("statuses", []) or [])
        matched_total = len(data.get("accounts", []) or []) + len(statuses) + len(data.get("hashtags", []) or [])
        if member_ids is not None:
            filtered_statuses = [s for s in statuses if str(s.get("account", {}).get("id", "")) in member_ids]
            data = dict(data)
            data["statuses"] = filtered_statuses
        # DD-338 B.1.b: per-bucket sort (after scope-filter, before format).
        data = dict(data)
        data["accounts"] = sort_by_id_desc(list(data.get("accounts", []) or []))
        data["statuses"] = sort_by_id_desc(list(data.get("statuses", []) or []))
        data["hashtags"] = sorted(
            list(data.get("hashtags", []) or []),
            key=lambda h: h.get("name", "") if isinstance(h, dict) else "",
        )
        returned = (
            len(data.get("accounts", []) or [])
            + len(data.get("statuses", []) or [])
            + len(data.get("hashtags", []) or [])
        )
        payload = format_search_results(data)
        domain_hints = _compute_domain_hints(list(data.get("statuses", []) or []))
        meta = meta_envelope(
            matched_total=matched_total,
            returned=returned,
            filtered_by=filtered_by,
            redactions=redactions,
            next_cursor=next_cursor,
            latency_ms=latency_ms,
            domain_hints=domain_hints or None,
        )
        return append_meta(payload, meta)
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
    scope: Annotated[
        str | None,
        Field(
            description=(
                "Scope tag (public|personal|family|work) used as a membership precondition: "
                "refuses if account_id is outside the scope's list. scope=public or omitted "
                "bypasses the precondition."
            )
        ),
    ] = None,
    instance: Annotated[str | None, Field(description="Target instance (omit for default)")] = None,
) -> str:
    """Get an account's statuses with filtering options.

    DD-338 A.1: scope is a membership *precondition* (not a result filter) -- if
    ``account_id`` is not in the scope's list, returns an Error with
    ``_meta.redactions: ["account_outside_scope"]``.

    DD-338 B.1.b: returns statuses sorted by id descending (newest first);
    ordering is byte-deterministic across invocations.
    """
    norm_scope, scope_err = _validate_scope(scope)
    if scope_err:
        return scope_err
    filtered_by: list[str] = [f"limit={limit}"]
    if exclude_reblogs:
        filtered_by.append("exclude_reblogs=true")
    if only_media:
        filtered_by.append("only_media=true")
    if pinned:
        filtered_by.append("pinned=true")
    filtered_by.append("sorted_by=id_desc")
    redactions: list[str] = []
    precondition_failed = False
    list_id: str | None = None
    if norm_scope and norm_scope != "public":
        list_id = _resolve_list_id(norm_scope, instance)
        if list_id:
            try:
                member_ids = await _get_client().list_accounts_cached(list_id, instance)
                if str(account_id) not in member_ids:
                    redactions.append("account_outside_scope")
                    precondition_failed = True
                else:
                    filtered_by.append(f"scope={norm_scope}")
            except MastodonError:
                redactions.append("list_membership_unavailable")
        else:
            redactions.append(f"scope={norm_scope}_unconfigured")
    filtered_by.sort()
    if precondition_failed:
        meta = meta_envelope(
            matched_total=0,
            returned=0,
            filtered_by=filtered_by,
            redactions=redactions,
            next_cursor=None,
            latency_ms=0,
        )
        return append_meta(
            f"Error: account_id not in scope={norm_scope} list",
            meta,
        )
    start = time.perf_counter()
    try:
        data, next_cursor = await _get_client().get_account_statuses_paginated(
            account_id, limit, max_id, exclude_reblogs, only_media, pinned, instance
        )
        latency_ms = int((time.perf_counter() - start) * 1000)
        data = sort_by_id_desc(data)
        payload = format_timeline(data)
        domain_hints = _compute_domain_hints(data)
        meta = meta_envelope(
            matched_total=len(data),
            returned=len(data),
            filtered_by=filtered_by,
            redactions=redactions,
            next_cursor=next_cursor,
            latency_ms=latency_ms,
            domain_hints=domain_hints or None,
        )
        return append_meta(payload, meta)
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
    """Check relationships with one or more accounts (following, blocked, muted, etc.).

    DD-338 C W4 (OQ-6): relationships are sorted by id ascending (account-id
    creation order) to honestly meet the catalog ``deterministic_ordering:
    stable`` declaration. Emits a ``_meta`` envelope describing the input
    cardinality, sort order, and latency (assembler audit trail per DD-287).
    """
    filtered_by = [f"account_ids={len(account_ids)}", "sorted_by=id_asc"]
    filtered_by.sort()
    start = time.perf_counter()
    try:
        data = await _get_client().get_relationships(account_ids, instance)
        latency_ms = int((time.perf_counter() - start) * 1000)
        # DD-338 OQ-6: sort by id ascending for byte-deterministic ordering.
        data = sort_by_id_asc(data)
        payload = format_relationships(data)
        meta = meta_envelope(
            matched_total=len(data),
            returned=len(data),
            filtered_by=filtered_by,
            redactions=[],
            next_cursor=None,
            latency_ms=latency_ms,
        )
        return append_meta(payload, meta)
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
    """List followers of an account.

    DD-338 B.1.b: returns accounts sorted by id descending (newest-followers
    first); ordering is byte-deterministic across invocations.

    DD-338 C W4: emits a ``_meta`` envelope describing the filter parameters,
    sort order, and latency (assembler audit trail per DD-287 ContextPacket).
    """
    filtered_by = [f"account_id={account_id}", f"limit={limit}", "sorted_by=id_desc"]
    filtered_by.sort()
    start = time.perf_counter()
    try:
        data = await _get_client().get_followers(account_id, limit, instance)
        latency_ms = int((time.perf_counter() - start) * 1000)
        data = sort_by_id_desc(data)
        payload = format_account_list(data)
        meta = meta_envelope(
            matched_total=len(data),
            returned=len(data),
            filtered_by=filtered_by,
            redactions=[],
            next_cursor=None,
            latency_ms=latency_ms,
        )
        return append_meta(payload, meta)
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
    """List accounts followed by an account.

    DD-338 B.1.b: returns accounts sorted by id descending (newest-followed
    first); ordering is byte-deterministic across invocations.

    DD-338 C W4: emits a ``_meta`` envelope describing the filter parameters,
    sort order, and latency (assembler audit trail per DD-287 ContextPacket).
    """
    filtered_by = [f"account_id={account_id}", f"limit={limit}", "sorted_by=id_desc"]
    filtered_by.sort()
    start = time.perf_counter()
    try:
        data = await _get_client().get_following(account_id, limit, instance)
        latency_ms = int((time.perf_counter() - start) * 1000)
        data = sort_by_id_desc(data)
        payload = format_account_list(data)
        meta = meta_envelope(
            matched_total=len(data),
            returned=len(data),
            filtered_by=filtered_by,
            redactions=[],
            next_cursor=None,
            latency_ms=latency_ms,
        )
        return append_meta(payload, meta)
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
    scope: Annotated[
        str | None,
        Field(
            description=(
                "Scope tag (public|personal|family|work). Filters notifications to those "
                "whose acting account (mentioner/favouriter/follower) is in the scope's list. "
                "Does NOT filter by status author. scope=public or omitted is unfiltered."
            )
        ),
    ] = None,
    instance: Annotated[str | None, Field(description="Target instance (omit for default)")] = None,
) -> str:
    """List notifications, optionally filtered by type.

    DD-338 A.1: scope filters by the notification's *actor* (the account who
    mentioned/favourited/followed/etc the authenticated user), not by status author.

    DD-338 B.1.b: returns notifications sorted by id descending (newest first);
    ordering is byte-deterministic across invocations.
    """
    norm_scope, scope_err = _validate_scope(scope)
    if scope_err:
        return scope_err
    filtered_by: list[str] = [f"limit={limit}"]
    if types:
        filtered_by.append(f"types={','.join(sorted(types))}")
    redactions: list[str] = []
    member_ids: set[str] | None = None
    list_id: str | None = None
    if norm_scope and norm_scope != "public":
        list_id = _resolve_list_id(norm_scope, instance)
        if list_id:
            try:
                member_ids = await _get_client().list_accounts_cached(list_id, instance)
                filtered_by.append(f"scope={norm_scope}")
            except MastodonError:
                redactions.append("list_membership_unavailable")
        else:
            redactions.append(f"scope={norm_scope}_unconfigured")
    filtered_by.append("sorted_by=id_desc")
    filtered_by.sort()
    start = time.perf_counter()
    try:
        data, next_cursor = await _get_client().get_notifications_paginated(types, limit, max_id, instance)
        latency_ms = int((time.perf_counter() - start) * 1000)
        matched_total = len(data)
        if member_ids is not None:
            data = [n for n in data if str(n.get("account", {}).get("id", "")) in member_ids]
        data = sort_by_id_desc(data)
        returned = len(data)
        payload = format_notifications(data)
        # Domain hints: prefer the embedded status (when present) for hint
        # computation since pattern fields like tags / mentions / content live
        # there. Notifications without a status (e.g. plain follow) get no hint.
        notif_hints: dict[str, str] = {}
        if _PATTERNS:
            for notif in data:
                if not isinstance(notif, dict):
                    continue
                notif_id = notif.get("id")
                if notif_id is None:
                    continue
                status = notif.get("status")
                if not isinstance(status, dict):
                    continue
                hint = compute_domain_hint(status, _PATTERNS)
                if hint is not None:
                    notif_hints[str(notif_id)] = hint
        meta = meta_envelope(
            matched_total=matched_total,
            returned=returned,
            filtered_by=filtered_by,
            redactions=redactions,
            next_cursor=next_cursor,
            latency_ms=latency_ms,
            domain_hints=notif_hints or None,
        )
        return append_meta(payload, meta)
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
    """Trending hashtags on the instance.

    DD-338 B.1.b: preserves server-returned trending rank; ties break on
    ``name`` ascending for byte-deterministic ordering.

    DD-338 C W4: emits a ``_meta`` envelope describing the limit, rank-preserve
    sort discipline, and latency (assembler audit trail per DD-287).
    """
    filtered_by = [f"limit={limit}", "sorted_by=server_rank;tie_name_asc"]
    filtered_by.sort()
    start = time.perf_counter()
    try:
        data = await _get_client().trending_tags(limit, instance)
        latency_ms = int((time.perf_counter() - start) * 1000)
        data = sort_preserve_rank_tie_break_by(
            data,
            tie_key=lambda r: r.get("name", "") if isinstance(r, dict) else "",
        )
        payload = format_trending_tags(data)
        meta = meta_envelope(
            matched_total=len(data),
            returned=len(data),
            filtered_by=filtered_by,
            redactions=[],
            next_cursor=None,
            latency_ms=latency_ms,
        )
        return append_meta(payload, meta)
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
    """Trending statuses on the instance.

    DD-338 B.1.b: preserves server-returned trending rank; ties break on
    ``id`` descending (snowflake newer-first) for byte-deterministic ordering.

    DD-338 C W4: emits a ``_meta`` envelope describing the limit, rank-preserve
    sort discipline, and latency (assembler audit trail per DD-287).
    """
    filtered_by = [f"limit={limit}", "sorted_by=server_rank;tie_id_desc"]
    filtered_by.sort()
    start = time.perf_counter()
    try:
        data = await _get_client().trending_statuses(limit, instance)
        latency_ms = int((time.perf_counter() - start) * 1000)

        def _id_desc_tie(rec: dict[str, Any]) -> int:
            raw = rec.get("id") if isinstance(rec, dict) else None
            if raw is None:
                return 0
            try:
                return -int(raw)
            except (TypeError, ValueError):
                return 0

        data = sort_preserve_rank_tie_break_by(data, tie_key=_id_desc_tie)
        payload = format_timeline(data)
        domain_hints = _compute_domain_hints(data)
        meta = meta_envelope(
            matched_total=len(data),
            returned=len(data),
            filtered_by=filtered_by,
            redactions=[],
            next_cursor=None,
            latency_ms=latency_ms,
            domain_hints=domain_hints or None,
        )
        return append_meta(payload, meta)
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
    """Trending links shared on the instance.

    DD-338 B.1.b: preserves server-returned trending rank; ties break on
    ``url`` ascending for byte-deterministic ordering.

    DD-338 C W4: emits a ``_meta`` envelope describing the limit, rank-preserve
    sort discipline, and latency (assembler audit trail per DD-287).
    """
    filtered_by = [f"limit={limit}", "sorted_by=server_rank;tie_url_asc"]
    filtered_by.sort()
    start = time.perf_counter()
    try:
        data = await _get_client().trending_links(limit, instance)
        latency_ms = int((time.perf_counter() - start) * 1000)
        data = sort_preserve_rank_tie_break_by(
            data,
            tie_key=lambda r: r.get("url", "") if isinstance(r, dict) else "",
        )
        payload = format_trending_links(data)
        meta = meta_envelope(
            matched_total=len(data),
            returned=len(data),
            filtered_by=filtered_by,
            redactions=[],
            next_cursor=None,
            latency_ms=latency_ms,
        )
        return append_meta(payload, meta)
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
    """List bookmarked statuses.

    DD-338 B.1.b: returns statuses sorted by id descending (newest-bookmarked
    first); ordering is byte-deterministic across invocations.
    """
    try:
        data = await _get_client().get_bookmarks(limit, max_id, instance)
        data = sort_by_id_desc(data)
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
    """List favourited statuses.

    DD-338 B.1.b: returns statuses sorted by id descending (newest-favourited
    first); ordering is byte-deterministic across invocations.
    """
    try:
        data = await _get_client().get_favourites(limit, max_id, instance)
        data = sort_by_id_desc(data)
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
    """List all lists.

    DD-338 B.1.b: returns lists sorted by id ascending (creation order);
    ordering is byte-deterministic across invocations.
    """
    try:
        data = await _get_client().get_lists(instance)
        data = sort_by_id_asc(data)
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
    """Get accounts in a specific list.

    DD-338 B.1.b: returns accounts sorted by id descending; ordering is
    byte-deterministic across invocations.

    DD-338 C W4: emits a ``_meta`` envelope describing the filter parameters,
    sort order, and latency (assembler audit trail per DD-287 ContextPacket).
    """
    filtered_by = [f"limit={limit}", f"list_id={list_id}", "sorted_by=id_desc"]
    filtered_by.sort()
    start = time.perf_counter()
    try:
        data = await _get_client().get_list_accounts(list_id, limit, instance)
        latency_ms = int((time.perf_counter() - start) * 1000)
        data = sort_by_id_desc(data)
        payload = format_account_list(data)
        meta = meta_envelope(
            matched_total=len(data),
            returned=len(data),
            filtered_by=filtered_by,
            redactions=[],
            next_cursor=None,
            latency_ms=latency_ms,
        )
        return append_meta(payload, meta)
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
    """List direct message conversations.

    DD-338 B.1.b: returns conversations sorted by id descending (newest-activity
    first); ordering is byte-deterministic across invocations.
    """
    try:
        data = await _get_client().get_conversations(limit, max_id, instance)
        data = sort_by_id_desc(data)
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
    """List active content filters (v2 API with v1 fallback).

    DD-338 B.1.b: returns filters sorted by id ascending (creation order);
    ordering is byte-deterministic across invocations. The ``int(id)`` cast
    handles both v2 (integer-shaped) and v1 (string-shaped) filter ids per
    spec architect amendment OQ-2.
    """
    try:
        data = await _get_client().get_filters(instance)
        data = sort_by_id_asc(data)
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

"""Mastodon client -- async httpx with multi-instance support.

Wraps the Mastodon REST API with rate limiting, credential scrubbing,
typed exceptions, and Link header pagination parsing.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from mastodon_blade_mcp.models import MastodonError, ProviderConfig, resolve_providers, scrub_credentials
from mastodon_blade_mcp.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class AuthError(MastodonError):
    """Authentication failed -- invalid or expired token."""


class NotFoundError(MastodonError):
    """Requested resource not found."""


class RateLimitError(MastodonError):
    """Rate limit exceeded."""


class ConnectionError(MastodonError):  # noqa: A001
    """Cannot connect to Mastodon instance."""


# ---------------------------------------------------------------------------
# Error classification
# ---------------------------------------------------------------------------

_ERROR_PATTERNS: list[tuple[str, type[MastodonError]]] = [
    ("unauthorized", AuthError),
    ("401", AuthError),
    ("invalid access token", AuthError),
    ("forbidden", AuthError),
    ("403", AuthError),
    ("not found", NotFoundError),
    ("404", NotFoundError),
    ("429", RateLimitError),
    ("rate limit", RateLimitError),
    ("connection", ConnectionError),
    ("timeout", ConnectionError),
    ("unreachable", ConnectionError),
    ("connect error", ConnectionError),
]


def _classify_error(message: str) -> MastodonError:
    """Map error message to a typed exception."""
    lower = message.lower()
    for pattern, exc_cls in _ERROR_PATTERNS:
        if pattern in lower:
            return exc_cls(message)
    return MastodonError(message)


def _parse_link_header(header: str) -> dict[str, str]:
    """Parse Link header into rel->url dict.

    Example: '<https://mastodon.social/api/v1/...?max_id=123>; rel="next"'
    """
    links: dict[str, str] = {}
    if not header:
        return links
    for part in header.split(","):
        part = part.strip()
        if ";" not in part:
            continue
        url_part, _, rel_part = part.partition(";")
        url = url_part.strip().strip("<>")
        rel = ""
        for segment in rel_part.split(";"):
            segment = segment.strip()
            if segment.startswith('rel="'):
                rel = segment[5:].rstrip('"')
        if url and rel:
            links[rel] = url
    return links


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class MastodonClient:
    """Multi-provider Mastodon API client.

    Manages httpx clients and rate limiters, one per provider.
    """

    def __init__(self) -> None:
        self._providers = resolve_providers()
        self._http: dict[str, httpx.AsyncClient] = {}
        self._rate_limiter = RateLimiter()

    @property
    def provider_names(self) -> list[str]:
        """Return configured provider names."""
        return [p.name for p in self._providers]

    def _get_http(self, provider: ProviderConfig) -> httpx.AsyncClient:
        """Get or create an httpx client for a provider."""
        if provider.name not in self._http:
            self._http[provider.name] = httpx.AsyncClient(
                base_url=provider.instance_url,
                headers={
                    "Authorization": f"Bearer {provider.token}",
                    "Accept": "application/json",
                },
                timeout=30.0,
            )
        return self._http[provider.name]

    def _resolve_provider(self, instance: str | None) -> ProviderConfig:
        """Resolve instance name to a single provider config."""
        if instance:
            for p in self._providers:
                if p.name == instance:
                    return p
            available = ", ".join(p.name for p in self._providers)
            raise MastodonError(f"Unknown instance: {instance}. Available: {available}")
        return self._providers[0]

    # -----------------------------------------------------------------------
    # Request transport
    # -----------------------------------------------------------------------

    async def _request(
        self,
        method: str,
        path: str,
        instance: str | None = None,
        **kwargs: Any,
    ) -> tuple[Any, dict[str, str]]:
        """Execute an API request with rate limiting and error handling.

        Returns (response_json, pagination_links).
        """
        provider = self._resolve_provider(instance)
        await self._rate_limiter.wait_if_needed(provider.name)

        try:
            client = self._get_http(provider)
            response = await client.request(method, path, **kwargs)
            self._rate_limiter.update_from_response(provider.name, response)

            if response.status_code == 401:
                raise AuthError(f"Authentication failed for {provider.name}")
            if response.status_code == 404:
                raise NotFoundError(f"Not found: {path}")
            if response.status_code == 429:
                raise RateLimitError(f"Rate limited on {provider.name}")
            response.raise_for_status()

            # Parse pagination
            link_header = response.headers.get("Link", "")
            pagination = _parse_link_header(link_header)

            ct = response.headers.get("content-type", "")
            if ct.startswith("application/json"):
                return response.json(), pagination
            return response.text, pagination

        except (httpx.ConnectError, httpx.TimeoutException) as e:
            raise ConnectionError(
                scrub_credentials(f"Connection failed for {provider.name}: {e}", self._providers)
            ) from e
        except httpx.HTTPStatusError as e:
            raise _classify_error(scrub_credentials(str(e), self._providers)) from e

    # -----------------------------------------------------------------------
    # Meta
    # -----------------------------------------------------------------------

    async def instance_info(self, instance: str | None = None) -> dict[str, Any]:
        """Get instance information (v2 API, fallback to v1)."""
        try:
            data, _ = await self._request("GET", "/api/v2/instance", instance)
            return data  # type: ignore[no-any-return]
        except (NotFoundError, MastodonError):
            data, _ = await self._request("GET", "/api/v1/instance", instance)
            return data  # type: ignore[no-any-return]

    async def verify_credentials(self, instance: str | None = None) -> dict[str, Any]:
        """Verify credentials and return current user account."""
        data, _ = await self._request("GET", "/api/v1/accounts/verify_credentials", instance)
        return data  # type: ignore[no-any-return]

    def get_rate_status(self, instance: str | None = None) -> str:
        """Get formatted rate limit status for an instance."""
        provider = self._resolve_provider(instance)
        return self._rate_limiter.format_status(provider.name)

    # -----------------------------------------------------------------------
    # Timelines
    # -----------------------------------------------------------------------

    async def timeline_home(
        self,
        limit: int = 20,
        max_id: str | None = None,
        instance: str | None = None,
    ) -> list[dict[str, Any]]:
        """Home timeline -- statuses from followed accounts."""
        params: dict[str, str | int] = {"limit": min(limit, 40)}
        if max_id:
            params["max_id"] = max_id
        data, _ = await self._request("GET", "/api/v1/timelines/home", instance, params=params)
        return data  # type: ignore[no-any-return]

    async def timeline_public(
        self,
        local: bool = False,
        limit: int = 20,
        max_id: str | None = None,
        instance: str | None = None,
    ) -> list[dict[str, Any]]:
        """Public (federated) or local timeline."""
        params: dict[str, str | int | bool] = {"limit": min(limit, 40)}
        if local:
            params["local"] = True
        if max_id:
            params["max_id"] = max_id
        data, _ = await self._request("GET", "/api/v1/timelines/public", instance, params=params)
        return data  # type: ignore[no-any-return]

    async def timeline_hashtag(
        self,
        hashtag: str,
        limit: int = 20,
        max_id: str | None = None,
        local: bool = False,
        instance: str | None = None,
    ) -> list[dict[str, Any]]:
        """Hashtag timeline."""
        params: dict[str, str | int | bool] = {"limit": min(limit, 40)}
        if local:
            params["local"] = True
        if max_id:
            params["max_id"] = max_id
        tag = hashtag.lstrip("#")
        data, _ = await self._request("GET", f"/api/v1/timelines/tag/{tag}", instance, params=params)
        return data  # type: ignore[no-any-return]

    async def timeline_list(
        self,
        list_id: str,
        limit: int = 20,
        max_id: str | None = None,
        instance: str | None = None,
    ) -> list[dict[str, Any]]:
        """List timeline."""
        params: dict[str, str | int] = {"limit": min(limit, 40)}
        if max_id:
            params["max_id"] = max_id
        data, _ = await self._request("GET", f"/api/v1/timelines/list/{list_id}", instance, params=params)
        return data  # type: ignore[no-any-return]

    # -----------------------------------------------------------------------
    # Statuses
    # -----------------------------------------------------------------------

    async def get_status(self, status_id: str, instance: str | None = None) -> dict[str, Any]:
        """Get a specific status by ID."""
        data, _ = await self._request("GET", f"/api/v1/statuses/{status_id}", instance)
        return data  # type: ignore[no-any-return]

    async def get_context(self, status_id: str, instance: str | None = None) -> dict[str, Any]:
        """Get thread context (ancestors + descendants) for a status."""
        data, _ = await self._request("GET", f"/api/v1/statuses/{status_id}/context", instance)
        return data  # type: ignore[no-any-return]

    async def post_status(
        self,
        text: str,
        visibility: str = "public",
        spoiler_text: str | None = None,
        in_reply_to_id: str | None = None,
        media_ids: list[str] | None = None,
        sensitive: bool = False,
        language: str | None = None,
        scheduled_at: str | None = None,
        instance: str | None = None,
    ) -> dict[str, Any]:
        """Create a new status."""
        body: dict[str, Any] = {
            "status": text,
            "visibility": visibility,
        }
        if spoiler_text:
            body["spoiler_text"] = spoiler_text
        if in_reply_to_id:
            body["in_reply_to_id"] = in_reply_to_id
        if media_ids:
            body["media_ids"] = media_ids
        if sensitive:
            body["sensitive"] = True
        if language:
            body["language"] = language
        if scheduled_at:
            body["scheduled_at"] = scheduled_at

        data, _ = await self._request("POST", "/api/v1/statuses", instance, json=body)
        return data  # type: ignore[no-any-return]

    async def edit_status(
        self,
        status_id: str,
        text: str,
        spoiler_text: str | None = None,
        sensitive: bool | None = None,
        media_ids: list[str] | None = None,
        instance: str | None = None,
    ) -> dict[str, Any]:
        """Edit an existing status."""
        body: dict[str, Any] = {"status": text}
        if spoiler_text is not None:
            body["spoiler_text"] = spoiler_text
        if sensitive is not None:
            body["sensitive"] = sensitive
        if media_ids is not None:
            body["media_ids"] = media_ids
        data, _ = await self._request("PUT", f"/api/v1/statuses/{status_id}", instance, json=body)
        return data  # type: ignore[no-any-return]

    async def delete_status(self, status_id: str, instance: str | None = None) -> dict[str, Any]:
        """Delete a status."""
        data, _ = await self._request("DELETE", f"/api/v1/statuses/{status_id}", instance)
        return data  # type: ignore[no-any-return]

    async def favourite_status(self, status_id: str, instance: str | None = None) -> dict[str, Any]:
        """Favourite a status."""
        data, _ = await self._request("POST", f"/api/v1/statuses/{status_id}/favourite", instance)
        return data  # type: ignore[no-any-return]

    async def unfavourite_status(self, status_id: str, instance: str | None = None) -> dict[str, Any]:
        """Unfavourite a status."""
        data, _ = await self._request("POST", f"/api/v1/statuses/{status_id}/unfavourite", instance)
        return data  # type: ignore[no-any-return]

    async def reblog_status(self, status_id: str, instance: str | None = None) -> dict[str, Any]:
        """Reblog (boost) a status."""
        data, _ = await self._request("POST", f"/api/v1/statuses/{status_id}/reblog", instance)
        return data  # type: ignore[no-any-return]

    async def unreblog_status(self, status_id: str, instance: str | None = None) -> dict[str, Any]:
        """Un-reblog (unboost) a status."""
        data, _ = await self._request("POST", f"/api/v1/statuses/{status_id}/unreblog", instance)
        return data  # type: ignore[no-any-return]

    async def bookmark_status(self, status_id: str, instance: str | None = None) -> dict[str, Any]:
        """Bookmark a status."""
        data, _ = await self._request("POST", f"/api/v1/statuses/{status_id}/bookmark", instance)
        return data  # type: ignore[no-any-return]

    async def unbookmark_status(self, status_id: str, instance: str | None = None) -> dict[str, Any]:
        """Remove bookmark from a status."""
        data, _ = await self._request("POST", f"/api/v1/statuses/{status_id}/unbookmark", instance)
        return data  # type: ignore[no-any-return]

    async def pin_status(self, status_id: str, instance: str | None = None) -> dict[str, Any]:
        """Pin a status to profile."""
        data, _ = await self._request("POST", f"/api/v1/statuses/{status_id}/pin", instance)
        return data  # type: ignore[no-any-return]

    async def unpin_status(self, status_id: str, instance: str | None = None) -> dict[str, Any]:
        """Unpin a status from profile."""
        data, _ = await self._request("POST", f"/api/v1/statuses/{status_id}/unpin", instance)
        return data  # type: ignore[no-any-return]

    # -----------------------------------------------------------------------
    # Search
    # -----------------------------------------------------------------------

    async def search(
        self,
        q: str,
        search_type: str | None = None,
        limit: int = 20,
        instance: str | None = None,
    ) -> dict[str, Any]:
        """Unified search across accounts, statuses, and hashtags."""
        params: dict[str, str | int] = {"q": q, "limit": min(limit, 40)}
        if search_type:
            params["type"] = search_type
        data, _ = await self._request("GET", "/api/v2/search", instance, params=params)
        return data  # type: ignore[no-any-return]

    # -----------------------------------------------------------------------
    # Accounts
    # -----------------------------------------------------------------------

    async def get_account(self, account_id: str, instance: str | None = None) -> dict[str, Any]:
        """Get account info by ID."""
        data, _ = await self._request("GET", f"/api/v1/accounts/{account_id}", instance)
        return data  # type: ignore[no-any-return]

    async def get_account_statuses(
        self,
        account_id: str,
        limit: int = 20,
        max_id: str | None = None,
        exclude_reblogs: bool = False,
        only_media: bool = False,
        pinned: bool = False,
        instance: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get an account's statuses."""
        params: dict[str, str | int | bool] = {"limit": min(limit, 40)}
        if max_id:
            params["max_id"] = max_id
        if exclude_reblogs:
            params["exclude_reblogs"] = True
        if only_media:
            params["only_media"] = True
        if pinned:
            params["pinned"] = True
        data, _ = await self._request("GET", f"/api/v1/accounts/{account_id}/statuses", instance, params=params)
        return data  # type: ignore[no-any-return]

    async def get_relationships(
        self,
        account_ids: list[str],
        instance: str | None = None,
    ) -> list[dict[str, Any]]:
        """Check relationships with accounts."""
        params_list = [("id[]", aid) for aid in account_ids]
        data, _ = await self._request("GET", "/api/v1/accounts/relationships", instance, params=params_list)
        return data  # type: ignore[no-any-return]

    async def get_followers(
        self,
        account_id: str,
        limit: int = 40,
        instance: str | None = None,
    ) -> list[dict[str, Any]]:
        """List followers of an account."""
        params: dict[str, int] = {"limit": min(limit, 80)}
        data, _ = await self._request("GET", f"/api/v1/accounts/{account_id}/followers", instance, params=params)
        return data  # type: ignore[no-any-return]

    async def get_following(
        self,
        account_id: str,
        limit: int = 40,
        instance: str | None = None,
    ) -> list[dict[str, Any]]:
        """List accounts followed by an account."""
        params: dict[str, int] = {"limit": min(limit, 80)}
        data, _ = await self._request("GET", f"/api/v1/accounts/{account_id}/following", instance, params=params)
        return data  # type: ignore[no-any-return]

    async def follow_account(self, account_id: str, instance: str | None = None) -> dict[str, Any]:
        """Follow an account."""
        data, _ = await self._request("POST", f"/api/v1/accounts/{account_id}/follow", instance)
        return data  # type: ignore[no-any-return]

    async def unfollow_account(self, account_id: str, instance: str | None = None) -> dict[str, Any]:
        """Unfollow an account."""
        data, _ = await self._request("POST", f"/api/v1/accounts/{account_id}/unfollow", instance)
        return data  # type: ignore[no-any-return]

    async def block_account(self, account_id: str, instance: str | None = None) -> dict[str, Any]:
        """Block an account."""
        data, _ = await self._request("POST", f"/api/v1/accounts/{account_id}/block", instance)
        return data  # type: ignore[no-any-return]

    async def unblock_account(self, account_id: str, instance: str | None = None) -> dict[str, Any]:
        """Unblock an account."""
        data, _ = await self._request("POST", f"/api/v1/accounts/{account_id}/unblock", instance)
        return data  # type: ignore[no-any-return]

    async def mute_account(
        self,
        account_id: str,
        duration: int | None = None,
        instance: str | None = None,
    ) -> dict[str, Any]:
        """Mute an account."""
        body: dict[str, Any] = {}
        if duration is not None:
            body["duration"] = duration
        data, _ = await self._request("POST", f"/api/v1/accounts/{account_id}/mute", instance, json=body)
        return data  # type: ignore[no-any-return]

    async def unmute_account(self, account_id: str, instance: str | None = None) -> dict[str, Any]:
        """Unmute an account."""
        data, _ = await self._request("POST", f"/api/v1/accounts/{account_id}/unmute", instance)
        return data  # type: ignore[no-any-return]

    # -----------------------------------------------------------------------
    # Notifications
    # -----------------------------------------------------------------------

    async def get_notifications(
        self,
        types: list[str] | None = None,
        limit: int = 20,
        max_id: str | None = None,
        instance: str | None = None,
    ) -> list[dict[str, Any]]:
        """List notifications."""
        params: dict[str, str | int] = {"limit": min(limit, 40)}
        if max_id:
            params["max_id"] = max_id
        if types:
            # Build query params manually for types[]
            query_parts: list[tuple[str, str | int]] = [("limit", min(limit, 40))]
            if max_id:
                query_parts.append(("max_id", max_id))
            for t in types:
                query_parts.append(("types[]", t))
            data, _ = await self._request("GET", "/api/v1/notifications", instance, params=query_parts)
        else:
            data, _ = await self._request("GET", "/api/v1/notifications", instance, params=params)
        return data  # type: ignore[no-any-return]

    async def dismiss_notification(self, notification_id: str, instance: str | None = None) -> None:
        """Dismiss a single notification."""
        await self._request("POST", f"/api/v1/notifications/{notification_id}/dismiss", instance)

    async def dismiss_all_notifications(self, instance: str | None = None) -> None:
        """Dismiss all notifications."""
        await self._request("POST", "/api/v1/notifications/clear", instance)

    # -----------------------------------------------------------------------
    # Trending
    # -----------------------------------------------------------------------

    async def trending_tags(self, limit: int = 10, instance: str | None = None) -> list[dict[str, Any]]:
        """Get trending hashtags."""
        params: dict[str, int] = {"limit": min(limit, 20)}
        data, _ = await self._request("GET", "/api/v1/trends/tags", instance, params=params)
        return data  # type: ignore[no-any-return]

    async def trending_statuses(self, limit: int = 20, instance: str | None = None) -> list[dict[str, Any]]:
        """Get trending statuses."""
        params: dict[str, int] = {"limit": min(limit, 40)}
        data, _ = await self._request("GET", "/api/v1/trends/statuses", instance, params=params)
        return data  # type: ignore[no-any-return]

    async def trending_links(self, limit: int = 10, instance: str | None = None) -> list[dict[str, Any]]:
        """Get trending links."""
        params: dict[str, int] = {"limit": min(limit, 20)}
        data, _ = await self._request("GET", "/api/v1/trends/links", instance, params=params)
        return data  # type: ignore[no-any-return]

    # -----------------------------------------------------------------------
    # Bookmarks & Favourites
    # -----------------------------------------------------------------------

    async def get_bookmarks(
        self,
        limit: int = 20,
        max_id: str | None = None,
        instance: str | None = None,
    ) -> list[dict[str, Any]]:
        """List bookmarked statuses."""
        params: dict[str, str | int] = {"limit": min(limit, 40)}
        if max_id:
            params["max_id"] = max_id
        data, _ = await self._request("GET", "/api/v1/bookmarks", instance, params=params)
        return data  # type: ignore[no-any-return]

    async def get_favourites(
        self,
        limit: int = 20,
        max_id: str | None = None,
        instance: str | None = None,
    ) -> list[dict[str, Any]]:
        """List favourited statuses."""
        params: dict[str, str | int] = {"limit": min(limit, 40)}
        if max_id:
            params["max_id"] = max_id
        data, _ = await self._request("GET", "/api/v1/favourites", instance, params=params)
        return data  # type: ignore[no-any-return]

    # -----------------------------------------------------------------------
    # Lists
    # -----------------------------------------------------------------------

    async def get_lists(self, instance: str | None = None) -> list[dict[str, Any]]:
        """List all lists."""
        data, _ = await self._request("GET", "/api/v1/lists", instance)
        return data  # type: ignore[no-any-return]

    async def get_list_accounts(
        self,
        list_id: str,
        limit: int = 40,
        instance: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get accounts in a list."""
        params: dict[str, int] = {"limit": min(limit, 80)}
        data, _ = await self._request("GET", f"/api/v1/lists/{list_id}/accounts", instance, params=params)
        return data  # type: ignore[no-any-return]

    # -----------------------------------------------------------------------
    # Conversations
    # -----------------------------------------------------------------------

    async def get_conversations(
        self,
        limit: int = 20,
        max_id: str | None = None,
        instance: str | None = None,
    ) -> list[dict[str, Any]]:
        """List DM conversations."""
        params: dict[str, str | int] = {"limit": min(limit, 40)}
        if max_id:
            params["max_id"] = max_id
        data, _ = await self._request("GET", "/api/v1/conversations", instance, params=params)
        return data  # type: ignore[no-any-return]

    # -----------------------------------------------------------------------
    # Filters
    # -----------------------------------------------------------------------

    async def get_filters(self, instance: str | None = None) -> list[dict[str, Any]]:
        """List active content filters (v2 API)."""
        try:
            data, _ = await self._request("GET", "/api/v2/filters", instance)
        except NotFoundError:
            # Fallback to v1
            data, _ = await self._request("GET", "/api/v1/filters", instance)
        return data  # type: ignore[no-any-return]

    # -----------------------------------------------------------------------
    # Media
    # -----------------------------------------------------------------------

    async def upload_media(
        self,
        file_path: str,
        description: str | None = None,
        instance: str | None = None,
    ) -> dict[str, Any]:
        """Upload media attachment.

        Note: Only accepts paths to local files, not URLs.
        """
        provider = self._resolve_provider(instance)
        await self._rate_limiter.wait_if_needed(provider.name)

        client = self._get_http(provider)
        with open(file_path, "rb") as f:
            files = {"file": (file_path.split("/")[-1], f)}
            data_fields: dict[str, str] = {}
            if description:
                data_fields["description"] = description
            response = await client.post(
                "/api/v2/media",
                files=files,
                data=data_fields,
            )
        self._rate_limiter.update_from_response(provider.name, response)
        response.raise_for_status()
        return response.json()  # type: ignore[no-any-return]

    # -----------------------------------------------------------------------
    # Cleanup
    # -----------------------------------------------------------------------

    async def close(self) -> None:
        """Close all HTTP connections."""
        for client in self._http.values():
            await client.aclose()
        self._http.clear()

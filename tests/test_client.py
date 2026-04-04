"""Tests for mastodon_blade_mcp.client -- request construction, error handling, pagination."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from mastodon_blade_mcp.client import (
    AuthError,
    ConnectionError,
    MastodonClient,
    NotFoundError,
    RateLimitError,
    _classify_error,
    _parse_link_header,
)


class TestClassifyError:
    def test_auth_error(self) -> None:
        assert isinstance(_classify_error("401 Unauthorized"), AuthError)
        assert isinstance(_classify_error("invalid access token"), AuthError)
        assert isinstance(_classify_error("Forbidden 403"), AuthError)

    def test_not_found(self) -> None:
        assert isinstance(_classify_error("404 Not Found"), NotFoundError)

    def test_rate_limit(self) -> None:
        assert isinstance(_classify_error("429 Too Many Requests"), RateLimitError)

    def test_connection(self) -> None:
        assert isinstance(_classify_error("Connection refused"), ConnectionError)
        assert isinstance(_classify_error("timeout error"), ConnectionError)

    def test_generic(self) -> None:
        from mastodon_blade_mcp.models import MastodonError

        error = _classify_error("some unknown error")
        assert isinstance(error, MastodonError)
        assert not isinstance(error, AuthError)


class TestParseLinkHeader:
    def test_basic(self) -> None:
        header = (
            '<https://mastodon.social/api/v1/timelines/home?max_id=123>; rel="next", '
            '<https://mastodon.social/api/v1/timelines/home?min_id=456>; rel="prev"'
        )
        links = _parse_link_header(header)
        assert "next" in links
        assert "prev" in links
        assert "max_id=123" in links["next"]
        assert "min_id=456" in links["prev"]

    def test_empty(self) -> None:
        assert _parse_link_header("") == {}

    def test_single_link(self) -> None:
        header = '<https://example.com/api?page=2>; rel="next"'
        links = _parse_link_header(header)
        assert len(links) == 1
        assert "next" in links

    def test_malformed(self) -> None:
        # No semicolon
        assert _parse_link_header("just-a-url") == {}


class TestMastodonClientInit:
    def test_creates_with_single_provider(self, mastodon_env: None) -> None:
        client = MastodonClient()
        assert len(client.provider_names) == 1
        assert client.provider_names[0] == "default"

    def test_creates_with_multi_provider(self, mastodon_env_multi: None) -> None:
        client = MastodonClient()
        assert len(client.provider_names) == 2
        assert "social" in client.provider_names
        assert "hachyderm" in client.provider_names

    def test_raises_without_config(self) -> None:
        with pytest.raises(ValueError):
            MastodonClient()


class TestMastodonClientResolveProvider:
    def test_resolves_default(self, mastodon_env: None) -> None:
        client = MastodonClient()
        provider = client._resolve_provider(None)
        assert provider.name == "default"

    def test_resolves_named(self, mastodon_env_multi: None) -> None:
        client = MastodonClient()
        provider = client._resolve_provider("hachyderm")
        assert provider.name == "hachyderm"

    def test_unknown_raises(self, mastodon_env: None) -> None:
        client = MastodonClient()
        from mastodon_blade_mcp.models import MastodonError

        with pytest.raises(MastodonError, match="Unknown instance"):
            client._resolve_provider("nonexistent")


class TestMastodonClientRequest:
    @pytest.mark.asyncio
    async def test_successful_request(self, mastodon_env: None) -> None:
        client = MastodonClient()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {
            "content-type": "application/json",
            "Link": "",
            "X-RateLimit-Limit": "300",
            "X-RateLimit-Remaining": "299",
            "X-RateLimit-Reset": "2026-04-04T12:00:00Z",
        }
        mock_response.json.return_value = {"id": "123", "content": "test"}
        mock_response.raise_for_status = MagicMock()

        with patch.object(client, "_get_http") as mock_http:
            mock_client = AsyncMock()
            mock_client.request.return_value = mock_response
            mock_http.return_value = mock_client

            data, pagination = await client._request("GET", "/api/v1/statuses/123")
            assert data["id"] == "123"
            assert isinstance(pagination, dict)

    @pytest.mark.asyncio
    async def test_auth_error(self, mastodon_env: None) -> None:
        client = MastodonClient()

        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.headers = {}

        with patch.object(client, "_get_http") as mock_http:
            mock_client = AsyncMock()
            mock_client.request.return_value = mock_response
            mock_http.return_value = mock_client

            with pytest.raises(AuthError):
                await client._request("GET", "/api/v1/statuses/123")

    @pytest.mark.asyncio
    async def test_not_found_error(self, mastodon_env: None) -> None:
        client = MastodonClient()

        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.headers = {}

        with patch.object(client, "_get_http") as mock_http:
            mock_client = AsyncMock()
            mock_client.request.return_value = mock_response
            mock_http.return_value = mock_client

            with pytest.raises(NotFoundError):
                await client._request("GET", "/api/v1/statuses/nonexistent")

    @pytest.mark.asyncio
    async def test_rate_limit_error(self, mastodon_env: None) -> None:
        client = MastodonClient()

        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.headers = {}

        with patch.object(client, "_get_http") as mock_http:
            mock_client = AsyncMock()
            mock_client.request.return_value = mock_response
            mock_http.return_value = mock_client

            with pytest.raises(RateLimitError):
                await client._request("GET", "/api/v1/timelines/home")

    @pytest.mark.asyncio
    async def test_connection_error(self, mastodon_env: None) -> None:
        client = MastodonClient()

        with patch.object(client, "_get_http") as mock_http:
            mock_client = AsyncMock()
            mock_client.request.side_effect = httpx.ConnectError("Connection refused")
            mock_http.return_value = mock_client

            with pytest.raises(ConnectionError):
                await client._request("GET", "/api/v1/timelines/home")


class TestMastodonClientAPIMethods:
    @pytest.mark.asyncio
    async def test_verify_credentials(self, mastodon_env: None) -> None:
        client = MastodonClient()
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = ({"id": "1", "acct": "user"}, {})
            data = await client.verify_credentials()
            assert data["acct"] == "user"
            mock_req.assert_called_once_with("GET", "/api/v1/accounts/verify_credentials", None)

    @pytest.mark.asyncio
    async def test_timeline_home(self, mastodon_env: None) -> None:
        client = MastodonClient()
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = ([{"id": "1"}], {})
            data = await client.timeline_home(limit=10)
            assert len(data) == 1
            call_kwargs = mock_req.call_args
            assert call_kwargs[1]["params"]["limit"] == 10

    @pytest.mark.asyncio
    async def test_timeline_home_pagination(self, mastodon_env: None) -> None:
        client = MastodonClient()
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = ([{"id": "1"}], {})
            await client.timeline_home(limit=20, max_id="12345")
            call_kwargs = mock_req.call_args
            assert call_kwargs[1]["params"]["max_id"] == "12345"

    @pytest.mark.asyncio
    async def test_post_status(self, mastodon_env: None) -> None:
        client = MastodonClient()
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = ({"id": "new-1", "content": "test"}, {})
            data = await client.post_status("Hello world!", visibility="unlisted")
            assert data["id"] == "new-1"
            call_args = mock_req.call_args
            body = call_args[1]["json"]
            assert body["status"] == "Hello world!"
            assert body["visibility"] == "unlisted"

    @pytest.mark.asyncio
    async def test_search(self, mastodon_env: None) -> None:
        client = MastodonClient()
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = ({"accounts": [], "statuses": [], "hashtags": []}, {})
            await client.search("python", search_type="hashtags")
            call_kwargs = mock_req.call_args
            assert call_kwargs[1]["params"]["q"] == "python"
            assert call_kwargs[1]["params"]["type"] == "hashtags"

    @pytest.mark.asyncio
    async def test_get_relationships(self, mastodon_env: None) -> None:
        client = MastodonClient()
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = ([{"id": "1", "following": True}], {})
            await client.get_relationships(["1", "2"])
            call_kwargs = mock_req.call_args
            params = call_kwargs[1]["params"]
            assert ("id[]", "1") in params
            assert ("id[]", "2") in params

    @pytest.mark.asyncio
    async def test_delete_status(self, mastodon_env: None) -> None:
        client = MastodonClient()
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = ({"id": "123", "text": "original"}, {})
            await client.delete_status("123")
            mock_req.assert_called_once_with("DELETE", "/api/v1/statuses/123", None)

    @pytest.mark.asyncio
    async def test_get_notifications_with_types(self, mastodon_env: None) -> None:
        client = MastodonClient()
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = ([], {})
            await client.get_notifications(types=["mention", "favourite"], limit=10)
            call_kwargs = mock_req.call_args
            params = call_kwargs[1]["params"]
            assert ("types[]", "mention") in params
            assert ("types[]", "favourite") in params

    @pytest.mark.asyncio
    async def test_mute_account_with_duration(self, mastodon_env: None) -> None:
        client = MastodonClient()
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = ({"id": "1", "muting": True}, {})
            await client.mute_account("1", duration=3600)
            call_kwargs = mock_req.call_args
            assert call_kwargs[1]["json"]["duration"] == 3600

    @pytest.mark.asyncio
    async def test_instance_info_v2_fallback(self, mastodon_env: None) -> None:
        client = MastodonClient()
        call_count = 0

        async def mock_request(
            method: str, path: str, instance: str | None = None, **kwargs: object
        ) -> tuple[dict[str, str], dict[str, str]]:
            nonlocal call_count
            call_count += 1
            if "/api/v2/instance" in path:
                raise NotFoundError("v2 not available")
            return {"title": "Test Instance", "version": "3.5.0"}, {}

        with patch.object(client, "_request", side_effect=mock_request):
            data = await client.instance_info()
            assert data["title"] == "Test Instance"
            assert call_count == 2  # Tried v2, fell back to v1

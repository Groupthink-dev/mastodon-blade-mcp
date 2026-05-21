"""DD-338 A.1 -- conformance stub for DD-333 Phase C harness.

Asserts subset relations for scope-aware tools:
- ``tool(scope="public")`` returns the same set as ``tool()`` (unfiltered).
- ``tool(scope=<configured>)`` returns a subset by status-id of ``tool()``.

Designed to plug into the DD-333 conformance harness when it lands; the
``_parse_meta`` helper here is portable to a pytest fixture later.
"""

from __future__ import annotations

import json
import re
from unittest.mock import AsyncMock, patch

import pytest

import mastodon_blade_mcp.server as server_module
from tests.conftest import make_notification, make_status


def _parse_meta(result: str) -> dict:
    m = re.search(r"\n\n_meta: (\{.*\})$", result)
    assert m is not None
    return json.loads(m.group(1))


def _status_ids_from_payload(result: str) -> set[str]:
    """Extract status IDs from format_timeline pipe-delimited output."""
    ids = set()
    for line in result.split("\n"):
        if not line or line.startswith("_meta:") or line.startswith("##") or line.startswith("("):
            continue
        first = line.split("|", 1)[0].strip()
        if first and first not in ("Error:",):
            ids.add(first)
    return ids


@pytest.fixture(autouse=True)
def _reset_client() -> None:
    server_module._client = None


@pytest.mark.asyncio
async def test_timeline_home_public_eq_unfiltered(mastodon_env: None) -> None:
    """scope=public must yield the same status-id set as no scope."""
    sample = [make_status(status_id=f"s{i}") for i in range(5)]
    with patch.object(server_module, "_get_client") as mock_gc:
        mock_client = AsyncMock()
        mock_client.timeline_home_paginated.return_value = (sample, None)
        mock_gc.return_value = mock_client
        r_none = await server_module.mastodon_timeline_home()
        r_public = await server_module.mastodon_timeline_home(scope="public")
    assert _status_ids_from_payload(r_none) == _status_ids_from_payload(r_public)


@pytest.mark.asyncio
async def test_timeline_home_scope_subset(mastodon_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """scope=personal status-id set must be a subset of unfiltered set."""
    monkeypatch.setenv("MASTODON_PERSONAL_LIST_ID", "list-42")
    sample_full = [make_status(status_id=f"s{i}") for i in range(5)]
    sample_in_list = sample_full[:2]
    with patch.object(server_module, "_get_client") as mock_gc:
        mock_client = AsyncMock()
        mock_client.timeline_home_paginated.return_value = (sample_full, None)
        mock_client.timeline_list_paginated.return_value = (sample_in_list, None)
        mock_gc.return_value = mock_client
        r_none = await server_module.mastodon_timeline_home()
        r_scope = await server_module.mastodon_timeline_home(scope="personal")
    assert _status_ids_from_payload(r_scope) <= _status_ids_from_payload(r_none)


@pytest.mark.asyncio
async def test_notifications_scope_subset(mastodon_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """scope filter applied to notifications must produce subset of unfiltered."""
    monkeypatch.setenv("MASTODON_PERSONAL_LIST_ID", "list-42")
    notifs = []
    for i in range(4):
        n = make_notification(notification_id=f"n{i}")
        n["account"]["id"] = str(i)
        notifs.append(n)
    with patch.object(server_module, "_get_client") as mock_gc:
        mock_client = AsyncMock()
        mock_client.get_notifications_paginated.return_value = (notifs, None)
        mock_client.list_accounts_cached.return_value = {"0", "1"}
        mock_gc.return_value = mock_client
        r_none = await server_module.mastodon_notifications()
        r_scope = await server_module.mastodon_notifications(scope="personal")
    # Notification IDs are first column in format_notification.
    none_ids = {ln.split("|", 1)[0].strip() for ln in r_none.split("\n") if ln and not ln.startswith("_meta:")}
    scope_ids = {ln.split("|", 1)[0].strip() for ln in r_scope.split("\n") if ln and not ln.startswith("_meta:")}
    assert scope_ids <= none_ids


@pytest.mark.asyncio
async def test_meta_envelope_schema_invariants(mastodon_env: None) -> None:
    """All 4 scope-aware tools emit the canonical 6-field _meta envelope."""
    expected_keys = {"matched_total", "returned", "filtered_by", "redactions", "next_cursor", "latency_ms"}
    with patch.object(server_module, "_get_client") as mock_gc:
        mock_client = AsyncMock()
        mock_client.timeline_home_paginated.return_value = ([], None)
        mock_client.search_paginated.return_value = ({"accounts": [], "statuses": [], "hashtags": []}, None)
        mock_client.get_notifications_paginated.return_value = ([], None)
        mock_client.get_account_statuses_paginated.return_value = ([], None)
        mock_gc.return_value = mock_client
        for fn, args in [
            (server_module.mastodon_timeline_home, []),
            (server_module.mastodon_search, ["q"]),
            (server_module.mastodon_notifications, []),
            (server_module.mastodon_account_statuses, ["acc-1"]),
        ]:
            result = await fn(*args)
            meta = _parse_meta(result)
            assert expected_keys.issubset(meta.keys()), f"{fn.__name__} missing keys"

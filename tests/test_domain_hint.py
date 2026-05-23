"""Tests for DD-338 A.2.dom.c domain_hint pattern engine."""

from __future__ import annotations

from typing import Any

import pytest

from mastodon_blade_mcp.domain_hint import (
    Pattern,
    compute_domain_hint,
    load_patterns_from_yaml,
)


def _projector(record: dict[str, Any], field: str) -> Any:
    """Mastodon-shape field projector mirroring server._field_projector."""
    if field == "account_acct":
        acct = record.get("account", {})
        if isinstance(acct, dict):
            return acct.get("acct")
        return None
    if field == "tags":
        tags = record.get("tags", [])
        if not isinstance(tags, list):
            return None
        return [t.get("name") for t in tags if isinstance(t, dict) and t.get("name") is not None]
    if field == "mentions":
        mentions = record.get("mentions", [])
        if not isinstance(mentions, list):
            return None
        return [m.get("acct") for m in mentions if isinstance(m, dict) and m.get("acct") is not None]
    if field == "content":
        return record.get("content")
    if field == "spoiler_text":
        return record.get("spoiler_text")
    return None


# ---------------------------------------------------------------------------
# compute_domain_hint
# ---------------------------------------------------------------------------


def test_compute_domain_hint_empty_patterns_returns_none() -> None:
    record = {"id": "1", "account": {"acct": "alice@example.social"}}
    assert compute_domain_hint(record, [], _projector) is None


def test_compute_domain_hint_single_equals_match_on_account_acct() -> None:
    record = {"id": "1", "account": {"acct": "family@example.social"}}
    patterns = [Pattern(field="account_acct", op="equals", value="family@example.social", domain="family")]
    assert compute_domain_hint(record, patterns, _projector) == "family"


def test_compute_domain_hint_first_match_wins() -> None:
    """First-match-wins ordering: family pattern beats work pattern even when both match."""
    record = {
        "id": "1",
        "account": {"acct": "shared@example.social"},
        "tags": [{"name": "work"}],
    }
    patterns = [
        Pattern(field="account_acct", op="equals", value="shared@example.social", domain="family"),
        Pattern(field="tags", op="equals", value="work", domain="work"),
    ]
    assert compute_domain_hint(record, patterns, _projector) == "family"


def test_compute_domain_hint_glob_wildcard_on_mentions_list() -> None:
    """Glob over list-valued projected field (mentions) — element-wise match."""
    record = {
        "id": "1",
        "mentions": [{"acct": "alice@home.example"}, {"acct": "bob@team.example.com"}],
    }
    patterns = [Pattern(field="mentions", op="glob", value="*@team.example.com", domain="work")]
    assert compute_domain_hint(record, patterns, _projector) == "work"


def test_compute_domain_hint_contains_on_content_html() -> None:
    """Contains-op substring match against HTML content body."""
    record = {"id": "1", "content": "<p>Project Atlas standup notes</p>"}
    patterns = [Pattern(field="content", op="contains", value="Project Atlas", domain="work")]
    assert compute_domain_hint(record, patterns, _projector) == "work"


def test_compute_domain_hint_projector_returns_none_yields_none() -> None:
    """Unknown projector field returns None; no domain hint emitted."""
    record = {"id": "1", "account": {"acct": "alice@example.social"}}
    patterns = [Pattern(field="nonexistent_field", op="equals", value="anything", domain="x")]
    assert compute_domain_hint(record, patterns, _projector) is None


def test_compute_domain_hint_unknown_op_silently_skipped() -> None:
    """Schema-drift defence: unknown op skipped, next pattern still evaluated."""
    record = {"id": "1", "account": {"acct": "alice@example.social"}}
    patterns = [
        Pattern(field="account_acct", op="regex", value=".*", domain="never"),
        Pattern(field="account_acct", op="equals", value="alice@example.social", domain="personal"),
    ]
    assert compute_domain_hint(record, patterns, _projector) == "personal"


# ---------------------------------------------------------------------------
# load_patterns_from_yaml
# ---------------------------------------------------------------------------


def test_load_patterns_empty_string_returns_empty_list() -> None:
    assert load_patterns_from_yaml("") == []


def test_load_patterns_whitespace_only_returns_empty_list() -> None:
    assert load_patterns_from_yaml("   \n  \t  ") == []


def test_load_patterns_malformed_yaml_returns_empty_list() -> None:
    assert load_patterns_from_yaml("not: valid: yaml: at: all: [unclosed") == []


def test_load_patterns_non_mapping_root_returns_empty_list() -> None:
    assert load_patterns_from_yaml("- just\n- a\n- list") == []


def test_load_patterns_missing_patterns_key_returns_empty_list() -> None:
    assert load_patterns_from_yaml("other_key: value") == []


def test_load_patterns_patterns_non_list_returns_empty_list() -> None:
    assert load_patterns_from_yaml("patterns: scalar") == []


def test_load_patterns_valid_entries_parsed() -> None:
    yaml_str = """
patterns:
  - field: account_acct
    op: equals
    value: "family@example.social"
    domain: family
  - field: tags
    op: contains
    value: "work"
    domain: work
"""
    result = load_patterns_from_yaml(yaml_str)
    assert len(result) == 2
    assert result[0] == Pattern(field="account_acct", op="equals", value="family@example.social", domain="family")
    assert result[1] == Pattern(field="tags", op="contains", value="work", domain="work")


def test_load_patterns_partial_failure_skips_bad_entries() -> None:
    """Per-pattern parse failures skip silently — good entries still load."""
    yaml_str = """
patterns:
  - field: account_acct
    op: equals
    value: "ok@example.social"
    domain: personal
  - missing_required_keys: true
  - field: tags
    op: glob
    value: "work-*"
    domain: work
"""
    result = load_patterns_from_yaml(yaml_str)
    assert len(result) == 2
    assert result[0].domain == "personal"
    assert result[1].domain == "work"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

"""Tests for DD-338 A.2.dom.c domain_hint pattern engine.

DD-338 Phase E.python correction: blade-level integration tests against the
local ``compute_domain_hint`` wrapper in :mod:`mastodon_blade_mcp.server`,
which pre-projects Mastodon's list-of-dict record shapes (``tags``,
``mentions``) via ``_field_projector`` before delegating to the canonical
2-arg helper. The canonical lib's dot-path navigation alone cannot address
these list-of-dict shapes; without the projector, ``tags`` / ``mentions``
patterns silently fail.
"""

from __future__ import annotations

from typing import Any

import pytest
from stallari_mcp_helpers import Pattern, load_patterns_from_yaml

from mastodon_blade_mcp.server import _field_projector, compute_domain_hint


def _projector(record: dict[str, Any], field: str) -> Any:
    """Test-side projector mirroring server._field_projector for explicit
    closure-binding in tests that pass a custom projector arg."""
    return _field_projector(record, field)


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
    """Glob over list-valued projected field (mentions) — element-wise match.

    This is the canonical regression case: without ``_field_projector``,
    ``mentions`` is a list-of-dicts that the canonical lib's ``_matches``
    helper skips entirely (``if isinstance(c, dict): continue``).
    """
    record = {
        "id": "1",
        "mentions": [{"acct": "alice@home.example"}, {"acct": "bob@team.example.com"}],
    }
    patterns = [Pattern(field="mentions", op="glob", value="*@team.example.com", domain="work")]
    assert compute_domain_hint(record, patterns, _projector) == "work"


def test_compute_domain_hint_equals_on_tags_list() -> None:
    """Equals against list-of-dict tags — element-wise match after projection."""
    record = {
        "id": "1",
        "tags": [{"name": "linux"}, {"name": "rust"}],
    }
    patterns = [Pattern(field="tags", op="equals", value="rust", domain="work")]
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
        Pattern(field="account_acct", op="regex", value=".*", domain="never"),  # type: ignore[arg-type]
        Pattern(field="account_acct", op="equals", value="alice@example.social", domain="personal"),
    ]
    assert compute_domain_hint(record, patterns, _projector) == "personal"


def test_compute_domain_hint_default_projector_arg() -> None:
    """Wrapper's default projector arg uses server._field_projector — covers
    the call-site that omits the explicit projector (in-tool dispatch sites
    that rely on the default)."""
    record = {
        "id": "1",
        "tags": [{"name": "family"}],
    }
    patterns = [Pattern(field="tags", op="equals", value="family", domain="family")]
    assert compute_domain_hint(record, patterns) == "family"


# ---------------------------------------------------------------------------
# load_patterns_from_yaml (canonical lib — smoke for blade-relevant shapes)
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

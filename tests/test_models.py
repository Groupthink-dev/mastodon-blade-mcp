"""Tests for mastodon_blade_mcp.models -- providers, gates, scrubbing."""

from __future__ import annotations

import pytest

from mastodon_blade_mcp.models import (
    ProviderConfig,
    check_confirm_gate,
    check_write_gate,
    is_write_enabled,
    resolve_providers,
    scrub_credentials,
)


class TestResolveProviders:
    def test_single_provider(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MASTODON_INSTANCE", "https://mastodon.social")
        monkeypatch.setenv("MASTODON_TOKEN", "my-token")
        providers = resolve_providers()
        assert len(providers) == 1
        assert providers[0].name == "default"
        assert providers[0].instance_url == "https://mastodon.social"
        assert providers[0].token == "my-token"

    def test_single_provider_strips_trailing_slash(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MASTODON_INSTANCE", "https://mastodon.social/")
        monkeypatch.setenv("MASTODON_TOKEN", "tok")
        providers = resolve_providers()
        assert providers[0].instance_url == "https://mastodon.social"

    def test_multi_provider(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MASTODON_PROVIDERS", "social,hachyderm")
        monkeypatch.setenv("MASTODON_SOCIAL_INSTANCE", "https://mastodon.social")
        monkeypatch.setenv("MASTODON_SOCIAL_TOKEN", "social-tok")
        monkeypatch.setenv("MASTODON_HACHYDERM_INSTANCE", "https://hachyderm.io")
        monkeypatch.setenv("MASTODON_HACHYDERM_TOKEN", "hach-tok")
        providers = resolve_providers()
        assert len(providers) == 2
        assert providers[0].name == "social"
        assert providers[1].name == "hachyderm"

    def test_multi_provider_skips_incomplete(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MASTODON_PROVIDERS", "ok,bad")
        monkeypatch.setenv("MASTODON_OK_INSTANCE", "https://ok.social")
        monkeypatch.setenv("MASTODON_OK_TOKEN", "tok")
        # bad has no token
        monkeypatch.setenv("MASTODON_BAD_INSTANCE", "https://bad.social")
        providers = resolve_providers()
        assert len(providers) == 1
        assert providers[0].name == "ok"

    def test_no_config_raises(self) -> None:
        with pytest.raises(ValueError, match="not configured"):
            resolve_providers()

    def test_multi_provider_all_incomplete_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MASTODON_PROVIDERS", "bad")
        monkeypatch.setenv("MASTODON_BAD_INSTANCE", "https://bad.social")
        with pytest.raises(ValueError, match="no providers configured"):
            resolve_providers()


class TestWriteGate:
    def test_disabled_by_default(self) -> None:
        assert not is_write_enabled()
        assert check_write_gate() is not None
        assert "disabled" in check_write_gate().lower()  # type: ignore[union-attr]

    def test_enabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MASTODON_WRITE_ENABLED", "true")
        assert is_write_enabled()
        assert check_write_gate() is None

    def test_case_insensitive(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MASTODON_WRITE_ENABLED", "TRUE")
        assert is_write_enabled()


class TestConfirmGate:
    def test_not_confirmed(self) -> None:
        result = check_confirm_gate(False, "Delete status")
        assert result is not None
        assert "confirm" in result.lower()
        assert "Delete status" in result

    def test_confirmed(self) -> None:
        assert check_confirm_gate(True, "Delete status") is None


class TestScrubCredentials:
    def test_scrubs_bearer_token(self) -> None:
        text = "Authorization: Bearer abc123-long-token-value"
        result = scrub_credentials(text)
        assert "abc123" not in result
        assert "****" in result

    def test_scrubs_url_credentials(self) -> None:
        text = "https://user:pass@mastodon.social/api"
        result = scrub_credentials(text)
        assert "pass" not in result
        assert "****" in result

    def test_scrubs_token_param(self) -> None:
        text = "url?token=abc123&other=ok"
        result = scrub_credentials(text)
        assert "abc123" not in result

    def test_scrubs_provider_tokens(self) -> None:
        providers = [
            ProviderConfig(name="test", instance_url="https://mastodon.social", token="super-secret-token-value")
        ]
        text = "Error with super-secret-token-value in message"
        result = scrub_credentials(text, providers)
        assert "super-secret-token-value" not in result
        assert "****" in result

    def test_preserves_normal_text(self) -> None:
        text = "Connection failed for mastodon.social"
        assert scrub_credentials(text) == text

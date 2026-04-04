"""Shared constants, types, and write-gate for Mastodon Blade MCP server."""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Default limits for list operations (token efficiency)
DEFAULT_LIMIT = 20


@dataclass
class ProviderConfig:
    """Configuration for a single Mastodon instance."""

    name: str
    instance_url: str
    token: str


class MastodonError(Exception):
    """Base exception for Mastodon client errors."""

    def __init__(self, message: str, details: str = "") -> None:
        super().__init__(message)
        self.details = details


def resolve_providers() -> list[ProviderConfig]:
    """Parse Mastodon provider configuration from environment variables.

    Supports two modes:

    1. Multi-provider: ``MASTODON_PROVIDERS=social,hachyderm`` with per-provider
       ``MASTODON_SOCIAL_INSTANCE``, ``MASTODON_SOCIAL_TOKEN``

    2. Single-provider (default): ``MASTODON_INSTANCE``, ``MASTODON_TOKEN``
       treated as provider "default".
    """
    providers_str = os.environ.get("MASTODON_PROVIDERS", "").strip()
    if providers_str:
        providers = []
        for name in providers_str.split(","):
            name = name.strip()
            prefix = f"MASTODON_{name.upper()}_"
            instance_url = os.environ.get(f"{prefix}INSTANCE", "").rstrip("/")
            token = os.environ.get(f"{prefix}TOKEN", "")
            if not all([instance_url, token]):
                logger.warning("Incomplete config for provider %s — skipping", name)
                continue
            providers.append(ProviderConfig(name=name, instance_url=instance_url, token=token))
        if not providers:
            raise ValueError("MASTODON_PROVIDERS set but no providers configured correctly")
        return providers

    # Single-provider mode
    instance_url = os.environ.get("MASTODON_INSTANCE", "").rstrip("/")
    token = os.environ.get("MASTODON_TOKEN", "")
    if not all([instance_url, token]):
        raise ValueError(
            "Mastodon credentials not configured. "
            "Set MASTODON_INSTANCE and MASTODON_TOKEN, or MASTODON_PROVIDERS with per-provider vars."
        )
    return [ProviderConfig(name="default", instance_url=instance_url, token=token)]


def is_write_enabled() -> bool:
    """Check if write operations are enabled via env var."""
    return os.environ.get("MASTODON_WRITE_ENABLED", "").lower() == "true"


def check_write_gate() -> str | None:
    """Return an error message if writes are disabled, else None."""
    if not is_write_enabled():
        return "Error: Write operations are disabled. Set MASTODON_WRITE_ENABLED=true to enable."
    return None


def check_confirm_gate(confirm: bool, action: str) -> str | None:
    """Return an error message if confirm is not set, else None."""
    if not confirm:
        return f"Error: {action} is a destructive operation. Set confirm=true to proceed."
    return None


def scrub_credentials(text: str, providers: list[ProviderConfig] | None = None) -> str:
    """Remove tokens and instance URLs with embedded auth from error messages."""
    # Strip Bearer tokens
    text = re.sub(r"Bearer\s+[A-Za-z0-9._\-]+", "Bearer ****", text)
    # Strip URLs with embedded credentials
    text = re.sub(r"https?://[^:]+:[^@]+@", "https://****:****@", text)
    # Strip token parameters
    text = re.sub(r"token=[^\s&]+", "token=****", text, flags=re.IGNORECASE)
    # Strip specific provider tokens
    if providers:
        for p in providers:
            if p.token and len(p.token) > 8:
                text = text.replace(p.token, "****")
    return text

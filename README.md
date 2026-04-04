# Mastodon Blade MCP

A security-first, token-efficient MCP server for Mastodon. 45 tools across timelines, statuses, notifications, search, and social interactions.

## Why another Mastodon MCP?

| | The-Focus-AI/mastodon-mcp | cameronrye/activitypub-mcp | **This** |
|---|---|---|---|
| **Tools** | ~4 (minimal) | 53 (ActivityPub-generic) | 45 (Mastodon-targeted) |
| **Token cost** | Full JSON dumps | Verbose output | Pipe-delimited, HTML-stripped |
| **Write safety** | None | None | Write gate + confirm gate |
| **Rate limiting** | None | None | X-RateLimit-* header parsing, adaptive backoff |
| **Multi-instance** | Single only | Single | Native multi-instance |
| **Notifications** | None | Basic | Full filtering by type |
| **Credential safety** | N/A | N/A | Scrubbed from all output |

**This MCP** is designed for agentic platforms that need:
- **Precise reads** -- query one status, one thread, one hashtag. No full-state dumps.
- **Safe writes** -- two-tier gating (env var + per-call confirm) for destructive operations.
- **Multi-instance** -- manage multiple Mastodon servers from a single MCP.
- **Token efficiency** -- pipe-delimited output, HTML stripping, null-field omission.
- **Rate limit awareness** -- parses Mastodon headers, warns at thresholds, backs off when exhausted.

## Quick Start

### Install

```bash
# With uv (recommended)
uv tool install mastodon-blade-mcp

# Or from source
git clone https://github.com/piersdd/mastodon-blade-mcp.git
cd mastodon-blade-mcp
make install
```

### Configure

```bash
# Single instance
export MASTODON_INSTANCE="https://mastodon.social"
export MASTODON_TOKEN="your-access-token"

# Multi-instance
export MASTODON_PROVIDERS="social,hachyderm"
export MASTODON_SOCIAL_INSTANCE="https://mastodon.social"
export MASTODON_SOCIAL_TOKEN="token-for-social"
export MASTODON_HACHYDERM_INSTANCE="https://hachyderm.io"
export MASTODON_HACHYDERM_TOKEN="token-for-hachyderm"

# Enable posting, favouriting, following (disabled by default)
export MASTODON_WRITE_ENABLED="true"
```

Create an access token at **Preferences > Development > New Application** on your Mastodon instance.

### Run

```bash
# stdio (default -- for Claude Code, Claude Desktop)
mastodon-blade-mcp

# HTTP transport (for remote access)
MASTODON_MCP_TRANSPORT=http MASTODON_MCP_API_TOKEN=your-secret mastodon-blade-mcp
```

### Claude Code Integration

```json
{
  "mcpServers": {
    "mastodon": {
      "command": "uvx",
      "args": ["mastodon-blade-mcp"],
      "env": {
        "MASTODON_INSTANCE": "https://mastodon.social",
        "MASTODON_TOKEN": "your-token",
        "MASTODON_WRITE_ENABLED": "true"
      }
    }
  }
}
```

### Claude Desktop Integration

```json
{
  "mcpServers": {
    "mastodon": {
      "command": "uvx",
      "args": ["mastodon-blade-mcp"],
      "env": {
        "MASTODON_INSTANCE": "https://mastodon.social",
        "MASTODON_TOKEN": "your-token"
      }
    }
  }
}
```

## Tools (45)

### Read (25 tools)

| Tool | Description | Token Cost |
|------|-------------|-----------|
| `mastodon_info` | Instance info, write gate, rate limit status | Low |
| `mastodon_verify` | Verify credentials (current user) | Low |
| `mastodon_timeline_home` | Home timeline (followed accounts) | Medium |
| `mastodon_timeline_public` | Public/federated timeline | Medium |
| `mastodon_timeline_local` | Local instance timeline | Medium |
| `mastodon_timeline_hashtag` | Hashtag timeline | Medium |
| `mastodon_timeline_list` | List timeline | Medium |
| `mastodon_status` | Get specific status by ID | Low |
| `mastodon_context` | Thread context (ancestors + descendants) | Medium |
| `mastodon_search` | Unified search (accounts/statuses/hashtags) | Medium |
| `mastodon_account` | Account info by ID | Low |
| `mastodon_account_statuses` | Account's statuses with filters | Medium |
| `mastodon_relationships` | Check relationships with accounts | Low |
| `mastodon_followers` | List followers | Medium |
| `mastodon_following` | List following | Medium |
| `mastodon_notifications` | Notifications (filterable by type) | Medium |
| `mastodon_trending_tags` | Trending hashtags | Low |
| `mastodon_trending_statuses` | Trending statuses | Medium |
| `mastodon_trending_links` | Trending links | Low |
| `mastodon_bookmarks` | Bookmarked statuses | Medium |
| `mastodon_favourites` | Favourited statuses | Medium |
| `mastodon_lists` | All lists | Low |
| `mastodon_list_accounts` | Accounts in a list | Medium |
| `mastodon_conversations` | DM conversations | Medium |
| `mastodon_filters` | Active content filters (v2) | Low |

### Write (20 tools -- require `MASTODON_WRITE_ENABLED=true`)

| Tool | Description | Confirm Gate |
|------|-------------|:---:|
| `mastodon_post` | Create new status (text, CW, media, schedule) | |
| `mastodon_reply` | Reply to a status | |
| `mastodon_edit` | Edit existing status | |
| `mastodon_delete` | Delete status | Yes |
| `mastodon_favourite` | Favourite a status | |
| `mastodon_unfavourite` | Remove favourite | |
| `mastodon_boost` | Reblog a status | |
| `mastodon_unboost` | Remove reblog | |
| `mastodon_bookmark` | Bookmark a status | |
| `mastodon_unbookmark` | Remove bookmark | |
| `mastodon_pin` | Pin to profile | |
| `mastodon_unpin` | Unpin from profile | |
| `mastodon_follow` | Follow an account | |
| `mastodon_unfollow` | Unfollow an account | |
| `mastodon_block` | Block an account | Yes |
| `mastodon_unblock` | Unblock an account | |
| `mastodon_mute` | Mute an account (optional duration) | Yes |
| `mastodon_unmute` | Unmute an account | |
| `mastodon_dismiss_notification` | Dismiss single notification | |
| `mastodon_media_upload` | Upload media attachment | |

## Output Format

All output is pipe-delimited for token efficiency:

```
# Status
109876543210 | @user@mastodon.social | 2026-04-04 10:30 | public | Hello world! | fav=5 | boost=2 | reply=1

# Account
@user@mastodon.social | Test User | followers=100 | following=50 | statuses=200

# Notification
99999 | mention | @other@mastodon.social | 2026-04-04 11:00 | status=109876543210 | "@user Hey there!"

# Search results
## Accounts (1)
@user@mastodon.social | Test User | followers=100 | following=50 | statuses=200
## Hashtags (1)
#python | uses_7d=42

# Thread context
## Ancestors (1)
anc-1 | @parent@mastodon.social | 2026-04-04 09:00 | public | Original post
## Descendants (2)
desc-1 | @reply1@mastodon.social | 2026-04-04 11:00 | public | First reply
desc-2 | @reply2@mastodon.social | 2026-04-04 12:00 | public | Second reply
```

## Security Model

| Layer | Mechanism |
|-------|-----------|
| Write gate | `MASTODON_WRITE_ENABLED=true` env var for any mutation |
| Confirm gate | `confirm=true` parameter for delete, block, mute |
| Credential scrubbing | Tokens and instance URLs stripped from all error output |
| Bearer auth | Optional `MASTODON_MCP_API_TOKEN` for HTTP transport (timing-safe comparison) |
| Rate limiting | X-RateLimit-* header parsing with adaptive backoff |
| No caching | Credentials read from env at startup, never persisted |

## Multi-Instance Support

Target a specific instance with the `instance` parameter on any tool:

```
mastodon_timeline_home instance="social"
mastodon_timeline_home instance="hachyderm"
```

Omit `instance` to use the default (first configured) instance.

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `MASTODON_INSTANCE` | Instance URL (single-instance) | Yes* |
| `MASTODON_TOKEN` | OAuth access token | Yes* |
| `MASTODON_PROVIDERS` | Comma-separated provider names | No |
| `MASTODON_{NAME}_INSTANCE` | Per-provider instance URL | Per-provider |
| `MASTODON_{NAME}_TOKEN` | Per-provider token | Per-provider |
| `MASTODON_WRITE_ENABLED` | Enable write operations | No (default: false) |
| `MASTODON_MCP_TRANSPORT` | `stdio` or `http` | No (default: stdio) |
| `MASTODON_MCP_HOST` | HTTP bind address | No (default: 127.0.0.1) |
| `MASTODON_MCP_PORT` | HTTP port | No (default: 8770) |
| `MASTODON_MCP_API_TOKEN` | Bearer token for HTTP transport | No |

\* Required if `MASTODON_PROVIDERS` is not set.

## Development

```bash
# Install with dev deps
make install-dev

# Run tests
make test

# Coverage report
make test-cov

# Lint + format + type check
make check

# Run the server
make run
```

## Architecture

```
src/mastodon_blade_mcp/
├── server.py        -- FastMCP 2.0 server, 45 tool definitions
├── client.py        -- MastodonClient: httpx async, multi-instance
├── formatters.py    -- Token-efficient pipe-delimited output, HTML stripping
├── models.py        -- ProviderConfig, write gate, confirm gate, credential scrubbing
├── rate_limiter.py  -- X-RateLimit-* header parsing, adaptive backoff
├── auth.py          -- Bearer token middleware for HTTP transport
└── __main__.py      -- Entry point
```

**Dependencies:** `fastmcp`, `httpx`, `pydantic`. No Mastodon.py dependency -- pure HTTP against the Mastodon REST API.

## Sidereal Marketplace

This MCP conforms to the `social-v1` service contract (20/20 operations):
- **Required (4/4):** timeline, status, search, notifications
- **Recommended (6/6):** context, account, trending, bookmarks, favourites, relationships
- **Optional (4/4):** lists, filters, conversations, instance
- **Gated (6/6):** post, delete, favourite, boost, follow, block

See `sidereal-plugin.yaml` for the full plugin manifest.

## License

MIT

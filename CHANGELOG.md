# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to a 4-axis version scheme parallel to the rest of the
Stallari platform (`major.macro.minor.patch`).

## [0.5.0] - 2026-05-24

### Changed
- DD-338 Phase E.python: depend on `stallari-mcp-helpers>=0.1.0,<1.0.0`; deleted
  local `domain_hint.py` + local `_meta`-envelope helpers (`format_meta` +
  `append_meta`) from `formatters.py`. Pure substrate swap — no behavioural
  change for callers. Wire-shape: `_meta.filtered_by` now alphabetically sorted
  by the canonical builder; JSON separators tightened (already tight here so
  no diff).
- Engine semantics: `compute_domain_hint` is now a Mastodon-specific local
  wrapper in `server.py` that pre-projects each pattern's referenced field
  via `_field_projector` and then delegates to
  `stallari_mcp_helpers.compute_domain_hint` (canonical 2-arg). The wrapper
  preserves the 3-arg shape the blade has used since DD-338 A.2.dom.c so
  existing call-sites and tests don't change. Logical field names
  (`account_acct`, `tags`, `mentions`, `content`, `spoiler_text`) continue
  to resolve correctly against list-of-dict record shapes that the
  canonical lib's dot-path navigation alone cannot address.

### Fixed
- **Architect-review correction (post-merge of the original Spec B Cluster
  C flip):** restore `_field_projector` and add a local
  `compute_domain_hint` wrapper. The original flip dropped the projector
  and delegated directly to the canonical 2-arg helper — that produced a
  silent behavioural regression for `tags = [{"name": ...}]` and
  `mentions = [{"acct": ...}]` patterns, because the canonical lib's
  `_matches` helper explicitly skips dict-shaped list elements
  (`if isinstance(c, dict): continue`). Mirrors the pattern landed in
  `home-assistant-blade-mcp` PR #5. Restored `tests/test_domain_hint.py`
  covering list-of-dict projection, first-match ordering, glob/contains/equals
  ops, and the wrapper's default-projector arg.

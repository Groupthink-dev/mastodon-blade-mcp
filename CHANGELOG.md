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
- Engine semantics: `compute_domain_hint` now uses canonical dot-path field
  resolution (e.g. `account.acct`) instead of a per-blade field projector.
  Existing YAML configs that relied on the projector's logical field names
  (`account_acct`, `tags`, `mentions`) need to be re-authored against the
  dot-path schema. The DD-338 A.2.dom.a substrate has not yet shipped
  user-facing pattern configs, so no in-the-wild migration is required.

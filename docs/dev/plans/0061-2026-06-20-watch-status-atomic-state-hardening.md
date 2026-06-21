# Plan 0061 | Watch Status Atomic State Hardening

State: CLOSED
Date: 2026-06-20

## Scope

Fix the watcher runtime status race observed when `watch-status --json` and
`watch-backlog-preflight --no-write --json` run concurrently against the same
user-scoped watch state.

## Non-Goals

- Do not process watched files.
- Do not OCR private card images.
- Do not change watched-input config semantics.
- Do not add PDF or card-backside support.
- Do not run enrichment, live lookup, live write, or readback.

## Implementation

- Made `WatchStateStore.write_status` write `status.json` through a
  same-directory temporary file and `os.replace`.
- Made `WatchStateStore.read_status` tolerate missing, empty, or malformed
  status JSON by returning a default status instead of crashing.
- Added regression tests for empty status reads and valid replacement writes.

## Acceptance Criteria

- Concurrent no-processing watcher status/preflight commands no longer fail
  with `JSONDecodeError`.
- Existing watcher behavior is preserved.
- Runtime status remains valid JSON after writes.

## Validation

- `.venv/bin/python -m pytest tests/test_watcher.py -q` passed with 16 tests.
- `.venv/bin/ruff check src/business_card_watchdog/watcher.py tests/test_watcher.py` passed.
- `git diff --check` passed.
- `python3 scripts/check_plan_drift.py` passed.
- Concurrent no-processing verification passed with both configured watch
  aliases:
  - `.venv/bin/bcw watch-status --json`
  - `.venv/bin/bcw watch-backlog-preflight --no-write --json`

## Safety

The concurrent verification reported two watched aliases and 12 settled backlog
items, but processed zero files, attempted zero OCR, attempted zero writes, and
made zero network calls.

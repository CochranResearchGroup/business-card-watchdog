# Plan 0038 | Watch Backlog Preflight

State: CLOSED
Product authority: `PRODUCT_SPEC.md`

## Scope

Add a no-private-data watch backlog preflight so operators and agent loops can
inspect configured watched-folder backlog counts before explicitly choosing any
private SyncThing dry run.

## Non-Goals

- Do not process private SyncThing images.
- Do not expose private watched-folder paths or image filenames.
- Do not run OCR, App Intelligence, public-web search, paid enrichment, or live
  sink calls.
- Do not replace the existing fixture-backed watch dry-run harness.

## Acceptance Criteria

- Service, CLI, API, and MCP surfaces expose `watch_backlog_preflight`.
- Payloads include aggregate watcher counts, redacted configured input
  summaries, recommended next action, and explicit stop conditions.
- Optional artifact writing is limited to the configured user data directory.
- Tests prove source paths and image filenames are not present in the preflight
  payload.
- README, ROADMAP, RUNBOOK, and public-upstream validation docs record the new
  operator boundary and validation evidence.

## Execution Log

### Slice 0038-A | 2026-06-15 | Redacted Backlog Preflight

Status: implemented.

Implemented:

- Added `BusinessCardService.watch_backlog_preflight`.
- Added CLI command `watch-backlog-preflight`.
- Added API route `POST /watch/backlog-preflight`.
- Added MCP tool `business_card_watchdog_watch_backlog_preflight`.
- Added status command and safe next action visibility for the preflight.
- Updated README and roadmap documentation for the private-source watch boundary.
- Added service, CLI, API, and MCP coverage for redacted backlog preflight
  payloads.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_watch_backlog_preflight_redacts_private_source_paths tests/test_service.py::test_service_watch_backlog_preflight_can_preview_without_writing tests/test_watcher.py::test_watch_backlog_preflight_cli_outputs_redacted_counts tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_watch_backlog_preflight_redacts_private_source_paths -q` passed with 6 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/cli.py src/business_card_watchdog/api.py src/business_card_watchdog/mcp.py tests/test_service.py tests/test_watcher.py tests/test_api.py tests/test_mcp.py` passed.
- `.venv/bin/python -m pytest -q` passed with 283 tests.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `rg -n "watch-backlog-preflight|watch_backlog_preflight|Watch backlog preflight|business_card_watchdog_watch_backlog_preflight" README.md ROADMAP.md RUNBOOK.md docs src tests` passed.
- `uv build --out-dir dist` built source and wheel distributions.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `codegraph sync && codegraph status` passed; index is up to date.
- `.venv/bin/bcw watch-backlog-preflight --no-write --json` passed against
  the user config and reported `$fsr:sync_phone` as one redacted input with 5
  backlog items, 0 unsettled items, no last error, no runtime artifact write, no
  OCR, no file processing, and no network calls.

Safety:

- This slice must remain read-only with respect to watched files and live sinks.
  It may write only the preflight JSON artifact under the configured user data
  directory when `write=true`.
- It did not process private SyncThing images, run OCR/App Intelligence, run
  public-web search, call paid enrichment, execute live lookup/write/readback, or
  write Google Contacts, Odoo, or Odollo records.

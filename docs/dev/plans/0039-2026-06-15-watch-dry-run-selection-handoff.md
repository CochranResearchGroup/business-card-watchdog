# Plan 0039 | Watch Dry-Run Selection Handoff

State: CLOSED
Product authority: `PRODUCT_SPEC.md`

## Scope

Add an operator-response and command-copy handoff before any configured
private-source watch dry run. This turns the redacted backlog preflight into an
auditable approval sequence without processing private files.

## Non-Goals

- Do not process private SyncThing images.
- Do not expose private watched-folder paths or image filenames.
- Do not run OCR, App Intelligence, public-web search, paid enrichment, or live
  sink calls.
- Do not execute `watch --once --dry-run`; only return it as copyable text after
  validation and acknowledgement.

## Acceptance Criteria

- Service, CLI, API, and MCP surfaces expose the handoff, response validation,
  and command-copy packet.
- The handoff uses only redacted input refs and aggregate preflight counts.
- Validation does not store the raw operator response or safety confirmation.
- The command-copy packet returns `watch --once --dry-run` only after response
  validation and exact acknowledgement.
- Tests prove no private source path or image filename appears in the handoff,
  validation, or command-copy payloads.
- README, ROADMAP, RUNBOOK, and public-upstream validation docs record the new
  boundary and validation evidence.

## Execution Log

### Slice 0039-A | 2026-06-15 | Operator Response And Command Copy

Status: implemented.

Implemented:

- Added `BusinessCardService.watch_dry_run_selection_handoff`.
- Added `BusinessCardService.validate_watch_dry_run_operator_response`.
- Added `BusinessCardService.watch_dry_run_command_copy_packet`.
- Added CLI commands `watch-dry-run-selection-handoff`,
  `watch-dry-run-validate-response`, and `watch-dry-run-command-copy-packet`.
- Added API routes under `/watch/dry-run-*` for handoff, validation, and
  command-copy packet generation.
- Added MCP tools for the same handoff, validation, and command-copy packet.
- Updated backlog preflight safe next actions to point at the selection handoff
  before the actual private-source dry-run command.
- Updated README and ROADMAP for the new private-source watch boundary.
- Added service, CLI, API, and MCP coverage for the handoff flow.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_watch_backlog_preflight_redacts_private_source_paths tests/test_service.py::test_service_watch_dry_run_selection_handoff_validates_response_and_command_copy tests/test_service.py::test_service_watch_dry_run_command_copy_blocks_without_acknowledgement tests/test_watcher.py::test_watch_backlog_preflight_cli_outputs_redacted_counts tests/test_watcher.py::test_watch_dry_run_selection_cli_validates_and_builds_command_copy tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_watch_backlog_preflight_redacts_private_source_paths tests/test_mcp.py::test_mcp_watch_dry_run_selection_flow_returns_command_copy -q` passed with 9 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/cli.py src/business_card_watchdog/api.py src/business_card_watchdog/mcp.py tests/test_service.py tests/test_watcher.py tests/test_api.py tests/test_mcp.py tests/test_cli_surfaces.py` passed.
- `.venv/bin/python -m pytest -q` passed with 287 tests.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `rg -n "watch-dry-run-selection-handoff|watch_dry_run_selection_handoff|watch-dry-run-validate-response|watch_dry_run_command_copy|business_card_watchdog_watch_dry_run" README.md ROADMAP.md RUNBOOK.md docs src tests` passed.
- `uv build --out-dir dist` built source and wheel distributions.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `codegraph sync && codegraph status` passed; index is up to date.
- `.venv/bin/bcw watch-dry-run-selection-handoff --no-write --json` passed
  against the user config and reported `$fsr:sync_phone` as one redacted input
  with 5 backlog items, 0 unsettled items, no runtime artifact write, no OCR, no
  file processing, and no network calls.

Safety:

- This slice must not process watched files. It may write only the handoff JSON
  artifact under the configured user data directory when `write=true`.
- It did not process private SyncThing images, run OCR/App Intelligence, run
  public-web search, call paid enrichment, execute live lookup/write/readback, or
  write Google Contacts, Odoo, or Odollo records.

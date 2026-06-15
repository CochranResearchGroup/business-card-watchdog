# Plan 0036 | Operator-Selected Live Smoke Preflight

State: CLOSED
Product authority: `PRODUCT_SPEC.md`

## Scope

Add a no-live preflight packet for the Plan 0009 operator-selected live smoke
boundary. The packet composes the offline pilot gap audit, live readiness audit,
and live selection requirements into one operator-facing status surface.

## Non-Goals

- Do not process private SyncThing images.
- Do not run public-web search or paid enrichment.
- Do not execute live Google Contacts, Odoo, or Odollo lookup/write/readback.
- Do not create or modify `selected_live_target.json`.
- Do not claim that live sink writes or readbacks are complete.

## Acceptance Criteria

- Service, CLI, API, and MCP expose an operator-selected live smoke preflight.
- The preflight reports the current state, required operator fields, candidate
  counts, ready entries, active selected targets, and exact next safe commands.
- The preflight writes only an audit/preflight artifact when requested.
- Focused tests cover service, CLI, API, and MCP surfaces.
- Validation evidence is recorded before closeout.

## Execution Log

### Slice 0036-A | 2026-06-15 | No-Live Operator Preflight Packet

Status: implemented.

Implemented:

- Added `BusinessCardService.operator_selected_live_smoke_preflight`.
- Added CLI command `operator-selected-live-smoke-preflight`.
- Added API route `POST /operator-selected-live-smoke-preflight`.
- Added MCP tool `business_card_watchdog_operator_selected_live_smoke_preflight`.
- Added status command and safe next action visibility for the preflight.
- Updated README and roadmap documentation for the operator-selected preflight.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_operator_selected_live_smoke_preflight_reports_blocked_boundary tests/test_cli_surfaces.py::test_cli_status_reports_command_map_text_and_json tests/test_cli_surfaces.py::test_cli_operator_selected_live_smoke_preflight_reports_blocked_boundary tests/test_api.py::test_api_operator_selected_live_smoke_preflight_reports_blocked_boundary tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_operator_selected_live_smoke_preflight_reports_blocked_boundary -q` passed with 6 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/cli.py src/business_card_watchdog/api.py src/business_card_watchdog/mcp.py tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py` passed.
- `.venv/bin/python -m pytest -q` passed with 279 tests.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `rg -n "operator-selected-live-smoke-preflight|operator_selected_live_smoke_preflight|Operator-selected live smoke preflight|business_card_watchdog_operator_selected_live_smoke_preflight" README.md ROADMAP.md RUNBOOK.md docs src tests` passed.
- `uv build --out-dir dist` built source and wheel distributions.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This slice composes offline readiness and live-selection reports only. It
  does not process private SyncThing images, run public-web search, call paid
  enrichment, execute live lookup/write/readback, create
  `selected_live_target.json`, or write Google Contacts/Odoo/Odollo records.

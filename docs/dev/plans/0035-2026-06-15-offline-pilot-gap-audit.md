# Plan 0035 | Offline Pilot Gap Audit

State: CLOSED
Product authority: `PRODUCT_SPEC.md`

## Scope

Add a no-live audit surface that reports offline pilot drill/documentation
coverage and identifies the remaining operator/live-only boundaries before the
next product-hardening slice.

## Non-Goals

- Do not process private SyncThing images.
- Do not run public-web search or paid enrichment.
- Do not execute live Google Contacts, Odoo, or Odollo lookup/write/readback.
- Do not claim live sink readiness or write/readback success.

## Acceptance Criteria

- Service, CLI, API, and MCP expose an offline pilot gap audit.
- The audit checks expected offline documentation and drill surfaces.
- The audit reports remaining boundaries for live smoke, private SyncThing
  processing, paid enrichment, and non-loopback API exposure.
- Status output includes the audit as a safe next action.
- Focused tests cover service, CLI, API, MCP, and status visibility.

## Execution Log

### Slice 0035-A | 2026-06-15 | Offline Gap Audit Surface

Status: implemented.

Implemented:

- Added `BusinessCardService.offline_pilot_gap_audit`.
- Added CLI command `offline-pilot-gap-audit`.
- Added API route `GET /offline-pilot-gap-audit`.
- Added MCP tool `business_card_watchdog_offline_pilot_gap_audit`.
- Added status command and safe next action visibility for the audit.
- Added focused service, CLI, API, and MCP coverage.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_offline_pilot_gap_audit_reports_remaining_live_boundaries tests/test_cli_surfaces.py::test_cli_status_reports_command_map_text_and_json tests/test_cli_surfaces.py::test_cli_offline_pilot_gap_audit_reports_remaining_boundaries tests/test_api.py::test_api_offline_pilot_gap_audit_reports_remaining_boundaries tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_offline_pilot_gap_audit_reports_remaining_boundaries -q` passed with 6 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/cli.py src/business_card_watchdog/api.py src/business_card_watchdog/mcp.py tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py` passed.
- `.venv/bin/python -m pytest -q` passed with 275 tests.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `rg -n "offline-pilot-gap-audit|offline_pilot_gap_audit|offline-pilot-gap|Offline pilot gap audit|business_card_watchdog_offline_pilot_gap_audit" README.md ROADMAP.md RUNBOOK.md docs src tests` passed.
- `uv build --out-dir dist` built source and wheel distributions.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This slice inspects repo docs and local command surfaces only. It does not
  process private SyncThing images, run public-web search, call paid
  enrichment, execute live sink calls, or write Google Contacts/Odoo/Odollo
  records.

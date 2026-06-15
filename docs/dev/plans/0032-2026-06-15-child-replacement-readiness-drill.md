# Plan 0032 | Child Replacement Readiness Drill

State: CLOSED
Product authority: `PRODUCT_SPEC.md`

## Scope

Add a synthetic no-live drill that proves child replacement stale/readiness
states and emits operator sample outputs through the existing review bundle,
HTML, workbook, and dashboard surfaces.

## Non-Goals

- Do not process private SyncThing images in validation.
- Do not create `selected_live_target.json`.
- Do not execute live Google Contacts, Odoo, or Odollo lookup/write/readback.
- Do not perform public-web search or paid enrichment.
- Do not write sink contacts.
- Do not treat fixture sink context as live approval.

## Acceptance Criteria

- A CLI/API/MCP-accessible drill creates a synthetic child replacement run.
- The drill demonstrates blocked replacement audit/validation states before
  the stale/readiness refresh path is complete.
- The drill demonstrates ready handoff, response validation, checklist,
  command-copy packet, and closeout states after the refresh path is complete.
- The drill writes review bundle, review HTML, and review workbook sample
  outputs and reports the operator dashboard child replacement summary.
- Focused service, CLI, API, and MCP tests cover the drill and no-live counters.

## Execution Log

### Slice 0032-A | 2026-06-15 | Offline Replacement Readiness Drill

Status: implemented.

Implemented:

- Added `BusinessCardService.child_replacement_readiness_drill`.
- Added a production-local synthetic fixture adapter used only by fixture drills.
- Added CLI command `drills child-replacement-readiness`.
- Added API route `POST /drills/child-replacement-readiness`.
- Added MCP tool `business_card_watchdog_child_replacement_readiness_drill`.
- Added operator dashboard command/API/MCP references for the drill.
- Added synthetic service, CLI, API, and MCP coverage for the readiness drill
  and sample review outputs.

Focused validation:

- `.venv/bin/python -m pytest tests/test_review_surface.py::test_service_child_replacement_readiness_drill_exports_operator_samples tests/test_cli_surfaces.py::test_cli_child_replacement_readiness_drill_exports_operator_samples tests/test_api.py::test_api_child_replacement_readiness_drill_exports_operator_samples tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_child_replacement_readiness_drill_exports_operator_samples -q` passed with 5 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/cli.py src/business_card_watchdog/api.py src/business_card_watchdog/mcp.py tests/test_review_surface.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py` passed.
- `.venv/bin/python -m pytest -q` passed with 271 tests.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `uv build --out-dir dist` built source and wheel distributions.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This slice uses synthetic fixture data only. It does not create selected
  targets; process private SyncThing images; execute live lookup; route to live
  sinks; enrich; write contacts; run public-web search; call paid APIs; or call
  GWS/Odollo/Odoo.

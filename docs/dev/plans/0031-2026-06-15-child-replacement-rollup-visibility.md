# Plan 0031 | Child Replacement Rollup Visibility

State: CLOSED
Product authority: `PRODUCT_SPEC.md`

## Scope

Expose child replacement closeout/status rollups in the existing review bundle
and operator dashboard surfaces so operators and agent loops can see replacement
state without knowing artifact paths.

## Non-Goals

- Do not create `selected_live_target.json`.
- Do not execute live Google Contacts, Odoo, or Odollo lookup/write/readback.
- Do not process private SyncThing images in validation.
- Do not perform public-web search or paid enrichment.
- Do not write sink contacts.
- Do not delete stale predecessor child artifacts.

## Acceptance Criteria

- Review bundle entries include child replacement closeout/status artifacts and a
  compact child replacement status summary.
- Review bundle groups include child replacement status counts.
- Operator dashboard includes a selected-run child replacement summary sourced
  from review bundle data.
- HTML/workbook surfaces expose enough text/columns for operators to identify
  child replacement closeout state.
- Synthetic tests cover service, CLI/API/MCP review bundle/dashboard visibility.

## Execution Log

### Slice 0031-A | 2026-06-15 | Offline Replacement Rollup Visibility

Status: implemented.

Implemented:

- Add child replacement closeout artifact kind to review bundle visibility.
- Add review bundle entry/group/dashboard summaries.
- Add HTML/workbook visibility for closeout state.
- Add synthetic coverage across service, CLI, API, and MCP visibility surfaces.

Validation:

- `.venv/bin/python -m pytest tests/test_review_surface.py::test_child_selected_target_response_validation_and_checklist tests/test_cli_surfaces.py::test_cli_child_selected_target_response_validation_and_checklist tests/test_api.py::test_api_child_selected_target_response_validation_and_checklist tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_child_selected_target_response_validation_and_checklist -q` passed with 5 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py tests/test_review_surface.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py` passed.
- `.venv/bin/python -m pytest -q` passed with 267 tests.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `uv build --out-dir dist` built source and wheel distributions.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This slice exposes existing no-live child replacement closeout state through
  review surfaces only. It does not create selected targets, process private
  SyncThing images, execute live lookup, route to live sinks, enrich, write
  contacts, run public-web search, call paid APIs, or call GWS/Odollo/Odoo.

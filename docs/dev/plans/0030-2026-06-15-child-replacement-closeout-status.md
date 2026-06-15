# Plan 0030 | Child Replacement Closeout Status

State: CLOSED
Product authority: `PRODUCT_SPEC.md`

## Scope

Add a no-live child replacement closeout/status rollup that summarizes the
replacement path after checklist/copy packet refresh. The rollup must report
whether predecessor child selected-target artifacts are stale, replacement
handoff/validation/checklist/copy packets are ready, and no live action was
taken.

## Non-Goals

- Do not create `selected_live_target.json`.
- Do not execute live Google Contacts, Odoo, or Odollo lookup/write/readback.
- Do not process private SyncThing images in validation.
- Do not perform public-web search or paid enrichment.
- Do not write sink contacts.
- Do not delete stale predecessor child artifacts.

## Acceptance Criteria

- Service writes a replacement closeout/status artifact from existing child
  replacement runtime artifacts.
- Status is ready only when stale predecessor artifacts are marked stale and
  refreshed replacement handoff/validation/checklist/copy packets are ready.
- Status reports zero live writes, zero network calls, and no selected target
  creation.
- CLI exposes a child replacement closeout/status command.
- API exposes a child replacement closeout/status route.
- MCP exposes a child replacement closeout/status tool.
- Synthetic tests cover service, CLI, API, and MCP behavior.

## Execution Log

### Slice 0030-A | 2026-06-15 | Offline Replacement Closeout Rollup

Status: implemented.

Implemented:

- Add replacement closeout/status service method.
- Add CLI/API/MCP surfaces.
- Add synthetic multi-card tests that prove ready and no-live rollup behavior.
- Add operator documentation for replacement closeout/status rollups.

Validation:

- `.venv/bin/python -m pytest tests/test_review_surface.py::test_child_selected_target_response_validation_and_checklist tests/test_cli_surfaces.py::test_cli_child_selected_target_response_validation_and_checklist tests/test_api.py::test_api_child_selected_target_response_validation_and_checklist tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_child_selected_target_response_validation_and_checklist -q` passed with 5 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/cli.py src/business_card_watchdog/api.py src/business_card_watchdog/mcp.py tests/test_review_surface.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py` passed.
- `.venv/bin/python -m pytest -q` passed with 267 tests.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `uv build --out-dir dist` built source and wheel distributions.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This slice writes only local child replacement closeout/status artifacts. It
  does not create selected targets, process private SyncThing images, execute
  live lookup, route to live sinks, enrich, write contacts, run public-web
  search, call paid APIs, or call GWS/Odollo/Odoo.

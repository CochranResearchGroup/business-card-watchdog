# Plan 0027 | Child Replacement Handoff Refresh

State: CLOSED
Product authority: `PRODUCT_SPEC.md`

## Scope

Create a no-live child replacement handoff refresh packet after an abandonment
and replacement reset, and mark prior child selected-target artifacts stale.

## Non-Goals

- Do not create `selected_live_target.json`.
- Do not execute live Google Contacts, Odoo, or Odollo lookup/write/readback.
- Do not process private SyncThing images in validation.
- Do not perform public-web search or paid enrichment.
- Do not write sink contacts.
- Do not promote child contacts into parent job state.

## Acceptance Criteria

- Service writes a refreshed child selected-target handoff from a ready
  replacement reset packet.
- Service writes a staleness marker for previous child selected-target
  response/checklist/command-copy/audit artifacts.
- Refreshed handoff keeps prior artifacts intact and reports zero live writes
  and zero network calls.
- CLI exposes a child replacement handoff refresh command.
- API exposes a child replacement handoff refresh route.
- MCP exposes a child replacement handoff refresh tool.
- Synthetic tests cover service, CLI, API, and MCP behavior.

## Execution Log

### Slice 0027-A | 2026-06-15 | Offline Child Replacement Refresh

Implemented:

- Add replacement handoff refresh service method.
- Add child selected-target staleness marker artifact.
- Add CLI/API/MCP surfaces.
- Add synthetic multi-card tests and full local validation evidence.

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

- This slice writes only local child replacement handoff refresh and staleness
  marker artifacts. It does not create selected targets, process private
  SyncThing images, execute live lookup, route to live sinks, enrich, write
  contacts, run public-web search, call paid APIs, or call GWS/Odollo/Odoo.

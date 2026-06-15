# Plan 0028 | Child Replacement Response Validation

State: CLOSED
Product authority: `PRODUCT_SPEC.md`

## Scope

Add a no-live replacement-specific response validation step for refreshed child
selected-target handoffs. The validator must prove that the replacement refresh
packet is ready, stale predecessor artifacts are explicitly marked stale, and the
new operator response matches the refreshed child handoff.

## Non-Goals

- Do not create `selected_live_target.json`.
- Do not execute live Google Contacts, Odoo, or Odollo lookup/write/readback.
- Do not process private SyncThing images in validation.
- Do not perform public-web search or paid enrichment.
- Do not write sink contacts.
- Do not delete stale child artifacts.

## Acceptance Criteria

- Service writes a replacement response validation artifact only when the
  replacement refresh packet and staleness marker are present and ready.
- Validation blocks if old child selected-target artifacts are not marked stale
  before the replacement response is reviewed.
- Validation reuses the refreshed child handoff and reports zero live writes and
  zero network calls.
- CLI exposes a child replacement response validation command.
- API exposes a child replacement response validation route.
- MCP exposes a child replacement response validation tool.
- Synthetic tests cover service, CLI, API, and MCP behavior.

## Execution Log

### Slice 0028-A | 2026-06-15 | Offline Replacement Response Gate

Status: implemented.

Implemented:

- Add replacement-specific validation service method.
- Add CLI/API/MCP surfaces.
- Add synthetic multi-card tests that prove stale enforcement and no-live counters.
- Add operator documentation for the replacement response validation command.

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

- This slice writes only local child replacement response validation artifacts.
  It does not create selected targets, process private SyncThing images, execute
  live lookup, route to live sinks, enrich, write contacts, run public-web
  search, call paid APIs, or call GWS/Odollo/Odoo.

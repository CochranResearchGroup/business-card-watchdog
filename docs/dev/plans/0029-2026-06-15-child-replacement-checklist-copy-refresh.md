# Plan 0029 | Child Replacement Checklist And Copy Refresh

State: CLOSED
Product authority: `PRODUCT_SPEC.md`

## Scope

Add replacement-specific no-live execution checklist and command-copy packets
after child replacement response validation. These packets must use the
replacement validation artifact as authority and keep predecessor child
selected-target checklist/copy packets stale.

## Non-Goals

- Do not create `selected_live_target.json`.
- Do not execute live Google Contacts, Odoo, or Odollo lookup/write/readback.
- Do not process private SyncThing images in validation.
- Do not perform public-web search or paid enrichment.
- Do not write sink contacts.
- Do not delete stale predecessor child artifacts.

## Acceptance Criteria

- Service writes a replacement execution checklist only from a ready replacement
  response validation artifact.
- Service writes a replacement command-copy packet only when the replacement
  checklist is ready and acknowledgement names the run, child candidate, sink,
  and operator.
- Replacement checklist/copy packets return only offline command text and never
  executable live commands.
- CLI exposes replacement checklist and command-copy commands.
- API exposes replacement checklist and command-copy routes.
- MCP exposes replacement checklist and command-copy tools.
- Synthetic tests cover service, CLI, API, and MCP behavior.

## Execution Log

### Slice 0029-A | 2026-06-15 | Offline Replacement Checklist/Copy Gate

Status: implemented.

Implemented:

- Add replacement checklist and command-copy service methods.
- Add CLI/API/MCP surfaces.
- Add synthetic multi-card tests that prove stale enforcement, acknowledgement
  gates, and no-live counters.
- Add operator documentation for replacement checklist and command-copy packets.

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

- This slice writes only local child replacement checklist and command-copy
  artifacts. It does not create selected targets, process private SyncThing
  images, execute live lookup, route to live sinks, enrich, write contacts, run
  public-web search, call paid APIs, or call GWS/Odollo/Odoo.

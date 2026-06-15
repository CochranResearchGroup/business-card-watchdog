# Plan 0024 | Child Command Copy Acknowledgement

State: CLOSED
Product authority: `PRODUCT_SPEC.md`

## Scope

Create a no-live child selected-target command-copy packet that requires an
explicit operator acknowledgement before showing copy text for the next safe
offline command.

## Non-Goals

- Do not create `selected_live_target.json`.
- Do not expose or execute a live GWS/Odollo/Odoo command.
- Do not execute live lookup, write, or readback.
- Do not process private SyncThing images in validation.
- Do not perform public-web search or paid enrichment.
- Do not write sink contacts.
- Do not promote child contacts into parent job state.

## Acceptance Criteria

- Service builds a child command-copy packet from the child no-live execution
  checklist.
- Packet remains blocked until acknowledgement text names the run, child
  candidate, sink, and operator and includes an approval/copy intent.
- Packet never returns an executable live command.
- CLI exposes a child command-copy packet command.
- API exposes a child command-copy packet route.
- MCP exposes a child command-copy packet tool.
- Synthetic tests cover service, CLI, API, and MCP behavior.

## Execution Log

### Slice 0024-A | 2026-06-15 | Offline Child Command Copy Gate

Implemented:

- Add child command-copy packet service method.
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

- This slice writes only local child command-copy packet artifacts. It does not
  create live selected targets, return executable live commands, process
  private SyncThing images, execute live lookup, route to live sinks, enrich,
  write contacts, run public-web search, call paid APIs, or call
  GWS/Odollo/Odoo.

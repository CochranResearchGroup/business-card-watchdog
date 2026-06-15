# Plan 0021 | Child Duplicate Resolution Gate

State: CLOSED
Product authority: `PRODUCT_SPEC.md`

## Scope

Record explicit operator duplicate decisions for child contacts and gate child
sink-plan progression based on downstream duplicate assessment state.

## Non-Goals

- Do not process private SyncThing images in validation.
- Do not execute live Google Contacts, Odoo, or Odollo lookup/write/readback.
- Do not perform public-web search or paid enrichment.
- Do not write sink contacts.
- Do not promote child contacts into parent job state.

## Acceptance Criteria

- Service records child duplicate resolutions for assessed child contacts.
- Service writes a child sink-plan gate artifact that blocks unresolved
  duplicates and clears explicitly resolved duplicates.
- CLI exposes child duplicate resolution and child sink-plan gate commands.
- API exposes child duplicate resolution and child sink-plan gate routes.
- MCP exposes child duplicate resolution and child sink-plan gate tools.
- Gate artifacts preserve parent job ID, candidate ID, work item ID, duplicate
  state, decision, planned sinks, and blocked reasons.
- Artifacts report zero live writes and zero network calls.
- Focused synthetic tests cover service, CLI, API, and MCP behavior.

## Execution Log

### Slice 0021-A | 2026-06-15 | Resolve Child Duplicate Gate

Implemented:

- Added `BusinessCardService.resolve_child_duplicate`.
- Added `BusinessCardService.child_sink_plan_gate`.
- Added CLI commands `reviews child-resolve-duplicate` and
  `reviews child-sink-plan-gate`.
- Added API routes `POST /reviews/children/{candidate_id}/duplicate-resolution`
  and `POST /reviews/children/{candidate_id}/sink-plan-gate`.
- Added MCP tools `business_card_watchdog_child_duplicate_resolution` and
  `business_card_watchdog_child_sink_plan_gate`.
- Added synthetic multi-card coverage for service, CLI, API, and MCP duplicate
  resolution plus gate clearing.

Validation:

- `.venv/bin/python -m pytest tests/test_review_surface.py::test_child_duplicate_resolution_clears_sink_plan_gate tests/test_cli_surfaces.py::test_cli_child_duplicate_resolution_clears_gate tests/test_api.py::test_api_child_duplicate_resolution_clears_gate tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_child_duplicate_resolution_clears_gate -q` passed with 5 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/cli.py src/business_card_watchdog/api.py src/business_card_watchdog/mcp.py tests/test_review_surface.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py` passed.
- `.venv/bin/python -m pytest -q` passed with 259 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This slice writes only local child duplicate resolution and gate artifacts.
  It does not process private SyncThing images, execute live lookup, write
  contacts, route to live sinks, enrich, run public-web search, call paid APIs,
  or call GWS/Odollo/Odoo.

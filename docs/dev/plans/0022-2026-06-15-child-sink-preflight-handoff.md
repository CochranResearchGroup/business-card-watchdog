# Plan 0022 | Child Sink Preflight And Handoff

State: CLOSED
Product authority: `PRODUCT_SPEC.md`

## Scope

Create child sink apply preflight previews and operator selected-target handoff
packets from cleared child sink-plan gates.

## Non-Goals

- Do not process private SyncThing images in validation.
- Do not create live selected-target artifacts.
- Do not execute live Google Contacts, Odoo, or Odollo lookup/write/readback.
- Do not perform public-web search or paid enrichment.
- Do not write sink contacts.
- Do not promote child contacts into parent job state.

## Acceptance Criteria

- Service writes child sink apply preflight previews from cleared child gates.
- Service writes child selected-target handoff packets with explicit no-live stop
  conditions.
- CLI exposes child apply preflight and child selected-target handoff commands.
- API exposes child apply preflight and child selected-target handoff routes.
- MCP exposes child apply preflight and child selected-target handoff tools.
- Handoff artifacts preserve parent job ID, candidate ID, work item ID, sink,
  operator, scope, and copyable command metadata.
- Artifacts report zero live writes and zero network calls.
- Focused synthetic tests cover service, CLI, API, and MCP behavior.

## Execution Log

### Slice 0022-A | 2026-06-15 | Preview Child Apply Boundary

Implemented:

- Added `BusinessCardService.child_sink_apply_preflight`.
- Added `BusinessCardService.child_selected_target_handoff`.
- Added CLI commands `reviews child-sink-apply-preflight` and
  `reviews child-selected-target-handoff`.
- Added API routes `POST /reviews/children/{candidate_id}/sink-apply-preflight`
  and `POST /reviews/children/{candidate_id}/selected-target-handoff`.
- Added MCP tools `business_card_watchdog_child_sink_apply_preflight` and
  `business_card_watchdog_child_selected_target_handoff`.
- Added synthetic multi-card coverage for service, CLI, API, and MCP preflight
  plus handoff creation.

Validation:

- `.venv/bin/python -m pytest tests/test_review_surface.py::test_child_sink_apply_preflight_and_selected_target_handoff tests/test_cli_surfaces.py::test_cli_child_sink_apply_preflight_and_handoff tests/test_api.py::test_api_child_sink_apply_preflight_and_handoff tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_child_sink_apply_preflight_and_handoff -q` passed with 5 tests.
- `.venv/bin/python -m pytest -q -x -vv` passed with 263 tests.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `uv build --out-dir dist` built source and wheel distributions.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This slice writes only local child preflight and handoff artifacts. It does
  not create live selected targets, process private SyncThing images, execute
  live lookup, route to live sinks, enrich, write contacts, run public-web
  search, call paid APIs, or call GWS/Odollo/Odoo.

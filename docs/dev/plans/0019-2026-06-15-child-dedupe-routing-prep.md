# Plan 0019 | Child Dedupe And Routing Prep

State: CLOSED
Product authority: `PRODUCT_SPEC.md`

## Scope

Consume approved child review artifacts from multi-card images and prepare local
dry-run downstream duplicate lookup and sink routing plan artifacts.

## Non-Goals

- Do not process private SyncThing images in validation.
- Do not execute live Google Contacts, Odoo, or Odollo lookup/write/readback.
- Do not perform public-web search or paid enrichment.
- Do not decide duplicate merges or write sink contacts.
- Do not promote child contacts into parent job state.

## Acceptance Criteria

- Service lists approved child contacts ready for route preparation.
- Service prepares dry-run child sink lookup and sink plan artifacts from a
  reviewed child contact.
- CLI exposes queue and prepare commands.
- API exposes queue and prepare routes.
- MCP exposes queue and prepare tools.
- Artifacts preserve parent job ID, candidate ID, work item ID, and reviewed
  child contact path.
- Prepared child artifacts report zero live writes and zero network calls.
- Focused synthetic tests cover service, CLI, API, and MCP behavior.

## Execution Log

### Slice 0019-A | 2026-06-15 | Dry-Run Child Route Prep

Implemented:

- Added `BusinessCardService.child_route_prep_queue`.
- Added `BusinessCardService.prepare_child_route`.
- Added CLI commands `reviews child-route-prep-queue` and
  `reviews child-route-prep <candidate-id>`.
- Added API routes `GET /reviews/children/route-prep` and
  `POST /reviews/children/{candidate_id}/route-prep`.
- Added MCP tools `business_card_watchdog_child_route_prep_queue` and
  `business_card_watchdog_child_route_prepare`.
- Added synthetic multi-card coverage for service, CLI, API, and MCP route prep.

Validation:

- `.venv/bin/python -m pytest tests/test_review_surface.py::test_child_route_prep_writes_dry_run_lookup_and_sink_plans tests/test_cli_surfaces.py::test_cli_child_route_prep_writes_dry_run_plans tests/test_api.py::test_api_child_route_prep_writes_dry_run_plans tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_child_route_prep_writes_dry_run_plans -q` passed with 5 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/cli.py src/business_card_watchdog/api.py src/business_card_watchdog/mcp.py tests/test_review_surface.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py` passed.
- `.venv/bin/python -m pytest -q` passed with 251 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This slice writes only local dry-run planning artifacts. It does not process
  private SyncThing images, call enrichment, execute live lookup, dedupe, route
  to sinks, write contacts, run public-web search, call paid APIs, or call
  GWS/Odollo/Odoo.

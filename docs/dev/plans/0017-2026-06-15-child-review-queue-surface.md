# Plan 0017 | Child Review Queue Surface

State: CLOSED
Product authority: `PRODUCT_SPEC.md`

## Scope

Expose promoted child contact candidates through review queue surfaces so operators and agent loops can inspect multi-card child candidates before any normal routing, enrichment, dedupe, or sink work.

## Non-Goals

- Do not process private SyncThing images in validation.
- Do not approve child contacts automatically.
- Do not route, enrich, dedupe, or write child contacts in this slice.
- Do not run public-web search or paid enrichment.
- Do not call GWS, Odollo, Odoo, or any live sink.

## Acceptance Criteria

- Service exposes a read-only child review queue for promoted child contact candidates.
- CLI exposes `reviews children`.
- API exposes `GET /reviews/children`.
- MCP exposes `business_card_watchdog_child_reviews_list`.
- Operator dashboard command/API/MCP maps advertise the child review queue.
- Queue entries include run ID, parent job ID, candidate ID, work item ID, contact candidate path, lineage, review state, and explicit next action.
- Focused tests cover service, CLI, API, and MCP surfaces with synthetic multi-card dry-run data.
- Validation includes focused tests, full tests, lint, build, gitleaks, diff check, CodeGraph sync/status, commit, push, and CI watch.

## Execution Log

### Slice 0017-A | 2026-06-15 | List Review-Pending Child Contacts

Implemented:

- Added `BusinessCardService.child_review_queue`.
- Added API route `GET /reviews/children`.
- Added CLI command `reviews children`.
- Added MCP tool `business_card_watchdog_child_reviews_list`.
- Added operator dashboard child review command/API/MCP map entries.
- Added synthetic multi-card coverage for service, CLI, API, and MCP child review list surfaces.

Validation:

- `.venv/bin/python -m pytest tests/test_review_surface.py::test_child_review_queue_lists_promoted_child_contact_candidates tests/test_cli_surfaces.py::test_cli_child_reviews_lists_promoted_child_candidates tests/test_api.py::test_api_child_reviews_lists_promoted_child_candidates tests/test_mcp.py::test_mcp_child_reviews_lists_promoted_child_candidates tests/test_mcp.py::test_manifest_has_process_tool -q` passed with 5 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/cli.py src/business_card_watchdog/api.py src/business_card_watchdog/mcp.py tests/test_review_surface.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py` passed.
- `.venv/bin/python -m pytest -q` passed with 243 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This slice is read-only review surfacing. It does not process private SyncThing images, approve child contacts, route, enrich, dedupe, write sinks, run public-web search, call paid APIs, or call GWS/Odollo/Odoo.

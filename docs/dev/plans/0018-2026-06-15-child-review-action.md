# Plan 0018 | Child Review Action

State: CLOSED
Product authority: `PRODUCT_SPEC.md`

## Scope

Allow operators and agent loops to submit explicit review decisions for promoted
child contact candidates created from multi-card images.

## Non-Goals

- Do not process private SyncThing images in validation.
- Do not auto-approve child contacts.
- Do not dedupe, enrich, route, or write child contacts in this slice.
- Do not run public-web search or paid enrichment.
- Do not call GWS, Odollo, Odoo, or any live sink.

## Acceptance Criteria

- Service accepts child candidate review decisions for promoted child contacts.
- Approval writes a reviewed child contact artifact and a child review result.
- Rejection and keep-review decisions remain outside routing.
- Child review queue reflects the latest child review result state.
- CLI exposes `reviews child-review`.
- API exposes `POST /reviews/children/{candidate_id}`.
- MCP exposes `business_card_watchdog_child_review_submit`.
- Focused tests cover service, CLI, API, and MCP surfaces with synthetic
  multi-card dry-run data.
- Validation distinguishes dry-run artifact creation from live sink evidence.

## Execution Log

### Slice 0018-A | 2026-06-15 | Submit Child Review Decisions

Implemented:

- Added `BusinessCardService.submit_child_review`.
- Added child review result state overlay to `BusinessCardService.child_review_queue`.
- Added CLI command `reviews child-review <candidate-id> --run-id <run-id>`.
- Added API route `POST /reviews/children/{candidate_id}`.
- Added MCP tool `business_card_watchdog_child_review_submit`.
- Added synthetic multi-card coverage for service, CLI, API, and MCP approval.

Validation:

- `.venv/bin/python -m pytest tests/test_review_surface.py::test_child_review_approval_writes_reviewed_child_contact_artifact tests/test_cli_surfaces.py::test_cli_child_review_approves_promoted_child_candidate tests/test_api.py::test_api_child_review_approves_promoted_child_candidate tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_child_review_approves_promoted_child_candidate -q` passed with 5 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/cli.py src/business_card_watchdog/api.py src/business_card_watchdog/mcp.py tests/test_review_surface.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py` passed.
- `.venv/bin/python -m pytest -q` passed with 247 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This slice writes only local synthetic review artifacts. It does not process
  private SyncThing images, route child contacts, dedupe, enrich, write sinks,
  run public-web search, call paid APIs, or call GWS/Odollo/Odoo.

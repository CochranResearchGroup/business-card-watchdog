# Plan 0014 | Child Verification Request Contract

State: CLOSED
Product authority: `PRODUCT_SPEC.md`

## Scope

Create a deterministic dry-run execution contract for crop-ready child work items. Each candidate crop should produce a request artifact that can later drive OCR/App Intelligence execution while preserving parent job lineage and explicit operator boundaries.

## Non-Goals

- Do not process private SyncThing images in validation.
- Do not execute OCR/App Intelligence in this slice.
- Do not normalize, dedupe, route, enrich, or write contacts from request artifacts.
- Do not run public-web search or paid enrichment.
- Do not call GWS, Odollo, Odoo, or any live sink.

## Acceptance Criteria

- Batch processing writes `child_verification_requests.json` when crop-ready candidate work items exist.
- Each request links to its parent job, candidate ID, work item ID, crop path, and intended `business-card-to-contact` adapter.
- Requests explicitly record `executed: false`, `requires_explicit_execution: true`, and route/enrichment/write denial flags.
- `candidate_work_items.json` records `verification_request_ready` and the request ID for each crop-ready child item.
- The run ledger records a `child_verification_requests` artifact and `child_verification_requests_recorded` event.
- Focused tests prove the request contract from a synthetic multi-card dry-run batch.
- Validation includes focused tests, full tests, lint, build, gitleaks, diff check, CodeGraph sync/status, commit, push, and CI watch.

## Execution Log

### Slice 0014-A | 2026-06-15 | Persist Dry-Run Child Verification Requests

Implemented:

- Added `business-card-watchdog.child-verification-requests.v1`.
- Added deterministic request manifest construction from crop-ready child work items.
- Wired batch orchestration to persist `child_verification_requests.json`.
- Updated synthetic multi-card dry-run coverage to verify request lineage, dry-run state, explicit execution gate, and ledger records.

Validation:

- `.venv/bin/python -m pytest tests/test_preclassifier.py::test_orchestrator_records_multi_card_candidate_manifest -q` passed with 1 test.
- `.venv/bin/ruff check src/business_card_watchdog/fanout.py src/business_card_watchdog/orchestrator.py tests/test_preclassifier.py` passed.
- `.venv/bin/python -m pytest -q` passed with 239 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This slice creates execution-request artifacts only. It does not execute OCR/App Intelligence, normalize child contacts, route, enrich, write sinks, run public-web search, call paid APIs, or call GWS/Odollo/Odoo.

# Plan 0015 | Synthetic Child Verification Results

State: CLOSED
Product authority: `PRODUCT_SPEC.md`

## Scope

Add an offline synthetic executor for child verification requests so crop-ready multi-card candidates can produce result artifacts for review without using private images, real OCR/App Intelligence, enrichment, or live sinks.

## Non-Goals

- Do not process private SyncThing images in validation.
- Do not invoke production OCR/App Intelligence providers.
- Do not promote child results into canonical contacts in this slice.
- Do not normalize, dedupe, route, enrich, or write contacts from child result artifacts.
- Do not run public-web search or paid enrichment.
- Do not call GWS, Odollo, Odoo, or any live sink.

## Acceptance Criteria

- Batch processing writes `child_verification_results.json` when child verification requests exist.
- Each result links to its request ID, work item ID, candidate ID, parent job, crop path, and synthetic result detail file.
- Result detail files include synthetic OCR text, synthetic contact spec, confidence evidence, review requirement, and route/enrichment/write denial flags.
- `candidate_work_items.json` moves child items to `verification_result_ready` and `awaiting_child_review`.
- The run ledger records a `child_verification_results` artifact and `child_verification_results_recorded` event.
- Focused tests prove synthetic child result artifacts from a synthetic multi-card dry-run batch.
- Validation includes focused tests, full tests, lint, build, gitleaks, diff check, CodeGraph sync/status, commit, push, and CI watch.

## Execution Log

### Slice 0015-A | 2026-06-15 | Persist Synthetic Child Verification Results

Implemented:

- Added `business-card-watchdog.child-verification-results.v1`.
- Added synthetic offline child verification result construction from request artifacts.
- Wired batch orchestration to persist `child_verification_results.json` and per-candidate result files.
- Updated synthetic multi-card dry-run coverage to verify result lineage, review requirement, and route/enrichment/write denial flags.

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

- This slice creates synthetic offline result artifacts only. It does not process private SyncThing images, execute production OCR/App Intelligence, promote child contacts, route, enrich, write sinks, run public-web search, call paid APIs, or call GWS/Odollo/Odoo.

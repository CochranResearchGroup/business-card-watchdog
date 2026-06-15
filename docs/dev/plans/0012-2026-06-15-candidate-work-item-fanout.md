# Plan 0012 | Candidate Work Item Fanout

State: CLOSED
Product authority: `PRODUCT_SPEC.md`

## Scope

Convert deterministic `card_candidates.json` records into durable pending child work items for later crop, OCR, App Intelligence verification, review, and routing. This is the queue-planning step between multi-card detection and per-card processing.

## Non-Goals

- Do not process private SyncThing images.
- Do not crop images in this slice.
- Do not invoke OCR/App Intelligence for child work items.
- Do not route, enrich, or write contacts from pending child work items.
- Do not run public-web search or paid enrichment.
- Do not call GWS, Odollo, Odoo, or any live sink.

## Acceptance Criteria

- Batch processing writes `candidate_work_items.json` when `card_candidates.json` exists.
- Each candidate work item has a stable ID, parent job lineage, source image path, candidate box, pending OCR/App Intelligence phase, and explicit route/enrichment/write denial flags.
- The run ledger records a `candidate_work_items` artifact and `candidate_work_items_recorded` event.
- Focused tests prove the work item manifest from a synthetic multi-card dry-run batch.
- Validation includes focused tests, full tests, lint, build, gitleaks, diff check, CodeGraph sync/status, commit, push, and CI watch.

## Execution Log

### Slice 0012-A | 2026-06-15 | Persist Pending Candidate Work Items

Implemented:

- Added `business-card-watchdog.card-candidate-work-items.v1`.
- Added deterministic fanout manifest construction from candidate boxes.
- Wired batch orchestration to persist `candidate_work_items.json` beside `card_candidates.json`.
- Extended synthetic multi-card dry-run coverage to verify pending child work items and ledger records.

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

- This slice is fixture/runtime-artifact only. It does not process private SyncThing inputs, crop images, run public-web search, call paid enrichment, invoke child OCR/App Intelligence, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.

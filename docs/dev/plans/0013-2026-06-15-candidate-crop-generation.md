# Plan 0013 | Candidate Crop Generation

State: CLOSED
Product authority: `PRODUCT_SPEC.md`

## Scope

Materialize deterministic image crops from `candidate_work_items.json` so each detected business-card-like rectangle has a bounded crop artifact ready for later OCR/App Intelligence verification.

## Non-Goals

- Do not process private SyncThing images in validation.
- Do not invoke OCR/App Intelligence for child work items.
- Do not normalize, dedupe, route, enrich, or write contacts from candidate crops.
- Do not run public-web search or paid enrichment.
- Do not call GWS, Odollo, Odoo, or any live sink.

## Acceptance Criteria

- Batch processing writes `candidate_crops.json` when candidate work items exist.
- Crop images are written under the job artifact directory with parent job and candidate lineage.
- `candidate_work_items.json` is updated so successfully cropped items move to `crop_ready` and point to their crop path and bounds.
- The run ledger records a `candidate_crops` artifact and `candidate_crops_recorded` event.
- Focused tests prove crop artifacts from a synthetic multi-card dry-run batch.
- Validation includes focused tests, full tests, lint, build, gitleaks, diff check, CodeGraph sync/status, commit, push, and CI watch.

## Execution Log

### Slice 0013-A | 2026-06-15 | Persist Candidate Crop Artifacts

Implemented:

- Added `business-card-watchdog.card-candidate-crops.v1`.
- Added bounded crop materialization from candidate work items.
- Wired batch orchestration to persist `candidate_crops.json` and crop images under each job artifact directory.
- Updated synthetic multi-card dry-run coverage to verify crop files, work item state, and ledger records.

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

- This slice uses synthetic fixture images for validation. It does not run OCR/App Intelligence, normalize child contacts, route, enrich, write sinks, run public-web search, call paid APIs, or call GWS/Odollo/Odoo.

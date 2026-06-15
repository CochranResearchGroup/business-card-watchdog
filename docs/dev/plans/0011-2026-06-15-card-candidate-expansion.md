# Plan 0011 | Card Candidate Expansion

State: CLOSED
Product authority: `PRODUCT_SPEC.md`

## Scope

Persist deterministic multi-card candidate boxes as stable, addressable batch artifacts before OCR/App Intelligence. This converts OpenCV preclassification boxes into a `card_candidates.json` manifest that later fanout work can use to create child OCR/App Intelligence jobs.

## Non-Goals

- Do not process private SyncThing images.
- Do not crop or split real images into child OCR jobs in this slice.
- Do not invoke OCR/App Intelligence for each candidate box.
- Do not run public-web search or paid enrichment.
- Do not call GWS, Odollo, Odoo, or any live sink.
- Do not route, enrich, or write contacts from candidate boxes.

## Acceptance Criteria

- Preclassifier OpenCV boxes become stable candidate records with deterministic candidate IDs.
- Batch processing writes `card_candidates.json` when deterministic candidate boxes exist.
- The run ledger records a `card_candidates` artifact and `card_candidates_recorded` event.
- Candidate manifests state that boxes are pre-OCR evidence and require OCR/App Intelligence verification before routing.
- Validation includes focused tests, full tests, lint, build, gitleaks, diff check, CodeGraph sync/status, commit, push, and CI watch.

## Execution Log

### Slice 0011-A | 2026-06-15 | Persist Multi-Card Candidate Manifests

Implemented:

- Added `business-card-watchdog.card-candidate-boxes.v1`.
- Added deterministic candidate manifest construction from OpenCV rectangle boxes.
- Wired batch orchestration to persist `card_candidates.json` before OCR/App Intelligence when boxes exist.
- Added synthetic multi-card fixture coverage for normal dry-run batch processing.

Validation:

- `.venv/bin/python -m pytest tests/test_preclassifier.py::test_preclassifier_detects_multiple_cards_in_large_photo tests/test_preclassifier.py::test_orchestrator_records_multi_card_candidate_manifest -q` passed with 2 tests.
- `.venv/bin/ruff check src/business_card_watchdog/preclassifier.py src/business_card_watchdog/orchestrator.py tests/test_preclassifier.py tests/synthetic_fixtures.py` passed.
- `.venv/bin/python -m pytest -q` passed with 239 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This slice is fixture/runtime-artifact only. It does not process private SyncThing inputs, run public-web search, call paid enrichment, invoke per-candidate OCR/App Intelligence, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.

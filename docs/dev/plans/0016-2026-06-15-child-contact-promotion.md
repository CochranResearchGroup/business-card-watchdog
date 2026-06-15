# Plan 0016 | Child Contact Promotion

State: CLOSED
Product authority: `PRODUCT_SPEC.md`

## Scope

Promote reviewed child verification result data into ordinary contact-candidate artifacts while preserving parent/child lineage and keeping all routing, enrichment, and sink writes disabled until review.

## Non-Goals

- Do not process private SyncThing images in validation.
- Do not invoke production OCR/App Intelligence providers.
- Do not auto-approve or auto-route child contact candidates.
- Do not run public-web search or paid enrichment.
- Do not call GWS, Odollo, Odoo, or any live sink.

## Acceptance Criteria

- Batch processing writes `child_contact_promotions.json` when child verification results exist.
- Each promotion links parent job, candidate ID, work item ID, verification result path, and promoted contact-candidate path.
- Each child contact candidate uses the normal `business-card-watchdog.contact-candidate.v1` schema with source `child_verification_result`.
- Child candidates include lineage and review state, and deny routing/enrichment/write until reviewed.
- `candidate_work_items.json` moves child items to `child_contact_candidate_ready` and `awaiting_child_contact_review`.
- The run ledger records a `child_contact_promotions` artifact and `child_contact_promotions_recorded` event.
- Focused tests prove promotion artifacts from a synthetic multi-card dry-run batch.
- Validation includes focused tests, full tests, lint, build, gitleaks, diff check, CodeGraph sync/status, commit, push, and CI watch.

## Execution Log

### Slice 0016-A | 2026-06-15 | Promote Synthetic Child Results To Contact Candidates

Implemented:

- Added `business-card-watchdog.child-contact-promotions.v1`.
- Added child result promotion into normalized contact-candidate artifacts.
- Wired batch orchestration to persist `child_contact_promotions.json` and child contact candidate files.
- Updated synthetic multi-card dry-run coverage to verify lineage, review state, normalized email, and route/enrichment/write denial flags.

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

- This slice creates review-pending child contact candidates only. It does not process private SyncThing images, execute production OCR/App Intelligence, auto-route contacts, run public-web search, call paid APIs, or call GWS/Odollo/Odoo.

# Plan 0066 | OCR Side Classification And Pair Proposals

State: CLOSED
Date: 2026-06-22

Parent: Plan 0060 Milestone 3

## Purpose

Add deterministic OCR-assisted card-side classification and front/back pair
proposal artifacts for scanner document pages.

## Scope

- Read per-page OCR text artifacts as evidence after the image extraction
  pipeline runs.
- Classify page-side candidates as `front`, `back`, `blank`, or `unknown` using
  deterministic contextual clues.
- Preserve scanner page lineage and OCR clues in `card_side_candidate.json`.
- Add run-level front/back pair proposals scored from same-document page
  adjacency, side labels, OCR token/domain overlap, and negative conflict
  evidence.
- Block ambiguous or conflicting pair proposals for review instead of merging
  contacts.

## Non-Goals

- No automatic front/back contact merge.
- No paid enrichment.
- No public-web calls.
- No live sink writes.
- No new OCR engine.

## Acceptance Criteria

- Scanner PDF fixture pages can produce `front`, `back`, `blank`, and
  `unknown` side classifications from OCR text.
- Consecutive front/back page candidates produce a reviewable pair proposal.
- Reversed back/front page order can still produce a pair proposal.
- Blank or conflicting backs are blocked or skipped rather than merged.
- Pair proposals include evidence and negative evidence.

## Validation

- Unit tests for OCR side classification clues.
- Synthetic scanner run tests for front/back, reversed order, blank backs, and
  conflicting OCR evidence.
- Existing dry-run, watcher, contact-store, API, CLI, and MCP tests remain
  green.

## Closeout Evidence

Implemented:

- Added `src/business_card_watchdog/card_sides.py`.
- Added deterministic OCR-assisted side classification for `front`, `back`,
  `blank`, and `unknown` labels.
- Updated scanner page jobs so `card_side_candidate.json` is rewritten after
  OCR text exists, preserving OCR feature evidence and OCR text hash.
- Added run-level `card_side_pair_proposals.json` artifacts with same-document,
  adjacency, side-label, and negative conflict evidence.
- Supported reversed back/front scanner order by assigning front/back roles from
  side labels rather than page order.
- Blocked conflicting-domain pair proposals for review instead of merging.
- Kept blank backs skipped from pair proposals.

Validation run:

- `.venv/bin/python -m pytest tests/test_card_sides.py tests/test_dry_run_pipeline.py::test_pdf_document_intake_materializes_page_jobs_and_side_candidates -q`
  passed with 5 tests.
- `.venv/bin/python -m pytest tests/test_card_sides.py tests/test_dry_run_pipeline.py tests/test_contact_store.py tests/test_watcher.py -q`
  passed with 29 tests.
- `.venv/bin/python -m pytest tests/test_service.py tests/test_review_surface.py tests/test_enrichment.py -q`
  passed with 141 tests.
- `.venv/bin/python -m pytest tests/test_api.py tests/test_cli_surfaces.py tests/test_mcp.py -q`
  passed with 111 tests.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `.venv/bin/python -m pytest -q` passed with 347 tests.

Safety:

- This slice treats OCR as evidence only. It does not automatically merge front
  and back contacts, run enrichment providers, run public-web search, execute
  live lookup/write/readback, or write Google Contacts, Odoo, or Odollo records.

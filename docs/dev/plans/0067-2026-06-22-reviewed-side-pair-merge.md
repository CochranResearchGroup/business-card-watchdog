# Plan 0067 | Reviewed Side Pair Merge

State: CLOSED
Date: 2026-06-22

Parent: Plan 0060 Milestone 3

## Purpose

Add an explicit host-owned review action that can merge a proposed front/back
card-side pair into one reviewed contact candidate with field-level side
provenance.

## Scope

- Add a side-pair review queue from `card_side_pair_proposals.json`.
- Add an explicit side-pair review submission command.
- Merge front/back contact candidates only when a reviewer approves a pair.
- Preserve field provenance showing whether each merged field came from the
  front side, back side, or both.
- Record durable review submission, merge result, and reviewed contact
  artifacts in the run ledger.

## Non-Goals

- No automatic front/back merge.
- No live sink writes.
- No paid enrichment or public-web calls.
- No new OCR engine behavior.

## Acceptance Criteria

- Pair proposals can be listed for review.
- Approving a proposed pair writes a merged reviewed contact artifact.
- Rejecting or keeping a pair for review does not create a merged contact.
- Merged fields include side provenance.
- Merge artifacts remain replayable through the run ledger.

## Validation

- Service tests for side-pair queue, approval, rejection, and provenance.
- CLI JSON smoke for side-pair review.
- Existing dry-run, scanner, service, API, CLI, and MCP tests remain green.

## Closeout Evidence

Implemented:

- Added side-pair review queue support from `card_side_pair_proposals.json`.
- Added explicit side-pair review submission support for
  `approve_side_pair_merge`, `keep_needs_review`, and `reject_side_pair`.
- Added `bcw reviews side-pairs` and `bcw reviews side-pair-review`.
- Added `merge_side_pair_contacts` to merge front/back contact candidates only
  after explicit review.
- Wrote durable `side_pair_review_submission`,
  `reviewed_side_pair_contact`, and `side_pair_review_result` artifacts.
- Preserved field-level side provenance for merged fields: `front`, `back`,
  `both`, or `reviewer_correction`.
- Kept merged side-pair contacts out of routing/sink writes pending final
  contact review.

Validation run:

- `.venv/bin/python -m pytest tests/test_card_sides.py -q` passed with 7
  tests.
- `.venv/bin/python -m pytest tests/test_card_sides.py tests/test_review_surface.py tests/test_cli_surfaces.py -q`
  passed with 67 tests.
- `.venv/bin/python -m pytest tests/test_contact_store.py tests/test_dry_run_pipeline.py tests/test_service.py -q`
  passed with 119 tests.
- `.venv/bin/python -m pytest tests/test_api.py tests/test_mcp.py -q` passed
  with 60 tests.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `.venv/bin/python -m pytest -q` passed with 350 tests.

Safety:

- This slice does not automatically merge side pairs, route merged contacts,
  run enrichment providers, run public-web search, execute live
  lookup/write/readback, or write Google Contacts, Odoo, or Odollo records.

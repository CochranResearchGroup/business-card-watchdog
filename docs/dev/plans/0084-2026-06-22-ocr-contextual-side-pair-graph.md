# Plan 0084 | OCR Contextual Side-Pair Graph

State: CLOSED
Date: 2026-06-22

Parent: Plan 0060 Milestone 3

## Purpose

Harden front/back business-card pairing for regular double-sided scanner
workflows so scanner adjacency is only one weighted clue, not the pairing
algorithm.

## Scope

- Replace the adjacent-page-only pair proposal pass with a bounded
  session-level pair graph.
- Evaluate plausible front/back candidates within a scanner session window.
- Require OCR or capture context beyond page proximity before a pair can become
  `proposed`.
- Preserve blocked proposals and unpaired non-blank backs for review.
- Support same-stem front/back image captures outside PDFs.
- Add regression coverage for adjacency-only blocks, non-adjacent compatible
  backs, conflicting adjacent backs, and same-stem captures.

## Non-Goals

- No automatic front/back merge.
- No new OCR engine.
- No live sink lookup, write, or readback.
- No public-web or paid enrichment calls.
- No processing of private SyncThing/scanner inputs.

## Acceptance Criteria

- Pair proposals can consider non-adjacent candidates within a bounded session
  window.
- Adjacent front/back-looking pages without required OCR/capture context are
  blocked for review.
- A non-adjacent OCR-compatible back can outrank an adjacent conflicting back.
- Same-stem image captures can produce a front/back proposal outside PDFs.
- Pair artifacts retain score, evidence, negative evidence, blocked reason, and
  reviewable state.

## Validation

- Focused card-side pair-graph tests.
- Scanner dry-run pipeline and contact-store projection regression tests.
- `ruff`, `git diff --check`, and plan drift guard.

## Closeout Evidence

Implemented:

- Replaced adjacent-only pair generation with a bounded pairing-session graph.
- Added pairing session keys for PDFs and same-stem image captures.
- Added OCR/capture evidence for shared domains, email-domain-to-back-URL
  matches, OCR token overlap, same capture stem, and complementary side density.
- Required concrete OCR/capture evidence before a pair can become `proposed`;
  adjacency and side-label complement alone now block for review.
- Preserved adjacent transition skips and unpaired non-blank side candidates
  for review.
- Sorted proposals so proposed, higher-scoring OCR-compatible pairs outrank
  blocked/conflicting pairs.
- Added tests for adjacency-only blocking, non-adjacent compatible backs,
  adjacent conflicting backs, same-stem image captures, reversed order, blank
  backs, and reviewed side-pair merge behavior.

Validation run:

- `.venv/bin/python -m pytest tests/test_card_sides.py -q` passed with 10
  tests.
- `.venv/bin/ruff check src/business_card_watchdog/card_sides.py tests/test_card_sides.py`
  passed.
- `.venv/bin/python -m pytest tests/test_card_sides.py tests/test_dry_run_pipeline.py tests/test_contact_store.py -q`
  passed with 25 tests.
- `git diff --check` passed.
- `.venv/bin/python scripts/check_plan_drift.py` passed.
- `.venv/bin/ruff check .` passed.
- `.venv/bin/python -m pytest -q` passed with 390 tests.

Safety:

- This slice did not process private SyncThing/scanner inputs, run live
  lookup/write/readback, merge side pairs automatically, call enrichment
  providers, or expose private image bytes.

# Plan 0074 | Enrichment Review Provenance Projection

State: CLOSED
Date: 2026-06-22

## Purpose

Advance Plan 0060 Milestone 5 by projecting reviewed enrichment merge decisions
into the user-scoped contact database, so enrichment provenance and review
status are visible from contact rows and not only from run-ledger artifacts.

## Scope

- Project `enrichment_merge_review` and `enrichment_proposal_review` artifacts
  as enrichment attempts with meaningful provider and review state.
- Preserve accepted/rejected proposal counts, approved fields, reviewer, source
  provider, and source result schema in the projected attempt payload.
- Include `enrichment_proposal_review` in projected asset lineage.
- Keep the existing ledger artifacts authoritative and replayable.

## Non-Goals

- No live enrichment provider calls.
- No public-web search.
- No paid API execution.
- No automatic enrichment merge without review.
- No sink writes.

## Acceptance Criteria

- Contact detail shows enrichment attempts for request/result/review artifacts
  after projection.
- Review artifacts project with `reviewed`, `accepted`, or `rejected` states
  instead of opaque `recorded` state.
- Projected payloads expose reviewer, approved fields, accepted/rejected counts,
  and source provider without credential values.
- Reprojection remains idempotent.

## Validation

- Contact-store projection test for enrichment merge review provenance.
- Targeted contact-store tests.
- Targeted ruff, full ruff, full pytest, `git diff --check`, plan drift guard,
  and CodeGraph sync/status.

## Closeout

Implemented:

- Projected `enrichment_proposal_review` as both contact asset lineage and a
  database-backed enrichment attempt.
- Projected enrichment review artifacts with meaningful `reviewed`, `accepted`,
  or `rejected` states.
- Added review summaries to projected enrichment payloads, including reviewer,
  approved fields, source provider, source result schema, accepted/rejected
  counts, and per-proposal decisions.
- Preserved idempotent reprojection through stable enrichment attempt IDs.

Validation:

- `.venv/bin/python -m pytest tests/test_contact_store.py::test_contact_store_projects_enrichment_review_provenance -q`
  passed with 1 test.
- `.venv/bin/python -m pytest tests/test_contact_store.py -q` passed with 6
  tests.
- `.venv/bin/ruff check src/business_card_watchdog/contact_store.py tests/test_contact_store.py`
  passed.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `.venv/bin/python scripts/check_plan_drift.py` passed.
- `.venv/bin/python -m pytest -q` passed with 364 tests.
- `codegraph sync /home/ecochran76/workspace.local/business-card-watchdog && codegraph status /home/ecochran76/workspace.local/business-card-watchdog`
  reported the index already up to date, 60 files, 1,958 nodes, and 2,212
  edges.

Safety:

- This slice did not make live enrichment, public-web, paid API, Google
  Contacts, Odoo, or Odollo calls. It did not process configured
  SyncThing/private watch inputs, automatically merge enrichment without review,
  or write sink records.

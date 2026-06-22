# Plan 0063 | User-Scoped Contact Store

State: CLOSED
Date: 2026-06-21

Parent: Plan 0060 Milestone 1

## Purpose

Implement the first bounded slice of the Plan 0060 contact database: a local
SQLite store under the user data directory plus an idempotent manual projection
from existing dry-run contact artifacts.

## Scope

- Add a user-scoped SQLite database at
  `~/.local/share/business-card-watchdog/contacts/contacts.sqlite`.
- Add schema/migration support for contacts, card assets, extraction attempts,
  enrichment attempts, routing decisions, sink attempts, and external tenant
  bindings.
- Add repository methods for deterministic contact upsert, lookup, listing,
  and projection from run artifacts.
- Add service and CLI inspection/projection surfaces.
- Keep existing run ledgers and artifacts as replay evidence.

## Non-Goals

- No live Google, Odoo, Odollo, Apollo, People Data Labs, or web-search calls.
- No watcher pipeline database writes.
- No private image/PDF processing.
- No automatic duplicate merge or sink mutation.

## Acceptance Criteria

- A fresh user data directory initializes the database and schema.
- Existing fixture dry-run artifacts can be projected into contact rows.
- Projection is idempotent for the same run/job artifacts.
- Contact rows retain source run/job IDs, extraction provenance, and asset
  references.
- CLI read-only inspection can list and show projected contact rows.

## Validation

- Unit tests for migrations and repository operations.
- Fixture-backed projection test from a dry-run artifact.
- CLI JSON smoke for init, project-run, list, and show.
- `ruff`, targeted tests, `git diff --check`, and plan drift guard.

## Closeout Evidence

Implemented:

- Added `src/business_card_watchdog/contact_store.py` with SQLite schema
  versioning under `data_dir/contacts/contacts.sqlite`.
- Added tables for contacts, card assets, extraction attempts, enrichment
  attempts, routing decisions, sink attempts, and external tenant bindings.
- Added deterministic contact, asset, and extraction-attempt IDs for idempotent
  projection.
- Added `BusinessCardService` contact-store status, initialization, list, show,
  and run-projection methods.
- Added `bcw contacts status|init|list|show|project-run`.
- Added tests for migration, idempotent synthetic-run projection, and CLI JSON
  smoke.

Validation run:

- `pytest tests/test_contact_store.py -q` passed with 3 tests.
- `pytest tests/test_contact.py tests/test_state_and_ledger.py tests/test_api.py -q`
  passed with 9 tests and 1 skipped.
- `.venv/bin/ruff check .` passed.
- `.venv/bin/python -m pytest tests/test_contact_store.py tests/test_contact.py tests/test_state_and_ledger.py -q`
  passed with 12 tests.
- `.venv/bin/python -m pytest -q` passed with 340 tests.
- `git diff --check` passed.
- `python3 scripts/check_plan_drift.py` passed.

Safety:

- This slice does not process configured watched folders, OCR private images,
  rasterize PDFs, run enrichment, run live lookup/write/readback, or write
  Google Contacts, Odoo, or Odollo records.
- Projection is manual and reads existing run artifacts. The watcher pipeline
  remains artifact-ledger first until a later Plan 0060 milestone wires
  automatic projection.

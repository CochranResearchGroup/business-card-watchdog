# Plan 0064 | Artifact-To-Database Projection

State: CLOSED
Date: 2026-06-22

Parent: Plan 0060 Milestone 2

## Purpose

Wire the current dry-run batch pipeline to project completed extraction
artifacts into the user-scoped contact store while preserving run ledgers as
the replay authority.

## Scope

- Add an automatic post-run projection step after batch extraction artifacts are
  recorded.
- Keep projection failures retryable by recording ledger evidence instead of
  making run artifacts unreadable.
- Extend projection to capture normalized contact fields, extraction
  provenance, crop/source asset references, duplicate evidence, enrichment
  request/result state, route readiness, and sink attempt summaries from
  existing artifacts.
- Add a drift/readback check between run artifacts and contact-store rows.
- Keep the existing manual `bcw contacts project-run` repair/replay command.

## Non-Goals

- No new OCR engine behavior.
- No live Google, Odoo, Odollo, Apollo, People Data Labs, or web-search calls.
- No automatic duplicate merge.
- No private watched-folder processing beyond explicit operator invocation of
  existing commands.

## Acceptance Criteria

- Dry-run batch processing writes contact rows after extraction/review artifacts
  exist.
- Re-running projection for the same run is idempotent.
- Projection failure records retryable ledger evidence and leaves the run ledger
  readable.
- Drift/readback reports whether artifact contact candidates and store contacts
  agree for a run.
- Contact detail rows expose projected route, enrichment, sink, asset, and
  extraction provenance where source artifacts exist.

## Validation

- Projection idempotency tests.
- Fixture dry-run pipeline projection test.
- Projection failure/retry evidence test.
- Drift/readback test.
- Existing service/API/CLI/MCP tests remain green.

## Closeout Evidence

Implemented:

- Added automatic post-run contact-store projection from
  `BatchOrchestrator.process_source` after job extraction artifacts are written.
- Added `contact_store_projection.json` run artifact and
  `contact_store_projected` ledger event on success.
- Added retryable `contact_store_projection_failed` ledger event on projection
  failure with a `contacts project-run <run-id> --json` repair command.
- Extended contact-store projection to capture route decisions, sink attempts,
  enrichment attempts, source/crop/OCR/review assets, normalized fields, and
  extraction provenance from existing artifacts.
- Added contact-store drift/readback status and `bcw contacts drift <run-id>`.
- Kept `bcw contacts project-run <run-id>` as the manual replay/repair path and
  included drift output in its JSON response.

Validation run:

- `.venv/bin/python -m pytest tests/test_contact_store.py tests/test_dry_run_pipeline.py -q`
  passed with 6 tests.
- `.venv/bin/python -m pytest tests/test_api.py tests/test_cli_surfaces.py tests/test_mcp.py -q`
  passed with 111 tests.
- `.venv/bin/python -m pytest tests/test_service.py tests/test_review_surface.py tests/test_enrichment.py -q`
  passed with 141 tests.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `.venv/bin/python -m pytest -q` passed with 341 tests.

Safety:

- This slice only projects artifacts that already exist in run ledgers. It did
  not add OCR behavior, rasterize PDFs, process private watched folders on its
  own, run enrichment providers, run live lookup/write/readback, or write Google
  Contacts, Odoo, or Odollo records.

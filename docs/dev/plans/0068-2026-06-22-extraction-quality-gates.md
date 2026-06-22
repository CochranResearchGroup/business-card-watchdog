# Plan 0068 | Extraction Quality Gates

State: CLOSED
Date: 2026-06-22

## Purpose

Execute the Plan 0060 Milestone 3 quality-gate hardening slice so scanner and
image jobs persist deterministic crop/OCR quality evidence before any contact
can become route-ready.

## Scope

- Add a deterministic extraction-quality artifact for successful adapter runs.
- Check OCR text presence/volume and crop-manifest presence/count.
- Treat scanner page side labels as route-readiness evidence: `front` can
  continue, while `back`, `blank`, and `unknown` require review or side-pair
  handling.
- Include quality evidence in review packets when quality blocks routing.
- Keep live sink behavior unchanged.

## Non-Goals

- No live Google Contacts, Odoo, or Odollo writes.
- No paid enrichment or public web search.
- No stochastic quality reviewer in this slice.
- No automatic side-pair merge.

## Acceptance Criteria

- Good synthetic image fixtures still reach `ready_to_route`.
- Every successful adapter run records an `extraction_quality` artifact.
- Missing/short OCR or missing/empty crop manifests force `needs_review`.
- Scanner `back`, `blank`, and `unknown` page contacts cannot route directly.
- Review packets expose the extraction-quality reasons.

## Validation

- Unit tests for quality assessment.
- Pipeline tests for pass and review-blocking quality states.
- Targeted pytest, ruff, `git diff --check`, full pytest, and plan drift guard.

## Closeout

Implemented:

- Added `business-card-watchdog.extraction-quality.v1` artifacts.
- Assessed OCR token count and crop-manifest presence/count for every
  successful adapter run.
- Blocked scanner page contacts whose side classification is `back`, `blank`,
  `unknown`, or missing from direct route-readiness.
- Added extraction-quality evidence to review packets.
- Preserved dry-run sink behavior for good synthetic front-side contacts.

Validation:

- `.venv/bin/python -m pytest tests/test_quality.py tests/test_dry_run_pipeline.py::test_batch_dry_run_uses_synthetic_adapter_without_credentials tests/test_dry_run_pipeline.py::test_incomplete_synthetic_spec_creates_review_packet tests/test_dry_run_pipeline.py::test_short_ocr_quality_creates_review_packet_before_routing -q`
  passed with 6 tests.
- `.venv/bin/python -m pytest tests/test_quality.py tests/test_card_sides.py tests/test_dry_run_pipeline.py -q`
  passed with 15 tests.
- `.venv/bin/python -m pytest tests/test_quality.py tests/test_card_sides.py tests/test_dry_run_pipeline.py tests/test_contact_store.py tests/test_review_surface.py -q`
  passed with 27 tests.
- `.venv/bin/python -m pytest tests/test_service.py tests/test_api.py tests/test_mcp.py tests/test_cli_surfaces.py -q`
  passed with 223 tests.
- `.venv/bin/ruff check src/business_card_watchdog tests/test_quality.py tests/test_card_sides.py tests/test_dry_run_pipeline.py`
  passed.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `.venv/bin/python scripts/check_plan_drift.py` passed.
- `.venv/bin/python -m pytest -q` passed with 354 tests.
- `codegraph sync /home/ecochran76/workspace.local/business-card-watchdog && codegraph status /home/ecochran76/workspace.local/business-card-watchdog`
  reported the index already up to date, 60 files, 1,913 nodes, and 2,567
  edges.

Safety:

- No live sink writes, paid enrichment, public web search, or automatic
  front/back merge were added.

# Plan 0065 | Scanner Document Intake

State: CLOSED
Date: 2026-06-22

Parent: Plan 0060 Milestone 3

## Purpose

Add the first scanner-intake foundation for Plan 0060 Milestone 3: PDFs are
document sources that produce page-image child jobs, explicit source-page
lineage, and initial card-side candidates before later OCR side classification
and pairing.

## Scope

- Keep `is_supported_image` image-only.
- Add a document intake boundary for `.pdf` files.
- Materialize PDF pages under run artifacts as page images, using local
  `pdftoppm` when available and deterministic placeholder page images for
  synthetic/unsupported fixtures.
- Record document-page, source-page, and initial card-side-candidate artifacts.
- Feed page-image children through the existing dry-run image pipeline.
- Make watched-folder discovery process PDFs as document sources.
- Keep practice-corpus manifest PDF entries separate from image inputs while
  reporting scanner document intake support.

## Non-Goals

- No full OCR side classifier yet.
- No front/back pair graph yet.
- No live sink writes.
- No paid enrichment or public-web calls.
- No mutation of source PDFs.

## Acceptance Criteria

- A PDF source produces document-page artifacts and one page-image child job per
  detected page.
- Page-image child jobs retain source PDF path and page-number lineage.
- Each page-image job gets an initial `unknown` card-side candidate requiring
  OCR classification.
- Watcher status and scan discovery include PDFs as processable document
  sources without treating PDFs as images.
- Existing image-only runs remain compatible.

## Validation

- Synthetic PDF intake test.
- Watcher PDF discovery test.
- Practice-corpus manifest test updates.
- Existing dry-run pipeline, service, API, CLI, MCP tests remain green.

## Closeout Evidence

Implemented:

- Added `src/business_card_watchdog/document_intake.py`.
- Kept `is_supported_image` image-only and added `.pdf` document-source
  support through `is_supported_document`.
- Added `discover_processable_sources` so the orchestrator and watcher can
  process images and PDF document sources separately.
- Added PDF page materialization under `run_dir/document_intake/`, using local
  `pdftoppm` when available and deterministic placeholder page images for
  synthetic/unsupported fixtures.
- Added run-level `document_pages` artifacts and per-page `source_page` plus
  `card_side_candidate` artifacts.
- Fed PDF page-image children through the existing dry-run pipeline and contact
  store projection.
- Updated practice-corpus manifest semantics so PDF entries are scanner
  document-intake sources, not direct image inputs.

Validation run:

- `.venv/bin/python -m pytest tests/test_dry_run_pipeline.py tests/test_watcher.py tests/test_service.py::test_service_practice_corpus_manifest_inventories_images_and_pdfs_without_processing -q`
  passed with 23 tests.
- `.venv/bin/python -m pytest tests/test_dry_run_pipeline.py tests/test_watcher.py tests/test_service.py tests/test_contact_store.py -q`
  passed with 137 tests.
- `.venv/bin/python -m pytest tests/test_api.py tests/test_cli_surfaces.py tests/test_mcp.py -q`
  passed with 111 tests.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `.venv/bin/python -m pytest -q` passed with 343 tests.

Safety:

- This slice does not add live sink writes, paid enrichment, public-web calls,
  automatic front/back pairing, or source PDF mutation.
- Placeholder page images are used only when local PDF rasterization is
  unavailable or a synthetic/unsupported fixture cannot be rasterized.

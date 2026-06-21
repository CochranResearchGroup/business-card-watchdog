# Plan 0062 | Practice Corpus Manifest

State: CLOSED
Date: 2026-06-21

## Scope

Add a no-processing practice-corpus manifest for the configured watched inputs.
The manifest should inventory the current practice batch from both active watch
aliases, bounded by explicit include globs before hashing so historical scanner
archives are not pulled into the practice corpus:

- `$fsr:sync_phone`
- `$fsr:scanner`

The manifest is a runtime/control artifact for later PDF intake, front/back
side modeling, crop/OCR quality tests, and contact-store projection work.

## Non-Goals

- Do not process watched files.
- Do not OCR images or PDFs.
- Do not rasterize PDFs.
- Do not crop candidate cards.
- Do not infer or extract contact data.
- Do not run App Intelligence, enrichment, public-web search, paid APIs, live
  lookup, live write, or readback.
- Do not commit private file manifests or private card images to git.

## Acceptance Criteria

- A CLI command can generate a practice-corpus manifest from all configured
  watched inputs.
- The command supports explicit include globs so an operator can bound the
  private practice batch before hashing.
- The manifest includes source alias/ref, relative path, suffix, media kind,
  size, mtime, sha256, settle state, and role hints.
- The manifest includes supported image files and PDF documents.
- PDF entries are marked as document sources that are not currently processable
  by the image-only watcher.
- The command can preview without writing runtime artifacts.
- When writing is enabled, the manifest is stored only under user-scoped runtime
  state.
- The command reports zero files processed, zero OCR, zero writes to sinks, and
  zero network calls.

## Validation Plan

- Unit/service test with synthetic watched image and PDF files.
- CLI JSON test for preview mode.
- Runtime smoke against the configured two-folder watcher using `--no-write`.
- `ruff`, targeted tests, full tests, `git diff --check`, drift guard, and
  CodeGraph sync.

## Closeout

Implemented:

- Added `src/business_card_watchdog/practice_corpus.py`.
- Added `BusinessCardService.watch_practice_corpus_manifest`.
- Added `bcw watch-practice-corpus-manifest`.
- Added repeatable `--include-glob` filters so private practice batches can be
  bounded before hashing.
- Added no-processing manifest fields for source alias/ref, relative path,
  suffix, media kind, role hint, current watcher processability, size, mtime,
  sha256, and settle state.
- Added tests for service and CLI preview behavior with synthetic image and PDF
  files.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_practice_corpus_manifest_inventories_images_and_pdfs_without_processing tests/test_watcher.py::test_watch_practice_corpus_manifest_cli_previews_images_and_pdfs -q`
  passed with 2 tests.
- `.venv/bin/ruff check src/business_card_watchdog/practice_corpus.py src/business_card_watchdog/service.py src/business_card_watchdog/cli.py tests/test_service.py tests/test_watcher.py`
  passed.
- Runtime preview passed:
  `.venv/bin/bcw watch-practice-corpus-manifest --no-write --include-glob 'Camera/20260620_11*.jpg' --include-glob '2026_06_20_11_21_42.pdf' --json`
  reported 14 entries, 13 images, 1 PDF document, 13 current watcher-processable
  files, 0 unsettled, 0 errors, 0 files processed, 0 OCR, 0 PDF rasterization,
  0 crops, 0 writes, and 0 network calls.
- Runtime write passed:
  `.venv/bin/bcw watch-practice-corpus-manifest --include-glob 'Camera/20260620_11*.jpg' --include-glob '2026_06_20_11_21_42.pdf' --json`
  wrote
  `/home/ecochran76/.local/share/business-card-watchdog/practice_corpus_manifest.json`.
- `.venv/bin/python -m pytest -q` passed with 337 tests.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `python3 scripts/check_plan_drift.py` passed.
- `codegraph sync && codegraph status` passed; index is up to date with 53
  files, 1,738 nodes, and 3,026 edges.

Safety:

- This slice inventoried configured watched files only. It did not OCR, crop,
  rasterize PDFs, enrich, route, execute live lookup/write/readback, or write
  Google Contacts, Odoo, or Odollo records. The runtime manifest is
  user-scoped and must not be committed to git.

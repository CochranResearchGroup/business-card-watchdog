# Plan 0100 | Negative-Control Corpus Intake

State: COMPLETE
Date: 2026-06-27

Parent: Plan 0060 Milestone 9

## Purpose

Create a user-scoped negative-control corpus from scanner PDFs and images that
are operator-declared not to be business cards. This fills the missing evidence
class identified by the Plan 0098 exit gate without changing broad
autodetection thresholds.

The product needs negative controls because most scanner/image library
documents are not business cards. Recognition tuning must be able to prove that
improvements on known positives do not increase false positives on handouts,
flyers, forms, letters, receipts, worksheets, and other non-card documents.

## Scope

- Add a `negative-control-intake` service/CLI surface.
- Accept one or more source paths or `$fsr:` aliases.
- Support include globs and a bounded file limit for reviewable intake runs.
- Store selected source media under
  `~/.local/share/business-card-watchdog/negative_control_corpus/`.
- Append a redacted `negative_control_corpus/index.jsonl` row per unique file.
- Preserve content hash, media kind, suffix, size, label, category, and intake
  run identity.
- Redact original source paths and filenames from returned payloads and stored
  manifests.
- Produce dry-run preview output without copying files or writing runtime
  manifests.

## Non-Goals

- No broad watched-folder autodetection over unknown documents.
- No OCR, crop, PDF rasterization, contact extraction, enrichment, routing,
  sink write, readback, public-web search, or paid provider call.
- No committing private scanner/image documents, runtime blobs, OCR dumps,
  crops, contact data, or original filenames/paths.
- No treating unreviewed negatives as permission to change promotion
  thresholds.
- No classifier threshold changes in this plan.

## Milestone 1 | Negative-Control Intake Surface

Objective:

File selected scanner PDFs/images as negative-control evidence in
user-scoped runtime storage.

Acceptance criteria:

- The intake command supports `--source`, `--label`, `--category`,
  `--include-glob`, `--limit`, `--no-write`, and `--json`.
- Preview mode reports selected files without writing runtime blobs,
  manifests, or index rows.
- Write mode copies selected files into runtime-only blob storage and appends
  unique index rows.
- Repeated intake dedupes by SHA.
- Returned payloads and stored manifests redact source paths and filenames.
- Safety counters remain zero for OCR, PDF rasterization, crops, writes,
  network calls, live sink calls, public-web search, and paid enrichment.

Validation:

- Unit tests for preview redaction/no-write behavior.
- Unit tests for write/dedupe behavior.
- CLI JSON test.
- Runtime bounded intake over the configured scanner corpus.
- Runtime redaction check against private path and filename patterns.
- `ruff`, `scripts/check_plan_drift.py`, and `git diff --check`.

## Completion Gate

Plan 0100 is complete when Milestone 1 is implemented, tested, run against a
bounded scanner-library sample, and pushed.

The next plan should replay deterministic recognition against the negative
corpus and report false positives before any broad autodetection threshold
change is reconsidered.

## Stop Conditions

- If the source cannot be operator-declared non-card, use a candidate label and
  do not use it for threshold promotion.
- If any workflow would OCR, crop, enrich, route, write contacts, read back
  sinks, search the public web, or call paid providers, fail closed.
- If a runtime artifact path resolves inside the git repo, fail closed.
- If private source paths or original filenames appear in a returned payload or
  runtime manifest, fail closed.

## Execution Update | 2026-06-27 | Milestone 1

Milestone 1 is implemented. Plan 0100 is complete.

Implemented:

- Added a negative-control corpus intake builder.
- Added `BusinessCardService.negative_control_intake`.
- Added CLI command `negative-control-intake` with `--source`, `--label`,
  `--category`, `--include-glob`, `--limit`, `--no-write`, and `--json`.
- Stored negative-control blobs and manifests under
  `~/.local/share/business-card-watchdog/negative_control_corpus/`.
- Appended unique negative-control rows to
  `negative_control_corpus/index.jsonl`.
- Preserved content hash, media kind, suffix, size, operator-declared label,
  category, and intake run identity without source paths or filenames.
- Added tests for preview/no-write redaction, runtime write/dedupe/limit, and
  CLI JSON.

Runtime proof:

- Ran `negative-control-intake --json` over a bounded scanner-library sample of
  five named non-card PDF candidates selected from explicit non-card filename
  cues.
- The intake wrote five runtime negative-control blobs and a runtime manifest.
- The intake reported five entries, five PDF documents, five newly stored
  negative controls, zero OCR attempts, zero PDF rasterization, zero crops,
  zero writes, and zero network calls.
- A redaction check found no original scanner paths or source filenames in the
  runtime manifest or negative-control index.
- A follow-up `positive-corpus-exit-gate --no-write --json` reported five
  negative controls. Broad autodetection remained paused because 14
  known-positive false negatives and 47 training candidates still need
  deterministic tests/rule work.

Validation:

- `.venv/bin/python -m pytest tests/test_negative_control_corpus.py tests/test_positive_corpus_exit_gate.py tests/test_known_card_corpus.py -q`
  passed with 10 tests.
- `.venv/bin/python -m ruff check src/business_card_watchdog/negative_control_corpus.py src/business_card_watchdog/service.py src/business_card_watchdog/cli.py tests/test_negative_control_corpus.py`
  passed.
- `.venv/bin/python scripts/check_plan_drift.py` passed.
- `git diff --check` passed.

Next boundary:

- Broad autodetection remains paused.
- Next negative-control work should replay deterministic recognition against
  the negative corpus and report false positives before threshold changes are
  reconsidered.

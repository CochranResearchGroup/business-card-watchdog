# Plan 0101 | Negative-Control Recognition Replay

State: COMPLETE
Date: 2026-06-27

Parent: Plan 0060 Milestone 9

Depends on: Plan 0100

## Purpose

Replay deterministic business-card recognition against the negative-control
corpus created by Plan 0100. This turns non-card scanner PDFs/images into
false-positive evidence before any broad autodetection or recognition threshold
change is reconsidered.

Positive-control training is only useful if every improvement is checked
against non-card documents. This plan creates that replay surface while keeping
broad autodetection paused.

## Scope

- Add a `negative-control-recognition-replay` service/CLI surface.
- Read `~/.local/share/business-card-watchdog/negative_control_corpus/index.jsonl`.
- Classify negative-control images and materialized PDF pages through the
  existing deterministic preclassifier.
- Record false-positive cases where a known non-card page/image is classified
  as `business_card_high_confidence`.
- Group results by category, media kind, classifier state, and candidate
  tuning cause.
- Write redacted runtime-only replay reports under
  `negative_control_corpus/recognition_replays/`.
- Feed latest negative replay summary into the positive-corpus exit gate.

## Non-Goals

- No broad watched-folder autodetection over unknown documents.
- No OCR, crop, contact extraction, enrichment, routing, sink write, readback,
  public-web search, or paid provider call.
- No threshold changes.
- No committing private negative-control media, rendered pages, OCR text,
  crops, contact data, source paths, or filenames.
- No using App Intelligence as control authority.

## Milestone 1 | Negative Recognition Replay

Objective:

Measure deterministic false positives on the negative-control corpus.

Acceptance criteria:

- The replay command supports `--no-write` and `--json`.
- Missing or empty negative-control corpus blocks with a clear reason.
- Runtime replay materializes PDF pages only under user-scoped runtime storage.
- Returned payloads and stored reports redact source paths and filenames.
- False positives include entry ID, SHA prefix, category, media kind, page
  number, decision, score, reasons, and candidate tuning reason.
- Summary counts include sources, images, PDFs, pages replayed, classifier
  states, false positives, and errors.
- The positive-corpus exit gate includes latest negative replay evidence and
  blocks broad resume when false positives remain or when no negative replay
  exists.
- Safety counters remain zero for OCR, crops, writes, network calls, live sink
  calls, public-web search, and paid enrichment.

Validation:

- Unit tests for false-positive and non-card replay summaries.
- Unit tests for preview/no-write behavior.
- CLI JSON test.
- Exit-gate regression test with negative replay evidence.
- Runtime replay over the current negative-control corpus.
- Runtime redaction check against private path and filename patterns.
- `ruff`, `scripts/check_plan_drift.py`, and `git diff --check`.

## Completion Gate

Plan 0101 is complete when Milestone 1 is implemented, tested, run against the
current negative-control corpus, reflected in the exit gate, and pushed.

## Stop Conditions

- If negative-control media is missing or unreviewed, do not use it to permit
  threshold promotion.
- If false positives are found, broad autodetection must remain paused until
  targeted tests/rules resolve or explicitly classify them as expected
  ambiguity.
- If any workflow would OCR, crop, enrich, route, write contacts, read back
  sinks, search the public web, or call paid providers, fail closed.
- If a runtime artifact path resolves inside the git repo, fail closed.
- If private source paths or original filenames appear in a returned payload or
  runtime report, fail closed.

## Execution Update | 2026-06-27 | Milestone 1

Milestone 1 is implemented. Plan 0101 is complete.

Implemented:

- Added a negative-control recognition replay builder.
- Added `BusinessCardService.negative_corpus_recognition_replay`.
- Added CLI command `negative-control-recognition-replay` with `--no-write`,
  `--json`, `--max-pages-per-pdf`, and `--pdf-dpi`.
- Added optional bounded PDF materialization arguments to
  `materialize_document_pages` without changing default behavior.
- Recorded false-positive cases where known non-card pages/images are promoted
  as `business_card_high_confidence`.
- Added category and classifier-state summaries.
- Fed latest negative replay evidence into the positive-corpus exit gate.
- Added tests for false-positive reporting, preview/no-write behavior, CLI
  JSON, missing negative replay gate blocking, and passing negative replay gate
  readiness.

Runtime proof:

- Ran `negative-control-recognition-replay --max-pages-per-pdf 1 --pdf-dpi 100
  --json` over the current negative-control corpus.
- Replayed five negative-control PDF sources and five first-page PDF images.
- The deterministic recognizer reported zero business-card high-confidence
  pages, zero indeterminate pages, five high-confidence non-card pages, and
  zero false positives.
- The replay wrote a runtime report under
  `~/.local/share/business-card-watchdog/negative_control_corpus/recognition_replays/`.
- Runtime safety counters remained zero for OCR, crops, writes, and network
  calls; no live sink calls, public-web search, paid enrichment, live route
  selection, sink payload writes, readback, or contact writes occurred.
- A redaction check found no original scanner paths or source filenames in the
  runtime negative replay report or negative-control index.
- A follow-up `positive-corpus-exit-gate --no-write --json` reported five
  negative controls, negative replay state `negative_controls_passed`, and zero
  negative false positives. Broad autodetection remained paused because 14
  known-positive false negatives and 47 training candidates still need
  deterministic tests/rule work.

Validation:

- `.venv/bin/python -m pytest tests/test_negative_corpus_recognition.py tests/test_positive_corpus_exit_gate.py tests/test_negative_control_corpus.py tests/test_positive_corpus_recognition.py tests/test_positive_corpus_exit_gate.py tests/test_preclassifier.py -q`
  passed with 28 tests.
- `.venv/bin/python -m ruff check src/business_card_watchdog/negative_corpus_recognition.py src/business_card_watchdog/document_intake.py src/business_card_watchdog/positive_corpus_exit_gate.py src/business_card_watchdog/service.py src/business_card_watchdog/cli.py tests/test_negative_corpus_recognition.py tests/test_positive_corpus_exit_gate.py`
  passed.
- `.venv/bin/python scripts/check_plan_drift.py` passed.
- `git diff --check` passed.

Next boundary:

- Broad autodetection remains paused.
- Next work should return to Plan 0099 Milestone 1 positive-control label
  normalization and then use positive/negative replay together for tuning.

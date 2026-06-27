# Plan 0098 | Positive Corpus Training, Cropping, And Side Matching

State: IN_PROGRESS
Date: 2026-06-26

Parent: Plan 0060 Milestone 9

## Purpose

Use the richer operator-confirmed positive-control corpus to improve business
card recognition training, known-card crop/OCR quality, and front/back matching
without reopening broad unattended autodetection.

Plan 0097 created the user-scoped positive-control corpus and filed the first
confirmed real business-card sources. This plan defines how those positives are
turned into deterministic training/evaluation evidence and how App
Intelligence review is used only for bounded ambiguity.

## Non-Goals

- No broad watched-folder autodetection over unknown documents.
- No live Google Contacts, Odoo, Odollo, Apollo, People Data Labs, public-web,
  or paid-enrichment writes.
- No committing private source images, PDFs, rendered pages, OCR dumps, crops,
  or contact data.
- No treating App Intelligence output as direct control authority.
- No weakening the Plan 0095 gate for sources that have not been explicitly
  operator-declared as known business cards.

## Milestone 1 | Corpus Evaluation Manifest

Objective:

Create a deterministic, redacted evaluation manifest from the positive-control
corpus.

Scope:

- Read the user-scoped positive-control corpus index.
- Produce a redacted evaluation manifest grouped by source media kind:
  single-card images, multi-card images, scanner PDFs, and likely front/back
  sequences.
- Track content hashes, media kind, size, page count when available, and
  operator-declared label without exposing private filenames or paths.
- Preserve a stable replay order for repeatable training and regression tests.

Acceptance criteria:

- The manifest lists every retained positive-control corpus entry.
- Private paths and original filenames are redacted.
- The manifest is runtime state only under
  `~/.local/share/business-card-watchdog/`.
- No OCR, crop, rasterization, enrichment, routing, or sink work occurs.

Validation:

- Synthetic corpus manifest tests for redaction, grouping, and stable ordering.
- Runtime manifest generation over the current positive-control corpus.

## Milestone 2 | Recognition Training Replay

Objective:

Evaluate business-card recognition against known positives without allowing the
recognizer to promote unknown documents.

Scope:

- Replay corpus entries through deterministic recognition evidence collection.
- For known positives, measure whether the current classifier would classify
  the source/page as business-card-like, indeterminate, or rejected.
- Record false-negative evidence and candidate tuning reasons.
- Keep unknown-document autodetection paused; this replay is evaluation, not a
  processing gate change.

Acceptance criteria:

- Positive controls that fail deterministic recognition are recorded as
  false-negative training cases, not silently discarded.
- Recognition summaries separate scanner PDFs, single-card images, and
  multi-card images.
- Any proposed tuning is backed by fixture or corpus evidence and a targeted
  test before changing classifier behavior.

Validation:

- Synthetic positive-control replay tests.
- One runtime replay over the current corpus with zero network and zero sink
  calls.

## Milestone 3 | Known-Card Crop/OCR Workbench Evaluation

Objective:

Turn known-card sources into reviewable crop/OCR artifacts and measure quality.

Scope:

- Use Plan 0097 known-card intake as the entry point.
- For images, run crop/OCR on operator-declared known cards even if broad
  autodetection would be uncertain.
- For PDFs, rasterize pages as known-card pages and retain page lineage.
- Emit OCR text, normalized contact draft, crop candidates, extraction quality,
  and review packets.
- Keep all contacts review-required and dry-run until an explicit selected
  apply boundary exists.

Acceptance criteria:

- Known positive images and PDF pages produce inspectable crop/OCR artifacts.
- Multi-card images produce child candidate records or bounded review evidence
  instead of a single ambiguous contact.
- Low-quality crops/OCR route to review or App Intelligence evidence, not sink
  writes.
- Dry-run closeout proves zero live/network/public-web/paid-provider activity.

Validation:

- Synthetic known-card image and PDF crop/OCR tests.
- Runtime dry-run over the current positive corpus with redacted summaries.

## Milestone 4 | Front/Back Matching Evaluation

Objective:

Improve deterministic front/back matching using scanner sequence, OCR clues,
side labels, and corpus scenarios.

Scope:

- Evaluate adjacent PDF pages as possible front/back pairs.
- Support front-first and back-first sequences.
- Support dropped blank backs.
- Use deterministic OCR clues: names, emails, phones, organizations, websites,
  social links, QR/context terms, shared domains, and conflicting identities.
- Prevent cross-card merges in multi-card or sequential unrelated-card cases.
- Mark ambiguous pair graphs for bounded App Intelligence review.

Acceptance criteria:

- Front/back pairs with coherent OCR evidence produce deterministic pair
  proposals.
- Backside-only useful fields can augment the front-side contact candidate.
- Conflicting identities produce review-required evidence.
- Multi-card images and unrelated adjacent pages do not cross-merge.

Validation:

- Synthetic graph tests plus replay-derived fixtures from the positive corpus.
- Runtime side-pair report over confirmed scanner PDFs.

## Milestone 5 | Training Review Loop

Objective:

Define the agent/App Intelligence loop for improving recognition, crop, OCR,
and side matching from corpus evidence.

Scope:

- Build a review queue of indeterminate recognition, poor crop/OCR, and
  ambiguous side-pair cases.
- Require the agent to inspect evidence and propose deterministic rule or
  fixture changes.
- Use App Intelligence only when deterministic evidence is insufficient.
- Record accepted changes as tests before implementation.

Acceptance criteria:

- Every review item has source lineage, redacted corpus identity, failure mode,
  proposed deterministic improvement, and stop conditions.
- App Intelligence requests are bounded and evidence-only.
- No reviewed item can route, enrich, write, read back, or select live targets.

Validation:

- Agent-loop tests for recognition, crop/OCR, and side-pair review queues.
- Runtime review report over the current positive corpus.

## Milestone 6 | Exit Gate For Resuming Autodetection

Objective:

Define when broad business-card autodetection can be reconsidered.

Scope:

- Summarize positive-control coverage across orientations, PDF sequences,
  front/back order, dropped backs, and multi-card images.
- Measure false-negative rate on known positives.
- Require a separate negative-control set before changing broad promotion
  thresholds.
- Keep broad autodetection paused until both positive and negative evidence are
  sufficient.

Acceptance criteria:

- Known positives have reproducible crop/OCR and side-pair evidence.
- Recognition tuning has targeted tests and no regression against existing
  negative controls.
- The next plan explicitly states whether autodetection remains paused or can
  resume under a bounded gate.

Validation:

- Full targeted suite for corpus manifest, recognition replay, crop/OCR,
  side-pair matching, review loop, and existing classifier gates.
- `ruff`, `scripts/check_plan_drift.py`, and `git diff --check`.

## Stop Conditions

- If a source is not operator-declared as a business card, do not use it as a
  positive control.
- If a proposed rule improves positives by increasing known false positives,
  stop and add negative-control coverage first.
- If any workflow would write contacts, call enrichment providers, search the
  public web, or expose private card artifacts in git, fail closed.

## Execution Update | 2026-06-26 | Milestone 1

Milestone 1 is implemented.

Implemented:

- Added a redacted positive-corpus evaluation manifest builder.
- Added `BusinessCardService.positive_corpus_evaluation_manifest`.
- Added CLI command `positive-corpus-evaluation-manifest` with preview and JSON
  modes.
- Grouped retained positive controls into stable replay buckets:
  `single_card_image_candidate`, `multi_card_image_candidate`,
  `scanner_pdf_document`, `likely_front_back_sequence`, and
  `unsupported_or_unknown_media`.
- Preserved content hashes, media kind, suffix, size, operator-declared label,
  PDF page counts, likely front/back sequence hints, and image dimension/aspect
  metadata without exposing original private source paths or filenames.
- Kept the manifest as runtime-only state with zero OCR, zero PDF
  rasterization, zero crops, zero contact routing, zero sink writes, zero
  network calls, zero public-web search, and zero paid enrichment.

Runtime proof:

- Generated a runtime manifest over the current positive-control corpus.
- The manifest contained five entries: two multi-card image candidates and
  three likely front/back PDF sequences.
- The PDF entries recorded page counts of 2, 4, and 8 pages.
- The two image entries recorded wide aspect-ratio metadata and grouped as
  multi-card image candidates.
- A redaction check found no original scanner/phone paths or source filenames
  in the runtime evaluation manifest.

Validation:

- `.venv/bin/python -m pytest tests/test_positive_corpus_evaluation.py tests/test_known_card_corpus.py tests/test_positive_controls.py tests/test_classifier_training.py -q`
  passed with 14 tests.
- `.venv/bin/python -m ruff check src/business_card_watchdog/positive_corpus_evaluation.py src/business_card_watchdog/known_card_corpus.py src/business_card_watchdog/service.py src/business_card_watchdog/cli.py tests/test_positive_corpus_evaluation.py tests/test_known_card_corpus.py tests/test_positive_controls.py tests/test_classifier_training.py`
  passed.
- `.venv/bin/python scripts/check_plan_drift.py` passed.
- `git diff --check` passed.

Remaining work:

- Milestone 2 recognition training replay over known positives.
- Milestone 3 known-card crop/OCR workbench evaluation.
- Milestone 4 front/back matching evaluation.
- Milestone 5 training review loop.
- Milestone 6 exit gate before broad autodetection can resume.

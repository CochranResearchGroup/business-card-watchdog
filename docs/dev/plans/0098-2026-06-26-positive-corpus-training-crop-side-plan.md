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

## Execution Update | 2026-06-26 | Milestone 2

Milestone 2 is implemented.

Implemented:

- Added a positive-corpus recognition replay builder.
- Added `BusinessCardService.positive_corpus_recognition_replay`.
- Added CLI command `positive-corpus-recognition-replay` with preview and JSON
  modes.
- Replayed operator-declared known positives through deterministic recognition
  evidence collection without promoting broad autodetection.
- Ran the current preclassifier against retained positive image blobs and
  runtime-materialized PDF pages.
- Recorded per-source and per-page classifier decisions, classifier training
  states, analyzer summaries, false-negative cases, and candidate tuning
  reasons.
- Kept false negatives as explicit training evidence rather than discarding
  them.
- Preserved zero OCR, zero crops, zero contact routing, zero sink writes, zero
  network calls, zero live sink calls, zero public-web search, and zero paid
  enrichment.

Runtime proof:

- Ran `positive-corpus-recognition-replay` over the current positive-control
  corpus.
- Replayed five known-positive sources: two multi-card image candidates and
  three likely front/back PDF sequences.
- Replayed 16 total pages/images, including 14 PDF pages materialized under
  user-scoped runtime state.
- Current deterministic recognition produced 2
  `business_card_high_confidence` pages, 12
  `indeterminate_needs_app_intelligence` pages, and 2
  `not_business_card_high_confidence` image cases.
- Recorded 14 known-positive false-negative cases:
  12 indeterminate pages needing feature/fixture review and 2 multi-card images
  rejected as document-like.
- A redaction check found no original scanner/phone paths or source filenames
  in the runtime recognition replay report.

Validation:

- `.venv/bin/python -m pytest tests/test_positive_corpus_recognition.py tests/test_positive_corpus_evaluation.py tests/test_known_card_corpus.py tests/test_positive_controls.py tests/test_classifier_training.py -q`
  passed with 17 tests.
- `.venv/bin/python -m ruff check src/business_card_watchdog/positive_corpus_recognition.py src/business_card_watchdog/positive_corpus_evaluation.py src/business_card_watchdog/known_card_corpus.py src/business_card_watchdog/service.py src/business_card_watchdog/cli.py tests/test_positive_corpus_recognition.py tests/test_positive_corpus_evaluation.py tests/test_known_card_corpus.py tests/test_positive_controls.py tests/test_classifier_training.py`
  passed.
- `.venv/bin/python scripts/check_plan_drift.py` passed.
- `git diff --check` passed.

Remaining work:

- Milestone 3 known-card crop/OCR workbench evaluation.
- Milestone 4 front/back matching evaluation.
- Milestone 5 training review loop.
- Milestone 6 exit gate before broad autodetection can resume.

## Execution Update | 2026-06-27 | Milestone 3

Milestone 3 is implemented.

Implemented:

- Added a positive-corpus crop/OCR workbench evaluation builder.
- Added `BusinessCardService.positive_corpus_workbench_evaluation`.
- Added CLI command `positive-corpus-workbench-evaluation` with preview,
  worker-count, and JSON modes.
- Added a bounded `known_positive` orchestrator mode that admits
  operator-declared positive corpus sources to crop/OCR workbench processing
  even when broad deterministic recognition would reject or mark them
  indeterminate.
- Kept the known-positive classifier bypass explicit in
  `scanner_page_classifier_gate.json` evidence and did not reopen broad
  unknown-document autodetection.
- Forced known-positive workbench jobs to stop at review-required crop/OCR
  evidence before duplicate lookup, routing, enrichment, sink payload planning,
  write, or readback.
- Copied corpus blobs into redacted runtime source bundles before processing.
- Retained PDF page lineage and summarized page number, rasterization mode,
  classifier state, crop candidates, OCR text artifacts, contact drafts,
  extraction quality, review packets, and App Intelligence review request
  counts.
- Added a known-positive-only OCR text fallback when the local adapter writes a
  contact spec but no raw `ocr.txt`; the workbench report marks those OCR text
  artifacts as `derived_from_contact_spec` so they remain review evidence, not
  raw OCR proof.

Runtime proof:

- Ran `positive-corpus-workbench-evaluation --workers 1 --json` over the
  current positive-control corpus.
- Processed five known-positive sources: two images and three PDF documents.
- Produced 16 review-required jobs: two image jobs and 14 PDF page jobs.
- Materialized 14 PDF pages with page lineage.
- Produced 16 contact drafts, 16 review packets, 16 OCR text artifacts, and one
  deterministic candidate crop.
- Recorded 14 known-positive classifier-bypass admissions from pages/images
  that current recognition would not admit through the broad gate.
- Recorded 17 bounded App Intelligence review requests from crop/OCR quality
  gates.
- The local `business-card-to-contact` adapter did not emit raw OCR text, so
  the 16 OCR text artifacts in this runtime proof were explicitly marked
  `derived_from_contact_spec`.
- Runtime safety counters remained zero for writes and network calls; no live
  sink calls, public-web search, paid enrichment, live route selection, or sink
  payload writes occurred.
- A redaction check found no original scanner/phone paths or source filenames
  in the runtime workbench report.

Validation:

- `.venv/bin/python -m pytest tests/test_positive_corpus_workbench.py tests/test_positive_corpus_recognition.py tests/test_positive_corpus_evaluation.py tests/test_known_card_corpus.py tests/test_dry_run_pipeline.py -q`
  passed with 18 tests.

Remaining work:

- Milestone 4 front/back matching evaluation.
- Milestone 5 training review loop.
- Milestone 6 exit gate before broad autodetection can resume.

## Execution Update | 2026-06-27 | Milestone 4

Milestone 4 is implemented.

Implemented:

- Added a positive-corpus front/back side-pair evaluation builder.
- Added `BusinessCardService.positive_corpus_side_pair_evaluation`.
- Added CLI command `positive-corpus-side-pair-evaluation` with preview and
  JSON modes.
- Reused the latest known-positive workbench run as the side-pair evidence
  source.
- Rebuilt scanner-page side candidates from redacted page lineage and OCR text
  artifacts.
- Evaluated adjacent and near-adjacent PDF pages with the existing deterministic
  side-pair proposal and side-pair graph rules.
- Summarized deterministic pair proposals, blocked pair proposals, review
  required edges, blank-back candidates, merge evaluations, backside-augmented
  fields, conflicting merge evidence, and bounded App Intelligence review
  requests.
- Kept all pair and merge outputs as evidence only: no routing, enrichment,
  sink payload planning, writes, readback, public-web search, or paid provider
  calls.

Synthetic validation coverage:

- Front-first scanner sequence produces a deterministic pair proposal.
- Back-first scanner sequence produces a deterministic pair proposal with the
  correct front/back job assignment.
- Blank adjacent backs are summarized as blank-back candidates instead of being
  merged.
- Backside-only useful fields augment merged contact evidence while remaining
  review-required.
- Conflicting domains create blocked pair proposals and App Intelligence review
  requests.
- Private source paths and filenames remain redacted from the side-pair report.

Runtime proof:

- Ran `positive-corpus-side-pair-evaluation --json` over the current real
  positive-control workbench evidence.
- Evaluated three scanner PDFs and 14 scanner-page candidates.
- Current runtime side classification produced 14 front candidates, zero back
  candidates, zero blank candidates, and zero unknown candidates.
- Because the local `business-card-to-contact` skill did not provide raw
  backside OCR in the preceding workbench and the fallback OCR text was derived
  from contact specs, the real corpus produced zero deterministic pair
  proposals and zero merge evaluations.
- The evaluator recorded 17 review-required graph edges and 17 bounded App
  Intelligence side-pair review requests instead of cross-merging pages.
- Runtime safety counters remained zero for writes and network calls; no live
  sink calls, public-web search, paid enrichment, live route selection, sink
  payload writes, or contact writes occurred.
- A redaction check found no original scanner/phone paths or source filenames
  in the runtime side-pair evaluation report.

Validation:

- `.venv/bin/python -m pytest tests/test_positive_corpus_side_pair.py tests/test_card_sides.py tests/test_positive_corpus_workbench.py tests/test_positive_corpus_recognition.py tests/test_positive_corpus_evaluation.py tests/test_known_card_corpus.py -q`
  passed with 33 tests.

Remaining work:

- Milestone 5 training review loop.
- Milestone 6 exit gate before broad autodetection can resume.

## Execution Update | 2026-06-27 | Milestone 5

Milestone 5 is implemented.

Implemented:

- Added a positive-corpus training review loop builder.
- Added `BusinessCardService.positive_corpus_training_review_loop`.
- Added CLI command `positive-corpus-training-review-loop` with preview and
  JSON modes.
- Built a unified agent review queue from the positive-corpus recognition
  replay, crop/OCR workbench evaluation, and side-pair evaluation reports.
- Added review items for recognition false negatives, crop/OCR quality
  blockers, raw OCR gaps, and ambiguous/conflicting side-pair evidence.
- Added one bounded App Intelligence evidence request per review item, with
  forbidden actions for routing, sink writes, readback, enrichment, public-web
  search, paid provider calls, and live target selection.
- Added one deterministic training candidate per review item, each requiring a
  targeted test before implementation.
- Added an agent iteration contract: inspect evidence, propose deterministic
  fixture/rule changes, request App Intelligence only when deterministic
  evidence is insufficient, and implement only after tests.
- Kept all review-loop output as runtime-only positive-corpus evidence.

Runtime proof:

- Ran `positive-corpus-training-review-loop --json` over the current real
  positive-control corpus reports.
- Produced 47 review items: 14 recognition items, 16 crop/OCR items, and 17
  side-pair items.
- Produced 47 bounded App Intelligence evidence requests and 47 deterministic
  training candidates.
- Preserved zero route-enabled items, zero sink-write-enabled items, and zero
  public-web-enabled items.
- Runtime safety counters remained zero for writes and network calls; no live
  sink calls, public-web search, paid enrichment, live route selection, sink
  payload writes, readback, or contact writes occurred.
- A redaction check found no original scanner/phone paths or source filenames
  in the runtime training review-loop report.

Validation:

- `.venv/bin/python -m pytest tests/test_positive_corpus_review_loop.py tests/test_positive_corpus_side_pair.py tests/test_positive_corpus_workbench.py tests/test_positive_corpus_recognition.py tests/test_positive_corpus_evaluation.py tests/test_known_card_corpus.py tests/test_card_sides.py tests/test_cli_surfaces.py::test_cli_runs_agent_review_loop_plans_qr_side_followup -q`
  passed with 37 tests.

Remaining work:

- Milestone 6 exit gate before broad autodetection can resume.

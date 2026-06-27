# Plan 0099 | Positive-Control Recognition, Crop, And Side Training

State: IN_PROGRESS
Date: 2026-06-27

Parent: Plan 0060 Milestone 9

Depends on: Plan 0098 Milestone 6 exit gate

## Purpose

Use the richer operator-confirmed business-card positive-control set to train
and harden three separable product surfaces:

- business-card recognition for known positives and eventual bounded
  autodetection reconsideration;
- crop/OCR extraction for known business-card images and scanner PDF pages;
- front/back matching for double-sided cards where page order can be front-back
  or back-front, and scanners may drop blank backs.

This plan keeps broad unattended autodetection paused unless a later exit gate
proves both positive and negative evidence are sufficient. The immediate value
is a higher-powered known-card processor that can convert confirmed card
images/PDFs into reviewable contact drafts while storing evidence for future
classifier training.

## Non-Goals

- No broad watched-folder autodetection over unknown documents.
- No live Google Contacts, Odoo, Odollo, Apollo, People Data Labs, public-web,
  or paid-enrichment writes.
- No committing private source images, PDFs, rendered pages, crops, OCR dumps,
  extracted contacts, or private filenames/paths.
- No treating App Intelligence output as host control authority.
- No promotion threshold changes without negative-control coverage.
- No automatic front/back merge when deterministic identity evidence conflicts.

## Milestone 1 | Corpus Label Normalization

Objective:

Turn the richer positive-control set into a stable, redacted, scenario-aware
training inventory.

Scope:

- Read the user-scoped positive-control corpus index.
- Normalize labels for source kind, page kind, capture mode, card count,
  orientation, front/back sequence, and blank/dropped-back expectations.
- Preserve stable replay IDs and content hashes without private paths or
  original filenames.
- Add a missing-label report for cases that need operator or agent review.

Acceptance criteria:

- Every current positive-control source has a redacted training inventory row.
- Scanner PDFs expose page-count and sequence metadata.
- Multi-card images and single-card images are distinguishable.
- Front/back expectations are explicit when known and `unknown` when not.
- Missing labels do not block known-card crop/OCR; they only block training
  promotion.

Validation:

- Synthetic corpus label tests for images, PDFs, orientation variants,
  front/back order variants, and dropped blank backs.
- Runtime inventory generation over the current positive-control corpus with a
  redaction check.

## Milestone 2 | Synthetic Scenario Expansion

Objective:

Generate deterministic positive-control scenarios from existing confirmed card
sources without adding private artifacts to git.

Scope:

- Build runtime-only scenario manifests for page-order swaps, rotations,
  omitted pages, duplicated pages, front-only scans, back-only scans,
  front-back and back-front PDFs, and mixed multi-card images.
- Keep derived scenario artifacts under user-scoped runtime/cache storage.
- Record derivation lineage from redacted source IDs and content hashes.
- Mark generated scenarios as positive-control training evidence, not operator
  source files.

Acceptance criteria:

- Scenario generation is reproducible from the corpus inventory.
- Generated cases cover orientation, sequence, and missing-back variants.
- No generated image/PDF artifact is committed to git.
- The scenario manifest can be replayed by recognition, crop/OCR, and side-pair
  evaluators.

Validation:

- Fixture tests for scenario manifest generation and lineage redaction.
- Runtime dry-run scenario generation over a bounded positive-control subset.

## Milestone 3 | Recognition Training Replay And Tuning

Objective:

Improve deterministic recognition against known positives while preserving the
paused broad-autodetection boundary.

Scope:

- Replay real and generated positive-control scenarios through deterministic
  recognition evidence collection.
- Track false negatives by scenario kind, orientation, PDF page role,
  image/card count, aspect ratio, OCR clue availability, and capture mode.
- Propose rule changes only when backed by tests and no known negative-control
  regression.
- Route indeterminate recognition cases to App Intelligence evidence review
  when deterministic features are insufficient.

Acceptance criteria:

- Known positive false negatives are grouped by actionable cause.
- Recognition tuning is implemented behind explicit tests, not ad hoc threshold
  changes.
- App Intelligence requests include bounded questions and redacted evidence.
- Unknown-document autodetection remains paused.

Validation:

- Positive-control replay tests for front, back, multi-card, rotated, and PDF
  page cases.
- Existing negative-control/classifier gate tests remain passing.
- Runtime replay report with false-negative counts before and after each
  accepted tuning change.

## Milestone 4 | Known-Card Crop Segmentation Workbench

Objective:

Make crop extraction reliable for known-card images and scanner PDF pages,
including multi-card photos.

Scope:

- Run crop candidate generation on operator-declared known positives.
- Separate single-card image, multi-card image, and PDF-page crop strategies.
- Preserve crop candidates with quality metrics: aspect ratio, contour
  confidence, edge completeness, skew/rotation estimate, size, and OCR
  readiness.
- For multi-card images, emit child crop candidates instead of one ambiguous
  contact.
- Route low-confidence crop choices to review/App Intelligence evidence.

Acceptance criteria:

- Known single-card images produce one primary crop candidate or a review item.
- Known multi-card images produce one child candidate per plausible card region
  or a bounded review item.
- PDF pages preserve source page lineage on every crop candidate.
- Crop artifacts stay in runtime/cache storage and are never committed.

Validation:

- Synthetic crop tests for one-card, multi-card, rotated, skewed, and low-edge
  inputs.
- Runtime workbench report over the richer positive-control set.

## Milestone 5 | OCR And Contact Draft Evidence

Objective:

Convert known-card crop candidates into reviewable contact drafts with clear
OCR provenance and quality gates.

Scope:

- Run OCR over accepted crop candidates and preserve raw OCR text as runtime
  evidence when the adapter provides it.
- Normalize names, organizations, titles, emails, phones, websites, addresses,
  and social handles into contact draft fields.
- Score OCR completeness and field confidence.
- Preserve backside-only fields as candidate augmentation evidence, not direct
  sink updates.
- Keep every draft review-required and dry-run.

Acceptance criteria:

- Every processed crop has OCR provenance: adapter raw text, fallback text, or
  explicit missing-OCR reason.
- Contact drafts separate extracted fields from normalized fields and review
  suggestions.
- Low-confidence or conflicting fields create review items.
- No enrichment, routing, sink payload, write, readback, or public-web action
  occurs.

Validation:

- OCR/contact draft fixture tests for front-only, back-only, front/back, and
  multi-card child crops.
- Runtime known-card OCR report with redacted summaries and zero live counters.

## Milestone 6 | Front/Back Matching And Merge Evidence

Objective:

Match card backsides to fronts using scanner sequence plus deterministic OCR
and layout clues.

Scope:

- Evaluate adjacent scanner pages as possible pairs in both front-back and
  back-front order.
- Support scanners that drop blank backs by allowing front-only candidates.
- Use deterministic clues: shared domains, emails, phones, names,
  organizations, websites, social handles, QR terms, address fragments,
  backside cue words, and conflicting identity evidence.
- Prevent cross-card merges in multi-card and unrelated-adjacent cases.
- Emit side-pair graph edges as `pair_proposed`, `review_required`,
  `front_only`, `blank_or_dropped_back`, or `blocked_conflict`.

Acceptance criteria:

- Coherent front/back evidence produces deterministic pair proposals.
- Backside-only fields augment the contact draft with provenance.
- Conflicting identities block automatic merge and create review evidence.
- Ambiguous pair graphs route to bounded App Intelligence review.

Validation:

- Pair-graph tests for front-back, back-front, dropped blank back,
  unrelated-adjacent, repeated-card, and multi-card scenarios.
- Runtime side-pair evaluation over scanner PDF positive controls.

## Milestone 7 | Agent Training Review Loop

Objective:

Use Codex/App Intelligence review as an evidence loop that improves
deterministic rules and fixtures without giving agents control of workflow
state.

Scope:

- Build a queue from recognition false negatives, crop failures, OCR quality
  gaps, and ambiguous side-pair graphs.
- Require every agent iteration to produce one of:
  deterministic rule proposal, fixture/test proposal, App Intelligence evidence
  request, or explicit stop condition.
- Accept implementation only after a targeted test captures the case.
- Keep the host orchestrator authoritative for state transitions, ledgers,
  approvals, replay, and stop rules.

Acceptance criteria:

- Review items are grouped by failure mode and scenario kind.
- Agent/App Intelligence output is recorded as evidence, not applied as direct
  control.
- Accepted training improvements have tests and before/after replay metrics.
- No live sink, route, enrichment, or public-web action is reachable.

Validation:

- Review-loop fixture tests for each failure family.
- Runtime review-loop report over current positive-control training evidence.

## Milestone 8 | Bounded Resume Readiness Gate

Objective:

Decide whether the product remains in known-card-only mode or can propose a
future bounded autodetection pilot.

Scope:

- Compose reports from Milestones 1-7 and the existing Plan 0098 exit gate.
- Require both positive-control improvements and negative-control regression
  coverage before any broad promotion threshold change.
- Explicitly state the next operating mode: known-card-only, expanded training,
  negative-control buildout, or bounded autodetection pilot.

Acceptance criteria:

- Known positives have reproducible recognition, crop/OCR, and side-pair
  evidence.
- Recognition false negatives and crop/OCR/side-pair review items are either
  resolved, accepted as expected ambiguity, or routed to the next training plan.
- Negative-control coverage exists before broad autodetection is reconsidered.
- The gate writes a redacted runtime report and updates the roadmap boundary.

Validation:

- Full targeted positive-control suite.
- Existing classifier/preclassifier negative-control suite.
- `ruff`, `scripts/check_plan_drift.py`, and `git diff --check`.

## Stop Conditions

- If a source is not operator-declared as a business card, do not use it as a
  positive control.
- If a generated scenario would expose private image/PDF data in git, stop.
- If tuning improves known positives but increases known false positives, stop
  and expand negative controls first.
- If OCR/contact data would route, enrich, write, read back, or select a live
  target, fail closed.
- If App Intelligence output lacks enough evidence for a deterministic rule or
  test, keep the case review-required.

## Execution Update | 2026-06-27 | Milestone 1

Completed:

- Added a positive-control label inventory builder and
  `positive-control-label-inventory` CLI surface.
- Normalized redacted source labels for images and PDFs, including media kind,
  source kind, capture mode, card-count expectation, orientation, page count,
  front/back sequence expectation, blank/dropped-back expectation, and
  per-page side labels.
- Added missing-label reporting that blocks training promotion only; known-card
  crop/OCR remains allowed when the corpus index is present.
- Preserved stable replay IDs and content hashes without original filenames or
  private source paths.

Runtime evidence:

- `positive-control-label-inventory --json` over the current user-scoped
  positive-control corpus produced state `training_inventory_ready`.
- Current corpus inventory count: 5 positive-control sources.
- Runtime group counts: 2 `multi_card_image_candidate` sources and 3
  `scanner_pdf_front_back_sequence_candidate` sources.
- Missing-label rows: 5. Training promotion remains blocked, while known-card
  crop/OCR remains allowed.
- Runtime inventory was written under
  `~/.local/share/business-card-watchdog/positive_control_corpus/label_inventories/`.
- Redaction scan found no original scanner path or source filename tokens in
  `/tmp/bcw-positive-control-label-inventory.json`.

Validation:

- `.venv/bin/python -m pytest tests/test_positive_control_labels.py tests/test_positive_corpus_evaluation.py tests/test_known_card_corpus.py tests/test_positive_corpus_recognition.py tests/test_positive_corpus_exit_gate.py -q`
  passed with 17 tests.
- `.venv/bin/python -m ruff check src/business_card_watchdog/positive_control_labels.py src/business_card_watchdog/service.py src/business_card_watchdog/cli.py tests/test_positive_control_labels.py`
  passed.
- `.venv/bin/python scripts/check_plan_drift.py` passed.
- `git diff --check` passed.

Remaining:

- Milestones 2-8 remain open. Next bounded goal is Milestone 2 synthetic
  scenario expansion from the redacted label inventory.

## Execution Update | 2026-06-27 | Milestone 2

Completed:

- Added a positive-control scenario manifest builder and
  `positive-control-scenario-manifest` CLI surface.
- Derived replayable scenario plans from the redacted positive-control label
  inventory without rendering derived private image or PDF artifacts.
- Covered page-order swaps, rotations, omitted pages, duplicated pages,
  front-only scans, back-only scans, front/back and back/front PDFs, and mixed
  multi-card images.
- Preserved redacted lineage from source entry IDs and content hashes, with
  replay targets for recognition, crop/OCR, and side-pair evaluators.

Runtime evidence:

- `positive-control-scenario-manifest --json` over the current user-scoped
  positive-control corpus produced state `ready_for_scenario_replay`.
- Current scenario manifest count: 25 scenario plans from 5 positive-control
  sources.
- Coverage flags were true for page-order swaps, rotations, omitted pages,
  duplicated pages, front-only scans, back-only scans, front/back PDFs, and
  mixed multi-card images.
- The manifest materialized 0 generated files and 0 derived artifacts; it is a
  plan-only runtime manifest.
- Runtime manifest was written under
  `~/.local/share/business-card-watchdog/positive_control_corpus/scenario_manifests/`.
- Redaction scan found no original scanner path or source filename tokens in
  `/tmp/bcw-positive-control-scenario-manifest.json`.

Validation:

- `.venv/bin/python -m pytest tests/test_positive_control_scenarios.py tests/test_positive_control_labels.py tests/test_positive_corpus_evaluation.py tests/test_known_card_corpus.py tests/test_positive_corpus_recognition.py tests/test_positive_corpus_exit_gate.py -q`
  passed with 20 tests.
- `.venv/bin/python -m ruff check src/business_card_watchdog/positive_control_scenarios.py src/business_card_watchdog/positive_control_labels.py src/business_card_watchdog/service.py src/business_card_watchdog/cli.py tests/test_positive_control_scenarios.py tests/test_positive_control_labels.py`
  passed.
- `.venv/bin/python scripts/check_plan_drift.py` passed.
- `git diff --check` passed.

Remaining:

- Milestones 3-8 remain open. Next bounded goal is Milestone 3 recognition
  training replay and tuning using real positive controls plus generated
  scenario plans while preserving the broad-autodetection pause.

## Execution Update | 2026-06-27 | Milestone 3

Completed:

- Added a positive-control recognition training replay builder and
  `positive-control-recognition-training-replay` CLI surface.
- Composed the positive label inventory, generated scenario manifest, and
  baseline positive recognition replay into a scenario-aware training report.
- Grouped known-positive false negatives by scenario kind, source kind, page
  role, card-count label, orientation label, capture mode, and tuning reason.
- Added contextual positive-control tuning that demotes operator-declared
  multi-card high-confidence negative outcomes to App Intelligence review
  without changing unknown-document thresholds.
- Added bounded App Intelligence request packets with redacted evidence and
  constrained answer choices for indeterminate pages/scenarios.

Runtime evidence:

- `positive-control-recognition-training-replay --json` over the current
  user-scoped positive-control corpus produced state
  `needs_app_intelligence_or_feature_tuning`.
- Current replay counts: 5 sources, 16 real page/image cases, and 25 generated
  scenario plans.
- Before contextual tuning: 14 known-positive false negatives, including 2
  high-confidence known-positive negative outcomes.
- After contextual tuning: 14 known-positive false negatives remain, but
  high-confidence known-positive negative outcomes were reduced from 2 to 0 and
  converted to indeterminate review.
- App Intelligence request count: 24 bounded requests.
- Unknown-document threshold changed: `False`.
- Negative-control regression replay over 5 first-page PDF controls reported
  0 business-card high-confidence pages and 0 false positives.
- Redaction scan found no original scanner path or source filename tokens in
  `/tmp/bcw-positive-control-recognition-training-replay.json`.

Validation:

- `.venv/bin/python -m pytest tests/test_positive_control_recognition_training.py tests/test_positive_control_scenarios.py tests/test_positive_control_labels.py tests/test_positive_corpus_recognition.py tests/test_negative_corpus_recognition.py tests/test_positive_corpus_exit_gate.py tests/test_preclassifier.py -q`
  passed with 33 tests.
- `.venv/bin/python -m ruff check src/business_card_watchdog/positive_control_recognition_training.py src/business_card_watchdog/positive_control_scenarios.py src/business_card_watchdog/positive_control_labels.py src/business_card_watchdog/service.py src/business_card_watchdog/cli.py tests/test_positive_control_recognition_training.py tests/test_positive_control_scenarios.py tests/test_positive_control_labels.py`
  passed.
- `.venv/bin/python scripts/check_plan_drift.py` passed.
- `git diff --check` passed.

Remaining:

- Milestones 4-8 remain open. Next bounded goal is Milestone 4 known-card crop
  segmentation workbench over real positive controls and generated scenario
  plans while keeping crop artifacts in runtime/cache storage.

## Execution Update | 2026-06-27 | Milestone 4

Completed:

- Added a positive-control crop segmentation workbench and
  `positive-control-crop-workbench` CLI surface.
- Generated redacted crop-candidate evidence from operator-declared known
  positives without OCR, contact extraction, routing, enrichment, or sink
  writes.
- Separated image units and PDF-page units, preserving source entry IDs,
  content hashes, page numbers, page roles, and runtime artifact lineage.
- Added candidate quality metrics: aspect ratio, contour confidence, edge
  completeness, skew/rotation estimate, size, and OCR readiness.
- Added primary crop candidates for single/PDF-page units and child crop
  candidates for deterministic multi-card fixture cases.
- Routed low-confidence or missing deterministic crop choices to bounded
  crop/App Intelligence review requests.

Runtime evidence:

- `positive-control-crop-workbench --json` over the current user-scoped
  positive-control corpus produced state `crop_workbench_review_required`.
- Current workbench counts: 5 sources, 25 scenario plans, 16 processing units,
  2 image units, and 14 PDF page units.
- PDF page lineage was preserved for 14 materialized PDF pages.
- Crop candidate count: 14 primary candidates, all accepted for the OCR
  workbench lane.
- Current real multi-card image units produced 0 deterministic child
  candidates and were routed to 4 bounded crop-review requests rather than
  forcing ambiguous crops.
- OCR attempted: 0. Network calls: 0. Live sink calls: `False`.
- Runtime report and candidate JSON artifacts were written under
  `~/.local/share/business-card-watchdog/positive_control_corpus/crop_workbenches/`.
- Redaction scan found no original scanner path or source filename tokens in
  `/tmp/bcw-positive-control-crop-workbench.json`.

Validation:

- `.venv/bin/python -m pytest tests/test_positive_control_crop_workbench.py tests/test_positive_control_recognition_training.py tests/test_positive_control_scenarios.py tests/test_positive_control_labels.py tests/test_positive_corpus_workbench.py tests/test_positive_corpus_exit_gate.py tests/test_preclassifier.py -q`
  passed with 33 tests.
- `.venv/bin/python -m ruff check src/business_card_watchdog/positive_control_crop_workbench.py src/business_card_watchdog/positive_control_recognition_training.py src/business_card_watchdog/positive_control_scenarios.py src/business_card_watchdog/positive_control_labels.py src/business_card_watchdog/service.py src/business_card_watchdog/cli.py tests/test_positive_control_crop_workbench.py tests/test_positive_control_recognition_training.py tests/test_positive_control_scenarios.py tests/test_positive_control_labels.py`
  passed.
- `.venv/bin/python scripts/check_plan_drift.py` passed.
- `git diff --check` passed.

Remaining:

- Milestones 5-8 remain open. Next bounded goal is Milestone 5 OCR and contact
  draft evidence from accepted known-card crop candidates, with all drafts
  review-required and no enrichment, routing, sink payloads, writes, readbacks,
  or public-web actions.

## Execution Update | 2026-06-27 | Milestone 5

Completed:

- Added a positive-control OCR/contact draft evidence builder and
  `positive-control-ocr-contact-drafts` CLI surface.
- Consumed accepted known-card crop candidates from the crop workbench and
  emitted review-required contact draft evidence.
- Preserved OCR provenance for every processed candidate: adapter raw text when
  supplied to the builder, or an explicit missing-OCR reason when no OCR output
  exists.
- Added deterministic field extraction and contact normalization for
  adapter-provided OCR text in fixture coverage.
- Added review items for missing OCR and missing contact points.
- Preserved backside-only fields as augmentation evidence only; direct sink
  updates remain disallowed.

Runtime evidence:

- `positive-control-ocr-contact-drafts --json` over the current user-scoped
  positive-control corpus produced state `ocr_missing_review_required`.
- Accepted crop candidates: 14. Contact drafts: 14.
- OCR text available: 0. Missing OCR records: 14.
- Review-required drafts: 14. Review items: 28.
- Backside augmentation candidates: 0 because current page roles remain
  `front_or_back_unknown`, not confirmed backs.
- Sink payloads created: 0. Network calls: 0. Live sink calls: `False`.
- Runtime report and draft JSON artifacts were written under
  `~/.local/share/business-card-watchdog/positive_control_corpus/ocr_contact_drafts/`.
- Redaction scan found no original scanner path or source filename tokens in
  `/tmp/bcw-positive-control-ocr-contact-drafts.json`.

Validation:

- `.venv/bin/python -m pytest tests/test_positive_control_ocr_drafts.py tests/test_positive_control_crop_workbench.py tests/test_positive_control_recognition_training.py tests/test_positive_control_scenarios.py tests/test_positive_control_labels.py tests/test_positive_corpus_workbench.py tests/test_positive_corpus_exit_gate.py tests/test_contact.py -q`
  passed with 26 tests.
- `.venv/bin/python -m ruff check src/business_card_watchdog/positive_control_ocr_drafts.py src/business_card_watchdog/positive_control_crop_workbench.py src/business_card_watchdog/positive_control_recognition_training.py src/business_card_watchdog/positive_control_scenarios.py src/business_card_watchdog/positive_control_labels.py src/business_card_watchdog/service.py src/business_card_watchdog/cli.py tests/test_positive_control_ocr_drafts.py tests/test_positive_control_crop_workbench.py tests/test_positive_control_recognition_training.py tests/test_positive_control_scenarios.py tests/test_positive_control_labels.py`
  passed.
- `.venv/bin/python scripts/check_plan_drift.py` passed.
- `git diff --check` passed.

Remaining:

- Milestones 6-8 remain open. Next bounded goal is Milestone 6 front/back
  matching and merge evidence using scanner sequence plus OCR/layout clues,
  while keeping ambiguous or conflicting pair graphs review-required.

## Execution Update | 2026-06-27 | Milestone 6

Completed:

- Added a positive-control front/back side-pair evidence builder and
  `positive-control-side-pair-evidence` CLI surface.
- Evaluated adjacent scanner PDF page drafts as candidate side pairs in
  front-back and back-front order.
- Added deterministic evidence states: `pair_proposed`, `review_required`,
  `front_only`, `blank_or_dropped_back`, and `blocked_conflict`.
- Used deterministic OCR clues including shared email/phone/domain evidence,
  identity-vs-backside cue separation, QR/website/social cues, missing OCR, and
  conflict fields.
- Added merge evidence that records backside-only field augmentation while
  keeping direct sink updates disallowed.
- Added bounded App Intelligence review requests for ambiguous and conflicting
  edges.
- Added no-write PDF page placeholder candidates for preview-only side-pair
  evidence when runtime page materialization is intentionally not performed.

Runtime evidence:

- `positive-control-side-pair-evidence --json` over the current user-scoped
  positive-control corpus produced state `front_back_review_required`.
- Current side-pair counts: 14 contact drafts, 14 scanner page drafts, and 7
  adjacent-page edges.
- Pair proposed: 0. Review required: 7. Front-only: 0.
  Blank/dropped-back: 0. Blocked conflicts: 0.
- App Intelligence review requests: 7 bounded requests.
- Backside augmented edges: 0 because current runtime OCR text is still
  missing for these scanner pages.
- Sink payloads created: 0. Writes attempted: 0. Network calls: 0. Live sink
  calls: `False`. Public-web search and paid enrichment remained unused.
- Runtime report was written under
  `~/.local/share/business-card-watchdog/positive_control_corpus/side_pair_evidence/`.
- Redaction scan found no original scanner path or source filename tokens in
  `/tmp/bcw-positive-control-side-pair-evidence.json`.

Validation:

- `.venv/bin/python -m pytest tests/test_positive_control_side_pair_evidence.py -q`
  passed with 5 tests.
- `.venv/bin/python -m pytest tests/test_positive_control_side_pair_evidence.py tests/test_positive_control_ocr_drafts.py tests/test_positive_control_crop_workbench.py tests/test_positive_control_recognition_training.py tests/test_positive_control_scenarios.py tests/test_positive_control_labels.py tests/test_positive_corpus_side_pair.py tests/test_card_sides.py -q`
  passed with 39 tests.
- `.venv/bin/python -m ruff check src/business_card_watchdog/positive_control_side_pair_evidence.py src/business_card_watchdog/positive_control_ocr_drafts.py src/business_card_watchdog/service.py src/business_card_watchdog/cli.py tests/test_positive_control_side_pair_evidence.py`
  passed.
- `.venv/bin/python scripts/check_plan_drift.py` passed.
- `git diff --check` passed.

Remaining:

- Milestones 7-8 remain open. Next bounded goal is Milestone 7 agent training
  review loop over the accumulated positive-control evidence, with host-owned
  state transitions and no enrichment, routing, sink payloads, writes,
  readbacks, public-web search, or paid-provider calls.

## Suggested Goal Order

1. `/goal Execute Plan 0099 Milestone 1`
2. `/goal Execute Plan 0099 Milestone 2`
3. `/goal Execute Plan 0099 Milestone 3`
4. `/goal Execute Plan 0099 Milestone 4`
5. `/goal Execute Plan 0099 Milestone 5`
6. `/goal Execute Plan 0099 Milestone 6`
7. `/goal Execute Plan 0099 Milestone 7`
8. `/goal Execute Plan 0099 Milestone 8`

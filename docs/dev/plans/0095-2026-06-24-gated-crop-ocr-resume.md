# Plan 0095 | Gated Crop OCR Resume

State: IN_PROGRESS
Date: 2026-06-24

Parent: Plan 0060 Milestone 9

## Purpose

Resume crop, OCR, and App Intelligence quality-assurance work only after the
Plan 0094 card-or-not classifier gate has admitted a scanner page as a
high-confidence business-card candidate.

Plan 0094 closed with this downstream precondition:

- crop/OCR/side-pair/vision-QA may run only for page-level
  `business_card_high_confidence`;
- `not_business_card_high_confidence` is blocked from contact extraction;
- `indeterminate_needs_app_intelligence` is blocked until bounded
  `classify_document_type` evidence changes the page state.

This plan executes that gate in the normal scanner PDF processing path before
continuing deeper into crop, OCR, contact normalization, side pairing, or
review routing.

## Non-Goals

- No live Google Contacts, Odoo, or Odollo lookup/write/readback.
- No selected live target creation.
- No public-web search or paid enrichment.
- No broad unattended scanner backlog run.
- No committing private scanner PDFs, rendered pages, OCR dumps, private
  contact data, or private paths.
- No change to existing image-folder practice workflows unless they are
  scanner PDF page jobs.

## Milestone 1 | Scanner Page Classifier Gate

Objective:

Prevent rendered scanner PDF pages from entering crop/OCR/contact extraction
unless their deterministic classifier state is `business_card_high_confidence`.

Scope:

- Add an explicit classifier-gate artifact to scanner page jobs.
- Record page-level `classifier_training_state` in preclassification evidence.
- For scanner page jobs classified as `not_business_card_high_confidence` or
  `indeterminate_needs_app_intelligence`, write orientation, QR, crop-quality,
  and gate evidence, then stop before `adapter.run_pipeline`.
- Preserve dry-run counters and do not create contact candidates or sink
  payloads for blocked pages.

Acceptance criteria:

- A PDF page classified as high-confidence business card can still reach the
  OCR adapter.
- A PDF page classified as non-card does not call the OCR adapter.
- A PDF page classified as indeterminate does not call the OCR adapter even if
  legacy `prefilter.process_uncertain` is enabled.
- Blocked pages have durable evidence explaining the gate state and downstream
  stop rules.

Validation:

- Unit/integration test over synthetic PDF page jobs.
- Targeted dry-run test proves only admitted scanner pages reach the adapter.
- `ruff`, targeted pytest, `git diff --check`, and plan drift guard pass.

## Milestone 2 | Crop Acceptance Evidence

Objective:

Run crop quality only on admitted business-card pages and make crop acceptance
explicit before OCR normalization proceeds.

Scope:

- Distinguish source-page crop quality from candidate-card crop quality.
- Require accepted crop evidence for any cropped child candidate.
- Route poor, clipped, QR-only, or full-page-looking crops to App Intelligence
  QA instead of contact extraction.

Acceptance criteria:

- Accepted crop evidence is present before OCR-normalized contact candidates
  are projected.
- Bad or ambiguous crops do not become route-ready contacts.
- Review surfaces show crop gate state beside OCR/contact evidence.

Validation:

- Focused crop-quality tests.
- One dry-run scanner page admitted by classifier and blocked by crop QA.

## Milestone 3 | OCR And Vision QA Gate

Objective:

Allow OCR only after classifier and crop gates pass, then route uncertain OCR
or field quality to bounded App Intelligence review.

Scope:

- Attach classifier and crop-gate lineage to OCR outputs.
- Ensure App Intelligence requests are evidence-only and cannot route, enrich,
  or write contacts.
- Keep normalized contacts review-required until OCR quality, field quality,
  and side/context evidence agree.

Acceptance criteria:

- OCR artifacts carry classifier/crop lineage.
- Low-confidence or incomplete OCR creates review/App Intelligence evidence,
  not route-ready contacts.
- Contact routing remains blocked until quality gates pass.

Validation:

- Targeted OCR-quality tests.
- Dry-run proof with writes/network/live-sink counters at zero.

## Milestone 4 | Review Surface Resume

Objective:

Expose the resumed card pipeline in the review surface so operators and agents
can inspect classifier, crop, OCR, and QA evidence together.

Scope:

- Add classifier-gate, crop-gate, OCR-quality, and App Intelligence status to
  the review row/detail payloads.
- Keep non-card and indeterminate scanner pages visible as blocked evidence,
  not contact candidates.
- Preserve mutation boundaries: review changes evidence state only unless an
  explicit later apply plan permits state transition.

Acceptance criteria:

- Review rows show why a scanner page was admitted, blocked, or escalated.
- Contact rows are created only for admitted card candidates.
- Blocked page evidence remains inspectable without creating contacts.

Validation:

- Review-surface tests.
- CLI/API/MCP parity checks for the new evidence fields.

## Milestone 5 | Exit Gate

Objective:

Define when the resumed crop/OCR path is safe to use for the next scanner
practice batch.

Acceptance criteria:

- Scanner pages with `business_card_high_confidence` can produce reviewable
  contact candidates.
- Scanner pages with non-card or indeterminate classifier states cannot produce
  contact candidates.
- Crop/OCR/vision-QA evidence is present for admitted pages.
- ROADMAP points the next offline slice to side-pair/OCR refinement only after
  these gates are fixture-backed.

Validation:

- Full targeted suite for classifier gate, crop quality, OCR quality, and
  review surface.
- One dry-run scanner PDF proof with zero live/network/sink calls.

## Execution Update | 2026-06-24

Milestone 1 is implemented.

Implemented:

- Added `scanner_page_classifier_gate.json` artifacts for rendered scanner PDF
  page jobs.
- Added `classifier_training_state` to scanner page preclassification
  artifacts in the normal batch orchestrator path.
- Blocked scanner page jobs whose classifier state is
  `not_business_card_high_confidence` or
  `indeterminate_needs_app_intelligence` before adapter OCR/contact extraction,
  even when legacy `prefilter.process_uncertain` is enabled.
- Preserved orientation, QR, crop-quality, and recrop evidence for blocked
  pages so review/reporting can inspect the stop reason without creating
  contact candidates.
- Allowed scanner pages with `business_card_high_confidence` to continue to the
  existing OCR/contact extraction path.

Validation:

- `.venv/bin/python -m pytest tests/test_dry_run_pipeline.py::test_scanner_pdf_pages_must_pass_classifier_gate_before_ocr tests/test_preclassifier.py tests/test_classifier_training.py -q`
  passed with 18 tests.
- `.venv/bin/python -m ruff check src/business_card_watchdog/orchestrator.py src/business_card_watchdog/contact_store.py tests/test_dry_run_pipeline.py`
  passed.

Remaining work:

- Milestone 2 crop acceptance evidence.
- Milestone 3 OCR and vision QA gate.
- Milestone 4 review surface resume.
- Milestone 5 exit gate and dry-run scanner PDF proof.

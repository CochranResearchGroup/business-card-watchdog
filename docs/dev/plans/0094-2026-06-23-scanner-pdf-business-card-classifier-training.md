# Plan 0094 | Scanner PDF Business Card Classifier Training

State: IN_PROGRESS
Date: 2026-06-23

Parent: Plan 0060 Milestone 9

## Purpose

Nail down the business-card-versus-other-document framework before continuing
to business-card cropping, OCR, side pairing, or AI vision quality assurance.

The Codex agent should proceed through scanner PDF files one source document at
a time. For each PDF, run the existing BCW deterministic routines that decide
whether each rendered page or image is likely a business card, not a business
card, or indeterminate. The agent then inspects the deterministic outcome,
compares it to the available local evidence, and decides what tuning,
fixtures, or App Intelligence escalation criteria are needed.

This plan treats `uncertain` as a correct and expected outcome. It is not
realistic to deterministically promote or discard every scanned document. The
goal is a defensible framework:

- high-confidence business cards proceed to later card-specific stages,
- high-confidence non-card documents are blocked from contact extraction,
- indeterminate cases are routed to bounded App Intelligence vision review,
- every correction becomes a training fixture or a deterministic rule update.

## Current Evidence

- Plan 0093 completed QR evidence, orientation evidence, crop quality, side-pair
  graph evidence, App Intelligence request artifacts, and idempotent
  `--apply-safe` evidence handlers.
- The existing preclassifier currently uses image dimensions, business-card
  aspect ratio, and OpenCV rectangular contour hints.
- Prior scanner feedback showed that pediatric handouts, CDC tri-fold
  handouts, and safety flyers can appear in scanner inputs and must not be
  promoted as contacts.
- The operator has scanner PDFs and related images in configured watched
  scanner inputs. Private scanner paths and raw images must remain in
  user-scoped runtime/cache state, not git.

## Non-Goals

- No business-card crop/OCR tuning in this plan except whatever minimal
  artifacts the existing deterministic classifier already emits.
- No front/back side-pair merging.
- No contact enrichment.
- No Google Contacts, Odoo, or Odollo lookup/write/readback.
- No selected live target creation.
- No public-web search or paid enrichment.
- No broad unattended scanner backlog processing.
- No committing private scanner PDFs, rendered page images, raw OCR dumps, or
  private paths.

## Agent Loop Contract

For each iteration, Codex should:

1. Select exactly one scanner PDF source document from the configured scanner
   corpus or a cache-local practice copy.
2. Run BCW deterministic intake in dry-run mode with live/network/sink counters
   expected to remain zero.
3. Read only redacted or runtime-local classifier artifacts:
   `preclassification.json`, `card_candidates.json`, document-page manifests,
   review bundle summaries, App Intelligence request artifacts, and run ledgers.
4. Decide whether each page/document outcome is:
   - `business_card_high_confidence`
   - `not_business_card_high_confidence`
   - `indeterminate_needs_app_intelligence`
5. Inspect failures by comparing deterministic evidence to local rendered
   artifacts or redacted previews, not by committing private images.
6. Update deterministic thresholds, feature extraction, labels, or fixture
   expectations only when the change is supported by the current document and
   targeted tests.
7. Create or update privacy-safe fixtures that represent the failure mode.
8. Add or refine `classify_document_type` App Intelligence request criteria for
   cases that should not be deterministically decided.
9. Re-run targeted classifier tests and a one-PDF dry-run.
10. Stop when the current PDF has either stable deterministic classification or
    bounded App Intelligence requests for the indeterminate cases.

## Classifier States

`business_card_high_confidence`:

- Evidence has a card-like rectangular object or page geometry plus enough
  card-specific signals to justify card-specific downstream work.
- This state allows later crop/OCR/side-pair work, but does not itself route,
  enrich, or write contacts.

`not_business_card_high_confidence`:

- Evidence strongly indicates a handout, flyer, form, multi-panel brochure,
  letter/page document, or other non-card source.
- This state blocks contact extraction unless later operator/App Intelligence
  evidence overrides it.

`indeterminate_needs_app_intelligence`:

- Deterministic evidence is conflicting, weak, or outside current rule
  coverage.
- This state creates a bounded `classify_document_type` request with candidate
  choices and stop rules.
- App Intelligence response is evidence only; accepted patterns must become
  deterministic fixtures or rule updates before safe apply.

## Milestone 1 | Scanner PDF Training Queue

Objective:

Create a deterministic, bounded queue for classifier training over scanner PDFs.

Scope:

- Discover scanner PDF source documents from configured scanner/practice inputs.
- Select one PDF per agent iteration.
- Render or reuse page-level derivatives in runtime/cache state only.
- Record a classifier-training iteration artifact that references runtime paths
  without committing private paths or images to git.

Acceptance criteria:

- A command or documented procedure selects exactly one PDF.
- The selected PDF produces a dry-run ledger with zero live/network/sink calls.
- The iteration artifact records PDF identity, page count, classifier artifact
  paths, and stop conditions.

Validation:

- Unit or CLI test for one-PDF selection.
- Dry-run on one scanner PDF or cache-local copy.
- `ruff`, targeted pytest, `git diff --check`, and plan drift guard pass.

## Milestone 2 | Deterministic Card-Or-Not Evidence

Objective:

Improve deterministic evidence so non-card documents are not accidentally
promoted into business-card work.

Scope:

- Extend classifier evidence beyond aspect ratio and rectangle hints.
- Add page/document features such as page count, page aspect, text-block
  density, multi-panel layout hints, dominant full-page document geometry,
  multiple-card grid hints, and QR-only ambiguity.
- Produce an explicit document-type decision artifact with state, score,
  reasons, and feature weights.
- Keep high-confidence thresholds conservative.

Acceptance criteria:

- A privacy-safe business-card fixture classifies as
  `business_card_high_confidence`.
- Privacy-safe handout/flyer/brochure fixtures classify as
  `not_business_card_high_confidence`.
- Ambiguous fixtures classify as `indeterminate_needs_app_intelligence`.

Validation:

- Focused classifier unit tests.
- One-PDF scanner dry-run demonstrates page/document states and reasons.

## Milestone 3 | App Intelligence Escalation Criteria

Objective:

Define when deterministic classification should stop and ask App Intelligence
for vision classification.

Scope:

- Create `classify_document_type` request artifacts for indeterminate cases.
- Include deterministic evidence, candidate labels, allowed answer schema, and
  stop rules.
- Prevent App Intelligence responses from directly routing contacts or enabling
  crop/OCR work.
- Convert accepted responses into fixture/rule training candidates.

Acceptance criteria:

- High-confidence deterministic cases do not create App Intelligence requests.
- Indeterminate cases create bounded `classify_document_type` requests.
- Imported/accepted response evidence cannot directly route, enrich, or write.

Validation:

- Tests for request gating.
- Tests for response-evidence boundaries.
- Dry-run agent iteration produces requests only for indeterminate cases.

## Milestone 4 | One-PDF Agent Training Iterations

Objective:

Let Codex perform repeated one-PDF training iterations without operator review
unless a human-only gate is reached.

Scope:

- Add or document a repeatable agent loop:
  - pick one PDF,
  - run deterministic classification,
  - inspect outcomes,
  - tune rules/fixtures,
  - create App Intelligence requests for indeterminate cases,
  - re-run targeted validation,
  - record closeout.
- Keep scanner PDFs and rendered pages in runtime/cache state.
- Record per-iteration decisions and unresolved cases.

Acceptance criteria:

- Each iteration has a run id, selected PDF identity, classifier decisions,
  tuning changes, tests, and remaining indeterminate cases.
- Repeated iterations reduce false business-card promotions for known
  handout/flyer cases.
- No crop/OCR/side-pair/QA work proceeds for documents classified as non-card
  or indeterminate.

Validation:

- At least one completed one-PDF training iteration.
- Targeted test coverage for every deterministic tuning change.
- Runtime proof that writes/network/live-sink counters remain zero.

## Milestone 5 | Exit Gate To Crop/OCR Work

Objective:

Define the gate for returning to business-card crop, OCR, and vision QA work.

Scope:

- Summarize classifier precision/coverage on the current scanner training set.
- List which document types are deterministic and which require App
  Intelligence.
- Define the exact downstream precondition for card crop/OCR work.

Acceptance criteria:

- The classifier has fixture-backed coverage for business cards, handouts,
  flyers, tri-fold/brochure-like pages, full-page documents, and ambiguous
  cases.
- App Intelligence escalation criteria are explicit and tested.
- ROADMAP points the next offline slice back to crop/OCR only after this gate is
  satisfied.

Validation:

- Full targeted classifier suite passes.
- One scanner PDF dry-run closeout proves the gate behavior.
- Plan closeout records remaining risks and next recommended crop/OCR slice.

## Execution Update | 2026-06-24

Implemented the first classifier-training loop slice.

Milestone coverage:

- Milestone 1 is implemented for a bounded one-PDF classifier-training command.
  `runs classifier-training-iteration` selects exactly one configured scanner
  PDF or accepts one explicit `--source`, renders pages into user-scoped
  runtime state, writes a run ledger, and records a
  `classifier_training_iteration` artifact.
- Milestone 2 has an initial deterministic tuning pass. The classifier now
  uses card-like aspect, rectangle evidence, text-line layout, dense
  document-like text detection, and tiny-rectangle suppression.
- Milestone 3 has initial request gating. Indeterminate pages create bounded
  `classify_document_type` App Intelligence request artifacts with zero
  network calls and zero live/sink writes.

Training evidence:

- One positive-control scanner PDF containing a business-card scan classified
  as `business_card_high_confidence`.
- Nine additional scanner PDFs were processed one source document at a time.
  Several initial false promotions were caused by dense handout/title-page
  layouts and tiny single rectangular logos. After tuning, the positive control
  still promoted, dense card-shaped documents routed to
  `indeterminate_needs_app_intelligence`, and portrait/full-page documents
  dropped to `not_business_card_high_confidence`.
- The loop remained offline: `writes_attempted = 0`,
  `network_calls_made = 0`, no live sink calls, no public-web search, and no
  paid enrichment.

Validation:

- `.venv/bin/python -m pytest tests/test_preclassifier.py tests/test_classifier_training.py -q`
  passed with 12 tests.
- `.venv/bin/python -m ruff check src/business_card_watchdog/preclassifier.py src/business_card_watchdog/service.py src/business_card_watchdog/cli.py src/business_card_watchdog/contact_store.py tests/test_preclassifier.py tests/test_classifier_training.py`
  passed.

Remaining work:

- Add a durable corpus-level report that summarizes precision/coverage without
  committing private scanner artifacts.
- Add more privacy-safe fixtures for tri-fold/brochure, flyer, handout, and
  ambiguous card-like document cases.
- Continue one-PDF iterations until the exit gate can confidently return the
  project to crop/OCR and App Intelligence quality-assurance work.

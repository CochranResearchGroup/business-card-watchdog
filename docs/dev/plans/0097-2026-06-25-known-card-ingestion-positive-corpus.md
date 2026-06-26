# Plan 0097 | Known-Card Ingestion And Positive Corpus

State: IN_PROGRESS
Date: 2026-06-25

Parent: Plan 0060 Milestone 9

## Purpose

Pause broad business-card autodetection until the operator has supplied more
positive controls. In the meantime, make Business Card Watchdog useful as a
higher-powered, reviewable wrapper around the `business-card-to-contact` skill
for sources the operator has explicitly declared are business cards.

As known real cards are processed, retain their original image or PDF inputs in
a user-scoped positive-control corpus so later classifier training has real
positive examples without committing private card artifacts to git.

## Non-Goals

- No broad unknown-document autodetection work.
- No weakening Plan 0095 gates for scanner pages that have not been declared
  known business cards.
- No committing private card images, PDFs, rendered pages, OCR dumps, contact
  specs, or derived crops.
- No silent Google Contacts, Odoo, Odollo, Apollo, People Data Labs, public-web,
  or paid-enrichment writes.
- No live sink write/readback until a later explicit selected-contact approval
  boundary.

## Milestone 1 | Known-Card Intake Contract

Objective:

Add an explicit known-card intake mode for operator-declared business card
images and PDFs.

Scope:

- Accept a file or directory as `known_business_card` input.
- Bypass the unknown-document classifier only for explicitly declared known-card
  sources.
- Preserve run ledgers, dry-run defaults, review-required states, contact-store
  projection, and sink blocking.
- Record source lineage that distinguishes operator-declared positives from
  autodetected positives.

Acceptance criteria:

- Known-card image inputs reach crop/OCR/review without requiring the
  business-card-vs-not-business-card classifier gate.
- Unknown watched scanner inputs still use the Plan 0095 classifier gate.
- Dry-run closeout still reports zero live sink, network, public-web, and paid
  enrichment activity.

## Milestone 2 | Positive-Control Corpus Retention

Objective:

Copy operator-declared real card sources into a user-scoped positive-control
corpus for future training.

Scope:

- Store originals under
  `~/.local/share/business-card-watchdog/positive_control_corpus/`.
- Deduplicate by content hash.
- Preserve source media kind, original suffix, size, hash, first-seen time,
  intake run id, and operator-declared label.
- Redact private absolute paths from committed artifacts and normal CLI/API/MCP
  summaries.
- Keep corpus writes local-only with zero network and zero sink writes.

Acceptance criteria:

- Processing a known-card image or PDF can retain the original source file in
  the positive-control corpus.
- Reprocessing the same source is idempotent and does not duplicate corpus
  blobs.
- Corpus manifests are runtime state only and are never written under the repo
  tree.

## Milestone 3 | Known PDF And Card-Side Handling

Objective:

Support known-card PDFs, including double-sided cards, without relying on broad
autodetection.

Scope:

- Rasterize known-card PDFs through the existing scanner document-intake path.
- Treat adjacent pages as possible front/back card sides while preserving
  variable front/back order.
- Support missing/dropped blank backs.
- Route side-pair ambiguity to review/App Intelligence evidence rather than
  live writes.

Acceptance criteria:

- A known-card PDF can produce page lineage, side-pair evidence, OCR artifacts,
  and reviewable contact candidates in dry-run mode.
- Backside-only useful fields can augment the front-side contact candidate.
- Ambiguous or conflicting backs remain review-required.

## Milestone 4 | Business-Card Skill Workbench

Objective:

Use `business-card-to-contact` as the extraction core while BCW supplies batch
state, review, corpus retention, and sink gating.

Scope:

- Invoke the skill pipeline for known card images/pages.
- Retain OCR text, normalized contact JSON, crop candidates, chosen crop, and
  review report as run artifacts.
- Project reviewed contact candidates into the user-scoped contact store.
- Keep Google Contacts apply disabled unless an explicit later apply boundary
  is selected.

Acceptance criteria:

- Known-card runs expose enough artifacts for review: source image/page, OCR
  text, normalized fields, crop candidates, chosen crop, side-pair status, and
  sink readiness.
- The workflow can serve as a more powerful dry-run version of
  `business-card-to-contact`.

## Milestone 5 | Review And Apply Boundary

Objective:

Prepare, but do not automatically execute, selected-contact apply workflows.

Scope:

- Add review surface status for known-card extraction quality, crop choice,
  side-pair status, corpus retention, and sink readiness.
- Allow field/crop/routing mutation before apply.
- Produce explicit command-copy or approval packets for selected Google
  Contacts writes only.
- Keep Odoo/Odollo/enrichment as reviewed stubs until separate approval.

Acceptance criteria:

- A reviewed known-card contact can be selected for an explicit future Google
  Contacts apply boundary.
- No live write path is reachable from known-card intake without the selected
  apply gate.

## Validation Strategy

- Synthetic known-card image tests for classifier bypass, dry-run closeout, and
  corpus retention.
- Synthetic known-card PDF tests for page lineage and side-pair evidence.
- Idempotency tests for positive-control corpus dedupe by hash.
- CLI/API/MCP parity tests for known-card intake status and corpus summaries.
- `ruff`, targeted pytest, `scripts/check_plan_drift.py`, and `git diff --check`
  before closeout.

## Stop Conditions

- If a source has not been explicitly declared a known business card, it must
  stay on the existing classifier-gated path.
- If corpus output would land under the repository tree, fail closed.
- If any sink, enrichment, public-web, or paid provider call would occur during
  known-card intake, fail closed.

## Execution Update | 2026-06-26 | Positive-Corpus Filing Foundation

Implemented the first known-card positive-evidence filing surface.

Implemented:

- Added `known-card-intake` as an explicit operator-declared known-card intake
  command.
- Added a service surface that accepts explicit source files or directories and
  filters to supported images and PDFs.
- Added user-scoped positive-control corpus retention under
  `~/.local/share/business-card-watchdog/positive_control_corpus/`.
- Deduped retained originals by content hash and stored blobs by hash/suffix.
- Wrote redacted runtime manifests and an idempotent corpus index without
  exposing original private source paths or filenames in normal summaries.
- Kept this foundation as positive-evidence filing only: no OCR, crop,
  rasterization, enrichment, routing, sink write, readback, public-web, or paid
  provider activity.

Runtime proof:

- Located and visually confirmed five operator-declared business-card sources
  from the configured scanner and phone paths: three ScanSnap PDFs and two
  Samsung JPEGs from June 25, 2026.
- Filed all five as positive evidence with `known-card-intake`; the write
  reported 2 images, 3 PDF documents, 5 newly stored blobs, zero errors, zero
  OCR, zero PDF rasterization, zero crops, zero writes, zero network calls, zero
  live sink calls, zero public-web search, and zero paid enrichment.
- Re-ran the same intake and confirmed all five entries deduped by hash.

Remaining work:

- Milestone 1 still needs the crop/OCR known-card processing bypass around
  unknown-document autodetection.
- Milestones 3-5 remain open for known-card PDF side handling, workbench
  review, and selected apply boundaries.

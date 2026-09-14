# Plan 0115 | Reviewed Page-Label Training

State: COMPLETE
Date: 2026-09-14

Parent: Plan 0097 known-card ingestion and positive-corpus lane
Work item: GitHub issue #1

## Scope

- Add an append-only, user-runtime overlay for operator-reviewed page labels on
  known-positive corpus entries.
- Merge the latest valid review for each page into the generated positive-control
  label inventory without storing private card content or paths in the repository.
- Let positive-control recognition training use an explicit confirmed-card review
  as supervised evidence while retaining the baseline classifier result.
- Apply the reviewed labels from the 37-page conference stack and replay the
  positive and negative control corpora.

## Non-Goals

- No model-weight training or global preclassifier threshold change.
- No promotion of unknown documents or unreviewed positive-control pages.
- No broad watched-folder autodetection resume.
- No contact extraction, enrichment, CRM, Slack, or other live sink action.
- No private scan, OCR text, contact identity, source path, or runtime report in Git.

## Acceptance Criteria

- A confirmed reviewed page is promoted only inside the operator-declared
  positive-control training replay, with baseline state and review provenance
  retained in the case output.
- Missing, withdrawn, or non-confirming reviews do not promote a page.
- Review writes are append-only, idempotent for an unchanged latest review, and
  reject unknown entries, out-of-range pages, or invalid side roles.
- The reviewed 37-page stack has no remaining indeterminate recognition cases.
- The current negative-control replay remains false-positive clean.
- Focused tests pass, and the full suite introduces no failures beyond the
  independently reproduced upstream baseline.
- Feature-module Ruff, correctness lint on the shared CLI/service surfaces,
  plan drift, and diff checks pass.

## Validation Plan

- `.venv/bin/python -m pytest tests/test_positive_control_labels.py tests/test_positive_control_recognition_training.py tests/test_negative_corpus_recognition.py -q`
- `.venv/bin/python -m pytest -q`
- `.venv/bin/python -m ruff check .`
- `.venv/bin/python scripts/check_plan_drift.py`
- `git diff --check`

## Current State

- The stack is already an operator-declared positive-control source.
- Baseline/current contextual replay recognizes 13 of 37 pages at high
  confidence; 24 remain indeterminate and none are high-confidence negatives.
- Human visual review confirmed all 37 pages are business-card sides and
  identified their side roles, including two duplicate fronts and one
  organization-only card.
- The existing inventory generates candidate labels but has no durable input
  surface for reviewed page truth.
- Broad autodetection remains paused.

## Execution Update | 2026-09-14

Implemented:

- Added an append-only `reviewed_page_labels.jsonl` runtime ledger and a
  `positive-control-page-review` CLI/service surface with entry, page, review
  state, side role, reviewer, and optional duplicate-page validation.
- Made unchanged repeated reviews idempotent and retained later corrections as
  append-only events whose latest valid value becomes the inventory overlay.
- Added reviewed-page provenance to recognition cases and scoped confirmed-page
  promotion to the operator-declared positive-control replay.
- Preserved baseline classifier state, global thresholds, and the broad
  autodetection pause.

Runtime evidence:

- Recorded 37 confirmed reviews in the private runtime ledger: 19 fronts, 15
  backs, 2 duplicate fronts, and 1 organization-only card.
- Candidate replay
  `positive-control-recognition-training-2026-09-14T21-15-55+00-00-eb3937061e33`
  moved the reviewed stack from 13/37 baseline high-confidence pages to 37/37.
- The upstream-lineage branch leaves the other positive-control backlog
  explicit: the full corpus moved from 15 high / 36 indeterminate / 2 negative
  to 39 high / 14 indeterminate / 0 negative.
- Negative replay
  `negative-corpus-recognition-2026-09-14T21-15-55+00-00-07ee5557f169`
  retained 0 false positives across 5 sources / 5 replayed pages.

Validation:

- Focused label, recognition, and negative-control suite: 13 passed.
- Candidate full suite: 477 passed, 12 failed.
- Untouched `upstream/main` under the same environment: 472 passed, the same
  12 tests failed; this slice adds five passing tests and no new failures.
- Feature-module Ruff passed. Ruff `F` correctness checks passed on the shared
  CLI/service and changed test surfaces. Repository-wide Ruff remains blocked
  by 290 pre-existing upstream findings.
- Plan drift and diff checks passed.
- Editable install with API, watch, vision, and dev extras completed in the
  isolated branch virtual environment.

Safety:

- No global unknown-document threshold changed.
- No private scan, card image, OCR text, contact identity, or runtime report was
  added to the repository.
- No network, enrichment, CRM, Slack, or live sink call was made in this slice.

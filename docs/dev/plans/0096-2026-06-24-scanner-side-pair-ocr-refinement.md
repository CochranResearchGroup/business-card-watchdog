# Plan 0096 | Scanner Side-Pair OCR Refinement

State: IN_PROGRESS
Date: 2026-06-24

Parent: Plan 0060 Milestone 9

## Purpose

Refine scanner front/back pairing and OCR merge behavior now that Plan 0095
gates prevent non-card and indeterminate scanner pages from reaching contact
extraction.

The operator confirmed that additional positive controls can be synthesized
from the already supplied private scanner PDF and image set by changing page
order, orientation, omitted pages, inserted pages, and multi-card
combinations. This plan uses those private materials as runtime-only seeds.
Generated controls must stay under user-scoped runtime/cache paths and must not
be committed to git.

## Non-Goals

- No live Google Contacts, Odoo, or Odollo lookup/write/readback.
- No selected live target creation.
- No public-web search or paid enrichment.
- No committing private scanner PDFs, rendered pages, card images, OCR dumps,
  derived positive-control images, or private paths.
- No broad unattended scanner backlog run.
- No weakening Plan 0095 classifier, crop, OCR, or review-surface gates.

## Milestone 1 | Runtime Positive-Control Synthesis

Objective:

Create a bounded positive-control generator that builds scanner side-pair/OCR
test sequences from the existing private scanner seed set without storing
private artifacts in the repo.

Scope:

- Discover or accept explicit runtime seed files from configured scanner and
  phone/image inputs.
- Generate runtime-only positive controls for:
  - front then back;
  - back then front;
  - front with blank or dropped back;
  - useful backside fields augmenting the front;
  - rotated fronts/backs;
  - interleaved non-card pages;
  - multi-card sequences that must not cross-merge adjacent unrelated cards.
- Write a redacted manifest that records scenario names, expected pair groups,
  expected omitted/blank pages, and expected no-merge boundaries.
- Store generated artifacts under `~/.local/share/business-card-watchdog/` or
  `~/.cache/business-card-watchdog/`.
- Commit only generator code, schema docs, and privacy-safe synthetic fixtures.

Acceptance criteria:

- The generator can run in preview mode without writing generated controls.
- Generated controls never land under the repo tree.
- The manifest exposes enough expected outcomes to drive deterministic tests
  without revealing private card data.
- At least one privacy-safe synthetic test exercises the manifest schema.

Validation:

- Unit tests over synthetic seed images.
- Dry-run manifest generation with zero network calls, zero writes to sinks,
  and no repo artifact churn.

## Execution Update | 2026-06-24 | Milestone 1

Milestone 1 is implemented.

Implemented:

- Added a runtime-only positive-control generator exposed through
  `BusinessCardService.watch_positive_controls`.
- Added CLI command `watch-positive-controls` with `--no-write`, `--seed`,
  `--include-glob`, and `--json`.
- Generated redacted positive-control manifests for front/back, back/front,
  dropped-back, rotated front/back, interleaved non-card, and multi-card
  no-cross-merge scenarios when enough image seeds exist.
- Recorded PDF seeds as source documents without rasterizing them in the
  positive-control generator.
- Kept original private seed paths and filenames out of the manifest; generated
  files are written only under cache runtime state when write mode is enabled.
- Added a repo-output guard so generated controls cannot be written under the
  repository tree.

Validation:

- `.venv/bin/python -m pytest tests/test_positive_controls.py -q` passed with
  3 tests.
- `.venv/bin/python -m ruff check src/business_card_watchdog/positive_controls.py src/business_card_watchdog/service.py src/business_card_watchdog/cli.py tests/test_positive_controls.py`
  passed.

Remaining work:

- Milestone 2 side-pair graph scoring against synthesized controls.
- Milestone 3 OCR merge completeness.
- Milestone 4 App Intelligence escalation criteria.
- Milestone 5 exit gate.

## Milestone 2 | Side-Pair Graph Scoring

Objective:

Improve deterministic scanner side-pair graph scoring against the synthesized
positive controls.

Scope:

- Treat scanner adjacency as a strong but not exclusive clue.
- Support front/back and back/front order.
- Detect likely dropped blank backs.
- Block cross-card merges when adjacent pages have conflicting OCR identity,
  organization, QR, or visual/card-boundary evidence.
- Preserve App Intelligence escalation for ambiguous pair graphs.

Acceptance criteria:

- Positive controls produce expected pair groups or bounded review-required
  states.
- Cross-card controls do not merge unrelated cards.
- Blank/dropped-back controls do not block complete front-only contacts.

Validation:

- Side-pair graph tests over synthesized controls.
- Review-bundle evidence shows side-pair reasoning without raw OCR leakage.

## Execution Update | 2026-06-24 | Milestone 2

Milestone 2 is implemented.

Implemented:

- Extended the side-pair graph beyond adjacent-only edges so compatible
  non-adjacent front/back pairs inside the pairing window can be represented.
- Kept adjacency as strong evidence while requiring deterministic context
  before a front/back edge becomes `pair_proposed`.
- Added broader conflicting-domain evidence so cross-card boundaries with
  different email/URL domains are blocked instead of proposed.
- Preserved blank-back and QR-adjacency review states.
- Added tests that consume synthesized positive-control scenario manifests for
  interleaved non-card and multi-card no-cross-merge cases.

Validation:

- `.venv/bin/python -m pytest tests/test_card_sides.py tests/test_positive_controls.py -q`
  passed with 17 tests.
- `.venv/bin/python -m ruff check src/business_card_watchdog/card_sides.py src/business_card_watchdog/positive_controls.py tests/test_card_sides.py tests/test_positive_controls.py`
  passed.

Remaining work:

- Milestone 3 OCR merge completeness.
- Milestone 4 App Intelligence escalation criteria.
- Milestone 5 exit gate.

## Milestone 3 | OCR Merge Completeness

Objective:

Tune deterministic OCR completeness and merge rules for front/back card data.

Scope:

- Define required fields for a route-reviewable contact candidate.
- Allow backside-only phone, email, website, address, QR, or social fields to
  augment a front-side identity.
- Block or escalate conflicting names, organizations, emails, and phone
  numbers.
- Keep merged contacts review-required until deterministic evidence is coherent.

Acceptance criteria:

- Backside useful fields merge into one contact candidate.
- Conflicting backside data creates review/App Intelligence evidence, not a
  route-ready contact.
- OCR quality gates record merge lineage.

Validation:

- OCR/merge tests over front/back positive controls.
- Dry-run closeout shows zero sink payloads and zero live/network calls.

## Execution Update | 2026-06-24 | Milestone 3

Milestone 3 is implemented.

Implemented:

- Added `ocr_merge_quality` evidence to reviewed side-pair contacts.
- Defined merge completeness around `full_name` plus at least one contact point
  (`email`, `phone`, or `website`).
- Preserved backside-only phone and website fields as merge augmentations.
- Added conflict detection for front/back OCR disagreement on names, emails,
  phones, and other contact fields.
- Kept merged side-pair contacts review-required and blocked from routing,
  enrichment, sink writes, and readback.
- Added merge lineage to OCR merge quality evidence.

Validation:

- `.venv/bin/python -m pytest tests/test_card_sides.py -q` passed with 16
  tests.
- `.venv/bin/python -m ruff check src/business_card_watchdog/card_sides.py tests/test_card_sides.py`
  passed.

Remaining work:

- Milestone 4 App Intelligence escalation criteria.
- Milestone 5 exit gate.

## Milestone 4 | App Intelligence Escalation Criteria

Objective:

Route only genuinely ambiguous side-pair/OCR cases to App Intelligence with
evidence-only stop rules.

Scope:

- Add bounded request types for side-pair ambiguity and OCR merge conflict.
- Ensure App Intelligence responses cannot route, enrich, write, read back, or
  select live targets.
- Convert accepted App Intelligence corrections into deterministic fixture or
  rule candidates before any safe apply.

Acceptance criteria:

- Deterministically resolvable controls do not request App Intelligence.
- Ambiguous controls produce bounded request payloads.
- Accepted responses remain evidence-only until a tested deterministic rule or
  fixture is added.

Validation:

- Agent-loop tests for side-pair/OCR requests.
- Review-surface tests for escalation status.

## Milestone 5 | Exit Gate

Objective:

Define when scanner side-pair/OCR refinement is ready for another real scanner
practice replay.

Acceptance criteria:

- Synthesized positive controls cover front/back, back/front, blank/dropped
  backs, rotation, backside-only useful fields, interleaved non-cards, and
  multi-card no-merge boundaries.
- Admitted scanner pages can produce reviewable merged contact candidates.
- Non-card and indeterminate pages remain blocked by Plan 0095 gates.
- Dry-run closeout proves zero sink payloads, zero writes, zero network calls,
  zero public-web search, and zero paid enrichment.

Validation:

- Full targeted suite for positive-control synthesis, side-pair graph, OCR
  merge, App Intelligence escalation, and review surfaces.
- One bounded dry-run replay from runtime-only generated controls.

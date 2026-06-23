# Plan 0093 | Agent Loop QR Orientation And Side Pairing

State: IN_PROGRESS
Date: 2026-06-23

Parent: Plan 0060 Milestone 9

## Purpose

Turn the Gallagher scanner feedback into an agent-operable review loop. The
service must improve deterministic QR extraction, orientation normalization,
crop quality, and scanner front/back pairing before asking App Intelligence to
review ambiguous cases. Human review should become the exception; agents should
run bounded review iterations, record evidence, and improve the deterministic
algorithm after each iteration.

## Current Evidence

- Focused scanner-sequence run: `2026-06-22T22-36-20+00-00`.
- Two reviewable Gallagher jobs remain `needs_review`.
- Operator feedback from Previews:
  - Job 1 is a Gallagher asphalt card side with QR code and no visible
    business-card text; contact text is likely on the other side.
  - Job 2 is another Gallagher card side with QR code, wrong orientation, and a
    bad crop.
- Both contacts have accepted contact-review evidence under
  `card_side_and_crop_quality` with recommendation
  `keep_needs_review_require_qr_orientation_crop_and_backside_pairing`.
- No live lookup, live write, readback, public-web search, paid enrichment, or
  selected-target creation is allowed in this plan.

## Non-Goals

- No live GWS/Odoo/Odollo lookup/write/readback.
- No selected live target creation.
- No public-web search or paid enrichment.
- No broad scanner backlog run.
- No storing raw private OCR dumps, card images, or private scanner paths in
  git.
- No replacing deterministic host control with agent/model control.

## Milestone 1 | QR Evidence Extraction

Objective:

Add deterministic QR detection and decoding artifacts for source pages and
candidate crops.

Scope:

- Detect QR-like regions on source pages and crop images.
- Decode QR payloads when local libraries can do so.
- Store redacted QR artifacts under the run/job artifact directory.
- Add QR evidence to review bundles, contact-store asset projection, and review
  surface rows.
- Keep QR payload handling conservative: store decoded URLs/text only in
  user-scoped runtime state, not git; redact in repo docs.

Acceptance criteria:

- A fixture with a QR code produces `qr_evidence.json`.
- A no-QR fixture produces an explicit `none_found` artifact.
- Review surface exposes QR presence, decode state, and payload type without
  leaking private payloads into committed docs.
- No network calls are made from QR detection.

Validation:

- Unit tests for QR present, QR absent, and unreadable QR.
- Dry-run on the focused Gallagher run proves QR evidence exists for the two
  reviewable jobs.
- `ruff`, targeted pytest, `git diff --check`, and plan drift guard pass.

## Milestone 2 | Orientation Normalization

Objective:

Add deterministic orientation scoring and normalized review images before OCR,
crop review, and QR extraction.

Scope:

- Score 0, 90, 180, and 270 degree rotations using OCR token confidence,
  QR geometry, card aspect ratio, and text-line orientation.
- Store `orientation_evidence.json` and a normalized image derivative when a
  rotation is chosen.
- Preserve the original page/crop asset and link normalized derivatives by
  provenance.
- Mark low-confidence orientation as `needs_app_intelligence_review` rather than
  rotating silently.

Acceptance criteria:

- Wrong-orientation fixture is normalized deterministically.
- Ambiguous fixture remains unchanged and is marked for App Intelligence review.
- Review HTML shows original and normalized images side by side.

Validation:

- Unit tests for rotation selection, no-op orientation, and ambiguous
  orientation.
- Dry-run on Gallagher Job 2 shows a deterministic orientation proposal or a
  documented App Intelligence escalation.

## Milestone 3 | Crop Quality And Recrop Proposals

Objective:

Improve deterministic crop proposals so QR-only sides and partial-card crops are
not treated as route-ready contact evidence.

Scope:

- Add crop quality metrics: card boundary coverage, text density, QR density,
  blank area, clipping risk, and aspect ratio.
- Generate recrop proposals from source page geometry when the first crop is
  poor.
- Store `crop_quality.json` and `recrop_proposals.json`.
- Keep crop decisions as evidence; host state transitions remain deterministic.

Acceptance criteria:

- Bad-crop fixture is flagged with `crop_quality = "bad"`.
- Recrop proposal exists when a larger plausible card boundary can be found.
- Review surface can compare original crop, recrop proposal, QR evidence, and
  extracted data.

Validation:

- Unit tests for good crop, clipped crop, QR-only crop, and no-card handout.
- Dry-run on Gallagher Job 2 shows bad-crop evidence and at least one recrop
  proposal or a reason no proposal is possible.

## Milestone 4 | Scanner Front/Back Pairing

Objective:

Pair adjacent scanner pages into card-side candidates using deterministic
sequence and contextual evidence.

Scope:

- Build a scanner sequence graph from source document order, PDF siblings,
  page numbers, QR payloads, OCR tokens, logo/domain clues, and blank-back
  handling.
- Treat adjacent front/back pages as candidates, but do not assume order.
- Allow dropped blank backs without pairing unrelated cards.
- Store `side_pair_graph.json` and pair confidence reasons.
- Merge side evidence only when deterministic thresholds pass; otherwise create
  an App Intelligence review request.

Acceptance criteria:

- Front/back fixture with reversed order pairs correctly.
- Front-only fixture with dropped blank back remains a single-side card.
- QR-only front plus text backside creates a pair proposal requiring review or
  deterministic merge depending on confidence.
- Handouts/flyers are not paired into contacts.

Validation:

- Unit tests for adjacent front/back, reversed order, blank dropped back,
  QR-only side, and unrelated adjacent pages.
- Dry-run on the 2026-06-20 scanner sequence produces side-pair proposals for
  the Gallagher cards and keeps handouts/flyers out of route-ready contacts.

## Milestone 5 | App Intelligence Escalation Contract

Objective:

Define when agents may ask App Intelligence for review and how those results
train deterministic gates.

Scope:

- Add `app_intelligence_review_request.json` only when deterministic evidence is
  insufficient.
- Request types:
  - `classify_document_type`
  - `resolve_orientation`
  - `assess_crop_quality`
  - `pair_card_sides`
  - `verify_contact_fields`
- Each request must include deterministic evidence, candidate choices, stop
  rules, and what answer shape is allowed.
- Each response is stored as review evidence, not a state transition.
- Host code converts accepted response patterns into deterministic rule updates
  or fixture additions.

Acceptance criteria:

- App Intelligence requests are absent when deterministic confidence is high.
- Requests are present and bounded when QR/orientation/pairing evidence is
  ambiguous.
- Responses cannot directly route, enrich, or write contacts.
- A training artifact records what deterministic rule or fixture should be
  added from each reviewed case.

Validation:

- Tests prove App Intelligence review is gated by deterministic uncertainty.
- Tests prove response import does not create route-ready contacts by itself.
- A dry-run agent loop iteration produces training candidates but no live calls.

## Milestone 6 | Agent Review Loop

Objective:

Let agents run bounded review iterations without operator involvement unless a
human-only gate is reached.

Loop contract:

1. Select one bounded review batch from a known run, never the broad scanner
   backlog.
2. Run deterministic analyzers: QR, orientation, crop quality, side pairing,
   OCR/context extraction, duplicate-safe route readiness.
3. Apply safe deterministic decisions:
   - reject non-card handouts/flyers when confidence is high
   - normalize orientation when confidence is high
   - accept recrop proposals when deterministic crop quality improves
   - pair sides when confidence passes threshold
4. Create App Intelligence review requests for ambiguous cases only.
5. Import App Intelligence responses as evidence.
6. Add or update a fixture/training case for every accepted App Intelligence
   correction.
7. Re-run targeted tests and the focused dry-run.
8. Stop when the batch has no safe actions, no bounded App Intelligence
   requests, or reaches a live/paid/human gate.

Agent permissions:

- Agents may write local runtime artifacts, deterministic code, fixtures, tests,
  and repo docs.
- Agents may not execute live lookup/write/readback, paid enrichment, public-web
  search, selected-target creation, or broad private backlog processing.
- Agents may not mark a contact route-ready unless deterministic gates pass and
  lookup prerequisites remain no-live.

Acceptance criteria:

- `bcw runs agent-review-loop <run-id> --limit <n> --dry-run --json` reports
  planned actions without applying.
- `--apply-safe` applies only safe deterministic actions and records all
  evidence.
- Loop output reports:
  - deterministic improvements applied
  - App Intelligence requests created
  - training fixtures added
  - contacts still blocked and why
  - writes/network/live counters, all zero
- Repeated loop iterations reduce repeated failure modes in the focused scanner
  sequence.

Validation:

- Unit tests for loop planning and safe-apply boundaries.
- Integration test on synthetic scanner sequence with QR side/back side.
- Focused dry-run on `2026-06-22T22-36-20+00-00` or a regenerated
  cache-local fixture batch.
- `ruff`, targeted pytest, `git diff --check`, and plan drift guard pass.

## Training Corpus Contract

Each training case must be local, bounded, and reproducible:

- Store synthetic or redacted fixtures in the repo only when safe.
- Store private real-card references only in user-scoped runtime manifests.
- Record feature vector, deterministic decision, App Intelligence review if
  used, accepted correction, and new/updated rule.
- Link each rule change to a failing-before/passing-after test.

Minimum labels:

- `not_business_card`
- `business_card_qr_side`
- `business_card_text_side`
- `business_card_backside`
- `orientation_wrong`
- `crop_bad`
- `crop_good`
- `side_pair_confirmed`
- `side_pair_rejected`
- `app_intelligence_needed`
- `app_intelligence_not_needed`

## Closeout Criteria

This plan is complete when:

- The Gallagher review cases can be processed by agent loop without asking the
  operator to classify the same issues again.
- QR evidence, orientation, crop quality, and side-pair proposals appear in the
  review surface.
- At least one deterministic rule or fixture is added from the Gallagher cases.
- Route readiness remains blocked until a paired text-bearing side produces a
  reviewed contact with lookup prerequisites.
- All evidence remains dry-run/no-live with writes/network counters at zero.

## Next Slice

Start with Milestone 1 plus the smallest part of Milestone 6:

- Implement QR evidence artifacts and review-surface exposure.
- Add `agent-review-loop --dry-run` planning output that can recognize QR-only
  side/crop/orientation blockers but does not apply changes yet.
- Validate on synthetic QR fixtures and the focused Gallagher run.

## Slice 1 Closeout | 2026-06-23

Implemented:

- Added deterministic local QR evidence extraction for source images and
  candidate crops using OpenCV when available.
- Wrote `qr_evidence.json` for QR-found, QR-not-found, and decoder-unavailable
  cases with writes/network counters at zero.
- Projected QR evidence into the contact store and exposed redacted QR summaries
  in review bundles, review matrices, and contact review surface rows.
- Added `runs agent-review-loop <run-id> --limit <n> --dry-run --json` as a
  no-live planner that identifies QR-bearing review jobs, planned App
  Intelligence request types, training candidates, and blocked contacts.
- Kept `--apply-safe` as a no-op boundary until deterministic
  orientation/crop/pair handlers have acceptance tests.

Validation:

- `.venv/bin/python -m pytest tests/test_qr_evidence.py tests/test_cli_surfaces.py::test_cli_runs_agent_review_loop_plans_qr_side_followup tests/test_preclassifier.py::test_orchestrator_records_multi_card_candidate_manifest -q`
  passed with 4 tests.
- `.venv/bin/python -m ruff check src/business_card_watchdog/qr_evidence.py src/business_card_watchdog/orchestrator.py src/business_card_watchdog/service.py src/business_card_watchdog/cli.py tests/test_qr_evidence.py tests/test_cli_surfaces.py`
  passed.
- Focused scanner run `2026-06-23T02-27-30+00-00` from the cache-local
  2026-06-20 scanner sequence completed dry-run with 14 jobs and 2
  `needs_review` jobs.
- The focused scanner run wrote `qr_evidence` artifacts for all jobs; the agent
  loop planned 2 QR follow-ups, including one reviewable QR-detected Gallagher
  side with `decode_count = 0`.
- `runs agent-review-loop 2026-06-23T02-27-30+00-00 --limit 14 --dry-run --json`
  reported `planned_action_count = 2`, `app_intelligence_request_count = 2`,
  `writes_attempted = 0`, and `network_calls_made = 0`.

Remaining:

- Milestone 4 scanner front/back pairing.
- Milestone 5 concrete App Intelligence request artifact creation and training
  fixture promotion.
- Milestone 6 `--apply-safe` deterministic handlers once each handler has
  passing tests.

## Slice 3 Closeout | 2026-06-23

Implemented:

- Added deterministic `crop_quality.json` artifacts for source pages with and
  without candidate crops.
- Added crop metrics for boundary coverage, text density, QR density, blank
  fraction, clipping risk, edge margin, aspect ratio, and text-line count.
- Added `recrop_proposals.json` artifacts with expanded source-page bounds for
  bad or QR-only crops.
- Projected crop quality and recrop proposal artifacts into the contact store.
- Exposed redacted crop and recrop summaries in review bundles, review matrices,
  contact review surfaces, and CLI text output.
- Updated the agent review loop to plan crop-quality inspection and bounded
  `assess_crop_quality` request candidates when deterministic crop evidence is
  bad or QR-only.

Validation:

- `.venv/bin/python -m pytest tests/test_crop_quality.py tests/test_orientation_evidence.py tests/test_qr_evidence.py tests/test_cli_surfaces.py::test_cli_runs_agent_review_loop_plans_qr_side_followup tests/test_preclassifier.py::test_orchestrator_records_multi_card_candidate_manifest -q`
  passed with 10 tests.
- `.venv/bin/python -m ruff check src/business_card_watchdog/crop_quality.py src/business_card_watchdog/orchestrator.py src/business_card_watchdog/service.py src/business_card_watchdog/cli.py src/business_card_watchdog/contact_store.py tests/test_crop_quality.py tests/test_preclassifier.py`
  passed.
- Focused scanner run `2026-06-23T02-44-36+00-00` from the cache-local
  2026-06-20 scanner sequence completed dry-run with 14 jobs.
- The focused scanner run wrote 14 `crop_quality` artifacts and 14
  `recrop_proposals` artifacts, detected 2 bad crops, and produced 2 recrop
  proposals.
- `runs agent-review-loop 2026-06-23T02-44-36+00-00 --limit 14 --dry-run --json`
  reported `planned_action_count = 4`, `app_intelligence_request_count = 7`,
  request types `assess_crop_quality`, `pair_card_sides`, and
  `resolve_orientation`, `writes_attempted = 0`, and `network_calls_made = 0`.

Remaining:

- Milestone 4 scanner front/back pairing.
- Milestone 5 concrete App Intelligence request artifact creation and training
  fixture promotion.
- Milestone 6 `--apply-safe` deterministic handlers once each handler has
  passing tests.

## Slice 2 Closeout | 2026-06-23

Implemented:

- Added deterministic local orientation scoring for 0, 90, 180, and 270 degree
  rotations using OpenCV image heuristics.
- Wrote `orientation_evidence.json` for every processed job, including
  per-image scores, selected rotation, confidence, and normalized derivative
  paths when confidence is high.
- Preserved 180-degree corrections as review-only for this slice because they
  need stronger OCR/upright-text evidence before safe automatic normalization.
- Projected `orientation_evidence` into the contact store and exposed redacted
  orientation summaries in review bundles, review matrices, contact review
  surfaces, and CLI text output.
- Updated the agent review loop to plan orientation-normalization inspection
  when a normalized derivative exists and to create bounded
  `resolve_orientation` request candidates only for reviewable, QR-bearing, or
  accepted-evidence jobs.

Validation:

- `.venv/bin/python -m pytest tests/test_orientation_evidence.py tests/test_qr_evidence.py tests/test_cli_surfaces.py::test_cli_runs_agent_review_loop_plans_qr_side_followup tests/test_preclassifier.py::test_orchestrator_records_multi_card_candidate_manifest -q`
  passed with 6 tests.
- `.venv/bin/python -m ruff check src/business_card_watchdog/orientation_evidence.py src/business_card_watchdog/orchestrator.py src/business_card_watchdog/service.py src/business_card_watchdog/cli.py src/business_card_watchdog/contact_store.py tests/test_orientation_evidence.py tests/test_qr_evidence.py tests/test_cli_surfaces.py tests/test_preclassifier.py`
  passed.
- Focused scanner run `2026-06-23T02-35-26+00-00` from the cache-local
  2026-06-20 scanner sequence completed dry-run with 14 jobs.
- The focused scanner run wrote 14 `orientation_evidence` artifacts:
  2 already normalized and 12 requiring App Intelligence review, with no
  automatic 180-degree derivatives.
- `runs agent-review-loop 2026-06-23T02-35-26+00-00 --limit 14 --dry-run --json`
  reported `planned_action_count = 2`, `app_intelligence_request_count = 5`,
  request types `pair_card_sides` and `resolve_orientation`,
  `writes_attempted = 0`, and `network_calls_made = 0`.

Remaining:

- Milestone 4 scanner front/back pairing.
- Milestone 5 concrete App Intelligence request artifact creation and training
  fixture promotion.
- Milestone 6 `--apply-safe` deterministic handlers once each handler has
  passing tests.

## Slice 4 Closeout | 2026-06-23

Implemented:

- Added deterministic `side_pair_graph.json` as a run-level scanner sequence
  graph.
- Graph nodes include page order, side labels, QR presence, crop state, and
  orientation state.
- Graph edges include adjacent-page evidence, side-label complement evidence,
  QR-side adjacency evidence, blank-back candidates, blocked review edges, and
  routing-disabled pair-review candidates.
- Preserved existing `card_side_pair_proposals.json` behavior for stricter
  front/back review queue proposals.
- Exposed a redacted side-pair graph summary in review bundles and the agent
  review loop.
- Updated the agent review loop to plan `inspect_side_pair_graph` when graph
  pair candidates exist and to include graph evidence in `pair_card_sides`
  request candidates.

Validation:

- `.venv/bin/python -m pytest tests/test_card_sides.py tests/test_crop_quality.py tests/test_orientation_evidence.py tests/test_qr_evidence.py tests/test_cli_surfaces.py::test_cli_runs_agent_review_loop_plans_qr_side_followup tests/test_preclassifier.py::test_orchestrator_records_multi_card_candidate_manifest -q`
  passed with 22 tests.
- `.venv/bin/python -m ruff check src/business_card_watchdog/card_sides.py src/business_card_watchdog/orchestrator.py src/business_card_watchdog/service.py src/business_card_watchdog/contact_store.py tests/test_card_sides.py`
  passed.
- Focused scanner run `2026-06-23T02-50-18+00-00` from the cache-local
  2026-06-20 scanner sequence completed dry-run with 14 jobs.
- The focused scanner run wrote `side_pair_graph.json` with 14 nodes, 6
  adjacent edges, 2 `pair_review_required` edges, 1 blank-back edge, and 3
  blocked review edges.
- `runs agent-review-loop 2026-06-23T02-50-18+00-00 --limit 14 --dry-run --json`
  reported `planned_action_count = 5`, `app_intelligence_request_count = 7`,
  graph `pair_proposal_count = 2`, `writes_attempted = 0`, and
  `network_calls_made = 0`.

Remaining:

- Milestone 5 concrete App Intelligence request artifact creation and training
  fixture promotion.
- Milestone 6 `--apply-safe` deterministic handlers once each handler has
  passing tests.

## Slice 5 Closeout | 2026-06-23

Implemented:

- Added durable evidence-only `app_intelligence_review_request` artifacts for
  bounded agent-loop escalation requests.
- Added `agent_training_candidate` artifacts for accepted-review evidence that
  should become deterministic fixtures or rule tests before safe apply.
- Added stable request IDs, deterministic evidence, candidate choices, stop
  rules, allowed response schemas, forbidden action lists, and response-import
  contracts to App Intelligence request payloads.
- Made `--no-write` agent-loop output keep the same schema while writing no
  request or training artifacts.
- Projected `app_intelligence_review_request` and `agent_training_candidate`
  artifact kinds into the contact store allowlist.
- Strengthened the contact-review evidence test to prove accepted App
  Intelligence evidence does not mutate contact state, add route decisions, or
  add sink attempts by itself.

Validation:

- `.venv/bin/python -m pytest tests/test_cli_surfaces.py::test_cli_runs_agent_review_loop_plans_qr_side_followup tests/test_contact_store.py::test_contact_review_recommendations_are_host_decided -q`
  passed with 2 tests.
- `.venv/bin/python -m ruff check src/business_card_watchdog/service.py src/business_card_watchdog/contact_store.py tests/test_cli_surfaces.py tests/test_contact_store.py`
  passed.
- `runs agent-review-loop 2026-06-23T02-50-18+00-00 --limit 14 --dry-run --json`
  wrote 7 private request artifacts for the focused scanner run, planned 5
  actions, and reported `writes_attempted = 0` and `network_calls_made = 0`.
- A sampled request artifact had schema
  `business-card-watchdog.app-intelligence-review-request.v1`, answer shape
  `evidence_only_no_state_transition`, `direct_route_ready_transition_allowed =
  false`, and forbidden actions for routing, sink write/readback, enrichment,
  and selected-target creation.

Remaining:

- Milestone 6 `--apply-safe` deterministic handlers once each handler has
  passing tests.

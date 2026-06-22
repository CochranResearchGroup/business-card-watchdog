# Plan 0060 | Product Development Milestone Plan

State: OPEN
Date: 2026-06-20

## Purpose

Define the next product-development arc from the current dry-run, reviewable
control plane to the intended local service:

- Watch configured folders for card images.
- Accept scanner outputs, including image files and PDF documents, without
  treating PDFs as already-supported image inputs.
- Detect business cards deterministically, with optional stochastic review.
- Crop card images and OCR normalized contact data.
- Represent card sides explicitly so front/back scans can contribute to one
  reviewed contact when information is split across both sides.
- Pair card backs with fronts using OCR-assisted and deterministic contextual
  evidence; scanner adjacency is useful evidence but not sufficient by itself.
- Quality-check extraction and routing with App Intelligence evidence while
  preserving host-owned state transitions.
- Store contact rows, crop images, enrichment state, and sink attempts in a
  user-scoped database.
- Optionally enrich contacts with Apollo, People Data Labs, and/or web search.
- Sink contacts to the configured `ecochran76` Google Workspace account.
- Route Providence-context contacts to SoyLei or SABER through Odollo when
  explicit policy and readiness allow.
- Expose a review surface for contact rows, enrichment, routing, and sink
  status.

This plan is an umbrella. Each milestone below is intentionally shaped so it
can become a standalone `/goal` with its own implementation plan, tests, and
closeout evidence.

## Baseline

- Current pushed checkpoint: `704da0c` (`Complete plan 0059 review route extraction`).
- The repo already has watched-folder service mechanics, dry-run orchestration,
  ledgers, review bundles, enrichment request/review flows, CLI/API/MCP
  surfaces, sink readiness gates, selected-target gates, and service refactor
  guardrails.
- The repo does not yet have a first-class user-scoped contact database.
- Broad live writes remain blocked. Live behavior must proceed one run, one job,
  and one sink at a time after explicit readiness and write/readback proof.

## Global Constraints

- Keep product code in this repo.
- Keep config under `~/.config/business-card-watchdog/`.
- Keep runtime data under `~/.local/share/business-card-watchdog/`.
- Keep cache/transient watcher state under `~/.cache/business-card-watchdog/`.
- Do not commit tenant secrets, connector credentials, private card images, raw
  OCR dumps from real cards, or live sink logs.
- Treat OCR/model/agent/App Intelligence output as evidence. The host
  orchestrator owns phase, retry, branch, approval, sink, rollback, and stop
  rules.
- Default new sink and enrichment behavior to dry-run or preview-only.
- Keep mutations to the same contact/person sequential.
- Every milestone must preserve replayable artifacts or provide a migration
  path from the current artifact-ledger model.

## Milestones

### Milestone 1 | User-Scoped Contact Store

Status: BASELINE_COMPLETE via Plan 0063. Follow-on work should start at
Milestone 2 unless it needs to expand the contact store schema.

Goal-compatible objective:

Implement a user-scoped contact store for extracted business-card contacts,
card crop assets, provenance, enrichment state, routing state, and sink attempts
without changing live sink behavior.

Scope:

- Choose and document the local database backend and file layout under
  `~/.local/share/business-card-watchdog/`.
- Add schema and migrations for contacts, card images/crops, extraction
  attempts, enrichment attempts, routing decisions, sink attempts, and external
  tenant bindings.
- Add a repository/service layer with deterministic inserts, updates, and
  lookup APIs.
- Preserve current run ledgers and artifacts as replay evidence.
- Add CLI/API/MCP read-only inspection for contact rows if it is small enough
  for the slice; otherwise leave it as the first follow-on.

Non-goals:

- No live Google/Odoo/Odollo writes.
- No paid enrichment calls.
- No private image processing beyond existing operator-approved flows.

Acceptance criteria:

- Fresh user data directory can initialize the database.
- Existing fixture dry-run artifacts can be projected into contact rows.
- Contact rows retain source run/job IDs, extraction provenance, and asset
  references.
- The database can be backed up or deleted without affecting repo files.

Validation:

- Unit tests for migrations and repository operations.
- Fixture-backed projection test from an existing dry-run artifact.
- CLI/API/MCP read-only smoke if surfaces are included.
- `ruff`, targeted tests, `git diff --check`, and plan drift guard.

### Milestone 2 | Artifact-To-Database Projection

Status: BASELINE_COMPLETE via Plan 0064. Follow-on work should start at
Milestone 3 unless projection schema needs to expand for scanner/card-side
artifacts.

Goal-compatible objective:

Wire the current dry-run batch pipeline so every reviewed extraction creates or
updates user-scoped contact rows while keeping ledger artifacts authoritative
for replay.

Scope:

- Add an idempotent projection step after extraction/review bundle generation.
- Record normalized fields, uncertainty, crop references, duplicate candidates,
  enrichment requests, and route readiness in the contact store.
- Add repair/replay command for projecting an existing run into the database.
- Add drift checks between run artifacts and database projection summaries.

Non-goals:

- No new OCR engine behavior.
- No live sink writes.
- No automatic duplicate merge beyond recording candidates.

Acceptance criteria:

- Re-running projection for the same run is idempotent.
- Projection failure leaves the run ledger readable and retryable.
- Contact rows can be traced back to source image, crop, OCR attempt, and review
  artifact.

Validation:

- Projection idempotency tests.
- Fixture run replay test.
- Failure/retry test for partial projection.
- Existing service/API/CLI/MCP tests remain green.

### Milestone 3 | Scanner Intake, Card Sides, And OCR Quality Loop

Status: IN_PROGRESS. Scanner document-intake foundation complete via Plan 0065;
OCR side classification and baseline front/back pair proposals complete via
Plan 0066; reviewed side-pair merge complete via Plan 0067; deterministic
extraction quality gates complete via Plan 0068; reviewed child contacts from
multi-card images project as distinct contact rows via Plan 0069. Regular
double-sided scanner pairing has been hardened with an OCR/contextual pairing
graph via Plan 0084: adjacency is a weighted clue only, near-adjacent candidates
can be scored, same-stem image captures can pair outside PDFs, and missing or
generic backs stay reviewable instead of being merged. Remaining scanner-side
work should continue with broader App Intelligence review-state hardening or
real-corpus pilot evidence from the configured scanner folder.

Goal-compatible objective:

Harden the scanner/image-processing path so watched-folder images and supported
scanner documents produce explicit source pages, card-side candidates, crop
assets, OCR attempts, and quality gates before contact rows become route-ready.

Scope:

- Add a document intake boundary for scanner PDFs that rasterizes pages into
  page images under runtime artifacts before normal card detection.
- Keep PDF support separate from `is_supported_image`; PDFs are document
  sources that produce page-image child work items, not image inputs.
- Formalize deterministic preclassification and card-candidate metadata.
- Store candidate boxes, chosen crop, rejected crop reasons, and crop quality
  metrics.
- Add a card-side model with `front`, `back`, `blank`, and `unknown` side
  labels.
- Add per-page and per-crop OCR text artifacts before side pairing, with OCR
  treated as evidence rather than control authority.
- Add an OCR-assisted side classifier using deterministic contextual clues such
  as name/title/email density, organization/domain overlap, phone/address
  fragments, QR/URL/domain hints, back-of-card disclaimer/social/address-only
  patterns, and blank/near-blank detection.
- Add a scored front/back pair-candidate graph instead of a sequence-only
  matcher. Evidence should include scanner page adjacency, same PDF/session,
  same-stem image pairs, timestamp adjacency, OCR token overlap, domain/company
  overlap, visual/crop similarity, and negative evidence such as conflicting
  person/company/domain signals.
- The pair-candidate graph must evaluate all plausible candidates within a
  bounded scanner session window, not only adjacent page pairs. Adjacency is a
  weighted feature; it is not sufficient pair evidence.
- Treat scanner page adjacency as a strong but non-authoritative hint. Some
  scanner workflows may place back before front, and some may drop blank backs,
  so pairing must allow near-adjacent candidates and explicit blank-side gaps.
- For scanner sequences, score both `front -> back` and `back -> front`
  adjacency edges. Page order may decide candidate priority but must not decide
  correctness without OCR/context evidence.
- Use deterministic OCR and contextual clues as required pair evidence:
  shared company/domain/address/phone fragments, complementary front/back field
  density, QR/URL/social fragments, and absence of conflicting name/company
  signals.
- Treat missing blank backs as an expected scanner behavior. A high-confidence
  front may stand alone when the adjacent page is absent or classified blank,
  but a non-blank back must remain unmerged until paired or reviewed.
- Preserve unpaired non-blank backs as reviewable side candidates with their
  own OCR/context evidence, so an operator can attach them to the correct front
  later rather than losing backside-only fields.
- Allow optional stochastic/app-intelligence review to rank or explain
  ambiguous pairs, but keep pair acceptance, merge, and route-readiness as
  host-owned review transitions.
- Store pair proposals with confidence, evidence, and blocked/ambiguous reasons
  for review.
- Merge reviewed front/back OCR fields into one contact candidate only through
  explicit host-owned review state.
- Normalize the handoff to the `business-card-to-contact` skill.
- Add multi-card image behavior as explicit candidates rather than implicit
  single-image extraction.
- Add low-confidence review states for crop and OCR quality.

Non-goals:

- No new live sinks.
- No paid enrichment.
- No irreversible mutation of source images.
- No automatic front/back merge without review evidence.
- No sequence-only assumption that page N and page N+1 are a true front/back
  pair.

Acceptance criteria:

- Fixture images produce stable candidate/crop metadata.
- Fixture PDFs produce stable page-image artifacts and page lineage.
- OCR extraction records quality state and review requirements.
- Multi-card fixtures produce separate candidate/contact rows.
- Scanner PDF fixtures produce OCR-backed side classifications for `front`,
  `back`, `blank`, and `unknown`.
- Pair proposals include scored evidence and negative evidence; ambiguous pairs
  are blocked for review rather than merged.
- Front/back fixtures can produce one reviewed contact with provenance for each
  field showing whether it came from the front side, back side, or both.

Validation:

- Synthetic image fixture tests for no-card, one-card, and multi-card cases.
- Synthetic PDF fixture tests for one-page and two-page scanner documents.
- Front/back pairing tests for consecutive pages, reversed front/back order,
  dropped blank backs, same-stem image pairs, and conflicting OCR evidence.
- Scanner sequence tests proving adjacency alone cannot merge a pair, reversed
  page order can still propose a pair, and dropped blank backs do not block a
  complete front-side contact from review progression.
- Pair-graph tests proving a non-adjacent but OCR-compatible front/back pair can
  outrank an adjacent conflicting pair, and same-stem/timestamp-adjacent image
  captures can produce proposals outside PDFs.
- OCR/context clue tests for name/title/email density, company/domain overlap,
  address-only backs, QR/URL hints, and blank/near-blank pages.
- Crop asset existence and checksum tests.
- OCR adapter contract tests using fixture output.

### Milestone 4 | App Intelligence Quality Review State

Status: COMPLETE_FOR_CURRENT_SCOPE. Contact-row App Intelligence review
recommendations and host-owned accept/reject decisions are database-backed via
Plan 0070. Bounded safe-loop behavior over contact review states is complete via
Plan 0071. API/MCP parity for recommendation, listing, decision, and safe-loop
surfaces is complete via Plan 0072. Continue with Milestone 5 enrichment
provider contracts.

Goal-compatible objective:

Make App Intelligence quality checks a first-class review state over contact
rows while preserving host-owned decisions and deterministic stop rules.

Scope:

- Add review states for extraction quality, duplicate confidence, enrichment
  need, route readiness, and sink readiness.
- Store App Intelligence recommendations as evidence with provenance and
  confidence, not as direct state transitions.
- Add bounded safe-loop commands over database-backed contact rows.
- Add audit trails for accepted/rejected recommendations.

Non-goals:

- No autonomous sink writes.
- No unbounded agent loop.
- No model output as sole authority.

Acceptance criteria:

- Contact rows expose pending/blocked/ready states with explainable reasons.
- Accepted recommendations mutate state through host-owned commands.
- Rejected recommendations remain visible as evidence.

Validation:

- State-machine unit tests.
- Bounded safe-loop fixture tests.
- CLI/API/MCP review parity tests.

### Milestone 5 | Enrichment Provider Contracts

Status: COMPLETE_FOR_CURRENT_SCOPE. Public-web and Apollo preview/provider-result
contracts pre-existed this milestone. People Data Labs provider config,
readiness, preview request/handoff, explicit result import normalization, and
API/CLI/MCP provider selection are complete via Plan 0073. Contact-store
enrichment review status/provenance projection is complete via Plan 0074.
Continue with Milestone 6 routing policy and GWS default sink.

Goal-compatible objective:

Add explicit provider contracts for web-search, Apollo, and People Data Labs
enrichment that can run in preview/dry-run mode and store provenance before any
paid or external call is enabled.

Scope:

- Define provider request/response schemas.
- Add provider readiness checks and credential redaction.
- Store enrichment attempts, results, provenance, cost/risk metadata, and
  review status in the contact store.
- Support preview-only packets for each provider.
- Gate paid/API calls behind operator approval and config readiness.

Non-goals:

- No default paid API execution.
- No enrichment result auto-merge without review.
- No credential storage in git or run artifacts.

Acceptance criteria:

- Provider packets can be generated without live calls.
- Redacted readiness reports identify missing config safely.
- Reviewed enrichment results can update normalized contact fields with
  provenance.

Validation:

- Schema and redaction tests.
- Preview packet tests for each provider.
- Review-merge provenance tests.

### Milestone 6 | Routing Policy And GWS Default Sink

Status: COMPLETE for the no-live GWS routing scope. Generated user config now
installs Google Contacts as the default dry-run sink with
`google_contacts_profile = "ecochran76"` and apply disabled via Plan 0075.
No-write sink and lookup plans surface the configured GWS target profile.
Contact-store routing decisions persist selected sink state and configured
target metadata via Plan 0076. Contact-scoped route-selection approval and
command-copy packets now cover the database-backed contact row flow via Plan
0077 while preserving selected-target gates and selected-live-target creation
as an explicit operator action.

Goal-compatible objective:

Install a deterministic routing profile that always targets the `ecochran76`
Google Workspace contact sink by default while keeping writes dry-run until
explicit live pilot approval.

Scope:

- Add user-config routing policy for default GWS sink.
- Add readiness checks that prove the configured Google account and sink target.
- Store route decisions and selected sink state in the contact store.
- Add command-copy and approval packets for GWS route selection.
- Preserve selected-target gates and one-job pilot boundary.

Non-goals:

- No broad live write enablement.
- No SoyLei/SABER routing in this milestone except as deferred route reasons.

Acceptance criteria:

- Route-ready contacts select the configured GWS sink by default.
- Missing/ambiguous account readiness blocks live approval.
- Dry-run packets show exactly what would be written.

Validation:

- Routing policy tests.
- Google readiness redaction tests.
- No-write selected-target packet tests.

### Milestone 7 | Odollo SoyLei And SABER Routing

Status: COMPLETE_FOR_CURRENT_SCOPE. Providence-context route rules can now
select the `odoo` sink with route-scoped Odollo tenant targets such as
`soylei-prod` and `saber-prod` via Plan 0078. Dry-run sink plans, sink
payloads, and duplicate lookup plans now carry the selected tenant target while
preserving `sink.odollo_tenant` as a fallback. Read-only tenant readiness
reports and duplicate lookup gate blockers are now present in Odoo lookup plans
via Plan 0079. Tenant route candidate state, selected target tenant references,
and readiness blockers now persist into the contact store via Plan 0080.
Selected-target/write-readback pilot boundaries now use the route-selected
tenant and block Odollo write pilots until selected lookup and duplicate
evidence are clear via Plan 0081. Continue with Milestone 8 contact review
surface work.

Goal-compatible objective:

Add deterministic Providence-context routing to SoyLei or SABER through Odollo
tenant profiles with read-only readiness before any write pilot.

Scope:

- Define routing rules and config for SoyLei and SABER tenant contexts.
- Add read-only tenant readiness and duplicate lookup packets.
- Store tenant route candidates, readiness blockers, and selected target
  references in the contact store.
- Add one-job, one-sink write/readback pilot boundaries for Odollo routes.

Non-goals:

- No automatic tenant creation.
- No broad live Odollo writes.
- No write behavior without read-only duplicate evidence first.

Acceptance criteria:

- Contacts with matching context can become SoyLei/SABER route candidates.
- Readiness reports distinguish missing config, blocked tenant, duplicate risk,
  and pilot-ready state.
- Write/readback pilot remains explicitly operator selected.

Validation:

- Routing-rule fixture tests.
- Tenant readiness tests with redacted config.
- Duplicate lookup packet tests.
- No-live selected-target gate tests.

### Milestone 8 | Contact Review Surface

Status: COMPLETE_FOR_CURRENT_SCOPE. Database-backed contact review surface
summaries and audited normalized field-correction mutations are available
through service, API, CLI, and MCP via Plan 0082. Audited route override
mutations are available through service, API, CLI, and MCP via Plan 0083.
Audited crop decision mutations are available through service, API, CLI, and MCP
via Plan 0085. Audited enrichment merge mutations are available through service,
API, CLI, and MCP via Plan 0086. Audited sink approval state mutations are
available through service, API, CLI, and MCP via Plan 0087. Plan 0088 closes the
local HTML decision by keeping Milestone 8 to the no-auth service/API/CLI/MCP
review scope; a richer database-backed contact HTML UI should be opened as a
separate UI plan if needed. Continue with Milestone 9 operator-selected live
pilot work.

Goal-compatible objective:

Expose a database-backed review surface where contact rows, card crops,
extraction quality, enrichment, route decisions, and sink attempts can be
reviewed and mutated through host-owned actions.

Scope:

- Add contact-row list/detail APIs.
- Add CLI and MCP parity for core review actions.
- Add an HTML or local review surface if it can be delivered without widening
  auth/network scope; otherwise keep the milestone API/CLI/MCP only and open a
  separate UI plan.
- Add mutation commands for accept/reject crop, accept/reject field correction,
  enrichment merge, route override, and sink approval state.

Non-goals:

- No non-loopback hosted API.
- No live sink writes from UI without existing approval gates.
- No private image exposure outside local operator surfaces.

Acceptance criteria:

- Operator can review and mutate contact-row state without editing artifacts by
  hand.
- Every mutation is audited with operator, timestamp, previous value, and new
  value.
- Review surface links back to source artifacts and crop assets.

Validation:

- API/CLI/MCP parity tests.
- Mutation audit tests.
- Local review fixture smoke.

### Milestone 9 | Operator-Selected Live Pilot

Status: READY_FOR_OPERATOR_SELECTION. Plan 0089 audited the current no-live
runtime state: runtime readiness is green and the contact store is initialized,
but there are no contact rows and no live-target candidates. Generic
continuation must stop before processing private watched-folder backlog or
creating `selected_live_target.json`; the next step requires an operator-selected
run/contact/sink or an explicit safe dry-run batch selection to project into the
contact store.

Goal-compatible objective:

Run the first live pilot for one run, one reviewed contact, and one selected
sink with authenticated write/readback proof, then record the production
boundary for repeating the process safely.

Scope:

- Use the existing Plan 0009 boundary as the live pilot authority.
- Select one route-ready contact from the database-backed review surface.
- Execute one approved GWS write/readback pilot first.
- Only after GWS proof, open separate Odollo SoyLei/SABER pilot goals.
- Record redacted live evidence in runtime artifacts and repo docs without
  leaking private contact data.

Non-goals:

- No batch live writes.
- No multi-sink live fanout.
- No live writes without operator-selected target approval.

Acceptance criteria:

- One selected contact is written to the approved sink.
- Readback confirms the external ID/fingerprint expected by the adapter.
- Contact store records sink attempt, success/failure, external binding, and
  redacted evidence path.
- Rollback/remediation instructions are documented.

Validation:

- Preflight readiness command output.
- Live write command output captured in redacted runtime evidence.
- Readback command output captured in redacted runtime evidence.
- Targeted tests plus manual live-pilot checklist closeout.

## Execution Order

1. Milestone 1: User-scoped contact store.
2. Milestone 2: Artifact-to-database projection.
3. Milestone 3: Scanner intake, card sides, and OCR quality loop.
4. Milestone 4: App Intelligence review state.
5. Milestone 5: Enrichment provider contracts.
6. Milestone 6: GWS default routing policy.
7. Milestone 8: Contact review surface.
8. Milestone 9: GWS live pilot.
9. Milestone 7: Odollo SoyLei/SABER routing and pilots.

Milestone 7 can move earlier if Providence routing becomes the immediate
operator need, but it should not precede the contact store and projection work.

## First Recommended `/goal`

Implement Milestone 1 from Plan 0060: add the user-scoped contact store under
`~/.local/share/business-card-watchdog/`, including schema, migrations,
repository APIs, fixture-backed projection of existing dry-run artifacts, and
tests. Do not add live sink writes, paid enrichment calls, or private image
processing.

## Scanner Directory Note

The planned `SyncThing/Documents/Scanner` watcher input should be added through
user config only after a no-processing backlog preflight confirms the path and
after PDF scanner support has a dry-run fixture proof. If the directory already
contains PDFs, adding it before Milestone 3 would not process those PDFs because
the current watcher admits image suffixes only.

## Closeout Requirements For Each Milestone

- Create or update a bounded implementation plan under `docs/dev/plans/`.
- Update `ROADMAP.md` and `RUNBOOK.md` with the milestone result.
- Record concrete validation evidence.
- Distinguish dry-run, preview, read-only, and live-write evidence.
- Keep the next milestone independently executable through `/goal`.

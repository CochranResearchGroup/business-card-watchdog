# Plan 0005 | Review, Routing, Normalization, Enrichment, And Dedupe Hardening

State: IN_PROGRESS
Product authority: `PRODUCT_SPEC.md`
Predecessor:

- `docs/dev/plans/0004-2026-06-13-review-normalization-enrichment-dedupe-sinks.md`

Planning inputs:

- Operator discussion on 2026-06-13 about review surfaces, GWS/Odollo sinks, normalization, enrichment, and dedupe.
- Explicit decision that API-based enrichment usually has cost and must be explicitly requested.
- Explicit decision that web-search enrichment can be useful but still belongs behind an explicit enrichment request/run policy.
- Explicit decision that reusable Odollo enrichment/contact tools may be copied or adapted where they fit this repo boundary.

## Scope

Turn the current artifact-backed review, enrichment, duplicate, and sink-pilot surfaces into the next operator-usable workflow for arbitrary-size business-card batches.

This plan focuses on the control plane around the contact data, not on making unrestricted live writes:

- review imported cards and extracted contacts at batch scale
- normalize card-observed contact data into stable canonical fields
- enrich only when requested, with a hard distinction between free/local/web-search work and API-backed paid providers
- dedupe before routing and again before any sink write pilot
- route reviewed contacts into Google Workspace Contacts and/or Odollo/Odoo tenants based on explicit policy
- make every phase inspectable through CLI, API, MCP, and agent-loop next actions

## Current Baseline

Implemented in earlier plans:

- deterministic image preclassification before OCR/App Intelligence
- per-run/job ledgers and artifacts
- `contact_candidate.json`, `reviewed_contact.json`, `duplicate_assessment.json`, `sink_plan.json`, `sink_lookup_result.json`, `sink_apply_decision.json`, `sink_write_pilot.json`, `sink_readback_pilot.json`, and `sink_apply_pilot_report.json`
- review queue, run summary, route refresh, review bundle, and next-action readback surfaces
- fixture-backed public-web enrichment request/result scaffolding
- explicit paid API enrichment readiness gate
- Google Contacts and Odollo/Odoo sink planning, lookup, write-pilot, readback-pilot, and pilot-report boundaries
- safe agent-loop executor that can advance zero-write steps and stops before paid enrichment or live write pilots

Important gaps:

- no ergonomic review UI/workbook for imported card/contact correction
- no batch-level reviewer workflow for duplicate conflicts and sink approvals
- no enrichment provider adapters copied/adapted from Odollo yet
- no local policy object that explains why a contact routes to GWS, Odollo, both, or neither
- no merged enrichment review flow that records accepted/rejected suggestions
- no durable duplicate-resolution index that survives future batches as operator-approved identity knowledge
- no "ready for pilot" report that combines review, dedupe, enrichment, route, sink lookup, and apply-pilot status across the whole run

## Product Decisions For This Plan

Review:

- The first review surface is generated and local: static HTML plus JSON artifacts, with a spreadsheet/workbook export as a follow-on once the schema stabilizes.
- Review rows must show the card image reference, extracted contact, normalized contact, duplicate status, enrichment proposals, routing explanation, sink lookup status, and sink pilot state.
- Review actions are append-only decisions. They update derived artifacts, but they do not erase raw OCR/App Intelligence evidence.

Sinks:

- GWS Contacts and Odollo/Odoo are independent sink profiles. A contact may route to GWS, Odollo/Odoo, both, neither, or `needs_review`.
- Route eligibility is not write approval. Eligibility says "this contact belongs in this sink"; apply approval says "this specific write pilot is allowed."
- Sink adapters must support lookup, write-pilot, readback-pilot, and pilot-report phases. Live writes remain one-job, one-sink, explicit actions until later policy changes.

Normalization:

- The canonical contact model is the center of the system. Review, dedupe, routing, enrichment merge, and sink payloads should consume canonical fields, not raw OCR fields.
- Observed card data, normalized values, reviewer corrections, enrichment values, downstream lookup values, and sink readbacks must keep separate provenance.
- Ambiguous normalization creates warnings for review instead of silently guessing.

Enrichment:

- Local deterministic enrichment may run as part of safe execution only when it uses already-present artifacts and makes no network/API calls.
- Public-web enrichment requires an explicit enrichment request or run-level policy because it performs network/search work.
- Paid API enrichment requires an explicit request, enabled provider config, available key in `~/credentials/API-keys.env`, and budget/count limits. Generic `continue` or safe agent-loop execution must never run it.
- Enrichment results are suggestions until reviewed. Accepted values are provenance-marked and may be included or excluded per sink policy.

Dedupe:

- Strong duplicate evidence, such as exact normalized email/phone or downstream resource match, blocks write pilots until reviewed or resolved.
- Weak evidence, such as same company/domain or fuzzy person/company match, creates review work but does not merge people automatically.
- Reviewer-approved duplicate resolutions become durable identity evidence for future runs.

## Odollo Reuse Targets

The first implementation pass should inspect and adapt these Odollo assets before inventing new provider logic:

- `/home/ecochran76/workspace.local/odollo/src/odollo/core/public_web_enrichment.py`
- `/home/ecochran76/workspace.local/odollo/src/odollo/adapters/apollo.py`
- `/home/ecochran76/workspace.local/odollo/src/odollo/core/apollo_intake.py`
- `/home/ecochran76/workspace.local/odollo/src/odollo/core/apollo_intake_review.py`
- `/home/ecochran76/workspace.local/odollo/src/odollo/core/apollo_catalog.py`
- `/home/ecochran76/workspace.local/odollo/src/odollo/core/contact_points.py`
- `/home/ecochran76/workspace.local/odollo/skills/business-card-to-contact/scripts/build_apollo_enrichment_stub.py`
- `/home/ecochran76/workspace.local/odollo/skills/business-card-to-contact/references/merge-policy.md`
- `/home/ecochran76/workspace.local/odollo/skills/business-card-to-contact/references/idempotency-contracts.md`

Reuse boundary:

- Copy/adapt small provider, scoring, normalization, contact-point, and fixture patterns into this package when that avoids a runtime dependency.
- Do not import broad Odollo runtime modules into the watchdog service unless they are isolated behind a narrow optional adapter.
- Keep Odollo tenant identity and credentials in user config/runtime, never in repo fixtures.

## `/goal` Execution Model

This plan is intended to run as a sequence of bounded `/goal` slices. Each slice should end with tests, `git diff --check`, `codegraph sync && codegraph status`, a commit, and a retry of `git push` if a remote exists.

Default stop rule:

- Safe agent-loop execution may continue only zero-write, zero-paid-call, fixture/local-file steps.
- Stop and report explicit operator actions for public-web search, paid API enrichment, live sink lookup, live write pilot, live readback pilot, duplicate merge decisions, and route/apply approvals.

Recommended slice order:

1. `0005-A | Review Matrix`: enrich review bundle/HTML rows with normalized, duplicate, enrichment, route, and sink eligibility columns.
2. `0005-B | Canonical Contact`: harden canonical observed/normalized/reviewed/enriched contact schema and provenance diagnostics.
3. `0005-C | Dedupe Index`: create durable identity index and duplicate-resolution artifacts that block strong duplicates.
4. `0005-D | Route Policy`: add explainable route policy and sink eligibility reports for GWS/Odollo/both/neither.
5. `0005-E | Odollo Enrichment Reuse`: adapt Odollo public-web/Apollo/contact-point patterns behind watchdog provider interfaces.
6. `0005-F | Enrichment Review`: add accepted/rejected enrichment proposal artifacts and review-surface integration.
7. `0005-G | Pilot Readiness Report`: add a run-level report combining review, normalize, enrichment, dedupe, route, lookup, approval, write-pilot, readback-pilot, and pilot-report state.
8. `0005-H | MCP/API/CLI Parity`: ensure every new service method is exposed consistently through CLI, API, and MCP.

Suggested main `/goal` prompt:

```text
Execute Plan 0005 in bounded, committed slices. Use safe agent-loop defaults: no paid API calls, no public-web search unless explicitly requested for that slice, and no live GWS/Odollo writes. Start with the next incomplete slice in docs/dev/plans/0005-2026-06-13-review-routing-normalization-enrichment-dedupe.md, validate it, commit it, and retry git push.
```

## Execution Log

### Slice 0005-A | 2026-06-14 | Review Matrix

Implemented:

- Added a per-job `review_matrix` object to review bundle entries.
- Summarized contact source and key contact fields, normalization warning count, duplicate state, enrichment state/proposals, route state/planned sinks, sink lookup state/matches, sink pilot state, next action, and safe/explicit action flags.
- Added review bundle groups for duplicate, enrichment, route, and sink lookup states.
- Rendered the review matrix into the static offline HTML review surface.
- Added CSV workbook columns for matrix contact source, duplicate state, enrichment state, route state, sink lookup state, normalization warning count, and sink lookup match count.
- Excluded local `.codegraph` state from Hatch source distributions after `uv build` exposed that transient local indexes could otherwise destabilize package builds.

Safety:

- This slice is readback-only.
- No public-web search, paid enrichment provider, GWS, Odollo/Odoo, or live sink calls are made.
- Safe agent-loop boundaries remain unchanged: the matrix reports blocked states; it does not approve or execute them.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_run_summary_and_review_queue tests/test_service.py::test_service_review_bundle_includes_sink_pilot_status -q` passed with 2 tests.
- `.venv/bin/python -m pytest -q` passed with 179 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed after the `.codegraph` sdist exclusion.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed and reported the index is up to date.

### Slice 0005-B | 2026-06-14 | Canonical Contact Provenance

Implemented:

- Added `business-card-watchdog.canonical-contact.v1` as a stable canonical view inside contact candidate and reviewed contact artifacts.
- Added per-field provenance chains for observed card data, normalized values, reviewer corrections, and approved enrichment values.
- Added provenance diagnostics that count fields needing review and summarize selected field sources.
- Preserved the existing flat contact spec contract for CLI/API/sink compatibility.
- Added service-loaded `_canonical_contact` and `_field_provenance` metadata so downstream dedupe/routing still read flat fields while sink planning can cite field evidence.
- Added `field_provenance` to dry-run sink payload values, including a conservative `flat_spec` fallback for callers that provide direct flat specs.

Safety:

- This slice is local schema and payload-readback work only.
- No public-web search, paid enrichment provider, GWS, Odollo/Odoo, or live sink calls are made.
- Sink write behavior remains gated; provenance is attached to planned payloads but does not approve or execute writes.

Validation:

- `.venv/bin/python -m pytest tests/test_contact.py tests/test_sinks.py tests/test_service.py::test_service_run_summary_and_review_queue tests/test_service.py::test_service_review_bundle_includes_sink_pilot_status -q` passed with 26 tests.
- `.venv/bin/python -m pytest -q` passed with 180 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed and reported the index is up to date.

### Slice 0005-C | 2026-06-14 | Durable Duplicate Resolution Index

Implemented:

- Added `business-card-watchdog.duplicate-resolution-index.v1` records under the user-scoped identity directory.
- Added `duplicate-resolutions.jsonl` next to the existing contact identity index.
- Persisted duplicate-resolution decisions from review submission into the durable identity index.
- Added reviewer-cleared `create_new` suppression for future false-positive duplicate pairs, while keeping unresolved duplicate matches blocking.
- Preserved existing per-job `duplicate_resolution.json` artifacts and route-refresh behavior.

Safety:

- This slice is local identity-index and review-artifact work only.
- No public-web search, paid enrichment provider, GWS, Odollo/Odoo, or live sink calls are made.
- Only explicit reviewer duplicate decisions update the durable resolution index.

Validation:

- `.venv/bin/python -m pytest tests/test_dedupe.py tests/test_service.py::test_service_submit_review_resolves_duplicate_for_routing tests/test_service.py::test_service_submit_review_resolves_duplicate_noop_as_cancelled -q` passed with 6 tests.
- `.venv/bin/python -m pytest -q` passed with 181 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed and reported the index is up to date.

### Slice 0005-D | 2026-06-14 | Explainable Route Policy

Implemented:

- Added `business-card-watchdog.route-explanation.v1` decision metadata.
- Recorded configured sinks, route context, matched rules, and excluded rules with reasons.
- Extended route rules beyond email domain to support organization, source folder, tenant, duplicate state, and review state predicates.
- Added sink eligibility reports that keep route eligibility separate from apply approval.
- Persisted route explanation and sink eligibility into `sink_plan.json` and `sink_lookup_plan.json`.
- Added service route context from current job image path, review state, and local/downstream duplicate assessment state.

Safety:

- This slice is local route-policy and artifact-readback work only.
- No public-web search, paid enrichment provider, GWS, Odollo/Odoo, or live sink calls are made.
- Route eligibility remains separate from write approval; live writes stay gated by existing explicit apply/pilot checks.

Validation:

- `.venv/bin/python -m pytest tests/test_routing.py tests/test_service.py::test_service_plan_sinks_for_job_writes_dry_run_plan tests/test_service.py::test_service_plan_sink_lookup_for_job_writes_zero_network_plan -q` passed with 6 tests.
- `.venv/bin/python -m pytest -q` passed with 183 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed and reported the index is up to date.

### Slice 0005-E | 2026-06-14 | Odollo Enrichment Reuse

Implemented:

- Inspected the planned Odollo enrichment reuse targets for public-web phone enrichment, Apollo adapter/result shape handling, contact-point handling, merge policy, and idempotency guidance.
- Adapted Odollo public-web phone normalization/query forms into local watchdog public-web query generation.
- Adapted Odollo directory-aware public-web scoring hints into local fixture/result scoring.
- Adapted Apollo person/contact/data/list wrapper extraction patterns into local paid-provider result normalization.
- Added `adapted_from_odollo_enrichment_patterns` markers to public-web and provider request/result/handoff artifacts.
- Preserved the existing zero-network, explicit-request enrichment boundary.

Safety:

- This slice is local helper adaptation and fixture scoring only.
- No public-web search, paid enrichment provider, GWS, Odollo/Odoo, or live sink calls are made.
- Apollo support remains an explicit paid-provider request/handoff/result-import path; no Apollo client or network adapter was added.

Validation:

- `.venv/bin/python -m pytest tests/test_enrichment.py -q` passed with 20 tests.
- `.venv/bin/python -m pytest -q` passed with 186 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed and reported the index is up to date.

### Slice 0005-F | 2026-06-14 | Enrichment Proposal Review

Implemented:

- Added `business-card-watchdog.enrichment-proposal-review.v1` artifacts.
- Recorded every enrichment merge proposal as `accepted` or `rejected` during `approve_enrichment_merge`.
- Preserved existing `enrichment_merge_review.json` behavior while adding first-class accepted/rejected proposal evidence.
- Added accepted/rejected enrichment counts to review matrix entries.
- Added accepted/rejected enrichment count columns to the CSV review workbook.
- Recorded rejected proposal counts and proposal-review artifact paths in `enrichment_merge_reviewed` events.

Safety:

- This slice records explicit operator review decisions only.
- No public-web search, paid enrichment provider, GWS, Odollo/Odoo, or live sink calls are made.
- Rejected enrichment proposals remain visible as review evidence and are not merged into contacts or sink payloads.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_submit_review_approves_enrichment_merge tests/test_service.py::test_service_apply_review_workbook_csv_supports_enrichment_columns -q` passed with 2 tests.
- `.venv/bin/python -m pytest -q` passed with 186 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed and reported the index is up to date.

## Workstreams

### WS1. Review Surface And Operator Queue

Purpose:

Give the operator a practical place to review card images, extracted fields, normalized fields, duplicate warnings, enrichment proposals, and sink routing decisions before any write.

Deliverables:

- generated batch review bundle index with one row per job
- card image thumbnail/reference, contact candidate summary, review state, duplicate state, enrichment state, route state, and sink-pilot state
- reviewer actions for:
  - approve candidate as-is
  - correct fields
  - reject non-card/low-confidence job
  - mark duplicate of another job/contact
  - approve/reject enrichment proposals
  - approve sink route and write-pilot eligibility
- CLI/API/MCP readback and mutation methods that all call the same service-layer review methods
- static HTML or workbook export as the first operator-friendly surface, with local files only and no live writes

Acceptance:

- a reviewer can inspect all jobs in a run without opening individual artifact paths manually
- corrections produce updated `reviewed_contact.json` artifacts and append-only decision evidence
- duplicate and sink approval states are visible in the same review row
- no paid enrichment or sink write happens from opening or rendering the review surface

Suggested subagent brief:

```text
You are WS1 Review Surface subagent. Build the first operator-usable batch review surface for Business Card Watchdog. Use existing artifacts and service methods. Add a generated static HTML/workbook-style bundle plus shared CLI/API/MCP methods for reviewer decisions. Do not add live sink writes or provider calls.
```

### WS2. Normalization And Canonical Contact Model

Purpose:

Make card-observed data stable enough for duplicate checks, route policy, and sink upserts while preserving provenance.

Deliverables:

- canonical contact schema with observed, normalized, reviewed, enriched, and sink-specific views
- stronger normalization for:
  - names and honorific/suffix handling
  - organization names and legal suffixes
  - titles
  - email domains
  - phone E.164/local display variants
  - websites and social URLs
  - postal addresses where available
- per-field provenance: card OCR, reviewer correction, public web, paid API, downstream lookup, or sink readback
- merge policy that never overwrites card-observed/reviewer-approved fields silently
- normalization diagnostics included in review bundles

Acceptance:

- every sink payload can cite the reviewed/normalized source for each field
- ambiguous normalization creates review warnings instead of guessing
- tests cover representative US phone/email/web/name cases and malformed input
- route/dedupe logic reads canonical fields rather than raw OCR output

Suggested subagent brief:

```text
You are WS2 Normalization subagent. Harden the canonical contact model and normalization pipeline. Preserve observed values and provenance. Add tests for names, organizations, phones, emails, websites, and ambiguous values. Keep route/dedupe consumers on canonical fields.
```

### WS3. Enrichment Boundaries And Provider Adapters

Purpose:

Add useful enrichment while keeping cost, credentials, and overwrite risk controlled.

Provider policy:

- local deterministic enrichment is allowed by default if it uses only already-available artifacts
- public-web enrichment is opt-in per request/run and may perform network/search calls only through an explicit enrichment command
- API-backed enrichment is paid/provider-backed by default and must require explicit request, enabled config, available key, and budget/count limits
- API keys are loaded from `~/credentials/API-keys.env` or existing user config without printing secret values

Odollo adaptation targets:

- copy or adapt reusable enrichment/contact helper patterns from the Odollo repo where they fit this package boundary
- preserve tenant safety and avoid importing broad Odollo runtime coupling unless isolated behind an adapter
- prefer fixture-backed tests and provider response adapters over live network tests

Deliverables:

- enrichment provider interface with `prepare`, `execute`, `score`, `propose_merge`, and `summarize_cost` phases
- public-web search provider adapter with query budget and citation/evidence capture
- paid API provider adapter shell using env-key readiness from `~/credentials/API-keys.env`
- enrichment request artifact that records mode, provider, requested_by, budget, and query/provider limits
- enrichment result artifact that records evidence, confidence, provenance, estimated cost, and merge proposals
- enrichment review artifact that records accepted/rejected proposals
- agent-loop stop rules: never run paid API enrichment from generic "continue"; public-web enrichment also requires explicit request unless configured for the run

Acceptance:

- default tests and default safe executor make zero paid calls
- missing API keys produce blocked readiness without exposing key values
- provider adapters can be tested from fixtures
- review surface shows enrichment proposals separately from card-observed data
- accepted enrichment values are provenance-marked and sink payloads can include or exclude them by policy

Suggested subagent brief:

```text
You are WS3 Enrichment subagent. Adapt Odollo enrichment/contact helper patterns where useful, but keep provider calls behind Business Card Watchdog's explicit request and cost gates. Implement provider interfaces, fixture-backed public-web/API adapter tests, and enrichment-review artifacts. Do not make live paid calls.
```

### WS4. Dedupe And Identity Resolution

Purpose:

Prevent duplicate contacts across the current batch, prior watchdog runs, Google Contacts, and Odollo/Odoo tenants before writing.

Deliverables:

- durable local identity index keyed by normalized email, phone, website/domain, person/org pair, card fingerprint, downstream resource IDs, and reviewer-approved aliases
- duplicate candidate artifact with match basis, confidence, evidence, recommended resolution, and blocking severity
- reviewer actions for:
  - same person/contact
  - same company but different person
  - different contact
  - merge candidate into existing local identity
  - block sink routing until downstream match is resolved
- downstream lookup merge into duplicate assessment from GWS/Odollo lookup results
- duplicate-resolution report at run and job level

Acceptance:

- strong exact email/phone matches block write pilots until reviewed or confirmed as safe update/noop
- company-only matches do not merge people automatically
- reviewer-approved identity resolutions become future duplicate evidence
- downstream lookup matches are visible before write-pilot approval
- tests cover batch duplicates, prior-run duplicates, downstream exact matches, and fuzzy-review-only matches

Suggested subagent brief:

```text
You are WS4 Dedupe subagent. Build durable duplicate and identity-resolution behavior across batch, local history, and downstream lookup evidence. Add reviewer resolution artifacts and make strong duplicates block sink write pilots. Avoid automatic person merges from weak company-only evidence.
```

### WS5. Routing Policy And Sink Eligibility

Purpose:

Make routing to GWS Contacts and/or Odollo/Odoo explicit, explainable, and reviewable.

Deliverables:

- route policy config with rules by tenant, domain, source folder, reviewer label, company, confidence, duplicate state, and enrichment/review state
- route explanation artifact that records matched rules and excluded rules
- sink eligibility report that combines:
  - reviewed contact readiness
  - duplicate status
  - enrichment review status
  - sink readiness
  - downstream lookup status
  - write-pilot/readback/report status
- per-sink apply approval remains separate from route eligibility
- support for "GWS only", "Odollo only", "both", and "neither/needs review"

Acceptance:

- route decisions are deterministic and explainable from config plus artifacts
- unknown or conflicting tenant context routes to `needs_review`
- live write-pilot commands refuse when route policy, duplicate state, or sink readiness is blocking
- tests cover route-by-source, route-by-domain/company, both-sink routing, and ambiguous tenant context

Suggested subagent brief:

```text
You are WS5 Routing subagent. Implement explainable route policy and sink eligibility reports for GWS and Odollo/Odoo. Keep apply approval separate from eligibility. Add tests for source/domain/company/tenant rules and blocking duplicate states.
```

### WS6. Agent-Loop Batch Orchestration

Purpose:

Give `/goal` and subagents a deterministic way to work through large batches without accidentally spending money or writing contacts.

Deliverables:

- batch phase report:
  - ingest/preclassify
  - OCR/App Intelligence extraction
  - normalize
  - review
  - enrichment requested
  - enrichment review
  - dedupe
  - route
  - sink lookup
  - sink approval
  - write pilot
  - readback pilot
  - final pilot report
- next-action groups by phase and blocking reason
- safe executor continues only zero-write/no-paid-call tasks
- explicit executor commands for:
  - public-web enrichment request
  - paid API enrichment request
  - duplicate resolution apply
  - route approval
  - one-job write pilot
  - one-job readback pilot
- idempotent progress markers so interrupted `/goal` runs can resume

Acceptance:

- generic safe execution never performs paid API calls or live writes
- agent-loop readback always explains what requires human/operator approval
- batch summaries scale to many jobs without requiring every artifact to be opened
- CLI/API/MCP expose the same phase report and explicit action methods

Suggested subagent brief:

```text
You are WS6 Agent-Loop subagent. Add batch phase reporting, grouped next actions, and safe/explicit executor boundaries. Generic safe execution may run only zero-write/no-paid-call steps. Make the CLI/API/MCP surfaces call shared service logic.
```

## Proposed Config Additions

```toml
[review]
surface = "html" # html | workbook | json
require_review_before_sink_plan = true
require_review_before_apply = true

[normalization]
default_country = "US"
preserve_observed_values = true
review_ambiguous_names = true
review_ambiguous_phones = true

[enrichment]
enabled = false
api_keys_env = "~/credentials/API-keys.env"
default_mode = "none" # none | public_web | api
allow_public_web = false
allow_paid_api = false
max_public_web_queries_per_run = 200
max_paid_provider_results_per_contact = 5
max_paid_provider_results_per_run = 50
max_paid_provider_cost_per_run_usd = 0

[dedupe]
enabled = true
block_strong_duplicates_before_apply = true
fuzzy_name_company_review_threshold = 0.82

[routing]
default = "needs_review" # needs_review | gws | odollo | both | none
require_route_explanation = true

[sink.google_contacts]
enabled = false
apply_enabled = false
require_duplicate_clearance = true

[sink.odollo]
enabled = false
apply_enabled = false
tenant = ""
require_duplicate_clearance = true
```

## Phase Gates

1. Review surface gate: batch review output can be generated and corrections are applied to `reviewed_contact.json`.
2. Normalization gate: canonical contact fields carry observed/normalized/reviewed provenance.
3. Enrichment gate: public-web and API adapters are fixture-tested; paid API is blocked unless explicitly requested and configured.
4. Dedupe gate: strong duplicates block sink write pilots until resolved.
5. Routing gate: route explanations and sink eligibility reports exist before apply approval.
6. Agent-loop gate: safe executor advances only zero-write/no-paid-call tasks and reports explicit blocked actions.
7. Pilot readiness gate: one reviewed, deduped, routed job can proceed through lookup, approval, write-pilot, readback-pilot, and pilot report.

## Validation Plan

Default validation:

- `git diff --check`
- `.venv/bin/python -m pytest -q`
- `PYTHONPATH=src pytest -q`
- `.venv/bin/bcw doctor --json`
- `.venv/bin/bcw enrichment check --json`
- `.venv/bin/bcw sinks check --json`
- `.venv/bin/bcw runs summary --run-id <fixture-run> --json`
- `.venv/bin/bcw next-actions --run-id <fixture-run> --json`
- `codegraph sync && codegraph status`

External-call validation:

- no network, paid API, GWS, or Odollo writes in default tests
- public-web smoke only after explicit operator request
- paid API smoke only after explicit operator request, configured key, and budget limit
- live GWS/Odollo write pilot only for one selected job and one selected sink after readiness, duplicate clearance, route approval, write pilot, readback pilot, and pilot report evidence

## Open Questions

- During `0005-E`, which Odollo helpers from the reuse target list are small enough to copy/adapt directly, and which should remain behind an optional adapter?
- Which public-web search provider should be the first executable adapter?
- Apollo is the first planned paid API provider shell; should `~/credentials/API-keys.env` recognize only `APOLLO_API_KEY` first, or also Odollo's existing aliases if present?
- After the static HTML/JSON review surface is stable, should workbook export be CSV-first, XLSX-first, or Google Sheets handoff?
- What should be the first live routing policy: GWS only, Odollo/Odoo only, or both after duplicate clearance?
- Which Odollo tenant should be used for the first one-job live pilot?

## Initial Execution Order

1. Execute `0005-A | Review Matrix`.
2. Execute `0005-B | Canonical Contact`.
3. Execute `0005-C | Dedupe Index`.
4. Execute `0005-D | Route Policy`.
5. Execute `0005-E | Odollo Enrichment Reuse`.
6. Execute `0005-F | Enrichment Review`.
7. Execute `0005-G | Pilot Readiness Report`.
8. Execute `0005-H | MCP/API/CLI Parity`.
9. Run one fully simulated end-to-end pilot chain across review, dedupe, route, sink lookup, write pilot, readback pilot, and pilot report.

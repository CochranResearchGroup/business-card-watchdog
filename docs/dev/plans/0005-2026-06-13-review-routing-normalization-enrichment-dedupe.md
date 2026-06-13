# Plan 0005 | Review, Routing, Normalization, Enrichment, And Dedupe Hardening

State: PLANNED
Product authority: `PRODUCT_SPEC.md`
Predecessor:

- `docs/dev/plans/0004-2026-06-13-review-normalization-enrichment-dedupe-sinks.md`

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

- Which Odollo enrichment helpers should be copied directly, and which should remain adapter calls into an installed Odollo package?
- Which public-web search provider should be the first executable adapter?
- Which paid API provider should be first, and what exact environment variable names in `~/credentials/API-keys.env` should be recognized?
- Should the first review surface be static HTML, spreadsheet/workbook, or both?
- What should be the first live routing policy: GWS only, Odollo only, or both after duplicate clearance?
- Which Odollo tenant should be used for the first one-job live pilot?

## Initial Execution Order

1. Add batch review surface and reviewer decision mutation methods.
2. Harden canonical contact/provenance model used by review, dedupe, routing, and sinks.
3. Add durable duplicate-resolution actions and make strong duplicates block apply pilots.
4. Add route policy/explanation and sink eligibility reports.
5. Add enrichment provider interface and fixture-backed public-web/API adapters with explicit request and cost gates.
6. Add batch phase report and agent-loop grouped next actions.
7. Run one fully simulated end-to-end pilot chain across review, dedupe, route, sink lookup, write pilot, readback pilot, and pilot report.


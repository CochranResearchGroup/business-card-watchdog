# Plan 0004 | Review, Normalization, Enrichment, Dedupe, And Sink Routing

State: IN_PROGRESS
Product authority: `PRODUCT_SPEC.md`
Predecessors:

- `docs/dev/plans/0002-2026-06-11-high-level-implementation-goal-plan.md`
- `docs/dev/plans/0003-2026-06-11-follow-on-live-sinks-and-mcp-server.md`

## Scope

Turn the current dry-run batch scaffold into a reviewable contact-intelligence system that can normalize extracted card data, optionally enrich it, detect duplicates before writes, and route approved contacts to Google Workspace Contacts and Odoo/Odollo targets with explicit readiness and cost gates.

This plan incorporates the current design discussion:

- review surface for imported cards and contacts
- sink routing into `gws` and Odollo/Odoo tenants
- stronger normalization contracts
- explicit opt-in enrichment, including Odollo-derived API and public-web enrichment helpers
- duplicate detection across run history and downstream contact stores
- operator-visible dry-run, review, approval, write, and readback evidence

## Non-Goals

- Do not perform paid API enrichment unless the operator explicitly requests it per run, batch, or job.
- Do not perform live Google Contacts or Odoo/Odollo writes without explicit config, readiness evidence, and an operator-approved apply command.
- Do not store API keys, OAuth tokens, tenant secrets, real card images, or private OCR data in the repo.
- Do not overwrite card-observed fields with enrichment data unless a merge policy explicitly marks the enriched value as approved.
- Do not claim perfect dedupe; downstream systems vary in metadata and matching support.
- Do not expose non-loopback API/MCP surfaces in this plan.

## Current Baseline

Implemented:

- per-run ledgers under the user data directory
- per-job artifacts and state transitions
- preclassification artifacts before OCR/App Intelligence
- basic review packets for missing identity fields
- review submission artifacts through CLI/API/MCP-shaped service methods
- dry-run sink decisions and sink payload artifacts
- contact fingerprint, match keys, and serialization key primitives
- dry-run readiness for `google_contacts` and `odoo`
- user-scoped config and watched-folder service installation

Important gaps:

- review approval does not yet apply corrected fields back into canonical contact data
- no review queue/listing UX beyond jobs/artifact inspection
- normalization is mostly whitespace trimming
- no enrichment engine
- no explicit cost gate for paid enrichment
- no cross-run duplicate index
- no downstream Google Contacts/Odoo lookup before routing
- no live write/readback adapters

## Execution Log

### Slice 0004-A | 2026-06-13 | Schema, Review Approval, Enrichment Gates, Local Dedupe

Implemented:

- `contact_candidate.json` artifact generation from current skill `spec.json`.
- Observed vs normalized contact fields for `full_name`, `organization`, `title`, `email`, `phone`, `website`, and `notes`.
- Basic email, phone, website, and person-name normalization.
- Routing now uses normalized contact candidates instead of raw `spec.json`.
- Review approval writes `reviewed_contact.json` with operator corrections and normalized values.
- Review packets embed the contact candidate for operator/agent inspection.
- Enrichment config and readiness checks with default `enabled = false`.
- Explicit paid API gate for Apollo-style enrichment using key names from `~/credentials/API-keys.env` without printing secret values.
- Public-web enrichment readiness surface without provider calls.
- Local identity index under user data for duplicate assessment.
- `duplicate_assessment.json` artifacts and duplicate events.
- Strong duplicate jobs are moved to `needs_review` before sink routing.
- CLI and MCP manifest exposure for enrichment readiness.

Validation:

- `.venv/bin/python -m pytest -q` passed with 57 tests.
- `PYTHONPATH=src pytest -q` passed with 54 tests and 3 skipped optional-extra tests.
- `.venv/bin/bcw enrichment check --json` reports no enrichment requested by default.
- `.venv/bin/bcw enrichment check --mode api --json` blocks because enrichment is disabled in current user config.

Remaining:

- Review queue filtering and batch summary surfaces.
- Actual enrichment request/result artifacts and fixture-backed provider adapters.
- Public-web query/result scoring integration.
- Apollo adapter integration behind the paid API gate.
- Sink-backed duplicate lookup against Google Contacts and Odoo/Odollo.
- Live GWS/Odollo dry-run apply plans and explicit one-job apply/readback pilots.
- MCP executable/server dispatcher for the new tools.

### Slice 0004-B | 2026-06-13 | Review Queue And Batch Summary Surfaces

Implemented:

- Shared service `review_queue` readback derived from run/job ledgers and artifact records.
- Shared service `run_summary` with job-state and artifact-kind counts.
- CLI `bcw reviews list` and `bcw runs summary`.
- API `GET /reviews` and `GET /runs/{run_id}/summary`.
- MCP manifest entries for review queue and run summary tools.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py -q` passed with 16 tests.
- `PYTHONPATH=src pytest tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py -q` passed with 15 tests and 1 skipped optional API-extra test.

Remaining:

- Review queue filtering beyond job state.
- Review queue rendering/workbook/local UI.
- Batch next-action recommendations for agent loops.
- Automatic re-routing after reviewed-contact approval.

### Slice 0004-C | 2026-06-13 | Enrichment Request And Fixture Result Artifacts

Implemented:

- `enrichment_request.json` artifacts for selected jobs.
- `enrichment_result.json` artifacts for fixture-backed public-web results.
- Deterministic public-web query generation from normalized contact candidates.
- Deterministic public-web result scoring from caller-supplied results.
- Merge proposals that remain review-required and do not overwrite observed card fields.
- Service `request_enrichment` method.
- CLI `bcw enrichment request`.
- API `POST /jobs/{job_id}/enrichment` and `POST /enrichment/check`.
- MCP manifest entry for enrichment requests.

Validation:

- `.venv/bin/python -m pytest tests/test_enrichment.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py -q` passed with 14 tests.
- `PYTHONPATH=src pytest tests/test_enrichment.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py -q` passed with 13 tests and 1 skipped optional API-extra test.

Remaining:

- Real public-web search execution remains out of scope for default tests and was not added.
- Apollo adapter integration remains behind the paid API gate.
- Enrichment request review/merge approval is still separate follow-on work.

### Slice 0004-D | 2026-06-13 | Dry-Run Sink Plan Artifacts

Implemented:

- `sink_plan.json` artifact generation for selected jobs.
- Sink plans prefer `reviewed_contact.json`, then `contact_candidate.json`, then legacy `spec.json`.
- Sink plans include routing decision, dry-run payloads, readiness, match keys, serialization keys, and planned upsert actions.
- Service `plan_sinks_for_job` method.
- CLI `bcw sinks plan`.
- API `POST /jobs/{job_id}/sink-plan`.
- MCP manifest entry for sink planning.

Validation:

- `.venv/bin/python -m pytest tests/test_sinks.py tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py -q` passed with 25 tests.
- `PYTHONPATH=src pytest tests/test_sinks.py tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py -q` passed with 24 tests and 1 skipped optional API-extra test.

Remaining:

- Downstream Google Contacts/Odoo lookup is not implemented.
- Live apply/readback remains blocked.
- Approved reviewed-contact jobs still need automatic rerouting/plan refresh.

### Slice 0004-E | 2026-06-13 | Agent Next Actions And MCP Dispatcher

Implemented:

- Shared service `next_actions` readback for deterministic agent-loop orchestration.
- Next-action recommendations for review, duplicate resolution, enrichment review, sink planning, apply approval, and failure inspection.
- MCP manifest entry for `business_card_watchdog_next_actions`.
- Executable MCP-style dispatcher `call_tool` for current manifest tools.
- CLI `bcw mcp-call` for local tool execution with JSON arguments.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py tests/test_mcp.py tests/test_cli_surfaces.py -q` passed with 22 tests.
- `PYTHONPATH=src pytest tests/test_service.py tests/test_mcp.py tests/test_cli_surfaces.py -q` passed with 22 tests.

Remaining:

- Streaming MCP server transport is not implemented.
- Agent next actions do not yet include explicit live apply pilot readiness.
- Automatic rerouting after reviewed-contact approval remains follow-on work.

### Slice 0004-F | 2026-06-13 | Expanded Review Actions

Implemented:

- First-class review actions: `request_enrichment`, `reject_not_card`, and `skip`.
- `request_enrichment` keeps or returns the job to `needs_review`.
- `reject_not_card` transitions the job to `failed` with an explicit review error.
- `skip` transitions the job to `cancelled`.
- CLI and MCP schema exposure for expanded review actions.

Validation:

- `.venv/bin/python -m pytest tests/test_review.py tests/test_service.py tests/test_cli_surfaces.py tests/test_mcp.py -q` passed with 27 tests.
- `PYTHONPATH=src pytest tests/test_review.py tests/test_service.py tests/test_cli_surfaces.py tests/test_mcp.py -q` passed with 27 tests.

Remaining:

- Live sink apply/reject/noop review actions remain follow-on work.

### Slice 0004-G | 2026-06-13 | Sink Apply Preflight Gate

Implemented:

- `sink_apply_preflight.json` artifact generation for planned jobs.
- Zero-write apply preflight schema with `writes_attempted = 0` and `network_calls_made = 0`.
- Default preview mode that explains no live write was attempted.
- Explicit `apply = true` path that remains blocked until live sink write/readback adapters exist.
- Service `preflight_sink_apply` method.
- CLI `bcw sinks apply-preflight`.
- API `POST /jobs/{job_id}/sink-apply-preflight`.
- MCP manifest and dispatcher entry for `business_card_watchdog_sink_apply_preflight`.
- Agent next-action command updated from generic sink apply to apply preflight.

Validation:

- `.venv/bin/python -m pytest tests/test_sinks.py tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py -q` passed with 35 tests.

Remaining:

- Live Google Contacts and Odoo/Odollo write/readback adapters remain blocked.
- Sink-backed duplicate lookup remains follow-on work.
- Automatic apply/reject/noop review actions remain follow-on work.

### Slice 0004-H | 2026-06-13 | Enrichment Merge Approval

Implemented:

- First-class review action `approve_enrichment_merge`.
- Explicit `approved_enrichment_fields` review submission field.
- Approved enrichment proposals write a new `reviewed_contact.json`.
- Approved enrichment proposals write `enrichment_merge_review.json` audit artifacts.
- Existing card notes are preserved when approved enrichment notes are merged.
- Service, CLI, API, and MCP dispatcher surfaces for enrichment merge approval.
- `enrichment_merge_reviewed` ledger events for agent-loop readback.

Validation:

- `.venv/bin/python -m pytest tests/test_contact.py tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py -q` passed with 33 tests.

Remaining:

- Live Google Contacts and Odoo/Odollo write/readback adapters remain blocked.
- Sink-backed duplicate lookup remains follow-on work.
- Automatic apply/reject/noop review actions remain follow-on work.

### Slice 0004-I | 2026-06-13 | Duplicate Resolution Review Actions

Implemented:

- First-class review action `resolve_duplicate`.
- Explicit duplicate decisions: `create_new`, `merge_existing`, and `noop`.
- `duplicate_resolution.json` audit artifacts.
- `duplicate_resolved` ledger events.
- `create_new` and `merge_existing` transition reviewed duplicate jobs to `ready_to_route`.
- `noop` transitions reviewed duplicate jobs to `cancelled`.
- Sink plans carry `duplicate_resolution` forward when present.
- Service, CLI, API, and MCP dispatcher surfaces support duplicate resolution.

Validation:

- `.venv/bin/python -m pytest tests/test_review.py tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py -q` passed with 38 tests.

Remaining:

- Live Google Contacts and Odoo/Odollo write/readback adapters remain blocked.
- Live sink-backed duplicate lookup execution remains follow-on work.
- Automatic apply/reject/noop sink apply actions remain follow-on work.

### Slice 0004-J | 2026-06-13 | Sink Lookup Plan Artifacts

Implemented:

- `sink_lookup_plan.json` artifacts for selected jobs.
- Zero-network downstream lookup planning with `network_calls_made = 0`.
- Google Contacts and Odoo lookup query descriptors built from fingerprint, email, phone, and name keys.
- Sink lookup readiness that remains dry-run ready and blocks live lookup execution until adapters exist.
- Service `plan_sink_lookup_for_job` method.
- CLI `bcw sinks lookup-plan`.
- API `POST /jobs/{job_id}/sink-lookup-plan`.
- MCP manifest and dispatcher entry for `business_card_watchdog_sink_lookup_plan`.
- Agent next-action ordering now recommends lookup planning before sink payload planning.

Validation:

- `.venv/bin/python -m pytest tests/test_sinks.py tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py -q` passed with 44 tests.

Remaining:

- Live Google Contacts and Odoo/Odollo lookup/write/readback adapters remain blocked.
- Live sink-backed duplicate lookup execution remains follow-on work.
- Automatic apply/reject/noop sink apply actions remain follow-on work.

### Slice 0004-K | 2026-06-13 | Sink Apply Decision Artifacts

Implemented:

- `sink_apply_decision.json` artifacts for apply approval, rejection, and no-op decisions.
- Explicit apply decisions: `approve`, `reject`, and `noop`.
- Zero-write decision artifacts with `writes_attempted = 0` and `network_calls_made = 0`.
- `noop` decisions transition jobs to `cancelled`.
- `sink_apply_decided` ledger events for agent-loop readback.
- Service `decide_sink_apply` method.
- CLI `bcw sinks apply-decision`.
- API `POST /jobs/{job_id}/sink-apply-decision`.
- MCP manifest and dispatcher entry for `business_card_watchdog_sink_apply_decision`.
- Agent next-action ordering now recommends apply preflight before apply decision.

Validation:

- `.venv/bin/python -m pytest tests/test_sinks.py tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py -q` passed with 49 tests.

Remaining:

- Live Google Contacts and Odoo/Odollo lookup/write/readback adapters remain blocked.
- Live sink-backed duplicate lookup execution remains follow-on work.
- Live apply after approved decision remains follow-on work.

### Slice 0004-L | 2026-06-13 | Gated Sink Apply Result Artifacts

Implemented:

- `sink_apply_result.json` artifacts for gated apply attempts.
- CLI `bcw sinks apply` with explicit `--apply`.
- API `POST /jobs/{job_id}/sink-apply`.
- MCP manifest and dispatcher entry for `business_card_watchdog_sink_apply`.
- Approved decisions are required before live apply can advance.
- Live apply currently writes a blocked result artifact because live sink write/readback adapters are not implemented.
- Apply result artifacts record `writes_attempted = 0`, `network_calls_made = 0`, and empty readback evidence.
- `sink_apply_attempted` ledger events for agent-loop readback.
- Agent next-action command now points to `sinks apply --apply` after an apply decision exists.

Validation:

- `.venv/bin/python -m pytest tests/test_sinks.py tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py -q` passed with 52 tests.

Remaining:

- Live Google Contacts and Odoo/Odollo lookup/write/readback adapters remain blocked.
- Live sink-backed duplicate lookup execution remains follow-on work.
- Live apply result remains blocked until adapters are implemented and explicitly approved.

### Slice 0004-M | 2026-06-13 | Sink Apply Policy Readiness Gates

Implemented:

- User config flags `google_contacts_apply_enabled` and `odoo_apply_enabled`, both defaulting to `false`.
- Default config template documents the live apply policy flags.
- Live sink readiness now blocks on disabled apply policy before checking tools or adapters.
- Service readiness passes per-sink apply policy into readiness checks.
- Live plan readiness can distinguish dry-run readiness, disabled live apply policy, and adapter-not-implemented state.

Validation:

- `.venv/bin/python -m pytest tests/test_config.py tests/test_sinks.py tests/test_service.py -q` passed with 40 tests.

Remaining:

- Live Google Contacts and Odoo/Odollo lookup/write/readback adapters remain blocked.
- Live sink-backed duplicate lookup execution remains follow-on work.
- Live apply result remains blocked until adapters are implemented and explicitly approved.

### Slice 0004-N | 2026-06-13 | Simulated Sink Apply Readback

Implemented:

- Explicit `simulate` flag for gated sink apply attempts.
- Mock sink apply/readback result state `mock_applied`.
- Simulated readback entries with stable mock resource IDs derived from sink and serialization key.
- CLI `bcw sinks apply --apply --simulate`.
- API and MCP apply surfaces accept `simulate`.
- Simulated apply keeps `writes_attempted = 0` and `network_calls_made = 0`.
- `sink_apply_attempted` events record whether the attempt was simulated.

Validation:

- `.venv/bin/python -m pytest tests/test_sinks.py tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py -q` passed with 56 tests.

Remaining:

- Live Google Contacts and Odoo/Odollo lookup/write/readback adapters remain blocked.
- Live sink-backed duplicate lookup execution remains follow-on work.
- Non-simulated live apply remains blocked until adapters are implemented and explicitly approved.

### Slice 0004-O | 2026-06-13 | Sink Adapter Request Artifacts

Implemented:

- Added `sink_adapter_request_{phase}.json` artifacts for `lookup`, `write`, and `readback` phases.
- Added adapter request descriptors for Google Contacts and Odoo/Odollo live lookup/write/readback calls.
- Adapter requests record intended adapter, method/model, match keys, payloads, serialization keys, and mock readback IDs where available.
- Adapter request artifacts remain blocked by default and record `writes_attempted = 0` and `network_calls_made = 0`.
- Service method auto-creates prerequisite dry-run lookup plans, sink plans, or preview apply results when the source artifact is missing.
- Added CLI `bcw sinks adapter-request`.
- Added API and MCP dispatcher surfaces for adapter request creation.

Validation:

- `.venv/bin/python -m pytest tests/test_sinks.py tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py -q` passed with 59 tests.

Remaining:

- Live Google Contacts and Odoo/Odollo lookup/write/readback adapters remain blocked.
- Live sink-backed duplicate lookup execution remains follow-on work.
- Non-simulated live apply remains blocked until adapters are implemented and explicitly approved.

### Slice 0004-P | 2026-06-13 | Adapter Request Agent Next Actions

Implemented:

- Updated deterministic `next_actions` sequencing to include adapter request phases.
- Ready jobs now request `sinks adapter-request --phase lookup` after sink lookup planning.
- Sink-planned jobs now request `sinks adapter-request --phase write` before apply preflight.
- Jobs with sink apply results now request `sinks adapter-request --phase readback`.
- Jobs with completed readback adapter requests no longer keep repeating the live apply approval action.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py tests/test_cli_surfaces.py tests/test_mcp.py -q` passed with 48 tests.

Remaining:

- Live Google Contacts and Odoo/Odollo lookup/write/readback adapters remain blocked.
- Live sink-backed duplicate lookup execution remains follow-on work.
- Non-simulated live apply remains blocked until adapters are implemented and explicitly approved.

### Slice 0004-Q | 2026-06-13 | Sink Lookup Result Artifacts

Implemented:

- Added `sink_lookup_result.json` artifacts for downstream lookup results.
- Lookup result artifacts can record future live/fixture sink matches while defaulting to zero-network `not_executed` results.
- Fixture-provided downstream matches set `state = possible_duplicate` and `duplicate_review_required = true`.
- Lookup results preserve adapter request source schema, sink match keys, query counts, match basis, confidence, and resource IDs.
- Service, CLI, API, and MCP surfaces can record lookup result artifacts.
- `next_actions` now requires `sinks lookup-result` after lookup adapter requests and before sink planning.
- Lookup result artifacts record `writes_attempted = 0` and `network_calls_made = 0`.

Validation:

- `.venv/bin/python -m pytest tests/test_sinks.py tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py -q` passed with 66 tests.

Remaining:

- Live Google Contacts and Odoo/Odollo lookup/write/readback adapters remain blocked.
- Live sink-backed duplicate lookup execution remains follow-on work.
- Non-simulated live apply remains blocked until adapters are implemented and explicitly approved.

### Slice 0004-R | 2026-06-13 | Downstream Duplicate Assessment Gate

Implemented:

- Added downstream sink lookup result assessment into the existing duplicate assessment schema.
- Fixture/live-shaped sink matches can now produce `strong_duplicate` or `possible_duplicate` assessments.
- Downstream duplicate assessments write `downstream_duplicate_assessment.json` artifacts.
- Jobs with downstream duplicate matches transition back to `needs_review` before sink planning proceeds.
- Duplicate resolution review can resolve downstream duplicate assessments when no local `duplicate_assessment.json` exists.
- Service, CLI, API, and MCP surfaces can run downstream duplicate assessment.
- `next_actions` now requires `sinks assess-duplicates` after sink lookup results and before sink planning.

Validation:

- `.venv/bin/python -m pytest tests/test_dedupe.py tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py -q` passed with 57 tests.

Remaining:

- Live Google Contacts and Odoo/Odollo lookup/write/readback adapters remain blocked.
- Live sink-backed duplicate lookup execution remains follow-on work.
- Non-simulated live apply remains blocked until adapters are implemented and explicitly approved.

### Slice 0004-S | 2026-06-13 | Safe Agent Next-Action Executor

Implemented:

- Added `run_next_actions` service method for deterministic agent-loop execution.
- Executor repeatedly runs only allowlisted safe actions: lookup planning, adapter request creation, lookup result recording, downstream duplicate assessment, sink planning, write adapter request creation, apply preflight, and readback adapter request creation.
- Executor skips review, duplicate resolution, enrichment review, apply decisions, live apply approval, and failure inspection.
- Added CLI `bcw actions run-next`.
- Added API `POST /actions/run-next`.
- Added MCP tool `business_card_watchdog_run_next_actions`.
- Safe executor returns executed and skipped action records for agent-loop readback.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py -q` passed with 55 tests.

Remaining:

- Live Google Contacts and Odoo/Odollo lookup/write/readback adapters remain blocked.
- Live sink-backed duplicate lookup execution remains follow-on work.
- Non-simulated live apply remains blocked until adapters are implemented and explicitly approved.

### Slice 0004-T | 2026-06-13 | MCP Stdio Transport

Implemented:

- Added `business_card_watchdog.mcp_server` JSONL stdio transport.
- Transport handles `initialize`, `tools/list`, `tools/call`, `ping`, and `shutdown` JSON-RPC requests.
- `tools/list` adapts the existing manifest into MCP-style `inputSchema` records.
- `tools/call` delegates to the existing `mcp.call_tool` dispatcher so service-layer policy remains shared with CLI/API.
- Added CLI `bcw mcp-stdio`.
- Added tests for transport initialize, tool listing, tool call dispatch, shutdown, and CLI parser exposure.

Validation:

- `.venv/bin/python -m pytest tests/test_mcp.py tests/test_cli_surfaces.py -q` passed with 21 tests.

Remaining:

- Live Google Contacts and Odoo/Odollo lookup/write/readback adapters remain blocked.
- Live sink-backed duplicate lookup execution remains follow-on work.
- Non-simulated live apply remains blocked until adapters are implemented and explicitly approved.

### Slice 0004-U | 2026-06-13 | Paid Enrichment Provider Request Artifacts

Implemented:

- Added `enrichment_provider_request.json` artifacts for explicitly requested paid API enrichment.
- Added Apollo-shaped provider request builder with observed contact fields, request fields, configured base URL, and API key env name.
- Provider request artifacts record `network_calls_made = 0` and `paid_api_calls_attempted = 0`.
- Provider request artifacts never include API key values.
- Service `request_enrichment` writes provider request artifacts for `api` and `all` modes only after readiness passes.
- CLI and MCP enrichment request surfaces can produce the provider request artifact with `--allow-paid-enrichment` / `allow_paid_enrichment`.

Validation:

- `.venv/bin/python -m pytest tests/test_enrichment.py tests/test_cli_surfaces.py tests/test_mcp.py -q` passed with 30 tests.

Remaining:

- Real public-web search execution remains out of scope for default tests.
- Apollo live API calls remain blocked behind explicit operator request and future adapter implementation.
- Live Google Contacts and Odoo/Odollo lookup/write/readback adapters remain blocked.
- Non-simulated live apply remains blocked until adapters are implemented and explicitly approved.

## `/goal` Objective

Use this as the high-level `/goal` objective:

```text
Implement the next Business Card Watchdog intelligence layer: a review-first contact pipeline that normalizes OCR output, preserves card-observed provenance, supports explicitly requested enrichment from Odollo-derived API and public-web tools, detects duplicates across run history and downstream sinks, and routes approved contacts to Google Workspace Contacts and Odoo/Odollo through dry-run-first, readiness-gated, idempotent sink adapters.
```

## Operating Contract

The primary agent owns:

- schema compatibility across review, normalization, enrichment, dedupe, and sinks
- cost and credential policy for enrichment providers
- live-write gates and final apply/readback decisions
- user-scoped config migration
- roadmap/runbook closeout

Subagents may work in parallel on bounded repo-local slices. Each subagent must return:

- inspected files
- changed files
- new schemas or state transitions
- tests run
- external-write/enrichment calls attempted, which should be zero unless explicitly authorized
- blockers and integration risks

Subagents must not:

- read or print secret values from `~/credentials/API-keys.env`
- perform paid API enrichment without an explicit operator flag and small bounded target
- write to Google Contacts or Odoo/Odollo without a dry-run artifact, readiness proof, and operator-approved apply command
- commit private card images or OCR artifacts

## Workstream Overview

### WS1. Canonical Contact Schema And Normalization

Purpose:

Create a durable schema for card-observed contact data, normalized fields, provenance, confidence, and enrichment candidates.

Deliverables:

- `contact_candidate.json` schema
- observed-field provenance model
- normalized-field model
- correction/merge model
- phone normalization, including E.164 where possible
- email normalization, including lowercase mailbox/domain and basic validation
- URL/domain normalization
- person-name parsing into display/given/family where confidence allows
- organization/title/address normalization placeholders
- migration path from current `spec.json`

Acceptance:

- current skill `spec.json` is converted into the canonical candidate schema
- normalized values preserve original observed values
- missing/ambiguous values remain reviewable, not silently invented
- tests cover whitespace, email case, phone formats, website forms, and partial names

Suggested subagent brief:

```text
You are WS1 Normalization subagent. Inspect current `sinks.py`, `review.py`, `orchestrator.py`, tests, and the `business-card-to-contact` skill artifact contract. Implement or propose a canonical contact candidate schema with observed values, normalized values, provenance, and review-safe merge fields. Do not call external enrichment providers or sinks. Return tests and schema examples.
```

### WS2. Review Queue And Operator Surface

Purpose:

Make review an actual workflow rather than isolated packets.

Deliverables:

- review queue listing by run/job/status
- review packet includes OCR text, preclassification summary, candidate contact, normalization notes, sink decision, duplicate candidates, and enrichment options
- review submission applies approved corrections into a new reviewed contact artifact
- explicit actions: `approve_for_routing`, `request_enrichment`, `reject_not_card`, `keep_needs_review`, `skip`
- batch summary showing ready, blocked, needs-review, duplicate, and enrichment-requested counts
- CLI/API/MCP parity for review listing, job review, and batch summary

Acceptance:

- approving corrections creates a reviewed contact artifact and records an event
- jobs only move to `ready_to_route` after reviewed/canonical data exists
- review actions are idempotent and replayable from artifacts
- tests cover correction application, invalid correction rejection, and queue filtering

Suggested subagent brief:

```text
You are WS2 Review Surface subagent. Build the repo-local review workflow around existing job/run artifacts. Add review queue readback, reviewed-contact artifacts, correction application, and CLI/API/MCP service methods. Do not implement live sinks. Keep real private card data out of tests. Return commands proving queue and approval behavior.
```

### WS3. Enrichment Policy And Provider Adapters

Purpose:

Add enrichment as an explicit, auditable, cost-aware workflow.

Provider sources:

- API-based enrichment copied or adapted from Odollo where appropriate:
  - `odollo.adapters.apollo.ApolloClient`
  - Odollo context/config patterns for provider readiness
  - Odoo/Odollo contact lookup helpers where tenant-safe
- public web enrichment copied or adapted from:
  - `odollo.core.public_web_enrichment`
- API keys loaded from `~/credentials/API-keys.env` by variable name only; never print values

Deliverables:

- enrichment config with default `enabled = false`
- run/job flags such as `--enrich none|public-web|api|all`
- explicit paid-provider gate, e.g. `--allow-paid-enrichment`
- provider readiness checks that report missing key names without exposing secrets
- enrichment request artifact
- enrichment result artifact with source, cost class, confidence, and provenance
- merge proposal artifact that never overwrites observed card data without approval
- deterministic public-web query builder and result scorer
- Apollo/person-company match adapter behind explicit API gate

Acceptance:

- default runs perform no enrichment
- public-web enrichment can be requested without paid API keys
- API enrichment refuses to run unless the operator passes the explicit paid-enrichment flag
- missing API key reports the missing variable name only
- enrichment outputs are candidates/proposals until reviewed
- tests use fixtures/mocks only; no network calls in default test suite

Suggested subagent brief:

```text
You are WS3 Enrichment subagent. Inspect Odollo's Apollo adapter, public web enrichment helper, config/readiness conventions, and this repo's review/routing code. Design and implement the smallest enrichment provider abstraction with no default external calls, explicit paid API gating, and fixture-backed tests. Do not read or print API key values. Return provider contracts, config keys, and test evidence.
```

### WS4. Duplicate Detection And Identity Resolution

Purpose:

Prevent avoidable duplicate contacts before sink writes.

Deliverables:

- local duplicate index under user data directory
- cross-run lookup by fingerprint, email, phone, normalized name+organization, and sink external IDs
- duplicate candidate artifact
- deterministic duplicate decision states:
  - `no_match`
  - `possible_duplicate`
  - `strong_duplicate`
  - `same_card_reprocess`
  - `sink_existing_match`
- review action for merge/noop/create-new
- same-contact serialization lock keyed by normalized email/phone/name/fingerprint

Acceptance:

- processing the same card twice surfaces a duplicate candidate before routing
- email and phone exact matches are strong duplicates
- fuzzy name/company matches are possible duplicates requiring review
- duplicate decisions are recorded in the ledger
- live sink write paths are blocked until duplicate decision is resolved

Suggested subagent brief:

```text
You are WS4 Dedupe subagent. Build a local identity index and duplicate candidate artifact using current fingerprints, match keys, and run ledgers. Add deterministic duplicate states and tests for repeated cards, exact email/phone matches, and ambiguous name/company matches. Do not call Google or Odoo live APIs. Return the index format and migration notes.
```

### WS5. Google Workspace Contacts Sink

Purpose:

Implement dry-run-first, idempotent Google Contacts routing.

Deliverables:

- `gws` readiness check for installed CLI/auth/scopes
- Google Contacts lookup by email, phone, and optionally stored fingerprint metadata/notes
- dry-run apply plan
- apply command requiring explicit `--apply`
- write/readback artifact with Google resource name and selected fields
- duplicate/noop/update/create decision
- rollback or remediation note when rollback is not possible

Acceptance:

- default readiness remains blocked for live writes unless config and auth pass
- dry-run shows intended create/update/noop and match basis
- live pilot can be run against one explicitly selected job
- readback proves the contact exists after write
- tests mock `gws`; no real Google write in default tests

Suggested subagent brief:

```text
You are WS5 GWS Sink subagent. Implement Google Contacts readiness, lookup, dry-run apply plans, and mocked write/readback paths through the service layer. Keep live apply behind explicit config and CLI flag. Do not perform a real contact write unless the primary agent provides a specific approved pilot job. Return tests and exact readiness failures.
```

### WS6. Odoo/Odollo Sink

Purpose:

Implement tenant-aware Odoo/Odollo routing while reusing proven Odollo helpers.

Odollo sources to adapt or call:

- `odollo.core.odoo_readiness`
- `odollo.core.odoo_lookup`
- `odollo.core.contact_points`
- `odollo.adapters.odoo_json2`
- review/action semantics from `odollo.review_workbook` where useful

Deliverables:

- tenant profile config
- tenant identity/readiness check
- partner lookup by email, phone, fingerprint, external IDs, and contact points
- dry-run `res.partner` create/update/noop plan
- optional Odollo contact-point creation plan
- live apply command requiring explicit `--apply`
- write/readback artifact with partner ID, matched key, action, and tenant identity
- handling for company/person relationship ambiguity

Acceptance:

- no tenant writes occur without readiness and explicit apply
- dry-run plan distinguishes create/update/noop/needs-review
- existing partner exact email/phone matches avoid duplicate creation
- contact-point plans are additive and do not overwrite canonical slots by default
- tests mock Odoo/Odollo client behavior

Suggested subagent brief:

```text
You are WS6 Odollo Sink subagent. Adapt Odollo readiness, lookup, and contact-point patterns into Business Card Watchdog's sink interface. Implement tenant-safe dry-run plans and mocked apply/readback paths. Do not perform live Odoo writes unless the primary agent gives a specific approved pilot. Return tenant config, tests, and blocked readiness examples.
```

### WS7. API/MCP Agent Loop Orchestration

Purpose:

Expose the new review/enrichment/dedupe/sink phases through deterministic agent-loop surfaces.

Deliverables:

- MCP server transport or executable dispatcher for current manifest tools
- new MCP tools for review queue, enrichment request, duplicate resolution, sink plan, and apply pilot
- API endpoints for the same service methods
- bounded batch orchestration commands:
  - classify/preflight
  - normalize
  - review
  - enrich requested jobs
  - dedupe
  - route dry-run
  - apply approved one-job pilot
- phase-specific stop rules and batch progress readback

Acceptance:

- CLI/API/MCP all call shared service methods
- no duplicated orchestration logic across surfaces
- agent can process a large batch by repeatedly asking for next actionable jobs
- expensive/provider-backed enrichment is never triggered by a generic "continue" operation

Suggested subagent brief:

```text
You are WS7 Agent Surface subagent. Extend service, CLI, API, and MCP surfaces around review/enrichment/dedupe/sink phases without duplicating orchestration logic. Add deterministic next-action readback for agent loops. Keep all apply and paid-enrichment actions explicit. Return manifest/API schema changes and tests.
```

## Configuration Additions

Proposed user config shape:

```toml
[normalization]
default_country = "US"

[enrichment]
enabled = false
default_mode = "none" # none | public_web | api | all
allow_paid_api = false
api_keys_env = "~/credentials/API-keys.env"

[enrichment.providers.apollo]
enabled = false
api_key_env = "APOLLO_API_KEY"
base_url = "https://api.apollo.io"

[enrichment.providers.public_web]
enabled = true
max_queries_per_contact = 8

[dedupe]
enabled = true
fuzzy_name_company_review_threshold = 0.82

[sink.google_contacts]
enabled = false
apply_enabled = false

[sink.odollo]
enabled = false
apply_enabled = false
tenant = ""
```

Exact key names should be reconciled against Odollo's existing config and `~/credentials/API-keys.env` without printing secret values.

## Phase Gates

1. Schema gate: canonical contact candidate, reviewed contact, enrichment proposal, duplicate candidate, and sink plan schemas exist with tests.
2. Review gate: operator can approve corrections into reviewed contact artifacts.
3. Enrichment gate: public-web enrichment works from fixtures; paid API provider refuses without explicit request.
4. Dedupe gate: duplicate candidates block live routing until resolved.
5. Dry-run sink gate: GWS and Odollo produce create/update/noop plans from reviewed contacts.
6. Readiness gate: live sink readiness distinguishes missing tools, missing auth, missing tenant, and apply-disabled state.
7. Pilot gate: one explicitly selected job can be applied to one explicitly selected sink with readback evidence.

## Validation Plan

Default validation:

- `git diff --check`
- `.venv/bin/python -m pytest -q`
- `PYTHONPATH=src pytest -q`
- `.venv/bin/bcw doctor --json`
- `.venv/bin/bcw sinks check --json`
- fixture-backed dry-run process/review/dedupe/route commands
- CodeGraph sync/status after implementation edits

External-call validation:

- no network or paid API calls in default tests
- explicit fixture tests for provider responses
- explicit smoke only after operator approval for:
  - Apollo API readiness
  - GWS Contacts lookup/write pilot
  - Odoo/Odollo tenant lookup/write pilot

## Open Questions

- Which `~/credentials/API-keys.env` variable names should be recognized for Apollo and any other paid enrichment providers?
- Should web-search enrichment use a local browser/search provider, an API, or both?
- Should Google Contacts store the business-card fingerprint in notes, user-defined metadata, or an external local index only?
- Which Odollo tenant should be the first live pilot target?
- Should reviewed contacts be routed to Google Contacts first, Odollo first, or both only after dedupe confidence is high?
- What is the minimum acceptable review surface for first use: CLI JSON, generated workbook, local web UI, or MCP-driven agent review?

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

### Slice 0004-V | 2026-06-13 | Provider-Specific Sink Adapter Request Contracts

Implemented:

- Expanded blocked `sink_adapter_request_*.json` artifacts with concrete Google People API request contracts.
- Google Contacts lookup requests now include profile placeholders, query body, read mask, match strategy, and expected response keys.
- Google Contacts write requests now include create/update method intent, People API request body, idempotency policy, and expected response keys.
- Google Contacts readback requests now include `people.get` request fields for resource verification.
- Expanded blocked Odollo/Odoo requests with tenant placeholders, `res.partner` lookup/write/readback contracts, Odoo domains, contact-point plans, and expected response keys.
- Odollo write requests keep contact-point plans additive and set `overwrite_canonical_slots = false`.
- Adapter request artifacts still record `network_calls_made = 0`, `writes_attempted = 0`, and `requires_live_adapter = true`.

Validation:

- `.venv/bin/python -m pytest tests/test_sinks.py -q` passed with 14 tests.

Remaining:

- Live Google Contacts and Odoo/Odollo lookup/write/readback adapters remain blocked.
- Live tenant/profile readiness still needs concrete config reconciliation with GWS/Odollo runtimes.
- Non-simulated live apply remains blocked until adapters are implemented and explicitly approved.

### Slice 0004-W | 2026-06-13 | Sink Tenant And Profile Config Metadata

Implemented:

- Added user config fields `sink.google_contacts_profile` and `sink.odollo_tenant`.
- Default user config now includes empty profile/tenant placeholders.
- Sink config loading preserves those values without reading live credentials or tenant runtime files.
- Live apply readiness reports missing `sink.google_contacts_profile` or `sink.odollo_tenant` before reaching live adapter checks.
- Configured profile/tenant values flow into generated Google Contacts and Odollo/Odoo adapter request artifacts.
- Adapter request artifacts remain blocked and record `network_calls_made = 0` and `writes_attempted = 0`.

Validation:

- `.venv/bin/python -m pytest tests/test_config.py tests/test_service.py tests/test_sinks.py -q` passed with 54 tests.

Remaining:

- Concrete GWS/Odollo auth checks remain blocked behind future live readiness adapters.
- Live Google Contacts and Odoo/Odollo lookup/write/readback adapters remain blocked.
- Non-simulated live apply remains blocked until adapters are implemented and explicitly approved.

### Slice 0004-X | 2026-06-13 | GWS Local Readiness Evidence

Implemented:

- Google Contacts live readiness now reports local `gws` readiness evidence without making Google API calls.
- Readiness distinguishes missing `gws`, missing Google Workspace auth evidence, missing People API discovery cache, and the still-blocked live write/readback gate.
- Readiness details include the configured profile, `gws` path, config directory, boolean auth evidence file presence, People discovery cache presence, required contact scopes, and a note that scope evidence is not verified without a live API call.
- Google adapter request contracts now include deterministic `gws` command vectors for lookup, write, and readback.
- Tests isolate `GOOGLE_WORKSPACE_CLI_CONFIG_DIR` to prove missing-auth behavior without depending on the workstation's real auth state.

Validation:

- `.venv/bin/python -m pytest tests/test_sinks.py tests/test_service.py tests/test_config.py -q` passed with 55 tests.

Remaining:

- Live Google scope verification remains blocked until an explicitly approved read-only/pilot call is allowed.
- Live Google Contacts and Odoo/Odollo lookup/write/readback adapters remain blocked.
- Non-simulated live apply remains blocked until adapters are implemented and explicitly approved.

### Slice 0004-Y | 2026-06-13 | Odollo Local Readiness Evidence

Implemented:

- Odoo/Odollo live readiness now reports local Odollo tenant evidence without importing Odollo runtime code or making Odoo calls.
- Readiness distinguishes missing `sink.odollo_tenant`, missing Odollo user config, missing tenant home, missing tenant state evidence, and the still-blocked live tenant readiness gate.
- Readiness details include `ODOLLO_HOME`, `odollo.yml` presence, tenant home path, resource/artifact/action-log presence, state DB candidate presence, and a blocked live probe descriptor.
- The readiness contract mirrors Odollo's `odollo.core.odoo_readiness.odoo_readiness_report` boundary while keeping `network_calls_made = 0`.
- Tests isolate `ODOLLO_HOME` to prove missing-config and local-evidence behavior without using private tenant state.

Validation:

- `.venv/bin/python -m pytest tests/test_sinks.py tests/test_service.py tests/test_config.py -q` passed with 57 tests.

Remaining:

- Live Odollo/Odoo schema/auth verification remains blocked until an explicitly approved read-only/pilot call is allowed.
- Live Google Contacts and Odoo/Odollo lookup/write/readback adapters remain blocked.
- Non-simulated live apply remains blocked until adapters are implemented and explicitly approved.

### Slice 0004-Z | 2026-06-13 | Public-Web Search Request Artifacts

Implemented:

- Added `enrichment_public_web_request.json` artifacts for public-web enrichment requests.
- Public-web request artifacts include observed card fields, deterministic search queries, search URLs, operator/search-agent instructions, max query count, and readiness status.
- Public-web request artifacts record `network_calls_made = 0` and `search_calls_attempted = 0`.
- Service `request_enrichment` writes public-web request artifacts for `public_web` and `all` modes before result scoring.
- CLI/API/MCP enrichment surfaces receive the new payload through the shared service method without adding duplicate orchestration logic.

Validation:

- `.venv/bin/python -m pytest tests/test_enrichment.py tests/test_cli_surfaces.py tests/test_mcp.py tests/test_api.py -q` passed with 32 tests.

Remaining:

- Real public-web search execution remains blocked until an explicit operator/search-adapter action is approved.
- Apollo live API calls remain blocked behind explicit operator request and future adapter implementation.
- Live Google Contacts and Odoo/Odollo lookup/write/readback adapters remain blocked.

### Slice 0004-AA | 2026-06-13 | Apply Pilot Readiness Artifact

Implemented:

- Added `sink_apply_pilot_readiness.json` artifacts for explicit one-job live apply pilot readiness.
- Pilot readiness artifacts summarize preflight, apply decision, write adapter request, sink readiness, readback adapter availability, missing requirements, and operator commands.
- Pilot readiness artifacts record `can_apply_pilot = false`, `writes_attempted = 0`, and `network_calls_made = 0`.
- Service, CLI, API, and MCP surfaces can create the pilot readiness artifact through shared service logic.
- Agent next actions now recommend `sinks apply-pilot-readiness` after an approved sink apply decision and before the manual `sinks apply --apply` boundary.
- Safe agent-loop execution can create the readiness artifact but still skips manual apply approval and live apply.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py -q` passed with 60 tests.

Remaining:

- Live apply pilots remain blocked until live adapters and an explicit operator-approved pilot are implemented.
- Live Google Contacts and Odoo/Odollo lookup/write/readback adapters remain blocked.
- Non-simulated live apply remains blocked until adapters are implemented and explicitly approved.

### Slice 0004-AB | 2026-06-13 | Paid Provider Result Artifacts

Implemented:

- Added Apollo-style paid provider result scoring for caller-supplied fixture/provider rows.
- Added `enrichment_provider_result.json` artifacts with normalized person/company fields, confidence signals, merge proposals, and raw fixture rows.
- API-only enrichment requests now also write `enrichment_result.json` from provider results so the existing enrichment merge review path remains shared.
- Provider result artifacts record `network_calls_made = 0` and `paid_api_calls_attempted = 0`.
- Service, CLI, API, and MCP enrichment request surfaces accept `provider_results` / `--provider-results-json`.
- Provider result tests cover service, CLI, API, MCP, and secret-free payload behavior.

Validation:

- `.venv/bin/python -m pytest tests/test_enrichment.py tests/test_cli_surfaces.py tests/test_mcp.py tests/test_api.py -q` passed with 34 tests.

Remaining:

- Apollo live API calls remain blocked behind explicit operator request and future adapter implementation.
- Real public-web search execution remains blocked until an explicit operator/search-adapter action is approved.
- Live Google Contacts and Odoo/Odollo lookup/write/readback adapters remain blocked.

### Slice 0004-AC | 2026-06-13 | Route Refresh After Review Changes

Implemented:

- Added `route_refresh.json` artifacts when reviewed contact data, approved enrichment merges, or duplicate resolution decisions make existing route artifacts stale.
- Route refresh artifacts preserve the stale artifact kinds, refreshed artifact kinds, pending artifact kinds, reason, reviewer, and zero-write/zero-network counters.
- Next-action readback now honors pending route refresh state before trusting existing lookup, duplicate, sink plan, preflight, decision, readiness, apply, or readback artifacts.
- Safe agent-loop execution can replay zero-network/zero-write route phases from the first stale artifact.
- Manual apply decisions are not reused after route-refresh invalidation; the next-action engine stops again at `decide_sink_apply` when a previous decision was stale.
- Refresh updates are ledgered with `route_refresh_requested` and `route_refresh_updated` events.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py -q` passed with 38 tests.
- `.venv/bin/python -m pytest -q` passed with 128 tests.
- `PYTHONPATH=src pytest -q` passed with 124 tests and 3 skipped optional-extra tests.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed with the index up to date.
- `.venv/bin/bcw mcp-call business_card_watchdog_status --arguments-json '{}'` passed against the user config.

Remaining:

- Route refresh does not delete old route artifacts; it relies on the refresh artifact and latest file contents for current-state readback.
- Live GWS/Odollo lookup/write/readback adapters remain blocked pending explicit pilot work.
- Public-web and paid API enrichment execution remain explicit follow-on actions.

### Slice 0004-AD | 2026-06-13 | Batch Review Bundle Surface

Implemented:

- Added run-level `review_bundle.json` artifacts for operator/agent batch review.
- Review bundles inline current review-relevant artifact payloads for each job, including contact candidates, reviewed contacts, enrichment artifacts, duplicate assessments, sink plans, route refresh state, apply gates, and adapter requests.
- Review bundles include per-job next-action readback and command hints while keeping all decisions routed through existing service methods.
- Added service `review_bundle`, CLI `bcw reviews bundle`, API `POST /runs/{run_id}/review-bundle`, and MCP `business_card_watchdog_review_bundle`.
- Review bundle creation records `review_bundle_created` events and a run-level `review_bundle` artifact record with `job_id = "__run__"`.
- Review bundle artifacts record `writes_attempted = 0` and `network_calls_made = 0`.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py -q` passed with 63 tests.
- `.venv/bin/python -m pytest -q` passed with 128 tests.
- `PYTHONPATH=src pytest -q` passed with 124 tests and 3 skipped optional-extra tests.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed with the index up to date.
- `.venv/bin/bcw mcp-call business_card_watchdog_status --arguments-json '{}'` passed against the user config.

Remaining:

- This is still a JSON artifact surface, not a spreadsheet or local web UI.
- Review decision import from a workbook remains follow-on work.
- Live sink adapters and enrichment execution remain blocked behind explicit pilot work.

### Slice 0004-AE | 2026-06-13 | Explicit Public-Web Result Import

Implemented:

- Added `enrichment_public_web_result.json` artifacts for explicit operator/search-agent public-web result submission.
- Public-web result artifacts consume an existing `enrichment_public_web_request.json`, preserve source request metadata, score submitted results, and emit reviewable merge proposals.
- Shared `enrichment_result.json` is written from the public-web result artifact so the existing enrichment merge review path remains shared.
- Added service `record_public_web_enrichment_results`.
- Added CLI `bcw enrichment public-web-results`.
- Added API `POST /jobs/{job_id}/enrichment/public-web-results`.
- Added MCP tool `business_card_watchdog_public_web_enrichment_results`.
- Result import records `network_calls_made = 0` and `search_calls_attempted = 0`; actual web search remains an explicit external/operator action.

Validation:

- `.venv/bin/python -m pytest tests/test_enrichment.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py -q` passed with 38 tests.
- `.venv/bin/python -m pytest -q` passed with 132 tests.
- `PYTHONPATH=src pytest -q` passed with 127 tests and 3 skipped optional-extra tests.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed with the index up to date.
- `.venv/bin/bcw mcp-call business_card_watchdog_status --arguments-json '{}'` passed against the user config.

Remaining:

- No live browser/search provider is invoked by this slice.
- Paid API execution remains blocked behind explicit config and request approval.
- Enrichment merge still requires review approval before changing reviewed contact data.

### Slice 0004-AF | 2026-06-13 | Contact Points And Normalization Metadata

Implemented:

- Added `[normalization] default_country` user config with default `US`.
- Orchestrator contact candidate creation now uses the configured normalization default country.
- Review corrections and enrichment merge approval now use the configured normalization default country.
- Contact candidates and reviewed contacts now include a `normalization` metadata block.
- Normalized fields now include `confidence` and `reason` metadata.
- Contact candidates and reviewed contacts now include `contact_points` for email, phone, and website with value, raw observed value, source, confidence, and reason.
- Non-US/default-country phone numbers that cannot be safely normalized to E.164 are retained and marked for review instead of being over-normalized.

Validation:

- `.venv/bin/python -m pytest tests/test_contact.py tests/test_config.py tests/test_service.py tests/test_dry_run_pipeline.py -q` passed with 49 tests.
- `.venv/bin/python -m pytest -q` passed with 134 tests.
- `PYTHONPATH=src pytest -q` passed with 129 tests and 3 skipped optional-extra tests.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed with the index up to date.
- `.venv/bin/bcw mcp-call business_card_watchdog_status --arguments-json '{}'` passed against the user config.

Remaining:

- Address normalization and richer organization/title parsing remain follow-on work.
- Contact-point mapping into future live adapters remains dry-run/request-contract only.
- Odollo helper reuse remains planned for further normalization/contact-point hardening.

### Slice 0004-AG | 2026-06-13 | Batch Review Decision Import

Implemented:

- Added run-scoped `review_decisions_import.json` artifacts for batch review decision imports.
- Batch imports call the existing `submit_review` path for each decision, preserving field validation, state transitions, reviewed-contact writes, duplicate resolution handling, and route refresh behavior.
- Added service `apply_review_decisions`.
- Added CLI `bcw reviews apply-decisions` with `--decisions-json` and `--decisions-file`.
- Added API `POST /runs/{run_id}/review-decisions`.
- Added MCP tool `business_card_watchdog_apply_review_decisions`.
- Import artifacts record `writes_attempted = 0` and `network_calls_made = 0`.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py -q` passed with 66 tests.
- `.venv/bin/python -m pytest -q` passed with 135 tests.
- `PYTHONPATH=src pytest -q` passed with 130 tests and 3 skipped optional-extra tests.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed with the index up to date.
- `.venv/bin/bcw mcp-call business_card_watchdog_status --arguments-json '{}'` passed against the user config.

Remaining:

- Spreadsheet/workbook import remains follow-on work.
- Batch imports are run-scoped; cross-run review imports should be split by run.
- Live sink writes remain explicit and blocked behind apply gates.

### Slice 0004-AH | 2026-06-13 | Public-Web Result Import Budget Guard

Implemented:

- Public-web result imports now enforce the originating `enrichment_public_web_request.json` `max_queries` limit.
- Oversized public-web result imports fail before writing result artifacts.
- `enrichment_public_web_result.json` artifacts now include `max_results` alongside submitted result count and source query count.
- The bound is enforced at the shared service layer used by CLI, API, and MCP.

Validation:

- `.venv/bin/python -m pytest tests/test_enrichment.py -q` passed with 12 tests.
- `.venv/bin/python -m pytest -q` passed with 136 tests.
- `PYTHONPATH=src pytest -q` passed with 131 tests and 3 skipped optional-extra tests.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed with the index up to date.
- `.venv/bin/bcw mcp-call business_card_watchdog_status --arguments-json '{}'` passed against the user config.

Remaining:

- Live browser/search execution remains explicit follow-on work.
- Per-batch aggregate enrichment budgets remain follow-on work.

### Slice 0004-AI | 2026-06-13 | Paid Provider Result Import Budget Guard

Implemented:

- Added `[enrichment] max_paid_provider_results_per_contact` with default `5`.
- Paid-provider request artifacts now include `max_results`.
- Paid-provider result artifacts now include `max_results` and `submitted_result_count`.
- Oversized paid-provider result imports fail before writing provider result artifacts.
- The bound is enforced at the shared service layer used by CLI, API, and MCP.

Validation:

- `.venv/bin/python -m pytest tests/test_config.py tests/test_enrichment.py -q` passed with 18 tests.
- `.venv/bin/python -m pytest -q` passed with 137 tests.
- `PYTHONPATH=src pytest -q` passed with 132 tests and 3 skipped optional-extra tests.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed with the index up to date.
- `.venv/bin/bcw mcp-call business_card_watchdog_status --arguments-json '{}'` passed against the user config.

Remaining:

- Per-batch aggregate enrichment budgets remain follow-on work.
- Live paid-provider API calls remain disabled until an explicit provider adapter and operator approval path are added.

### Slice 0004-AJ | 2026-06-13 | Run Enrichment Budget Readback

Implemented:

- Run summaries now include `enrichment_budget`.
- Public-web budget readback totals request count, result count, requested query budget, submitted result count, search calls attempted, and network calls made.
- Paid-provider budget readback totals request count, result count, configured result budget, submitted result count, paid API calls attempted, and network calls made.
- Budget readback uses existing ledger artifacts and is exposed automatically through existing CLI/API/MCP run-summary surfaces.
- Missing/unreadable enrichment artifacts are counted instead of failing the summary.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py -q` passed with 40 tests.
- `.venv/bin/python -m pytest -q` passed with 138 tests.
- `PYTHONPATH=src pytest -q` passed with 133 tests and 3 skipped optional-extra tests.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed with the index up to date.
- `.venv/bin/bcw mcp-call business_card_watchdog_status --arguments-json '{}'` passed against the user config.

Remaining:

- Per-run hard-stop policy for enrichment budgets remains follow-on work.
- Live paid-provider API calls remain disabled until an explicit provider adapter and operator approval path are added.

### Slice 0004-AK | 2026-06-13 | Run Enrichment Budget Hard Stops

Implemented:

- Added `[enrichment] max_public_web_queries_per_run` with default `200`.
- Added `[enrichment] max_paid_provider_results_per_run` with default `50`.
- Run summaries now report public-web remaining query budget and paid-provider remaining result budget.
- Service enrichment requests refuse before writing new request artifacts when a run-level public-web or paid-provider request budget would be exceeded.
- The hard stop is enforced at the shared service layer used by CLI, API, and MCP.

Validation:

- `.venv/bin/python -m pytest tests/test_config.py tests/test_service.py -q` passed with 47 tests.
- `.venv/bin/python -m pytest -q` passed with 140 tests.
- `PYTHONPATH=src pytest -q` passed with 135 tests and 3 skipped optional-extra tests.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed with the index up to date.
- `.venv/bin/bcw mcp-call business_card_watchdog_status --arguments-json '{}'` passed against the user config.

Remaining:

- Live public-web and paid-provider execution adapters remain explicit follow-on work.
- Budget policy is currently per-run and per-job; cross-run/user-scope spend limits remain follow-on work.

### Slice 0004-AL | 2026-06-13 | Batch Review Bundle Indexing

Implemented:

- Review bundles now include `groups.by_state` for batch triage.
- Review bundles now include `groups.by_next_action` for agent-loop and operator prioritization.
- Each review bundle entry now includes a `decision_template` shaped for `reviews apply-decisions`.
- Review bundles now include a run-level `decision_import_template` array that can be copied into a decision import file.
- Existing CLI/API/MCP review-bundle surfaces expose the richer bundle without adding new orchestration paths.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py -q` passed with 69 tests.
- `.venv/bin/python -m pytest -q` passed with 140 tests.
- `PYTHONPATH=src pytest -q` passed with 135 tests and 3 skipped optional-extra tests.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed with the index up to date.
- `.venv/bin/bcw mcp-call business_card_watchdog_status --arguments-json '{}'` passed against the user config.

Remaining:

- A spreadsheet/HTML review presentation remains follow-on work.
- Decision templates are conservative suggestions and still require operator edits/approval before import.

### Slice 0004-AM | 2026-06-13 | Static HTML Review Surface

Implemented:

- Added a static offline `review_bundle.html` export generated from the artifact-backed review bundle.
- Added service `review_html` with zero network calls and zero sink writes.
- Added CLI `bcw reviews html`.
- Added API `POST /runs/{run_id}/review-html`.
- Added MCP tool `business_card_watchdog_review_html`.
- The HTML review surface includes run summary context, state/action groups, job rows, local image paths, artifact kinds, next actions, and decision templates.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py -q` passed with 69 tests.
- `.venv/bin/python -m pytest -q` passed with 140 tests.
- `PYTHONPATH=src pytest -q` passed with 135 tests and 3 skipped optional-extra tests.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed with the index up to date.
- `.venv/bin/bcw mcp-call business_card_watchdog_status --arguments-json '{}'` passed against the user config.

Remaining:

- Spreadsheet export remains optional follow-on work.
- The static HTML file is read-only; decisions still flow through `reviews apply-decisions` or `jobs review`.

### Slice 0004-AN | 2026-06-13 | Duplicate Resolution Route Refresh Proof

Implemented:

- Added regression coverage proving duplicate-resolution decisions refresh existing route artifacts.
- The test covers a reviewed contact with an existing `sink_plan.json`, a later duplicate resolution, `route_refresh.json` creation, next-action rerouting to `plan_sinks`, and refreshed sink plan duplicate-resolution context.
- No runtime behavior changed; the existing shared service path already created route-refresh artifacts for non-noop duplicate resolutions.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py -q` passed with 43 tests.
- `.venv/bin/python -m pytest -q` passed with 141 tests.
- `PYTHONPATH=src pytest -q` passed with 136 tests and 3 skipped optional-extra tests.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed with the index up to date.
- `.venv/bin/bcw mcp-call business_card_watchdog_status --arguments-json '{}'` passed against the user config.

Remaining:

- Additional route-refresh coverage for lookup-result and apply-preflight invalidation remains useful follow-on work.

### Slice 0004-AO | 2026-06-13 | Full Route Refresh Chain Proof

Implemented:

- Strengthened review-update route-refresh regression coverage to prove the full existing downstream chain is marked stale.
- The test now verifies stale and refreshed route artifact kinds for lookup plan, lookup adapter request, lookup result, downstream duplicate assessment, sink plan, write adapter request, and apply preflight.
- The test snapshots old route artifacts and proves refreshed lookup and sink plans use the corrected reviewed email.
- No runtime behavior changed; this locks in the existing safe agent-loop refresh semantics.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py -q` passed with 43 tests.
- `.venv/bin/python -m pytest -q` passed with 141 tests.
- `PYTHONPATH=src pytest -q` passed with 136 tests and 3 skipped optional-extra tests.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed with the index up to date.
- `.venv/bin/bcw mcp-call business_card_watchdog_status --arguments-json '{}'` passed against the user config.

Remaining:

- Route-refresh semantics for future live lookup/apply artifacts should be extended when those adapters are implemented.

### Slice 0004-AP | 2026-06-13 | Profile URL Contact Points

Implemented:

- Contact candidates now derive `profile_url` contact points from extra profile/social URL fields such as `linkedin`, `linkedin_url`, `profile_url`, `social_url`, and `social_profile`.
- Profile URLs are normalized with scheme, host casing, `www.` removal, and trailing-slash cleanup.
- Reviewed contacts and enrichment-merged contacts now preserve `extras` from the base candidate.
- Profile URL contact points remain outside canonical flat contact fields, so they cannot overwrite card-observed name, email, phone, website, or notes.

Validation:

- `.venv/bin/python -m pytest tests/test_contact.py -q` passed with 5 tests.
- `.venv/bin/python -m pytest -q` passed with 142 tests.
- `PYTHONPATH=src pytest -q` passed with 137 tests and 3 skipped optional-extra tests.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed with the index up to date.
- `.venv/bin/bcw mcp-call business_card_watchdog_status --arguments-json '{}'` passed against the user config.

### Slice 0004-AQ | 2026-06-13 | Profile URL Sink Mapping

Implemented:

- Service route planning now preserves `contact_points` from contact candidate and reviewed contact artifacts.
- Sink payloads now carry additive `contact_points` metadata when present.
- GWS write adapter requests now map website/profile URLs into People API `urls` without overwriting canonical contact slots.
- Odollo write adapter requests now include profile URLs in the additive `contact_point_plan`.
- Tests cover direct sink payload/adaptor contracts and the service route planning boundary.

Validation:

- `.venv/bin/python -m pytest tests/test_sinks.py tests/test_service.py -q` passed with 61 tests.
- `.venv/bin/python -m pytest -q` passed with 143 tests.
- `PYTHONPATH=src pytest -q` passed with 138 tests and 3 skipped optional-extra tests.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed with the index up to date.
- `.venv/bin/bcw mcp-call business_card_watchdog_status --arguments-json '{}'` passed against the user config.

Remaining:

- Live sink adapters still need explicit read-only lookup pilots before any write behavior can use these mapped fields.

### Slice 0004-AR | 2026-06-13 | Public-Web Search Handoff

Implemented:

- Added `enrichment_public_web_search_handoff.json` artifacts generated from existing `enrichment_public_web_request.json` artifacts.
- Handoff artifacts preserve source request status, query count, max query budget, zero-network counters, operator instructions, and explicit CLI/API/MCP result-import surfaces.
- Added service `build_public_web_enrichment_handoff`.
- Added CLI `bcw enrichment public-web-handoff`.
- Added API `POST /jobs/{job_id}/enrichment/public-web-handoff`.
- Added MCP tool `business_card_watchdog_public_web_enrichment_handoff`.
- Review bundle indexing now includes the handoff artifact kind.

Validation:

- `.venv/bin/python -m pytest tests/test_enrichment.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py -q` passed with 42 tests.
- `.venv/bin/python -m pytest -q` passed with 145 tests.
- `PYTHONPATH=src pytest -q` passed with 140 tests and 3 skipped optional-extra tests.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed with the index up to date.
- `.venv/bin/bcw mcp-call business_card_watchdog_status --arguments-json '{}'` passed against the user config.

Remaining:

- Live public-web search execution remains explicit follow-on work; this slice only prepares a deterministic handoff for an operator or search agent.

### Slice 0004-AS | 2026-06-13 | Paid Provider Handoff And Result Import

Implemented:

- Added `enrichment_provider_handoff.json` artifacts generated from existing `enrichment_provider_request.json` artifacts.
- Provider handoffs carry approval state, key environment variable name, request fields, max result budget, zero-call counters, and explicit CLI/API/MCP result-import surfaces without writing credential values.
- Added service `build_provider_enrichment_handoff`.
- Added service `record_provider_enrichment_results` so provider results can be imported after the original request artifact exists.
- Added CLI `bcw enrichment provider-handoff` and `bcw enrichment provider-results`.
- Added API `POST /jobs/{job_id}/enrichment/provider-handoff` and `POST /jobs/{job_id}/enrichment/provider-results`.
- Added MCP tools `business_card_watchdog_provider_enrichment_handoff` and `business_card_watchdog_provider_enrichment_results`.
- Review bundle indexing now includes the provider handoff artifact kind.

Validation:

- `.venv/bin/python -m pytest tests/test_enrichment.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py -q` passed with 44 tests.
- `.venv/bin/python -m pytest -q` passed with 147 tests.
- `PYTHONPATH=src pytest -q` passed with 142 tests and 3 skipped optional-extra tests.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed with the index up to date.
- `.venv/bin/bcw mcp-call business_card_watchdog_status --arguments-json '{}'` passed against the user config.

Remaining:

- Live paid-provider API execution remains explicit follow-on work and must stay behind config plus request-level approval.

### Slice 0004-AT | 2026-06-13 | Read-Only Sink Lookup Pilot

Implemented:

- Added `sink_lookup_pilot.json` artifacts for explicit one-job read-only lookup pilots.
- Lookup pilots require `run_id`, `job_id`, `sink`, and `approved_by` and currently accept mocked/read-only match rows without invoking live adapters.
- Lookup pilots write the existing `sink_lookup_result.json` schema so downstream duplicate assessment and routing review continue to use the shared path.
- Added CLI `bcw sinks lookup-pilot`.
- Added API `POST /jobs/{job_id}/sink-lookup-pilot`.
- Added MCP tool `business_card_watchdog_sink_lookup_pilot`.
- Review bundle and route-refresh artifact registries now include `sink_lookup_pilot`.

Validation:

- `.venv/bin/python -m pytest tests/test_sinks.py tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py -q` passed with 91 tests.
- `.venv/bin/python -m pytest -q` passed with 150 tests.
- `PYTHONPATH=src pytest -q` passed with 144 tests and 3 skipped optional-extra tests.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed with the index up to date.
- `.venv/bin/bcw mcp-call business_card_watchdog_status --arguments-json '{}'` passed against the user config.

Remaining:

- Live GWS/Odollo read-only adapter execution remains manual follow-on work; default tests continue to use mocked rows and make no network calls.

### Slice 0004-AU | 2026-06-13 | Read-Only Lookup Adapter Boundary

Implemented:

- Added `sink_lookup_adapters.py` with explicit read-only lookup adapter execution boundaries.
- GWS People lookup responses are normalized into existing match rows with `resource_id`, confidence, basis, display, and raw evidence.
- Odollo/Odoo `res.partner` lookup rows are normalized into the same match-row shape using `odoo:res.partner:{id}` resource IDs.
- `BusinessCardService.execute_sink_lookup_pilot_for_job(..., simulate=False)` can now use an injected read-only lookup executor and records adapter execution evidence in `sink_lookup_pilot.json`.
- Non-simulated pilot results update `sink_lookup_result.json` with read-only status and network-call count while keeping `writes_attempted = 0`.

Validation:

- `.venv/bin/python -m pytest tests/test_sink_lookup_adapters.py tests/test_sinks.py tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py -q` passed with 94 tests.
- `.venv/bin/python -m pytest -q` passed with 153 tests.
- `PYTHONPATH=src pytest -q` passed with 147 tests and 3 skipped optional-extra tests.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed with the index up to date.
- `.venv/bin/bcw mcp-call business_card_watchdog_status --arguments-json '{}'` passed against the user config.

Remaining:

- Real GWS and Odollo runner construction remains manual follow-on work; this slice establishes the adapter boundary and mocked execution proof without invoking live services.

### Slice 0004-AV | 2026-06-13 | Read-Only Lookup Runner Construction

Implemented:

- Added default GWS lookup runner construction for explicit non-simulated lookup pilots.
- GWS lookup runner uses the existing adapter request `gws_command` plus `--params <json>` and `--format json`, then parses the returned JSON.
- Added default Odollo/Odoo lookup runner construction for explicit non-simulated lookup pilots.
- Odollo runner loads the configured tenant profile via Odollo config and performs `OdooClient.search_read` only.
- Added offline tests that mock the GWS command runner and Odollo client, proving command/search parameters without making network calls.

Validation:

- `.venv/bin/python -m pytest tests/test_sink_lookup_adapters.py tests/test_service.py tests/test_sinks.py -q` passed with 68 tests.
- `.venv/bin/python -m pytest -q` passed with 155 tests.
- `PYTHONPATH=src pytest -q` passed with 149 tests and 3 skipped optional-extra tests.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed with the index up to date.
- `.venv/bin/bcw mcp-call business_card_watchdog_status --arguments-json '{}'` passed against the user config.

Remaining:

- Live smoke execution still requires explicit `lookup-pilot --no-simulate` on a selected run/job/sink and local GWS/Odollo auth.

## Next High-Level Plan

The next execution block should turn the current artifact-first scaffolding into an operator-usable review and routing system while preserving the current safety boundaries: no paid enrichment unless explicitly requested, no live sink writes without an approved pilot, and no secret values in repo artifacts or logs.

### Current Capability Baseline

Already in place:

- review queue and run summary readbacks through shared service, CLI, API, and MCP surfaces
- reviewed-contact artifacts for operator corrections and approved enrichment merges
- contact candidate normalization with observed-vs-normalized provenance
- public-web and paid-provider enrichment request/result artifacts from caller-supplied fixture rows
- explicit paid enrichment gate using configured key names from `~/credentials/API-keys.env`
- local and downstream duplicate assessment artifacts
- duplicate resolution review actions
- dry-run sink lookup plans, sink plans, adapter request contracts, apply preflight, apply decisions, simulated apply/readback, and one-job apply pilot readiness
- deterministic next-action readback and safe zero-network/zero-write agent-loop executor
- local GWS and Odollo readiness evidence without live API calls

Still needed before production use:

- a review surface that humans can efficiently use for batches, not just JSON readback
- route-plan freshness after reviewed contact updates and duplicate/enrichment resolution
- stronger normalization and merge policy copied/adapted from Odollo where it is already proven
- concrete, explicit public-web enrichment execution path
- concrete, explicit paid API enrichment adapter path
- live read-only lookup pilots for GWS and Odollo before any write pilot
- live one-job write/readback pilots only after lookup, dedupe, readiness, and operator approval gates pass

### NP1. Batch Review Surface

Purpose:

Give operators a practical way to inspect imported cards, OCR/App Intelligence output, normalized contacts, enrichment proposals, duplicate findings, and sink decisions before any live write.

Deliverables:

- CLI/API/MCP review readbacks remain the canonical machine surfaces.
- Add a generated local review workbook or local web review queue that groups cards by state:
  - needs review
  - enrichment proposed
  - duplicate review required
  - ready to route
  - apply approval required
  - failed or skipped
- Include image thumbnail/path, preclassification evidence, card-observed fields, normalized fields, reviewed contact, duplicate candidates, enrichment proposals, planned sinks, and next recommended action.
- Add batch commands to export review packets and import approved review decisions.
- Keep review decisions artifact-backed so the agent loop can resume without UI state.

Acceptance:

- A batch of jobs can be reviewed without opening individual artifact files.
- Review decisions still flow through `submit_review` or equivalent shared service methods.
- Every operator decision creates a durable artifact and ledger event.
- No review surface stores private card data in the repo.

Suggested subagent brief:

```text
You are NP1 Review Surface subagent. Build an operator-usable batch review surface on top of the existing service methods and artifacts. Prefer a generated local workbook or lightweight local web queue, but keep the shared service layer authoritative. Include cards, normalized fields, enrichment proposals, duplicate findings, sink plans, and next actions. Do not add live sink writes or paid enrichment calls. Return changed files, screenshots or sample artifacts if applicable, and tests.
```

### NP2. Route Refresh And Agent-Loop Coherency

Purpose:

Ensure reviewed-contact, enrichment-merge, and duplicate-resolution changes invalidate or refresh stale downstream route artifacts before the safe agent loop continues.

Deliverables:

- `route_refresh.json` or equivalent artifact whenever reviewed contact data changes after routing artifacts already exist.
- Automatic zero-network refresh of sink lookup plans and sink plans from the latest reviewed contact when safe.
- Next-action logic that does not treat stale lookup/plan/apply artifacts as current after review changes.
- Explicit ledger events for route refresh, skipped refresh, and refresh blockers.
- Tests for approval-after-plan, enrichment-merge-after-plan, and duplicate-resolution-after-plan cases.

Acceptance:

- If an operator changes email, phone, organization, name, or routing-relevant fields, the next sink lookup/plan uses the reviewed value.
- Safe agent-loop execution can refresh zero-network route artifacts but still skips manual approval and live apply boundaries.
- Existing artifacts are preserved as audit history rather than silently deleted.

Suggested subagent brief:

```text
You are NP2 Route Refresh subagent. Inspect review submission, next-action, sink lookup planning, and sink planning code. Add artifact-backed route refresh semantics so reviewed-contact and duplicate/enrichment decisions cannot leave stale sink plans active. Preserve old artifacts as audit evidence. Do not call external services. Return tests showing corrected reviewed fields are used in refreshed route artifacts.
```

### NP3. Normalization And Merge Policy Hardening

Purpose:

Improve contact quality before enrichment or routing, while keeping card-observed evidence authoritative.

Sources to inspect/adapt:

- Odollo contact normalization and contact-point handling helpers
- Odollo review/action semantics where useful
- Existing `business-card-watchdog.contact` normalization functions

Deliverables:

- stronger phone normalization with default-country config and review fallback
- address and organization/title normalization placeholders
- contact-point model for email, phone, website, social/profile URLs, and source evidence
- merge policy that distinguishes:
  - card-observed canonical fields
  - operator-corrected fields
  - enrichment proposals
  - downstream existing-contact values
- confidence/reason fields for every proposed normalized value

Acceptance:

- Normalization never invents missing identity fields.
- Enrichment can propose additional fields but cannot overwrite card-observed or operator-corrected values without explicit approval.
- Sink plans can map contact points into GWS and Odollo payloads without destructive overwrites.

Suggested subagent brief:

```text
You are NP3 Normalization subagent. Inspect Odollo contact-point and normalization helpers plus this repo's contact and sink payload code. Harden normalization and merge policy around provenance, contact points, and confidence. Keep output schema backward compatible where possible. Do not perform enrichment or sink calls. Return schema examples and tests.
```

### NP4. Explicit Enrichment Execution Paths

Purpose:

Make enrichment useful without letting a generic agent loop spend money or leak secrets.

Rules:

- API-based enrichment generally has cost and must be explicitly requested.
- Public-web enrichment can be useful, but execution should still be an explicit operator/search-agent action with query and result artifacts.
- API keys may be read from `~/credentials/API-keys.env` only by name and only by the adapter that needs them; never print or persist values.

Deliverables:

- Public-web execution adapter or browser/search-agent handoff that consumes `enrichment_public_web_request.json` and writes result fixtures back into the existing result scorer.
- Paid provider adapter copied/adapted from Odollo Apollo tooling, behind both config `allow_paid_api = true` and request-level `allow_paid_enrichment = true`.
- Per-job and per-batch budget/call-count limits.
- Enrichment event log fields for provider, mode, requested_by, cost_class, call count, and result artifact path.
- Operator command examples for public-web enrichment and paid API enrichment.

Acceptance:

- Default tests and safe agent-loop runs make zero network calls and zero paid API calls.
- Public-web execution is explicit and bounded.
- Paid API execution refuses unless both config and command/request approval are present.
- Results still enter review as merge proposals, not direct overwrites.

Suggested subagent brief:

```text
You are NP4 Enrichment Adapter subagent. Inspect Odollo Apollo and public-web enrichment code plus this repo's enrichment artifact contracts. Add explicit execution paths that consume existing request artifacts and write existing result schemas. Keep paid API calls behind config and request-level approval. Never print secrets. Default tests must use fixtures and make no network calls.
```

### NP5. Sink Lookup Pilots Before Write Pilots

Purpose:

Move from blocked adapter request contracts to approved read-only lookup pilots for GWS and Odollo, then use lookup evidence to improve dedupe and routing decisions.

Deliverables:

- GWS People read-only lookup adapter using the existing `gws` command vectors.
- Odollo/Odoo read-only lookup adapter using tenant readiness patterns copied/adapted from Odollo.
- Lookup pilot command that requires explicit run/job/sink selection.
- Lookup result artifact populated from live read-only responses.
- Downstream duplicate assessment from live lookup result.
- Readiness evidence that distinguishes local auth presence, live read-only probe success, and write-disabled state.

Acceptance:

- Live lookup pilots do not write to GWS or Odollo.
- A live lookup result can block routing as duplicate review when matches are found.
- Lookup artifacts include enough resource IDs and match basis to support later update/noop/create planning.
- Tests mock `gws` and Odollo clients; live pilots are manual smoke tests only.

Suggested subagent brief:

```text
You are NP5 Read-Only Sink Lookup subagent. Implement explicit one-job read-only lookup pilots for GWS and Odollo using existing adapter request contracts. Mock all live calls in tests. Do not implement writes. Return readiness behavior, lookup artifacts, and duplicate-assessment evidence.
```

### NP6. One-Job Live Apply Pilot

Purpose:

Only after review, enrichment, dedupe, route refresh, read-only lookup, preflight, apply decision, and pilot readiness are satisfied, allow one explicitly selected contact to be written and read back.

Deliverables:

- per-sink live apply adapter implementation for the selected pilot sink
- strict one-job apply command requiring `--apply`, approved `sink_apply_decision.json`, and passing `sink_apply_pilot_readiness.json`
- readback verification artifact
- idempotent retry behavior keyed by serialization key and downstream resource ID
- rollback/remediation note when rollback is not feasible

Acceptance:

- The first live pilot cannot run from safe agent-loop execution.
- The command must name run ID, job ID, and sink.
- Readback proves the created/updated contact exists with expected fields.
- Failed write/readback leaves an explicit recovery artifact and does not mark the job successfully routed.

Suggested subagent brief:

```text
You are NP6 Live Apply Pilot subagent. Implement the smallest one-job live apply path for one approved sink after all readiness, duplicate, preflight, decision, and pilot-readiness gates pass. Keep tests mocked. Do not run a live write unless the primary agent provides an explicit approved run ID, job ID, and sink. Return readback schema, recovery behavior, and validation commands.
```

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
max_public_web_queries_per_run = 200
max_paid_provider_results_per_contact = 5
max_paid_provider_results_per_run = 50

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

## Execution Log

### Slice 0004-AW | 2026-06-13 | Mock Apply Pilot Readiness Gate

Implemented:

- `sink_apply_pilot_readiness.json` now distinguishes mock-apply readiness from live-apply readiness.
- Simulated apply now requires or creates a ready pilot-readiness artifact before emitting the local mock apply result.
- Mock apply readiness is gated by local preflight, explicit apply approval, and local mock readback availability.
- Live apply remains blocked behind live sink readiness plus write/readback adapter evidence.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py tests/test_sinks.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py -q` passed with 93 tests.
- `.venv/bin/python -m pytest -q` passed with 156 tests.
- `PYTHONPATH=src pytest -q` passed with 150 tests and 3 skipped optional-extra tests.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed with the index up to date.
- `.venv/bin/bcw mcp-call business_card_watchdog_status --arguments-json '{}'` passed against the user config.

Remaining:

- Live write/readback adapters remain follow-on work; this slice only makes the mock pilot readiness gate meaningful.

### Slice 0004-AX | 2026-06-13 | Write And Readback Adapter Boundary

Implemented:

- Added `sink_apply_adapters.py` with explicit write and readback adapter execution boundaries for GWS People and Odollo/Odoo.
- GWS write/readback runners construct command-vector calls from existing adapter request contracts and parse JSON responses.
- Odollo write/readback runners use `OdooClient.create` and `OdooClient.read` through the configured tenant profile when invoked.
- Adapter execution results normalize resource IDs, write counters, network counters, and readback evidence into deterministic payloads.
- `BusinessCardService` now supports an injected write executor for one-job pilot tests, while default CLI/API/MCP service construction still leaves non-simulated live apply blocked.
- Injected write execution records `live_applied` apply results and carries the returned resource ID into the existing readback adapter request path.

Validation:

- `.venv/bin/python -m pytest tests/test_sink_apply_adapters.py tests/test_service.py tests/test_sinks.py -q` passed with 74 tests.
- `.venv/bin/python -m pytest tests/test_sink_apply_adapters.py tests/test_service.py tests/test_sinks.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py -q` passed with 102 tests.
- `.venv/bin/python -m pytest -q` passed with 165 tests.
- `PYTHONPATH=src pytest -q` passed with 159 tests and 3 skipped optional-extra tests.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed with the index up to date.
- `.venv/bin/bcw mcp-call business_card_watchdog_status --arguments-json '{}'` passed against the user config.

Remaining:

- Public CLI/API/MCP live write execution remains blocked pending an explicit operator-approved pilot surface.
- Live readback execution is available as an adapter boundary but is not yet wired into a public pilot command.

### Slice 0004-AY | 2026-06-13 | Explicit Readback Pilot Surface

Implemented:

- Added `sink_readback_pilot.json` artifacts for explicit read-only sink readback verification.
- Added `BusinessCardService.execute_sink_readback_pilot_for_job` with simulated readback by default and injected/live readback execution when explicitly requested.
- Readback pilots require `job_id`, `run_id`, `sink`, and `approved_by`; they always record `writes_attempted = 0`.
- Added CLI `bcw sinks readback-pilot`.
- Added API `POST /jobs/{job_id}/sink-readback-pilot`.
- Added MCP tool `business_card_watchdog_sink_readback_pilot`.
- Next-action readback now recommends the explicit readback pilot after a readback adapter request exists, but the safe agent-loop executor does not run it automatically.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py tests/test_sink_apply_adapters.py -q` passed with 87 tests.
- `.venv/bin/python -m pytest tests/test_service.py tests/test_sinks.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py tests/test_sink_apply_adapters.py -q` passed with 105 tests.
- `.venv/bin/python -m pytest -q` passed with 168 tests.
- `PYTHONPATH=src pytest -q` passed with 161 tests and 3 skipped optional-extra tests.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed with the index up to date.
- `.venv/bin/bcw mcp-call business_card_watchdog_status --arguments-json '{}'` passed against the user config.

Remaining:

- Live readback still requires explicit `--no-simulate`/API/MCP request and local sink auth; default tests remain offline.
- Live write execution remains available only through injected service proof pending a public one-job write pilot command.

### Slice 0004-AZ | 2026-06-13 | Explicit Write Pilot Surface

Implemented:

- Added `sink_write_pilot.json` artifacts for explicit one-job sink write pilot evidence.
- Added `BusinessCardService.execute_sink_write_pilot_for_job`, simulated by default and live only on explicit non-simulated execution.
- Write pilots require `job_id`, `run_id`, `sink`, `approved_by`, and an approved sink apply decision.
- Simulated write pilots record zero writes and still produce a `sink_apply_result.json` so readback adapter requests and readback pilots can continue through the existing path.
- Non-simulated default execution refuses unless `sink_apply_pilot_readiness.json` reports live pilot readiness; injected tests can exercise live-shaped writes offline.
- Added CLI `bcw sinks write-pilot`.
- Added API `POST /jobs/{job_id}/sink-write-pilot`.
- Added MCP tool `business_card_watchdog_sink_write_pilot`.
- Next-action readback now recommends explicit write pilot after apply pilot readiness; safe agent-loop execution still skips it.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py tests/test_sink_apply_adapters.py -q` passed with 89 tests.
- `.venv/bin/python -m pytest tests/test_service.py tests/test_sinks.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py tests/test_sink_apply_adapters.py -q` passed with 107 tests.
- `.venv/bin/python -m pytest -q` passed with 170 tests.
- `PYTHONPATH=src pytest -q` passed with 163 tests and 3 skipped optional-extra tests.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed with the index up to date.
- `.venv/bin/bcw mcp-call business_card_watchdog_status --arguments-json '{}'` passed against the user config.

Remaining:

- Real live write pilots still require explicit non-simulated invocation plus local sink readiness and auth.
- Readback remains a separate explicit pilot step after write evidence exists.

### Slice 0004-BA | 2026-06-13 | Apply Pilot Report Surface

Implemented:

- Added `sink_apply_pilot_report.json` artifacts that summarize readiness, write pilot, apply result, readback adapter request, and readback pilot evidence.
- Reports compute complete/incomplete state, missing required artifacts, per-sink resource IDs, simulated/live flags, readback match status, write counters, and network counters.
- Added service `build_sink_apply_pilot_report_for_job`.
- Added CLI `bcw sinks apply-pilot-report`.
- Added API `POST /jobs/{job_id}/sink-apply-pilot-report`.
- Added MCP tool `business_card_watchdog_sink_apply_pilot_report`.
- Next-action readback now recommends report creation after explicit write and readback pilot evidence exists; safe agent-loop execution may create the zero-write report.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py tests/test_sink_apply_adapters.py -q` passed with 90 tests.
- `.venv/bin/python -m pytest tests/test_service.py tests/test_sinks.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py tests/test_sink_apply_adapters.py -q` passed with 108 tests.
- `.venv/bin/python -m pytest -q` passed with 171 tests.
- `PYTHONPATH=src pytest -q` passed with 164 tests and 3 skipped optional-extra tests.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed with the index up to date.
- `.venv/bin/bcw mcp-call business_card_watchdog_status --arguments-json '{}'` passed against the user config.

Remaining:

- Reports summarize existing pilot artifacts only; they do not perform live writes, readbacks, or external readiness probes.

### Slice 0004-BB | 2026-06-13 | Review Bundle Sink Pilot Status

Implemented:

- Added per-job `sink_pilot_status` summaries to `review_bundle.json`.
- Status summaries include completed sink pilot artifact kinds, latest pilot stage, report completion, write/readback/report booleans, safe-next-action state, explicit-operator-action state, write counters, network counters, and report sink readback evidence.
- Added `groups.by_sink_pilot_state` so batch review and agent-loop consumers can count jobs by pilot progress without opening every artifact.
- Added the same sink pilot status to the static offline review HTML export.
- Added service tests for a full simulated lookup, downstream dedupe, sink plan, write pilot, readback pilot, and apply-pilot-report chain as shown through the review bundle.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_review_bundle_includes_sink_pilot_status tests/test_service.py::test_service_apply_pilot_report_summarizes_write_and_readback tests/test_service.py::test_service_run_summary_and_review_queue -q` passed with 3 tests.
- `.venv/bin/python -m pytest tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py -q` passed with 83 tests.
- `.venv/bin/python -m pytest -q` passed with 172 tests.
- `PYTHONPATH=src pytest -q` passed with 165 tests and 3 skipped optional-extra tests.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed with the index up to date.
- `.venv/bin/bcw mcp-call business_card_watchdog_status --arguments-json '{}'` passed against the user config.

Remaining:

- The review bundle summarizes pilot state only; explicit write/readback pilots and paid/provider-backed enrichment remain separate operator-approved actions.

### Slice 0004-BC | 2026-06-13 | Run Summary Sink Pilot Progress

Implemented:

- Added `sink_pilot_summary` to run summaries for batch-level sink pilot progress readback.
- The summary reuses the same per-job sink pilot status vocabulary as review bundles.
- Summary counts now include jobs by sink pilot state, write-pilot count, readback-pilot count, pilot-report count, complete-report count, safe auto-continue count, explicit-operator-action count, write counters, network counters, and compact per-job status rows.
- CLI/API/MCP run-summary consumers receive the new progress object through the existing shared service method.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_review_bundle_includes_sink_pilot_status tests/test_service.py::test_service_run_summary_and_review_queue -q` passed with 2 tests.
- `.venv/bin/python -m pytest tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py -q` passed with 83 tests.
- `.venv/bin/python -m pytest -q` passed with 172 tests.
- `PYTHONPATH=src pytest -q` passed with 165 tests and 3 skipped optional-extra tests.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed with the index up to date.
- `.venv/bin/bcw mcp-call business_card_watchdog_status --arguments-json '{}'` passed against the user config.

Remaining:

- Run summaries still report existing artifacts only; explicit write/readback pilots and paid/provider-backed enrichment remain separate operator-approved actions.

### Slice 0004-BD | 2026-06-13 | Batch Phase Report Surface

Implemented:

- Added a read-only `phase_report` service method for deterministic batch progress readback.
- Phase reports group each job by pipeline phases: ingest, normalize, review, enrichment, dedupe, route, sink lookup, apply approval, write pilot, readback pilot, and pilot report.
- Phase reports count per-phase states and blocked/explicit-required next actions without executing work.
- Added CLI `bcw runs phase-report`.
- Added API `GET /runs/{run_id}/phase-report`.
- Added MCP tool `business_card_watchdog_phase_report`.
- Covered blocked-review and complete simulated-pilot phase states through service, CLI, API, and MCP tests.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_run_summary_and_review_queue tests/test_service.py::test_service_review_bundle_includes_sink_pilot_status tests/test_cli_surfaces.py::test_cli_runs_and_jobs_use_recorded_runtime_state tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 6 tests.
- `.venv/bin/python -m pytest tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py -q` passed with 83 tests.
- `.venv/bin/python -m pytest -q` passed with 172 tests.
- `PYTHONPATH=src pytest -q` passed with 165 tests and 3 skipped optional-extra tests.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed with the index up to date.
- `.venv/bin/bcw mcp-call business_card_watchdog_status --arguments-json '{}'` passed against the user config.

Remaining:

- Phase reports are read-only; generic safe execution remains limited to zero-write/no-paid-call next actions.

### Slice 0004-BE | 2026-06-13 | Run-Next Phase Snapshot Readback

Implemented:

- Added `phase_report_before` and `phase_report_after` to safe `run_next_actions` execution results when scoped to a run.
- CLI `bcw actions run-next`, API `POST /actions/run-next`, and MCP `business_card_watchdog_run_next_actions` now return the same before/after phase snapshots through the shared service method.
- Phase snapshots remain read-only and do not broaden the set of safe auto-executed actions.
- Added tests proving service, CLI, API, and MCP run-next surfaces expose the phase snapshots.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_run_next_actions_executes_safe_steps_until_manual_decision tests/test_cli_surfaces.py::test_cli_jobs_review_records_submission tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 4 tests.
- `.venv/bin/python -m pytest tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py -q` passed with 83 tests.
- `.venv/bin/python -m pytest -q` passed with 172 tests.
- `PYTHONPATH=src pytest -q` passed with 165 tests and 3 skipped optional-extra tests.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed with the index up to date.
- `.venv/bin/bcw mcp-call business_card_watchdog_status --arguments-json '{}'` passed against the user config.

Remaining:

- Run-next still executes only zero-write/no-paid-call safe actions and skips review, paid enrichment, write pilots, readback pilots, and live apply.

### Slice 0004-BF | 2026-06-13 | Phase Stop-Rule Policy Readback

Implemented:

- Added machine-readable `stop_rules` to phase reports.
- Stop rules list safe auto actions, explicit operator actions, and phase-specific action policy.
- Generic continue policy now explicitly reports that paid API enrichment, public-web enrichment, live sink writes, and live sink readbacks are not allowed from generic safe execution.
- Reused the explicit-operator-action set in sink pilot status summaries.
- Added focused tests for safe vs explicit write-pilot policy and no-paid/no-live generic continue rules.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_run_summary_and_review_queue tests/test_service.py::test_service_review_bundle_includes_sink_pilot_status tests/test_cli_surfaces.py::test_cli_runs_and_jobs_use_recorded_runtime_state tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 5 tests.
- `.venv/bin/python -m pytest tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py -q` passed with 83 tests.
- `.venv/bin/python -m pytest -q` passed with 172 tests.
- `PYTHONPATH=src pytest -q` passed with 165 tests and 3 skipped optional-extra tests.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed with the index up to date.
- `.venv/bin/bcw mcp-call business_card_watchdog_status --arguments-json '{}'` passed against the user config.

Remaining:

- Stop rules are readback policy only; explicit operator commands still perform the actual review/enrichment/pilot actions.

### Slice 0004-BG | 2026-06-13 | Review Queue Next-Action Filters

Implemented:

- Added review queue filters for `next_action` and `artifact_kind`.
- Review queue entries now include their deterministic `next_action` payload.
- Added CLI filters `bcw reviews list --next-action ... --artifact-kind ...`.
- Added API query parameters `next_action` and `artifact_kind` on `GET /reviews`.
- Added MCP `business_card_watchdog_reviews_list` input fields for `next_action` and `artifact_kind`.
- Covered service, CLI, API, and MCP filtering behavior with focused tests.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_run_summary_and_review_queue tests/test_cli_surfaces.py::test_cli_runs_and_jobs_use_recorded_runtime_state tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 4 tests.
- `.venv/bin/python -m pytest tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py -q` passed with 83 tests.
- `.venv/bin/python -m pytest -q` passed with 172 tests.
- `PYTHONPATH=src pytest -q` passed with 165 tests and 3 skipped optional-extra tests.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed with the index up to date.
- `.venv/bin/bcw mcp-call business_card_watchdog_status --arguments-json '{}'` passed against the user config.

Remaining:

- Review queue filters are read-only; reviewer decisions still flow through explicit review submission/import actions.

### Slice 0004-BH | 2026-06-13 | Review Bundle Agent Commands

Implemented:

- Added phase-report and safe run-next commands to `review_bundle.json`.
- Added MCP phase-report command text to the review bundle command set.
- Rendered review-bundle commands in the static offline review HTML.
- Kept command rendering read-only; actions still require the operator to run explicit CLI/MCP commands.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_run_summary_and_review_queue tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_cli_surfaces.py::test_cli_runs_and_jobs_use_recorded_runtime_state tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 4 tests.
- `.venv/bin/python -m pytest tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py -q` passed with 83 tests.
- `.venv/bin/python -m pytest -q` passed with 172 tests.
- `PYTHONPATH=src pytest -q` passed with 165 tests and 3 skipped optional-extra tests.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed with the index up to date.
- `.venv/bin/bcw mcp-call business_card_watchdog_status --arguments-json '{}'` passed against the user config.

Remaining:

- The HTML review surface displays commands and decision templates only; applying decisions remains an explicit import action.

### Slice 0004-BI | 2026-06-13 | MCP JSONL Phase Transport Coverage

Implemented:

- Hardened the MCP JSONL/stdio transport test for newer Plan 0004 surfaces.
- The transport test now lists tools, calls `business_card_watchdog_phase_report`, calls filtered `business_card_watchdog_reviews_list`, applies an explicit review decision, and calls `business_card_watchdog_run_next_actions`.
- The JSON-RPC path now proves phase reports and safe run-next before/after phase snapshots are returned as `structuredContent`.
- Kept the scenario zero-write/no-network; safe run-next executes only the first deterministic sink lookup planning step after review approval.

Validation:

- `.venv/bin/python -m pytest tests/test_mcp.py::test_mcp_jsonl_server_lists_and_calls_tools -q` passed with 1 test.

Remaining:

- MCP JSONL coverage now exercises the newer readback/control-plane tools, but live sink lookup/write/readback and paid enrichment remain explicit operator-approved actions outside safe generic execution.

### Slice 0004-BJ | 2026-06-13 | Full Pilot Route-Refresh Safety Coverage

Implemented:

- Added regression coverage for review updates after a full simulated pilot chain exists.
- The test proves `route_refresh.json` marks lookup plans, lookup adapter requests, lookup pilot evidence, lookup results, downstream duplicate assessment, sink plans, write adapter requests, apply preflight, apply decisions, pilot readiness, write pilot, apply result, readback adapter request, readback pilot, and pilot report as stale.
- The test proves safe `run_next_actions` refreshes only the zero-network safe prefix after the review update.
- The test proves safe execution stops before refreshing explicit lookup-pilot evidence, leaving later write/readback pilot artifacts pending for operator action.
- No runtime behavior changed; this locks in the existing full-chain route-refresh safety boundary.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_review_update_stales_full_pilot_chain_and_safe_refresh_stops_at_pilot -q` passed with 1 test.

Remaining:

- Explicit lookup/write/readback pilot evidence still requires operator-approved commands after route-refresh invalidation.

### Slice 0004-BK | 2026-06-13 | CSV Review Workbook Surface

Implemented:

- Added `review_workbook.csv` generation from the shared review bundle.
- The workbook contains one row per job with state, image path, next action, sink pilot state, core contact fields, duplicate state, enrichment proposal count, planned sinks, route-refresh state, artifact kinds, review command, and decision template JSON.
- Added service `review_workbook`, CLI `bcw reviews workbook`, API `POST /runs/{run_id}/review-workbook`, and MCP tool `business_card_watchdog_review_workbook`.
- CLI workbook output prints CSV by default and returns metadata plus CSV with `--json`.
- Added `contact_spec` to the review-bundle artifact registry so legacy extracted-spec evidence is visible in workbook exports.
- Kept the surface read-only and zero-network/zero-write.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_run_summary_and_review_queue tests/test_cli_surfaces.py::test_cli_runs_and_jobs_use_recorded_runtime_state tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 5 tests.

Remaining:

- Workbook import still flows through the existing JSON decision import path; a direct CSV decision importer remains follow-on work.

### Slice 0004-BL | 2026-06-13 | CSV Review Workbook Decision Import

Implemented:

- Added CSV workbook decision import through the shared review-decision submission path.
- Added service `apply_review_workbook_csv` that parses `decision_template_json` from workbook rows and calls the existing `apply_review_decisions` method.
- Added CSV import support to CLI `bcw reviews apply-decisions --decisions-csv-file <path>`.
- Added `decisions_csv` support to API `POST /runs/{run_id}/review-decisions`.
- Added `decisions_csv` support to MCP `business_card_watchdog_apply_review_decisions`.
- CSV imports record the same `review_decisions_import.json` artifact as JSON imports, with `source_format = csv` and `source_schema = business-card-watchdog.review-workbook.v1`.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_apply_review_workbook_csv_uses_decision_template_json tests/test_cli_surfaces.py::test_cli_runs_and_jobs_use_recorded_runtime_state tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 4 tests.

Remaining:

- CSV import intentionally reuses existing decision JSON in each row; richer spreadsheet editing helpers remain follow-on work.

### Slice 0004-BM | 2026-06-13 | Editable Workbook Decision Columns

Implemented:

- Added human-editable workbook columns for `review_action`, corrected contact fields, `review_notes`, and `skip_import`.
- CSV imports now translate edited contact columns into the existing `field_corrections` review decision object.
- `decision_template_json` remains supported as the fallback/advanced path, but routine approve-and-correct review can be done without editing JSON in a spreadsheet cell.
- Added service, CLI, API, and MCP tests that import decisions from editable workbook columns.
- Kept the import path on the shared `submit_review` behavior, preserving validation, artifacts, ledger events, route refresh, and zero-network/zero-write boundaries.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_run_summary_and_review_queue tests/test_service.py::test_service_apply_review_workbook_csv_uses_decision_template_json tests/test_cli_surfaces.py::test_cli_runs_and_jobs_use_recorded_runtime_state tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 5 tests.

Remaining:

- More specialized workbook helpers for duplicate resolution and enrichment approval can be added later without changing the shared review-decision importer.

### Slice 0004-BN | 2026-06-13 | Workbook Enrichment And Duplicate Decision Columns

Implemented:

- Added workbook columns for `approved_enrichment_fields`, `duplicate_decision`, `duplicate_target_identity`, and `duplicate_reason`.
- CSV workbook imports now translate those columns into the existing `approved_enrichment_fields` and `duplicate_resolution` review-decision fields.
- Added service regression coverage for approving enrichment merge proposals from workbook rows.
- Added service regression coverage for resolving duplicates from workbook rows.
- Kept the import path on shared review submission, preserving existing validation, artifacts, route refresh behavior, and zero-network/zero-write boundaries.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_run_summary_and_review_queue tests/test_service.py::test_service_apply_review_workbook_csv_uses_decision_template_json tests/test_service.py::test_service_apply_review_workbook_csv_supports_enrichment_columns tests/test_service.py::test_service_apply_review_workbook_csv_supports_duplicate_resolution_columns -q` passed with 4 tests.

Remaining:

- Workbook convenience columns now cover normal field correction, enrichment approval, and duplicate resolution; future work can add richer validation previews before import.

### Slice 0004-BO | 2026-06-13 | Review Workbook Import Preview

Implemented:

- Added a zero-write review workbook preview report before CSV import.
- Preview reuses the same workbook CSV parser as the apply path, so row interpretation stays aligned with actual import behavior.
- Preview reports ready, skipped, and error rows, including row numbers, job IDs, actions, artifact kinds, correction counts, approved enrichment fields, duplicate-resolution payloads, and warnings.
- Preview validates unsupported review actions, missing jobs, missing enrichment-result artifacts for enrichment merge approval, and missing duplicate-assessment artifacts or decisions for duplicate resolution.
- Added CLI `bcw reviews apply-decisions --decisions-csv-file <path> --preview`.
- Added API and MCP preview flags on the existing review-decision import surfaces.
- Kept preview at `writes_attempted = 0` and `network_calls_made = 0`; applying decisions remains a separate explicit action.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_preview_review_workbook_csv_validates_without_writes tests/test_service.py::test_service_apply_review_workbook_csv_uses_decision_template_json tests/test_cli_surfaces.py::test_cli_runs_and_jobs_use_recorded_runtime_state tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 5 tests.

Remaining:

- Future preview work can add richer sink-readiness warnings and spreadsheet-exported validation summaries, but the import boundary now has an operator-visible dry-run check.

### Slice 0004-BP | 2026-06-13 | Spreadsheet Preview Validation Report

Implemented:

- Added `validation_csv` to review workbook preview responses.
- Validation CSV rows summarize row number, status, run ID, job ID, action, errors, warnings, artifact kinds, field correction count, approved enrichment fields, duplicate decision, duplicate target identity, and duplicate reason.
- Parse-level errors still return a CSV with an error row, so preview callers always have a spreadsheet-readable report.
- Service, CLI, API, and MCP tests assert the CSV report is available on the preview surface.
- Kept the preview path at `writes_attempted = 0` and `network_calls_made = 0`; applying decisions remains a separate explicit action.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_preview_review_workbook_csv_validates_without_writes tests/test_cli_surfaces.py::test_cli_runs_and_jobs_use_recorded_runtime_state tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 4 tests.

Remaining:

- Future preview work can add sink-readiness warnings and optional persisted validation artifacts, but the default preview remains zero-write.

### Slice 0004-BQ | 2026-06-14 | Preview Sink Readiness Warnings

Implemented:

- Added sink-readiness warnings to review workbook preview rows for actions that can move a job toward routing.
- Blocked sink readiness now appears in row `warnings`, structured `sink_readiness_warnings`, and the spreadsheet `validation_csv`.
- Warnings reuse the existing user-config-aware sink readiness checks and remain zero-network/zero-write.
- Added regression coverage for a live Google Contacts target with apply disabled.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_preview_review_workbook_csv_validates_without_writes tests/test_service.py::test_service_preview_review_workbook_csv_warns_on_blocked_sink_readiness tests/test_cli_surfaces.py::test_cli_runs_and_jobs_use_recorded_runtime_state tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 5 tests.

Remaining:

- Future preview work can optionally persist validation artifacts, but default preview responses remain non-mutating.

### Slice 0004-BR | 2026-06-14 | Optional Preview Artifact Persistence

Implemented:

- Added optional persistence for review workbook preview results.
- `preview_review_workbook_csv(..., write=True)` now writes run-level `review_workbook_preview.json` and `review_workbook_preview_validation.csv` artifacts.
- CLI/API/MCP preview surfaces expose explicit preview persistence through `--preview-write` / `preview_write`.
- Persisted preview artifacts record ledger artifact entries and a `review_workbook_preview_created` event.
- Default preview remains non-mutating; applying review decisions remains a separate explicit action.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_preview_review_workbook_csv_validates_without_writes tests/test_service.py::test_service_preview_review_workbook_csv_can_persist_artifacts tests/test_cli_surfaces.py::test_cli_runs_and_jobs_use_recorded_runtime_state tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 5 tests.

Remaining:

- Future work can add a dedicated command for exporting only the validation CSV, but the preview artifact surface now has durable run-level evidence when explicitly requested.

### Slice 0004-BS | 2026-06-14 | Dedicated Validation CSV Export Command

Implemented:

- Added CLI `bcw reviews preview-validation`.
- The command reads an edited review workbook CSV and prints only the spreadsheet-friendly validation CSV by default.
- Added `--write-artifacts --json` support to persist and return the structured preview artifact paths when the operator wants durable run-level evidence.
- Reused the same preview parser and validation logic as `reviews apply-decisions --preview`; the command never applies review decisions.

Validation:

- `.venv/bin/python -m pytest tests/test_cli_surfaces.py::test_cli_runs_and_jobs_use_recorded_runtime_state tests/test_service.py::test_service_preview_review_workbook_csv_can_persist_artifacts tests/test_service.py::test_service_preview_review_workbook_csv_validates_without_writes -q` passed with 3 tests.

Remaining:

- Future work can add API/MCP aliases for validation-only export if needed, while the structured preview payload already carries `validation_csv` on those surfaces.

### Slice 0004-BT | 2026-06-14 | API And MCP Validation-Only Aliases

Implemented:

- Added API `POST /runs/{run_id}/review-workbook-validation`.
- Added MCP tool `business_card_watchdog_review_workbook_validation`.
- Both surfaces call the shared review workbook preview service and return `validation_csv` without applying decisions.
- Optional preview artifact persistence stays explicit via `preview_write`.

Validation:

- `.venv/bin/python -m pytest tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 3 tests.

Remaining:

- Workbook review now has validation-only exports across CLI, API, and MCP; future work can focus on routing/run-level summary integration rather than additional validation transport aliases.

### Slice 0004-BU | 2026-06-14 | Run Summary Preview Validation Readback

Implemented:

- Added `review_workbook_preview_summary` to run summaries.
- Summary readback includes preview/validation artifact counts, latest artifact paths, latest validity, row counts, error counts, skipped counts, ready counts, and warning counts.
- Missing or unreadable persisted preview artifacts are counted instead of failing run summary generation.
- Added service regression coverage for empty preview state and persisted preview readback.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_run_summary_and_review_queue tests/test_service.py::test_service_preview_review_workbook_csv_can_persist_artifacts -q` passed with 2 tests.

Remaining:

- Future work can add phase-report grouping for preview validation status if operators need dashboard-level phase counts.

### Slice 0004-BV | 2026-06-14 | Phase Report Preview Validation Readback

Implemented:

- Added run-level `review_workbook_preview` readback to phase reports.
- The readback groups persisted review workbook preview validation into `not_started`, `valid`, `invalid`, or `unreadable` states without changing per-job phase rows.
- Reused persisted preview artifacts and the run-summary preview summarizer for row counts, ready/error/skipped counts, warning counts, validity, and latest artifact paths.
- Added regression coverage for both empty preview state and persisted valid preview state.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_run_summary_and_review_queue tests/test_service.py::test_service_preview_review_workbook_csv_can_persist_artifacts -q` passed with 2 tests.
- `python -m py_compile src/business_card_watchdog/service.py` passed.

Remaining:

- Future work can surface this run-level preview phase in CLI/API/MCP dashboards if operators want it outside the existing phase-report payload.

### Slice 0004-BW | 2026-06-14 | Phase Report Preview Surface Coverage

Implemented:

- Added explicit CLI phase-report regression coverage for `review_workbook_preview`.
- Added explicit API phase-report regression coverage for `review_workbook_preview`.
- Added explicit MCP tool and JSON-RPC stdio regression coverage for `review_workbook_preview`.
- Confirmed the run-level preview validation phase is visible through existing phase-report dashboard surfaces without changing the transport contracts.

Validation:

- `.venv/bin/python -m pytest tests/test_cli_surfaces.py::test_cli_runs_and_jobs_use_recorded_runtime_state tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service tests/test_mcp.py::test_mcp_jsonl_server_lists_and_calls_tools -q` passed with 4 tests.
- `python -m py_compile tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py` passed.

Remaining:

- Future work can add formatted dashboard summaries if operators need a condensed view beyond the raw phase-report JSON payload.

### Slice 0004-BX | 2026-06-14 | Phase Report Dashboard Summary

Implemented:

- Added additive `dashboard_summary` readback to phase reports.
- Summary includes a compact status line, review workbook preview state, blocked phase count, explicit-required phase count, pending phase count, complete phase count, and grouped phase lists.
- CLI/API/MCP phase-report payloads now carry a dashboard-ready summary without changing existing phase rows or transport contracts.
- Added service, CLI, API, MCP direct-tool, and MCP JSON-RPC regression coverage.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_run_summary_and_review_queue tests/test_service.py::test_service_review_bundle_includes_sink_pilot_status tests/test_cli_surfaces.py::test_cli_runs_and_jobs_use_recorded_runtime_state tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service tests/test_mcp.py::test_mcp_jsonl_server_lists_and_calls_tools -q` passed with 6 tests.
- `python -m py_compile src/business_card_watchdog/service.py tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py` passed.

Remaining:

- Future work can decide whether the CLI non-JSON output should render this summary as text instead of printing the raw Python object.

### Slice 0004-BY | 2026-06-14 | CLI Phase Report Text Summary

Implemented:

- Added human-readable text rendering for non-JSON `bcw runs phase-report`.
- The text output includes run id, run state, job count, dashboard status line, review workbook preview state, and blocked/explicit/pending/complete phase groups.
- `--json` phase-report output remains unchanged for API-style consumers.
- Added CLI regression coverage to prevent raw Python dict output from returning for phase reports.

Validation:

- `.venv/bin/python -m pytest tests/test_cli_surfaces.py::test_cli_runs_and_jobs_use_recorded_runtime_state -q` passed with 1 test.
- `python -m py_compile src/business_card_watchdog/cli.py tests/test_cli_surfaces.py` passed.

Remaining:

- Future work can consider similar text renderers for other raw-object CLI paths if operators prefer command-line summaries over JSON.

### Slice 0004-BZ | 2026-06-14 | CLI Run Summary Text Summary

Implemented:

- Added human-readable text rendering for non-JSON `bcw runs summary`.
- The text output includes run id, state, job count, review/routing/failure counts, enrichment budget counters, sink pilot counters, and review workbook preview validation state.
- `--json` run summary output remains unchanged for automation.
- Added CLI regression coverage to prevent raw Python dict output from returning for run summaries.

Validation:

- `.venv/bin/python -m pytest tests/test_cli_surfaces.py::test_cli_runs_and_jobs_use_recorded_runtime_state -q` passed with 1 test.
- `python -m py_compile src/business_card_watchdog/cli.py tests/test_cli_surfaces.py` passed.

Remaining:

- Future work can decide whether list/show/review queue CLI paths also need custom text renderers or should remain JSON-first for operator use.

### Slice 0004-CA | 2026-06-14 | CLI Review Queue Text Summary

Implemented:

- Added human-readable text rendering for non-JSON `bcw reviews list`.
- The text output includes queue count plus one compact row per job with job id, state, next action, and artifact kinds.
- Empty review queues render as an explicit zero-job summary.
- `--json` review-list output remains unchanged for automation.
- Added CLI regression coverage to prevent raw Python list/dict output from returning for review queues.

Validation:

- `.venv/bin/python -m pytest tests/test_cli_surfaces.py::test_cli_runs_and_jobs_use_recorded_runtime_state -q` passed with 1 test.
- `python -m py_compile src/business_card_watchdog/cli.py tests/test_cli_surfaces.py` passed.

Remaining:

- Future work can decide whether `runs list`, `runs show`, `jobs list`, and `jobs show` need similar text renderers, or whether those should stay JSON-first.

### Slice 0004-CB | 2026-06-14 | CLI Job Text Summaries

Implemented:

- Added human-readable text rendering for non-JSON `bcw jobs list`.
- Added human-readable text rendering for non-JSON `bcw jobs show`.
- Job list output includes job count plus compact rows with job id, run id, state, and image path.
- Job show output includes job id, run id, state, image path, artifact kinds, and any error.
- `--json` job list/show output remains unchanged for automation.
- Added CLI regression coverage to prevent raw Python list/dict output from returning for job list/show surfaces.

Validation:

- `.venv/bin/python -m pytest tests/test_cli_surfaces.py::test_cli_runs_and_jobs_use_recorded_runtime_state -q` passed with 1 test.
- `python -m py_compile src/business_card_watchdog/cli.py tests/test_cli_surfaces.py` passed.

Remaining:

- Future work can decide whether `runs list` and `runs show` need similar text renderers, or whether run discovery should stay JSON-first.

### Slice 0004-CC | 2026-06-14 | CLI Run List And Show Text Summaries

Implemented:

- Added human-readable text rendering for non-JSON `bcw runs list`.
- Added human-readable text rendering for non-JSON `bcw runs show`.
- Run list output includes run count plus compact rows with run id, state, job count, and updated timestamp.
- Run show output includes run id, state, job count, loaded job count, artifact count, and run directory.
- `--json` run list/show output remains unchanged for automation.
- Added CLI regression coverage to prevent raw Python list/dict output from returning for run list/show surfaces.

Validation:

- `.venv/bin/python -m pytest tests/test_cli_surfaces.py::test_cli_runs_and_jobs_use_recorded_runtime_state -q` passed with 1 test.
- `python -m py_compile src/business_card_watchdog/cli.py tests/test_cli_surfaces.py` passed.

Remaining:

- Core run/review/job CLI discovery and dashboard paths now have human-readable non-JSON output while retaining JSON automation surfaces.

### Slice 0004-CD | 2026-06-14 | README CLI Review Surface Readback

Implemented:

- Updated README operator commands to show human-readable run, phase-report, job, and review queue surfaces.
- Kept JSON guidance explicit for automation consumers.
- Documented the review queue and job show commands alongside run discovery so operators can inspect imported cards without reading raw JSON by default.

Validation:

- `git diff --check` passed.
- `.venv/bin/python -m pytest tests/test_cli_surfaces.py::test_cli_runs_and_jobs_use_recorded_runtime_state -q` passed with 1 test.
- `rg -n 'bcw runs list|bcw runs summary|bcw runs phase-report|bcw jobs show|bcw reviews list|--json' README.md` passed.
- `python -m py_compile src/business_card_watchdog/cli.py tests/test_cli_surfaces.py` passed.

Remaining:

- Future documentation work can add a longer operator walkthrough once Plan 0004 reaches a stable end-to-end review workflow.

### Slice 0004-CE | 2026-06-14 | Review Workflow Operations Walkthrough

Implemented:

- Added `docs/operations/review-workflow.md`.
- Documented the operator path from intake through run/job inspection, review queue inspection, workbook preview/import, enrichment guardrails, duplicate/routing checks, explicit sink-pilot gates, and safe deterministic continuation.
- Linked the workflow from README operational details.
- Kept automation guidance aligned with existing `--json` surfaces.

Validation:

- `git diff --check` passed.
- `.venv/bin/python -m pytest tests/test_cli_surfaces.py::test_cli_runs_and_jobs_use_recorded_runtime_state -q` passed with 1 test.
- `rg -n 'review-workflow|reviews preview-validation|reviews apply-decisions|sinks write-pilot|actions run-next|--allow-paid-enrichment' README.md docs/operations/review-workflow.md` passed.

Remaining:

- Future docs can add screenshots or sample fixture output if the review workflow needs training material.

### Slice 0004-CF | 2026-06-14 | Review Workflow Sample Output

Implemented:

- Added `docs/operations/review-workflow-sample-output.md`.
- Documented representative text output for run discovery, run show, run summary, phase report, job list/show, review queue, empty filtered review queue, workbook preview validation CSV, persisted preview JSON, and safe continuation stops.
- Linked the sample output from the review workflow and README.

Validation:

- `git diff --check` passed.
- `.venv/bin/python -m pytest tests/test_cli_surfaces.py::test_cli_runs_and_jobs_use_recorded_runtime_state -q` passed with 1 test.
- `rg -n 'review-workflow-sample-output|Run: run-001|Review queue: 1 jobs|row_number,status|actions run-next' README.md docs/operations/review-workflow.md docs/operations/review-workflow-sample-output.md` passed.

Remaining:

- Future training docs can add screenshots if a richer visual guide is needed.

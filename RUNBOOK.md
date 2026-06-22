# Runbook

## Turn 1 | 2026-06-10

Bootstrapped the repo as a product/runtime platform rather than a simple library. Installed local policy docs, package skeleton, deterministic batch ledger, config paths, business-card skill adapter, routing stubs, CLI/API/MCP surfaces, and initial tests.

Validation:

- `PYTHONPATH=src pytest -q` passed with 5 tests.
- `PYTHONPATH=src python -m business_card_watchdog.cli status --json` confirmed the business-card skill adapter is ready.
- `PYTHONPATH=src python -m business_card_watchdog.cli mcp-manifest` rendered a 914-byte MCP manifest.

Remaining:

- Implement durable watcher state across restarts.
- Add live Google/Odoo sink readiness and write/readback checks before enabling non-dry-run routing.
- Initialize CodeGraph if desired for structural navigation after the first code scaffold.

## Turn 2 | 2026-06-11

Added `PRODUCT_SPEC.md` as the draft product authority before continuing implementation. The spec defines the problem, target users, goals/non-goals, core workflows, functional requirements, App Intelligence control rules, user-scoped config/runtime requirements, sink routing/idempotency requirements, security boundaries, and milestone acceptance criteria.

Validation:

- Documentation-only change; no code tests required.

## Turn 3 | 2026-06-11

Added `docs/dev/plans/0002-2026-06-11-high-level-implementation-goal-plan.md` as the high-level implementation plan adapted for `/goal` and subagent execution. The plan defines the `/goal` objective, operating contract, workstream/subagent briefs, critical path, parallel launch set, integration gates, reconciliation checklist, suggested turn sequence, and validation matrix.

Validation:

- Documentation-only change; no code tests required.

## Turn 4 | 2026-06-11

Started executing Plan 0002 under the active `/goal`. Kept WS1 local because core state is the critical-path contract, and delegated WS7 as a tests-only subagent sidecar.

Implemented:

- WS1: typed run/job/sink states, explicit invalid-transition rejection, run index writes, artifact registry JSONL, and orchestrator state transitions.
- WS7: privacy-safe synthetic fixtures, fake skill adapter, and dry-run end-to-end batch validation without real card data or external credentials.

Validation:

- `PYTHONPATH=src pytest -q` passed with 10 tests.
- CodeGraph was not initialized (`.codegraph/` missing), so this slice used direct source reads and targeted tests.

Remaining:

- WS2 watched-folder durable state and file-settle behavior.
- WS3 review/classification hardening.
- WS4 routing fingerprint/readiness/sink adapter work.
- WS5 expanded CLI/API/MCP service surfaces.
- WS6 user-scope service/install operations.

## Turn 5 | 2026-06-11

Continued Plan 0002 execution with the next critical integration slice: WS3 review classification and WS4 dry-run routing/sink primitives.

Implemented:

- WS3: deterministic contact-spec assessment, structured `review_packet.json` generation for incomplete specs, optional OCR/crop/contact-sheet artifact registration, and review-state tests.
- WS4: canonical contact fingerprinting, dry-run sink payload generation, readiness primitives that keep live Google/Odoo writes blocked until implemented, route decision fingerprints/matched-rule metadata, and sink tests.

Validation:

- `PYTHONPATH=src pytest -q` passed with 18 tests.
- `PYTHONPATH=src python -m business_card_watchdog.cli status --json` confirmed the business-card skill adapter is still ready.
- `PYTHONPATH=src python -m business_card_watchdog.cli mcp-manifest` rendered a 914-byte MCP manifest.

Remaining:

- WS2 watched-folder durable seen-file state and SyncThing file-settle behavior.
- WS3 richer field/crop correction schemas and review submission flow.
- WS4 live sink readiness/write/readback and same-contact write serialization.
- WS5 expanded CLI/API/MCP service surfaces.
- WS6 user-scope service/install operations.

## Turn 6 | 2026-06-11

Continued Plan 0002 execution with WS2 watcher hardening.

Implemented:

- Durable watcher state under `~/.local/share/business-card-watchdog/watch/`, including `seen-files.jsonl`, `pending-files.json`, and `status.json`.
- SyncThing-style file-settle behavior using size/mtime snapshots and configurable `watch.settle_seconds`.
- Restart-safe seen-file behavior so already processed files are not reprocessed unless watcher state is explicitly reset.
- `bcw watch-status` and guarded `bcw watch-reset --yes` commands.
- Main `bcw status --json` now includes watcher status readback.

Validation:

- `PYTHONPATH=src pytest -q` passed with 26 tests.
- `PYTHONPATH=src python -m business_card_watchdog.cli status --json` confirmed skill readiness and watcher status payload. The current user config still points at `$fsr:sync_phone` -> `E:\SyncThing\S22 Camera Phone Storage`, which is not present in this Linux path namespace, so watcher status reports that input as missing.

Remaining:

- WS2 service install/uninstall helpers.
- WS5 expanded CLI/API/MCP service surfaces.
- WS6 packaging and user-scope operations.
- Live sink gates remain intentionally blocked pending explicit readiness/write/readback implementations.

## Turn 7 | 2026-06-11

Completed Plan 0002 execution.

Implemented:

- WS5: shared `BusinessCardService`, expanded CLI run/job/review/sink/watch/service/doctor commands, expanded FastAPI endpoints, expanded MCP schemas, and `docs/dev/architecture/0002-mcp-server-plan.md`.
- WS6: API/dev dependency extras, user-scope systemd unit install/status/uninstall helpers, runtime doctor, config migration/versioning guidance, and release checklist documentation.
- Remaining review submission and same-contact serialization policy gaps from the Plan 0002 audit.

Validation:

- `PYTHONPATH=src pytest -q` passed with 39 tests and 1 skipped API-extra test.
- `.venv/bin/python -m pytest -q` passed with 40 tests after installing `.[api,dev]`.
- `.venv/bin/bcw doctor --json` passed with a temp config and writable temp runtime paths.
- `.venv/bin/bcw status --json` passed with the real user config and reported the expected missing Windows SyncThing path caveat.
- `.venv/bin/bcw service status --json` passed and showed the user-scope unit path.
- `.venv/bin/bcw mcp-manifest | python -m json.tool` passed and rendered a 5129-byte manifest.
- `.venv/bin/bcw --config <temp-config> process <empty-temp-source> --dry-run --workers 1` passed and created a completed dry-run run.

Follow-on:

- Opened `docs/dev/plans/0003-2026-06-11-follow-on-live-sinks-and-mcp-server.md` for live sink write/readback and MCP server transport work.

## Turn 8 | 2026-06-12

Added deterministic image preclassification before the business-card pipeline.

Implemented:

- `src/business_card_watchdog/preclassifier.py` with header-based image dimension reading, aspect-ratio scoring, and optional OpenCV rectangular contour hints when `cv2` is installed.
- `[prefilter]` config with `enabled`, `min_score`, and `process_uncertain`.
- Orchestrator wiring that records `preclassification.json` and `image_preclassified` events before adapter execution.
- Rejection path for `not_business_card` and, by default, `uncertain`, so those images do not hit the business-card/App Intelligence pipeline.
- Architecture note `docs/dev/architecture/0003-deterministic-image-prefilter.md`.

Validation:

- `PYTHONPATH=src pytest -q` passed with 43 tests and 1 skipped API-extra test.
- `.venv/bin/python -m pytest -q` passed with 44 tests.

## Turn 9 | 2026-06-13

Standardized local install/dependency workflow on `uv`.

Updated:

- README install commands now use `uv venv .venv` and `uv pip install --python .venv/bin/python -e ".[api,watch,vision,dev]"`.
- Operations docs now use uv for dependency management and installed-entrypoint validation.
- Prefilter architecture note now documents the uv command for the `vision` extra.

Validation:

- `uv pip install --python .venv/bin/python -e ".[api,watch,vision,dev]"` succeeded.
- `.venv/bin/python -m pytest -q` passed with 45 tests.
- `.venv/bin/bcw status --json` passed and still reports the expected missing Windows SyncThing path caveat in this Linux namespace.
- `.venv/bin/python` imported `cv2` 4.13.0 and `watchfiles` 1.2.0.

## Turn 10 | 2026-06-13

Implemented the SyncThing/OpenCV prefilter hardening slice.

Updated:

- Default config and real user config now point `$fsr:sync_phone` at `/mnt/e/SyncThing/S22 Camera Phone Storage`.
- Watcher status scans are bounded and non-recursive by default so `bcw status --json` does not walk an entire phone-camera tree.
- OpenCV rectangle analysis now records multiple card-like boxes and raises confidence for multi-card phone photos.
- Aspect ratio is weak evidence only; without rectangle evidence, 16:9 phone images are `uncertain`, not `likely_business_card`.
- CodeGraph was initialized for the repo; its local database remains ignored under `.codegraph/`.

Validation:

- `.venv/bin/python -m pytest tests/test_preclassifier.py tests/test_watcher.py -q` passed with 15 tests.
- `PYTHONPATH=src pytest tests/test_preclassifier.py tests/test_watcher.py -q` passed with 13 tests and 2 skipped OpenCV tests.
- `.venv/bin/bcw status --json` passed against the real user config and reported 5 top-level backlog images, no unsettled files, no truncation, and no last error.
- Real top-level SyncThing JPGs classified as `uncertain` with zero card-like contours instead of `likely_business_card`.

## Turn 11 | 2026-06-13

Opened the next high-level plan for review, normalization, enrichment, dedupe, and live sink routing.

Updated:

- Added `docs/dev/plans/0004-2026-06-13-review-normalization-enrichment-dedupe-sinks.md`.
- Updated `ROADMAP.md` to point at Plan 0004 as the current high-level implementation plan.
- Captured the policy that API-based enrichment has cost and must be explicitly requested.
- Captured Odollo-derived implementation sources for Apollo enrichment, public-web enrichment, Odoo readiness/lookup, contact points, and review action semantics.

Validation:

- Planning-only change; run `git diff --check` before commit.

## Turn 12 | 2026-06-13

Started executing Plan 0004.

Implemented:

- Contact candidate normalization contract and `contact_candidate.json` artifacts.
- Review approval now writes `reviewed_contact.json` with normalized operator corrections.
- Review packets include the contact candidate.
- Enrichment config/readiness with default-off behavior, public-web readiness, and paid API gating for Apollo-style providers using key names from `~/credentials/API-keys.env` without exposing values.
- CLI/MCP enrichment readiness surface.
- Local identity index and `duplicate_assessment.json` artifacts.
- Strong duplicate jobs move to `needs_review` before sink routing.

Validation:

- `.venv/bin/python -m pytest -q` passed with 57 tests.
- `PYTHONPATH=src pytest -q` passed with 54 tests and 3 skipped optional-extra tests.
- `.venv/bin/bcw enrichment check --json` passed and reported default no-op readiness.
- `.venv/bin/bcw enrichment check --mode api --json` reported blocked readiness because enrichment is disabled in the current user config.

Operational note:

- `git remote -v` returned no configured remotes, so the requested push cannot be completed until a remote is added.

## Turn 13 | 2026-06-13

Continued Plan 0004 execution with review queue and batch summary surfaces.

Implemented:

- `BusinessCardService.review_queue` derived from run/job ledgers and artifact records.
- `BusinessCardService.run_summary` with state and artifact counts.
- CLI `bcw reviews list` and `bcw runs summary`.
- API `GET /reviews` and `GET /runs/{run_id}/summary`.
- MCP manifest entries for review queue and run summary tools.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py -q` passed with 16 tests.
- `PYTHONPATH=src pytest tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py -q` passed with 15 tests and 1 skipped optional API-extra test.

## Turn 14 | 2026-06-13

Continued Plan 0004 execution with enrichment request/result artifacts.

Implemented:

- `enrichment_request.json` artifacts for selected jobs.
- Fixture-backed `enrichment_result.json` artifacts for public-web results supplied by the caller.
- Deterministic public-web query generation and result scoring.
- Review-required merge proposals that do not overwrite observed card fields.
- Service, CLI, API, and MCP-manifest surfaces for enrichment requests.

Validation:

- `.venv/bin/python -m pytest tests/test_enrichment.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py -q` passed with 14 tests.
- `PYTHONPATH=src pytest tests/test_enrichment.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py -q` passed with 13 tests and 1 skipped optional API-extra test.

## Turn 15 | 2026-06-13

Continued Plan 0004 execution with dry-run sink plan artifacts.

Implemented:

- `sink_plan.json` artifacts for selected jobs.
- Sink plans prefer reviewed contact artifacts, then normalized contact candidates, then legacy specs.
- Sink plans record routing decision, dry-run payloads, readiness, match keys, serialization keys, and planned upsert actions.
- Service, CLI, API, and MCP-manifest surfaces for sink planning.

Validation:

- `.venv/bin/python -m pytest tests/test_sinks.py tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py -q` passed with 25 tests.
- `PYTHONPATH=src pytest tests/test_sinks.py tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py -q` passed with 24 tests and 1 skipped optional API-extra test.

## Turn 16 | 2026-06-13

Continued Plan 0004 execution with agent next-action readback and MCP dispatcher.

Implemented:

- `BusinessCardService.next_actions` for deterministic agent-loop orchestration.
- Next-action recommendations for review, duplicate resolution, enrichment review, sink planning, apply approval, and failure inspection.
- MCP manifest entry for next actions.
- Local executable MCP dispatcher `call_tool`.
- CLI `bcw mcp-call` for JSON-argument tool execution.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py tests/test_mcp.py tests/test_cli_surfaces.py -q` passed with 22 tests.
- `PYTHONPATH=src pytest tests/test_service.py tests/test_mcp.py tests/test_cli_surfaces.py -q` passed with 22 tests.

## Turn 17 | 2026-06-13

Continued Plan 0004 execution with expanded review action semantics.

Implemented:

- Added review actions `request_enrichment`, `reject_not_card`, and `skip`.
- `request_enrichment` keeps/returns the job to `needs_review`.
- `reject_not_card` transitions the job to `failed` with explicit review error.
- `skip` transitions the job to `cancelled`.
- CLI and MCP schema exposure for expanded review actions.

Validation:

- `.venv/bin/python -m pytest tests/test_review.py tests/test_service.py tests/test_cli_surfaces.py tests/test_mcp.py -q` passed with 27 tests.
- `PYTHONPATH=src pytest tests/test_review.py tests/test_service.py tests/test_cli_surfaces.py tests/test_mcp.py -q` passed with 27 tests.

## Turn 18 | 2026-06-13

Continued Plan 0004 execution with a zero-write sink apply preflight gate.

Implemented:

- `sink_apply_preflight.json` artifacts for planned jobs.
- Default preview mode that records no live write was attempted.
- Explicit `apply = true` handling that remains blocked until live sink write/readback adapters exist.
- Service, CLI, API, and MCP dispatcher surfaces for apply preflight.
- Agent next-action command updated to `sinks apply-preflight`.

Validation:

- `.venv/bin/python -m pytest tests/test_sinks.py tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py -q` passed with 35 tests.

## Turn 19 | 2026-06-13

Continued Plan 0004 execution with explicit enrichment merge approval.

Implemented:

- Added review action `approve_enrichment_merge`.
- Added `approved_enrichment_fields` to review submissions.
- Approved enrichment proposals now write `reviewed_contact.json` and `enrichment_merge_review.json`.
- Existing card notes are preserved when approved enrichment notes are merged.
- Service, CLI, API, and MCP dispatcher surfaces support enrichment merge approval.
- Added `enrichment_merge_reviewed` events for agent-loop readback.

Validation:

- `.venv/bin/python -m pytest tests/test_contact.py tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py -q` passed with 33 tests.

## Turn 20 | 2026-06-13

Continued Plan 0004 execution with duplicate resolution review actions.

Implemented:

- Added review action `resolve_duplicate`.
- Added duplicate decisions `create_new`, `merge_existing`, and `noop`.
- Duplicate resolution writes `duplicate_resolution.json` and `duplicate_resolved` events.
- `create_new` and `merge_existing` move jobs to `ready_to_route`; `noop` cancels the job.
- Sink plans include the duplicate resolution artifact when present.
- Service, CLI, API, and MCP dispatcher surfaces support duplicate resolution.

Validation:

- `.venv/bin/python -m pytest tests/test_review.py tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py -q` passed with 38 tests.

## Turn 21 | 2026-06-13

Continued Plan 0004 execution with zero-network sink lookup planning.

Implemented:

- Added `sink_lookup_plan.json` artifacts for selected jobs.
- Added dry-run Google Contacts and Odoo lookup query descriptors from fingerprint, email, phone, and name keys.
- Added lookup readiness that remains zero-network and blocks live lookup execution until adapters exist.
- Added service, CLI, API, and MCP dispatcher surfaces for sink lookup planning.
- Agent next-action ordering now recommends `sinks lookup-plan` before `sinks plan`.

Validation:

- `.venv/bin/python -m pytest tests/test_sinks.py tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py -q` passed with 44 tests.

## Turn 22 | 2026-06-13

Continued Plan 0004 execution with zero-write sink apply decisions.

Implemented:

- Added `sink_apply_decision.json` artifacts for apply approval, rejection, and no-op decisions.
- Added decisions `approve`, `reject`, and `noop`.
- Decision artifacts record `writes_attempted = 0` and `network_calls_made = 0`.
- `noop` decisions transition jobs to `cancelled`.
- Added `sink_apply_decided` events for agent-loop readback.
- Added service, CLI, API, and MCP dispatcher surfaces for sink apply decisions.
- Agent next-action ordering now recommends apply preflight before apply decision.

Validation:

- `.venv/bin/python -m pytest tests/test_sinks.py tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py -q` passed with 49 tests.

## Turn 23 | 2026-06-13

Continued Plan 0004 execution with gated zero-write sink apply results.

Implemented:

- Added `sink_apply_result.json` artifacts for gated apply attempts.
- Added CLI `bcw sinks apply --apply`.
- Added API and MCP dispatcher surfaces for sink apply attempts.
- Apply requires the existing preflight/decision artifacts and remains blocked until live adapters exist.
- Apply result artifacts record `writes_attempted = 0`, `network_calls_made = 0`, and empty readback evidence.
- Added `sink_apply_attempted` events for agent-loop readback.
- Agent next-action command now points to `sinks apply --apply` after an apply decision exists.

Validation:

- `.venv/bin/python -m pytest tests/test_sinks.py tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py -q` passed with 52 tests.

## Turn 24 | 2026-06-13

Continued Plan 0004 execution with per-sink live apply policy readiness gates.

Implemented:

- Added user config flags `google_contacts_apply_enabled` and `odoo_apply_enabled`, both defaulting to `false`.
- Updated default config template with the live apply policy flags.
- Live sink readiness now blocks on disabled apply policy before checking tools or adapters.
- Service readiness passes per-sink apply policy into sink readiness checks.
- Live plan readiness can distinguish dry-run readiness, disabled live apply policy, and adapter-not-implemented state.

Validation:

- `.venv/bin/python -m pytest tests/test_config.py tests/test_sinks.py tests/test_service.py -q` passed with 40 tests.

## Turn 25 | 2026-06-13

Continued Plan 0004 execution with simulated sink apply/readback.

Implemented:

- Added explicit `simulate` flag for gated sink apply attempts.
- Added mock sink apply/readback result state `mock_applied`.
- Simulated readback entries use stable mock resource IDs derived from sink and serialization key.
- CLI `bcw sinks apply --apply --simulate`.
- API and MCP apply surfaces accept `simulate`.
- Simulated apply keeps `writes_attempted = 0` and `network_calls_made = 0`.
- `sink_apply_attempted` events record whether the attempt was simulated.

Validation:

- `.venv/bin/python -m pytest tests/test_sinks.py tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py -q` passed with 56 tests.

## Turn 26 | 2026-06-13

Continued Plan 0004 execution with blocked live adapter request artifacts.

Implemented:

- Added `sink_adapter_request_{phase}.json` artifacts for `lookup`, `write`, and `readback`.
- Added Google Contacts and Odoo/Odollo adapter request descriptors for lookup/write/readback phases.
- Adapter request artifacts document intended live methods, payloads, match keys, serialization keys, and readback IDs without invoking adapters.
- Service, CLI, API, and MCP surfaces can create adapter request artifacts.
- Adapter request creation auto-creates prerequisite dry-run artifacts when needed.
- Adapter requests remain blocked and record `writes_attempted = 0` and `network_calls_made = 0`.

Validation:

- `.venv/bin/python -m pytest tests/test_sinks.py tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py -q` passed with 59 tests.

## Turn 27 | 2026-06-13

Continued Plan 0004 execution with adapter-request next-action sequencing.

Implemented:

- `BusinessCardService.next_actions` now recommends lookup adapter requests after sink lookup planning.
- Next actions now recommend write adapter requests after sink planning and before apply preflight.
- Next actions now recommend readback adapter requests after sink apply result artifacts exist.
- Jobs with readback adapter requests do not continue repeating the apply approval action.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py tests/test_cli_surfaces.py tests/test_mcp.py -q` passed with 48 tests.

## Turn 28 | 2026-06-13

Continued Plan 0004 execution with downstream sink lookup result artifacts.

Implemented:

- Added `sink_lookup_result.json` artifacts for downstream lookup results.
- Lookup result artifacts default to zero-network `not_executed` results and can hold fixture-provided downstream matches.
- Fixture matches set `state = possible_duplicate`, `duplicate_review_required = true`, and preserve sink resource IDs, basis, confidence, and display labels.
- Service, CLI, API, and MCP surfaces can record lookup result artifacts.
- `BusinessCardService.next_actions` now recommends `sinks lookup-result` after lookup adapter requests and before sink planning.
- Lookup result artifacts record `writes_attempted = 0` and `network_calls_made = 0`.

Validation:

- `.venv/bin/python -m pytest tests/test_sinks.py tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py -q` passed with 66 tests.

## Turn 29 | 2026-06-13

Continued Plan 0004 execution with downstream duplicate assessment gating.

Implemented:

- Added downstream sink lookup result assessment into the existing duplicate assessment schema.
- Sink lookup matches can now produce `strong_duplicate` or `possible_duplicate` assessments.
- Added `downstream_duplicate_assessment.json` artifacts.
- Jobs with downstream duplicate matches transition back to `needs_review`.
- Duplicate resolution review can resolve downstream duplicate assessments when no local duplicate assessment exists.
- Service, CLI, API, and MCP surfaces can run downstream duplicate assessment.
- `BusinessCardService.next_actions` now recommends `sinks assess-duplicates` after sink lookup results and before sink planning.

Validation:

- `.venv/bin/python -m pytest tests/test_dedupe.py tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py -q` passed with 57 tests.

## Turn 30 | 2026-06-13

Continued Plan 0004 execution with a safe next-action executor for agent loops.

Implemented:

- Added `BusinessCardService.run_next_actions`.
- Executor runs only allowlisted zero-network/zero-write safe actions.
- Executor skips review, duplicate resolution, enrichment review, apply decisions, live apply approval, and failure inspection.
- Added CLI `bcw actions run-next`.
- Added API `POST /actions/run-next`.
- Added MCP tool `business_card_watchdog_run_next_actions`.
- Executor returns executed and skipped action records for deterministic agent-loop readback.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py -q` passed with 55 tests.

## Turn 31 | 2026-06-13

Continued Plan 0004 execution with MCP stdio transport.

Implemented:

- Added `business_card_watchdog.mcp_server` JSONL stdio transport.
- Transport handles `initialize`, `tools/list`, `tools/call`, `ping`, and `shutdown` JSON-RPC requests.
- `tools/list` maps the repo manifest to MCP-style `inputSchema` records.
- `tools/call` delegates to the shared MCP dispatcher and service-layer methods.
- Added CLI `bcw mcp-stdio`.
- Added transport and CLI parser tests.

Validation:

- `.venv/bin/python -m pytest tests/test_mcp.py tests/test_cli_surfaces.py -q` passed with 21 tests.

## Turn 32 | 2026-06-13

Continued Plan 0004 execution with paid enrichment provider request artifacts.

Implemented:

- Added `enrichment_provider_request.json` artifacts for explicitly requested paid API enrichment.
- Added Apollo-shaped provider request builder with observed contact fields, request fields, configured base URL, and API key env name.
- Provider request artifacts record `network_calls_made = 0` and `paid_api_calls_attempted = 0`.
- Provider request artifacts do not include API key values.
- Service `request_enrichment` writes provider request artifacts for `api` and `all` modes after readiness passes.
- CLI and MCP enrichment request surfaces can produce the provider request artifact with explicit paid-enrichment approval.

Validation:

- `.venv/bin/python -m pytest tests/test_enrichment.py tests/test_cli_surfaces.py tests/test_mcp.py -q` passed with 30 tests.

## Turn 33 | 2026-06-13

Continued Plan 0004 execution with provider-specific sink adapter request contracts.

Implemented:

- Expanded blocked sink adapter request artifacts with concrete Google People API lookup/write/readback contracts.
- Google Contacts requests now include profile placeholders, query/request bodies, read masks, match strategy, idempotency policy, and expected response keys.
- Expanded Odollo/Odoo requests with tenant placeholders, `res.partner` lookup/write/readback contracts, Odoo lookup domains, additive contact-point plans, and expected response keys.
- Odollo contact-point plans explicitly preserve canonical slots by default.
- Adapter requests remain blocked and record `writes_attempted = 0`, `network_calls_made = 0`, and `requires_live_adapter = true`.

Validation:

- `.venv/bin/python -m pytest tests/test_sinks.py -q` passed with 14 tests.

## Turn 34 | 2026-06-13

Continued Plan 0004 execution with sink tenant/profile config metadata.

Implemented:

- Added user config fields `sink.google_contacts_profile` and `sink.odollo_tenant`.
- Default user config now includes empty profile/tenant placeholders.
- Live apply readiness reports missing profile/tenant config before live adapter checks.
- Configured Google Contacts profile and Odollo tenant names flow into lookup, write, and readback adapter request artifacts.
- No live credentials, tenant files, network calls, or writes are touched.

Validation:

- `.venv/bin/python -m pytest tests/test_config.py tests/test_service.py tests/test_sinks.py -q` passed with 54 tests.

## Turn 35 | 2026-06-13

Continued Plan 0004 execution with Google Workspace local readiness evidence.

Implemented:

- Google Contacts live readiness now reports local `gws` evidence without making Google API calls.
- Readiness distinguishes missing `gws`, missing auth evidence, missing People API discovery cache, and the still-blocked live write/readback gate.
- Readiness details include profile, `gws` path, config directory, auth evidence booleans, People discovery cache presence, required contact scopes, and an explicit note that scopes are not verified without a live call.
- Google adapter request contracts now include deterministic `gws` command vectors for lookup, write, and readback.
- Tests isolate `GOOGLE_WORKSPACE_CLI_CONFIG_DIR` for missing-auth behavior.

Validation:

- `.venv/bin/python -m pytest tests/test_sinks.py tests/test_service.py tests/test_config.py -q` passed with 55 tests.

## Turn 36 | 2026-06-13

Continued Plan 0004 execution with Odollo local readiness evidence.

Implemented:

- Odoo/Odollo live readiness now reports local Odollo tenant evidence without importing Odollo runtime code or making Odoo calls.
- Readiness distinguishes missing tenant config, missing Odollo user config, missing tenant home, missing tenant state evidence, and the still-blocked live tenant readiness gate.
- Readiness details include `ODOLLO_HOME`, `odollo.yml` presence, tenant home path, resource/artifact/action-log presence, state DB candidate presence, and a blocked live probe descriptor.
- The readiness contract mirrors Odollo's `odollo.core.odoo_readiness.odoo_readiness_report` boundary while keeping `network_calls_made = 0`.
- Tests isolate `ODOLLO_HOME` for missing-config and local-evidence behavior.

Validation:

- `.venv/bin/python -m pytest tests/test_sinks.py tests/test_service.py tests/test_config.py -q` passed with 57 tests.

## Turn 37 | 2026-06-13

Continued Plan 0004 execution with public-web search request artifacts.

Implemented:

- Added `enrichment_public_web_request.json` artifacts for public-web enrichment requests.
- Request artifacts include observed card fields, deterministic search queries, search URLs, operator/search-agent instructions, max query count, and readiness status.
- Public-web request artifacts record `network_calls_made = 0` and `search_calls_attempted = 0`.
- Service `request_enrichment` writes public-web request artifacts for `public_web` and `all` modes before result scoring.
- CLI/API/MCP enrichment surfaces receive the new payload through the shared service method.

Validation:

- `.venv/bin/python -m pytest tests/test_enrichment.py tests/test_cli_surfaces.py tests/test_mcp.py tests/test_api.py -q` passed with 32 tests.

## Turn 38 | 2026-06-13

Continued Plan 0004 execution with explicit apply pilot readiness artifacts.

Implemented:

- Added `sink_apply_pilot_readiness.json` artifacts for one-job live apply pilot readiness.
- Pilot readiness artifacts summarize preflight, apply decision, write adapter request, sink readiness, readback adapter availability, missing requirements, and operator commands.
- Pilot readiness artifacts record `can_apply_pilot = false`, `writes_attempted = 0`, and `network_calls_made = 0`.
- Service, CLI, API, and MCP surfaces can create the readiness artifact through shared service logic.
- Agent next actions recommend `sinks apply-pilot-readiness` after an approved sink apply decision and before the manual `sinks apply --apply` boundary.
- Safe agent-loop execution can create the readiness artifact but still skips manual apply approval and live apply.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py -q` passed with 60 tests.

## Turn 39 | 2026-06-13

Continued Plan 0004 execution with paid provider result artifacts.

Implemented:

- Added Apollo-style paid provider result scoring for caller-supplied fixture/provider rows.
- Added `enrichment_provider_result.json` artifacts with normalized person/company fields, confidence signals, merge proposals, and raw fixture rows.
- API-only enrichment requests also write `enrichment_result.json` from provider results so the existing enrichment merge review path remains shared.
- Provider result artifacts record `network_calls_made = 0` and `paid_api_calls_attempted = 0`.
- Service, CLI, API, and MCP enrichment request surfaces accept `provider_results` / `--provider-results-json`.
- Provider result tests cover service, CLI, API, MCP, and secret-free payload behavior.

Validation:

- `.venv/bin/python -m pytest tests/test_enrichment.py tests/test_cli_surfaces.py tests/test_mcp.py tests/test_api.py -q` passed with 34 tests.

## Turn 40 | 2026-06-13

Expanded Plan 0004 into the next high-level execution block for review surface, route freshness, normalization, enrichment execution, read-only sink lookup pilots, and one-job live apply pilots.

Captured:

- API-based enrichment remains explicitly requested because provider calls can cost money.
- Public-web enrichment should also execute only through an explicit bounded operator/search-agent action.
- Odollo enrichment, contact-point, readiness, lookup, and review semantics are implementation sources to inspect or adapt.
- `~/credentials/API-keys.env` can provide enrichment API key names/values to adapters, but secret values must not be printed or persisted.
- Safe agent loops may continue zero-network/zero-write route refresh and planning work, but cannot trigger paid enrichment or live apply.

Validation:

- Documentation-only planning update; run `git diff --check` before commit.

## Turn 41 | 2026-06-13

Continued Plan 0004 execution with route-refresh handling after review changes.

Implemented:

- Added `route_refresh.json` artifacts when reviewed contact changes, enrichment merge approvals, or duplicate resolution decisions make existing route artifacts stale.
- Route refresh artifacts track stale, refreshed, and pending route artifact kinds with zero-write and zero-network counters.
- `next_actions` now checks pending route refresh before trusting existing lookup, duplicate, sink plan, preflight, decision, readiness, apply, or readback artifacts.
- Safe next-action execution can replay stale zero-network/zero-write route phases from the first stale artifact.
- Stale manual apply decisions are not reused after a route refresh; the agent loop stops again at the manual decision boundary.
- Ledger events now record `route_refresh_requested` and `route_refresh_updated`.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py -q` passed with 38 tests.
- `.venv/bin/python -m pytest -q` passed with 128 tests.
- `PYTHONPATH=src pytest -q` passed with 124 tests and 3 skipped optional-extra tests.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed with the index up to date.
- `.venv/bin/bcw mcp-call business_card_watchdog_status --arguments-json '{}'` passed against the user config.

## Turn 42 | 2026-06-13

Continued Plan 0004 execution with a batch review bundle surface.

Implemented:

- Added run-level `review_bundle.json` artifacts for operator/agent batch review.
- Review bundles inline review-relevant artifact payloads for each job, including contact candidates, reviewed contacts, enrichment artifacts, duplicate assessments, sink plans, route refresh state, apply gates, and adapter requests.
- Review bundles include per-job next-action readback and command hints while keeping decisions routed through existing service methods.
- Added shared service `review_bundle`.
- Added CLI `bcw reviews bundle`.
- Added API `POST /runs/{run_id}/review-bundle`.
- Added MCP tool `business_card_watchdog_review_bundle`.
- Review bundle creation records `review_bundle_created` and a run-level `review_bundle` artifact with `job_id = "__run__"`.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py -q` passed with 63 tests.
- `.venv/bin/python -m pytest -q` passed with 128 tests.
- `PYTHONPATH=src pytest -q` passed with 124 tests and 3 skipped optional-extra tests.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed with the index up to date.
- `.venv/bin/bcw mcp-call business_card_watchdog_status --arguments-json '{}'` passed against the user config.

## Turn 43 | 2026-06-13

Continued Plan 0004 execution with explicit public-web enrichment result import.

Implemented:

- Added `enrichment_public_web_result.json` artifacts for operator/search-agent submitted public-web results.
- Public-web result artifacts consume an existing `enrichment_public_web_request.json`, preserve source request metadata, score submitted results, and emit merge proposals.
- Shared `enrichment_result.json` is written from public-web result imports so enrichment merge review stays on the existing path.
- Added service `record_public_web_enrichment_results`.
- Added CLI `bcw enrichment public-web-results`.
- Added API `POST /jobs/{job_id}/enrichment/public-web-results`.
- Added MCP tool `business_card_watchdog_public_web_enrichment_results`.
- Result import records zero network calls and zero search calls attempted; actual search remains an explicit external/operator action.

Validation:

- `.venv/bin/python -m pytest tests/test_enrichment.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py -q` passed with 38 tests.
- `.venv/bin/python -m pytest -q` passed with 132 tests.
- `PYTHONPATH=src pytest -q` passed with 127 tests and 3 skipped optional-extra tests.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed with the index up to date.
- `.venv/bin/bcw mcp-call business_card_watchdog_status --arguments-json '{}'` passed against the user config.

## Turn 44 | 2026-06-13

Continued Plan 0004 execution with contact-point and normalization metadata hardening.

Implemented:

- Added `[normalization] default_country` user config with default `US`.
- Orchestrator contact candidate creation now uses the configured normalization default country.
- Review corrections and enrichment merge approval now use the configured normalization default country.
- Contact candidates and reviewed contacts include a `normalization` metadata block.
- Normalized fields include `confidence` and `reason` metadata.
- Contact candidates and reviewed contacts include `contact_points` for email, phone, and website with value, raw observed value, source, confidence, and reason.
- Non-US/default-country phone numbers that cannot be safely normalized to E.164 are retained and marked for review instead of being over-normalized.

Validation:

- `.venv/bin/python -m pytest tests/test_contact.py tests/test_config.py tests/test_service.py tests/test_dry_run_pipeline.py -q` passed with 49 tests.
- `.venv/bin/python -m pytest -q` passed with 134 tests.
- `PYTHONPATH=src pytest -q` passed with 129 tests and 3 skipped optional-extra tests.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed with the index up to date.
- `.venv/bin/bcw mcp-call business_card_watchdog_status --arguments-json '{}'` passed against the user config.

## Turn 45 | 2026-06-13

Continued Plan 0004 execution with batch review decision import.

Implemented:

- Added run-scoped `review_decisions_import.json` artifacts for batch review decision imports.
- Batch imports call the existing `submit_review` path for each decision, preserving field validation, state transitions, reviewed-contact writes, duplicate resolution handling, and route refresh behavior.
- Added service `apply_review_decisions`.
- Added CLI `bcw reviews apply-decisions` with `--decisions-json` and `--decisions-file`.
- Added API `POST /runs/{run_id}/review-decisions`.
- Added MCP tool `business_card_watchdog_apply_review_decisions`.
- Import artifacts record zero network calls and zero sink writes.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py -q` passed with 66 tests.
- `.venv/bin/python -m pytest -q` passed with 135 tests.
- `PYTHONPATH=src pytest -q` passed with 130 tests and 3 skipped optional-extra tests.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed with the index up to date.
- `.venv/bin/bcw mcp-call business_card_watchdog_status --arguments-json '{}'` passed against the user config.

## Turn 46 | 2026-06-13

Continued Plan 0004 execution with a public-web result import budget guard.

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

## Turn 47 | 2026-06-13

Continued Plan 0004 execution with a paid-provider result import budget guard.

Implemented:

- Added `[enrichment] max_paid_provider_results_per_contact` user config with default `5`.
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

## Turn 48 | 2026-06-13

Continued Plan 0004 execution with run-level enrichment budget readback.

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

## Turn 49 | 2026-06-13

Continued Plan 0004 execution with run-level enrichment budget hard stops.

Implemented:

- Added `[enrichment] max_public_web_queries_per_run` user config with default `200`.
- Added `[enrichment] max_paid_provider_results_per_run` user config with default `50`.
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

## Turn 50 | 2026-06-13

Continued Plan 0004 execution with batch review bundle indexing.

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

## Turn 51 | 2026-06-13

Continued Plan 0004 execution with a static HTML review surface.

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

## Turn 52 | 2026-06-13

Continued Plan 0004 execution with duplicate-resolution route-refresh proof.

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

## Turn 53 | 2026-06-13

Continued Plan 0004 execution with full route-refresh chain proof.

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

## Turn 54 | 2026-06-13

Continued Plan 0004 execution with profile URL contact points.

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

## Turn 55 | 2026-06-13

Continued Plan 0004 execution with profile URL sink mapping.

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

## Turn 56 | 2026-06-13

Continued Plan 0004 execution with public-web search handoff artifacts.

Implemented:

- Added deterministic `enrichment_public_web_search_handoff.json` artifacts from existing public-web enrichment request artifacts.
- Handoffs carry source request status, query budget, zero-network counters, operator/search-agent instructions, and explicit result-import commands for CLI/API/MCP.
- Added service, CLI, API, and MCP surfaces for creating the handoff without making live search calls.
- Added the handoff artifact kind to review bundle indexing.

Validation:

- `.venv/bin/python -m pytest tests/test_enrichment.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py -q` passed with 42 tests.
- `.venv/bin/python -m pytest -q` passed with 145 tests.
- `PYTHONPATH=src pytest -q` passed with 140 tests and 3 skipped optional-extra tests.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed with the index up to date.
- `.venv/bin/bcw mcp-call business_card_watchdog_status --arguments-json '{}'` passed against the user config.

## Turn 57 | 2026-06-13

Continued Plan 0004 execution with paid-provider handoff and post-request result import.

Implemented:

- Added deterministic `enrichment_provider_handoff.json` artifacts from existing provider enrichment request artifacts.
- Provider handoffs preserve explicit approval state, provider operation details, max result budget, key environment variable name, and zero-call counters without writing credential values.
- Added service, CLI, API, and MCP surfaces for provider handoff creation.
- Added service, CLI, API, and MCP surfaces for importing paid-provider result rows after the original request artifact exists.
- Added the provider handoff artifact kind to review bundle indexing.

Validation:

- `.venv/bin/python -m pytest tests/test_enrichment.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py -q` passed with 44 tests.
- `.venv/bin/python -m pytest -q` passed with 147 tests.
- `PYTHONPATH=src pytest -q` passed with 142 tests and 3 skipped optional-extra tests.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed with the index up to date.
- `.venv/bin/bcw mcp-call business_card_watchdog_status --arguments-json '{}'` passed against the user config.

## Turn 58 | 2026-06-13

Continued Plan 0004 execution with explicit read-only sink lookup pilots.

Implemented:

- Added deterministic `sink_lookup_pilot.json` artifacts that require explicit job, run, sink, and reviewer approval metadata.
- Lookup pilots currently consume mocked/read-only match rows and make no network calls or writes.
- Lookup pilots also write the existing `sink_lookup_result.json` schema so downstream duplicate assessment can block routing through the shared path.
- Added service, CLI, API, and MCP surfaces for the lookup pilot.
- Added `sink_lookup_pilot` to review bundle and route-refresh artifact registries.

Validation:

- `.venv/bin/python -m pytest tests/test_sinks.py tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py -q` passed with 91 tests.
- `.venv/bin/python -m pytest -q` passed with 150 tests.
- `PYTHONPATH=src pytest -q` passed with 144 tests and 3 skipped optional-extra tests.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed with the index up to date.
- `.venv/bin/bcw mcp-call business_card_watchdog_status --arguments-json '{}'` passed against the user config.

## Turn 59 | 2026-06-13

Continued Plan 0004 execution with the read-only sink lookup adapter boundary.

Implemented:

- Added explicit GWS/Odollo read-only lookup adapter execution helpers that normalize downstream responses into existing match rows.
- GWS People responses normalize `resourceName`, names, emails, and phones into duplicate-review evidence.
- Odollo/Odoo `res.partner` rows normalize IDs into `odoo:res.partner:{id}` resources with match basis and raw evidence.
- Non-simulated lookup pilots can now use an injected read-only executor and record adapter execution evidence while keeping writes at zero.
- Existing `sink_lookup_result.json` output now carries read-only status and network-call count when produced by a non-simulated pilot.

Validation:

- `.venv/bin/python -m pytest tests/test_sink_lookup_adapters.py tests/test_sinks.py tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py -q` passed with 94 tests.
- `.venv/bin/python -m pytest -q` passed with 153 tests.
- `PYTHONPATH=src pytest -q` passed with 147 tests and 3 skipped optional-extra tests.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed with the index up to date.
- `.venv/bin/bcw mcp-call business_card_watchdog_status --arguments-json '{}'` passed against the user config.

## Turn 60 | 2026-06-13

Continued Plan 0004 execution with default read-only lookup runner construction.

Implemented:

- Added default GWS runner behavior for explicit non-simulated lookup pilots using adapter request command vectors, `--params`, and JSON output.
- Added default Odollo runner behavior for explicit non-simulated lookup pilots using the configured Odollo tenant profile and `OdooClient.search_read`.
- Kept default validation offline with mocked command/client tests.

Validation:

- `.venv/bin/python -m pytest tests/test_sink_lookup_adapters.py tests/test_service.py tests/test_sinks.py -q` passed with 68 tests.
- `.venv/bin/python -m pytest -q` passed with 155 tests.
- `PYTHONPATH=src pytest -q` passed with 149 tests and 3 skipped optional-extra tests.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed with the index up to date.
- `.venv/bin/bcw mcp-call business_card_watchdog_status --arguments-json '{}'` passed against the user config.

## Turn 61 | 2026-06-13

Continued Plan 0004 execution with a mock apply pilot readiness gate.

Implemented:

- Split `sink_apply_pilot_readiness.json` into mock-apply and live-apply readiness signals.
- Simulated apply now requires or creates ready pilot-readiness evidence before producing a mock apply result.
- Mock apply readiness requires local preflight, explicit apply approval, and local mock readback availability.
- Live apply remains blocked until live sink readiness plus write/readback adapter requirements pass.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py tests/test_sinks.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py -q` passed with 93 tests.
- `.venv/bin/python -m pytest -q` passed with 156 tests.
- `PYTHONPATH=src pytest -q` passed with 150 tests and 3 skipped optional-extra tests.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed with the index up to date.
- `.venv/bin/bcw mcp-call business_card_watchdog_status --arguments-json '{}'` passed against the user config.

## Turn 62 | 2026-06-13

Continued Plan 0004 execution with write and readback adapter execution boundaries.

Implemented:

- Added explicit GWS People and Odollo/Odoo write/readback adapter helpers in `sink_apply_adapters.py`.
- GWS helpers build command-vector calls from existing adapter requests and parse JSON output without running during default tests.
- Odollo helpers call `OdooClient.create` and `OdooClient.read` when explicitly invoked with tenant profile context.
- Adapter execution results normalize resource IDs, write counters, network counters, and readback evidence.
- Added an injected service write-executor path for one-job pilot proof while keeping default CLI/API/MCP live apply blocked.
- Injected service write execution records `live_applied` results and feeds returned resource IDs into existing readback adapter requests.

Validation:

- `.venv/bin/python -m pytest tests/test_sink_apply_adapters.py tests/test_service.py tests/test_sinks.py -q` passed with 74 tests.
- `.venv/bin/python -m pytest tests/test_sink_apply_adapters.py tests/test_service.py tests/test_sinks.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py -q` passed with 102 tests.
- `.venv/bin/python -m pytest -q` passed with 165 tests.
- `PYTHONPATH=src pytest -q` passed with 159 tests and 3 skipped optional-extra tests.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed with the index up to date.
- `.venv/bin/bcw mcp-call business_card_watchdog_status --arguments-json '{}'` passed against the user config.

## Turn 63 | 2026-06-13

Continued Plan 0004 execution with an explicit readback pilot surface.

Implemented:

- Added `sink_readback_pilot.json` artifacts for explicit read-only sink readback verification.
- Added service readback-pilot execution with simulated readback by default and injected/live readback execution when explicitly requested.
- Readback pilots require job, run, sink, and reviewer approval metadata while always recording zero writes.
- Added CLI, API, and MCP surfaces for the shared readback-pilot service method.
- Next-action readback now recommends the explicit readback pilot after a readback adapter request exists, but the safe agent-loop executor does not run it automatically.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py tests/test_sink_apply_adapters.py -q` passed with 87 tests.
- `.venv/bin/python -m pytest tests/test_service.py tests/test_sinks.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py tests/test_sink_apply_adapters.py -q` passed with 105 tests.
- `.venv/bin/python -m pytest -q` passed with 168 tests.
- `PYTHONPATH=src pytest -q` passed with 161 tests and 3 skipped optional-extra tests.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed with the index up to date.
- `.venv/bin/bcw mcp-call business_card_watchdog_status --arguments-json '{}'` passed against the user config.

## Turn 64 | 2026-06-13

Continued Plan 0004 execution with an explicit write pilot surface.

Implemented:

- Added `sink_write_pilot.json` artifacts for explicit one-job sink write pilot evidence.
- Added service write-pilot execution with simulated writes by default and live execution only on explicit non-simulated invocation.
- Write pilots require job, run, sink, reviewer approval metadata, and an approved sink apply decision.
- Simulated write pilots record zero writes while producing `sink_apply_result.json` for the existing readback adapter/pilot path.
- Non-simulated default execution refuses unless live pilot readiness is ready; injected tests exercise live-shaped writes offline.
- Added CLI, API, and MCP surfaces for the shared write-pilot service method.
- Next-action readback now recommends explicit write pilot after apply pilot readiness, while safe agent-loop execution still skips it.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py tests/test_sink_apply_adapters.py -q` passed with 89 tests.
- `.venv/bin/python -m pytest tests/test_service.py tests/test_sinks.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py tests/test_sink_apply_adapters.py -q` passed with 107 tests.
- `.venv/bin/python -m pytest -q` passed with 170 tests.
- `PYTHONPATH=src pytest -q` passed with 163 tests and 3 skipped optional-extra tests.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed with the index up to date.
- `.venv/bin/bcw mcp-call business_card_watchdog_status --arguments-json '{}'` passed against the user config.

## Turn 65 | 2026-06-13

Continued Plan 0004 execution with an apply pilot report surface.

Implemented:

- Added `sink_apply_pilot_report.json` artifacts summarizing readiness, write pilot, apply result, readback adapter request, and readback pilot evidence.
- Reports include complete/incomplete state, missing artifacts, per-sink resource IDs, simulated/live flags, readback match status, write counters, and network counters.
- Added service, CLI, API, and MCP surfaces for the shared report builder.
- Next-action readback now recommends report creation after explicit write and readback pilot evidence exists; safe agent-loop execution may create the zero-write report.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py tests/test_sink_apply_adapters.py -q` passed with 90 tests.
- `.venv/bin/python -m pytest tests/test_service.py tests/test_sinks.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py tests/test_sink_apply_adapters.py -q` passed with 108 tests.
- `.venv/bin/python -m pytest -q` passed with 171 tests.
- `PYTHONPATH=src pytest -q` passed with 164 tests and 3 skipped optional-extra tests.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed with the index up to date.
- `.venv/bin/bcw mcp-call business_card_watchdog_status --arguments-json '{}'` passed against the user config.

## Turn 66 | 2026-06-13

Captured the next high-level implementation plan for review, routing, normalization, enrichment, and dedupe hardening.

Planned:

- Added Plan 0005 as the repo-backed handoff for the next workstream after the current Plan 0004 sink-pilot surfaces.
- Made the review surface, canonical normalization, enrichment provider boundaries, duplicate resolution, routing policy, and agent-loop batch reporting separate workstreams.
- Documented that API-backed enrichment must remain explicitly requested, config-enabled, key-ready, and budget-limited.
- Documented that public-web enrichment is useful but still an explicit enrichment action, while generic safe agent loops remain no-paid-call and zero-write.
- Added Odollo adaptation guidance for copying reusable enrichment/contact helpers without importing broad tenant runtime coupling.
- Updated the roadmap to point at Plan 0005 as the next high-level plan.

Validation:

- `git diff --check` passed.

## Turn 67 | 2026-06-13

Continued Plan 0004 execution with review-bundle sink pilot status summaries.

Implemented:

- Added per-job `sink_pilot_status` to review bundles.
- Added `groups.by_sink_pilot_state` for batch-level review and agent-loop progress readback.
- Added sink pilot state to the static offline review HTML.
- Covered a full simulated lookup, downstream dedupe, sink plan, write pilot, readback pilot, and apply-pilot-report chain through the review bundle.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_review_bundle_includes_sink_pilot_status tests/test_service.py::test_service_apply_pilot_report_summarizes_write_and_readback tests/test_service.py::test_service_run_summary_and_review_queue -q` passed with 3 tests.
- `.venv/bin/python -m pytest tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py -q` passed with 83 tests.
- `.venv/bin/python -m pytest -q` passed with 172 tests.
- `PYTHONPATH=src pytest -q` passed with 165 tests and 3 skipped optional-extra tests.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed with the index up to date.
- `.venv/bin/bcw mcp-call business_card_watchdog_status --arguments-json '{}'` passed against the user config.

## Turn 68 | 2026-06-13

Continued Plan 0004 execution with run-summary sink pilot progress.

Implemented:

- Added `sink_pilot_summary` to run summaries.
- Reused the same per-job sink pilot status vocabulary used by review bundles.
- Added batch counts for sink pilot state, write pilots, readback pilots, pilot reports, complete reports, safe auto-continue actions, explicit operator actions, writes attempted, and network calls made.
- Kept CLI/API/MCP run-summary consumers on the shared service method.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_review_bundle_includes_sink_pilot_status tests/test_service.py::test_service_run_summary_and_review_queue -q` passed with 2 tests.
- `.venv/bin/python -m pytest tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py -q` passed with 83 tests.
- `.venv/bin/python -m pytest -q` passed with 172 tests.
- `PYTHONPATH=src pytest -q` passed with 165 tests and 3 skipped optional-extra tests.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed with the index up to date.
- `.venv/bin/bcw mcp-call business_card_watchdog_status --arguments-json '{}'` passed against the user config.

## Turn 69 | 2026-06-13

Continued Plan 0004 execution with a batch phase-report surface.

Implemented:

- Added read-only service `phase_report` for deterministic batch progress readback.
- Grouped jobs by ingest, normalize, review, enrichment, dedupe, route, sink lookup, apply approval, write pilot, readback pilot, and pilot report phases.
- Added per-phase counts and blocked/explicit-required next-action counts.
- Exposed the report through CLI `bcw runs phase-report`, API `GET /runs/{run_id}/phase-report`, and MCP `business_card_watchdog_phase_report`.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_run_summary_and_review_queue tests/test_service.py::test_service_review_bundle_includes_sink_pilot_status tests/test_cli_surfaces.py::test_cli_runs_and_jobs_use_recorded_runtime_state tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 6 tests.
- `.venv/bin/python -m pytest tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py -q` passed with 83 tests.
- `.venv/bin/python -m pytest -q` passed with 172 tests.
- `PYTHONPATH=src pytest -q` passed with 165 tests and 3 skipped optional-extra tests.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed with the index up to date.
- `.venv/bin/bcw mcp-call business_card_watchdog_status --arguments-json '{}'` passed against the user config.

## Turn 70 | 2026-06-13

Continued Plan 0004 execution with run-next phase snapshot readback.

Implemented:

- Added `phase_report_before` and `phase_report_after` to run-scoped safe next-action execution results.
- CLI, API, and MCP run-next surfaces now expose the same snapshots through the shared service method.
- Kept run-next execution limited to zero-write/no-paid-call safe actions.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_run_next_actions_executes_safe_steps_until_manual_decision tests/test_cli_surfaces.py::test_cli_jobs_review_records_submission tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 4 tests.
- `.venv/bin/python -m pytest tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py -q` passed with 83 tests.
- `.venv/bin/python -m pytest -q` passed with 172 tests.
- `PYTHONPATH=src pytest -q` passed with 165 tests and 3 skipped optional-extra tests.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed with the index up to date.
- `.venv/bin/bcw mcp-call business_card_watchdog_status --arguments-json '{}'` passed against the user config.

## Turn 71 | 2026-06-13

Continued Plan 0004 execution with phase stop-rule policy readback.

Implemented:

- Added machine-readable stop rules to phase reports.
- Stop rules identify safe auto actions, explicit operator actions, and phase-specific action policy.
- Generic continue policy now explicitly disallows paid API enrichment, public-web enrichment, live sink writes, and live sink readbacks.
- Reused the explicit-operator-action set in sink pilot status summaries.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_run_summary_and_review_queue tests/test_service.py::test_service_review_bundle_includes_sink_pilot_status tests/test_cli_surfaces.py::test_cli_runs_and_jobs_use_recorded_runtime_state tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 5 tests.
- `.venv/bin/python -m pytest tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py -q` passed with 83 tests.
- `.venv/bin/python -m pytest -q` passed with 172 tests.
- `PYTHONPATH=src pytest -q` passed with 165 tests and 3 skipped optional-extra tests.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed with the index up to date.
- `.venv/bin/bcw mcp-call business_card_watchdog_status --arguments-json '{}'` passed against the user config.

## Turn 72 | 2026-06-13

Continued Plan 0004 execution with review queue next-action filters.

Implemented:

- Added `next_action` and `artifact_kind` filters to the shared review queue.
- Included each queue entry's deterministic next action in queue output.
- Exposed the filters through CLI, API, and MCP.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_run_summary_and_review_queue tests/test_cli_surfaces.py::test_cli_runs_and_jobs_use_recorded_runtime_state tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 4 tests.
- `.venv/bin/python -m pytest tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py -q` passed with 83 tests.
- `.venv/bin/python -m pytest -q` passed with 172 tests.
- `PYTHONPATH=src pytest -q` passed with 165 tests and 3 skipped optional-extra tests.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed with the index up to date.
- `.venv/bin/bcw mcp-call business_card_watchdog_status --arguments-json '{}'` passed against the user config.

## Turn 73 | 2026-06-13

Continued Plan 0004 execution with review-bundle agent commands.

Implemented:

- Added phase-report and safe run-next commands to review bundles.
- Added MCP phase-report command text to the review bundle command set.
- Rendered bundle commands in the static offline review HTML.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_run_summary_and_review_queue tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_cli_surfaces.py::test_cli_runs_and_jobs_use_recorded_runtime_state tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 4 tests.
- `.venv/bin/python -m pytest tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py -q` passed with 83 tests.
- `.venv/bin/python -m pytest -q` passed with 172 tests.
- `PYTHONPATH=src pytest -q` passed with 165 tests and 3 skipped optional-extra tests.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed with the index up to date.
- `.venv/bin/bcw mcp-call business_card_watchdog_status --arguments-json '{}'` passed against the user config.

## Turn 74 | 2026-06-13

Continued Plan 0004 execution with MCP JSONL transport coverage for newer batch readback tools.

Implemented:

- Expanded the MCP JSONL/stdio server test beyond status calls.
- The test now verifies tool listing, phase-report calls, filtered review-list calls, explicit review-decision import, and safe run-next calls over JSON-RPC.
- The run-next JSON-RPC response is checked for `phase_report_before` and `phase_report_after` structured content.
- Kept the transport scenario zero-write/no-network; live sink and paid enrichment actions remain explicit operator actions.

Validation:

- `.venv/bin/python -m pytest tests/test_mcp.py::test_mcp_jsonl_server_lists_and_calls_tools -q` passed with 1 test.

## Turn 75 | 2026-06-13

Continued Plan 0004 execution with full pilot-chain route-refresh safety coverage.

Implemented:

- Added regression coverage for a review update after lookup, write, readback, and pilot-report artifacts already exist.
- The test proves `route_refresh.json` marks the full pilot chain stale.
- Safe run-next refreshes only the safe zero-network prefix and stops at explicit lookup-pilot evidence.
- No runtime behavior changed; this locks in the existing safety boundary.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_review_update_stales_full_pilot_chain_and_safe_refresh_stops_at_pilot -q` passed with 1 test.

## Turn 76 | 2026-06-13

Continued Plan 0004 execution with a CSV review workbook surface.

Implemented:

- Added `review_workbook.csv` generation from the shared review bundle.
- Exposed the workbook through service, CLI `bcw reviews workbook`, API `POST /runs/{run_id}/review-workbook`, and MCP `business_card_watchdog_review_workbook`.
- Workbook rows include job state, image path, next action, sink pilot state, contact fields, duplicate/enrichment/routing status, artifact kinds, review command, and decision template JSON.
- Added `contact_spec` to the review-bundle artifact registry.
- Kept the workbook surface read-only and zero-network/zero-write.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_run_summary_and_review_queue tests/test_cli_surfaces.py::test_cli_runs_and_jobs_use_recorded_runtime_state tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 5 tests.

## Turn 77 | 2026-06-13

Continued Plan 0004 execution with CSV review workbook decision import.

Implemented:

- Added service `apply_review_workbook_csv`.
- CSV imports parse workbook `decision_template_json` rows and use the existing shared review-decision submission path.
- Added CLI `bcw reviews apply-decisions --decisions-csv-file <path>`.
- Added `decisions_csv` support to API `POST /runs/{run_id}/review-decisions`.
- Added `decisions_csv` support to MCP `business_card_watchdog_apply_review_decisions`.
- CSV imports write the same `review_decisions_import.json` artifact with CSV source metadata.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_apply_review_workbook_csv_uses_decision_template_json tests/test_cli_surfaces.py::test_cli_runs_and_jobs_use_recorded_runtime_state tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 4 tests.

## Turn 78 | 2026-06-13

Continued Plan 0004 execution with editable review workbook decision columns.

Implemented:

- Added workbook columns for `review_action`, corrected contact fields, `review_notes`, and `skip_import`.
- CSV workbook import now converts edited contact columns into shared `field_corrections`.
- Kept `decision_template_json` as the advanced fallback.
- Service, CLI, API, and MCP tests now import decisions from editable workbook columns.
- No new external calls or write behavior was added.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_run_summary_and_review_queue tests/test_service.py::test_service_apply_review_workbook_csv_uses_decision_template_json tests/test_cli_surfaces.py::test_cli_runs_and_jobs_use_recorded_runtime_state tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 5 tests.

## Turn 79 | 2026-06-13

Continued Plan 0004 execution with workbook enrichment and duplicate decision columns.

Implemented:

- Added workbook columns for `approved_enrichment_fields`, `duplicate_decision`, `duplicate_target_identity`, and `duplicate_reason`.
- CSV import now maps those columns into the shared review-decision schema.
- Added service tests for enrichment merge approval and duplicate resolution from workbook rows.
- No new external calls or live write behavior was added.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_run_summary_and_review_queue tests/test_service.py::test_service_apply_review_workbook_csv_uses_decision_template_json tests/test_service.py::test_service_apply_review_workbook_csv_supports_enrichment_columns tests/test_service.py::test_service_apply_review_workbook_csv_supports_duplicate_resolution_columns -q` passed with 4 tests.

## Turn 80 | 2026-06-13

Continued Plan 0004 execution with review workbook preview before import.

Implemented:

- Added service `preview_review_workbook_csv` for zero-write validation of edited review workbooks.
- Preview reports ready, skipped, and error rows before applying review submissions.
- Preview validates unsupported review actions, missing jobs, missing enrichment-result artifacts, and missing duplicate-assessment prerequisites.
- Added CLI `bcw reviews apply-decisions --decisions-csv-file <path> --preview`.
- Added API/MCP preview flags on the existing review-decision import surfaces.
- No review artifacts, job states, external calls, or live sink writes are changed by preview.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_preview_review_workbook_csv_validates_without_writes tests/test_service.py::test_service_apply_review_workbook_csv_uses_decision_template_json tests/test_cli_surfaces.py::test_cli_runs_and_jobs_use_recorded_runtime_state tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 5 tests.

## Turn 81 | 2026-06-13

Continued Plan 0004 execution with spreadsheet-friendly review workbook preview validation.

Implemented:

- Review workbook preview now includes a `validation_csv` field for operator spreadsheet review.
- Validation CSV rows include row number, status, run/job/action, errors, warnings, artifact kinds, field correction count, approved enrichment fields, and duplicate-resolution fields.
- The same validation CSV is available through service, CLI, API, and MCP preview responses.
- No review artifacts, job states, external calls, or live sink writes are changed by preview.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_preview_review_workbook_csv_validates_without_writes tests/test_cli_surfaces.py::test_cli_runs_and_jobs_use_recorded_runtime_state tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 4 tests.

## Turn 82 | 2026-06-14

Continued Plan 0004 execution with sink-readiness warnings in review workbook preview.

Implemented:

- Review workbook preview now adds sink-readiness warnings for rows whose review action can move a contact toward routing.
- Blocked sink readiness is surfaced in row `warnings`, structured `sink_readiness_warnings`, and the spreadsheet `validation_csv`.
- Added regression coverage for live Google Contacts routing with apply disabled.
- Preview remains zero-write and does not perform external calls or live sink writes.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_preview_review_workbook_csv_validates_without_writes tests/test_service.py::test_service_preview_review_workbook_csv_warns_on_blocked_sink_readiness tests/test_cli_surfaces.py::test_cli_runs_and_jobs_use_recorded_runtime_state tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 5 tests.

## Turn 83 | 2026-06-14

Continued Plan 0004 execution with optional persisted workbook preview artifacts.

Implemented:

- Added optional `write` support to `preview_review_workbook_csv`.
- Persisted preview writes run-level `review_workbook_preview.json` and `review_workbook_preview_validation.csv` artifacts.
- CLI/API/MCP preview surfaces now support explicit preview artifact persistence through `--preview-write` / `preview_write`.
- Default preview remains non-mutating and still does not apply review decisions.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_preview_review_workbook_csv_validates_without_writes tests/test_service.py::test_service_preview_review_workbook_csv_can_persist_artifacts tests/test_cli_surfaces.py::test_cli_runs_and_jobs_use_recorded_runtime_state tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 5 tests.

## Turn 84 | 2026-06-14

Continued Plan 0004 execution with a dedicated validation CSV export command.

Implemented:

- Added CLI `bcw reviews preview-validation`.
- The command reads an edited review workbook CSV and prints only the validation CSV by default.
- Optional `--write-artifacts --json` persists and returns the same preview artifacts as the structured preview path.
- The command reuses the existing preview parser and does not apply review decisions.

Validation:

- `.venv/bin/python -m pytest tests/test_cli_surfaces.py::test_cli_runs_and_jobs_use_recorded_runtime_state tests/test_service.py::test_service_preview_review_workbook_csv_can_persist_artifacts tests/test_service.py::test_service_preview_review_workbook_csv_validates_without_writes -q` passed with 3 tests.

## Turn 85 | 2026-06-14

Continued Plan 0004 execution with API and MCP validation-only aliases.

Implemented:

- Added API `POST /runs/{run_id}/review-workbook-validation`.
- Added MCP tool `business_card_watchdog_review_workbook_validation`.
- Both aliases reuse the shared workbook preview parser and return `validation_csv` without applying review decisions.
- Optional preview artifact persistence remains explicit through `preview_write`.

Validation:

- `.venv/bin/python -m pytest tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 3 tests.

## Turn 86 | 2026-06-14

Continued Plan 0004 execution with run-summary preview validation readback.

Implemented:

- Added `review_workbook_preview_summary` to run summaries.
- Summary reports preview/validation artifact counts, latest preview paths, validity, ready/error/skipped row counts, and warning count.
- Missing or unreadable persisted preview artifacts are counted without failing run summary generation.
- Added service regression coverage for both no-preview and persisted-preview summary states.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_run_summary_and_review_queue tests/test_service.py::test_service_preview_review_workbook_csv_can_persist_artifacts -q` passed with 2 tests.

## Turn 87 | 2026-06-14

Continued Plan 0004 execution with phase-report preview validation readback.

Implemented:

- Added run-level `review_workbook_preview` to phase reports.
- Preview validation state is grouped as `not_started`, `valid`, `invalid`, or `unreadable`.
- The readback includes persisted preview counts, latest artifact paths, validity, ready/error/skipped row counts, and warning counts.
- Per-job phase rows remain unchanged.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_run_summary_and_review_queue tests/test_service.py::test_service_preview_review_workbook_csv_can_persist_artifacts -q` passed with 2 tests.
- `python -m py_compile src/business_card_watchdog/service.py` passed.

## Turn 88 | 2026-06-14

Continued Plan 0004 execution with phase-report preview surface coverage.

Implemented:

- Added explicit CLI coverage that `runs phase-report --json` includes `review_workbook_preview`.
- Added explicit API coverage that `GET /runs/{run_id}/phase-report` includes `review_workbook_preview`.
- Added explicit MCP direct-tool and JSON-RPC stdio coverage that phase-report payloads include `review_workbook_preview`.
- Kept existing phase-report transport contracts unchanged.

Validation:

- `.venv/bin/python -m pytest tests/test_cli_surfaces.py::test_cli_runs_and_jobs_use_recorded_runtime_state tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service tests/test_mcp.py::test_mcp_jsonl_server_lists_and_calls_tools -q` passed with 4 tests.
- `python -m py_compile tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py` passed.

## Turn 89 | 2026-06-14

Continued Plan 0004 execution with a phase-report dashboard summary.

Implemented:

- Added additive `dashboard_summary` to phase reports.
- Summary includes a compact status line, review workbook preview state, phase counts by attention category, and grouped blocked/explicit/pending/complete phase lists.
- Existing phase rows and CLI/API/MCP transport contracts remain unchanged.
- Added regression coverage across service, CLI, API, MCP direct-tool, and MCP JSON-RPC surfaces.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_run_summary_and_review_queue tests/test_service.py::test_service_review_bundle_includes_sink_pilot_status tests/test_cli_surfaces.py::test_cli_runs_and_jobs_use_recorded_runtime_state tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service tests/test_mcp.py::test_mcp_jsonl_server_lists_and_calls_tools -q` passed with 6 tests.
- `python -m py_compile src/business_card_watchdog/service.py tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py` passed.

## Turn 90 | 2026-06-14

Continued Plan 0004 execution with CLI phase-report text rendering.

Implemented:

- Added human-readable non-JSON output for `bcw runs phase-report`.
- Output includes the run id, state, job count, dashboard status line, review workbook preview state, and grouped phase counts.
- JSON output remains unchanged.
- Added CLI regression coverage to keep phase-report text output from falling back to a raw Python dict.

Validation:

- `.venv/bin/python -m pytest tests/test_cli_surfaces.py::test_cli_runs_and_jobs_use_recorded_runtime_state -q` passed with 1 test.
- `python -m py_compile src/business_card_watchdog/cli.py tests/test_cli_surfaces.py` passed.

## Turn 99 | 2026-06-14

Started Plan 0006 for public upstream hardening and executed the first CI/leak-gate slice.

Implemented:

- Added `docs/dev/plans/0006-2026-06-14-public-upstream-hardening.md`.
- Updated `ROADMAP.md` to make Plan 0006 the active implementation plan.
- Added `.github/workflows/ci.yml` for public push/PR validation.
- The workflow installs Python 3.11 with `uv`, installs `.[dev]`, runs pytest, runs ruff, builds package artifacts, and scans repository history with gitleaks.
- The workflow seeds a minimal offline `business-card-to-contact` skill fixture for status/doctor tests.
- The secret scan uses the `zricethezav/gitleaks:v8.30.1` CLI container instead of the licensed organization action.
- Fixed small ruff findings in `dedupe.py` and `sinks.py` so the new lint gate is enforceable.

Validation:

- `.venv/bin/python -m pytest -q` passed with 179 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` built source and wheel distributions.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` scanned 92 commits and found no leaks.
- First upstream workflow run failed before this adjustment because the CI runner lacked the user-scoped skill and `gitleaks/gitleaks-action@v2` required an organization license.
- Second upstream workflow run passed for both jobs: `Test, lint, and build` and `Secret scan`.
- Configured `main` branch protection requiring both CI jobs, with force-push and deletion disabled.

## Turn 100 | 2026-06-14

Continued Plan 0006 with public collaboration templates.

Implemented:

- Added GitHub issue templates for bug reports, feature requests, live-pilot requests, and bounded plan slices.
- Added a pull request template with validation and privacy/safety checks.
- Added `SECURITY.md` with reporting and data-handling guidance.
- Updated CI to opt JavaScript actions into Node 24 and disabled `setup-uv` cache until a lockfile exists.

Validation:

- `git diff --check` passed.
- `.venv/bin/ruff check .` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` scanned 95 commits and found no leaks.
- `rg -n 'private business-card images|raw OCR|API keys|Live pilot|Plan slice|FORCE_JAVASCRIPT_ACTIONS_TO_NODE24|enable-cache' .github SECURITY.md docs/dev/plans/0006-2026-06-14-public-upstream-hardening.md RUNBOOK.md` passed.

## Turn 101 | 2026-06-14

Continued Plan 0006 with clean public clone validation.

Implemented:

- Added `docs/operations/public-upstream-validation.md`.
- Documented public clone, `uv` install, offline skill fixture seeding, CLI smoke, pytest, ruff, and build commands.
- Linked the validation runbook from README.

Validation:

- Cloned `https://github.com/CochranResearchGroup/business-card-watchdog.git` into `/tmp/bcw-public-clone.3OrD8L/business-card-watchdog`.
- `uv venv --python 3.11` installed CPython 3.11.15.
- `uv pip install --python .venv/bin/python -e '.[dev]'` installed the package and dev tools.
- `.venv/bin/bcw --help` returned successfully.
- `.venv/bin/python -m pytest -q` passed with 172 tests and 3 skipped optional-extra tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` built source and wheel distributions.

## Turn 102 | 2026-06-14

Continued Plan 0006 with live pilot checklists.

Implemented:

- Added `docs/operations/live-pilot-checklists.md`.
- Documented read-only lookup smoke prerequisites, commands, review requirements, and stop conditions.
- Documented one-job write/readback pilot prerequisites, commands, completion evidence, and remediation notes.
- Linked the checklist from README.

Validation:

- `git diff --check` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` scanned 97 commits and found no leaks.
- `rg -n 'live-pilot-checklists|Read-Only Lookup Smoke|One-Job Write And Readback Pilot|Stop conditions|No live lookup or write was run|--no-simulate' README.md docs/operations/live-pilot-checklists.md docs/dev/plans/0006-2026-06-14-public-upstream-hardening.md RUNBOOK.md` passed.

## Turn 103 | 2026-06-14

Continued Plan 0006 with release-readiness documentation.

Implemented:

- Added `docs/operations/release-readiness.md`.
- Documented pre-release gates, branch-protection readback, private-artifact check, annotated tag command, GitHub release command, and v0.1.0 release notes.
- Linked the release-readiness runbook from README.
- Added public repository topics: `app-intelligence`, `business-cards`, `contacts`, `google-workspace`, `mcp`, `ocr`, and `odoo`.
- Published annotated tag and GitHub release `v0.1.0`.

Validation:

- `git diff --check` passed.
- `.venv/bin/python -m pytest -q` passed with 179 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` built source and wheel distributions.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` scanned 98 commits and found no leaks.
- `gh api repos/CochranResearchGroup/business-card-watchdog/branches/main/protection --jq '{strict:.required_status_checks.strict, contexts:.required_status_checks.contexts, allow_force_pushes:.allow_force_pushes.enabled, allow_deletions:.allow_deletions.enabled}'` confirmed strict checks, disabled force pushes, and disabled deletion.
- `git ls-files | rg '(\.env|secret|credential|token|\.key|\.pem|\.p12|\.sqlite|\.db|\.jpg|\.jpeg|\.png|\.heic)' || true` returned no tracked private-artifact paths.
- `rg -n 'release-readiness|v0.1.0|Initial public source release|Paid enrichment remains explicitly requested' README.md docs/operations/release-readiness.md docs/dev/plans/0006-2026-06-14-public-upstream-hardening.md RUNBOOK.md` passed.
- Latest pre-release CI run `27507317451` passed `Test, lint, and build` and `Secret scan`.
- `git ls-remote --tags upstream v0.1.0` returned `refs/tags/v0.1.0`.
- `gh release view v0.1.0 --repo CochranResearchGroup/business-card-watchdog --json tagName,name,url,isDraft,isPrerelease,publishedAt,targetCommitish` confirmed a published non-draft, non-prerelease release.
- `gh repo view CochranResearchGroup/business-card-watchdog --json repositoryTopics,description,visibility,url` confirmed the public repository topics.

## Turn 104 | 2026-06-14

Closed Plan 0006 for public-release hardening.

Implemented:

- Updated `docs/dev/plans/0006-2026-06-14-public-upstream-hardening.md` state to `COMPLETE_FOR_PUBLIC_RELEASE`.
- Reconciled stale remaining-work notes for completed public CI, collaboration-template, branch-protection, clean-clone, and release slices.
- Added a Plan 0006 completion audit with public repo, CI, branch-protection, clean-clone, live-pilot checklist, and v0.1.0 release evidence.

Validation:

- Latest upstream CI run `27507366888` passed both required jobs: `Test, lint, and build` and `Secret scan`.
- Plan 0006 remaining work is now scoped to out-of-plan live pilot execution requiring selected target inputs and local auth.

## Turn 98 | 2026-06-14

Continued Plan 0004 execution with a current completion and residual backlog audit.

Implemented:

- Added Slice 0004-CG to `docs/dev/plans/0004-2026-06-13-review-normalization-enrichment-dedupe-sinks.md`.
- Documented the current repo-local capability baseline after the later review, route-refresh, enrichment, sink-pilot, CLI/API/MCP, agent-loop, and operations-documentation slices.
- Separated remaining work into explicit live lookup/write/readback smoke pilots, paid-provider production adapter decisions, optional screenshots, and git remote configuration.

Validation:

- `git diff --check` passed.
- `rg -n 'Slice 0004-CG|Current repo-local capability baseline|Residual backlog|git remote' docs/dev/plans/0004-2026-06-13-review-normalization-enrichment-dedupe-sinks.md` passed.

## Turn 95 | 2026-06-14

Continued Plan 0004 execution with README CLI review-surface readback.

Implemented:

- Updated README operator commands to show human-readable run, phase-report, job, and review queue surfaces.
- Kept `--json` guidance explicit for automation consumers.
- Documented review queue and job show commands alongside run discovery so operators can inspect imported cards without reading raw JSON by default.

Validation:

- `git diff --check` passed.
- `.venv/bin/python -m pytest tests/test_cli_surfaces.py::test_cli_runs_and_jobs_use_recorded_runtime_state -q` passed with 1 test.
- `rg -n 'bcw runs list|bcw runs summary|bcw runs phase-report|bcw jobs show|bcw reviews list|--json' README.md` passed.
- `python -m py_compile src/business_card_watchdog/cli.py tests/test_cli_surfaces.py` passed.

## Turn 96 | 2026-06-14

Continued Plan 0004 execution with a review workflow operations walkthrough.

Implemented:

- Added `docs/operations/review-workflow.md`.
- Documented the operator path from intake through run/job inspection, review queue inspection, workbook preview/import, enrichment guardrails, duplicate/routing checks, explicit sink-pilot gates, and safe deterministic continuation.
- Linked the workflow from README operational details.
- Kept automation guidance aligned with existing `--json` surfaces.

Validation:

- `git diff --check` passed.
- `.venv/bin/python -m pytest tests/test_cli_surfaces.py::test_cli_runs_and_jobs_use_recorded_runtime_state -q` passed with 1 test.
- `rg -n 'review-workflow|reviews preview-validation|reviews apply-decisions|sinks write-pilot|actions run-next|--allow-paid-enrichment' README.md docs/operations/review-workflow.md` passed.

## Turn 97 | 2026-06-14

Continued Plan 0004 execution with review workflow sample output.

Implemented:

- Added `docs/operations/review-workflow-sample-output.md`.
- Documented representative text output for run discovery, run show, run summary, phase report, job list/show, review queue, empty filtered review queue, workbook preview validation CSV, persisted preview JSON, and safe continuation stops.
- Linked the sample output from the review workflow and README.

Validation:

- `git diff --check` passed.
- `.venv/bin/python -m pytest tests/test_cli_surfaces.py::test_cli_runs_and_jobs_use_recorded_runtime_state -q` passed with 1 test.
- `rg -n 'review-workflow-sample-output|Run: run-001|Review queue: 1 jobs|row_number,status|actions run-next' README.md docs/operations/review-workflow.md docs/operations/review-workflow-sample-output.md` passed.

## Turn 94 | 2026-06-14

Continued Plan 0004 execution with CLI run list/show text summaries.

Implemented:

- Added human-readable non-JSON output for `bcw runs list`.
- Added human-readable non-JSON output for `bcw runs show`.
- Run list output includes run count plus compact rows with run id, state, job count, and updated timestamp.
- Run show output includes run id, state, job count, loaded job count, artifact count, and run directory.
- JSON output remains unchanged.
- Added CLI regression coverage to keep run list/show text output from falling back to raw Python list/dict output.

Validation:

- `.venv/bin/python -m pytest tests/test_cli_surfaces.py::test_cli_runs_and_jobs_use_recorded_runtime_state -q` passed with 1 test.
- `python -m py_compile src/business_card_watchdog/cli.py tests/test_cli_surfaces.py` passed.

## Turn 93 | 2026-06-14

Continued Plan 0004 execution with CLI job text summaries.

Implemented:

- Added human-readable non-JSON output for `bcw jobs list`.
- Added human-readable non-JSON output for `bcw jobs show`.
- Job list output includes job count plus compact rows with job id, run id, state, and image path.
- Job show output includes job id, run id, state, image path, artifact kinds, and any error.
- JSON output remains unchanged.
- Added CLI regression coverage to keep job list/show text output from falling back to raw Python list/dict output.

Validation:

- `.venv/bin/python -m pytest tests/test_cli_surfaces.py::test_cli_runs_and_jobs_use_recorded_runtime_state -q` passed with 1 test.
- `python -m py_compile src/business_card_watchdog/cli.py tests/test_cli_surfaces.py` passed.

## Turn 92 | 2026-06-14

Continued Plan 0004 execution with CLI review-queue text rendering.

Implemented:

- Added human-readable non-JSON output for `bcw reviews list`.
- Output includes queue count plus compact rows with job id, state, next action, and artifact kinds.
- Empty review queues render as an explicit zero-job summary.
- JSON output remains unchanged.
- Added CLI regression coverage to keep review-list text output from falling back to raw Python list/dict output.

Validation:

- `.venv/bin/python -m pytest tests/test_cli_surfaces.py::test_cli_runs_and_jobs_use_recorded_runtime_state -q` passed with 1 test.
- `python -m py_compile src/business_card_watchdog/cli.py tests/test_cli_surfaces.py` passed.

## Turn 91 | 2026-06-14

Continued Plan 0004 execution with CLI run-summary text rendering.

Implemented:

- Added human-readable non-JSON output for `bcw runs summary`.
- Output includes run id, state, job count, review/routing/failure counts, enrichment budget counters, sink pilot counters, and review workbook preview validation state.
- JSON output remains unchanged.
- Added CLI regression coverage to keep run-summary text output from falling back to a raw Python dict.

Validation:

- `.venv/bin/python -m pytest tests/test_cli_surfaces.py::test_cli_runs_and_jobs_use_recorded_runtime_state -q` passed with 1 test.
- `python -m py_compile src/business_card_watchdog/cli.py tests/test_cli_surfaces.py` passed.

## Turn 106 | 2026-06-14

Continued Plan 0005 execution with the first review-matrix slice.

Implemented:

- Added per-job review matrix data to review bundle entries.
- Summarized contact source, key contact fields, normalization warning count, duplicate state, enrichment state, route state, sink lookup state, sink pilot state, next action, and safe/explicit action flags.
- Added review bundle groups by duplicate, enrichment, route, and sink lookup states.
- Rendered the review matrix into the offline HTML review surface and CSV workbook export.
- Excluded local `.codegraph` state from Hatch source distributions so transient local index files cannot enter or destabilize package builds.
- Updated the roadmap so Plan 0005 is the active product-hardening plan now that Plan 0006 public upstream hardening is closed.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_run_summary_and_review_queue tests/test_service.py::test_service_review_bundle_includes_sink_pilot_status -q` passed with 2 tests.
- `.venv/bin/python -m pytest -q` passed with 179 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed and reported the index is up to date.

Safety:

- This was a readback/reporting slice only. It made no public-web search, paid enrichment, GWS, Odollo/Odoo, or live sink calls.

## Turn 107 | 2026-06-14

Continued Plan 0005 execution with the canonical-contact provenance slice.

Implemented:

- Added `business-card-watchdog.canonical-contact.v1` inside contact candidate and reviewed contact artifacts.
- Added per-field provenance chains for observed card data, normalization, reviewer corrections, and approved enrichment values.
- Added provenance diagnostics for review-needed fields and selected source counts.
- Preserved the existing flat contact spec while adding service-loaded `_canonical_contact` and `_field_provenance` metadata for downstream planning.
- Added `field_provenance` to dry-run sink payload values so planned writes can cite field sources.

Validation:

- `.venv/bin/python -m pytest tests/test_contact.py tests/test_sinks.py tests/test_service.py::test_service_run_summary_and_review_queue tests/test_service.py::test_service_review_bundle_includes_sink_pilot_status -q` passed with 26 tests.
- `.venv/bin/python -m pytest -q` passed with 180 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed and reported the index is up to date.

Safety:

- This was local schema and payload-readback work only. It made no public-web search, paid enrichment, GWS, Odollo/Odoo, or live sink calls.

## Turn 108 | 2026-06-14

Continued Plan 0005 execution with the durable duplicate-resolution index slice.

Implemented:

- Added `business-card-watchdog.duplicate-resolution-index.v1` records in the user-scoped identity directory.
- Added `duplicate-resolutions.jsonl` next to the existing contact identity index.
- Persisted explicit duplicate-resolution review decisions into the durable index.
- Added suppression for reviewer-cleared `create_new` false-positive duplicate pairs.
- Kept unresolved duplicate matches blocking and preserved per-job `duplicate_resolution.json` plus route-refresh behavior.

Validation:

- `.venv/bin/python -m pytest tests/test_dedupe.py tests/test_service.py::test_service_submit_review_resolves_duplicate_for_routing tests/test_service.py::test_service_submit_review_resolves_duplicate_noop_as_cancelled -q` passed with 6 tests.
- `.venv/bin/python -m pytest -q` passed with 181 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed and reported the index is up to date.

Safety:

- This was local identity-index and review-artifact work only. It made no public-web search, paid enrichment, GWS, Odollo/Odoo, or live sink calls.

## Turn 109 | 2026-06-14

Continued Plan 0005 execution with the explainable route-policy slice.

Implemented:

- Added `business-card-watchdog.route-explanation.v1` metadata to route decisions.
- Recorded configured sinks, route context, matched rules, and excluded rules with reasons.
- Added route predicates for organization, source folder, tenant, duplicate state, and review state while preserving email-domain behavior.
- Added sink eligibility reports that keep route eligibility separate from apply approval.
- Persisted route explanation and sink eligibility into `sink_plan.json` and `sink_lookup_plan.json`.

Validation:

- `.venv/bin/python -m pytest tests/test_routing.py tests/test_service.py::test_service_plan_sinks_for_job_writes_dry_run_plan tests/test_service.py::test_service_plan_sink_lookup_for_job_writes_zero_network_plan -q` passed with 6 tests.
- `.venv/bin/python -m pytest -q` passed with 183 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed and reported the index is up to date.

Safety:

- This was local route-policy and artifact-readback work only. It made no public-web search, paid enrichment, GWS, Odollo/Odoo, or live sink calls.

## Turn 110 | 2026-06-14

Continued Plan 0005 execution with the Odollo enrichment reuse slice.

Implemented:

- Inspected Odollo public-web enrichment, Apollo adapter/result shape handling, contact-point handling, merge policy, and idempotency guidance.
- Adapted Odollo public-web phone normalization/query forms into watchdog public-web query generation.
- Adapted directory-aware public-web scoring hints into local fixture/result scoring.
- Adapted Apollo person/contact/data/list wrapper extraction patterns into local paid-provider result normalization.
- Added `adapted_from_odollo_enrichment_patterns` markers to public-web and provider request/result/handoff artifacts.

Validation:

- `.venv/bin/python -m pytest tests/test_enrichment.py -q` passed with 20 tests.
- `.venv/bin/python -m pytest -q` passed with 186 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed and reported the index is up to date.

Safety:

- This was local helper adaptation and fixture scoring only. It made no public-web search, paid enrichment, GWS, Odollo/Odoo, or live sink calls.

## Turn 111 | 2026-06-14

Continued Plan 0005 execution with the enrichment proposal review slice.

Implemented:

- Added `business-card-watchdog.enrichment-proposal-review.v1` artifacts.
- Recorded each enrichment merge proposal as accepted or rejected during `approve_enrichment_merge`.
- Preserved `enrichment_merge_review.json` while adding first-class accepted/rejected proposal evidence.
- Added accepted/rejected enrichment counts to review matrix entries and CSV review workbook columns.
- Recorded rejected counts and proposal-review artifact paths in `enrichment_merge_reviewed` events.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_submit_review_approves_enrichment_merge tests/test_service.py::test_service_apply_review_workbook_csv_supports_enrichment_columns -q` passed with 2 tests.
- `.venv/bin/python -m pytest -q` passed with 186 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed and reported the index is up to date.

Safety:

- This recorded explicit operator enrichment-review decisions only. It made no public-web search, paid enrichment, GWS, Odollo/Odoo, or live sink calls.

## Turn 112 | 2026-06-14

Continued Plan 0005 execution with the pilot readiness report slice.

Implemented:

- Added `business-card-watchdog.pilot-readiness-report.v1`.
- Combined phase report, review bundle, review matrix, next actions, enrichment budget, and sink pilot summary into one run-level readiness readback.
- Added per-job readiness states, blocking reasons, artifact paths, and commands.
- Exposed the report through CLI `bcw runs pilot-readiness`, API `GET /runs/{run_id}/pilot-readiness`, and MCP `business_card_watchdog_pilot_readiness_report`.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_run_summary_and_review_queue tests/test_service.py::test_service_review_bundle_includes_sink_pilot_status tests/test_cli_surfaces.py::test_cli_runs_and_jobs_use_recorded_runtime_state tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service tests/test_mcp.py::test_mcp_jsonl_server_lists_and_calls_tools -q` passed with 7 tests.
- `.venv/bin/python -m pytest -q` passed with 186 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed and reported the index is up to date.

Safety:

- This was readback-only. It made no public-web search, paid enrichment, GWS, Odollo/Odoo, or live sink calls.
- The report identifies explicit write/readback pilot readiness but does not approve or execute pilots.

## Turn 113 | 2026-06-14

Closed Plan 0005 with the MCP/API/CLI parity and simulated pilot-chain slice.

Implemented:

- Audited Plan 0005 parity for the new pilot readiness report across service, CLI, API, direct MCP, and JSONL MCP transport.
- Added `test_service_safe_loop_and_manual_steps_complete_simulated_pilot_chain`.
- The acceptance test proves reviewer approval, safe agent-loop progression, explicit apply approval, explicit simulated write pilot, simulated apply result, explicit readback pilot, safe pilot-report generation, and final pilot readiness `complete` state.
- Marked `docs/dev/plans/0005-2026-06-13-review-routing-normalization-enrichment-dedupe.md` complete.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_safe_loop_and_manual_steps_complete_simulated_pilot_chain -q` passed with 1 test.
- `.venv/bin/python -m pytest -q` passed with 187 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed and reported the index is up to date.

Safety:

- This was fixture-backed validation only. It made no public-web search, paid enrichment, GWS, Odollo/Odoo, or live sink calls.

## Turn 114 | 2026-06-14

Opened Plan 0007 for live pilot readiness and implemented the read-only lookup readiness slice.

Implemented:

- Added `docs/dev/plans/0007-2026-06-14-live-pilot-readiness-and-evidence.md`.
- Added `business-card-watchdog.live-lookup-readiness.v1`.
- Added service `live_lookup_readiness_report`.
- Added CLI `bcw sinks lookup-readiness`, API `POST /jobs/{job_id}/sink-lookup-readiness`, and MCP `business_card_watchdog_sink_lookup_readiness`.
- Tightened live lookup readiness so Google Contacts requires a configured profile plus local GWS auth evidence, and Odollo/Odoo requires configured tenant/local state evidence.
- Updated README and live-pilot checklist with the new readiness command.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_live_lookup_readiness_blocks_until_requirements_exist tests/test_service.py::test_service_live_lookup_readiness_ready_with_local_gws_evidence tests/test_cli_surfaces.py::test_cli_runs_and_jobs_use_recorded_runtime_state tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 6 tests.
- `.venv/bin/python -m pytest -q` passed with 189 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed and reported the index is up to date.

Safety:

- This was read-only readiness reporting only. It made no public-web search, paid enrichment, GWS, Odollo/Odoo, or live sink calls.

## Turn 115 | 2026-06-14

Continued Plan 0007 with live lookup result-import hardening.

Implemented:

- Added redacted execution metadata for non-simulated lookup pilot artifacts.
- Redacted raw adapter execution payloads and raw per-match evidence before writing live-shaped `sink_lookup_pilot.json` and `sink_lookup_result.json`.
- Preserved resource ID, confidence, basis, sink, network-call count, and write count for downstream duplicate assessment and audit.
- Kept simulated/fixture lookup artifacts unchanged for offline review tests and fixtures.

Validation:

- `.venv/bin/python -m pytest tests/test_sinks.py::test_build_sink_lookup_pilot_redacts_live_execution_payloads tests/test_service.py::test_service_lookup_pilot_uses_injected_read_only_executor tests/test_service.py::test_service_assess_downstream_duplicates_blocks_review_and_can_resolve tests/test_api.py::test_api_executes_sink_lookup_pilot_with_mocked_matches tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 5 tests.
- `.venv/bin/python -m pytest -q` passed with 190 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed and reported the index is up to date.

Safety:

- This was artifact-hardening work only. It made no public-web search, paid enrichment, GWS, Odollo/Odoo, or live sink calls.

## Turn 116 | 2026-06-14

Continued Plan 0007 with selected-sink write/readback pilot readiness.

Implemented:

- Added optional selected-sink scoping to the one-job apply pilot readiness artifact.
- Added CLI `bcw sinks apply-pilot-readiness <job-id> --run-id <run-id> --sink <sink>`.
- Added API and MCP parity for selected-sink readiness.
- Filtered readiness requirements and selected actions to the requested sink.
- Added readiness commands for selected-sink mock/live write and readback pilots.
- Guarded non-simulated write pilots from reusing a readiness artifact prepared for another sink.
- Updated live pilot operator docs to require selected-sink readiness.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_apply_pilot_readiness_can_scope_to_selected_sink tests/test_api.py::test_api_sink_readback_pilot_writes_zero_write_artifact tests/test_cli_surfaces.py::test_cli_sinks_apply_decision_writes_zero_write_artifact tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 4 tests.
- `.venv/bin/python -m pytest -q` passed with 191 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed and reported the index is up to date.

Safety:

- This was zero-network, zero-write readiness work only. It made no public-web search, paid enrichment, GWS, Odollo/Odoo, or live sink calls.

## Turn 117 | 2026-06-14

Continued Plan 0007 with the operator pilot bundle slice.

Implemented:

- Added `business-card-watchdog.sink-apply-pilot-bundle.v1` for one-job, selected-sink live pilot handoff.
- Added service `build_sink_apply_pilot_bundle_for_job`.
- Added CLI `bcw sinks apply-pilot-bundle <job-id> --run-id <run-id> --sink <sink> --operator <operator>`.
- Added API `POST /jobs/{job_id}/sink-apply-pilot-bundle`.
- Added MCP `business_card_watchdog_sink_apply_pilot_bundle`.
- Registered `sink_apply_pilot_bundle.json` for route-refresh staleness and review-bundle visibility.
- Bundle artifacts include selected-sink commands, requirements, missing requirements, stop conditions, and sink-specific remediation notes.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_apply_pilot_bundle_collects_selected_sink_commands_and_stops tests/test_api.py::test_api_sink_readback_pilot_writes_zero_write_artifact tests/test_cli_surfaces.py::test_cli_sinks_apply_decision_writes_zero_write_artifact tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 5 tests.
- `.venv/bin/python -m pytest -q` passed with 192 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed and reported the index is up to date.

Safety:

- This was zero-network, zero-write handoff work only. It made no public-web search, paid enrichment, GWS, Odollo/Odoo, or live sink calls.

## Turn 118 | 2026-06-14

Continued Plan 0007 with the live lookup smoke handoff slice.

Implemented:

- Added `business-card-watchdog.sink-lookup-smoke-handoff.v1` for selected run/job/sink read-only live lookup smoke handoff.
- Added service `build_sink_lookup_smoke_handoff_for_job`.
- Added CLI `bcw sinks lookup-smoke-handoff <job-id> --run-id <run-id> --sink <sink> --approved-by <operator>`.
- Added API `POST /jobs/{job_id}/sink-lookup-smoke-handoff`.
- Added MCP `business_card_watchdog_sink_lookup_smoke_handoff`.
- Registered `sink_lookup_smoke_handoff.json` for route-refresh staleness and review-bundle visibility.
- Updated live pilot docs to require reviewing the handoff before `lookup-pilot --no-simulate`.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_lookup_smoke_handoff_packages_selected_target_without_network tests/test_api.py::test_api_executes_sink_lookup_pilot_with_mocked_matches tests/test_cli_surfaces.py::test_cli_sinks_lookup_result_writes_zero_network_artifact tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 5 tests.
- `.venv/bin/python -m pytest -q` passed with 193 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed and reported the index is up to date.

Safety:

- This was zero-network, zero-write handoff work only. It made no public-web search, paid enrichment, GWS, Odollo/Odoo, or live sink calls.
- No live lookup smoke was executed because no explicit operator-selected live target was provided in this turn.

## Turn 119 | 2026-06-14

Closed Plan 0007 and created the next high-level execution plan for runtime operations.

Completed:

- Marked `docs/dev/plans/0007-2026-06-14-live-pilot-readiness-and-evidence.md` complete.
- Added closeout evidence for all five Plan 0007 slices and the final validation gate.
- Preserved the live-action boundary: no live lookup, live write, live readback, public-web search, or paid API enrichment was executed.
- Added `docs/dev/plans/0008-2026-06-14-runtime-installation-and-pilot-operations.md`.

Next plan:

- Plan 0008 focuses on user-scope runtime readiness, watched SyncThing dry-run proof, service/watch diagnostics, durable selected-target approval records, and a read-only live smoke only after explicit operator approval.

## Turn 120 | 2026-06-14

Started Plan 0008 execution with Slice 0008-A.

Implemented:

- Added `business-card-watchdog.runtime-readiness.v1` runtime readiness reports.
- Added `BusinessCardService.runtime_readiness`.
- Added CLI `bcw runtime-readiness`.
- Added API `GET /runtime/readiness`.
- Added MCP tool `business_card_watchdog_runtime_readiness`.
- Report includes config-file evidence, user runtime directory checks, service unit status, watcher status, blocked/warning checks, safe next actions, and explicit stop conditions.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_runtime_readiness_reports_user_scope_runtime_state tests/test_cli_surfaces.py::test_cli_runtime_readiness_reports_local_runtime_state tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 5 tests.

Safety:

- This was local runtime readiness work only. It made no public-web search, paid enrichment, GWS, Odollo/Odoo, live lookup, live write, live readback, or private SyncThing image processing calls.

## Turn 121 | 2026-06-14

Continued Plan 0008 with Slice 0008-B.

Implemented:

- Added `business-card-watchdog.watch-dry-run-harness.v1`.
- Added `BusinessCardService.watch_dry_run_harness`.
- Added CLI `bcw watch-dry-run`.
- Added API `POST /watch/dry-run`.
- Added MCP tool `business_card_watchdog_watch_dry_run`.
- Harness creates a synthetic cache-local watch source, processes it through watcher dry-run state once, restarts watcher state, and proves the second scan does not reprocess the seen file.

Validation:

- `.venv/bin/python -m pytest tests/test_watcher.py::test_service_watch_dry_run_harness_uses_synthetic_source_only tests/test_watcher.py::test_watch_dry_run_cli_outputs_fixture_harness tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 5 tests.

Safety:

- This was fixture-backed watcher proof only. It did not inspect or process configured SyncThing/private watch inputs and made no public-web search, paid enrichment, GWS, Odollo/Odoo, live lookup, live write, or live readback calls.

## Turn 122 | 2026-06-14

Continued Plan 0008 with Slice 0008-C.

Implemented:

- Added `business-card-watchdog.selected-live-target.v1`.
- Added `BusinessCardService.select_live_target_for_job`.
- Added CLI `bcw sinks select-live-target`.
- Added API `POST /jobs/{job_id}/selected-live-target`.
- Added MCP tool `business_card_watchdog_selected_live_target`.
- Registered `selected_live_target.json` for route-refresh staleness and review-bundle visibility.
- Non-simulated lookup, write, and readback pilots now require selected-target evidence matching run, job, sink, operator, and scope.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_selected_live_target_gates_non_simulated_lookup tests/test_service.py::test_service_lookup_pilot_uses_injected_read_only_executor tests/test_service.py::test_service_write_pilot_uses_injected_executor tests/test_service.py::test_service_readback_pilot_uses_injected_executor tests/test_cli_surfaces.py::test_cli_sinks_apply_decision_writes_zero_write_artifact tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 8 tests.

Safety:

- This was zero-network, zero-write approval-artifact work only. It made no live lookup, live write, live readback, public-web search, paid enrichment, GWS, or Odollo/Odoo calls.

## Turn 123 | 2026-06-14

Continued Plan 0008 with Slice 0008-D.

Implemented:

- Added `business-card-watchdog.selected-lookup-smoke.v1`.
- Added `BusinessCardService.execute_selected_lookup_smoke_for_job`.
- Added CLI `bcw sinks execute-lookup-smoke`.
- Added API `POST /jobs/{job_id}/selected-lookup-smoke`.
- Added MCP tool `business_card_watchdog_selected_lookup_smoke`.
- Registered `selected_lookup_smoke.json` for route-refresh staleness and review-bundle visibility.
- Smoke execution now consumes `selected_live_target.json`, executes the selected read-only lookup path, imports redacted lookup result evidence, and writes downstream duplicate assessment evidence.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_selected_lookup_smoke_imports_redacted_duplicate_evidence tests/test_api.py::test_api_executes_sink_lookup_pilot_with_mocked_matches tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_selected_lookup_smoke_uses_selected_target -q` passed with 4 tests.

Safety:

- This was execution-surface and injected-adapter proof only. It made no real GWS/Odollo/Odoo lookup, write, readback, public-web search, or paid enrichment calls.

## Turn 124 | 2026-06-14

Continued Plan 0008 with Slice 0008-E.

Implemented:

- Added `business-card-watchdog.service-recovery.v1`.
- Added `BusinessCardService.service_recovery_report`.
- Added CLI `bcw service recovery`.
- Added API `GET /service/recovery`.
- Added MCP tool `business_card_watchdog_service_recovery`.
- Recovery reports now compose runtime readiness, service status, watcher status, latest run state, phase/pilot readiness, deterministic next actions, blocked reasons, copy-paste install/start/status/restart/resume/recover commands, and explicit stop conditions.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_recovery_report_composes_status_and_recovery_commands tests/test_cli_surfaces.py::test_cli_service_recovery_reports_status_shape tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 5 tests.

Safety:

- This was report-only recovery guidance. It did not run `systemctl`, scan configured SyncThing inputs, process private images, execute safe next actions, run public-web search, call paid enrichment, or call GWS/Odollo/Odoo.

## Turn 125 | 2026-06-14

Started Plan 0009 with Slice 0009-A.

Implemented:

- Added `business-card-watchdog.live-target-candidates.v1`.
- Added `BusinessCardService.live_target_candidates`.
- Added CLI `bcw live-target-candidates`.
- Added API `GET /live-target-candidates`.
- Added MCP tool `business_card_watchdog_live_target_candidates`.
- Candidate reports list no-network run/job/sink target candidates, lookup readiness state, stop reasons, and selected-target commands for operator review.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_live_target_candidates_report_blocks_unready_jobs tests/test_cli_surfaces.py::test_cli_live_target_candidates_reports_text_and_json tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 5 tests.

Safety:

- This was read-only target-selection preparation. It did not create `selected_live_target.json`, process private SyncThing inputs, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.

## Turn 126 | 2026-06-14

Continued Plan 0009 with Slice 0009-A2.

Implemented:

- Added `business-card-watchdog.live-readiness-audit.v1`.
- Added `BusinessCardService.live_readiness_audit`.
- Added CLI `bcw live-readiness-audit`.
- Added API `POST /live-readiness-audit`.
- Added MCP tool `business_card_watchdog_live_readiness_audit`.
- Live readiness audits compose runtime readiness, service recovery, pilot readiness, and live target candidate evidence into one no-network run-level artifact.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_live_readiness_audit_writes_run_level_artifact tests/test_cli_surfaces.py::test_cli_live_readiness_audit_reports_text_and_json tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 5 tests.
- `.venv/bin/python -m pytest -q` passed with 206 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This was readiness evidence only. It can write `live_readiness_audit.json` under a selected run, but it did not create `selected_live_target.json`, process private SyncThing inputs, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.

## Turn 127 | 2026-06-14

Continued Plan 0009 with Slice 0009-A3.

Implemented:

- Added `business-card-watchdog.live-selection-packet.v1`.
- Added `BusinessCardService.live_selection_packet`.
- Added CLI `bcw sinks live-selection-packet`.
- Added API `POST /jobs/{job_id}/live-selection-packet`.
- Added MCP tool `business_card_watchdog_live_selection_packet`.
- Selection packets compose live readiness, target candidate state, lookup readiness, and optional apply readiness for one proposed run/job/sink/scope.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_live_selection_packet_does_not_select_target tests/test_cli_surfaces.py::test_cli_live_selection_packet_writes_no_selected_target tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 5 tests.
- `.venv/bin/python -m pytest -q` passed with 208 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This was pre-approval evidence only. It can write `live_selection_packet.json` under a selected job, but it did not create `selected_live_target.json`, process private SyncThing inputs, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.

## Turn 128 | 2026-06-14

Continued Plan 0009 with Slice 0009-A4.

Implemented:

- Added `business-card-watchdog.selected-live-target-audit.v1`.
- Added `BusinessCardService.selected_live_target_audit`.
- Added CLI `bcw sinks selected-target-audit`.
- Added API `POST /jobs/{job_id}/selected-live-target-audit`.
- Added MCP tool `business_card_watchdog_selected_live_target_audit`.
- Selected target audits read existing approval evidence, validate run/job/scope alignment, re-check lookup/apply readiness, and report matching next commands without executing them.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_selected_live_target_gates_non_simulated_lookup tests/test_service.py::test_service_live_pilot_status_does_not_double_count_closeout_totals tests/test_cli_surfaces.py::test_cli_selected_target_audit_reports_existing_approval tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 6 tests.
- `.venv/bin/python -m pytest -q` passed with 210 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This was post-approval verification only. It can write `selected_live_target_audit.json`, but it did not create or modify `selected_live_target.json`, process private SyncThing inputs, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.

## Turn 129 | 2026-06-14

Continued Plan 0009 with Slice 0009-A5.

Implemented:

- Added `business-card-watchdog.live-pilot-closeout.v1`.
- Added `BusinessCardService.build_live_pilot_closeout_for_job`.
- Added CLI `bcw sinks live-pilot-closeout`.
- Added API `POST /jobs/{job_id}/live-pilot-closeout`.
- Added MCP tool `business_card_watchdog_live_pilot_closeout`.
- Closeout reports compose selected-target approval, selected-target audit, lookup smoke evidence, downstream duplicate assessment, write/readback pilot evidence, apply-pilot report state, artifact links, stop conditions, and remediation notes.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_selected_live_target_gates_non_simulated_lookup tests/test_cli_surfaces.py::test_cli_selected_target_audit_reports_existing_approval tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 5 tests.
- `.venv/bin/python -m pytest -q` passed with 209 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This was closeout evidence only. It can write `live_pilot_closeout.json`, but it did not create or modify `selected_live_target.json`, process private SyncThing inputs, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.

## Turn 130 | 2026-06-14

Continued Plan 0009 with Slice 0009-A6.

Implemented:

- Added `business-card-watchdog.live-pilot-status.v1`.
- Added `BusinessCardService.live_pilot_status`.
- Added CLI `bcw runs live-pilot-status`.
- Added API `GET /runs/{run_id}/live-pilot-status`.
- Added MCP tool `business_card_watchdog_live_pilot_status`.
- Live pilot status aggregates candidate, pre-approval packet, selected-target, selected-target audit, lookup smoke, write/readback, and closeout state across every job in a run.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_selected_live_target_gates_non_simulated_lookup tests/test_cli_surfaces.py::test_cli_selected_target_audit_reports_existing_approval tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 5 tests.
- `.venv/bin/python -m pytest -q` passed with 209 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This was run-level readback only. It can write `live_pilot_status.json`, but it did not create or modify `selected_live_target.json`, process private SyncThing inputs, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.

## Turn 131 | 2026-06-14

Continued Plan 0009 with Slice 0009-A7.

Implemented:

- Added `business-card-watchdog.live-pilot-handoff.v1`.
- Added `BusinessCardService.live_pilot_handoff`.
- Added CLI `bcw runs live-pilot-handoff`.
- Added API `GET /runs/{run_id}/live-pilot-handoff`.
- Added MCP tool `business_card_watchdog_live_pilot_handoff`.
- Live pilot handoffs convert run-level status entries into operator-facing next actions, exact next commands, stop reasons, selected-target context, and action counts for deterministic `/goal` and subagent handoff.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_selected_live_target_gates_non_simulated_lookup tests/test_cli_surfaces.py::test_cli_selected_target_audit_reports_existing_approval tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 5 tests.
- `.venv/bin/python -m pytest -q` passed with 210 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This was handoff/readback only. It can write `live_pilot_handoff.json`, but it did not create or modify `selected_live_target.json`, process private SyncThing inputs, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.

## Turn 132 | 2026-06-14

Continued Plan 0009 with Slice 0009-A8.

Implemented:

- Added `business-card-watchdog.live-pilot-abandonment.v1`.
- Added `BusinessCardService.live_pilot_abandon_for_job`.
- Added CLI `bcw sinks abandon-live-pilot`.
- Added API `POST /jobs/{job_id}/live-pilot-abandonment`.
- Added MCP tool `business_card_watchdog_live_pilot_abandonment`.
- Live pilot status and handoff now report abandoned selected targets.
- Non-simulated selected-target gates now refuse the abandoned selected target until the operator creates a later selected target.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_live_pilot_abandonment_blocks_abandoned_selected_target tests/test_cli_surfaces.py::test_cli_selected_target_audit_reports_existing_approval tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 5 tests.
- `.venv/bin/python -m pytest -q` passed with 211 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This was abandonment/readback only. It can write `live_pilot_abandonment.json`, but it did not delete or modify `selected_live_target.json`, process private SyncThing inputs, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.

## Turn 133 | 2026-06-14

Continued Plan 0009 with Slice 0009-A9.

Implemented:

- `BusinessCardService.select_live_target_for_job` now requires tenant/profile safety confirmation.
- CLI `bcw sinks select-live-target` now requires `--safety-confirmation`.
- API `POST /jobs/{job_id}/selected-live-target` now requires `safety_confirmation`.
- MCP `business_card_watchdog_selected_live_target` now requires `safety_confirmation`.
- Selected target artifacts persist `target_safety_confirmed` and `target_safety_confirmation`.
- Selected target audits and non-simulated selected-target gates reject selected targets missing tenant/profile safety confirmation.
- Generated selection commands now include a safety-confirmation placeholder.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_selected_live_target_gates_non_simulated_lookup tests/test_service.py::test_service_live_pilot_abandonment_blocks_abandoned_selected_target tests/test_cli_surfaces.py::test_cli_selected_target_audit_reports_existing_approval tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 6 tests.
- `.venv/bin/python -m pytest -q` passed with 211 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This was approval-evidence hardening only. It did not create selected targets from generic continuation, process private SyncThing inputs, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.

## Turn 134 | 2026-06-14

Continued Plan 0009 with Slice 0009-A58.

Implemented:

- Review bundles now expose a run-level `live_pilot_handoff` command.
- Review bundle job entries now include the same handoff command beside job review commands.
- Review workbook CSV exports now include `live_pilot_handoff_command`.
- Offline review HTML now renders the handoff command through the shared command list.
- Service, API, and MCP tests protect handoff-command visibility from batch review artifacts.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_run_summary_and_review_queue tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 3 tests.
- `.venv/bin/python -m pytest -q` passed with 226 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This was command-link/readback hardening only. It did not create `selected_live_target.json`, process private SyncThing inputs, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.

## Turn 143 | 2026-06-14

Continued Plan 0009 with Slice 0009-A67.

Implemented:

- Operator dashboard now includes `live_pilot_handoff_summary` built from `live_pilot_handoff(write=False)`.
- Summary includes handoff state, action counts, operator-required count, sample operator entries, response contract, and zero-call counters.
- CLI text output now shows live handoff state and operator-required count.
- Service/API/CLI/MCP focused tests protect the no-write handoff summary.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_operator_dashboard_composes_no_live_readiness tests/test_cli_surfaces.py::test_cli_operator_dashboard_reports_no_live_summary tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 4 tests.

Safety:

- This was no-write live handoff readback only. It did not write `live_pilot_handoff.json`, create `selected_live_target.json`, execute next actions, process private SyncThing inputs, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.

## Turn 144 | 2026-06-15

Continued Plan 0009 with Slice 0009-A68.

Implemented:

- Operator dashboard text output now renders API route handoff entries.
- Operator dashboard text output now renders MCP tool names and selected-run argument templates.
- MCP arguments are rendered as compact `key=value` text instead of raw nested JSON.
- CLI tests protect readable API/MCP handoff visibility from `bcw operator-dashboard`.

Validation:

- `.venv/bin/python -m pytest tests/test_cli_surfaces.py::test_cli_operator_dashboard_reports_no_live_summary tests/test_service.py::test_service_operator_dashboard_composes_no_live_readiness tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 4 tests.
- `.venv/bin/python -m pytest -q` passed with 226 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This was presentation/readback only. It did not invoke API routes or MCP tools, execute next actions, process private SyncThing inputs, run public-web search, call paid enrichment, create `selected_live_target.json`, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.

## Turn 145 | 2026-06-15

Continued Plan 0009 with Slice 0009-A69.

Implemented:

- Live pilot handoffs now expose top-level `operator_response_templates` for operator-required next actions.
- Each template includes schema, run/job identifiers, next action, prompt, command, and copyable approval fields.
- Operator dashboard live-handoff summaries now include response-template count and first-template samples.
- Operator dashboard text now shows the response-template count at the live handoff boundary.
- Service and CLI tests cover zero-template and selected-target template cases.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_operator_dashboard_composes_no_live_readiness tests/test_service.py::test_service_selected_live_target_gates_non_simulated_lookup tests/test_cli_surfaces.py::test_cli_operator_dashboard_reports_no_live_summary tests/test_cli_surfaces.py::test_cli_selected_target_audit_reports_existing_approval tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 6 tests.
- `.venv/bin/python -m pytest -q` passed with 226 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This was no-live readback/presentation only. It did not create or modify `selected_live_target.json`, invoke API routes or MCP tools, execute next actions, process private SyncThing inputs, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.

## Turn 146 | 2026-06-15

Continued Plan 0009 with Slice 0009-A70.

Implemented:

- `bcw runs live-pilot-handoff` text output now renders a top-level response-template count.
- CLI tests protect readable response-template count visibility.
- MCP direct tool tests now assert the promoted `operator_response_templates` packet and copyable approval fields.

Validation:

- `.venv/bin/python -m pytest tests/test_cli_surfaces.py::test_cli_selected_target_audit_reports_existing_approval tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service tests/test_service.py::test_service_selected_live_target_gates_non_simulated_lookup tests/test_service.py::test_service_operator_dashboard_composes_no_live_readiness tests/test_api.py::test_api_health_status_runs_and_jobs -q` passed with 5 tests.
- `.venv/bin/python -m pytest -q` passed with 226 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This was readback/test coverage only. It did not create or modify `selected_live_target.json`, invoke API routes or MCP tools outside tests, execute next actions, process private SyncThing inputs, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.

## Turn 147 | 2026-06-15

Continued Plan 0009 with Slice 0009-A71.

Implemented:

- Added read-only operator response validation for live handoff template responses.
- The validator parses required fields, checks allowed sink/scope values, matches current live handoff templates, and returns blockers or the exact `sinks select-live-target` command.
- Added CLI `bcw runs live-pilot-validate-response <run-id> --response <response>`.
- Added API `POST /runs/{run_id}/live-pilot-operator-response-validation`.
- Added MCP tool `business_card_watchdog_live_pilot_operator_response_validation`.
- Service, CLI, API, and MCP tests cover ready validation, missing-field blockers, zero write/network counters, and no selected-target artifact creation.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_selected_live_target_gates_non_simulated_lookup tests/test_cli_surfaces.py::test_cli_selected_target_audit_reports_existing_approval tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 5 tests.
- `.venv/bin/python -m pytest -q` passed with 226 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This was validation/readback only. It did not create or modify `selected_live_target.json`, execute the returned select-target command, execute next actions, process private SyncThing inputs, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.

## Turn 148 | 2026-06-15

Continued Plan 0009 with Slice 0009-A72.

Implemented:

- Operator dashboard command maps now include the live-pilot operator response validation command.
- Operator dashboard API route maps now include `POST /runs/{run_id}/live-pilot-operator-response-validation`.
- Operator dashboard MCP tool maps now include `business_card_watchdog_live_pilot_operator_response_validation` with placeholder response arguments.
- Human-readable dashboard output now renders the validation command, API route, and MCP tool entry.
- Service, CLI, API, and MCP tests protect dashboard validator discovery.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_operator_dashboard_composes_no_live_readiness tests/test_cli_surfaces.py::test_cli_operator_dashboard_reports_no_live_summary tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 4 tests.
- `.venv/bin/python -m pytest -q` passed with 226 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This was no-live metadata/readback only. It did not run validation, execute the returned select-target command, create or modify `selected_live_target.json`, execute next actions, process private SyncThing inputs, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.

## Turn 149 | 2026-06-15

Continued Plan 0009 with Slice 0009-A73.

Implemented:

- README live-pilot quick-start now inserts `runs live-pilot-validate-response` between handoff review and selected-target creation.
- The live-pilot checklist now includes response validation for lookup-only and all-scope pilot flows.
- Docs now state that response validation is read-only and only returns blockers or the exact select-target command.

Validation:

- `rg -n 'live-pilot-validate-response|validation is read-only|selected_live_target\.json' README.md docs/operations/live-pilot-checklists.md` passed.
- `.venv/bin/python -m pytest tests/test_cli_surfaces.py::test_cli_selected_target_audit_reports_existing_approval tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 3 tests.
- `.venv/bin/python -m pytest -q` passed with 226 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This was documentation only. It did not run validation, execute the returned select-target command, create or modify `selected_live_target.json`, execute next actions, process private SyncThing inputs, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.

## Turn 150 | 2026-06-15

Continued Plan 0009 with Slice 0009-A74.

Implemented:

- MCP JSONL server regression coverage now calls `business_card_watchdog_live_pilot_operator_response_validation`.
- The JSONL test prepares a fixture-only selected target, sends the filled operator response over JSON-RPC, and asserts ready validation, matching template, zero write/network counters, and no selected-target creation by validation.

Validation:

- `.venv/bin/python -m pytest tests/test_mcp.py::test_mcp_jsonl_server_lists_and_calls_tools tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_service.py::test_service_selected_live_target_gates_non_simulated_lookup -q` passed with 4 tests.
- `.venv/bin/python -m pytest -q` passed with 226 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This was transport test coverage only. It used fixture data and did not process private SyncThing inputs, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.

## Turn 151 | 2026-06-15

Continued Plan 0009 with Slice 0009-A75.

Implemented:

- Operator response validation now rejects concrete operator/scope values that conflict with the current handoff template.
- Service tests cover a wrong-scope response that remains blocked and does not return a select-target command.
- CLI tests cover a wrong-operator response in readable text output without raw JSON.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_selected_live_target_gates_non_simulated_lookup tests/test_cli_surfaces.py::test_cli_selected_target_audit_reports_existing_approval tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service tests/test_mcp.py::test_mcp_jsonl_server_lists_and_calls_tools -q` passed with 5 tests.
- `.venv/bin/python -m pytest -q` passed with 226 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This was validation hardening only. It did not create or modify `selected_live_target.json`, execute the returned select-target command, process private SyncThing inputs, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.

## Turn 142 | 2026-06-14

Continued Plan 0009 with Slice 0009-A66.

Implemented:

- Operator dashboard now includes `mcp_tools` for dashboard refresh, next-action readback, safe run-next, live pilot status, and live pilot handoff.
- MCP tool metadata uses concrete tool names plus selected-run argument templates when a run is selected.
- MCP dashboard tool description now advertises CLI/API/MCP handoff commands.
- README now notes that operator dashboard includes CLI commands, API routes, and MCP tool argument templates.
- Service/API/MCP focused tests protect the MCP handoff metadata.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_operator_dashboard_composes_no_live_readiness tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service tests/test_mcp.py::test_mcp_jsonl_server_lists_and_calls_tools -q` passed with 4 tests.

Safety:

- This was metadata readback only. It did not invoke MCP tools, execute next actions, process private SyncThing inputs, run public-web search, call paid enrichment, create `selected_live_target.json`, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.

## Turn 141 | 2026-06-14

Continued Plan 0009 with Slice 0009-A65.

Implemented:

- Added read-only API `GET /actions/next`.
- Added read-only API `POST /actions/next`.
- Operator dashboard now includes `api_routes` for dashboard, next-action readback, safe run-next, live status, and live handoff surfaces.
- README now calls out read-only API inspection routes.
- Service/API focused tests protect the new API route hints and next-action endpoint behavior.

Validation:

- `.venv/bin/python -m pytest tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_service.py::test_service_operator_dashboard_composes_no_live_readiness tests/test_cli_surfaces.py::test_cli_operator_dashboard_reports_no_live_summary tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 4 tests.

Safety:

- This was API readback only. It did not execute next actions, process private SyncThing inputs, run public-web search, call paid enrichment, create `selected_live_target.json`, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.

## Turn 140 | 2026-06-14

Continued Plan 0009 with Slice 0009-A64.

Implemented:

- Operator dashboard now includes `next_action_summary` with total, safe-auto, explicit-operator, action-group, and sample-action readback.
- Dashboard command map now links to read-only next-action inspection and the bounded safe executor.
- Added CLI `bcw actions next` for read-only next-action inspection.
- CLI/API/MCP/service tests protect dashboard next-action summary and command hints.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_operator_dashboard_composes_no_live_readiness tests/test_cli_surfaces.py::test_cli_operator_dashboard_reports_no_live_summary tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 4 tests.

Safety:

- This was next-action readback only. It did not execute next actions from the dashboard, process private SyncThing inputs, run public-web search, call paid enrichment, create `selected_live_target.json`, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.

## Turn 139 | 2026-06-14

Continued Plan 0009 with Slice 0009-A63.

Implemented:

- Added `business-card-watchdog.operator-dashboard.v1`.
- Added service `BusinessCardService.operator_dashboard`.
- Added CLI `bcw operator-dashboard [--run-id]`.
- Added API `GET /operator/dashboard`.
- Added MCP tool `business_card_watchdog_operator_dashboard`.
- The dashboard composes top-level status, runtime readiness, service recovery, recent runs, selected run summary, phase dashboard summary, review counts, and no-write live pilot status into one operator readback.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_operator_dashboard_composes_no_live_readiness tests/test_cli_surfaces.py::test_cli_operator_dashboard_reports_no_live_summary tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service tests/test_mcp.py::test_mcp_jsonl_server_lists_and_calls_tools -q` passed with 5 tests.

Safety:

- This was no-live operator readback only. It did not process private SyncThing inputs, run public-web search, call paid enrichment, create `selected_live_target.json`, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.

## Turn 138 | 2026-06-14

Continued Plan 0009 with Slice 0009-A62.

Implemented:

- Default `bcw status` output now renders a readable operator summary instead of a raw Python dict.
- The text summary lists config/data/cache paths, skill state, watcher counts, zero write/network counters, safe command links, safe next actions, and stop conditions.
- CLI tests protect both JSON and text status command-map behavior.

Validation:

- `.venv/bin/python -m pytest tests/test_cli_surfaces.py::test_cli_status_reports_command_map_text_and_json tests/test_service.py::test_service_status_and_sink_readiness_are_structured tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service tests/test_mcp.py::test_mcp_jsonl_server_lists_and_calls_tools -q` passed with 5 tests.

Safety:

- This was status presentation hardening only. It did not process private SyncThing inputs, run public-web search, call paid enrichment, create `selected_live_target.json`, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.

## Turn 137 | 2026-06-14

Continued Plan 0009 with Slice 0009-A61.

Implemented:

- Top-level status now has schema `business-card-watchdog.status.v1`.
- Status reports now expose zero-call commands for runtime readiness, service recovery, watch status, watch dry-run, run listing, and MCP manifest inspection.
- Status reports now include safe next actions, explicit stop conditions, and zero write/network counters.
- Service, API, direct MCP, and MCP JSON-RPC tests protect the status command map.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_status_and_sink_readiness_are_structured tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service tests/test_mcp.py::test_mcp_jsonl_server_lists_and_calls_tools -q` passed with 4 tests.

Safety:

- This was status readback and command-link hardening only. It did not process private SyncThing inputs, run public-web search, call paid enrichment, create `selected_live_target.json`, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.

## Turn 136 | 2026-06-14

Continued Plan 0009 with Slice 0009-A60.

Implemented:

- Live pilot status reports now expose a run-level `live_pilot_handoff` command.
- CLI text for `runs live-pilot-status` now renders the handoff command.
- Service, CLI, API, and MCP tests protect handoff-command visibility from live status reports.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_selected_live_target_gates_non_simulated_lookup tests/test_cli_surfaces.py::test_cli_selected_target_audit_reports_existing_approval tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 4 tests.
- `.venv/bin/python -m pytest -q` passed with 226 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This was command-link/readback hardening only. It did not create `selected_live_target.json`, process private SyncThing inputs, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.

## Turn 135 | 2026-06-14

Continued Plan 0009 with Slice 0009-A59.

Implemented:

- Phase reports now expose run-level commands for report refresh, pilot readiness, review bundle, review workbook, safe next actions, and live pilot handoff.
- Pilot-readiness reports now expose the same run-level commands.
- CLI text for phase reports and pilot-readiness reports now renders the live pilot handoff command.
- Service, CLI, API, and MCP tests protect handoff-command visibility from run-level progress reports.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_run_summary_and_review_queue tests/test_cli_surfaces.py::test_cli_runs_and_jobs_use_recorded_runtime_state tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 4 tests.

Safety:

- This was command-link/readback hardening only. It did not create `selected_live_target.json`, process private SyncThing inputs, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.

## Turn 152 | 2026-06-15

Continued Plan 0009 with Slice 0009-A76.

Implemented:

- Live pilot handoffs now expose `commands.validate_operator_response`.
- CLI text for `runs live-pilot-handoff` now renders the validation command directly.
- Service, CLI, API, and MCP tests protect validation-command visibility from the handoff packet.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_selected_live_target_gates_non_simulated_lookup tests/test_cli_surfaces.py::test_cli_selected_target_audit_reports_existing_approval tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 4 tests.
- `.venv/bin/python -m pytest -q` passed with 226 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This was no-live handoff/readback hardening only. It did not validate an operator response, execute any returned select-target command, create or modify `selected_live_target.json`, process private SyncThing inputs, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.

## Turn 153 | 2026-06-15

Continued Plan 0009 with Slice 0009-A77.

Implemented:

- Live pilot status reports now expose `commands.validate_operator_response`.
- CLI text for `runs live-pilot-status` now renders the validation command directly.
- Service, CLI, API, and MCP tests protect validation-command visibility from the status packet.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_selected_live_target_gates_non_simulated_lookup tests/test_cli_surfaces.py::test_cli_selected_target_audit_reports_existing_approval tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 4 tests.
- `.venv/bin/python -m pytest -q` passed with 226 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This was no-live status/readback hardening only. It did not validate an operator response, execute any returned select-target command, create or modify `selected_live_target.json`, process private SyncThing inputs, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.

## Turn 154 | 2026-06-15

Continued Plan 0009 with Slice 0009-A78.

Implemented:

- Live pilot status entries now expose `commands.validate_operator_response`.
- Promoted `operator_response_templates` now include `validation_command` next to the current next-action command.
- Service, CLI, API, and MCP tests protect per-job validation-command visibility for batch handoffs.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_selected_live_target_gates_non_simulated_lookup tests/test_cli_surfaces.py::test_cli_selected_target_audit_reports_existing_approval tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 4 tests.
- `.venv/bin/python -m pytest -q` passed with 226 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This was no-live per-job handoff/readback hardening only. It did not validate an operator response, execute any returned select-target command, create or modify `selected_live_target.json`, process private SyncThing inputs, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.

## Turn 155 | 2026-06-15

Continued Plan 0009 with Slice 0009-A79.

Implemented:

- Review bundles now expose run-level and per-entry `validate_operator_response` commands.
- Review workbook CSV exports now include `validate_operator_response_command`.
- Service, API, and MCP tests protect validation-command visibility in review bundles and exported workbooks.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_run_summary_and_review_queue tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 3 tests.

Safety:

- This was no-live review/export command-surface hardening only. It did not validate an operator response, execute any returned select-target command, create or modify `selected_live_target.json`, process private SyncThing inputs, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.

## Turn 156 | 2026-06-15

Continued Plan 0009 with Slice 0009-A80.

Implemented:

- Live selection requirements now expose run-level and per-entry `validate_operator_response` commands.
- Service, CLI, API, and MCP tests protect validation-command visibility from the selection-requirements packet.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_live_selection_requirements_report_writes_run_level_artifact tests/test_cli_surfaces.py::test_cli_live_selection_requirements_reports_text_and_json tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 4 tests.
- `.venv/bin/python -m pytest -q` passed with 226 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This was no-live selection-requirements command-surface hardening only. It did not validate an operator response, execute any returned select-target command, create or modify `selected_live_target.json`, process private SyncThing inputs, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.

## Turn 157 | 2026-06-15

Continued Plan 0009 with Slice 0009-A81.

Implemented:

- Live target candidate reports now expose run-level and per-candidate `validate_operator_response` commands.
- Live readiness audits now expose the same run-level validation command.
- CLI text for target candidates and readiness audits now renders the validation command.
- Service, CLI, API, and MCP tests protect validation-command visibility from candidate and readiness reports.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_live_target_candidates_report_blocks_unready_jobs tests/test_service.py::test_service_live_readiness_audit_writes_run_level_artifact tests/test_cli_surfaces.py::test_cli_live_target_candidates_reports_text_and_json tests/test_cli_surfaces.py::test_cli_live_readiness_audit_reports_text_and_json tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 6 tests.
- `.venv/bin/python -m pytest -q` passed with 226 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This was no-live candidate/readiness command-surface hardening only. It did not validate an operator response, execute any returned select-target command, create or modify `selected_live_target.json`, process private SyncThing inputs, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.

## Turn 158 | 2026-06-15

Continued Plan 0009 with Slice 0009-A82.

Implemented:

- Live selection packets now expose `commands.validate_operator_response`.
- CLI text for `sinks live-selection-packet` now renders the validation command before the create-selected-target command.
- Service, CLI, API, and MCP tests protect validation-command visibility from selection packets.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_live_selection_packet_does_not_select_target tests/test_cli_surfaces.py::test_cli_live_selection_packet_writes_no_selected_target tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 4 tests.
- `.venv/bin/python -m pytest -q` passed with 226 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This was no-live selection-packet command-surface hardening only. It did not validate an operator response, execute any returned select-target command, create or modify `selected_live_target.json`, process private SyncThing inputs, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.

## Turn 159 | 2026-06-15

Continued Plan 0009 with Slice 0009-A83.

Implemented:

- Live selection packets now include `operator_response_template`, `operator_prompt`, and `copyable_approval_fields`.
- CLI text for `sinks live-selection-packet` now renders the operator response template.
- Service, CLI, API, and MCP tests protect self-contained operator response metadata from selection packets.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_live_selection_packet_does_not_select_target tests/test_cli_surfaces.py::test_cli_live_selection_packet_writes_no_selected_target tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 4 tests.
- `.venv/bin/python -m pytest -q` passed with 226 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This was no-live selection-packet metadata hardening only. It did not validate an operator response, execute any returned select-target command, create or modify `selected_live_target.json`, process private SyncThing inputs, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.

## Turn 160 | 2026-06-15

Continued Plan 0009 with Slice 0009-A84.

Implemented:

- Live selection packets now expose `commands.validate_operator_response_prefilled` with the packet's operator response template already quoted into the read-only validation command.
- CLI text for `sinks live-selection-packet` now renders the prefilled validation command.
- Service, CLI, API, and MCP tests protect the prefilled command on selection-packet surfaces.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_live_selection_packet_does_not_select_target tests/test_cli_surfaces.py::test_cli_live_selection_packet_writes_no_selected_target tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 4 tests.
- `.venv/bin/python -m pytest -q` passed with 226 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This was no-live selection-packet command-surface hardening only. It did not validate an operator response, execute any returned select-target command, create or modify `selected_live_target.json`, process private SyncThing inputs, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.

## Turn 161 | 2026-06-15

Continued Plan 0009 with Slice 0009-A85.

Implemented:

- README live-pilot quick-start now tells operators to run the selection packet's printed `Validate prefilled response:` command before filling the tenant/profile confirmation.
- The live-pilot checklist now gives the same prefilled-validation guidance for lookup-only and all-scope selected-target approval flows.
- The docs preserve the manual `runs live-pilot-validate-response` command for the filled confirmation and keep validation explicitly read-only.

Validation:

- `rg -n 'Validate prefilled response|validation is read-only|selected_live_target\.json|live-pilot-validate-response' README.md docs/operations/live-pilot-checklists.md` passed.
- `.venv/bin/python -m pytest -q` passed with 226 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This was documentation only. It did not run validation, execute any returned select-target command, create or modify `selected_live_target.json`, process private SyncThing inputs, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.

## Turn 162 | 2026-06-15

Continued Plan 0009 with Slice 0009-A86.

Implemented:

- Live pilot status entries now include `commands.validate_operator_response_prefilled` using the same quoting helper as selection packets.
- Live pilot handoff `operator_response_templates` now promote that value as `validation_command_prefilled`.
- Service, CLI, API, and MCP tests protect the promoted prefilled validation command on handoff/status surfaces.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_selected_live_target_gates_non_simulated_lookup tests/test_cli_surfaces.py::test_cli_selected_target_audit_reports_existing_approval tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 4 tests.
- `.venv/bin/python -m pytest -q` passed with 226 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This was no-live handoff/readback command-surface hardening only. It did not validate an operator response, execute any returned select-target command, create or modify `selected_live_target.json`, process private SyncThing inputs, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.

## Turn 163 | 2026-06-15

Continued Plan 0009 with Slice 0009-A87.

Implemented:

- Live selection requirement entries now include `commands.validate_operator_response_prefilled`.
- CLI text for `live-selection-requirements` now renders the entry-level prefilled validation command next to the operator response template.
- Service, CLI, and MCP tests protect the prefilled command on populated selection-requirements entries.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_live_selection_requirements_report_writes_run_level_artifact tests/test_cli_surfaces.py::test_cli_live_selection_requirements_reports_text_and_json tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 3 tests.
- `.venv/bin/python -m pytest -q` passed with 226 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This was no-live selection-requirements command-surface hardening only. It did not validate an operator response, execute any returned select-target command, create or modify `selected_live_target.json`, process private SyncThing inputs, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.

## Turn 164 | 2026-06-15

Continued Plan 0009 with Slice 0009-A88.

Implemented:

- Selected target creation now rejects terse safety confirmations that do not describe the intended tenant/profile/account context.
- Read-only operator-response validation now blocks weak safety confirmations before returning a select-target command.
- Service tests protect both direct selection and validation blockers.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_selected_live_target_gates_non_simulated_lookup -q` passed with 1 test.
- `.venv/bin/python -m pytest -q` passed with 226 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This was no-live approval hardening only. It did not validate a real operator response, execute any returned select-target command, create or modify `selected_live_target.json`, process private SyncThing inputs, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.

## Turn 165 | 2026-06-15

Continued Plan 0009 with Slice 0009-A89.

Implemented:

- Operator-facing live-target approval templates now use `safety_confirmation=<tenant-profile-account-confirmation>` instead of the generic `<confirmation>` placeholder.
- Selected target creation now rejects placeholder-shaped safety confirmations even when the placeholder contains tenant/profile/account words.
- README and live-pilot checklist examples now tell operators to replace the tenant/profile/account placeholder before validation or selection.
- Service, CLI, API, and MCP tests protect the updated placeholder across selection requirements, selection packets, status, handoff, and response validation.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_live_selection_requirements_report_writes_run_level_artifact tests/test_service.py::test_service_live_selection_packet_does_not_select_target tests/test_service.py::test_service_selected_live_target_gates_non_simulated_lookup -q` passed with 3 tests.
- `.venv/bin/python -m pytest tests/test_cli_surfaces.py::test_cli_live_target_candidates_reports_text_and_json tests/test_cli_surfaces.py::test_cli_live_selection_requirements_reports_text_and_json tests/test_cli_surfaces.py::test_cli_live_selection_packet_writes_no_selected_target tests/test_cli_surfaces.py::test_cli_selected_target_audit_reports_existing_approval tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 6 tests.
- `rg -n 'safety_confirmation=<confirmation>|--safety-confirmation <confirmation>|"safety_confirmation": "<confirmation>"' .` found no matches.
- `.venv/bin/python -m pytest -q` passed with 226 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This was no-live approval-template hardening only. It did not validate a real operator response, execute any returned select-target command, create or modify `selected_live_target.json`, process private SyncThing inputs, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.

## Turn 166 | 2026-06-15

Continued Plan 0009 with Slice 0009-A90.

Implemented:

- Reordered the Runbook Plan 0009 tail so Turns 157-165 appear in numeric execution order.
- Preserved the existing Turn 164 and Turn 165 evidence text while moving it after Turn 163.
- Added this repair note as a no-live documentation/evidence-integrity slice.

Validation:

- `rg -n '## Turn 15[0-9]|## Turn 16[0-9]' RUNBOOK.md` passed and shows Turn 150 through Turn 166 in order.
- `.venv/bin/python -m pytest -q` passed with 226 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This was documentation/evidence ordering only. It did not validate an operator response, execute any returned select-target command, create or modify `selected_live_target.json`, process private SyncThing inputs, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.

## Turn 167 | 2026-06-15

Continued Plan 0009 with Slice 0009-A91.

Implemented:

- Plain-text `runs live-pilot-handoff --no-write` output now renders each entry's prefilled operator-response validation command.
- The handoff text surface now matches the JSON handoff, selection-packet, and selection-requirements surfaces for agent-loop copy/paste validation.
- CLI tests protect the prefilled validation command in the text handoff output.

Validation:

- `.venv/bin/python -m pytest tests/test_cli_surfaces.py::test_cli_selected_target_audit_reports_existing_approval -q` passed with 1 test.
- `.venv/bin/python -m pytest tests/test_service.py::test_service_selected_live_target_gates_non_simulated_lookup tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 3 tests.
- `.venv/bin/python -m pytest -q` passed with 226 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This was no-live CLI text hardening only. It did not validate an operator response, execute any returned select-target command, create or modify `selected_live_target.json`, process private SyncThing inputs, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.

## Turn 168 | 2026-06-15

Continued Plan 0009 with Slice 0009-A92.

Implemented:

- Operator dashboard live handoff entries now include `validation_command` and `validation_command_prefilled`.
- Plain-text `operator-dashboard --run-id <run-id>` output now renders live handoff operator entries with the prefilled validation command.
- CLI and MCP tests protect dashboard visibility for the prefilled validation command.

Validation:

- `.venv/bin/python -m pytest tests/test_cli_surfaces.py::test_cli_live_target_candidates_reports_text_and_json tests/test_cli_surfaces.py::test_cli_operator_dashboard_reports_no_live_summary -q` passed with 2 tests.
- `.venv/bin/python -m pytest tests/test_service.py::test_service_operator_dashboard_composes_no_live_readiness tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 3 tests.
- `.venv/bin/python -m pytest -q` passed with 226 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This was no-live dashboard handoff hardening only. It did not validate an operator response, execute any returned select-target command, create or modify `selected_live_target.json`, process private SyncThing inputs, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.

## Turn 169 | 2026-06-15

Continued Plan 0009 with Slice 0009-A93.

Implemented:

- Ready operator-response validation reports now include `selected_target_audit_command`.
- The command is also exposed as `commands.selected_target_audit`.
- Plain-text validation output now renders the selected-target audit command after the select-target command.
- Blocked validations keep both selected-target and audit commands null.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_selected_live_target_gates_non_simulated_lookup tests/test_cli_surfaces.py::test_cli_selected_target_audit_reports_existing_approval -q` passed with 2 tests.
- `.venv/bin/python -m pytest tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_mcp_jsonl_server_lists_and_calls_tools -q` passed with 2 tests.
- `.venv/bin/python -m pytest -q` passed with 226 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This was no-live validation handoff hardening only. It did not validate a real operator response, execute any returned select-target command, execute selected-target audit, create or modify `selected_live_target.json`, process private SyncThing inputs, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.

## Turn 170 | 2026-06-15

Continued Plan 0009 with Slice 0009-A94.

Implemented:

- Ready operator-response validation reports now include `lookup_smoke_handoff_command`.
- The command is also exposed as `commands.lookup_smoke_handoff`.
- Plain-text validation output now renders the lookup-smoke handoff command after the selected-target audit command.
- Blocked validations keep select-target, audit, and lookup-smoke handoff commands null.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_selected_live_target_gates_non_simulated_lookup tests/test_cli_surfaces.py::test_cli_selected_target_audit_reports_existing_approval -q` passed with 2 tests.
- `.venv/bin/python -m pytest tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_mcp_jsonl_server_lists_and_calls_tools -q` passed with 2 tests after correcting the fixture operator to `mcp-jsonl`.
- `.venv/bin/python -m pytest -q` passed with 226 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This was no-live validation handoff hardening only. It did not validate a real operator response, execute any returned select-target command, execute selected-target audit, build lookup-smoke handoff, create or modify `selected_live_target.json`, process private SyncThing inputs, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.

## Turn 171 | 2026-06-15

Continued Plan 0009 with Slice 0009-A95.

Implemented:

- Ready operator-response validation reports now include `post_selection_sequence`.
- The sequence orders `select_target`, `selected_target_audit`, and `lookup_smoke_handoff`.
- Each sequence step reports the command plus no-live metadata for runtime-artifact writes, sink writes, network calls, and stop conditions.
- Plain-text validation output now renders the post-selection sequence after the individual handoff commands.
- Blocked validations keep the post-selection sequence empty.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_selected_live_target_gates_non_simulated_lookup tests/test_cli_surfaces.py::test_cli_selected_target_audit_reports_existing_approval tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_mcp_jsonl_server_lists_and_calls_tools -q` passed with 4 tests.
- `.venv/bin/python -m pytest -q` passed with 226 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This was no-live validation handoff hardening only. It did not validate a real operator response, execute any returned select-target command, execute selected-target audit, build lookup-smoke handoff, create or modify `selected_live_target.json`, process private SyncThing inputs, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.

## Turn 172 | 2026-06-15

Continued Plan 0009 with Slice 0009-A96.

Implemented:

- Operator-response validation now detects handoff templates whose next action is `request_live_lookup_smoke`.
- Active selected-target validation now reports `ready_for_live_lookup_request` instead of `ready_to_select_live_target`.
- Active selected-target validation no longer returns a second `select_target_command`.
- The active-target `post_selection_sequence` starts at selected-target audit and lookup-smoke handoff.
- Preselection validation still returns the select-target sequence.
- README and live-pilot checklist text now describe the state-aware validation behavior.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_selected_live_target_gates_non_simulated_lookup tests/test_cli_surfaces.py::test_cli_selected_target_audit_reports_existing_approval tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service tests/test_mcp.py::test_mcp_jsonl_server_lists_and_calls_tools -q` passed with 5 tests.
- `.venv/bin/python -m pytest -q` passed with 226 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This was no-live validation handoff hardening only. It did not validate a real operator response, execute any returned select-target command, execute selected-target audit, build lookup-smoke handoff, create or modify `selected_live_target.json`, process private SyncThing inputs, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.

## Turn 173 | 2026-06-15

Continued Plan 0009 with Slice 0009-A97.

Implemented:

- Operator-response validation now includes `next_validation_step`.
- Plain-text validation output now renders the next validation step.
- Validation stop conditions are now state-aware for blocked, preselection, active selected-target, and selected-target-audit review states.
- Active selected-target validation explicitly warns not to run `select_target` again and to review selected-target audit plus lookup-smoke handoff before any live lookup request.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_selected_live_target_gates_non_simulated_lookup tests/test_cli_surfaces.py::test_cli_selected_target_audit_reports_existing_approval tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service tests/test_mcp.py::test_mcp_jsonl_server_lists_and_calls_tools -q` passed with 5 tests.
- `.venv/bin/python -m pytest -q` passed with 226 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This was no-live validation guidance hardening only. It did not validate a real operator response, execute any returned select-target command, execute selected-target audit, build lookup-smoke handoff, create or modify `selected_live_target.json`, process private SyncThing inputs, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.

## Turn 174 | 2026-06-15

Continued Plan 0009 with Slice 0009-A98.

Implemented:

- Plain-text operator-response validation output now renders stop-condition count and stop-condition lines.
- Active selected-target validation text now shows the no-reselection warning and selected-target audit plus lookup-smoke handoff review boundary without requiring `--json`.

Validation:

- `.venv/bin/python -m pytest tests/test_cli_surfaces.py::test_cli_selected_target_audit_reports_existing_approval tests/test_service.py::test_service_selected_live_target_gates_non_simulated_lookup tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service tests/test_mcp.py::test_mcp_jsonl_server_lists_and_calls_tools -q` passed with 5 tests.
- `.venv/bin/python -m pytest -q` passed with 226 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This was no-live CLI presentation hardening only. It did not validate a real operator response, execute any returned select-target command, execute selected-target audit, build lookup-smoke handoff, create or modify `selected_live_target.json`, process private SyncThing inputs, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.

## Turn 175 | 2026-06-15

Continued Plan 0009 with Slice 0009-A99.

Implemented:

- Plain-text `runs live-pilot-handoff` output now renders operator stop-condition count and stop-condition lines.
- Active selected-target handoff text now shows tenant/profile, selected-target creation, live command, private input, public-web, and paid-enrichment boundaries without requiring `--json`.

Validation:

- `.venv/bin/python -m pytest tests/test_cli_surfaces.py::test_cli_selected_target_audit_reports_existing_approval -q` passed with 1 test.
- `.venv/bin/python -m pytest -q` passed with 226 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This was no-live CLI presentation hardening only. It did not validate a real operator response, execute any returned select-target command, execute selected-target audit, build lookup-smoke handoff, create or modify `selected_live_target.json`, process private SyncThing inputs, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.

## Turn 176 | 2026-06-15

Continued Plan 0009 with Slice 0009-A100.

Implemented:

- Plain-text `runs live-pilot-status` output now renders stop-condition count and stop-condition lines.
- Active selected-target status text now shows the selected-target, live command, private input, public-web, and paid-enrichment boundaries without requiring `--json`.

Validation:

- `.venv/bin/python -m pytest tests/test_cli_surfaces.py::test_cli_selected_target_audit_reports_existing_approval -q` passed with 1 test.
- `.venv/bin/python -m pytest -q` passed with 226 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This was no-live CLI presentation hardening only. It did not validate a real operator response, execute any returned select-target command, execute selected-target audit, build lookup-smoke handoff, create or modify `selected_live_target.json`, process private SyncThing inputs, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.

## Turn 177 | 2026-06-15

Continued Plan 0009 with Slice 0009-A101.

Implemented:

- Operator dashboard live-pilot summary now includes the underlying `runs live-pilot-status` explicit stop conditions.
- Operator dashboard live-handoff summary now includes the underlying `runs live-pilot-handoff` operator stop conditions.
- Plain-text `operator-dashboard` output now renders live-pilot and live-handoff stop-condition counts and lines.
- API, CLI, and MCP coverage now assert those dashboard stop-condition fields and rendered lines.

Validation:

- `.venv/bin/python -m pytest tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_cli_surfaces.py::test_cli_operator_dashboard_reports_no_live_summary tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 3 tests.
- `.venv/bin/python -m pytest -q` passed with 226 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This was no-live dashboard presentation hardening only. It did not validate a real operator response, execute any returned select-target command, execute selected-target audit, build lookup-smoke handoff, create or modify `selected_live_target.json`, process private SyncThing inputs, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.

## Turn 178 | 2026-06-15

Continued Plan 0009 with Slice 0009-A102.

Implemented:

- Operator dashboard `safe_next_actions` now includes no-write `inspect_live_pilot_status`.
- Operator dashboard `safe_next_actions` now includes no-write `inspect_live_pilot_handoff`.
- Service, API, CLI, and MCP coverage now assert those dashboard safe actions and commands.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_operator_dashboard_composes_no_live_readiness tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_cli_surfaces.py::test_cli_operator_dashboard_reports_no_live_summary tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 4 tests.
- `.venv/bin/python -m pytest -q` passed with 226 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This was no-live dashboard orchestration guidance only. It did not validate a real operator response, execute any returned select-target command, execute selected-target audit, build lookup-smoke handoff, create or modify `selected_live_target.json`, process private SyncThing inputs, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.

## Turn 179 | 2026-06-15

Continued Plan 0009 with Slice 0009-A103.

Implemented:

- Service recovery reports now expose a no-write `live_pilot_status` command.
- Service recovery `safe_next_actions` now include no-write `inspect_live_pilot_status` and `inspect_live_pilot_handoff`.
- Plain-text `service recovery` output now renders safe-action rows, including the live-pilot inspection commands.
- Service, API, CLI, and MCP coverage now assert the recovery live safe actions and commands.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_recovery_report_composes_status_and_recovery_commands tests/test_cli_surfaces.py::test_cli_service_recovery_reports_status_shape tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 4 tests.
- `.venv/bin/python -m pytest -q` passed with 226 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This was no-live recovery orchestration guidance only. It did not validate a real operator response, execute any returned select-target command, execute selected-target audit, build lookup-smoke handoff, create or modify `selected_live_target.json`, process private SyncThing inputs, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.

## Turn 180 | 2026-06-15

Continued Plan 0009 with Slice 0009-A104.

Implemented:

- `run_next_actions` now returns `safe_inspection_commands` for no-write live-pilot status, no-write live-pilot handoff, operator dashboard, and service recovery readback.
- Service, API, CLI, and MCP JSON surfaces now assert those commands.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_run_next_actions_executes_safe_steps_until_manual_decision tests/test_cli_surfaces.py::test_cli_jobs_review_records_submission tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 4 tests.
- `.venv/bin/python -m pytest -q` passed with 226 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This was no-live deterministic continuation readback only. It did not execute the inspection commands, validate a real operator response, execute any returned select-target command, execute selected-target audit, build lookup-smoke handoff, create or modify `selected_live_target.json`, process private SyncThing inputs, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.

## Turn 181 | 2026-06-15

Continued Plan 0009 with Slice 0009-A105.

Implemented:

- `watch-dry-run` harness ids now include a UUID suffix so repeated harness runs in the same second do not collide in cache state.
- `watch-dry-run` now includes command links for watch status, harness rerun, status, and service recovery.
- Plain-text `watch-status` and `watch-dry-run` now render operator-readable summaries instead of Python dicts.
- Watch/API/MCP coverage now asserts fixture-only private-source boundaries, safe actions, stop conditions, and command metadata.

Validation:

- `.venv/bin/python -m pytest tests/test_watcher.py::test_watch_status_cli_outputs_json tests/test_watcher.py::test_watch_dry_run_cli_outputs_fixture_harness tests/test_api.py::test_api_enrichment_request_accepts_paid_provider_results tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 4 tests.
- `.venv/bin/python -m pytest -q` passed with 226 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This was fixture-backed watch harness and presentation hardening only. It did not process configured/private SyncThing inputs, run public-web search, call paid enrichment, validate a real operator response, create or modify `selected_live_target.json`, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.

## Turn 182 | 2026-06-15

Continued Plan 0009 with Slice 0009-A106.

Implemented:

- `watch-reset --yes` now returns `business-card-watchdog.watch-reset.v1` with reset files, command links, zero write/network counters, and private-source status.
- Watch reset output now includes explicit stop conditions that distinguish resetting watcher state from processing configured/private watch inputs.
- Service and CLI coverage now assert the structured reset artifact and guard behavior.

Validation:

- `.venv/bin/python -m pytest tests/test_watcher.py::test_watch_reset_cli_requires_yes tests/test_service.py::test_service_watch_reset_returns_runtime_path -q` passed with 2 tests.
- `.venv/bin/python -m pytest -q` passed with 226 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This was watched-folder state reset readback only. It did not process configured/private SyncThing inputs, run public-web search, call paid enrichment, validate a real operator response, create or modify `selected_live_target.json`, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.

## Turn 183 | 2026-06-15

Continued Plan 0009 with Slice 0009-A107.

Implemented:

- Added `business-card-watchdog.review-routing-drill.v1` to create an isolated synthetic run that exercises review approval, review bundle/workbook export, downstream duplicate lookup planning, dry-run sink planning, and apply preflight.
- Added CLI `bcw drills review-routing`, API `POST /drills/review-routing`, and MCP tool `business_card_watchdog_review_routing_drill`.
- The drill uses a fixture sink overlay for `google_contacts` and `odoo` routing while preserving the operator's real user config and stopping at `decide_sink_apply`.
- Service, CLI, API, and MCP coverage now assert the fixture-only boundary, skipped manual apply decision, zero network/write counters, and drill artifact creation.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_review_routing_drill_exercises_safe_fixture_route tests/test_cli_surfaces.py::test_cli_review_routing_drill_outputs_fixture_artifact tests/test_api.py::test_api_review_routing_drill_outputs_fixture_artifact tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 5 tests.
- `.venv/bin/python -m pytest -q` passed with 229 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This was synthetic review/export/routing drill execution only. It did not process configured/private SyncThing inputs, run public-web search, call paid enrichment, validate a real operator response, create or modify `selected_live_target.json`, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.

## Turn 184 | 2026-06-15

Continued Plan 0009 with Slice 0009-A108.

Implemented:

- Added operator-readable text output for `bcw drills review-routing`.
- The text readback summarizes run/job IDs, fixture sink context, review transition, zero write/network counters, route artifacts, safe executed actions, skipped manual actions, next commands, and stop conditions.
- Added README front-door documentation for the review/routing drill command and its no-live boundary.
- CLI coverage now asserts both JSON and text drill output.

Validation:

- `.venv/bin/python -m pytest tests/test_cli_surfaces.py::test_cli_review_routing_drill_outputs_fixture_artifact -q` passed with 1 test.
- `.venv/bin/python -m pytest -q` passed with 229 tests.
- `.venv/bin/ruff check src/business_card_watchdog/cli.py tests/test_cli_surfaces.py` passed.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This was presentation and documentation hardening for the synthetic drill only. It did not process configured/private SyncThing inputs, run public-web search, call paid enrichment, validate a real operator response, create or modify `selected_live_target.json`, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.

## Turn 185 | 2026-06-15

Continued Plan 0009 with Slice 0009-A109.

Implemented:

- Runtime readiness `safe_next_actions` now includes `run_fixture_review_routing_drill` with command `drills review-routing` whenever runtime readiness is not blocked.
- Non-JSON `bcw runtime-readiness` output now renders safe next actions and stop conditions instead of only aggregate check counts.
- Service and CLI coverage now assert the fixture review/routing drill handoff from runtime readiness.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_runtime_readiness_reports_user_scope_runtime_state tests/test_cli_surfaces.py::test_cli_runtime_readiness_reports_local_runtime_state tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 4 tests.
- `.venv/bin/python -m pytest -q` passed with 229 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/cli.py tests/test_service.py tests/test_cli_surfaces.py` passed.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This was runtime/readiness handoff and text presentation hardening only. It did not process configured/private SyncThing inputs, run public-web search, call paid enrichment, validate a real operator response, create or modify `selected_live_target.json`, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.

## Turn 186 | 2026-06-15

Continued Plan 0009 with Slice 0009-A110.

Implemented:

- Operator dashboard command, API route, MCP tool, and safe-action maps now expose the synthetic review/routing drill.
- Service recovery command and safe-action maps now expose the same fixture drill as a no-live recovery proof.
- Text output for operator dashboard and service recovery now renders the review/routing drill command.
- Service, CLI, API, and MCP coverage now assert the dashboard/recovery drill handoff.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_recovery_report_composes_status_and_recovery_commands tests/test_service.py::test_service_operator_dashboard_composes_no_live_readiness tests/test_cli_surfaces.py::test_cli_operator_dashboard_reports_no_live_summary tests/test_cli_surfaces.py::test_cli_service_recovery_reports_status_shape tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 6 tests.
- `.venv/bin/python -m pytest -q` passed with 229 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/cli.py tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py` passed.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This was dashboard/recovery handoff and text presentation hardening only. It did not process configured/private SyncThing inputs, run public-web search, call paid enrichment, validate a real operator response, create or modify `selected_live_target.json`, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.

## Turn 187 | 2026-06-15

Continued Plan 0009 with Slice 0009-A111.

Implemented:

- Review/routing drill payloads now include `business-card-watchdog.review-routing-drill-agent-readback.v1`.
- The agent readback summarizes pass/attention state, expected artifact checks, safe executed/skipped action counts, manual boundary, zero write/network counters, and no-private/no-live flags.
- Non-JSON drill output now shows agent readback state and the next manual boundary.
- Service, CLI, API, and MCP coverage now assert the agent readback contract.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_review_routing_drill_exercises_safe_fixture_route tests/test_cli_surfaces.py::test_cli_review_routing_drill_outputs_fixture_artifact tests/test_api.py::test_api_review_routing_drill_outputs_fixture_artifact tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 4 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/cli.py tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py` passed.
- `.venv/bin/python -m pytest -q` passed with 229 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This was synthetic drill readback hardening only. It did not process configured/private SyncThing inputs, run public-web search, call paid enrichment, validate a real operator response, create or modify `selected_live_target.json`, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.

## Turn 188 | 2026-06-15

Continued Plan 0009 with Slice 0009-A112.

Implemented:

- Added `business-card-watchdog.latest-review-routing-drill.v1`.
- Operator dashboard and service recovery now summarize the latest run-level `review_routing_drill.json` artifact.
- The summary reports latest drill state, run/job IDs, selected-run match, agent readback state, manual boundary, artifact-check counts, safe action counts, zero write/network counters, and no-private/no-live flags.
- CLI dashboard and recovery text output now render the latest review/routing drill state.
- Service and CLI coverage now assert both the no-drill state and the passed synthetic-drill readback.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_operator_dashboard_composes_no_live_readiness tests/test_service.py::test_service_dashboard_and_recovery_report_latest_review_routing_drill tests/test_service.py::test_service_recovery_report_composes_status_and_recovery_commands tests/test_cli_surfaces.py::test_cli_operator_dashboard_reports_no_live_summary tests/test_cli_surfaces.py::test_cli_service_recovery_reports_status_shape tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 7 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/cli.py tests/test_service.py tests/test_cli_surfaces.py` passed.
- `.venv/bin/python -m pytest -q` passed with 230 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This was read-only drill evidence discovery only. It did not process configured/private SyncThing inputs, run public-web search, call paid enrichment, validate a real operator response, create or modify `selected_live_target.json`, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.

## Turn 189 | 2026-06-15

Continued Plan 0009 with Slice 0009-A113.

Implemented:

- Updated sink apply preflight and apply-result reasons to describe the current boundary accurately: broad live apply is disabled and operators must use selected-target write/readback pilot commands.
- Updated live Google Contacts and Odollo/Odoo readiness messages to describe existing local readiness evidence plus selected-target audit and explicit one-job pilot requirements.
- Removed stale active-surface wording that said live write/readback adapters were not implemented.
- Sink/service/API/MCP focused coverage now asserts the selected-target pilot boundary language and zero write/network behavior.

Validation:

- `.venv/bin/python -m pytest tests/test_sinks.py::test_live_odoo_readiness_blocks_until_local_evidence_when_apply_enabled tests/test_sinks.py::test_live_odoo_readiness_reports_local_evidence_without_call tests/test_sinks.py::test_build_sink_apply_preflight_is_zero_write_and_explicitly_gated tests/test_sinks.py::test_build_sink_apply_result_blocks_live_write_after_approval tests/test_service.py::test_service_preflight_sink_apply_writes_zero_write_artifact tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 7 tests.
- `.venv/bin/ruff check src/business_card_watchdog/sinks.py tests/test_sinks.py` passed.
- `.venv/bin/python -m pytest -q` passed with 230 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This was messaging and readiness-boundary hardening only. It did not process configured/private SyncThing inputs, run public-web search, call paid enrichment, validate a real operator response, create or modify `selected_live_target.json`, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.

## Turn 190 | 2026-06-15

Continued Plan 0009 with Slice 0009-A114.

Implemented:

- Live selection packets now include `pilot_command_checklist`, an ordered operator/subagent checklist for validation, selected-target creation, selected-target audit, lookup-smoke handoff, and scope-specific live lookup/write/readback pilot commands.
- Each checklist step records whether it requires explicit operator action, writes a runtime artifact, makes a live call, writes a sink, is enabled for the selected scope, and where to stop.
- Live selection packet commands now include selected-target audit, lookup-smoke handoff, and readback adapter request commands alongside the existing validation and pilot commands.
- CLI live-selection-packet text output now renders the pilot checklist without raw dict output.
- Service and CLI coverage now assert lookup and all-scope checklist ordering, live-call flags, sink-write flags, and zero write/network counters.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_live_selection_packet_does_not_select_target tests/test_service.py::test_service_live_selection_packet_all_scope_lists_write_and_readback_checklist tests/test_service.py::test_service_live_selection_packet_reports_existing_selected_target_context tests/test_cli_surfaces.py::test_cli_live_selection_packet_writes_no_selected_target tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 6 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/cli.py tests/test_service.py tests/test_cli_surfaces.py` passed.
- `.venv/bin/python -m pytest -q` passed with 231 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This was no-live command sequencing and packet presentation only. It did not process configured/private SyncThing inputs, run public-web search, call paid enrichment, validate a real operator response, create or modify `selected_live_target.json`, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.

## Turn 191 | 2026-06-15

Continued Plan 0009 with Slice 0009-A115.

Implemented:

- Added `business-card-watchdog.pilot-command-checklist-summary.v1`.
- Run-level live pilot status entries now summarize each job's ordered pilot command checklist.
- Live pilot handoff entries carry the same summary for operator/subagent use.
- The summary reports step, live-call, sink-write, explicit-operator, and runtime-artifact counts plus ordered step flags.
- Status generates a deterministic fallback checklist from selected-target metadata when direct `select-live-target` flows did not persist a `live_selection_packet.json`.
- Service, CLI, API, and MCP coverage assert lookup-scope and all-scope summaries.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_selected_live_target_gates_non_simulated_lookup tests/test_cli_surfaces.py::test_cli_selected_target_audit_reports_existing_approval tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 4 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py` passed.
- `.venv/bin/python -m pytest -q` passed with 231 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This was status/handoff presentation only. It did not process configured/private SyncThing inputs, run public-web search, call paid enrichment, validate a real operator response, create or modify `selected_live_target.json`, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.

## Turn 192 | 2026-06-15

Continued Plan 0009 with Slice 0009-A116.

Implemented:

- Added `business-card-watchdog.live-pilot-checklist-rollup.v1`.
- Operator dashboard handoff summaries now roll up operator-required pilot checklist jobs, total steps, live-call steps, sink-write steps, explicit-operator steps, runtime-artifact steps, and sample jobs.
- Service recovery reports carry the same rollup for recovery handoffs.
- Dashboard and recovery text output now render compact live-pilot checklist counts.
- Rollups count only operator-required handoff entries, so no-candidate runs do not appear to have queued live-pilot work.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_operator_dashboard_composes_no_live_readiness tests/test_cli_surfaces.py::test_cli_operator_dashboard_reports_no_live_summary tests/test_cli_surfaces.py::test_cli_live_target_candidates_reports_text_and_json tests/test_cli_surfaces.py::test_cli_service_recovery_reports_status_shape tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 6 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/cli.py tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py` passed.
- `.venv/bin/python -m pytest -q` passed with 231 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This was dashboard/recovery presentation only. It did not process configured/private SyncThing inputs, run public-web search, call paid enrichment, validate a real operator response, create or modify `selected_live_target.json`, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.

## Turn 193 | 2026-06-15

Continued Plan 0009 with Slice 0009-A117.

Implemented:

- Added `business-card-watchdog.pilot-command-sequence.v1`.
- Live pilot status entries now split the ordered pilot checklist into safe-inspection, explicit-operator, live-call, and sink-write step groups.
- Live pilot handoff entries carry the same sequence groups for subagent handoffs.
- The sequence payload includes next safe and next explicit steps plus an execution policy that forbids running live or sink-write commands from the handoff.
- Service, CLI, API, and MCP coverage assert lookup-scope and all-scope sequence grouping.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_selected_live_target_gates_non_simulated_lookup tests/test_cli_surfaces.py::test_cli_selected_target_audit_reports_existing_approval tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 4 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py` passed.
- `.venv/bin/python -m pytest -q` passed with 231 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This was status/handoff sequencing metadata only. It did not process configured/private SyncThing inputs, run public-web search, call paid enrichment, validate a real operator response, create or modify `selected_live_target.json`, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.

## Turn 194 | 2026-06-15

Continued Plan 0009 with Slice 0009-A118.

Implemented:

- Live pilot operator-response validation reports now include `validation_command_sequence` using `business-card-watchdog.pilot-command-sequence.v1`.
- Validation reports split post-selection commands into safe-inspection, explicit-operator, live-call, and sink-write groups.
- CLI validation text now renders compact sequence-group counts.
- Blocked validations return an empty sequence so subagents can treat the report as non-executable.
- Service, CLI, API, and MCP coverage assert zero-live/zero-sink sequence grouping.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_selected_live_target_gates_non_simulated_lookup tests/test_cli_surfaces.py::test_cli_selected_target_audit_reports_existing_approval tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 4 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/cli.py tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py` passed.
- `.venv/bin/python -m pytest -q` passed with 231 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This was validation metadata and text presentation only. It did not process configured/private SyncThing inputs, run public-web search, call paid enrichment, validate a real operator response for a real target, create or modify `selected_live_target.json`, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.

## Turn 195 | 2026-06-15

Continued Plan 0009 with Slice 0009-A119.

Implemented:

- Added `business-card-watchdog.pilot-command-sequence-summary.v1`.
- Operator dashboard live handoff entries now include compact sequence counts for safe-inspection, explicit-operator, live-call, and sink-write steps.
- Dashboard entries also expose the next safe-inspection step and next explicit-operator step for subagent handoffs.
- CLI dashboard text renders the per-entry sequence summary.
- CLI, API, MCP, and service coverage assert the dashboard sequence summary and zero-write/no-live behavior.

Validation:

- `.venv/bin/python -m pytest tests/test_cli_surfaces.py::test_cli_live_target_candidates_reports_text_and_json tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service tests/test_service.py::test_service_operator_dashboard_composes_no_live_readiness -q` passed with 4 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/cli.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py tests/test_service.py` passed.
- `.venv/bin/python -m pytest -q` passed with 231 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This was dashboard presentation metadata only. It did not process configured/private SyncThing inputs, run public-web search, call paid enrichment, validate a real operator response for a real target, create or modify `selected_live_target.json`, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.

## Turn 196 | 2026-06-15

Continued Plan 0009 with Slice 0009-A120.

Implemented:

- Added `business-card-watchdog.operator-dashboard.live-pilot-execution-packet.v1`.
- Operator dashboard live handoff summaries now include a compact no-live execution packet with the next safe command, next explicit operator command, packet entries, stop conditions, and execution policy.
- CLI dashboard text renders the packet state, next commands, and live/sink-write prohibition.
- Service, CLI, API, and MCP coverage assert the execution packet and zero-write/no-network behavior.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_operator_dashboard_composes_no_live_readiness tests/test_cli_surfaces.py::test_cli_live_target_candidates_reports_text_and_json tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 4 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/cli.py tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py` passed.
- `.venv/bin/python -m pytest -q` passed with 231 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This was dashboard presentation and handoff packaging only. It did not process configured/private SyncThing inputs, run public-web search, call paid enrichment, validate a real operator response for a real target, create or modify `selected_live_target.json`, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.

## Turn 197 | 2026-06-15

Continued Plan 0009 with Slice 0009-A121.

Implemented:

- Added `business-card-watchdog.live-pilot-operator-approval-readback.v1`.
- Live pilot operator-response validation now includes a compact approval readback with parsed fields, matched template identity, missing/mismatch counts, next safe command, and no-create/no-live counters.
- CLI validation text renders approval readback for ready and blocked responses.
- Service, CLI, API, and MCP coverage assert the approval readback and zero-write/no-network behavior.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_selected_live_target_gates_non_simulated_lookup tests/test_cli_surfaces.py::test_cli_selected_target_audit_reports_existing_approval tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_mcp_jsonl_server_lists_and_calls_tools -q` passed with 4 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/cli.py tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py` passed.
- `.venv/bin/python -m pytest -q` passed with 231 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This was validation readback metadata and CLI presentation only. It did not process configured/private SyncThing inputs, run public-web search, call paid enrichment, create or modify `selected_live_target.json`, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.

## Turn 198 | 2026-06-15

Continued Plan 0009 with Slice 0009-A122.

Implemented:

- Added `business-card-watchdog.live-pilot-approval-packet.v1`.
- Added no-live approval packet export across service, CLI, API, and MCP surfaces.
- Approval packets expose operator approval templates, prompts, copyable fields, validation commands, next explicit command hints, stop conditions, and zero-write/no-network counters without the full dashboard payload.
- Operator dashboard command/API/MCP maps now advertise the approval packet surface.
- Service, CLI, API, and MCP coverage assert packet contents, dashboard discovery, and zero-write/no-network behavior.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_operator_dashboard_composes_no_live_readiness tests/test_service.py::test_service_selected_live_target_gates_non_simulated_lookup tests/test_cli_surfaces.py::test_cli_selected_target_audit_reports_existing_approval tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 6 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/cli.py src/business_card_watchdog/api.py src/business_card_watchdog/mcp.py tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py` passed.
- `.venv/bin/python -m pytest -q` passed with 231 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This was no-live approval-template export only. It did not process configured/private SyncThing inputs, run public-web search, call paid enrichment, validate a real operator response for a real target, create or modify `selected_live_target.json`, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.

## Turn 199 | 2026-06-15

Continued Plan 0009 with Slice 0009-A123.

Implemented:

- Added `business-card-watchdog.selected-live-target-preflight.v1`.
- Added no-write selected-target creation preflight across service, CLI, API, and MCP surfaces.
- Preflight reuses live pilot operator-response validation and reports whether `selected_live_target.json` would be allowed while keeping `creates_selected_live_target=false`.
- Operator dashboard command/API/MCP maps now advertise the preflight surface.
- Service, CLI, API, and MCP coverage assert ready and blocked preflight states plus zero-write/no-network behavior.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_operator_dashboard_composes_no_live_readiness tests/test_service.py::test_service_selected_live_target_gates_non_simulated_lookup tests/test_cli_surfaces.py::test_cli_selected_target_audit_reports_existing_approval tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 6 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/cli.py src/business_card_watchdog/api.py src/business_card_watchdog/mcp.py tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py` passed.
- `.venv/bin/python -m pytest -q` passed with 231 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This was selected-target creation preflight only. It did not process configured/private SyncThing inputs, run public-web search, call paid enrichment, create or modify `selected_live_target.json`, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.

## Turn 200 | 2026-06-15

Continued Plan 0009 with Slice 0009-A124.

Implemented:

- Added `business-card-watchdog.selected-live-target-artifact-preview.v1`.
- Added no-write selected-target artifact preview across service, CLI, API, and MCP surfaces.
- Preview reports the exact selected-target artifact field map that would be written when preflight is ready, with volatile fields marked as generated on write.
- Operator dashboard command/API/MCP maps now advertise the preview surface.
- Service, CLI, API, and MCP coverage assert ready and blocked preview states plus zero-write/no-network behavior.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_selected_live_target_gates_non_simulated_lookup tests/test_cli_surfaces.py::test_cli_selected_target_audit_reports_existing_approval tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 5 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/cli.py src/business_card_watchdog/api.py src/business_card_watchdog/mcp.py tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py` passed.
- `.venv/bin/python -m pytest -q` passed with 231 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This was selected-target artifact preview only. It did not process configured/private SyncThing inputs, run public-web search, call paid enrichment, create or modify `selected_live_target.json`, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.

## Turn 201 | 2026-06-15

Continued Plan 0009 with Slice 0009-A125.

Implemented:

- Added `business-card-watchdog.selected-live-target-from-response.v1`.
- Added guarded selected-target create-from-response flow across service, CLI, API, and MCP surfaces.
- Default mode returns preview/no-write output and does not create `selected_live_target.json`.
- Explicit write mode requires `--write-selected-target` or equivalent API/MCP flag and reuses the existing selected-target writer only after preflight/preview is ready.
- Operator dashboard command/API/MCP maps now advertise the guarded create-from-response surface.
- Service, CLI, API, and MCP coverage assert default preview behavior, explicit creation behavior, blocked behavior, and zero live sink calls.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_operator_dashboard_composes_no_live_readiness tests/test_service.py::test_service_selected_live_target_gates_non_simulated_lookup tests/test_cli_surfaces.py::test_cli_selected_target_audit_reports_existing_approval tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 6 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/cli.py src/business_card_watchdog/api.py src/business_card_watchdog/mcp.py tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py` passed.
- `.venv/bin/python -m pytest -q` passed with 231 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This created `selected_live_target.json` only in focused synthetic tests when the explicit write flag was set. Default CLI/API/MCP behavior remains no-write preview. It did not process configured/private SyncThing inputs, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.

## Turn 202 | 2026-06-15

Continued Plan 0009 with Slice 0009-A126.

Implemented:

- Added `business-card-watchdog.selected-live-target-handoff-from-response.v1`.
- Added no-live selected-target handoff/readback from a validated operator response across service, CLI, API, and MCP surfaces.
- Handoff output composes validation state, selected target identity, selected-target audit preview, next safe audit command, and next explicit command when audit evidence is ready.
- Default mode does not write `selected_live_target_audit.json`; explicit write-audit mode persists only the audit artifact.
- Operator dashboard command/API/MCP maps now advertise the handoff surface.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_operator_dashboard_composes_no_live_readiness tests/test_service.py::test_service_selected_live_target_gates_non_simulated_lookup tests/test_cli_surfaces.py::test_cli_selected_target_audit_reports_existing_approval tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 6 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/cli.py src/business_card_watchdog/api.py src/business_card_watchdog/mcp.py tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py` passed.

Safety:

- This was selected-target readback and audit handoff only. It did not create or modify `selected_live_target.json`, process configured/private SyncThing inputs, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.

## Turn 203 | 2026-06-15

Continued Plan 0009 with Slice 0009-A127.

Implemented:

- Added `business-card-watchdog.lookup-smoke-handoff-from-response.v1`.
- Added run-scoped lookup-smoke handoff preview from a validated operator response across service, CLI, API, and MCP surfaces.
- Existing job-scoped lookup-smoke handoff now supports `write=False` while preserving default write behavior.
- Default run-scoped behavior previews the lookup-smoke handoff without writing `sink_lookup_smoke_handoff.json`; explicit write-handoff mode persists only that handoff artifact.
- Operator dashboard command/API/MCP maps now advertise the handoff surface.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_operator_dashboard_composes_no_live_readiness tests/test_service.py::test_service_selected_live_target_gates_non_simulated_lookup tests/test_cli_surfaces.py::test_cli_selected_target_audit_reports_existing_approval tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 6 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/cli.py src/business_card_watchdog/api.py src/business_card_watchdog/mcp.py tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py` passed.

Safety:

- This was lookup-smoke handoff preparation only. It did not create or modify `selected_live_target.json`, execute selected lookup smoke, process configured/private SyncThing inputs, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.

## Turn 204 | 2026-06-15

Continued Plan 0009 with Slice 0009-A128.

Implemented:

- Added `business-card-watchdog.selected-lookup-smoke-execution-packet-from-response.v1`.
- Added run-scoped selected lookup smoke execution packet from a validated operator response across service, CLI, API, and MCP surfaces.
- Default mode is no-execute and reports whether selected lookup smoke would be allowed, exact explicit execution command, blocked reasons, and follow-up inspection commands.
- Explicit execute mode remains blocked unless the run-scoped lookup-smoke handoff is ready.
- Operator dashboard command/API/MCP maps now advertise the execution packet surface.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_operator_dashboard_composes_no_live_readiness tests/test_service.py::test_service_selected_live_target_gates_non_simulated_lookup tests/test_cli_surfaces.py::test_cli_selected_target_audit_reports_existing_approval tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 6 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/cli.py src/business_card_watchdog/api.py src/business_card_watchdog/mcp.py tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py` passed.

Safety:

- This was selected lookup smoke execution-packet hardening only. Default mode did not execute selected lookup smoke or write `selected_lookup_smoke.json`; blocked explicit execution returned a blocked packet without live lookup, live write, live readback, public-web search, paid enrichment, GWS/Odollo/Odoo calls, or configured/private SyncThing processing.

## Turn 205 | 2026-06-15

Continued Plan 0009 with Slice 0009-A129.

Implemented:

- Added `business-card-watchdog.selected-write-pilot-execution-packet-from-response.v1`.
- Added run-scoped selected write-pilot execution packet from a validated operator response across service, CLI, API, and MCP surfaces.
- Default mode is no-execute and reports selected target context, lookup-smoke evidence, downstream duplicate evidence, live apply readiness, exact explicit write command, and blocked reasons.
- Explicit execute mode remains blocked unless selected target scope allows write, lookup evidence exists, downstream duplicate review is resolved, and live apply readiness passes.
- Operator dashboard command/API/MCP maps now advertise the write-pilot execution packet surface.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_operator_dashboard_composes_no_live_readiness tests/test_service.py::test_service_selected_live_target_gates_non_simulated_lookup tests/test_cli_surfaces.py::test_cli_selected_target_audit_reports_existing_approval tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 6 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/cli.py src/business_card_watchdog/api.py src/business_card_watchdog/mcp.py tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py` passed.
- `.venv/bin/python -m pytest -q` passed with 231 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This was selected write-pilot execution-packet hardening only. Default mode did not execute sink write pilot or write `sink_write_pilot.json`; blocked explicit execution returned a blocked packet without live lookup, live write, live readback, public-web search, paid enrichment, GWS/Odollo/Odoo calls, or configured/private SyncThing processing.

## Turn 206 | 2026-06-15

Continued Plan 0009 with Slice 0009-A130.

Implemented:

- Added `business-card-watchdog.selected-readback-pilot-execution-packet-from-response.v1`.
- Added run-scoped selected readback-pilot execution packet from a validated operator response across service, CLI, API, and MCP surfaces.
- Default mode is no-execute and reports selected target context, source write-pilot evidence, readback adapter request state, exact explicit readback command, and blocked reasons.
- Explicit execute mode remains blocked unless selected target scope allows readback, `sink_write_pilot.json` is live-written by the current selected target, and `sink_adapter_request_readback.json` exists.
- Operator dashboard command/API/MCP maps now advertise the readback-pilot execution packet surface.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_operator_dashboard_composes_no_live_readiness tests/test_service.py::test_service_selected_live_target_gates_non_simulated_lookup tests/test_cli_surfaces.py::test_cli_selected_target_audit_reports_existing_approval tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 6 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/cli.py src/business_card_watchdog/api.py src/business_card_watchdog/mcp.py tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py` passed.
- `.venv/bin/python -m pytest -q` passed with 231 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This was selected readback-pilot execution-packet hardening only. Default mode did not execute sink readback pilot or write `sink_readback_pilot.json`; blocked explicit execution returned a blocked packet without live lookup, live write, live readback, public-web search, paid enrichment, GWS/Odollo/Odoo calls, or configured/private SyncThing processing.

## Turn 207 | 2026-06-15

Continued Plan 0009 with Slice 0009-A131.

Implemented:

- Added `business-card-watchdog.live-pilot-closeout-packet-from-response.v1`.
- Added run-scoped live-pilot closeout packet from a validated operator response across service, CLI, API, and MCP surfaces.
- Default mode is no-write and composes selected-target handoff evidence with a closeout report preview.
- Explicit `write_closeout` writes only `live_pilot_closeout.json`; it does not run live lookup, live write, or live readback.
- Operator dashboard command/API/MCP maps now advertise the closeout-packet surface.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_operator_dashboard_composes_no_live_readiness tests/test_service.py::test_service_selected_live_target_gates_non_simulated_lookup tests/test_cli_surfaces.py::test_cli_selected_target_audit_reports_existing_approval tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 6 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/cli.py src/business_card_watchdog/api.py src/business_card_watchdog/mcp.py tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py` passed.
- `.venv/bin/python -m pytest -q` passed with 231 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This was live-pilot closeout packet hardening only. Default mode did not write `live_pilot_closeout.json`; explicit write mode writes only the closeout report artifact and does not execute live lookup, live write, live readback, public-web search, paid enrichment, GWS/Odollo/Odoo calls, or configured/private SyncThing processing.

## Turn 208 | 2026-06-15

Continued Plan 0009 with Slice 0009-A132.

Implemented:

- Added `business-card-watchdog.live-pilot-operator-workflow-packet-from-response.v1`.
- Added run-scoped consolidated live-pilot operator workflow packet from a validated response across service, CLI, API, and MCP surfaces.
- The packet composes selected target, lookup handoff, lookup smoke, write pilot, readback pilot, and closeout packet state without executing live calls.
- Operator dashboard command/API/MCP maps now advertise the workflow packet surface.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_operator_dashboard_composes_no_live_readiness tests/test_service.py::test_service_selected_live_target_gates_non_simulated_lookup tests/test_cli_surfaces.py::test_cli_selected_target_audit_reports_existing_approval tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 6 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/cli.py src/business_card_watchdog/api.py src/business_card_watchdog/mcp.py tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py` passed.
- `.venv/bin/python -m pytest -q` passed with 231 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This was live-pilot workflow packet composition only. Default mode did not execute lookup, write, readback, or closeout writes and did not run public-web search, paid enrichment, GWS/Odollo/Odoo calls, or configured/private SyncThing processing.

## Turn 209 | 2026-06-15

Continued Plan 0009 with Slice 0009-A133.

Implemented:

- Added `business-card-watchdog.live-pilot-operator-rehearsal-from-response.v1`.
- Added run-scoped live-pilot operator rehearsal from a validated response across service, CLI, API, and MCP surfaces.
- The rehearsal wraps the workflow packet into one safe inspection command followed by the next explicit operator command, without executing either.
- Operator dashboard command/API/MCP maps now advertise the rehearsal surface.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_operator_dashboard_composes_no_live_readiness tests/test_service.py::test_service_selected_live_target_gates_non_simulated_lookup tests/test_cli_surfaces.py::test_cli_selected_target_audit_reports_existing_approval tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 6 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/cli.py src/business_card_watchdog/api.py src/business_card_watchdog/mcp.py tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py` passed.
- `.venv/bin/python -m pytest -q` passed with 231 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This was rehearsal/readback only. It did not execute the explicit operator command and did not run live lookup, live write, live readback, public-web search, paid enrichment, GWS/Odollo/Odoo calls, or configured/private SyncThing processing.

## Turn 210 | 2026-06-15

Continued Plan 0009 with Slice 0009-A134.

Implemented:

- Added `business-card-watchdog.live-pilot-readiness-export-from-response.v1`.
- Added run-scoped redacted live-pilot readiness export from a validated operator response across service, CLI, API, and MCP surfaces.
- The export packages the operator response digest, redacted response fields, rehearsal packet, workflow packet, stop conditions, and inspection/explicit command templates for operator review.
- Operator dashboard command/API/MCP maps now advertise the readiness export surface.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_selected_live_target_gates_non_simulated_lookup -q` passed with 1 test.
- `.venv/bin/python -m pytest tests/test_service.py::test_service_operator_dashboard_composes_no_live_readiness tests/test_service.py::test_service_selected_live_target_gates_non_simulated_lookup tests/test_cli_surfaces.py::test_cli_selected_target_audit_reports_existing_approval tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 6 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/cli.py src/business_card_watchdog/api.py src/business_card_watchdog/mcp.py tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py` passed.
- `.venv/bin/python -m pytest -q` passed with 231 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This was export/readback only. It did not execute lookup, write, readback, closeout, public-web search, paid enrichment, GWS/Odollo/Odoo calls, or configured/private SyncThing processing. The written export stores a response digest and redacted fields only; raw operator response and safety confirmation are not persisted.

## Turn 211 | 2026-06-15

Continued Plan 0009 with Slice 0009-A135.

Implemented:

- Added `business-card-watchdog.live-pilot-execution-checklist-from-response.v1`.
- Added run-scoped export-backed live-pilot execution checklist from a validated response across service, CLI, API, and MCP surfaces.
- The checklist reads `live_pilot_readiness_export.json`, verifies redaction, response digest, and run/job/sink/operator alignment, then exposes an executable live command only when the export matches current state.
- Operator dashboard command/API/MCP maps now advertise the checklist surface.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_operator_dashboard_composes_no_live_readiness tests/test_service.py::test_service_selected_live_target_gates_non_simulated_lookup tests/test_cli_surfaces.py::test_cli_selected_target_audit_reports_existing_approval tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 6 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/cli.py src/business_card_watchdog/api.py src/business_card_watchdog/mcp.py tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py` passed.
- `.venv/bin/python -m pytest -q` passed with 231 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This was checklist/readback only. It did not execute lookup, write, readback, closeout, public-web search, paid enrichment, GWS/Odollo/Odoo calls, or configured/private SyncThing processing. It refuses to show `executable_live_command` unless the persisted redacted readiness export exists and matches current response and rehearsal state.

## Turn 212 | 2026-06-15

Continued Plan 0009 with Slice 0009-A136.

Implemented:

- Added `business-card-watchdog.live-pilot-command-copy-packet-from-response.v1`.
- Added run-scoped command-copy packet generation from a validated response across service, CLI, API, and MCP surfaces.
- The packet composes the export-backed execution checklist and only returns command-copy text when the checklist is ready and the operator acknowledgement names the run, job, sink, and operator with an approval/copy verb.
- Operator dashboard command/API/MCP maps now advertise the command-copy packet surface.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_operator_dashboard_composes_no_live_readiness tests/test_service.py::test_service_selected_live_target_gates_non_simulated_lookup tests/test_cli_surfaces.py::test_cli_selected_target_audit_reports_existing_approval tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 6 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/cli.py src/business_card_watchdog/api.py src/business_card_watchdog/mcp.py tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py` passed.
- `.venv/bin/python -m pytest -q` passed with 231 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This was command-copy/readback only. It did not execute lookup, write, readback, closeout, public-web search, paid enrichment, GWS/Odollo/Odoo calls, or configured/private SyncThing processing. It refuses to show command-copy text unless the persisted redacted readiness export matches current state and the operator acknowledgement matches the intended live-pilot context.

## Turn 213 | 2026-06-15

Continued Plan 0009 with Slice 0009-A137.

Implemented:

- Updated `docs/operations/live-pilot-checklists.md` so read-only lookup smoke and one-job write/readback procedures require the final pre-live command-copy gate.
- Documented the operator response and acknowledgement variables, redacted readiness export, execution checklist, and command-copy packet sequence.
- Updated `README.md` to point operators to the readiness export, execution checklist, and command-copy packet before any non-simulated lookup/write/readback command.

Validation:

- `rg -n "live-pilot-readiness-export-from-response|live-pilot-execution-checklist-from-response|live-pilot-command-copy-packet-from-response|ready_for_operator_copy|command_copy_text" README.md docs/operations/live-pilot-checklists.md docs/dev/plans/0009-2026-06-14-operator-selected-live-smoke-and-pilot-rollout.md RUNBOOK.md` passed.
- `git diff --check` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `.venv/bin/python -m pytest -q` passed with 231 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This was documentation only. It did not validate an operator response, execute any returned command, create or modify `selected_live_target.json`, process private SyncThing inputs, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.

## Turn 214 | 2026-06-15

Continued Plan 0009 with Slice 0009-A138.

Implemented:

- Added `business-card-watchdog.live-pilot-rehearsal-drill.v1`.
- Added `bcw drills live-pilot-rehearsal`, `POST /drills/live-pilot-rehearsal`, and MCP tool `business_card_watchdog_live_pilot_rehearsal_drill`.
- The drill builds on the synthetic review-routing fixture and rehearses selected-target creation, selected-target audit, lookup handoff, redacted readiness export, execution checklist, and command-copy packet.
- Operator dashboard command/API/MCP maps now advertise the live-pilot rehearsal drill.
- Updated README and live-pilot checklist docs so operators can run the no-live rehearsal before selecting a real target.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_live_pilot_rehearsal_drill_reaches_command_copy_gate tests/test_cli_surfaces.py::test_cli_live_pilot_rehearsal_drill_reaches_command_copy_gate tests/test_cli_surfaces.py::test_cli_operator_dashboard_reports_no_live_summary tests/test_api.py::test_api_live_pilot_rehearsal_drill_reaches_command_copy_gate tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 7 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/cli.py src/business_card_watchdog/api.py src/business_card_watchdog/mcp.py tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py` passed.
- `.venv/bin/python -m pytest -q` passed with 234 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This was synthetic no-live rehearsal only. It created synthetic fixture runtime artifacts under the configured data/cache dirs and did not process private SyncThing inputs, run public-web search, call paid enrichment, execute command-copy text, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.

## Turn 215 | 2026-06-15

Continued Plan 0009 with a CI portability fix for Slice 0009-A138.

Implemented:

- Adjusted `business-card-watchdog.live-pilot-rehearsal-drill.v1` top-level assertions so CI-portable pass/fail is based on the deterministic no-live rehearsal path rather than host-specific live lookup readiness.
- Kept live lookup readiness blockers visible in nested selection and handoff packets.
- Relaxed the service test to require command-copy text to be sink-scoped and bound to the same job/run, instead of requiring one host-specific next command.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_live_pilot_rehearsal_drill_reaches_command_copy_gate tests/test_cli_surfaces.py::test_cli_live_pilot_rehearsal_drill_reaches_command_copy_gate tests/test_api.py::test_api_live_pilot_rehearsal_drill_reaches_command_copy_gate tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 4 tests.
- CI-like temporary `HOME` with the offline business-card skill fixture: `.venv/bin/python -m pytest tests/test_service.py::test_service_live_pilot_rehearsal_drill_reaches_command_copy_gate tests/test_cli_surfaces.py::test_cli_live_pilot_rehearsal_drill_reaches_command_copy_gate tests/test_api.py::test_api_live_pilot_rehearsal_drill_reaches_command_copy_gate tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 4 tests.
- `.venv/bin/python -m pytest -q` passed with 234 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This was CI/test hardening only. It did not process private SyncThing inputs, run public-web search, call paid enrichment, execute command-copy text, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.

## Turn 216 | 2026-06-15

Executed Plan 0010 with Slice 0010-A.

Implemented:

- Added `business-card-watchdog.multi-card-preclassification-drill.v1`.
- Added fixture-only synthetic multi-card image generation under the cache directory.
- Added service, CLI, API, and MCP surfaces for `multi_card_preclassification_drill`.
- Operator dashboard command/API/MCP maps now advertise the multi-card preclassification drill.
- Updated CI to install `.[dev,vision]` so OpenCV rectangle detection is exercised upstream.
- Updated README, public upstream validation docs, roadmap, and Plan 0010.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_multi_card_preclassification_drill_records_candidate_boxes tests/test_cli_surfaces.py::test_cli_multi_card_preclassification_drill_records_candidate_boxes tests/test_api.py::test_api_multi_card_preclassification_drill_records_candidate_boxes tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_multi_card_preclassification_drill_records_candidate_boxes -q` passed with 5 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/cli.py src/business_card_watchdog/api.py src/business_card_watchdog/mcp.py tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py` passed.
- `.venv/bin/python -m pytest -q` passed with 238 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This was fixture-only preclassification proof. It did not process private SyncThing inputs, invoke OCR/App Intelligence, run public-web search, call paid enrichment, execute command-copy text, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.

## Turn 217 | 2026-06-15

Executed Plan 0011 with Slice 0011-A.

Implemented:

- Added `business-card-watchdog.card-candidate-boxes.v1`.
- Added deterministic candidate manifest construction from OpenCV rectangle boxes.
- Wired batch orchestration to persist `card_candidates.json` before OCR/App Intelligence when deterministic boxes exist.
- Recorded `card_candidates` ledger artifacts and `card_candidates_recorded` events.
- Added synthetic multi-card fixture coverage for normal dry-run batch processing.
- Updated README and roadmap documentation for the new pre-OCR candidate manifest.

Validation:

- `.venv/bin/python -m pytest tests/test_preclassifier.py::test_preclassifier_detects_multiple_cards_in_large_photo tests/test_preclassifier.py::test_orchestrator_records_multi_card_candidate_manifest -q` passed with 2 tests.
- `.venv/bin/ruff check src/business_card_watchdog/preclassifier.py src/business_card_watchdog/orchestrator.py tests/test_preclassifier.py tests/synthetic_fixtures.py` passed.
- `.venv/bin/python -m pytest -q` passed with 239 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This was fixture/runtime-artifact only. It did not process private SyncThing inputs, run public-web search, call paid enrichment, invoke per-candidate OCR/App Intelligence, execute command-copy text, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.

## Turn 218 | 2026-06-15

Executed Plan 0012 with Slice 0012-A.

Implemented:

- Added `business-card-watchdog.card-candidate-work-items.v1`.
- Added deterministic candidate work item manifest construction from `card_candidates.json`.
- Wired batch orchestration to persist `candidate_work_items.json` beside `card_candidates.json`.
- Recorded `candidate_work_items` ledger artifacts and `candidate_work_items_recorded` events.
- Extended synthetic multi-card dry-run coverage to verify pending child work items, parent job lineage, and route/enrichment/write denial flags.
- Updated README and roadmap documentation for the pending child OCR/App Intelligence work queue.

Validation:

- `.venv/bin/python -m pytest tests/test_preclassifier.py::test_orchestrator_records_multi_card_candidate_manifest -q` passed with 1 test.
- `.venv/bin/ruff check src/business_card_watchdog/fanout.py src/business_card_watchdog/orchestrator.py tests/test_preclassifier.py` passed.
- `.venv/bin/python -m pytest -q` passed with 239 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This was fixture/runtime-artifact only. It did not process private SyncThing inputs, crop images, run public-web search, call paid enrichment, invoke child OCR/App Intelligence, execute command-copy text, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.

## Turn 219 | 2026-06-15

Executed Plan 0013 with Slice 0013-A.

Implemented:

- Added `business-card-watchdog.card-candidate-crops.v1`.
- Added bounded crop materialization from candidate work items.
- Wired batch orchestration to persist `candidate_crops.json` and crop images under each job artifact directory.
- Updated `candidate_work_items.json` so successfully cropped child work items move to `crop_ready` with crop path and bounds.
- Recorded `candidate_crops` ledger artifacts and `candidate_crops_recorded` events.
- Updated synthetic multi-card dry-run coverage to verify crop files, work item state, and ledger records.
- Updated README and roadmap documentation for candidate crop generation.

Validation:

- `.venv/bin/python -m pytest tests/test_preclassifier.py::test_orchestrator_records_multi_card_candidate_manifest -q` passed with 1 test.
- `.venv/bin/ruff check src/business_card_watchdog/fanout.py src/business_card_watchdog/orchestrator.py tests/test_preclassifier.py` passed.
- `.venv/bin/python -m pytest -q` passed with 239 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This used synthetic fixture images for validation. It did not run OCR/App Intelligence, normalize child contacts, route, enrich, write sinks, execute command-copy text, run public-web search, call paid APIs, or call GWS/Odollo/Odoo.

## Turn 220 | 2026-06-15

Executed Plan 0014 with Slice 0014-A.

Implemented:

- Added `business-card-watchdog.child-verification-requests.v1`.
- Added deterministic request manifest construction from crop-ready child work items.
- Wired batch orchestration to persist `child_verification_requests.json`.
- Updated `candidate_work_items.json` so crop-ready items record `verification_request_ready` and a request ID.
- Recorded `child_verification_requests` ledger artifacts and `child_verification_requests_recorded` events.
- Updated synthetic multi-card dry-run coverage to verify request lineage, dry-run state, explicit execution gate, and route/enrichment/write denial flags.
- Updated README and roadmap documentation for the dry-run child OCR/App Intelligence request contract.

Validation:

- `.venv/bin/python -m pytest tests/test_preclassifier.py::test_orchestrator_records_multi_card_candidate_manifest -q` passed with 1 test.
- `.venv/bin/ruff check src/business_card_watchdog/fanout.py src/business_card_watchdog/orchestrator.py tests/test_preclassifier.py` passed.
- `.venv/bin/python -m pytest -q` passed with 239 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This created execution-request artifacts only. It did not execute OCR/App Intelligence, normalize child contacts, route, enrich, write sinks, execute command-copy text, run public-web search, call paid APIs, or call GWS/Odollo/Odoo.

## Turn 221 | 2026-06-15

Executed Plan 0015 with Slice 0015-A.

Implemented:

- Added `business-card-watchdog.child-verification-results.v1`.
- Added synthetic offline child verification result construction from request artifacts.
- Wired batch orchestration to persist `child_verification_results.json` and per-candidate result detail files.
- Updated `candidate_work_items.json` so child items move to `verification_result_ready` and `awaiting_child_review`.
- Recorded `child_verification_results` ledger artifacts and `child_verification_results_recorded` events.
- Updated synthetic multi-card dry-run coverage to verify result lineage, synthetic OCR/contact data, review requirement, and route/enrichment/write denial flags.
- Updated README and roadmap documentation for synthetic child verification result artifacts.

Validation:

- `.venv/bin/python -m pytest tests/test_preclassifier.py::test_orchestrator_records_multi_card_candidate_manifest -q` passed with 1 test.
- `.venv/bin/ruff check src/business_card_watchdog/fanout.py src/business_card_watchdog/orchestrator.py tests/test_preclassifier.py` passed.
- `.venv/bin/python -m pytest -q` passed with 239 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This created synthetic offline result artifacts only. It did not process private SyncThing images, execute production OCR/App Intelligence, promote child contacts, route, enrich, write sinks, execute command-copy text, run public-web search, call paid APIs, or call GWS/Odollo/Odoo.

## Turn 222 | 2026-06-15

Executed Plan 0016 with Slice 0016-A.

Implemented:

- Added `business-card-watchdog.child-contact-promotions.v1`.
- Added child result promotion into normalized `business-card-watchdog.contact-candidate.v1` artifacts.
- Wired batch orchestration to persist `child_contact_promotions.json` and child contact candidate files.
- Updated `candidate_work_items.json` so child items move to `child_contact_candidate_ready` and `awaiting_child_contact_review`.
- Recorded `child_contact_promotions` ledger artifacts and `child_contact_promotions_recorded` events.
- Updated synthetic multi-card dry-run coverage to verify lineage, review state, normalized email, and route/enrichment/write denial flags.
- Updated README and roadmap documentation for review-pending child contact promotion.

Validation:

- `.venv/bin/python -m pytest tests/test_preclassifier.py::test_orchestrator_records_multi_card_candidate_manifest -q` passed with 1 test.
- `.venv/bin/ruff check src/business_card_watchdog/fanout.py src/business_card_watchdog/orchestrator.py tests/test_preclassifier.py` passed.
- `.venv/bin/python -m pytest -q` passed with 239 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This created review-pending child contact candidates only. It did not process private SyncThing images, execute production OCR/App Intelligence, auto-route contacts, execute command-copy text, run public-web search, call paid APIs, or call GWS/Odollo/Odoo.

## Turn 223 | 2026-06-15

Executed Plan 0017 with Slice 0017-A.

Implemented:

- Added `BusinessCardService.child_review_queue`.
- Added API route `GET /reviews/children`.
- Added CLI command `reviews children`.
- Added MCP tool `business_card_watchdog_child_reviews_list`.
- Added operator dashboard command/API/MCP map entries for the child review queue.
- Added synthetic multi-card coverage for service, CLI, API, and MCP child review list surfaces.
- Updated README and roadmap documentation for promoted child contact review.

Validation:

- `.venv/bin/python -m pytest tests/test_review_surface.py::test_child_review_queue_lists_promoted_child_contact_candidates tests/test_cli_surfaces.py::test_cli_child_reviews_lists_promoted_child_candidates tests/test_api.py::test_api_child_reviews_lists_promoted_child_candidates tests/test_mcp.py::test_mcp_child_reviews_lists_promoted_child_candidates tests/test_mcp.py::test_manifest_has_process_tool -q` passed with 5 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/cli.py src/business_card_watchdog/api.py src/business_card_watchdog/mcp.py tests/test_review_surface.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py` passed.
- `.venv/bin/python -m pytest -q` passed with 243 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This was read-only review surfacing. It did not process private SyncThing images, approve child contacts, route, enrich, dedupe, write sinks, execute command-copy text, run public-web search, call paid APIs, or call GWS/Odollo/Odoo.

## Turn 224 | 2026-06-15

Executed Plan 0018 with Slice 0018-A.

Implemented:

- Added `BusinessCardService.submit_child_review`.
- Added child review result state overlay to `BusinessCardService.child_review_queue`.
- Added CLI command `reviews child-review <candidate-id> --run-id <run-id>`.
- Added API route `POST /reviews/children/{candidate_id}`.
- Added MCP tool `business_card_watchdog_child_review_submit`.
- Added synthetic multi-card coverage for service, CLI, API, and MCP approval.
- Updated README and roadmap documentation for child review decisions.

Validation:

- `.venv/bin/python -m pytest tests/test_review_surface.py::test_child_review_approval_writes_reviewed_child_contact_artifact tests/test_cli_surfaces.py::test_cli_child_review_approves_promoted_child_candidate tests/test_api.py::test_api_child_review_approves_promoted_child_candidate tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_child_review_approves_promoted_child_candidate -q` passed with 5 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/cli.py src/business_card_watchdog/api.py src/business_card_watchdog/mcp.py tests/test_review_surface.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py` passed.
- `.venv/bin/python -m pytest -q` passed with 247 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This created local child review artifacts only. It did not process private SyncThing images, dedupe, route, enrich, write sinks, execute command-copy text, run public-web search, call paid APIs, or call GWS/Odollo/Odoo.

## Turn 225 | 2026-06-15

Executed Plan 0019 with Slice 0019-A.

Implemented:

- Added `BusinessCardService.child_route_prep_queue`.
- Added `BusinessCardService.prepare_child_route`.
- Added CLI commands `reviews child-route-prep-queue` and `reviews child-route-prep <candidate-id>`.
- Added API routes `GET /reviews/children/route-prep` and `POST /reviews/children/{candidate_id}/route-prep`.
- Added MCP tools `business_card_watchdog_child_route_prep_queue` and `business_card_watchdog_child_route_prepare`.
- Added synthetic multi-card coverage for service, CLI, API, and MCP route prep.
- Updated README and roadmap documentation for child route-prep decisions.

Validation:

- `.venv/bin/python -m pytest tests/test_review_surface.py::test_child_route_prep_writes_dry_run_lookup_and_sink_plans tests/test_cli_surfaces.py::test_cli_child_route_prep_writes_dry_run_plans tests/test_api.py::test_api_child_route_prep_writes_dry_run_plans tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_child_route_prep_writes_dry_run_plans -q` passed with 5 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/cli.py src/business_card_watchdog/api.py src/business_card_watchdog/mcp.py tests/test_review_surface.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py` passed.
- `.venv/bin/python -m pytest -q` passed with 251 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This created local dry-run child lookup and sink plan artifacts only. It did not process private SyncThing images, execute live lookup, dedupe, route to sinks, enrich, write contacts, execute command-copy text, run public-web search, call paid APIs, or call GWS/Odollo/Odoo.

## Turn 226 | 2026-06-15

Executed Plan 0020 with Slice 0020-A.

Implemented:

- Added `BusinessCardService.record_child_sink_lookup_result`.
- Added `BusinessCardService.assess_child_downstream_duplicates`.
- Added CLI commands `reviews child-lookup-result` and `reviews child-assess-duplicates`.
- Added API routes `POST /reviews/children/{candidate_id}/sink-lookup-result` and `POST /reviews/children/{candidate_id}/downstream-duplicate-assessment`.
- Added MCP tools `business_card_watchdog_child_sink_lookup_result` and `business_card_watchdog_child_downstream_duplicate_assessment`.
- Added synthetic multi-card coverage for service, CLI, API, and MCP child lookup evidence import plus duplicate assessment.
- Updated README and roadmap documentation for child lookup evidence and duplicate assessment.

Validation:

- `.venv/bin/python -m pytest tests/test_review_surface.py::test_child_lookup_result_and_duplicate_assessment_use_fixture_matches tests/test_cli_surfaces.py::test_cli_child_lookup_result_and_duplicate_assessment tests/test_api.py::test_api_child_lookup_result_and_duplicate_assessment tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_child_lookup_result_and_duplicate_assessment -q` passed with 5 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/cli.py src/business_card_watchdog/api.py src/business_card_watchdog/mcp.py tests/test_review_surface.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py` passed.
- `.venv/bin/python -m pytest -q` passed with 255 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This created local child lookup evidence and duplicate assessment artifacts only. It did not process private SyncThing images, execute live lookup, resolve duplicates, route to sinks, enrich, write contacts, execute command-copy text, run public-web search, call paid APIs, or call GWS/Odollo/Odoo.

## Turn 227 | 2026-06-15

Executed Plan 0021 with Slice 0021-A.

Implemented:

- Added `BusinessCardService.resolve_child_duplicate`.
- Added `BusinessCardService.child_sink_plan_gate`.
- Added CLI commands `reviews child-resolve-duplicate` and `reviews child-sink-plan-gate`.
- Added API routes `POST /reviews/children/{candidate_id}/duplicate-resolution` and `POST /reviews/children/{candidate_id}/sink-plan-gate`.
- Added MCP tools `business_card_watchdog_child_duplicate_resolution` and `business_card_watchdog_child_sink_plan_gate`.
- Added synthetic multi-card coverage for service, CLI, API, and MCP child duplicate resolution plus gate clearing.
- Updated README and roadmap documentation for child duplicate-resolution gates.

Validation:

- `.venv/bin/python -m pytest tests/test_review_surface.py::test_child_duplicate_resolution_clears_sink_plan_gate tests/test_cli_surfaces.py::test_cli_child_duplicate_resolution_clears_gate tests/test_api.py::test_api_child_duplicate_resolution_clears_gate tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_child_duplicate_resolution_clears_gate -q` passed with 5 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/cli.py src/business_card_watchdog/api.py src/business_card_watchdog/mcp.py tests/test_review_surface.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py` passed.
- `.venv/bin/python -m pytest -q` passed with 259 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This created local child duplicate resolution and gate artifacts only. It did not process private SyncThing images, execute live lookup, route to live sinks, enrich, write contacts, execute command-copy text, run public-web search, call paid APIs, or call GWS/Odollo/Odoo.

## Turn 228 | 2026-06-15

Executed Plan 0022 with Slice 0022-A.

Implemented:

- Added `BusinessCardService.child_sink_apply_preflight`.
- Added `BusinessCardService.child_selected_target_handoff`.
- Added CLI commands `reviews child-sink-apply-preflight` and `reviews child-selected-target-handoff`.
- Added API routes `POST /reviews/children/{candidate_id}/sink-apply-preflight` and `POST /reviews/children/{candidate_id}/selected-target-handoff`.
- Added MCP tools `business_card_watchdog_child_sink_apply_preflight` and `business_card_watchdog_child_selected_target_handoff`.
- Added synthetic multi-card coverage for service, CLI, API, and MCP child preflight plus selected-target handoff.
- Updated README and roadmap documentation for child preflight handoff packets.

Validation:

- `.venv/bin/python -m pytest tests/test_review_surface.py::test_child_sink_apply_preflight_and_selected_target_handoff tests/test_cli_surfaces.py::test_cli_child_sink_apply_preflight_and_handoff tests/test_api.py::test_api_child_sink_apply_preflight_and_handoff tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_child_sink_apply_preflight_and_handoff -q` passed with 5 tests.
- `.venv/bin/python -m pytest -q -x -vv` passed with 263 tests.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `uv build --out-dir dist` built source and wheel distributions.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This created local child apply preflight and selected-target handoff artifacts only. It did not create live selected targets, process private SyncThing images, execute live lookup, route to live sinks, enrich, write contacts, execute command-copy text, run public-web search, call paid APIs, or call GWS/Odollo/Odoo.

## Turn 229 | 2026-06-15

Executed Plan 0023 with Slice 0023-A.

Implemented:

- Added `BusinessCardService.validate_child_selected_target_response`.
- Added `BusinessCardService.child_selected_target_execution_checklist`.
- Added CLI commands `reviews child-validate-selected-target-response` and `reviews child-selected-target-execution-checklist`.
- Added API routes `POST /reviews/children/{candidate_id}/selected-target-response-validation` and `POST /reviews/children/{candidate_id}/selected-target-execution-checklist`.
- Added MCP tools `business_card_watchdog_child_selected_target_response_validation` and `business_card_watchdog_child_selected_target_execution_checklist`.
- Added synthetic multi-card coverage for service, CLI, API, and MCP child response validation plus no-live execution checklist.
- Updated README and roadmap documentation for child selected-target response/checklist packets.

Validation:

- `.venv/bin/python -m pytest tests/test_review_surface.py::test_child_selected_target_response_validation_and_checklist tests/test_cli_surfaces.py::test_cli_child_selected_target_response_validation_and_checklist tests/test_api.py::test_api_child_selected_target_response_validation_and_checklist tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_child_selected_target_response_validation_and_checklist -q` passed with 5 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/cli.py src/business_card_watchdog/api.py src/business_card_watchdog/mcp.py tests/test_review_surface.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py` passed.
- `.venv/bin/python -m pytest -q` passed with 267 tests.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `uv build --out-dir dist` built source and wheel distributions.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This created local child response validation and no-live execution checklist artifacts only. It did not create live selected targets, process private SyncThing images, execute live lookup, route to live sinks, enrich, write contacts, execute command-copy text, run public-web search, call paid APIs, or call GWS/Odollo/Odoo.

## Turn 230 | 2026-06-15

Executed Plan 0024 with Slice 0024-A.

Implemented:

- Added `BusinessCardService.child_selected_target_command_copy_packet`.
- Added CLI command `reviews child-selected-target-command-copy-packet`.
- Added API route `POST /reviews/children/{candidate_id}/selected-target-command-copy-packet`.
- Added MCP tool `business_card_watchdog_child_selected_target_command_copy_packet`.
- Added synthetic multi-card coverage for service, CLI, API, and MCP child command-copy acknowledgement behavior.
- Updated README and roadmap documentation for child no-live command-copy packets.

Validation:

- `.venv/bin/python -m pytest tests/test_review_surface.py::test_child_selected_target_response_validation_and_checklist tests/test_cli_surfaces.py::test_cli_child_selected_target_response_validation_and_checklist tests/test_api.py::test_api_child_selected_target_response_validation_and_checklist tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_child_selected_target_response_validation_and_checklist -q` passed with 5 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/cli.py src/business_card_watchdog/api.py src/business_card_watchdog/mcp.py tests/test_review_surface.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py` passed.
- `.venv/bin/python -m pytest -q` passed with 267 tests.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `uv build --out-dir dist` built source and wheel distributions.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This created local child command-copy packet artifacts only. It did not create live selected targets, return executable live commands, process private SyncThing images, execute live lookup, route to live sinks, enrich, write contacts, run public-web search, call paid APIs, or call GWS/Odollo/Odoo.

## Turn 231 | 2026-06-15

Executed Plan 0025 with Slice 0025-A.

Implemented:

- Added `BusinessCardService.child_selected_target_audit`.
- Added CLI command `reviews child-selected-target-audit`.
- Added API route `POST /reviews/children/{candidate_id}/selected-target-audit`.
- Added MCP tool `business_card_watchdog_child_selected_target_audit`.
- Added synthetic multi-card coverage for service, CLI, API, and MCP child selected-target audit and replacement/abandonment guard behavior.
- Updated README and roadmap documentation for child selected-target audit previews.

Validation:

- `.venv/bin/python -m pytest tests/test_review_surface.py::test_child_selected_target_response_validation_and_checklist tests/test_cli_surfaces.py::test_cli_child_selected_target_response_validation_and_checklist tests/test_api.py::test_api_child_selected_target_response_validation_and_checklist tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_child_selected_target_response_validation_and_checklist -q` passed with 5 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/cli.py src/business_card_watchdog/api.py src/business_card_watchdog/mcp.py tests/test_review_surface.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py` passed.
- `.venv/bin/python -m pytest -q` passed with 267 tests.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `uv build --out-dir dist` built source and wheel distributions.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This created local child selected-target audit preview artifacts only. It did not create, replace, or abandon selected targets; process private SyncThing images; execute live lookup; route to live sinks; enrich; write contacts; run public-web search; call paid APIs; or call GWS/Odollo/Odoo.

## Turn 232 | 2026-06-15

Executed Plan 0026 with Slice 0026-A.

Implemented:

- Added `BusinessCardService.abandon_child_selected_target`.
- Added `BusinessCardService.child_selected_target_replacement_reset`.
- Added CLI commands `reviews child-abandon-selected-target` and `reviews child-selected-target-replacement-reset`.
- Added API routes `POST /reviews/children/{candidate_id}/selected-target-abandonment` and `POST /reviews/children/{candidate_id}/selected-target-replacement-reset`.
- Added MCP tools `business_card_watchdog_child_selected_target_abandonment` and `business_card_watchdog_child_selected_target_replacement_reset`.
- Added synthetic multi-card coverage for service, CLI, API, and MCP child abandonment plus replacement reset behavior.
- Updated README and roadmap documentation for child selected-target abandonment/reset packets.

Validation:

- `.venv/bin/python -m pytest tests/test_review_surface.py::test_child_selected_target_response_validation_and_checklist tests/test_cli_surfaces.py::test_cli_child_selected_target_response_validation_and_checklist tests/test_api.py::test_api_child_selected_target_response_validation_and_checklist tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_child_selected_target_response_validation_and_checklist -q` passed with 5 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/cli.py src/business_card_watchdog/api.py src/business_card_watchdog/mcp.py tests/test_review_surface.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py` passed.
- `.venv/bin/python -m pytest -q` passed with 267 tests.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `uv build --out-dir dist` built source and wheel distributions.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This created local child selected-target abandonment and replacement reset artifacts only. It did not create, delete, replace, or mutate selected-target packets; process private SyncThing images; execute live lookup; route to live sinks; enrich; write contacts; run public-web search; call paid APIs; or call GWS/Odollo/Odoo.

## Turn 233 | 2026-06-15

Executed Plan 0027 with Slice 0027-A.

Implemented:

- Added `BusinessCardService.refresh_child_replacement_handoff`.
- Added CLI command `reviews child-replacement-handoff-refresh`.
- Added API route `POST /reviews/children/{candidate_id}/replacement-handoff-refresh`.
- Added MCP tool `business_card_watchdog_child_replacement_handoff_refresh`.
- Added local child selected-target staleness marker artifacts for replacement refresh.
- Added synthetic multi-card coverage for service, CLI, API, and MCP child replacement handoff refresh behavior.
- Updated README and roadmap documentation for child replacement handoff refresh packets.

Validation:

- `.venv/bin/python -m pytest tests/test_review_surface.py::test_child_selected_target_response_validation_and_checklist tests/test_cli_surfaces.py::test_cli_child_selected_target_response_validation_and_checklist tests/test_api.py::test_api_child_selected_target_response_validation_and_checklist tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_child_selected_target_response_validation_and_checklist -q` passed with 5 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/cli.py src/business_card_watchdog/api.py src/business_card_watchdog/mcp.py tests/test_review_surface.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py` passed.
- `.venv/bin/python -m pytest -q` passed with 267 tests.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `uv build --out-dir dist` built source and wheel distributions.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This created local child replacement handoff refresh and staleness marker artifacts only. It did not create selected targets; process private SyncThing images; execute live lookup; route to live sinks; enrich; write contacts; run public-web search; call paid APIs; or call GWS/Odollo/Odoo.

## Turn 234 | 2026-06-15

Executed Plan 0028 with Slice 0028-A.

Implemented:

- Added `BusinessCardService.validate_child_replacement_response`.
- Added CLI command `reviews child-validate-replacement-response`.
- Added API route `POST /reviews/children/{candidate_id}/replacement-response-validation`.
- Added MCP tool `business_card_watchdog_child_replacement_response_validation`.
- Added stale-marker enforcement before replacement response validation can become ready.
- Added synthetic multi-card coverage for service, CLI, API, and MCP child replacement response validation behavior.
- Updated README and roadmap documentation for child replacement response validation packets.

Validation:

- `.venv/bin/python -m pytest tests/test_review_surface.py::test_child_selected_target_response_validation_and_checklist tests/test_cli_surfaces.py::test_cli_child_selected_target_response_validation_and_checklist tests/test_api.py::test_api_child_selected_target_response_validation_and_checklist tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_child_selected_target_response_validation_and_checklist -q` passed with 5 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/cli.py src/business_card_watchdog/api.py src/business_card_watchdog/mcp.py tests/test_review_surface.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py` passed.
- `.venv/bin/python -m pytest -q` passed with 267 tests.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `uv build --out-dir dist` built source and wheel distributions.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This created local child replacement response validation artifacts only. It did not create selected targets; process private SyncThing images; execute live lookup; route to live sinks; enrich; write contacts; run public-web search; call paid APIs; or call GWS/Odollo/Odoo.

## Turn 235 | 2026-06-15

Executed Plan 0029 with Slice 0029-A.

Implemented:

- Added `BusinessCardService.child_replacement_execution_checklist`.
- Added `BusinessCardService.child_replacement_command_copy_packet`.
- Added CLI commands `reviews child-replacement-execution-checklist` and `reviews child-replacement-command-copy-packet`.
- Added API routes `POST /reviews/children/{candidate_id}/replacement-execution-checklist` and `POST /reviews/children/{candidate_id}/replacement-command-copy-packet`.
- Added MCP tools `business_card_watchdog_child_replacement_execution_checklist` and `business_card_watchdog_child_replacement_command_copy_packet`.
- Added acknowledgement gating for replacement command-copy packets.
- Added synthetic multi-card coverage for service, CLI, API, and MCP child replacement checklist/copy behavior.
- Updated README and roadmap documentation for child replacement checklist/copy packets.

Validation:

- `.venv/bin/python -m pytest tests/test_review_surface.py::test_child_selected_target_response_validation_and_checklist tests/test_cli_surfaces.py::test_cli_child_selected_target_response_validation_and_checklist tests/test_api.py::test_api_child_selected_target_response_validation_and_checklist tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_child_selected_target_response_validation_and_checklist -q` passed with 5 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/cli.py src/business_card_watchdog/api.py src/business_card_watchdog/mcp.py tests/test_review_surface.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py` passed.
- `.venv/bin/python -m pytest -q` passed with 267 tests.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `uv build --out-dir dist` built source and wheel distributions.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This created local child replacement checklist and command-copy artifacts only. It did not create selected targets; process private SyncThing images; execute live lookup; route to live sinks; enrich; write contacts; run public-web search; call paid APIs; or call GWS/Odollo/Odoo.

## Turn 236 | 2026-06-15

Executed Plan 0030 with Slice 0030-A.

Implemented:

- Added `BusinessCardService.child_replacement_closeout_status`.
- Added CLI command `reviews child-replacement-closeout-status`.
- Added API route `POST /reviews/children/{candidate_id}/replacement-closeout-status`.
- Added MCP tool `business_card_watchdog_child_replacement_closeout_status`.
- Added a local closeout/status rollup for stale predecessor artifacts and refreshed replacement packet readiness.
- Added synthetic multi-card coverage for service, CLI, API, and MCP child replacement closeout/status behavior.
- Updated README and roadmap documentation for child replacement closeout/status packets.

Validation:

- `.venv/bin/python -m pytest tests/test_review_surface.py::test_child_selected_target_response_validation_and_checklist tests/test_cli_surfaces.py::test_cli_child_selected_target_response_validation_and_checklist tests/test_api.py::test_api_child_selected_target_response_validation_and_checklist tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_child_selected_target_response_validation_and_checklist -q` passed with 5 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/cli.py src/business_card_watchdog/api.py src/business_card_watchdog/mcp.py tests/test_review_surface.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py` passed.
- `.venv/bin/python -m pytest -q` passed with 267 tests.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `uv build --out-dir dist` built source and wheel distributions.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This created local child replacement closeout/status artifacts only. It did not create selected targets; process private SyncThing images; execute live lookup; route to live sinks; enrich; write contacts; run public-web search; call paid APIs; or call GWS/Odollo/Odoo.

## Turn 237 | 2026-06-15

Executed Plan 0031 with Slice 0031-A.

Implemented:

- Added `child_replacement_closeout_status` artifact visibility to review bundles.
- Added per-entry `child_replacement_status` summaries.
- Added `by_child_replacement_state` review bundle grouping.
- Added operator dashboard child replacement summary sourced from review bundle data.
- Added review HTML and workbook columns for child replacement closeout state.
- Added synthetic multi-card coverage for service, CLI, API, and MCP visibility behavior.
- Updated README and roadmap documentation for child replacement rollup visibility.

Validation:

- `.venv/bin/python -m pytest tests/test_review_surface.py::test_child_selected_target_response_validation_and_checklist tests/test_cli_surfaces.py::test_cli_child_selected_target_response_validation_and_checklist tests/test_api.py::test_api_child_selected_target_response_validation_and_checklist tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_child_selected_target_response_validation_and_checklist -q` passed with 5 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py tests/test_review_surface.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py` passed.
- `.venv/bin/python -m pytest -q` passed with 267 tests.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `uv build --out-dir dist` built source and wheel distributions.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This exposed existing no-live child replacement closeout state through review surfaces only. It did not create selected targets; process private SyncThing images; execute live lookup; route to live sinks; enrich; write contacts; run public-web search; call paid APIs; or call GWS/Odollo/Odoo.

## Turn 238 | 2026-06-15

Executed Plan 0032 with Slice 0032-A.

Implemented:

- Added `BusinessCardService.child_replacement_readiness_drill`.
- Added CLI command `drills child-replacement-readiness`.
- Added API route `POST /drills/child-replacement-readiness`.
- Added MCP tool `business_card_watchdog_child_replacement_readiness_drill`.
- Added operator dashboard CLI/API/MCP command references for the drill.
- Added synthetic service, CLI, API, and MCP coverage for child replacement stale/readiness sample outputs.
- Updated README and roadmap documentation for the child replacement readiness drill.

Validation:

- `.venv/bin/python -m pytest tests/test_review_surface.py::test_service_child_replacement_readiness_drill_exports_operator_samples tests/test_cli_surfaces.py::test_cli_child_replacement_readiness_drill_exports_operator_samples tests/test_api.py::test_api_child_replacement_readiness_drill_exports_operator_samples tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_child_replacement_readiness_drill_exports_operator_samples -q` passed with 5 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/cli.py src/business_card_watchdog/api.py src/business_card_watchdog/mcp.py tests/test_review_surface.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py` passed.
- `.venv/bin/python -m pytest -q` passed with 271 tests.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `uv build --out-dir dist` built source and wheel distributions.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This created synthetic child replacement readiness sample outputs only. It did not create selected targets; process private SyncThing images; execute live lookup; route to live sinks; enrich; write contacts; run public-web search; call paid APIs; or call GWS/Odollo/Odoo.

## Turn 239 | 2026-06-15

Executed Plan 0033 with Slice 0033-A.

Implemented:

- Added `live_pilot_rehearsal_sample_output.md` generation to `drills live-pilot-rehearsal`.
- Added `sample_outputs.live_pilot_rehearsal_markdown_path` to the drill payload.
- Added `live_pilot_rehearsal_sample_output` as a run artifact kind.
- Added CLI text output for the sample path.
- Added `docs/operations/live-pilot-sample-output.md`.
- Updated README and roadmap documentation for live-pilot sample output.
- Added service, CLI, API, and MCP coverage for sample output visibility and redaction.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_live_pilot_rehearsal_drill_reaches_command_copy_gate tests/test_cli_surfaces.py::test_cli_live_pilot_rehearsal_drill_reaches_command_copy_gate tests/test_api.py::test_api_live_pilot_rehearsal_drill_reaches_command_copy_gate tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 5 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/cli.py tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py` passed.
- `.venv/bin/python -m pytest -q` passed with 271 tests.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `rg -n "live-pilot-sample-output|live_pilot_rehearsal_sample_output|Live Pilot Rehearsal Sample Output|sample_outputs" README.md docs src tests` passed.
- `uv build --out-dir dist` built source and wheel distributions.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This created synthetic live-pilot rehearsal sample output only. It did not process private SyncThing images; run public-web search; call paid enrichment; execute live lookup/write/readback; or write Google Contacts, Odoo, or Odollo records.

## Turn 240 | 2026-06-15

Executed Plan 0034 with Slice 0034-A.

Implemented:

- Added `child_replacement_readiness_sample_output.md` generation to `drills child-replacement-readiness`.
- Added `sample_outputs.child_replacement_readiness_markdown_path` to the drill payload.
- Added `child_replacement_readiness_sample_output` as a run artifact kind.
- Added CLI text output for the sample path.
- Added `docs/operations/child-replacement-sample-output.md`.
- Updated README and roadmap documentation for child replacement sample output.
- Added service, CLI, API, and MCP coverage for sample output visibility and redaction.

Validation:

- `.venv/bin/python -m pytest tests/test_review_surface.py::test_service_child_replacement_readiness_drill_exports_operator_samples tests/test_cli_surfaces.py::test_cli_child_replacement_readiness_drill_exports_operator_samples tests/test_api.py::test_api_child_replacement_readiness_drill_exports_operator_samples tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_child_replacement_readiness_drill_exports_operator_samples -q` passed with 5 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/cli.py tests/test_review_surface.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py` passed.
- `.venv/bin/python -m pytest -q` passed with 271 tests.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `rg -n "child-replacement-sample-output|child_replacement_readiness_sample_output|Child Replacement Readiness Sample Output|child_replacement_readiness_markdown_path" README.md docs src tests` passed.
- `uv build --out-dir dist` built source and wheel distributions.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This created synthetic child replacement readiness sample output only. It did not process private SyncThing images; run public-web search; call paid enrichment; execute live lookup/write/readback; or write Google Contacts, Odoo, or Odollo records.

## Turn 241 | 2026-06-15

Executed Plan 0035 with Slice 0035-A.

Implemented:

- Added `BusinessCardService.offline_pilot_gap_audit`.
- Added CLI command `offline-pilot-gap-audit`.
- Added API route `GET /offline-pilot-gap-audit`.
- Added MCP tool `business_card_watchdog_offline_pilot_gap_audit`.
- Added status command and safe next action visibility for the audit.
- Added service, CLI, API, and MCP coverage for offline pilot gap audit visibility.
- Updated README and roadmap documentation for offline pilot gap auditing.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_offline_pilot_gap_audit_reports_remaining_live_boundaries tests/test_cli_surfaces.py::test_cli_status_reports_command_map_text_and_json tests/test_cli_surfaces.py::test_cli_offline_pilot_gap_audit_reports_remaining_boundaries tests/test_api.py::test_api_offline_pilot_gap_audit_reports_remaining_boundaries tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_offline_pilot_gap_audit_reports_remaining_boundaries -q` passed with 6 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/cli.py src/business_card_watchdog/api.py src/business_card_watchdog/mcp.py tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py` passed.
- `.venv/bin/python -m pytest -q` passed with 275 tests.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `rg -n "offline-pilot-gap-audit|offline_pilot_gap_audit|offline-pilot-gap|Offline pilot gap audit|business_card_watchdog_offline_pilot_gap_audit" README.md ROADMAP.md RUNBOOK.md docs src tests` passed.
- `uv build --out-dir dist` built source and wheel distributions.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This inspected offline docs and local command surfaces only. It did not process private SyncThing images; run public-web search; call paid enrichment; execute live lookup/write/readback; or write Google Contacts, Odoo, or Odollo records.

## Turn 242 | 2026-06-15

Executed Plan 0036 with Slice 0036-A.

Implemented:

- Added `BusinessCardService.operator_selected_live_smoke_preflight`.
- Added CLI command `operator-selected-live-smoke-preflight`.
- Added API route `POST /operator-selected-live-smoke-preflight`.
- Added MCP tool `business_card_watchdog_operator_selected_live_smoke_preflight`.
- Added status command and safe next action visibility for the preflight.
- Updated README and roadmap documentation for the operator-selected live smoke preflight.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_operator_selected_live_smoke_preflight_reports_blocked_boundary tests/test_cli_surfaces.py::test_cli_status_reports_command_map_text_and_json tests/test_cli_surfaces.py::test_cli_operator_selected_live_smoke_preflight_reports_blocked_boundary tests/test_api.py::test_api_operator_selected_live_smoke_preflight_reports_blocked_boundary tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_operator_selected_live_smoke_preflight_reports_blocked_boundary -q` passed with 6 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/cli.py src/business_card_watchdog/api.py src/business_card_watchdog/mcp.py tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py` passed.
- `.venv/bin/python -m pytest -q` passed with 279 tests.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `rg -n "operator-selected-live-smoke-preflight|operator_selected_live_smoke_preflight|Operator-selected live smoke preflight|business_card_watchdog_operator_selected_live_smoke_preflight" README.md ROADMAP.md RUNBOOK.md docs src tests` passed.
- `uv build --out-dir dist` built source and wheel distributions.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This composed existing no-live readiness reports only. It did not process private SyncThing images; run public-web search; call paid enrichment; create `selected_live_target.json`; execute live lookup/write/readback; or write Google Contacts, Odoo, or Odollo records.

## Turn 243 | 2026-06-15

Executed Plan 0037 with Slice 0037-A.

Implemented:

- Added `operator_selected_live_smoke_preflight_sample_output.md` generation to `drills live-pilot-rehearsal`.
- Added `sample_outputs.operator_selected_live_smoke_preflight_markdown_path` to the drill payload.
- Added `operator_selected_live_smoke_preflight_sample_output` as a run artifact kind.
- Added `docs/operations/operator-selected-live-smoke-preflight-sample-output.md`.
- Updated README, roadmap, and live-pilot sample-output docs.
- Added service, CLI, API, and MCP coverage for sample output visibility.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_live_pilot_rehearsal_drill_reaches_command_copy_gate tests/test_cli_surfaces.py::test_cli_live_pilot_rehearsal_drill_reaches_command_copy_gate tests/test_api.py::test_api_live_pilot_rehearsal_drill_reaches_command_copy_gate tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 5 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py` passed.
- `.venv/bin/python -m pytest -q` passed with 279 tests.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `rg -n "operator-selected-live-smoke-preflight-sample-output|operator_selected_live_smoke_preflight_sample_output|operator_selected_live_smoke_preflight_markdown_path|Operator-Selected Live Smoke Preflight Sample Output" README.md ROADMAP.md RUNBOOK.md docs src tests` passed.
- `uv build --out-dir dist` built source and wheel distributions.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This created synthetic preflight sample output only. It did not process private SyncThing images; run public-web search; call paid enrichment; execute live lookup/write/readback; or write Google Contacts, Odoo, or Odollo records.

## Turn 244 | 2026-06-15

Executed Plan 0038 with Slice 0038-A.

Implemented:

- Added `BusinessCardService.watch_backlog_preflight`.
- Added CLI command `watch-backlog-preflight`.
- Added API route `POST /watch/backlog-preflight`.
- Added MCP tool `business_card_watchdog_watch_backlog_preflight`.
- Added status command and safe next action visibility for the preflight.
- Updated README and roadmap documentation for the private-source watch boundary.
- Added service, CLI, API, and MCP coverage for redacted backlog preflight payloads.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_watch_backlog_preflight_redacts_private_source_paths tests/test_service.py::test_service_watch_backlog_preflight_can_preview_without_writing tests/test_watcher.py::test_watch_backlog_preflight_cli_outputs_redacted_counts tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_watch_backlog_preflight_redacts_private_source_paths -q` passed with 6 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/cli.py src/business_card_watchdog/api.py src/business_card_watchdog/mcp.py tests/test_service.py tests/test_watcher.py tests/test_api.py tests/test_mcp.py` passed.
- `.venv/bin/python -m pytest -q` passed with 283 tests.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `rg -n "watch-backlog-preflight|watch_backlog_preflight|Watch backlog preflight|business_card_watchdog_watch_backlog_preflight" README.md ROADMAP.md RUNBOOK.md docs src tests` passed.
- `uv build --out-dir dist` built source and wheel distributions.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `codegraph sync && codegraph status` passed; index is up to date.
- `.venv/bin/bcw watch-backlog-preflight --no-write --json` passed against the user config and reported `$fsr:sync_phone` as one redacted input with 5 backlog items, 0 unsettled items, no last error, no runtime artifact write, no OCR, no file processing, and no network calls.

Safety:

- This inspected configured watcher counts only and redacted watched input paths and filenames from the new preflight payload. It did not process private SyncThing images; run OCR/App Intelligence; run public-web search; call paid enrichment; execute live lookup/write/readback; or write Google Contacts, Odoo, or Odollo records.

## Turn 245 | 2026-06-15

Executed Plan 0039 with Slice 0039-A.

Implemented:

- Added `BusinessCardService.watch_dry_run_selection_handoff`.
- Added `BusinessCardService.validate_watch_dry_run_operator_response`.
- Added `BusinessCardService.watch_dry_run_command_copy_packet`.
- Added CLI commands `watch-dry-run-selection-handoff`, `watch-dry-run-validate-response`, and `watch-dry-run-command-copy-packet`.
- Added API routes under `/watch/dry-run-*` for handoff, validation, and command-copy packet generation.
- Added MCP tools for the same handoff, validation, and command-copy packet.
- Updated backlog preflight safe next actions to point at the selection handoff before the actual private-source dry-run command.
- Updated README and ROADMAP for the new private-source watch boundary.
- Added service, CLI, API, and MCP coverage for the handoff flow.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_watch_backlog_preflight_redacts_private_source_paths tests/test_service.py::test_service_watch_dry_run_selection_handoff_validates_response_and_command_copy tests/test_service.py::test_service_watch_dry_run_command_copy_blocks_without_acknowledgement tests/test_watcher.py::test_watch_backlog_preflight_cli_outputs_redacted_counts tests/test_watcher.py::test_watch_dry_run_selection_cli_validates_and_builds_command_copy tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_watch_backlog_preflight_redacts_private_source_paths tests/test_mcp.py::test_mcp_watch_dry_run_selection_flow_returns_command_copy -q` passed with 9 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/cli.py src/business_card_watchdog/api.py src/business_card_watchdog/mcp.py tests/test_service.py tests/test_watcher.py tests/test_api.py tests/test_mcp.py tests/test_cli_surfaces.py` passed.
- `.venv/bin/python -m pytest -q` passed with 287 tests.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `rg -n "watch-dry-run-selection-handoff|watch_dry_run_selection_handoff|watch-dry-run-validate-response|watch_dry_run_command_copy|business_card_watchdog_watch_dry_run" README.md ROADMAP.md RUNBOOK.md docs src tests` passed.
- `uv build --out-dir dist` built source and wheel distributions.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `codegraph sync && codegraph status` passed; index is up to date.
- `.venv/bin/bcw watch-dry-run-selection-handoff --no-write --json` passed against the user config and reported `$fsr:sync_phone` as one redacted input with 5 backlog items, 0 unsettled items, no runtime artifact write, no OCR, no file processing, and no network calls.

Safety:

- This created a no-processing operator-response and command-copy handoff only. It did not process private SyncThing images; run OCR/App Intelligence; run public-web search; call paid enrichment; execute live lookup/write/readback; or write Google Contacts, Odoo, or Odollo records.

## Turn 246 | 2026-06-15

Executed Plan 0040 with Slice 0040-A.

Implemented:

- Added `BusinessCardService.watch_dry_run_selection_drill`.
- Added CLI `bcw drills watch-dry-run-selection`.
- Added API `POST /drills/watch-dry-run-selection`.
- Added MCP tool `business_card_watchdog_watch_dry_run_selection_drill`.
- Added fixture markdown sample output export for the watch dry-run selection workflow.
- Fixed zero-second watcher settle handling so `settle_seconds = 0.0` means immediate settlement in status and scan paths.
- Updated README and ROADMAP for the fixture watch dry-run selection sample-output drill.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_watch_dry_run_selection_drill_exports_sample_output tests/test_cli_surfaces.py::test_cli_watch_dry_run_selection_drill_exports_sample_output tests/test_api.py::test_api_watch_dry_run_selection_drill_exports_sample_output tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_watch_dry_run_selection_drill_exports_sample_output -q` passed with 5 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/cli.py src/business_card_watchdog/api.py src/business_card_watchdog/mcp.py tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py` passed.
- `.venv/bin/python -m pytest -q` passed with 291 tests.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `rg -n "watch-dry-run-selection|watch_dry_run_selection|Watch Dry-Run Selection|business_card_watchdog_watch_dry_run_selection_drill|Plan 0040" README.md ROADMAP.md RUNBOOK.md docs src tests` passed.
- `uv build --out-dir dist` built source and wheel distributions.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `codegraph sync && codegraph status` passed; index is up to date.
- `.venv/bin/bcw drills watch-dry-run-selection --json` passed with `state=passed`, `command_copy_ready=true`, one synthetic fixture backlog item, zero files processed, zero OCR attempts, zero writes, and zero network calls.

Safety:

- This used a synthetic fixture watch source under the cache directory. It did not process configured SyncThing/private watch inputs; run OCR/App Intelligence; run public-web search; call paid enrichment; execute live lookup/write/readback; or write Google Contacts, Odoo, or Odollo records.

## Turn 247 | 2026-06-15

Executed Plan 0041 with Slice 0041-A.

Implemented:

- Added `BusinessCardService.watch_dry_run_execution_drill`.
- Added CLI `bcw drills watch-dry-run-execution`.
- Added API `POST /drills/watch-dry-run-execution`.
- Added MCP tool `business_card_watchdog_watch_dry_run_execution_drill`.
- Added fixture markdown sample output export for watched dry-run execution.
- Updated README and ROADMAP for the new synthetic watched execution proof.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_watch_dry_run_execution_drill_runs_real_dry_pipeline tests/test_cli_surfaces.py::test_cli_watch_dry_run_execution_drill_runs_real_dry_pipeline tests/test_api.py::test_api_watch_dry_run_execution_drill_runs_real_dry_pipeline tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_watch_dry_run_execution_drill_runs_real_dry_pipeline -q` passed with 5 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/cli.py src/business_card_watchdog/api.py src/business_card_watchdog/mcp.py tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py` passed.
- `.venv/bin/python -m pytest -q` passed with 295 tests.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `rg -n "watch-dry-run-execution|watch_dry_run_execution|Watch Dry-Run Execution|business_card_watchdog_watch_dry_run_execution_drill|Plan 0041" README.md ROADMAP.md RUNBOOK.md docs src tests` passed.
- `uv build --out-dir dist` built source and wheel distributions.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `codegraph sync && codegraph status` passed; index is up to date.
- `.venv/bin/bcw drills watch-dry-run-execution --json` passed with `state=passed`, one synthetic fixture file processed, a completed dry-run batch run, OCR/contact/review/sink payload artifacts, zero duplicate processing after restart, zero writes, and zero network calls.

Safety:

- This used a synthetic fixture watch source under the cache directory. It did not process configured SyncThing/private watch inputs; run public-web search; call paid enrichment; execute live lookup/write/readback; or write Google Contacts, Odoo, or Odollo records.

## Turn 248 | 2026-06-15

Executed Plan 0042 with Slice 0042-A.

Implemented:

- Added `BusinessCardService.watch_dry_run_readiness`.
- Added CLI `bcw watch-dry-run-readiness`.
- Added API `POST /watch/dry-run-readiness`.
- Added MCP tool `business_card_watchdog_watch_dry_run_readiness`.
- Updated README and ROADMAP for the configured-source no-processing readiness packet.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_watch_dry_run_readiness_redacts_private_source_and_blocks_command tests/test_watcher.py::test_watch_dry_run_readiness_cli_redacts_and_blocks_command_copy tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_watch_dry_run_selection_flow_returns_command_copy -q` passed with 5 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/cli.py src/business_card_watchdog/api.py src/business_card_watchdog/mcp.py tests/test_service.py tests/test_watcher.py tests/test_api.py tests/test_mcp.py` passed.
- `.venv/bin/python -m pytest -q` passed with 297 tests.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `rg -n "watch-dry-run-readiness|watch_dry_run_readiness|Watch dry-run readiness|business_card_watchdog_watch_dry_run_readiness|Plan 0042" README.md ROADMAP.md RUNBOOK.md docs src tests` passed.
- `uv build --out-dir dist` built source and wheel distributions.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `codegraph sync && codegraph status` passed; index is up to date.
- `.venv/bin/bcw watch-dry-run-readiness --no-write --json` passed against the configured watcher and reported `$fsr:sync_phone` as one redacted input with 5 backlog items, 0 unsettled items, no runtime artifact write, no copyable command, no OCR, no file processing, and no network calls.

Safety:

- This created a no-processing readiness packet only. It did not process configured SyncThing/private watch inputs; run OCR/App Intelligence; run public-web search; call paid enrichment; execute live lookup/write/readback; or write Google Contacts, Odoo, or Odollo records.

## Turn 249 | 2026-06-15

Executed Plan 0043 with Slice 0043-A.

Implemented:

- Added `BusinessCardService.dry_run_closeout`.
- Added CLI `bcw runs dry-run-closeout`.
- Added API `GET /runs/{run_id}/dry-run-closeout`.
- Added MCP tool `business_card_watchdog_dry_run_closeout`.
- Updated README and ROADMAP for the post-dry-run closeout checkpoint.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_dry_run_closeout_audits_completed_dry_run tests/test_cli_surfaces.py::test_cli_runs_dry_run_closeout_reports_no_live tests/test_api.py::test_api_run_dry_run_closeout_reports_no_live tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_dry_run_closeout_reports_no_live -q` passed with 5 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/cli.py src/business_card_watchdog/api.py src/business_card_watchdog/mcp.py tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py` passed.
- `.venv/bin/python -m pytest -q` passed with 301 tests.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `rg -n "dry-run-closeout|dry_run_closeout|Dry-run closeout|business_card_watchdog_dry_run_closeout|Plan 0043" README.md ROADMAP.md RUNBOOK.md docs src tests` passed.
- `uv build --out-dir dist` built source and wheel distributions.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `codegraph sync && codegraph status` passed; index is up to date.
- `.venv/bin/bcw drills watch-dry-run-execution --json` passed with a synthetic completed dry-run batch run, one fixture file processed, zero writes, and zero network calls.
- `.venv/bin/bcw --config <temp-fixture-config> runs dry-run-closeout 2026-06-15T13-04-42+00-00 --no-write --json` passed with `state=ready_for_review_and_routing`, zero live event types, zero live artifact kinds, zero writes, and zero network calls.

Safety:

- This added a local-ledger dry-run closeout only. It did not process configured SyncThing/private watch inputs; run public-web search; call paid enrichment; execute live lookup/write/readback; or write Google Contacts, Odoo, or Odollo records.

## Turn 250 | 2026-06-15

Executed Plan 0044 with Slice 0044-A.

Implemented:

- Added `BusinessCardService.dry_run_review_handoff`.
- Added CLI `bcw runs dry-run-review-handoff`.
- Added API `GET /runs/{run_id}/dry-run-review-handoff`.
- Added MCP tool `business_card_watchdog_dry_run_review_handoff`.
- Updated README and ROADMAP for the post-closeout review/routing handoff.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_dry_run_review_handoff_summarizes_safe_next_steps tests/test_cli_surfaces.py::test_cli_runs_dry_run_review_handoff_reports_safe_next_steps tests/test_api.py::test_api_run_dry_run_review_handoff_reports_safe_next_steps tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_dry_run_review_handoff_reports_safe_next_steps -q` passed with 5 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/cli.py src/business_card_watchdog/api.py src/business_card_watchdog/mcp.py tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py` passed.
- `.venv/bin/python -m pytest -q` passed with 305 tests.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `rg -n "dry-run-review-handoff|dry_run_review_handoff|Dry-run review handoff|business_card_watchdog_dry_run_review_handoff|Plan 0044" README.md ROADMAP.md RUNBOOK.md docs src tests` passed.
- `uv build --out-dir dist` built source and wheel distributions.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `codegraph sync && codegraph status` passed; index is up to date.
- `.venv/bin/bcw --config <temp-fixture-config> runs dry-run-review-handoff 2026-06-15T13-15-20+00-00 --no-write --json` passed with `state=ready_for_safe_agent_loop`, one safe `plan_sink_lookup`, zero writes, zero network calls, and no live sink calls.

Safety:

- This added a local-ledger dry-run review handoff only. It did not process configured SyncThing/private watch inputs; run OCR/App Intelligence; run public-web search; call paid enrichment; execute live lookup/write/readback; or write Google Contacts, Odoo, or Odollo records.

## Turn 251 | 2026-06-15

Executed Plan 0045 with Slice 0045-A.

Implemented:

- Added `BusinessCardService.dry_run_safe_loop`.
- Added CLI `bcw runs dry-run-safe-loop`.
- Added API `GET /runs/{run_id}/dry-run-safe-loop`.
- Added MCP tool `business_card_watchdog_dry_run_safe_loop`.
- Updated README and ROADMAP for the gated bounded safe-loop executor.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_dry_run_safe_loop_executes_bounded_safe_actions tests/test_cli_surfaces.py::test_cli_runs_dry_run_safe_loop_executes_bounded_safe_actions tests/test_api.py::test_api_run_dry_run_safe_loop_executes_bounded_safe_actions tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_dry_run_safe_loop_executes_bounded_safe_actions -q` passed with 5 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/cli.py src/business_card_watchdog/api.py src/business_card_watchdog/mcp.py tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py` passed.
- `.venv/bin/python -m pytest -q` passed with 309 tests.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `rg -n "dry-run-safe-loop|dry_run_safe_loop|Dry-run safe loop|business_card_watchdog_dry_run_safe_loop|Plan 0045" README.md ROADMAP.md RUNBOOK.md docs src tests` passed.
- `uv build --out-dir dist` built source and wheel distributions.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `codegraph sync && codegraph status` passed; index is up to date.
- `.venv/bin/bcw --config <temp-fixture-config> runs dry-run-safe-loop 2026-06-15T13-22-52+00-00 --limit 3 --no-write --json` passed with `state=safe_loop_executed`, three safe actions, zero writes, zero network calls, and no live sink calls.

Safety:

- This added a gated local-ledger safe-loop executor only. It did not process configured SyncThing/private watch inputs; run OCR/App Intelligence beyond the synthetic fixture drill; run public-web search; call paid enrichment; execute live lookup/write/readback; or write Google Contacts, Odoo, or Odollo records.

## Turn 252 | 2026-06-15

Executed Plan 0046 with Slice 0046-A.

Implemented:

- Added `BusinessCardService.review_route_readiness`.
- Added CLI `bcw runs review-route-readiness`.
- Added API `GET /runs/{run_id}/review-route-readiness`.
- Added MCP tool `business_card_watchdog_review_route_readiness`.
- Updated README and ROADMAP for the run-level review-route readiness checkpoint.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_review_route_readiness_summarizes_review_and_route_state tests/test_cli_surfaces.py::test_cli_runs_review_route_readiness_reports_route_state tests/test_api.py::test_api_run_review_route_readiness_reports_route_state tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_review_route_readiness_reports_route_state -q` passed with 5 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/cli.py src/business_card_watchdog/api.py src/business_card_watchdog/mcp.py tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py` passed.
- `.venv/bin/python -m pytest -q` passed with 313 tests.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `rg -n "review-route-readiness|review_route_readiness|Review-route readiness|business_card_watchdog_review_route_readiness|Plan 0046" README.md ROADMAP.md RUNBOOK.md docs src tests` passed.
- `uv build --out-dir dist` built source and wheel distributions.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `codegraph sync && codegraph status` passed; index is up to date.
- `.venv/bin/bcw drills watch-dry-run-execution --json` passed with one synthetic fixture file processed through a completed dry-run batch and no writes or network calls.
- `.venv/bin/bcw --config <temp-fixture-config> runs review-route-readiness 2026-06-15T13-34-46+00-00 --no-write --json` passed with `state=ready_for_safe_agent_loop`, one route-ready job, one safe `plan_sink_lookup`, zero writes, zero network calls, and no live sink calls.

Safety:

- This added a local-ledger review-route readiness report only. It did not process configured SyncThing/private watch inputs; run OCR/App Intelligence; run public-web search; call paid enrichment; execute live lookup/write/readback; or write Google Contacts, Odoo, or Odollo records.

## Turn 253 | 2026-06-15

Executed Plan 0047 with Slice 0047-A.

Implemented:

- Added `BusinessCardService.lookup_selection_packet`.
- Added CLI `bcw runs lookup-selection-packet`.
- Added API `POST /runs/{run_id}/lookup-selection-packet`.
- Added MCP tool `business_card_watchdog_lookup_selection_packet`.
- Updated README and ROADMAP for the preview-only lookup selection packet boundary.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_lookup_selection_packet_selects_route_ready_job_without_live_calls tests/test_cli_surfaces.py::test_cli_runs_lookup_selection_packet_reports_selected_candidate tests/test_api.py::test_api_run_lookup_selection_packet_reports_selected_candidate tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_lookup_selection_packet_reports_selected_candidate -q` passed with 5 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/cli.py src/business_card_watchdog/api.py src/business_card_watchdog/mcp.py tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py` passed.
- `.venv/bin/python -m pytest -q` passed with 317 tests.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `rg -n "lookup-selection-packet|lookup_selection_packet|Lookup selection packet|business_card_watchdog_lookup_selection_packet|Plan 0047" README.md ROADMAP.md RUNBOOK.md docs src tests` passed.
- `uv build --out-dir dist` built source and wheel distributions.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `codegraph sync && codegraph status` passed; index is up to date.
- `.venv/bin/bcw drills watch-dry-run-execution --json` passed with one synthetic fixture file processed through a completed dry-run batch and no writes or network calls.
- `.venv/bin/bcw --config <temp-fixture-config> runs lookup-selection-packet 2026-06-15T13-44-18+00-00 --operator fixture-smoke --sink google_contacts --no-write --json` passed with `state=packet_blocked`, one route-ready job, one selected lookup packet, zero writes, zero network calls, no selected-target creation, and no live sink calls.

Safety:

- This added a run-level lookup selection packet only. It did not create `selected_live_target.json`; process configured SyncThing/private watch inputs; run OCR/App Intelligence; run public-web search; call paid enrichment; execute live lookup/write/readback; or write Google Contacts, Odoo, or Odollo records.

## Turn 254 | 2026-06-15

Executed Plan 0048 with Slice 0048-A.

Implemented:

- Added `BusinessCardService.close_lookup_prerequisites`.
- Added CLI `bcw runs close-lookup-prerequisites`.
- Added API `POST /runs/{run_id}/close-lookup-prerequisites`.
- Added MCP tool `business_card_watchdog_close_lookup_prerequisites`.
- Updated README and ROADMAP for the no-live lookup prerequisite closer.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_close_lookup_prerequisites_executes_only_lookup_safe_actions tests/test_cli_surfaces.py::test_cli_runs_close_lookup_prerequisites_executes_lookup_steps tests/test_api.py::test_api_run_close_lookup_prerequisites_executes_lookup_steps tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_close_lookup_prerequisites_executes_lookup_steps -q` passed with 5 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/cli.py src/business_card_watchdog/api.py src/business_card_watchdog/mcp.py tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py` passed.
- `.venv/bin/python -m pytest -q` passed with 321 tests.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `rg -n "close-lookup-prerequisites|close_lookup_prerequisites|Close lookup prerequisites|business_card_watchdog_close_lookup_prerequisites|Plan 0048" README.md ROADMAP.md RUNBOOK.md docs src tests` passed.
- `uv build --out-dir dist` built source and wheel distributions.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `codegraph sync && codegraph status` passed; index is up to date.
- `.venv/bin/bcw drills watch-dry-run-execution --json` passed with one synthetic fixture file processed through a completed dry-run batch and no writes or network calls.
- Synthetic CLI close-lookup smoke passed with `state=lookup_prerequisites_advanced`, `executed_count=4`, remaining missing requirement `live_lookup_readiness_ready`, zero writes, zero network calls, no selected-target creation, and no runtime artifact write under `--no-write`.

Safety:

- This added a local lookup prerequisite closer only. It did not approve contact review; create `selected_live_target.json`; process configured SyncThing/private watch inputs; run OCR/App Intelligence; run public-web search; call paid enrichment; execute live lookup/write/readback; or write Google Contacts, Odoo, or Odollo records.

## Turn 255 | 2026-06-15

Executed Plan 0049 with Slice 0049-A.

Implemented:

- Added `BusinessCardService.selected_target_approval_boundary`.
- Added CLI `bcw runs selected-target-approval-boundary`.
- Added API `POST /runs/{run_id}/selected-target-approval-boundary`.
- Added MCP tool `business_card_watchdog_selected_target_approval_boundary`.
- Updated README and ROADMAP for the no-live selected-target approval boundary packet.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_selected_target_approval_boundary_previews_explicit_selection tests/test_cli_surfaces.py::test_cli_runs_selected_target_approval_boundary_previews_selection tests/test_api.py::test_api_run_selected_target_approval_boundary_previews_selection tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_selected_target_approval_boundary_previews_selection -q` passed with 5 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/cli.py src/business_card_watchdog/api.py src/business_card_watchdog/mcp.py tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py` passed.
- `.venv/bin/python -m pytest -q` passed with 325 tests.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `rg -n "selected-target-approval-boundary|selected_target_approval_boundary|Selected-target approval boundary|business_card_watchdog_selected_target_approval_boundary|Plan 0049" README.md ROADMAP.md RUNBOOK.md docs src tests` passed.
- `uv build --out-dir dist` built source and wheel distributions.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `codegraph sync && codegraph status` passed; index is up to date.
- `.venv/bin/bcw drills watch-dry-run-execution --json` passed with one synthetic fixture file processed through a completed dry-run batch and no writes or network calls.
- Synthetic CLI selected-target approval boundary smoke passed with `state=ready_for_explicit_selected_target_creation`, validation state `ready_to_select_live_target`, preflight state `ready_to_create_selected_target`, preview state `ready`, zero writes, zero network calls, no selected-target creation, and no runtime artifact write under `--no-write`.

Safety:

- This added a local selected-target approval boundary packet only. It did not create `selected_live_target.json`; process configured SyncThing/private watch inputs; run OCR/App Intelligence; run public-web search; call paid enrichment; execute live lookup/write/readback; or write Google Contacts, Odoo, or Odollo records.

## Turn 256 | 2026-06-15

Executed Plan 0050 with Slice 0050-A.

Implemented:

- Added `BusinessCardService.selected_target_command_copy_packet`.
- Added CLI `bcw runs selected-target-command-copy-packet`.
- Added API `POST /runs/{run_id}/selected-target-command-copy-packet`.
- Added MCP tool `business_card_watchdog_selected_target_command_copy_packet`.
- Updated README and ROADMAP for the selected-target creation command-copy gate.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_selected_target_command_copy_packet_requires_acknowledgement tests/test_cli_surfaces.py::test_cli_runs_selected_target_command_copy_packet_requires_ack tests/test_api.py::test_api_run_selected_target_command_copy_packet_requires_ack tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_selected_target_command_copy_packet_requires_ack -q` passed with 5 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/cli.py src/business_card_watchdog/api.py src/business_card_watchdog/mcp.py tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py` passed.
- `.venv/bin/python -m pytest -q` passed with 329 tests.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `rg -n "selected-target-command-copy-packet|selected_target_command_copy_packet|Selected-target command copy packet|business_card_watchdog_selected_target_command_copy_packet|Plan 0050" README.md ROADMAP.md RUNBOOK.md docs src tests` passed.
- `uv build --out-dir dist` built source and wheel distributions.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `codegraph sync && codegraph status` passed; index is up to date.
- `.venv/bin/bcw drills watch-dry-run-execution --json` passed with one synthetic fixture file processed through a completed dry-run batch and no writes or network calls.
- Synthetic CLI selected-target command-copy smoke passed with `state=ready_for_operator_copy`, boundary state `ready_for_explicit_selected_target_creation`, acknowledgement ok, command text for `runs selected-live-target-from-response ... --write-selected-target`, zero writes, zero network calls, and no selected-target creation from the packet.

Safety:

- This added a selected-target command-copy packet only. It did not create `selected_live_target.json`; process configured SyncThing/private watch inputs; run OCR/App Intelligence; run public-web search; call paid enrichment; execute live lookup/write/readback; or write Google Contacts, Odoo, or Odollo records.

## Turn 257 | 2026-06-15

Executed Plan 0051 with Slice 0051-A.

Implemented:

- Added operator dashboard command/API/MCP map entries for `selected_target_approval_boundary`.
- Added operator dashboard command/API/MCP map entries for `selected_target_command_copy_packet`.
- Updated plain-text `bcw operator-dashboard` rendering for both selected-target gates.
- Updated README and ROADMAP for operator-dashboard selected-target gate discoverability.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_operator_dashboard_composes_no_live_readiness tests/test_cli_surfaces.py::test_cli_operator_dashboard_reports_no_live_summary tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 4 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/cli.py tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py` passed.
- `.venv/bin/python -m pytest -q` passed with 329 tests.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `rg -n "selected_target_approval_boundary|selected-target-approval-boundary|selected_target_command_copy_packet|selected-target-command-copy-packet|Plan 0051|operator dashboard" README.md ROADMAP.md RUNBOOK.md docs src tests` passed.
- `uv build --out-dir dist` built source and wheel distributions.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `codegraph sync && codegraph status` passed; index is up to date.
- `.venv/bin/bcw drills watch-dry-run-execution --json` passed with one synthetic fixture file processed through a completed dry-run batch and no writes or network calls.

Safety:

- This exposed existing selected-target gates from the operator dashboard only. It did not create `selected_live_target.json`; process configured SyncThing/private watch inputs; run OCR/App Intelligence; run public-web search; call paid enrichment; execute live lookup/write/readback; or write Google Contacts, Odoo, or Odollo records.

## Turn 258 | 2026-06-15

Executed Plan 0052 with Slice 0052-A.

Implemented:

- Added selected-target approval boundary execution to the synthetic live-pilot rehearsal drill.
- Added selected-target command-copy packet execution before synthetic selected-target creation.
- Updated rehearsal sample output and CLI text to show both selected-target gate states and commands.
- Updated ROADMAP for the new rehearsal evidence.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_live_pilot_rehearsal_drill_reaches_command_copy_gate tests/test_cli_surfaces.py::test_cli_live_pilot_rehearsal_drill_reaches_command_copy_gate tests/test_api.py::test_api_live_pilot_rehearsal_drill_reaches_command_copy_gate tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 4 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/cli.py tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py` passed.
- `.venv/bin/python -m pytest -q` passed with 329 tests.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `rg -n "selected_target_approval_boundary|selected-target-approval-boundary|selected_target_command_copy_packet|selected-target-command-copy-packet|Plan 0052|live-pilot rehearsal|live_pilot_rehearsal" README.md ROADMAP.md RUNBOOK.md docs src tests` passed.
- `uv build --out-dir dist` built source and wheel distributions.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `codegraph sync && codegraph status` passed; index is up to date.
- `.venv/bin/bcw drills live-pilot-rehearsal --json` passed with the selected-target approval boundary at `ready_for_explicit_selected_target_creation`, the selected-target command-copy packet at `ready_for_operator_copy`, zero writes, and zero network calls.
- `.venv/bin/bcw drills watch-dry-run-execution --json` passed with one synthetic fixture file processed through a completed dry-run batch and no writes or network calls.

Safety:

- This changed only a synthetic rehearsal drill and local sample output. It did not process configured SyncThing/private watch inputs; run private OCR/App Intelligence; run public-web search; call paid enrichment; execute live lookup/write/readback; or write Google Contacts, Odoo, or Odollo records.

## Turn 259 | 2026-06-15

Recovered Plan 0053 with Slice 0053-A after drift audit.

Implemented:

- Added `BusinessCardService.operator_live_pilot_readiness_packet`.
- Added CLI command `bcw operator-live-pilot-readiness-packet`.
- Added API routes `GET /operator/live-pilot-readiness-packet` and `POST /operator/live-pilot-readiness-packet`.
- Added MCP tool `business_card_watchdog_operator_live_pilot_readiness_packet`.
- Updated README and ROADMAP for the no-live operator readiness packet.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_operator_live_pilot_readiness_packet_reports_ready_boundary tests/test_cli_surfaces.py::test_cli_operator_live_pilot_readiness_packet_reports_ready_boundary tests/test_api.py::test_api_operator_live_pilot_readiness_packet_reports_ready_boundary tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_operator_live_pilot_readiness_packet_reports_ready_boundary -q` passed with 5 tests.
- `.venv/bin/python -m pytest -q` passed with 333 tests.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.

Recovery:

- The previous loop had updated Plan 0053 and ROADMAP but did not add the claimed RUNBOOK closeout before handoff.
- This entry reconciles the missing closeout evidence without adding more live-pilot feature scope.

Safety:

- This added a local no-live readiness packet only. It did not create `selected_live_target.json`; process configured SyncThing/private watch inputs; run OCR/App Intelligence on private images; run public-web search; call paid enrichment; execute live lookup/write/readback; or write Google Contacts, Odoo, or Odollo records.

## Turn 260 | 2026-06-15

Executed Plan 0054 with Slice 0054-A.

Implemented:

- Added `docs/dev/plans/0054-2026-06-15-drift-recovery-closeout-reconciliation.md`.
- Updated Plan 0053 validation from a missing runbook pointer to concrete validation evidence.
- Recorded the drift recovery boundary and stopped further feature expansion.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_operator_live_pilot_readiness_packet_reports_ready_boundary tests/test_cli_surfaces.py::test_cli_operator_live_pilot_readiness_packet_reports_ready_boundary tests/test_api.py::test_api_operator_live_pilot_readiness_packet_reports_ready_boundary tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_operator_live_pilot_readiness_packet_reports_ready_boundary -q` passed with 5 tests.
- `.venv/bin/python -m pytest -q` passed with 333 tests.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.

Safety:

- This recovery changed documentation and closeout records only. It did not process private input; create selected targets; execute live lookup, write, or readback; or write Google Contacts, Odoo, or Odollo records.

## Turn 261 | 2026-06-15

Executed Plan 0055 with Slice 0055-A.

Implemented:

- Added `src/business_card_watchdog/live_pilot_packets.py`.
- Moved the no-live operator live-pilot readiness packet body out of `BusinessCardService`.
- Moved selected-target approval boundary and selected-target command-copy packet bodies out of `BusinessCardService`.
- Left the existing `BusinessCardService` methods as compatibility wrappers so CLI/API/MCP surfaces remain unchanged.
- Updated `ROADMAP.md` and Plan 0055 closeout evidence.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_operator_live_pilot_readiness_packet_reports_ready_boundary tests/test_service.py::test_service_selected_target_approval_boundary_previews_explicit_selection tests/test_service.py::test_service_selected_target_command_copy_packet_requires_acknowledgement tests/test_cli_surfaces.py::test_cli_operator_live_pilot_readiness_packet_reports_ready_boundary tests/test_cli_surfaces.py::test_cli_runs_selected_target_approval_boundary_previews_selection tests/test_cli_surfaces.py::test_cli_runs_selected_target_command_copy_packet_requires_ack tests/test_api.py::test_api_operator_live_pilot_readiness_packet_reports_ready_boundary tests/test_api.py::test_api_run_selected_target_approval_boundary_previews_selection tests/test_api.py::test_api_run_selected_target_command_copy_packet_requires_ack tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_operator_live_pilot_readiness_packet_reports_ready_boundary tests/test_mcp.py::test_mcp_selected_target_approval_boundary_previews_selection tests/test_mcp.py::test_mcp_selected_target_command_copy_packet_requires_ack -q` passed with 13 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/live_pilot_packets.py` passed.
- `.venv/bin/python -m pytest -q` passed with 333 tests.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This was a behavior-preserving extraction only. It did not process private input; create selected targets; execute live lookup, write, or readback; or write Google Contacts, Odoo, or Odollo records.

## Turn 262 | 2026-06-16

Executed Plan 0056 with Slice 0056-A.

Implemented:

- Added `docs/dev/plans/0056-2026-06-16-monolith-decomposition-drift-guard.md` with subagent workstreams, drift gates, and stop conditions.
- Added `src/business_card_watchdog/surface_registry.py` as a shared MCP surface registry seed.
- Routed MCP manifest entries and dispatch for the operator live-pilot readiness packet, selected-target approval boundary, and selected-target command-copy packet through the registry.
- Added `scripts/check_plan_drift.py` to guard roadmap, plan, and runbook closeout pointers.
- Updated `ROADMAP.md` with Plan 0056 as the latest completed refactor plan.

Validation:

- `.venv/bin/python -m pytest tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_operator_live_pilot_readiness_packet_reports_ready_boundary tests/test_mcp.py::test_mcp_selected_target_approval_boundary_previews_selection tests/test_mcp.py::test_mcp_selected_target_command_copy_packet_requires_ack tests/test_service.py::test_service_operator_live_pilot_readiness_packet_reports_ready_boundary tests/test_service.py::test_service_selected_target_approval_boundary_previews_explicit_selection tests/test_service.py::test_service_selected_target_command_copy_packet_requires_acknowledgement -q` passed with 7 tests.
- `.venv/bin/ruff check src/business_card_watchdog/mcp.py src/business_card_watchdog/surface_registry.py scripts/check_plan_drift.py` passed.
- `python3 scripts/check_plan_drift.py` passed.
- `.venv/bin/python -m pytest -q` passed with 333 tests.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This was a behavior-preserving surface registry seed and drift-guard slice only. It did not process private input; create selected targets; execute live lookup, write, or readback; or write Google Contacts, Odoo, or Odollo records.

## Turn 263 | 2026-06-18

Finished Plan 0056 with Slices 0056-B and 0056-C.

Implemented:

- Extended the selected packet surface registry into CLI parser/dispatch reuse for the operator live-pilot readiness packet, selected-target approval boundary, and selected-target command-copy packet.
- Reused registry route-path constants from API decorators while keeping explicit FastAPI endpoint functions and request models.
- Added `src/business_card_watchdog/operator_dashboard.py` and moved the large `operator_dashboard` aggregation behind `build_operator_dashboard`.
- Kept `BusinessCardService.operator_dashboard` as the compatibility entrypoint.
- Updated Plan 0056, ROADMAP, and the drift guard to record the full-plan closeout instead of only Slice 0056-A.

Validation:

- `.venv/bin/python -m pytest tests/test_cli_surfaces.py::test_cli_operator_live_pilot_readiness_packet_reports_ready_boundary tests/test_cli_surfaces.py::test_cli_runs_selected_target_approval_boundary_previews_selection tests/test_cli_surfaces.py::test_cli_runs_selected_target_command_copy_packet_requires_ack tests/test_api.py::test_api_operator_live_pilot_readiness_packet_reports_ready_boundary tests/test_api.py::test_api_run_selected_target_approval_boundary_previews_selection tests/test_api.py::test_api_run_selected_target_command_copy_packet_requires_ack tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_operator_live_pilot_readiness_packet_reports_ready_boundary tests/test_mcp.py::test_mcp_selected_target_approval_boundary_previews_selection tests/test_mcp.py::test_mcp_selected_target_command_copy_packet_requires_ack tests/test_service.py::test_service_operator_dashboard_composes_no_live_readiness tests/test_cli_surfaces.py::test_cli_operator_dashboard_reports_no_live_summary -q` passed with 12 tests.
- `.venv/bin/ruff check src/business_card_watchdog/operator_dashboard.py src/business_card_watchdog/service.py src/business_card_watchdog/cli.py src/business_card_watchdog/api.py src/business_card_watchdog/surface_registry.py` passed.
- `.venv/bin/python -m pytest -q` passed with 333 tests.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `.venv/bin/ruff check scripts/check_plan_drift.py` passed.
- `python3 scripts/check_plan_drift.py` passed.
- `codegraph sync && codegraph status` passed; index is up to date with 48 files, 1,672 nodes, and 3,348 edges.

Safety:

- This completed Plan 0056 as behavior-preserving registry and dashboard extraction work. It did not process private input; create selected targets; execute live lookup, write, or readback; or write Google Contacts, Odoo, or Odollo records.

## Turn 264 | 2026-06-18

Executed Plan 0057 with Slice 0057-A.

Implemented:

- Added `docs/dev/plans/0057-2026-06-18-service-recovery-extraction.md`.
- Added `src/business_card_watchdog/service_recovery.py` for the read-only service recovery aggregator.
- Moved the `service_recovery_report` aggregation body behind `build_service_recovery_report`.
- Kept `BusinessCardService.service_recovery_report` as the compatibility entrypoint.
- Updated `ROADMAP.md` and `scripts/check_plan_drift.py` so the latest refactor closeout points at Plan 0057.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_recovery_report_composes_status_and_recovery_commands tests/test_cli_surfaces.py::test_cli_service_recovery_reports_status_shape tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service tests/test_service.py::test_service_operator_dashboard_composes_no_live_readiness tests/test_cli_surfaces.py::test_cli_operator_dashboard_reports_no_live_summary -q` passed with 7 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/service_recovery.py` passed.
- `.venv/bin/python -m pytest -q` passed with 333 tests.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `.venv/bin/ruff check scripts/check_plan_drift.py` passed.
- `python3 scripts/check_plan_drift.py` passed.
- `codegraph sync && codegraph status` passed; index is up to date with 49 files, 1,680 nodes, and 3,363 edges.

Safety:

- This was a behavior-preserving service-recovery extraction. It did not process private input; create selected targets; execute live lookup, write, or readback; or write Google Contacts, Odoo, or Odollo records.

## Turn 265 | 2026-06-19

Opened Plan 0058 as the next goal-compatible monolith refactoring plan.

Updated:

- Added `docs/dev/plans/0058-2026-06-19-goal-compatible-monolith-refactoring.md`.
- Wired `ROADMAP.md` to show Plan 0058 as the next refactor plan while keeping
  Plan 0057 as the latest completed refactor plan.
- Captured current monolith pressure from repo evidence: `service.py` remains
  roughly 15.4k lines, `cli.py` roughly 4.3k lines, and `mcp.py` roughly 2.1k
  lines after the Plan 0057 extraction.
- Captured the pre-plan CodeGraph status: 49 indexed files, 1,680 nodes, and
  3,363 edges.
- Defined `/goal` workstreams, subagent boundaries, stop conditions, slice
  plan, acceptance criteria, and validation rules for further
  behavior-preserving decomposition.

Validation:

- `git diff --check` passed.
- `python3 scripts/check_plan_drift.py` passed.

Safety:

- This opened a plan only. It did not process private input; create selected
  targets; execute live lookup, write, live pilot execution, or readback; or
  write Google Contacts, Odoo, or Odollo records.

## Turn 266 | 2026-06-19

Executed Plan 0058 with Slices 0058-A through 0058-C for the pilot-readiness
cluster.

Implemented:

- Added `src/business_card_watchdog/pilot_readiness.py` and moved the
  `pilot_readiness_report` aggregation body behind `build_pilot_readiness_report`.
- Kept `BusinessCardService.pilot_readiness_report` as the compatibility
  wrapper.
- Added `src/business_card_watchdog/cli_renderers.py` and moved the
  pilot-readiness text renderer behind `render_pilot_readiness_report_text`.
- Extended `src/business_card_watchdog/surface_registry.py` with the
  pilot-readiness MCP tool spec, CLI parser/dispatch helper, and API path
  constant.
- Reused the registry from `mcp.py`, `cli.py`, and `api.py` for the
  pilot-readiness public surface.
- Closed Plan 0058 and updated `ROADMAP.md` so the latest completed refactor
  plan points at Plan 0058.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_run_summary_and_review_queue tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_cli_surfaces.py::test_cli_runs_and_jobs_use_recorded_runtime_state tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service tests/test_mcp.py::test_mcp_jsonl_server_lists_and_calls_tools -q`
  passed with 6 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/pilot_readiness.py src/business_card_watchdog/surface_registry.py src/business_card_watchdog/cli.py src/business_card_watchdog/cli_renderers.py src/business_card_watchdog/api.py src/business_card_watchdog/mcp.py`
  passed.
- `.venv/bin/python -m pytest -q` passed with 333 tests.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `.venv/bin/ruff check scripts/check_plan_drift.py` passed.
- `python3 scripts/check_plan_drift.py` passed.
- `codegraph sync && codegraph status` passed; index is up to date with 51
  files, 1,691 nodes, and 4,540 edges.

Safety:

- This was a behavior-preserving pilot-readiness extraction and surface
  registry/renderer thinning slice. It did not process private input; create
  selected targets; execute live lookup, write, live pilot execution, or
  readback; or write Google Contacts, Odoo, or Odollo records.

## Turn 267 | 2026-06-20

Committed and pushed the completed Plan 0058 checkpoint, then opened the next
bounded refactor plan.

Updated:

- Committed Plan 0058 as `706070c` with message
  `Complete plan 0058 pilot readiness extraction`.
- Pushed `main` to `upstream/main`.
- Added `docs/dev/plans/0059-2026-06-20-review-route-lookup-selection-extraction.md`.
- Updated `ROADMAP.md` so the next refactor plan points at Plan 0059 while
  the latest completed refactor plan remains Plan 0058.
- Used CodeGraph context to confirm `lookup_selection_packet` depends on
  `review_route_readiness`, so Plan 0059 keeps those methods in one extraction
  cluster.

Validation:

- Pre-commit Plan 0058 validation passed before `706070c`:
  `python3 scripts/check_plan_drift.py`, `git diff --check`,
  `.venv/bin/ruff check .`, and `.venv/bin/python -m pytest -q` with 333 tests.
- Plan 0059 is planning-only; run `git diff --check` and
  `python3 scripts/check_plan_drift.py` before committing it.

Safety:

- Plan 0059 is planning-only. It does not process private input; create
  selected targets; execute live lookup, write, live pilot execution, or
  readback; or write Google Contacts, Odoo, or Odollo records.

## Turn 268 | 2026-06-20

Executed Plan 0059 with the review-route readiness and lookup-selection packet
cluster.

Implemented:

- Added `src/business_card_watchdog/review_route_packets.py`.
- Moved the `review_route_readiness` aggregation body behind
  `build_review_route_readiness`.
- Moved the `lookup_selection_packet` aggregation body behind
  `build_lookup_selection_packet`.
- Kept `BusinessCardService.review_route_readiness` and
  `BusinessCardService.lookup_selection_packet` as compatibility wrappers.
- Extended `src/business_card_watchdog/surface_registry.py` with the
  review-route and lookup-selection MCP tool specs, CLI command constants,
  parser/dispatch helpers, and API path constants.
- Reused the registry from `mcp.py`, `cli.py`, and `api.py` for both public
  surfaces.
- Moved the review-route readiness and lookup-selection text renderers into
  `src/business_card_watchdog/cli_renderers.py`.
- Closed Plan 0059 and updated `ROADMAP.md` so the latest completed refactor
  plan points at Plan 0059.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_review_route_readiness_summarizes_review_and_route_state tests/test_service.py::test_service_lookup_selection_packet_selects_route_ready_job_without_live_calls tests/test_cli_surfaces.py::test_cli_runs_review_route_readiness_reports_route_state tests/test_cli_surfaces.py::test_cli_runs_lookup_selection_packet_reports_selected_candidate tests/test_api.py::test_api_run_review_route_readiness_reports_route_state tests/test_api.py::test_api_run_lookup_selection_packet_reports_selected_candidate tests/test_mcp.py::test_mcp_review_route_readiness_reports_route_state tests/test_mcp.py::test_mcp_lookup_selection_packet_reports_selected_candidate tests/test_mcp.py::test_manifest_has_process_tool -q`
  passed with 9 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/review_route_packets.py src/business_card_watchdog/surface_registry.py src/business_card_watchdog/api.py src/business_card_watchdog/mcp.py src/business_card_watchdog/cli.py src/business_card_watchdog/cli_renderers.py`
  passed.
- `.venv/bin/python -m pytest -q` passed with 333 tests.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `.venv/bin/ruff check scripts/check_plan_drift.py` passed.
- `python3 scripts/check_plan_drift.py` passed.
- `codegraph sync && codegraph status` passed; index is up to date with 52
  files, 1,705 nodes, and 4,698 edges.

Safety:

- This was a behavior-preserving review-route and lookup-selection extraction.
  It did not process private input; create selected targets; execute live
  lookup, write, live pilot execution, or readback; or write Google Contacts,
  Odoo, or Odollo records.

## Turn 269 | 2026-06-20

Committed and pushed Plan 0059, then opened a high-level product development
milestone plan.

Updated:

- Committed Plan 0059 as `704da0c` with message
  `Complete plan 0059 review route extraction`.
- Pushed `main` to `upstream/main`.
- Added
  `docs/dev/plans/0060-2026-06-20-product-development-milestone-plan.md`.
- Linked Plan 0060 from `ROADMAP.md` as the active high-level development
  plan.

Plan 0060 milestones:

- User-scoped contact store.
- Artifact-to-database projection.
- Card detection, cropping, and OCR quality loop.
- App Intelligence quality review state.
- Enrichment provider contracts.
- Routing policy and `ecochran76` GWS default sink.
- Odollo SoyLei and SABER routing.
- Contact review surface.
- Operator-selected live pilot.

Validation:

- Pre-commit Plan 0059 validation in Turn 268 passed before `704da0c`:
  targeted service/API/CLI/MCP tests, full test suite with 333 tests, full
  ruff, `git diff --check`, drift guard, and CodeGraph sync/status.
- Before committing `704da0c`, lightweight gates passed again:
  `git diff --check`, `python3 scripts/check_plan_drift.py`, and targeted
  ruff over the changed modules.
- Plan 0060 is planning-only; run `git diff --check` and
  `python3 scripts/check_plan_drift.py` before committing it.

Safety:

- Plan 0060 is planning-only. It did not process private input; create selected
  targets; execute live lookup, enrichment, write, live pilot execution, or
  readback; or write Google Contacts, Odoo, or Odollo records.

## Turn 270 | 2026-06-20

Hardened watcher status state after concurrent no-processing commands exposed a
status JSON race.

Implemented:

- Added `docs/dev/plans/0061-2026-06-20-watch-status-atomic-state-hardening.md`.
- Updated `WatchStateStore.write_status` to write `status.json` through a
  same-directory temporary file and `os.replace`.
- Updated `WatchStateStore.read_status` to tolerate missing, empty, or malformed
  status JSON by returning a default status rather than raising
  `JSONDecodeError`.
- Added regression tests for empty status reads and valid replacement writes.

Validation:

- `.venv/bin/python -m pytest tests/test_watcher.py -q` passed with 16 tests.
- `.venv/bin/ruff check src/business_card_watchdog/watcher.py tests/test_watcher.py`
  passed.
- `git diff --check` passed.
- `python3 scripts/check_plan_drift.py` passed.
- Concurrent no-processing verification passed:
  `.venv/bin/bcw watch-status --json` and
  `.venv/bin/bcw watch-backlog-preflight --no-write --json` both completed over
  `$fsr:sync_phone` and `$fsr:scanner` with backlog `12`, unsettled `0`, no
  last error, zero files processed, zero OCR, zero writes, and zero network
  calls.

Safety:

- This slice changed watcher runtime status state handling only. It did not
  process watched files; OCR private card images; add PDF/card-backside support;
  run enrichment; run live lookup, write, or readback; or write Google Contacts,
  Odoo, or Odollo records.

## Turn 271 | 2026-06-21

Executed Plan 0062 with a no-processing practice-corpus manifest for the current
two-folder watcher configuration.

Implemented:

- Added `docs/dev/plans/0062-2026-06-21-practice-corpus-manifest.md`.
- Added `src/business_card_watchdog/practice_corpus.py`.
- Added `BusinessCardService.watch_practice_corpus_manifest`.
- Added `bcw watch-practice-corpus-manifest` with repeatable
  `--include-glob` filters.
- Added service and CLI tests for synthetic image/PDF practice manifests.
- Linked Plan 0062 from `ROADMAP.md`.

Runtime execution:

- Preview command:
  `.venv/bin/bcw watch-practice-corpus-manifest --no-write --include-glob 'Camera/20260620_11*.jpg' --include-glob '2026_06_20_11_21_42.pdf' --json`.
- Write command:
  `.venv/bin/bcw watch-practice-corpus-manifest --include-glob 'Camera/20260620_11*.jpg' --include-glob '2026_06_20_11_21_42.pdf' --json`.
- The written user-scoped runtime manifest is
  `/home/ecochran76/.local/share/business-card-watchdog/practice_corpus_manifest.json`.
- The manifest reported 14 entries: 13 phone-camera images and 1 scanner PDF,
  with 13 current watcher-processable files, 0 unsettled entries, and 0 errors.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_practice_corpus_manifest_inventories_images_and_pdfs_without_processing tests/test_watcher.py::test_watch_practice_corpus_manifest_cli_previews_images_and_pdfs -q`
  passed with 2 tests.
- `.venv/bin/ruff check src/business_card_watchdog/practice_corpus.py src/business_card_watchdog/service.py src/business_card_watchdog/cli.py tests/test_service.py tests/test_watcher.py`
  passed.
- `.venv/bin/python -m pytest -q` passed with 337 tests.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `python3 scripts/check_plan_drift.py` passed.
- `codegraph sync && codegraph status` passed; index is up to date with 53
  files, 1,738 nodes, and 3,026 edges.

Safety:

- Plan 0062 inventoried and hashed selected watched files only. It did not OCR,
  crop, rasterize PDFs, enrich, route, execute live lookup/write/readback, or
  write Google Contacts, Odoo, or Odollo records. The runtime manifest is
  user-scoped private state and was not added to git.

## Turn 272 | 2026-06-21

Integrated the card-backside pairing design into the active high-level
development plan.

Updated:

- Revised Plan 0060 Milestone 3 so scanner front/back pairing is explicitly
  OCR-assisted and context-scored rather than sequence-only.
- Added `front`, `back`, `blank`, and `unknown` side labels.
- Added OCR/contextual evidence requirements for name/title/email density,
  company/domain overlap, phone/address fragments, QR/URL/domain hints,
  back-of-card patterns, and blank/near-blank detection.
- Added scored pair-candidate graph requirements that combine scanner page
  adjacency, same PDF/session, same-stem image pairs, timestamp adjacency, OCR
  token overlap, visual/crop similarity, and negative conflict evidence.
- Added acceptance/validation coverage for reversed front/back order, dropped
  blank backs, ambiguous pairs, and conflicting OCR evidence.

Validation:

- Planning-only update. Run `git diff --check` and
  `python3 scripts/check_plan_drift.py` before committing.

Safety:

- Planning-only update. It did not process watched files; OCR private card
  images; rasterize PDFs; run enrichment; run live lookup/write/readback; or
  write Google Contacts, Odoo, or Odollo records.

## Turn 273 | 2026-06-21

Executed Plan 0063 as the first Plan 0060 Milestone 1 implementation slice.

Implemented:

- Added `docs/dev/plans/0063-2026-06-21-user-scoped-contact-store.md`.
- Added a user-scoped SQLite contact store at
  `data_dir/contacts/contacts.sqlite`.
- Added migration/schema support for contacts, card assets, extraction
  attempts, enrichment attempts, routing decisions, sink attempts, and external
  tenant bindings.
- Added deterministic idempotent projection from existing dry-run run artifacts
  into contact rows.
- Added service methods and `bcw contacts status|init|list|show|project-run`.
- Added tests for schema initialization, idempotent synthetic-run projection,
  and CLI JSON inspection/projection.

Validation:

- `pytest tests/test_contact_store.py -q` passed with 3 tests.
- `pytest tests/test_contact.py tests/test_state_and_ledger.py tests/test_api.py -q`
  passed with 9 tests and 1 skipped.
- `.venv/bin/ruff check .` passed.
- `.venv/bin/python -m pytest tests/test_contact_store.py tests/test_contact.py tests/test_state_and_ledger.py -q`
  passed with 12 tests.
- `.venv/bin/python -m pytest -q` passed with 340 tests.
- `git diff --check` passed.
- `python3 scripts/check_plan_drift.py` passed.

Safety:

- This slice only projects existing local run artifacts when explicitly invoked.
  It did not process watched files; OCR private card images; rasterize PDFs; run
  enrichment; run live lookup/write/readback; or write Google Contacts, Odoo, or
  Odollo records.

## Turn 274 | 2026-06-22

Executed Plan 0064 as the Plan 0060 Milestone 2 implementation slice.

Implemented:

- Added `docs/dev/plans/0064-2026-06-22-artifact-to-database-projection.md`.
- Wired `BatchOrchestrator.process_source` to project run artifacts into the
  user-scoped contact store after extraction artifacts are written.
- Added `contact_store_projection.json` run artifact and
  `contact_store_projected` ledger event for successful projection.
- Added retryable `contact_store_projection_failed` ledger evidence with a
  `contacts project-run <run-id> --json` repair command when projection fails.
- Extended contact-store projection to include source/crop/OCR/review assets,
  enrichment attempts, routing decisions, sink attempts, normalized contact
  fields, and extraction provenance.
- Added contact-store drift/readback status and `bcw contacts drift <run-id>`.

Validation:

- `.venv/bin/python -m pytest tests/test_contact_store.py tests/test_dry_run_pipeline.py -q`
  passed with 6 tests.
- `.venv/bin/python -m pytest tests/test_api.py tests/test_cli_surfaces.py tests/test_mcp.py -q`
  passed with 111 tests.
- `.venv/bin/python -m pytest tests/test_service.py tests/test_review_surface.py tests/test_enrichment.py -q`
  passed with 141 tests.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `.venv/bin/python -m pytest -q` passed with 341 tests.

Safety:

- This slice projects existing run artifacts only. It did not add OCR behavior,
  rasterize PDFs, process private watched folders on its own, run enrichment
  providers, run live lookup/write/readback, or write Google Contacts, Odoo, or
  Odollo records.

## Turn 275 | 2026-06-22

Executed Plan 0065 as the first Plan 0060 Milestone 3 implementation slice.

Implemented:

- Added `docs/dev/plans/0065-2026-06-22-scanner-document-intake.md`.
- Added `src/business_card_watchdog/document_intake.py`.
- Kept `is_supported_image` image-only while adding PDF document-source support.
- Added `discover_processable_sources` for image and PDF document discovery.
- Materialized PDF pages under each run's `document_intake/` directory, using
  local `pdftoppm` when available and deterministic placeholder page images for
  synthetic/unsupported fixtures.
- Added run-level `document_pages` artifacts plus per-page `source_page` and
  initial `card_side_candidate` artifacts.
- Fed PDF page-image child jobs through the existing dry-run image pipeline and
  contact-store projection.
- Updated watcher discovery/status and practice-corpus manifest semantics so
  PDFs are processable document-intake sources, not direct image inputs.

Validation:

- `.venv/bin/python -m pytest tests/test_dry_run_pipeline.py tests/test_watcher.py tests/test_service.py::test_service_practice_corpus_manifest_inventories_images_and_pdfs_without_processing -q`
  passed with 23 tests.
- `.venv/bin/python -m pytest tests/test_dry_run_pipeline.py tests/test_watcher.py tests/test_service.py tests/test_contact_store.py -q`
  passed with 137 tests.
- `.venv/bin/python -m pytest tests/test_api.py tests/test_cli_surfaces.py tests/test_mcp.py -q`
  passed with 111 tests.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `.venv/bin/python -m pytest -q` passed with 343 tests.

Safety:

- This slice did not add live sink writes, paid enrichment, public-web calls,
  automatic front/back pairing, or source PDF mutation.
- Scanner PDF processing now creates runtime page-image artifacts only after an
  existing operator/runtime command processes a PDF source.

## Turn 276 | 2026-06-22

Executed Plan 0066 as the OCR-assisted card-side classification and pair
proposal slice under Plan 0060 Milestone 3.

Implemented:

- Added `docs/dev/plans/0066-2026-06-22-ocr-side-classification-pair-proposals.md`.
- Added `src/business_card_watchdog/card_sides.py`.
- Classified scanner page sides as `front`, `back`, `blank`, or `unknown`
  using deterministic OCR clues: email/phone/name/title density, URL/social/QR
  hints, address/context words, and blank/near-blank text.
- Rewrote per-page `card_side_candidate.json` after OCR text exists, preserving
  evidence, OCR feature counts, and OCR text hash.
- Added run-level `card_side_pair_proposals.json` artifacts.
- Scored pair proposals from same-document evidence, page adjacency, side-label
  complement, and negative conflicting-domain evidence.
- Supported reversed back/front scanner order through side labels rather than
  sequence-only assumptions.
- Kept blank backs skipped and conflicting pairs blocked for review rather than
  merged automatically.

Validation:

- `.venv/bin/python -m pytest tests/test_card_sides.py tests/test_dry_run_pipeline.py::test_pdf_document_intake_materializes_page_jobs_and_side_candidates -q`
  passed with 5 tests.
- `.venv/bin/python -m pytest tests/test_card_sides.py tests/test_dry_run_pipeline.py tests/test_contact_store.py tests/test_watcher.py -q`
  passed with 29 tests.
- `.venv/bin/python -m pytest tests/test_service.py tests/test_review_surface.py tests/test_enrichment.py -q`
  passed with 141 tests.
- `.venv/bin/python -m pytest tests/test_api.py tests/test_cli_surfaces.py tests/test_mcp.py -q`
  passed with 111 tests.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `.venv/bin/python -m pytest -q` passed with 347 tests.

Safety:

- This slice treats OCR as evidence only. It did not automatically merge
  front/back contacts, run enrichment providers, run public-web search, execute
  live lookup/write/readback, or write Google Contacts, Odoo, or Odollo records.

## Turn 277 | 2026-06-22

Executed Plan 0067 as the reviewed front/back side-pair merge slice under Plan
0060 Milestone 3.

Implemented:

- Added `docs/dev/plans/0067-2026-06-22-reviewed-side-pair-merge.md`.
- Added side-pair review queue support from `card_side_pair_proposals.json`.
- Added explicit side-pair review submission support for
  `approve_side_pair_merge`, `keep_needs_review`, and `reject_side_pair`.
- Added `bcw reviews side-pairs` and `bcw reviews side-pair-review`.
- Added reviewed front/back merge behavior through `merge_side_pair_contacts`.
- Wrote durable `side_pair_review_submission`,
  `reviewed_side_pair_contact`, and `side_pair_review_result` artifacts.
- Preserved field-level side provenance showing whether merged fields came from
  the front side, back side, both, or reviewer correction.
- Kept merged side-pair contacts out of routing/sink writes pending final
  contact review.

Validation:

- `.venv/bin/python -m pytest tests/test_card_sides.py -q` passed with 7 tests.
- `.venv/bin/python -m pytest tests/test_card_sides.py tests/test_review_surface.py tests/test_cli_surfaces.py -q`
  passed with 67 tests.
- `.venv/bin/python -m pytest tests/test_contact_store.py tests/test_dry_run_pipeline.py tests/test_service.py -q`
  passed with 119 tests.
- `.venv/bin/python -m pytest tests/test_api.py tests/test_mcp.py -q` passed
  with 60 tests.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `.venv/bin/python -m pytest -q` passed with 350 tests.

Safety:

- This slice did not automatically merge side pairs, route merged contacts, run
  enrichment providers, run public-web search, execute live lookup/write/readback,
  or write Google Contacts, Odoo, or Odollo records.

## Turn 278 | 2026-06-22

Updated the active Plan 0060 Milestone 3 scanner-side pairing scope instead of
opening a duplicate plan.

Captured:

- Scanner adjacency is a priority signal but not correctness proof.
- Both front-back and back-front scanner page orderings must be scored.
- OCR/context clues are required pair evidence, including shared domain,
  company, address, phone, QR/URL/social, and absence of conflicting identity
  signals.
- Dropped blank backs are expected scanner behavior; complete fronts can still
  progress, while non-blank backs remain unmerged until paired or reviewed.
- Optional stochastic/app-intelligence evidence may rank or explain ambiguous
  pairs, but acceptance, merge, and route-readiness remain host-owned review
  transitions.

Validation:

- Documentation-only change reviewed with `git diff`.

## Turn 279 | 2026-06-22

Executed Plan 0068 as the deterministic extraction quality-gate slice under
Plan 0060 Milestone 3.

Implemented:

- Added `src/business_card_watchdog/quality.py`.
- Added `business-card-watchdog.extraction-quality.v1` artifacts for successful
  adapter runs.
- Checked OCR text presence/token count and crop-manifest presence/count before
  duplicate and sink decisions.
- Blocked scanner-derived `back`, `blank`, `unknown`, or missing side labels
  from direct route-readiness.
- Added extraction-quality evidence to review packets.

Validation:

- `.venv/bin/python -m pytest tests/test_quality.py tests/test_dry_run_pipeline.py::test_batch_dry_run_uses_synthetic_adapter_without_credentials tests/test_dry_run_pipeline.py::test_incomplete_synthetic_spec_creates_review_packet tests/test_dry_run_pipeline.py::test_short_ocr_quality_creates_review_packet_before_routing -q`
  passed with 6 tests.
- `.venv/bin/python -m pytest tests/test_quality.py tests/test_card_sides.py tests/test_dry_run_pipeline.py -q`
  passed with 15 tests.
- `.venv/bin/python -m pytest tests/test_quality.py tests/test_card_sides.py tests/test_dry_run_pipeline.py tests/test_contact_store.py tests/test_review_surface.py -q`
  passed with 27 tests.
- `.venv/bin/python -m pytest tests/test_service.py tests/test_api.py tests/test_mcp.py tests/test_cli_surfaces.py -q`
  passed with 223 tests.
- `.venv/bin/ruff check src/business_card_watchdog tests/test_quality.py tests/test_card_sides.py tests/test_dry_run_pipeline.py`
  passed.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `.venv/bin/python scripts/check_plan_drift.py` passed.
- `.venv/bin/python -m pytest -q` passed with 354 tests.
- `codegraph sync /home/ecochran76/workspace.local/business-card-watchdog && codegraph status /home/ecochran76/workspace.local/business-card-watchdog`
  reported the index already up to date, 60 files, 1,913 nodes, and 2,567
  edges.

Safety:

- This slice did not run enrichment providers, public-web search, live
  lookup/write/readback, Google Contacts writes, Odoo/Odollo writes, or
  automatic front/back merges.

## Turn 280 | 2026-06-22

Executed Plan 0069 as the reviewed child-contact projection slice under Plan
0060 Milestone 3.

Implemented:

- Added `docs/dev/plans/0069-2026-06-22-reviewed-child-contact-projection.md`.
- Projected `reviewed_child_contact` artifacts as first-class user-scoped
  contact rows.
- Used child-specific source job IDs in the form
  `<parent_job_id>::<candidate_id>` so multiple reviewed cards from one
  multi-card source image remain distinct.
- Preserved parent job, child candidate, work item, crop, and review provenance
  on projected child contact rows.
- Added child review submission, result, and reviewed contact artifacts to the
  child contact asset set.
- Refreshed contact-store projection after child review submission without
  live sink writes.

Validation:

- `.venv/bin/python -m pytest tests/test_review_surface.py::test_child_review_approval_writes_reviewed_child_contact_artifact tests/test_review_surface.py::test_multiple_reviewed_child_contacts_project_as_distinct_contacts tests/test_contact_store.py::test_contact_store_projects_run_idempotently tests/test_preclassifier.py::test_orchestrator_records_multi_card_candidate_manifest -q`
  passed with 4 tests.
- `.venv/bin/python -m pytest tests/test_review_surface.py tests/test_preclassifier.py tests/test_contact_store.py -q`
  passed with 20 tests.
- `.venv/bin/python -m pytest tests/test_api.py tests/test_cli_surfaces.py tests/test_mcp.py -q`
  passed with 111 tests.
- `.venv/bin/ruff check src/business_card_watchdog/contact_store.py src/business_card_watchdog/service.py tests/test_review_surface.py`
  passed.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `.venv/bin/python scripts/check_plan_drift.py` passed.
- `.venv/bin/python -m pytest -q` passed with 355 tests.
- `codegraph sync /home/ecochran76/workspace.local/business-card-watchdog && codegraph status /home/ecochran76/workspace.local/business-card-watchdog`
  reported the index already up to date, 60 files, 1,918 nodes, and 2,552
  edges.

Safety:

- This slice did not run production OCR/App Intelligence for child crops, run
  enrichment providers, public-web search, live lookup/write/readback, Google
  Contacts writes, Odoo/Odollo writes, or automatic child-contact routing.

## Turn 281 | 2026-06-22

Executed Plan 0070 as the first App Intelligence review-state slice under Plan
0060 Milestone 4.

Implemented:

- Added `docs/dev/plans/0070-2026-06-22-contact-review-states.md`.
- Added `contact_review_states` to the user-scoped contact database.
- Stored App Intelligence recommendations as proposed contact review states
  with source, category, recommendation, rationale, confidence, and evidence.
- Added host-owned accept/reject decisions that preserve audit evidence without
  mutating contact fields from model output.
- Surfaced review states in contact detail.
- Added service and CLI JSON flows for recording, listing, and deciding contact
  review recommendations.

Validation:

- `.venv/bin/python -m pytest tests/test_contact_store.py -q` passed with 4
  tests.
- `.venv/bin/python -m pytest tests/test_cli_surfaces.py tests/test_service.py -q`
  passed with 163 tests.
- `.venv/bin/python -m pytest tests/test_api.py tests/test_mcp.py -q` passed
  with 60 tests.
- `.venv/bin/ruff check src/business_card_watchdog/contact_store.py src/business_card_watchdog/service.py src/business_card_watchdog/cli.py tests/test_contact_store.py`
  passed.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `.venv/bin/python scripts/check_plan_drift.py` passed.
- `.venv/bin/python -m pytest -q` passed with 356 tests.
- `codegraph sync /home/ecochran76/workspace.local/business-card-watchdog && codegraph status /home/ecochran76/workspace.local/business-card-watchdog`
  reported the index already up to date, 60 files, 1,926 nodes, and 2,560
  edges.

Safety:

- This slice did not run autonomous App Intelligence loops, mutate contact
  fields from model output, run enrichment providers, public-web search, live
  lookup/write/readback, Google Contacts writes, Odoo writes, or Odollo writes.

## Turn 282 | 2026-06-22

Executed Plan 0071 as the bounded contact review-state safe-loop slice under
Plan 0060 Milestone 4.

Implemented:

- Added `docs/dev/plans/0071-2026-06-22-contact-review-safe-loop.md`.
- Added a bounded safe-loop service method over proposed contact review states.
- Previewed actions by default and applied decisions only when requested.
- Limited automatic action to explicit safe auto-rejection evidence:
  `safe_to_auto_continue=true` and `safe_auto_decision=reject`.
- Preserved explicit operator control for recommendation acceptance.
- Added `bcw contacts review-safe-loop` CLI JSON support.

Validation:

- `.venv/bin/python -m pytest tests/test_contact_store.py -q` passed with 5
  tests.
- `.venv/bin/python -m pytest tests/test_cli_surfaces.py tests/test_service.py tests/test_contact_store.py -q`
  passed with 168 tests.
- `.venv/bin/python -m pytest tests/test_api.py tests/test_mcp.py -q` passed
  with 60 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/cli.py tests/test_contact_store.py`
  passed.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `.venv/bin/python scripts/check_plan_drift.py` passed.
- `.venv/bin/python -m pytest -q` passed with 357 tests.
- `codegraph sync /home/ecochran76/workspace.local/business-card-watchdog && codegraph status /home/ecochran76/workspace.local/business-card-watchdog`
  reported the index already up to date, 60 files, 1,928 nodes, and 2,562
  edges.

Safety:

- This slice did not accept recommendations automatically, mutate contact
  fields, run enrichment providers, public-web search, live lookup/write/readback,
  Google Contacts writes, Odoo writes, or Odollo writes.

## Turn 283 | 2026-06-22

Executed Plan 0072 as the contact review-state API/MCP parity slice under Plan
0060 Milestone 4.

Implemented:

- Added FastAPI endpoints for contact review recommendation recording, review
  state listing, host-owned decisions, and bounded safe-loop execution.
- Added MCP tools for the same contact review-state operations.
- Added API and MCP parity tests for proposed recommendations, review-state
  listing, explicit reject decisions, and safe auto-rejection.
- Updated Plan 0060 Milestone 4 status to complete for the current scope.

Validation:

- `.venv/bin/python -m pytest tests/test_api.py::test_api_contact_review_state_safe_loop_parity tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_contact_review_state_safe_loop_parity -q`
  passed with 3 tests.
- `.venv/bin/python -m pytest tests/test_api.py tests/test_mcp.py -q` passed
  with 62 tests.
- `.venv/bin/ruff check src/business_card_watchdog/api.py src/business_card_watchdog/mcp.py tests/test_api.py tests/test_mcp.py`
  passed.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `.venv/bin/python scripts/check_plan_drift.py` passed.
- `.venv/bin/python -m pytest -q` passed with 359 tests.
- `codegraph sync /home/ecochran76/workspace.local/business-card-watchdog && codegraph status /home/ecochran76/workspace.local/business-card-watchdog`
  reported the index already up to date, 60 files, 1,943 nodes, and 2,352
  edges.

Safety:

- This slice did not accept recommendations automatically, mutate contact
  fields, process configured SyncThing/private watch inputs, run OCR/App
  Intelligence, run enrichment providers, public-web search, live
  lookup/write/readback, Google Contacts writes, Odoo writes, or Odollo writes.

## Turn 284 | 2026-06-22

Executed Plan 0073 as the first Plan 0060 Milestone 5 provider-contract slice.

Implemented:

- Added `enrichment.providers.people_data_labs` config support with a
  disabled-by-default provider, `PDL_API_KEY`, and the Person Enrichment base
  URL.
- Added selected-provider readiness for paid enrichment while preserving Apollo
  as the default.
- Added People Data Labs preview request fields and provider handoff metadata
  without making network or paid API calls.
- Added People Data Labs explicit-result normalization into reviewable
  enrichment artifacts.
- Added API, CLI, and MCP provider-selection support for enrichment request and
  readiness surfaces.

Validation:

- `.venv/bin/python -m pytest tests/test_config.py::test_load_enrichment_config_nested_provider_tables tests/test_enrichment.py::test_people_data_labs_provider_contract_is_zero_call_and_secret_free tests/test_api.py::test_api_enrichment_request_can_select_people_data_labs_without_call tests/test_cli_surfaces.py::test_cli_enrichment_request_can_select_people_data_labs_without_call tests/test_mcp.py::test_mcp_enrichment_request_can_select_people_data_labs_without_call -q`
  passed with 5 tests.
- `.venv/bin/python -m pytest tests/test_config.py tests/test_enrichment.py -q`
  passed with 26 tests.
- `.venv/bin/python -m pytest tests/test_api.py tests/test_mcp.py -q` passed
  with 64 tests.
- `.venv/bin/python -m pytest tests/test_cli_surfaces.py -q` passed with 52
  tests.
- `.venv/bin/ruff check src/business_card_watchdog/config.py src/business_card_watchdog/enrichment.py src/business_card_watchdog/service.py src/business_card_watchdog/api.py src/business_card_watchdog/cli.py src/business_card_watchdog/mcp.py tests/test_config.py tests/test_enrichment.py tests/test_api.py tests/test_cli_surfaces.py tests/test_mcp.py`
  passed.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `.venv/bin/python scripts/check_plan_drift.py` passed.
- `.venv/bin/python -m pytest -q` passed with 363 tests.
- `codegraph sync /home/ecochran76/workspace.local/business-card-watchdog && codegraph status /home/ecochran76/workspace.local/business-card-watchdog`
  reported the index already up to date, 60 files, 1,955 nodes, and 2,209
  edges.

Safety:

- This slice did not make live People Data Labs, Apollo, public-web, Google
  Contacts, Odoo, or Odollo calls. It did not run paid API enrichment, process
  configured SyncThing/private watch inputs, mutate contact fields from provider
  output, or write sink records.

## Turn 285 | 2026-06-22

Executed Plan 0074 as the enrichment review-provenance projection slice under
Plan 0060 Milestone 5.

Implemented:

- Added `enrichment_proposal_review` to projected contact asset lineage.
- Projected `enrichment_merge_review` and `enrichment_proposal_review` artifacts
  as enrichment attempts with meaningful review states.
- Added projected review summaries for reviewer, approved fields, source
  provider, source result schema, accepted/rejected counts, and proposal
  decisions.
- Preserved idempotent reprojection through stable enrichment attempt IDs.
- Updated Plan 0060 Milestone 5 to complete for the current scope.

Validation:

- `.venv/bin/python -m pytest tests/test_contact_store.py::test_contact_store_projects_enrichment_review_provenance -q`
  passed with 1 test.
- `.venv/bin/python -m pytest tests/test_contact_store.py -q` passed with 6
  tests.
- `.venv/bin/ruff check src/business_card_watchdog/contact_store.py tests/test_contact_store.py`
  passed.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `.venv/bin/python scripts/check_plan_drift.py` passed.
- `.venv/bin/python -m pytest -q` passed with 364 tests.
- `codegraph sync /home/ecochran76/workspace.local/business-card-watchdog && codegraph status /home/ecochran76/workspace.local/business-card-watchdog`
  reported the index already up to date, 60 files, 1,958 nodes, and 2,212
  edges.

Safety:

- This slice did not make live enrichment, public-web, paid API, Google
  Contacts, Odoo, or Odollo calls. It did not process configured
  SyncThing/private watch inputs, automatically merge enrichment without review,
  or write sink records.

## Turn 286 | 2026-06-22

Executed Plan 0075 as the first Plan 0060 Milestone 6 routing/GWS default sink
slice.

Implemented:

- Updated generated user config to enable Google Contacts as the default dry-run
  sink.
- Set the generated Google Contacts profile to `ecochran76`.
- Kept `google_contacts_apply_enabled = false` by default.
- Preserved the wildcard route rule that routes contacts to Google Contacts.
- Added configured GWS target metadata to dry-run sink apply and lookup
  readiness payloads.
- Threaded configured sink profile context through orchestrator and service
  sink/lookup plan generation.

Validation:

- `.venv/bin/python -m pytest tests/test_config.py::test_default_config_installs_dry_run_ecochran76_gws_route tests/test_routing.py::test_generated_default_config_routes_to_ecochran76_google_contacts tests/test_sinks.py::test_dry_run_readiness_does_not_require_credentials tests/test_sinks.py::test_build_sink_plan_is_dry_run_and_action_oriented tests/test_sinks.py::test_build_sink_lookup_plan_is_zero_network_and_keyed -q`
  passed with 5 tests.
- `.venv/bin/python -m pytest tests/test_config.py tests/test_routing.py tests/test_sinks.py -q`
  passed with 31 tests.
- `.venv/bin/python -m pytest tests/test_service.py tests/test_api.py tests/test_mcp.py -q`
  passed with 176 tests.
- `.venv/bin/ruff check src/business_card_watchdog/config.py src/business_card_watchdog/sinks.py src/business_card_watchdog/service.py src/business_card_watchdog/orchestrator.py tests/test_config.py tests/test_routing.py tests/test_sinks.py`
  passed.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `.venv/bin/python scripts/check_plan_drift.py` passed.
- `.venv/bin/python -m pytest -q` passed with 366 tests.
- `codegraph sync /home/ecochran76/workspace.local/business-card-watchdog && codegraph status /home/ecochran76/workspace.local/business-card-watchdog`
  reported the index already up to date, 60 files, 1,960 nodes, and 2,072
  edges.

Safety:

- This slice did not run live Google lookup/write/readback, public-web search,
  paid enrichment, Odoo, or Odollo calls. It did not process configured
  SyncThing/private watch inputs, enable broad live writes, or bypass
  selected-target gates.

## Turn 287 | 2026-06-22

Executed Plan 0076 as the Plan 0060 Milestone 6 contact-store selected sink
state slice.

Implemented:

- Added contact-store schema version 3.
- Added first-class routing decision columns for selected sinks, selected sink
  state, selected target profile, and selected target tenant.
- Added migration backfill from legacy routing payload JSON so existing route
  rows retain selected sink metadata when available.
- Projected dry-run Google Contacts readiness metadata into durable routing
  decision columns.
- Exposed selected sinks as parsed list data in contact detail responses.

Validation:

- `.venv/bin/python -m pytest tests/test_contact_store.py::test_contact_store_migrates_selected_sink_columns_without_losing_routes tests/test_contact_store.py::test_contact_store_projects_run_idempotently -q`
  passed with 2 tests.
- `.venv/bin/python -m pytest tests/test_contact_store.py -q` passed with 7
  tests.
- `.venv/bin/python -m pytest tests/test_api.py::test_api_run_lookup_selection_packet_reports_selected_candidate tests/test_api.py::test_api_run_selected_target_approval_boundary_previews_selection tests/test_api.py::test_api_run_selected_target_command_copy_packet_requires_ack -q`
  passed with 3 tests.
- `.venv/bin/python -m pytest tests/test_service.py -q` passed with 112 tests.
- `.venv/bin/ruff check src/business_card_watchdog/contact_store.py tests/test_contact_store.py`
  passed.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `.venv/bin/python scripts/check_plan_drift.py` passed.
- `.venv/bin/python -m pytest -q` passed with 367 tests.
- `codegraph sync /home/ecochran76/workspace.local/business-card-watchdog && codegraph status /home/ecochran76/workspace.local/business-card-watchdog`
  reported the index already up to date, 60 files, 1,967 nodes, and 2,079
  edges.

Safety:

- This slice did not run live Google lookup/write/readback, public-web search,
  paid enrichment, Odoo, or Odollo calls. It did not process configured
  SyncThing/private watch inputs, create selected-live-target artifacts, or
  enable live sink writes.

## Turn 288 | 2026-06-22

Executed Plan 0077 as the Plan 0060 Milestone 6 database-backed route-selection
packet slice.

Implemented:

- Added contact-scoped route-selection approval boundary packets backed by
  contact-store routing decisions.
- Added contact-scoped route-selection command-copy packets that delegate to the
  existing selected-target acknowledgement gate.
- Blocked missing or mismatched configured GWS target profile before
  selected-target delegation.
- Exposed contact route-selection packets through service, API, CLI, and MCP.
- Marked Plan 0060 Milestone 6 complete for the no-live GWS routing scope.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_contact_route_selection_packets_use_projected_gws_route tests/test_service.py::test_service_contact_route_selection_blocks_gws_profile_mismatch tests/test_api.py::test_api_contact_route_selection_packets_use_projected_route tests/test_cli_surfaces.py::test_cli_contact_route_selection_packets_use_projected_route tests/test_mcp.py::test_mcp_contact_route_selection_packets_use_projected_route -q`
  passed with 5 tests.
- `.venv/bin/python -m pytest tests/test_service.py -q` passed with 114 tests.
- `.venv/bin/python -m pytest tests/test_api.py tests/test_cli_surfaces.py tests/test_mcp.py -q`
  passed with 119 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/api.py src/business_card_watchdog/cli.py src/business_card_watchdog/mcp.py tests/test_service.py tests/test_api.py tests/test_cli_surfaces.py tests/test_mcp.py`
  passed.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `.venv/bin/python scripts/check_plan_drift.py` passed.
- `.venv/bin/python -m pytest -q` passed with 372 tests.
- `codegraph sync /home/ecochran76/workspace.local/business-card-watchdog && codegraph status /home/ecochran76/workspace.local/business-card-watchdog`
  reported the index already up to date, 60 files, 1,983 nodes, and 2,093
  edges.

Safety:

- This slice did not run live Google lookup/write/readback, public-web search,
  paid enrichment, Odoo, or Odollo calls. It did not process configured
  SyncThing/private watch inputs, create selected-live-target artifacts, or
  enable live sink writes.

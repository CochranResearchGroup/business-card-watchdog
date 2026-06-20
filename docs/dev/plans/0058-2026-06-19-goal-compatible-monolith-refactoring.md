# Plan 0058 | Goal-Compatible Monolith Refactoring

State: CLOSED
Date: 2026-06-19

## Goal Objective

Refactor the remaining service and surface monoliths into compatibility-preserving
modules that keep `/goal` execution bounded, parallelizable, and drift-resistant.

The goal is not to reduce line count for its own sake. The goal is to make the
current dry-run, review, selected-target, and live-pilot control plane easier to
change without weakening the host-owned orchestration boundary.

## Scope

- Continue the Plan 0056 and Plan 0057 pattern: extract one cohesive
  read-only or packet-building cluster at a time behind existing public
  wrappers.
- Split large CLI, API, and MCP registration/dispatch surfaces only where a
  registry or focused module preserves explicit command, schema, route, and
  tool contracts.
- Keep service state transitions, ledger writes, sink writes, selected-target
  creation, and live pilot execution under deterministic host control.
- Make each slice small enough for `/goal` turn accounting and subagent
  validation, with stop conditions that prevent long-run drift.

## Baseline

- `service.py` remains the primary monolith at roughly 15.4k lines after Plans
  0055-0057.
- `cli.py` remains a large surface file at roughly 4.3k lines, with `main` and
  `build_parser` still carrying most command registration and dispatch.
- `mcp.py` still contains large manifest and dispatch functions, even though
  the selected packet cluster now uses `surface_registry.py`.
- `api.py` still has one large `create_app` route-registration function, while
  explicit FastAPI endpoint functions remain useful for schema readability.
- Current CodeGraph status before this plan: 49 indexed files, 1,680 nodes, and
  3,363 edges.

## Non-Goals

- Do not add a new workflow feature.
- Do not process configured SyncThing/private watch inputs.
- Do not create `selected_live_target.json`.
- Do not execute live lookup, live write, live pilot execution, or live
  readback.
- Do not write Google Contacts, Odoo, or Odollo records.
- Do not change public CLI command names, API route paths, MCP tool names,
  request fields, return payloads, text renderers, or safety counters.
- Do not extract state-transition, ledger-writing, sink-writing, or live
  execution methods until a separate plan proves a narrow compatibility and
  rollback boundary.
- Do not ask subagents to make unbounded "clean up the monolith" changes.

## Operating Contract

- Start each `/goal` slice by re-reading repo policy, `ROADMAP.md`,
  `RUNBOOK.md`, this plan, and the current drift guard.
- Capture `git status --short`, CodeGraph status, largest remaining methods,
  and the intended target cluster before editing.
- Assign subagents by cluster, not by broad file ownership.
- Keep compatibility wrappers in the old public entrypoints until tests and
  downstream surfaces prove equivalent behavior.
- Update this plan with validation evidence as slices close.
- Update `ROADMAP.md`, `RUNBOOK.md`, and `scripts/check_plan_drift.py` only
  when a slice becomes the latest completed refactor closeout.
- Stop immediately on any mismatch between plan state, roadmap pointer, runbook
  evidence, drift guard output, or public surface behavior.

## Workstreams

### WS1 | Drift Baseline And Slice Control

Owner: coordinator or validation subagent.

- Re-read policy, roadmap, runbook, Plan 0056, Plan 0057, and this plan.
- Record CodeGraph status and largest remaining service/surface functions.
- Select one slice target and write the target, non-goals, tests, and rollback
  boundary before code edits.
- Run `scripts/check_plan_drift.py` before and after closeout doc updates.
- Stop condition: stale plan/runbook/roadmap pointers, dirty unrelated changes,
  or ambiguous latest-completed state.

### WS2 | Read-Only Service Aggregator Extractions

Owner: service-refactor subagent.

- Extract one read-only service aggregator per slice.
- Candidate order:
  - `pilot_readiness_report`
  - `review_route_readiness`
  - `lookup_selection_packet`
  - `watch_dry_run_readiness`
  - `live_selection_requirements`
  - `live_pilot_status`
- Prefer clusters that compose artifacts and readiness summaries without
  mutating run/job state.
- Keep `BusinessCardService` methods as compatibility wrappers.
- Stop condition: extraction touches phase transitions, artifact writes,
  ledger events, sink calls, or selected-target creation.

### WS3 | Review And Child-Replacement Packet Modules

Owner: review-surface subagent.

- Group review-route, dry-run handoff, child replacement, and selected-target
  response packet builders into focused modules only after their tests are
  identified.
- Preserve command strings, acknowledgement wording, stop conditions, and
  no-live counters.
- Keep mutation methods such as review submission separate from read-only
  packet modules unless a later plan isolates their state boundary.
- Stop condition: rendered operator text or JSON packet shape changes outside
  an explicitly approved compatibility update.

### WS4 | Surface Registry Expansion

Owner: CLI/API/MCP subagent.

- Extend `surface_registry.py` only where it removes repeated names, route
  paths, schemas, or dispatch tables without hiding FastAPI validation or CLI
  readability.
- Candidate clusters:
  - dry-run closeout and review handoff surfaces
  - review-route readiness and lookup-selection packet surfaces
  - live selection and live pilot no-write packet surfaces
- Keep explicit endpoint functions for API routes where request models or
  dependency injection are clearer than dynamic registration.
- Stop condition: command help, API path, request model, MCP schema, or
  response payload drifts.

### WS5 | CLI Renderer And Dispatch Thinning

Owner: CLI subagent.

- Move large text renderers into focused rendering modules after their JSON
  producers are stable.
- Split parser registration into small cluster-specific helpers only when tests
  cover command spelling and option compatibility.
- Keep CLI dispatch deterministic and easy to trace from command to service
  method.
- Stop condition: any CLI command becomes harder to audit, loses JSON parity,
  or changes copy needed by operator command-copy packets.

### WS6 | Validation And Closeout

Owner: validation subagent.

- Run targeted service/CLI/API/MCP parity tests for the touched cluster.
- Run full repo validation before closing a slice:
  `.venv/bin/python -m pytest -q`, `.venv/bin/ruff check .`,
  `git diff --check`, `python3 scripts/check_plan_drift.py`, and
  `codegraph sync && codegraph status`.
- Record validation evidence in this plan and `RUNBOOK.md`.
- Update `ROADMAP.md` latest completed refactor pointer only after a slice is
  closed.

## Slice Plan

### Slice 0058-A | Read-Only Packet Extraction

Select one read-only service aggregator from WS2, extract it into a focused
module, and leave the existing `BusinessCardService` method as the wrapper.

Preferred first target: `pilot_readiness_report`, unless baseline inspection
shows stronger test coverage and lower coupling for `review_route_readiness`.

Required validation:

- Targeted service test for the selected method.
- Targeted CLI/API/MCP tests for every public surface that calls the selected
  method.
- Ruff on the touched service and extracted module.
- Full validation before closeout.

### Slice 0058-B | Matching Surface Registry Expansion

For the cluster extracted in Slice 0058-A, reuse registry constants and dispatch
metadata across MCP, CLI, and API where that reduces repetition without making
route or schema registration opaque.

Required validation:

- MCP manifest and dispatch tests.
- CLI command invocation tests.
- API route tests.
- `git diff --check` and drift guard.

### Slice 0058-C | CLI Renderer Extraction

Move the matching human-text renderer into a focused renderer module if the
renderer is large enough to justify the file split.

Required validation:

- Existing JSON tests must still pass.
- Text-output tests must preserve key operator copy and command strings.
- No new live or private-source behavior may be introduced.

## Acceptance Criteria

- Plan 0058 records a `/goal` objective, workstreams, subagent boundaries,
  stop conditions, slice plan, acceptance criteria, and validation rules.
- At least one additional read-only service aggregator is extracted behind a
  compatibility wrapper before the plan closes.
- Any registry expansion preserves public CLI/API/MCP compatibility.
- Any CLI renderer extraction preserves operator-facing command copy and JSON
  parity.
- Drift guard passes after closeout docs are updated.
- Targeted parity tests pass for every touched public surface.
- Full repo validation passes before closing the plan.
- CodeGraph is synced after the final slice.

## Validation

- Slice 0058 targeted parity validation passed:
  `.venv/bin/python -m pytest tests/test_service.py::test_service_run_summary_and_review_queue tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_cli_surfaces.py::test_cli_runs_and_jobs_use_recorded_runtime_state tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service tests/test_mcp.py::test_mcp_jsonl_server_lists_and_calls_tools -q`
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

## Closeout

Plan 0058 completed Slices 0058-A through 0058-C for the pilot-readiness
cluster.

Slice 0058-A extracted `BusinessCardService.pilot_readiness_report` into
`src/business_card_watchdog/pilot_readiness.py` behind the existing service
wrapper. Slice 0058-B moved the matching MCP tool manifest/dispatch, CLI parser
registration/dispatch, and API route path constant into
`surface_registry.py`. Slice 0058-C moved the pilot-readiness CLI text renderer
into `src/business_card_watchdog/cli_renderers.py`.

The public CLI command, API route path, MCP tool name/schema, JSON payload,
operator text, no-live counters, and compatibility wrapper are preserved.
Further decomposition should continue with the next read-only packet cluster,
most likely `review_route_readiness` plus `lookup_selection_packet`, under a
new bounded plan.

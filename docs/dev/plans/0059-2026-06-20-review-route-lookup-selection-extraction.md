# Plan 0059 | Review Route And Lookup Selection Extraction

State: CLOSED
Date: 2026-06-20

## Scope

Extract the review-route readiness and lookup-selection packet cluster from
`BusinessCardService` while preserving the existing CLI, API, and MCP public
surfaces.

This is the bounded follow-on named by `ROADMAP.md` after Plan 0058. CodeGraph
shows `lookup_selection_packet` depends on `review_route_readiness`, and
`review_route_readiness` composes dry-run closeout, dry-run review handoff, and
review-bundle state. Keep this cluster together so the extracted module owns
the local review/route/lookup packet composition boundary.

## Baseline

- Latest completed refactor plan: Plan 0058.
- Current branch was pushed to `upstream/main` at commit `706070c`.
- `BusinessCardService.review_route_readiness` remains inline in
  `service.py`.
- `BusinessCardService.lookup_selection_packet` remains inline in `service.py`.
- `lookup_selection_packet` calls `review_route_readiness(write=False)`.
- CLI, API, MCP, and service tests already cover both public surfaces.
- Public compatibility contract:
  - CLI commands: `bcw runs review-route-readiness` and
    `bcw runs lookup-selection-packet`.
  - API routes: `GET /runs/{run_id}/review-route-readiness` and
    `POST /runs/{run_id}/lookup-selection-packet`.
  - MCP tools: `business_card_watchdog_review_route_readiness` and
    `business_card_watchdog_lookup_selection_packet`.

## Non-Goals

- Do not add a workflow feature.
- Do not process configured SyncThing/private watch inputs.
- Do not create `selected_live_target.json`.
- Do not execute live lookup, live write, live pilot execution, or live
  readback.
- Do not write Google Contacts, Odoo, or Odollo records.
- Do not change command names, route paths, MCP tool names, request fields,
  response payloads, operator text, ledger event names, or artifact names.
- Do not extract live-selection, selected-target creation, lookup smoke,
  write-pilot, readback-pilot, or closeout execution code in this plan.

## Workstreams

### WS1 | Baseline And Compatibility Guard

- Re-read repo policy, `ROADMAP.md`, `RUNBOOK.md`, Plan 0058, and this plan.
- Capture `git status --short --branch`, CodeGraph status, and current method
  sizes before editing.
- Run `python3 scripts/check_plan_drift.py` before edits.
- Identify the exact service/API/CLI/MCP tests that prove this cluster.
- Stop condition: any stale roadmap/runbook/plan pointer or uncommitted
  unrelated change.

### WS2 | Service Cluster Extraction

- Add a focused module for review-route and lookup-selection packet building.
- Move the body of `review_route_readiness` into the module behind a builder
  function.
- Move the body of `lookup_selection_packet` into the same module behind a
  builder function.
- Keep `BusinessCardService.review_route_readiness` and
  `BusinessCardService.lookup_selection_packet` as compatibility wrappers.
- Pass the service object into the builder where existing helper access is
  required, matching the Plan 0057 and Plan 0058 extraction pattern.
- Stop condition: extraction starts changing ledger writes, artifact names,
  event names, selected-target behavior, live-selection packet behavior, or
  no-live counters.

### WS3 | Surface Registry Expansion

- Add registry constants for the two CLI command names and API route paths.
- Move the two MCP tool specs and dispatch handlers into
  `surface_registry.py`.
- Reuse registry parser/dispatch helpers from `cli.py` only if that preserves
  parser readability and existing option behavior.
- Reuse API route-path constants while keeping explicit FastAPI endpoint
  functions and request models.
- Stop condition: CLI help, API path, request model, MCP schema, or response
  payload drifts.

### WS4 | CLI Renderer Follow-On

- Move `_render_review_route_readiness_text` and
  `_render_lookup_selection_packet_text` into the focused CLI renderer module
  only after the service and registry changes are green.
- Preserve operator-facing command copy and no-JSON text output.
- Stop condition: text tests fail or command-copy wording changes.

### WS5 | Closeout And Validation

- Update this plan, `ROADMAP.md`, `RUNBOOK.md`, and
  `scripts/check_plan_drift.py` only after the slice is complete.
- Sync CodeGraph after code edits.
- Record validation evidence in this plan and the runbook.

## Acceptance Criteria

- `review_route_readiness` is no longer a large inline
  `BusinessCardService` method.
- `lookup_selection_packet` is no longer a large inline
  `BusinessCardService` method.
- Existing service wrappers remain as public compatibility entrypoints.
- CLI, API, and MCP surfaces preserve names, paths, schemas, arguments,
  defaults, output payloads, and text renderers.
- Runtime artifact names and ledger event names remain unchanged:
  `review_route_readiness`, `review_route_readiness_created`,
  `lookup_selection_packet`, and `lookup_selection_packet_created`.
- No private-source processing, live lookup, live write, live pilot execution,
  or readback is introduced.
- Drift guard passes after closeout docs are updated.
- Targeted service/API/CLI/MCP parity tests pass.
- Full repo validation passes before closing the plan.
- CodeGraph is synced after the final slice.

## Validation Plan

- Targeted service:
  `.venv/bin/python -m pytest tests/test_service.py::test_service_review_route_readiness_summarizes_review_and_route_state tests/test_service.py::test_service_lookup_selection_packet_selects_route_ready_job_without_live_calls -q`
- Targeted CLI/API/MCP:
  `.venv/bin/python -m pytest tests/test_cli_surfaces.py::test_cli_runs_review_route_readiness_reports_route_state tests/test_cli_surfaces.py::test_cli_runs_lookup_selection_packet_reports_selected_candidate tests/test_api.py::test_api_run_review_route_readiness_reports_route_state tests/test_api.py::test_api_run_lookup_selection_packet_reports_selected_candidate tests/test_mcp.py::test_mcp_review_route_readiness_reports_route_state tests/test_mcp.py::test_mcp_lookup_selection_packet_reports_selected_candidate tests/test_mcp.py::test_manifest_has_process_tool -q`
- Static and full validation:
  `.venv/bin/ruff check .`
  `.venv/bin/python -m pytest -q`
  `git diff --check`
  `.venv/bin/ruff check scripts/check_plan_drift.py`
  `python3 scripts/check_plan_drift.py`
  `codegraph sync && codegraph status`

## Closeout

Plan 0059 completed the review-route readiness and lookup-selection packet
extraction.

Implemented:

- Added `src/business_card_watchdog/review_route_packets.py`.
- Moved `review_route_readiness` into `build_review_route_readiness`.
- Moved `lookup_selection_packet` into `build_lookup_selection_packet`.
- Kept `BusinessCardService.review_route_readiness` and
  `BusinessCardService.lookup_selection_packet` as compatibility wrappers.
- Added registry constants for the review-route and lookup-selection CLI
  commands and API route paths.
- Moved the matching MCP tool specs and dispatch handlers into
  `surface_registry.py`.
- Reused registry parser/dispatch helpers from `cli.py`.
- Reused API route-path constants while keeping explicit FastAPI endpoints and
  request models.
- Moved the review-route readiness and lookup-selection text renderers into
  `cli_renderers.py`.

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

- This was a behavior-preserving extraction and surface/renderer thinning
  slice. It did not process private input, create selected targets, execute
  live lookup, write, live pilot execution, or readback, or write Google
  Contacts, Odoo, or Odollo records.

Next:

- The remaining service monolith work should continue with another bounded
  packet extraction plan rather than expanding this closed slice. Candidate
  clusters include dry-run closeout/review handoff or later live-pilot status
  read-only reporting.

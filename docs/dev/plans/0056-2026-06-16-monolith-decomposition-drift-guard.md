# Plan 0056 | Monolith Decomposition Drift Guard

State: CLOSED
Date: 2026-06-16

## Scope

Create a high-level, subagent-suitable decomposition plan for the remaining
monolith surfaces and execute the first bounded slice with explicit drift
protection.

The current repo already includes recovered Plans 0053-0055 in the working
tree. This plan must treat that dirty tree as the baseline, detect drift before
and after edits, and avoid adding new product behavior while decomposing
repetitive surface code.

## Baseline

- `service.py` remains the main monolith at more than 16k lines.
- `api.py`, `cli.py`, and `mcp.py` remain surface monoliths with large
  registration/dispatch functions.
- Plan 0055 extracted live-pilot packet bodies into
  `src/business_card_watchdog/live_pilot_packets.py`.
- Public CLI/API/MCP commands, schemas, routes, and tool names are the
  compatibility contract.

## Non-Goals

- Do not add a new workflow feature.
- Do not rewrite the full 23-hour commit chain.
- Do not process configured SyncThing/private watch inputs.
- Do not create `selected_live_target.json`.
- Do not execute live lookup, live write, or live readback.
- Do not write Google Contacts, Odoo, or Odollo records.
- Do not collapse all service/API/CLI/MCP monoliths in one slice.

## Subagent Workstreams

### WS1 | Drift Baseline And Guard

Owner: coordinator or validation subagent.

- Re-read repo policy, `ROADMAP.md`, `RUNBOOK.md`, and latest plans before
  editing.
- Capture `git status --short --branch`, CodeGraph status, current largest
  files/methods, and validation baseline.
- Add or update a lightweight drift guard that verifies plan/runbook/roadmap
  closeout pointers stay synchronized.
- Stop condition: any contradiction between roadmap, runbook, plan state,
  validation output, or current code must be reconciled before feature or
  refactor work continues.

### WS2 | Surface Registry Seed

Owner: surface/API subagent.

- Introduce a small declarative registry for the live-pilot/selected-target
  surface cluster.
- Use the registry first where the risk is lowest: MCP tool manifest and
  dispatch for the Plan 0053/0049/0050 packet cluster.
- Preserve public MCP tool names, input schemas, defaults, and return payloads.
- Stop condition: targeted MCP/service/API/CLI parity tests fail.

### WS3 | CLI/API Registry Follow-On

Owner: CLI/API subagent.

- After WS2 is stable, extend the registry into CLI parser/dispatch and API
  route metadata where it reduces repetition without dynamic route opacity.
- Keep explicit route functions where FastAPI readability or type validation
  benefits from them.
- Stop condition: command help text, route paths, or request fields drift.

### WS4 | Service Aggregator Extraction

Owner: service-refactor subagent.

- Extract one remaining service aggregator at a time, starting with
  `operator_dashboard` only after surface registry work is stable.
- Keep `BusinessCardService` wrappers as compatibility entrypoints.
- Stop condition: extraction starts changing state transition, artifact,
  ledger, sink, or command semantics.

## Slice 0056-A

Execute WS1 and the low-risk portion of WS2:

- Add `src/business_card_watchdog/surface_registry.py`.
- Register the operator live-pilot readiness packet, selected-target approval
  boundary, and selected-target command-copy packet surfaces.
- Use the registry from `mcp.py` for those tool manifest entries and dispatch.
- Add a repo drift guard under `scripts/`.
- Update `ROADMAP.md` and `RUNBOOK.md` with validation evidence.

## Slice 0056-B

Execute the remaining low-risk WS3 follow-on for the selected packet cluster:

- Reuse `surface_registry.py` constants/helpers from CLI parser registration
  and dispatch for the operator readiness and selected-target commands.
- Reuse the same route-path constants from API decorators while keeping the
  explicit FastAPI endpoint functions and request models.
- Preserve command names, route paths, request fields, defaults, schemas, and
  text renderers.

## Slice 0056-C

Execute the bounded WS4 service aggregator extraction:

- Add `src/business_card_watchdog/operator_dashboard.py`.
- Move the `operator_dashboard` aggregation body into
  `build_operator_dashboard`.
- Keep `BusinessCardService.operator_dashboard` as the compatibility
  entrypoint.
- Preserve dashboard schema, command maps, API route maps, MCP tool maps,
  safe-next-action summaries, and no-live safety counters.

## Acceptance Criteria

- Plan 0056 records subagent workstreams, drift gates, and stop conditions.
- The surface registry exists and is used by MCP, CLI, and API for the selected
  packet cluster where that does not hide explicit endpoint request validation.
- MCP manifest entries, CLI command behavior, and API route behavior remain
  equivalent for the selected packet cluster.
- `operator_dashboard` is no longer a large inline `BusinessCardService`
  method; the service keeps a wrapper compatibility entrypoint.
- Drift guard passes after closeout docs are updated.
- Targeted MCP/service/API/CLI tests pass.
- Full repo venv validation passes.
- CodeGraph is synced after the slice.

## Validation

- Slice 0056-A targeted validation passed:
  `.venv/bin/python -m pytest tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_operator_live_pilot_readiness_packet_reports_ready_boundary tests/test_mcp.py::test_mcp_selected_target_approval_boundary_previews_selection tests/test_mcp.py::test_mcp_selected_target_command_copy_packet_requires_ack tests/test_service.py::test_service_operator_live_pilot_readiness_packet_reports_ready_boundary tests/test_service.py::test_service_selected_target_approval_boundary_previews_explicit_selection tests/test_service.py::test_service_selected_target_command_copy_packet_requires_acknowledgement -q` passed with 7 tests.
- Full-plan targeted validation passed:
  `.venv/bin/python -m pytest tests/test_cli_surfaces.py::test_cli_operator_live_pilot_readiness_packet_reports_ready_boundary tests/test_cli_surfaces.py::test_cli_runs_selected_target_approval_boundary_previews_selection tests/test_cli_surfaces.py::test_cli_runs_selected_target_command_copy_packet_requires_ack tests/test_api.py::test_api_operator_live_pilot_readiness_packet_reports_ready_boundary tests/test_api.py::test_api_run_selected_target_approval_boundary_previews_selection tests/test_api.py::test_api_run_selected_target_command_copy_packet_requires_ack tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_operator_live_pilot_readiness_packet_reports_ready_boundary tests/test_mcp.py::test_mcp_selected_target_approval_boundary_previews_selection tests/test_mcp.py::test_mcp_selected_target_command_copy_packet_requires_ack tests/test_service.py::test_service_operator_dashboard_composes_no_live_readiness tests/test_cli_surfaces.py::test_cli_operator_dashboard_reports_no_live_summary -q` passed with 12 tests.
- `.venv/bin/ruff check src/business_card_watchdog/operator_dashboard.py src/business_card_watchdog/service.py src/business_card_watchdog/cli.py src/business_card_watchdog/api.py src/business_card_watchdog/surface_registry.py` passed.
- `.venv/bin/ruff check scripts/check_plan_drift.py` passed.
- `python3 scripts/check_plan_drift.py` passed.
- `.venv/bin/python -m pytest -q` passed with 333 tests.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date with 48 files, 1,672 nodes, and 3,348 edges.

## Closeout

Plan 0056 completed WS1 through WS4 for the selected packet cluster and the
first service aggregator extraction. The registry now covers MCP plus bounded
CLI/API reuse for the operator readiness and selected-target packet surfaces,
and `operator_dashboard` is extracted behind the existing
`BusinessCardService.operator_dashboard` wrapper.

Further decomposition remains intentionally incremental: broader CLI/API route
registry coverage and additional service-method extraction should each use a
new bounded plan with the same drift guard and compatibility-test pattern.

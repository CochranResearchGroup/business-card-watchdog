# Plan 0008 | Runtime Installation And Pilot Operations

State: IN_PROGRESS
Product authority: `PRODUCT_SPEC.md`
Predecessors:

- `docs/dev/plans/0005-2026-06-13-review-routing-normalization-enrichment-dedupe.md`
- `docs/dev/plans/0007-2026-06-14-live-pilot-readiness-and-evidence.md`

## Scope

Move the repo from artifact-complete pilot readiness to operator-usable runtime operations for the local workstation.

This plan covers:

- user-scope install and config readiness
- watched SyncThing source readiness and dry-run proof without committing private card data
- service/watchdog status diagnostics
- operator-selected target records for one-job live pilots
- read-only live smoke execution only after explicit target selection
- runbook evidence for restart, recovery, and safe continuation

## Non-Goals

- Do not process the real SyncThing camera directory in generic agent-loop continuation.
- Do not commit real card images, OCR dumps, credentials, tenant config, or live sink payload bodies.
- Do not run public-web enrichment or paid API enrichment unless explicitly requested for a selected run.
- Do not run live GWS/Odollo/Odoo lookup, write, or readback commands without an explicit selected run, job, sink, and operator approval record.
- Do not expand live writes beyond one job and one sink.

## Product Decisions

- Runtime readiness is separate from extraction correctness. A clean service install can still be blocked from live routing.
- The watched-folder workflow must have a zero-private-data dry-run harness before it touches the real phone sync tree.
- Target selection is a durable artifact, not a chat-only instruction, so API/MCP/CLI surfaces can agree on what was approved.
- Service health must report the active config path, data path, watched roots, last scan, queued jobs, blocked actions, and explicit next safe actions.
- Live smoke execution is read-only, but still treated as an explicit operator action because it may call external systems.

## Default Stop Rule

Safe agent-loop execution may prepare local artifacts, run fixture-backed dry runs, and inspect local readiness. It must stop before:

- processing private SyncThing images
- public-web search
- paid API enrichment
- live lookup
- live write pilot
- live readback pilot
- duplicate merge decisions
- route/apply approvals

## Execution Slices

1. `0008-A | Runtime Readiness Report`: add a run/service readiness report that checks user-scope install paths, config files, runtime directories, watcher config, service command availability, and current blocked actions.
2. `0008-B | SyncThing Watch Dry-Run Harness`: add a fixture-backed watch-source dry run that proves settle, seen-file, queue, and resume behavior without reading or committing private phone images.
3. `0008-C | Operator Target Selection Record`: add a durable selected-target artifact for one run/job/sink, with operator, timestamp, readiness references, approval scope, and stop conditions.
4. `0008-D | Read-Only Live Smoke Execution`: after explicit target selection, execute one read-only lookup smoke and import redacted results into review/dedupe artifacts.
5. `0008-E | Service Recovery Runbook`: document install/start/status/restart/resume/recover commands and add tests for status output shape where practical.

## Acceptance Criteria

- Runtime readiness is available through CLI, API, and MCP.
- Watch-source dry-run evidence can be generated from fixtures and produces no private artifacts.
- Selected-target approval is represented as a repo-defined schema and user-runtime artifact.
- Live lookup smoke remains impossible from safe continuation unless selected-target approval exists and the operator explicitly asks to execute it.
- Runbook commands explain how to install at user scope, configure paths under `~/.config/business-card-watchdog/`, store runtime state under `~/.local/share/business-card-watchdog/`, and inspect service/watch status.
- Each executed slice ends with tests, `ruff`, build, gitleaks, `git diff --check`, CodeGraph sync/status, commit, push, and CI watch.

## `/goal` Execution Model

Suggested main `/goal` prompt:

```text
Execute Plan 0008 in bounded, committed slices. Start with the next incomplete slice in docs/dev/plans/0008-2026-06-14-runtime-installation-and-pilot-operations.md. Keep safe continuation local and zero-network unless I explicitly select a run/job/sink live target. Validate, commit, push, and watch CI for each slice.
```

Recommended subagent split:

- Runtime/status subagent: inspect install/config/service surfaces and propose the readiness schema.
- Watcher subagent: exercise fixture-backed watch-source dry runs and resume behavior.
- Pilot-ops subagent: design selected-target approval records and align them with Plan 0007 handoff artifacts.
- Documentation subagent: update runbook/operator commands after code lands.

## Execution Log

### Slice 0008-A | 2026-06-14 | Runtime Readiness Report

Implemented:

- Added `business-card-watchdog.runtime-readiness.v1` as a zero-network, zero-private-data runtime readiness report.
- Added service `BusinessCardService.runtime_readiness`.
- Added CLI `bcw runtime-readiness`.
- Added API `GET /runtime/readiness`.
- Added MCP tool `business_card_watchdog_runtime_readiness`.
- Report now composes config-file evidence, user-scope runtime directory writability, business-card skill readiness, user service unit status, watcher input status, blocked checks, warning checks, safe next actions, and explicit stop conditions.

Safety:

- This slice creates/probes user-scope runtime directories only.
- It does not process private SyncThing images.
- It does not run public-web search, paid enrichment, GWS, Odollo/Odoo, live lookup, live write, or live readback commands.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_runtime_readiness_reports_user_scope_runtime_state tests/test_cli_surfaces.py::test_cli_runtime_readiness_reports_local_runtime_state tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 5 tests.

### Slice 0008-B | 2026-06-14 | SyncThing Watch Dry-Run Harness

Implemented:

- Added `business-card-watchdog.watch-dry-run-harness.v1` as a fixture-backed watcher proof.
- Added service `BusinessCardService.watch_dry_run_harness`.
- Added CLI `bcw watch-dry-run`.
- Added API `POST /watch/dry-run`.
- Added MCP tool `business_card_watchdog_watch_dry_run`.
- Harness creates an isolated synthetic image source under cache, runs one dry-run watcher scan, restarts watcher state, runs a second scan, and proves seen-file persistence prevents reprocessing.
- Harness records assertions for synthetic-source-only execution, first-scan processing, restart behavior, seen-file persistence, dry-run-only processing, and no configured watch input usage.

Safety:

- This slice uses only a synthetic image generated under the cache directory.
- It does not inspect, scan, or process configured SyncThing/private watch inputs.
- It does not invoke OCR/App Intelligence, public-web search, paid enrichment, GWS, Odollo/Odoo, live lookup, live write, or live readback commands.

Validation:

- `.venv/bin/python -m pytest tests/test_watcher.py::test_service_watch_dry_run_harness_uses_synthetic_source_only tests/test_watcher.py::test_watch_dry_run_cli_outputs_fixture_harness tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 5 tests.

### Slice 0008-C | 2026-06-14 | Operator Target Selection Record

Implemented:

- Added `business-card-watchdog.selected-live-target.v1` as durable selected run/job/sink/operator/scope approval evidence.
- Added service `BusinessCardService.select_live_target_for_job`.
- Added CLI `bcw sinks select-live-target`.
- Added API `POST /jobs/{job_id}/selected-live-target`.
- Added MCP tool `business_card_watchdog_selected_live_target`.
- Registered `selected_live_target.json` for route-refresh staleness and review-bundle visibility.
- Non-simulated lookup, write, and readback pilots now require a matching `selected_live_target.json` for the same run, job, sink, operator, and scope.

Safety:

- This slice creates zero-network, zero-write approval artifacts only.
- Simulated pilots remain usable without selected-target approval.
- Non-simulated pilots fail before adapter execution when selected-target evidence is missing or mismatched.
- No live GWS/Odollo/Odoo lookup, write, or readback command was executed.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_selected_live_target_gates_non_simulated_lookup tests/test_service.py::test_service_lookup_pilot_uses_injected_read_only_executor tests/test_service.py::test_service_write_pilot_uses_injected_executor tests/test_service.py::test_service_readback_pilot_uses_injected_executor tests/test_cli_surfaces.py::test_cli_sinks_apply_decision_writes_zero_write_artifact tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 8 tests.

### Slice 0008-D | 2026-06-14 | Read-Only Live Smoke Execution

Implemented:

- Added `business-card-watchdog.selected-lookup-smoke.v1`.
- Added service `BusinessCardService.execute_selected_lookup_smoke_for_job`.
- Added CLI `bcw sinks execute-lookup-smoke`.
- Added API `POST /jobs/{job_id}/selected-lookup-smoke`.
- Added MCP tool `business_card_watchdog_selected_lookup_smoke`.
- Registered `selected_lookup_smoke.json` for route-refresh staleness and review-bundle visibility.
- The smoke executor reads `selected_live_target.json`, enforces lookup scope, executes the non-simulated read-only lookup path, writes redacted `sink_lookup_pilot.json` and `sink_lookup_result.json`, and immediately writes `downstream_duplicate_assessment.json`.

Safety:

- This slice adds the execution surface and offline/injected proof only.
- No real GWS/Odollo/Odoo lookup was executed.
- The production path still requires selected-target approval before any non-simulated lookup adapter can run.
- The smoke executor records `writes_attempted = 0` and fails if selected target evidence is missing or mismatched.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_selected_lookup_smoke_imports_redacted_duplicate_evidence tests/test_api.py::test_api_executes_sink_lookup_pilot_with_mocked_matches tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_selected_lookup_smoke_uses_selected_target -q` passed with 4 tests.

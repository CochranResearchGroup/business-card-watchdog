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

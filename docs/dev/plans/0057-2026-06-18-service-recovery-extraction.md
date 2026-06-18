# Plan 0057 | Service Recovery Aggregator Extraction

State: CLOSED
Date: 2026-06-18

## Scope

Extract the next low-risk `BusinessCardService` read-only aggregator behind a
compatibility wrapper, using the Plan 0056 drift-guard pattern.

The selected target is `BusinessCardService.service_recovery_report`.

## Baseline

- `service.py` remains the largest source file after Plan 0056 at roughly
  15.6k lines.
- `service_recovery_report` is a sizable read-only aggregator that composes
  runtime readiness, watcher state, run summaries, pilot readiness, next
  actions, latest review-routing drill state, and no-write live-pilot handoff
  status.
- Existing service, CLI, API, and MCP tests cover the `service-recovery`
  payload shape and no-live counters.
- Public CLI/API/MCP command names, route paths, schemas, and tool names are
  the compatibility contract.

## Non-Goals

- Do not add a new workflow feature.
- Do not process configured SyncThing/private watch inputs.
- Do not create `selected_live_target.json`.
- Do not execute live lookup, live write, or live readback.
- Do not write Google Contacts, Odoo, or Odollo records.
- Do not change service recovery commands, safe-next-action ordering, schema,
  or no-live counters.
- Do not extract state-transition, ledger-writing, sink, or live-pilot
  execution methods in this plan.

## Workstreams

### WS1 | Drift Baseline

- Re-read repo policy, `ROADMAP.md`, `RUNBOOK.md`, Plan 0056, and the current
  drift guard before editing.
- Capture current git status, CodeGraph status, and largest remaining service
  methods.
- Confirm the target method is read-only and has targeted service/CLI/API/MCP
  coverage.

### WS2 | Aggregator Extraction

- Add a focused service-recovery module.
- Move the `service_recovery_report` aggregation body into that module.
- Keep `BusinessCardService.service_recovery_report` as a compatibility
  wrapper.
- Preserve all existing payload fields, command strings, stop conditions,
  safe-next-actions, and no-live counters.

### WS3 | Drift Guard And Closeout

- Update `scripts/check_plan_drift.py` so the latest refactor closeout points
  at Plan 0057 and the matching runbook evidence.
- Update `ROADMAP.md`, `RUNBOOK.md`, and this plan with validation evidence.
- Sync CodeGraph after the extraction.

## Acceptance Criteria

- Plan 0057 records scope, non-goals, acceptance criteria, validation, and
  deterministic state.
- `service_recovery_report` is no longer a large inline
  `BusinessCardService` method; the service keeps a wrapper compatibility
  entrypoint.
- Existing service/CLI/API/MCP service-recovery behavior remains equivalent.
- Drift guard passes after closeout docs are updated.
- Targeted service/CLI/API/MCP tests pass for service recovery and the
  dependent operator dashboard surface.
- Full repo venv validation passes.
- CodeGraph is synced after the slice.

## Validation

- `.venv/bin/python -m pytest tests/test_service.py::test_service_recovery_report_composes_status_and_recovery_commands tests/test_cli_surfaces.py::test_cli_service_recovery_reports_status_shape tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service tests/test_service.py::test_service_operator_dashboard_composes_no_live_readiness tests/test_cli_surfaces.py::test_cli_operator_dashboard_reports_no_live_summary -q` passed with 7 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/service_recovery.py` passed.
- `.venv/bin/python -m pytest -q` passed with 333 tests.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `.venv/bin/ruff check scripts/check_plan_drift.py` passed.
- `python3 scripts/check_plan_drift.py` passed.
- `codegraph sync && codegraph status` passed; index is up to date with 49 files, 1,680 nodes, and 3,363 edges.

## Closeout

Slice 0057-A extracted the read-only service recovery aggregator into
`src/business_card_watchdog/service_recovery.py` and left
`BusinessCardService.service_recovery_report` as the compatibility wrapper.

The extracted body preserves the service-recovery schema, command strings,
safe-next-action ordering, explicit stop conditions, and no-live counters.
Further service decomposition remains incremental; avoid extracting
state-transition, ledger-writing, sink, or live-execution methods without a
separate plan and targeted parity coverage.

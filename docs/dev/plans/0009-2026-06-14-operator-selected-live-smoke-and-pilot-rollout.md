# Plan 0009 | Operator-Selected Live Smoke And Pilot Rollout

State: READY_FOR_OPERATOR_SELECTION
Product authority: `PRODUCT_SPEC.md`
Predecessors:

- `docs/dev/plans/0004-2026-06-13-review-normalization-enrichment-dedupe-sinks.md`
- `docs/dev/plans/0007-2026-06-14-live-pilot-readiness-and-evidence.md`
- `docs/dev/plans/0008-2026-06-14-runtime-installation-and-pilot-operations.md`

## Scope

Move from offline/simulated control-plane proof to a deliberately selected production smoke path.

This plan is not a broad batch live-write rollout. It covers one explicit run, one explicit job, one explicit sink, and one explicit operator approval at a time.

## Stop Rule

Generic `/goal` continuation may inspect readiness and prepare artifacts, but it must stop before:

- scanning or processing private SyncThing images
- public-web search
- paid API enrichment
- live GWS/Odollo/Odoo lookup
- live write pilot
- live readback pilot
- duplicate merge decisions
- route/apply approvals

## Required Operator Selection

Before any live call, the operator must provide or create all of:

- `run_id`
- `job_id`
- `sink` as `google_contacts` or `odoo`
- operator name
- approval scope: `lookup`, `write`, `readback`, or `all`
- confirmation that the selected card/contact is safe for the target tenant/profile

The durable approval artifact is `selected_live_target.json`, created by:

```bash
bcw sinks select-live-target <job-id> --run-id <run-id> --sink <sink> --operator <operator> --scope lookup
```

## Execution Slices

1. `0009-A | Live Readiness Audit`: run `bcw runtime-readiness`, `bcw service recovery`, `bcw runs pilot-readiness`, and selected sink lookup readiness for the provided target. No live calls.
2. `0009-B | Read-Only Lookup Smoke`: after selected-target approval, run one live lookup smoke and import redacted downstream duplicate evidence.
3. `0009-C | Duplicate/Route Review`: inspect downstream duplicate evidence, resolve duplicates if needed, and confirm route/apply eligibility.
4. `0009-D | One-Job Write Pilot`: after selected-target approval with write scope, run one write pilot only for the selected sink.
5. `0009-E | One-Job Readback Pilot`: after selected-target approval with readback scope, verify the written/updated downstream resource.
6. `0009-F | Pilot Closeout`: write a pilot report with artifact links, write/readback evidence, stop conditions encountered, and rollback/remediation notes.

## `/goal` Execution Model

Suggested main `/goal` prompt:

```text
Execute Plan 0009 only after I provide an explicit run_id, job_id, sink, operator, and approval scope. Until then, inspect readiness and prepare documentation only. Never run live lookup, live write, live readback, public-web search, paid enrichment, or private SyncThing processing from generic continuation.
```

Recommended subagent split:

- Runtime readiness subagent: verify config, service recovery, watched-folder status, and selected run/job availability.
- Sink readiness subagent: inspect Google Contacts or Odollo/Odoo local readiness for the selected sink without making live calls.
- Review/dedupe subagent: inspect review, route, duplicate, and downstream lookup artifacts for the selected job.
- Pilot evidence subagent: after explicit live execution, assemble closeout evidence and redaction/readback checks.

## Acceptance Criteria

- No live call occurs without matching `selected_live_target.json`.
- Lookup smoke results are redacted before persistence.
- Strong downstream duplicates block write pilots until reviewed or resolved.
- Write and readback remain one job and one sink.
- GWS/Odollo/Odoo credentials, tenant state, live payload bodies, and private card data stay out of the repo.
- Each executed slice ends with tests or explicit operational readback, `gitleaks`, `git diff --check`, commit, push, and CI watch when code/docs change.

## Current State

Ready for operator target selection. No live target has been selected in this plan.

## Execution Log

### Slice 0009-A | 2026-06-14 | Live Target Candidate Report

Implemented:

- Added `business-card-watchdog.live-target-candidates.v1`.
- Added service `BusinessCardService.live_target_candidates`.
- Added CLI `bcw live-target-candidates`.
- Added API `GET /live-target-candidates`.
- Added MCP tool `business_card_watchdog_live_target_candidates`.
- Candidate reports list no-network run/job/sink target candidates, lookup readiness state, stop reasons, and the exact selected-target command the operator can run after choosing a target.

Safety:

- This slice is read-only and report-only.
- It does not create `selected_live_target.json`.
- It does not process private SyncThing inputs, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_live_target_candidates_report_blocks_unready_jobs tests/test_cli_surfaces.py::test_cli_live_target_candidates_reports_text_and_json tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 5 tests.

### Slice 0009-A2 | 2026-06-14 | Durable Live Readiness Audit

Implemented:

- Added `business-card-watchdog.live-readiness-audit.v1`.
- Added service `BusinessCardService.live_readiness_audit`.
- Added CLI `bcw live-readiness-audit`.
- Added API `POST /live-readiness-audit`.
- Added MCP tool `business_card_watchdog_live_readiness_audit`.
- The audit composes runtime readiness, service recovery, pilot readiness, and live target candidate evidence into one no-network run-level artifact.

Safety:

- This slice is readiness evidence only.
- It can write `live_readiness_audit.json` under a selected run, but it records `writes_attempted = 0` because it does not write to any sink.
- It does not create `selected_live_target.json`, process private SyncThing inputs, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_live_readiness_audit_writes_run_level_artifact tests/test_cli_surfaces.py::test_cli_live_readiness_audit_reports_text_and_json tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 5 tests.
- `.venv/bin/python -m pytest -q` passed with 206 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

### Slice 0009-A3 | 2026-06-14 | Live Selection Packet

Implemented:

- Added `business-card-watchdog.live-selection-packet.v1`.
- Added service `BusinessCardService.live_selection_packet`.
- Added CLI `bcw sinks live-selection-packet`.
- Added API `POST /jobs/{job_id}/live-selection-packet`.
- Added MCP tool `business_card_watchdog_live_selection_packet`.
- Selection packets compose the readiness audit, target candidate state, lookup readiness, and optional apply readiness for one proposed run/job/sink/scope.

Safety:

- This slice prepares operator approval evidence only.
- It can write `live_selection_packet.json` under the selected job, but it does not create `selected_live_target.json`.
- It records `approval_state = pending_operator_approval`, `writes_attempted = 0`, and `network_calls_made = 0`.
- It does not process private SyncThing inputs, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_live_selection_packet_does_not_select_target tests/test_cli_surfaces.py::test_cli_live_selection_packet_writes_no_selected_target tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 5 tests.
- `.venv/bin/python -m pytest -q` passed with 208 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

### Slice 0009-A4 | 2026-06-14 | Selected Target Audit

Implemented:

- Added `business-card-watchdog.selected-live-target-audit.v1`.
- Added service `BusinessCardService.selected_live_target_audit`.
- Added CLI `bcw sinks selected-target-audit`.
- Added API `POST /jobs/{job_id}/selected-live-target-audit`.
- Added MCP tool `business_card_watchdog_selected_live_target_audit`.
- The audit reads an existing `selected_live_target.json`, validates run/job/scope alignment, re-checks lookup/apply readiness, and reports the next matching live commands without executing them.

Safety:

- This slice is post-approval verification only.
- It can write `selected_live_target_audit.json`, but it does not create or modify `selected_live_target.json`.
- It records `writes_attempted = 0` and `network_calls_made = 0`.
- It does not process private SyncThing inputs, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_selected_live_target_gates_non_simulated_lookup tests/test_cli_surfaces.py::test_cli_selected_target_audit_reports_existing_approval tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 5 tests.
- `.venv/bin/python -m pytest -q` passed with 209 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

### Slice 0009-A5 | 2026-06-14 | Live Pilot Closeout Report

Implemented:

- Added `business-card-watchdog.live-pilot-closeout.v1`.
- Added service `BusinessCardService.build_live_pilot_closeout_for_job`.
- Added CLI `bcw sinks live-pilot-closeout`.
- Added API `POST /jobs/{job_id}/live-pilot-closeout`.
- Added MCP tool `business_card_watchdog_live_pilot_closeout`.
- The closeout report composes selected-target approval, selected-target audit, lookup smoke evidence, downstream duplicate assessment, write/readback pilot evidence, apply-pilot report state, artifact links, stop conditions, and remediation notes.

Safety:

- This slice is closeout evidence only.
- It can write `live_pilot_closeout.json`, but it does not create or modify `selected_live_target.json` and does not execute lookup, write, or readback pilots.
- It records only the already persisted `writes_attempted` and `network_calls_made` counters from pilot artifacts.
- It does not process private SyncThing inputs, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_selected_live_target_gates_non_simulated_lookup tests/test_cli_surfaces.py::test_cli_selected_target_audit_reports_existing_approval tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 5 tests.
- `.venv/bin/python -m pytest -q` passed with 209 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

### Slice 0009-A6 | 2026-06-14 | Run-Level Live Pilot Status

Implemented:

- Added `business-card-watchdog.live-pilot-status.v1`.
- Added service `BusinessCardService.live_pilot_status`.
- Added CLI `bcw runs live-pilot-status`.
- Added API `GET /runs/{run_id}/live-pilot-status`.
- Added MCP tool `business_card_watchdog_live_pilot_status`.
- The status report aggregates candidate, pre-approval packet, selected-target, selected-target audit, lookup smoke, write/readback, and closeout state across every job in a run.

Safety:

- This slice is run-level readback only.
- It can write `live_pilot_status.json` under the run, but it does not create or modify `selected_live_target.json` and does not execute lookup, write, or readback pilots.
- It records status-operation counters as zero and separates already observed pilot counters into `observed_writes_attempted` and `observed_network_calls_made`.
- It does not process private SyncThing inputs, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_selected_live_target_gates_non_simulated_lookup tests/test_service.py::test_service_live_pilot_status_does_not_double_count_closeout_totals tests/test_cli_surfaces.py::test_cli_selected_target_audit_reports_existing_approval tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 6 tests.
- `.venv/bin/python -m pytest -q` passed with 210 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

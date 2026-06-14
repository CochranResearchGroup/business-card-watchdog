# Plan 0007 | Live Pilot Readiness And Evidence

State: COMPLETE
Product authority: `PRODUCT_SPEC.md`
Predecessors:

- `docs/dev/plans/0005-2026-06-13-review-routing-normalization-enrichment-dedupe.md`
- `docs/dev/plans/0006-2026-06-14-public-upstream-hardening.md`

## Scope

Move from simulated/offline sink-pilot proof to operator-safe live-pilot readiness without broad live writes.

This plan covers:

- selected run/job/sink readiness reports before any `--no-simulate` command
- read-only live lookup readiness for Google Contacts and Odollo/Odoo
- one-job write/readback pilot readiness evidence
- CLI/API/MCP parity for readiness reports
- artifact-backed closeout evidence after any pilot attempt

## Closeout

Completed: 2026-06-14

Outcome:

- Implemented all planned slices, `0007-A` through `0007-E`.
- Added selected run/job/sink readiness and handoff artifacts before any non-simulated lookup, write, or readback command.
- Preserved CLI, API, and MCP parity for lookup readiness, write/readback readiness, operator pilot bundles, and live lookup smoke handoffs.
- Hardened non-simulated lookup artifacts so downstream duplicate assessment keeps enough metadata for idempotency while redacting raw live sink payloads.
- Registered the new pilot-bundle and lookup-smoke handoff artifacts for route-refresh staleness checks and review-bundle visibility.

Validation evidence:

- Latest full local gate passed in Slice `0007-E`: `.venv/bin/python -m pytest -q` with 193 tests, `.venv/bin/ruff check .`, `uv build --out-dir dist`, `gitleaks detect --source . --no-banner --redact --exit-code 1`, `git diff --check`, and `codegraph sync && codegraph status`.
- The latest pushed implementation commit, `509ea7b Add live lookup smoke handoff`, passed GitHub Actions run `27509492605`.

Safety boundary:

- No public-web search, paid API enrichment, GWS, Odollo/Odoo, live lookup, live write, or live readback command was executed by this plan.
- No `lookup-pilot --no-simulate` command was executed because no explicit operator-selected live target was provided.
- Live execution remains gated by selected run/job/sink readiness, handoff review, and explicit operator approval.

## Non-Goals

- Do not run live GWS/Odollo/Odoo writes from generic agent-loop continuation.
- Do not run paid enrichment.
- Do not commit real card images, OCR dumps, credentials, tenant config, or live sink payload bodies.
- Do not turn batch-wide live writes on by default.

## Product Decisions

- Live lookup is read-only but still explicit because it may call external systems.
- Live write and readback remain one-job, one-sink operations until a later policy expands scope.
- Readiness reports must explain why a selected pilot is blocked and provide the exact next safe commands.
- Local evidence can prove that a pilot is ready to attempt, but the live command itself must remain separate and operator-approved.

## Execution Slices

1. `0007-A | Live Lookup Readiness`: add selected run/job/sink readiness reports for read-only lookup pilots.
2. `0007-B | Live Lookup Result Import`: tighten lookup pilot/readback artifacts so live result import preserves redacted execution metadata and downstream duplicate state.
3. `0007-C | One-Job Write Pilot Readiness`: make write/readback readiness sink-scoped instead of all-configured-sinks scoped.
4. `0007-D | Operator Pilot Bundle`: generate a one-job pilot bundle with commands, artifacts, stop conditions, and rollback/remediation notes.
5. `0007-E | Live Smoke Handoff`: document and, only with explicit operator target selection, execute a read-only live lookup smoke.

## Default Stop Rule

Safe agent-loop execution may prepare zero-network artifacts and readiness reports. It must stop before:

- public-web search
- paid API enrichment
- live lookup
- live write pilot
- live readback pilot
- duplicate merge decisions
- route/apply approvals

## Execution Log

### Slice 0007-A | 2026-06-14 | Live Lookup Readiness

Implemented:

- Added `business-card-watchdog.live-lookup-readiness.v1` as a selected run/job/sink readiness report.
- Added service `BusinessCardService.live_lookup_readiness_report`.
- Added CLI `bcw sinks lookup-readiness <job-id> --run-id <run-id> --sink <sink>`.
- Added API `POST /jobs/{job_id}/sink-lookup-readiness`.
- Added MCP tool `business_card_watchdog_sink_lookup_readiness`.
- Updated live lookup readiness to use implemented read-only adapters and local evidence:
  - Google Contacts requires `sink.google_contacts_profile`, `gws` on `PATH`, and local auth evidence.
  - Odollo/Odoo requires configured tenant, user config, tenant home, and tenant state evidence.
- Updated the live-pilot checklist to require lookup readiness before any `--no-simulate` lookup pilot.

Safety:

- This slice adds read-only readiness reporting only.
- No public-web search, paid enrichment provider, GWS, Odollo/Odoo, or live sink calls are made.
- The report provides the explicit live lookup command, but it does not execute it.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_live_lookup_readiness_blocks_until_requirements_exist tests/test_service.py::test_service_live_lookup_readiness_ready_with_local_gws_evidence tests/test_cli_surfaces.py::test_cli_runs_and_jobs_use_recorded_runtime_state tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 6 tests.
- `.venv/bin/python -m pytest -q` passed with 189 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed and reported the index is up to date.

### Slice 0007-E | 2026-06-14 | Live Smoke Handoff

Implemented:

- Added `business-card-watchdog.sink-lookup-smoke-handoff.v1` for selected run/job/sink read-only live lookup smoke handoff.
- Added service `BusinessCardService.build_sink_lookup_smoke_handoff_for_job`.
- Added CLI `bcw sinks lookup-smoke-handoff <job-id> --run-id <run-id> --sink <sink> --approved-by <operator>`.
- Added API `POST /jobs/{job_id}/sink-lookup-smoke-handoff`.
- Added MCP tool `business_card_watchdog_sink_lookup_smoke_handoff`.
- Registered `sink_lookup_smoke_handoff.json` for route-refresh staleness and review-bundle visibility.
- Handoff payload includes readiness, selected-target commands, CLI/API/MCP next steps, artifact paths, stop conditions, and an explicit note that the handoff is not live approval.

Safety:

- This slice creates zero-network, zero-write handoff artifacts only.
- No public-web search, paid enrichment provider, GWS, Odollo/Odoo, or live sink calls are made.
- No `lookup-pilot --no-simulate` command was executed because no explicit operator-selected live target was provided in this turn.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_lookup_smoke_handoff_packages_selected_target_without_network tests/test_api.py::test_api_executes_sink_lookup_pilot_with_mocked_matches tests/test_cli_surfaces.py::test_cli_sinks_lookup_result_writes_zero_network_artifact tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 5 tests.
- `.venv/bin/python -m pytest -q` passed with 193 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed and reported the index is up to date.

### Slice 0007-D | 2026-06-14 | Operator Pilot Bundle

Implemented:

- Added `business-card-watchdog.sink-apply-pilot-bundle.v1` for one-job, selected-sink operator handoff.
- Added service `BusinessCardService.build_sink_apply_pilot_bundle_for_job`.
- Added CLI `bcw sinks apply-pilot-bundle <job-id> --run-id <run-id> --sink <sink> --operator <operator>`.
- Added API `POST /jobs/{job_id}/sink-apply-pilot-bundle`.
- Added MCP tool `business_card_watchdog_sink_apply_pilot_bundle`.
- Registered `sink_apply_pilot_bundle.json` for route-refresh staleness and review-bundle visibility.
- Bundle payload includes selected-sink commands, artifact status, requirements, missing requirements, stop conditions, and sink-specific remediation notes.

Safety:

- This slice creates zero-network, zero-write operator handoff artifacts only.
- No public-web search, paid enrichment provider, GWS, Odollo/Odoo, or live sink calls are made.
- Live write/readback remains an explicit operator command outside generic agent-loop continuation.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_apply_pilot_bundle_collects_selected_sink_commands_and_stops tests/test_api.py::test_api_sink_readback_pilot_writes_zero_write_artifact tests/test_cli_surfaces.py::test_cli_sinks_apply_decision_writes_zero_write_artifact tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 5 tests.
- `.venv/bin/python -m pytest -q` passed with 192 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed and reported the index is up to date.

### Slice 0007-C | 2026-06-14 | One-Job Write Pilot Readiness

Implemented:

- Added selected-sink scoping to `BusinessCardService.build_sink_apply_pilot_readiness_for_job`.
- Added CLI `bcw sinks apply-pilot-readiness <job-id> --run-id <run-id> --sink <sink>`.
- Added API and MCP parity for the optional selected sink.
- Filtered readiness requirements, preflight actions, write adapter requests, readback adapter requests, and sink readiness checks to the selected sink when provided.
- Added selected-sink write/readback commands to the readiness payload.
- Guarded non-simulated write pilots so a selected-sink readiness artifact cannot be reused for a different sink.
- Updated operator docs to require selected-sink readiness before a one-job live write/readback pilot.

Safety:

- This slice prepares zero-network, zero-write readiness artifacts only.
- No public-web search, paid enrichment provider, GWS, Odollo/Odoo, or live sink calls are made.
- Live write/readback remains an explicit operator command outside generic agent-loop continuation.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_apply_pilot_readiness_can_scope_to_selected_sink tests/test_api.py::test_api_sink_readback_pilot_writes_zero_write_artifact tests/test_cli_surfaces.py::test_cli_sinks_apply_decision_writes_zero_write_artifact tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 4 tests.
- `.venv/bin/python -m pytest -q` passed with 191 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed and reported the index is up to date.

### Slice 0007-B | 2026-06-14 | Live Lookup Result Import

Implemented:

- Added redacted execution metadata for non-simulated lookup pilot artifacts.
- Preserved normalized match evidence needed for downstream duplicate assessment: sink, resource ID, confidence, basis, and redacted display.
- Redacted raw adapter execution payloads and raw per-match evidence before writing `sink_lookup_pilot.json` and `sink_lookup_result.json` for non-simulated lookup pilots.
- Kept simulated/fixture lookup behavior unchanged so tests and offline review fixtures remain inspectable.
- Added tests proving redaction on live-shaped injected lookup execution while preserving downstream duplicate blocking.

Safety:

- This slice changes artifact persistence for live-shaped read-only lookup results only.
- No public-web search, paid enrichment provider, GWS, Odollo/Odoo, or live sink calls are made.
- Redaction keeps source resource IDs for idempotency/dedupe while avoiding persistence of raw contact rows.

Validation:

- `.venv/bin/python -m pytest tests/test_sinks.py::test_build_sink_lookup_pilot_redacts_live_execution_payloads tests/test_service.py::test_service_lookup_pilot_uses_injected_read_only_executor tests/test_service.py::test_service_assess_downstream_duplicates_blocks_review_and_can_resolve tests/test_api.py::test_api_executes_sink_lookup_pilot_with_mocked_matches tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 5 tests.
- `.venv/bin/python -m pytest -q` passed with 190 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed and reported the index is up to date.

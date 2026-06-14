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
bcw sinks select-live-target <job-id> --run-id <run-id> --sink <sink> --operator <operator> --scope lookup --safety-confirmation "<confirmation>"
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

- No live call occurs without matching `selected_live_target.json` that includes tenant/profile safety confirmation.
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

### Slice 0009-A10 | 2026-06-14 | Operator Selection Requirements Report

Implemented:

- Added `business-card-watchdog.live-selection-requirements.v1`.
- Added service `BusinessCardService.live_selection_requirements`.
- Added CLI `bcw live-selection-requirements`.
- Added API `POST /live-selection-requirements`.
- Added MCP tool `business_card_watchdog_live_selection_requirements`.
- The report enumerates the required operator fields for live target selection: `run_id`, `job_id`, `sink`, `operator`, `scope`, and `safety_confirmation`.
- Per candidate, the report shows selected-target existence, safety-confirmation state, abandonment state, missing operator fields, and exact selection commands.
- Live readiness, status, and handoff command maps now point operators to the requirements report.

Safety:

- This slice creates only a no-network operator requirements artifact.
- It can write `live_selection_requirements.json` under a selected run, but it does not create or modify `selected_live_target.json`.
- It records `writes_attempted = 0` and `network_calls_made = 0`.
- It does not process private SyncThing inputs, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_live_selection_requirements_report_writes_run_level_artifact tests/test_service.py::test_service_selected_live_target_gates_non_simulated_lookup tests/test_cli_surfaces.py::test_cli_live_selection_requirements_reports_text_and_json tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 6 tests.

### Slice 0009-A11 | 2026-06-14 | Downstream Duplicate Write Gate

Implemented:

- `BusinessCardService.execute_sink_write_pilot_for_job` now checks downstream duplicate evidence before writing pilot artifacts.
- If `downstream_duplicate_assessment.json` exists and its state is not `no_match`, write pilots are blocked until `duplicate_resolution.json` contains a non-`noop` decision.
- The gate applies before simulated or live write-pilot execution so pilot evidence cannot imply write eligibility while a strong downstream duplicate remains unresolved.

Safety:

- This slice adds a deterministic pre-write guard only.
- It does not process private SyncThing inputs, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.
- Existing missing-assessment behavior is unchanged; the new block is tied to explicit downstream duplicate evidence.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_write_pilot_blocks_unresolved_downstream_duplicate tests/test_service.py::test_service_assess_downstream_duplicates_blocks_review_and_can_resolve tests/test_service.py::test_service_safe_loop_and_manual_steps_complete_simulated_pilot_chain tests/test_cli_surfaces.py::test_cli_sinks_apply_decision_writes_zero_write_artifact tests/test_api.py::test_api_sink_readback_pilot_writes_zero_write_artifact tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 6 tests.

### Slice 0009-A12 | 2026-06-14 | Same-Sink Write-Before-Readback Gate

Implemented:

- `BusinessCardService.execute_sink_readback_pilot_for_job` now requires `sink_write_pilot.json` before creating readback evidence.
- The readback pilot must target the same sink as the write pilot.
- The source write pilot must be in `mock_written` or `live_written` state.
- Readback pilot artifacts now include `source_write_pilot` state, simulation mode, and resource id context.

Safety:

- This slice adds a deterministic readback-ordering guard only.
- It does not process private SyncThing inputs, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.
- The gate applies to simulated and non-simulated readback so dry-run evidence cannot imply a standalone readback path.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_readback_pilot_writes_simulated_evidence tests/test_service.py::test_service_readback_pilot_uses_injected_executor tests/test_service.py::test_service_apply_pilot_report_summarizes_write_and_readback tests/test_service.py::test_service_safe_loop_and_manual_steps_complete_simulated_pilot_chain tests/test_cli_surfaces.py::test_cli_sinks_apply_decision_writes_zero_write_artifact tests/test_api.py::test_api_sink_readback_pilot_writes_zero_write_artifact tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 7 tests.

### Slice 0009-A13 | 2026-06-14 | Apply Pilot Evidence Consistency Gate

Implemented:

- `BusinessCardService.build_sink_apply_pilot_report_for_job` now checks write/readback evidence consistency before reporting completion.
- The report is incomplete when write and readback pilot artifacts name different sinks.
- The report is incomplete when readback evidence is missing `source_write_pilot` context or that context disagrees with the write-pilot state/resource id.
- Apply pilot reports now include `consistency_errors` for review and remediation.

Safety:

- This slice validates final evidence only.
- It does not process private SyncThing inputs, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.
- It catches stale or hand-edited artifacts that bypassed earlier execution-time gates.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_apply_pilot_report_summarizes_write_and_readback tests/test_service.py::test_service_apply_pilot_report_blocks_inconsistent_write_readback tests/test_service.py::test_service_readback_pilot_writes_simulated_evidence tests/test_service.py::test_service_safe_loop_and_manual_steps_complete_simulated_pilot_chain tests/test_cli_surfaces.py::test_cli_sinks_apply_decision_writes_zero_write_artifact tests/test_api.py::test_api_sink_readback_pilot_writes_zero_write_artifact tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 7 tests.

### Slice 0009-A14 | 2026-06-14 | Closeout Requires Selected Target Audit

Implemented:

- `BusinessCardService.build_live_pilot_closeout_for_job` now requires `selected_live_target_audit.json`.
- Closeout reports now include selected-target audit state, mismatches, and safety-confirmation state.
- Closeout blocks when selected-target audit mismatches exist or when target safety confirmation is missing.

Safety:

- This slice validates closeout evidence only.
- It does not process private SyncThing inputs, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.
- Older pre-live audit state can remain blocked for readiness reasons; closeout only treats identity/safety mismatches as closeout blockers.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_selected_live_target_gates_non_simulated_lookup tests/test_service.py::test_service_live_pilot_closeout_requires_selected_target_audit tests/test_cli_surfaces.py::test_cli_selected_target_audit_reports_existing_approval tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 5 tests.

### Slice 0009-A15 | 2026-06-14 | Closeout Rejects Stale Selected Target Audit

Implemented:

- `BusinessCardService.build_live_pilot_closeout_for_job` now verifies that `selected_live_target_audit.json` matches the selected run, job, sink, operator, and scope.
- Closeout blocks when the selected target audit was created for a different scope or stale selected-target context.
- This prevents a lookup-only audit from being reused as closeout evidence for an `all`, `write`, or `readback` pilot scope.

Safety:

- This slice validates closeout evidence only.
- It does not process private SyncThing inputs, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.
- It strengthens stale-artifact detection for final pilot evidence.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_live_pilot_closeout_requires_selected_target_audit tests/test_service.py::test_service_live_pilot_closeout_rejects_stale_selected_target_audit_scope tests/test_service.py::test_service_selected_live_target_gates_non_simulated_lookup tests/test_cli_surfaces.py::test_cli_selected_target_audit_reports_existing_approval tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 6 tests.

### Slice 0009-A16 | 2026-06-14 | Status Blocks Stale Selected Target Audit

Implemented:

- Added a shared selected-target audit context check for run, job, sink, operator, scope, audit mismatches, and safety confirmation.
- Run-level live pilot status now reports `selected_target_audit_blocked` when existing audit evidence does not match the current selected target context.
- Operator handoff now routes stale selected-target audit cases to `review_selected_target_audit` instead of suggesting live lookup smoke execution.

Safety:

- This slice changes status and handoff classification only.
- It does not process private SyncThing inputs, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.
- It keeps ordinary readiness blockers separate from selected-target identity/safety mismatches so a readiness-blocked audit does not become a false stale-target stop.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_live_pilot_closeout_rejects_stale_selected_target_audit_scope tests/test_service.py::test_service_live_pilot_closeout_requires_selected_target_audit tests/test_service.py::test_service_selected_live_target_gates_non_simulated_lookup tests/test_cli_surfaces.py::test_cli_selected_target_audit_reports_existing_approval tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 6 tests.

### Slice 0009-A17 | 2026-06-14 | Selected Target Replacement Requires Abandonment

Implemented:

- `BusinessCardService.select_live_target_for_job` now refuses to overwrite an active `selected_live_target.json`.
- Selecting a replacement target is allowed only after `live_pilot_abandonment.json` records abandonment for the existing selected target creation timestamp.
- This preserves the Plan 0009 invariant that one run/job/sink target is explicitly active at a time.

Safety:

- This slice changes durable approval artifact creation only.
- It does not process private SyncThing inputs, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.
- It forces operators to preserve a durable abandonment trail before replacing a selected target.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_select_live_target_requires_abandonment_before_replacement tests/test_service.py::test_service_live_pilot_abandonment_blocks_abandoned_selected_target tests/test_service.py::test_service_selected_live_target_gates_non_simulated_lookup tests/test_cli_surfaces.py::test_cli_selected_target_audit_reports_existing_approval tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 6 tests.

### Slice 0009-A18 | 2026-06-14 | Lookup Smoke Rejects Write-Attempting Executors

Implemented:

- Non-simulated sink lookup pilots now reject adapter execution evidence that reports `writes_attempted > 0`.
- Selected lookup smoke now verifies zero writes and redacted lookup evidence before writing `selected_lookup_smoke.json`.
- A regression proves a write-attempting lookup executor fails before `sink_lookup_pilot.json`, `sink_lookup_result.json`, or `selected_lookup_smoke.json` are persisted.

Safety:

- This slice enforces the Plan 0009 read-only lookup smoke contract.
- It does not process private SyncThing inputs, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.
- It prevents unsafe lookup executor evidence from being promoted into completed pilot artifacts.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_selected_lookup_smoke_rejects_lookup_writes_attempted tests/test_service.py::test_service_selected_lookup_smoke_imports_redacted_duplicate_evidence tests/test_service.py::test_service_selected_live_target_gates_non_simulated_lookup tests/test_cli_surfaces.py::test_cli_selected_target_audit_reports_existing_approval tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 6 tests.

### Slice 0009-A19 | 2026-06-14 | Readback Pilot Rejects Write-Attempting Executors

Implemented:

- Non-simulated sink readback pilots now reject adapter execution evidence that reports `writes_attempted > 0`.
- A regression proves a write-attempting readback executor fails before `sink_readback_pilot.json` is persisted.
- This prevents readback artifacts from falsely recording zero writes when a downstream readback adapter reports a write attempt.

Safety:

- This slice enforces the Plan 0009 read-only readback contract.
- It does not process private SyncThing inputs, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.
- It validates injected/live executor evidence before durable pilot artifacts are created.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_readback_pilot_rejects_executor_writes_attempted tests/test_service.py::test_service_readback_pilot_uses_injected_executor tests/test_service.py::test_service_readback_pilot_writes_simulated_evidence tests/test_service.py::test_service_selected_live_target_gates_non_simulated_lookup tests/test_cli_surfaces.py::test_cli_selected_target_audit_reports_existing_approval tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 7 tests.

### Slice 0009-A20 | 2026-06-14 | Readback Requires Current Selected Target Write

Implemented:

- Selected live target artifacts now include a durable `selection_id`.
- Live write pilot artifacts now record the selected-target identity that authorized the write.
- Non-simulated readback pilots now reject stale write evidence if the write pilot was authorized by a different selected-target identity than the current selected target.
- Abandonment, requirements, status, and non-simulated selected-target gates now match selected targets by identity with `created_at` fallback for older artifacts.

Safety:

- This slice validates selected-target/write/readback evidence only.
- It does not process private SyncThing inputs, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.
- It prevents a write from an abandoned target from being reused as readback evidence for a replacement target.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_readback_pilot_rejects_stale_selected_target_write tests/test_service.py::test_service_readback_pilot_uses_injected_executor tests/test_service.py::test_service_select_live_target_requires_abandonment_before_replacement tests/test_service.py::test_service_live_pilot_abandonment_blocks_abandoned_selected_target tests/test_service.py::test_service_selected_live_target_gates_non_simulated_lookup tests/test_cli_surfaces.py::test_cli_selected_target_audit_reports_existing_approval tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 8 tests.

### Slice 0009-A21 | 2026-06-14 | Apply Report Checks Selected Target Evidence

Implemented:

- Readback pilot artifacts now copy the write pilot selected-target reference into `source_write_pilot.selected_target`.
- Apply pilot report consistency checks now compare write-pilot selected-target identity with readback source-write selected-target identity.
- Tampered or stale write/readback evidence now leaves `sink_apply_pilot_report.json` incomplete with `source_write_selected_target_mismatch`.

Safety:

- This slice validates final pilot evidence only.
- It does not process private SyncThing inputs, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.
- It catches stale or hand-edited readback artifacts even if execution-time selected-target gates were bypassed.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_apply_pilot_report_blocks_inconsistent_write_readback tests/test_service.py::test_service_readback_pilot_uses_injected_executor tests/test_service.py::test_service_readback_pilot_rejects_stale_selected_target_write tests/test_service.py::test_service_selected_live_target_gates_non_simulated_lookup tests/test_cli_surfaces.py::test_cli_selected_target_audit_reports_existing_approval tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 7 tests.

### Slice 0009-A22 | 2026-06-14 | Closeout Checks Selected Target Evidence

Implemented:

- Live pilot closeout now recomputes write/readback selected-target consistency instead of trusting only the prior apply report state.
- Closeout blocks if `sink_write_pilot.json` or `sink_readback_pilot.json` carries selected-target evidence that differs from the current selected live target.
- Closeout now copies apply-report consistency errors into its own report and blocks even if a stale or hand-edited apply report claims `state = complete`.

Safety:

- This slice validates closeout evidence only.
- It does not process private SyncThing inputs, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.
- It prevents stale or hand-edited final evidence from advancing a pilot closeout after selected-target replacement or artifact tampering.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_live_pilot_closeout_rejects_stale_selected_target_evidence tests/test_service.py::test_service_apply_pilot_report_blocks_inconsistent_write_readback tests/test_service.py::test_service_live_pilot_closeout_rejects_stale_selected_target_audit_scope -q` passed with 3 tests.

### Slice 0009-A23 | 2026-06-14 | Status Routes Closeout Blockers

Implemented:

- Live pilot status now reports non-missing closeout blockers separately from ordinary missing closeout artifacts.
- Status now marks a job `live_pilot_closeout_blocked` when closeout evidence exists but contains stale or inconsistent evidence blockers.
- Live pilot handoff now routes those jobs to `review_live_pilot_closeout` with the closeout command and blocker list.

Safety:

- This slice surfaces existing closeout evidence only.
- It does not process private SyncThing inputs, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.
- It keeps normal missing-artifact closeout progress separate from stale/tampered evidence blockers.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_live_pilot_closeout_rejects_stale_selected_target_evidence tests/test_service.py::test_service_live_pilot_closeout_rejects_stale_selected_target_audit_scope tests/test_service.py::test_service_live_pilot_status_does_not_double_count_closeout_totals tests/test_service.py::test_service_live_pilot_abandonment_blocks_abandoned_selected_target -q` passed with 4 tests.

### Slice 0009-A24 | 2026-06-14 | Report Selected Target Identity

Implemented:

- Live selection requirements now report `selected_target_identity`, `abandonment_identity`, and `abandonment_reason` per candidate entry.
- Live pilot status now reports the active selected-target identity and matching abandonment identity.
- Live pilot handoff now carries selected-target and abandonment identities into operator-facing next-action entries.

Safety:

- This slice surfaces existing selected-target metadata only.
- It does not process private SyncThing inputs, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.
- It makes replacement and abandonment workflows auditable without requiring operators to open raw artifact files.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_live_selection_requirements_report_writes_run_level_artifact tests/test_service.py::test_service_selected_live_target_gates_non_simulated_lookup tests/test_service.py::test_service_live_pilot_abandonment_blocks_abandoned_selected_target -q` passed with 3 tests.

### Slice 0009-A25 | 2026-06-14 | Show Target Identity in CLI Text

Implemented:

- CLI live selection requirements text now shows selected-target and abandonment identities per entry.
- CLI live pilot handoff text now shows selected-target and abandonment identities per next-action entry.
- Text-mode CLI output now lets operators reconcile active and abandoned targets without requiring `--json`.

Safety:

- This slice changes presentation only.
- It does not process private SyncThing inputs, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.
- It keeps private card/contact contents out of the CLI text while exposing durable artifact identities needed for operator control.

Validation:

- `.venv/bin/python -m pytest tests/test_cli_surfaces.py::test_cli_live_selection_requirements_reports_text_and_json tests/test_cli_surfaces.py::test_cli_selected_target_audit_reports_existing_approval -q` passed with 2 tests.

### Slice 0009-A26 | 2026-06-14 | Show Target Identity in Status Text

Implemented:

- CLI live pilot status text now shows selected-target and abandonment identities per status entry.
- Text-mode status output now matches the identity visibility already present in JSON status and text handoff surfaces.
- The CLI regression covers active selected-target status and abandoned selected-target status.

Safety:

- This slice changes presentation only.
- It does not process private SyncThing inputs, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.
- It exposes only durable selected-target artifact identities, not private card/contact contents.

Validation:

- `.venv/bin/python -m pytest tests/test_cli_surfaces.py::test_cli_selected_target_audit_reports_existing_approval -q` passed with 1 test.

### Slice 0009-A27 | 2026-06-14 | Assert Target Identity API/MCP Parity

Implemented:

- API live pilot status and handoff tests now assert selected-target identity propagation.
- API live pilot status tests now assert abandonment identity propagation after live pilot abandonment.
- MCP live pilot status and handoff tests now assert selected-target identity propagation.

Safety:

- This slice adds parity coverage only.
- It does not process private SyncThing inputs, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.
- It protects the JSON surfaces used by external operators and agents without exposing private card/contact contents.

Validation:

- `.venv/bin/python -m pytest tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 2 tests.

### Slice 0009-A28 | 2026-06-14 | Hide Stale Abandonment Identity After Replacement

Implemented:

- Live selection requirements now report an abandonment identity only when it matches the current selected target.
- Live pilot status and handoff now suppress stale abandonment identity after an abandoned target has been replaced.
- Replacement tests now prove the active replacement target is reported without carrying the previous target's abandonment identity.

Safety:

- This slice changes report interpretation only.
- It does not process private SyncThing inputs, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.
- It prevents operators from confusing a historical abandonment artifact with the current selected target.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_select_live_target_requires_abandonment_before_replacement tests/test_service.py::test_service_live_pilot_abandonment_blocks_abandoned_selected_target -q` passed with 2 tests.

### Slice 0009-A29 | 2026-06-14 | Hide Stale Abandonment State After Replacement

Implemented:

- Live selection requirements now report abandonment reason only when the abandonment matches the current selected target.
- Live pilot status and handoff now suppress stale abandonment state and reason after target replacement.
- Replacement tests now prove the active replacement target is reported without the previous target's abandonment state, reason, or identity.

Safety:

- This slice changes report interpretation only.
- It does not process private SyncThing inputs, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.
- It keeps historical abandonment artifacts from appearing as current-target state after replacement.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_select_live_target_requires_abandonment_before_replacement tests/test_service.py::test_service_live_pilot_abandonment_blocks_abandoned_selected_target -q` passed with 2 tests.

### Slice 0009-A30 | 2026-06-14 | Add Existing Target Context to Selection Packets

Implemented:

- Live selection packets now include existing selected-target identity, sink, scope, operator, and current abandonment context.
- Existing target context uses current-target abandonment semantics, so stale historical abandonment is not shown after replacement.
- Service and CLI tests now cover missing, active, abandoned, and replaced selected-target packet context.

Safety:

- This slice enriches approval-packet evidence only.
- It does not create or modify selected targets, process private SyncThing inputs, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.
- It helps operators see whether a packet would be prepared while a target already exists or has been abandoned.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_live_selection_packet_does_not_select_target tests/test_service.py::test_service_live_selection_packet_reports_existing_selected_target_context tests/test_cli_surfaces.py::test_cli_live_selection_packet_writes_no_selected_target -q` passed with 3 tests.

### Slice 0009-A31 | 2026-06-14 | Assert Selection Packet API/MCP Context

Implemented:

- API live selection packet tests now assert missing existing-target context before approval.
- MCP live selection packet tests now assert missing existing-target context before approval.
- API/MCP parity now protects the existing selected-target context added to selection packets.

Safety:

- This slice adds parity coverage only.
- It does not create or modify selected targets, process private SyncThing inputs, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.
- It protects agent/API clients from losing the selected-target context fields required for operator review.

Validation:

- `.venv/bin/python -m pytest tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 2 tests.

### Slice 0009-A32 | 2026-06-14 | Gate Replacement Packets on Abandonment

Implemented:

- Live selection packets now expose whether an existing selected target is safety-confirmed.
- Live selection packets now expose whether replacement requires abandonment and whether a new selection can proceed immediately.
- Active existing targets add a packet blocker matching the selected-target write path: abandon the current target before selecting a replacement.
- Active existing target context now includes an explicit `abandon-live-pilot` command; missing or already-abandoned targets do not.

Safety:

- This slice enriches approval-packet evidence only.
- It does not create or modify selected targets, process private SyncThing inputs, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.
- It prevents operator/API/MCP clients from treating a replacement packet as runnable while an active selected target still exists.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_live_selection_packet_does_not_select_target tests/test_service.py::test_service_live_selection_packet_reports_existing_selected_target_context tests/test_cli_surfaces.py::test_cli_live_selection_packet_writes_no_selected_target -q` passed with 3 tests.

### Slice 0009-A33 | 2026-06-14 | Assert Replacement Packet API/MCP Parity

Implemented:

- API live selection packet tests now assert active selected-target replacement gates.
- API live selection packet tests now assert abandoned selected-target replacement gates.
- MCP live selection packet tests now assert active and abandoned selected-target replacement gates.
- API/MCP parity now protects `target_safety_confirmed`, `replacement_requires_abandonment`, `can_select_replacement_now`, and `abandon_command`.

Safety:

- This slice adds parity coverage only.
- It does not create or modify selected targets outside fixture artifacts, process private SyncThing inputs, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.
- It keeps agent/API clients aligned with the deterministic replacement gate before any operator-selected live pilot.

Validation:

- `.venv/bin/python -m pytest tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 2 tests.

### Slice 0009-A34 | 2026-06-14 | Update Live Pilot Operator Checklist

Implemented:

- The read-only lookup smoke checklist now requires live selection packet, selected target, selected-target audit, status review, and tenant/profile safety confirmation.
- The write/readback pilot checklist now requires selected-target evidence with `write` or `all` scope before non-simulated writes.
- The checklist now documents replacement handling with `replacement_requires_abandonment`, `can_select_replacement_now`, and `abandon-live-pilot`.
- Stop conditions now include missing, stale, abandoned, scope-mismatched, or safety-unconfirmed selected-target evidence.

Safety:

- This slice updates operator documentation only.
- It does not create or modify selected targets, process private SyncThing inputs, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.
- It aligns the operator checklist with the deterministic selected-target gates already enforced by CLI/API/MCP surfaces.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_live_selection_packet_reports_existing_selected_target_context tests/test_cli_surfaces.py::test_cli_selected_target_audit_reports_existing_approval -q` passed with 2 tests.

### Slice 0009-A35 | 2026-06-14 | Add Live Selection Packet Text Review

Implemented:

- `bcw sinks live-selection-packet` now renders a compact text review when `--json` is omitted.
- The text review shows run, job, sink, operator, scope, existing selected-target identity, safety-confirmation status, abandonment status, replacement gate, blocked reasons, and stop conditions.
- Active selected-target text includes the `abandon-live-pilot` command before replacement.
- CLI tests now cover missing-target and active-target text output without exposing raw JSON.

Safety:

- This slice improves operator review ergonomics only.
- It does not create or modify selected targets, process private SyncThing inputs, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.
- It keeps selection packet review usable from CLI while preserving the explicit selected-target approval gate.

Validation:

- `.venv/bin/python -m pytest tests/test_cli_surfaces.py::test_cli_live_selection_packet_writes_no_selected_target tests/test_cli_surfaces.py::test_cli_selected_target_audit_reports_existing_approval -q` passed with 2 tests.

### Slice 0009-A36 | 2026-06-14 | Add Selected Target Audit Text Review

Implemented:

- `bcw sinks selected-target-audit` now renders a compact text review when `--json` is omitted.
- The text review shows state, run, job, scope, sink, operator, selected-target identity, selected-target scope, safety-confirmation state, mismatches, blocked reasons, commands, and stop conditions.
- The renderer intentionally omits raw safety-confirmation text while preserving the boolean safety gate.
- CLI tests now cover selected-target audit text output without exposing raw JSON.

Safety:

- This slice improves operator review ergonomics only.
- It does not create or modify selected targets beyond fixture audit artifacts, process private SyncThing inputs, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.
- It keeps the required selected-target audit gate reviewable from CLI before any operator-selected live pilot.

Validation:

- `.venv/bin/python -m pytest tests/test_cli_surfaces.py::test_cli_selected_target_audit_reports_existing_approval -q` passed with 1 test.

### Slice 0009-A37 | 2026-06-14 | Add Live Pilot Closeout Text Review

Implemented:

- `bcw sinks live-pilot-closeout` now renders a compact text review when `--json` is omitted.
- The text review shows closeout state, run, job, scope, sink, operator, selected-target audit state, lookup summary, write summary, readback summary, apply-report summary, missing artifacts, blockers, commands, and stop conditions.
- CLI tests now cover live-pilot closeout text output without exposing raw JSON.

Safety:

- This slice improves final closeout review ergonomics only.
- It does not create or modify selected targets, process private SyncThing inputs, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.
- It keeps closeout evidence reviewable from CLI before retrying, replacing, or closing an operator-selected pilot.

Validation:

- `.venv/bin/python -m pytest tests/test_cli_surfaces.py::test_cli_selected_target_audit_reports_existing_approval -q` passed with 1 test.

### Slice 0009-A38 | 2026-06-14 | Align Checklist With Text Review Surfaces

Implemented:

- The live pilot checklist now uses text-mode review commands for `live-selection-packet`, `selected-target-audit`, and `live-pilot-closeout`.
- The checklist keeps JSON on artifact-producing commands and notes when to add `--json` for archival structured output.
- The closeout checklist now previews closeout with `--no-write` before persisting the final `live_pilot_closeout.json`.

Safety:

- This slice updates operator documentation only.
- It does not create or modify selected targets, process private SyncThing inputs, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.
- It aligns the live pilot checklist with the CLI text review surfaces used before live execution.

Validation:

- `.venv/bin/python -m pytest -q` passed with 223 tests.

### Slice 0009-A39 | 2026-06-14 | Add README Live Pilot Front Door

Implemented:

- README now includes an operator-selected live pilot section.
- The section states that live lookup/write/readback are not part of generic continuation or broad batch automation.
- The section shows the current text-mode selected-target review sequence before any non-simulated sink call.
- The section points operators to the full live pilot checklist for lookup, write, readback, and closeout.

Safety:

- This slice updates operator documentation only.
- It does not create or modify selected targets, process private SyncThing inputs, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.
- It makes the repo front door match Plan 0009's explicit one-run, one-job, one-sink live-pilot boundary.

Validation:

- `.venv/bin/python -m pytest -q` passed with 223 tests.

### Slice 0009-A40 | 2026-06-14 | Add Lookup Smoke Handoff Text Review

Implemented:

- `bcw sinks lookup-smoke-handoff` now renders a compact text review when `--json` is omitted.
- The text review shows state, run, job, sink, approver, read-only status, readiness state, missing requirements, artifact existence, next commands, stop conditions, and the operator note.
- CLI tests now cover lookup smoke handoff text output without exposing raw JSON.

Safety:

- This slice improves operator review ergonomics only.
- It does not process private SyncThing inputs, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.
- It keeps the read-only lookup smoke handoff reviewable before an operator explicitly runs `lookup-pilot --no-simulate`.

Validation:

- `.venv/bin/python -m pytest tests/test_cli_surfaces.py::test_cli_sinks_lookup_result_writes_zero_network_artifact -q` passed with 1 test.

### Slice 0009-A41 | 2026-06-14 | Add Apply Pilot Bundle Text Review

Implemented:

- `bcw sinks apply-pilot-bundle` now renders a compact text review when `--json` is omitted.
- The text review shows state, run, job, sink, operator, mock/live pilot eligibility, readiness state, requirements, missing requirements, write/readback/report commands, stop conditions, and remediation notes.
- CLI tests now cover apply pilot bundle text output without exposing raw JSON.

Safety:

- This slice improves operator review ergonomics only.
- It does not process private SyncThing inputs, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.
- It keeps the one-job write/readback pilot bundle reviewable before an operator explicitly runs non-simulated write or readback commands.

Validation:

- `.venv/bin/python -m pytest tests/test_cli_surfaces.py::test_cli_sinks_apply_decision_writes_zero_write_artifact -q` passed with 1 test.

### Slice 0009-A42 | 2026-06-14 | Add Apply Pilot Report Text Review

Implemented:

- `bcw sinks apply-pilot-report` now renders a compact text review when `--json` is omitted.
- The text review shows state, run, job, reason, readiness/apply/readback-request evidence, observed write/network counts, report path, per-sink write/readback status, missing artifacts, consistency errors, and artifact paths.
- Operator review docs now use the text report by default and reserve `--json` for structured handoff output.
- CLI tests now cover apply pilot report text output without exposing raw JSON.

Safety:

- This slice improves operator review ergonomics only.
- It writes the existing local `sink_apply_pilot_report.json` artifact but does not execute lookup, write, readback, GWS/Odollo/Odoo, public-web search, paid enrichment, or private SyncThing processing.
- It keeps apply pilot evidence reviewable before an operator explicitly proceeds to closeout or live follow-up.

Validation:

- `.venv/bin/python -m pytest tests/test_cli_surfaces.py::test_cli_sinks_apply_decision_writes_zero_write_artifact -q` passed with 1 test.

### Slice 0009-A43 | 2026-06-14 | Align Generated Commands With Text Reviews

Implemented:

- Live pilot closeout, status, handoff, and abandonment command maps now prefer text-mode review/readiness commands where text renderers exist.
- Execution and durable approval commands remain explicit JSON handoffs where they create or drive approval/execution artifacts.
- CLI and service tests now assert that generated operator review commands stay text-first for selected-target audit, apply pilot report, closeout, live status, handoff, readiness audit, and target candidates.

Safety:

- This slice changes generated next-step command text only.
- It does not process private SyncThing inputs, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.
- It keeps live execution gated by selected-target approval and explicit operator commands.

Validation:

- `.venv/bin/python -m pytest tests/test_cli_surfaces.py::test_cli_selected_target_audit_reports_existing_approval tests/test_service.py::test_service_live_pilot_closeout_rejects_stale_selected_target_evidence -q` passed with 2 tests.

### Slice 0009-A44 | 2026-06-14 | Align Selection Requirements Commands With Text Reviews

Implemented:

- Live selection requirements now generate text-mode review/readiness commands for selection packets, live target candidates, live readiness audits, and the requirements report itself.
- Durable selected-target approval remains an explicit JSON command because it creates `selected_live_target.json`.
- CLI and service tests now pin both filtered and unfiltered requirements command maps.

Safety:

- This slice changes generated next-step command text only.
- It does not create selected targets, process private SyncThing inputs, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.
- It keeps live execution gated by selected-target approval and explicit operator commands.

Validation:

- `.venv/bin/python -m pytest tests/test_cli_surfaces.py::test_cli_live_selection_requirements_reports_text_and_json tests/test_service.py::test_service_live_selection_requirements_report_writes_run_level_artifact -q` passed with 2 tests.

### Slice 0009-A45 | 2026-06-14 | Render Selection Requirement Commands

Implemented:

- `bcw live-selection-requirements` text output now includes per-candidate selection packet and selected-target approval commands.
- The text output now also shows the run-level target-candidates, readiness-audit, and requirements refresh commands.
- CLI tests now assert that operators can see the next commands without requesting JSON.

Safety:

- This slice changes text presentation only.
- It does not create selected targets, process private SyncThing inputs, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.
- The selected-target approval command remains explicit and JSON-producing because it creates durable approval evidence.

Validation:

- `.venv/bin/python -m pytest tests/test_cli_surfaces.py::test_cli_live_selection_requirements_reports_text_and_json -q` passed with 1 test.

### Slice 0009-A46 | 2026-06-14 | Make Selection Requirements the Operator Front Door

Implemented:

- README and live-pilot checklists now start selected-target approval evidence with `bcw live-selection-requirements --no-write`.
- Lookup and write/readback checklist paths now tell operators to use the requirements report for candidate-specific packet and approval commands.
- The selected-target approval command remains explicit and JSON-producing because it creates durable approval evidence.

Safety:

- This slice changes operator documentation only.
- It does not create selected targets, process private SyncThing inputs, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.
- It keeps the documented workflow aligned with the no-call requirements report before any selected-target approval.

Validation:

- `.venv/bin/python -m pytest tests/test_cli_surfaces.py::test_cli_live_selection_requirements_reports_text_and_json -q` passed with 1 test.

### Slice 0009-A47 | 2026-06-14 | Render Live Readiness Audit Commands

Implemented:

- Live readiness audit command maps now use text-mode target-candidates and selection-requirements commands.
- `bcw live-readiness-audit` text output now renders next-step commands for target candidates, selection requirements, runtime readiness, service recovery, and pilot readiness.
- CLI tests now assert that the audit text is sufficient to continue to the next no-call operator review surface without requesting JSON.

Safety:

- This slice changes command presentation only.
- It does not create selected targets, process private SyncThing inputs, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.
- It keeps the live readiness audit as no-call evidence before any selected-target approval.

Validation:

- `.venv/bin/python -m pytest tests/test_cli_surfaces.py::test_cli_live_readiness_audit_reports_text_and_json -q` passed with 1 test.

### Slice 0009-A48 | 2026-06-14 | Render Live Target Candidate Commands

Implemented:

- Live target candidate approval commands now include `--json` because selected-target approval creates durable evidence.
- `bcw live-target-candidates` text output now renders per-candidate inspect, pilot-readiness, lookup-readiness, and select-target commands.
- The candidate report now also exposes no-call handoff commands for live readiness audit and selection requirements.
- CLI tests now assert that candidate text is actionable without requesting JSON.

Safety:

- This slice changes command presentation only.
- It does not create selected targets, process private SyncThing inputs, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.
- It keeps selected-target approval explicit and JSON-producing while making the no-call candidate report usable as a CLI handoff.

Validation:

- `.venv/bin/python -m pytest tests/test_cli_surfaces.py::test_cli_live_target_candidates_reports_text_and_json -q` passed with 1 test.

### Slice 0009-A49 | 2026-06-14 | Expose Safe Continuation Policy

Implemented:

- `next_actions` now labels each action with `safe_to_auto_continue` and `requires_explicit_operator_action`.
- `run_next_actions` now returns sink/live operation counters, the safe-auto action set, the explicit-operator action set, and stop conditions for subagent orchestration.
- Service and CLI tests now assert that deterministic safe actions are auto-continuable while review/live/manual actions remain explicit operator actions.

Safety:

- This slice exposes policy metadata only.
- It does not process private SyncThing inputs, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.
- `run_next_actions` continues to stop at explicit operator actions and reports zero sink writes and zero network calls from deterministic safe continuation.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_next_actions_recommends_review_for_needs_review_job tests/test_service.py::test_service_run_next_actions_executes_safe_steps_until_manual_decision tests/test_service.py::test_service_next_actions_recommends_live_apply_after_decision tests/test_cli_surfaces.py::test_cli_runs_and_jobs_use_recorded_runtime_state tests/test_cli_surfaces.py::test_cli_jobs_review_records_submission -q` passed with 5 tests.

### Slice 0009-A50 | 2026-06-14 | Machine-Readable Operator Selection Prompt

Implemented:

- `live_selection_requirements` now includes `operator_response_contract` so `/goal` and subagents can pause on an exact required response shape.
- Each selection requirement entry now includes `operator_response_template`, `operator_prompt`, and `copyable_approval_fields`.
- CLI text for `bcw live-selection-requirements` now renders the operator response template next to the packet and selected-target commands.

Safety:

- This slice adds prompt/contract metadata only.
- It does not create `selected_live_target.json`, process private SyncThing inputs, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.
- The response contract explicitly records `creates_selected_live_target = false`; the operator must still run the selected-target command to create durable approval evidence.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_live_selection_requirements_report_writes_run_level_artifact tests/test_cli_surfaces.py::test_cli_live_selection_requirements_reports_text_and_json -q` passed with 2 tests.

### Slice 0009-A51 | 2026-06-14 | API/MCP Operator Selection Contract Parity

Implemented:

- API regression coverage now asserts that `POST /live-selection-requirements` exposes the operator response contract.
- MCP regression coverage now asserts that `business_card_watchdog_live_selection_requirements` exposes both the top-level contract and per-entry response template fields.
- The parity tests protect `/goal`, subagent, API, and MCP clients from losing the same explicit operator-selection handoff available in the CLI.

Safety:

- This slice adds test coverage only.
- It does not create `selected_live_target.json`, process private SyncThing inputs, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.

Validation:

- `.venv/bin/python -m pytest tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 2 tests.

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

### Slice 0009-A7 | 2026-06-14 | Operator Live Pilot Handoff

Implemented:

- Added `business-card-watchdog.live-pilot-handoff.v1`.
- Added service `BusinessCardService.live_pilot_handoff`.
- Added CLI `bcw runs live-pilot-handoff`.
- Added API `GET /runs/{run_id}/live-pilot-handoff`.
- Added MCP tool `business_card_watchdog_live_pilot_handoff`.
- The handoff turns live pilot status entries into operator-facing next actions, exact next commands, stop reasons, selected-target context, and per-run action counts.

Safety:

- This slice is handoff/readback only.
- It can write `live_pilot_handoff.json` under the run, but it does not create or modify `selected_live_target.json` and does not execute lookup, write, or readback pilots.
- It records status-operation counters as zero and preserves already observed pilot counters from the status report.
- It does not process private SyncThing inputs, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_selected_live_target_gates_non_simulated_lookup tests/test_cli_surfaces.py::test_cli_selected_target_audit_reports_existing_approval tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 5 tests.
- `.venv/bin/python -m pytest -q` passed with 210 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

### Slice 0009-A8 | 2026-06-14 | Live Pilot Abandonment Gate

Implemented:

- Added `business-card-watchdog.live-pilot-abandonment.v1`.
- Added service `BusinessCardService.live_pilot_abandon_for_job`.
- Added CLI `bcw sinks abandon-live-pilot`.
- Added API `POST /jobs/{job_id}/live-pilot-abandonment`.
- Added MCP tool `business_card_watchdog_live_pilot_abandonment`.
- Live pilot status and handoff now report abandoned selected targets, and non-simulated selected-target gates refuse the abandoned selected target.

Safety:

- This slice is abandonment/readback only.
- It writes `live_pilot_abandonment.json`, but it does not delete or modify `selected_live_target.json` and does not execute lookup, write, or readback pilots.
- It records operation counters as zero and requires an explicit operator plus reason.
- It does not process private SyncThing inputs, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_live_pilot_abandonment_blocks_abandoned_selected_target tests/test_cli_surfaces.py::test_cli_selected_target_audit_reports_existing_approval tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 5 tests.
- `.venv/bin/python -m pytest -q` passed with 211 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

### Slice 0009-A9 | 2026-06-14 | Selected Target Safety Confirmation Gate

Implemented:

- `bcw sinks select-live-target` now requires `--safety-confirmation`.
- API `POST /jobs/{job_id}/selected-live-target` now requires `safety_confirmation`.
- MCP `business_card_watchdog_selected_live_target` now requires `safety_confirmation`.
- Selected target artifacts now persist `target_safety_confirmed` and `target_safety_confirmation`.
- Selected target audits and non-simulated selected-target gates now reject selected targets that lack tenant/profile safety confirmation.
- Generated selection commands now include a safety-confirmation placeholder.

Safety:

- This slice strengthens approval evidence only.
- It does not create selected targets from generic continuation, process private SyncThing inputs, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_selected_live_target_gates_non_simulated_lookup tests/test_service.py::test_service_live_pilot_abandonment_blocks_abandoned_selected_target tests/test_cli_surfaces.py::test_cli_selected_target_audit_reports_existing_approval tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 6 tests.
- `.venv/bin/python -m pytest -q` passed with 211 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

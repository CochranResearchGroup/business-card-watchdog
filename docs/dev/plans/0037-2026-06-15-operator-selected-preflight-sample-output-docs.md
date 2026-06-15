# Plan 0037 | Operator-Selected Preflight Sample Output Docs

State: CLOSED
Product authority: `PRODUCT_SPEC.md`

## Scope

Add synthetic sample output for the operator-selected live smoke preflight so
operators and agent loops can review the pre-selection boundary before choosing
a real run, job, sink, operator, and scope.

## Non-Goals

- Do not process private SyncThing images.
- Do not run public-web search or paid enrichment.
- Do not execute live Google Contacts, Odoo, or Odollo lookup/write/readback.
- Do not create real selected-target approval outside the synthetic drill.
- Do not claim live sink readiness or write/readback success.

## Acceptance Criteria

- `drills live-pilot-rehearsal` writes a dedicated preflight sample markdown
  artifact.
- The sample output path is exposed under `sample_outputs`.
- The sample output is recorded in the run ledger.
- README and operations docs describe how to generate and interpret the sample.
- Focused service, CLI, API, and MCP coverage checks sample output visibility.

## Execution Log

### Slice 0037-A | 2026-06-15 | Preflight Sample Output

Status: implemented.

Implemented:

- Added `operator_selected_live_smoke_preflight_sample_output.md` generation to
  `drills live-pilot-rehearsal`.
- Added `sample_outputs.operator_selected_live_smoke_preflight_markdown_path`
  to the drill payload.
- Added `operator_selected_live_smoke_preflight_sample_output` as a run
  artifact kind.
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

- This slice created synthetic preflight sample output only. It did not process
  private SyncThing images, run public-web search, call paid enrichment,
  execute live lookup/write/readback, or write Google Contacts/Odoo/Odollo
  records.

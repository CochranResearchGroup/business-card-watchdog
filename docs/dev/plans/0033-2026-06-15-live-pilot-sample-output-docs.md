# Plan 0033 | Live Pilot Sample Output Documentation

State: CLOSED
Product authority: `PRODUCT_SPEC.md`

## Scope

Add sampled operator output documentation for live-pilot handoff drill packets so
operators and agent loops can inspect the packet sequence before any live sink
work.

## Non-Goals

- Do not process private SyncThing images.
- Do not run public-web search or paid enrichment.
- Do not execute live Google Contacts, Odoo, or Odollo lookup/write/readback.
- Do not treat synthetic drill command-copy text as live approval.
- Do not store raw operator response or acknowledgement text in sample output.

## Acceptance Criteria

- The live-pilot rehearsal drill writes an operator-readable markdown sample
  output artifact in the synthetic run directory.
- The sample output summarizes packet states, redaction, commands, command-copy
  status, and stop conditions.
- CLI/API/MCP drill responses expose the sample output artifact path.
- Checked-in operations documentation explains how to generate and inspect the
  sample output.
- Focused tests prove the sample output exists and omits raw safety-confirmation
  text.

## Execution Log

### Slice 0033-A | 2026-06-15 | Offline Sample Output Artifact

Status: implemented.

Implemented:

- Added `live_pilot_rehearsal_sample_output.md` generation to
  `drills live-pilot-rehearsal`.
- Added `sample_outputs.live_pilot_rehearsal_markdown_path` to the drill
  payload.
- Added a `live_pilot_rehearsal_sample_output` run artifact entry.
- Updated CLI text output to show the sample output path.
- Added operations documentation for the generated sample output.
- Added service, CLI, API, and MCP assertions for sample output visibility.

Safety:

- This slice uses synthetic fixture drill data only. It does not process private
  SyncThing images, run public-web search, call paid enrichment, execute live
  sink calls, or write Google Contacts/Odoo/Odollo records.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_live_pilot_rehearsal_drill_reaches_command_copy_gate tests/test_cli_surfaces.py::test_cli_live_pilot_rehearsal_drill_reaches_command_copy_gate tests/test_api.py::test_api_live_pilot_rehearsal_drill_reaches_command_copy_gate tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 5 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/cli.py tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py` passed.
- `.venv/bin/python -m pytest -q` passed with 271 tests.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `rg -n "live-pilot-sample-output|live_pilot_rehearsal_sample_output|Live Pilot Rehearsal Sample Output|sample_outputs" README.md docs src tests` passed.
- `uv build --out-dir dist` built source and wheel distributions.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `codegraph sync && codegraph status` passed; index is up to date.

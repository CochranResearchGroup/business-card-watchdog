# Plan 0055 | Live-Pilot Packet Extraction

State: CLOSED
Date: 2026-06-15

## Scope

Reduce the drift-driven service monolith by extracting no-live live-pilot and
selected-target packet implementations out of `BusinessCardService` and into a
focused packet module.

This is a behavior-preserving refactor. Public CLI/API/MCP surfaces, schema
strings, command text, artifact names, ledger event names, and zero-live-write
boundaries must remain unchanged.

## Non-Goals

- Do not add another operator workflow feature.
- Do not rewrite the full 23-hour commit chain.
- Do not refactor all CLI/API/MCP registration in this slice; that remains a
  separate follow-on if packet extraction stays stable.
- Do not change live-pilot, selected-target, lookup, write, or readback
  semantics.
- Do not process configured SyncThing/private watch inputs.
- Do not create `selected_live_target.json`.
- Do not execute live lookup, live write, or live readback.
- Do not write Google Contacts, Odoo, or Odollo records.

## Implementation

- Add `src/business_card_watchdog/live_pilot_packets.py`.
- Move the body of `BusinessCardService.operator_live_pilot_readiness_packet`
  into a module-level builder that takes the service object as a collaborator.
- Move the bodies of `BusinessCardService.selected_target_approval_boundary`
  and `BusinessCardService.selected_target_command_copy_packet` into
  module-level builders.
- Leave the corresponding `BusinessCardService` methods as thin compatibility
  wrappers.
- Keep Plan 0053 CLI/API/MCP/tests unchanged unless import fallout requires
  small updates.
- Update `ROADMAP.md` and `RUNBOOK.md` with the refactor closeout evidence.

## Acceptance Criteria

- `service.py` loses the large Plan 0053 readiness-packet body and the
  selected-target gate bodies, then delegates to the packet module.
- `operator_live_pilot_readiness_packet` still returns
  `business-card-watchdog.operator-live-pilot-readiness-packet.v1`.
- CLI, API, MCP, and service tests for the packet still pass.
- Full repo venv validation still passes.
- CodeGraph is synced after the extraction.

## Validation

- `.venv/bin/python -m pytest tests/test_service.py::test_service_operator_live_pilot_readiness_packet_reports_ready_boundary tests/test_service.py::test_service_selected_target_approval_boundary_previews_explicit_selection tests/test_service.py::test_service_selected_target_command_copy_packet_requires_acknowledgement tests/test_cli_surfaces.py::test_cli_operator_live_pilot_readiness_packet_reports_ready_boundary tests/test_cli_surfaces.py::test_cli_runs_selected_target_approval_boundary_previews_selection tests/test_cli_surfaces.py::test_cli_runs_selected_target_command_copy_packet_requires_ack tests/test_api.py::test_api_operator_live_pilot_readiness_packet_reports_ready_boundary tests/test_api.py::test_api_run_selected_target_approval_boundary_previews_selection tests/test_api.py::test_api_run_selected_target_command_copy_packet_requires_ack tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_operator_live_pilot_readiness_packet_reports_ready_boundary tests/test_mcp.py::test_mcp_selected_target_approval_boundary_previews_selection tests/test_mcp.py::test_mcp_selected_target_command_copy_packet_requires_ack -q` passed with 13 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/live_pilot_packets.py` passed.
- `.venv/bin/python -m pytest -q` passed with 333 tests.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

# Plan 0053 | Operator Live-Pilot Readiness Packet

State: implemented
Date: 2026-06-15

## Scope

Add a no-live operator readiness packet that composes the operator dashboard,
operator-selected live smoke preflight, and synthetic rehearsal expectations for
one selected run and optional sink.

The packet gives an agent loop one compact readback before selected-target
approval or live-pilot rehearsal. It proves that the operator-facing command
surfaces are visible and that a dashboard-ready candidate exists, while keeping
selected-target creation, private processing, and live sink activity outside the
packet.

## Non-Goals

- Do not process configured SyncThing/private watch inputs.
- Do not run OCR/App Intelligence against private images.
- Do not run public-web search or paid enrichment.
- Do not create `selected_live_target.json`.
- Do not execute live lookup, live write, or live readback.
- Do not write Google Contacts, Odoo, or Odollo records.

## Implementation

- Add `BusinessCardService.operator_live_pilot_readiness_packet`.
- Add CLI command `operator-live-pilot-readiness-packet`.
- Add API routes `GET /operator/live-pilot-readiness-packet` and
  `POST /operator/live-pilot-readiness-packet`.
- Add MCP tool
  `business_card_watchdog_operator_live_pilot_readiness_packet`.
- Report dashboard, selected-target gate, command-copy gate, and synthetic
  rehearsal readiness in one schema with zero write/network counters.
- Persist a local run artifact when requested without creating a selected
  target.

## Acceptance Criteria

- The packet returns
  `business-card-watchdog.operator-live-pilot-readiness-packet.v1`.
- A synthetic review-routing run with a ready dashboard action reports
  `state == ready_for_operator_response`.
- The packet includes selected-target approval, selected-target command-copy,
  operator preflight, and synthetic rehearsal commands.
- CLI, API, and MCP surfaces expose equivalent packet output.
- Full local validation passes before push.

## Validation

Recovered and recorded in `RUNBOOK.md` after drift audit.

- `.venv/bin/python -m pytest tests/test_service.py::test_service_operator_live_pilot_readiness_packet_reports_ready_boundary tests/test_cli_surfaces.py::test_cli_operator_live_pilot_readiness_packet_reports_ready_boundary tests/test_api.py::test_api_operator_live_pilot_readiness_packet_reports_ready_boundary tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_operator_live_pilot_readiness_packet_reports_ready_boundary -q` passed with 5 tests.
- `.venv/bin/python -m pytest -q` passed with 333 tests.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.

## Drift Recovery Note

The original loop marked this plan implemented and updated `ROADMAP.md`, but
did not add the claimed `RUNBOOK.md` closeout entry before handoff. Plan 0054
records the recovery boundary and stops further feature expansion.

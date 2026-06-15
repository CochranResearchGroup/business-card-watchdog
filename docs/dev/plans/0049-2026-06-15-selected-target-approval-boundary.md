# Plan 0049 | Selected-Target Approval Boundary

State: implemented
Date: 2026-06-15

## Scope

Add a run-level no-live packet that bridges closed lookup prerequisites to the
explicit selected-target approval command.

The packet should compose the existing live-pilot approval packet, operator
response validation, selected-target preflight, and selected-target artifact
preview. It must make the next operator boundary explicit without creating
`selected_live_target.json`.

## Non-Goals

- Do not create `selected_live_target.json`.
- Do not execute live lookup, write, or readback.
- Do not process configured SyncThing/private watch inputs.
- Do not run OCR/App Intelligence.
- Do not run public-web search or paid enrichment.
- Do not approve duplicate resolution, routing, or sink writes.

## Implementation

- Add `BusinessCardService.selected_target_approval_boundary`.
- Add CLI `bcw runs selected-target-approval-boundary <run-id> --operator <operator>`.
- Add API `POST /runs/{run_id}/selected-target-approval-boundary`.
- Add MCP tool `business_card_watchdog_selected_target_approval_boundary`.
- Persist `selected_target_approval_boundary.json` as a run-level artifact only
  when requested.

## Acceptance Criteria

- Without an operator response, the packet stops at
  `awaiting_operator_response` and shows the approval template.
- With a filled operator response, the packet reports validation, preflight,
  preview, and the explicit select-target command.
- The packet accepts placeholder operator templates but requires the filled
  response to bind the concrete operator and safety confirmation.
- Service, CLI, API, and MCP coverage prove zero-write, zero-network, no-live
  behavior and no selected-target creation.
- Full local validation passes before push.

## Validation

Completed in Turn 255 and recorded in `RUNBOOK.md`.

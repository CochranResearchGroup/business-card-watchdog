# Plan 0050 | Selected-Target Command Copy Packet

State: implemented
Date: 2026-06-15

## Scope

Add a no-live command-copy packet for the selected-target creation command.

The packet should compose the selected-target approval boundary, require a
matching operator acknowledgement, and reveal the exact
`selected-live-target-from-response --write-selected-target` command only when
the response, preflight, preview, and acknowledgement all match.

## Non-Goals

- Do not create `selected_live_target.json`.
- Do not execute live lookup, write, or readback.
- Do not process configured SyncThing/private watch inputs.
- Do not run OCR/App Intelligence.
- Do not run public-web search or paid enrichment.
- Do not store the raw acknowledgement.

## Implementation

- Add `BusinessCardService.selected_target_command_copy_packet`.
- Add CLI `bcw runs selected-target-command-copy-packet <run-id> --operator <operator>`.
- Add API `POST /runs/{run_id}/selected-target-command-copy-packet`.
- Add MCP tool `business_card_watchdog_selected_target_command_copy_packet`.
- Return selected-target creation command text only when the acknowledgement
  names the run, job, sink, and operator and includes an approval/copy verb.

## Acceptance Criteria

- Without acknowledgement, the packet is blocked and returns no command text.
- With a matching acknowledgement, the packet reaches
  `ready_for_operator_copy`.
- The returned command would create `selected_live_target.json` only if the
  operator explicitly copies and runs it.
- Service, CLI, API, and MCP coverage prove zero-write, zero-network, no-live
  behavior and no selected-target creation.
- Full local validation passes before push.

## Validation

Completed in Turn 256 and recorded in `RUNBOOK.md`.

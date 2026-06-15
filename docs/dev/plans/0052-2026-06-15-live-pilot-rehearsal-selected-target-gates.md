# Plan 0052 | Live-Pilot Rehearsal Selected-Target Gates

State: implemented
Date: 2026-06-15

## Scope

Extend the synthetic live-pilot rehearsal drill so it exercises the selected
target approval boundary and selected-target command-copy packet before the
synthetic selected target is created.

The rehearsal already proves the later no-live readiness export, execution
checklist, and live-pilot command-copy gates. This plan closes the gap between
operator response validation and selected-target creation so the synthetic drill
matches the safer operator path exposed by the dashboard.

## Non-Goals

- Do not process configured SyncThing/private watch inputs.
- Do not run OCR/App Intelligence against private images.
- Do not run public-web search or paid enrichment.
- Do not execute live lookup, live write, or live readback.
- Do not write Google Contacts, Odoo, or Odollo records.
- Do not treat synthetic selected-target creation as approval for a real target.

## Implementation

- Add `selected_target_approval_boundary` to the live-pilot rehearsal packet
  chain.
- Add `selected_target_command_copy_packet` to the rehearsal before synthetic
  selected-target creation.
- Render both selected-target gate states and commands in rehearsal sample
  output and CLI text.
- Cover service, CLI, API, and MCP rehearsal outputs with focused assertions.

## Acceptance Criteria

- `bcw drills live-pilot-rehearsal --json` reports
  `selected_target_approval_boundary.state ==
  ready_for_explicit_selected_target_creation`.
- The same drill reports `selected_target_command_copy_packet.state ==
  ready_for_operator_copy` and `creates_selected_live_target == false`.
- The generated sample output and text CLI output show both selected-target
  gates.
- Full local validation passes before push.

## Validation

Completed in Turn 258 and recorded in `RUNBOOK.md`.

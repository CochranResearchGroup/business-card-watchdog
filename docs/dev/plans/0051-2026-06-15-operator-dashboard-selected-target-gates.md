# Plan 0051 | Operator Dashboard Selected-Target Gates

State: implemented
Date: 2026-06-15

## Scope

Expose the selected-target approval boundary and selected-target command-copy
packet from the operator dashboard.

The dashboard already reports CLI, API, and MCP paths for older live-pilot and
selected-target handoff steps. This plan adds the newer no-live gates from
Plans 0049 and 0050 to those maps so operators and agent loops can discover the
current safest path without reading implementation notes.

## Non-Goals

- Do not create `selected_live_target.json`.
- Do not execute live lookup, write, or readback.
- Do not process configured SyncThing/private watch inputs.
- Do not run OCR/App Intelligence.
- Do not run public-web search or paid enrichment.
- Do not change approval, acknowledgement, or selected-target creation
  semantics.

## Implementation

- Add `selected_target_approval_boundary` to operator dashboard command, API,
  and MCP maps.
- Add `selected_target_command_copy_packet` to operator dashboard command, API,
  and MCP maps.
- Render both entries in plain-text `bcw operator-dashboard` output.
- Cover service, CLI, API, and MCP dashboard outputs with focused assertions.

## Acceptance Criteria

- `bcw operator-dashboard --run-id <run-id> --json` reports the two selected
  target gates in `commands`, `api_routes`, and `mcp_tools`.
- Plain-text `bcw operator-dashboard --run-id <run-id>` renders matching
  command/API/MCP entries.
- The dashboard remains zero-write and zero-network.
- Full local validation passes before push.

## Validation

Completed in Turn 257 and recorded in `RUNBOOK.md`.

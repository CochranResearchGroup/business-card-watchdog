# Plan 0047 | Lookup Selection Packet

State: implemented
Date: 2026-06-15

## Scope

Add a run-level packet that bridges review-route readiness to the first explicit
lookup target selection boundary.

The packet should choose a route-ready job and sink, prepare the existing
job-level live selection packet in preview mode, and show the operator exactly
what remains blocked before selected-target approval or live lookup.

## Non-Goals

- Do not create `selected_live_target.json`.
- Do not execute live lookup, write, or readback.
- Do not process configured SyncThing/private watch inputs.
- Do not run OCR/App Intelligence.
- Do not run public-web search or paid enrichment.

## Implementation

- Add `BusinessCardService.lookup_selection_packet`.
- Add CLI `bcw runs lookup-selection-packet <run-id> --operator <operator>`.
- Add API `POST /runs/{run_id}/lookup-selection-packet`.
- Add MCP tool `business_card_watchdog_lookup_selection_packet`.
- Persist `lookup_selection_packet.json` as a run-level artifact only when
  requested.

## Acceptance Criteria

- The packet consumes `review_route_readiness` and selects a route-ready row.
- The selected job-level packet is preview-only and does not create selected
  target artifacts.
- The packet reports blocked lookup requirements when the live lookup boundary
  is not ready.
- Service, CLI, API, and MCP coverage prove zero-write, zero-network, no-live
  behavior on a synthetic dry-run batch.
- Full local validation passes before push.

## Validation

Completed in Turn 253 and recorded in `RUNBOOK.md`.

# Plan 0048 | Close Lookup Prerequisites

State: implemented
Date: 2026-06-15

## Scope

Add a bounded no-live closer that advances only the local lookup prerequisite
actions needed after the lookup selection packet and before selected-target
approval.

The closer should use the existing deterministic safe-action machinery to create
lookup plan, adapter-request, recorded lookup-result, and downstream duplicate
assessment artifacts for reviewed dry-run contacts. It must report exactly what
it executed, what remains blocked, and where the operator boundary starts.

## Non-Goals

- Do not approve contact review or synthesize `reviewed_contact.json`.
- Do not create `selected_live_target.json`.
- Do not execute live lookup, write, or readback.
- Do not process configured SyncThing/private watch inputs.
- Do not run OCR/App Intelligence.
- Do not run public-web search or paid enrichment.

## Implementation

- Add `BusinessCardService.close_lookup_prerequisites`.
- Add CLI `bcw runs close-lookup-prerequisites <run-id> --operator <operator>`.
- Add API `POST /runs/{run_id}/close-lookup-prerequisites`.
- Add MCP tool `business_card_watchdog_close_lookup_prerequisites`.
- Persist `close_lookup_prerequisites.json` as a run-level artifact only when
  requested.

## Acceptance Criteria

- The closer executes only the lookup prerequisite allowlist:
  `plan_sink_lookup`, `prepare_sink_lookup_adapter`,
  `record_sink_lookup_result`, and `assess_downstream_duplicates`.
- It refuses to cross the operator boundary into selected-target creation or
  live sink calls.
- It reports before/after lookup selection packet state and explicit stop
  conditions.
- Service, CLI, API, and MCP coverage prove zero-write, zero-network, no-live
  behavior on a synthetic dry-run batch.
- Full local validation passes before push.

## Validation

Completed in Turn 254 and recorded in `RUNBOOK.md`.

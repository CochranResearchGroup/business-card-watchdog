# Plan 0045 | Dry-Run Safe Loop

State: implemented
Date: 2026-06-15

## Scope

Add a bounded deterministic agent-loop surface that executes only host-approved
safe actions after dry-run closeout and dry-run review handoff have passed.

The loop should make it possible for an agent or operator to advance dry-run
planning work without crossing into private-source processing, enrichment, or
live sink operations.

## Non-Goals

- Do not process configured SyncThing/private watch inputs.
- Do not run OCR/App Intelligence.
- Do not run public-web search or paid enrichment.
- Do not execute live lookup, write, or readback.
- Do not auto-approve explicit operator actions.

## Implementation

- Add `BusinessCardService.dry_run_safe_loop`.
- Add CLI `bcw runs dry-run-safe-loop <run-id> --limit <n>`.
- Add API `GET /runs/{run_id}/dry-run-safe-loop`.
- Add MCP tool `business_card_watchdog_dry_run_safe_loop`.
- Gate execution on dry-run review handoff.
- Recompute before/after handoff state and write `dry_run_safe_loop.json` only
  when requested.

## Acceptance Criteria

- The loop refuses to execute when dry-run closeout or handoff is blocked.
- The loop executes only actions in `_SAFE_NEXT_ACTIONS`.
- The loop reports executed/skipped rows, before/after action counts, and
  no-write live-pilot inspection commands.
- Service, CLI, API, and MCP coverage prove bounded no-live behavior on a
  synthetic dry-run batch.
- Full local validation passes before push.

## Validation

Completed in Turn 251 and recorded in `RUNBOOK.md`.

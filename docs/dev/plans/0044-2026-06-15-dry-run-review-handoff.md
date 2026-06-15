# Plan 0044 | Dry-Run Review Handoff

State: implemented
Date: 2026-06-15

## Scope

Add a deterministic post-closeout handoff that summarizes review, routing, and
safe agent-loop next steps for a completed dry-run batch.

The handoff should compose existing local-ledger surfaces instead of creating a
new review workflow:

- dry-run closeout
- run summary
- phase report
- review bundle groups
- next action counts
- safe auto actions
- explicit operator actions

## Non-Goals

- Do not process configured SyncThing/private watch inputs.
- Do not run OCR/App Intelligence.
- Do not run public-web search or paid enrichment.
- Do not execute live lookup, write, or readback.
- Do not approve live sink operations.

## Implementation

- Add `BusinessCardService.dry_run_review_handoff`.
- Add CLI `bcw runs dry-run-review-handoff <run-id>`.
- Add API `GET /runs/{run_id}/dry-run-review-handoff`.
- Add MCP tool `business_card_watchdog_dry_run_review_handoff`.
- Record `dry_run_review_handoff.json` only when requested.
- Keep live-pilot commands no-write/read-only and stop before live sink calls.

## Acceptance Criteria

- The handoff is blocked if dry-run closeout is blocked.
- The handoff reports safe auto action counts and explicit operator action counts.
- The handoff exposes review bundle, phase report, next action, and no-write live
  pilot inspection commands.
- Service, CLI, API, and MCP coverage prove no-live behavior on a synthetic
  dry-run batch.
- Full local validation passes before push.

## Validation

Completed in Turn 250 and recorded in `RUNBOOK.md`.

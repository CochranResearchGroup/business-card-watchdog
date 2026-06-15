# Plan 0043 | Dry-Run Closeout Audit

State: implemented
Date: 2026-06-15

## Scope

Add a run-level dry-run closeout audit for the operator-selected private or
synthetic dry-run boundary.

The closeout should let an operator or agent loop confirm that a completed
dry-run batch is ready for review, routing inspection, or live-pilot selection
without reprocessing files or touching downstream systems.

## Non-Goals

- Do not process configured SyncThing/private watch inputs.
- Do not run OCR/App Intelligence.
- Do not run public-web search or paid enrichment.
- Do not call Google Contacts, Odoo, or Odollo lookup/write/readback surfaces.
- Do not treat dry-run closeout as approval for a live sink call.

## Implementation

- Add `BusinessCardService.dry_run_closeout`.
- Add CLI `bcw runs dry-run-closeout <run-id>`.
- Add API `GET /runs/{run_id}/dry-run-closeout`.
- Add MCP tool `business_card_watchdog_dry_run_closeout`.
- Record `dry_run_closeout.json` only when requested.
- Detect completed dry-run state, artifact counts, event counts, live/pilot
  artifact or event markers, write attempts, and network calls.

## Acceptance Criteria

- The closeout is `ready_for_review_and_routing` only for a completed dry-run
  ledger with no live/pilot event markers, no live/pilot artifacts, no writes,
  and no network calls.
- The payload reports job, OCR, contact-candidate, review, and sink-payload
  counts.
- Text output gives operators the next safe inspection commands.
- Service, CLI, API, and MCP coverage prove no-live behavior on a synthetic
  dry-run batch.
- Full local validation passes before push.

## Validation

Completed in Turn 249 and recorded in `RUNBOOK.md`.

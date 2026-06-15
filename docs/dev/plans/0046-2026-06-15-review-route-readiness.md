# Plan 0046 | Review-Route Readiness

State: implemented
Date: 2026-06-15

## Scope

Add a run-level readiness surface that summarizes review, normalization,
duplicate, enrichment, and route state before any live sink action is selected.

This gives operators and agent loops a single dry-run checkpoint after closeout,
handoff, and bounded safe-loop execution.

## Non-Goals

- Do not process configured SyncThing/private watch inputs.
- Do not run OCR/App Intelligence.
- Do not run public-web search or paid enrichment.
- Do not execute live lookup, write, or readback.
- Do not approve or run Google Contacts, Odoo, or Odollo sink operations.

## Implementation

- Add `BusinessCardService.review_route_readiness`.
- Add CLI `bcw runs review-route-readiness <run-id>`.
- Add API `GET /runs/{run_id}/review-route-readiness`.
- Add MCP tool `business_card_watchdog_review_route_readiness`.
- Summarize per-job contact source, normalization warnings, duplicate state,
  enrichment state, route state, planned sinks, sink lookup state, and next
  action.
- Write `review_route_readiness.json` only when requested.

## Acceptance Criteria

- The report reads local run ledgers and review/routing artifacts only.
- The report shows aggregate counts for review, duplicate, enrichment, route,
  safe auto, and explicit operator states.
- Service, CLI, API, and MCP coverage prove zero-write, zero-network behavior on
  a synthetic dry-run batch.
- Full local validation passes before push.

## Validation

Completed in Turn 252 and recorded in `RUNBOOK.md`.

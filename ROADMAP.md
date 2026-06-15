# Roadmap

## Current Priority

Build a robust, installable business-card ingestion system that can process arbitrary-size batches from watched folders and route reviewed contact data to Google Contacts and/or Odoo/Odollo tenants.

Product authority: `PRODUCT_SPEC.md`.
Latest completed control-plane plan: `docs/dev/plans/0008-2026-06-14-runtime-installation-and-pilot-operations.md`.
Latest completed offline product-hardening plan: `docs/dev/plans/0026-2026-06-15-child-selected-target-abandonment-reset.md`.
Next production plan: `docs/dev/plans/0009-2026-06-14-operator-selected-live-smoke-and-pilot-rollout.md`.
Next offline boundary: child replacement handoff refresh after reset and route artifact staleness handling.
Next production boundary: operator-selected live smoke/pilot rollout for one run, one job, and one sink at a time.

## Milestones

### M1 | Repo Bootstrap And Dry-Run Batch Core | CLOSED

- Install repo-local policy.
- Provide installable Python package with CLI entrypoint.
- Load user-scoped config.
- Discover card images from files/directories and `$fsr` paths.
- Write deterministic run ledgers.
- Invoke the existing `business-card-to-contact` skill in dry-run mode.
- Expose initial API and MCP manifest surfaces.

Status evidence: Plan 0002 closed with dry-run batch core, shared service surfaces, watcher state, and user-scope operations in place. Live sink writes remain outside M1.

### M2 | Reviewable Batch Intelligence | CLOSED

- Add structured review schemas for OCR fixes, crop selection, retry/stop decisions, and sink routing.
- Add deterministic retry policy and per-card phase state.
- Add review queues for uncertain fields or poor crop confidence.
- Add batch-level summaries and failure triage artifacts.
- Apply reviewed corrections into canonical contact artifacts before routing.
- Add explicit enrichment request/review actions.

Status evidence: Plans 0004 and 0005 are reconciled/closed for review queues, review bundles, HTML/workbook surfaces, canonical contact provenance, enrichment requests/review, duplicate resolution, route refresh, phase reports, pilot readiness reports, CLI/API/MCP parity, and operator documentation.

### M3 | Watched Folder Service | CLOSED

- Add durable watch state so already-seen files survive process restarts.
- Add file-settle detection for SyncThing partial writes.
- Add user-scope service install helpers.
- Add health/status commands for watcher readiness.

Status evidence: Plan 0008 closed runtime readiness, fixture-backed watch dry-run proof, service recovery reporting, and user-scope runtime operations. Real SyncThing/private source processing still requires explicit operator action.

### M4 | Live Sink Adapters | READY_FOR_OPERATOR_SELECTED_PILOTS

- Add Google Contacts readiness checks and idempotent write/readback.
- Add Odoo/Odollo tenant readiness checks and idempotent partner upsert.
- Store per-sink external IDs and fingerprints in runtime state.
- Keep sink writes sequential per matched person/contact.
- Add duplicate detection before live writes.
- Keep paid API enrichment behind explicit operator request.

Status evidence: Plans 0004, 0007, and 0008 added Google Contacts and Odollo/Odoo local readiness evidence, adapter request contracts, read-only lookup adapters, write/readback adapters, selected-target gates, lookup smoke execution, one-job write/readback pilot readiness, pilot bundles, and redacted downstream duplicate evidence. Broad live writes remain intentionally blocked; the next step is an explicit one-job live smoke/pilot.

### M5 | Production MCP/API Surface | CLOSED_FOR_LOCAL_OPERATOR_USE

- Implement MCP server transport beyond static manifest.
- Expand API run/status/artifact endpoints.
- Add auth/network boundary guidance for non-loopback API exposure.
- Add packaging docs and release workflow.

Status evidence: MCP JSONL stdio transport, CLI/API/MCP parity, public upstream hardening, CI, branch protection checks, runtime recovery reports, and local operator docs are in place. Non-loopback hosted API exposure remains out of scope until a separate auth/network design is requested.

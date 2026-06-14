# Roadmap

## Current Priority

Build a robust, installable business-card ingestion system that can process arbitrary-size batches from watched folders and route reviewed contact data to Google Contacts and/or Odoo/Odollo tenants.

Product authority: `PRODUCT_SPEC.md`.
Active implementation plan: `docs/dev/plans/0005-2026-06-13-review-routing-normalization-enrichment-dedupe.md`.
Latest public upstream hardening plan: `docs/dev/plans/0006-2026-06-14-public-upstream-hardening.md`.

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

### M2 | Reviewable Batch Intelligence | PLANNED

- Add structured review schemas for OCR fixes, crop selection, retry/stop decisions, and sink routing.
- Add deterministic retry policy and per-card phase state.
- Add review queues for uncertain fields or poor crop confidence.
- Add batch-level summaries and failure triage artifacts.
- Apply reviewed corrections into canonical contact artifacts before routing.
- Add explicit enrichment request/review actions.

### M3 | Watched Folder Service | PLANNED

- Add durable watch state so already-seen files survive process restarts.
- Add file-settle detection for SyncThing partial writes.
- Add user-scope service install helpers.
- Add health/status commands for watcher readiness.

### M4 | Live Sink Adapters | PLANNED

- Add Google Contacts readiness checks and idempotent write/readback.
- Add Odoo/Odollo tenant readiness checks and idempotent partner upsert.
- Store per-sink external IDs and fingerprints in runtime state.
- Keep sink writes sequential per matched person/contact.
- Add duplicate detection before live writes.
- Keep paid API enrichment behind explicit operator request.

### M5 | Production MCP/API Surface | PLANNED

- Implement MCP server transport beyond static manifest.
- Expand API run/status/artifact endpoints.
- Add auth/network boundary guidance for non-loopback API exposure.
- Add packaging docs and release workflow.

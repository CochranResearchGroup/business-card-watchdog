# Roadmap

## Current Priority

Build a robust, installable business-card ingestion system that can process arbitrary-size batches from watched folders and route reviewed contact data to Google Contacts and/or Odoo/Odollo tenants.

Product authority: `PRODUCT_SPEC.md`.
Latest completed control-plane plan: `docs/dev/plans/0008-2026-06-14-runtime-installation-and-pilot-operations.md`.
Latest completed offline product-hardening plan: `docs/dev/plans/0053-2026-06-15-operator-live-pilot-readiness-packet.md`.
Latest completed refactor plan: `docs/dev/plans/0059-2026-06-20-review-route-lookup-selection-extraction.md`.
Active high-level development plan: `docs/dev/plans/0060-2026-06-20-product-development-milestone-plan.md`.
Latest completed contact-store plan: `docs/dev/plans/0063-2026-06-21-user-scoped-contact-store.md`.
Latest completed projection plan: `docs/dev/plans/0064-2026-06-22-artifact-to-database-projection.md`.
Latest completed scanner-intake plan: `docs/dev/plans/0065-2026-06-22-scanner-document-intake.md`.
Latest completed card-side plan: `docs/dev/plans/0066-2026-06-22-ocr-side-classification-pair-proposals.md`.
Latest completed side-merge plan: `docs/dev/plans/0067-2026-06-22-reviewed-side-pair-merge.md`.
Latest completed extraction-quality plan: `docs/dev/plans/0068-2026-06-22-extraction-quality-gates.md`.
Latest completed child-contact projection plan: `docs/dev/plans/0069-2026-06-22-reviewed-child-contact-projection.md`.
Latest completed contact-review-state plan: `docs/dev/plans/0070-2026-06-22-contact-review-states.md`.
Latest completed contact-review safe-loop plan: `docs/dev/plans/0071-2026-06-22-contact-review-safe-loop.md`.
Latest completed contact-review API/MCP parity plan: `docs/dev/plans/0072-2026-06-22-contact-review-api-mcp-parity.md`.
Latest completed enrichment provider-contract plan: `docs/dev/plans/0073-2026-06-22-people-data-labs-provider-contract.md`.
Latest completed enrichment review-provenance plan: `docs/dev/plans/0074-2026-06-22-enrichment-review-provenance-projection.md`.
Latest completed GWS default routing plan: `docs/dev/plans/0075-2026-06-22-gws-default-routing-profile.md`.
Latest completed contact-store selected-sink plan: `docs/dev/plans/0076-2026-06-22-contact-store-selected-sink-state.md`.
Latest completed contact route-selection packet plan: `docs/dev/plans/0077-2026-06-22-contact-route-selection-packets.md`.
Latest completed Odollo tenant route-target plan: `docs/dev/plans/0078-2026-06-22-odollo-tenant-route-targets.md`.
Latest completed Odollo read-only readiness packet plan: `docs/dev/plans/0079-2026-06-22-odollo-read-only-readiness-packets.md`.
Latest completed Odollo route-readiness contact-store plan: `docs/dev/plans/0080-2026-06-22-odollo-route-readiness-contact-store.md`.
Latest completed Odollo selected-target pilot-boundary plan: `docs/dev/plans/0081-2026-06-22-odollo-selected-target-pilot-boundary.md`.
Latest completed contact review surface field-correction plan: `docs/dev/plans/0082-2026-06-22-contact-review-surface-field-corrections.md`.
Latest completed contact review route-override plan: `docs/dev/plans/0083-2026-06-22-contact-review-route-overrides.md`.
Latest completed contact review crop-decision plan: `docs/dev/plans/0085-2026-06-22-contact-review-crop-decisions.md`.
Latest completed contact review enrichment-merge plan: `docs/dev/plans/0086-2026-06-22-contact-review-enrichment-merge.md`.
Latest completed contact review sink-approval plan: `docs/dev/plans/0087-2026-06-22-contact-review-sink-approval.md`.
Latest completed contact review surface closeout plan: `docs/dev/plans/0088-2026-06-22-contact-review-surface-closeout.md`.
Latest completed live pilot target-selection audit plan: `docs/dev/plans/0089-2026-06-22-live-pilot-target-selection-audit.md`.
Latest completed Milestone 9 dry-run selection handoff plan: `docs/dev/plans/0090-2026-06-22-milestone-9-dry-run-selection-handoff.md`.
Latest completed Milestone 9 operator checklist plan: `docs/dev/plans/0091-2026-06-22-milestone-9-operator-checklist.md`.
Latest completed Milestone 9 scoped scanner dry-run plan: `docs/dev/plans/0092-2026-06-22-scoped-scanner-dry-run-unblock.md`.
Latest completed Milestone 9 agent-loop plan: `docs/dev/plans/0093-2026-06-23-agent-loop-qr-orientation-side-pairing.md`.
Latest completed classifier-training plan: `docs/dev/plans/0094-2026-06-23-scanner-pdf-business-card-classifier-training.md`.
Latest completed gated crop/OCR resume plan: `docs/dev/plans/0095-2026-06-24-gated-crop-ocr-resume.md`.
Latest completed scanner side-pair/OCR refinement plan: `docs/dev/plans/0096-2026-06-24-scanner-side-pair-ocr-refinement.md`.
Active known-card ingestion and positive-corpus plan: `docs/dev/plans/0097-2026-06-25-known-card-ingestion-positive-corpus.md`.
Latest completed positive-corpus training/crop/side plan: `docs/dev/plans/0098-2026-06-26-positive-corpus-training-crop-side-plan.md`.
Active positive-control recognition/crop/side training plan: `docs/dev/plans/0099-2026-06-27-positive-control-recognition-crop-side-training.md`.
Latest completed negative-control corpus intake plan: `docs/dev/plans/0100-2026-06-27-negative-control-corpus-intake.md`.
Latest completed negative-control recognition replay plan: `docs/dev/plans/0101-2026-06-27-negative-control-recognition-replay.md`.
Latest completed practice-corpus plan: `docs/dev/plans/0062-2026-06-21-practice-corpus-manifest.md`.
Latest completed scanner side-pair graph plan: `docs/dev/plans/0084-2026-06-22-ocr-contextual-side-pair-graph.md`.
Next refactor/development plan: execute Plan 0099 Milestone 6 front/back matching and merge evidence from scanner sequence plus OCR/layout clues.
Next production plan: `docs/dev/plans/0009-2026-06-14-operator-selected-live-smoke-and-pilot-rollout.md`.
Next offline boundary: pause broad autodetection; process only operator-declared known business cards through dry-run crop/OCR/review, retain positive and negative controls in user-scoped runtime corpora, and require negative replay evidence before threshold changes.
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

Status evidence: Plan 0008 closed runtime readiness, fixture-backed watch dry-run proof, service recovery reporting, and user-scope runtime operations. Plan 0038 added a redacted watch backlog preflight for configured inputs. Plan 0039 added operator-response validation and a command-copy packet for the configured private-source watch dry-run boundary. Plan 0040 added a synthetic sample-output drill for that selection workflow. Plan 0041 added a synthetic watched dry-run execution drill through the real batch orchestrator. Plan 0042 added a no-processing configured-source readiness packet before private dry-run command copy. Plan 0043 added a post-dry-run closeout audit across CLI, API, and MCP before review/routing or live-pilot selection. Plan 0044 added a post-closeout review/routing handoff that summarizes safe agent-loop next actions without live sink calls. Plan 0045 added a gated bounded safe-loop executor for those safe actions. Plan 0046 added a run-level review-route readiness report before live sink selection. Plan 0047 added a preview-only lookup selection packet from route readiness to the explicit selected-target boundary. Plan 0048 added a bounded no-live closer for lookup prerequisite artifacts while preserving the selected-target approval boundary. Plan 0049 added a no-live selected-target approval boundary packet that composes validation, preflight, and preview without creating the target. Plan 0050 added an acknowledgement-gated selected-target command-copy packet before target creation. Plan 0051 exposed those selected-target gates from the operator dashboard command, API, and MCP maps. Plan 0052 added those gates to the synthetic live-pilot rehearsal before synthetic selected-target creation. Plan 0053 added a no-live operator readiness packet that composes dashboard, preflight, selected-target commands, and synthetic rehearsal expectations before live-pilot approval. Plan 0055 extracted the no-live live-pilot readiness and selected-target gate packet bodies from the service monolith into a focused packet module without changing public surfaces. Plan 0056 added a subagent-ready monolith decomposition plan, a drift guard, a shared selected-packet surface registry used by MCP/CLI/API, and the first service aggregator extraction for `operator_dashboard`. Plan 0057 extracted the read-only service recovery aggregator behind the existing service wrapper while preserving CLI/API/MCP behavior. Plan 0058 extracted the pilot-readiness report, moved its public surface metadata through the registry, and moved its CLI text renderer while preserving CLI/API/MCP behavior. Plan 0059 extracted review-route readiness and lookup-selection packet building, moved their public surface metadata through the registry, and moved their CLI text renderers while preserving CLI/API/MCP behavior. Real SyncThing/private source processing still requires explicit operator action.

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

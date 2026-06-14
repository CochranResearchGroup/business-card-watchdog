# Product Specification | Business Card Watchdog

Status: Draft authority  
Owner: Cochran Research Group  
Last updated: 2026-06-11

## 1. Product Summary

Business Card Watchdog is installable user-scope software that watches one or more local folders for business card images, processes arbitrary-size batches through OCR and review workflows, and routes validated contact records and image artifacts to configured contact sinks such as Google Contacts and Odoo/Odollo tenants.

The product builds on the existing `business-card-to-contact` skill, but turns the one-card skill workflow into a durable batch system with:

- watched-folder ingestion, including SyncThing phone-camera directories
- deterministic App Intelligence orchestration for large batches
- replayable ledgers and per-card artifacts
- CLI, API, and MCP surfaces
- user-scoped config and runtime state
- explicit dry-run-first routing to Google Contacts and Odoo/Odollo

## 2. Problem

Business card photos accumulate in phone-camera sync folders and are expensive to process one at a time. A reliable system must handle many cards at once, avoid duplicate contacts, preserve review evidence, and route each contact to the right downstream system without silently mixing tenants or performing unsafe writes.

Current one-off workflows are useful but insufficient for ongoing operations because they do not provide:

- durable watched-folder state
- batch retry and review queues
- deterministic run ledgers
- source-to-sink traceability
- sink-specific readiness checks
- user-scope installation and config
- API/MCP surfaces for agent-driven or external orchestration

## 3. Target Users

Primary user:

- A local operator who syncs phone photos to a workstation with SyncThing and wants a reliable contact-ingestion pipeline.

Secondary users:

- Agents or deterministic orchestrators that need CLI/API/MCP entrypoints for batch work.
- Future operators who need to process cards into Google Contacts, Odoo/Odollo, or other CRM/contact stores with tenant isolation.

## 4. Product Principles

- Deterministic host control: The software owns state transitions, retries, approvals, sink writes, and stop rules.
- AI as evidence, not authority: OCR/model/agent outputs may suggest fields, crops, reviews, and routing, but host-owned schemas and policy validate decisions before action.
- Dry-run first: External writes are disabled by default until readiness and routing policy are explicit.
- User-scope install: Config and runtime state live under the user home, not inside the repo.
- Tenant isolation: Google, Odoo/Odollo, and future sinks are separate profiles with isolated state and explicit readiness.
- Reviewable artifacts: Every processed card should leave inspectable OCR, normalized JSON, crop candidates, final decision records, and sink outcomes.
- Idempotency over convenience: Reprocessing should avoid duplicate contact creation where downstream systems provide enough matching hooks.

## 5. Goals

### G1. Folder And Batch Ingestion

The product can process a file, a directory, or configured watched folders. It supports arbitrary batch size by splitting work into per-card jobs and bounded worker pools.

### G2. Business Card Extraction

The product uses the `business-card-to-contact` workflow to:

- OCR card images
- normalize visible fields into contact JSON
- generate contact-photo crop candidates
- produce review artifacts
- optionally delegate Google Contact upsert after readiness is enabled

### G3. App Intelligence Orchestration

The product provides deterministic agent-loop orchestration for large batches:

- run ledger
- per-card phase state
- retry policy
- structured decision schemas
- failure triage
- review queue
- replayable event logs

### G4. Contact Routing

The product routes contact records and image artifacts to configured sinks:

- Google Contacts
- Odoo/Odollo tenants
- future CRM/contact-store adapters

Routing is based on deterministic config rules and sink readiness.

### G5. Operator Surfaces

The product exposes:

- CLI for local operation and scripting
- HTTP API for local service mode
- MCP surface for agent workflows
- watched-folder service for unattended ingestion

### G6. User-Scope Runtime

The product is installable at user scope and uses:

- `~/.config/business-card-watchdog/` for configuration
- `~/.local/share/business-card-watchdog/` for durable runtime data
- `~/.cache/business-card-watchdog/` for cache and transient watcher state

## 6. Non-Goals

- No silent writes to Google Contacts, Odoo/Odollo, or any CRM.
- No repo storage of private card photos, raw OCR dumps from real cards, connector credentials, or tenant secrets.
- No claim of perfect OCR accuracy.
- No automatic enrichment overwrite of card-observed fields without explicit merge policy.
- No non-loopback API exposure until authentication and network-boundary policy are designed.
- No assumption that all downstream systems support perfect cross-system idempotency.

## 7. Core Workflows

### W1. One-Time Batch Processing

1. Operator runs `bcw process <file-or-directory> --dry-run`.
2. Product creates a run directory.
3. Product discovers supported images.
4. Product creates one job per image.
5. Product invokes the card extraction adapter for each job.
6. Product records artifacts and job state.
7. Product evaluates routing rules.
8. Product records dry-run sink decisions.
9. Operator reviews run summary and per-card artifacts.

### W2. Watched SyncThing Folder

1. Operator configures the SyncThing phone directory in user config.
2. Product starts watcher service or `bcw watch`.
3. Product detects new image files.
4. Product waits for file-settle before processing.
5. Product records each seen file durably to avoid duplicate processing after restart.
6. Product processes cards through the same batch pipeline.
7. Product exposes health/status for watcher state.

### W3. Review Queue

1. A card has low-confidence OCR, ambiguous fields, missing required identity data, or poor crop candidates.
2. Product moves job to `needs_review`.
3. Product writes a review packet with original image reference, OCR text, normalized draft, crop contact sheet, and proposed fixes.
4. Human or agent review returns structured corrections.
5. Product validates corrections against schema and provenance rules.
6. Product resumes routing after review.

### W4. Live Google Contacts Routing

1. Operator enables Google Contacts sink in config.
2. Product runs readiness checks for `gws` auth and required Contacts scope.
3. Product computes or reads the business-card fingerprint.
4. Product matches existing contacts by email, phone, name, and stored fingerprint where available.
5. Product writes only when not dry-run and readiness passes.
6. Product records action, resource name, display name, and readback evidence.

### W5. Live Odoo/Odollo Routing

1. Operator enables an Odoo/Odollo tenant profile in config.
2. Product verifies tenant identity, base URL, database/profile binding, and credentials outside the repo.
3. Product builds an idempotent `res.partner` upsert payload.
4. Product matches by known external ID, fingerprint, email, phone, then exact name.
5. Product writes only when not dry-run and readiness passes.
6. Product records partner ID, matched key, action, and readback evidence.

### W6. Agent-Orchestrated Batch

1. Agent calls MCP/API/CLI to create or resume a run.
2. Product returns run ID and policy constraints.
3. Agent may request structured review, retry, or routing recommendations.
4. Product validates recommendations against schemas and phase policy.
5. Product applies only host-approved transitions.
6. Product records all decisions in the ledger.

## 8. Functional Requirements

### Ingestion

- Accept a single image path.
- Accept a directory and recursively discover supported images.
- Accept configured watched inputs.
- Resolve `$fsr` aliases from user config.
- Support common card-image extensions: JPEG, PNG, WebP, TIFF, and future HEIC where dependencies allow.
- Avoid processing partially synced files by using file-settle checks before watcher ingestion.
- Run deterministic preclassification before OCR/App Intelligence where possible, recording whether an image is a likely business card, not a business card, or uncertain.
- Treat whole-image aspect ratio as a weak hint only; `likely_business_card` should require stronger deterministic evidence such as one or more OpenCV-detected card-like rectangular contours.
- Support photos containing multiple business cards by recording multiple candidate card boxes before OCR/App Intelligence verification.

### Batch Orchestration

- Create one run directory per batch.
- Create one job record per image.
- Preserve job states with timestamps.
- Allow bounded parallel OCR/review work.
- Keep same-person/contact writes sequential.
- Support resume or re-run without losing previous artifacts.
- Record append-only events in JSONL.

### OCR And Contact Extraction

- Invoke the `business-card-to-contact` skill or equivalent local adapter.
- Preserve OCR text, normalized JSON, crop manifest, contact sheet, and review report.
- Keep only fields visible on the card unless later enrichment is explicitly approved.
- Store uncertain leftovers in notes.
- Add provenance to notes.

### Review And Corrections

- Mark low-confidence or incomplete records as `needs_review`.
- Provide structured field correction schema.
- Provide structured crop selection schema.
- Keep human/agent corrections distinct from raw OCR output.
- Reject corrections that invent unsupported contact data unless enrichment policy allows them.

### Routing

- Evaluate routing rules from user config.
- Support multiple sinks per card.
- Default to no live sink writes.
- Record dry-run decisions.
- Require readiness checks before live writes.
- Store sink outcomes with action, identifiers, and readback evidence.

### CLI

Required commands:

- `bcw init-config`
- `bcw status`
- `bcw process <source>`
- `bcw watch`
- `bcw api`
- `bcw mcp-manifest`

Future commands:

- `bcw runs list`
- `bcw runs show <run-id>`
- `bcw jobs review <job-id>`
- `bcw sinks check`
- `bcw service install`
- `bcw service uninstall`

### API

Initial local API:

- `GET /health`
- `POST /runs`

Future API:

- `GET /runs`
- `GET /runs/{run_id}`
- `GET /runs/{run_id}/jobs`
- `GET /jobs/{job_id}`
- `POST /jobs/{job_id}/review`
- `POST /sinks/check`

### MCP

Initial MCP surface:

- process source
- report status/readiness

Future MCP surface:

- create/resume run
- list jobs needing review
- submit structured review
- request sink readiness
- fetch artifact references

## 9. Configuration Requirements

Configuration file:

```text
~/.config/business-card-watchdog/config.toml
```

Required config domains:

- path aliases
- watched inputs
- sink enablement
- sink dry-run policy
- routing rules
- worker/concurrency policy
- review thresholds
- runtime profile names

Example:

```toml
[paths]
sync_phone = "/mnt/e/SyncThing/Phone Camera"

[watch]
inputs = ["$fsr:sync_phone"]

[sink]
dry_run = true
google_contacts = false
odoo = false

[routing]
rules = [
  { match = "email_domain", value = "*", sinks = ["google_contacts"] }
]
```

## 10. Runtime Data Requirements

Runtime root:

```text
~/.local/share/business-card-watchdog/
```

Expected structure:

```text
runs/
  <run-id>/
    run.json
    events.jsonl
    jobs.jsonl
    artifacts/
      <job-id>/
        spec.json
        ocr.txt
        review.md
        contact_sheet.jpg
        manifest.json
        sink-decisions.json
        sink-readbacks.json
watch/
  seen-files.jsonl
sinks/
  google-contacts/
  odoo/
```

Private images and OCR artifacts remain runtime data. They should not be committed.

## 11. State Model

Run states:

- `created`
- `discovering`
- `processing`
- `waiting_for_review`
- `routing`
- `completed`
- `failed`
- `cancelled`

Job states:

- `queued`
- `processing`
- `needs_review`
- `ready_to_route`
- `routed`
- `failed`
- `cancelled`

Sink action states:

- `planned`
- `dry_run`
- `ready`
- `written`
- `noop`
- `failed`
- `blocked`

## 12. App Intelligence Requirements

The product must implement deterministic agent loops where stochastic decisions are bounded by host policy.

Required loop properties:

- host-owned ledger
- host-owned phase transitions
- host-owned retry limits
- structured JSON schemas for decisions
- schema validation before action
- recorded accepted and rejected decisions
- explicit allowed actions per phase
- replayable input and output artifacts

Candidate structured decisions:

- field correction recommendation
- crop selection recommendation
- retry/stop recommendation
- duplicate/contact match recommendation
- sink routing recommendation
- batch triage summary

Agents must not directly:

- mutate external contact stores
- rewrite global config
- change tenant profile binding
- delete run artifacts
- mark live writes successful without readback

## 13. Idempotency Requirements

The product should use a canonical contact fingerprint derived from normalized card data:

- full name
- email
- normalized phone
- organization
- title
- website
- notes/provenance

Downstream matching order:

1. provider-native stable external ID when known
2. stored fingerprint
3. email
4. normalized phone
5. exact full name

The product may call idempotency best-effort when a sink lacks custom metadata fields, but it must not claim perfect deduplication.

## 14. Security And Privacy

- No credentials in repo.
- No private business card images in repo.
- No raw OCR dumps from real cards in repo.
- Redact sensitive logs before sharing.
- Keep tenant profile state outside repo.
- Require explicit opt-in before live writes.
- Require non-loopback API security design before exposing API beyond `127.0.0.1`.

## 15. Observability

The product should provide:

- run summary
- job counts by state
- sink decisions by sink
- failures with reason and artifact references
- watcher health
- adapter readiness
- last processed file timestamp
- durable event log paths

## 16. Milestone Acceptance

### M1. Repo Bootstrap And Dry-Run Batch Core

Acceptance:

- Installable package exists.
- CLI entrypoint exists.
- User config can be initialized.
- Files/directories can be discovered.
- Run ledgers are written.
- Existing card skill adapter can be invoked.
- Dry-run routing decisions are recorded.
- Initial API and MCP surfaces exist.

### M2. Reviewable Batch Intelligence

Acceptance:

- Structured review schemas exist.
- Per-card retry/stop policy exists.
- Review queue artifacts are generated.
- Ambiguous field/crop cases are separated from routable jobs.
- Batch triage summary is produced.

### M3. Watched Folder Service

Acceptance:

- Watcher persists seen-file state across restarts.
- SyncThing file-settle detection exists.
- User-scope service install/uninstall commands exist.
- Watcher status reports health and backlog.

### M4. Live Sink Adapters

Acceptance:

- Google Contacts readiness check exists.
- Google Contacts write/readback is proven.
- Odoo/Odollo readiness check exists.
- Odoo/Odollo write/readback is proven.
- Sink identifiers and fingerprints are stored in runtime state.

### M5. Production MCP/API Surface

Acceptance:

- MCP server transport exists.
- API exposes run/job/status/review endpoints.
- Local auth/network boundary is documented.
- Release and packaging workflow is documented.

## 17. Open Questions

- Which Odoo/Odollo tenant profile names should be first-class in the default config?
- Should the watcher process run as a systemd user service, scheduled task, or both?
- What minimum review confidence should allow fully automatic Google routing?
- Should HEIC support be mandatory in M1/M2 or deferred until watcher hardening?
- Should contact-photo crop review be human-gated for all cards, or only low-confidence cards?

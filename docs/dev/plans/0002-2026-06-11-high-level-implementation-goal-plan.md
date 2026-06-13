# Plan 0002 | High-Level Implementation Plan For /goal And Subagents

State: CLOSED  
Product authority: `PRODUCT_SPEC.md`  
Roadmap authority: `ROADMAP.md`

## Scope

This plan turns the product specification into a high-level execution structure designed for a `/goal` run with subagents. It defines the goal prompt, workstream decomposition, subagent briefs, dependency gates, integration gates, and validation evidence needed to move from the current scaffold toward a usable watched-folder business-card ingestion product.

## Non-Goals

- Do not perform live Google Contacts or Odoo/Odollo writes during the planning slice.
- Do not process real private card photos into repo artifacts.
- Do not expose the API beyond loopback.
- Do not let subagents mutate shared runtime state, credentials, or external contact stores.
- Do not optimize OCR accuracy before the run ledger, review, and sink contracts are structurally sound.

## `/goal` Objective

Use this as the high-level `/goal` objective:

```text
Build Business Card Watchdog into a robust, installable, user-scoped OCR and App Intelligence product that can process arbitrary-size batches of business card images from watched folders, preserve replayable per-card artifacts and ledgers, expose CLI/API/MCP surfaces, and route reviewed contacts to Google Contacts and/or Odoo/Odollo through explicit dry-run-first sink adapters with readiness checks, idempotency, and tenant isolation.
```

## `/goal` Operating Contract

The primary agent owns:

- goal state and scope control
- roadmap/runbook updates
- cross-workstream architecture decisions
- shared schema and state-machine compatibility
- final integration and validation
- all decisions involving live external writes

Subagents may work on bounded, repo-local branches of the problem. Each subagent must return:

- files inspected
- files changed or proposed
- validation run
- unresolved blockers
- integration risks
- any assumptions that need primary-agent confirmation

Subagents must not:

- write to Google Contacts, Odoo/Odollo, or any external sink
- edit user-scoped config containing private credentials
- add real card images or raw OCR artifacts to git
- change roadmap/product authority without explicit primary-agent merge
- spawn nested subagents unless the primary agent explicitly allows it

## Workstream Overview

### WS1. Core State, Ledger, And Schema

Purpose:

Define the durable state model that all other workstreams use.

Deliverables:

- typed run/job/sink state schemas
- append-only event model
- resumable run index
- artifact registry
- per-card phase transitions
- retry and stop policy

Acceptance:

- unit tests cover run/job state transitions
- sample dry-run batch produces stable `run.json`, `events.jsonl`, `jobs.jsonl`, and artifact registry
- invalid state transitions are rejected

Parallelism:

- Can proceed immediately.
- Must finish before production watcher, review queue, and sink adapters are integrated.

Suggested subagent brief:

```text
You are WS1 Core State subagent. Inspect PRODUCT_SPEC.md, ROADMAP.md, existing models/ledger/orchestrator code, and docs/dev/policies. Propose and implement the smallest typed state/ledger/schema changes needed for resumable runs, per-card phase state, artifact registry, and invalid-transition rejection. Do not touch external sink integrations. Return changed files, tests, and any compatibility risks.
```

### WS2. Ingestion And Watched Folder Service

Purpose:

Make folder watching reliable for SyncThing-style phone directories.

Deliverables:

- durable seen-file store
- file-settle detection
- watch backlog/status reporting
- `bcw watch` restart behavior
- user-scope service install plan, then implementation

Acceptance:

- watcher does not process files before size/mtime settle
- watcher does not reprocess seen files after restart unless explicitly reset
- CLI status reports watched inputs, backlog, last processed file, and errors
- tests simulate new, partial, settled, and already-seen files

Parallelism:

- Can start after WS1 state interface is drafted.
- Should not depend on live sink adapters.

Suggested subagent brief:

```text
You are WS2 Watcher subagent. Focus on SyncThing-style watched folders. Inspect watcher/config/orchestrator code and PRODUCT_SPEC W2. Implement or propose durable seen-file state, file-settle checks, and watcher status without processing real private images. Keep all runtime data under user-scope paths. Return tests and a dry-run smoke command.
```

### WS3. Business-Card Skill Adapter And Review Queue

Purpose:

Harden the adapter from the one-card skill into batch-safe reviewable jobs.

Deliverables:

- adapter readiness checks for scripts and OCR dependencies
- normalized artifact contract for OCR/spec/crops/review
- review packet generator
- structured field correction schema
- structured crop selection schema
- low-confidence or incomplete-card classification

Acceptance:

- adapter failures produce `failed` jobs with stderr excerpts and artifact references
- incomplete cards become `needs_review`, not `ready_to_route`
- review packets are deterministic and do not invent unsupported fields
- tests cover missing skill, failed subprocess, successful artifact normalization, and review classification

Parallelism:

- Can start immediately.
- Must integrate with WS1 before final merge.

Suggested subagent brief:

```text
You are WS3 Adapter/Review subagent. Inspect the local business-card-to-contact skill contract and this repo's skill_adapter/orchestrator. Design and implement batch-safe artifact normalization and review queue behavior. Do not perform live Google upserts. Keep card-observed fields authoritative. Return schema choices, tests, and any needed changes to PRODUCT_SPEC if gaps are found.
```

### WS4. Routing, Idempotency, And Sink Readiness

Purpose:

Build safe dry-run-first routing and readiness checks for Google Contacts and Odoo/Odollo.

Deliverables:

- routing rule schema
- canonical contact fingerprint helper
- sink adapter interface
- Google Contacts readiness check
- Odoo/Odollo readiness check
- dry-run sink payload/readback artifact shape
- sequential write lock design for same-person/contact mutations

Acceptance:

- dry-run sink decisions include matched routing rule, sink payload, fingerprint, and blocked/readiness reason
- readiness checks can run without performing writes
- live writes require explicit config and readiness pass
- tests cover route matching, fingerprint stability, disabled sinks, failed readiness, and same-contact serialization policy

Parallelism:

- Can start from spec and existing routing code.
- Must not enable live writes until primary-agent gate.

Suggested subagent brief:

```text
You are WS4 Routing/Sinks subagent. Implement safe dry-run-first routing primitives: fingerprinting, sink adapter interface, readiness-check stubs, and deterministic dry-run payload artifacts for Google Contacts and Odoo/Odollo. Do not perform live writes or read private credentials. Return tests and the exact gate conditions needed before live sink enablement.
```

### WS5. CLI, API, And MCP Surfaces

Purpose:

Expose the same core workflow consistently across operator and agent surfaces.

Deliverables:

- expanded CLI commands for run/job/status/review/sink checks
- API endpoints for run/job/status/review
- MCP server plan or implementation beyond static manifest
- consistent response schemas across surfaces
- loopback-only API defaults

Acceptance:

- CLI, API, and MCP all use the same core service functions
- no surface bypasses ledger/state validation
- local API health and run creation are covered by tests
- MCP tool schemas match the service contracts

Parallelism:

- Can start after WS1 schemas are stable enough.
- Should integrate with WS2/WS3/WS4 through service-layer calls, not duplicate logic.

Suggested subagent brief:

```text
You are WS5 Surfaces subagent. Expand CLI/API/MCP around shared service functions. Do not duplicate orchestration logic in the surface layers. Keep API loopback-first and avoid auth claims beyond current implementation. Return endpoint/tool schemas, tests, and any service-layer refactors needed.
```

### WS6. Packaging, Install, And User-Scope Operations

Purpose:

Make the product installable and operable at user scope.

Deliverables:

- install docs
- dependency groups for OCR/watch/API/dev
- config migration/versioning plan
- service install/uninstall commands or documented first implementation
- runtime directory doctor
- release checklist

Acceptance:

- editable install works in a venv
- `bcw init-config`, `bcw status`, and `bcw process --dry-run` work from installed entrypoint
- package metadata includes correct runtime dependencies
- service install does not require root

Parallelism:

- Can start immediately for documentation and metadata.
- Service commands should wait for WS2 watcher behavior.

Suggested subagent brief:

```text
You are WS6 Packaging/Ops subagent. Focus on installability, dependency groups, user-scope config/runtime directories, status/doctor checks, and service operation. Do not change core processing semantics. Return tested install commands, docs updates, and any missing dependency findings.
```

### WS7. QA, Fixtures, And Demo Corpus

Purpose:

Create safe validation coverage without committing private business card data.

Deliverables:

- synthetic card-image fixtures or generated test artifacts
- fake skill adapter for fast tests
- golden run ledger snapshots
- end-to-end dry-run smoke
- privacy-safe demo corpus guidance

Acceptance:

- tests do not need private card images
- end-to-end dry-run can run in CI/local without Google/Odoo credentials
- golden artifacts avoid unstable timestamps or normalize them before comparison
- failures point to run/job/artifact evidence

Parallelism:

- Can start immediately.
- Should support all workstreams with fixtures.

Suggested subagent brief:

```text
You are WS7 QA/Fixtures subagent. Build privacy-safe fixtures and test helpers for dry-run batch processing. Avoid real business card data. Prefer synthetic images or fake adapter outputs. Return fixture strategy, tests, and any changes needed so other workstreams can validate without external credentials.
```

## Critical Path

1. WS1 defines state, ledger, artifact, and transition contracts.
2. WS7 provides safe fixtures and fake adapters.
3. WS3 normalizes business-card adapter artifacts and review states.
4. WS4 defines dry-run routing, fingerprinting, and readiness gates.
5. WS2 hardens watched-folder ingestion against duplicate and partial files.
6. WS5 expands CLI/API/MCP on top of shared services.
7. WS6 finalizes user-scope install and service operation.

## Parallel Launch Set

Safe first subagents:

- WS1 Core State
- WS3 Adapter/Review
- WS4 Routing/Sinks
- WS6 Packaging/Ops
- WS7 QA/Fixtures

Hold until WS1 draft lands:

- WS2 Watcher
- WS5 Surfaces

Reason:

Watcher and surface work need stable run/job/service contracts. Adapter, routing, packaging, and fixtures can proceed with narrower interfaces and reconcile after WS1.

## Integration Gates

### Gate A. State Contract Gate

Required before merging watcher or surface expansions:

- run/job/sink states documented
- service functions return stable structured results
- invalid transitions tested
- artifact registry path rules documented

### Gate B. Privacy And Runtime Gate

Required before any e2e dry-run using real directories:

- runtime outputs stay under `~/.local/share/business-card-watchdog/`
- cache outputs stay under `~/.cache/business-card-watchdog/`
- no real card image or OCR text lands in git
- `.gitignore` covers local generated material

### Gate C. Sink Safety Gate

Required before live sink writes:

- sink enabled explicitly in config
- global dry-run disabled explicitly
- sink readiness check passed
- route decision recorded
- idempotency key/fingerprint recorded
- write lock or sequential mutation policy active for matched contact
- write result read back and recorded

### Gate D. Watcher Reliability Gate

Required before unattended watcher use:

- file-settle checks implemented
- seen-file state persists across restart
- watcher status reports backlog and last error
- reset/reprocess behavior is explicit

### Gate E. Surface Consistency Gate

Required before declaring API/MCP production-ready:

- CLI/API/MCP use shared service layer
- schemas are documented
- endpoint/tool tests pass
- API remains loopback-only by default

## Primary Agent Reconciliation Checklist

After subagents return:

- Review every diff against `PRODUCT_SPEC.md`, `AGENTS.md`, and policy files.
- Reject duplicated orchestration logic across CLI/API/MCP.
- Confirm runtime paths remain user-scoped.
- Confirm no private data or credentials entered git.
- Run targeted unit tests for each touched workstream.
- Run one end-to-end dry-run using synthetic fixtures.
- Update `ROADMAP.md` milestone state if acceptance criteria changed.
- Update `RUNBOOK.md` with validation evidence.
- Close or revise this plan with remaining blockers.

## Suggested `/goal` Turn Sequence

### Turn 1. Start Goal And Assign Safe Parallel Work

Primary agent:

- create `/goal` from the objective above
- mark WS1 as critical path owner task
- launch or delegate WS3, WS4, WS6, and WS7 if subagent tooling is available
- keep WS2 and WS5 pending until WS1 returns

### Turn 2. Integrate State And Fixtures

Primary agent:

- merge or adapt WS1
- merge or adapt WS7
- run unit tests
- update plan current state
- unblock WS2 and WS5

### Turn 3. Integrate Adapter, Review, And Routing

Primary agent:

- reconcile WS3 and WS4 with state contract
- ensure no live writes are enabled
- add dry-run e2e smoke
- record evidence

### Turn 4. Integrate Watcher And Surfaces

Primary agent:

- merge WS2 watcher hardening
- merge WS5 CLI/API/MCP expansion
- verify surface consistency
- run watcher restart simulation

### Turn 5. Package And Close Milestone

Primary agent:

- merge WS6 install/service docs or commands
- run installed-entrypoint smoke
- update `ROADMAP.md` M1/M2/M3 state as justified
- close this plan or open follow-on live-sink plan

## Validation Matrix

Minimum validation before closing this plan:

- `PYTHONPATH=src pytest -q`
- CLI status smoke
- CLI dry-run process against synthetic fixture
- watcher once-mode simulation with settled synthetic file
- API health test if API dependencies are installed
- MCP manifest/schema check
- `git status --short` reviewed for private/generated artifacts

## Current State

The repo has:

- initial package scaffold
- user config loader
- dry-run batch orchestrator
- append-only ledger files
- business-card skill subprocess adapter
- simple routing decisions
- initial CLI/API/MCP manifest surfaces
- product spec and repo policy
- WS1 partial implementation: typed run/job/sink states, explicit run/job transition validation, run index writes, artifact registry JSONL, and core state tests
- WS7 partial implementation: privacy-safe synthetic image fixtures, fake skill adapter, and end-to-end dry-run test coverage without external credentials
- WS3 partial implementation: deterministic contact-spec review assessment, structured review packets for incomplete specs, optional OCR/crop/contact-sheet artifact registration, and review-state tests
- WS4 partial implementation: canonical contact fingerprinting, dry-run sink payload artifacts, sink readiness primitives that block live writes until implemented, route decision fingerprints, and sink tests
- WS2 partial implementation: durable `watch/seen-files.jsonl` state, pending file snapshots for SyncThing-style file-settle detection, watcher status JSON, explicit watcher reset, and CLI `watch-status` / `watch-reset --yes` commands
- WS5 implementation: shared `BusinessCardService`, expanded CLI run/job/review/sink/watch/service/doctor surfaces, expanded API run/job/review/sink/watch endpoints, expanded MCP schemas, and a repo-backed MCP server implementation plan
- WS6 implementation: API/dev dependency extras validated in a local venv, user-scope systemd unit file install/status/uninstall commands, runtime doctor, config migration/versioning policy, and release checklist documentation

Validation evidence:

- `PYTHONPATH=src pytest -q` passed with 10 tests on 2026-06-11 after WS1 and WS7 integration.
- `PYTHONPATH=src pytest -q` passed with 18 tests on 2026-06-11 after WS3 and WS4 integration.
- `PYTHONPATH=src python -m business_card_watchdog.cli status --json` confirmed the skill adapter still reports ready.
- `PYTHONPATH=src python -m business_card_watchdog.cli mcp-manifest` rendered a 914-byte manifest after WS3/WS4 changes.
- `PYTHONPATH=src pytest -q` passed with 26 tests on 2026-06-11 after WS2 watcher hardening.
- `PYTHONPATH=src python -m business_card_watchdog.cli status --json` now includes watcher readback. On this machine it reports the configured `$fsr:sync_phone` target as missing because `E:\SyncThing\S22 Camera Phone Storage` is not present in the current Linux path namespace.
- `PYTHONPATH=src pytest -q` passed with 39 tests and 1 skipped API-extra test on 2026-06-11 after WS5/WS6 integration.
- `.venv/bin/python -m pytest -q` passed with 40 tests after installing `.[api,dev]`, proving FastAPI endpoints including review submission.
- `.venv/bin/bcw doctor --json` passed with a temp config that had no watched inputs and writable user-scope runtime paths.
- `.venv/bin/bcw status --json` passed with the real user config and reported the expected missing Windows SyncThing path caveat.
- `.venv/bin/bcw service status --json` passed and showed the user-scope unit path without requiring root.
- `.venv/bin/bcw mcp-manifest | python -m json.tool` passed and rendered a 5129-byte manifest.
- `.venv/bin/bcw --config <temp-config> process <empty-temp-source> --dry-run --workers 1` passed and created a completed dry-run run with no jobs or artifacts.

Follow-On Work:

- Live Google Contacts write/readback gates remain intentionally blocked until credentials/readiness can be verified safely.
- Live Odoo/Odollo tenant write/readback gates remain intentionally blocked until tenant identity and credentials are verified safely.
- The MCP server transport is planned in `docs/dev/architecture/0002-mcp-server-plan.md`; current implementation provides the manifest and service mapping, not a running MCP transport.
- CodeGraph is not initialized for this repo yet; structural code navigation is falling back to direct source reads until `.codegraph/` exists.

Plan 0002 is closed. Follow-on live sink and MCP transport work is tracked in `docs/dev/plans/0003-2026-06-11-follow-on-live-sinks-and-mcp-server.md`.

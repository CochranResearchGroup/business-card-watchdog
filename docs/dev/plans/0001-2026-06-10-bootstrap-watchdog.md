# Plan 0001 | Bootstrap Watchdog

State: OPEN

## Scope

Create the initial repository structure for installable OCR/App Intelligence software that builds on `business-card-to-contact`.

## Non-Goals

- No live Google Contacts writes without readiness and idempotency readback.
- No live Odoo/Odollo writes without tenant profile checks.
- No production daemon installer in the first slice.
- No claim that OCR quality is solved beyond the existing skill adapter.

## Acceptance Criteria

- Repo has local policy wiring in `AGENTS.md` and `docs/dev/policies/`.
- Python package installs with a CLI entrypoint.
- User-scoped config/runtime paths are explicit.
- Batch processing writes a deterministic run ledger.
- The business-card skill can be invoked through a bounded adapter.
- CLI, API, and MCP surfaces have initial entrypoints.
- Targeted tests pass.

## Current State

Initial scaffold is present. Live sink adapters and durable watch restart state remain planned.


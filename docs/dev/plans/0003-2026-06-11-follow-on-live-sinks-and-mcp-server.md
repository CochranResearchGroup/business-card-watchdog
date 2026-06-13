# Plan 0003 | Follow-On Live Sinks And MCP Server

State: PLANNED  
Product authority: `PRODUCT_SPEC.md`  
Predecessor: `docs/dev/plans/0002-2026-06-11-high-level-implementation-goal-plan.md`

## Scope

Implement the work intentionally left out of Plan 0002's dry-run-first execution:

- real Google Contacts readiness and write/readback gates
- real Odoo/Odollo tenant readiness and write/readback gates
- same-contact write serialization during live sink mutation
- production MCP server transport over the service-layer methods

## Non-Goals

- Do not perform live writes without explicit operator config and readiness evidence.
- Do not store credentials or private card data in the repo.
- Do not expose API or MCP outside loopback without a separate auth/network-boundary design.

## Acceptance Criteria

- `bcw sinks check --json` can distinguish dry-run readiness, missing credentials, and live-ready sink state.
- Google Contacts live write has a sandbox or controlled write/readback proof.
- Odoo/Odollo live write has tenant identity verification plus write/readback proof.
- Same-contact writes are serialized by the contact serialization key.
- MCP server transport executes the tool map defined in `docs/dev/architecture/0002-mcp-server-plan.md`.
- Tests cover blocked readiness, successful mocked readiness, and handler-to-service mapping.


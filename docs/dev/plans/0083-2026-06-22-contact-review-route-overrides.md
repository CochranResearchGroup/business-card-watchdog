# Plan 0083 | Contact Review Route Overrides

State: CLOSED
Date: 2026-06-22

## Purpose

Advance Plan 0060 Milestone 8 by adding an audited operator route-override
mutation to the database-backed contact review surface.

## Scope

- Add a host-owned route override mutation for projected contact routing
  decisions.
- Record previous and new route state in `contact_mutations`.
- Update the selected sink list, selected sink state, selected target profile or
  tenant, route candidate state, and readiness blockers for the selected routing
  decision.
- Expose route override through service, API, CLI, and MCP.

## Non-Goals

- No live sink writes.
- No selected-live-target creation.
- No automatic route override from model output.
- No crop, enrichment merge, or sink approval mutation in this slice.

## Acceptance Criteria

- Operators can override a contact's selected route without editing artifacts by
  hand.
- Route overrides are audited with operator, timestamp, previous values, and new
  values.
- Review surface rows reflect the overridden route and mutation count.
- API, CLI, and MCP expose route override parity.

## Validation

- Route override mutation audit tests.
- API/CLI/MCP parity tests.
- Full lint/test/drift gates before closeout.

## Closeout

Implemented:

- Added `override_route` to the contact store.
- Added `contact-route-override` service/API/CLI/MCP surfaces.
- Updated routing decisions in-place while preserving prior route state in
  mutation audit payloads.
- Extended contact review surface output to show the overridden route through
  existing route candidate summaries.

Validation:

- `.venv/bin/python -m pytest tests/test_contact_store.py::test_contact_route_override_is_audited tests/test_contact_store.py::test_contacts_cli_json_surfaces -q`
  passed with 2 tests.
- `.venv/bin/python -m pytest tests/test_api.py::test_api_contact_review_state_safe_loop_parity tests/test_mcp.py::test_mcp_contact_review_state_safe_loop_parity -q`
  passed with 2 tests.
- `.venv/bin/ruff check src/business_card_watchdog/contact_store.py src/business_card_watchdog/service.py src/business_card_watchdog/api.py src/business_card_watchdog/cli.py src/business_card_watchdog/mcp.py tests/test_contact_store.py tests/test_api.py tests/test_mcp.py`
  passed.
- `git diff --check` passed.
- `.venv/bin/python scripts/check_plan_drift.py` passed.
- `.venv/bin/ruff check .` passed.
- `.venv/bin/python -m pytest -q` passed with 387 tests.
- `codegraph sync /home/ecochran76/workspace.local/business-card-watchdog && codegraph status /home/ecochran76/workspace.local/business-card-watchdog`
  reported the index up to date with 60 files, 2,038 nodes, and 2,127 edges.

Safety:

- This slice did not run live sink calls, create selected-live-target artifacts,
  process configured SyncThing/private watch inputs, or enable non-loopback API
  behavior.

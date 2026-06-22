# Plan 0082 | Contact Review Surface Field Corrections

State: CLOSED
Date: 2026-06-22

## Purpose

Start Plan 0060 Milestone 8 by exposing a database-backed contact review
surface and an audited operator field-correction mutation for projected contact
rows.

## Scope

- Add a contact-store mutation audit table.
- Add host-owned field-correction mutation for normalized contact row fields.
- Add a composed contact review surface summarizing source assets, extraction,
  enrichment, routing, sink attempts, pending review states, and mutation audit.
- Expose the surface and mutation through service, API, CLI, and MCP.

## Non-Goals

- No non-loopback hosted UI.
- No private image bytes returned by the review surface.
- No live sink writes or selected-target creation.
- No route override, crop mutation, enrichment merge mutation, or sink approval
  mutation in this slice.

## Acceptance Criteria

- Operators can list contact review rows with asset and route links.
- Operators can apply field corrections without editing artifacts by hand.
- Field-correction mutations are audited with operator, timestamp, previous
  values, and new values.
- API, CLI, and MCP expose parity for the new surface and mutation.

## Validation

- Contact-store mutation audit tests.
- API/CLI/MCP parity tests.
- Full lint/test/drift gates before closeout.

## Closeout

Implemented:

- Bumped contact-store schema to v5.
- Added `contact_mutations` audit rows.
- Added audited normalized field corrections for `display_name`,
  `organization`, `email`, and `phone`.
- Added `contact_review_surface` summaries over contact rows, assets,
  extraction attempts, enrichment attempts, routing decisions, sink attempts,
  review states, and mutations.
- Exposed field corrections and review surface through service, API, CLI, and
  MCP.

Validation:

- `.venv/bin/python -m pytest tests/test_contact_store.py::test_contact_field_corrections_are_audited tests/test_contact_store.py::test_contacts_cli_json_surfaces -q`
  passed with 2 tests.
- `.venv/bin/python -m pytest tests/test_api.py::test_api_contact_review_state_safe_loop_parity tests/test_mcp.py::test_mcp_contact_review_state_safe_loop_parity -q`
  passed with 2 tests.
- `.venv/bin/ruff check src/business_card_watchdog/contact_store.py src/business_card_watchdog/service.py src/business_card_watchdog/api.py src/business_card_watchdog/cli.py src/business_card_watchdog/mcp.py tests/test_contact_store.py tests/test_api.py tests/test_mcp.py`
  passed.
- `git diff --check` passed.
- `.venv/bin/python scripts/check_plan_drift.py` passed.
- `.venv/bin/ruff check .` passed.
- `.venv/bin/python -m pytest -q` passed with 386 tests.
- `codegraph sync /home/ecochran76/workspace.local/business-card-watchdog && codegraph status /home/ecochran76/workspace.local/business-card-watchdog`
  reported the index up to date with 60 files, 2,031 nodes, and 2,121 edges.

Safety:

- This slice did not expose private image bytes, run live sink calls, create
  selected-live-target artifacts, process configured SyncThing/private watch
  inputs, or enable non-loopback API behavior.

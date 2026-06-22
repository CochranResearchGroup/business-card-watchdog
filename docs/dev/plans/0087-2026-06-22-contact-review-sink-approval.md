# Plan 0087 | Contact Review Sink Approval State

State: CLOSED
Date: 2026-06-22

Parent: Plan 0060 Milestone 8

## Purpose

Add an audited contact-review mutation for operator sink approval state against
projected contact sink attempts, without creating selected targets or running
live sink operations.

## Scope

- Add a contact-store sink approval mutation against a projected sink attempt.
- Preserve previous and new approval state in `contact_mutations`.
- Update the projected sink attempt state and payload with operator approval
  metadata.
- Expose the mutation through service, API, CLI, and MCP surfaces.
- Add focused store and CLI/API/MCP parity tests.

## Non-Goals

- No selected-live-target creation.
- No live Google Contacts, Odoo, or Odollo lookup/write/readback.
- No bypass of selected-target approval gates.
- No private watched-input processing.

## Acceptance Criteria

- Operator can set sink approval state on a projected sink attempt.
- Supported states are explicit review states: `approved_for_lookup`,
  `approved_for_write_pilot`, `rejected`, and `needs_review`.
- Mutation audit records operator, timestamp, previous state, new state, scope,
  reason, and attempt id.
- API, CLI, and MCP expose equivalent mutation behavior.

## Validation

- Focused store mutation test.
- CLI/API/MCP parity tests.
- `ruff`, `git diff --check`, and plan drift guard.

## Closeout Evidence

Implemented:

- Added `ContactStore.set_sink_approval_state` and projected sink-attempt
  lookup.
- Added `BusinessCardService.set_contact_sink_approval_state`.
- Added `POST /contacts/{contact_id}/sink-approval`.
- Added `bcw contacts sink-approval`.
- Added MCP tool `business_card_watchdog_contact_sink_approval`.
- Added tests for audited sink approval behavior and CLI/API/MCP parity.

Validation run:

- `.venv/bin/python -m pytest tests/test_contact_store.py::test_contact_sink_approval_is_audited tests/test_contact_store.py::test_contacts_cli_json_surfaces -q`
  passed with 2 tests.
- `.venv/bin/python -m pytest tests/test_api.py::test_api_contact_review_state_safe_loop_parity tests/test_mcp.py::test_mcp_contact_review_state_safe_loop_parity -q`
  passed with 2 tests.
- `.venv/bin/ruff check src/business_card_watchdog/contact_store.py src/business_card_watchdog/service.py src/business_card_watchdog/api.py src/business_card_watchdog/cli.py src/business_card_watchdog/mcp.py tests/test_contact_store.py tests/test_api.py tests/test_mcp.py`
  passed.
- `git diff --check` passed.
- `.venv/bin/python scripts/check_plan_drift.py` passed.
- `.venv/bin/ruff check .` passed.
- `.venv/bin/python -m pytest -q` passed with 393 tests.

Safety:

- This slice does not create selected-live-target artifacts, run live
  lookup/write/readback, process configured SyncThing/private watch inputs, or
  expose private image bytes.

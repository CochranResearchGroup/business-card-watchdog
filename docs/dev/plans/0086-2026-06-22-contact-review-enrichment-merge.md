# Plan 0086 | Contact Review Enrichment Merge

State: CLOSED
Date: 2026-06-22

Parent: Plan 0060 Milestone 8

## Purpose

Add an audited contact-review mutation for operator-approved enrichment merges
against projected contact rows, without editing run artifacts by hand or
calling enrichment providers.

## Scope

- Add a contact-store enrichment merge mutation against a projected enrichment
  attempt.
- Apply only operator-approved supported fields to the contact row payload.
- Preserve previous and new field values in `contact_mutations`.
- Expose the mutation through service, API, CLI, and MCP surfaces.
- Add focused store and CLI/API/MCP parity tests.

## Non-Goals

- No live enrichment provider calls.
- No public-web search.
- No automatic merge of enrichment results.
- No live sink lookup, write, or readback.
- No private watched-input processing.

## Acceptance Criteria

- Operator can merge selected fields from a projected enrichment attempt into a
  contact row.
- Unsupported, empty, and unapproved proposals are skipped with reasons.
- Mutation audit records operator, timestamp, attempt id, previous values, new
  values, approved fields, and skipped proposals.
- API, CLI, and MCP expose equivalent mutation behavior.

## Validation

- Focused store mutation test.
- CLI/API/MCP parity tests.
- `ruff`, `git diff --check`, and plan drift guard.

## Closeout Evidence

Implemented:

- Added `ContactStore.apply_enrichment_merge` and projected-attempt lookup.
- Added `BusinessCardService.apply_contact_enrichment_merge`.
- Added `POST /contacts/{contact_id}/enrichment-merge`.
- Added `bcw contacts enrichment-merge`.
- Added MCP tool `business_card_watchdog_contact_enrichment_merge`.
- Added tests for audited merge behavior and CLI/API/MCP parity.

Validation run:

- `.venv/bin/python -m pytest tests/test_contact_store.py::test_contact_enrichment_merge_is_audited tests/test_contact_store.py::test_contacts_cli_json_surfaces -q`
  passed with 2 tests.
- `.venv/bin/python -m pytest tests/test_api.py::test_api_contact_review_state_safe_loop_parity tests/test_mcp.py::test_mcp_contact_review_state_safe_loop_parity -q`
  passed with 2 tests.
- `.venv/bin/ruff check src/business_card_watchdog/contact_store.py src/business_card_watchdog/service.py src/business_card_watchdog/api.py src/business_card_watchdog/cli.py src/business_card_watchdog/mcp.py tests/test_contact_store.py tests/test_api.py tests/test_mcp.py`
  passed.
- `git diff --check` passed.
- `.venv/bin/python scripts/check_plan_drift.py` passed.
- `.venv/bin/ruff check .` passed.
- `.venv/bin/python -m pytest -q` passed with 392 tests.

Safety:

- This slice does not call enrichment providers, run public-web search, process
  configured SyncThing/private watch inputs, perform live lookup/write/readback,
  or expose private image bytes.

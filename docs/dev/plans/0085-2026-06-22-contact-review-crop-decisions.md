# Plan 0085 | Contact Review Crop Decisions

State: CLOSED
Date: 2026-06-22

Parent: Plan 0060 Milestone 8

## Purpose

Add an audited contact-review mutation for operator crop decisions so projected
card crop assets can be accepted, rejected, marked for recrop, or switched to an
alternate crop without editing artifacts by hand.

## Scope

- Add a contact-store crop decision mutation against projected card assets.
- Preserve previous and new crop decision state in `contact_mutations`.
- Update the selected asset payload with crop decision metadata.
- Expose the mutation through service, API, CLI, and MCP surfaces.
- Add focused store and CLI/API/MCP parity tests.

## Non-Goals

- No image editing or crop generation.
- No automatic crop acceptance from App Intelligence.
- No live sink lookup, write, or readback.
- No private SyncThing/scanner image processing.

## Acceptance Criteria

- Operator can apply a crop decision to a projected card asset.
- The mutation records operator, timestamp, previous state, new state, reason,
  selected crop path, and optional checksum.
- Contact review surface mutation counts and audit summaries include the crop
  decision.
- API, CLI, and MCP expose equivalent mutation behavior.

## Validation

- Focused store mutation test.
- CLI/API/MCP parity tests.
- `ruff`, `git diff --check`, and plan drift guard.

## Closeout Evidence

Implemented:

- Added `ContactStore.decide_crop` and `ContactStore.get_asset`.
- Added `BusinessCardService.decide_contact_crop`.
- Added `POST /contacts/{contact_id}/crop-decision`.
- Added `bcw contacts crop-decision`.
- Added MCP tool `business_card_watchdog_contact_crop_decision`.
- Added focused tests for audited crop decisions and CLI/API/MCP parity.

Validation run:

- `.venv/bin/python -m pytest tests/test_contact_store.py::test_contact_crop_decision_is_audited tests/test_contact_store.py::test_contacts_cli_json_surfaces -q`
  passed with 2 tests.
- `.venv/bin/python -m pytest tests/test_api.py::test_api_contact_review_state_safe_loop_parity tests/test_mcp.py::test_mcp_contact_review_state_safe_loop_parity -q`
  passed with 2 tests.
- `.venv/bin/ruff check src/business_card_watchdog/contact_store.py src/business_card_watchdog/service.py src/business_card_watchdog/api.py src/business_card_watchdog/cli.py src/business_card_watchdog/mcp.py tests/test_contact_store.py tests/test_api.py tests/test_mcp.py`
  passed.
- `git diff --check` passed.
- `.venv/bin/python scripts/check_plan_drift.py` passed.
- `.venv/bin/ruff check .` passed.
- `.venv/bin/python -m pytest -q` passed with 391 tests.

Safety:

- This slice does not generate or mutate image files, process private watched
  inputs, run enrichment, perform live lookup/write/readback, or expose private
  image bytes.

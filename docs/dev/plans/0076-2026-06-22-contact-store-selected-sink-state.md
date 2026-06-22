# Plan 0076 | Contact Store Selected Sink State

State: CLOSED
Date: 2026-06-22

## Purpose

Advance Plan 0060 Milestone 6 by making route decisions and selected sink state
queryable in the user-scoped contact store, instead of requiring review or sink
approval surfaces to infer the selected GWS target from transient artifacts.

## Scope

- Add a contact-store migration for durable selected sink state fields on
  routing decisions.
- Project selected sink names, selected route state, and configured target
  profile or tenant metadata from dry-run routing artifacts.
- Preserve existing routing payload JSON for replay and audit context.
- Cover generated default GWS routing projection with contact-store tests.

## Non-Goals

- No live Google Contacts lookup, write, or readback.
- No selected-live-target creation.
- No Odoo/Odollo route expansion.
- No private SyncThing or scanner input processing.

## Acceptance Criteria

- Existing contact-store databases migrate without data loss.
- A projected default GWS dry-run run stores `google_contacts` as the selected
  sink in first-class routing columns.
- The selected target profile `ecochran76` is persisted when available from
  dry-run readiness metadata.
- Contact detail responses expose the selected sink state alongside existing
  routing payloads.

## Validation

- Contact-store projection tests.
- Focused ruff for changed files.
- Plan drift guard and broader test run before closeout.

## Closeout

Implemented:

- Added contact-store schema version 3 with first-class selected sink state on
  routing decisions.
- Added migration-safe columns for selected sinks, selected sink state, selected
  target profile, and selected target tenant.
- Backfilled selected sink state from existing routing payload JSON when
  migrating older databases.
- Projected dry-run sink payload readiness metadata into durable routing
  decision columns.
- Exposed selected sinks as parsed list data in contact detail routing
  decisions.

Validation:

- `.venv/bin/python -m pytest tests/test_contact_store.py::test_contact_store_migrates_selected_sink_columns_without_losing_routes tests/test_contact_store.py::test_contact_store_projects_run_idempotently -q`
  passed with 2 tests.
- `.venv/bin/python -m pytest tests/test_contact_store.py -q` passed with 7
  tests.
- `.venv/bin/python -m pytest tests/test_api.py::test_api_run_lookup_selection_packet_reports_selected_candidate tests/test_api.py::test_api_run_selected_target_approval_boundary_previews_selection tests/test_api.py::test_api_run_selected_target_command_copy_packet_requires_ack -q`
  passed with 3 tests.
- `.venv/bin/python -m pytest tests/test_service.py -q` passed with 112 tests.
- `.venv/bin/ruff check src/business_card_watchdog/contact_store.py tests/test_contact_store.py`
  passed.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `.venv/bin/python scripts/check_plan_drift.py` passed.
- `.venv/bin/python -m pytest -q` passed with 367 tests.
- `codegraph sync /home/ecochran76/workspace.local/business-card-watchdog && codegraph status /home/ecochran76/workspace.local/business-card-watchdog`
  reported the index already up to date, 60 files, 1,967 nodes, and 2,079
  edges.

Safety:

- This slice did not run live Google lookup/write/readback, public-web search,
  paid enrichment, Odoo, or Odollo calls. It did not process configured
  SyncThing/private watch inputs, create selected-live-target artifacts, or
  enable live sink writes.

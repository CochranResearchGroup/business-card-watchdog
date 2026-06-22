# Plan 0080 | Odollo Route Readiness Contact Store

State: CLOSED
Date: 2026-06-22

## Purpose

Advance Plan 0060 Milestone 7 by persisting Odollo route candidates, selected
tenant targets, and read-only readiness blockers into the user-scoped contact
store.

## Scope

- Extend contact-store routing decisions with queryable route candidate state
  and readiness blocker fields.
- Project Odoo/Odollo lookup-plan tenant readiness and duplicate lookup gate
  packets into routing decision payloads.
- Preserve selected target tenant references already threaded through route
  selection.
- Add migration/backfill behavior for existing routing decision rows.

## Non-Goals

- No live Odollo/Odoo lookup, write, or readback.
- No selected-live-target creation.
- No tenant-private artifact ingestion into git.
- No broad contact-store redesign.

## Acceptance Criteria

- Existing contact stores migrate without losing selected sink metadata.
- Odoo route decisions persist selected tenant references.
- Odoo route decisions persist readiness blockers from tenant readiness and
  duplicate lookup gate packets.
- Contacts can expose Odollo route candidate state from the contact-store detail
  surface.

## Validation

- Contact-store migration tests.
- Odollo route projection tests.
- Adjacent dry-run pipeline and route-selection tests.
- Full lint/test/drift gates before closeout.

## Closeout

Implemented:

- Bumped the contact-store schema to v4.
- Added `route_candidate_state` and `readiness_blockers_json` to
  `routing_decisions`.
- Projected Odoo lookup-plan tenant readiness and duplicate lookup gate packets
  into routing decision payloads.
- Added legacy backfill for route candidate state and readiness blockers.
- Added fixture coverage for an Odollo/SABER route that is tenant-ready locally
  but duplicate-lookup blocked.

Validation:

- `.venv/bin/python -m pytest tests/test_contact_store.py -q` passed with 8
  tests.
- `.venv/bin/python -m pytest tests/test_dry_run_pipeline.py tests/test_service.py::test_service_contact_route_selection_packets_use_projected_gws_route tests/test_service.py::test_service_contact_route_selection_blocks_gws_profile_mismatch -q`
  passed with 7 tests.
- `.venv/bin/ruff check src/business_card_watchdog/contact_store.py tests/test_contact_store.py`
  passed.
- `git diff --check` passed.
- `.venv/bin/python scripts/check_plan_drift.py` passed.
- `.venv/bin/ruff check .` passed.
- `.venv/bin/python -m pytest -q` passed with 383 tests.
- `codegraph sync /home/ecochran76/workspace.local/business-card-watchdog && codegraph status /home/ecochran76/workspace.local/business-card-watchdog`
  reported the index up to date with 60 files, 2,012 nodes, and 2,104 edges.

Safety:

- This slice did not run live Odollo/Odoo lookup, write, or readback. It did
  not inspect tenant-private runtime artifacts, process configured
  SyncThing/private watch inputs, create selected-live-target artifacts, or
  enable live sink writes.

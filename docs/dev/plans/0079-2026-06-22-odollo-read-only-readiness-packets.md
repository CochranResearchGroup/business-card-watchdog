# Plan 0079 | Odollo Read-Only Readiness Packets

State: CLOSED
Date: 2026-06-22

## Purpose

Advance Plan 0060 Milestone 7 by adding explicit read-only Odollo tenant
readiness and duplicate lookup blocker packets to route-selected Odollo lookup
plans before any write pilot.

## Scope

- Add a tenant readiness packet for Odollo routes that distinguishes missing
  config, blocked tenant state, and local pilot-ready evidence.
- Add a duplicate lookup gate to Odoo lookup plan entries that preserves
  zero-network dry-run behavior while making duplicate risk explicit.
- Keep readiness checks local-only and redacted; do not invoke Odollo/Odoo
  network calls.
- Add focused fixture tests with a temp `ODOLLO_HOME`.

## Non-Goals

- No live Odollo/Odoo lookup, write, or readback.
- No broad write pilot enablement.
- No inspection or ingestion of tenant-private runtime artifacts.
- No contact-store schema changes in this slice.

## Acceptance Criteria

- Missing Odollo config reports `missing_config`.
- Missing or incomplete tenant local state reports `blocked_tenant`.
- Complete local tenant evidence reports `pilot_ready` without network calls.
- Dry-run Odoo duplicate lookup plans expose duplicate risk as blocked until an
  operator-selected read-only lookup runs.

## Validation

- Tenant readiness tests for missing config, blocked tenant, and pilot-ready
  local evidence.
- Duplicate lookup packet tests proving zero network and zero writes.
- Full lint/test/drift gates before closeout.

## Closeout

Implemented:

- Added `business-card-watchdog.odollo-tenant-readiness.v1` packets.
- Added `business-card-watchdog.odollo-duplicate-lookup-gate.v1` packets to
  Odoo lookup plan entries.
- Kept dry-run lookup planning at zero network calls and zero writes.
- Added deterministic tests using a temp `ODOLLO_HOME`.

Validation:

- `.venv/bin/python -m pytest tests/test_sinks.py -q` passed with 26 tests.
- `.venv/bin/ruff check src/business_card_watchdog/sinks.py tests/test_sinks.py`
  passed.
- `git diff --check` passed.
- `.venv/bin/python scripts/check_plan_drift.py` passed.
- `.venv/bin/python -m pytest -q` passed with 382 tests.
- `.venv/bin/ruff check .` passed.
- `codegraph sync /home/ecochran76/workspace.local/business-card-watchdog && codegraph status /home/ecochran76/workspace.local/business-card-watchdog`
  reported the index up to date with 60 files, 2,004 nodes, and 2,096 edges.

Safety:

- This slice did not run live Odollo/Odoo lookup, write, or readback. It did
  not inspect tenant-private runtime artifacts, process configured
  SyncThing/private watch inputs, create selected-live-target artifacts, or
  enable live sink writes.

# Plan 0081 | Odollo Selected-Target Pilot Boundary

State: CLOSED
Date: 2026-06-22

## Purpose

Close the Plan 0060 Milestone 7 selected-target/write-readback boundary by
making Odollo route-selected tenant targets explicit at live lookup, selected
target, write-pilot, and readback-pilot gates.

## Scope

- Use the job's route-selected Odollo tenant target for live lookup readiness
  instead of falling back only to global `sink.odollo_tenant`.
- Persist selected target tenant context in `selected_live_target.json`.
- Block non-simulated Odollo write pilots until tenant readiness is pilot-ready
  and selected read-only duplicate evidence has been produced and cleared.
- Keep readback read-only and tied to the current selected live target.
- Add focused tests for route-selected SABER tenant readiness and write-pilot
  blocking before duplicate evidence.

## Non-Goals

- No broad live Odollo writes.
- No automatic tenant creation.
- No tenant-private artifact ingestion into git.
- No bypass of selected-target or duplicate-review gates.

## Acceptance Criteria

- Live lookup readiness uses the route-selected Odollo tenant target.
- Selected live targets for Odoo carry the chosen tenant context.
- Non-simulated Odollo write pilots are blocked before selected lookup and
  downstream duplicate evidence exist.
- Operator-facing write-pilot execution packets explain Odollo readiness
  blockers without running live calls.
- Readback remains explicit, read-only, and selected-target scoped.

## Validation

- Route-selected Odollo live lookup readiness test.
- Odollo selected-target/write boundary blocker test.
- Adjacent selected-target, write, readback, and readiness tests.
- Full lint/test/drift gates before closeout.

## Closeout

Implemented:

- Added selected sink target-context extraction from `sink_lookup_plan.json`,
  `sink_plan.json`, and configured fallback.
- Updated live lookup readiness to use the route-selected Odollo tenant.
- Added selected target tenant context to selected live target artifacts.
- Added an Odollo write-pilot boundary that requires tenant readiness,
  selected lookup smoke evidence, and downstream duplicate clearance.
- Enforced the boundary for non-simulated Odollo write pilots and surfaced it in
  selected write-pilot execution packets.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_odollo_live_lookup_uses_route_selected_tenant tests/test_service.py::test_service_odollo_selected_target_blocks_write_until_duplicate_evidence -q`
  passed with 2 tests.
- `.venv/bin/python -m pytest tests/test_service.py::test_service_apply_pilot_readiness_can_scope_to_selected_sink tests/test_service.py::test_service_write_pilot_uses_injected_executor tests/test_service.py::test_service_readback_pilot_writes_simulated_evidence tests/test_service.py::test_service_select_live_target_requires_abandonment_before_replacement tests/test_service.py::test_service_odollo_live_lookup_uses_route_selected_tenant tests/test_service.py::test_service_odollo_selected_target_blocks_write_until_duplicate_evidence -q`
  passed with 6 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py tests/test_service.py`
  passed.
- `git diff --check` passed.
- `.venv/bin/python scripts/check_plan_drift.py` passed.
- `.venv/bin/ruff check .` passed.
- `.venv/bin/python -m pytest -q` passed with 385 tests.
- `codegraph sync /home/ecochran76/workspace.local/business-card-watchdog && codegraph status /home/ecochran76/workspace.local/business-card-watchdog`
  reported the index up to date with 60 files, 2,018 nodes, and 2,110 edges.

Safety:

- This slice did not run live Odollo/Odoo lookup, write, or readback. It did
  not inspect tenant-private runtime artifacts, process configured
  SyncThing/private watch inputs, create selected-live-target artifacts outside
  synthetic test runs, or enable broad live sink writes.

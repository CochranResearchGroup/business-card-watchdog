# Plan 0078 | Odollo Tenant Route Targets

State: CLOSED
Date: 2026-06-22

## Purpose

Advance Plan 0060 Milestone 7 by allowing deterministic route rules to target
specific Odollo tenant profiles, starting with SoyLei and SABER, while keeping
lookup/write behavior read-only or dry-run.

## Scope

- Add route-rule metadata for the selected Odollo tenant target.
- Support Providence-context route matching through existing host-owned route
  policy, without stochastic routing decisions.
- Thread the selected tenant into dry-run sink payloads and duplicate lookup
  plans.
- Preserve the existing global `sink.odollo_tenant` fallback.
- Add fixture tests for SoyLei and SABER route targets.

## Non-Goals

- No live Odollo lookup, write, or readback.
- No automatic tenant creation.
- No tenant-private artifact ingestion into git.
- No broad write pilot enablement.

## Acceptance Criteria

- A route rule can select `odoo` and name `soylei-prod` or `saber-prod` as the
  target tenant.
- Dry-run sink payloads and lookup packets expose the selected tenant target.
- Missing tenant metadata remains blocked for non-dry-run lookup/write
  readiness.
- Existing global `sink.odollo_tenant` behavior continues to work.

## Validation

- Routing policy tests for Providence-context SoyLei/SABER routing.
- Sink readiness and lookup packet tests for selected tenant metadata.
- Targeted service/orchestrator tests if call-site threading changes.
- Full lint/test/drift gates before closeout.

## Closeout

Implemented:

- Added `providence_context` route matching for deterministic SoyLei/SABER
  context rules.
- Added route-rule Odollo tenant target metadata via `odollo_tenant`, `tenant`,
  or `target_tenant`.
- Preserved global `sink.odollo_tenant` as the fallback target.
- Threaded selected route targets into dry-run sink plans, sink payloads, and
  sink lookup plans.
- Added fixture tests for `soylei-prod` and `saber-prod` target selection.

Validation:

- `.venv/bin/python -m pytest tests/test_routing.py::test_providence_context_route_selects_soylei_odollo_tenant tests/test_routing.py::test_providence_context_route_selects_saber_odollo_tenant_from_labels tests/test_routing.py::test_odollo_route_target_falls_back_to_global_tenant tests/test_sinks.py::test_build_sink_lookup_plan_exposes_selected_odollo_tenant tests/test_sinks.py::test_build_sink_plan_exposes_selected_odollo_tenant tests/test_service.py::test_service_plans_use_route_selected_odollo_tenant -q`
  passed with 6 tests.
- `.venv/bin/python -m pytest tests/test_routing.py tests/test_sinks.py -q`
  passed with 30 tests.
- `.venv/bin/python -m pytest tests/test_service.py -q` passed with 115 tests.
- `.venv/bin/ruff check src/business_card_watchdog/routing.py src/business_card_watchdog/service.py src/business_card_watchdog/orchestrator.py tests/test_routing.py tests/test_sinks.py tests/test_service.py`
  passed.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `.venv/bin/python scripts/check_plan_drift.py` passed.
- `.venv/bin/python -m pytest -q` passed with 378 tests.
- `codegraph sync /home/ecochran76/workspace.local/business-card-watchdog && codegraph status /home/ecochran76/workspace.local/business-card-watchdog`
  reported the index already up to date, 60 files, 1,995 nodes, and 2,087
  edges.

Safety:

- This slice did not run live Odollo/Odoo lookup, write, or readback. It did
  not inspect tenant-private runtime artifacts, process configured
  SyncThing/private watch inputs, create selected-live-target artifacts, or
  enable live sink writes.

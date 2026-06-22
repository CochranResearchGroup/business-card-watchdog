# Plan 0075 | GWS Default Routing Profile

State: CLOSED
Date: 2026-06-22

## Purpose

Advance Plan 0060 Milestone 6 by installing a deterministic dry-run Google
Workspace default routing profile for the `ecochran76` account while preserving
selected-target gates before any live write.

## Scope

- Update generated user config so Google Contacts is the default dry-run sink
  with `google_contacts_profile = "ecochran76"`.
- Keep live apply disabled by default.
- Preserve the existing wildcard route policy to target Google Contacts.
- Include configured Google Contacts profile/target metadata in no-write sink
  plan and lookup readiness payloads.
- Keep existing route and selected-target gates authoritative.

## Non-Goals

- No live Google Contacts writes.
- No live Google lookup/readback calls.
- No broad batch pilot enablement.
- No SoyLei/SABER/Odollo routing in this slice.

## Acceptance Criteria

- A generated config routes route-ready contacts to Google Contacts by default
  in dry-run mode.
- The generated profile target is `ecochran76`.
- Sink and lookup plans expose the configured GWS profile without credentials.
- Live apply remains disabled until explicit selected-target pilot approval.

## Validation

- Config/default routing tests.
- Sink readiness/plan metadata tests.
- Targeted ruff/pytest, full ruff/pytest, `git diff --check`, plan drift guard,
  and CodeGraph sync/status.

## Closeout

Implemented:

- Updated generated user config to enable Google Contacts as the default dry-run
  sink with `google_contacts_profile = "ecochran76"`.
- Kept `google_contacts_apply_enabled = false` by default.
- Preserved the wildcard route rule that routes contacts to Google Contacts.
- Added configured target-account metadata to dry-run sink apply and lookup
  readiness payloads without credentials.
- Threaded configured sink profile context through orchestrator and service
  sink/lookup plan generation.

Validation:

- `.venv/bin/python -m pytest tests/test_config.py::test_default_config_installs_dry_run_ecochran76_gws_route tests/test_routing.py::test_generated_default_config_routes_to_ecochran76_google_contacts tests/test_sinks.py::test_dry_run_readiness_does_not_require_credentials tests/test_sinks.py::test_build_sink_plan_is_dry_run_and_action_oriented tests/test_sinks.py::test_build_sink_lookup_plan_is_zero_network_and_keyed -q`
  passed with 5 tests.
- `.venv/bin/python -m pytest tests/test_config.py tests/test_routing.py tests/test_sinks.py -q`
  passed with 31 tests.
- `.venv/bin/python -m pytest tests/test_service.py tests/test_api.py tests/test_mcp.py -q`
  passed with 176 tests.
- `.venv/bin/ruff check src/business_card_watchdog/config.py src/business_card_watchdog/sinks.py src/business_card_watchdog/service.py src/business_card_watchdog/orchestrator.py tests/test_config.py tests/test_routing.py tests/test_sinks.py`
  passed.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `.venv/bin/python scripts/check_plan_drift.py` passed.
- `.venv/bin/python -m pytest -q` passed with 366 tests.
- `codegraph sync /home/ecochran76/workspace.local/business-card-watchdog && codegraph status /home/ecochran76/workspace.local/business-card-watchdog`
  reported the index already up to date, 60 files, 1,960 nodes, and 2,072
  edges.

Safety:

- This slice did not run live Google lookup/write/readback, public-web search,
  paid enrichment, Odoo, or Odollo calls. It did not process configured
  SyncThing/private watch inputs, enable broad live writes, or bypass
  selected-target gates.

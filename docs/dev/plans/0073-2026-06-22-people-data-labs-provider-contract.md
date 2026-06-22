# Plan 0073 | People Data Labs Provider Contract

State: CLOSED
Date: 2026-06-22

## Purpose

Advance Plan 0060 Milestone 5 by adding People Data Labs as an explicit
paid-provider enrichment contract alongside the existing Apollo contract,
without making live paid API calls.

## Scope

- Add user config support for `enrichment.providers.people_data_labs`.
- Add redacted readiness checks for the selected paid provider.
- Add provider selection to CLI/API/MCP enrichment request surfaces while
  preserving Apollo as the default.
- Generate People Data Labs preview request and handoff artifacts with no
  network calls or paid API calls.
- Normalize explicit People Data Labs result imports into reviewable enrichment
  result artifacts with provenance.

## Non-Goals

- No live People Data Labs calls.
- No paid API execution.
- No enrichment auto-merge into contacts.
- No credential values in git, ledgers, handoffs, or test output.

## Acceptance Criteria

- Config loading and default config expose People Data Labs provider settings.
- Readiness reports can distinguish missing PDL config/key from ready preview
  conditions without leaking key values.
- API/CLI/MCP can prepare PDL provider request/handoff artifacts and import
  explicit PDL result rows.
- Existing Apollo provider behavior remains compatible.

## Validation

- Config tests for People Data Labs provider loading.
- Provider readiness/request/result tests for PDL.
- API/CLI/MCP parity tests for selectable provider behavior.
- Targeted ruff/pytest, full ruff/pytest, `git diff --check`, plan drift guard,
  and CodeGraph sync/status.

## Closeout

Implemented:

- Added disabled-by-default People Data Labs config under
  `enrichment.providers.people_data_labs`.
- Added selected-provider readiness for paid enrichment, preserving Apollo as
  the default provider.
- Added People Data Labs preview request fields and handoff metadata for the
  Person Enrichment contract without executing network calls.
- Added People Data Labs result normalization for explicit result imports.
- Added API, CLI, and MCP provider-selection support for enrichment requests and
  readiness checks.

Validation:

- `.venv/bin/python -m pytest tests/test_config.py::test_load_enrichment_config_nested_provider_tables tests/test_enrichment.py::test_people_data_labs_provider_contract_is_zero_call_and_secret_free tests/test_api.py::test_api_enrichment_request_can_select_people_data_labs_without_call tests/test_cli_surfaces.py::test_cli_enrichment_request_can_select_people_data_labs_without_call tests/test_mcp.py::test_mcp_enrichment_request_can_select_people_data_labs_without_call -q`
  passed with 5 tests.
- `.venv/bin/python -m pytest tests/test_config.py tests/test_enrichment.py -q`
  passed with 26 tests.
- `.venv/bin/python -m pytest tests/test_api.py tests/test_mcp.py -q` passed
  with 64 tests.
- `.venv/bin/python -m pytest tests/test_cli_surfaces.py -q` passed with 52
  tests.
- `.venv/bin/ruff check src/business_card_watchdog/config.py src/business_card_watchdog/enrichment.py src/business_card_watchdog/service.py src/business_card_watchdog/api.py src/business_card_watchdog/cli.py src/business_card_watchdog/mcp.py tests/test_config.py tests/test_enrichment.py tests/test_api.py tests/test_cli_surfaces.py tests/test_mcp.py`
  passed.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `.venv/bin/python scripts/check_plan_drift.py` passed.
- `.venv/bin/python -m pytest -q` passed with 363 tests.
- `codegraph sync /home/ecochran76/workspace.local/business-card-watchdog && codegraph status /home/ecochran76/workspace.local/business-card-watchdog`
  reported the index already up to date, 60 files, 1,955 nodes, and 2,209
  edges.

Safety:

- This slice did not make live People Data Labs, Apollo, public-web, Google
  Contacts, Odoo, or Odollo calls. It did not run paid API enrichment, process
  configured SyncThing/private watch inputs, mutate contact fields from provider
  output, or write sink records.

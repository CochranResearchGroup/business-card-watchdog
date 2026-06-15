# Plan 0020 | Child Lookup Result And Duplicate Assessment

State: CLOSED
Product authority: `PRODUCT_SPEC.md`

## Scope

Import supplied downstream lookup evidence for prepared child contacts and assess
child downstream duplicate state without live sink calls.

## Non-Goals

- Do not process private SyncThing images in validation.
- Do not execute live Google Contacts, Odoo, or Odollo lookup/write/readback.
- Do not perform public-web search or paid enrichment.
- Do not resolve child duplicate decisions.
- Do not write sink contacts or promote child contacts into parent job state.

## Acceptance Criteria

- Service records child sink lookup results from supplied fixture matches.
- Service assesses child downstream duplicate state from the child lookup result.
- CLI exposes child lookup-result import and child duplicate assessment commands.
- API exposes child lookup-result import and child duplicate assessment routes.
- MCP exposes child lookup-result import and child duplicate assessment tools.
- Child lookup and duplicate artifacts preserve parent job ID, candidate ID, and
  work item ID.
- Artifacts report zero live writes and zero network calls.
- Focused synthetic tests cover service, CLI, API, and MCP behavior.

## Execution Log

### Slice 0020-A | 2026-06-15 | Child Lookup Evidence Import

Implemented:

- Added `BusinessCardService.record_child_sink_lookup_result`.
- Added `BusinessCardService.assess_child_downstream_duplicates`.
- Added CLI commands `reviews child-lookup-result` and
  `reviews child-assess-duplicates`.
- Added API routes `POST /reviews/children/{candidate_id}/sink-lookup-result`
  and `POST /reviews/children/{candidate_id}/downstream-duplicate-assessment`.
- Added MCP tools `business_card_watchdog_child_sink_lookup_result` and
  `business_card_watchdog_child_downstream_duplicate_assessment`.
- Added synthetic multi-card coverage for service, CLI, API, and MCP lookup
  evidence import plus duplicate assessment.

Validation:

- `.venv/bin/python -m pytest tests/test_review_surface.py::test_child_lookup_result_and_duplicate_assessment_use_fixture_matches tests/test_cli_surfaces.py::test_cli_child_lookup_result_and_duplicate_assessment tests/test_api.py::test_api_child_lookup_result_and_duplicate_assessment tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_child_lookup_result_and_duplicate_assessment -q` passed with 5 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/cli.py src/business_card_watchdog/api.py src/business_card_watchdog/mcp.py tests/test_review_surface.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py` passed.
- `.venv/bin/python -m pytest -q` passed with 255 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This slice writes only local child lookup evidence and duplicate assessment
  artifacts from supplied fixture matches. It does not process private SyncThing
  images, execute live lookup, resolve duplicates, route to sinks, enrich, write
  contacts, run public-web search, call paid APIs, or call GWS/Odollo/Odoo.

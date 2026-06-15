# Plan 0026 | Child Selected Target Abandonment Reset

State: CLOSED
Product authority: `PRODUCT_SPEC.md`

## Scope

Create a no-live child selected-target abandonment artifact and replacement
reset packet so a future child target preview can proceed after an explicit
operator reset.

## Non-Goals

- Do not create `selected_live_target.json`.
- Do not delete or mutate previous child target packet artifacts.
- Do not execute live Google Contacts, Odoo, or Odollo lookup/write/readback.
- Do not process private SyncThing images in validation.
- Do not perform public-web search or paid enrichment.
- Do not write sink contacts.
- Do not promote child contacts into parent job state.

## Acceptance Criteria

- Service writes a child selected-target abandonment artifact from an existing
  child selected-target audit.
- Service writes a replacement reset packet that confirms replacement is
  unblocked after abandonment.
- CLI exposes child abandonment and replacement reset commands.
- API exposes child abandonment and replacement reset routes.
- MCP exposes child abandonment and replacement reset tools.
- Artifacts report zero live writes and zero network calls.
- Synthetic tests cover service, CLI, API, and MCP behavior.

## Execution Log

### Slice 0026-A | 2026-06-15 | Offline Child Abandonment Reset

Implemented:

- Add child selected-target abandonment service method.
- Add child replacement reset packet service method.
- Add CLI/API/MCP surfaces.
- Add synthetic multi-card tests and full local validation evidence.

Validation:

- `.venv/bin/python -m pytest tests/test_review_surface.py::test_child_selected_target_response_validation_and_checklist tests/test_cli_surfaces.py::test_cli_child_selected_target_response_validation_and_checklist tests/test_api.py::test_api_child_selected_target_response_validation_and_checklist tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_child_selected_target_response_validation_and_checklist -q` passed with 5 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/cli.py src/business_card_watchdog/api.py src/business_card_watchdog/mcp.py tests/test_review_surface.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py` passed.
- `.venv/bin/python -m pytest -q` passed with 267 tests.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `uv build --out-dir dist` built source and wheel distributions.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This slice writes only local child selected-target abandonment and
  replacement reset artifacts. It does not create, delete, replace, or mutate
  selected-target packets, process private SyncThing images, execute live
  lookup, route to live sinks, enrich, write contacts, run public-web search,
  call paid APIs, or call GWS/Odollo/Odoo.

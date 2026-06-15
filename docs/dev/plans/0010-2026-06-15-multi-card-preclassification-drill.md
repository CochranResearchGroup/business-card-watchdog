# Plan 0010 | Multi-Card Preclassification Drill

State: CLOSED
Product authority: `PRODUCT_SPEC.md`

## Scope

Add a fixture-only proof that deterministic image preclassification can detect and record multiple business-card-like rectangles in one phone-photo-like image before OCR/App Intelligence.

## Non-Goals

- Do not process private SyncThing images.
- Do not invoke OCR/App Intelligence.
- Do not run public-web search or paid enrichment.
- Do not call GWS, Odollo, Odoo, or any live sink.
- Do not split real multi-card photos into child OCR jobs in this slice.

## Acceptance Criteria

- A synthetic multi-card fixture is generated under the cache directory.
- The OpenCV rectangle analyzer records at least three candidate card boxes.
- The result is persisted as run-level drill and preclassification artifacts.
- CLI, API, and MCP surfaces expose the same shared service method.
- CI installs the vision extra so OpenCV preclassification coverage runs upstream.
- Validation includes focused tests, full tests, lint, build, gitleaks, diff check, CodeGraph sync/status, commit, push, and CI watch.

## Execution Log

### Slice 0010-A | 2026-06-15 | Fixture Multi-Card Preclassification Drill

Implemented:

- Added `business-card-watchdog.multi-card-preclassification-drill.v1`.
- Added a synthetic cache-local multi-card image writer for fixture drills.
- Added service `BusinessCardService.multi_card_preclassification_drill`.
- Added CLI `bcw drills multi-card-preclassification`.
- Added API `POST /drills/multi-card-preclassification`.
- Added MCP tool `business_card_watchdog_multi_card_preclassification_drill`.
- Operator dashboard command/API/MCP maps now advertise the multi-card preclassification drill.
- Updated CI to install `.[dev,vision]` so OpenCV contour coverage runs upstream.
- Updated README and public upstream validation docs for the new drill and vision extra.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_multi_card_preclassification_drill_records_candidate_boxes tests/test_cli_surfaces.py::test_cli_multi_card_preclassification_drill_records_candidate_boxes tests/test_api.py::test_api_multi_card_preclassification_drill_records_candidate_boxes tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_multi_card_preclassification_drill_records_candidate_boxes -q` passed with 5 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/cli.py src/business_card_watchdog/api.py src/business_card_watchdog/mcp.py tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py` passed.
- `.venv/bin/python -m pytest -q` passed with 238 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

Safety:

- This was fixture-only preclassification proof. It did not process private SyncThing inputs, invoke OCR/App Intelligence, run public-web search, call paid enrichment, run live lookup, run live write, run readback, or call GWS/Odollo/Odoo.

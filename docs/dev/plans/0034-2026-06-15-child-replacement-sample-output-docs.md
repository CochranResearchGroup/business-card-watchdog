# Plan 0034 | Child Replacement Sample Output Documentation

State: CLOSED
Product authority: `PRODUCT_SPEC.md`

## Scope

Add operator sample output documentation for the child replacement readiness
drill so operators and agent loops can inspect stale/readiness, review bundle,
HTML, workbook, and dashboard evidence from one synthetic artifact.

## Non-Goals

- Do not process private SyncThing images.
- Do not run public-web search or paid enrichment.
- Do not execute live Google Contacts, Odoo, or Odollo lookup/write/readback.
- Do not treat fixture command-copy text as live approval.
- Do not store raw operator response or acknowledgement text in sample output.

## Acceptance Criteria

- `drills child-replacement-readiness` writes an operator-readable markdown
  sample output artifact in the synthetic run directory.
- The sample output summarizes readiness states, closeout rollup, review
  artifact paths, dashboard summary, commands, and stop conditions.
- CLI/API/MCP drill responses expose the sample output artifact path.
- Checked-in operations documentation explains how to generate and inspect the
  sample output.
- Focused tests prove the sample output exists and omits raw safety-confirmation
  text.

## Execution Log

### Slice 0034-A | 2026-06-15 | Offline Child Replacement Sample Output

Status: implemented.

Implemented:

- Added `child_replacement_readiness_sample_output.md` generation to
  `drills child-replacement-readiness`.
- Added `sample_outputs.child_replacement_readiness_markdown_path` to the drill
  payload.
- Added a `child_replacement_readiness_sample_output` run artifact entry.
- Updated CLI text output to show the sample output path.
- Added operations documentation for the generated child replacement sample
  output.
- Added service, CLI, API, and MCP assertions for sample output visibility.

Safety:

- This slice uses synthetic fixture drill data only. It does not process private
  SyncThing images, run public-web search, call paid enrichment, execute live
  sink calls, or write Google Contacts/Odoo/Odollo records.

Validation:

- `.venv/bin/python -m pytest tests/test_review_surface.py::test_service_child_replacement_readiness_drill_exports_operator_samples tests/test_cli_surfaces.py::test_cli_child_replacement_readiness_drill_exports_operator_samples tests/test_api.py::test_api_child_replacement_readiness_drill_exports_operator_samples tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_child_replacement_readiness_drill_exports_operator_samples -q` passed with 5 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/cli.py tests/test_review_surface.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py` passed.
- `.venv/bin/python -m pytest -q` passed with 271 tests.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `rg -n "child-replacement-sample-output|child_replacement_readiness_sample_output|Child Replacement Readiness Sample Output|child_replacement_readiness_markdown_path" README.md docs src tests` passed.
- `uv build --out-dir dist` built source and wheel distributions.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `codegraph sync && codegraph status` passed; index is up to date.

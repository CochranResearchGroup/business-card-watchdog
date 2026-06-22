# Plan 0071 | Contact Review Safe Loop

State: CLOSED
Date: 2026-06-22

## Purpose

Execute the Plan 0060 Milestone 4 bounded safe-loop slice over database-backed
contact review states.

## Scope

- Add a bounded safe-loop service method over proposed contact review states.
- Preview safe-loop actions by default.
- Apply only explicitly safe `reject` decisions.
- Keep recommendation acceptance as an explicit operator decision.
- Expose a CLI JSON surface for preview/apply.

## Non-Goals

- No autonomous acceptance of recommendations.
- No contact-field mutation from model output.
- No sink writes, enrichment calls, web search, or paid API calls.
- No unbounded agent loop.
- No API/MCP expansion in this slice.

## Acceptance Criteria

- Proposed review states can be previewed with bounded safe-loop decisions.
- Only recommendations with explicit safe-auto-reject evidence can be applied.
- Unsafe or accept-style recommendations are skipped with reasons.
- Applying the loop records host-owned rejection decisions and audit notes.
- CLI JSON covers preview and apply flows.

## Validation

- Contact-store/service/CLI tests.
- Targeted ruff, targeted pytest, full pytest, plan drift guard, `git diff
  --check`, and CodeGraph sync/status.

## Closeout

Implemented:

- Added a bounded contact review-state safe loop.
- Previewed actions by default and applied decisions only when `--apply` is
  provided.
- Limited automatic action to explicit safe auto-rejection evidence:
  `safe_to_auto_continue=true` and `safe_auto_decision=reject`.
- Preserved explicit operator control for recommendation acceptance.
- Added `bcw contacts review-safe-loop` CLI JSON support.

Validation:

- `.venv/bin/python -m pytest tests/test_contact_store.py -q` passed with 5
  tests.
- `.venv/bin/python -m pytest tests/test_cli_surfaces.py tests/test_service.py tests/test_contact_store.py -q`
  passed with 168 tests.
- `.venv/bin/python -m pytest tests/test_api.py tests/test_mcp.py -q` passed
  with 60 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/cli.py tests/test_contact_store.py`
  passed.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `.venv/bin/python scripts/check_plan_drift.py` passed.
- `.venv/bin/python -m pytest -q` passed with 357 tests.
- `codegraph sync /home/ecochran76/workspace.local/business-card-watchdog && codegraph status /home/ecochran76/workspace.local/business-card-watchdog`
  reported the index already up to date, 60 files, 1,928 nodes, and 2,562
  edges.

Safety:

- This slice did not accept recommendations automatically, mutate contact
  fields, run enrichment providers, run public-web search, perform live
  lookup/write/readback, or write Google Contacts, Odoo, or Odollo records.

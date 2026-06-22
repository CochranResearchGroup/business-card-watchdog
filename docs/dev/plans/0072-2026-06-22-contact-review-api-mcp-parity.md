# Plan 0072 | Contact Review API/MCP Parity

State: CLOSED
Date: 2026-06-22

## Purpose

Complete the Plan 0060 Milestone 4 parity gap by exposing contact review-state
recommendations, decisions, and safe-loop controls through API and MCP surfaces.

## Scope

- Add API endpoints for contact review recommendation record/list/decide.
- Add an API endpoint for the bounded contact review safe loop.
- Add MCP tools for the same operations.
- Keep all surfaces host-owned and no-live.

## Non-Goals

- No live sink writes.
- No enrichment calls, web search, or paid API calls.
- No automatic acceptance of recommendations.
- No contact-field mutation from model output.

## Acceptance Criteria

- API can record, list, decide, and safely loop contact review states.
- MCP can record, list, decide, and safely loop contact review states.
- Parity surfaces preserve zero writes/network calls to external systems.
- Existing CLI/service behavior remains unchanged.

## Validation

- API tests.
- MCP manifest and dispatch tests.
- Targeted ruff, targeted pytest, full pytest, `git diff --check`, plan drift
  guard, and CodeGraph sync/status.

## Closeout

Implemented:

- Added API endpoints to record contact review recommendations, list review
  states, apply host-owned decisions, and run the bounded safe loop.
- Added MCP tools for the same contact review-state operations.
- Added API and MCP parity tests proving proposed recommendation, list,
  reject decision, and explicit safe auto-rejection behavior.
- Kept recommendation acceptance outside the safe loop and preserved zero
  external writes/network calls on these surfaces.

Validation:

- `.venv/bin/python -m pytest tests/test_api.py::test_api_contact_review_state_safe_loop_parity tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_contact_review_state_safe_loop_parity -q`
  passed with 3 tests.
- `.venv/bin/python -m pytest tests/test_api.py tests/test_mcp.py -q`
  passed with 62 tests.
- `.venv/bin/ruff check src/business_card_watchdog/api.py src/business_card_watchdog/mcp.py tests/test_api.py tests/test_mcp.py`
  passed.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `.venv/bin/python scripts/check_plan_drift.py` passed.
- `.venv/bin/python -m pytest -q` passed with 359 tests.
- `codegraph sync /home/ecochran76/workspace.local/business-card-watchdog && codegraph status /home/ecochran76/workspace.local/business-card-watchdog`
  reported the index already up to date, 60 files, 1,943 nodes, and 2,352
  edges.

Safety:

- This slice did not accept recommendations automatically, mutate contact
  fields, process configured SyncThing/private watch inputs, run OCR/App
  Intelligence, run enrichment providers, run public-web search, run live
  lookup/write/readback, write Google Contacts, write Odoo, or write Odollo.

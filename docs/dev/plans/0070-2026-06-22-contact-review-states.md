# Plan 0070 | Contact Review States

State: CLOSED
Date: 2026-06-22

## Purpose

Execute the first Plan 0060 Milestone 4 slice by making App Intelligence
recommendations a first-class, database-backed review state over projected
contact rows.

## Scope

- Add contact-level review recommendation storage to the user-scoped contact
  database.
- Store App Intelligence recommendations as evidence with provenance and
  confidence.
- Add host-owned commands to accept or reject a recommendation.
- Expose read/write service and CLI surfaces.
- Keep decisions local and do not trigger sink, enrichment, or route writes.

## Non-Goals

- No autonomous App Intelligence loop.
- No model output as direct contact mutation authority.
- No live Google Contacts, Odoo, or Odollo writes.
- No paid enrichment or public web search.
- No hosted API/MCP surface expansion in this first slice.

## Acceptance Criteria

- A contact can receive a proposed App Intelligence review recommendation.
- Proposed recommendations are visible from contact detail and listable by
  state.
- Accepting or rejecting a recommendation changes only host-owned review state.
- Recommendation recording and decisions are idempotent enough for replay.
- CLI JSON surfaces cover record/list/decide flows.

## Validation

- Contact-store unit tests.
- Service/CLI JSON tests.
- Targeted ruff, targeted pytest, full pytest, plan drift guard, `git diff
  --check`, and CodeGraph sync/status.

## Closeout

Implemented:

- Added `contact_review_states` to the user-scoped contact database.
- Stored App Intelligence recommendations as proposed contact review states
  with source, category, recommendation, rationale, confidence, and evidence
  payloads.
- Added host-owned accept/reject decisions that update review state and preserve
  decision audit evidence.
- Surfaced review states in contact detail.
- Added service and CLI JSON flows for recording, listing, and deciding contact
  review recommendations.

Validation:

- `.venv/bin/python -m pytest tests/test_contact_store.py -q` passed with 4
  tests.
- `.venv/bin/python -m pytest tests/test_cli_surfaces.py tests/test_service.py -q`
  passed with 163 tests.
- `.venv/bin/python -m pytest tests/test_api.py tests/test_mcp.py -q` passed
  with 60 tests.
- `.venv/bin/ruff check src/business_card_watchdog/contact_store.py src/business_card_watchdog/service.py src/business_card_watchdog/cli.py tests/test_contact_store.py`
  passed.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `.venv/bin/python scripts/check_plan_drift.py` passed.
- `.venv/bin/python -m pytest -q` passed with 356 tests.
- `codegraph sync /home/ecochran76/workspace.local/business-card-watchdog && codegraph status /home/ecochran76/workspace.local/business-card-watchdog`
  reported the index already up to date, 60 files, 1,926 nodes, and 2,560
  edges.

Safety:

- This slice did not run autonomous App Intelligence loops, mutate contact
  fields from model output, run enrichment providers, run public-web search,
  perform live lookup/write/readback, or write Google Contacts, Odoo, or Odollo
  records.

# Plan 0077 | Contact Route Selection Packets

State: CLOSED
Date: 2026-06-22

## Purpose

Advance Plan 0060 Milestone 6 by adding database-backed route-selection
approval and command-copy packets for projected contacts, reusing the existing
selected-target gates and keeping live sink writes disabled.

## Scope

- Add contact-scoped route-selection approval packets backed by persisted
  contact-store routing decisions.
- Add contact-scoped route-selection command-copy packets that require the same
  acknowledgement discipline as selected-target command-copy packets.
- Block ambiguous or mismatched target profiles before delegating to
  selected-target gates.
- Expose the packets through service, CLI, API, and MCP surfaces.
- Cover the GWS default route with tests.

## Non-Goals

- No selected-live-target creation.
- No live Google Contacts lookup, write, or readback.
- No Odoo/Odollo route expansion.
- No private SyncThing or scanner input processing.

## Acceptance Criteria

- A projected contact with stored `google_contacts` selected sink state can
  produce a route-selection approval packet from the contact database row.
- The packet blocks if the stored GWS target profile is missing or does not
  match configured `sink.google_contacts_profile`.
- The command-copy packet never executes the command and only reveals copy text
  after explicit acknowledgement.
- API/CLI/MCP surfaces expose the contact-scoped packets.

## Validation

- Service packet tests for ready and blocked profile cases.
- API/CLI/MCP parity tests for the new surfaces.
- Targeted ruff/pytest, full ruff/pytest, `git diff --check`, plan drift guard,
  and CodeGraph sync/status before closeout.

## Closeout

Implemented:

- Added contact-scoped route-selection approval boundary packets backed by
  persisted contact-store routing decisions.
- Added contact-scoped route-selection command-copy packets that delegate to
  the existing selected-target command-copy gate.
- Blocked missing or mismatched configured GWS target profile before
  selected-target delegation.
- Exposed the packets through service, API, CLI, and MCP surfaces.
- Preserved selected-target gates and avoided selected-live-target creation.

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_contact_route_selection_packets_use_projected_gws_route tests/test_service.py::test_service_contact_route_selection_blocks_gws_profile_mismatch tests/test_api.py::test_api_contact_route_selection_packets_use_projected_route tests/test_cli_surfaces.py::test_cli_contact_route_selection_packets_use_projected_route tests/test_mcp.py::test_mcp_contact_route_selection_packets_use_projected_route -q`
  passed with 5 tests.
- `.venv/bin/python -m pytest tests/test_service.py -q` passed with 114 tests.
- `.venv/bin/python -m pytest tests/test_api.py tests/test_cli_surfaces.py tests/test_mcp.py -q`
  passed with 119 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/api.py src/business_card_watchdog/cli.py src/business_card_watchdog/mcp.py tests/test_service.py tests/test_api.py tests/test_cli_surfaces.py tests/test_mcp.py`
  passed.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `.venv/bin/python scripts/check_plan_drift.py` passed.
- `.venv/bin/python -m pytest -q` passed with 372 tests.
- `codegraph sync /home/ecochran76/workspace.local/business-card-watchdog && codegraph status /home/ecochran76/workspace.local/business-card-watchdog`
  reported the index already up to date, 60 files, 1,983 nodes, and 2,093
  edges.

Safety:

- This slice did not run live Google lookup/write/readback, public-web search,
  paid enrichment, Odoo, or Odollo calls. It did not process configured
  SyncThing/private watch inputs, create selected-live-target artifacts, or
  enable live sink writes.

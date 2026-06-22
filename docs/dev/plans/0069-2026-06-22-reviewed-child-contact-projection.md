# Plan 0069 | Reviewed Child Contact Projection

State: CLOSED
Date: 2026-06-22

## Purpose

Execute the Plan 0060 Milestone 3 multi-card promotion gap by making reviewed
child contacts from multi-card images project into the user-scoped contact
store as distinct contacts.

## Scope

- Project `reviewed_child_contact` artifacts as first-class contact rows.
- Use child-specific source identities so multiple reviewed cards from one
  parent image do not overwrite each other.
- Include child review artifacts as contact assets.
- Refresh contact-store projection after child review submission.
- Preserve all child sink/enrichment behavior as dry-run or gated.

## Non-Goals

- No live sink writes.
- No paid enrichment or public web search.
- No automatic approval of child contacts.
- No production OCR/App Intelligence execution for child crops.

## Acceptance Criteria

- Approving multiple child contacts from one multi-card image produces multiple
  user-scoped contact rows.
- Child contact rows retain parent job ID, child candidate ID, work item ID,
  crop path, and review artifact provenance.
- Projection is idempotent.
- Existing parent contact projection remains unchanged.

## Validation

- Child review/projection tests.
- Contact-store idempotency tests.
- Targeted review/preclassifier tests, ruff, `git diff --check`, full pytest,
  plan drift guard, and CodeGraph sync/status.

## Closeout

Implemented:

- Projected `reviewed_child_contact` artifacts into the user-scoped contact
  store as first-class contacts.
- Used child-specific source job IDs in the form
  `<parent_job_id>::<candidate_id>` so multiple reviewed cards from one source
  image remain distinct.
- Preserved parent job, child candidate, work item, crop, and review artifact
  provenance on projected child contact rows.
- Added child review submission, result, and reviewed contact artifacts to the
  child contact asset set.
- Refreshed contact-store projection after child review submission without any
  live sink writes.

Validation:

- `.venv/bin/python -m pytest tests/test_review_surface.py::test_child_review_approval_writes_reviewed_child_contact_artifact tests/test_review_surface.py::test_multiple_reviewed_child_contacts_project_as_distinct_contacts tests/test_contact_store.py::test_contact_store_projects_run_idempotently tests/test_preclassifier.py::test_orchestrator_records_multi_card_candidate_manifest -q`
  passed with 4 tests.
- `.venv/bin/python -m pytest tests/test_review_surface.py tests/test_preclassifier.py tests/test_contact_store.py -q`
  passed with 20 tests.
- `.venv/bin/python -m pytest tests/test_api.py tests/test_cli_surfaces.py tests/test_mcp.py -q`
  passed with 111 tests.
- `.venv/bin/ruff check src/business_card_watchdog/contact_store.py src/business_card_watchdog/service.py tests/test_review_surface.py`
  passed.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `.venv/bin/python scripts/check_plan_drift.py` passed.
- `.venv/bin/python -m pytest -q` passed with 355 tests.
- `codegraph sync /home/ecochran76/workspace.local/business-card-watchdog && codegraph status /home/ecochran76/workspace.local/business-card-watchdog`
  reported the index already up to date, 60 files, 1,918 nodes, and 2,552
  edges.

Safety:

- This slice did not run production OCR/App Intelligence for child crops, run
  enrichment providers, run public-web search, perform live lookup/write/readback,
  or write Google Contacts, Odoo, or Odollo records.

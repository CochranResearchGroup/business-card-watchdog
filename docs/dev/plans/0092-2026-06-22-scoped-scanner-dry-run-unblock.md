# Plan 0092 | Scoped Scanner Dry-Run Unblock

State: CLOSED
Date: 2026-06-22

Parent: Plan 0060 Milestone 9

## Purpose

Use the operator-approved scanner input to unblock Plan 0060 Milestone 9 without
turning the configured private backlog into an unbounded continuation task.

## Scope

- Validate the operator response for the scanner watched input.
- Add scoped watcher execution for `--input-ref`.
- Add a positive source/document `--limit` to the copied watch command.
- Run one bounded scanner dry-run source/document.
- Close out the run through dry-run closeout, review handoff, contact
  projection, review-surface inspection, route readiness, and live-target
  candidate inspection.

## Non-Goals

- No broad scanner backlog processing.
- No public-web search, paid enrichment, live lookup, live write, or readback.
- No selected live target creation.
- No committing runtime manifests, private paths, private filenames, raw card
  images, or OCR dumps.

## Implementation

- `PollingWatcher.scan_once` and `PollingWatcher.run` accept selected input refs
  and an optional positive processed-source limit.
- `bcw watch` accepts repeatable `--input-ref` and optional `--limit`.
- `watch-dry-run-command-copy-packet` emits scoped command text:
  `watch --once --dry-run --input-ref <input_ref> --limit <n>`.
- API command-copy requests accept the same limit.
- Service readiness text and operator docs now point to scoped copied commands
  instead of generic `watch --once --dry-run`.

## Runtime Evidence

- Operator response validation reached `state = "ready_for_command_copy"` for
  the scanner input ref.
- Command-copy packet reached `state = "ready_for_operator_copy"` with
  `selected_input_ref = "input_1"` and `selected_limit = 1`.
- The exact bounded copied command completed successfully.
- The bounded run id was `2026-06-22T12-27-33+00-00`.
- Dry-run closeout returned `state = "ready_for_review_and_routing"`.
- Dry-run review handoff returned `state = "ready_for_operator_review"` with
  24 jobs.
- Contact projection produced 3 projected contacts and 48 projected assets.
- Live-target candidate inspection returned 24 candidates, all blocked.
- Route readiness returned `state = "operator_review_required"` with 3 jobs
  requiring explicit operator review and 0 route-ready jobs.

## Safety Notes

An initial scanner-only dry-run without a limit was interrupted after proving the
scope was too broad. The completed evidence for this plan comes from the later
bounded command-copy path with `--limit 1`.

All closeout, review, projection, route-readiness, and candidate commands stayed
local and reported zero live writes and zero network calls.

## Validation

- `.venv/bin/python -m pytest tests/test_watcher.py::test_watcher_scan_once_can_scope_to_input_ref tests/test_watcher.py::test_watcher_scan_once_can_limit_processed_sources tests/test_service.py::test_service_watch_dry_run_selection_handoff_validates_response_and_command_copy tests/test_service.py::test_service_watch_dry_run_command_copy_blocks_invalid_limit tests/test_cli_surfaces.py::test_cli_watch_accepts_scoped_input_refs -q`
  passed with 5 tests.
- `.venv/bin/ruff check src/business_card_watchdog/watcher.py src/business_card_watchdog/cli.py src/business_card_watchdog/service.py src/business_card_watchdog/api.py tests/test_watcher.py tests/test_service.py tests/test_cli_surfaces.py`
  passed.
- `git diff --check` passed.
- `.venv/bin/python scripts/check_plan_drift.py` passed.

## Outcome

Plan 0060 Milestone 9 is no longer blocked on dry-run input selection. It is now
blocked at the intended review boundary: operator review and route readiness
must approve at least one projected contact before lookup prerequisite closure
or live target selection can proceed.

# Plan 0091 | Milestone 9 Operator Checklist

State: CLOSED
Date: 2026-06-22

Parent: Plan 0060 Milestone 9

## Purpose

Create an operator-facing checklist that connects the current Milestone 9 gate
to the existing no-live dry-run handoff, contact projection, review, and live
target candidate commands.

## Scope

- Add a concise operations checklist for going from one operator-selected
  watched-folder dry-run to live target candidates.
- Link the checklist from the README and live-pilot checklist.
- Run the synthetic watch dry-run execution drill as current no-live proof.
- Preserve the stop rule that private watched inputs require explicit operator
  command-copy acknowledgement.

## Non-Goals

- No private watched-folder processing.
- No OCR of configured private files.
- No live lookup, write, or readback.
- No selected live target creation.
- No public-web search or paid enrichment.

## Closeout Evidence

Implemented:

- Added `docs/operations/milestone-9-dry-run-to-live-target.md`.
- Documented the sequence from synthetic drill, to private backlog readiness, to
  operator response validation, to command-copy packet, to dry-run closeout,
  contact projection, review surface, route readiness, and live target candidate
  inspection.
- Linked the checklist from README and live-pilot operations docs.

Validation:

- `.venv/bin/python -m business_card_watchdog.cli drills watch-dry-run-execution --json`
  returned `state = "passed"` with one synthetic file processed, a completed
  dry-run batch, contact projection artifact evidence, zero writes, zero network
  calls, and no configured watch inputs used.
- `rg -n "milestone-9-dry-run-to-live-target|Plan 0091|watch-dry-run-execution|contact projection|live-target-candidates" README.md docs/operations/milestone-9-dry-run-to-live-target.md docs/operations/live-pilot-checklists.md docs/dev/plans/0060-2026-06-20-product-development-milestone-plan.md docs/dev/plans/0091-2026-06-22-milestone-9-operator-checklist.md ROADMAP.md RUNBOOK.md`
  passed.
- `git diff --check` passed.
- `.venv/bin/python scripts/check_plan_drift.py` passed.

Safety:

- This slice used synthetic fixture data only and did not process configured
  watched-folder backlog or call live/external services.

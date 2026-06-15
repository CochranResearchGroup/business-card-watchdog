# Plan 0041 | Watch Dry-Run Execution Drill

State: implemented
Date: 2026-06-15

## Scope

Add a fixture-backed drill that executes the watched-folder dry-run path through
the real batch orchestrator without touching configured private watch inputs.

The drill should prove:

- a synthetic watched source can be scanned by `PollingWatcher`
- one fixture image is processed through the dry-run batch pipeline
- the fixture skill adapter produces OCR/spec/review artifacts
- normalization and dry-run sink payload planning run without live sink calls
- watcher seen-file state prevents duplicate processing after restart
- service, CLI, API, and MCP surfaces expose the drill

## Non-Goals

- Do not process configured SyncThing/private watch inputs.
- Do not run public-web search or paid enrichment.
- Do not call Google Contacts, Odoo, or Odollo lookup/write/readback surfaces.
- Do not replace the existing no-processing `watch-dry-run-selection` drill.
- Do not use this fixture execution as approval for `watch --once --dry-run`
  against configured private inputs.

## Implementation

- Add `BusinessCardService.watch_dry_run_execution_drill`.
- Add CLI `bcw drills watch-dry-run-execution`.
- Add API `POST /drills/watch-dry-run-execution`.
- Add MCP tool `business_card_watchdog_watch_dry_run_execution_drill`.
- Use a synthetic watched source, a fixture skill adapter, and real
  `PollingWatcher.scan_once(dry_run=True)` execution.
- Write `watch_dry_run_execution_sample_output.md` and
  `watch_dry_run_execution_drill.json`.

## Acceptance Criteria

- The first watcher scan processes exactly one synthetic fixture image.
- A second watcher instance processes zero images because seen-file state
  persisted.
- The processed run completes in dry-run mode with one job.
- The run records contact, review, OCR, and dry-run sink planning artifacts.
- The drill reports `private_sources_used=false`, `writes_attempted=0`, and
  `network_calls_made=0`.
- Service, CLI, API, and MCP tests cover the drill.
- Full local validation passes before push.

## Validation

Completed in Turn 247 and recorded in `RUNBOOK.md`.

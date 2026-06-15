# Plan 0040 | Watch Dry-Run Selection Sample Output

State: implemented
Date: 2026-06-15

## Scope

Add a fixture-backed drill that lets an operator inspect the full watch dry-run
selection path before deciding whether to run against configured private watch
inputs.

The drill should exercise:

- watch backlog preflight
- watch dry-run selection handoff
- operator response validation
- command-copy packet generation
- markdown sample output export
- service, CLI, API, and MCP access

## Non-Goals

- Do not process configured SyncThing/private watch inputs.
- Do not execute the copied `watch --once --dry-run` command.
- Do not run OCR/App Intelligence.
- Do not run public-web search or paid enrichment.
- Do not call Google Contacts, Odoo, or Odollo lookup/write/readback surfaces.

## Implementation

- Add `BusinessCardService.watch_dry_run_selection_drill`.
- Add CLI `bcw drills watch-dry-run-selection`.
- Add API `POST /drills/watch-dry-run-selection`.
- Add MCP tool `business_card_watchdog_watch_dry_run_selection_drill`.
- Write `watch_dry_run_selection_sample_output.md` and
  `watch_dry_run_selection_drill.json` under a fixture run directory.
- Keep operator response and acknowledgement raw text out of sample outputs.
- Record run artifacts in the ledger using normal run state transitions.

## Acceptance Criteria

- The drill uses a synthetic fixture source under the cache directory.
- The drill reports `private_sources_used=false`, `files_processed=0`,
  `ocr_attempted=0`, `writes_attempted=0`, and `network_calls_made=0`.
- The command-copy packet reaches `ready_for_operator_copy`.
- The sample output contains only redacted operator fields and no raw safety
  confirmation or acknowledgement text.
- Service, CLI, API, and MCP tests cover the drill.
- Full local validation passes before push.

## Validation

Completed in Turn 246 and recorded in `RUNBOOK.md`.

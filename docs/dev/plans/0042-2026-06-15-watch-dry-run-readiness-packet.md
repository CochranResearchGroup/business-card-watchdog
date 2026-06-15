# Plan 0042 | Watch Dry-Run Readiness Packet

State: implemented
Date: 2026-06-15

## Scope

Add a no-processing readiness packet that lets an operator inspect whether the
configured watch backlog is ready for the private-source dry-run approval flow.

The packet should combine:

- redacted watch backlog preflight state
- redacted dry-run selection handoff state
- required fixture execution drill review step
- required operator response validation step
- required command-copy acknowledgement step
- explicit stop conditions before `watch --once --dry-run`

## Non-Goals

- Do not process configured SyncThing/private watch inputs.
- Do not run OCR/App Intelligence.
- Do not return copyable `watch --once --dry-run` text.
- Do not run public-web search or paid enrichment.
- Do not call Google Contacts, Odoo, or Odollo lookup/write/readback surfaces.

## Implementation

- Add `BusinessCardService.watch_dry_run_readiness`.
- Add CLI `bcw watch-dry-run-readiness`.
- Add API `POST /watch/dry-run-readiness`.
- Add MCP tool `business_card_watchdog_watch_dry_run_readiness`.
- Keep configured paths and filenames redacted.
- Write `watch_dry_run_readiness.json` only when requested.

## Acceptance Criteria

- The packet reports aggregate backlog counts and redacted input entries.
- The packet is `ready_for_operator_response` only when configured backlog is
  settled and the selection handoff is available.
- The packet leaves `command_copy_text=null`.
- The packet reports zero files processed, zero OCR attempts, zero writes, and
  zero network calls.
- Service, CLI, API, and MCP coverage prove redaction and no-processing behavior.
- Full local validation passes before push.

## Validation

Completed in Turn 248 and recorded in `RUNBOOK.md`.

# Plan 0090 | Milestone 9 Dry-Run Selection Handoff

State: CLOSED
Date: 2026-06-22

Parent: Plan 0060 Milestone 9

## Purpose

Bridge the Plan 0060 Milestone 9 gap found in Plan 0089: the runtime is ready,
but the user-scoped contact store has no contact rows and therefore no live
target candidates. This slice records the no-live operator handoff required to
create an operator-selected dry-run batch from the configured watched folders
without processing private backlog from generic continuation.

## Scope

- Run the no-live watch dry-run readiness packet.
- Run the no-live watch dry-run selection handoff.
- Confirm the practice corpus manifest remains runtime-only and is not committed
  to git.
- Record the exact operator-gated sequence needed before any private watched
  file can be processed in dry-run mode.

## Non-Goals

- No private watched-file processing.
- No OCR, PDF rasterization, crop generation, enrichment, routing, or contact
  projection from configured private watched folders.
- No `selected_live_target.json` creation.
- No live lookup, write, readback, public-web search, or paid enrichment.
- No committing runtime manifests, private filenames, private paths, card
  images, or OCR output.

## Handoff Evidence

- `watch-dry-run-readiness --json` returned
  `state = "ready_for_operator_response"`.
- The watch backlog contains 1,833 settled items across the two configured
  watched inputs, with no unsettled files and no truncated scan.
- The readiness packet preserved the stop rule by withholding `command_copy_text`
  until operator response validation and acknowledgement.
- `watch-dry-run-selection-handoff --json` returned
  `state = "awaiting_operator_response"` with entries for `$fsr:sync_phone` and
  `$fsr:scanner`.
- The handoff wrote the runtime artifact
  `~/.local/share/business-card-watchdog/watch_dry_run_selection_handoff.json`.
- `watch-practice-corpus-manifest --json` refreshed the runtime-only practice
  corpus manifest at
  `~/.local/share/business-card-watchdog/practice_corpus_manifest.json` with
  1,833 entries. That artifact is not committed because it may contain private
  filenames even when paths are redacted.

## Required Operator Sequence

Before the service may process private watched-folder backlog for Milestone 9
candidate creation, a human operator must:

1. Review the fixture drill:
   `bcw drills watch-dry-run-execution --json`.
2. Inspect the handoff:
   `bcw watch-dry-run-selection-handoff --json`.
3. Choose exactly one input such as `input_0` (`$fsr:sync_phone`) or `input_1`
   (`$fsr:scanner`).
4. Provide an operator response matching:
   `input_ref=<input_ref> operator=<operator> mode=dry_run safety_confirmation=<operator-confirms-private-source-dry-run>`.
5. Validate the response:
   `bcw watch-dry-run-validate-response --response <operator-response> --json`.
6. Build the command-copy packet with acknowledgement:
   `bcw watch-dry-run-command-copy-packet --response <operator-response> --acknowledgement <operator-acknowledgement> --limit 1 --json`.
7. Only after the packet reports ready for operator copy, run the copied
   `watch --once --dry-run --input-ref <input_ref> --limit <n>` command.

## Outcome

Plan 0060 Milestone 9 remains ready for operator action, not generic automated
continuation. The next meaningful product step is an explicit operator-selected
dry-run batch from one watched input, followed by contact projection and review,
which can then produce live target candidates for Plan 0009.

## Validation

- `.venv/bin/python -m business_card_watchdog.cli watch-dry-run-readiness --json`
  returned `state = "ready_for_operator_response"`, `files_processed = 0`,
  `ocr_attempted = 0`, `writes_attempted = 0`, and `network_calls_made = 0`.
- `.venv/bin/python -m business_card_watchdog.cli watch-dry-run-selection-handoff --json`
  returned `state = "awaiting_operator_response"` and wrote the handoff artifact
  under user-scoped runtime state.
- `.venv/bin/python -m business_card_watchdog.cli watch-practice-corpus-manifest --json`
  refreshed the user-scoped runtime manifest without OCR, rasterization, crop
  creation, enrichment, routing, sink writes, or network calls.

## Safety

This slice made no live calls, processed no watched files, created no selected
target, and committed no private runtime artifacts.

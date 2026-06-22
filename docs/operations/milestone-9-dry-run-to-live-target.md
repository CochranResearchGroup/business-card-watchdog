# Milestone 9 Dry-Run To Live Target Checklist

This checklist turns the current Plan 0060 Milestone 9 state into an operator
workflow. It starts from a configured watched-folder backlog and stops before any
live lookup, write, readback, public-web search, or paid enrichment.

Current boundary:

- The user-scoped contact store is initialized but has no live-target
  candidates until an operator-selected dry-run batch is processed and projected.
- The configured watched inputs are `$fsr:sync_phone` and `$fsr:scanner`.
- Generic continuation must not process private watched-folder backlog.
- A human operator must choose one input and approve a dry-run command-copy
  packet before private files are processed.

## 1. Prove The Synthetic Path

Run the fixture execution drill first:

```bash
.venv/bin/bcw drills watch-dry-run-execution --json
```

Expected evidence:

- `state = "passed"`
- `configured_watch_inputs_not_used = true`
- `run_was_dry_run = true`
- `contact_candidate_written = true`
- `contact_store_projected = true` or a `contact_store_projection` artifact kind
- `writes_attempted = 0`
- `network_calls_made = 0`

This drill is not approval to process the configured watch backlog. It only
proves the no-live watcher and projection path against synthetic fixture data.

## 2. Inspect The Private Backlog Readiness

```bash
.venv/bin/bcw watch-dry-run-readiness --json
.venv/bin/bcw watch-dry-run-selection-handoff --json
```

Expected evidence:

- `watch-dry-run-readiness` reports `state = "ready_for_operator_response"`.
- `watch-dry-run-selection-handoff` reports
  `state = "awaiting_operator_response"`.
- The handoff entries name redacted configured refs such as `$fsr:sync_phone`
  and `$fsr:scanner`.
- `command_copy_text` is absent until response validation and acknowledgement.

## 3. Choose One Input

Choose one handoff entry only:

- `input_0` for `$fsr:sync_phone`
- `input_1` for `$fsr:scanner`

Build an operator response:

```bash
OPERATOR_RESPONSE="input_ref=<input_ref> operator=<operator> mode=dry_run safety_confirmation=<operator confirms this private-source dry-run is intended>"
```

Validate it:

```bash
.venv/bin/bcw watch-dry-run-validate-response \
  --response "$OPERATOR_RESPONSE" \
  --json
```

## 4. Build The Command-Copy Packet

```bash
OPERATOR_ACK="I understand this will dry-run the configured private watch backlog"

.venv/bin/bcw watch-dry-run-command-copy-packet \
  --response "$OPERATOR_RESPONSE" \
  --acknowledgement "$OPERATOR_ACK" \
  --json
```

Only continue when the packet reports ready for operator copy and no blocked
reasons.

## 5. Run The Copied Dry-Run Command

Run only the exact command emitted in `command_copy_text`.

The dry run may process private watched-folder files, but it must remain dry-run
only. Do not run public-web search, paid enrichment, live lookup, live write, or
live readback from this step.

## 6. Close Out The Dry-Run Batch

After the dry run completes, capture the run id and run:

```bash
.venv/bin/bcw runs dry-run-closeout <run-id> --json
.venv/bin/bcw runs dry-run-review-handoff <run-id> --json
.venv/bin/bcw contacts project-run <run-id> --json
.venv/bin/bcw contacts review-surface --limit 20 --json
```

Then continue through review and route readiness:

```bash
.venv/bin/bcw runs dry-run-safe-loop <run-id> --limit 5 --json
.venv/bin/bcw runs review-route-readiness <run-id> --json
.venv/bin/bcw runs lookup-selection-packet <run-id> --operator <operator> --json
.venv/bin/bcw runs close-lookup-prerequisites <run-id> --operator <operator> --json
.venv/bin/bcw live-target-candidates --run-id <run-id> --sink google_contacts --json
.venv/bin/bcw live-selection-requirements --run-id <run-id> --sink google_contacts --no-write --json
```

Do not create `selected_live_target.json` until a human selects one reviewed
contact, one run, one job, one sink, one operator, and one approval scope.

## Stop Conditions

Stop before live target selection if:

- The synthetic drill fails.
- The private backlog readiness packet is not ready.
- The handoff has no intended input.
- The command-copy packet is blocked or lacks acknowledgement.
- The dry-run batch is not completed.
- Dry-run closeout reports network calls, writes, live sink markers, or pilot
  artifacts.
- The contact review surface has no acceptable reviewed contact.
- Route readiness, lookup prerequisites, or duplicate checks are blocked.

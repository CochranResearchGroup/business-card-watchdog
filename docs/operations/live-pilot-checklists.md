# Live Pilot Checklists

These checklists are for explicit operator-approved live smoke work. Do not run them from generic CI, safe agent-loop continuation, or broad batch automation.

Use only non-sensitive test card data for first pilots.

Before selecting a real target, use the synthetic rehearsal drill to prove the local no-live control path:

```bash
.venv/bin/bcw drills live-pilot-rehearsal --json
```

The drill creates a synthetic fixture run and rehearses selected-target creation, selected-target audit, lookup handoff, redacted readiness export, execution checklist, and command-copy packet without executing the copied command or calling GWS/Odollo/Odoo. It is not approval for a real target.

If the contact store has no reviewed target candidates yet, first follow
`docs/operations/milestone-9-dry-run-to-live-target.md`. That checklist covers
the operator-selected watched-folder dry run, contact projection, review surface,
route readiness, and live-target candidate inspection required before any real
live target can be selected.

## Read-Only Lookup Smoke

Purpose: prove Google Workspace Contacts and/or Odollo/Odoo lookup adapters can read matching contacts without writing.

Required inputs:

- `run_id`
- `job_id`
- `sink`: `google_contacts` or `odoo`
- `operator`
- `scope`: `lookup`
- tenant/profile safety confirmation text
- configured local sink auth/profile outside the repo

Preflight:

```bash
.venv/bin/bcw sinks check --json
.venv/bin/bcw jobs show <job-id> --run-id <run-id>
.venv/bin/bcw reviews list --run-id <run-id> --state all
```

Prepare selected-target approval evidence:

```bash
.venv/bin/bcw live-selection-requirements \
  --run-id <run-id> \
  --sink google_contacts \
  --no-write
.venv/bin/bcw sinks live-selection-packet \
  <job-id> \
  --run-id <run-id> \
  --sink google_contacts \
  --operator <operator> \
  --scope lookup
.venv/bin/bcw runs live-pilot-handoff <run-id> --no-write
# Run the packet's printed "Validate prefilled response:" command first, then replace
# safety_confirmation=<tenant-profile-account-confirmation> with the operator's tenant/profile confirmation.
.venv/bin/bcw runs live-pilot-validate-response \
  <run-id> \
  --response "run_id=<run-id> job_id=<job-id> sink=google_contacts operator=<operator> scope=lookup safety_confirmation=<operator confirms this run/job/sink uses the intended tenant/profile>"
.venv/bin/bcw sinks select-live-target \
  <job-id> \
  --run-id <run-id> \
  --sink google_contacts \
  --operator <operator> \
  --scope lookup \
  --safety-confirmation "<operator confirms this run/job/sink uses the intended tenant/profile>" \
  --json
.venv/bin/bcw sinks selected-target-audit \
  <job-id> \
  --run-id <run-id> \
  --scope lookup \
  --no-write
.venv/bin/bcw runs live-pilot-status <run-id> --no-write
```

Use `--sink odoo` when the read-only smoke target is Odollo/Odoo. Start with `live-selection-requirements` when you need candidate-specific packet and approval commands. Use the selection packet's `Validate prefilled response:` command for the first read-only check, then validate the filled response after replacing the confirmation placeholder. Use `runs live-pilot-handoff --no-write` when an agent loop needs the current concrete operator response template; it does not create `selected_live_target.json`. Validation is read-only and only returns blockers or the exact select-target command. The packet must show `existing_selected_target.can_select_replacement_now = true` before selecting a replacement; if it shows `replacement_requires_abandonment = true`, run `abandon-live-pilot` for the old target first and then prepare a new packet.
If validation is run after the selected target already exists, it reports the active-target state and omits the select-target command. In that case, follow the returned `post_selection_sequence`, which begins with selected-target audit and lookup-smoke handoff.
Add `--json` to review commands when you need to archive the full structured artifact.

Final pre-live command-copy gate:

```bash
OPERATOR_RESPONSE="run_id=<run-id> job_id=<job-id> sink=google_contacts operator=<operator> scope=lookup safety_confirmation=<operator confirms this run/job/sink uses the intended tenant/profile>"
OPERATOR_ACK="acknowledge run_id=<run-id> job_id=<job-id> sink=google_contacts operator=<operator> copy command"

.venv/bin/bcw runs live-pilot-operator-rehearsal-from-response \
  <run-id> \
  --response "$OPERATOR_RESPONSE" \
  --json
.venv/bin/bcw runs live-pilot-readiness-export-from-response \
  <run-id> \
  --response "$OPERATOR_RESPONSE" \
  --json
.venv/bin/bcw runs live-pilot-execution-checklist-from-response \
  <run-id> \
  --response "$OPERATOR_RESPONSE" \
  --json
.venv/bin/bcw runs live-pilot-command-copy-packet-from-response \
  <run-id> \
  --response "$OPERATOR_RESPONSE" \
  --acknowledgement "$OPERATOR_ACK" \
  --json
```

Only copy the command from `command_copy_text` when the command-copy packet reports `state = ready_for_operator_copy`, `acknowledgement_ok = true`, and an empty `blocked_reasons` list. This packet is still no-send: it validates the persisted redacted readiness export and acknowledgement, but it never executes the lookup pilot.

Prepare lookup artifacts:

```bash
.venv/bin/bcw sinks lookup-plan <job-id> --run-id <run-id> --json
.venv/bin/bcw sinks adapter-request <job-id> --run-id <run-id> --phase lookup --json
.venv/bin/bcw sinks lookup-readiness \
  <job-id> \
  --run-id <run-id> \
  --sink google_contacts \
  --json
.venv/bin/bcw sinks lookup-smoke-handoff \
  <job-id> \
  --run-id <run-id> \
  --sink google_contacts \
  --approved-by <operator> \
  --json
```

Review `selected_live_target.json`, `selected_live_target_audit.json`, and `sink_lookup_smoke_handoff.json` before running `lookup-pilot --no-simulate`; none of those artifacts is live approval by itself. The selected target is valid only when it names the intended run, job, sink, operator, scope, and tenant/profile safety confirmation.
The command-copy packet is the final pre-live guard. Do not run a copied lookup command if the readiness export is missing, the execution checklist is blocked, the acknowledgement does not match the selected target, or any artifact changed after the readiness export was written.

Run one explicit read-only lookup pilot:

```bash
.venv/bin/bcw sinks lookup-pilot \
  <job-id> \
  --run-id <run-id> \
  --sink google_contacts \
  --approved-by <operator> \
  --no-simulate \
  --json
```

or:

```bash
.venv/bin/bcw sinks lookup-pilot \
  <job-id> \
  --run-id <run-id> \
  --sink odoo \
  --approved-by <operator> \
  --no-simulate \
  --json
```

Review the downstream duplicate assessment before any write:

```bash
.venv/bin/bcw sinks assess-duplicates <job-id> --run-id <run-id> --json
.venv/bin/bcw runs phase-report <run-id>
```

For non-simulated lookup pilots, persisted execution metadata is redacted. Use the normalized sink/resource ID, confidence, basis, and downstream duplicate assessment as the durable review evidence; do not paste raw contact rows into the repo or issue trackers.

Stop conditions:

- `sink_lookup_smoke_handoff.json` is missing, blocked, or names a different run/job/sink/operator.
- `selected_live_target.json` is missing, abandoned, missing `target_safety_confirmed = true`, or names a different run/job/sink/operator/scope.
- `selected_target_audit.json` is missing, blocked, or names a different selected target.
- `live_selection_packet.json` says replacement requires abandonment and no matching `live_pilot_abandonment.json` exists.
- Lookup returns a strong duplicate that has not been reviewed.
- Sink readiness is blocked or references an unexpected profile/tenant.
- The job, run, sink, or reviewer is not the intended pilot target.
- Any command would write to a sink.

## One-Job Write And Readback Pilot

Purpose: write exactly one reviewed contact to exactly one selected sink, then verify it with readback evidence.

Required prior evidence:

- Reviewed contact exists.
- Downstream lookup result exists for the selected sink.
- Duplicate assessment is reviewed or no-match.
- Sink plan exists and names the expected sink.
- Apply preflight exists.
- Apply decision is explicitly approved.
- Apply pilot readiness is ready for the selected sink.
- Operator accepts the remediation limits for the selected sink.
- Selected target exists for the same run/job/sink/operator and has scope `write` or `all`.
- Selected target audit is ready for the selected write/readback scope.

Prepare or refresh selected-target approval evidence:

```bash
.venv/bin/bcw live-selection-requirements \
  --run-id <run-id> \
  --sink google_contacts \
  --no-write
.venv/bin/bcw sinks live-selection-packet \
  <job-id> \
  --run-id <run-id> \
  --sink google_contacts \
  --operator <operator> \
  --scope all
.venv/bin/bcw runs live-pilot-handoff <run-id> --no-write
# Run the packet's printed "Validate prefilled response:" command first, then replace
# safety_confirmation=<tenant-profile-account-confirmation> with the operator's tenant/profile confirmation.
.venv/bin/bcw runs live-pilot-validate-response \
  <run-id> \
  --response "run_id=<run-id> job_id=<job-id> sink=google_contacts operator=<operator> scope=all safety_confirmation=<operator confirms this run/job/sink uses the intended tenant/profile>"
.venv/bin/bcw sinks select-live-target \
  <job-id> \
  --run-id <run-id> \
  --sink google_contacts \
  --operator <operator> \
  --scope all \
  --safety-confirmation "<operator confirms this run/job/sink uses the intended tenant/profile>" \
  --json
.venv/bin/bcw sinks selected-target-audit \
  <job-id> \
  --run-id <run-id> \
  --scope all \
  --no-write
.venv/bin/bcw runs live-pilot-status <run-id> --no-write
```

Start with `live-selection-requirements` when you need candidate-specific packet and approval commands. Use the selection packet's `Validate prefilled response:` command for the first read-only check, then validate the filled response after replacing the confirmation placeholder. Use `runs live-pilot-handoff --no-write` when an agent loop needs the current concrete operator response template; it does not create `selected_live_target.json`. Validation is read-only and only returns blockers or the exact select-target command. If a lookup-only selected target already exists, record `abandon-live-pilot` with the reason for replacement before selecting the broader `all` scope target. Do not hand-edit selected-target artifacts.
If validation is run after the selected target already exists, it reports the active-target state and omits the select-target command. In that case, follow the returned `post_selection_sequence`, which begins with selected-target audit and lookup-smoke handoff.
Add `--json` to review commands when you need to archive the full structured artifact.

Final pre-live command-copy gate:

```bash
OPERATOR_RESPONSE="run_id=<run-id> job_id=<job-id> sink=google_contacts operator=<operator> scope=all safety_confirmation=<operator confirms this run/job/sink uses the intended tenant/profile>"
OPERATOR_ACK="acknowledge run_id=<run-id> job_id=<job-id> sink=google_contacts operator=<operator> copy command"

.venv/bin/bcw runs live-pilot-operator-rehearsal-from-response \
  <run-id> \
  --response "$OPERATOR_RESPONSE" \
  --json
.venv/bin/bcw runs live-pilot-readiness-export-from-response \
  <run-id> \
  --response "$OPERATOR_RESPONSE" \
  --json
.venv/bin/bcw runs live-pilot-execution-checklist-from-response \
  <run-id> \
  --response "$OPERATOR_RESPONSE" \
  --json
.venv/bin/bcw runs live-pilot-command-copy-packet-from-response \
  <run-id> \
  --response "$OPERATOR_RESPONSE" \
  --acknowledgement "$OPERATOR_ACK" \
  --json
```

Only copy the command from `command_copy_text` when the command-copy packet reports `state = ready_for_operator_copy`, `acknowledgement_ok = true`, and an empty `blocked_reasons` list. This packet is still no-send: it validates the persisted redacted readiness export and acknowledgement, but it never executes lookup, write, or readback pilots.

Prepare apply artifacts:

```bash
.venv/bin/bcw sinks plan <job-id> --run-id <run-id> --json
.venv/bin/bcw sinks adapter-request <job-id> --run-id <run-id> --phase write --json
.venv/bin/bcw sinks apply-preflight <job-id> --run-id <run-id> --json
.venv/bin/bcw sinks apply-decision \
  <job-id> \
  --run-id <run-id> \
  --decision approve \
  --reviewer <operator> \
  --reason "one-job pilot approved" \
  --json
.venv/bin/bcw sinks apply-pilot-readiness \
  <job-id> \
  --run-id <run-id> \
  --sink google_contacts \
  --json
.venv/bin/bcw sinks apply-pilot-bundle \
  <job-id> \
  --run-id <run-id> \
  --sink google_contacts \
  --operator <operator> \
  --json
```

Use `--sink odoo` when the one-job pilot target is Odollo/Odoo. Treat readiness as valid only for the selected sink named in the artifact.
Review the selected-target audit and operator bundle before any live write. They list selected-sink commands, artifact paths, missing requirements, stop conditions, and remediation notes.
The command-copy packet is the final pre-live guard. Re-run the readiness export, execution checklist, and command-copy packet after any selected-target, duplicate, apply-decision, write-pilot, or readback evidence changes.

Run one explicit live write pilot:

```bash
.venv/bin/bcw sinks write-pilot \
  <job-id> \
  --run-id <run-id> \
  --sink google_contacts \
  --approved-by <operator> \
  --no-simulate \
  --json
```

or:

```bash
.venv/bin/bcw sinks write-pilot \
  <job-id> \
  --run-id <run-id> \
  --sink odoo \
  --approved-by <operator> \
  --no-simulate \
  --json
```

Prepare and run readback:

```bash
.venv/bin/bcw sinks adapter-request <job-id> --run-id <run-id> --phase readback --json
.venv/bin/bcw sinks readback-pilot \
  <job-id> \
  --run-id <run-id> \
  --sink google_contacts \
  --approved-by <operator> \
  --no-simulate \
  --json
.venv/bin/bcw sinks apply-pilot-report <job-id> --run-id <run-id>
.venv/bin/bcw sinks live-pilot-closeout <job-id> --run-id <run-id> --no-write
```

Use `--sink odoo` for an Odollo/Odoo readback pilot.
Add `--json` to `apply-pilot-report` when another tool needs structured report output.
Run closeout again with `--json` when you are ready to persist the final `live_pilot_closeout.json` artifact.

Completion evidence:

- `selected_live_target.json` exists and records the expected run/job/sink/operator/scope and `target_safety_confirmed = true`.
- `selected_target_audit.json` reports ready for the selected scope.
- `sink_apply_pilot_bundle.json` exists and names the selected sink/operator.
- `sink_write_pilot.json` exists and records the expected sink/resource ID.
- `sink_readback_pilot.json` exists and reports `state = verified`.
- `sink_apply_pilot_report.json` reports complete state for the selected sink.
- `live_pilot_closeout.json` reports complete state for the selected scope or names missing evidence.
- Run phase report no longer points to missing write/readback pilot evidence for the selected job.

Stop conditions:

- Readiness, lookup, duplicate, preflight, decision, or pilot-readiness artifacts are missing.
- Selected-target evidence is missing, stale, abandoned, scope-mismatched, or lacks tenant/profile safety confirmation.
- Any artifact names a different run/job/sink than the selected pilot.
- Readback does not verify the expected resource.
- The operator cannot accept the sink-specific rollback/remediation limits.

## Remediation Notes

- Google Contacts and Odoo/Odollo may not support a perfect automatic rollback for all create/update paths.
- Prefer first live pilots against disposable or clearly marked test contacts.
- If readback fails after a write, preserve all artifacts and inspect the sink manually before retrying.
- Do not run a second write pilot until the first pilot report is complete or explicitly abandoned.
- Use `.venv/bin/bcw sinks abandon-live-pilot <job-id> --run-id <run-id> --operator <operator> --reason <reason> --json` before replacing an active selected target.

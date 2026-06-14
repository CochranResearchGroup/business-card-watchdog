# Live Pilot Checklists

These checklists are for explicit operator-approved live smoke work. Do not run them from generic CI, safe agent-loop continuation, or broad batch automation.

Use only non-sensitive test card data for first pilots.

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
.venv/bin/bcw sinks live-selection-packet \
  <job-id> \
  --run-id <run-id> \
  --sink google_contacts \
  --operator <operator> \
  --scope lookup
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

Use `--sink odoo` when the read-only smoke target is Odollo/Odoo. The packet must show `existing_selected_target.can_select_replacement_now = true` before selecting a replacement; if it shows `replacement_requires_abandonment = true`, run `abandon-live-pilot` for the old target first and then prepare a new packet.
Add `--json` to review commands when you need to archive the full structured artifact.

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
.venv/bin/bcw sinks live-selection-packet \
  <job-id> \
  --run-id <run-id> \
  --sink google_contacts \
  --operator <operator> \
  --scope all
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

If a lookup-only selected target already exists, record `abandon-live-pilot` with the reason for replacement before selecting the broader `all` scope target. Do not hand-edit selected-target artifacts.
Add `--json` to review commands when you need to archive the full structured artifact.

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
.venv/bin/bcw sinks apply-pilot-report <job-id> --run-id <run-id> --json
.venv/bin/bcw sinks live-pilot-closeout <job-id> --run-id <run-id> --no-write
```

Use `--sink odoo` for an Odollo/Odoo readback pilot.
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

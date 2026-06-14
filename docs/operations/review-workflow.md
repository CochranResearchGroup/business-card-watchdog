# Review Workflow Operations

This runbook covers the operator path for reviewing imported business cards without relying on raw JSON output. Add `--json` to the same commands when feeding another tool or script.

For representative command output, see `docs/operations/review-workflow-sample-output.md`.

## 1. Start Or Inspect Intake

Run a dry batch from a folder:

```bash
.venv/bin/bcw process "/mnt/e/SyncThing/Phone Camera" --dry-run
```

Or poll the configured watch inputs once:

```bash
.venv/bin/bcw watch --once
```

Check service and watcher state:

```bash
.venv/bin/bcw status --json
.venv/bin/bcw watch-status --json
```

## 2. Find The Run And Jobs

List recent runs:

```bash
.venv/bin/bcw runs list
```

Inspect a run summary and phase report:

```bash
.venv/bin/bcw runs summary <run-id>
.venv/bin/bcw runs phase-report <run-id>
```

List and inspect jobs:

```bash
.venv/bin/bcw jobs list --run-id <run-id>
.venv/bin/bcw jobs show <job-id> --run-id <run-id>
```

## 3. Inspect The Review Queue

Show pending review work:

```bash
.venv/bin/bcw reviews list --run-id <run-id>
```

Filter by next action or artifact kind:

```bash
.venv/bin/bcw reviews list --run-id <run-id> --next-action review_contact
.venv/bin/bcw reviews list --run-id <run-id> --artifact-kind contact_spec
```

Create review artifacts for local inspection:

```bash
.venv/bin/bcw reviews bundle --run-id <run-id> --json
.venv/bin/bcw reviews html --run-id <run-id> --json
.venv/bin/bcw reviews workbook --run-id <run-id> --json
```

## 4. Preview Review Workbook Decisions

Edit the generated review workbook CSV, then preview the import before applying it:

```bash
.venv/bin/bcw reviews preview-validation \
  --run-id <run-id> \
  --decisions-csv-file <edited-review-workbook.csv>
```

Persist preview artifacts only when durable review evidence is useful:

```bash
.venv/bin/bcw reviews preview-validation \
  --run-id <run-id> \
  --decisions-csv-file <edited-review-workbook.csv> \
  --write-artifacts \
  --json
```

Apply decisions after the preview is clean:

```bash
.venv/bin/bcw reviews apply-decisions \
  --run-id <run-id> \
  --decisions-csv-file <edited-review-workbook.csv> \
  --json
```

## 5. Enrichment And Duplicate Guardrails

Public-web enrichment is explicit. Paid API enrichment requires explicit approval:

```bash
.venv/bin/bcw enrichment check --json
.venv/bin/bcw enrichment request <job-id> --run-id <run-id> --mode public_web --json
.venv/bin/bcw enrichment request <job-id> --run-id <run-id> --mode api --allow-paid-enrichment --json
```

Duplicate checks and routing artifacts remain operator-visible:

```bash
.venv/bin/bcw sinks assess-duplicates <job-id> --run-id <run-id> --json
.venv/bin/bcw sinks lookup-plan <job-id> --run-id <run-id> --json
.venv/bin/bcw sinks plan <job-id> --run-id <run-id> --json
```

## 6. Sink Apply Pilot Gates

Live sink writes and readbacks remain explicit. Check readiness first:

```bash
.venv/bin/bcw sinks check --json
.venv/bin/bcw sinks apply-preflight <job-id> --run-id <run-id> --json
.venv/bin/bcw sinks apply-pilot-readiness <job-id> --run-id <run-id> --sink google_contacts --json
.venv/bin/bcw sinks apply-pilot-bundle <job-id> --run-id <run-id> --sink google_contacts --operator <operator> --json
```

Run simulated pilots before live operations:

```bash
.venv/bin/bcw sinks write-pilot <job-id> --run-id <run-id> --sink google_contacts --approved-by <operator> --simulate
.venv/bin/bcw sinks readback-pilot <job-id> --run-id <run-id> --sink google_contacts --approved-by <operator> --simulate
.venv/bin/bcw sinks apply-pilot-report <job-id> --run-id <run-id> --json
```

Live write/readback commands should only be used after the readiness and approval artifacts show the intended target and sink policy.

## 7. Safe Loop Progression

Use safe deterministic continuation for zero-write phases:

```bash
.venv/bin/bcw actions run-next --run-id <run-id>
```

If no safe action is available, inspect the phase report and review queue:

```bash
.venv/bin/bcw runs phase-report <run-id>
.venv/bin/bcw reviews list --run-id <run-id> --state all
```

# Review Workflow Sample Output

This companion note shows representative output from the synthetic one-card review fixture used in the CLI regression tests. IDs and timestamps are examples; real runs use the local runtime ledger.

## Run Discovery

```text
$ .venv/bin/bcw runs list
Runs: 1
 - run-001 state=waiting_for_review jobs=1 updated=2026-06-14T00:00:00+00:00
```

```text
$ .venv/bin/bcw runs show run-001
Run: run-001
State: waiting_for_review
Jobs: 1
Loaded jobs: 1
Artifacts: 1
Run dir: /home/operator/.local/share/business-card-watchdog/runs/run-001
```

```text
$ .venv/bin/bcw runs summary run-001
Run: run-001
State: waiting_for_review
Jobs: 1
Needs review: 1
Ready to route: 0
Failed: 0
Enrichment: public_web_requests=0 paid_provider_requests=0 paid_api_calls_attempted=0
Sink pilots: write=0 readback=0 reports=0 complete_reports=0
Review workbook preview: has_preview=False latest_valid=None errors=0 warnings=0
```

## Phase Report

```text
$ .venv/bin/bcw runs phase-report run-001
Run: run-001
State: waiting_for_review
Jobs: 1
Status: 1 blocked phases; 0 explicit-required phases; review workbook preview not_started
Review workbook preview: not_started
Blocked phases: review=1
Explicit-required phases: none
Pending phases: ingest=1, normalize=1, dedupe=1, route=1, sink_lookup=1, apply_approval=1
Complete phases: none
```

The exact pending/complete phase counts depend on which artifacts already exist. The status line and blocked/explicit groups are the main operator cues.

## Job And Review Queue

```text
$ .venv/bin/bcw jobs list --run-id run-001
Jobs: 1
 - job-001 run=run-001 state=needs_review image=/tmp/cards/card-001.png
```

```text
$ .venv/bin/bcw jobs show job-001 --run-id run-001
Job: job-001
Run: run-001
State: needs_review
Image: /tmp/cards/card-001.png
Artifacts: contact_spec
```

```text
$ .venv/bin/bcw reviews list --run-id run-001
Review queue: 1 jobs
 - job-001 state=needs_review next=review_contact artifacts=contact_spec
```

```text
$ .venv/bin/bcw reviews list --run-id run-001 --next-action plan_sinks
Review queue: 0 jobs
```

## Review Workbook Preview

Validation-only output is CSV so an operator can paste it back into a workbook:

```text
$ .venv/bin/bcw reviews preview-validation --run-id run-001 --decisions-csv-file edited-review-workbook.csv
row_number,status,run_id,job_id,action,errors,warnings
2,ready,run-001,job-001,approve_for_routing,,
```

Persisted preview mode returns JSON with artifact paths:

```json
{
  "schema": "business-card-watchdog.review-workbook-preview.v1",
  "run_id": "run-001",
  "row_count": 1,
  "ready_count": 1,
  "error_count": 0,
  "writes_attempted": 0,
  "network_calls_made": 0,
  "preview_path": ".../runs/run-001/review_workbook_preview.json",
  "validation_csv_path": ".../runs/run-001/review_workbook_preview_validation.csv"
}
```

## Safe Continuation Stop

When only explicit review, enrichment, duplicate, or sink approval work remains, safe continuation reports skipped actions instead of forcing progress:

```text
$ .venv/bin/bcw actions run-next --run-id run-001
{'run_id': 'run-001', 'limit': 10, 'executed': [], 'skipped': [...], 'executed_count': 0, 'skipped_count': 1, ...}
```

Use `--json` for this command when exact skipped action details are needed by an operator tool.

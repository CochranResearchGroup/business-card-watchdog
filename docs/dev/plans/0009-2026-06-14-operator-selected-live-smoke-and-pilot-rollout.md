# Plan 0009 | Operator-Selected Live Smoke And Pilot Rollout

State: READY_FOR_OPERATOR_SELECTION
Product authority: `PRODUCT_SPEC.md`
Predecessors:

- `docs/dev/plans/0004-2026-06-13-review-normalization-enrichment-dedupe-sinks.md`
- `docs/dev/plans/0007-2026-06-14-live-pilot-readiness-and-evidence.md`
- `docs/dev/plans/0008-2026-06-14-runtime-installation-and-pilot-operations.md`

## Scope

Move from offline/simulated control-plane proof to a deliberately selected production smoke path.

This plan is not a broad batch live-write rollout. It covers one explicit run, one explicit job, one explicit sink, and one explicit operator approval at a time.

## Stop Rule

Generic `/goal` continuation may inspect readiness and prepare artifacts, but it must stop before:

- scanning or processing private SyncThing images
- public-web search
- paid API enrichment
- live GWS/Odollo/Odoo lookup
- live write pilot
- live readback pilot
- duplicate merge decisions
- route/apply approvals

## Required Operator Selection

Before any live call, the operator must provide or create all of:

- `run_id`
- `job_id`
- `sink` as `google_contacts` or `odoo`
- operator name
- approval scope: `lookup`, `write`, `readback`, or `all`
- confirmation that the selected card/contact is safe for the target tenant/profile

The durable approval artifact is `selected_live_target.json`, created by:

```bash
bcw sinks select-live-target <job-id> --run-id <run-id> --sink <sink> --operator <operator> --scope lookup
```

## Execution Slices

1. `0009-A | Live Readiness Audit`: run `bcw runtime-readiness`, `bcw service recovery`, `bcw runs pilot-readiness`, and selected sink lookup readiness for the provided target. No live calls.
2. `0009-B | Read-Only Lookup Smoke`: after selected-target approval, run one live lookup smoke and import redacted downstream duplicate evidence.
3. `0009-C | Duplicate/Route Review`: inspect downstream duplicate evidence, resolve duplicates if needed, and confirm route/apply eligibility.
4. `0009-D | One-Job Write Pilot`: after selected-target approval with write scope, run one write pilot only for the selected sink.
5. `0009-E | One-Job Readback Pilot`: after selected-target approval with readback scope, verify the written/updated downstream resource.
6. `0009-F | Pilot Closeout`: write a pilot report with artifact links, write/readback evidence, stop conditions encountered, and rollback/remediation notes.

## `/goal` Execution Model

Suggested main `/goal` prompt:

```text
Execute Plan 0009 only after I provide an explicit run_id, job_id, sink, operator, and approval scope. Until then, inspect readiness and prepare documentation only. Never run live lookup, live write, live readback, public-web search, paid enrichment, or private SyncThing processing from generic continuation.
```

Recommended subagent split:

- Runtime readiness subagent: verify config, service recovery, watched-folder status, and selected run/job availability.
- Sink readiness subagent: inspect Google Contacts or Odollo/Odoo local readiness for the selected sink without making live calls.
- Review/dedupe subagent: inspect review, route, duplicate, and downstream lookup artifacts for the selected job.
- Pilot evidence subagent: after explicit live execution, assemble closeout evidence and redaction/readback checks.

## Acceptance Criteria

- No live call occurs without matching `selected_live_target.json`.
- Lookup smoke results are redacted before persistence.
- Strong downstream duplicates block write pilots until reviewed or resolved.
- Write and readback remain one job and one sink.
- GWS/Odollo/Odoo credentials, tenant state, live payload bodies, and private card data stay out of the repo.
- Each executed slice ends with tests or explicit operational readback, `gitleaks`, `git diff --check`, commit, push, and CI watch when code/docs change.

## Current State

Ready for operator target selection. No live target has been selected in this plan.

# Child Replacement Sample Output

This page documents the synthetic operator sample produced by
`drills child-replacement-readiness`. The sample is for review, training, and
agent-loop handoff inspection only. It does not approve or execute live sink
work.

## Generate The Sample

```bash
.venv/bin/bcw drills child-replacement-readiness --json
```

The response includes:

- `sample_outputs.child_replacement_readiness_markdown_path`
- `sample_outputs.review_bundle_path`
- `sample_outputs.review_html_path`
- `sample_outputs.review_workbook_path`
- `operator_dashboard_child_replacement_summary`
- `review_bundle_child_replacement_groups`
- `readiness_states`
- `closeout_rollup`

The markdown artifact is written under the synthetic run directory as
`child_replacement_readiness_sample_output.md` and is also recorded in the run
ledger as artifact kind `child_replacement_readiness_sample_output`.

## Expected Readiness States

For a passing fixture drill, the sample output should show:

- Blocked replacement audit: `blocked`
- Blocked replacement validation: `blocked`
- Replacement handoff: `ready_for_replacement_handoff`
- Replacement response: `ready_for_no_live_replacement_checklist`
- Replacement checklist: `ready_for_replacement_operator_review`
- Blocked replacement copy packet: `blocked`
- Ready replacement copy packet: `ready_for_replacement_operator_copy`
- Closeout: `ready_for_operator_closeout`

The closeout rollup should show stale predecessor artifacts and no executable
live command. The review bundle and operator dashboard should both count one
`ready_for_operator_closeout` replacement.

## Redaction Expectations

The sample output may retain synthetic run, job, candidate, sink, operator, and
state values. It must not store raw operator response, acknowledgement, or
safety confirmation text.

## Operator Boundary

The fixture command-copy text is offline operator copy text. It is not a live
sink command and is not permission to create or replace a real contact. Before
any non-simulated Google Contacts, Odoo, or Odollo operation, use authenticated
readiness plus live or sandbox write/readback checks for one explicit `run_id`,
`job_id`, `candidate_id`, `sink`, `operator`, and scope.

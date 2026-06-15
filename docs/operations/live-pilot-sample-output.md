# Live Pilot Sample Output

This page documents the synthetic operator sample produced by
`drills live-pilot-rehearsal`. The sample is for training, review, and agent-loop
handoff inspection only. It does not approve or execute live sink work.

## Generate The Sample

```bash
.venv/bin/bcw drills live-pilot-rehearsal --json
```

The response includes:

- `sample_outputs.live_pilot_rehearsal_markdown_path`
- `packets.selection_packet`
- `packets.validation`
- `packets.selected_target_handoff`
- `packets.lookup_handoff`
- `packets.workflow_packet`
- `packets.rehearsal`
- `packets.readiness_export`
- `packets.execution_checklist`
- `packets.command_copy_packet`

The markdown artifact is written under the synthetic run directory as
`live_pilot_rehearsal_sample_output.md` and is also recorded in the run ledger
as artifact kind `live_pilot_rehearsal_sample_output`.

## Expected Packet States

For a passing fixture drill, the sample output should show:

- Selection packet: `ready_for_operator_approval`
- Operator response validation: `ready_to_select_live_target`
- Selected target: `created`
- Lookup handoff: `ready_for_live_lookup_request`
- Workflow packet: `workflow_blocked`
- Operator rehearsal: `ready_for_explicit_operator_step`
- Readiness export written: `True`
- Execution checklist: `ready_for_explicit_operator_command`
- Command copy packet: `ready_for_operator_copy`

The workflow packet is expected to remain blocked in the fixture because the
sample stops before executing the explicit live lookup command.

The sample also reports `writes_attempted=0`, `network_calls_made=0`, and
`live_sink_calls_made=False`.

## Redaction Expectations

The sample output may retain non-secret routing fields:

- `run_id`
- `job_id`
- `sink`
- `operator`
- `scope`

It must not store the raw operator response, acknowledgement, or safety
confirmation text. Regenerate the readiness export and command-copy packet after
any target, lookup, duplicate, write, or readback evidence changes.

## Operator Boundary

The fixture command-copy text proves that the command-copy gate can be reached.
It is not permission to run a live command. Before any non-simulated
Google Contacts, Odoo, or Odollo operation, use the live-pilot checklist in
`docs/operations/live-pilot-checklists.md` with one explicit `run_id`, `job_id`,
`sink`, `operator`, and scope.

# Operator-Selected Live Smoke Preflight Sample Output

This page documents the synthetic operator sample produced by
`drills live-pilot-rehearsal` for the `operator-selected-live-smoke-preflight`
surface. The sample is for training, review, and agent-loop handoff inspection
only. It does not approve or execute live sink work.

## Generate The Sample

```bash
.venv/bin/bcw drills live-pilot-rehearsal --json
```

The response includes:

- `sample_outputs.operator_selected_live_smoke_preflight_markdown_path`
- `packets.operator_selected_preflight`
- `packets.selection_packet`
- `packets.validation`
- `packets.readiness_export`
- `packets.execution_checklist`
- `packets.command_copy_packet`

The markdown artifact is written under the synthetic run directory as
`operator_selected_live_smoke_preflight_sample_output.md` and is also recorded
in the run ledger as artifact kind
`operator_selected_live_smoke_preflight_sample_output`.

## Expected Packet State

For a passing fixture drill, the preflight sample should show:

- Preflight: `awaiting_operator_selection` when runtime config is ready, or
  `awaiting_run_selection` when a fixture/temp config intentionally lacks
  user-scope readiness.
- Ready entry count: `1`
- Active selected target count: `0`
- Preflight written: `True`
- Writes attempted: `0`
- Network calls made: `0`

The sample is captured before the synthetic `selected_live_target.json` is
created. Later packets in the same drill prove the selected-target, readiness
export, checklist, and command-copy gates without running a live sink command.

## Operator Boundary

The preflight sample shows what an operator or agent loop should inspect before
selecting a real live-smoke target. It is not permission to process private
SyncThing images, run public-web enrichment, call paid enrichment, run live
lookup/write/readback, or write Google Contacts, Odoo, or Odollo records.

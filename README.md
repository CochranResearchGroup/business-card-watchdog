# Business Card Watchdog

Business Card Watchdog is an installable, user-scoped service for processing large batches of business card images from watched folders, including SyncThing phone-camera directories.

The design builds on the local `business-card-to-contact` skill:

- OCR and normalize each card into reviewed contact JSON.
- Generate candidate contact photos.
- Route processed card data and image artifacts to Google Contacts and/or Odoo/Odollo tenants.
- Use deterministic App Intelligence style orchestration for large batches: host-owned state, ledgers, approvals, replay logs, and explicit sink policies.
- Expose CLI, API, MCP, and watched-folder surfaces from one shared core.

## Install

From this repo, use `uv`:

```bash
uv venv .venv
uv pip install --python .venv/bin/python -e ".[api,watch,vision,dev]"
```

Run commands through the venv:

```bash
.venv/bin/bcw status --json
```

For deterministic rectangle/contour hints in the image prefilter, include the vision extra:

```bash
uv pip install --python .venv/bin/python -e ".[vision]"
```

## User Config

Config lives under the user scope:

```text
~/.config/business-card-watchdog/config.toml
~/.local/share/business-card-watchdog/
~/.cache/business-card-watchdog/
```

Create an editable starter config:

```bash
.venv/bin/bcw init-config
```

The SyncThing source can be configured as a normal path or an alias such as:

```toml
[paths]
sync_phone = "/mnt/e/SyncThing/Phone Camera"

[watch]
inputs = ["$fsr:sync_phone"]
```

## First Commands

Inspect local readiness and safe next commands:

```bash
.venv/bin/bcw status
.venv/bin/bcw operator-dashboard
```

The operator dashboard includes matching CLI commands, API routes, and MCP tool argument templates for read-only continuation and live-pilot handoff inspection.

Dry-run a batch:

```bash
.venv/bin/bcw process "/mnt/e/SyncThing/Phone Camera" --dry-run
```

Start polling watch mode:

```bash
.venv/bin/bcw watch --once
```

Serve the API, if `fastapi` and `uvicorn` are installed:

```bash
.venv/bin/bcw api --host 127.0.0.1 --port 8787
```

Read-only API inspection surfaces include `GET /operator/dashboard` and `GET /actions/next`.

Print the MCP tool manifest:

```bash
.venv/bin/bcw mcp-manifest
```

Inspect runs, jobs, review queue, sinks, and watcher state:

```bash
.venv/bin/bcw runs list
.venv/bin/bcw runs summary <run-id>
.venv/bin/bcw runs phase-report <run-id>
.venv/bin/bcw operator-dashboard --run-id <run-id>
.venv/bin/bcw drills review-routing
.venv/bin/bcw sinks lookup-readiness <job-id> --run-id <run-id> --sink google_contacts --json
.venv/bin/bcw jobs list --run-id <run-id>
.venv/bin/bcw jobs show <job-id> --run-id <run-id>
.venv/bin/bcw reviews list --run-id <run-id>
.venv/bin/bcw actions next --run-id <run-id> --json
.venv/bin/bcw sinks check --json
.venv/bin/bcw watch-status --json
.venv/bin/bcw watch-backlog-preflight --json
.venv/bin/bcw watch-dry-run-selection-handoff --json
.venv/bin/bcw drills watch-dry-run-selection
```

Add `--json` to run, job, and review commands when consuming them from automation.

`drills multi-card-preclassification` creates a synthetic phone-photo-like image
with multiple card rectangles and proves the deterministic OpenCV prefilter records
candidate card boxes before OCR/App Intelligence. It uses only cache-local fixture
data and makes no private, enrichment, or sink calls.

`watch-backlog-preflight` inspects configured watch inputs without processing
files. It reports only aggregate backlog counts, redacted input references, a
recommended next action, and stop conditions. If backlog is present, use
`watch-dry-run-selection-handoff --json`, validate the returned operator
response template with `watch-dry-run-validate-response`, and request
`watch-dry-run-command-copy-packet` with the required acknowledgement. The packet
returns `watch --once --dry-run` as copyable text only after validation; it does
not execute the private-source dry run.

`drills watch-dry-run-selection` creates a synthetic watched source and rehearses
the preflight, handoff, response validation, and command-copy packet without
using configured watch inputs. It writes markdown sample output for operator
review and does not execute the copied command, run OCR/App Intelligence, or call
network/sink surfaces.

Ordinary dry-run batch processing also writes `card_candidates.json` beside a job's
`preclassification.json` when deterministic OpenCV boxes exist. Those records are
stable pre-OCR candidate boxes for later fanout; they are not contacts and cannot be
routed or enriched without OCR/App Intelligence verification. The same run also
writes `candidate_work_items.json` with one pending child OCR/App Intelligence work
item per candidate box so later agent loops can process large multi-card photos
without losing parent image lineage. When crops can be materialized, the run writes
`candidate_crops.json` and image files under the job artifact directory, then marks
those child work items `crop_ready` for later OCR/App Intelligence verification.
The run also writes `child_verification_requests.json` as a dry-run execution
contract for the crop-ready items; these requests are not executed and cannot route,
enrich, or write contacts. Synthetic/offline runs then write
`child_verification_results.json` and per-candidate fixture result files so the
review workflow can be built without production OCR/App Intelligence or sink calls.
Those child results are promoted into review-pending `child_contact_promotions.json`
records and normal contact-candidate files with parent/child lineage preserved.
Use `reviews children --run-id <run-id> --json` to inspect those promoted child
candidates before review, routing, enrichment, or sink work. Use
`reviews child-review <candidate-id> --run-id <run-id> --action approve_child_for_routing --json`
to approve a promoted child candidate into local reviewed-child-contact artifacts;
that approval still does not call enrichment, dedupe, routing, or live sinks.
After approval, `reviews child-route-prep-queue --run-id <run-id> --json` lists
child contacts ready for dry-run route preparation, and
`reviews child-route-prep <candidate-id> --run-id <run-id> --json` writes local
child lookup and sink plan artifacts with parent/child lineage. This prep still
does not run live lookup, resolve duplicates, enrich, or write sinks. Use
`reviews child-lookup-result <candidate-id> --run-id <run-id> --matches-by-sink-json '{}' --json`
to import supplied child lookup evidence, then
`reviews child-assess-duplicates <candidate-id> --run-id <run-id> --json` to
classify downstream duplicate state without live sink calls. Use
`reviews child-resolve-duplicate <candidate-id> --run-id <run-id> --decision create_new --json`
to record an explicit child duplicate decision, then
`reviews child-sink-plan-gate <candidate-id> --run-id <run-id> --json` to verify
whether the child sink plan is still blocked or cleared for future preflight.
Once clear, `reviews child-sink-apply-preflight <candidate-id> --run-id <run-id> --json`
previews child sink apply readiness, and
`reviews child-selected-target-handoff <candidate-id> --run-id <run-id> --sink google_contacts --json`
writes a no-live operator handoff packet without creating a selected target.
Use `reviews child-validate-selected-target-response <candidate-id> --run-id <run-id> --response <operator-response> --json`
to validate a copied child handoff response, then
`reviews child-selected-target-execution-checklist <candidate-id> --run-id <run-id> --response <operator-response> --json`
to create a no-live checklist that still blocks selected-target creation and
live sink execution. Use
`reviews child-selected-target-command-copy-packet <candidate-id> --run-id <run-id> --response <operator-response> --acknowledgement <operator-acknowledgement> --json`
to show the next offline command only after the acknowledgement names the run,
child candidate, sink, and operator. It never returns a live GWS/Odollo/Odoo
command. Use
`reviews child-selected-target-audit <candidate-id> --run-id <run-id> --json`
to preview the current child selected-target packet and whether a replacement
would require abandonment. The audit never creates, replaces, or abandons a
selected target. Use
`reviews child-abandon-selected-target <candidate-id> --run-id <run-id> --operator <operator> --reason <reason> --json`
to record a no-live child abandonment artifact, then
`reviews child-selected-target-replacement-reset <candidate-id> --run-id <run-id> --sink google_contacts --operator <operator> --json`
to verify that a replacement handoff preview is unblocked. Use
`reviews child-replacement-handoff-refresh <candidate-id> --run-id <run-id> --sink google_contacts --operator <operator> --json`
to refresh the no-live handoff and mark prior child selected-target response,
checklist, command-copy, and audit artifacts stale. Then use
`reviews child-validate-replacement-response <candidate-id> --run-id <run-id> --response <operator-response> --json`
to validate the replacement response only after the refresh packet and staleness
marker are ready. Then use
`reviews child-replacement-execution-checklist <candidate-id> --run-id <run-id> --response <operator-response> --json`
and
`reviews child-replacement-command-copy-packet <candidate-id> --run-id <run-id> --response <operator-response> --acknowledgement <operator-acknowledgement> --json`
to create replacement-specific no-live checklist and offline command-copy
packets. Use
`reviews child-replacement-closeout-status <candidate-id> --run-id <run-id> --json`
to summarize stale predecessor artifacts, refreshed replacement packet readiness,
and no-live counters in one local rollup artifact. Review bundles, review HTML,
review workbook CSVs, and `operator-dashboard` expose that closeout state so
agent loops do not need to know the child artifact path.

`drills review-routing` creates a synthetic fixture run and proves review approval,
review bundle/workbook export, duplicate lookup planning, dry-run sink routing, and
apply preflight without configured watch inputs, private images, enrichment calls, or
live sink operations.

`drills live-pilot-rehearsal` builds on that synthetic fixture and rehearses the
operator-selected live-pilot gate through preflight, selected target creation,
selected-target audit, lookup handoff, redacted readiness export, execution
checklist, and command copy packet. It writes preflight and rehearsal markdown
sample outputs, but does not execute the copied command or call live sinks.

`drills child-replacement-readiness` creates a synthetic child replacement run and
exports review bundle, review HTML, review workbook, and operator dashboard sample
outputs. It proves the blocked audit/validation states before refresh and the
ready handoff, response, checklist, command-copy, and closeout states after
replacement refresh. It uses fixture data only and does not call live sinks.

`drills watch-dry-run-selection` exports sample output for the configured-watch
dry-run approval workflow using only a synthetic watch source. It proves the
command-copy packet can be reached without touching private SyncThing inputs or
executing `watch --once --dry-run`.

`offline-pilot-gap-audit` inspects offline drill and documentation coverage and
reports the remaining live/operator-only boundaries without running private
source processing, enrichment, or live sink calls.

## Operator-Selected Live Pilots

Live lookup, write, and readback are not part of generic continuation or broad batch automation. Use one explicit `run_id`, `job_id`, `sink`, `operator`, and scope at a time, starting with non-sensitive test card data.

Review the selected target gates before any non-simulated sink call:

```bash
.venv/bin/bcw operator-selected-live-smoke-preflight --run-id <run-id> --sink google_contacts --no-write
.venv/bin/bcw live-selection-requirements --run-id <run-id> --sink google_contacts --no-write
.venv/bin/bcw sinks live-selection-packet <job-id> --run-id <run-id> --sink google_contacts --operator <operator> --scope lookup
.venv/bin/bcw runs live-pilot-handoff <run-id> --no-write
# Run the packet's printed "Validate prefilled response:" command first, then replace
# safety_confirmation=<tenant-profile-account-confirmation> with the operator's tenant/profile confirmation.
.venv/bin/bcw runs live-pilot-validate-response <run-id> --response "run_id=<run-id> job_id=<job-id> sink=google_contacts operator=<operator> scope=lookup safety_confirmation=<operator confirms intended tenant/profile>"
.venv/bin/bcw sinks select-live-target <job-id> --run-id <run-id> --sink google_contacts --operator <operator> --scope lookup --safety-confirmation "<operator confirms intended tenant/profile>" --json
.venv/bin/bcw sinks selected-target-audit <job-id> --run-id <run-id> --scope lookup --no-write
.venv/bin/bcw runs live-pilot-status <run-id> --no-write
```

Use `--sink odoo` for Odollo/Odoo targets. Start with `operator-selected-live-smoke-preflight` for a composed no-live view of the offline gap audit, live readiness audit, selection requirements, required operator fields, and stop conditions. Use `live-selection-requirements` when you need the exact candidate-specific packet and approval commands. Use the selection packet's `Validate prefilled response:` command for the first read-only check, then validate the filled response after replacing the confirmation placeholder. Use `runs live-pilot-handoff --no-write` when an agent loop needs the current concrete operator response template; it does not create `selected_live_target.json`. Validation is read-only and only returns blockers or the exact select-target command. If the selection packet reports that replacement requires abandonment, run `sinks abandon-live-pilot` for the current target before selecting a replacement. Before any non-simulated lookup/write/readback command, run `runs live-pilot-readiness-export-from-response`, `runs live-pilot-execution-checklist-from-response`, and `runs live-pilot-command-copy-packet-from-response`; copy only the returned `command_copy_text` when the packet is `ready_for_operator_copy`. Use `docs/operations/live-pilot-checklists.md` for the full lookup, write, readback, and closeout procedure.
After a selected target already exists, validation no longer returns a second select-target command. It reports the active-target state and starts the ordered post-selection sequence at selected-target audit and lookup-smoke handoff.

Install a user-scope systemd unit file without enabling or starting it:

```bash
.venv/bin/bcw service install --json
systemctl --user daemon-reload
systemctl --user enable business-card-watchdog.service
systemctl --user start business-card-watchdog.service
```

Remove the generated unit file:

```bash
.venv/bin/bcw service uninstall --json
systemctl --user daemon-reload
```

The service commands write only under the user config directory, normally:

```text
~/.config/systemd/user/business-card-watchdog.service
```

## Current State

This is an initial scaffold. It has deterministic run ledgers, config loading, routing decisions, CLI/API/MCP surfaces, and a subprocess adapter for the existing `business-card-to-contact` skill. `bcw status` reports safe next commands, stop conditions, and zero write/network counters. External writes are intentionally explicit and dry-run first.

Operational details live in:

- `docs/operations/user-scope-install-and-service.md`
- `docs/operations/review-workflow.md`
- `docs/operations/review-workflow-sample-output.md`
- `docs/operations/public-upstream-validation.md`
- `docs/operations/live-pilot-checklists.md`
- `docs/operations/operator-selected-live-smoke-preflight-sample-output.md`
- `docs/operations/live-pilot-sample-output.md`
- `docs/operations/child-replacement-sample-output.md`
- `docs/operations/release-readiness.md`

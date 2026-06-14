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
sync_phone = "/mnt/e/SyncThing/S22 Camera Phone Storage"

[watch]
inputs = ["$fsr:sync_phone"]
```

## First Commands

Dry-run a batch:

```bash
.venv/bin/bcw process "/mnt/e/SyncThing/S22 Camera Phone Storage" --dry-run
```

Start polling watch mode:

```bash
.venv/bin/bcw watch --once
```

Serve the API, if `fastapi` and `uvicorn` are installed:

```bash
.venv/bin/bcw api --host 127.0.0.1 --port 8787
```

Print the MCP tool manifest:

```bash
.venv/bin/bcw mcp-manifest
```

Inspect runs, jobs, review queue, sinks, and watcher state:

```bash
.venv/bin/bcw runs list
.venv/bin/bcw runs summary <run-id>
.venv/bin/bcw runs phase-report <run-id>
.venv/bin/bcw jobs list --run-id <run-id>
.venv/bin/bcw jobs show <job-id> --run-id <run-id>
.venv/bin/bcw reviews list --run-id <run-id>
.venv/bin/bcw sinks check --json
.venv/bin/bcw watch-status --json
```

Add `--json` to run, job, and review commands when consuming them from automation.

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

This is an initial scaffold. It has deterministic run ledgers, config loading, routing decisions, CLI/API/MCP surfaces, and a subprocess adapter for the existing `business-card-to-contact` skill. External writes are intentionally explicit and dry-run first.

Operational details live in:

- `docs/operations/user-scope-install-and-service.md`
- `docs/operations/review-workflow.md`
- `docs/operations/review-workflow-sample-output.md`

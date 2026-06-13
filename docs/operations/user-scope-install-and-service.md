# User-Scope Install And Service Operations

## Install

Recommended local development install:

```bash
uv venv .venv
uv pip install --python .venv/bin/python -e ".[api,vision,dev]"
```

Run commands through the venv:

```bash
.venv/bin/bcw status --json
```

Use `uv pip install --python .venv/bin/python ...` for dependency changes. Do not force packages into an externally managed host Python.

## Runtime Doctor

Run:

```bash
.venv/bin/bcw doctor --json
```

The doctor checks:

- config parent directory writability
- data/cache/runs/watch directory writability
- business-card skill readiness
- watched input readability

Watcher input failures make the doctor fail because unattended operation would not be reliable.

## User Service

Generate the user-scope systemd unit:

```bash
.venv/bin/bcw service install --json
systemctl --user daemon-reload
systemctl --user enable business-card-watchdog.service
systemctl --user start business-card-watchdog.service
```

Inspect:

```bash
.venv/bin/bcw service status --json
systemctl --user status business-card-watchdog.service
```

Remove the unit file:

```bash
.venv/bin/bcw service uninstall --json
systemctl --user daemon-reload
```

The product does not start or enable the service automatically. The operator remains responsible for the final `systemctl --user` action.

## Config Versioning And Migration

Current config schema is implicit TOML v1. Until migrations are implemented:

- preserve unknown config keys
- add new optional config keys with defaults in code
- avoid rewriting the config file except for `bcw init-config`
- document any breaking config change in `RUNBOOK.md` and this operations note

Future migration work should add an explicit `config_version` key and a `bcw config migrate` command.

## Release Checklist

Before release:

- `PYTHONPATH=src pytest -q`
- `.venv/bin/python -m pytest -q` after `uv pip install --python .venv/bin/python -e ".[api,vision,dev]"`
- `.venv/bin/bcw status --json`
- `.venv/bin/bcw doctor --json` with intended watch inputs reachable
- `.venv/bin/bcw mcp-manifest | python -m json.tool`
- dry-run process against synthetic or non-private fixture data
- confirm no private card images, OCR dumps, credentials, or generated runtime state are in git
- update `ROADMAP.md`, `RUNBOOK.md`, and relevant plan state

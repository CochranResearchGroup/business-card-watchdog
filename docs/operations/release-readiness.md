# Release Readiness

This runbook describes how to cut a public source release for Business Card Watchdog.

The current package version is read from `pyproject.toml`.

## Pre-Release Gates

Run from a clean worktree:

```bash
git status --short --branch
.venv/bin/python -m pytest -q
.venv/bin/ruff check .
uv build --out-dir dist
gitleaks detect --source . --no-banner --redact --exit-code 1
```

Confirm public CI is green for the target commit:

```bash
gh run list --repo CochranResearchGroup/business-card-watchdog --limit 5
```

Confirm branch protection is active:

```bash
gh api repos/CochranResearchGroup/business-card-watchdog/branches/main/protection \
  --jq '{strict:.required_status_checks.strict, contexts:.required_status_checks.contexts, allow_force_pushes:.allow_force_pushes.enabled, allow_deletions:.allow_deletions.enabled}'
```

Confirm there are no private artifacts in the release:

```bash
git ls-files | rg '(\.env|secret|credential|token|\.key|\.pem|\.p12|\.sqlite|\.db|\.jpg|\.jpeg|\.png|\.heic)' || true
```

## Tag

Create an annotated tag for the package version:

```bash
git tag -a v0.1.0 -m "business-card-watchdog v0.1.0"
git push upstream v0.1.0
```

## GitHub Release

Create a release after the tag is pushed:

```bash
gh release create v0.1.0 \
  --repo CochranResearchGroup/business-card-watchdog \
  --title "business-card-watchdog v0.1.0" \
  --notes-file /tmp/business-card-watchdog-v0.1.0-notes.md
```

The release notes should state that this is an initial public source release with offline/simulated control-plane support only. Do not claim live sink write production readiness.

## v0.1.0 Release Notes

Initial public source release.

Includes:

- watched-folder and batch-processing scaffold
- deterministic image preclassification
- review, normalization, enrichment request, dedupe, routing, and sink-pilot artifacts
- CLI/API/MCP control surfaces
- user-scoped config and service install helpers
- public CI with pytest, ruff, package build, and gitleaks
- branch protection and public collaboration templates

Safety boundaries:

- Paid enrichment remains explicitly requested and gated.
- Live Google Workspace/Odoo/Odollo writes remain explicit one-job pilot operations.
- Public CI uses fixtures and does not perform networked enrichment or live sink writes.

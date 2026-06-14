# Plan 0006 | Public Upstream Hardening And Production-Readiness Path

State: IN_PROGRESS
Product authority: `PRODUCT_SPEC.md`
Predecessors:

- `docs/dev/plans/0004-2026-06-13-review-normalization-enrichment-dedupe-sinks.md`
- `docs/dev/plans/0005-2026-06-13-review-routing-normalization-enrichment-dedupe.md`

Public upstream:

- `https://github.com/CochranResearchGroup/business-card-watchdog`

## Scope

Turn the newly published public repository into a safer collaboration and release base before live sink or paid-enrichment pilots.

This plan covers:

- public repository hygiene and CI gates
- branch-protection/ruleset readiness
- issue/PR templates for bounded agent/subagent work
- install-from-clean-clone checks with `uv`
- live-safe GWS/Odollo read-only smoke planning
- one-job live write/readback pilot planning after explicit operator approval
- packaging and release-readiness checks

## Non-Goals

- Do not run paid API enrichment from generic CI or safe agent-loop work.
- Do not run live Google Contacts or Odoo/Odollo writes from CI.
- Do not commit real card images, OCR dumps, connector credentials, tenant secrets, or live sink logs.
- Do not require local user-scoped runtime state for public CI.

## Current Baseline

Implemented before this plan:

- Public GitHub repository exists under `CochranResearchGroup/business-card-watchdog`.
- `main` tracks `upstream/main`.
- Pre-publication `gitleaks detect --source . --no-banner --redact --exit-code 1` scanned 91 commits and found no leaks.
- Concrete local default paths and fake fixture key wording were scrubbed before publication.
- Plan 0004 control-plane work is repo-complete for offline/simulated review, enrichment, dedupe, routing, sink-pilot, CLI/API/MCP, and operations-documentation surfaces.

Important gaps:

- No GitHub Actions workflow exists yet.
- No public CI gate runs pytest, lint, packaging, or leak scanning on push/PR.
- No GitHub branch protection/ruleset has been configured from this repo.
- No issue/PR templates exist for public or subagent work.
- Clean-clone installation has not been validated from the public upstream.
- Live read-only lookup and one-job write/readback pilots still need explicit selected targets and local auth.

## Execution Slices

### Slice 0006-A | Public CI And Leak Gate

Deliverables:

- Add GitHub Actions workflow for:
  - `uv` setup
  - Python 3.11 test environment
  - `pytest`
  - `ruff check`
  - package build
  - gitleaks secret scanning
- Keep CI offline: no paid enrichment, no GWS/Odollo live calls, no private data.
- Validate locally with the same practical commands where possible.
- Commit and push to `upstream/main`.

Acceptance:

- Workflow exists under `.github/workflows/`.
- Local pytest/ruff/build/leak checks pass or any unsupported local equivalent is documented.
- `git push` updates public `upstream/main`.

### Slice 0006-B | Public Collaboration Templates

Deliverables:

- Add issue templates for bug, feature, live-pilot request, and plan slice.
- Add PR template with validation, privacy, and live-call checkboxes.
- Add security disclosure guidance or a minimal `SECURITY.md`.

Acceptance:

- Templates avoid asking for secrets, private card images, or raw OCR dumps.
- PR checklist requires tests, leak-scan awareness, and explicit declaration of live calls.

### Slice 0006-C | Branch Protection / Ruleset Readiness

Deliverables:

- Inspect organization/repo permissions with `gh`.
- Configure or document a GitHub ruleset for `main` requiring CI and preventing force pushes if permissions allow.
- If direct configuration is blocked by permissions, add a repo-backed runbook with exact UI/CLI steps.

Acceptance:

- `main` protection/ruleset state is readable and either configured or documented with an explicit blocker.

### Slice 0006-D | Clean Clone And User-Scope Install Validation

Deliverables:

- Clone the public repo into a temporary directory.
- Use `uv` to create a clean environment and install the package with dev extras.
- Run tests and CLI smoke commands from the clean clone.
- Document the clean-clone install/readback commands.

Acceptance:

- Clean clone can run `bcw --help` and the offline test suite without user runtime credentials.

### Slice 0006-E | Live Read-Only Lookup Smoke Plan

Deliverables:

- Write an operations checklist for a selected non-sensitive test card/job.
- Include GWS and Odollo read-only lookup commands.
- Require readiness output and lookup-result artifact review before any write pilot.

Acceptance:

- The plan is explicit enough to run later without discovering commands from source.
- It does not perform writes.

### Slice 0006-F | One-Job Live Write/Readback Pilot Plan

Deliverables:

- Write the one-job live pilot checklist after read-only lookup.
- Require selected run ID, job ID, sink, reviewer, readiness, preflight, apply decision, write pilot, readback pilot, and apply-pilot report.
- Include rollback/remediation notes for sinks where true rollback is not available.

Acceptance:

- No live write is run by this slice.
- The future live write command is fully gated and one-job/one-sink scoped.

## Operating Rules

- Use `uv` for clean development environments and CI setup.
- Use fixture-backed tests for public CI.
- Run `gitleaks` before public pushes when changing fixtures, docs, workflows, or config defaults.
- Keep live sink and paid enrichment actions outside CI and safe generic agent-loop execution.

## Execution Log

### Slice 0006-A | 2026-06-14 | Public CI And Leak Gate

Implemented:

- Added `.github/workflows/ci.yml`.
- The workflow runs on push and pull requests to `main`.
- Test/lint/build job installs Python 3.11 with `uv`, installs `.[dev]`, runs `pytest`, runs `ruff check .`, and builds package artifacts with `uv build`.
- Secret-scan job checks out full history and runs `gitleaks/gitleaks-action`.
- CI remains offline with no paid enrichment, live GWS/Odollo calls, private card data, or user runtime dependency.

Validation:

- `.venv/bin/python -m pytest -q` passed with 179 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` built sdist and wheel artifacts.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` scanned 92 commits and found no leaks.

Remaining:

- Configure branch protection/rulesets after the first workflow run exists on GitHub.

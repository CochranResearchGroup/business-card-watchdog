# Plan 0006 | Public Upstream Hardening And Production-Readiness Path

State: COMPLETE_FOR_PUBLIC_RELEASE
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

Important remaining gap:

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

### Slice 0006-B | 2026-06-14 | Public Collaboration Templates

Implemented:

- Added bug, feature, live-pilot request, and plan-slice issue templates.
- Added a pull request template with validation, privacy, paid-enrichment, and live-write checks.
- Added `SECURITY.md` with public-safe reporting and data-handling guidance.
- Updated CI to opt JavaScript actions into Node 24 and disabled `setup-uv` cache because this repo has no lockfile yet.

Validation:

- `git diff --check` passed.
- `.venv/bin/ruff check .` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` scanned 95 commits and found no leaks.
- `rg -n 'private business-card images|raw OCR|API keys|Live pilot|Plan slice|FORCE_JAVASCRIPT_ACTIONS_TO_NODE24|enable-cache' .github SECURITY.md docs/dev/plans/0006-2026-06-14-public-upstream-hardening.md RUNBOOK.md` passed.

Remaining:

- Completed.

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

### Slice 0006-D | 2026-06-14 | Clean Public Clone Validation

Implemented:

- Added `docs/operations/public-upstream-validation.md`.
- Documented public clone, `uv` install, offline skill fixture seeding, CLI smoke, pytest, ruff, and build commands.
- Linked the validation runbook from README.

Validation:

- Cloned `https://github.com/CochranResearchGroup/business-card-watchdog.git` into `/tmp/bcw-public-clone.3OrD8L/business-card-watchdog`.
- `uv venv --python 3.11` installed CPython 3.11.15.
- `uv pip install --python .venv/bin/python -e '.[dev]'` installed the package and dev tools.
- `.venv/bin/bcw --help` returned successfully.
- `.venv/bin/python -m pytest -q` passed with 172 tests and 3 skipped optional-extra tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` built source and wheel distributions.

Remaining:

- Completed.

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

### Slices 0006-E/F | 2026-06-14 | Live Pilot Checklists

Implemented:

- Added `docs/operations/live-pilot-checklists.md`.
- Documented read-only lookup smoke prerequisites, commands, review requirements, and stop conditions.
- Documented one-job write/readback pilot prerequisites, commands, completion evidence, and remediation notes.
- Linked the checklist from README.

Validation:

- `git diff --check` passed.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` scanned 97 commits and found no leaks.
- `rg -n 'live-pilot-checklists|Read-Only Lookup Smoke|One-Job Write And Readback Pilot|Stop conditions|No live lookup or write was run|--no-simulate' README.md docs/operations/live-pilot-checklists.md docs/dev/plans/0006-2026-06-14-public-upstream-hardening.md RUNBOOK.md` passed.

Remaining:

- No live lookup or write was run. Actual execution requires an operator-selected non-sensitive run/job/sink and local sink auth.

### Slice 0006-G | 2026-06-14 | Release Readiness And v0.1.0 Tag

Implemented:

- Added `docs/operations/release-readiness.md`.
- Documented pre-release gates, branch-protection readback, private-artifact check, annotated tag command, GitHub release command, and v0.1.0 release notes.
- Linked the release-readiness runbook from README.
- Added public repository topics: `app-intelligence`, `business-cards`, `contacts`, `google-workspace`, `mcp`, `ocr`, and `odoo`.
- Published annotated tag and GitHub release `v0.1.0`.

Validation:

- `git diff --check` passed.
- `.venv/bin/python -m pytest -q` passed with 179 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` built source and wheel distributions.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` scanned 98 commits and found no leaks.
- `gh api repos/CochranResearchGroup/business-card-watchdog/branches/main/protection --jq '{strict:.required_status_checks.strict, contexts:.required_status_checks.contexts, allow_force_pushes:.allow_force_pushes.enabled, allow_deletions:.allow_deletions.enabled}'` confirmed strict checks, disabled force pushes, and disabled deletion.
- `git ls-files | rg '(\.env|secret|credential|token|\.key|\.pem|\.p12|\.sqlite|\.db|\.jpg|\.jpeg|\.png|\.heic)' || true` returned no tracked private-artifact paths.
- `rg -n 'release-readiness|v0.1.0|Initial public source release|Paid enrichment remains explicitly requested' README.md docs/operations/release-readiness.md docs/dev/plans/0006-2026-06-14-public-upstream-hardening.md RUNBOOK.md` passed.
- Latest pre-release CI run `27507317451` passed `Test, lint, and build` and `Secret scan`.
- `git ls-remote --tags upstream v0.1.0` returned `refs/tags/v0.1.0`.
- `gh release view v0.1.0 --repo CochranResearchGroup/business-card-watchdog --json tagName,name,url,isDraft,isPrerelease,publishedAt,targetCommitish` confirmed a published non-draft, non-prerelease release.
- `gh repo view CochranResearchGroup/business-card-watchdog --json repositoryTopics,description,visibility,url` confirmed the public repository topics.

Remaining:

- Future releases should follow `docs/operations/release-readiness.md`.

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
- Test/lint/build job seeds a minimal offline `business-card-to-contact` skill fixture under the CI runner home so status/doctor tests do not depend on private user-scoped runtime state.
- Secret-scan job checks out full history and runs the `zricethezav/gitleaks:v8.30.1` CLI container.
- CI remains offline with no paid enrichment, live GWS/Odollo calls, private card data, or user runtime dependency.

Validation:

- `.venv/bin/python -m pytest -q` passed with 179 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` built sdist and wheel artifacts.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` scanned 92 commits and found no leaks.
- First upstream workflow run failed because GitHub CI lacked the user-scoped skill root and `gitleaks/gitleaks-action@v2` requires an organization license.
- Second upstream workflow run passed for both required jobs: `Test, lint, and build` and `Secret scan`.

Remaining:

- Completed.

### Slice 0006-C | 2026-06-14 | Main Branch Protection

Implemented:

- Confirmed `main` initially had no branch protection and the repository had no rulesets.
- Configured branch protection for `main` with strict required status checks.
- Required checks are:
  - `Test, lint, and build`
  - `Secret scan`
- Disabled force pushes and branch deletion.
- Left admin enforcement disabled so repository administrators can still perform emergency maintenance.

Validation:

- `gh api repos/CochranResearchGroup/business-card-watchdog/branches/main/protection` returned the configured protection object.
- Required status check contexts resolve to the GitHub Actions app.

Remaining:

- Completed.

## Completion Audit

Plan 0006 public-release hardening is complete as of `e50eace`.

Evidence:

- Public repository exists at `https://github.com/CochranResearchGroup/business-card-watchdog`.
- Local `main` tracks `upstream/main`.
- Public CI exists and the latest head run `27507366888` passed `Test, lint, and build` and `Secret scan`.
- `main` branch protection requires strict `Test, lint, and build` plus `Secret scan`; force pushes and deletion are disabled.
- Public collaboration templates and `SECURITY.md` exist.
- Clean public clone validation passed with `uv`, pytest, ruff, CLI help, and package build.
- Live lookup/write pilot checklists exist and explicitly stop before unapproved writes.
- `v0.1.0` is tagged and published as a non-draft, non-prerelease GitHub release.

Remaining outside this public-release plan:

- Actual live lookup or write/readback pilot execution requires an operator-selected non-sensitive `run_id`, `job_id`, sink, reviewer, and local GWS/Odollo auth.
- Plan 0005 product hardening remains the next code/product plan.

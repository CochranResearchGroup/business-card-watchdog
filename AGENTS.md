# Business Card Watchdog

## Repo Context

This repo is an installable OCR and App Intelligence product for ingesting large batches of business card photos from watched folders, including SyncThing phone directories, and routing reviewed contact data to Google Contacts and/or Odoo/Odollo tenants.

The product must keep deterministic host control over batch orchestration. Agent/model output may suggest field fixes, routing, retries, or review actions, but the host-owned orchestrator owns state transitions, ledgers, approvals, replay logs, sink writes, and stop rules.

## Repo-Specific Guidance

- Keep user config under `~/.config/business-card-watchdog/`.
- Keep runtime state under `~/.local/share/business-card-watchdog/`.
- Keep cache and transient watcher state under `~/.cache/business-card-watchdog/`.
- Do not put tenant secrets, raw connector credentials, or private card images in git.
- Treat Google Contacts and Odoo/Odollo writes as explicit sink actions. Default new workflows to dry-run until readiness checks and routing policy are present.
- The base extraction workflow builds on the user-scoped `business-card-to-contact` skill, normally at `~/.codex/shared/skills/business-card-to-contact`.
- Mutations to the same contact/person should remain sequential even when OCR and review are batched.

## CodeGraph

This project is expected to use CodeGraph for structural code questions once initialized. If `.codegraph/` does not exist and a structural question or non-trivial code change needs it, ask whether to run `codegraph init -i`.

Prefer CodeGraph for symbol definitions, callers/callees, impact, traces, signatures, and focused architectural context. Use text search for literal strings, logs, comments, or after a specific file is already identified.

## Policy Loading Contract

- `AGENTS.md` is a routing surface, not a one-time pointer.
- Re-read the relevant policy files under `docs/dev/policies/` at the start of any non-trivial turn.
- Re-read the relevant policy files when task scope changes mid-session.
- When behavior is ambiguous, prefer re-reading policy over improvising from stale assumptions.

## Policy Re-read Triggers

- Re-read planning policy before opening, revising, or closing a substantive plan.
- Re-read runtime and tenant policy before changing config, watcher, routing, sink, or ledger behavior.
- Re-read validation and closeout policy before claiming work complete.

## Policy Entry

Read and follow:

- `docs/dev/policies/0001-policy-management.md`
- `docs/dev/policies/0002-product-and-runtime-governance.md`
- `docs/dev/policies/0003-planning-and-validation.md`

# Policy | Product And Runtime Governance

## Product Boundary

- Product code lives in this repo.
- User-scoped config lives under `~/.config/business-card-watchdog/`.
- User-scoped runtime data lives under `~/.local/share/business-card-watchdog/`.
- Cache and transient watcher state live under `~/.cache/business-card-watchdog/`.
- Tenant secrets, connector credentials, private card images, raw OCR dumps from real cards, and live sink logs do not belong in git.

## Runtime State

- Persist every batch as a run directory with a host-owned ledger.
- Keep replayable events in append-only JSONL where practical.
- Treat OCR/model/agent decisions as evidence, not control authority.
- The orchestrator owns phase, retry, branch, approval, sink, rollback, and stop rules.

## Tenant And Sink Isolation

- Treat Google Contacts, Odoo/Odollo, and any future CRM as separate sink adapters.
- Bind sink writes to an explicit runtime profile and readiness check before enabling live writes.
- Route contacts by deterministic rules from user config.
- Default new sink behavior to dry-run.
- Mutations to the same person/contact must stay sequential even when image processing is parallel.

## CodeGraph

- Use CodeGraph for structural source questions once initialized.
- If CodeGraph is unavailable or `.codegraph/` is missing, say so and fall back to direct source reads and targeted tests.


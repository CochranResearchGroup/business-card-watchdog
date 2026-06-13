# Policy | Policy Management

Adopted profile: custom composition from `repo-product-engineering` plus operations-platform modules.

The selector’s deterministic first pass saw an empty repo and recommended `standalone-library`; that was rejected because the user’s stated purpose requires installable product software plus watched-folder runtime operations, tenant routing, ledgers, and CLI/API/MCP surfaces.

## Policy

- Keep durable repo-local policy under `docs/dev/policies/`.
- Keep `AGENTS.md` as the entrypoint that wires repo-local policy into agent behavior.
- Re-read relevant policy files at the start of non-trivial work and when scope changes.
- Preserve local commands, runtime paths, credential boundaries, and sink-specific caveats in repo docs rather than hiding them in shared policy.
- Treat the installed policy library as source material. This repo’s policy files are the runtime authority.

## Installed Source Library

- Source: `/home/ecochran76/workspace.local/agent-policies/repo-policy-selector`
- Catalog checked: `policy-library/catalog.yaml`
- Profiles considered: `repo-product-engineering`, `operations-platform`, `standalone-library`
- Key modules adopted locally: policy management, codegraph usage, planning discipline, roadmap/runbook governance, runtime state governance, tenant isolation, architecture guardrails, validation and handoff.


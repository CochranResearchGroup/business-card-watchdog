# Security Policy

## Reporting

Do not open public issues that include secrets, private business-card images, raw OCR from real cards, OAuth tokens, API keys, tenant identifiers, or live sink response logs.

For sensitive reports, contact the repository maintainers through the Cochran Research Group organization owner channel or use a private GitHub security advisory if enabled for this repository.

## Data Handling

This repository should contain only source code, synthetic fixtures, documentation, and public-safe examples. Runtime state belongs in user-scoped directories, normally under:

- `~/.config/business-card-watchdog/`
- `~/.local/share/business-card-watchdog/`
- `~/.cache/business-card-watchdog/`

## Live Integrations

Paid enrichment providers and Google Workspace/Odoo/Odollo sink writes must be explicitly requested and scoped. Generic CI, safe agent loops, and public test fixtures must not perform paid API calls or live writes.

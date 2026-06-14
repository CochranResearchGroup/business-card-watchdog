## Summary

Describe the change and the plan/slice it belongs to.

## Validation

- [ ] Tests:
- [ ] `ruff check .` when Python code changed.
- [ ] `git diff --check`.
- [ ] `gitleaks detect --source . --no-banner --redact --exit-code 1` when docs, fixtures, workflows, or config defaults changed.

## Privacy And Safety

- [ ] No private business-card images, raw private OCR, credentials, tenant secrets, or live sink logs are committed.
- [ ] Paid enrichment was not run, or the exact approved request is documented.
- [ ] Live GWS/Odollo writes were not run, or the exact one-job pilot approval and readback evidence are documented.

## Operator Impact

Document any CLI/API/MCP behavior changes, config migrations, or service restart needs.

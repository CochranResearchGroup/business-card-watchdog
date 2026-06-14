---
name: Plan slice
about: Track a bounded implementation slice from a repo plan.
title: "Plan slice: "
labels: plan-slice
assignees: ""
---

## Plan Reference

- Plan:
- Slice:
- Product authority:

## Scope

Describe the bounded change. Include what is intentionally out of scope.

## Validation

- [ ] Focused tests:
- [ ] `git diff --check`
- [ ] `ruff check .` when Python code changes:
- [ ] `gitleaks detect` when fixtures, docs, workflows, or config defaults change:

## External Calls

- [ ] No paid enrichment calls.
- [ ] No live sink writes.
- [ ] Any read-only live lookup is explicitly approved and scoped.

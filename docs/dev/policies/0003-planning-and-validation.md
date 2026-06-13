# Policy | Planning And Validation

## Planning

- Use `ROADMAP.md` for durable priority and milestone state.
- Use `RUNBOOK.md` for dated execution history.
- Use `docs/dev/plans/` for bounded implementation plans.
- Plan filenames should use `NNNN-YYYY-MM-DD-plan-slug.md`.
- Plans should include scope, non-goals, acceptance criteria, and a deterministic state.

## Validation

- Run targeted tests for changed code before handoff.
- Record concrete validation evidence in `RUNBOOK.md` or the relevant plan when a slice closes.
- For runtime integrations, distinguish dry-run evidence from live write evidence.
- Do not claim Google/Odoo writes work until authenticated readiness and live or sandbox write/readback checks exist.

## Closeout

- Close work with files changed, validation run, remaining blockers, and the next bounded slice.
- Keep closeout concise and evidence-backed.


# Runbook

## Turn 1 | 2026-06-10

Bootstrapped the repo as a product/runtime platform rather than a simple library. Installed local policy docs, package skeleton, deterministic batch ledger, config paths, business-card skill adapter, routing stubs, CLI/API/MCP surfaces, and initial tests.

Validation:

- `PYTHONPATH=src pytest -q` passed with 5 tests.
- `PYTHONPATH=src python -m business_card_watchdog.cli status --json` confirmed the business-card skill adapter is ready.
- `PYTHONPATH=src python -m business_card_watchdog.cli mcp-manifest` rendered a 914-byte MCP manifest.

Remaining:

- Implement durable watcher state across restarts.
- Add live Google/Odoo sink readiness and write/readback checks before enabling non-dry-run routing.
- Initialize CodeGraph if desired for structural navigation after the first code scaffold.

## Turn 2 | 2026-06-11

Added `PRODUCT_SPEC.md` as the draft product authority before continuing implementation. The spec defines the problem, target users, goals/non-goals, core workflows, functional requirements, App Intelligence control rules, user-scoped config/runtime requirements, sink routing/idempotency requirements, security boundaries, and milestone acceptance criteria.

Validation:

- Documentation-only change; no code tests required.

## Turn 3 | 2026-06-11

Added `docs/dev/plans/0002-2026-06-11-high-level-implementation-goal-plan.md` as the high-level implementation plan adapted for `/goal` and subagent execution. The plan defines the `/goal` objective, operating contract, workstream/subagent briefs, critical path, parallel launch set, integration gates, reconciliation checklist, suggested turn sequence, and validation matrix.

Validation:

- Documentation-only change; no code tests required.

## Turn 4 | 2026-06-11

Started executing Plan 0002 under the active `/goal`. Kept WS1 local because core state is the critical-path contract, and delegated WS7 as a tests-only subagent sidecar.

Implemented:

- WS1: typed run/job/sink states, explicit invalid-transition rejection, run index writes, artifact registry JSONL, and orchestrator state transitions.
- WS7: privacy-safe synthetic fixtures, fake skill adapter, and dry-run end-to-end batch validation without real card data or external credentials.

Validation:

- `PYTHONPATH=src pytest -q` passed with 10 tests.
- CodeGraph was not initialized (`.codegraph/` missing), so this slice used direct source reads and targeted tests.

Remaining:

- WS2 watched-folder durable state and file-settle behavior.
- WS3 review/classification hardening.
- WS4 routing fingerprint/readiness/sink adapter work.
- WS5 expanded CLI/API/MCP service surfaces.
- WS6 user-scope service/install operations.

## Turn 5 | 2026-06-11

Continued Plan 0002 execution with the next critical integration slice: WS3 review classification and WS4 dry-run routing/sink primitives.

Implemented:

- WS3: deterministic contact-spec assessment, structured `review_packet.json` generation for incomplete specs, optional OCR/crop/contact-sheet artifact registration, and review-state tests.
- WS4: canonical contact fingerprinting, dry-run sink payload generation, readiness primitives that keep live Google/Odoo writes blocked until implemented, route decision fingerprints/matched-rule metadata, and sink tests.

Validation:

- `PYTHONPATH=src pytest -q` passed with 18 tests.
- `PYTHONPATH=src python -m business_card_watchdog.cli status --json` confirmed the business-card skill adapter is still ready.
- `PYTHONPATH=src python -m business_card_watchdog.cli mcp-manifest` rendered a 914-byte MCP manifest.

Remaining:

- WS2 watched-folder durable seen-file state and SyncThing file-settle behavior.
- WS3 richer field/crop correction schemas and review submission flow.
- WS4 live sink readiness/write/readback and same-contact write serialization.
- WS5 expanded CLI/API/MCP service surfaces.
- WS6 user-scope service/install operations.

## Turn 6 | 2026-06-11

Continued Plan 0002 execution with WS2 watcher hardening.

Implemented:

- Durable watcher state under `~/.local/share/business-card-watchdog/watch/`, including `seen-files.jsonl`, `pending-files.json`, and `status.json`.
- SyncThing-style file-settle behavior using size/mtime snapshots and configurable `watch.settle_seconds`.
- Restart-safe seen-file behavior so already processed files are not reprocessed unless watcher state is explicitly reset.
- `bcw watch-status` and guarded `bcw watch-reset --yes` commands.
- Main `bcw status --json` now includes watcher status readback.

Validation:

- `PYTHONPATH=src pytest -q` passed with 26 tests.
- `PYTHONPATH=src python -m business_card_watchdog.cli status --json` confirmed skill readiness and watcher status payload. The current user config still points at `$fsr:sync_phone` -> `E:\SyncThing\S22 Camera Phone Storage`, which is not present in this Linux path namespace, so watcher status reports that input as missing.

Remaining:

- WS2 service install/uninstall helpers.
- WS5 expanded CLI/API/MCP service surfaces.
- WS6 packaging and user-scope operations.
- Live sink gates remain intentionally blocked pending explicit readiness/write/readback implementations.

## Turn 7 | 2026-06-11

Completed Plan 0002 execution.

Implemented:

- WS5: shared `BusinessCardService`, expanded CLI run/job/review/sink/watch/service/doctor commands, expanded FastAPI endpoints, expanded MCP schemas, and `docs/dev/architecture/0002-mcp-server-plan.md`.
- WS6: API/dev dependency extras, user-scope systemd unit install/status/uninstall helpers, runtime doctor, config migration/versioning guidance, and release checklist documentation.
- Remaining review submission and same-contact serialization policy gaps from the Plan 0002 audit.

Validation:

- `PYTHONPATH=src pytest -q` passed with 39 tests and 1 skipped API-extra test.
- `.venv/bin/python -m pytest -q` passed with 40 tests after installing `.[api,dev]`.
- `.venv/bin/bcw doctor --json` passed with a temp config and writable temp runtime paths.
- `.venv/bin/bcw status --json` passed with the real user config and reported the expected missing Windows SyncThing path caveat.
- `.venv/bin/bcw service status --json` passed and showed the user-scope unit path.
- `.venv/bin/bcw mcp-manifest | python -m json.tool` passed and rendered a 5129-byte manifest.
- `.venv/bin/bcw --config <temp-config> process <empty-temp-source> --dry-run --workers 1` passed and created a completed dry-run run.

Follow-on:

- Opened `docs/dev/plans/0003-2026-06-11-follow-on-live-sinks-and-mcp-server.md` for live sink write/readback and MCP server transport work.

## Turn 8 | 2026-06-12

Added deterministic image preclassification before the business-card pipeline.

Implemented:

- `src/business_card_watchdog/preclassifier.py` with header-based image dimension reading, aspect-ratio scoring, and optional OpenCV rectangular contour hints when `cv2` is installed.
- `[prefilter]` config with `enabled`, `min_score`, and `process_uncertain`.
- Orchestrator wiring that records `preclassification.json` and `image_preclassified` events before adapter execution.
- Rejection path for `not_business_card` and, by default, `uncertain`, so those images do not hit the business-card/App Intelligence pipeline.
- Architecture note `docs/dev/architecture/0003-deterministic-image-prefilter.md`.

Validation:

- `PYTHONPATH=src pytest -q` passed with 43 tests and 1 skipped API-extra test.
- `.venv/bin/python -m pytest -q` passed with 44 tests.

## Turn 9 | 2026-06-13

Standardized local install/dependency workflow on `uv`.

Updated:

- README install commands now use `uv venv .venv` and `uv pip install --python .venv/bin/python -e ".[api,watch,vision,dev]"`.
- Operations docs now use uv for dependency management and installed-entrypoint validation.
- Prefilter architecture note now documents the uv command for the `vision` extra.

Validation:

- `uv pip install --python .venv/bin/python -e ".[api,watch,vision,dev]"` succeeded.
- `.venv/bin/python -m pytest -q` passed with 45 tests.
- `.venv/bin/bcw status --json` passed and still reports the expected missing Windows SyncThing path caveat in this Linux namespace.
- `.venv/bin/python` imported `cv2` 4.13.0 and `watchfiles` 1.2.0.

## Turn 10 | 2026-06-13

Implemented the SyncThing/OpenCV prefilter hardening slice.

Updated:

- Default config and real user config now point `$fsr:sync_phone` at `/mnt/e/SyncThing/S22 Camera Phone Storage`.
- Watcher status scans are bounded and non-recursive by default so `bcw status --json` does not walk an entire phone-camera tree.
- OpenCV rectangle analysis now records multiple card-like boxes and raises confidence for multi-card phone photos.
- Aspect ratio is weak evidence only; without rectangle evidence, 16:9 phone images are `uncertain`, not `likely_business_card`.
- CodeGraph was initialized for the repo; its local database remains ignored under `.codegraph/`.

Validation:

- `.venv/bin/python -m pytest tests/test_preclassifier.py tests/test_watcher.py -q` passed with 15 tests.
- `PYTHONPATH=src pytest tests/test_preclassifier.py tests/test_watcher.py -q` passed with 13 tests and 2 skipped OpenCV tests.
- `.venv/bin/bcw status --json` passed against the real user config and reported 5 top-level backlog images, no unsettled files, no truncation, and no last error.
- Real top-level SyncThing JPGs classified as `uncertain` with zero card-like contours instead of `likely_business_card`.

## Turn 11 | 2026-06-13

Opened the next high-level plan for review, normalization, enrichment, dedupe, and live sink routing.

Updated:

- Added `docs/dev/plans/0004-2026-06-13-review-normalization-enrichment-dedupe-sinks.md`.
- Updated `ROADMAP.md` to point at Plan 0004 as the current high-level implementation plan.
- Captured the policy that API-based enrichment has cost and must be explicitly requested.
- Captured Odollo-derived implementation sources for Apollo enrichment, public-web enrichment, Odoo readiness/lookup, contact points, and review action semantics.

Validation:

- Planning-only change; run `git diff --check` before commit.

## Turn 12 | 2026-06-13

Started executing Plan 0004.

Implemented:

- Contact candidate normalization contract and `contact_candidate.json` artifacts.
- Review approval now writes `reviewed_contact.json` with normalized operator corrections.
- Review packets include the contact candidate.
- Enrichment config/readiness with default-off behavior, public-web readiness, and paid API gating for Apollo-style providers using key names from `~/credentials/API-keys.env` without exposing values.
- CLI/MCP enrichment readiness surface.
- Local identity index and `duplicate_assessment.json` artifacts.
- Strong duplicate jobs move to `needs_review` before sink routing.

Validation:

- `.venv/bin/python -m pytest -q` passed with 57 tests.
- `PYTHONPATH=src pytest -q` passed with 54 tests and 3 skipped optional-extra tests.
- `.venv/bin/bcw enrichment check --json` passed and reported default no-op readiness.
- `.venv/bin/bcw enrichment check --mode api --json` reported blocked readiness because enrichment is disabled in the current user config.

Operational note:

- `git remote -v` returned no configured remotes, so the requested push cannot be completed until a remote is added.

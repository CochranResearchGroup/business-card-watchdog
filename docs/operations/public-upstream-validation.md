# Public Upstream Validation

This runbook validates that the public GitHub repository can be cloned, installed, tested, linted, and built without private workspace state.

Repository:

```text
https://github.com/CochranResearchGroup/business-card-watchdog.git
```

## Clean Clone Check

```bash
tmpdir="$(mktemp -d /tmp/bcw-public-clone.XXXXXX)"
git clone https://github.com/CochranResearchGroup/business-card-watchdog.git "$tmpdir/business-card-watchdog"
cd "$tmpdir/business-card-watchdog"

uv venv --python 3.11
uv pip install --python .venv/bin/python -e '.[dev,vision]'
```

The status and doctor tests expect the user-scoped `business-card-to-contact` skill to exist. For CI or clean validation hosts that do not have the real skill installed, seed a minimal offline fixture:

```bash
mkdir -p "$HOME/.codex/shared/skills/business-card-to-contact/scripts"
cat > "$HOME/.codex/shared/skills/business-card-to-contact/scripts/run_business_card_pipeline.py" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

_image_path = Path(sys.argv[1])
artifact_dir = Path(sys.argv[2])
artifact_dir.mkdir(parents=True, exist_ok=True)
(artifact_dir / "spec.json").write_text(
    json.dumps(
        {
            "full_name": "Clean Clone Fixture",
            "organization": "Example Organization",
            "email": "clean.clone@example.test",
        },
        sort_keys=True,
    )
    + "\n",
    encoding="utf-8",
)
(artifact_dir / "review.md").write_text("# Clean clone fixture review\n", encoding="utf-8")
PY
```

Run the validation:

```bash
.venv/bin/bcw --help
.venv/bin/python -m pytest -q
.venv/bin/ruff check .
uv build --out-dir dist
```

## 2026-06-14 Readback

Clean clone path:

```text
/tmp/bcw-public-clone.3OrD8L/business-card-watchdog
```

Validation:

- `uv venv --python 3.11` installed CPython 3.11.15.
- `uv pip install --python .venv/bin/python -e '.[dev,vision]'` installed the package, dev tools, and OpenCV vision analyzer.
- `.venv/bin/bcw --help` returned successfully.
- `.venv/bin/python -m pytest -q` should pass with the CI-equivalent dev and vision extras installed.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` built source and wheel distributions.

## 2026-06-15 Local Gate For Plan 0011

Validation:

- `.venv/bin/python -m pytest tests/test_preclassifier.py::test_preclassifier_detects_multiple_cards_in_large_photo tests/test_preclassifier.py::test_orchestrator_records_multi_card_candidate_manifest -q` passed with 2 tests.
- `.venv/bin/python -m pytest -q` passed with 239 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` built source and wheel distributions.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

## 2026-06-15 Local Gate For Plan 0012

Validation:

- `.venv/bin/python -m pytest tests/test_preclassifier.py::test_orchestrator_records_multi_card_candidate_manifest -q` passed with 1 test.
- `.venv/bin/python -m pytest -q` passed with 239 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` built source and wheel distributions.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

## 2026-06-15 Local Gate For Plan 0013

Validation:

- `.venv/bin/python -m pytest tests/test_preclassifier.py::test_orchestrator_records_multi_card_candidate_manifest -q` passed with 1 test.
- `.venv/bin/python -m pytest -q` passed with 239 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` built source and wheel distributions.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

## 2026-06-15 Local Gate For Plan 0014

Validation:

- `.venv/bin/python -m pytest tests/test_preclassifier.py::test_orchestrator_records_multi_card_candidate_manifest -q` passed with 1 test.
- `.venv/bin/python -m pytest -q` passed with 239 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` built source and wheel distributions.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

## 2026-06-15 Local Gate For Plan 0015

Validation:

- `.venv/bin/python -m pytest tests/test_preclassifier.py::test_orchestrator_records_multi_card_candidate_manifest -q` passed with 1 test.
- `.venv/bin/python -m pytest -q` passed with 239 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` built source and wheel distributions.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

## 2026-06-15 Local Gate For Plan 0016

Validation:

- `.venv/bin/python -m pytest tests/test_preclassifier.py::test_orchestrator_records_multi_card_candidate_manifest -q` passed with 1 test.
- `.venv/bin/python -m pytest -q` passed with 239 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` built source and wheel distributions.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

## 2026-06-15 Local Gate For Plan 0017

Validation:

- `.venv/bin/python -m pytest tests/test_review_surface.py::test_child_review_queue_lists_promoted_child_contact_candidates tests/test_cli_surfaces.py::test_cli_child_reviews_lists_promoted_child_candidates tests/test_api.py::test_api_child_reviews_lists_promoted_child_candidates tests/test_mcp.py::test_mcp_child_reviews_lists_promoted_child_candidates tests/test_mcp.py::test_manifest_has_process_tool -q` passed with 5 tests.
- `.venv/bin/python -m pytest -q` passed with 243 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` built source and wheel distributions.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

## 2026-06-15 Local Gate For Plan 0018

Validation:

- `.venv/bin/python -m pytest tests/test_review_surface.py::test_child_review_approval_writes_reviewed_child_contact_artifact tests/test_cli_surfaces.py::test_cli_child_review_approves_promoted_child_candidate tests/test_api.py::test_api_child_review_approves_promoted_child_candidate tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_child_review_approves_promoted_child_candidate -q` passed with 5 tests.
- `.venv/bin/python -m pytest -q` passed with 247 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` built source and wheel distributions.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

## 2026-06-15 Local Gate For Plan 0019

Validation:

- `.venv/bin/python -m pytest tests/test_review_surface.py::test_child_route_prep_writes_dry_run_lookup_and_sink_plans tests/test_cli_surfaces.py::test_cli_child_route_prep_writes_dry_run_plans tests/test_api.py::test_api_child_route_prep_writes_dry_run_plans tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_child_route_prep_writes_dry_run_plans -q` passed with 5 tests.
- `.venv/bin/python -m pytest -q` passed with 251 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` built source and wheel distributions.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

## 2026-06-15 Local Gate For Plan 0020

Validation:

- `.venv/bin/python -m pytest tests/test_review_surface.py::test_child_lookup_result_and_duplicate_assessment_use_fixture_matches tests/test_cli_surfaces.py::test_cli_child_lookup_result_and_duplicate_assessment tests/test_api.py::test_api_child_lookup_result_and_duplicate_assessment tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_child_lookup_result_and_duplicate_assessment -q` passed with 5 tests.
- `.venv/bin/python -m pytest -q` passed with 255 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` built source and wheel distributions.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

## 2026-06-15 Local Gate For Plan 0021

Validation:

- `.venv/bin/python -m pytest tests/test_review_surface.py::test_child_duplicate_resolution_clears_sink_plan_gate tests/test_cli_surfaces.py::test_cli_child_duplicate_resolution_clears_gate tests/test_api.py::test_api_child_duplicate_resolution_clears_gate tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_child_duplicate_resolution_clears_gate -q` passed with 5 tests.
- `.venv/bin/python -m pytest -q` passed with 259 tests.
- `.venv/bin/ruff check .` passed.
- `uv build --out-dir dist` built source and wheel distributions.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `git diff --check` passed.
- `codegraph sync && codegraph status` passed; index is up to date.

## 2026-06-15 Local Gate For Plan 0022

Validation:

- `.venv/bin/python -m pytest tests/test_review_surface.py::test_child_sink_apply_preflight_and_selected_target_handoff tests/test_cli_surfaces.py::test_cli_child_sink_apply_preflight_and_handoff tests/test_api.py::test_api_child_sink_apply_preflight_and_handoff tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_child_sink_apply_preflight_and_handoff -q` passed with 5 tests.
- `.venv/bin/python -m pytest -q -x -vv` passed with 263 tests.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `uv build --out-dir dist` built source and wheel distributions.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `codegraph sync && codegraph status` passed; index is up to date.

## 2026-06-15 Local Gate For Plan 0037

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_live_pilot_rehearsal_drill_reaches_command_copy_gate tests/test_cli_surfaces.py::test_cli_live_pilot_rehearsal_drill_reaches_command_copy_gate tests/test_api.py::test_api_live_pilot_rehearsal_drill_reaches_command_copy_gate tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 5 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py` passed.
- `.venv/bin/python -m pytest -q` passed with 279 tests.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `rg -n "operator-selected-live-smoke-preflight-sample-output|operator_selected_live_smoke_preflight_sample_output|operator_selected_live_smoke_preflight_markdown_path|Operator-Selected Live Smoke Preflight Sample Output" README.md ROADMAP.md RUNBOOK.md docs src tests` passed.
- `uv build --out-dir dist` built source and wheel distributions.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `codegraph sync && codegraph status` passed; index is up to date.

## 2026-06-15 Local Gate For Plan 0036

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_operator_selected_live_smoke_preflight_reports_blocked_boundary tests/test_cli_surfaces.py::test_cli_status_reports_command_map_text_and_json tests/test_cli_surfaces.py::test_cli_operator_selected_live_smoke_preflight_reports_blocked_boundary tests/test_api.py::test_api_operator_selected_live_smoke_preflight_reports_blocked_boundary tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_operator_selected_live_smoke_preflight_reports_blocked_boundary -q` passed with 6 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/cli.py src/business_card_watchdog/api.py src/business_card_watchdog/mcp.py tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py` passed.
- `.venv/bin/python -m pytest -q` passed with 279 tests.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `rg -n "operator-selected-live-smoke-preflight|operator_selected_live_smoke_preflight|Operator-selected live smoke preflight|business_card_watchdog_operator_selected_live_smoke_preflight" README.md ROADMAP.md RUNBOOK.md docs src tests` passed.
- `uv build --out-dir dist` built source and wheel distributions.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `codegraph sync && codegraph status` passed; index is up to date.

## 2026-06-15 Local Gate For Plan 0023

Validation:

- `.venv/bin/python -m pytest tests/test_review_surface.py::test_child_selected_target_response_validation_and_checklist tests/test_cli_surfaces.py::test_cli_child_selected_target_response_validation_and_checklist tests/test_api.py::test_api_child_selected_target_response_validation_and_checklist tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_child_selected_target_response_validation_and_checklist -q` passed with 5 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/cli.py src/business_card_watchdog/api.py src/business_card_watchdog/mcp.py tests/test_review_surface.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py` passed.
- `.venv/bin/python -m pytest -q` passed with 267 tests.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `uv build --out-dir dist` built source and wheel distributions.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `codegraph sync && codegraph status` passed; index is up to date.
- `.venv/bin/python -m pytest -q` passed with 267 tests.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `uv build --out-dir dist` built source and wheel distributions.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `codegraph sync && codegraph status` passed; index is up to date.
- `.venv/bin/python -m pytest -q` passed with 267 tests.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `uv build --out-dir dist` built source and wheel distributions.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `codegraph sync && codegraph status` passed; index is up to date.
- `.venv/bin/python -m pytest -q` passed with 267 tests.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `uv build --out-dir dist` built source and wheel distributions.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `codegraph sync && codegraph status` passed; index is up to date.
- `.venv/bin/python -m pytest -q` passed with 267 tests.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `uv build --out-dir dist` built source and wheel distributions.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `codegraph sync && codegraph status` passed; index is up to date.
- `.venv/bin/python -m pytest -q` passed with 267 tests.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `uv build --out-dir dist` built source and wheel distributions.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `codegraph sync && codegraph status` passed; index is up to date.
- `.venv/bin/python -m pytest -q` passed with 267 tests.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `uv build --out-dir dist` built source and wheel distributions.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `codegraph sync && codegraph status` passed; index is up to date.
- `.venv/bin/python -m pytest -q` passed with 267 tests.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `uv build --out-dir dist` built source and wheel distributions.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `codegraph sync && codegraph status` passed; index is up to date.

## 2026-06-15 Local Gate For Plan 0024

Validation:

- `.venv/bin/python -m pytest tests/test_review_surface.py::test_child_selected_target_response_validation_and_checklist tests/test_cli_surfaces.py::test_cli_child_selected_target_response_validation_and_checklist tests/test_api.py::test_api_child_selected_target_response_validation_and_checklist tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_child_selected_target_response_validation_and_checklist -q` passed with 5 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/cli.py src/business_card_watchdog/api.py src/business_card_watchdog/mcp.py tests/test_review_surface.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py` passed.

## 2026-06-15 Local Gate For Plan 0025

Validation:

- `.venv/bin/python -m pytest tests/test_review_surface.py::test_child_selected_target_response_validation_and_checklist tests/test_cli_surfaces.py::test_cli_child_selected_target_response_validation_and_checklist tests/test_api.py::test_api_child_selected_target_response_validation_and_checklist tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_child_selected_target_response_validation_and_checklist -q` passed with 5 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/cli.py src/business_card_watchdog/api.py src/business_card_watchdog/mcp.py tests/test_review_surface.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py` passed.

## 2026-06-15 Local Gate For Plan 0026

Validation:

- `.venv/bin/python -m pytest tests/test_review_surface.py::test_child_selected_target_response_validation_and_checklist tests/test_cli_surfaces.py::test_cli_child_selected_target_response_validation_and_checklist tests/test_api.py::test_api_child_selected_target_response_validation_and_checklist tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_child_selected_target_response_validation_and_checklist -q` passed with 5 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/cli.py src/business_card_watchdog/api.py src/business_card_watchdog/mcp.py tests/test_review_surface.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py` passed.

## 2026-06-15 Local Gate For Plan 0027

Validation:

- `.venv/bin/python -m pytest tests/test_review_surface.py::test_child_selected_target_response_validation_and_checklist tests/test_cli_surfaces.py::test_cli_child_selected_target_response_validation_and_checklist tests/test_api.py::test_api_child_selected_target_response_validation_and_checklist tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_child_selected_target_response_validation_and_checklist -q` passed with 5 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/cli.py src/business_card_watchdog/api.py src/business_card_watchdog/mcp.py tests/test_review_surface.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py` passed.

## 2026-06-15 Local Gate For Plan 0028

Validation:

- `.venv/bin/python -m pytest tests/test_review_surface.py::test_child_selected_target_response_validation_and_checklist tests/test_cli_surfaces.py::test_cli_child_selected_target_response_validation_and_checklist tests/test_api.py::test_api_child_selected_target_response_validation_and_checklist tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_child_selected_target_response_validation_and_checklist -q` passed with 5 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/cli.py src/business_card_watchdog/api.py src/business_card_watchdog/mcp.py tests/test_review_surface.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py` passed.

## 2026-06-15 Local Gate For Plan 0029

Validation:

- `.venv/bin/python -m pytest tests/test_review_surface.py::test_child_selected_target_response_validation_and_checklist tests/test_cli_surfaces.py::test_cli_child_selected_target_response_validation_and_checklist tests/test_api.py::test_api_child_selected_target_response_validation_and_checklist tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_child_selected_target_response_validation_and_checklist -q` passed with 5 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/cli.py src/business_card_watchdog/api.py src/business_card_watchdog/mcp.py tests/test_review_surface.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py` passed.

## 2026-06-15 Local Gate For Plan 0030

Validation:

- `.venv/bin/python -m pytest tests/test_review_surface.py::test_child_selected_target_response_validation_and_checklist tests/test_cli_surfaces.py::test_cli_child_selected_target_response_validation_and_checklist tests/test_api.py::test_api_child_selected_target_response_validation_and_checklist tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_child_selected_target_response_validation_and_checklist -q` passed with 5 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/cli.py src/business_card_watchdog/api.py src/business_card_watchdog/mcp.py tests/test_review_surface.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py` passed.

## 2026-06-15 Local Gate For Plan 0031

Validation:

- `.venv/bin/python -m pytest tests/test_review_surface.py::test_child_selected_target_response_validation_and_checklist tests/test_cli_surfaces.py::test_cli_child_selected_target_response_validation_and_checklist tests/test_api.py::test_api_child_selected_target_response_validation_and_checklist tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_child_selected_target_response_validation_and_checklist -q` passed with 5 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py tests/test_review_surface.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py` passed.
- `.venv/bin/python -m pytest -q` passed with 267 tests.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `uv build --out-dir dist` built source and wheel distributions.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `codegraph sync && codegraph status` passed; index is up to date.

## 2026-06-15 Local Gate For Plan 0032

Validation:

- `.venv/bin/python -m pytest tests/test_review_surface.py::test_service_child_replacement_readiness_drill_exports_operator_samples tests/test_cli_surfaces.py::test_cli_child_replacement_readiness_drill_exports_operator_samples tests/test_api.py::test_api_child_replacement_readiness_drill_exports_operator_samples tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_child_replacement_readiness_drill_exports_operator_samples -q` passed with 5 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/cli.py src/business_card_watchdog/api.py src/business_card_watchdog/mcp.py tests/test_review_surface.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py` passed.
- `.venv/bin/python -m pytest -q` passed with 271 tests.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `uv build --out-dir dist` built source and wheel distributions.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `codegraph sync && codegraph status` passed; index is up to date.

## 2026-06-15 Local Gate For Plan 0033

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_live_pilot_rehearsal_drill_reaches_command_copy_gate tests/test_cli_surfaces.py::test_cli_live_pilot_rehearsal_drill_reaches_command_copy_gate tests/test_api.py::test_api_live_pilot_rehearsal_drill_reaches_command_copy_gate tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_call_tool_dispatches_to_service -q` passed with 5 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/cli.py tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py` passed.
- `.venv/bin/python -m pytest -q` passed with 271 tests.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `rg -n "live-pilot-sample-output|live_pilot_rehearsal_sample_output|Live Pilot Rehearsal Sample Output|sample_outputs" README.md docs src tests` passed.
- `uv build --out-dir dist` built source and wheel distributions.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `codegraph sync && codegraph status` passed; index is up to date.

## 2026-06-15 Local Gate For Plan 0034

Validation:

- `.venv/bin/python -m pytest tests/test_review_surface.py::test_service_child_replacement_readiness_drill_exports_operator_samples tests/test_cli_surfaces.py::test_cli_child_replacement_readiness_drill_exports_operator_samples tests/test_api.py::test_api_child_replacement_readiness_drill_exports_operator_samples tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_child_replacement_readiness_drill_exports_operator_samples -q` passed with 5 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/cli.py tests/test_review_surface.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py` passed.
- `.venv/bin/python -m pytest -q` passed with 271 tests.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `rg -n "child-replacement-sample-output|child_replacement_readiness_sample_output|Child Replacement Readiness Sample Output|child_replacement_readiness_markdown_path" README.md docs src tests` passed.
- `uv build --out-dir dist` built source and wheel distributions.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `codegraph sync && codegraph status` passed; index is up to date.

## 2026-06-15 Local Gate For Plan 0035

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_offline_pilot_gap_audit_reports_remaining_live_boundaries tests/test_cli_surfaces.py::test_cli_status_reports_command_map_text_and_json tests/test_cli_surfaces.py::test_cli_offline_pilot_gap_audit_reports_remaining_boundaries tests/test_api.py::test_api_offline_pilot_gap_audit_reports_remaining_boundaries tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_offline_pilot_gap_audit_reports_remaining_boundaries -q` passed with 6 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/cli.py src/business_card_watchdog/api.py src/business_card_watchdog/mcp.py tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py` passed.
- `.venv/bin/python -m pytest -q` passed with 275 tests.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `rg -n "offline-pilot-gap-audit|offline_pilot_gap_audit|offline-pilot-gap|Offline pilot gap audit|business_card_watchdog_offline_pilot_gap_audit" README.md ROADMAP.md RUNBOOK.md docs src tests` passed.
- `uv build --out-dir dist` built source and wheel distributions.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `codegraph sync && codegraph status` passed; index is up to date.

## 2026-06-15 Local Gate For Plan 0038

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_watch_backlog_preflight_redacts_private_source_paths tests/test_service.py::test_service_watch_backlog_preflight_can_preview_without_writing tests/test_watcher.py::test_watch_backlog_preflight_cli_outputs_redacted_counts tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_watch_backlog_preflight_redacts_private_source_paths -q` passed with 6 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/cli.py src/business_card_watchdog/api.py src/business_card_watchdog/mcp.py tests/test_service.py tests/test_watcher.py tests/test_api.py tests/test_mcp.py` passed.
- `.venv/bin/python -m pytest -q` passed with 283 tests.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `rg -n "watch-backlog-preflight|watch_backlog_preflight|Watch backlog preflight|business_card_watchdog_watch_backlog_preflight" README.md ROADMAP.md RUNBOOK.md docs src tests` passed.
- `uv build --out-dir dist` built source and wheel distributions.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `codegraph sync && codegraph status` passed; index is up to date.
- `.venv/bin/bcw watch-backlog-preflight --no-write --json` passed against the user config and reported `$fsr:sync_phone` as one redacted input with 5 backlog items, 0 unsettled items, no last error, no runtime artifact write, no OCR, no file processing, and no network calls.

## 2026-06-15 Local Gate For Plan 0039

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_watch_backlog_preflight_redacts_private_source_paths tests/test_service.py::test_service_watch_dry_run_selection_handoff_validates_response_and_command_copy tests/test_service.py::test_service_watch_dry_run_command_copy_blocks_without_acknowledgement tests/test_watcher.py::test_watch_backlog_preflight_cli_outputs_redacted_counts tests/test_watcher.py::test_watch_dry_run_selection_cli_validates_and_builds_command_copy tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_watch_backlog_preflight_redacts_private_source_paths tests/test_mcp.py::test_mcp_watch_dry_run_selection_flow_returns_command_copy -q` passed with 9 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/cli.py src/business_card_watchdog/api.py src/business_card_watchdog/mcp.py tests/test_service.py tests/test_watcher.py tests/test_api.py tests/test_mcp.py tests/test_cli_surfaces.py` passed.
- `.venv/bin/python -m pytest -q` passed with 287 tests.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `rg -n "watch-dry-run-selection-handoff|watch_dry_run_selection_handoff|watch-dry-run-validate-response|watch_dry_run_command_copy|business_card_watchdog_watch_dry_run" README.md ROADMAP.md RUNBOOK.md docs src tests` passed.
- `uv build --out-dir dist` built source and wheel distributions.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `codegraph sync && codegraph status` passed; index is up to date.
- `.venv/bin/bcw watch-dry-run-selection-handoff --no-write --json` passed against the user config and reported `$fsr:sync_phone` as one redacted input with 5 backlog items, 0 unsettled items, no runtime artifact write, no OCR, no file processing, and no network calls.

## 2026-06-15 Local Gate For Plan 0040

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_watch_dry_run_selection_drill_exports_sample_output tests/test_cli_surfaces.py::test_cli_watch_dry_run_selection_drill_exports_sample_output tests/test_api.py::test_api_watch_dry_run_selection_drill_exports_sample_output tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_watch_dry_run_selection_drill_exports_sample_output -q` passed with 5 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/cli.py src/business_card_watchdog/api.py src/business_card_watchdog/mcp.py tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py` passed.
- `.venv/bin/python -m pytest -q` passed with 291 tests.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `rg -n "watch-dry-run-selection|watch_dry_run_selection|Watch Dry-Run Selection|business_card_watchdog_watch_dry_run_selection_drill|Plan 0040" README.md ROADMAP.md RUNBOOK.md docs src tests` passed.
- `uv build --out-dir dist` built source and wheel distributions.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `codegraph sync && codegraph status` passed; index is up to date.
- `.venv/bin/bcw drills watch-dry-run-selection --json` passed with `state=passed`, `command_copy_ready=true`, one synthetic fixture backlog item, zero files processed, zero OCR attempts, zero writes, and zero network calls.

Safety:

- The Plan 0040 smoke used a synthetic fixture watch source under the cache directory. It did not process configured SyncThing/private watch inputs; run OCR/App Intelligence; run public-web search; call paid enrichment; execute live lookup/write/readback; or write Google Contacts, Odoo, or Odollo records.

## 2026-06-15 Local Gate For Plan 0041

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_watch_dry_run_execution_drill_runs_real_dry_pipeline tests/test_cli_surfaces.py::test_cli_watch_dry_run_execution_drill_runs_real_dry_pipeline tests/test_api.py::test_api_watch_dry_run_execution_drill_runs_real_dry_pipeline tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_watch_dry_run_execution_drill_runs_real_dry_pipeline -q` passed with 5 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/cli.py src/business_card_watchdog/api.py src/business_card_watchdog/mcp.py tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py` passed.
- `.venv/bin/python -m pytest -q` passed with 295 tests.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `rg -n "watch-dry-run-execution|watch_dry_run_execution|Watch Dry-Run Execution|business_card_watchdog_watch_dry_run_execution_drill|Plan 0041" README.md ROADMAP.md RUNBOOK.md docs src tests` passed.
- `uv build --out-dir dist` built source and wheel distributions.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `codegraph sync && codegraph status` passed; index is up to date.
- `.venv/bin/bcw drills watch-dry-run-execution --json` passed with `state=passed`, one synthetic fixture file processed, a completed dry-run batch run, OCR/contact/review/sink payload artifacts, zero duplicate processing after restart, zero writes, and zero network calls.

Safety:

- The Plan 0041 smoke used a synthetic fixture watch source under the cache directory. It did not process configured SyncThing/private watch inputs; run public-web search; call paid enrichment; execute live lookup/write/readback; or write Google Contacts, Odoo, or Odollo records.

## 2026-06-15 Local Gate For Plan 0042

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_watch_dry_run_readiness_redacts_private_source_and_blocks_command tests/test_watcher.py::test_watch_dry_run_readiness_cli_redacts_and_blocks_command_copy tests/test_api.py::test_api_health_status_runs_and_jobs tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_watch_dry_run_selection_flow_returns_command_copy -q` passed with 5 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/cli.py src/business_card_watchdog/api.py src/business_card_watchdog/mcp.py tests/test_service.py tests/test_watcher.py tests/test_api.py tests/test_mcp.py` passed.
- `.venv/bin/python -m pytest -q` passed with 297 tests.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `rg -n "watch-dry-run-readiness|watch_dry_run_readiness|Watch dry-run readiness|business_card_watchdog_watch_dry_run_readiness|Plan 0042" README.md ROADMAP.md RUNBOOK.md docs src tests` passed.
- `uv build --out-dir dist` built source and wheel distributions.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `codegraph sync && codegraph status` passed; index is up to date.
- `.venv/bin/bcw watch-dry-run-readiness --no-write --json` passed against the configured watcher and reported `$fsr:sync_phone` as one redacted input with 5 backlog items, 0 unsettled items, no runtime artifact write, no copyable command, no OCR, no file processing, and no network calls.

Safety:

- The Plan 0042 smoke created a no-processing readiness packet only. It did not process configured SyncThing/private watch inputs; run OCR/App Intelligence; run public-web search; call paid enrichment; execute live lookup/write/readback; or write Google Contacts, Odoo, or Odollo records.

## 2026-06-15 Local Gate For Plan 0043

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_dry_run_closeout_audits_completed_dry_run tests/test_cli_surfaces.py::test_cli_runs_dry_run_closeout_reports_no_live tests/test_api.py::test_api_run_dry_run_closeout_reports_no_live tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_dry_run_closeout_reports_no_live -q` passed with 5 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/cli.py src/business_card_watchdog/api.py src/business_card_watchdog/mcp.py tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py` passed.
- `.venv/bin/python -m pytest -q` passed with 301 tests.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `rg -n "dry-run-closeout|dry_run_closeout|Dry-run closeout|business_card_watchdog_dry_run_closeout|Plan 0043" README.md ROADMAP.md RUNBOOK.md docs src tests` passed.
- `uv build --out-dir dist` built source and wheel distributions.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `codegraph sync && codegraph status` passed; index is up to date.
- `.venv/bin/bcw drills watch-dry-run-execution --json` passed with one synthetic fixture file processed through a completed dry-run batch and no writes or network calls.
- `.venv/bin/bcw --config <temp-fixture-config> runs dry-run-closeout 2026-06-15T13-04-42+00-00 --no-write --json` passed with `state=ready_for_review_and_routing`, zero live markers, zero writes, and zero network calls.

Safety:

- The Plan 0043 closeout reads local run ledgers only. It did not process configured SyncThing/private watch inputs; run public-web search; call paid enrichment; execute live lookup/write/readback; or write Google Contacts, Odoo, or Odollo records.

## 2026-06-15 Local Gate For Plan 0044

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_dry_run_review_handoff_summarizes_safe_next_steps tests/test_cli_surfaces.py::test_cli_runs_dry_run_review_handoff_reports_safe_next_steps tests/test_api.py::test_api_run_dry_run_review_handoff_reports_safe_next_steps tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_dry_run_review_handoff_reports_safe_next_steps -q` passed with 5 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/cli.py src/business_card_watchdog/api.py src/business_card_watchdog/mcp.py tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py` passed.
- `.venv/bin/python -m pytest -q` passed with 305 tests.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `rg -n "dry-run-review-handoff|dry_run_review_handoff|Dry-run review handoff|business_card_watchdog_dry_run_review_handoff|Plan 0044" README.md ROADMAP.md RUNBOOK.md docs src tests` passed.
- `uv build --out-dir dist` built source and wheel distributions.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `codegraph sync && codegraph status` passed; index is up to date.
- `.venv/bin/bcw --config <temp-fixture-config> runs dry-run-review-handoff 2026-06-15T13-15-20+00-00 --no-write --json` passed with `state=ready_for_safe_agent_loop`, one safe `plan_sink_lookup`, zero writes, zero network calls, and no live sink calls.

Safety:

- The Plan 0044 handoff reads local dry-run ledger and review artifacts only. It did not process configured SyncThing/private watch inputs; run OCR/App Intelligence; run public-web search; call paid enrichment; execute live lookup/write/readback; or write Google Contacts, Odoo, or Odollo records.

## 2026-06-15 Local Gate For Plan 0045

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_dry_run_safe_loop_executes_bounded_safe_actions tests/test_cli_surfaces.py::test_cli_runs_dry_run_safe_loop_executes_bounded_safe_actions tests/test_api.py::test_api_run_dry_run_safe_loop_executes_bounded_safe_actions tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_dry_run_safe_loop_executes_bounded_safe_actions -q` passed with 5 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/cli.py src/business_card_watchdog/api.py src/business_card_watchdog/mcp.py tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py` passed.
- `.venv/bin/python -m pytest -q` passed with 309 tests.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `rg -n "dry-run-safe-loop|dry_run_safe_loop|Dry-run safe loop|business_card_watchdog_dry_run_safe_loop|Plan 0045" README.md ROADMAP.md RUNBOOK.md docs src tests` passed.
- `uv build --out-dir dist` built source and wheel distributions.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `codegraph sync && codegraph status` passed; index is up to date.
- `.venv/bin/bcw --config <temp-fixture-config> runs dry-run-safe-loop 2026-06-15T13-22-52+00-00 --limit 3 --no-write --json` passed with `state=safe_loop_executed`, three safe actions, zero writes, zero network calls, and no live sink calls.

Safety:

- The Plan 0045 safe loop is gated by dry-run closeout and dry-run review handoff. It did not process configured SyncThing/private watch inputs; run OCR/App Intelligence beyond the synthetic fixture drill; run public-web search; call paid enrichment; execute live lookup/write/readback; or write Google Contacts, Odoo, or Odollo records.

## 2026-06-15 Local Gate For Plan 0046

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_review_route_readiness_summarizes_review_and_route_state tests/test_cli_surfaces.py::test_cli_runs_review_route_readiness_reports_route_state tests/test_api.py::test_api_run_review_route_readiness_reports_route_state tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_review_route_readiness_reports_route_state -q` passed with 5 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/cli.py src/business_card_watchdog/api.py src/business_card_watchdog/mcp.py tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py` passed.
- `.venv/bin/python -m pytest -q` passed with 313 tests.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `rg -n "review-route-readiness|review_route_readiness|Review-route readiness|business_card_watchdog_review_route_readiness|Plan 0046" README.md ROADMAP.md RUNBOOK.md docs src tests` passed.
- `uv build --out-dir dist` built source and wheel distributions.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `codegraph sync && codegraph status` passed; index is up to date.
- `.venv/bin/bcw drills watch-dry-run-execution --json` passed with one synthetic fixture file processed through a completed dry-run batch and no writes or network calls.
- `.venv/bin/bcw --config <temp-fixture-config> runs review-route-readiness 2026-06-15T13-34-46+00-00 --no-write --json` passed with `state=ready_for_safe_agent_loop`, one route-ready job, one safe `plan_sink_lookup`, zero writes, zero network calls, and no live sink calls.

Safety:

- The Plan 0046 readiness report reads local dry-run review, duplicate, enrichment, and route artifacts only. It did not process configured SyncThing/private watch inputs; run OCR/App Intelligence; run public-web search; call paid enrichment; execute live lookup/write/readback; or write Google Contacts, Odoo, or Odollo records.

## 2026-06-15 Local Gate For Plan 0047

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_lookup_selection_packet_selects_route_ready_job_without_live_calls tests/test_cli_surfaces.py::test_cli_runs_lookup_selection_packet_reports_selected_candidate tests/test_api.py::test_api_run_lookup_selection_packet_reports_selected_candidate tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_lookup_selection_packet_reports_selected_candidate -q` passed with 5 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/cli.py src/business_card_watchdog/api.py src/business_card_watchdog/mcp.py tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py` passed.
- `.venv/bin/python -m pytest -q` passed with 317 tests.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `rg -n "lookup-selection-packet|lookup_selection_packet|Lookup selection packet|business_card_watchdog_lookup_selection_packet|Plan 0047" README.md ROADMAP.md RUNBOOK.md docs src tests` passed.
- `uv build --out-dir dist` built source and wheel distributions.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `codegraph sync && codegraph status` passed; index is up to date.
- `.venv/bin/bcw drills watch-dry-run-execution --json` passed with one synthetic fixture file processed through a completed dry-run batch and no writes or network calls.
- `.venv/bin/bcw --config <temp-fixture-config> runs lookup-selection-packet 2026-06-15T13-44-18+00-00 --operator fixture-smoke --sink google_contacts --no-write --json` passed with `state=packet_blocked`, one route-ready job, one selected lookup packet, zero writes, zero network calls, no selected-target creation, and no live sink calls.

Safety:

- The Plan 0047 lookup selection packet reads local dry-run review-route readiness and previews the existing live selection packet. It did not create `selected_live_target.json`; process configured SyncThing/private watch inputs; run OCR/App Intelligence; run public-web search; call paid enrichment; execute live lookup/write/readback; or write Google Contacts, Odoo, or Odollo records.

## 2026-06-15 Local Gate For Plan 0048

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_close_lookup_prerequisites_executes_only_lookup_safe_actions tests/test_cli_surfaces.py::test_cli_runs_close_lookup_prerequisites_executes_lookup_steps tests/test_api.py::test_api_run_close_lookup_prerequisites_executes_lookup_steps tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_close_lookup_prerequisites_executes_lookup_steps -q` passed with 5 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/cli.py src/business_card_watchdog/api.py src/business_card_watchdog/mcp.py tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py` passed.
- `.venv/bin/python -m pytest -q` passed with 321 tests.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `rg -n "close-lookup-prerequisites|close_lookup_prerequisites|Close lookup prerequisites|business_card_watchdog_close_lookup_prerequisites|Plan 0048" README.md ROADMAP.md RUNBOOK.md docs src tests` passed.
- `uv build --out-dir dist` built source and wheel distributions.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `codegraph sync && codegraph status` passed; index is up to date.
- `.venv/bin/bcw drills watch-dry-run-execution --json` passed with one synthetic fixture file processed through a completed dry-run batch and no writes or network calls.
- Synthetic CLI close-lookup smoke passed with `state=lookup_prerequisites_advanced`, `executed_count=4`, remaining missing requirement `live_lookup_readiness_ready`, zero writes, zero network calls, no selected-target creation, and no runtime artifact write under `--no-write`.

Safety:

- The Plan 0048 closer executes only local lookup prerequisite actions and stops before selected-target approval. It did not approve contact review; create `selected_live_target.json`; process configured SyncThing/private watch inputs; run OCR/App Intelligence; run public-web search; call paid enrichment; execute live lookup/write/readback; or write Google Contacts, Odoo, or Odollo records.

## 2026-06-15 Local Gate For Plan 0049

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_selected_target_approval_boundary_previews_explicit_selection tests/test_cli_surfaces.py::test_cli_runs_selected_target_approval_boundary_previews_selection tests/test_api.py::test_api_run_selected_target_approval_boundary_previews_selection tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_selected_target_approval_boundary_previews_selection -q` passed with 5 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/cli.py src/business_card_watchdog/api.py src/business_card_watchdog/mcp.py tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py` passed.
- `.venv/bin/python -m pytest -q` passed with 325 tests.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `rg -n "selected-target-approval-boundary|selected_target_approval_boundary|Selected-target approval boundary|business_card_watchdog_selected_target_approval_boundary|Plan 0049" README.md ROADMAP.md RUNBOOK.md docs src tests` passed.
- `uv build --out-dir dist` built source and wheel distributions.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `codegraph sync && codegraph status` passed; index is up to date.
- `.venv/bin/bcw drills watch-dry-run-execution --json` passed with one synthetic fixture file processed through a completed dry-run batch and no writes or network calls.
- Synthetic CLI selected-target approval boundary smoke passed with `state=ready_for_explicit_selected_target_creation`, validation state `ready_to_select_live_target`, preflight state `ready_to_create_selected_target`, preview state `ready`, zero writes, zero network calls, no selected-target creation, and no runtime artifact write under `--no-write`.

Safety:

- The Plan 0049 boundary packet composes approval templates, response validation, selected-target preflight, and selected-target preview while stopping before selected-target creation. It did not create `selected_live_target.json`; process configured SyncThing/private watch inputs; run OCR/App Intelligence; run public-web search; call paid enrichment; execute live lookup/write/readback; or write Google Contacts, Odoo, or Odollo records.

## 2026-06-15 Local Gate For Plan 0050

Validation:

- `.venv/bin/python -m pytest tests/test_service.py::test_service_selected_target_command_copy_packet_requires_acknowledgement tests/test_cli_surfaces.py::test_cli_runs_selected_target_command_copy_packet_requires_ack tests/test_api.py::test_api_run_selected_target_command_copy_packet_requires_ack tests/test_mcp.py::test_manifest_has_process_tool tests/test_mcp.py::test_mcp_selected_target_command_copy_packet_requires_ack -q` passed with 5 tests.
- `.venv/bin/ruff check src/business_card_watchdog/service.py src/business_card_watchdog/cli.py src/business_card_watchdog/api.py src/business_card_watchdog/mcp.py tests/test_service.py tests/test_cli_surfaces.py tests/test_api.py tests/test_mcp.py` passed.
- `.venv/bin/python -m pytest -q` passed with 329 tests.
- `.venv/bin/ruff check .` passed.
- `git diff --check` passed.
- `rg -n "selected-target-command-copy-packet|selected_target_command_copy_packet|Selected-target command copy packet|business_card_watchdog_selected_target_command_copy_packet|Plan 0050" README.md ROADMAP.md RUNBOOK.md docs src tests` passed.
- `uv build --out-dir dist` built source and wheel distributions.
- `gitleaks detect --source . --no-banner --redact --exit-code 1` passed with no leaks found.
- `codegraph sync && codegraph status` passed; index is up to date.
- `.venv/bin/bcw drills watch-dry-run-execution --json` passed with one synthetic fixture file processed through a completed dry-run batch and no writes or network calls.
- Synthetic CLI selected-target command-copy smoke passed with `state=ready_for_operator_copy`, boundary state `ready_for_explicit_selected_target_creation`, acknowledgement ok, command text for `runs selected-live-target-from-response ... --write-selected-target`, zero writes, zero network calls, and no selected-target creation from the packet.

Safety:

- The Plan 0050 packet requires matching acknowledgement before returning selected-target creation command text. It did not create `selected_live_target.json`; process configured SyncThing/private watch inputs; run OCR/App Intelligence; run public-web search; call paid enrichment; execute live lookup/write/readback; or write Google Contacts, Odoo, or Odollo records.

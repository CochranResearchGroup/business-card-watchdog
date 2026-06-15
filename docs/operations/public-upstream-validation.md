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

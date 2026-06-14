from __future__ import annotations

import csv
import json
from io import StringIO
from pathlib import Path

from business_card_watchdog.cli import build_parser, main
from business_card_watchdog.config import (
    AppConfig,
    EnrichmentConfig,
    EnrichmentProviderConfig,
    PrefilterConfig,
    SinkConfig,
)
from business_card_watchdog.contact import build_contact_candidate
from business_card_watchdog.orchestrator import BatchOrchestrator
from business_card_watchdog.service_ops import service_unit_path

from synthetic_fixtures import SyntheticSkillAdapter, latest_jobs_by_id, write_synthetic_image
from test_service import make_recorded_run


def write_config(path: Path, data_dir: Path) -> None:
    path.write_text(f'data_dir = "{data_dir}"\n[watch]\ninputs = []\n', encoding="utf-8")


def test_cli_has_mcp_stdio_command() -> None:
    args = build_parser().parse_args(["mcp-stdio"])

    assert args.command == "mcp-stdio"


def test_cli_runtime_readiness_reports_local_runtime_state(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "config.toml"
    data_dir = tmp_path / "data"
    write_config(config_path, data_dir)

    assert main(["--config", str(config_path), "runtime-readiness", "--json"]) in {0, 2}
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema"] == "business-card-watchdog.runtime-readiness.v1"
    assert payload["config"]["config_exists"] is True
    assert payload["network_calls_made"] == 0
    assert payload["writes_attempted"] == 0

    assert main(["--config", str(config_path), "runtime-readiness"]) in {0, 2}
    text = capsys.readouterr().out
    assert "Runtime readiness:" in text
    assert "Config:" in text
    assert "{" not in text


def test_cli_service_recovery_reports_status_shape(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "config.toml"
    data_dir = tmp_path / "data"
    write_config(config_path, data_dir)
    run_id, _job_id = make_recorded_run(AppConfig(config_path=config_path, data_dir=data_dir))

    assert main(["--config", str(config_path), "service", "recovery", "--run-id", run_id, "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema"] == "business-card-watchdog.service-recovery.v1"
    assert payload["run_id"] == run_id
    assert payload["commands"]["status"].startswith(f"bcw --config {config_path} service status")
    assert payload["network_calls_made"] == 0
    assert payload["writes_attempted"] == 0

    assert main(["--config", str(config_path), "service", "recovery", "--run-id", run_id]) == 0
    text = capsys.readouterr().out
    assert "Service recovery:" in text
    assert f"Run: {run_id}" in text
    assert "Restart: systemctl --user restart business-card-watchdog.service" in text
    assert "Resume: bcw --config" in text
    assert "{" not in text


def test_cli_live_target_candidates_reports_text_and_json(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "config.toml"
    data_dir = tmp_path / "data"
    config_path.write_text(
        f'data_dir = "{data_dir}"\n[watch]\ninputs = []\n[sink]\ngoogle_contacts = true\n',
        encoding="utf-8",
    )
    run_id, _job_id = make_recorded_run(
        AppConfig(
            config_path=config_path,
            data_dir=data_dir,
            sink=SinkConfig(google_contacts=True, dry_run=True),
        )
    )

    assert main(["--config", str(config_path), "live-target-candidates", "--run-id", run_id, "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema"] == "business-card-watchdog.live-target-candidates.v1"
    assert payload["candidate_count"] == 1
    assert payload["network_calls_made"] == 0
    assert payload["writes_attempted"] == 0

    assert main(["--config", str(config_path), "live-target-candidates", "--run-id", run_id]) == 0
    text = capsys.readouterr().out
    assert "Live target candidates: 1" in text
    assert "sink=google_contacts" in text
    assert "{" not in text


def test_cli_live_readiness_audit_reports_text_and_json(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "config.toml"
    data_dir = tmp_path / "data"
    config_path.write_text(
        f'data_dir = "{data_dir}"\n[watch]\ninputs = []\n[sink]\ngoogle_contacts = true\n',
        encoding="utf-8",
    )
    run_id, _job_id = make_recorded_run(
        AppConfig(
            config_path=config_path,
            data_dir=data_dir,
            sink=SinkConfig(google_contacts=True, dry_run=True),
        )
    )

    assert main(["--config", str(config_path), "live-readiness-audit", "--run-id", run_id, "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema"] == "business-card-watchdog.live-readiness-audit.v1"
    assert payload["candidate_count"] == 1
    assert Path(payload["audit_path"]).exists()
    assert payload["network_calls_made"] == 0
    assert payload["writes_attempted"] == 0

    assert main(["--config", str(config_path), "live-readiness-audit", "--run-id", run_id, "--no-write"]) == 0
    text = capsys.readouterr().out
    assert "Live readiness audit:" in text
    assert f"Run: {run_id}" in text
    assert "{" not in text


def test_cli_live_selection_packet_writes_no_selected_target(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "config.toml"
    data_dir = tmp_path / "data"
    config_path.write_text(
        f'data_dir = "{data_dir}"\n[watch]\ninputs = []\n[sink]\ngoogle_contacts = true\n',
        encoding="utf-8",
    )
    run_id, job_id = make_recorded_run(
        AppConfig(
            config_path=config_path,
            data_dir=data_dir,
            sink=SinkConfig(google_contacts=True, dry_run=True),
        )
    )

    assert (
        main(
            [
                "--config",
                str(config_path),
                "sinks",
                "live-selection-packet",
                job_id,
                "--run-id",
                run_id,
                "--sink",
                "google_contacts",
                "--operator",
                "tester",
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema"] == "business-card-watchdog.live-selection-packet.v1"
    assert payload["approval_state"] == "pending_operator_approval"
    assert Path(payload["packet_path"]).exists()
    assert not Path(payload["existing_selected_target"]["path"]).exists()


def test_cli_runs_and_jobs_use_recorded_runtime_state(
    tmp_path: Path, capsys
) -> None:
    config_path = tmp_path / "config.toml"
    data_dir = tmp_path / "data"
    write_config(config_path, data_dir)
    run_id, job_id = make_recorded_run(AppConfig(config_path=config_path, data_dir=data_dir))

    assert main(["--config", str(config_path), "runs", "list", "--json"]) == 0
    runs = json.loads(capsys.readouterr().out)
    assert runs[0]["run_id"] == run_id
    assert main(["--config", str(config_path), "runs", "list"]) == 0
    runs_text = capsys.readouterr().out
    assert "Runs: 1" in runs_text
    assert f"{run_id} state=waiting_for_review jobs=1" in runs_text
    assert "{" not in runs_text
    assert main(["--config", str(config_path), "runs", "show", run_id]) == 0
    run_text = capsys.readouterr().out
    assert f"Run: {run_id}" in run_text
    assert "State: waiting_for_review" in run_text
    assert "Jobs: 1" in run_text
    assert "Loaded jobs: 1" in run_text
    assert "Artifacts: 1" in run_text
    assert "{" not in run_text

    assert main(["--config", str(config_path), "runs", "summary", run_id, "--json"]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["needs_review_count"] == 1
    assert main(["--config", str(config_path), "runs", "summary", run_id]) == 0
    summary_text = capsys.readouterr().out
    assert f"Run: {run_id}" in summary_text
    assert "Needs review: 1" in summary_text
    assert "Enrichment: public_web_requests=0 paid_provider_requests=0 paid_api_calls_attempted=0" in summary_text
    assert "Sink pilots: write=0 readback=0 reports=0 complete_reports=0" in summary_text
    assert "Review workbook preview: has_preview=False latest_valid=None errors=0 warnings=0" in summary_text
    assert "{" not in summary_text

    assert main(["--config", str(config_path), "runs", "phase-report", run_id, "--json"]) == 0
    phase_report = json.loads(capsys.readouterr().out)
    assert phase_report["schema"] == "business-card-watchdog.phase-report.v1"
    assert phase_report["review_workbook_preview"]["schema"] == (
        "business-card-watchdog.review-workbook-preview-phase.v1"
    )
    assert phase_report["review_workbook_preview"]["state"] == "not_started"
    assert phase_report["dashboard_summary"]["schema"] == "business-card-watchdog.phase-dashboard-summary.v1"
    assert phase_report["dashboard_summary"]["blocked_phases"] == [{"phase": "review", "count": 1}]
    assert phase_report["phases"][2]["phase"] == "review"
    assert phase_report["phases"][2]["counts"]["blocked"] == 1
    assert main(["--config", str(config_path), "runs", "phase-report", run_id]) == 0
    phase_text = capsys.readouterr().out
    assert f"Run: {run_id}" in phase_text
    assert "Status: 1 blocked phases; 0 explicit-required phases; review workbook preview not_started" in phase_text
    assert "Review workbook preview: not_started" in phase_text
    assert "Blocked phases: review=1" in phase_text
    assert "{" not in phase_text

    assert main(["--config", str(config_path), "runs", "pilot-readiness", run_id, "--json"]) == 0
    readiness_report = json.loads(capsys.readouterr().out)
    assert readiness_report["schema"] == "business-card-watchdog.pilot-readiness-report.v1"
    assert readiness_report["state"] == "explicit_operator_required"
    assert readiness_report["blocked_job_ids"] == [job_id]
    assert main(["--config", str(config_path), "runs", "pilot-readiness", run_id]) == 0
    readiness_text = capsys.readouterr().out
    assert f"Run: {run_id}" in readiness_text
    assert "Readiness: ready_for_write_pilot=0 safe_auto_available=0 explicit_operator_required=1" in readiness_text
    assert "Pilot evidence: write_complete=0 readback_complete=0 pilot_report_complete=0" in readiness_text
    assert "{" not in readiness_text

    assert (
        main(
            [
                "--config",
                str(config_path),
                "sinks",
                "lookup-readiness",
                job_id,
                "--run-id",
                run_id,
                "--sink",
                "google_contacts",
                "--json",
            ]
        )
        == 0
    )
    lookup_readiness = json.loads(capsys.readouterr().out)
    assert lookup_readiness["schema"] == "business-card-watchdog.live-lookup-readiness.v1"
    assert lookup_readiness["state"] == "blocked"
    assert lookup_readiness["writes_attempted"] == 0
    assert lookup_readiness["network_calls_made"] == 0

    assert main(["--config", str(config_path), "jobs", "show", job_id, "--run-id", run_id, "--json"]) == 0
    job = json.loads(capsys.readouterr().out)
    assert job["job_id"] == job_id
    assert job["artifacts"][0]["kind"] == "contact_spec"
    assert main(["--config", str(config_path), "jobs", "list", "--run-id", run_id]) == 0
    jobs_text = capsys.readouterr().out
    assert "Jobs: 1" in jobs_text
    assert f"{job_id} run={run_id} state=needs_review" in jobs_text
    assert "{" not in jobs_text
    assert main(["--config", str(config_path), "jobs", "show", job_id, "--run-id", run_id]) == 0
    job_text = capsys.readouterr().out
    assert f"Job: {job_id}" in job_text
    assert f"Run: {run_id}" in job_text
    assert "State: needs_review" in job_text
    assert "Artifacts: contact_spec" in job_text
    assert "{" not in job_text

    assert main(["--config", str(config_path), "reviews", "list", "--run-id", run_id, "--json"]) == 0
    reviews = json.loads(capsys.readouterr().out)
    assert reviews[0]["job_id"] == job_id
    assert reviews[0]["next_action"]["action"] == "review_contact"
    assert main(["--config", str(config_path), "reviews", "list", "--run-id", run_id]) == 0
    review_text = capsys.readouterr().out
    assert "Review queue: 1 jobs" in review_text
    assert f"{job_id} state=needs_review next=review_contact artifacts=contact_spec" in review_text
    assert "{" not in review_text

    assert (
        main(
            [
                "--config",
                str(config_path),
                "reviews",
                "list",
                "--run-id",
                run_id,
                "--next-action",
                "review_contact",
                "--artifact-kind",
                "contact_spec",
                "--json",
            ]
        )
        == 0
    )
    filtered_reviews = json.loads(capsys.readouterr().out)
    assert [entry["job_id"] for entry in filtered_reviews] == [job_id]
    assert (
        main(
            [
                "--config",
                str(config_path),
                "reviews",
                "list",
                "--run-id",
                run_id,
                "--next-action",
                "plan_sinks",
            ]
        )
        == 0
    )
    empty_review_text = capsys.readouterr().out
    assert empty_review_text == "Review queue: 0 jobs\n"

    assert main(["--config", str(config_path), "reviews", "bundle", "--run-id", run_id, "--json"]) == 0
    bundle = json.loads(capsys.readouterr().out)
    assert bundle["schema"] == "business-card-watchdog.review-bundle.v1"
    assert bundle["entries"][0]["job_id"] == job_id
    assert bundle["entries"][0]["next_action"]["action"] == "review_contact"
    assert bundle["groups"]["by_state"]["needs_review"]["count"] == 1
    assert bundle["decision_import_template"][0]["action"] == "approve_for_routing"
    assert Path(bundle["review_bundle_path"]).exists()

    assert main(["--config", str(config_path), "reviews", "html", "--run-id", run_id, "--json"]) == 0
    html = json.loads(capsys.readouterr().out)
    assert html["schema"] == "business-card-watchdog.review-html.v1"
    assert "Business Card Review" in html["html"]
    assert Path(html["html_path"]).exists()

    assert main(["--config", str(config_path), "reviews", "workbook", "--run-id", run_id, "--json"]) == 0
    workbook = json.loads(capsys.readouterr().out)
    assert workbook["schema"] == "business-card-watchdog.review-workbook.v1"
    assert Path(workbook["workbook_path"]).exists()
    rows = list(csv.DictReader(StringIO(workbook["csv"])))
    assert rows[0]["job_id"] == job_id
    assert rows[0]["next_action"] == "review_contact"
    assert rows[0]["review_action"] == "approve_for_routing"
    assert "corrected_email" in rows[0]

    assert main(["--config", str(config_path), "reviews", "workbook", "--run-id", run_id, "--no-write"]) == 0
    csv_text = capsys.readouterr().out
    assert "job_id,state,image_path,next_action" in csv_text
    assert job_id in csv_text

    workbook_rows = list(csv.DictReader(StringIO(workbook["csv"])))
    workbook_rows[0]["review_action"] = "approve_for_routing"
    workbook_rows[0]["corrected_full_name"] = "CLI Workbook"
    workbook_import_path = tmp_path / "review-workbook-import.csv"
    with workbook_import_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(workbook_rows[0]))
        writer.writeheader()
        writer.writerows(workbook_rows)
    assert (
        main(
            [
                "--config",
                str(config_path),
                "reviews",
                "apply-decisions",
                "--run-id",
                run_id,
                "--reviewer",
                "cli-workbook",
                "--decisions-csv-file",
                str(workbook_import_path),
                "--preview",
                "--preview-write",
                "--json",
            ]
        )
        == 0
    )
    workbook_preview = json.loads(capsys.readouterr().out)
    assert workbook_preview["schema"] == "business-card-watchdog.review-workbook-preview.v1"
    assert workbook_preview["ready_count"] == 1
    assert "row_number,status,run_id,job_id,action,errors,warnings" in workbook_preview["validation_csv"]
    assert Path(workbook_preview["validation_csv_path"]).exists()
    assert workbook_preview["writes_attempted"] == 0
    assert (
        main(
            [
                "--config",
                str(config_path),
                "reviews",
                "preview-validation",
                "--run-id",
                run_id,
                "--reviewer",
                "cli-workbook",
                "--decisions-csv-file",
                str(workbook_import_path),
            ]
        )
        == 0
    )
    validation_csv = capsys.readouterr().out
    assert "row_number,status,run_id,job_id,action,errors,warnings" in validation_csv
    assert "ready" in validation_csv
    assert (
        main(
            [
                "--config",
                str(config_path),
                "reviews",
                "preview-validation",
                "--run-id",
                run_id,
                "--reviewer",
                "cli-workbook",
                "--decisions-csv-file",
                str(workbook_import_path),
                "--write-artifacts",
                "--json",
            ]
        )
        == 0
    )
    validation_preview = json.loads(capsys.readouterr().out)
    assert Path(validation_preview["validation_csv_path"]).exists()
    assert (
        main(
            [
                "--config",
                str(config_path),
                "reviews",
                "apply-decisions",
                "--run-id",
                run_id,
                "--reviewer",
                "cli-workbook",
                "--decisions-csv-file",
                str(workbook_import_path),
                "--json",
            ]
        )
        == 0
    )
    workbook_import = json.loads(capsys.readouterr().out)
    assert workbook_import["import"]["source_format"] == "csv"
    assert workbook_import["results"][0]["job_state"] == "ready_to_route"

    assert (
        main(
            [
                "--config",
                str(config_path),
                "reviews",
                "apply-decisions",
                "--run-id",
                run_id,
                "--reviewer",
                "cli-batch",
                "--decisions-json",
                f'[{{"job_id":"{job_id}","action":"approve_for_routing","field_corrections":{{"full_name":"CLI Batch"}}}}]',
                "--json",
            ]
        )
        == 0
    )
    imported = json.loads(capsys.readouterr().out)
    assert imported["import"]["schema"] == "business-card-watchdog.review-decisions-import.v1"
    assert imported["results"][0]["job_state"] == "ready_to_route"

    assert (
        main(
            [
                "--config",
                str(config_path),
                "mcp-call",
                "business_card_watchdog_next_actions",
                "--arguments-json",
                f'{{"run_id": "{run_id}"}}',
            ]
        )
        == 0
    )
    next_actions = json.loads(capsys.readouterr().out)
    assert next_actions["actions"][0]["action"] == "plan_sink_lookup"


def test_cli_jobs_review_records_submission(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "config.toml"
    data_dir = tmp_path / "data"
    write_config(config_path, data_dir)
    run_id, job_id = make_recorded_run(AppConfig(config_path=config_path, data_dir=data_dir))

    assert (
        main(
            [
                "--config",
                str(config_path),
                "jobs",
                "review",
                job_id,
                "--run-id",
                run_id,
                "--reviewer",
                "cli-test",
                "--action",
                "approve_for_routing",
                "--field-corrections-json",
                '{"full_name": "CLI Fixture"}',
                "--crop-selection-json",
                '{"crop_id": "c01"}',
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["job"]["state"] == "ready_to_route"
    assert payload["submission"]["reviewer"] == "cli-test"

    assert (
        main(
            [
                "--config",
                str(config_path),
                "actions",
                "run-next",
                "--run-id",
                run_id,
                "--limit",
                "2",
                "--json",
            ]
        )
        == 0
    )
    actions = json.loads(capsys.readouterr().out)
    assert [item["action"] for item in actions["executed"]] == [
        "plan_sink_lookup",
        "prepare_sink_lookup_adapter",
    ]
    assert actions["phase_report_before"]["schema"] == "business-card-watchdog.phase-report.v1"
    assert actions["phase_report_after"]["schema"] == "business-card-watchdog.phase-report.v1"


def test_cli_jobs_review_supports_request_enrichment_action(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "config.toml"
    data_dir = tmp_path / "data"
    write_config(config_path, data_dir)
    run_id, job_id = make_recorded_run(AppConfig(config_path=config_path, data_dir=data_dir))

    assert (
        main(
            [
                "--config",
                str(config_path),
                "jobs",
                "review",
                job_id,
                "--run-id",
                run_id,
                "--action",
                "request_enrichment",
                "--notes",
                "needs corroboration",
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["job"]["state"] == "needs_review"
    assert payload["submission"]["action"] == "request_enrichment"


def test_cli_jobs_review_approves_enrichment_merge(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "config.toml"
    data_dir = tmp_path / "data"
    write_config(config_path, data_dir)
    run_id, job_id = make_recorded_run(AppConfig(config_path=config_path, data_dir=data_dir))
    artifact_dir = data_dir / "runs" / run_id / "artifacts" / job_id
    (artifact_dir / "contact_candidate.json").write_text(
        json.dumps(build_contact_candidate({"full_name": "Ada Lovelace"}), indent=2),
        encoding="utf-8",
    )
    (artifact_dir / "enrichment_result.json").write_text(
        json.dumps(
            {
                "schema": "business-card-watchdog.enrichment-result.v1",
                "merge_proposals": [
                    {
                        "field": "notes",
                        "value": "Public-web corroboration candidate: https://example.test/ada",
                        "source": "public_web",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    assert (
        main(
            [
                "--config",
                str(config_path),
                "jobs",
                "review",
                job_id,
                "--run-id",
                run_id,
                "--action",
                "approve_enrichment_merge",
                "--approved-enrichment-fields-json",
                '["notes"]',
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["job"]["state"] == "ready_to_route"
    assert payload["submission"]["approved_enrichment_fields"] == ["notes"]


def test_cli_jobs_review_resolves_duplicate(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "config.toml"
    data_dir = tmp_path / "data"
    write_config(config_path, data_dir)
    run_id, job_id = make_recorded_run(AppConfig(config_path=config_path, data_dir=data_dir))
    artifact_dir = data_dir / "runs" / run_id / "artifacts" / job_id
    (artifact_dir / "duplicate_assessment.json").write_text(
        '{"schema": "business-card-watchdog.duplicate-assessment.v1", "state": "strong_duplicate"}\n',
        encoding="utf-8",
    )

    assert (
        main(
            [
                "--config",
                str(config_path),
                "jobs",
                "review",
                job_id,
                "--run-id",
                run_id,
                "--action",
                "resolve_duplicate",
                "--duplicate-resolution-json",
                '{"decision": "create_new", "reason": "operator confirmed separate person"}',
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["job"]["state"] == "ready_to_route"
    assert payload["submission"]["duplicate_resolution"]["decision"] == "create_new"


def test_cli_sinks_check_is_dry_run_and_non_mutating(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "config.toml"
    write_config(config_path, tmp_path / "data")

    assert main(["--config", str(config_path), "sinks", "check", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["dry_run"] is True
    assert {sink["status"] for sink in payload["sinks"]} == {"ready"}


def test_cli_sinks_plan_writes_artifact(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "config.toml"
    data_dir = tmp_path / "data"
    config_path.write_text(
        f'data_dir = "{data_dir}"\n'
        "[watch]\ninputs = []\n"
        "[sink]\ndry_run = true\ngoogle_contacts = true\nodoo = true\n"
        "[routing]\nrules = [{ match = \"email_domain\", value = \"*\", sinks = [\"google_contacts\"] }]\n",
        encoding="utf-8",
    )
    run_id, job_id = make_recorded_run(AppConfig(config_path=config_path, data_dir=data_dir))

    assert main(["--config", str(config_path), "sinks", "plan", job_id, "--run-id", run_id, "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["plan"]["schema"] == "business-card-watchdog.sink-plan.v1"
    assert payload["plan"]["state"] == "dry_run"


def test_cli_sinks_lookup_plan_writes_zero_network_artifact(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "config.toml"
    data_dir = tmp_path / "data"
    config_path.write_text(
        f'data_dir = "{data_dir}"\n'
        "[watch]\ninputs = []\n"
        "[sink]\ndry_run = true\ngoogle_contacts = true\n"
        "[routing]\nrules = [{ match = \"email_domain\", value = \"*\", sinks = [\"google_contacts\"] }]\n",
        encoding="utf-8",
    )
    run_id, job_id = make_recorded_run(AppConfig(config_path=config_path, data_dir=data_dir))

    assert main(["--config", str(config_path), "sinks", "lookup-plan", job_id, "--run-id", run_id, "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["lookup_plan"]["schema"] == "business-card-watchdog.sink-lookup-plan.v1"
    assert payload["lookup_plan"]["network_calls_made"] == 0
    assert payload["lookup_plan"]["lookups"][0]["sink"] == "google_contacts"


def test_cli_sinks_apply_preflight_is_zero_write(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "config.toml"
    data_dir = tmp_path / "data"
    config_path.write_text(
        f'data_dir = "{data_dir}"\n'
        "[watch]\ninputs = []\n"
        "[sink]\ndry_run = true\ngoogle_contacts = true\n",
        encoding="utf-8",
    )
    run_id, job_id = make_recorded_run(AppConfig(config_path=config_path, data_dir=data_dir))

    assert main(["--config", str(config_path), "sinks", "apply-preflight", job_id, "--run-id", run_id, "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["preflight"]["schema"] == "business-card-watchdog.sink-apply-preflight.v1"
    assert payload["preflight"]["state"] == "preview"
    assert payload["preflight"]["writes_attempted"] == 0

    assert (
        main(
            [
                "--config",
                str(config_path),
                "sinks",
                "apply-preflight",
                job_id,
                "--run-id",
                run_id,
                "--apply",
                "--json",
            ]
        )
        == 0
    )
    blocked = json.loads(capsys.readouterr().out)
    assert blocked["preflight"]["state"] == "blocked"


def test_cli_sinks_apply_decision_writes_zero_write_artifact(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "config.toml"
    data_dir = tmp_path / "data"
    config_path.write_text(
        f'data_dir = "{data_dir}"\n'
        "[watch]\ninputs = []\n"
        "[sink]\ndry_run = true\ngoogle_contacts = true\n",
        encoding="utf-8",
    )
    run_id, job_id = make_recorded_run(AppConfig(config_path=config_path, data_dir=data_dir))

    assert (
        main(
            [
                "--config",
                str(config_path),
                "sinks",
                "apply-decision",
                job_id,
                "--run-id",
                run_id,
                "--decision",
                "approve",
                "--reviewer",
                "cli-test",
                "--reason",
                "pilot approved",
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["decision"]["schema"] == "business-card-watchdog.sink-apply-decision.v1"
    assert payload["decision"]["state"] == "approved_for_apply"
    assert payload["decision"]["writes_attempted"] == 0

    assert (
        main(
            [
                "--config",
                str(config_path),
                "sinks",
                "apply",
                job_id,
                "--run-id",
                run_id,
                "--apply",
                "--simulate",
                "--json",
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    assert result["result"]["schema"] == "business-card-watchdog.sink-apply-result.v1"
    assert result["result"]["state"] == "mock_applied"
    assert result["result"]["writes_attempted"] == 0
    assert result["result"]["readback"][0]["simulated"] is True

    assert (
        main(
            [
                "--config",
                str(config_path),
                "sinks",
                "apply-pilot-readiness",
                job_id,
                "--run-id",
                run_id,
                "--sink",
                "google_contacts",
                "--json",
            ]
        )
        == 0
    )
    readiness = json.loads(capsys.readouterr().out)
    assert readiness["readiness"]["schema"] == "business-card-watchdog.sink-apply-pilot-readiness.v1"
    assert readiness["readiness"]["selected_sink"] == "google_contacts"
    assert readiness["readiness"]["writes_attempted"] == 0

    assert (
        main(
            [
                "--config",
                str(config_path),
                "sinks",
                "apply-pilot-bundle",
                job_id,
                "--run-id",
                run_id,
                "--sink",
                "google_contacts",
                "--operator",
                "cli-test",
                "--json",
            ]
        )
        == 0
    )
    pilot_bundle = json.loads(capsys.readouterr().out)
    assert pilot_bundle["bundle"]["schema"] == "business-card-watchdog.sink-apply-pilot-bundle.v1"
    assert pilot_bundle["bundle"]["sink"] == "google_contacts"
    assert pilot_bundle["bundle"]["writes_attempted"] == 0

    assert (
        main(
            [
                "--config",
                str(config_path),
                "sinks",
                "select-live-target",
                job_id,
                "--run-id",
                run_id,
                "--sink",
                "google_contacts",
                "--operator",
                "cli-test",
                "--scope",
                "all",
                "--json",
            ]
        )
        == 0
    )
    selected_target = json.loads(capsys.readouterr().out)
    assert selected_target["target"]["schema"] == "business-card-watchdog.selected-live-target.v1"
    assert selected_target["target"]["scope_allows"]["lookup"] is True
    assert selected_target["target"]["scope_allows"]["write"] is True

    assert (
        main(
            [
                "--config",
                str(config_path),
                "sinks",
                "write-pilot",
                job_id,
                "--run-id",
                run_id,
                "--sink",
                "google_contacts",
                "--approved-by",
                "cli-test",
                "--json",
            ]
        )
        == 0
    )
    write_pilot = json.loads(capsys.readouterr().out)
    assert write_pilot["pilot"]["schema"] == "business-card-watchdog.sink-write-pilot.v1"
    assert write_pilot["pilot"]["writes_attempted"] == 0
    assert write_pilot["result"]["state"] == "mock_applied"

    assert (
        main(
            [
                "--config",
                str(config_path),
                "sinks",
                "adapter-request",
                job_id,
                "--run-id",
                run_id,
                "--phase",
                "readback",
                "--json",
            ]
        )
        == 0
    )
    capsys.readouterr()

    assert (
        main(
            [
                "--config",
                str(config_path),
                "sinks",
                "readback-pilot",
                job_id,
                "--run-id",
                run_id,
                "--sink",
                "google_contacts",
                "--approved-by",
                "cli-test",
                "--json",
            ]
        )
        == 0
    )
    readback = json.loads(capsys.readouterr().out)
    assert readback["pilot"]["schema"] == "business-card-watchdog.sink-readback-pilot.v1"
    assert readback["pilot"]["writes_attempted"] == 0
    assert readback["pilot"]["network_calls_made"] == 0

    assert (
        main(
            [
                "--config",
                str(config_path),
                "sinks",
                "apply-pilot-report",
                job_id,
                "--run-id",
                run_id,
                "--json",
            ]
        )
        == 0
    )
    report = json.loads(capsys.readouterr().out)
    assert report["report"]["schema"] == "business-card-watchdog.sink-apply-pilot-report.v1"
    assert report["report"]["state"] == "complete"
    assert report["report"]["writes_attempted"] == 0


def test_cli_sinks_adapter_request_writes_blocked_contract(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "config.toml"
    data_dir = tmp_path / "data"
    config_path.write_text(
        f'data_dir = "{data_dir}"\n'
        "[watch]\ninputs = []\n"
        "[sink]\ndry_run = true\ngoogle_contacts = true\n",
        encoding="utf-8",
    )
    run_id, job_id = make_recorded_run(AppConfig(config_path=config_path, data_dir=data_dir))

    assert (
        main(
            [
                "--config",
                str(config_path),
                "sinks",
                "adapter-request",
                job_id,
                "--run-id",
                run_id,
                "--phase",
                "lookup",
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["request"]["schema"] == "business-card-watchdog.sink-adapter-request.v1"
    assert payload["request"]["phase"] == "lookup"
    assert payload["request"]["network_calls_made"] == 0
    assert payload["request"]["requests"][0]["status"] == "blocked"


def test_cli_sinks_lookup_result_writes_zero_network_artifact(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "config.toml"
    data_dir = tmp_path / "data"
    config_path.write_text(
        f'data_dir = "{data_dir}"\n'
        "[watch]\ninputs = []\n"
        "[sink]\ndry_run = true\ngoogle_contacts = true\n",
        encoding="utf-8",
    )
    run_id, job_id = make_recorded_run(AppConfig(config_path=config_path, data_dir=data_dir))

    assert (
        main(
            [
                "--config",
                str(config_path),
                "sinks",
                "lookup-result",
                job_id,
                "--run-id",
                run_id,
                "--matches-by-sink-json",
                '{"google_contacts": [{"resource_id": "people/c123", "confidence": 0.91, "basis": ["email"]}]}',
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["result"]["schema"] == "business-card-watchdog.sink-lookup-result.v1"
    assert payload["result"]["state"] == "possible_duplicate"
    assert payload["result"]["network_calls_made"] == 0
    assert payload["result"]["match_count"] == 1

    assert (
        main(
            [
                "--config",
                str(config_path),
                "sinks",
                "lookup-smoke-handoff",
                job_id,
                "--run-id",
                run_id,
                "--sink",
                "google_contacts",
                "--approved-by",
                "cli-operator",
                "--json",
            ]
        )
        == 0
    )
    handoff = json.loads(capsys.readouterr().out)
    assert handoff["handoff"]["schema"] == "business-card-watchdog.sink-lookup-smoke-handoff.v1"
    assert handoff["handoff"]["writes_attempted"] == 0
    assert handoff["handoff"]["network_calls_made"] == 0

    assert (
        main(
            [
                "--config",
                str(config_path),
                "sinks",
                "lookup-pilot",
                job_id,
                "--run-id",
                run_id,
                "--sink",
                "google_contacts",
                "--approved-by",
                "cli-operator",
                "--matches-json",
                '[{"resource_id": "people/c456", "confidence": 0.93, "basis": ["email"]}]',
                "--json",
            ]
        )
        == 0
    )
    pilot = json.loads(capsys.readouterr().out)
    assert pilot["pilot"]["schema"] == "business-card-watchdog.sink-lookup-pilot.v1"
    assert pilot["pilot"]["approved_by"] == "cli-operator"
    assert pilot["pilot"]["network_calls_made"] == 0
    assert pilot["pilot"]["writes_attempted"] == 0

    assert (
        main(
            [
                "--config",
                str(config_path),
                "sinks",
                "assess-duplicates",
                job_id,
                "--run-id",
                run_id,
                "--json",
            ]
        )
        == 0
    )
    assessment = json.loads(capsys.readouterr().out)
    assert assessment["assessment"]["schema"] == "business-card-watchdog.duplicate-assessment.v1"
    assert assessment["assessment"]["state"] == "strong_duplicate"
    assert assessment["job"]["state"] == "needs_review"


def test_cli_enrichment_check_blocks_when_not_enabled(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "config.toml"
    write_config(config_path, tmp_path / "data")

    assert main(["--config", str(config_path), "enrichment", "check", "--mode", "api", "--json"]) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["checks"][0]["status"] == "blocked"
    assert "disabled" in payload["checks"][0]["reason"]


def test_cli_enrichment_request_writes_public_web_artifacts(tmp_path: Path, monkeypatch, capsys) -> None:
    config_path = tmp_path / "config.toml"
    data_dir = tmp_path / "data"
    source_dir = tmp_path / "cards"
    write_synthetic_image(source_dir / "card.png")
    config_path.write_text(
        f'data_dir = "{data_dir}"\ncache_dir = "{tmp_path / "cache"}"\n'
        "[watch]\ninputs = []\n"
        "[enrichment]\nenabled = true\n",
        encoding="utf-8",
    )
    config = AppConfig(
        config_path=config_path,
        data_dir=data_dir,
        cache_dir=tmp_path / "cache",
        prefilter=PrefilterConfig(process_uncertain=True),
        enrichment=EnrichmentConfig(enabled=True),
    )
    orchestrator = BatchOrchestrator(config)
    monkeypatch.setattr(orchestrator, "adapter", SyntheticSkillAdapter())
    run_dir = orchestrator.process_source(str(source_dir), dry_run=True, workers=1)
    job = next(iter(latest_jobs_by_id(run_dir / "jobs.jsonl").values()))

    assert (
        main(
            [
                "--config",
                str(config_path),
                "enrichment",
                "request",
                job["job_id"],
                "--run-id",
                run_dir.name,
                "--public-web-results-json",
                '[{"title":"Fixture Labs","url":"https://example.test","snippet":"fixture@example.test"}]',
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["result"]["network_calls_made"] == 0

    assert (
        main(
            [
                "--config",
                str(config_path),
                "enrichment",
                "public-web-handoff",
                job["job_id"],
                "--run-id",
                run_dir.name,
                "--json",
            ]
        )
        == 0
    )
    handoff_payload = json.loads(capsys.readouterr().out)
    assert handoff_payload["handoff"]["schema"] == "business-card-watchdog.enrichment-public-web-search-handoff.v1"
    assert handoff_payload["handoff"]["network_calls_made"] == 0
    assert handoff_payload["handoff"]["result_import"]["mcp_tool"] == "business_card_watchdog_public_web_enrichment_results"

    assert (
        main(
            [
                "--config",
                str(config_path),
                "enrichment",
                "public-web-results",
                job["job_id"],
                "--run-id",
                run_dir.name,
                "--searched-by",
                "cli-search",
                "--results-json",
                '[{"title":"Fixture Labs","url":"https://example.test","snippet":"fixture@example.test"}]',
                "--json",
            ]
        )
        == 0
    )
    result_payload = json.loads(capsys.readouterr().out)
    assert result_payload["public_web_result"]["schema"] == "business-card-watchdog.enrichment-public-web-result.v1"
    assert result_payload["public_web_result"]["searched_by"] == "cli-search"
    assert result_payload["public_web_result"]["network_calls_made"] == 0


def test_cli_enrichment_request_writes_paid_provider_request_without_call(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "config.toml"
    data_dir = tmp_path / "data"
    keys_path = tmp_path / "API-keys.env"
    keys_path.write_text("APOLLO_API_KEY=fixture-value-redacted\n", encoding="utf-8")
    config_path.write_text(
        f'data_dir = "{data_dir}"\n'
        "[watch]\ninputs = []\n"
        "[enrichment]\nenabled = true\nallow_paid_api = true\n"
        f'api_keys_env = "{keys_path}"\n'
        "[enrichment.providers.apollo]\nenabled = true\napi_key_env = \"APOLLO_API_KEY\"\n",
        encoding="utf-8",
    )
    run_id, job_id = make_recorded_run(
        AppConfig(
            config_path=config_path,
            data_dir=data_dir,
            enrichment=EnrichmentConfig(
                enabled=True,
                allow_paid_api=True,
                api_keys_env=keys_path,
                apollo=EnrichmentProviderConfig(enabled=True),
            ),
        )
    )
    artifact_dir = data_dir / "runs" / run_id / "artifacts" / job_id
    (artifact_dir / "contact_candidate.json").write_text(
        json.dumps(
            build_contact_candidate(
                {
                    "full_name": "Ada Lovelace",
                    "organization": "Example Labs",
                    "email": "ada@example.test",
                }
            )
        )
        + "\n",
        encoding="utf-8",
    )

    assert (
        main(
            [
                "--config",
                str(config_path),
                "enrichment",
                "request",
                job_id,
                "--run-id",
                run_id,
                "--mode",
                "api",
                "--allow-paid-enrichment",
                "--provider-results-json",
                '[{"person":{"name":"Ada Lovelace","email":"ada@example.test","title":"Principal"},"organization":{"name":"Example Labs"}}]',
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["provider_request"]["schema"] == "business-card-watchdog.enrichment-provider-request.v1"
    assert payload["provider_request"]["status"] == "prepared"
    assert payload["provider_request"]["network_calls_made"] == 0
    assert payload["provider_result"]["schema"] == "business-card-watchdog.enrichment-provider-result.v1"
    assert payload["provider_result"]["paid_api_calls_attempted"] == 0
    assert "secret" not in json.dumps(payload)

    assert (
        main(
            [
                "--config",
                str(config_path),
                "enrichment",
                "provider-handoff",
                job_id,
                "--run-id",
                run_id,
                "--json",
            ]
        )
        == 0
    )
    handoff_payload = json.loads(capsys.readouterr().out)
    assert handoff_payload["handoff"]["schema"] == "business-card-watchdog.enrichment-provider-handoff.v1"
    assert handoff_payload["handoff"]["paid_api_calls_attempted"] == 0
    assert handoff_payload["handoff"]["result_import"]["mcp_tool"] == "business_card_watchdog_provider_enrichment_results"
    assert "secret" not in json.dumps(handoff_payload)

    assert (
        main(
            [
                "--config",
                str(config_path),
                "enrichment",
                "provider-results",
                job_id,
                "--run-id",
                run_id,
                "--provider",
                "apollo",
                "--submitted-by",
                "cli-agent",
                "--results-json",
                '[{"person":{"name":"Ada Lovelace","email":"ada@example.test","title":"Principal"},"organization":{"name":"Example Labs"}}]',
                "--json",
            ]
        )
        == 0
    )
    result_payload = json.loads(capsys.readouterr().out)
    assert result_payload["provider_result"]["schema"] == "business-card-watchdog.enrichment-provider-result.v1"
    assert result_payload["provider_result"]["submitted_by"] == "cli-agent"
    assert result_payload["provider_result"]["paid_api_calls_attempted"] == 0


def test_cli_doctor_reports_user_scope_checks(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "config.toml"
    write_config(config_path, tmp_path / "data")

    assert main(["--config", str(config_path), "doctor", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert any(check["name"] == "runs_dir" for check in payload["checks"])


def test_cli_service_install_status_uninstall_user_scope(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg-config"))
    config_path = tmp_path / "config.toml"
    write_config(config_path, tmp_path / "data")

    assert main(["--config", str(config_path), "service", "install", "--json"]) == 0
    installed = json.loads(capsys.readouterr().out)
    assert installed["installed"] is True
    assert Path(installed["unit_path"]) == service_unit_path()
    assert service_unit_path().read_text(encoding="utf-8").count("ExecStart=") == 1

    assert main(["--config", str(config_path), "service", "status", "--json"]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["installed"] is True

    assert main(["--config", str(config_path), "service", "uninstall", "--json"]) == 0
    uninstalled = json.loads(capsys.readouterr().out)
    assert uninstalled["installed"] is False

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
from business_card_watchdog.service import BusinessCardService
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


def test_cli_status_reports_command_map_text_and_json(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "config.toml"
    data_dir = tmp_path / "data"
    write_config(config_path, data_dir)

    assert main(["--config", str(config_path), "status", "--json"]) in {0, 2}
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema"] == "business-card-watchdog.status.v1"
    assert payload["commands"]["runtime_readiness"] == "runtime-readiness --json"
    assert payload["commands"]["service_recovery"] == "service recovery --json"
    assert payload["commands"]["runs_list"] == "runs list --json"
    assert payload["safe_next_actions"][0]["action"] == "inspect_runtime_readiness"
    assert payload["writes_attempted"] == 0
    assert payload["network_calls_made"] == 0

    assert main(["--config", str(config_path), "status"]) in {0, 2}
    text = capsys.readouterr().out
    assert "Status:" in text
    assert "Commands:" in text
    assert "Runtime readiness: runtime-readiness --json" in text
    assert "Service recovery: service recovery --json" in text
    assert "Runs list: runs list --json" in text
    assert "Safe next actions: 3" in text
    assert "Stop conditions: 3" in text
    assert "Observed: writes=0 network=0" in text
    assert "{" not in text


def test_cli_operator_dashboard_reports_no_live_summary(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "config.toml"
    data_dir = tmp_path / "data"
    write_config(config_path, data_dir)
    run_id, _job_id = make_recorded_run(AppConfig(config_path=config_path, data_dir=data_dir))

    assert main(["--config", str(config_path), "operator-dashboard", "--run-id", run_id, "--json"]) in {0, 2}
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema"] == "business-card-watchdog.operator-dashboard.v1"
    assert payload["selected_run_id"] == run_id
    assert payload["commands"]["review_queue"] == f"reviews list --run-id {run_id} --state all --json"
    assert payload["commands"]["next_actions"] == f"actions next --run-id {run_id} --json"
    assert payload["commands"]["run_next_safe"] == f"actions run-next --run-id {run_id} --limit 10 --json"
    assert payload["commands"]["live_pilot_handoff"] == f"runs live-pilot-handoff {run_id} --no-write --json"
    assert payload["commands"]["live_pilot_validate_response"] == (
        f"runs live-pilot-validate-response {run_id} --response <operator-response> --json"
    )
    assert payload["review_counts"]["needs_review"] == 1
    assert payload["next_action_summary"]["by_action"] == {"review_contact": 1}
    assert payload["live_pilot_handoff_summary"]["action_counts"] == {"no_live_candidate": 1}
    assert payload["live_pilot_handoff_summary"]["operator_required_count"] == 0
    assert payload["writes_attempted"] == 0
    assert payload["network_calls_made"] == 0

    assert main(["--config", str(config_path), "actions", "next", "--run-id", run_id, "--json"]) == 0
    next_actions = json.loads(capsys.readouterr().out)
    assert next_actions["action_count"] == 1
    assert next_actions["actions"][0]["action"] == "review_contact"
    assert next_actions["actions"][0]["requires_explicit_operator_action"] is True

    assert main(["--config", str(config_path), "operator-dashboard", "--run-id", run_id]) in {0, 2}
    text = capsys.readouterr().out
    assert "Operator dashboard:" in text
    assert f"Selected run: {run_id}" in text
    assert f"Review queue: reviews list --run-id {run_id} --state all --json" in text
    assert f"Next actions: actions next --run-id {run_id} --json" in text
    assert "API routes:" in text
    assert f"Next actions: GET /actions/next?run_id={run_id}&limit=20" in text
    assert f"Live pilot handoff: GET /runs/{run_id}/live-pilot-handoff?write=false" in text
    assert f"Live pilot validate response: POST /runs/{run_id}/live-pilot-operator-response-validation" in text
    assert "MCP tools:" in text
    assert f"Operator dashboard: business_card_watchdog_operator_dashboard args=run_id={run_id}" in text
    assert f"Next actions: business_card_watchdog_next_actions args=limit=20, run_id={run_id}" in text
    assert f"Live pilot status: business_card_watchdog_live_pilot_status args=run_id={run_id}, write=False" in text
    assert (
        "Live pilot validate response: "
        f"business_card_watchdog_live_pilot_operator_response_validation "
        f"args=response=<operator-response>, run_id={run_id}"
    ) in text
    assert "Next actions: total=1 safe=0 explicit=1" in text
    assert "action=review_contact" in text
    assert "Live handoff: state=blocked operator_required=0 response_templates=0" in text
    assert f"Live pilot status: runs live-pilot-status {run_id} --no-write --json" in text
    assert (
        f"Live pilot validate response: runs live-pilot-validate-response {run_id} "
        "--response <operator-response> --json"
    ) in text
    assert "Observed: writes=0 network=0" in text
    assert "Stop conditions: 3" in text
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
    assert payload["commands"]["live_pilot_handoff"] == (
        f"bcw --config {config_path} runs live-pilot-handoff {run_id}"
    )
    assert payload["network_calls_made"] == 0
    assert payload["writes_attempted"] == 0

    assert main(["--config", str(config_path), "service", "recovery", "--run-id", run_id]) == 0
    text = capsys.readouterr().out
    assert "Service recovery:" in text
    assert f"Run: {run_id}" in text
    assert "Restart: systemctl --user restart business-card-watchdog.service" in text
    assert "Resume: bcw --config" in text
    assert f"Live pilot handoff: bcw --config {config_path} runs live-pilot-handoff {run_id}" in text
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
    candidate = payload["candidates"][0]
    assert candidate["commands"]["select_lookup_target"] == (
        f"sinks select-live-target {candidate['job_id']} --run-id {run_id} --sink google_contacts "
        "--operator <operator> --scope lookup --safety-confirmation <confirmation> --json"
    )
    assert payload["commands"]["live_readiness_audit"] == f"live-readiness-audit --run-id {run_id}"
    assert payload["commands"]["live_selection_requirements"] == f"live-selection-requirements --run-id {run_id}"
    assert payload["commands"]["live_pilot_handoff"] == f"runs live-pilot-handoff {run_id}"

    assert main(["--config", str(config_path), "live-target-candidates", "--run-id", run_id]) == 0
    text = capsys.readouterr().out
    assert "Live target candidates: 1" in text
    assert "sink=google_contacts" in text
    assert f"Inspect job: jobs show {candidate['job_id']} --run-id {run_id}" in text
    assert f"Lookup readiness: sinks lookup-readiness {candidate['job_id']} --run-id {run_id} --sink google_contacts" in text
    assert (
        f"Select lookup target: sinks select-live-target {candidate['job_id']} --run-id {run_id} "
        "--sink google_contacts --operator <operator> --scope lookup --safety-confirmation <confirmation> --json"
    ) in text
    assert f"Live readiness audit: live-readiness-audit --run-id {run_id}" in text
    assert f"Selection requirements: live-selection-requirements --run-id {run_id}" in text
    assert f"Live pilot handoff: runs live-pilot-handoff {run_id}" in text
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
    assert payload["commands"]["target_candidates"] == f"live-target-candidates --run-id {run_id}"
    assert payload["commands"]["selection_requirements"] == f"live-selection-requirements --run-id {run_id}"
    assert payload["commands"]["live_pilot_handoff"] == f"runs live-pilot-handoff {run_id}"

    assert main(["--config", str(config_path), "live-readiness-audit", "--run-id", run_id, "--no-write"]) == 0
    text = capsys.readouterr().out
    assert "Live readiness audit:" in text
    assert f"Run: {run_id}" in text
    assert f"Target candidates: live-target-candidates --run-id {run_id}" in text
    assert f"Selection requirements: live-selection-requirements --run-id {run_id}" in text
    assert f"Live pilot handoff: runs live-pilot-handoff {run_id}" in text
    assert "Runtime readiness: runtime-readiness --json" in text
    assert "{" not in text


def test_cli_live_selection_requirements_reports_text_and_json(tmp_path: Path, capsys) -> None:
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

    assert main(["--config", str(config_path), "live-selection-requirements", "--run-id", run_id, "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema"] == "business-card-watchdog.live-selection-requirements.v1"
    assert payload["candidate_count"] == 1
    assert Path(payload["requirements_path"]).exists()
    assert payload["network_calls_made"] == 0
    assert payload["writes_attempted"] == 0
    assert payload["operator_response_contract"]["creates_selected_live_target"] is False
    assert payload["operator_response_contract"]["required_fields"] == [
        "run_id",
        "job_id",
        "sink",
        "operator",
        "scope",
        "safety_confirmation",
    ]
    entry = payload["entries"][0]
    assert entry["operator_response_template"] == (
        f"run_id={run_id} job_id={entry['job_id']} sink=google_contacts "
        "operator=<operator> scope=lookup safety_confirmation=<confirmation>"
    )
    assert entry["commands"]["selection_packet"] == (
        f"sinks live-selection-packet {entry['job_id']} --run-id {run_id} --sink google_contacts --operator <operator>"
    )
    assert payload["commands"]["live_target_candidates"] == f"live-target-candidates --run-id {run_id}"
    assert payload["commands"]["live_readiness_audit"] == f"live-readiness-audit --run-id {run_id}"
    assert payload["commands"]["live_selection_requirements"] == f"live-selection-requirements --run-id {run_id}"
    assert payload["commands"]["live_pilot_handoff"] == f"runs live-pilot-handoff {run_id}"

    assert main(["--config", str(config_path), "live-selection-requirements", "--run-id", run_id, "--no-write"]) == 0
    text = capsys.readouterr().out
    assert "Live selection requirements:" in text
    assert f"Run: {run_id}" in text
    assert "target=none" in text
    assert "abandonment=none" in text
    assert "missing=operator,scope,safety_confirmation" in text
    assert (
        f"Selection packet: sinks live-selection-packet {entry['job_id']} --run-id {run_id} "
        "--sink google_contacts --operator <operator>"
    ) in text
    assert (
        f"Select target: sinks select-live-target {entry['job_id']} --run-id {run_id} "
        "--sink google_contacts --operator <operator> --scope lookup --safety-confirmation <confirmation> --json"
    ) in text
    assert (
        f"Operator response: run_id={run_id} job_id={entry['job_id']} sink=google_contacts "
        "operator=<operator> scope=lookup safety_confirmation=<confirmation>"
    ) in text
    assert f"Live target candidates: live-target-candidates --run-id {run_id}" in text
    assert f"Live readiness audit: live-readiness-audit --run-id {run_id}" in text
    assert f"Selection requirements: live-selection-requirements --run-id {run_id}" in text
    assert f"Live pilot handoff: runs live-pilot-handoff {run_id}" in text
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
    assert payload["existing_selected_target"]["identity"] is None
    assert payload["existing_selected_target"]["target_safety_confirmed"] is False
    assert payload["existing_selected_target"]["abandoned"] is False
    assert payload["existing_selected_target"]["replacement_requires_abandonment"] is False
    assert payload["existing_selected_target"]["can_select_replacement_now"] is True
    assert payload["existing_selected_target"]["abandon_command"] is None

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
                "--no-write",
            ]
        )
        == 0
    )
    text = capsys.readouterr().out
    assert "Live selection packet: blocked" in text
    assert f"Run: {run_id}" in text
    assert f"Job: {job_id}" in text
    assert "Existing target: exists=False identity=none" in text
    assert "Replacement: requires_abandonment=False can_select_now=True" in text
    assert "Create selected target: sinks select-live-target" in text
    assert "{" not in text


def test_cli_selected_target_audit_reports_existing_approval(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "config.toml"
    data_dir = tmp_path / "data"
    config_path.write_text(
        f'data_dir = "{data_dir}"\n[watch]\ninputs = []\n[sink]\ngoogle_contacts = true\n',
        encoding="utf-8",
    )
    config = AppConfig(
        config_path=config_path,
        data_dir=data_dir,
        sink=SinkConfig(google_contacts=True, dry_run=True),
    )
    run_id, job_id = make_recorded_run(config)
    service = BusinessCardService(config)
    service.build_sink_adapter_request_for_job(job_id=job_id, run_id=run_id, phase="lookup")
    service.select_live_target_for_job(
        job_id=job_id,
        run_id=run_id,
        sink="google_contacts",
        operator="tester",
        scope="lookup",
        safety_confirmation="fixture contact is safe for google contacts test profile",
    )

    assert (
        main(
            [
                "--config",
                str(config_path),
                "sinks",
                "selected-target-audit",
                job_id,
                "--run-id",
                run_id,
                "--scope",
                "lookup",
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema"] == "business-card-watchdog.selected-live-target-audit.v1"
    assert payload["state"] == "blocked"
    assert payload["selected_target_exists"] is True
    assert payload["writes_attempted"] == 0
    assert payload["network_calls_made"] == 0

    assert (
        main(
            [
                "--config",
                str(config_path),
                "sinks",
                "selected-target-audit",
                job_id,
                "--run-id",
                run_id,
                "--scope",
                "lookup",
                "--no-write",
            ]
        )
        == 0
    )
    audit_text = capsys.readouterr().out
    assert "Selected target audit: blocked" in audit_text
    assert f"Run: {run_id}" in audit_text
    assert f"Job: {job_id}" in audit_text
    assert "Scope: lookup" in audit_text
    assert "Sink: google_contacts" in audit_text
    assert "Operator: tester" in audit_text
    assert "safety_confirmed=True" in audit_text
    assert "Lookup smoke: sinks execute-lookup-smoke" in audit_text
    assert "Stop conditions:" in audit_text
    assert "{" not in audit_text

    assert (
        main(
            [
                "--config",
                str(config_path),
                "sinks",
                "live-pilot-closeout",
                job_id,
                "--run-id",
                run_id,
                "--json",
            ]
        )
        == 0
    )
    closeout = json.loads(capsys.readouterr().out)
    assert closeout["report"]["schema"] == "business-card-watchdog.live-pilot-closeout.v1"
    assert closeout["report"]["state"] == "incomplete"
    assert closeout["report"]["writes_attempted"] == 0
    assert Path(closeout["closeout_path"]).exists()
    assert closeout["report"]["commands"]["selected_target_audit"] == (
        f"sinks selected-target-audit {job_id} --run-id {run_id}"
    )
    assert closeout["report"]["commands"]["apply_pilot_report"] == (
        f"sinks apply-pilot-report {job_id} --run-id {run_id}"
    )
    assert closeout["report"]["commands"]["closeout"] == f"sinks live-pilot-closeout {job_id} --run-id {run_id}"

    assert (
        main(
            [
                "--config",
                str(config_path),
                "sinks",
                "live-pilot-closeout",
                job_id,
                "--run-id",
                run_id,
                "--no-write",
            ]
        )
        == 0
    )
    closeout_text = capsys.readouterr().out
    assert "Live pilot closeout: incomplete" in closeout_text
    assert f"Run: {run_id}" in closeout_text
    assert f"Job: {job_id}" in closeout_text
    assert "Scope: lookup" in closeout_text
    assert "Sink: google_contacts" in closeout_text
    assert "Selected target audit: state=blocked safety_confirmed=True" in closeout_text
    assert "Missing artifacts:" in closeout_text
    assert "Blocked reasons:" in closeout_text
    assert "Closeout: sinks live-pilot-closeout" in closeout_text
    assert "Stop conditions:" in closeout_text
    assert "{" not in closeout_text

    assert main(["--config", str(config_path), "runs", "live-pilot-status", run_id, "--json"]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["schema"] == "business-card-watchdog.live-pilot-status.v1"
    assert status["counts"]["selected_target_active"] == 1
    assert status["writes_attempted"] == 0
    assert Path(status["status_path"]).exists()
    assert status["commands"]["live_pilot_status"] == f"runs live-pilot-status {run_id}"
    assert status["commands"]["live_target_candidates"] == f"live-target-candidates --run-id {run_id}"
    assert status["commands"]["live_pilot_handoff"] == f"runs live-pilot-handoff {run_id}"
    assert status["commands"]["validate_operator_response"] == (
        f"runs live-pilot-validate-response {run_id} --response <operator-response> --json"
    )
    assert status["operator_response_contract"]["creates_selected_live_target"] is False
    assert status["entries"][0]["operator_response_template"] == (
        f"run_id={run_id} job_id={job_id} sink=google_contacts "
        "operator=tester scope=lookup safety_confirmation=<confirmation>"
    )
    assert status["entries"][0]["commands"]["selected_target_audit"] == (
        f"sinks selected-target-audit {job_id} --run-id {run_id}"
    )
    assert status["entries"][0]["commands"]["closeout"] == f"sinks live-pilot-closeout {job_id} --run-id {run_id}"
    target_identity = status["entries"][0]["selected_target_identity"]

    assert main(["--config", str(config_path), "runs", "live-pilot-status", run_id, "--no-write"]) == 0
    text_status = capsys.readouterr().out
    assert f"target={target_identity}" in text_status
    assert "abandonment=none" in text_status
    assert f"Live pilot handoff: runs live-pilot-handoff {run_id}" in text_status
    assert (
        f"Validate response: runs live-pilot-validate-response {run_id} "
        "--response <operator-response> --json"
    ) in text_status
    assert "{" not in text_status

    assert main(["--config", str(config_path), "runs", "live-pilot-handoff", run_id, "--json"]) == 0
    handoff = json.loads(capsys.readouterr().out)
    assert handoff["schema"] == "business-card-watchdog.live-pilot-handoff.v1"
    assert handoff["state"] == "ready_for_live_lookup_request"
    assert handoff["action_counts"]["request_live_lookup_smoke"] == 1
    assert handoff["writes_attempted"] == 0
    assert Path(handoff["handoff_path"]).exists()
    assert handoff["commands"]["live_pilot_handoff"] == f"runs live-pilot-handoff {run_id}"
    assert handoff["commands"]["validate_operator_response"] == (
        f"runs live-pilot-validate-response {run_id} --response <operator-response> --json"
    )
    assert handoff["commands"]["live_readiness_audit"] == f"live-readiness-audit --run-id {run_id}"
    assert handoff["operator_response_contract"]["creates_selected_live_target"] is False
    assert handoff["entries"][0]["operator_response_template"] == (
        f"run_id={run_id} job_id={job_id} sink=google_contacts "
        "operator=tester scope=lookup safety_confirmation=<confirmation>"
    )
    assert handoff["operator_response_template_count"] == 1
    assert handoff["operator_response_templates"][0]["template"] == (
        f"run_id={run_id} job_id={job_id} sink=google_contacts "
        "operator=tester scope=lookup safety_confirmation=<confirmation>"
    )
    assert handoff["operator_response_templates"][0]["command"] == (
        f"sinks execute-lookup-smoke {job_id} --run-id {run_id} --json"
    )
    assert handoff["entries"][0]["command"] == f"sinks execute-lookup-smoke {job_id} --run-id {run_id} --json"

    assert main(["--config", str(config_path), "runs", "live-pilot-handoff", run_id, "--no-write"]) == 0
    text_handoff = capsys.readouterr().out
    assert f"target={target_identity}" in text_handoff
    assert (
        f"Validate response: runs live-pilot-validate-response {run_id} "
        "--response <operator-response> --json"
    ) in text_handoff
    assert "abandonment=none" in text_handoff
    assert "Response templates: 1" in text_handoff
    assert (
        f"Operator response: run_id={run_id} job_id={job_id} sink=google_contacts "
        "operator=tester scope=lookup safety_confirmation=<confirmation>"
    ) in text_handoff
    assert "{" not in text_handoff

    response = (
        f"run_id={run_id} job_id={job_id} sink=google_contacts "
        "operator=tester scope=lookup safety_confirmation=fixture contact is safe for google contacts test profile"
    )
    assert (
        main(
            [
                "--config",
                str(config_path),
                "runs",
                "live-pilot-validate-response",
                run_id,
                "--response",
                response,
                "--json",
            ]
        )
        == 0
    )
    validation = json.loads(capsys.readouterr().out)
    assert validation["schema"] == "business-card-watchdog.live-pilot-operator-response-validation.v1"
    assert validation["state"] == "ready_to_select_live_target"
    assert validation["creates_selected_live_target"] is False
    assert validation["writes_attempted"] == 0
    assert validation["network_calls_made"] == 0
    assert validation["matching_template"]["job_id"] == job_id
    assert validation["select_target_command"].startswith(f"sinks select-live-target {job_id}")

    assert (
        main(
            [
                "--config",
                str(config_path),
                "runs",
                "live-pilot-validate-response",
                run_id,
                "--response",
                response,
            ]
        )
        == 0
    )
    validation_text = capsys.readouterr().out
    assert "State: ready_to_select_live_target" in validation_text
    assert "Creates selected target: False" in validation_text
    assert f"Select target: sinks select-live-target {job_id}" in validation_text
    assert "{" not in validation_text

    wrong_operator_response = (
        f"run_id={run_id} job_id={job_id} sink=google_contacts "
        "operator=other scope=lookup safety_confirmation=fixture contact is safe for google contacts test profile"
    )
    assert (
        main(
            [
                "--config",
                str(config_path),
                "runs",
                "live-pilot-validate-response",
                run_id,
                "--response",
                wrong_operator_response,
            ]
        )
        == 0
    )
    blocked_validation_text = capsys.readouterr().out
    assert "State: blocked" in blocked_validation_text
    assert "Mismatches: operator does not match current operator response template" in blocked_validation_text
    assert "Select target:" not in blocked_validation_text

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
                "--no-write",
            ]
        )
        == 0
    )
    active_packet = capsys.readouterr().out
    assert "Live selection packet: blocked" in active_packet
    assert f"identity={target_identity}" in active_packet
    assert "safety_confirmed=True abandoned=False" in active_packet
    assert "Replacement: requires_abandonment=True can_select_now=False" in active_packet
    assert "Abandon existing target: sinks abandon-live-pilot" in active_packet
    assert "{" not in active_packet

    assert (
        main(
            [
                "--config",
                str(config_path),
                "sinks",
                "abandon-live-pilot",
                job_id,
                "--run-id",
                run_id,
                "--operator",
                "tester",
                "--reason",
                "wrong target profile selected",
                "--json",
            ]
        )
        == 0
    )
    abandonment = json.loads(capsys.readouterr().out)
    assert abandonment["abandonment"]["schema"] == "business-card-watchdog.live-pilot-abandonment.v1"
    assert abandonment["abandonment"]["writes_attempted"] == 0
    assert Path(abandonment["abandonment_path"]).exists()

    assert main(["--config", str(config_path), "runs", "live-pilot-status", run_id, "--no-write"]) == 0
    abandoned_status = capsys.readouterr().out
    assert f"target={target_identity}" in abandoned_status
    assert f"abandonment={target_identity}" in abandoned_status
    assert "{" not in abandoned_status

    assert main(["--config", str(config_path), "runs", "live-pilot-handoff", run_id, "--no-write"]) == 0
    abandoned_handoff = capsys.readouterr().out
    assert f"target={target_identity}" in abandoned_handoff
    assert f"abandonment={target_identity}" in abandoned_handoff
    assert "{" not in abandoned_handoff


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
    assert phase_report["commands"]["live_pilot_handoff"] == f"runs live-pilot-handoff {run_id}"
    assert phase_report["phases"][2]["phase"] == "review"
    assert phase_report["phases"][2]["counts"]["blocked"] == 1
    assert main(["--config", str(config_path), "runs", "phase-report", run_id]) == 0
    phase_text = capsys.readouterr().out
    assert f"Run: {run_id}" in phase_text
    assert "Status: 1 blocked phases; 0 explicit-required phases; review workbook preview not_started" in phase_text
    assert "Review workbook preview: not_started" in phase_text
    assert "Blocked phases: review=1" in phase_text
    assert f"Live pilot handoff: runs live-pilot-handoff {run_id}" in phase_text
    assert "{" not in phase_text

    assert main(["--config", str(config_path), "runs", "pilot-readiness", run_id, "--json"]) == 0
    readiness_report = json.loads(capsys.readouterr().out)
    assert readiness_report["schema"] == "business-card-watchdog.pilot-readiness-report.v1"
    assert readiness_report["state"] == "explicit_operator_required"
    assert readiness_report["blocked_job_ids"] == [job_id]
    assert readiness_report["commands"]["live_pilot_handoff"] == f"runs live-pilot-handoff {run_id}"
    assert main(["--config", str(config_path), "runs", "pilot-readiness", run_id]) == 0
    readiness_text = capsys.readouterr().out
    assert f"Run: {run_id}" in readiness_text
    assert "Readiness: ready_for_write_pilot=0 safe_auto_available=0 explicit_operator_required=1" in readiness_text
    assert "Pilot evidence: write_complete=0 readback_complete=0 pilot_report_complete=0" in readiness_text
    assert f"Live pilot handoff: runs live-pilot-handoff {run_id}" in readiness_text
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
    assert next_actions["actions"][0]["safe_to_auto_continue"] is True
    assert next_actions["actions"][0]["requires_explicit_operator_action"] is False


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
    assert actions["writes_attempted"] == 0
    assert actions["network_calls_made"] == 0
    assert "plan_sink_lookup" in actions["safe_auto_actions"]
    assert "execute_sink_write_pilot" in actions["explicit_operator_actions"]
    assert all(item["safe_to_auto_continue"] is True for item in actions["executed"])
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
                "apply-pilot-bundle",
                job_id,
                "--run-id",
                run_id,
                "--sink",
                "google_contacts",
                "--operator",
                "cli-test",
            ]
        )
        == 0
    )
    bundle_text = capsys.readouterr().out
    assert "Apply pilot bundle:" in bundle_text
    assert f"Run: {run_id}" in bundle_text
    assert f"Job: {job_id}" in bundle_text
    assert "Sink: google_contacts" in bundle_text
    assert "Operator: cli-test" in bundle_text
    assert "Mock pilot:" in bundle_text
    assert "Live pilot:" in bundle_text
    assert "Missing requirements:" in bundle_text
    assert "Live write: sinks write-pilot" in bundle_text
    assert "Stop conditions:" in bundle_text
    assert "{" not in bundle_text

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
                "--safety-confirmation",
                "fixture contact is safe for google contacts test profile",
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
            ]
        )
        == 0
    )
    text = capsys.readouterr().out
    assert "Apply pilot report: complete" in text
    assert f"Run: {run_id}" in text
    assert f"Job: {job_id}" in text
    assert "Evidence: readiness=ready_for_mock_apply apply_result=mock_applied readback_request=blocked" in text
    assert "Observed: writes=0 network=0" in text
    assert "Sinks: 1" in text
    assert "google_contacts: write=mock_written" in text
    assert "readback=verified" in text
    assert "readback_matched=True" in text
    assert "Missing artifacts: 0" in text
    assert "Consistency errors: 0" in text
    assert "{" not in text


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
                "lookup-smoke-handoff",
                job_id,
                "--run-id",
                run_id,
                "--sink",
                "google_contacts",
                "--approved-by",
                "cli-operator",
            ]
        )
        == 0
    )
    handoff_text = capsys.readouterr().out
    assert "Lookup smoke handoff:" in handoff_text
    assert f"Run: {run_id}" in handoff_text
    assert f"Job: {job_id}" in handoff_text
    assert "Sink: google_contacts" in handoff_text
    assert "Approved by: cli-operator" in handoff_text
    assert "Read only: True" in handoff_text
    assert "Missing requirements:" in handoff_text
    assert "Live lookup pilot: sinks lookup-pilot" in handoff_text
    assert "Stop conditions:" in handoff_text
    assert "{" not in handoff_text

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

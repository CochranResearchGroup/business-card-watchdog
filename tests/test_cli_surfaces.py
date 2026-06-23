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

from synthetic_fixtures import (
    SyntheticSkillAdapter,
    latest_jobs_by_id,
    write_multi_card_image,
    write_synthetic_image,
)
from test_service import make_recorded_run, project_gws_route_contact


def write_config(path: Path, data_dir: Path) -> None:
    path.write_text(f'data_dir = "{data_dir}"\n[watch]\ninputs = []\n', encoding="utf-8")


def write_qr_image(path: Path, payload: str) -> Path:
    pytest = __import__("pytest")
    cv2 = pytest.importorskip("cv2")
    encoder = cv2.QRCodeEncoder_create()
    image = encoder.encode(payload)
    image = cv2.resize(image, (290, 290), interpolation=cv2.INTER_NEAREST)
    image = cv2.copyMakeBorder(image, 40, 40, 40, 40, cv2.BORDER_CONSTANT, value=255)
    path.parent.mkdir(parents=True, exist_ok=True)
    assert cv2.imwrite(str(path), image)
    return path


def test_cli_has_mcp_stdio_command() -> None:
    args = build_parser().parse_args(["mcp-stdio"])

    assert args.command == "mcp-stdio"


def test_cli_watch_accepts_scoped_input_refs() -> None:
    args = build_parser().parse_args(["watch", "--once", "--dry-run", "--input-ref", "input_1", "--limit", "1"])

    assert args.command == "watch"
    assert args.input_ref == ["input_1"]
    assert args.limit == 1


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
    assert "Safe next actions:" in text
    assert "run_fixture_review_routing_drill: drills review-routing" in text
    assert "Stop conditions: 3" in text
    assert "{" not in text


def test_cli_status_reports_command_map_text_and_json(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "config.toml"
    data_dir = tmp_path / "data"
    write_config(config_path, data_dir)

    assert main(["--config", str(config_path), "status", "--json"]) in {0, 2}
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema"] == "business-card-watchdog.status.v1"
    assert payload["commands"]["runtime_readiness"] == "runtime-readiness --json"
    assert payload["commands"]["offline_pilot_gap_audit"] == "offline-pilot-gap-audit --json"
    assert payload["commands"]["operator_selected_live_smoke_preflight"] == (
        "operator-selected-live-smoke-preflight --json"
    )
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
    assert "Offline pilot gap audit: offline-pilot-gap-audit --json" in text
    assert "Operator-selected live smoke preflight: operator-selected-live-smoke-preflight --json" in text
    assert "Service recovery: service recovery --json" in text
    assert "Watch backlog preflight: watch-backlog-preflight --json" in text
    assert "Watch dry-run selection handoff: watch-dry-run-selection-handoff --json" in text
    assert "Runs list: runs list --json" in text
    assert "Safe next actions: 6" in text
    assert "Stop conditions: 3" in text
    assert "Observed: writes=0 network=0" in text
    assert "{" not in text


def test_cli_offline_pilot_gap_audit_reports_remaining_boundaries(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "config.toml"
    data_dir = tmp_path / "data"
    write_config(config_path, data_dir)

    assert main(["--config", str(config_path), "offline-pilot-gap-audit", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["schema"] == "business-card-watchdog.offline-pilot-gap-audit.v1"
    assert payload["state"] == "ready_for_live_operator_boundary"
    assert payload["recommended_next_slice"] == "operator_selected_live_smoke"
    assert payload["coverage"]["missing_doc_count"] == 0
    assert payload["writes_attempted"] == 0
    assert payload["network_calls_made"] == 0
    assert Path(payload["audit_path"]).exists()

    assert main(["--config", str(config_path), "offline-pilot-gap-audit", "--no-write"]) == 0
    text = capsys.readouterr().out
    assert "Offline pilot gap audit: ready_for_live_operator_boundary" in text
    assert "Remaining boundaries:" in text
    assert "operator_selected_live_smoke" in text
    assert "{" not in text


def test_cli_operator_live_pilot_readiness_packet_reports_ready_boundary(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "config.toml"
    data_dir = tmp_path / "data"
    write_config(config_path, data_dir)

    assert main(["--config", str(config_path), "drills", "review-routing", "--json"]) == 0
    routing_drill = json.loads(capsys.readouterr().out)
    run_id = routing_drill["run_id"]

    assert (
        main(
            [
                "--config",
                str(config_path),
                "operator-live-pilot-readiness-packet",
                "--run-id",
                run_id,
                "--sink",
                "google_contacts",
                "--json",
            ]
        )
        == 0
    )
    packet = json.loads(capsys.readouterr().out)
    assert packet["schema"] == "business-card-watchdog.operator-live-pilot-readiness-packet.v1"
    assert packet["state"] == "ready_for_operator_response"
    assert packet["ready_entry_count"] == 1
    assert packet["writes_attempted"] == 0
    assert packet["network_calls_made"] == 0
    assert packet["commands"]["live_pilot_rehearsal_drill"] == "drills live-pilot-rehearsal --json"

    assert (
        main(
            [
                "--config",
                str(config_path),
                "operator-live-pilot-readiness-packet",
                "--run-id",
                run_id,
                "--sink",
                "google_contacts",
                "--no-write",
            ]
        )
        == 0
    )
    text = capsys.readouterr().out
    assert "Operator live pilot readiness packet: ready_for_operator_response" in text
    assert "Selected target approval boundary: runs selected-target-approval-boundary" in text
    assert "Selected target command copy packet: runs selected-target-command-copy-packet" in text
    assert "Synthetic rehearsal: drills live-pilot-rehearsal --json" in text
    assert "{" not in text


def test_cli_review_routing_drill_outputs_fixture_artifact(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "config.toml"
    data_dir = tmp_path / "data"
    write_config(config_path, data_dir)

    assert main(["--config", str(config_path), "drills", "review-routing", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["schema"] == "business-card-watchdog.review-routing-drill.v1"
    assert payload["private_sources_used"] is False
    assert payload["agent_loop_readback"]["state"] == "passed"
    assert payload["agent_loop_readback"]["next_manual_boundary"] == "decide_sink_apply"
    assert payload["safe_actions"]["skipped_actions"] == ["decide_sink_apply"]
    assert payload["commands"]["review_workbook"] == (
        f"reviews workbook --run-id {payload['run_id']} --state all --json"
    )
    assert Path(payload["drill_path"]).exists()

    assert main(["--config", str(config_path), "drills", "review-routing"]) == 0
    text = capsys.readouterr().out
    assert "Review routing drill:" in text
    assert "Fixture sinks: google_contacts, odoo" in text
    assert "Review: needs_review -> ready_to_route" in text
    assert "Agent readback: passed" in text
    assert "Manual boundary: decide_sink_apply" in text
    assert "Observed: writes=0 network=0 private_sources=False live_sinks=False" in text
    assert "Safe actions executed: 7" in text
    assert "Manual actions skipped: 1" in text
    assert "decide_sink_apply" in text
    assert "Review workbook: reviews workbook --run-id" in text
    assert "Stop conditions: 3" in text
    assert "{" not in text


def test_cli_live_pilot_rehearsal_drill_reaches_command_copy_gate(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "config.toml"
    data_dir = tmp_path / "data"
    write_config(config_path, data_dir)

    assert main(["--config", str(config_path), "drills", "live-pilot-rehearsal", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["schema"] == "business-card-watchdog.live-pilot-rehearsal-drill.v1"
    assert payload["state"] == "passed"
    assert payload["private_sources_used"] is False
    assert payload["live_sink_calls_made"] is False
    assert payload["command_copy_ready"] is True
    assert payload["packets"]["selected_target_approval_boundary"]["state"] == (
        "ready_for_explicit_selected_target_creation"
    )
    assert payload["packets"]["selected_target_command_copy_packet"]["state"] == "ready_for_operator_copy"
    assert payload["packets"]["command_copy_packet"]["state"] == "ready_for_operator_copy"
    assert payload["writes_attempted"] == 0
    assert payload["network_calls_made"] == 0
    sample_output_path = Path(payload["sample_outputs"]["live_pilot_rehearsal_markdown_path"])
    preflight_sample_output_path = Path(
        payload["sample_outputs"]["operator_selected_live_smoke_preflight_markdown_path"]
    )
    assert sample_output_path.exists()
    assert preflight_sample_output_path.exists()
    assert "Live Pilot Rehearsal Sample Output" in sample_output_path.read_text(encoding="utf-8")
    assert "Operator-Selected Live Smoke Preflight Sample Output" in preflight_sample_output_path.read_text(
        encoding="utf-8"
    )
    assert payload["packets"]["operator_selected_preflight"]["schema"] == (
        "business-card-watchdog.operator-selected-live-smoke-preflight.v1"
    )
    assert Path(payload["drill_path"]).exists()

    assert main(["--config", str(config_path), "drills", "live-pilot-rehearsal"]) == 0
    text = capsys.readouterr().out
    assert "Live pilot rehearsal drill:" in text
    assert "State: passed" in text
    assert "Command copy ready: True" in text
    assert "Observed: writes=0 network=0 private_sources=False live_sinks=False" in text
    assert "Selected target approval boundary: runs selected-target-approval-boundary" in text
    assert "Selected target command copy packet: runs selected-target-command-copy-packet" in text
    assert "Command copy packet: runs live-pilot-command-copy-packet-from-response" in text
    assert "Sample output:" in text
    assert "Stop conditions: 4" in text
    assert "{" not in text


def test_cli_child_replacement_readiness_drill_exports_operator_samples(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "config.toml"
    data_dir = tmp_path / "data"
    write_config(config_path, data_dir)

    assert main(["--config", str(config_path), "drills", "child-replacement-readiness", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["schema"] == "business-card-watchdog.child-replacement-readiness-drill.v1"
    assert payload["state"] == "passed"
    assert payload["readiness_states"]["closeout"] == "ready_for_operator_closeout"
    assert payload["operator_dashboard_child_replacement_summary"]["ready_count"] == 1
    assert payload["writes_attempted"] == 0
    assert payload["network_calls_made"] == 0
    sample_output_path = Path(payload["sample_outputs"]["child_replacement_readiness_markdown_path"])
    assert sample_output_path.exists()
    assert "Child Replacement Readiness Sample Output" in sample_output_path.read_text(encoding="utf-8")
    assert Path(payload["sample_outputs"]["review_html_path"]).exists()

    assert main(["--config", str(config_path), "drills", "child-replacement-readiness"]) == 0
    text = capsys.readouterr().out
    assert "Child replacement readiness drill:" in text
    assert "closeout: ready_for_operator_closeout" in text
    assert "Sample output:" in text
    assert "Review HTML:" in text
    assert "{" not in text


def test_cli_multi_card_preclassification_drill_records_candidate_boxes(
    tmp_path: Path,
    capsys,
) -> None:
    pytest = __import__("pytest")
    pytest.importorskip("cv2")
    config_path = tmp_path / "config.toml"
    data_dir = tmp_path / "data"
    write_config(config_path, data_dir)

    assert main(["--config", str(config_path), "drills", "multi-card-preclassification", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["schema"] == "business-card-watchdog.multi-card-preclassification-drill.v1"
    assert payload["state"] == "passed"
    assert payload["expected_card_count"] == 3
    assert payload["detected_card_like_count"] >= 3
    assert len(payload["candidate_boxes"]) >= 3
    assert payload["writes_attempted"] == 0
    assert payload["network_calls_made"] == 0
    assert Path(payload["drill_path"]).exists()

    assert main(["--config", str(config_path), "drills", "multi-card-preclassification"]) == 0
    text = capsys.readouterr().out
    assert "Multi-card preclassification drill:" in text
    assert "State: passed" in text
    assert "Detected card-like boxes:" in text
    assert "Observed: writes=0 network=0 private_sources=False live_sinks=False" in text
    assert "{" not in text


def test_cli_watch_dry_run_selection_drill_exports_sample_output(
    tmp_path: Path,
    capsys,
) -> None:
    config_path = tmp_path / "config.toml"
    data_dir = tmp_path / "data"
    write_config(config_path, data_dir)

    assert main(["--config", str(config_path), "drills", "watch-dry-run-selection", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["schema"] == "business-card-watchdog.watch-dry-run-selection-drill.v1"
    assert payload["state"] == "passed"
    assert payload["command_copy_ready"] is True
    assert payload["files_processed"] == 0
    assert payload["ocr_attempted"] == 0
    sample_output_path = Path(payload["sample_outputs"]["watch_dry_run_selection_markdown_path"])
    assert sample_output_path.exists()
    assert "Watch Dry-Run Selection Sample Output" in sample_output_path.read_text(encoding="utf-8")

    assert main(["--config", str(config_path), "drills", "watch-dry-run-selection"]) == 0
    text = capsys.readouterr().out
    assert "Watch dry-run selection drill:" in text
    assert "State: passed" in text
    assert "Command copy ready: True" in text
    assert "Sample output:" in text
    assert "{" not in text


def test_cli_watch_dry_run_execution_drill_runs_real_dry_pipeline(
    tmp_path: Path,
    capsys,
) -> None:
    config_path = tmp_path / "config.toml"
    data_dir = tmp_path / "data"
    write_config(config_path, data_dir)

    assert main(["--config", str(config_path), "drills", "watch-dry-run-execution", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["schema"] == "business-card-watchdog.watch-dry-run-execution-drill.v1"
    assert payload["state"] == "passed"
    assert payload["files_processed"] == 1
    assert payload["ocr_attempted"] == 1
    assert payload["network_calls_made"] == 0
    assert payload["processed_run"]["state"] == "completed"
    sample_output_path = Path(payload["sample_outputs"]["watch_dry_run_execution_markdown_path"])
    assert sample_output_path.exists()

    assert main(["--config", str(config_path), "drills", "watch-dry-run-execution"]) == 0
    text = capsys.readouterr().out
    assert "Watch dry-run execution drill:" in text
    assert "State: passed" in text
    assert "Processed run state: completed" in text
    assert "Observed: files=1 ocr=1 writes=0 network=0" in text
    assert "Sample output:" in text
    assert "{" not in text


def test_cli_runs_dry_run_closeout_reports_no_live(tmp_path: Path, monkeypatch, capsys) -> None:
    config_path = tmp_path / "config.toml"
    data_dir = tmp_path / "data"
    write_config(config_path, data_dir)
    source_dir = tmp_path / "cards"
    write_synthetic_image(source_dir / "card.png")
    config = AppConfig(
        config_path=config_path,
        data_dir=data_dir,
        prefilter=PrefilterConfig(enabled=False),
        sink=SinkConfig(google_contacts=True, odoo=True, dry_run=True),
        routing_rules=[{"match": "email_domain", "value": "*", "sinks": ["google_contacts", "odoo"]}],
    )
    orchestrator = BatchOrchestrator(config)
    monkeypatch.setattr(orchestrator, "adapter", SyntheticSkillAdapter())
    run_dir = orchestrator.process_source(str(source_dir), dry_run=True, workers=1)

    assert main(["--config", str(config_path), "runs", "dry-run-closeout", run_dir.name, "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["schema"] == "business-card-watchdog.dry-run-closeout.v1"
    assert payload["state"] == "ready_for_review_and_routing"
    assert payload["runtime_artifact_written"] is True
    assert Path(payload["closeout_path"]).exists()
    assert payload["writes_attempted"] == 0
    assert payload["network_calls_made"] == 0
    assert payload["live_sink_calls_made"] is False

    assert main(["--config", str(config_path), "runs", "dry-run-closeout", run_dir.name, "--no-write"]) == 0
    text = capsys.readouterr().out
    assert "Dry-run closeout: ready_for_review_and_routing" in text
    assert "Observed: files=1 ocr_artifacts=1 writes=0 network=0" in text
    assert "Live event types: 0" in text
    assert "Runtime artifact written: False" in text
    assert "Closeout: runs dry-run-closeout" in text
    assert "Stop conditions: 4" in text
    assert "{" not in text


def test_cli_runs_dry_run_review_handoff_reports_safe_next_steps(tmp_path: Path, monkeypatch, capsys) -> None:
    config_path = tmp_path / "config.toml"
    data_dir = tmp_path / "data"
    write_config(config_path, data_dir)
    source_dir = tmp_path / "cards"
    write_synthetic_image(source_dir / "card.png")
    config = AppConfig(
        config_path=config_path,
        data_dir=data_dir,
        prefilter=PrefilterConfig(enabled=False),
        sink=SinkConfig(google_contacts=True, odoo=True, dry_run=True),
        routing_rules=[{"match": "email_domain", "value": "*", "sinks": ["google_contacts", "odoo"]}],
    )
    orchestrator = BatchOrchestrator(config)
    monkeypatch.setattr(orchestrator, "adapter", SyntheticSkillAdapter())
    run_dir = orchestrator.process_source(str(source_dir), dry_run=True, workers=1)

    assert main(["--config", str(config_path), "runs", "dry-run-review-handoff", run_dir.name, "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["schema"] == "business-card-watchdog.dry-run-review-handoff.v1"
    assert payload["state"] == "ready_for_safe_agent_loop"
    assert payload["safe_auto_action_count"] == 1
    assert payload["next_action_counts"] == {"plan_sink_lookup": 1}
    assert payload["writes_attempted"] == 0
    assert payload["network_calls_made"] == 0
    assert Path(payload["handoff_path"]).exists()

    assert main(["--config", str(config_path), "runs", "dry-run-review-handoff", run_dir.name, "--no-write"]) == 0
    text = capsys.readouterr().out
    assert "Dry-run review handoff: ready_for_safe_agent_loop" in text
    assert "Closeout: ready_for_review_and_routing" in text
    assert "Safe auto actions: 1" in text
    assert "plan_sink_lookup: 1" in text
    assert "Observed: writes=0 network=0 live_sinks=False" in text
    assert "Live pilot status: runs live-pilot-status" in text
    assert "Stop conditions: 4" in text
    assert "{" not in text


def test_cli_runs_dry_run_safe_loop_executes_bounded_safe_actions(tmp_path: Path, monkeypatch, capsys) -> None:
    config_path = tmp_path / "config.toml"
    data_dir = tmp_path / "data"
    write_config(config_path, data_dir)
    source_dir = tmp_path / "cards"
    write_synthetic_image(source_dir / "card.png")
    config = AppConfig(
        config_path=config_path,
        data_dir=data_dir,
        prefilter=PrefilterConfig(enabled=False),
        sink=SinkConfig(google_contacts=True, odoo=True, dry_run=True),
        routing_rules=[{"match": "email_domain", "value": "*", "sinks": ["google_contacts", "odoo"]}],
    )
    orchestrator = BatchOrchestrator(config)
    monkeypatch.setattr(orchestrator, "adapter", SyntheticSkillAdapter())
    run_dir = orchestrator.process_source(str(source_dir), dry_run=True, workers=1)

    assert (
        main(
            [
                "--config",
                str(config_path),
                "runs",
                "dry-run-safe-loop",
                run_dir.name,
                "--limit",
                "2",
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)

    assert payload["schema"] == "business-card-watchdog.dry-run-safe-loop.v1"
    assert payload["state"] == "safe_loop_executed"
    assert payload["executed_count"] == 2
    assert [action["action"] for action in payload["executed"]] == [
        "plan_sink_lookup",
        "prepare_sink_lookup_adapter",
    ]
    assert payload["writes_attempted"] == 0
    assert payload["network_calls_made"] == 0
    assert Path(payload["safe_loop_path"]).exists()

    assert (
        main(
            [
                "--config",
                str(config_path),
                "runs",
                "dry-run-safe-loop",
                run_dir.name,
                "--limit",
                "1",
                "--no-write",
            ]
        )
        == 0
    )
    text = capsys.readouterr().out
    assert "Dry-run safe loop:" in text
    assert "Executed: 1" in text
    assert "Observed: writes=0 network=0 live_sinks=False" in text
    assert "Safe loop: runs dry-run-safe-loop" in text
    assert "Stop conditions: 5" in text
    assert "{" not in text


def test_cli_runs_agent_review_loop_plans_qr_side_followup(tmp_path: Path, monkeypatch, capsys) -> None:
    config_path = tmp_path / "config.toml"
    data_dir = tmp_path / "data"
    write_config(config_path, data_dir)
    source_dir = tmp_path / "cards"
    write_qr_image(source_dir / "qr-side.png", "https://example.test/gallagher")
    config = AppConfig(
        config_path=config_path,
        data_dir=data_dir,
        prefilter=PrefilterConfig(enabled=False),
        sink=SinkConfig(dry_run=True),
        routing_rules=[],
    )
    orchestrator = BatchOrchestrator(config)
    monkeypatch.setattr(orchestrator, "adapter", SyntheticSkillAdapter())
    run_dir = orchestrator.process_source(str(source_dir), dry_run=True, workers=1)
    service = BusinessCardService(config)
    surface = service.contact_review_surface(limit=10)
    contact_id = surface["rows"][0]["contact_id"]
    review_state = service.record_contact_review_recommendation(
        contact_id=contact_id,
        source="cli-test",
        category="card_side_and_crop_quality",
        recommendation="keep_needs_review_require_qr_orientation_crop_and_backside_pairing",
        rationale="QR side requires orientation, crop, and backside pairing review",
        confidence=0.9,
    )["review_state"]
    service.decide_contact_review_state(
        review_state_id=review_state["review_state_id"],
        reviewer="cli-test",
        decision="accept",
        notes="fixture acceptance",
    )

    assert (
        main(
            [
                "--config",
                str(config_path),
                "runs",
                "agent-review-loop",
                run_dir.name,
                "--limit",
                "1",
                "--dry-run",
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)

    assert payload["schema"] == "business-card-watchdog.agent-review-loop.v1"
    assert payload["selected_job_count"] == 1
    assert payload["planned_actions"][0]["action"] == "inspect_qr_evidence"
    assert payload["planned_actions"][0]["qr_evidence"]["payload_types"] == ["url"]
    assert {request["request_type"] for request in payload["app_intelligence_requests"]} == {
        "resolve_orientation",
        "assess_crop_quality",
        "pair_card_sides",
    }
    assert payload["training_candidate_count"] == 1
    assert payload["writes_attempted"] == 0
    assert payload["network_calls_made"] == 0

    assert (
        main(
            [
                "--config",
                str(config_path),
                "runs",
                "agent-review-loop",
                run_dir.name,
                "--limit",
                "1",
                "--no-write",
            ]
        )
        == 0
    )
    text = capsys.readouterr().out
    assert "Agent review loop:" in text
    assert "App Intelligence requests: 3" in text
    assert "Observed: writes=0 network=0 live_sinks=False" in text
    assert "{" not in text


def test_cli_runs_review_route_readiness_reports_route_state(tmp_path: Path, monkeypatch, capsys) -> None:
    config_path = tmp_path / "config.toml"
    data_dir = tmp_path / "data"
    write_config(config_path, data_dir)
    source_dir = tmp_path / "cards"
    write_synthetic_image(source_dir / "card.png")
    config = AppConfig(
        config_path=config_path,
        data_dir=data_dir,
        prefilter=PrefilterConfig(enabled=False),
        sink=SinkConfig(google_contacts=True, odoo=True, dry_run=True),
        routing_rules=[{"match": "email_domain", "value": "*", "sinks": ["google_contacts", "odoo"]}],
    )
    orchestrator = BatchOrchestrator(config)
    monkeypatch.setattr(orchestrator, "adapter", SyntheticSkillAdapter())
    run_dir = orchestrator.process_source(str(source_dir), dry_run=True, workers=1)

    assert main(["--config", str(config_path), "runs", "review-route-readiness", run_dir.name, "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["schema"] == "business-card-watchdog.review-route-readiness.v1"
    assert payload["state"] == "ready_for_safe_agent_loop"
    assert payload["counts"]["route_ready"] == 1
    assert payload["next_action_counts"] == {"plan_sink_lookup": 1}
    assert payload["writes_attempted"] == 0
    assert payload["network_calls_made"] == 0
    assert Path(payload["readiness_path"]).exists()

    assert main(["--config", str(config_path), "runs", "review-route-readiness", run_dir.name, "--no-write"]) == 0
    text = capsys.readouterr().out
    assert "Review-route readiness: ready_for_safe_agent_loop" in text
    assert "Ready to route: 1" in text
    assert "Duplicate risky: 0" in text
    assert "Safe auto: 1" in text
    assert "plan_sink_lookup: 1" in text
    assert "Observed: writes=0 network=0 live_sinks=False" in text
    assert "Stop conditions: 4" in text
    assert "{" not in text


def test_cli_runs_lookup_selection_packet_reports_selected_candidate(tmp_path: Path, monkeypatch, capsys) -> None:
    config_path = tmp_path / "config.toml"
    data_dir = tmp_path / "data"
    write_config(config_path, data_dir)
    source_dir = tmp_path / "cards"
    write_synthetic_image(source_dir / "card.png")
    config = AppConfig(
        config_path=config_path,
        data_dir=data_dir,
        prefilter=PrefilterConfig(enabled=False),
        sink=SinkConfig(google_contacts=True, dry_run=True),
    )
    orchestrator = BatchOrchestrator(config)
    monkeypatch.setattr(orchestrator, "adapter", SyntheticSkillAdapter())
    run_dir = orchestrator.process_source(str(source_dir), dry_run=True, workers=1)

    assert (
        main(
            [
                "--config",
                str(config_path),
                "runs",
                "lookup-selection-packet",
                run_dir.name,
                "--operator",
                "tester",
                "--sink",
                "google_contacts",
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)

    assert payload["schema"] == "business-card-watchdog.lookup-selection-packet.v1"
    assert payload["state"] == "packet_blocked"
    assert payload["route_ready_count"] == 1
    assert payload["selected"]["sink"] == "google_contacts"
    assert payload["creates_selected_live_target"] is False
    assert payload["writes_attempted"] == 0
    assert payload["network_calls_made"] == 0
    assert Path(payload["packet_path"]).exists()

    assert (
        main(
            [
                "--config",
                str(config_path),
                "runs",
                "lookup-selection-packet",
                run_dir.name,
                "--operator",
                "tester",
                "--sink",
                "google_contacts",
                "--no-write",
            ]
        )
        == 0
    )
    text = capsys.readouterr().out
    assert "Lookup selection packet: packet_blocked" in text
    assert "Selected sink: google_contacts" in text
    assert "creates_selected_target=False" in text
    assert "Validate prefilled response: runs live-pilot-validate-response" in text
    assert "Stop conditions: 5" in text
    assert "{" not in text


def test_cli_runs_close_lookup_prerequisites_executes_lookup_steps(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "config.toml"
    data_dir = tmp_path / "data"
    write_config(config_path, data_dir)
    config = AppConfig(
        config_path=config_path,
        data_dir=data_dir,
        sink=SinkConfig(google_contacts=True, dry_run=True),
    )
    run_id, job_id = make_recorded_run(config)
    BusinessCardService(config).submit_review(
        job_id=job_id,
        run_id=run_id,
        reviewer="tester",
        action="approve_for_routing",
    )

    assert (
        main(
            [
                "--config",
                str(config_path),
                "runs",
                "close-lookup-prerequisites",
                run_id,
                "--operator",
                "tester",
                "--sink",
                "google_contacts",
                "--limit",
                "4",
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)

    assert payload["schema"] == "business-card-watchdog.close-lookup-prerequisites.v1"
    assert payload["executed_count"] == 4
    assert payload["writes_attempted"] == 0
    assert payload["network_calls_made"] == 0
    assert Path(payload["closeout_path"]).exists()

    assert (
        main(
            [
                "--config",
                str(config_path),
                "runs",
                "close-lookup-prerequisites",
                run_id,
                "--operator",
                "tester",
                "--sink",
                "google_contacts",
                "--limit",
                "1",
                "--no-write",
            ]
        )
        == 0
    )
    text = capsys.readouterr().out
    assert "Close lookup prerequisites:" in text
    assert "creates_selected_target=False" in text
    assert "Close lookup prerequisites: runs close-lookup-prerequisites" in text
    assert "Stop conditions: 5" in text
    assert "{" not in text


def test_cli_runs_selected_target_approval_boundary_previews_selection(tmp_path: Path, capsys) -> None:
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
    service.submit_review(
        job_id=job_id,
        run_id=run_id,
        reviewer="tester",
        action="approve_for_routing",
    )
    service.close_lookup_prerequisites(
        run_id,
        operator="tester",
        sink="google_contacts",
        limit=4,
        write=True,
    )

    assert (
        main(
            [
                "--config",
                str(config_path),
                "runs",
                "selected-target-approval-boundary",
                run_id,
                "--operator",
                "tester",
                "--sink",
                "google_contacts",
                "--job-id",
                job_id,
                "--no-write",
                "--json",
            ]
        )
        == 0
    )
    awaiting = json.loads(capsys.readouterr().out)
    assert awaiting["schema"] == "business-card-watchdog.selected-target-approval-boundary.v1"
    assert awaiting["state"] == "awaiting_operator_response"
    assert awaiting["would_create_selected_live_target"] is False
    assert awaiting["creates_selected_live_target"] is False
    assert awaiting["runtime_artifact_written"] is False

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
                "selected-target-approval-boundary",
                run_id,
                "--operator",
                "tester",
                "--sink",
                "google_contacts",
                "--job-id",
                job_id,
                "--response",
                response,
                "--no-write",
            ]
        )
        == 0
    )
    text = capsys.readouterr().out
    assert "Selected-target approval boundary: ready_for_explicit_selected_target_creation" in text
    assert "Would create selected target: True" in text
    assert "Creates selected target: False" in text
    assert "Select target: sinks select-live-target" in text
    assert "Stop conditions: 4" in text
    assert "{" not in text


def test_cli_runs_selected_target_command_copy_packet_requires_ack(tmp_path: Path, capsys) -> None:
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
    service.submit_review(
        job_id=job_id,
        run_id=run_id,
        reviewer="tester",
        action="approve_for_routing",
    )
    service.close_lookup_prerequisites(
        run_id,
        operator="tester",
        sink="google_contacts",
        limit=4,
        write=True,
    )
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
                "selected-target-command-copy-packet",
                run_id,
                "--operator",
                "tester",
                "--sink",
                "google_contacts",
                "--job-id",
                job_id,
                "--response",
                response,
                "--json",
            ]
        )
        == 0
    )
    blocked = json.loads(capsys.readouterr().out)
    assert blocked["schema"] == "business-card-watchdog.selected-target-command-copy-packet.v1"
    assert blocked["state"] == "blocked"
    assert blocked["command_copy_text"] is None
    assert blocked["creates_selected_live_target"] is False

    assert (
        main(
            [
                "--config",
                str(config_path),
                "runs",
                "selected-target-command-copy-packet",
                run_id,
                "--operator",
                "tester",
                "--sink",
                "google_contacts",
                "--job-id",
                job_id,
                "--response",
                response,
                "--acknowledgement",
                f"acknowledge run_id={run_id} job_id={job_id} sink=google_contacts operator=tester copy command",
            ]
        )
        == 0
    )
    text = capsys.readouterr().out
    assert "Selected-target command copy packet: ready_for_operator_copy" in text
    assert "Acknowledgement ok: True" in text
    assert "Command copy text: runs selected-live-target-from-response" in text
    assert "--write-selected-target" in text
    assert "Creates selected target: False" in text
    assert "{" not in text


def test_cli_contact_route_selection_packets_use_projected_route(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "config.toml"
    data_dir = tmp_path / "data"
    config_path.write_text(
        f'data_dir = "{data_dir}"\n[watch]\ninputs = []\n[sink]\n'
        'dry_run = true\ngoogle_contacts = true\ngoogle_contacts_profile = "ecochran76"\n',
        encoding="utf-8",
    )
    config = AppConfig(
        config_path=config_path,
        data_dir=data_dir,
        sink=SinkConfig(google_contacts=True, dry_run=True, google_contacts_profile="ecochran76"),
    )
    _service, run_id, job_id, contact_id = project_gws_route_contact(config)

    assert (
        main(
            [
                "--config",
                str(config_path),
                "contacts",
                "route-selection-approval-boundary",
                contact_id,
                "--operator",
                "cli-test",
                "--sink",
                "google_contacts",
                "--no-write",
                "--json",
            ]
        )
        == 0
    )
    awaiting = json.loads(capsys.readouterr().out)
    assert awaiting["state"] == "awaiting_operator_response"
    assert awaiting["run_id"] == run_id
    assert awaiting["job_id"] == job_id
    assert awaiting["creates_selected_live_target"] is False

    response = (
        f"run_id={run_id} job_id={job_id} sink=google_contacts "
        "operator=cli-test scope=lookup safety_confirmation=fixture contact is safe for google contacts test profile"
    )
    assert (
        main(
            [
                "--config",
                str(config_path),
                "contacts",
                "route-selection-command-copy-packet",
                contact_id,
                "--operator",
                "cli-test",
                "--sink",
                "google_contacts",
                "--response",
                response,
                "--acknowledgement",
                f"acknowledge run_id={run_id} job_id={job_id} sink=google_contacts operator=cli-test copy command",
                "--json",
            ]
        )
        == 0
    )
    ready = json.loads(capsys.readouterr().out)
    assert ready["state"] == "ready_for_operator_copy"
    assert ready["command_copy_text"].startswith(f"runs selected-live-target-from-response {run_id}")
    assert ready["creates_selected_live_target"] is False


def test_cli_child_reviews_lists_promoted_child_candidates(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    pytest = __import__("pytest")
    pytest.importorskip("cv2")
    config_path = tmp_path / "config.toml"
    data_dir = tmp_path / "data"
    write_config(config_path, data_dir)
    source_dir = tmp_path / "images"
    write_multi_card_image(source_dir / "multi.jpg")
    config = AppConfig(config_path=config_path, data_dir=data_dir)
    orchestrator = BatchOrchestrator(config)
    monkeypatch.setattr(orchestrator, "adapter", SyntheticSkillAdapter())
    run_dir = orchestrator.process_source(str(source_dir), dry_run=True, workers=1)

    assert main(["--config", str(config_path), "reviews", "children", "--run-id", run_dir.name, "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert len(payload) >= 3
    assert payload[0]["next_action"]["action"] == "review_child_contact"
    assert payload[0]["contact_candidate"]["source"] == "child_verification_result"

    assert main(["--config", str(config_path), "reviews", "children", "--run-id", run_dir.name]) == 0
    text = capsys.readouterr().out
    assert "Child review queue:" in text
    assert "next=review_child_contact" in text
    assert "{" not in text


def test_cli_child_review_approves_promoted_child_candidate(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    pytest = __import__("pytest")
    pytest.importorskip("cv2")
    config_path = tmp_path / "config.toml"
    data_dir = tmp_path / "data"
    write_config(config_path, data_dir)
    source_dir = tmp_path / "images"
    write_multi_card_image(source_dir / "multi.jpg")
    config = AppConfig(config_path=config_path, data_dir=data_dir)
    orchestrator = BatchOrchestrator(config)
    monkeypatch.setattr(orchestrator, "adapter", SyntheticSkillAdapter())
    run_dir = orchestrator.process_source(str(source_dir), dry_run=True, workers=1)
    candidate_id = str(BusinessCardService(config).child_review_queue(run_id=run_dir.name)[0]["candidate_id"])

    assert (
        main(
            [
                "--config",
                str(config_path),
                "reviews",
                "child-review",
                candidate_id,
                "--run-id",
                run_dir.name,
                "--action",
                "approve_child_for_routing",
                "--field-corrections-json",
                '{"email":"cli-child@example.test"}',
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)

    assert payload["candidate_id"] == candidate_id
    assert payload["state"] == "approved_for_dedupe"
    assert payload["reviewed_contact"]["flat"]["email"] == "cli-child@example.test"
    assert payload["writes_attempted"] == 0
    assert payload["network_calls_made"] == 0


def test_cli_child_route_prep_writes_dry_run_plans(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    pytest = __import__("pytest")
    pytest.importorskip("cv2")
    config_path = tmp_path / "config.toml"
    data_dir = tmp_path / "data"
    write_config(config_path, data_dir)
    source_dir = tmp_path / "images"
    write_multi_card_image(source_dir / "multi.jpg")
    config = AppConfig(
        config_path=config_path,
        data_dir=data_dir,
        sink=SinkConfig(google_contacts=True, dry_run=True),
    )
    orchestrator = BatchOrchestrator(config)
    monkeypatch.setattr(orchestrator, "adapter", SyntheticSkillAdapter())
    run_dir = orchestrator.process_source(str(source_dir), dry_run=True, workers=1)
    service = BusinessCardService(config)
    candidate_id = str(service.child_review_queue(run_id=run_dir.name)[0]["candidate_id"])
    service.submit_child_review(
        run_id=run_dir.name,
        candidate_id=candidate_id,
        reviewer="operator",
        action="approve_child_for_routing",
    )

    assert (
        main(
            [
                "--config",
                str(config_path),
                "reviews",
                "child-route-prep-queue",
                "--run-id",
                run_dir.name,
                "--json",
            ]
        )
        == 0
    )
    queue = json.loads(capsys.readouterr().out)
    assert any(entry["candidate_id"] == candidate_id for entry in queue)

    assert (
        main(
            [
                "--config",
                str(config_path),
                "reviews",
                "child-route-prep",
                candidate_id,
                "--run-id",
                run_dir.name,
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)

    assert payload["state"] == "routing_prepared"
    assert payload["lookup_plan"]["dry_run"] is True
    assert payload["sink_plan"]["dry_run"] is True
    assert payload["result"]["sink_write_allowed"] is False
    assert payload["writes_attempted"] == 0
    assert payload["network_calls_made"] == 0


def test_cli_child_lookup_result_and_duplicate_assessment(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    pytest = __import__("pytest")
    pytest.importorskip("cv2")
    config_path = tmp_path / "config.toml"
    data_dir = tmp_path / "data"
    write_config(config_path, data_dir)
    source_dir = tmp_path / "images"
    write_multi_card_image(source_dir / "multi.jpg")
    config = AppConfig(
        config_path=config_path,
        data_dir=data_dir,
        sink=SinkConfig(google_contacts=True, dry_run=True),
    )
    orchestrator = BatchOrchestrator(config)
    monkeypatch.setattr(orchestrator, "adapter", SyntheticSkillAdapter())
    run_dir = orchestrator.process_source(str(source_dir), dry_run=True, workers=1)
    service = BusinessCardService(config)
    candidate_id = str(service.child_review_queue(run_id=run_dir.name)[0]["candidate_id"])
    service.submit_child_review(
        run_id=run_dir.name,
        candidate_id=candidate_id,
        reviewer="operator",
        action="approve_child_for_routing",
    )
    service.prepare_child_route(run_id=run_dir.name, candidate_id=candidate_id)

    assert (
        main(
            [
                "--config",
                str(config_path),
                "reviews",
                "child-lookup-result",
                candidate_id,
                "--run-id",
                run_dir.name,
                "--matches-by-sink-json",
                '{"google_contacts":[{"resource_id":"people/cli-child","confidence":0.9,"basis":["email"]}]}',
                "--json",
            ]
        )
        == 0
    )
    lookup = json.loads(capsys.readouterr().out)

    assert main(
        [
            "--config",
            str(config_path),
            "reviews",
            "child-assess-duplicates",
            candidate_id,
            "--run-id",
            run_dir.name,
            "--json",
        ]
    ) == 0
    assessment = json.loads(capsys.readouterr().out)

    assert lookup["result"]["match_count"] == 1
    assert lookup["writes_attempted"] == 0
    assert lookup["network_calls_made"] == 0
    assert assessment["assessment"]["state"] == "strong_duplicate"
    assert assessment["writes_attempted"] == 0
    assert assessment["network_calls_made"] == 0


def test_cli_child_duplicate_resolution_clears_gate(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    pytest = __import__("pytest")
    pytest.importorskip("cv2")
    config_path = tmp_path / "config.toml"
    data_dir = tmp_path / "data"
    write_config(config_path, data_dir)
    source_dir = tmp_path / "images"
    write_multi_card_image(source_dir / "multi.jpg")
    config = AppConfig(
        config_path=config_path,
        data_dir=data_dir,
        sink=SinkConfig(google_contacts=True, dry_run=True),
    )
    orchestrator = BatchOrchestrator(config)
    monkeypatch.setattr(orchestrator, "adapter", SyntheticSkillAdapter())
    run_dir = orchestrator.process_source(str(source_dir), dry_run=True, workers=1)
    service = BusinessCardService(config)
    candidate_id = str(service.child_review_queue(run_id=run_dir.name)[0]["candidate_id"])
    service.submit_child_review(
        run_id=run_dir.name,
        candidate_id=candidate_id,
        reviewer="operator",
        action="approve_child_for_routing",
    )
    service.prepare_child_route(run_id=run_dir.name, candidate_id=candidate_id)
    service.record_child_sink_lookup_result(
        run_id=run_dir.name,
        candidate_id=candidate_id,
        matches_by_sink={"google_contacts": [{"resource_id": "people/cli-existing", "basis": ["email"]}]},
    )
    service.assess_child_downstream_duplicates(run_id=run_dir.name, candidate_id=candidate_id)

    assert main(
        [
            "--config",
            str(config_path),
            "reviews",
            "child-resolve-duplicate",
            candidate_id,
            "--run-id",
            run_dir.name,
            "--decision",
            "create_new",
            "--reason",
            "separate person",
            "--json",
        ]
    ) == 0
    resolution = json.loads(capsys.readouterr().out)

    assert main(
        [
            "--config",
            str(config_path),
            "reviews",
            "child-sink-plan-gate",
            candidate_id,
            "--run-id",
            run_dir.name,
            "--json",
        ]
    ) == 0
    gate = json.loads(capsys.readouterr().out)

    assert resolution["resolution"]["decision"] == "create_new"
    assert resolution["writes_attempted"] == 0
    assert resolution["network_calls_made"] == 0
    assert gate["gate"]["state"] == "ready_for_sink_plan"
    assert gate["gate"]["sink_write_allowed"] is False


def test_cli_child_sink_apply_preflight_and_handoff(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    pytest = __import__("pytest")
    pytest.importorskip("cv2")
    config_path = tmp_path / "config.toml"
    data_dir = tmp_path / "data"
    write_config(config_path, data_dir)
    source_dir = tmp_path / "images"
    write_multi_card_image(source_dir / "multi.jpg")
    config = AppConfig(
        config_path=config_path,
        data_dir=data_dir,
        sink=SinkConfig(google_contacts=True, dry_run=True),
    )
    orchestrator = BatchOrchestrator(config)
    monkeypatch.setattr(orchestrator, "adapter", SyntheticSkillAdapter())
    run_dir = orchestrator.process_source(str(source_dir), dry_run=True, workers=1)
    service = BusinessCardService(config)
    candidate_id = str(service.child_review_queue(run_id=run_dir.name)[0]["candidate_id"])
    service.submit_child_review(
        run_id=run_dir.name,
        candidate_id=candidate_id,
        reviewer="operator",
        action="approve_child_for_routing",
    )
    service.prepare_child_route(run_id=run_dir.name, candidate_id=candidate_id)
    service.record_child_sink_lookup_result(run_id=run_dir.name, candidate_id=candidate_id)
    service.assess_child_downstream_duplicates(run_id=run_dir.name, candidate_id=candidate_id)
    service.child_sink_plan_gate(run_id=run_dir.name, candidate_id=candidate_id)

    assert main(
        [
            "--config",
            str(config_path),
            "reviews",
            "child-sink-apply-preflight",
            candidate_id,
            "--run-id",
            run_dir.name,
            "--json",
        ]
    ) == 0
    preflight = json.loads(capsys.readouterr().out)

    assert main(
        [
            "--config",
            str(config_path),
            "reviews",
            "child-selected-target-handoff",
            candidate_id,
            "--run-id",
            run_dir.name,
            "--sink",
            "google_contacts",
            "--json",
        ]
    ) == 0
    handoff = json.loads(capsys.readouterr().out)

    assert preflight["preflight"]["state"] == "preview"
    assert preflight["preflight"]["sink_write_allowed"] is False
    assert handoff["handoff"]["state"] == "ready_for_operator_selection"
    assert handoff["handoff"]["selected_target_created"] is False
    assert handoff["writes_attempted"] == 0
    assert handoff["network_calls_made"] == 0


def test_cli_child_selected_target_response_validation_and_checklist(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    pytest = __import__("pytest")
    pytest.importorskip("cv2")
    config_path = tmp_path / "config.toml"
    data_dir = tmp_path / "data"
    write_config(config_path, data_dir)
    source_dir = tmp_path / "images"
    write_multi_card_image(source_dir / "multi.jpg")
    config = AppConfig(
        config_path=config_path,
        data_dir=data_dir,
        sink=SinkConfig(google_contacts=True, dry_run=True),
    )
    orchestrator = BatchOrchestrator(config)
    monkeypatch.setattr(orchestrator, "adapter", SyntheticSkillAdapter())
    run_dir = orchestrator.process_source(str(source_dir), dry_run=True, workers=1)
    service = BusinessCardService(config)
    candidate_id = str(service.child_review_queue(run_id=run_dir.name)[0]["candidate_id"])
    service.submit_child_review(
        run_id=run_dir.name,
        candidate_id=candidate_id,
        reviewer="operator",
        action="approve_child_for_routing",
    )
    service.prepare_child_route(run_id=run_dir.name, candidate_id=candidate_id)
    service.record_child_sink_lookup_result(run_id=run_dir.name, candidate_id=candidate_id)
    service.assess_child_downstream_duplicates(run_id=run_dir.name, candidate_id=candidate_id)
    service.child_sink_plan_gate(run_id=run_dir.name, candidate_id=candidate_id)
    handoff = service.child_selected_target_handoff(
        run_id=run_dir.name,
        candidate_id=candidate_id,
        sink="google_contacts",
        operator="operator",
    )["handoff"]
    template = handoff["operator_response_template"]
    response = (
        f"run_id={template['run_id']} job_id={template['job_id']} "
        f"candidate_id={template['candidate_id']} work_item_id={template['work_item_id']} "
        "sink=google_contacts operator=operator scope=write "
        "safety_confirmation='approved google contacts target profile'"
    )

    assert main(
        [
            "--config",
            str(config_path),
            "reviews",
            "child-validate-selected-target-response",
            candidate_id,
            "--run-id",
            run_dir.name,
            "--response",
            response,
            "--json",
        ]
    ) == 0
    validation = json.loads(capsys.readouterr().out)

    assert main(
        [
            "--config",
            str(config_path),
            "reviews",
            "child-selected-target-execution-checklist",
            candidate_id,
            "--run-id",
            run_dir.name,
            "--response",
            response,
            "--json",
        ]
    ) == 0
    checklist = json.loads(capsys.readouterr().out)

    assert main(
        [
            "--config",
            str(config_path),
            "reviews",
            "child-selected-target-command-copy-packet",
            candidate_id,
            "--run-id",
            run_dir.name,
            "--response",
            response,
            "--acknowledgement",
            (
                f"I acknowledge run_id={run_dir.name} candidate_id={candidate_id} "
                "sink=google_contacts operator=operator ready to copy"
            ),
            "--json",
        ]
    ) == 0
    command_copy = json.loads(capsys.readouterr().out)

    assert main(
        [
            "--config",
            str(config_path),
            "reviews",
            "child-selected-target-audit",
            candidate_id,
            "--run-id",
            run_dir.name,
            "--json",
        ]
    ) == 0
    audit = json.loads(capsys.readouterr().out)

    assert main(
        [
            "--config",
            str(config_path),
            "reviews",
            "child-abandon-selected-target",
            candidate_id,
            "--run-id",
            run_dir.name,
            "--operator",
            "operator",
            "--reason",
            "replace child target",
            "--json",
        ]
    ) == 0
    abandonment = json.loads(capsys.readouterr().out)

    assert main(
        [
            "--config",
            str(config_path),
            "reviews",
            "child-selected-target-replacement-reset",
            candidate_id,
            "--run-id",
            run_dir.name,
            "--sink",
            "google_contacts",
            "--operator",
            "replacement-operator",
            "--json",
        ]
    ) == 0
    reset = json.loads(capsys.readouterr().out)

    assert main(
        [
            "--config",
            str(config_path),
            "reviews",
            "child-replacement-handoff-refresh",
            candidate_id,
            "--run-id",
            run_dir.name,
            "--sink",
            "google_contacts",
            "--operator",
            "replacement-operator",
            "--json",
        ]
    ) == 0
    refresh = json.loads(capsys.readouterr().out)
    replacement_template = refresh["refreshed_handoff"]["operator_response_template"]
    replacement_response = (
        f"run_id={replacement_template['run_id']} job_id={replacement_template['job_id']} "
        f"candidate_id={replacement_template['candidate_id']} "
        f"work_item_id={replacement_template['work_item_id']} "
        "sink=google_contacts operator=replacement-operator scope=write "
        "safety_confirmation='approved replacement google contacts target profile'"
    )

    assert main(
        [
            "--config",
            str(config_path),
            "reviews",
            "child-validate-replacement-response",
            candidate_id,
            "--run-id",
            run_dir.name,
            "--response",
            replacement_response,
            "--json",
        ]
    ) == 0
    replacement_validation = json.loads(capsys.readouterr().out)
    assert main(
        [
            "--config",
            str(config_path),
            "reviews",
            "child-replacement-execution-checklist",
            candidate_id,
            "--run-id",
            run_dir.name,
            "--response",
            replacement_response,
            "--json",
        ]
    ) == 0
    replacement_checklist = json.loads(capsys.readouterr().out)

    assert main(
        [
            "--config",
            str(config_path),
            "reviews",
            "child-replacement-command-copy-packet",
            candidate_id,
            "--run-id",
            run_dir.name,
            "--response",
            replacement_response,
            "--acknowledgement",
            (
                f"I acknowledge run_id={run_dir.name} candidate_id={candidate_id} "
                "sink=google_contacts operator=replacement-operator ready to copy"
            ),
            "--json",
        ]
    ) == 0
    replacement_command_copy = json.loads(capsys.readouterr().out)
    assert main(
        [
            "--config",
            str(config_path),
            "reviews",
            "child-replacement-closeout-status",
            candidate_id,
            "--run-id",
            run_dir.name,
            "--json",
        ]
    ) == 0
    closeout = json.loads(capsys.readouterr().out)
    assert main(
        [
            "--config",
            str(config_path),
            "reviews",
            "bundle",
            "--run-id",
            run_dir.name,
            "--json",
        ]
    ) == 0
    bundle = json.loads(capsys.readouterr().out)
    assert main(["--config", str(config_path), "operator-dashboard", "--run-id", run_dir.name, "--json"]) == 0
    dashboard = json.loads(capsys.readouterr().out)

    assert validation["state"] == "ready_for_no_live_child_checklist"
    assert validation["writes_attempted"] == 0
    assert validation["network_calls_made"] == 0
    assert checklist["state"] == "ready_for_operator_review"
    assert checklist["selected_target_created"] is False
    assert checklist["executable_live_command"] is None
    assert checklist["writes_attempted"] == 0
    assert checklist["network_calls_made"] == 0
    assert command_copy["schema"] == "business-card-watchdog.child-selected-target-command-copy-packet.v1"
    assert command_copy["state"] == "ready_for_operator_copy"
    assert command_copy["acknowledgement_ok"] is True
    assert command_copy["command_copy_text"].startswith("reviews child-selected-target-execution-checklist")
    assert command_copy["executable_live_command"] is None
    assert command_copy["writes_attempted"] == 0
    assert command_copy["network_calls_made"] == 0
    assert audit["schema"] == "business-card-watchdog.child-selected-target-audit.v1"
    assert audit["state"] == "ready"
    assert audit["selected_target_exists"] is True
    assert audit["replacement_requires_abandonment"] is False
    assert audit["writes_attempted"] == 0
    assert audit["network_calls_made"] == 0
    assert abandonment["schema"] == "business-card-watchdog.child-selected-target-abandonment.v1"
    assert abandonment["state"] == "abandoned"
    assert abandonment["writes_attempted"] == 0
    assert abandonment["network_calls_made"] == 0
    assert reset["schema"] == "business-card-watchdog.child-selected-target-replacement-reset.v1"
    assert reset["state"] == "ready_for_replacement_preview"
    assert reset["replacement_unblocked"] is True
    assert reset["replacement_requires_abandonment"] is False
    assert reset["writes_attempted"] == 0
    assert reset["network_calls_made"] == 0
    assert refresh["schema"] == "business-card-watchdog.child-replacement-handoff-refresh.v1"
    assert refresh["state"] == "ready_for_replacement_handoff"
    assert refresh["refreshed_handoff"]["operator"] == "replacement-operator"
    assert refresh["staleness"]["state"] == "stale"
    assert refresh["writes_attempted"] == 0
    assert refresh["network_calls_made"] == 0
    assert replacement_validation["schema"] == "business-card-watchdog.child-replacement-response-validation.v1"
    assert replacement_validation["state"] == "ready_for_no_live_replacement_checklist"
    assert replacement_validation["stale_enforcement"]["staleness_state"] == "stale"
    assert replacement_validation["parsed_response"]["operator"] == "replacement-operator"
    assert replacement_validation["selected_target_created"] is False
    assert replacement_validation["writes_attempted"] == 0
    assert replacement_validation["network_calls_made"] == 0
    assert replacement_checklist["schema"] == "business-card-watchdog.child-replacement-execution-checklist.v1"
    assert replacement_checklist["state"] == "ready_for_replacement_operator_review"
    assert replacement_checklist["executable_live_command"] is None
    assert replacement_checklist["writes_attempted"] == 0
    assert replacement_checklist["network_calls_made"] == 0
    assert replacement_command_copy["schema"] == "business-card-watchdog.child-replacement-command-copy-packet.v1"
    assert replacement_command_copy["state"] == "ready_for_replacement_operator_copy"
    assert replacement_command_copy["command_copy_text"].startswith("reviews child-replacement-execution-checklist")
    assert replacement_command_copy["executable_live_command"] is None
    assert replacement_command_copy["writes_attempted"] == 0
    assert replacement_command_copy["network_calls_made"] == 0
    assert closeout["schema"] == "business-card-watchdog.child-replacement-closeout-status.v1"
    assert closeout["state"] == "ready_for_operator_closeout"
    assert closeout["rollup"]["predecessor_artifacts_stale"] is True
    assert closeout["rollup"]["replacement_copy_ready"] is True
    assert closeout["rollup"]["executable_live_command"] is None
    assert closeout["writes_attempted"] == 0
    assert closeout["network_calls_made"] == 0
    bundle_entry = next(entry for entry in bundle["entries"] if entry["job_id"] == closeout["job_id"])
    assert bundle_entry["child_replacement_status"]["state"] == "ready_for_operator_closeout"
    assert bundle["groups"]["by_child_replacement_state"]["ready_for_operator_closeout"]["count"] == 1
    assert dashboard["child_replacement_summary"]["closeout_count"] == 1
    assert dashboard["child_replacement_summary"]["ready_count"] == 1


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
    assert payload["commands"]["selected_target_approval_boundary"] == (
        f"runs selected-target-approval-boundary {run_id} "
        "--operator <operator> --response <operator-response> --no-write --json"
    )
    assert payload["commands"]["selected_target_command_copy_packet"] == (
        f"runs selected-target-command-copy-packet {run_id} "
        "--operator <operator> --response <operator-response> "
        "--acknowledgement <operator-acknowledgement> --json"
    )
    assert payload["review_counts"]["needs_review"] == 1
    assert payload["next_action_summary"]["by_action"] == {"review_contact": 1}
    assert payload["live_pilot_handoff_summary"]["action_counts"] == {"no_live_candidate": 1}
    assert payload["live_pilot_handoff_summary"]["operator_required_count"] == 0
    assert payload["live_pilot_handoff_summary"]["pilot_checklist_rollup"]["checklist_job_count"] == 0
    assert payload["live_pilot_handoff_summary"]["pilot_checklist_rollup"]["step_count"] == 0
    assert payload["latest_review_routing_drill"]["state"] == "not_run"
    assert payload["latest_review_routing_drill"]["has_drill"] is False
    assert len(payload["live_pilot_summary"]["explicit_stop_conditions"]) == 3
    assert "Do not run live lookup, live write, or live readback from this status report." in (
        payload["live_pilot_summary"]["explicit_stop_conditions"]
    )
    assert len(payload["live_pilot_handoff_summary"]["operator_stop_conditions"]) == 4
    assert "Do not create selected_live_target.json unless the selected card/contact is safe" in (
        payload["live_pilot_handoff_summary"]["operator_stop_conditions"][1]
    )
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
    assert "Multi-card preclassification drill: drills multi-card-preclassification --json" in text
    assert "Review routing drill: drills review-routing --json" in text
    assert "Live pilot rehearsal drill: drills live-pilot-rehearsal --json" in text
    assert "API routes:" in text
    assert f"Next actions: GET /actions/next?run_id={run_id}&limit=20" in text
    assert "Multi-card preclassification drill: POST /drills/multi-card-preclassification" in text
    assert "Review routing drill: POST /drills/review-routing" in text
    assert "Live pilot rehearsal drill: POST /drills/live-pilot-rehearsal" in text
    assert f"Live pilot handoff: GET /runs/{run_id}/live-pilot-handoff?write=false" in text
    assert f"Live pilot validate response: POST /runs/{run_id}/live-pilot-operator-response-validation" in text
    assert f"Selected target approval boundary: POST /runs/{run_id}/selected-target-approval-boundary" in text
    assert f"Selected target command copy packet: POST /runs/{run_id}/selected-target-command-copy-packet" in text
    assert "MCP tools:" in text
    assert f"Operator dashboard: business_card_watchdog_operator_dashboard args=run_id={run_id}" in text
    assert f"Next actions: business_card_watchdog_next_actions args=limit=20, run_id={run_id}" in text
    assert (
        "Multi-card preclassification drill: "
        "business_card_watchdog_multi_card_preclassification_drill"
    ) in text
    assert "Review routing drill: business_card_watchdog_review_routing_drill" in text
    assert "Live pilot rehearsal drill: business_card_watchdog_live_pilot_rehearsal_drill" in text
    assert "Latest review routing drill: not_run run=none readback=none manual=none" in text
    assert f"Live pilot status: business_card_watchdog_live_pilot_status args=run_id={run_id}, write=False" in text
    assert "Safe next actions: 6" in text
    assert f"inspect_live_pilot_status: runs live-pilot-status {run_id} --no-write --json" in text
    assert f"inspect_live_pilot_handoff: runs live-pilot-handoff {run_id} --no-write --json" in text
    assert "run_fixture_review_routing_drill: drills review-routing --json" in text
    assert "Live pilot stop conditions: 3" in text
    assert "Do not run live lookup, live write, or live readback from this status report." in text
    assert "Live handoff stop conditions: 4" in text
    assert "Do not create selected_live_target.json unless the selected card/contact is safe" in text
    assert (
        "Live pilot validate response: "
        f"business_card_watchdog_live_pilot_operator_response_validation "
        f"args=response=<operator-response>, run_id={run_id}"
    ) in text
    assert (
        "Selected target approval boundary: "
        f"business_card_watchdog_selected_target_approval_boundary "
        f"args=operator=<operator>, response=<operator-response>, run_id={run_id}, write=False"
    ) in text
    assert (
        "Selected target command copy packet: "
        f"business_card_watchdog_selected_target_command_copy_packet "
        "args=acknowledgement=<operator-acknowledgement>, operator=<operator>, "
        f"response=<operator-response>, run_id={run_id}"
    ) in text
    assert "Next actions: total=1 safe=0 explicit=1" in text
    assert "action=review_contact" in text
    assert "Live handoff: state=blocked operator_required=0 response_templates=0" in text
    assert "Live pilot checklist: jobs=0 steps=0 live_calls=0 sink_writes=0 explicit_steps=0" in text
    assert f"Live pilot status: runs live-pilot-status {run_id} --no-write --json" in text
    assert (
        f"Live pilot validate response: runs live-pilot-validate-response {run_id} "
        "--response <operator-response> --json"
    ) in text
    assert (
        f"Selected target approval boundary: runs selected-target-approval-boundary {run_id} "
        "--operator <operator> --response <operator-response> --no-write --json"
    ) in text
    assert (
        f"Selected target command copy packet: runs selected-target-command-copy-packet {run_id} "
        "--operator <operator> --response <operator-response> "
        "--acknowledgement <operator-acknowledgement> --json"
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
    assert payload["commands"]["live_pilot_status"] == (
        f"bcw --config {config_path} runs live-pilot-status {run_id} --no-write --json"
    )
    assert payload["commands"]["live_pilot_handoff"] == (
        f"bcw --config {config_path} runs live-pilot-handoff {run_id}"
    )
    assert payload["commands"]["review_routing_drill"] == (
        f"bcw --config {config_path} drills review-routing --json"
    )
    assert payload["latest_review_routing_drill"]["state"] == "not_run"
    assert payload["live_pilot_checklist_rollup"]["checklist_job_count"] == 0
    assert payload["live_pilot_checklist_rollup"]["step_count"] == 0
    assert any(action["action"] == "inspect_live_pilot_status" for action in payload["safe_next_actions"])
    assert any(action["action"] == "inspect_live_pilot_handoff" for action in payload["safe_next_actions"])
    assert any(action["action"] == "run_fixture_review_routing_drill" for action in payload["safe_next_actions"])
    assert payload["network_calls_made"] == 0
    assert payload["writes_attempted"] == 0

    assert main(["--config", str(config_path), "service", "recovery", "--run-id", run_id]) == 0
    text = capsys.readouterr().out
    assert "Latest review routing drill: not_run run=none readback=none" in text
    assert "Live pilot checklist: jobs=0 steps=0 live_calls=0 sink_writes=0" in text
    assert "Service recovery:" in text
    assert f"Run: {run_id}" in text
    assert "Restart: systemctl --user restart business-card-watchdog.service" in text
    assert f"Review routing drill: bcw --config {config_path} drills review-routing --json" in text
    assert "Resume: bcw --config" in text
    assert f"Live pilot status: bcw --config {config_path} runs live-pilot-status {run_id} --no-write --json" in text
    assert f"Live pilot handoff: bcw --config {config_path} runs live-pilot-handoff {run_id}" in text
    assert f"inspect_live_pilot_status: bcw --config {config_path} runs live-pilot-status {run_id}" in text
    assert f"inspect_live_pilot_handoff: bcw --config {config_path} runs live-pilot-handoff {run_id}" in text
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
        "--operator <operator> --scope lookup --safety-confirmation <tenant-profile-account-confirmation> --json"
    )
    assert candidate["commands"]["validate_operator_response"] == (
        f"runs live-pilot-validate-response {run_id} --response <operator-response> --json"
    )
    assert payload["commands"]["live_readiness_audit"] == f"live-readiness-audit --run-id {run_id}"
    assert payload["commands"]["live_selection_requirements"] == f"live-selection-requirements --run-id {run_id}"
    assert payload["commands"]["live_pilot_handoff"] == f"runs live-pilot-handoff {run_id}"
    assert payload["commands"]["validate_operator_response"] == (
        f"runs live-pilot-validate-response {run_id} --response <operator-response> --json"
    )

    assert main(["--config", str(config_path), "live-target-candidates", "--run-id", run_id]) == 0
    text = capsys.readouterr().out
    assert "Live target candidates: 1" in text
    assert "sink=google_contacts" in text
    assert f"Inspect job: jobs show {candidate['job_id']} --run-id {run_id}" in text
    assert f"Lookup readiness: sinks lookup-readiness {candidate['job_id']} --run-id {run_id} --sink google_contacts" in text
    assert (
        f"Select lookup target: sinks select-live-target {candidate['job_id']} --run-id {run_id} "
        "--sink google_contacts --operator <operator> --scope lookup --safety-confirmation <tenant-profile-account-confirmation> --json"
    ) in text
    assert (
        f"Validate response: runs live-pilot-validate-response {run_id} "
        "--response <operator-response> --json"
    ) in text
    assert f"Live readiness audit: live-readiness-audit --run-id {run_id}" in text
    assert f"Selection requirements: live-selection-requirements --run-id {run_id}" in text
    assert f"Live pilot handoff: runs live-pilot-handoff {run_id}" in text
    assert "{" not in text

    assert main(["--config", str(config_path), "operator-dashboard", "--run-id", run_id, "--json"]) == 0
    dashboard = json.loads(capsys.readouterr().out)
    dashboard_entry = dashboard["live_pilot_handoff_summary"]["operator_entries"][0]
    checklist_rollup = dashboard["live_pilot_handoff_summary"]["pilot_checklist_rollup"]
    assert dashboard_entry["job_id"] == candidate["job_id"]
    assert checklist_rollup["schema"] == "business-card-watchdog.live-pilot-checklist-rollup.v1"
    assert checklist_rollup["operator_required_job_count"] == 1
    assert checklist_rollup["checklist_job_count"] == 1
    assert checklist_rollup["step_count"] == 5
    assert checklist_rollup["live_call_count"] == 1
    assert checklist_rollup["sink_write_step_count"] == 0
    assert checklist_rollup["explicit_operator_step_count"] == 2
    assert checklist_rollup["sample_jobs"][0]["job_id"] == candidate["job_id"]
    sequence_summary = dashboard_entry["pilot_command_sequence_summary"]
    assert sequence_summary["schema"] == "business-card-watchdog.pilot-command-sequence-summary.v1"
    assert sequence_summary["safe_inspection_step_count"] == 3
    assert sequence_summary["explicit_operator_step_count"] == 2
    assert sequence_summary["live_call_step_count"] == 1
    assert sequence_summary["sink_write_step_count"] == 0
    assert sequence_summary["next_safe_inspection_step"] == "validate_operator_response"
    assert sequence_summary["next_explicit_operator_step"] == "create_selected_target"
    execution_packet = dashboard["live_pilot_handoff_summary"]["execution_packet"]
    assert execution_packet["schema"] == "business-card-watchdog.operator-dashboard.live-pilot-execution-packet.v1"
    assert execution_packet["state"] == "operator_required"
    assert execution_packet["operator_required_count"] == 1
    assert execution_packet["next_safe_command"] == dashboard_entry["validation_command_prefilled"]
    assert execution_packet["next_explicit_operator_command"] == (
        f"sinks select-live-target {candidate['job_id']} --run-id {run_id} "
        "--sink google_contacts --operator <operator> --scope lookup "
        "--safety-confirmation <tenant-profile-account-confirmation>"
    )
    assert execution_packet["forbidden_live_or_sink_write_from_dashboard"] is True
    assert execution_packet["writes_attempted"] == 0
    assert execution_packet["network_calls_made"] == 0
    assert dashboard_entry["validation_command_prefilled"] == (
        f"runs live-pilot-validate-response {run_id} "
        f"--response 'run_id={run_id} job_id={candidate['job_id']} sink=google_contacts "
        "operator=<operator> scope=lookup safety_confirmation=<tenant-profile-account-confirmation>' --json"
    )

    assert main(["--config", str(config_path), "operator-dashboard", "--run-id", run_id]) == 0
    dashboard_text = capsys.readouterr().out
    assert "Live pilot execution packet: state=operator_required operator_required=1" in dashboard_text
    assert "Live pilot execution policy: forbid_live_or_sink=True" in dashboard_text
    assert "next_safe=runs live-pilot-validate-response" in dashboard_text
    assert "next_explicit=sinks select-live-target" in dashboard_text
    assert "{" not in dashboard_text

    assert main(["--config", str(config_path), "service", "recovery", "--run-id", run_id, "--json"]) == 0
    recovery = json.loads(capsys.readouterr().out)
    assert recovery["live_pilot_checklist_rollup"]["checklist_job_count"] == 1
    assert recovery["live_pilot_checklist_rollup"]["step_count"] == 5
    assert recovery["live_pilot_checklist_rollup"]["live_call_count"] == 1

    assert main(["--config", str(config_path), "operator-dashboard", "--run-id", run_id]) == 0
    dashboard_text = capsys.readouterr().out
    assert "Live pilot checklist: jobs=1 steps=5 live_calls=1 sink_writes=0 explicit_steps=2" in dashboard_text
    assert "Live handoff operator entries:" in dashboard_text
    assert "Sequence: safe=3 explicit=2 live=1 sink_writes=0" in dashboard_text
    assert "next_safe=validate_operator_response next_explicit=create_selected_target" in dashboard_text
    assert (
        f"Validate prefilled response: runs live-pilot-validate-response {run_id} "
        f"--response 'run_id={run_id} job_id={candidate['job_id']} sink=google_contacts "
        "operator=<operator> scope=lookup safety_confirmation=<tenant-profile-account-confirmation>' --json"
    ) in dashboard_text
    assert "{" not in dashboard_text


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
    assert payload["commands"]["validate_operator_response"] == (
        f"runs live-pilot-validate-response {run_id} --response <operator-response> --json"
    )

    assert main(["--config", str(config_path), "live-readiness-audit", "--run-id", run_id, "--no-write"]) == 0
    text = capsys.readouterr().out
    assert "Live readiness audit:" in text
    assert f"Run: {run_id}" in text
    assert f"Target candidates: live-target-candidates --run-id {run_id}" in text
    assert f"Selection requirements: live-selection-requirements --run-id {run_id}" in text
    assert f"Live pilot handoff: runs live-pilot-handoff {run_id}" in text
    assert (
        f"Validate response: runs live-pilot-validate-response {run_id} "
        "--response <operator-response> --json"
    ) in text
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
        "operator=<operator> scope=lookup safety_confirmation=<tenant-profile-account-confirmation>"
    )
    assert entry["commands"]["selection_packet"] == (
        f"sinks live-selection-packet {entry['job_id']} --run-id {run_id} --sink google_contacts --operator <operator>"
    )
    assert entry["commands"]["validate_operator_response"] == (
        f"runs live-pilot-validate-response {run_id} --response <operator-response> --json"
    )
    assert entry["commands"]["validate_operator_response_prefilled"] == (
        f"runs live-pilot-validate-response {run_id} "
        f"--response 'run_id={run_id} job_id={entry['job_id']} sink=google_contacts "
        "operator=<operator> scope=lookup safety_confirmation=<tenant-profile-account-confirmation>' --json"
    )
    assert payload["commands"]["live_target_candidates"] == f"live-target-candidates --run-id {run_id}"
    assert payload["commands"]["live_readiness_audit"] == f"live-readiness-audit --run-id {run_id}"
    assert payload["commands"]["live_selection_requirements"] == f"live-selection-requirements --run-id {run_id}"
    assert payload["commands"]["live_pilot_handoff"] == f"runs live-pilot-handoff {run_id}"
    assert payload["commands"]["validate_operator_response"] == (
        f"runs live-pilot-validate-response {run_id} --response <operator-response> --json"
    )

    assert main(["--config", str(config_path), "live-selection-requirements", "--run-id", run_id, "--no-write"]) == 0
    text = capsys.readouterr().out
    assert "Live selection requirements:" in text
    assert f"Run: {run_id}" in text
    assert "target=none" in text
    assert "Validate prefilled response: runs live-pilot-validate-response" in text
    assert "abandonment=none" in text
    assert "missing=operator,scope,safety_confirmation" in text
    assert (
        f"Selection packet: sinks live-selection-packet {entry['job_id']} --run-id {run_id} "
        "--sink google_contacts --operator <operator>"
    ) in text
    assert (
        f"Select target: sinks select-live-target {entry['job_id']} --run-id {run_id} "
        "--sink google_contacts --operator <operator> --scope lookup --safety-confirmation <tenant-profile-account-confirmation> --json"
    ) in text
    assert (
        f"Operator response: run_id={run_id} job_id={entry['job_id']} sink=google_contacts "
        "operator=<operator> scope=lookup safety_confirmation=<tenant-profile-account-confirmation>"
    ) in text
    assert f"Live target candidates: live-target-candidates --run-id {run_id}" in text
    assert f"Live readiness audit: live-readiness-audit --run-id {run_id}" in text
    assert f"Selection requirements: live-selection-requirements --run-id {run_id}" in text
    assert f"Live pilot handoff: runs live-pilot-handoff {run_id}" in text
    assert "{" not in text


def test_cli_operator_selected_live_smoke_preflight_reports_blocked_boundary(
    tmp_path: Path,
    capsys,
) -> None:
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

    assert main(
        [
            "--config",
            str(config_path),
            "operator-selected-live-smoke-preflight",
            "--run-id",
            run_id,
            "--sink",
            "google_contacts",
            "--json",
        ]
    ) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema"] == "business-card-watchdog.operator-selected-live-smoke-preflight.v1"
    assert payload["state"] == "needs_preparation"
    assert payload["run_id"] == run_id
    assert payload["sink"] == "google_contacts"
    assert payload["entry_count"] == 1
    assert payload["blocked_entry_count"] == 1
    assert payload["writes_attempted"] == 0
    assert payload["network_calls_made"] == 0
    assert Path(payload["preflight_path"]).exists()

    assert main(
        [
            "--config",
            str(config_path),
            "operator-selected-live-smoke-preflight",
            "--run-id",
            run_id,
            "--sink",
            "google_contacts",
            "--no-write",
        ]
    ) == 2
    text = capsys.readouterr().out
    assert "Operator-selected live smoke preflight: needs_preparation" in text
    assert f"Run: {run_id}" in text
    assert "Blocked reasons:" in text
    assert "Checklist:" in text
    assert "Selection requirements: live-selection-requirements" in text
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
    assert payload["operator_response_template"] == (
        f"run_id={run_id} job_id={job_id} sink=google_contacts "
        "operator=tester scope=lookup safety_confirmation=<tenant-profile-account-confirmation>"
    )
    assert payload["copyable_approval_fields"]["operator"] == "tester"
    assert payload["commands"]["validate_operator_response"] == (
        f"runs live-pilot-validate-response {run_id} --response <operator-response> --json"
    )
    assert payload["commands"]["validate_operator_response_prefilled"] == (
        f"runs live-pilot-validate-response {run_id} "
        f"--response 'run_id={run_id} job_id={job_id} sink=google_contacts "
        "operator=tester scope=lookup safety_confirmation=<tenant-profile-account-confirmation>' --json"
    )
    assert [row["step"] for row in payload["pilot_command_checklist"]] == [
        "validate_operator_response",
        "create_selected_target",
        "selected_target_audit",
        "lookup_smoke_handoff",
        "live_lookup_pilot",
    ]
    assert payload["pilot_command_checklist"][3]["live_call"] is False
    assert payload["pilot_command_checklist"][4]["live_call"] is True
    assert payload["pilot_command_checklist"][4]["writes_sink"] is False

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
    assert (
        f"Operator response: run_id={run_id} job_id={job_id} sink=google_contacts "
        "operator=tester scope=lookup safety_confirmation=<tenant-profile-account-confirmation>"
    ) in text
    assert (
        f"Validate response: runs live-pilot-validate-response {run_id} "
        "--response <operator-response> --json"
    ) in text
    assert (
        f"Validate prefilled response: runs live-pilot-validate-response {run_id} "
        f"--response 'run_id={run_id} job_id={job_id} sink=google_contacts "
        "operator=tester scope=lookup safety_confirmation=<tenant-profile-account-confirmation>' --json"
    ) in text
    assert "Create selected target: sinks select-live-target" in text
    assert "Pilot checklist: 5" in text
    assert "validate_operator_response: live=False writes_sink=False" in text
    assert "lookup_smoke_handoff: live=False writes_sink=False" in text
    assert "live_lookup_pilot: live=True writes_sink=False" in text
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
        "operator=tester scope=lookup safety_confirmation=<tenant-profile-account-confirmation>"
    )
    assert status["entries"][0]["commands"]["validate_operator_response"] == (
        f"runs live-pilot-validate-response {run_id} --response <operator-response> --json"
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
    assert "Stop conditions: 3" in text_status
    assert "This status report does not create selected_live_target.json" in text_status
    assert "Do not run live lookup, live write, or live readback" in text_status
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
        "operator=tester scope=lookup safety_confirmation=<tenant-profile-account-confirmation>"
    )
    assert handoff["entries"][0]["pilot_command_checklist_summary"]["step_count"] == 5
    assert handoff["entries"][0]["pilot_command_checklist_summary"]["live_call_count"] == 1
    sequence = handoff["entries"][0]["pilot_command_sequence"]
    assert sequence["schema"] == "business-card-watchdog.pilot-command-sequence.v1"
    assert sequence["safe_inspection_step_count"] == 3
    assert sequence["explicit_operator_step_count"] == 2
    assert sequence["live_call_step_count"] == 1
    assert sequence["sink_write_step_count"] == 0
    assert sequence["safe_inspection_steps"][0]["step"] == "validate_operator_response"
    assert sequence["explicit_operator_steps"][0]["step"] == "create_selected_target"
    assert sequence["live_call_steps"][0]["step"] == "live_lookup_pilot"
    assert sequence["execution_policy"]["requires_operator_before_live_call_steps"] is True
    assert handoff["operator_response_template_count"] == 1
    assert handoff["operator_response_templates"][0]["template"] == (
        f"run_id={run_id} job_id={job_id} sink=google_contacts "
        "operator=tester scope=lookup safety_confirmation=<tenant-profile-account-confirmation>"
    )
    assert handoff["operator_response_templates"][0]["command"] == (
        f"sinks execute-lookup-smoke {job_id} --run-id {run_id} --json"
    )
    assert handoff["operator_response_templates"][0]["validation_command"] == (
        f"runs live-pilot-validate-response {run_id} --response <operator-response> --json"
    )
    assert handoff["operator_response_templates"][0]["validation_command_prefilled"] == (
        f"runs live-pilot-validate-response {run_id} "
        f"--response 'run_id={run_id} job_id={job_id} sink=google_contacts "
        "operator=tester scope=lookup safety_confirmation=<tenant-profile-account-confirmation>' --json"
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
        "operator=tester scope=lookup safety_confirmation=<tenant-profile-account-confirmation>"
    ) in text_handoff
    assert (
        f"Validate prefilled response: runs live-pilot-validate-response {run_id} "
        f"--response 'run_id={run_id} job_id={job_id} sink=google_contacts "
        "operator=tester scope=lookup safety_confirmation=<tenant-profile-account-confirmation>' --json"
    ) in text_handoff
    assert "Operator stop conditions: 4" in text_handoff
    assert "Operator must choose exactly one run_id, job_id, sink, scope" in text_handoff
    assert "Do not create selected_live_target.json" in text_handoff
    assert "Do not run live lookup, live write, or live readback" in text_handoff
    assert "{" not in text_handoff

    assert (
        main(
            [
                "--config",
                str(config_path),
                "runs",
                "live-pilot-approval-packet",
                run_id,
                "--job-id",
                job_id,
                "--json",
            ]
        )
        == 0
    )
    approval_packet = json.loads(capsys.readouterr().out)
    assert approval_packet["schema"] == "business-card-watchdog.live-pilot-approval-packet.v1"
    assert approval_packet["state"] == "ready"
    assert approval_packet["entry_count"] == 1
    assert approval_packet["entries"][0]["job_id"] == job_id
    assert approval_packet["entries"][0]["operator"] == "tester"
    assert approval_packet["entries"][0]["scope"] == "lookup"
    assert approval_packet["entries"][0]["validation_command_prefilled"] == handoff["entries"][0]["commands"][
        "validate_operator_response_prefilled"
    ]
    assert approval_packet["creates_selected_live_target"] is False
    assert approval_packet["writes_attempted"] == 0
    assert approval_packet["network_calls_made"] == 0

    assert (
        main(
            [
                "--config",
                str(config_path),
                "runs",
                "live-pilot-approval-packet",
                run_id,
                "--job-id",
                job_id,
            ]
        )
        == 0
    )
    approval_text = capsys.readouterr().out
    assert "State: ready" in approval_text
    assert "Approval entries: 1" in approval_text
    assert f" - {job_id} sink=google_contacts scope=lookup next=request_live_lookup_smoke" in approval_text
    assert "Validate prefilled response: runs live-pilot-validate-response" in approval_text
    assert "Creates selected target: False" in approval_text
    assert "Stop conditions: 4" in approval_text
    assert "{" not in approval_text

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
                "selected-live-target-preflight",
                run_id,
                "--response",
                response,
                "--json",
            ]
        )
        == 0
    )
    preflight = json.loads(capsys.readouterr().out)
    assert preflight["schema"] == "business-card-watchdog.selected-live-target-preflight.v1"
    assert preflight["state"] == "blocked"
    assert preflight["would_create_selected_live_target"] is False
    assert preflight["creates_selected_live_target"] is False
    assert preflight["select_target_command"] is None
    assert "selected_live_target already exists" in preflight["blocked_reasons"][0]
    assert preflight["writes_attempted"] == 0
    assert preflight["network_calls_made"] == 0

    assert (
        main(
            [
                "--config",
                str(config_path),
                "runs",
                "selected-live-target-preflight",
                run_id,
                "--response",
                response,
            ]
        )
        == 0
    )
    preflight_text = capsys.readouterr().out
    assert "State: blocked" in preflight_text
    assert "Would create selected target: False" in preflight_text
    assert "Creates selected target: False" in preflight_text
    assert "selected_live_target already exists" in preflight_text
    assert "Stop conditions: 3" in preflight_text
    assert "{" not in preflight_text

    assert (
        main(
            [
                "--config",
                str(config_path),
                "runs",
                "selected-live-target-preview",
                run_id,
                "--response",
                response,
                "--json",
            ]
        )
        == 0
    )
    preview = json.loads(capsys.readouterr().out)
    assert preview["schema"] == "business-card-watchdog.selected-live-target-artifact-preview.v1"
    assert preview["state"] == "blocked"
    assert preview["artifact_preview"] is None
    assert preview["would_create_selected_live_target"] is False
    assert preview["creates_selected_live_target"] is False
    assert "selected_live_target already exists" in preview["blocked_reasons"][0]
    assert preview["writes_attempted"] == 0
    assert preview["network_calls_made"] == 0

    assert (
        main(
            [
                "--config",
                str(config_path),
                "runs",
                "selected-live-target-preview",
                run_id,
                "--response",
                response,
            ]
        )
        == 0
    )
    preview_text = capsys.readouterr().out
    assert "State: blocked" in preview_text
    assert "Would create selected target: False" in preview_text
    assert "Creates selected target: False" in preview_text
    assert "selected_live_target already exists" in preview_text
    assert "Stop conditions: 3" in preview_text
    assert "{" not in preview_text

    assert (
        main(
            [
                "--config",
                str(config_path),
                "runs",
                "selected-live-target-from-response",
                run_id,
                "--response",
                response,
                "--json",
            ]
        )
        == 0
    )
    from_response = json.loads(capsys.readouterr().out)
    assert from_response["schema"] == "business-card-watchdog.selected-live-target-from-response.v1"
    assert from_response["state"] == "preview"
    assert from_response["write_selected_target"] is False
    assert from_response["preview"]["state"] == "blocked"
    assert from_response["target"] is None
    assert from_response["target_path"] is None
    assert from_response["creates_selected_live_target"] is False
    assert from_response["writes_attempted"] == 0
    assert from_response["network_calls_made"] == 0

    assert (
        main(
            [
                "--config",
                str(config_path),
                "runs",
                "selected-live-target-from-response",
                run_id,
                "--response",
                response,
            ]
        )
        == 0
    )
    from_response_text = capsys.readouterr().out
    assert "State: preview" in from_response_text
    assert "Write selected target: False" in from_response_text
    assert "Creates selected target: False" in from_response_text
    assert "Preview state: blocked" in from_response_text
    assert "Stop conditions: 3" in from_response_text
    assert "{" not in from_response_text

    assert (
        main(
            [
                "--config",
                str(config_path),
                "runs",
                "selected-live-target-handoff-from-response",
                run_id,
                "--response",
                response,
                "--json",
            ]
        )
        == 0
    )
    handoff = json.loads(capsys.readouterr().out)
    assert handoff["schema"] == "business-card-watchdog.selected-live-target-handoff-from-response.v1"
    assert handoff["state"] == "audit_blocked"
    assert handoff["validation_state"] == "ready_for_live_lookup_request"
    assert handoff["selected_target_audit"]["state"] == "blocked"
    assert handoff["write_audit"] is False
    assert handoff["audit_written"] is False
    assert handoff["creates_selected_live_target"] is False
    assert handoff["writes_attempted"] == 0
    assert handoff["network_calls_made"] == 0

    assert (
        main(
            [
                "--config",
                str(config_path),
                "runs",
                "selected-live-target-handoff-from-response",
                run_id,
                "--response",
                response,
            ]
        )
        == 0
    )
    handoff_text = capsys.readouterr().out
    assert "State: audit_blocked" in handoff_text
    assert "Write audit: False" in handoff_text
    assert "Audit written: False" in handoff_text
    assert "Creates selected target: False" in handoff_text
    assert "Stop conditions: 3" in handoff_text
    assert "{" not in handoff_text

    assert (
        main(
            [
                "--config",
                str(config_path),
                "runs",
                "lookup-smoke-handoff-from-response",
                run_id,
                "--response",
                response,
                "--json",
            ]
        )
        == 0
    )
    lookup_handoff = json.loads(capsys.readouterr().out)
    assert lookup_handoff["schema"] == "business-card-watchdog.lookup-smoke-handoff-from-response.v1"
    assert lookup_handoff["state"] == "handoff_blocked"
    assert lookup_handoff["job_id"] == job_id
    assert lookup_handoff["sink"] == "google_contacts"
    assert lookup_handoff["operator"] == "tester"
    assert lookup_handoff["lookup_smoke_handoff"]["state"] == "blocked"
    assert lookup_handoff["write_handoff"] is False
    assert lookup_handoff["handoff_written"] is False
    assert lookup_handoff["writes_attempted"] == 0
    assert lookup_handoff["network_calls_made"] == 0

    assert (
        main(
            [
                "--config",
                str(config_path),
                "runs",
                "lookup-smoke-handoff-from-response",
                run_id,
                "--response",
                response,
            ]
        )
        == 0
    )
    lookup_handoff_text = capsys.readouterr().out
    assert "State: handoff_blocked" in lookup_handoff_text
    assert "Write handoff: False" in lookup_handoff_text
    assert "Handoff written: False" in lookup_handoff_text
    assert "Lookup handoff state: blocked" in lookup_handoff_text
    assert "Stop conditions: 4" in lookup_handoff_text
    assert "{" not in lookup_handoff_text

    assert (
        main(
            [
                "--config",
                str(config_path),
                "runs",
                "selected-lookup-smoke-execution-packet-from-response",
                run_id,
                "--response",
                response,
                "--json",
            ]
        )
        == 0
    )
    execution_packet = json.loads(capsys.readouterr().out)
    assert execution_packet["schema"] == (
        "business-card-watchdog.selected-lookup-smoke-execution-packet-from-response.v1"
    )
    assert execution_packet["state"] == "blocked"
    assert execution_packet["execute_selected_lookup_smoke"] is False
    assert execution_packet["would_execute_selected_lookup_smoke"] is False
    assert execution_packet["smoke"] is None
    assert execution_packet["smoke_path"] is None
    assert execution_packet["writes_attempted"] == 0
    assert execution_packet["network_calls_made"] == 0

    assert (
        main(
            [
                "--config",
                str(config_path),
                "runs",
                "selected-lookup-smoke-execution-packet-from-response",
                run_id,
                "--response",
                response,
            ]
        )
        == 0
    )
    execution_packet_text = capsys.readouterr().out
    assert "State: blocked" in execution_packet_text
    assert "Execute selected lookup smoke: False" in execution_packet_text
    assert "Would execute selected lookup smoke: False" in execution_packet_text
    assert "Smoke path: none" in execution_packet_text
    assert "Stop conditions: 4" in execution_packet_text
    assert "{" not in execution_packet_text

    assert (
        main(
            [
                "--config",
                str(config_path),
                "runs",
                "selected-write-pilot-execution-packet-from-response",
                run_id,
                "--response",
                response,
                "--json",
            ]
        )
        == 0
    )
    write_packet = json.loads(capsys.readouterr().out)
    assert write_packet["schema"] == (
        "business-card-watchdog.selected-write-pilot-execution-packet-from-response.v1"
    )
    assert write_packet["state"] == "blocked"
    assert write_packet["execute_write_pilot"] is False
    assert write_packet["would_execute_write_pilot"] is False
    assert write_packet["write_pilot"] is None
    assert write_packet["write_pilot_path"] is None
    assert write_packet["writes_attempted"] == 0
    assert write_packet["network_calls_made"] == 0

    assert (
        main(
            [
                "--config",
                str(config_path),
                "runs",
                "selected-write-pilot-execution-packet-from-response",
                run_id,
                "--response",
                response,
            ]
        )
        == 0
    )
    write_packet_text = capsys.readouterr().out
    assert "State: blocked" in write_packet_text
    assert "Execute write pilot: False" in write_packet_text
    assert "Would execute write pilot: False" in write_packet_text
    assert "Write pilot path: none" in write_packet_text
    assert "{" not in write_packet_text

    assert (
        main(
            [
                "--config",
                str(config_path),
                "runs",
                "selected-readback-pilot-execution-packet-from-response",
                run_id,
                "--response",
                response,
                "--json",
            ]
        )
        == 0
    )
    readback_packet = json.loads(capsys.readouterr().out)
    assert readback_packet["schema"] == (
        "business-card-watchdog.selected-readback-pilot-execution-packet-from-response.v1"
    )
    assert readback_packet["state"] == "blocked"
    assert readback_packet["execute_readback_pilot"] is False
    assert readback_packet["would_execute_readback_pilot"] is False
    assert readback_packet["readback_pilot"] is None
    assert readback_packet["readback_pilot_path"] is None
    assert readback_packet["writes_attempted"] == 0
    assert readback_packet["network_calls_made"] == 0

    assert (
        main(
            [
                "--config",
                str(config_path),
                "runs",
                "selected-readback-pilot-execution-packet-from-response",
                run_id,
                "--response",
                response,
            ]
        )
        == 0
    )
    readback_packet_text = capsys.readouterr().out
    assert "State: blocked" in readback_packet_text
    assert "Execute readback pilot: False" in readback_packet_text
    assert "Would execute readback pilot: False" in readback_packet_text
    assert "Readback pilot path: none" in readback_packet_text
    assert "{" not in readback_packet_text

    assert (
        main(
            [
                "--config",
                str(config_path),
                "runs",
                "live-pilot-closeout-packet-from-response",
                run_id,
                "--response",
                response,
                "--json",
            ]
        )
        == 0
    )
    closeout_packet = json.loads(capsys.readouterr().out)
    assert closeout_packet["schema"] == "business-card-watchdog.live-pilot-closeout-packet-from-response.v1"
    assert closeout_packet["state"] == "closeout_incomplete"
    assert closeout_packet["write_closeout"] is False
    assert closeout_packet["closeout_written"] is False
    assert closeout_packet["closeout_path"] is None
    assert closeout_packet["closeout_report"]["state"] == "incomplete"
    assert closeout_packet["writes_attempted"] == 0
    assert closeout_packet["network_calls_made"] == 0

    assert (
        main(
            [
                "--config",
                str(config_path),
                "runs",
                "live-pilot-operator-workflow-packet-from-response",
                run_id,
                "--response",
                response,
                "--json",
            ]
        )
        == 0
    )
    workflow_packet = json.loads(capsys.readouterr().out)
    assert workflow_packet["schema"] == (
        "business-card-watchdog.live-pilot-operator-workflow-packet-from-response.v1"
    )
    assert workflow_packet["state"] == "workflow_blocked"
    assert workflow_packet["blocked_step_count"] >= 1
    assert workflow_packet["packets"]["live_pilot_closeout"]["state"] == "closeout_incomplete"
    assert workflow_packet["writes_attempted"] == 0
    assert workflow_packet["network_calls_made"] == 0

    assert (
        main(
            [
                "--config",
                str(config_path),
                "runs",
                "live-pilot-operator-rehearsal-from-response",
                run_id,
                "--response",
                response,
                "--json",
            ]
        )
        == 0
    )
    rehearsal = json.loads(capsys.readouterr().out)
    assert rehearsal["schema"] == "business-card-watchdog.live-pilot-operator-rehearsal-from-response.v1"
    assert rehearsal["state"] == "ready_for_explicit_operator_step"
    assert rehearsal["workflow_state"] == "workflow_blocked"
    assert rehearsal["rehearsal_steps"][0]["safe_to_auto_continue"] is True
    assert rehearsal["rehearsal_steps"][1]["requires_explicit_operator_action"] is True
    assert rehearsal["writes_attempted"] == 0
    assert rehearsal["network_calls_made"] == 0

    assert (
        main(
            [
                "--config",
                str(config_path),
                "runs",
                "live-pilot-readiness-export-from-response",
                run_id,
                "--response",
                response,
                "--no-write",
                "--json",
            ]
        )
        == 0
    )
    readiness_export = json.loads(capsys.readouterr().out)
    assert readiness_export["schema"] == "business-card-watchdog.live-pilot-readiness-export-from-response.v1"
    assert readiness_export["state"] == "ready_for_explicit_operator_step"
    assert readiness_export["write"] is False
    assert readiness_export["export_written"] is False
    assert readiness_export["export_path"] is None
    assert readiness_export["operator_response_redacted"]["raw_response_stored"] is False
    assert response not in json.dumps(readiness_export, sort_keys=True)
    assert readiness_export["writes_attempted"] == 0
    assert readiness_export["network_calls_made"] == 0

    assert (
        main(
            [
                "--config",
                str(config_path),
                "runs",
                "live-pilot-execution-checklist-from-response",
                run_id,
                "--response",
                response,
                "--json",
            ]
        )
        == 0
    )
    checklist = json.loads(capsys.readouterr().out)
    assert checklist["schema"] == "business-card-watchdog.live-pilot-execution-checklist-from-response.v1"
    assert checklist["state"] == "blocked"
    assert checklist["readiness_export_loaded"] is False
    assert checklist["executable_live_command"] is None
    assert checklist["writes_attempted"] == 0
    assert checklist["network_calls_made"] == 0

    assert (
        main(
            [
                "--config",
                str(config_path),
                "runs",
                "live-pilot-command-copy-packet-from-response",
                run_id,
                "--response",
                response,
                "--json",
            ]
        )
        == 0
    )
    command_copy_packet = json.loads(capsys.readouterr().out)
    assert command_copy_packet["schema"] == (
        "business-card-watchdog.live-pilot-command-copy-packet-from-response.v1"
    )
    assert command_copy_packet["state"] == "blocked"
    assert command_copy_packet["checklist_state"] == "blocked"
    assert command_copy_packet["acknowledgement_required"] is True
    assert command_copy_packet["acknowledgement_ok"] is False
    assert command_copy_packet["command_copy_text"] is None
    assert command_copy_packet["executable_live_command"] is None
    assert command_copy_packet["writes_attempted"] == 0
    assert command_copy_packet["network_calls_made"] == 0

    assert (
        main(
            [
                "--config",
                str(config_path),
                "runs",
                "live-pilot-closeout-packet-from-response",
                run_id,
                "--response",
                response,
            ]
        )
        == 0
    )
    closeout_packet_text = capsys.readouterr().out
    assert "State: closeout_incomplete" in closeout_packet_text
    assert "Closeout state: incomplete" in closeout_packet_text
    assert "Write closeout: False" in closeout_packet_text
    assert "Closeout written: False" in closeout_packet_text
    assert "{" not in closeout_packet_text

    assert (
        main(
            [
                "--config",
                str(config_path),
                "runs",
                "live-pilot-operator-workflow-packet-from-response",
                run_id,
                "--response",
                response,
            ]
        )
        == 0
    )
    workflow_packet_text = capsys.readouterr().out
    assert "State: workflow_blocked" in workflow_packet_text
    assert "Workflow steps: 6" in workflow_packet_text
    assert "Observed: writes=0 network=0" in workflow_packet_text
    assert "{" not in workflow_packet_text

    assert (
        main(
            [
                "--config",
                str(config_path),
                "runs",
                "live-pilot-operator-rehearsal-from-response",
                run_id,
                "--response",
                response,
            ]
        )
        == 0
    )
    rehearsal_text = capsys.readouterr().out
    assert "State: ready_for_explicit_operator_step" in rehearsal_text
    assert "Workflow state: workflow_blocked" in rehearsal_text
    assert "Rehearsal steps: 2" in rehearsal_text
    assert "Observed: writes=0 network=0" in rehearsal_text
    assert "{" not in rehearsal_text

    assert (
        main(
            [
                "--config",
                str(config_path),
                "runs",
                "live-pilot-readiness-export-from-response",
                run_id,
                "--response",
                response,
                "--no-write",
            ]
        )
        == 0
    )
    readiness_export_text = capsys.readouterr().out
    assert "State: ready_for_explicit_operator_step" in readiness_export_text
    assert "Write export: False" in readiness_export_text
    assert "Export written: False" in readiness_export_text
    assert "Raw response stored: False" in readiness_export_text
    assert "Rehearsal steps: 2" in readiness_export_text
    assert "Observed: writes=0 network=0" in readiness_export_text
    assert "{" not in readiness_export_text

    assert (
        main(
            [
                "--config",
                str(config_path),
                "runs",
                "live-pilot-execution-checklist-from-response",
                run_id,
                "--response",
                response,
            ]
        )
        == 0
    )
    checklist_text = capsys.readouterr().out
    assert "State: blocked" in checklist_text
    assert "Readiness export loaded: False" in checklist_text
    assert "Executable live command: none" in checklist_text
    assert "Checklist items: 5" in checklist_text
    assert "Observed: writes=0 network=0" in checklist_text
    assert "{" not in checklist_text

    assert (
        main(
            [
                "--config",
                str(config_path),
                "runs",
                "live-pilot-command-copy-packet-from-response",
                run_id,
                "--response",
                response,
            ]
        )
        == 0
    )
    command_copy_text = capsys.readouterr().out
    assert "State: blocked" in command_copy_text
    assert "Checklist state: blocked" in command_copy_text
    assert "Acknowledgement required: True" in command_copy_text
    assert "Acknowledgement ok: False" in command_copy_text
    assert "Command copy text: none" in command_copy_text
    assert "Observed: writes=0 network=0" in command_copy_text
    assert "{" not in command_copy_text

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
    assert validation["state"] == "ready_for_live_lookup_request"
    assert validation["next_validation_step"] == "selected_target_audit"
    assert validation["creates_selected_live_target"] is False
    assert validation["writes_attempted"] == 0
    assert validation["network_calls_made"] == 0
    assert validation["matching_template"]["job_id"] == job_id
    assert validation["select_target_command"] is None
    assert validation["commands"]["select_target"] is None
    assert validation["selected_target_audit_command"] == (
        f"sinks selected-target-audit {job_id} --run-id {run_id} --scope lookup --no-write --json"
    )
    assert validation["lookup_smoke_handoff_command"] == (
        f"sinks lookup-smoke-handoff {job_id} --run-id {run_id} --sink google_contacts --approved-by tester --json"
    )
    assert [item["step"] for item in validation["post_selection_sequence"]] == [
        "selected_target_audit",
        "lookup_smoke_handoff",
    ]
    assert validation["post_selection_sequence"][1]["command"] == validation["lookup_smoke_handoff_command"]
    assert validation["validation_command_sequence"]["safe_inspection_step_count"] == 2
    assert validation["validation_command_sequence"]["explicit_operator_step_count"] == 0
    assert validation["validation_command_sequence"]["live_call_step_count"] == 0
    assert validation["validation_command_sequence"]["sink_write_step_count"] == 0
    approval_readback = validation["approval_readback"]
    assert approval_readback["schema"] == "business-card-watchdog.live-pilot-operator-approval-readback.v1"
    assert approval_readback["state"] == "ready"
    assert approval_readback["validation_state"] == "ready_for_live_lookup_request"
    assert approval_readback["response_matches_template"] is True
    assert approval_readback["matched_template_job_id"] == job_id
    assert approval_readback["parsed_fields"]["operator"] == "tester"
    assert approval_readback["missing_field_count"] == 0
    assert approval_readback["mismatch_count"] == 0
    assert approval_readback["next_safe_step"] == "selected_target_audit"
    assert approval_readback["next_safe_command"] == validation["selected_target_audit_command"]
    assert approval_readback["creates_selected_live_target"] is False

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
    assert "State: ready_for_live_lookup_request" in validation_text
    assert "Next validation step: selected_target_audit" in validation_text
    assert "Creates selected target: False" in validation_text
    assert f"Select target: sinks select-live-target {job_id}" not in validation_text
    assert (
        f"Selected target audit: sinks selected-target-audit {job_id} "
        f"--run-id {run_id} --scope lookup --no-write --json"
    ) in validation_text
    assert (
        f"Lookup smoke handoff: sinks lookup-smoke-handoff {job_id} "
        f"--run-id {run_id} --sink google_contacts --approved-by tester --json"
    ) in validation_text
    assert "Post-selection sequence:" in validation_text
    assert (
        "Approval readback: state=ready matches_template=True "
        "missing=0 mismatches=0 next_safe=selected_target_audit"
    ) in validation_text
    assert "Validation sequence groups: safe=2 explicit=0 live=0 sink_writes=0" in validation_text
    assert f" - select_target: sinks select-live-target {job_id}" not in validation_text
    assert (
        f" - selected_target_audit: sinks selected-target-audit {job_id} "
        f"--run-id {run_id} --scope lookup --no-write --json"
    ) in validation_text
    assert (
        f" - lookup_smoke_handoff: sinks lookup-smoke-handoff {job_id} "
        f"--run-id {run_id} --sink google_contacts --approved-by tester --json"
    ) in validation_text
    assert "Stop conditions: 4" in validation_text
    assert "do not run select_target again" in validation_text
    assert "Review the selected-target audit and lookup-smoke handoff" in validation_text
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
    assert (
        "Approval readback: state=blocked matches_template=False "
        "missing=0 mismatches=1 next_safe=none"
    ) in blocked_validation_text
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
    assert actions["safe_inspection_commands"]["live_pilot_status"] == (
        f"runs live-pilot-status {run_id} --no-write --json"
    )
    assert actions["safe_inspection_commands"]["live_pilot_handoff"] == (
        f"runs live-pilot-handoff {run_id} --no-write --json"
    )
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


def test_cli_enrichment_request_can_select_people_data_labs_without_call(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "config.toml"
    data_dir = tmp_path / "data"
    keys_path = tmp_path / "API-keys.env"
    keys_path.write_text("PDL_API_KEY=fixture-value-redacted\n", encoding="utf-8")
    config_path.write_text(
        f'data_dir = "{data_dir}"\n'
        "[watch]\ninputs = []\n"
        "[enrichment]\nenabled = true\nallow_paid_api = true\n"
        f'api_keys_env = "{keys_path}"\n'
        "[enrichment.providers.people_data_labs]\nenabled = true\napi_key_env = \"PDL_API_KEY\"\n",
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
                people_data_labs=EnrichmentProviderConfig(enabled=True, api_key_env="PDL_API_KEY"),
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
                "--provider",
                "people_data_labs",
                "--provider-results-json",
                (
                    '[{"data":{"full_name":"Ada Lovelace","work_email":"ada@example.test",'
                    '"job_title":"Principal","job_company_name":"Example Labs"}}]'
                ),
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)

    assert payload["provider_request"]["provider"] == "people_data_labs"
    assert payload["provider_request"]["operation"] == "person_enrichment"
    assert payload["provider_result"]["provider"] == "people_data_labs"
    assert payload["provider_result"]["paid_api_calls_attempted"] == 0
    assert "fixture-value-redacted" not in json.dumps(payload)


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

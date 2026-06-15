import csv
import json
from io import StringIO
from pathlib import Path

from business_card_watchdog.config import AppConfig, EnrichmentConfig, EnrichmentProviderConfig, SinkConfig
from business_card_watchdog.contact import build_contact_candidate
from business_card_watchdog.mcp import call_tool, tool_manifest
from business_card_watchdog.mcp_server import serve_jsonl
from business_card_watchdog.orchestrator import BatchOrchestrator
from business_card_watchdog.service import BusinessCardService

from synthetic_fixtures import SyntheticSkillAdapter, write_multi_card_image
from test_service import make_recorded_run


def test_manifest_has_process_tool() -> None:
    manifest = tool_manifest()
    names = {tool["name"] for tool in manifest["tools"]}
    assert "business_card_watchdog_process" in names
    assert "business_card_watchdog_runtime_readiness" in names
    assert "business_card_watchdog_service_recovery" in names
    assert "business_card_watchdog_live_target_candidates" in names
    assert "business_card_watchdog_live_readiness_audit" in names
    assert "business_card_watchdog_live_selection_requirements" in names
    assert "business_card_watchdog_live_selection_packet" in names
    assert "business_card_watchdog_runs_list" in names
    assert "business_card_watchdog_job_show" in names
    assert "business_card_watchdog_job_review" in names
    assert "business_card_watchdog_run_summary" in names
    assert "business_card_watchdog_phase_report" in names
    assert "business_card_watchdog_pilot_readiness_report" in names
    assert "business_card_watchdog_live_pilot_status" in names
    assert "business_card_watchdog_live_pilot_handoff" in names
    assert "business_card_watchdog_live_pilot_approval_packet" in names
    assert "business_card_watchdog_live_pilot_operator_response_validation" in names
    assert "business_card_watchdog_selected_live_target_preflight" in names
    assert "business_card_watchdog_selected_live_target_artifact_preview" in names
    assert "business_card_watchdog_selected_live_target_from_response" in names
    assert "business_card_watchdog_selected_live_target_handoff_from_response" in names
    assert "business_card_watchdog_lookup_smoke_handoff_from_response" in names
    assert "business_card_watchdog_selected_lookup_smoke_execution_packet_from_response" in names
    assert "business_card_watchdog_selected_write_pilot_execution_packet_from_response" in names
    assert "business_card_watchdog_selected_readback_pilot_execution_packet_from_response" in names
    assert "business_card_watchdog_live_pilot_closeout_packet_from_response" in names
    assert "business_card_watchdog_live_pilot_operator_workflow_packet_from_response" in names
    assert "business_card_watchdog_live_pilot_operator_rehearsal_from_response" in names
    assert "business_card_watchdog_live_pilot_readiness_export_from_response" in names
    assert "business_card_watchdog_live_pilot_execution_checklist_from_response" in names
    assert "business_card_watchdog_live_pilot_command_copy_packet_from_response" in names
    assert "business_card_watchdog_next_actions" in names
    assert "business_card_watchdog_run_next_actions" in names
    assert "business_card_watchdog_multi_card_preclassification_drill" in names
    assert "business_card_watchdog_review_routing_drill" in names
    assert "business_card_watchdog_live_pilot_rehearsal_drill" in names
    assert "business_card_watchdog_reviews_list" in names
    assert "business_card_watchdog_child_reviews_list" in names
    assert "business_card_watchdog_child_review_submit" in names
    assert "business_card_watchdog_child_route_prep_queue" in names
    assert "business_card_watchdog_child_route_prepare" in names
    assert "business_card_watchdog_child_sink_lookup_result" in names
    assert "business_card_watchdog_child_downstream_duplicate_assessment" in names
    assert "business_card_watchdog_child_duplicate_resolution" in names
    assert "business_card_watchdog_child_sink_plan_gate" in names
    assert "business_card_watchdog_child_sink_apply_preflight" in names
    assert "business_card_watchdog_child_selected_target_handoff" in names
    assert "business_card_watchdog_child_selected_target_response_validation" in names
    assert "business_card_watchdog_child_selected_target_execution_checklist" in names
    assert "business_card_watchdog_child_selected_target_command_copy_packet" in names
    assert "business_card_watchdog_child_selected_target_audit" in names
    assert "business_card_watchdog_review_bundle" in names
    assert "business_card_watchdog_review_html" in names
    assert "business_card_watchdog_review_workbook" in names
    assert "business_card_watchdog_review_workbook_validation" in names
    assert "business_card_watchdog_apply_review_decisions" in names
    assert "business_card_watchdog_sinks_check" in names
    assert "business_card_watchdog_sink_plan" in names
    assert "business_card_watchdog_sink_lookup_plan" in names
    assert "business_card_watchdog_sink_apply_preflight" in names
    assert "business_card_watchdog_sink_apply_decision" in names
    assert "business_card_watchdog_sink_apply" in names
    assert "business_card_watchdog_sink_apply_pilot_readiness" in names
    assert "business_card_watchdog_sink_apply_pilot_report" in names
    assert "business_card_watchdog_sink_apply_pilot_bundle" in names
    assert "business_card_watchdog_sink_adapter_request" in names
    assert "business_card_watchdog_sink_lookup_pilot" in names
    assert "business_card_watchdog_sink_lookup_readiness" in names
    assert "business_card_watchdog_sink_lookup_smoke_handoff" in names
    assert "business_card_watchdog_selected_live_target" in names
    assert "business_card_watchdog_selected_live_target_audit" in names
    assert "business_card_watchdog_live_pilot_abandonment" in names
    assert "business_card_watchdog_selected_lookup_smoke" in names
    assert "business_card_watchdog_sink_write_pilot" in names
    assert "business_card_watchdog_sink_readback_pilot" in names
    assert "business_card_watchdog_live_pilot_closeout" in names
    assert "business_card_watchdog_sink_lookup_result" in names
    assert "business_card_watchdog_downstream_duplicate_assessment" in names
    assert "business_card_watchdog_enrichment_check" in names
    assert "business_card_watchdog_enrichment_request" in names
    assert "business_card_watchdog_public_web_enrichment_handoff" in names
    assert "business_card_watchdog_public_web_enrichment_results" in names
    assert "business_card_watchdog_provider_enrichment_handoff" in names
    assert "business_card_watchdog_provider_enrichment_results" in names
    assert "business_card_watchdog_watch_dry_run" in names
    assert "business_card_watchdog_doctor" in names
    review_tool = next(tool for tool in manifest["tools"] if tool["name"] == "business_card_watchdog_job_review")
    assert "approve_enrichment_merge" in review_tool["input_schema"]["properties"]["action"]["enum"]
    assert "request_enrichment" in review_tool["input_schema"]["properties"]["action"]["enum"]
    assert "resolve_duplicate" in review_tool["input_schema"]["properties"]["action"]["enum"]
    assert "reject_not_card" in review_tool["input_schema"]["properties"]["action"]["enum"]
    assert "skip" in review_tool["input_schema"]["properties"]["action"]["enum"]


def test_mcp_multi_card_preclassification_drill_records_candidate_boxes(tmp_path: Path) -> None:
    pytest = __import__("pytest")
    pytest.importorskip("cv2")
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        cache_dir=tmp_path / "cache",
    )

    payload = call_tool("business_card_watchdog_multi_card_preclassification_drill", {}, config=config)

    assert payload["schema"] == "business-card-watchdog.multi-card-preclassification-drill.v1"
    assert payload["state"] == "passed"
    assert payload["expected_card_count"] == 3
    assert payload["detected_card_like_count"] >= 3
    assert len(payload["candidate_boxes"]) >= 3
    assert payload["private_sources_used"] is False
    assert payload["live_sink_calls_made"] is False
    assert payload["writes_attempted"] == 0
    assert payload["network_calls_made"] == 0


def test_mcp_child_reviews_lists_promoted_child_candidates(tmp_path: Path, monkeypatch) -> None:
    pytest = __import__("pytest")
    pytest.importorskip("cv2")
    source_dir = tmp_path / "images"
    write_multi_card_image(source_dir / "multi.jpg")
    config = AppConfig(config_path=tmp_path / "config.toml", data_dir=tmp_path / "data")
    orchestrator = BatchOrchestrator(config)
    monkeypatch.setattr(orchestrator, "adapter", SyntheticSkillAdapter())
    run_dir = orchestrator.process_source(str(source_dir), dry_run=True, workers=1)

    payload = call_tool(
        "business_card_watchdog_child_reviews_list",
        {"run_id": run_dir.name},
        config=config,
    )

    assert len(payload) >= 3
    assert payload[0]["next_action"]["action"] == "review_child_contact"
    assert payload[0]["contact_candidate"]["source"] == "child_verification_result"


def test_mcp_child_review_approves_promoted_child_candidate(tmp_path: Path, monkeypatch) -> None:
    pytest = __import__("pytest")
    pytest.importorskip("cv2")
    source_dir = tmp_path / "images"
    write_multi_card_image(source_dir / "multi.jpg")
    config = AppConfig(config_path=tmp_path / "config.toml", data_dir=tmp_path / "data")
    orchestrator = BatchOrchestrator(config)
    monkeypatch.setattr(orchestrator, "adapter", SyntheticSkillAdapter())
    run_dir = orchestrator.process_source(str(source_dir), dry_run=True, workers=1)
    candidate_id = str(BusinessCardService(config).child_review_queue(run_id=run_dir.name)[0]["candidate_id"])

    payload = call_tool(
        "business_card_watchdog_child_review_submit",
        {
            "run_id": run_dir.name,
            "candidate_id": candidate_id,
            "reviewer": "operator",
            "action": "approve_child_for_routing",
            "field_corrections": {"email": "mcp-child@example.test"},
        },
        config=config,
    )

    assert payload["candidate_id"] == candidate_id
    assert payload["state"] == "approved_for_dedupe"
    assert payload["reviewed_contact"]["flat"]["email"] == "mcp-child@example.test"
    assert payload["writes_attempted"] == 0
    assert payload["network_calls_made"] == 0


def test_mcp_child_route_prep_writes_dry_run_plans(tmp_path: Path, monkeypatch) -> None:
    pytest = __import__("pytest")
    pytest.importorskip("cv2")
    source_dir = tmp_path / "images"
    write_multi_card_image(source_dir / "multi.jpg")
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
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

    queue = call_tool(
        "business_card_watchdog_child_route_prep_queue",
        {"run_id": run_dir.name},
        config=config,
    )
    payload = call_tool(
        "business_card_watchdog_child_route_prepare",
        {"run_id": run_dir.name, "candidate_id": candidate_id},
        config=config,
    )

    assert any(entry["candidate_id"] == candidate_id for entry in queue)
    assert payload["state"] == "routing_prepared"
    assert payload["lookup_plan"]["dry_run"] is True
    assert payload["sink_plan"]["dry_run"] is True
    assert payload["result"]["sink_write_allowed"] is False
    assert payload["writes_attempted"] == 0
    assert payload["network_calls_made"] == 0


def test_mcp_child_lookup_result_and_duplicate_assessment(tmp_path: Path, monkeypatch) -> None:
    pytest = __import__("pytest")
    pytest.importorskip("cv2")
    source_dir = tmp_path / "images"
    write_multi_card_image(source_dir / "multi.jpg")
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
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

    lookup = call_tool(
        "business_card_watchdog_child_sink_lookup_result",
        {
            "run_id": run_dir.name,
            "candidate_id": candidate_id,
            "matches_by_sink": {
                "google_contacts": [
                    {"resource_id": "people/mcp-child", "confidence": 0.9, "basis": ["email"]}
                ]
            },
        },
        config=config,
    )
    assessment = call_tool(
        "business_card_watchdog_child_downstream_duplicate_assessment",
        {"run_id": run_dir.name, "candidate_id": candidate_id},
        config=config,
    )

    assert lookup["result"]["match_count"] == 1
    assert lookup["writes_attempted"] == 0
    assert lookup["network_calls_made"] == 0
    assert assessment["assessment"]["state"] == "strong_duplicate"
    assert assessment["writes_attempted"] == 0
    assert assessment["network_calls_made"] == 0


def test_mcp_child_duplicate_resolution_clears_gate(tmp_path: Path, monkeypatch) -> None:
    pytest = __import__("pytest")
    pytest.importorskip("cv2")
    source_dir = tmp_path / "images"
    write_multi_card_image(source_dir / "multi.jpg")
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
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
        matches_by_sink={"google_contacts": [{"resource_id": "people/mcp-existing", "basis": ["email"]}]},
    )
    service.assess_child_downstream_duplicates(run_id=run_dir.name, candidate_id=candidate_id)

    resolution = call_tool(
        "business_card_watchdog_child_duplicate_resolution",
        {
            "run_id": run_dir.name,
            "candidate_id": candidate_id,
            "reviewer": "operator",
            "decision": "create_new",
            "reason": "separate person",
        },
        config=config,
    )
    gate = call_tool(
        "business_card_watchdog_child_sink_plan_gate",
        {"run_id": run_dir.name, "candidate_id": candidate_id},
        config=config,
    )

    assert resolution["resolution"]["decision"] == "create_new"
    assert resolution["writes_attempted"] == 0
    assert resolution["network_calls_made"] == 0
    assert gate["gate"]["state"] == "ready_for_sink_plan"
    assert gate["gate"]["sink_write_allowed"] is False


def test_mcp_child_sink_apply_preflight_and_handoff(tmp_path: Path, monkeypatch) -> None:
    pytest = __import__("pytest")
    pytest.importorskip("cv2")
    source_dir = tmp_path / "images"
    write_multi_card_image(source_dir / "multi.jpg")
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
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

    preflight = call_tool(
        "business_card_watchdog_child_sink_apply_preflight",
        {"run_id": run_dir.name, "candidate_id": candidate_id},
        config=config,
    )
    handoff = call_tool(
        "business_card_watchdog_child_selected_target_handoff",
        {"run_id": run_dir.name, "candidate_id": candidate_id, "sink": "google_contacts"},
        config=config,
    )

    assert preflight["preflight"]["state"] == "preview"
    assert preflight["preflight"]["sink_write_allowed"] is False
    assert handoff["handoff"]["state"] == "ready_for_operator_selection"
    assert handoff["handoff"]["selected_target_created"] is False
    assert handoff["writes_attempted"] == 0
    assert handoff["network_calls_made"] == 0


def test_mcp_child_selected_target_response_validation_and_checklist(tmp_path: Path, monkeypatch) -> None:
    pytest = __import__("pytest")
    pytest.importorskip("cv2")
    source_dir = tmp_path / "images"
    write_multi_card_image(source_dir / "multi.jpg")
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
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
    handoff = call_tool(
        "business_card_watchdog_child_selected_target_handoff",
        {"run_id": run_dir.name, "candidate_id": candidate_id, "sink": "google_contacts"},
        config=config,
    )["handoff"]
    template = handoff["operator_response_template"]
    response = (
        f"run_id={template['run_id']} job_id={template['job_id']} "
        f"candidate_id={template['candidate_id']} work_item_id={template['work_item_id']} "
        "sink=google_contacts operator=operator scope=write "
        "safety_confirmation='approved google contacts target profile'"
    )

    validation = call_tool(
        "business_card_watchdog_child_selected_target_response_validation",
        {"run_id": run_dir.name, "candidate_id": candidate_id, "response": response},
        config=config,
    )
    checklist = call_tool(
        "business_card_watchdog_child_selected_target_execution_checklist",
        {"run_id": run_dir.name, "candidate_id": candidate_id, "response": response},
        config=config,
    )
    command_copy = call_tool(
        "business_card_watchdog_child_selected_target_command_copy_packet",
        {
            "run_id": run_dir.name,
            "candidate_id": candidate_id,
            "response": response,
            "acknowledgement": (
                f"I acknowledge run_id={run_dir.name} candidate_id={candidate_id} "
                "sink=google_contacts operator=operator ready to copy"
            ),
        },
        config=config,
    )
    audit = call_tool(
        "business_card_watchdog_child_selected_target_audit",
        {"run_id": run_dir.name, "candidate_id": candidate_id},
        config=config,
    )

    assert validation["schema"] == "business-card-watchdog.child-selected-target-response-validation.v1"
    assert validation["state"] == "ready_for_no_live_child_checklist"
    assert validation["writes_attempted"] == 0
    assert validation["network_calls_made"] == 0
    assert checklist["schema"] == "business-card-watchdog.child-selected-target-execution-checklist.v1"
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


def test_mcp_call_tool_dispatches_to_service(tmp_path: Path) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        sink=SinkConfig(google_contacts=True, dry_run=True),
        routing_rules=[{"match": "email_domain", "value": "*", "sinks": ["google_contacts"]}],
    )
    run_id, job_id = make_recorded_run(config)
    artifact_dir = config.runs_dir / run_id / "artifacts" / job_id
    (artifact_dir / "enrichment_result.json").write_text(
        json.dumps(
            {
                "schema": "business-card-watchdog.enrichment-result.v1",
                "merge_proposals": [
                    {
                        "field": "notes",
                        "value": "Public-web corroboration candidate: https://example.test/mcp",
                        "source": "public_web",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (artifact_dir / "duplicate_assessment.json").write_text(
        '{"schema": "business-card-watchdog.duplicate-assessment.v1", "state": "possible_duplicate"}\n',
        encoding="utf-8",
    )

    status = call_tool("business_card_watchdog_status", {}, config=config)
    operator_dashboard = call_tool(
        "business_card_watchdog_operator_dashboard",
        {"run_id": run_id},
        config=config,
    )
    summary = call_tool("business_card_watchdog_run_summary", {"run_id": run_id}, config=config)
    phase_report = call_tool("business_card_watchdog_phase_report", {"run_id": run_id}, config=config)
    readiness_report = call_tool("business_card_watchdog_pilot_readiness_report", {"run_id": run_id}, config=config)
    runtime_readiness = call_tool("business_card_watchdog_runtime_readiness", {}, config=config)
    service_recovery = call_tool("business_card_watchdog_service_recovery", {"run_id": run_id}, config=config)
    live_targets = call_tool("business_card_watchdog_live_target_candidates", {"run_id": run_id}, config=config)
    live_audit = call_tool(
        "business_card_watchdog_live_readiness_audit",
        {"run_id": run_id, "write": False},
        config=config,
    )
    live_requirements = call_tool(
        "business_card_watchdog_live_selection_requirements",
        {"run_id": run_id, "write": False},
        config=config,
    )
    live_packet = call_tool(
        "business_card_watchdog_live_selection_packet",
        {
            "job_id": job_id,
            "run_id": run_id,
            "sink": "google_contacts",
            "operator": "mcp-test",
            "write": False,
        },
        config=config,
    )
    watch_dry_run = call_tool("business_card_watchdog_watch_dry_run", {}, config=config)
    review_routing_drill = call_tool("business_card_watchdog_review_routing_drill", {}, config=config)
    live_pilot_rehearsal_drill = call_tool(
        "business_card_watchdog_live_pilot_rehearsal_drill",
        {},
        config=config,
    )
    reviews = call_tool(
        "business_card_watchdog_reviews_list",
        {
            "run_id": run_id,
            "next_action": "review_contact",
            "artifact_kind": "contact_spec",
        },
        config=config,
    )
    review_bundle = call_tool("business_card_watchdog_review_bundle", {"run_id": run_id}, config=config)
    review_html = call_tool("business_card_watchdog_review_html", {"run_id": run_id}, config=config)
    review_workbook = call_tool("business_card_watchdog_review_workbook", {"run_id": run_id}, config=config)
    next_actions = call_tool("business_card_watchdog_next_actions", {"run_id": run_id}, config=config)
    review_import = call_tool(
        "business_card_watchdog_apply_review_decisions",
        {
            "run_id": run_id,
            "reviewer": "mcp-batch",
            "decisions": [
                {
                    "job_id": job_id,
                    "action": "approve_for_routing",
                    "field_corrections": {"full_name": "MCP Batch"},
                }
            ],
        },
        config=config,
    )
    job = call_tool("business_card_watchdog_job_show", {"job_id": job_id, "run_id": run_id}, config=config)
    lookup = call_tool(
        "business_card_watchdog_sink_lookup_plan",
        {"job_id": job_id, "run_id": run_id},
        config=config,
    )
    preflight = call_tool(
        "business_card_watchdog_sink_apply_preflight",
        {"job_id": job_id, "run_id": run_id},
        config=config,
    )
    apply_decision = call_tool(
        "business_card_watchdog_sink_apply_decision",
        {"job_id": job_id, "run_id": run_id, "decision": "approve", "reviewer": "mcp-test"},
        config=config,
    )
    apply_result = call_tool(
        "business_card_watchdog_sink_apply",
        {"job_id": job_id, "run_id": run_id, "apply": True, "simulate": True},
        config=config,
    )
    pilot_readiness = call_tool(
        "business_card_watchdog_sink_apply_pilot_readiness",
        {"job_id": job_id, "run_id": run_id, "sink": "google_contacts"},
        config=config,
    )
    pilot_bundle = call_tool(
        "business_card_watchdog_sink_apply_pilot_bundle",
        {"job_id": job_id, "run_id": run_id, "sink": "google_contacts", "operator": "mcp-test"},
        config=config,
    )
    selected_target = call_tool(
        "business_card_watchdog_selected_live_target",
        {
            "job_id": job_id,
            "run_id": run_id,
            "sink": "google_contacts",
            "operator": "mcp-test",
            "scope": "all",
            "safety_confirmation": "fixture contact is safe for google contacts test profile",
        },
        config=config,
    )
    active_live_packet = call_tool(
        "business_card_watchdog_live_selection_packet",
        {
            "job_id": job_id,
            "run_id": run_id,
            "sink": "google_contacts",
            "operator": "mcp-test",
            "write": False,
        },
        config=config,
    )
    selected_target_audit = call_tool(
        "business_card_watchdog_selected_live_target_audit",
        {
            "job_id": job_id,
            "run_id": run_id,
            "scope": "lookup",
            "write": False,
        },
        config=config,
    )
    live_closeout = call_tool(
        "business_card_watchdog_live_pilot_closeout",
        {"job_id": job_id, "run_id": run_id, "write": False},
        config=config,
    )
    live_status = call_tool(
        "business_card_watchdog_live_pilot_status",
        {"run_id": run_id, "write": False},
        config=config,
    )
    live_handoff = call_tool(
        "business_card_watchdog_live_pilot_handoff",
        {"run_id": run_id, "write": False},
        config=config,
    )
    approval_packet = call_tool(
        "business_card_watchdog_live_pilot_approval_packet",
        {"run_id": run_id, "job_id": job_id},
        config=config,
    )
    operator_response_validation = call_tool(
        "business_card_watchdog_live_pilot_operator_response_validation",
        {
            "run_id": run_id,
            "response": (
                f"run_id={run_id} job_id={job_id} sink=google_contacts "
                "operator=mcp-test scope=all "
                "safety_confirmation=fixture contact is safe for google contacts test profile"
            ),
        },
        config=config,
    )
    selected_target_preflight = call_tool(
        "business_card_watchdog_selected_live_target_preflight",
        {
            "run_id": run_id,
            "response": (
                f"run_id={run_id} job_id={job_id} sink=google_contacts "
                "operator=mcp-test scope=all "
                "safety_confirmation=fixture contact is safe for google contacts test profile"
            ),
        },
        config=config,
    )
    selected_target_preview = call_tool(
        "business_card_watchdog_selected_live_target_artifact_preview",
        {
            "run_id": run_id,
            "response": (
                f"run_id={run_id} job_id={job_id} sink=google_contacts "
                "operator=mcp-test scope=all "
                "safety_confirmation=fixture contact is safe for google contacts test profile"
            ),
        },
        config=config,
    )
    selected_target_from_response = call_tool(
        "business_card_watchdog_selected_live_target_from_response",
        {
            "run_id": run_id,
            "response": (
                f"run_id={run_id} job_id={job_id} sink=google_contacts "
                "operator=mcp-test scope=all "
                "safety_confirmation=fixture contact is safe for google contacts test profile"
            ),
        },
        config=config,
    )
    selected_target_handoff_from_response = call_tool(
        "business_card_watchdog_selected_live_target_handoff_from_response",
        {
            "run_id": run_id,
            "response": (
                f"run_id={run_id} job_id={job_id} sink=google_contacts "
                "operator=mcp-test scope=all "
                "safety_confirmation=fixture contact is safe for google contacts test profile"
            ),
            "write_audit": False,
        },
        config=config,
    )
    lookup_smoke_handoff_from_response = call_tool(
        "business_card_watchdog_lookup_smoke_handoff_from_response",
        {
            "run_id": run_id,
            "response": (
                f"run_id={run_id} job_id={job_id} sink=google_contacts "
                "operator=mcp-test scope=all "
                "safety_confirmation=fixture contact is safe for google contacts test profile"
            ),
            "write_handoff": False,
        },
        config=config,
    )
    selected_lookup_smoke_execution_packet_from_response = call_tool(
        "business_card_watchdog_selected_lookup_smoke_execution_packet_from_response",
        {
            "run_id": run_id,
            "response": (
                f"run_id={run_id} job_id={job_id} sink=google_contacts "
                "operator=mcp-test scope=all "
                "safety_confirmation=fixture contact is safe for google contacts test profile"
            ),
            "execute_selected_lookup_smoke": False,
        },
        config=config,
    )
    selected_write_pilot_execution_packet_from_response = call_tool(
        "business_card_watchdog_selected_write_pilot_execution_packet_from_response",
        {
            "run_id": run_id,
            "response": (
                f"run_id={run_id} job_id={job_id} sink=google_contacts "
                "operator=mcp-test scope=all "
                "safety_confirmation=fixture contact is safe for google contacts test profile"
            ),
            "execute_write_pilot": False,
        },
        config=config,
    )
    selected_readback_pilot_execution_packet_from_response = call_tool(
        "business_card_watchdog_selected_readback_pilot_execution_packet_from_response",
        {
            "run_id": run_id,
            "response": (
                f"run_id={run_id} job_id={job_id} sink=google_contacts "
                "operator=mcp-test scope=all "
                "safety_confirmation=fixture contact is safe for google contacts test profile"
            ),
            "execute_readback_pilot": False,
        },
        config=config,
    )
    live_pilot_closeout_packet_from_response = call_tool(
        "business_card_watchdog_live_pilot_closeout_packet_from_response",
        {
            "run_id": run_id,
            "response": (
                f"run_id={run_id} job_id={job_id} sink=google_contacts "
                "operator=mcp-test scope=all "
                "safety_confirmation=fixture contact is safe for google contacts test profile"
            ),
            "write_closeout": False,
        },
        config=config,
    )
    live_pilot_operator_workflow_packet_from_response = call_tool(
        "business_card_watchdog_live_pilot_operator_workflow_packet_from_response",
        {
            "run_id": run_id,
            "response": (
                f"run_id={run_id} job_id={job_id} sink=google_contacts "
                "operator=mcp-test scope=all "
                "safety_confirmation=fixture contact is safe for google contacts test profile"
            ),
        },
        config=config,
    )
    live_pilot_operator_rehearsal_from_response = call_tool(
        "business_card_watchdog_live_pilot_operator_rehearsal_from_response",
        {
            "run_id": run_id,
            "response": (
                f"run_id={run_id} job_id={job_id} sink=google_contacts "
                "operator=mcp-test scope=all "
                "safety_confirmation=fixture contact is safe for google contacts test profile"
            ),
        },
        config=config,
    )
    live_pilot_readiness_export_from_response = call_tool(
        "business_card_watchdog_live_pilot_readiness_export_from_response",
        {
            "run_id": run_id,
            "response": (
                f"run_id={run_id} job_id={job_id} sink=google_contacts "
                "operator=mcp-test scope=all "
                "safety_confirmation=fixture contact is safe for google contacts test profile"
            ),
            "write": False,
        },
        config=config,
    )
    live_pilot_execution_checklist_from_response = call_tool(
        "business_card_watchdog_live_pilot_execution_checklist_from_response",
        {
            "run_id": run_id,
            "response": (
                f"run_id={run_id} job_id={job_id} sink=google_contacts "
                "operator=mcp-test scope=all "
                "safety_confirmation=fixture contact is safe for google contacts test profile"
            ),
        },
        config=config,
    )
    live_pilot_command_copy_packet_from_response = call_tool(
        "business_card_watchdog_live_pilot_command_copy_packet_from_response",
        {
            "run_id": run_id,
            "response": (
                f"run_id={run_id} job_id={job_id} sink=google_contacts "
                "operator=mcp-test scope=all "
                "safety_confirmation=fixture contact is safe for google contacts test profile"
            ),
        },
        config=config,
    )
    abandonment = call_tool(
        "business_card_watchdog_live_pilot_abandonment",
        {
            "job_id": job_id,
            "run_id": run_id,
            "operator": "mcp-test",
            "reason": "wrong target profile selected",
        },
        config=config,
    )
    abandoned_live_packet = call_tool(
        "business_card_watchdog_live_selection_packet",
        {
            "job_id": job_id,
            "run_id": run_id,
            "sink": "google_contacts",
            "operator": "mcp-test",
            "write": False,
        },
        config=config,
    )
    write_pilot = call_tool(
        "business_card_watchdog_sink_write_pilot",
        {
            "job_id": job_id,
            "run_id": run_id,
            "sink": "google_contacts",
            "approved_by": "mcp-operator",
        },
        config=config,
    )
    adapter_request = call_tool(
        "business_card_watchdog_sink_adapter_request",
        {"job_id": job_id, "run_id": run_id, "phase": "readback"},
        config=config,
    )
    readback_pilot = call_tool(
        "business_card_watchdog_sink_readback_pilot",
        {
            "job_id": job_id,
            "run_id": run_id,
            "sink": "google_contacts",
            "approved_by": "mcp-operator",
        },
        config=config,
    )
    pilot_report = call_tool(
        "business_card_watchdog_sink_apply_pilot_report",
        {"job_id": job_id, "run_id": run_id},
        config=config,
    )
    lookup_pilot = call_tool(
        "business_card_watchdog_sink_lookup_pilot",
        {
            "job_id": job_id,
            "run_id": run_id,
            "sink": "google_contacts",
            "approved_by": "mcp-operator",
            "matches": [
                {"resource_id": "people/c456", "confidence": 0.93, "basis": ["email"]}
            ],
        },
        config=config,
    )
    lookup_readiness = call_tool(
        "business_card_watchdog_sink_lookup_readiness",
        {"job_id": job_id, "run_id": run_id, "sink": "google_contacts"},
        config=config,
    )
    lookup_handoff = call_tool(
        "business_card_watchdog_sink_lookup_smoke_handoff",
        {
            "job_id": job_id,
            "run_id": run_id,
            "sink": "google_contacts",
            "approved_by": "mcp-operator",
        },
        config=config,
    )
    lookup_result = call_tool(
        "business_card_watchdog_sink_lookup_result",
        {
            "job_id": job_id,
            "run_id": run_id,
            "matches_by_sink": {
                "google_contacts": [
                    {"resource_id": "people/c123", "confidence": 0.91, "basis": ["email"]}
                ]
            },
        },
        config=config,
    )
    downstream_duplicate = call_tool(
        "business_card_watchdog_downstream_duplicate_assessment",
        {"job_id": job_id, "run_id": run_id},
        config=config,
    )
    merge = call_tool(
        "business_card_watchdog_job_review",
        {
            "job_id": job_id,
            "run_id": run_id,
            "action": "approve_enrichment_merge",
            "approved_enrichment_fields": ["notes"],
        },
        config=config,
    )
    duplicate = call_tool(
        "business_card_watchdog_job_review",
        {
            "job_id": job_id,
            "run_id": run_id,
            "action": "resolve_duplicate",
            "duplicate_resolution": {"decision": "create_new", "reason": "separate contact"},
        },
        config=config,
    )
    run_next = call_tool(
        "business_card_watchdog_run_next_actions",
        {"run_id": run_id, "limit": 1},
        config=config,
    )

    assert status["schema"] == "business-card-watchdog.status.v1"
    assert status["commands"]["runtime_readiness"] == "runtime-readiness --json"
    assert status["safe_next_actions"][0]["action"] == "inspect_runtime_readiness"
    assert operator_dashboard["schema"] == "business-card-watchdog.operator-dashboard.v1"
    assert run_next["safe_inspection_commands"]["live_pilot_status"] == (
        f"runs live-pilot-status {run_id} --no-write --json"
    )
    assert run_next["safe_inspection_commands"]["service_recovery"] == (
        f"service recovery --run-id {run_id} --json"
    )
    assert operator_dashboard["selected_run_id"] == run_id
    assert operator_dashboard["commands"]["review_queue"] == f"reviews list --run-id {run_id} --state all --json"
    assert operator_dashboard["commands"]["next_actions"] == f"actions next --run-id {run_id} --json"
    assert operator_dashboard["commands"]["multi_card_preclassification_drill"] == (
        "drills multi-card-preclassification --json"
    )
    assert operator_dashboard["commands"]["review_routing_drill"] == "drills review-routing --json"
    assert operator_dashboard["commands"]["live_pilot_rehearsal_drill"] == "drills live-pilot-rehearsal --json"
    assert operator_dashboard["api_routes"]["multi_card_preclassification_drill"] == (
        "POST /drills/multi-card-preclassification"
    )
    assert operator_dashboard["api_routes"]["review_routing_drill"] == "POST /drills/review-routing"
    assert operator_dashboard["api_routes"]["live_pilot_rehearsal_drill"] == "POST /drills/live-pilot-rehearsal"
    assert operator_dashboard["commands"]["live_pilot_validate_response"] == (
        f"runs live-pilot-validate-response {run_id} --response <operator-response> --json"
    )
    assert operator_dashboard["commands"]["live_pilot_approval_packet"] == (
        f"runs live-pilot-approval-packet {run_id} --json"
    )
    assert operator_dashboard["commands"]["selected_live_target_preflight"] == (
        f"runs selected-live-target-preflight {run_id} --response <operator-response> --json"
    )
    assert operator_dashboard["commands"]["selected_live_target_preview"] == (
        f"runs selected-live-target-preview {run_id} --response <operator-response> --json"
    )
    assert operator_dashboard["commands"]["selected_live_target_from_response"] == (
        f"runs selected-live-target-from-response {run_id} --response <operator-response> --json"
    )
    assert operator_dashboard["commands"]["selected_live_target_handoff_from_response"] == (
        f"runs selected-live-target-handoff-from-response {run_id} --response <operator-response> --json"
    )
    assert operator_dashboard["commands"]["lookup_smoke_handoff_from_response"] == (
        f"runs lookup-smoke-handoff-from-response {run_id} --response <operator-response> --json"
    )
    assert operator_dashboard["commands"]["selected_lookup_smoke_execution_packet_from_response"] == (
        f"runs selected-lookup-smoke-execution-packet-from-response {run_id} "
        "--response <operator-response> --json"
    )
    assert operator_dashboard["commands"]["selected_write_pilot_execution_packet_from_response"] == (
        f"runs selected-write-pilot-execution-packet-from-response {run_id} "
        "--response <operator-response> --json"
    )
    assert operator_dashboard["commands"]["selected_readback_pilot_execution_packet_from_response"] == (
        f"runs selected-readback-pilot-execution-packet-from-response {run_id} "
        "--response <operator-response> --json"
    )
    assert operator_dashboard["commands"]["live_pilot_closeout_packet_from_response"] == (
        f"runs live-pilot-closeout-packet-from-response {run_id} "
        "--response <operator-response> --json"
    )
    assert operator_dashboard["commands"]["live_pilot_operator_workflow_packet_from_response"] == (
        f"runs live-pilot-operator-workflow-packet-from-response {run_id} "
        "--response <operator-response> --json"
    )
    assert operator_dashboard["commands"]["live_pilot_operator_rehearsal_from_response"] == (
        f"runs live-pilot-operator-rehearsal-from-response {run_id} --response <operator-response> --json"
    )
    assert operator_dashboard["commands"]["live_pilot_readiness_export_from_response"] == (
        f"runs live-pilot-readiness-export-from-response {run_id} --response <operator-response> --json"
    )
    assert operator_dashboard["commands"]["live_pilot_execution_checklist_from_response"] == (
        f"runs live-pilot-execution-checklist-from-response {run_id} --response <operator-response> --json"
    )
    assert operator_dashboard["commands"]["live_pilot_command_copy_packet_from_response"] == (
        f"runs live-pilot-command-copy-packet-from-response {run_id} "
        "--response <operator-response> --acknowledgement <operator-acknowledgement> --json"
    )
    assert operator_dashboard["safe_next_actions"][3]["action"] == "inspect_live_pilot_status"
    assert operator_dashboard["safe_next_actions"][3]["command"] == (
        f"runs live-pilot-status {run_id} --no-write --json"
    )
    assert operator_dashboard["safe_next_actions"][4]["action"] == "inspect_live_pilot_handoff"
    assert operator_dashboard["safe_next_actions"][4]["command"] == (
        f"runs live-pilot-handoff {run_id} --no-write --json"
    )
    assert operator_dashboard["mcp_tools"]["next_actions"]["tool"] == "business_card_watchdog_next_actions"
    assert operator_dashboard["mcp_tools"]["next_actions"]["arguments"] == {"run_id": run_id, "limit": 20}
    assert operator_dashboard["mcp_tools"]["multi_card_preclassification_drill"] == {
        "tool": "business_card_watchdog_multi_card_preclassification_drill",
        "arguments": {},
    }
    assert operator_dashboard["mcp_tools"]["review_routing_drill"] == {
        "tool": "business_card_watchdog_review_routing_drill",
        "arguments": {},
    }
    assert operator_dashboard["mcp_tools"]["live_pilot_rehearsal_drill"] == {
        "tool": "business_card_watchdog_live_pilot_rehearsal_drill",
        "arguments": {},
    }
    assert operator_dashboard["mcp_tools"]["live_pilot_validate_response"] == {
        "tool": "business_card_watchdog_live_pilot_operator_response_validation",
        "arguments": {"run_id": run_id, "response": "<operator-response>"},
    }
    assert operator_dashboard["mcp_tools"]["live_pilot_approval_packet"] == {
        "tool": "business_card_watchdog_live_pilot_approval_packet",
        "arguments": {"run_id": run_id},
    }
    assert operator_dashboard["mcp_tools"]["selected_live_target_preflight"] == {
        "tool": "business_card_watchdog_selected_live_target_preflight",
        "arguments": {"run_id": run_id, "response": "<operator-response>"},
    }
    assert operator_dashboard["mcp_tools"]["selected_live_target_preview"] == {
        "tool": "business_card_watchdog_selected_live_target_artifact_preview",
        "arguments": {"run_id": run_id, "response": "<operator-response>"},
    }
    assert operator_dashboard["mcp_tools"]["selected_live_target_from_response"] == {
        "tool": "business_card_watchdog_selected_live_target_from_response",
        "arguments": {"run_id": run_id, "response": "<operator-response>"},
    }
    assert operator_dashboard["mcp_tools"]["selected_live_target_handoff_from_response"] == {
        "tool": "business_card_watchdog_selected_live_target_handoff_from_response",
        "arguments": {"run_id": run_id, "response": "<operator-response>", "write_audit": False},
    }
    assert operator_dashboard["mcp_tools"]["lookup_smoke_handoff_from_response"] == {
        "tool": "business_card_watchdog_lookup_smoke_handoff_from_response",
        "arguments": {"run_id": run_id, "response": "<operator-response>", "write_handoff": False},
    }
    assert operator_dashboard["mcp_tools"]["selected_lookup_smoke_execution_packet_from_response"] == {
        "tool": "business_card_watchdog_selected_lookup_smoke_execution_packet_from_response",
        "arguments": {"run_id": run_id, "response": "<operator-response>", "execute_selected_lookup_smoke": False},
    }
    assert operator_dashboard["mcp_tools"]["selected_write_pilot_execution_packet_from_response"] == {
        "tool": "business_card_watchdog_selected_write_pilot_execution_packet_from_response",
        "arguments": {"run_id": run_id, "response": "<operator-response>", "execute_write_pilot": False},
    }
    assert operator_dashboard["mcp_tools"]["selected_readback_pilot_execution_packet_from_response"] == {
        "tool": "business_card_watchdog_selected_readback_pilot_execution_packet_from_response",
        "arguments": {"run_id": run_id, "response": "<operator-response>", "execute_readback_pilot": False},
    }
    assert operator_dashboard["mcp_tools"]["live_pilot_closeout_packet_from_response"] == {
        "tool": "business_card_watchdog_live_pilot_closeout_packet_from_response",
        "arguments": {"run_id": run_id, "response": "<operator-response>", "write_closeout": False},
    }
    assert operator_dashboard["mcp_tools"]["live_pilot_operator_workflow_packet_from_response"] == {
        "tool": "business_card_watchdog_live_pilot_operator_workflow_packet_from_response",
        "arguments": {"run_id": run_id, "response": "<operator-response>"},
    }
    assert operator_dashboard["mcp_tools"]["live_pilot_operator_rehearsal_from_response"] == {
        "tool": "business_card_watchdog_live_pilot_operator_rehearsal_from_response",
        "arguments": {"run_id": run_id, "response": "<operator-response>"},
    }
    assert operator_dashboard["mcp_tools"]["live_pilot_readiness_export_from_response"] == {
        "tool": "business_card_watchdog_live_pilot_readiness_export_from_response",
        "arguments": {"run_id": run_id, "response": "<operator-response>", "write": True},
    }
    assert operator_dashboard["mcp_tools"]["live_pilot_execution_checklist_from_response"] == {
        "tool": "business_card_watchdog_live_pilot_execution_checklist_from_response",
        "arguments": {"run_id": run_id, "response": "<operator-response>"},
    }
    assert operator_dashboard["mcp_tools"]["live_pilot_command_copy_packet_from_response"] == {
        "tool": "business_card_watchdog_live_pilot_command_copy_packet_from_response",
        "arguments": {
            "run_id": run_id,
            "response": "<operator-response>",
            "acknowledgement": "<operator-acknowledgement>",
        },
    }
    assert operator_dashboard["next_action_summary"]["by_action"] == {"review_contact": 1}
    assert operator_dashboard["live_pilot_handoff_summary"]["operator_required_count"] == 1
    assert len(operator_dashboard["live_pilot_summary"]["explicit_stop_conditions"]) == 3
    assert "This status report does not create selected_live_target.json." in (
        operator_dashboard["live_pilot_summary"]["explicit_stop_conditions"]
    )
    assert len(operator_dashboard["live_pilot_handoff_summary"]["operator_stop_conditions"]) == 4
    assert "Do not run live lookup, live write, or live readback from this handoff artifact." in (
        operator_dashboard["live_pilot_handoff_summary"]["operator_stop_conditions"]
    )
    assert operator_dashboard["live_pilot_handoff_summary"]["operator_entries"][0][
        "validation_command_prefilled"
    ].startswith(f"runs live-pilot-validate-response {run_id} --response 'run_id={run_id}")
    dashboard_sequence = operator_dashboard["live_pilot_handoff_summary"]["operator_entries"][0][
        "pilot_command_sequence_summary"
    ]
    assert dashboard_sequence["safe_inspection_step_count"] == 3
    assert dashboard_sequence["explicit_operator_step_count"] == 2
    assert dashboard_sequence["live_call_step_count"] == 1
    assert dashboard_sequence["sink_write_step_count"] == 0
    assert dashboard_sequence["next_safe_inspection_step"] == "validate_operator_response"
    assert dashboard_sequence["next_explicit_operator_step"] == "create_selected_target"
    dashboard_packet = operator_dashboard["live_pilot_handoff_summary"]["execution_packet"]
    assert dashboard_packet["schema"] == "business-card-watchdog.operator-dashboard.live-pilot-execution-packet.v1"
    assert dashboard_packet["state"] == "operator_required"
    assert dashboard_packet["operator_required_count"] == 1
    assert dashboard_packet["next_safe_command"].startswith(
        f"runs live-pilot-validate-response {run_id} --response 'run_id={run_id}"
    )
    assert dashboard_packet["next_explicit_operator_command"].startswith("sinks select-live-target ")
    assert dashboard_packet["forbidden_live_or_sink_write_from_dashboard"] is True
    assert dashboard_packet["writes_attempted"] == 0
    assert dashboard_packet["network_calls_made"] == 0
    assert operator_dashboard["writes_attempted"] == 0
    assert operator_dashboard["network_calls_made"] == 0
    assert summary["needs_review_count"] == 1
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
    assert readiness_report["schema"] == "business-card-watchdog.pilot-readiness-report.v1"
    assert readiness_report["blocked_job_ids"] == [job_id]
    assert readiness_report["commands"]["live_pilot_handoff"] == f"runs live-pilot-handoff {run_id}"
    assert runtime_readiness["schema"] == "business-card-watchdog.runtime-readiness.v1"
    assert runtime_readiness["network_calls_made"] == 0
    assert review_routing_drill["schema"] == "business-card-watchdog.review-routing-drill.v1"
    assert review_routing_drill["private_sources_used"] is False
    assert review_routing_drill["agent_loop_readback"]["state"] == "passed"
    assert review_routing_drill["agent_loop_readback"]["next_manual_boundary"] == "decide_sink_apply"
    assert review_routing_drill["safe_actions"]["skipped_actions"] == ["decide_sink_apply"]
    assert review_routing_drill["writes_attempted"] == 0
    assert review_routing_drill["network_calls_made"] == 0
    assert live_pilot_rehearsal_drill["schema"] == "business-card-watchdog.live-pilot-rehearsal-drill.v1"
    assert live_pilot_rehearsal_drill["state"] == "passed"
    assert live_pilot_rehearsal_drill["private_sources_used"] is False
    assert live_pilot_rehearsal_drill["live_sink_calls_made"] is False
    assert live_pilot_rehearsal_drill["command_copy_ready"] is True
    assert live_pilot_rehearsal_drill["packets"]["command_copy_packet"]["state"] == "ready_for_operator_copy"
    assert live_pilot_rehearsal_drill["writes_attempted"] == 0
    assert live_pilot_rehearsal_drill["network_calls_made"] == 0
    assert service_recovery["schema"] == "business-card-watchdog.service-recovery.v1"
    assert service_recovery["run_id"] == run_id
    assert service_recovery["commands"]["restart"] == "systemctl --user restart business-card-watchdog.service"
    assert service_recovery["commands"]["live_pilot_status"].endswith(
        f"runs live-pilot-status {run_id} --no-write --json"
    )
    assert service_recovery["commands"]["live_pilot_handoff"].endswith(f"runs live-pilot-handoff {run_id}")
    assert service_recovery["commands"]["review_routing_drill"].endswith("drills review-routing --json")
    assert any(action["action"] == "inspect_live_pilot_status" for action in service_recovery["safe_next_actions"])
    assert any(action["action"] == "inspect_live_pilot_handoff" for action in service_recovery["safe_next_actions"])
    assert any(
        action["action"] == "run_fixture_review_routing_drill"
        for action in service_recovery["safe_next_actions"]
    )
    assert service_recovery["writes_attempted"] == 0
    assert live_targets["schema"] == "business-card-watchdog.live-target-candidates.v1"
    assert live_targets["candidate_count"] == 1
    assert live_targets["network_calls_made"] == 0
    assert live_targets["commands"]["live_pilot_handoff"] == f"runs live-pilot-handoff {run_id}"
    assert live_targets["commands"]["validate_operator_response"] == (
        f"runs live-pilot-validate-response {run_id} --response <operator-response> --json"
    )
    assert live_targets["candidates"][0]["commands"]["validate_operator_response"] == (
        f"runs live-pilot-validate-response {run_id} --response <operator-response> --json"
    )
    assert live_audit["schema"] == "business-card-watchdog.live-readiness-audit.v1"
    assert live_audit["run_id"] == run_id
    assert live_audit["writes_attempted"] == 0
    assert live_audit["commands"]["live_pilot_handoff"] == f"runs live-pilot-handoff {run_id}"
    assert live_audit["commands"]["validate_operator_response"] == (
        f"runs live-pilot-validate-response {run_id} --response <operator-response> --json"
    )
    assert live_requirements["schema"] == "business-card-watchdog.live-selection-requirements.v1"
    assert live_requirements["run_id"] == run_id
    assert live_requirements["writes_attempted"] == 0
    assert live_requirements["network_calls_made"] == 0
    assert live_requirements["commands"]["live_pilot_handoff"] == f"runs live-pilot-handoff {run_id}"
    assert live_requirements["commands"]["validate_operator_response"] == (
        f"runs live-pilot-validate-response {run_id} --response <operator-response> --json"
    )
    assert live_requirements["operator_response_contract"]["schema"] == (
        "business-card-watchdog.operator-selection-response-contract.v1"
    )
    assert live_requirements["operator_response_contract"]["creates_selected_live_target"] is False
    assert live_requirements["entries"][0]["operator_response_template"] == (
        f"run_id={run_id} job_id={job_id} sink=google_contacts "
        "operator=<operator> scope=lookup safety_confirmation=<tenant-profile-account-confirmation>"
    )
    assert live_requirements["entries"][0]["commands"]["validate_operator_response"] == (
        f"runs live-pilot-validate-response {run_id} --response <operator-response> --json"
    )
    assert live_requirements["entries"][0]["commands"]["validate_operator_response_prefilled"] == (
        f"runs live-pilot-validate-response {run_id} "
        f"--response 'run_id={run_id} job_id={job_id} sink=google_contacts "
        "operator=<operator> scope=lookup safety_confirmation=<tenant-profile-account-confirmation>' --json"
    )
    assert live_requirements["entries"][0]["copyable_approval_fields"]["job_id"] == job_id
    assert live_packet["schema"] == "business-card-watchdog.live-selection-packet.v1"
    assert live_packet["approval_state"] == "pending_operator_approval"
    assert live_packet["writes_attempted"] == 0
    assert live_packet["existing_selected_target"]["exists"] is False
    assert live_packet["existing_selected_target"]["identity"] is None
    assert live_packet["existing_selected_target"]["abandoned"] is False
    assert live_packet["operator_response_template"] == (
        f"run_id={run_id} job_id={job_id} sink=google_contacts "
        "operator=mcp-test scope=lookup safety_confirmation=<tenant-profile-account-confirmation>"
    )
    assert live_packet["copyable_approval_fields"]["operator"] == "mcp-test"
    assert live_packet["commands"]["validate_operator_response"] == (
        f"runs live-pilot-validate-response {run_id} --response <operator-response> --json"
    )
    assert live_packet["commands"]["validate_operator_response_prefilled"] == (
        f"runs live-pilot-validate-response {run_id} "
        f"--response 'run_id={run_id} job_id={job_id} sink=google_contacts "
        "operator=mcp-test scope=lookup safety_confirmation=<tenant-profile-account-confirmation>' --json"
    )
    assert active_live_packet["state"] == "blocked"
    assert active_live_packet["existing_selected_target"]["exists"] is True
    assert active_live_packet["existing_selected_target"]["identity"] == selected_target["target"]["selection_id"]
    assert active_live_packet["existing_selected_target"]["target_safety_confirmed"] is True
    assert active_live_packet["existing_selected_target"]["replacement_requires_abandonment"] is True
    assert active_live_packet["existing_selected_target"]["can_select_replacement_now"] is False
    assert "abandon-live-pilot" in active_live_packet["existing_selected_target"]["abandon_command"]
    assert abandoned_live_packet["existing_selected_target"]["identity"] == selected_target["target"]["selection_id"]
    assert abandoned_live_packet["existing_selected_target"]["abandoned"] is True
    assert abandoned_live_packet["existing_selected_target"]["replacement_requires_abandonment"] is False
    assert abandoned_live_packet["existing_selected_target"]["can_select_replacement_now"] is True
    assert abandoned_live_packet["existing_selected_target"]["abandon_command"] is None
    assert watch_dry_run["schema"] == "business-card-watchdog.watch-dry-run-harness.v1"
    assert watch_dry_run["state"] == "passed"
    assert watch_dry_run["commands"]["watch_dry_run"] == "watch-dry-run --json"
    assert watch_dry_run["safe_next_actions"][0]["action"] == "inspect_watch_harness"
    assert [entry["job_id"] for entry in reviews] == [job_id]
    assert review_bundle["schema"] == "business-card-watchdog.review-bundle.v1"
    assert review_bundle["entries"][0]["job_id"] == job_id
    assert review_bundle["entries"][0]["next_action"]["action"] == "review_contact"
    assert review_bundle["groups"]["by_next_action"]["review_contact"]["count"] == 1
    assert review_bundle["decision_import_template"][0]["job_id"] == job_id
    assert review_bundle["commands"]["live_pilot_handoff"] == f"runs live-pilot-handoff {run_id}"
    assert review_bundle["commands"]["validate_operator_response"] == (
        f"runs live-pilot-validate-response {run_id} --response <operator-response> --json"
    )
    assert review_bundle["entries"][0]["commands"]["validate_operator_response"] == (
        f"runs live-pilot-validate-response {run_id} --response <operator-response> --json"
    )
    assert review_html["schema"] == "business-card-watchdog.review-html.v1"
    assert "Business Card Review" in review_html["html"]
    assert f"runs live-pilot-handoff {run_id}" in review_html["html"]
    assert review_workbook["schema"] == "business-card-watchdog.review-workbook.v1"
    workbook_rows = list(csv.DictReader(StringIO(review_workbook["csv"])))
    assert workbook_rows[0]["job_id"] == job_id
    assert workbook_rows[0]["next_action"] == "review_contact"
    assert workbook_rows[0]["review_action"] == "approve_for_routing"
    assert workbook_rows[0]["live_pilot_handoff_command"] == f"runs live-pilot-handoff {run_id}"
    assert workbook_rows[0]["validate_operator_response_command"] == (
        f"runs live-pilot-validate-response {run_id} --response <operator-response> --json"
    )
    workbook_rows[0]["review_action"] = "approve_for_routing"
    workbook_rows[0]["corrected_full_name"] = "MCP Workbook"
    workbook_csv = StringIO()
    workbook_writer = csv.DictWriter(workbook_csv, fieldnames=list(workbook_rows[0]))
    workbook_writer.writeheader()
    workbook_writer.writerows(workbook_rows)
    workbook_preview = call_tool(
        "business_card_watchdog_apply_review_decisions",
        {
            "run_id": run_id,
            "reviewer": "mcp-workbook",
            "decisions_csv": workbook_csv.getvalue(),
            "preview": True,
            "preview_write": True,
        },
        config=config,
    )
    assert workbook_preview["schema"] == "business-card-watchdog.review-workbook-preview.v1"
    assert workbook_preview["ready_count"] == 1
    assert "row_number,status,run_id,job_id,action,errors,warnings" in workbook_preview["validation_csv"]
    assert Path(workbook_preview["validation_csv_path"]).exists()
    assert workbook_preview["writes_attempted"] == 0
    workbook_validation = call_tool(
        "business_card_watchdog_review_workbook_validation",
        {"run_id": run_id, "reviewer": "mcp-workbook", "decisions_csv": workbook_csv.getvalue()},
        config=config,
    )
    assert workbook_validation["schema"] == "business-card-watchdog.review-workbook-preview.v1"
    assert workbook_validation["ready_count"] == 1
    assert "row_number,status,run_id,job_id,action,errors,warnings" in workbook_validation["validation_csv"]
    assert "validation_csv_path" not in workbook_validation
    workbook_import = call_tool(
        "business_card_watchdog_apply_review_decisions",
        {"run_id": run_id, "reviewer": "mcp-workbook", "decisions_csv": workbook_csv.getvalue()},
        config=config,
    )
    assert workbook_import["import"]["source_format"] == "csv"
    assert workbook_import["results"][0]["job_state"] == "ready_to_route"
    assert review_import["import"]["schema"] == "business-card-watchdog.review-decisions-import.v1"
    assert review_import["results"][0]["job_state"] == "ready_to_route"
    assert next_actions["actions"][0]["action"] == "review_contact"
    assert job["job_id"] == job_id
    assert lookup["lookup_plan"]["network_calls_made"] == 0
    assert preflight["preflight"]["state"] == "preview"
    assert preflight["preflight"]["writes_attempted"] == 0
    assert apply_decision["decision"]["state"] == "approved_for_apply"
    assert apply_decision["decision"]["network_calls_made"] == 0
    assert apply_result["result"]["state"] == "mock_applied"
    assert apply_result["result"]["writes_attempted"] == 0
    assert apply_result["result"]["readback"][0]["simulated"] is True
    assert pilot_readiness["readiness"]["schema"] == "business-card-watchdog.sink-apply-pilot-readiness.v1"
    assert pilot_readiness["readiness"]["selected_sink"] == "google_contacts"
    assert pilot_bundle["bundle"]["schema"] == "business-card-watchdog.sink-apply-pilot-bundle.v1"
    assert pilot_bundle["bundle"]["sink"] == "google_contacts"
    assert pilot_bundle["bundle"]["writes_attempted"] == 0
    assert selected_target["target"]["schema"] == "business-card-watchdog.selected-live-target.v1"
    assert selected_target["target"]["scope_allows"]["write"] is True
    assert selected_target_audit["schema"] == "business-card-watchdog.selected-live-target-audit.v1"
    assert selected_target_audit["selected_target_exists"] is True
    assert selected_target_audit["writes_attempted"] == 0
    assert live_closeout["report"]["schema"] == "business-card-watchdog.live-pilot-closeout.v1"
    assert live_closeout["report"]["writes_attempted"] == 0
    assert live_status["schema"] == "business-card-watchdog.live-pilot-status.v1"
    assert live_status["writes_attempted"] == 0
    assert live_status["commands"]["live_pilot_handoff"] == f"runs live-pilot-handoff {run_id}"
    assert live_status["commands"]["validate_operator_response"] == (
        f"runs live-pilot-validate-response {run_id} --response <operator-response> --json"
    )
    assert live_status["entries"][0]["selected_target_identity"] == selected_target["target"]["selection_id"]
    assert live_status["entries"][0]["abandonment_identity"] is None
    assert live_status["operator_response_contract"]["creates_selected_live_target"] is False
    assert live_status["entries"][0]["operator_response_template"] == (
        f"run_id={run_id} job_id={job_id} sink=google_contacts "
        "operator=mcp-test scope=all safety_confirmation=<tenant-profile-account-confirmation>"
    )
    assert live_status["entries"][0]["commands"]["validate_operator_response"] == (
        f"runs live-pilot-validate-response {run_id} --response <operator-response> --json"
    )
    assert live_handoff["schema"] == "business-card-watchdog.live-pilot-handoff.v1"
    assert live_handoff["action_counts"]["request_live_lookup_smoke"] == 1
    assert live_handoff["writes_attempted"] == 0
    assert live_handoff["entries"][0]["selected_target_identity"] == selected_target["target"]["selection_id"]
    assert live_handoff["entries"][0]["abandonment_identity"] is None
    assert live_handoff["commands"]["validate_operator_response"] == (
        f"runs live-pilot-validate-response {run_id} --response <operator-response> --json"
    )
    assert live_handoff["operator_response_contract"]["creates_selected_live_target"] is False
    assert live_handoff["entries"][0]["operator_response_template"] == (
        f"run_id={run_id} job_id={job_id} sink=google_contacts "
        "operator=mcp-test scope=all safety_confirmation=<tenant-profile-account-confirmation>"
    )
    assert live_handoff["entries"][0]["copyable_approval_fields"]["scope"] == "all"
    assert live_handoff["entries"][0]["pilot_command_checklist_summary"]["step_count"] == 8
    assert live_handoff["entries"][0]["pilot_command_checklist_summary"]["live_call_count"] == 3
    assert live_handoff["entries"][0]["pilot_command_checklist_summary"]["sink_write_step_count"] == 1
    mcp_sequence = live_handoff["entries"][0]["pilot_command_sequence"]
    assert mcp_sequence["safe_inspection_step_count"] == 4
    assert mcp_sequence["explicit_operator_step_count"] == 4
    assert mcp_sequence["live_call_step_count"] == 3
    assert mcp_sequence["sink_write_step_count"] == 1
    assert mcp_sequence["sink_write_steps"][0]["step"] == "live_write_pilot"
    assert mcp_sequence["execution_policy"]["requires_operator_before_sink_write_steps"] is True
    assert live_handoff["operator_response_template_count"] == 1
    assert live_handoff["operator_response_templates"][0]["schema"] == (
        "business-card-watchdog.operator-response-template.v1"
    )
    assert live_handoff["operator_response_templates"][0]["template"] == (
        f"run_id={run_id} job_id={job_id} sink=google_contacts "
        "operator=mcp-test scope=all safety_confirmation=<tenant-profile-account-confirmation>"
    )
    assert live_handoff["operator_response_templates"][0]["copyable_approval_fields"]["scope"] == "all"
    assert live_handoff["operator_response_templates"][0]["validation_command"] == (
        f"runs live-pilot-validate-response {run_id} --response <operator-response> --json"
    )
    assert live_handoff["operator_response_templates"][0]["validation_command_prefilled"] == (
        f"runs live-pilot-validate-response {run_id} "
        f"--response 'run_id={run_id} job_id={job_id} sink=google_contacts "
        "operator=mcp-test scope=all safety_confirmation=<tenant-profile-account-confirmation>' --json"
    )
    assert approval_packet["schema"] == "business-card-watchdog.live-pilot-approval-packet.v1"
    assert approval_packet["state"] == "ready"
    assert approval_packet["entry_count"] == 1
    assert approval_packet["entries"][0]["job_id"] == job_id
    assert approval_packet["entries"][0]["operator"] == "mcp-test"
    assert approval_packet["entries"][0]["scope"] == "all"
    assert approval_packet["entries"][0]["validation_command_prefilled"] == live_handoff["entries"][0]["commands"][
        "validate_operator_response_prefilled"
    ]
    assert approval_packet["creates_selected_live_target"] is False
    assert approval_packet["writes_attempted"] == 0
    assert approval_packet["network_calls_made"] == 0
    assert selected_target_preflight["schema"] == "business-card-watchdog.selected-live-target-preflight.v1"
    assert selected_target_preflight["state"] == "blocked"
    assert selected_target_preflight["would_create_selected_live_target"] is False
    assert selected_target_preflight["creates_selected_live_target"] is False
    assert selected_target_preflight["select_target_command"] is None
    assert "selected_live_target already exists" in selected_target_preflight["blocked_reasons"][0]
    assert selected_target_preflight["writes_attempted"] == 0
    assert selected_target_preflight["network_calls_made"] == 0
    assert selected_target_preview["schema"] == "business-card-watchdog.selected-live-target-artifact-preview.v1"
    assert selected_target_preview["state"] == "blocked"
    assert selected_target_preview["artifact_preview"] is None
    assert selected_target_preview["would_create_selected_live_target"] is False
    assert selected_target_preview["creates_selected_live_target"] is False
    assert "selected_live_target already exists" in selected_target_preview["blocked_reasons"][0]
    assert selected_target_preview["writes_attempted"] == 0
    assert selected_target_preview["network_calls_made"] == 0
    assert selected_target_from_response["schema"] == "business-card-watchdog.selected-live-target-from-response.v1"
    assert selected_target_from_response["state"] == "preview"
    assert selected_target_from_response["write_selected_target"] is False
    assert selected_target_from_response["preview"]["state"] == "blocked"
    assert selected_target_from_response["target"] is None
    assert selected_target_from_response["target_path"] is None
    assert selected_target_from_response["creates_selected_live_target"] is False
    assert selected_target_from_response["writes_attempted"] == 0
    assert selected_target_from_response["network_calls_made"] == 0
    assert selected_target_handoff_from_response["schema"] == (
        "business-card-watchdog.selected-live-target-handoff-from-response.v1"
    )
    assert selected_target_handoff_from_response["state"] == "audit_blocked"
    assert selected_target_handoff_from_response["job_id"] == job_id
    assert selected_target_handoff_from_response["validation_state"] == "ready_for_live_lookup_request"
    assert selected_target_handoff_from_response["selected_target_audit"]["state"] == "blocked"
    assert selected_target_handoff_from_response["write_audit"] is False
    assert selected_target_handoff_from_response["audit_written"] is False
    assert selected_target_handoff_from_response["creates_selected_live_target"] is False
    assert selected_target_handoff_from_response["writes_attempted"] == 0
    assert selected_target_handoff_from_response["network_calls_made"] == 0
    assert lookup_smoke_handoff_from_response["schema"] == (
        "business-card-watchdog.lookup-smoke-handoff-from-response.v1"
    )
    assert lookup_smoke_handoff_from_response["state"] == "handoff_blocked"
    assert lookup_smoke_handoff_from_response["job_id"] == job_id
    assert lookup_smoke_handoff_from_response["sink"] == "google_contacts"
    assert lookup_smoke_handoff_from_response["operator"] == "mcp-test"
    assert lookup_smoke_handoff_from_response["lookup_smoke_handoff"]["state"] == "blocked"
    assert lookup_smoke_handoff_from_response["write_handoff"] is False
    assert lookup_smoke_handoff_from_response["handoff_written"] is False
    assert lookup_smoke_handoff_from_response["writes_attempted"] == 0
    assert lookup_smoke_handoff_from_response["network_calls_made"] == 0
    assert selected_lookup_smoke_execution_packet_from_response["schema"] == (
        "business-card-watchdog.selected-lookup-smoke-execution-packet-from-response.v1"
    )
    assert selected_lookup_smoke_execution_packet_from_response["state"] == "blocked"
    assert selected_lookup_smoke_execution_packet_from_response["job_id"] == job_id
    assert selected_lookup_smoke_execution_packet_from_response["sink"] == "google_contacts"
    assert selected_lookup_smoke_execution_packet_from_response["operator"] == "mcp-test"
    assert selected_lookup_smoke_execution_packet_from_response["execute_selected_lookup_smoke"] is False
    assert selected_lookup_smoke_execution_packet_from_response["would_execute_selected_lookup_smoke"] is False
    assert selected_lookup_smoke_execution_packet_from_response["smoke"] is None
    assert selected_lookup_smoke_execution_packet_from_response["smoke_path"] is None
    assert selected_lookup_smoke_execution_packet_from_response["writes_attempted"] == 0
    assert selected_lookup_smoke_execution_packet_from_response["network_calls_made"] == 0
    assert selected_write_pilot_execution_packet_from_response["schema"] == (
        "business-card-watchdog.selected-write-pilot-execution-packet-from-response.v1"
    )
    assert selected_write_pilot_execution_packet_from_response["state"] == "blocked"
    assert selected_write_pilot_execution_packet_from_response["job_id"] == job_id
    assert selected_write_pilot_execution_packet_from_response["sink"] == "google_contacts"
    assert selected_write_pilot_execution_packet_from_response["operator"] == "mcp-test"
    assert selected_write_pilot_execution_packet_from_response["execute_write_pilot"] is False
    assert selected_write_pilot_execution_packet_from_response["would_execute_write_pilot"] is False
    assert selected_write_pilot_execution_packet_from_response["write_pilot"] is None
    assert selected_write_pilot_execution_packet_from_response["write_pilot_path"] is None
    assert selected_write_pilot_execution_packet_from_response["writes_attempted"] == 0
    assert selected_write_pilot_execution_packet_from_response["network_calls_made"] == 0
    assert selected_readback_pilot_execution_packet_from_response["schema"] == (
        "business-card-watchdog.selected-readback-pilot-execution-packet-from-response.v1"
    )
    assert selected_readback_pilot_execution_packet_from_response["state"] == "blocked"
    assert selected_readback_pilot_execution_packet_from_response["job_id"] == job_id
    assert selected_readback_pilot_execution_packet_from_response["sink"] == "google_contacts"
    assert selected_readback_pilot_execution_packet_from_response["operator"] == "mcp-test"
    assert selected_readback_pilot_execution_packet_from_response["execute_readback_pilot"] is False
    assert selected_readback_pilot_execution_packet_from_response["would_execute_readback_pilot"] is False
    assert selected_readback_pilot_execution_packet_from_response["readback_pilot"] is None
    assert selected_readback_pilot_execution_packet_from_response["readback_pilot_path"] is None
    assert selected_readback_pilot_execution_packet_from_response["writes_attempted"] == 0
    assert selected_readback_pilot_execution_packet_from_response["network_calls_made"] == 0
    assert live_pilot_closeout_packet_from_response["schema"] == (
        "business-card-watchdog.live-pilot-closeout-packet-from-response.v1"
    )
    assert live_pilot_closeout_packet_from_response["state"] == "closeout_incomplete"
    assert live_pilot_closeout_packet_from_response["job_id"] == job_id
    assert live_pilot_closeout_packet_from_response["sink"] == "google_contacts"
    assert live_pilot_closeout_packet_from_response["operator"] == "mcp-test"
    assert live_pilot_closeout_packet_from_response["write_closeout"] is False
    assert live_pilot_closeout_packet_from_response["closeout_written"] is False
    assert live_pilot_closeout_packet_from_response["closeout_path"] is None
    assert live_pilot_closeout_packet_from_response["closeout_report"]["state"] == "incomplete"
    assert live_pilot_closeout_packet_from_response["writes_attempted"] == 0
    assert live_pilot_closeout_packet_from_response["network_calls_made"] == 0
    assert live_pilot_operator_workflow_packet_from_response["schema"] == (
        "business-card-watchdog.live-pilot-operator-workflow-packet-from-response.v1"
    )
    assert live_pilot_operator_workflow_packet_from_response["state"] == "workflow_blocked"
    assert live_pilot_operator_workflow_packet_from_response["job_id"] == job_id
    assert live_pilot_operator_workflow_packet_from_response["sink"] == "google_contacts"
    assert live_pilot_operator_workflow_packet_from_response["operator"] == "mcp-test"
    assert live_pilot_operator_workflow_packet_from_response["blocked_step_count"] >= 1
    assert live_pilot_operator_workflow_packet_from_response["packets"]["live_pilot_closeout"]["state"] == (
        "closeout_incomplete"
    )
    assert [step["step"] for step in live_pilot_operator_workflow_packet_from_response["step_summary"]] == [
        "selected_target",
        "lookup_handoff",
        "lookup_smoke",
        "write_pilot",
        "readback_pilot",
        "closeout",
    ]
    assert live_pilot_operator_workflow_packet_from_response["writes_attempted"] == 0
    assert live_pilot_operator_workflow_packet_from_response["network_calls_made"] == 0
    assert live_pilot_operator_rehearsal_from_response["schema"] == (
        "business-card-watchdog.live-pilot-operator-rehearsal-from-response.v1"
    )
    assert live_pilot_operator_rehearsal_from_response["state"] == "ready_for_explicit_operator_step"
    assert live_pilot_operator_rehearsal_from_response["workflow_state"] == "workflow_blocked"
    assert live_pilot_operator_rehearsal_from_response["job_id"] == job_id
    assert live_pilot_operator_rehearsal_from_response["sink"] == "google_contacts"
    assert live_pilot_operator_rehearsal_from_response["operator"] == "mcp-test"
    assert live_pilot_operator_rehearsal_from_response["workflow_packet"]["schema"] == (
        "business-card-watchdog.live-pilot-operator-workflow-packet-from-response.v1"
    )
    assert live_pilot_operator_rehearsal_from_response["next_safe_command"].startswith(
        "runs live-pilot-operator-workflow-packet-from-response"
    )
    assert live_pilot_operator_rehearsal_from_response["next_explicit_operator_command"]
    assert live_pilot_operator_rehearsal_from_response["rehearsal_steps"][0]["safe_to_auto_continue"] is True
    assert live_pilot_operator_rehearsal_from_response["rehearsal_steps"][1][
        "requires_explicit_operator_action"
    ] is True
    assert live_pilot_operator_rehearsal_from_response["writes_attempted"] == 0
    assert live_pilot_operator_rehearsal_from_response["network_calls_made"] == 0
    assert live_pilot_readiness_export_from_response["schema"] == (
        "business-card-watchdog.live-pilot-readiness-export-from-response.v1"
    )
    assert live_pilot_readiness_export_from_response["state"] == "ready_for_explicit_operator_step"
    assert live_pilot_readiness_export_from_response["write"] is False
    assert live_pilot_readiness_export_from_response["export_written"] is False
    assert live_pilot_readiness_export_from_response["export_path"] is None
    assert live_pilot_readiness_export_from_response["operator_response_redacted"]["raw_response_stored"] is False
    assert "safety_confirmation" not in live_pilot_readiness_export_from_response["operator_response_redacted"]["fields"]
    assert "fixture contact is safe for google contacts test profile" not in json.dumps(
        live_pilot_readiness_export_from_response,
        sort_keys=True,
    )
    assert live_pilot_readiness_export_from_response["writes_attempted"] == 0
    assert live_pilot_readiness_export_from_response["network_calls_made"] == 0
    assert live_pilot_execution_checklist_from_response["schema"] == (
        "business-card-watchdog.live-pilot-execution-checklist-from-response.v1"
    )
    assert live_pilot_execution_checklist_from_response["state"] == "blocked"
    assert live_pilot_execution_checklist_from_response["readiness_export_loaded"] is False
    assert live_pilot_execution_checklist_from_response["executable_live_command"] is None
    assert (
        "live_pilot_readiness_export.json is required before showing executable live command"
        in live_pilot_execution_checklist_from_response["blocked_reasons"]
    )
    assert live_pilot_execution_checklist_from_response["writes_attempted"] == 0
    assert live_pilot_execution_checklist_from_response["network_calls_made"] == 0
    assert live_pilot_command_copy_packet_from_response["schema"] == (
        "business-card-watchdog.live-pilot-command-copy-packet-from-response.v1"
    )
    assert live_pilot_command_copy_packet_from_response["state"] == "blocked"
    assert live_pilot_command_copy_packet_from_response["checklist_state"] == "blocked"
    assert live_pilot_command_copy_packet_from_response["acknowledgement_required"] is True
    assert live_pilot_command_copy_packet_from_response["acknowledgement_ok"] is False
    assert live_pilot_command_copy_packet_from_response["command_copy_text"] is None
    assert live_pilot_command_copy_packet_from_response["executable_live_command"] is None
    assert (
        "operator acknowledgement is required before command copy text is shown"
        in live_pilot_command_copy_packet_from_response["blocked_reasons"]
    )
    assert live_pilot_command_copy_packet_from_response["writes_attempted"] == 0
    assert live_pilot_command_copy_packet_from_response["network_calls_made"] == 0
    assert operator_response_validation["schema"] == (
        "business-card-watchdog.live-pilot-operator-response-validation.v1"
    )
    assert operator_response_validation["state"] == "ready_for_live_lookup_request"
    assert operator_response_validation["next_validation_step"] == "selected_target_audit"
    assert operator_response_validation["matching_template"]["job_id"] == job_id
    assert operator_response_validation["select_target_command"] is None
    assert operator_response_validation["commands"]["select_target"] is None
    assert operator_response_validation["creates_selected_live_target"] is False
    assert operator_response_validation["writes_attempted"] == 0
    assert operator_response_validation["network_calls_made"] == 0
    assert abandonment["abandonment"]["schema"] == "business-card-watchdog.live-pilot-abandonment.v1"
    assert abandonment["abandonment"]["writes_attempted"] == 0
    assert write_pilot["pilot"]["schema"] == "business-card-watchdog.sink-write-pilot.v1"
    assert write_pilot["pilot"]["writes_attempted"] == 0
    assert write_pilot["result"]["state"] == "mock_applied"
    assert adapter_request["request"]["phase"] == "readback"
    assert adapter_request["request"]["network_calls_made"] == 0
    assert readback_pilot["pilot"]["schema"] == "business-card-watchdog.sink-readback-pilot.v1"
    assert readback_pilot["pilot"]["writes_attempted"] == 0
    assert readback_pilot["pilot"]["network_calls_made"] == 0
    assert pilot_report["report"]["schema"] == "business-card-watchdog.sink-apply-pilot-report.v1"
    assert pilot_report["report"]["state"] == "complete"
    assert lookup_pilot["pilot"]["schema"] == "business-card-watchdog.sink-lookup-pilot.v1"
    assert lookup_pilot["pilot"]["approved_by"] == "mcp-operator"
    assert lookup_pilot["pilot"]["writes_attempted"] == 0
    assert lookup_readiness["schema"] == "business-card-watchdog.live-lookup-readiness.v1"
    assert lookup_readiness["state"] == "blocked"
    assert lookup_handoff["handoff"]["schema"] == "business-card-watchdog.sink-lookup-smoke-handoff.v1"
    assert lookup_handoff["handoff"]["network_calls_made"] == 0
    assert lookup_result["result"]["state"] == "possible_duplicate"
    assert lookup_result["result"]["network_calls_made"] == 0
    assert downstream_duplicate["assessment"]["state"] == "strong_duplicate"
    assert downstream_duplicate["job"]["state"] == "needs_review"
    assert merge["submission"]["approved_enrichment_fields"] == ["notes"]
    assert duplicate["submission"]["duplicate_resolution"]["decision"] == "create_new"
    assert run_next["executed_count"] == 1
    assert run_next["executed"][0]["action"].startswith(("plan_", "prepare_", "record_", "assess_"))
    assert run_next["phase_report_before"]["schema"] == "business-card-watchdog.phase-report.v1"
    assert run_next["phase_report_after"]["schema"] == "business-card-watchdog.phase-report.v1"


def test_mcp_selected_lookup_smoke_uses_selected_target(tmp_path: Path, monkeypatch) -> None:
    import business_card_watchdog.service as service_module

    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        sink=SinkConfig(google_contacts=True, dry_run=True),
        routing_rules=[{"match": "email_domain", "value": "*", "sinks": ["google_contacts"]}],
    )
    run_id, job_id = make_recorded_run(config)

    def execute_lookup(request: dict[str, object]) -> dict[str, object]:
        return {
            "status": "read_only_lookup_completed",
            "network_calls_made": 1,
            "writes_attempted": 0,
            "matches": [{"resource_id": "people/mcp-smoke", "confidence": 0.9, "basis": ["email"], "raw": {"x": 1}}],
            "raw": {"results": [{"person": {"names": [{"displayName": "MCP Smoke"}]}}]},
        }

    monkeypatch.setattr(service_module, "execute_sink_lookup_adapter", execute_lookup)
    call_tool(
        "business_card_watchdog_sink_adapter_request",
        {"job_id": job_id, "run_id": run_id, "phase": "lookup"},
        config=config,
    )
    call_tool(
        "business_card_watchdog_selected_live_target",
        {
            "job_id": job_id,
            "run_id": run_id,
            "sink": "google_contacts",
            "operator": "mcp-smoke",
            "safety_confirmation": "fixture contact is safe for google contacts test profile",
        },
        config=config,
    )
    smoke = call_tool(
        "business_card_watchdog_selected_lookup_smoke",
        {"job_id": job_id, "run_id": run_id},
        config=config,
    )

    assert smoke["smoke"]["schema"] == "business-card-watchdog.selected-lookup-smoke.v1"
    assert smoke["smoke"]["network_calls_made"] == 1
    assert smoke["smoke"]["writes_attempted"] == 0
    assert smoke["assessment"]["state"] == "strong_duplicate"


def test_mcp_enrichment_request_can_prepare_paid_provider_without_call(tmp_path: Path) -> None:
    keys_path = tmp_path / "API-keys.env"
    keys_path.write_text("APOLLO_API_KEY=fixture-value-redacted\n", encoding="utf-8")
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        enrichment=EnrichmentConfig(
            enabled=True,
            allow_paid_api=True,
            api_keys_env=keys_path,
            apollo=EnrichmentProviderConfig(enabled=True),
        ),
    )
    run_id, job_id = make_recorded_run(config)
    artifact_dir = config.runs_dir / run_id / "artifacts" / job_id
    (artifact_dir / "contact_candidate.json").write_text(
        json.dumps(build_contact_candidate({"full_name": "Ada Lovelace", "email": "ada@example.test"}))
        + "\n",
        encoding="utf-8",
    )

    payload = call_tool(
        "business_card_watchdog_enrichment_request",
        {
            "job_id": job_id,
            "run_id": run_id,
            "mode": "api",
            "allow_paid_enrichment": True,
            "provider_results": [
                {
                    "person": {
                        "name": "Ada Lovelace",
                        "email": "ada@example.test",
                        "title": "Principal",
                    },
                    "organization": {"name": "Example Labs"},
                }
            ],
        },
        config=config,
    )

    assert payload["status"] == "ok"
    assert payload["provider_request"]["status"] == "prepared"
    assert payload["provider_request"]["network_calls_made"] == 0
    assert payload["provider_result"]["schema"] == "business-card-watchdog.enrichment-provider-result.v1"
    assert payload["provider_result"]["network_calls_made"] == 0
    assert "secret" not in json.dumps(payload)
    handoff = call_tool(
        "business_card_watchdog_provider_enrichment_handoff",
        {"job_id": job_id, "run_id": run_id},
        config=config,
    )
    result = call_tool(
        "business_card_watchdog_provider_enrichment_results",
        {
            "job_id": job_id,
            "run_id": run_id,
            "provider": "apollo",
            "submitted_by": "mcp-agent",
            "results": [
                {
                    "person": {
                        "name": "Ada Lovelace",
                        "email": "ada@example.test",
                        "title": "Principal",
                    },
                    "organization": {"name": "Example Labs"},
                }
            ],
        },
        config=config,
    )
    assert handoff["handoff"]["schema"] == "business-card-watchdog.enrichment-provider-handoff.v1"
    assert handoff["handoff"]["paid_api_calls_attempted"] == 0
    assert "secret" not in json.dumps(handoff)
    assert result["provider_result"]["submitted_by"] == "mcp-agent"
    assert result["provider_result"]["paid_api_calls_attempted"] == 0


def test_mcp_public_web_enrichment_results_are_explicit(tmp_path: Path) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        enrichment=EnrichmentConfig(enabled=True),
    )
    run_id, job_id = make_recorded_run(config)
    artifact_dir = config.runs_dir / run_id / "artifacts" / job_id
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
    request = call_tool(
        "business_card_watchdog_enrichment_request",
        {"job_id": job_id, "run_id": run_id, "mode": "public_web"},
        config=config,
    )
    handoff = call_tool(
        "business_card_watchdog_public_web_enrichment_handoff",
        {"job_id": job_id, "run_id": run_id},
        config=config,
    )
    payload = call_tool(
        "business_card_watchdog_public_web_enrichment_results",
        {
            "job_id": job_id,
            "run_id": run_id,
            "searched_by": "mcp-search",
            "results": [
                {
                    "title": "Ada Lovelace - Example Labs",
                    "url": "https://example.test/team/ada",
                    "snippet": "Contact Ada at ada@example.test",
                }
            ],
        },
        config=config,
    )

    assert request["public_web_request"]["network_calls_made"] == 0
    assert handoff["handoff"]["schema"] == "business-card-watchdog.enrichment-public-web-search-handoff.v1"
    assert handoff["handoff"]["search_calls_attempted"] == 0
    assert payload["public_web_result"]["schema"] == "business-card-watchdog.enrichment-public-web-result.v1"
    assert payload["public_web_result"]["searched_by"] == "mcp-search"
    assert payload["public_web_result"]["network_calls_made"] == 0
    assert payload["result"]["merge_proposals"][0]["field"] == "notes"


def test_mcp_call_tool_rejects_unknown_tool(tmp_path: Path) -> None:
    config = AppConfig(config_path=Path("config.toml"), data_dir=tmp_path / "data")

    try:
        call_tool("missing_tool", {}, config=config)
    except ValueError as exc:
        assert "unknown MCP tool" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_mcp_jsonl_server_lists_and_calls_tools(tmp_path: Path) -> None:
    config = AppConfig(config_path=tmp_path / "config.toml", data_dir=tmp_path / "data")
    run_id, job_id = make_recorded_run(config)
    BusinessCardService(config).select_live_target_for_job(
        job_id=job_id,
        run_id=run_id,
        sink="google_contacts",
        operator="mcp-jsonl",
        scope="lookup",
        safety_confirmation="fixture contact is safe for google contacts test profile",
    )
    operator_response = (
        f"run_id={run_id} job_id={job_id} sink=google_contacts "
        "operator=mcp-jsonl scope=lookup "
        "safety_confirmation=fixture contact is safe for google contacts test profile"
    )
    requests = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "business_card_watchdog_status", "arguments": {}},
        },
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "business_card_watchdog_phase_report",
                "arguments": {"run_id": run_id},
            },
        },
        {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {
                "name": "business_card_watchdog_pilot_readiness_report",
                "arguments": {"run_id": run_id},
            },
        },
        {
            "jsonrpc": "2.0",
            "id": 6,
            "method": "tools/call",
            "params": {
                "name": "business_card_watchdog_reviews_list",
                "arguments": {
                    "run_id": run_id,
                    "next_action": "review_contact",
                    "artifact_kind": "contact_spec",
                },
            },
        },
        {
            "jsonrpc": "2.0",
            "id": 7,
            "method": "tools/call",
            "params": {
                "name": "business_card_watchdog_apply_review_decisions",
                "arguments": {
                    "run_id": run_id,
                    "reviewer": "mcp-jsonl",
                    "decisions": [
                        {
                            "job_id": job_id,
                            "action": "approve_for_routing",
                            "field_corrections": {"full_name": "JSONL Transport"},
                        }
                    ],
                },
            },
        },
        {
            "jsonrpc": "2.0",
            "id": 8,
            "method": "tools/call",
            "params": {
                "name": "business_card_watchdog_run_next_actions",
                "arguments": {"run_id": run_id, "limit": 1},
            },
        },
        {
            "jsonrpc": "2.0",
            "id": 9,
            "method": "tools/call",
            "params": {
                "name": "business_card_watchdog_live_pilot_operator_response_validation",
                "arguments": {"run_id": run_id, "response": operator_response},
            },
        },
        {"jsonrpc": "2.0", "id": 10, "method": "shutdown", "params": {}},
    ]
    input_stream = StringIO(
        "\n".join(json.dumps(request, sort_keys=True) for request in requests) + "\n"
    )
    output_stream = StringIO()

    serve_jsonl(input_stream=input_stream, output_stream=output_stream, config=config)
    responses = [json.loads(line) for line in output_stream.getvalue().splitlines()]

    assert responses[0]["result"]["serverInfo"]["name"] == "business-card-watchdog"
    assert responses[1]["result"]["tools"][0]["inputSchema"]["type"] == "object"
    assert any(tool["name"] == "business_card_watchdog_status" for tool in responses[1]["result"]["tools"])
    assert any(
        tool["name"] == "business_card_watchdog_operator_dashboard"
        for tool in responses[1]["result"]["tools"]
    )
    assert any(
        tool["name"] == "business_card_watchdog_pilot_readiness_report"
        for tool in responses[1]["result"]["tools"]
    )
    assert responses[2]["result"]["isError"] is False
    assert responses[2]["result"]["structuredContent"]["skill_ready"] is True
    assert responses[2]["result"]["structuredContent"]["schema"] == "business-card-watchdog.status.v1"
    assert responses[2]["result"]["structuredContent"]["commands"]["runtime_readiness"] == "runtime-readiness --json"
    phase_report = responses[3]["result"]["structuredContent"]
    assert phase_report["schema"] == "business-card-watchdog.phase-report.v1"
    assert phase_report["review_workbook_preview"]["schema"] == (
        "business-card-watchdog.review-workbook-preview-phase.v1"
    )
    assert phase_report["review_workbook_preview"]["state"] == "not_started"
    assert phase_report["dashboard_summary"]["schema"] == "business-card-watchdog.phase-dashboard-summary.v1"
    assert phase_report["dashboard_summary"]["blocked_phases"] == [{"phase": "review", "count": 1}]
    assert phase_report["phases"][2]["phase"] == "review"
    assert phase_report["phases"][2]["counts"]["blocked"] == 1
    readiness_report = responses[4]["result"]["structuredContent"]
    assert readiness_report["schema"] == "business-card-watchdog.pilot-readiness-report.v1"
    assert readiness_report["blocked_job_ids"] == [job_id]
    reviews = responses[5]["result"]["structuredContent"]
    assert [entry["job_id"] for entry in reviews] == [job_id]
    assert reviews[0]["next_action"]["action"] == "review_contact"
    review_import = responses[6]["result"]["structuredContent"]
    assert review_import["import"]["schema"] == "business-card-watchdog.review-decisions-import.v1"
    assert review_import["results"][0]["job_state"] == "ready_to_route"
    run_next = responses[7]["result"]["structuredContent"]
    assert run_next["executed_count"] == 1
    assert run_next["executed"][0]["action"] == "plan_sink_lookup"
    assert run_next["phase_report_before"]["schema"] == "business-card-watchdog.phase-report.v1"
    assert run_next["phase_report_after"]["schema"] == "business-card-watchdog.phase-report.v1"
    operator_response_validation = responses[8]["result"]["structuredContent"]
    assert operator_response_validation["schema"] == (
        "business-card-watchdog.live-pilot-operator-response-validation.v1"
    )
    assert operator_response_validation["state"] == "ready_for_live_lookup_request"
    assert operator_response_validation["next_validation_step"] == "selected_target_audit"
    assert operator_response_validation["matching_template"]["job_id"] == job_id
    assert operator_response_validation["select_target_command"] is None
    assert operator_response_validation["commands"]["select_target"] is None
    assert operator_response_validation["selected_target_audit_command"] == (
        f"sinks selected-target-audit {job_id} --run-id {run_id} --scope lookup --no-write --json"
    )
    assert operator_response_validation["lookup_smoke_handoff_command"] == (
        f"sinks lookup-smoke-handoff {job_id} --run-id {run_id} --sink google_contacts --approved-by mcp-jsonl --json"
    )
    assert [item["step"] for item in operator_response_validation["post_selection_sequence"]] == [
        "selected_target_audit",
        "lookup_smoke_handoff",
    ]
    assert (
        operator_response_validation["post_selection_sequence"][1]["command"]
        == operator_response_validation["lookup_smoke_handoff_command"]
    )
    assert operator_response_validation["validation_command_sequence"]["safe_inspection_step_count"] == 2
    assert operator_response_validation["validation_command_sequence"]["explicit_operator_step_count"] == 0
    assert operator_response_validation["validation_command_sequence"]["live_call_step_count"] == 0
    assert operator_response_validation["validation_command_sequence"]["sink_write_step_count"] == 0
    approval_readback = operator_response_validation["approval_readback"]
    assert approval_readback["schema"] == "business-card-watchdog.live-pilot-operator-approval-readback.v1"
    assert approval_readback["state"] == "ready"
    assert approval_readback["validation_state"] == "ready_for_live_lookup_request"
    assert approval_readback["response_matches_template"] is True
    assert approval_readback["matched_template_job_id"] == job_id
    assert approval_readback["parsed_fields"]["operator"] == "mcp-jsonl"
    assert approval_readback["missing_field_count"] == 0
    assert approval_readback["mismatch_count"] == 0
    assert approval_readback["next_safe_step"] == "selected_target_audit"
    assert approval_readback["next_safe_command"] == operator_response_validation["selected_target_audit_command"]
    assert approval_readback["creates_selected_live_target"] is False
    assert approval_readback["writes_attempted"] == 0
    assert approval_readback["network_calls_made"] == 0
    assert operator_response_validation["creates_selected_live_target"] is False
    assert operator_response_validation["writes_attempted"] == 0
    assert operator_response_validation["network_calls_made"] == 0
    assert responses[9]["result"]["shutdown"] is True

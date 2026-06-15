from __future__ import annotations

import json
import csv
from io import StringIO
from pathlib import Path

from business_card_watchdog.config import AppConfig, PrefilterConfig, SinkConfig
from business_card_watchdog.orchestrator import BatchOrchestrator
from business_card_watchdog.service import BusinessCardService

from synthetic_fixtures import (
    SyntheticSkillAdapter,
    latest_jobs_by_id,
    read_jsonl,
    write_multi_card_image,
    write_synthetic_image,
)


def test_review_approval_writes_reviewed_contact_artifact(tmp_path: Path, monkeypatch) -> None:
    source_dir = tmp_path / "synthetic-cards"
    write_synthetic_image(source_dir / "incomplete.png")
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        cache_dir=tmp_path / "cache",
        prefilter=PrefilterConfig(process_uncertain=True),
        sink=SinkConfig(google_contacts=True, odoo=True, dry_run=True),
    )
    orchestrator = BatchOrchestrator(config)
    monkeypatch.setattr(
        orchestrator,
        "adapter",
        SyntheticSkillAdapter(specs_by_stem={"incomplete": {"full_name": "", "email": "", "phone": ""}}),
    )
    run_dir = orchestrator.process_source(str(source_dir), dry_run=True, workers=1)
    job = next(iter(latest_jobs_by_id(run_dir / "jobs.jsonl").values()))

    result = BusinessCardService(config).submit_review(
        job_id=job["job_id"],
        run_id=run_dir.name,
        reviewer="operator",
        action="approve_for_routing",
        field_corrections={
            "full_name": "Reviewed Person",
            "email": " REVIEWED@EXAMPLE.TEST ",
        },
        notes="approved from synthetic fixture",
    )

    reviewed_path = Path(result["job"]["artifact_dir"]) / "reviewed_contact.json"
    reviewed = json.loads(reviewed_path.read_text(encoding="utf-8"))
    artifacts = read_jsonl(run_dir / "artifacts.jsonl")
    events = read_jsonl(run_dir / "events.jsonl")

    assert result["job"]["state"] == "ready_to_route"
    assert reviewed["schema"] == "business-card-watchdog.reviewed-contact.v1"
    assert reviewed["flat"]["email"] == "reviewed@example.test"
    assert any(artifact["kind"] == "reviewed_contact" for artifact in artifacts)
    assert any(event["event_type"] == "review_submitted" for event in events)


def test_child_review_queue_lists_promoted_child_contact_candidates(tmp_path: Path, monkeypatch) -> None:
    pytest = __import__("pytest")
    pytest.importorskip("cv2")
    source_dir = tmp_path / "images"
    write_multi_card_image(source_dir / "multi.jpg")
    config = AppConfig(config_path=tmp_path / "config.toml", data_dir=tmp_path / "data")
    orchestrator = BatchOrchestrator(config)
    monkeypatch.setattr(orchestrator, "adapter", SyntheticSkillAdapter())
    run_dir = orchestrator.process_source(str(source_dir), dry_run=True, workers=1)

    queue = BusinessCardService(config).child_review_queue(run_id=run_dir.name)

    assert len(queue) >= 3
    assert queue[0]["schema"] == "business-card-watchdog.child-review-queue-entry.v1"
    assert queue[0]["state"] == "needs_review"
    assert queue[0]["next_action"]["action"] == "review_child_contact"
    assert queue[0]["routing_allowed"] is False
    assert queue[0]["contact_candidate"]["schema"] == "business-card-watchdog.contact-candidate.v1"
    assert queue[0]["contact_candidate"]["lineage"]["parent_job_id"] == queue[0]["job_id"]
    assert BusinessCardService(config).child_review_queue(run_id=run_dir.name, state="all")


def test_service_child_replacement_readiness_drill_exports_operator_samples(tmp_path: Path) -> None:
    config = AppConfig(config_path=tmp_path / "config.toml", data_dir=tmp_path / "data", cache_dir=tmp_path / "cache")

    drill = BusinessCardService(config).child_replacement_readiness_drill()

    assert drill["schema"] == "business-card-watchdog.child-replacement-readiness-drill.v1"
    assert drill["state"] == "passed"
    assert drill["private_sources_used"] is False
    assert drill["public_web_search_used"] is False
    assert drill["paid_enrichment_used"] is False
    assert drill["live_sink_calls_made"] is False
    assert drill["writes_attempted"] == 0
    assert drill["network_calls_made"] == 0
    assert drill["readiness_states"]["blocked_replacement_audit"] == "blocked"
    assert drill["readiness_states"]["blocked_replacement_validation"] == "blocked"
    assert drill["readiness_states"]["replacement_handoff"] == "ready_for_replacement_handoff"
    assert drill["readiness_states"]["replacement_response"] == "ready_for_no_live_replacement_checklist"
    assert drill["readiness_states"]["replacement_checklist"] == "ready_for_replacement_operator_review"
    assert drill["readiness_states"]["ready_replacement_copy_packet"] == "ready_for_replacement_operator_copy"
    assert drill["readiness_states"]["closeout"] == "ready_for_operator_closeout"
    assert drill["closeout_rollup"]["predecessor_artifacts_stale"] is True
    assert drill["review_bundle_child_replacement_groups"]["ready_for_operator_closeout"]["count"] == 1
    assert drill["operator_dashboard_child_replacement_summary"]["ready_count"] == 1
    assert Path(drill["sample_outputs"]["review_bundle_path"]).exists()
    assert Path(drill["sample_outputs"]["review_html_path"]).exists()
    assert Path(drill["sample_outputs"]["review_workbook_path"]).exists()
    sample_output_path = Path(drill["sample_outputs"]["child_replacement_readiness_markdown_path"])
    sample_output = sample_output_path.read_text(encoding="utf-8")
    assert sample_output_path.exists()
    assert "# Child Replacement Readiness Sample Output" in sample_output
    assert "ready_replacement_copy_packet: `ready_for_replacement_operator_copy`" in sample_output
    assert "approved fixture replacement google contacts target profile" not in sample_output
    assert Path(drill["drill_path"]).exists()


def test_child_review_approval_writes_reviewed_child_contact_artifact(tmp_path: Path, monkeypatch) -> None:
    pytest = __import__("pytest")
    pytest.importorskip("cv2")
    source_dir = tmp_path / "images"
    write_multi_card_image(source_dir / "multi.jpg")
    config = AppConfig(config_path=tmp_path / "config.toml", data_dir=tmp_path / "data")
    orchestrator = BatchOrchestrator(config)
    monkeypatch.setattr(orchestrator, "adapter", SyntheticSkillAdapter())
    run_dir = orchestrator.process_source(str(source_dir), dry_run=True, workers=1)
    service = BusinessCardService(config)
    candidate_id = str(service.child_review_queue(run_id=run_dir.name)[0]["candidate_id"])

    result = service.submit_child_review(
        run_id=run_dir.name,
        candidate_id=candidate_id,
        reviewer="operator",
        action="approve_child_for_routing",
        field_corrections={"email": " reviewed-child@example.test "},
        notes="approved synthetic child contact",
    )

    reviewed_path = Path(str(result["reviewed_child_contact_path"]))
    reviewed = json.loads(reviewed_path.read_text(encoding="utf-8"))
    artifacts = read_jsonl(run_dir / "artifacts.jsonl")
    events = read_jsonl(run_dir / "events.jsonl")
    approved_queue = service.child_review_queue(run_id=run_dir.name, state="approved_for_dedupe")

    assert result["schema"] == "business-card-watchdog.child-review-submission-result.v1"
    assert result["state"] == "approved_for_dedupe"
    assert result["writes_attempted"] == 0
    assert result["network_calls_made"] == 0
    assert reviewed["schema"] == "business-card-watchdog.reviewed-contact.v1"
    assert reviewed["flat"]["email"] == "reviewed-child@example.test"
    assert reviewed["review"]["state"] == "approved_for_dedupe"
    assert reviewed["routing_allowed"] is True
    assert reviewed["sink_write_allowed"] is False
    assert any(artifact["kind"] == "child_review_submission" for artifact in artifacts)
    assert any(artifact["kind"] == "reviewed_child_contact" for artifact in artifacts)
    assert any(artifact["kind"] == "child_contact_review_result" for artifact in artifacts)
    assert any(event["event_type"] == "child_contact_review_submitted" for event in events)
    assert any(entry["candidate_id"] == candidate_id for entry in approved_queue)


def test_child_route_prep_writes_dry_run_lookup_and_sink_plans(tmp_path: Path, monkeypatch) -> None:
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

    queue = service.child_route_prep_queue(run_id=run_dir.name)
    result = service.prepare_child_route(run_id=run_dir.name, candidate_id=candidate_id)

    lookup_plan = json.loads(Path(result["lookup_plan_path"]).read_text(encoding="utf-8"))
    sink_plan = json.loads(Path(result["sink_plan_path"]).read_text(encoding="utf-8"))
    artifacts = read_jsonl(run_dir / "artifacts.jsonl")
    events = read_jsonl(run_dir / "events.jsonl")

    assert any(entry["candidate_id"] == candidate_id for entry in queue)
    assert result["state"] == "routing_prepared"
    assert result["writes_attempted"] == 0
    assert result["network_calls_made"] == 0
    assert lookup_plan["schema"] == "business-card-watchdog.sink-lookup-plan.v1"
    assert lookup_plan["dry_run"] is True
    assert lookup_plan["candidate_id"] == candidate_id
    assert lookup_plan["lookups"][0]["sink"] == "google_contacts"
    assert sink_plan["schema"] == "business-card-watchdog.sink-plan.v1"
    assert sink_plan["dry_run"] is True
    assert sink_plan["candidate_id"] == candidate_id
    assert result["result"]["sink_write_allowed"] is False
    assert any(artifact["kind"] == "child_sink_lookup_plan" for artifact in artifacts)
    assert any(artifact["kind"] == "child_sink_plan" for artifact in artifacts)
    assert any(artifact["kind"] == "child_route_prep_result" for artifact in artifacts)
    assert any(event["event_type"] == "child_route_prepared" for event in events)


def test_child_lookup_result_and_duplicate_assessment_use_fixture_matches(
    tmp_path: Path,
    monkeypatch,
) -> None:
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

    lookup = service.record_child_sink_lookup_result(
        run_id=run_dir.name,
        candidate_id=candidate_id,
        matches_by_sink={
            "google_contacts": [
                {
                    "resource_id": "people/fixture-child-1",
                    "confidence": 0.98,
                    "basis": ["email"],
                    "display": "Fixture Existing Contact",
                }
            ]
        },
    )
    assessment = service.assess_child_downstream_duplicates(
        run_id=run_dir.name,
        candidate_id=candidate_id,
    )
    artifacts = read_jsonl(run_dir / "artifacts.jsonl")
    events = read_jsonl(run_dir / "events.jsonl")

    assert lookup["result"]["state"] == "possible_duplicate"
    assert lookup["result"]["match_count"] == 1
    assert lookup["result"]["candidate_id"] == candidate_id
    assert lookup["writes_attempted"] == 0
    assert lookup["network_calls_made"] == 0
    assert assessment["assessment"]["state"] == "strong_duplicate"
    assert assessment["assessment"]["candidate_id"] == candidate_id
    assert assessment["assessment"]["reviewed"] is False
    assert assessment["writes_attempted"] == 0
    assert assessment["network_calls_made"] == 0
    assert any(artifact["kind"] == "child_sink_adapter_request_lookup" for artifact in artifacts)
    assert any(artifact["kind"] == "child_sink_lookup_result" for artifact in artifacts)
    assert any(artifact["kind"] == "child_downstream_duplicate_assessment" for artifact in artifacts)
    assert any(event["event_type"] == "child_sink_lookup_result_recorded" for event in events)
    assert any(event["event_type"] == "child_downstream_duplicate_assessed" for event in events)


def test_child_duplicate_resolution_clears_sink_plan_gate(tmp_path: Path, monkeypatch) -> None:
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
        matches_by_sink={"google_contacts": [{"resource_id": "people/existing", "basis": ["email"]}]},
    )
    service.assess_child_downstream_duplicates(run_id=run_dir.name, candidate_id=candidate_id)

    blocked = service.child_sink_plan_gate(run_id=run_dir.name, candidate_id=candidate_id)
    resolution = service.resolve_child_duplicate(
        run_id=run_dir.name,
        candidate_id=candidate_id,
        reviewer="operator",
        decision="create_new",
        reason="confirmed separate person",
    )
    cleared = service.child_sink_plan_gate(run_id=run_dir.name, candidate_id=candidate_id)
    artifacts = read_jsonl(run_dir / "artifacts.jsonl")
    events = read_jsonl(run_dir / "events.jsonl")

    assert blocked["gate"]["state"] == "blocked"
    assert blocked["gate"]["blocked_reasons"] == ["child_duplicate_state_unresolved:strong_duplicate"]
    assert resolution["resolution"]["decision"] == "create_new"
    assert resolution["resolution"]["sink_write_allowed"] is False
    assert cleared["gate"]["state"] == "ready_for_sink_plan"
    assert cleared["gate"]["routing_allowed"] is True
    assert cleared["gate"]["sink_write_allowed"] is False
    assert cleared["writes_attempted"] == 0
    assert cleared["network_calls_made"] == 0
    assert any(artifact["kind"] == "child_duplicate_resolution" for artifact in artifacts)
    assert any(artifact["kind"] == "child_sink_plan_gate" for artifact in artifacts)
    assert any(event["event_type"] == "child_duplicate_resolved" for event in events)
    assert any(event["event_type"] == "child_sink_plan_gate_created" for event in events)


def test_child_sink_apply_preflight_and_selected_target_handoff(tmp_path: Path, monkeypatch) -> None:
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

    preflight = service.child_sink_apply_preflight(run_id=run_dir.name, candidate_id=candidate_id)
    handoff = service.child_selected_target_handoff(
        run_id=run_dir.name,
        candidate_id=candidate_id,
        sink="google_contacts",
        operator="operator",
        reason="synthetic child target review",
    )
    artifacts = read_jsonl(run_dir / "artifacts.jsonl")
    events = read_jsonl(run_dir / "events.jsonl")

    assert preflight["preflight"]["schema"] == "business-card-watchdog.child-sink-apply-preflight.v1"
    assert preflight["preflight"]["state"] == "preview"
    assert preflight["preflight"]["can_apply"] is False
    assert preflight["preflight"]["sink_write_allowed"] is False
    assert handoff["handoff"]["schema"] == "business-card-watchdog.child-selected-target-handoff.v1"
    assert handoff["handoff"]["state"] == "ready_for_operator_selection"
    assert handoff["handoff"]["selected_target_created"] is False
    assert handoff["handoff"]["writes_attempted"] == 0
    assert handoff["handoff"]["network_calls_made"] == 0
    assert "Do not run live lookup, live write, or live readback from this child handoff." in handoff["handoff"][
        "explicit_stop_conditions"
    ]
    assert any(artifact["kind"] == "child_sink_apply_preflight" for artifact in artifacts)
    assert any(artifact["kind"] == "child_selected_target_handoff" for artifact in artifacts)
    assert any(event["event_type"] == "child_sink_apply_preflight_created" for event in events)
    assert any(event["event_type"] == "child_selected_target_handoff_created" for event in events)


def test_child_selected_target_response_validation_and_checklist(tmp_path: Path, monkeypatch) -> None:
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
    handoff = service.child_selected_target_handoff(
        run_id=run_dir.name,
        candidate_id=candidate_id,
        sink="google_contacts",
        operator="operator",
        scope="write",
    )["handoff"]
    template = handoff["operator_response_template"]
    response = (
        f"run_id={template['run_id']} job_id={template['job_id']} "
        f"candidate_id={template['candidate_id']} work_item_id={template['work_item_id']} "
        "sink=google_contacts operator=operator scope=write "
        "safety_confirmation='approved google contacts target profile'"
    )

    validation = service.validate_child_selected_target_response(
        run_id=run_dir.name,
        candidate_id=candidate_id,
        response=response,
    )
    checklist = service.child_selected_target_execution_checklist(
        run_id=run_dir.name,
        candidate_id=candidate_id,
        response=response,
    )
    blocked_copy_packet = service.child_selected_target_command_copy_packet(
        run_id=run_dir.name,
        candidate_id=candidate_id,
        response=response,
    )
    ready_copy_packet = service.child_selected_target_command_copy_packet(
        run_id=run_dir.name,
        candidate_id=candidate_id,
        response=response,
        acknowledgement=(
            f"I acknowledge run_id={run_dir.name} candidate_id={candidate_id} "
            "sink=google_contacts operator=operator ready to copy"
        ),
    )
    audit = service.child_selected_target_audit(run_id=run_dir.name, candidate_id=candidate_id)
    replacement_audit = service.child_selected_target_audit(
        run_id=run_dir.name,
        candidate_id=candidate_id,
        operator="replacement-operator",
    )
    abandonment = service.abandon_child_selected_target(
        run_id=run_dir.name,
        candidate_id=candidate_id,
        operator="operator",
        reason="replace child selected target preview",
    )
    reset = service.child_selected_target_replacement_reset(
        run_id=run_dir.name,
        candidate_id=candidate_id,
        sink="google_contacts",
        operator="replacement-operator",
        scope="write",
        reset_by="operator",
        reason="replacement preview requested",
    )
    blocked_replacement_validation = service.validate_child_replacement_response(
        run_id=run_dir.name,
        candidate_id=candidate_id,
        response=response,
    )
    refresh = service.refresh_child_replacement_handoff(
        run_id=run_dir.name,
        candidate_id=candidate_id,
        sink="google_contacts",
        operator="replacement-operator",
        scope="write",
        reason="replacement handoff refresh",
    )
    replacement_template = refresh["refreshed_handoff"]["operator_response_template"]
    replacement_response = (
        f"run_id={replacement_template['run_id']} job_id={replacement_template['job_id']} "
        f"candidate_id={replacement_template['candidate_id']} "
        f"work_item_id={replacement_template['work_item_id']} "
        "sink=google_contacts operator=replacement-operator scope=write "
        "safety_confirmation='approved replacement google contacts target profile'"
    )
    replacement_validation = service.validate_child_replacement_response(
        run_id=run_dir.name,
        candidate_id=candidate_id,
        response=replacement_response,
    )
    replacement_checklist = service.child_replacement_execution_checklist(
        run_id=run_dir.name,
        candidate_id=candidate_id,
        response=replacement_response,
    )
    blocked_replacement_copy_packet = service.child_replacement_command_copy_packet(
        run_id=run_dir.name,
        candidate_id=candidate_id,
        response=replacement_response,
    )
    ready_replacement_copy_packet = service.child_replacement_command_copy_packet(
        run_id=run_dir.name,
        candidate_id=candidate_id,
        response=replacement_response,
        acknowledgement=(
            f"I acknowledge run_id={run_dir.name} candidate_id={candidate_id} "
            "sink=google_contacts operator=replacement-operator ready to copy"
        ),
    )
    closeout = service.child_replacement_closeout_status(
        run_id=run_dir.name,
        candidate_id=candidate_id,
    )
    artifacts = read_jsonl(run_dir / "artifacts.jsonl")
    events = read_jsonl(run_dir / "events.jsonl")

    assert validation["schema"] == "business-card-watchdog.child-selected-target-response-validation.v1"
    assert validation["state"] == "ready_for_no_live_child_checklist"
    assert validation["creates_selected_live_target"] is False
    assert checklist["schema"] == "business-card-watchdog.child-selected-target-execution-checklist.v1"
    assert checklist["state"] == "ready_for_operator_review"
    assert checklist["selected_target_created"] is False
    assert checklist["executable_live_command"] is None
    assert checklist["writes_attempted"] == 0
    assert checklist["network_calls_made"] == 0
    assert all(item["ok"] for item in checklist["checklist_items"])
    assert "safety_confirmation" not in checklist["operator_response_redacted"]["fields"]
    assert blocked_copy_packet["schema"] == "business-card-watchdog.child-selected-target-command-copy-packet.v1"
    assert blocked_copy_packet["state"] == "blocked"
    assert blocked_copy_packet["acknowledgement_ok"] is False
    assert blocked_copy_packet["command_copy_text"] is None
    assert "operator acknowledgement is required before child command copy text is shown" in blocked_copy_packet[
        "blocked_reasons"
    ]
    assert ready_copy_packet["state"] == "ready_for_operator_copy"
    assert ready_copy_packet["acknowledgement_ok"] is True
    assert ready_copy_packet["command_copy_text"].startswith("reviews child-selected-target-execution-checklist")
    assert ready_copy_packet["executable_live_command"] is None
    assert ready_copy_packet["selected_target_created"] is False
    assert ready_copy_packet["writes_attempted"] == 0
    assert ready_copy_packet["network_calls_made"] == 0
    assert ready_copy_packet["acknowledgement_redacted"]["raw_acknowledgement_stored"] is False
    assert audit["schema"] == "business-card-watchdog.child-selected-target-audit.v1"
    assert audit["state"] == "ready"
    assert audit["selected_target_exists"] is True
    assert audit["replacement_requested"] is False
    assert audit["replacement_requires_abandonment"] is False
    assert audit["abandonment_supported"] is False
    assert audit["writes_attempted"] == 0
    assert audit["network_calls_made"] == 0
    assert replacement_audit["state"] == "blocked"
    assert replacement_audit["replacement_requested"] is True
    assert replacement_audit["replacement_requires_abandonment"] is True
    assert "replacement requires child selected-target abandonment before a new target preview" in replacement_audit[
        "blocked_reasons"
    ]
    assert abandonment["schema"] == "business-card-watchdog.child-selected-target-abandonment.v1"
    assert abandonment["state"] == "abandoned"
    assert abandonment["selected_target_identity"] == audit["selected_target_identity"]
    assert abandonment["writes_attempted"] == 0
    assert abandonment["network_calls_made"] == 0
    assert reset["schema"] == "business-card-watchdog.child-selected-target-replacement-reset.v1"
    assert reset["state"] == "ready_for_replacement_preview"
    assert reset["replacement_unblocked"] is True
    assert reset["replacement_requires_abandonment"] is False
    assert reset["requested_target"]["operator"] == "replacement-operator"
    assert reset["writes_attempted"] == 0
    assert reset["network_calls_made"] == 0
    assert blocked_replacement_validation["schema"] == (
        "business-card-watchdog.child-replacement-response-validation.v1"
    )
    assert blocked_replacement_validation["state"] == "blocked"
    assert "child replacement handoff refresh artifact is missing" in blocked_replacement_validation[
        "blocked_reasons"
    ]
    assert "child selected-target staleness marker is missing" in blocked_replacement_validation["blocked_reasons"]
    assert refresh["schema"] == "business-card-watchdog.child-replacement-handoff-refresh.v1"
    assert refresh["state"] == "ready_for_replacement_handoff"
    assert refresh["refreshed_handoff"]["state"] == "ready_for_operator_selection"
    assert refresh["refreshed_handoff"]["operator"] == "replacement-operator"
    assert refresh["staleness"]["state"] == "stale"
    assert any(item["kind"] == "child_selected_target_command_copy_packet" for item in refresh["staleness"]["stale_artifacts"])
    assert refresh["writes_attempted"] == 0
    assert refresh["network_calls_made"] == 0
    assert replacement_validation["schema"] == "business-card-watchdog.child-replacement-response-validation.v1"
    assert replacement_validation["state"] == "ready_for_no_live_replacement_checklist"
    assert replacement_validation["stale_enforcement"]["staleness_marker_present"] is True
    assert replacement_validation["stale_enforcement"]["staleness_state"] == "stale"
    assert "child_selected_target_command_copy_packet" in replacement_validation["stale_enforcement"][
        "stale_artifact_kinds"
    ]
    assert replacement_validation["parsed_response"]["operator"] == "replacement-operator"
    assert replacement_validation["selected_target_created"] is False
    assert replacement_validation["writes_attempted"] == 0
    assert replacement_validation["network_calls_made"] == 0
    assert replacement_checklist["schema"] == "business-card-watchdog.child-replacement-execution-checklist.v1"
    assert replacement_checklist["state"] == "ready_for_replacement_operator_review"
    assert all(item["ok"] for item in replacement_checklist["checklist_items"])
    assert replacement_checklist["stale_enforcement"]["staleness_state"] == "stale"
    assert replacement_checklist["executable_live_command"] is None
    assert replacement_checklist["selected_target_created"] is False
    assert replacement_checklist["writes_attempted"] == 0
    assert replacement_checklist["network_calls_made"] == 0
    assert "safety_confirmation" not in replacement_checklist["operator_response_redacted"]["fields"]
    assert blocked_replacement_copy_packet["schema"] == (
        "business-card-watchdog.child-replacement-command-copy-packet.v1"
    )
    assert blocked_replacement_copy_packet["state"] == "blocked"
    assert blocked_replacement_copy_packet["acknowledgement_ok"] is False
    assert blocked_replacement_copy_packet["command_copy_text"] is None
    assert "operator acknowledgement is required before replacement command copy text is shown" in (
        blocked_replacement_copy_packet["blocked_reasons"]
    )
    assert ready_replacement_copy_packet["state"] == "ready_for_replacement_operator_copy"
    assert ready_replacement_copy_packet["acknowledgement_ok"] is True
    assert ready_replacement_copy_packet["command_copy_text"].startswith(
        "reviews child-replacement-execution-checklist"
    )
    assert ready_replacement_copy_packet["executable_live_command"] is None
    assert ready_replacement_copy_packet["selected_target_created"] is False
    assert ready_replacement_copy_packet["writes_attempted"] == 0
    assert ready_replacement_copy_packet["network_calls_made"] == 0
    assert ready_replacement_copy_packet["acknowledgement_redacted"]["raw_acknowledgement_stored"] is False
    assert closeout["schema"] == "business-card-watchdog.child-replacement-closeout-status.v1"
    assert closeout["state"] == "ready_for_operator_closeout"
    assert closeout["rollup"]["predecessor_artifacts_stale"] is True
    assert closeout["rollup"]["replacement_handoff_ready"] is True
    assert closeout["rollup"]["replacement_response_ready"] is True
    assert closeout["rollup"]["replacement_checklist_ready"] is True
    assert closeout["rollup"]["replacement_copy_ready"] is True
    assert closeout["rollup"]["acknowledgement_ok"] is True
    assert closeout["rollup"]["selected_target_created"] is False
    assert closeout["rollup"]["executable_live_command"] is None
    assert closeout["writes_attempted"] == 0
    assert closeout["network_calls_made"] == 0
    bundle = service.review_bundle(run_id=run_dir.name, state="all", write=False)
    bundle_entry = next(
        entry
        for entry in bundle["entries"]
        if entry["job_id"] == closeout["job_id"]
    )
    assert "child_replacement_closeout_status" in bundle_entry["artifact_kinds"]
    assert bundle_entry["child_replacement_status"]["state"] == "ready_for_operator_closeout"
    assert bundle_entry["child_replacement_status"]["predecessor_artifacts_stale"] is True
    assert bundle["groups"]["by_child_replacement_state"]["ready_for_operator_closeout"]["count"] == 1
    html = service.review_html(run_id=run_dir.name, state="all", write=False)
    assert "By Child Replacement State" in html["html"]
    assert "ready_for_operator_closeout" in html["html"]
    workbook = service.review_workbook(run_id=run_dir.name, state="all", write=False)
    workbook_rows = list(csv.DictReader(StringIO(workbook["csv"])))
    workbook_row = next(row for row in workbook_rows if row["job_id"] == closeout["job_id"])
    assert workbook_row["child_replacement_state"] == "ready_for_operator_closeout"
    assert workbook_row["child_replacement_copy_ready"] == "True"
    dashboard = service.operator_dashboard(run_id=run_dir.name)
    assert dashboard["child_replacement_summary"]["closeout_count"] == 1
    assert dashboard["child_replacement_summary"]["ready_count"] == 1
    assert dashboard["child_replacement_summary"]["state_counts"]["ready_for_operator_closeout"]["count"] == 1
    assert any(artifact["kind"] == "child_selected_target_response_validation" for artifact in artifacts)
    assert any(artifact["kind"] == "child_selected_target_execution_checklist" for artifact in artifacts)
    assert any(artifact["kind"] == "child_selected_target_command_copy_packet" for artifact in artifacts)
    assert any(artifact["kind"] == "child_selected_target_audit" for artifact in artifacts)
    assert any(artifact["kind"] == "child_selected_target_abandonment" for artifact in artifacts)
    assert any(artifact["kind"] == "child_selected_target_replacement_reset" for artifact in artifacts)
    assert any(artifact["kind"] == "child_selected_target_staleness" for artifact in artifacts)
    assert any(artifact["kind"] == "child_replacement_handoff_refresh" for artifact in artifacts)
    assert any(artifact["kind"] == "child_replacement_response_validation" for artifact in artifacts)
    assert any(artifact["kind"] == "child_replacement_execution_checklist" for artifact in artifacts)
    assert any(artifact["kind"] == "child_replacement_command_copy_packet" for artifact in artifacts)
    assert any(artifact["kind"] == "child_replacement_closeout_status" for artifact in artifacts)
    assert any(event["event_type"] == "child_selected_target_response_validated" for event in events)
    assert any(event["event_type"] == "child_selected_target_execution_checklist_created" for event in events)
    assert any(event["event_type"] == "child_selected_target_command_copy_packet_created" for event in events)
    assert any(event["event_type"] == "child_selected_target_audit_created" for event in events)
    assert any(event["event_type"] == "child_selected_target_abandoned" for event in events)
    assert any(event["event_type"] == "child_selected_target_replacement_reset_created" for event in events)
    assert any(event["event_type"] == "child_replacement_handoff_refreshed" for event in events)
    assert any(event["event_type"] == "child_replacement_response_validated" for event in events)
    assert any(event["event_type"] == "child_replacement_execution_checklist_created" for event in events)
    assert any(event["event_type"] == "child_replacement_command_copy_packet_created" for event in events)
    assert any(event["event_type"] == "child_replacement_closeout_status_created" for event in events)

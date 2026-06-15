from __future__ import annotations

import json
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

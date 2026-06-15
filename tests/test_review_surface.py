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

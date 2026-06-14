from __future__ import annotations

import json
from pathlib import Path

from business_card_watchdog.config import AppConfig, PrefilterConfig, SinkConfig
from business_card_watchdog.dedupe import (
    IdentityIndex,
    assess_downstream_lookup_result,
    assess_duplicate,
    remember_duplicate_resolution,
    remember_identity,
)
from business_card_watchdog.orchestrator import BatchOrchestrator

from synthetic_fixtures import SyntheticSkillAdapter, latest_jobs_by_id, read_jsonl, write_synthetic_image


def test_identity_index_detects_strong_email_duplicate(tmp_path: Path) -> None:
    config = AppConfig(config_path=tmp_path / "config.toml", data_dir=tmp_path / "data")
    spec = {"full_name": "Ada Lovelace", "email": "ada@example.test"}
    remember_identity(config, spec=spec, job_id="job-1", run_id="run-1", image_path="/tmp/one.png")

    assessment = assess_duplicate(
        config,
        spec={"full_name": "A. Lovelace", "email": "ADA@example.test"},
        job_id="job-2",
        run_id="run-2",
        image_path="/tmp/two.png",
    )

    assert assessment.state == "strong_duplicate"
    assert assessment.blocks_routing is True
    assert assessment.matches[0]["basis"] == "email"


def test_create_new_duplicate_resolution_suppresses_future_false_positive(tmp_path: Path) -> None:
    config = AppConfig(config_path=tmp_path / "config.toml", data_dir=tmp_path / "data")
    prior = {"full_name": "Ada Lovelace", "organization": "Analytical Engines"}
    current = {"full_name": "Ada Lovelace", "organization": "Analytical Engines", "title": "Founder"}
    remember_identity(config, spec=prior, job_id="job-1", run_id="run-1", image_path="/tmp/one.png")
    assessment = assess_duplicate(
        config,
        spec=current,
        job_id="job-2",
        run_id="run-2",
        image_path="/tmp/two.png",
    )

    record = remember_duplicate_resolution(
        config,
        spec=current,
        resolution={
            "decision": "create_new",
            "reviewer": "operator",
            "reason": "same company and name, different person confirmed",
            "duplicate_assessment": assessment.to_dict(),
        },
        job_id="job-2",
        run_id="run-2",
        image_path="/tmp/two.png",
    )
    repeated = assess_duplicate(
        config,
        spec=current,
        job_id="job-3",
        run_id="run-3",
        image_path="/tmp/three.png",
    )

    assert assessment.state == "possible_duplicate"
    assert record.schema == "business-card-watchdog.duplicate-resolution-index.v1"
    assert IdentityIndex(config).duplicate_resolutions()[0].decision == "create_new"
    assert repeated.state == "no_match"


def test_downstream_lookup_result_detects_strong_sink_duplicate() -> None:
    assessment = assess_downstream_lookup_result(
        {
            "schema": "business-card-watchdog.sink-lookup-result.v1",
            "results": [
                {
                    "sink": "google_contacts",
                    "matches": [
                        {
                            "resource_id": "people/c123",
                            "confidence": 0.92,
                            "basis": ["email"],
                            "display": "Ada Lovelace",
                        }
                    ],
                }
            ],
        }
    )

    assert assessment.state == "strong_duplicate"
    assert assessment.blocks_routing is True
    assert assessment.matches[0]["basis"] == "downstream_email"
    assert assessment.matches[0]["resource_id"] == "people/c123"


def test_duplicate_card_is_moved_to_review_before_routing(tmp_path: Path, monkeypatch) -> None:
    source_dir = tmp_path / "synthetic-cards"
    write_synthetic_image(source_dir / "first.png")
    write_synthetic_image(source_dir / "second.png")
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        cache_dir=tmp_path / "cache",
        prefilter=PrefilterConfig(process_uncertain=True),
        sink=SinkConfig(google_contacts=True, odoo=True, dry_run=True),
        routing_rules=[{"match": "email_domain", "value": "example.test", "sinks": ["google_contacts"]}],
    )
    orchestrator = BatchOrchestrator(config)
    monkeypatch.setattr(
        orchestrator,
        "adapter",
        SyntheticSkillAdapter(
            specs_by_stem={
                "first": {"full_name": "Duplicate Person", "email": "dupe@example.test"},
                "second": {"full_name": "Duplicate Person", "email": "dupe@example.test"},
            }
        ),
    )

    run_dir = orchestrator.process_source(str(source_dir), dry_run=True, workers=1)
    final_jobs = latest_jobs_by_id(run_dir / "jobs.jsonl")
    states = {Path(job["image_path"]).name: job["state"] for job in final_jobs.values()}
    duplicate_job = next(job for job in final_jobs.values() if Path(job["image_path"]).name == "second.png")
    duplicate_artifact = Path(duplicate_job["artifact_dir"]) / "duplicate_assessment.json"
    duplicate = json.loads(duplicate_artifact.read_text(encoding="utf-8"))
    events = read_jsonl(run_dir / "events.jsonl")

    assert states["first.png"] == "ready_to_route"
    assert states["second.png"] == "needs_review"
    assert duplicate["state"] == "strong_duplicate"
    assert any(event["event_type"] == "job_duplicate_needs_review" for event in events)

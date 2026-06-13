from __future__ import annotations

import json
from pathlib import Path

from business_card_watchdog.config import AppConfig, PrefilterConfig, SinkConfig
from business_card_watchdog.orchestrator import BatchOrchestrator

from synthetic_fixtures import (
    SyntheticSkillAdapter,
    latest_jobs_by_id,
    normalize_events,
    read_jsonl,
    write_synthetic_image,
)


def test_batch_dry_run_uses_synthetic_adapter_without_credentials(
    tmp_path: Path, monkeypatch
) -> None:
    source_dir = tmp_path / "synthetic-cards"
    write_synthetic_image(source_dir / "alpha.png")
    write_synthetic_image(source_dir / "nested" / "beta.jpg")

    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        cache_dir=tmp_path / "cache",
        prefilter=PrefilterConfig(process_uncertain=True),
        sink=SinkConfig(google_contacts=True, odoo=True, dry_run=True),
        routing_rules=[
            {"match": "email_domain", "value": "example.test", "sinks": ["google_contacts", "odoo"]}
        ],
    )
    adapter = SyntheticSkillAdapter(
        specs_by_stem={
            "alpha": {"email": "alpha@example.test", "full_name": "Alpha Fixture"},
            "beta": {"email": "beta@example.test", "full_name": "Beta Fixture"},
        }
    )
    orchestrator = BatchOrchestrator(config)
    monkeypatch.setattr(orchestrator, "adapter", adapter)

    run_dir = orchestrator.process_source(str(source_dir), dry_run=True, workers=1)

    assert run_dir.parent == config.runs_dir
    assert adapter.apply_google_calls == [False, False]
    assert json.loads((run_dir / "run.json").read_text(encoding="utf-8"))["dry_run"] is True

    final_jobs = latest_jobs_by_id(run_dir / "jobs.jsonl")
    assert {Path(job["image_path"]).name for job in final_jobs.values()} == {"alpha.png", "beta.jpg"}
    assert {job["state"] for job in final_jobs.values()} == {"ready_to_route"}

    for job in final_jobs.values():
        artifact_dir = Path(job["artifact_dir"])
        assert artifact_dir.parent == run_dir / "artifacts"
        assert (artifact_dir / "spec.json").exists()
        assert (artifact_dir / "review.md").exists()
        assert (artifact_dir / "crop_manifest.json").exists()
        assert (artifact_dir / "ocr.txt").exists()
        assert (artifact_dir / "sink_payloads.json").exists()
        spec = json.loads((artifact_dir / "spec.json").read_text(encoding="utf-8"))
        assert spec["email"].endswith("@example.test")
        assert spec["notes"].startswith("Synthetic privacy-safe")
        sink_payloads = json.loads((artifact_dir / "sink_payloads.json").read_text(encoding="utf-8"))
        assert sink_payloads["schema"] == "business-card-watchdog.sink-payloads.v1"
        assert [payload["sink"] for payload in sink_payloads["payloads"]] == [
            "google_contacts",
            "odoo",
        ]

    dry_run_events = [
        event for event in read_jsonl(run_dir / "events.jsonl") if event["event_type"] == "sink_decision_dry_run"
    ]
    assert len(dry_run_events) == 2
    assert all(event["payload"]["decision"]["dry_run"] is True for event in dry_run_events)
    assert all(
        event["payload"]["decision"]["sinks"] == ["google_contacts", "odoo"]
        for event in dry_run_events
    )
    assert all(event["payload"]["decision"]["fingerprint"] for event in dry_run_events)
    assert all(len(event["payload"]["payloads"]) == 2 for event in dry_run_events)

    artifact_records = read_jsonl(run_dir / "artifacts.jsonl")
    assert [record["kind"] for record in artifact_records] == [
        "preclassification",
        "artifact_dir",
        "contact_spec",
        "review_report",
        "ocr_text",
        "crop_manifest",
        "sink_payloads",
        "preclassification",
        "artifact_dir",
        "contact_spec",
        "review_report",
        "ocr_text",
        "crop_manifest",
        "sink_payloads",
    ]

    normalized_events = normalize_events(read_jsonl(run_dir / "events.jsonl"))
    event_types = [event["event_type"] for event in normalized_events]
    assert event_types[0] == "run_initialized"
    assert event_types.count("sink_decision_dry_run") == 2
    assert "run_completed" in event_types
    assert normalized_events[event_types.index("run_completed")]["payload"] == {"job_count": 2}


def test_incomplete_synthetic_spec_creates_review_packet(tmp_path: Path, monkeypatch) -> None:
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

    final_job = next(iter(latest_jobs_by_id(run_dir / "jobs.jsonl").values()))
    artifact_dir = Path(final_job["artifact_dir"])
    review_packet = json.loads((artifact_dir / "review_packet.json").read_text(encoding="utf-8"))
    events = read_jsonl(run_dir / "events.jsonl")

    assert final_job["state"] == "needs_review"
    assert review_packet["assessment"]["status"] == "needs_review"
    assert any(event["event_type"] == "job_needs_review" for event in events)

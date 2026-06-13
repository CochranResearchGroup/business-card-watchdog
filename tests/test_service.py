from __future__ import annotations

import json
from pathlib import Path

from business_card_watchdog.config import AppConfig
from business_card_watchdog.ledger import RunLedger
from business_card_watchdog.models import CardJob
from business_card_watchdog.service import BusinessCardService


def make_recorded_run(config: AppConfig, run_id: str = "run-001") -> tuple[str, str]:
    ledger = RunLedger(config.runs_dir / run_id)
    ledger.initialize(source="/tmp/cards", dry_run=True)
    ledger.transition_run("discovering")
    ledger.transition_run("processing")
    job = CardJob(image_path="/tmp/cards/card.png", job_id="job-001")
    ledger.set_job_count(1)
    ledger.record_job(job)
    job.transition_to("processing")
    ledger.record_job(job)
    artifact_path = ledger.run_dir / "artifacts" / job.job_id / "spec.json"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text('{"full_name": "Synthetic Fixture"}\n', encoding="utf-8")
    ledger.record_artifact(job_id=job.job_id, kind="contact_spec", path=artifact_path)
    job.artifact_dir = str(artifact_path.parent)
    job.transition_to("needs_review")
    ledger.record_job(job)
    ledger.transition_run("waiting_for_review")
    return run_id, job.job_id


def test_service_lists_and_shows_runs_jobs_and_artifacts(tmp_path: Path) -> None:
    config = AppConfig(config_path=tmp_path / "config.toml", data_dir=tmp_path / "data")
    run_id, job_id = make_recorded_run(config)
    service = BusinessCardService(config)

    runs = service.list_runs()
    run = service.get_run(run_id)
    jobs = service.list_jobs(run_id)
    job = service.get_job(job_id, run_id=run_id)

    assert runs[0]["run_id"] == run_id
    assert run["job_count"] == 1
    assert jobs[0]["job_id"] == job_id
    assert job["artifacts"][0]["kind"] == "contact_spec"


def test_service_status_and_sink_readiness_are_structured(tmp_path: Path) -> None:
    config = AppConfig(config_path=tmp_path / "config.toml", data_dir=tmp_path / "data")
    service = BusinessCardService(config)

    status = service.status()
    readiness = service.sink_readiness()

    assert status["skill_ready"] is True
    assert "watch" in status
    assert readiness["dry_run"] is True
    assert {sink["sink"] for sink in readiness["sinks"]} == {"google_contacts", "odoo"}


def test_service_watch_reset_returns_runtime_path(tmp_path: Path) -> None:
    config = AppConfig(config_path=tmp_path / "config.toml", data_dir=tmp_path / "data")
    service = BusinessCardService(config)
    config.watch_dir.mkdir(parents=True)
    (config.watch_dir / "seen-files.jsonl").write_text('{"key": "x"}\n', encoding="utf-8")

    payload = service.watch_reset()

    assert payload["reset"] is True
    assert not (config.watch_dir / "seen-files.jsonl").exists()


def test_service_doctor_checks_user_scope_paths(tmp_path: Path) -> None:
    config = AppConfig(config_path=tmp_path / "config.toml", data_dir=tmp_path / "data")
    payload = BusinessCardService(config).doctor()

    assert payload["ok"] is True
    assert {check["name"] for check in payload["checks"]} >= {
        "config_parent",
        "data_dir",
        "cache_dir",
        "runs_dir",
        "watch_dir",
        "business_card_skill",
        "watch_inputs",
    }


def test_service_submit_review_records_artifact_and_advances_job(tmp_path: Path) -> None:
    config = AppConfig(config_path=tmp_path / "config.toml", data_dir=tmp_path / "data")
    run_id, job_id = make_recorded_run(config)
    service = BusinessCardService(config)

    result = service.submit_review(
        job_id=job_id,
        run_id=run_id,
        reviewer="tester",
        action="approve_for_routing",
        field_corrections={"full_name": "Reviewed Fixture"},
        crop_selection={"crop_id": "c01", "reason": "face-centered"},
        notes="synthetic review",
    )
    job = service.get_job(job_id, run_id=run_id)
    events = [
        json.loads(line)
        for line in (config.runs_dir / run_id / "events.jsonl").read_text(encoding="utf-8").splitlines()
    ]

    assert result["submission"]["field_corrections"]["full_name"] == "Reviewed Fixture"
    assert job["state"] == "ready_to_route"
    assert any(artifact["kind"] == "review_submission" for artifact in job["artifacts"])
    assert any(event["event_type"] == "review_submitted" for event in events)


def test_service_submit_review_rejects_unknown_fields(tmp_path: Path) -> None:
    config = AppConfig(config_path=tmp_path / "config.toml", data_dir=tmp_path / "data")
    run_id, job_id = make_recorded_run(config)
    service = BusinessCardService(config)

    try:
        service.submit_review(
            job_id=job_id,
            run_id=run_id,
            reviewer="tester",
            action="keep_needs_review",
            field_corrections={"linkedin": "invented"},
        )
    except ValueError as exc:
        assert "unsupported field corrections" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_service_get_missing_run_raises(tmp_path: Path) -> None:
    config = AppConfig(config_path=tmp_path / "config.toml", data_dir=tmp_path / "data")
    service = BusinessCardService(config)

    try:
        service.get_run("missing")
    except FileNotFoundError as exc:
        assert "run not found" in str(exc)
    else:
        raise AssertionError("expected FileNotFoundError")

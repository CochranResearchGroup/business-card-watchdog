import json
from pathlib import Path

import pytest

from business_card_watchdog.config import AppConfig
from business_card_watchdog.ledger import RunLedger
from business_card_watchdog.models import CardJob, InvalidStateTransition
from business_card_watchdog.orchestrator import BatchOrchestrator


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_job_transition_rejects_invalid_skip() -> None:
    job = CardJob(image_path="/tmp/card.jpg")

    with pytest.raises(InvalidStateTransition):
        job.transition_to("routed")


def test_job_transition_allows_retry_from_failed() -> None:
    job = CardJob(image_path="/tmp/card.jpg")
    job.transition_to("processing")
    job.transition_to("failed", error="ocr failed")
    job.transition_to("queued")

    assert job.state == "queued"
    assert job.error is None


def test_ledger_writes_run_index_and_artifacts(tmp_path: Path) -> None:
    run_dir = tmp_path / "runs" / "run-001"
    ledger = RunLedger(run_dir)
    ledger.initialize(source="/tmp/cards", dry_run=True)
    ledger.transition_run("discovering")
    ledger.set_job_count(1)
    ledger.record_artifact(job_id="job-001", kind="contact_spec", path=run_dir / "spec.json")

    run_payload = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    index_rows = read_jsonl(tmp_path / "runs" / "index.jsonl")
    artifacts = read_jsonl(run_dir / "artifacts.jsonl")

    assert run_payload["state"] == "discovering"
    assert run_payload["job_count"] == 1
    assert index_rows[-1]["run_id"] == "run-001"
    assert artifacts[0]["kind"] == "contact_spec"


def test_no_supported_images_completes_run(tmp_path: Path) -> None:
    source = tmp_path / "empty"
    source.mkdir()
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        cache_dir=tmp_path / "cache",
    )

    run_dir = BatchOrchestrator(config).process_source(str(source), dry_run=True)
    run_payload = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    events = read_jsonl(run_dir / "events.jsonl")

    assert run_payload["state"] == "completed"
    assert run_payload["job_count"] == 0
    assert any(event["event_type"] == "no_supported_images" for event in events)


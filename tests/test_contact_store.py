import json
from pathlib import Path

from business_card_watchdog.cli import main
from business_card_watchdog.config import AppConfig
from business_card_watchdog.contact import build_contact_candidate
from business_card_watchdog.contact_store import ContactStore
from business_card_watchdog.ledger import RunLedger
from business_card_watchdog.models import CardJob
from business_card_watchdog.service import BusinessCardService


def _write_recorded_contact_run(config: AppConfig) -> tuple[str, str]:
    run_id = "run-contact-store"
    job = CardJob(image_path=str(config.data_dir / "fixtures" / "ada-card.jpg"), job_id="job-ada")
    run_dir = config.runs_dir / run_id
    artifact_dir = run_dir / "artifacts" / job.job_id
    artifact_dir.mkdir(parents=True, exist_ok=True)
    candidate_path = artifact_dir / "contact_candidate.json"
    spec_path = artifact_dir / "spec.json"
    sink_payload_path = artifact_dir / "sink_payloads.json"
    enrichment_path = artifact_dir / "enrichment_request.json"
    candidate = build_contact_candidate(
        {
            "full_name": "Ada Lovelace",
            "organization": "Example Labs",
            "email": "ADA@Example.TEST",
            "phone": "(555) 010-1234",
        }
    )
    candidate_path.write_text(json.dumps(candidate, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    spec_path.write_text(
        json.dumps(
            {
                "full_name": "Ada Lovelace",
                "organization": "Example Labs",
                "email": "ada@example.test",
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    sink_payload_path.write_text(
        json.dumps(
            {
                "schema": "business-card-watchdog.sink-payloads.v1",
                "payloads": [{"sink": "google_contacts", "dry_run": True, "contact": {"email": "ada@example.test"}}],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    enrichment_path.write_text(
        json.dumps(
            {
                "schema": "business-card-watchdog.enrichment-request.v1",
                "provider": "public_web",
                "state": "requested",
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    ledger = RunLedger(run_dir)
    ledger.initialize(source="synthetic", dry_run=True)
    job.artifact_dir = str(artifact_dir)
    job.transition_to("processing")
    job.transition_to("needs_review")
    ledger.record_job(job)
    ledger.record_artifact(job_id=job.job_id, kind="contact_candidate", path=candidate_path)
    ledger.record_artifact(job_id=job.job_id, kind="contact_spec", path=spec_path)
    ledger.record_artifact(job_id=job.job_id, kind="sink_payloads", path=sink_payload_path)
    ledger.record_artifact(job_id=job.job_id, kind="enrichment_request", path=enrichment_path)
    ledger.transition_run("discovering")
    ledger.transition_run("processing")
    ledger.transition_run("waiting_for_review")
    ledger.set_job_count(1)
    return run_id, job.job_id


def test_contact_store_initializes_schema(tmp_path: Path) -> None:
    config = AppConfig(config_path=tmp_path / "config.toml", data_dir=tmp_path / "data")
    store = ContactStore.from_config(config)

    status = store.initialize()

    assert status["exists"] is True
    assert status["schema_version"] == 1
    assert config.contact_store_path.exists()


def test_contact_store_projects_run_idempotently(tmp_path: Path) -> None:
    config = AppConfig(config_path=tmp_path / "config.toml", data_dir=tmp_path / "data")
    run_id, job_id = _write_recorded_contact_run(config)
    service = BusinessCardService(config)

    first = service.project_contacts_from_run(run_id)
    second = service.project_contacts_from_run(run_id)
    contacts = service.list_contacts()["contacts"]
    detail = service.get_contact(str(contacts[0]["contact_id"]))["contact"]

    assert first["projected_contacts"] == 1
    assert first["projected_enrichment_attempts"] == 1
    assert first["projected_routing_decisions"] == 1
    assert first["projected_sink_attempts"] == 1
    assert first["drift"]["state"] == "in_sync"
    assert second["projected_contacts"] == 1
    assert len(contacts) == 1
    assert contacts[0]["display_name"] == "Ada Lovelace"
    assert contacts[0]["email"] == "ada@example.test"
    assert detail["source_run_id"] == run_id
    assert detail["source_job_id"] == job_id
    assert detail["payload"]["contact_spec"]["organization"] == "Example Labs"
    assert len(detail["assets"]) >= 2
    assert len(detail["extraction_attempts"]) == 1
    assert detail["enrichment_attempts"][0]["provider"] == "public_web"
    assert detail["routing_decisions"][0]["state"] == "ready_to_route"
    assert detail["sink_attempts"][0]["sink"] == "google_contacts"


def test_contacts_cli_json_surfaces(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "config.toml"
    data_dir = tmp_path / "data"
    config_path.write_text(f'data_dir = "{data_dir}"\n[watch]\ninputs = []\n', encoding="utf-8")
    config = AppConfig(config_path=config_path, data_dir=data_dir)
    run_id, _job_id = _write_recorded_contact_run(config)

    assert main(["--config", str(config_path), "contacts", "init", "--json"]) == 0
    init_payload = json.loads(capsys.readouterr().out)
    assert init_payload["schema_version"] == 1

    assert main(["--config", str(config_path), "contacts", "project-run", run_id, "--json"]) == 0
    projection = json.loads(capsys.readouterr().out)
    assert projection["projected_contacts"] == 1

    assert main(["--config", str(config_path), "contacts", "list", "--json"]) == 0
    listing = json.loads(capsys.readouterr().out)
    contact_id = listing["contacts"][0]["contact_id"]

    assert main(["--config", str(config_path), "contacts", "show", contact_id, "--json"]) == 0
    detail = json.loads(capsys.readouterr().out)
    assert detail["contact"]["display_name"] == "Ada Lovelace"

    assert main(["--config", str(config_path), "contacts", "drift", run_id, "--json"]) == 0
    drift = json.loads(capsys.readouterr().out)
    assert drift["drift"]["state"] == "in_sync"

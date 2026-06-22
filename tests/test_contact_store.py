import json
import sqlite3
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
                "payloads": [
                    {
                        "sink": "google_contacts",
                        "dry_run": True,
                        "contact": {"email": "ada@example.test"},
                        "readiness": {
                            "status": "ready",
                            "details": {
                                "profile": "ecochran76",
                                "target_account": "ecochran76",
                                "config_key": "sink.google_contacts_profile",
                                "live_apply_requires_selected_target": True,
                            },
                        },
                    }
                ],
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
    assert status["schema_version"] == 3
    assert config.contact_store_path.exists()


def test_contact_store_migrates_selected_sink_columns_without_losing_routes(tmp_path: Path) -> None:
    db_path = tmp_path / "contacts.sqlite"
    now = "2026-06-22T00:00:00Z"
    route_payload = {
        "sinks": ["google_contacts"],
        "sink_payloads": {
            "payloads": [
                {
                    "sink": "google_contacts",
                    "dry_run": True,
                    "readiness": {
                        "details": {
                            "profile": "ecochran76",
                            "target_account": "ecochran76",
                        }
                    },
                }
            ]
        },
    }
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL
            );
            CREATE TABLE contacts (
                contact_id TEXT PRIMARY KEY,
                source_run_id TEXT NOT NULL,
                source_job_id TEXT NOT NULL,
                state TEXT NOT NULL,
                display_name TEXT NOT NULL DEFAULT '',
                organization TEXT NOT NULL DEFAULT '',
                email TEXT NOT NULL DEFAULT '',
                phone TEXT NOT NULL DEFAULT '',
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE routing_decisions (
                decision_id TEXT PRIMARY KEY,
                contact_id TEXT,
                tenant TEXT NOT NULL,
                state TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )
        conn.execute("INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)", (2, now))
        conn.execute(
            """
            INSERT INTO contacts (
                contact_id, source_run_id, source_job_id, state, display_name,
                payload_json, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("contact_legacy", "run-legacy", "job-legacy", "projected", "Legacy Contact", "{}", now, now),
        )
        conn.execute(
            """
            INSERT INTO routing_decisions (
                decision_id, contact_id, tenant, state, payload_json, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "route_legacy",
                "contact_legacy",
                "google_contacts",
                "ready_to_route",
                json.dumps(route_payload),
                now,
                now,
            ),
        )

    store = ContactStore(db_path)
    status = store.initialize()
    detail = store.get_contact("contact_legacy")

    assert status["schema_version"] == 3
    assert detail["routing_decisions"][0]["decision_id"] == "route_legacy"
    assert detail["routing_decisions"][0]["selected_sinks"] == ["google_contacts"]
    assert detail["routing_decisions"][0]["selected_sink_state"] == "dry_run"
    assert detail["routing_decisions"][0]["selected_target_profile"] == "ecochran76"


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
    assert detail["routing_decisions"][0]["selected_sinks"] == ["google_contacts"]
    assert detail["routing_decisions"][0]["selected_sink_state"] == "dry_run"
    assert detail["routing_decisions"][0]["selected_target_profile"] == "ecochran76"
    assert detail["routing_decisions"][0]["selected_target_tenant"] == ""
    assert detail["sink_attempts"][0]["sink"] == "google_contacts"
    assert detail["review_states"] == []


def test_contact_store_projects_enrichment_review_provenance(tmp_path: Path) -> None:
    config = AppConfig(config_path=tmp_path / "config.toml", data_dir=tmp_path / "data")
    run_id, job_id = _write_recorded_contact_run(config)
    service = BusinessCardService(config)
    artifact_dir = config.runs_dir / run_id / "artifacts" / job_id
    enrichment_result_path = artifact_dir / "enrichment_result.json"
    enrichment_result_path.write_text(
        json.dumps(
            {
                "schema": "business-card-watchdog.enrichment-result.v1",
                "provider": "public_web",
                "merge_proposals": [
                    {
                        "field": "notes",
                        "value": "Public-web corroboration candidate: https://example.test/ada",
                        "source": "public_web",
                        "requires_review": True,
                    },
                    {
                        "field": "title",
                        "value": "Principal Engineer",
                        "source": "public_web",
                        "requires_review": True,
                    },
                ],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    RunLedger(config.runs_dir / run_id).record_artifact(
        job_id=job_id,
        kind="enrichment_result",
        path=enrichment_result_path,
    )

    service.submit_review(
        job_id=job_id,
        run_id=run_id,
        reviewer="operator",
        action="approve_enrichment_merge",
        approved_enrichment_fields=["notes"],
    )
    projection = service.project_contacts_from_run(run_id)
    second_projection = service.project_contacts_from_run(run_id)
    contact_id = service.list_contacts()["contacts"][0]["contact_id"]
    detail = service.get_contact(str(contact_id))["contact"]
    attempts_by_schema = {
        attempt["payload"]["payload"].get("schema"): attempt
        for attempt in detail["enrichment_attempts"]
        if isinstance(attempt["payload"].get("payload"), dict)
    }
    proposal_review = attempts_by_schema["business-card-watchdog.enrichment-proposal-review.v1"]
    merge_review = attempts_by_schema["business-card-watchdog.enrichment-merge-review.v1"]

    assert projection["projected_contacts"] == 1
    assert projection["projected_enrichment_attempts"] == 4
    assert second_projection["projected_enrichment_attempts"] == 4
    assert len(detail["enrichment_attempts"]) == 4
    assert proposal_review["provider"] == "public_web"
    assert proposal_review["state"] == "reviewed"
    assert proposal_review["payload"]["review"]["reviewer"] == "operator"
    assert proposal_review["payload"]["review"]["source_provider"] == "public_web"
    assert proposal_review["payload"]["review"]["accepted_count"] == 1
    assert proposal_review["payload"]["review"]["rejected_count"] == 1
    assert proposal_review["payload"]["review"]["proposals"][0]["decision"] == "accepted"
    assert proposal_review["payload"]["review"]["proposals"][1]["decision"] == "rejected"
    assert merge_review["state"] == "reviewed"
    assert merge_review["payload"]["review"]["applied_count"] == 1
    assert merge_review["payload"]["review"]["skipped_count"] == 1


def test_contact_review_recommendations_are_host_decided(tmp_path: Path) -> None:
    config = AppConfig(config_path=tmp_path / "config.toml", data_dir=tmp_path / "data")
    run_id, _job_id = _write_recorded_contact_run(config)
    service = BusinessCardService(config)
    service.project_contacts_from_run(run_id)
    contact_id = service.list_contacts()["contacts"][0]["contact_id"]

    proposed = service.record_contact_review_recommendation(
        contact_id=contact_id,
        source="app_intelligence",
        category="route_readiness",
        recommendation="request_enrichment_before_routing",
        rationale="missing independent organization confirmation",
        confidence=0.82,
        evidence={"signals": ["organization_only"]},
    )
    review_state_id = proposed["review_state"]["review_state_id"]
    listing = service.list_contact_review_states(contact_id=contact_id, state="proposed")
    decided = service.decide_contact_review_state(
        review_state_id=review_state_id,
        reviewer="operator",
        decision="reject",
        notes="card is sufficient for dry-run routing",
    )
    detail = service.get_contact(str(contact_id))["contact"]

    assert proposed["writes_attempted"] == 0
    assert proposed["network_calls_made"] == 0
    assert proposed["review_state"]["state"] == "proposed"
    assert proposed["review_state"]["payload"]["evidence"]["signals"] == ["organization_only"]
    assert listing["count"] == 1
    assert decided["review_state"]["state"] == "rejected"
    assert decided["review_state"]["decided_by"] == "operator"
    assert decided["review_state"]["payload"]["decision"]["decision"] == "reject"
    assert detail["review_states"][0]["review_state_id"] == review_state_id
    assert detail["review_states"][0]["state"] == "rejected"


def test_contact_review_safe_loop_only_rejects_explicit_safe_rejections(tmp_path: Path) -> None:
    config = AppConfig(config_path=tmp_path / "config.toml", data_dir=tmp_path / "data")
    run_id, _job_id = _write_recorded_contact_run(config)
    service = BusinessCardService(config)
    service.project_contacts_from_run(run_id)
    contact_id = service.list_contacts()["contacts"][0]["contact_id"]
    safe = service.record_contact_review_recommendation(
        contact_id=contact_id,
        source="app_intelligence",
        category="route_readiness",
        recommendation="ignore_low_value_hint",
        rationale="recommendation duplicates existing route state",
        confidence=0.91,
        evidence={"safe_to_auto_continue": True, "safe_auto_decision": "reject"},
    )["review_state"]
    unsafe = service.record_contact_review_recommendation(
        contact_id=contact_id,
        source="app_intelligence",
        category="enrichment_need",
        recommendation="request_public_web_enrichment",
        rationale="could improve organization confidence",
        confidence=0.64,
        evidence={"safe_to_auto_continue": True, "safe_auto_decision": "accept"},
    )["review_state"]

    preview = service.run_contact_review_safe_loop(limit=10, reviewer="tester", apply=False)
    after_preview = service.list_contact_review_states(state="proposed")
    applied = service.run_contact_review_safe_loop(limit=10, reviewer="tester", apply=True)
    final_states = service.list_contact_review_states(state="all")["review_states"]
    states_by_id = {row["review_state_id"]: row for row in final_states}

    assert preview["apply"] is False
    assert preview["action_count"] == 1
    assert preview["actions"][0]["review_state_id"] == safe["review_state_id"]
    assert preview["actions"][0]["status"] == "preview"
    assert preview["skipped"][0]["review_state_id"] == unsafe["review_state_id"]
    assert after_preview["count"] == 2
    assert applied["apply"] is True
    assert applied["action_count"] == 1
    assert applied["actions"][0]["status"] == "executed"
    assert states_by_id[safe["review_state_id"]]["state"] == "rejected"
    assert states_by_id[safe["review_state_id"]]["decided_by"] == "tester"
    assert states_by_id[unsafe["review_state_id"]]["state"] == "proposed"


def test_contacts_cli_json_surfaces(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "config.toml"
    data_dir = tmp_path / "data"
    config_path.write_text(f'data_dir = "{data_dir}"\n[watch]\ninputs = []\n', encoding="utf-8")
    config = AppConfig(config_path=config_path, data_dir=data_dir)
    run_id, _job_id = _write_recorded_contact_run(config)

    assert main(["--config", str(config_path), "contacts", "init", "--json"]) == 0
    init_payload = json.loads(capsys.readouterr().out)
    assert init_payload["schema_version"] == 3

    assert main(["--config", str(config_path), "contacts", "project-run", run_id, "--json"]) == 0
    projection = json.loads(capsys.readouterr().out)
    assert projection["projected_contacts"] == 1

    assert main(["--config", str(config_path), "contacts", "list", "--json"]) == 0
    listing = json.loads(capsys.readouterr().out)
    contact_id = listing["contacts"][0]["contact_id"]

    assert main(["--config", str(config_path), "contacts", "show", contact_id, "--json"]) == 0
    detail = json.loads(capsys.readouterr().out)
    assert detail["contact"]["display_name"] == "Ada Lovelace"

    assert (
        main(
            [
                "--config",
                str(config_path),
                "contacts",
                "review-recommend",
                contact_id,
                "--category",
                "extraction_quality",
                "--recommendation",
                "keep_needs_review",
                "--rationale",
                "OCR confidence needs operator confirmation",
                "--confidence",
                "0.7",
                "--evidence-json",
                '{"field":"email"}',
                "--json",
            ]
        )
        == 0
    )
    recommendation = json.loads(capsys.readouterr().out)
    review_state_id = recommendation["review_state"]["review_state_id"]
    assert recommendation["review_state"]["state"] == "proposed"
    assert recommendation["review_state"]["payload"]["evidence"]["field"] == "email"

    assert (
        main(
            [
                "--config",
                str(config_path),
                "contacts",
                "review-states",
                "--contact-id",
                contact_id,
                "--state",
                "proposed",
                "--json",
            ]
        )
        == 0
    )
    review_states = json.loads(capsys.readouterr().out)
    assert review_states["count"] == 1

    assert (
        main(
            [
                "--config",
                str(config_path),
                "contacts",
                "review-decide",
                review_state_id,
                "--reviewer",
                "operator",
                "--decision",
                "accept",
                "--notes",
                "confirmed",
                "--json",
            ]
        )
        == 0
    )
    decision = json.loads(capsys.readouterr().out)
    assert decision["review_state"]["state"] == "accepted"
    assert decision["review_state"]["payload"]["decision"]["notes"] == "confirmed"

    assert (
        main(
            [
                "--config",
                str(config_path),
                "contacts",
                "review-recommend",
                contact_id,
                "--category",
                "route_readiness",
                "--recommendation",
                "ignore_low_value_hint",
                "--evidence-json",
                '{"safe_to_auto_continue":true,"safe_auto_decision":"reject"}',
                "--json",
            ]
        )
        == 0
    )
    json.loads(capsys.readouterr().out)

    assert (
        main(
            [
                "--config",
                str(config_path),
                "contacts",
                "review-safe-loop",
                "--limit",
                "5",
                "--reviewer",
                "operator",
                "--apply",
                "--json",
            ]
        )
        == 0
    )
    safe_loop = json.loads(capsys.readouterr().out)
    assert safe_loop["action_count"] == 1
    assert safe_loop["actions"][0]["status"] == "executed"

    assert main(["--config", str(config_path), "contacts", "drift", run_id, "--json"]) == 0
    drift = json.loads(capsys.readouterr().out)
    assert drift["drift"]["state"] == "in_sync"

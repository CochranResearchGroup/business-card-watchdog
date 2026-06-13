from __future__ import annotations

import json
from pathlib import Path

from business_card_watchdog.config import AppConfig, EnrichmentConfig, EnrichmentProviderConfig, SinkConfig
from business_card_watchdog.contact import build_contact_candidate
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


def write_candidate_for_job(config: AppConfig, run_id: str, job_id: str) -> Path:
    artifact_dir = config.runs_dir / run_id / "artifacts" / job_id
    candidate = build_contact_candidate(
        {
            "full_name": "Ada Lovelace",
            "organization": "Example Labs",
            "email": "ada@example.test",
        }
    )
    (artifact_dir / "contact_candidate.json").write_text(json.dumps(candidate, indent=2), encoding="utf-8")
    return artifact_dir


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


def test_service_run_summary_and_review_queue(tmp_path: Path) -> None:
    config = AppConfig(config_path=tmp_path / "config.toml", data_dir=tmp_path / "data")
    run_id, job_id = make_recorded_run(config)
    service = BusinessCardService(config)

    summary = service.run_summary(run_id)
    queue = service.review_queue(run_id=run_id)
    bundle = service.review_bundle(run_id=run_id)
    bundle_path = config.runs_dir / run_id / "review_bundle.json"

    assert summary["run_id"] == run_id
    assert summary["needs_review_count"] == 1
    assert summary["artifact_counts"]["contact_spec"] == 1
    assert queue[0]["job_id"] == job_id
    assert queue[0]["artifact_kinds"] == ["contact_spec"]
    assert bundle["schema"] == "business-card-watchdog.review-bundle.v1"
    assert bundle["review_bundle_path"] == str(bundle_path)
    assert bundle["entries"][0]["job_id"] == job_id
    assert bundle["entries"][0]["next_action"]["action"] == "review_contact"
    assert bundle["entries"][0]["decision_template"]["action"] == "approve_for_routing"
    assert bundle["entries"][0]["commands"]["review"] == f"jobs review {job_id} --run-id {run_id}"
    assert bundle["groups"]["by_state"]["needs_review"]["job_ids"] == [job_id]
    assert bundle["groups"]["by_next_action"]["review_contact"]["count"] == 1
    assert bundle["decision_import_template"][0]["job_id"] == job_id
    assert bundle["commands"]["apply_decisions"] == f"reviews apply-decisions --run-id {run_id} --decisions-file <path>"
    assert bundle["writes_attempted"] == 0
    assert bundle["network_calls_made"] == 0
    assert bundle_path.exists()
    assert any(artifact["kind"] == "review_bundle" for artifact in service.list_artifacts(run_id))

    html = service.review_html(run_id=run_id)
    html_path = config.runs_dir / run_id / "review_bundle.html"
    assert html["schema"] == "business-card-watchdog.review-html.v1"
    assert html["html_path"] == str(html_path)
    assert "Business Card Review" in html["html"]
    assert job_id in html["html"]
    assert html_path.exists()
    assert any(artifact["kind"] == "review_html" for artifact in service.list_artifacts(run_id))


def test_service_run_summary_includes_enrichment_budget(tmp_path: Path) -> None:
    config = AppConfig(config_path=tmp_path / "config.toml", data_dir=tmp_path / "data")
    run_id, job_id = make_recorded_run(config)
    ledger = RunLedger(config.runs_dir / run_id)
    artifact_dir = config.runs_dir / run_id / "artifacts" / job_id
    artifacts = {
        "enrichment_public_web_request": {
            "max_queries": 3,
            "search_calls_attempted": 0,
            "network_calls_made": 0,
        },
        "enrichment_public_web_result": {
            "submitted_result_count": 2,
            "search_calls_attempted": 0,
            "network_calls_made": 0,
        },
        "enrichment_provider_request": {
            "max_results": 5,
            "paid_api_calls_attempted": 0,
            "network_calls_made": 0,
        },
        "enrichment_provider_result": {
            "submitted_result_count": 1,
            "paid_api_calls_attempted": 0,
            "network_calls_made": 0,
        },
    }
    for kind, payload in artifacts.items():
        path = artifact_dir / f"{kind}.json"
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        ledger.record_artifact(job_id=job_id, kind=kind, path=path)
    malformed_path = artifact_dir / "malformed_enrichment_provider_result.json"
    malformed_path.write_text("{not-json\n", encoding="utf-8")
    ledger.record_artifact(job_id=job_id, kind="enrichment_provider_result", path=malformed_path)

    summary = BusinessCardService(config).run_summary(run_id)

    assert summary["enrichment_budget"]["schema"] == "business-card-watchdog.enrichment-budget-summary.v1"
    assert summary["enrichment_budget"]["public_web"]["request_count"] == 1
    assert summary["enrichment_budget"]["public_web"]["result_count"] == 1
    assert summary["enrichment_budget"]["public_web"]["max_queries"] == 3
    assert summary["enrichment_budget"]["public_web"]["max_queries_per_run"] == 200
    assert summary["enrichment_budget"]["public_web"]["remaining_queries"] == 197
    assert summary["enrichment_budget"]["public_web"]["submitted_result_count"] == 2
    assert summary["enrichment_budget"]["paid_provider"]["request_count"] == 1
    assert summary["enrichment_budget"]["paid_provider"]["result_count"] == 1
    assert summary["enrichment_budget"]["paid_provider"]["max_results"] == 5
    assert summary["enrichment_budget"]["paid_provider"]["max_results_per_run"] == 50
    assert summary["enrichment_budget"]["paid_provider"]["remaining_results"] == 45
    assert summary["enrichment_budget"]["paid_provider"]["submitted_result_count"] == 1
    assert summary["enrichment_budget"]["paid_provider"]["paid_api_calls_attempted"] == 0
    assert summary["enrichment_budget"]["unreadable_artifact_count"] == 1


def test_service_public_web_enrichment_request_enforces_run_budget(tmp_path: Path) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        enrichment=EnrichmentConfig(
            enabled=True,
            max_public_web_queries_per_contact=3,
            max_public_web_queries_per_run=3,
        ),
    )
    run_id, job_id = make_recorded_run(config)
    artifact_dir = write_candidate_for_job(config, run_id, job_id)
    ledger = RunLedger(config.runs_dir / run_id)
    existing_request = artifact_dir / "existing_public_web_request.json"
    existing_request.write_text(
        json.dumps({"max_queries": 3, "search_calls_attempted": 0, "network_calls_made": 0}),
        encoding="utf-8",
    )
    ledger.record_artifact(job_id=job_id, kind="enrichment_public_web_request", path=existing_request)

    try:
        BusinessCardService(config).request_enrichment(
            job_id=job_id,
            run_id=run_id,
            mode="public_web",
            requested_by="tester",
        )
    except ValueError as exc:
        assert "public web enrichment request exceeds run budget" in str(exc)
    else:
        raise AssertionError("expected public-web enrichment request to exceed run budget")

    artifacts = BusinessCardService(config).list_artifacts(run_id)
    assert sum(1 for artifact in artifacts if artifact["kind"] == "enrichment_request") == 0


def test_service_paid_provider_enrichment_request_enforces_run_budget(tmp_path: Path) -> None:
    keys_path = tmp_path / "API-keys.env"
    keys_path.write_text("APOLLO_API_KEY=secret-value-not-printed\n", encoding="utf-8")
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        enrichment=EnrichmentConfig(
            enabled=True,
            allow_paid_api=True,
            api_keys_env=keys_path,
            max_paid_provider_results_per_contact=2,
            max_paid_provider_results_per_run=2,
            apollo=EnrichmentProviderConfig(enabled=True),
        ),
    )
    run_id, job_id = make_recorded_run(config)
    artifact_dir = write_candidate_for_job(config, run_id, job_id)
    ledger = RunLedger(config.runs_dir / run_id)
    existing_request = artifact_dir / "existing_provider_request.json"
    existing_request.write_text(
        json.dumps({"max_results": 2, "paid_api_calls_attempted": 0, "network_calls_made": 0}),
        encoding="utf-8",
    )
    ledger.record_artifact(job_id=job_id, kind="enrichment_provider_request", path=existing_request)

    try:
        BusinessCardService(config).request_enrichment(
            job_id=job_id,
            run_id=run_id,
            mode="api",
            requested_by="tester",
            allow_paid_enrichment=True,
        )
    except ValueError as exc:
        assert "paid provider enrichment request exceeds run budget" in str(exc)
    else:
        raise AssertionError("expected paid-provider enrichment request to exceed run budget")

    artifacts = BusinessCardService(config).list_artifacts(run_id)
    assert sum(1 for artifact in artifacts if artifact["kind"] == "enrichment_request") == 0


def test_service_next_actions_recommends_review_for_needs_review_job(tmp_path: Path) -> None:
    config = AppConfig(config_path=tmp_path / "config.toml", data_dir=tmp_path / "data")
    run_id, job_id = make_recorded_run(config)

    payload = BusinessCardService(config).next_actions(run_id=run_id)

    assert payload["action_count"] == 1
    assert payload["actions"][0]["job_id"] == job_id
    assert payload["actions"][0]["action"] == "review_contact"


def test_service_status_and_sink_readiness_are_structured(tmp_path: Path) -> None:
    config = AppConfig(config_path=tmp_path / "config.toml", data_dir=tmp_path / "data")
    service = BusinessCardService(config)

    status = service.status()
    readiness = service.sink_readiness()

    assert status["skill_ready"] is True
    assert "watch" in status
    assert readiness["dry_run"] is True
    assert {sink["sink"] for sink in readiness["sinks"]} == {"google_contacts", "odoo"}


def test_service_sink_readiness_reports_apply_policy(tmp_path: Path) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        sink=SinkConfig(
            google_contacts=True,
            odoo=True,
            dry_run=False,
            google_contacts_apply_enabled=False,
            odoo_apply_enabled=True,
        ),
    )

    readiness = BusinessCardService(config).sink_readiness()

    by_sink = {sink["sink"]: sink for sink in readiness["sinks"]}
    assert readiness["dry_run"] is False
    assert "disabled" in by_sink["google_contacts"]["reason"]
    assert by_sink["odoo"]["details"]["config_key"] == "sink.odollo_tenant"


def test_service_sink_readiness_reports_configured_profile_and_tenant(tmp_path: Path) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        sink=SinkConfig(
            google_contacts=True,
            google_contacts_profile="codex",
            odoo=True,
            odollo_tenant="saber",
            dry_run=False,
            google_contacts_apply_enabled=True,
            odoo_apply_enabled=True,
        ),
    )

    readiness = BusinessCardService(config).sink_readiness()

    by_sink = {sink["sink"]: sink for sink in readiness["sinks"]}
    assert by_sink["google_contacts"]["details"].get("profile") == "codex"
    assert by_sink["odoo"]["details"]["tenant"] == "saber"
    assert "Odollo" in by_sink["odoo"]["reason"]


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


def test_service_apply_review_decisions_records_run_import_artifact(tmp_path: Path) -> None:
    config = AppConfig(config_path=tmp_path / "config.toml", data_dir=tmp_path / "data")
    run_id, job_id = make_recorded_run(config)
    service = BusinessCardService(config)

    payload = service.apply_review_decisions(
        run_id=run_id,
        reviewer="batch-reviewer",
        decisions=[
            {
                "job_id": job_id,
                "action": "approve_for_routing",
                "field_corrections": {"full_name": "Batch Fixture", "email": "batch@example.test"},
                "notes": "batch import",
            }
        ],
    )
    job = service.get_job(job_id, run_id=run_id)
    artifacts = service.list_artifacts(run_id)
    events = [
        json.loads(line)
        for line in (config.runs_dir / run_id / "events.jsonl").read_text(encoding="utf-8").splitlines()
    ]

    assert payload["import"]["schema"] == "business-card-watchdog.review-decisions-import.v1"
    assert payload["import"]["applied_count"] == 1
    assert payload["results"][0]["action"] == "approve_for_routing"
    assert payload["results"][0]["job_state"] == "ready_to_route"
    assert job["state"] == "ready_to_route"
    assert any(artifact["kind"] == "review_decisions_import" for artifact in artifacts)
    assert any(event["event_type"] == "review_decisions_imported" for event in events)


def test_service_plan_sinks_for_job_writes_dry_run_plan(tmp_path: Path) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        sink=SinkConfig(google_contacts=True, odoo=True, dry_run=True),
        routing_rules=[{"match": "email_domain", "value": "example.test", "sinks": ["google_contacts", "odoo"]}],
    )
    run_id, job_id = make_recorded_run(config)
    artifact_dir = config.runs_dir / run_id / "artifacts" / job_id
    candidate = build_contact_candidate({"full_name": "Ada Lovelace", "email": "ADA@EXAMPLE.TEST"})
    (artifact_dir / "contact_candidate.json").write_text(json.dumps(candidate, indent=2), encoding="utf-8")

    result = BusinessCardService(config).plan_sinks_for_job(job_id=job_id, run_id=run_id)
    job = BusinessCardService(config).get_job(job_id, run_id=run_id)

    assert result["plan"]["schema"] == "business-card-watchdog.sink-plan.v1"
    assert result["plan"]["state"] == "dry_run"
    assert [action["sink"] for action in result["plan"]["actions"]] == ["google_contacts", "odoo"]
    assert result["plan"]["actions"][0]["match_keys"]["email"] == "ada@example.test"
    assert any(artifact["kind"] == "sink_plan" for artifact in job["artifacts"])


def test_service_plan_sink_lookup_for_job_writes_zero_network_plan(tmp_path: Path) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        sink=SinkConfig(google_contacts=True, odoo=True, dry_run=True),
        routing_rules=[{"match": "email_domain", "value": "*", "sinks": ["google_contacts", "odoo"]}],
    )
    run_id, job_id = make_recorded_run(config)
    artifact_dir = config.runs_dir / run_id / "artifacts" / job_id
    candidate = build_contact_candidate({"full_name": "Ada Lovelace", "email": "ada@example.test"})
    (artifact_dir / "contact_candidate.json").write_text(json.dumps(candidate, indent=2), encoding="utf-8")

    result = BusinessCardService(config).plan_sink_lookup_for_job(job_id=job_id, run_id=run_id)
    job = BusinessCardService(config).get_job(job_id, run_id=run_id)
    events = [
        json.loads(line)
        for line in (config.runs_dir / run_id / "events.jsonl").read_text(encoding="utf-8").splitlines()
    ]

    assert result["lookup_plan"]["schema"] == "business-card-watchdog.sink-lookup-plan.v1"
    assert result["lookup_plan"]["network_calls_made"] == 0
    assert [lookup["sink"] for lookup in result["lookup_plan"]["lookups"]] == ["google_contacts", "odoo"]
    assert result["lookup_plan"]["lookups"][0]["match_keys"]["email"] == "ada@example.test"
    assert any(artifact["kind"] == "sink_lookup_plan" for artifact in job["artifacts"])
    assert any(event["event_type"] == "sink_lookup_plan_created" for event in events)


def test_service_preflight_sink_apply_writes_zero_write_artifact(tmp_path: Path) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        sink=SinkConfig(google_contacts=True, dry_run=True),
        routing_rules=[{"match": "email_domain", "value": "*", "sinks": ["google_contacts"]}],
    )
    run_id, job_id = make_recorded_run(config)
    service = BusinessCardService(config)
    service.plan_sinks_for_job(job_id=job_id, run_id=run_id)

    preview = service.preflight_sink_apply(job_id=job_id, run_id=run_id)
    blocked = service.preflight_sink_apply(job_id=job_id, run_id=run_id, apply=True)
    job = service.get_job(job_id, run_id=run_id)
    events = [
        json.loads(line)
        for line in (config.runs_dir / run_id / "events.jsonl").read_text(encoding="utf-8").splitlines()
    ]

    assert preview["preflight"]["schema"] == "business-card-watchdog.sink-apply-preflight.v1"
    assert preview["preflight"]["state"] == "preview"
    assert preview["preflight"]["writes_attempted"] == 0
    assert preview["preflight"]["network_calls_made"] == 0
    assert blocked["preflight"]["state"] == "blocked"
    assert any(artifact["kind"] == "sink_apply_preflight" for artifact in job["artifacts"])
    assert any(event["event_type"] == "sink_apply_preflight_created" for event in events)


def test_service_decide_sink_apply_writes_zero_write_decision(tmp_path: Path) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        sink=SinkConfig(google_contacts=True, dry_run=True),
        routing_rules=[{"match": "email_domain", "value": "*", "sinks": ["google_contacts"]}],
    )
    run_id, job_id = make_recorded_run(config)
    service = BusinessCardService(config)
    service.plan_sinks_for_job(job_id=job_id, run_id=run_id)
    service.preflight_sink_apply(job_id=job_id, run_id=run_id)

    result = service.decide_sink_apply(
        job_id=job_id,
        run_id=run_id,
        decision="approve",
        reviewer="tester",
        reason="pilot approved",
    )
    job = service.get_job(job_id, run_id=run_id)
    events = [
        json.loads(line)
        for line in (config.runs_dir / run_id / "events.jsonl").read_text(encoding="utf-8").splitlines()
    ]

    assert result["decision"]["schema"] == "business-card-watchdog.sink-apply-decision.v1"
    assert result["decision"]["state"] == "approved_for_apply"
    assert result["decision"]["writes_attempted"] == 0
    assert any(artifact["kind"] == "sink_apply_decision" for artifact in job["artifacts"])
    assert any(event["event_type"] == "sink_apply_decided" for event in events)


def test_service_decide_sink_apply_noop_cancels_job(tmp_path: Path) -> None:
    config = AppConfig(config_path=tmp_path / "config.toml", data_dir=tmp_path / "data")
    run_id, job_id = make_recorded_run(config)

    result = BusinessCardService(config).decide_sink_apply(
        job_id=job_id,
        run_id=run_id,
        decision="noop",
        reviewer="tester",
        reason="no sink write needed",
    )

    assert result["job"]["state"] == "cancelled"
    assert result["job"]["error"] == "sink apply resolved as no-op"


def test_service_apply_sinks_for_job_writes_blocked_zero_write_result(tmp_path: Path) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        sink=SinkConfig(google_contacts=True, dry_run=True),
        routing_rules=[{"match": "email_domain", "value": "*", "sinks": ["google_contacts"]}],
    )
    run_id, job_id = make_recorded_run(config)
    service = BusinessCardService(config)
    service.plan_sinks_for_job(job_id=job_id, run_id=run_id)
    service.preflight_sink_apply(job_id=job_id, run_id=run_id)
    service.decide_sink_apply(job_id=job_id, run_id=run_id, decision="approve", reviewer="tester")

    result = service.apply_sinks_for_job(job_id=job_id, run_id=run_id, apply=True)
    job = service.get_job(job_id, run_id=run_id)
    events = [
        json.loads(line)
        for line in (config.runs_dir / run_id / "events.jsonl").read_text(encoding="utf-8").splitlines()
    ]

    assert result["result"]["schema"] == "business-card-watchdog.sink-apply-result.v1"
    assert result["result"]["state"] == "blocked"
    assert result["result"]["writes_attempted"] == 0
    assert result["result"]["network_calls_made"] == 0
    assert result["result"]["readback"] == []
    assert any(artifact["kind"] == "sink_apply_result" for artifact in job["artifacts"])
    assert any(event["event_type"] == "sink_apply_attempted" for event in events)


def test_service_apply_sinks_for_job_can_emit_mock_readback(tmp_path: Path) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        sink=SinkConfig(google_contacts=True, dry_run=True),
        routing_rules=[{"match": "email_domain", "value": "*", "sinks": ["google_contacts"]}],
    )
    run_id, job_id = make_recorded_run(config)
    service = BusinessCardService(config)
    service.plan_sinks_for_job(job_id=job_id, run_id=run_id)
    service.preflight_sink_apply(job_id=job_id, run_id=run_id)
    service.decide_sink_apply(job_id=job_id, run_id=run_id, decision="approve", reviewer="tester")

    result = service.apply_sinks_for_job(job_id=job_id, run_id=run_id, apply=True, simulate=True)
    events = [
        json.loads(line)
        for line in (config.runs_dir / run_id / "events.jsonl").read_text(encoding="utf-8").splitlines()
    ]

    assert result["result"]["state"] == "mock_applied"
    assert result["result"]["simulated"] is True
    assert result["result"]["readback"][0]["resource_id"].startswith("mock:google_contacts:")
    assert any(event["payload"]["simulated"] is True for event in events if event["event_type"] == "sink_apply_attempted")


def test_service_apply_sinks_for_job_uses_injected_write_executor(tmp_path: Path) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        sink=SinkConfig(google_contacts=True, dry_run=True),
        routing_rules=[{"match": "email_domain", "value": "*", "sinks": ["google_contacts"]}],
    )
    run_id, job_id = make_recorded_run(config)
    calls: list[dict[str, object]] = []

    def execute(request: dict[str, object]) -> dict[str, object]:
        calls.append(request)
        return {
            "sink": "google_contacts",
            "status": "live_write_completed",
            "network_calls_made": 1,
            "writes_attempted": 1,
            "write": {
                "sink": "google_contacts",
                "resource_id": "people/live123",
                "serialization_key": request.get("serialization_key"),
            },
        }

    service = BusinessCardService(config, sink_write_executor=execute)
    service.plan_sinks_for_job(job_id=job_id, run_id=run_id)
    service.build_sink_adapter_request_for_job(job_id=job_id, run_id=run_id, phase="write")
    service.preflight_sink_apply(job_id=job_id, run_id=run_id)
    service.decide_sink_apply(job_id=job_id, run_id=run_id, decision="approve", reviewer="tester")

    result = service.apply_sinks_for_job(job_id=job_id, run_id=run_id, apply=True)
    readback = service.build_sink_adapter_request_for_job(job_id=job_id, run_id=run_id, phase="readback")

    assert calls[0]["sink"] == "google_contacts"
    assert result["result"]["state"] == "live_applied"
    assert result["result"]["writes_attempted"] == 1
    assert result["result"]["network_calls_made"] == 1
    assert result["result"]["readback"][0]["resource_id"] == "people/live123"
    assert result["result"]["actions"][0]["write_attempted"] is True
    assert readback["request"]["requests"][0]["resource_id"] == "people/live123"


def test_service_readback_pilot_writes_simulated_evidence(tmp_path: Path) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        sink=SinkConfig(google_contacts=True, dry_run=True),
        routing_rules=[{"match": "email_domain", "value": "*", "sinks": ["google_contacts"]}],
    )
    run_id, job_id = make_recorded_run(config)
    service = BusinessCardService(config)
    service.plan_sinks_for_job(job_id=job_id, run_id=run_id)
    service.preflight_sink_apply(job_id=job_id, run_id=run_id)
    service.decide_sink_apply(job_id=job_id, run_id=run_id, decision="approve", reviewer="tester")
    service.apply_sinks_for_job(job_id=job_id, run_id=run_id, apply=True, simulate=True)
    service.build_sink_adapter_request_for_job(job_id=job_id, run_id=run_id, phase="readback")

    pilot = service.execute_sink_readback_pilot_for_job(
        job_id=job_id,
        run_id=run_id,
        sink="google_contacts",
        approved_by="tester",
    )
    job = service.get_job(job_id, run_id=run_id)

    assert pilot["pilot"]["schema"] == "business-card-watchdog.sink-readback-pilot.v1"
    assert pilot["pilot"]["state"] == "verified"
    assert pilot["pilot"]["simulated"] is True
    assert pilot["pilot"]["writes_attempted"] == 0
    assert pilot["pilot"]["network_calls_made"] == 0
    assert pilot["pilot"]["readback"]["resource_id"].startswith("mock:google_contacts:")
    assert any(artifact["kind"] == "sink_readback_pilot" for artifact in job["artifacts"])


def test_service_readback_pilot_uses_injected_executor(tmp_path: Path) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        sink=SinkConfig(google_contacts=True, dry_run=True),
        routing_rules=[{"match": "email_domain", "value": "*", "sinks": ["google_contacts"]}],
    )
    run_id, job_id = make_recorded_run(config)
    calls: list[dict[str, object]] = []

    def write(request: dict[str, object]) -> dict[str, object]:
        return {
            "sink": "google_contacts",
            "network_calls_made": 1,
            "writes_attempted": 1,
            "write": {"resource_id": "people/live123", "serialization_key": request.get("serialization_key")},
        }

    def readback(request: dict[str, object]) -> dict[str, object]:
        calls.append(request)
        return {
            "sink": "google_contacts",
            "status": "live_readback_completed",
            "network_calls_made": 1,
            "writes_attempted": 0,
            "readback": {
                "resource_id": "people/live123",
                "display": "Live Fixture",
                "emails": ["fixture@example.test"],
                "matched": True,
            },
        }

    service = BusinessCardService(config, sink_write_executor=write, sink_readback_executor=readback)
    service.plan_sinks_for_job(job_id=job_id, run_id=run_id)
    service.build_sink_adapter_request_for_job(job_id=job_id, run_id=run_id, phase="write")
    service.preflight_sink_apply(job_id=job_id, run_id=run_id)
    service.decide_sink_apply(job_id=job_id, run_id=run_id, decision="approve", reviewer="tester")
    service.apply_sinks_for_job(job_id=job_id, run_id=run_id, apply=True)
    service.build_sink_adapter_request_for_job(job_id=job_id, run_id=run_id, phase="readback")

    pilot = service.execute_sink_readback_pilot_for_job(
        job_id=job_id,
        run_id=run_id,
        sink="google_contacts",
        approved_by="tester",
        simulate=False,
    )

    assert calls[0]["sink"] == "google_contacts"
    assert calls[0]["resource_id"] == "people/live123"
    assert pilot["pilot"]["status"] == "live_readback_completed"
    assert pilot["pilot"]["simulated"] is False
    assert pilot["pilot"]["network_calls_made"] == 1
    assert pilot["pilot"]["writes_attempted"] == 0
    assert pilot["pilot"]["readback"]["emails"] == ["fixture@example.test"]


def test_service_build_sink_adapter_request_writes_phase_artifact(tmp_path: Path) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        sink=SinkConfig(
            google_contacts=True,
            google_contacts_profile="codex",
            odoo=True,
            odollo_tenant="saber",
            dry_run=True,
        ),
        routing_rules=[{"match": "email_domain", "value": "*", "sinks": ["google_contacts", "odoo"]}],
    )
    run_id, job_id = make_recorded_run(config)
    service = BusinessCardService(config)

    lookup = service.build_sink_adapter_request_for_job(job_id=job_id, run_id=run_id, phase="lookup")
    write = service.build_sink_adapter_request_for_job(job_id=job_id, run_id=run_id, phase="write")
    readback = service.build_sink_adapter_request_for_job(job_id=job_id, run_id=run_id, phase="readback")
    job = service.get_job(job_id, run_id=run_id)
    events = [
        json.loads(line)
        for line in (config.runs_dir / run_id / "events.jsonl").read_text(encoding="utf-8").splitlines()
    ]

    assert lookup["request"]["schema"] == "business-card-watchdog.sink-adapter-request.v1"
    assert lookup["request"]["phase"] == "lookup"
    assert lookup["request"]["network_calls_made"] == 0
    assert lookup["request"]["requests"][0]["profile"]["name"] == "codex"
    assert lookup["request"]["requests"][1]["tenant"]["name"] == "saber"
    assert write["request"]["phase"] == "write"
    assert write["request"]["requests"][0]["profile"]["name"] == "codex"
    assert write["request"]["requests"][1]["tenant"]["name"] == "saber"
    assert readback["request"]["phase"] == "readback"
    assert readback["request"]["requests"][0]["profile"]["name"] == "codex"
    assert readback["request"]["requests"][1]["tenant"]["name"] == "saber"
    assert any(artifact["kind"] == "sink_adapter_request_lookup" for artifact in job["artifacts"])
    assert any(artifact["kind"] == "sink_adapter_request_write" for artifact in job["artifacts"])
    assert any(artifact["kind"] == "sink_adapter_request_readback" for artifact in job["artifacts"])
    assert any(event["event_type"] == "sink_adapter_request_created" for event in events)


def test_service_record_sink_lookup_result_writes_zero_network_artifact(tmp_path: Path) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        sink=SinkConfig(google_contacts=True, dry_run=True),
        routing_rules=[{"match": "email_domain", "value": "*", "sinks": ["google_contacts"]}],
    )
    run_id, job_id = make_recorded_run(config)
    service = BusinessCardService(config)

    result = service.record_sink_lookup_result_for_job(
        job_id=job_id,
        run_id=run_id,
        matches_by_sink={
            "google_contacts": [
                {
                    "resource_id": "people/c123",
                    "confidence": 0.9,
                    "basis": ["email"],
                    "display": "Reviewed Fixture",
                }
            ]
        },
    )
    job = service.get_job(job_id, run_id=run_id)
    events = [
        json.loads(line)
        for line in (config.runs_dir / run_id / "events.jsonl").read_text(encoding="utf-8").splitlines()
    ]

    assert result["result"]["schema"] == "business-card-watchdog.sink-lookup-result.v1"
    assert result["result"]["state"] == "possible_duplicate"
    assert result["result"]["network_calls_made"] == 0
    assert result["result"]["writes_attempted"] == 0
    assert result["result"]["match_count"] == 1
    assert any(artifact["kind"] == "sink_lookup_result" for artifact in job["artifacts"])
    assert any(event["event_type"] == "sink_lookup_result_recorded" for event in events)


def test_service_lookup_pilot_writes_result_and_blocks_duplicate_review(tmp_path: Path) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        sink=SinkConfig(google_contacts=True, dry_run=True),
        routing_rules=[{"match": "email_domain", "value": "*", "sinks": ["google_contacts"]}],
    )
    run_id, job_id = make_recorded_run(config)
    service = BusinessCardService(config)
    service.build_sink_adapter_request_for_job(job_id=job_id, run_id=run_id, phase="lookup")

    pilot = service.execute_sink_lookup_pilot_for_job(
        job_id=job_id,
        run_id=run_id,
        sink="google_contacts",
        approved_by="operator",
        matches=[
            {
                "resource_id": "people/c123",
                "confidence": 0.92,
                "basis": ["email"],
                "display": "Reviewed Fixture",
            }
        ],
    )
    assessment = service.assess_downstream_duplicates_for_job(job_id=job_id, run_id=run_id)
    job = service.get_job(job_id, run_id=run_id)
    events = [
        json.loads(line)
        for line in (config.runs_dir / run_id / "events.jsonl").read_text(encoding="utf-8").splitlines()
    ]

    assert pilot["pilot"]["schema"] == "business-card-watchdog.sink-lookup-pilot.v1"
    assert pilot["pilot"]["sink"] == "google_contacts"
    assert pilot["pilot"]["network_calls_made"] == 0
    assert pilot["pilot"]["writes_attempted"] == 0
    assert pilot["result"]["source_pilot_schema"] == "business-card-watchdog.sink-lookup-pilot.v1"
    assert pilot["result"]["state"] == "possible_duplicate"
    assert assessment["assessment"]["state"] == "strong_duplicate"
    assert any(artifact["kind"] == "sink_lookup_pilot" for artifact in job["artifacts"])
    assert any(artifact["kind"] == "sink_lookup_result" for artifact in job["artifacts"])
    assert any(event["event_type"] == "sink_lookup_pilot_executed" for event in events)


def test_service_lookup_pilot_uses_injected_read_only_executor(tmp_path: Path) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        sink=SinkConfig(google_contacts=True, dry_run=True),
        routing_rules=[{"match": "email_domain", "value": "*", "sinks": ["google_contacts"]}],
    )
    run_id, job_id = make_recorded_run(config)
    calls: list[dict[str, object]] = []

    def execute(request: dict[str, object]) -> dict[str, object]:
        calls.append(request)
        return {
            "sink": "google_contacts",
            "status": "read_only_lookup_completed",
            "network_calls_made": 1,
            "writes_attempted": 0,
            "matches": [
                {
                    "resource_id": "people/live123",
                    "confidence": 0.91,
                    "basis": ["email"],
                    "display": "Live Fixture",
                }
            ],
        }

    service = BusinessCardService(config, sink_lookup_executor=execute)
    service.build_sink_adapter_request_for_job(job_id=job_id, run_id=run_id, phase="lookup")

    payload = service.execute_sink_lookup_pilot_for_job(
        job_id=job_id,
        run_id=run_id,
        sink="google_contacts",
        approved_by="operator",
        simulate=False,
    )

    assert calls[0]["sink"] == "google_contacts"
    assert payload["pilot"]["status"] == "read_only_lookup_completed"
    assert payload["pilot"]["simulated"] is False
    assert payload["pilot"]["network_calls_made"] == 1
    assert payload["pilot"]["writes_attempted"] == 0
    assert payload["result"]["status"] == "read_only_lookup_matches"
    assert payload["result"]["network_calls_made"] == 1
    assert payload["result"]["results"][0]["matches"][0]["resource_id"] == "people/live123"


def test_service_assess_downstream_duplicates_blocks_review_and_can_resolve(tmp_path: Path) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        sink=SinkConfig(google_contacts=True, dry_run=True),
        routing_rules=[{"match": "email_domain", "value": "*", "sinks": ["google_contacts"]}],
    )
    run_id, job_id = make_recorded_run(config)
    service = BusinessCardService(config)
    service.submit_review(
        job_id=job_id,
        run_id=run_id,
        reviewer="tester",
        action="approve_for_routing",
        field_corrections={"full_name": "Reviewed Fixture", "email": "fixture@example.test"},
    )
    service.plan_sink_lookup_for_job(job_id=job_id, run_id=run_id)
    service.build_sink_adapter_request_for_job(job_id=job_id, run_id=run_id, phase="lookup")
    service.record_sink_lookup_result_for_job(
        job_id=job_id,
        run_id=run_id,
        matches_by_sink={
            "google_contacts": [
                {
                    "resource_id": "people/c123",
                    "confidence": 0.91,
                    "basis": ["email"],
                    "display": "Reviewed Fixture",
                }
            ]
        },
    )

    assessment = service.assess_downstream_duplicates_for_job(job_id=job_id, run_id=run_id)
    job = service.get_job(job_id, run_id=run_id)
    resolved = service.submit_review(
        job_id=job_id,
        run_id=run_id,
        reviewer="tester",
        action="resolve_duplicate",
        duplicate_resolution={"decision": "merge_existing", "target_identity": "people/c123"},
    )
    events = [
        json.loads(line)
        for line in (config.runs_dir / run_id / "events.jsonl").read_text(encoding="utf-8").splitlines()
    ]

    assert assessment["assessment"]["state"] == "strong_duplicate"
    assert assessment["job"]["state"] == "needs_review"
    assert job["state"] == "needs_review"
    assert resolved["job"]["state"] == "ready_to_route"
    assert any(artifact["kind"] == "downstream_duplicate_assessment" for artifact in job["artifacts"])
    assert any(event["event_type"] == "downstream_duplicate_assessed" for event in events)


def test_service_next_actions_recommends_sink_lookup_for_ready_job(tmp_path: Path) -> None:
    config = AppConfig(config_path=tmp_path / "config.toml", data_dir=tmp_path / "data")
    run_id, job_id = make_recorded_run(config)
    service = BusinessCardService(config)
    service.submit_review(
        job_id=job_id,
        run_id=run_id,
        reviewer="tester",
        action="approve_for_routing",
        field_corrections={"full_name": "Reviewed Fixture", "email": "fixture@example.test"},
    )

    payload = service.next_actions(run_id=run_id)

    assert payload["actions"][0]["action"] == "plan_sink_lookup"
    assert payload["actions"][0]["command"] == "sinks lookup-plan"


def test_service_next_actions_recommends_lookup_adapter_request_after_lookup_plan(tmp_path: Path) -> None:
    config = AppConfig(config_path=tmp_path / "config.toml", data_dir=tmp_path / "data")
    run_id, job_id = make_recorded_run(config)
    service = BusinessCardService(config)
    service.submit_review(
        job_id=job_id,
        run_id=run_id,
        reviewer="tester",
        action="approve_for_routing",
        field_corrections={"full_name": "Reviewed Fixture", "email": "fixture@example.test"},
    )
    service.plan_sink_lookup_for_job(job_id=job_id, run_id=run_id)

    payload = service.next_actions(run_id=run_id)

    assert payload["actions"][0]["action"] == "prepare_sink_lookup_adapter"
    assert payload["actions"][0]["command"] == "sinks adapter-request --phase lookup"


def test_service_next_actions_recommends_lookup_result_after_lookup_adapter_request(tmp_path: Path) -> None:
    config = AppConfig(config_path=tmp_path / "config.toml", data_dir=tmp_path / "data")
    run_id, job_id = make_recorded_run(config)
    service = BusinessCardService(config)
    service.submit_review(
        job_id=job_id,
        run_id=run_id,
        reviewer="tester",
        action="approve_for_routing",
        field_corrections={"full_name": "Reviewed Fixture", "email": "fixture@example.test"},
    )
    service.plan_sink_lookup_for_job(job_id=job_id, run_id=run_id)
    service.build_sink_adapter_request_for_job(job_id=job_id, run_id=run_id, phase="lookup")

    payload = service.next_actions(run_id=run_id)

    assert payload["actions"][0]["action"] == "record_sink_lookup_result"
    assert payload["actions"][0]["command"] == "sinks lookup-result"


def test_service_next_actions_recommends_downstream_duplicate_assessment_after_lookup_result(tmp_path: Path) -> None:
    config = AppConfig(config_path=tmp_path / "config.toml", data_dir=tmp_path / "data")
    run_id, job_id = make_recorded_run(config)
    service = BusinessCardService(config)
    service.submit_review(
        job_id=job_id,
        run_id=run_id,
        reviewer="tester",
        action="approve_for_routing",
        field_corrections={"full_name": "Reviewed Fixture", "email": "fixture@example.test"},
    )
    service.plan_sink_lookup_for_job(job_id=job_id, run_id=run_id)
    service.build_sink_adapter_request_for_job(job_id=job_id, run_id=run_id, phase="lookup")
    service.record_sink_lookup_result_for_job(job_id=job_id, run_id=run_id)

    payload = service.next_actions(run_id=run_id)

    assert payload["actions"][0]["action"] == "assess_downstream_duplicates"
    assert payload["actions"][0]["command"] == "sinks assess-duplicates"


def test_service_next_actions_recommends_sink_plan_after_downstream_duplicate_assessment(tmp_path: Path) -> None:
    config = AppConfig(config_path=tmp_path / "config.toml", data_dir=tmp_path / "data")
    run_id, job_id = make_recorded_run(config)
    service = BusinessCardService(config)
    service.submit_review(
        job_id=job_id,
        run_id=run_id,
        reviewer="tester",
        action="approve_for_routing",
        field_corrections={"full_name": "Reviewed Fixture", "email": "fixture@example.test"},
    )
    service.plan_sink_lookup_for_job(job_id=job_id, run_id=run_id)
    service.build_sink_adapter_request_for_job(job_id=job_id, run_id=run_id, phase="lookup")
    service.record_sink_lookup_result_for_job(job_id=job_id, run_id=run_id)
    service.assess_downstream_duplicates_for_job(job_id=job_id, run_id=run_id)

    payload = service.next_actions(run_id=run_id)

    assert payload["actions"][0]["action"] == "plan_sinks"


def test_service_next_actions_recommends_write_adapter_request_after_sink_plan(tmp_path: Path) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        sink=SinkConfig(google_contacts=True, dry_run=True),
        routing_rules=[{"match": "email_domain", "value": "*", "sinks": ["google_contacts"]}],
    )
    run_id, job_id = make_recorded_run(config)
    service = BusinessCardService(config)
    service.submit_review(
        job_id=job_id,
        run_id=run_id,
        reviewer="tester",
        action="approve_for_routing",
        field_corrections={"full_name": "Reviewed Fixture", "email": "fixture@example.test"},
    )
    service.plan_sink_lookup_for_job(job_id=job_id, run_id=run_id)
    service.build_sink_adapter_request_for_job(job_id=job_id, run_id=run_id, phase="lookup")
    service.record_sink_lookup_result_for_job(job_id=job_id, run_id=run_id)
    service.assess_downstream_duplicates_for_job(job_id=job_id, run_id=run_id)
    service.plan_sinks_for_job(job_id=job_id, run_id=run_id)

    payload = service.next_actions(run_id=run_id)

    assert payload["actions"][0]["action"] == "prepare_sink_write_adapter"
    assert payload["actions"][0]["command"] == "sinks adapter-request --phase write"


def test_service_next_actions_recommends_apply_preflight_after_write_adapter_request(tmp_path: Path) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        routing_rules=[{"match": "email_domain", "value": "*", "sinks": ["google_contacts"]}],
    )
    run_id, job_id = make_recorded_run(config)
    service = BusinessCardService(config)
    service.submit_review(
        job_id=job_id,
        run_id=run_id,
        reviewer="tester",
        action="approve_for_routing",
        field_corrections={"full_name": "Reviewed Fixture", "email": "fixture@example.test"},
    )
    service.plan_sink_lookup_for_job(job_id=job_id, run_id=run_id)
    service.build_sink_adapter_request_for_job(job_id=job_id, run_id=run_id, phase="lookup")
    service.record_sink_lookup_result_for_job(job_id=job_id, run_id=run_id)
    service.assess_downstream_duplicates_for_job(job_id=job_id, run_id=run_id)
    service.plan_sinks_for_job(job_id=job_id, run_id=run_id)
    service.build_sink_adapter_request_for_job(job_id=job_id, run_id=run_id, phase="write")

    payload = service.next_actions(run_id=run_id)

    assert payload["actions"][0]["action"] == "preflight_sink_apply"
    assert payload["actions"][0]["command"] == "sinks apply-preflight"


def test_service_next_actions_recommends_apply_decision_after_preflight(tmp_path: Path) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        routing_rules=[{"match": "email_domain", "value": "*", "sinks": ["google_contacts"]}],
    )
    run_id, job_id = make_recorded_run(config)
    service = BusinessCardService(config)
    service.submit_review(
        job_id=job_id,
        run_id=run_id,
        reviewer="tester",
        action="approve_for_routing",
        field_corrections={"full_name": "Reviewed Fixture", "email": "fixture@example.test"},
    )
    service.plan_sink_lookup_for_job(job_id=job_id, run_id=run_id)
    service.build_sink_adapter_request_for_job(job_id=job_id, run_id=run_id, phase="lookup")
    service.record_sink_lookup_result_for_job(job_id=job_id, run_id=run_id)
    service.assess_downstream_duplicates_for_job(job_id=job_id, run_id=run_id)
    service.plan_sinks_for_job(job_id=job_id, run_id=run_id)
    service.build_sink_adapter_request_for_job(job_id=job_id, run_id=run_id, phase="write")
    service.preflight_sink_apply(job_id=job_id, run_id=run_id)

    payload = service.next_actions(run_id=run_id)

    assert payload["actions"][0]["action"] == "decide_sink_apply"
    assert payload["actions"][0]["command"] == "sinks apply-decision"


def test_service_run_next_actions_executes_safe_steps_until_manual_decision(tmp_path: Path) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        routing_rules=[{"match": "email_domain", "value": "*", "sinks": ["google_contacts"]}],
    )
    run_id, job_id = make_recorded_run(config)
    service = BusinessCardService(config)
    service.submit_review(
        job_id=job_id,
        run_id=run_id,
        reviewer="tester",
        action="approve_for_routing",
        field_corrections={"full_name": "Reviewed Fixture", "email": "fixture@example.test"},
    )

    payload = service.run_next_actions(run_id=run_id, limit=10)
    job = service.get_job(job_id, run_id=run_id)

    assert [item["action"] for item in payload["executed"]] == [
        "plan_sink_lookup",
        "prepare_sink_lookup_adapter",
        "record_sink_lookup_result",
        "assess_downstream_duplicates",
        "plan_sinks",
        "prepare_sink_write_adapter",
        "preflight_sink_apply",
    ]
    assert payload["skipped"][0]["action"] == "decide_sink_apply"
    assert payload["skipped"][0]["status"] == "skipped"
    assert {artifact["kind"] for artifact in job["artifacts"]} >= {
        "sink_lookup_plan",
        "sink_adapter_request_lookup",
        "sink_lookup_result",
        "downstream_duplicate_assessment",
        "sink_plan",
        "sink_adapter_request_write",
        "sink_apply_preflight",
    }


def test_service_review_update_refreshes_stale_route_artifacts(tmp_path: Path) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        sink=SinkConfig(google_contacts=True, dry_run=True),
        routing_rules=[{"match": "email_domain", "value": "*", "sinks": ["google_contacts"]}],
    )
    run_id, job_id = make_recorded_run(config)
    service = BusinessCardService(config)
    service.submit_review(
        job_id=job_id,
        run_id=run_id,
        reviewer="tester",
        action="approve_for_routing",
        field_corrections={"full_name": "Old Fixture", "email": "old@example.test"},
    )
    service.run_next_actions(run_id=run_id, limit=10)
    artifact_dir = config.runs_dir / run_id / "artifacts" / job_id
    stale_artifact_payloads = {
        kind: json.loads((artifact_dir / filename).read_text(encoding="utf-8"))
        for kind, filename in {
            "sink_lookup_plan": "sink_lookup_plan.json",
            "sink_adapter_request_lookup": "sink_adapter_request_lookup.json",
            "sink_lookup_result": "sink_lookup_result.json",
            "downstream_duplicate_assessment": "downstream_duplicate_assessment.json",
            "sink_plan": "sink_plan.json",
            "sink_adapter_request_write": "sink_adapter_request_write.json",
            "sink_apply_preflight": "sink_apply_preflight.json",
        }.items()
    }

    result = service.submit_review(
        job_id=job_id,
        run_id=run_id,
        reviewer="tester",
        action="approve_for_routing",
        field_corrections={"full_name": "Reviewed Fixture", "email": "new@example.test"},
    )
    next_action = service.next_actions(run_id=run_id)["actions"][0]
    rerun = service.run_next_actions(run_id=run_id, limit=10)
    route_refresh = json.loads((artifact_dir / "route_refresh.json").read_text(encoding="utf-8"))
    lookup_plan = json.loads((artifact_dir / "sink_lookup_plan.json").read_text(encoding="utf-8"))
    sink_plan = json.loads((artifact_dir / "sink_plan.json").read_text(encoding="utf-8"))
    events = [
        json.loads(line)
        for line in (config.runs_dir / run_id / "events.jsonl").read_text(encoding="utf-8").splitlines()
    ]

    assert result["route_refresh"]["schema"] == "business-card-watchdog.route-refresh.v1"
    assert result["route_refresh"]["stale_artifact_kinds"] == [
        "sink_lookup_plan",
        "sink_adapter_request_lookup",
        "sink_lookup_result",
        "downstream_duplicate_assessment",
        "sink_plan",
        "sink_adapter_request_write",
        "sink_apply_preflight",
    ]
    assert result["route_refresh"]["pending_artifact_kinds"] == result["route_refresh"]["stale_artifact_kinds"]
    assert next_action["action"] == "plan_sink_lookup"
    assert next_action["route_refresh_path"].endswith("route_refresh.json")
    assert [item["action"] for item in rerun["executed"]] == [
        "plan_sink_lookup",
        "prepare_sink_lookup_adapter",
        "record_sink_lookup_result",
        "assess_downstream_duplicates",
        "plan_sinks",
        "prepare_sink_write_adapter",
        "preflight_sink_apply",
    ]
    assert route_refresh["state"] == "complete"
    assert route_refresh["pending_artifact_kinds"] == []
    assert route_refresh["refreshed_artifact_kinds"] == result["route_refresh"]["stale_artifact_kinds"]
    assert stale_artifact_payloads["sink_lookup_plan"]["lookups"][0]["match_keys"]["email"] == "old@example.test"
    assert stale_artifact_payloads["sink_plan"]["actions"][0]["match_keys"]["email"] == "old@example.test"
    assert lookup_plan["lookups"][0]["match_keys"]["email"] == "new@example.test"
    assert sink_plan["actions"][0]["match_keys"]["email"] == "new@example.test"
    assert any(event["event_type"] == "route_refresh_requested" for event in events)
    assert any(event["event_type"] == "route_refresh_updated" for event in events)


def test_service_enrichment_merge_refreshes_existing_sink_plan(tmp_path: Path) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        sink=SinkConfig(google_contacts=True, dry_run=True),
        routing_rules=[{"match": "email_domain", "value": "*", "sinks": ["google_contacts"]}],
    )
    run_id, job_id = make_recorded_run(config)
    service = BusinessCardService(config)
    artifact_dir = config.runs_dir / run_id / "artifacts" / job_id
    service.submit_review(
        job_id=job_id,
        run_id=run_id,
        reviewer="tester",
        action="approve_for_routing",
        field_corrections={"full_name": "Ada Lovelace", "email": "ada@example.test", "notes": "Card note"},
    )
    service.plan_sinks_for_job(job_id=job_id, run_id=run_id)
    (artifact_dir / "enrichment_result.json").write_text(
        json.dumps(
            {
                "schema": "business-card-watchdog.enrichment-result.v1",
                "merge_proposals": [
                    {
                        "field": "notes",
                        "value": "Public-web corroboration candidate: https://example.test/ada",
                        "source": "public_web",
                        "requires_review": True,
                    }
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    result = service.submit_review(
        job_id=job_id,
        run_id=run_id,
        reviewer="tester",
        action="approve_enrichment_merge",
        approved_enrichment_fields=["notes"],
    )
    next_action = service.next_actions(run_id=run_id)["actions"][0]
    refreshed = service.plan_sinks_for_job(job_id=job_id, run_id=run_id)
    route_refresh = json.loads((artifact_dir / "route_refresh.json").read_text(encoding="utf-8"))

    assert result["route_refresh"]["reason"] == "enrichment_merge_updated_reviewed_contact"
    assert result["route_refresh"]["pending_artifact_kinds"] == ["sink_plan"]
    assert next_action["action"] == "plan_sinks"
    assert route_refresh["state"] == "complete"
    assert "Public-web corroboration candidate" in refreshed["plan"]["payloads"][0]["payload"]["values"]["notes"]


def test_service_sink_plan_preserves_profile_url_contact_points(tmp_path: Path) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        sink=SinkConfig(google_contacts=True, odoo=True, dry_run=True),
        routing_rules=[{"match": "email_domain", "value": "*", "sinks": ["google_contacts", "odoo"]}],
    )
    run_id, job_id = make_recorded_run(config)
    artifact_dir = config.runs_dir / run_id / "artifacts" / job_id
    candidate = build_contact_candidate(
        {
            "full_name": "Ada Lovelace",
            "email": "ada@example.test",
            "linkedin_url": "linkedin.com/in/ada-lovelace",
        }
    )
    (artifact_dir / "contact_candidate.json").write_text(json.dumps(candidate, indent=2), encoding="utf-8")

    plan = BusinessCardService(config).plan_sinks_for_job(job_id=job_id, run_id=run_id)["plan"]

    for payload in plan["payloads"]:
        assert {
            "kind": "profile_url",
            "value": "https://linkedin.com/in/ada-lovelace",
            "label": "linkedin_url",
        } in payload["payload"]["values"]["contact_points"]


def test_service_duplicate_resolution_refreshes_existing_sink_plan(tmp_path: Path) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        sink=SinkConfig(google_contacts=True, dry_run=True),
        routing_rules=[{"match": "email_domain", "value": "*", "sinks": ["google_contacts"]}],
    )
    run_id, job_id = make_recorded_run(config)
    service = BusinessCardService(config)
    artifact_dir = config.runs_dir / run_id / "artifacts" / job_id
    service.submit_review(
        job_id=job_id,
        run_id=run_id,
        reviewer="tester",
        action="approve_for_routing",
        field_corrections={"full_name": "Ada Lovelace", "email": "ada@example.test"},
    )
    service.plan_sinks_for_job(job_id=job_id, run_id=run_id)
    (artifact_dir / "duplicate_assessment.json").write_text(
        json.dumps(
            {
                "schema": "business-card-watchdog.duplicate-assessment.v1",
                "state": "strong_duplicate",
                "matches": [{"match_type": "email", "serialization_key": "email:ada@example.test"}],
                "reasons": ["email match"],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    result = service.submit_review(
        job_id=job_id,
        run_id=run_id,
        reviewer="tester",
        action="resolve_duplicate",
        duplicate_resolution={
            "decision": "merge_existing",
            "target_identity": "email:ada@example.test",
            "reason": "same contact",
        },
    )
    next_action = service.next_actions(run_id=run_id)["actions"][0]
    refreshed = service.plan_sinks_for_job(job_id=job_id, run_id=run_id)
    route_refresh = json.loads((artifact_dir / "route_refresh.json").read_text(encoding="utf-8"))

    assert result["route_refresh"]["reason"] == "duplicate_resolution_updated_route_context"
    assert result["route_refresh"]["pending_artifact_kinds"] == ["sink_plan"]
    assert next_action["action"] == "plan_sinks"
    assert route_refresh["state"] == "complete"
    assert refreshed["plan"]["duplicate_resolution"]["decision"] == "merge_existing"


def test_service_next_actions_recommends_live_apply_after_decision(tmp_path: Path) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        routing_rules=[{"match": "email_domain", "value": "*", "sinks": ["google_contacts"]}],
    )
    run_id, job_id = make_recorded_run(config)
    service = BusinessCardService(config)
    service.submit_review(
        job_id=job_id,
        run_id=run_id,
        reviewer="tester",
        action="approve_for_routing",
        field_corrections={"full_name": "Reviewed Fixture", "email": "fixture@example.test"},
    )
    service.plan_sink_lookup_for_job(job_id=job_id, run_id=run_id)
    service.build_sink_adapter_request_for_job(job_id=job_id, run_id=run_id, phase="lookup")
    service.record_sink_lookup_result_for_job(job_id=job_id, run_id=run_id)
    service.assess_downstream_duplicates_for_job(job_id=job_id, run_id=run_id)
    service.plan_sinks_for_job(job_id=job_id, run_id=run_id)
    service.build_sink_adapter_request_for_job(job_id=job_id, run_id=run_id, phase="write")
    service.preflight_sink_apply(job_id=job_id, run_id=run_id)
    service.decide_sink_apply(job_id=job_id, run_id=run_id, decision="approve", reviewer="tester")

    payload = service.next_actions(run_id=run_id)

    assert payload["actions"][0]["action"] == "prepare_sink_apply_pilot_readiness"
    assert payload["actions"][0]["command"] == "sinks apply-pilot-readiness"

    readiness = service.build_sink_apply_pilot_readiness_for_job(job_id=job_id, run_id=run_id)
    next_payload = service.next_actions(run_id=run_id)

    assert readiness["readiness"]["schema"] == "business-card-watchdog.sink-apply-pilot-readiness.v1"
    assert readiness["readiness"]["can_apply_pilot"] is True
    assert readiness["readiness"]["can_mock_apply_pilot"] is True
    assert readiness["readiness"]["can_live_apply_pilot"] is False
    assert readiness["readiness"]["state"] == "ready_for_mock_apply"
    assert readiness["readiness"]["writes_attempted"] == 0
    assert readiness["readiness"]["network_calls_made"] == 0
    assert "readback_adapter_available_after_apply" in readiness["readiness"]["missing_requirements"]
    assert readiness["readiness"]["mock_missing_requirements"] == []
    assert "readback_adapter_available_after_apply" in readiness["readiness"]["live_missing_requirements"]
    assert next_payload["actions"][0]["action"] == "await_apply_approval"
    assert next_payload["actions"][0]["command"] == "sinks apply --apply"


def test_service_next_actions_recommends_readback_adapter_request_after_apply_result(tmp_path: Path) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        routing_rules=[{"match": "email_domain", "value": "*", "sinks": ["google_contacts"]}],
    )
    run_id, job_id = make_recorded_run(config)
    service = BusinessCardService(config)
    service.submit_review(
        job_id=job_id,
        run_id=run_id,
        reviewer="tester",
        action="approve_for_routing",
        field_corrections={"full_name": "Reviewed Fixture", "email": "fixture@example.test"},
    )
    service.plan_sink_lookup_for_job(job_id=job_id, run_id=run_id)
    service.build_sink_adapter_request_for_job(job_id=job_id, run_id=run_id, phase="lookup")
    service.record_sink_lookup_result_for_job(job_id=job_id, run_id=run_id)
    service.assess_downstream_duplicates_for_job(job_id=job_id, run_id=run_id)
    service.plan_sinks_for_job(job_id=job_id, run_id=run_id)
    service.build_sink_adapter_request_for_job(job_id=job_id, run_id=run_id, phase="write")
    service.preflight_sink_apply(job_id=job_id, run_id=run_id)
    service.decide_sink_apply(job_id=job_id, run_id=run_id, decision="approve", reviewer="tester")
    service.apply_sinks_for_job(job_id=job_id, run_id=run_id, apply=True, simulate=True)

    payload = service.next_actions(run_id=run_id)

    assert payload["actions"][0]["action"] == "prepare_sink_readback_adapter"
    assert payload["actions"][0]["command"] == "sinks adapter-request --phase readback"


def test_service_simulated_apply_requires_ready_pilot_readiness(tmp_path: Path) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        sink=SinkConfig(google_contacts=True, dry_run=True),
        routing_rules=[{"match": "email_domain", "value": "*", "sinks": ["google_contacts"]}],
    )
    run_id, job_id = make_recorded_run(config)
    service = BusinessCardService(config)
    service.submit_review(
        job_id=job_id,
        run_id=run_id,
        reviewer="tester",
        action="approve_for_routing",
        field_corrections={"full_name": "Reviewed Fixture", "email": "fixture@example.test"},
    )
    service.plan_sink_lookup_for_job(job_id=job_id, run_id=run_id)
    service.build_sink_adapter_request_for_job(job_id=job_id, run_id=run_id, phase="lookup")
    service.record_sink_lookup_result_for_job(job_id=job_id, run_id=run_id)
    service.assess_downstream_duplicates_for_job(job_id=job_id, run_id=run_id)
    service.plan_sinks_for_job(job_id=job_id, run_id=run_id)
    service.build_sink_adapter_request_for_job(job_id=job_id, run_id=run_id, phase="write")
    service.preflight_sink_apply(job_id=job_id, run_id=run_id)
    service.decide_sink_apply(job_id=job_id, run_id=run_id, decision="approve", reviewer="tester")

    result = service.apply_sinks_for_job(job_id=job_id, run_id=run_id, apply=True, simulate=True)
    readiness_path = config.runs_dir / run_id / "artifacts" / job_id / "sink_apply_pilot_readiness.json"

    assert readiness_path.exists()
    assert result["result"]["state"] == "mock_applied"
    assert result["result"]["simulated"] is True
    assert result["result"]["writes_attempted"] == 0
    assert result["result"]["readback"][0]["simulated"] is True


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


def test_service_submit_review_supports_request_enrichment_reject_and_skip(tmp_path: Path) -> None:
    config = AppConfig(config_path=tmp_path / "config.toml", data_dir=tmp_path / "data")
    service = BusinessCardService(config)

    enrich_run_id, enrich_job_id = make_recorded_run(config, run_id="run-enrich")
    enrich = service.submit_review(
        job_id=enrich_job_id,
        run_id=enrich_run_id,
        reviewer="tester",
        action="request_enrichment",
        notes="needs public web corroboration",
    )
    assert enrich["job"]["state"] == "needs_review"

    reject_run_id, reject_job_id = make_recorded_run(config, run_id="run-reject")
    rejected = service.submit_review(
        job_id=reject_job_id,
        run_id=reject_run_id,
        reviewer="tester",
        action="reject_not_card",
    )
    assert rejected["job"]["state"] == "failed"
    assert "not a business card" in str(rejected["job"]["error"])

    skip_run_id, skip_job_id = make_recorded_run(config, run_id="run-skip")
    skipped = service.submit_review(
        job_id=skip_job_id,
        run_id=skip_run_id,
        reviewer="tester",
        action="skip",
    )
    assert skipped["job"]["state"] == "cancelled"


def test_service_submit_review_approves_enrichment_merge(tmp_path: Path) -> None:
    config = AppConfig(config_path=tmp_path / "config.toml", data_dir=tmp_path / "data")
    run_id, job_id = make_recorded_run(config)
    artifact_dir = config.runs_dir / run_id / "artifacts" / job_id
    candidate = build_contact_candidate({"full_name": "Ada Lovelace", "notes": "Card note"})
    (artifact_dir / "contact_candidate.json").write_text(json.dumps(candidate, indent=2), encoding="utf-8")
    (artifact_dir / "enrichment_result.json").write_text(
        json.dumps(
            {
                "schema": "business-card-watchdog.enrichment-result.v1",
                "merge_proposals": [
                    {
                        "field": "notes",
                        "value": "Public-web corroboration candidate: https://example.test/ada",
                        "source": "public_web",
                        "requires_review": True,
                    }
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    service = BusinessCardService(config)

    result = service.submit_review(
        job_id=job_id,
        run_id=run_id,
        reviewer="tester",
        action="approve_enrichment_merge",
        approved_enrichment_fields=["notes"],
    )
    reviewed = json.loads((artifact_dir / "reviewed_contact.json").read_text(encoding="utf-8"))
    merge_review = json.loads((artifact_dir / "enrichment_merge_review.json").read_text(encoding="utf-8"))
    job = service.get_job(job_id, run_id=run_id)
    events = [
        json.loads(line)
        for line in (config.runs_dir / run_id / "events.jsonl").read_text(encoding="utf-8").splitlines()
    ]

    assert result["submission"]["approved_enrichment_fields"] == ["notes"]
    assert job["state"] == "ready_to_route"
    assert reviewed["observed"]["notes"]["source"] == "approved_enrichment"
    assert "Card note" in reviewed["flat"]["notes"]
    assert merge_review["applied"][0]["field"] == "notes"
    assert any(artifact["kind"] == "enrichment_merge_review" for artifact in job["artifacts"])
    assert any(event["event_type"] == "enrichment_merge_reviewed" for event in events)


def test_service_submit_review_resolves_duplicate_for_routing(tmp_path: Path) -> None:
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        routing_rules=[{"match": "email_domain", "value": "*", "sinks": ["google_contacts"]}],
    )
    run_id, job_id = make_recorded_run(config)
    artifact_dir = config.runs_dir / run_id / "artifacts" / job_id
    (artifact_dir / "duplicate_assessment.json").write_text(
        json.dumps(
            {
                "schema": "business-card-watchdog.duplicate-assessment.v1",
                "state": "strong_duplicate",
                "matches": [{"match_type": "email", "serialization_key": "email:ada@example.test"}],
                "reasons": ["email match"],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    service = BusinessCardService(config)

    result = service.submit_review(
        job_id=job_id,
        run_id=run_id,
        reviewer="tester",
        action="resolve_duplicate",
        duplicate_resolution={
            "decision": "merge_existing",
            "target_identity": "email:ada@example.test",
            "reason": "same contact",
        },
    )
    plan = service.plan_sinks_for_job(job_id=job_id, run_id=run_id)
    resolution = json.loads((artifact_dir / "duplicate_resolution.json").read_text(encoding="utf-8"))
    job = service.get_job(job_id, run_id=run_id)
    events = [
        json.loads(line)
        for line in (config.runs_dir / run_id / "events.jsonl").read_text(encoding="utf-8").splitlines()
    ]

    assert result["job"]["state"] == "ready_to_route"
    assert resolution["decision"] == "merge_existing"
    assert job["state"] == "ready_to_route"
    assert plan["plan"]["duplicate_resolution"]["decision"] == "merge_existing"
    assert any(artifact["kind"] == "duplicate_resolution" for artifact in job["artifacts"])
    assert any(event["event_type"] == "duplicate_resolved" for event in events)


def test_service_submit_review_resolves_duplicate_noop_as_cancelled(tmp_path: Path) -> None:
    config = AppConfig(config_path=tmp_path / "config.toml", data_dir=tmp_path / "data")
    run_id, job_id = make_recorded_run(config)
    artifact_dir = config.runs_dir / run_id / "artifacts" / job_id
    (artifact_dir / "duplicate_assessment.json").write_text(
        '{"schema": "business-card-watchdog.duplicate-assessment.v1", "state": "strong_duplicate"}\n',
        encoding="utf-8",
    )

    result = BusinessCardService(config).submit_review(
        job_id=job_id,
        run_id=run_id,
        reviewer="tester",
        action="resolve_duplicate",
        duplicate_resolution={"decision": "noop", "reason": "already imported"},
    )

    assert result["job"]["state"] == "cancelled"
    assert result["job"]["error"] == "duplicate resolved as no-op"


def test_service_get_missing_run_raises(tmp_path: Path) -> None:
    config = AppConfig(config_path=tmp_path / "config.toml", data_dir=tmp_path / "data")
    service = BusinessCardService(config)

    try:
        service.get_run("missing")
    except FileNotFoundError as exc:
        assert "run not found" in str(exc)
    else:
        raise AssertionError("expected FileNotFoundError")

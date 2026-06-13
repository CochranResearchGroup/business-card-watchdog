from __future__ import annotations

import json
from pathlib import Path

from business_card_watchdog.config import AppConfig, SinkConfig
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

    assert summary["run_id"] == run_id
    assert summary["needs_review_count"] == 1
    assert summary["artifact_counts"]["contact_spec"] == 1
    assert queue[0]["job_id"] == job_id
    assert queue[0]["artifact_kinds"] == ["contact_spec"]


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


def test_service_next_actions_recommends_sink_plan_after_lookup_plan(tmp_path: Path) -> None:
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

    assert payload["actions"][0]["action"] == "plan_sinks"


def test_service_next_actions_recommends_apply_preflight_after_sink_plan(tmp_path: Path) -> None:
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
    service.plan_sinks_for_job(job_id=job_id, run_id=run_id)

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
    service.plan_sinks_for_job(job_id=job_id, run_id=run_id)
    service.preflight_sink_apply(job_id=job_id, run_id=run_id)

    payload = service.next_actions(run_id=run_id)

    assert payload["actions"][0]["action"] == "decide_sink_apply"
    assert payload["actions"][0]["command"] == "sinks apply-decision"


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
    service.plan_sinks_for_job(job_id=job_id, run_id=run_id)
    service.preflight_sink_apply(job_id=job_id, run_id=run_id)
    service.decide_sink_apply(job_id=job_id, run_id=run_id, decision="approve", reviewer="tester")

    payload = service.next_actions(run_id=run_id)

    assert payload["actions"][0]["action"] == "await_apply_approval"
    assert payload["actions"][0]["command"] == "sinks apply --apply"


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

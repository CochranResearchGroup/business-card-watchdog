from __future__ import annotations

import json
from pathlib import Path

import pytest

from business_card_watchdog.config import AppConfig, EnrichmentConfig, EnrichmentProviderConfig, SinkConfig
from business_card_watchdog.contact import build_contact_candidate

from test_service import make_recorded_run


fastapi_testclient = pytest.importorskip("fastapi.testclient")
TestClient = fastapi_testclient.TestClient


def write_config(path: Path, data_dir: Path) -> None:
    path.write_text(f'data_dir = "{data_dir}"\n[watch]\ninputs = []\n', encoding="utf-8")


def test_api_health_status_runs_and_jobs(tmp_path: Path) -> None:
    from business_card_watchdog.api import create_app

    config_path = tmp_path / "config.toml"
    data_dir = tmp_path / "data"
    write_config(config_path, data_dir)
    run_id, job_id = make_recorded_run(AppConfig(config_path=config_path, data_dir=data_dir))
    client = TestClient(create_app(config_path))

    assert client.get("/health").json()["ok"] is True
    assert client.get("/status").json()["watch"]["inputs"] == []
    assert client.get("/runs").json()[0]["run_id"] == run_id
    assert client.get(f"/runs/{run_id}").json()["run_id"] == run_id
    assert client.get(f"/runs/{run_id}/summary").json()["needs_review_count"] == 1
    phase_report = client.get(f"/runs/{run_id}/phase-report").json()
    assert phase_report["schema"] == "business-card-watchdog.phase-report.v1"
    assert phase_report["phases"][2]["phase"] == "review"
    assert phase_report["phases"][2]["counts"]["blocked"] == 1
    assert client.get(f"/runs/{run_id}/jobs").json()[0]["job_id"] == job_id
    assert client.get(f"/jobs/{job_id}", params={"run_id": run_id}).json()["job_id"] == job_id
    assert client.get("/reviews", params={"run_id": run_id}).json()[0]["job_id"] == job_id
    filtered_reviews = client.get(
        "/reviews",
        params={"run_id": run_id, "next_action": "review_contact", "artifact_kind": "contact_spec"},
    ).json()
    assert [entry["job_id"] for entry in filtered_reviews] == [job_id]
    review_bundle = client.post(f"/runs/{run_id}/review-bundle").json()
    assert review_bundle["schema"] == "business-card-watchdog.review-bundle.v1"
    assert review_bundle["entries"][0]["job_id"] == job_id
    assert review_bundle["entries"][0]["next_action"]["action"] == "review_contact"
    assert review_bundle["groups"]["by_state"]["needs_review"]["count"] == 1
    assert review_bundle["decision_import_template"][0]["action"] == "approve_for_routing"
    review_html = client.post(f"/runs/{run_id}/review-html").json()
    assert review_html["schema"] == "business-card-watchdog.review-html.v1"
    assert "Business Card Review" in review_html["html"]
    review_import = client.post(
        f"/runs/{run_id}/review-decisions",
        json={
            "reviewer": "api-batch",
            "decisions": [
                {
                    "job_id": job_id,
                    "action": "approve_for_routing",
                    "field_corrections": {"full_name": "API Batch"},
                }
            ],
        },
    ).json()
    assert review_import["import"]["schema"] == "business-card-watchdog.review-decisions-import.v1"
    assert review_import["results"][0]["job_state"] == "ready_to_route"
    assert client.post("/enrichment/check", json={"mode": "api", "run_id": run_id}).json()["checks"][0]["status"] == "blocked"
    lookup = client.post(f"/jobs/{job_id}/sink-lookup-plan", params={"run_id": run_id}).json()
    assert lookup["lookup_plan"]["schema"] == "business-card-watchdog.sink-lookup-plan.v1"
    assert lookup["lookup_plan"]["network_calls_made"] == 0
    assert client.post(f"/jobs/{job_id}/sink-plan", params={"run_id": run_id}).json()["plan"]["schema"] == "business-card-watchdog.sink-plan.v1"
    preflight = client.post(f"/jobs/{job_id}/sink-apply-preflight", json={"run_id": run_id}).json()
    assert preflight["preflight"]["schema"] == "business-card-watchdog.sink-apply-preflight.v1"
    assert preflight["preflight"]["writes_attempted"] == 0
    apply_decision = client.post(
        f"/jobs/{job_id}/sink-apply-decision",
        json={"run_id": run_id, "decision": "approve", "reviewer": "api-test"},
    ).json()
    assert apply_decision["decision"]["schema"] == "business-card-watchdog.sink-apply-decision.v1"
    assert apply_decision["decision"]["network_calls_made"] == 0
    pilot_readiness = client.post(
        f"/jobs/{job_id}/sink-apply-pilot-readiness",
        json={"run_id": run_id},
    ).json()
    assert pilot_readiness["readiness"]["schema"] == "business-card-watchdog.sink-apply-pilot-readiness.v1"
    assert pilot_readiness["readiness"]["network_calls_made"] == 0
    apply_result = client.post(
        f"/jobs/{job_id}/sink-apply",
        json={"run_id": run_id, "apply": True, "simulate": True},
    ).json()
    assert apply_result["result"]["schema"] == "business-card-watchdog.sink-apply-result.v1"
    assert apply_result["result"]["state"] == "mock_applied"
    assert apply_result["result"]["writes_attempted"] == 0
    adapter_request = client.post(
        f"/jobs/{job_id}/sink-adapter-request",
        json={"run_id": run_id, "phase": "readback"},
    ).json()
    assert adapter_request["request"]["schema"] == "business-card-watchdog.sink-adapter-request.v1"
    assert adapter_request["request"]["phase"] == "readback"
    assert adapter_request["request"]["network_calls_made"] == 0
    lookup_result = client.post(
        f"/jobs/{job_id}/sink-lookup-result",
        json={
            "run_id": run_id,
            "matches_by_sink": {
                "google_contacts": [
                    {"resource_id": "people/c123", "confidence": 0.91, "basis": ["email"]}
                ]
            },
        },
    ).json()
    assert lookup_result["result"]["schema"] == "business-card-watchdog.sink-lookup-result.v1"
    assert lookup_result["result"]["state"] == "no_match"
    assert lookup_result["result"]["network_calls_made"] == 0
    downstream_duplicate = client.post(
        f"/jobs/{job_id}/downstream-duplicate-assessment",
        params={"run_id": run_id},
    ).json()
    assert downstream_duplicate["assessment"]["schema"] == "business-card-watchdog.duplicate-assessment.v1"
    assert downstream_duplicate["assessment"]["state"] == "no_match"
    artifact_dir = data_dir / "runs" / run_id / "artifacts" / job_id
    (artifact_dir / "enrichment_result.json").write_text(
        json.dumps(
            {
                "schema": "business-card-watchdog.enrichment-result.v1",
                "merge_proposals": [
                    {
                        "field": "notes",
                        "value": "Public-web corroboration candidate: https://example.test/api",
                        "source": "public_web",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    merge = client.post(
        f"/jobs/{job_id}/review",
        json={
            "run_id": run_id,
            "reviewer": "api-test",
            "action": "approve_enrichment_merge",
            "approved_enrichment_fields": ["notes"],
        },
    ).json()
    assert merge["submission"]["approved_enrichment_fields"] == ["notes"]
    (artifact_dir / "duplicate_assessment.json").write_text(
        '{"schema": "business-card-watchdog.duplicate-assessment.v1", "state": "possible_duplicate"}\n',
        encoding="utf-8",
    )
    duplicate = client.post(
        f"/jobs/{job_id}/review",
        json={
            "run_id": run_id,
            "reviewer": "api-test",
            "action": "resolve_duplicate",
            "duplicate_resolution": {"decision": "create_new", "reason": "confirmed separate contact"},
        },
    ).json()
    assert duplicate["submission"]["duplicate_resolution"]["decision"] == "create_new"
    review = client.post(
        f"/jobs/{job_id}/review",
        json={
            "run_id": run_id,
            "reviewer": "api-test",
            "action": "approve_for_routing",
            "field_corrections": {"full_name": "API Fixture"},
            "crop_selection": {"crop_id": "c01"},
        },
    ).json()
    assert review["job"]["state"] == "ready_to_route"
    run_next = client.post("/actions/run-next", json={"run_id": run_id, "limit": 2}).json()
    assert run_next["executed_count"] >= 1
    assert run_next["executed"][0]["action"].startswith(("plan_", "prepare_", "record_", "assess_"))
    assert run_next["phase_report_before"]["schema"] == "business-card-watchdog.phase-report.v1"
    assert run_next["phase_report_after"]["schema"] == "business-card-watchdog.phase-report.v1"


def test_api_sink_readback_pilot_writes_zero_write_artifact(tmp_path: Path) -> None:
    from business_card_watchdog.api import create_app

    config_path = tmp_path / "config.toml"
    data_dir = tmp_path / "data"
    config_path.write_text(
        f'data_dir = "{data_dir}"\n'
        "[watch]\ninputs = []\n"
        "[sink]\ndry_run = true\ngoogle_contacts = true\n"
        "[routing]\nrules = [{ match = \"email_domain\", value = \"*\", sinks = [\"google_contacts\"] }]\n",
        encoding="utf-8",
    )
    run_id, job_id = make_recorded_run(
        AppConfig(
            config_path=config_path,
            data_dir=data_dir,
            sink=SinkConfig(google_contacts=True, dry_run=True),
            routing_rules=[{"match": "email_domain", "value": "*", "sinks": ["google_contacts"]}],
        )
    )
    client = TestClient(create_app(config_path))

    client.post(
        f"/runs/{run_id}/review-decisions",
        json={
            "reviewer": "api-batch",
            "decisions": [
                {
                    "job_id": job_id,
                    "action": "approve_for_routing",
                    "field_corrections": {"full_name": "API Batch", "email": "api@example.test"},
                }
            ],
        },
    )
    client.post(f"/jobs/{job_id}/sink-plan", params={"run_id": run_id})
    client.post(f"/jobs/{job_id}/sink-apply-preflight", json={"run_id": run_id})
    client.post(
        f"/jobs/{job_id}/sink-apply-decision",
        json={"run_id": run_id, "decision": "approve", "reviewer": "api-test"},
    )
    client.post(f"/jobs/{job_id}/sink-apply-pilot-readiness", json={"run_id": run_id})
    write_pilot = client.post(
        f"/jobs/{job_id}/sink-write-pilot",
        json={"run_id": run_id, "sink": "google_contacts", "approved_by": "api-test"},
    ).json()
    assert write_pilot["pilot"]["schema"] == "business-card-watchdog.sink-write-pilot.v1"
    assert write_pilot["pilot"]["writes_attempted"] == 0
    assert write_pilot["result"]["state"] == "mock_applied"
    client.post(f"/jobs/{job_id}/sink-adapter-request", json={"run_id": run_id, "phase": "readback"})
    readback_pilot = client.post(
        f"/jobs/{job_id}/sink-readback-pilot",
        json={"run_id": run_id, "sink": "google_contacts", "approved_by": "api-test"},
    ).json()

    assert readback_pilot["pilot"]["schema"] == "business-card-watchdog.sink-readback-pilot.v1"
    assert readback_pilot["pilot"]["state"] == "verified"
    assert readback_pilot["pilot"]["writes_attempted"] == 0
    assert readback_pilot["pilot"]["network_calls_made"] == 0
    report = client.post(f"/jobs/{job_id}/sink-apply-pilot-report", json={"run_id": run_id}).json()
    assert report["report"]["schema"] == "business-card-watchdog.sink-apply-pilot-report.v1"
    assert report["report"]["state"] == "complete"
    assert report["report"]["writes_attempted"] == 0


def test_api_enrichment_request_accepts_paid_provider_results(tmp_path: Path) -> None:
    from business_card_watchdog.api import create_app

    config_path = tmp_path / "config.toml"
    data_dir = tmp_path / "data"
    keys_path = tmp_path / "API-keys.env"
    keys_path.write_text("APOLLO_API_KEY=secret-value-not-printed\n", encoding="utf-8")
    config_path.write_text(
        f'data_dir = "{data_dir}"\n'
        "[watch]\ninputs = []\n"
        "[enrichment]\nenabled = true\nallow_paid_api = true\n"
        f'api_keys_env = "{keys_path}"\n'
        "[enrichment.providers.apollo]\nenabled = true\napi_key_env = \"APOLLO_API_KEY\"\n",
        encoding="utf-8",
    )
    config = AppConfig(
        config_path=config_path,
        data_dir=data_dir,
        enrichment=EnrichmentConfig(
            enabled=True,
            allow_paid_api=True,
            api_keys_env=keys_path,
            apollo=EnrichmentProviderConfig(enabled=True),
        ),
    )
    run_id, job_id = make_recorded_run(config)
    artifact_dir = data_dir / "runs" / run_id / "artifacts" / job_id
    (artifact_dir / "contact_candidate.json").write_text(
        json.dumps(
            build_contact_candidate(
                {
                    "full_name": "Ada Lovelace",
                    "organization": "Example Labs",
                    "email": "ada@example.test",
                }
            )
        )
        + "\n",
        encoding="utf-8",
    )
    client = TestClient(create_app(config_path))

    payload = client.post(
        f"/jobs/{job_id}/enrichment",
        json={
            "run_id": run_id,
            "mode": "api",
            "allow_paid_enrichment": True,
            "provider_results": [
                {
                    "person": {
                        "name": "Ada Lovelace",
                        "email": "ada@example.test",
                        "title": "Principal",
                    },
                    "organization": {"name": "Example Labs"},
                }
            ],
        },
    ).json()

    assert payload["status"] == "ok"
    assert payload["provider_result"]["schema"] == "business-card-watchdog.enrichment-provider-result.v1"
    assert payload["provider_result"]["network_calls_made"] == 0
    handoff = client.post(
        f"/jobs/{job_id}/enrichment/provider-handoff",
        json={"run_id": run_id},
    ).json()
    assert handoff["handoff"]["schema"] == "business-card-watchdog.enrichment-provider-handoff.v1"
    assert handoff["handoff"]["paid_api_calls_attempted"] == 0
    assert "secret" not in json.dumps(handoff)

    result = client.post(
        f"/jobs/{job_id}/enrichment/provider-results",
        json={
            "run_id": run_id,
            "provider": "apollo",
            "submitted_by": "api-agent",
            "results": [
                {
                    "person": {
                        "name": "Ada Lovelace",
                        "email": "ada@example.test",
                        "title": "Principal",
                    },
                    "organization": {"name": "Example Labs"},
                }
            ],
        },
    ).json()
    assert result["provider_result"]["schema"] == "business-card-watchdog.enrichment-provider-result.v1"
    assert result["provider_result"]["submitted_by"] == "api-agent"
    assert result["provider_result"]["paid_api_calls_attempted"] == 0
    assert client.post("/sinks/check").json()["dry_run"] is True
    assert client.get("/watch/status").json()["seen_count"] == 0


def test_api_executes_sink_lookup_pilot_with_mocked_matches(tmp_path: Path) -> None:
    from business_card_watchdog.api import create_app

    config_path = tmp_path / "config.toml"
    data_dir = tmp_path / "data"
    config_path.write_text(
        f'data_dir = "{data_dir}"\n'
        "[watch]\ninputs = []\n"
        "[sink]\ndry_run = true\ngoogle_contacts = true\n",
        encoding="utf-8",
    )
    config = AppConfig(
        config_path=config_path,
        data_dir=data_dir,
        sink=SinkConfig(google_contacts=True, dry_run=True),
        routing_rules=[{"match": "email_domain", "value": "*", "sinks": ["google_contacts"]}],
    )
    run_id, job_id = make_recorded_run(config)
    client = TestClient(create_app(config_path))
    client.post(f"/jobs/{job_id}/sink-lookup-plan", params={"run_id": run_id})
    client.post(f"/jobs/{job_id}/sink-adapter-request", json={"run_id": run_id, "phase": "lookup"})

    payload = client.post(
        f"/jobs/{job_id}/sink-lookup-pilot",
        json={
            "run_id": run_id,
            "sink": "google_contacts",
            "approved_by": "api-operator",
            "matches": [
                {"resource_id": "people/c456", "confidence": 0.93, "basis": ["email"]}
            ],
        },
    ).json()

    assert payload["pilot"]["schema"] == "business-card-watchdog.sink-lookup-pilot.v1"
    assert payload["pilot"]["approved_by"] == "api-operator"
    assert payload["pilot"]["network_calls_made"] == 0
    assert payload["pilot"]["writes_attempted"] == 0
    assert payload["result"]["state"] == "possible_duplicate"


def test_api_records_public_web_enrichment_results(tmp_path: Path) -> None:
    from business_card_watchdog.api import create_app

    config_path = tmp_path / "config.toml"
    data_dir = tmp_path / "data"
    config_path.write_text(
        f'data_dir = "{data_dir}"\n'
        "[watch]\ninputs = []\n"
        "[enrichment]\nenabled = true\n",
        encoding="utf-8",
    )
    config = AppConfig(
        config_path=config_path,
        data_dir=data_dir,
        enrichment=EnrichmentConfig(enabled=True),
    )
    run_id, job_id = make_recorded_run(config)
    artifact_dir = data_dir / "runs" / run_id / "artifacts" / job_id
    (artifact_dir / "contact_candidate.json").write_text(
        json.dumps(
            build_contact_candidate(
                {
                    "full_name": "Ada Lovelace",
                    "organization": "Example Labs",
                    "email": "ada@example.test",
                }
            )
        )
        + "\n",
        encoding="utf-8",
    )
    client = TestClient(create_app(config_path))
    request = client.post(
        f"/jobs/{job_id}/enrichment",
        json={"run_id": run_id, "mode": "public_web", "requested_by": "api-test"},
    ).json()
    assert request["public_web_request"]["schema"] == "business-card-watchdog.enrichment-public-web-request.v1"

    handoff = client.post(
        f"/jobs/{job_id}/enrichment/public-web-handoff",
        json={"run_id": run_id},
    ).json()
    assert handoff["handoff"]["schema"] == "business-card-watchdog.enrichment-public-web-search-handoff.v1"
    assert handoff["handoff"]["network_calls_made"] == 0
    assert handoff["handoff"]["result_import"]["api"] == f"POST /jobs/{job_id}/enrichment/public-web-results"

    payload = client.post(
        f"/jobs/{job_id}/enrichment/public-web-results",
        json={
            "run_id": run_id,
            "searched_by": "api-search",
            "results": [
                {
                    "title": "Ada Lovelace - Example Labs",
                    "url": "https://example.test/team/ada",
                    "snippet": "Contact Ada at ada@example.test",
                }
            ],
        },
    ).json()

    assert payload["public_web_result"]["schema"] == "business-card-watchdog.enrichment-public-web-result.v1"
    assert payload["public_web_result"]["searched_by"] == "api-search"
    assert payload["public_web_result"]["network_calls_made"] == 0
    assert payload["result"]["schema"] == "business-card-watchdog.enrichment-result.v1"

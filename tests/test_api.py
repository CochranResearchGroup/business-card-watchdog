from __future__ import annotations

import json
from pathlib import Path

import pytest

from business_card_watchdog.config import AppConfig

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
    assert client.get(f"/runs/{run_id}/jobs").json()[0]["job_id"] == job_id
    assert client.get(f"/jobs/{job_id}", params={"run_id": run_id}).json()["job_id"] == job_id
    assert client.get("/reviews", params={"run_id": run_id}).json()[0]["job_id"] == job_id
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
    assert client.post("/sinks/check").json()["dry_run"] is True
    assert client.get("/watch/status").json()["seen_count"] == 0

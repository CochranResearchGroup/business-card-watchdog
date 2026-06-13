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
    assert client.post(f"/jobs/{job_id}/sink-plan", params={"run_id": run_id}).json()["plan"]["schema"] == "business-card-watchdog.sink-plan.v1"
    preflight = client.post(f"/jobs/{job_id}/sink-apply-preflight", json={"run_id": run_id}).json()
    assert preflight["preflight"]["schema"] == "business-card-watchdog.sink-apply-preflight.v1"
    assert preflight["preflight"]["writes_attempted"] == 0
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

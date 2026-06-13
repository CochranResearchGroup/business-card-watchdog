from __future__ import annotations

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

from __future__ import annotations

import json
from pathlib import Path

from business_card_watchdog.cli import main
from business_card_watchdog.config import AppConfig
from business_card_watchdog.service_ops import service_unit_path

from test_service import make_recorded_run


def write_config(path: Path, data_dir: Path) -> None:
    path.write_text(f'data_dir = "{data_dir}"\n[watch]\ninputs = []\n', encoding="utf-8")


def test_cli_runs_and_jobs_use_recorded_runtime_state(
    tmp_path: Path, capsys
) -> None:
    config_path = tmp_path / "config.toml"
    data_dir = tmp_path / "data"
    write_config(config_path, data_dir)
    run_id, job_id = make_recorded_run(AppConfig(config_path=config_path, data_dir=data_dir))

    assert main(["--config", str(config_path), "runs", "list", "--json"]) == 0
    runs = json.loads(capsys.readouterr().out)
    assert runs[0]["run_id"] == run_id

    assert main(["--config", str(config_path), "jobs", "show", job_id, "--run-id", run_id, "--json"]) == 0
    job = json.loads(capsys.readouterr().out)
    assert job["job_id"] == job_id
    assert job["artifacts"][0]["kind"] == "contact_spec"


def test_cli_jobs_review_records_submission(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "config.toml"
    data_dir = tmp_path / "data"
    write_config(config_path, data_dir)
    run_id, job_id = make_recorded_run(AppConfig(config_path=config_path, data_dir=data_dir))

    assert (
        main(
            [
                "--config",
                str(config_path),
                "jobs",
                "review",
                job_id,
                "--run-id",
                run_id,
                "--reviewer",
                "cli-test",
                "--action",
                "approve_for_routing",
                "--field-corrections-json",
                '{"full_name": "CLI Fixture"}',
                "--crop-selection-json",
                '{"crop_id": "c01"}',
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["job"]["state"] == "ready_to_route"
    assert payload["submission"]["reviewer"] == "cli-test"


def test_cli_sinks_check_is_dry_run_and_non_mutating(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "config.toml"
    write_config(config_path, tmp_path / "data")

    assert main(["--config", str(config_path), "sinks", "check", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["dry_run"] is True
    assert {sink["status"] for sink in payload["sinks"]} == {"ready"}


def test_cli_enrichment_check_blocks_when_not_enabled(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "config.toml"
    write_config(config_path, tmp_path / "data")

    assert main(["--config", str(config_path), "enrichment", "check", "--mode", "api", "--json"]) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["checks"][0]["status"] == "blocked"
    assert "disabled" in payload["checks"][0]["reason"]


def test_cli_doctor_reports_user_scope_checks(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "config.toml"
    write_config(config_path, tmp_path / "data")

    assert main(["--config", str(config_path), "doctor", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert any(check["name"] == "runs_dir" for check in payload["checks"])


def test_cli_service_install_status_uninstall_user_scope(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg-config"))
    config_path = tmp_path / "config.toml"
    write_config(config_path, tmp_path / "data")

    assert main(["--config", str(config_path), "service", "install", "--json"]) == 0
    installed = json.loads(capsys.readouterr().out)
    assert installed["installed"] is True
    assert Path(installed["unit_path"]) == service_unit_path()
    assert service_unit_path().read_text(encoding="utf-8").count("ExecStart=") == 1

    assert main(["--config", str(config_path), "service", "status", "--json"]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["installed"] is True

    assert main(["--config", str(config_path), "service", "uninstall", "--json"]) == 0
    uninstalled = json.loads(capsys.readouterr().out)
    assert uninstalled["installed"] is False

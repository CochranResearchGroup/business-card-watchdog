from __future__ import annotations

import json
from pathlib import Path

from business_card_watchdog.cli import build_parser, main
from business_card_watchdog.config import (
    AppConfig,
    EnrichmentConfig,
    EnrichmentProviderConfig,
    PrefilterConfig,
)
from business_card_watchdog.contact import build_contact_candidate
from business_card_watchdog.orchestrator import BatchOrchestrator
from business_card_watchdog.service_ops import service_unit_path

from synthetic_fixtures import SyntheticSkillAdapter, latest_jobs_by_id, write_synthetic_image
from test_service import make_recorded_run


def write_config(path: Path, data_dir: Path) -> None:
    path.write_text(f'data_dir = "{data_dir}"\n[watch]\ninputs = []\n', encoding="utf-8")


def test_cli_has_mcp_stdio_command() -> None:
    args = build_parser().parse_args(["mcp-stdio"])

    assert args.command == "mcp-stdio"


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

    assert main(["--config", str(config_path), "runs", "summary", run_id, "--json"]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["needs_review_count"] == 1

    assert main(["--config", str(config_path), "jobs", "show", job_id, "--run-id", run_id, "--json"]) == 0
    job = json.loads(capsys.readouterr().out)
    assert job["job_id"] == job_id
    assert job["artifacts"][0]["kind"] == "contact_spec"

    assert main(["--config", str(config_path), "reviews", "list", "--run-id", run_id, "--json"]) == 0
    reviews = json.loads(capsys.readouterr().out)
    assert reviews[0]["job_id"] == job_id

    assert main(["--config", str(config_path), "reviews", "bundle", "--run-id", run_id, "--json"]) == 0
    bundle = json.loads(capsys.readouterr().out)
    assert bundle["schema"] == "business-card-watchdog.review-bundle.v1"
    assert bundle["entries"][0]["job_id"] == job_id
    assert bundle["entries"][0]["next_action"]["action"] == "review_contact"
    assert Path(bundle["review_bundle_path"]).exists()

    assert (
        main(
            [
                "--config",
                str(config_path),
                "mcp-call",
                "business_card_watchdog_next_actions",
                "--arguments-json",
                f'{{"run_id": "{run_id}"}}',
            ]
        )
        == 0
    )
    next_actions = json.loads(capsys.readouterr().out)
    assert next_actions["actions"][0]["action"] == "review_contact"


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

    assert (
        main(
            [
                "--config",
                str(config_path),
                "actions",
                "run-next",
                "--run-id",
                run_id,
                "--limit",
                "2",
                "--json",
            ]
        )
        == 0
    )
    actions = json.loads(capsys.readouterr().out)
    assert [item["action"] for item in actions["executed"]] == [
        "plan_sink_lookup",
        "prepare_sink_lookup_adapter",
    ]


def test_cli_jobs_review_supports_request_enrichment_action(tmp_path: Path, capsys) -> None:
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
                "--action",
                "request_enrichment",
                "--notes",
                "needs corroboration",
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["job"]["state"] == "needs_review"
    assert payload["submission"]["action"] == "request_enrichment"


def test_cli_jobs_review_approves_enrichment_merge(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "config.toml"
    data_dir = tmp_path / "data"
    write_config(config_path, data_dir)
    run_id, job_id = make_recorded_run(AppConfig(config_path=config_path, data_dir=data_dir))
    artifact_dir = data_dir / "runs" / run_id / "artifacts" / job_id
    (artifact_dir / "contact_candidate.json").write_text(
        json.dumps(build_contact_candidate({"full_name": "Ada Lovelace"}), indent=2),
        encoding="utf-8",
    )
    (artifact_dir / "enrichment_result.json").write_text(
        json.dumps(
            {
                "schema": "business-card-watchdog.enrichment-result.v1",
                "merge_proposals": [
                    {
                        "field": "notes",
                        "value": "Public-web corroboration candidate: https://example.test/ada",
                        "source": "public_web",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

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
                "--action",
                "approve_enrichment_merge",
                "--approved-enrichment-fields-json",
                '["notes"]',
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["job"]["state"] == "ready_to_route"
    assert payload["submission"]["approved_enrichment_fields"] == ["notes"]


def test_cli_jobs_review_resolves_duplicate(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "config.toml"
    data_dir = tmp_path / "data"
    write_config(config_path, data_dir)
    run_id, job_id = make_recorded_run(AppConfig(config_path=config_path, data_dir=data_dir))
    artifact_dir = data_dir / "runs" / run_id / "artifacts" / job_id
    (artifact_dir / "duplicate_assessment.json").write_text(
        '{"schema": "business-card-watchdog.duplicate-assessment.v1", "state": "strong_duplicate"}\n',
        encoding="utf-8",
    )

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
                "--action",
                "resolve_duplicate",
                "--duplicate-resolution-json",
                '{"decision": "create_new", "reason": "operator confirmed separate person"}',
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["job"]["state"] == "ready_to_route"
    assert payload["submission"]["duplicate_resolution"]["decision"] == "create_new"


def test_cli_sinks_check_is_dry_run_and_non_mutating(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "config.toml"
    write_config(config_path, tmp_path / "data")

    assert main(["--config", str(config_path), "sinks", "check", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["dry_run"] is True
    assert {sink["status"] for sink in payload["sinks"]} == {"ready"}


def test_cli_sinks_plan_writes_artifact(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "config.toml"
    data_dir = tmp_path / "data"
    config_path.write_text(
        f'data_dir = "{data_dir}"\n'
        "[watch]\ninputs = []\n"
        "[sink]\ndry_run = true\ngoogle_contacts = true\nodoo = true\n"
        "[routing]\nrules = [{ match = \"email_domain\", value = \"*\", sinks = [\"google_contacts\"] }]\n",
        encoding="utf-8",
    )
    run_id, job_id = make_recorded_run(AppConfig(config_path=config_path, data_dir=data_dir))

    assert main(["--config", str(config_path), "sinks", "plan", job_id, "--run-id", run_id, "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["plan"]["schema"] == "business-card-watchdog.sink-plan.v1"
    assert payload["plan"]["state"] == "dry_run"


def test_cli_sinks_lookup_plan_writes_zero_network_artifact(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "config.toml"
    data_dir = tmp_path / "data"
    config_path.write_text(
        f'data_dir = "{data_dir}"\n'
        "[watch]\ninputs = []\n"
        "[sink]\ndry_run = true\ngoogle_contacts = true\n"
        "[routing]\nrules = [{ match = \"email_domain\", value = \"*\", sinks = [\"google_contacts\"] }]\n",
        encoding="utf-8",
    )
    run_id, job_id = make_recorded_run(AppConfig(config_path=config_path, data_dir=data_dir))

    assert main(["--config", str(config_path), "sinks", "lookup-plan", job_id, "--run-id", run_id, "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["lookup_plan"]["schema"] == "business-card-watchdog.sink-lookup-plan.v1"
    assert payload["lookup_plan"]["network_calls_made"] == 0
    assert payload["lookup_plan"]["lookups"][0]["sink"] == "google_contacts"


def test_cli_sinks_apply_preflight_is_zero_write(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "config.toml"
    data_dir = tmp_path / "data"
    config_path.write_text(
        f'data_dir = "{data_dir}"\n'
        "[watch]\ninputs = []\n"
        "[sink]\ndry_run = true\ngoogle_contacts = true\n",
        encoding="utf-8",
    )
    run_id, job_id = make_recorded_run(AppConfig(config_path=config_path, data_dir=data_dir))

    assert main(["--config", str(config_path), "sinks", "apply-preflight", job_id, "--run-id", run_id, "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["preflight"]["schema"] == "business-card-watchdog.sink-apply-preflight.v1"
    assert payload["preflight"]["state"] == "preview"
    assert payload["preflight"]["writes_attempted"] == 0

    assert (
        main(
            [
                "--config",
                str(config_path),
                "sinks",
                "apply-preflight",
                job_id,
                "--run-id",
                run_id,
                "--apply",
                "--json",
            ]
        )
        == 0
    )
    blocked = json.loads(capsys.readouterr().out)
    assert blocked["preflight"]["state"] == "blocked"


def test_cli_sinks_apply_decision_writes_zero_write_artifact(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "config.toml"
    data_dir = tmp_path / "data"
    config_path.write_text(
        f'data_dir = "{data_dir}"\n'
        "[watch]\ninputs = []\n"
        "[sink]\ndry_run = true\ngoogle_contacts = true\n",
        encoding="utf-8",
    )
    run_id, job_id = make_recorded_run(AppConfig(config_path=config_path, data_dir=data_dir))

    assert (
        main(
            [
                "--config",
                str(config_path),
                "sinks",
                "apply-decision",
                job_id,
                "--run-id",
                run_id,
                "--decision",
                "approve",
                "--reviewer",
                "cli-test",
                "--reason",
                "pilot approved",
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["decision"]["schema"] == "business-card-watchdog.sink-apply-decision.v1"
    assert payload["decision"]["state"] == "approved_for_apply"
    assert payload["decision"]["writes_attempted"] == 0

    assert (
        main(
            [
                "--config",
                str(config_path),
                "sinks",
                "apply",
                job_id,
                "--run-id",
                run_id,
                "--apply",
                "--simulate",
                "--json",
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    assert result["result"]["schema"] == "business-card-watchdog.sink-apply-result.v1"
    assert result["result"]["state"] == "mock_applied"
    assert result["result"]["writes_attempted"] == 0
    assert result["result"]["readback"][0]["simulated"] is True

    assert (
        main(
            [
                "--config",
                str(config_path),
                "sinks",
                "apply-pilot-readiness",
                job_id,
                "--run-id",
                run_id,
                "--json",
            ]
        )
        == 0
    )
    readiness = json.loads(capsys.readouterr().out)
    assert readiness["readiness"]["schema"] == "business-card-watchdog.sink-apply-pilot-readiness.v1"
    assert readiness["readiness"]["writes_attempted"] == 0


def test_cli_sinks_adapter_request_writes_blocked_contract(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "config.toml"
    data_dir = tmp_path / "data"
    config_path.write_text(
        f'data_dir = "{data_dir}"\n'
        "[watch]\ninputs = []\n"
        "[sink]\ndry_run = true\ngoogle_contacts = true\n",
        encoding="utf-8",
    )
    run_id, job_id = make_recorded_run(AppConfig(config_path=config_path, data_dir=data_dir))

    assert (
        main(
            [
                "--config",
                str(config_path),
                "sinks",
                "adapter-request",
                job_id,
                "--run-id",
                run_id,
                "--phase",
                "lookup",
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["request"]["schema"] == "business-card-watchdog.sink-adapter-request.v1"
    assert payload["request"]["phase"] == "lookup"
    assert payload["request"]["network_calls_made"] == 0
    assert payload["request"]["requests"][0]["status"] == "blocked"


def test_cli_sinks_lookup_result_writes_zero_network_artifact(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "config.toml"
    data_dir = tmp_path / "data"
    config_path.write_text(
        f'data_dir = "{data_dir}"\n'
        "[watch]\ninputs = []\n"
        "[sink]\ndry_run = true\ngoogle_contacts = true\n",
        encoding="utf-8",
    )
    run_id, job_id = make_recorded_run(AppConfig(config_path=config_path, data_dir=data_dir))

    assert (
        main(
            [
                "--config",
                str(config_path),
                "sinks",
                "lookup-result",
                job_id,
                "--run-id",
                run_id,
                "--matches-by-sink-json",
                '{"google_contacts": [{"resource_id": "people/c123", "confidence": 0.91, "basis": ["email"]}]}',
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["result"]["schema"] == "business-card-watchdog.sink-lookup-result.v1"
    assert payload["result"]["state"] == "possible_duplicate"
    assert payload["result"]["network_calls_made"] == 0
    assert payload["result"]["match_count"] == 1

    assert (
        main(
            [
                "--config",
                str(config_path),
                "sinks",
                "assess-duplicates",
                job_id,
                "--run-id",
                run_id,
                "--json",
            ]
        )
        == 0
    )
    assessment = json.loads(capsys.readouterr().out)
    assert assessment["assessment"]["schema"] == "business-card-watchdog.duplicate-assessment.v1"
    assert assessment["assessment"]["state"] == "strong_duplicate"
    assert assessment["job"]["state"] == "needs_review"


def test_cli_enrichment_check_blocks_when_not_enabled(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "config.toml"
    write_config(config_path, tmp_path / "data")

    assert main(["--config", str(config_path), "enrichment", "check", "--mode", "api", "--json"]) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["checks"][0]["status"] == "blocked"
    assert "disabled" in payload["checks"][0]["reason"]


def test_cli_enrichment_request_writes_public_web_artifacts(tmp_path: Path, monkeypatch, capsys) -> None:
    config_path = tmp_path / "config.toml"
    data_dir = tmp_path / "data"
    source_dir = tmp_path / "cards"
    write_synthetic_image(source_dir / "card.png")
    config_path.write_text(
        f'data_dir = "{data_dir}"\ncache_dir = "{tmp_path / "cache"}"\n'
        "[watch]\ninputs = []\n"
        "[enrichment]\nenabled = true\n",
        encoding="utf-8",
    )
    config = AppConfig(
        config_path=config_path,
        data_dir=data_dir,
        cache_dir=tmp_path / "cache",
        prefilter=PrefilterConfig(process_uncertain=True),
        enrichment=EnrichmentConfig(enabled=True),
    )
    orchestrator = BatchOrchestrator(config)
    monkeypatch.setattr(orchestrator, "adapter", SyntheticSkillAdapter())
    run_dir = orchestrator.process_source(str(source_dir), dry_run=True, workers=1)
    job = next(iter(latest_jobs_by_id(run_dir / "jobs.jsonl").values()))

    assert (
        main(
            [
                "--config",
                str(config_path),
                "enrichment",
                "request",
                job["job_id"],
                "--run-id",
                run_dir.name,
                "--public-web-results-json",
                '[{"title":"Fixture Labs","url":"https://example.test","snippet":"fixture@example.test"}]',
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["result"]["network_calls_made"] == 0

    assert (
        main(
            [
                "--config",
                str(config_path),
                "enrichment",
                "public-web-results",
                job["job_id"],
                "--run-id",
                run_dir.name,
                "--searched-by",
                "cli-search",
                "--results-json",
                '[{"title":"Fixture Labs","url":"https://example.test","snippet":"fixture@example.test"}]',
                "--json",
            ]
        )
        == 0
    )
    result_payload = json.loads(capsys.readouterr().out)
    assert result_payload["public_web_result"]["schema"] == "business-card-watchdog.enrichment-public-web-result.v1"
    assert result_payload["public_web_result"]["searched_by"] == "cli-search"
    assert result_payload["public_web_result"]["network_calls_made"] == 0


def test_cli_enrichment_request_writes_paid_provider_request_without_call(tmp_path: Path, capsys) -> None:
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
    run_id, job_id = make_recorded_run(
        AppConfig(
            config_path=config_path,
            data_dir=data_dir,
            enrichment=EnrichmentConfig(
                enabled=True,
                allow_paid_api=True,
                api_keys_env=keys_path,
                apollo=EnrichmentProviderConfig(enabled=True),
            ),
        )
    )
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

    assert (
        main(
            [
                "--config",
                str(config_path),
                "enrichment",
                "request",
                job_id,
                "--run-id",
                run_id,
                "--mode",
                "api",
                "--allow-paid-enrichment",
                "--provider-results-json",
                '[{"person":{"name":"Ada Lovelace","email":"ada@example.test","title":"Principal"},"organization":{"name":"Example Labs"}}]',
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["provider_request"]["schema"] == "business-card-watchdog.enrichment-provider-request.v1"
    assert payload["provider_request"]["status"] == "prepared"
    assert payload["provider_request"]["network_calls_made"] == 0
    assert payload["provider_result"]["schema"] == "business-card-watchdog.enrichment-provider-result.v1"
    assert payload["provider_result"]["paid_api_calls_attempted"] == 0
    assert "secret" not in json.dumps(payload)


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

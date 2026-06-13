from pathlib import Path

from business_card_watchdog.config import AppConfig, EnrichmentConfig, EnrichmentProviderConfig, PrefilterConfig
from business_card_watchdog.enrichment import build_enrichment_request, check_enrichment_readiness
from business_card_watchdog.orchestrator import BatchOrchestrator
from business_card_watchdog.service import BusinessCardService

from synthetic_fixtures import SyntheticSkillAdapter, latest_jobs_by_id, read_jsonl, write_synthetic_image


def test_enrichment_defaults_to_no_requested_work(tmp_path: Path) -> None:
    config = AppConfig(config_path=tmp_path / "config.toml")

    payload = BusinessCardService(config).enrichment_readiness()

    assert payload["enabled"] is False
    assert payload["checks"][0]["status"] == "ready"
    assert payload["checks"][0]["reason"] == "enrichment not requested"


def test_public_web_enrichment_requires_enabled_config(tmp_path: Path) -> None:
    disabled = AppConfig(config_path=tmp_path / "config.toml")
    enabled = AppConfig(
        config_path=tmp_path / "config.toml",
        enrichment=EnrichmentConfig(enabled=True),
    )

    assert check_enrichment_readiness(disabled, mode="public_web")[0].status == "blocked"
    public_web = check_enrichment_readiness(enabled, mode="public_web")[0]
    assert public_web.status == "ready"
    assert public_web.cost_class == "operator_search"


def test_paid_api_enrichment_requires_config_flag_operator_flag_and_key_name(tmp_path: Path) -> None:
    keys_path = tmp_path / "API-keys.env"
    base = EnrichmentConfig(
        enabled=True,
        allow_paid_api=True,
        api_keys_env=keys_path,
        apollo=EnrichmentProviderConfig(enabled=True, api_key_env="APOLLO_API_KEY"),
    )
    config = AppConfig(config_path=tmp_path / "config.toml", enrichment=base)

    blocked_without_operator_flag = check_enrichment_readiness(config, mode="api")[0]
    assert blocked_without_operator_flag.status == "blocked"
    assert "explicit operator request" in blocked_without_operator_flag.reason

    missing_key = check_enrichment_readiness(config, mode="api", allow_paid_enrichment=True)[0]
    assert missing_key.status == "blocked"
    assert missing_key.missing_key == "APOLLO_API_KEY"

    keys_path.write_text("APOLLO_API_KEY=secret-value-not-printed\n", encoding="utf-8")
    ready = check_enrichment_readiness(config, mode="api", allow_paid_enrichment=True)[0]
    assert ready.status == "ready"
    assert ready.missing_key is None
    assert "secret" not in ready.to_dict()["reason"]


def test_public_web_request_builds_queries_from_contact_candidate() -> None:
    request = build_enrichment_request(
        {
            "schema": "business-card-watchdog.contact-candidate.v1",
            "normalized": {
                "full_name": {"value": "Ada Lovelace"},
                "organization": {"value": "Example Labs"},
                "email": {"value": "ada@example.test"},
            },
        },
        mode="public_web",
    )

    assert request["schema"] == "business-card-watchdog.enrichment-request.v1"
    assert request["queries"][0]["query"] == '"ada@example.test"'
    assert request["cost_gate"]["paid_api_requested"] is False


def test_service_request_enrichment_writes_request_and_fixture_result(tmp_path: Path, monkeypatch) -> None:
    source_dir = tmp_path / "synthetic-cards"
    write_synthetic_image(source_dir / "card.png")
    config = AppConfig(
        config_path=tmp_path / "config.toml",
        data_dir=tmp_path / "data",
        cache_dir=tmp_path / "cache",
        prefilter=PrefilterConfig(process_uncertain=True),
        enrichment=EnrichmentConfig(enabled=True),
    )
    orchestrator = BatchOrchestrator(config)
    monkeypatch.setattr(
        orchestrator,
        "adapter",
        SyntheticSkillAdapter(
            specs_by_stem={
                "card": {
                    "full_name": "Ada Lovelace",
                    "organization": "Example Labs",
                    "email": "ada@example.test",
                }
            }
        ),
    )
    run_dir = orchestrator.process_source(str(source_dir), dry_run=True, workers=1)
    job = next(iter(latest_jobs_by_id(run_dir / "jobs.jsonl").values()))

    payload = BusinessCardService(config).request_enrichment(
        job_id=job["job_id"],
        run_id=run_dir.name,
        mode="public_web",
        requested_by="tester",
        public_web_results=[
            {
                "title": "Ada Lovelace - Example Labs",
                "url": "https://example.test/team/ada",
                "snippet": "Contact Ada at ada@example.test",
            }
        ],
    )
    artifacts = read_jsonl(run_dir / "artifacts.jsonl")
    result_path = Path(payload["result_path"])

    assert payload["status"] == "ok"
    assert payload["result"]["network_calls_made"] == 0
    assert payload["result"]["results"][0]["score"] >= 75
    assert result_path.exists()
    assert any(artifact["kind"] == "enrichment_request" for artifact in artifacts)
    assert any(artifact["kind"] == "enrichment_result" for artifact in artifacts)

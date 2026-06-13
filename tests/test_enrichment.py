from pathlib import Path

from business_card_watchdog.config import AppConfig, EnrichmentConfig, EnrichmentProviderConfig
from business_card_watchdog.enrichment import check_enrichment_readiness
from business_card_watchdog.service import BusinessCardService


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

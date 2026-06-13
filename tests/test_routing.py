from pathlib import Path

from business_card_watchdog.config import AppConfig, SinkConfig
from business_card_watchdog.routing import decide_sinks


def test_no_enabled_sinks_is_review_only() -> None:
    decision = decide_sinks(AppConfig(config_path=Path("config.toml")), {"email": "a@example.com"})
    assert decision.sinks == []
    assert "no sinks" in decision.reason


def test_email_domain_rule_filters_enabled_sinks() -> None:
    config = AppConfig(
        config_path=Path("config.toml"),
        sink=SinkConfig(google_contacts=True, odoo=True, dry_run=True),
        routing_rules=[{"match": "email_domain", "value": "example.com", "sinks": ["odoo"]}],
    )
    decision = decide_sinks(config, {"email": "a@example.com"})
    assert decision.sinks == ["odoo"]


from pathlib import Path

from business_card_watchdog.config import AppConfig, SinkConfig
from business_card_watchdog.routing import decide_sinks


def test_no_enabled_sinks_is_review_only() -> None:
    decision = decide_sinks(AppConfig(config_path=Path("config.toml")), {"email": "a@example.com"})
    assert decision.sinks == []
    assert "no sinks" in decision.reason
    assert decision.metadata["route_explanation"]["schema"] == "business-card-watchdog.route-explanation.v1"
    assert decision.metadata["sink_eligibility"] == []


def test_email_domain_rule_filters_enabled_sinks() -> None:
    config = AppConfig(
        config_path=Path("config.toml"),
        sink=SinkConfig(google_contacts=True, odoo=True, dry_run=True),
        routing_rules=[{"match": "email_domain", "value": "example.com", "sinks": ["odoo"]}],
    )
    decision = decide_sinks(config, {"email": "a@example.com"})
    assert decision.sinks == ["odoo"]
    assert decision.metadata["route_explanation"]["matched_rules"][0]["rule"]["value"] == "example.com"
    assert decision.metadata["sink_eligibility"][1]["route_eligible"] is True


def test_route_explanation_records_excluded_rules_and_source_folder_match() -> None:
    config = AppConfig(
        config_path=Path("config.toml"),
        sink=SinkConfig(google_contacts=True, odoo=True, dry_run=True),
        routing_rules=[
            {"match": "email_domain", "value": "example.org", "sinks": ["odoo"]},
            {"match": "source_folder", "value": "S22 Camera", "sinks": ["google_contacts"]},
        ],
    )

    decision = decide_sinks(
        config,
        {
            "email": "a@example.com",
            "_image_path": "/mnt/e/SyncThing/S22 Camera Phone Storage/card.jpg",
        },
    )

    explanation = decision.metadata["route_explanation"]
    assert decision.sinks == ["google_contacts"]
    assert explanation["excluded_rules"][0]["reason"] == "email_domain=example.com did not match example.org"
    assert explanation["matched_rules"][0]["reason"] == "matched source_folder=S22 Camera"


def test_route_policy_can_match_organization_and_duplicate_state() -> None:
    config = AppConfig(
        config_path=Path("config.toml"),
        sink=SinkConfig(google_contacts=True, odoo=True, dry_run=True),
        routing_rules=[
            {"match": "duplicate_state", "value": "strong_duplicate", "sinks": []},
            {"match": "organization", "value": "Fixture Labs", "sinks": ["google_contacts", "odoo"]},
        ],
    )

    blocked = decide_sinks(config, {"organization": "Fixture Labs", "_duplicate_state": "strong_duplicate"})
    routed = decide_sinks(config, {"organization": "Fixture Labs", "_duplicate_state": "no_match"})

    assert blocked.sinks == []
    assert blocked.reason == "matched duplicate_state=strong_duplicate"
    assert routed.sinks == ["google_contacts", "odoo"]
    assert routed.metadata["route_explanation"]["excluded_rules"][0]["reason"] == (
        "duplicate_state=no_match did not match strong_duplicate"
    )

from pathlib import Path

from business_card_watchdog.config import AppConfig, load_config, resolve_input_path


def test_resolve_fsr_alias() -> None:
    config = AppConfig(config_path=Path("config.toml"), path_aliases={"sync_phone": "/tmp/cards"})
    assert resolve_input_path("$fsr:sync_phone", config) == Path("/tmp/cards")


def test_resolve_fsr_raw_path() -> None:
    config = AppConfig(config_path=Path("config.toml"))
    assert str(resolve_input_path("$fsr E:\\SyncThing\\S22 Camera Phone Storage", config)).endswith(
        "E:\\SyncThing\\S22 Camera Phone Storage"
    )


def test_load_enrichment_config_nested_provider_tables(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    keys_path = tmp_path / "API-keys.env"
    config_path.write_text(
        f"""
[enrichment]
enabled = true
default_mode = "public_web"
allow_paid_api = true
api_keys_env = "{keys_path}"

[enrichment.providers.public_web]
enabled = false
max_queries_per_contact = 3

[enrichment.providers.apollo]
enabled = true
api_key_env = "CUSTOM_APOLLO_KEY"
base_url = "https://apollo.example.test"
""",
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.enrichment.enabled is True
    assert config.enrichment.default_mode == "public_web"
    assert config.enrichment.public_web_enabled is False
    assert config.enrichment.max_public_web_queries_per_contact == 3
    assert config.enrichment.apollo.enabled is True
    assert config.enrichment.apollo.api_key_env == "CUSTOM_APOLLO_KEY"


def test_load_normalization_default_country(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[normalization]
default_country = "GB"
""",
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.normalization.default_country == "GB"


def test_load_sink_apply_policy_flags(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        """
[sink]
dry_run = false
google_contacts = true
google_contacts_profile = "codex"
google_contacts_apply_enabled = true
odoo = true
odollo_tenant = "saber"
odoo_apply_enabled = false
""",
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.sink.dry_run is False
    assert config.sink.google_contacts is True
    assert config.sink.google_contacts_profile == "codex"
    assert config.sink.google_contacts_apply_enabled is True
    assert config.sink.odoo is True
    assert config.sink.odollo_tenant == "saber"
    assert config.sink.odoo_apply_enabled is False

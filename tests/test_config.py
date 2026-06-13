from pathlib import Path

from business_card_watchdog.config import AppConfig, resolve_input_path


def test_resolve_fsr_alias() -> None:
    config = AppConfig(config_path=Path("config.toml"), path_aliases={"sync_phone": "/tmp/cards"})
    assert resolve_input_path("$fsr:sync_phone", config) == Path("/tmp/cards")


def test_resolve_fsr_raw_path() -> None:
    config = AppConfig(config_path=Path("config.toml"))
    assert str(resolve_input_path("$fsr E:\\SyncThing\\S22 Camera Phone Storage", config)).endswith(
        "E:\\SyncThing\\S22 Camera Phone Storage"
    )


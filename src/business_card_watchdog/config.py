from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


APP_NAME = "business-card-watchdog"
DEFAULT_SKILL_ROOT = Path("/home/ecochran76/.codex/shared/skills/business-card-to-contact")


def config_home() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / APP_NAME


def data_home() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / APP_NAME


def cache_home() -> Path:
    return Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / APP_NAME


@dataclass(frozen=True)
class SinkConfig:
    google_contacts: bool = False
    odoo: bool = False
    dry_run: bool = True


@dataclass(frozen=True)
class WatchConfig:
    inputs: list[str] = field(default_factory=list)
    settle_seconds: float = 2.0
    status_scan_limit: int = 2000
    status_recursive: bool = False


@dataclass(frozen=True)
class PrefilterConfig:
    enabled: bool = True
    min_score: float = 0.55
    process_uncertain: bool = False


@dataclass(frozen=True)
class AppConfig:
    config_path: Path
    skill_root: Path = DEFAULT_SKILL_ROOT
    data_dir: Path = field(default_factory=data_home)
    cache_dir: Path = field(default_factory=cache_home)
    path_aliases: dict[str, str] = field(default_factory=dict)
    watch: WatchConfig = field(default_factory=WatchConfig)
    prefilter: PrefilterConfig = field(default_factory=PrefilterConfig)
    sink: SinkConfig = field(default_factory=SinkConfig)
    routing_rules: list[dict[str, Any]] = field(default_factory=list)

    @property
    def runs_dir(self) -> Path:
        return self.data_dir / "runs"

    @property
    def inbox_dir(self) -> Path:
        return self.data_dir / "inbox"

    @property
    def watch_inputs(self) -> list[str]:
        return self.watch.inputs

    @property
    def watch_dir(self) -> Path:
        return self.data_dir / "watch"


def default_config_path() -> Path:
    return config_home() / "config.toml"


def load_config(path: Path | None = None) -> AppConfig:
    config_path = path or default_config_path()
    if not config_path.exists():
        return AppConfig(config_path=config_path)

    with config_path.open("rb") as handle:
        raw = tomllib.load(handle)

    paths = raw.get("paths", {})
    sink = raw.get("sink", {})
    watch = raw.get("watch", {})
    prefilter = raw.get("prefilter", {})
    routing = raw.get("routing", {})

    return AppConfig(
        config_path=config_path,
        skill_root=Path(raw.get("skill_root", DEFAULT_SKILL_ROOT)).expanduser(),
        data_dir=Path(raw.get("data_dir", data_home())).expanduser(),
        cache_dir=Path(raw.get("cache_dir", cache_home())).expanduser(),
        path_aliases={str(key): str(value) for key, value in paths.items()},
        watch=WatchConfig(
            inputs=[str(item) for item in watch.get("inputs", [])],
            settle_seconds=float(watch.get("settle_seconds", 2.0)),
            status_scan_limit=int(watch.get("status_scan_limit", 2000)),
            status_recursive=bool(watch.get("status_recursive", False)),
        ),
        prefilter=PrefilterConfig(
            enabled=bool(prefilter.get("enabled", True)),
            min_score=float(prefilter.get("min_score", 0.55)),
            process_uncertain=bool(prefilter.get("process_uncertain", False)),
        ),
        sink=SinkConfig(
            google_contacts=bool(sink.get("google_contacts", False)),
            odoo=bool(sink.get("odoo", False)),
            dry_run=bool(sink.get("dry_run", True)),
        ),
        routing_rules=list(routing.get("rules", [])),
    )


def write_default_config(path: Path | None = None) -> Path:
    target = path or default_config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        return target
    target.write_text(
        """# Business Card Watchdog user config.
skill_root = "/home/ecochran76/.codex/shared/skills/business-card-to-contact"

[paths]
# WSL/Linux mount for the SyncThing phone-camera directory.
sync_phone = "/mnt/e/SyncThing/S22 Camera Phone Storage"

[watch]
inputs = ["$fsr:sync_phone"]
settle_seconds = 2.0
status_scan_limit = 2000
status_recursive = false

[prefilter]
enabled = true
min_score = 0.55
process_uncertain = false

[sink]
dry_run = true
google_contacts = false
odoo = false

[routing]
rules = [
  { match = "email_domain", value = "*", sinks = ["google_contacts"] }
]
""",
        encoding="utf-8",
    )
    return target


def ensure_runtime_dirs(config: AppConfig) -> None:
    for path in (config.data_dir, config.cache_dir, config.runs_dir, config.inbox_dir, config.watch_dir):
        path.mkdir(parents=True, exist_ok=True)


def resolve_input_path(raw_path: str, config: AppConfig) -> Path:
    if raw_path.startswith("$fsr:"):
        alias = raw_path.removeprefix("$fsr:")
        if alias not in config.path_aliases:
            raise KeyError(f"unknown $fsr alias: {alias}")
        raw_path = config.path_aliases[alias]
    elif raw_path.startswith("$fsr "):
        raw_path = raw_path.removeprefix("$fsr ").strip()
    return Path(raw_path).expanduser()

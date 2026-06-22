from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


APP_NAME = "business-card-watchdog"
DEFAULT_SKILL_ROOT = Path.home() / ".codex/shared/skills/business-card-to-contact"


def config_home() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / APP_NAME


def data_home() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / APP_NAME


def cache_home() -> Path:
    return Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / APP_NAME


@dataclass(frozen=True)
class SinkConfig:
    google_contacts: bool = False
    google_contacts_profile: str = ""
    odoo: bool = False
    odollo_tenant: str = ""
    dry_run: bool = True
    google_contacts_apply_enabled: bool = False
    odoo_apply_enabled: bool = False


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
class NormalizationConfig:
    default_country: str = "US"


@dataclass(frozen=True)
class EnrichmentProviderConfig:
    enabled: bool = False
    api_key_env: str = "APOLLO_API_KEY"
    base_url: str = "https://api.apollo.io"


@dataclass(frozen=True)
class EnrichmentConfig:
    enabled: bool = False
    default_mode: str = "none"
    allow_paid_api: bool = False
    api_keys_env: Path = field(default_factory=lambda: Path("~/credentials/API-keys.env"))
    public_web_enabled: bool = True
    max_public_web_queries_per_contact: int = 8
    max_public_web_queries_per_run: int = 200
    max_paid_provider_results_per_contact: int = 5
    max_paid_provider_results_per_run: int = 50
    apollo: EnrichmentProviderConfig = field(default_factory=EnrichmentProviderConfig)


@dataclass(frozen=True)
class AppConfig:
    config_path: Path
    skill_root: Path = DEFAULT_SKILL_ROOT
    data_dir: Path = field(default_factory=data_home)
    cache_dir: Path = field(default_factory=cache_home)
    path_aliases: dict[str, str] = field(default_factory=dict)
    watch: WatchConfig = field(default_factory=WatchConfig)
    prefilter: PrefilterConfig = field(default_factory=PrefilterConfig)
    normalization: NormalizationConfig = field(default_factory=NormalizationConfig)
    enrichment: EnrichmentConfig = field(default_factory=EnrichmentConfig)
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

    @property
    def contact_store_path(self) -> Path:
        return self.data_dir / "contacts" / "contacts.sqlite"


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
    normalization = raw.get("normalization", {})
    enrichment = raw.get("enrichment", {})
    enrichment_providers = enrichment.get("providers", {})
    public_web_provider = enrichment_providers.get("public_web", {})
    apollo_provider = enrichment_providers.get("apollo", {})
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
        normalization=NormalizationConfig(
            default_country=str(normalization.get("default_country", "US")),
        ),
        enrichment=EnrichmentConfig(
            enabled=bool(enrichment.get("enabled", False)),
            default_mode=str(enrichment.get("default_mode", "none")),
            allow_paid_api=bool(enrichment.get("allow_paid_api", False)),
            api_keys_env=Path(str(enrichment.get("api_keys_env", "~/credentials/API-keys.env"))).expanduser(),
            public_web_enabled=bool(public_web_provider.get("enabled", True)),
            max_public_web_queries_per_contact=int(public_web_provider.get("max_queries_per_contact", 8)),
            max_public_web_queries_per_run=int(enrichment.get("max_public_web_queries_per_run", 200)),
            max_paid_provider_results_per_contact=int(enrichment.get("max_paid_provider_results_per_contact", 5)),
            max_paid_provider_results_per_run=int(enrichment.get("max_paid_provider_results_per_run", 50)),
            apollo=EnrichmentProviderConfig(
                enabled=bool(apollo_provider.get("enabled", False)),
                api_key_env=str(apollo_provider.get("api_key_env", "APOLLO_API_KEY")),
                base_url=str(apollo_provider.get("base_url", "https://api.apollo.io")),
            ),
        ),
        sink=SinkConfig(
            google_contacts=bool(sink.get("google_contacts", False)),
            google_contacts_profile=str(sink.get("google_contacts_profile", "")),
            odoo=bool(sink.get("odoo", False)),
            odollo_tenant=str(sink.get("odollo_tenant", "")),
            dry_run=bool(sink.get("dry_run", True)),
            google_contacts_apply_enabled=bool(sink.get("google_contacts_apply_enabled", False)),
            odoo_apply_enabled=bool(sink.get("odoo_apply_enabled", False)),
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
skill_root = "~/.codex/shared/skills/business-card-to-contact"

[paths]
# Example WSL/Linux mount for a SyncThing phone-camera directory.
sync_phone = "/mnt/e/SyncThing/Phone Camera"

[watch]
inputs = ["$fsr:sync_phone"]
settle_seconds = 2.0
status_scan_limit = 2000
status_recursive = false

[prefilter]
enabled = true
min_score = 0.55
process_uncertain = false

[normalization]
default_country = "US"

[enrichment]
enabled = false
default_mode = "none"
allow_paid_api = false
api_keys_env = "~/credentials/API-keys.env"
max_public_web_queries_per_run = 200
max_paid_provider_results_per_contact = 5
max_paid_provider_results_per_run = 50

[enrichment.providers.public_web]
enabled = true
max_queries_per_contact = 8

[enrichment.providers.apollo]
enabled = false
api_key_env = "APOLLO_API_KEY"
base_url = "https://api.apollo.io"

[sink]
dry_run = true
google_contacts = false
google_contacts_profile = ""
google_contacts_apply_enabled = false
odoo = false
odollo_tenant = ""
odoo_apply_enabled = false

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

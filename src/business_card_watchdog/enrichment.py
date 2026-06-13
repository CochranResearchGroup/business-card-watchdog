from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from .config import AppConfig


EnrichmentMode = Literal["none", "public_web", "api", "all"]
EnrichmentReadinessStatus = Literal["ready", "blocked"]


@dataclass(frozen=True)
class EnrichmentReadiness:
    mode: str
    status: EnrichmentReadinessStatus
    reason: str
    cost_class: str = "none"
    provider: str | None = None
    missing_key: str | None = None

    @property
    def ready(self) -> bool:
        return self.status == "ready"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def check_enrichment_readiness(
    config: AppConfig,
    *,
    mode: str | None = None,
    allow_paid_enrichment: bool = False,
) -> list[EnrichmentReadiness]:
    requested = mode or config.enrichment.default_mode
    if requested == "none":
        return [
            EnrichmentReadiness(
                mode="none",
                status="ready",
                reason="enrichment not requested",
            )
        ]
    if requested not in {"public_web", "api", "all"}:
        return [
            EnrichmentReadiness(
                mode=str(requested),
                status="blocked",
                reason=f"unsupported enrichment mode: {requested}",
            )
        ]
    if not config.enrichment.enabled:
        return [
            EnrichmentReadiness(
                mode=requested,
                status="blocked",
                reason="enrichment is disabled in user config",
            )
        ]

    readiness: list[EnrichmentReadiness] = []
    if requested in {"public_web", "all"}:
        readiness.append(
            EnrichmentReadiness(
                mode="public_web",
                provider="public_web",
                status="ready" if config.enrichment.public_web_enabled else "blocked",
                reason="public-web enrichment is enabled"
                if config.enrichment.public_web_enabled
                else "public-web enrichment provider is disabled",
                cost_class="operator_search",
            )
        )
    if requested in {"api", "all"}:
        readiness.append(_apollo_readiness(config, allow_paid_enrichment=allow_paid_enrichment))
    return readiness


def _apollo_readiness(config: AppConfig, *, allow_paid_enrichment: bool) -> EnrichmentReadiness:
    provider = config.enrichment.apollo
    if not provider.enabled:
        return EnrichmentReadiness(
            mode="api",
            provider="apollo",
            status="blocked",
            reason="Apollo enrichment provider is disabled",
            cost_class="paid_api",
        )
    if not config.enrichment.allow_paid_api or not allow_paid_enrichment:
        return EnrichmentReadiness(
            mode="api",
            provider="apollo",
            status="blocked",
            reason="paid API enrichment requires config allow_paid_api and explicit operator request",
            cost_class="paid_api",
        )
    key_names = _present_env_keys(config.enrichment.api_keys_env)
    if provider.api_key_env not in key_names:
        return EnrichmentReadiness(
            mode="api",
            provider="apollo",
            status="blocked",
            reason="Apollo API key is not available",
            cost_class="paid_api",
            missing_key=provider.api_key_env,
        )
    return EnrichmentReadiness(
        mode="api",
        provider="apollo",
        status="ready",
        reason="Apollo API key name is present; no provider call was made",
        cost_class="paid_api",
    )


def _present_env_keys(path: Path) -> set[str]:
    target = path.expanduser()
    if not target.exists():
        return set()
    keys: set[str] = set()
    for line in target.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        if key.strip() and value.strip():
            keys.add(key.strip())
    return keys

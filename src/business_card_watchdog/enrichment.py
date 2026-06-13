from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote_plus, urlparse

from .config import AppConfig
from .contact import contact_candidate_to_spec


EnrichmentMode = Literal["none", "public_web", "api", "all"]
EnrichmentReadinessStatus = Literal["ready", "blocked"]
ENRICHMENT_REQUEST_SCHEMA = "business-card-watchdog.enrichment-request.v1"
ENRICHMENT_RESULT_SCHEMA = "business-card-watchdog.enrichment-result.v1"
ENRICHMENT_PROVIDER_REQUEST_SCHEMA = "business-card-watchdog.enrichment-provider-request.v1"
ENRICHMENT_PUBLIC_WEB_REQUEST_SCHEMA = "business-card-watchdog.enrichment-public-web-request.v1"


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


def build_enrichment_request(
    contact_candidate: dict[str, Any],
    *,
    mode: str,
    allow_paid_enrichment: bool = False,
    requested_by: str = "operator",
) -> dict[str, Any]:
    spec = contact_candidate_to_spec(contact_candidate)
    return {
        "schema": ENRICHMENT_REQUEST_SCHEMA,
        "mode": mode,
        "requested_by": requested_by,
        "allow_paid_enrichment": allow_paid_enrichment,
        "cost_gate": _cost_gate(mode, allow_paid_enrichment=allow_paid_enrichment),
        "queries": build_public_web_queries(spec) if mode in {"public_web", "all"} else [],
        "observed": {
            key: spec[key]
            for key in ("full_name", "organization", "email", "phone", "website")
            if spec.get(key)
        },
    }


def score_public_web_results(
    contact_candidate: dict[str, Any],
    *,
    results: list[dict[str, Any]],
) -> dict[str, Any]:
    spec = contact_candidate_to_spec(contact_candidate)
    scored = [_score_result(spec, result, index=index) for index, result in enumerate(results)]
    scored.sort(key=lambda row: int(row["score"]), reverse=True)
    return {
        "schema": ENRICHMENT_RESULT_SCHEMA,
        "provider": "public_web",
        "cost_class": "operator_search",
        "network_calls_made": 0,
        "results": scored,
        "merge_proposals": _merge_proposals(spec, scored),
    }


def build_public_web_search_request(
    config: AppConfig,
    contact_candidate: dict[str, Any],
    *,
    mode: str,
    requested_by: str,
    readiness: list[dict[str, Any]],
) -> dict[str, Any]:
    spec = contact_candidate_to_spec(contact_candidate)
    public_web_ready = next((check for check in readiness if check.get("provider") == "public_web"), {})
    queries = build_public_web_queries(
        spec,
        max_queries=config.enrichment.max_public_web_queries_per_contact,
    )
    observed = {
        key: spec[key]
        for key in ("full_name", "organization", "email", "phone", "website")
        if spec.get(key)
    }
    return {
        "schema": ENRICHMENT_PUBLIC_WEB_REQUEST_SCHEMA,
        "provider": "public_web",
        "mode": mode,
        "requested_by": requested_by,
        "status": "prepared" if public_web_ready.get("status") == "ready" else "blocked",
        "reason": public_web_ready.get("reason") or "public-web readiness was not evaluated",
        "cost_class": "operator_search",
        "network_calls_made": 0,
        "search_calls_attempted": 0,
        "max_queries": config.enrichment.max_public_web_queries_per_contact,
        "observed": observed,
        "queries": [
            {
                **query,
                "search_url": f"https://www.google.com/search?q={quote_plus(str(query.get('query') or ''))}",
            }
            for query in queries
        ],
        "instructions": [
            "Collect only public professional identity evidence relevant to the observed business card fields.",
            "Return title, url, snippet, and any observed matching fields; do not overwrite card-observed values without review.",
            "Record no paid API calls under this request.",
        ],
    }


def build_paid_api_provider_request(
    config: AppConfig,
    contact_candidate: dict[str, Any],
    *,
    mode: str,
    requested_by: str,
    allow_paid_enrichment: bool,
    readiness: list[dict[str, Any]],
) -> dict[str, Any]:
    spec = contact_candidate_to_spec(contact_candidate)
    apollo_ready = next((check for check in readiness if check.get("provider") == "apollo"), {})
    observed = {
        key: spec[key]
        for key in ("full_name", "organization", "email", "phone", "website")
        if spec.get(key)
    }
    return {
        "schema": ENRICHMENT_PROVIDER_REQUEST_SCHEMA,
        "provider": "apollo",
        "mode": mode,
        "requested_by": requested_by,
        "status": "prepared" if apollo_ready.get("status") == "ready" else "blocked",
        "reason": apollo_ready.get("reason") or "Apollo readiness was not evaluated",
        "cost_class": "paid_api",
        "allow_paid_enrichment": allow_paid_enrichment,
        "network_calls_made": 0,
        "paid_api_calls_attempted": 0,
        "api_key_env": config.enrichment.apollo.api_key_env,
        "api_key_available": apollo_ready.get("status") == "ready",
        "base_url": config.enrichment.apollo.base_url,
        "operation": "person_company_lookup",
        "observed": observed,
        "request_fields": {
            "email": observed.get("email", ""),
            "name": observed.get("full_name", ""),
            "organization_name": observed.get("organization", ""),
            "domain": _host(str(observed.get("website") or "")),
        },
    }


def build_public_web_queries(spec: dict[str, Any], *, max_queries: int = 8) -> list[dict[str, Any]]:
    queries: list[dict[str, Any]] = []
    email = str(spec.get("email") or "").strip().lower()
    phone = str(spec.get("phone") or "").strip()
    full_name = str(spec.get("full_name") or "").strip()
    organization = str(spec.get("organization") or "").strip()
    website = str(spec.get("website") or "").strip()
    if email:
        queries.append({"query": f'"{email}"', "purpose": "exact_email", "required": True})
    if phone:
        queries.append({"query": f'"{phone}"', "purpose": "exact_phone", "required": True})
    if full_name and organization:
        queries.append({"query": f'"{full_name}" "{organization}"', "purpose": "name_organization"})
    if full_name and website:
        queries.append({"query": f'"{full_name}" site:{_host(website)}', "purpose": "name_site"})
    if organization and website:
        queries.append({"query": f'"{organization}" site:{_host(website)}', "purpose": "organization_site"})
    return queries[:max_queries]


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


def _cost_gate(mode: str, *, allow_paid_enrichment: bool) -> dict[str, Any]:
    return {
        "paid_api_requested": mode in {"api", "all"},
        "paid_api_allowed": bool(allow_paid_enrichment),
        "can_call_paid_api": mode in {"api", "all"} and bool(allow_paid_enrichment),
    }


def _score_result(spec: dict[str, Any], result: dict[str, Any], *, index: int) -> dict[str, Any]:
    title = str(result.get("title") or result.get("name") or "").strip()
    url = str(result.get("url") or result.get("link") or "").strip()
    snippet = str(result.get("snippet") or result.get("description") or "").strip()
    text = " ".join([title, url, snippet]).casefold()
    score = 0
    signals: list[str] = []
    for field, points in (("email", 40), ("phone", 30), ("full_name", 20), ("organization", 15)):
        value = str(spec.get(field) or "").strip()
        if value and value.casefold() in text:
            score += points
            signals.append(field)
    website = str(spec.get("website") or "").strip()
    if website and _host(website) and _host(website) in _host(url):
        score += 15
        signals.append("website_host")
    return {
        "rank": index + 1,
        "score": score,
        "signals": signals,
        "title": title,
        "url": url,
        "snippet": snippet,
    }


def _merge_proposals(spec: dict[str, Any], scored: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not scored or int(scored[0].get("score") or 0) < 40:
        return []
    return [
        {
            "field": "notes",
            "value": f"Public-web corroboration candidate: {scored[0]['url']}",
            "source": "public_web",
            "requires_review": True,
        }
    ]


def _host(url: str) -> str:
    parsed = urlparse(url if "://" in url else f"https://{url}")
    host = parsed.netloc.lower()
    return host[4:] if host.startswith("www.") else host


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

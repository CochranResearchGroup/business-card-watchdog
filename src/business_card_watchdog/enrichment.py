from __future__ import annotations

import re
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
ENRICHMENT_PROVIDER_HANDOFF_SCHEMA = "business-card-watchdog.enrichment-provider-handoff.v1"
ENRICHMENT_PUBLIC_WEB_REQUEST_SCHEMA = "business-card-watchdog.enrichment-public-web-request.v1"
ENRICHMENT_PUBLIC_WEB_SEARCH_HANDOFF_SCHEMA = "business-card-watchdog.enrichment-public-web-search-handoff.v1"
ENRICHMENT_PUBLIC_WEB_RESULT_SCHEMA = "business-card-watchdog.enrichment-public-web-result.v1"
ENRICHMENT_PROVIDER_RESULT_SCHEMA = "business-card-watchdog.enrichment-provider-result.v1"
ODOLLO_REUSE_NOTE = "adapted_from_odollo_enrichment_patterns"
PHONE_DIGIT_RE = re.compile(r"\D+")
DIRECTORY_DOMAINS = {
    "apollo.io",
    "bbb.org",
    "facebook.com",
    "instagram.com",
    "linkedin.com",
    "manta.com",
    "peoplefinders.com",
    "truepeoplesearch.com",
    "twitter.com",
    "whitepages.com",
    "x.com",
    "yellowpages.com",
    "yelp.com",
    "youtube.com",
    "zoominfo.com",
}


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
        "reuse_note": ODOLLO_REUSE_NOTE,
        "network_calls_made": 0,
        "results": scored,
        "merge_proposals": _merge_proposals(spec, scored),
    }


def build_public_web_result_artifact(
    contact_candidate: dict[str, Any],
    *,
    public_web_request: dict[str, Any],
    results: list[dict[str, Any]],
    searched_by: str = "operator",
) -> dict[str, Any]:
    scored_result = score_public_web_results(contact_candidate, results=results)
    max_results = int(public_web_request.get("max_queries") or len(public_web_request.get("queries") or []))
    return {
        "schema": ENRICHMENT_PUBLIC_WEB_RESULT_SCHEMA,
        "result_schema": ENRICHMENT_RESULT_SCHEMA,
        "provider": "public_web",
        "mode": public_web_request.get("mode") or "public_web",
        "reuse_note": ODOLLO_REUSE_NOTE,
        "searched_by": searched_by,
        "source_request_schema": public_web_request.get("schema"),
        "source_request_status": public_web_request.get("status"),
        "source_query_count": len(public_web_request.get("queries") or []),
        "max_results": max_results,
        "submitted_result_count": len(results),
        "cost_class": "operator_search",
        "network_calls_made": 0,
        "search_calls_attempted": 0,
        "results": scored_result["results"],
        "merge_proposals": scored_result["merge_proposals"],
    }


def build_public_web_search_handoff(
    public_web_request: dict[str, Any],
    *,
    run_id: str,
    job_id: str,
) -> dict[str, Any]:
    queries = list(public_web_request.get("queries") or [])
    max_queries = int(public_web_request.get("max_queries") or len(queries))
    return {
        "schema": ENRICHMENT_PUBLIC_WEB_SEARCH_HANDOFF_SCHEMA,
        "source_request_schema": public_web_request.get("schema"),
        "source_request_status": public_web_request.get("status"),
        "run_id": run_id,
        "job_id": job_id,
        "provider": "public_web",
        "mode": public_web_request.get("mode") or "public_web",
        "cost_class": "operator_search",
        "network_calls_made": 0,
        "search_calls_attempted": 0,
        "max_queries": max_queries,
        "query_count": len(queries),
        "queries": queries,
        "instructions": [
            "Run only the listed public-web searches or narrower variants derived from the observed card fields.",
            "Collect title, url, snippet, and any observed matching fields for results that appear to describe the same person or organization.",
            "Do not use paid APIs or authenticated data sources for this handoff.",
            "Submit the collected rows through the result import surface for scoring and review.",
        ],
        "result_import": {
            "cli": (
                "bcw enrichment public-web-results "
                f"{job_id} --run-id {run_id} --results-json '<json-array>' --searched-by <operator> --json"
            ),
            "api": f"POST /jobs/{job_id}/enrichment/public-web-results",
            "mcp_tool": "business_card_watchdog_public_web_enrichment_results",
            "result_schema": ENRICHMENT_PUBLIC_WEB_RESULT_SCHEMA,
        },
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
        "reuse_note": ODOLLO_REUSE_NOTE,
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
        "reuse_note": ODOLLO_REUSE_NOTE,
        "requested_by": requested_by,
        "status": "prepared" if apollo_ready.get("status") == "ready" else "blocked",
        "reason": apollo_ready.get("reason") or "Apollo readiness was not evaluated",
        "cost_class": "paid_api",
        "allow_paid_enrichment": allow_paid_enrichment,
        "network_calls_made": 0,
        "paid_api_calls_attempted": 0,
        "max_results": config.enrichment.max_paid_provider_results_per_contact,
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


def build_paid_api_provider_handoff(
    provider_request: dict[str, Any],
    *,
    run_id: str,
    job_id: str,
) -> dict[str, Any]:
    provider = str(provider_request.get("provider") or "apollo")
    max_results = int(provider_request.get("max_results") or 0)
    return {
        "schema": ENRICHMENT_PROVIDER_HANDOFF_SCHEMA,
        "source_request_schema": provider_request.get("schema"),
        "source_request_status": provider_request.get("status"),
        "run_id": run_id,
        "job_id": job_id,
        "provider": provider,
        "mode": provider_request.get("mode") or "api",
        "reuse_note": ODOLLO_REUSE_NOTE,
        "operation": provider_request.get("operation") or "person_company_lookup",
        "cost_class": "paid_api",
        "allow_paid_enrichment": bool(provider_request.get("allow_paid_enrichment", False)),
        "network_calls_made": 0,
        "paid_api_calls_attempted": 0,
        "max_results": max_results,
        "api_key_env": provider_request.get("api_key_env"),
        "api_key_available": bool(provider_request.get("api_key_available", False)),
        "base_url": provider_request.get("base_url"),
        "request_fields": dict(provider_request.get("request_fields") or {}),
        "instructions": [
            "Use this handoff only after explicit operator approval for paid API enrichment.",
            "Load the API key from the named environment variable; never write or return the credential value.",
            "Submit at most max_results rows through the provider result import surface for scoring and review.",
            "Do not merge provider values directly into contacts without review approval.",
        ],
        "result_import": {
            "cli": (
                "bcw enrichment provider-results "
                f"{job_id} --run-id {run_id} --provider {provider} --results-json '<json-array>' --submitted-by <operator> --json"
            ),
            "api": f"POST /jobs/{job_id}/enrichment/provider-results",
            "mcp_tool": "business_card_watchdog_provider_enrichment_results",
            "result_schema": ENRICHMENT_PROVIDER_RESULT_SCHEMA,
        },
    }


def score_paid_api_provider_results(
    contact_candidate: dict[str, Any],
    *,
    provider: str,
    results: list[dict[str, Any]],
    max_results: int | None = None,
) -> dict[str, Any]:
    spec = contact_candidate_to_spec(contact_candidate)
    normalized = [_normalize_provider_result(spec, result, index=index) for index, result in enumerate(results)]
    normalized.sort(key=lambda row: int(row["score"]), reverse=True)
    return {
        "schema": ENRICHMENT_PROVIDER_RESULT_SCHEMA,
        "result_schema": ENRICHMENT_RESULT_SCHEMA,
        "provider": provider,
        "cost_class": "paid_api",
        "reuse_note": ODOLLO_REUSE_NOTE,
        "network_calls_made": 0,
        "paid_api_calls_attempted": 0,
        "max_results": max_results if max_results is not None else len(results),
        "submitted_result_count": len(results),
        "results": normalized,
        "merge_proposals": _provider_merge_proposals(provider, normalized),
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
        queries.extend(_public_web_phone_queries(phone, context_terms=[full_name, organization]))
    if full_name and organization:
        queries.append({"query": f'"{full_name}" "{organization}"', "purpose": "name_organization"})
    if full_name and website:
        queries.append({"query": f'"{full_name}" site:{_host(website)}', "purpose": "name_site"})
    if organization and website:
        queries.append({"query": f'"{organization}" site:{_host(website)}', "purpose": "organization_site"})
    return queries[:max_queries]


def _public_web_phone_queries(
    phone: str,
    *,
    context_terms: list[str],
    max_queries: int = 6,
) -> list[dict[str, Any]]:
    normalized = _normalize_phone_for_public_web(phone)
    queries = [
        {"query": f'"{form}"', "purpose": "exact_phone", "required": True}
        for form in normalized["search_forms"][:4]
    ]
    for term in [item.strip() for item in context_terms if item and item.strip()][:2]:
        queries.append(
            {
                "query": f'"{normalized["display"]}" "{term}"',
                "purpose": "phone_with_context",
                "required": False,
            }
        )
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
    phone = str(spec.get("phone") or "").strip()
    phone_hits = _phone_hits(text, phone) if phone else []
    for field, points in (("email", 40), ("phone", 30), ("full_name", 20), ("organization", 15)):
        value = str(spec.get(field) or "").strip()
        if field == "phone" and phone_hits:
            score += points
            signals.append(field)
        elif field != "phone" and value and value.casefold() in text:
            score += points
            signals.append(field)
    website = str(spec.get("website") or "").strip()
    if website and _host(website) and _host(website) in _host(url):
        score += 15
        signals.append("website_host")
    domain = _host(url)
    if domain and domain not in DIRECTORY_DOMAINS:
        score += 6
        signals.append("non_directory_source")
    return {
        "rank": index + 1,
        "score": score,
        "signals": signals,
        "title": title,
        "url": url,
        "domain": domain,
        "snippet": snippet,
        "phone_hits": phone_hits,
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


def _normalize_provider_result(spec: dict[str, Any], result: dict[str, Any], *, index: int) -> dict[str, Any]:
    person = _extract_apollo_person(result)
    organization = dict(result.get("organization") or result.get("account") or {})
    email = str(person.get("email") or result.get("email") or "").strip().lower()
    full_name = str(person.get("name") or result.get("name") or "").strip()
    title = str(person.get("title") or result.get("title") or "").strip()
    org_name = str(
        organization.get("name")
        or result.get("organization_name")
        or result.get("company")
        or ""
    ).strip()
    website = str(organization.get("website_url") or organization.get("domain") or result.get("website") or "").strip()
    score = 0
    signals: list[str] = []
    for field, value, points in (
        ("email", email, 45),
        ("full_name", full_name, 20),
        ("organization", org_name, 15),
    ):
        observed = str(spec.get(field) or "").strip()
        if observed and value and observed.casefold() == value.casefold():
            score += points
            signals.append(field)
    if title:
        score += 5
        signals.append("title_present")
    if website:
        score += 5
        signals.append("website_present")
    return {
        "rank": index + 1,
        "score": score,
        "signals": signals,
        "email": email,
        "full_name": full_name,
        "title": title,
        "organization": org_name,
        "website": website,
        "raw": result,
    }


def _provider_merge_proposals(provider: str, scored: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not scored or int(scored[0].get("score") or 0) < 45:
        return []
    top = scored[0]
    proposals: list[dict[str, Any]] = []
    for field in ("title", "organization", "website"):
        value = str(top.get(field) or "").strip()
        if value:
            proposals.append(
                {
                    "field": field,
                    "value": value,
                    "source": provider,
                    "requires_review": True,
                }
            )
    if top.get("email"):
        proposals.append(
            {
                "field": "notes",
                "value": f"{provider} corroboration candidate for {top['email']}",
                "source": provider,
                "requires_review": True,
            }
        )
    return proposals


def _extract_apollo_person(payload: dict[str, Any]) -> dict[str, Any]:
    for key in ("person", "contact", "data"):
        value = payload.get(key)
        if isinstance(value, dict) and (value.get("id") or value.get("email") or value.get("name")):
            return dict(value)
    for key in ("people", "contacts"):
        value = payload.get(key)
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict) and (item.get("id") or item.get("email") or item.get("name")):
                    return dict(item)
    return dict(payload)


def _normalize_phone_for_public_web(phone: str, *, default_country_code: str = "1") -> dict[str, Any]:
    digits = PHONE_DIGIT_RE.sub("", phone or "")
    if len(digits) == 10:
        e164 = f"+{default_country_code}{digits}"
        national = digits
    elif len(digits) == 11 and digits.startswith(default_country_code):
        e164 = f"+{digits}"
        national = digits[1:]
    else:
        e164 = f"+{digits}" if digits.startswith(default_country_code) and len(digits) > 8 else None
        national = digits[-10:] if len(digits) >= 10 else digits
    display = (
        f"{national[0:3]}-{national[3:6]}-{national[6:10]}"
        if len(national) == 10
        else phone.strip()
    )
    forms = []
    if len(national) == 10:
        forms.extend(
            [
                display,
                national,
                f"({national[0:3]}) {national[3:6]}-{national[6:10]}",
                f"{national[0:3]} {national[3:6]} {national[6:10]}",
            ]
        )
    if e164:
        forms.append(e164)
    return {
        "raw": phone,
        "digits": digits,
        "e164": e164,
        "display": display,
        "search_forms": list(dict.fromkeys(form for form in forms if form)),
    }


def _phone_hits(text: str, phone: str) -> list[str]:
    normalized = _normalize_phone_for_public_web(phone)
    compact = PHONE_DIGIT_RE.sub("", text)
    hits = [
        form
        for form in normalized["search_forms"]
        if str(form).casefold() in text.casefold()
    ]
    digits = str(normalized["digits"] or "")
    national = digits[-10:] if len(digits) >= 10 else digits
    if national and national in compact:
        hits.append(national)
    return list(dict.fromkeys(hits))


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

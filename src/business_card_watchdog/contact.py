from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse


CONTACT_FIELDS = ("full_name", "organization", "title", "email", "phone", "website", "notes")
CONTACT_CANDIDATE_SCHEMA = "business-card-watchdog.contact-candidate.v1"
REVIEWED_CONTACT_SCHEMA = "business-card-watchdog.reviewed-contact.v1"


def build_contact_candidate(
    spec: dict[str, Any],
    *,
    source: str = "business_card_skill",
    default_country: str = "US",
) -> dict[str, Any]:
    observed = {
        field: {
            "value": str(spec.get(field) or "").strip(),
            "source": source,
        }
        for field in CONTACT_FIELDS
        if str(spec.get(field) or "").strip()
    }
    normalized = {
        field: _normalize_field(field, str(payload["value"]), default_country=default_country)
        for field, payload in observed.items()
    }
    candidate: dict[str, Any] = {
        "schema": CONTACT_CANDIDATE_SCHEMA,
        "source": source,
        "observed": observed,
        "normalized": normalized,
        "name_parts": _name_parts(normalized.get("full_name", {}).get("value", "")),
        "extras": {
            key: value
            for key, value in spec.items()
            if key not in CONTACT_FIELDS and value not in (None, "", [], {})
        },
    }
    candidate["flat"] = contact_candidate_to_spec(candidate)
    return candidate


def contact_candidate_to_spec(candidate: dict[str, Any]) -> dict[str, Any]:
    normalized = candidate.get("normalized") if isinstance(candidate.get("normalized"), dict) else {}
    observed = candidate.get("observed") if isinstance(candidate.get("observed"), dict) else {}
    spec: dict[str, Any] = {}
    for field in CONTACT_FIELDS:
        value = ""
        normalized_payload = normalized.get(field) if isinstance(normalized.get(field), dict) else {}
        observed_payload = observed.get(field) if isinstance(observed.get(field), dict) else {}
        if normalized_payload:
            value = str(normalized_payload.get("value") or "").strip()
        if not value and observed_payload:
            value = str(observed_payload.get("value") or "").strip()
        if value:
            spec[field] = value
    return spec


def apply_review_corrections(
    candidate: dict[str, Any],
    *,
    reviewer: str,
    field_corrections: dict[str, Any],
    default_country: str = "US",
) -> dict[str, Any]:
    reviewed = {
        "schema": REVIEWED_CONTACT_SCHEMA,
        "reviewer": reviewer,
        "base_schema": candidate.get("schema"),
        "observed": dict(candidate.get("observed") or {}),
        "normalized": dict(candidate.get("normalized") or {}),
        "corrections": {},
    }
    for field, value in field_corrections.items():
        clean = str(value or "").strip()
        if not clean:
            continue
        reviewed["observed"][field] = {
            "value": clean,
            "source": "operator_review",
            "reviewer": reviewer,
        }
        reviewed["normalized"][field] = _normalize_field(field, clean, default_country=default_country)
        reviewed["corrections"][field] = {
            "value": clean,
            "reviewer": reviewer,
        }
    reviewed["name_parts"] = _name_parts(reviewed["normalized"].get("full_name", {}).get("value", ""))
    reviewed["flat"] = contact_candidate_to_spec(reviewed)
    return reviewed


def _normalize_field(field: str, value: str, *, default_country: str) -> dict[str, Any]:
    clean = " ".join(str(value or "").strip().split())
    if field == "email":
        return {"value": clean.lower(), "raw": value}
    if field == "phone":
        phone = _normalize_phone(clean, default_country=default_country)
        return {"value": phone["e164"] or phone["display"], "raw": value, **phone}
    if field == "website":
        return {"value": _normalize_website(clean), "raw": value}
    return {"value": clean, "raw": value}


def _normalize_phone(value: str, *, default_country: str) -> dict[str, Any]:
    digits = re.sub(r"\D+", "", value)
    country_code = "1" if default_country.upper() in {"US", "USA"} else ""
    e164 = None
    national = digits
    if country_code and len(digits) == 10:
        national = digits
        e164 = f"+{country_code}{digits}"
    elif country_code and len(digits) == 11 and digits.startswith(country_code):
        national = digits[1:]
        e164 = f"+{digits}"
    elif value.strip().startswith("+") and 8 <= len(digits) <= 15:
        e164 = f"+{digits}"
        national = digits[-10:] if len(digits) >= 10 else digits
    display = (
        f"{national[0:3]}-{national[3:6]}-{national[6:10]}"
        if len(national) == 10
        else value.strip()
    )
    return {"digits": digits, "e164": e164, "display": display}


def _normalize_website(value: str) -> str:
    if not value:
        return ""
    candidate = value if "://" in value else f"https://{value}"
    parsed = urlparse(candidate)
    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    path = parsed.path.rstrip("/")
    return f"https://{host}{path}" if host else value.strip()


def _name_parts(value: str) -> dict[str, str]:
    parts = [part for part in str(value or "").strip().split() if part]
    if len(parts) < 2:
        return {"display": " ".join(parts)}
    return {
        "display": " ".join(parts),
        "given": parts[0],
        "family": parts[-1],
    }

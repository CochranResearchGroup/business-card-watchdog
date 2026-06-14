from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse


CONTACT_FIELDS = ("full_name", "organization", "title", "email", "phone", "website", "notes")
PROFILE_URL_FIELDS = ("linkedin", "linkedin_url", "profile_url", "profile", "social_url", "social_profile")
CONTACT_CANDIDATE_SCHEMA = "business-card-watchdog.contact-candidate.v1"
REVIEWED_CONTACT_SCHEMA = "business-card-watchdog.reviewed-contact.v1"
CANONICAL_CONTACT_SCHEMA = "business-card-watchdog.canonical-contact.v1"
ENRICHMENT_MERGE_REVIEW_SCHEMA = "business-card-watchdog.enrichment-merge-review.v1"


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
        field: _normalize_field(
            field,
            str(payload["value"]),
            default_country=default_country,
            source=source,
        )
        for field, payload in observed.items()
    }
    extras = {
        key: value
        for key, value in spec.items()
        if key not in CONTACT_FIELDS and value not in (None, "", [], {})
    }
    candidate: dict[str, Any] = {
        "schema": CONTACT_CANDIDATE_SCHEMA,
        "source": source,
        "normalization": {
            "default_country": default_country,
        },
        "observed": observed,
        "normalized": normalized,
        "contact_points": _contact_points(normalized, observed, extras),
        "name_parts": _name_parts(normalized.get("full_name", {}).get("value", "")),
        "extras": extras,
    }
    _refresh_contact_views(candidate)
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
        "normalization": {
            "default_country": default_country,
        },
        "observed": dict(candidate.get("observed") or {}),
        "normalized": dict(candidate.get("normalized") or {}),
        "extras": dict(candidate.get("extras") or {}),
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
        reviewed["normalized"][field] = _normalize_field(
            field,
            clean,
            default_country=default_country,
            source="operator_review",
        )
        reviewed["corrections"][field] = {
            "value": clean,
            "reviewer": reviewer,
        }
    reviewed["name_parts"] = _name_parts(reviewed["normalized"].get("full_name", {}).get("value", ""))
    reviewed["contact_points"] = _contact_points(
        reviewed["normalized"],
        reviewed["observed"],
        reviewed["extras"],
    )
    _refresh_contact_views(reviewed)
    return reviewed


def apply_enrichment_proposals(
    candidate: dict[str, Any],
    *,
    reviewer: str,
    proposals: list[dict[str, Any]],
    approved_fields: list[str],
    default_country: str = "US",
) -> tuple[dict[str, Any], dict[str, Any]]:
    approved = set(approved_fields)
    reviewed = {
        "schema": REVIEWED_CONTACT_SCHEMA,
        "reviewer": reviewer,
        "base_schema": candidate.get("schema"),
        "normalization": {
            "default_country": default_country,
        },
        "observed": dict(candidate.get("observed") or {}),
        "normalized": dict(candidate.get("normalized") or {}),
        "extras": dict(candidate.get("extras") or {}),
        "corrections": dict(candidate.get("corrections") or {}),
        "merge_approvals": [],
    }
    applied: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for proposal in proposals:
        field = str(proposal.get("field") or "").strip()
        value = str(proposal.get("value") or "").strip()
        if field not in CONTACT_FIELDS or not value:
            skipped.append({"field": field, "reason": "unsupported or empty proposal"})
            continue
        if field not in approved:
            skipped.append({"field": field, "reason": "field was not approved"})
            continue
        merged_value = _merge_enrichment_value(field, reviewed["normalized"], value)
        reviewed["observed"][field] = {
            "value": merged_value,
            "source": "approved_enrichment",
            "reviewer": reviewer,
            "provider": proposal.get("source"),
        }
        reviewed["normalized"][field] = _normalize_field(
            field,
            merged_value,
            default_country=default_country,
            source="approved_enrichment",
        )
        approval = {
            "field": field,
            "value": merged_value,
            "source": proposal.get("source"),
            "reviewer": reviewer,
        }
        reviewed["merge_approvals"].append(approval)
        applied.append(approval)
    reviewed["name_parts"] = _name_parts(reviewed["normalized"].get("full_name", {}).get("value", ""))
    reviewed["contact_points"] = _contact_points(
        reviewed["normalized"],
        reviewed["observed"],
        reviewed["extras"],
    )
    _refresh_contact_views(reviewed)
    return reviewed, {
        "schema": ENRICHMENT_MERGE_REVIEW_SCHEMA,
        "reviewer": reviewer,
        "approved_fields": sorted(approved),
        "applied": applied,
        "skipped": skipped,
    }


def build_canonical_contact(contact: dict[str, Any]) -> dict[str, Any]:
    observed = contact.get("observed") if isinstance(contact.get("observed"), dict) else {}
    normalized = contact.get("normalized") if isinstance(contact.get("normalized"), dict) else {}
    corrections = contact.get("corrections") if isinstance(contact.get("corrections"), dict) else {}
    merge_approvals = list(contact.get("merge_approvals") or [])
    fields = {
        field: _canonical_field(
            field=field,
            observed=observed.get(field) if isinstance(observed.get(field), dict) else {},
            normalized=normalized.get(field) if isinstance(normalized.get(field), dict) else {},
            correction=corrections.get(field) if isinstance(corrections.get(field), dict) else {},
            merge_approvals=merge_approvals,
        )
        for field in CONTACT_FIELDS
        if isinstance(normalized.get(field), dict) or isinstance(observed.get(field), dict)
    }
    return {
        "schema": CANONICAL_CONTACT_SCHEMA,
        "source_schema": contact.get("schema"),
        "fields": fields,
        "contact_points": list(contact.get("contact_points") or []),
        "name_parts": dict(contact.get("name_parts") or {}),
        "diagnostics": _provenance_diagnostics(fields),
    }


def canonical_contact_to_spec(canonical: dict[str, Any]) -> dict[str, Any]:
    fields = canonical.get("fields") if isinstance(canonical.get("fields"), dict) else {}
    spec: dict[str, Any] = {}
    for field in CONTACT_FIELDS:
        payload = fields.get(field) if isinstance(fields.get(field), dict) else {}
        value = str(payload.get("value") or "").strip()
        if value:
            spec[field] = value
    return spec


def field_provenance_from_canonical(canonical: dict[str, Any]) -> dict[str, Any]:
    fields = canonical.get("fields") if isinstance(canonical.get("fields"), dict) else {}
    return {
        field: {
            "source": payload.get("selected_source") or "unknown",
            "confidence": payload.get("confidence") or "unknown",
            "reason": payload.get("reason") or "",
            "provenance": list(payload.get("provenance") or []),
        }
        for field, payload in fields.items()
        if isinstance(payload, dict)
    }


def _normalize_field(field: str, value: str, *, default_country: str, source: str = "normalized") -> dict[str, Any]:
    clean = " ".join(str(value or "").strip().split())
    if field == "email":
        return {
            "value": clean.lower(),
            "raw": value,
            "source": source,
            "confidence": "high" if "@" in clean else "review",
            "reason": "lowercased email address" if "@" in clean else "email-like value needs review",
        }
    if field == "phone":
        phone = _normalize_phone(clean, default_country=default_country)
        return {
            "value": phone["e164"] or phone["display"],
            "raw": value,
            "source": source,
            "confidence": "high" if phone["e164"] else "review",
            "reason": "normalized to E.164" if phone["e164"] else "phone could not be normalized to E.164",
            **phone,
        }
    if field == "website":
        normalized = _normalize_website(clean)
        return {
            "value": normalized,
            "raw": value,
            "source": source,
            "confidence": "high" if normalized.startswith("https://") else "review",
            "reason": "normalized website host and scheme" if normalized.startswith("https://") else "website needs review",
        }
    return {
        "value": clean,
        "raw": value,
        "source": source,
        "confidence": "observed",
        "reason": "trimmed whitespace",
    }


def _refresh_contact_views(contact: dict[str, Any]) -> None:
    canonical = build_canonical_contact(contact)
    contact["canonical"] = canonical
    contact["provenance_diagnostics"] = canonical["diagnostics"]
    contact["flat"] = contact_candidate_to_spec(contact)


def _canonical_field(
    *,
    field: str,
    observed: dict[str, Any],
    normalized: dict[str, Any],
    correction: dict[str, Any],
    merge_approvals: list[dict[str, Any]],
) -> dict[str, Any]:
    value = str(normalized.get("value") or observed.get("value") or "").strip()
    selected_source = _selected_field_source(observed=observed, normalized=normalized, correction=correction)
    provenance = []
    if observed:
        provenance.append(
            {
                "stage": "observed",
                "source": observed.get("source") or "unknown",
                "value": observed.get("value") or "",
            }
        )
    if normalized:
        provenance.append(
            {
                "stage": "normalized",
                "source": normalized.get("source") or observed.get("source") or "normalizer",
                "value": normalized.get("value") or "",
                "raw": normalized.get("raw") or "",
                "confidence": normalized.get("confidence") or "unknown",
                "reason": normalized.get("reason") or "",
            }
        )
    if correction:
        provenance.append(
            {
                "stage": "reviewed",
                "source": "operator_review",
                "value": correction.get("value") or "",
                "reviewer": correction.get("reviewer") or "",
            }
        )
    for approval in merge_approvals:
        if approval.get("field") == field:
            provenance.append(
                {
                    "stage": "enriched",
                    "source": approval.get("source") or "enrichment",
                    "value": approval.get("value") or "",
                    "reviewer": approval.get("reviewer") or "",
                }
            )
    return {
        "value": value,
        "observed_value": observed.get("value") or "",
        "normalized_value": normalized.get("value") or "",
        "selected_source": selected_source,
        "confidence": normalized.get("confidence") or ("observed" if observed else "missing"),
        "reason": normalized.get("reason") or "",
        "provenance": provenance,
    }


def _selected_field_source(
    *,
    observed: dict[str, Any],
    normalized: dict[str, Any],
    correction: dict[str, Any],
) -> str:
    if correction:
        return "reviewer_correction"
    if observed.get("source") == "approved_enrichment":
        return "approved_enrichment"
    if normalized.get("source"):
        return str(normalized["source"])
    return str(observed.get("source") or "unknown")


def _provenance_diagnostics(fields: dict[str, dict[str, Any]]) -> dict[str, Any]:
    review_fields = sorted(
        field
        for field, payload in fields.items()
        if str(payload.get("confidence") or "") == "review"
    )
    source_counts: dict[str, int] = {}
    for payload in fields.values():
        source = str(payload.get("selected_source") or "unknown")
        source_counts[source] = source_counts.get(source, 0) + 1
    return {
        "schema": "business-card-watchdog.contact-provenance-diagnostics.v1",
        "review_field_count": len(review_fields),
        "review_fields": review_fields,
        "source_counts": dict(sorted(source_counts.items())),
    }


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


def _merge_enrichment_value(field: str, normalized: dict[str, Any], value: str) -> str:
    if field != "notes":
        return value
    existing = normalized.get("notes") if isinstance(normalized.get("notes"), dict) else {}
    existing_value = str(existing.get("value") or "").strip()
    if not existing_value or value in existing_value:
        return value if not existing_value else existing_value
    return f"{existing_value}\n{value}"


def _contact_points(
    normalized: dict[str, Any],
    observed: dict[str, Any],
    extras: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []
    for field, kind in (("email", "email"), ("phone", "phone"), ("website", "website")):
        payload = normalized.get(field) if isinstance(normalized.get(field), dict) else {}
        value = str(payload.get("value") or "").strip()
        if not value:
            continue
        observed_payload = observed.get(field) if isinstance(observed.get(field), dict) else {}
        points.append(
            {
                "kind": kind,
                "value": value,
                "source": observed_payload.get("source") or "normalized",
                "raw": observed_payload.get("value") or payload.get("raw") or "",
                "confidence": payload.get("confidence") or "observed",
                "reason": payload.get("reason") or "",
            }
        )
    seen_values = {str(point.get("value") or "") for point in points}
    for point in _profile_contact_points(extras or {}):
        if str(point.get("value") or "") in seen_values:
            continue
        points.append(point)
        seen_values.add(str(point.get("value") or ""))
    return points


def _profile_contact_points(extras: dict[str, Any]) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []
    for key, raw_value in extras.items():
        if key not in PROFILE_URL_FIELDS:
            continue
        values = raw_value if isinstance(raw_value, list) else [raw_value]
        for item in values:
            raw = str(item or "").strip()
            if not raw:
                continue
            normalized = _normalize_website(raw)
            points.append(
                {
                    "kind": "profile_url",
                    "value": normalized,
                    "source": "business_card_skill",
                    "raw": raw,
                    "confidence": "high" if normalized.startswith("https://") else "review",
                    "reason": "normalized profile URL",
                    "label": key,
                }
            )
    return points


def _name_parts(value: str) -> dict[str, str]:
    parts = [part for part in str(value or "").strip().split() if part]
    if len(parts) < 2:
        return {"display": " ".join(parts)}
    return {
        "display": " ".join(parts),
        "given": parts[0],
        "family": parts[-1],
    }

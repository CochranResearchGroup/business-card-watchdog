from __future__ import annotations

import hashlib
import re
from typing import Any


EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE_RE = re.compile(r"(?:\+?\d[\d .()/-]{6,}\d)")
URL_RE = re.compile(r"\b(?:https?://)?(?:www\.)?[A-Z0-9.-]+\.[A-Z]{2,}(?:/[^\s]*)?\b", re.IGNORECASE)
NAME_HINT_RE = re.compile(r"\b[A-Z][a-z]+\s+[A-Z][a-z]+\b")
TITLE_WORDS = {
    "ceo",
    "founder",
    "president",
    "director",
    "manager",
    "engineer",
    "principal",
    "sales",
    "marketing",
    "operations",
    "partner",
}
BACK_WORDS = {
    "linkedin",
    "github",
    "facebook",
    "instagram",
    "twitter",
    "x.com",
    "scan",
    "qr",
    "appointment",
    "hours",
    "directions",
}
ADDRESS_WORDS = {"street", "st.", "suite", "road", "rd.", "avenue", "ave", "city", "state", "zip"}


def classify_card_side(
    *,
    job_id: str,
    source_page: dict[str, Any],
    ocr_text: str,
) -> dict[str, Any]:
    text = ocr_text.strip()
    features = _features(text)
    front_score = (
        features["email_count"] * 4
        + features["phone_count"] * 2
        + features["name_hint_count"] * 2
        + features["title_word_count"]
    )
    back_score = (
        features["url_count"] * 2
        + features["back_word_count"] * 2
        + features["address_word_count"]
        + (2 if features["email_count"] == 0 and features["phone_count"] == 0 else 0)
    )
    evidence = _evidence(features)
    if not text or features["token_count"] <= 2:
        side_label = "blank"
        confidence = "high" if not text or features["token_count"] == 0 else "review"
        reason = "blank_or_near_blank_ocr"
    elif front_score >= 5 and front_score >= back_score + 2:
        side_label = "front"
        confidence = "high" if front_score >= 7 else "review"
        reason = "contact_identity_density"
    elif back_score >= 4 and back_score >= front_score:
        side_label = "back"
        confidence = "review" if front_score else "high"
        reason = "back_side_contextual_clues"
    else:
        side_label = "unknown"
        confidence = "review"
        reason = "insufficient_or_mixed_ocr_clues"
    return {
        "schema": "business-card-watchdog.card-side-candidate.v1",
        "job_id": job_id,
        "source_document_path": source_page["source_document_path"],
        "page_number": source_page["page_number"],
        "page_image_path": source_page["page_image_path"],
        "side_label": side_label,
        "confidence": confidence,
        "classification_reason": reason,
        "features": features,
        "evidence": evidence,
        "ocr_text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "blocked_reason": "" if side_label in {"front", "back", "blank"} else "review required",
    }


def build_pair_proposals(
    *,
    run_id: str,
    side_candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    by_doc: dict[str, list[dict[str, Any]]] = {}
    for candidate in side_candidates:
        by_doc.setdefault(str(candidate.get("source_document_path") or ""), []).append(candidate)
    proposals: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for document_path, candidates in by_doc.items():
        ordered = sorted(candidates, key=lambda row: int(row.get("page_number") or 0))
        for left, right in zip(ordered, ordered[1:]):
            proposal = _pair_candidate(run_id=run_id, document_path=document_path, left=left, right=right)
            if proposal is None:
                skipped.append(
                    {
                        "document_path": document_path,
                        "page_numbers": [left.get("page_number"), right.get("page_number")],
                        "reason": "not_front_back_candidate",
                        "side_labels": [left.get("side_label"), right.get("side_label")],
                    }
                )
            else:
                proposals.append(proposal)
    return {
        "schema": "business-card-watchdog.card-side-pair-proposals.v1",
        "run_id": run_id,
        "proposal_count": len(proposals),
        "proposals": proposals,
        "skipped": skipped,
        "writes_attempted": 0,
        "network_calls_made": 0,
    }


def _pair_candidate(
    *,
    run_id: str,
    document_path: str,
    left: dict[str, Any],
    right: dict[str, Any],
) -> dict[str, Any] | None:
    labels = {str(left.get("side_label") or ""), str(right.get("side_label") or "")}
    if labels != {"front", "back"}:
        return None
    front = left if left.get("side_label") == "front" else right
    back = right if front is left else left
    positive = [
        {"kind": "same_document", "weight": 3, "value": document_path},
        {
            "kind": "page_adjacency",
            "weight": 3,
            "value": abs(int(left.get("page_number") or 0) - int(right.get("page_number") or 0)),
        },
        {"kind": "side_label_complement", "weight": 4, "value": "front_back"},
    ]
    negative = _negative_evidence(front, back)
    score = sum(int(item["weight"]) for item in positive) - sum(int(item["weight"]) for item in negative)
    state = "proposed" if score >= 7 and not negative else "blocked_for_review"
    return {
        "schema": "business-card-watchdog.card-side-pair-proposal.v1",
        "proposal_id": _stable_id(run_id, document_path, str(front.get("job_id")), str(back.get("job_id"))),
        "state": state,
        "confidence": "review" if state == "proposed" else "blocked",
        "front_job_id": front.get("job_id"),
        "back_job_id": back.get("job_id"),
        "front_page_number": front.get("page_number"),
        "back_page_number": back.get("page_number"),
        "source_document_path": document_path,
        "score": score,
        "evidence": positive,
        "negative_evidence": negative,
        "blocked_reason": "" if state == "proposed" else "conflicting OCR evidence requires review",
    }


def _features(text: str) -> dict[str, Any]:
    lowered = text.lower()
    tokens = re.findall(r"[a-z0-9._%+-]+", lowered)
    emails = EMAIL_RE.findall(text)
    phones = PHONE_RE.findall(text)
    urls = [url for url in URL_RE.findall(text) if "@" not in url]
    return {
        "token_count": len(tokens),
        "email_count": len(emails),
        "phone_count": len(phones),
        "url_count": len(urls),
        "name_hint_count": len(NAME_HINT_RE.findall(text)),
        "title_word_count": sum(1 for token in tokens if token in TITLE_WORDS),
        "back_word_count": sum(1 for word in BACK_WORDS if word in lowered),
        "address_word_count": sum(1 for word in ADDRESS_WORDS if word in lowered),
        "domains": sorted({_domain_from_email(email) for email in emails if _domain_from_email(email)}),
        "urls": sorted(set(urls)),
    }


def _evidence(features: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key in [
        "email_count",
        "phone_count",
        "url_count",
        "name_hint_count",
        "title_word_count",
        "back_word_count",
        "address_word_count",
    ]:
        value = int(features.get(key) or 0)
        if value:
            rows.append({"kind": key, "value": value})
    return rows


def _negative_evidence(front: dict[str, Any], back: dict[str, Any]) -> list[dict[str, Any]]:
    front_domains = set((front.get("features") or {}).get("domains") or [])
    back_domains = set((back.get("features") or {}).get("domains") or [])
    if front_domains and back_domains and front_domains.isdisjoint(back_domains):
        return [
            {
                "kind": "conflicting_email_domains",
                "weight": 5,
                "front_domains": sorted(front_domains),
                "back_domains": sorted(back_domains),
            }
        ]
    return []


def _domain_from_email(email: str) -> str:
    if "@" not in email:
        return ""
    return email.rsplit("@", 1)[-1].lower()


def _stable_id(*parts: str) -> str:
    digest = hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()[:20]
    return f"pair_{digest}"

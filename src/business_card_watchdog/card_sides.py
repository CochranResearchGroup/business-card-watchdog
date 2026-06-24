from __future__ import annotations

import hashlib
from pathlib import PurePath
import re
from typing import Any


EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE_RE = re.compile(r"(?:\+?\d[\d .()/-]{6,}\d)")
URL_RE = re.compile(r"\b(?:https?://)?(?:www\.)?[A-Z0-9.-]+\.[A-Z]{2,}(?:/[^\s]*)?\b", re.IGNORECASE)
NAME_HINT_RE = re.compile(r"\b[A-Z][a-z]+\s+[A-Z][a-z]+\b")
PAIR_SESSION_WINDOW = 4
COMMON_TOKENS = {
    "and",
    "ave",
    "avenue",
    "card",
    "city",
    "com",
    "directions",
    "email",
    "for",
    "hours",
    "linkedin",
    "phone",
    "portfolio",
    "qr",
    "road",
    "scan",
    "state",
    "street",
    "suite",
    "the",
    "www",
}
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
    by_session: dict[str, list[dict[str, Any]]] = {}
    for candidate in side_candidates:
        by_session.setdefault(_pairing_session_key(candidate), []).append(candidate)
    proposals: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for session_key, candidates in by_session.items():
        ordered = sorted(candidates, key=lambda row: (_page_number(row), str(row.get("job_id") or "")))
        skipped.extend(_adjacent_transition_skips(session_key, ordered))
        session_proposals: list[dict[str, Any]] = []
        for index, left in enumerate(ordered):
            for right in ordered[index + 1 :]:
                if not _within_pairing_window(left, right):
                    continue
                proposal = _pair_candidate(run_id=run_id, session_key=session_key, left=left, right=right)
                if proposal is not None:
                    session_proposals.append(proposal)
        session_proposals.sort(
            key=lambda row: (
                0 if row.get("state") == "proposed" else 1,
                -int(row.get("score") or 0),
                str(row.get("proposal_id") or ""),
            )
        )
        proposals.extend(session_proposals)
        skipped.extend(_unpaired_side_skips(session_key, ordered, session_proposals))
    return {
        "schema": "business-card-watchdog.card-side-pair-proposals.v1",
        "run_id": run_id,
        "proposal_count": len(proposals),
        "proposals": proposals,
        "skipped": skipped,
        "writes_attempted": 0,
        "network_calls_made": 0,
    }


def build_side_pair_graph(
    *,
    run_id: str,
    side_candidates: list[dict[str, Any]],
    evidence_by_job: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    evidence_by_job = evidence_by_job or {}
    by_session: dict[str, list[dict[str, Any]]] = {}
    for candidate in side_candidates:
        by_session.setdefault(_pairing_session_key(candidate), []).append(candidate)
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    pair_proposals: list[dict[str, Any]] = []
    for session_key, candidates in sorted(by_session.items()):
        ordered = sorted(candidates, key=lambda row: (_page_number(row), str(row.get("job_id") or "")))
        for candidate in ordered:
            nodes.append(_side_pair_node(candidate, evidence_by_job.get(str(candidate.get("job_id") or ""), {})))
        for index, left in enumerate(ordered):
            for right in ordered[index + 1 :]:
                if not _graph_edge_candidate(left, right, evidence_by_job=evidence_by_job):
                    continue
                edge = _side_pair_edge(
                    run_id=run_id,
                    session_key=session_key,
                    left=left,
                    right=right,
                    left_evidence=evidence_by_job.get(str(left.get("job_id") or ""), {}),
                    right_evidence=evidence_by_job.get(str(right.get("job_id") or ""), {}),
                )
                edges.append(edge)
                if edge["state"] in {"pair_proposed", "pair_review_required"}:
                    pair_proposals.append(edge)
    return {
        "schema": "business-card-watchdog.side-pair-graph.v1",
        "run_id": run_id,
        "node_count": len(nodes),
        "edge_count": len(edges),
        "pair_proposal_count": len(pair_proposals),
        "nodes": nodes,
        "edges": edges,
        "pair_proposals": pair_proposals,
        "writes_attempted": 0,
        "network_calls_made": 0,
    }


def redacted_side_pair_graph_summary(payload: dict[str, Any]) -> dict[str, Any]:
    edges = [edge for edge in list(payload.get("edges") or []) if isinstance(edge, dict)]
    states: dict[str, int] = {}
    for edge in edges:
        state = str(edge.get("state") or "unknown")
        states[state] = states.get(state, 0) + 1
    return {
        "state": "has_pair_candidates" if payload.get("pair_proposal_count") else "no_pair_candidates",
        "node_count": int(payload.get("node_count") or 0),
        "edge_count": int(payload.get("edge_count") or 0),
        "pair_proposal_count": int(payload.get("pair_proposal_count") or 0),
        "edge_states": dict(sorted(states.items())),
    }


def merge_side_pair_contacts(
    *,
    front_candidate: dict[str, Any],
    back_candidate: dict[str, Any],
    proposal: dict[str, Any],
    reviewer: str,
    reviewed_at: str,
    field_corrections: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from .contact import CONTACT_FIELDS, build_contact_candidate

    front_spec = _candidate_spec(front_candidate)
    back_spec = _candidate_spec(back_candidate)
    corrections = {key: str(value).strip() for key, value in dict(field_corrections or {}).items()}
    merged_spec: dict[str, Any] = {}
    field_provenance: dict[str, dict[str, Any]] = {}
    for field in CONTACT_FIELDS:
        front_value = str(front_spec.get(field) or "").strip()
        back_value = str(back_spec.get(field) or "").strip()
        corrected = corrections.get(field, "")
        if corrected:
            merged_spec[field] = corrected
            field_provenance[field] = {
                "selected_side": "reviewer_correction",
                "front_value": front_value,
                "back_value": back_value,
                "reviewer": reviewer,
            }
        elif front_value and back_value and front_value == back_value:
            merged_spec[field] = front_value
            field_provenance[field] = {
                "selected_side": "both",
                "front_value": front_value,
                "back_value": back_value,
            }
        elif front_value:
            merged_spec[field] = front_value
            field_provenance[field] = {
                "selected_side": "front",
                "front_value": front_value,
                "back_value": back_value,
            }
        elif back_value:
            merged_spec[field] = back_value
            field_provenance[field] = {
                "selected_side": "back",
                "front_value": front_value,
                "back_value": back_value,
            }
    reviewed = build_contact_candidate(merged_spec, source="side_pair_review")
    reviewed["schema"] = "business-card-watchdog.reviewed-side-pair-contact.v1"
    reviewed["review"] = {
        "state": "approved_for_routing_review",
        "reviewer": reviewer,
        "reviewed_at": reviewed_at,
        "action": "approve_side_pair_merge",
    }
    reviewed["side_pair"] = {
        "proposal_id": proposal.get("proposal_id"),
        "front_job_id": proposal.get("front_job_id"),
        "back_job_id": proposal.get("back_job_id"),
        "front_page_number": proposal.get("front_page_number"),
        "back_page_number": proposal.get("back_page_number"),
        "source_document_path": proposal.get("source_document_path"),
        "field_provenance": field_provenance,
    }
    reviewed["routing_allowed"] = False
    reviewed["enrichment_allowed"] = False
    reviewed["sink_write_allowed"] = False
    return reviewed


def _side_pair_node(candidate: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
    qr = dict(evidence.get("qr_evidence") or {})
    crop = dict(evidence.get("crop_quality") or {})
    orientation = dict(evidence.get("orientation_evidence") or {})
    features = dict(candidate.get("features") or {})
    return {
        "job_id": candidate.get("job_id"),
        "source_document_path": candidate.get("source_document_path"),
        "page_number": candidate.get("page_number"),
        "page_image_path": candidate.get("page_image_path"),
        "pairing_session_key": _pairing_session_key(candidate),
        "side_label": candidate.get("side_label"),
        "side_confidence": candidate.get("confidence"),
        "domain_count": len(features.get("domains") or []),
        "token_count": int(features.get("token_count") or 0),
        "qr_found": bool(qr.get("qr_found")),
        "qr_decode_count": int(qr.get("decode_count") or 0),
        "crop_state": crop.get("state") or "unknown",
        "crop_bad_count": int(crop.get("bad_count") or 0),
        "orientation_state": orientation.get("state") or "unknown",
    }


def _side_pair_edge(
    *,
    run_id: str,
    session_key: str,
    left: dict[str, Any],
    right: dict[str, Any],
    left_evidence: dict[str, Any],
    right_evidence: dict[str, Any],
) -> dict[str, Any]:
    page_distance = abs(_page_number(left) - _page_number(right))
    labels = {str(left.get("side_label") or ""), str(right.get("side_label") or "")}
    positive = [
        {"kind": "same_pairing_session", "weight": 2, "value": session_key},
        {"kind": "adjacent_pages", "weight": 3 if page_distance == 1 else 1, "value": page_distance},
    ]
    negative: list[dict[str, Any]] = []
    state = "blocked_for_review"
    reason = "adjacent pages need side-pair review"
    if _qr_side_pair_candidate(left_evidence, right_evidence):
        positive.append({"kind": "qr_side_adjacency", "weight": 3, "value": "qr_adjacent_to_possible_text_side"})
        state = "pair_review_required"
        reason = "QR-bearing side adjacent to possible text or crop-evidence side"
    elif "blank" in labels:
        state = "blank_back_candidate"
        reason = "adjacent blank side may be a dropped or blank card back"
    elif labels == {"front", "back"}:
        positive.append({"kind": "side_label_complement", "weight": 3, "value": "front_back"})
        state = "pair_review_required"
        reason = "front/back side labels need contextual confirmation"
    elif labels == {"unknown"}:
        reason = "adjacent unknown sides lack enough deterministic context"
    context = _context_evidence(left, right) + _context_evidence(right, left)
    positive.extend(context)
    negative.extend(_negative_evidence(left, right))
    score = sum(int(item.get("weight") or 0) for item in positive) - sum(
        int(item.get("weight") or 0) for item in negative
    )
    if negative:
        state = "blocked_for_review"
        reason = "conflicting OCR/domain evidence"
    elif labels == {"front", "back"} and _has_required_context_evidence(context) and score >= 7:
        state = "pair_proposed"
        reason = "front/back side labels with deterministic context"
    return {
        "edge_id": _stable_id(run_id, session_key, str(left.get("job_id")), str(right.get("job_id")), "graph"),
        "state": state,
        "reason": reason,
        "left_job_id": left.get("job_id"),
        "right_job_id": right.get("job_id"),
        "page_numbers": [left.get("page_number"), right.get("page_number")],
        "side_labels": [left.get("side_label"), right.get("side_label")],
        "pairing_session_key": session_key,
        "page_distance": page_distance,
        "score": score,
        "evidence": positive,
        "negative_evidence": negative,
        "requires_app_intelligence_review": state in {"pair_review_required", "blocked_for_review"},
        "routing_allowed": False,
    }


def _graph_edge_candidate(
    left: dict[str, Any],
    right: dict[str, Any],
    *,
    evidence_by_job: dict[str, dict[str, Any]],
) -> bool:
    page_distance = abs(_page_number(left) - _page_number(right))
    if page_distance <= 1:
        return True
    if not _within_pairing_window(left, right):
        return False
    labels = {str(left.get("side_label") or ""), str(right.get("side_label") or "")}
    if labels == {"front", "back"}:
        return True
    left_evidence = evidence_by_job.get(str(left.get("job_id") or ""), {})
    right_evidence = evidence_by_job.get(str(right.get("job_id") or ""), {})
    return _qr_side_pair_candidate(left_evidence, right_evidence)


def _qr_side_pair_candidate(left_evidence: dict[str, Any], right_evidence: dict[str, Any]) -> bool:
    left_qr = bool((left_evidence.get("qr_evidence") or {}).get("qr_found"))
    right_qr = bool((right_evidence.get("qr_evidence") or {}).get("qr_found"))
    if left_qr == right_qr:
        return False
    other = right_evidence if left_qr else left_evidence
    crop = dict(other.get("crop_quality") or {})
    orientation = dict(other.get("orientation_evidence") or {})
    return (
        str(crop.get("state") or "") in {"good", "bad", "qr_only"}
        or int(crop.get("crop_count") or 0) > 0
        or str(orientation.get("state") or "") != "unknown"
    )


def _pair_candidate(
    *,
    run_id: str,
    session_key: str,
    left: dict[str, Any],
    right: dict[str, Any],
) -> dict[str, Any] | None:
    labels = {str(left.get("side_label") or ""), str(right.get("side_label") or "")}
    if labels != {"front", "back"}:
        return None
    front = left if left.get("side_label") == "front" else right
    back = right if front is left else left
    page_distance = abs(_page_number(left) - _page_number(right))
    positive = [
        {"kind": "same_pairing_session", "weight": 2, "value": session_key},
        {
            "kind": "page_proximity",
            "weight": 2 if page_distance == 1 else 1,
            "value": page_distance,
        },
        {"kind": "side_label_complement", "weight": 3, "value": "front_back"},
    ]
    context_evidence = _context_evidence(front, back)
    positive.extend(context_evidence)
    negative = _negative_evidence(front, back)
    score = sum(int(item["weight"]) for item in positive) - sum(int(item["weight"]) for item in negative)
    has_required_context = _has_required_context_evidence(context_evidence)
    state = "proposed" if score >= 7 and has_required_context and not negative else "blocked_for_review"
    blocked_reason = ""
    if state != "proposed":
        blocked_reason = (
            "conflicting OCR evidence requires review"
            if negative
            else "missing OCR/context evidence beyond page proximity"
        )
    return {
        "schema": "business-card-watchdog.card-side-pair-proposal.v1",
        "proposal_id": _stable_id(run_id, session_key, str(front.get("job_id")), str(back.get("job_id"))),
        "state": state,
        "confidence": "review" if state == "proposed" else "blocked",
        "front_job_id": front.get("job_id"),
        "back_job_id": back.get("job_id"),
        "front_page_number": front.get("page_number"),
        "back_page_number": back.get("page_number"),
        "source_document_path": front.get("source_document_path") or back.get("source_document_path") or session_key,
        "pairing_session_key": session_key,
        "pairing_window": PAIR_SESSION_WINDOW,
        "required_context_evidence": has_required_context,
        "score": score,
        "evidence": positive,
        "negative_evidence": negative,
        "blocked_reason": blocked_reason,
    }


def _features(text: str) -> dict[str, Any]:
    lowered = text.lower()
    tokens = re.findall(r"[a-z0-9._%+-]+", lowered)
    emails = EMAIL_RE.findall(text)
    phones = PHONE_RE.findall(text)
    urls = [url for url in URL_RE.findall(text) if "@" not in url]
    email_domains = sorted({_domain_from_email(email) for email in emails if _domain_from_email(email)})
    url_domains = sorted({_domain_from_url(url) for url in urls if _domain_from_url(url)})
    return {
        "token_count": len(tokens),
        "tokens": sorted(set(tokens)),
        "email_count": len(emails),
        "phone_count": len(phones),
        "url_count": len(urls),
        "name_hint_count": len(NAME_HINT_RE.findall(text)),
        "title_word_count": sum(1 for token in tokens if token in TITLE_WORDS),
        "back_word_count": sum(1 for word in BACK_WORDS if word in lowered),
        "address_word_count": sum(1 for word in ADDRESS_WORDS if word in lowered),
        "email_domains": email_domains,
        "url_domains": url_domains,
        "domains": sorted(set(email_domains) | set(url_domains)),
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
    front_domains = set((front.get("features") or {}).get("email_domains") or [])
    back_domains = set((back.get("features") or {}).get("email_domains") or [])
    front_all_domains = set((front.get("features") or {}).get("domains") or [])
    back_all_domains = set((back.get("features") or {}).get("domains") or [])
    if front_domains and back_domains and front_domains.isdisjoint(back_domains):
        return [
            {
                "kind": "conflicting_email_domains",
                "weight": 5,
                "front_domains": sorted(front_domains),
                "back_domains": sorted(back_domains),
            }
        ]
    if front_all_domains and back_all_domains and front_all_domains.isdisjoint(back_all_domains):
        return [
            {
                "kind": "conflicting_contact_domains",
                "weight": 4,
                "front_domains": sorted(front_all_domains),
                "back_domains": sorted(back_all_domains),
            }
        ]
    return []


def _context_evidence(front: dict[str, Any], back: dict[str, Any]) -> list[dict[str, Any]]:
    front_features = front.get("features") or {}
    back_features = back.get("features") or {}
    evidence: list[dict[str, Any]] = []
    shared_domains = sorted(set(front_features.get("domains") or []) & set(back_features.get("domains") or []))
    if shared_domains:
        evidence.append({"kind": "shared_domain", "weight": 4, "domains": shared_domains})
    front_email_domains = set(front_features.get("email_domains") or [])
    back_url_domains = set(back_features.get("url_domains") or [])
    email_url_domains = sorted(front_email_domains & back_url_domains)
    if email_url_domains:
        evidence.append({"kind": "email_domain_matches_back_url", "weight": 3, "domains": email_url_domains})
    shared_tokens = _shared_context_tokens(front_features, back_features)
    if shared_tokens:
        evidence.append({"kind": "ocr_token_overlap", "weight": 2, "tokens": shared_tokens[:8]})
    if _capture_stem(front) and _capture_stem(front) == _capture_stem(back):
        evidence.append({"kind": "same_capture_stem", "weight": 3, "value": _capture_stem(front)})
    if _is_front_dense(front_features) and _is_back_complementary(back_features):
        evidence.append({"kind": "complementary_side_density", "weight": 2, "value": "front_identity_back_context"})
    return evidence


def _has_required_context_evidence(evidence: list[dict[str, Any]]) -> bool:
    required_kinds = {
        "shared_domain",
        "email_domain_matches_back_url",
        "ocr_token_overlap",
        "same_capture_stem",
    }
    return any(str(item.get("kind") or "") in required_kinds for item in evidence)


def _adjacent_transition_skips(session_key: str, ordered: list[dict[str, Any]]) -> list[dict[str, Any]]:
    skipped: list[dict[str, Any]] = []
    for left, right in zip(ordered, ordered[1:]):
        labels = [left.get("side_label"), right.get("side_label")]
        if set(str(label or "") for label in labels) == {"front", "back"}:
            continue
        skipped.append(
            {
                "document_path": session_key,
                "pairing_session_key": session_key,
                "page_numbers": [left.get("page_number"), right.get("page_number")],
                "reason": "not_front_back_candidate",
                "side_labels": labels,
            }
        )
    return skipped


def _unpaired_side_skips(
    session_key: str,
    ordered: list[dict[str, Any]],
    proposals: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    paired_job_ids = {
        str(proposal.get(key) or "")
        for proposal in proposals
        for key in ("front_job_id", "back_job_id")
        if proposal.get(key)
    }
    skipped: list[dict[str, Any]] = []
    for candidate in ordered:
        side_label = str(candidate.get("side_label") or "")
        job_id = str(candidate.get("job_id") or "")
        if side_label not in {"front", "back"} or job_id in paired_job_ids:
            continue
        skipped.append(
            {
                "document_path": session_key,
                "pairing_session_key": session_key,
                "page_numbers": [candidate.get("page_number")],
                "reason": "unpaired_non_blank_side_candidate",
                "side_labels": [side_label],
                "job_id": candidate.get("job_id"),
                "review_required": side_label == "back",
            }
        )
    return skipped


def _within_pairing_window(left: dict[str, Any], right: dict[str, Any]) -> bool:
    if _capture_stem(left) and _capture_stem(left) == _capture_stem(right):
        return True
    left_page = _page_number(left)
    right_page = _page_number(right)
    if left_page == 0 or right_page == 0:
        return True
    return abs(left_page - right_page) <= PAIR_SESSION_WINDOW


def _page_number(candidate: dict[str, Any]) -> int:
    try:
        return int(candidate.get("page_number") or 0)
    except (TypeError, ValueError):
        return 0


def _pairing_session_key(candidate: dict[str, Any]) -> str:
    source_document = str(candidate.get("source_document_path") or "")
    if source_document.lower().endswith(".pdf"):
        return source_document
    capture_stem = _capture_stem(candidate)
    if capture_stem:
        return f"capture:{capture_stem}"
    source_path = source_document or str(candidate.get("page_image_path") or "")
    if source_path:
        parent = str(PurePath(source_path).parent)
        return parent if parent != "." else source_path
    return "unknown"


def _capture_stem(candidate: dict[str, Any]) -> str:
    source_path = str(candidate.get("source_file_path") or candidate.get("source_document_path") or "")
    image_path = str(candidate.get("page_image_path") or "")
    if source_path.lower().endswith(".pdf"):
        source_path = image_path
    stem = PurePath(source_path or image_path).stem.lower()
    return re.sub(r"[-_\s]?(front|back|recto|verso|side[ab]|side-[ab])$", "", stem).strip("-_ ")


def _shared_context_tokens(front_features: dict[str, Any], back_features: dict[str, Any]) -> list[str]:
    front_tokens = set(front_features.get("tokens") or [])
    back_tokens = set(back_features.get("tokens") or [])
    return sorted(
        token
        for token in front_tokens & back_tokens
        if len(token) >= 4 and token not in COMMON_TOKENS and token not in TITLE_WORDS
    )


def _is_front_dense(features: dict[str, Any]) -> bool:
    return (
        int(features.get("email_count") or 0) > 0
        or int(features.get("phone_count") or 0) > 0
        or int(features.get("name_hint_count") or 0) > 0
    )


def _is_back_complementary(features: dict[str, Any]) -> bool:
    return int(features.get("url_count") or 0) > 0 or int(features.get("back_word_count") or 0) > 0


def _domain_from_email(email: str) -> str:
    if "@" not in email:
        return ""
    return email.rsplit("@", 1)[-1].lower()


def _domain_from_url(url: str) -> str:
    cleaned = re.sub(r"^https?://", "", url.strip().lower())
    cleaned = re.sub(r"^www\.", "", cleaned)
    return cleaned.split("/", 1)[0]


def _candidate_spec(candidate: dict[str, Any]) -> dict[str, Any]:
    from .contact import contact_candidate_to_spec

    return contact_candidate_to_spec(candidate)


def _stable_id(*parts: str) -> str:
    digest = hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()[:20]
    return f"pair_{digest}"

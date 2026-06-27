from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .config import AppConfig
from .models import utc_now
from .positive_control_ocr_drafts import build_positive_control_ocr_contact_drafts


POSITIVE_CONTROL_SIDE_PAIR_EVIDENCE_SCHEMA = "business-card-watchdog.positive-control-side-pair-evidence.v1"
SIDE_PAIR_EDGE_SCHEMA = "business-card-watchdog.positive-control-side-pair-edge.v1"


def build_positive_control_side_pair_evidence(
    config: AppConfig,
    *,
    write: bool = True,
    ocr_text_by_candidate_id: dict[str, str] | None = None,
) -> dict[str, Any]:
    corpus_root = config.data_dir / "positive_control_corpus"
    ocr_drafts = build_positive_control_ocr_contact_drafts(
        config,
        write=write,
        ocr_text_by_candidate_id=ocr_text_by_candidate_id,
    )
    drafts = [draft for draft in list(ocr_drafts.get("contact_drafts") or []) if isinstance(draft, dict)]
    edges = _edges(drafts)
    report_id = f"positive-control-side-pair-{utc_now().replace(':', '-')}-{_edge_digest(edges)}"
    report_dir = corpus_root / "side_pair_evidence" / report_id
    report_path = report_dir / "side_pair_evidence.json"
    review_requests = _review_requests(edges)
    counts = _counts(drafts=drafts, edges=edges, review_requests=review_requests)
    state = _state(drafts=drafts, edges=edges)
    payload: dict[str, Any] = {
        "schema": POSITIVE_CONTROL_SIDE_PAIR_EVIDENCE_SCHEMA,
        "generated_at": utc_now(),
        "state": state if write else ("ready_for_runtime_side_pair_evidence" if state != "blocked" else "blocked"),
        "report_id": report_id,
        "ocr_draft_id": ocr_drafts.get("draft_id"),
        "ocr_draft_state": ocr_drafts.get("state"),
        "contact_draft_count": len(drafts),
        "edge_count": len(edges),
        "edges": edges,
        "review_requests": review_requests,
        "counts": counts,
        "private_paths_redacted": True,
        "private_filenames_redacted": True,
        "operator_declared_known_positive_only": True,
        "contacts_review_required": True,
        "dry_run": True,
        "routing_allowed": False,
        "enrichment_allowed": False,
        "sink_payloads_created": 0,
        "ocr_attempted": int(ocr_drafts.get("ocr_attempted") or 0),
        "pdfs_rasterized": int(ocr_drafts.get("pdfs_rasterized") or 0),
        "crops_created": 0,
        "writes_attempted": 0,
        "network_calls_made": 0,
        "live_sink_calls_made": False,
        "public_web_search_used": False,
        "paid_enrichment_used": False,
        "runtime_artifact_written": False,
        "report_path": None,
        "commands": {
            "positive_control_side_pair_evidence": "positive-control-side-pair-evidence --json",
            "positive_control_side_pair_evidence_preview": "positive-control-side-pair-evidence --no-write --json",
            "positive_control_ocr_contact_drafts": "positive-control-ocr-contact-drafts --json",
        },
        "explicit_stop_conditions": [
            "This surface emits front/back side-pair evidence only; it does not apply merges.",
            "Every pair_proposed edge remains review-required before downstream contact projection.",
            "Conflicting identities are blocked and require review evidence before any merge.",
            "Ambiguous pairs route to bounded App Intelligence review evidence.",
            "Do not enrich, route, create sink payloads, write contacts, read back sinks, search public web, or call paid providers.",
        ],
    }
    if write and state != "blocked":
        _ensure_runtime_output_not_repo(corpus_root)
        report_dir.mkdir(parents=True, exist_ok=True)
        report_payload = payload | {
            "runtime_artifact_written": True,
            "report_path": str(report_path),
        }
        report_path.write_text(json.dumps(report_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        payload["runtime_artifact_written"] = True
        payload["report_path"] = str(report_path)
    return payload


def _edges(drafts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for draft in drafts:
        if draft.get("media_kind") != "pdf_page":
            continue
        grouped.setdefault(str(draft.get("entry_id") or ""), []).append(draft)
    edges: list[dict[str, Any]] = []
    for entry_id, rows in sorted(grouped.items()):
        ordered = sorted(rows, key=lambda draft: int(draft.get("page_number") or 0))
        index = 0
        while index < len(ordered):
            left = ordered[index]
            right = ordered[index + 1] if index + 1 < len(ordered) else None
            if right is None:
                edges.append(_front_only_edge(entry_id=entry_id, draft=left))
                index += 1
                continue
            edges.append(_pair_edge(entry_id=entry_id, left=left, right=right))
            index += 2
    edges.sort(key=lambda edge: str(edge.get("edge_id") or ""))
    return edges


def _pair_edge(*, entry_id: str, left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    left_features = _features(left)
    right_features = _features(right)
    clues = _deterministic_clues(left_features=left_features, right_features=right_features)
    conflict = _conflict(left_features=left_features, right_features=right_features)
    state = _edge_state(left_features=left_features, right_features=right_features, clues=clues, conflict=conflict)
    front, back, order = _front_back_order(left=left, right=right, left_features=left_features, right_features=right_features)
    merge_evidence = _merge_evidence(front=front, back=back, state=state, conflict=conflict)
    edge_id = f"{entry_id}-pages-{int(left.get('page_number') or 0):03d}-{int(right.get('page_number') or 0):03d}"
    return {
        "schema": SIDE_PAIR_EDGE_SCHEMA,
        "edge_id": edge_id,
        "entry_id": entry_id,
        "state": state,
        "reason": _state_reason(state=state, clues=clues, conflict=conflict),
        "left_draft_id": left.get("draft_id"),
        "right_draft_id": right.get("draft_id"),
        "front_draft_id": front.get("draft_id") if front else None,
        "back_draft_id": back.get("draft_id") if back else None,
        "page_numbers": [left.get("page_number"), right.get("page_number")],
        "front_back_order": order,
        "deterministic_clues": clues,
        "conflict_evidence": conflict,
        "merge_evidence": merge_evidence,
        "app_intelligence_review_required": state in {"review_required", "blocked_conflict"},
        "review_required": True,
        "routing_allowed": False,
        "enrichment_allowed": False,
        "sink_write_allowed": False,
        "private_paths_redacted": True,
        "private_filenames_redacted": True,
    }


def _front_only_edge(*, entry_id: str, draft: dict[str, Any]) -> dict[str, Any]:
    fields = dict(draft.get("extracted_fields") or {})
    state = "front_only" if _has_identity(_features(draft)) else "review_required"
    edge_id = f"{entry_id}-page-{int(draft.get('page_number') or 0):03d}-front-only"
    return {
        "schema": SIDE_PAIR_EDGE_SCHEMA,
        "edge_id": edge_id,
        "entry_id": entry_id,
        "state": state,
        "reason": "unpaired scanner page retained as front-only candidate" if state == "front_only" else "unpaired scanner page lacks deterministic identity evidence",
        "left_draft_id": draft.get("draft_id"),
        "right_draft_id": None,
        "front_draft_id": draft.get("draft_id") if state == "front_only" else None,
        "back_draft_id": None,
        "page_numbers": [draft.get("page_number")],
        "front_back_order": "front_only",
        "deterministic_clues": {
            "front_identity_present": _has_identity(_features(draft)),
            "extracted_fields": sorted(fields),
        },
        "conflict_evidence": {},
        "merge_evidence": {
            "state": "front_only_candidate" if state == "front_only" else "review_required",
            "merged_fields": fields if state == "front_only" else {},
            "backside_augmented_fields": [],
            "direct_sink_update_allowed": False,
        },
        "app_intelligence_review_required": state == "review_required",
        "review_required": True,
        "routing_allowed": False,
        "enrichment_allowed": False,
        "sink_write_allowed": False,
        "private_paths_redacted": True,
        "private_filenames_redacted": True,
    }


def _features(draft: dict[str, Any]) -> dict[str, Any]:
    fields = dict(draft.get("extracted_fields") or {})
    normalized = dict(draft.get("normalized_contact") or {})
    flat = dict(normalized.get("flat") or {})
    ocr = dict(draft.get("ocr_provenance") or {})
    raw_text = str(ocr.get("raw_text") or "")
    email = str(fields.get("email") or flat.get("email") or "").lower()
    phone = str(fields.get("phone") or flat.get("phone") or "")
    website = str(fields.get("website") or flat.get("website") or "").lower()
    full_name = str(fields.get("full_name") or flat.get("full_name") or "")
    organization = str(fields.get("organization") or flat.get("organization") or "")
    domains = sorted({domain for domain in [_domain(email), _domain(website)] if domain})
    text_lower = raw_text.lower()
    cue_words = sorted(word for word in ["linkedin", "github", "qr", "scan", "website", "directions", "hours"] if word in text_lower)
    has_backside_cue = bool(cue_words and not email and not phone)
    meaningful_name = bool(full_name and full_name.strip().lower() not in {"scan qr", "qr code", "website"})
    if full_name.lower().startswith(("scan ", "visit ", "follow ")):
        meaningful_name = False
    meaningful_organization = bool(organization and not has_backside_cue)
    return {
        "draft_id": draft.get("draft_id"),
        "page_number": draft.get("page_number"),
        "ocr_state": ocr.get("state"),
        "email": email,
        "phone": phone,
        "website": website,
        "full_name": full_name,
        "organization": organization,
        "domains": domains,
        "cue_words": cue_words,
        "fields": fields,
        "has_identity": bool(email or phone or meaningful_organization or meaningful_name),
        "has_contact_point": bool(email or phone or website),
        "has_backside_cue": has_backside_cue,
        "ocr_missing": ocr.get("state") == "ocr_missing",
    }


def _domain(value: str) -> str:
    value = value.lower().strip()
    if not value:
        return ""
    if "@" in value:
        return value.rsplit("@", 1)[-1]
    value = value.removeprefix("https://").removeprefix("http://").removeprefix("www.")
    return value.split("/", 1)[0]


def _deterministic_clues(*, left_features: dict[str, Any], right_features: dict[str, Any]) -> dict[str, Any]:
    shared_domains = sorted(set(left_features["domains"]) & set(right_features["domains"]))
    shared_email = left_features["email"] and left_features["email"] == right_features["email"]
    shared_phone = left_features["phone"] and left_features["phone"] == right_features["phone"]
    return {
        "shared_domains": shared_domains,
        "shared_email": bool(shared_email),
        "shared_phone": bool(shared_phone),
        "left_identity_present": _has_identity(left_features),
        "right_identity_present": _has_identity(right_features),
        "left_backside_cues": list(left_features["cue_words"]),
        "right_backside_cues": list(right_features["cue_words"]),
        "left_ocr_missing": bool(left_features["ocr_missing"]),
        "right_ocr_missing": bool(right_features["ocr_missing"]),
    }


def _conflict(*, left_features: dict[str, Any], right_features: dict[str, Any]) -> dict[str, Any]:
    conflicts: list[str] = []
    if left_features["email"] and right_features["email"] and left_features["email"] != right_features["email"]:
        conflicts.append("email")
    if left_features["phone"] and right_features["phone"] and left_features["phone"] != right_features["phone"]:
        conflicts.append("phone")
    left_domains = set(left_features["domains"])
    right_domains = set(right_features["domains"])
    if left_domains and right_domains and not left_domains & right_domains and not (
        left_features["has_backside_cue"] or right_features["has_backside_cue"]
    ):
        conflicts.append("domain")
    if (
        left_features["full_name"]
        and right_features["full_name"]
        and not left_features["has_backside_cue"]
        and not right_features["has_backside_cue"]
        and left_features["full_name"].lower() != right_features["full_name"].lower()
        and left_features["email"] != right_features["email"]
    ):
        conflicts.append("full_name")
    return {
        "conflict_fields": sorted(set(conflicts)),
        "conflict_count": len(set(conflicts)),
    }


def _edge_state(*, left_features: dict[str, Any], right_features: dict[str, Any], clues: dict[str, Any], conflict: dict[str, Any]) -> str:
    if int(conflict.get("conflict_count") or 0) > 0:
        return "blocked_conflict"
    if left_features["ocr_missing"] and right_features["ocr_missing"]:
        return "review_required"
    if (left_features["ocr_missing"] and _has_identity(right_features)) or (right_features["ocr_missing"] and _has_identity(left_features)):
        return "blank_or_dropped_back"
    if clues["shared_email"] or clues["shared_phone"] or clues["shared_domains"]:
        return "pair_proposed"
    if (_has_identity(left_features) and right_features["has_backside_cue"]) or (_has_identity(right_features) and left_features["has_backside_cue"]):
        return "pair_proposed"
    return "review_required"


def _has_identity(features: dict[str, Any]) -> bool:
    return bool(features.get("has_identity"))


def _front_back_order(*, left: dict[str, Any], right: dict[str, Any], left_features: dict[str, Any], right_features: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any] | None, str]:
    if _has_identity(left_features) and not _has_identity(right_features):
        return left, right, "front_back"
    if _has_identity(right_features) and not _has_identity(left_features):
        return right, left, "back_front"
    return left, right, "order_unknown"


def _merge_evidence(*, front: dict[str, Any] | None, back: dict[str, Any] | None, state: str, conflict: dict[str, Any]) -> dict[str, Any]:
    if front is None:
        return {"state": "review_required", "direct_sink_update_allowed": False}
    front_fields = dict(front.get("extracted_fields") or {})
    back_fields = dict(back.get("extracted_fields") or {}) if back else {}
    merged = dict(front_fields)
    augmented: list[str] = []
    for field, value in back_fields.items():
        if field not in merged and value:
            merged[field] = value
            augmented.append(field)
    if state == "blocked_conflict":
        merge_state = "blocked_conflict"
    elif state == "pair_proposed":
        merge_state = "pair_merge_evidence_ready"
    elif state in {"front_only", "blank_or_dropped_back"}:
        merge_state = state
    else:
        merge_state = "review_required"
    return {
        "state": merge_state,
        "merged_fields": merged if state in {"pair_proposed", "front_only", "blank_or_dropped_back"} else {},
        "backside_augmented_fields": sorted(augmented),
        "conflict_fields": list(conflict.get("conflict_fields") or []),
        "direct_sink_update_allowed": False,
    }


def _state_reason(*, state: str, clues: dict[str, Any], conflict: dict[str, Any]) -> str:
    if state == "pair_proposed":
        if clues.get("shared_email"):
            return "shared_email"
        if clues.get("shared_phone"):
            return "shared_phone"
        if clues.get("shared_domains"):
            return "shared_domain"
        return "identity_plus_backside_contextual_cues"
    if state == "blank_or_dropped_back":
        return "adjacent page appears blank or lacks OCR while companion has identity evidence"
    if state == "blocked_conflict":
        return "conflicting identity evidence: " + ",".join(conflict.get("conflict_fields") or [])
    return "insufficient deterministic side-pair evidence"


def _review_requests(edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    requests: list[dict[str, Any]] = []
    for edge in edges:
        if edge.get("state") not in {"review_required", "blocked_conflict"}:
            continue
        requests.append(
            {
                "request_id": f"{edge.get('edge_id')}-app-intelligence-review",
                "request_kind": "front_back_side_pair_review",
                "bounded_question": "Do these adjacent operator-declared positive-control scanner pages represent the front and back of the same business card?",
                "allowed_outputs": [
                    "same_card_pair",
                    "not_same_card",
                    "blank_or_dropped_back",
                    "front_only",
                    "needs_more_ocr_or_visual_evidence",
                ],
                "evidence": {
                    "edge_id": edge.get("edge_id"),
                    "state": edge.get("state"),
                    "reason": edge.get("reason"),
                    "page_numbers": edge.get("page_numbers"),
                    "deterministic_clues": edge.get("deterministic_clues"),
                    "conflict_evidence": edge.get("conflict_evidence"),
                },
                "private_paths_redacted": True,
                "private_filenames_redacted": True,
            }
        )
    return requests


def _counts(*, drafts: list[dict[str, Any]], edges: list[dict[str, Any]], review_requests: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "contact_drafts": len(drafts),
        "scanner_page_drafts": sum(1 for draft in drafts if draft.get("media_kind") == "pdf_page"),
        "edges": len(edges),
        "pair_proposed": sum(1 for edge in edges if edge.get("state") == "pair_proposed"),
        "review_required": sum(1 for edge in edges if edge.get("state") == "review_required"),
        "front_only": sum(1 for edge in edges if edge.get("state") == "front_only"),
        "blank_or_dropped_back": sum(1 for edge in edges if edge.get("state") == "blank_or_dropped_back"),
        "blocked_conflict": sum(1 for edge in edges if edge.get("state") == "blocked_conflict"),
        "backside_augmented_edges": sum(
            1 for edge in edges if dict(edge.get("merge_evidence") or {}).get("backside_augmented_fields")
        ),
        "app_intelligence_review_requests": len(review_requests),
    }


def _state(*, drafts: list[dict[str, Any]], edges: list[dict[str, Any]]) -> str:
    if not drafts:
        return "blocked"
    if any(edge.get("state") in {"review_required", "blocked_conflict"} for edge in edges):
        return "front_back_review_required"
    if any(edge.get("state") == "pair_proposed" for edge in edges):
        return "front_back_pair_evidence_ready"
    return "front_back_evidence_collected"


def _edge_digest(edges: list[dict[str, Any]]) -> str:
    digest = hashlib.sha256()
    for edge in edges:
        digest.update(str(edge.get("edge_id") or "").encode("utf-8"))
        digest.update(str(edge.get("state") or "").encode("utf-8"))
    return digest.hexdigest()[:12] if edges else "no-edges"


def _ensure_runtime_output_not_repo(output_root: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    try:
        output_root.resolve().relative_to(repo_root)
    except ValueError:
        return
    raise ValueError(f"positive control side-pair output root is inside the repo: {output_root}")

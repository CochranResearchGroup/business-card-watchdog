from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .config import AppConfig
from .contact import build_contact_candidate
from .models import utc_now
from .positive_control_crop_workbench import build_positive_control_crop_workbench


POSITIVE_CONTROL_OCR_DRAFTS_SCHEMA = "business-card-watchdog.positive-control-ocr-contact-drafts.v1"
CONTACT_DRAFT_SCHEMA = "business-card-watchdog.positive-control-contact-draft.v1"


def build_positive_control_ocr_contact_drafts(
    config: AppConfig,
    *,
    write: bool = True,
    ocr_text_by_candidate_id: dict[str, str] | None = None,
) -> dict[str, Any]:
    corpus_root = config.data_dir / "positive_control_corpus"
    crop_workbench = build_positive_control_crop_workbench(config, write=write)
    accepted_candidates = _accepted_candidates(crop_workbench)
    ocr_text = dict(ocr_text_by_candidate_id or {})
    draft_id = f"positive-control-ocr-drafts-{utc_now().replace(':', '-')}-{_candidate_digest(accepted_candidates)}"
    draft_dir = corpus_root / "ocr_contact_drafts" / draft_id
    contact_draft_dir = draft_dir / "drafts"
    report_path = draft_dir / "ocr_contact_drafts.json"
    drafts = [
        _contact_draft(
            candidate=candidate,
            ocr_text=ocr_text.get(str(candidate.get("candidate_id") or "")),
            contact_draft_dir=contact_draft_dir,
            write=write,
        )
        for candidate in accepted_candidates
    ]
    counts = _counts(drafts)
    state = _state(crop_workbench=crop_workbench, drafts=drafts)
    payload: dict[str, Any] = {
        "schema": POSITIVE_CONTROL_OCR_DRAFTS_SCHEMA,
        "generated_at": utc_now(),
        "state": state if write else ("ready_for_runtime_ocr_contact_drafts" if state != "blocked" else "blocked"),
        "draft_id": draft_id,
        "crop_workbench_id": crop_workbench.get("workbench_id"),
        "crop_workbench_state": crop_workbench.get("state"),
        "accepted_crop_candidate_count": len(accepted_candidates),
        "contact_draft_count": len(drafts),
        "contact_drafts": drafts,
        "counts": counts,
        "review_items": [
            item
            for draft in drafts
            for item in list(draft.get("review_items") or [])
            if isinstance(item, dict)
        ],
        "private_paths_redacted": True,
        "private_filenames_redacted": True,
        "operator_declared_known_positive_only": True,
        "contacts_review_required": True,
        "dry_run": True,
        "routing_allowed": False,
        "enrichment_allowed": False,
        "sink_payloads_created": 0,
        "ocr_attempted": len(accepted_candidates),
        "pdfs_rasterized": int(crop_workbench.get("pdfs_rasterized") or 0),
        "crops_created": 0,
        "writes_attempted": 0,
        "network_calls_made": 0,
        "live_sink_calls_made": False,
        "public_web_search_used": False,
        "paid_enrichment_used": False,
        "runtime_artifact_written": False,
        "report_path": None,
        "contact_draft_dir": str(contact_draft_dir) if write and state != "blocked" else None,
        "commands": {
            "positive_control_ocr_contact_drafts": "positive-control-ocr-contact-drafts --json",
            "positive_control_ocr_contact_drafts_preview": "positive-control-ocr-contact-drafts --no-write --json",
            "positive_control_crop_workbench": "positive-control-crop-workbench --json",
        },
        "explicit_stop_conditions": [
            "This surface processes accepted known-card crop candidates only.",
            "Every contact draft remains review-required and dry-run.",
            "Missing OCR is recorded as provenance; no contact data is fabricated.",
            "Backside-only fields are stored as augmentation evidence, not direct sink updates.",
            "Do not enrich, route, create sink payloads, write contacts, read back sinks, search public web, or call paid providers.",
            "Do not commit runtime OCR text, contact drafts, crops, or private media to git.",
        ],
    }
    if write and state != "blocked":
        _ensure_runtime_output_not_repo(corpus_root)
        draft_dir.mkdir(parents=True, exist_ok=True)
        report_payload = payload | {
            "runtime_artifact_written": True,
            "report_path": str(report_path),
        }
        report_path.write_text(json.dumps(report_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        payload["runtime_artifact_written"] = True
        payload["report_path"] = str(report_path)
    return payload


def _accepted_candidates(crop_workbench: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = [
        candidate
        for source in list(crop_workbench.get("source_results") or [])
        if isinstance(source, dict)
        for unit in list(source.get("processing_units") or [])
        if isinstance(unit, dict)
        for candidate in list(unit.get("crop_candidates") or [])
        if isinstance(candidate, dict) and candidate.get("state") == "accepted_for_ocr_workbench"
    ]
    if not candidates and crop_workbench.get("state") == "ready_for_runtime_crop_workbench":
        candidates = [
            _runtime_pdf_page_placeholder_candidate(source=source, unit=unit)
            for source in list(crop_workbench.get("source_results") or [])
            if isinstance(source, dict)
            for unit in list(source.get("processing_units") or [])
            if isinstance(unit, dict)
            and unit.get("media_kind") == "pdf_page"
            and unit.get("state") == "requires_runtime_page_materialization"
        ]
    candidates.sort(key=lambda candidate: str(candidate.get("candidate_id") or ""))
    return candidates


def _runtime_pdf_page_placeholder_candidate(*, source: dict[str, Any], unit: dict[str, Any]) -> dict[str, Any]:
    unit_id = str(unit.get("unit_id") or "")
    return {
        "schema": "business-card-watchdog.positive-control-crop-candidate-preview.v1",
        "candidate_id": f"{unit_id}-crop-001",
        "unit_id": unit_id,
        "entry_id": source.get("entry_id"),
        "sha256_prefix": source.get("sha256_prefix"),
        "source_kind": source.get("source_kind"),
        "media_kind": "pdf_page",
        "page_number": unit.get("page_number"),
        "page_role": unit.get("page_role"),
        "candidate_kind": "primary_card_candidate",
        "box": {},
        "quality": {"ocr_readiness": "requires_runtime_page_materialization"},
        "state": "accepted_for_ocr_workbench",
        "artifact_path": None,
        "requires_review": True,
        "requires_app_intelligence": True,
        "source_path_redacted": True,
        "source_filename_redacted": True,
    }


def _contact_draft(
    *,
    candidate: dict[str, Any],
    ocr_text: str | None,
    contact_draft_dir: Path,
    write: bool,
) -> dict[str, Any]:
    candidate_id = str(candidate.get("candidate_id") or "")
    raw_text = str(ocr_text or "").strip()
    ocr_provenance = _ocr_provenance(raw_text)
    extracted = _extract_fields(raw_text)
    contact_candidate = build_contact_candidate(
        extracted,
        source="positive_control_ocr_workbench",
    )
    confidence = _field_confidence(extracted=extracted, ocr_provenance=ocr_provenance)
    review_items = _review_items(candidate=candidate, extracted=extracted, ocr_provenance=ocr_provenance)
    artifact_path = contact_draft_dir / f"{candidate_id}.json"
    draft: dict[str, Any] = {
        "schema": CONTACT_DRAFT_SCHEMA,
        "draft_id": f"draft-{candidate_id}",
        "candidate_id": candidate_id,
        "entry_id": candidate.get("entry_id"),
        "sha256_prefix": candidate.get("sha256_prefix"),
        "source_kind": candidate.get("source_kind"),
        "media_kind": candidate.get("media_kind"),
        "page_number": candidate.get("page_number"),
        "page_role": candidate.get("page_role"),
        "candidate_kind": candidate.get("candidate_kind"),
        "ocr_provenance": ocr_provenance,
        "extracted_fields": extracted,
        "normalized_contact": contact_candidate,
        "field_confidence": confidence,
        "backside_augmentation_evidence": _backside_augmentation(candidate=candidate, extracted=extracted),
        "review_items": review_items,
        "review_required": True,
        "routing_allowed": False,
        "enrichment_allowed": False,
        "sink_write_allowed": False,
        "artifact_path": str(artifact_path) if write else None,
        "private_paths_redacted": True,
        "private_filenames_redacted": True,
    }
    if write:
        contact_draft_dir.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text(json.dumps(draft, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return draft


def _ocr_provenance(raw_text: str) -> dict[str, Any]:
    if raw_text:
        return {
            "state": "ocr_text_available",
            "source": "adapter_raw_text",
            "raw_text": raw_text,
            "missing_ocr_reason": None,
            "character_count": len(raw_text),
        }
    return {
        "state": "ocr_missing",
        "source": "missing_ocr_reason",
        "raw_text": "",
        "missing_ocr_reason": "No OCR adapter output was available for this accepted crop candidate.",
        "character_count": 0,
    }


def _extract_fields(raw_text: str) -> dict[str, Any]:
    if not raw_text.strip():
        return {}
    lines = [" ".join(line.strip().split()) for line in raw_text.splitlines() if line.strip()]
    joined = "\n".join(lines)
    fields: dict[str, Any] = {}
    email = _first_match(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", joined)
    phone = _first_match(r"(?:\+?1[\s.-]?)?(?:\(?\d{3}\)?[\s.-]?)\d{3}[\s.-]?\d{4}", joined)
    website = _first_match(r"(?:https?://)?(?:www\.)?[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?:/[^\s]*)?", joined)
    if lines:
        fields["full_name"] = lines[0]
    if len(lines) > 1 and "@" not in lines[1] and not re.search(r"\d{3}", lines[1]):
        fields["organization"] = lines[1]
    if email:
        fields["email"] = email
    if phone:
        fields["phone"] = phone
    if website and website != email:
        fields["website"] = website
    fields["notes"] = "Extracted from accepted positive-control crop candidate; review required before use."
    return fields


def _first_match(pattern: str, text: str) -> str:
    match = re.search(pattern, text)
    return match.group(0) if match else ""


def _field_confidence(*, extracted: dict[str, Any], ocr_provenance: dict[str, Any]) -> dict[str, Any]:
    if ocr_provenance["state"] == "ocr_missing":
        return {
            "overall": "missing_ocr",
            "fields_present": 0,
            "needs_review": True,
            "reason": "OCR text is missing.",
        }
    high_confidence = sum(1 for key in ("email", "phone", "website") if extracted.get(key))
    return {
        "overall": "review" if high_confidence < 2 else "medium",
        "fields_present": len(extracted),
        "high_confidence_contact_points": high_confidence,
        "needs_review": True,
        "reason": "All positive-control OCR drafts require operator review before routing.",
    }


def _review_items(
    *,
    candidate: dict[str, Any],
    extracted: dict[str, Any],
    ocr_provenance: dict[str, Any],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    candidate_id = str(candidate.get("candidate_id") or "")
    if ocr_provenance["state"] == "ocr_missing":
        items.append(
            {
                "review_item_id": f"{candidate_id}-missing-ocr",
                "kind": "missing_ocr",
                "severity": "blocking",
                "message": "OCR text is missing for this accepted crop candidate.",
            }
        )
    if not extracted.get("email") and not extracted.get("phone"):
        items.append(
            {
                "review_item_id": f"{candidate_id}-missing-contact-points",
                "kind": "missing_contact_points",
                "severity": "review",
                "message": "No email or phone was extracted from this crop candidate.",
            }
        )
    if _is_backside_role(str(candidate.get("page_role") or "")):
        items.append(
            {
                "review_item_id": f"{candidate_id}-backside-augmentation",
                "kind": "backside_augmentation_review",
                "severity": "review",
                "message": "Backside-only fields must augment a reviewed front-side contact, not create a direct sink update.",
            }
        )
    return items


def _backside_augmentation(*, candidate: dict[str, Any], extracted: dict[str, Any]) -> dict[str, Any]:
    page_role = str(candidate.get("page_role") or "")
    backside = _is_backside_role(page_role)
    return {
        "is_backside_candidate": backside,
        "fields": extracted if backside else {},
        "direct_sink_update_allowed": False,
    }


def _is_backside_role(page_role: str) -> bool:
    return page_role in {"back", "back_candidate", "business_card_backside"} or page_role.startswith("back_")


def _counts(drafts: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "accepted_crop_candidates": len(drafts),
        "contact_drafts": len(drafts),
        "ocr_text_available": sum(1 for draft in drafts if dict(draft.get("ocr_provenance") or {}).get("state") == "ocr_text_available"),
        "missing_ocr": sum(1 for draft in drafts if dict(draft.get("ocr_provenance") or {}).get("state") == "ocr_missing"),
        "review_required_drafts": sum(1 for draft in drafts if draft.get("review_required") is True),
        "drafts_with_email": sum(1 for draft in drafts if dict(draft.get("extracted_fields") or {}).get("email")),
        "drafts_with_phone": sum(1 for draft in drafts if dict(draft.get("extracted_fields") or {}).get("phone")),
        "backside_augmentation_candidates": sum(
            1
            for draft in drafts
            if dict(draft.get("backside_augmentation_evidence") or {}).get("is_backside_candidate") is True
        ),
        "review_items": sum(len(list(draft.get("review_items") or [])) for draft in drafts),
        "sink_payloads": 0,
    }


def _state(*, crop_workbench: dict[str, Any], drafts: list[dict[str, Any]]) -> str:
    if crop_workbench.get("state") == "blocked" or not drafts:
        return "blocked"
    if any(dict(draft.get("ocr_provenance") or {}).get("state") == "ocr_text_available" for draft in drafts):
        return "contact_drafts_review_required"
    return "ocr_missing_review_required"


def _candidate_digest(candidates: list[dict[str, Any]]) -> str:
    digest = hashlib.sha256()
    for candidate in candidates:
        digest.update(str(candidate.get("candidate_id") or "").encode("utf-8"))
    return digest.hexdigest()[:12] if candidates else "no-candidates"


def _ensure_runtime_output_not_repo(output_root: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    try:
        output_root.resolve().relative_to(repo_root)
    except ValueError:
        return
    raise ValueError(f"positive control OCR draft output root is inside the repo: {output_root}")

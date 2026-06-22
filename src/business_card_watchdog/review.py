from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal


ReviewStatus = Literal["pass", "needs_review"]
ReviewAction = Literal[
    "approve_for_routing",
    "approve_enrichment_merge",
    "keep_needs_review",
    "request_enrichment",
    "resolve_duplicate",
    "reject_not_card",
    "skip",
]


@dataclass(frozen=True)
class ReviewAssessment:
    status: ReviewStatus
    reasons: list[str] = field(default_factory=list)
    missing_fields: list[str] = field(default_factory=list)

    @property
    def needs_review(self) -> bool:
        return self.status == "needs_review"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def assess_contact_spec(spec: dict[str, Any]) -> ReviewAssessment:
    missing: list[str] = []
    reasons: list[str] = []

    full_name = _clean(spec.get("full_name") or spec.get("name"))
    email = _clean(spec.get("email"))
    phone = _clean(spec.get("phone"))
    organization = _clean(spec.get("organization"))

    if not full_name:
        missing.append("full_name")
        reasons.append("missing full_name")

    if not (email or phone or organization):
        missing.append("email_or_phone_or_organization")
        reasons.append("missing all routing identity fields")

    if _clean(spec.get("uncertain")):
        reasons.append("spec has uncertain marker")

    status: ReviewStatus = "needs_review" if reasons else "pass"
    return ReviewAssessment(status=status, reasons=reasons, missing_fields=missing)


def write_review_packet(
    *,
    packet_path: Path,
    image_path: Path,
    spec: dict[str, Any],
    assessment: ReviewAssessment,
    contact_candidate: dict[str, Any] | None = None,
    extraction_quality: dict[str, Any] | None = None,
) -> Path:
    packet_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "business-card-watchdog.review-packet.v1",
        "image_path": str(image_path),
        "assessment": assessment.to_dict(),
        "observed_fields": {
            key: spec.get(key)
            for key in ("full_name", "organization", "title", "email", "phone", "website", "notes")
            if spec.get(key)
        },
        "contact_candidate": contact_candidate or {},
        "extraction_quality": extraction_quality or {},
        "instructions": [
            "Keep only fields visible on the card unless an enrichment policy explicitly permits more.",
            "Put uncertain leftovers in notes with provenance.",
            "Do not route live sinks until this review packet is resolved.",
        ],
    }
    packet_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return packet_path


def build_review_submission(
    *,
    job_id: str,
    reviewer: str,
    action: ReviewAction,
    field_corrections: dict[str, Any] | None = None,
    crop_selection: dict[str, Any] | None = None,
    approved_enrichment_fields: list[str] | None = None,
    duplicate_resolution: dict[str, Any] | None = None,
    notes: str = "",
) -> dict[str, Any]:
    field_corrections = field_corrections or {}
    crop_selection = crop_selection or {}
    approved_enrichment_fields = approved_enrichment_fields or []
    duplicate_resolution = duplicate_resolution or {}
    _validate_field_corrections(field_corrections)
    _validate_crop_selection(crop_selection)
    _validate_approved_enrichment_fields(approved_enrichment_fields)
    _validate_duplicate_resolution(duplicate_resolution)
    return {
        "schema": "business-card-watchdog.review-submission.v1",
        "job_id": job_id,
        "reviewer": reviewer,
        "action": action,
        "field_corrections": field_corrections,
        "crop_selection": crop_selection,
        "approved_enrichment_fields": approved_enrichment_fields,
        "duplicate_resolution": duplicate_resolution,
        "notes": notes,
    }


def write_review_submission(path: Path, submission: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(submission, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _validate_field_corrections(corrections: dict[str, Any]) -> None:
    allowed = {"full_name", "organization", "title", "email", "phone", "website", "notes"}
    unknown = set(corrections) - allowed
    if unknown:
        raise ValueError(f"unsupported field corrections: {', '.join(sorted(unknown))}")


def _validate_crop_selection(crop_selection: dict[str, Any]) -> None:
    allowed = {"crop_id", "reason"}
    unknown = set(crop_selection) - allowed
    if unknown:
        raise ValueError(f"unsupported crop selection keys: {', '.join(sorted(unknown))}")


def _validate_approved_enrichment_fields(fields: list[str]) -> None:
    allowed = {"full_name", "organization", "title", "email", "phone", "website", "notes"}
    unknown = set(fields) - allowed
    if unknown:
        raise ValueError(f"unsupported enrichment fields: {', '.join(sorted(unknown))}")


def _validate_duplicate_resolution(resolution: dict[str, Any]) -> None:
    if not resolution:
        return
    allowed_keys = {"decision", "target_identity", "reason"}
    unknown = set(resolution) - allowed_keys
    if unknown:
        raise ValueError(f"unsupported duplicate resolution keys: {', '.join(sorted(unknown))}")
    decision = str(resolution.get("decision") or "").strip()
    if decision not in {"create_new", "merge_existing", "noop"}:
        raise ValueError("duplicate resolution decision must be create_new, merge_existing, or noop")

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal


QualityStatus = Literal["pass", "needs_review"]


@dataclass(frozen=True)
class ExtractionQualityAssessment:
    status: QualityStatus
    reasons: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    checks: dict[str, dict[str, Any]] = field(default_factory=dict)
    route_ready_allowed: bool = True

    @property
    def needs_review(self) -> bool:
        return self.status == "needs_review"

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["schema"] = "business-card-watchdog.extraction-quality.v1"
        return payload


def assess_extraction_quality(
    *,
    artifact_dir: Path,
    source_page: dict[str, Any] | None = None,
    side_candidate: dict[str, Any] | None = None,
) -> ExtractionQualityAssessment:
    reasons: list[str] = []
    checks: dict[str, dict[str, Any]] = {}
    metrics: dict[str, Any] = {}

    ocr_path = artifact_dir / "ocr.txt"
    ocr_text = ocr_path.read_text(encoding="utf-8") if ocr_path.exists() else ""
    ocr_tokens = re.findall(r"[A-Za-z0-9._%+-]+", ocr_text)
    metrics["ocr_token_count"] = len(ocr_tokens)
    metrics["ocr_text_sha256"] = hashlib.sha256(ocr_text.strip().encode("utf-8")).hexdigest()
    checks["ocr_text"] = {
        "state": "pass" if len(ocr_tokens) >= 3 else "needs_review",
        "path": str(ocr_path),
        "exists": ocr_path.exists(),
        "token_count": len(ocr_tokens),
    }
    if not ocr_path.exists():
        reasons.append("missing_ocr_text")
    elif len(ocr_tokens) < 3:
        reasons.append("ocr_text_too_short")

    crop_payload, crop_path = _load_crop_manifest(artifact_dir)
    crop_count = _crop_count(crop_payload)
    metrics["crop_count"] = crop_count
    checks["crop_manifest"] = {
        "state": "pass" if crop_count > 0 else "needs_review",
        "path": str(crop_path) if crop_path else "",
        "exists": crop_path is not None,
        "crop_count": crop_count,
    }
    if crop_path is None:
        reasons.append("missing_crop_manifest")
    elif crop_count <= 0:
        reasons.append("empty_crop_manifest")

    side_label = str((side_candidate or {}).get("side_label") or "")
    if source_page is not None:
        metrics["source_media_kind"] = source_page.get("media_kind")
        metrics["side_label"] = side_label or "missing"
        allowed = side_label == "front"
        checks["scanner_side"] = {
            "state": "pass" if allowed else "needs_review",
            "side_label": side_label or "missing",
            "reason": "" if allowed else "side_not_route_ready",
        }
        if not allowed:
            reasons.append("side_not_route_ready")

    status: QualityStatus = "needs_review" if reasons else "pass"
    return ExtractionQualityAssessment(
        status=status,
        reasons=reasons,
        metrics=metrics,
        checks=checks,
        route_ready_allowed=not reasons,
    )


def write_extraction_quality(path: Path, assessment: ExtractionQualityAssessment) -> Path:
    path.write_text(json.dumps(assessment.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _load_crop_manifest(artifact_dir: Path) -> tuple[dict[str, Any], Path | None]:
    for path in (artifact_dir / "manifest.json", artifact_dir / "crop_manifest.json"):
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}, path
        return payload if isinstance(payload, dict) else {}, path
    return {}, None


def _crop_count(payload: dict[str, Any]) -> int:
    crop_count = payload.get("crop_count")
    if isinstance(crop_count, int):
        return crop_count
    crops = payload.get("crops")
    if isinstance(crops, list):
        return len(crops)
    return 0

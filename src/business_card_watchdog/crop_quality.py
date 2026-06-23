from __future__ import annotations

from pathlib import Path
from typing import Any


CROP_QUALITY_SCHEMA = "business-card-watchdog.crop-quality.v1"
RECROP_PROPOSALS_SCHEMA = "business-card-watchdog.recrop-proposals.v1"


def build_crop_quality(
    *,
    run_id: str,
    job_id: str,
    source_image_path: Path,
    crop_manifest: dict[str, Any] | None = None,
    qr_evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    crops = [crop for crop in list((crop_manifest or {}).get("crops") or []) if isinstance(crop, dict)]
    image_dimensions = dict((crop_manifest or {}).get("image_dimensions") or {})
    source_width = int(image_dimensions.get("width") or 0)
    source_height = int(image_dimensions.get("height") or 0)
    if source_width <= 0 or source_height <= 0:
        source_width, source_height = _image_dimensions(source_image_path)
    qr_by_crop_path = _qr_by_crop_path(qr_evidence or {})
    crop_rows: list[dict[str, Any]] = []
    for crop in crops:
        crop_path = Path(str(crop.get("crop_path") or ""))
        bounds = dict(crop.get("bounds") or {})
        metrics = _image_metrics(crop_path)
        width = int(bounds.get("width") or metrics.get("width") or 0)
        height = int(bounds.get("height") or metrics.get("height") or 0)
        aspect_ratio = max(width, height) / max(1, min(width, height))
        edge_margin = _edge_margin(bounds, source_width=source_width, source_height=source_height)
        clipping_risk = edge_margin <= 4
        qr_summary = qr_by_crop_path.get(str(crop_path), {"qr_found": False, "decode_count": 0})
        text_density = float(metrics.get("text_density") or 0.0)
        text_line_count = int(metrics.get("text_line_count") or 0)
        blank_fraction = float(metrics.get("blank_fraction") or 0.0)
        card_boundary_coverage = (width * height) / max(source_width * source_height, 1) if source_width and source_height else 0.0
        qr_density = 1.0 if qr_summary.get("qr_found") else 0.0
        quality, reasons = _quality_state(
            aspect_ratio=aspect_ratio,
            blank_fraction=blank_fraction,
            card_boundary_coverage=card_boundary_coverage,
            text_density=text_density,
            text_line_count=text_line_count,
            qr_density=qr_density,
            clipping_risk=clipping_risk,
            width=width,
            height=height,
        )
        crop_rows.append(
            {
                "candidate_id": crop.get("candidate_id"),
                "work_item_id": crop.get("work_item_id"),
                "crop_path": str(crop_path),
                "bounds": bounds,
                "quality": quality,
                "reasons": reasons,
                "metrics": {
                    "card_boundary_coverage": round(card_boundary_coverage, 4),
                    "text_density": round(text_density, 4),
                    "text_line_count": text_line_count,
                    "qr_density": qr_density,
                    "blank_fraction": round(blank_fraction, 4),
                    "clipping_risk": clipping_risk,
                    "edge_margin": edge_margin,
                    "aspect_ratio": round(aspect_ratio, 4),
                    "width": width,
                    "height": height,
                },
                "qr_evidence": qr_summary,
            }
        )
    bad_count = len([row for row in crop_rows if row["quality"] == "bad"])
    qr_only_count = len([row for row in crop_rows if row["quality"] == "qr_only"])
    good_count = len([row for row in crop_rows if row["quality"] == "good"])
    state = (
        "no_crops"
        if not crop_rows
        else "bad"
        if bad_count
        else "qr_only"
        if qr_only_count and not good_count
        else "good"
        if good_count
        else "needs_review"
    )
    return {
        "schema": CROP_QUALITY_SCHEMA,
        "run_id": run_id,
        "job_id": job_id,
        "state": state,
        "source_image_path": str(source_image_path),
        "source_dimensions": {"width": source_width, "height": source_height},
        "crop_count": len(crop_rows),
        "good_count": good_count,
        "bad_count": bad_count,
        "qr_only_count": qr_only_count,
        "crops": crop_rows,
        "writes_attempted": 0,
        "network_calls_made": 0,
    }


def build_recrop_proposals(
    *,
    run_id: str,
    job_id: str,
    source_image_path: Path,
    crop_quality: dict[str, Any],
) -> dict[str, Any]:
    source_dimensions = dict(crop_quality.get("source_dimensions") or {})
    source_width = int(source_dimensions.get("width") or 0)
    source_height = int(source_dimensions.get("height") or 0)
    proposals: list[dict[str, Any]] = []
    for crop in list(crop_quality.get("crops") or []):
        if not isinstance(crop, dict):
            continue
        if crop.get("quality") not in {"bad", "qr_only"}:
            continue
        bounds = dict(crop.get("bounds") or {})
        expanded = _expand_bounds(bounds, source_width=source_width, source_height=source_height)
        if not expanded:
            continue
        proposals.append(
            {
                "proposal_id": f"{job_id}-{crop.get('candidate_id') or 'crop'}-recrop-001",
                "candidate_id": crop.get("candidate_id"),
                "work_item_id": crop.get("work_item_id"),
                "source_image_path": str(source_image_path),
                "original_crop_path": crop.get("crop_path"),
                "original_bounds": bounds,
                "proposed_bounds": expanded,
                "reason": "expand clipped or low-evidence crop for review",
                "state": "proposed",
                "routing_allowed": False,
            }
        )
    return {
        "schema": RECROP_PROPOSALS_SCHEMA,
        "run_id": run_id,
        "job_id": job_id,
        "state": "proposed" if proposals else "none",
        "proposal_count": len(proposals),
        "proposals": proposals,
        "writes_attempted": 0,
        "network_calls_made": 0,
    }


def redacted_crop_quality_summary(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "state": payload.get("state") or "unknown",
        "crop_count": int(payload.get("crop_count") or 0),
        "good_count": int(payload.get("good_count") or 0),
        "bad_count": int(payload.get("bad_count") or 0),
        "qr_only_count": int(payload.get("qr_only_count") or 0),
    }


def redacted_recrop_summary(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "state": payload.get("state") or "unknown",
        "proposal_count": int(payload.get("proposal_count") or 0),
    }


def _quality_state(
    *,
    aspect_ratio: float,
    blank_fraction: float,
    card_boundary_coverage: float,
    text_density: float,
    text_line_count: int,
    qr_density: float,
    clipping_risk: bool,
    width: int,
    height: int,
) -> tuple[str, list[str]]:
    reasons: list[str] = []
    if width <= 0 or height <= 0:
        return "bad", ["crop image dimensions are unavailable"]
    if clipping_risk:
        reasons.append("crop touches source edge")
    if not 1.25 <= aspect_ratio <= 2.4:
        reasons.append("crop aspect ratio is not business-card-like")
    if 0 < card_boundary_coverage < 0.05:
        reasons.append("crop covers too little of the source page")
    if blank_fraction > 0.94:
        reasons.append("crop is mostly blank")
    if text_density < 0.01 and qr_density <= 0:
        reasons.append("crop has low text and QR evidence")
    if qr_density > 0 and text_line_count <= 1:
        reasons.append("crop appears QR-only")
        return ("bad" if clipping_risk else "qr_only"), reasons
    if reasons:
        return "bad", reasons
    return "good", ["crop has card-like aspect and usable foreground density"]


def _image_metrics(path: Path) -> dict[str, Any]:
    try:
        import cv2  # type: ignore[import-not-found]
        import numpy as np  # type: ignore[import-not-found]
    except Exception:
        return {"width": 0, "height": 0, "text_density": 0.0, "blank_fraction": 1.0}
    image = cv2.imread(str(path))
    if image is None:
        return {"width": 0, "height": 0, "text_density": 0.0, "blank_fraction": 1.0}
    height, width = image.shape[:2]
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    _, threshold = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    line_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(12, width // 18), 3))
    line_mask = cv2.dilate(threshold, line_kernel, iterations=1)
    contours, _ = cv2.findContours(line_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    text_line_count = 0
    for contour in contours:
        _, _, contour_width, contour_height = cv2.boundingRect(contour)
        if contour_width >= max(18, contour_height * 1.8) and 2 <= contour_height <= max(4, height // 4):
            text_line_count += 1
    foreground = int(np.count_nonzero(threshold))
    area = max(width * height, 1)
    return {
        "width": width,
        "height": height,
        "text_density": foreground / area,
        "text_line_count": text_line_count,
        "blank_fraction": 1.0 - (foreground / area),
    }


def _image_dimensions(path: Path) -> tuple[int, int]:
    try:
        import cv2  # type: ignore[import-not-found]
    except Exception:
        return 0, 0
    image = cv2.imread(str(path))
    if image is None:
        return 0, 0
    height, width = image.shape[:2]
    return int(width), int(height)


def _edge_margin(bounds: dict[str, Any], *, source_width: int, source_height: int) -> int:
    if source_width <= 0 or source_height <= 0:
        return 0
    x = int(bounds.get("x") or 0)
    y = int(bounds.get("y") or 0)
    width = int(bounds.get("width") or 0)
    height = int(bounds.get("height") or 0)
    return min(x, y, max(0, source_width - (x + width)), max(0, source_height - (y + height)))


def _expand_bounds(bounds: dict[str, Any], *, source_width: int, source_height: int) -> dict[str, int] | None:
    if source_width <= 0 or source_height <= 0:
        return None
    x = int(bounds.get("x") or 0)
    y = int(bounds.get("y") or 0)
    width = int(bounds.get("width") or 0)
    height = int(bounds.get("height") or 0)
    if width <= 0 or height <= 0:
        return None
    pad_x = max(8, int(width * 0.12))
    pad_y = max(8, int(height * 0.12))
    x1 = max(0, x - pad_x)
    y1 = max(0, y - pad_y)
    x2 = min(source_width, x + width + pad_x)
    y2 = min(source_height, y + height + pad_y)
    if x2 <= x1 or y2 <= y1:
        return None
    return {"x": x1, "y": y1, "width": x2 - x1, "height": y2 - y1}


def _qr_by_crop_path(qr_evidence: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for item in list(qr_evidence.get("detections") or []):
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or "")
        if not path:
            continue
        rows[path] = {
            "qr_found": bool(item.get("qr_found")),
            "decode_count": int(item.get("decode_count") or 0),
            "payload_types": list(item.get("payload_types") or []),
        }
    return rows

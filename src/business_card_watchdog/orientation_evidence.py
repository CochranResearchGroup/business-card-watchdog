from __future__ import annotations

from pathlib import Path
from typing import Any


ORIENTATION_EVIDENCE_SCHEMA = "business-card-watchdog.orientation-evidence.v1"


def build_orientation_evidence(
    *,
    run_id: str,
    job_id: str,
    source_image_path: Path,
    output_dir: Path,
    crop_manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    images = [{"role": "source_page", "path": str(source_image_path)}]
    for crop in list((crop_manifest or {}).get("crops") or []):
        if not isinstance(crop, dict):
            continue
        crop_path = str(crop.get("crop_path") or "")
        if crop_path:
            images.append(
                {
                    "role": "candidate_crop",
                    "path": crop_path,
                    "candidate_id": crop.get("candidate_id"),
                    "work_item_id": crop.get("work_item_id"),
                }
            )

    analyzer_state = "available"
    analyzer_error = ""
    try:
        import cv2  # type: ignore[import-not-found]
        import numpy as np  # type: ignore[import-not-found]
    except Exception as exc:  # pragma: no cover - depends on optional runtime package.
        analyzer_state = "unavailable"
        analyzer_error = str(exc)
        cv2 = None  # type: ignore[assignment]
        np = None  # type: ignore[assignment]

    items: list[dict[str, Any]] = []
    for index, image_ref in enumerate(images):
        path = Path(str(image_ref["path"]))
        item: dict[str, Any] = {
            "role": image_ref.get("role"),
            "path": str(path),
            "candidate_id": image_ref.get("candidate_id"),
            "work_item_id": image_ref.get("work_item_id"),
            "exists": path.exists(),
            "state": "analyzer_unavailable" if cv2 is None else "scanned",
            "selected_rotation_degrees": 0,
            "confidence": "none",
            "normalized_image_path": "",
            "scores": [],
        }
        if cv2 is None or np is None:
            item["error"] = analyzer_error
            items.append(item)
            continue
        if not path.exists():
            item["state"] = "image_missing"
            items.append(item)
            continue
        image = cv2.imread(str(path))
        if image is None:
            item["state"] = "unreadable_image"
            items.append(item)
            continue
        scores = [_score_rotation(cv2, np, image, rotation) for rotation in (0, 90, 180, 270)]
        ranked = sorted(scores, key=lambda row: float(row["score"]), reverse=True)
        best = ranked[0]
        runner_up = ranked[1] if len(ranked) > 1 else {"score": 0.0}
        margin = float(best["score"]) - float(runner_up["score"])
        item["scores"] = scores
        item["selected_rotation_degrees"] = int(best["rotation_degrees"])
        item["score"] = round(float(best["score"]), 4)
        item["score_margin"] = round(margin, 4)
        item["confidence"] = (
            "high"
            if int(best["rotation_degrees"]) != 180 and float(best["score"]) >= 0.6 and margin >= 0.12
            else "low"
        )
        if item["confidence"] == "high":
            if item["selected_rotation_degrees"] == 0:
                item["state"] = "already_normalized"
            else:
                normalized_dir = output_dir / "orientation_normalized"
                normalized_dir.mkdir(parents=True, exist_ok=True)
                normalized_path = normalized_dir / _normalized_name(path, index, int(best["rotation_degrees"]))
                rotated = _rotate_image(cv2, image, int(best["rotation_degrees"]))
                if cv2.imwrite(str(normalized_path), rotated):
                    item["state"] = "normalized_derivative_created"
                    item["normalized_image_path"] = str(normalized_path)
                else:
                    item["state"] = "normalization_write_failed"
        else:
            item["state"] = "needs_app_intelligence_review"
        items.append(item)

    normalized_count = len(
        [item for item in items if item.get("state") == "normalized_derivative_created"]
    )
    needs_review_count = len(
        [item for item in items if item.get("state") == "needs_app_intelligence_review"]
    )
    return {
        "schema": ORIENTATION_EVIDENCE_SCHEMA,
        "run_id": run_id,
        "job_id": job_id,
        "state": "needs_app_intelligence_review"
        if needs_review_count
        else "normalized"
        if normalized_count
        else "already_normalized"
        if analyzer_state == "available"
        else "analyzer_unavailable",
        "analyzer": {"name": "opencv_orientation_heuristics", "state": analyzer_state},
        "source_image_path": str(source_image_path),
        "image_count": len(images),
        "normalized_count": normalized_count,
        "needs_review_count": needs_review_count,
        "items": items,
        "writes_attempted": 0,
        "network_calls_made": 0,
    }


def redacted_orientation_summary(payload: dict[str, Any]) -> dict[str, Any]:
    items = [item for item in list(payload.get("items") or []) if isinstance(item, dict)]
    rotations = sorted({int(item.get("selected_rotation_degrees") or 0) for item in items})
    states = sorted({str(item.get("state") or "unknown") for item in items})
    return {
        "state": payload.get("state") or "unknown",
        "analyzer_state": (payload.get("analyzer") or {}).get("state") or "unknown",
        "image_count": int(payload.get("image_count") or 0),
        "normalized_count": int(payload.get("normalized_count") or 0),
        "needs_review_count": int(payload.get("needs_review_count") or 0),
        "selected_rotations": rotations,
        "item_states": states,
    }


def _score_rotation(cv2: Any, np: Any, image: Any, rotation: int) -> dict[str, Any]:
    rotated = _rotate_image(cv2, image, rotation)
    height, width = rotated.shape[:2]
    gray = cv2.cvtColor(rotated, cv2.COLOR_BGR2GRAY)
    _, threshold = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    line_kernel_width = max(12, width // 18)
    line_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (line_kernel_width, 3))
    line_mask = cv2.dilate(threshold, line_kernel, iterations=1)
    contours, _ = cv2.findContours(line_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    horizontal_lines = 0
    horizontal_area = 0.0
    foreground_area = 0
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        area = w * h
        if area < 12:
            continue
        foreground_area += area
        if w >= max(12, h * 1.8) and 2 <= h <= max(4, height // 5):
            horizontal_lines += 1
            horizontal_area += area
    text_line_score = min(1.0, horizontal_lines / 4.0) * 0.7 + min(1.0, horizontal_area / 5000.0) * 0.3
    aspect = width / max(height, 1)
    aspect_score = 1.0 if 1.25 <= aspect <= 2.3 else 0.55 if width >= height else 0.0
    top = threshold[: height // 2, :]
    bottom = threshold[height // 2 :, :]
    top_pixels = int(np.count_nonzero(top))
    bottom_pixels = int(np.count_nonzero(bottom))
    top_bias_score = 0.5
    if top_pixels + bottom_pixels > 0:
        top_ratio = top_pixels / (top_pixels + bottom_pixels)
        top_bias_score = max(0.0, min(1.0, (top_ratio - 0.35) / 0.35))
    content_score = min(1.0, foreground_area / max(width * height * 0.015, 1.0))
    score = (
        aspect_score * 0.25
        + text_line_score * 0.35
        + top_bias_score * 0.25
        + content_score * 0.15
    )
    return {
        "rotation_degrees": rotation,
        "score": round(float(score), 4),
        "aspect_score": round(float(aspect_score), 4),
        "text_line_score": round(float(text_line_score), 4),
        "top_bias_score": round(float(top_bias_score), 4),
        "content_score": round(float(content_score), 4),
        "horizontal_line_count": horizontal_lines,
        "dimensions": {"width": int(width), "height": int(height)},
    }


def _rotate_image(cv2: Any, image: Any, rotation: int) -> Any:
    if rotation == 90:
        return cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)
    if rotation == 180:
        return cv2.rotate(image, cv2.ROTATE_180)
    if rotation == 270:
        return cv2.rotate(image, cv2.ROTATE_90_COUNTERCLOCKWISE)
    return image


def _normalized_name(path: Path, index: int, rotation: int) -> str:
    stem = path.stem or f"image-{index}"
    return f"{stem}-rot{rotation}.jpg"

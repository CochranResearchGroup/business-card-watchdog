from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any


CANDIDATE_WORK_ITEMS_SCHEMA = "business-card-watchdog.card-candidate-work-items.v1"
CANDIDATE_CROPS_SCHEMA = "business-card-watchdog.card-candidate-crops.v1"


def build_candidate_work_item_manifest(candidate_manifest: dict[str, Any]) -> dict[str, Any]:
    source_job_id = str(candidate_manifest["source_job_id"])
    source_image_path = str(candidate_manifest["source_image_path"])
    candidates = [
        candidate
        for candidate in list(candidate_manifest.get("candidates") or [])
        if isinstance(candidate, dict)
    ]
    work_items = [
        {
            "work_item_id": f"{candidate['candidate_id']}-ocr-verification",
            "candidate_id": str(candidate["candidate_id"]),
            "candidate_index": int(candidate["candidate_index"]),
            "parent_job_id": source_job_id,
            "source_image_path": source_image_path,
            "box": candidate["box"],
            "phase": "pending_ocr_app_intelligence_verification",
            "state": "pending",
            "requires_crop_before_ocr": True,
            "requires_human_or_app_intelligence_verification": True,
            "routing_allowed": False,
            "enrichment_allowed": False,
            "sink_write_allowed": False,
        }
        for candidate in candidates
    ]
    return {
        "schema": CANDIDATE_WORK_ITEMS_SCHEMA,
        "parent_job_id": source_job_id,
        "source_image_path": source_image_path,
        "work_item_count": len(work_items),
        "work_items": work_items,
        "parent_candidate_manifest_schema": candidate_manifest.get("schema"),
        "explicit_stop_conditions": [
            "Work items are pending OCR/App Intelligence verification only.",
            "Do not route, enrich, or write contacts until a child work item produces reviewed contact data.",
            "Do not crop or process private source images without an explicit operator-selected run/source.",
        ],
    }


def materialize_candidate_crops(
    *,
    source_image_path: Path,
    work_item_manifest: dict[str, Any],
    crop_dir: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        import cv2  # type: ignore[import-not-found]
    except Exception as exc:  # pragma: no cover - candidate boxes require OpenCV.
        raise RuntimeError("OpenCV is required to materialize candidate crops") from exc

    image = cv2.imread(str(source_image_path))
    if image is None:
        raise RuntimeError(f"OpenCV could not read source image: {source_image_path}")

    image_height, image_width = image.shape[:2]
    crop_dir.mkdir(parents=True, exist_ok=True)
    updated_manifest = deepcopy(work_item_manifest)
    crop_records: list[dict[str, Any]] = []
    for item in updated_manifest["work_items"]:
        bounds = _clamped_box_bounds(item["box"], image_width=image_width, image_height=image_height)
        if bounds is None:
            item["state"] = "failed"
            item["phase"] = "crop_failed"
            item["error"] = "candidate box is outside source image bounds"
            continue
        x1, y1, x2, y2 = bounds
        crop = image[y1:y2, x1:x2]
        crop_path = crop_dir / f"{item['candidate_id']}.jpg"
        if not cv2.imwrite(str(crop_path), crop):
            item["state"] = "failed"
            item["phase"] = "crop_failed"
            item["error"] = "OpenCV failed to write crop image"
            continue
        crop_record = {
            "candidate_id": item["candidate_id"],
            "work_item_id": item["work_item_id"],
            "crop_path": str(crop_path),
            "source_image_path": str(source_image_path),
            "bounds": {"x": x1, "y": y1, "width": x2 - x1, "height": y2 - y1},
            "state": "crop_ready",
            "next_phase": "ocr_app_intelligence_verification",
        }
        crop_records.append(crop_record)
        item["state"] = "crop_ready"
        item["phase"] = "ready_for_ocr_app_intelligence_verification"
        item["crop_path"] = str(crop_path)
        item["crop_bounds"] = crop_record["bounds"]

    updated_manifest["work_item_count"] = len(updated_manifest["work_items"])
    updated_manifest["crop_ready_count"] = len(crop_records)
    return (
        {
            "schema": CANDIDATE_CROPS_SCHEMA,
            "parent_job_id": work_item_manifest["parent_job_id"],
            "source_image_path": str(source_image_path),
            "image_dimensions": {"width": image_width, "height": image_height},
            "crop_count": len(crop_records),
            "crops": crop_records,
            "explicit_stop_conditions": [
                "Candidate crops are image artifacts for OCR/App Intelligence verification only.",
                "Do not route, enrich, or write contacts from crops until reviewed contact data exists.",
            ],
        },
        updated_manifest,
    )


def _clamped_box_bounds(
    box: dict[str, Any],
    *,
    image_width: int,
    image_height: int,
) -> tuple[int, int, int, int] | None:
    x1 = max(0, int(box["x"]))
    y1 = max(0, int(box["y"]))
    x2 = min(image_width, x1 + max(0, int(box["width"])))
    y2 = min(image_height, y1 + max(0, int(box["height"])))
    if x2 <= x1 or y2 <= y1:
        return None
    return x1, y1, x2, y2

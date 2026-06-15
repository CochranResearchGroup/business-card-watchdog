from __future__ import annotations

from typing import Any


CANDIDATE_WORK_ITEMS_SCHEMA = "business-card-watchdog.card-candidate-work-items.v1"


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

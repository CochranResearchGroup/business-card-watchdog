from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any


QR_EVIDENCE_SCHEMA = "business-card-watchdog.qr-evidence.v1"


def build_qr_evidence(
    *,
    run_id: str,
    job_id: str,
    source_image_path: Path,
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

    detections: list[dict[str, Any]] = []
    decoder_state = "available"
    decoder_error = ""
    try:
        import cv2  # type: ignore[import-not-found]
    except Exception as exc:  # pragma: no cover - depends on optional runtime package.
        decoder_state = "unavailable"
        decoder_error = str(exc)
        cv2 = None  # type: ignore[assignment]

    for image_ref in images:
        path = Path(str(image_ref["path"]))
        image_result: dict[str, Any] = {
            "role": image_ref.get("role"),
            "path": str(path),
            "candidate_id": image_ref.get("candidate_id"),
            "work_item_id": image_ref.get("work_item_id"),
            "exists": path.exists(),
            "qr_found": False,
            "decode_count": 0,
            "payload_types": [],
            "detections": [],
        }
        if cv2 is None:
            image_result["state"] = "decoder_unavailable"
            image_result["error"] = decoder_error
            detections.append(image_result)
            continue
        if not path.exists():
            image_result["state"] = "image_missing"
            detections.append(image_result)
            continue
        image = cv2.imread(str(path))
        if image is None:
            image_result["state"] = "unreadable_image"
            detections.append(image_result)
            continue
        image_result["state"] = "scanned"
        decoded = _decode_qr_payloads(cv2, image)
        payload_types: list[str] = []
        for item in decoded:
            payload = str(item.get("payload") or "")
            payload_type = _payload_type(payload)
            payload_types.append(payload_type)
            image_result["detections"].append(
                {
                    "payload": payload,
                    "payload_sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest()
                    if payload
                    else "",
                    "payload_type": payload_type,
                    "bbox": item.get("bbox") or [],
                    "decode_state": "decoded" if payload else "detected_not_decoded",
                }
            )
        image_result["qr_found"] = bool(image_result["detections"])
        image_result["decode_count"] = len([row for row in image_result["detections"] if row["payload"]])
        image_result["payload_types"] = sorted(set(payload_types))
        detections.append(image_result)

    decoded_payloads = [
        detection
        for image_result in detections
        for detection in list(image_result.get("detections") or [])
        if isinstance(detection, dict) and detection.get("payload")
    ]
    qr_found = any(bool(image_result.get("qr_found")) for image_result in detections)
    return {
        "schema": QR_EVIDENCE_SCHEMA,
        "run_id": run_id,
        "job_id": job_id,
        "state": "found" if qr_found else "decoder_unavailable" if decoder_state == "unavailable" else "none_found",
        "decoder": {"name": "opencv_qrcode_detector", "state": decoder_state},
        "source_image_path": str(source_image_path),
        "image_count": len(images),
        "qr_found": qr_found,
        "decode_count": len(decoded_payloads),
        "payload_types": sorted({str(row.get("payload_type") or "unknown") for row in decoded_payloads}),
        "detections": detections,
        "writes_attempted": 0,
        "network_calls_made": 0,
    }


def redacted_qr_summary(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "state": payload.get("state") or "unknown",
        "qr_found": bool(payload.get("qr_found")),
        "decode_count": int(payload.get("decode_count") or 0),
        "payload_types": list(payload.get("payload_types") or []),
        "decoder_state": (payload.get("decoder") or {}).get("state") or "unknown",
        "image_count": int(payload.get("image_count") or 0),
    }


def _decode_qr_payloads(cv2: Any, image: Any) -> list[dict[str, Any]]:
    detector = cv2.QRCodeDetector()
    rows: list[dict[str, Any]] = []
    try:
        ok, decoded_info, points, _ = detector.detectAndDecodeMulti(image)
    except Exception:
        ok = False
        decoded_info = []
        points = None
    if ok:
        for index, payload in enumerate(decoded_info or []):
            rows.append({"payload": str(payload or ""), "bbox": _point_box(points, index)})
        return rows
    payload, points, _ = detector.detectAndDecode(image)
    if payload or points is not None:
        rows.append({"payload": str(payload or ""), "bbox": _point_box(points, 0)})
    return rows


def _point_box(points: Any, index: int) -> list[dict[str, float]]:
    if points is None:
        return []
    try:
        selected = points[index] if len(points.shape) == 3 else points
        return [{"x": float(point[0]), "y": float(point[1])} for point in selected]
    except Exception:
        return []


def _payload_type(payload: str) -> str:
    stripped = payload.strip().lower()
    if not stripped:
        return "empty"
    if stripped.startswith(("http://", "https://")):
        return "url"
    if stripped.startswith("mailto:"):
        return "email"
    if "begin:vcard" in stripped:
        return "vcard"
    return "text"

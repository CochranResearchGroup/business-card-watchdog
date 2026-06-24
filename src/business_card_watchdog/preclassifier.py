from __future__ import annotations

import struct
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal


CardCandidateDecision = Literal["likely_business_card", "not_business_card", "uncertain"]
CARD_CANDIDATE_BOXES_SCHEMA = "business-card-watchdog.card-candidate-boxes.v1"


@dataclass(frozen=True)
class ImageDimensions:
    width: int
    height: int
    format: str

    @property
    def aspect_ratio(self) -> float:
        long_side = max(self.width, self.height)
        short_side = max(1, min(self.width, self.height))
        return long_side / short_side

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CardCandidateAssessment:
    decision: CardCandidateDecision
    score: float
    reasons: list[str] = field(default_factory=list)
    dimensions: ImageDimensions | None = None
    analyzers: dict[str, Any] = field(default_factory=dict)

    @property
    def should_process(self) -> bool:
        return self.decision == "likely_business_card"

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        if self.dimensions is not None:
            payload["dimensions"] = self.dimensions.to_dict()
        return payload


def assess_business_card_candidate(path: Path, *, min_score: float = 0.55) -> CardCandidateAssessment:
    dimensions = read_image_dimensions(path)
    reasons: list[str] = []
    analyzers: dict[str, Any] = {}

    if dimensions is None:
        return CardCandidateAssessment(
            decision="uncertain",
            score=0.0,
            reasons=["could not read image dimensions without optional image libraries"],
            analyzers={"header": {"available": False}},
        )

    aspect_score = _score_business_card_aspect(dimensions.aspect_ratio)
    analyzers["aspect_ratio"] = {
        "ratio": dimensions.aspect_ratio,
        "score": aspect_score,
        "target": "1.45-2.15 long-side/short-side",
    }
    if aspect_score > 0:
        reasons.append("image aspect ratio is compatible with a business card crop")
    else:
        reasons.append("image aspect ratio is not business-card-like")

    rectangle = _opencv_rectangle_hint(path)
    analyzers["opencv_rectangle"] = rectangle
    rectangle_score = float(rectangle.get("score", 0.0))
    if rectangle_score > 0:
        count = int(rectangle.get("card_like_count", 1))
        if count > 1:
            reasons.append(f"detected {count} business-card-like rectangular contours")
        else:
            reasons.append("detected a business-card-like rectangular contour")
    elif rectangle.get("available") is False:
        reasons.append("OpenCV rectangle analyzer unavailable")

    text_layout = _opencv_text_layout_hint(path)
    analyzers["opencv_text_layout"] = text_layout
    text_layout_score = float(text_layout.get("score", 0.0)) if aspect_score >= 0.25 else 0.0
    if text_layout.get("document_like") is True:
        text_layout_score = 0.0
        reasons.append("document-like dense text layout requires App Intelligence review")
    if text_layout_score > 0:
        reasons.append("card-like aspect ratio with multiple horizontal text-line regions")

    score = max(rectangle_score, text_layout_score)
    if score < min_score:
        score = min(aspect_score, 0.45)
    if score >= min_score:
        decision: CardCandidateDecision = "likely_business_card"
    elif score <= 0.05:
        decision = "not_business_card"
    else:
        decision = "uncertain"

    return CardCandidateAssessment(
        decision=decision,
        score=round(score, 4),
        reasons=reasons,
        dimensions=dimensions,
        analyzers=analyzers,
    )


def build_card_candidate_box_manifest(
    *,
    assessment: CardCandidateAssessment,
    source_image_path: Path,
    job_id: str,
) -> dict[str, Any]:
    payload = assessment.to_dict()
    rectangle = dict(payload.get("analyzers", {}).get("opencv_rectangle") or {})
    boxes = [box for box in list(rectangle.get("boxes") or []) if isinstance(box, dict)]
    candidates = [
        {
            "candidate_id": f"{job_id}-card-{index:03d}",
            "candidate_index": index,
            "source_job_id": job_id,
            "source_image_path": str(source_image_path),
            "box": box,
            "preclassification_decision": assessment.decision,
            "preclassification_score": assessment.score,
            "analyzer": "opencv_rectangle",
            "requires_ocr_verification": True,
        }
        for index, box in enumerate(boxes, start=1)
    ]
    return {
        "schema": CARD_CANDIDATE_BOXES_SCHEMA,
        "source_job_id": job_id,
        "source_image_path": str(source_image_path),
        "candidate_count": len(candidates),
        "candidates": candidates,
        "preclassification": {
            "decision": assessment.decision,
            "score": assessment.score,
            "reasons": list(assessment.reasons),
            "dimensions": payload.get("dimensions"),
        },
        "analyzer_summary": {
            "opencv_rectangle_available": rectangle.get("available") is True,
            "card_like_count": int(rectangle.get("card_like_count") or 0),
            "area_fraction_total": float(rectangle.get("area_fraction_total") or 0.0),
        },
        "explicit_stop_conditions": [
            "Candidate boxes are deterministic pre-OCR evidence, not verified contacts.",
            "Do not route, enrich, or write contacts from candidate boxes without OCR/App Intelligence verification.",
        ],
    }


def read_image_dimensions(path: Path) -> ImageDimensions | None:
    with path.open("rb") as handle:
        header = handle.read(24)
        handle.seek(0)
        kind = _image_kind(header)
        if kind == "png":
            handle.seek(16)
            width, height = struct.unpack(">II", handle.read(8))
            return ImageDimensions(width=width, height=height, format="png")
        if kind == "gif":
            handle.seek(6)
            width, height = struct.unpack("<HH", handle.read(4))
            return ImageDimensions(width=width, height=height, format="gif")
        if kind == "jpeg":
            return _read_jpeg_dimensions(handle.read())
    return None


def _image_kind(header: bytes) -> str | None:
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if header.startswith((b"GIF87a", b"GIF89a")):
        return "gif"
    if header.startswith(b"\xff\xd8"):
        return "jpeg"
    return None


def _read_jpeg_dimensions(data: bytes) -> ImageDimensions | None:
    index = 2
    while index < len(data):
        if data[index] != 0xFF:
            index += 1
            continue
        marker = data[index + 1]
        index += 2
        if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}:
            height, width = struct.unpack(">HH", data[index + 3 : index + 7])
            return ImageDimensions(width=width, height=height, format="jpeg")
        if marker in {0xD8, 0xD9}:
            continue
        segment_length = struct.unpack(">H", data[index : index + 2])[0]
        index += segment_length
    return None


def _score_business_card_aspect(ratio: float) -> float:
    if 1.55 <= ratio <= 1.95:
        return 0.35
    if 1.45 <= ratio < 1.55 or 1.95 < ratio <= 2.15:
        return 0.25
    if 1.30 <= ratio < 1.45 or 2.15 < ratio <= 2.35:
        return 0.1
    return 0.0


def _opencv_rectangle_hint(path: Path) -> dict[str, Any]:
    try:
        import cv2  # type: ignore[import-not-found]
    except Exception:
        return {"available": False, "score": 0.0}

    image = cv2.imread(str(path))
    if image is None:
        return {"available": True, "score": 0.0, "reason": "cv2 could not read image"}
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    image_area = image.shape[0] * image.shape[1]
    boxes: list[dict[str, Any]] = []
    for contour in contours:
        area = cv2.contourArea(contour)
        if area < image_area * 0.005:
            continue
        peri = cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, 0.03 * peri, True)
        if len(approx) != 4:
            continue
        x, y, width, height = cv2.boundingRect(approx)
        ratio = max(width, height) / max(1, min(width, height))
        if 1.45 <= ratio <= 2.15:
            boxes.append(
                {
                    "x": x,
                    "y": y,
                    "width": width,
                    "height": height,
                    "area_fraction": round(area / max(1, image_area), 4),
                    "ratio": round(ratio, 4),
                }
            )

    boxes = _dedupe_boxes(boxes)
    boxes.sort(key=lambda box: float(box["area_fraction"]), reverse=True)
    count = len(boxes)
    area_total = min(1.0, sum(float(box["area_fraction"]) for box in boxes))
    score = 0.0
    if count == 1 and area_total >= 0.04:
        score = min(0.85, 0.56 + area_total)
    elif count > 1:
        meaningful_boxes = [box for box in boxes if float(box["area_fraction"]) >= 0.025]
        if len(meaningful_boxes) > 1:
            score = min(0.95, 0.62 + (0.08 * min(len(meaningful_boxes), 4)) + min(area_total, 0.2))
    return {
        "available": True,
        "score": round(score, 4),
        "contours": len(contours),
        "card_like_count": count,
        "boxes": boxes[:10],
        "area_fraction_total": round(area_total, 4),
    }


def _opencv_text_layout_hint(path: Path) -> dict[str, Any]:
    try:
        import cv2  # type: ignore[import-not-found]
        import numpy as np  # type: ignore[import-not-found]
    except Exception:
        return {"available": False, "score": 0.0}

    image = cv2.imread(str(path))
    if image is None:
        return {"available": True, "score": 0.0, "reason": "cv2 could not read image"}
    height, width = image.shape[:2]
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    _, threshold = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    line_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(18, width // 20), 3))
    line_mask = cv2.dilate(threshold, line_kernel, iterations=1)
    contours, _ = cv2.findContours(line_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    text_lines = 0
    text_area = 0
    for contour in contours:
        x, y, contour_width, contour_height = cv2.boundingRect(contour)
        area = contour_width * contour_height
        if contour_width < max(24, contour_height * 1.8):
            continue
        if contour_height < 3 or contour_height > max(8, height // 4):
            continue
        if area < 20:
            continue
        text_lines += 1
        text_area += area
    foreground_density = float(np.count_nonzero(threshold)) / max(width * height, 1)
    text_area_fraction = text_area / max(width * height, 1)
    score = 0.0
    document_like = text_lines > 10 or text_area_fraction > 0.24
    if text_lines >= 3 and 0.01 <= foreground_density <= 0.45 and not document_like:
        score = min(0.82, 0.56 + (0.035 * min(text_lines, 6)) + min(text_area_fraction, 0.05))
    return {
        "available": True,
        "score": round(score, 4),
        "text_line_count": text_lines,
        "foreground_density": round(foreground_density, 4),
        "text_area_fraction": round(text_area_fraction, 4),
        "document_like": document_like,
    }


def _dedupe_boxes(boxes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    for box in boxes:
        if not any(_box_iou(box, kept) > 0.75 for kept in deduped):
            deduped.append(box)
    return deduped


def _box_iou(left: dict[str, Any], right: dict[str, Any]) -> float:
    left_x2 = int(left["x"]) + int(left["width"])
    left_y2 = int(left["y"]) + int(left["height"])
    right_x2 = int(right["x"]) + int(right["width"])
    right_y2 = int(right["y"]) + int(right["height"])
    inter_x1 = max(int(left["x"]), int(right["x"]))
    inter_y1 = max(int(left["y"]), int(right["y"]))
    inter_x2 = min(left_x2, right_x2)
    inter_y2 = min(left_y2, right_y2)
    inter_area = max(0, inter_x2 - inter_x1) * max(0, inter_y2 - inter_y1)
    left_area = int(left["width"]) * int(left["height"])
    right_area = int(right["width"]) * int(right["height"])
    union = left_area + right_area - inter_area
    return inter_area / max(1, union)

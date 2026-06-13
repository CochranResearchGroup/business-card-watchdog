from __future__ import annotations

import struct
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal


CardCandidateDecision = Literal["likely_business_card", "not_business_card", "uncertain"]


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
        reasons.append("detected a business-card-like rectangular contour")
    elif rectangle.get("available") is False:
        reasons.append("OpenCV rectangle analyzer unavailable")

    score = max(aspect_score, rectangle_score)
    if score >= min_score:
        decision: CardCandidateDecision = "likely_business_card"
    elif score <= 0.15:
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
        return 0.65
    if 1.45 <= ratio < 1.55 or 1.95 < ratio <= 2.15:
        return 0.45
    if 1.30 <= ratio < 1.45 or 2.15 < ratio <= 2.35:
        return 0.2
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
    best: dict[str, Any] = {"available": True, "score": 0.0, "contours": len(contours)}
    for contour in contours:
        area = cv2.contourArea(contour)
        if area < image_area * 0.05:
            continue
        peri = cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, 0.03 * peri, True)
        if len(approx) != 4:
            continue
        x, y, width, height = cv2.boundingRect(approx)
        ratio = max(width, height) / max(1, min(width, height))
        if 1.45 <= ratio <= 2.15:
            score = min(0.9, 0.55 + (area / max(1, image_area)))
            if score > best["score"]:
                best = {
                    "available": True,
                    "score": round(score, 4),
                    "contours": len(contours),
                    "box": {"x": x, "y": y, "width": width, "height": height},
                    "area_fraction": round(area / max(1, image_area), 4),
                    "ratio": round(ratio, 4),
                }
    return best

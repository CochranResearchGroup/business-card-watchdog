from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from business_card_watchdog.models import SkillRunResult


def png_header(width: int, height: int) -> bytes:
    return (
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\rIHDR"
        + width.to_bytes(4, "big")
        + height.to_bytes(4, "big")
        + b"\x08\x02\x00\x00\x00"
        + b"\x00\x00\x00\x00"
        + b"\x00\x00\x00\x00IEND\xaeB`\x82"
    )


BUSINESS_CARD_PNG = png_header(350, 200)
SQUARE_PHOTO_PNG = png_header(200, 200)


SYNTHETIC_CONTACT_SPEC: dict[str, Any] = {
    "full_name": "Synthetic Fixture",
    "organization": "Fixture Labs",
    "title": "Validation Contact",
    "email": "fixture@example.test",
    "phone": "+1-555-0100",
    "notes": "Synthetic privacy-safe business-card fixture for dry-run validation.",
}


def write_synthetic_image(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(BUSINESS_CARD_PNG)
    return path


def write_square_image(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(SQUARE_PHOTO_PNG)
    return path


def write_multi_card_image(path: Path) -> Path:
    cv2 = __import__("cv2")
    np = __import__("numpy")
    image = np.zeros((900, 1400, 3), dtype=np.uint8)
    cards = [
        ((100, 120), (520, 360)),
        ((650, 140), (1070, 380)),
        ((240, 520), (660, 760)),
    ]
    for top_left, bottom_right in cards:
        cv2.rectangle(image, top_left, bottom_right, (255, 255, 255), thickness=-1)
        cv2.rectangle(image, top_left, bottom_right, (0, 0, 0), thickness=4)
    path.parent.mkdir(parents=True, exist_ok=True)
    assert cv2.imwrite(str(path), image)
    return path


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def latest_jobs_by_id(jobs_path: Path) -> dict[str, dict[str, Any]]:
    jobs: dict[str, dict[str, Any]] = {}
    for job in read_jsonl(jobs_path):
        jobs[job["job_id"]] = job
    return jobs


def normalize_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = []
    for event in events:
        payload = _normalize_value(event["payload"])
        normalized.append({"event_type": event["event_type"], "payload": payload})
    return normalized


def _normalize_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _normalize_value(item)
            for key, item in value.items()
            if key not in {"created_at", "updated_at"}
        }
    if isinstance(value, list):
        return [_normalize_value(item) for item in value]
    if isinstance(value, str) and len(value) == 32 and all(char in "0123456789abcdef" for char in value):
        return "<job-id>"
    return value


@dataclass
class SyntheticSkillAdapter:
    specs_by_stem: dict[str, dict[str, Any]] = field(default_factory=dict)
    ocr_by_stem: dict[str, str] = field(default_factory=dict)
    apply_google_calls: list[bool] = field(default_factory=list)

    def run_pipeline(self, image_path: Path, artifact_dir: Path, *, apply_google: bool) -> SkillRunResult:
        self.apply_google_calls.append(apply_google)
        artifact_dir.mkdir(parents=True, exist_ok=True)
        spec = dict(SYNTHETIC_CONTACT_SPEC)
        spec.update(self.specs_by_stem.get(image_path.stem, {}))
        spec["source_fixture"] = image_path.name

        spec_path = artifact_dir / "spec.json"
        review_path = artifact_dir / "review.md"
        crop_manifest_path = artifact_dir / "crop_manifest.json"
        ocr_path = artifact_dir / "ocr.txt"

        spec_path.write_text(json.dumps(spec, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        review_path.write_text(
            "# Synthetic Review\n\n"
            "- privacy: synthetic fixture only\n"
            "- confidence: high\n"
            "- action: dry-run validation\n",
            encoding="utf-8",
        )
        crop_manifest_path.write_text(
            json.dumps(
                {
                    "schema": "business-card-watchdog.synthetic-crops.v1",
                    "crops": [{"id": "contact-photo-1", "source": image_path.name, "synthetic": True}],
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        ocr_path.write_text(
            self.ocr_by_stem.get(
                image_path.stem,
                "Synthetic Fixture\nFixture Labs\nfixture@example.test\n+1-555-0100\n",
            ),
            encoding="utf-8",
        )

        return SkillRunResult(
            status="ok",
            artifact_dir=artifact_dir,
            spec_path=spec_path,
            review_path=review_path,
            stdout="synthetic adapter completed\n",
        )

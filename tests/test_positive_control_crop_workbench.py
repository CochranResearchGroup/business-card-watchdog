from __future__ import annotations

import json
from pathlib import Path

from business_card_watchdog.cli import main
from business_card_watchdog.config import AppConfig
from business_card_watchdog.service import BusinessCardService

from synthetic_fixtures import write_square_image, write_synthetic_image


def write_pdf(path: Path, *, pages: int) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    objects = "\n".join(f"{index} 0 obj << /Type /Page >> endobj" for index in range(1, pages + 1))
    path.write_bytes(f"%PDF-1.7\n{objects}\n%%EOF\n".encode("utf-8"))
    return path


def write_large_multi_card_image(path: Path) -> Path:
    cv2 = __import__("cv2")
    np = __import__("numpy")
    image = np.zeros((1500, 3200, 3), dtype=np.uint8)
    cards = [
        ((160, 180), (960, 640)),
        ((1160, 220), (1960, 680)),
        ((540, 860), (1340, 1320)),
    ]
    for index, (top_left, bottom_right) in enumerate(cards, start=1):
        cv2.rectangle(image, top_left, bottom_right, (255, 255, 255), thickness=-1)
        cv2.rectangle(image, top_left, bottom_right, (0, 0, 0), thickness=8)
        x, y = top_left
        cv2.putText(image, f"Fixture Card {index}", (x + 60, y + 130), cv2.FONT_HERSHEY_SIMPLEX, 1.8, (0, 0, 0), 4)
        cv2.putText(image, "fixture@example.test", (x + 60, y + 240), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 0), 3)
    path.parent.mkdir(parents=True, exist_ok=True)
    assert cv2.imwrite(str(path), image)
    return path


def seed_corpus(tmp_path: Path) -> tuple[AppConfig, list[Path]]:
    source_dir = tmp_path / "Private Crop Positives"
    single = write_synthetic_image(source_dir / "private-single-card.jpg")
    multi = write_large_multi_card_image(source_dir / "private-multi-card.jpg")
    square = write_square_image(source_dir / "private-low-edge.jpg")
    pdf = write_pdf(source_dir / "private-front-back.pdf", pages=2)
    config = AppConfig(config_path=tmp_path / "config.toml", data_dir=tmp_path / "data")
    BusinessCardService(config).known_card_intake(
        source_paths=[str(single), str(multi), str(square), str(pdf)],
        write=True,
    )
    return config, [single, multi, square, pdf]


def test_positive_control_crop_workbench_generates_candidates_and_review_requests(
    tmp_path: Path,
) -> None:
    config, private_sources = seed_corpus(tmp_path)

    payload = BusinessCardService(config).positive_control_crop_workbench(write=True)
    serialized = json.dumps(payload, sort_keys=True)
    counts = payload["counts"]

    assert payload["schema"] == "business-card-watchdog.positive-control-crop-workbench.v1"
    assert payload["state"] == "crop_workbench_review_required"
    assert payload["source_count"] == 4
    assert counts["images"] == 3
    assert counts["pdf_documents"] == 1
    assert counts["pdf_page_units"] == 2
    assert counts["pdf_pages_materialized"] == 2
    assert counts["primary_crop_candidates"] >= 1
    assert counts["child_crop_candidates"] >= 2
    assert counts["multi_card_units_with_children"] >= 1
    assert counts["crop_review_requests"] >= 1
    assert counts["app_intelligence_request_count"] == counts["crop_review_requests"]
    assert payload["ocr_attempted"] == 0
    assert payload["writes_attempted"] == 0
    assert payload["network_calls_made"] == 0
    assert payload["live_sink_calls_made"] is False
    assert payload["public_web_search_used"] is False
    assert payload["paid_enrichment_used"] is False
    assert payload["runtime_artifact_written"] is True
    assert Path(payload["report_path"]).exists()
    assert Path(payload["candidate_artifact_dir"]).is_dir()

    candidates = [
        candidate
        for source in payload["source_results"]
        for unit in source["processing_units"]
        for candidate in unit["crop_candidates"]
    ]
    assert candidates
    assert all(candidate["artifact_path"] for candidate in candidates)
    assert all(Path(candidate["artifact_path"]).exists() for candidate in candidates)
    assert all("quality" in candidate for candidate in candidates)
    assert any(candidate["candidate_kind"] == "child_card_candidate" for candidate in candidates)
    assert any(candidate["media_kind"] == "pdf_page" for candidate in candidates) or counts["crop_review_requests"] > 0
    assert all(candidate["source_path_redacted"] is True for candidate in candidates)
    assert all(candidate["source_filename_redacted"] is True for candidate in candidates)
    for source in private_sources:
        assert str(source) not in serialized
        assert source.name not in serialized


def test_positive_control_crop_workbench_preview_writes_nothing(tmp_path: Path) -> None:
    config, _ = seed_corpus(tmp_path)

    payload = BusinessCardService(config).positive_control_crop_workbench(write=False)

    assert payload["state"] == "ready_for_runtime_crop_workbench"
    assert payload["runtime_artifact_written"] is False
    assert payload["report_path"] is None
    assert payload["candidate_artifact_dir"] is None
    assert payload["ocr_attempted"] == 0
    assert payload["counts"]["pdf_page_units"] == 2
    assert not (config.data_dir / "positive_control_corpus" / "crop_workbenches").exists()


def test_positive_control_crop_workbench_cli_json_preview_redacts_private_sources(
    tmp_path: Path,
    capsys,
) -> None:
    config, private_sources = seed_corpus(tmp_path)
    config_path = tmp_path / "config.toml"
    config_path.write_text(f'data_dir = "{config.data_dir}"\n', encoding="utf-8")

    assert (
        main(
            [
                "--config",
                str(config_path),
                "positive-control-crop-workbench",
                "--no-write",
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    serialized = json.dumps(payload, sort_keys=True)

    assert payload["state"] == "ready_for_runtime_crop_workbench"
    assert payload["runtime_artifact_written"] is False
    assert payload["source_count"] == 4
    for source in private_sources:
        assert str(source) not in serialized
        assert source.name not in serialized

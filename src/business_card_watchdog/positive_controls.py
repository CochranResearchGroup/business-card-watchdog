from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

from .config import AppConfig, resolve_input_path
from .document_intake import is_supported_document
from .models import utc_now
from .skill_adapter import is_supported_image


@dataclass(frozen=True)
class PositiveControlSeed:
    path: Path
    seed_id: str
    seed_ref: str
    media_kind: str
    suffix: str
    sha256: str


def build_positive_control_manifest(
    config: AppConfig,
    *,
    write: bool = True,
    seed_paths: list[str] | None = None,
    include_globs: list[str] | None = None,
) -> dict[str, Any]:
    include_patterns = list(include_globs or [])
    seeds, errors = _select_seeds(config, seed_paths=list(seed_paths or []), include_globs=include_patterns)
    image_seeds = [seed for seed in seeds if seed.media_kind == "image"]
    pdf_seeds = [seed for seed in seeds if seed.media_kind == "pdf_document"]
    run_id = f"positive-controls-{utc_now().replace(':', '-')}-{_manifest_digest(seeds)}"
    output_root = config.cache_dir / "positive_controls" / run_id
    scenarios = _build_scenarios(image_seeds)
    state = _manifest_state(errors=errors, scenarios=scenarios)
    payload: dict[str, Any] = {
        "schema": "business-card-watchdog.positive-control-manifest.v1",
        "generated_at": utc_now(),
        "state": state,
        "run_id": run_id,
        "seed_count": len(seeds),
        "image_seed_count": len(image_seeds),
        "pdf_seed_count": len(pdf_seeds),
        "include_globs": include_patterns,
        "seeds": [_seed_summary(seed) for seed in seeds],
        "pdf_seed_refs": [seed.seed_ref for seed in pdf_seeds],
        "scenario_count": len(scenarios),
        "scenarios": [_scenario_manifest(scenario, output_root=output_root, write=write) for scenario in scenarios],
        "errors": errors,
        "private_paths_redacted": True,
        "private_filenames_redacted": True,
        "private_sources_used": bool(seeds),
        "files_processed": 0,
        "generated_file_count": 0,
        "ocr_attempted": 0,
        "pdfs_rasterized": 0,
        "crops_created": 0,
        "writes_attempted": 0,
        "network_calls_made": 0,
        "live_sink_calls_made": False,
        "public_web_search_used": False,
        "paid_enrichment_used": False,
        "runtime_artifact_written": False,
        "manifest_path": None,
        "output_root": str(output_root) if write else None,
        "commands": {
            "positive_controls": "watch-positive-controls --json",
            "positive_controls_preview": "watch-positive-controls --no-write --json",
            "practice_corpus_manifest": "watch-practice-corpus-manifest --no-write --json",
        },
        "explicit_stop_conditions": [
            "Generated controls are runtime-only and must not be committed to git.",
            "This surface does not OCR, crop, enrich, route, or write contacts.",
            "PDF seeds are recorded as source documents; this generator does not rasterize PDFs.",
            "Use generated controls only inside dry-run scanner side-pair/OCR tests.",
        ],
    }
    if write:
        _ensure_runtime_output_not_repo(output_root)
        generated = _write_scenarios(scenarios, output_root=output_root)
        manifest_dir = config.data_dir / "positive_controls"
        manifest_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = manifest_dir / f"{run_id}.json"
        payload["generated_file_count"] = generated
        payload["runtime_artifact_written"] = True
        payload["manifest_path"] = str(manifest_path)
        manifest_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def _ensure_runtime_output_not_repo(output_root: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    try:
        output_root.resolve().relative_to(repo_root)
    except ValueError:
        return
    raise ValueError(f"positive-control output root is inside the repo: {output_root}")


def _select_seeds(
    config: AppConfig,
    *,
    seed_paths: list[str],
    include_globs: list[str],
) -> tuple[list[PositiveControlSeed], list[dict[str, Any]]]:
    errors: list[dict[str, Any]] = []
    paths: list[Path] = []
    if seed_paths:
        for raw in seed_paths:
            path = Path(raw).expanduser()
            if not path.exists():
                errors.append({"seed_ref": "<explicit>", "error": "seed path not found"})
                continue
            paths.extend(_seed_files_from_path(path, recursive=True, include_globs=include_globs))
    else:
        for index, raw_input in enumerate(config.watch_inputs):
            try:
                source = resolve_input_path(raw_input, config)
            except KeyError as exc:
                errors.append({"input_ref": f"input_{index}", "error": str(exc)})
                continue
            if not source.exists():
                errors.append({"input_ref": f"input_{index}", "error": "watch input not found"})
                continue
            paths.extend(
                _seed_files_from_path(
                    source,
                    recursive=config.watch.status_recursive,
                    include_globs=include_globs,
                    limit=config.watch.status_scan_limit,
                )
            )
    unique_paths = sorted(set(paths), key=lambda path: str(path))
    seeds = [_seed(path, index=index) for index, path in enumerate(unique_paths, start=1)]
    return seeds, errors


def _seed_files_from_path(
    path: Path,
    *,
    recursive: bool,
    include_globs: list[str],
    limit: int | None = None,
) -> list[Path]:
    if path.is_file():
        return [path] if _is_seed_file(path) and _matches_include(path, include_globs) else []
    paths = path.rglob("*") if recursive else path.iterdir()
    files: list[Path] = []
    for candidate in paths:
        if not candidate.is_file() or not _is_seed_file(candidate):
            continue
        if not _matches_include(candidate, include_globs):
            continue
        if limit is not None and len(files) >= limit:
            break
        files.append(candidate)
    return files


def _seed(path: Path, *, index: int) -> PositiveControlSeed:
    suffix = path.suffix.lower()
    media_kind = "pdf_document" if is_supported_document(path) else "image"
    digest = _sha256(path)
    return PositiveControlSeed(
        path=path,
        seed_id=f"seed-{digest[:16]}",
        seed_ref=f"seed_{index:03d}",
        media_kind=media_kind,
        suffix=suffix,
        sha256=digest,
    )


def _build_scenarios(image_seeds: list[PositiveControlSeed]) -> list[dict[str, Any]]:
    if len(image_seeds) < 2:
        return []
    front = image_seeds[0]
    back = image_seeds[1]
    scenarios = [
        _scenario(
            "front_then_back",
            [
                _page(front, "front"),
                _page(back, "back"),
            ],
            expected_pair_groups=[["page_001", "page_002"]],
        ),
        _scenario(
            "back_then_front",
            [
                _page(back, "back"),
                _page(front, "front"),
            ],
            expected_pair_groups=[["page_001", "page_002"]],
        ),
        _scenario(
            "front_only_dropped_back",
            [_page(front, "front")],
            expected_pair_groups=[["page_001"]],
            expected_omitted_pages=["back"],
        ),
        _scenario(
            "rotated_front_back",
            [
                _page(front, "front", transform="rotate_90"),
                _page(back, "back", transform="rotate_180"),
            ],
            expected_pair_groups=[["page_001", "page_002"]],
        ),
    ]
    if len(image_seeds) >= 3:
        insert = image_seeds[2]
        scenarios.append(
            _scenario(
                "interleaved_non_card_page",
                [
                    _page(front, "front"),
                    _page(insert, "inserted_non_card"),
                    _page(back, "back"),
                ],
                expected_pair_groups=[["page_001", "page_003"]],
                expected_no_merge_boundaries=[["page_001", "page_002"], ["page_002", "page_003"]],
            )
        )
    if len(image_seeds) >= 4:
        front_2 = image_seeds[2]
        back_2 = image_seeds[3]
        scenarios.append(
            _scenario(
                "multi_card_no_cross_merge",
                [
                    _page(front, "front", card_ref="card_001"),
                    _page(back, "back", card_ref="card_001"),
                    _page(front_2, "front", card_ref="card_002"),
                    _page(back_2, "back", card_ref="card_002"),
                ],
                expected_pair_groups=[["page_001", "page_002"], ["page_003", "page_004"]],
                expected_no_merge_boundaries=[["page_002", "page_003"]],
            )
        )
    return scenarios


def _scenario(
    name: str,
    pages: list[dict[str, Any]],
    *,
    expected_pair_groups: list[list[str]],
    expected_omitted_pages: list[str] | None = None,
    expected_no_merge_boundaries: list[list[str]] | None = None,
) -> dict[str, Any]:
    for index, page in enumerate(pages, start=1):
        page["page_id"] = f"page_{index:03d}"
    return {
        "scenario_id": name,
        "scenario_name": name,
        "pages": pages,
        "expected_pair_groups": expected_pair_groups,
        "expected_omitted_pages": list(expected_omitted_pages or []),
        "expected_no_merge_boundaries": list(expected_no_merge_boundaries or []),
    }


def _page(seed: PositiveControlSeed, role: str, *, transform: str = "copy", card_ref: str = "card_001") -> dict[str, Any]:
    output_suffix = ".png" if transform.startswith("rotate_") else seed.suffix
    return {
        "seed_ref": seed.seed_ref,
        "seed_id": seed.seed_id,
        "card_ref": card_ref,
        "expected_role": role,
        "transform": transform,
        "output_suffix": output_suffix,
        "_source_path": seed.path,
    }


def _scenario_manifest(scenario: dict[str, Any], *, output_root: Path, write: bool) -> dict[str, Any]:
    scenario_dir = output_root / str(scenario["scenario_id"])
    pages = []
    for page in scenario["pages"]:
        output_name = f"{page['page_id']}{page.get('output_suffix') or '.png'}"
        redacted_page = {key: value for key, value in page.items() if not str(key).startswith("_")}
        pages.append(
            {
                **redacted_page,
                "generated_path": str(scenario_dir / output_name) if write else None,
                "generated_path_redacted": not write,
            }
        )
    return {
        "schema": "business-card-watchdog.positive-control-scenario.v1",
        "scenario_id": scenario["scenario_id"],
        "scenario_name": scenario["scenario_name"],
        "page_count": len(pages),
        "pages": pages,
        "expected_pair_groups": scenario["expected_pair_groups"],
        "expected_omitted_pages": scenario["expected_omitted_pages"],
        "expected_no_merge_boundaries": scenario["expected_no_merge_boundaries"],
        "runtime_only": True,
    }


def _write_scenarios(scenarios: list[dict[str, Any]], *, output_root: Path) -> int:
    by_seed = {
        page["seed_ref"]: page
        for scenario in scenarios
        for page in scenario["pages"]
    }
    seed_paths = {
        seed_ref: _find_seed_path_for_page(page)
        for seed_ref, page in by_seed.items()
    }
    count = 0
    for scenario in scenarios:
        scenario_dir = output_root / str(scenario["scenario_id"])
        scenario_dir.mkdir(parents=True, exist_ok=True)
        for page in scenario["pages"]:
            source = seed_paths[page["seed_ref"]]
            output = scenario_dir / f"{page['page_id']}{page.get('output_suffix') or '.png'}"
            _write_transformed_image(source, output, transform=str(page.get("transform") or "copy"))
            count += 1
    return count


def _find_seed_path_for_page(page: dict[str, Any]) -> Path:
    # The source path is deliberately not included in the public manifest. It is
    # kept only on the in-memory page object while writing generated controls.
    path = page.get("_source_path")
    if isinstance(path, Path):
        return path
    raise ValueError("positive-control page is missing in-memory source path")


def _write_transformed_image(source: Path, output: Path, *, transform: str) -> None:
    if transform == "copy":
        shutil.copy2(source, output)
        return
    try:
        import cv2  # type: ignore[import-not-found]
    except Exception:
        shutil.copy2(source, output)
        return
    image = cv2.imread(str(source))
    if image is None:
        shutil.copy2(source, output)
        return
    if transform == "rotate_90":
        image = cv2.rotate(image, cv2.ROTATE_90_CLOCKWISE)
    elif transform == "rotate_180":
        image = cv2.rotate(image, cv2.ROTATE_180)
    if not cv2.imwrite(str(output), image):
        raise OSError(f"failed to write generated positive control: {output}")


def _seed_summary(seed: PositiveControlSeed) -> dict[str, Any]:
    return {
        "seed_ref": seed.seed_ref,
        "seed_id": seed.seed_id,
        "media_kind": seed.media_kind,
        "suffix": seed.suffix,
        "sha256": seed.sha256,
        "private_path_redacted": True,
        "private_filename_redacted": True,
    }


def _is_seed_file(path: Path) -> bool:
    return is_supported_image(path) or is_supported_document(path)


def _matches_include(path: Path, include_globs: list[str]) -> bool:
    if not include_globs:
        return True
    return any(fnmatch(path.name, pattern) or fnmatch(str(path), pattern) for pattern in include_globs)


def _manifest_digest(seeds: list[PositiveControlSeed]) -> str:
    digest = hashlib.sha256()
    for seed in seeds:
        digest.update(seed.seed_id.encode("utf-8"))
    return digest.hexdigest()[:12] if seeds else "no-seeds"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _manifest_state(*, errors: list[dict[str, Any]], scenarios: list[dict[str, Any]]) -> str:
    if errors:
        return "blocked"
    if not scenarios:
        return "needs_at_least_two_image_seeds"
    return "ready_for_side_pair_ocr_training"

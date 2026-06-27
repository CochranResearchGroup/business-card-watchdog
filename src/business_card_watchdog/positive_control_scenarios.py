from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .config import AppConfig
from .models import utc_now
from .positive_control_labels import build_positive_control_label_inventory


POSITIVE_CONTROL_SCENARIO_MANIFEST_SCHEMA = "business-card-watchdog.positive-control-scenario-manifest.v1"
POSITIVE_CONTROL_SCENARIO_SCHEMA = "business-card-watchdog.positive-control-scenario-plan.v1"


def build_positive_control_scenario_manifest(config: AppConfig, *, write: bool = True) -> dict[str, Any]:
    inventory = build_positive_control_label_inventory(config, write=False)
    entries = [entry for entry in list(inventory.get("entries") or []) if isinstance(entry, dict)]
    scenarios = _build_scenarios(entries)
    manifest_id = f"positive-control-scenarios-{utc_now().replace(':', '-')}-{_scenario_digest(scenarios)}"
    manifest_path = (
        config.data_dir
        / "positive_control_corpus"
        / "scenario_manifests"
        / f"{manifest_id}.json"
    )
    state = _state(inventory=inventory, scenarios=scenarios)
    payload: dict[str, Any] = {
        "schema": POSITIVE_CONTROL_SCENARIO_MANIFEST_SCHEMA,
        "generated_at": utc_now(),
        "state": state,
        "manifest_id": manifest_id,
        "inventory_id": inventory.get("inventory_id"),
        "inventory_state": inventory.get("state"),
        "source_count": len(entries),
        "scenario_count": len(scenarios),
        "scenarios": scenarios,
        "stable_replay_order": [scenario["scenario_id"] for scenario in scenarios],
        "coverage": _coverage(scenarios),
        "lineage_redacted": True,
        "private_paths_redacted": True,
        "private_filenames_redacted": True,
        "generated_file_count": 0,
        "materialized_artifact_count": 0,
        "files_inspected": len(entries),
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
        "commands": {
            "positive_control_scenario_manifest": "positive-control-scenario-manifest --json",
            "positive_control_scenario_manifest_preview": "positive-control-scenario-manifest --no-write --json",
            "positive_control_label_inventory": "positive-control-label-inventory --no-write --json",
        },
        "explicit_stop_conditions": [
            "This manifest contains replayable scenario plans only; it does not render derived images or PDFs.",
            "Scenario plans are derived only from operator-declared positive controls.",
            "This surface does not OCR, crop, rasterize PDFs, enrich, route, or write contacts.",
            "Generated scenario artifacts must remain under user-scoped runtime/cache storage if a later replayer materializes them.",
            "Do not commit runtime scenario manifests or private card artifacts to git.",
        ],
    }
    if write and state != "blocked":
        _ensure_runtime_output_not_repo(manifest_path.parent)
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        written_payload = payload | {
            "runtime_artifact_written": True,
            "manifest_path": str(manifest_path),
        }
        manifest_path.write_text(json.dumps(written_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        payload["runtime_artifact_written"] = True
        payload["manifest_path"] = str(manifest_path)
    return payload


def _build_scenarios(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    scenarios: list[dict[str, Any]] = []
    for entry in entries:
        source_kind = str(entry.get("source_kind") or "")
        if source_kind == "scanner_pdf_front_back_sequence_candidate":
            scenarios.extend(_pdf_sequence_scenarios(entry))
        elif source_kind == "scanner_pdf_document":
            scenarios.extend(_pdf_single_page_scenarios(entry))
        elif source_kind in {"single_card_image_candidate", "multi_card_image_candidate"}:
            scenarios.extend(_image_scenarios(entry))
    scenarios.extend(_mixed_multi_card_scenarios(entries))
    scenarios.sort(key=lambda scenario: scenario["scenario_id"])
    return scenarios


def _pdf_sequence_scenarios(entry: dict[str, Any]) -> list[dict[str, Any]]:
    page_count = max(0, int(entry.get("page_count") or 0))
    pages = list(range(1, page_count + 1))
    first_pair = pages[:2]
    source = _lineage(entry)
    scenarios = [
        _scenario(
            entry,
            "pdf_front_back_order",
            "scanner_pdf_order_variant",
            source,
            [_page_step(page, role="front_or_back_unknown") for page in pages],
            expected_pair_groups=_pair_groups(pages, order="front_back"),
            operations=[{"operation": "preserve_page_order", "page_order": pages}],
        ),
        _scenario(
            entry,
            "pdf_back_front_order",
            "scanner_pdf_order_variant",
            source,
            [_page_step(page, role="front_or_back_unknown") for page in _swap_adjacent_pairs(pages)],
            expected_pair_groups=_pair_groups(_swap_adjacent_pairs(pages), order="back_front"),
            operations=[{"operation": "swap_adjacent_front_back_pages", "page_order": _swap_adjacent_pairs(pages)}],
        ),
        _scenario(
            entry,
            "pdf_front_only_dropped_back",
            "scanner_pdf_missing_back_variant",
            source,
            [_page_step(page, role="front_or_back_unknown") for page in pages[::2]],
            expected_pair_groups=[[f"page_{page:03d}"] for page in pages[::2]],
            omitted_source_pages=pages[1::2],
            operations=[{"operation": "omit_even_pages_as_blank_or_dropped_backs", "page_order": pages[::2]}],
        ),
    ]
    if first_pair:
        scenarios.extend(
            [
                _scenario(
                    entry,
                    "pdf_back_only",
                    "scanner_pdf_back_only_variant",
                    source,
                    [_page_step(page, role="back_candidate") for page in pages[1::2]],
                    expected_pair_groups=[[f"page_{page:03d}"] for page in pages[1::2]],
                    omitted_source_pages=pages[::2],
                    operations=[{"operation": "omit_odd_pages_as_fronts", "page_order": pages[1::2]}],
                ),
                _scenario(
                    entry,
                    "pdf_duplicated_page",
                    "scanner_pdf_duplicate_page_variant",
                    source,
                    [_page_step(page, role="front_or_back_unknown") for page in [*first_pair, first_pair[0]]],
                    expected_pair_groups=[["page_001", "page_002"]],
                    operations=[{"operation": "duplicate_first_page", "page_order": [*first_pair, first_pair[0]]}],
                ),
                _scenario(
                    entry,
                    "pdf_rotated_pages",
                    "scanner_pdf_orientation_variant",
                    source,
                    [
                        _page_step(page, role="front_or_back_unknown", rotation=rotation)
                        for page, rotation in zip(first_pair, [90, 180], strict=False)
                    ],
                    expected_pair_groups=[["page_001", "page_002"]],
                    operations=[{"operation": "rotate_pages", "rotations_degrees": {"page_001": 90, "page_002": 180}}],
                ),
            ]
        )
    return scenarios


def _pdf_single_page_scenarios(entry: dict[str, Any]) -> list[dict[str, Any]]:
    source = _lineage(entry)
    return [
        _scenario(
            entry,
            "pdf_single_page_front_only",
            "scanner_pdf_front_only_variant",
            source,
            [_page_step(1, role="front_or_back_unknown")],
            expected_pair_groups=[["page_001"]],
            operations=[{"operation": "preserve_single_pdf_page", "page_order": [1]}],
        ),
        _scenario(
            entry,
            "pdf_single_page_rotated",
            "scanner_pdf_orientation_variant",
            source,
            [_page_step(1, role="front_or_back_unknown", rotation=90)],
            expected_pair_groups=[["page_001"]],
            operations=[{"operation": "rotate_pages", "rotations_degrees": {"page_001": 90}}],
        ),
    ]


def _image_scenarios(entry: dict[str, Any]) -> list[dict[str, Any]]:
    source_kind = str(entry.get("source_kind") or "")
    scenario_kind = (
        "multi_card_image_orientation_variant"
        if source_kind == "multi_card_image_candidate"
        else "single_card_image_orientation_variant"
    )
    source = _lineage(entry)
    return [
        _scenario(
            entry,
            f"{source_kind}_identity",
            scenario_kind,
            source,
            [_image_step(entry, rotation=0)],
            operations=[{"operation": "preserve_image"}],
        ),
        _scenario(
            entry,
            f"{source_kind}_rotate_90",
            scenario_kind,
            source,
            [_image_step(entry, rotation=90)],
            operations=[{"operation": "rotate_image", "rotation_degrees": 90}],
        ),
        _scenario(
            entry,
            f"{source_kind}_rotate_180",
            scenario_kind,
            source,
            [_image_step(entry, rotation=180)],
            operations=[{"operation": "rotate_image", "rotation_degrees": 180}],
        ),
    ]


def _mixed_multi_card_scenarios(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    multi_entries = [entry for entry in entries if entry.get("source_kind") == "multi_card_image_candidate"]
    if not multi_entries:
        return []
    lineage = [_lineage(entry) for entry in multi_entries]
    first = multi_entries[0]
    return [
        _scenario(
            first,
            "mixed_multi_card_images",
            "mixed_multi_card_image_variant",
            {"source_entry_count": len(multi_entries), "sources": lineage},
            [
                {
                    "step_id": f"source_{index:03d}",
                    "source_entry_id": str(entry.get("entry_id") or ""),
                    "source_sha256_prefix": str(entry.get("sha256_prefix") or ""),
                    "media_kind": "image",
                    "page_kind": "multi_card_image_candidate",
                    "transform": {"operation": "compose_multi_card_image", "rotation_degrees": 0},
                }
                for index, entry in enumerate(multi_entries, start=1)
            ],
            operations=[
                {
                    "operation": "compose_mixed_multi_card_image_plan",
                    "source_entry_ids": [str(entry.get("entry_id") or "") for entry in multi_entries],
                }
            ],
        )
    ]


def _scenario(
    entry: dict[str, Any],
    suffix: str,
    scenario_kind: str,
    source_lineage: dict[str, Any],
    steps: list[dict[str, Any]],
    *,
    expected_pair_groups: list[list[str]] | None = None,
    omitted_source_pages: list[int] | None = None,
    operations: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    source_id = str(entry.get("entry_id") or "unknown")
    scenario_id = f"{source_id}-{suffix}"
    return {
        "schema": POSITIVE_CONTROL_SCENARIO_SCHEMA,
        "scenario_id": scenario_id,
        "scenario_kind": scenario_kind,
        "source_entry_id": source_id,
        "source_sha256_prefix": str(entry.get("sha256_prefix") or ""),
        "source_kind": str(entry.get("source_kind") or ""),
        "media_kind": str(entry.get("media_kind") or ""),
        "operator_declared_label": "known_business_card",
        "training_evidence_kind": "positive_control_synthetic_scenario",
        "lineage": source_lineage,
        "steps": steps,
        "expected_pair_groups": expected_pair_groups or [],
        "omitted_source_pages": omitted_source_pages or [],
        "operations": operations or [],
        "replay_targets": ["recognition", "crop_ocr", "side_pair"],
        "materialization": {
            "state": "plan_only_not_materialized",
            "generated_artifact_path": None,
            "must_remain_runtime_only": True,
        },
        "private_paths_redacted": True,
        "private_filenames_redacted": True,
    }


def _lineage(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_entry_id": str(entry.get("entry_id") or ""),
        "source_sha256": str(entry.get("sha256") or ""),
        "source_sha256_prefix": str(entry.get("sha256_prefix") or ""),
        "source_kind": str(entry.get("source_kind") or ""),
        "media_kind": str(entry.get("media_kind") or ""),
        "page_count": int(entry.get("page_count") or 0),
        "source_path_redacted": True,
        "source_filename_redacted": True,
    }


def _page_step(page_number: int, *, role: str, rotation: int = 0) -> dict[str, Any]:
    return {
        "step_id": f"page_{page_number:03d}",
        "source_page_number": page_number,
        "media_kind": "pdf_page",
        "page_kind": "business_card_side_candidate",
        "side_expectation": role,
        "transform": {"operation": "pdf_page_transform", "rotation_degrees": rotation},
    }


def _image_step(entry: dict[str, Any], *, rotation: int) -> dict[str, Any]:
    image_metadata = dict(entry.get("image_metadata") or {})
    return {
        "step_id": "image_001",
        "source_entry_id": str(entry.get("entry_id") or ""),
        "source_sha256_prefix": str(entry.get("sha256_prefix") or ""),
        "media_kind": "image",
        "page_kind": str(entry.get("source_kind") or ""),
        "card_count_label": str(entry.get("card_count_label") or ""),
        "image_metadata": image_metadata,
        "transform": {"operation": "image_transform", "rotation_degrees": rotation},
    }


def _swap_adjacent_pairs(pages: list[int]) -> list[int]:
    swapped: list[int] = []
    for index in range(0, len(pages), 2):
        pair = pages[index : index + 2]
        swapped.extend(reversed(pair) if len(pair) == 2 else pair)
    return swapped


def _pair_groups(pages: list[int], *, order: str) -> list[list[str]]:
    groups: list[list[str]] = []
    for index in range(0, len(pages), 2):
        pair = pages[index : index + 2]
        if pair:
            groups.append([f"page_{page:03d}" for page in pair])
    return groups if order in {"front_back", "back_front"} else []


def _coverage(scenarios: list[dict[str, Any]]) -> dict[str, Any]:
    kinds = {str(scenario.get("scenario_kind") or "") for scenario in scenarios}
    operation_names = {
        str(operation.get("operation") or "")
        for scenario in scenarios
        for operation in list(scenario.get("operations") or [])
        if isinstance(operation, dict)
    }
    return {
        "scenario_kinds": sorted(kinds),
        "operation_names": sorted(operation_names),
        "covers_page_order_swaps": "swap_adjacent_front_back_pages" in operation_names,
        "covers_rotations": bool({"rotate_pages", "rotate_image"} & operation_names),
        "covers_omitted_pages": "omit_even_pages_as_blank_or_dropped_backs" in operation_names,
        "covers_duplicated_pages": "duplicate_first_page" in operation_names,
        "covers_front_only_scans": bool(
            {"scanner_pdf_front_only_variant", "scanner_pdf_missing_back_variant"} & kinds
        ),
        "covers_back_only_scans": "scanner_pdf_back_only_variant" in kinds,
        "covers_front_back_pdfs": "scanner_pdf_order_variant" in kinds,
        "covers_mixed_multi_card_images": "mixed_multi_card_image_variant" in kinds,
    }


def _scenario_digest(scenarios: list[dict[str, Any]]) -> str:
    digest = hashlib.sha256()
    for scenario in scenarios:
        digest.update(str(scenario.get("scenario_id") or "").encode("utf-8"))
    return digest.hexdigest()[:12] if scenarios else "no-scenarios"


def _state(*, inventory: dict[str, Any], scenarios: list[dict[str, Any]]) -> str:
    if inventory.get("state") == "blocked" or not scenarios:
        return "blocked"
    if inventory.get("state") == "ready_with_index_errors":
        return "ready_with_inventory_warnings"
    return "ready_for_scenario_replay"


def _ensure_runtime_output_not_repo(output_root: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    try:
        output_root.resolve().relative_to(repo_root)
    except ValueError:
        return
    raise ValueError(f"positive control scenario manifest output root is inside the repo: {output_root}")

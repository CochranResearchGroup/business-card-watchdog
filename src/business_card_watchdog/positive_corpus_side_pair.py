from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .card_sides import build_pair_proposals, build_side_pair_graph, classify_card_side, merge_side_pair_contacts
from .config import AppConfig
from .models import utc_now
from .positive_corpus_workbench import build_positive_corpus_workbench_evaluation


SIDE_PAIR_EVALUATION_SCHEMA = "business-card-watchdog.positive-corpus-side-pair-evaluation.v1"


def build_positive_corpus_side_pair_evaluation(
    config: AppConfig,
    *,
    write: bool = True,
    workbench_report_path: Path | None = None,
) -> dict[str, Any]:
    corpus_root = config.data_dir / "positive_control_corpus"
    errors: list[dict[str, Any]] = []
    workbench = _load_or_create_workbench_report(
        config,
        write=write,
        workbench_report_path=workbench_report_path,
        errors=errors,
    )
    evaluation_id = f"positive-corpus-side-pair-{utc_now().replace(':', '-')}-{_workbench_digest(workbench)}"
    evaluation_dir = corpus_root / "side_pair_evaluations" / evaluation_id
    report_path = evaluation_dir / "side_pair_evaluation.json"
    run_dir = Path(str(workbench.get("run_dir") or "")) if workbench.get("run_dir") else None
    state = "blocked" if errors or run_dir is None or not run_dir.exists() else "preview"
    payload: dict[str, Any] = {
        "schema": SIDE_PAIR_EVALUATION_SCHEMA,
        "generated_at": utc_now(),
        "state": state,
        "evaluation_id": evaluation_id,
        "workbench_id": workbench.get("workbench_id"),
        "workbench_run_id": workbench.get("run_id"),
        "workbench_report_path": str(workbench_report_path) if workbench_report_path else workbench.get("report_path"),
        "report_path": None,
        "source_count": int(workbench.get("source_count") or 0),
        "scanner_pdf_count": int(dict(workbench.get("counts") or {}).get("pdf_documents") or 0),
        "page_candidate_count": 0,
        "side_candidates": [],
        "pair_graph_summary": _empty_graph_summary(),
        "pair_proposal_summary": _empty_proposal_summary(),
        "merge_evaluations": [],
        "app_intelligence_review_requests": [],
        "counts": _empty_counts(errors=errors),
        "errors": errors,
        "private_paths_redacted": True,
        "private_filenames_redacted": True,
        "operator_declared_known_positive_only": True,
        "broad_autodetection_promoted": False,
        "dry_run": True,
        "ocr_attempted": 0,
        "pdfs_rasterized": 0,
        "crops_created": 0,
        "writes_attempted": 0,
        "network_calls_made": 0,
        "live_sink_calls_made": False,
        "public_web_search_used": False,
        "paid_enrichment_used": False,
        "runtime_artifact_written": False,
        "commands": {
            "positive_corpus_side_pair_evaluation": "positive-corpus-side-pair-evaluation --json",
            "positive_corpus_side_pair_evaluation_preview": "positive-corpus-side-pair-evaluation --no-write --json",
        },
        "explicit_stop_conditions": [
            "This evaluates front/back matching for operator-declared positive controls only.",
            "Pair proposals and merge evaluations are evidence, not route or sink decisions.",
            "Ambiguous or conflicting pairs require bounded App Intelligence review evidence before any deterministic rule change.",
            "Do not route, enrich, write contacts, read back sinks, search the public web, or call paid providers.",
            "Do not commit runtime side-pair artifacts, private source media, OCR text, crops, or contact data.",
        ],
    }
    if state == "blocked":
        return payload

    assert run_dir is not None
    evidence = _collect_side_pair_evidence(run_dir)
    graph = build_side_pair_graph(
        run_id=str(workbench.get("run_id") or run_dir.name),
        side_candidates=evidence["side_candidates"],
        evidence_by_job=evidence["evidence_by_job"],
    )
    proposals = build_pair_proposals(
        run_id=str(workbench.get("run_id") or run_dir.name),
        side_candidates=evidence["side_candidates"],
    )
    merge_evaluations = _merge_evaluations(
        proposals=list(proposals.get("proposals") or []),
        side_candidates=evidence["side_candidates"],
        contact_candidates=evidence["contact_candidates"],
    )
    review_requests = _review_requests(graph=graph, proposals=proposals, merge_evaluations=merge_evaluations)
    counts = _counts(
        side_candidates=evidence["side_candidates"],
        graph=graph,
        proposals=proposals,
        merge_evaluations=merge_evaluations,
        review_requests=review_requests,
        errors=errors,
    )
    written_payload = payload | {
        "state": "front_back_review_required"
        if review_requests
        else "front_back_pairs_proposed"
        if counts["deterministic_pair_proposals"]
        else "needs_more_side_pair_evidence",
        "report_path": str(report_path) if write else None,
        "page_candidate_count": len(evidence["side_candidates"]),
        "side_candidates": [_redacted_side_candidate(row) for row in evidence["side_candidates"]],
        "pair_graph_summary": _graph_summary(graph),
        "pair_proposal_summary": _proposal_summary(proposals),
        "merge_evaluations": merge_evaluations,
        "app_intelligence_review_requests": review_requests,
        "counts": counts,
        "ocr_attempted": len(evidence["side_candidates"]),
        "pdfs_rasterized": len(evidence["side_candidates"]),
        "runtime_artifact_written": bool(write),
    }
    if write:
        _ensure_runtime_output_not_repo(corpus_root)
        evaluation_dir.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(written_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return written_payload


def _load_or_create_workbench_report(
    config: AppConfig,
    *,
    write: bool,
    workbench_report_path: Path | None,
    errors: list[dict[str, Any]],
) -> dict[str, Any]:
    if workbench_report_path is not None:
        report = _read_json(workbench_report_path)
        if not report:
            errors.append({"error": "workbench report not found or invalid"})
        return report
    latest = _latest_workbench_report(config.data_dir / "positive_control_corpus" / "workbench_evaluations")
    if latest is not None:
        return _read_json(latest)
    if not write:
        errors.append({"error": "no workbench report found; run positive-corpus-workbench-evaluation first"})
        return {}
    return build_positive_corpus_workbench_evaluation(config, write=True, workers=1)


def _latest_workbench_report(root: Path) -> Path | None:
    if not root.exists():
        return None
    reports = sorted(root.glob("*/workbench_evaluation.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    return reports[0] if reports else None


def _collect_side_pair_evidence(run_dir: Path) -> dict[str, Any]:
    jobs = _latest_jobs(run_dir / "jobs.jsonl")
    side_candidates: list[dict[str, Any]] = []
    evidence_by_job: dict[str, dict[str, Any]] = {}
    contact_candidates: dict[str, dict[str, Any]] = {}
    for job_id, job in sorted(jobs.items()):
        artifact_dir = Path(str(job.get("artifact_dir") or run_dir / "artifacts" / job_id))
        source_page = _read_json(artifact_dir / "source_page.json")
        if not source_page:
            continue
        redacted_source_page = _redacted_source_page(source_page)
        ocr_text = _read_text(artifact_dir / "ocr.txt")
        side_candidate = classify_card_side(
            job_id=job_id,
            source_page=redacted_source_page,
            ocr_text=ocr_text,
        )
        side_candidate["ocr_text_source"] = _ocr_text_source(run_dir / "artifacts.jsonl", job_id=job_id)
        side_candidates.append(side_candidate)
        evidence_by_job[job_id] = {
            "qr_evidence": _read_json(artifact_dir / "qr_evidence.json"),
            "orientation_evidence": _read_json(artifact_dir / "orientation_evidence.json"),
            "crop_quality": _read_json(artifact_dir / "crop_quality.json"),
            "recrop_proposals": _read_json(artifact_dir / "recrop_proposals.json"),
        }
        contact_candidate = _read_json(artifact_dir / "contact_candidate.json")
        if contact_candidate:
            contact_candidates[job_id] = contact_candidate
    return {
        "side_candidates": side_candidates,
        "evidence_by_job": evidence_by_job,
        "contact_candidates": contact_candidates,
    }


def _redacted_source_page(source_page: dict[str, Any]) -> dict[str, Any]:
    document_digest = hashlib.sha256(str(source_page.get("source_document_path") or "").encode("utf-8")).hexdigest()
    page_number = int(source_page.get("page_number") or 0)
    return {
        "schema": source_page.get("schema") or "business-card-watchdog.document-page.v1",
        "source_document_path": f"document-{document_digest[:12]}.pdf",
        "page_number": page_number,
        "page_image_path": f"document-{document_digest[:12]}-page-{page_number:04d}.png",
        "media_kind": source_page.get("media_kind") or "page_image",
        "rasterization_mode": source_page.get("rasterization_mode") or "unknown",
        "sha256": source_page.get("sha256") or "",
    }


def _redacted_side_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    features = dict(candidate.get("features") or {})
    return {
        "job_id": candidate.get("job_id"),
        "document_key": str(candidate.get("source_document_path") or "").removesuffix(".pdf"),
        "page_number": candidate.get("page_number"),
        "side_label": candidate.get("side_label"),
        "confidence": candidate.get("confidence"),
        "classification_reason": candidate.get("classification_reason"),
        "ocr_text_source": candidate.get("ocr_text_source") or "",
        "feature_counts": {
            "email_count": int(features.get("email_count") or 0),
            "phone_count": int(features.get("phone_count") or 0),
            "url_count": int(features.get("url_count") or 0),
            "name_hint_count": int(features.get("name_hint_count") or 0),
            "back_word_count": int(features.get("back_word_count") or 0),
            "domain_count": len(features.get("domains") or []),
        },
        "source_path_redacted": True,
        "source_filename_redacted": True,
    }


def _merge_evaluations(
    *,
    proposals: list[dict[str, Any]],
    side_candidates: list[dict[str, Any]],
    contact_candidates: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    side_by_job = {str(row.get("job_id") or ""): row for row in side_candidates}
    evaluations: list[dict[str, Any]] = []
    for proposal in proposals:
        if proposal.get("state") != "proposed":
            continue
        front_job_id = str(proposal.get("front_job_id") or "")
        back_job_id = str(proposal.get("back_job_id") or "")
        front_candidate = contact_candidates.get(front_job_id)
        back_candidate = contact_candidates.get(back_job_id)
        if front_candidate is None or back_candidate is None:
            evaluations.append(
                {
                    "proposal_id": proposal.get("proposal_id"),
                    "state": "missing_contact_candidate",
                    "front_job_id": front_job_id,
                    "back_job_id": back_job_id,
                    "requires_review": True,
                    "routing_allowed": False,
                    "enrichment_allowed": False,
                    "sink_write_allowed": False,
                }
            )
            continue
        merged = merge_side_pair_contacts(
            front_candidate=front_candidate,
            back_candidate=back_candidate,
            proposal=proposal,
            reviewer="positive-corpus-side-pair-evaluation",
            reviewed_at=utc_now(),
        )
        quality = dict(merged.get("ocr_merge_quality") or {})
        evaluations.append(
            {
                "proposal_id": proposal.get("proposal_id"),
                "state": "merge_review_required",
                "front_job_id": front_job_id,
                "back_job_id": back_job_id,
                "front_page_number": proposal.get("front_page_number"),
                "back_page_number": proposal.get("back_page_number"),
                "front_side_label": dict(side_by_job.get(front_job_id) or {}).get("side_label"),
                "back_side_label": dict(side_by_job.get(back_job_id) or {}).get("side_label"),
                "merge_quality_status": quality.get("status"),
                "backside_augmented_fields": list(quality.get("backside_augmented_fields") or []),
                "conflict_count": int(quality.get("conflict_count") or 0),
                "missing_required_fields": list(quality.get("missing_required_fields") or []),
                "requires_review": True,
                "routing_allowed": False,
                "enrichment_allowed": False,
                "sink_write_allowed": False,
            }
        )
    return evaluations


def _review_requests(
    *,
    graph: dict[str, Any],
    proposals: dict[str, Any],
    merge_evaluations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    requests: list[dict[str, Any]] = []
    for edge in list(graph.get("edges") or []):
        if not isinstance(edge, dict):
            continue
        state = str(edge.get("state") or "")
        if state not in {"pair_review_required", "blocked_for_review"}:
            continue
        requests.append(
            {
                "request_id": f"{edge.get('edge_id')}-side-pair-review",
                "request_type": "pair_card_sides",
                "status": "planned",
                "reason": edge.get("reason"),
                "edge_state": state,
                "page_numbers": list(edge.get("page_numbers") or []),
                "side_labels": list(edge.get("side_labels") or []),
                "deterministic_evidence": {
                    "score": edge.get("score"),
                    "evidence_kinds": [item.get("kind") for item in list(edge.get("evidence") or [])],
                    "negative_evidence_kinds": [
                        item.get("kind") for item in list(edge.get("negative_evidence") or [])
                    ],
                },
                "allowed_response_schema": {
                    "type": "object",
                    "required": ["recommendation", "confidence", "rationale", "evidence"],
                    "properties": {
                        "recommendation": {
                            "type": "string",
                            "enum": [
                                "same_card_pair",
                                "not_same_card",
                                "blank_back",
                                "needs_more_deterministic_evidence",
                            ],
                        },
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                        "rationale": {"type": "string"},
                        "evidence": {"type": "object"},
                        "training_hint": {"type": "string"},
                    },
                    "forbidden_actions": [
                        "route_contact",
                        "write_sink",
                        "readback_sink",
                        "run_enrichment",
                        "select_live_target",
                    ],
                },
                "stop_rules": [
                    "Return side-pair evidence only; do not route, enrich, write, or read back.",
                    "Accepted App Intelligence evidence must become deterministic side-pair fixture coverage before downstream apply.",
                ],
                "writes_attempted": 0,
                "network_calls_made": 0,
            }
        )
    for proposal in list(proposals.get("proposals") or []):
        if not isinstance(proposal, dict) or proposal.get("state") != "blocked_for_review":
            continue
        requests.append(
            {
                "request_id": f"{proposal.get('proposal_id')}-proposal-review",
                "request_type": "pair_card_sides",
                "status": "planned",
                "reason": proposal.get("blocked_reason") or "blocked side-pair proposal requires review",
                "edge_state": "blocked_for_review",
                "page_numbers": [proposal.get("front_page_number"), proposal.get("back_page_number")],
                "side_labels": ["front", "back"],
                "deterministic_evidence": {
                    "score": proposal.get("score"),
                    "negative_evidence_kinds": [
                        item.get("kind") for item in list(proposal.get("negative_evidence") or [])
                    ],
                },
                "stop_rules": [
                    "Return side-pair evidence only; do not route, enrich, write, or read back.",
                    "Resolve conflicts with deterministic fixture coverage before downstream apply.",
                ],
                "writes_attempted": 0,
                "network_calls_made": 0,
            }
        )
    for merge in merge_evaluations:
        if not merge.get("conflict_count") and not merge.get("missing_required_fields"):
            continue
        requests.append(
            {
                "request_id": f"{merge.get('proposal_id')}-ocr-merge-review",
                "request_type": "resolve_ocr_merge_conflict",
                "status": "planned",
                "reason": "front/back OCR merge has missing required fields or conflicting contact fields",
                "proposal_id": merge.get("proposal_id"),
                "front_job_id": merge.get("front_job_id"),
                "back_job_id": merge.get("back_job_id"),
                "deterministic_evidence": {
                    "merge_quality_status": merge.get("merge_quality_status"),
                    "conflict_count": merge.get("conflict_count"),
                    "missing_required_fields": merge.get("missing_required_fields"),
                    "backside_augmented_fields": merge.get("backside_augmented_fields"),
                },
                "stop_rules": [
                    "Return OCR merge evidence only; do not route, enrich, write, or read back.",
                    "Accepted merge evidence must become deterministic side-pair OCR fixture coverage before downstream apply.",
                ],
                "writes_attempted": 0,
                "network_calls_made": 0,
            }
        )
    return _dedupe_requests(requests)


def _dedupe_requests(requests: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for request in requests:
        request_id = str(request.get("request_id") or "")
        if request_id in seen:
            continue
        seen.add(request_id)
        deduped.append(request)
    return deduped


def _graph_summary(graph: dict[str, Any]) -> dict[str, Any]:
    edges = [edge for edge in list(graph.get("edges") or []) if isinstance(edge, dict)]
    states: dict[str, int] = {}
    for edge in edges:
        state = str(edge.get("state") or "unknown")
        states[state] = states.get(state, 0) + 1
    return {
        "schema": graph.get("schema"),
        "node_count": int(graph.get("node_count") or 0),
        "edge_count": int(graph.get("edge_count") or 0),
        "pair_proposal_count": int(graph.get("pair_proposal_count") or 0),
        "edge_states": dict(sorted(states.items())),
        "deterministic_pair_edges": [
            _redacted_edge(edge) for edge in edges if edge.get("state") == "pair_proposed"
        ],
        "review_required_edges": [
            _redacted_edge(edge)
            for edge in edges
            if edge.get("state") in {"pair_review_required", "blocked_for_review"}
        ],
        "blank_back_candidates": [
            _redacted_edge(edge) for edge in edges if edge.get("state") == "blank_back_candidate"
        ],
    }


def _proposal_summary(proposals: dict[str, Any]) -> dict[str, Any]:
    rows = [row for row in list(proposals.get("proposals") or []) if isinstance(row, dict)]
    states: dict[str, int] = {}
    for row in rows:
        state = str(row.get("state") or "unknown")
        states[state] = states.get(state, 0) + 1
    return {
        "schema": proposals.get("schema"),
        "proposal_count": int(proposals.get("proposal_count") or 0),
        "states": dict(sorted(states.items())),
        "proposed": [_redacted_proposal(row) for row in rows if row.get("state") == "proposed"],
        "blocked_for_review": [
            _redacted_proposal(row) for row in rows if row.get("state") == "blocked_for_review"
        ],
        "skipped_count": len(list(proposals.get("skipped") or [])),
    }


def _redacted_edge(edge: dict[str, Any]) -> dict[str, Any]:
    return {
        "edge_id": edge.get("edge_id"),
        "state": edge.get("state"),
        "reason": edge.get("reason"),
        "left_job_id": edge.get("left_job_id"),
        "right_job_id": edge.get("right_job_id"),
        "page_numbers": list(edge.get("page_numbers") or []),
        "side_labels": list(edge.get("side_labels") or []),
        "page_distance": edge.get("page_distance"),
        "score": edge.get("score"),
        "evidence_kinds": [item.get("kind") for item in list(edge.get("evidence") or [])],
        "negative_evidence_kinds": [item.get("kind") for item in list(edge.get("negative_evidence") or [])],
        "requires_app_intelligence_review": edge.get("requires_app_intelligence_review"),
        "routing_allowed": False,
    }


def _redacted_proposal(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "proposal_id": row.get("proposal_id"),
        "state": row.get("state"),
        "front_job_id": row.get("front_job_id"),
        "back_job_id": row.get("back_job_id"),
        "front_page_number": row.get("front_page_number"),
        "back_page_number": row.get("back_page_number"),
        "required_context_evidence": row.get("required_context_evidence"),
        "score": row.get("score"),
        "evidence_kinds": [item.get("kind") for item in list(row.get("evidence") or [])],
        "negative_evidence_kinds": [item.get("kind") for item in list(row.get("negative_evidence") or [])],
        "blocked_reason": row.get("blocked_reason"),
    }


def _counts(
    *,
    side_candidates: list[dict[str, Any]],
    graph: dict[str, Any],
    proposals: dict[str, Any],
    merge_evaluations: list[dict[str, Any]],
    review_requests: list[dict[str, Any]],
    errors: list[dict[str, Any]],
) -> dict[str, int]:
    graph_summary = _graph_summary(graph)
    proposal_summary = _proposal_summary(proposals)
    edge_states = dict(graph_summary.get("edge_states") or {})
    proposal_states = dict(proposal_summary.get("states") or {})
    return {
        "scanner_page_candidates": len(side_candidates),
        "front_candidates": sum(1 for row in side_candidates if row.get("side_label") == "front"),
        "back_candidates": sum(1 for row in side_candidates if row.get("side_label") == "back"),
        "blank_candidates": sum(1 for row in side_candidates if row.get("side_label") == "blank"),
        "unknown_candidates": sum(1 for row in side_candidates if row.get("side_label") == "unknown"),
        "graph_edges": int(graph_summary.get("edge_count") or 0),
        "deterministic_pair_edges": int(edge_states.get("pair_proposed") or 0),
        "review_required_edges": int(edge_states.get("pair_review_required") or 0)
        + int(edge_states.get("blocked_for_review") or 0),
        "blank_back_candidates": int(edge_states.get("blank_back_candidate") or 0),
        "deterministic_pair_proposals": int(proposal_states.get("proposed") or 0),
        "blocked_pair_proposals": int(proposal_states.get("blocked_for_review") or 0),
        "merge_evaluations": len(merge_evaluations),
        "backside_augmented_merges": sum(
            1 for row in merge_evaluations if row.get("backside_augmented_fields")
        ),
        "conflicting_merge_evaluations": sum(
            1 for row in merge_evaluations if int(row.get("conflict_count") or 0) > 0
        ),
        "app_intelligence_review_requests": len(review_requests),
        "errors": len(errors),
    }


def _empty_counts(*, errors: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "scanner_page_candidates": 0,
        "front_candidates": 0,
        "back_candidates": 0,
        "blank_candidates": 0,
        "unknown_candidates": 0,
        "graph_edges": 0,
        "deterministic_pair_edges": 0,
        "review_required_edges": 0,
        "blank_back_candidates": 0,
        "deterministic_pair_proposals": 0,
        "blocked_pair_proposals": 0,
        "merge_evaluations": 0,
        "backside_augmented_merges": 0,
        "conflicting_merge_evaluations": 0,
        "app_intelligence_review_requests": 0,
        "errors": len(errors),
    }


def _empty_graph_summary() -> dict[str, Any]:
    return {
        "node_count": 0,
        "edge_count": 0,
        "pair_proposal_count": 0,
        "edge_states": {},
        "deterministic_pair_edges": [],
        "review_required_edges": [],
        "blank_back_candidates": [],
    }


def _empty_proposal_summary() -> dict[str, Any]:
    return {
        "proposal_count": 0,
        "states": {},
        "proposed": [],
        "blocked_for_review": [],
        "skipped_count": 0,
    }


def _latest_jobs(path: Path) -> dict[str, dict[str, Any]]:
    jobs: dict[str, dict[str, Any]] = {}
    if not path.exists():
        return jobs
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if isinstance(row, dict):
            jobs[str(row["job_id"])] = row
    return jobs


def _ocr_text_source(artifacts_path: Path, *, job_id: str) -> str:
    if not artifacts_path.exists():
        return ""
    for line in artifacts_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if not isinstance(row, dict):
            continue
        if row.get("job_id") != job_id or row.get("kind") != "ocr_text":
            continue
        metadata = dict(row.get("metadata") or {})
        return str(metadata.get("source") or "adapter")
    return ""


def _workbench_digest(workbench: dict[str, Any]) -> str:
    digest = hashlib.sha256()
    for key in ("workbench_id", "run_id", "report_path"):
        digest.update(str(workbench.get(key) or "").encode("utf-8"))
    return digest.hexdigest()[:12] if workbench else "no-workbench"


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _ensure_runtime_output_not_repo(output_root: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    try:
        output_root.resolve().relative_to(repo_root)
    except ValueError:
        return
    raise ValueError(f"positive corpus side-pair output root is inside the repo: {output_root}")

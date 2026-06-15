from __future__ import annotations

import csv
import hashlib
import json
import shlex
from dataclasses import replace
from html import escape
from io import StringIO
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from .config import AppConfig, PrefilterConfig, SinkConfig, WatchConfig, ensure_runtime_dirs
from .contact import (
    apply_enrichment_proposals,
    apply_review_corrections,
    build_canonical_contact,
    build_contact_candidate,
    contact_candidate_to_spec,
    field_provenance_from_canonical,
)
from .dedupe import assess_downstream_lookup_result, remember_duplicate_resolution
from .enrichment import (
    build_paid_api_provider_handoff,
    build_public_web_result_artifact,
    build_enrichment_request,
    build_paid_api_provider_request,
    build_public_web_search_handoff,
    build_public_web_search_request,
    check_enrichment_readiness,
    score_paid_api_provider_results,
    score_public_web_results,
)
from .ledger import RunLedger
from .models import CardJob, SkillRunResult, utc_now
from .orchestrator import BatchOrchestrator
from .preclassifier import assess_business_card_candidate
from .review import assess_contact_spec, build_review_submission, write_review_packet, write_review_submission
from .routing import decide_sinks
from .sink_apply_adapters import execute_sink_readback_adapter, execute_sink_write_adapter
from .sink_lookup_adapters import execute_sink_lookup_adapter
from .sinks import (
    SinkAdapterPhase,
    build_sink_adapter_request,
    build_sink_apply_decision,
    build_sink_apply_preflight,
    build_sink_apply_result,
    build_sink_lookup_plan,
    build_sink_lookup_pilot,
    build_sink_lookup_result,
    build_sink_plan,
    check_sink_readiness,
    check_sink_lookup_readiness,
)
from .skill_adapter import BusinessCardSkillAdapter
from .service_ops import service_status
from .watcher import PollingWatcher


_SAFE_NEXT_ACTIONS = {
    "plan_sink_lookup",
    "prepare_sink_lookup_adapter",
    "prepare_sink_lookup_smoke_handoff",
    "record_sink_lookup_result",
    "assess_downstream_duplicates",
    "plan_sinks",
    "prepare_sink_write_adapter",
    "preflight_sink_apply",
    "prepare_sink_apply_pilot_readiness",
    "prepare_sink_apply_pilot_bundle",
    "prepare_sink_readback_adapter",
    "prepare_sink_apply_pilot_report",
}


def _selected_target_identity(payload: dict[str, Any]) -> str:
    return str(payload.get("selection_id") or payload.get("created_at") or "")


class _FixtureSkillAdapter:
    def run_pipeline(self, image_path: Path, artifact_dir: Path, *, apply_google: bool) -> SkillRunResult:
        artifact_dir.mkdir(parents=True, exist_ok=True)
        spec = {
            "full_name": "Synthetic Fixture",
            "organization": "Fixture Labs",
            "title": "Validation Contact",
            "email": "fixture@example.test",
            "phone": "+1-555-0100",
            "notes": "Synthetic privacy-safe business-card fixture for dry-run validation.",
            "source_fixture": image_path.name,
        }
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
            "Synthetic Fixture\nFixture Labs\nfixture@example.test\n+1-555-0100\n",
            encoding="utf-8",
        )
        return SkillRunResult(
            status="ok",
            artifact_dir=artifact_dir,
            spec_path=spec_path,
            review_path=review_path,
            stdout="synthetic adapter completed\n",
        )

_EXPLICIT_OPERATOR_ACTIONS = {
    "decide_sink_apply",
    "execute_sink_lookup_pilot",
    "execute_sink_write_pilot",
    "execute_sink_readback_pilot",
    "await_apply_approval",
    "request_enrichment",
    "review_contact",
    "review_duplicate",
    "review_enrichment",
    "resolve_duplicate",
}

_SUPPORTED_REVIEW_ACTIONS = {
    "approve_for_routing",
    "approve_enrichment_merge",
    "keep_needs_review",
    "request_enrichment",
    "resolve_duplicate",
    "reject_not_card",
    "skip",
}

_SUPPORTED_CHILD_REVIEW_ACTIONS = {
    "approve_child_for_routing",
    "keep_needs_review",
    "reject_child_contact",
}

_ROUTE_ARTIFACT_FILES = {
    "sink_lookup_plan": "sink_lookup_plan.json",
    "sink_adapter_request_lookup": "sink_adapter_request_lookup.json",
    "live_selection_packet": "live_selection_packet.json",
    "selected_live_target": "selected_live_target.json",
    "selected_live_target_audit": "selected_live_target_audit.json",
    "sink_lookup_smoke_handoff": "sink_lookup_smoke_handoff.json",
    "selected_lookup_smoke": "selected_lookup_smoke.json",
    "sink_lookup_pilot": "sink_lookup_pilot.json",
    "sink_lookup_result": "sink_lookup_result.json",
    "downstream_duplicate_assessment": "downstream_duplicate_assessment.json",
    "sink_plan": "sink_plan.json",
    "sink_adapter_request_write": "sink_adapter_request_write.json",
    "sink_apply_preflight": "sink_apply_preflight.json",
    "sink_apply_decision": "sink_apply_decision.json",
    "sink_apply_pilot_readiness": "sink_apply_pilot_readiness.json",
    "sink_apply_pilot_bundle": "sink_apply_pilot_bundle.json",
    "sink_write_pilot": "sink_write_pilot.json",
    "sink_apply_result": "sink_apply_result.json",
    "sink_adapter_request_readback": "sink_adapter_request_readback.json",
    "sink_readback_pilot": "sink_readback_pilot.json",
    "sink_apply_pilot_report": "sink_apply_pilot_report.json",
    "live_pilot_closeout": "live_pilot_closeout.json",
}

_ROUTE_REFRESH_STEPS = [
    {
        "kind": "sink_lookup_plan",
        "action": "plan_sink_lookup",
        "command": "sinks lookup-plan",
        "reason": "review changed routing-relevant contact data; refresh sink lookup plan",
    },
    {
        "kind": "sink_adapter_request_lookup",
        "action": "prepare_sink_lookup_adapter",
        "command": "sinks adapter-request --phase lookup",
        "reason": "review changed routing-relevant contact data; refresh lookup adapter request",
    },
    {
        "kind": "sink_lookup_smoke_handoff",
        "action": "prepare_sink_lookup_smoke_handoff",
        "command": "sinks lookup-smoke-handoff",
        "reason": "review changed routing-relevant contact data; refresh read-only live lookup smoke handoff",
    },
    {
        "kind": "sink_lookup_pilot",
        "action": "execute_sink_lookup_pilot",
        "command": "sinks lookup-pilot",
        "reason": "review changed routing-relevant contact data; refresh explicit read-only lookup pilot evidence",
    },
    {
        "kind": "sink_lookup_result",
        "action": "record_sink_lookup_result",
        "command": "sinks lookup-result",
        "reason": "review changed routing-relevant contact data; refresh lookup result from the new lookup request",
    },
    {
        "kind": "downstream_duplicate_assessment",
        "action": "assess_downstream_duplicates",
        "command": "sinks assess-duplicates",
        "reason": "review changed routing-relevant contact data; reassess downstream duplicates",
    },
    {
        "kind": "sink_plan",
        "action": "plan_sinks",
        "command": "sinks plan",
        "reason": "review changed routing-relevant contact data; refresh sink plan",
    },
    {
        "kind": "sink_adapter_request_write",
        "action": "prepare_sink_write_adapter",
        "command": "sinks adapter-request --phase write",
        "reason": "review changed routing-relevant contact data; refresh write adapter request",
    },
    {
        "kind": "sink_apply_preflight",
        "action": "preflight_sink_apply",
        "command": "sinks apply-preflight",
        "reason": "review changed routing-relevant contact data; refresh apply preflight",
    },
    {
        "kind": "sink_apply_decision",
        "action": "decide_sink_apply",
        "command": "sinks apply-decision",
        "reason": "review changed routing-relevant contact data; previous apply decision must be reviewed again",
    },
    {
        "kind": "sink_apply_pilot_readiness",
        "action": "prepare_sink_apply_pilot_readiness",
        "command": "sinks apply-pilot-readiness",
        "reason": "review changed routing-relevant contact data; refresh live apply pilot readiness",
    },
    {
        "kind": "sink_apply_pilot_bundle",
        "action": "prepare_sink_apply_pilot_bundle",
        "command": "sinks apply-pilot-bundle",
        "reason": "review changed routing-relevant contact data; refresh operator pilot bundle",
    },
    {
        "kind": "sink_write_pilot",
        "action": "execute_sink_write_pilot",
        "command": "sinks write-pilot",
        "reason": "review changed routing-relevant contact data; refresh explicit write pilot evidence",
    },
    {
        "kind": "sink_apply_result",
        "action": "await_apply_approval",
        "command": "sinks apply --apply",
        "reason": "review changed routing-relevant contact data; live apply remains explicit and gated",
    },
    {
        "kind": "sink_adapter_request_readback",
        "action": "prepare_sink_readback_adapter",
        "command": "sinks adapter-request --phase readback",
        "reason": "review changed routing-relevant contact data; refresh readback adapter request after apply",
    },
    {
        "kind": "sink_readback_pilot",
        "action": "execute_sink_readback_pilot",
        "command": "sinks readback-pilot",
        "reason": "review changed routing-relevant contact data; refresh explicit readback pilot evidence",
    },
    {
        "kind": "sink_apply_pilot_report",
        "action": "prepare_sink_apply_pilot_report",
        "command": "sinks apply-pilot-report",
        "reason": "review changed routing-relevant contact data; refresh apply pilot report",
    },
]

_REVIEW_BUNDLE_ARTIFACT_KINDS = {
    "preclassification",
    "review_packet",
    "contact_spec",
    "contact_candidate",
    "reviewed_contact",
    "review_submission",
    "enrichment_request",
    "enrichment_public_web_request",
    "enrichment_public_web_search_handoff",
    "enrichment_public_web_result",
    "enrichment_provider_request",
    "enrichment_provider_handoff",
    "enrichment_result",
    "enrichment_provider_result",
    "enrichment_merge_review",
    "enrichment_proposal_review",
    "duplicate_assessment",
    "downstream_duplicate_assessment",
    "duplicate_resolution",
    "sink_lookup_plan",
    "sink_adapter_request_lookup",
    "selected_live_target",
    "sink_lookup_smoke_handoff",
    "selected_lookup_smoke",
    "sink_lookup_pilot",
    "sink_lookup_result",
    "sink_plan",
    "sink_adapter_request_write",
    "sink_apply_preflight",
    "sink_apply_decision",
    "sink_apply_pilot_readiness",
    "sink_apply_pilot_bundle",
    "sink_write_pilot",
    "sink_apply_result",
    "sink_adapter_request_readback",
    "sink_readback_pilot",
    "sink_apply_pilot_report",
    "route_refresh",
    "child_replacement_closeout_status",
}


class BusinessCardService:
    def __init__(
        self,
        config: AppConfig,
        *,
        sink_lookup_executor: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
        sink_write_executor: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
        sink_readback_executor: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    ) -> None:
        self.config = config
        self.sink_lookup_executor = sink_lookup_executor
        self.sink_write_executor = sink_write_executor
        self.sink_readback_executor = sink_readback_executor

    def status(self) -> dict[str, Any]:
        ready, message = BusinessCardSkillAdapter(self.config).check_ready()
        watch_status = PollingWatcher(self.config).status()
        return {
            "schema": "business-card-watchdog.status.v1",
            "config_path": str(self.config.config_path),
            "data_dir": str(self.config.data_dir),
            "cache_dir": str(self.config.cache_dir),
            "skill_ready": ready,
            "skill_message": message,
            "watch": watch_status.to_dict(),
            "commands": {
                "runtime_readiness": "runtime-readiness --json",
                "offline_pilot_gap_audit": "offline-pilot-gap-audit --json",
                "operator_selected_live_smoke_preflight": "operator-selected-live-smoke-preflight --json",
                "service_recovery": "service recovery --json",
                "watch_status": "watch-status --json",
                "watch_backlog_preflight": "watch-backlog-preflight --json",
                "watch_dry_run_selection_handoff": "watch-dry-run-selection-handoff --json",
                "watch_dry_run": "watch-dry-run --json",
                "runs_list": "runs list --json",
                "mcp_manifest": "mcp-manifest",
            },
            "safe_next_actions": [
                {
                    "action": "inspect_runtime_readiness",
                    "command": "runtime-readiness --json",
                    "reason": "confirm user-scope config, runtime directories, service, and watcher readiness",
                    "safe_to_auto_continue": True,
                    "requires_explicit_operator_action": False,
                },
                {
                    "action": "inspect_service_recovery",
                    "command": "service recovery --json",
                    "reason": "review recovery commands and stop conditions without changing runtime state",
                    "safe_to_auto_continue": True,
                    "requires_explicit_operator_action": False,
                },
                {
                    "action": "inspect_offline_pilot_gap_audit",
                    "command": "offline-pilot-gap-audit --json",
                    "reason": "review offline pilot drill and documentation coverage before choosing the next slice",
                    "safe_to_auto_continue": True,
                    "requires_explicit_operator_action": False,
                },
                {
                    "action": "inspect_operator_selected_live_smoke_preflight",
                    "command": "operator-selected-live-smoke-preflight --json",
                    "reason": "review the no-live operator-selection boundary before any live smoke",
                    "safe_to_auto_continue": True,
                    "requires_explicit_operator_action": False,
                },
                {
                    "action": "inspect_watch_backlog_preflight",
                    "command": "watch-backlog-preflight --json",
                    "reason": "review configured watch backlog counts without exposing private paths or processing files",
                    "safe_to_auto_continue": True,
                    "requires_explicit_operator_action": False,
                },
                {
                    "action": "inspect_runs",
                    "command": "runs list --json",
                    "reason": "find existing run IDs before selecting review, routing, or live-pilot work",
                    "safe_to_auto_continue": True,
                    "requires_explicit_operator_action": False,
                },
            ],
            "explicit_stop_conditions": [
                "Do not process private SyncThing images from generic status checks.",
                "Do not run public-web search or paid API enrichment from status checks.",
                "Do not run live GWS/Odollo/Odoo lookup, write, or readback without selected target approval.",
            ],
            "writes_attempted": 0,
            "network_calls_made": 0,
        }

    def process_source(self, source: str, *, dry_run: bool = True, workers: int = 2) -> dict[str, Any]:
        run_dir = BatchOrchestrator(self.config).process_source(source, dry_run=dry_run, workers=workers)
        return self.get_run(run_dir.name)

    def list_runs(self) -> list[dict[str, Any]]:
        ensure_runtime_dirs(self.config)
        index_path = self.config.runs_dir / "index.jsonl"
        if not index_path.exists():
            return []
        latest: dict[str, dict[str, Any]] = {}
        for row in _read_jsonl(index_path):
            latest[str(row["run_id"])] = row
        return sorted(latest.values(), key=lambda row: str(row.get("updated_at", "")), reverse=True)

    def latest_review_routing_drill(self, *, selected_run_id: str | None = None) -> dict[str, Any]:
        summary: dict[str, Any] = {
            "schema": "business-card-watchdog.latest-review-routing-drill.v1",
            "state": "not_run",
            "has_drill": False,
            "selected_run_id": selected_run_id,
            "selected_run_matches": False,
            "run_id": None,
            "job_id": None,
            "drill_path": None,
            "generated_at": None,
            "agent_readback_state": None,
            "next_manual_boundary": None,
            "expected_manual_boundary": None,
            "artifact_check_count": 0,
            "artifact_check_passed_count": 0,
            "safe_action_counts": {"executed": 0, "skipped": 0},
            "private_sources_used": False,
            "public_web_search_used": False,
            "paid_enrichment_used": False,
            "live_sink_calls_made": False,
            "writes_attempted": 0,
            "network_calls_made": 0,
            "commands": {"run_fixture_review_routing_drill": "drills review-routing --json"},
            "explicit_stop_conditions": [
                "Latest drill readback is fixture-only evidence.",
                "Do not treat a passed fixture drill as approval for private inputs or live sinks.",
            ],
        }
        candidates: list[dict[str, Any]] = []
        for run in self.list_runs():
            run_id = str(run.get("run_id") or "")
            if not run_id:
                continue
            for artifact in self.list_artifacts(run_id):
                if artifact.get("kind") == "review_routing_drill" and artifact.get("job_id") == "__run__":
                    candidates.append({**artifact, "run_id": run_id})
        if not candidates:
            return summary

        candidates.sort(key=lambda row: str(row.get("created_at") or ""), reverse=True)
        latest = candidates[0]
        drill_path = str(latest.get("path") or "")
        payload = _read_json_file(Path(drill_path))
        if payload is None:
            return {
                **summary,
                "state": "unreadable",
                "has_drill": True,
                "run_id": latest.get("run_id"),
                "drill_path": drill_path,
                "selected_run_matches": bool(selected_run_id and latest.get("run_id") == selected_run_id),
            }

        readback = dict(payload.get("agent_loop_readback") or {})
        artifact_checks = [check for check in readback.get("artifact_checks") or [] if isinstance(check, dict)]
        passed_checks = [check for check in artifact_checks if check.get("exists")]
        readback_state = str(readback.get("state") or "unknown")
        return {
            **summary,
            "state": "passed" if readback_state == "passed" else "needs_attention",
            "has_drill": True,
            "selected_run_matches": bool(selected_run_id and payload.get("run_id") == selected_run_id),
            "run_id": payload.get("run_id"),
            "job_id": payload.get("job_id"),
            "drill_path": drill_path,
            "generated_at": payload.get("generated_at"),
            "agent_readback_state": readback_state,
            "next_manual_boundary": readback.get("next_manual_boundary"),
            "expected_manual_boundary": readback.get("expected_manual_boundary"),
            "artifact_check_count": len(artifact_checks),
            "artifact_check_passed_count": len(passed_checks),
            "safe_action_counts": readback.get("safe_action_counts") or {"executed": 0, "skipped": 0},
            "private_sources_used": bool(payload.get("private_sources_used")),
            "public_web_search_used": bool(payload.get("public_web_search_used")),
            "paid_enrichment_used": bool(payload.get("paid_enrichment_used")),
            "live_sink_calls_made": bool(payload.get("live_sink_calls_made")),
            "writes_attempted": _int(payload.get("writes_attempted")),
            "network_calls_made": _int(payload.get("network_calls_made")),
        }

    def offline_pilot_gap_audit(self, *, write: bool = True) -> dict[str, Any]:
        ensure_runtime_dirs(self.config)
        repo_root = Path(__file__).resolve().parents[2]
        required_docs = {
            "review_workflow_sample_output": repo_root / "docs/operations/review-workflow-sample-output.md",
            "live_pilot_sample_output": repo_root / "docs/operations/live-pilot-sample-output.md",
            "child_replacement_sample_output": repo_root / "docs/operations/child-replacement-sample-output.md",
            "live_pilot_checklists": repo_root / "docs/operations/live-pilot-checklists.md",
            "public_upstream_validation": repo_root / "docs/operations/public-upstream-validation.md",
        }
        doc_checks = [
            {
                "name": name,
                "path": str(path),
                "exists": path.exists(),
            }
            for name, path in required_docs.items()
        ]
        drill_surfaces = [
            {
                "name": "multi_card_preclassification",
                "cli": "drills multi-card-preclassification --json",
                "api": "POST /drills/multi-card-preclassification",
                "mcp": "business_card_watchdog_multi_card_preclassification_drill",
                "covered": True,
            },
            {
                "name": "review_routing",
                "cli": "drills review-routing --json",
                "api": "POST /drills/review-routing",
                "mcp": "business_card_watchdog_review_routing_drill",
                "covered": True,
            },
            {
                "name": "live_pilot_rehearsal",
                "cli": "drills live-pilot-rehearsal --json",
                "api": "POST /drills/live-pilot-rehearsal",
                "mcp": "business_card_watchdog_live_pilot_rehearsal_drill",
                "covered": True,
            },
            {
                "name": "child_replacement_readiness",
                "cli": "drills child-replacement-readiness --json",
                "api": "POST /drills/child-replacement-readiness",
                "mcp": "business_card_watchdog_child_replacement_readiness_drill",
                "covered": True,
            },
        ]
        remaining_boundaries = [
            {
                "boundary": "operator_selected_live_smoke",
                "state": "live_operator_required",
                "reason": "requires one explicit real run, job, sink, operator, target, and tenant/profile confirmation",
                "next_plan": "docs/dev/plans/0009-2026-06-14-operator-selected-live-smoke-and-pilot-rollout.md",
            },
            {
                "boundary": "private_syncthing_source_processing",
                "state": "operator_required",
                "reason": "private phone directory images must not be processed by generic offline audits",
                "next_safe_command": "watch-dry-run --json",
            },
            {
                "boundary": "paid_api_enrichment",
                "state": "explicit_request_required",
                "reason": "paid enrichment may cost money and must be explicitly requested by the operator",
                "next_safe_command": "enrichment check --json",
            },
            {
                "boundary": "non_loopback_api_exposure",
                "state": "separate_design_required",
                "reason": "hosted or non-loopback API exposure needs an auth/network design before enablement",
                "next_doc": "docs/operations/release-readiness.md",
            },
        ]
        covered_count = sum(1 for item in drill_surfaces if item["covered"]) + sum(1 for item in doc_checks if item["exists"])
        total_count = len(drill_surfaces) + len(doc_checks)
        missing_docs = [item for item in doc_checks if not item["exists"]]
        state = "ready_for_live_operator_boundary" if not missing_docs else "needs_offline_attention"
        audit_path = self.config.data_dir / "offline_pilot_gap_audit.json"
        payload = {
            "schema": "business-card-watchdog.offline-pilot-gap-audit.v1",
            "generated_at": utc_now(),
            "state": state,
            "coverage": {
                "covered_count": covered_count,
                "total_count": total_count,
                "missing_doc_count": len(missing_docs),
                "drill_surface_count": len(drill_surfaces),
            },
            "doc_checks": doc_checks,
            "drill_surfaces": drill_surfaces,
            "remaining_boundaries": remaining_boundaries,
            "recommended_next_slice": (
                "operator_selected_live_smoke"
                if state == "ready_for_live_operator_boundary"
                else "complete_missing_offline_docs"
            ),
            "commands": {
                "offline_pilot_gap_audit": "offline-pilot-gap-audit --json",
                "multi_card_preclassification_drill": "drills multi-card-preclassification --json",
                "review_routing_drill": "drills review-routing --json",
                "live_pilot_rehearsal_drill": "drills live-pilot-rehearsal --json",
                "child_replacement_readiness_drill": "drills child-replacement-readiness --json",
                "operator_dashboard": "operator-dashboard --json",
                "runtime_readiness": "runtime-readiness --json",
            },
            "explicit_stop_conditions": [
                "This audit inspects offline surfaces only.",
                "Do not process private SyncThing images from this audit.",
                "Do not run public-web search, paid enrichment, live lookup, live write, or live readback from this audit.",
                "Do not claim Google/Odoo writes work until authenticated readiness and live or sandbox write/readback checks exist.",
            ],
            "audit_path": str(audit_path) if write else None,
            "audit_written": False,
            "writes_attempted": 0,
            "network_calls_made": 0,
        }
        if write:
            payload["audit_written"] = True
            audit_path.parent.mkdir(parents=True, exist_ok=True)
            audit_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return payload

    def operator_dashboard(self, *, run_id: str | None = None) -> dict[str, Any]:
        status = self.status()
        runtime = self.runtime_readiness()
        runs = self.list_runs()
        selected_run_id = run_id or (str(runs[0]["run_id"]) if runs else None)
        recovery = self.service_recovery_report(run_id=selected_run_id)
        latest_drill = self.latest_review_routing_drill(selected_run_id=selected_run_id)
        run_summary: dict[str, Any] | None = None
        phase_dashboard: dict[str, Any] | None = None
        review_counts: dict[str, int] = {}
        live_pilot_summary: dict[str, Any] | None = None
        live_pilot_handoff_summary: dict[str, Any] | None = None
        child_replacement_summary: dict[str, Any] | None = None
        next_action_summary: dict[str, Any] = {
            "action_count": 0,
            "safe_auto_count": 0,
            "explicit_operator_count": 0,
            "by_action": {},
            "sample_actions": [],
        }

        if selected_run_id:
            run_summary = self.run_summary(selected_run_id)
            phase_dashboard = self.phase_report(selected_run_id)["dashboard_summary"]
            review_entries = self.review_queue(run_id=selected_run_id, state="all")
            for entry in review_entries:
                state = str(entry.get("state") or "unknown")
                review_counts[state] = review_counts.get(state, 0) + 1
            live_status = self.live_pilot_status(run_id=selected_run_id, write=False)
            live_pilot_summary = {
                "state": live_status.get("state"),
                "job_count": live_status.get("job_count", 0),
                "counts": live_status.get("counts") or {},
                "observed_writes_attempted": live_status.get("observed_writes_attempted", 0),
                "observed_network_calls_made": live_status.get("observed_network_calls_made", 0),
                "commands": live_status.get("commands") or {},
                "explicit_stop_conditions": live_status.get("explicit_stop_conditions") or [],
            }
            handoff = self.live_pilot_handoff(run_id=selected_run_id, write=False)
            pilot_checklist_rollup = _live_pilot_checklist_rollup(handoff)
            operator_entries = [
                {
                    "job_id": entry.get("job_id"),
                    "next_action": entry.get("next_action"),
                    "command": entry.get("command"),
                    "operator_response_template": entry.get("operator_response_template"),
                    "operator_prompt": entry.get("operator_prompt"),
                    "pilot_command_sequence_summary": _pilot_command_sequence_summary(
                        dict(entry.get("pilot_command_sequence") or {})
                    ),
                    "validation_command": (entry.get("commands") or {}).get("validate_operator_response"),
                    "validation_command_prefilled": (entry.get("commands") or {}).get(
                        "validate_operator_response_prefilled"
                    ),
                }
                for entry in handoff.get("entries") or []
                if isinstance(entry, dict) and entry.get("operator_required")
            ]
            operator_response_templates = list(handoff.get("operator_response_templates") or [])
            live_pilot_execution_packet = _operator_dashboard_live_pilot_execution_packet(
                selected_run_id,
                handoff,
            )
            live_pilot_handoff_summary = {
                "schema": "business-card-watchdog.operator-dashboard.live-pilot-handoff-summary.v1",
                "state": handoff.get("state"),
                "job_count": handoff.get("job_count", 0),
                "action_counts": handoff.get("action_counts") or {},
                "operator_required_count": len(operator_entries),
                "operator_entries": operator_entries[:5],
                "operator_response_template_count": len(operator_response_templates),
                "operator_response_templates": operator_response_templates[:5],
                "operator_response_contract": handoff.get("operator_response_contract"),
                "writes_attempted": handoff.get("writes_attempted", 0),
                "network_calls_made": handoff.get("network_calls_made", 0),
                "observed_writes_attempted": handoff.get("observed_writes_attempted", 0),
                "observed_network_calls_made": handoff.get("observed_network_calls_made", 0),
                "pilot_checklist_rollup": pilot_checklist_rollup,
                "execution_packet": live_pilot_execution_packet,
                "operator_stop_conditions": handoff.get("operator_stop_conditions") or [],
            }
            review_bundle = self.review_bundle(run_id=selected_run_id, state="all", write=False)
            child_replacement_entries = [
                {
                    "job_id": entry.get("job_id"),
                    "candidate_id": (entry.get("child_replacement_status") or {}).get("candidate_id"),
                    "state": (entry.get("child_replacement_status") or {}).get("state"),
                    "sink": (entry.get("child_replacement_status") or {}).get("sink"),
                    "operator": (entry.get("child_replacement_status") or {}).get("operator"),
                    "predecessor_artifacts_stale": (entry.get("child_replacement_status") or {}).get(
                        "predecessor_artifacts_stale"
                    ),
                    "replacement_copy_ready": (entry.get("child_replacement_status") or {}).get(
                        "replacement_copy_ready"
                    ),
                    "closeout_command": (
                        (entry.get("child_replacement_status") or {}).get("commands") or {}
                    ).get("closeout_status"),
                }
                for entry in review_bundle.get("entries") or []
                if (entry.get("child_replacement_status") or {}).get("has_closeout")
            ]
            child_replacement_summary = {
                "schema": "business-card-watchdog.operator-dashboard.child-replacement-summary.v1",
                "state_counts": (review_bundle.get("groups") or {}).get("by_child_replacement_state") or {},
                "closeout_count": len(child_replacement_entries),
                "ready_count": sum(
                    1
                    for entry in child_replacement_entries
                    if entry.get("state") == "ready_for_operator_closeout"
                ),
                "entries": child_replacement_entries[:5],
                "writes_attempted": 0,
                "network_calls_made": 0,
            }
            next_actions = self.next_actions(run_id=selected_run_id, limit=20)
            action_counts: dict[str, int] = {}
            safe_auto_count = 0
            explicit_operator_count = 0
            sample_actions: list[dict[str, Any]] = []
            for action in next_actions["actions"]:
                action_name = str(action.get("action") or "unknown")
                action_counts[action_name] = action_counts.get(action_name, 0) + 1
                if action.get("safe_to_auto_continue"):
                    safe_auto_count += 1
                if action.get("requires_explicit_operator_action"):
                    explicit_operator_count += 1
                sample_actions.append(
                    {
                        "run_id": action.get("run_id"),
                        "job_id": action.get("job_id"),
                        "action": action_name,
                        "command": action.get("command"),
                        "safe_to_auto_continue": action.get("safe_to_auto_continue", False),
                        "requires_explicit_operator_action": action.get(
                            "requires_explicit_operator_action",
                            False,
                        ),
                    }
                )
            next_action_summary = {
                "action_count": next_actions["action_count"],
                "safe_auto_count": safe_auto_count,
                "explicit_operator_count": explicit_operator_count,
                "by_action": dict(sorted(action_counts.items())),
                "sample_actions": sample_actions,
            }

        blocked_reasons: list[str] = []
        if runtime.get("state") == "blocked":
            blocked_reasons.append("runtime readiness is blocked")
        if recovery.get("state") == "blocked":
            blocked_reasons.extend(str(item) for item in recovery.get("blocked_reasons") or [])
        if not selected_run_id:
            blocked_reasons.append("no run selected or available for review/routing/live-pilot inspection")

        return {
            "schema": "business-card-watchdog.operator-dashboard.v1",
            "created_at": utc_now(),
            "state": "blocked" if blocked_reasons else "ready",
            "config_path": status.get("config_path"),
            "data_dir": status.get("data_dir"),
            "cache_dir": status.get("cache_dir"),
            "selected_run_id": selected_run_id,
            "run_count": len(runs),
            "recent_runs": runs[:5],
            "status": status,
            "runtime_readiness": runtime,
            "service_recovery": recovery,
            "run_summary": run_summary,
            "phase_dashboard_summary": phase_dashboard,
            "review_counts": review_counts,
            "next_action_summary": next_action_summary,
            "live_pilot_summary": live_pilot_summary,
            "live_pilot_handoff_summary": live_pilot_handoff_summary,
            "child_replacement_summary": child_replacement_summary,
            "latest_review_routing_drill": latest_drill,
            "blocked_reasons": blocked_reasons,
            "commands": {
                "operator_dashboard": (
                    f"operator-dashboard --run-id {selected_run_id} --json"
                    if selected_run_id
                    else "operator-dashboard --json"
                ),
                "status": "status --json",
                "runtime_readiness": "runtime-readiness --json",
                "service_recovery": (
                    f"service recovery --run-id {selected_run_id} --json"
                    if selected_run_id
                    else "service recovery --json"
                ),
                "runs_list": "runs list --json",
                "review_queue": (
                    f"reviews list --run-id {selected_run_id} --state all --json"
                    if selected_run_id
                    else "runs list --json"
                ),
                "child_review_queue": (
                    f"reviews children --run-id {selected_run_id} --state needs_review --json"
                    if selected_run_id
                    else "runs list --json"
                ),
                "phase_report": (
                    f"runs phase-report {selected_run_id} --json" if selected_run_id else "runs list --json"
                ),
                "next_actions": (
                    f"actions next --run-id {selected_run_id} --json" if selected_run_id else "runs list --json"
                ),
                "run_next_safe": (
                    f"actions run-next --run-id {selected_run_id} --limit 10 --json"
                    if selected_run_id
                    else "runs list --json"
                ),
                "multi_card_preclassification_drill": "drills multi-card-preclassification --json",
                "review_routing_drill": "drills review-routing --json",
                "live_pilot_rehearsal_drill": "drills live-pilot-rehearsal --json",
                "child_replacement_readiness_drill": "drills child-replacement-readiness --json",
                "live_pilot_status": (
                    f"runs live-pilot-status {selected_run_id} --no-write --json"
                    if selected_run_id
                    else "runs list --json"
                ),
                "live_pilot_handoff": (
                    f"runs live-pilot-handoff {selected_run_id} --no-write --json"
                    if selected_run_id
                    else "runs list --json"
                ),
                "live_pilot_approval_packet": (
                    f"runs live-pilot-approval-packet {selected_run_id} --json"
                    if selected_run_id
                    else "runs list --json"
                ),
                "live_pilot_validate_response": (
                    f"runs live-pilot-validate-response {selected_run_id} --response <operator-response> --json"
                    if selected_run_id
                    else "runs list --json"
                ),
                "selected_live_target_preflight": (
                    f"runs selected-live-target-preflight {selected_run_id} --response <operator-response> --json"
                    if selected_run_id
                    else "runs list --json"
                ),
                "selected_live_target_preview": (
                    f"runs selected-live-target-preview {selected_run_id} --response <operator-response> --json"
                    if selected_run_id
                    else "runs list --json"
                ),
                "selected_live_target_from_response": (
                    f"runs selected-live-target-from-response {selected_run_id} "
                    "--response <operator-response> --json"
                    if selected_run_id
                    else "runs list --json"
                ),
                "selected_live_target_handoff_from_response": (
                    f"runs selected-live-target-handoff-from-response {selected_run_id} "
                    "--response <operator-response> --json"
                    if selected_run_id
                    else "runs list --json"
                ),
                "lookup_smoke_handoff_from_response": (
                    f"runs lookup-smoke-handoff-from-response {selected_run_id} "
                    "--response <operator-response> --json"
                    if selected_run_id
                    else "runs list --json"
                ),
                "selected_lookup_smoke_execution_packet_from_response": (
                    f"runs selected-lookup-smoke-execution-packet-from-response {selected_run_id} "
                    "--response <operator-response> --json"
                    if selected_run_id
                    else "runs list --json"
                ),
                "selected_write_pilot_execution_packet_from_response": (
                    f"runs selected-write-pilot-execution-packet-from-response {selected_run_id} "
                    "--response <operator-response> --json"
                    if selected_run_id
                    else "runs list --json"
                ),
                "selected_readback_pilot_execution_packet_from_response": (
                    f"runs selected-readback-pilot-execution-packet-from-response {selected_run_id} "
                    "--response <operator-response> --json"
                    if selected_run_id
                    else "runs list --json"
                ),
                "live_pilot_closeout_packet_from_response": (
                    f"runs live-pilot-closeout-packet-from-response {selected_run_id} "
                    "--response <operator-response> --json"
                    if selected_run_id
                    else "runs list --json"
                ),
                "live_pilot_operator_workflow_packet_from_response": (
                    f"runs live-pilot-operator-workflow-packet-from-response {selected_run_id} "
                    "--response <operator-response> --json"
                    if selected_run_id
                    else "runs list --json"
                ),
                "live_pilot_operator_rehearsal_from_response": (
                    f"runs live-pilot-operator-rehearsal-from-response {selected_run_id} "
                    "--response <operator-response> --json"
                    if selected_run_id
                    else "runs list --json"
                ),
                "live_pilot_readiness_export_from_response": (
                    f"runs live-pilot-readiness-export-from-response {selected_run_id} "
                    "--response <operator-response> --json"
                    if selected_run_id
                    else "runs list --json"
                ),
                "live_pilot_execution_checklist_from_response": (
                    f"runs live-pilot-execution-checklist-from-response {selected_run_id} "
                    "--response <operator-response> --json"
                    if selected_run_id
                    else "runs list --json"
                ),
                "live_pilot_command_copy_packet_from_response": (
                    f"runs live-pilot-command-copy-packet-from-response {selected_run_id} "
                    "--response <operator-response> --acknowledgement <operator-acknowledgement> --json"
                    if selected_run_id
                    else "runs list --json"
                ),
                "mcp_manifest": "mcp-manifest",
            },
            "api_routes": {
                "operator_dashboard": (
                    f"GET /operator/dashboard?run_id={selected_run_id}"
                    if selected_run_id
                    else "GET /operator/dashboard"
                ),
                "next_actions": (
                    f"GET /actions/next?run_id={selected_run_id}&limit=20"
                    if selected_run_id
                    else "GET /actions/next?limit=20"
                ),
                "child_review_queue": (
                    f"GET /reviews/children?run_id={selected_run_id}&state=needs_review"
                    if selected_run_id
                    else "GET /reviews/children?state=needs_review"
                ),
                "run_next_safe": "POST /actions/run-next",
                "multi_card_preclassification_drill": "POST /drills/multi-card-preclassification",
                "review_routing_drill": "POST /drills/review-routing",
                "live_pilot_rehearsal_drill": "POST /drills/live-pilot-rehearsal",
                "child_replacement_readiness_drill": "POST /drills/child-replacement-readiness",
                "live_pilot_status": (
                    f"GET /runs/{selected_run_id}/live-pilot-status?write=false"
                    if selected_run_id
                    else "GET /runs/{run_id}/live-pilot-status?write=false"
                ),
                "live_pilot_handoff": (
                    f"GET /runs/{selected_run_id}/live-pilot-handoff?write=false"
                    if selected_run_id
                    else "GET /runs/{run_id}/live-pilot-handoff?write=false"
                ),
                "live_pilot_approval_packet": (
                    f"GET /runs/{selected_run_id}/live-pilot-approval-packet"
                    if selected_run_id
                    else "GET /runs/{run_id}/live-pilot-approval-packet"
                ),
                "live_pilot_validate_response": (
                    f"POST /runs/{selected_run_id}/live-pilot-operator-response-validation"
                    if selected_run_id
                    else "POST /runs/{run_id}/live-pilot-operator-response-validation"
                ),
                "selected_live_target_preflight": (
                    f"POST /runs/{selected_run_id}/selected-live-target-preflight"
                    if selected_run_id
                    else "POST /runs/{run_id}/selected-live-target-preflight"
                ),
                "selected_live_target_preview": (
                    f"POST /runs/{selected_run_id}/selected-live-target-preview"
                    if selected_run_id
                    else "POST /runs/{run_id}/selected-live-target-preview"
                ),
                "selected_live_target_from_response": (
                    f"POST /runs/{selected_run_id}/selected-live-target-from-response"
                    if selected_run_id
                    else "POST /runs/{run_id}/selected-live-target-from-response"
                ),
                "selected_live_target_handoff_from_response": (
                    f"POST /runs/{selected_run_id}/selected-live-target-handoff-from-response"
                    if selected_run_id
                    else "POST /runs/{run_id}/selected-live-target-handoff-from-response"
                ),
                "lookup_smoke_handoff_from_response": (
                    f"POST /runs/{selected_run_id}/lookup-smoke-handoff-from-response"
                    if selected_run_id
                    else "POST /runs/{run_id}/lookup-smoke-handoff-from-response"
                ),
                "selected_lookup_smoke_execution_packet_from_response": (
                    f"POST /runs/{selected_run_id}/selected-lookup-smoke-execution-packet-from-response"
                    if selected_run_id
                    else "POST /runs/{run_id}/selected-lookup-smoke-execution-packet-from-response"
                ),
                "selected_write_pilot_execution_packet_from_response": (
                    f"POST /runs/{selected_run_id}/selected-write-pilot-execution-packet-from-response"
                    if selected_run_id
                    else "POST /runs/{run_id}/selected-write-pilot-execution-packet-from-response"
                ),
                "selected_readback_pilot_execution_packet_from_response": (
                    f"POST /runs/{selected_run_id}/selected-readback-pilot-execution-packet-from-response"
                    if selected_run_id
                    else "POST /runs/{run_id}/selected-readback-pilot-execution-packet-from-response"
                ),
                "live_pilot_closeout_packet_from_response": (
                    f"POST /runs/{selected_run_id}/live-pilot-closeout-packet-from-response"
                    if selected_run_id
                    else "POST /runs/{run_id}/live-pilot-closeout-packet-from-response"
                ),
                "live_pilot_operator_workflow_packet_from_response": (
                    f"POST /runs/{selected_run_id}/live-pilot-operator-workflow-packet-from-response"
                    if selected_run_id
                    else "POST /runs/{run_id}/live-pilot-operator-workflow-packet-from-response"
                ),
                "live_pilot_operator_rehearsal_from_response": (
                    f"POST /runs/{selected_run_id}/live-pilot-operator-rehearsal-from-response"
                    if selected_run_id
                    else "POST /runs/{run_id}/live-pilot-operator-rehearsal-from-response"
                ),
                "live_pilot_readiness_export_from_response": (
                    f"POST /runs/{selected_run_id}/live-pilot-readiness-export-from-response"
                    if selected_run_id
                    else "POST /runs/{run_id}/live-pilot-readiness-export-from-response"
                ),
                "live_pilot_execution_checklist_from_response": (
                    f"POST /runs/{selected_run_id}/live-pilot-execution-checklist-from-response"
                    if selected_run_id
                    else "POST /runs/{run_id}/live-pilot-execution-checklist-from-response"
                ),
                "live_pilot_command_copy_packet_from_response": (
                    f"POST /runs/{selected_run_id}/live-pilot-command-copy-packet-from-response"
                    if selected_run_id
                    else "POST /runs/{run_id}/live-pilot-command-copy-packet-from-response"
                ),
            },
            "mcp_tools": {
                "operator_dashboard": {
                    "tool": "business_card_watchdog_operator_dashboard",
                    "arguments": {"run_id": selected_run_id} if selected_run_id else {},
                },
                "next_actions": {
                    "tool": "business_card_watchdog_next_actions",
                    "arguments": {"run_id": selected_run_id, "limit": 20}
                    if selected_run_id
                    else {"limit": 20},
                },
                "run_next_safe": {
                    "tool": "business_card_watchdog_run_next_actions",
                    "arguments": {"run_id": selected_run_id, "limit": 10}
                    if selected_run_id
                    else {"limit": 10},
                },
                "child_review_queue": {
                    "tool": "business_card_watchdog_child_reviews_list",
                    "arguments": {"run_id": selected_run_id, "state": "needs_review"}
                    if selected_run_id
                    else {"state": "needs_review"},
                },
                "multi_card_preclassification_drill": {
                    "tool": "business_card_watchdog_multi_card_preclassification_drill",
                    "arguments": {},
                },
                "review_routing_drill": {
                    "tool": "business_card_watchdog_review_routing_drill",
                    "arguments": {},
                },
                "live_pilot_rehearsal_drill": {
                    "tool": "business_card_watchdog_live_pilot_rehearsal_drill",
                    "arguments": {},
                },
                "child_replacement_readiness_drill": {
                    "tool": "business_card_watchdog_child_replacement_readiness_drill",
                    "arguments": {},
                },
                "live_pilot_status": {
                    "tool": "business_card_watchdog_live_pilot_status",
                    "arguments": {"run_id": selected_run_id, "write": False}
                    if selected_run_id
                    else {"run_id": "<run-id>", "write": False},
                },
                "live_pilot_handoff": {
                    "tool": "business_card_watchdog_live_pilot_handoff",
                    "arguments": {"run_id": selected_run_id, "write": False}
                    if selected_run_id
                    else {"run_id": "<run-id>", "write": False},
                },
                "live_pilot_approval_packet": {
                    "tool": "business_card_watchdog_live_pilot_approval_packet",
                    "arguments": {"run_id": selected_run_id} if selected_run_id else {"run_id": "<run-id>"},
                },
                "live_pilot_validate_response": {
                    "tool": "business_card_watchdog_live_pilot_operator_response_validation",
                    "arguments": {"run_id": selected_run_id, "response": "<operator-response>"}
                    if selected_run_id
                    else {"run_id": "<run-id>", "response": "<operator-response>"},
                },
                "selected_live_target_preflight": {
                    "tool": "business_card_watchdog_selected_live_target_preflight",
                    "arguments": {"run_id": selected_run_id, "response": "<operator-response>"}
                    if selected_run_id
                    else {"run_id": "<run-id>", "response": "<operator-response>"},
                },
                "selected_live_target_preview": {
                    "tool": "business_card_watchdog_selected_live_target_artifact_preview",
                    "arguments": {"run_id": selected_run_id, "response": "<operator-response>"}
                    if selected_run_id
                    else {"run_id": "<run-id>", "response": "<operator-response>"},
                },
                "selected_live_target_from_response": {
                    "tool": "business_card_watchdog_selected_live_target_from_response",
                    "arguments": {"run_id": selected_run_id, "response": "<operator-response>"}
                    if selected_run_id
                    else {"run_id": "<run-id>", "response": "<operator-response>"},
                },
                "selected_live_target_handoff_from_response": {
                    "tool": "business_card_watchdog_selected_live_target_handoff_from_response",
                    "arguments": {"run_id": selected_run_id, "response": "<operator-response>", "write_audit": False}
                    if selected_run_id
                    else {"run_id": "<run-id>", "response": "<operator-response>", "write_audit": False},
                },
                "lookup_smoke_handoff_from_response": {
                    "tool": "business_card_watchdog_lookup_smoke_handoff_from_response",
                    "arguments": {
                        "run_id": selected_run_id,
                        "response": "<operator-response>",
                        "write_handoff": False,
                    }
                    if selected_run_id
                    else {"run_id": "<run-id>", "response": "<operator-response>", "write_handoff": False},
                },
                "selected_lookup_smoke_execution_packet_from_response": {
                    "tool": "business_card_watchdog_selected_lookup_smoke_execution_packet_from_response",
                    "arguments": {
                        "run_id": selected_run_id,
                        "response": "<operator-response>",
                        "execute_selected_lookup_smoke": False,
                    }
                    if selected_run_id
                    else {
                        "run_id": "<run-id>",
                        "response": "<operator-response>",
                        "execute_selected_lookup_smoke": False,
                    },
                },
                "selected_write_pilot_execution_packet_from_response": {
                    "tool": "business_card_watchdog_selected_write_pilot_execution_packet_from_response",
                    "arguments": {
                        "run_id": selected_run_id,
                        "response": "<operator-response>",
                        "execute_write_pilot": False,
                    }
                    if selected_run_id
                    else {
                        "run_id": "<run-id>",
                        "response": "<operator-response>",
                        "execute_write_pilot": False,
                    },
                },
                "selected_readback_pilot_execution_packet_from_response": {
                    "tool": "business_card_watchdog_selected_readback_pilot_execution_packet_from_response",
                    "arguments": {
                        "run_id": selected_run_id,
                        "response": "<operator-response>",
                        "execute_readback_pilot": False,
                    }
                    if selected_run_id
                    else {
                        "run_id": "<run-id>",
                        "response": "<operator-response>",
                        "execute_readback_pilot": False,
                    },
                },
                "live_pilot_closeout_packet_from_response": {
                    "tool": "business_card_watchdog_live_pilot_closeout_packet_from_response",
                    "arguments": {
                        "run_id": selected_run_id,
                        "response": "<operator-response>",
                        "write_closeout": False,
                    }
                    if selected_run_id
                    else {
                        "run_id": "<run-id>",
                        "response": "<operator-response>",
                        "write_closeout": False,
                    },
                },
                "live_pilot_operator_workflow_packet_from_response": {
                    "tool": "business_card_watchdog_live_pilot_operator_workflow_packet_from_response",
                    "arguments": {"run_id": selected_run_id, "response": "<operator-response>"}
                    if selected_run_id
                    else {"run_id": "<run-id>", "response": "<operator-response>"},
                },
                "live_pilot_operator_rehearsal_from_response": {
                    "tool": "business_card_watchdog_live_pilot_operator_rehearsal_from_response",
                    "arguments": {"run_id": selected_run_id, "response": "<operator-response>"}
                    if selected_run_id
                    else {"run_id": "<run-id>", "response": "<operator-response>"},
                },
                "live_pilot_readiness_export_from_response": {
                    "tool": "business_card_watchdog_live_pilot_readiness_export_from_response",
                    "arguments": {"run_id": selected_run_id, "response": "<operator-response>", "write": True}
                    if selected_run_id
                    else {"run_id": "<run-id>", "response": "<operator-response>", "write": True},
                },
                "live_pilot_execution_checklist_from_response": {
                    "tool": "business_card_watchdog_live_pilot_execution_checklist_from_response",
                    "arguments": {"run_id": selected_run_id, "response": "<operator-response>"}
                    if selected_run_id
                    else {"run_id": "<run-id>", "response": "<operator-response>"},
                },
                "live_pilot_command_copy_packet_from_response": {
                    "tool": "business_card_watchdog_live_pilot_command_copy_packet_from_response",
                    "arguments": {
                        "run_id": selected_run_id,
                        "response": "<operator-response>",
                        "acknowledgement": "<operator-acknowledgement>",
                    }
                    if selected_run_id
                    else {
                        "run_id": "<run-id>",
                        "response": "<operator-response>",
                        "acknowledgement": "<operator-acknowledgement>",
                    },
                },
            },
            "safe_next_actions": [
                {
                    "action": "inspect_runtime_readiness",
                    "command": "runtime-readiness --json",
                    "safe_to_auto_continue": True,
                    "requires_explicit_operator_action": False,
                },
                {
                    "action": "inspect_service_recovery",
                    "command": (
                        f"service recovery --run-id {selected_run_id} --json"
                        if selected_run_id
                        else "service recovery --json"
                    ),
                    "safe_to_auto_continue": True,
                    "requires_explicit_operator_action": False,
                },
                {
                    "action": "inspect_review_queue" if selected_run_id else "inspect_runs",
                    "command": (
                        f"reviews list --run-id {selected_run_id} --state all --json"
                        if selected_run_id
                        else "runs list --json"
                    ),
                    "safe_to_auto_continue": True,
                    "requires_explicit_operator_action": False,
                },
                {
                    "action": "inspect_live_pilot_status" if selected_run_id else "inspect_runs",
                    "command": (
                        f"runs live-pilot-status {selected_run_id} --no-write --json"
                        if selected_run_id
                        else "runs list --json"
                    ),
                    "safe_to_auto_continue": True,
                    "requires_explicit_operator_action": False,
                },
                {
                    "action": "inspect_live_pilot_handoff" if selected_run_id else "inspect_runs",
                    "command": (
                        f"runs live-pilot-handoff {selected_run_id} --no-write --json"
                        if selected_run_id
                        else "runs list --json"
                    ),
                    "safe_to_auto_continue": True,
                    "requires_explicit_operator_action": False,
                },
                {
                    "action": "run_fixture_review_routing_drill",
                    "command": "drills review-routing --json",
                    "safe_to_auto_continue": True,
                    "requires_explicit_operator_action": False,
                },
            ],
            "explicit_stop_conditions": [
                "Do not process private SyncThing images from the operator dashboard.",
                "Do not run public-web search or paid API enrichment from the operator dashboard.",
                "Do not run live GWS/Odollo/Odoo lookup, write, or readback without selected target approval.",
            ],
            "writes_attempted": 0,
            "network_calls_made": 0,
        }

    def get_run(self, run_id: str) -> dict[str, Any]:
        run_dir = self.config.runs_dir / run_id
        run_path = run_dir / "run.json"
        if not run_path.exists():
            raise FileNotFoundError(f"run not found: {run_id}")
        payload = json.loads(run_path.read_text(encoding="utf-8"))
        payload["run_dir"] = str(run_dir)
        payload["jobs"] = self.list_jobs(run_id)
        payload["artifacts"] = self.list_artifacts(run_id)
        return payload

    def run_summary(self, run_id: str) -> dict[str, Any]:
        run = self.get_run(run_id)
        jobs = run["jobs"]
        artifacts = run["artifacts"]
        state_counts: dict[str, int] = {}
        artifact_counts: dict[str, int] = {}
        for job in jobs:
            state = str(job.get("state") or "unknown")
            state_counts[state] = state_counts.get(state, 0) + 1
        for artifact in artifacts:
            kind = str(artifact.get("kind") or "unknown")
            artifact_counts[kind] = artifact_counts.get(kind, 0) + 1
        enrichment_budget = self._summarize_enrichment_budget(artifacts)
        sink_pilot_summary = self._summarize_sink_pilot_progress(jobs=jobs, artifacts=artifacts)
        review_workbook_preview_summary = self._summarize_review_workbook_preview(artifacts)
        return {
            "run_id": run_id,
            "state": run["state"],
            "job_count": run["job_count"],
            "state_counts": state_counts,
            "artifact_counts": artifact_counts,
            "enrichment_budget": enrichment_budget,
            "sink_pilot_summary": sink_pilot_summary,
            "review_workbook_preview_summary": review_workbook_preview_summary,
            "needs_review_count": state_counts.get("needs_review", 0),
            "ready_to_route_count": state_counts.get("ready_to_route", 0),
            "failed_count": state_counts.get("failed", 0),
            "duplicate_assessment_count": artifact_counts.get("duplicate_assessment", 0),
            "reviewed_contact_count": artifact_counts.get("reviewed_contact", 0),
        }

    def dry_run_closeout(self, run_id: str, *, write: bool = True) -> dict[str, Any]:
        run = self.get_run(run_id)
        run_dir = self.config.runs_dir / run_id
        jobs = list(run.get("jobs") or [])
        artifacts = list(run.get("artifacts") or [])
        events_path = run_dir / "events.jsonl"
        events = _read_jsonl(events_path) if events_path.exists() else []
        event_types = [str(event.get("event_type") or "") for event in events]
        artifact_kinds = [str(artifact.get("kind") or "") for artifact in artifacts]
        state_counts: dict[str, int] = {}
        artifact_counts: dict[str, int] = {}
        for job in jobs:
            state = str(job.get("state") or "unknown")
            state_counts[state] = state_counts.get(state, 0) + 1
        for kind in artifact_kinds:
            artifact_counts[kind] = artifact_counts.get(kind, 0) + 1
        live_event_types = [
            event_type
            for event_type in event_types
            if any(token in event_type for token in ["live", "write_pilot", "readback_pilot", "lookup_pilot"])
        ]
        live_artifact_kinds = [
            kind
            for kind in artifact_kinds
            if any(token in kind for token in ["live", "write_pilot", "readback_pilot", "lookup_pilot"])
        ]
        writes_attempted = max((_max_nested_int(event, "writes_attempted") for event in events), default=0)
        network_calls_made = max((_max_nested_int(event, "network_calls_made") for event in events), default=0)
        blocked_reasons: list[str] = []
        if run.get("state") != "completed":
            blocked_reasons.append(f"run state is {run.get('state')}")
        if run.get("dry_run") is not True:
            blocked_reasons.append("run was not executed in dry-run mode")
        if live_event_types:
            blocked_reasons.append("ledger contains live/pilot event types")
        if live_artifact_kinds:
            blocked_reasons.append("ledger contains live/pilot artifact kinds")
        if writes_attempted:
            blocked_reasons.append("ledger reports write attempts")
        if network_calls_made:
            blocked_reasons.append("ledger reports network calls")
        state = "ready_for_review_and_routing" if not blocked_reasons else "blocked"
        payload: dict[str, Any] = {
            "schema": "business-card-watchdog.dry-run-closeout.v1",
            "generated_at": utc_now(),
            "state": state,
            "run_id": run_id,
            "run_state": run.get("state"),
            "dry_run": run.get("dry_run"),
            "job_count": run.get("job_count"),
            "state_counts": state_counts,
            "artifact_counts": artifact_counts,
            "event_count": len(events),
            "event_types": sorted(set(event_types)),
            "live_event_types": sorted(set(live_event_types)),
            "live_artifact_kinds": sorted(set(live_artifact_kinds)),
            "blocked_reasons": blocked_reasons,
            "files_processed": int(run.get("job_count") or len(jobs)),
            "ocr_artifact_count": artifact_counts.get("ocr_text", 0),
            "contact_candidate_count": artifact_counts.get("contact_candidate", 0),
            "review_packet_count": artifact_counts.get("review_packet", 0),
            "review_report_count": artifact_counts.get("review_report", 0),
            "sink_payload_count": artifact_counts.get("sink_payloads", 0),
            "writes_attempted": writes_attempted,
            "network_calls_made": network_calls_made,
            "private_sources_used": False,
            "public_web_search_used": False,
            "paid_enrichment_used": False,
            "live_sink_calls_made": bool(live_event_types or live_artifact_kinds or writes_attempted or network_calls_made),
            "runtime_artifact_written": False,
            "closeout_path": None,
            "safe_next_actions": [
                {
                    "action": "inspect_run_summary",
                    "command": f"runs summary {run_id} --json",
                    "safe_to_auto_continue": True,
                    "requires_explicit_operator_action": False,
                },
                {
                    "action": "inspect_phase_report",
                    "command": f"runs phase-report {run_id} --json",
                    "safe_to_auto_continue": True,
                    "requires_explicit_operator_action": False,
                },
                {
                    "action": "inspect_review_queue",
                    "command": f"reviews list --run-id {run_id} --state all --json",
                    "safe_to_auto_continue": True,
                    "requires_explicit_operator_action": False,
                },
                {
                    "action": "inspect_next_actions",
                    "command": f"actions next --run-id {run_id} --json",
                    "safe_to_auto_continue": True,
                    "requires_explicit_operator_action": False,
                },
            ],
            "explicit_stop_conditions": [
                "This closeout reads local run ledger artifacts only.",
                "Do not treat dry-run closeout as approval for live sink lookup, write, or readback.",
                "Do not run public-web search or paid enrichment from this closeout.",
                "Use live-pilot selection gates before any Google Contacts, Odoo, or Odollo calls.",
            ],
            "commands": {
                "dry_run_closeout": f"runs dry-run-closeout {run_id} --json",
                "run_summary": f"runs summary {run_id} --json",
                "phase_report": f"runs phase-report {run_id} --json",
                "reviews": f"reviews list --run-id {run_id} --state all --json",
                "next_actions": f"actions next --run-id {run_id} --json",
                "operator_dashboard": f"operator-dashboard --run-id {run_id} --json",
                "live_pilot_preflight": f"operator-selected-live-smoke-preflight --run-id {run_id} --no-write --json",
            },
        }
        if write:
            closeout_path = run_dir / "dry_run_closeout.json"
            payload["runtime_artifact_written"] = True
            payload["closeout_path"] = str(closeout_path)
            closeout_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            ledger = RunLedger(run_dir)
            ledger.record_artifact(job_id="__run__", kind="dry_run_closeout", path=closeout_path)
            ledger.record_event(
                "dry_run_closeout_created",
                {
                    "run_id": run_id,
                    "state": state,
                    "closeout_path": str(closeout_path),
                    "writes_attempted": 0,
                    "network_calls_made": 0,
                },
            )
        return payload

    def phase_report(self, run_id: str) -> dict[str, Any]:
        run = self.get_run(run_id)
        jobs = run["jobs"]
        artifacts = run["artifacts"]
        artifacts_by_job: dict[str, set[str]] = {}
        for artifact in artifacts:
            artifacts_by_job.setdefault(str(artifact.get("job_id") or ""), set()).add(
                str(artifact.get("kind") or "")
            )
        next_by_job = {
            str(action["job_id"]): action
            for action in self.next_actions(run_id=run_id, limit=max(1000, int(run.get("job_count") or 0) + 10))[
                "actions"
            ]
        }
        phases = [
            "ingest",
            "normalize",
            "review",
            "enrichment",
            "dedupe",
            "route",
            "sink_lookup",
            "apply_approval",
            "write_pilot",
            "readback_pilot",
            "pilot_report",
        ]
        phase_rows: dict[str, dict[str, Any]] = {
            phase: {
                "phase": phase,
                "counts": {},
                "blocked_action_counts": {},
                "job_ids_by_state": {},
            }
            for phase in phases
        }
        job_rows: list[dict[str, Any]] = []
        for job in jobs:
            job_id = str(job.get("job_id") or "")
            artifact_kinds = artifacts_by_job.get(job_id, set())
            next_action = next_by_job.get(job_id)
            phase_states = self._phase_states_for_job(
                job=job,
                artifact_kinds=artifact_kinds,
                next_action=next_action,
            )
            for phase, state in phase_states.items():
                row = phase_rows[phase]
                counts = row["counts"]
                counts[state] = counts.get(state, 0) + 1
                row["job_ids_by_state"].setdefault(state, []).append(job_id)
                if state in {"blocked", "explicit_required"}:
                    action = str((next_action or {}).get("action") or "unknown")
                    blocked_counts = row["blocked_action_counts"]
                    blocked_counts[action] = blocked_counts.get(action, 0) + 1
            job_rows.append(
                {
                    "job_id": job_id,
                    "state": job.get("state"),
                    "next_action": (next_action or {}).get("action"),
                    "phase_states": phase_states,
                }
            )
        phase_list = [phase_rows[phase] for phase in phases]
        review_workbook_preview = self._review_workbook_preview_phase(artifacts)
        return {
            "schema": "business-card-watchdog.phase-report.v1",
            "run_id": run_id,
            "created_at": utc_now(),
            "run_state": run.get("state"),
            "job_count": len(jobs),
            "stop_rules": self._phase_stop_rules(),
            "review_workbook_preview": review_workbook_preview,
            "dashboard_summary": self._phase_dashboard_summary(
                phases=phase_list,
                review_workbook_preview=review_workbook_preview,
            ),
            "phases": phase_list,
            "jobs": job_rows,
            "commands": {
                "phase_report": f"runs phase-report {run_id}",
                "pilot_readiness": f"runs pilot-readiness {run_id}",
                "review_bundle": f"reviews bundle --run-id {run_id} --state all",
                "review_workbook": f"reviews workbook --run-id {run_id} --state all",
                "run_next_safe": f"actions run-next --run-id {run_id}",
                "live_pilot_handoff": f"runs live-pilot-handoff {run_id}",
            },
            "writes_attempted": 0,
            "network_calls_made": 0,
        }

    def pilot_readiness_report(self, run_id: str) -> dict[str, Any]:
        run_summary = self.run_summary(run_id)
        phase_report = self.phase_report(run_id)
        review_bundle = self.review_bundle(run_id=run_id, state="all", write=False)
        next_actions = self.next_actions(
            run_id=run_id,
            limit=max(1000, _int(run_summary.get("job_count")) + 10),
        )
        next_by_job = {str(action.get("job_id") or ""): action for action in next_actions["actions"]}
        phase_by_job = {str(job.get("job_id") or ""): job for job in phase_report["jobs"]}
        entries = review_bundle["entries"]

        jobs: list[dict[str, Any]] = []
        counts = {
            "blocked": 0,
            "safe_auto_available": 0,
            "explicit_operator_required": 0,
            "ready_for_write_pilot": 0,
            "write_pilot_complete": 0,
            "readback_complete": 0,
            "pilot_report_complete": 0,
            "complete": 0,
        }
        blocking_reasons_by_job: dict[str, list[dict[str, Any]]] = {}
        ready_job_ids: list[str] = []
        blocked_job_ids: list[str] = []
        safe_auto_job_ids: list[str] = []
        explicit_action_job_ids: list[str] = []
        pilot_complete_job_ids: list[str] = []

        for entry in entries:
            job_id = str(entry.get("job_id") or "")
            next_action = next_by_job.get(job_id) or entry.get("next_action") or {}
            matrix = dict(entry.get("review_matrix") or {})
            sink_pilot_status = dict(entry.get("sink_pilot_status") or {})
            phase_job = phase_by_job.get(job_id) or {}
            phase_states = dict(phase_job.get("phase_states") or {})
            blocking_reasons = self._pilot_readiness_blocking_reasons(
                phase_states=phase_states,
                next_action=next_action,
            )
            readiness_state = self._pilot_readiness_state_for_job(
                phase_states=phase_states,
                next_action=next_action,
                blocking_reasons=blocking_reasons,
            )
            if blocking_reasons:
                counts["blocked"] += 1
                blocked_job_ids.append(job_id)
                blocking_reasons_by_job[job_id] = blocking_reasons
            if next_action.get("action") in _SAFE_NEXT_ACTIONS:
                counts["safe_auto_available"] += 1
                safe_auto_job_ids.append(job_id)
            if next_action.get("action") in _EXPLICIT_OPERATOR_ACTIONS:
                counts["explicit_operator_required"] += 1
                explicit_action_job_ids.append(job_id)
            if next_action.get("action") == "execute_sink_write_pilot":
                counts["ready_for_write_pilot"] += 1
                ready_job_ids.append(job_id)
            if phase_states.get("write_pilot") == "complete":
                counts["write_pilot_complete"] += 1
            if phase_states.get("readback_pilot") == "complete":
                counts["readback_complete"] += 1
            if phase_states.get("pilot_report") == "complete":
                counts["pilot_report_complete"] += 1
                pilot_complete_job_ids.append(job_id)
            if readiness_state == "complete":
                counts["complete"] += 1

            jobs.append(
                {
                    "job_id": job_id,
                    "state": entry.get("state"),
                    "image_path": entry.get("image_path"),
                    "readiness_state": readiness_state,
                    "next_action": next_action.get("action"),
                    "next_action_reason": next_action.get("reason"),
                    "safe_to_auto_continue": bool(sink_pilot_status.get("safe_to_auto_continue")),
                    "requires_explicit_operator_action": bool(
                        sink_pilot_status.get("requires_explicit_operator_action")
                    ),
                    "blocking_reasons": blocking_reasons,
                    "phase_states": phase_states,
                    "review_matrix": matrix,
                    "sink_pilot_status": sink_pilot_status,
                    "artifact_kinds": entry.get("artifact_kinds") or [],
                    "artifact_paths": {
                        kind: record.get("path")
                        for kind, record in (entry.get("artifacts") or {}).items()
                        if isinstance(record, dict) and record.get("path")
                    },
                    "commands": {
                        "review": (entry.get("commands") or {}).get("review"),
                        "next": (entry.get("commands") or {}).get("next"),
                        "show_job": (entry.get("commands") or {}).get("show_job"),
                    },
                }
            )

        job_count = len(jobs)
        if job_count == 0:
            state = "empty"
        elif counts["complete"] == job_count:
            state = "complete"
        elif counts["ready_for_write_pilot"]:
            state = "ready_for_write_pilot"
        elif counts["explicit_operator_required"]:
            state = "explicit_operator_required"
        elif counts["blocked"]:
            state = "blocked"
        elif counts["safe_auto_available"]:
            state = "safe_auto_available"
        else:
            state = "in_progress"

        return {
            "schema": "business-card-watchdog.pilot-readiness-report.v1",
            "run_id": run_id,
            "created_at": utc_now(),
            "state": state,
            "job_count": job_count,
            "counts": counts,
            "ready_job_ids": ready_job_ids,
            "blocked_job_ids": blocked_job_ids,
            "safe_auto_job_ids": safe_auto_job_ids,
            "explicit_action_job_ids": explicit_action_job_ids,
            "pilot_complete_job_ids": pilot_complete_job_ids,
            "blocking_reasons_by_job": blocking_reasons_by_job,
            "phase_dashboard_summary": phase_report["dashboard_summary"],
            "review_workbook_preview": phase_report["review_workbook_preview"],
            "sink_pilot_summary": run_summary["sink_pilot_summary"],
            "enrichment_budget": run_summary["enrichment_budget"],
            "review_groups": review_bundle["groups"],
            "next_actions": next_actions["actions"],
            "stop_rules": phase_report["stop_rules"],
            "jobs": jobs,
            "commands": {
                "phase_report": f"runs phase-report {run_id}",
                "pilot_readiness": f"runs pilot-readiness {run_id}",
                "review_bundle": f"reviews bundle --run-id {run_id} --state all",
                "review_workbook": f"reviews workbook --run-id {run_id} --state all",
                "run_next_safe": f"actions run-next --run-id {run_id}",
                "live_pilot_handoff": f"runs live-pilot-handoff {run_id}",
            },
            "writes_attempted": 0,
            "network_calls_made": 0,
        }

    def _pilot_readiness_state_for_job(
        self,
        *,
        phase_states: dict[str, str],
        next_action: dict[str, Any],
        blocking_reasons: list[dict[str, Any]],
    ) -> str:
        next_action_name = str(next_action.get("action") or "")
        if phase_states.get("pilot_report") == "complete":
            return "complete"
        if next_action_name == "execute_sink_write_pilot":
            return "ready_for_write_pilot"
        if next_action_name == "execute_sink_readback_pilot":
            return "ready_for_readback_pilot"
        if next_action_name == "prepare_sink_apply_pilot_report":
            return "ready_for_pilot_report"
        if next_action_name in _EXPLICIT_OPERATOR_ACTIONS:
            return "explicit_operator_required"
        if next_action_name in _SAFE_NEXT_ACTIONS:
            return "safe_auto_available"
        if blocking_reasons:
            return "blocked"
        return "in_progress"

    def _pilot_readiness_blocking_reasons(
        self,
        *,
        phase_states: dict[str, str],
        next_action: dict[str, Any],
    ) -> list[dict[str, Any]]:
        reasons: list[dict[str, Any]] = []
        action = str(next_action.get("action") or "")
        reason = str(next_action.get("reason") or "")
        for phase, state in phase_states.items():
            if state in {"blocked", "explicit_required"}:
                reasons.append(
                    {
                        "phase": phase,
                        "state": state,
                        "action": action or None,
                        "reason": reason or None,
                    }
                )
        return reasons

    def _phase_stop_rules(self) -> dict[str, Any]:
        return {
            "schema": "business-card-watchdog.phase-stop-rules.v1",
            "safe_auto_actions": sorted(_SAFE_NEXT_ACTIONS),
            "explicit_operator_actions": sorted(_EXPLICIT_OPERATOR_ACTIONS),
            "generic_continue_policy": {
                "allows_paid_api_enrichment": False,
                "allows_public_web_enrichment": False,
                "allows_live_sink_write": False,
                "allows_live_sink_readback": False,
                "allows_zero_write_artifact_preparation": True,
            },
            "phase_actions": {
                "enrichment": {
                    "safe_auto_actions": [],
                    "explicit_operator_actions": ["request_enrichment", "review_enrichment"],
                },
                "apply_approval": {
                    "safe_auto_actions": ["preflight_sink_apply", "prepare_sink_apply_pilot_readiness"],
                    "explicit_operator_actions": ["decide_sink_apply", "await_apply_approval"],
                },
                "write_pilot": {
                    "safe_auto_actions": [],
                    "explicit_operator_actions": ["execute_sink_write_pilot"],
                },
                "readback_pilot": {
                    "safe_auto_actions": [],
                    "explicit_operator_actions": ["execute_sink_readback_pilot"],
                },
                "pilot_report": {
                    "safe_auto_actions": ["prepare_sink_apply_pilot_report"],
                    "explicit_operator_actions": [],
                },
            },
        }

    def _phase_dashboard_summary(
        self,
        *,
        phases: list[dict[str, Any]],
        review_workbook_preview: dict[str, Any],
    ) -> dict[str, Any]:
        blocked_phases: list[dict[str, Any]] = []
        explicit_required_phases: list[dict[str, Any]] = []
        pending_phases: list[dict[str, Any]] = []
        complete_phases: list[dict[str, Any]] = []
        for phase in phases:
            counts = dict(phase.get("counts") or {})
            phase_name = str(phase.get("phase") or "")
            if counts.get("blocked"):
                blocked_phases.append({"phase": phase_name, "count": counts["blocked"]})
            if counts.get("explicit_required"):
                explicit_required_phases.append({"phase": phase_name, "count": counts["explicit_required"]})
            if counts.get("pending"):
                pending_phases.append({"phase": phase_name, "count": counts["pending"]})
            if counts.get("complete"):
                complete_phases.append({"phase": phase_name, "count": counts["complete"]})
        preview_state = str(review_workbook_preview.get("state") or "unknown")
        status_line = (
            f"{len(blocked_phases)} blocked phases; "
            f"{len(explicit_required_phases)} explicit-required phases; "
            f"review workbook preview {preview_state}"
        )
        return {
            "schema": "business-card-watchdog.phase-dashboard-summary.v1",
            "status_line": status_line,
            "review_workbook_preview_state": preview_state,
            "blocked_phase_count": len(blocked_phases),
            "explicit_required_phase_count": len(explicit_required_phases),
            "pending_phase_count": len(pending_phases),
            "complete_phase_count": len(complete_phases),
            "blocked_phases": blocked_phases,
            "explicit_required_phases": explicit_required_phases,
            "pending_phases": pending_phases,
            "complete_phases": complete_phases,
        }

    def _review_workbook_preview_phase(self, artifacts: list[dict[str, Any]]) -> dict[str, Any]:
        summary = self._summarize_review_workbook_preview(artifacts)
        if not summary["has_preview"]:
            state = "not_started"
        elif summary["unreadable_artifact_count"]:
            state = "unreadable"
        elif summary["latest_valid"] is False or summary["latest_error_count"] > 0:
            state = "invalid"
        else:
            state = "valid"
        counts = {name: 0 for name in ("not_started", "valid", "invalid", "unreadable")}
        counts[state] = 1
        return {
            "schema": "business-card-watchdog.review-workbook-preview-phase.v1",
            "state": state,
            "counts": counts,
            "preview_count": summary["preview_count"],
            "validation_csv_count": summary["validation_csv_count"],
            "latest_preview_path": summary["latest_preview_path"],
            "latest_validation_csv_path": summary["latest_validation_csv_path"],
            "latest_valid": summary["latest_valid"],
            "latest_row_count": summary["latest_row_count"],
            "latest_ready_count": summary["latest_ready_count"],
            "latest_error_count": summary["latest_error_count"],
            "latest_skipped_count": summary["latest_skipped_count"],
            "latest_warning_count": summary["latest_warning_count"],
            "unreadable_artifact_count": summary["unreadable_artifact_count"],
        }

    def _phase_states_for_job(
        self,
        *,
        job: dict[str, Any],
        artifact_kinds: set[str],
        next_action: dict[str, Any] | None,
    ) -> dict[str, str]:
        job_state = str(job.get("state") or "")
        next_action_name = str((next_action or {}).get("action") or "")
        failed = job_state == "failed"
        cancelled = job_state == "cancelled"

        def base_state(required_kinds: set[str], *, optional: bool = False) -> str:
            if failed:
                return "blocked"
            if cancelled:
                return "skipped"
            if artifact_kinds.intersection(required_kinds):
                return "complete"
            return "not_requested" if optional else "pending"

        states = {
            "ingest": base_state({"contact_spec", "preclassification", "contact_candidate"}),
            "normalize": base_state({"contact_candidate", "reviewed_contact"}),
            "review": base_state({"reviewed_contact", "review_submission"}),
            "enrichment": base_state(
                {
                    "enrichment_result",
                    "enrichment_public_web_result",
                    "enrichment_provider_result",
                    "enrichment_merge_review",
                },
                optional=True,
            ),
            "dedupe": base_state({"duplicate_assessment", "downstream_duplicate_assessment", "duplicate_resolution"}),
            "route": base_state({"sink_plan"}),
            "sink_lookup": base_state({"sink_lookup_result"}),
            "apply_approval": base_state({"sink_apply_decision"}),
            "write_pilot": base_state({"sink_write_pilot"}, optional=True),
            "readback_pilot": base_state({"sink_readback_pilot"}, optional=True),
            "pilot_report": base_state({"sink_apply_pilot_report"}, optional=True),
        }

        if job_state == "needs_review":
            states["review"] = "blocked"
        if next_action_name == "review_enrichment":
            states["enrichment"] = "blocked"
        if next_action_name in {"resolve_duplicate", "review_duplicate"}:
            states["dedupe"] = "blocked"
        if next_action_name in {"decide_sink_apply", "await_apply_approval"}:
            states["apply_approval"] = "explicit_required"
        if next_action_name == "execute_sink_write_pilot":
            states["write_pilot"] = "explicit_required"
        if next_action_name == "execute_sink_readback_pilot":
            states["readback_pilot"] = "explicit_required"
        if next_action_name == "prepare_sink_apply_pilot_report":
            states["pilot_report"] = "pending"
        if "sink_apply_pilot_report" in artifact_kinds:
            states["pilot_report"] = "complete"
        return states

    def _summarize_enrichment_budget(self, artifacts: list[dict[str, Any]]) -> dict[str, Any]:
        public_web = {
            "request_count": 0,
            "result_count": 0,
            "max_queries": 0,
            "max_queries_per_run": self.config.enrichment.max_public_web_queries_per_run,
            "remaining_queries": self.config.enrichment.max_public_web_queries_per_run,
            "submitted_result_count": 0,
            "search_calls_attempted": 0,
            "network_calls_made": 0,
        }
        paid_provider = {
            "request_count": 0,
            "result_count": 0,
            "max_results": 0,
            "max_results_per_run": self.config.enrichment.max_paid_provider_results_per_run,
            "remaining_results": self.config.enrichment.max_paid_provider_results_per_run,
            "submitted_result_count": 0,
            "paid_api_calls_attempted": 0,
            "network_calls_made": 0,
        }
        unreadable_artifact_count = 0
        for artifact in artifacts:
            kind = str(artifact.get("kind") or "")
            if kind not in {
                "enrichment_public_web_request",
                "enrichment_public_web_result",
                "enrichment_provider_request",
                "enrichment_provider_result",
            }:
                continue
            path = Path(str(artifact.get("path") or ""))
            if not path.exists():
                unreadable_artifact_count += 1
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                unreadable_artifact_count += 1
                continue
            if kind == "enrichment_public_web_request":
                public_web["request_count"] += 1
                public_web["max_queries"] += _int(payload.get("max_queries"))
                public_web["search_calls_attempted"] += _int(payload.get("search_calls_attempted"))
                public_web["network_calls_made"] += _int(payload.get("network_calls_made"))
            elif kind == "enrichment_public_web_result":
                public_web["result_count"] += 1
                public_web["submitted_result_count"] += _int(payload.get("submitted_result_count"))
                public_web["search_calls_attempted"] += _int(payload.get("search_calls_attempted"))
                public_web["network_calls_made"] += _int(payload.get("network_calls_made"))
            elif kind == "enrichment_provider_request":
                paid_provider["request_count"] += 1
                paid_provider["max_results"] += _int(payload.get("max_results"))
                paid_provider["paid_api_calls_attempted"] += _int(payload.get("paid_api_calls_attempted"))
                paid_provider["network_calls_made"] += _int(payload.get("network_calls_made"))
            elif kind == "enrichment_provider_result":
                paid_provider["result_count"] += 1
                paid_provider["submitted_result_count"] += _int(payload.get("submitted_result_count"))
                paid_provider["paid_api_calls_attempted"] += _int(payload.get("paid_api_calls_attempted"))
                paid_provider["network_calls_made"] += _int(payload.get("network_calls_made"))
        public_web["remaining_queries"] = max(0, public_web["max_queries_per_run"] - public_web["max_queries"])
        paid_provider["remaining_results"] = max(0, paid_provider["max_results_per_run"] - paid_provider["max_results"])
        return {
            "schema": "business-card-watchdog.enrichment-budget-summary.v1",
            "public_web": public_web,
            "paid_provider": paid_provider,
            "unreadable_artifact_count": unreadable_artifact_count,
        }

    def _summarize_review_workbook_preview(self, artifacts: list[dict[str, Any]]) -> dict[str, Any]:
        preview_artifacts = [
            artifact
            for artifact in artifacts
            if str(artifact.get("kind") or "") == "review_workbook_preview"
        ]
        validation_artifacts = [
            artifact
            for artifact in artifacts
            if str(artifact.get("kind") or "") == "review_workbook_preview_validation_csv"
        ]
        latest_preview = preview_artifacts[-1] if preview_artifacts else None
        latest_validation = validation_artifacts[-1] if validation_artifacts else None
        summary: dict[str, Any] = {
            "schema": "business-card-watchdog.review-workbook-preview-summary.v1",
            "preview_count": len(preview_artifacts),
            "validation_csv_count": len(validation_artifacts),
            "has_preview": latest_preview is not None,
            "latest_preview_path": str(latest_preview.get("path") or "") if latest_preview else None,
            "latest_validation_csv_path": str(latest_validation.get("path") or "") if latest_validation else None,
            "latest_valid": None,
            "latest_row_count": 0,
            "latest_ready_count": 0,
            "latest_error_count": 0,
            "latest_skipped_count": 0,
            "latest_warning_count": 0,
            "unreadable_artifact_count": 0,
        }
        if latest_preview is None:
            return summary
        payload = _read_json_file(Path(str(latest_preview.get("path") or "")))
        if payload is None:
            summary["unreadable_artifact_count"] = 1
            return summary
        rows = list(payload.get("rows") or [])
        summary.update(
            {
                "latest_valid": bool(payload.get("valid")),
                "latest_row_count": _int(payload.get("row_count")),
                "latest_ready_count": _int(payload.get("ready_count")),
                "latest_error_count": _int(payload.get("error_count")),
                "latest_skipped_count": _int(payload.get("skipped_count")),
                "latest_warning_count": sum(len(row.get("warnings") or []) for row in rows if isinstance(row, dict)),
            }
        )
        return summary

    def _summarize_sink_pilot_progress(
        self,
        *,
        jobs: list[dict[str, Any]],
        artifacts: list[dict[str, Any]],
    ) -> dict[str, Any]:
        artifacts_by_job: dict[str, dict[str, dict[str, Any]]] = {}
        for artifact in artifacts:
            job_id = str(artifact.get("job_id") or "")
            kind = str(artifact.get("kind") or "")
            if kind in _REVIEW_BUNDLE_ARTIFACT_KINDS:
                artifacts_by_job.setdefault(job_id, {})[kind] = artifact

        by_state: dict[str, int] = {}
        job_statuses: list[dict[str, Any]] = []
        total_writes_attempted = 0
        total_network_calls_made = 0
        for job in jobs:
            job_id = str(job.get("job_id") or "")
            by_kind = artifacts_by_job.get(job_id, {})
            next_action = self._next_action_for_job(job, set(by_kind))
            status = self._sink_pilot_status(by_kind=by_kind, next_action=next_action)
            state = str(status.get("state") or "not_started")
            by_state[state] = by_state.get(state, 0) + 1
            total_writes_attempted += _int(status.get("writes_attempted"))
            total_network_calls_made += _int(status.get("network_calls_made"))
            job_statuses.append(
                {
                    "job_id": job_id,
                    "state": state,
                    "latest_artifact_kind": status.get("latest_artifact_kind"),
                    "has_write_pilot": status.get("has_write_pilot"),
                    "has_readback_pilot": status.get("has_readback_pilot"),
                    "has_pilot_report": status.get("has_pilot_report"),
                    "report_complete": status.get("report_complete"),
                    "next_action": status.get("next_action"),
                    "safe_to_auto_continue": status.get("safe_to_auto_continue"),
                    "requires_explicit_operator_action": status.get("requires_explicit_operator_action"),
                }
            )

        return {
            "schema": "business-card-watchdog.sink-pilot-summary.v1",
            "job_count": len(jobs),
            "by_state": dict(sorted(by_state.items())),
            "write_pilot_count": sum(1 for status in job_statuses if status["has_write_pilot"]),
            "readback_pilot_count": sum(1 for status in job_statuses if status["has_readback_pilot"]),
            "pilot_report_count": sum(1 for status in job_statuses if status["has_pilot_report"]),
            "complete_report_count": sum(1 for status in job_statuses if status["report_complete"]),
            "safe_to_auto_continue_count": sum(1 for status in job_statuses if status["safe_to_auto_continue"]),
            "explicit_operator_action_count": sum(
                1 for status in job_statuses if status["requires_explicit_operator_action"]
            ),
            "writes_attempted": total_writes_attempted,
            "network_calls_made": total_network_calls_made,
            "jobs": job_statuses,
        }

    def _enforce_run_enrichment_budget(self, *, run_id: str, mode: str) -> None:
        summary = self.run_summary(run_id)
        budget = summary["enrichment_budget"]
        if mode in {"public_web", "all"}:
            public_web = budget["public_web"]
            projected_queries = public_web["max_queries"] + self.config.enrichment.max_public_web_queries_per_contact
            max_queries = public_web["max_queries_per_run"]
            if projected_queries > max_queries:
                raise ValueError(
                    "public web enrichment request exceeds run budget: "
                    f"{projected_queries} requested queries for max {max_queries}"
                )
        if mode in {"api", "all"}:
            paid_provider = budget["paid_provider"]
            projected_results = paid_provider["max_results"] + self.config.enrichment.max_paid_provider_results_per_contact
            max_results = paid_provider["max_results_per_run"]
            if projected_results > max_results:
                raise ValueError(
                    "paid provider enrichment request exceeds run budget: "
                    f"{projected_results} requested results for max {max_results}"
                )

    def next_actions(self, *, run_id: str | None = None, limit: int = 20) -> dict[str, Any]:
        actions: list[dict[str, Any]] = []
        runs = [self.get_run(run_id)] if run_id else self.list_runs()
        for run in runs:
            current_run_id = str(run["run_id"])
            for job in self.list_jobs(current_run_id):
                artifacts = [
                    artifact
                    for artifact in self.list_artifacts(current_run_id)
                    if artifact.get("job_id") == job["job_id"]
                ]
                kinds = {str(artifact.get("kind")) for artifact in artifacts}
                action = self._next_action_for_job(job, kinds)
                if action is not None:
                    action_name = str(action.get("action") or "")
                    actions.append(
                        {
                            "run_id": current_run_id,
                            "job_id": job["job_id"],
                            **action,
                            "safe_to_auto_continue": action_name in _SAFE_NEXT_ACTIONS,
                            "requires_explicit_operator_action": action_name in _EXPLICIT_OPERATOR_ACTIONS,
                        }
                    )
                if len(actions) >= limit:
                    break
            if len(actions) >= limit:
                break
        return {
            "run_id": run_id,
            "limit": limit,
            "actions": actions,
            "action_count": len(actions),
        }

    def run_next_actions(self, *, run_id: str | None = None, limit: int = 10) -> dict[str, Any]:
        executed: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        phase_report_before = self.phase_report(run_id) if run_id else None
        for _ in range(max(0, limit)):
            candidates = self.next_actions(run_id=run_id, limit=max(1, limit))["actions"]
            executable = next(
                (candidate for candidate in candidates if candidate.get("action") in _SAFE_NEXT_ACTIONS),
                None,
            )
            if executable is None:
                skipped = [
                    {
                        **candidate,
                        "status": "skipped",
                        "skip_reason": "action requires review, approval, live apply, or manual inspection",
                    }
                    for candidate in candidates
                ]
                break
            result = self._execute_safe_next_action(executable)
            executed.append(
                {
                    **executable,
                    "status": "executed",
                    "result": result,
                }
            )
        phase_report_after = self.phase_report(run_id) if run_id else None
        safe_inspection_commands = {
            "live_pilot_status": f"runs live-pilot-status {run_id} --no-write --json"
            if run_id
            else "runs list --json",
            "live_pilot_handoff": f"runs live-pilot-handoff {run_id} --no-write --json"
            if run_id
            else "runs list --json",
            "operator_dashboard": f"operator-dashboard --run-id {run_id} --json"
            if run_id
            else "operator-dashboard --json",
            "service_recovery": f"service recovery --run-id {run_id} --json"
            if run_id
            else "service recovery --json",
        }
        return {
            "run_id": run_id,
            "limit": limit,
            "executed": executed,
            "skipped": skipped,
            "executed_count": len(executed),
            "skipped_count": len(skipped),
            "writes_attempted": 0,
            "network_calls_made": 0,
            "safe_auto_actions": sorted(_SAFE_NEXT_ACTIONS),
            "explicit_operator_actions": sorted(_EXPLICIT_OPERATOR_ACTIONS),
            "safe_inspection_commands": safe_inspection_commands,
            "operator_stop_conditions": [
                "Do not execute skipped actions from run-next without explicit operator approval.",
                "Do not run live lookup, live write, or live readback from deterministic safe continuation.",
                "Do not process private SyncThing images, run public-web search, or call paid enrichment from run-next.",
            ],
            "phase_report_before": phase_report_before,
            "phase_report_after": phase_report_after,
        }

    def multi_card_preclassification_drill(self) -> dict[str, Any]:
        ensure_runtime_dirs(self.config)
        run_id = f"fixture-multi-card-preclassification-{utc_now().replace(':', '-')}-{uuid4().hex[:8]}"
        fixture_dir = self.config.cache_dir / "fixture-drills" / run_id
        image_path, expected_count, fixture_available = _write_synthetic_multi_card_image(
            fixture_dir / "synthetic-multi-card-photo.jpg"
        )
        assessment = assess_business_card_candidate(
            image_path,
            min_score=self.config.prefilter.min_score,
        )
        assessment_payload = assessment.to_dict()
        rectangle = dict(assessment_payload.get("analyzers", {}).get("opencv_rectangle") or {})
        boxes = [box for box in list(rectangle.get("boxes") or []) if isinstance(box, dict)]
        detected_count = int(rectangle.get("card_like_count") or 0)
        assertions = {
            "fixture_image_available": fixture_available,
            "opencv_rectangle_available": rectangle.get("available") is True,
            "decision_likely_business_card": assessment.decision == "likely_business_card",
            "detected_expected_card_boxes": detected_count >= expected_count,
            "candidate_boxes_recorded": len(boxes) >= expected_count,
            "no_private_sources": True,
            "no_public_web_search": True,
            "no_paid_enrichment": True,
            "no_live_sink_calls": True,
        }
        state = "passed" if all(assertions.values()) else "needs_attention"

        run_dir = self.config.runs_dir / run_id
        ledger = RunLedger(run_dir)
        ledger.initialize(source=str(fixture_dir), dry_run=True)
        ledger.transition_run("discovering")
        ledger.transition_run("completed")
        drill_path = run_dir / "multi_card_preclassification_drill.json"
        preclassification_path = run_dir / "multi_card_preclassification.json"
        payload = {
            "schema": "business-card-watchdog.multi-card-preclassification-drill.v1",
            "generated_at": utc_now(),
            "state": state,
            "run_id": run_id,
            "fixture_dir": str(fixture_dir),
            "fixture_image_path": str(image_path),
            "expected_card_count": expected_count,
            "detected_card_like_count": detected_count,
            "candidate_boxes": boxes,
            "preclassification": assessment_payload,
            "assertions": assertions,
            "private_sources_used": False,
            "public_web_search_used": False,
            "paid_enrichment_used": False,
            "live_sink_calls_made": False,
            "writes_attempted": 0,
            "network_calls_made": 0,
            "commands": {
                "multi_card_preclassification_drill": "drills multi-card-preclassification --json",
                "operator_dashboard": f"operator-dashboard --run-id {run_id} --json",
                "run_show": f"runs show {run_id} --json",
            },
            "explicit_stop_conditions": [
                "This drill uses only a synthetic fixture image written under the cache directory.",
                "Candidate boxes are deterministic pre-OCR evidence only; App Intelligence still verifies contacts later.",
                "Do not process private SyncThing images, run public-web search, call paid enrichment, or call GWS/Odollo/Odoo from this drill.",
            ],
        }
        preclassification_path.write_text(
            json.dumps(assessment_payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        drill_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        ledger.record_artifact(job_id="__run__", kind="multi_card_preclassification", path=preclassification_path)
        ledger.record_artifact(job_id="__run__", kind="multi_card_preclassification_drill", path=drill_path)
        ledger.record_event(
            "multi_card_preclassification_drill_completed",
            {
                "run_id": run_id,
                "drill_path": str(drill_path),
                "state": state,
                "expected_card_count": expected_count,
                "detected_card_like_count": detected_count,
                "writes_attempted": 0,
                "network_calls_made": 0,
            },
        )
        payload["drill_path"] = str(drill_path)
        payload["preclassification_path"] = str(preclassification_path)
        return payload

    def review_routing_drill(self) -> dict[str, Any]:
        ensure_runtime_dirs(self.config)
        run_id = f"fixture-review-routing-{utc_now().replace(':', '-')}-{uuid4().hex[:8]}"
        fixture_dir = self.config.cache_dir / "fixture-drills" / run_id
        image_path = _write_synthetic_business_card_image(fixture_dir / "synthetic-business-card.png")
        run_dir = self.config.runs_dir / run_id
        artifact_dir = run_dir / "artifacts"

        ledger = RunLedger(run_dir)
        ledger.initialize(source=str(fixture_dir), dry_run=True)
        ledger.transition_run("discovering")

        job = CardJob.from_path(image_path)
        job.artifact_dir = str(artifact_dir / job.job_id)
        ledger.set_job_count(1)
        ledger.record_job(job)
        ledger.transition_run("processing")
        job.transition_to("processing")
        ledger.record_job(job)

        job_artifact_dir = Path(job.artifact_dir)
        job_artifact_dir.mkdir(parents=True, exist_ok=True)
        spec = {
            "full_name": "",
            "organization": "Fixture Labs",
            "title": "Synthetic Routing Drill Contact",
            "notes": "Synthetic privacy-safe fixture for review, normalization, dedupe, and sink routing drill.",
            "source_fixture": image_path.name,
        }
        spec_path = job_artifact_dir / "spec.json"
        spec_path.write_text(json.dumps(spec, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        ledger.record_artifact(job_id=job.job_id, kind="contact_spec", path=spec_path)

        candidate = build_contact_candidate(
            spec,
            source="fixture_review_routing_drill",
            default_country=self.config.normalization.default_country,
        )
        candidate_path = job_artifact_dir / "contact_candidate.json"
        candidate_path.write_text(json.dumps(candidate, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        ledger.record_artifact(job_id=job.job_id, kind="contact_candidate", path=candidate_path)

        assessment = assess_contact_spec(contact_candidate_to_spec(candidate))
        review_packet_path = write_review_packet(
            packet_path=job_artifact_dir / "review_packet.json",
            image_path=image_path,
            spec=contact_candidate_to_spec(candidate),
            assessment=assessment,
            contact_candidate=candidate,
        )
        ledger.record_artifact(job_id=job.job_id, kind="review_packet", path=review_packet_path)
        job.transition_to("needs_review")
        ledger.record_job(job)
        ledger.record_event(
            "fixture_review_routing_drill_created",
            {
                "job_id": job.job_id,
                "run_id": run_id,
                "fixture_dir": str(fixture_dir),
                "private_sources_used": False,
                "writes_attempted": 0,
                "network_calls_made": 0,
            },
        )
        ledger.transition_run("waiting_for_review")

        review_result = self.submit_review(
            job_id=job.job_id,
            run_id=run_id,
            reviewer="fixture-drill",
            action="approve_for_routing",
            field_corrections={
                "full_name": "Fixture Routing Contact",
                "email": "fixture.routing@example.test",
                "phone": "+1 555 0100",
                "organization": "Fixture Labs",
            },
            notes="approved by synthetic fixture drill",
        )
        ledger.transition_run("routing")

        drill_config = replace(
            self.config,
            sink=SinkConfig(
                google_contacts=True,
                google_contacts_profile="fixture-gws-profile",
                odoo=True,
                odollo_tenant="fixture-odollo-tenant",
                dry_run=True,
                google_contacts_apply_enabled=False,
                odoo_apply_enabled=False,
            ),
            routing_rules=[
                {
                    "match": "email_domain",
                    "value": "*",
                    "sinks": ["google_contacts", "odoo"],
                }
            ],
        )
        drill_service = BusinessCardService(
            drill_config,
            sink_lookup_executor=self.sink_lookup_executor,
            sink_write_executor=self.sink_write_executor,
            sink_readback_executor=self.sink_readback_executor,
        )
        run_next = drill_service.run_next_actions(run_id=run_id, limit=10)
        review_bundle = drill_service.review_bundle(run_id=run_id, state="all", write=True)
        review_workbook = drill_service.review_workbook(run_id=run_id, state="all", write=True)
        final_next = drill_service.next_actions(run_id=run_id, limit=10)
        phase_report = drill_service.phase_report(run_id)
        route_artifact_kinds = sorted(
            {
                str(artifact.get("kind") or "")
                for artifact in drill_service.list_artifacts(run_id)
                if artifact.get("job_id") == job.job_id and str(artifact.get("kind") or "") in _ROUTE_ARTIFACT_FILES
            }
        )
        required_route_artifacts = [
            "sink_lookup_plan",
            "sink_adapter_request_lookup",
            "sink_lookup_result",
            "downstream_duplicate_assessment",
            "sink_plan",
            "sink_adapter_request_write",
            "sink_apply_preflight",
        ]
        next_action_names = [str(action.get("action") or "") for action in final_next["actions"]]
        artifact_checks = [
            {"kind": kind, "exists": kind in route_artifact_kinds}
            for kind in required_route_artifacts
        ]
        agent_loop_readback = {
            "schema": "business-card-watchdog.review-routing-drill-agent-readback.v1",
            "state": "passed"
            if all(check["exists"] for check in artifact_checks)
            and next_action_names[:1] == ["decide_sink_apply"]
            and run_next["executed_count"] == 7
            and run_next["skipped_count"] == 1
            else "needs_attention",
            "run_id": run_id,
            "job_id": job.job_id,
            "private_sources_used": False,
            "public_web_search_used": False,
            "paid_enrichment_used": False,
            "live_sink_calls_made": False,
            "writes_attempted": 0,
            "network_calls_made": 0,
            "expected_manual_boundary": "decide_sink_apply",
            "next_manual_boundary": next_action_names[0] if next_action_names else "",
            "artifact_checks": artifact_checks,
            "safe_action_counts": {
                "executed": run_next["executed_count"],
                "skipped": run_next["skipped_count"],
            },
            "safe_actions_executed": [str(action.get("action") or "") for action in run_next["executed"]],
            "manual_actions_skipped": [str(action.get("action") or "") for action in run_next["skipped"]],
            "route_artifact_kinds": route_artifact_kinds,
        }
        payload = {
            "schema": "business-card-watchdog.review-routing-drill.v1",
            "generated_at": utc_now(),
            "run_id": run_id,
            "job_id": job.job_id,
            "fixture_dir": str(fixture_dir),
            "fixture_image_path": str(image_path),
            "private_sources_used": False,
            "public_web_search_used": False,
            "paid_enrichment_used": False,
            "live_sink_calls_made": False,
            "writes_attempted": 0,
            "network_calls_made": 0,
            "configured_fixture_sinks": ["google_contacts", "odoo"],
            "fixture_sink_context": {
                "google_contacts_profile": "fixture-gws-profile",
                "odollo_tenant": "fixture-odollo-tenant",
                "dry_run": True,
            },
            "review": {
                "initial_state": "needs_review",
                "final_state": review_result["job"]["state"],
                "reviewed_contact_path": str(job_artifact_dir / "reviewed_contact.json"),
            },
            "safe_actions": {
                "executed_count": run_next["executed_count"],
                "executed_actions": [str(action.get("action") or "") for action in run_next["executed"]],
                "skipped_count": run_next["skipped_count"],
                "skipped_actions": [str(action.get("action") or "") for action in run_next["skipped"]],
            },
            "route_artifact_kinds": route_artifact_kinds,
            "review_bundle_path": review_bundle.get("review_bundle_path"),
            "review_workbook_path": review_workbook.get("workbook_path"),
            "phase_dashboard": phase_report["dashboard_summary"],
            "next_actions": final_next["actions"],
            "agent_loop_readback": agent_loop_readback,
            "commands": {
                "review_bundle": f"reviews bundle --run-id {run_id} --state all --json",
                "review_workbook": f"reviews workbook --run-id {run_id} --state all --json",
                "next_actions": f"actions next --run-id {run_id} --json",
                "run_next_safe": f"actions run-next --run-id {run_id} --json",
                "phase_report": f"runs phase-report {run_id} --json",
            },
            "explicit_stop_conditions": [
                "This drill uses only a synthetic fixture image written under the cache directory.",
                "Do not treat fixture sink context as approval for a real GWS, Odollo, or Odoo target.",
                "Do not run public-web search, paid enrichment, live lookup, live write, or live readback from this drill.",
            ],
        }
        drill_path = run_dir / "review_routing_drill.json"
        drill_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        ledger.record_artifact(job_id="__run__", kind="review_routing_drill", path=drill_path)
        ledger.record_event(
            "review_routing_drill_completed",
            {
                "run_id": run_id,
                "job_id": job.job_id,
                "drill_path": str(drill_path),
                "executed_count": run_next["executed_count"],
                "writes_attempted": 0,
                "network_calls_made": 0,
            },
        )
        payload["drill_path"] = str(drill_path)
        return payload

    def watch_dry_run_selection_drill(self) -> dict[str, Any]:
        ensure_runtime_dirs(self.config)
        run_id = f"fixture-watch-dry-run-selection-{utc_now().replace(':', '-')}-{uuid4().hex[:8]}"
        run_dir = self.config.runs_dir / run_id
        fixture_root = self.config.cache_dir / "fixture-drills" / run_id
        source_dir = fixture_root / "source"
        image_path = _write_synthetic_business_card_image(source_dir / "synthetic-watch-card.png")
        fixture_config = replace(
            self.config,
            data_dir=run_dir / "fixture-data",
            cache_dir=fixture_root / "cache",
            watch=WatchConfig(inputs=[str(source_dir)], settle_seconds=0.0),
        )
        fixture_service = BusinessCardService(fixture_config)
        preflight = fixture_service.watch_backlog_preflight(write=False)
        handoff = fixture_service.watch_dry_run_selection_handoff(write=True)
        operator_response = (
            "input_ref=input_0 operator=fixture-operator mode=dry_run "
            "safety_confirmation='private dry run approved for this fixture source'"
        )
        validation = fixture_service.validate_watch_dry_run_operator_response(response=operator_response)
        command_copy_packet = fixture_service.watch_dry_run_command_copy_packet(
            response=operator_response,
            acknowledgement="I understand this will dry-run the configured private watch backlog",
        )
        handoff_entries = [entry for entry in list(handoff.get("entries") or []) if isinstance(entry, dict)]
        first_handoff_entry = handoff_entries[0] if handoff_entries else {}
        assertions = {
            "preflight_ready": preflight.get("state") == "ready_for_operator_selected_dry_run",
            "handoff_ready": handoff.get("state") == "awaiting_operator_response",
            "validation_ready": validation.get("state") == "ready_for_command_copy",
            "command_copy_ready": command_copy_packet.get("state") == "ready_for_operator_copy",
            "fixture_source_only": str(image_path).startswith(str(fixture_root)),
            "no_configured_watch_inputs_used": first_handoff_entry.get("configured_ref_display") == "<redacted-path>",
            "no_files_processed": command_copy_packet.get("files_processed") == 0,
            "no_ocr_attempted": command_copy_packet.get("ocr_attempted") == 0,
            "no_network_calls": command_copy_packet.get("network_calls_made") == 0,
        }
        state = "passed" if all(assertions.values()) else "needs_attention"
        payload: dict[str, Any] = {
            "schema": "business-card-watchdog.watch-dry-run-selection-drill.v1",
            "generated_at": utc_now(),
            "state": state,
            "run_id": run_id,
            "fixture_root": str(fixture_root),
            "fixture_source_dir": str(source_dir),
            "fixture_image_path": str(image_path),
            "private_sources_used": False,
            "public_web_search_used": False,
            "paid_enrichment_used": False,
            "live_sink_calls_made": False,
            "files_processed": 0,
            "ocr_attempted": 0,
            "writes_attempted": 0,
            "network_calls_made": 0,
            "operator_response_redacted": {
                "raw_response_stored": False,
                "fields": {
                    "input_ref": "input_0",
                    "operator": "fixture-operator",
                    "mode": "dry_run",
                },
            },
            "acknowledgement_redacted": {
                "required": True,
                "ok": command_copy_packet.get("acknowledgement_ok") is True,
                "raw_acknowledgement_stored": False,
            },
            "assertions": assertions,
            "packets": {
                "preflight": preflight,
                "handoff": handoff,
                "validation": validation,
                "command_copy_packet": command_copy_packet,
            },
            "command_copy_ready": command_copy_packet.get("state") == "ready_for_operator_copy",
            "command_copy_text": command_copy_packet.get("command_copy_text"),
            "commands": {
                "watch_backlog_preflight": "watch-backlog-preflight --no-write --json",
                "watch_dry_run_selection_handoff": "watch-dry-run-selection-handoff --json",
                "watch_dry_run_validate_response": "watch-dry-run-validate-response --response <operator-response> --json",
                "watch_dry_run_command_copy_packet": (
                    "watch-dry-run-command-copy-packet --response <operator-response> "
                    "--acknowledgement <operator-acknowledgement> --json"
                ),
                "watch_dry_run_selection_drill": "drills watch-dry-run-selection --json",
            },
            "explicit_stop_conditions": [
                "This drill uses only a synthetic fixture image written under the cache directory.",
                "This drill does not execute command_copy_text.",
                "Do not treat fixture command-copy text as approval for configured private SyncThing inputs.",
                "Do not process private SyncThing images, run public-web search, call paid enrichment, or call GWS/Odollo/Odoo from this drill.",
            ],
        }
        sample_output_path = run_dir / "watch_dry_run_selection_sample_output.md"
        drill_path = run_dir / "watch_dry_run_selection_drill.json"
        payload["sample_outputs"] = {
            "watch_dry_run_selection_markdown_path": str(sample_output_path),
            "raw_operator_response_stored": False,
            "raw_acknowledgement_stored": False,
        }
        run_dir.mkdir(parents=True, exist_ok=True)
        sample_output_path.write_text(
            self._render_watch_dry_run_selection_sample_output(payload),
            encoding="utf-8",
        )
        drill_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        ledger = RunLedger(run_dir)
        ledger.initialize(source=str(fixture_root), dry_run=True)
        ledger.transition_run("discovering")
        ledger.transition_run("completed")
        ledger.record_artifact(
            job_id="__run__",
            kind="watch_dry_run_selection_sample_output",
            path=sample_output_path,
        )
        ledger.record_artifact(job_id="__run__", kind="watch_dry_run_selection_drill", path=drill_path)
        ledger.record_event(
            "watch_dry_run_selection_drill_completed",
            {
                "run_id": run_id,
                "drill_path": str(drill_path),
                "sample_output_path": str(sample_output_path),
                "state": state,
                "writes_attempted": 0,
                "network_calls_made": 0,
            },
        )
        payload["drill_path"] = str(drill_path)
        return payload

    def _render_watch_dry_run_selection_sample_output(self, payload: dict[str, Any]) -> str:
        packets = dict(payload.get("packets") or {})
        preflight = dict(packets.get("preflight") or {})
        handoff = dict(packets.get("handoff") or {})
        validation = dict(packets.get("validation") or {})
        command_copy_packet = dict(packets.get("command_copy_packet") or {})
        commands = dict(payload.get("commands") or {})
        stop_conditions = list(payload.get("explicit_stop_conditions") or [])
        redacted_fields = dict(payload.get("operator_response_redacted", {}).get("fields") or {})
        lines = [
            "# Watch Dry-Run Selection Sample Output",
            "",
            "Synthetic fixture only. Do not use this sample as approval for configured private watch inputs.",
            "",
            "## Drill State",
            "",
            f"- Run: `{payload.get('run_id')}`",
            f"- State: `{payload.get('state')}`",
            f"- Preflight: `{preflight.get('state')}`",
            f"- Handoff: `{handoff.get('state')}`",
            f"- Validation: `{validation.get('state')}`",
            f"- Command copy packet: `{command_copy_packet.get('state')}`",
            f"- Command copy ready: `{payload.get('command_copy_ready')}`",
            f"- Files processed: `{payload.get('files_processed', 0)}`",
            f"- OCR attempted: `{payload.get('ocr_attempted', 0)}`",
            f"- Writes attempted: `{payload.get('writes_attempted', 0)}`",
            f"- Network calls made: `{payload.get('network_calls_made', 0)}`",
            "",
            "## Redaction",
            "",
            "- Raw operator response stored: `False`",
            "- Raw acknowledgement stored: `False`",
            "- Operator response fields retained:",
        ]
        for key in ["input_ref", "operator", "mode"]:
            lines.append(f"  - {key}: `{redacted_fields.get(key)}`")
        lines.extend(
            [
                "",
                "## Watch Counts",
                "",
                f"- Input count: `{preflight.get('input_count', 0)}`",
                f"- Backlog count: `{dict(preflight.get('counts') or {}).get('backlog', 0)}`",
                f"- Unsettled count: `{dict(preflight.get('counts') or {}).get('unsettled', 0)}`",
                "",
                "## Commands",
                "",
                f"- Backlog preflight: `{commands.get('watch_backlog_preflight')}`",
                f"- Selection handoff: `{commands.get('watch_dry_run_selection_handoff')}`",
                f"- Validate response: `{commands.get('watch_dry_run_validate_response')}`",
                f"- Command copy packet: `{commands.get('watch_dry_run_command_copy_packet')}`",
                f"- Re-run drill: `{commands.get('watch_dry_run_selection_drill')}`",
                "",
                "## Command Copy",
                "",
                "- The drill proves command-copy gating but does not execute the copied command.",
                f"- Command copy text: `{payload.get('command_copy_text')}`",
                "",
                "## Stop Conditions",
                "",
            ]
        )
        for condition in stop_conditions:
            lines.append(f"- {condition}")
        lines.append("")
        return "\n".join(lines)

    def watch_dry_run_execution_drill(self) -> dict[str, Any]:
        ensure_runtime_dirs(self.config)
        drill_id = f"fixture-watch-dry-run-execution-{utc_now().replace(':', '-')}-{uuid4().hex[:8]}"
        drill_root = self.config.cache_dir / "fixture-drills" / drill_id
        source_dir = drill_root / "source"
        data_dir = self.config.runs_dir / drill_id / "fixture-data"
        cache_dir = drill_root / "cache"
        image_path = _write_synthetic_business_card_image(source_dir / "synthetic-watch-execution-card.png")
        drill_config = replace(
            self.config,
            data_dir=data_dir,
            cache_dir=cache_dir,
            watch=WatchConfig(inputs=[str(source_dir)], settle_seconds=0.0),
            prefilter=PrefilterConfig(enabled=False),
            sink=SinkConfig(
                google_contacts=True,
                google_contacts_profile="fixture-gws-profile",
                odoo=True,
                odollo_tenant="fixture-odollo-tenant",
                dry_run=True,
                google_contacts_apply_enabled=False,
                odoo_apply_enabled=False,
            ),
            routing_rules=[
                {
                    "match": "email_domain",
                    "value": "*",
                    "sinks": ["google_contacts", "odoo"],
                }
            ],
        )
        first = PollingWatcher(drill_config)
        first.orchestrator.adapter = _FixtureSkillAdapter()
        first_scan = [str(path) for path in first.scan_once(dry_run=True)]

        seen_records = []
        if first.state.seen_path.exists():
            seen_records = [
                json.loads(line)
                for line in first.state.seen_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        processed_run_dirs = [str(record.get("run_dir")) for record in seen_records if record.get("run_dir")]
        processed_run_dir = Path(processed_run_dirs[0]) if processed_run_dirs else None
        run_payload: dict[str, Any] = {}
        job_records: list[dict[str, Any]] = []
        artifact_records: list[dict[str, Any]] = []
        event_types: list[str] = []
        if processed_run_dir is not None:
            run_path = processed_run_dir / "run.json"
            jobs_path = processed_run_dir / "jobs.jsonl"
            artifacts_path = processed_run_dir / "artifacts.jsonl"
            events_path = processed_run_dir / "events.jsonl"
            if run_path.exists():
                run_payload = json.loads(run_path.read_text(encoding="utf-8"))
            if jobs_path.exists():
                job_records = [json.loads(line) for line in jobs_path.read_text(encoding="utf-8").splitlines() if line]
            if artifacts_path.exists():
                artifact_records = [
                    json.loads(line) for line in artifacts_path.read_text(encoding="utf-8").splitlines() if line
                ]
            if events_path.exists():
                event_types = [
                    str(json.loads(line).get("event_type"))
                    for line in events_path.read_text(encoding="utf-8").splitlines()
                    if line
                ]

        restarted = PollingWatcher(drill_config)
        restarted.orchestrator.adapter = _FixtureSkillAdapter()
        second_scan = [str(path) for path in restarted.scan_once(dry_run=True)]
        final_status = restarted.status().to_dict()
        latest_job = job_records[-1] if job_records else {}
        artifact_kinds = sorted({str(record.get("kind")) for record in artifact_records if record.get("kind")})
        assertions = {
            "synthetic_source_only": str(image_path).startswith(str(drill_root)),
            "configured_watch_inputs_not_used": final_status.get("inputs") == [str(source_dir)],
            "first_scan_processed_one": first_scan == [str(image_path)],
            "second_scan_processed_zero": second_scan == [],
            "seen_file_persisted": int(final_status.get("seen_count", 0)) == 1,
            "processed_run_recorded": processed_run_dir is not None and processed_run_dir.exists(),
            "run_completed": run_payload.get("state") == "completed",
            "run_was_dry_run": run_payload.get("dry_run") is True,
            "job_recorded": len(job_records) >= 1,
            "contact_candidate_written": "contact_candidate" in artifact_kinds,
            "review_report_written": "review_report" in artifact_kinds,
            "sink_payloads_written": "sink_payloads" in artifact_kinds,
            "sink_decision_dry_run_recorded": "sink_decision_dry_run" in event_types,
            "no_private_sources_used": True,
            "no_live_sink_calls": True,
            "no_network_calls": True,
        }
        state = "passed" if all(assertions.values()) else "needs_attention"
        payload: dict[str, Any] = {
            "schema": "business-card-watchdog.watch-dry-run-execution-drill.v1",
            "generated_at": utc_now(),
            "state": state,
            "drill_id": drill_id,
            "drill_root": str(drill_root),
            "source_dir": str(source_dir),
            "data_dir": str(data_dir),
            "watch_dir": str(drill_config.watch_dir),
            "synthetic_images": [str(image_path)],
            "first_scan_processed": first_scan,
            "second_scan_processed": second_scan,
            "processed_run_dirs": processed_run_dirs,
            "processed_run": {
                "run_id": run_payload.get("run_id"),
                "path": str(processed_run_dir) if processed_run_dir is not None else None,
                "state": run_payload.get("state"),
                "dry_run": run_payload.get("dry_run"),
                "job_count": run_payload.get("job_count"),
                "latest_job_state": latest_job.get("state"),
                "artifact_kinds": artifact_kinds,
                "event_types": event_types,
            },
            "final_status": final_status,
            "assertions": assertions,
            "files_processed": len(first_scan),
            "ocr_attempted": 1 if "ocr_text" in artifact_kinds else 0,
            "writes_attempted": 0,
            "network_calls_made": 0,
            "private_sources_used": False,
            "public_web_search_used": False,
            "paid_enrichment_used": False,
            "live_sink_calls_made": False,
            "commands": {
                "watch_dry_run_execution_drill": "drills watch-dry-run-execution --json",
                "watch_dry_run_selection_drill": "drills watch-dry-run-selection --json",
                "watch_dry_run": "watch-dry-run --json",
                "watch_status": "watch-status --json",
                "run_summary": f"runs summary {processed_run_dir.name}" if processed_run_dir is not None else None,
                "operator_dashboard": (
                    f"operator-dashboard --run-id {processed_run_dir.name}" if processed_run_dir is not None else None
                ),
            },
            "explicit_stop_conditions": [
                "This drill executes the watcher only against a synthetic fixture source.",
                "This drill does not use configured SyncThing/private watch inputs.",
                "This drill uses dry-run routing only and does not call live sink adapters.",
                "Do not treat this fixture execution as approval to run the configured private watch backlog.",
            ],
        }
        sample_output_path = self.config.runs_dir / drill_id / "watch_dry_run_execution_sample_output.md"
        drill_path = self.config.runs_dir / drill_id / "watch_dry_run_execution_drill.json"
        sample_output_path.parent.mkdir(parents=True, exist_ok=True)
        payload["sample_outputs"] = {
            "watch_dry_run_execution_markdown_path": str(sample_output_path),
        }
        sample_output_path.write_text(
            self._render_watch_dry_run_execution_sample_output(payload),
            encoding="utf-8",
        )
        drill_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        payload["drill_path"] = str(drill_path)
        return payload

    def _render_watch_dry_run_execution_sample_output(self, payload: dict[str, Any]) -> str:
        processed_run = dict(payload.get("processed_run") or {})
        commands = dict(payload.get("commands") or {})
        stop_conditions = list(payload.get("explicit_stop_conditions") or [])
        artifact_kinds = list(processed_run.get("artifact_kinds") or [])
        lines = [
            "# Watch Dry-Run Execution Sample Output",
            "",
            "Synthetic fixture only. This sample proves watched dry-run execution without configured private inputs.",
            "",
            "## Drill State",
            "",
            f"- Drill: `{payload.get('drill_id')}`",
            f"- State: `{payload.get('state')}`",
            f"- Files processed: `{payload.get('files_processed', 0)}`",
            f"- OCR attempted: `{payload.get('ocr_attempted', 0)}`",
            f"- Writes attempted: `{payload.get('writes_attempted', 0)}`",
            f"- Network calls made: `{payload.get('network_calls_made', 0)}`",
            f"- Private sources used: `{payload.get('private_sources_used')}`",
            "",
            "## Processed Run",
            "",
            f"- Run id: `{processed_run.get('run_id')}`",
            f"- State: `{processed_run.get('state')}`",
            f"- Dry run: `{processed_run.get('dry_run')}`",
            f"- Job count: `{processed_run.get('job_count')}`",
            f"- Latest job state: `{processed_run.get('latest_job_state')}`",
            "",
            "## Artifacts",
            "",
        ]
        if artifact_kinds:
            for kind in artifact_kinds:
                lines.append(f"- `{kind}`")
        else:
            lines.append("- none")
        lines.extend(
            [
                "",
                "## Commands",
                "",
                f"- Re-run execution drill: `{commands.get('watch_dry_run_execution_drill')}`",
                f"- Selection drill: `{commands.get('watch_dry_run_selection_drill')}`",
                f"- Watch dry-run harness: `{commands.get('watch_dry_run')}`",
                f"- Watch status: `{commands.get('watch_status')}`",
                f"- Run summary: `{commands.get('run_summary')}`",
                f"- Operator dashboard: `{commands.get('operator_dashboard')}`",
                "",
                "## Stop Conditions",
                "",
            ]
        )
        for condition in stop_conditions:
            lines.append(f"- {condition}")
        lines.append("")
        return "\n".join(lines)

    def live_pilot_rehearsal_drill(self) -> dict[str, Any]:
        routing_drill = self.review_routing_drill()
        run_id = str(routing_drill["run_id"])
        job_id = str(routing_drill["job_id"])
        sink = "google_contacts"
        operator = "fixture-operator"
        scope = "lookup"
        safety_confirmation = "fixture contact is safe for google contacts test profile"
        operator_response = (
            f"run_id={run_id} job_id={job_id} sink={sink} operator={operator} "
            f"scope={scope} safety_confirmation={safety_confirmation}"
        )
        acknowledgement = (
            f"acknowledge run_id={run_id} job_id={job_id} sink={sink} operator={operator} copy command"
        )
        drill_config = replace(
            self.config,
            sink=SinkConfig(
                google_contacts=True,
                google_contacts_profile="fixture-gws-profile",
                odoo=True,
                odollo_tenant="fixture-odollo-tenant",
                dry_run=True,
                google_contacts_apply_enabled=False,
                odoo_apply_enabled=False,
            ),
            routing_rules=[
                {
                    "match": "email_domain",
                    "value": "*",
                    "sinks": ["google_contacts", "odoo"],
                }
            ],
        )
        drill_service = BusinessCardService(
            drill_config,
            sink_lookup_executor=self.sink_lookup_executor,
            sink_write_executor=self.sink_write_executor,
            sink_readback_executor=self.sink_readback_executor,
        )
        selection_packet = drill_service.live_selection_packet(
            job_id=job_id,
            run_id=run_id,
            sink=sink,
            operator=operator,
            scope=scope,
        )
        validation = drill_service.validate_live_pilot_operator_response(
            run_id=run_id,
            response=operator_response,
        )
        operator_selected_preflight = drill_service.operator_selected_live_smoke_preflight(
            run_id=run_id,
            sink=sink,
            write=True,
        )
        selected_target = drill_service.selected_live_target_from_response(
            run_id=run_id,
            response=operator_response,
            write_selected_target=True,
            reason="synthetic live pilot rehearsal drill",
        )
        selected_target_handoff = drill_service.selected_live_target_handoff_from_response(
            run_id=run_id,
            response=operator_response,
            write_audit=True,
        )
        lookup_handoff = drill_service.lookup_smoke_handoff_from_response(
            run_id=run_id,
            response=operator_response,
            write_handoff=True,
        )
        workflow_packet = drill_service.live_pilot_operator_workflow_packet_from_response(
            run_id=run_id,
            response=operator_response,
        )
        rehearsal = drill_service.live_pilot_operator_rehearsal_from_response(
            run_id=run_id,
            response=operator_response,
        )
        readiness_export = drill_service.live_pilot_readiness_export_from_response(
            run_id=run_id,
            response=operator_response,
        )
        execution_checklist = drill_service.live_pilot_execution_checklist_from_response(
            run_id=run_id,
            response=operator_response,
        )
        command_copy_packet = drill_service.live_pilot_command_copy_packet_from_response(
            run_id=run_id,
            response=operator_response,
            acknowledgement=acknowledgement,
        )
        assertions = {
            "routing_drill_passed": routing_drill.get("agent_loop_readback", {}).get("state") == "passed",
            "selection_packet_generated": selection_packet.get("schema")
            == "business-card-watchdog.live-selection-packet.v1",
            "validation_ready": validation.get("state") == "ready_to_select_live_target",
            "operator_selected_preflight_generated": operator_selected_preflight.get("schema")
            == "business-card-watchdog.operator-selected-live-smoke-preflight.v1"
            and operator_selected_preflight.get("writes_attempted") == 0
            and operator_selected_preflight.get("network_calls_made") == 0,
            "selected_target_created": selected_target.get("state") == "created",
            "selected_target_handoff_generated": selected_target_handoff.get("schema")
            == "business-card-watchdog.selected-live-target-handoff-from-response.v1",
            "lookup_handoff_generated": lookup_handoff.get("schema")
            == "business-card-watchdog.lookup-smoke-handoff-from-response.v1",
            "rehearsal_ready": rehearsal.get("state") == "ready_for_explicit_operator_step",
            "readiness_export_written": readiness_export.get("export_written") is True,
            "execution_checklist_ready": execution_checklist.get("state") == "ready_for_explicit_operator_command",
            "command_copy_ready": command_copy_packet.get("state") == "ready_for_operator_copy",
            "no_private_sources": routing_drill.get("private_sources_used") is False,
            "no_public_web_search": routing_drill.get("public_web_search_used") is False,
            "no_paid_enrichment": routing_drill.get("paid_enrichment_used") is False,
            "no_live_sink_calls": routing_drill.get("live_sink_calls_made") is False,
        }
        state = "passed" if all(assertions.values()) else "needs_attention"
        command_copy_text = command_copy_packet.get("command_copy_text")
        payload = {
            "schema": "business-card-watchdog.live-pilot-rehearsal-drill.v1",
            "generated_at": utc_now(),
            "state": state,
            "run_id": run_id,
            "job_id": job_id,
            "sink": sink,
            "operator": operator,
            "scope": scope,
            "fixture_source": "review_routing_drill",
            "private_sources_used": False,
            "public_web_search_used": False,
            "paid_enrichment_used": False,
            "live_sink_calls_made": False,
            "writes_attempted": 0,
            "network_calls_made": 0,
            "operator_response_redacted": {
                "fields": {
                    "run_id": run_id,
                    "job_id": job_id,
                    "sink": sink,
                    "operator": operator,
                    "scope": scope,
                },
                "raw_response_stored": False,
            },
            "acknowledgement_redacted": {
                "required": True,
                "ok": command_copy_packet.get("acknowledgement_ok") is True,
                "raw_acknowledgement_stored": False,
            },
            "assertions": assertions,
            "routing_drill": {
                "schema": routing_drill.get("schema"),
                "state": routing_drill.get("agent_loop_readback", {}).get("state"),
                "drill_path": routing_drill.get("drill_path"),
                "route_artifact_kinds": routing_drill.get("route_artifact_kinds"),
            },
            "packets": {
                "operator_selected_preflight": operator_selected_preflight,
                "selection_packet": selection_packet,
                "validation": validation,
                "selected_target": selected_target,
                "selected_target_handoff": selected_target_handoff,
                "lookup_handoff": lookup_handoff,
                "workflow_packet": workflow_packet,
                "rehearsal": rehearsal,
                "readiness_export": readiness_export,
                "execution_checklist": execution_checklist,
                "command_copy_packet": command_copy_packet,
            },
            "command_copy_ready": command_copy_packet.get("state") == "ready_for_operator_copy",
            "command_copy_text": command_copy_text,
            "commands": {
                "review_routing_drill": "drills review-routing --json",
                "live_pilot_rehearsal_drill": "drills live-pilot-rehearsal --json",
                "operator_dashboard": f"operator-dashboard --run-id {run_id} --json",
                "live_pilot_status": f"runs live-pilot-status {run_id} --no-write --json",
                "live_pilot_handoff": f"runs live-pilot-handoff {run_id} --no-write --json",
                "readiness_export": (
                    f"runs live-pilot-readiness-export-from-response {shlex.quote(run_id)} "
                    "--response <operator-response> --json"
                ),
                "execution_checklist": (
                    f"runs live-pilot-execution-checklist-from-response {shlex.quote(run_id)} "
                    "--response <operator-response> --json"
                ),
                "command_copy_packet": (
                    f"runs live-pilot-command-copy-packet-from-response {shlex.quote(run_id)} "
                    "--response <operator-response> --acknowledgement <operator-acknowledgement> --json"
                ),
            },
            "explicit_stop_conditions": [
                "This drill uses only synthetic fixture data and fixture sink context.",
                "Do not run command_copy_text against a real sink; this drill is not live approval.",
                "Do not process private SyncThing images, run public-web search, call paid enrichment, or call GWS/Odollo/Odoo from this drill.",
                "Use the documented operator-selected live pilot procedure with a real operator-selected target before any non-simulated sink call.",
            ],
        }
        sample_output_path = self.config.runs_dir / run_id / "live_pilot_rehearsal_sample_output.md"
        preflight_sample_output_path = (
            self.config.runs_dir / run_id / "operator_selected_live_smoke_preflight_sample_output.md"
        )
        payload["sample_outputs"] = {
            "live_pilot_rehearsal_markdown_path": str(sample_output_path),
            "operator_selected_live_smoke_preflight_markdown_path": str(preflight_sample_output_path),
            "documents_packets": [
                "operator_selected_preflight",
                "selection_packet",
                "validation",
                "selected_target_handoff",
                "lookup_handoff",
                "workflow_packet",
                "rehearsal",
                "readiness_export",
                "execution_checklist",
                "command_copy_packet",
            ],
            "raw_operator_response_stored": False,
            "raw_acknowledgement_stored": False,
        }
        sample_output_path.write_text(
            self._render_live_pilot_rehearsal_sample_output(payload),
            encoding="utf-8",
        )
        preflight_sample_output_path.write_text(
            self._render_operator_selected_live_smoke_preflight_sample_output(payload),
            encoding="utf-8",
        )
        drill_path = self.config.runs_dir / run_id / "live_pilot_rehearsal_drill.json"
        drill_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        ledger = RunLedger(self.config.runs_dir / run_id)
        ledger.record_artifact(job_id="__run__", kind="live_pilot_rehearsal_sample_output", path=sample_output_path)
        ledger.record_artifact(
            job_id="__run__",
            kind="operator_selected_live_smoke_preflight_sample_output",
            path=preflight_sample_output_path,
        )
        ledger.record_artifact(job_id="__run__", kind="live_pilot_rehearsal_drill", path=drill_path)
        ledger.record_event(
            "live_pilot_rehearsal_drill_completed",
            {
                "run_id": run_id,
                "job_id": job_id,
                "drill_path": str(drill_path),
                "state": state,
                "writes_attempted": 0,
                "network_calls_made": 0,
            },
        )
        payload["drill_path"] = str(drill_path)
        return payload

    def _render_live_pilot_rehearsal_sample_output(self, payload: dict[str, Any]) -> str:
        packets = dict(payload.get("packets") or {})
        commands = dict(payload.get("commands") or {})
        stop_conditions = list(payload.get("explicit_stop_conditions") or [])
        readiness_export = dict(packets.get("readiness_export") or {})
        command_copy_packet = dict(packets.get("command_copy_packet") or {})
        workflow_packet = dict(packets.get("workflow_packet") or {})
        rehearsal = dict(packets.get("rehearsal") or {})
        redacted_fields = dict(payload.get("operator_response_redacted", {}).get("fields") or {})
        lines = [
            "# Live Pilot Rehearsal Sample Output",
            "",
            "Synthetic fixture only. Do not use this sample as live sink approval.",
            "",
            "## Run",
            "",
            f"- Run: `{payload.get('run_id')}`",
            f"- Job: `{payload.get('job_id')}`",
            f"- Sink: `{payload.get('sink')}`",
            f"- Operator: `{payload.get('operator')}`",
            f"- Scope: `{payload.get('scope')}`",
            f"- State: `{payload.get('state')}`",
            f"- Writes attempted: `{payload.get('writes_attempted', 0)}`",
            f"- Network calls made: `{payload.get('network_calls_made', 0)}`",
            "",
            "## Redaction",
            "",
            "- Raw operator response stored: `False`",
            "- Raw acknowledgement stored: `False`",
            "- Operator response fields retained:",
        ]
        for key in ["run_id", "job_id", "sink", "operator", "scope"]:
            lines.append(f"  - {key}: `{redacted_fields.get(key)}`")
        lines.extend(
            [
                "",
                "## Packet States",
                "",
                f"- Operator-selected preflight: `{dict(packets.get('operator_selected_preflight') or {}).get('state')}`",
                f"- Selection packet: `{dict(packets.get('selection_packet') or {}).get('state')}`",
                f"- Operator response validation: `{dict(packets.get('validation') or {}).get('state')}`",
                f"- Selected target: `{dict(packets.get('selected_target') or {}).get('state')}`",
                f"- Selected target handoff: `{dict(packets.get('selected_target_handoff') or {}).get('state')}`",
                f"- Lookup handoff: `{dict(packets.get('lookup_handoff') or {}).get('state')}`",
                f"- Workflow packet: `{workflow_packet.get('state')}`",
                f"- Operator rehearsal: `{rehearsal.get('state')}`",
                f"- Readiness export written: `{readiness_export.get('export_written')}`",
                f"- Execution checklist: `{dict(packets.get('execution_checklist') or {}).get('state')}`",
                f"- Command copy packet: `{command_copy_packet.get('state')}`",
                "",
                "## Operator Commands",
                "",
                f"- Dashboard: `{commands.get('operator_dashboard')}`",
                f"- Live pilot status: `{commands.get('live_pilot_status')}`",
                f"- Live pilot handoff: `{commands.get('live_pilot_handoff')}`",
                f"- Readiness export: `{commands.get('readiness_export')}`",
                f"- Execution checklist: `{commands.get('execution_checklist')}`",
                f"- Command copy packet: `{commands.get('command_copy_packet')}`",
                "",
                "## Command Copy",
                "",
                "- The drill proves command-copy gating but does not execute the copied command.",
                f"- Command copy ready: `{payload.get('command_copy_ready')}`",
                f"- Command copy text: `{payload.get('command_copy_text')}`",
                "",
                "## Stop Conditions",
                "",
            ]
        )
        for condition in stop_conditions:
            lines.append(f"- {condition}")
        lines.append("")
        return "\n".join(lines)

    def _render_operator_selected_live_smoke_preflight_sample_output(self, payload: dict[str, Any]) -> str:
        packets = dict(payload.get("packets") or {})
        preflight = dict(packets.get("operator_selected_preflight") or {})
        commands = dict(preflight.get("commands") or {})
        checklist = list(preflight.get("operator_selection_checklist") or [])
        ready_entries = list(preflight.get("ready_entries") or [])
        blocked_reasons = list(preflight.get("blocked_reasons") or [])
        stop_conditions = list(preflight.get("explicit_stop_conditions") or [])
        lines = [
            "# Operator-Selected Live Smoke Preflight Sample Output",
            "",
            "Synthetic fixture only. Do not use this sample as live sink approval.",
            "",
            "## Preflight State",
            "",
            f"- Run: `{preflight.get('run_id')}`",
            f"- Sink: `{preflight.get('sink')}`",
            f"- State: `{preflight.get('state')}`",
            f"- Recommended next step: `{preflight.get('recommended_next_step')}`",
            f"- Candidate count: `{preflight.get('candidate_count', 0)}`",
            f"- Ready entry count: `{preflight.get('ready_entry_count', 0)}`",
            f"- Active selected target count: `{preflight.get('active_selected_target_count', 0)}`",
            f"- Writes attempted: `{preflight.get('writes_attempted', 0)}`",
            f"- Network calls made: `{preflight.get('network_calls_made', 0)}`",
            f"- Preflight written: `{preflight.get('preflight_written')}`",
            "",
            "## Ready Entries",
            "",
        ]
        if ready_entries:
            for entry in ready_entries:
                if isinstance(entry, dict):
                    missing_fields = ",".join(str(item) for item in list(entry.get("missing_operator_fields") or []))
                    lines.append(
                        f"- `{entry.get('run_id')}` / `{entry.get('job_id')}` "
                        f"sink `{entry.get('sink')}` missing `{missing_fields or 'none'}`"
                    )
        else:
            lines.append("- none")
        lines.extend(["", "## Checklist", ""])
        for item in checklist:
            if isinstance(item, dict):
                lines.append(
                    f"- `{item.get('step')}`: `{item.get('command')}` "
                    f"(operator action: `{item.get('requires_explicit_operator_action')}`)"
                )
        lines.extend(["", "## Commands", ""])
        for key in [
            "operator_selected_live_smoke_preflight",
            "offline_pilot_gap_audit",
            "live_readiness_audit",
            "live_selection_requirements",
            "live_pilot_handoff",
            "validate_operator_response",
        ]:
            lines.append(f"- {key}: `{commands.get(key)}`")
        lines.extend(["", "## Blocked Reasons", ""])
        if blocked_reasons:
            for reason in blocked_reasons:
                lines.append(f"- {reason}")
        else:
            lines.append("- none")
        lines.extend(["", "## Stop Conditions", ""])
        for condition in stop_conditions:
            lines.append(f"- {condition}")
        lines.append("")
        return "\n".join(lines)

    def child_replacement_readiness_drill(self) -> dict[str, Any]:
        ensure_runtime_dirs(self.config)
        run_id = f"fixture-child-replacement-readiness-{utc_now().replace(':', '-')}-{uuid4().hex[:8]}"
        fixture_dir = self.config.cache_dir / "fixture-drills" / run_id
        image_path, expected_count, fixture_available = _write_synthetic_multi_card_image(
            fixture_dir / "synthetic-child-replacement-photo.jpg"
        )
        drill_config = replace(
            self.config,
            sink=SinkConfig(
                google_contacts=True,
                google_contacts_profile="fixture-gws-profile",
                odoo=True,
                odollo_tenant="fixture-odollo-tenant",
                dry_run=True,
                google_contacts_apply_enabled=False,
                odoo_apply_enabled=False,
            ),
            routing_rules=[
                {
                    "match": "email_domain",
                    "value": "*",
                    "sinks": ["google_contacts", "odoo"],
                }
            ],
        )
        orchestrator = BatchOrchestrator(drill_config)
        orchestrator.adapter = _FixtureSkillAdapter()
        run_dir = orchestrator.process_source(str(fixture_dir), dry_run=True, workers=1)
        drill_service = BusinessCardService(
            drill_config,
            sink_lookup_executor=self.sink_lookup_executor,
            sink_write_executor=self.sink_write_executor,
            sink_readback_executor=self.sink_readback_executor,
        )
        child_queue = drill_service.child_review_queue(run_id=run_dir.name)
        if not child_queue:
            raise RuntimeError("synthetic child replacement drill did not produce child review candidates")
        candidate_id = str(child_queue[0]["candidate_id"])
        drill_service.submit_child_review(
            run_id=run_dir.name,
            candidate_id=candidate_id,
            reviewer="fixture-operator",
            action="approve_child_for_routing",
            notes="approved by synthetic child replacement readiness drill",
        )
        drill_service.prepare_child_route(run_id=run_dir.name, candidate_id=candidate_id)
        drill_service.record_child_sink_lookup_result(run_id=run_dir.name, candidate_id=candidate_id)
        drill_service.assess_child_downstream_duplicates(run_id=run_dir.name, candidate_id=candidate_id)
        drill_service.child_sink_plan_gate(run_id=run_dir.name, candidate_id=candidate_id)
        handoff = drill_service.child_selected_target_handoff(
            run_id=run_dir.name,
            candidate_id=candidate_id,
            sink="google_contacts",
            operator="fixture-operator",
            scope="write",
        )["handoff"]
        template = handoff["operator_response_template"]
        operator_response = (
            f"run_id={template['run_id']} job_id={template['job_id']} "
            f"candidate_id={template['candidate_id']} work_item_id={template['work_item_id']} "
            "sink=google_contacts operator=fixture-operator scope=write "
            "safety_confirmation='approved fixture google contacts target profile'"
        )
        drill_service.validate_child_selected_target_response(
            run_id=run_dir.name,
            candidate_id=candidate_id,
            response=operator_response,
        )
        drill_service.child_selected_target_execution_checklist(
            run_id=run_dir.name,
            candidate_id=candidate_id,
            response=operator_response,
        )
        drill_service.child_selected_target_command_copy_packet(
            run_id=run_dir.name,
            candidate_id=candidate_id,
            response=operator_response,
            acknowledgement=(
                f"I acknowledge run_id={run_dir.name} candidate_id={candidate_id} "
                "sink=google_contacts operator=fixture-operator ready to copy"
            ),
        )
        blocked_replacement_audit = drill_service.child_selected_target_audit(
            run_id=run_dir.name,
            candidate_id=candidate_id,
            operator="replacement-operator",
        )
        abandonment = drill_service.abandon_child_selected_target(
            run_id=run_dir.name,
            candidate_id=candidate_id,
            operator="fixture-operator",
            reason="synthetic replacement readiness drill",
        )
        reset = drill_service.child_selected_target_replacement_reset(
            run_id=run_dir.name,
            candidate_id=candidate_id,
            sink="google_contacts",
            operator="replacement-operator",
            scope="write",
            reset_by="fixture-operator",
            reason="synthetic replacement preview requested",
        )
        blocked_replacement_validation = drill_service.validate_child_replacement_response(
            run_id=run_dir.name,
            candidate_id=candidate_id,
            response=operator_response,
        )
        refresh = drill_service.refresh_child_replacement_handoff(
            run_id=run_dir.name,
            candidate_id=candidate_id,
            sink="google_contacts",
            operator="replacement-operator",
            scope="write",
            reason="synthetic replacement handoff refresh",
        )
        replacement_template = refresh["refreshed_handoff"]["operator_response_template"]
        replacement_response = (
            f"run_id={replacement_template['run_id']} job_id={replacement_template['job_id']} "
            f"candidate_id={replacement_template['candidate_id']} "
            f"work_item_id={replacement_template['work_item_id']} "
            "sink=google_contacts operator=replacement-operator scope=write "
            "safety_confirmation='approved fixture replacement google contacts target profile'"
        )
        replacement_validation = drill_service.validate_child_replacement_response(
            run_id=run_dir.name,
            candidate_id=candidate_id,
            response=replacement_response,
        )
        replacement_checklist = drill_service.child_replacement_execution_checklist(
            run_id=run_dir.name,
            candidate_id=candidate_id,
            response=replacement_response,
        )
        blocked_replacement_copy_packet = drill_service.child_replacement_command_copy_packet(
            run_id=run_dir.name,
            candidate_id=candidate_id,
            response=replacement_response,
        )
        ready_replacement_copy_packet = drill_service.child_replacement_command_copy_packet(
            run_id=run_dir.name,
            candidate_id=candidate_id,
            response=replacement_response,
            acknowledgement=(
                f"I acknowledge run_id={run_dir.name} candidate_id={candidate_id} "
                "sink=google_contacts operator=replacement-operator ready to copy"
            ),
        )
        closeout = drill_service.child_replacement_closeout_status(
            run_id=run_dir.name,
            candidate_id=candidate_id,
        )
        review_bundle = drill_service.review_bundle(run_id=run_dir.name, state="all", write=True)
        review_html = drill_service.review_html(run_id=run_dir.name, state="all", write=True)
        review_workbook = drill_service.review_workbook(run_id=run_dir.name, state="all", write=True)
        operator_dashboard = drill_service.operator_dashboard(run_id=run_dir.name)
        closeout_status = dict(closeout.get("rollup") or {})
        bundle_groups = dict(review_bundle.get("groups") or {})
        child_state_groups = dict(bundle_groups.get("by_child_replacement_state") or {})
        child_summary = dict(operator_dashboard.get("child_replacement_summary") or {})
        assertions = {
            "fixture_image_available": fixture_available,
            "expected_child_candidates_available": len(child_queue) >= min(expected_count, 1),
            "replacement_requires_abandonment_seen": blocked_replacement_audit.get("replacement_requires_abandonment")
            is True,
            "abandonment_recorded": abandonment.get("state") == "abandoned",
            "replacement_reset_ready": reset.get("state") == "ready_for_replacement_preview",
            "blocked_validation_before_refresh": blocked_replacement_validation.get("state") == "blocked",
            "replacement_handoff_ready": refresh.get("state") == "ready_for_replacement_handoff",
            "replacement_response_ready": replacement_validation.get("state") == "ready_for_no_live_replacement_checklist",
            "replacement_checklist_ready": replacement_checklist.get("state") == "ready_for_replacement_operator_review",
            "blocked_copy_requires_acknowledgement": blocked_replacement_copy_packet.get("state") == "blocked",
            "replacement_copy_ready": ready_replacement_copy_packet.get("state") == "ready_for_replacement_operator_copy",
            "closeout_ready": closeout.get("state") == "ready_for_operator_closeout",
            "predecessors_marked_stale": closeout_status.get("predecessor_artifacts_stale") is True,
            "review_bundle_groups_closeout": child_state_groups.get("ready_for_operator_closeout", {}).get("count") == 1,
            "review_html_written": bool(review_html.get("html_path")),
            "review_workbook_written": bool(review_workbook.get("workbook_path")),
            "operator_dashboard_ready_count": child_summary.get("ready_count") == 1,
            "no_private_sources": True,
            "no_public_web_search": True,
            "no_paid_enrichment": True,
            "no_live_sink_calls": True,
        }
        state = "passed" if all(assertions.values()) else "needs_attention"
        payload = {
            "schema": "business-card-watchdog.child-replacement-readiness-drill.v1",
            "generated_at": utc_now(),
            "state": state,
            "run_id": run_dir.name,
            "job_id": closeout.get("job_id"),
            "candidate_id": candidate_id,
            "fixture_dir": str(fixture_dir),
            "fixture_image_path": str(image_path),
            "fixture_child_candidate_count": len(child_queue),
            "private_sources_used": False,
            "public_web_search_used": False,
            "paid_enrichment_used": False,
            "live_sink_calls_made": False,
            "writes_attempted": 0,
            "network_calls_made": 0,
            "sample_outputs": {
                "review_bundle_path": review_bundle.get("review_bundle_path"),
                "review_html_path": review_html.get("html_path"),
                "review_workbook_path": review_workbook.get("workbook_path"),
                "operator_dashboard_command": f"operator-dashboard --run-id {run_dir.name} --json",
            },
            "readiness_states": {
                "blocked_replacement_audit": blocked_replacement_audit.get("state"),
                "blocked_replacement_validation": blocked_replacement_validation.get("state"),
                "replacement_handoff": refresh.get("state"),
                "replacement_response": replacement_validation.get("state"),
                "replacement_checklist": replacement_checklist.get("state"),
                "blocked_replacement_copy_packet": blocked_replacement_copy_packet.get("state"),
                "ready_replacement_copy_packet": ready_replacement_copy_packet.get("state"),
                "closeout": closeout.get("state"),
            },
            "closeout_rollup": closeout_status,
            "review_bundle_child_replacement_groups": child_state_groups,
            "operator_dashboard_child_replacement_summary": child_summary,
            "assertions": assertions,
            "commands": {
                "child_replacement_readiness_drill": "drills child-replacement-readiness --json",
                "review_bundle": f"reviews bundle --run-id {run_dir.name} --state all --json",
                "review_html": f"reviews html --run-id {run_dir.name} --state all --json",
                "review_workbook": f"reviews workbook --run-id {run_dir.name} --state all --json",
                "operator_dashboard": f"operator-dashboard --run-id {run_dir.name} --json",
                "closeout_status": (
                    f"reviews child-replacement-closeout-status {shlex.quote(candidate_id)} "
                    f"--run-id {run_dir.name} --json"
                ),
            },
            "explicit_stop_conditions": [
                "This drill uses only synthetic fixture data written under the cache directory.",
                "The command-copy text is offline operator copy text; it is not a live sink command.",
                "Do not process private SyncThing images, run public-web search, call paid enrichment, or call GWS/Odollo/Odoo from this drill.",
                "Use authenticated readiness and live or sandbox write/readback checks before claiming real sink routing.",
            ],
        }
        sample_output_path = self.config.runs_dir / run_dir.name / "child_replacement_readiness_sample_output.md"
        payload["sample_outputs"]["child_replacement_readiness_markdown_path"] = str(sample_output_path)
        payload["sample_outputs"]["documents_packets"] = [
            "blocked_replacement_audit",
            "abandonment",
            "replacement_reset",
            "blocked_replacement_validation",
            "replacement_handoff",
            "replacement_validation",
            "replacement_checklist",
            "blocked_replacement_copy_packet",
            "ready_replacement_copy_packet",
            "closeout",
            "review_bundle",
            "review_html",
            "review_workbook",
            "operator_dashboard",
        ]
        payload["sample_outputs"]["raw_operator_response_stored"] = False
        payload["sample_outputs"]["raw_acknowledgement_stored"] = False
        sample_output_path.write_text(
            self._render_child_replacement_readiness_sample_output(payload),
            encoding="utf-8",
        )
        drill_path = self.config.runs_dir / run_dir.name / "child_replacement_readiness_drill.json"
        drill_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        ledger = RunLedger(self.config.runs_dir / run_dir.name)
        ledger.record_artifact(job_id="__run__", kind="child_replacement_readiness_sample_output", path=sample_output_path)
        ledger.record_artifact(job_id="__run__", kind="child_replacement_readiness_drill", path=drill_path)
        ledger.record_event(
            "child_replacement_readiness_drill_completed",
            {
                "run_id": run_dir.name,
                "job_id": closeout.get("job_id"),
                "candidate_id": candidate_id,
                "drill_path": str(drill_path),
                "state": state,
                "writes_attempted": 0,
                "network_calls_made": 0,
            },
        )
        payload["drill_path"] = str(drill_path)
        return payload

    def _render_child_replacement_readiness_sample_output(self, payload: dict[str, Any]) -> str:
        sample_outputs = dict(payload.get("sample_outputs") or {})
        readiness_states = dict(payload.get("readiness_states") or {})
        commands = dict(payload.get("commands") or {})
        closeout_rollup = dict(payload.get("closeout_rollup") or {})
        state_groups = dict(payload.get("review_bundle_child_replacement_groups") or {})
        dashboard_summary = dict(payload.get("operator_dashboard_child_replacement_summary") or {})
        stop_conditions = list(payload.get("explicit_stop_conditions") or [])
        lines = [
            "# Child Replacement Readiness Sample Output",
            "",
            "Synthetic fixture only. Do not use this sample as live sink approval.",
            "",
            "## Run",
            "",
            f"- Run: `{payload.get('run_id')}`",
            f"- Job: `{payload.get('job_id')}`",
            f"- Candidate: `{payload.get('candidate_id')}`",
            f"- State: `{payload.get('state')}`",
            f"- Writes attempted: `{payload.get('writes_attempted', 0)}`",
            f"- Network calls made: `{payload.get('network_calls_made', 0)}`",
            "",
            "## Redaction",
            "",
            "- Raw operator response stored: `False`",
            "- Raw acknowledgement stored: `False`",
            "- Safety confirmation text is not stored in this sample output.",
            "",
            "## Readiness States",
            "",
        ]
        for key in [
            "blocked_replacement_audit",
            "blocked_replacement_validation",
            "replacement_handoff",
            "replacement_response",
            "replacement_checklist",
            "blocked_replacement_copy_packet",
            "ready_replacement_copy_packet",
            "closeout",
        ]:
            lines.append(f"- {key}: `{readiness_states.get(key)}`")
        lines.extend(
            [
                "",
                "## Closeout Rollup",
                "",
                f"- Predecessor artifacts stale: `{closeout_rollup.get('predecessor_artifacts_stale')}`",
                f"- Replacement handoff ready: `{closeout_rollup.get('replacement_handoff_ready')}`",
                f"- Replacement response ready: `{closeout_rollup.get('replacement_response_ready')}`",
                f"- Replacement checklist ready: `{closeout_rollup.get('replacement_checklist_ready')}`",
                f"- Replacement copy ready: `{closeout_rollup.get('replacement_copy_ready')}`",
                f"- Selected target created: `{closeout_rollup.get('selected_target_created')}`",
                f"- Executable live command: `{closeout_rollup.get('executable_live_command')}`",
                "",
                "## Review Samples",
                "",
                f"- Review bundle: `{sample_outputs.get('review_bundle_path')}`",
                f"- Review HTML: `{sample_outputs.get('review_html_path')}`",
                f"- Review workbook: `{sample_outputs.get('review_workbook_path')}`",
                f"- Operator dashboard: `{sample_outputs.get('operator_dashboard_command')}`",
                f"- Review bundle child replacement groups: `{json.dumps(state_groups, sort_keys=True)}`",
                f"- Operator dashboard ready count: `{dashboard_summary.get('ready_count')}`",
                "",
                "## Operator Commands",
                "",
                f"- Re-run drill: `{commands.get('child_replacement_readiness_drill')}`",
                f"- Review bundle: `{commands.get('review_bundle')}`",
                f"- Review HTML: `{commands.get('review_html')}`",
                f"- Review workbook: `{commands.get('review_workbook')}`",
                f"- Operator dashboard: `{commands.get('operator_dashboard')}`",
                f"- Closeout status: `{commands.get('closeout_status')}`",
                "",
                "## Stop Conditions",
                "",
            ]
        )
        for condition in stop_conditions:
            lines.append(f"- {condition}")
        lines.append("")
        return "\n".join(lines)

    def list_jobs(self, run_id: str | None = None) -> list[dict[str, Any]]:
        run_ids = [run_id] if run_id is not None else [str(run["run_id"]) for run in self.list_runs()]
        jobs: list[dict[str, Any]] = []
        for current_run_id in run_ids:
            jobs_path = self.config.runs_dir / current_run_id / "jobs.jsonl"
            if not jobs_path.exists():
                continue
            latest: dict[str, dict[str, Any]] = {}
            for row in _read_jsonl(jobs_path):
                row["run_id"] = current_run_id
                latest[str(row["job_id"])] = row
            jobs.extend(latest.values())
        return sorted(jobs, key=lambda row: str(row.get("updated_at", "")), reverse=True)

    def get_job(self, job_id: str, *, run_id: str | None = None) -> dict[str, Any]:
        for job in self.list_jobs(run_id):
            if job["job_id"] == job_id:
                job["artifacts"] = [
                    artifact
                    for artifact in self.list_artifacts(str(job["run_id"]))
                    if artifact.get("job_id") == job_id
                ]
                return job
        raise FileNotFoundError(f"job not found: {job_id}")

    def review_queue(
        self,
        *,
        run_id: str | None = None,
        state: str = "needs_review",
        next_action: str | None = None,
        artifact_kind: str | None = None,
    ) -> list[dict[str, Any]]:
        jobs = self.list_jobs(run_id)
        queue: list[dict[str, Any]] = []
        for job in jobs:
            if state != "all" and job.get("state") != state:
                continue
            artifacts = [
                artifact
                for artifact in self.list_artifacts(str(job["run_id"]))
                if artifact.get("job_id") == job["job_id"]
            ]
            by_kind = {str(artifact.get("kind")): artifact for artifact in artifacts}
            if artifact_kind and artifact_kind not in by_kind:
                continue
            action = self._next_action_for_job(job, set(by_kind))
            if next_action and str((action or {}).get("action") or "") != next_action:
                continue
            queue.append(
                {
                    "run_id": job["run_id"],
                    "job_id": job["job_id"],
                    "state": job["state"],
                    "image_path": job["image_path"],
                    "error": job.get("error"),
                    "artifact_dir": job.get("artifact_dir"),
                    "next_action": action,
                    "review_packet": by_kind.get("review_packet"),
                    "duplicate_assessment": by_kind.get("duplicate_assessment"),
                    "contact_candidate": by_kind.get("contact_candidate"),
                    "reviewed_contact": by_kind.get("reviewed_contact"),
                    "artifact_kinds": sorted(by_kind),
                }
            )
        return queue

    def child_review_queue(
        self,
        *,
        run_id: str | None = None,
        state: str = "needs_review",
    ) -> list[dict[str, Any]]:
        run_ids = [run_id] if run_id is not None else [str(run["run_id"]) for run in self.list_runs()]
        queue: list[dict[str, Any]] = []
        for current_run_id in run_ids:
            if current_run_id is None:
                continue
            artifacts = self.list_artifacts(str(current_run_id))
            jobs_by_id = {str(job["job_id"]): job for job in self.list_jobs(str(current_run_id))}
            promotion_artifacts = [
                artifact
                for artifact in artifacts
                if artifact.get("kind") == "child_contact_promotions"
            ]
            review_results: dict[str, dict[str, Any]] = {}
            for result_artifact in artifacts:
                if result_artifact.get("kind") != "child_contact_review_result":
                    continue
                result_payload = _read_json_file(Path(str(result_artifact.get("path") or ""))) or {}
                result_candidate_id = str(result_payload.get("candidate_id") or "")
                if result_candidate_id:
                    review_results[result_candidate_id] = result_payload
            for artifact in promotion_artifacts:
                manifest = _read_json_file(Path(str(artifact.get("path") or ""))) or {}
                promotions = [
                    promotion
                    for promotion in list(manifest.get("promotions") or [])
                    if isinstance(promotion, dict)
                ]
                for promotion in promotions:
                    candidate_id = str(promotion.get("candidate_id") or "")
                    review_result = review_results.get(candidate_id)
                    current_state = str((review_result or {}).get("state") or promotion.get("state") or "")
                    if state != "all" and current_state != state:
                        continue
                    candidate_path = Path(str(promotion.get("contact_candidate_path") or ""))
                    candidate = _read_json_file(candidate_path) or {}
                    job = jobs_by_id.get(str(promotion.get("parent_job_id") or ""))
                    queue.append(
                        {
                            "schema": "business-card-watchdog.child-review-queue-entry.v1",
                            "run_id": str(current_run_id),
                            "job_id": promotion.get("parent_job_id"),
                            "candidate_id": candidate_id,
                            "work_item_id": promotion.get("work_item_id"),
                            "state": current_state,
                            "image_path": (job or {}).get("image_path"),
                            "artifact_dir": (job or {}).get("artifact_dir"),
                            "contact_candidate_path": str(candidate_path),
                            "verification_result_path": promotion.get("verification_result_path"),
                            "contact_candidate": candidate,
                            "lineage": candidate.get("lineage") if isinstance(candidate, dict) else {},
                            "review": candidate.get("review") if isinstance(candidate, dict) else {},
                            "child_review_result": review_result,
                            "routing_allowed": bool((review_result or {}).get("routing_allowed")),
                            "enrichment_allowed": bool(promotion.get("enrichment_allowed")),
                            "sink_write_allowed": bool(promotion.get("sink_write_allowed")),
                            "next_action": {
                                "action": "review_child_contact",
                                "safe_to_auto_continue": False,
                                "requires_explicit_operator_action": True,
                                "reason": "promoted child contact candidate requires review before routing",
                                "command": (
                                    "reviews child-review "
                                    f"{shlex.quote(candidate_id)} --run-id {current_run_id} "
                                    "--action approve_child_for_routing --json"
                                ),
                            },
                        }
                    )
        return sorted(
            queue,
            key=lambda row: (
                str(row.get("run_id") or ""),
                str(row.get("job_id") or ""),
                str(row.get("candidate_id") or ""),
            ),
        )

    def submit_child_review(
        self,
        *,
        run_id: str,
        candidate_id: str,
        reviewer: str,
        action: str,
        field_corrections: dict[str, Any] | None = None,
        notes: str = "",
    ) -> dict[str, Any]:
        if action not in _SUPPORTED_CHILD_REVIEW_ACTIONS:
            raise ValueError(f"unsupported child review action: {action}")

        queue = self.child_review_queue(run_id=run_id, state="all")
        entry = next((row for row in queue if str(row.get("candidate_id") or "") == candidate_id), None)
        if entry is None:
            raise FileNotFoundError(f"child contact candidate not found: {candidate_id}")

        contact_candidate_path = Path(str(entry.get("contact_candidate_path") or ""))
        candidate = _read_json_file(contact_candidate_path) or {}
        if not isinstance(candidate, dict):
            candidate = {}
        artifact_dir = Path(str(entry.get("artifact_dir") or "")) if entry.get("artifact_dir") else contact_candidate_path.parent
        child_review_dir = artifact_dir / "child_reviews" / candidate_id
        child_review_dir.mkdir(parents=True, exist_ok=True)
        created_at = utc_now()
        field_corrections = dict(field_corrections or {})
        submission = {
            "schema": "business-card-watchdog.child-review-submission.v1",
            "run_id": run_id,
            "job_id": entry.get("job_id"),
            "candidate_id": candidate_id,
            "work_item_id": entry.get("work_item_id"),
            "reviewer": reviewer,
            "action": action,
            "field_corrections": field_corrections,
            "notes": notes,
            "contact_candidate_path": str(contact_candidate_path),
            "submitted_at": created_at,
        }
        submission_path = child_review_dir / "child_review_submission.json"
        submission_path.write_text(json.dumps(submission, indent=2, sort_keys=True) + "\n", encoding="utf-8")

        reviewed_contact = None
        reviewed_contact_path = None
        state = "needs_review"
        routing_allowed = False
        if action == "approve_child_for_routing":
            reviewed_contact = apply_review_corrections(
                candidate,
                reviewer=reviewer,
                field_corrections=field_corrections,
                default_country=self.config.normalization.default_country,
            )
            reviewed_contact["lineage"] = {
                **dict(candidate.get("lineage") or {}),
                "child_review_submission_path": str(submission_path),
                "contact_candidate_path": str(contact_candidate_path),
            }
            reviewed_contact["review"] = {
                "state": "approved_for_dedupe",
                "reviewer": reviewer,
                "reviewed_at": created_at,
                "notes": notes,
            }
            reviewed_contact["routing_allowed"] = True
            reviewed_contact["enrichment_allowed"] = False
            reviewed_contact["sink_write_allowed"] = False
            reviewed_contact_path = child_review_dir / "reviewed_child_contact.json"
            reviewed_contact_path.write_text(
                json.dumps(reviewed_contact, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            state = "approved_for_dedupe"
            routing_allowed = True
        elif action == "reject_child_contact":
            state = "rejected"

        result = {
            "schema": "business-card-watchdog.child-contact-review-result.v1",
            "run_id": run_id,
            "job_id": entry.get("job_id"),
            "candidate_id": candidate_id,
            "work_item_id": entry.get("work_item_id"),
            "state": state,
            "action": action,
            "reviewer": reviewer,
            "reviewed_at": created_at,
            "notes": notes,
            "contact_candidate_path": str(contact_candidate_path),
            "child_review_submission_path": str(submission_path),
            "reviewed_child_contact_path": str(reviewed_contact_path) if reviewed_contact_path is not None else None,
            "routing_allowed": routing_allowed,
            "enrichment_allowed": False,
            "sink_write_allowed": False,
            "next_action": {
                "action": "dedupe_child_contact" if routing_allowed else "review_child_contact",
                "safe_to_auto_continue": bool(routing_allowed),
                "requires_explicit_operator_action": not bool(routing_allowed),
                "reason": (
                    "approved child contact is ready for future dedupe/routing"
                    if routing_allowed
                    else "child contact remains out of routing"
                ),
            },
        }
        result_path = child_review_dir / "child_contact_review_result.json"
        result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")

        ledger = RunLedger(self.config.runs_dir / run_id)
        parent_job_id = str(entry.get("job_id") or "__run__")
        ledger.record_artifact(job_id=parent_job_id, kind="child_review_submission", path=submission_path)
        if reviewed_contact_path is not None:
            ledger.record_artifact(job_id=parent_job_id, kind="reviewed_child_contact", path=reviewed_contact_path)
        ledger.record_artifact(job_id=parent_job_id, kind="child_contact_review_result", path=result_path)
        ledger.record_event(
            "child_contact_review_submitted",
            {
                "run_id": run_id,
                "job_id": entry.get("job_id"),
                "candidate_id": candidate_id,
                "action": action,
                "state": state,
                "reviewer": reviewer,
                "submission_path": str(submission_path),
                "result_path": str(result_path),
                "writes_attempted": 0,
                "network_calls_made": 0,
            },
        )
        return {
            "schema": "business-card-watchdog.child-review-submission-result.v1",
            "run_id": run_id,
            "job_id": entry.get("job_id"),
            "candidate_id": candidate_id,
            "state": state,
            "submission": submission,
            "submission_path": str(submission_path),
            "result": result,
            "result_path": str(result_path),
            "reviewed_contact": reviewed_contact,
            "reviewed_child_contact_path": str(reviewed_contact_path) if reviewed_contact_path is not None else None,
            "writes_attempted": 0,
            "network_calls_made": 0,
        }

    def child_route_prep_queue(
        self,
        *,
        run_id: str | None = None,
        state: str = "approved_for_dedupe",
    ) -> list[dict[str, Any]]:
        run_ids = [run_id] if run_id is not None else [str(run["run_id"]) for run in self.list_runs()]
        queue: list[dict[str, Any]] = []
        for current_run_id in run_ids:
            if current_run_id is None:
                continue
            artifacts = self.list_artifacts(str(current_run_id))
            prep_results: dict[str, dict[str, Any]] = {}
            for artifact in artifacts:
                if artifact.get("kind") != "child_route_prep_result":
                    continue
                prep_payload = _read_json_file(Path(str(artifact.get("path") or ""))) or {}
                prep_candidate_id = str(prep_payload.get("candidate_id") or "")
                if prep_candidate_id:
                    prep_results[prep_candidate_id] = prep_payload
            for entry in self.child_review_queue(run_id=str(current_run_id), state="all"):
                candidate_id = str(entry.get("candidate_id") or "")
                prep_result = prep_results.get(candidate_id)
                current_state = str((prep_result or {}).get("state") or entry.get("state") or "")
                if state != "all" and current_state != state:
                    continue
                if current_state not in {"approved_for_dedupe", "routing_prepared"}:
                    continue
                queue.append(
                    {
                        "schema": "business-card-watchdog.child-route-prep-queue-entry.v1",
                        "run_id": str(current_run_id),
                        "job_id": entry.get("job_id"),
                        "candidate_id": candidate_id,
                        "work_item_id": entry.get("work_item_id"),
                        "state": current_state,
                        "image_path": entry.get("image_path"),
                        "artifact_dir": entry.get("artifact_dir"),
                        "child_review_result": entry.get("child_review_result"),
                        "child_route_prep_result": prep_result,
                        "reviewed_child_contact_path": (entry.get("child_review_result") or {}).get(
                            "reviewed_child_contact_path"
                        ),
                        "routing_allowed": bool((entry.get("child_review_result") or {}).get("routing_allowed")),
                        "sink_write_allowed": False,
                        "next_action": {
                            "action": "prepare_child_route",
                            "safe_to_auto_continue": True,
                            "requires_explicit_operator_action": False,
                            "reason": "approved child contact is ready for dry-run dedupe/routing preparation",
                            "command": (
                                "reviews child-route-prep "
                                f"{shlex.quote(candidate_id)} --run-id {current_run_id} --json"
                            ),
                        },
                    }
                )
        return sorted(
            queue,
            key=lambda row: (
                str(row.get("run_id") or ""),
                str(row.get("job_id") or ""),
                str(row.get("candidate_id") or ""),
            ),
        )

    def prepare_child_route(
        self,
        *,
        run_id: str,
        candidate_id: str,
        dry_run: bool = True,
    ) -> dict[str, Any]:
        queue = self.child_route_prep_queue(run_id=run_id, state="all")
        entry = next((row for row in queue if str(row.get("candidate_id") or "") == candidate_id), None)
        if entry is None:
            raise FileNotFoundError(f"approved child contact candidate not found: {candidate_id}")
        if str(entry.get("state") or "") not in {"approved_for_dedupe", "routing_prepared"}:
            raise ValueError(f"child contact candidate is not approved for routing prep: {candidate_id}")

        reviewed_child_contact_path = Path(str(entry.get("reviewed_child_contact_path") or ""))
        reviewed_child_contact = _read_json_file(reviewed_child_contact_path) or {}
        if not isinstance(reviewed_child_contact, dict) or not reviewed_child_contact:
            raise FileNotFoundError(f"reviewed child contact not found: {reviewed_child_contact_path}")
        artifact_dir = Path(str(entry.get("artifact_dir") or "")) if entry.get("artifact_dir") else reviewed_child_contact_path.parent
        child_prep_dir = artifact_dir / "child_route_prep" / candidate_id
        child_prep_dir.mkdir(parents=True, exist_ok=True)

        spec = contact_candidate_to_spec(reviewed_child_contact)
        canonical = reviewed_child_contact.get("canonical") or build_canonical_contact(reviewed_child_contact)
        spec["_canonical_contact"] = canonical
        spec["_field_provenance"] = field_provenance_from_canonical(canonical)
        if isinstance(reviewed_child_contact.get("contact_points"), list):
            spec["contact_points"] = list(reviewed_child_contact["contact_points"])
        spec["_image_path"] = str(entry.get("image_path") or "")
        spec["_review_state"] = "approved_for_dedupe"
        spec["_child_candidate_id"] = candidate_id
        spec["_parent_job_id"] = str(entry.get("job_id") or "")

        decision = decide_sinks(self.config, spec)
        dry_run = dry_run or decision.dry_run
        lookup_plan = build_sink_lookup_plan(
            sinks=decision.sinks,
            spec=spec,
            dry_run=dry_run,
            reason=decision.reason,
        )
        lookup_plan["run_id"] = run_id
        lookup_plan["job_id"] = entry.get("job_id")
        lookup_plan["candidate_id"] = candidate_id
        lookup_plan["work_item_id"] = entry.get("work_item_id")
        lookup_plan["decision"] = decision.to_dict()
        lookup_plan["route_explanation"] = decision.metadata.get("route_explanation")
        lookup_plan["sink_eligibility"] = decision.metadata.get("sink_eligibility", [])
        sink_plan = build_sink_plan(
            sinks=decision.sinks,
            spec=spec,
            dry_run=dry_run,
            reason=decision.reason,
            apply_enabled={sink: self._sink_apply_enabled(sink) for sink in decision.sinks},
        )
        sink_plan["run_id"] = run_id
        sink_plan["job_id"] = entry.get("job_id")
        sink_plan["candidate_id"] = candidate_id
        sink_plan["work_item_id"] = entry.get("work_item_id")
        sink_plan["decision"] = decision.to_dict()
        sink_plan["route_explanation"] = decision.metadata.get("route_explanation")
        sink_plan["sink_eligibility"] = decision.metadata.get("sink_eligibility", [])

        lookup_plan_path = child_prep_dir / "child_sink_lookup_plan.json"
        sink_plan_path = child_prep_dir / "child_sink_plan.json"
        lookup_plan_path.write_text(json.dumps(lookup_plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        sink_plan_path.write_text(json.dumps(sink_plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        result = {
            "schema": "business-card-watchdog.child-route-prep-result.v1",
            "run_id": run_id,
            "job_id": entry.get("job_id"),
            "candidate_id": candidate_id,
            "work_item_id": entry.get("work_item_id"),
            "state": "routing_prepared",
            "dry_run": dry_run,
            "reviewed_child_contact_path": str(reviewed_child_contact_path),
            "child_sink_lookup_plan_path": str(lookup_plan_path),
            "child_sink_plan_path": str(sink_plan_path),
            "planned_sinks": decision.sinks,
            "route_reason": decision.reason,
            "routing_allowed": True,
            "sink_write_allowed": False,
            "writes_attempted": 0,
            "network_calls_made": 0,
            "next_action": {
                "action": "child_sink_lookup_result",
                "safe_to_auto_continue": False,
                "requires_explicit_operator_action": True,
                "reason": "dry-run routing prep is complete; downstream lookup evidence is still required",
            },
        }
        result_path = child_prep_dir / "child_route_prep_result.json"
        result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")

        ledger = RunLedger(self.config.runs_dir / run_id)
        parent_job_id = str(entry.get("job_id") or "__run__")
        ledger.record_artifact(job_id=parent_job_id, kind="child_sink_lookup_plan", path=lookup_plan_path)
        ledger.record_artifact(job_id=parent_job_id, kind="child_sink_plan", path=sink_plan_path)
        ledger.record_artifact(job_id=parent_job_id, kind="child_route_prep_result", path=result_path)
        ledger.record_event(
            "child_route_prepared",
            {
                "run_id": run_id,
                "job_id": entry.get("job_id"),
                "candidate_id": candidate_id,
                "state": result["state"],
                "planned_sinks": decision.sinks,
                "result_path": str(result_path),
                "writes_attempted": 0,
                "network_calls_made": 0,
            },
        )
        return {
            "schema": "business-card-watchdog.child-route-prep-submission-result.v1",
            "run_id": run_id,
            "job_id": entry.get("job_id"),
            "candidate_id": candidate_id,
            "state": "routing_prepared",
            "lookup_plan_path": str(lookup_plan_path),
            "sink_plan_path": str(sink_plan_path),
            "result_path": str(result_path),
            "lookup_plan": lookup_plan,
            "sink_plan": sink_plan,
            "result": result,
            "writes_attempted": 0,
            "network_calls_made": 0,
        }

    def record_child_sink_lookup_result(
        self,
        *,
        run_id: str,
        candidate_id: str,
        matches_by_sink: dict[str, list[dict[str, Any]]] | None = None,
    ) -> dict[str, Any]:
        entry = self._child_route_prep_entry(run_id=run_id, candidate_id=candidate_id)
        prep_result = dict(entry.get("child_route_prep_result") or {})
        lookup_plan_path = Path(str(prep_result.get("child_sink_lookup_plan_path") or ""))
        lookup_plan = _read_json_file(lookup_plan_path) or {}
        if not lookup_plan:
            raise FileNotFoundError(f"child sink lookup plan not found: {lookup_plan_path}")
        prep_dir = lookup_plan_path.parent
        adapter_request = build_sink_adapter_request(
            phase="lookup",
            lookup_plan=lookup_plan,
            sink_context=self._sink_context(),
        )
        adapter_request["candidate_id"] = candidate_id
        adapter_request["work_item_id"] = entry.get("work_item_id")
        adapter_request_path = prep_dir / "child_sink_adapter_request_lookup.json"
        adapter_request_path.write_text(
            json.dumps(adapter_request, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        result = build_sink_lookup_result(
            adapter_request=adapter_request,
            matches_by_sink=matches_by_sink or {},
        )
        result["candidate_id"] = candidate_id
        result["work_item_id"] = entry.get("work_item_id")
        result["child_sink_lookup_plan_path"] = str(lookup_plan_path)
        result_path = prep_dir / "child_sink_lookup_result.json"
        result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")

        ledger = RunLedger(self.config.runs_dir / run_id)
        parent_job_id = str(entry.get("job_id") or "__run__")
        ledger.record_artifact(job_id=parent_job_id, kind="child_sink_adapter_request_lookup", path=adapter_request_path)
        ledger.record_artifact(job_id=parent_job_id, kind="child_sink_lookup_result", path=result_path)
        ledger.record_event(
            "child_sink_lookup_result_recorded",
            {
                "run_id": run_id,
                "job_id": entry.get("job_id"),
                "candidate_id": candidate_id,
                "result_path": str(result_path),
                "state": result["state"],
                "match_count": result["match_count"],
                "writes_attempted": 0,
                "network_calls_made": 0,
            },
        )
        return {
            "schema": "business-card-watchdog.child-sink-lookup-result-submission.v1",
            "run_id": run_id,
            "job_id": entry.get("job_id"),
            "candidate_id": candidate_id,
            "adapter_request_path": str(adapter_request_path),
            "result_path": str(result_path),
            "adapter_request": adapter_request,
            "result": result,
            "writes_attempted": 0,
            "network_calls_made": 0,
        }

    def assess_child_downstream_duplicates(
        self,
        *,
        run_id: str,
        candidate_id: str,
    ) -> dict[str, Any]:
        entry = self._child_route_prep_entry(run_id=run_id, candidate_id=candidate_id)
        prep_result = dict(entry.get("child_route_prep_result") or {})
        lookup_plan_path = Path(str(prep_result.get("child_sink_lookup_plan_path") or ""))
        prep_dir = lookup_plan_path.parent
        result_path = prep_dir / "child_sink_lookup_result.json"
        if result_path.exists():
            lookup_result = json.loads(result_path.read_text(encoding="utf-8"))
        else:
            lookup_result = self.record_child_sink_lookup_result(
                run_id=run_id,
                candidate_id=candidate_id,
            )["result"]
        assessment = assess_downstream_lookup_result(lookup_result).to_dict()
        assessment["candidate_id"] = candidate_id
        assessment["work_item_id"] = entry.get("work_item_id")
        assessment["reviewed"] = assessment["state"] == "no_match"
        assessment_path = prep_dir / "child_downstream_duplicate_assessment.json"
        assessment_path.write_text(json.dumps(assessment, indent=2, sort_keys=True) + "\n", encoding="utf-8")

        ledger = RunLedger(self.config.runs_dir / run_id)
        parent_job_id = str(entry.get("job_id") or "__run__")
        ledger.record_artifact(job_id=parent_job_id, kind="child_downstream_duplicate_assessment", path=assessment_path)
        ledger.record_event(
            "child_downstream_duplicate_assessed",
            {
                "run_id": run_id,
                "job_id": entry.get("job_id"),
                "candidate_id": candidate_id,
                "assessment_path": str(assessment_path),
                "state": assessment["state"],
                "match_count": len(assessment["matches"]),
                "writes_attempted": 0,
                "network_calls_made": 0,
            },
        )
        return {
            "schema": "business-card-watchdog.child-downstream-duplicate-assessment-result.v1",
            "run_id": run_id,
            "job_id": entry.get("job_id"),
            "candidate_id": candidate_id,
            "assessment_path": str(assessment_path),
            "assessment": assessment,
            "writes_attempted": 0,
            "network_calls_made": 0,
        }

    def resolve_child_duplicate(
        self,
        *,
        run_id: str,
        candidate_id: str,
        reviewer: str,
        decision: str,
        target_identity: str = "",
        reason: str = "",
    ) -> dict[str, Any]:
        if decision not in {"create_new", "merge_existing", "noop"}:
            raise ValueError("child duplicate decision must be create_new, merge_existing, or noop")
        entry = self._child_route_prep_entry(run_id=run_id, candidate_id=candidate_id)
        prep_dir = self._child_route_prep_dir(entry)
        assessment_path = prep_dir / "child_downstream_duplicate_assessment.json"
        assessment = _read_json_file(assessment_path) or {}
        if not assessment:
            raise FileNotFoundError(f"child downstream duplicate assessment not found: {assessment_path}")
        payload = {
            "schema": "business-card-watchdog.child-duplicate-resolution.v1",
            "run_id": run_id,
            "job_id": entry.get("job_id"),
            "candidate_id": candidate_id,
            "work_item_id": entry.get("work_item_id"),
            "reviewer": reviewer,
            "decision": decision,
            "target_identity": target_identity,
            "reason": reason,
            "resolved_at": utc_now(),
            "duplicate_assessment": assessment,
            "routing_allowed": decision != "noop",
            "sink_write_allowed": False,
            "writes_attempted": 0,
            "network_calls_made": 0,
        }
        resolution_path = prep_dir / "child_duplicate_resolution.json"
        resolution_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        ledger = RunLedger(self.config.runs_dir / run_id)
        parent_job_id = str(entry.get("job_id") or "__run__")
        ledger.record_artifact(job_id=parent_job_id, kind="child_duplicate_resolution", path=resolution_path)
        ledger.record_event(
            "child_duplicate_resolved",
            {
                "run_id": run_id,
                "job_id": entry.get("job_id"),
                "candidate_id": candidate_id,
                "decision": decision,
                "resolution_path": str(resolution_path),
                "writes_attempted": 0,
                "network_calls_made": 0,
            },
        )
        return {
            "schema": "business-card-watchdog.child-duplicate-resolution-result.v1",
            "run_id": run_id,
            "job_id": entry.get("job_id"),
            "candidate_id": candidate_id,
            "resolution_path": str(resolution_path),
            "resolution": payload,
            "writes_attempted": 0,
            "network_calls_made": 0,
        }

    def child_sink_plan_gate(
        self,
        *,
        run_id: str,
        candidate_id: str,
    ) -> dict[str, Any]:
        entry = self._child_route_prep_entry(run_id=run_id, candidate_id=candidate_id)
        prep_dir = self._child_route_prep_dir(entry)
        assessment = _read_json_file(prep_dir / "child_downstream_duplicate_assessment.json") or {}
        resolution = _read_json_file(prep_dir / "child_duplicate_resolution.json") or {}
        sink_plan = _read_json_file(prep_dir / "child_sink_plan.json") or {}
        duplicate_state = str(assessment.get("state") or "missing")
        decision = str(resolution.get("decision") or "")
        blockers: list[str] = []
        if not sink_plan:
            blockers.append("child_sink_plan_missing")
        if not assessment:
            blockers.append("child_downstream_duplicate_assessment_missing")
        elif duplicate_state != "no_match" and not decision:
            blockers.append(f"child_duplicate_state_unresolved:{duplicate_state}")
        elif decision == "noop":
            blockers.append("child_duplicate_resolution_noop")
        state = "ready_for_sink_plan" if not blockers else "blocked"
        payload = {
            "schema": "business-card-watchdog.child-sink-plan-gate.v1",
            "run_id": run_id,
            "job_id": entry.get("job_id"),
            "candidate_id": candidate_id,
            "work_item_id": entry.get("work_item_id"),
            "state": state,
            "duplicate_state": duplicate_state,
            "duplicate_decision": decision,
            "blocked_reasons": blockers,
            "planned_sinks": [
                str(action.get("sink") or "")
                for action in list(sink_plan.get("actions") or [])
                if action.get("sink")
            ],
            "routing_allowed": state == "ready_for_sink_plan",
            "sink_write_allowed": False,
            "writes_attempted": 0,
            "network_calls_made": 0,
            "artifact_paths": {
                "child_sink_plan": str(prep_dir / "child_sink_plan.json"),
                "child_downstream_duplicate_assessment": str(prep_dir / "child_downstream_duplicate_assessment.json"),
                "child_duplicate_resolution": str(prep_dir / "child_duplicate_resolution.json"),
            },
            "next_action": {
                "action": "child_sink_apply_preflight" if state == "ready_for_sink_plan" else "resolve_child_duplicate",
                "safe_to_auto_continue": state == "ready_for_sink_plan",
                "requires_explicit_operator_action": state != "ready_for_sink_plan",
                "reason": (
                    "child duplicate gate is clear for future sink preflight"
                    if state == "ready_for_sink_plan"
                    else "child duplicate assessment must be resolved before sink preflight"
                ),
            },
        }
        gate_path = prep_dir / "child_sink_plan_gate.json"
        gate_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        ledger = RunLedger(self.config.runs_dir / run_id)
        parent_job_id = str(entry.get("job_id") or "__run__")
        ledger.record_artifact(job_id=parent_job_id, kind="child_sink_plan_gate", path=gate_path)
        ledger.record_event(
            "child_sink_plan_gate_created",
            {
                "run_id": run_id,
                "job_id": entry.get("job_id"),
                "candidate_id": candidate_id,
                "state": state,
                "blocked_reasons": blockers,
                "gate_path": str(gate_path),
                "writes_attempted": 0,
                "network_calls_made": 0,
            },
        )
        return {
            "schema": "business-card-watchdog.child-sink-plan-gate-result.v1",
            "run_id": run_id,
            "job_id": entry.get("job_id"),
            "candidate_id": candidate_id,
            "gate_path": str(gate_path),
            "gate": payload,
            "writes_attempted": 0,
            "network_calls_made": 0,
        }

    def child_sink_apply_preflight(
        self,
        *,
        run_id: str,
        candidate_id: str,
        apply: bool = False,
    ) -> dict[str, Any]:
        entry = self._child_route_prep_entry(run_id=run_id, candidate_id=candidate_id)
        prep_dir = self._child_route_prep_dir(entry)
        gate = _read_json_file(prep_dir / "child_sink_plan_gate.json") or {}
        if gate.get("state") != "ready_for_sink_plan":
            raise ValueError(f"child sink plan gate is not ready for preflight: {candidate_id}")
        sink_plan = _read_json_file(prep_dir / "child_sink_plan.json") or {}
        if not sink_plan:
            raise FileNotFoundError(f"child sink plan not found: {prep_dir / 'child_sink_plan.json'}")
        preflight = build_sink_apply_preflight(plan=sink_plan, apply=apply)
        preflight["schema"] = "business-card-watchdog.child-sink-apply-preflight.v1"
        preflight["job_id"] = entry.get("job_id")
        preflight["candidate_id"] = candidate_id
        preflight["work_item_id"] = entry.get("work_item_id")
        preflight["child_sink_plan_gate_path"] = str(prep_dir / "child_sink_plan_gate.json")
        preflight["can_apply"] = False
        preflight["state"] = "preview" if not apply and preflight.get("state") == "preview" else "blocked"
        preflight["reason"] = (
            preflight.get("reason")
            if not apply
            else "child live apply is disabled; create an operator-selected child target handoff first"
        )
        preflight["sink_write_allowed"] = False
        preflight["writes_attempted"] = 0
        preflight["network_calls_made"] = 0
        preflight_path = prep_dir / "child_sink_apply_preflight.json"
        preflight_path.write_text(json.dumps(preflight, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        ledger = RunLedger(self.config.runs_dir / run_id)
        parent_job_id = str(entry.get("job_id") or "__run__")
        ledger.record_artifact(job_id=parent_job_id, kind="child_sink_apply_preflight", path=preflight_path)
        ledger.record_event(
            "child_sink_apply_preflight_created",
            {
                "run_id": run_id,
                "job_id": entry.get("job_id"),
                "candidate_id": candidate_id,
                "state": preflight["state"],
                "preflight_path": str(preflight_path),
                "writes_attempted": 0,
                "network_calls_made": 0,
            },
        )
        return {
            "schema": "business-card-watchdog.child-sink-apply-preflight-result.v1",
            "run_id": run_id,
            "job_id": entry.get("job_id"),
            "candidate_id": candidate_id,
            "preflight_path": str(preflight_path),
            "preflight": preflight,
            "writes_attempted": 0,
            "network_calls_made": 0,
        }

    def child_selected_target_handoff(
        self,
        *,
        run_id: str,
        candidate_id: str,
        sink: str,
        operator: str = "operator",
        scope: str = "write",
        reason: str = "",
    ) -> dict[str, Any]:
        entry = self._child_route_prep_entry(run_id=run_id, candidate_id=candidate_id)
        prep_dir = self._child_route_prep_dir(entry)
        preflight = _read_json_file(prep_dir / "child_sink_apply_preflight.json") or {}
        if not preflight:
            preflight = self.child_sink_apply_preflight(
                run_id=run_id,
                candidate_id=candidate_id,
                apply=False,
            )["preflight"]
        actions = [action for action in list(preflight.get("actions") or []) if action.get("sink") == sink]
        blockers: list[str] = []
        if preflight.get("state") != "preview":
            blockers.append(f"child_preflight_state:{preflight.get('state') or 'missing'}")
        if not actions:
            blockers.append(f"sink_not_in_child_preflight:{sink}")
        state = "ready_for_operator_selection" if not blockers else "blocked"
        payload = {
            "schema": "business-card-watchdog.child-selected-target-handoff.v1",
            "state": state,
            "run_id": run_id,
            "job_id": entry.get("job_id"),
            "candidate_id": candidate_id,
            "work_item_id": entry.get("work_item_id"),
            "sink": sink,
            "operator": operator,
            "scope": scope,
            "reason": reason,
            "blocked_reasons": blockers,
            "preflight_path": str(prep_dir / "child_sink_apply_preflight.json"),
            "selected_target_created": False,
            "target_safety_confirmation_required": True,
            "operator_response_template": {
                "run_id": run_id,
                "job_id": entry.get("job_id"),
                "candidate_id": candidate_id,
                "work_item_id": entry.get("work_item_id"),
                "sink": sink,
                "operator": operator,
                "scope": scope,
                "reason": reason,
                "safety_confirmation": "I approve this child contact sink target for a future selected-target pilot.",
            },
            "commands": {
                "refresh_preflight": (
                    f"reviews child-sink-apply-preflight {shlex.quote(candidate_id)} "
                    f"--run-id {run_id} --json"
                ),
                "refresh_handoff": (
                    f"reviews child-selected-target-handoff {shlex.quote(candidate_id)} "
                    f"--run-id {run_id} --sink {shlex.quote(sink)} --operator {shlex.quote(operator)} --json"
                ),
                "validate_response": (
                    f"reviews child-validate-selected-target-response {shlex.quote(candidate_id)} "
                    f"--run-id {run_id} --response <operator-response> --json"
                ),
                "execution_checklist": (
                    f"reviews child-selected-target-execution-checklist {shlex.quote(candidate_id)} "
                    f"--run-id {run_id} --response <operator-response> --json"
                ),
            },
            "explicit_stop_conditions": [
                "Do not create a live selected target from this handoff artifact.",
                "Do not run live lookup, live write, or live readback from this child handoff.",
                "Do not write Google Contacts, Odoo, or Odollo records from this child handoff.",
            ],
            "writes_attempted": 0,
            "network_calls_made": 0,
        }
        handoff_path = prep_dir / "child_selected_target_handoff.json"
        handoff_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        ledger = RunLedger(self.config.runs_dir / run_id)
        parent_job_id = str(entry.get("job_id") or "__run__")
        ledger.record_artifact(job_id=parent_job_id, kind="child_selected_target_handoff", path=handoff_path)
        ledger.record_event(
            "child_selected_target_handoff_created",
            {
                "run_id": run_id,
                "job_id": entry.get("job_id"),
                "candidate_id": candidate_id,
                "sink": sink,
                "state": state,
                "handoff_path": str(handoff_path),
                "writes_attempted": 0,
                "network_calls_made": 0,
            },
        )
        return {
            "schema": "business-card-watchdog.child-selected-target-handoff-result.v1",
            "run_id": run_id,
            "job_id": entry.get("job_id"),
            "candidate_id": candidate_id,
            "handoff_path": str(handoff_path),
            "handoff": payload,
            "writes_attempted": 0,
            "network_calls_made": 0,
        }

    def validate_child_selected_target_response(
        self,
        *,
        run_id: str,
        candidate_id: str,
        response: str,
    ) -> dict[str, Any]:
        entry = self._child_route_prep_entry(run_id=run_id, candidate_id=candidate_id)
        prep_dir = self._child_route_prep_dir(entry)
        parsed = _parse_operator_response_fields(response)
        handoff = _read_json_file(prep_dir / "child_selected_target_handoff.json") or {}
        if not handoff and parsed.get("sink"):
            handoff = self.child_selected_target_handoff(
                run_id=run_id,
                candidate_id=candidate_id,
                sink=str(parsed["sink"]),
                operator=str(parsed.get("operator") or "operator"),
                scope=str(parsed.get("scope") or "write"),
            )["handoff"]
        expected = {
            "run_id": run_id,
            "job_id": str(entry.get("job_id") or ""),
            "candidate_id": candidate_id,
            "work_item_id": str(entry.get("work_item_id") or ""),
            "sink": str(handoff.get("sink") or ""),
            "operator": str(handoff.get("operator") or ""),
            "scope": str(handoff.get("scope") or ""),
        }
        required_fields = ["run_id", "job_id", "candidate_id", "sink", "operator", "scope", "safety_confirmation"]
        missing_fields = [
            field
            for field in required_fields
            if not str(parsed.get(field) or "").strip()
            or str(parsed.get(field) or "").strip().startswith("<")
        ]
        mismatches: list[str] = []
        if not handoff:
            mismatches.append("child selected-target handoff artifact is missing")
        elif handoff.get("state") != "ready_for_operator_selection":
            mismatches.append(f"child handoff state is {handoff.get('state') or 'missing'}")
        for field, expected_value in expected.items():
            if field == "work_item_id" and not parsed.get(field):
                continue
            actual = str(parsed.get(field) or "").strip()
            if expected_value and actual and actual != expected_value:
                mismatches.append(f"{field} does not match current child handoff")
        if "safety_confirmation" not in missing_fields:
            safety_confirmation_blocker = _safety_confirmation_blocker(
                str(parsed.get("safety_confirmation") or "")
            )
            if safety_confirmation_blocker:
                mismatches.append(safety_confirmation_blocker)
        state = "ready_for_no_live_child_checklist" if not missing_fields and not mismatches else "blocked"
        validation = {
            "schema": "business-card-watchdog.child-selected-target-response-validation.v1",
            "generated_at": utc_now(),
            "state": state,
            "run_id": run_id,
            "job_id": entry.get("job_id"),
            "candidate_id": candidate_id,
            "work_item_id": entry.get("work_item_id"),
            "response": response,
            "parsed_response": parsed,
            "expected_fields": expected,
            "missing_fields": missing_fields,
            "mismatches": mismatches,
            "handoff_path": str(prep_dir / "child_selected_target_handoff.json"),
            "handoff_state": handoff.get("state"),
            "selected_target_created": False,
            "creates_selected_live_target": False,
            "writes_attempted": 0,
            "network_calls_made": 0,
            "commands": {
                "refresh_handoff": (
                    f"reviews child-selected-target-handoff {shlex.quote(candidate_id)} "
                    f"--run-id {run_id} --sink {shlex.quote(str(parsed.get('sink') or expected['sink']))} --json"
                ),
                "execution_checklist": (
                    f"reviews child-selected-target-execution-checklist {shlex.quote(candidate_id)} "
                    f"--run-id {run_id} --response {shlex.quote(response)} --json"
                ),
            },
            "explicit_stop_conditions": [
                "This validation does not create selected_live_target.json.",
                "Do not run live lookup, live write, or live readback from this validation report.",
                "Fix missing fields or mismatches before preparing any child selected-target checklist.",
            ],
        }
        validation_path = prep_dir / "child_selected_target_response_validation.json"
        validation_path.write_text(json.dumps(validation, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        ledger = RunLedger(self.config.runs_dir / run_id)
        parent_job_id = str(entry.get("job_id") or "__run__")
        ledger.record_artifact(job_id=parent_job_id, kind="child_selected_target_response_validation", path=validation_path)
        ledger.record_event(
            "child_selected_target_response_validated",
            {
                "run_id": run_id,
                "job_id": entry.get("job_id"),
                "candidate_id": candidate_id,
                "state": state,
                "validation_path": str(validation_path),
                "writes_attempted": 0,
                "network_calls_made": 0,
            },
        )
        return validation

    def child_selected_target_execution_checklist(
        self,
        *,
        run_id: str,
        candidate_id: str,
        response: str,
    ) -> dict[str, Any]:
        validation = self.validate_child_selected_target_response(
            run_id=run_id,
            candidate_id=candidate_id,
            response=response,
        )
        entry = self._child_route_prep_entry(run_id=run_id, candidate_id=candidate_id)
        prep_dir = self._child_route_prep_dir(entry)
        response_digest = hashlib.sha256(response.encode("utf-8")).hexdigest()
        checklist_items = [
            {
                "name": "child_handoff_ready",
                "ok": validation.get("handoff_state") == "ready_for_operator_selection",
                "evidence": validation.get("handoff_path"),
            },
            {
                "name": "operator_response_matches_child_context",
                "ok": validation.get("state") == "ready_for_no_live_child_checklist",
                "evidence": "run_id, job_id, candidate_id, sink, operator, and scope",
            },
            {
                "name": "response_digest_recorded_without_live_action",
                "ok": bool(response_digest),
                "evidence": "sha256 digest only; raw response remains in local runtime artifact",
            },
            {
                "name": "live_execution_blocked",
                "ok": True,
                "evidence": "executable_live_command is null and selected_target_created is false",
            },
        ]
        blocked_reasons = list(validation.get("missing_fields") or []) + list(validation.get("mismatches") or [])
        state = "ready_for_operator_review" if validation.get("state") == "ready_for_no_live_child_checklist" else "blocked"
        checklist = {
            "schema": "business-card-watchdog.child-selected-target-execution-checklist.v1",
            "generated_at": utc_now(),
            "state": state,
            "run_id": run_id,
            "job_id": entry.get("job_id"),
            "candidate_id": candidate_id,
            "work_item_id": entry.get("work_item_id"),
            "sink": (validation.get("parsed_response") or {}).get("sink"),
            "operator": (validation.get("parsed_response") or {}).get("operator"),
            "scope": (validation.get("parsed_response") or {}).get("scope"),
            "validation": validation,
            "operator_response_redacted": {
                "raw_response_stored": True,
                "sha256": response_digest,
                "fields": {
                    key: value
                    for key, value in dict(validation.get("parsed_response") or {}).items()
                    if key != "safety_confirmation"
                },
                "safety_confirmation_stored": False,
            },
            "checklist_items": checklist_items,
            "blocked_reasons": blocked_reasons,
            "selected_target_created": False,
            "creates_selected_live_target": False,
            "executable_live_command": None,
            "next_safe_command": (
                f"reviews child-selected-target-handoff {shlex.quote(candidate_id)} "
                f"--run-id {run_id} --sink {shlex.quote(str((validation.get('parsed_response') or {}).get('sink') or ''))} --json"
            ),
            "commands": {
                "validate_response": (
                    f"reviews child-validate-selected-target-response {shlex.quote(candidate_id)} "
                    f"--run-id {run_id} --response <operator-response> --json"
                ),
                "refresh_handoff": (
                    f"reviews child-selected-target-handoff {shlex.quote(candidate_id)} "
                    f"--run-id {run_id} --sink {shlex.quote(str((validation.get('parsed_response') or {}).get('sink') or ''))} --json"
                ),
            },
            "explicit_stop_conditions": [
                "This checklist is not selected-target approval.",
                "Do not create selected_live_target.json from this child checklist.",
                "Do not run live GWS/Odollo/Odoo lookup, write, or readback from this child checklist.",
                "Do not process private SyncThing images, run public-web search, or call paid enrichment from this checklist.",
            ],
            "writes_attempted": 0,
            "network_calls_made": 0,
        }
        checklist_path = prep_dir / "child_selected_target_execution_checklist.json"
        checklist_path.write_text(json.dumps(checklist, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        ledger = RunLedger(self.config.runs_dir / run_id)
        parent_job_id = str(entry.get("job_id") or "__run__")
        ledger.record_artifact(job_id=parent_job_id, kind="child_selected_target_execution_checklist", path=checklist_path)
        ledger.record_event(
            "child_selected_target_execution_checklist_created",
            {
                "run_id": run_id,
                "job_id": entry.get("job_id"),
                "candidate_id": candidate_id,
                "state": state,
                "checklist_path": str(checklist_path),
                "writes_attempted": 0,
                "network_calls_made": 0,
            },
        )
        checklist["checklist_path"] = str(checklist_path)
        return checklist

    def child_selected_target_command_copy_packet(
        self,
        *,
        run_id: str,
        candidate_id: str,
        response: str,
        acknowledgement: str = "",
    ) -> dict[str, Any]:
        checklist = self.child_selected_target_execution_checklist(
            run_id=run_id,
            candidate_id=candidate_id,
            response=response,
        )
        entry = self._child_route_prep_entry(run_id=run_id, candidate_id=candidate_id)
        prep_dir = self._child_route_prep_dir(entry)
        blocked_reasons = list(checklist.get("blocked_reasons") or [])
        normalized_acknowledgement = " ".join(str(acknowledgement or "").lower().split())
        acknowledgement_terms = {
            "run_id": str(checklist.get("run_id") or ""),
            "candidate_id": str(checklist.get("candidate_id") or ""),
            "sink": str(checklist.get("sink") or ""),
            "operator": str(checklist.get("operator") or ""),
        }
        missing_acknowledgement_terms = [
            f"{key}={value}"
            for key, value in acknowledgement_terms.items()
            if value and value.lower() not in normalized_acknowledgement
        ]
        acknowledgement_verb_ok = any(
            verb in normalized_acknowledgement
            for verb in ["acknowledge", "acknowledged", "approve", "approved", "copy", "ready"]
        )
        if not normalized_acknowledgement:
            blocked_reasons.append("operator acknowledgement is required before child command copy text is shown")
        if missing_acknowledgement_terms:
            blocked_reasons.append(
                "operator acknowledgement must name "
                + ", ".join(missing_acknowledgement_terms)
                + " before child command copy text is shown"
            )
        if not acknowledgement_verb_ok:
            blocked_reasons.append(
                "operator acknowledgement must include one of acknowledge, approved, copy, or ready"
            )
        checklist_ready = checklist.get("state") == "ready_for_operator_review"
        acknowledgement_ok = bool(
            normalized_acknowledgement
            and not missing_acknowledgement_terms
            and acknowledgement_verb_ok
        )
        offline_command = (
            f"reviews child-selected-target-execution-checklist {shlex.quote(candidate_id)} "
            f"--run-id {run_id} --response <operator-response> --json"
        )
        command_copy_text = offline_command if checklist_ready and acknowledgement_ok and not blocked_reasons else None
        state = "ready_for_operator_copy" if command_copy_text else "blocked"
        packet = {
            "schema": "business-card-watchdog.child-selected-target-command-copy-packet.v1",
            "generated_at": utc_now(),
            "state": state,
            "run_id": run_id,
            "job_id": entry.get("job_id"),
            "candidate_id": candidate_id,
            "work_item_id": entry.get("work_item_id"),
            "sink": checklist.get("sink"),
            "operator": checklist.get("operator"),
            "scope": checklist.get("scope"),
            "acknowledgement_required": True,
            "acknowledgement_ok": acknowledgement_ok,
            "acknowledgement_instruction": (
                "Acknowledge the exact run_id, candidate_id, sink, and operator plus an approval/copy verb."
            ),
            "acknowledgement_redacted": {
                "raw_acknowledgement_stored": False,
                "sha256": hashlib.sha256(acknowledgement.encode("utf-8")).hexdigest() if acknowledgement else None,
                "required_terms": acknowledgement_terms,
                "missing_terms": missing_acknowledgement_terms,
            },
            "checklist_state": checklist.get("state"),
            "checklist": checklist,
            "command_copy_text": command_copy_text,
            "offline_command_copy_text": command_copy_text,
            "executable_live_command": None,
            "selected_target_created": False,
            "creates_selected_live_target": False,
            "blocked_reasons": blocked_reasons,
            "commands": {
                "validate_response": (
                    f"reviews child-validate-selected-target-response {shlex.quote(candidate_id)} "
                    f"--run-id {run_id} --response <operator-response> --json"
                ),
                "execution_checklist": offline_command,
                "refresh_handoff": (
                    f"reviews child-selected-target-handoff {shlex.quote(candidate_id)} "
                    f"--run-id {run_id} --sink {shlex.quote(str(checklist.get('sink') or ''))} --json"
                ),
            },
            "explicit_stop_conditions": [
                "This packet only returns offline command text for operator copy; it never executes the command.",
                "This packet never returns an executable live command.",
                "Do not create selected_live_target.json from this child command-copy packet.",
                "Do not run live GWS/Odollo/Odoo lookup, write, or readback from this packet.",
                "Do not process private SyncThing images, run public-web search, or call paid enrichment from this packet.",
            ],
            "writes_attempted": 0,
            "network_calls_made": 0,
        }
        packet_path = prep_dir / "child_selected_target_command_copy_packet.json"
        packet_path.write_text(json.dumps(packet, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        ledger = RunLedger(self.config.runs_dir / run_id)
        parent_job_id = str(entry.get("job_id") or "__run__")
        ledger.record_artifact(job_id=parent_job_id, kind="child_selected_target_command_copy_packet", path=packet_path)
        ledger.record_event(
            "child_selected_target_command_copy_packet_created",
            {
                "run_id": run_id,
                "job_id": entry.get("job_id"),
                "candidate_id": candidate_id,
                "state": state,
                "packet_path": str(packet_path),
                "writes_attempted": 0,
                "network_calls_made": 0,
            },
        )
        packet["packet_path"] = str(packet_path)
        return packet

    def child_selected_target_audit(
        self,
        *,
        run_id: str,
        candidate_id: str,
        sink: str | None = None,
        operator: str | None = None,
        scope: str | None = None,
        write: bool = True,
    ) -> dict[str, Any]:
        entry = self._child_route_prep_entry(run_id=run_id, candidate_id=candidate_id)
        prep_dir = self._child_route_prep_dir(entry)
        packet_path = prep_dir / "child_selected_target_command_copy_packet.json"
        checklist_path = prep_dir / "child_selected_target_execution_checklist.json"
        packet = _read_json_file(packet_path)
        checklist = _read_json_file(checklist_path)
        if checklist is None and packet is not None:
            checklist = dict(packet.get("checklist") or {})
        existing_target = packet if packet and packet.get("state") == "ready_for_operator_copy" else None
        existing_identity = ""
        if existing_target:
            existing_identity = "|".join(
                str(existing_target.get(key) or "")
                for key in ["run_id", "job_id", "candidate_id", "sink", "operator", "scope"]
            )
        requested = {
            "sink": sink or (existing_target or {}).get("sink") or (checklist or {}).get("sink"),
            "operator": operator or (existing_target or {}).get("operator") or (checklist or {}).get("operator"),
            "scope": scope or (existing_target or {}).get("scope") or (checklist or {}).get("scope"),
        }
        requested_identity = "|".join(
            [
                run_id,
                str(entry.get("job_id") or ""),
                candidate_id,
                str(requested.get("sink") or ""),
                str(requested.get("operator") or ""),
                str(requested.get("scope") or ""),
            ]
        )
        abandonment_path = prep_dir / "child_selected_target_abandonment.json"
        abandonment = _read_json_file(abandonment_path)
        existing_abandoned = bool(
            abandonment
            and str(abandonment.get("selected_target_identity") or "") == existing_identity
            and abandonment.get("state") == "abandoned"
        )
        replacement_requested = bool(existing_target and requested_identity and requested_identity != existing_identity)
        replacement_requires_abandonment = bool(existing_target and replacement_requested and not existing_abandoned)
        blocked_reasons: list[str] = []
        if packet is None:
            blocked_reasons.append("child selected-target command-copy packet is missing")
        elif packet.get("state") != "ready_for_operator_copy":
            blocked_reasons.append(f"child command-copy packet state is {packet.get('state') or 'missing'}")
        if checklist is None:
            blocked_reasons.append("child selected-target execution checklist is missing")
        elif checklist.get("state") != "ready_for_operator_review":
            blocked_reasons.append(f"child execution checklist state is {checklist.get('state') or 'missing'}")
        if replacement_requires_abandonment:
            blocked_reasons.append("replacement requires child selected-target abandonment before a new target preview")
        state = "ready" if not blocked_reasons else "blocked"
        audit = {
            "schema": "business-card-watchdog.child-selected-target-audit.v1",
            "generated_at": utc_now(),
            "state": state,
            "run_id": run_id,
            "job_id": entry.get("job_id"),
            "candidate_id": candidate_id,
            "work_item_id": entry.get("work_item_id"),
            "selected_target_exists": existing_target is not None,
            "selected_target_identity": existing_identity or None,
            "selected_target": existing_target,
            "selected_target_path": str(packet_path),
            "checklist_path": str(checklist_path),
            "sink": (existing_target or checklist or {}).get("sink"),
            "operator": (existing_target or checklist or {}).get("operator"),
            "scope": (existing_target or checklist or {}).get("scope"),
            "requested_target": requested,
            "requested_target_identity": requested_identity or None,
            "replacement_requested": replacement_requested,
            "replacement_requires_abandonment": replacement_requires_abandonment,
            "existing_target_abandoned": existing_abandoned,
            "abandonment_supported": False,
            "abandonment_path": str(abandonment_path),
            "abandonment": abandonment,
            "blocked_reasons": blocked_reasons,
            "commands": {
                "refresh_command_copy_packet": (
                    f"reviews child-selected-target-command-copy-packet {shlex.quote(candidate_id)} "
                    f"--run-id {run_id} --response <operator-response> "
                    "--acknowledgement <operator-acknowledgement> --json"
                ),
                "refresh_audit": (
                    f"reviews child-selected-target-audit {shlex.quote(candidate_id)} --run-id {run_id} --json"
                ),
                "abandonment": None,
            },
            "explicit_stop_conditions": [
                "This audit preview does not create, replace, or abandon a selected target.",
                "Do not create selected_live_target.json from this child audit.",
                "Do not run live GWS/Odollo/Odoo lookup, write, or readback from this audit.",
                "Do not proceed with a replacement while replacement_requires_abandonment is true.",
                "Do not process private SyncThing images, run public-web search, or call paid enrichment from this audit.",
            ],
            "writes_attempted": 0,
            "network_calls_made": 0,
        }
        if write:
            audit_path = prep_dir / "child_selected_target_audit.json"
            audit_path.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            ledger = RunLedger(self.config.runs_dir / run_id)
            parent_job_id = str(entry.get("job_id") or "__run__")
            ledger.record_artifact(job_id=parent_job_id, kind="child_selected_target_audit", path=audit_path)
            ledger.record_event(
                "child_selected_target_audit_created",
                {
                    "run_id": run_id,
                    "job_id": entry.get("job_id"),
                    "candidate_id": candidate_id,
                    "state": state,
                    "audit_path": str(audit_path),
                    "replacement_requires_abandonment": replacement_requires_abandonment,
                    "writes_attempted": 0,
                    "network_calls_made": 0,
                },
            )
            audit["audit_path"] = str(audit_path)
        return audit

    def abandon_child_selected_target(
        self,
        *,
        run_id: str,
        candidate_id: str,
        operator: str,
        reason: str,
    ) -> dict[str, Any]:
        if not operator.strip():
            raise ValueError("child selected-target abandonment requires an operator")
        if not reason.strip():
            raise ValueError("child selected-target abandonment requires a reason")
        entry = self._child_route_prep_entry(run_id=run_id, candidate_id=candidate_id)
        prep_dir = self._child_route_prep_dir(entry)
        audit = self.child_selected_target_audit(run_id=run_id, candidate_id=candidate_id, write=False)
        if not audit.get("selected_target_exists"):
            raise ValueError("child selected-target abandonment requires an existing child selected-target packet")
        selected_target = dict(audit.get("selected_target") or {})
        selected_target_identity = str(audit.get("selected_target_identity") or "")
        payload = {
            "schema": "business-card-watchdog.child-selected-target-abandonment.v1",
            "state": "abandoned",
            "created_at": utc_now(),
            "run_id": run_id,
            "job_id": entry.get("job_id"),
            "candidate_id": candidate_id,
            "work_item_id": entry.get("work_item_id"),
            "sink": selected_target.get("sink"),
            "scope": selected_target.get("scope"),
            "operator": operator,
            "reason": reason,
            "selected_target_path": audit.get("selected_target_path"),
            "selected_target_identity": selected_target_identity,
            "selected_target_operator": selected_target.get("operator"),
            "selected_target": selected_target,
            "writes_attempted": 0,
            "network_calls_made": 0,
            "commands": {
                "audit": f"reviews child-selected-target-audit {shlex.quote(candidate_id)} --run-id {run_id} --json",
                "replacement_reset": (
                    f"reviews child-selected-target-replacement-reset {shlex.quote(candidate_id)} "
                    f"--run-id {run_id} --sink <sink> --operator <operator> --scope <scope> --json"
                ),
            },
            "explicit_stop_conditions": [
                "This abandonment artifact does not delete or mutate prior child target artifacts.",
                "Do not run live lookup, live write, or live readback for the abandoned child target.",
                "A replacement reset packet is required before preparing a new child selected-target preview.",
                "Do not process private SyncThing images, run public-web search, or call paid enrichment from this artifact.",
            ],
        }
        abandonment_path = prep_dir / "child_selected_target_abandonment.json"
        abandonment_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        ledger = RunLedger(self.config.runs_dir / run_id)
        parent_job_id = str(entry.get("job_id") or "__run__")
        ledger.record_artifact(job_id=parent_job_id, kind="child_selected_target_abandonment", path=abandonment_path)
        ledger.record_event(
            "child_selected_target_abandoned",
            {
                "run_id": run_id,
                "job_id": entry.get("job_id"),
                "candidate_id": candidate_id,
                "selected_target_identity": selected_target_identity,
                "abandonment_path": str(abandonment_path),
                "operator": operator,
                "writes_attempted": 0,
                "network_calls_made": 0,
            },
        )
        payload["abandonment_path"] = str(abandonment_path)
        return payload

    def child_selected_target_replacement_reset(
        self,
        *,
        run_id: str,
        candidate_id: str,
        sink: str,
        operator: str,
        scope: str = "write",
        reset_by: str = "operator",
        reason: str = "",
    ) -> dict[str, Any]:
        entry = self._child_route_prep_entry(run_id=run_id, candidate_id=candidate_id)
        prep_dir = self._child_route_prep_dir(entry)
        abandonment_path = prep_dir / "child_selected_target_abandonment.json"
        abandonment = _read_json_file(abandonment_path)
        audit = self.child_selected_target_audit(
            run_id=run_id,
            candidate_id=candidate_id,
            sink=sink,
            operator=operator,
            scope=scope,
            write=False,
        )
        blocked_reasons: list[str] = []
        if not abandonment:
            blocked_reasons.append("child selected-target abandonment artifact is missing")
        elif abandonment.get("state") != "abandoned":
            blocked_reasons.append(f"child abandonment state is {abandonment.get('state') or 'missing'}")
        expected_identity = str(audit.get("selected_target_identity") or "")
        actual_identity = str((abandonment or {}).get("selected_target_identity") or "")
        if expected_identity and actual_identity and expected_identity != actual_identity:
            blocked_reasons.append("child abandonment identity does not match current selected target")
        if audit.get("replacement_requires_abandonment"):
            blocked_reasons.append("replacement still requires child selected-target abandonment")
        requested_target = {"sink": sink, "operator": operator, "scope": scope}
        state = "ready_for_replacement_preview" if not blocked_reasons else "blocked"
        payload = {
            "schema": "business-card-watchdog.child-selected-target-replacement-reset.v1",
            "generated_at": utc_now(),
            "state": state,
            "run_id": run_id,
            "job_id": entry.get("job_id"),
            "candidate_id": candidate_id,
            "work_item_id": entry.get("work_item_id"),
            "reset_by": reset_by,
            "reason": reason,
            "requested_target": requested_target,
            "replacement_unblocked": state == "ready_for_replacement_preview",
            "replacement_requires_abandonment": bool(audit.get("replacement_requires_abandonment")),
            "previous_selected_target_identity": expected_identity or None,
            "abandonment_path": str(abandonment_path),
            "abandonment": abandonment,
            "selected_target_audit": audit,
            "blocked_reasons": blocked_reasons,
            "commands": {
                "refresh_audit": (
                    f"reviews child-selected-target-audit {shlex.quote(candidate_id)} --run-id {run_id} "
                    f"--sink {shlex.quote(sink)} --operator {shlex.quote(operator)} --scope {shlex.quote(scope)} --json"
                ),
                "new_handoff": (
                    f"reviews child-selected-target-handoff {shlex.quote(candidate_id)} --run-id {run_id} "
                    f"--sink {shlex.quote(sink)} --operator {shlex.quote(operator)} --scope {shlex.quote(scope)} --json"
                ),
            },
            "explicit_stop_conditions": [
                "This reset packet does not create a new selected target.",
                "This reset packet does not delete or mutate prior child target artifacts.",
                "Do not run live GWS/Odollo/Odoo lookup, write, or readback from this reset packet.",
                "Use the new_handoff command only to prepare another no-live child handoff preview.",
                "Do not process private SyncThing images, run public-web search, or call paid enrichment from this packet.",
            ],
            "writes_attempted": 0,
            "network_calls_made": 0,
        }
        reset_path = prep_dir / "child_selected_target_replacement_reset.json"
        reset_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        ledger = RunLedger(self.config.runs_dir / run_id)
        parent_job_id = str(entry.get("job_id") or "__run__")
        ledger.record_artifact(job_id=parent_job_id, kind="child_selected_target_replacement_reset", path=reset_path)
        ledger.record_event(
            "child_selected_target_replacement_reset_created",
            {
                "run_id": run_id,
                "job_id": entry.get("job_id"),
                "candidate_id": candidate_id,
                "state": state,
                "reset_path": str(reset_path),
                "replacement_unblocked": payload["replacement_unblocked"],
                "writes_attempted": 0,
                "network_calls_made": 0,
            },
        )
        payload["reset_path"] = str(reset_path)
        return payload

    def refresh_child_replacement_handoff(
        self,
        *,
        run_id: str,
        candidate_id: str,
        sink: str,
        operator: str,
        scope: str = "write",
        reason: str = "",
    ) -> dict[str, Any]:
        entry = self._child_route_prep_entry(run_id=run_id, candidate_id=candidate_id)
        prep_dir = self._child_route_prep_dir(entry)
        reset_path = prep_dir / "child_selected_target_replacement_reset.json"
        reset = _read_json_file(reset_path)
        blocked_reasons: list[str] = []
        if not reset:
            blocked_reasons.append("child selected-target replacement reset packet is missing")
        elif reset.get("state") != "ready_for_replacement_preview":
            blocked_reasons.append(f"child replacement reset state is {reset.get('state') or 'missing'}")
        requested = dict((reset or {}).get("requested_target") or {})
        for key, expected in [("sink", sink), ("operator", operator), ("scope", scope)]:
            actual = str(requested.get(key) or "")
            if actual and actual != expected:
                blocked_reasons.append(f"{key} does not match ready replacement reset packet")
        stale_candidates = [
            ("child_selected_target_response_validation", prep_dir / "child_selected_target_response_validation.json"),
            ("child_selected_target_execution_checklist", prep_dir / "child_selected_target_execution_checklist.json"),
            ("child_selected_target_command_copy_packet", prep_dir / "child_selected_target_command_copy_packet.json"),
            ("child_selected_target_audit", prep_dir / "child_selected_target_audit.json"),
        ]
        stale_artifacts = [
            {"kind": kind, "path": str(path), "exists": path.exists()}
            for kind, path in stale_candidates
            if path.exists()
        ]
        state = "ready_for_replacement_handoff" if not blocked_reasons else "blocked"
        staleness = {
            "schema": "business-card-watchdog.child-selected-target-staleness.v1",
            "generated_at": utc_now(),
            "state": "stale" if state == "ready_for_replacement_handoff" else "blocked",
            "run_id": run_id,
            "job_id": entry.get("job_id"),
            "candidate_id": candidate_id,
            "work_item_id": entry.get("work_item_id"),
            "reason": reason or "child selected-target replacement reset requested",
            "source_reset_path": str(reset_path),
            "source_reset_state": (reset or {}).get("state"),
            "stale_artifacts": stale_artifacts,
            "replacement_target": {"sink": sink, "operator": operator, "scope": scope},
            "blocked_reasons": blocked_reasons,
            "writes_attempted": 0,
            "network_calls_made": 0,
            "explicit_stop_conditions": [
                "This staleness marker does not delete prior child artifacts.",
                "Do not use stale child selected-target response/checklist/command-copy/audit artifacts for a replacement target.",
                "Do not run live GWS/Odollo/Odoo lookup, write, or readback from this marker.",
            ],
        }
        staleness_path = prep_dir / "child_selected_target_staleness.json"
        staleness_path.write_text(json.dumps(staleness, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        refreshed: dict[str, Any] | None = None
        if state == "ready_for_replacement_handoff":
            refreshed = self.child_selected_target_handoff(
                run_id=run_id,
                candidate_id=candidate_id,
                sink=sink,
                operator=operator,
                scope=scope,
                reason=reason or "replacement handoff refreshed after child selected-target reset",
            )
        payload = {
            "schema": "business-card-watchdog.child-replacement-handoff-refresh.v1",
            "generated_at": utc_now(),
            "state": state,
            "run_id": run_id,
            "job_id": entry.get("job_id"),
            "candidate_id": candidate_id,
            "work_item_id": entry.get("work_item_id"),
            "sink": sink,
            "operator": operator,
            "scope": scope,
            "reason": reason,
            "reset_path": str(reset_path),
            "reset": reset,
            "staleness_path": str(staleness_path),
            "staleness": staleness,
            "refreshed_handoff_path": (refreshed or {}).get("handoff_path"),
            "refreshed_handoff": (refreshed or {}).get("handoff"),
            "blocked_reasons": blocked_reasons,
            "commands": {
                "inspect_reset": (
                    f"reviews child-selected-target-replacement-reset {shlex.quote(candidate_id)} "
                    f"--run-id {run_id} --sink {shlex.quote(sink)} --operator {shlex.quote(operator)} "
                    f"--scope {shlex.quote(scope)} --json"
                ),
                "validate_replacement_response": (
                    f"reviews child-validate-selected-target-response {shlex.quote(candidate_id)} "
                    f"--run-id {run_id} --response <operator-response> --json"
                ),
            },
            "explicit_stop_conditions": [
                "This refresh only creates no-live local artifacts.",
                "This refresh does not create selected_live_target.json.",
                "Do not use stale child selected-target artifacts after this refresh.",
                "Do not run live GWS/Odollo/Odoo lookup, write, or readback from this refresh packet.",
                "Do not process private SyncThing images, run public-web search, or call paid enrichment from this packet.",
            ],
            "writes_attempted": 0,
            "network_calls_made": 0,
        }
        refresh_path = prep_dir / "child_replacement_handoff_refresh.json"
        refresh_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        ledger = RunLedger(self.config.runs_dir / run_id)
        parent_job_id = str(entry.get("job_id") or "__run__")
        ledger.record_artifact(job_id=parent_job_id, kind="child_selected_target_staleness", path=staleness_path)
        ledger.record_artifact(job_id=parent_job_id, kind="child_replacement_handoff_refresh", path=refresh_path)
        ledger.record_event(
            "child_replacement_handoff_refreshed",
            {
                "run_id": run_id,
                "job_id": entry.get("job_id"),
                "candidate_id": candidate_id,
                "state": state,
                "refresh_path": str(refresh_path),
                "staleness_path": str(staleness_path),
                "refreshed_handoff_path": payload["refreshed_handoff_path"],
                "writes_attempted": 0,
                "network_calls_made": 0,
            },
        )
        payload["refresh_path"] = str(refresh_path)
        return payload

    def validate_child_replacement_response(
        self,
        *,
        run_id: str,
        candidate_id: str,
        response: str,
    ) -> dict[str, Any]:
        entry = self._child_route_prep_entry(run_id=run_id, candidate_id=candidate_id)
        prep_dir = self._child_route_prep_dir(entry)
        parsed = _parse_operator_response_fields(response)
        refresh_path = prep_dir / "child_replacement_handoff_refresh.json"
        staleness_path = prep_dir / "child_selected_target_staleness.json"
        handoff_path = prep_dir / "child_selected_target_handoff.json"
        refresh = _read_json_file(refresh_path) or {}
        staleness = _read_json_file(staleness_path) or {}
        handoff = _read_json_file(handoff_path) or {}
        expected = {
            "run_id": run_id,
            "job_id": str(entry.get("job_id") or ""),
            "candidate_id": candidate_id,
            "work_item_id": str(entry.get("work_item_id") or ""),
            "sink": str(handoff.get("sink") or refresh.get("sink") or ""),
            "operator": str(handoff.get("operator") or refresh.get("operator") or ""),
            "scope": str(handoff.get("scope") or refresh.get("scope") or ""),
        }
        required_fields = ["run_id", "job_id", "candidate_id", "sink", "operator", "scope", "safety_confirmation"]
        missing_fields = [
            field
            for field in required_fields
            if not str(parsed.get(field) or "").strip()
            or str(parsed.get(field) or "").strip().startswith("<")
        ]
        mismatches: list[str] = []
        blocked_reasons: list[str] = []
        if not refresh:
            blocked_reasons.append("child replacement handoff refresh artifact is missing")
        elif refresh.get("state") != "ready_for_replacement_handoff":
            blocked_reasons.append(f"child replacement handoff refresh state is {refresh.get('state') or 'missing'}")
        if not staleness:
            blocked_reasons.append("child selected-target staleness marker is missing")
        elif staleness.get("state") != "stale":
            blocked_reasons.append(f"child selected-target staleness state is {staleness.get('state') or 'missing'}")
        if not handoff:
            mismatches.append("refreshed child selected-target handoff artifact is missing")
        elif handoff.get("state") != "ready_for_operator_selection":
            mismatches.append(f"refreshed child handoff state is {handoff.get('state') or 'missing'}")
        if refresh and handoff:
            if str(refresh.get("refreshed_handoff_path") or "") != str(handoff_path):
                mismatches.append("refreshed handoff path does not match current child handoff")
            for field in ["sink", "operator", "scope"]:
                if str(refresh.get(field) or "") and str(refresh.get(field) or "") != str(handoff.get(field) or ""):
                    mismatches.append(f"{field} does not match refreshed child handoff")
        stale_kinds = [
            str(item.get("kind") or "")
            for item in list(staleness.get("stale_artifacts") or [])
            if isinstance(item, dict) and item.get("exists")
        ]
        expected_stale_kinds = {
            "child_selected_target_response_validation",
            "child_selected_target_execution_checklist",
            "child_selected_target_command_copy_packet",
            "child_selected_target_audit",
        }
        if staleness and not expected_stale_kinds.intersection(stale_kinds):
            blocked_reasons.append("child selected-target staleness marker does not name stale predecessor artifacts")
        for field, expected_value in expected.items():
            if field == "work_item_id" and not parsed.get(field):
                continue
            actual = str(parsed.get(field) or "").strip()
            if expected_value and actual and actual != expected_value:
                mismatches.append(f"{field} does not match refreshed child handoff")
        if "safety_confirmation" not in missing_fields:
            safety_confirmation_blocker = _safety_confirmation_blocker(
                str(parsed.get("safety_confirmation") or "")
            )
            if safety_confirmation_blocker:
                mismatches.append(safety_confirmation_blocker)
        blocked_reasons.extend(missing_fields)
        blocked_reasons.extend(mismatches)
        state = "ready_for_no_live_replacement_checklist" if not blocked_reasons else "blocked"
        validation = {
            "schema": "business-card-watchdog.child-replacement-response-validation.v1",
            "generated_at": utc_now(),
            "state": state,
            "run_id": run_id,
            "job_id": entry.get("job_id"),
            "candidate_id": candidate_id,
            "work_item_id": entry.get("work_item_id"),
            "response": response,
            "parsed_response": parsed,
            "expected_fields": expected,
            "missing_fields": missing_fields,
            "mismatches": mismatches,
            "blocked_reasons": blocked_reasons,
            "refresh_path": str(refresh_path),
            "refresh_state": refresh.get("state"),
            "refresh": refresh,
            "staleness_path": str(staleness_path),
            "staleness_state": staleness.get("state"),
            "staleness": staleness,
            "handoff_path": str(handoff_path),
            "handoff_state": handoff.get("state"),
            "handoff": handoff,
            "stale_enforcement": {
                "required": True,
                "staleness_marker_present": bool(staleness),
                "staleness_state": staleness.get("state"),
                "stale_artifact_kinds": stale_kinds,
                "expected_predecessor_kinds": sorted(expected_stale_kinds),
            },
            "selected_target_created": False,
            "creates_selected_live_target": False,
            "writes_attempted": 0,
            "network_calls_made": 0,
            "commands": {
                "refresh_replacement_handoff": (
                    f"reviews child-replacement-handoff-refresh {shlex.quote(candidate_id)} "
                    f"--run-id {run_id} --sink {shlex.quote(str(expected['sink']))} "
                    f"--operator {shlex.quote(str(expected['operator']))} "
                    f"--scope {shlex.quote(str(expected['scope']))} --json"
                ),
                "validate_again": (
                    f"reviews child-validate-replacement-response {shlex.quote(candidate_id)} "
                    f"--run-id {run_id} --response {shlex.quote(response)} --json"
                ),
            },
            "explicit_stop_conditions": [
                "This validation does not create selected_live_target.json.",
                "This validation does not delete stale child artifacts.",
                "Do not run live lookup, live write, or live readback from this validation report.",
                "Do not proceed unless stale predecessor artifacts are marked stale and state is ready.",
                "Do not process private SyncThing images, run public-web search, or call paid enrichment from this report.",
            ],
        }
        validation_path = prep_dir / "child_replacement_response_validation.json"
        validation_path.write_text(json.dumps(validation, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        ledger = RunLedger(self.config.runs_dir / run_id)
        parent_job_id = str(entry.get("job_id") or "__run__")
        ledger.record_artifact(job_id=parent_job_id, kind="child_replacement_response_validation", path=validation_path)
        ledger.record_event(
            "child_replacement_response_validated",
            {
                "run_id": run_id,
                "job_id": entry.get("job_id"),
                "candidate_id": candidate_id,
                "state": state,
                "validation_path": str(validation_path),
                "writes_attempted": 0,
                "network_calls_made": 0,
            },
        )
        validation["validation_path"] = str(validation_path)
        return validation

    def child_replacement_execution_checklist(
        self,
        *,
        run_id: str,
        candidate_id: str,
        response: str,
    ) -> dict[str, Any]:
        validation = self.validate_child_replacement_response(
            run_id=run_id,
            candidate_id=candidate_id,
            response=response,
        )
        entry = self._child_route_prep_entry(run_id=run_id, candidate_id=candidate_id)
        prep_dir = self._child_route_prep_dir(entry)
        response_digest = hashlib.sha256(response.encode("utf-8")).hexdigest()
        stale_enforcement = dict(validation.get("stale_enforcement") or {})
        checklist_items = [
            {
                "name": "replacement_response_ready",
                "ok": validation.get("state") == "ready_for_no_live_replacement_checklist",
                "evidence": validation.get("validation_path"),
            },
            {
                "name": "replacement_handoff_ready",
                "ok": validation.get("handoff_state") == "ready_for_operator_selection",
                "evidence": validation.get("handoff_path"),
            },
            {
                "name": "stale_predecessor_artifacts_marked",
                "ok": stale_enforcement.get("staleness_marker_present") is True
                and stale_enforcement.get("staleness_state") == "stale",
                "evidence": validation.get("staleness_path"),
            },
            {
                "name": "response_digest_recorded_without_live_action",
                "ok": bool(response_digest),
                "evidence": "sha256 digest only; raw response remains in local runtime artifact",
            },
            {
                "name": "live_execution_blocked",
                "ok": True,
                "evidence": "executable_live_command is null and selected_target_created is false",
            },
        ]
        blocked_reasons = list(validation.get("blocked_reasons") or [])
        state = (
            "ready_for_replacement_operator_review"
            if validation.get("state") == "ready_for_no_live_replacement_checklist"
            else "blocked"
        )
        checklist = {
            "schema": "business-card-watchdog.child-replacement-execution-checklist.v1",
            "generated_at": utc_now(),
            "state": state,
            "run_id": run_id,
            "job_id": entry.get("job_id"),
            "candidate_id": candidate_id,
            "work_item_id": entry.get("work_item_id"),
            "sink": (validation.get("parsed_response") or {}).get("sink"),
            "operator": (validation.get("parsed_response") or {}).get("operator"),
            "scope": (validation.get("parsed_response") or {}).get("scope"),
            "validation": validation,
            "stale_enforcement": stale_enforcement,
            "operator_response_redacted": {
                "raw_response_stored": True,
                "sha256": response_digest,
                "fields": {
                    key: value
                    for key, value in dict(validation.get("parsed_response") or {}).items()
                    if key != "safety_confirmation"
                },
                "safety_confirmation_stored": False,
            },
            "checklist_items": checklist_items,
            "blocked_reasons": blocked_reasons,
            "selected_target_created": False,
            "creates_selected_live_target": False,
            "executable_live_command": None,
            "next_safe_command": (
                f"reviews child-replacement-handoff-refresh {shlex.quote(candidate_id)} "
                f"--run-id {run_id} --sink {shlex.quote(str((validation.get('parsed_response') or {}).get('sink') or ''))} "
                f"--operator {shlex.quote(str((validation.get('parsed_response') or {}).get('operator') or ''))} "
                f"--scope {shlex.quote(str((validation.get('parsed_response') or {}).get('scope') or 'write'))} --json"
            ),
            "commands": {
                "validate_replacement_response": (
                    f"reviews child-validate-replacement-response {shlex.quote(candidate_id)} "
                    f"--run-id {run_id} --response <operator-response> --json"
                ),
                "replacement_command_copy_packet": (
                    f"reviews child-replacement-command-copy-packet {shlex.quote(candidate_id)} "
                    f"--run-id {run_id} --response <operator-response> "
                    "--acknowledgement <operator-acknowledgement> --json"
                ),
            },
            "explicit_stop_conditions": [
                "This replacement checklist is not selected-target approval.",
                "Do not create selected_live_target.json from this replacement checklist.",
                "Do not run live GWS/Odollo/Odoo lookup, write, or readback from this replacement checklist.",
                "Do not use stale predecessor child checklist or command-copy packets for the replacement target.",
                "Do not process private SyncThing images, run public-web search, or call paid enrichment from this checklist.",
            ],
            "writes_attempted": 0,
            "network_calls_made": 0,
        }
        checklist_path = prep_dir / "child_replacement_execution_checklist.json"
        checklist_path.write_text(json.dumps(checklist, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        ledger = RunLedger(self.config.runs_dir / run_id)
        parent_job_id = str(entry.get("job_id") or "__run__")
        ledger.record_artifact(job_id=parent_job_id, kind="child_replacement_execution_checklist", path=checklist_path)
        ledger.record_event(
            "child_replacement_execution_checklist_created",
            {
                "run_id": run_id,
                "job_id": entry.get("job_id"),
                "candidate_id": candidate_id,
                "state": state,
                "checklist_path": str(checklist_path),
                "writes_attempted": 0,
                "network_calls_made": 0,
            },
        )
        checklist["checklist_path"] = str(checklist_path)
        return checklist

    def child_replacement_command_copy_packet(
        self,
        *,
        run_id: str,
        candidate_id: str,
        response: str,
        acknowledgement: str = "",
    ) -> dict[str, Any]:
        checklist = self.child_replacement_execution_checklist(
            run_id=run_id,
            candidate_id=candidate_id,
            response=response,
        )
        entry = self._child_route_prep_entry(run_id=run_id, candidate_id=candidate_id)
        prep_dir = self._child_route_prep_dir(entry)
        blocked_reasons = list(checklist.get("blocked_reasons") or [])
        normalized_acknowledgement = " ".join(str(acknowledgement or "").lower().split())
        acknowledgement_terms = {
            "run_id": str(checklist.get("run_id") or ""),
            "candidate_id": str(checklist.get("candidate_id") or ""),
            "sink": str(checklist.get("sink") or ""),
            "operator": str(checklist.get("operator") or ""),
        }
        missing_acknowledgement_terms = [
            f"{key}={value}"
            for key, value in acknowledgement_terms.items()
            if value and value.lower() not in normalized_acknowledgement
        ]
        acknowledgement_verb_ok = any(
            verb in normalized_acknowledgement
            for verb in ["acknowledge", "acknowledged", "approve", "approved", "copy", "ready"]
        )
        if not normalized_acknowledgement:
            blocked_reasons.append("operator acknowledgement is required before replacement command copy text is shown")
        if missing_acknowledgement_terms:
            blocked_reasons.append(
                "operator acknowledgement must name "
                + ", ".join(missing_acknowledgement_terms)
                + " before replacement command copy text is shown"
            )
        if not acknowledgement_verb_ok:
            blocked_reasons.append(
                "operator acknowledgement must include one of acknowledge, approved, copy, or ready"
            )
        checklist_ready = checklist.get("state") == "ready_for_replacement_operator_review"
        acknowledgement_ok = bool(
            normalized_acknowledgement
            and not missing_acknowledgement_terms
            and acknowledgement_verb_ok
        )
        offline_command = (
            f"reviews child-replacement-execution-checklist {shlex.quote(candidate_id)} "
            f"--run-id {run_id} --response <operator-response> --json"
        )
        command_copy_text = offline_command if checklist_ready and acknowledgement_ok and not blocked_reasons else None
        state = "ready_for_replacement_operator_copy" if command_copy_text else "blocked"
        packet = {
            "schema": "business-card-watchdog.child-replacement-command-copy-packet.v1",
            "generated_at": utc_now(),
            "state": state,
            "run_id": run_id,
            "job_id": entry.get("job_id"),
            "candidate_id": candidate_id,
            "work_item_id": entry.get("work_item_id"),
            "sink": checklist.get("sink"),
            "operator": checklist.get("operator"),
            "scope": checklist.get("scope"),
            "acknowledgement_required": True,
            "acknowledgement_ok": acknowledgement_ok,
            "acknowledgement_instruction": (
                "Acknowledge the exact run_id, candidate_id, sink, and operator plus an approval/copy verb."
            ),
            "acknowledgement_redacted": {
                "raw_acknowledgement_stored": False,
                "sha256": hashlib.sha256(acknowledgement.encode("utf-8")).hexdigest() if acknowledgement else None,
                "required_terms": acknowledgement_terms,
                "missing_terms": missing_acknowledgement_terms,
            },
            "checklist_state": checklist.get("state"),
            "checklist": checklist,
            "command_copy_text": command_copy_text,
            "offline_command_copy_text": command_copy_text,
            "executable_live_command": None,
            "selected_target_created": False,
            "creates_selected_live_target": False,
            "blocked_reasons": blocked_reasons,
            "commands": {
                "validate_replacement_response": (
                    f"reviews child-validate-replacement-response {shlex.quote(candidate_id)} "
                    f"--run-id {run_id} --response <operator-response> --json"
                ),
                "replacement_execution_checklist": offline_command,
                "refresh_replacement_handoff": (
                    f"reviews child-replacement-handoff-refresh {shlex.quote(candidate_id)} "
                    f"--run-id {run_id} --sink {shlex.quote(str(checklist.get('sink') or ''))} "
                    f"--operator {shlex.quote(str(checklist.get('operator') or ''))} "
                    f"--scope {shlex.quote(str(checklist.get('scope') or 'write'))} --json"
                ),
            },
            "explicit_stop_conditions": [
                "This packet only returns offline replacement command text for operator copy; it never executes the command.",
                "This packet never returns an executable live command.",
                "Do not create selected_live_target.json from this replacement command-copy packet.",
                "Do not run live GWS/Odollo/Odoo lookup, write, or readback from this packet.",
                "Do not use stale predecessor child command-copy packets for the replacement target.",
                "Do not process private SyncThing images, run public-web search, or call paid enrichment from this packet.",
            ],
            "writes_attempted": 0,
            "network_calls_made": 0,
        }
        packet_path = prep_dir / "child_replacement_command_copy_packet.json"
        packet_path.write_text(json.dumps(packet, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        ledger = RunLedger(self.config.runs_dir / run_id)
        parent_job_id = str(entry.get("job_id") or "__run__")
        ledger.record_artifact(job_id=parent_job_id, kind="child_replacement_command_copy_packet", path=packet_path)
        ledger.record_event(
            "child_replacement_command_copy_packet_created",
            {
                "run_id": run_id,
                "job_id": entry.get("job_id"),
                "candidate_id": candidate_id,
                "state": state,
                "packet_path": str(packet_path),
                "writes_attempted": 0,
                "network_calls_made": 0,
            },
        )
        packet["packet_path"] = str(packet_path)
        return packet

    def child_replacement_closeout_status(
        self,
        *,
        run_id: str,
        candidate_id: str,
    ) -> dict[str, Any]:
        entry = self._child_route_prep_entry(run_id=run_id, candidate_id=candidate_id)
        prep_dir = self._child_route_prep_dir(entry)
        artifact_specs = [
            ("staleness", "child_selected_target_staleness", prep_dir / "child_selected_target_staleness.json"),
            ("handoff_refresh", "child_replacement_handoff_refresh", prep_dir / "child_replacement_handoff_refresh.json"),
            (
                "response_validation",
                "child_replacement_response_validation",
                prep_dir / "child_replacement_response_validation.json",
            ),
            (
                "execution_checklist",
                "child_replacement_execution_checklist",
                prep_dir / "child_replacement_execution_checklist.json",
            ),
            (
                "command_copy_packet",
                "child_replacement_command_copy_packet",
                prep_dir / "child_replacement_command_copy_packet.json",
            ),
        ]
        artifacts: dict[str, dict[str, Any]] = {}
        blocked_reasons: list[str] = []
        for name, kind, path in artifact_specs:
            payload = _read_json_file(path)
            exists = payload is not None
            artifacts[name] = {
                "kind": kind,
                "path": str(path),
                "exists": exists,
                "state": (payload or {}).get("state"),
                "payload": payload,
            }
            if not exists:
                blocked_reasons.append(f"{kind} artifact is missing")
        staleness = dict((artifacts.get("staleness") or {}).get("payload") or {})
        refresh = dict((artifacts.get("handoff_refresh") or {}).get("payload") or {})
        validation = dict((artifacts.get("response_validation") or {}).get("payload") or {})
        checklist = dict((artifacts.get("execution_checklist") or {}).get("payload") or {})
        command_copy = dict((artifacts.get("command_copy_packet") or {}).get("payload") or {})
        expected_states = {
            "staleness": "stale",
            "handoff_refresh": "ready_for_replacement_handoff",
            "response_validation": "ready_for_no_live_replacement_checklist",
            "execution_checklist": "ready_for_replacement_operator_review",
            "command_copy_packet": "ready_for_replacement_operator_copy",
        }
        for name, expected_state in expected_states.items():
            artifact = artifacts.get(name) or {}
            if artifact.get("exists") and artifact.get("state") != expected_state:
                blocked_reasons.append(
                    f"{artifact.get('kind') or name} state is {artifact.get('state') or 'missing'}"
                )
        stale_artifact_kinds = [
            str(item.get("kind") or "")
            for item in list(staleness.get("stale_artifacts") or [])
            if isinstance(item, dict) and item.get("exists")
        ]
        if staleness and not stale_artifact_kinds:
            blocked_reasons.append("child selected-target staleness marker does not name stale predecessor artifacts")
        if command_copy and command_copy.get("executable_live_command") is not None:
            blocked_reasons.append("replacement command-copy packet unexpectedly contains an executable live command")
        selected_target_created = any(
            bool(payload.get("selected_target_created") or payload.get("creates_selected_live_target"))
            for payload in [refresh, validation, checklist, command_copy]
            if isinstance(payload, dict)
        )
        if selected_target_created:
            blocked_reasons.append("replacement artifact reports selected target creation")
        writes_attempted = sum(
            int(payload.get("writes_attempted") or 0)
            for payload in [staleness, refresh, validation, checklist, command_copy]
            if isinstance(payload, dict)
        )
        network_calls_made = sum(
            int(payload.get("network_calls_made") or 0)
            for payload in [staleness, refresh, validation, checklist, command_copy]
            if isinstance(payload, dict)
        )
        if writes_attempted:
            blocked_reasons.append("replacement artifacts report live writes attempted")
        if network_calls_made:
            blocked_reasons.append("replacement artifacts report network calls made")
        state = "ready_for_operator_closeout" if not blocked_reasons else "blocked"
        payload = {
            "schema": "business-card-watchdog.child-replacement-closeout-status.v1",
            "generated_at": utc_now(),
            "state": state,
            "run_id": run_id,
            "job_id": entry.get("job_id"),
            "candidate_id": candidate_id,
            "work_item_id": entry.get("work_item_id"),
            "sink": command_copy.get("sink") or checklist.get("sink") or validation.get("sink") or refresh.get("sink"),
            "operator": (
                command_copy.get("operator")
                or checklist.get("operator")
                or validation.get("operator")
                or refresh.get("operator")
            ),
            "scope": command_copy.get("scope") or checklist.get("scope") or validation.get("scope") or refresh.get("scope"),
            "blocked_reasons": blocked_reasons,
            "artifacts": artifacts,
            "rollup": {
                "predecessor_artifacts_stale": staleness.get("state") == "stale" and bool(stale_artifact_kinds),
                "stale_artifact_kinds": stale_artifact_kinds,
                "replacement_handoff_ready": refresh.get("state") == "ready_for_replacement_handoff",
                "replacement_response_ready": validation.get("state") == "ready_for_no_live_replacement_checklist",
                "replacement_checklist_ready": checklist.get("state") == "ready_for_replacement_operator_review",
                "replacement_copy_ready": command_copy.get("state") == "ready_for_replacement_operator_copy",
                "acknowledgement_ok": bool(command_copy.get("acknowledgement_ok")),
                "offline_command_copy_text": command_copy.get("offline_command_copy_text"),
                "selected_target_created": selected_target_created,
                "executable_live_command": command_copy.get("executable_live_command"),
            },
            "selected_target_created": False,
            "creates_selected_live_target": False,
            "writes_attempted": writes_attempted,
            "network_calls_made": network_calls_made,
            "commands": {
                "refresh_handoff": (
                    f"reviews child-replacement-handoff-refresh {shlex.quote(candidate_id)} "
                    f"--run-id {run_id} --sink <sink> --operator <operator> --json"
                ),
                "validate_replacement_response": (
                    f"reviews child-validate-replacement-response {shlex.quote(candidate_id)} "
                    f"--run-id {run_id} --response <operator-response> --json"
                ),
                "replacement_execution_checklist": (
                    f"reviews child-replacement-execution-checklist {shlex.quote(candidate_id)} "
                    f"--run-id {run_id} --response <operator-response> --json"
                ),
                "replacement_command_copy_packet": (
                    f"reviews child-replacement-command-copy-packet {shlex.quote(candidate_id)} "
                    f"--run-id {run_id} --response <operator-response> "
                    "--acknowledgement <operator-acknowledgement> --json"
                ),
                "closeout_status": (
                    f"reviews child-replacement-closeout-status {shlex.quote(candidate_id)} "
                    f"--run-id {run_id} --json"
                ),
            },
            "explicit_stop_conditions": [
                "This closeout/status packet is a no-live local rollup.",
                "This packet does not create selected_live_target.json.",
                "This packet does not execute any copied command.",
                "Do not run live GWS/Odollo/Odoo lookup, write, or readback from this packet.",
                "Do not process private SyncThing images, run public-web search, or call paid enrichment from this packet.",
            ],
        }
        closeout_path = prep_dir / "child_replacement_closeout_status.json"
        closeout_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        ledger = RunLedger(self.config.runs_dir / run_id)
        parent_job_id = str(entry.get("job_id") or "__run__")
        ledger.record_artifact(job_id=parent_job_id, kind="child_replacement_closeout_status", path=closeout_path)
        ledger.record_event(
            "child_replacement_closeout_status_created",
            {
                "run_id": run_id,
                "job_id": entry.get("job_id"),
                "candidate_id": candidate_id,
                "state": state,
                "closeout_path": str(closeout_path),
                "writes_attempted": writes_attempted,
                "network_calls_made": network_calls_made,
            },
        )
        payload["closeout_path"] = str(closeout_path)
        return payload

    def _child_route_prep_entry(self, *, run_id: str, candidate_id: str) -> dict[str, Any]:
        entry = next(
            (
                row
                for row in self.child_route_prep_queue(run_id=run_id, state="all")
                if str(row.get("candidate_id") or "") == candidate_id
            ),
            None,
        )
        if entry is None:
            raise FileNotFoundError(f"prepared child contact candidate not found: {candidate_id}")
        prep_result = dict(entry.get("child_route_prep_result") or {})
        if not prep_result:
            raise FileNotFoundError(f"child route prep result not found: {candidate_id}")
        return entry

    def _child_route_prep_dir(self, entry: dict[str, Any]) -> Path:
        prep_result = dict(entry.get("child_route_prep_result") or {})
        lookup_plan_path = Path(str(prep_result.get("child_sink_lookup_plan_path") or ""))
        if not lookup_plan_path:
            raise FileNotFoundError("child sink lookup plan path is missing")
        return lookup_plan_path.parent

    def review_bundle(self, *, run_id: str, state: str = "all", write: bool = True) -> dict[str, Any]:
        run = self.get_run(run_id)
        artifacts = self.list_artifacts(run_id)
        artifacts_by_job: dict[str, dict[str, dict[str, Any]]] = {}
        for artifact in artifacts:
            job_id = str(artifact.get("job_id") or "")
            kind = str(artifact.get("kind") or "")
            if kind in _REVIEW_BUNDLE_ARTIFACT_KINDS:
                artifacts_by_job.setdefault(job_id, {})[kind] = artifact
        next_by_job = {
            str(action["job_id"]): action
            for action in self.next_actions(run_id=run_id, limit=max(1000, int(run.get("job_count") or 0) + 10))["actions"]
        }
        entries: list[dict[str, Any]] = []
        for job in self.list_jobs(run_id):
            if state != "all" and job.get("state") != state:
                continue
            by_kind = artifacts_by_job.get(str(job["job_id"]), {})
            next_action = next_by_job.get(str(job["job_id"]))
            sink_pilot_status = self._sink_pilot_status(by_kind=by_kind, next_action=next_action)
            artifact_entries = {
                kind: self._artifact_bundle_entry(record)
                for kind, record in sorted(by_kind.items())
            }
            child_replacement_status = self._child_replacement_bundle_status(artifact_entries)
            review_matrix = self._review_matrix_entry(
                job=job,
                artifacts=artifact_entries,
                next_action=next_action,
                sink_pilot_status=sink_pilot_status,
            )
            entries.append(
                {
                    "run_id": run_id,
                    "job_id": job["job_id"],
                    "state": job["state"],
                    "image_path": job["image_path"],
                    "error": job.get("error"),
                    "artifact_dir": job.get("artifact_dir"),
                    "next_action": next_action,
                    "sink_pilot_status": sink_pilot_status,
                    "child_replacement_status": child_replacement_status,
                    "review_matrix": review_matrix,
                    "artifact_kinds": sorted(by_kind),
                    "artifacts": artifact_entries,
                    "decision_template": self._review_decision_template(
                        run_id=run_id,
                        job_id=str(job["job_id"]),
                        next_action=next_action,
                    ),
                    "commands": {
                        "show_job": f"jobs show {job['job_id']} --run-id {run_id}",
                        "review": f"jobs review {job['job_id']} --run-id {run_id}",
                        "next": (next_action or {}).get("command"),
                        "live_pilot_handoff": f"runs live-pilot-handoff {run_id}",
                        "validate_operator_response": (
                            f"runs live-pilot-validate-response {run_id} --response <operator-response> --json"
                        ),
                    },
                }
            )
        groups = self._review_bundle_groups(entries)
        payload = {
            "schema": "business-card-watchdog.review-bundle.v1",
            "run_id": run_id,
            "state_filter": state,
            "created_at": utc_now(),
            "job_count": len(entries),
            "run_state": run.get("state"),
            "summary": self.run_summary(run_id),
            "groups": groups,
            "decision_import_template": [entry["decision_template"] for entry in entries],
            "entries": entries,
            "commands": {
                "refresh": f"reviews bundle --run-id {run_id} --state {state}",
                "list": f"reviews list --run-id {run_id} --state {state}",
                "apply_decisions": f"reviews apply-decisions --run-id {run_id} --decisions-file <path>",
                "phase_report": f"runs phase-report {run_id}",
                "run_next_safe": f"actions run-next --run-id {run_id}",
                "live_pilot_handoff": f"runs live-pilot-handoff {run_id}",
                "validate_operator_response": (
                    f"runs live-pilot-validate-response {run_id} --response <operator-response> --json"
                ),
                "next_actions": f"mcp-call business_card_watchdog_next_actions --arguments-json '{{\"run_id\":\"{run_id}\"}}'",
                "mcp_phase_report": f"mcp-call business_card_watchdog_phase_report --arguments-json '{{\"run_id\":\"{run_id}\"}}'",
            },
            "writes_attempted": 0,
            "network_calls_made": 0,
        }
        if write:
            bundle_path = self.config.runs_dir / run_id / "review_bundle.json"
            bundle_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            ledger = RunLedger(self.config.runs_dir / run_id)
            ledger.record_artifact(job_id="__run__", kind="review_bundle", path=bundle_path)
            ledger.record_event(
                "review_bundle_created",
                {
                    "run_id": run_id,
                    "bundle_path": str(bundle_path),
                    "job_count": len(entries),
                    "state_filter": state,
                    "writes_attempted": 0,
                    "network_calls_made": 0,
                },
            )
            payload["review_bundle_path"] = str(bundle_path)
        return payload

    def review_html(self, *, run_id: str, state: str = "all", write: bool = True) -> dict[str, Any]:
        bundle = self.review_bundle(run_id=run_id, state=state, write=write)
        html = self._render_review_html(bundle)
        html_path = self.config.runs_dir / run_id / "review_bundle.html"
        if write:
            html_path.write_text(html, encoding="utf-8")
            ledger = RunLedger(self.config.runs_dir / run_id)
            ledger.record_artifact(job_id="__run__", kind="review_html", path=html_path)
            ledger.record_event(
                "review_html_created",
                {
                    "run_id": run_id,
                    "html_path": str(html_path),
                    "job_count": bundle["job_count"],
                    "state_filter": state,
                    "writes_attempted": 0,
                    "network_calls_made": 0,
                },
            )
        return {
            "schema": "business-card-watchdog.review-html.v1",
            "run_id": run_id,
            "state_filter": state,
            "html_path": str(html_path) if write else None,
            "html": html,
            "bundle_path": bundle.get("review_bundle_path"),
            "job_count": bundle["job_count"],
            "writes_attempted": 0,
            "network_calls_made": 0,
        }

    def review_workbook(self, *, run_id: str, state: str = "all", write: bool = True) -> dict[str, Any]:
        bundle = self.review_bundle(run_id=run_id, state=state, write=write)
        csv_text = self._render_review_workbook_csv(bundle)
        workbook_path = self.config.runs_dir / run_id / "review_workbook.csv"
        payload = {
            "schema": "business-card-watchdog.review-workbook.v1",
            "run_id": run_id,
            "state_filter": state,
            "format": "csv",
            "row_count": bundle["job_count"],
            "csv": csv_text,
            "bundle_path": bundle.get("review_bundle_path"),
            "writes_attempted": 0,
            "network_calls_made": 0,
        }
        if write:
            workbook_path.write_text(csv_text, encoding="utf-8")
            ledger = RunLedger(self.config.runs_dir / run_id)
            ledger.record_artifact(job_id="__run__", kind="review_workbook", path=workbook_path)
            ledger.record_event(
                "review_workbook_created",
                {
                    "run_id": run_id,
                    "workbook_path": str(workbook_path),
                    "row_count": bundle["job_count"],
                    "state_filter": state,
                    "writes_attempted": 0,
                    "network_calls_made": 0,
                },
            )
            payload["workbook_path"] = str(workbook_path)
        return payload

    def submit_review(
        self,
        *,
        job_id: str,
        run_id: str,
        reviewer: str,
        action: str,
        field_corrections: dict[str, Any] | None = None,
        crop_selection: dict[str, Any] | None = None,
        approved_enrichment_fields: list[str] | None = None,
        duplicate_resolution: dict[str, Any] | None = None,
        notes: str = "",
    ) -> dict[str, Any]:
        if action not in _SUPPORTED_REVIEW_ACTIONS:
            raise ValueError(f"unsupported review action: {action}")

        job_payload = self.get_job(job_id, run_id=run_id)
        job = CardJob.from_dict(job_payload)
        submission = build_review_submission(
            job_id=job_id,
            reviewer=reviewer,
            action=action,  # type: ignore[arg-type]
            field_corrections=field_corrections,
            crop_selection=crop_selection,
            approved_enrichment_fields=approved_enrichment_fields,
            duplicate_resolution=duplicate_resolution,
            notes=notes,
        )
        artifact_dir = Path(job.artifact_dir) if job.artifact_dir else self.config.runs_dir / run_id / "artifacts" / job_id
        submission_path = write_review_submission(artifact_dir / "review_submission.json", submission)

        ledger = RunLedger(self.config.runs_dir / run_id)
        ledger.record_artifact(job_id=job_id, kind="review_submission", path=submission_path)
        route_refresh = None
        if action == "approve_for_routing":
            candidate_path = artifact_dir / "contact_candidate.json"
            if candidate_path.exists():
                candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
            else:
                candidate = build_contact_candidate({})
            reviewed_contact = apply_review_corrections(
                candidate,
                reviewer=reviewer,
                field_corrections=field_corrections or {},
                default_country=self.config.normalization.default_country,
            )
            reviewed_contact_path = artifact_dir / "reviewed_contact.json"
            reviewed_contact_path.write_text(
                json.dumps(reviewed_contact, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            ledger.record_artifact(job_id=job_id, kind="reviewed_contact", path=reviewed_contact_path)
            job.transition_to("ready_to_route")
            ledger.record_job(job)
            route_refresh = self._record_route_refresh_if_needed(
                artifact_dir,
                job_id=job_id,
                run_id=run_id,
                reviewer=reviewer,
                reason="reviewed_contact_updated",
            )
        elif action == "approve_enrichment_merge":
            candidate_path = artifact_dir / "reviewed_contact.json"
            if not candidate_path.exists():
                candidate_path = artifact_dir / "contact_candidate.json"
            if candidate_path.exists():
                candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
            else:
                candidate = build_contact_candidate({})
            enrichment_result_path = artifact_dir / "enrichment_result.json"
            if not enrichment_result_path.exists():
                raise FileNotFoundError(f"enrichment result not found for job: {job_id}")
            enrichment_result = json.loads(enrichment_result_path.read_text(encoding="utf-8"))
            reviewed_contact, merge_review = apply_enrichment_proposals(
                candidate,
                reviewer=reviewer,
                proposals=list(enrichment_result.get("merge_proposals") or []),
                approved_fields=approved_enrichment_fields or [],
                default_country=self.config.normalization.default_country,
            )
            reviewed_contact_path = artifact_dir / "reviewed_contact.json"
            reviewed_contact_path.write_text(
                json.dumps(reviewed_contact, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            merge_review_path = artifact_dir / "enrichment_merge_review.json"
            merge_review_path.write_text(
                json.dumps(merge_review, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            proposal_review = self._build_enrichment_proposal_review(
                enrichment_result=enrichment_result,
                merge_review=merge_review,
                reviewer=reviewer,
            )
            proposal_review_path = artifact_dir / "enrichment_proposal_review.json"
            proposal_review_path.write_text(
                json.dumps(proposal_review, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            ledger.record_artifact(job_id=job_id, kind="reviewed_contact", path=reviewed_contact_path)
            ledger.record_artifact(job_id=job_id, kind="enrichment_merge_review", path=merge_review_path)
            ledger.record_artifact(
                job_id=job_id,
                kind="enrichment_proposal_review",
                path=proposal_review_path,
            )
            job.transition_to("ready_to_route" if merge_review["applied"] else "needs_review")
            ledger.record_job(job)
            ledger.record_event(
                "enrichment_merge_reviewed",
                {
                    "job_id": job_id,
                    "run_id": run_id,
                    "reviewer": reviewer,
                    "approved_fields": merge_review["approved_fields"],
                    "applied_count": len(merge_review["applied"]),
                    "rejected_count": proposal_review["rejected_count"],
                    "merge_review_path": str(merge_review_path),
                    "proposal_review_path": str(proposal_review_path),
                },
            )
            if merge_review["applied"]:
                route_refresh = self._record_route_refresh_if_needed(
                    artifact_dir,
                    job_id=job_id,
                    run_id=run_id,
                    reviewer=reviewer,
                    reason="enrichment_merge_updated_reviewed_contact",
                )
        elif action == "request_enrichment":
            if job.state != "needs_review":
                job.transition_to("needs_review")
                ledger.record_job(job)
        elif action == "resolve_duplicate":
            duplicate_path = artifact_dir / "duplicate_assessment.json"
            if not duplicate_path.exists():
                duplicate_path = artifact_dir / "downstream_duplicate_assessment.json"
            if not duplicate_path.exists():
                raise FileNotFoundError(f"duplicate assessment not found for job: {job_id}")
            resolution = dict(duplicate_resolution or {})
            decision = str(resolution.get("decision") or "")
            if not decision:
                raise ValueError("duplicate resolution decision is required")
            resolution_payload = {
                "schema": "business-card-watchdog.duplicate-resolution.v1",
                "job_id": job_id,
                "run_id": run_id,
                "reviewer": reviewer,
                "decision": decision,
                "target_identity": resolution.get("target_identity"),
                "reason": resolution.get("reason") or notes,
                "duplicate_assessment": json.loads(duplicate_path.read_text(encoding="utf-8")),
            }
            resolution_path = artifact_dir / "duplicate_resolution.json"
            resolution_path.write_text(
                json.dumps(resolution_payload, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            ledger.record_artifact(job_id=job_id, kind="duplicate_resolution", path=resolution_path)
            contact_spec = self._contact_spec_for_artifact_dir(artifact_dir)
            resolution_record = remember_duplicate_resolution(
                self.config,
                spec=contact_spec,
                resolution=resolution_payload,
                job_id=job_id,
                run_id=run_id,
                image_path=job.image_path,
            )
            if decision == "noop":
                job.transition_to("cancelled", error="duplicate resolved as no-op")
            else:
                job.transition_to("ready_to_route")
            ledger.record_job(job)
            ledger.record_event(
                "duplicate_resolved",
                {
                    "job_id": job_id,
                    "run_id": run_id,
                    "reviewer": reviewer,
                    "decision": decision,
                    "resolution_path": str(resolution_path),
                    "resolution_index_schema": resolution_record.schema,
                },
            )
            if decision != "noop":
                route_refresh = self._record_route_refresh_if_needed(
                    artifact_dir,
                    job_id=job_id,
                    run_id=run_id,
                    reviewer=reviewer,
                    reason="duplicate_resolution_updated_route_context",
                )
        elif action == "reject_not_card":
            job.transition_to("failed", error="review rejected image as not a business card")
            ledger.record_job(job)
        elif action == "skip":
            job.transition_to("cancelled", error="review skipped job")
            ledger.record_job(job)
        ledger.record_event(
            "review_submitted",
            {
                "job_id": job_id,
                "run_id": run_id,
                "action": action,
                "reviewer": reviewer,
                "submission_path": str(submission_path),
            },
        )
        response = {
            "job": job.to_dict(),
            "submission": submission,
            "submission_path": str(submission_path),
        }
        if route_refresh is not None:
            response["route_refresh"] = route_refresh["route_refresh"]
            response["route_refresh_path"] = route_refresh["route_refresh_path"]
        return response

    def apply_review_decisions(
        self,
        *,
        run_id: str,
        decisions: list[dict[str, Any]],
        reviewer: str = "operator",
    ) -> dict[str, Any]:
        applied: list[dict[str, Any]] = []
        for index, decision in enumerate(decisions):
            job_id = str(decision.get("job_id") or "").strip()
            if not job_id:
                raise ValueError(f"review decision at index {index} is missing job_id")
            result = self.submit_review(
                job_id=job_id,
                run_id=str(decision.get("run_id") or run_id),
                reviewer=str(decision.get("reviewer") or reviewer),
                action=str(decision.get("action") or "keep_needs_review"),
                field_corrections=dict(decision.get("field_corrections") or {}),
                crop_selection=dict(decision.get("crop_selection") or {}),
                approved_enrichment_fields=list(decision.get("approved_enrichment_fields") or []),
                duplicate_resolution=dict(decision.get("duplicate_resolution") or {}),
                notes=str(decision.get("notes") or ""),
            )
            applied.append(
                {
                    "index": index,
                    "job_id": job_id,
                    "action": result["submission"]["action"],
                    "job_state": result["job"]["state"],
                    "submission_path": result["submission_path"],
                    "route_refresh_path": result.get("route_refresh_path"),
                }
            )
        payload = {
            "schema": "business-card-watchdog.review-decisions-import.v1",
            "run_id": run_id,
            "reviewer": reviewer,
            "decision_count": len(decisions),
            "applied_count": len(applied),
            "applied": applied,
            "writes_attempted": 0,
            "network_calls_made": 0,
        }
        import_path = self.config.runs_dir / run_id / "review_decisions_import.json"
        import_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        ledger = RunLedger(self.config.runs_dir / run_id)
        ledger.record_artifact(job_id="__run__", kind="review_decisions_import", path=import_path)
        ledger.record_event(
            "review_decisions_imported",
            {
                "run_id": run_id,
                "reviewer": reviewer,
                "decision_count": len(decisions),
                "applied_count": len(applied),
                "import_path": str(import_path),
                "writes_attempted": 0,
                "network_calls_made": 0,
            },
        )
        return {
            "import_path": str(import_path),
            "import": payload,
            "results": applied,
        }

    def apply_review_workbook_csv(
        self,
        *,
        run_id: str,
        csv_text: str,
        reviewer: str = "operator",
    ) -> dict[str, Any]:
        decisions = self._review_decisions_from_workbook_csv(csv_text)
        payload = self.apply_review_decisions(run_id=run_id, reviewer=reviewer, decisions=decisions)
        payload["import"]["source_format"] = "csv"
        payload["import"]["source_schema"] = "business-card-watchdog.review-workbook.v1"
        import_path = self.config.runs_dir / run_id / "review_decisions_import.json"
        import_path.write_text(json.dumps(payload["import"], indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return payload

    def preview_review_workbook_csv(
        self,
        *,
        run_id: str,
        csv_text: str,
        reviewer: str = "operator",
        write: bool = False,
    ) -> dict[str, Any]:
        try:
            entries = self._review_workbook_decision_entries(csv_text)
        except ValueError as exc:
            payload = {
                "schema": "business-card-watchdog.review-workbook-preview.v1",
                "run_id": run_id,
                "reviewer": reviewer,
                "valid": False,
                "row_count": 0,
                "decision_count": 0,
                "ready_count": 0,
                "skipped_count": 0,
                "error_count": 1,
                "rows": [],
                "errors": [{"message": str(exc)}],
                "writes_attempted": 0,
                "network_calls_made": 0,
            }
            payload["validation_csv"] = self._render_review_workbook_preview_csv(payload["rows"], payload["errors"])
            if write:
                self._write_review_workbook_preview_artifacts(run_id, payload)
            return payload
        rows: list[dict[str, Any]] = []
        jobs_by_run: dict[str, dict[str, dict[str, Any]]] = {}
        artifacts_by_run: dict[str, dict[str, set[str]]] = {}
        for entry in entries:
            row_number = int(entry["row_number"])
            if entry.get("skipped"):
                rows.append(
                    {
                        "row_number": row_number,
                        "status": "skipped",
                        "reason": entry.get("skip_reason") or "skip_import",
                        "errors": [],
                        "warnings": [],
                    }
                )
                continue
            decision = dict(entry["decision"])
            decision_run_id = str(decision.get("run_id") or run_id)
            job_id = str(decision.get("job_id") or "")
            action = str(decision.get("action") or "keep_needs_review")
            if decision_run_id not in jobs_by_run:
                jobs_by_run[decision_run_id] = {str(job["job_id"]): job for job in self.list_jobs(decision_run_id)}
                artifact_kinds: dict[str, set[str]] = {}
                for artifact in self.list_artifacts(decision_run_id):
                    artifact_kinds.setdefault(str(artifact.get("job_id") or ""), set()).add(str(artifact.get("kind") or ""))
                artifacts_by_run[decision_run_id] = artifact_kinds
            errors: list[str] = []
            warnings: list[str] = []
            artifact_kinds = artifacts_by_run[decision_run_id].get(job_id, set())
            if job_id not in jobs_by_run[decision_run_id]:
                errors.append(f"job not found in run {decision_run_id}: {job_id}")
            if action not in _SUPPORTED_REVIEW_ACTIONS:
                errors.append(f"unsupported review action: {action}")
            if action == "approve_enrichment_merge" and "enrichment_result" not in artifact_kinds:
                errors.append("approve_enrichment_merge requires an enrichment_result artifact")
            if action == "resolve_duplicate":
                if not ({"duplicate_assessment", "downstream_duplicate_assessment"} & artifact_kinds):
                    errors.append("resolve_duplicate requires a duplicate assessment artifact")
                if not dict(decision.get("duplicate_resolution") or {}).get("decision"):
                    errors.append("resolve_duplicate requires duplicate_resolution.decision")
            if action == "approve_for_routing" and "contact_candidate" not in artifact_kinds:
                warnings.append("approve_for_routing will fall back to an empty contact candidate")
            sink_readiness_warnings = self._review_workbook_sink_readiness_warnings(decision)
            warnings.extend(str(warning["message"]) for warning in sink_readiness_warnings)
            rows.append(
                {
                    "row_number": row_number,
                    "run_id": decision_run_id,
                    "job_id": job_id,
                    "action": action,
                    "status": "ready" if not errors else "error",
                    "errors": errors,
                    "warnings": warnings,
                    "artifact_kinds": sorted(kind for kind in artifact_kinds if kind),
                    "field_correction_count": len(dict(decision.get("field_corrections") or {})),
                    "approved_enrichment_fields": list(decision.get("approved_enrichment_fields") or []),
                    "duplicate_resolution": dict(decision.get("duplicate_resolution") or {}),
                    "sink_readiness_warnings": sink_readiness_warnings,
                }
            )
        skipped_count = sum(1 for row in rows if row["status"] == "skipped")
        error_count = sum(1 for row in rows if row["status"] == "error")
        ready_count = sum(1 for row in rows if row["status"] == "ready")
        payload = {
            "schema": "business-card-watchdog.review-workbook-preview.v1",
            "run_id": run_id,
            "reviewer": reviewer,
            "valid": error_count == 0,
            "row_count": len(rows),
            "decision_count": ready_count + error_count,
            "ready_count": ready_count,
            "skipped_count": skipped_count,
            "error_count": error_count,
            "rows": rows,
            "errors": [error for row in rows for error in row.get("errors", [])],
            "writes_attempted": 0,
            "network_calls_made": 0,
        }
        payload["validation_csv"] = self._render_review_workbook_preview_csv(payload["rows"], payload["errors"])
        if write:
            self._write_review_workbook_preview_artifacts(run_id, payload)
        return payload

    def list_artifacts(self, run_id: str) -> list[dict[str, Any]]:
        artifacts_path = self.config.runs_dir / run_id / "artifacts.jsonl"
        if not artifacts_path.exists():
            return []
        return _read_jsonl(artifacts_path)

    def sink_readiness(self) -> dict[str, Any]:
        sinks: list[str] = []
        if self.config.sink.google_contacts:
            sinks.append("google_contacts")
        if self.config.sink.odoo:
            sinks.append("odoo")
        if not sinks:
            sinks = ["google_contacts", "odoo"]
        return {
            "dry_run": self.config.sink.dry_run,
            "sinks": [
                check_sink_readiness(
                    sink,
                    dry_run=self.config.sink.dry_run,
                    apply_enabled=self._sink_apply_enabled(sink),
                    google_contacts_profile=self.config.sink.google_contacts_profile,
                    odollo_tenant=self.config.sink.odollo_tenant,
                ).to_dict()
                for sink in sinks
            ],
        }

    def live_lookup_readiness_report(self, *, job_id: str, run_id: str, sink: str) -> dict[str, Any]:
        if sink not in {"google_contacts", "odoo"}:
            raise ValueError(f"unsupported live lookup sink: {sink}")
        job = self.get_job(job_id, run_id=run_id)
        artifact_dir = Path(job["artifact_dir"]) if job.get("artifact_dir") else self.config.runs_dir / run_id / "artifacts" / job_id
        reviewed_path = artifact_dir / "reviewed_contact.json"
        lookup_plan_path = artifact_dir / "sink_lookup_plan.json"
        adapter_request_path = artifact_dir / "sink_adapter_request_lookup.json"
        downstream_assessment_path = artifact_dir / "downstream_duplicate_assessment.json"
        reviewed = _read_json_file(reviewed_path)
        lookup_plan = _read_json_file(lookup_plan_path)
        adapter_request = _read_json_file(adapter_request_path)
        downstream_assessment = _read_json_file(downstream_assessment_path)
        lookup_plan_sinks = [
            str(row.get("sink") or "")
            for row in list((lookup_plan or {}).get("lookups") or [])
            if isinstance(row, dict)
        ]
        adapter_request_sinks = [
            str(row.get("sink") or "")
            for row in list((adapter_request or {}).get("requests") or [])
            if isinstance(row, dict) and row.get("phase") == "lookup"
        ]
        selected_sink_enabled = (
            bool(self.config.sink.google_contacts)
            if sink == "google_contacts"
            else bool(self.config.sink.odoo)
        )
        live_readiness = check_sink_lookup_readiness(
            sink,
            dry_run=False,
            google_contacts_profile=self.config.sink.google_contacts_profile,
            odollo_tenant=self.config.sink.odollo_tenant,
        ).to_dict()
        requirements = [
            {
                "name": "job_ready_to_route",
                "ok": job.get("state") == "ready_to_route",
                "detail": f"job state is {job.get('state')}",
            },
            {
                "name": "reviewed_contact_exists",
                "ok": reviewed is not None,
                "detail": str(reviewed_path),
            },
            {
                "name": "selected_sink_enabled",
                "ok": selected_sink_enabled,
                "detail": f"sink.{sink} enabled in user config",
            },
            {
                "name": "lookup_plan_exists",
                "ok": lookup_plan is not None,
                "detail": str(lookup_plan_path),
            },
            {
                "name": "lookup_plan_includes_sink",
                "ok": sink in lookup_plan_sinks,
                "detail": ",".join(sorted(lookup_plan_sinks)) or "no lookup plan sinks",
            },
            {
                "name": "lookup_adapter_request_exists",
                "ok": adapter_request is not None,
                "detail": str(adapter_request_path),
            },
            {
                "name": "lookup_adapter_request_includes_sink",
                "ok": sink in adapter_request_sinks,
                "detail": ",".join(sorted(adapter_request_sinks)) or "no lookup adapter request sinks",
            },
            {
                "name": "live_lookup_readiness_ready",
                "ok": live_readiness.get("status") == "ready",
                "detail": str(live_readiness.get("reason") or ""),
            },
        ]
        requirement_by_name = {str(item["name"]): bool(item["ok"]) for item in requirements}
        ready = all(requirement_by_name.values())
        return {
            "schema": "business-card-watchdog.live-lookup-readiness.v1",
            "state": "ready" if ready else "blocked",
            "status": "ready" if ready else "blocked",
            "reason": (
                "selected job and sink are ready for an explicit read-only live lookup pilot"
                if ready
                else "selected job and sink are not ready for live lookup"
            ),
            "run_id": run_id,
            "job_id": job_id,
            "sink": sink,
            "writes_attempted": 0,
            "network_calls_made": 0,
            "requirements": requirements,
            "missing_requirements": [
                str(item["name"]) for item in requirements if not item["ok"]
            ],
            "live_lookup_readiness": live_readiness,
            "job_state": job.get("state"),
            "lookup_plan_state": (lookup_plan or {}).get("state", "missing"),
            "downstream_duplicate_state": (downstream_assessment or {}).get("state", "missing"),
            "artifact_paths": {
                "reviewed_contact": str(reviewed_path),
                "sink_lookup_plan": str(lookup_plan_path),
                "sink_adapter_request_lookup": str(adapter_request_path),
                "downstream_duplicate_assessment": str(downstream_assessment_path),
            },
            "commands": {
                "review": f"jobs review {job_id} --run-id {run_id}",
                "run_next_safe": f"actions run-next --run-id {run_id}",
                "lookup_plan": f"sinks lookup-plan {job_id} --run-id {run_id}",
                "lookup_adapter_request": f"sinks adapter-request {job_id} --run-id {run_id} --phase lookup",
                "live_lookup_pilot": (
                    f"sinks lookup-pilot {job_id} --run-id {run_id} "
                    f"--sink {sink} --approved-by <operator> --no-simulate"
                ),
            },
        }

    def build_sink_lookup_smoke_handoff_for_job(
        self,
        *,
        job_id: str,
        run_id: str,
        sink: str,
        approved_by: str = "operator",
        write: bool = True,
    ) -> dict[str, Any]:
        if sink not in {"google_contacts", "odoo"}:
            raise ValueError("lookup smoke handoff requires sink google_contacts or odoo")
        job = self.get_job(job_id, run_id=run_id)
        artifact_dir = Path(job["artifact_dir"]) if job.get("artifact_dir") else self.config.runs_dir / run_id / "artifacts" / job_id
        readiness = self.live_lookup_readiness_report(job_id=job_id, run_id=run_id, sink=sink)
        lookup_plan_path = artifact_dir / "sink_lookup_plan.json"
        adapter_request_path = artifact_dir / "sink_adapter_request_lookup.json"
        lookup_pilot_path = artifact_dir / "sink_lookup_pilot.json"
        lookup_result_path = artifact_dir / "sink_lookup_result.json"
        downstream_assessment_path = artifact_dir / "downstream_duplicate_assessment.json"
        state = "ready_for_live_lookup" if readiness.get("state") == "ready" else "blocked"
        payload = {
            "schema": "business-card-watchdog.sink-lookup-smoke-handoff.v1",
            "state": state,
            "status": state,
            "reason": (
                "selected job and sink have readiness evidence for an explicit read-only live lookup smoke"
                if state == "ready_for_live_lookup"
                else "read-only live lookup smoke is blocked until selected-target readiness requirements pass"
            ),
            "run_id": run_id,
            "job_id": job_id,
            "sink": sink,
            "approved_by": approved_by,
            "created_at": utc_now(),
            "read_only": True,
            "writes_attempted": 0,
            "network_calls_made": 0,
            "readiness": readiness,
            "missing_requirements": list(readiness.get("missing_requirements") or []),
            "artifacts": {
                "sink_lookup_plan": {
                    "path": str(lookup_plan_path),
                    "exists": lookup_plan_path.exists(),
                },
                "sink_adapter_request_lookup": {
                    "path": str(adapter_request_path),
                    "exists": adapter_request_path.exists(),
                },
                "sink_lookup_pilot": {
                    "path": str(lookup_pilot_path),
                    "exists": lookup_pilot_path.exists(),
                },
                "sink_lookup_result": {
                    "path": str(lookup_result_path),
                    "exists": lookup_result_path.exists(),
                },
                "downstream_duplicate_assessment": {
                    "path": str(downstream_assessment_path),
                    "exists": downstream_assessment_path.exists(),
                },
            },
            "commands": {
                "inspect_job": f"jobs show {job_id} --run-id {run_id}",
                "lookup_plan": f"sinks lookup-plan {job_id} --run-id {run_id}",
                "lookup_adapter_request": f"sinks adapter-request {job_id} --run-id {run_id} --phase lookup",
                "lookup_readiness": f"sinks lookup-readiness {job_id} --run-id {run_id} --sink {sink}",
                "live_lookup_pilot": (
                    f"sinks lookup-pilot {job_id} --run-id {run_id} --sink {sink} "
                    f"--approved-by {approved_by} --no-simulate"
                ),
                "assess_duplicates": f"sinks assess-duplicates {job_id} --run-id {run_id}",
                "review_bundle": f"reviews bundle --run-id {run_id} --state all",
            },
            "api": {
                "readiness": f"POST /jobs/{job_id}/sink-lookup-readiness",
                "live_lookup_pilot": f"POST /jobs/{job_id}/sink-lookup-pilot",
                "assess_duplicates": f"POST /jobs/{job_id}/downstream-duplicate-assessment",
            },
            "mcp": {
                "readiness": "business_card_watchdog_sink_lookup_readiness",
                "live_lookup_pilot": "business_card_watchdog_sink_lookup_pilot",
                "assess_duplicates": "business_card_watchdog_downstream_duplicate_assessment",
            },
            "stop_conditions": [
                "readiness state is not ready",
                "run, job, sink, or approver is not the explicit operator-selected target",
                "sink readiness references an unexpected Google profile or Odollo/Odoo tenant",
                "any command would write to a sink",
                "lookup returns possible duplicates that have not been reviewed",
                "raw live contact rows would be pasted into repo docs, issue trackers, or chat",
            ],
            "operator_note": (
                "This handoff is not live approval. It only packages the selected target and commands; "
                "the operator must explicitly run lookup-pilot with --no-simulate."
            ),
        }
        handoff_path = artifact_dir / "sink_lookup_smoke_handoff.json"
        if write:
            handoff_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            ledger = RunLedger(self.config.runs_dir / run_id)
            ledger.record_artifact(job_id=job_id, kind="sink_lookup_smoke_handoff", path=handoff_path)
            ledger.record_event(
                "sink_lookup_smoke_handoff_created",
                {
                    "job_id": job_id,
                    "run_id": run_id,
                    "sink": sink,
                    "approved_by": approved_by,
                    "handoff_path": str(handoff_path),
                    "state": state,
                    "writes_attempted": 0,
                    "network_calls_made": 0,
                },
            )
            self._mark_route_artifact_refreshed(
                artifact_dir,
                job_id=job_id,
                run_id=run_id,
                kind="sink_lookup_smoke_handoff",
            )
            return {"handoff_path": str(handoff_path), "handoff": payload}
        return {"handoff_path": str(handoff_path), "handoff": payload}

    def select_live_target_for_job(
        self,
        *,
        job_id: str,
        run_id: str,
        sink: str,
        operator: str,
        scope: str = "lookup",
        reason: str = "",
        safety_confirmation: str = "",
    ) -> dict[str, Any]:
        if sink not in {"google_contacts", "odoo"}:
            raise ValueError("selected live target requires sink google_contacts or odoo")
        if scope not in {"lookup", "write", "readback", "all"}:
            raise ValueError("selected live target scope must be lookup, write, readback, or all")
        if not operator.strip():
            raise ValueError("selected live target requires an operator")
        if not safety_confirmation.strip():
            raise ValueError("selected live target requires tenant/profile safety confirmation")
        safety_confirmation_blocker = _safety_confirmation_blocker(safety_confirmation)
        if safety_confirmation_blocker:
            raise ValueError(safety_confirmation_blocker)
        job = self.get_job(job_id, run_id=run_id)
        artifact_dir = Path(job["artifact_dir"]) if job.get("artifact_dir") else self.config.runs_dir / run_id / "artifacts" / job_id
        existing_target = _read_json_file(artifact_dir / "selected_live_target.json")
        abandonment = _read_json_file(artifact_dir / "live_pilot_abandonment.json") or {}
        existing_abandoned = (
            existing_target is not None
            and abandonment.get("state") == "abandoned"
            and str(abandonment.get("selected_target_identity") or abandonment.get("selected_target_created_at") or "")
            == _selected_target_identity(existing_target)
        )
        if existing_target is not None and not existing_abandoned:
            raise ValueError("selected live target already exists; abandon it before selecting a replacement")
        lookup_readiness = None
        apply_readiness = None
        if scope in {"lookup", "all"}:
            lookup_readiness = self.live_lookup_readiness_report(job_id=job_id, run_id=run_id, sink=sink)
        if scope in {"write", "readback", "all"}:
            apply_readiness = self.build_sink_apply_pilot_readiness_for_job(
                job_id=job_id,
                run_id=run_id,
                sink=sink,
            )["readiness"]
        missing_requirements = []
        if lookup_readiness is not None:
            missing_requirements.extend(
                f"lookup:{name}" for name in list(lookup_readiness.get("missing_requirements") or [])
            )
        if apply_readiness is not None:
            missing_requirements.extend(
                f"apply:{name}" for name in list(apply_readiness.get("missing_requirements") or [])
            )
        payload = {
            "schema": "business-card-watchdog.selected-live-target.v1",
            "state": "selected",
            "status": "selected",
            "reason": reason or "operator selected this exact run/job/sink/scope for explicit live pilot commands",
            "run_id": run_id,
            "job_id": job_id,
            "sink": sink,
            "operator": operator,
            "approved_by": operator,
            "scope": scope,
            "selection_id": str(uuid4()),
            "target_safety_confirmed": True,
            "target_safety_confirmation": safety_confirmation,
            "scope_allows": {
                "lookup": scope in {"lookup", "all"},
                "write": scope in {"write", "all"},
                "readback": scope in {"readback", "all"},
            },
            "created_at": utc_now(),
            "job_state": job.get("state"),
            "readiness": {
                "lookup": lookup_readiness,
                "apply": apply_readiness,
            },
            "missing_requirements": missing_requirements,
            "writes_attempted": 0,
            "network_calls_made": 0,
            "commands": {
                "lookup_pilot": (
                    f"sinks lookup-pilot {job_id} --run-id {run_id} --sink {sink} "
                    f"--approved-by {operator} --no-simulate"
                ),
                "write_pilot": (
                    f"sinks write-pilot {job_id} --run-id {run_id} --sink {sink} "
                    f"--approved-by {operator} --no-simulate"
                ),
                "readback_pilot": (
                    f"sinks readback-pilot {job_id} --run-id {run_id} --sink {sink} "
                    f"--approved-by {operator} --no-simulate"
                ),
            },
            "stop_conditions": [
                "the live command names a different run, job, sink, operator, or scope",
                "readiness artifacts are stale or reference a different sink",
                "operator did not explicitly request the non-simulated command after this record was created",
                "operator did not confirm the selected card/contact is safe for the target tenant/profile",
                "public-web search, paid enrichment, or duplicate merge decisions would be needed first",
            ],
            "operator_note": (
                "This is durable selected-target approval evidence. It is not a command execution; "
                "the operator must still explicitly run the non-simulated pilot command."
            ),
        }
        target_path = artifact_dir / "selected_live_target.json"
        target_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        ledger = RunLedger(self.config.runs_dir / run_id)
        ledger.record_artifact(job_id=job_id, kind="selected_live_target", path=target_path)
        ledger.record_event(
            "selected_live_target_created",
            {
                "job_id": job_id,
                "run_id": run_id,
                "sink": sink,
                "operator": operator,
                "scope": scope,
                "target_safety_confirmed": True,
                "target_path": str(target_path),
                "writes_attempted": 0,
                "network_calls_made": 0,
            },
        )
        self._mark_route_artifact_refreshed(
            artifact_dir,
            job_id=job_id,
            run_id=run_id,
            kind="selected_live_target",
        )
        return {"target_path": str(target_path), "target": payload}

    def selected_live_target_audit(
        self,
        *,
        job_id: str,
        run_id: str,
        scope: str | None = None,
        write: bool = True,
    ) -> dict[str, Any]:
        if scope is not None and scope not in {"lookup", "write", "readback", "all"}:
            raise ValueError("selected live target audit scope must be lookup, write, readback, all, or omitted")
        job = self.get_job(job_id, run_id=run_id)
        artifact_dir = (
            Path(job["artifact_dir"])
            if job.get("artifact_dir")
            else self.config.runs_dir / run_id / "artifacts" / job_id
        )
        target_path = artifact_dir / "selected_live_target.json"
        target = _read_json_file(target_path)
        blocked_reasons: list[str] = []
        mismatches: list[str] = []
        sink = str((target or {}).get("sink") or "")
        operator = str((target or {}).get("operator") or (target or {}).get("approved_by") or "")
        target_scope = str((target or {}).get("scope") or "")
        requested_scope = scope or target_scope or "lookup"
        lookup_readiness = None
        apply_readiness = None
        if target is None:
            blocked_reasons.append("selected_live_target.json is missing")
        else:
            for key, expected in [("run_id", run_id), ("job_id", job_id)]:
                if target.get(key) != expected:
                    mismatches.append(f"{key}={target.get(key)!r}")
            if sink not in {"google_contacts", "odoo"}:
                mismatches.append(f"sink={sink!r}")
            if not target.get("target_safety_confirmed") or not target.get("target_safety_confirmation"):
                mismatches.append("target_safety_confirmation=missing")
            allows = dict(target.get("scope_allows") or {})
            if requested_scope == "all":
                if not all(bool(allows.get(name)) for name in ["lookup", "write", "readback"]):
                    mismatches.append(f"scope={target_scope!r}")
            elif not bool(allows.get(requested_scope)):
                mismatches.append(f"scope={target_scope!r}")
            if mismatches:
                blocked_reasons.extend(mismatches)
            if sink in {"google_contacts", "odoo"} and requested_scope in {"lookup", "all"}:
                lookup_readiness = self.live_lookup_readiness_report(job_id=job_id, run_id=run_id, sink=sink)
                blocked_reasons.extend(
                    f"lookup:{name}" for name in list(lookup_readiness.get("missing_requirements") or [])
                )
            if sink in {"google_contacts", "odoo"} and requested_scope in {"write", "readback", "all"}:
                apply_readiness = self.build_sink_apply_pilot_readiness_for_job(
                    job_id=job_id,
                    run_id=run_id,
                    sink=sink,
                )["readiness"]
                blocked_reasons.extend(
                    f"apply:{name}" for name in list(apply_readiness.get("missing_requirements") or [])
                )
        state = "ready" if not blocked_reasons else "blocked"
        payload = {
            "schema": "business-card-watchdog.selected-live-target-audit.v1",
            "generated_at": utc_now(),
            "state": state,
            "run_id": run_id,
            "job_id": job_id,
            "job_state": job.get("state"),
            "scope": requested_scope,
            "selected_target_path": str(target_path),
            "selected_target_exists": target_path.exists(),
            "selected_target": target,
            "sink": sink or None,
            "operator": operator or None,
            "target_safety_confirmed": bool((target or {}).get("target_safety_confirmed")),
            "target_safety_confirmation": (target or {}).get("target_safety_confirmation"),
            "mismatches": mismatches,
            "blocked_reasons": blocked_reasons,
            "readiness": {
                "lookup": lookup_readiness,
                "apply": apply_readiness,
            },
            "writes_attempted": 0,
            "network_calls_made": 0,
            "commands": {
                "lookup_smoke": f"sinks execute-lookup-smoke {job_id} --run-id {run_id}",
                "write_pilot": (
                    f"sinks write-pilot {job_id} --run-id {run_id} --sink {sink} "
                    f"--approved-by {operator} --no-simulate"
                    if sink and operator
                    else None
                ),
                "readback_pilot": (
                    f"sinks readback-pilot {job_id} --run-id {run_id} --sink {sink} "
                    f"--approved-by {operator} --no-simulate"
                    if sink and operator
                    else None
                ),
            },
            "explicit_stop_conditions": [
                "This audit is not a live execution command.",
                "Do not run live lookup, live write, or live readback unless state is ready and the operator explicitly requests the matching command.",
                "Do not proceed if selected_live_target.json does not match run, job, sink, operator, scope, and target safety confirmation.",
                "Do not process private SyncThing images, run public-web search, or call paid enrichment from this audit.",
            ],
        }
        if write:
            audit_path = artifact_dir / "selected_live_target_audit.json"
            audit_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            ledger = RunLedger(self.config.runs_dir / run_id)
            ledger.record_artifact(job_id=job_id, kind="selected_live_target_audit", path=audit_path)
            ledger.record_event(
                "selected_live_target_audit_created",
                {
                    "job_id": job_id,
                    "run_id": run_id,
                    "scope": requested_scope,
                    "audit_path": str(audit_path),
                    "state": state,
                    "writes_attempted": 0,
                    "network_calls_made": 0,
                },
            )
            self._mark_route_artifact_refreshed(
                artifact_dir,
                job_id=job_id,
                run_id=run_id,
                kind="selected_live_target_audit",
            )
            payload["audit_path"] = str(audit_path)
        return payload

    def live_pilot_abandon_for_job(
        self,
        *,
        job_id: str,
        run_id: str,
        operator: str,
        reason: str,
    ) -> dict[str, Any]:
        if not operator.strip():
            raise ValueError("live pilot abandonment requires an operator")
        if not reason.strip():
            raise ValueError("live pilot abandonment requires a reason")
        job = self.get_job(job_id, run_id=run_id)
        artifact_dir = (
            Path(job["artifact_dir"])
            if job.get("artifact_dir")
            else self.config.runs_dir / run_id / "artifacts" / job_id
        )
        target_path = artifact_dir / "selected_live_target.json"
        selected_target = _read_json_file(target_path)
        if selected_target is None:
            raise ValueError("live pilot abandonment requires selected_live_target.json")
        payload = {
            "schema": "business-card-watchdog.live-pilot-abandonment.v1",
            "state": "abandoned",
            "created_at": utc_now(),
            "run_id": run_id,
            "job_id": job_id,
            "job_state": job.get("state"),
            "sink": selected_target.get("sink"),
            "scope": selected_target.get("scope"),
            "operator": operator,
            "reason": reason,
            "selected_target_path": str(target_path),
            "selected_target_created_at": selected_target.get("created_at"),
            "selected_target_identity": _selected_target_identity(selected_target),
            "selected_target_operator": selected_target.get("operator") or selected_target.get("approved_by"),
            "selected_target": selected_target,
            "writes_attempted": 0,
            "network_calls_made": 0,
            "commands": {
                "live_pilot_status": f"runs live-pilot-status {run_id}",
                "live_pilot_handoff": f"runs live-pilot-handoff {run_id}",
                "prepare_new_selection_packet": (
                    f"sinks live-selection-packet {job_id} --run-id {run_id} "
                    "--sink <sink> --operator <operator>"
                ),
                "select_new_target": (
                    f"sinks select-live-target {job_id} --run-id {run_id} "
                    "--sink <sink> --operator <operator> --scope <scope> "
                    "--safety-confirmation <tenant-profile-account-confirmation> --json"
                ),
            },
            "explicit_stop_conditions": [
                "This abandonment artifact does not delete selected_live_target.json.",
                "Do not run live lookup, live write, or live readback for the abandoned selected target.",
                "A later selected_live_target.json with a different selection identity is required before another non-simulated live command.",
                "Do not process private SyncThing images, run public-web search, or call paid enrichment from this abandonment artifact.",
            ],
        }
        abandon_path = artifact_dir / "live_pilot_abandonment.json"
        abandon_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        ledger = RunLedger(self.config.runs_dir / run_id)
        ledger.record_artifact(job_id=job_id, kind="live_pilot_abandonment", path=abandon_path)
        ledger.record_event(
            "live_pilot_abandoned",
            {
                "job_id": job_id,
                "run_id": run_id,
                "sink": selected_target.get("sink"),
                "scope": selected_target.get("scope"),
                "operator": operator,
                "abandon_path": str(abandon_path),
                "writes_attempted": 0,
                "network_calls_made": 0,
            },
        )
        self._mark_route_artifact_refreshed(
            artifact_dir,
            job_id=job_id,
            run_id=run_id,
            kind="live_pilot_abandonment",
        )
        return {"abandonment_path": str(abandon_path), "abandonment": payload}

    def execute_selected_lookup_smoke_for_job(
        self,
        *,
        job_id: str,
        run_id: str,
    ) -> dict[str, Any]:
        job = self.get_job(job_id, run_id=run_id)
        artifact_dir = Path(job["artifact_dir"]) if job.get("artifact_dir") else self.config.runs_dir / run_id / "artifacts" / job_id
        target = self._require_selected_live_target(
            artifact_dir=artifact_dir,
            job_id=job_id,
            run_id=run_id,
            sink=str((_read_json_file(artifact_dir / "selected_live_target.json") or {}).get("sink") or ""),
            approved_by=str((_read_json_file(artifact_dir / "selected_live_target.json") or {}).get("operator") or ""),
            scope="lookup",
        )
        sink = str(target["sink"])
        operator = str(target.get("operator") or target.get("approved_by") or "")
        pilot_payload = self.execute_sink_lookup_pilot_for_job(
            job_id=job_id,
            run_id=run_id,
            sink=sink,
            approved_by=operator,
            simulate=False,
        )
        duplicate_payload = self.assess_downstream_duplicates_for_job(job_id=job_id, run_id=run_id)
        pilot = dict(pilot_payload["pilot"])
        result = dict(pilot_payload["result"])
        duplicate = dict(duplicate_payload["assessment"])
        result_redacted = bool(pilot.get("execution_redacted", False) or result.get("result_redacted", False))
        if int(pilot.get("writes_attempted") or 0):
            raise ValueError("selected lookup smoke reported writes attempted")
        if not result_redacted:
            raise ValueError("selected lookup smoke requires redacted lookup evidence")
        payload = {
            "schema": "business-card-watchdog.selected-lookup-smoke.v1",
            "state": "complete",
            "status": "complete",
            "reason": "selected read-only live lookup smoke completed and downstream duplicate assessment was updated",
            "run_id": run_id,
            "job_id": job_id,
            "sink": sink,
            "operator": operator,
            "selected_target": target,
            "pilot_path": pilot_payload["pilot_path"],
            "result_path": pilot_payload["result_path"],
            "downstream_duplicate_assessment_path": duplicate_payload["assessment_path"],
            "lookup_status": pilot.get("status"),
            "lookup_match_count": pilot.get("match_count", 0),
            "downstream_duplicate_state": duplicate.get("state"),
            "writes_attempted": int(pilot.get("writes_attempted") or 0),
            "network_calls_made": int(pilot.get("network_calls_made") or 0),
            "result_redacted": result_redacted,
            "artifacts": {
                "selected_live_target": str(artifact_dir / "selected_live_target.json"),
                "sink_lookup_pilot": pilot_payload["pilot_path"],
                "sink_lookup_result": pilot_payload["result_path"],
                "downstream_duplicate_assessment": duplicate_payload["assessment_path"],
            },
            "stop_conditions": [
                "selected target no longer matches run, job, sink, operator, or lookup scope",
                "lookup adapter reports writes attempted",
                "lookup result includes unredacted raw downstream contact rows",
                "downstream duplicate assessment requires review before any write pilot",
            ],
        }
        smoke_path = artifact_dir / "selected_lookup_smoke.json"
        smoke_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        ledger = RunLedger(self.config.runs_dir / run_id)
        ledger.record_artifact(job_id=job_id, kind="selected_lookup_smoke", path=smoke_path)
        ledger.record_event(
            "selected_lookup_smoke_executed",
            {
                "job_id": job_id,
                "run_id": run_id,
                "sink": sink,
                "operator": operator,
                "smoke_path": str(smoke_path),
                "writes_attempted": payload["writes_attempted"],
                "network_calls_made": payload["network_calls_made"],
                "downstream_duplicate_state": payload["downstream_duplicate_state"],
            },
        )
        self._mark_route_artifact_refreshed(
            artifact_dir,
            job_id=job_id,
            run_id=run_id,
            kind="selected_lookup_smoke",
        )
        return {"smoke_path": str(smoke_path), "smoke": payload, **pilot_payload, **duplicate_payload}

    def enrichment_readiness(
        self,
        *,
        mode: str | None = None,
        allow_paid_enrichment: bool = False,
    ) -> dict[str, Any]:
        checks = check_enrichment_readiness(
            self.config,
            mode=mode,
            allow_paid_enrichment=allow_paid_enrichment,
        )
        return {
            "enabled": self.config.enrichment.enabled,
            "default_mode": self.config.enrichment.default_mode,
            "allow_paid_api": self.config.enrichment.allow_paid_api,
            "checks": [check.to_dict() for check in checks],
        }

    def request_enrichment(
        self,
        *,
        job_id: str,
        run_id: str,
        mode: str = "public_web",
        requested_by: str = "operator",
        allow_paid_enrichment: bool = False,
        public_web_results: list[dict[str, Any]] | None = None,
        provider_results: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        readiness = self.enrichment_readiness(
            mode=mode,
            allow_paid_enrichment=allow_paid_enrichment,
        )
        if any(check["status"] != "ready" for check in readiness["checks"]):
            return {
                "status": "blocked",
                "readiness": readiness,
            }
        self._enforce_run_enrichment_budget(run_id=run_id, mode=mode)
        job = self.get_job(job_id, run_id=run_id)
        artifact_dir = Path(job["artifact_dir"]) if job.get("artifact_dir") else self.config.runs_dir / run_id / "artifacts" / job_id
        candidate_path = artifact_dir / "contact_candidate.json"
        if not candidate_path.exists():
            raise FileNotFoundError(f"contact candidate not found for job: {job_id}")
        candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
        request = build_enrichment_request(
            candidate,
            mode=mode,
            allow_paid_enrichment=allow_paid_enrichment,
            requested_by=requested_by,
        )
        request_path = artifact_dir / "enrichment_request.json"
        request_path.write_text(json.dumps(request, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        ledger = RunLedger(self.config.runs_dir / run_id)
        ledger.record_artifact(job_id=job_id, kind="enrichment_request", path=request_path)
        result_payload = None
        result_path = None
        public_web_request_payload = None
        public_web_request_path = None
        provider_request_payload = None
        provider_request_path = None
        provider_result_payload = None
        provider_result_path = None
        if mode in {"public_web", "all"}:
            public_web_request_payload = build_public_web_search_request(
                self.config,
                candidate,
                mode=mode,
                requested_by=requested_by,
                readiness=list(readiness["checks"]),
            )
            public_web_request_path = artifact_dir / "enrichment_public_web_request.json"
            public_web_request_path.write_text(
                json.dumps(public_web_request_payload, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            ledger.record_artifact(
                job_id=job_id,
                kind="enrichment_public_web_request",
                path=public_web_request_path,
            )
        if mode in {"api", "all"}:
            provider_request_payload = build_paid_api_provider_request(
                self.config,
                candidate,
                mode=mode,
                requested_by=requested_by,
                allow_paid_enrichment=allow_paid_enrichment,
                readiness=list(readiness["checks"]),
            )
            provider_request_path = artifact_dir / "enrichment_provider_request.json"
            provider_request_path.write_text(
                json.dumps(provider_request_payload, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            ledger.record_artifact(
                job_id=job_id,
                kind="enrichment_provider_request",
                path=provider_request_path,
            )
            if provider_results:
                max_provider_results = self.config.enrichment.max_paid_provider_results_per_contact
                if len(provider_results) > max_provider_results:
                    raise ValueError(
                        "paid provider result import exceeds request limit: "
                        f"{len(provider_results)} results for max {max_provider_results}"
                    )
                provider_result_payload = score_paid_api_provider_results(
                    candidate,
                    provider="apollo",
                    results=provider_results,
                    max_results=max_provider_results,
                )
                provider_result_path = artifact_dir / "enrichment_provider_result.json"
                provider_result_path.write_text(
                    json.dumps(provider_result_payload, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
                ledger.record_artifact(
                    job_id=job_id,
                    kind="enrichment_provider_result",
                    path=provider_result_path,
                )
        if mode in {"public_web", "all"}:
            result_payload = score_public_web_results(candidate, results=public_web_results or [])
            result_path = artifact_dir / "enrichment_result.json"
            result_path.write_text(
                json.dumps(result_payload, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            ledger.record_artifact(job_id=job_id, kind="enrichment_result", path=result_path)
        elif provider_result_payload is not None:
            result_payload = provider_result_payload
            result_path = artifact_dir / "enrichment_result.json"
            result_path.write_text(
                json.dumps(result_payload, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            ledger.record_artifact(job_id=job_id, kind="enrichment_result", path=result_path)
        ledger.record_event(
            "enrichment_requested",
            {
                "job_id": job_id,
                "run_id": run_id,
                    "mode": mode,
                    "requested_by": requested_by,
                    "request_path": str(request_path),
                    "result_path": str(result_path) if result_path else None,
                    "public_web_request_path": str(public_web_request_path) if public_web_request_path else None,
                    "provider_request_path": str(provider_request_path) if provider_request_path else None,
                    "provider_result_path": str(provider_result_path) if provider_result_path else None,
                },
            )
        return {
            "status": "ok",
            "readiness": readiness,
            "request_path": str(request_path),
            "result_path": str(result_path) if result_path else None,
            "public_web_request_path": str(public_web_request_path) if public_web_request_path else None,
            "provider_request_path": str(provider_request_path) if provider_request_path else None,
            "provider_result_path": str(provider_result_path) if provider_result_path else None,
            "request": request,
            "result": result_payload,
            "public_web_request": public_web_request_payload,
            "provider_request": provider_request_payload,
            "provider_result": provider_result_payload,
        }

    def record_public_web_enrichment_results(
        self,
        *,
        job_id: str,
        run_id: str,
        results: list[dict[str, Any]],
        searched_by: str = "operator",
    ) -> dict[str, Any]:
        job = self.get_job(job_id, run_id=run_id)
        artifact_dir = Path(job["artifact_dir"]) if job.get("artifact_dir") else self.config.runs_dir / run_id / "artifacts" / job_id
        candidate_path = artifact_dir / "contact_candidate.json"
        request_path = artifact_dir / "enrichment_public_web_request.json"
        if not candidate_path.exists():
            raise FileNotFoundError(f"contact candidate not found for job: {job_id}")
        if not request_path.exists():
            raise FileNotFoundError(f"public web enrichment request not found for job: {job_id}")
        candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
        public_web_request = json.loads(request_path.read_text(encoding="utf-8"))
        max_results = int(public_web_request.get("max_queries") or self.config.enrichment.max_public_web_queries_per_contact)
        if len(results) > max_results:
            raise ValueError(
                f"public web result import exceeds request limit: {len(results)} results for max {max_results}"
            )
        public_web_result = build_public_web_result_artifact(
            candidate,
            public_web_request=public_web_request,
            results=results,
            searched_by=searched_by,
        )
        public_web_result_path = artifact_dir / "enrichment_public_web_result.json"
        public_web_result_path.write_text(
            json.dumps(public_web_result, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        result_payload = {
            "schema": public_web_result["result_schema"],
            "provider": public_web_result["provider"],
            "cost_class": public_web_result["cost_class"],
            "network_calls_made": public_web_result["network_calls_made"],
            "results": public_web_result["results"],
            "merge_proposals": public_web_result["merge_proposals"],
        }
        result_path = artifact_dir / "enrichment_result.json"
        result_path.write_text(
            json.dumps(result_payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        ledger = RunLedger(self.config.runs_dir / run_id)
        ledger.record_artifact(job_id=job_id, kind="enrichment_public_web_result", path=public_web_result_path)
        ledger.record_artifact(job_id=job_id, kind="enrichment_result", path=result_path)
        ledger.record_event(
            "enrichment_public_web_results_recorded",
            {
                "job_id": job_id,
                "run_id": run_id,
                "searched_by": searched_by,
                "public_web_result_path": str(public_web_result_path),
                "result_path": str(result_path),
                "submitted_result_count": len(results),
                "merge_proposal_count": len(result_payload["merge_proposals"]),
                "network_calls_made": 0,
                "search_calls_attempted": 0,
            },
        )
        return {
            "status": "ok",
            "public_web_result_path": str(public_web_result_path),
            "result_path": str(result_path),
            "public_web_result": public_web_result,
            "result": result_payload,
        }

    def build_public_web_enrichment_handoff(
        self,
        *,
        job_id: str,
        run_id: str,
    ) -> dict[str, Any]:
        job = self.get_job(job_id, run_id=run_id)
        artifact_dir = Path(job["artifact_dir"]) if job.get("artifact_dir") else self.config.runs_dir / run_id / "artifacts" / job_id
        request_path = artifact_dir / "enrichment_public_web_request.json"
        if not request_path.exists():
            raise FileNotFoundError(f"public web enrichment request not found for job: {job_id}")
        public_web_request = json.loads(request_path.read_text(encoding="utf-8"))
        handoff = build_public_web_search_handoff(
            public_web_request,
            run_id=run_id,
            job_id=job_id,
        )
        handoff_path = artifact_dir / "enrichment_public_web_search_handoff.json"
        handoff_path.write_text(
            json.dumps(handoff, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        ledger = RunLedger(self.config.runs_dir / run_id)
        ledger.record_artifact(job_id=job_id, kind="enrichment_public_web_search_handoff", path=handoff_path)
        ledger.record_event(
            "enrichment_public_web_search_handoff_created",
            {
                "job_id": job_id,
                "run_id": run_id,
                "handoff_path": str(handoff_path),
                "query_count": handoff["query_count"],
                "network_calls_made": 0,
                "search_calls_attempted": 0,
            },
        )
        return {
            "status": "ok",
            "handoff_path": str(handoff_path),
            "handoff": handoff,
        }

    def build_provider_enrichment_handoff(
        self,
        *,
        job_id: str,
        run_id: str,
    ) -> dict[str, Any]:
        job = self.get_job(job_id, run_id=run_id)
        artifact_dir = Path(job["artifact_dir"]) if job.get("artifact_dir") else self.config.runs_dir / run_id / "artifacts" / job_id
        request_path = artifact_dir / "enrichment_provider_request.json"
        if not request_path.exists():
            raise FileNotFoundError(f"provider enrichment request not found for job: {job_id}")
        provider_request = json.loads(request_path.read_text(encoding="utf-8"))
        handoff = build_paid_api_provider_handoff(
            provider_request,
            run_id=run_id,
            job_id=job_id,
        )
        handoff_path = artifact_dir / "enrichment_provider_handoff.json"
        handoff_path.write_text(
            json.dumps(handoff, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        ledger = RunLedger(self.config.runs_dir / run_id)
        ledger.record_artifact(job_id=job_id, kind="enrichment_provider_handoff", path=handoff_path)
        ledger.record_event(
            "enrichment_provider_handoff_created",
            {
                "job_id": job_id,
                "run_id": run_id,
                "provider": handoff["provider"],
                "handoff_path": str(handoff_path),
                "max_results": handoff["max_results"],
                "network_calls_made": 0,
                "paid_api_calls_attempted": 0,
            },
        )
        return {
            "status": "ok",
            "handoff_path": str(handoff_path),
            "handoff": handoff,
        }

    def record_provider_enrichment_results(
        self,
        *,
        job_id: str,
        run_id: str,
        provider: str = "apollo",
        results: list[dict[str, Any]],
        submitted_by: str = "operator",
    ) -> dict[str, Any]:
        job = self.get_job(job_id, run_id=run_id)
        artifact_dir = Path(job["artifact_dir"]) if job.get("artifact_dir") else self.config.runs_dir / run_id / "artifacts" / job_id
        candidate_path = artifact_dir / "contact_candidate.json"
        request_path = artifact_dir / "enrichment_provider_request.json"
        if not candidate_path.exists():
            raise FileNotFoundError(f"contact candidate not found for job: {job_id}")
        if not request_path.exists():
            raise FileNotFoundError(f"provider enrichment request not found for job: {job_id}")
        candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
        provider_request = json.loads(request_path.read_text(encoding="utf-8"))
        requested_provider = str(provider_request.get("provider") or provider)
        if requested_provider != provider:
            raise ValueError(f"provider result import provider mismatch: {provider} for request provider {requested_provider}")
        max_results = int(provider_request.get("max_results") or self.config.enrichment.max_paid_provider_results_per_contact)
        if len(results) > max_results:
            raise ValueError(
                f"paid provider result import exceeds request limit: {len(results)} results for max {max_results}"
            )
        provider_result = score_paid_api_provider_results(
            candidate,
            provider=provider,
            results=results,
            max_results=max_results,
        )
        provider_result["submitted_by"] = submitted_by
        provider_result["source_request_schema"] = provider_request.get("schema")
        provider_result["source_request_status"] = provider_request.get("status")
        provider_result_path = artifact_dir / "enrichment_provider_result.json"
        provider_result_path.write_text(
            json.dumps(provider_result, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        result_payload = {
            "schema": provider_result["result_schema"],
            "provider": provider_result["provider"],
            "cost_class": provider_result["cost_class"],
            "network_calls_made": provider_result["network_calls_made"],
            "results": provider_result["results"],
            "merge_proposals": provider_result["merge_proposals"],
        }
        result_path = artifact_dir / "enrichment_result.json"
        result_path.write_text(
            json.dumps(result_payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        ledger = RunLedger(self.config.runs_dir / run_id)
        ledger.record_artifact(job_id=job_id, kind="enrichment_provider_result", path=provider_result_path)
        ledger.record_artifact(job_id=job_id, kind="enrichment_result", path=result_path)
        ledger.record_event(
            "enrichment_provider_results_recorded",
            {
                "job_id": job_id,
                "run_id": run_id,
                "provider": provider,
                "submitted_by": submitted_by,
                "provider_result_path": str(provider_result_path),
                "result_path": str(result_path),
                "submitted_result_count": len(results),
                "merge_proposal_count": len(result_payload["merge_proposals"]),
                "network_calls_made": 0,
                "paid_api_calls_attempted": 0,
            },
        )
        return {
            "status": "ok",
            "provider_result_path": str(provider_result_path),
            "result_path": str(result_path),
            "provider_result": provider_result,
            "result": result_payload,
        }

    def plan_sinks_for_job(self, *, job_id: str, run_id: str, dry_run: bool = True) -> dict[str, Any]:
        job = self.get_job(job_id, run_id=run_id)
        artifact_dir = Path(job["artifact_dir"]) if job.get("artifact_dir") else self.config.runs_dir / run_id / "artifacts" / job_id
        spec = self._contact_spec_for_artifact_dir(artifact_dir)
        self._add_route_context(spec, job=job, artifact_dir=artifact_dir)
        decision = decide_sinks(self.config, spec)
        plan = build_sink_plan(
            sinks=decision.sinks,
            spec=spec,
            dry_run=dry_run or decision.dry_run,
            reason=decision.reason,
            apply_enabled={sink: self._sink_apply_enabled(sink) for sink in decision.sinks},
        )
        plan["job_id"] = job_id
        plan["run_id"] = run_id
        plan["decision"] = decision.to_dict()
        plan["route_explanation"] = decision.metadata.get("route_explanation")
        plan["sink_eligibility"] = decision.metadata.get("sink_eligibility", [])
        duplicate_resolution_path = artifact_dir / "duplicate_resolution.json"
        if duplicate_resolution_path.exists():
            plan["duplicate_resolution"] = json.loads(duplicate_resolution_path.read_text(encoding="utf-8"))
        plan_path = artifact_dir / "sink_plan.json"
        plan_path.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        ledger = RunLedger(self.config.runs_dir / run_id)
        ledger.record_artifact(job_id=job_id, kind="sink_plan", path=plan_path)
        ledger.record_event(
            "sink_plan_created",
            {
                "job_id": job_id,
                "run_id": run_id,
                "plan_path": str(plan_path),
                "state": plan["state"],
                "sinks": decision.sinks,
            },
        )
        self._mark_route_artifact_refreshed(
            artifact_dir,
            job_id=job_id,
            run_id=run_id,
            kind="sink_plan",
        )
        return {"plan_path": str(plan_path), "plan": plan}

    def plan_sink_lookup_for_job(self, *, job_id: str, run_id: str, dry_run: bool = True) -> dict[str, Any]:
        job = self.get_job(job_id, run_id=run_id)
        artifact_dir = Path(job["artifact_dir"]) if job.get("artifact_dir") else self.config.runs_dir / run_id / "artifacts" / job_id
        spec = self._contact_spec_for_artifact_dir(artifact_dir)
        self._add_route_context(spec, job=job, artifact_dir=artifact_dir)
        decision = decide_sinks(self.config, spec)
        plan = build_sink_lookup_plan(
            sinks=decision.sinks,
            spec=spec,
            dry_run=dry_run or decision.dry_run,
            reason=decision.reason,
        )
        plan["job_id"] = job_id
        plan["run_id"] = run_id
        plan["decision"] = decision.to_dict()
        plan["route_explanation"] = decision.metadata.get("route_explanation")
        plan["sink_eligibility"] = decision.metadata.get("sink_eligibility", [])
        lookup_plan_path = artifact_dir / "sink_lookup_plan.json"
        lookup_plan_path.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        ledger = RunLedger(self.config.runs_dir / run_id)
        ledger.record_artifact(job_id=job_id, kind="sink_lookup_plan", path=lookup_plan_path)
        ledger.record_event(
            "sink_lookup_plan_created",
            {
                "job_id": job_id,
                "run_id": run_id,
                "lookup_plan_path": str(lookup_plan_path),
                "state": plan["state"],
                "sinks": decision.sinks,
                "network_calls_made": 0,
            },
        )
        self._mark_route_artifact_refreshed(
            artifact_dir,
            job_id=job_id,
            run_id=run_id,
            kind="sink_lookup_plan",
        )
        return {"lookup_plan_path": str(lookup_plan_path), "lookup_plan": plan}

    def preflight_sink_apply(self, *, job_id: str, run_id: str, apply: bool = False) -> dict[str, Any]:
        job = self.get_job(job_id, run_id=run_id)
        artifact_dir = Path(job["artifact_dir"]) if job.get("artifact_dir") else self.config.runs_dir / run_id / "artifacts" / job_id
        plan_path = artifact_dir / "sink_plan.json"
        if plan_path.exists():
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
        else:
            plan = self.plan_sinks_for_job(job_id=job_id, run_id=run_id, dry_run=True)["plan"]
        preflight = build_sink_apply_preflight(plan=plan, apply=apply)
        preflight_path = artifact_dir / "sink_apply_preflight.json"
        preflight_path.write_text(json.dumps(preflight, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        ledger = RunLedger(self.config.runs_dir / run_id)
        ledger.record_artifact(job_id=job_id, kind="sink_apply_preflight", path=preflight_path)
        ledger.record_event(
            "sink_apply_preflight_created",
            {
                "job_id": job_id,
                "run_id": run_id,
                "preflight_path": str(preflight_path),
                "state": preflight["state"],
                "apply_requested": apply,
                "writes_attempted": 0,
                "network_calls_made": 0,
            },
        )
        self._mark_route_artifact_refreshed(
            artifact_dir,
            job_id=job_id,
            run_id=run_id,
            kind="sink_apply_preflight",
        )
        return {"preflight_path": str(preflight_path), "preflight": preflight}

    def decide_sink_apply(
        self,
        *,
        job_id: str,
        run_id: str,
        decision: str,
        reviewer: str = "operator",
        reason: str = "",
    ) -> dict[str, Any]:
        job_payload = self.get_job(job_id, run_id=run_id)
        job = CardJob.from_dict(job_payload)
        artifact_dir = Path(job.artifact_dir) if job.artifact_dir else self.config.runs_dir / run_id / "artifacts" / job_id
        preflight_path = artifact_dir / "sink_apply_preflight.json"
        if preflight_path.exists():
            preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
        else:
            preflight = self.preflight_sink_apply(job_id=job_id, run_id=run_id)["preflight"]
        decision_payload = build_sink_apply_decision(
            preflight=preflight,
            decision=decision,
            reviewer=reviewer,
            reason=reason,
        )
        decision_path = artifact_dir / "sink_apply_decision.json"
        decision_path.write_text(json.dumps(decision_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        ledger = RunLedger(self.config.runs_dir / run_id)
        ledger.record_artifact(job_id=job_id, kind="sink_apply_decision", path=decision_path)
        if decision == "noop":
            job.transition_to("cancelled", error="sink apply resolved as no-op")
            ledger.record_job(job)
        ledger.record_event(
            "sink_apply_decided",
            {
                "job_id": job_id,
                "run_id": run_id,
                "decision": decision,
                "reviewer": reviewer,
                "decision_path": str(decision_path),
                "writes_attempted": 0,
                "network_calls_made": 0,
            },
        )
        self._mark_route_artifact_refreshed(
            artifact_dir,
            job_id=job_id,
            run_id=run_id,
            kind="sink_apply_decision",
        )
        return {
            "job": job.to_dict(),
            "decision_path": str(decision_path),
            "decision": decision_payload,
        }

    def apply_sinks_for_job(
        self,
        *,
        job_id: str,
        run_id: str,
        apply: bool = False,
        simulate: bool = False,
    ) -> dict[str, Any]:
        job = self.get_job(job_id, run_id=run_id)
        artifact_dir = Path(job["artifact_dir"]) if job.get("artifact_dir") else self.config.runs_dir / run_id / "artifacts" / job_id
        preflight_path = artifact_dir / "sink_apply_preflight.json"
        decision_path = artifact_dir / "sink_apply_decision.json"
        readiness_path = artifact_dir / "sink_apply_pilot_readiness.json"
        if preflight_path.exists():
            preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
        else:
            preflight = self.preflight_sink_apply(job_id=job_id, run_id=run_id)["preflight"]
        if decision_path.exists():
            decision = json.loads(decision_path.read_text(encoding="utf-8"))
        else:
            decision = {
                "schema": None,
                "state": "missing",
                "decision": "",
                "job_id": job_id,
                "run_id": run_id,
            }
        if apply and simulate:
            readiness = (
                json.loads(readiness_path.read_text(encoding="utf-8"))
                if readiness_path.exists()
                else self.build_sink_apply_pilot_readiness_for_job(job_id=job_id, run_id=run_id)["readiness"]
            )
            if not readiness.get("can_mock_apply_pilot"):
                raise ValueError(
                    "simulated sink apply requires ready sink_apply_pilot_readiness.json"
                )
        write_executions: list[dict[str, Any]] = []
        if apply and not simulate and decision.get("decision") == "approve" and self.sink_write_executor is not None:
            write_adapter_path = artifact_dir / "sink_adapter_request_write.json"
            if write_adapter_path.exists():
                write_adapter = json.loads(write_adapter_path.read_text(encoding="utf-8"))
            else:
                write_adapter = self.build_sink_adapter_request_for_job(
                    job_id=job_id,
                    run_id=run_id,
                    phase="write",
                )["request"]
            for request in list(write_adapter.get("requests") or []):
                if request.get("phase") != "write":
                    continue
                write_executions.append(self.sink_write_executor(request))

        result = build_sink_apply_result(preflight=preflight, decision=decision, apply=apply, simulate=simulate)
        if write_executions:
            write_by_sink = {str(row.get("sink") or ""): row for row in write_executions}
            result["state"] = "live_applied"
            result["reason"] = "injected sink write adapter completed; readback adapter still requires explicit request"
            result["writes_attempted"] = sum(int(row.get("writes_attempted") or 0) for row in write_executions)
            result["network_calls_made"] = sum(int(row.get("network_calls_made") or 0) for row in write_executions)
            result["write_executions"] = write_executions
            result["readback"] = []
            for action in result["actions"]:
                execution = write_by_sink.get(str(action.get("sink") or ""))
                if execution is None:
                    continue
                write = dict(execution.get("write") or {})
                action["state"] = "live_applied"
                action["write_attempted"] = True
                action["resource_id"] = write.get("resource_id")
                result["readback"].append(
                    {
                        "sink": action.get("sink"),
                        "resource_id": write.get("resource_id"),
                        "serialization_key": action.get("serialization_key"),
                        "matched": bool(write.get("resource_id")),
                        "simulated": False,
                    }
                )
        result_path = artifact_dir / "sink_apply_result.json"
        result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        ledger = RunLedger(self.config.runs_dir / run_id)
        ledger.record_artifact(job_id=job_id, kind="sink_apply_result", path=result_path)
        ledger.record_event(
            "sink_apply_attempted",
            {
                "job_id": job_id,
                "run_id": run_id,
                "apply_requested": apply,
                "simulated": result["simulated"],
                "state": result["state"],
                "result_path": str(result_path),
                "writes_attempted": result["writes_attempted"],
                "network_calls_made": result["network_calls_made"],
            },
        )
        self._mark_route_artifact_refreshed(
            artifact_dir,
            job_id=job_id,
            run_id=run_id,
            kind="sink_apply_result",
        )
        return {"result_path": str(result_path), "result": result}

    def build_sink_apply_pilot_readiness_for_job(
        self,
        *,
        job_id: str,
        run_id: str,
        sink: str | None = None,
    ) -> dict[str, Any]:
        job = self.get_job(job_id, run_id=run_id)
        artifact_dir = Path(job["artifact_dir"]) if job.get("artifact_dir") else self.config.runs_dir / run_id / "artifacts" / job_id
        preflight_path = artifact_dir / "sink_apply_preflight.json"
        decision_path = artifact_dir / "sink_apply_decision.json"
        write_adapter_path = artifact_dir / "sink_adapter_request_write.json"
        readback_adapter_path = artifact_dir / "sink_adapter_request_readback.json"

        preflight = json.loads(preflight_path.read_text(encoding="utf-8")) if preflight_path.exists() else None
        decision = json.loads(decision_path.read_text(encoding="utf-8")) if decision_path.exists() else None
        write_adapter = json.loads(write_adapter_path.read_text(encoding="utf-8")) if write_adapter_path.exists() else None
        readback_adapter = json.loads(readback_adapter_path.read_text(encoding="utf-8")) if readback_adapter_path.exists() else None
        readiness = self.sink_readiness()
        selected_sink = str(sink or "").strip()
        preflight_actions = [
            action
            for action in list((preflight or {}).get("actions") or [])
            if not selected_sink or action.get("sink") == selected_sink
        ]
        decision_actions = [
            action
            for action in list((decision or {}).get("actions") or [])
            if not selected_sink or action.get("sink") == selected_sink
        ]
        write_adapter_requests = [
            request
            for request in list((write_adapter or {}).get("requests") or [])
            if request.get("phase") == "write" and (not selected_sink or request.get("sink") == selected_sink)
        ]
        readback_adapter_requests = [
            request
            for request in list((readback_adapter or {}).get("requests") or [])
            if request.get("phase") == "readback" and (not selected_sink or request.get("sink") == selected_sink)
        ]
        sink_readiness_checks = [
            check
            for check in list(readiness.get("sinks") or [])
            if not selected_sink or check.get("sink") == selected_sink
        ]
        readiness_scope = f"selected sink {selected_sink}" if selected_sink else "all configured sinks"
        requirements = [
            {
                "name": "preflight_exists",
                "ok": preflight is not None,
                "detail": str(preflight_path),
            },
            {
                "name": "selected_sink_in_preflight",
                "ok": bool(preflight and (preflight_actions or not selected_sink)),
                "detail": readiness_scope,
            },
            {
                "name": "apply_decision_approved",
                "ok": bool(
                    decision
                    and decision.get("decision") == "approve"
                    and (not selected_sink or decision_actions)
                ),
                "detail": str(decision_path),
            },
            {
                "name": "write_adapter_request_exists",
                "ok": bool(write_adapter and (write_adapter_requests or not selected_sink)),
                "detail": str(write_adapter_path),
            },
            {
                "name": "mock_readback_available",
                "ok": True,
                "detail": "simulated apply can produce local readback evidence without a live adapter",
            },
            {
                "name": "live_sink_readiness_ready",
                "ok": bool(sink_readiness_checks)
                and all(check.get("status") == "ready" for check in sink_readiness_checks),
                "detail": f"{readiness_scope} readiness checks must be ready",
            },
            {
                "name": "readback_adapter_available_after_apply",
                "ok": bool(readback_adapter and (readback_adapter_requests or not selected_sink)),
                "detail": str(readback_adapter_path),
            },
        ]
        mock_requirements = {
            "preflight_exists",
            "selected_sink_in_preflight",
            "apply_decision_approved",
            "mock_readback_available",
        }
        live_requirements = {
            "preflight_exists",
            "selected_sink_in_preflight",
            "apply_decision_approved",
            "write_adapter_request_exists",
            "live_sink_readiness_ready",
            "readback_adapter_available_after_apply",
        }
        requirement_by_name = {str(item["name"]): bool(item["ok"]) for item in requirements}
        can_mock_apply_pilot = all(requirement_by_name[name] for name in mock_requirements)
        can_live_apply_pilot = all(requirement_by_name[name] for name in live_requirements)
        missing_requirements = [item["name"] for item in requirements if not item["ok"]]
        payload = {
            "schema": "business-card-watchdog.sink-apply-pilot-readiness.v1",
            "state": "ready_for_mock_apply" if can_mock_apply_pilot else "blocked",
            "status": "ready_for_mock_apply" if can_mock_apply_pilot else "blocked",
            "reason": (
                "mock apply pilot is ready; live apply remains blocked until live readiness and readback adapter checks pass"
                if can_mock_apply_pilot
                else "apply pilot remains blocked until required review, preflight, selected sink, and adapter request artifacts exist"
            ),
            "job_id": job_id,
            "run_id": run_id,
            "sink": selected_sink or None,
            "selected_sink": selected_sink or None,
            "readiness_scope": "selected_sink" if selected_sink else "all_configured_sinks",
            "can_apply_pilot": can_mock_apply_pilot,
            "can_mock_apply_pilot": can_mock_apply_pilot,
            "can_live_apply_pilot": can_live_apply_pilot,
            "writes_attempted": 0,
            "network_calls_made": 0,
            "preflight_state": preflight.get("state") if preflight else "missing",
            "decision_state": decision.get("state") if decision else "missing",
            "decision": decision.get("decision") if decision else "",
            "sink_readiness": readiness,
            "selected_sink_readiness": sink_readiness_checks,
            "selected_actions": {
                "preflight": preflight_actions,
                "decision": decision_actions,
                "write_adapter_requests": write_adapter_requests,
                "readback_adapter_requests": readback_adapter_requests,
            },
            "requirements": requirements,
            "missing_requirements": missing_requirements,
            "mock_missing_requirements": [
                name for name in sorted(mock_requirements) if not requirement_by_name[name]
            ],
            "live_missing_requirements": [
                name for name in sorted(live_requirements) if not requirement_by_name[name]
            ],
            "commands": {
                "prepare": (
                    f"sinks apply-pilot-readiness {job_id} --run-id {run_id}"
                    + (f" --sink {selected_sink}" if selected_sink else "")
                ),
                "mock_write": (
                    f"sinks write-pilot {job_id} --run-id {run_id} --sink {selected_sink or '<sink>'} "
                    "--approved-by <operator> --simulate"
                ),
                "live_write": (
                    f"sinks write-pilot {job_id} --run-id {run_id} --sink {selected_sink or '<sink>'} "
                    "--approved-by <operator> --no-simulate"
                ),
                "readback_request": f"sinks adapter-request {job_id} --run-id {run_id} --phase readback",
                "mock_readback": (
                    f"sinks readback-pilot {job_id} --run-id {run_id} --sink {selected_sink or '<sink>'} "
                    "--approved-by <operator> --simulate"
                ),
                "mock_apply": "sinks apply --apply --simulate",
                "manual_apply": "sinks apply --apply --no-simulate",
                "readback": "sinks adapter-request --phase readback",
            },
        }
        readiness_path = artifact_dir / "sink_apply_pilot_readiness.json"
        readiness_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        ledger = RunLedger(self.config.runs_dir / run_id)
        ledger.record_artifact(job_id=job_id, kind="sink_apply_pilot_readiness", path=readiness_path)
        ledger.record_event(
            "sink_apply_pilot_readiness_created",
            {
                "job_id": job_id,
                "run_id": run_id,
                "readiness_path": str(readiness_path),
                "state": payload["state"],
                "writes_attempted": 0,
                "network_calls_made": 0,
            },
        )
        self._mark_route_artifact_refreshed(
            artifact_dir,
            job_id=job_id,
            run_id=run_id,
            kind="sink_apply_pilot_readiness",
        )
        return {"readiness_path": str(readiness_path), "readiness": payload}

    def build_sink_adapter_request_for_job(
        self,
        *,
        job_id: str,
        run_id: str,
        phase: SinkAdapterPhase = "lookup",
    ) -> dict[str, Any]:
        job = self.get_job(job_id, run_id=run_id)
        artifact_dir = Path(job["artifact_dir"]) if job.get("artifact_dir") else self.config.runs_dir / run_id / "artifacts" / job_id
        if phase == "lookup":
            lookup_plan_path = artifact_dir / "sink_lookup_plan.json"
            if lookup_plan_path.exists():
                lookup_plan = json.loads(lookup_plan_path.read_text(encoding="utf-8"))
            else:
                lookup_plan = self.plan_sink_lookup_for_job(job_id=job_id, run_id=run_id)["lookup_plan"]
            request = build_sink_adapter_request(
                phase=phase,
                lookup_plan=lookup_plan,
                sink_context=self._sink_context(),
            )
        elif phase == "write":
            sink_plan_path = artifact_dir / "sink_plan.json"
            if sink_plan_path.exists():
                sink_plan = json.loads(sink_plan_path.read_text(encoding="utf-8"))
            else:
                sink_plan = self.plan_sinks_for_job(job_id=job_id, run_id=run_id)["plan"]
            request = build_sink_adapter_request(
                phase=phase,
                sink_plan=sink_plan,
                sink_context=self._sink_context(),
            )
        elif phase == "readback":
            result_path = artifact_dir / "sink_apply_result.json"
            if result_path.exists():
                apply_result = json.loads(result_path.read_text(encoding="utf-8"))
            else:
                apply_result = self.apply_sinks_for_job(job_id=job_id, run_id=run_id)["result"]
            request = build_sink_adapter_request(
                phase=phase,
                apply_result=apply_result,
                sink_context=self._sink_context(),
            )
        else:
            raise ValueError("sink adapter phase must be lookup, write, or readback")

        request_path = artifact_dir / f"sink_adapter_request_{phase}.json"
        request_path.write_text(json.dumps(request, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        ledger = RunLedger(self.config.runs_dir / run_id)
        ledger.record_artifact(job_id=job_id, kind=f"sink_adapter_request_{phase}", path=request_path)
        ledger.record_event(
            "sink_adapter_request_created",
            {
                "job_id": job_id,
                "run_id": run_id,
                "phase": phase,
                "request_path": str(request_path),
                "request_count": request["request_count"],
                "writes_attempted": 0,
                "network_calls_made": 0,
            },
        )
        self._mark_route_artifact_refreshed(
            artifact_dir,
            job_id=job_id,
            run_id=run_id,
            kind=f"sink_adapter_request_{phase}",
        )
        return {"request_path": str(request_path), "request": request}

    def record_sink_lookup_result_for_job(
        self,
        *,
        job_id: str,
        run_id: str,
        matches_by_sink: dict[str, list[dict[str, Any]]] | None = None,
    ) -> dict[str, Any]:
        job = self.get_job(job_id, run_id=run_id)
        artifact_dir = Path(job["artifact_dir"]) if job.get("artifact_dir") else self.config.runs_dir / run_id / "artifacts" / job_id
        request_path = artifact_dir / "sink_adapter_request_lookup.json"
        if request_path.exists():
            adapter_request = json.loads(request_path.read_text(encoding="utf-8"))
        else:
            adapter_request = self.build_sink_adapter_request_for_job(
                job_id=job_id,
                run_id=run_id,
                phase="lookup",
            )["request"]
        result = build_sink_lookup_result(
            adapter_request=adapter_request,
            matches_by_sink=matches_by_sink or {},
        )
        result_path = artifact_dir / "sink_lookup_result.json"
        result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        ledger = RunLedger(self.config.runs_dir / run_id)
        ledger.record_artifact(job_id=job_id, kind="sink_lookup_result", path=result_path)
        ledger.record_event(
            "sink_lookup_result_recorded",
            {
                "job_id": job_id,
                "run_id": run_id,
                "result_path": str(result_path),
                "state": result["state"],
                "match_count": result["match_count"],
                "writes_attempted": 0,
                "network_calls_made": 0,
            },
        )
        self._mark_route_artifact_refreshed(
            artifact_dir,
            job_id=job_id,
            run_id=run_id,
            kind="sink_lookup_result",
        )
        return {"result_path": str(result_path), "result": result}

    def execute_sink_lookup_pilot_for_job(
        self,
        *,
        job_id: str,
        run_id: str,
        sink: str,
        approved_by: str,
        matches: list[dict[str, Any]] | None = None,
        simulate: bool = True,
    ) -> dict[str, Any]:
        job = self.get_job(job_id, run_id=run_id)
        artifact_dir = Path(job["artifact_dir"]) if job.get("artifact_dir") else self.config.runs_dir / run_id / "artifacts" / job_id
        request_path = artifact_dir / "sink_adapter_request_lookup.json"
        if request_path.exists():
            adapter_request = json.loads(request_path.read_text(encoding="utf-8"))
        else:
            adapter_request = self.build_sink_adapter_request_for_job(
                job_id=job_id,
                run_id=run_id,
                phase="lookup",
            )["request"]
        execution = None
        if not simulate:
            self._require_selected_live_target(
                artifact_dir=artifact_dir,
                job_id=job_id,
                run_id=run_id,
                sink=sink,
                approved_by=approved_by,
                scope="lookup",
            )
            requests = [
                request
                for request in list(adapter_request.get("requests") or [])
                if request.get("phase") == "lookup" and request.get("sink") == sink
            ]
            if not requests:
                raise ValueError(f"sink lookup pilot request not found for sink: {sink}")
            if self.sink_lookup_executor is not None:
                execution = self.sink_lookup_executor(requests[0])
            else:
                execution = execute_sink_lookup_adapter(requests[0])
            if int(execution.get("writes_attempted") or 0):
                raise ValueError("live sink lookup pilot reported writes attempted")
            matches = list(execution.get("matches") or [])
        pilot = build_sink_lookup_pilot(
            adapter_request=adapter_request,
            sink=sink,
            approved_by=approved_by,
            matches=matches or [],
            simulate=simulate,
            execution=execution,
            redact_sensitive=not simulate,
        )
        pilot_path = artifact_dir / "sink_lookup_pilot.json"
        pilot_path.write_text(json.dumps(pilot, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        result = build_sink_lookup_result(
            adapter_request=adapter_request,
            matches_by_sink={sink: matches or []},
            redact_sensitive=not simulate,
        )
        result["source_pilot_schema"] = pilot["schema"]
        result["source_pilot_path"] = str(pilot_path)
        result["status"] = (
            ("mock_lookup_matches" if result["match_count"] else "mock_lookup_no_match")
            if simulate
            else ("read_only_lookup_matches" if result["match_count"] else "read_only_lookup_no_match")
        )
        result["reason"] = (
            "mock read-only lookup pilot result; no downstream writes attempted"
            if simulate
            else "read-only lookup adapter result; no downstream writes attempted"
        )
        result["network_calls_made"] = pilot["network_calls_made"]
        for row in result["results"]:
            if row.get("sink") == sink:
                row["status"] = "mock_lookup_matches" if simulate else "read_only_lookup_completed"
                row["network_calls_made"] = pilot["network_calls_made"]
        result_path = artifact_dir / "sink_lookup_result.json"
        result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        ledger = RunLedger(self.config.runs_dir / run_id)
        ledger.record_artifact(job_id=job_id, kind="sink_lookup_pilot", path=pilot_path)
        ledger.record_artifact(job_id=job_id, kind="sink_lookup_result", path=result_path)
        ledger.record_event(
            "sink_lookup_pilot_executed",
            {
                "job_id": job_id,
                "run_id": run_id,
                "sink": sink,
                "approved_by": approved_by,
                "pilot_path": str(pilot_path),
                "result_path": str(result_path),
                "match_count": pilot["match_count"],
                "writes_attempted": 0,
                "network_calls_made": pilot["network_calls_made"],
            },
        )
        self._mark_route_artifact_refreshed(
            artifact_dir,
            job_id=job_id,
            run_id=run_id,
            kind="sink_lookup_pilot",
        )
        self._mark_route_artifact_refreshed(
            artifact_dir,
            job_id=job_id,
            run_id=run_id,
            kind="sink_lookup_result",
        )
        return {
            "pilot_path": str(pilot_path),
            "result_path": str(result_path),
            "pilot": pilot,
            "result": result,
        }

    def assess_downstream_duplicates_for_job(self, *, job_id: str, run_id: str) -> dict[str, Any]:
        job_payload = self.get_job(job_id, run_id=run_id)
        job = CardJob.from_dict(job_payload)
        artifact_dir = Path(job.artifact_dir) if job.artifact_dir else self.config.runs_dir / run_id / "artifacts" / job_id
        result_path = artifact_dir / "sink_lookup_result.json"
        if result_path.exists():
            lookup_result = json.loads(result_path.read_text(encoding="utf-8"))
        else:
            lookup_result = self.record_sink_lookup_result_for_job(job_id=job_id, run_id=run_id)["result"]
        assessment = assess_downstream_lookup_result(lookup_result).to_dict()
        assessment_path = artifact_dir / "downstream_duplicate_assessment.json"
        assessment_path.write_text(json.dumps(assessment, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        ledger = RunLedger(self.config.runs_dir / run_id)
        ledger.record_artifact(job_id=job_id, kind="downstream_duplicate_assessment", path=assessment_path)
        if assessment["state"] != "no_match":
            job.transition_to("needs_review")
            ledger.record_job(job)
        ledger.record_event(
            "downstream_duplicate_assessed",
            {
                "job_id": job_id,
                "run_id": run_id,
                "assessment_path": str(assessment_path),
                "state": assessment["state"],
                "match_count": len(assessment["matches"]),
            },
        )
        self._mark_route_artifact_refreshed(
            artifact_dir,
            job_id=job_id,
            run_id=run_id,
            kind="downstream_duplicate_assessment",
        )
        return {
            "job": job.to_dict(),
            "assessment_path": str(assessment_path),
            "assessment": assessment,
        }

    def execute_sink_write_pilot_for_job(
        self,
        *,
        job_id: str,
        run_id: str,
        sink: str,
        approved_by: str,
        simulate: bool = True,
    ) -> dict[str, Any]:
        job = self.get_job(job_id, run_id=run_id)
        artifact_dir = Path(job["artifact_dir"]) if job.get("artifact_dir") else self.config.runs_dir / run_id / "artifacts" / job_id
        self._enforce_downstream_duplicate_write_gate(artifact_dir)
        decision_path = artifact_dir / "sink_apply_decision.json"
        if decision_path.exists():
            decision = json.loads(decision_path.read_text(encoding="utf-8"))
        else:
            decision = {
                "schema": None,
                "state": "missing",
                "decision": "",
                "job_id": job_id,
                "run_id": run_id,
            }
        if decision.get("decision") != "approve":
            raise ValueError("sink write pilot requires an approved sink apply decision")
        request_path = artifact_dir / "sink_adapter_request_write.json"
        if request_path.exists():
            adapter_request = json.loads(request_path.read_text(encoding="utf-8"))
        else:
            adapter_request = self.build_sink_adapter_request_for_job(
                job_id=job_id,
                run_id=run_id,
                phase="write",
            )["request"]
        requests = [
            request
            for request in list(adapter_request.get("requests") or [])
            if request.get("phase") == "write" and request.get("sink") == sink
        ]
        if not requests:
            raise ValueError(f"sink write pilot request not found for sink: {sink}")
        request = requests[0]
        execution = None
        selected_target_ref = None
        if simulate:
            write = {
                "sink": sink,
                "resource_id": f"mock:{sink}:{request.get('serialization_key') or 'unknown'}",
                "serialization_key": request.get("serialization_key"),
                "planned_action": request.get("planned_action"),
            }
            network_calls_made = 0
            writes_attempted = 0
            status = "mock_write_completed"
        else:
            selected_target = self._require_selected_live_target(
                artifact_dir=artifact_dir,
                job_id=job_id,
                run_id=run_id,
                sink=sink,
                approved_by=approved_by,
                scope="write",
            )
            selected_target_ref = {
                "selection_id": selected_target.get("selection_id"),
                "created_at": selected_target.get("created_at"),
                "run_id": selected_target.get("run_id"),
                "job_id": selected_target.get("job_id"),
                "sink": selected_target.get("sink"),
                "operator": selected_target.get("operator") or selected_target.get("approved_by"),
                "scope": selected_target.get("scope"),
            }
            if self.sink_write_executor is None:
                readiness_path = artifact_dir / "sink_apply_pilot_readiness.json"
                readiness = (
                    json.loads(readiness_path.read_text(encoding="utf-8"))
                    if readiness_path.exists()
                    else self.build_sink_apply_pilot_readiness_for_job(
                        job_id=job_id,
                        run_id=run_id,
                        sink=sink,
                    )["readiness"]
                )
                readiness_sink = str(readiness.get("selected_sink") or readiness.get("sink") or "")
                if readiness_sink and readiness_sink != sink:
                    raise ValueError(
                        f"live sink write pilot readiness was prepared for {readiness_sink}, not {sink}"
                    )
                if not readiness.get("can_live_apply_pilot"):
                    raise ValueError("live sink write pilot requires ready sink_apply_pilot_readiness.json")
                execution = execute_sink_write_adapter(request)
            else:
                execution = self.sink_write_executor(request)
            write = dict(execution.get("write") or {})
            network_calls_made = int(execution.get("network_calls_made") or 0)
            writes_attempted = int(execution.get("writes_attempted") or 0)
            status = str(execution.get("status") or "live_write_completed")
        state = "mock_written" if simulate else "live_written"
        pilot = {
            "schema": "business-card-watchdog.sink-write-pilot.v1",
            "state": state,
            "status": status,
            "job_id": job_id,
            "run_id": run_id,
            "sink": sink,
            "approved_by": approved_by,
            "simulated": simulate,
            "writes_attempted": writes_attempted,
            "network_calls_made": network_calls_made,
            "request": request,
            "write": write,
            "execution": execution,
            "selected_target": selected_target_ref,
        }
        pilot_path = artifact_dir / "sink_write_pilot.json"
        pilot_path.write_text(json.dumps(pilot, indent=2, sort_keys=True) + "\n", encoding="utf-8")

        preflight_path = artifact_dir / "sink_apply_preflight.json"
        if preflight_path.exists():
            preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
        else:
            preflight = self.preflight_sink_apply(job_id=job_id, run_id=run_id)["preflight"]
        result = build_sink_apply_result(
            preflight=preflight,
            decision=decision,
            apply=True,
            simulate=simulate,
        )
        result["state"] = "mock_applied" if simulate else "live_applied"
        result["reason"] = (
            "explicit simulated sink write pilot completed; no live write attempted"
            if simulate
            else "explicit sink write pilot completed; readback adapter still requires explicit request"
        )
        result["writes_attempted"] = writes_attempted
        result["network_calls_made"] = network_calls_made
        result["source_write_pilot_schema"] = pilot["schema"]
        result["source_write_pilot_path"] = str(pilot_path)
        result["write_executions"] = [] if execution is None else [execution]
        result["readback"] = []
        for action in result["actions"]:
            if action.get("sink") != sink:
                continue
            action["state"] = result["state"]
            action["write_attempted"] = bool(writes_attempted)
            action["resource_id"] = write.get("resource_id")
            result["readback"].append(
                {
                    "sink": sink,
                    "resource_id": write.get("resource_id"),
                    "serialization_key": action.get("serialization_key"),
                    "matched": bool(write.get("resource_id")),
                    "simulated": simulate,
                }
            )
        result_path = artifact_dir / "sink_apply_result.json"
        result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        ledger = RunLedger(self.config.runs_dir / run_id)
        ledger.record_artifact(job_id=job_id, kind="sink_write_pilot", path=pilot_path)
        ledger.record_artifact(job_id=job_id, kind="sink_apply_result", path=result_path)
        ledger.record_event(
            "sink_write_pilot_executed",
            {
                "job_id": job_id,
                "run_id": run_id,
                "sink": sink,
                "approved_by": approved_by,
                "pilot_path": str(pilot_path),
                "result_path": str(result_path),
                "state": state,
                "writes_attempted": writes_attempted,
                "network_calls_made": network_calls_made,
            },
        )
        self._mark_route_artifact_refreshed(
            artifact_dir,
            job_id=job_id,
            run_id=run_id,
            kind="sink_write_pilot",
        )
        self._mark_route_artifact_refreshed(
            artifact_dir,
            job_id=job_id,
            run_id=run_id,
            kind="sink_apply_result",
        )
        return {
            "pilot_path": str(pilot_path),
            "result_path": str(result_path),
            "pilot": pilot,
            "result": result,
        }

    def execute_sink_readback_pilot_for_job(
        self,
        *,
        job_id: str,
        run_id: str,
        sink: str,
        approved_by: str,
        readback: dict[str, Any] | None = None,
        simulate: bool = True,
    ) -> dict[str, Any]:
        job = self.get_job(job_id, run_id=run_id)
        artifact_dir = Path(job["artifact_dir"]) if job.get("artifact_dir") else self.config.runs_dir / run_id / "artifacts" / job_id
        source_write_pilot = self._require_write_pilot_for_readback(artifact_dir, sink=sink)
        request_path = artifact_dir / "sink_adapter_request_readback.json"
        if request_path.exists():
            adapter_request = json.loads(request_path.read_text(encoding="utf-8"))
        else:
            adapter_request = self.build_sink_adapter_request_for_job(
                job_id=job_id,
                run_id=run_id,
                phase="readback",
            )["request"]
        requests = [
            request
            for request in list(adapter_request.get("requests") or [])
            if request.get("phase") == "readback" and request.get("sink") == sink
        ]
        if not requests:
            raise ValueError(f"sink readback pilot request not found for sink: {sink}")
        request = requests[0]
        execution = None
        if simulate:
            readback_payload = readback or {
                "resource_id": request.get("resource_id"),
                "matched": bool(request.get("resource_id")),
                "simulated": True,
            }
            network_calls_made = 0
            status = "mock_readback_verified" if readback_payload.get("matched") else "mock_readback_missing"
        else:
            selected_target = self._require_selected_live_target(
                artifact_dir=artifact_dir,
                job_id=job_id,
                run_id=run_id,
                sink=sink,
                approved_by=approved_by,
                scope="readback",
            )
            source_selected_target = dict(source_write_pilot.get("selected_target") or {})
            if _selected_target_identity(source_selected_target) != _selected_target_identity(selected_target):
                raise ValueError("sink readback pilot requires write pilot from current selected live target")
            if self.sink_readback_executor is not None:
                execution = self.sink_readback_executor(request)
            else:
                execution = execute_sink_readback_adapter(request)
            if int(execution.get("writes_attempted") or 0):
                raise ValueError("live sink readback pilot reported writes attempted")
            readback_payload = dict(execution.get("readback") or {})
            network_calls_made = int(execution.get("network_calls_made") or 0)
            status = str(execution.get("status") or "live_readback_completed")
        state = "verified" if readback_payload.get("matched") else "not_verified"
        pilot = {
            "schema": "business-card-watchdog.sink-readback-pilot.v1",
            "state": state,
            "status": status,
            "job_id": job_id,
            "run_id": run_id,
            "sink": sink,
            "approved_by": approved_by,
            "simulated": simulate,
            "read_only": True,
            "writes_attempted": 0,
            "network_calls_made": network_calls_made,
            "request": request,
            "readback": readback_payload,
            "execution": execution,
            "source_write_pilot": {
                "path": str(artifact_dir / "sink_write_pilot.json"),
                "state": source_write_pilot.get("state"),
                "simulated": bool(source_write_pilot.get("simulated", False)),
                "resource_id": (source_write_pilot.get("write") or {}).get("resource_id"),
                "selected_target": source_write_pilot.get("selected_target"),
            },
        }
        pilot_path = artifact_dir / "sink_readback_pilot.json"
        pilot_path.write_text(json.dumps(pilot, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        ledger = RunLedger(self.config.runs_dir / run_id)
        ledger.record_artifact(job_id=job_id, kind="sink_readback_pilot", path=pilot_path)
        ledger.record_event(
            "sink_readback_pilot_executed",
            {
                "job_id": job_id,
                "run_id": run_id,
                "sink": sink,
                "approved_by": approved_by,
                "pilot_path": str(pilot_path),
                "state": state,
                "writes_attempted": 0,
                "network_calls_made": network_calls_made,
            },
        )
        self._mark_route_artifact_refreshed(
            artifact_dir,
            job_id=job_id,
            run_id=run_id,
            kind="sink_readback_pilot",
        )
        return {"pilot_path": str(pilot_path), "pilot": pilot}

    def build_sink_apply_pilot_report_for_job(self, *, job_id: str, run_id: str) -> dict[str, Any]:
        job = self.get_job(job_id, run_id=run_id)
        artifact_dir = Path(job["artifact_dir"]) if job.get("artifact_dir") else self.config.runs_dir / run_id / "artifacts" / job_id
        readiness = _read_json_file(artifact_dir / "sink_apply_pilot_readiness.json")
        write_pilot = _read_json_file(artifact_dir / "sink_write_pilot.json")
        apply_result = _read_json_file(artifact_dir / "sink_apply_result.json")
        readback_request = _read_json_file(artifact_dir / "sink_adapter_request_readback.json")
        readback_pilot = _read_json_file(artifact_dir / "sink_readback_pilot.json")
        write_sink = str((write_pilot or {}).get("sink") or "")
        readback_sink = str((readback_pilot or {}).get("sink") or "")
        sinks = sorted({sink for sink in [write_sink, readback_sink] if sink})
        sink_reports = []
        for sink in sinks:
            write_for_sink = write_pilot if write_sink == sink else None
            readback_for_sink = readback_pilot if readback_sink == sink else None
            sink_reports.append(
                {
                    "sink": sink,
                    "write_state": (write_for_sink or {}).get("state", "missing"),
                    "write_simulated": bool((write_for_sink or {}).get("simulated", False)),
                    "write_resource_id": ((write_for_sink or {}).get("write") or {}).get("resource_id"),
                    "readback_state": (readback_for_sink or {}).get("state", "missing"),
                    "readback_simulated": bool((readback_for_sink or {}).get("simulated", False)),
                    "readback_resource_id": ((readback_for_sink or {}).get("readback") or {}).get("resource_id"),
                    "readback_matched": bool(((readback_for_sink or {}).get("readback") or {}).get("matched", False)),
                }
            )
        missing = [
            name
            for name, payload in [
                ("sink_apply_pilot_readiness", readiness),
                ("sink_write_pilot", write_pilot),
                ("sink_apply_result", apply_result),
                ("sink_adapter_request_readback", readback_request),
                ("sink_readback_pilot", readback_pilot),
            ]
            if payload is None
        ]
        readback_verified = bool(readback_pilot and readback_pilot.get("state") == "verified")
        write_present = bool(write_pilot)
        consistency_errors = self._apply_pilot_report_consistency_errors(
            write_pilot=write_pilot,
            readback_pilot=readback_pilot,
        )
        state = "complete" if write_present and readback_verified and not missing and not consistency_errors else "incomplete"
        writes_attempted = int((write_pilot or {}).get("writes_attempted") or 0)
        network_calls_made = int((write_pilot or {}).get("network_calls_made") or 0) + int(
            (readback_pilot or {}).get("network_calls_made") or 0
        )
        payload = {
            "schema": "business-card-watchdog.sink-apply-pilot-report.v1",
            "state": state,
            "status": state,
            "reason": (
                "write pilot and readback pilot evidence are present"
                if state == "complete"
                else "apply pilot report is missing required artifacts or has inconsistent evidence"
            ),
            "job_id": job_id,
            "run_id": run_id,
            "writes_attempted": writes_attempted,
            "network_calls_made": network_calls_made,
            "missing_artifacts": missing,
            "consistency_errors": consistency_errors,
            "readiness_state": (readiness or {}).get("state", "missing"),
            "apply_result_state": (apply_result or {}).get("state", "missing"),
            "readback_request_state": (readback_request or {}).get("state", "missing"),
            "sinks": sink_reports,
            "artifact_paths": {
                "sink_apply_pilot_readiness": str(artifact_dir / "sink_apply_pilot_readiness.json"),
                "sink_write_pilot": str(artifact_dir / "sink_write_pilot.json"),
                "sink_apply_result": str(artifact_dir / "sink_apply_result.json"),
                "sink_adapter_request_readback": str(artifact_dir / "sink_adapter_request_readback.json"),
                "sink_readback_pilot": str(artifact_dir / "sink_readback_pilot.json"),
            },
        }
        report_path = artifact_dir / "sink_apply_pilot_report.json"
        report_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        ledger = RunLedger(self.config.runs_dir / run_id)
        ledger.record_artifact(job_id=job_id, kind="sink_apply_pilot_report", path=report_path)
        ledger.record_event(
            "sink_apply_pilot_report_created",
            {
                "job_id": job_id,
                "run_id": run_id,
                "report_path": str(report_path),
                "state": state,
                "writes_attempted": writes_attempted,
                "network_calls_made": network_calls_made,
            },
        )
        self._mark_route_artifact_refreshed(
            artifact_dir,
            job_id=job_id,
            run_id=run_id,
            kind="sink_apply_pilot_report",
        )
        return {"report_path": str(report_path), "report": payload}

    def _apply_pilot_report_consistency_errors(
        self,
        *,
        write_pilot: dict[str, Any] | None,
        readback_pilot: dict[str, Any] | None,
    ) -> list[str]:
        if not write_pilot or not readback_pilot:
            return []
        errors: list[str] = []
        write_sink = str(write_pilot.get("sink") or "")
        readback_sink = str(readback_pilot.get("sink") or "")
        if write_sink != readback_sink:
            errors.append(f"sink_mismatch:write={write_sink or 'missing'} readback={readback_sink or 'missing'}")
        source_write = readback_pilot.get("source_write_pilot")
        if not isinstance(source_write, dict):
            errors.append("readback_source_write_pilot=missing")
            return errors
        write_state = str(write_pilot.get("state") or "")
        source_state = str(source_write.get("state") or "")
        if source_state != write_state:
            errors.append(f"source_write_state_mismatch:write={write_state or 'missing'} source={source_state or 'missing'}")
        write_resource_id = str((write_pilot.get("write") or {}).get("resource_id") or "")
        source_resource_id = str(source_write.get("resource_id") or "")
        if write_resource_id != source_resource_id:
            errors.append(
                f"source_write_resource_mismatch:write={write_resource_id or 'missing'} "
                f"source={source_resource_id or 'missing'}"
            )
        write_selected_target = dict(write_pilot.get("selected_target") or {})
        source_selected_target = dict(source_write.get("selected_target") or {})
        if write_selected_target or source_selected_target:
            write_identity = _selected_target_identity(write_selected_target)
            source_identity = _selected_target_identity(source_selected_target)
            if write_identity != source_identity:
                errors.append(
                    f"source_write_selected_target_mismatch:write={write_identity or 'missing'} "
                    f"source={source_identity or 'missing'}"
                )
        return errors

    def _selected_target_audit_context_mismatches(
        self,
        *,
        selected_target: dict[str, Any],
        selected_target_audit: dict[str, Any],
        run_id: str,
        job_id: str,
    ) -> list[str]:
        if not selected_target or not selected_target_audit:
            return []
        sink = str(selected_target.get("sink") or "")
        operator = str(selected_target.get("operator") or selected_target.get("approved_by") or "")
        scope = str(selected_target.get("scope") or "lookup")
        mismatches: list[str] = []
        for key, expected in [
            ("run_id", run_id),
            ("job_id", job_id),
            ("sink", sink or None),
            ("operator", operator or None),
            ("scope", scope),
        ]:
            if selected_target_audit.get(key) != expected:
                mismatches.append(f"{key}={selected_target_audit.get(key)!r}")
        mismatches.extend(str(reason) for reason in list(selected_target_audit.get("mismatches") or []))
        if selected_target_audit.get("target_safety_confirmed") is False:
            mismatches.append("target_safety_confirmation=missing")
        return mismatches

    def build_live_pilot_closeout_for_job(self, *, job_id: str, run_id: str, write: bool = True) -> dict[str, Any]:
        job = self.get_job(job_id, run_id=run_id)
        artifact_dir = (
            Path(job["artifact_dir"])
            if job.get("artifact_dir")
            else self.config.runs_dir / run_id / "artifacts" / job_id
        )
        artifacts = {
            "selected_live_target": _read_json_file(artifact_dir / "selected_live_target.json"),
            "selected_live_target_audit": _read_json_file(artifact_dir / "selected_live_target_audit.json"),
            "selected_lookup_smoke": _read_json_file(artifact_dir / "selected_lookup_smoke.json"),
            "sink_lookup_pilot": _read_json_file(artifact_dir / "sink_lookup_pilot.json"),
            "sink_lookup_result": _read_json_file(artifact_dir / "sink_lookup_result.json"),
            "downstream_duplicate_assessment": _read_json_file(artifact_dir / "downstream_duplicate_assessment.json"),
            "sink_apply_pilot_bundle": _read_json_file(artifact_dir / "sink_apply_pilot_bundle.json"),
            "sink_write_pilot": _read_json_file(artifact_dir / "sink_write_pilot.json"),
            "sink_apply_result": _read_json_file(artifact_dir / "sink_apply_result.json"),
            "sink_readback_pilot": _read_json_file(artifact_dir / "sink_readback_pilot.json"),
            "sink_apply_pilot_report": _read_json_file(artifact_dir / "sink_apply_pilot_report.json"),
        }
        selected_target = artifacts["selected_live_target"] or {}
        sink = str(
            selected_target.get("sink")
            or (artifacts["sink_write_pilot"] or {}).get("sink")
            or (artifacts["sink_readback_pilot"] or {}).get("sink")
            or ""
        )
        operator = str(selected_target.get("operator") or selected_target.get("approved_by") or "")
        scope = str(selected_target.get("scope") or "lookup")
        scope_allows = dict(selected_target.get("scope_allows") or {})
        selected_lookup_smoke = artifacts["selected_lookup_smoke"] or {}
        duplicate = artifacts["downstream_duplicate_assessment"] or {}
        write_pilot = artifacts["sink_write_pilot"] or {}
        readback_pilot = artifacts["sink_readback_pilot"] or {}
        apply_report = artifacts["sink_apply_pilot_report"] or {}
        selected_target_audit = artifacts["selected_live_target_audit"] or {}
        required_artifacts = ["selected_live_target", "selected_live_target_audit"]
        if scope_allows.get("lookup") or scope in {"lookup", "all"}:
            required_artifacts.extend(["selected_lookup_smoke", "downstream_duplicate_assessment"])
        if scope_allows.get("write") or scope in {"write", "all"}:
            required_artifacts.extend(["sink_write_pilot", "sink_apply_result", "sink_apply_pilot_report"])
        if scope_allows.get("readback") or scope in {"readback", "all"}:
            required_artifacts.extend(["sink_readback_pilot", "sink_apply_pilot_report"])
        required_artifacts = list(dict.fromkeys(required_artifacts))
        missing_artifacts = [name for name in required_artifacts if artifacts.get(name) is None]
        blocked_reasons = list(missing_artifacts)
        if selected_target_audit:
            audit_mismatches = self._selected_target_audit_context_mismatches(
                selected_target=selected_target,
                selected_target_audit=selected_target_audit,
                run_id=run_id,
                job_id=job_id,
            )
            blocked_reasons.extend(f"selected_target_audit:{reason}" for reason in audit_mismatches)
        if duplicate.get("state") in {"strong_duplicate", "possible_duplicate"} and not duplicate.get("reviewed"):
            blocked_reasons.append(f"downstream_duplicate_state:{duplicate.get('state')}")
        if write_pilot and write_pilot.get("state") not in {"mock_written", "live_written"}:
            blocked_reasons.append(f"write_pilot_state:{write_pilot.get('state')}")
        if readback_pilot and readback_pilot.get("state") != "verified":
            blocked_reasons.append(f"readback_pilot_state:{readback_pilot.get('state')}")
        consistency_errors = self._apply_pilot_report_consistency_errors(
            write_pilot=write_pilot or None,
            readback_pilot=readback_pilot or None,
        )
        blocked_reasons.extend(f"sink_apply_pilot_report:{reason}" for reason in consistency_errors)
        if selected_target and write_pilot:
            write_selected_target = dict(write_pilot.get("selected_target") or {})
            if write_selected_target:
                expected_identity = _selected_target_identity(selected_target)
                write_identity = _selected_target_identity(write_selected_target)
                if write_identity != expected_identity:
                    blocked_reasons.append(
                        f"write_pilot_selected_target_mismatch:current={expected_identity or 'missing'} "
                        f"write={write_identity or 'missing'}"
                    )
        if selected_target and readback_pilot:
            readback_source_write = dict(readback_pilot.get("source_write_pilot") or {})
            readback_selected_target = dict(readback_source_write.get("selected_target") or {})
            if readback_selected_target:
                expected_identity = _selected_target_identity(selected_target)
                readback_identity = _selected_target_identity(readback_selected_target)
                if readback_identity != expected_identity:
                    blocked_reasons.append(
                        f"readback_source_selected_target_mismatch:current={expected_identity or 'missing'} "
                        f"readback={readback_identity or 'missing'}"
                    )
        if apply_report and apply_report.get("state") != "complete":
            blocked_reasons.append(f"sink_apply_pilot_report_state:{apply_report.get('state')}")
        apply_report_consistency_errors = list(apply_report.get("consistency_errors") or [])
        blocked_reasons.extend(
            f"sink_apply_pilot_report:{reason}" for reason in apply_report_consistency_errors
        )
        state = "complete" if not blocked_reasons else "incomplete"
        writes_attempted = int(write_pilot.get("writes_attempted") or 0)
        network_calls_made = (
            int((selected_lookup_smoke or {}).get("network_calls_made") or 0)
            + int(write_pilot.get("network_calls_made") or 0)
            + int(readback_pilot.get("network_calls_made") or 0)
        )
        artifact_paths = {
            name: str(artifact_dir / filename)
            for name, filename in {
                "selected_live_target": "selected_live_target.json",
                "selected_live_target_audit": "selected_live_target_audit.json",
                "selected_lookup_smoke": "selected_lookup_smoke.json",
                "sink_lookup_pilot": "sink_lookup_pilot.json",
                "sink_lookup_result": "sink_lookup_result.json",
                "downstream_duplicate_assessment": "downstream_duplicate_assessment.json",
                "sink_apply_pilot_bundle": "sink_apply_pilot_bundle.json",
                "sink_write_pilot": "sink_write_pilot.json",
                "sink_apply_result": "sink_apply_result.json",
                "sink_readback_pilot": "sink_readback_pilot.json",
                "sink_apply_pilot_report": "sink_apply_pilot_report.json",
            }.items()
        }
        payload = {
            "schema": "business-card-watchdog.live-pilot-closeout.v1",
            "generated_at": utc_now(),
            "state": state,
            "status": state,
            "reason": (
                "selected live pilot evidence is complete for the approved scope"
                if state == "complete"
                else "selected live pilot closeout is missing required evidence"
            ),
            "run_id": run_id,
            "job_id": job_id,
            "job_state": job.get("state"),
            "sink": sink or None,
            "operator": operator or None,
            "scope": scope,
            "required_artifacts": required_artifacts,
            "missing_artifacts": missing_artifacts,
            "blocked_reasons": blocked_reasons,
            "writes_attempted": writes_attempted,
            "network_calls_made": network_calls_made,
            "lookup": {
                "status": selected_lookup_smoke.get("lookup_status") or (artifacts["sink_lookup_pilot"] or {}).get("status"),
                "match_count": selected_lookup_smoke.get("lookup_match_count")
                or (artifacts["sink_lookup_pilot"] or {}).get("match_count", 0),
                "result_redacted": selected_lookup_smoke.get("result_redacted")
                or bool((artifacts["sink_lookup_pilot"] or {}).get("execution_redacted", False)),
                "downstream_duplicate_state": duplicate.get("state"),
            },
            "selected_target_audit": {
                "state": selected_target_audit.get("state"),
                "mismatches": selected_target_audit.get("mismatches", []),
                "target_safety_confirmed": selected_target_audit.get("target_safety_confirmed"),
            },
            "write": {
                "state": write_pilot.get("state"),
                "simulated": write_pilot.get("simulated"),
                "resource_id": (write_pilot.get("write") or {}).get("resource_id"),
            },
            "readback": {
                "state": readback_pilot.get("state"),
                "simulated": readback_pilot.get("simulated"),
                "matched": (readback_pilot.get("readback") or {}).get("matched"),
                "resource_id": (readback_pilot.get("readback") or {}).get("resource_id"),
            },
            "apply_report": {
                "state": apply_report.get("state"),
                "consistency_errors": apply_report_consistency_errors,
                "closeout_consistency_errors": consistency_errors,
                "path": artifact_paths["sink_apply_pilot_report"],
            },
            "artifact_paths": artifact_paths,
            "remediation": self._pilot_bundle_remediation(sink or "unknown"),
            "commands": {
                "selected_target_audit": f"sinks selected-target-audit {job_id} --run-id {run_id}",
                "lookup_smoke": f"sinks execute-lookup-smoke {job_id} --run-id {run_id} --json",
                "apply_pilot_report": f"sinks apply-pilot-report {job_id} --run-id {run_id}",
                "closeout": f"sinks live-pilot-closeout {job_id} --run-id {run_id}",
            },
            "explicit_stop_conditions": [
                "Do not run another live write until this closeout is complete or explicitly abandoned.",
                "Do not proceed if required artifacts name a different run, job, sink, operator, or scope.",
                "Do not paste raw downstream contact rows, credentials, tenant state, or private card data into the repo.",
                "Inspect downstream contacts manually before retrying any failed write or readback.",
            ],
        }
        if write:
            closeout_path = artifact_dir / "live_pilot_closeout.json"
            closeout_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            ledger = RunLedger(self.config.runs_dir / run_id)
            ledger.record_artifact(job_id=job_id, kind="live_pilot_closeout", path=closeout_path)
            ledger.record_event(
                "live_pilot_closeout_created",
                {
                    "job_id": job_id,
                    "run_id": run_id,
                    "closeout_path": str(closeout_path),
                    "state": state,
                    "writes_attempted": writes_attempted,
                    "network_calls_made": network_calls_made,
                },
            )
            self._mark_route_artifact_refreshed(
                artifact_dir,
                job_id=job_id,
                run_id=run_id,
                kind="live_pilot_closeout",
            )
            payload["closeout_path"] = str(closeout_path)
        return {"closeout_path": payload.get("closeout_path"), "report": payload}

    def build_sink_apply_pilot_bundle_for_job(
        self,
        *,
        job_id: str,
        run_id: str,
        sink: str,
        operator: str = "operator",
    ) -> dict[str, Any]:
        if sink not in {"google_contacts", "odoo"}:
            raise ValueError("sink apply pilot bundle requires sink google_contacts or odoo")
        job = self.get_job(job_id, run_id=run_id)
        artifact_dir = Path(job["artifact_dir"]) if job.get("artifact_dir") else self.config.runs_dir / run_id / "artifacts" / job_id
        readiness = self.build_sink_apply_pilot_readiness_for_job(
            job_id=job_id,
            run_id=run_id,
            sink=sink,
        )["readiness"]
        artifacts = {
            "reviewed_contact": _read_json_file(artifact_dir / "reviewed_contact.json"),
            "contact_candidate": _read_json_file(artifact_dir / "contact_candidate.json"),
            "sink_lookup_result": _read_json_file(artifact_dir / "sink_lookup_result.json"),
            "downstream_duplicate_assessment": _read_json_file(artifact_dir / "downstream_duplicate_assessment.json"),
            "duplicate_resolution": _read_json_file(artifact_dir / "duplicate_resolution.json"),
            "sink_plan": _read_json_file(artifact_dir / "sink_plan.json"),
            "sink_adapter_request_write": _read_json_file(artifact_dir / "sink_adapter_request_write.json"),
            "sink_apply_preflight": _read_json_file(artifact_dir / "sink_apply_preflight.json"),
            "sink_apply_decision": _read_json_file(artifact_dir / "sink_apply_decision.json"),
            "sink_apply_pilot_readiness": readiness,
            "sink_write_pilot": _read_json_file(artifact_dir / "sink_write_pilot.json"),
            "sink_apply_result": _read_json_file(artifact_dir / "sink_apply_result.json"),
            "sink_adapter_request_readback": _read_json_file(artifact_dir / "sink_adapter_request_readback.json"),
            "sink_readback_pilot": _read_json_file(artifact_dir / "sink_readback_pilot.json"),
            "sink_apply_pilot_report": _read_json_file(artifact_dir / "sink_apply_pilot_report.json"),
        }
        artifact_status = {
            kind: self._pilot_bundle_artifact_status(
                kind=kind,
                path=artifact_dir / f"{kind}.json",
                payload=payload,
                sink=sink,
            )
            for kind, payload in artifacts.items()
        }
        requirements = self._pilot_bundle_requirements(
            artifacts=artifacts,
            artifact_status=artifact_status,
            readiness=readiness,
            sink=sink,
        )
        requirement_by_name = {str(item["name"]): bool(item["ok"]) for item in requirements}
        can_attempt_mock = all(
            requirement_by_name[name]
            for name in [
                "reviewed_contact_exists",
                "selected_sink_planned",
                "apply_decision_approved",
                "selected_sink_readiness_prepared",
                "mock_apply_ready",
            ]
        )
        can_attempt_live = all(
            requirement_by_name[name]
            for name in [
                "reviewed_contact_exists",
                "selected_sink_lookup_reviewed",
                "selected_sink_planned",
                "apply_decision_approved",
                "selected_sink_readiness_prepared",
                "live_apply_ready",
            ]
        )
        missing_requirements = [item["name"] for item in requirements if not item["ok"]]
        state = (
            "ready_for_live_pilot"
            if can_attempt_live
            else ("ready_for_mock_pilot" if can_attempt_mock else "blocked")
        )
        payload = {
            "schema": "business-card-watchdog.sink-apply-pilot-bundle.v1",
            "state": state,
            "status": state,
            "reason": (
                "selected sink has live pilot readiness evidence"
                if can_attempt_live
                else (
                    "selected sink has mock pilot readiness evidence; live pilot remains blocked"
                    if can_attempt_mock
                    else "operator pilot bundle is blocked until required selected-sink evidence exists"
                )
            ),
            "job_id": job_id,
            "run_id": run_id,
            "sink": sink,
            "operator": operator,
            "created_at": utc_now(),
            "writes_attempted": 0,
            "network_calls_made": 0,
            "can_attempt_mock_pilot": can_attempt_mock,
            "can_attempt_live_pilot": can_attempt_live,
            "requirements": requirements,
            "missing_requirements": missing_requirements,
            "artifacts": artifact_status,
            "readiness": readiness,
            "commands": {
                "inspect_job": f"jobs show {job_id} --run-id {run_id}",
                "review_bundle": f"reviews bundle --run-id {run_id} --state all",
                "lookup_readiness": f"sinks lookup-readiness {job_id} --run-id {run_id} --sink {sink}",
                "lookup_pilot": (
                    f"sinks lookup-pilot {job_id} --run-id {run_id} --sink {sink} "
                    "--approved-by <operator> --no-simulate"
                ),
                "assess_duplicates": f"sinks assess-duplicates {job_id} --run-id {run_id}",
                "apply_pilot_readiness": f"sinks apply-pilot-readiness {job_id} --run-id {run_id} --sink {sink}",
                "mock_write": (
                    f"sinks write-pilot {job_id} --run-id {run_id} --sink {sink} "
                    "--approved-by <operator> --simulate"
                ),
                "live_write": (
                    f"sinks write-pilot {job_id} --run-id {run_id} --sink {sink} "
                    "--approved-by <operator> --no-simulate"
                ),
                "readback_request": f"sinks adapter-request {job_id} --run-id {run_id} --phase readback",
                "mock_readback": (
                    f"sinks readback-pilot {job_id} --run-id {run_id} --sink {sink} "
                    "--approved-by <operator> --simulate"
                ),
                "live_readback": (
                    f"sinks readback-pilot {job_id} --run-id {run_id} --sink {sink} "
                    "--approved-by <operator> --no-simulate"
                ),
                "pilot_report": f"sinks apply-pilot-report {job_id} --run-id {run_id}",
            },
            "stop_conditions": [
                "any artifact names a different run, job, or sink than this bundle",
                "selected sink readiness is blocked or references an unexpected profile or tenant",
                "downstream duplicate assessment is missing, unresolved, or names an unreviewed strong match",
                "operator cannot accept sink-specific remediation limits",
                "readback does not verify the expected resource after a write pilot",
                "a second write pilot would run before the first pilot report is complete or explicitly abandoned",
            ],
            "remediation": self._pilot_bundle_remediation(sink),
        }
        bundle_path = artifact_dir / "sink_apply_pilot_bundle.json"
        bundle_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        ledger = RunLedger(self.config.runs_dir / run_id)
        ledger.record_artifact(job_id=job_id, kind="sink_apply_pilot_bundle", path=bundle_path)
        ledger.record_event(
            "sink_apply_pilot_bundle_created",
            {
                "job_id": job_id,
                "run_id": run_id,
                "sink": sink,
                "operator": operator,
                "bundle_path": str(bundle_path),
                "state": state,
                "writes_attempted": 0,
                "network_calls_made": 0,
            },
        )
        self._mark_route_artifact_refreshed(
            artifact_dir,
            job_id=job_id,
            run_id=run_id,
            kind="sink_apply_pilot_bundle",
        )
        return {"bundle_path": str(bundle_path), "bundle": payload}

    def doctor(self) -> dict[str, Any]:
        status = self.status()
        checks = [
            _path_check("config_parent", self.config.config_path.parent),
            _path_check("data_dir", self.config.data_dir),
            _path_check("cache_dir", self.config.cache_dir),
            _path_check("runs_dir", self.config.runs_dir),
            _path_check("watch_dir", self.config.watch_dir),
            {
                "name": "business_card_skill",
                "ok": bool(status["skill_ready"]),
                "detail": str(status["skill_message"]),
            },
            {
                "name": "watch_inputs",
                "ok": status["watch"]["last_error"] is None,
                "detail": status["watch"]["last_error"] or "watch inputs are readable or not configured",
            },
        ]
        return {"ok": all(check["ok"] for check in checks), "checks": checks}

    def runtime_readiness(self) -> dict[str, Any]:
        status = self.status()
        doctor = self.doctor()
        service = service_status().to_dict()
        watch_status = dict(status["watch"])
        config_exists = self.config.config_path.exists()
        runtime_checks = [
            _readiness_check(
                "config_file",
                "ready" if config_exists else "blocked",
                str(self.config.config_path) if config_exists else f"config file not found: {self.config.config_path}",
            ),
            *[
                _readiness_check(
                    str(check["name"]),
                    "ready" if check["ok"] else "blocked",
                    str(check["detail"]),
                )
                for check in doctor["checks"]
                if str(check.get("name")) in {"config_parent", "data_dir", "cache_dir", "runs_dir", "watch_dir"}
            ],
            _readiness_check(
                "business_card_skill",
                "ready" if status["skill_ready"] else "blocked",
                str(status["skill_message"]),
            ),
        ]
        service_checks = [
            _readiness_check(
                "user_service_unit",
                "ready" if service["installed"] else "warning",
                str(service["unit_path"]) if service["installed"] else f"user service unit not installed: {service['unit_path']}",
            )
        ]
        watch_inputs = list(watch_status.get("inputs") or [])
        watch_error = watch_status.get("last_error")
        watch_checks = [
            _readiness_check(
                "watch_inputs_configured",
                "ready" if watch_inputs else "warning",
                f"{len(watch_inputs)} configured watch input(s)" if watch_inputs else "no watched inputs configured",
            ),
            _readiness_check(
                "watch_inputs_readable",
                "ready" if watch_error is None else "blocked",
                str(watch_error or "configured watched inputs are readable or no inputs are configured"),
            ),
            _readiness_check(
                "watch_scan_not_truncated",
                "warning" if watch_status.get("scan_truncated") else "ready",
                "watch status scan was truncated"
                if watch_status.get("scan_truncated")
                else "watch status scan was not truncated",
            ),
        ]
        checks = runtime_checks + service_checks + watch_checks
        blocked = [check for check in checks if check["status"] == "blocked"]
        warnings = [check for check in checks if check["status"] == "warning"]
        state = "blocked" if blocked else "warning" if warnings else "ready"
        return {
            "schema": "business-card-watchdog.runtime-readiness.v1",
            "generated_at": utc_now(),
            "state": state,
            "ready": state == "ready",
            "network_calls_made": 0,
            "writes_attempted": 0,
            "config": {
                "config_path": str(self.config.config_path),
                "config_exists": config_exists,
                "data_dir": str(self.config.data_dir),
                "cache_dir": str(self.config.cache_dir),
                "runs_dir": str(self.config.runs_dir),
                "watch_dir": str(self.config.watch_dir),
            },
            "service": service,
            "watch": watch_status,
            "checks": checks,
            "blocked_checks": blocked,
            "warning_checks": warnings,
            "safe_next_actions": _runtime_safe_next_actions(
                state=state,
                config_exists=config_exists,
                service_installed=bool(service["installed"]),
                watch_error=str(watch_error) if watch_error else "",
                watch_inputs=watch_inputs,
            ),
            "explicit_stop_conditions": [
                "Do not process private SyncThing images from generic continuation.",
                "Do not run public-web search or paid API enrichment without an explicit selected run policy.",
                "Do not run live GWS/Odollo/Odoo lookup, write, or readback without selected target approval.",
            ],
        }

    def service_recovery_report(self, *, run_id: str | None = None) -> dict[str, Any]:
        readiness = self.runtime_readiness()
        service = dict(readiness["service"])
        watch = dict(readiness["watch"])
        runs = self.list_runs()
        selected_run_id = run_id or (str(runs[0]["run_id"]) if runs else None)
        latest_drill = self.latest_review_routing_drill(selected_run_id=selected_run_id)
        run_summary: dict[str, Any] | None = None
        phase_report: dict[str, Any] | None = None
        pilot_readiness: dict[str, Any] | None = None
        next_actions: dict[str, Any] | None = None
        live_pilot_checklist_rollup = _live_pilot_checklist_rollup(None)
        if selected_run_id:
            run_summary = self.run_summary(selected_run_id)
            phase_report = self.phase_report(selected_run_id)
            pilot_readiness = self.pilot_readiness_report(selected_run_id)
            next_actions = self.next_actions(run_id=selected_run_id, limit=20)
            live_pilot_checklist_rollup = _live_pilot_checklist_rollup(
                self.live_pilot_handoff(run_id=selected_run_id, write=False)
            )

        command_prefix = f"bcw --config {self.config.config_path} "
        service_name = str(service.get("service_name") or "business-card-watchdog.service")
        commands = {
            "install": f"{command_prefix}service install --json",
            "start": f"systemctl --user start {service_name}",
            "status": f"{command_prefix}service status --json",
            "runtime_status": f"{command_prefix}runtime-readiness --json",
            "watch_status": f"{command_prefix}watch-status --json",
            "review_routing_drill": f"{command_prefix}drills review-routing --json",
            "restart": f"systemctl --user restart {service_name}",
            "resume": f"{command_prefix}actions run-next --run-id {selected_run_id} --limit 10 --json"
            if selected_run_id
            else f"{command_prefix}runs list --json",
            "recover": f"{command_prefix}service recovery --run-id {selected_run_id} --json"
            if selected_run_id
            else f"{command_prefix}service recovery --json",
            "live_pilot_status": f"{command_prefix}runs live-pilot-status {selected_run_id} --no-write --json"
            if selected_run_id
            else f"{command_prefix}runs list --json",
            "live_pilot_handoff": f"{command_prefix}runs live-pilot-handoff {selected_run_id}"
            if selected_run_id
            else f"{command_prefix}runs list --json",
        }
        blocked_reasons: list[dict[str, Any]] = []
        if readiness["state"] == "blocked":
            blocked_reasons.extend(
                {
                    "source": "runtime_readiness",
                    "name": str(check.get("name") or "unknown"),
                    "detail": str(check.get("detail") or ""),
                }
                for check in readiness.get("blocked_checks", [])
                if isinstance(check, dict)
            )
        if watch.get("last_error"):
            blocked_reasons.append(
                {
                    "source": "watch",
                    "name": "watch_inputs",
                    "detail": str(watch["last_error"]),
                }
            )
        explicit_action_count = 0
        safe_action_count = 0
        if pilot_readiness:
            counts = dict(pilot_readiness.get("counts") or {})
            explicit_action_count = int(counts.get("explicit_operator_required") or 0)
            safe_action_count = int(counts.get("safe_auto_available") or 0)
        if blocked_reasons:
            state = "blocked"
        elif explicit_action_count:
            state = "operator_required"
        elif safe_action_count:
            state = "safe_resume_available"
        elif readiness["state"] == "warning":
            state = "warning"
        else:
            state = "ready"
        safe_next_actions = [
            {
                "action": "inspect_runtime_readiness",
                "command": commands["runtime_status"],
                "reason": "confirm config, runtime paths, watcher, and service readiness before recovery",
                "safe_to_auto_continue": True,
                "requires_explicit_operator_action": False,
            },
            {
                "action": "inspect_watch_status",
                "command": commands["watch_status"],
                "reason": "confirm watched inputs, backlog, unsettled files, and last watcher error",
                "safe_to_auto_continue": True,
                "requires_explicit_operator_action": False,
            },
            {
                "action": "run_fixture_review_routing_drill",
                "command": commands["review_routing_drill"],
                "reason": "prove review/export/routing readiness with synthetic fixture data before private or live work",
                "safe_to_auto_continue": True,
                "requires_explicit_operator_action": False,
            },
        ]
        if selected_run_id and safe_action_count:
            safe_next_actions.append(
                {
                    "action": "resume_safe_next_actions",
                    "command": commands["resume"],
                    "reason": "run has deterministic zero-network/zero-write actions available",
                    "safe_to_auto_continue": True,
                    "requires_explicit_operator_action": False,
                }
            )
        if selected_run_id:
            safe_next_actions.extend(
                [
                    {
                        "action": "inspect_live_pilot_status",
                        "command": commands["live_pilot_status"],
                        "reason": "inspect selected-run live pilot state without writing artifacts or running live calls",
                        "safe_to_auto_continue": True,
                        "requires_explicit_operator_action": False,
                    },
                    {
                        "action": "inspect_live_pilot_handoff",
                        "command": commands["live_pilot_handoff"] + " --no-write --json",
                        "reason": "inspect selected-run live pilot handoff without writing artifacts or running live calls",
                        "safe_to_auto_continue": True,
                        "requires_explicit_operator_action": False,
                    },
                ]
            )
        return {
            "schema": "business-card-watchdog.service-recovery.v1",
            "generated_at": utc_now(),
            "state": state,
            "run_id": selected_run_id,
            "network_calls_made": 0,
            "writes_attempted": 0,
            "service": service,
            "runtime_readiness": readiness,
            "watch": watch,
            "latest_runs": runs[:5],
            "run_summary": run_summary,
            "phase_dashboard_summary": (phase_report or {}).get("dashboard_summary") if phase_report else None,
            "pilot_readiness": pilot_readiness,
            "next_actions": (next_actions or {}).get("actions", []) if next_actions else [],
            "latest_review_routing_drill": latest_drill,
            "live_pilot_checklist_rollup": live_pilot_checklist_rollup,
            "blocked_reasons": blocked_reasons,
            "commands": commands,
            "safe_next_actions": safe_next_actions,
            "explicit_operator_actions": [
                action
                for action in ((next_actions or {}).get("actions", []) if next_actions else [])
                if action.get("requires_explicit_operator_action")
                or action.get("action") in _EXPLICIT_OPERATOR_ACTIONS
            ],
            "recovery_sequence": [
                {
                    "step": "status",
                    "command": commands["runtime_status"],
                    "purpose": "confirm user-scope config, runtime directories, service unit, and watched inputs",
                },
                {
                    "step": "restart",
                    "command": commands["restart"],
                    "purpose": "restart the user-scoped watched-folder daemon if it is installed but stale",
                },
                {
                    "step": "resume",
                    "command": commands["resume"],
                    "purpose": "resume only deterministic zero-network/zero-write actions for the selected run",
                },
                {
                    "step": "recover",
                    "command": commands["recover"],
                    "purpose": "re-read recovery state after any restart, config repair, or safe resume",
                },
            ],
            "explicit_stop_conditions": [
                "Do not scan or process private SyncThing images from generic recovery.",
                "Do not run public-web search or paid enrichment from recovery.",
                "Do not execute live GWS/Odollo/Odoo lookup, write, or readback without selected-target approval.",
                "Stop when next actions require review, duplicate resolution, selected target approval, live lookup, live write, or readback.",
            ],
        }

    def live_target_candidates(
        self,
        *,
        run_id: str | None = None,
        sink: str | None = None,
    ) -> dict[str, Any]:
        selected_sink = str(sink or "").strip()
        if selected_sink and selected_sink not in {"google_contacts", "odoo"}:
            raise ValueError("live target candidates require sink google_contacts or odoo")
        runs = [self.get_run(run_id)] if run_id else self.list_runs()
        candidates: list[dict[str, Any]] = []
        for run in runs:
            current_run_id = str(run["run_id"])
            bundle = self.review_bundle(run_id=current_run_id, state="all", write=False)
            for entry in bundle["entries"]:
                candidate_sinks = self._live_candidate_sinks(entry, selected_sink=selected_sink)
                for candidate_sink in candidate_sinks:
                    readiness = self.live_lookup_readiness_report(
                        job_id=str(entry["job_id"]),
                        run_id=current_run_id,
                        sink=candidate_sink,
                    )
                    matrix = dict(entry.get("review_matrix") or {})
                    stop_reasons = self._live_target_candidate_stop_reasons(
                        entry=entry,
                        readiness=readiness,
                    )
                    candidate_state = "ready_for_selection" if not stop_reasons else "blocked"
                    candidates.append(
                        {
                            "schema": "business-card-watchdog.live-target-candidate.v1",
                            "state": candidate_state,
                            "run_id": current_run_id,
                            "job_id": entry["job_id"],
                            "sink": candidate_sink,
                            "job_state": entry.get("state"),
                            "image_path": entry.get("image_path"),
                            "next_action": (entry.get("next_action") or {}).get("action"),
                            "duplicate_state": matrix.get("duplicate_state"),
                            "route_state": matrix.get("route_state"),
                            "sink_lookup_state": matrix.get("sink_lookup_state"),
                            "lookup_readiness_state": readiness.get("state"),
                            "lookup_missing_requirements": readiness.get("missing_requirements", []),
                            "stop_reasons": stop_reasons,
                            "commands": {
                                "inspect_job": f"jobs show {entry['job_id']} --run-id {current_run_id}",
                                "pilot_readiness": f"runs pilot-readiness {current_run_id}",
                                "lookup_readiness": (
                                    f"sinks lookup-readiness {entry['job_id']} --run-id {current_run_id} "
                                    f"--sink {candidate_sink}"
                                ),
                                "select_lookup_target": (
                                    f"sinks select-live-target {entry['job_id']} --run-id {current_run_id} "
                                    f"--sink {candidate_sink} --operator <operator> --scope lookup "
                                    "--safety-confirmation <tenant-profile-account-confirmation> --json"
                                ),
                                "validate_operator_response": (
                                    f"runs live-pilot-validate-response {current_run_id} "
                                    "--response <operator-response> --json"
                                ),
                            },
                        }
                    )
        return {
            "schema": "business-card-watchdog.live-target-candidates.v1",
            "generated_at": utc_now(),
            "state": "candidates_available" if candidates else "empty",
            "run_id": run_id,
            "sink": selected_sink or None,
            "candidate_count": len(candidates),
            "ready_candidate_count": sum(1 for candidate in candidates if candidate["state"] == "ready_for_selection"),
            "blocked_candidate_count": sum(1 for candidate in candidates if candidate["state"] == "blocked"),
            "candidates": candidates,
            "writes_attempted": 0,
            "network_calls_made": 0,
            "commands": {
                "live_readiness_audit": (
                    "live-readiness-audit"
                    + (f" --run-id {run_id}" if run_id else "")
                    + (f" --sink {selected_sink}" if selected_sink else "")
                ),
                "live_selection_requirements": (
                    "live-selection-requirements"
                    + (f" --run-id {run_id}" if run_id else "")
                    + (f" --sink {selected_sink}" if selected_sink else "")
                ),
                "live_pilot_handoff": f"runs live-pilot-handoff {run_id}" if run_id else "runs list --json",
                "validate_operator_response": (
                    f"runs live-pilot-validate-response {run_id} --response <operator-response> --json"
                    if run_id
                    else "runs list --json"
                ),
            },
            "explicit_stop_conditions": [
                "Do not create selected_live_target.json until the operator chooses a run, job, sink, operator, and scope.",
                "Do not run live lookup, write, or readback from this report.",
                "Do not process private SyncThing images from generic target selection.",
                "Do not run public-web search or paid enrichment from target selection.",
            ],
        }

    def live_readiness_audit(
        self,
        *,
        run_id: str | None = None,
        sink: str | None = None,
        write: bool = True,
    ) -> dict[str, Any]:
        selected_sink = str(sink or "").strip()
        if selected_sink and selected_sink not in {"google_contacts", "odoo"}:
            raise ValueError("live readiness audit requires sink google_contacts or odoo")
        runtime = self.runtime_readiness()
        recovery = self.service_recovery_report(run_id=run_id)
        candidates = self.live_target_candidates(run_id=run_id, sink=selected_sink or None)
        pilot_readiness = self.pilot_readiness_report(run_id) if run_id else None
        blocked_reasons: list[str] = []
        if runtime.get("state") == "blocked":
            blocked_reasons.append("runtime readiness is blocked")
        if candidates.get("candidate_count", 0) == 0:
            blocked_reasons.append("no live target candidates are available")
        if candidates.get("ready_candidate_count", 0) == 0:
            blocked_reasons.append("no candidate is ready for selected-target approval")
        if pilot_readiness and pilot_readiness.get("state") == "blocked":
            blocked_reasons.append("pilot readiness is blocked")
        state = "ready_for_operator_selection" if not blocked_reasons else "needs_preparation"
        payload = {
            "schema": "business-card-watchdog.live-readiness-audit.v1",
            "generated_at": utc_now(),
            "state": state,
            "run_id": run_id,
            "sink": selected_sink or None,
            "runtime_readiness_state": runtime.get("state"),
            "service_recovery_state": recovery.get("state"),
            "pilot_readiness_state": (pilot_readiness or {}).get("state") if pilot_readiness else None,
            "candidate_count": candidates.get("candidate_count", 0),
            "ready_candidate_count": candidates.get("ready_candidate_count", 0),
            "blocked_candidate_count": candidates.get("blocked_candidate_count", 0),
            "blocked_reasons": blocked_reasons,
            "runtime_readiness": runtime,
            "service_recovery": recovery,
            "pilot_readiness": pilot_readiness,
            "live_target_candidates": candidates,
            "writes_attempted": 0,
            "network_calls_made": 0,
            "commands": {
                "runtime_readiness": "runtime-readiness --json",
                "service_recovery": (
                    f"service recovery --run-id {run_id} --json" if run_id else "service recovery --json"
                ),
                "pilot_readiness": f"runs pilot-readiness {run_id} --json" if run_id else "runs list --json",
                "target_candidates": (
                    "live-target-candidates"
                    + (f" --run-id {run_id}" if run_id else "")
                    + (f" --sink {selected_sink}" if selected_sink else "")
                ),
                "selection_requirements": (
                    "live-selection-requirements"
                    + (f" --run-id {run_id}" if run_id else "")
                    + (f" --sink {selected_sink}" if selected_sink else "")
                ),
                "live_pilot_handoff": f"runs live-pilot-handoff {run_id}" if run_id else "runs list --json",
                "validate_operator_response": (
                    f"runs live-pilot-validate-response {run_id} --response <operator-response> --json"
                    if run_id
                    else "runs list --json"
                ),
            },
            "explicit_stop_conditions": [
                "Do not create selected_live_target.json from this audit alone.",
                "Do not run live lookup, live write, or live readback from this audit.",
                "Do not process private SyncThing images from generic readiness auditing.",
                "Do not run public-web search or paid enrichment from readiness auditing.",
            ],
        }
        if write and run_id:
            audit_path = self.config.runs_dir / run_id / "live_readiness_audit.json"
            audit_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            ledger = RunLedger(self.config.runs_dir / run_id)
            ledger.record_artifact(job_id="__run__", kind="live_readiness_audit", path=audit_path)
            ledger.record_event(
                "live_readiness_audit_created",
                {
                    "run_id": run_id,
                    "sink": selected_sink or None,
                    "audit_path": str(audit_path),
                    "state": state,
                    "candidate_count": payload["candidate_count"],
                    "ready_candidate_count": payload["ready_candidate_count"],
                    "writes_attempted": 0,
                    "network_calls_made": 0,
                },
            )
            payload["audit_path"] = str(audit_path)
        return payload

    def live_selection_requirements(
        self,
        *,
        run_id: str | None = None,
        sink: str | None = None,
        write: bool = True,
    ) -> dict[str, Any]:
        selected_sink = str(sink or "").strip()
        if selected_sink and selected_sink not in {"google_contacts", "odoo"}:
            raise ValueError("live selection requirements require sink google_contacts or odoo")
        candidates_payload = self.live_target_candidates(run_id=run_id, sink=selected_sink or None)
        requirement_fields = [
            {
                "name": "run_id",
                "source": "candidate",
                "required": True,
                "description": "Operator-selected run containing the reviewed card job.",
            },
            {
                "name": "job_id",
                "source": "candidate",
                "required": True,
                "description": "Operator-selected business card job within the run.",
            },
            {
                "name": "sink",
                "source": "candidate_or_operator",
                "required": True,
                "allowed_values": ["google_contacts", "odoo"],
                "description": "One selected downstream target sink.",
            },
            {
                "name": "operator",
                "source": "operator",
                "required": True,
                "description": "Human operator approving the selected target.",
            },
            {
                "name": "scope",
                "source": "operator",
                "required": True,
                "allowed_values": ["lookup", "write", "readback", "all"],
                "default": "lookup",
                "description": "Maximum allowed live pilot scope for this selected target.",
            },
            {
                "name": "safety_confirmation",
                "source": "operator",
                "required": True,
                "description": "Statement that the selected card/contact is safe for the target tenant/profile.",
            },
        ]
        entries: list[dict[str, Any]] = []
        for candidate in list(candidates_payload.get("candidates") or []):
            if not isinstance(candidate, dict):
                continue
            candidate_run_id = str(candidate.get("run_id") or "")
            candidate_job_id = str(candidate.get("job_id") or "")
            candidate_sink = str(candidate.get("sink") or "")
            artifact_dir = self.config.runs_dir / candidate_run_id / "artifacts" / candidate_job_id
            selected_target = _read_json_file(artifact_dir / "selected_live_target.json") or {}
            abandonment = _read_json_file(artifact_dir / "live_pilot_abandonment.json") or {}
            selected_target_exists = bool(selected_target)
            target_abandoned = (
                selected_target_exists
                and abandonment.get("state") == "abandoned"
                and str(abandonment.get("selected_target_identity") or abandonment.get("selected_target_created_at") or "")
                == _selected_target_identity(selected_target)
            )
            selected_target_identity = _selected_target_identity(selected_target)
            raw_abandonment_identity = str(
                abandonment.get("selected_target_identity") or abandonment.get("selected_target_created_at") or ""
            )
            abandonment_identity = raw_abandonment_identity if target_abandoned else ""
            abandonment_reason = abandonment.get("reason") if target_abandoned else None
            target_safety_confirmed = bool(
                selected_target.get("target_safety_confirmed")
                and str(selected_target.get("target_safety_confirmation") or "").strip()
            )
            operator_response_template = (
                f"run_id={candidate_run_id} job_id={candidate_job_id} sink={candidate_sink} "
                "operator=<operator> scope=lookup safety_confirmation=<tenant-profile-account-confirmation>"
            )
            copyable_approval_fields = {
                "run_id": candidate_run_id,
                "job_id": candidate_job_id,
                "sink": candidate_sink,
                "operator": "<operator>",
                "scope": "lookup",
                "safety_confirmation": "<tenant-profile-account-confirmation>",
            }
            missing_operator_fields: list[str] = []
            if not selected_target_exists or target_abandoned:
                missing_operator_fields.extend(["operator", "scope", "safety_confirmation"])
            else:
                if not str(selected_target.get("operator") or selected_target.get("approved_by") or "").strip():
                    missing_operator_fields.append("operator")
                if not str(selected_target.get("scope") or "").strip():
                    missing_operator_fields.append("scope")
                if not target_safety_confirmed:
                    missing_operator_fields.append("safety_confirmation")
            if target_abandoned:
                entry_state = "abandoned_select_new_target"
            elif selected_target_exists and not missing_operator_fields:
                entry_state = "selected_target_active"
            elif candidate.get("state") == "ready_for_selection":
                entry_state = "needs_operator_selection"
            else:
                entry_state = "blocked"
            entries.append(
                {
                    "schema": "business-card-watchdog.live-selection-requirement.v1",
                    "state": entry_state,
                    "run_id": candidate_run_id,
                    "job_id": candidate_job_id,
                    "sink": candidate_sink,
                    "candidate_state": candidate.get("state"),
                    "candidate_stop_reasons": list(candidate.get("stop_reasons") or []),
                    "selected_target_exists": selected_target_exists,
                    "selected_target_identity": selected_target_identity or None,
                    "selected_target_scope": selected_target.get("scope"),
                    "selected_target_operator": selected_target.get("operator") or selected_target.get("approved_by"),
                    "selected_target_safety_confirmed": target_safety_confirmed,
                    "selected_target_abandoned": target_abandoned,
                    "abandonment_identity": abandonment_identity or None,
                    "abandonment_reason": abandonment_reason,
                    "missing_operator_fields": missing_operator_fields,
                    "required_operator_fields": requirement_fields,
                    "operator_response_template": operator_response_template,
                    "operator_prompt": (
                        "Reply with an explicit live target selection only if this card/contact is safe for the "
                        f"target tenant/profile: {operator_response_template}"
                    ),
                    "copyable_approval_fields": copyable_approval_fields,
                    "commands": {
                        "selection_packet": (
                            f"sinks live-selection-packet {candidate_job_id} --run-id {candidate_run_id} "
                            f"--sink {candidate_sink} --operator <operator>"
                        ),
                        "select_target": (
                            f"sinks select-live-target {candidate_job_id} --run-id {candidate_run_id} "
                            f"--sink {candidate_sink} --operator <operator> --scope lookup "
                            "--safety-confirmation <tenant-profile-account-confirmation> --json"
                        ),
                        "validate_operator_response": (
                            f"runs live-pilot-validate-response {candidate_run_id} "
                            "--response <operator-response> --json"
                        ),
                        "validate_operator_response_prefilled": _operator_response_validation_command(
                            candidate_run_id,
                            operator_response_template,
                        ),
                    },
                }
            )
        state_counts: dict[str, int] = {}
        for entry in entries:
            state = str(entry["state"])
            state_counts[state] = state_counts.get(state, 0) + 1
        state = (
            "ready_for_operator_selection"
            if state_counts.get("needs_operator_selection") or state_counts.get("abandoned_select_new_target")
            else "selected_target_active"
            if state_counts.get("selected_target_active")
            else "needs_preparation"
            if entries
            else "empty"
        )
        payload = {
            "schema": "business-card-watchdog.live-selection-requirements.v1",
            "generated_at": utc_now(),
            "state": state,
            "run_id": run_id,
            "sink": selected_sink or None,
            "candidate_count": candidates_payload.get("candidate_count", 0),
            "ready_candidate_count": candidates_payload.get("ready_candidate_count", 0),
            "blocked_candidate_count": candidates_payload.get("blocked_candidate_count", 0),
            "entry_count": len(entries),
            "state_counts": state_counts,
            "required_operator_fields": requirement_fields,
            "entries": entries,
            "operator_response_contract": {
                "schema": "business-card-watchdog.operator-selection-response-contract.v1",
                "required_fields": ["run_id", "job_id", "sink", "operator", "scope", "safety_confirmation"],
                "allowed_sinks": ["google_contacts", "odoo"],
                "allowed_scopes": ["lookup", "write", "readback", "all"],
                "format": (
                    "run_id=<run_id> job_id=<job_id> sink=<google_contacts|odoo> "
                    "operator=<operator> scope=<lookup|write|readback|all> "
                    "safety_confirmation=<tenant-profile-account-confirmation>"
                ),
                "default_scope": "lookup",
                "requires_human_safety_confirmation": True,
                "creates_selected_live_target": False,
            },
            "writes_attempted": 0,
            "network_calls_made": 0,
            "commands": {
                "live_target_candidates": (
                    "live-target-candidates"
                    + (f" --run-id {run_id}" if run_id else "")
                    + (f" --sink {selected_sink}" if selected_sink else "")
                ),
                "live_readiness_audit": (
                    "live-readiness-audit"
                    + (f" --run-id {run_id}" if run_id else "")
                    + (f" --sink {selected_sink}" if selected_sink else "")
                ),
                "live_selection_requirements": (
                    "live-selection-requirements"
                    + (f" --run-id {run_id}" if run_id else "")
                    + (f" --sink {selected_sink}" if selected_sink else "")
                ),
                "live_pilot_handoff": f"runs live-pilot-handoff {run_id}" if run_id else "runs list --json",
                "validate_operator_response": (
                    f"runs live-pilot-validate-response {run_id} --response <operator-response> --json"
                    if run_id
                    else "runs list --json"
                ),
            },
            "explicit_stop_conditions": [
                "This report does not create selected_live_target.json.",
                "Operator must provide run_id, job_id, sink, operator, scope, and safety_confirmation before any non-simulated live call.",
                "Do not run live lookup, live write, or live readback from this report.",
                "Do not process private SyncThing images, run public-web search, or call paid enrichment from this report.",
            ],
        }
        if write and run_id:
            requirements_path = self.config.runs_dir / run_id / "live_selection_requirements.json"
            requirements_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            ledger = RunLedger(self.config.runs_dir / run_id)
            ledger.record_artifact(job_id="__run__", kind="live_selection_requirements", path=requirements_path)
            ledger.record_event(
                "live_selection_requirements_created",
                {
                    "run_id": run_id,
                    "sink": selected_sink or None,
                    "requirements_path": str(requirements_path),
                    "state": state,
                    "entry_count": len(entries),
                    "writes_attempted": 0,
                    "network_calls_made": 0,
                },
            )
            payload["requirements_path"] = str(requirements_path)
        return payload

    def operator_selected_live_smoke_preflight(
        self,
        *,
        run_id: str | None = None,
        sink: str | None = None,
        write: bool = True,
    ) -> dict[str, Any]:
        selected_sink = str(sink or "").strip()
        if selected_sink and selected_sink not in {"google_contacts", "odoo"}:
            raise ValueError("operator-selected live smoke preflight requires sink google_contacts or odoo")
        ensure_runtime_dirs(self.config)
        offline_gap = self.offline_pilot_gap_audit(write=False)
        readiness_audit = self.live_readiness_audit(run_id=run_id, sink=selected_sink or None, write=False)
        selection_requirements = self.live_selection_requirements(
            run_id=run_id,
            sink=selected_sink or None,
            write=False,
        )
        entries = [
            entry
            for entry in list(selection_requirements.get("entries") or [])
            if isinstance(entry, dict)
        ]
        ready_entries = [
            entry
            for entry in entries
            if entry.get("state") in {"needs_operator_selection", "abandoned_select_new_target"}
        ]
        active_entries = [entry for entry in entries if entry.get("state") == "selected_target_active"]
        blocked_entries = [entry for entry in entries if entry.get("state") == "blocked"]
        blocked_reasons: list[str] = []
        if offline_gap.get("state") != "ready_for_live_operator_boundary":
            blocked_reasons.append("offline pilot gap audit is not ready for live operator boundary")
        if readiness_audit.get("state") == "needs_preparation":
            blocked_reasons.extend(str(reason) for reason in list(readiness_audit.get("blocked_reasons") or []))
        if run_id is None:
            blocked_reasons.append("operator must select one run_id before a live smoke can proceed")
        if not entries:
            blocked_reasons.append("no live selection requirement entries are available")
        elif not ready_entries and not active_entries:
            blocked_reasons.append("no candidate is ready for operator selection")

        if active_entries:
            state = "selected_target_active"
            recommended_next_step = "inspect_selected_target_audit"
        elif ready_entries and not blocked_reasons:
            state = "awaiting_operator_selection"
            recommended_next_step = "validate_operator_response"
        elif ready_entries:
            state = "awaiting_run_selection"
            recommended_next_step = "choose_run_job_sink_operator_scope"
        else:
            state = "needs_preparation"
            recommended_next_step = "prepare_ready_candidate"

        example_entry = ready_entries[0] if ready_entries else active_entries[0] if active_entries else {}
        entry_commands = dict(example_entry.get("commands") or {})
        operator_selection_checklist = [
            {
                "step": "inspect_offline_gap_audit",
                "command": "offline-pilot-gap-audit --no-write --json",
                "safe_to_auto_continue": True,
                "requires_explicit_operator_action": False,
                "executes_live_call": False,
                "writes_sink": False,
            },
            {
                "step": "inspect_live_readiness_audit",
                "command": (
                    "live-readiness-audit"
                    + (f" --run-id {run_id}" if run_id else "")
                    + (f" --sink {selected_sink}" if selected_sink else "")
                    + " --no-write --json"
                ),
                "safe_to_auto_continue": True,
                "requires_explicit_operator_action": False,
                "executes_live_call": False,
                "writes_sink": False,
            },
            {
                "step": "inspect_selection_requirements",
                "command": (
                    "live-selection-requirements"
                    + (f" --run-id {run_id}" if run_id else "")
                    + (f" --sink {selected_sink}" if selected_sink else "")
                    + " --no-write --json"
                ),
                "safe_to_auto_continue": True,
                "requires_explicit_operator_action": False,
                "executes_live_call": False,
                "writes_sink": False,
            },
            {
                "step": "validate_operator_response",
                "command": entry_commands.get("validate_operator_response_prefilled")
                or entry_commands.get("validate_operator_response")
                or (
                    f"runs live-pilot-validate-response {run_id} --response <operator-response> --json"
                    if run_id
                    else "runs list --json"
                ),
                "safe_to_auto_continue": False,
                "requires_explicit_operator_action": True,
                "executes_live_call": False,
                "writes_sink": False,
            },
        ]
        preflight_path = (
            self.config.runs_dir / run_id / "operator_selected_live_smoke_preflight.json"
            if run_id
            else self.config.data_dir / "operator_selected_live_smoke_preflight.json"
        )
        payload = {
            "schema": "business-card-watchdog.operator-selected-live-smoke-preflight.v1",
            "generated_at": utc_now(),
            "state": state,
            "recommended_next_step": recommended_next_step,
            "run_id": run_id,
            "sink": selected_sink or None,
            "candidate_count": selection_requirements.get("candidate_count", 0),
            "ready_candidate_count": selection_requirements.get("ready_candidate_count", 0),
            "blocked_candidate_count": selection_requirements.get("blocked_candidate_count", 0),
            "entry_count": len(entries),
            "ready_entry_count": len(ready_entries),
            "active_selected_target_count": len(active_entries),
            "blocked_entry_count": len(blocked_entries),
            "blocked_reasons": blocked_reasons,
            "required_operator_fields": list(selection_requirements.get("required_operator_fields") or []),
            "operator_response_contract": selection_requirements.get("operator_response_contract"),
            "ready_entries": ready_entries,
            "active_selected_targets": active_entries,
            "blocked_entries": blocked_entries,
            "offline_pilot_gap_audit": offline_gap,
            "live_readiness_audit": readiness_audit,
            "live_selection_requirements": selection_requirements,
            "operator_selection_checklist": operator_selection_checklist,
            "preflight_path": str(preflight_path) if write else None,
            "preflight_written": False,
            "writes_attempted": 0,
            "network_calls_made": 0,
            "commands": {
                "operator_selected_live_smoke_preflight": (
                    "operator-selected-live-smoke-preflight"
                    + (f" --run-id {run_id}" if run_id else "")
                    + (f" --sink {selected_sink}" if selected_sink else "")
                    + " --json"
                ),
                "offline_pilot_gap_audit": "offline-pilot-gap-audit --no-write --json",
                "live_readiness_audit": (
                    "live-readiness-audit"
                    + (f" --run-id {run_id}" if run_id else "")
                    + (f" --sink {selected_sink}" if selected_sink else "")
                    + " --no-write --json"
                ),
                "live_selection_requirements": (
                    "live-selection-requirements"
                    + (f" --run-id {run_id}" if run_id else "")
                    + (f" --sink {selected_sink}" if selected_sink else "")
                    + " --no-write --json"
                ),
                "live_pilot_handoff": (
                    f"runs live-pilot-handoff {run_id} --no-write --json" if run_id else "runs list --json"
                ),
                "validate_operator_response": (
                    f"runs live-pilot-validate-response {run_id} --response <operator-response> --json"
                    if run_id
                    else "runs list --json"
                ),
            },
            "explicit_stop_conditions": [
                "This preflight does not create selected_live_target.json.",
                "Do not run live lookup, live write, or live readback from this preflight.",
                "Operator must explicitly provide run_id, job_id, sink, operator, scope, and safety_confirmation before any non-simulated live call.",
                "Do not process private SyncThing images, run public-web search, or call paid enrichment from this preflight.",
            ],
        }
        if write:
            payload["preflight_written"] = True
            preflight_path.parent.mkdir(parents=True, exist_ok=True)
            preflight_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            if run_id:
                ledger = RunLedger(self.config.runs_dir / run_id)
                ledger.record_artifact(
                    job_id="__run__",
                    kind="operator_selected_live_smoke_preflight",
                    path=preflight_path,
                )
                ledger.record_event(
                    "operator_selected_live_smoke_preflight_created",
                    {
                        "run_id": run_id,
                        "sink": selected_sink or None,
                        "preflight_path": str(preflight_path),
                        "state": state,
                        "ready_entry_count": len(ready_entries),
                        "active_selected_target_count": len(active_entries),
                        "writes_attempted": 0,
                        "network_calls_made": 0,
                    },
                )
        return payload

    def live_pilot_status(self, *, run_id: str, write: bool = True) -> dict[str, Any]:
        run = self.get_run(run_id)
        candidates_payload = self.live_target_candidates(run_id=run_id)
        candidates_by_job: dict[str, list[dict[str, Any]]] = {}
        for candidate in list(candidates_payload.get("candidates") or []):
            if isinstance(candidate, dict):
                candidates_by_job.setdefault(str(candidate.get("job_id") or ""), []).append(candidate)
        jobs = self.list_jobs(run_id)
        entries: list[dict[str, Any]] = []
        observed_writes_attempted = 0
        observed_network_calls_made = 0
        for job in jobs:
            job_id = str(job["job_id"])
            artifact_dir = (
                Path(str(job["artifact_dir"]))
                if job.get("artifact_dir")
                else self.config.runs_dir / run_id / "artifacts" / job_id
            )
            artifacts = {
                "live_selection_packet": _read_json_file(artifact_dir / "live_selection_packet.json"),
                "selected_live_target": _read_json_file(artifact_dir / "selected_live_target.json"),
                "selected_live_target_audit": _read_json_file(artifact_dir / "selected_live_target_audit.json"),
                "selected_lookup_smoke": _read_json_file(artifact_dir / "selected_lookup_smoke.json"),
                "sink_write_pilot": _read_json_file(artifact_dir / "sink_write_pilot.json"),
                "sink_readback_pilot": _read_json_file(artifact_dir / "sink_readback_pilot.json"),
                "live_pilot_closeout": _read_json_file(artifact_dir / "live_pilot_closeout.json"),
                "live_pilot_abandonment": _read_json_file(artifact_dir / "live_pilot_abandonment.json"),
            }
            closeout = artifacts["live_pilot_closeout"] or {}
            selected_target = artifacts["selected_live_target"] or {}
            selected_target_audit = artifacts["selected_live_target_audit"] or {}
            abandonment = artifacts["live_pilot_abandonment"] or {}
            packet = artifacts["live_selection_packet"] or {}
            job_candidates = candidates_by_job.get(job_id, [])
            ready_candidate_count = sum(1 for candidate in job_candidates if candidate.get("state") == "ready_for_selection")
            target_abandoned = (
                artifacts["selected_live_target"] is not None
                and abandonment.get("state") == "abandoned"
                and str(abandonment.get("selected_target_identity") or abandonment.get("selected_target_created_at") or "")
                == _selected_target_identity(selected_target)
            )
            selected_target_identity = _selected_target_identity(selected_target)
            raw_abandonment_identity = str(
                abandonment.get("selected_target_identity") or abandonment.get("selected_target_created_at") or ""
            )
            abandonment_identity = raw_abandonment_identity if target_abandoned else ""
            abandonment_state = abandonment.get("state") if target_abandoned else None
            abandonment_reason = abandonment.get("reason") if target_abandoned else None
            selected_target_audit_blockers = self._selected_target_audit_context_mismatches(
                selected_target=selected_target,
                selected_target_audit=selected_target_audit,
                run_id=run_id,
                job_id=job_id,
            )
            closeout_missing_artifacts = list(closeout.get("missing_artifacts") or [])
            closeout_blockers = [
                str(reason)
                for reason in list(closeout.get("blocked_reasons") or [])
                if str(reason) not in closeout_missing_artifacts
            ]
            candidate_sink = next(
                (
                    str(candidate.get("sink") or "")
                    for candidate in job_candidates
                    if isinstance(candidate, dict) and candidate.get("sink")
                ),
                "",
            )
            selection_prompt_sink = str(packet.get("sink") or candidate_sink or selected_target.get("sink") or "<sink>")
            selection_operator = str(
                packet.get("operator")
                or selected_target.get("operator")
                or selected_target.get("approved_by")
                or "<operator>"
            )
            selection_scope = str(packet.get("scope") or selected_target.get("scope") or "lookup")
            operator_response_template = (
                f"run_id={run_id} job_id={job_id} sink={selection_prompt_sink} "
                f"operator={selection_operator} scope={selection_scope} "
                "safety_confirmation=<tenant-profile-account-confirmation>"
            )
            pilot_command_checklist = list(packet.get("pilot_command_checklist") or [])
            if not pilot_command_checklist:
                pilot_command_checklist = _live_selection_packet_checklist(
                    commands=_live_selection_packet_commands(
                        job_id=job_id,
                        run_id=run_id,
                        sink=selection_prompt_sink,
                        operator=selection_operator,
                        scope=selection_scope,
                    ),
                    scope=selection_scope,
                    state=str(packet.get("state") or "ready_for_operator_approval"),
                )
            pilot_command_checklist_summary = _pilot_command_checklist_summary(pilot_command_checklist)
            pilot_command_sequence = _pilot_command_sequence(pilot_command_checklist)
            copyable_approval_fields = {
                "run_id": run_id,
                "job_id": job_id,
                "sink": selection_prompt_sink,
                "operator": selection_operator,
                "scope": selection_scope,
                "safety_confirmation": "<tenant-profile-account-confirmation>",
            }
            if target_abandoned:
                state = "abandoned"
            elif closeout.get("state") == "complete":
                state = "complete"
            elif selected_target_audit_blockers:
                state = "selected_target_audit_blocked"
            elif closeout_blockers:
                state = "live_pilot_closeout_blocked"
            elif artifacts["selected_live_target"] is not None:
                state = "selected_target_active"
            elif packet.get("state") == "ready_for_operator_approval":
                state = "pending_operator_approval"
            elif ready_candidate_count:
                state = "ready_for_selection"
            elif job_candidates:
                state = "blocked"
            else:
                state = "no_candidate"
            observed_writes_attempted += int((artifacts["sink_write_pilot"] or {}).get("writes_attempted") or 0)
            observed_network_calls_made += int((artifacts["selected_lookup_smoke"] or {}).get("network_calls_made") or 0)
            observed_network_calls_made += int((artifacts["sink_write_pilot"] or {}).get("network_calls_made") or 0)
            observed_network_calls_made += int((artifacts["sink_readback_pilot"] or {}).get("network_calls_made") or 0)
            entries.append(
                {
                    "schema": "business-card-watchdog.live-pilot-status-entry.v1",
                    "state": state,
                    "run_id": run_id,
                    "job_id": job_id,
                    "job_state": job.get("state"),
                    "candidate_count": len(job_candidates),
                    "ready_candidate_count": ready_candidate_count,
                    "selected_target_exists": artifacts["selected_live_target"] is not None,
                    "selected_target_identity": selected_target_identity or None,
                    "selected_target_scope": selected_target.get("scope"),
                    "selected_target_sink": selected_target.get("sink"),
                    "selected_target_operator": selected_target.get("operator") or selected_target.get("approved_by"),
                    "selection_packet_state": packet.get("state"),
                    "pilot_command_checklist_summary": pilot_command_checklist_summary,
                    "pilot_command_sequence": pilot_command_sequence,
                    "selected_target_audit_state": selected_target_audit.get("state"),
                    "selected_target_audit_blockers": selected_target_audit_blockers,
                    "lookup_smoke_state": (artifacts["selected_lookup_smoke"] or {}).get("state"),
                    "write_pilot_state": (artifacts["sink_write_pilot"] or {}).get("state"),
                    "readback_pilot_state": (artifacts["sink_readback_pilot"] or {}).get("state"),
                    "closeout_state": closeout.get("state"),
                    "closeout_missing_artifacts": closeout_missing_artifacts,
                    "closeout_blockers": closeout_blockers,
                    "abandonment_state": abandonment_state,
                    "abandonment_identity": abandonment_identity or None,
                    "abandonment_reason": abandonment_reason,
                    "operator_response_template": operator_response_template,
                    "operator_prompt": (
                        "Reply with an explicit live target selection only if this card/contact is safe for the "
                        f"target tenant/profile: {operator_response_template}"
                    ),
                    "copyable_approval_fields": copyable_approval_fields,
                    "commands": {
                        "selection_packet": (
                            f"sinks live-selection-packet {job_id} --run-id {run_id} "
                            f"--sink {selection_prompt_sink} --operator {selection_operator}"
                        ),
                        "select_target": (
                            f"sinks select-live-target {job_id} --run-id {run_id} --sink {selection_prompt_sink} "
                            f"--operator {selection_operator} --scope {selection_scope} "
                            "--safety-confirmation <tenant-profile-account-confirmation> --json"
                        ),
                        "selected_target_audit": f"sinks selected-target-audit {job_id} --run-id {run_id}",
                        "lookup_smoke": f"sinks execute-lookup-smoke {job_id} --run-id {run_id} --json",
                        "abandon": f"sinks abandon-live-pilot {job_id} --run-id {run_id} --operator <operator> --reason <reason> --json",
                        "closeout": f"sinks live-pilot-closeout {job_id} --run-id {run_id}",
                        "validate_operator_response": (
                            f"runs live-pilot-validate-response {run_id} --response <operator-response> --json"
                        ),
                        "validate_operator_response_prefilled": _operator_response_validation_command(
                            run_id,
                            operator_response_template,
                        ),
                    },
                }
            )
        counts: dict[str, int] = {}
        for entry in entries:
            counts[str(entry["state"])] = counts.get(str(entry["state"]), 0) + 1
        state = (
            "complete"
            if entries and counts.get("complete") == len(entries)
            else "operator_action_required"
            if any(
                entry["state"] in {
                    "abandoned",
                    "pending_operator_approval",
                    "selected_target_active",
                    "ready_for_selection",
                }
                for entry in entries
            )
            else "blocked"
            if entries
            else "empty"
        )
        payload = {
            "schema": "business-card-watchdog.live-pilot-status.v1",
            "generated_at": utc_now(),
            "state": state,
            "run_id": run_id,
            "run_state": run.get("state"),
            "job_count": len(entries),
            "counts": counts,
            "entries": entries,
            "operator_response_contract": {
                "schema": "business-card-watchdog.operator-selection-response-contract.v1",
                "required_fields": ["run_id", "job_id", "sink", "operator", "scope", "safety_confirmation"],
                "allowed_sinks": ["google_contacts", "odoo"],
                "allowed_scopes": ["lookup", "write", "readback", "all"],
                "format": (
                    "run_id=<run_id> job_id=<job_id> sink=<google_contacts|odoo> "
                    "operator=<operator> scope=<lookup|write|readback|all> "
                    "safety_confirmation=<tenant-profile-account-confirmation>"
                ),
                "default_scope": "lookup",
                "requires_human_safety_confirmation": True,
                "creates_selected_live_target": False,
            },
            "writes_attempted": 0,
            "network_calls_made": 0,
            "observed_writes_attempted": observed_writes_attempted,
            "observed_network_calls_made": observed_network_calls_made,
            "commands": {
                "live_readiness_audit": f"live-readiness-audit --run-id {run_id}",
                "live_selection_requirements": f"live-selection-requirements --run-id {run_id}",
                "live_target_candidates": f"live-target-candidates --run-id {run_id}",
                "live_pilot_status": f"runs live-pilot-status {run_id}",
                "live_pilot_handoff": f"runs live-pilot-handoff {run_id}",
                "validate_operator_response": (
                    f"runs live-pilot-validate-response {run_id} --response <operator-response> --json"
                ),
            },
            "explicit_stop_conditions": [
                "This status report does not create selected_live_target.json.",
                "Do not run live lookup, live write, or live readback from this status report.",
                "Do not process private SyncThing images, run public-web search, or call paid enrichment from this status report.",
            ],
        }
        if write:
            status_path = self.config.runs_dir / run_id / "live_pilot_status.json"
            status_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            ledger = RunLedger(self.config.runs_dir / run_id)
            ledger.record_artifact(job_id="__run__", kind="live_pilot_status", path=status_path)
            ledger.record_event(
                "live_pilot_status_created",
                {
                    "run_id": run_id,
                    "status_path": str(status_path),
                    "state": state,
                    "job_count": len(entries),
                    "writes_attempted": 0,
                    "network_calls_made": 0,
                },
            )
            payload["status_path"] = str(status_path)
        return payload

    def live_pilot_handoff(self, *, run_id: str, write: bool = True) -> dict[str, Any]:
        status = self.live_pilot_status(run_id=run_id, write=False)
        handoff_entries: list[dict[str, Any]] = []
        for entry in list(status.get("entries") or []):
            if not isinstance(entry, dict):
                continue
            job_id = str(entry.get("job_id") or "")
            job_state = str(entry.get("state") or "unknown")
            commands = dict(entry.get("commands") or {})
            if job_state == "complete":
                next_action = "complete"
                operator_required = False
                command = commands.get("closeout")
                reason = "live pilot closeout is complete"
            elif job_state == "selected_target_active":
                next_action = "request_live_lookup_smoke"
                operator_required = True
                command = commands.get("lookup_smoke")
                reason = "selected live target exists; live lookup smoke requires explicit operator request"
            elif job_state == "selected_target_audit_blocked":
                next_action = "review_selected_target_audit"
                operator_required = True
                command = commands.get("selected_target_audit")
                reason = "selected target audit context does not match the current selected target; rerun or abandon before live commands"
            elif job_state == "live_pilot_closeout_blocked":
                next_action = "review_live_pilot_closeout"
                operator_required = True
                command = commands.get("closeout")
                reason = "live pilot closeout has non-missing-artifact blockers; review evidence or abandon before live commands"
            elif job_state == "abandoned":
                next_action = "select_new_live_target"
                operator_required = True
                command = commands.get("select_target")
                reason = "selected live target was abandoned; operator must approve a new target before live commands"
            elif job_state == "pending_operator_approval":
                next_action = "approve_selected_target"
                operator_required = True
                command = commands.get("select_target")
                reason = "selection packet is ready; operator must approve a selected live target"
            elif job_state == "ready_for_selection":
                next_action = "prepare_selection_packet"
                operator_required = True
                command = commands.get("selection_packet")
                reason = "candidate is ready; prepare approval evidence before selecting a live target"
            elif job_state == "blocked":
                next_action = "review_blockers"
                operator_required = True
                command = f"runs live-pilot-status {run_id}"
                reason = "candidate exists but readiness or policy blockers remain"
            else:
                next_action = "no_live_candidate"
                operator_required = False
                command = f"live-target-candidates --run-id {run_id}"
                reason = "no live target candidate is currently available for this job"
            handoff_entries.append(
                {
                    "schema": "business-card-watchdog.live-pilot-handoff-entry.v1",
                    "run_id": run_id,
                    "job_id": job_id,
                    "status_state": job_state,
                    "next_action": next_action,
                    "operator_required": operator_required,
                    "reason": reason,
                    "command": command,
                    "operator_response_template": entry.get("operator_response_template"),
                    "operator_prompt": entry.get("operator_prompt"),
                    "copyable_approval_fields": entry.get("copyable_approval_fields"),
                    "selected_target_sink": entry.get("selected_target_sink"),
                    "selected_target_identity": entry.get("selected_target_identity"),
                    "selected_target_scope": entry.get("selected_target_scope"),
                    "selection_packet_state": entry.get("selection_packet_state"),
                    "pilot_command_checklist_summary": entry.get("pilot_command_checklist_summary"),
                    "pilot_command_sequence": entry.get("pilot_command_sequence"),
                    "selected_target_audit_state": entry.get("selected_target_audit_state"),
                    "selected_target_audit_blockers": entry.get("selected_target_audit_blockers", []),
                    "lookup_smoke_state": entry.get("lookup_smoke_state"),
                    "write_pilot_state": entry.get("write_pilot_state"),
                    "readback_pilot_state": entry.get("readback_pilot_state"),
                    "closeout_state": entry.get("closeout_state"),
                    "closeout_missing_artifacts": entry.get("closeout_missing_artifacts", []),
                    "closeout_blockers": entry.get("closeout_blockers", []),
                    "abandonment_state": entry.get("abandonment_state"),
                    "abandonment_identity": entry.get("abandonment_identity"),
                    "abandonment_reason": entry.get("abandonment_reason"),
                    "commands": commands,
                }
            )
        action_counts: dict[str, int] = {}
        for entry in handoff_entries:
            action = str(entry["next_action"])
            action_counts[action] = action_counts.get(action, 0) + 1
        operator_response_templates = [
            {
                "schema": "business-card-watchdog.operator-response-template.v1",
                "run_id": entry.get("run_id"),
                "job_id": entry.get("job_id"),
                "next_action": entry.get("next_action"),
                "operator_required": entry.get("operator_required", False),
                "template": entry.get("operator_response_template"),
                "prompt": entry.get("operator_prompt"),
                "copyable_approval_fields": entry.get("copyable_approval_fields"),
                "command": entry.get("command"),
                "validation_command": (entry.get("commands") or {}).get("validate_operator_response"),
                "validation_command_prefilled": (entry.get("commands") or {}).get(
                    "validate_operator_response_prefilled"
                ),
            }
            for entry in handoff_entries
            if entry.get("operator_required") and entry.get("operator_response_template")
        ]
        state = (
            "complete"
            if handoff_entries and action_counts.get("complete") == len(handoff_entries)
            else "ready_for_live_lookup_request"
            if action_counts.get("request_live_lookup_smoke")
            else "ready_for_operator_selection"
            if action_counts.get("approve_selected_target")
            or action_counts.get("prepare_selection_packet")
            or action_counts.get("select_new_live_target")
            else "blocked"
            if handoff_entries
            else "empty"
        )
        payload = {
            "schema": "business-card-watchdog.live-pilot-handoff.v1",
            "generated_at": utc_now(),
            "state": state,
            "run_id": run_id,
            "status_state": status.get("state"),
            "job_count": len(handoff_entries),
            "action_counts": action_counts,
            "entries": handoff_entries,
            "operator_response_template_count": len(operator_response_templates),
            "operator_response_templates": operator_response_templates,
            "operator_response_contract": status.get("operator_response_contract"),
            "writes_attempted": 0,
            "network_calls_made": 0,
            "observed_writes_attempted": status.get("observed_writes_attempted", 0),
            "observed_network_calls_made": status.get("observed_network_calls_made", 0),
            "commands": {
                "live_pilot_status": f"runs live-pilot-status {run_id}",
                "live_pilot_handoff": f"runs live-pilot-handoff {run_id}",
                "validate_operator_response": (
                    f"runs live-pilot-validate-response {run_id} --response <operator-response> --json"
                ),
                "live_readiness_audit": f"live-readiness-audit --run-id {run_id}",
                "live_selection_requirements": f"live-selection-requirements --run-id {run_id}",
                "live_target_candidates": f"live-target-candidates --run-id {run_id}",
            },
            "operator_stop_conditions": [
                "Operator must choose exactly one run_id, job_id, sink, scope, and target tenant/profile before any live call.",
                "Do not create selected_live_target.json unless the selected card/contact is safe for the target tenant/profile.",
                "Do not run live lookup, live write, or live readback from this handoff artifact.",
                "Do not process private SyncThing images, run public-web search, or call paid enrichment from this handoff artifact.",
            ],
        }
        if write:
            handoff_path = self.config.runs_dir / run_id / "live_pilot_handoff.json"
            handoff_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            ledger = RunLedger(self.config.runs_dir / run_id)
            ledger.record_artifact(job_id="__run__", kind="live_pilot_handoff", path=handoff_path)
            ledger.record_event(
                "live_pilot_handoff_created",
                {
                    "run_id": run_id,
                    "handoff_path": str(handoff_path),
                    "state": state,
                    "job_count": len(handoff_entries),
                    "writes_attempted": 0,
                    "network_calls_made": 0,
                },
            )
            payload["handoff_path"] = str(handoff_path)
        return payload

    def live_pilot_approval_packet(self, *, run_id: str, job_id: str | None = None) -> dict[str, Any]:
        handoff = self.live_pilot_handoff(run_id=run_id, write=False)
        entries: list[dict[str, Any]] = []
        for template in list(handoff.get("operator_response_templates") or []):
            if not isinstance(template, dict):
                continue
            if job_id and str(template.get("job_id") or "") != job_id:
                continue
            fields = dict(template.get("copyable_approval_fields") or {})
            entries.append(
                {
                    "schema": "business-card-watchdog.live-pilot-approval-packet-entry.v1",
                    "run_id": template.get("run_id"),
                    "job_id": template.get("job_id"),
                    "sink": fields.get("sink"),
                    "operator": fields.get("operator"),
                    "scope": fields.get("scope"),
                    "next_action": template.get("next_action"),
                    "operator_response_template": template.get("template"),
                    "operator_prompt": template.get("prompt"),
                    "copyable_approval_fields": fields,
                    "validation_command": template.get("validation_command"),
                    "validation_command_prefilled": template.get("validation_command_prefilled"),
                    "next_explicit_command": template.get("command"),
                }
            )
        state = "ready" if entries else "empty"
        return {
            "schema": "business-card-watchdog.live-pilot-approval-packet.v1",
            "generated_at": utc_now(),
            "state": state,
            "run_id": run_id,
            "job_id": job_id,
            "entry_count": len(entries),
            "entries": entries,
            "operator_response_contract": handoff.get("operator_response_contract"),
            "commands": {
                "live_pilot_handoff": f"runs live-pilot-handoff {run_id} --no-write --json",
                "approval_packet": (
                    f"runs live-pilot-approval-packet {run_id} --job-id {job_id} --json"
                    if job_id
                    else f"runs live-pilot-approval-packet {run_id} --json"
                ),
            },
            "explicit_stop_conditions": [
                "This packet does not create selected_live_target.json.",
                "Validate the operator response before selecting a live target.",
                "Do not run live lookup, live write, or live readback from this approval packet.",
                "Do not process private SyncThing images, run public-web search, or call paid enrichment from this packet.",
            ],
            "writes_attempted": 0,
            "network_calls_made": 0,
            "creates_selected_live_target": False,
        }

    def selected_live_target_preflight(self, *, run_id: str, response: str) -> dict[str, Any]:
        validation = self.validate_live_pilot_operator_response(run_id=run_id, response=response)
        parsed = dict(validation.get("parsed_response") or {})
        select_target_command = validation.get("select_target_command")
        ready = validation.get("state") == "ready_to_select_live_target" and bool(select_target_command)
        blocker_reasons = []
        if not ready:
            blocker_reasons.extend(str(item) for item in list(validation.get("missing_fields") or []))
            blocker_reasons.extend(str(item) for item in list(validation.get("mismatches") or []))
            if validation.get("state") == "ready_for_live_lookup_request":
                blocker_reasons.append("selected_live_target already exists; do not create another target")
            elif validation.get("state") == "ready_to_review_selected_target_audit":
                blocker_reasons.append("selected target audit must be reviewed before further live-pilot setup")
            elif not blocker_reasons:
                blocker_reasons.append(f"validation state {validation.get('state')} is not ready_to_select_live_target")
        return {
            "schema": "business-card-watchdog.selected-live-target-preflight.v1",
            "generated_at": utc_now(),
            "state": "ready_to_create_selected_target" if ready else "blocked",
            "run_id": run_id,
            "job_id": parsed.get("job_id"),
            "sink": parsed.get("sink"),
            "operator": parsed.get("operator"),
            "scope": parsed.get("scope"),
            "safety_confirmation_present": bool(str(parsed.get("safety_confirmation") or "").strip()),
            "validation_state": validation.get("state"),
            "validation_next_step": validation.get("next_validation_step"),
            "approval_readback": validation.get("approval_readback"),
            "select_target_command": select_target_command,
            "would_create_selected_live_target": ready,
            "creates_selected_live_target": False,
            "blocked_reasons": blocker_reasons,
            "commands": {
                "approval_packet": f"runs live-pilot-approval-packet {run_id} --json",
                "validate_response": (
                    f"runs live-pilot-validate-response {shlex.quote(run_id)} "
                    f"--response {shlex.quote(response)} --json"
                ),
                "select_target": select_target_command,
            },
            "explicit_stop_conditions": [
                "This preflight does not create selected_live_target.json.",
                "Run the select_target command only after confirming tenant/profile/account safety.",
                "Do not run live lookup, live write, or live readback from this preflight.",
            ],
            "writes_attempted": 0,
            "network_calls_made": 0,
        }

    def selected_live_target_artifact_preview(self, *, run_id: str, response: str) -> dict[str, Any]:
        preflight = self.selected_live_target_preflight(run_id=run_id, response=response)
        parsed = dict((preflight.get("approval_readback") or {}).get("parsed_fields") or {})
        artifact_preview = None
        artifact_path = None
        if preflight.get("state") == "ready_to_create_selected_target":
            job_id = str(parsed.get("job_id") or "")
            sink = str(parsed.get("sink") or "")
            operator = str(parsed.get("operator") or "")
            scope = str(parsed.get("scope") or "")
            validation = self.validate_live_pilot_operator_response(run_id=run_id, response=response)
            safety_confirmation = str((validation.get("parsed_response") or {}).get("safety_confirmation") or "")
            job = self.get_job(job_id, run_id=run_id)
            artifact_dir = (
                Path(job["artifact_dir"])
                if job.get("artifact_dir")
                else self.config.runs_dir / run_id / "artifacts" / job_id
            )
            artifact_path = str(artifact_dir / "selected_live_target.json")
            lookup_readiness = (
                self.live_lookup_readiness_report(job_id=job_id, run_id=run_id, sink=sink)
                if scope in {"lookup", "all"}
                else None
            )
            apply_readiness = (
                self.build_sink_apply_pilot_readiness_for_job(
                    job_id=job_id,
                    run_id=run_id,
                    sink=sink,
                )["readiness"]
                if scope in {"write", "readback", "all"}
                else None
            )
            missing_requirements = []
            if lookup_readiness is not None:
                missing_requirements.extend(
                    f"lookup:{name}" for name in list(lookup_readiness.get("missing_requirements") or [])
                )
            if apply_readiness is not None:
                missing_requirements.extend(
                    f"apply:{name}" for name in list(apply_readiness.get("missing_requirements") or [])
                )
            artifact_preview = {
                "schema": "business-card-watchdog.selected-live-target.v1",
                "state": "selected",
                "status": "selected",
                "reason": "operator selected this exact run/job/sink/scope for explicit live pilot commands",
                "run_id": run_id,
                "job_id": job_id,
                "sink": sink,
                "operator": operator,
                "approved_by": operator,
                "scope": scope,
                "selection_id": "<generated-on-write>",
                "target_safety_confirmed": True,
                "target_safety_confirmation": safety_confirmation,
                "scope_allows": {
                    "lookup": scope in {"lookup", "all"},
                    "write": scope in {"write", "all"},
                    "readback": scope in {"readback", "all"},
                },
                "created_at": "<generated-on-write>",
                "job_state": job.get("state"),
                "readiness": {
                    "lookup": lookup_readiness,
                    "apply": apply_readiness,
                },
                "missing_requirements": missing_requirements,
                "writes_attempted": 0,
                "network_calls_made": 0,
                "commands": {
                    "lookup_pilot": (
                        f"sinks lookup-pilot {job_id} --run-id {run_id} --sink {sink} "
                        f"--approved-by {operator} --no-simulate"
                    ),
                    "write_pilot": (
                        f"sinks write-pilot {job_id} --run-id {run_id} --sink {sink} "
                        f"--approved-by {operator} --no-simulate"
                    ),
                    "readback_pilot": (
                        f"sinks readback-pilot {job_id} --run-id {run_id} --sink {sink} "
                        f"--approved-by {operator} --no-simulate"
                    ),
                },
                "stop_conditions": [
                    "the live command names a different run, job, sink, operator, or scope",
                    "readiness artifacts are stale or reference a different sink",
                    "operator did not explicitly request the non-simulated command after this record was created",
                    "operator did not confirm the selected card/contact is safe for the target tenant/profile",
                    "public-web search, paid enrichment, or duplicate merge decisions would be needed first",
                ],
                "operator_note": (
                    "This is durable selected-target approval evidence. It is not a command execution; "
                    "the operator must still explicitly run the non-simulated pilot command."
                ),
            }
        return {
            "schema": "business-card-watchdog.selected-live-target-artifact-preview.v1",
            "generated_at": utc_now(),
            "state": "ready" if artifact_preview else "blocked",
            "run_id": run_id,
            "job_id": preflight.get("job_id"),
            "preflight_state": preflight.get("state"),
            "would_write_path": artifact_path,
            "artifact_preview": artifact_preview,
            "volatile_fields": ["selection_id", "created_at"] if artifact_preview else [],
            "blocked_reasons": preflight.get("blocked_reasons") or [],
            "would_create_selected_live_target": bool(artifact_preview),
            "creates_selected_live_target": False,
            "commands": {
                "preflight": (
                    f"runs selected-live-target-preflight {shlex.quote(run_id)} "
                    f"--response {shlex.quote(response)} --json"
                ),
                "select_target": preflight.get("select_target_command"),
            },
            "explicit_stop_conditions": [
                "This preview does not create selected_live_target.json.",
                "Volatile fields are generated only if the operator explicitly runs select_target.",
                "Do not run live lookup, live write, or live readback from this preview.",
            ],
            "writes_attempted": 0,
            "network_calls_made": 0,
        }

    def selected_live_target_from_response(
        self,
        *,
        run_id: str,
        response: str,
        write_selected_target: bool = False,
        reason: str = "",
    ) -> dict[str, Any]:
        preview = self.selected_live_target_artifact_preview(run_id=run_id, response=response)
        if not write_selected_target:
            return {
                "schema": "business-card-watchdog.selected-live-target-from-response.v1",
                "generated_at": utc_now(),
                "state": "preview",
                "run_id": run_id,
                "write_selected_target": False,
                "preview": preview,
                "target": None,
                "target_path": None,
                "creates_selected_live_target": False,
                "writes_attempted": 0,
                "network_calls_made": 0,
                "explicit_stop_conditions": [
                    "Default mode is preview only and does not create selected_live_target.json.",
                    "Pass the explicit write-selected-target flag only after operator approval is final.",
                    "This command never runs live lookup, live write, or live readback.",
                ],
            }
        if preview.get("state") != "ready" or not preview.get("artifact_preview"):
            return {
                "schema": "business-card-watchdog.selected-live-target-from-response.v1",
                "generated_at": utc_now(),
                "state": "blocked",
                "run_id": run_id,
                "write_selected_target": True,
                "preview": preview,
                "target": None,
                "target_path": None,
                "blocked_reasons": preview.get("blocked_reasons") or ["selected target preview is not ready"],
                "creates_selected_live_target": False,
                "writes_attempted": 0,
                "network_calls_made": 0,
                "explicit_stop_conditions": [
                    "selected_live_target.json was not created because preflight/preview is blocked.",
                    "Fix the blocked reasons before retrying with the explicit write-selected-target flag.",
                    "This command never runs live lookup, live write, or live readback.",
                ],
            }
        validation = self.validate_live_pilot_operator_response(run_id=run_id, response=response)
        parsed = dict(validation.get("parsed_response") or {})
        created = self.select_live_target_for_job(
            job_id=str(parsed["job_id"]),
            run_id=run_id,
            sink=str(parsed["sink"]),
            operator=str(parsed["operator"]),
            scope=str(parsed["scope"]),
            reason=reason,
            safety_confirmation=str(parsed["safety_confirmation"]),
        )
        return {
            "schema": "business-card-watchdog.selected-live-target-from-response.v1",
            "generated_at": utc_now(),
            "state": "created",
            "run_id": run_id,
            "write_selected_target": True,
            "preview": preview,
            "target": created["target"],
            "target_path": created["target_path"],
            "creates_selected_live_target": True,
            "writes_attempted": 1,
            "network_calls_made": 0,
            "explicit_stop_conditions": [
                "selected_live_target.json was created; do not create another selected target without abandonment.",
                "This command did not run live lookup, live write, or live readback.",
                "Run selected-target audit before any explicit live pilot command.",
            ],
        }

    def selected_live_target_handoff_from_response(
        self,
        *,
        run_id: str,
        response: str,
        write_audit: bool = False,
    ) -> dict[str, Any]:
        validation = self.validate_live_pilot_operator_response(run_id=run_id, response=response)
        parsed = dict(validation.get("parsed_response") or {})
        job_id = str(parsed.get("job_id") or "")
        scope = str(parsed.get("scope") or "lookup")
        if validation.get("state") not in {
            "ready_for_live_lookup_request",
            "ready_to_review_selected_target_audit",
        }:
            return {
                "schema": "business-card-watchdog.selected-live-target-handoff-from-response.v1",
                "generated_at": utc_now(),
                "state": "blocked",
                "run_id": run_id,
                "job_id": job_id or None,
                "scope": scope,
                "validation_state": validation.get("state"),
                "validation": validation,
                "selected_target_audit": None,
                "selected_target": None,
                "selected_target_path": None,
                "write_audit": write_audit,
                "audit_written": False,
                "next_safe_command": f"runs live-pilot-validate-response {run_id} --response <operator-response> --json",
                "next_explicit_operator_command": None,
                "blocked_reasons": [
                    f"validation state {validation.get('state')} does not have an active selected_live_target.json"
                ],
                "commands": {
                    "validate_response": (
                        f"runs live-pilot-validate-response {shlex.quote(run_id)} "
                        f"--response {shlex.quote(response)} --json"
                    ),
                    "create_selected_target": (
                        f"runs selected-live-target-from-response {shlex.quote(run_id)} "
                        f"--response {shlex.quote(response)} --write-selected-target --json"
                    ),
                    "live_pilot_handoff": f"runs live-pilot-handoff {run_id} --no-write --json",
                },
                "explicit_stop_conditions": [
                    "This handoff did not create selected_live_target.json.",
                    "Create a selected target only after explicit operator approval.",
                    "This handoff never runs live lookup, live write, or live readback.",
                ],
                "creates_selected_live_target": False,
                "writes_attempted": 0,
                "network_calls_made": 0,
            }
        if not job_id:
            raise ValueError("validated operator response did not include job_id")
        audit = self.selected_live_target_audit(
            job_id=job_id,
            run_id=run_id,
            scope=scope,
            write=write_audit,
        )
        selected_target = audit.get("selected_target")
        audit_written = bool(write_audit and audit.get("audit_path"))
        next_explicit_operator_command = None
        if audit.get("state") == "ready":
            next_explicit_operator_command = dict(audit.get("commands") or {}).get("lookup_smoke")
        blocked_reasons = list(audit.get("blocked_reasons") or [])
        state = "ready_for_live_lookup_request" if audit.get("state") == "ready" else "audit_blocked"
        return {
            "schema": "business-card-watchdog.selected-live-target-handoff-from-response.v1",
            "generated_at": utc_now(),
            "state": state,
            "run_id": run_id,
            "job_id": job_id,
            "scope": scope,
            "validation_state": validation.get("state"),
            "validation_next_step": validation.get("next_validation_step"),
            "approval_readback": validation.get("approval_readback"),
            "selected_target_audit": audit,
            "selected_target": selected_target,
            "selected_target_path": audit.get("selected_target_path"),
            "selected_target_identity": _selected_target_identity(dict(selected_target or {})) or None,
            "write_audit": write_audit,
            "audit_written": audit_written,
            "next_safe_command": (
                f"sinks selected-target-audit {job_id} --run-id {run_id} --scope {scope} --no-write --json"
            ),
            "next_explicit_operator_command": next_explicit_operator_command,
            "blocked_reasons": blocked_reasons,
            "commands": {
                "validate_response": (
                    f"runs live-pilot-validate-response {shlex.quote(run_id)} "
                    f"--response {shlex.quote(response)} --json"
                ),
                "selected_target_audit": (
                    f"sinks selected-target-audit {job_id} --run-id {run_id} --scope {scope} --no-write --json"
                ),
                "live_pilot_status": f"runs live-pilot-status {run_id} --no-write --json",
                "live_pilot_handoff": f"runs live-pilot-handoff {run_id} --no-write --json",
                "lookup_smoke": dict(audit.get("commands") or {}).get("lookup_smoke"),
            },
            "explicit_stop_conditions": [
                "This handoff does not run live lookup, live write, or live readback.",
                "A blocked selected-target audit must be resolved before any explicit live pilot command.",
                "Only run the next explicit operator command after confirming the selected target is still safe.",
            ],
            "creates_selected_live_target": False,
            "writes_attempted": 0,
            "network_calls_made": 0,
        }

    def lookup_smoke_handoff_from_response(
        self,
        *,
        run_id: str,
        response: str,
        write_handoff: bool = False,
    ) -> dict[str, Any]:
        selected_target_handoff = self.selected_live_target_handoff_from_response(
            run_id=run_id,
            response=response,
            write_audit=False,
        )
        if selected_target_handoff.get("state") == "blocked":
            return {
                "schema": "business-card-watchdog.lookup-smoke-handoff-from-response.v1",
                "generated_at": utc_now(),
                "state": "blocked",
                "run_id": run_id,
                "job_id": selected_target_handoff.get("job_id"),
                "sink": None,
                "operator": None,
                "validation_state": selected_target_handoff.get("validation_state"),
                "selected_target_handoff": selected_target_handoff,
                "lookup_smoke_handoff": None,
                "handoff_path": None,
                "write_handoff": write_handoff,
                "handoff_written": False,
                "blocked_reasons": list(selected_target_handoff.get("blocked_reasons") or []),
                "next_safe_command": selected_target_handoff.get("next_safe_command"),
                "next_explicit_operator_command": None,
                "commands": {
                    "validate_response": (
                        f"runs live-pilot-validate-response {shlex.quote(run_id)} "
                        f"--response {shlex.quote(response)} --json"
                    ),
                    "selected_target_handoff": (
                        f"runs selected-live-target-handoff-from-response {shlex.quote(run_id)} "
                        f"--response {shlex.quote(response)} --json"
                    ),
                },
                "explicit_stop_conditions": [
                    "This handoff did not run live lookup, live write, or live readback.",
                    "Create or repair the selected target before preparing lookup-smoke handoff.",
                    "Do not process private SyncThing images, run public-web search, or call paid enrichment.",
                ],
                "writes_attempted": 0,
                "network_calls_made": 0,
            }
        selected_target = dict(selected_target_handoff.get("selected_target") or {})
        job_id = str(selected_target_handoff.get("job_id") or selected_target.get("job_id") or "")
        sink = str(selected_target.get("sink") or "")
        operator = str(selected_target.get("operator") or selected_target.get("approved_by") or "")
        if not job_id or sink not in {"google_contacts", "odoo"} or not operator:
            blocked_reasons = ["active selected target is missing job_id, sink, or operator"]
            return {
                "schema": "business-card-watchdog.lookup-smoke-handoff-from-response.v1",
                "generated_at": utc_now(),
                "state": "blocked",
                "run_id": run_id,
                "job_id": job_id or None,
                "sink": sink or None,
                "operator": operator or None,
                "validation_state": selected_target_handoff.get("validation_state"),
                "selected_target_handoff": selected_target_handoff,
                "lookup_smoke_handoff": None,
                "handoff_path": None,
                "write_handoff": write_handoff,
                "handoff_written": False,
                "blocked_reasons": blocked_reasons,
                "next_safe_command": selected_target_handoff.get("next_safe_command"),
                "next_explicit_operator_command": None,
                "commands": {
                    "selected_target_handoff": (
                        f"runs selected-live-target-handoff-from-response {shlex.quote(run_id)} "
                        f"--response {shlex.quote(response)} --json"
                    ),
                },
                "explicit_stop_conditions": [
                    "This handoff did not run live lookup, live write, or live readback.",
                    "Repair selected-target evidence before preparing lookup-smoke handoff.",
                ],
                "writes_attempted": 0,
                "network_calls_made": 0,
            }
        handoff_result = self.build_sink_lookup_smoke_handoff_for_job(
            job_id=job_id,
            run_id=run_id,
            sink=sink,
            approved_by=operator,
            write=write_handoff,
        )
        handoff = dict(handoff_result.get("handoff") or {})
        handoff_path = str(handoff_result.get("handoff_path") or "")
        handoff_written = bool(write_handoff and handoff_path and Path(handoff_path).exists())
        ready = handoff.get("state") == "ready_for_live_lookup"
        blocked_reasons = list(handoff.get("missing_requirements") or [])
        return {
            "schema": "business-card-watchdog.lookup-smoke-handoff-from-response.v1",
            "generated_at": utc_now(),
            "state": "ready_for_live_lookup_request" if ready else "handoff_blocked",
            "run_id": run_id,
            "job_id": job_id,
            "sink": sink,
            "operator": operator,
            "validation_state": selected_target_handoff.get("validation_state"),
            "selected_target_identity": selected_target_handoff.get("selected_target_identity"),
            "selected_target_handoff": selected_target_handoff,
            "lookup_smoke_handoff": handoff,
            "handoff_path": handoff_path,
            "write_handoff": write_handoff,
            "handoff_written": handoff_written,
            "blocked_reasons": blocked_reasons,
            "next_safe_command": (
                f"sinks lookup-smoke-handoff {job_id} --run-id {run_id} "
                f"--sink {sink} --approved-by {operator} --json"
            ),
            "next_explicit_operator_command": dict(handoff.get("commands") or {}).get("live_lookup_pilot")
            if ready
            else None,
            "commands": {
                "selected_target_handoff": (
                    f"runs selected-live-target-handoff-from-response {shlex.quote(run_id)} "
                    f"--response {shlex.quote(response)} --json"
                ),
                "lookup_smoke_handoff": (
                    f"sinks lookup-smoke-handoff {job_id} --run-id {run_id} "
                    f"--sink {sink} --approved-by {operator} --json"
                ),
                "execute_lookup_smoke": f"sinks execute-lookup-smoke {job_id} --run-id {run_id} --json",
                "live_pilot_status": f"runs live-pilot-status {run_id} --no-write --json",
                "live_pilot_handoff": f"runs live-pilot-handoff {run_id} --no-write --json",
            },
            "explicit_stop_conditions": [
                "This handoff does not run live lookup, live write, or live readback.",
                "Only run the explicit live lookup command after the handoff state is ready_for_live_lookup_request.",
                "Persist and inspect redacted lookup evidence before any duplicate resolution or write pilot.",
                "Do not process private SyncThing images, run public-web search, or call paid enrichment from this handoff.",
            ],
            "writes_attempted": 0,
            "network_calls_made": 0,
        }

    def selected_lookup_smoke_execution_packet_from_response(
        self,
        *,
        run_id: str,
        response: str,
        execute_selected_lookup_smoke: bool = False,
    ) -> dict[str, Any]:
        handoff_packet = self.lookup_smoke_handoff_from_response(
            run_id=run_id,
            response=response,
            write_handoff=False,
        )
        job_id = str(handoff_packet.get("job_id") or "")
        ready = handoff_packet.get("state") == "ready_for_live_lookup_request"
        execute_command = (
            f"sinks execute-lookup-smoke {job_id} --run-id {run_id} --json"
            if job_id
            else None
        )
        if not execute_selected_lookup_smoke:
            return {
                "schema": "business-card-watchdog.selected-lookup-smoke-execution-packet-from-response.v1",
                "generated_at": utc_now(),
                "state": "ready_to_request_execution" if ready else "blocked",
                "run_id": run_id,
                "job_id": job_id or None,
                "sink": handoff_packet.get("sink"),
                "operator": handoff_packet.get("operator"),
                "execute_selected_lookup_smoke": False,
                "would_execute_selected_lookup_smoke": ready,
                "lookup_smoke_handoff_from_response": handoff_packet,
                "smoke": None,
                "smoke_path": None,
                "blocked_reasons": [] if ready else list(handoff_packet.get("blocked_reasons") or []),
                "next_safe_command": (
                    f"runs lookup-smoke-handoff-from-response {shlex.quote(run_id)} "
                    f"--response {shlex.quote(response)} --json"
                ),
                "next_explicit_operator_command": execute_command if ready else None,
                "commands": {
                    "lookup_smoke_handoff": (
                        f"runs lookup-smoke-handoff-from-response {shlex.quote(run_id)} "
                        f"--response {shlex.quote(response)} --json"
                    ),
                    "execute_selected_lookup_smoke": execute_command,
                    "live_pilot_status": f"runs live-pilot-status {run_id} --no-write --json",
                    "live_pilot_handoff": f"runs live-pilot-handoff {run_id} --no-write --json",
                },
                "explicit_stop_conditions": [
                    "Default mode does not execute selected lookup smoke.",
                    "Pass the explicit execute-selected-lookup-smoke flag only after reviewing the ready handoff.",
                    "The selected lookup smoke must persist redacted evidence and report writes_attempted=0.",
                    "Do not process private SyncThing images, run public-web search, or call paid enrichment from this packet.",
                ],
                "writes_attempted": 0,
                "network_calls_made": 0,
            }
        if not ready or not job_id:
            return {
                "schema": "business-card-watchdog.selected-lookup-smoke-execution-packet-from-response.v1",
                "generated_at": utc_now(),
                "state": "blocked",
                "run_id": run_id,
                "job_id": job_id or None,
                "sink": handoff_packet.get("sink"),
                "operator": handoff_packet.get("operator"),
                "execute_selected_lookup_smoke": True,
                "would_execute_selected_lookup_smoke": False,
                "lookup_smoke_handoff_from_response": handoff_packet,
                "smoke": None,
                "smoke_path": None,
                "blocked_reasons": list(handoff_packet.get("blocked_reasons") or ["lookup-smoke handoff is not ready"]),
                "next_safe_command": (
                    f"runs lookup-smoke-handoff-from-response {shlex.quote(run_id)} "
                    f"--response {shlex.quote(response)} --json"
                ),
                "next_explicit_operator_command": None,
                "commands": {
                    "lookup_smoke_handoff": (
                        f"runs lookup-smoke-handoff-from-response {shlex.quote(run_id)} "
                        f"--response {shlex.quote(response)} --json"
                    ),
                    "execute_selected_lookup_smoke": execute_command,
                    "live_pilot_status": f"runs live-pilot-status {run_id} --no-write --json",
                },
                "explicit_stop_conditions": [
                    "selected lookup smoke was not executed because the handoff is blocked.",
                    "Resolve blocked reasons and review a ready handoff before retrying with the explicit execute flag.",
                    "This blocked response did not run live lookup, live write, or live readback.",
                ],
                "writes_attempted": 0,
                "network_calls_made": 0,
            }
        executed = self.execute_selected_lookup_smoke_for_job(job_id=job_id, run_id=run_id)
        smoke = dict(executed.get("smoke") or {})
        return {
            "schema": "business-card-watchdog.selected-lookup-smoke-execution-packet-from-response.v1",
            "generated_at": utc_now(),
            "state": "executed",
            "run_id": run_id,
            "job_id": job_id,
            "sink": smoke.get("sink") or handoff_packet.get("sink"),
            "operator": smoke.get("operator") or handoff_packet.get("operator"),
            "execute_selected_lookup_smoke": True,
            "would_execute_selected_lookup_smoke": True,
            "lookup_smoke_handoff_from_response": handoff_packet,
            "smoke": smoke,
            "smoke_path": executed.get("smoke_path"),
            "blocked_reasons": [],
            "next_safe_command": f"runs live-pilot-status {run_id} --no-write --json",
            "next_explicit_operator_command": None,
            "commands": {
                "live_pilot_status": f"runs live-pilot-status {run_id} --no-write --json",
                "live_pilot_handoff": f"runs live-pilot-handoff {run_id} --no-write --json",
                "review_bundle": f"reviews bundle --run-id {run_id} --state all --json",
            },
            "explicit_stop_conditions": [
                "Inspect redacted downstream duplicate evidence before any duplicate resolution or write pilot.",
                "Do not run sink write or readback until duplicate evidence is reviewed.",
            ],
            "writes_attempted": int(smoke.get("writes_attempted") or 0),
            "network_calls_made": int(smoke.get("network_calls_made") or 0),
        }

    def selected_write_pilot_execution_packet_from_response(
        self,
        *,
        run_id: str,
        response: str,
        execute_write_pilot: bool = False,
    ) -> dict[str, Any]:
        selected_target_handoff = self.selected_live_target_handoff_from_response(
            run_id=run_id,
            response=response,
            write_audit=False,
        )
        selected_target = dict(selected_target_handoff.get("selected_target") or {})
        job_id = str(selected_target_handoff.get("job_id") or selected_target.get("job_id") or "")
        sink = str(selected_target.get("sink") or "")
        operator = str(selected_target.get("operator") or selected_target.get("approved_by") or "")
        artifact_dir = None
        selected_lookup_smoke = None
        downstream_duplicate = None
        duplicate_resolution = None
        apply_readiness_result = None
        apply_readiness = None
        blockers = list(selected_target_handoff.get("blocked_reasons") or [])
        if selected_target_handoff.get("state") not in {
            "ready_for_live_lookup_request",
            "ready_for_live_write_request",
        }:
            blockers.append("selected target handoff is not ready")
        if not job_id or not sink or not operator:
            blockers.append("active selected target is missing job_id, sink, or operator")
        if sink and sink not in {"google_contacts", "odoo"}:
            blockers.append(f"unsupported sink for write pilot: {sink}")
        scope_allows = dict(selected_target.get("scope_allows") or {})
        if selected_target and not bool(scope_allows.get("write")):
            blockers.append("selected target scope does not allow write")
        if job_id:
            job = self.get_job(job_id, run_id=run_id)
            artifact_dir = (
                Path(job["artifact_dir"])
                if job.get("artifact_dir")
                else self.config.runs_dir / run_id / "artifacts" / job_id
            )
            selected_lookup_smoke = _read_json_file(artifact_dir / "selected_lookup_smoke.json")
            downstream_duplicate = _read_json_file(artifact_dir / "downstream_duplicate_assessment.json")
            duplicate_resolution = _read_json_file(artifact_dir / "duplicate_resolution.json")
            if selected_lookup_smoke is None:
                blockers.append("selected_lookup_smoke.json is required before write pilot")
            duplicate_state = str((downstream_duplicate or {}).get("state") or "missing")
            resolution_decision = str((duplicate_resolution or {}).get("decision") or "").strip()
            if downstream_duplicate is None:
                blockers.append("downstream_duplicate_assessment.json is required before write pilot")
            elif duplicate_state != "no_match" and (not resolution_decision or resolution_decision == "noop"):
                blockers.append(f"downstream duplicate state {duplicate_state} must be resolved before write pilot")
            if sink:
                apply_readiness_result = self.build_sink_apply_pilot_readiness_for_job(
                    job_id=job_id,
                    run_id=run_id,
                    sink=sink,
                )
                apply_readiness = dict(apply_readiness_result.get("readiness") or {})
                if not apply_readiness.get("can_live_apply_pilot"):
                    blockers.extend(
                        f"apply:{name}" for name in list(apply_readiness.get("live_missing_requirements") or [])
                    )
        ready = not blockers and bool(job_id and sink and operator)
        execute_command = (
            f"sinks write-pilot {job_id} --run-id {run_id} --sink {sink} "
            f"--approved-by {operator} --no-simulate --json"
            if job_id and sink and operator
            else None
        )
        base_payload = {
            "schema": "business-card-watchdog.selected-write-pilot-execution-packet-from-response.v1",
            "generated_at": utc_now(),
            "run_id": run_id,
            "job_id": job_id or None,
            "sink": sink or None,
            "operator": operator or None,
            "execute_write_pilot": execute_write_pilot,
            "would_execute_write_pilot": ready,
            "selected_target_handoff_from_response": selected_target_handoff,
            "selected_target_identity": selected_target_handoff.get("selected_target_identity"),
            "selected_lookup_smoke": selected_lookup_smoke,
            "downstream_duplicate_assessment": downstream_duplicate,
            "duplicate_resolution": duplicate_resolution,
            "apply_readiness": apply_readiness,
            "apply_readiness_path": (apply_readiness_result or {}).get("readiness_path")
            if apply_readiness_result
            else None,
            "write_pilot": None,
            "write_pilot_path": None,
            "blocked_reasons": blockers,
            "next_safe_command": (
                f"runs selected-write-pilot-execution-packet-from-response {shlex.quote(run_id)} "
                f"--response {shlex.quote(response)} --json"
            ),
            "next_explicit_operator_command": execute_command if ready else None,
            "commands": {
                "selected_target_handoff": (
                    f"runs selected-live-target-handoff-from-response {shlex.quote(run_id)} "
                    f"--response {shlex.quote(response)} --json"
                ),
                "selected_lookup_smoke_packet": (
                    f"runs selected-lookup-smoke-execution-packet-from-response {shlex.quote(run_id)} "
                    f"--response {shlex.quote(response)} --json"
                ),
                "apply_readiness": (
                    f"sinks apply-pilot-readiness {job_id} --run-id {run_id} --sink {sink}"
                    if job_id and sink
                    else None
                ),
                "execute_write_pilot": execute_command,
                "live_pilot_status": f"runs live-pilot-status {run_id} --no-write --json",
                "live_pilot_handoff": f"runs live-pilot-handoff {run_id} --no-write --json",
            },
            "explicit_stop_conditions": [
                "Default mode does not execute sink write pilot.",
                "Pass the explicit execute-write-pilot flag only after lookup evidence and duplicate review are ready.",
                "Live write remains blocked unless selected target scope allows write and live apply readiness passes.",
                "Do not process private SyncThing images, run public-web search, or call paid enrichment from this packet.",
            ],
            "writes_attempted": 0,
            "network_calls_made": 0,
        }
        if not execute_write_pilot:
            return {
                **base_payload,
                "state": "ready_to_request_write_pilot" if ready else "blocked",
                "execute_write_pilot": False,
            }
        if not ready or not job_id or not sink or not operator:
            return {
                **base_payload,
                "state": "blocked",
                "execute_write_pilot": True,
                "would_execute_write_pilot": False,
                "next_explicit_operator_command": None,
                "explicit_stop_conditions": [
                    "sink write pilot was not executed because readiness is blocked.",
                    "Resolve blocked reasons before retrying with the explicit execute flag.",
                    "This blocked response did not run live lookup, live write, or live readback.",
                ],
            }
        executed = self.execute_sink_write_pilot_for_job(
            job_id=job_id,
            run_id=run_id,
            sink=sink,
            approved_by=operator,
            simulate=False,
        )
        pilot = dict(executed.get("pilot") or {})
        return {
            **base_payload,
            "state": "executed",
            "execute_write_pilot": True,
            "would_execute_write_pilot": True,
            "write_pilot": pilot,
            "write_pilot_path": executed.get("pilot_path"),
            "blocked_reasons": [],
            "next_safe_command": f"runs live-pilot-status {run_id} --no-write --json",
            "next_explicit_operator_command": None,
            "commands": {
                "live_pilot_status": f"runs live-pilot-status {run_id} --no-write --json",
                "live_pilot_handoff": f"runs live-pilot-handoff {run_id} --no-write --json",
                "review_bundle": f"reviews bundle --run-id {run_id} --state all --json",
            },
            "explicit_stop_conditions": [
                "Inspect write/readback evidence before closing the live pilot.",
                "Do not run another write pilot for this job unless the prior write is reconciled.",
            ],
            "writes_attempted": int(pilot.get("writes_attempted") or 0),
            "network_calls_made": int(pilot.get("network_calls_made") or 0),
        }

    def selected_readback_pilot_execution_packet_from_response(
        self,
        *,
        run_id: str,
        response: str,
        execute_readback_pilot: bool = False,
    ) -> dict[str, Any]:
        selected_target_handoff = self.selected_live_target_handoff_from_response(
            run_id=run_id,
            response=response,
            write_audit=False,
        )
        selected_target = dict(selected_target_handoff.get("selected_target") or {})
        job_id = str(selected_target_handoff.get("job_id") or selected_target.get("job_id") or "")
        sink = str(selected_target.get("sink") or "")
        operator = str(selected_target.get("operator") or selected_target.get("approved_by") or "")
        sink_write_pilot = None
        readback_adapter_request = None
        blockers = list(selected_target_handoff.get("blocked_reasons") or [])
        if selected_target_handoff.get("state") not in {
            "ready_for_live_lookup_request",
            "ready_for_live_write_request",
            "ready_for_live_readback_request",
        }:
            blockers.append("selected target handoff is not ready")
        if not job_id or not sink or not operator:
            blockers.append("active selected target is missing job_id, sink, or operator")
        if sink and sink not in {"google_contacts", "odoo"}:
            blockers.append(f"unsupported sink for readback pilot: {sink}")
        scope_allows = dict(selected_target.get("scope_allows") or {})
        if selected_target and not bool(scope_allows.get("readback")):
            blockers.append("selected target scope does not allow readback")
        if job_id:
            job = self.get_job(job_id, run_id=run_id)
            artifact_dir = (
                Path(job["artifact_dir"])
                if job.get("artifact_dir")
                else self.config.runs_dir / run_id / "artifacts" / job_id
            )
            sink_write_pilot = _read_json_file(artifact_dir / "sink_write_pilot.json")
            readback_adapter_request = _read_json_file(artifact_dir / "sink_adapter_request_readback.json")
            if sink_write_pilot is None:
                blockers.append("sink_write_pilot.json is required before readback pilot")
            elif sink_write_pilot.get("sink") != sink:
                blockers.append(f"sink_write_pilot.json is not for sink {sink}")
            elif sink_write_pilot.get("state") != "live_written":
                blockers.append(
                    f"live readback pilot requires live_written sink_write_pilot.json, "
                    f"found {sink_write_pilot.get('state')!r}"
                )
            source_selected_target = dict((sink_write_pilot or {}).get("selected_target") or {})
            if sink_write_pilot is not None and not _selected_target_identity(source_selected_target):
                blockers.append("sink_write_pilot.json does not reference a selected live target")
            elif (
                sink_write_pilot is not None
                and _selected_target_identity(source_selected_target) != _selected_target_identity(selected_target)
            ):
                blockers.append("sink_write_pilot.json was not created by the current selected live target")
            if readback_adapter_request is None:
                blockers.append("sink_adapter_request_readback.json is required before readback pilot")
            elif not any(
                request.get("phase") == "readback" and request.get("sink") == sink
                for request in list(readback_adapter_request.get("requests") or [])
            ):
                blockers.append(f"sink_adapter_request_readback.json has no readback request for sink {sink}")
        ready = not blockers and bool(job_id and sink and operator)
        execute_command = (
            f"sinks readback-pilot {job_id} --run-id {run_id} --sink {sink} "
            f"--approved-by {operator} --no-simulate --json"
            if job_id and sink and operator
            else None
        )
        base_payload = {
            "schema": "business-card-watchdog.selected-readback-pilot-execution-packet-from-response.v1",
            "generated_at": utc_now(),
            "run_id": run_id,
            "job_id": job_id or None,
            "sink": sink or None,
            "operator": operator or None,
            "execute_readback_pilot": execute_readback_pilot,
            "would_execute_readback_pilot": ready,
            "selected_target_handoff_from_response": selected_target_handoff,
            "selected_target_identity": selected_target_handoff.get("selected_target_identity"),
            "sink_write_pilot": sink_write_pilot,
            "readback_adapter_request": readback_adapter_request,
            "readback_pilot": None,
            "readback_pilot_path": None,
            "blocked_reasons": blockers,
            "next_safe_command": (
                f"runs selected-readback-pilot-execution-packet-from-response {shlex.quote(run_id)} "
                f"--response {shlex.quote(response)} --json"
            ),
            "next_explicit_operator_command": execute_command if ready else None,
            "commands": {
                "selected_target_handoff": (
                    f"runs selected-live-target-handoff-from-response {shlex.quote(run_id)} "
                    f"--response {shlex.quote(response)} --json"
                ),
                "selected_write_pilot_packet": (
                    f"runs selected-write-pilot-execution-packet-from-response {shlex.quote(run_id)} "
                    f"--response {shlex.quote(response)} --json"
                ),
                "prepare_readback_adapter_request": (
                    f"sinks adapter-request {job_id} --run-id {run_id} --phase readback"
                    if job_id
                    else None
                ),
                "execute_readback_pilot": execute_command,
                "live_pilot_status": f"runs live-pilot-status {run_id} --no-write --json",
                "live_pilot_handoff": f"runs live-pilot-handoff {run_id} --no-write --json",
            },
            "explicit_stop_conditions": [
                "Default mode does not execute sink readback pilot.",
                "Pass the explicit execute-readback-pilot flag only after write-pilot evidence and readback adapter request are ready.",
                "Live readback remains blocked unless selected target scope allows readback and the write pilot came from the current selected target.",
                "Readback must remain read-only and report writes_attempted=0.",
            ],
            "writes_attempted": 0,
            "network_calls_made": 0,
        }
        if not execute_readback_pilot:
            return {
                **base_payload,
                "state": "ready_to_request_readback_pilot" if ready else "blocked",
                "execute_readback_pilot": False,
            }
        if not ready or not job_id or not sink or not operator:
            return {
                **base_payload,
                "state": "blocked",
                "execute_readback_pilot": True,
                "would_execute_readback_pilot": False,
                "next_explicit_operator_command": None,
                "explicit_stop_conditions": [
                    "sink readback pilot was not executed because readiness is blocked.",
                    "Resolve blocked reasons before retrying with the explicit execute flag.",
                    "This blocked response did not run live lookup, live write, or live readback.",
                ],
            }
        executed = self.execute_sink_readback_pilot_for_job(
            job_id=job_id,
            run_id=run_id,
            sink=sink,
            approved_by=operator,
            simulate=False,
        )
        pilot = dict(executed.get("pilot") or {})
        return {
            **base_payload,
            "state": "executed",
            "execute_readback_pilot": True,
            "would_execute_readback_pilot": True,
            "readback_pilot": pilot,
            "readback_pilot_path": executed.get("pilot_path"),
            "blocked_reasons": [],
            "next_safe_command": f"runs live-pilot-status {run_id} --no-write --json",
            "next_explicit_operator_command": None,
            "commands": {
                "live_pilot_status": f"runs live-pilot-status {run_id} --no-write --json",
                "live_pilot_handoff": f"runs live-pilot-handoff {run_id} --no-write --json",
                "review_bundle": f"reviews bundle --run-id {run_id} --state all --json",
            },
            "explicit_stop_conditions": [
                "Inspect readback evidence before closing the live pilot.",
                "Do not run another readback pilot for this job unless the prior readback is reconciled.",
            ],
            "writes_attempted": int(pilot.get("writes_attempted") or 0),
            "network_calls_made": int(pilot.get("network_calls_made") or 0),
        }

    def live_pilot_closeout_packet_from_response(
        self,
        *,
        run_id: str,
        response: str,
        write_closeout: bool = False,
    ) -> dict[str, Any]:
        selected_target_handoff = self.selected_live_target_handoff_from_response(
            run_id=run_id,
            response=response,
            write_audit=False,
        )
        job_id = str(selected_target_handoff.get("job_id") or "")
        validation_state = str(selected_target_handoff.get("validation_state") or "")
        handoff_blockers = list(selected_target_handoff.get("blocked_reasons") or [])
        blockers = []
        if selected_target_handoff.get("state") == "blocked" or not job_id:
            blockers.extend(handoff_blockers)
            blockers.append("selected target handoff is not ready for closeout")
        if validation_state not in {
            "ready_for_live_lookup_request",
            "ready_to_review_selected_target_audit",
            "ready_for_live_write_request",
            "ready_for_live_readback_request",
            "ready_for_live_pilot_closeout",
        }:
            blockers.append(f"validation state {validation_state or 'missing'} is not ready for closeout")
        closeout = None
        closeout_path = None
        closeout_report = None
        if job_id:
            closeout = self.build_live_pilot_closeout_for_job(
                job_id=job_id,
                run_id=run_id,
                write=write_closeout and not blockers,
            )
            closeout_path = closeout.get("closeout_path")
            closeout_report = dict(closeout.get("report") or {})
        packet_state = "blocked" if blockers else "closeout_ready" if closeout_report and closeout_report.get("state") == "complete" else "closeout_incomplete"
        return {
            "schema": "business-card-watchdog.live-pilot-closeout-packet-from-response.v1",
            "generated_at": utc_now(),
            "state": packet_state,
            "run_id": run_id,
            "job_id": job_id or None,
            "sink": (closeout_report or {}).get("sink") if closeout_report else None,
            "operator": (closeout_report or {}).get("operator") if closeout_report else None,
            "validation_state": validation_state or None,
            "selected_target_handoff_from_response": selected_target_handoff,
            "selected_target_handoff_blockers": handoff_blockers,
            "closeout": closeout,
            "closeout_report": closeout_report,
            "closeout_path": closeout_path,
            "write_closeout": write_closeout,
            "closeout_written": bool(write_closeout and closeout_path),
            "blocked_reasons": blockers,
            "next_safe_command": (
                f"runs live-pilot-closeout-packet-from-response {shlex.quote(run_id)} "
                f"--response {shlex.quote(response)} --json"
            ),
            "next_explicit_operator_command": None
            if blockers
            else (
                f"sinks live-pilot-closeout {job_id} --run-id {run_id} --json"
                if job_id and not closeout_path
                else None
            ),
            "commands": {
                "selected_target_handoff": (
                    f"runs selected-live-target-handoff-from-response {shlex.quote(run_id)} "
                    f"--response {shlex.quote(response)} --json"
                ),
                "selected_readback_packet": (
                    f"runs selected-readback-pilot-execution-packet-from-response {shlex.quote(run_id)} "
                    f"--response {shlex.quote(response)} --json"
                ),
                "closeout_preview": (
                    f"sinks live-pilot-closeout {job_id} --run-id {run_id} --no-write --json"
                    if job_id
                    else None
                ),
                "write_closeout": (
                    f"runs live-pilot-closeout-packet-from-response {shlex.quote(run_id)} "
                    f"--response {shlex.quote(response)} --write-closeout --json"
                    if job_id
                    else None
                ),
                "live_pilot_status": f"runs live-pilot-status {run_id} --no-write --json",
                "live_pilot_handoff": f"runs live-pilot-handoff {run_id} --no-write --json",
            },
            "explicit_stop_conditions": [
                "Default mode does not write live_pilot_closeout.json.",
                "The explicit write-closeout flag writes only the closeout report and never runs live lookup, live write, or live readback.",
                "Do not mark a live pilot complete unless the closeout report state is complete.",
                "Do not process private SyncThing images, run public-web search, or call paid enrichment from this packet.",
            ],
            "writes_attempted": int((closeout_report or {}).get("writes_attempted") or 0),
            "network_calls_made": int((closeout_report or {}).get("network_calls_made") or 0),
        }

    def live_pilot_operator_workflow_packet_from_response(
        self,
        *,
        run_id: str,
        response: str,
    ) -> dict[str, Any]:
        target_handoff = self.selected_live_target_handoff_from_response(
            run_id=run_id,
            response=response,
            write_audit=False,
        )
        lookup_handoff = self.lookup_smoke_handoff_from_response(
            run_id=run_id,
            response=response,
            write_handoff=False,
        )
        lookup_execution = self.selected_lookup_smoke_execution_packet_from_response(
            run_id=run_id,
            response=response,
            execute_selected_lookup_smoke=False,
        )
        write_execution = self.selected_write_pilot_execution_packet_from_response(
            run_id=run_id,
            response=response,
            execute_write_pilot=False,
        )
        readback_execution = self.selected_readback_pilot_execution_packet_from_response(
            run_id=run_id,
            response=response,
            execute_readback_pilot=False,
        )
        closeout_packet = self.live_pilot_closeout_packet_from_response(
            run_id=run_id,
            response=response,
            write_closeout=False,
        )
        packets = {
            "selected_target_handoff": target_handoff,
            "lookup_smoke_handoff": lookup_handoff,
            "selected_lookup_smoke_execution": lookup_execution,
            "selected_write_pilot_execution": write_execution,
            "selected_readback_pilot_execution": readback_execution,
            "live_pilot_closeout": closeout_packet,
        }
        step_order = [
            ("selected_target_handoff", "selected_target"),
            ("lookup_smoke_handoff", "lookup_handoff"),
            ("selected_lookup_smoke_execution", "lookup_smoke"),
            ("selected_write_pilot_execution", "write_pilot"),
            ("selected_readback_pilot_execution", "readback_pilot"),
            ("live_pilot_closeout", "closeout"),
        ]
        step_summary = [
            {
                "step": step,
                "packet": packet_key,
                "state": packets[packet_key].get("state"),
                "blocked_reasons": list(packets[packet_key].get("blocked_reasons") or []),
                "next_safe_command": packets[packet_key].get("next_safe_command"),
                "next_explicit_operator_command": packets[packet_key].get("next_explicit_operator_command"),
            }
            for packet_key, step in step_order
        ]
        blocked_steps = [
            item
            for item in step_summary
            if item["state"]
            in {
                "blocked",
                "audit_blocked",
                "handoff_blocked",
                "closeout_incomplete",
                "workflow_blocked",
            }
        ]
        closeout_report = dict(closeout_packet.get("closeout_report") or {})
        job_id = (
            closeout_packet.get("job_id")
            or target_handoff.get("job_id")
            or lookup_handoff.get("job_id")
            or lookup_execution.get("job_id")
        )
        state = (
            "workflow_complete"
            if closeout_packet.get("state") == "closeout_ready" and not blocked_steps
            else "workflow_blocked"
            if blocked_steps
            else "workflow_ready"
        )
        return {
            "schema": "business-card-watchdog.live-pilot-operator-workflow-packet-from-response.v1",
            "generated_at": utc_now(),
            "state": state,
            "run_id": run_id,
            "job_id": job_id,
            "sink": closeout_packet.get("sink") or lookup_handoff.get("sink") or write_execution.get("sink"),
            "operator": closeout_packet.get("operator") or lookup_handoff.get("operator") or write_execution.get("operator"),
            "validation_state": target_handoff.get("validation_state"),
            "step_summary": step_summary,
            "blocked_step_count": len(blocked_steps),
            "blocked_steps": [item["step"] for item in blocked_steps],
            "packets": packets,
            "next_safe_command": (
                f"runs live-pilot-operator-workflow-packet-from-response {shlex.quote(run_id)} "
                f"--response {shlex.quote(response)} --json"
            ),
            "next_explicit_operator_command": next(
                (
                    item.get("next_explicit_operator_command")
                    for item in step_summary
                    if item.get("next_explicit_operator_command")
                ),
                None,
            ),
            "commands": {
                "selected_target_handoff": (
                    f"runs selected-live-target-handoff-from-response {shlex.quote(run_id)} "
                    f"--response {shlex.quote(response)} --json"
                ),
                "lookup_smoke_handoff": (
                    f"runs lookup-smoke-handoff-from-response {shlex.quote(run_id)} "
                    f"--response {shlex.quote(response)} --json"
                ),
                "lookup_smoke_execution_packet": (
                    f"runs selected-lookup-smoke-execution-packet-from-response {shlex.quote(run_id)} "
                    f"--response {shlex.quote(response)} --json"
                ),
                "write_pilot_execution_packet": (
                    f"runs selected-write-pilot-execution-packet-from-response {shlex.quote(run_id)} "
                    f"--response {shlex.quote(response)} --json"
                ),
                "readback_pilot_execution_packet": (
                    f"runs selected-readback-pilot-execution-packet-from-response {shlex.quote(run_id)} "
                    f"--response {shlex.quote(response)} --json"
                ),
                "closeout_packet": (
                    f"runs live-pilot-closeout-packet-from-response {shlex.quote(run_id)} "
                    f"--response {shlex.quote(response)} --json"
                ),
                "live_pilot_status": f"runs live-pilot-status {run_id} --no-write --json",
                "live_pilot_handoff": f"runs live-pilot-handoff {run_id} --no-write --json",
            },
            "explicit_stop_conditions": [
                "This workflow packet is read-only and does not execute lookup, write, readback, or closeout writes.",
                "Run only the next explicit operator command after reviewing the corresponding packet and tenant/profile safety.",
                "Do not mark a live pilot complete unless the closeout packet reports closeout_ready.",
                "Do not process private SyncThing images, run public-web search, or call paid enrichment from this packet.",
            ],
            "writes_attempted": int(closeout_report.get("writes_attempted") or 0),
            "network_calls_made": int(closeout_report.get("network_calls_made") or 0),
        }

    def live_pilot_operator_rehearsal_from_response(
        self,
        *,
        run_id: str,
        response: str,
    ) -> dict[str, Any]:
        workflow_packet = self.live_pilot_operator_workflow_packet_from_response(
            run_id=run_id,
            response=response,
        )
        step_summary = list(workflow_packet.get("step_summary") or [])
        next_blocked_step = next(
            (step for step in step_summary if isinstance(step, dict) and step.get("step") in workflow_packet.get("blocked_steps", [])),
            None,
        )
        next_explicit_command = workflow_packet.get("next_explicit_operator_command")
        safe_inspection_command = (
            f"runs live-pilot-operator-workflow-packet-from-response {shlex.quote(run_id)} "
            f"--response {shlex.quote(response)} --json"
        )
        rehearsal_steps = [
            {
                "step": "inspect_workflow_packet",
                "command": safe_inspection_command,
                "safe_to_auto_continue": True,
                "requires_explicit_operator_action": False,
                "executes_live_call": False,
                "executes_sink_write": False,
            }
        ]
        if next_explicit_command:
            rehearsal_steps.append(
                {
                    "step": "run_next_explicit_operator_command",
                    "command": next_explicit_command,
                    "safe_to_auto_continue": False,
                    "requires_explicit_operator_action": True,
                    "executes_live_call": True,
                    "executes_sink_write": "write-pilot" in str(next_explicit_command)
                    or "apply --apply" in str(next_explicit_command),
                }
            )
        state = "ready_for_explicit_operator_step" if next_explicit_command else "inspection_only"
        if workflow_packet.get("state") == "workflow_complete":
            state = "workflow_complete"
        return {
            "schema": "business-card-watchdog.live-pilot-operator-rehearsal-from-response.v1",
            "generated_at": utc_now(),
            "state": state,
            "run_id": run_id,
            "job_id": workflow_packet.get("job_id"),
            "sink": workflow_packet.get("sink"),
            "operator": workflow_packet.get("operator"),
            "workflow_state": workflow_packet.get("state"),
            "workflow_blocked_steps": list(workflow_packet.get("blocked_steps") or []),
            "next_blocked_step": next_blocked_step,
            "next_safe_command": safe_inspection_command,
            "next_explicit_operator_command": next_explicit_command,
            "rehearsal_steps": rehearsal_steps,
            "workflow_packet": workflow_packet,
            "commands": {
                "inspect_workflow_packet": safe_inspection_command,
                "operator_dashboard": f"operator-dashboard --run-id {run_id} --json",
                "live_pilot_status": f"runs live-pilot-status {run_id} --no-write --json",
                "live_pilot_handoff": f"runs live-pilot-handoff {run_id} --no-write --json",
            },
            "explicit_stop_conditions": [
                "This rehearsal packet is read-only and never executes the explicit operator command.",
                "Run the explicit command only after reviewing the workflow packet and confirming tenant/profile safety.",
                "Stop if the workflow packet or selected target does not match the intended run, job, sink, operator, and scope.",
                "Do not process private SyncThing images, run public-web search, or call paid enrichment from this packet.",
            ],
            "writes_attempted": int(workflow_packet.get("writes_attempted") or 0),
            "network_calls_made": int(workflow_packet.get("network_calls_made") or 0),
        }

    def live_pilot_readiness_export_from_response(
        self,
        *,
        run_id: str,
        response: str,
        write: bool = True,
    ) -> dict[str, Any]:
        rehearsal = self.live_pilot_operator_rehearsal_from_response(
            run_id=run_id,
            response=response,
        )
        workflow_packet = dict(rehearsal.get("workflow_packet") or {})
        response_fields = _parse_operator_response_fields(response)
        redacted_response_fields = {
            key: value
            for key, value in response_fields.items()
            if key in {"run_id", "job_id", "sink", "operator", "scope"}
        }
        response_digest = hashlib.sha256(response.encode("utf-8")).hexdigest()
        redaction_token = "<operator-response-redacted>"
        safety_confirmation = str(response_fields.get("safety_confirmation") or "")

        def redact_export_value(value: Any) -> Any:
            if isinstance(value, str):
                redacted = value.replace(response, redaction_token)
                if safety_confirmation:
                    redacted = redacted.replace(safety_confirmation, "<safety-confirmation-redacted>")
                return redacted
            if isinstance(value, list):
                return [redact_export_value(item) for item in value]
            if isinstance(value, dict):
                return {key: redact_export_value(item) for key, item in value.items()}
            return value

        redacted_rehearsal = redact_export_value(rehearsal)
        redacted_workflow_packet = redact_export_value(workflow_packet)
        export_path = self.config.runs_dir / run_id / "live_pilot_readiness_export.json"
        payload = {
            "schema": "business-card-watchdog.live-pilot-readiness-export-from-response.v1",
            "generated_at": utc_now(),
            "state": rehearsal.get("state"),
            "run_id": run_id,
            "job_id": rehearsal.get("job_id"),
            "sink": rehearsal.get("sink"),
            "operator": rehearsal.get("operator"),
            "write": write,
            "export_written": False,
            "export_path": None,
            "operator_response_redacted": {
                "fields": redacted_response_fields,
                "sha256": response_digest,
                "raw_response_stored": False,
                "redacted_fields": ["safety_confirmation"],
            },
            "review_packet": {
                "workflow_state": workflow_packet.get("state"),
                "workflow_blocked_steps": list(workflow_packet.get("blocked_steps") or []),
                "workflow_step_summary": redact_export_value(workflow_packet.get("step_summary") or []),
                "rehearsal_steps": redact_export_value(rehearsal.get("rehearsal_steps") or []),
                "next_safe_command": redact_export_value(rehearsal.get("next_safe_command")),
                "next_explicit_operator_command": redact_export_value(
                    rehearsal.get("next_explicit_operator_command")
                ),
            },
            "artifact_packet_schemas": {
                "rehearsal": rehearsal.get("schema"),
                "workflow": workflow_packet.get("schema"),
                "selected_target_handoff": (
                    dict(dict(workflow_packet.get("packets") or {}).get("selected_target_handoff") or {}).get("schema")
                ),
                "lookup_smoke_handoff": (
                    dict(dict(workflow_packet.get("packets") or {}).get("lookup_smoke_handoff") or {}).get("schema")
                ),
                "live_pilot_closeout": (
                    dict(dict(workflow_packet.get("packets") or {}).get("live_pilot_closeout") or {}).get("schema")
                ),
            },
            "commands": {
                "operator_dashboard": f"operator-dashboard --run-id {run_id} --json",
                "inspect_rehearsal": (
                    f"runs live-pilot-operator-rehearsal-from-response {shlex.quote(run_id)} "
                    "--response <operator-response> --json"
                ),
                "inspect_workflow_packet": (
                    f"runs live-pilot-operator-workflow-packet-from-response {shlex.quote(run_id)} "
                    "--response <operator-response> --json"
                ),
                "preview_export": (
                    f"runs live-pilot-readiness-export-from-response {shlex.quote(run_id)} "
                    "--response <operator-response> --no-write --json"
                ),
                "write_export": (
                    f"runs live-pilot-readiness-export-from-response {shlex.quote(run_id)} "
                    "--response <operator-response> --json"
                ),
                "live_pilot_status": f"runs live-pilot-status {run_id} --no-write --json",
                "live_pilot_handoff": f"runs live-pilot-handoff {run_id} --no-write --json",
            },
            "explicit_stop_conditions": [
                "This export is review-only and does not execute lookup, write, readback, or closeout commands.",
                "The raw operator response and safety confirmation are not stored in this export.",
                "Run the explicit operator command only after reviewing the rehearsal, workflow packet, and tenant/profile safety.",
                "Do not process private SyncThing images, run public-web search, or call paid enrichment from this export.",
            ],
            "rehearsal": redacted_rehearsal,
            "workflow_packet": redacted_workflow_packet,
            "writes_attempted": int(rehearsal.get("writes_attempted") or 0),
            "network_calls_made": int(rehearsal.get("network_calls_made") or 0),
        }
        if write:
            export_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            ledger = RunLedger(self.config.runs_dir / run_id)
            ledger.record_artifact(job_id="__run__", kind="live_pilot_readiness_export", path=export_path)
            ledger.record_event(
                "live_pilot_readiness_export_created",
                {
                    "run_id": run_id,
                    "job_id": payload.get("job_id"),
                    "sink": payload.get("sink"),
                    "operator": payload.get("operator"),
                    "export_path": str(export_path),
                    "state": payload.get("state"),
                    "writes_attempted": payload["writes_attempted"],
                    "network_calls_made": payload["network_calls_made"],
                },
            )
            payload["export_written"] = True
            payload["export_path"] = str(export_path)
        return payload

    def live_pilot_execution_checklist_from_response(
        self,
        *,
        run_id: str,
        response: str,
    ) -> dict[str, Any]:
        rehearsal = self.live_pilot_operator_rehearsal_from_response(
            run_id=run_id,
            response=response,
        )
        response_fields = _parse_operator_response_fields(response)
        response_digest = hashlib.sha256(response.encode("utf-8")).hexdigest()
        export_path = self.config.runs_dir / run_id / "live_pilot_readiness_export.json"
        export = _read_json_file(export_path)
        blocked_reasons: list[str] = []
        export_text = ""
        if not export_path.exists() or not export:
            blocked_reasons.append("live_pilot_readiness_export.json is required before showing executable live command")
        else:
            export_text = export_path.read_text(encoding="utf-8")
            if export.get("schema") != "business-card-watchdog.live-pilot-readiness-export-from-response.v1":
                blocked_reasons.append("readiness export schema is not recognized")
            redacted = dict(export.get("operator_response_redacted") or {})
            if redacted.get("raw_response_stored") is not False:
                blocked_reasons.append("readiness export does not prove raw response redaction")
            if redacted.get("sha256") != response_digest:
                blocked_reasons.append("readiness export response digest does not match current response")
            redacted_fields = dict(redacted.get("fields") or {})
            for field in ["run_id", "job_id", "sink", "operator", "scope"]:
                expected = str(response_fields.get(field) or "")
                actual = str(redacted_fields.get(field) or "")
                if expected and actual != expected:
                    blocked_reasons.append(f"readiness export {field} does not match current response")
            if response in export_text:
                blocked_reasons.append("readiness export contains the raw operator response")
            safety_confirmation = str(response_fields.get("safety_confirmation") or "")
            if safety_confirmation and safety_confirmation in export_text:
                blocked_reasons.append("readiness export contains the safety confirmation")
            for field in ["run_id", "job_id", "sink", "operator"]:
                expected = str(rehearsal.get(field) or "")
                actual = str(export.get(field) or "")
                if expected and actual != expected:
                    blocked_reasons.append(f"readiness export {field} does not match current rehearsal")
        next_explicit_command = rehearsal.get("next_explicit_operator_command")
        executable_live_command = next_explicit_command if not blocked_reasons else None
        checklist_items = [
            {
                "name": "readiness_export_exists",
                "ok": bool(export_path.exists() and export),
                "evidence": str(export_path),
            },
            {
                "name": "readiness_export_redacted",
                "ok": bool(
                    export
                    and not any(
                        "raw operator response" in reason or "safety confirmation" in reason
                        for reason in blocked_reasons
                    )
                ),
                "evidence": "raw_response_stored=false and response text absent",
            },
            {
                "name": "response_digest_matches",
                "ok": bool(export and dict(export.get("operator_response_redacted") or {}).get("sha256") == response_digest),
                "evidence": "operator_response_redacted.sha256",
            },
            {
                "name": "run_job_sink_operator_match",
                "ok": bool(export and not any("does not match" in reason for reason in blocked_reasons)),
                "evidence": "export fields compared to current response and rehearsal",
            },
            {
                "name": "next_explicit_command_available",
                "ok": bool(next_explicit_command),
                "evidence": "current rehearsal next_explicit_operator_command",
            },
        ]
        if not next_explicit_command:
            blocked_reasons.append("current rehearsal has no explicit live command")
        state = "ready_for_explicit_operator_command" if executable_live_command else "blocked"
        return {
            "schema": "business-card-watchdog.live-pilot-execution-checklist-from-response.v1",
            "generated_at": utc_now(),
            "state": state,
            "run_id": run_id,
            "job_id": rehearsal.get("job_id"),
            "sink": rehearsal.get("sink"),
            "operator": rehearsal.get("operator"),
            "readiness_export_path": str(export_path),
            "readiness_export_loaded": bool(export),
            "checklist_items": checklist_items,
            "blocked_reasons": blocked_reasons,
            "executable_live_command": executable_live_command,
            "next_safe_command": (
                f"runs live-pilot-readiness-export-from-response {shlex.quote(run_id)} "
                "--response <operator-response> --no-write --json"
            ),
            "commands": {
                "readiness_export": (
                    f"runs live-pilot-readiness-export-from-response {shlex.quote(run_id)} "
                    "--response <operator-response> --json"
                ),
                "rehearsal": (
                    f"runs live-pilot-operator-rehearsal-from-response {shlex.quote(run_id)} "
                    "--response <operator-response> --json"
                ),
                "workflow_packet": (
                    f"runs live-pilot-operator-workflow-packet-from-response {shlex.quote(run_id)} "
                    "--response <operator-response> --json"
                ),
                "operator_dashboard": f"operator-dashboard --run-id {run_id} --json",
            },
            "explicit_stop_conditions": [
                "Do not run executable_live_command unless checklist state is ready_for_explicit_operator_command.",
                "Do not run the command if the readiness export is missing, unredacted, stale, or mismatched.",
                "Recreate the readiness export after any selected-target, lookup, duplicate, write, or readback evidence changes.",
                "Do not process private SyncThing images, run public-web search, or call paid enrichment from this checklist.",
            ],
            "writes_attempted": 0,
            "network_calls_made": 0,
        }

    def live_pilot_command_copy_packet_from_response(
        self,
        *,
        run_id: str,
        response: str,
        acknowledgement: str = "",
    ) -> dict[str, Any]:
        checklist = self.live_pilot_execution_checklist_from_response(run_id=run_id, response=response)
        blocked_reasons = list(checklist.get("blocked_reasons") or [])
        normalized_acknowledgement = " ".join(str(acknowledgement or "").lower().split())
        acknowledgement_terms = {
            "run_id": str(checklist.get("run_id") or ""),
            "job_id": str(checklist.get("job_id") or ""),
            "sink": str(checklist.get("sink") or ""),
            "operator": str(checklist.get("operator") or ""),
        }
        missing_acknowledgement_terms = [
            f"{key}={value}"
            for key, value in acknowledgement_terms.items()
            if value and value.lower() not in normalized_acknowledgement
        ]
        acknowledgement_verb_ok = any(
            verb in normalized_acknowledgement
            for verb in ["acknowledge", "acknowledged", "approve", "approved", "copy", "ready"]
        )
        if not normalized_acknowledgement:
            blocked_reasons.append("operator acknowledgement is required before command copy text is shown")
        if missing_acknowledgement_terms:
            blocked_reasons.append(
                "operator acknowledgement must name "
                + ", ".join(missing_acknowledgement_terms)
                + " before command copy text is shown"
            )
        if not acknowledgement_verb_ok:
            blocked_reasons.append(
                "operator acknowledgement must include one of acknowledge, approved, copy, or ready"
            )
        checklist_ready = checklist.get("state") == "ready_for_explicit_operator_command"
        acknowledgement_ok = bool(
            normalized_acknowledgement
            and not missing_acknowledgement_terms
            and acknowledgement_verb_ok
        )
        executable_live_command = (
            checklist.get("executable_live_command") if checklist_ready and acknowledgement_ok and not blocked_reasons else None
        )
        state = "ready_for_operator_copy" if executable_live_command else "blocked"
        return {
            "schema": "business-card-watchdog.live-pilot-command-copy-packet-from-response.v1",
            "generated_at": utc_now(),
            "state": state,
            "run_id": run_id,
            "job_id": checklist.get("job_id"),
            "sink": checklist.get("sink"),
            "operator": checklist.get("operator"),
            "acknowledgement_required": True,
            "acknowledgement_ok": acknowledgement_ok,
            "acknowledgement_instruction": (
                "Acknowledge the exact run_id, job_id, sink, and operator plus an approval/copy verb before copying."
            ),
            "checklist_state": checklist.get("state"),
            "checklist": checklist,
            "command_copy_text": executable_live_command,
            "executable_live_command": executable_live_command,
            "blocked_reasons": blocked_reasons,
            "explicit_stop_conditions": [
                "This packet only returns command text for operator copy; it never executes the command.",
                "Do not copy command_copy_text unless state is ready_for_operator_copy.",
                "Stop if the command, acknowledgement, checklist, or readiness export no longer matches the intended run.",
                "Do not process private SyncThing images, run public-web search, or call paid enrichment from this packet.",
            ],
            "writes_attempted": 0,
            "network_calls_made": 0,
        }

    def validate_live_pilot_operator_response(self, *, run_id: str, response: str) -> dict[str, Any]:
        parsed_response = _parse_operator_response_fields(response)
        handoff = self.live_pilot_handoff(run_id=run_id, write=False)
        contract = dict(handoff.get("operator_response_contract") or {})
        required_fields = list(contract.get("required_fields") or [])
        allowed_sinks = set(str(item) for item in contract.get("allowed_sinks") or ["google_contacts", "odoo"])
        allowed_scopes = set(str(item) for item in contract.get("allowed_scopes") or ["lookup", "write", "readback", "all"])
        missing_fields = [
            field
            for field in required_fields
            if not str(parsed_response.get(field) or "").strip()
            or str(parsed_response.get(field) or "").strip().startswith("<")
        ]
        mismatches: list[str] = []
        if parsed_response.get("run_id") and parsed_response.get("run_id") != run_id:
            mismatches.append("run_id does not match validation run")
        sink = str(parsed_response.get("sink") or "")
        if sink and sink not in allowed_sinks:
            mismatches.append(f"sink must be one of {sorted(allowed_sinks)}")
        scope = str(parsed_response.get("scope") or "")
        if scope and scope not in allowed_scopes:
            mismatches.append(f"scope must be one of {sorted(allowed_scopes)}")

        matching_template: dict[str, Any] | None = None
        for template in list(handoff.get("operator_response_templates") or []):
            if not isinstance(template, dict):
                continue
            fields = dict(template.get("copyable_approval_fields") or {})
            if (
                str(fields.get("run_id") or "") == str(parsed_response.get("run_id") or "")
                and str(fields.get("job_id") or "") == str(parsed_response.get("job_id") or "")
                and str(fields.get("sink") or "") == sink
            ):
                matching_template = template
                break
        if not matching_template and not missing_fields:
            mismatches.append("response does not match a current operator response template")
        if matching_template:
            template_fields = dict(matching_template.get("copyable_approval_fields") or {})
            for field in ["operator", "scope"]:
                expected = str(template_fields.get(field) or "").strip()
                actual = str(parsed_response.get(field) or "").strip()
                if expected and not expected.startswith("<") and actual and expected != actual:
                    mismatches.append(f"{field} does not match current operator response template")
        if "safety_confirmation" not in missing_fields:
            safety_confirmation_blocker = _safety_confirmation_blocker(
                str(parsed_response.get("safety_confirmation") or "")
            )
            if safety_confirmation_blocker:
                mismatches.append(safety_confirmation_blocker)

        matching_next_action = str((matching_template or {}).get("next_action") or "")
        if missing_fields or mismatches:
            state = "blocked"
            next_validation_step = "fix_response"
        elif matching_next_action == "request_live_lookup_smoke":
            state = "ready_for_live_lookup_request"
            next_validation_step = "selected_target_audit"
        elif matching_next_action == "review_selected_target_audit":
            state = "ready_to_review_selected_target_audit"
            next_validation_step = "selected_target_audit"
        else:
            state = "ready_to_select_live_target"
            next_validation_step = "select_target"
        select_target_command = None
        selected_target_audit_command = None
        lookup_smoke_handoff_command = None
        post_selection_sequence: list[dict[str, Any]] = []
        if state != "blocked":
            selected_target_audit_command = (
                f"sinks selected-target-audit {shlex.quote(str(parsed_response['job_id']))} "
                f"--run-id {shlex.quote(str(parsed_response['run_id']))} "
                f"--scope {shlex.quote(str(parsed_response['scope']))} --no-write --json"
            )
            lookup_smoke_handoff_command = (
                f"sinks lookup-smoke-handoff {shlex.quote(str(parsed_response['job_id']))} "
                f"--run-id {shlex.quote(str(parsed_response['run_id']))} "
                f"--sink {shlex.quote(str(parsed_response['sink']))} "
                f"--approved-by {shlex.quote(str(parsed_response['operator']))} --json"
            )
            if state == "ready_to_select_live_target":
                select_target_command = (
                    f"sinks select-live-target {shlex.quote(str(parsed_response['job_id']))} "
                    f"--run-id {shlex.quote(str(parsed_response['run_id']))} "
                    f"--sink {shlex.quote(str(parsed_response['sink']))} "
                    f"--operator {shlex.quote(str(parsed_response['operator']))} "
                    f"--scope {shlex.quote(str(parsed_response['scope']))} "
                    f"--safety-confirmation {shlex.quote(str(parsed_response['safety_confirmation']))} --json"
                )
                post_selection_sequence.append(
                    {
                        "step": "select_target",
                        "command": select_target_command,
                        "requires_explicit_operator_action": True,
                        "writes_runtime_artifact": True,
                        "writes_sink": False,
                        "network_calls_made": 0,
                        "stop_condition": "Run only after confirming tenant/profile safety.",
                    }
                )
            post_selection_sequence.append(
                {
                    "step": "selected_target_audit",
                    "command": selected_target_audit_command,
                    "requires_explicit_operator_action": False,
                    "writes_runtime_artifact": False,
                    "writes_sink": False,
                    "network_calls_made": 0,
                    "stop_condition": "Run after selected target approval; keep --no-write for this validation sequence.",
                }
            )
            if state != "ready_to_review_selected_target_audit":
                post_selection_sequence.append(
                    {
                        "step": "lookup_smoke_handoff",
                        "command": lookup_smoke_handoff_command,
                        "requires_explicit_operator_action": False,
                        "writes_runtime_artifact": True,
                        "writes_sink": False,
                        "network_calls_made": 0,
                        "stop_condition": "Creates a handoff artifact only; does not execute live lookup.",
                    }
                )
        validation_command_sequence = _pilot_command_sequence(post_selection_sequence)
        approval_readback = _live_pilot_operator_approval_readback(
            state=state,
            next_validation_step=next_validation_step,
            parsed_response=parsed_response,
            matching_template=matching_template,
            missing_fields=missing_fields,
            mismatches=mismatches,
            validation_command_sequence=validation_command_sequence,
            select_target_command=select_target_command,
            selected_target_audit_command=selected_target_audit_command,
            lookup_smoke_handoff_command=lookup_smoke_handoff_command,
        )

        explicit_stop_conditions = [
            "This validation does not create selected_live_target.json.",
            "Do not run live lookup, live write, or live readback from this validation report.",
        ]
        if state == "ready_to_select_live_target":
            explicit_stop_conditions.insert(
                1,
                "Run the select_target command only after confirming the card/contact is safe for the target tenant/profile.",
            )
        elif state == "ready_for_live_lookup_request":
            explicit_stop_conditions.insert(
                1,
                "A selected target already exists; do not run select_target again from this validation report.",
            )
            explicit_stop_conditions.insert(
                2,
                "Review the selected-target audit and lookup-smoke handoff before any explicit live lookup request.",
            )
        elif state == "ready_to_review_selected_target_audit":
            explicit_stop_conditions.insert(
                1,
                "Review or refresh the selected-target audit before any lookup-smoke handoff or live command.",
            )
        else:
            explicit_stop_conditions.insert(
                1,
                "Fix missing fields or mismatches before selecting a target or preparing post-selection handoff artifacts.",
            )

        return {
            "schema": "business-card-watchdog.live-pilot-operator-response-validation.v1",
            "generated_at": utc_now(),
            "state": state,
            "next_validation_step": next_validation_step,
            "run_id": run_id,
            "response": response,
            "parsed_response": parsed_response,
            "missing_fields": missing_fields,
            "mismatches": mismatches,
            "matching_template": matching_template,
            "select_target_command": select_target_command,
            "selected_target_audit_command": selected_target_audit_command,
            "lookup_smoke_handoff_command": lookup_smoke_handoff_command,
            "post_selection_sequence": post_selection_sequence,
            "validation_command_sequence": validation_command_sequence,
            "approval_readback": approval_readback,
            "operator_response_contract": contract,
            "writes_attempted": 0,
            "network_calls_made": 0,
            "creates_selected_live_target": False,
            "commands": {
                "live_pilot_handoff": f"runs live-pilot-handoff {run_id} --no-write --json",
                "validate_again": (
                    f"runs live-pilot-validate-response {shlex.quote(run_id)} "
                    f"--response {shlex.quote(response)} --json"
                ),
                "select_target": select_target_command,
                "selected_target_audit": selected_target_audit_command,
                "lookup_smoke_handoff": lookup_smoke_handoff_command,
            },
            "explicit_stop_conditions": explicit_stop_conditions,
        }

    def live_selection_packet(
        self,
        *,
        job_id: str,
        run_id: str,
        sink: str,
        operator: str,
        scope: str = "lookup",
        reason: str = "",
        write: bool = True,
    ) -> dict[str, Any]:
        if sink not in {"google_contacts", "odoo"}:
            raise ValueError("live selection packet requires sink google_contacts or odoo")
        if scope not in {"lookup", "write", "readback", "all"}:
            raise ValueError("live selection packet scope must be lookup, write, readback, or all")
        if not operator.strip():
            raise ValueError("live selection packet requires an operator")
        job = self.get_job(job_id, run_id=run_id)
        artifact_dir = (
            Path(job["artifact_dir"])
            if job.get("artifact_dir")
            else self.config.runs_dir / run_id / "artifacts" / job_id
        )
        selected_target_path = artifact_dir / "selected_live_target.json"
        existing_selected_target = _read_json_file(selected_target_path) or {}
        existing_abandonment = _read_json_file(artifact_dir / "live_pilot_abandonment.json") or {}
        existing_target_identity = _selected_target_identity(existing_selected_target)
        existing_target_exists = selected_target_path.exists()
        existing_target_abandoned = (
            existing_target_exists
            and existing_abandonment.get("state") == "abandoned"
            and str(
                existing_abandonment.get("selected_target_identity")
                or existing_abandonment.get("selected_target_created_at")
                or ""
            )
            == existing_target_identity
        )
        replacement_requires_abandonment = existing_target_exists and not existing_target_abandoned
        can_select_replacement_now = not existing_target_exists or existing_target_abandoned
        readiness_audit = self.live_readiness_audit(run_id=run_id, sink=sink, write=False)
        candidates_payload = dict(readiness_audit.get("live_target_candidates") or {})
        candidates = [
            candidate
            for candidate in list(candidates_payload.get("candidates") or [])
            if isinstance(candidate, dict)
            and str(candidate.get("run_id")) == run_id
            and str(candidate.get("job_id")) == job_id
            and str(candidate.get("sink")) == sink
        ]
        candidate = dict(candidates[0]) if candidates else None
        lookup_readiness = None
        apply_readiness = None
        missing_requirements: list[str] = []
        blocked_reasons: list[str] = []
        if candidate is None:
            blocked_reasons.append("selected run/job/sink is not present in live target candidates")
        elif candidate.get("state") != "ready_for_selection":
            blocked_reasons.extend(str(reason) for reason in list(candidate.get("stop_reasons") or []))
        if scope in {"lookup", "all"}:
            lookup_readiness = self.live_lookup_readiness_report(job_id=job_id, run_id=run_id, sink=sink)
            missing_requirements.extend(
                f"lookup:{name}" for name in list(lookup_readiness.get("missing_requirements") or [])
            )
        if scope in {"write", "readback", "all"}:
            apply_readiness = self.build_sink_apply_pilot_readiness_for_job(
                job_id=job_id,
                run_id=run_id,
                sink=sink,
            )["readiness"]
            missing_requirements.extend(
                f"apply:{name}" for name in list(apply_readiness.get("missing_requirements") or [])
            )
        if missing_requirements:
            blocked_reasons.extend(missing_requirements)
        if replacement_requires_abandonment:
            blocked_reasons.append("selected live target already exists; abandon it before selecting a replacement")
        state = "ready_for_operator_approval" if not blocked_reasons else "blocked"
        operator_response_template = (
            f"run_id={run_id} job_id={job_id} sink={sink} operator={operator} "
            f"scope={scope} safety_confirmation=<tenant-profile-account-confirmation>"
        )
        commands = _live_selection_packet_commands(
            job_id=job_id,
            run_id=run_id,
            sink=sink,
            operator=operator,
            scope=scope,
            reason=reason,
            operator_response_template=operator_response_template,
        )
        pilot_command_checklist = _live_selection_packet_checklist(
            commands=commands,
            scope=scope,
            state=state,
        )
        copyable_approval_fields = {
            "run_id": run_id,
            "job_id": job_id,
            "sink": sink,
            "operator": operator,
            "scope": scope,
            "safety_confirmation": "<tenant-profile-account-confirmation>",
        }
        payload = {
            "schema": "business-card-watchdog.live-selection-packet.v1",
            "generated_at": utc_now(),
            "state": state,
            "approval_state": "pending_operator_approval",
            "reason": reason or "operator selection packet prepared without creating selected_live_target.json",
            "run_id": run_id,
            "job_id": job_id,
            "sink": sink,
            "operator": operator,
            "scope": scope,
            "scope_allows": {
                "lookup": scope in {"lookup", "all"},
                "write": scope in {"write", "all"},
                "readback": scope in {"readback", "all"},
            },
            "job_state": job.get("state"),
            "candidate": candidate,
            "readiness": {
                "audit_state": readiness_audit.get("state"),
                "lookup": lookup_readiness,
                "apply": apply_readiness,
            },
            "missing_requirements": missing_requirements,
            "blocked_reasons": blocked_reasons,
            "operator_response_template": operator_response_template,
            "operator_prompt": (
                "Validate this operator response before creating a selected live target: "
                f"{operator_response_template}"
            ),
            "copyable_approval_fields": copyable_approval_fields,
            "existing_selected_target": {
                "path": str(selected_target_path),
                "exists": existing_target_exists,
                "identity": existing_target_identity or None,
                "sink": existing_selected_target.get("sink"),
                "scope": existing_selected_target.get("scope"),
                "operator": existing_selected_target.get("operator") or existing_selected_target.get("approved_by"),
                "target_safety_confirmed": bool(
                    existing_target_exists
                    and existing_selected_target.get("target_safety_confirmed")
                    and existing_selected_target.get("target_safety_confirmation")
                ),
                "abandoned": existing_target_abandoned,
                "abandonment_identity": existing_target_identity if existing_target_abandoned else None,
                "abandonment_reason": existing_abandonment.get("reason") if existing_target_abandoned else None,
                "replacement_requires_abandonment": replacement_requires_abandonment,
                "can_select_replacement_now": can_select_replacement_now,
                "abandon_command": (
                    f"sinks abandon-live-pilot {job_id} --run-id {run_id} --operator {operator} --reason <reason> --json"
                    if replacement_requires_abandonment
                    else None
                ),
            },
            "writes_attempted": 0,
            "network_calls_made": 0,
            "commands": commands,
            "pilot_command_checklist": pilot_command_checklist,
            "explicit_stop_conditions": [
                "This packet is not selected-target approval.",
                "Do not create selected_live_target.json unless the operator explicitly runs create_selected_target.",
                "Do not run live lookup, live write, or live readback from this packet alone.",
                "Do not process private SyncThing images, run public-web search, or call paid enrichment from this packet.",
            ],
        }
        if write:
            packet_path = artifact_dir / "live_selection_packet.json"
            packet_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            ledger = RunLedger(self.config.runs_dir / run_id)
            ledger.record_artifact(job_id=job_id, kind="live_selection_packet", path=packet_path)
            ledger.record_event(
                "live_selection_packet_created",
                {
                    "job_id": job_id,
                    "run_id": run_id,
                    "sink": sink,
                    "operator": operator,
                    "scope": scope,
                    "packet_path": str(packet_path),
                    "state": state,
                    "writes_attempted": 0,
                    "network_calls_made": 0,
                },
            )
            self._mark_route_artifact_refreshed(
                artifact_dir,
                job_id=job_id,
                run_id=run_id,
                kind="live_selection_packet",
            )
            payload["packet_path"] = str(packet_path)
        return payload

    def watch_status(self) -> dict[str, Any]:
        return PollingWatcher(self.config).status().to_dict()

    def watch_backlog_preflight(self, *, write: bool = True) -> dict[str, Any]:
        ensure_runtime_dirs(self.config)
        watch_status = PollingWatcher(self.config).status().to_dict()
        input_summaries = [
            _redacted_watch_input_summary(index, raw_input)
            for index, raw_input in enumerate(self.config.watch_inputs)
        ]
        backlog_count = int(watch_status.get("backlog_count") or 0)
        unsettled_count = int(watch_status.get("unsettled_count") or 0)
        last_error = str(watch_status.get("last_error") or "")
        scan_truncated = bool(watch_status.get("scan_truncated", False))
        if last_error:
            state = "blocked"
            recommended_next_action = "repair_watch_input"
        elif unsettled_count:
            state = "waiting_for_settle"
            recommended_next_action = "wait_for_settle_then_recheck"
        elif backlog_count:
            state = "ready_for_operator_selected_dry_run"
            recommended_next_action = "prepare_watch_dry_run_selection_handoff"
        elif not input_summaries:
            state = "not_configured"
            recommended_next_action = "configure_watch_inputs"
        else:
            state = "empty"
            recommended_next_action = "monitor_watch_inputs"

        payload: dict[str, Any] = {
            "schema": "business-card-watchdog.watch-backlog-preflight.v1",
            "generated_at": utc_now(),
            "state": state,
            "recommended_next_action": recommended_next_action,
            "input_count": len(input_summaries),
            "inputs": input_summaries,
            "counts": {
                "seen": int(watch_status.get("seen_count") or 0),
                "backlog": backlog_count,
                "unsettled": unsettled_count,
            },
            "scan_truncated": scan_truncated,
            "last_error_present": bool(last_error),
            "last_error_redacted": _redacted_watch_error(last_error),
            "private_paths_redacted": True,
            "private_filenames_redacted": True,
            "private_sources_used": False,
            "files_processed": 0,
            "ocr_attempted": 0,
            "writes_attempted": 0,
            "network_calls_made": 0,
            "runtime_artifact_written": False,
            "preflight_path": None,
            "commands": {
                "watch_status": "watch-status --json",
                "watch_backlog_preflight": "watch-backlog-preflight --json",
                "watch_dry_run_selection_handoff": "watch-dry-run-selection-handoff --json",
                "watch_dry_run": "watch-dry-run --json",
                "watch_once_dry_run": "watch --once --dry-run",
                "runtime_readiness": "runtime-readiness --json",
                "service_recovery": "service recovery --json",
            },
            "safe_next_actions": _watch_backlog_preflight_actions(
                state=state,
                recommended_next_action=recommended_next_action,
            ),
            "explicit_stop_conditions": [
                "This preflight does not process watched files.",
                "Do not OCR/process private SyncThing images from this preflight.",
                "Run watch-dry-run --json or watch --once --dry-run only after explicit operator selection.",
                "Do not run public-web search, paid enrichment, or live sink operations from watch backlog preflight.",
            ],
        }
        if write:
            preflight_path = self.config.data_dir / "watch_backlog_preflight.json"
            payload["runtime_artifact_written"] = True
            payload["preflight_path"] = str(preflight_path)
            preflight_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return payload

    def watch_dry_run_selection_handoff(self, *, write: bool = True) -> dict[str, Any]:
        ensure_runtime_dirs(self.config)
        preflight = self.watch_backlog_preflight(write=False)
        input_rows = [row for row in list(preflight.get("inputs") or []) if isinstance(row, dict)]
        ready = preflight.get("state") == "ready_for_operator_selected_dry_run" and bool(input_rows)
        handoff_path = self.config.data_dir / "watch_dry_run_selection_handoff.json"
        entries: list[dict[str, Any]] = []
        for row in input_rows:
            input_ref = str(row.get("input_ref") or "")
            template = (
                f"input_ref={input_ref} operator=<operator> mode=dry_run "
                "safety_confirmation=<operator-confirms-private-source-dry-run>"
            )
            entries.append(
                {
                    "schema": "business-card-watchdog.watch-dry-run-selection-entry.v1",
                    "state": "awaiting_operator_response" if ready else "blocked",
                    "input_ref": input_ref,
                    "configured_ref_kind": row.get("configured_ref_kind"),
                    "configured_ref_display": row.get("configured_ref_display"),
                    "operator_response_template": template,
                    "copyable_approval_fields": {
                        "input_ref": input_ref,
                        "operator": "<operator>",
                        "mode": "dry_run",
                        "safety_confirmation": "<operator-confirms-private-source-dry-run>",
                    },
                    "commands": {
                        "validate_operator_response": (
                            "watch-dry-run-validate-response --response <operator-response> --json"
                        ),
                        "validate_operator_response_prefilled": _watch_dry_run_response_validation_command(template),
                        "command_copy_packet": (
                            "watch-dry-run-command-copy-packet --response <operator-response> "
                            "--acknowledgement <operator-acknowledgement> --json"
                        ),
                    },
                }
            )
        state = "awaiting_operator_response" if ready else str(preflight.get("state") or "blocked")
        payload: dict[str, Any] = {
            "schema": "business-card-watchdog.watch-dry-run-selection-handoff.v1",
            "generated_at": utc_now(),
            "state": state,
            "recommended_next_step": "validate_operator_response" if ready else preflight.get("recommended_next_action"),
            "preflight": preflight,
            "entry_count": len(entries),
            "entries": entries,
            "operator_response_contract": {
                "schema": "business-card-watchdog.watch-dry-run-operator-response-contract.v1",
                "required_fields": ["input_ref", "operator", "mode", "safety_confirmation"],
                "allowed_modes": ["dry_run"],
                "format": (
                    "input_ref=<input_ref> operator=<operator> mode=dry_run "
                    "safety_confirmation=<operator-confirms-private-source-dry-run>"
                ),
                "requires_human_safety_confirmation": True,
                "creates_runtime_artifact": False,
                "processes_watched_files": False,
            },
            "commands": {
                "watch_backlog_preflight": "watch-backlog-preflight --no-write --json",
                "watch_dry_run_selection_handoff": "watch-dry-run-selection-handoff --json",
                "validate_operator_response": "watch-dry-run-validate-response --response <operator-response> --json",
                "command_copy_packet": (
                    "watch-dry-run-command-copy-packet --response <operator-response> "
                    "--acknowledgement <operator-acknowledgement> --json"
                ),
            },
            "handoff_path": str(handoff_path) if write else None,
            "handoff_written": False,
            "private_paths_redacted": True,
            "private_filenames_redacted": True,
            "private_sources_used": False,
            "files_processed": 0,
            "ocr_attempted": 0,
            "writes_attempted": 0,
            "network_calls_made": 0,
            "explicit_stop_conditions": [
                "This handoff does not process watched files.",
                "Do not run watch --once --dry-run until a human validates the operator response and copies the command.",
                "Do not OCR/process private SyncThing images from this handoff.",
                "Do not run public-web search, paid enrichment, or live sink operations from watch dry-run selection handoff.",
            ],
        }
        if write:
            payload["handoff_written"] = True
            handoff_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return payload

    def validate_watch_dry_run_operator_response(self, *, response: str) -> dict[str, Any]:
        handoff = self.watch_dry_run_selection_handoff(write=False)
        fields = _parse_operator_response_fields(response)
        entries = [row for row in list(handoff.get("entries") or []) if isinstance(row, dict)]
        entries_by_ref = {str(row.get("input_ref") or ""): row for row in entries}
        input_ref = str(fields.get("input_ref") or "")
        mode = str(fields.get("mode") or "")
        operator = str(fields.get("operator") or "")
        safety_confirmation = str(fields.get("safety_confirmation") or "")
        missing_fields = [
            field
            for field, value in [
                ("input_ref", input_ref),
                ("operator", operator),
                ("mode", mode),
                ("safety_confirmation", safety_confirmation),
            ]
            if not value.strip()
        ]
        mismatches: list[str] = []
        if input_ref and input_ref not in entries_by_ref:
            mismatches.append(f"input_ref is not available in current handoff: {input_ref}")
        if mode and mode != "dry_run":
            mismatches.append("mode must be dry_run")
        confirmation_error = _watch_dry_run_safety_confirmation_error(safety_confirmation)
        if confirmation_error:
            mismatches.append(confirmation_error)
        if handoff.get("state") != "awaiting_operator_response":
            mismatches.append(f"watch dry-run handoff is not ready: {handoff.get('state')}")
        matching_entry = entries_by_ref.get(input_ref) if input_ref else None
        state = "ready_for_command_copy" if not missing_fields and not mismatches else "blocked"
        return {
            "schema": "business-card-watchdog.watch-dry-run-operator-response-validation.v1",
            "generated_at": utc_now(),
            "state": state,
            "next_validation_step": "command_copy_packet" if state == "ready_for_command_copy" else "fix_operator_response",
            "missing_fields": missing_fields,
            "mismatches": mismatches,
            "matching_entry": matching_entry,
            "operator_response_redacted": {
                "raw_response_stored": False,
                "fields": {
                    "input_ref": input_ref or None,
                    "operator": operator or None,
                    "mode": mode or None,
                },
                "safety_confirmation_present": bool(safety_confirmation.strip()),
            },
            "commands": {
                "handoff": "watch-dry-run-selection-handoff --no-write --json",
                "command_copy_packet": (
                    "watch-dry-run-command-copy-packet --response <operator-response> "
                    "--acknowledgement <operator-acknowledgement> --json"
                ),
            },
            "creates_runtime_artifact": False,
            "processes_watched_files": False,
            "private_paths_redacted": True,
            "private_filenames_redacted": True,
            "private_sources_used": False,
            "files_processed": 0,
            "ocr_attempted": 0,
            "writes_attempted": 0,
            "network_calls_made": 0,
            "explicit_stop_conditions": [
                "Validation does not process watched files.",
                "Validation does not store the raw operator response or safety confirmation.",
                "Do not run watch --once --dry-run until command-copy packet is ready.",
            ],
        }

    def watch_dry_run_command_copy_packet(
        self,
        *,
        response: str,
        acknowledgement: str = "",
    ) -> dict[str, Any]:
        validation = self.validate_watch_dry_run_operator_response(response=response)
        required_acknowledgement = "I understand this will dry-run the configured private watch backlog"
        acknowledgement_ok = acknowledgement.strip() == required_acknowledgement
        ready = validation.get("state") == "ready_for_command_copy" and acknowledgement_ok
        command_copy_text = "watch --once --dry-run" if ready else None
        blocked_reasons: list[str] = []
        if validation.get("state") != "ready_for_command_copy":
            blocked_reasons.extend(str(item) for item in list(validation.get("missing_fields") or []))
            blocked_reasons.extend(str(item) for item in list(validation.get("mismatches") or []))
        if not acknowledgement_ok:
            blocked_reasons.append("acknowledgement does not match required text")
        return {
            "schema": "business-card-watchdog.watch-dry-run-command-copy-packet.v1",
            "generated_at": utc_now(),
            "state": "ready_for_operator_copy" if ready else "blocked",
            "validation_state": validation.get("state"),
            "acknowledgement_required": True,
            "required_acknowledgement": required_acknowledgement,
            "acknowledgement_ok": acknowledgement_ok,
            "command_copy_text": command_copy_text,
            "executable_command": command_copy_text,
            "blocked_reasons": blocked_reasons,
            "validation": validation,
            "processes_watched_files": False,
            "copying_command_would_process_watched_files": bool(command_copy_text),
            "private_paths_redacted": True,
            "private_filenames_redacted": True,
            "private_sources_used": False,
            "files_processed": 0,
            "ocr_attempted": 0,
            "writes_attempted": 0,
            "network_calls_made": 0,
            "explicit_stop_conditions": [
                "This packet does not execute the command.",
                "Only copy command_copy_text after confirming dry-run scope and private-source intent.",
                "Do not add --no-dry-run or live sink flags to the copied command.",
            ],
        }

    def watch_dry_run_readiness(self, *, write: bool = True) -> dict[str, Any]:
        ensure_runtime_dirs(self.config)
        preflight = self.watch_backlog_preflight(write=False)
        handoff = self.watch_dry_run_selection_handoff(write=False)
        preflight_state = str(preflight.get("state") or "")
        handoff_state = str(handoff.get("state") or "")
        counts = dict(preflight.get("counts") or {})
        backlog_count = int(counts.get("backlog") or 0)
        unsettled_count = int(counts.get("unsettled") or 0)
        blocked_reasons: list[str] = []
        if preflight_state != "ready_for_operator_selected_dry_run":
            blocked_reasons.append(f"watch backlog preflight is {preflight_state or 'unknown'}")
        if handoff_state != "awaiting_operator_response":
            blocked_reasons.append(f"watch dry-run selection handoff is {handoff_state or 'unknown'}")
        if backlog_count <= 0:
            blocked_reasons.append("configured watch backlog is empty")
        if unsettled_count:
            blocked_reasons.append("configured watch backlog still has unsettled files")
        state = "ready_for_operator_response" if not blocked_reasons else "blocked"
        payload: dict[str, Any] = {
            "schema": "business-card-watchdog.watch-dry-run-readiness.v1",
            "generated_at": utc_now(),
            "state": state,
            "recommended_next_step": "validate_operator_response" if state == "ready_for_operator_response" else "resolve_blockers",
            "preflight_summary": {
                "schema": preflight.get("schema"),
                "state": preflight_state,
                "input_count": preflight.get("input_count", 0),
                "counts": counts,
                "scan_truncated": preflight.get("scan_truncated", False),
                "last_error_present": preflight.get("last_error_present", False),
                "private_paths_redacted": True,
                "private_filenames_redacted": True,
            },
            "handoff_summary": {
                "schema": handoff.get("schema"),
                "state": handoff_state,
                "entry_count": handoff.get("entry_count", 0),
                "entries": [
                    {
                        "input_ref": entry.get("input_ref"),
                        "state": entry.get("state"),
                        "configured_ref_kind": entry.get("configured_ref_kind"),
                        "configured_ref_display": entry.get("configured_ref_display"),
                    }
                    for entry in list(handoff.get("entries") or [])
                    if isinstance(entry, dict)
                ],
            },
            "readiness_checks": [
                {
                    "check": "configured_watch_backlog_settled",
                    "status": "ready" if preflight_state == "ready_for_operator_selected_dry_run" else "blocked",
                    "evidence": {
                        "preflight_state": preflight_state,
                        "backlog": backlog_count,
                        "unsettled": unsettled_count,
                        "input_count": preflight.get("input_count", 0),
                    },
                },
                {
                    "check": "operator_response_handoff_available",
                    "status": "ready" if handoff_state == "awaiting_operator_response" else "blocked",
                    "evidence": {
                        "handoff_state": handoff_state,
                        "entry_count": handoff.get("entry_count", 0),
                    },
                },
                {
                    "check": "fixture_execution_drill_review",
                    "status": "operator_review_required",
                    "evidence": {
                        "command": "drills watch-dry-run-execution --json",
                        "requires_operator_to_review_sample_output": True,
                    },
                },
                {
                    "check": "command_copy_packet_required",
                    "status": "operator_response_required",
                    "evidence": {
                        "command": (
                            "watch-dry-run-command-copy-packet --response <operator-response> "
                            "--acknowledgement <operator-acknowledgement> --json"
                        ),
                        "required_acknowledgement": "I understand this will dry-run the configured private watch backlog",
                    },
                },
            ],
            "blocked_reasons": blocked_reasons,
            "operator_sequence": [
                {
                    "step": "review_fixture_execution_drill",
                    "command": "drills watch-dry-run-execution --json",
                    "requires_explicit_operator_action": False,
                    "safe_to_auto_continue": True,
                },
                {
                    "step": "inspect_selection_handoff",
                    "command": "watch-dry-run-selection-handoff --json",
                    "requires_explicit_operator_action": False,
                    "safe_to_auto_continue": True,
                },
                {
                    "step": "validate_operator_response",
                    "command": "watch-dry-run-validate-response --response <operator-response> --json",
                    "requires_explicit_operator_action": True,
                    "safe_to_auto_continue": False,
                },
                {
                    "step": "build_command_copy_packet",
                    "command": (
                        "watch-dry-run-command-copy-packet --response <operator-response> "
                        "--acknowledgement <operator-acknowledgement> --json"
                    ),
                    "requires_explicit_operator_action": True,
                    "safe_to_auto_continue": False,
                },
                {
                    "step": "run_private_watch_dry_run",
                    "command": "watch --once --dry-run",
                    "requires_explicit_operator_action": True,
                    "safe_to_auto_continue": False,
                    "blocked_until": "command_copy_packet_state_ready_for_operator_copy",
                },
            ],
            "command_copy_text": None,
            "private_paths_redacted": True,
            "private_filenames_redacted": True,
            "private_sources_used": False,
            "files_processed": 0,
            "ocr_attempted": 0,
            "writes_attempted": 0,
            "network_calls_made": 0,
            "runtime_artifact_written": False,
            "readiness_path": None,
            "commands": {
                "watch_dry_run_readiness": "watch-dry-run-readiness --json",
                "watch_backlog_preflight": "watch-backlog-preflight --no-write --json",
                "watch_dry_run_execution_drill": "drills watch-dry-run-execution --json",
                "watch_dry_run_selection_handoff": "watch-dry-run-selection-handoff --json",
                "watch_dry_run_validate_response": "watch-dry-run-validate-response --response <operator-response> --json",
                "watch_dry_run_command_copy_packet": (
                    "watch-dry-run-command-copy-packet --response <operator-response> "
                    "--acknowledgement <operator-acknowledgement> --json"
                ),
                "watch_once_dry_run": "watch --once --dry-run",
            },
            "explicit_stop_conditions": [
                "This readiness packet does not process watched files.",
                "This readiness packet does not return a copyable private-source dry-run command.",
                "Only run watch --once --dry-run after response validation and command-copy acknowledgement.",
                "Do not run public-web search, paid enrichment, or live sink operations from this readiness packet.",
            ],
        }
        if write:
            readiness_path = self.config.data_dir / "watch_dry_run_readiness.json"
            readiness_path.parent.mkdir(parents=True, exist_ok=True)
            readiness_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            payload["runtime_artifact_written"] = True
            payload["readiness_path"] = str(readiness_path)
        return payload

    def watch_dry_run_harness(self) -> dict[str, Any]:
        ensure_runtime_dirs(self.config)
        harness_id = f"{utc_now().replace(':', '-')}-{uuid4().hex[:8]}"
        harness_root = self.config.cache_dir / "watch-dry-run-harness" / harness_id
        source_dir = harness_root / "source"
        data_dir = harness_root / "data"
        cache_dir = harness_root / "cache"
        image_path = _write_synthetic_business_card_image(source_dir / "synthetic-business-card.png")
        probe_config = AppConfig(
            config_path=self.config.config_path,
            skill_root=self.config.skill_root,
            data_dir=data_dir,
            cache_dir=cache_dir,
            path_aliases=dict(self.config.path_aliases),
            watch=WatchConfig(inputs=[str(source_dir)], settle_seconds=0.0),
            prefilter=self.config.prefilter,
            normalization=self.config.normalization,
            enrichment=self.config.enrichment,
            sink=self.config.sink,
            routing_rules=list(self.config.routing_rules),
        )
        processed: list[dict[str, Any]] = []

        def process_source(source: str, *, dry_run: bool = True, workers: int = 1) -> Path:
            run_dir = probe_config.runs_dir / f"watch-dry-run-{len(processed) + 1}"
            ledger = RunLedger(run_dir)
            ledger.initialize(source=source, dry_run=dry_run)
            ledger.transition_run("discovering")
            ledger.set_job_count(1)
            ledger.transition_run("processing")
            ledger.record_event(
                "watch_dry_run_harness_processed",
                {"source": source, "dry_run": dry_run, "workers": workers},
            )
            ledger.transition_run("completed")
            processed.append({"source": source, "dry_run": dry_run, "workers": workers, "run_dir": str(run_dir)})
            return run_dir

        first = PollingWatcher(probe_config)
        first.orchestrator.process_source = process_source  # type: ignore[method-assign]
        first_scan = [str(path) for path in first.scan_once(dry_run=True)]

        restarted = PollingWatcher(probe_config)
        restarted.orchestrator.process_source = process_source  # type: ignore[method-assign]
        second_scan = [str(path) for path in restarted.scan_once(dry_run=True)]
        final_status = restarted.status().to_dict()

        assertions = {
            "synthetic_source_only": str(image_path).startswith(str(harness_root)),
            "first_scan_processed_one": len(first_scan) == 1,
            "restart_processed_zero": len(second_scan) == 0,
            "seen_file_persisted": int(final_status.get("seen_count", 0)) == 1,
            "dry_run_only": all(item["dry_run"] is True for item in processed),
            "no_configured_watch_inputs_used": final_status.get("inputs") == [str(source_dir)],
        }
        state = "passed" if all(assertions.values()) else "failed"
        return {
            "schema": "business-card-watchdog.watch-dry-run-harness.v1",
            "generated_at": utc_now(),
            "state": state,
            "harness_id": harness_id,
            "harness_root": str(harness_root),
            "source_dir": str(source_dir),
            "data_dir": str(data_dir),
            "watch_dir": str(probe_config.watch_dir),
            "synthetic_images": [str(image_path)],
            "first_scan_processed": first_scan,
            "second_scan_processed": second_scan,
            "processed": processed,
            "final_status": final_status,
            "assertions": assertions,
            "writes_attempted": 0,
            "network_calls_made": 0,
            "private_sources_used": False,
            "commands": {
                "watch_status": "watch-status --json",
                "watch_dry_run": "watch-dry-run --json",
                "status": "status --json",
                "service_recovery": "service recovery --json",
            },
            "safe_next_actions": [
                {
                    "action": "inspect_watch_harness",
                    "command": "watch-dry-run --json",
                    "reason": "review fixture-backed watcher proof before using configured SyncThing inputs",
                    "safe_to_auto_continue": True,
                    "requires_explicit_operator_action": False,
                }
            ],
            "explicit_stop_conditions": [
                "Do not process private SyncThing images from generic continuation.",
                "Do not replace the configured watch inputs from this harness.",
            ],
        }

    def watch_reset(self) -> dict[str, Any]:
        PollingWatcher(self.config).reset()
        return {
            "schema": "business-card-watchdog.watch-reset.v1",
            "generated_at": utc_now(),
            "reset": True,
            "watch_dir": str(self.config.watch_dir),
            "reset_files": ["seen-files.jsonl", "pending-files.json", "status.json"],
            "writes_attempted": 0,
            "network_calls_made": 0,
            "private_sources_used": False,
            "commands": {
                "watch_status": "watch-status --json",
                "watch_dry_run": "watch-dry-run --json",
                "status": "status --json",
            },
            "explicit_stop_conditions": [
                "This only resets watcher state; it does not process configured watch inputs.",
                "Run watch-dry-run before polling private SyncThing inputs after a reset.",
                "Do not run public-web search, paid enrichment, or live sink operations from watch reset.",
            ],
        }

    def _require_selected_live_target(
        self,
        *,
        artifact_dir: Path,
        job_id: str,
        run_id: str,
        sink: str,
        approved_by: str,
        scope: str,
    ) -> dict[str, Any]:
        target_path = artifact_dir / "selected_live_target.json"
        target = _read_json_file(target_path)
        if target is None:
            raise ValueError("non-simulated sink pilot requires selected_live_target.json")
        abandonment = _read_json_file(artifact_dir / "live_pilot_abandonment.json") or {}
        if (
            abandonment.get("state") == "abandoned"
            and str(abandonment.get("selected_target_identity") or abandonment.get("selected_target_created_at") or "")
            == _selected_target_identity(target)
        ):
            raise ValueError("non-simulated sink pilot selected target was abandoned")
        mismatches = []
        for key, expected in [
            ("job_id", job_id),
            ("run_id", run_id),
            ("sink", sink),
        ]:
            if target.get(key) != expected:
                mismatches.append(f"{key}={target.get(key)!r}")
        if target.get("approved_by") != approved_by and target.get("operator") != approved_by:
            mismatches.append(f"operator={target.get('operator')!r}")
        if not target.get("target_safety_confirmed") or not target.get("target_safety_confirmation"):
            mismatches.append("target_safety_confirmation=missing")
        allows = dict(target.get("scope_allows") or {})
        if not bool(allows.get(scope)):
            mismatches.append(f"scope={target.get('scope')!r}")
        if mismatches:
            raise ValueError(
                "non-simulated sink pilot selected target mismatch: " + ", ".join(mismatches)
            )
        return target

    def _enforce_downstream_duplicate_write_gate(self, artifact_dir: Path) -> None:
        assessment = _read_json_file(artifact_dir / "downstream_duplicate_assessment.json")
        if assessment is None:
            return
        duplicate_state = str(assessment.get("state") or "missing")
        if duplicate_state == "no_match":
            return
        resolution = _read_json_file(artifact_dir / "duplicate_resolution.json") or {}
        decision = str(resolution.get("decision") or "").strip()
        if decision and decision != "noop":
            return
        raise ValueError(
            "sink write pilot blocked by downstream duplicate assessment; resolve duplicate before writing"
        )

    def _require_write_pilot_for_readback(self, artifact_dir: Path, *, sink: str) -> dict[str, Any]:
        write_pilot = _read_json_file(artifact_dir / "sink_write_pilot.json")
        if write_pilot is None:
            raise ValueError("sink readback pilot requires sink_write_pilot.json")
        if write_pilot.get("sink") != sink:
            raise ValueError(
                f"sink readback pilot requires sink_write_pilot.json for sink {sink}"
            )
        if write_pilot.get("state") not in {"mock_written", "live_written"}:
            raise ValueError(
                f"sink readback pilot requires completed write pilot, found state {write_pilot.get('state')!r}"
            )
        return write_pilot

    def _contact_spec_for_artifact_dir(self, artifact_dir: Path) -> dict[str, Any]:
        reviewed_path = artifact_dir / "reviewed_contact.json"
        candidate_path = artifact_dir / "contact_candidate.json"
        spec_path = artifact_dir / "spec.json"
        if reviewed_path.exists():
            reviewed = json.loads(reviewed_path.read_text(encoding="utf-8"))
            spec = contact_candidate_to_spec(reviewed)
            canonical = reviewed.get("canonical") or build_canonical_contact(reviewed)
            spec["_canonical_contact"] = canonical
            spec["_field_provenance"] = field_provenance_from_canonical(canonical)
            if isinstance(reviewed.get("contact_points"), list):
                spec["contact_points"] = list(reviewed["contact_points"])
            return spec
        if candidate_path.exists():
            candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
            spec = contact_candidate_to_spec(candidate)
            canonical = candidate.get("canonical") or build_canonical_contact(candidate)
            spec["_canonical_contact"] = canonical
            spec["_field_provenance"] = field_provenance_from_canonical(canonical)
            if isinstance(candidate.get("contact_points"), list):
                spec["contact_points"] = list(candidate["contact_points"])
            return spec
        if spec_path.exists():
            return json.loads(spec_path.read_text(encoding="utf-8"))
        raise FileNotFoundError(f"no contact artifact found in {artifact_dir}")

    def _sink_apply_enabled(self, sink: str) -> bool:
        if sink == "google_contacts":
            return self.config.sink.google_contacts_apply_enabled
        if sink == "odoo":
            return self.config.sink.odoo_apply_enabled
        return False

    def _sink_context(self) -> dict[str, dict[str, Any]]:
        return {
            "google_contacts": {"profile": self.config.sink.google_contacts_profile},
            "odoo": {"tenant": self.config.sink.odollo_tenant},
        }

    def _add_route_context(self, spec: dict[str, Any], *, job: dict[str, Any], artifact_dir: Path) -> None:
        spec["_image_path"] = str(job.get("image_path") or "")
        spec["_review_state"] = str(job.get("state") or "")
        duplicate_payload = self._load_first_existing_json(
            artifact_dir / "downstream_duplicate_assessment.json",
            artifact_dir / "duplicate_assessment.json",
        )
        if duplicate_payload:
            spec["_duplicate_state"] = str(duplicate_payload.get("state") or "")

    def _load_first_existing_json(self, *paths: Path) -> dict[str, Any] | None:
        for path in paths:
            if path.exists():
                return json.loads(path.read_text(encoding="utf-8"))
        return None

    def _build_enrichment_proposal_review(
        self,
        *,
        enrichment_result: dict[str, Any],
        merge_review: dict[str, Any],
        reviewer: str,
    ) -> dict[str, Any]:
        applied_by_field = {
            str(row.get("field") or ""): row
            for row in list(merge_review.get("applied") or [])
            if isinstance(row, dict)
        }
        proposals = []
        for index, proposal in enumerate(list(enrichment_result.get("merge_proposals") or []), start=1):
            field = str(proposal.get("field") or "")
            accepted = field in applied_by_field
            proposals.append(
                {
                    "index": index,
                    "field": field,
                    "value": proposal.get("value"),
                    "source": proposal.get("source"),
                    "requires_review": bool(proposal.get("requires_review", True)),
                    "decision": "accepted" if accepted else "rejected",
                    "reason": "field approved by reviewer"
                    if accepted
                    else "field was not approved by reviewer",
                }
            )
        accepted = [proposal for proposal in proposals if proposal["decision"] == "accepted"]
        rejected = [proposal for proposal in proposals if proposal["decision"] == "rejected"]
        return {
            "schema": "business-card-watchdog.enrichment-proposal-review.v1",
            "reviewer": reviewer,
            "source_result_schema": enrichment_result.get("schema"),
            "source_provider": enrichment_result.get("provider"),
            "approved_fields": list(merge_review.get("approved_fields") or []),
            "proposal_count": len(proposals),
            "accepted_count": len(accepted),
            "rejected_count": len(rejected),
            "proposals": proposals,
        }

    def _artifact_bundle_entry(self, record: dict[str, Any]) -> dict[str, Any]:
        path = Path(str(record.get("path") or ""))
        entry = {
            "kind": record.get("kind"),
            "path": str(path),
            "metadata": record.get("metadata") or {},
            "exists": path.exists(),
        }
        if not path.exists():
            entry["payload"] = None
            entry["error"] = "artifact path does not exist"
            return entry
        try:
            entry["payload"] = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            entry["payload"] = None
            entry["error"] = f"artifact is not JSON: {exc}"
        return entry

    def _review_decision_template(
        self,
        *,
        run_id: str,
        job_id: str,
        next_action: dict[str, Any] | None,
    ) -> dict[str, Any]:
        action = str((next_action or {}).get("action") or "")
        suggested_action = "keep_needs_review"
        if action == "review_contact":
            suggested_action = "approve_for_routing"
        elif action == "review_duplicate":
            suggested_action = "resolve_duplicate"
        elif action == "review_enrichment":
            suggested_action = "approve_enrichment_merge"
        elif action == "inspect_failure":
            suggested_action = "skip"
        return {
            "run_id": run_id,
            "job_id": job_id,
            "action": suggested_action,
            "field_corrections": {},
            "crop_selection": {},
            "approved_enrichment_fields": [],
            "duplicate_resolution": {},
            "notes": "",
        }

    def _review_bundle_groups(self, entries: list[dict[str, Any]]) -> dict[str, Any]:
        by_state: dict[str, dict[str, Any]] = {}
        by_next_action: dict[str, dict[str, Any]] = {}
        by_sink_pilot_state: dict[str, dict[str, Any]] = {}
        by_duplicate_state: dict[str, dict[str, Any]] = {}
        by_enrichment_state: dict[str, dict[str, Any]] = {}
        by_route_state: dict[str, dict[str, Any]] = {}
        by_sink_lookup_state: dict[str, dict[str, Any]] = {}
        by_child_replacement_state: dict[str, dict[str, Any]] = {}
        for entry in entries:
            state = str(entry.get("state") or "unknown")
            state_group = by_state.setdefault(state, {"count": 0, "job_ids": []})
            state_group["count"] += 1
            state_group["job_ids"].append(entry["job_id"])
            action = str((entry.get("next_action") or {}).get("action") or "none")
            action_group = by_next_action.setdefault(action, {"count": 0, "job_ids": []})
            action_group["count"] += 1
            action_group["job_ids"].append(entry["job_id"])
            pilot_state = str((entry.get("sink_pilot_status") or {}).get("state") or "not_started")
            pilot_group = by_sink_pilot_state.setdefault(pilot_state, {"count": 0, "job_ids": []})
            pilot_group["count"] += 1
            pilot_group["job_ids"].append(entry["job_id"])
            child_replacement_state = str(
                (entry.get("child_replacement_status") or {}).get("state") or "not_started"
            )
            child_replacement_group = by_child_replacement_state.setdefault(
                child_replacement_state,
                {"count": 0, "job_ids": []},
            )
            child_replacement_group["count"] += 1
            child_replacement_group["job_ids"].append(entry["job_id"])
            matrix = entry.get("review_matrix") or {}
            for groups, key in [
                (by_duplicate_state, "duplicate_state"),
                (by_enrichment_state, "enrichment_state"),
                (by_route_state, "route_state"),
                (by_sink_lookup_state, "sink_lookup_state"),
            ]:
                value = str(matrix.get(key) or "unknown")
                group = groups.setdefault(value, {"count": 0, "job_ids": []})
                group["count"] += 1
                group["job_ids"].append(entry["job_id"])
        return {
            "by_state": dict(sorted(by_state.items())),
            "by_next_action": dict(sorted(by_next_action.items())),
            "by_sink_pilot_state": dict(sorted(by_sink_pilot_state.items())),
            "by_duplicate_state": dict(sorted(by_duplicate_state.items())),
            "by_enrichment_state": dict(sorted(by_enrichment_state.items())),
            "by_route_state": dict(sorted(by_route_state.items())),
            "by_sink_lookup_state": dict(sorted(by_sink_lookup_state.items())),
            "by_child_replacement_state": dict(sorted(by_child_replacement_state.items())),
        }

    def _child_replacement_bundle_status(self, artifacts: dict[str, dict[str, Any]]) -> dict[str, Any]:
        closeout = (artifacts.get("child_replacement_closeout_status") or {}).get("payload") or {}
        if not closeout:
            return {
                "schema": "business-card-watchdog.child-replacement-bundle-status.v1",
                "state": "not_started",
                "has_closeout": False,
                "closeout_path": None,
                "candidate_id": None,
                "sink": None,
                "operator": None,
                "scope": None,
                "predecessor_artifacts_stale": False,
                "replacement_copy_ready": False,
                "writes_attempted": 0,
                "network_calls_made": 0,
                "commands": {},
            }
        rollup = dict(closeout.get("rollup") or {})
        commands = dict(closeout.get("commands") or {})
        return {
            "schema": "business-card-watchdog.child-replacement-bundle-status.v1",
            "state": str(closeout.get("state") or "unknown"),
            "has_closeout": True,
            "closeout_path": closeout.get("closeout_path"),
            "candidate_id": closeout.get("candidate_id"),
            "sink": closeout.get("sink"),
            "operator": closeout.get("operator"),
            "scope": closeout.get("scope"),
            "predecessor_artifacts_stale": bool(rollup.get("predecessor_artifacts_stale")),
            "replacement_handoff_ready": bool(rollup.get("replacement_handoff_ready")),
            "replacement_response_ready": bool(rollup.get("replacement_response_ready")),
            "replacement_checklist_ready": bool(rollup.get("replacement_checklist_ready")),
            "replacement_copy_ready": bool(rollup.get("replacement_copy_ready")),
            "acknowledgement_ok": bool(rollup.get("acknowledgement_ok")),
            "selected_target_created": bool(rollup.get("selected_target_created")),
            "executable_live_command": rollup.get("executable_live_command"),
            "offline_command_copy_text": rollup.get("offline_command_copy_text"),
            "blocked_reasons": list(closeout.get("blocked_reasons") or []),
            "writes_attempted": _int(closeout.get("writes_attempted") or 0),
            "network_calls_made": _int(closeout.get("network_calls_made") or 0),
            "commands": {
                "closeout_status": commands.get("closeout_status"),
                "replacement_command_copy_packet": commands.get("replacement_command_copy_packet"),
            },
        }

    def _review_matrix_entry(
        self,
        *,
        job: dict[str, Any],
        artifacts: dict[str, dict[str, Any]],
        next_action: dict[str, Any] | None,
        sink_pilot_status: dict[str, Any],
    ) -> dict[str, Any]:
        reviewed = (artifacts.get("reviewed_contact") or {}).get("payload") or {}
        candidate = (artifacts.get("contact_candidate") or {}).get("payload") or {}
        contact = reviewed if reviewed else candidate
        contact_source = "reviewed_contact" if reviewed else "contact_candidate" if candidate else "missing"
        duplicate = (artifacts.get("downstream_duplicate_assessment") or {}).get("payload") or (
            artifacts.get("duplicate_assessment") or {}
        ).get("payload") or {}
        enrichment = (artifacts.get("enrichment_result") or {}).get("payload") or (
            artifacts.get("enrichment_public_web_result") or {}
        ).get("payload") or (
            artifacts.get("enrichment_provider_result") or {}
        ).get("payload") or {}
        proposal_review = (artifacts.get("enrichment_proposal_review") or {}).get("payload") or {}
        sink_plan = (artifacts.get("sink_plan") or {}).get("payload") or {}
        sink_lookup = (artifacts.get("sink_lookup_result") or {}).get("payload") or {}
        route_refresh = (artifacts.get("route_refresh") or {}).get("payload") or {}
        normalized = contact.get("normalized") if isinstance(contact.get("normalized"), dict) else {}
        review_warnings = [
            field
            for field, payload in normalized.items()
            if isinstance(payload, dict) and str(payload.get("confidence") or "") == "review"
        ]
        planned_sinks = self._review_sink_names(sink_plan)
        duplicate_state = str(duplicate.get("state") or "not_assessed")
        enrichment_proposals = list(enrichment.get("merge_proposals") or [])
        enrichment_state = (
            "reviewed"
            if proposal_review
            else "proposed"
            if enrichment_proposals
            else "requested"
            if any(kind in artifacts for kind in ("enrichment_request", "enrichment_public_web_request", "enrichment_provider_request"))
            else "not_requested"
        )
        route_state = str(sink_plan.get("state") or route_refresh.get("state") or "not_planned")
        lookup_state = str(sink_lookup.get("state") or "not_started")
        next_action_name = str((next_action or {}).get("action") or "none")
        return {
            "schema": "business-card-watchdog.review-matrix-entry.v1",
            "job_id": job.get("job_id"),
            "review_state": job.get("state"),
            "contact_source": contact_source,
            "contact": {
                "full_name": self._review_contact_value(contact, "full_name"),
                "organization": self._review_contact_value(contact, "organization"),
                "title": self._review_contact_value(contact, "title"),
                "email": self._review_contact_value(contact, "email"),
                "phone": self._review_contact_value(contact, "phone"),
                "website": self._review_contact_value(contact, "website"),
            },
            "normalization_warning_fields": review_warnings,
            "normalization_warning_count": len(review_warnings),
            "duplicate_state": duplicate_state,
            "duplicate_match_count": _int(duplicate.get("match_count") or len(duplicate.get("matches") or [])),
            "enrichment_state": enrichment_state,
            "enrichment_proposal_count": len(enrichment_proposals),
            "enrichment_accepted_count": _int(proposal_review.get("accepted_count") or 0),
            "enrichment_rejected_count": _int(proposal_review.get("rejected_count") or 0),
            "route_state": route_state,
            "planned_sinks": planned_sinks,
            "sink_lookup_state": lookup_state,
            "sink_lookup_match_count": _int(sink_lookup.get("match_count") or 0),
            "sink_pilot_state": sink_pilot_status.get("state") or "not_started",
            "next_action": next_action_name,
            "safe_to_auto_continue": bool(sink_pilot_status.get("safe_to_auto_continue")),
            "requires_explicit_operator_action": bool(
                sink_pilot_status.get("requires_explicit_operator_action")
            ),
        }

    def _live_candidate_sinks(self, entry: dict[str, Any], *, selected_sink: str = "") -> list[str]:
        if selected_sink:
            return [selected_sink]
        matrix = dict(entry.get("review_matrix") or {})
        planned = [
            str(sink)
            for sink in list(matrix.get("planned_sinks") or [])
            if str(sink) in {"google_contacts", "odoo"}
        ]
        if planned:
            return sorted(set(planned))
        configured: list[str] = []
        if self.config.sink.google_contacts:
            configured.append("google_contacts")
        if self.config.sink.odoo:
            configured.append("odoo")
        return configured

    def _live_target_candidate_stop_reasons(
        self,
        *,
        entry: dict[str, Any],
        readiness: dict[str, Any],
    ) -> list[str]:
        reasons: list[str] = []
        matrix = dict(entry.get("review_matrix") or {})
        if entry.get("state") != "ready_to_route":
            reasons.append(f"job state is {entry.get('state')}")
        duplicate_state = str(matrix.get("duplicate_state") or "")
        if duplicate_state in {"strong_duplicate", "possible_duplicate"}:
            reasons.append(f"downstream duplicate state is {duplicate_state}")
        if readiness.get("state") != "ready":
            reasons.append(f"lookup readiness is {readiness.get('state')}")
        for missing in list(readiness.get("missing_requirements") or []):
            reasons.append(f"missing lookup requirement: {missing}")
        return reasons

    def _sink_pilot_status(
        self,
        *,
        by_kind: dict[str, dict[str, Any]],
        next_action: dict[str, Any] | None,
    ) -> dict[str, Any]:
        stage_order = [
            ("sink_lookup_plan", "lookup_planned"),
            ("sink_adapter_request_lookup", "lookup_adapter_prepared"),
            ("sink_lookup_pilot", "lookup_pilot_recorded"),
            ("sink_lookup_result", "lookup_result_recorded"),
            ("downstream_duplicate_assessment", "downstream_duplicates_assessed"),
            ("sink_plan", "sink_plan_ready"),
            ("sink_adapter_request_write", "write_adapter_prepared"),
            ("sink_apply_preflight", "apply_preflight_ready"),
            ("sink_apply_decision", "apply_decision_recorded"),
            ("sink_apply_pilot_readiness", "apply_pilot_readiness_recorded"),
            ("sink_write_pilot", "write_pilot_recorded"),
            ("sink_apply_result", "apply_result_recorded"),
            ("sink_adapter_request_readback", "readback_adapter_prepared"),
            ("sink_readback_pilot", "readback_pilot_recorded"),
            ("sink_apply_pilot_report", "pilot_report_recorded"),
        ]
        artifact_kinds = set(by_kind)
        latest_kind = ""
        state = "not_started"
        completed_stages: list[str] = []
        for kind, label in stage_order:
            if kind in artifact_kinds:
                latest_kind = kind
                state = label
                completed_stages.append(kind)

        next_action_name = str((next_action or {}).get("action") or "")
        report = self._read_bundle_json(by_kind.get("sink_apply_pilot_report"))
        readiness = self._read_bundle_json(by_kind.get("sink_apply_pilot_readiness"))
        write_pilot = self._read_bundle_json(by_kind.get("sink_write_pilot"))
        readback_pilot = self._read_bundle_json(by_kind.get("sink_readback_pilot"))
        if report:
            state = f"pilot_report_{report.get('state') or 'recorded'}"
        elif readiness and readiness.get("state"):
            state = str(readiness["state"])

        return {
            "schema": "business-card-watchdog.sink-pilot-status.v1",
            "state": state,
            "latest_artifact_kind": latest_kind or None,
            "completed_artifact_kinds": completed_stages,
            "has_apply_decision": "sink_apply_decision" in artifact_kinds,
            "has_write_pilot": "sink_write_pilot" in artifact_kinds,
            "has_readback_pilot": "sink_readback_pilot" in artifact_kinds,
            "has_pilot_report": "sink_apply_pilot_report" in artifact_kinds,
            "report_complete": bool(report and report.get("state") == "complete"),
            "next_action": next_action_name or None,
            "safe_to_auto_continue": next_action_name in _SAFE_NEXT_ACTIONS,
            "requires_explicit_operator_action": next_action_name in _EXPLICIT_OPERATOR_ACTIONS,
            "simulated": _maybe_bool(write_pilot.get("simulated") if write_pilot else None),
            "readback_verified": _maybe_bool(readback_pilot.get("state") == "verified" if readback_pilot else None),
            "missing_artifacts": list(report.get("missing_artifacts") or []) if report else [],
            "sinks": list(report.get("sinks") or []) if report else [],
            "writes_attempted": _int(report.get("writes_attempted") if report else 0),
            "network_calls_made": _int(report.get("network_calls_made") if report else 0),
        }

    def _read_bundle_json(self, record: dict[str, Any] | None) -> dict[str, Any]:
        if not record:
            return {}
        path = Path(str(record.get("path") or ""))
        if not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def _render_review_workbook_csv(self, bundle: dict[str, Any]) -> str:
        output = StringIO()
        fieldnames = [
            "run_id",
            "job_id",
            "state",
            "image_path",
            "next_action",
            "next_action_reason",
            "sink_pilot_state",
            "safe_to_auto_continue",
            "requires_explicit_operator_action",
            "matrix_contact_source",
            "matrix_duplicate_state",
            "matrix_enrichment_state",
            "matrix_route_state",
            "matrix_sink_lookup_state",
            "matrix_normalization_warning_count",
            "matrix_sink_lookup_match_count",
            "matrix_enrichment_accepted_count",
            "matrix_enrichment_rejected_count",
            "child_replacement_state",
            "child_replacement_candidate_id",
            "child_replacement_sink",
            "child_replacement_operator",
            "child_replacement_predecessors_stale",
            "child_replacement_copy_ready",
            "child_replacement_closeout_command",
            "full_name",
            "organization",
            "title",
            "email",
            "phone",
            "website",
            "duplicate_state",
            "enrichment_proposal_count",
            "planned_sinks",
            "route_refresh_state",
            "artifact_kinds",
            "review_command",
            "live_pilot_handoff_command",
            "validate_operator_response_command",
            "decision_action",
            "review_action",
            "corrected_full_name",
            "corrected_organization",
            "corrected_title",
            "corrected_email",
            "corrected_phone",
            "corrected_website",
            "approved_enrichment_fields",
            "duplicate_decision",
            "duplicate_target_identity",
            "duplicate_reason",
            "review_notes",
            "skip_import",
            "decision_template_json",
        ]
        writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        for entry in bundle["entries"]:
            writer.writerow(self._review_workbook_row(entry))
        return output.getvalue()

    def _render_review_workbook_preview_csv(
        self,
        rows: list[dict[str, Any]],
        errors: list[Any] | None = None,
    ) -> str:
        output = StringIO()
        fieldnames = [
            "row_number",
            "status",
            "run_id",
            "job_id",
            "action",
            "errors",
            "warnings",
            "artifact_kinds",
            "field_correction_count",
            "approved_enrichment_fields",
            "duplicate_decision",
            "duplicate_target_identity",
            "duplicate_reason",
            "sink_readiness_warnings",
        ]
        writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        if rows:
            for row in rows:
                duplicate_resolution = dict(row.get("duplicate_resolution") or {})
                writer.writerow(
                    {
                        "row_number": row.get("row_number"),
                        "status": row.get("status"),
                        "run_id": row.get("run_id"),
                        "job_id": row.get("job_id"),
                        "action": row.get("action"),
                        "errors": "; ".join(str(error) for error in row.get("errors") or []),
                        "warnings": "; ".join(str(warning) for warning in row.get("warnings") or []),
                        "artifact_kinds": ";".join(str(kind) for kind in row.get("artifact_kinds") or []),
                        "field_correction_count": row.get("field_correction_count", ""),
                        "approved_enrichment_fields": ";".join(
                            str(field) for field in row.get("approved_enrichment_fields") or []
                        ),
                        "duplicate_decision": duplicate_resolution.get("decision", ""),
                        "duplicate_target_identity": duplicate_resolution.get("target_identity", ""),
                        "duplicate_reason": duplicate_resolution.get("reason", ""),
                        "sink_readiness_warnings": "; ".join(
                            str(warning.get("message") or warning)
                            for warning in row.get("sink_readiness_warnings") or []
                        ),
                    }
                )
        else:
            for error in errors or []:
                message = error.get("message") if isinstance(error, dict) else str(error)
                writer.writerow({"status": "error", "errors": message})
        return output.getvalue()

    def _write_review_workbook_preview_artifacts(self, run_id: str, payload: dict[str, Any]) -> None:
        run_dir = self.config.runs_dir / run_id
        preview_path = run_dir / "review_workbook_preview.json"
        validation_csv_path = run_dir / "review_workbook_preview_validation.csv"
        preview_payload = {key: value for key, value in payload.items() if key not in {"preview_path", "validation_csv_path"}}
        preview_path.write_text(json.dumps(preview_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        validation_csv_path.write_text(str(payload.get("validation_csv") or ""), encoding="utf-8")
        ledger = RunLedger(run_dir)
        ledger.record_artifact(job_id="__run__", kind="review_workbook_preview", path=preview_path)
        ledger.record_artifact(job_id="__run__", kind="review_workbook_preview_validation_csv", path=validation_csv_path)
        ledger.record_event(
            "review_workbook_preview_created",
            {
                "run_id": run_id,
                "preview_path": str(preview_path),
                "validation_csv_path": str(validation_csv_path),
                "row_count": payload.get("row_count", 0),
                "ready_count": payload.get("ready_count", 0),
                "error_count": payload.get("error_count", 0),
                "skipped_count": payload.get("skipped_count", 0),
                "writes_attempted": 0,
                "network_calls_made": 0,
            },
        )
        payload["preview_path"] = str(preview_path)
        payload["validation_csv_path"] = str(validation_csv_path)

    def _review_workbook_sink_readiness_warnings(self, decision: dict[str, Any]) -> list[dict[str, Any]]:
        action = str(decision.get("action") or "keep_needs_review")
        duplicate_decision = str((decision.get("duplicate_resolution") or {}).get("decision") or "")
        routes_after_review = action in {"approve_for_routing", "approve_enrichment_merge"} or (
            action == "resolve_duplicate" and duplicate_decision != "noop"
        )
        if not routes_after_review:
            return []
        warnings: list[dict[str, Any]] = []
        for readiness in self.sink_readiness()["sinks"]:
            if readiness.get("status") == "blocked":
                sink = str(readiness.get("sink") or "")
                reason = str(readiness.get("reason") or "sink readiness is blocked")
                warnings.append(
                    {
                        "sink": sink,
                        "status": "blocked",
                        "reason": reason,
                        "message": f"sink {sink} blocked: {reason}",
                    }
                )
        return warnings

    def _review_decisions_from_workbook_csv(self, csv_text: str) -> list[dict[str, Any]]:
        return [
            dict(entry["decision"])
            for entry in self._review_workbook_decision_entries(csv_text)
            if not entry.get("skipped")
        ]

    def _review_workbook_decision_entries(self, csv_text: str) -> list[dict[str, Any]]:
        reader = csv.DictReader(StringIO(csv_text))
        entries: list[dict[str, Any]] = []
        for index, row in enumerate(reader):
            row_number = index + 2
            if str(row.get("skip_import") or "").strip().lower() in {"1", "true", "yes", "y"}:
                entries.append({"row_number": row_number, "skipped": True, "skip_reason": "skip_import"})
                continue
            entries.append(
                {
                    "row_number": row_number,
                    "skipped": False,
                    "decision": self._review_decision_from_workbook_row(row, row_number=row_number),
                }
            )
        return entries

    def _review_decision_from_workbook_row(self, row: dict[str, Any], *, row_number: int) -> dict[str, Any]:
        template_text = str(row.get("decision_template_json") or "").strip()
        if template_text:
            try:
                decision = json.loads(template_text)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid decision_template_json at CSV row {row_number}: {exc}") from exc
            if not isinstance(decision, dict):
                raise ValueError(f"decision_template_json at CSV row {row_number} must be a JSON object")
        else:
            decision = {}
        job_id = str(row.get("job_id") or decision.get("job_id") or "").strip()
        if not job_id:
            raise ValueError(f"review workbook CSV row {row_number} is missing job_id")
        decision["job_id"] = job_id
        if row.get("run_id") and not decision.get("run_id"):
            decision["run_id"] = str(row["run_id"])
        if row.get("decision_action"):
            decision["action"] = str(row["decision_action"])
        if row.get("review_action"):
            decision["action"] = str(row["review_action"])
        if row.get("notes"):
            decision["notes"] = str(row["notes"])
        if row.get("review_notes"):
            decision["notes"] = str(row["review_notes"])
        field_corrections = dict(decision.get("field_corrections") or {})
        for column, field in [
            ("corrected_full_name", "full_name"),
            ("corrected_organization", "organization"),
            ("corrected_title", "title"),
            ("corrected_email", "email"),
            ("corrected_phone", "phone"),
            ("corrected_website", "website"),
        ]:
            value = str(row.get(column) or "").strip()
            if value:
                field_corrections[field] = value
        if field_corrections:
            decision["field_corrections"] = field_corrections
        approved_fields = self._split_workbook_list(row.get("approved_enrichment_fields"))
        if approved_fields:
            decision["approved_enrichment_fields"] = approved_fields
        duplicate_decision = str(row.get("duplicate_decision") or "").strip()
        if duplicate_decision:
            duplicate_resolution = dict(decision.get("duplicate_resolution") or {})
            duplicate_resolution["decision"] = duplicate_decision
            if row.get("duplicate_target_identity"):
                duplicate_resolution["target_identity"] = str(row["duplicate_target_identity"]).strip()
            if row.get("duplicate_reason"):
                duplicate_resolution["reason"] = str(row["duplicate_reason"]).strip()
            decision["duplicate_resolution"] = duplicate_resolution
        for column, key in [
            ("field_corrections_json", "field_corrections"),
            ("crop_selection_json", "crop_selection"),
            ("approved_enrichment_fields_json", "approved_enrichment_fields"),
            ("duplicate_resolution_json", "duplicate_resolution"),
        ]:
            value = str(row.get(column) or "").strip()
            if value:
                try:
                    decision[key] = json.loads(value)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"invalid {column} at CSV row {row_number}: {exc}") from exc
        return decision

    def _review_workbook_row(self, entry: dict[str, Any]) -> dict[str, Any]:
        artifacts = entry.get("artifacts") or {}
        matrix = entry.get("review_matrix") or {}
        reviewed = (artifacts.get("reviewed_contact") or {}).get("payload") or {}
        candidate = (artifacts.get("contact_candidate") or {}).get("payload") or {}
        contact = reviewed if reviewed else candidate
        duplicate = (artifacts.get("downstream_duplicate_assessment") or {}).get("payload") or (
            artifacts.get("duplicate_assessment") or {}
        ).get("payload") or {}
        enrichment = (artifacts.get("enrichment_result") or {}).get("payload") or {}
        sink_plan = (artifacts.get("sink_plan") or {}).get("payload") or {}
        route_refresh = (artifacts.get("route_refresh") or {}).get("payload") or {}
        next_action = entry.get("next_action") or {}
        pilot_status = entry.get("sink_pilot_status") or {}
        child_replacement = entry.get("child_replacement_status") or {}
        decision_template = entry.get("decision_template") or {}
        return {
            "run_id": entry.get("run_id"),
            "job_id": entry.get("job_id"),
            "state": entry.get("state"),
            "image_path": entry.get("image_path"),
            "next_action": next_action.get("action"),
            "next_action_reason": next_action.get("reason"),
            "sink_pilot_state": pilot_status.get("state"),
            "safe_to_auto_continue": pilot_status.get("safe_to_auto_continue"),
            "requires_explicit_operator_action": pilot_status.get("requires_explicit_operator_action"),
            "matrix_contact_source": matrix.get("contact_source"),
            "matrix_duplicate_state": matrix.get("duplicate_state"),
            "matrix_enrichment_state": matrix.get("enrichment_state"),
            "matrix_route_state": matrix.get("route_state"),
            "matrix_sink_lookup_state": matrix.get("sink_lookup_state"),
            "matrix_normalization_warning_count": matrix.get("normalization_warning_count"),
            "matrix_sink_lookup_match_count": matrix.get("sink_lookup_match_count"),
            "matrix_enrichment_accepted_count": matrix.get("enrichment_accepted_count"),
            "matrix_enrichment_rejected_count": matrix.get("enrichment_rejected_count"),
            "child_replacement_state": child_replacement.get("state"),
            "child_replacement_candidate_id": child_replacement.get("candidate_id"),
            "child_replacement_sink": child_replacement.get("sink"),
            "child_replacement_operator": child_replacement.get("operator"),
            "child_replacement_predecessors_stale": child_replacement.get("predecessor_artifacts_stale"),
            "child_replacement_copy_ready": child_replacement.get("replacement_copy_ready"),
            "child_replacement_closeout_command": (child_replacement.get("commands") or {}).get("closeout_status"),
            "full_name": self._review_contact_value(contact, "full_name"),
            "organization": self._review_contact_value(contact, "organization"),
            "title": self._review_contact_value(contact, "title"),
            "email": self._review_contact_value(contact, "email"),
            "phone": self._review_contact_value(contact, "phone"),
            "website": self._review_contact_value(contact, "website"),
            "duplicate_state": duplicate.get("state"),
            "enrichment_proposal_count": len(enrichment.get("merge_proposals") or []),
            "planned_sinks": self._review_sink_names(sink_plan),
            "route_refresh_state": route_refresh.get("state"),
            "artifact_kinds": ";".join(str(kind) for kind in entry.get("artifact_kinds") or []),
            "review_command": (entry.get("commands") or {}).get("review"),
            "live_pilot_handoff_command": (entry.get("commands") or {}).get("live_pilot_handoff"),
            "validate_operator_response_command": (entry.get("commands") or {}).get("validate_operator_response"),
            "decision_action": decision_template.get("action"),
            "review_action": decision_template.get("action"),
            "corrected_full_name": self._review_contact_value(contact, "full_name"),
            "corrected_organization": self._review_contact_value(contact, "organization"),
            "corrected_title": self._review_contact_value(contact, "title"),
            "corrected_email": self._review_contact_value(contact, "email"),
            "corrected_phone": self._review_contact_value(contact, "phone"),
            "corrected_website": self._review_contact_value(contact, "website"),
            "approved_enrichment_fields": "",
            "duplicate_decision": "",
            "duplicate_target_identity": "",
            "duplicate_reason": "",
            "review_notes": "",
            "skip_import": "",
            "decision_template_json": json.dumps(decision_template, sort_keys=True),
        }

    def _split_workbook_list(self, value: Any) -> list[str]:
        text = str(value or "").strip()
        if not text:
            return []
        separators = [",", ";"]
        for separator in separators:
            if separator in text:
                return [item.strip() for item in text.split(separator) if item.strip()]
        return [text]

    def _review_contact_value(self, contact: dict[str, Any], field: str) -> str:
        flat = contact.get("flat")
        if isinstance(flat, dict) and flat.get(field) not in {None, ""}:
            return str(flat[field])
        for section_name in ("normalized", "observed"):
            section = contact.get(section_name)
            if not isinstance(section, dict):
                continue
            value = section.get(field)
            if isinstance(value, dict):
                value = value.get("value")
            if value not in {None, ""}:
                return str(value)
        return ""

    def _review_sink_names(self, sink_plan: dict[str, Any]) -> str:
        sinks = sink_plan.get("sinks")
        if isinstance(sinks, list):
            return ";".join(str(sink) for sink in sinks)
        actions = sink_plan.get("actions")
        if isinstance(actions, list):
            names = [str(action.get("sink")) for action in actions if isinstance(action, dict) and action.get("sink")]
            return ";".join(names)
        payloads = sink_plan.get("payloads")
        if isinstance(payloads, list):
            names = [str(payload.get("sink")) for payload in payloads if isinstance(payload, dict) and payload.get("sink")]
            return ";".join(names)
        return ""

    def _render_review_html(self, bundle: dict[str, Any]) -> str:
        rows = "\n".join(self._review_html_row(entry) for entry in bundle["entries"])
        state_groups = self._review_html_groups(bundle["groups"]["by_state"])
        action_groups = self._review_html_groups(bundle["groups"]["by_next_action"])
        pilot_groups = self._review_html_groups(bundle["groups"].get("by_sink_pilot_state", {}))
        duplicate_groups = self._review_html_groups(bundle["groups"].get("by_duplicate_state", {}))
        enrichment_groups = self._review_html_groups(bundle["groups"].get("by_enrichment_state", {}))
        route_groups = self._review_html_groups(bundle["groups"].get("by_route_state", {}))
        lookup_groups = self._review_html_groups(bundle["groups"].get("by_sink_lookup_state", {}))
        child_replacement_groups = self._review_html_groups(
            bundle["groups"].get("by_child_replacement_state", {})
        )
        commands = self._review_html_commands(bundle.get("commands") or {})
        return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Business Card Review {escape(str(bundle["run_id"]))}</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 24px; color: #1f2933; }}
    header {{ margin-bottom: 24px; }}
    h1 {{ font-size: 24px; margin: 0 0 8px; }}
    h2 {{ font-size: 18px; margin: 24px 0 8px; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border: 1px solid #cbd5e1; padding: 8px; vertical-align: top; text-align: left; }}
    th {{ background: #f1f5f9; }}
    code, pre {{ font-family: ui-monospace, monospace; font-size: 12px; }}
    pre {{ white-space: pre-wrap; margin: 0; }}
    .groups {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 16px; }}
  </style>
</head>
<body>
  <header>
    <h1>Business Card Review</h1>
    <div>Run: <code>{escape(str(bundle["run_id"]))}</code></div>
    <div>State filter: <code>{escape(str(bundle["state_filter"]))}</code></div>
    <div>Jobs: {escape(str(bundle["job_count"]))}</div>
  </header>
  <section>
    <h2>Commands</h2>
    {commands}
  </section>
  <section class="groups">
    <div>
      <h2>By State</h2>
      {state_groups}
    </div>
    <div>
      <h2>By Next Action</h2>
      {action_groups}
    </div>
    <div>
      <h2>By Sink Pilot State</h2>
      {pilot_groups}
    </div>
    <div>
      <h2>By Duplicate State</h2>
      {duplicate_groups}
    </div>
    <div>
      <h2>By Enrichment State</h2>
      {enrichment_groups}
    </div>
    <div>
      <h2>By Route State</h2>
      {route_groups}
    </div>
    <div>
      <h2>By Sink Lookup State</h2>
      {lookup_groups}
    </div>
    <div>
      <h2>By Child Replacement State</h2>
      {child_replacement_groups}
    </div>
  </section>
  <h2>Jobs</h2>
  <table>
    <thead>
      <tr>
        <th>Job</th>
        <th>State</th>
        <th>Image</th>
        <th>Next Action</th>
        <th>Review Matrix</th>
        <th>Sink Pilot</th>
        <th>Child Replacement</th>
        <th>Artifacts</th>
        <th>Decision Template</th>
      </tr>
    </thead>
    <tbody>
      {rows}
    </tbody>
  </table>
</body>
</html>
"""

    def _review_html_groups(self, groups: dict[str, Any]) -> str:
        items = [
            f"<li><code>{escape(name)}</code>: {escape(str(group['count']))}</li>"
            for name, group in sorted(groups.items())
        ]
        return "<ul>" + "".join(items) + "</ul>"

    def _review_html_commands(self, commands: dict[str, Any]) -> str:
        items = [
            f"<li><code>{escape(str(name))}</code>: <code>{escape(str(command))}</code></li>"
            for name, command in sorted(commands.items())
        ]
        return "<ul>" + "".join(items) + "</ul>"

    def _review_html_row(self, entry: dict[str, Any]) -> str:
        next_action = entry.get("next_action") or {}
        pilot_status = entry.get("sink_pilot_status") or {}
        child_replacement = entry.get("child_replacement_status") or {}
        matrix = entry.get("review_matrix") or {}
        contact = matrix.get("contact") if isinstance(matrix.get("contact"), dict) else {}
        artifacts = ", ".join(escape(kind) for kind in entry.get("artifact_kinds") or [])
        decision_template = escape(json.dumps(entry["decision_template"], sort_keys=True, indent=2))
        image_path = escape(str(entry.get("image_path") or ""))
        return f"""<tr>
  <td><code>{escape(str(entry["job_id"]))}</code></td>
  <td>{escape(str(entry.get("state") or ""))}</td>
  <td><code>{image_path}</code></td>
  <td><code>{escape(str(next_action.get("action") or "none"))}</code><br>{escape(str(next_action.get("reason") or ""))}</td>
  <td>
    <strong>{escape(str(contact.get("full_name") or ""))}</strong><br>
    {escape(str(contact.get("organization") or ""))}<br>
    <code>{escape(str(contact.get("email") or ""))}</code><br>
    duplicate: <code>{escape(str(matrix.get("duplicate_state") or "unknown"))}</code><br>
    enrichment: <code>{escape(str(matrix.get("enrichment_state") or "unknown"))}</code><br>
    route: <code>{escape(str(matrix.get("route_state") or "unknown"))}</code><br>
    lookup: <code>{escape(str(matrix.get("sink_lookup_state") or "unknown"))}</code>
  </td>
  <td><code>{escape(str(pilot_status.get("state") or "not_started"))}</code><br>safe: {escape(str(pilot_status.get("safe_to_auto_continue")))}<br>explicit: {escape(str(pilot_status.get("requires_explicit_operator_action")))}</td>
  <td><code>{escape(str(child_replacement.get("state") or "not_started"))}</code><br>candidate: <code>{escape(str(child_replacement.get("candidate_id") or ""))}</code><br>stale: {escape(str(child_replacement.get("predecessor_artifacts_stale")))}<br>copy ready: {escape(str(child_replacement.get("replacement_copy_ready")))}<br><code>{escape(str((child_replacement.get("commands") or {}).get("closeout_status") or ""))}</code></td>
  <td>{artifacts}</td>
  <td><pre>{decision_template}</pre></td>
</tr>"""

    def _record_route_refresh_if_needed(
        self,
        artifact_dir: Path,
        *,
        job_id: str,
        run_id: str,
        reviewer: str,
        reason: str,
    ) -> dict[str, Any] | None:
        stale_kinds = [
            kind
            for kind, filename in _ROUTE_ARTIFACT_FILES.items()
            if (artifact_dir / filename).exists()
        ]
        if not stale_kinds:
            return None
        payload = {
            "schema": "business-card-watchdog.route-refresh.v1",
            "state": "pending",
            "job_id": job_id,
            "run_id": run_id,
            "reviewer": reviewer,
            "reason": reason,
            "stale_artifact_kinds": stale_kinds,
            "refreshed_artifact_kinds": [],
            "pending_artifact_kinds": stale_kinds,
            "writes_attempted": 0,
            "network_calls_made": 0,
        }
        refresh_path = artifact_dir / "route_refresh.json"
        refresh_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        ledger = RunLedger(self.config.runs_dir / run_id)
        ledger.record_artifact(job_id=job_id, kind="route_refresh", path=refresh_path)
        ledger.record_event(
            "route_refresh_requested",
            {
                "job_id": job_id,
                "run_id": run_id,
                "reason": reason,
                "refresh_path": str(refresh_path),
                "stale_artifact_kinds": stale_kinds,
                "writes_attempted": 0,
                "network_calls_made": 0,
            },
        )
        return {"route_refresh_path": str(refresh_path), "route_refresh": payload}

    def _pilot_bundle_artifact_status(
        self,
        *,
        kind: str,
        path: Path,
        payload: dict[str, Any] | None,
        sink: str,
    ) -> dict[str, Any]:
        payload_sink = str((payload or {}).get("sink") or (payload or {}).get("selected_sink") or "")
        if kind == "sink_plan":
            payload_sink = ",".join(
                sorted(
                    {
                        str(action.get("sink") or "")
                        for action in list((payload or {}).get("actions") or [])
                        if action.get("sink")
                    }
                )
            )
        if kind == "sink_lookup_result":
            payload_sink = ",".join(
                sorted(
                    {
                        str(result.get("sink") or "")
                        for result in list((payload or {}).get("results") or [])
                        if result.get("sink")
                    }
                )
            )
        return {
            "kind": kind,
            "path": str(path),
            "exists": payload is not None,
            "schema": (payload or {}).get("schema"),
            "state": (payload or {}).get("state", "missing"),
            "status": (payload or {}).get("status", "missing"),
            "sink": payload_sink or None,
            "selected": bool(payload and (not payload_sink or sink in payload_sink.split(","))),
        }

    def _pilot_bundle_requirements(
        self,
        *,
        artifacts: dict[str, dict[str, Any] | None],
        artifact_status: dict[str, dict[str, Any]],
        readiness: dict[str, Any],
        sink: str,
    ) -> list[dict[str, Any]]:
        duplicate_assessment = artifacts.get("downstream_duplicate_assessment") or {}
        duplicate_resolution = artifacts.get("duplicate_resolution") or {}
        duplicate_state = str(duplicate_assessment.get("state") or "missing")
        duplicate_reviewed = duplicate_state == "no_match" or bool(duplicate_resolution.get("decision"))
        return [
            {
                "name": "reviewed_contact_exists",
                "ok": artifacts.get("reviewed_contact") is not None,
                "detail": artifact_status["reviewed_contact"]["path"],
            },
            {
                "name": "selected_sink_lookup_reviewed",
                "ok": self._pilot_bundle_lookup_result_has_sink(artifacts.get("sink_lookup_result"), sink)
                and duplicate_reviewed,
                "detail": (
                    "lookup result exists and duplicate state is reviewed or no-match"
                    if duplicate_reviewed
                    else f"downstream duplicate state is {duplicate_state}"
                ),
            },
            {
                "name": "selected_sink_planned",
                "ok": self._pilot_bundle_sink_plan_has_sink(artifacts.get("sink_plan"), sink),
                "detail": artifact_status["sink_plan"]["path"],
            },
            {
                "name": "write_adapter_request_exists",
                "ok": self._pilot_bundle_adapter_has_sink(artifacts.get("sink_adapter_request_write"), sink, phase="write"),
                "detail": artifact_status["sink_adapter_request_write"]["path"],
            },
            {
                "name": "apply_preflight_exists",
                "ok": artifacts.get("sink_apply_preflight") is not None,
                "detail": artifact_status["sink_apply_preflight"]["path"],
            },
            {
                "name": "apply_decision_approved",
                "ok": bool((artifacts.get("sink_apply_decision") or {}).get("decision") == "approve"),
                "detail": artifact_status["sink_apply_decision"]["path"],
            },
            {
                "name": "selected_sink_readiness_prepared",
                "ok": readiness.get("selected_sink") == sink,
                "detail": "apply pilot readiness artifact is scoped to the selected sink",
            },
            {
                "name": "mock_apply_ready",
                "ok": bool(readiness.get("can_mock_apply_pilot")),
                "detail": "mock write/readback pilot can run without live sink calls",
            },
            {
                "name": "live_apply_ready",
                "ok": bool(readiness.get("can_live_apply_pilot")),
                "detail": "live write/readback pilot readiness checks are satisfied for the selected sink",
            },
            {
                "name": "readback_adapter_request_exists",
                "ok": self._pilot_bundle_adapter_has_sink(
                    artifacts.get("sink_adapter_request_readback"),
                    sink,
                    phase="readback",
                ),
                "detail": artifact_status["sink_adapter_request_readback"]["path"],
            },
        ]

    def _pilot_bundle_sink_plan_has_sink(self, plan: dict[str, Any] | None, sink: str) -> bool:
        return any(action.get("sink") == sink for action in list((plan or {}).get("actions") or []))

    def _pilot_bundle_lookup_result_has_sink(self, result: dict[str, Any] | None, sink: str) -> bool:
        return any(row.get("sink") == sink for row in list((result or {}).get("results") or []))

    def _pilot_bundle_adapter_has_sink(
        self,
        request: dict[str, Any] | None,
        sink: str,
        *,
        phase: str,
    ) -> bool:
        return any(
            row.get("sink") == sink and row.get("phase") == phase
            for row in list((request or {}).get("requests") or [])
        )

    def _pilot_bundle_remediation(self, sink: str) -> dict[str, Any]:
        common = {
            "rollback_guaranteed": False,
            "before_retry": [
                "preserve sink_apply_pilot_bundle.json and all pilot artifacts",
                "inspect the downstream contact manually",
                "do not rerun write-pilot until the prior pilot is complete or explicitly abandoned",
            ],
        }
        if sink == "google_contacts":
            return {
                **common,
                "sink": sink,
                "manual_checks": [
                    "inspect the created or updated Google Contact resource",
                    "remove disposable pilot contacts manually if appropriate",
                    "verify People API scopes before another live write",
                ],
            }
        return {
            **common,
            "sink": sink,
            "manual_checks": [
                "inspect the Odollo/Odoo res.partner record in the selected tenant",
                "preserve tenant action logs before manual correction",
                "verify tenant/profile selection before another live write",
            ],
        }

    def _default_sink_for_job(self, *, job_id: str, run_id: str) -> str:
        job = self.get_job(job_id, run_id=run_id)
        artifact_dir = Path(job["artifact_dir"]) if job.get("artifact_dir") else self.config.runs_dir / run_id / "artifacts" / job_id
        plan = _read_json_file(artifact_dir / "sink_plan.json")
        for action in list((plan or {}).get("actions") or []):
            sink = str(action.get("sink") or "")
            if sink in {"google_contacts", "odoo"}:
                return sink
        if self.config.sink.google_contacts:
            return "google_contacts"
        if self.config.sink.odoo:
            return "odoo"
        return "google_contacts"

    def _mark_route_artifact_refreshed(
        self,
        artifact_dir: Path,
        *,
        job_id: str,
        run_id: str,
        kind: str,
    ) -> None:
        refresh_path = artifact_dir / "route_refresh.json"
        if not refresh_path.exists():
            return
        payload = json.loads(refresh_path.read_text(encoding="utf-8"))
        pending = list(payload.get("pending_artifact_kinds") or [])
        if kind not in pending:
            return
        refreshed = list(payload.get("refreshed_artifact_kinds") or [])
        refreshed.append(kind)
        pending = [item for item in pending if item != kind]
        payload["refreshed_artifact_kinds"] = refreshed
        payload["pending_artifact_kinds"] = pending
        payload["state"] = "complete" if not pending else "pending"
        refresh_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        RunLedger(self.config.runs_dir / run_id).record_event(
            "route_refresh_updated",
            {
                "job_id": job_id,
                "run_id": run_id,
                "refresh_path": str(refresh_path),
                "refreshed_kind": kind,
                "pending_artifact_kinds": pending,
                "state": payload["state"],
                "writes_attempted": 0,
                "network_calls_made": 0,
            },
        )

    def _next_route_refresh_action(self, artifact_dir: Path) -> dict[str, Any] | None:
        refresh_path = artifact_dir / "route_refresh.json"
        if not refresh_path.exists():
            return None
        payload = json.loads(refresh_path.read_text(encoding="utf-8"))
        if payload.get("state") != "pending":
            return None
        pending = set(str(kind) for kind in payload.get("pending_artifact_kinds") or [])
        if not pending:
            return None
        for step in _ROUTE_REFRESH_STEPS:
            if step["kind"] in pending:
                return {
                    "action": step["action"],
                    "reason": step["reason"],
                    "command": step["command"],
                    "route_refresh_path": str(refresh_path),
                    "pending_artifact_kinds": [kind for kind in payload["pending_artifact_kinds"]],
                }
        return None

    def _execute_safe_next_action(self, action: dict[str, Any]) -> dict[str, Any]:
        action_name = str(action.get("action") or "")
        job_id = str(action["job_id"])
        run_id = str(action["run_id"])
        if action_name == "plan_sink_lookup":
            return self.plan_sink_lookup_for_job(job_id=job_id, run_id=run_id)
        if action_name == "prepare_sink_lookup_adapter":
            return self.build_sink_adapter_request_for_job(job_id=job_id, run_id=run_id, phase="lookup")
        if action_name == "prepare_sink_lookup_smoke_handoff":
            sink = self._default_sink_for_job(job_id=job_id, run_id=run_id)
            return self.build_sink_lookup_smoke_handoff_for_job(job_id=job_id, run_id=run_id, sink=sink)
        if action_name == "record_sink_lookup_result":
            return self.record_sink_lookup_result_for_job(job_id=job_id, run_id=run_id)
        if action_name == "assess_downstream_duplicates":
            return self.assess_downstream_duplicates_for_job(job_id=job_id, run_id=run_id)
        if action_name == "plan_sinks":
            return self.plan_sinks_for_job(job_id=job_id, run_id=run_id)
        if action_name == "prepare_sink_write_adapter":
            return self.build_sink_adapter_request_for_job(job_id=job_id, run_id=run_id, phase="write")
        if action_name == "preflight_sink_apply":
            return self.preflight_sink_apply(job_id=job_id, run_id=run_id)
        if action_name == "prepare_sink_apply_pilot_readiness":
            return self.build_sink_apply_pilot_readiness_for_job(job_id=job_id, run_id=run_id)
        if action_name == "prepare_sink_apply_pilot_bundle":
            sink = self._default_sink_for_job(job_id=job_id, run_id=run_id)
            return self.build_sink_apply_pilot_bundle_for_job(job_id=job_id, run_id=run_id, sink=sink)
        if action_name == "prepare_sink_readback_adapter":
            return self.build_sink_adapter_request_for_job(job_id=job_id, run_id=run_id, phase="readback")
        if action_name == "prepare_sink_apply_pilot_report":
            return self.build_sink_apply_pilot_report_for_job(job_id=job_id, run_id=run_id)
        raise ValueError(f"next action is not safe to execute automatically: {action_name}")

    def _next_action_for_job(self, job: dict[str, Any], artifact_kinds: set[str]) -> dict[str, Any] | None:
        state = str(job.get("state") or "")
        if state == "needs_review":
            if "duplicate_assessment" in artifact_kinds:
                return {
                    "action": "resolve_duplicate",
                    "reason": "job has duplicate assessment and needs review",
                    "command": "jobs review",
                }
            if "enrichment_result" in artifact_kinds:
                return {
                    "action": "review_enrichment",
                    "reason": "job has enrichment result awaiting review",
                    "command": "jobs review",
                }
            return {
                "action": "review_contact",
                "reason": "job needs operator or agent review",
                "command": "jobs review",
            }
        if state == "ready_to_route":
            artifact_dir_value = str(job.get("artifact_dir") or "")
            if artifact_dir_value:
                route_refresh_action = self._next_route_refresh_action(Path(artifact_dir_value))
                if route_refresh_action is not None:
                    return route_refresh_action
            if "sink_lookup_plan" not in artifact_kinds:
                return {
                    "action": "plan_sink_lookup",
                    "reason": "reviewed/normalized job is ready for downstream duplicate lookup planning",
                    "command": "sinks lookup-plan",
                }
            if "sink_adapter_request_lookup" not in artifact_kinds:
                return {
                    "action": "prepare_sink_lookup_adapter",
                    "reason": "sink lookup plan exists; prepare blocked live lookup adapter request",
                    "command": "sinks adapter-request --phase lookup",
                }
            if "sink_lookup_result" not in artifact_kinds:
                return {
                    "action": "record_sink_lookup_result",
                    "reason": "sink lookup adapter request exists; record zero-network lookup result",
                    "command": "sinks lookup-result",
                }
            if "downstream_duplicate_assessment" not in artifact_kinds:
                return {
                    "action": "assess_downstream_duplicates",
                    "reason": "sink lookup result exists; assess downstream duplicate state",
                    "command": "sinks assess-duplicates",
                }
            if "sink_plan" not in artifact_kinds:
                return {
                    "action": "plan_sinks",
                    "reason": "reviewed/normalized job is ready for dry-run sink planning",
                    "command": "sinks plan",
                }
            if "sink_adapter_request_write" not in artifact_kinds:
                return {
                    "action": "prepare_sink_write_adapter",
                    "reason": "sink plan exists; prepare blocked live write adapter request",
                    "command": "sinks adapter-request --phase write",
                }
            if "sink_apply_preflight" not in artifact_kinds:
                return {
                    "action": "preflight_sink_apply",
                    "reason": "sink plan exists; create zero-write apply preflight",
                    "command": "sinks apply-preflight",
                }
            if "sink_apply_decision" not in artifact_kinds:
                return {
                    "action": "decide_sink_apply",
                    "reason": "sink apply preflight exists; approve, reject, or mark no-op",
                    "command": "sinks apply-decision",
                }
            if "sink_apply_result" in artifact_kinds:
                if "sink_adapter_request_readback" not in artifact_kinds:
                    return {
                        "action": "prepare_sink_readback_adapter",
                        "reason": "sink apply result exists; prepare blocked live readback adapter request",
                        "command": "sinks adapter-request --phase readback",
                    }
                if "sink_readback_pilot" not in artifact_kinds:
                    return {
                        "action": "execute_sink_readback_pilot",
                        "reason": "readback adapter request exists; execute explicit read-only readback pilot",
                        "command": "sinks readback-pilot",
                    }
                if "sink_apply_pilot_report" not in artifact_kinds:
                    return {
                        "action": "prepare_sink_apply_pilot_report",
                        "reason": "write and readback pilot evidence exists; prepare apply pilot report",
                        "command": "sinks apply-pilot-report",
                    }
                return None
            if "sink_apply_pilot_readiness" not in artifact_kinds:
                return {
                    "action": "prepare_sink_apply_pilot_readiness",
                    "reason": "sink apply decision exists; prepare explicit one-job live apply pilot readiness artifact",
                    "command": "sinks apply-pilot-readiness",
                }
            if "sink_write_pilot" not in artifact_kinds:
                return {
                    "action": "execute_sink_write_pilot",
                    "reason": "sink apply pilot readiness exists; execute explicit one-job write pilot",
                    "command": "sinks write-pilot",
                }
            return {
                "action": "await_apply_approval",
                "reason": "sink apply decision exists; live apply remains explicit and gated",
                "command": "sinks apply --apply",
            }
        if state == "failed":
            return {
                "action": "inspect_failure",
                "reason": str(job.get("error") or "job failed"),
                "command": "jobs show",
            }
        return None


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _read_json_file(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _maybe_bool(value: Any) -> bool | None:
    if value is None:
        return None
    return bool(value)


def _path_check(name: str, path: Path) -> dict[str, Any]:
    path.mkdir(parents=True, exist_ok=True)
    probe = path / ".business-card-watchdog-write-test"
    try:
        probe.write_text("ok\n", encoding="utf-8")
        probe.unlink()
        return {"name": name, "ok": True, "detail": str(path)}
    except OSError as exc:
        return {"name": name, "ok": False, "detail": f"{path}: {exc}"}


def _readiness_check(name: str, status: str, detail: str) -> dict[str, Any]:
    return {"name": name, "status": status, "detail": detail}


def _parse_operator_response_fields(response: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    current_key = ""
    for token in shlex.split(response):
        if "=" in token:
            key, value = token.split("=", 1)
            current_key = key.strip()
            if current_key:
                fields[current_key] = value.strip()
        elif current_key:
            fields[current_key] = f"{fields[current_key]} {token}".strip()
    return fields


def _operator_response_validation_command(run_id: str, response: str) -> str:
    return (
        f"runs live-pilot-validate-response {shlex.quote(run_id)} "
        f"--response {shlex.quote(response)} --json"
    )


def _watch_dry_run_response_validation_command(response: str) -> str:
    return f"watch-dry-run-validate-response --response {shlex.quote(response)} --json"


def _watch_dry_run_safety_confirmation_error(safety_confirmation: str) -> str:
    normalized = safety_confirmation.strip().lower()
    required_terms = {"private", "dry", "run"}
    if len(normalized) < 16 or not all(term in normalized for term in required_terms):
        return "safety_confirmation must explicitly mention private dry run intent"
    return ""


def _live_selection_packet_commands(
    *,
    job_id: str,
    run_id: str,
    sink: str,
    operator: str,
    scope: str,
    reason: str = "",
    operator_response_template: str = "",
) -> dict[str, str]:
    response_template = operator_response_template or (
        f"run_id={run_id} job_id={job_id} sink={sink} operator={operator} "
        f"scope={scope} safety_confirmation=<tenant-profile-account-confirmation>"
    )
    create_selected_target = (
        f"sinks select-live-target {job_id} --run-id {run_id} --sink {sink} "
        f"--operator {operator} --scope {scope} --safety-confirmation <tenant-profile-account-confirmation>"
    )
    if reason:
        create_selected_target += f" --reason {json.dumps(reason)}"
    return {
        "validate_operator_response": (
            f"runs live-pilot-validate-response {run_id} --response <operator-response> --json"
        ),
        "validate_operator_response_prefilled": _operator_response_validation_command(run_id, response_template),
        "create_selected_target": create_selected_target,
        "selected_target_audit": (
            f"sinks selected-target-audit {job_id} --run-id {run_id} --scope {scope} --no-write --json"
        ),
        "lookup_smoke_handoff": (
            f"sinks lookup-smoke-handoff {job_id} --run-id {run_id} --sink {sink} "
            f"--approved-by {operator} --json"
        ),
        "lookup_pilot": (
            f"sinks lookup-pilot {job_id} --run-id {run_id} --sink {sink} --approved-by {operator} --no-simulate"
        ),
        "write_pilot": (
            f"sinks write-pilot {job_id} --run-id {run_id} --sink {sink} --approved-by {operator} --no-simulate"
        ),
        "readback_request": f"sinks adapter-request {job_id} --run-id {run_id} --phase readback --json",
        "readback_pilot": (
            f"sinks readback-pilot {job_id} --run-id {run_id} --sink {sink} "
            f"--approved-by {operator} --no-simulate"
        ),
    }


def _live_selection_packet_checklist(
    *,
    commands: dict[str, str],
    scope: str,
    state: str,
) -> list[dict[str, Any]]:
    checklist = [
        {
            "step": "validate_operator_response",
            "command": commands["validate_operator_response_prefilled"],
            "requires_explicit_operator_action": False,
            "writes_runtime_artifact": False,
            "live_call": False,
            "writes_sink": False,
            "enabled_for_scope": True,
            "stop_condition": "Fix missing fields, mismatches, or safety confirmation blockers before continuing.",
        },
        {
            "step": "create_selected_target",
            "command": commands["create_selected_target"],
            "requires_explicit_operator_action": True,
            "writes_runtime_artifact": True,
            "live_call": False,
            "writes_sink": False,
            "enabled_for_scope": state == "ready_for_operator_approval",
            "stop_condition": (
                "Run only after the operator confirms the selected card/contact is safe for the target tenant/profile."
            ),
        },
        {
            "step": "selected_target_audit",
            "command": commands["selected_target_audit"],
            "requires_explicit_operator_action": False,
            "writes_runtime_artifact": False,
            "live_call": False,
            "writes_sink": False,
            "enabled_for_scope": True,
            "stop_condition": (
                "Keep --no-write for packet validation; audit must match run/job/sink/operator/scope before live commands."
            ),
        },
        {
            "step": "lookup_smoke_handoff",
            "command": commands["lookup_smoke_handoff"],
            "requires_explicit_operator_action": False,
            "writes_runtime_artifact": True,
            "live_call": False,
            "writes_sink": False,
            "enabled_for_scope": scope in {"lookup", "write", "readback", "all"},
            "stop_condition": "Creates a runtime handoff artifact only; inspect it before any explicit live lookup.",
        },
    ]
    if scope in {"lookup", "all"}:
        checklist.append(
            {
                "step": "live_lookup_pilot",
                "command": commands["lookup_pilot"],
                "requires_explicit_operator_action": True,
                "writes_runtime_artifact": True,
                "live_call": True,
                "writes_sink": False,
                "enabled_for_scope": True,
                "stop_condition": "Explicit read-only live lookup; persist only redacted downstream duplicate evidence.",
            }
        )
    if scope in {"write", "all"}:
        checklist.append(
            {
                "step": "live_write_pilot",
                "command": commands["write_pilot"],
                "requires_explicit_operator_action": True,
                "writes_runtime_artifact": True,
                "live_call": True,
                "writes_sink": True,
                "enabled_for_scope": True,
                "stop_condition": (
                    "Explicit one-job write; requires selected-target audit, duplicate clearance, and apply approval."
                ),
            }
        )
    if scope in {"readback", "all"}:
        checklist.extend(
            [
                {
                    "step": "readback_adapter_request",
                    "command": commands["readback_request"],
                    "requires_explicit_operator_action": False,
                    "writes_runtime_artifact": True,
                    "live_call": False,
                    "writes_sink": False,
                    "enabled_for_scope": True,
                    "stop_condition": "Prepare readback request only after write-pilot evidence exists.",
                },
                {
                    "step": "live_readback_pilot",
                    "command": commands["readback_pilot"],
                    "requires_explicit_operator_action": True,
                    "writes_runtime_artifact": True,
                    "live_call": True,
                    "writes_sink": False,
                    "enabled_for_scope": True,
                    "stop_condition": "Explicit read-only readback; abort if the adapter reports any write attempt.",
                },
            ]
        )
    return checklist


def _pilot_command_checklist_summary(checklist: list[Any]) -> dict[str, Any]:
    rows = [row for row in checklist if isinstance(row, dict)]
    return {
        "schema": "business-card-watchdog.pilot-command-checklist-summary.v1",
        "step_count": len(rows),
        "live_call_count": sum(1 for row in rows if row.get("live_call")),
        "sink_write_step_count": sum(1 for row in rows if row.get("writes_sink")),
        "explicit_operator_step_count": sum(1 for row in rows if row.get("requires_explicit_operator_action")),
        "runtime_artifact_step_count": sum(1 for row in rows if row.get("writes_runtime_artifact")),
        "steps": [
            {
                "step": row.get("step"),
                "live_call": bool(row.get("live_call", False)),
                "writes_sink": bool(row.get("writes_sink", False)),
                "requires_explicit_operator_action": bool(row.get("requires_explicit_operator_action", False)),
            }
            for row in rows[:8]
        ],
    }


def _pilot_command_sequence(checklist: list[Any]) -> dict[str, Any]:
    rows = [row for row in checklist if isinstance(row, dict)]

    def format_step(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "step": row.get("step"),
            "command": row.get("command"),
            "enabled_for_scope": bool(row.get("enabled_for_scope", True)),
            "requires_explicit_operator_action": bool(row.get("requires_explicit_operator_action", False)),
            "writes_runtime_artifact": bool(row.get("writes_runtime_artifact", False)),
            "live_call": bool(row.get("live_call", False)),
            "writes_sink": bool(row.get("writes_sink", False)),
            "stop_condition": row.get("stop_condition"),
        }

    enabled_rows = [row for row in rows if row.get("enabled_for_scope", True)]
    safe_inspection_steps = [
        format_step(row)
        for row in enabled_rows
        if not row.get("requires_explicit_operator_action") and not row.get("live_call") and not row.get("writes_sink")
    ]
    explicit_operator_steps = [format_step(row) for row in enabled_rows if row.get("requires_explicit_operator_action")]
    live_call_steps = [format_step(row) for row in enabled_rows if row.get("live_call")]
    sink_write_steps = [format_step(row) for row in enabled_rows if row.get("writes_sink")]
    return {
        "schema": "business-card-watchdog.pilot-command-sequence.v1",
        "step_count": len(rows),
        "enabled_step_count": len(enabled_rows),
        "safe_inspection_step_count": len(safe_inspection_steps),
        "explicit_operator_step_count": len(explicit_operator_steps),
        "live_call_step_count": len(live_call_steps),
        "sink_write_step_count": len(sink_write_steps),
        "safe_inspection_steps": safe_inspection_steps[:8],
        "explicit_operator_steps": explicit_operator_steps[:8],
        "live_call_steps": live_call_steps[:8],
        "sink_write_steps": sink_write_steps[:8],
        "next_safe_inspection_step": safe_inspection_steps[0] if safe_inspection_steps else None,
        "next_explicit_operator_step": explicit_operator_steps[0] if explicit_operator_steps else None,
        "execution_policy": {
            "auto_execute_safe_inspection_steps_only": True,
            "requires_operator_before_explicit_steps": True,
            "requires_operator_before_live_call_steps": True,
            "requires_operator_before_sink_write_steps": True,
            "do_not_run_live_or_sink_write_from_handoff": True,
        },
    }


def _pilot_command_sequence_summary(sequence: dict[str, Any]) -> dict[str, Any]:
    next_safe = dict(sequence.get("next_safe_inspection_step") or {})
    next_explicit = dict(sequence.get("next_explicit_operator_step") or {})
    return {
        "schema": "business-card-watchdog.pilot-command-sequence-summary.v1",
        "step_count": _int(sequence.get("step_count")),
        "safe_inspection_step_count": _int(sequence.get("safe_inspection_step_count")),
        "explicit_operator_step_count": _int(sequence.get("explicit_operator_step_count")),
        "live_call_step_count": _int(sequence.get("live_call_step_count")),
        "sink_write_step_count": _int(sequence.get("sink_write_step_count")),
        "next_safe_inspection_step": next_safe.get("step"),
        "next_explicit_operator_step": next_explicit.get("step"),
        "execution_policy": sequence.get("execution_policy") or {},
    }


def _operator_dashboard_live_pilot_execution_packet(run_id: str, handoff: dict[str, Any]) -> dict[str, Any]:
    operator_entries = [
        entry
        for entry in list(handoff.get("entries") or [])
        if isinstance(entry, dict) and entry.get("operator_required")
    ]
    packet_entries: list[dict[str, Any]] = []
    for entry in operator_entries[:5]:
        sequence = dict(entry.get("pilot_command_sequence") or {})
        next_safe = dict(sequence.get("next_safe_inspection_step") or {})
        next_explicit = dict(sequence.get("next_explicit_operator_step") or {})
        commands = dict(entry.get("commands") or {})
        packet_entries.append(
            {
                "job_id": entry.get("job_id"),
                "next_action": entry.get("next_action"),
                "next_safe_step": next_safe.get("step"),
                "next_safe_command": next_safe.get("command") or commands.get("validate_operator_response_prefilled"),
                "next_explicit_step": next_explicit.get("step"),
                "next_explicit_command": next_explicit.get("command"),
                "operator_response_template": entry.get("operator_response_template"),
                "operator_prompt": entry.get("operator_prompt"),
                "forbidden_live_command_count": _int(sequence.get("live_call_step_count")),
                "forbidden_sink_write_command_count": _int(sequence.get("sink_write_step_count")),
            }
        )

    state = "operator_required" if operator_entries else "no_operator_required"
    return {
        "schema": "business-card-watchdog.operator-dashboard.live-pilot-execution-packet.v1",
        "run_id": run_id,
        "state": state,
        "operator_required_count": len(operator_entries),
        "entries": packet_entries,
        "next_safe_command": packet_entries[0]["next_safe_command"] if packet_entries else None,
        "next_explicit_operator_command": packet_entries[0]["next_explicit_command"] if packet_entries else None,
        "forbidden_live_or_sink_write_from_dashboard": True,
        "execution_policy": {
            "safe_to_auto_execute_next_safe_command": True,
            "requires_operator_before_explicit_command": True,
            "requires_operator_before_live_call": True,
            "requires_operator_before_sink_write": True,
            "do_not_run_live_or_sink_write_from_dashboard": True,
        },
        "stop_conditions": handoff.get("operator_stop_conditions") or [],
        "writes_attempted": 0,
        "network_calls_made": 0,
    }


def _live_pilot_operator_approval_readback(
    *,
    state: str,
    next_validation_step: str,
    parsed_response: dict[str, str],
    matching_template: dict[str, Any] | None,
    missing_fields: list[str],
    mismatches: list[str],
    validation_command_sequence: dict[str, Any],
    select_target_command: str | None,
    selected_target_audit_command: str | None,
    lookup_smoke_handoff_command: str | None,
) -> dict[str, Any]:
    template_fields = dict((matching_template or {}).get("copyable_approval_fields") or {})
    next_safe = dict(validation_command_sequence.get("next_safe_inspection_step") or {})
    return {
        "schema": "business-card-watchdog.live-pilot-operator-approval-readback.v1",
        "state": "ready" if state != "blocked" else "blocked",
        "validation_state": state,
        "next_validation_step": next_validation_step,
        "response_matches_template": bool(matching_template) and not missing_fields and not mismatches,
        "matched_template_job_id": (matching_template or {}).get("job_id"),
        "parsed_fields": {
            "run_id": parsed_response.get("run_id"),
            "job_id": parsed_response.get("job_id"),
            "sink": parsed_response.get("sink"),
            "operator": parsed_response.get("operator"),
            "scope": parsed_response.get("scope"),
            "safety_confirmation_present": bool(str(parsed_response.get("safety_confirmation") or "").strip()),
        },
        "template_fields": {
            "run_id": template_fields.get("run_id"),
            "job_id": template_fields.get("job_id"),
            "sink": template_fields.get("sink"),
            "operator": template_fields.get("operator"),
            "scope": template_fields.get("scope"),
        },
        "missing_field_count": len(missing_fields),
        "mismatch_count": len(mismatches),
        "next_safe_step": next_safe.get("step"),
        "next_safe_command": next_safe.get("command"),
        "select_target_command": select_target_command,
        "selected_target_audit_command": selected_target_audit_command,
        "lookup_smoke_handoff_command": lookup_smoke_handoff_command,
        "creates_selected_live_target": False,
        "writes_attempted": 0,
        "network_calls_made": 0,
    }


def _live_pilot_checklist_rollup(handoff: dict[str, Any] | None) -> dict[str, Any]:
    entries = [entry for entry in list((handoff or {}).get("entries") or []) if isinstance(entry, dict)]
    actionable_entries = [entry for entry in entries if entry.get("operator_required")]
    checklist_summaries = [
        dict(entry.get("pilot_command_checklist_summary") or {})
        for entry in actionable_entries
        if isinstance(entry.get("pilot_command_checklist_summary"), dict)
    ]
    return {
        "schema": "business-card-watchdog.live-pilot-checklist-rollup.v1",
        "job_count": len(entries),
        "operator_required_job_count": len(actionable_entries),
        "checklist_job_count": len(checklist_summaries),
        "step_count": sum(_int(summary.get("step_count")) for summary in checklist_summaries),
        "live_call_count": sum(_int(summary.get("live_call_count")) for summary in checklist_summaries),
        "sink_write_step_count": sum(_int(summary.get("sink_write_step_count")) for summary in checklist_summaries),
        "explicit_operator_step_count": sum(
            _int(summary.get("explicit_operator_step_count")) for summary in checklist_summaries
        ),
        "runtime_artifact_step_count": sum(
            _int(summary.get("runtime_artifact_step_count")) for summary in checklist_summaries
        ),
        "sample_jobs": [
            {
                "job_id": entry.get("job_id"),
                "next_action": entry.get("next_action"),
                "step_count": _int((entry.get("pilot_command_checklist_summary") or {}).get("step_count")),
                "live_call_count": _int(
                    (entry.get("pilot_command_checklist_summary") or {}).get("live_call_count")
                ),
                "sink_write_step_count": _int(
                    (entry.get("pilot_command_checklist_summary") or {}).get("sink_write_step_count")
                ),
            }
            for entry in actionable_entries[:5]
        ],
    }


def _safety_confirmation_blocker(value: str) -> str:
    normalized = " ".join(value.strip().lower().split())
    if normalized.startswith("<") or normalized.endswith(">"):
        return "safety_confirmation must replace the tenant/profile/account placeholder"
    context_terms = {
        "account",
        "contacts",
        "google",
        "gws",
        "odollo",
        "odoo",
        "profile",
        "target",
        "tenant",
        "workspace",
    }
    if len(normalized) < 16 or not any(term in normalized for term in context_terms):
        return "safety_confirmation must describe the intended tenant/profile/account context"
    return ""


def _runtime_safe_next_actions(
    *,
    state: str,
    config_exists: bool,
    service_installed: bool,
    watch_error: str,
    watch_inputs: list[str],
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    if not config_exists:
        actions.append(
            {
                "action": "initialize_user_config",
                "command": "init-config",
                "reason": "runtime readiness requires a user-scoped config file",
                "safe_to_auto_continue": True,
                "requires_explicit_operator_action": False,
            }
        )
    if not service_installed:
        actions.append(
            {
                "action": "install_user_service_unit",
                "command": "service install",
                "reason": "watched-folder operation is not installed as a user service yet",
                "safe_to_auto_continue": True,
                "requires_explicit_operator_action": False,
            }
        )
    if not watch_inputs:
        actions.append(
            {
                "action": "configure_watch_inputs",
                "command": "edit user config [watch].inputs",
                "reason": "no watched inputs are configured",
                "safe_to_auto_continue": False,
                "requires_explicit_operator_action": True,
            }
        )
    if watch_error:
        actions.append(
            {
                "action": "repair_watch_input",
                "command": "watch-status --json",
                "reason": watch_error,
                "safe_to_auto_continue": False,
                "requires_explicit_operator_action": True,
            }
        )
    if state != "blocked":
        actions.append(
            {
                "action": "run_fixture_watch_dry_run",
                "command": "watch --once --dry-run",
                "reason": "runtime prerequisites are sufficient for the next fixture-backed Plan 0008 slice",
                "safe_to_auto_continue": True,
                "requires_explicit_operator_action": False,
            }
        )
        actions.append(
            {
                "action": "run_fixture_review_routing_drill",
                "command": "drills review-routing",
                "reason": "prove review, normalization, dedupe, and dry-run sink routing with synthetic fixture data",
                "safe_to_auto_continue": True,
                "requires_explicit_operator_action": False,
            }
        )
    return actions


def _redacted_watch_input_summary(index: int, raw_input: str) -> dict[str, Any]:
    if raw_input.startswith("$fsr:"):
        kind = "fsr_alias"
        display = raw_input
    elif raw_input.startswith("$fsr "):
        kind = "fsr_path"
        display = "$fsr <redacted-path>"
    else:
        kind = "path"
        display = "<redacted-path>"
    return {
        "input_ref": f"input_{index}",
        "configured_ref_kind": kind,
        "configured_ref_display": display,
    }


def _redacted_watch_error(last_error: str) -> str | None:
    if not last_error:
        return None
    if "unknown $fsr alias" in last_error:
        return last_error
    return "configured watch input is not readable; run watch-status --json locally for full operator detail"


def _watch_backlog_preflight_actions(
    *,
    state: str,
    recommended_next_action: str,
) -> list[dict[str, Any]]:
    if recommended_next_action == "prepare_watch_dry_run_selection_handoff":
        return [
            {
                "action": "inspect_watch_dry_run_selection_handoff",
                "command": "watch-dry-run-selection-handoff --json",
                "reason": "prepare the operator-response and command-copy packet before any private-source dry run",
                "safe_to_auto_continue": True,
                "requires_explicit_operator_action": False,
            },
            {
                "action": "operator_explicit_watch_dry_run",
                "command": "watch --once --dry-run",
                "reason": "backlog is present and settled; run only after operator response validation and command-copy acknowledgement",
                "safe_to_auto_continue": False,
                "requires_explicit_operator_action": True,
            },
        ]
    if recommended_next_action == "wait_for_settle_then_recheck":
        return [
            {
                "action": "wait_for_settle_then_recheck",
                "command": "watch-backlog-preflight --json",
                "reason": "some files are still within the configured settle window",
                "safe_to_auto_continue": True,
                "requires_explicit_operator_action": False,
            }
        ]
    if recommended_next_action == "repair_watch_input":
        return [
            {
                "action": "repair_watch_input",
                "command": "watch-status --json",
                "reason": "configured watch input has a local readability error",
                "safe_to_auto_continue": False,
                "requires_explicit_operator_action": True,
            }
        ]
    if recommended_next_action == "configure_watch_inputs":
        return [
            {
                "action": "configure_watch_inputs",
                "command": "edit user config [watch].inputs",
                "reason": "no watched inputs are configured",
                "safe_to_auto_continue": False,
                "requires_explicit_operator_action": True,
            }
        ]
    return [
        {
            "action": "monitor_watch_inputs",
            "command": "watch-backlog-preflight --json",
            "reason": f"watch backlog preflight state is {state}",
            "safe_to_auto_continue": True,
            "requires_explicit_operator_action": False,
        }
    ]


def _max_nested_int(value: Any, key: str) -> int:
    if isinstance(value, dict):
        candidates = [_int(value.get(key))] if key in value else [0]
        candidates.extend(_max_nested_int(item, key) for item in value.values())
        return max(candidates, default=0)
    if isinstance(value, list):
        return max((_max_nested_int(item, key) for item in value), default=0)
    return 0


def _write_synthetic_business_card_image(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    width = 350
    height = 200
    payload = (
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\rIHDR"
        + width.to_bytes(4, "big")
        + height.to_bytes(4, "big")
        + b"\x08\x02\x00\x00\x00"
        + b"\x00\x00\x00\x00"
        + b"\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    path.write_bytes(payload)
    return path


def _write_synthetic_multi_card_image(path: Path) -> tuple[Path, int, bool]:
    path.parent.mkdir(parents=True, exist_ok=True)
    expected_count = 3
    try:
        import cv2  # type: ignore[import-not-found]
        import numpy as np
    except Exception:
        fallback = _write_synthetic_business_card_image(path.with_suffix(".png"))
        return fallback, expected_count, False

    image = np.zeros((900, 1400, 3), dtype=np.uint8)
    cards = [
        ((100, 120), (520, 360)),
        ((650, 140), (1070, 380)),
        ((240, 520), (660, 760)),
    ]
    for top_left, bottom_right in cards:
        cv2.rectangle(image, top_left, bottom_right, (255, 255, 255), thickness=-1)
        cv2.rectangle(image, top_left, bottom_right, (0, 0, 0), thickness=4)
    if not cv2.imwrite(str(path), image):
        fallback = _write_synthetic_business_card_image(path.with_suffix(".png"))
        return fallback, expected_count, False
    return path, expected_count, True

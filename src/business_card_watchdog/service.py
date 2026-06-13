from __future__ import annotations

import json
from html import escape
from pathlib import Path
from typing import Any, Callable

from .config import AppConfig, ensure_runtime_dirs
from .contact import (
    apply_enrichment_proposals,
    apply_review_corrections,
    build_contact_candidate,
    contact_candidate_to_spec,
)
from .dedupe import assess_downstream_lookup_result
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
from .models import CardJob, utc_now
from .orchestrator import BatchOrchestrator
from .review import build_review_submission, write_review_submission
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
)
from .skill_adapter import BusinessCardSkillAdapter
from .watcher import PollingWatcher


_SAFE_NEXT_ACTIONS = {
    "plan_sink_lookup",
    "prepare_sink_lookup_adapter",
    "record_sink_lookup_result",
    "assess_downstream_duplicates",
    "plan_sinks",
    "prepare_sink_write_adapter",
    "preflight_sink_apply",
    "prepare_sink_apply_pilot_readiness",
    "prepare_sink_readback_adapter",
}

_ROUTE_ARTIFACT_FILES = {
    "sink_lookup_plan": "sink_lookup_plan.json",
    "sink_adapter_request_lookup": "sink_adapter_request_lookup.json",
    "sink_lookup_pilot": "sink_lookup_pilot.json",
    "sink_lookup_result": "sink_lookup_result.json",
    "downstream_duplicate_assessment": "downstream_duplicate_assessment.json",
    "sink_plan": "sink_plan.json",
    "sink_adapter_request_write": "sink_adapter_request_write.json",
    "sink_apply_preflight": "sink_apply_preflight.json",
    "sink_apply_decision": "sink_apply_decision.json",
    "sink_apply_pilot_readiness": "sink_apply_pilot_readiness.json",
    "sink_write_pilot": "sink_write_pilot.json",
    "sink_apply_result": "sink_apply_result.json",
    "sink_adapter_request_readback": "sink_adapter_request_readback.json",
    "sink_readback_pilot": "sink_readback_pilot.json",
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
]

_REVIEW_BUNDLE_ARTIFACT_KINDS = {
    "preclassification",
    "review_packet",
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
    "duplicate_assessment",
    "downstream_duplicate_assessment",
    "duplicate_resolution",
    "sink_lookup_plan",
    "sink_adapter_request_lookup",
    "sink_lookup_pilot",
    "sink_lookup_result",
    "sink_plan",
    "sink_adapter_request_write",
    "sink_apply_preflight",
    "sink_apply_decision",
    "sink_apply_pilot_readiness",
    "sink_write_pilot",
    "sink_apply_result",
    "sink_adapter_request_readback",
    "sink_readback_pilot",
    "route_refresh",
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
            "config_path": str(self.config.config_path),
            "data_dir": str(self.config.data_dir),
            "cache_dir": str(self.config.cache_dir),
            "skill_ready": ready,
            "skill_message": message,
            "watch": watch_status.to_dict(),
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
        return {
            "run_id": run_id,
            "state": run["state"],
            "job_count": run["job_count"],
            "state_counts": state_counts,
            "artifact_counts": artifact_counts,
            "enrichment_budget": enrichment_budget,
            "needs_review_count": state_counts.get("needs_review", 0),
            "ready_to_route_count": state_counts.get("ready_to_route", 0),
            "failed_count": state_counts.get("failed", 0),
            "duplicate_assessment_count": artifact_counts.get("duplicate_assessment", 0),
            "reviewed_contact_count": artifact_counts.get("reviewed_contact", 0),
        }

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
                    actions.append({"run_id": current_run_id, "job_id": job["job_id"], **action})
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
        return {
            "run_id": run_id,
            "limit": limit,
            "executed": executed,
            "skipped": skipped,
            "executed_count": len(executed),
            "skipped_count": len(skipped),
        }

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

    def review_queue(self, *, run_id: str | None = None, state: str = "needs_review") -> list[dict[str, Any]]:
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
            queue.append(
                {
                    "run_id": job["run_id"],
                    "job_id": job["job_id"],
                    "state": job["state"],
                    "image_path": job["image_path"],
                    "error": job.get("error"),
                    "artifact_dir": job.get("artifact_dir"),
                    "review_packet": by_kind.get("review_packet"),
                    "duplicate_assessment": by_kind.get("duplicate_assessment"),
                    "contact_candidate": by_kind.get("contact_candidate"),
                    "reviewed_contact": by_kind.get("reviewed_contact"),
                    "artifact_kinds": sorted(by_kind),
                }
            )
        return queue

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
            entries.append(
                {
                    "run_id": run_id,
                    "job_id": job["job_id"],
                    "state": job["state"],
                    "image_path": job["image_path"],
                    "error": job.get("error"),
                    "artifact_dir": job.get("artifact_dir"),
                    "next_action": next_action,
                    "artifact_kinds": sorted(by_kind),
                    "artifacts": {
                        kind: self._artifact_bundle_entry(record)
                        for kind, record in sorted(by_kind.items())
                    },
                    "decision_template": self._review_decision_template(
                        run_id=run_id,
                        job_id=str(job["job_id"]),
                        next_action=next_action,
                    ),
                    "commands": {
                        "show_job": f"jobs show {job['job_id']} --run-id {run_id}",
                        "review": f"jobs review {job['job_id']} --run-id {run_id}",
                        "next": (next_action or {}).get("command"),
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
                "next_actions": f"mcp-call business_card_watchdog_next_actions --arguments-json '{{\"run_id\":\"{run_id}\"}}'",
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
        if action not in {
            "approve_for_routing",
            "approve_enrichment_merge",
            "keep_needs_review",
            "request_enrichment",
            "resolve_duplicate",
            "reject_not_card",
            "skip",
        }:
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
            ledger.record_artifact(job_id=job_id, kind="reviewed_contact", path=reviewed_contact_path)
            ledger.record_artifact(job_id=job_id, kind="enrichment_merge_review", path=merge_review_path)
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
                    "merge_review_path": str(merge_review_path),
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

    def build_sink_apply_pilot_readiness_for_job(self, *, job_id: str, run_id: str) -> dict[str, Any]:
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
        requirements = [
            {
                "name": "preflight_exists",
                "ok": preflight is not None,
                "detail": str(preflight_path),
            },
            {
                "name": "apply_decision_approved",
                "ok": bool(decision and decision.get("decision") == "approve"),
                "detail": str(decision_path),
            },
            {
                "name": "write_adapter_request_exists",
                "ok": write_adapter is not None,
                "detail": str(write_adapter_path),
            },
            {
                "name": "mock_readback_available",
                "ok": True,
                "detail": "simulated apply can produce local readback evidence without a live adapter",
            },
            {
                "name": "live_sink_readiness_ready",
                "ok": all(check.get("status") == "ready" for check in readiness["sinks"]),
                "detail": "all configured sink readiness checks must be ready",
            },
            {
                "name": "readback_adapter_available_after_apply",
                "ok": readback_adapter is not None,
                "detail": str(readback_adapter_path),
            },
        ]
        mock_requirements = {"preflight_exists", "apply_decision_approved", "mock_readback_available"}
        live_requirements = {
            "preflight_exists",
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
                else "apply pilot remains blocked until required review, preflight, and adapter request artifacts exist"
            ),
            "job_id": job_id,
            "run_id": run_id,
            "can_apply_pilot": can_mock_apply_pilot,
            "can_mock_apply_pilot": can_mock_apply_pilot,
            "can_live_apply_pilot": can_live_apply_pilot,
            "writes_attempted": 0,
            "network_calls_made": 0,
            "preflight_state": preflight.get("state") if preflight else "missing",
            "decision_state": decision.get("state") if decision else "missing",
            "decision": decision.get("decision") if decision else "",
            "sink_readiness": readiness,
            "requirements": requirements,
            "missing_requirements": missing_requirements,
            "mock_missing_requirements": [
                name for name in sorted(mock_requirements) if not requirement_by_name[name]
            ],
            "live_missing_requirements": [
                name for name in sorted(live_requirements) if not requirement_by_name[name]
            ],
            "commands": {
                "prepare": "sinks apply-pilot-readiness",
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
            matches = list(execution.get("matches") or [])
        pilot = build_sink_lookup_pilot(
            adapter_request=adapter_request,
            sink=sink,
            approved_by=approved_by,
            matches=matches or [],
            simulate=simulate,
            execution=execution,
        )
        pilot_path = artifact_dir / "sink_lookup_pilot.json"
        pilot_path.write_text(json.dumps(pilot, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        result = build_sink_lookup_result(
            adapter_request=adapter_request,
            matches_by_sink={sink: matches or []},
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
            if self.sink_write_executor is None:
                readiness_path = artifact_dir / "sink_apply_pilot_readiness.json"
                readiness = (
                    json.loads(readiness_path.read_text(encoding="utf-8"))
                    if readiness_path.exists()
                    else self.build_sink_apply_pilot_readiness_for_job(job_id=job_id, run_id=run_id)["readiness"]
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
            if self.sink_readback_executor is not None:
                execution = self.sink_readback_executor(request)
            else:
                execution = execute_sink_readback_adapter(request)
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

    def watch_status(self) -> dict[str, Any]:
        return PollingWatcher(self.config).status().to_dict()

    def watch_reset(self) -> dict[str, Any]:
        PollingWatcher(self.config).reset()
        return {"reset": True, "watch_dir": str(self.config.watch_dir)}

    def _contact_spec_for_artifact_dir(self, artifact_dir: Path) -> dict[str, Any]:
        reviewed_path = artifact_dir / "reviewed_contact.json"
        candidate_path = artifact_dir / "contact_candidate.json"
        spec_path = artifact_dir / "spec.json"
        if reviewed_path.exists():
            reviewed = json.loads(reviewed_path.read_text(encoding="utf-8"))
            spec = contact_candidate_to_spec(reviewed)
            if isinstance(reviewed.get("contact_points"), list):
                spec["contact_points"] = list(reviewed["contact_points"])
            return spec
        if candidate_path.exists():
            candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
            spec = contact_candidate_to_spec(candidate)
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
        for entry in entries:
            state = str(entry.get("state") or "unknown")
            state_group = by_state.setdefault(state, {"count": 0, "job_ids": []})
            state_group["count"] += 1
            state_group["job_ids"].append(entry["job_id"])
            action = str((entry.get("next_action") or {}).get("action") or "none")
            action_group = by_next_action.setdefault(action, {"count": 0, "job_ids": []})
            action_group["count"] += 1
            action_group["job_ids"].append(entry["job_id"])
        return {
            "by_state": dict(sorted(by_state.items())),
            "by_next_action": dict(sorted(by_next_action.items())),
        }

    def _render_review_html(self, bundle: dict[str, Any]) -> str:
        rows = "\n".join(self._review_html_row(entry) for entry in bundle["entries"])
        state_groups = self._review_html_groups(bundle["groups"]["by_state"])
        action_groups = self._review_html_groups(bundle["groups"]["by_next_action"])
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
  <section class="groups">
    <div>
      <h2>By State</h2>
      {state_groups}
    </div>
    <div>
      <h2>By Next Action</h2>
      {action_groups}
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

    def _review_html_row(self, entry: dict[str, Any]) -> str:
        next_action = entry.get("next_action") or {}
        artifacts = ", ".join(escape(kind) for kind in entry.get("artifact_kinds") or [])
        decision_template = escape(json.dumps(entry["decision_template"], sort_keys=True, indent=2))
        image_path = escape(str(entry.get("image_path") or ""))
        return f"""<tr>
  <td><code>{escape(str(entry["job_id"]))}</code></td>
  <td>{escape(str(entry.get("state") or ""))}</td>
  <td><code>{image_path}</code></td>
  <td><code>{escape(str(next_action.get("action") or "none"))}</code><br>{escape(str(next_action.get("reason") or ""))}</td>
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
        if action_name == "prepare_sink_readback_adapter":
            return self.build_sink_adapter_request_for_job(job_id=job_id, run_id=run_id, phase="readback")
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


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _path_check(name: str, path: Path) -> dict[str, Any]:
    path.mkdir(parents=True, exist_ok=True)
    probe = path / ".business-card-watchdog-write-test"
    try:
        probe.write_text("ok\n", encoding="utf-8")
        probe.unlink()
        return {"name": name, "ok": True, "detail": str(path)}
    except OSError as exc:
        return {"name": name, "ok": False, "detail": f"{path}: {exc}"}

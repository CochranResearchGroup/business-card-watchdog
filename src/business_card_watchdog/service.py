from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import AppConfig, ensure_runtime_dirs
from .contact import apply_review_corrections, build_contact_candidate, contact_candidate_to_spec
from .enrichment import build_enrichment_request, check_enrichment_readiness, score_public_web_results
from .ledger import RunLedger
from .models import CardJob
from .orchestrator import BatchOrchestrator
from .review import build_review_submission, write_review_submission
from .routing import decide_sinks
from .sinks import build_sink_apply_preflight, build_sink_plan, check_sink_readiness
from .skill_adapter import BusinessCardSkillAdapter
from .watcher import PollingWatcher


class BusinessCardService:
    def __init__(self, config: AppConfig) -> None:
        self.config = config

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
        return {
            "run_id": run_id,
            "state": run["state"],
            "job_count": run["job_count"],
            "state_counts": state_counts,
            "artifact_counts": artifact_counts,
            "needs_review_count": state_counts.get("needs_review", 0),
            "ready_to_route_count": state_counts.get("ready_to_route", 0),
            "failed_count": state_counts.get("failed", 0),
            "duplicate_assessment_count": artifact_counts.get("duplicate_assessment", 0),
            "reviewed_contact_count": artifact_counts.get("reviewed_contact", 0),
        }

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

    def submit_review(
        self,
        *,
        job_id: str,
        run_id: str,
        reviewer: str,
        action: str,
        field_corrections: dict[str, Any] | None = None,
        crop_selection: dict[str, Any] | None = None,
        notes: str = "",
    ) -> dict[str, Any]:
        if action not in {"approve_for_routing", "keep_needs_review", "request_enrichment", "reject_not_card", "skip"}:
            raise ValueError(f"unsupported review action: {action}")

        job_payload = self.get_job(job_id, run_id=run_id)
        job = CardJob.from_dict(job_payload)
        submission = build_review_submission(
            job_id=job_id,
            reviewer=reviewer,
            action=action,  # type: ignore[arg-type]
            field_corrections=field_corrections,
            crop_selection=crop_selection,
            notes=notes,
        )
        artifact_dir = Path(job.artifact_dir) if job.artifact_dir else self.config.runs_dir / run_id / "artifacts" / job_id
        submission_path = write_review_submission(artifact_dir / "review_submission.json", submission)

        ledger = RunLedger(self.config.runs_dir / run_id)
        ledger.record_artifact(job_id=job_id, kind="review_submission", path=submission_path)
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
            )
            reviewed_contact_path = artifact_dir / "reviewed_contact.json"
            reviewed_contact_path.write_text(
                json.dumps(reviewed_contact, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            ledger.record_artifact(job_id=job_id, kind="reviewed_contact", path=reviewed_contact_path)
            job.transition_to("ready_to_route")
            ledger.record_job(job)
        elif action == "request_enrichment":
            if job.state != "needs_review":
                job.transition_to("needs_review")
                ledger.record_job(job)
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
        return {
            "job": job.to_dict(),
            "submission": submission,
            "submission_path": str(submission_path),
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
                check_sink_readiness(sink, dry_run=self.config.sink.dry_run).to_dict()
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
        if mode in {"public_web", "all"}:
            result_payload = score_public_web_results(candidate, results=public_web_results or [])
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
            },
        )
        return {
            "status": "ok",
            "readiness": readiness,
            "request_path": str(request_path),
            "result_path": str(result_path) if result_path else None,
            "request": request,
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
        )
        plan["job_id"] = job_id
        plan["run_id"] = run_id
        plan["decision"] = decision.to_dict()
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
        return {"plan_path": str(plan_path), "plan": plan}

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
        return {"preflight_path": str(preflight_path), "preflight": preflight}

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
            return contact_candidate_to_spec(reviewed)
        if candidate_path.exists():
            candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
            return contact_candidate_to_spec(candidate)
        if spec_path.exists():
            return json.loads(spec_path.read_text(encoding="utf-8"))
        raise FileNotFoundError(f"no contact artifact found in {artifact_dir}")

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
            if "sink_plan" not in artifact_kinds:
                return {
                    "action": "plan_sinks",
                    "reason": "reviewed/normalized job is ready for dry-run sink planning",
                    "command": "sinks plan",
                }
            return {
                "action": "await_apply_approval",
                "reason": "sink plan exists; live apply remains explicit and gated",
                "command": "sinks apply-preflight",
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


def _path_check(name: str, path: Path) -> dict[str, Any]:
    path.mkdir(parents=True, exist_ok=True)
    probe = path / ".business-card-watchdog-write-test"
    try:
        probe.write_text("ok\n", encoding="utf-8")
        probe.unlink()
        return {"name": name, "ok": True, "detail": str(path)}
    except OSError as exc:
        return {"name": name, "ok": False, "detail": f"{path}: {exc}"}

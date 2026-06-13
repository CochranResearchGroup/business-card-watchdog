from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import ArtifactRecord, CardJob, RunRecord, RunState, utc_now


class RunLedger:
    def __init__(self, run_dir: Path) -> None:
        self.run_dir = run_dir
        self.events_path = run_dir / "events.jsonl"
        self.jobs_path = run_dir / "jobs.jsonl"
        self.run_path = run_dir / "run.json"
        self.artifacts_path = run_dir / "artifacts.jsonl"
        self.run_index_path = run_dir.parent / "index.jsonl"
        self.run_record: RunRecord | None = None
        self.run_dir.mkdir(parents=True, exist_ok=True)

    def initialize(self, *, source: str, dry_run: bool) -> RunRecord:
        record = RunRecord(run_id=self.run_dir.name, source=source, dry_run=dry_run)
        self.run_record = record
        self._write_run()
        self._append_run_index(record)
        self.record_event("run_initialized", record.to_dict())
        return record

    def transition_run(self, state: RunState) -> RunRecord:
        if self.run_record is None:
            self.run_record = self._load_run()
        self.run_record.transition_to(state)
        self._write_run()
        self._append_run_index(self.run_record)
        self.record_event("run_transitioned", {"run_id": self.run_record.run_id, "state": state})
        return self.run_record

    def set_job_count(self, job_count: int) -> None:
        if self.run_record is None:
            self.run_record = self._load_run()
        self.run_record.job_count = job_count
        self.run_record.updated_at = utc_now()
        self._write_run()
        self._append_run_index(self.run_record)

    def record_job(self, job: CardJob) -> None:
        with self.jobs_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(job.to_dict(), sort_keys=True) + "\n")

    def record_artifact(
        self,
        *,
        job_id: str,
        kind: str,
        path: Path,
        metadata: dict[str, Any] | None = None,
    ) -> ArtifactRecord:
        record = ArtifactRecord(
            job_id=job_id,
            kind=kind,
            path=str(path),
            metadata=metadata or {},
        )
        with self.artifacts_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record.to_dict(), sort_keys=True) + "\n")
        self.record_event("artifact_recorded", record.to_dict())
        return record

    def record_event(self, event_type: str, payload: dict[str, Any]) -> None:
        event = {"event_type": event_type, "created_at": utc_now(), "payload": payload}
        with self.events_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, sort_keys=True) + "\n")

    def _write_run(self) -> None:
        if self.run_record is None:
            raise RuntimeError("run ledger is not initialized")
        self.run_path.write_text(
            json.dumps(self.run_record.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def _load_run(self) -> RunRecord:
        payload = json.loads(self.run_path.read_text(encoding="utf-8"))
        return RunRecord(**payload)

    def _append_run_index(self, record: RunRecord) -> None:
        self.run_index_path.parent.mkdir(parents=True, exist_ok=True)
        with self.run_index_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record.to_dict(), sort_keys=True) + "\n")

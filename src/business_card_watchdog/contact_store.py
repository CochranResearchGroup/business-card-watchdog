from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import AppConfig
from .contact import contact_candidate_to_spec
from .models import utc_now


SCHEMA_VERSION = 1
CONTACT_STORE_SCHEMA = "business-card-watchdog.contact-store.v1"
_PROJECTED_ASSET_KINDS = {
    "artifact_dir",
    "preclassification",
    "card_candidates",
    "candidate_crops",
    "child_verification_requests",
    "child_verification_results",
    "child_contact_promotions",
    "candidate_work_items",
    "contact_spec",
    "review_report",
    "ocr_text",
    "crop_manifest",
    "contact_sheet",
    "contact_candidate",
    "document_pages",
    "source_page",
    "card_side_candidate",
    "reviewed_contact",
    "review_packet",
    "duplicate_assessment",
    "downstream_duplicate_assessment",
    "sink_payloads",
    "sink_lookup_plan",
    "sink_plan",
    "enrichment_request",
    "enrichment_public_web_request",
    "enrichment_public_web_search_handoff",
    "enrichment_public_web_result",
    "enrichment_provider_request",
    "enrichment_provider_handoff",
    "enrichment_provider_result",
    "enrichment_result",
    "enrichment_merge_review",
}


@dataclass(frozen=True)
class ProjectionResult:
    run_id: str
    projected_contacts: int
    projected_assets: int
    projected_extraction_attempts: int
    projected_enrichment_attempts: int
    projected_routing_decisions: int
    projected_sink_attempts: int
    skipped_jobs: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": "business-card-watchdog.contact-store-projection.v1",
            "run_id": self.run_id,
            "projected_contacts": self.projected_contacts,
            "projected_assets": self.projected_assets,
            "projected_extraction_attempts": self.projected_extraction_attempts,
            "projected_enrichment_attempts": self.projected_enrichment_attempts,
            "projected_routing_decisions": self.projected_routing_decisions,
            "projected_sink_attempts": self.projected_sink_attempts,
            "skipped_jobs": self.skipped_jobs,
        }


def default_contact_store_path(config: AppConfig) -> Path:
    return config.data_dir / "contacts" / "contacts.sqlite"


class ContactStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    @classmethod
    def from_config(cls, config: AppConfig) -> "ContactStore":
        return cls(default_contact_store_path(config))

    def initialize(self) -> dict[str, Any]:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            self._migrate(conn)
        return self.status()

    def status(self) -> dict[str, Any]:
        exists = self.db_path.exists()
        version = 0
        if exists:
            with self._connect() as conn:
                self._migrate(conn)
                row = conn.execute(
                    "SELECT version FROM schema_migrations ORDER BY version DESC LIMIT 1"
                ).fetchone()
                version = int(row["version"]) if row else 0
        return {
            "schema": CONTACT_STORE_SCHEMA,
            "path": str(self.db_path),
            "exists": exists,
            "schema_version": version,
        }

    def list_contacts(self, *, limit: int = 100) -> list[dict[str, Any]]:
        self.initialize()
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT contact_id, state, display_name, organization, email, phone,
                       source_run_id, source_job_id, created_at, updated_at
                FROM contacts
                ORDER BY updated_at DESC, contact_id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_contact(self, contact_id: str) -> dict[str, Any]:
        self.initialize()
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM contacts WHERE contact_id = ?", (contact_id,)).fetchone()
            if row is None:
                raise KeyError(f"contact not found: {contact_id}")
            assets = conn.execute(
                "SELECT * FROM card_assets WHERE contact_id = ? ORDER BY created_at, asset_id",
                (contact_id,),
            ).fetchall()
            attempts = conn.execute(
                "SELECT * FROM extraction_attempts WHERE contact_id = ? ORDER BY created_at, attempt_id",
                (contact_id,),
            ).fetchall()
            enrichment = conn.execute(
                "SELECT * FROM enrichment_attempts WHERE contact_id = ? ORDER BY created_at, attempt_id",
                (contact_id,),
            ).fetchall()
            routing = conn.execute(
                "SELECT * FROM routing_decisions WHERE contact_id = ? ORDER BY created_at, decision_id",
                (contact_id,),
            ).fetchall()
            sinks = conn.execute(
                "SELECT * FROM sink_attempts WHERE contact_id = ? ORDER BY created_at, attempt_id",
                (contact_id,),
            ).fetchall()
            bindings = conn.execute(
                "SELECT * FROM external_bindings WHERE contact_id = ? ORDER BY created_at, binding_id",
                (contact_id,),
            ).fetchall()
        payload = dict(row)
        payload["payload"] = _json_loads(payload.pop("payload_json"))
        payload["assets"] = [_row_with_payload(asset) for asset in assets]
        payload["extraction_attempts"] = [_row_with_payload(attempt) for attempt in attempts]
        payload["enrichment_attempts"] = [_row_with_payload(attempt) for attempt in enrichment]
        payload["routing_decisions"] = [_row_with_payload(decision) for decision in routing]
        payload["sink_attempts"] = [_row_with_payload(attempt) for attempt in sinks]
        payload["external_bindings"] = [_row_with_payload(binding) for binding in bindings]
        return payload

    def project_run(self, *, run_id: str, run_dir: Path) -> ProjectionResult:
        self.initialize()
        artifacts = _read_jsonl(run_dir / "artifacts.jsonl")
        jobs = {str(row.get("job_id") or ""): row for row in _read_jsonl(run_dir / "jobs.jsonl")}
        by_job: dict[str, dict[str, dict[str, Any]]] = {}
        for artifact in artifacts:
            job_id = str(artifact.get("job_id") or "")
            kind = str(artifact.get("kind") or "")
            if job_id and kind:
                by_job.setdefault(job_id, {})[kind] = artifact

        projected_contacts = 0
        projected_assets = 0
        projected_extraction_attempts = 0
        projected_enrichment_attempts = 0
        projected_routing_decisions = 0
        projected_sink_attempts = 0
        skipped_jobs = 0
        for job_id, artifacts_by_kind in by_job.items():
            candidate_artifact = artifacts_by_kind.get("reviewed_contact") or artifacts_by_kind.get("contact_candidate")
            if not candidate_artifact:
                skipped_jobs += 1
                continue
            candidate_path = Path(str(candidate_artifact.get("path") or ""))
            candidate = _read_json_file(candidate_path)
            if candidate is None:
                skipped_jobs += 1
                continue
            job = jobs.get(job_id, {})
            contact_id = self.upsert_contact_from_candidate(
                run_id=run_id,
                job_id=job_id,
                candidate=candidate,
                artifact_path=candidate_path,
                job=job,
            )
            projected_contacts += 1
            projected_extraction_attempts += self.upsert_extraction_attempt(
                contact_id=contact_id,
                run_id=run_id,
                job_id=job_id,
                artifact_path=candidate_path,
                candidate_kind=str(candidate_artifact.get("kind") or "contact_candidate"),
                job=job,
            )
            projected_assets += self.upsert_assets_for_job(
                contact_id=contact_id,
                run_id=run_id,
                job_id=job_id,
                artifacts=artifacts_by_kind,
                job=job,
            )
            projected_enrichment_attempts += self.upsert_enrichment_attempts_for_job(
                contact_id=contact_id,
                run_id=run_id,
                job_id=job_id,
                artifacts=artifacts_by_kind,
            )
            projected_routing_decisions += self.upsert_routing_decision_for_job(
                contact_id=contact_id,
                run_id=run_id,
                job_id=job_id,
                artifacts=artifacts_by_kind,
                job=job,
            )
            projected_sink_attempts += self.upsert_sink_attempts_for_job(
                contact_id=contact_id,
                run_id=run_id,
                job_id=job_id,
                artifacts=artifacts_by_kind,
            )

        return ProjectionResult(
            run_id=run_id,
            projected_contacts=projected_contacts,
            projected_assets=projected_assets,
            projected_extraction_attempts=projected_extraction_attempts,
            projected_enrichment_attempts=projected_enrichment_attempts,
            projected_routing_decisions=projected_routing_decisions,
            projected_sink_attempts=projected_sink_attempts,
            skipped_jobs=skipped_jobs,
        )

    def run_projection_status(self, *, run_id: str, run_dir: Path) -> dict[str, Any]:
        self.initialize()
        expected_job_ids, unreadable_job_ids = _candidate_job_ids(run_dir)
        with self._connect() as conn:
            self._migrate(conn)
            rows = conn.execute(
                "SELECT contact_id, source_job_id FROM contacts WHERE source_run_id = ?",
                (run_id,),
            ).fetchall()
        projected_job_ids = {str(row["source_job_id"]) for row in rows}
        missing_job_ids = sorted(expected_job_ids - projected_job_ids)
        extra_job_ids = sorted(projected_job_ids - expected_job_ids)
        return {
            "schema": "business-card-watchdog.contact-store-drift.v1",
            "run_id": run_id,
            "state": "in_sync" if not missing_job_ids and not extra_job_ids and not unreadable_job_ids else "drift",
            "expected_contact_count": len(expected_job_ids),
            "projected_contact_count": len(projected_job_ids),
            "missing_job_ids": missing_job_ids,
            "extra_job_ids": extra_job_ids,
            "unreadable_candidate_job_ids": sorted(unreadable_job_ids),
            "writes_attempted": 0,
            "network_calls_made": 0,
        }

    def upsert_contact_from_candidate(
        self,
        *,
        run_id: str,
        job_id: str,
        candidate: dict[str, Any],
        artifact_path: Path,
        job: dict[str, Any] | None = None,
    ) -> str:
        self.initialize()
        spec = contact_candidate_to_spec(candidate)
        flat = candidate.get("flat") if isinstance(candidate.get("flat"), dict) else {}
        contact_id = _stable_id("contact", run_id, job_id)
        now = utc_now()
        display_name = str(spec.get("full_name") or flat.get("full_name") or "").strip()
        organization = str(spec.get("organization") or flat.get("organization") or "").strip()
        email = str(spec.get("email") or flat.get("email") or "").strip()
        phone = str(spec.get("phone") or flat.get("phone") or "").strip()
        payload = {
            "candidate": candidate,
            "contact_spec": spec,
            "source_artifact_path": str(artifact_path),
            "source_image_path": str((job or {}).get("image_path") or ""),
        }
        with self._connect() as conn:
            self._migrate(conn)
            conn.execute(
                """
                INSERT INTO contacts (
                    contact_id, source_run_id, source_job_id, state, display_name,
                    organization, email, phone, payload_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(contact_id) DO UPDATE SET
                    state = excluded.state,
                    display_name = excluded.display_name,
                    organization = excluded.organization,
                    email = excluded.email,
                    phone = excluded.phone,
                    payload_json = excluded.payload_json,
                    updated_at = excluded.updated_at
                """,
                (
                    contact_id,
                    run_id,
                    job_id,
                    "projected",
                    display_name,
                    organization,
                    email,
                    phone,
                    _json_dumps(payload),
                    now,
                    now,
                ),
            )
        return contact_id

    def upsert_extraction_attempt(
        self,
        *,
        contact_id: str,
        run_id: str,
        job_id: str,
        artifact_path: Path,
        candidate_kind: str,
        job: dict[str, Any] | None = None,
    ) -> int:
        attempt_id = _stable_id("extract", run_id, job_id, str(artifact_path))
        now = utc_now()
        payload = {
            "candidate_kind": candidate_kind,
            "source_image_path": str((job or {}).get("image_path") or ""),
        }
        with self._connect() as conn:
            self._migrate(conn)
            conn.execute(
                """
                INSERT INTO extraction_attempts (
                    attempt_id, contact_id, source_run_id, source_job_id, adapter,
                    state, artifact_path, payload_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(attempt_id) DO UPDATE SET
                    contact_id = excluded.contact_id,
                    state = excluded.state,
                    artifact_path = excluded.artifact_path,
                    payload_json = excluded.payload_json,
                    updated_at = excluded.updated_at
                """,
                (
                    attempt_id,
                    contact_id,
                    run_id,
                    job_id,
                    "business_card_to_contact",
                    "projected",
                    str(artifact_path),
                    _json_dumps(payload),
                    now,
                    now,
                ),
            )
        return 1

    def upsert_assets_for_job(
        self,
        *,
        contact_id: str,
        run_id: str,
        job_id: str,
        artifacts: dict[str, dict[str, Any]],
        job: dict[str, Any] | None = None,
    ) -> int:
        rows: list[tuple[str, str, str, str, str, str, str, str, str, str]] = []
        now = utc_now()
        source_path = str((job or {}).get("image_path") or "")
        if source_path:
            rows.append(
                (
                    _stable_id("asset", run_id, job_id, "source", source_path),
                    contact_id,
                    run_id,
                    job_id,
                    "source",
                    _media_kind(source_path),
                    "unknown",
                    source_path,
                    _json_dumps({"source": "job.image_path"}),
                    now,
                )
            )
        for kind, artifact in artifacts.items():
            path = str(artifact.get("path") or "")
            if kind not in _PROJECTED_ASSET_KINDS or not path:
                continue
            rows.append(
                (
                    _stable_id("asset", run_id, job_id, kind, path),
                    contact_id,
                    run_id,
                    job_id,
                    kind,
                    _media_kind(path),
                    "unknown",
                    path,
                    _json_dumps({"artifact": artifact}),
                    now,
                )
            )
        with self._connect() as conn:
            self._migrate(conn)
            for row in rows:
                conn.execute(
                    """
                    INSERT INTO card_assets (
                        asset_id, contact_id, source_run_id, source_job_id, asset_kind,
                        media_kind, side_label, path_ref, payload_json, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(asset_id) DO UPDATE SET
                        contact_id = excluded.contact_id,
                        path_ref = excluded.path_ref,
                        payload_json = excluded.payload_json,
                        updated_at = excluded.updated_at
                    """,
                    (*row, now),
                )
        return len(rows)

    def upsert_enrichment_attempts_for_job(
        self,
        *,
        contact_id: str,
        run_id: str,
        job_id: str,
        artifacts: dict[str, dict[str, Any]],
    ) -> int:
        rows: list[tuple[str, str, str, str, str, str, str]] = []
        now = utc_now()
        for kind, artifact in artifacts.items():
            if not kind.startswith("enrichment"):
                continue
            path = Path(str(artifact.get("path") or ""))
            payload = _read_json_file(path) or {}
            provider = _enrichment_provider(kind, payload)
            state = str(payload.get("state") or payload.get("status") or "recorded")
            rows.append(
                (
                    _stable_id("enrich", run_id, job_id, kind, str(path)),
                    contact_id,
                    provider,
                    state,
                    _json_dumps({"artifact": artifact, "payload": payload}),
                    now,
                    now,
                )
            )
        with self._connect() as conn:
            self._migrate(conn)
            for row in rows:
                conn.execute(
                    """
                    INSERT INTO enrichment_attempts (
                        attempt_id, contact_id, provider, state, payload_json, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(attempt_id) DO UPDATE SET
                        contact_id = excluded.contact_id,
                        provider = excluded.provider,
                        state = excluded.state,
                        payload_json = excluded.payload_json,
                        updated_at = excluded.updated_at
                    """,
                    row,
                )
        return len(rows)

    def upsert_routing_decision_for_job(
        self,
        *,
        contact_id: str,
        run_id: str,
        job_id: str,
        artifacts: dict[str, dict[str, Any]],
        job: dict[str, Any] | None = None,
    ) -> int:
        sink_payload_artifact = artifacts.get("sink_payloads")
        duplicate_artifact = artifacts.get("duplicate_assessment") or artifacts.get("downstream_duplicate_assessment")
        sink_payloads = _read_json_file(Path(str((sink_payload_artifact or {}).get("path") or ""))) or {}
        duplicate = _read_json_file(Path(str((duplicate_artifact or {}).get("path") or ""))) or {}
        payload_rows = sink_payloads.get("payloads") if isinstance(sink_payloads.get("payloads"), list) else []
        sinks = sorted({str(row.get("sink") or "") for row in payload_rows if isinstance(row, dict) and row.get("sink")})
        job_state = str((job or {}).get("state") or "")
        if sinks:
            state = "ready_to_route"
        elif duplicate.get("blocks_routing") or job_state == "needs_review":
            state = "needs_review"
        else:
            state = "no_route"
        payload = {
            "job_state": job_state,
            "sinks": sinks,
            "sink_payloads": sink_payloads,
            "duplicate_assessment": duplicate,
            "source_artifacts": {
                "sink_payloads": sink_payload_artifact,
                "duplicate_assessment": duplicate_artifact,
            },
        }
        now = utc_now()
        with self._connect() as conn:
            self._migrate(conn)
            conn.execute(
                """
                INSERT INTO routing_decisions (
                    decision_id, contact_id, tenant, state, payload_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(decision_id) DO UPDATE SET
                    contact_id = excluded.contact_id,
                    tenant = excluded.tenant,
                    state = excluded.state,
                    payload_json = excluded.payload_json,
                    updated_at = excluded.updated_at
                """,
                (
                    _stable_id("route", run_id, job_id),
                    contact_id,
                    ",".join(sinks) if sinks else "unassigned",
                    state,
                    _json_dumps(payload),
                    now,
                    now,
                ),
            )
        return 1

    def upsert_sink_attempts_for_job(
        self,
        *,
        contact_id: str,
        run_id: str,
        job_id: str,
        artifacts: dict[str, dict[str, Any]],
    ) -> int:
        sink_payload_artifact = artifacts.get("sink_payloads")
        sink_payloads = _read_json_file(Path(str((sink_payload_artifact or {}).get("path") or ""))) or {}
        payload_rows = sink_payloads.get("payloads") if isinstance(sink_payloads.get("payloads"), list) else []
        rows: list[tuple[str, str, str, str, str, str, str]] = []
        now = utc_now()
        for row in payload_rows:
            if not isinstance(row, dict):
                continue
            sink = str(row.get("sink") or "")
            if not sink:
                continue
            state = "dry_run" if row.get("dry_run", True) else "planned"
            rows.append(
                (
                    _stable_id("sink", run_id, job_id, sink),
                    contact_id,
                    sink,
                    state,
                    _json_dumps({"sink_payload": row, "artifact": sink_payload_artifact}),
                    now,
                    now,
                )
            )
        with self._connect() as conn:
            self._migrate(conn)
            for row in rows:
                conn.execute(
                    """
                    INSERT INTO sink_attempts (
                        attempt_id, contact_id, sink, state, payload_json, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(attempt_id) DO UPDATE SET
                        contact_id = excluded.contact_id,
                        sink = excluded.sink,
                        state = excluded.state,
                        payload_json = excluded.payload_json,
                        updated_at = excluded.updated_at
                    """,
                    row,
                )
        return len(rows)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _migrate(self, conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS contacts (
                contact_id TEXT PRIMARY KEY,
                source_run_id TEXT NOT NULL,
                source_job_id TEXT NOT NULL,
                state TEXT NOT NULL,
                display_name TEXT NOT NULL DEFAULT '',
                organization TEXT NOT NULL DEFAULT '',
                email TEXT NOT NULL DEFAULT '',
                phone TEXT NOT NULL DEFAULT '',
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS card_assets (
                asset_id TEXT PRIMARY KEY,
                contact_id TEXT,
                source_run_id TEXT NOT NULL,
                source_job_id TEXT NOT NULL,
                asset_kind TEXT NOT NULL,
                media_kind TEXT NOT NULL,
                side_label TEXT NOT NULL DEFAULT 'unknown',
                path_ref TEXT NOT NULL,
                sha256 TEXT,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(contact_id) REFERENCES contacts(contact_id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS extraction_attempts (
                attempt_id TEXT PRIMARY KEY,
                contact_id TEXT,
                source_run_id TEXT NOT NULL,
                source_job_id TEXT NOT NULL,
                adapter TEXT NOT NULL,
                state TEXT NOT NULL,
                artifact_path TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(contact_id) REFERENCES contacts(contact_id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS enrichment_attempts (
                attempt_id TEXT PRIMARY KEY,
                contact_id TEXT,
                provider TEXT NOT NULL,
                state TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(contact_id) REFERENCES contacts(contact_id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS routing_decisions (
                decision_id TEXT PRIMARY KEY,
                contact_id TEXT,
                tenant TEXT NOT NULL,
                state TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(contact_id) REFERENCES contacts(contact_id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS sink_attempts (
                attempt_id TEXT PRIMARY KEY,
                contact_id TEXT,
                sink TEXT NOT NULL,
                state TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(contact_id) REFERENCES contacts(contact_id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS external_bindings (
                binding_id TEXT PRIMARY KEY,
                contact_id TEXT,
                system TEXT NOT NULL,
                external_id TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(contact_id) REFERENCES contacts(contact_id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_contacts_source ON contacts(source_run_id, source_job_id);
            CREATE INDEX IF NOT EXISTS idx_contacts_email ON contacts(email);
            CREATE INDEX IF NOT EXISTS idx_assets_contact ON card_assets(contact_id);
            CREATE INDEX IF NOT EXISTS idx_extraction_contact ON extraction_attempts(contact_id);
            """
        )
        conn.execute(
            "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (?, ?)",
            (SCHEMA_VERSION, utc_now()),
        )


def _stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()[:20]
    return f"{prefix}_{digest}"


def _json_dumps(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _json_loads(value: str) -> dict[str, Any]:
    payload = json.loads(value)
    return payload if isinstance(payload, dict) else {}


def _row_with_payload(row: sqlite3.Row) -> dict[str, Any]:
    payload = dict(row)
    payload["payload"] = _json_loads(payload.pop("payload_json"))
    return payload


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        payload = json.loads(line)
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def _read_json_file(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _candidate_job_ids(run_dir: Path) -> tuple[set[str], set[str]]:
    expected: set[str] = set()
    unreadable: set[str] = set()
    for artifact in _read_jsonl(run_dir / "artifacts.jsonl"):
        kind = str(artifact.get("kind") or "")
        if kind not in {"contact_candidate", "reviewed_contact"}:
            continue
        job_id = str(artifact.get("job_id") or "")
        path = Path(str(artifact.get("path") or ""))
        if _read_json_file(path) is None:
            unreadable.add(job_id)
            continue
        expected.add(job_id)
    return expected, unreadable


def _enrichment_provider(kind: str, payload: dict[str, Any]) -> str:
    provider = str(payload.get("provider") or "").strip()
    if provider:
        return provider
    if "public_web" in kind:
        return "public_web"
    if "provider" in kind:
        return str(payload.get("provider_name") or "paid_provider")
    return "unknown"


def _media_kind(path: str) -> str:
    suffix = Path(path).suffix.lower()
    if suffix == ".pdf":
        return "pdf"
    if suffix in {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".bmp"}:
        return "image"
    if suffix in {".json", ".jsonl"}:
        return "json"
    if suffix in {".md", ".txt"}:
        return "text"
    return "unknown"

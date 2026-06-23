from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import AppConfig
from .contact import CONTACT_FIELDS, contact_candidate_to_spec
from .models import utc_now


SCHEMA_VERSION = 5
CONTACT_STORE_SCHEMA = "business-card-watchdog.contact-store.v1"
CONTACT_FIELD_CORRECTION_FIELDS = {"display_name", "organization", "email", "phone"}
CONTACT_CROP_DECISIONS = {"accept", "reject", "needs_recrop", "use_alternate"}
CONTACT_ENRICHMENT_MERGE_FIELDS = set(CONTACT_FIELDS)
CONTACT_SINK_APPROVAL_STATES = {
    "approved_for_lookup",
    "approved_for_write_pilot",
    "rejected",
    "needs_review",
}
_PROJECTED_ASSET_KINDS = {
    "artifact_dir",
    "preclassification",
    "card_candidates",
    "candidate_crops",
    "qr_evidence",
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
    "card_side_classification",
    "card_side_pair_proposals",
    "side_pair_review_submission",
    "side_pair_review_result",
    "reviewed_side_pair_contact",
    "child_review_submission",
    "child_contact_review_result",
    "reviewed_child_contact",
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
    "enrichment_proposal_review",
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
            mutations = conn.execute(
                "SELECT * FROM contact_mutations WHERE contact_id = ? ORDER BY created_at, mutation_id",
                (contact_id,),
            ).fetchall()
            review_states = conn.execute(
                "SELECT * FROM contact_review_states WHERE contact_id = ? ORDER BY created_at, review_state_id",
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
        payload["mutations"] = [_row_with_payload(mutation) for mutation in mutations]
        payload["review_states"] = [_row_with_payload(review_state) for review_state in review_states]
        return payload

    def apply_field_corrections(
        self,
        *,
        contact_id: str,
        operator: str,
        field_corrections: dict[str, Any],
        reason: str = "",
    ) -> dict[str, Any]:
        if not operator.strip():
            raise ValueError("contact field correction requires an operator")
        unsupported = sorted(set(field_corrections) - CONTACT_FIELD_CORRECTION_FIELDS)
        if unsupported:
            raise ValueError(f"unsupported contact field corrections: {', '.join(unsupported)}")
        self.initialize()
        current = self.get_contact(contact_id)
        previous_values = {field: str(current.get(field) or "") for field in CONTACT_FIELD_CORRECTION_FIELDS}
        normalized = {
            field: str(value or "").strip()
            for field, value in field_corrections.items()
            if field in CONTACT_FIELD_CORRECTION_FIELDS
        }
        changed = {
            field: {"previous": previous_values[field], "new": value}
            for field, value in normalized.items()
            if value != previous_values[field]
        }
        now = utc_now()
        mutation_id = _stable_id(
            "mutation",
            contact_id,
            operator,
            "field_correction",
            _json_dump_value(changed),
            now,
        )
        contact_payload = dict(current.get("payload") or {})
        contact_spec = dict(contact_payload.get("contact_spec") or {})
        for field, values in changed.items():
            if field == "display_name":
                contact_spec["full_name"] = values["new"]
            else:
                contact_spec[field] = values["new"]
        if changed:
            contact_payload["contact_spec"] = contact_spec
            contact_payload.setdefault("review_mutations", []).append(
                {
                    "mutation_id": mutation_id,
                    "action": "field_correction",
                    "operator": operator,
                    "reason": reason,
                    "changed_fields": sorted(changed),
                    "created_at": now,
                }
            )
        mutation_payload = {
            "action": "field_correction",
            "operator": operator,
            "reason": reason,
            "previous_values": previous_values,
            "new_values": {field: item["new"] for field, item in changed.items()},
            "changed_fields": changed,
        }
        with self._connect() as conn:
            self._migrate(conn)
            conn.execute(
                """
                INSERT INTO contact_mutations (
                    mutation_id, contact_id, action, operator, previous_json,
                    new_json, payload_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    mutation_id,
                    contact_id,
                    "field_correction",
                    operator,
                    _json_dump_value({field: item["previous"] for field, item in changed.items()}),
                    _json_dump_value({field: item["new"] for field, item in changed.items()}),
                    _json_dumps(mutation_payload),
                    now,
                    now,
                ),
            )
            if changed:
                conn.execute(
                    """
                    UPDATE contacts
                    SET display_name = ?,
                        organization = ?,
                        email = ?,
                        phone = ?,
                        payload_json = ?,
                        updated_at = ?
                    WHERE contact_id = ?
                    """,
                    (
                        changed.get("display_name", {}).get("new", previous_values["display_name"]),
                        changed.get("organization", {}).get("new", previous_values["organization"]),
                        changed.get("email", {}).get("new", previous_values["email"]),
                        changed.get("phone", {}).get("new", previous_values["phone"]),
                        _json_dumps(contact_payload),
                        now,
                        contact_id,
                    ),
                )
        mutation = self.get_mutation(mutation_id)
        return {"mutation": mutation, "contact": self.get_contact(contact_id)}

    def decide_crop(
        self,
        *,
        contact_id: str,
        operator: str,
        asset_id: str,
        decision: str,
        reason: str = "",
        selected_crop_path: str = "",
        selected_crop_sha256: str = "",
    ) -> dict[str, Any]:
        if not operator.strip():
            raise ValueError("contact crop decision requires an operator")
        normalized_decision = decision.strip()
        if normalized_decision not in CONTACT_CROP_DECISIONS:
            raise ValueError(f"unsupported contact crop decision: {normalized_decision}")
        self.initialize()
        self.get_contact(contact_id)
        with self._connect() as conn:
            self._migrate(conn)
            row = conn.execute(
                "SELECT * FROM card_assets WHERE asset_id = ? AND contact_id = ?",
                (asset_id, contact_id),
            ).fetchone()
        if row is None:
            raise KeyError(f"card asset not found for contact: {asset_id}")
        current_asset = _row_with_payload(row)
        previous_values = _crop_decision_snapshot(current_asset)
        now = utc_now()
        new_values = {
            "asset_id": asset_id,
            "decision": normalized_decision,
            "selected_crop_path": selected_crop_path.strip(),
            "selected_crop_sha256": selected_crop_sha256.strip(),
            "reason": reason,
            "decided_by": operator,
            "decided_at": now,
        }
        mutation_id = _stable_id(
            "mutation",
            contact_id,
            operator,
            "crop_decision",
            asset_id,
            _json_dump_value(new_values),
            now,
        )
        asset_payload = dict(current_asset.get("payload") or {})
        asset_payload.setdefault("review_mutations", []).append(
            {
                "mutation_id": mutation_id,
                "action": "crop_decision",
                "operator": operator,
                "reason": reason,
                "previous_values": previous_values,
                "new_values": new_values,
                "created_at": now,
            }
        )
        asset_payload["crop_decision"] = {
            "mutation_id": mutation_id,
            **new_values,
        }
        mutation_payload = {
            "action": "crop_decision",
            "operator": operator,
            "reason": reason,
            "asset_id": asset_id,
            "previous_values": previous_values,
            "new_values": new_values,
        }
        with self._connect() as conn:
            self._migrate(conn)
            conn.execute(
                """
                INSERT INTO contact_mutations (
                    mutation_id, contact_id, action, operator, previous_json,
                    new_json, payload_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    mutation_id,
                    contact_id,
                    "crop_decision",
                    operator,
                    _json_dump_value(previous_values),
                    _json_dump_value(new_values),
                    _json_dumps(mutation_payload),
                    now,
                    now,
                ),
            )
            conn.execute(
                """
                UPDATE card_assets
                SET payload_json = ?,
                    sha256 = ?,
                    updated_at = ?
                WHERE asset_id = ? AND contact_id = ?
                """,
                (
                    _json_dumps(asset_payload),
                    selected_crop_sha256.strip() or current_asset.get("sha256"),
                    now,
                    asset_id,
                    contact_id,
                ),
            )
        return {
            "mutation": self.get_mutation(mutation_id),
            "asset": self.get_asset(asset_id),
            "contact": self.get_contact(contact_id),
        }

    def apply_enrichment_merge(
        self,
        *,
        contact_id: str,
        operator: str,
        attempt_id: str,
        approved_fields: list[str],
        reason: str = "",
    ) -> dict[str, Any]:
        if not operator.strip():
            raise ValueError("contact enrichment merge requires an operator")
        approved = sorted({str(field).strip() for field in approved_fields if str(field).strip()})
        unsupported = sorted(set(approved) - CONTACT_ENRICHMENT_MERGE_FIELDS)
        if unsupported:
            raise ValueError(f"unsupported enrichment merge fields: {', '.join(unsupported)}")
        contact = self.get_contact(contact_id)
        attempt = self.get_enrichment_attempt(attempt_id)
        if str(attempt.get("contact_id") or "") != contact_id:
            raise KeyError(f"enrichment attempt not found for contact: {attempt_id}")
        proposals = _enrichment_merge_proposals(attempt)
        previous_values = _contact_spec_snapshot(contact)
        approved_set = set(approved)
        changed: dict[str, dict[str, Any]] = {}
        skipped: list[dict[str, Any]] = []
        for proposal in proposals:
            field = str(proposal.get("field") or "").strip()
            value = str(proposal.get("value") or "").strip()
            if field not in CONTACT_ENRICHMENT_MERGE_FIELDS or not value:
                skipped.append({"field": field, "reason": "unsupported or empty proposal"})
                continue
            if field not in approved_set:
                skipped.append({"field": field, "reason": "field was not approved"})
                continue
            if value != previous_values.get(field, ""):
                changed[field] = {
                    "previous": previous_values.get(field, ""),
                    "new": value,
                    "source": proposal.get("source"),
                }
        now = utc_now()
        mutation_id = _stable_id(
            "mutation",
            contact_id,
            operator,
            "enrichment_merge",
            attempt_id,
            _json_dump_value(changed),
            now,
        )
        contact_payload = dict(contact.get("payload") or {})
        contact_spec = dict(contact_payload.get("contact_spec") or {})
        for field, values in changed.items():
            contact_spec[field] = values["new"]
        if changed:
            contact_payload["contact_spec"] = contact_spec
        merge_decision = {
            "mutation_id": mutation_id,
            "action": "enrichment_merge",
            "operator": operator,
            "reason": reason,
            "attempt_id": attempt_id,
            "approved_fields": approved,
            "applied": [
                {
                    "field": field,
                    "value": values["new"],
                    "source": values.get("source"),
                }
                for field, values in sorted(changed.items())
            ],
            "skipped": skipped,
            "created_at": now,
        }
        contact_payload.setdefault("review_mutations", []).append(merge_decision)
        contact_payload["enrichment_merge_decision"] = merge_decision
        mutation_payload = {
            "action": "enrichment_merge",
            "operator": operator,
            "reason": reason,
            "attempt_id": attempt_id,
            "approved_fields": approved,
            "previous_values": previous_values,
            "new_values": {field: item["new"] for field, item in changed.items()},
            "changed_fields": changed,
            "skipped": skipped,
        }
        with self._connect() as conn:
            self._migrate(conn)
            conn.execute(
                """
                INSERT INTO contact_mutations (
                    mutation_id, contact_id, action, operator, previous_json,
                    new_json, payload_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    mutation_id,
                    contact_id,
                    "enrichment_merge",
                    operator,
                    _json_dump_value(previous_values),
                    _json_dump_value({field: item["new"] for field, item in changed.items()}),
                    _json_dumps(mutation_payload),
                    now,
                    now,
                ),
            )
            conn.execute(
                """
                UPDATE contacts
                SET display_name = ?,
                    organization = ?,
                    email = ?,
                    phone = ?,
                    payload_json = ?,
                    updated_at = ?
                WHERE contact_id = ?
                """,
                (
                    changed.get("full_name", {}).get("new", contact.get("display_name") or ""),
                    changed.get("organization", {}).get("new", contact.get("organization") or ""),
                    changed.get("email", {}).get("new", contact.get("email") or ""),
                    changed.get("phone", {}).get("new", contact.get("phone") or ""),
                    _json_dumps(contact_payload),
                    now,
                    contact_id,
                ),
            )
        return {
            "mutation": self.get_mutation(mutation_id),
            "attempt": self.get_enrichment_attempt(attempt_id),
            "contact": self.get_contact(contact_id),
        }

    def get_mutation(self, mutation_id: str) -> dict[str, Any]:
        self.initialize()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM contact_mutations WHERE mutation_id = ?",
                (mutation_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"contact mutation not found: {mutation_id}")
        return _row_with_payload(row)

    def get_asset(self, asset_id: str) -> dict[str, Any]:
        self.initialize()
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM card_assets WHERE asset_id = ?", (asset_id,)).fetchone()
        if row is None:
            raise KeyError(f"card asset not found: {asset_id}")
        return _row_with_payload(row)

    def get_enrichment_attempt(self, attempt_id: str) -> dict[str, Any]:
        self.initialize()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM enrichment_attempts WHERE attempt_id = ?",
                (attempt_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"enrichment attempt not found: {attempt_id}")
        return _row_with_payload(row)

    def set_sink_approval_state(
        self,
        *,
        contact_id: str,
        operator: str,
        attempt_id: str,
        approval_state: str,
        reason: str = "",
        scope: str = "lookup",
    ) -> dict[str, Any]:
        if not operator.strip():
            raise ValueError("contact sink approval requires an operator")
        normalized_state = approval_state.strip()
        if normalized_state not in CONTACT_SINK_APPROVAL_STATES:
            raise ValueError(f"unsupported contact sink approval state: {normalized_state}")
        normalized_scope = scope.strip() or "lookup"
        if normalized_scope not in {"lookup", "write", "readback", "all"}:
            raise ValueError(f"unsupported contact sink approval scope: {normalized_scope}")
        self.get_contact(contact_id)
        attempt = self.get_sink_attempt(attempt_id)
        if str(attempt.get("contact_id") or "") != contact_id:
            raise KeyError(f"sink attempt not found for contact: {attempt_id}")
        previous_values = _sink_approval_snapshot(attempt)
        now = utc_now()
        new_values = {
            "attempt_id": attempt_id,
            "sink": attempt.get("sink"),
            "previous_state": attempt.get("state"),
            "approval_state": normalized_state,
            "scope": normalized_scope,
            "reason": reason,
            "approved_by": operator,
            "approved_at": now,
        }
        mutation_id = _stable_id(
            "mutation",
            contact_id,
            operator,
            "sink_approval",
            attempt_id,
            _json_dump_value(new_values),
            now,
        )
        payload = dict(attempt.get("payload") or {})
        payload.setdefault("review_mutations", []).append(
            {
                "mutation_id": mutation_id,
                "action": "sink_approval",
                "operator": operator,
                "reason": reason,
                "previous_values": previous_values,
                "new_values": new_values,
                "created_at": now,
            }
        )
        payload["sink_approval"] = {
            "mutation_id": mutation_id,
            **new_values,
        }
        mutation_payload = {
            "action": "sink_approval",
            "operator": operator,
            "reason": reason,
            "attempt_id": attempt_id,
            "previous_values": previous_values,
            "new_values": new_values,
        }
        with self._connect() as conn:
            self._migrate(conn)
            conn.execute(
                """
                INSERT INTO contact_mutations (
                    mutation_id, contact_id, action, operator, previous_json,
                    new_json, payload_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    mutation_id,
                    contact_id,
                    "sink_approval",
                    operator,
                    _json_dump_value(previous_values),
                    _json_dump_value(new_values),
                    _json_dumps(mutation_payload),
                    now,
                    now,
                ),
            )
            conn.execute(
                """
                UPDATE sink_attempts
                SET state = ?,
                    payload_json = ?,
                    updated_at = ?
                WHERE attempt_id = ? AND contact_id = ?
                """,
                (
                    normalized_state,
                    _json_dumps(payload),
                    now,
                    attempt_id,
                    contact_id,
                ),
            )
        return {
            "mutation": self.get_mutation(mutation_id),
            "attempt": self.get_sink_attempt(attempt_id),
            "contact": self.get_contact(contact_id),
        }

    def get_sink_attempt(self, attempt_id: str) -> dict[str, Any]:
        self.initialize()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM sink_attempts WHERE attempt_id = ?",
                (attempt_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"sink attempt not found: {attempt_id}")
        return _row_with_payload(row)

    def override_route(
        self,
        *,
        contact_id: str,
        operator: str,
        selected_sinks: list[str],
        selected_sink_state: str = "dry_run",
        selected_target_profile: str = "",
        selected_target_tenant: str = "",
        route_candidate_state: str = "operator_overridden",
        reason: str = "",
        decision_id: str = "",
    ) -> dict[str, Any]:
        if not operator.strip():
            raise ValueError("contact route override requires an operator")
        normalized_sinks = sorted({str(sink).strip() for sink in selected_sinks if str(sink).strip()})
        invalid_sinks = [sink for sink in normalized_sinks if sink not in {"google_contacts", "odoo"}]
        if invalid_sinks:
            raise ValueError(f"unsupported route override sinks: {', '.join(invalid_sinks)}")
        if not normalized_sinks:
            raise ValueError("contact route override requires at least one selected sink")
        contact = self.get_contact(contact_id)
        routing_decisions = [
            row
            for row in list(contact.get("routing_decisions") or [])
            if isinstance(row, dict)
            and (not decision_id or str(row.get("decision_id") or "") == decision_id)
        ]
        if not routing_decisions:
            raise KeyError(f"routing decision not found for contact: {contact_id}")
        current = routing_decisions[-1]
        decision_id = str(current.get("decision_id") or decision_id)
        previous_values = _route_override_snapshot(current)
        new_values = {
            "selected_sinks": normalized_sinks,
            "selected_sink_state": selected_sink_state,
            "selected_target_profile": selected_target_profile.strip(),
            "selected_target_tenant": selected_target_tenant.strip(),
            "route_candidate_state": route_candidate_state,
            "readiness_blockers": [],
            "state": "ready_to_route",
        }
        now = utc_now()
        mutation_id = _stable_id(
            "mutation",
            contact_id,
            operator,
            "route_override",
            decision_id,
            _json_dump_value(new_values),
            now,
        )
        payload = dict(current.get("payload") or {})
        payload.setdefault("review_mutations", []).append(
            {
                "mutation_id": mutation_id,
                "action": "route_override",
                "operator": operator,
                "reason": reason,
                "previous_values": previous_values,
                "new_values": new_values,
                "created_at": now,
            }
        )
        payload["route_override"] = {
            "mutation_id": mutation_id,
            "operator": operator,
            "reason": reason,
            "previous_values": previous_values,
            "new_values": new_values,
            "created_at": now,
        }
        mutation_payload = {
            "action": "route_override",
            "operator": operator,
            "reason": reason,
            "decision_id": decision_id,
            "previous_values": previous_values,
            "new_values": new_values,
        }
        with self._connect() as conn:
            self._migrate(conn)
            conn.execute(
                """
                INSERT INTO contact_mutations (
                    mutation_id, contact_id, action, operator, previous_json,
                    new_json, payload_json, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    mutation_id,
                    contact_id,
                    "route_override",
                    operator,
                    _json_dump_value(previous_values),
                    _json_dump_value(new_values),
                    _json_dumps(mutation_payload),
                    now,
                    now,
                ),
            )
            conn.execute(
                """
                UPDATE routing_decisions
                SET state = ?,
                    tenant = ?,
                    selected_sinks_json = ?,
                    selected_sink_state = ?,
                    selected_target_profile = ?,
                    selected_target_tenant = ?,
                    route_candidate_state = ?,
                    readiness_blockers_json = ?,
                    payload_json = ?,
                    updated_at = ?
                WHERE decision_id = ? AND contact_id = ?
                """,
                (
                    new_values["state"],
                    ",".join(normalized_sinks),
                    _json_dump_value(normalized_sinks),
                    selected_sink_state,
                    selected_target_profile.strip(),
                    selected_target_tenant.strip(),
                    route_candidate_state,
                    _json_dump_value([]),
                    _json_dumps(payload),
                    now,
                    decision_id,
                    contact_id,
                ),
            )
        return {"mutation": self.get_mutation(mutation_id), "contact": self.get_contact(contact_id)}

    def record_review_recommendation(
        self,
        *,
        contact_id: str,
        source: str,
        category: str,
        recommendation: str,
        rationale: str = "",
        confidence: float | None = None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.initialize()
        contact = self.get_contact(contact_id)
        payload = dict(payload or {})
        now = utc_now()
        review_state_id = _stable_id(
            "review_state",
            contact_id,
            source,
            category,
            recommendation,
            _json_dumps(payload),
        )
        with self._connect() as conn:
            self._migrate(conn)
            conn.execute(
                """
                INSERT INTO contact_review_states (
                    review_state_id, contact_id, state, source, category,
                    recommendation, rationale, confidence, payload_json,
                    decided_by, decided_at, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, '', '', ?, ?)
                ON CONFLICT(review_state_id) DO UPDATE SET
                    contact_id = excluded.contact_id,
                    source = excluded.source,
                    category = excluded.category,
                    recommendation = excluded.recommendation,
                    rationale = excluded.rationale,
                    confidence = excluded.confidence,
                    payload_json = excluded.payload_json,
                    updated_at = excluded.updated_at
                """,
                (
                    review_state_id,
                    contact_id,
                    "proposed",
                    source,
                    category,
                    recommendation,
                    rationale,
                    confidence,
                    _json_dumps(
                        {
                            "evidence": payload,
                            "contact_source_run_id": contact["source_run_id"],
                            "contact_source_job_id": contact["source_job_id"],
                        }
                    ),
                    now,
                    now,
                ),
            )
        return self.get_review_state(review_state_id)

    def get_review_state(self, review_state_id: str) -> dict[str, Any]:
        self.initialize()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM contact_review_states WHERE review_state_id = ?",
                (review_state_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"review state not found: {review_state_id}")
        return _row_with_payload(row)

    def list_review_states(
        self,
        *,
        contact_id: str | None = None,
        state: str = "all",
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        self.initialize()
        clauses: list[str] = []
        params: list[Any] = []
        if contact_id:
            clauses.append("contact_id = ?")
            params.append(contact_id)
        if state != "all":
            clauses.append("state = ?")
            params.append(state)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM contact_review_states
                {where}
                ORDER BY updated_at DESC, review_state_id DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
        return [_row_with_payload(row) for row in rows]

    def decide_review_state(
        self,
        *,
        review_state_id: str,
        reviewer: str,
        decision: str,
        notes: str = "",
    ) -> dict[str, Any]:
        if decision not in {"accept", "reject"}:
            raise ValueError("review state decision must be accept or reject")
        current = self.get_review_state(review_state_id)
        payload = dict(current.get("payload") or {})
        payload["decision"] = {
            "decision": decision,
            "reviewer": reviewer,
            "notes": notes,
        }
        now = utc_now()
        state = "accepted" if decision == "accept" else "rejected"
        with self._connect() as conn:
            self._migrate(conn)
            conn.execute(
                """
                UPDATE contact_review_states
                SET state = ?, payload_json = ?, decided_by = ?, decided_at = ?, updated_at = ?
                WHERE review_state_id = ?
                """,
                (state, _json_dumps(payload), reviewer, now, now, review_state_id),
            )
        return self.get_review_state(review_state_id)

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

        child_rows = _reviewed_child_rows(artifacts)
        for row in child_rows:
            candidate_artifact = row["candidate_artifact"]
            candidate_path = Path(str(candidate_artifact.get("path") or ""))
            candidate = _read_json_file(candidate_path)
            if candidate is None:
                skipped_jobs += 1
                continue
            parent_job_id = str(row.get("parent_job_id") or candidate.get("lineage", {}).get("parent_job_id") or "")
            child_source_job_id = _child_source_job_id(parent_job_id, candidate)
            job = dict(jobs.get(parent_job_id, {}))
            if row.get("candidate_id"):
                job["child_candidate_id"] = row["candidate_id"]
            if row.get("work_item_id"):
                job["child_work_item_id"] = row["work_item_id"]
            contact_id = self.upsert_contact_from_candidate(
                run_id=run_id,
                job_id=child_source_job_id,
                candidate=candidate,
                artifact_path=candidate_path,
                job=job,
            )
            projected_contacts += 1
            projected_extraction_attempts += self.upsert_extraction_attempt(
                contact_id=contact_id,
                run_id=run_id,
                job_id=child_source_job_id,
                artifact_path=candidate_path,
                candidate_kind=str(candidate_artifact.get("kind") or "reviewed_child_contact"),
                job=job,
            )
            projected_assets += self.upsert_assets_for_job(
                contact_id=contact_id,
                run_id=run_id,
                job_id=child_source_job_id,
                artifacts=row["artifacts"],
                job=job,
            )
            projected_routing_decisions += self.upsert_routing_decision_for_job(
                contact_id=contact_id,
                run_id=run_id,
                job_id=child_source_job_id,
                artifacts=row["artifacts"],
                job=job,
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
            "parent_job_id": str((job or {}).get("job_id") or ""),
            "child_candidate_id": str((job or {}).get("child_candidate_id") or ""),
            "child_work_item_id": str((job or {}).get("child_work_item_id") or ""),
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
            state = _enrichment_state(kind, payload)
            rows.append(
                (
                    _stable_id("enrich", run_id, job_id, kind, str(path)),
                    contact_id,
                    provider,
                    state,
                    _json_dumps(_enrichment_projection_payload(kind, artifact, payload)),
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
        sink_lookup_artifact = artifacts.get("sink_lookup_plan")
        duplicate_artifact = artifacts.get("duplicate_assessment") or artifacts.get("downstream_duplicate_assessment")
        sink_payloads = _read_json_file(Path(str((sink_payload_artifact or {}).get("path") or ""))) or {}
        sink_lookup_plan = _read_json_file(Path(str((sink_lookup_artifact or {}).get("path") or ""))) or {}
        duplicate = _read_json_file(Path(str((duplicate_artifact or {}).get("path") or ""))) or {}
        payload_rows = sink_payloads.get("payloads") if isinstance(sink_payloads.get("payloads"), list) else []
        sinks = sorted({str(row.get("sink") or "") for row in payload_rows if isinstance(row, dict) and row.get("sink")})
        selected_sink_state, selected_target_profile, selected_target_tenant = _selected_route_metadata(payload_rows)
        route_candidate_state, readiness_blockers, odollo_route_candidates = _route_candidate_metadata(
            payload_rows=payload_rows,
            lookup_plan=sink_lookup_plan,
        )
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
            "sink_lookup_plan": sink_lookup_plan,
            "odollo_route_candidates": odollo_route_candidates,
            "route_candidate_state": route_candidate_state,
            "readiness_blockers": readiness_blockers,
            "duplicate_assessment": duplicate,
            "source_artifacts": {
                "sink_payloads": sink_payload_artifact,
                "sink_lookup_plan": sink_lookup_artifact,
                "duplicate_assessment": duplicate_artifact,
            },
        }
        now = utc_now()
        with self._connect() as conn:
            self._migrate(conn)
            conn.execute(
                """
                INSERT INTO routing_decisions (
                    decision_id, contact_id, tenant, state, selected_sinks_json,
                    selected_sink_state, selected_target_profile, selected_target_tenant,
                    route_candidate_state, readiness_blockers_json, payload_json,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(decision_id) DO UPDATE SET
                    contact_id = excluded.contact_id,
                    tenant = excluded.tenant,
                    state = excluded.state,
                    selected_sinks_json = excluded.selected_sinks_json,
                    selected_sink_state = excluded.selected_sink_state,
                    selected_target_profile = excluded.selected_target_profile,
                    selected_target_tenant = excluded.selected_target_tenant,
                    route_candidate_state = excluded.route_candidate_state,
                    readiness_blockers_json = excluded.readiness_blockers_json,
                    payload_json = excluded.payload_json,
                    updated_at = excluded.updated_at
                """,
                (
                    _stable_id("route", run_id, job_id),
                    contact_id,
                    ",".join(sinks) if sinks else "unassigned",
                    state,
                    _json_dump_value(sinks),
                    selected_sink_state,
                    selected_target_profile,
                    selected_target_tenant,
                    route_candidate_state,
                    _json_dump_value(readiness_blockers),
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
                selected_sinks_json TEXT NOT NULL DEFAULT '[]',
                selected_sink_state TEXT NOT NULL DEFAULT 'none',
                selected_target_profile TEXT NOT NULL DEFAULT '',
                selected_target_tenant TEXT NOT NULL DEFAULT '',
                route_candidate_state TEXT NOT NULL DEFAULT 'none',
                readiness_blockers_json TEXT NOT NULL DEFAULT '[]',
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

            CREATE TABLE IF NOT EXISTS contact_mutations (
                mutation_id TEXT PRIMARY KEY,
                contact_id TEXT NOT NULL,
                action TEXT NOT NULL,
                operator TEXT NOT NULL,
                previous_json TEXT NOT NULL,
                new_json TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(contact_id) REFERENCES contacts(contact_id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS contact_review_states (
                review_state_id TEXT PRIMARY KEY,
                contact_id TEXT NOT NULL,
                state TEXT NOT NULL,
                source TEXT NOT NULL,
                category TEXT NOT NULL,
                recommendation TEXT NOT NULL,
                rationale TEXT NOT NULL DEFAULT '',
                confidence REAL,
                payload_json TEXT NOT NULL,
                decided_by TEXT NOT NULL DEFAULT '',
                decided_at TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(contact_id) REFERENCES contacts(contact_id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_contacts_source ON contacts(source_run_id, source_job_id);
            CREATE INDEX IF NOT EXISTS idx_contacts_email ON contacts(email);
            CREATE INDEX IF NOT EXISTS idx_assets_contact ON card_assets(contact_id);
            CREATE INDEX IF NOT EXISTS idx_extraction_contact ON extraction_attempts(contact_id);
            CREATE INDEX IF NOT EXISTS idx_routing_contact ON routing_decisions(contact_id);
            CREATE INDEX IF NOT EXISTS idx_contact_mutations_contact ON contact_mutations(contact_id);
            CREATE INDEX IF NOT EXISTS idx_review_states_contact ON contact_review_states(contact_id);
            CREATE INDEX IF NOT EXISTS idx_review_states_state ON contact_review_states(state);
            """
        )
        _ensure_columns(
            conn,
            "routing_decisions",
            {
                "selected_sinks_json": "TEXT NOT NULL DEFAULT '[]'",
                "selected_sink_state": "TEXT NOT NULL DEFAULT 'none'",
                "selected_target_profile": "TEXT NOT NULL DEFAULT ''",
                "selected_target_tenant": "TEXT NOT NULL DEFAULT ''",
                "route_candidate_state": "TEXT NOT NULL DEFAULT 'none'",
                "readiness_blockers_json": "TEXT NOT NULL DEFAULT '[]'",
            },
        )
        _backfill_selected_route_metadata(conn)
        _backfill_route_readiness_metadata(conn)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_routing_selected_state ON routing_decisions(selected_sink_state)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_routing_route_candidate_state ON routing_decisions(route_candidate_state)"
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


def _json_dump_value(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _json_loads(value: str) -> dict[str, Any]:
    payload = json.loads(value)
    return payload if isinstance(payload, dict) else {}


def _row_with_payload(row: sqlite3.Row) -> dict[str, Any]:
    payload = dict(row)
    payload["payload"] = _json_loads(payload.pop("payload_json"))
    if "selected_sinks_json" in payload:
        payload["selected_sinks"] = _json_load_list(str(payload.pop("selected_sinks_json") or "[]"))
    if "readiness_blockers_json" in payload:
        payload["readiness_blockers"] = _json_load_list(str(payload.pop("readiness_blockers_json") or "[]"))
    return payload


def _route_override_snapshot(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "decision_id": row.get("decision_id"),
        "state": row.get("state"),
        "selected_sinks": list(row.get("selected_sinks") or []),
        "selected_sink_state": row.get("selected_sink_state"),
        "selected_target_profile": row.get("selected_target_profile"),
        "selected_target_tenant": row.get("selected_target_tenant"),
        "route_candidate_state": row.get("route_candidate_state"),
        "readiness_blockers": list(row.get("readiness_blockers") or []),
    }


def _crop_decision_snapshot(row: dict[str, Any]) -> dict[str, Any]:
    payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
    crop_decision = payload.get("crop_decision") if isinstance(payload.get("crop_decision"), dict) else {}
    return {
        "asset_id": row.get("asset_id"),
        "asset_kind": row.get("asset_kind"),
        "path_ref": row.get("path_ref"),
        "sha256": row.get("sha256"),
        "decision": crop_decision.get("decision", ""),
        "selected_crop_path": crop_decision.get("selected_crop_path", ""),
        "selected_crop_sha256": crop_decision.get("selected_crop_sha256", ""),
        "decided_by": crop_decision.get("decided_by", ""),
        "decided_at": crop_decision.get("decided_at", ""),
    }


def _contact_spec_snapshot(contact: dict[str, Any]) -> dict[str, str]:
    payload = contact.get("payload") if isinstance(contact.get("payload"), dict) else {}
    contact_spec = payload.get("contact_spec") if isinstance(payload.get("contact_spec"), dict) else {}
    return {
        "full_name": str(contact_spec.get("full_name") or contact.get("display_name") or ""),
        "organization": str(contact_spec.get("organization") or contact.get("organization") or ""),
        "title": str(contact_spec.get("title") or ""),
        "email": str(contact_spec.get("email") or contact.get("email") or ""),
        "phone": str(contact_spec.get("phone") or contact.get("phone") or ""),
        "website": str(contact_spec.get("website") or ""),
        "notes": str(contact_spec.get("notes") or ""),
    }


def _enrichment_merge_proposals(attempt: dict[str, Any]) -> list[dict[str, Any]]:
    payload = attempt.get("payload") if isinstance(attempt.get("payload"), dict) else {}
    source_payload = payload.get("payload") if isinstance(payload.get("payload"), dict) else {}
    proposals = source_payload.get("merge_proposals")
    if isinstance(proposals, list):
        return [proposal for proposal in proposals if isinstance(proposal, dict)]
    review = payload.get("review") if isinstance(payload.get("review"), dict) else {}
    review_proposals = review.get("proposals")
    if isinstance(review_proposals, list):
        rows: list[dict[str, Any]] = []
        for proposal in review_proposals:
            if not isinstance(proposal, dict):
                continue
            rows.append(
                {
                    "field": proposal.get("field"),
                    "value": proposal.get("value"),
                    "source": proposal.get("source") or attempt.get("provider"),
                }
            )
        return rows
    return []


def _sink_approval_snapshot(row: dict[str, Any]) -> dict[str, Any]:
    payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
    sink_approval = payload.get("sink_approval") if isinstance(payload.get("sink_approval"), dict) else {}
    return {
        "attempt_id": row.get("attempt_id"),
        "sink": row.get("sink"),
        "state": row.get("state"),
        "approval_state": sink_approval.get("approval_state", ""),
        "scope": sink_approval.get("scope", ""),
        "approved_by": sink_approval.get("approved_by", ""),
        "approved_at": sink_approval.get("approved_at", ""),
    }


def _ensure_columns(conn: sqlite3.Connection, table: str, columns: dict[str, str]) -> None:
    existing = {str(row["name"]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    for name, definition in columns.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")


def _selected_route_metadata(payload_rows: list[Any]) -> tuple[str, str, str]:
    rows = [row for row in payload_rows if isinstance(row, dict) and str(row.get("sink") or "").strip()]
    if not rows:
        return "none", "", ""
    selected_state = "dry_run" if all(bool(row.get("dry_run", True)) for row in rows) else "planned"
    target_profile = ""
    target_tenant = ""
    for row in rows:
        readiness = row.get("readiness") if isinstance(row.get("readiness"), dict) else {}
        details = readiness.get("details") if isinstance(readiness.get("details"), dict) else {}
        sink = str(row.get("sink") or "")
        if sink == "google_contacts" and not target_profile:
            target_profile = str(details.get("target_account") or details.get("profile") or "").strip()
        elif sink == "odoo" and not target_tenant:
            target_tenant = str(details.get("tenant") or details.get("target_tenant") or "").strip()
    return selected_state, target_profile, target_tenant


def _route_candidate_metadata(
    *,
    payload_rows: list[Any],
    lookup_plan: dict[str, Any],
) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
    selected_sinks = {str(row.get("sink") or "") for row in payload_rows if isinstance(row, dict)}
    if "odoo" not in selected_sinks:
        return "none", [], []
    lookups = lookup_plan.get("lookups") if isinstance(lookup_plan.get("lookups"), list) else []
    candidates: list[dict[str, Any]] = []
    blockers: list[dict[str, Any]] = []
    for lookup in lookups:
        if not isinstance(lookup, dict) or str(lookup.get("sink") or "") != "odoo":
            continue
        tenant_readiness = (
            lookup.get("tenant_readiness") if isinstance(lookup.get("tenant_readiness"), dict) else {}
        )
        duplicate_gate = (
            lookup.get("duplicate_lookup_gate") if isinstance(lookup.get("duplicate_lookup_gate"), dict) else {}
        )
        candidate_blockers = _route_blockers_from_packets(
            tenant_readiness=tenant_readiness,
            duplicate_gate=duplicate_gate,
        )
        tenant = str(tenant_readiness.get("tenant") or _lookup_tenant(lookup) or "").strip()
        candidate_state = _odollo_candidate_state(
            tenant_readiness=tenant_readiness,
            duplicate_gate=duplicate_gate,
            blockers=candidate_blockers,
        )
        candidates.append(
            {
                "sink": "odoo",
                "tenant": tenant,
                "state": candidate_state,
                "tenant_readiness": tenant_readiness,
                "duplicate_lookup_gate": duplicate_gate,
                "readiness_blockers": candidate_blockers,
            }
        )
        blockers.extend(candidate_blockers)
    if candidates:
        return _summarize_route_candidate_state(candidates), blockers, candidates
    return "missing_readiness_packet", [
        {
            "source": "contact_store_projection",
            "code": "missing_odollo_lookup_plan",
            "category": "missing_config",
            "reason": "Odoo route candidate is missing sink_lookup_plan readiness evidence",
        }
    ], []


def _route_blockers_from_packets(
    *,
    tenant_readiness: dict[str, Any],
    duplicate_gate: dict[str, Any],
) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    for source, packet in (
        ("tenant_readiness", tenant_readiness),
        ("duplicate_lookup_gate", duplicate_gate),
    ):
        for blocker in packet.get("blockers") if isinstance(packet.get("blockers"), list) else []:
            if isinstance(blocker, dict):
                row = dict(blocker)
                row["source"] = source
                blockers.append(row)
    return blockers


def _lookup_tenant(lookup: dict[str, Any]) -> str:
    readiness = lookup.get("readiness") if isinstance(lookup.get("readiness"), dict) else {}
    details = readiness.get("details") if isinstance(readiness.get("details"), dict) else {}
    return str(details.get("tenant") or details.get("target_tenant") or "")


def _odollo_candidate_state(
    *,
    tenant_readiness: dict[str, Any],
    duplicate_gate: dict[str, Any],
    blockers: list[dict[str, Any]],
) -> str:
    tenant_state = str(tenant_readiness.get("state") or "")
    if tenant_state in {"missing_config", "blocked_tenant"}:
        return tenant_state
    if any(str(blocker.get("category") or "") == "duplicate_risk" for blocker in blockers):
        return "duplicate_lookup_blocked"
    duplicate_state = str(duplicate_gate.get("state") or "")
    if duplicate_state == "pilot_ready":
        return "pilot_ready"
    return tenant_state or duplicate_state or "unknown"


def _summarize_route_candidate_state(candidates: list[dict[str, Any]]) -> str:
    states = {str(candidate.get("state") or "") for candidate in candidates}
    for state in ("missing_config", "blocked_tenant", "missing_readiness_packet", "duplicate_lookup_blocked"):
        if state in states:
            return state
    if states == {"pilot_ready"}:
        return "pilot_ready"
    return sorted(states)[0] if states else "none"


def _backfill_selected_route_metadata(conn: sqlite3.Connection) -> None:
    rows = conn.execute(
        """
        SELECT decision_id, payload_json
        FROM routing_decisions
        WHERE selected_sinks_json = '[]' AND selected_sink_state = 'none'
        """
    ).fetchall()
    for row in rows:
        payload = _json_loads(str(row["payload_json"] or "{}"))
        payload_sinks = [str(sink) for sink in payload.get("sinks") or [] if str(sink).strip()]
        sink_payloads = payload.get("sink_payloads") if isinstance(payload.get("sink_payloads"), dict) else {}
        payload_rows = sink_payloads.get("payloads") if isinstance(sink_payloads.get("payloads"), list) else []
        if not payload_rows and payload_sinks:
            payload_rows = [{"sink": sink, "dry_run": True} for sink in payload_sinks]
        selected_sinks = sorted(
            {
                str(payload_row.get("sink") or "")
                for payload_row in payload_rows
                if isinstance(payload_row, dict) and payload_row.get("sink")
            }
        )
        selected_sink_state, selected_target_profile, selected_target_tenant = _selected_route_metadata(payload_rows)
        if not selected_sinks:
            continue
        conn.execute(
            """
            UPDATE routing_decisions
            SET selected_sinks_json = ?,
                selected_sink_state = ?,
                selected_target_profile = ?,
                selected_target_tenant = ?
            WHERE decision_id = ?
            """,
            (
                _json_dump_value(selected_sinks),
                selected_sink_state,
                selected_target_profile,
                selected_target_tenant,
                row["decision_id"],
            ),
        )


def _backfill_route_readiness_metadata(conn: sqlite3.Connection) -> None:
    rows = conn.execute(
        """
        SELECT decision_id, payload_json
        FROM routing_decisions
        WHERE route_candidate_state = 'none' AND readiness_blockers_json = '[]'
        """
    ).fetchall()
    for row in rows:
        payload = _json_loads(str(row["payload_json"] or "{}"))
        sink_payloads = payload.get("sink_payloads") if isinstance(payload.get("sink_payloads"), dict) else {}
        payload_rows = sink_payloads.get("payloads") if isinstance(sink_payloads.get("payloads"), list) else []
        lookup_plan = payload.get("sink_lookup_plan") if isinstance(payload.get("sink_lookup_plan"), dict) else {}
        route_candidate_state, readiness_blockers, odollo_route_candidates = _route_candidate_metadata(
            payload_rows=payload_rows,
            lookup_plan=lookup_plan,
        )
        if route_candidate_state == "none" and not readiness_blockers:
            continue
        payload["route_candidate_state"] = route_candidate_state
        payload["readiness_blockers"] = readiness_blockers
        payload["odollo_route_candidates"] = odollo_route_candidates
        conn.execute(
            """
            UPDATE routing_decisions
            SET route_candidate_state = ?,
                readiness_blockers_json = ?,
                payload_json = ?
            WHERE decision_id = ?
            """,
            (
                route_candidate_state,
                _json_dump_value(readiness_blockers),
                _json_dumps(payload),
                row["decision_id"],
            ),
        )


def _json_load_list(value: str) -> list[Any]:
    try:
        payload = json.loads(value)
    except json.JSONDecodeError:
        return []
    return payload if isinstance(payload, list) else []


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
        if kind not in {"contact_candidate", "reviewed_contact", "reviewed_child_contact"}:
            continue
        job_id = str(artifact.get("job_id") or "")
        path = Path(str(artifact.get("path") or ""))
        payload = _read_json_file(path)
        if payload is None:
            unreadable.add(job_id)
            continue
        if kind == "reviewed_child_contact":
            job_id = _child_source_job_id(job_id, payload)
        expected.add(job_id)
    return expected, unreadable


def _reviewed_child_rows(artifacts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    review_artifacts_by_candidate: dict[str, dict[str, dict[str, Any]]] = {}
    reviewed_rows: list[dict[str, Any]] = []
    for artifact in artifacts:
        kind = str(artifact.get("kind") or "")
        if kind not in {"child_review_submission", "child_contact_review_result", "reviewed_child_contact"}:
            continue
        payload = _read_json_file(Path(str(artifact.get("path") or ""))) or {}
        candidate_id = str(payload.get("candidate_id") or _candidate_id_from_reviewed_child(payload) or "")
        if not candidate_id:
            continue
        review_artifacts_by_candidate.setdefault(candidate_id, {})[kind] = artifact
        if kind == "reviewed_child_contact":
            reviewed_rows.append(
                {
                    "candidate_id": candidate_id,
                    "work_item_id": _work_item_id_from_child_payload(payload),
                    "parent_job_id": str(artifact.get("job_id") or payload.get("lineage", {}).get("parent_job_id") or ""),
                    "candidate_artifact": artifact,
                }
            )
    rows: list[dict[str, Any]] = []
    for row in reviewed_rows:
        candidate_id = str(row["candidate_id"])
        row["artifacts"] = dict(review_artifacts_by_candidate.get(candidate_id) or {})
        row["artifacts"]["reviewed_child_contact"] = row["candidate_artifact"]
        rows.append(row)
    return rows


def _candidate_id_from_reviewed_child(payload: dict[str, Any]) -> str:
    lineage = payload.get("lineage") if isinstance(payload.get("lineage"), dict) else {}
    return str(lineage.get("candidate_id") or "")


def _work_item_id_from_child_payload(payload: dict[str, Any]) -> str:
    lineage = payload.get("lineage") if isinstance(payload.get("lineage"), dict) else {}
    return str(payload.get("work_item_id") or lineage.get("work_item_id") or "")


def _child_source_job_id(parent_job_id: str, candidate: dict[str, Any]) -> str:
    candidate_id = _candidate_id_from_reviewed_child(candidate) or str(candidate.get("candidate_id") or "")
    return f"{parent_job_id}::{candidate_id}" if candidate_id else parent_job_id


def _enrichment_provider(kind: str, payload: dict[str, Any]) -> str:
    provider = str(payload.get("provider") or "").strip()
    if provider:
        return provider
    source_provider = str(payload.get("source_provider") or "").strip()
    if source_provider:
        return source_provider
    if "public_web" in kind:
        return "public_web"
    if "provider" in kind:
        return str(payload.get("provider_name") or "paid_provider")
    return "unknown"


def _enrichment_state(kind: str, payload: dict[str, Any]) -> str:
    if kind == "enrichment_proposal_review":
        accepted = int(payload.get("accepted_count") or 0)
        rejected = int(payload.get("rejected_count") or 0)
        if accepted and rejected:
            return "reviewed"
        if accepted:
            return "accepted"
        if rejected:
            return "rejected"
        return "reviewed"
    if kind == "enrichment_merge_review":
        applied = payload.get("applied") if isinstance(payload.get("applied"), list) else []
        skipped = payload.get("skipped") if isinstance(payload.get("skipped"), list) else []
        if applied and skipped:
            return "reviewed"
        if applied:
            return "accepted"
        if skipped:
            return "rejected"
        return "reviewed"
    return str(payload.get("state") or payload.get("status") or "recorded")


def _enrichment_projection_payload(
    kind: str,
    artifact: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    projection = {"artifact": artifact, "payload": payload}
    if kind == "enrichment_proposal_review":
        projection["review"] = {
            "reviewer": payload.get("reviewer"),
            "source_provider": payload.get("source_provider"),
            "source_result_schema": payload.get("source_result_schema"),
            "approved_fields": list(payload.get("approved_fields") or []),
            "proposal_count": int(payload.get("proposal_count") or 0),
            "accepted_count": int(payload.get("accepted_count") or 0),
            "rejected_count": int(payload.get("rejected_count") or 0),
            "proposals": list(payload.get("proposals") or []),
        }
    elif kind == "enrichment_merge_review":
        applied = payload.get("applied") if isinstance(payload.get("applied"), list) else []
        skipped = payload.get("skipped") if isinstance(payload.get("skipped"), list) else []
        projection["review"] = {
            "reviewer": payload.get("reviewer"),
            "approved_fields": list(payload.get("approved_fields") or []),
            "applied_count": len(applied),
            "skipped_count": len(skipped),
            "applied": list(applied),
            "skipped": list(skipped),
        }
    return projection


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

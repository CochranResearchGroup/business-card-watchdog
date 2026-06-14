from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from .config import AppConfig
from .sinks import canonical_contact_fingerprint


DuplicateState = Literal["no_match", "possible_duplicate", "strong_duplicate", "same_card_reprocess"]
DUPLICATE_RESOLUTION_INDEX_SCHEMA = "business-card-watchdog.duplicate-resolution-index.v1"


@dataclass(frozen=True)
class IdentityRecord:
    job_id: str
    run_id: str
    image_path: str
    fingerprint: str
    email: str = ""
    phone: str = ""
    full_name: str = ""
    organization: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "IdentityRecord":
        return cls(
            job_id=str(payload.get("job_id") or ""),
            run_id=str(payload.get("run_id") or ""),
            image_path=str(payload.get("image_path") or ""),
            fingerprint=str(payload.get("fingerprint") or ""),
            email=str(payload.get("email") or ""),
            phone=str(payload.get("phone") or ""),
            full_name=str(payload.get("full_name") or ""),
            organization=str(payload.get("organization") or ""),
        )


@dataclass(frozen=True)
class DuplicateResolutionRecord:
    job_id: str
    run_id: str
    image_path: str
    decision: str
    reviewer: str
    reason: str
    current_fingerprint: str
    target_identity: str = ""
    match_fingerprints: list[str] = field(default_factory=list)
    match_keys: list[str] = field(default_factory=list)
    schema: str = DUPLICATE_RESOLUTION_INDEX_SCHEMA

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "DuplicateResolutionRecord":
        return cls(
            job_id=str(payload.get("job_id") or ""),
            run_id=str(payload.get("run_id") or ""),
            image_path=str(payload.get("image_path") or ""),
            decision=str(payload.get("decision") or ""),
            reviewer=str(payload.get("reviewer") or ""),
            reason=str(payload.get("reason") or ""),
            current_fingerprint=str(payload.get("current_fingerprint") or ""),
            target_identity=str(payload.get("target_identity") or ""),
            match_fingerprints=[str(value) for value in list(payload.get("match_fingerprints") or [])],
            match_keys=[str(value) for value in list(payload.get("match_keys") or [])],
            schema=str(payload.get("schema") or DUPLICATE_RESOLUTION_INDEX_SCHEMA),
        )


@dataclass(frozen=True)
class DuplicateAssessment:
    schema: str = "business-card-watchdog.duplicate-assessment.v1"
    state: DuplicateState = "no_match"
    reason: str = "no prior identity match"
    fingerprint: str = ""
    matches: list[dict[str, Any]] = field(default_factory=list)

    @property
    def blocks_routing(self) -> bool:
        return self.state in {"possible_duplicate", "strong_duplicate", "same_card_reprocess"}

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class IdentityIndex:
    def __init__(self, config: AppConfig) -> None:
        self.index_dir = config.data_dir / "identity"
        self.index_path = self.index_dir / "contact-identities.jsonl"
        self.resolution_path = self.index_dir / "duplicate-resolutions.jsonl"

    def records(self) -> list[IdentityRecord]:
        if not self.index_path.exists():
            return []
        return [
            IdentityRecord.from_dict(json.loads(line))
            for line in self.index_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def append(self, record: IdentityRecord) -> None:
        if any(
            existing.job_id == record.job_id and existing.run_id == record.run_id
            for existing in self.records()
        ):
            return
        self.index_dir.mkdir(parents=True, exist_ok=True)
        with self.index_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record.to_dict(), sort_keys=True) + "\n")

    def duplicate_resolutions(self) -> list[DuplicateResolutionRecord]:
        if not self.resolution_path.exists():
            return []
        return [
            DuplicateResolutionRecord.from_dict(json.loads(line))
            for line in self.resolution_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def append_duplicate_resolution(self, record: DuplicateResolutionRecord) -> None:
        if any(
            existing.job_id == record.job_id
            and existing.run_id == record.run_id
            and existing.decision == record.decision
            for existing in self.duplicate_resolutions()
        ):
            return
        self.index_dir.mkdir(parents=True, exist_ok=True)
        with self.resolution_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record.to_dict(), sort_keys=True) + "\n")


def assess_duplicate(
    config: AppConfig,
    *,
    spec: dict[str, Any],
    job_id: str,
    run_id: str,
    image_path: str,
) -> DuplicateAssessment:
    current = identity_record_from_spec(spec, job_id=job_id, run_id=run_id, image_path=image_path)
    index = IdentityIndex(config)
    resolutions = index.duplicate_resolutions()
    matches: list[dict[str, Any]] = []
    for record in index.records():
        if record.job_id == job_id and record.run_id == run_id:
            continue
        basis = _match_basis(current, record)
        if basis and not _match_suppressed_by_resolution(current, record, resolutions):
            matches.append({"basis": basis, "record": record.to_dict()})

    if not matches:
        return DuplicateAssessment(fingerprint=current.fingerprint)

    if any(match["basis"] == "same_image_path" for match in matches):
        return DuplicateAssessment(
            state="same_card_reprocess",
            reason="same image path was already indexed",
            fingerprint=current.fingerprint,
            matches=matches,
        )
    if any(match["basis"] in {"fingerprint", "email", "phone"} for match in matches):
        return DuplicateAssessment(
            state="strong_duplicate",
            reason="strong identity key matched prior contact",
            fingerprint=current.fingerprint,
            matches=matches,
        )
    return DuplicateAssessment(
        state="possible_duplicate",
        reason="name and organization matched prior contact",
        fingerprint=current.fingerprint,
        matches=matches,
    )


def assess_downstream_lookup_result(lookup_result: dict[str, Any]) -> DuplicateAssessment:
    matches = [
        {
            "basis": _downstream_match_basis(match),
            "sink": result.get("sink"),
            "resource_id": match.get("resource_id"),
            "confidence": match.get("confidence", 0),
            "display": match.get("display", ""),
            "match_basis": list(match.get("basis") or []),
        }
        for result in list(lookup_result.get("results") or [])
        for match in list(result.get("matches") or [])
    ]
    if not matches:
        return DuplicateAssessment(
            state="no_match",
            reason="no downstream sink match",
            fingerprint=str(lookup_result.get("fingerprint") or ""),
            matches=[],
        )
    if any(match["basis"] in {"downstream_fingerprint", "downstream_email", "downstream_phone"} for match in matches):
        return DuplicateAssessment(
            state="strong_duplicate",
            reason="strong downstream sink identity key matched",
            fingerprint=str(lookup_result.get("fingerprint") or ""),
            matches=matches,
        )
    return DuplicateAssessment(
        state="possible_duplicate",
        reason="downstream sink match requires review",
        fingerprint=str(lookup_result.get("fingerprint") or ""),
        matches=matches,
    )


def remember_identity(
    config: AppConfig,
    *,
    spec: dict[str, Any],
    job_id: str,
    run_id: str,
    image_path: str,
) -> IdentityRecord:
    record = identity_record_from_spec(spec, job_id=job_id, run_id=run_id, image_path=image_path)
    IdentityIndex(config).append(record)
    return record


def remember_duplicate_resolution(
    config: AppConfig,
    *,
    spec: dict[str, Any],
    resolution: dict[str, Any],
    job_id: str,
    run_id: str,
    image_path: str,
) -> DuplicateResolutionRecord:
    assessment = (
        resolution.get("duplicate_assessment")
        if isinstance(resolution.get("duplicate_assessment"), dict)
        else {}
    )
    current = identity_record_from_spec(spec, job_id=job_id, run_id=run_id, image_path=image_path)
    record = DuplicateResolutionRecord(
        job_id=job_id,
        run_id=run_id,
        image_path=image_path,
        decision=str(resolution.get("decision") or ""),
        reviewer=str(resolution.get("reviewer") or ""),
        reason=str(resolution.get("reason") or ""),
        current_fingerprint=current.fingerprint,
        target_identity=str(resolution.get("target_identity") or ""),
        match_fingerprints=_assessment_match_fingerprints(assessment),
        match_keys=_assessment_match_keys(assessment),
    )
    IdentityIndex(config).append_duplicate_resolution(record)
    return record


def identity_record_from_spec(
    spec: dict[str, Any],
    *,
    job_id: str,
    run_id: str,
    image_path: str,
) -> IdentityRecord:
    return IdentityRecord(
        job_id=job_id,
        run_id=run_id,
        image_path=image_path,
        fingerprint=canonical_contact_fingerprint(spec),
        email=_clean(spec.get("email")).lower(),
        phone=_digits(spec.get("phone")),
        full_name=_clean(spec.get("full_name")).lower(),
        organization=_clean(spec.get("organization")).lower(),
    )


def _match_basis(current: IdentityRecord, prior: IdentityRecord) -> str | None:
    if current.image_path and current.image_path == prior.image_path:
        return "same_image_path"
    if current.fingerprint and current.fingerprint == prior.fingerprint:
        return "fingerprint"
    if current.email and current.email == prior.email:
        return "email"
    if current.phone and current.phone == prior.phone and (
        not current.email or not prior.email or current.full_name == prior.full_name
    ):
        return "phone"
    if (
        current.full_name
        and current.organization
        and current.full_name == prior.full_name
        and current.organization == prior.organization
    ):
        return "name_organization"
    return None


def _match_suppressed_by_resolution(
    current: IdentityRecord,
    prior: IdentityRecord,
    resolutions: list[DuplicateResolutionRecord],
) -> bool:
    current_keys = _identity_keys(current)
    prior_keys = _identity_keys(prior)
    for resolution in resolutions:
        if resolution.decision != "create_new":
            continue
        if resolution.current_fingerprint not in {current.fingerprint, prior.fingerprint}:
            continue
        if resolution.match_fingerprints and (
            current.fingerprint in resolution.match_fingerprints
            or prior.fingerprint in resolution.match_fingerprints
        ):
            return True
        if resolution.match_keys and (current_keys | prior_keys) & set(resolution.match_keys):
            return True
    return False


def _assessment_match_fingerprints(assessment: dict[str, Any]) -> list[str]:
    fingerprints = []
    for match in list(assessment.get("matches") or []):
        record = match.get("record") if isinstance(match.get("record"), dict) else {}
        fingerprint = str(record.get("fingerprint") or "")
        if fingerprint:
            fingerprints.append(fingerprint)
    return sorted(set(fingerprints))


def _assessment_match_keys(assessment: dict[str, Any]) -> list[str]:
    keys: list[str] = []
    for match in list(assessment.get("matches") or []):
        basis = str(match.get("basis") or match.get("match_type") or "")
        record = match.get("record") if isinstance(match.get("record"), dict) else {}
        if basis == "email" and record.get("email"):
            keys.append(f"email:{record['email']}")
        if basis == "phone" and record.get("phone"):
            keys.append(f"phone:{record['phone']}")
        if basis == "name_organization" and record.get("full_name") and record.get("organization"):
            keys.append(f"name_org:{record['full_name']}|{record['organization']}")
        if match.get("serialization_key"):
            keys.append(str(match["serialization_key"]))
        if match.get("target_identity"):
            keys.append(str(match["target_identity"]))
    return sorted(set(keys))


def _identity_keys(record: IdentityRecord) -> set[str]:
    keys = {f"fingerprint:{record.fingerprint}"} if record.fingerprint else set()
    if record.email:
        keys.add(f"email:{record.email}")
    if record.phone:
        keys.add(f"phone:{record.phone}")
    if record.full_name and record.organization:
        keys.add(f"name_org:{record.full_name}|{record.organization}")
    return keys


def _downstream_match_basis(match: dict[str, Any]) -> str:
    basis = {str(value) for value in list(match.get("basis") or [])}
    if "fingerprint" in basis:
        return "downstream_fingerprint"
    if "email" in basis:
        return "downstream_email"
    if "phone" in basis:
        return "downstream_phone"
    return "downstream_match"


def _clean(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _digits(value: Any) -> str:
    return "".join(char for char in str(value or "") if char.isdigit() or char == "+")

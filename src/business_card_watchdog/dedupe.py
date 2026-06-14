from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from .config import AppConfig
from .sinks import canonical_contact_fingerprint


DuplicateState = Literal["no_match", "possible_duplicate", "strong_duplicate", "same_card_reprocess"]


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


def assess_duplicate(
    config: AppConfig,
    *,
    spec: dict[str, Any],
    job_id: str,
    run_id: str,
    image_path: str,
) -> DuplicateAssessment:
    current = identity_record_from_spec(spec, job_id=job_id, run_id=run_id, image_path=image_path)
    matches: list[dict[str, Any]] = []
    for record in IdentityIndex(config).records():
        if record.job_id == job_id and record.run_id == run_id:
            continue
        basis = _match_basis(current, record)
        if basis:
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

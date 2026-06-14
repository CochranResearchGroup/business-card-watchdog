from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4


RunState = Literal[
    "created",
    "discovering",
    "processing",
    "waiting_for_review",
    "routing",
    "completed",
    "failed",
    "cancelled",
]
JobState = Literal[
    "queued",
    "processing",
    "needs_review",
    "ready_to_route",
    "routed",
    "failed",
    "cancelled",
]
SinkActionState = Literal["planned", "dry_run", "ready", "written", "noop", "failed", "blocked"]


RUN_TRANSITIONS: dict[RunState, set[RunState]] = {
    "created": {"discovering", "failed", "cancelled"},
    "discovering": {"processing", "completed", "failed", "cancelled"},
    "processing": {"waiting_for_review", "routing", "completed", "failed", "cancelled"},
    "waiting_for_review": {"processing", "routing", "failed", "cancelled"},
    "routing": {"waiting_for_review", "completed", "failed", "cancelled"},
    "completed": set(),
    "failed": {"processing", "cancelled"},
    "cancelled": set(),
}

JOB_TRANSITIONS: dict[JobState, set[JobState]] = {
    "queued": {"processing", "failed", "cancelled"},
    "processing": {"needs_review", "ready_to_route", "failed", "cancelled"},
    "needs_review": {"processing", "ready_to_route", "failed", "cancelled"},
    "ready_to_route": {"needs_review", "routed", "failed", "cancelled"},
    "routed": set(),
    "failed": {"queued", "cancelled"},
    "cancelled": set(),
}


class InvalidStateTransition(ValueError):
    """Raised when a run or job attempts an illegal state transition."""


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


@dataclass
class CardJob:
    image_path: str
    job_id: str = field(default_factory=lambda: uuid4().hex)
    state: JobState = "queued"
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    artifact_dir: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def transition_to(self, state: JobState, *, error: str | None = None) -> None:
        if state == self.state:
            if error is not None:
                self.error = error
            self.updated_at = utc_now()
            return
        allowed = JOB_TRANSITIONS[self.state]
        if state not in allowed:
            raise InvalidStateTransition(f"job {self.job_id}: cannot transition {self.state} -> {state}")
        self.state = state
        self.error = error
        self.updated_at = utc_now()

    @classmethod
    def from_path(cls, image_path: Path) -> "CardJob":
        return cls(image_path=str(image_path))

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "CardJob":
        return cls(
            image_path=str(payload["image_path"]),
            job_id=str(payload["job_id"]),
            state=payload["state"],
            created_at=str(payload["created_at"]),
            updated_at=str(payload["updated_at"]),
            artifact_dir=payload.get("artifact_dir"),
            error=payload.get("error"),
        )


@dataclass
class RunRecord:
    run_id: str
    source: str
    dry_run: bool
    state: RunState = "created"
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    schema: str = "business-card-watchdog.run.v1"
    job_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def transition_to(self, state: RunState) -> None:
        if state == self.state:
            self.updated_at = utc_now()
            return
        allowed = RUN_TRANSITIONS[self.state]
        if state not in allowed:
            raise InvalidStateTransition(f"run {self.run_id}: cannot transition {self.state} -> {state}")
        self.state = state
        self.updated_at = utc_now()


@dataclass(frozen=True)
class ArtifactRecord:
    job_id: str
    kind: str
    path: str
    artifact_id: str = field(default_factory=lambda: uuid4().hex)
    created_at: str = field(default_factory=utc_now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SinkDecision:
    sinks: list[str]
    reason: str
    dry_run: bool = True
    state: SinkActionState = "planned"
    fingerprint: str | None = None
    matched_rule: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SkillRunResult:
    status: Literal["ok", "failed", "skipped"]
    artifact_dir: Path
    spec_path: Path | None = None
    review_path: Path | None = None
    stdout: str = ""
    stderr: str = ""
    error: str | None = None

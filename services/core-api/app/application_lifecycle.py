from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from .models import ApplicationEvent, ApplicationSession

ALLOWED_STATUSES = {
    "OPENED",
    "IN_PROGRESS",
    "SUBMITTED",
    "INTERVIEWING",
    "OFFER",
    "REJECTED",
    "ABANDONED",
}

TERMINAL_STATUSES = {"REJECTED", "ABANDONED"}
ACTIVE_STATUSES = ALLOWED_STATUSES - TERMINAL_STATUSES

STATUS_TRANSITIONS: dict[str, tuple[str, ...]] = {
    "OPENED": ("IN_PROGRESS", "SUBMITTED", "ABANDONED"),
    "IN_PROGRESS": ("SUBMITTED", "ABANDONED"),
    "SUBMITTED": ("INTERVIEWING", "OFFER", "REJECTED", "ABANDONED"),
    "INTERVIEWING": ("OFFER", "REJECTED", "ABANDONED"),
    "OFFER": ("ABANDONED",),
    "REJECTED": (),
    "ABANDONED": (),
}


@dataclass(frozen=True, slots=True)
class InvalidApplicationTransition(ValueError):
    current_status: str
    target_status: str
    allowed: tuple[str, ...]

    def __str__(self) -> str:
        return (
            f"Invalid application status transition {self.current_status} -> "
            f"{self.target_status}; allowed next statuses: {list(self.allowed)}"
        )


def allowed_next_statuses(status: str) -> tuple[str, ...]:
    return STATUS_TRANSITIONS.get(status, ())


def record_application_created(session: Session, record: ApplicationSession) -> None:
    session.add(
        ApplicationEvent(
            application_id=record.id,
            event_type="CREATED",
            from_status=None,
            to_status="OPENED",
            note=None,
        )
    )


def transition_application(
    session: Session,
    record: ApplicationSession,
    target_status: str,
    *,
    note: str | None = None,
) -> bool:
    """Apply one legal lifecycle transition and append an immutable event.

    Returns False for an idempotent same-status request and True when a
    transition was applied. The caller owns commit/rollback.
    """
    if target_status not in ALLOWED_STATUSES:
        raise ValueError(f"Unknown application status: {target_status}")
    if target_status == record.status:
        return False

    allowed = allowed_next_statuses(record.status)
    if target_status not in allowed:
        raise InvalidApplicationTransition(record.status, target_status, allowed)

    previous = record.status
    record.status = target_status
    normalized_note = note.strip() if note and note.strip() else None
    session.add(
        ApplicationEvent(
            application_id=record.id,
            event_type="STATUS_CHANGED",
            from_status=previous,
            to_status=target_status,
            note=normalized_note,
        )
    )
    return True

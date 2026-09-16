from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import SourceSnapshot, SourceSyncRun, utcnow


def latest_good_snapshot(session: Session, source_name: str) -> SourceSnapshot | None:
    return session.scalar(
        select(SourceSnapshot)
        .where(SourceSnapshot.source_name == source_name)
        .order_by(SourceSnapshot.id.desc())
        .limit(1)
    )


def record_sync_success(
    session: Session,
    source_name: str,
    content_hash: str,
    payload_text: str | None,
    remote_version: str | None = None,
    items_seen: int = 0,
    items_created: int = 0,
    local_path: str | None = None,
) -> SourceSyncRun:
    snapshot = session.scalar(
        select(SourceSnapshot).where(
            SourceSnapshot.source_name == source_name,
            SourceSnapshot.content_hash == content_hash,
        )
    )
    status = "UNCHANGED" if snapshot is not None else "SUCCESS"
    if snapshot is None:
        snapshot = SourceSnapshot(
            source_name=source_name,
            content_hash=content_hash,
            remote_version=remote_version,
            payload_text=payload_text,
            local_path=local_path,
        )
        session.add(snapshot)
        session.flush()

    run = SourceSyncRun(
        source_name=source_name,
        status=status,
        snapshot_id=snapshot.id,
        remote_version=remote_version,
        content_hash=content_hash,
        items_seen=items_seen,
        items_created=items_created,
        finished_at=utcnow(),
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def record_sync_failure(session: Session, source_name: str, error: str) -> SourceSyncRun:
    run = SourceSyncRun(
        source_name=source_name,
        status="FAILED",
        error=error[:4000],
        finished_at=utcnow(),
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    return run

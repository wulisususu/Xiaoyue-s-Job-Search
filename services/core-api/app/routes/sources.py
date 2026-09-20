from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_engine
from ..models import SourceSnapshot, SourceSyncRun
from ..sources.store import latest_good_snapshot
from ..sources.sync import SyncResult, sync_due_sources, sync_tencent_source, sync_workfind_bundle

router = APIRouter(prefix="/api/sources", tags=["sources"])


class SourceStatusRead(BaseModel):
    source_name: str
    last_run_status: str | None = None
    last_run_at: str | None = None
    last_good_version: str | None = None
    last_good_hash: str | None = None
    last_error: str | None = None


class SyncResultRead(BaseModel):
    source_name: str
    status: str
    content_hash: str | None = None
    records_seen: int
    companies_created: int
    jobs_created: int
    sources_created: int
    relations_created: int
    error: str | None = None


def _to_read(result: SyncResult) -> SyncResultRead:
    return SyncResultRead(**{field: getattr(result, field) for field in SyncResultRead.model_fields})


@router.get("/status", response_model=list[SourceStatusRead])
def source_status() -> list[SourceStatusRead]:
    engine = get_engine(get_settings())
    try:
        with Session(engine) as session:
            names = {"tencent-sheet", "workfind-online"}
            names.update(session.scalars(select(SourceSyncRun.source_name).distinct()).all())
            output: list[SourceStatusRead] = []
            for source_name in sorted(names):
                latest_run = session.scalar(
                    select(SourceSyncRun)
                    .where(SourceSyncRun.source_name == source_name)
                    .order_by(SourceSyncRun.id.desc())
                    .limit(1)
                )
                latest_snapshot = latest_good_snapshot(session, source_name)
                output.append(
                    SourceStatusRead(
                        source_name=source_name,
                        last_run_status=latest_run.status if latest_run else None,
                        last_run_at=latest_run.finished_at.isoformat() if latest_run else None,
                        last_good_version=latest_snapshot.remote_version if latest_snapshot else None,
                        last_good_hash=latest_snapshot.content_hash if latest_snapshot else None,
                        last_error=(
                            latest_run.error
                            if latest_run and latest_run.status in {"FAILED", "QUARANTINED"}
                            else None
                        ),
                    )
                )
            return output
    finally:
        engine.dispose()


@router.post("/tencent/sync", response_model=SyncResultRead)
def manual_tencent_sync() -> SyncResultRead:
    engine = get_engine(get_settings())
    try:
        with Session(engine) as session:
            return _to_read(sync_tencent_source(session))
    finally:
        engine.dispose()


@router.post("/workfind/sync", response_model=SyncResultRead)
def manual_workfind_sync() -> SyncResultRead:
    settings = get_settings()
    engine = get_engine(settings)
    try:
        with Session(engine) as session:
            cache_dir = Path(settings.data_dir) / "source-cache" / "workfind"
            return _to_read(sync_workfind_bundle(session, cache_dir=cache_dir))
    finally:
        engine.dispose()


@router.post("/sync-due", response_model=list[SyncResultRead])
def sync_due() -> list[SyncResultRead]:
    settings = get_settings()
    engine = get_engine(settings)
    try:
        with Session(engine) as session:
            cache_dir = Path(settings.data_dir) / "source-cache" / "workfind"
            return [_to_read(result) for result in sync_due_sources(session, cache_dir=cache_dir)]
    finally:
        engine.dispose()

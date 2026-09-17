"""Source completeness gate: one bad feed must not mass-tombstone the library."""

from __future__ import annotations

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models import Base, Job, JobSource
from app.sources.sync import sync_tencent_source


def _payload(records: list[dict], declared_count: int | None = None) -> dict:
    payload = {
        "updated": "2026-09-17",
        "count": len(records) if declared_count is None else declared_count,
        "jobs": records,
    }
    return payload


def _record(title: str) -> dict:
    return {
        "c": "中国移动", "p": title, "l": "南京", "e": "",
        "w": "批次:27届秋招", "d": "招满即止", "s": "腾讯文档校招雷达",
        "t": "其他", "ind": "通信", "u": f"https://jobs.example.com/apply/{title}",
    }


def _job_statuses(session: Session) -> dict[str, str]:
    return {job.title: job.status for job in session.scalars(select(Job)).all()}


def test_suspicious_shrink_is_quarantined_and_does_not_tombstone(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'gate.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        good = sync_tencent_source(session, payload_loader=lambda: _payload([_record("岗位A"), _record("岗位B"), _record("岗位C")]))
        assert good.status == "SUCCESS"

        # Upstream "loses" two thirds of the feed but HTTP/JSON are fine.
        shrunk = sync_tencent_source(session, payload_loader=lambda: _payload([_record("岗位A")]))
        assert shrunk.status == "QUARANTINED"
        assert "50%" in (shrunk.error or "")

        statuses = _job_statuses(session)
        # The mass tombstone must NOT have fired.
        assert statuses["岗位B"] != "STALE"
        assert statuses["岗位C"] != "STALE"
        active_sources = session.scalars(select(JobSource).where(JobSource.status == "ACTIVE")).all()
        assert len(active_sources) == 3
    engine.dispose()


def test_count_field_mismatch_is_quarantined_even_without_shrink(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'gate2.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        good = sync_tencent_source(session, payload_loader=lambda: _payload([_record("岗位A")]))
        assert good.status == "SUCCESS"

        # Feed declares 5 records but carries 1 — suspicious even though the
        # volume never grew before.
        lying = sync_tencent_source(session, payload_loader=lambda: _payload([_record("岗位A")], declared_count=5))
        assert lying.status == "QUARANTINED"
        assert "declared count" in (lying.error or "")
    engine.dispose()


def test_second_identical_pull_confirms_shrink_and_reconciles(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'gate3.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        sync_tencent_source(session, payload_loader=lambda: _payload([_record("岗位A"), _record("岗位B"), _record("岗位C")]))
        first_bad = sync_tencent_source(session, payload_loader=lambda: _payload([_record("岗位A")]))
        assert first_bad.status == "QUARANTINED"

        # Second pull, same reduced volume: accept the new normal.
        confirmed = sync_tencent_source(session, payload_loader=lambda: _payload([_record("岗位A")]))
        assert confirmed.status in {"SUCCESS", "UNCHANGED"}

        statuses = _job_statuses(session)
        assert statuses["岗位B"] == "STALE"
        assert statuses["岗位C"] == "STALE"
        assert statuses["岗位A"] != "STALE"
    engine.dispose()


def test_healthy_feed_after_quarantine_recovers_normally(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'gate4.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        sync_tencent_source(session, payload_loader=lambda: _payload([_record("岗位A"), _record("岗位B"), _record("岗位C")]))
        bad = sync_tencent_source(session, payload_loader=lambda: _payload([_record("岗位A")]))
        assert bad.status == "QUARANTINED"

        # Feed recovers: full volume again, everything stays/restarts ACTIVE.
        recovered = sync_tencent_source(session, payload_loader=lambda: _payload([_record("岗位A"), _record("岗位B"), _record("岗位C")]))
        assert recovered.status in {"SUCCESS", "UNCHANGED"}
        statuses = _job_statuses(session)
        assert all(status != "STALE" for status in statuses.values())
    engine.dispose()

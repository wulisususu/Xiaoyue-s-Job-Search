from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models import Base, SourceSnapshot, SourceSyncRun
from app.sources.store import latest_good_snapshot, record_sync_failure, record_sync_success


def test_success_snapshot_survives_later_failed_refresh(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'source.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        first = record_sync_success(
            session,
            source_name='tencent-sheet',
            content_hash='abc123',
            payload_text='{"count":1}',
            remote_version='2026-09-16',
            items_seen=1,
            items_created=1,
        )
        assert first.status == 'SUCCESS'
        assert latest_good_snapshot(session, 'tencent-sheet').payload_text == '{"count":1}'

        failed = record_sync_failure(session, 'tencent-sheet', 'network timeout')
        assert failed.status == 'FAILED'
        snapshot = latest_good_snapshot(session, 'tencent-sheet')
        assert snapshot is not None
        assert snapshot.content_hash == 'abc123'
        assert snapshot.payload_text == '{"count":1}'

        assert len(session.scalars(select(SourceSnapshot)).all()) == 1
        assert [row.status for row in session.scalars(select(SourceSyncRun).order_by(SourceSyncRun.id)).all()] == [
            'SUCCESS', 'FAILED'
        ]


def test_unchanged_hash_reuses_snapshot_and_records_run(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'source.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        first = record_sync_success(session, 'tencent-sheet', 'same', '{"count":2}', items_seen=2)
        second = record_sync_success(session, 'tencent-sheet', 'same', '{"count":2}', items_seen=2)
        assert first.snapshot_id == second.snapshot_id
        assert first.status == 'SUCCESS'
        assert second.status == 'UNCHANGED'
        assert len(session.scalars(select(SourceSnapshot)).all()) == 1


def test_quarantined_snapshot_never_replaces_last_known_good(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'source.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        good = record_sync_success(
            session,
            "tencent-sheet",
            "good-hash",
            '{"count":100}',
            remote_version="good-v1",
            items_seen=100,
        )
        quarantined = record_sync_success(
            session,
            "tencent-sheet",
            "quarantined-hash",
            '{"count":10}',
            remote_version="suspect-v2",
            items_seen=10,
        )
        quarantined.status = "QUARANTINED"
        quarantined.error = "completeness gate: suspicious shrink"
        session.commit()

        snapshot = latest_good_snapshot(session, "tencent-sheet")
        assert snapshot is not None
        assert snapshot.id == good.snapshot_id
        assert snapshot.content_hash == "good-hash"
        assert snapshot.remote_version == "good-v1"

        all_snapshots = session.scalars(
            select(SourceSnapshot).order_by(SourceSnapshot.id)
        ).all()
        assert [item.content_hash for item in all_snapshots] == [
            "good-hash",
            "quarantined-hash",
        ]


def test_only_quarantined_snapshots_do_not_create_a_last_known_good(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'source.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        quarantined = record_sync_success(
            session,
            "tencent-sheet",
            "quarantined-only",
            '{"count":10}',
            remote_version="suspect-v1",
            items_seen=10,
        )
        quarantined.status = "QUARANTINED"
        session.commit()

        assert latest_good_snapshot(session, "tencent-sheet") is None

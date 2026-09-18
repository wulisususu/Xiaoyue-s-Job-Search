"""Concurrent syncs race on first-seen companies.

Real-world repro (packaged app, 2026-09-18): the dashboard fires the
tencent and workfind syncs at the same time, both feeds contain 搜狐集团,
both request sessions run their company lookup before either INSERT
commits, and the loser dies with sqlite3.IntegrityError on the
(normalized_name, ownership) unique index - taking the whole sync down.
"""

from __future__ import annotations

import threading

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_engine, init_db
from app.jobs.company_resolver import resolve_company
from app.models import Company

COMPANY = "搜狐集团"


@pytest.fixture
def engine(tmp_path, monkeypatch):
    monkeypatch.setenv("XIAOYUE_DATA_DIR", str(tmp_path))
    settings = get_settings()
    init_db(settings)
    return get_engine(settings)


def test_concurrent_first_seen_company_syncs_do_not_crash(engine):
    barrier = threading.Barrier(3)
    failures: list[BaseException] = []

    def worker(name: str) -> None:
        try:
            with Session(engine) as session:
                # Phase A: the pre-insert lookup every sync performs.
                first = resolve_company(session, name, create_unknown=False)
                assert first is None, "test premise: company starts absent"
                barrier.wait(timeout=10)
                # Phase B: creation + commit racing the sibling thread.
                company = resolve_company(session, name, create_unknown=True)
                assert company is not None
                session.commit()
        except BaseException as error:  # noqa: BLE001 - capture everything for the assertion
            failures.append(error)

    threads = [
        threading.Thread(target=worker, args=(COMPANY,), name="sync-tencent"),
        threading.Thread(target=worker, args=(COMPANY,), name="sync-workfind"),
    ]
    for thread in threads:
        thread.start()
    barrier.wait(timeout=10)
    for thread in threads:
        thread.join(timeout=30)

    assert failures == [], f"concurrent sync raised: {failures!r}"

    with Session(engine) as session:
        companies = session.scalars(
            select(Company).where(Company.normalized_name == COMPANY)
        ).all()
        assert len(companies) == 1, "exactly one company row must survive"

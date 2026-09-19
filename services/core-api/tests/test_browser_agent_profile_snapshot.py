from __future__ import annotations

import json

from sqlalchemy.orm import Session

from app.browser_agent.profile_snapshot import build_confirmed_profile_snapshot
from app.models import ProfileCollectionItem, ProfileDraftField, ProfileField


def test_browser_agent_snapshot_reads_only_confirmed_ssot(client):
    from app.config import get_settings
    from app.db import get_engine

    engine = get_engine(get_settings())
    try:
        with Session(engine) as session:
            session.add_all([
                ProfileField(
                    field_key="identity.name",
                    value_json=json.dumps("赵新悦", ensure_ascii=False),
                    value_type="string",
                    source_type="manual",
                    confidence=1.0,
                    confirmed=True,
                ),
                ProfileField(
                    field_key="contact.email",
                    value_json=json.dumps("draft@example.com"),
                    value_type="string",
                    source_type="resume",
                    confidence=0.9,
                    confirmed=False,
                ),
                ProfileCollectionItem(
                    kind="education",
                    position=0,
                    payload_json=json.dumps({"school": "三江学院", "major": "视觉传达设计"}, ensure_ascii=False),
                    source_type="manual",
                    confidence=1.0,
                    confirmed=True,
                ),
                ProfileCollectionItem(
                    kind="skill",
                    position=0,
                    payload_json=json.dumps({"name": "不应读取的草稿技能"}, ensure_ascii=False),
                    source_type="resume",
                    confidence=0.8,
                    confirmed=False,
                ),
            ])
            session.commit()

            snapshot = build_confirmed_profile_snapshot(session)

            assert snapshot.scalars == {"identity.name": "赵新悦"}
            assert snapshot.collections == {
                "education": [{"school": "三江学院", "major": "视觉传达设计"}],
            }
            assert "contact.email" not in snapshot.scalars
            assert "skill" not in snapshot.collections
    finally:
        engine.dispose()

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy.orm import Session

from app.browser_agent.manager import BrowserAgentManager
from app.browser_agent.models import FormFieldDescriptor, FormScan
from app.config import get_settings
from app.db import get_engine
from app.models import ApplicationSession, Company, Job, ProfileField


class FakeEdgeBackend:
    browser_name = "Fake Edge"

    def __init__(self) -> None:
        self.started: tuple[str, Path] | None = None
        self.filled: dict[str, object] | None = None
        self.closed = False

    def start(self, url: str, profile_dir: Path):
        self.started = (url, profile_dir)
        return object()

    def scan(self, handle):
        return FormScan(
            url="https://ats.example.com/apply/form",
            title="申请表",
            fields=[
                FormFieldDescriptor(
                    field_id="name",
                    tag="input",
                    input_type="text",
                    label="姓名",
                    name="realName",
                    placeholder="",
                    aria_label="",
                    section="基本信息",
                    required=True,
                    options=[],
                ),
                FormFieldDescriptor(
                    field_id="password",
                    tag="input",
                    input_type="password",
                    label="密码",
                    name="password",
                    placeholder="",
                    aria_label="",
                    section="账号",
                    required=True,
                    options=[],
                ),
            ],
        )

    def fill(self, handle, values):
        self.filled = values
        return {"filled_count": len(values), "skipped_count": 0}

    def close(self, handle):
        self.closed = True


def _seed_application_and_profile() -> int:
    engine = get_engine(get_settings())
    try:
        with Session(engine) as session:
            company = Company(name="中国移动", normalized_name="中国移动", ownership="central_soe")
            session.add(company)
            session.flush()
            job = Job(
                id="job-agent-manager",
                company_id=company.id,
                title="视觉设计",
                location="南京",
                industry="设计",
                recruitment_batch="27届",
                deadline_text="招满即止",
                apply_url="https://ats.example.com/apply",
                canonical_url="https://ats.example.com/apply",
                status="VERIFIED_OPEN",
                fingerprint="fp-agent-manager",
            )
            session.add(job)
            session.flush()
            application = ApplicationSession(
                job_id=job.id,
                channel="browser_agent",
                opened_url=job.canonical_url,
            )
            session.add(application)
            session.add_all(
                [
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
                        value_json=json.dumps("unconfirmed@example.com"),
                        value_type="string",
                        source_type="resume",
                        confidence=0.9,
                        confirmed=False,
                    ),
                ]
            )
            session.commit()
            session.refresh(application)
            return application.id
    finally:
        engine.dispose()


def test_real_manager_uses_confirmed_ssot_blocks_sensitive_fields_and_updates_crm(client, monkeypatch):
    application_id = _seed_application_and_profile()
    backend = FakeEdgeBackend()
    manager = BrowserAgentManager(backend=backend)
    monkeypatch.setattr("app.browser_agent.manager.validate_external_url", lambda url: None)

    info = manager.start_for_application(application_id)
    assert info.browser == "Fake Edge"
    assert backend.started is not None
    assert backend.started[0] == "https://ats.example.com/apply"
    assert "browser-agent" in str(backend.started[1])

    plan = manager.build_plan(info.id)
    assert [(item.field_id, item.value, item.source_path) for item in plan.items] == [
        ("name", "赵新悦", "identity.name"),
    ]
    assert [item.field_id for item in plan.blocked] == ["password"]
    assert all(item.value != "unconfirmed@example.com" for item in plan.items)

    result = manager.fill(info.id, plan.token, ["name"])
    assert result == {"filled_count": 1, "skipped_count": 0, "status": "FILLED"}
    assert backend.filled == {"name": "赵新悦"}

    engine = get_engine(get_settings())
    try:
        with Session(engine) as session:
            application = session.get(ApplicationSession, application_id)
            assert application is not None
            assert application.status == "IN_PROGRESS"
    finally:
        engine.dispose()

    assert manager.close(info.id) is True
    assert backend.closed is True


def test_real_manager_rejects_stale_plan_and_unknown_field_ids(client, monkeypatch):
    application_id = _seed_application_and_profile()
    backend = FakeEdgeBackend()
    manager = BrowserAgentManager(backend=backend)
    monkeypatch.setattr("app.browser_agent.manager.validate_external_url", lambda url: None)

    info = manager.start_for_application(application_id)
    plan = manager.build_plan(info.id)

    import pytest
    from app.browser_agent.manager import BrowserAgentPlanError

    with pytest.raises(BrowserAgentPlanError):
        manager.fill(info.id, "stale-token", ["name"])
    with pytest.raises(BrowserAgentPlanError):
        manager.fill(info.id, plan.token, ["not-in-plan"])

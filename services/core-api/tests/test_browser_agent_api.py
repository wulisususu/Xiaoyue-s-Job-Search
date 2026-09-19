from __future__ import annotations

from dataclasses import asdict

from sqlalchemy.orm import Session

from app.browser_agent.models import BrowserAgentSessionInfo, FillPlan, FillPlanItem, FormFieldDescriptor
from app.config import get_settings
from app.db import get_engine
from app.models import ApplicationSession, Company, Job
from app.routes import browser_agent as browser_routes


class FakeBrowserAgentManager:
    def __init__(self):
        self.filled = None
        self.closed = None

    def start_for_application(self, application_id: int):
        return BrowserAgentSessionInfo(
            id="agent-1",
            application_id=application_id,
            url="https://ats.example.com/apply",
            status="READY",
            browser="Microsoft Edge",
        )

    def list_sessions(self):
        return [self.start_for_application(1)]

    def build_plan(self, session_id: str):
        descriptor = FormFieldDescriptor(
            field_id="xy-1", tag="input", input_type="text", label="姓名",
            name="name", placeholder="", aria_label="", section="", required=True, options=[],
        )
        return FillPlan(
            token="plan-1",
            session_id=session_id,
            page_url="https://ats.example.com/apply",
            items=[
                FillPlanItem(
                    field_id="xy-1", label="姓名", control_type="text", value="赵新悦",
                    source_path="identity.name", confidence=0.99, reason="姓名", requires_confirmation=False,
                )
            ],
            unmatched=[],
            blocked=[],
        )

    def augment_plan_with_ai(self, session_id: str, plan_token: str):
        assert session_id == "agent-1"
        assert plan_token == "plan-1"
        plan = self.build_plan(session_id)
        plan.token = "plan-ai"
        plan.items[0].requires_confirmation = True
        return plan

    def fill(self, session_id: str, plan_token: str, field_ids: list[str]):
        self.filled = (session_id, plan_token, field_ids)
        return {"filled_count": len(field_ids), "skipped_count": 0, "status": "FILLED"}

    def close(self, session_id: str):
        self.closed = session_id
        return True


def seed_application(*, status: str = "VERIFIED_OPEN", channel: str = "browser_agent") -> int:
    engine = get_engine(get_settings())
    try:
        with Session(engine) as session:
            company = Company(name="中国移动", normalized_name="中国移动", ownership="central_soe")
            session.add(company)
            session.flush()
            job = Job(
                id="job-agent", company_id=company.id, title="视觉设计", location="南京", industry="设计",
                recruitment_batch="27届", deadline_text="招满即止",
                apply_url="https://ats.example.com/apply", canonical_url="https://ats.example.com/apply",
                status=status, fingerprint=f"fp-{status}",
            )
            session.add(job)
            session.flush()
            application = ApplicationSession(
                job_id=job.id,
                channel=channel,
                opened_url=job.canonical_url,
            )
            session.add(application)
            session.commit()
            session.refresh(application)
            return application.id
    finally:
        engine.dispose()


def test_browser_agent_api_exposes_plan_then_fills_only_approved_plan_fields(client, monkeypatch):
    application_id = seed_application()
    manager = FakeBrowserAgentManager()
    monkeypatch.setattr(browser_routes, "get_browser_agent_manager", lambda: manager)

    started = client.post("/api/browser-agent/sessions", json={"application_id": application_id})
    assert started.status_code == 200
    assert started.json()["id"] == "agent-1"

    plan = client.post("/api/browser-agent/sessions/agent-1/plan")
    assert plan.status_code == 200
    payload = plan.json()
    assert payload["items"][0]["source_path"] == "identity.name"
    assert payload["items"][0]["value"] == "赵新悦"

    semantic = client.post(
        "/api/browser-agent/sessions/agent-1/semantic-plan",
        json={"plan_token": "plan-1"},
    )
    assert semantic.status_code == 200
    assert semantic.json()["token"] == "plan-ai"
    assert semantic.json()["items"][0]["requires_confirmation"] is True

    filled = client.post(
        "/api/browser-agent/sessions/agent-1/fill",
        json={"plan_token": "plan-ai", "field_ids": ["xy-1"]},
    )
    assert filled.status_code == 200
    assert filled.json()["filled_count"] == 1
    assert manager.filled == ("agent-1", "plan-ai", ["xy-1"])


def test_browser_agent_requires_browser_agent_application_channel(client, monkeypatch):
    application_id = seed_application(channel="manual")
    monkeypatch.setattr(browser_routes, "get_browser_agent_manager", lambda: FakeBrowserAgentManager())

    response = client.post("/api/browser-agent/sessions", json={"application_id": application_id})
    assert response.status_code == 409


def test_browser_agent_plan_read_redacts_sensitive_profile_values():
    from app.routes.browser_agent import _plan_read

    raw = "TESTDOC-ABC1234"
    plan = FillPlan(
        token="secret-plan",
        session_id="agent-secret",
        page_url="https://ats.example.com/apply",
        items=[
            FillPlanItem(
                field_id="doc",
                label="证件号码",
                control_type="text",
                value=raw,
                source_path="identity.id_number",
                confidence=0.99,
                reason="证件号码",
                requires_confirmation=True,
            )
        ],
        unmatched=[],
        blocked=[],
    )

    rendered = _plan_read(plan)
    assert rendered.items[0].value != raw
    assert str(rendered.items[0].value).endswith("1234")

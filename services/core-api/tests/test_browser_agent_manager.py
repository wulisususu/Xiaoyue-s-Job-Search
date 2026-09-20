from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy.orm import Session

from app.browser_agent.manager import BrowserAgentManager
from app.browser_agent.models import FormFieldDescriptor, FormScan
from app.config import get_settings
from app.db import get_engine
from app.models import ApplicationEvent, ApplicationSession, Company, Job, ProfileField, ResumeVersion


class FakeEdgeBackend:
    browser_name = "Fake Edge"

    def __init__(self) -> None:
        self.started: tuple[str, Path] | None = None
        self.filled: dict[str, object] | None = None
        self.closed = False
        self.current_url = "https://ats.example.com/apply/form"
        self.name_input_type = "text"
        self.name_label = "姓名"
        self.title = "申请表"
        self.fill_outcome = "VERIFIED"

    def start(self, url: str, profile_dir: Path):
        self.started = (url, profile_dir)
        return object()

    def scan(self, handle):
        return FormScan(
            url=self.current_url,
            title=self.title,
            fields=[
                FormFieldDescriptor(
                    field_id="name",
                    tag="input",
                    input_type=self.name_input_type,
                    label=self.name_label,
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
            target_id="target-1",
        )

    def fill(self, handle, values):
        self.filled = values
        results = []
        for field_id, value in values.items():
            if self.fill_outcome == "FAILED":
                results.append(
                    {
                        "field_id": field_id,
                        "requested": value,
                        "observed": "",
                        "status": "FAILED",
                        "reason": "VALUE_REVERTED",
                    }
                )
            else:
                results.append(
                    {
                        "field_id": field_id,
                        "requested": value,
                        "observed": value,
                        "status": "VERIFIED",
                        "reason": "READBACK_MATCH",
                    }
                )
        return {
            "filled_count": len(values),
            "skipped_count": 0,
            "verified_count": len(values) if self.fill_outcome == "VERIFIED" else 0,
            "failed_count": len(values) if self.fill_outcome == "FAILED" else 0,
            "uncertain_count": 0,
            "results": results,
        }

    def close(self, handle):
        self.closed = True


def _seed_application_and_profile(*, job_status: str = "VERIFIED_OPEN") -> int:
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
                status=job_status,
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
    assert result == {
        "filled_count": 1,
        "skipped_count": 0,
        "verified_count": 1,
        "failed_count": 0,
        "uncertain_count": 0,
        "results": [
            {
                "field_id": "name",
                "requested": "赵新悦",
                "observed": "赵新悦",
                "status": "VERIFIED",
                "reason": "READBACK_MATCH",
                "source_path": "identity.name",
            }
        ],
        "status": "VERIFIED",
    }
    assert backend.filled == {"name": "赵新悦"}

    engine = get_engine(get_settings())
    try:
        with Session(engine) as session:
            application = session.get(ApplicationSession, application_id)
            assert application is not None
            assert application.status == "IN_PROGRESS"
            events = session.query(ApplicationEvent).filter(
                ApplicationEvent.application_id == application_id
            ).order_by(ApplicationEvent.id).all()
            assert [(event.from_status, event.to_status) for event in events] == [
                ("OPENED", "IN_PROGRESS"),
            ]
            assert events[0].note == "Browser Agent started filling confirmed fields"
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


def test_real_manager_rejects_plan_after_navigation_or_control_type_change(client, monkeypatch):
    application_id = _seed_application_and_profile()
    backend = FakeEdgeBackend()
    manager = BrowserAgentManager(backend=backend)
    monkeypatch.setattr("app.browser_agent.manager.validate_external_url", lambda url: None)

    info = manager.start_for_application(application_id)
    plan = manager.build_plan(info.id)

    import pytest
    from app.browser_agent.manager import BrowserAgentPlanError

    backend.current_url = "https://ats.example.com/apply/next-step"
    with pytest.raises(BrowserAgentPlanError, match="页面已变化"):
        manager.fill(info.id, plan.token, ["name"])
    assert backend.filled is None

    backend.current_url = plan.page_url
    backend.name_input_type = "password"
    with pytest.raises(BrowserAgentPlanError, match="页面控件已变化"):
        manager.fill(info.id, plan.token, ["name"])
    assert backend.filled is None


def test_real_manager_rejects_plan_when_same_url_spa_structure_changes(client, monkeypatch):
    application_id = _seed_application_and_profile()
    backend = FakeEdgeBackend()
    manager = BrowserAgentManager(backend=backend)
    monkeypatch.setattr("app.browser_agent.manager.validate_external_url", lambda url: None)

    info = manager.start_for_application(application_id)
    plan = manager.build_plan(info.id)
    assert plan.page_revision

    import pytest
    from app.browser_agent.manager import BrowserAgentPlanError

    # Same URL, same field id and same input type, but the SPA replaced the
    # semantic structure of the page. The old plan must not be reused.
    backend.name_label = "紧急联系人姓名"
    with pytest.raises(BrowserAgentPlanError, match="页面结构已变化"):
        manager.fill(info.id, plan.token, ["name"])
    assert backend.filled is None


def test_verify_mode_breaks_static_verification_deadlock_and_promotes_job(client, monkeypatch):
    application_id = _seed_application_and_profile(job_status="DISCOVERED_URL_UNVERIFIED")
    backend = FakeEdgeBackend()
    manager = BrowserAgentManager(backend=backend)
    monkeypatch.setattr("app.browser_agent.manager.validate_external_url", lambda url: None)

    import pytest
    from app.browser_agent.manager import BrowserAgentConflictError

    with pytest.raises(BrowserAgentConflictError, match="VERIFIED_OPEN"):
        manager.start_for_application(application_id, mode="fill")

    info = manager.start_for_application(application_id, mode="verify")
    assert info.mode == "verify"

    with pytest.raises(BrowserAgentConflictError, match="Verify-mode"):
        manager.build_plan(info.id)

    result = manager.confirm_browser_verification(info.id)
    assert result["verified"] is True
    assert result["job_status"] == "VERIFIED_OPEN"
    assert result["evidence_count"] >= 1
    assert info.mode == "fill"

    # The same live browser session becomes fill-capable only after browser
    # evidence has promoted the job.
    plan = manager.build_plan(info.id)
    assert plan.page_revision

    engine = get_engine(get_settings())
    try:
        with Session(engine) as session:
            application = session.get(ApplicationSession, application_id)
            assert application is not None
            job = session.get(Job, application.job_id)
            assert job is not None
            assert job.status == "VERIFIED_OPEN"
    finally:
        engine.dispose()


def test_verify_mode_refuses_login_page_as_application_evidence(client, monkeypatch):
    application_id = _seed_application_and_profile(job_status="DISCOVERED_URL_UNVERIFIED")
    backend = FakeEdgeBackend()
    backend.title = "招聘系统登录"
    manager = BrowserAgentManager(backend=backend)
    monkeypatch.setattr("app.browser_agent.manager.validate_external_url", lambda url: None)

    import pytest
    from app.browser_agent.manager import BrowserAgentPlanError

    info = manager.start_for_application(application_id, mode="verify")
    with pytest.raises(BrowserAgentPlanError, match="实际申请表"):
        manager.confirm_browser_verification(info.id)

    engine = get_engine(get_settings())
    try:
        with Session(engine) as session:
            application = session.get(ApplicationSession, application_id)
            assert application is not None
            job = session.get(Job, application.job_id)
            assert job is not None
            assert job.status == "DISCOVERED_URL_UNVERIFIED"
    finally:
        engine.dispose()


def test_real_manager_propagates_post_fill_readback_failure(client, monkeypatch):
    application_id = _seed_application_and_profile()
    backend = FakeEdgeBackend()
    backend.fill_outcome = "FAILED"
    manager = BrowserAgentManager(backend=backend)
    monkeypatch.setattr("app.browser_agent.manager.validate_external_url", lambda url: None)

    info = manager.start_for_application(application_id)
    plan = manager.build_plan(info.id)
    result = manager.fill(info.id, plan.token, ["name"])

    assert result["status"] == "FILLED_WITH_FAILURES"
    assert result["filled_count"] == 1
    assert result["verified_count"] == 0
    assert result["failed_count"] == 1
    assert result["results"][0]["status"] == "FAILED"
    assert result["results"][0]["reason"] == "VALUE_REVERTED"


class FakeMokaUploadBackend(FakeEdgeBackend):
    def __init__(self) -> None:
        super().__init__()
        self.current_url = "https://app.mokahr.com/apply/acme/site#/job/1/apply"
        self.uploaded: tuple[str, Path] | None = None

    def scan(self, handle):
        return FormScan(
            url=self.current_url,
            title="Moka 职位申请",
            fields=[
                FormFieldDescriptor(
                    field_id="resume-file",
                    tag="input",
                    input_type="file",
                    label="上传简历",
                    name="resume",
                    placeholder="",
                    aria_label="",
                    section="简历",
                    required=True,
                    options=[],
                ),
            ],
            target_id="target-1",
        )

    def upload_file(self, handle, field_id: str, file_path: Path):
        self.uploaded = (field_id, file_path)
        return {"filename": file_path.name, "size": file_path.stat().st_size, "type": "application/pdf"}


def _seed_resume_version() -> str:
    settings = get_settings()
    resume_id = "resume-upload-test"
    relpath = Path("resumes") / "upload-test-sha" / "original.pdf"
    source = settings.vault_dir / relpath
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(b"%PDF-test-upload")

    engine = get_engine(settings)
    try:
        with Session(engine) as session:
            session.add(
                ResumeVersion(
                    id=resume_id,
                    sha256="a" * 64,
                    original_filename="赵新悦-央企简历.pdf",
                    file_ext=".pdf",
                    mime_type="application/pdf",
                    size_bytes=source.stat().st_size,
                    vault_relpath=relpath.as_posix(),
                    version_number=99,
                    extraction_status="EXTRACTED",
                )
            )
            session.commit()
    finally:
        engine.dispose()
    return resume_id


def test_manager_uploads_only_explicit_resume_version_to_current_moka_plan(client, monkeypatch):
    application_id = _seed_application_and_profile()
    resume_id = _seed_resume_version()
    backend = FakeMokaUploadBackend()
    manager = BrowserAgentManager(backend=backend)
    monkeypatch.setattr("app.browser_agent.manager.validate_external_url", lambda url: None)

    info = manager.start_for_application(application_id)
    plan = manager.build_plan(info.id)
    assert plan.adapter_id == "moka"
    assert [(item.field_id, item.kind) for item in plan.attachments] == [("resume-file", "resume")]

    import pytest
    from app.browser_agent.manager import BrowserAgentPlanError

    with pytest.raises(BrowserAgentPlanError, match="计划已失效"):
        manager.upload_resume(info.id, "stale-token", "resume-file", resume_id)

    result = manager.upload_resume(info.id, plan.token, "resume-file", resume_id)
    assert result["status"] == "VERIFIED"
    assert result["resume_version_id"] == resume_id
    assert result["filename"] == "赵新悦-央企简历.pdf"

    engine = get_engine(get_settings())
    try:
        with Session(engine) as session:
            application = session.get(ApplicationSession, application_id)
            assert application is not None
            assert application.resume_version_id == resume_id
            events = session.query(ApplicationEvent).filter(
                ApplicationEvent.application_id == application_id
            ).order_by(ApplicationEvent.id).all()
            assert [(event.event_type, event.from_status, event.to_status) for event in events] == [
                ("RESUME_LINKED", "OPENED", "OPENED"),
            ]
            assert events[0].note == f"{resume_id} · 赵新悦-央企简历.pdf"
    finally:
        engine.dispose()

    assert backend.uploaded is not None
    assert backend.uploaded[0] == "resume-file"
    staged_path = backend.uploaded[1]
    assert staged_path.is_file()
    assert "browser-agent" in str(staged_path)
    assert "uploads" in str(staged_path)

    assert manager.close(info.id) is True
    assert not staged_path.exists()


def test_manager_rejects_resume_upload_after_page_revision_changes(client, monkeypatch):
    application_id = _seed_application_and_profile()
    resume_id = _seed_resume_version()
    backend = FakeMokaUploadBackend()
    manager = BrowserAgentManager(backend=backend)
    monkeypatch.setattr("app.browser_agent.manager.validate_external_url", lambda url: None)

    info = manager.start_for_application(application_id)
    plan = manager.build_plan(info.id)
    backend.title = "changed"

    # Make the scan structure change without changing the URL.
    original_scan = backend.scan
    def changed_scan(handle):
        scan = original_scan(handle)
        scan.title = "Moka 新步骤"
        return scan
    backend.scan = changed_scan

    import pytest
    from app.browser_agent.manager import BrowserAgentPlanError
    with pytest.raises(BrowserAgentPlanError, match="页面结构已变化"):
        manager.upload_resume(info.id, plan.token, "resume-file", resume_id)
    assert backend.uploaded is None


class FakeMokaUploadMismatchBackend(FakeMokaUploadBackend):
    def upload_file(self, handle, field_id: str, file_path: Path):
        self.uploaded = (field_id, file_path)
        return {
            "filename": "different.pdf",
            "size": file_path.stat().st_size,
            "type": "application/pdf",
        }


def test_manager_does_not_link_resume_when_browser_readback_fails(client, monkeypatch):
    import pytest
    from app.browser_agent.manager import BrowserAgentPlanError

    application_id = _seed_application_and_profile()
    resume_id = _seed_resume_version()
    backend = FakeMokaUploadMismatchBackend()
    manager = BrowserAgentManager(backend=backend)
    monkeypatch.setattr("app.browser_agent.manager.validate_external_url", lambda url: None)

    info = manager.start_for_application(application_id)
    plan = manager.build_plan(info.id)

    with pytest.raises(BrowserAgentPlanError, match="未确认所选简历文件名"):
        manager.upload_resume(info.id, plan.token, "resume-file", resume_id)

    engine = get_engine(get_settings())
    try:
        with Session(engine) as session:
            application = session.get(ApplicationSession, application_id)
            assert application is not None
            assert application.resume_version_id is None
            events = session.query(ApplicationEvent).filter(
                ApplicationEvent.application_id == application_id
            ).all()
            assert events == []
    finally:
        engine.dispose()

from __future__ import annotations

import atexit
import hashlib
import json
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from ..ai.secrets import CredentialStoreUnavailableError, get_secret_store
from ..config import get_settings
from ..db import get_engine
from ..models import AIProviderConfig, ApplicationSession, Job
from ..verification.url_guard import validate_external_url
from .cdp import BrowserControlError, BrowserUnavailableError, EdgeBrowserBackend, EdgeHandle
from .mapping import build_fill_plan
from .models import BrowserAgentSessionInfo, FillPlan, FormScan
from .profile_snapshot import build_confirmed_profile_snapshot
from .semantic_mapping import OpenAICompatibleSemanticMappingProvider, apply_semantic_suggestions


class BrowserAgentSessionNotFoundError(LookupError):
    pass


class BrowserAgentConflictError(RuntimeError):
    pass


class BrowserAgentPlanError(RuntimeError):
    pass


class BrowserAgentAIUnavailableError(RuntimeError):
    pass


def _page_revision(scan: FormScan) -> str:
    payload = {
        "target_id": scan.target_id,
        "url": scan.url,
        "title": scan.title,
        "fields": [
            {
                "field_id": field.field_id,
                "tag": field.tag,
                "input_type": field.input_type,
                "label": field.label,
                "name": field.name,
                "placeholder": field.placeholder,
                "aria_label": field.aria_label,
                "section": field.section,
                "required": field.required,
                "options": field.options,
                "disabled": field.disabled,
                "readonly": field.readonly,
            }
            for field in scan.fields
        ],
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(slots=True)
class _RuntimeSession:
    info: BrowserAgentSessionInfo
    handle: EdgeHandle
    latest_plan: FillPlan | None = None


class BrowserAgentManager:
    def __init__(self, backend: EdgeBrowserBackend | None = None) -> None:
        self._backend = backend or EdgeBrowserBackend()
        self._sessions: dict[str, _RuntimeSession] = {}
        self._by_application: dict[int, str] = {}
        self._lock = threading.RLock()

    def _application(self, application_id: int) -> tuple[ApplicationSession, Job]:
        engine = get_engine(get_settings())
        try:
            with Session(engine) as session:
                application = session.get(ApplicationSession, application_id)
                if application is None:
                    raise BrowserAgentSessionNotFoundError(f"Application {application_id} not found")
                job = session.get(Job, application.job_id)
                if job is None:
                    raise BrowserAgentSessionNotFoundError(f"Job {application.job_id} not found")
                session.expunge(application)
                session.expunge(job)
                return application, job
        finally:
            engine.dispose()

    def start_for_application(self, application_id: int) -> BrowserAgentSessionInfo:
        with self._lock:
            existing_id = self._by_application.get(application_id)
            if existing_id and existing_id in self._sessions:
                return self._sessions[existing_id].info

        application, job = self._application(application_id)
        if application.channel != "browser_agent":
            raise BrowserAgentConflictError("Application is not a Browser Agent session")
        if job.status != "VERIFIED_OPEN":
            raise BrowserAgentConflictError("Browser Agent only opens VERIFIED_OPEN jobs")
        url = application.opened_url or job.canonical_url or job.apply_url
        if not url:
            raise BrowserAgentConflictError("Application has no verified URL")
        validate_external_url(url)

        settings = get_settings()
        profile_dir = settings.data_dir / "browser-agent" / "profiles" / f"application-{application_id}"
        handle = self._backend.start(url, profile_dir)
        session_id = uuid.uuid4().hex
        info = BrowserAgentSessionInfo(
            id=session_id,
            application_id=application_id,
            url=url,
            status="READY",
            browser=self._backend.browser_name,
        )
        runtime = _RuntimeSession(info=info, handle=handle)
        with self._lock:
            self._sessions[session_id] = runtime
            self._by_application[application_id] = session_id
        return info

    def list_sessions(self) -> list[BrowserAgentSessionInfo]:
        with self._lock:
            return [runtime.info for runtime in self._sessions.values()]

    def _runtime(self, session_id: str) -> _RuntimeSession:
        with self._lock:
            runtime = self._sessions.get(session_id)
        if runtime is None:
            raise BrowserAgentSessionNotFoundError(f"Browser Agent session {session_id} not found")
        return runtime

    def build_plan(self, session_id: str) -> FillPlan:
        runtime = self._runtime(session_id)
        scan = self._backend.scan(runtime.handle)
        engine = get_engine(get_settings())
        try:
            with Session(engine) as db:
                snapshot = build_confirmed_profile_snapshot(db)
        finally:
            engine.dispose()
        plan = build_fill_plan(
            snapshot,
            scan,
            session_id=session_id,
            page_revision=_page_revision(scan),
        )
        runtime.latest_plan = plan
        runtime.info.url = scan.url or runtime.info.url
        return plan

    def augment_plan_with_ai(self, session_id: str, plan_token: str) -> FillPlan:
        runtime = self._runtime(session_id)
        plan = runtime.latest_plan
        if plan is None or plan.token != plan_token:
            raise BrowserAgentPlanError("填写计划已失效，请重新扫描表单。")
        if not plan.unmatched:
            return plan

        current_scan = self._backend.scan(runtime.handle)
        if current_scan.url != plan.page_url or _page_revision(current_scan) != plan.page_revision:
            raise BrowserAgentPlanError("页面已变化，请重新扫描表单后再使用 AI 补全。")

        engine = get_engine(get_settings())
        try:
            with Session(engine) as db:
                snapshot = build_confirmed_profile_snapshot(db)
                config = db.get(AIProviderConfig, "default")
                if config is None:
                    raise BrowserAgentAIUnavailableError("请先在设置中配置 AI Provider。")
                if not config.secret_ref:
                    raise BrowserAgentAIUnavailableError("请先在设置中保存 AI Provider API Key。")
                try:
                    api_key = get_secret_store().get_secret(config.secret_ref)
                except CredentialStoreUnavailableError as exc:
                    raise BrowserAgentAIUnavailableError(str(exc)) from exc
                if not api_key:
                    raise BrowserAgentAIUnavailableError("AI Provider API Key 不可用，请重新保存。")
                provider = OpenAICompatibleSemanticMappingProvider(config, api_key)
                updated = apply_semantic_suggestions(snapshot, current_scan, plan, provider)
        finally:
            engine.dispose()

        runtime.latest_plan = updated
        return updated

    def fill(self, session_id: str, plan_token: str, field_ids: list[str]) -> dict[str, Any]:
        runtime = self._runtime(session_id)
        plan = runtime.latest_plan
        if plan is None or plan.token != plan_token:
            raise BrowserAgentPlanError("填写计划已失效，请重新扫描表单。")

        by_id = {item.field_id: item for item in plan.items}
        unknown = sorted(set(field_ids) - set(by_id))
        if unknown:
            raise BrowserAgentPlanError(f"填写计划不包含字段: {', '.join(unknown)}")

        current_scan = self._backend.scan(runtime.handle)
        if current_scan.url != plan.page_url:
            raise BrowserAgentPlanError("页面已变化，请重新扫描表单后再填写。")
        current_fields = {field.field_id: field for field in current_scan.fields}
        stale: list[str] = []
        for field_id in field_ids:
            descriptor = current_fields.get(field_id)
            expected = by_id[field_id]
            current_type = (descriptor.input_type or descriptor.tag).lower() if descriptor else ""
            if descriptor is None or current_type != expected.control_type.lower():
                stale.append(field_id)
        if stale:
            raise BrowserAgentPlanError(
                f"页面控件已变化，请重新扫描: {', '.join(sorted(stale))}"
            )
        if _page_revision(current_scan) != plan.page_revision:
            raise BrowserAgentPlanError("页面结构已变化，请重新扫描表单后再填写。")

        approved_values = {field_id: by_id[field_id].value for field_id in field_ids}
        result = self._backend.fill(runtime.handle, approved_values)

        engine = get_engine(get_settings())
        try:
            with Session(engine) as db:
                application = db.get(ApplicationSession, runtime.info.application_id)
                if application is not None and application.status == "OPENED":
                    application.status = "IN_PROGRESS"
                    db.commit()
        finally:
            engine.dispose()

        return {
            "filled_count": int(result.get("filled_count", 0)),
            "skipped_count": int(result.get("skipped_count", 0)),
            "status": "FILLED",
        }

    def close(self, session_id: str) -> bool:
        with self._lock:
            runtime = self._sessions.pop(session_id, None)
            if runtime is None:
                return False
            self._by_application.pop(runtime.info.application_id, None)
        self._backend.close(runtime.handle)
        return True

    def shutdown(self) -> None:
        with self._lock:
            ids = list(self._sessions)
        for session_id in ids:
            self.close(session_id)


_MANAGER: BrowserAgentManager | None = None
_MANAGER_LOCK = threading.Lock()


def get_browser_agent_manager() -> BrowserAgentManager:
    global _MANAGER
    if _MANAGER is None:
        with _MANAGER_LOCK:
            if _MANAGER is None:
                _MANAGER = BrowserAgentManager()
                atexit.register(_MANAGER.shutdown)
    return _MANAGER

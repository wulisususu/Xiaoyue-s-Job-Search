from __future__ import annotations

import atexit
import hashlib
import json
import re
import shutil
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from ..ai.secrets import CredentialStoreUnavailableError, get_secret_store
from ..config import get_settings
from ..db import get_engine
from ..models import AIProviderConfig, ApplicationSession, Job, ResumeVersion
from ..verification.service import promote_browser_verified
from ..verification.url_guard import validate_external_url
from .adapters import (
    adapt_scan_for_browser_adapter,
    get_browser_adapter,
    select_browser_adapter,
)
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


_VERIFICATION_BLOCKED_TYPES = {"hidden", "password", "submit", "button", "reset", "image"}
_APPLICATION_FIELD_TERMS = (
    "姓名", "手机", "电话", "邮箱", "性别", "出生", "证件", "学校", "院校",
    "专业", "学历", "户籍", "简历", "工作经历", "教育经历",
    "name", "phone", "mobile", "email", "gender", "birth", "document",
    "school", "university", "major", "degree", "resume", "experience",
)
_APPLICATION_TITLE_TERMS = ("申请", "应聘", "网申", "application", "career")
_LOGIN_TITLE_TERMS = ("登录", "登陆", "login", "sign in", "signin")
_INVALID_UPLOAD_FILENAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_WINDOWS_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}


def _safe_upload_filename(original_filename: str, file_ext: str) -> str:
    raw_name = (original_filename or "resume").replace("\\", "/").rsplit("/", 1)[-1]
    cleaned = _INVALID_UPLOAD_FILENAME.sub("_", raw_name).strip(" .")
    stem = Path(cleaned).stem.strip(" .") or "resume"
    if stem.upper() in _WINDOWS_RESERVED_NAMES:
        stem = f"resume-{stem.lower()}"
    ext = file_ext.lower()
    if ext not in {".pdf", ".docx"}:
        raise BrowserAgentPlanError("Browser Agent only uploads validated PDF/DOCX resume versions")
    return f"{stem}{ext}"


def _browser_verification_evidence(scan: FormScan) -> list[str]:
    title = (scan.title or "").strip().lower()
    if any(term in title for term in _LOGIN_TITLE_TERMS):
        return []

    editable = []
    evidence: list[str] = []
    for field in scan.fields:
        control_type = (field.input_type or field.tag or "").lower()
        if field.disabled or field.readonly or control_type in _VERIFICATION_BLOCKED_TYPES:
            continue
        editable.append(field)
        text = " ".join(
            [
                field.label,
                field.name,
                field.placeholder,
                field.aria_label,
                field.section,
            ]
        ).lower()
        if any(term in text for term in _APPLICATION_FIELD_TERMS):
            evidence.append(field.field_id)

    title_is_application = any(term in title for term in _APPLICATION_TITLE_TERMS)
    if evidence and title_is_application:
        return evidence
    if len(evidence) >= 2:
        return evidence
    if evidence and len(editable) >= 3:
        return evidence
    return []


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
                "dom_id": field.dom_id,
                "placeholder": field.placeholder,
                "aria_label": field.aria_label,
                "section": field.section,
                "required": field.required,
                "options": field.options,
                "disabled": field.disabled,
                "readonly": field.readonly,
                "adapter_source_path": field.adapter_source_path,
                "adapter_action": field.adapter_action,
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
    upload_dir: Path | None = None


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

    def start_for_application(self, application_id: int, *, mode: str = "fill") -> BrowserAgentSessionInfo:
        if mode not in {"verify", "fill"}:
            raise ValueError("Browser Agent mode must be verify or fill")
        with self._lock:
            existing_id = self._by_application.get(application_id)
            if existing_id and existing_id in self._sessions:
                existing = self._sessions[existing_id]
                if existing.info.mode != mode:
                    raise BrowserAgentConflictError(
                        f"Application already has a Browser Agent session in {existing.info.mode} mode"
                    )
                return existing.info

        application, job = self._application(application_id)
        if application.channel != "browser_agent":
            raise BrowserAgentConflictError("Application is not a Browser Agent session")
        if mode == "fill" and job.status != "VERIFIED_OPEN":
            raise BrowserAgentConflictError("Browser Agent fill mode requires a VERIFIED_OPEN job")
        url = application.opened_url or job.canonical_url or job.apply_url
        if not url:
            raise BrowserAgentConflictError("Application has no entry URL")
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
            mode=mode,
        )
        runtime = _RuntimeSession(
            info=info,
            handle=handle,
            upload_dir=settings.data_dir / "browser-agent" / "uploads" / session_id,
        )
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
        if runtime.info.mode != "fill":
            raise BrowserAgentConflictError("Verify-mode sessions cannot build or execute fill plans")
        scan = self._backend.scan(runtime.handle)
        adapter = select_browser_adapter(scan.url or runtime.info.url)
        scan = adapt_scan_for_browser_adapter(adapter, scan)
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
            adapter_id=adapter.id,
            adapter_display_name=adapter.display_name,
            adapter_implementation=adapter.implementation,
            adapter_capabilities=list(adapter.capabilities),
            adapter_limitations=list(adapter.limitations),
        )
        runtime.latest_plan = plan
        runtime.info.url = scan.url or runtime.info.url
        return plan

    def augment_plan_with_ai(self, session_id: str, plan_token: str) -> FillPlan:
        runtime = self._runtime(session_id)
        if runtime.info.mode != "fill":
            raise BrowserAgentConflictError("Verify-mode sessions cannot use AI fill mapping")
        plan = runtime.latest_plan
        if plan is None or plan.token != plan_token:
            raise BrowserAgentPlanError("填写计划已失效，请重新扫描表单。")
        if not plan.unmatched:
            return plan

        current_scan = adapt_scan_for_browser_adapter(
            get_browser_adapter(plan.adapter_id),
            self._backend.scan(runtime.handle),
        )
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
        if runtime.info.mode != "fill":
            raise BrowserAgentConflictError("Verify-mode sessions cannot fill form fields")
        plan = runtime.latest_plan
        if plan is None or plan.token != plan_token:
            raise BrowserAgentPlanError("填写计划已失效，请重新扫描表单。")

        by_id = {item.field_id: item for item in plan.items}
        unknown = sorted(set(field_ids) - set(by_id))
        if unknown:
            raise BrowserAgentPlanError(f"填写计划不包含字段: {', '.join(unknown)}")

        current_scan = adapt_scan_for_browser_adapter(
            get_browser_adapter(plan.adapter_id),
            self._backend.scan(runtime.handle),
        )
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

        verified_count = int(result.get("verified_count", 0))
        failed_count = int(result.get("failed_count", 0))
        uncertain_count = int(result.get("uncertain_count", 0))
        raw_results = result.get("results")
        field_results = raw_results if isinstance(raw_results, list) else []

        if failed_count:
            status = "FILLED_WITH_FAILURES"
        elif uncertain_count:
            status = "FILLED_UNCERTAIN"
        elif verified_count:
            status = "VERIFIED"
        else:
            status = "NO_VERIFIED_CHANGES"

        enriched_results: list[dict[str, Any]] = []
        for item in field_results:
            if not isinstance(item, dict):
                continue
            field_id = item.get("field_id")
            expected = by_id.get(field_id) if isinstance(field_id, str) else None
            enriched = dict(item)
            enriched["source_path"] = expected.source_path if expected is not None else ""
            enriched_results.append(enriched)

        return {
            "filled_count": int(result.get("filled_count", 0)),
            "skipped_count": int(result.get("skipped_count", 0)),
            "verified_count": verified_count,
            "failed_count": failed_count,
            "uncertain_count": uncertain_count,
            "results": enriched_results,
            "status": status,
        }

    def upload_resume(
        self,
        session_id: str,
        plan_token: str,
        field_id: str,
        resume_version_id: str,
    ) -> dict[str, Any]:
        runtime = self._runtime(session_id)
        if runtime.info.mode != "fill":
            raise BrowserAgentConflictError("Verify-mode sessions cannot upload resumes")
        plan = runtime.latest_plan
        if plan is None or plan.token != plan_token:
            raise BrowserAgentPlanError("填写计划已失效，请重新扫描表单。")

        attachment = next(
            (
                item
                for item in plan.attachments
                if item.field_id == field_id and item.kind == "resume"
            ),
            None,
        )
        if attachment is None:
            raise BrowserAgentPlanError("当前填写计划不包含可上传的简历控件。")

        current_scan = adapt_scan_for_browser_adapter(
            get_browser_adapter(plan.adapter_id),
            self._backend.scan(runtime.handle),
        )
        if current_scan.url != plan.page_url or _page_revision(current_scan) != plan.page_revision:
            raise BrowserAgentPlanError("页面结构已变化，请重新扫描表单后再上传简历。")

        descriptor = next((field for field in current_scan.fields if field.field_id == field_id), None)
        if (
            descriptor is None
            or (descriptor.input_type or descriptor.tag).lower() != "file"
            or descriptor.adapter_action != "resume_upload"
        ):
            raise BrowserAgentPlanError("目标控件不再是受控简历上传控件，请重新扫描。")

        settings = get_settings()
        engine = get_engine(settings)
        try:
            with Session(engine) as db:
                resume = db.get(ResumeVersion, resume_version_id)
                if resume is None:
                    raise ValueError("Resume version not found")

                vault_root = settings.vault_dir.resolve()
                source = (settings.vault_dir / resume.vault_relpath).resolve()
                if not source.is_relative_to(vault_root) or not source.is_file():
                    raise BrowserAgentPlanError("Resume Vault file is unavailable or outside the vault")

                if runtime.upload_dir is None:
                    raise BrowserAgentPlanError("Browser Agent upload workspace is unavailable")
                runtime.upload_dir.mkdir(parents=True, exist_ok=True)
                filename = _safe_upload_filename(resume.original_filename, resume.file_ext)
                upload_path = runtime.upload_dir / filename
                shutil.copy2(source, upload_path)

                result = self._backend.upload_file(runtime.handle, field_id, upload_path)
                observed_name = str(result.get("filename") or "")
                if observed_name != filename:
                    raise BrowserAgentPlanError(
                        "浏览器未确认所选简历文件名，请重新扫描后重试。"
                    )
        finally:
            engine.dispose()

        return {
            "field_id": field_id,
            "resume_version_id": resume_version_id,
            "filename": filename,
            "status": "VERIFIED",
        }

    def confirm_browser_verification(self, session_id: str) -> dict[str, Any]:
        runtime = self._runtime(session_id)
        if runtime.info.mode != "verify":
            raise BrowserAgentConflictError("Only verify-mode sessions can confirm browser verification")

        scan = self._backend.scan(runtime.handle)
        if not scan.url:
            raise BrowserAgentPlanError("浏览器当前页面没有可验证 URL。")
        validate_external_url(scan.url)

        evidence = _browser_verification_evidence(scan)
        if not evidence:
            raise BrowserAgentPlanError(
                "当前页面尚未显示足够的网申表单证据。请完成登录/验证码并进入实际申请表后再确认。"
            )

        revision = _page_revision(scan)
        engine = get_engine(get_settings())
        try:
            with Session(engine) as db:
                application = db.get(ApplicationSession, runtime.info.application_id)
                if application is None:
                    raise BrowserAgentSessionNotFoundError(
                        f"Application {runtime.info.application_id} not found"
                    )
                job = db.get(Job, application.job_id)
                if job is None:
                    raise BrowserAgentSessionNotFoundError(f"Job {application.job_id} not found")
                checked_url = application.opened_url or job.canonical_url or job.apply_url
                promote_browser_verified(
                    db,
                    job,
                    checked_url=checked_url,
                    final_url=scan.url,
                    evidence=evidence,
                    content_fingerprint=revision,
                )
                db.commit()
        finally:
            engine.dispose()

        runtime.latest_plan = None
        runtime.info.mode = "fill"
        runtime.info.url = scan.url
        runtime.info.status = "READY"
        return {
            "verified": True,
            "job_status": "VERIFIED_OPEN",
            "page_url": scan.url,
            "evidence_count": len(evidence),
            "page_revision": revision,
        }

    def close(self, session_id: str) -> bool:
        with self._lock:
            runtime = self._sessions.pop(session_id, None)
            if runtime is None:
                return False
            self._by_application.pop(runtime.info.application_id, None)
        self._backend.close(runtime.handle)
        if runtime.upload_dir is not None:
            shutil.rmtree(runtime.upload_dir, ignore_errors=True)
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

from __future__ import annotations

from dataclasses import asdict
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..ai.errors import ProviderError, ProviderTimeoutError
from ..browser_agent.cdp import BrowserControlError, BrowserUnavailableError
from ..browser_agent.manager import (
    BrowserAgentAIUnavailableError,
    BrowserAgentConflictError,
    BrowserAgentPlanError,
    BrowserAgentSessionNotFoundError,
    get_browser_agent_manager,
)
from ..browser_agent.models import (
    AttachmentPlanItem,
    BrowserAgentSessionInfo,
    FillPlan,
    FillPlanItem,
    PlanFieldSummary,
)
from ..config import get_settings
from ..db import get_engine
from ..models import ApplicationSession, Job
from ..profile.registry import get_field_definition, mask_profile_value

router = APIRouter(prefix="/api/browser-agent", tags=["browser-agent"])


class BrowserAgentSessionStart(BaseModel):
    application_id: int = Field(gt=0)
    mode: Literal["verify", "fill"] = "fill"


class BrowserAgentSessionRead(BaseModel):
    id: str
    application_id: int
    url: str
    status: str
    browser: str
    mode: str


class FillPlanItemRead(BaseModel):
    field_id: str
    label: str
    control_type: str
    value: object
    source_path: str
    confidence: float
    reason: str
    requires_confirmation: bool


class AttachmentPlanItemRead(BaseModel):
    field_id: str
    label: str
    kind: str
    required: bool


class PlanFieldSummaryRead(BaseModel):
    field_id: str
    label: str
    control_type: str


class FillPlanRead(BaseModel):
    token: str
    session_id: str
    page_url: str
    page_revision: str
    adapter_id: str
    adapter_display_name: str
    adapter_implementation: str
    adapter_capabilities: list[str]
    adapter_limitations: list[str]
    items: list[FillPlanItemRead]
    attachments: list[AttachmentPlanItemRead]
    unmatched: list[PlanFieldSummaryRead]
    blocked: list[PlanFieldSummaryRead]


class SemanticPlanRequest(BaseModel):
    plan_token: str = Field(min_length=1)


class FillRequest(BaseModel):
    plan_token: str = Field(min_length=1)
    field_ids: list[str]


class ResumeUploadRequest(BaseModel):
    plan_token: str = Field(min_length=1)
    field_id: str = Field(min_length=1)
    resume_version_id: str = Field(min_length=1)


class ResumeUploadRead(BaseModel):
    field_id: str
    resume_version_id: str
    filename: str
    status: str


class FillFieldResultRead(BaseModel):
    field_id: str
    requested: object
    observed: object | None = None
    status: str
    reason: str


class FillResultRead(BaseModel):
    filled_count: int
    skipped_count: int
    verified_count: int
    failed_count: int
    uncertain_count: int
    results: list[FillFieldResultRead]
    status: str


class BrowserVerificationRead(BaseModel):
    verified: bool
    job_status: str
    page_url: str
    evidence_count: int
    page_revision: str


class CloseResultRead(BaseModel):
    closed: bool


def _session_read(info: BrowserAgentSessionInfo) -> BrowserAgentSessionRead:
    return BrowserAgentSessionRead(**asdict(info))


def _plan_read(plan: FillPlan) -> FillPlanRead:
    return FillPlanRead(
        token=plan.token,
        session_id=plan.session_id,
        page_url=plan.page_url,
        page_revision=plan.page_revision,
        adapter_id=plan.adapter_id,
        adapter_display_name=plan.adapter_display_name,
        adapter_implementation=plan.adapter_implementation,
        adapter_capabilities=list(plan.adapter_capabilities),
        adapter_limitations=list(plan.adapter_limitations),
        items=[
            FillPlanItemRead(
                **{
                    **asdict(item),
                    "value": (
                        mask_profile_value(item.source_path, item.value)
                        if (
                            not item.source_path.startswith("collections.")
                            and get_field_definition(item.source_path).sensitive
                        )
                        else item.value
                    ),
                }
            )
            for item in plan.items
        ],
        attachments=[AttachmentPlanItemRead(**asdict(item)) for item in plan.attachments],
        unmatched=[PlanFieldSummaryRead(**asdict(item)) for item in plan.unmatched],
        blocked=[PlanFieldSummaryRead(**asdict(item)) for item in plan.blocked],
    )


def _mask_fill_result_value(source_path: str, value: object) -> object:
    if source_path.startswith("collections.") or value is None or value == "":
        return value
    try:
        definition = get_field_definition(source_path)
    except KeyError:
        return value
    if not definition.sensitive:
        return value
    # Do not let post-fill read-back undo the masking guarantee enforced by
    # FillPlanRead. Sensitive values stay local even after DOM verification.
    return mask_profile_value(source_path, value)


def _fill_result_read(result: dict[str, object]) -> FillResultRead:
    raw_results = result.get("results")
    rows: list[FillFieldResultRead] = []
    if isinstance(raw_results, list):
        for raw in raw_results:
            if not isinstance(raw, dict):
                continue
            source_path = raw.get("source_path")
            path = source_path if isinstance(source_path, str) else ""
            rows.append(
                FillFieldResultRead(
                    field_id=str(raw.get("field_id", "")),
                    requested=_mask_fill_result_value(path, raw.get("requested")),
                    observed=_mask_fill_result_value(path, raw.get("observed")),
                    status=str(raw.get("status", "")),
                    reason=str(raw.get("reason", "")),
                )
            )
    return FillResultRead(
        filled_count=int(result.get("filled_count", 0)),
        skipped_count=int(result.get("skipped_count", 0)),
        verified_count=int(result.get("verified_count", 0)),
        failed_count=int(result.get("failed_count", 0)),
        uncertain_count=int(result.get("uncertain_count", 0)),
        results=rows,
        status=str(result.get("status", "")),
    )


def _validate_application(application_id: int, mode: str) -> None:
    engine = get_engine(get_settings())
    try:
        with Session(engine) as session:
            application = session.get(ApplicationSession, application_id)
            if application is None:
                raise HTTPException(status_code=404, detail="Application not found")
            if application.channel != "browser_agent":
                raise HTTPException(status_code=409, detail="Application is not a Browser Agent session")
            job = session.get(Job, application.job_id)
            if job is None:
                raise HTTPException(status_code=404, detail="Job not found")
            if mode == "fill" and job.status != "VERIFIED_OPEN":
                raise HTTPException(status_code=409, detail="Browser Agent fill mode requires a VERIFIED_OPEN job")
            if not (application.opened_url or job.canonical_url or job.apply_url):
                raise HTTPException(status_code=409, detail="Browser Agent requires an entry URL")
    finally:
        engine.dispose()


@router.post("/sessions", response_model=BrowserAgentSessionRead)
def start_browser_agent_session(body: BrowserAgentSessionStart) -> BrowserAgentSessionRead:
    _validate_application(body.application_id, body.mode)
    try:
        return _session_read(
            get_browser_agent_manager().start_for_application(
                body.application_id,
                mode=body.mode,
            )
        )
    except BrowserAgentSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except BrowserAgentConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except BrowserUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except BrowserControlError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/sessions", response_model=list[BrowserAgentSessionRead])
def list_browser_agent_sessions() -> list[BrowserAgentSessionRead]:
    return [_session_read(info) for info in get_browser_agent_manager().list_sessions()]


@router.post("/sessions/{session_id}/plan", response_model=FillPlanRead)
def build_browser_agent_plan(session_id: str) -> FillPlanRead:
    try:
        return _plan_read(get_browser_agent_manager().build_plan(session_id))
    except BrowserAgentSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except BrowserAgentConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (BrowserControlError, BrowserUnavailableError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/sessions/{session_id}/semantic-plan", response_model=FillPlanRead)
def build_browser_agent_semantic_plan(session_id: str, body: SemanticPlanRequest) -> FillPlanRead:
    try:
        return _plan_read(
            get_browser_agent_manager().augment_plan_with_ai(session_id, body.plan_token)
        )
    except BrowserAgentSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except BrowserAgentPlanError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except BrowserAgentConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except BrowserAgentAIUnavailableError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ProviderTimeoutError as exc:
        raise HTTPException(status_code=504, detail=str(exc)) from exc
    except ProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except BrowserControlError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/sessions/{session_id}/fill", response_model=FillResultRead)
def fill_browser_agent_plan(session_id: str, body: FillRequest) -> FillResultRead:
    try:
        result = get_browser_agent_manager().fill(session_id, body.plan_token, body.field_ids)
        return _fill_result_read(result)
    except BrowserAgentSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except BrowserAgentPlanError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except BrowserAgentConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except BrowserControlError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/sessions/{session_id}/resume-upload", response_model=ResumeUploadRead)
def upload_browser_agent_resume(session_id: str, body: ResumeUploadRequest) -> ResumeUploadRead:
    try:
        result = get_browser_agent_manager().upload_resume(
            session_id,
            body.plan_token,
            body.field_id,
            body.resume_version_id,
        )
        return ResumeUploadRead(**result)
    except BrowserAgentSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (BrowserAgentConflictError, BrowserAgentPlanError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except BrowserControlError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/sessions/{session_id}/verify", response_model=BrowserVerificationRead)
def confirm_browser_agent_verification(session_id: str) -> BrowserVerificationRead:
    try:
        result = get_browser_agent_manager().confirm_browser_verification(session_id)
        return BrowserVerificationRead(**result)
    except BrowserAgentSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (BrowserAgentConflictError, BrowserAgentPlanError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (BrowserControlError, BrowserUnavailableError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.delete("/sessions/{session_id}", response_model=CloseResultRead)
def close_browser_agent_session(session_id: str) -> CloseResultRead:
    return CloseResultRead(closed=get_browser_agent_manager().close(session_id))

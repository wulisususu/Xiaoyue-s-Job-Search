from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..ai.errors import ProviderError
from ..ai.openai_compatible import OpenAICompatibleExtractionProvider
from ..ai.provider import normalize_base_url
from ..ai.secrets import (
    DEFAULT_AI_API_KEY_REF,
    CredentialStoreUnavailableError,
    get_secret_store,
)
from ..config import get_settings
from ..db import get_engine
from ..models import (
    AIExtractionRun,
    AIProviderConfig,
    ProfileCollectionDraft,
    ProfileDraftField,
    ResumeVersion,
)
from ..profile.extraction_runs import execute_extraction_run

router = APIRouter(prefix="/api/ai", tags=["ai"])


class AIProviderWrite(BaseModel):
    provider_name: str = Field(min_length=1, max_length=160)
    base_url: str = Field(min_length=1)
    text_model: str = Field(min_length=1, max_length=240)
    vision_model: str | None = Field(default=None, max_length=240)
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    timeout_seconds: int = Field(default=60, ge=5, le=300)
    supports_json_schema: bool = True
    supports_vision: bool = False


class AIAPIKeyWrite(BaseModel):
    api_key: str = Field(min_length=1)


class AIProviderRead(BaseModel):
    id: str
    provider_name: str
    base_url: str
    text_model: str
    vision_model: str | None
    temperature: float
    timeout_seconds: int
    supports_json_schema: bool
    supports_vision: bool
    has_api_key: bool
    created_at: str
    updated_at: str


def _has_api_key(config: AIProviderConfig) -> bool:
    if not config.secret_ref:
        return False
    try:
        return bool(get_secret_store().get_secret(config.secret_ref))
    except CredentialStoreUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _provider_read(config: AIProviderConfig) -> AIProviderRead:
    return AIProviderRead(
        id=config.id,
        provider_name=config.provider_name,
        base_url=config.base_url,
        text_model=config.text_model,
        vision_model=config.vision_model,
        temperature=config.temperature,
        timeout_seconds=config.timeout_seconds,
        supports_json_schema=config.supports_json_schema,
        supports_vision=config.supports_vision,
        has_api_key=_has_api_key(config),
        created_at=config.created_at.isoformat(),
        updated_at=config.updated_at.isoformat(),
    )


@router.get("/provider", response_model=AIProviderRead | None)
def get_provider() -> AIProviderRead | None:
    engine = get_engine(get_settings())
    try:
        with Session(engine) as session:
            config = session.get(AIProviderConfig, "default")
            return _provider_read(config) if config is not None else None
    finally:
        engine.dispose()


@router.put("/provider", response_model=AIProviderRead)
def put_provider(body: AIProviderWrite) -> AIProviderRead:
    try:
        base_url = normalize_base_url(body.base_url)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    provider_name = body.provider_name.strip()
    text_model = body.text_model.strip()
    vision_model = body.vision_model.strip() if body.vision_model and body.vision_model.strip() else None
    if not provider_name:
        raise HTTPException(status_code=422, detail="Provider name is required")
    if not text_model:
        raise HTTPException(status_code=422, detail="Text model is required")

    engine = get_engine(get_settings())
    try:
        with Session(engine) as session:
            config = session.get(AIProviderConfig, "default")
            if config is None:
                config = AIProviderConfig(
                    id="default",
                    provider_name=provider_name,
                    base_url=base_url,
                    text_model=text_model,
                    vision_model=vision_model,
                    temperature=body.temperature,
                    timeout_seconds=body.timeout_seconds,
                    supports_json_schema=body.supports_json_schema,
                    supports_vision=body.supports_vision,
                )
                session.add(config)
            else:
                config.provider_name = provider_name
                config.base_url = base_url
                config.text_model = text_model
                config.vision_model = vision_model
                config.temperature = body.temperature
                config.timeout_seconds = body.timeout_seconds
                config.supports_json_schema = body.supports_json_schema
                config.supports_vision = body.supports_vision
            session.commit()
            session.refresh(config)
            return _provider_read(config)
    finally:
        engine.dispose()


@router.put("/provider/api-key", response_model=AIProviderRead)
def put_provider_api_key(body: AIAPIKeyWrite) -> AIProviderRead:
    api_key = body.api_key.strip()
    if not api_key:
        raise HTTPException(status_code=422, detail="API key is required")

    engine = get_engine(get_settings())
    try:
        with Session(engine) as session:
            config = session.get(AIProviderConfig, "default")
            if config is None:
                raise HTTPException(status_code=409, detail="Configure the AI provider before saving an API key")

            # Near-transactional rotation across two stores (keyring + DB):
            # write the key under a FRESH unique ref, switch the DB pointer
            # to it, and only after a successful commit delete the old ref.
            # Any failure along the way leaves the previous key + ref pair
            # fully intact.
            store = get_secret_store()
            new_ref = f"{DEFAULT_AI_API_KEY_REF}:{uuid.uuid4().hex}"
            old_ref = config.secret_ref
            try:
                store.set_secret(new_ref, api_key)
            except CredentialStoreUnavailableError as exc:
                raise HTTPException(status_code=503, detail=str(exc)) from exc

            config.secret_ref = new_ref
            try:
                session.commit()
            except Exception:
                session.rollback()
                try:
                    store.delete_secret(new_ref)
                except CredentialStoreUnavailableError:
                    pass
                raise
            if old_ref and old_ref != new_ref:
                try:
                    store.delete_secret(old_ref)
                except CredentialStoreUnavailableError:
                    pass
            session.refresh(config)
            return _provider_read(config)
    finally:
        engine.dispose()


@router.delete("/provider/api-key", response_model=AIProviderRead)
def delete_provider_api_key() -> AIProviderRead:
    engine = get_engine(get_settings())
    try:
        with Session(engine) as session:
            config = session.get(AIProviderConfig, "default")
            if config is None:
                raise HTTPException(status_code=409, detail="AI provider is not configured")

            # Point the DB at "no key" FIRST, commit, and only then remove
            # the credential: if the commit fails the keyring entry is still
            # referenced and usable; if the keyring delete fails afterwards
            # the leftover secret is unreferenced and harmless.
            old_ref = config.secret_ref
            config.secret_ref = None
            try:
                session.commit()
            except Exception:
                session.rollback()
                raise
            if old_ref:
                try:
                    get_secret_store().delete_secret(old_ref)
                except CredentialStoreUnavailableError:
                    pass
            session.refresh(config)
            return _provider_read(config)
    finally:
        engine.dispose()


class AIProviderNotConfiguredError(RuntimeError):
    pass


class AIProviderKeyMissingError(RuntimeError):
    pass


class AIExtractionRunCreate(BaseModel):
    resume_version_id: str = Field(min_length=1, max_length=32)


class AIExtractionRunRead(BaseModel):
    id: int
    resume_version_id: str
    provider: str
    model: str
    prompt_version: str
    schema_version: str
    status: str
    input_hash: str | None = None
    error: str | None = None
    created_at: str
    completed_at: str | None = None
    scalar_draft_count: int
    collection_draft_count: int


def build_default_provider(session: Session) -> OpenAICompatibleExtractionProvider:
    """Materialize the unified provider from the default AIProviderConfig.

    Swapping OpenAI/DeepSeek/Qwen only changes the config row; this factory
    and every caller above it stay untouched.
    """
    config = session.get(AIProviderConfig, "default")
    if config is None:
        raise AIProviderNotConfiguredError("Configure the AI provider before running an extraction")
    if not config.secret_ref:
        raise AIProviderKeyMissingError("Save an AI provider API key before running an extraction")
    try:
        api_key = get_secret_store().get_secret(config.secret_ref)
    except CredentialStoreUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if not api_key:
        raise AIProviderKeyMissingError("Save an AI provider API key before running an extraction")
    return OpenAICompatibleExtractionProvider(config, api_key)


def _run_read(session: Session, run: AIExtractionRun) -> AIExtractionRunRead:
    scalar_count = int(
        session.scalar(
            select(func.count(ProfileDraftField.id)).where(
                ProfileDraftField.extraction_run_id == run.id
            )
        )
        or 0
    )
    collection_count = int(
        session.scalar(
            select(func.count(ProfileCollectionDraft.id)).where(
                ProfileCollectionDraft.extraction_run_id == run.id
            )
        )
        or 0
    )
    return AIExtractionRunRead(
        id=run.id,
        resume_version_id=run.resume_version_id,
        provider=run.provider,
        model=run.model,
        prompt_version=run.prompt_version,
        schema_version=run.schema_version,
        status=run.status,
        input_hash=run.input_hash,
        error=run.error,
        created_at=run.created_at.isoformat(),
        completed_at=run.completed_at.isoformat() if run.completed_at else None,
        scalar_draft_count=scalar_count,
        collection_draft_count=collection_count,
    )


@router.post("/extraction-runs", response_model=AIExtractionRunRead)
def create_extraction_run(body: AIExtractionRunCreate) -> AIExtractionRunRead:
    """The one formal AI chain entrypoint:
    Resume → AIExtractionRun → provider → validated PENDING drafts."""
    engine = get_engine(get_settings())
    try:
        with Session(engine) as session:
            resume = session.get(ResumeVersion, body.resume_version_id)
            if resume is None:
                raise HTTPException(status_code=404, detail="Resume version not found")
            if resume.extraction_status != "EXTRACTED" or not resume.extracted_text:
                raise HTTPException(
                    status_code=422,
                    detail="Resume version has no extracted text to run extraction on",
                )
            try:
                provider = build_default_provider(session)
            except AIProviderNotConfiguredError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            except AIProviderKeyMissingError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc

            try:
                run = execute_extraction_run(session, resume, provider)
            except ProviderError:
                # The run row is the record: provider failures come back as a
                # FAILED run with the error text, never as a silent 5xx.
                failed = session.scalar(
                    select(AIExtractionRun)
                    .where(AIExtractionRun.resume_version_id == resume.id)
                    .order_by(AIExtractionRun.id.desc())
                )
                if failed is None:
                    raise
                return _run_read(session, failed)
            return _run_read(session, run)
    finally:
        engine.dispose()


@router.get("/extraction-runs", response_model=list[AIExtractionRunRead])
def list_extraction_runs(
    resume_version_id: str | None = Query(default=None),
) -> list[AIExtractionRunRead]:
    engine = get_engine(get_settings())
    try:
        with Session(engine) as session:
            query = select(AIExtractionRun).order_by(AIExtractionRun.id.desc())
            if resume_version_id:
                query = query.where(AIExtractionRun.resume_version_id == resume_version_id)
            runs = session.scalars(query).all()
            return [_run_read(session, run) for run in runs]
    finally:
        engine.dispose()

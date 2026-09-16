from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..ai.provider import normalize_base_url
from ..ai.secrets import (
    DEFAULT_AI_API_KEY_REF,
    CredentialStoreUnavailableError,
    get_secret_store,
)
from ..config import get_settings
from ..db import get_engine
from ..models import AIProviderConfig

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

            store = get_secret_store()
            try:
                store.set_secret(DEFAULT_AI_API_KEY_REF, api_key)
            except CredentialStoreUnavailableError as exc:
                raise HTTPException(status_code=503, detail=str(exc)) from exc

            config.secret_ref = DEFAULT_AI_API_KEY_REF
            try:
                session.commit()
            except Exception:
                session.rollback()
                try:
                    store.delete_secret(DEFAULT_AI_API_KEY_REF)
                except CredentialStoreUnavailableError:
                    pass
                raise
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

            if config.secret_ref:
                try:
                    get_secret_store().delete_secret(config.secret_ref)
                except CredentialStoreUnavailableError as exc:
                    raise HTTPException(status_code=503, detail=str(exc)) from exc
            config.secret_ref = None
            session.commit()
            session.refresh(config)
            return _provider_read(config)
    finally:
        engine.dispose()

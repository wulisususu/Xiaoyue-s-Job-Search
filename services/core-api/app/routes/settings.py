from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_engine
from ..models import AppSetting

router = APIRouter(prefix="/api/settings", tags=["settings"])

_SECRET_FRAGMENTS = ("api_key", "token", "secret", "password")


class SettingWrite(BaseModel):
    value: str


class SettingRead(BaseModel):
    key: str
    value: str


def _validate_key(key: str) -> None:
    lowered = key.lower()
    if any(fragment in lowered for fragment in _SECRET_FRAGMENTS):
        raise HTTPException(
            status_code=400,
            detail="Secrets must be stored in the operating system credential store.",
        )


@router.get("")
def list_settings() -> dict[str, str]:
    engine = get_engine(get_settings())
    try:
        with Session(engine) as session:
            rows = session.scalars(select(AppSetting).order_by(AppSetting.key)).all()
            return {row.key: row.value for row in rows}
    finally:
        engine.dispose()


@router.put("/{key}", response_model=SettingRead)
def put_setting(key: str, payload: SettingWrite) -> SettingRead:
    _validate_key(key)
    engine = get_engine(get_settings())
    try:
        with Session(engine) as session:
            row = session.get(AppSetting, key)
            if row is None:
                row = AppSetting(key=key, value=payload.value)
                session.add(row)
            else:
                row.value = payload.value
            session.commit()
            return SettingRead(key=row.key, value=row.value)
    finally:
        engine.dispose()

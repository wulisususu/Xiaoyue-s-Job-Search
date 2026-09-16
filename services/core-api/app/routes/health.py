from fastapi import APIRouter
from sqlalchemy import text

from ..config import get_settings
from ..db import get_engine

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/health")
def health() -> dict[str, str]:
    settings = get_settings()
    engine = get_engine(settings)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    finally:
        engine.dispose()

    return {"status": "ok", "database": "ok", "version": "0.1.0"}

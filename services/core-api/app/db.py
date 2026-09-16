from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session

from .config import AppSettings, get_settings
from .models import Base


def get_engine(settings: AppSettings | None = None) -> Engine:
    resolved = settings or get_settings()
    return create_engine(
        f"sqlite:///{resolved.database_path}",
        connect_args={"check_same_thread": False},
    )


def init_db(settings: AppSettings | None = None) -> None:
    engine = get_engine(settings)
    Base.metadata.create_all(engine)
    engine.dispose()


def open_session(settings: AppSettings | None = None) -> Session:
    return Session(get_engine(settings))

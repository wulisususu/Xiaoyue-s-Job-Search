from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session

from .config import AppSettings, get_settings
from .models import Base


def _configure_sqlite_connection(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
    finally:
        cursor.close()


def get_engine(settings: AppSettings | None = None) -> Engine:
    resolved = settings or get_settings()
    engine = create_engine(
        f"sqlite:///{resolved.database_path}",
        connect_args={"check_same_thread": False},
    )
    event.listen(engine, "connect", _configure_sqlite_connection)
    return engine


def init_db(settings: AppSettings | None = None) -> None:
    engine = get_engine(settings)
    Base.metadata.create_all(engine)
    engine.dispose()


def open_session(settings: AppSettings | None = None) -> Session:
    return Session(get_engine(settings))

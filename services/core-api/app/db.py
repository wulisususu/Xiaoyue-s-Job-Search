from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session

from .config import AppSettings, get_settings


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


def _alembic_config(settings: AppSettings):
    from alembic.config import Config

    core_root = Path(__file__).resolve().parents[1]
    config = Config(core_root / "alembic.ini")
    config.set_main_option("script_location", str(core_root / "alembic"))
    config.attributes["db_url"] = f"sqlite:///{settings.database_path}"
    return config


def _run_migrations(settings: AppSettings) -> None:
    from alembic import command

    command.upgrade(_alembic_config(settings), "head")


def init_db(settings: AppSettings | None = None) -> None:
    """Prepare the database schema. Alembic is the single schema
    source-of-truth: every startup runs `upgrade head`, which builds the
    full schema on an empty database (0001_initial_schema -> ...) and
    applies incremental migrations to existing ones. create_all is NOT
    part of the startup path anymore; test fixtures may still use it."""
    resolved = settings or get_settings()
    resolved.data_dir.mkdir(parents=True, exist_ok=True)
    resolved.vault_dir.mkdir(parents=True, exist_ok=True)
    _run_migrations(resolved)


def open_session(settings: AppSettings | None = None) -> Session:
    return Session(get_engine(settings))

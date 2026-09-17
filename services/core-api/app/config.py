from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="XIAOYUE_", extra="ignore")

    app_name: str = "Xiaoyue Job Search"
    host: str = "127.0.0.1"
    port: int = 8765
    # Set by the Tauri shell per launch (XIAOYUE_SESSION_TOKEN): when present,
    # every /api/* request must carry `Authorization: Bearer <token>`. The
    # health endpoint stays open so the sidecar readiness probe works.
    session_token: str | None = None
    data_dir: Path = Field(default_factory=lambda: Path.home() / ".xiaoyue-job-search")

    @property
    def database_path(self) -> Path:
        return self.data_dir / "xiaoyue.db"

    @property
    def vault_dir(self) -> Path:
        return self.data_dir / "vault"


def get_settings() -> AppSettings:
    settings = AppSettings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.vault_dir.mkdir(parents=True, exist_ok=True)
    return settings

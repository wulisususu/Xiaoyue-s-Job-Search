"""PyInstaller entrypoint: run the core API under the packaged runtime.

Imports the FastAPI app object directly (not via the "app.main:app" string)
so PyInstaller's static analysis follows the whole app import graph into the
bundle. The Tauri shell passes XIAOYUE_PORT / XIAOYUE_SESSION_TOKEN /
XIAOYUE_DATA_DIR as process env; the app itself reads them via pydantic
settings.
"""
from __future__ import annotations

import os

import uvicorn

from app.main import app as application


def main() -> None:
    host = os.environ.get("XIAOYUE_HOST", "127.0.0.1")
    port = int(os.environ.get("XIAOYUE_PORT", "8765"))
    uvicorn.run(application, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()

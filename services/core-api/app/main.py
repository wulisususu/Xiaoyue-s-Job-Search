from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .db import init_db
from .routes.health import router as health_router
from .routes.jobs import router as jobs_router
from .routes.settings import router as settings_router


def create_app() -> FastAPI:
    settings = get_settings()
    init_db(settings)

    application = FastAPI(title=settings.app_name, version="0.1.0")
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:1420", "tauri://localhost"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.include_router(health_router)
    application.include_router(jobs_router)
    application.include_router(settings_router)
    return application


app = create_app()

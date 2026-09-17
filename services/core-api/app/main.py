import hmac

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_engine, init_db
from .resumes.vault import reconcile_vault
from .routes.ai import router as ai_router
from .routes.health import router as health_router
from .routes.jobs import router as jobs_router
from .routes.profile import router as profile_router
from .routes.resumes import router as resumes_router
from .routes.settings import router as settings_router
from .routes.sources import router as sources_router
from .routes.verification import router as verification_router


def create_app() -> FastAPI:
    settings = get_settings()
    init_db(settings)

    engine = get_engine(settings)
    try:
        with Session(engine) as session:
            reconcile_vault(session, settings)
    finally:
        engine.dispose()

    application = FastAPI(title=settings.app_name, version="0.1.0")
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:1420", "tauri://localhost"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*", "Authorization"],
    )

    if settings.session_token:
        # Trust boundary for the desktop app: only the shell that launched
        # this sidecar knows the per-launch token, so other local processes
        # (or web pages probing localhost) cannot drive the API.
        expected = f"Bearer {settings.session_token}"

        @application.middleware("http")
        async def _require_session_token(request, call_next):
            path = request.url.path
            if path.startswith("/api/") and path != "/api/health":
                provided = request.headers.get("authorization", "")
                if not hmac.compare_digest(provided, expected):
                    return JSONResponse(status_code=401, content={"detail": "invalid session token"})
            return await call_next(request)

    application.include_router(ai_router)
    application.include_router(health_router)
    application.include_router(jobs_router)
    application.include_router(profile_router)
    application.include_router(resumes_router)
    application.include_router(settings_router)
    application.include_router(sources_router)
    application.include_router(verification_router)
    return application


app = create_app()

import logging

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError

from app.api.deps import csrf_protect
from app.api.routes import auth, jobs, misc, portals, profile, settings
from app.core.config import get_settings

logger = logging.getLogger("app")


def create_app() -> FastAPI:
    cfg = get_settings()
    dev = cfg.environment != "production"
    app = FastAPI(
        title=cfg.app_name,
        version="0.1.0",
        dependencies=[Depends(csrf_protect)],
        docs_url="/api/docs" if dev else None,
        redoc_url=None,
        openapi_url="/api/openapi.json" if dev else None,
    )

    # Normal traffic arrives same-origin through the Next.js /api proxy; CORS only covers the
    # explicitly configured frontend origins.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["content-type", "x-csrf-token"],
    )

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        if not request.url.path.startswith("/api/docs"):
            response.headers.setdefault("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
            response.headers.setdefault("Cache-Control", "no-store")
        return response

    @app.exception_handler(OperationalError)
    async def db_unavailable(_request: Request, exc: OperationalError) -> JSONResponse:
        # Typical on free tiers while the database compute resumes from idle suspend.
        logger.warning("database unavailable: %s", type(exc.orig).__name__)
        return JSONResponse(
            {
                "detail": "Database temporarily unavailable. It may be waking up; retry shortly.",
                "code": "db_unavailable",
            },
            status_code=503,
            headers={"Retry-After": "5"},
        )

    for r in (auth.router, profile.router, portals.router, jobs.router, settings.router, misc.router):
        app.include_router(r, prefix="/api")
    return app


app = create_app()

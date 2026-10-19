"""Local reference app. Run: .venv/bin/uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8765"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from .admin import build_admin_router
from .portal import build_portal_router
from .services import build_services
from .settings import load_settings

HERE = Path(__file__).parent


def create_app(settings=None, services=None) -> FastAPI:
    settings = settings or load_settings()
    services = services or build_services(settings)
    app = FastAPI(title="Genie custom-claims reference app", docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(SessionMiddleware, secret_key=settings.session_secret, session_cookie="claims_ref_session", same_site="strict")
    templates = Jinja2Templates(directory=str(HERE / "templates"))
    app.mount("/static", StaticFiles(directory=str(HERE / "static")), name="static")
    app.include_router(build_portal_router(settings, services, templates))
    app.include_router(build_admin_router(settings, services, templates))

    @app.get("/")
    def root():
        return RedirectResponse("/portal")

    return app

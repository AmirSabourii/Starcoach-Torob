"""ASGI entrypoint. Serves the API and the Persian frontend from one process."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from backend.app.api.routes import router
from backend.app.config import get_settings

try:
    from gt_lib import DatabaseNotReady
except ImportError:  # engine path is inserted by routes
    from backend.app.engine.gt_lib import DatabaseNotReady

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Starcoach Torob",
        summary="دستیار خرید حضوری روی دادهٔ ترب",
        version="0.2.0",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_list(),
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )
    app.include_router(router)

    @app.exception_handler(DatabaseNotReady)
    async def _missing_db(_request, _exc: DatabaseNotReady):
        return JSONResponse(
            status_code=503,
            content={"detail": "پایگاه داده هنوز ساخته نشده است. اسکریپت scripts/build_db.py را اجرا کنید."},
        )

    @app.get("/")
    def index():
        return FileResponse(FRONTEND_DIR / "index.html")

    @app.get("/app.js")
    def app_js():
        return FileResponse(FRONTEND_DIR / "app.js", media_type="text/javascript")

    @app.get("/app.css")
    def app_css():
        return FileResponse(FRONTEND_DIR / "app.css", media_type="text/css")

    @app.get("/favicon.ico")
    def favicon():
        icon = FRONTEND_DIR / "assets" / "logo.png"
        if icon.exists():
            return FileResponse(icon)
        return Response(status_code=204)

    app.mount("/assets", StaticFiles(directory=FRONTEND_DIR / "assets"), name="assets")
    app.mount("/fonts", StaticFiles(directory=FRONTEND_DIR / "fonts"), name="fonts")
    app.mount("/screens", StaticFiles(directory=FRONTEND_DIR / "screens"), name="screens")
    return app


app = create_app()

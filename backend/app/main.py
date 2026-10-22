"""ASGI entrypoint. Serves the API and the Persian frontend from one process."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from backend.app.api.routes import router
from backend.app.config import get_settings
from backend.app.db.connection import DatabaseNotReady

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Starcoach Torob",
        summary="دستیار خرید حضوری روی دادهٔ ترب",
        version="0.1.0",
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

    @app.get("/favicon.ico")
    def favicon():
        return Response(status_code=204)

    app.mount("/css", StaticFiles(directory=FRONTEND_DIR / "css"), name="css")
    app.mount("/js", StaticFiles(directory=FRONTEND_DIR / "js"), name="js")
    return app


app = create_app()

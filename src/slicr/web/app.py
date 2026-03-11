"""
FastAPI-приложение slicr.

Запуск: python -m slicr.web
Доступ: http://<IP>:8080
"""

import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from slicr.config import Config, load_config
from slicr.utils.logging_config import setup_logging
from slicr.web.state import AppState

STATIC_DIR = Path(__file__).parent / "static"

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Инициализация и завершение приложения."""
    config = load_config()
    state = AppState(config)
    app.state.app_state = state
    logger.info("slicr web-service запущен")
    yield
    await state.shutdown()
    logger.info("slicr web-service остановлен")


def create_app() -> FastAPI:
    """Создать FastAPI-приложение."""
    setup_logging()

    app = FastAPI(
        title="slicr",
        description="Веб-сервис нарезки видео",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    from slicr.web.routes import router
    from slicr.web.ws import ws_router

    app.include_router(router, prefix="/api")
    app.include_router(ws_router)

    # Главная страница
    @app.get("/")
    async def index():
        return FileResponse(STATIC_DIR / "index.html")

    # Статика
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    return app
